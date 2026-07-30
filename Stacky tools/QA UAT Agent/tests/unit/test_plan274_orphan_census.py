"""
test_plan274_orphan_census.py — Plan 274 F0.2.

Censo del corpus CERRADO de 11 modulos huerfanos (§2.3 / H1).

DOS METRICAS SEPARADAS, a proposito:
  * direct_importers(m)  -> importadores TEXTUALES (lo mismo que el comando C-4).
  * prod_reachable(m)    -> ¿algun importador es alcanzable desde
                            qa_uat_pipeline.py o desde un .spec.ts vivo?

Sin la segunda, un implementador cierra KPI-4a importando un huerfano DESDE OTRO
HUERFANO — que es exactamente el estado de `arrival_validator.ts` hoy: tiene 1
importador (`navigation_executor.ts:26`) y ese importador tambien es huerfano.

POR QUE EL CRITERIO NO ES "la lista esta vacia": un conteo agregado colapsa N
casos en 1 y no discrimina CUAL se conecto. Todo se assertea POR MODULO, con el
nombre en el mensaje de fallo.
"""
from __future__ import annotations

import re
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]

# ── Corpus CERRADO de 11 (tabla H1). Esta lista es NORMATIVA: ninguna fase la amplia.
ORPHAN_CORPUS: dict[str, int] = {
    "navigation_driver.py": 975,
    "playwright/helpers/navigation_executor.ts": 793,
    "playwright/instrumented_actions.ts": 601,
    "deeplink_readiness_checker.py": 435,
    "playwright/helpers/arrival_validator.ts": 372,
    "locator_quality.py": 294,
    "playbook_performance.py": 226,
    "test_data_cache.py": 219,
    "screenshot_budget.py": 208,
    "playwright/helpers/grid_precheck.ts": 172,
    "playwright/helpers/session_guard.ts": 167,
}

# Valores de ARRANQUE medidos el 2026-07-30 (comando C-4). Son constantes
# historicas: NO se editan cuando una fase conecta un modulo — para eso esta
# EXPECTED_CONNECTED.
ARRANQUE_DIRECT_CERO = 10          # 10 de 11; arrival_validator.ts ya tenia 1
ARRANQUE_NO_ALCANZABLE = 11        # los 11, sin excepcion
EL_UNICO_CON_IMPORTADOR = "playwright/helpers/arrival_validator.ts"

# Crece de a un modulo por fase (F2, F4, F5, F6, F7). Modulo -> fase que lo conecta.
# En F0 esta VACIO: los 11 son huerfanos. Cada fase agrega SU entrada al conectar.
EXPECTED_CONNECTED: dict[str, str] = {
    "screenshot_budget.py": "F2",
    "deeplink_readiness_checker.py": "F4",
    "locator_quality.py": "F5",
    "test_data_cache.py": "F6",
    "playbook_performance.py": "F7",
}

# Raices del camino de produccion.
PY_ROOT = "qa_uat_pipeline.py"
TS_ROOTS = (
    "playwright/uat/ado120_obligaciones.spec.ts",
    "playwright/uat/ado122_provincia_domicilio.spec.ts",
    "playwright/uat/ado171_emails_oficial.spec.ts",
    "playwright/uat/frm_detalle_clie.spec.ts",
    "playwright/smoke/compromiso_minimo.spec.ts",
    "playwright.config.ts",
    "playwright/global.setup.ts",
)

_EXCLUDE_PY = re.compile(r"__pycache__|[\\/]tests[\\/]|_attic|[\\/]evals[\\/]")


def _is_excluded_py(p: Path) -> bool:
    return bool(_EXCLUDE_PY.search(str(p)))


def _py_files() -> list[Path]:
    return [p for p in TOOL_ROOT.rglob("*.py") if not _is_excluded_py(p)]


def _ts_files() -> list[Path]:
    return [p for p in TOOL_ROOT.rglob("*.ts")
            if "node_modules" not in str(p) and "__tests__" not in str(p)]


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# ── Metrica 1: importadores directos (replica C-4) ───────────────────────────

def direct_importers(module: str) -> list[str]:
    """Importadores TEXTUALES del modulo. Mismo criterio que el comando C-4."""
    if module.endswith(".py"):
        stem = Path(module).stem
        rx = re.compile(rf"(^|\s)import\s+{re.escape(stem)}\b|from\s+{re.escape(stem)}\s+import")
        out = []
        for p in _py_files():
            if p.resolve() == (TOOL_ROOT / module).resolve():
                continue
            if rx.search(_read(p)):
                out.append(p.relative_to(TOOL_ROOT).as_posix())
        return sorted(out)

    stem = Path(module).stem
    rx = re.compile(rf"from\s+['\"][^'\"]*{re.escape(stem)}['\"]")
    out = []
    for p in _ts_files():
        if p.resolve() == (TOOL_ROOT / module).resolve():
            continue
        for line in _read(p).splitlines():
            if line.lstrip().startswith("*") or line.lstrip().startswith("//"):
                continue
            if rx.search(line):
                out.append(p.relative_to(TOOL_ROOT).as_posix())
                break
    return sorted(out)


# ── Metrica 2: alcance TRANSITIVO de produccion ──────────────────────────────

def _local_py_imports(text: str, known: set[str]) -> set[str]:
    found = set()
    for m in re.finditer(r"(?:^|\s)(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", text):
        name = m.group(1)
        if f"{name}.py" in known:
            found.add(f"{name}.py")
    return found


def _resolve_ts_import(origin: Path, spec: str) -> str | None:
    if not spec.startswith("."):
        return None
    cand = (origin.parent / spec).resolve()
    for suffix in (".ts", ".tsx", "/index.ts"):
        p = Path(str(cand) + suffix)
        if p.is_file():
            try:
                return p.relative_to(TOOL_ROOT).as_posix()
            except ValueError:
                return None
    return None


def production_reachable_set() -> set[str]:
    """BFS desde las raices de produccion (pipeline Python + specs vivos TS)."""
    known_py = {p.relative_to(TOOL_ROOT).as_posix() for p in _py_files()
                if p.parent == TOOL_ROOT}
    reachable: set[str] = set()

    # --- Python: raiz = qa_uat_pipeline.py
    frontier = [PY_ROOT]
    while frontier:
        cur = frontier.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        f = TOOL_ROOT / cur
        if not f.is_file():
            continue
        for dep in _local_py_imports(_read(f), known_py):
            if dep not in reachable:
                frontier.append(dep)

    # --- TypeScript: raices = specs vivos + config + global setup
    frontier = [r for r in TS_ROOTS if (TOOL_ROOT / r).is_file()]
    while frontier:
        cur = frontier.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        f = TOOL_ROOT / cur
        if not f.is_file():
            continue
        for m in re.finditer(r"from\s+['\"]([^'\"]+)['\"]", _read(f)):
            dep = _resolve_ts_import(f, m.group(1))
            if dep and dep not in reachable:
                frontier.append(dep)

    reachable.discard(PY_ROOT)
    for r in TS_ROOTS:
        reachable.discard(r)
    return reachable


def prod_reachable(module: str, _cache: dict = {}) -> bool:
    if "set" not in _cache:
        _cache["set"] = production_reachable_set()
    return module in _cache["set"]


# ── Tests ────────────────────────────────────────────────────────────────────

def test_corpus_es_exactamente_once():
    assert len(ORPHAN_CORPUS) == 11, (
        f"el corpus es CERRADO en 11 modulos; tiene {len(ORPHAN_CORPUS)}")
    assert sum(ORPHAN_CORPUS.values()) == 4462, (
        f"el corpus suma {sum(ORPHAN_CORPUS.values())} lineas; el `wc -l` "
        "verificado el 2026-07-30 daba 4462 exacto")
    faltan = [m for m in ORPHAN_CORPUS if not (TOOL_ROOT / m).is_file()]
    assert not faltan, f"modulos del corpus que ya no existen: {faltan}"


def test_censo_de_importadores():
    """Assert POR MODULO (nunca un agregado), con las dos metricas separadas."""
    fallas = []
    for m in ORPHAN_CORPUS:
        d = direct_importers(m)
        r = prod_reachable(m)
        fase = EXPECTED_CONNECTED.get(m)
        if fase:
            if not d:
                fallas.append(f"{m}: {fase} deberia haberlo conectado y tiene 0 importadores directos")
            elif not r:
                fallas.append(
                    f"{m}: tiene importadores {d} pero NINGUNO es alcanzable desde "
                    "produccion — conectar un huerfano a otro huerfano no lo conecta")
        else:
            if r:
                fallas.append(
                    f"{m}: aparecio alcanzable desde produccion sin fase que lo declare; "
                    "agregalo a EXPECTED_CONNECTED con su fase")
    assert not fallas, "censo por modulo:\n  - " + "\n  - ".join(fallas)


def test_arranque_directo_es_diez():
    """El arranque medido por C-4 fue 10 de 11, y el unico con importador
    era `playwright/helpers/arrival_validator.ts`. El invariante se mantiene
    a medida que las fases conectan: huerfanos_actuales + conectados == 10."""
    huerfanos = [m for m in ORPHAN_CORPUS if not direct_importers(m)]
    conectados = [m for m in EXPECTED_CONNECTED
                  if m != EL_UNICO_CON_IMPORTADOR and direct_importers(m)]
    total = len(huerfanos) + len(conectados)
    assert total == ARRANQUE_DIRECT_CERO, (
        f"la cuenta de arranque no cierra: {len(huerfanos)} huerfanos "
        f"({huerfanos}) + {len(conectados)} conectados ({conectados}) = {total}, "
        f"y el arranque medido por C-4 era {ARRANQUE_DIRECT_CERO}")
    assert EL_UNICO_CON_IMPORTADOR not in huerfanos, (
        f"{EL_UNICO_CON_IMPORTADOR} deberia seguir teniendo su importador "
        "textual (navigation_executor.ts:26), que a su vez es huerfano")


def test_arranque_alcanzable_es_once():
    """Los 11 arrancaron SIN alcance de produccion, sin excepcion."""
    sin_alcance = [m for m in ORPHAN_CORPUS if not prod_reachable(m)]
    conectados = [m for m in EXPECTED_CONNECTED if prod_reachable(m)]
    total = len(sin_alcance) + len(conectados)
    assert total == ARRANQUE_NO_ALCANZABLE, (
        f"la cuenta de arranque no cierra: {len(sin_alcance)} sin alcance + "
        f"{len(conectados)} conectados = {total}, y el arranque era "
        f"{ARRANQUE_NO_ALCANZABLE} (los 11)")


def test_esperado_de_la_fase_en_curso():
    """Cada modulo declarado conectado tiene que estarlo DE VERDAD, con nombre."""
    fallas = []
    for m, fase in sorted(EXPECTED_CONNECTED.items()):
        assert m in ORPHAN_CORPUS, f"{m} no pertenece al corpus CERRADO de 11"
        d = direct_importers(m)
        if not d:
            fallas.append(f"{m} ({fase}): 0 importadores directos")
            continue
        if not prod_reachable(m):
            fallas.append(
                f"{m} ({fase}): importado por {d} pero fuera del alcance de produccion")
    assert not fallas, (
        "modulos declarados conectados que NO lo estan:\n  - " + "\n  - ".join(fallas))
