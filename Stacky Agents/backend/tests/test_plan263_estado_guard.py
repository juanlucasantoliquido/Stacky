"""Plan 263 F2 — ratchet: ningún plan nuevo nace sin **Estado:**.

NADA de la regla se reimplementa acá. Se importan de services.plans_board las
TRES piezas que definen "esto es un plan y tiene estado":
  _ESTADO_RE          -> qué línea cuenta como estado
  _HEADER_READ_CHARS  -> cuánto encabezado se lee (CARACTERES, no bytes)
  _PLAN_FILE_RE       -> qué archivo es un plan            (v3/C6)
Ver ADICIÓN ARQUITECTO 3 (test_regla_unica_de_estado) y
ADICIÓN ARQUITECTO 5 (test_regla_de_archivo_unica).
"""
import json
import pathlib
import sys

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services.plans_board import (  # noqa: E402
    _ESTADO_RE,
    _HEADER_READ_CHARS,
    _PLAN_FILE_RE,
    parse_plan_header,
)

DOCS_DIR = _BACKEND.parent / "docs"
BASELINE_PATH = _BACKEND / "tests" / "plans_estado_baseline.json"


def _texto_encabezado(path: pathlib.Path) -> str:
    """MISMA lectura que services.plans_board._read_header_cached (:126-140):
    modo texto UTF-8 y N CARACTERES (no bytes)."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return fh.read(_HEADER_READ_CHARS)


def tiene_estado(path: pathlib.Path) -> bool:
    return bool(_ESTADO_RE.search(_texto_encabezado(path)))


def planes_sin_estado(docs_dir: pathlib.Path) -> list[str]:
    return sorted(
        p.name for p in docs_dir.iterdir()
        if p.is_file() and _PLAN_FILE_RE.match(p.name) and not tiene_estado(p)
    )


def _cargar_baseline() -> list[str]:
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return data["sin_estado"]


# ── Test 1 ───────────────────────────────────────────────────────────────────

def test_baseline_existe_y_es_json():
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert isinstance(data["sin_estado"], list)
    assert all(isinstance(x, str) for x in data["sin_estado"])


# ── Test 2 — el ratchet: ningún plan nuevo sin **Estado:** ──────────────────

def test_ningun_plan_nuevo_sin_estado():
    baseline = set(_cargar_baseline())
    actuales = set(planes_sin_estado(DOCS_DIR))
    nuevos = actuales - baseline
    assert nuevos == set(), (
        f"El plan {sorted(nuevos)} no declara **Estado:**. Agregale la linea o "
        "corré la normalización del Plan 263."
    )


# ── Test 3 — el baseline solo puede achicarse ───────────────────────────────

def test_el_ratchet_solo_se_achica():
    baseline = set(_cargar_baseline())
    actuales = set(planes_sin_estado(DOCS_DIR))
    stale = baseline - actuales
    assert stale == set(), (
        f"El baseline quedó stale: sacá {sorted(stale)} de plans_estado_baseline.json "
        "(o dejá que la normalización del Plan 263 lo pode sola)."
    )


# ── Test 4 — sin duplicados ──────────────────────────────────────────────────

def test_baseline_sin_duplicados():
    sin_estado = _cargar_baseline()
    assert len(sin_estado) == len(set(sin_estado))


# ── Test 5 [ADICIÓN ARQUITECTO 3] — fuente única de la regla, borde multibyte ─

def test_regla_unica_de_estado(tmp_path):
    p = tmp_path / "263_PLAN_MULTIBYTE.md"
    p.write_text("# t\n" + "á" * 3900 + "\n**Estado:** PROPUESTO v1\n", encoding="utf-8")

    assert tiene_estado(p) is True
    assert parse_plan_header(_texto_encabezado(p))["estado"] == "PROPUESTO"
    # El equivalente por BYTES no lo ve: "á" son 2 bytes en UTF-8, así que la
    # línea cae dentro de los 4000 CARACTERES pero fuera de los 4000 BYTES.
    # Si alguien "optimiza" el ratchet a shell (head -c), reintroduce ese bug.
    assert _ESTADO_RE.search(p.read_bytes()[:4000].decode("utf-8", "replace")) is None


# ── Test 6 — el baseline solo contiene nombres de plan válidos ───────────────

def test_baseline_solo_nombres_de_plan():
    for nombre in _cargar_baseline():
        assert _PLAN_FILE_RE.match(nombre), f"{nombre} no matchea _PLAN_FILE_RE"
        assert ".." not in nombre and "/" not in nombre and "\\" not in nombre


# ── Test 7 [ADICIÓN ARQUITECTO 5] — misma regex de archivo que el tablero ────

def test_regla_de_archivo_unica():
    from services import plans_board

    assert _PLAN_FILE_RE is plans_board._PLAN_FILE_RE  # identidad de objeto, no ==

    universo_ratchet = {
        p.name for p in DOCS_DIR.iterdir() if p.is_file() and _PLAN_FILE_RE.match(p.name)
    }
    universo_tablero = {
        c["filename"] for c in plans_board.scan_plan_files_with_census(DOCS_DIR)[0]
    }
    assert universo_ratchet == universo_tablero
