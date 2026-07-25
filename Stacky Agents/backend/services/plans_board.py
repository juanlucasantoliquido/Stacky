"""Plan 128 — Tablero de evolución de planes (servicio, solo lectura).

F1: escanea `docs/`, parsea encabezados **Estado:**, mergea el ledger de
supervisión y arma el board como dict puro (sin git, sin Flask, sin cache).
F2 agrega el enriquecimiento git read-only (`collect_unpushed_docs`).
F3 agrega el cache TTL + orquestación (`get_board_cached`, `get_detail`).

PURO en F1/F2: no toca Flask. El único subprocess de todo el módulo es el
`git log` read-only de `collect_unpushed_docs` (F2).
"""
from __future__ import annotations

import copy
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
_MAX_PLAN_FILES = 500          # Plan 237: cota de I/O. Más allá de esto se cuenta y no se parsea.

_LEDGER_OK_VEREDICTOS = ("APROBADO", "TERMINADO-POR-SUPERVISOR")

# ── Plan 237 — Triage: el ORDEN de esta tupla ES el orden de presentación. ──
# Responde, de arriba a abajo: qué NO está implementado, qué NO está criticado,
# qué ni siquiera tiene documento, qué falta cerrar, y qué ya está completo.
TRIAGE_BUCKETS: tuple[tuple[str, str], ...] = (
    ("SIN_IMPLEMENTAR", "Sin implementar"),      # pasó el juez (o quedó a medias): toca construir
    ("SIN_CRITICAR",    "Sin criticar"),         # escrito pero sin juez adversarial
    ("SIN_DOCUMENTO",   "Sin documento"),        # catalogado en un roadmap, todavía sin .md (F3)
    ("SIN_SUPERVISAR",  "Sin supervisar"),       # construido, falta el cierre del supervisor
    ("COMPLETADO",      "Completado"),           # ledger APROBADO y sin drift del doc
)
_TRIAGE_RANK: dict[str, int] = {key: i for i, (key, _label) in enumerate(TRIAGE_BUCKETS)}

# estado_efectivo -> bucket. COBERTURA COMPLETA: normalize_estado (:35-49) devuelve
# exactamente PROPUESTO/CRITICADO/IMPLEMENTADO/IMPLEMENTADO_PARCIAL/SIN_ESTADO, y
# build_board (:277) puede sustituirlo por "APROBADO". No hay un sexto valor posible.
# Un estado desconocido cae en SIN_CRITICAR (se prefiere pedir revisión humana antes
# que esconder un plan al fondo).
_ESTADO_A_BUCKET: dict[str, str] = {
    "CRITICADO":            "SIN_IMPLEMENTAR",
    "IMPLEMENTADO_PARCIAL": "SIN_IMPLEMENTAR",
    "PROPUESTO":            "SIN_CRITICAR",
    "SIN_ESTADO":           "SIN_CRITICAR",
    "IMPLEMENTADO":         "SIN_SUPERVISAR",
    "APROBADO":             "COMPLETADO",
}


def triage_bucket(estado_efectivo: str) -> str:
    """Bucket de triage de un plan CON documento. Nunca lanza."""
    return _ESTADO_A_BUCKET.get(estado_efectivo or "", "SIN_CRITICAR")


def triage_rank(bucket: str) -> int:
    """Posición del bucket. Un bucket desconocido va al final (nunca oculto)."""
    return _TRIAGE_RANK.get(bucket, len(TRIAGE_BUCKETS))


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


# Plan 237 — memo de encabezados: clave = (str(path), mtime_ns, size) -> dict header.
# Un archivo que no cambió NO se vuelve a leer ni a parsear. Cota: se limpia si supera
# 4 * _MAX_PLAN_FILES entradas (evita crecer sin techo en procesos largos).
_HEADER_MEMO: dict[tuple[str, int, int], dict] = {}


def _read_header_cached(entry: Path, size: int) -> dict | None:
    """Encabezado parseado de `entry`, leyendo COMO MUCHO _HEADER_READ_CHARS bytes.

    Devuelve None si el archivo no se pudo leer (el llamador lo cuenta como ilegible).
    """
    try:
        key = (str(entry), entry.stat().st_mtime_ns, size)
    except OSError:
        return None
    hit = _HEADER_MEMO.get(key)
    if hit is not None:
        return dict(hit)
    try:
        with entry.open("r", encoding="utf-8", errors="replace") as fh:
            texto = fh.read(_HEADER_READ_CHARS)
    except OSError:
        return None
    header = parse_plan_header(texto)
    if not header["title"]:
        header["title"] = entry.stem
    if len(_HEADER_MEMO) > 4 * _MAX_PLAN_FILES:
        _HEADER_MEMO.clear()
    _HEADER_MEMO[key] = dict(header)
    return header


def scan_plan_files_with_census(docs_dir: Path) -> tuple[list[dict], dict]:
    """Igual que scan_plan_files, pero devolviendo (planes, censo).

    census = {
      "files_seen": int,            # entradas de archivo en el directorio raíz
      "plans_parsed": int,          # NN_PLAN_*.md efectivamente parseados
      "skipped_not_a_plan": int,    # NN_ que no son _PLAN_, y todo lo demás
      "skipped_oversize": int,      # > _MAX_FILE_BYTES
      "skipped_unreadable": int,    # OSError al leer o al stat
      "skipped_over_cap": int,      # planes más allá de _MAX_PLAN_FILES (cota de I/O)
      "skipped_subdirs": int,       # planes NN_PLAN_*.md en subdirectorios (p.ej. _legacy/)
      "subdir_examples": list[str], # hasta 5 rutas relativas, para que el operador sepa cuáles
    }
    NUNCA lanza: cualquier problema suma a un contador.
    Invariante testeada: plans_parsed + skipped_not_a_plan + skipped_oversize
                       + skipped_unreadable + skipped_over_cap == files_seen
    """
    census: dict = {
        "files_seen": 0,
        "plans_parsed": 0,
        "skipped_not_a_plan": 0,
        "skipped_oversize": 0,
        "skipped_unreadable": 0,
        "skipped_over_cap": 0,
        "skipped_subdirs": 0,
        "subdir_examples": [],
    }
    if not docs_dir.exists():
        return [], census

    results: list[dict] = []
    for entry in sorted(docs_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            # subdirectorio: contar los planes que quedan afuera, SIN parsearlos
            try:
                hijos = sorted(entry.glob("*_PLAN_*.md"))
            except OSError:
                hijos = []
            census["skipped_subdirs"] += len(hijos)
            faltan = 5 - len(census["subdir_examples"])
            for h in hijos[:max(0, faltan)]:
                census["subdir_examples"].append(f"{entry.name}/{h.name}")
            continue

        census["files_seen"] += 1
        m = _PLAN_FILE_RE.match(entry.name)
        if not m:
            census["skipped_not_a_plan"] += 1
            continue
        try:
            size = entry.stat().st_size
        except OSError:
            census["skipped_unreadable"] += 1
            continue
        if size > _MAX_FILE_BYTES:
            census["skipped_oversize"] += 1
            continue
        if len(results) >= _MAX_PLAN_FILES:
            census["skipped_over_cap"] += 1
            continue
        header = _read_header_cached(entry, size)
        if header is None:
            census["skipped_unreadable"] += 1
            continue
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
        census["plans_parsed"] += 1
    return results, census


def scan_plan_files(docs_dir: Path) -> list[dict]:      # firma INTACTA (G4)
    """iterdir() NO recursivo, solo archivos NN_PLAN_*.md <= _MAX_FILE_BYTES."""
    return scan_plan_files_with_census(docs_dir)[0]


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


_ROADMAP_DIRNAME = "_roadmap"


def load_roadmap_entries(docs_dir: Path) -> list[dict]:
    """Lee docs/_roadmap/*.json y devuelve las entradas de plan catalogadas.

    Formato aceptado (el del Plan 218 F7): dict con "subplans": [ {..}, .. ],
    donde cada entrada tiene al menos "number" (int). "title", "slug",
    "priority" y "milestone" son opcionales.
    Devuelve [] ante CUALQUIER problema (no existe, no es JSON, es otra forma).
    Cada entrada devuelta: {"number", "title", "slug", "priority", "milestone", "source"}.
    """
    root = docs_dir / _ROADMAP_DIRNAME
    if not root.exists() or not root.is_dir():
        return []
    out: list[dict] = []
    vistos: set[int] = set()
    try:
        archivos = sorted(root.glob("*.json"))
    except OSError:
        return []
    for f in archivos:
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue                                  # nunca lanza
        if not isinstance(data, dict):
            continue
        subplans = data.get("subplans")
        if not isinstance(subplans, list):
            continue
        for e in subplans:
            if not isinstance(e, dict):
                continue
            n = e.get("number")
            if not isinstance(n, int) or isinstance(n, bool):
                continue
            if n in vistos:
                continue                              # primer roadmap gana
            vistos.add(n)
            out.append({
                "number": n,
                "title": str(e.get("title") or f"Plan {n}"),
                "slug": str(e.get("slug") or ""),
                "priority": e.get("priority"),
                "milestone": e.get("milestone"),
                "source": f.name,
            })
    return sorted(out, key=lambda e: e["number"])


def reserved_numbers(docs_dir: Path) -> set[int]:
    """Números comprometidos por algún roadmap (tengan o no documento)."""
    return {e["number"] for e in load_roadmap_entries(docs_dir)}


def all_claimed_numbers(docs_dir: Path) -> dict[str, set[int]]:
    """Números comprometidos, por fuente. NUNCA lanza.

    - "root":    prefijo NN_ de archivos del directorio raíz (planes, checklists, incidentes)
    - "subdirs": prefijo NN_ de archivos de subdirectorios de PRIMER nivel (_legacy/, etc.)
    - "roadmap": reserved_numbers(docs_dir)
    - "ledger":  claves numéricas de docs/_supervision/ledger.json (load_ledger)
    """
    fuentes: dict[str, set[int]] = {
        "root": set(), "subdirs": set(), "roadmap": set(), "ledger": set(),
    }
    if not docs_dir.exists():
        return fuentes
    try:
        entradas = list(docs_dir.iterdir())
    except OSError:
        entradas = []
    for entry in entradas:
        if entry.is_file():
            m = _SEQ_PREFIX_RE.match(entry.name)
            if m:
                fuentes["root"].add(int(m.group(1)))
        else:
            try:
                hijos = list(entry.iterdir())
            except OSError:
                hijos = []
            for h in hijos:
                if h.is_file():
                    m = _SEQ_PREFIX_RE.match(h.name)
                    if m:
                        fuentes["subdirs"].add(int(m.group(1)))
    fuentes["roadmap"] = reserved_numbers(docs_dir)
    for k in load_ledger(docs_dir):        # las claves del ledger son "NN" o "NN_slug"
        m = re.match(r"^(\d{2,3})", str(k))
        if m:
            fuentes["ledger"].add(int(m.group(1)))
    return fuentes


def next_free_number_effective(docs_dir: Path) -> int:
    """Primer número > max(TODAS las fuentes) que no esté comprometido en ninguna.
    Sin docs/_roadmap/ ni subdirectorios devuelve lo mismo que next_free_number."""
    fuentes = all_claimed_numbers(docs_dir)
    tomados: set[int] = set().union(*fuentes.values()) or {0}
    n = max(tomados) + 1
    while n in tomados:
        n += 1
    return n


def plan_number_duplicates(docs_dir: Path) -> list[dict]:
    """[{"number": int, "filenames": [str, ...]}] para todo NN con >1 documento en el raíz.
    Ordenado por number. Lista vacía = todo sano."""
    por_numero: dict[int, list[str]] = {}
    if not docs_dir.exists():
        return []
    try:
        entradas = sorted(docs_dir.iterdir(), key=lambda p: p.name)
    except OSError:
        return []
    for entry in entradas:
        if not entry.is_file():
            continue
        m = _PLAN_FILE_RE.match(entry.name)
        if not m:
            continue
        por_numero.setdefault(int(m.group(1)), []).append(entry.name)
    return [
        {"number": n, "filenames": sorted(nombres)}
        for n, nombres in sorted(por_numero.items())
        if len(nombres) > 1
    ]


def claim_plan_path(docs_dir: Path, number: int, filename: str) -> Path:
    """Crea el archivo del plan de forma ATÓMICA y devuelve su ruta.

    Usa creación EXCLUSIVA (open(..., "x")): si otra sesión ganó la carrera entre el
    cálculo del número y la escritura, esto levanta FileExistsError en vez de pisar.
    NO tiene endpoint HTTP: es una utilidad importable por la skill que ya escribía el
    archivo. No agrega autonomía: hace atómica una escritura que ya existía (G2).
    """
    docs_dir.mkdir(parents=True, exist_ok=True)
    destino = docs_dir / filename
    with destino.open("x", encoding="utf-8") as fh:   # falla si ya existe
        fh.write(f"# Plan {number} — (borrador)\n\n**Estado:** PROPUESTO v1\n")
    return destino


def build_planned_cards(docs_dir: Path, numeros_con_doc: set[int]) -> list[dict]:
    """Cards del bucket SIN_DOCUMENTO: catalogados en un roadmap y sin .md.
    Mismas claves que un card normal (para que la UI no discrimine)."""
    cards: list[dict] = []
    for e in load_roadmap_entries(docs_dir):
        if e["number"] in numeros_con_doc:
            continue
        ns = f"{e['number']:02d}"
        cards.append({
            "number": e["number"], "number_str": ns, "slug": e["slug"],
            "filename": None, "path_rel": f"docs/_roadmap/{e['source']}",
            "title": e["title"], "estado": "SIN_DOCUMENTO", "estado_raw": None,
            "estado_efectivo": "SIN_DOCUMENTO", "triage_bucket": "SIN_DOCUMENTO",
            "veredicto": None, "version": None, "fecha": None, "duplicate": False,
            "ledger": None, "unpushed": None,
            "priority": e["priority"], "milestone": e["milestone"],
            "suggested_action": {
                "kind": "proponer",
                "label": "Escribir el plan",
                "command": f"/proponer-plan-stacky {e['title']}",
                "natural_language": (f"El plan {ns} está comprometido en el roadmap "
                                     f"({e['source']}) pero todavía no tiene documento: "
                                     f"pedile al agente proponer el plan {ns} — {e['title']}."),
            },
        })
    return cards


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
    cards_raw, census = scan_plan_files_with_census(docs_dir)
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
            "triage_bucket": triage_bucket(estado_efectivo),
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

    # Plan 237 F3 — planes comprometidos en un roadmap que todavía no tienen .md.
    # `numeros_con_doc` se calcula sobre cards_raw (planes parseados), no sobre
    # `plans`, para no auto-excluir las cards que se están agregando.
    numeros_con_doc = {c["number"] for c in cards_raw}
    planned = build_planned_cards(docs_dir, numeros_con_doc)
    for card in planned:
        plans.append(card)
        totals["SIN_DOCUMENTO"] = totals.get("SIN_DOCUMENTO", 0) + 1

    # Plan 237: primero el triage, y DENTRO de cada bucket el número descendente
    # (lo más nuevo primero), con el filename como desempate estable.
    # `filename` puede ser None en las cards SIN_DOCUMENTO (F3) -> se normaliza a "".
    plans.sort(key=lambda c: (triage_rank(c["triage_bucket"]), -c["number"], c["filename"] or ""))

    totals["unpushed"] = unpushed_count
    totals["duplicados"] = sum(1 for cnt in number_counts.values() if cnt > 1)
    totals["total"] = len(plans)

    triage_totals = {key: 0 for key, _ in TRIAGE_BUCKETS}
    for card in plans:
        triage_totals[card["triage_bucket"]] = triage_totals.get(card["triage_bucket"], 0) + 1

    # Plan 237 F7 — guardia de numeración: universo completo + duplicados ruidosos.
    fuentes = all_claimed_numbers(docs_dir)
    todos_los_tomados: set[int] = set().union(*fuentes.values())

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "docs_dir_found": docs_dir.exists(),
        "next_free_number": next_free_number_effective(docs_dir),
        "next_free_number_raw": next_free_number(docs_dir),
        "reserved_count": len(reserved_numbers(docs_dir)),
        "census": census,
        "totals": totals,
        "triage_order": [key for key, _ in TRIAGE_BUCKETS],
        "triage_totals": triage_totals,
        "numbering": {
            "max_number": max(todos_los_tomados, default=0),
            "next_free_number": next_free_number_effective(docs_dir),
            "next_free_number_raw": next_free_number(docs_dir),
            "reserved_count": len(reserved_numbers(docs_dir)),
            "duplicates": plan_number_duplicates(docs_dir),
        },
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
_BOARD_MIN_REFRESH_SEC = 2.0   # Plan 237: ?refresh=1 no puede forzar rebuilds en ráfaga.
_BOARD_CACHE: tuple[float, dict] | None = None


def get_board_cached(refresh: bool = False) -> dict:
    """Board completo con cache TTL de 15s. Nunca lanza (build_board ya es defensivo).

    Plan 237 (C12): devuelve una copia PROFUNDA. Con `dict(board)` las dos
    superficies (tab "Planes" y Centro de Evolución) compartían `census`,
    `totals`, `triage_totals` y `plans`, así que una mutación de un consumidor
    envenenaba el cache del otro.
    """
    global _BOARD_CACHE
    if _BOARD_CACHE is not None:
        ts, board = _BOARD_CACHE
        edad = time.monotonic() - ts
        # Piso anti-abuso: el botón "Refrescar" no puede martillar el disco.
        if edad < (_BOARD_MIN_REFRESH_SEC if refresh else _BOARD_TTL_SEC):
            return copy.deepcopy(board)

    root = repo_root()
    unpushed = collect_unpushed_docs(root)
    board = build_board(docs_dir_default(), unpushed)
    board["ok"] = True
    board["git_available"] = unpushed is not None
    _BOARD_CACHE = (time.monotonic(), board)
    return copy.deepcopy(board)


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
