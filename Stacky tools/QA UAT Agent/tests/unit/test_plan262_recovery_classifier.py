"""Plan 262 F3 — recovery_classifier: las 5 clases del pedido, mapeadas a lo que ya existe.

25 casos. El par discriminante es test_health_none_da_unrecoverable_no_functional /
test_app_viva_ruta_legal_sin_nav_code_da_functional_error: la implementacion
prohibida ("si algo exploto, es la app") falla el segundo; la perezosa ("si no se,
es funcional") falla el primero.

El gate anti-deriva (ultimo caso) escanea el ARCHIVO COMPLETO del driver y es
BIDIRECCIONAL. El gate del v1 miraba solo _classify_error, obtenia 8 de 11 y
pasaba dejando NAV_WRONG_SCREEN sin mapear — el codigo mas on-point del pedido.
"""
from __future__ import annotations

import re
from pathlib import Path

import failure_triage
import playwright_result_classifier
import recovery_classifier as rc
from agenda_health import HealthProbe

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_DRIVER = _TOOL_ROOT / "navigation_driver.py"
_CLASSIFIER_PY = _TOOL_ROOT / "recovery_classifier.py"


def _viva(samples: int = 2) -> HealthProbe:
    return HealthProbe(True, 200, "http://x/AgendaWeb/", 5, "", "http_probe_confirmed",
                       samples)


def _muerta(samples: int = 2) -> HealthProbe:
    return HealthProbe(False, None, "http://x/AgendaWeb/", 5000, "URLError: refused",
                       "http_probe_confirmed", samples)


# ── Forma de la taxonomia ─────────────────────────────────────────────────────

def test_las_5_clases_y_nada_mas():
    assert rc.RECOVERY_CLASSES == frozenset({
        "SERVICE_DOWN", "ROUTE_ERROR", "SESSION_ERROR",
        "FUNCTIONAL_ERROR", "UNRECOVERABLE",
    })


def test_toda_clase_mapea_a_una_categoria_existente():
    ajenas = {
        c: t["category"] for c, t in rc._CLASS_TO_TAXONOMY.items()
        if t["category"] not in playwright_result_classifier.VALID_CATEGORIES
        or t["category"] not in failure_triage.VALID_CATEGORIES
    }
    assert ajenas == {}, f"categorias que no existen en las taxonomias vigentes: {ajenas}"


def test_todo_verdict_esta_en_valid_verdicts():
    ajenos = {
        c: t["verdict"] for c, t in rc._CLASS_TO_TAXONOMY.items()
        if t["verdict"] not in playwright_result_classifier.VALID_VERDICTS
    }
    assert ajenos == {}, f"verdicts fuera de VALID_VERDICTS: {ajenos}"


def test_todo_owner_esta_en_valid_owners():
    ajenos = {
        c: t["owner"] for c, t in rc._CLASS_TO_TAXONOMY.items()
        if t["owner"] not in failure_triage.VALID_OWNERS
    }
    assert ajenos == {}, f"owners fuera de VALID_OWNERS: {ajenos}"


# ── Las 5 clases, por evidencia ───────────────────────────────────────────────

def test_app_caida_da_service_down():
    v = rc.classify_recovery(exc_text="boom", route_used="FrmBusqueda.aspx",
                             health=_muerta(), route_allowed=True)
    assert v.recovery_class == "SERVICE_DOWN"


def test_ruta_no_permitida_con_app_viva_da_route_error():
    v = rc.classify_recovery(exc_text="boom", route_used="FrmInventada.aspx",
                             health=_viva(), route_allowed=False)
    assert v.recovery_class == "ROUTE_ERROR"


def test_nav_deviation_da_route_error():
    v = rc.classify_recovery(exc_text="x", route_used="a.aspx", nav_code="NAV_DEVIATION",
                             health=_viva(), route_allowed=True)
    assert v.recovery_class == "ROUTE_ERROR"


def test_nav_wrong_screen_da_route_error():
    """v2/C2 — 'pantalla equivocada' es el caso MAS central del pedido del operador.

    Con el mapa del v1 caia en UNRECOVERABLE, o sea "no se puede hacer nada".
    """
    v = rc.classify_recovery(exc_text="x", route_used="a.aspx",
                             nav_code="NAV_WRONG_SCREEN", health=_viva(),
                             route_allowed=True)
    assert v.recovery_class == "ROUTE_ERROR"
    assert v.taxonomy["recoverable"] is True


def test_menu_label_not_found_da_route_error():
    v = rc.classify_recovery(exc_text="x", route_used="a.aspx",
                             nav_code="MENU_LABEL_NOT_FOUND", health=_viva(),
                             route_allowed=True)
    assert v.recovery_class == "ROUTE_ERROR"


def test_session_lost_da_session_error():
    v = rc.classify_recovery(exc_text="x", route_used="a.aspx",
                             nav_code="NAV_SESSION_LOST", health=_viva(),
                             route_allowed=True)
    assert v.recovery_class == "SESSION_ERROR"


def test_auth_expired_da_session_error():
    v = rc.classify_recovery(exc_text="x", route_used="a.aspx",
                             nav_code="NAV_AUTH_EXPIRED", health=_viva(),
                             route_allowed=True)
    assert v.recovery_class == "SESSION_ERROR"


def test_nav_timeout_con_app_viva_da_unrecoverable():
    """El driver ya reintento lo suyo con backoff [1,2,4,8]. Duplicarlo viola INV-7."""
    v = rc.classify_recovery(exc_text="x", route_used="a.aspx", nav_code="NAV_TIMEOUT",
                             health=_viva(), route_allowed=True)
    assert v.recovery_class == "UNRECOVERABLE"


def test_app_viva_ruta_legal_sin_nav_code_da_functional_error():
    """La prueba fallo. Es un RESULTADO, no un incidente. INV-2: no se reintenta."""
    v = rc.classify_recovery(exc_text="expected 5 got 3", route_used="FrmBusqueda.aspx",
                             health=_viva(), route_allowed=True)
    assert v.recovery_class == "FUNCTIONAL_ERROR"


def test_functional_error_no_es_recuperable():
    v = rc.classify_recovery(exc_text="assert", route_used="a.aspx",
                             health=_viva(), route_allowed=True)
    assert v.taxonomy["recoverable"] is False


def test_is_recoverable_publica_coincide_con_la_taxonomia():
    """v2/C14 — API publica para F5: una clase desconocida NO puede levantar KeyError."""
    for clase, tax in rc._CLASS_TO_TAXONOMY.items():
        assert rc.is_recoverable(clase) is tax["recoverable"], clase
    assert rc.is_recoverable("BASURA") is False


# ── Sin evidencia no se afirma nada ───────────────────────────────────────────

def test_health_none_da_unrecoverable_no_functional():
    """Sin evidencia de salud no se afirma ni caida ni fallo funcional."""
    v = rc.classify_recovery(exc_text="boom", route_used="a.aspx", health=None,
                             route_allowed=True)
    assert v.recovery_class == "UNRECOVERABLE"


def test_health_sin_confirmar_no_da_service_down():
    """v2/F1.5 — una sola muestra muerta NO puede gastar el arranque de servicio."""
    v = rc.classify_recovery(exc_text="boom", route_used="a.aspx",
                             health=_muerta(samples=1), route_allowed=True)
    assert v.recovery_class == "UNRECOVERABLE"
    assert "muestra" in v.evidence.lower()


def test_exc_vacia_da_unrecoverable():
    """Inventar un fallo funcional a partir de la nada es fabricar un veredicto."""
    v = rc.classify_recovery(exc=None, exc_text="", route_used="a.aspx",
                             health=_viva(), route_allowed=True)
    assert v.recovery_class == "UNRECOVERABLE"


def test_nav_code_gana_sobre_ruta_no_permitida():
    """El driver tuvo acceso a la URL real en el momento del fallo: su senal gana."""
    v = rc.classify_recovery(exc_text="x", route_used="a.aspx",
                             nav_code="NAV_SESSION_LOST", health=_viva(),
                             route_allowed=False)
    assert v.recovery_class == "SESSION_ERROR"
    assert "conflicto" in v.evidence.lower()


def test_evidence_nunca_vacia():
    casos = [
        dict(exc_text="x", route_used="a.aspx", health=_muerta(), route_allowed=True),
        dict(exc_text="x", route_used="a.aspx", health=_viva(), route_allowed=False),
        dict(exc_text="x", route_used="a.aspx", nav_code="NAV_SESSION_LOST",
             health=_viva(), route_allowed=True),
        dict(exc_text="x", route_used="a.aspx", health=_viva(), route_allowed=True),
        dict(exc_text="x", route_used="a.aspx", health=None, route_allowed=True),
    ]
    vacias = [c for c in casos if not rc.classify_recovery(**c).evidence.strip()]
    assert vacias == [], f"clasificaciones sin evidencia escrita: {vacias}"


def test_route_used_vacia_se_rotula_desconocida():
    v = rc.classify_recovery(exc_text="x", route_used="", health=_viva(),
                             route_allowed=None)
    assert v.route_used == "<desconocida>"


def test_redireccion_a_otro_host_da_route_error():
    v = rc.classify_recovery(exc_text="x", route_used="http://otro:8080/x.aspx",
                             health=_viva(), route_allowed=False)
    assert v.recovery_class == "ROUTE_ERROR"


# ── INV-6: determinismo ───────────────────────────────────────────────────────

def test_clasificador_no_importa_ningun_modulo_de_llm():
    texto = _CLASSIFIER_PY.read_text(encoding="utf-8")
    hits = [t for t in ("invoke_local_llm", "openai", "anthropic", "STACKY_LLM_BACKEND")
            if t in texto]
    assert hits == [], f"INV-6 roto: el clasificador referencia {hits}"


def test_clasificar_es_puro():
    args = dict(exc_text="boom", route_used="a.aspx", nav_code="NAV_DEVIATION",
                health=_viva(), route_allowed=False)
    assert rc.classify_recovery(**args) == rc.classify_recovery(**args)


# ── Gate anti-deriva, bidireccional, sobre el ARCHIVO COMPLETO ────────────────

def test_los_11_nav_codes_del_driver_estan_mapeados():
    """v2/C2 — escanea TODO navigation_driver.py, no solo _classify_error.

    TRES regex, no dos: los codigos NAV_DOPOSTBACK_NOT_AVAILABLE y NAV_JS_ERROR
    nacen de un ternario asignado a una local (`_ec = "A" if ... else "B"`, :734)
    y despues se pasan como `error_code=_ec`, asi que NINGUNO de los dos patrones
    del plan (`error_code="..."` y `return "..."`) los ve. Con dos regex el
    conjunto da 9 y el assert de 11 seria insatisfacible.
    """
    texto = _DRIVER.read_text(encoding="utf-8")
    _NOT_AN_ERROR_CODE = {"NAV_SUCCESS"}          # solo aparece en el docstring :33

    found = set()
    found |= set(re.findall(r'error_code\s*=\s*"([A-Z][A-Z0-9_]+)"', texto))
    found |= set(re.findall(r'return\s+"([A-Z][A-Z0-9_]+)"', texto))
    found |= set(re.findall(r'_ec\s*=\s*"([A-Z][A-Z0-9_]+)"', texto))
    found |= set(re.findall(r'else\s+"([A-Z][A-Z0-9_]+)"', texto))
    found -= _NOT_AN_ERROR_CODE

    sin_mapear = sorted(found - set(rc._NAV_CODE_TO_CLASS))
    assert sin_mapear == [], f"codigos del driver SIN mapear: {sin_mapear}"

    fantasma = sorted(set(rc._NAV_CODE_TO_CLASS) - found)
    assert fantasma == [], f"entradas fantasma en _NAV_CODE_TO_CLASS: {fantasma}"

    assert len(found) == 11, (
        f"el driver ahora produce {len(found)} codigos: {sorted(found)}"
    )
