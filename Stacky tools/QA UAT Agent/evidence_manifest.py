"""evidence_manifest.py — Manifiesto de evidencia con hash (Plan 240 F7 / 241 F8).

"Evidencias claras y resultados repetibles" exige poder demostrar que la evidencia
CORRESPONDE al run y que no cambio despues. Hoy hay artefactos sueltos sin indice ni
integridad. Este modulo indexa el directorio del run con sha256 por archivo y permite
re-verificarlo con un comando.

100% DETERMINISTA (orden por path ascendente) => dos corridas sobre el mismo
directorio producen el MISMO manifiesto salvo `generated_at`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

_KIND_BY_SUFFIX = {".png": "screenshot", ".webm": "video", ".zip": "trace",
                   ".json": "data", ".jsonl": "log", ".html": "report",
                   ".log": "log", ".txt": "log", ".ts": "spec"}
_MANIFEST_NAME = "evidence_manifest.json"
_MAX_FILES = 5000          # cota dura: un run patologico no puede colgar el walk
_CHUNK = 64 * 1024


def _sha256_of(path: Path) -> str:
    """sha256 por chunks de 64 KB (no carga archivos enteros en memoria)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _kind_of(path: Path) -> str:
    return _KIND_BY_SUFFIX.get(path.suffix.lower(), "other")


def build_evidence_manifest(run_dir) -> dict:
    """Indexa run_dir recursivo y escribe <run_dir>/evidence_manifest.json.

    NUNCA lanza: directorio inexistente => {"ok": False, "error": "run_dir_missing"}.
    """
    try:
        base = Path(run_dir)
        if not base.is_dir():
            return {"ok": False, "error": "run_dir_missing", "run_dir": str(base)}

        files: list = []
        truncated = False
        for p in sorted(base.rglob("*"), key=lambda x: str(x.relative_to(base)).replace("\\", "/")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base)).replace("\\", "/")
            if rel == _MANIFEST_NAME:
                continue                       # el manifiesto nunca se indexa a si mismo
            if len(files) >= _MAX_FILES:
                truncated = True
                break
            try:
                files.append({
                    "path": rel,
                    "bytes": p.stat().st_size,
                    "sha256": _sha256_of(p),
                    "kind": _kind_of(p),
                })
            except Exception:  # noqa: BLE001 — un archivo ilegible no rompe el walk
                continue

        counts = {"total": len(files)}
        for f in files:
            counts[f["kind"]] = counts.get(f["kind"], 0) + 1

        manifest = {
            "ok": True,
            "run_dir": str(base),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "files": files,
            "counts": counts,
            "truncated": truncated,
        }
        try:
            (base / _MANIFEST_NAME).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return manifest
    except Exception as exc:  # noqa: BLE001 — NUNCA lanza
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:250]}


def verify_evidence_manifest(run_dir) -> dict:
    """Relee el manifiesto y RECALCULA los hashes. NUNCA lanza.

    {"ok", "checked", "mismatches": [{"path","reason"}], "missing": [...], "extra": [...]}
    reason en ("hash_mismatch", "size_mismatch").
    "extra" = archivos presentes que no estan en el manifiesto (informativo, no falla).
    ok=True solo si mismatches y missing estan vacios.
    """
    out = {"ok": False, "checked": 0, "mismatches": [], "missing": [], "extra": []}
    try:
        base = Path(run_dir)
        mpath = base / _MANIFEST_NAME
        if not mpath.is_file():
            out["error"] = "manifest_missing"
            return out
        manifest = json.loads(mpath.read_text(encoding="utf-8")) or {}
        listed = {f.get("path"): f for f in (manifest.get("files") or [])
                  if isinstance(f, dict) and f.get("path")}

        for rel, entry in listed.items():
            p = base / rel
            if not p.is_file():
                out["missing"].append(rel)
                continue
            out["checked"] += 1
            try:
                if p.stat().st_size != entry.get("bytes"):
                    out["mismatches"].append({"path": rel, "reason": "size_mismatch"})
                    continue
                if _sha256_of(p) != entry.get("sha256"):
                    out["mismatches"].append({"path": rel, "reason": "hash_mismatch"})
            except Exception:  # noqa: BLE001
                out["mismatches"].append({"path": rel, "reason": "hash_mismatch"})

        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base)).replace("\\", "/")
            if rel == _MANIFEST_NAME or rel in listed:
                continue
            out["extra"].append(rel)

        out["ok"] = not out["mismatches"] and not out["missing"]
        return out
    except Exception as exc:  # noqa: BLE001 — NUNCA lanza
        out["error"] = f"{type(exc).__name__}: {exc}"[:250]
        return out
