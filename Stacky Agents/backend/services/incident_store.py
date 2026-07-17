"""Plan 131 — Resolutor de incidencias multimodal: intake (store de persistencia).

Contrato §4.1 del plan: límites/almacenamiento del intake (texto + archivos) que
el operador carga en el modal "Resolver incidencia".

Almacenamiento: `data_dir()/incidents/<incident_id>/` con `intake.json` + los
archivos con `stored_name` sanitizado. Ledger global
`data_dir()/incidents/ledger.json` = lista de resúmenes {id, created_at, status,
title, tracker_id} para listar sin abrir cada intake.json.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import runtime_paths

MAX_FILES = 10
MAX_FILE_BYTES = 10 * 1024 * 1024        # 10 MB por archivo
MAX_TOTAL_BYTES = 25 * 1024 * 1024       # 25 MB por incidencia
MAX_TEXT_LEN = 20_000                    # caracteres del texto libre
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
TEXT_EXTENSIONS = {".txt", ".log", ".md", ".json", ".csv", ".xml", ".yaml", ".yml",
                   ".sql", ".ps1", ".sh", ".py", ".cs", ".ts", ".tsx", ".js",
                   ".html", ".css", ".config"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | TEXT_EXTENSIONS | {".pdf"}

_LEDGER_LOCK = threading.Lock()


def incidents_root() -> Path:
    return runtime_paths.data_dir() / "incidents"


def _ledger_path() -> Path:
    return incidents_root() / "ledger.json"


def _read_ledger() -> list[dict]:
    path = _ledger_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — ledger corrupto no debe tumbar el flujo
        return []


def _write_ledger(entries: list[dict]) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_filename(name: str) -> str:
    """Basename defensivo (anti path-traversal) + charset seguro + cap 120 chars."""
    base = re.split(r"[\\/]", name or "")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", base)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned[:120]
    return cleaned or "archivo"


def _ext_of(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def _kind_for_ext(ext: str) -> str:
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "binary"


def _derive_title(text: str, n_files: int) -> str | None:
    stripped = (text or "").strip()
    if stripped:
        return stripped.splitlines()[0][:80]
    if n_files:
        plural = "s" if n_files != 1 else ""
        return f"Incidencia sin texto ({n_files} archivo{plural})"
    return None


def _unique_stored_name(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    stem, dot, suffix = base.rpartition(".")
    stem = stem if dot else base
    suffix = f".{suffix}" if dot else ""
    i = 2
    while True:
        candidate = f"{stem}_{i}{suffix}"
        if candidate not in used:
            return candidate
        i += 1


def create_incident(text: str, files: list[tuple[str, bytes]]) -> dict:
    """Valida, persiste archivos + intake.json, y agrega entrada al ledger.

    Lanza ValueError con mensaje claro ante violación de límites:
    'empty_intake', 'too_many_files', 'file_too_big:<name>',
    'ext_not_allowed:<ext>', 'total_too_big'.
    """
    text = (text or "")[:MAX_TEXT_LEN]
    files = files or []

    if not text.strip() and not files:
        raise ValueError("empty_intake")
    if len(files) > MAX_FILES:
        raise ValueError("too_many_files")

    total_bytes = 0
    for fname, data in files:
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"file_too_big:{fname}")
        ext = _ext_of(fname)
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"ext_not_allowed:{ext}")
        total_bytes += len(data)
    if total_bytes > MAX_TOTAL_BYTES:
        raise ValueError("total_too_big")

    incident_id = (
        "inc_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6]
    )
    incident_dir = incidents_root() / incident_id
    incident_dir.mkdir(parents=True, exist_ok=True)

    used_names: set[str] = set()
    files_meta: list[dict] = []
    for fname, data in files:
        stored_name = _unique_stored_name(sanitize_filename(fname), used_names)
        used_names.add(stored_name)
        (incident_dir / stored_name).write_bytes(data)
        ext = _ext_of(stored_name)
        files_meta.append({
            "name": fname,
            "stored_name": stored_name,
            "bytes": len(data),
            "ext": ext,
            "kind": _kind_for_ext(ext),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    created_at = datetime.now(timezone.utc).isoformat()
    incident = {
        "id": incident_id,
        "created_at": created_at,
        "text": text,
        "files": files_meta,
        "status": "capturada",
        "execution_id": None,
        "tracker_id": None,
        "tracker_url": None,
        "epic_id": None,
        "doc_path": None,
        "error": None,
        # Campo aditivo (no rompe §4.1): título derivado para el ledger; se
        # actualiza con el <h1> real del desglose vía update_incident en F5.
        "title": _derive_title(text, len(files_meta)),
    }
    (incident_dir / "intake.json").write_text(
        json.dumps(incident, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with _LEDGER_LOCK:
        entries = _read_ledger()
        entries.append({
            "id": incident_id,
            "created_at": created_at,
            "status": incident["status"],
            "title": incident["title"],
            "tracker_id": None,
        })
        _write_ledger(entries)

    return incident


def get_incident(incident_id: str) -> dict | None:
    path = incidents_root() / incident_id / "intake.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — intake corrupto se trata como ausente
        return None


def update_incident(incident_id: str, **patch) -> dict:
    """Aplica patch a intake.json y sincroniza el resumen del ledger. Lanza
    ValueError si el incidente no existe."""
    incident = get_incident(incident_id)
    if incident is None:
        raise ValueError(f"incident_not_found:{incident_id}")

    incident.update(patch)
    path = incidents_root() / incident_id / "intake.json"
    path.write_text(json.dumps(incident, ensure_ascii=False, indent=2), encoding="utf-8")

    with _LEDGER_LOCK:
        entries = _read_ledger()
        for entry in entries:
            if entry.get("id") == incident_id:
                entry["status"] = incident.get("status", entry.get("status"))
                entry["title"] = incident.get("title", entry.get("title"))
                entry["tracker_id"] = incident.get("tracker_id", entry.get("tracker_id"))
                break
        _write_ledger(entries)

    return incident


def list_incidents() -> list[dict]:
    """Resúmenes del ledger, orden created_at desc."""
    with _LEDGER_LOCK:
        entries = list(_read_ledger())
    return sorted(entries, key=lambda e: e.get("created_at") or "", reverse=True)
