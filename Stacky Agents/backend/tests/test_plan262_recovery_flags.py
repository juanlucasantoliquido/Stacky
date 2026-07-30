"""Plan 262 F2 — las 9 claves nuevas del arnes y el puente flags->proceso del tool.

14 casos. Los dos mas importantes:
  - caso 11 (C4): AGENDA_WEB_BASE_URL NO puede pisar el valor del operador. Si lo
    pisa, el probe pega contra la URL equivocada, da SERVICE_DOWN, y el plan se
    autoinflige el bug que vino a matar.
  - caso 10 (C5/R-5): el export coacciona TODO a booleano; int("true") -> ValueError
    dentro del hilo del pipeline -> rotulado PIPELINE_CRASH.
"""
from __future__ import annotations

import ast
import importlib
import os
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND.parent.parent
_TOOL_ROOT = _REPO_ROOT / "Stacky tools" / "QA UAT Agent"
_RECOVERY_CONFIG_PY = _TOOL_ROOT / "recovery_config.py"
_CONFIG_PY = _BACKEND / "config.py"

LAS_9 = (
    "STACKY_QA_UAT_HOT_RECOVERY_ENABLED",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE",
    "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S",
    "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S",
    "STACKY_QA_UAT_ROUTE_ALLOWLIST",
    "STACKY_QA_UAT_SAFE_ROUTE",
    "AGENDA_WEB_BASE_URL",
    "QA_NAV_RETRIES",
)

_TIPOS = {
    "STACKY_QA_UAT_HOT_RECOVERY_ENABLED": "bool",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN": "int",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE": "int",
    "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S": "float",
    "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S": "float",
    "STACKY_QA_UAT_ROUTE_ALLOWLIST": "csv",
    "STACKY_QA_UAT_SAFE_ROUTE": "str",
    "AGENDA_WEB_BASE_URL": "str",
    "QA_NAV_RETRIES": "int",
}

_BOUNDS = {
    "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN": (0, 50),
    "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE": (0, 10),
    "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S": (1, 30),
    "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S": (0, 15),
    "QA_NAV_RETRIES": (0, 10),
}

# Las 5 bool que el puente ya exportaba antes de este plan (api/qa_uat.py:83-87).
_BOOL_PREEXISTENTES = (
    "STACKY_QA_UAT_ADO_BRIDGE_ENABLED",
    "STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED",
    "STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED",
    "STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED",
    "STACKY_QA_UAT_EPIC_ROLLUP_ENABLED",
)


def _spec_by_key():
    from services.harness_flags import FLAG_REGISTRY
    return {s.key: s for s in FLAG_REGISTRY}


def test_las_9_keys_estan_en_el_registry():
    specs = _spec_by_key()
    faltantes = [k for k in LAS_9 if k not in specs]
    assert faltantes == [], f"keys ausentes de FLAG_REGISTRY: {faltantes}"


def test_las_9_keys_estan_categorizadas():
    from services.harness_flags import categorize
    mal = {k: categorize(k) for k in LAS_9 if categorize(k) != "calidad_verificacion"}
    assert mal == {}, f"keys mal categorizadas (key -> categoria real): {mal}"


def test_los_tipos_son_los_declarados():
    specs = _spec_by_key()
    real = {k: specs[k].type for k in LAS_9 if k in specs}
    assert real == _TIPOS, f"tipos divergentes: {real}"


def test_solo_la_bool_tiene_default_explicito():
    specs = _spec_by_key()
    assert specs["STACKY_QA_UAT_HOT_RECOVERY_ENABLED"].default is True
    con_default = [
        k for k in LAS_9
        if k != "STACKY_QA_UAT_HOT_RECOVERY_ENABLED"
        and k in specs and specs[k].default is not None
    ]
    assert con_default == [], (
        "las 8 de valor NO pueden declarar default= (default_is_known es "
        f"`spec.default is not None`, type-agnostico). Ofensoras: {con_default}"
    )


def test_las_5_numericas_tienen_bounds():
    specs = _spec_by_key()
    real = {
        k: (specs[k].min_value, specs[k].max_value)
        for k in _BOUNDS if k in specs
    }
    esperado = {k: (float(a), float(b)) for k, (a, b) in _BOUNDS.items()}
    normal = {k: (float(a), float(b)) for k, (a, b) in real.items()}
    assert normal == esperado, f"bounds divergentes: {real}"


def test_las_9_estan_en_config_py():
    from config import config
    faltantes = [k for k in LAS_9 if not hasattr(config, k)]
    assert faltantes == [], f"keys ausentes de config.py: {faltantes}"


def test_defaults_de_config_coinciden_con_el_tool():
    """Paridad cross-arbol SIN importar el tool: se lee DEFAULTS como texto.

    Los defaults EFECTIVOS viven duplicados a proposito (el tool corre tambien
    desde la CLI, donde NADIE exporta las keys). Este test falla si divergen.
    """
    from config import config

    texto = _RECOVERY_CONFIG_PY.read_text(encoding="utf-8")
    marca = "DEFAULTS: dict[str, str] = "
    ini = texto.index(marca) + len(marca)
    fin = texto.index("\n}", ini) + len("\n}")
    defaults_tool = ast.literal_eval(texto[ini:fin])

    divergencias = {}
    for k in LAS_9:
        v = getattr(config, k, None)
        # Los bool viajan como "true"/"false" por el entorno, no como "True".
        esperado = str(v).lower() if isinstance(v, bool) else str(v)
        if defaults_tool.get(k) != esperado:
            divergencias[k] = {"tool": defaults_tool.get(k), "config": esperado}
    assert divergencias == {}, f"defaults divergentes tool vs config: {divergencias}"


def test_las_9_estan_en_la_tupla_de_export():
    import api.qa_uat as qa
    faltantes = [k for k in LAS_9 if k not in qa._QA_UAT_FLAG_KEYS]
    assert faltantes == [], (
        f"sin esto nacen invisibles para el tool. Faltantes: {faltantes}"
    )


def test_export_de_bool_sigue_siendo_true_false():
    """GUARDA DE NO-REGRESION: las 5 bool preexistentes no cambian de forma."""
    import api.qa_uat as qa
    exported = qa._export_qa_uat_flags()
    malas = {
        k: exported.get(k) for k in _BOOL_PREEXISTENTES
        if exported.get(k) not in ("true", "false")
    }
    assert malas == {}, f"el export rompio las bool preexistentes: {malas}"


def test_export_de_valor_no_se_coacciona_a_booleano(monkeypatch):
    """int('true') levanta ValueError DENTRO del hilo del pipeline -> PIPELINE_CRASH."""
    import api.qa_uat as qa
    from config import config

    monkeypatch.setattr(config, "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN", 6, raising=False)
    qa._export_qa_uat_flags()
    valor = os.environ["STACKY_QA_UAT_RECOVERY_MAX_PER_RUN"]
    assert valor == "6", f"se exporto {valor!r}; coaccionar a booleano destruye el valor"


def test_export_de_base_url_es_idempotente_con_el_valor_del_operador():
    """v2/C4 — EL GATE MAS IMPORTANTE DE F2.

    Con la declaracion hardcodeada en config.py este test FALLA: todo run lanzado
    desde la UI pisaria la URL del operador con el default 35017, el probe pegaria
    contra la URL equivocada y el veredicto seria SERVICE_DOWN. Con la declaracion
    env-first PASA, porque config adopta el valor del entorno y el export escribe
    el MISMO string: la operacion se vuelve idempotente.
    """
    import config as config_mod
    import api.qa_uat as qa

    ajeno = "http://otrohost:9999/AgendaWeb/"
    previo = os.environ.get("AGENDA_WEB_BASE_URL")
    try:
        os.environ["AGENDA_WEB_BASE_URL"] = ajeno
        importlib.reload(config_mod)           # config debe materializarse con el env puesto
        qa._export_qa_uat_flags()
        assert os.environ["AGENDA_WEB_BASE_URL"] == ajeno, (
            "el export piso la URL base del operador con el default"
        )
    finally:
        if previo is None:
            os.environ.pop("AGENDA_WEB_BASE_URL", None)
        else:
            os.environ["AGENDA_WEB_BASE_URL"] = previo
        importlib.reload(config_mod)           # restaurar para el resto del archivo


def test_agenda_web_base_url_se_declara_env_first():
    """Gate ESTRUCTURAL: impide que un refactor futuro la vuelva a hardcodear."""
    texto = _CONFIG_PY.read_text(encoding="utf-8")
    m = re.search(
        r'AGENDA_WEB_BASE_URL\s*:\s*str\s*=\s*os\.getenv\(\s*"AGENDA_WEB_BASE_URL"',
        texto,
        re.S,
    )
    assert m is not None, (
        "AGENDA_WEB_BASE_URL debe declararse env-first con os.getenv(...); "
        "un default hardcodeado vuelve DESTRUCTIVO el export (C4)"
    )


def test_qa_nav_retries_default_es_3_en_config():
    """v2/C9 — un 1 aca bajaria los reintentos efectivos de navegacion en silencio."""
    from config import config
    assert config.QA_NAV_RETRIES == 3


def test_ninguna_de_las_9_keys_esta_en_curated_defaults_on_salvo_la_bool():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert "STACKY_QA_UAT_HOT_RECOVERY_ENABLED" in _CURATED_DEFAULTS_ON
    intrusas = [
        k for k in LAS_9
        if k != "STACKY_QA_UAT_HOT_RECOVERY_ENABLED" and k in _CURATED_DEFAULTS_ON
    ]
    assert intrusas == [], (
        f"las 8 de valor no tienen default= y no pueden estar en el set curado: {intrusas}"
    )
