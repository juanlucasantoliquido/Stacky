"""Plan 128 — Tablero de evolución de planes (servicio, solo lectura).

F1: escanea `docs/`, parsea encabezados **Estado:**, mergea el ledger de
supervisión y arma el board como dict puro (sin git, sin Flask, sin cache).
F2 agrega el enriquecimiento git read-only (`collect_unpushed_docs`).
F3 agrega el cache TTL + orquestación (`get_board_cached`, `get_detail`).

PURO en F1/F2: no toca Flask. El único subprocess de todo el módulo es el
`git log` read-only de `collect_unpushed_docs` (F2).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# ── §4.1 — Regex y normalización (LITERALES) ────────────────────────────────
_PLAN_FILE_RE = re.compile(r"^(\d{2,3})_PLAN_(.+)\.md$")      # solo planes
_SEQ_PREFIX_RE = re.compile(r"^(\d{2,3})_")                    # secuencia compartida
_ESTADO_RE = re.compile(r"^\s*(?:>\s*)?\*\*Estado:\*\*\s*(.+?)\s*$", re.MULTILINE)
_VEREDICTO_RE = re.compile(r"APROBADO-CON-CAMBIOS|RECHAZADO|APROBADO")
_VERSION_RE = re.compile(r"\bv(\d+(?:\.\d+)*)", re.IGNORECASE)
_FECHA_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")

_HEADER_READ_CHARS = 4000
_MAX_FILE_BYTES = 2_000_000          # archivos más grandes se saltean (defensa; ver R1 §6 doc)

_LEDGER_OK_VEREDICTOS = ("APROBADO", "TERMINADO-POR-SUPERVISOR")


def normalize_estado(raw: str | None) -> str:
    """Devuelve UNO de: PROPUESTO | CRITICADO | IMPLEMENTADO | IMPLEMENTADO_PARCIAL | SIN_ESTADO."""
    if not raw:
        return "SIN_ESTADO"
    u = raw.upper()
    if "IMPLEMENTADO-PARCIAL" in u:          # antes que startswith IMPLEMENTADO
        return "IMPLEMENTADO_PARCIAL"
    if u.startswith("IMPLEMENTADO"):
        return "IMPLEMENTADO"
    if u.startswith("CRITICADO"):
        return "CRITICADO"
    if u.startswith(("PROPUESTO", "PROPUESTA")):
        return "PROPUESTO"
    return "SIN_ESTADO"


def parse_plan_header(text: str) -> dict:
    """text = primeros _HEADER_READ_CHARS chars (o menos). Claves SIEMPRE presentes."""
    title = None
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    m = _ESTADO_RE.search(text)
    estado_raw = m.group(1).strip() if m else None
    estado = normalize_estado(estado_raw)

    veredicto = version = fecha = None
    if estado_raw:
        vm = _VEREDICTO_RE.search(estado_raw)
        veredicto = vm.group(0) if vm else None
        verm = _VERSION_RE.search(estado_raw)
        version = verm.group(1) if verm else None
        fm = _FECHA_RE.search(estado_raw)
        fecha = fm.group(0) if fm else None

    return {
        "title": title,
        "estado_raw": estado_raw,
        "estado": estado,
        "veredicto": veredicto,
        "version": version,
        "fecha": fecha,
    }


def scan_plan_files(docs_dir: Path) -> list[dict]:
    """iterdir() NO recursivo, solo archivos NN_PLAN_*.md <= _MAX_FILE_BYTES."""
    if not docs_dir.exists():
        return []
    results: list[dict] = []
    for entry in sorted(docs_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        m = _PLAN_FILE_RE.match(entry.name)
        if not m:
            continue
        try:
            if entry.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        try:
            full_text = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        header = parse_plan_header(full_text[:_HEADER_READ_CHARS])
        if not header["title"]:
            header["title"] = entry.stem
        results.append(
            {
                "number": int(m.group(1)),
                "number_str": m.group(1),
                "slug": m.group(2),
                "filename": entry.name,
                "path": entry,
                **header,
            }
        )
    return results


def next_free_number(docs_dir: Path) -> int:
    """max de int(m.group(1)) sobre TODOS los archivos NN_ (planes+checklists+incidentes) + 1."""
    if not docs_dir.exists():
        return 1
    max_n = 0
    for entry in docs_dir.iterdir():
        if not entry.is_file():
            continue
        m = _SEQ_PREFIX_RE.match(entry.name)
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return max_n + 1


def load_ledger(docs_dir: Path) -> dict:
    """§4.2. Devuelve el dict "planes" (o {} ante cualquier problema)."""
    path = docs_dir / "_supervision" / "ledger.json"
    try:
        raw_bytes = path.read_bytes()
    except OSError:
        return {}
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw_bytes.decode("utf-16")
        except UnicodeDecodeError:
            return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    planes = data.get("planes")
    return planes if isinstance(planes, dict) else {}


def ledger_info_for(number: int, path: Path, ledger: dict) -> dict | None:
    """entry = ledger.get(str(number)); None si no hay."""
    entry = ledger.get(str(number))
    if not entry:
        return None
    doc_sha256 = entry.get("doc_sha256")
    doc_drift: bool | None
    if doc_sha256:
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            doc_drift = actual != str(doc_sha256).lower()
        except OSError:
            doc_drift = None
    else:
        doc_drift = None
    return {
        "veredicto": entry.get("veredicto"),
        "fecha": entry.get("fecha"),
        "doc_drift": doc_drift,
    }


def suggest_next_action(
    estado: str, ledger_info: dict | None, unpushed: bool | None, number_str: str
) -> dict:
    """Tabla §4.3 LITERAL. Devuelve {"kind","label","command","natural_language"}."""
    ledger_ok = bool(ledger_info) and ledger_info.get("veredicto") in _LEDGER_OK_VEREDICTOS
    doc_drift = ledger_info.get("doc_drift") if ledger_info else None

    if ledger_ok and doc_drift is not True and unpushed is True:
        return {
            "kind": "push",
            "label": "Push pendiente",
            "command": "git push",
            "natural_language": (
                f"El plan {number_str} está aprobado pero sus commits siguen sin pushear: "
                "corré git push manualmente cuando quieras publicarlos."
            ),
        }
    if ledger_ok and doc_drift is not True:
        return {
            "kind": "ok",
            "label": "Al día",
            "command": None,
            "natural_language": f"Plan {number_str} al día: implementado, supervisado y aprobado.",
        }
    if ledger_info is not None and doc_drift is True:
        return {
            "kind": "supervisar",
            "label": "Re-supervisar (drift)",
            "command": f"/supervisar-implementaciones-planes {number_str}",
            "natural_language": (
                f"El doc del plan {number_str} cambió después de la aprobación del supervisor: "
                f"pedile al agente re-supervisar el plan {number_str}."
            ),
        }
    if estado == "PROPUESTO":
        return {
            "kind": "criticar",
            "label": "Criticar plan",
            "command": f"/criticar-y-mejorar-plan {number_str}",
            "natural_language": (
                f"Pedile al agente criticar y mejorar el plan {number_str} con el juez "
                "adversarial antes de implementarlo."
            ),
        }
    if estado == "CRITICADO":
        return {
            "kind": "implementar",
            "label": "Implementar plan",
            "command": f"/implementar-plan-stacky {number_str}",
            "natural_language": (
                f"Pedile al agente implementar el plan {number_str} fase por fase con TDD, "
                "sin falsos verdes."
            ),
        }
    if estado in ("IMPLEMENTADO", "IMPLEMENTADO_PARCIAL"):
        return {
            "kind": "supervisar",
            "label": "Supervisar",
            "command": f"/supervisar-implementaciones-planes {number_str}",
            "natural_language": (
                f"Pedile al agente supervisar la implementación del plan {number_str} contra "
                "su documento y cerrar lo que falte."
            ),
        }
    return {
        "kind": "revisar",
        "label": "Sin estado",
        "command": None,
        "natural_language": (
            f"El doc del plan {number_str} no tiene línea **Estado:** — agregásela para que "
            "el tablero lo clasifique."
        ),
    }


def build_board(
    docs_dir: Path, unpushed_paths: set[str] | None, repo_rel_prefix: str = "Stacky Agents/docs"
) -> dict:
    """Ensambla el contrato §4.4 COMPLETO menos "ok"/"git_available" (los pone la API)."""
    cards_raw = scan_plan_files(docs_dir)
    ledger = load_ledger(docs_dir)

    number_counts: dict[int, int] = {}
    for c in cards_raw:
        number_counts[c["number"]] = number_counts.get(c["number"], 0) + 1

    plans: list[dict] = []
    totals: dict[str, int] = {}
    unpushed_count = 0

    for c in cards_raw:
        path_rel = f"{repo_rel_prefix}/{c['filename']}"
        unpushed = None if unpushed_paths is None else (path_rel in unpushed_paths)

        ledger_info = ledger_info_for(c["number"], c["path"], ledger)
        ledger_ok = bool(ledger_info) and ledger_info.get("veredicto") in _LEDGER_OK_VEREDICTOS
        doc_drift = ledger_info.get("doc_drift") if ledger_info else None
        estado_efectivo = "APROBADO" if (ledger_ok and doc_drift is not True) else c["estado"]

        action = suggest_next_action(c["estado"], ledger_info, unpushed, c["number_str"])

        card = {
            "number": c["number"],
            "number_str": c["number_str"],
            "slug": c["slug"],
            "filename": c["filename"],
            "path_rel": path_rel,
            "title": c["title"],
            "estado": c["estado"],
            "estado_raw": c["estado_raw"],
            "estado_efectivo": estado_efectivo,
            "veredicto": c["veredicto"],
            "version": c["version"],
            "fecha": c["fecha"],
            "duplicate": number_counts[c["number"]] > 1,
            "ledger": ledger_info,
            "unpushed": unpushed,
            "suggested_action": action,
        }
        plans.append(card)
        totals[estado_efectivo] = totals.get(estado_efectivo, 0) + 1
        if unpushed is True:
            unpushed_count += 1

    plans.sort(key=lambda c: (-c["number"], c["filename"]))

    totals["unpushed"] = unpushed_count
    totals["duplicados"] = sum(1 for cnt in number_counts.values() if cnt > 1)
    totals["total"] = len(plans)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "docs_dir_found": docs_dir.exists(),
        "next_free_number": next_free_number(docs_dir),
        "totals": totals,
        "plans": plans,
    }


# ── F2 — Enriquecimiento git de solo lectura ────────────────────────────────
_GIT_TIMEOUT_SEC = 5


def repo_root() -> Path | None:
    """services -> backend -> "Stacky Agents" -> raíz repo. None si no hay .git (deploy congelado)."""
    root = Path(__file__).resolve().parents[3]
    if not (root / ".git").exists():
        return None
    return root


def docs_dir_default() -> Path:
    """"Stacky Agents"/docs — services -> backend -> "Stacky Agents"/docs."""
    return Path(__file__).resolve().parents[2] / "docs"


def collect_unpushed_docs(root: Path | None) -> set[str] | None:
    """UNA llamada git de solo lectura. None ante CUALQUIER problema (nunca rompe)."""
    if root is None:
        return None
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--name-only",
                "--pretty=format:",
                "origin/main..HEAD",
                "--",
                "Stacky Agents/docs",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    paths: set[str] = set()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('"') and line.endswith('"') and len(line) >= 2:
            line = line[1:-1]
        paths.add(line)
    return paths


# ── F3 — Cache TTL + orquestación (consumido por api/plans_board.py) ───────
_BOARD_TTL_SEC = 15
_BOARD_CACHE: tuple[float, dict] | None = None


def get_board_cached(refresh: bool = False) -> dict:
    """Board completo con cache TTL de 15s. Nunca lanza (build_board ya es defensivo)."""
    global _BOARD_CACHE
    if not refresh and _BOARD_CACHE is not None:
        ts, board = _BOARD_CACHE
        if time.monotonic() - ts < _BOARD_TTL_SEC:
            return dict(board)

    root = repo_root()
    unpushed = collect_unpushed_docs(root)
    board = build_board(docs_dir_default(), unpushed)
    board["ok"] = True
    board["git_available"] = unpushed is not None
    _BOARD_CACHE = (time.monotonic(), board)
    return dict(board)


def get_detail(number: int) -> dict | None:
    """Sobre get_board_cached(): cards con ese number. [] -> None."""
    board = get_board_cached()
    matches = [c for c in board["plans"] if c["number"] == number]
    if not matches:
        return None
    plan = matches[0]
    duplicates = matches[1:]
    docs_dir = docs_dir_default()
    file_path = docs_dir / plan["filename"]
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        head_excerpt = "\n".join(content.splitlines()[:60])
    except OSError:
        head_excerpt = ""
    return {
        "ok": True,
        "plan": plan,
        "duplicates": duplicates,
        "head_excerpt": head_excerpt,
    }
