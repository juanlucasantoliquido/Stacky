"""tests/test_plan281_ratchet_ado_only.py — Plan 281 F8.

El gate permanente: el censo de F0 convertido en ratchet que sólo deja BAJAR.

Baseline en `tests/ado_only_baseline.json`, archivo SEPARADO de
`provider_coupling_baseline.json` a propósito: ése pertenece al Plan 218 y tiene
su propio ratchet; mezclarlos haría que un cambio de este plan rompa un gate ajeno.

Dos controles hacen que este archivo no pueda degenerar en un gate decorativo:
  - `test_el_ratchet_detecta_una_violacion_inyectada` (F8.4): un scanner que
    devolviera `[]` siempre pasaría el ratchet para siempre. Acá se le inyecta el
    defecto en un módulo temporal y se EXIGE que lo vea.
  - `test_ningun_sitio_nuevo_lee_tracker_type_para_rutear` (F8.3): lleva la
    calibración adentro — un positivo obligatorio y CUATRO negativos obligatorios,
    entre ellos las tres funciones de clave compuesta del Plan 277, que un
    detector ingenuo (recorrer `ast.BoolOp`) marcaría como falsos positivos.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from services.provider_coupling_audit import (
    ADO_ONLY_JUSTIFICADOS,
    CIEGOS_A_GITLAB_TOLERADOS,
    scan_ado_only_sites,
    scan_tracker_type_routing,
)

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_BASELINE = Path(__file__).resolve().parent / "ado_only_baseline.json"


def _baseline() -> dict:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))


# ── F8.2 · El ratchet ────────────────────────────────────────────────────────


def test_violaciones_no_crecen():
    actual = scan_ado_only_sites()["violaciones_count"]
    base = _baseline()["violaciones_count"]
    assert actual <= base, (
        f"violaciones_count subió de {base} a {actual}. Un sitio nuevo construye "
        f"cliente ADO sin preguntar por el tracker: "
        f"{scan_ado_only_sites()['violaciones']}"
    )


def test_ado_only_no_crece():
    actual = scan_ado_only_sites()["ado_only_count"]
    base = _baseline()["ado_only_count"]
    assert actual <= base, (
        f"ado_only_count subió de {base} a {actual}: {scan_ado_only_sites()['ado_only']}"
    )


def test_ciegos_a_gitlab_no_crecen():
    s = scan_ado_only_sites()
    base = _baseline()["ciegos_count"]
    assert s["ciegos_count"] <= base, (
        f"ciegos_count subió de {base} a {s['ciegos_count']}: {s['ciegos_a_gitlab']}. "
        "Alguien agregó un tracker nuevo al sync pero no a este `if`."
    )
    # Y el único que queda tolerado es el DECLARADO, con su motivo escrito.
    assert set(s["ciegos_a_gitlab"]) <= set(CIEGOS_A_GITLAB_TOLERADOS), (
        f"hay ciegos a GitLab sin declarar: "
        f"{set(s['ciegos_a_gitlab']) - set(CIEGOS_A_GITLAB_TOLERADOS)}"
    )


def test_justificados_siguen_siendo_dos():
    """Impide agrandar la allowlist en silencio: es la puerta trasera del gate."""
    assert len(ADO_ONLY_JUSTIFICADOS) == 2, sorted(ADO_ONLY_JUSTIFICADOS)
    assert all(ADO_ONLY_JUSTIFICADOS.values()), "toda justificación exige motivo escrito"


# ── F8.3 · El detector de ruteo por `<algo>.tracker_type`, calibrado ─────────

_MODULO_CALIBRACION = '''
"""Módulo sintético de calibración del detector de ruteo por columna."""
_TRACKER_POR_DEFECTO = "azure_devops"


def refresh_ticket_snapshot(ticket):
    """POSITIVO OBLIGATORIO — el idioma REAL del defecto: la lectura y la
    comparación viven en SENTENCIAS DISTINTAS, unidas por una variable local."""
    tracker_type = ticket.tracker_type or "azure_devops"
    if tracker_type != "azure_devops":
        return {"refreshed": False, "reason": "non_ado_tracker"}
    return {"refreshed": True}


def _clave(tk):
    """NEGATIVO 1 (Plan 277) — coalescencia como CLAVE DE IDENTIDAD, no ruteo."""
    return ((tk.tracker_type or _TRACKER_POR_DEFECTO).strip().lower(), tk.ado_id)


def _clave_de_padre(tk):
    """NEGATIVO 2 (Plan 277)."""
    return ((tk.tracker_type or _TRACKER_POR_DEFECTO).strip().lower(), tk.parent_ado_id)


def _crea_ciclo(ticket, tickets, indice=None):
    """NEGATIVO 3 (Plan 277) — asigna desde la columna, pero NUNCA compara contra
    un literal de tracker: recorre la cadena de padres."""
    if indice is None:
        indice = {_clave(tk): tk for tk in tickets}
    tracker = (ticket.tracker_type or _TRACKER_POR_DEFECTO).strip().lower()
    visitados = {_clave(ticket)}
    actual = ticket.parent_ado_id
    for _ in range(50):
        if not actual:
            return False
        clave = (tracker, actual)
        if clave in visitados:
            return True
        visitados.add(clave)
        arriba = indice.get(clave)
        if arriba is None:
            return False
        actual = arriba.parent_ado_id
    return True


def serializa(t):
    """NEGATIVO 4 — MOSTRAR la columna es legítimo; decidir con ella no."""
    d = {}
    d["tracker_type"] = t.tracker_type
    return d


def preflight_check_route(project):
    """NEGATIVO 5 — el `.tracker_type` cuelga de una llamada al resolvedor: NO es
    la columna, es la verdad ya resuelta desde el config."""
    from services.project_context import resolve_project_context

    tt = resolve_project_context(project_name=project).tracker_type
    if tt == "gitlab":
        return "gl"
    return "ado"
'''


def test_ningun_sitio_nuevo_lee_tracker_type_para_rutear(tmp_path):
    # (a) El backend REAL: cero sitios ruteando por la columna (K5 cerrado por F6).
    vivos = scan_tracker_type_routing()
    assert vivos == [], f"hay sitios ruteando por la columna que MIENTE: {vivos}"

    # (b) CALIBRACIÓN — va como assert, no como paso manual (R10). El detector se
    # ejercita contra un módulo con el idioma del defecto y los cinco idiomas
    # legítimos que un detector ingenuo confundiría.
    (tmp_path / "calibracion.py").write_text(_MODULO_CALIBRACION, encoding="utf-8")
    marcadas = scan_tracker_type_routing(raiz=tmp_path)

    assert marcadas == ["calibracion.py::refresh_ticket_snapshot"], (
        f"la calibración del detector falló: {marcadas}. Si devuelve [] o si marca "
        f"las funciones de clave compuesta del Plan 277, se ARREGLA EL DETECTOR, "
        f"no se baja la expectativa."
    )
    for negativo in ("_clave", "_clave_de_padre", "_crea_ciclo", "serializa",
                     "preflight_check_route"):
        assert f"calibracion.py::{negativo}" not in marcadas, negativo


# ── F8.4 · El gate se corre CONTRA el defecto ───────────────────────────────

_MODULO_VIOLACION = '''
"""Un sitio ADO-only sintético: construye el cliente sin preguntar nada."""
from services.project_context import build_ado_client


def enriquecer_sin_guard(ado_id, project_name=None):
    client = build_ado_client(project_name=project_name)
    return client.fetch_comments(ado_id)


def por_alias(project_name=None):
    """La MISMA violación pero por alias de módulo: si el scanner sólo mirara
    `ast.Name`, éste le pasaría por debajo."""
    from services import project_context

    return project_context.build_ado_client(project_name=project_name)
'''


def test_el_ratchet_detecta_una_violacion_inyectada(tmp_path):
    """Sin este caso, un scanner que devolviera siempre listas vacías pasaría el
    ratchet para siempre."""
    (tmp_path / "inyectado.py").write_text(_MODULO_VIOLACION, encoding="utf-8")
    s = scan_ado_only_sites(raiz=tmp_path)

    assert "inyectado.py::enriquecer_sin_guard" in s["ado_only"], s
    assert "inyectado.py::por_alias" in s["ado_only"], (
        f"el scanner NO ve la llamada por alias de módulo: {s['ado_only']}"
    )
    assert s["violaciones_count"] == 2, s["violaciones"]
    # Y no inventa gateados ni ciegos donde no los hay.
    assert s["gateados"] == [] and s["con_seam"] == []


# ── F9.1 · Casos MIGRADOS desde el andamio `test_plan281_censo_ado_only.py` ──
#
# Ese archivo se borró: su caso `test_censo_reproduce_la_foto_vieja` es falso por
# diseño una vez aplicado F7 (reportaba 10 ado-only / 8 violaciones). Los otros
# cinco son propiedades PERMANENTES del detector y viven acá.


def test_app_py_ya_no_es_ciego_a_gitlab():
    """MIGRADO Y REESCRITO (el plan avisa que migrarlo tal cual falla).

    Antes de F4, `app.py::_startup_sync` era `gateado` + `ciego_a_gitlab`:
    discriminaba jira/mantis/resto y GitLab caía en el `else` de ADO. Tras F4 ya
    no es ciego —y además subió a `con_seam`, porque resuelve el provider— pero lo
    que este caso guarda es que NUNCA vuelva a `ado_only` ni a `ciegos`.
    """
    s = scan_ado_only_sites()
    assert "app.py::_startup_sync" not in s["ciegos_a_gitlab"]
    assert "app.py::_startup_sync" not in s["ado_only"]
    assert "app.py::_startup_sync" in s["con_seam"], (
        "el censo dejó de ver `_startup_sync`: el alcance ampliado de F0 "
        "(app.py DENTRO del censo) se perdió"
    )


def test_censo_detecta_llamada_por_alias():
    """R2 — `completion_sync` llama `project_context.build_ado_client(...)` por
    ALIAS de módulo. Un censo que sólo mirara `ast.Name` daría CERO ahí."""
    s = scan_ado_only_sites()
    assert "services/completion_sync.py::_do_project_sync" in s["gateados"]


def test_censo_excluye_familia_ado():
    """Un adaptador ADO tiene derecho a ser ADO-only."""
    s = scan_ado_only_sites()
    todos = set(s["con_seam"]) | set(s["gateados"]) | set(s["ado_only"])
    assert not [k for k in todos if k.startswith("services/ado_")]


def test_censo_es_determinista():
    """Un gate que devuelve listas en orden aleatorio no es un gate."""
    assert scan_ado_only_sites() == scan_ado_only_sites()


def test_justificados_son_subconjunto_de_ado_only():
    """Impide que una justificación quede huérfana y esconda un sitio que ya no existe."""
    s = scan_ado_only_sites()
    faltantes = [k for k in ADO_ONLY_JUSTIFICADOS if k not in s["ado_only"]]
    assert not faltantes, faltantes
