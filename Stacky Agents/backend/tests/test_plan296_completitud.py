"""tests/test_plan296_completitud.py - Plan 296 F2.

Que falta, que esta mal, cuanto llevamos: la completitud del perfil y el banco
de preguntas derivado de lo que falta.

16 casos declarados, 16 colectados (sin parametrize).

AISLAMIENTO: `estado_perfil` lee `projects_dir()` (seam de LECTURA de
services/client_profile.py). La fixture lo apunta a tmp_path para que ningun
caso dependa de -- ni toque -- los proyectos reales del operador.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


@pytest.fixture()
def proyectos(tmp_path, monkeypatch):
    """Apunta el seam de lectura de client_profile a tmp_path. SOLO LECTURA."""
    import services.client_profile as cp

    pdir = tmp_path / "projects"
    pdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cp, "projects_dir", lambda: pdir)

    def sembrar(nombre: str, *, perfil=None, tracker="azure_devops"):
        carpeta = pdir / nombre.upper()
        carpeta.mkdir(parents=True, exist_ok=True)
        cfg = {"issue_tracker": {"type": tracker}}
        if perfil is not None:
            cfg["client_profile"] = perfil
        (carpeta / "config.json").write_text(
            json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
        )
        return nombre

    return sembrar


_TRES_REQUERIDAS = {
    "code_layout": {"roots": ["src"]},
    "language": {"primary": "python"},
    "tracker_state_machine": {"functional": {"next_state_ok": "Active"}},
}


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_perfil_vacio_falta_las_tres_requeridas(proyectos):
    from services.profile_completeness import SECCIONES_REQUERIDAS, estado_perfil

    proyectos("DEMO")  # proyecto SIN client_profile guardado
    estado = estado_perfil("DEMO")
    assert estado["tiene_perfil"] is False
    assert estado["secciones_faltantes_requeridas"] == list(SECCIONES_REQUERIDAS), (
        f"faltantes reales: {estado['secciones_faltantes_requeridas']}"
    )


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_seccion_ya_completa_no_genera_pregunta(proyectos):
    """K4 - toda seccion ya presente y valida sale del banco de preguntas."""
    from services.profile_completeness import estado_perfil, preguntas_pendientes

    proyectos("DEMO", perfil={"code_layout": {"roots": ["src", "backend"]}})
    estado = estado_perfil("DEMO")
    repetidas = [p for p in preguntas_pendientes(estado) if p.seccion == "code_layout"]
    assert repetidas == [], f"pregunto de nuevo por code_layout: {[p.id for p in repetidas]}"


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_seccion_vacia_cuenta_como_ausente(proyectos):
    from services.profile_completeness import estado_perfil

    proyectos("DEMO", perfil={"code_layout": {}})
    estado = estado_perfil("DEMO")
    assert "code_layout" in estado["secciones_faltantes_requeridas"], (
        f"un dict vacio se conto como presente: {estado['secciones_presentes']}"
    )


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_completitud_solo_cuenta_requeridas(proyectos):
    from services.profile_completeness import completitud, estado_perfil

    proyectos("DEMO", perfil=dict(_TRES_REQUERIDAS))
    c = completitud(estado_perfil("DEMO"))
    assert (c["requeridas_ok"], c["requeridas_total"]) == (3, 3)
    assert (c["opcionales_ok"], c["opcionales_total"]) == (0, 6)
    assert c["porcentaje"] == 100, (
        f"el porcentaje mezclo opcionales: {c['porcentaje']} con {c}"
    )


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_listo_para_usar_exige_validacion_ok(proyectos):
    """La key secreta va ANIDADA a proposito: `_contains_secret_keys` es
    recursivo (client_profile.py:196-211), asi que basta una key hundida para
    forzar ok=False."""
    from services.profile_completeness import completitud, estado_perfil

    perfil = json.loads(json.dumps(_TRES_REQUERIDAS))
    perfil["code_layout"]["credenciales"] = {"password": "x"}
    proyectos("DEMO", perfil=perfil)

    estado = estado_perfil("DEMO")
    assert estado["validacion"]["ok"] is False, "el secreto anidado no se detecto"
    assert completitud(estado)["listo_para_usar"] is False


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_listo_para_usar_exige_cero_warnings_de_seccion_ausente():
    """C12 - `validate_client_profile({}).ok` ya es True hoy porque las secciones
    requeridas ausentes generan WARNINGS, no errors. El unico indicador que
    discrimina es que esos warnings desaparezcan.

    El estado se construye a mano porque esta combinacion (las 3 secciones
    presentes Y un warning de seccion ausente) no la puede producir el
    validador real: es exactamente el caso que el AND tiene que atrapar.
    """
    from services.profile_completeness import SECCIONES_REQUERIDAS, completitud

    estado = {
        "secciones_presentes": list(SECCIONES_REQUERIDAS),
        "secciones_faltantes_requeridas": [],
        "secciones_faltantes_opcionales": [],
        "validacion": {"ok": True, "errors": [], "warnings": []},
        "warnings_de_seccion_ausente": ["tracker_state_machine"],
    }
    c = completitud(estado)
    assert c["listo_para_usar"] is False, (
        "listo_para_usar ignoro el warning de seccion ausente "
        f"{estado['warnings_de_seccion_ausente']}"
    )

    estado["warnings_de_seccion_ausente"] = []
    assert completitud(estado)["listo_para_usar"] is True


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_proxima_pregunta_respeta_ya_respondidas(proyectos):
    from services.profile_completeness import estado_perfil, preguntas_pendientes, proxima_pregunta

    proyectos("DEMO")
    estado = estado_perfil("DEMO")
    pendientes = preguntas_pendientes(estado)
    assert len(pendientes) >= 2

    primera = proxima_pregunta(estado, ())
    assert primera is not None and primera.id == pendientes[0].id

    segunda = proxima_pregunta(estado, (primera.id,))
    assert segunda is not None and segunda.id == pendientes[1].id, (
        f"tras responder {primera.id!r} devolvio {segunda.id if segunda else None!r}"
    )


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_proxima_pregunta_devuelve_none_cuando_no_falta_nada(proyectos):
    from services.profile_completeness import estado_perfil, preguntas_pendientes, proxima_pregunta

    proyectos("DEMO")
    estado = estado_perfil("DEMO")
    todas = tuple(p.id for p in preguntas_pendientes(estado))
    assert proxima_pregunta(estado, todas) is None


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_obligatorias_van_antes_que_opcionales(proyectos):
    from services.profile_completeness import estado_perfil, preguntas_pendientes

    proyectos("DEMO")
    pendientes = preguntas_pendientes(estado_perfil("DEMO"))
    obligatorias = [i for i, p in enumerate(pendientes) if p.obligatoria]
    opcionales = [i for i, p in enumerate(pendientes) if not p.obligatoria]
    assert obligatorias and opcionales
    assert max(obligatorias) < min(opcionales), (
        f"orden real: {[(p.id, p.obligatoria) for p in pendientes]}"
    )


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_estados_validos_vacios_degradan_a_texto_libre(proyectos):
    from services.profile_completeness import estado_perfil, preguntas_pendientes

    proyectos("DEMO")
    pendientes = preguntas_pendientes(estado_perfil("DEMO"), estados_validos=())
    tsm = [p for p in pendientes if p.seccion == "tracker_state_machine"]
    assert len(tsm) == 1, f"se esperaba 1 pregunta de tracker_state_machine, hay {len(tsm)}"
    assert tsm[0].tipo == "texto", f"tipo real: {tsm[0].tipo!r}"
    assert tsm[0].opciones == ()
    assert tsm[0].texto.strip(), "pregunta muda"


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_estados_validos_poblados_dan_eleccion(proyectos):
    from services.profile_completeness import estado_perfil, preguntas_pendientes

    proyectos("DEMO")
    pendientes = preguntas_pendientes(
        estado_perfil("DEMO"), estados_validos=("New", "Active", "Closed")
    )
    tsm = [p for p in pendientes if p.seccion == "tracker_state_machine"][0]
    assert tsm.tipo == "eleccion", f"tipo real: {tsm.tipo!r}"
    assert tsm.opciones == ("New", "Active", "Closed"), f"opciones: {tsm.opciones}"


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_procesos_detectados_vacios_no_generan_pregunta_muda(proyectos):
    """C1 - `procesos_detectados` es un PARAMETRO, no una llamada:
    autodetect_process_catalog es una RUTA FLASK y services/ no importa api/."""
    from services.profile_completeness import estado_perfil, preguntas_pendientes

    proyectos("DEMO")
    pendientes = preguntas_pendientes(estado_perfil("DEMO"), procesos_detectados=())
    procesos = [p for p in pendientes if p.seccion == "process_catalog"]
    assert len(procesos) == 1, f"se esperaba 1 pregunta de procesos, hay {len(procesos)}"
    assert procesos[0].tipo == "texto", f"tipo real: {procesos[0].tipo!r}"
    assert procesos[0].opciones == ()
    assert procesos[0].texto.strip(), "pregunta muda: la degradacion tiene que ser VISIBLE"


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_procesos_detectados_poblados_dan_eleccion(proyectos):
    from services.profile_completeness import estado_perfil, preguntas_pendientes

    proyectos("DEMO")
    pendientes = preguntas_pendientes(
        estado_perfil("DEMO"), procesos_detectados=("Mul2Bane", "RSCore")
    )
    procesos = [p for p in pendientes if p.seccion == "process_catalog"][0]
    assert procesos.tipo == "eleccion", f"tipo real: {procesos.tipo!r}"
    assert procesos.opciones == ("Mul2Bane", "RSCore"), f"opciones: {procesos.opciones}"


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_inconsistencias_cubren_las_cuatro_formas(proyectos):
    """C13 - el v1 cubria 1 de las 4 formas reales de mensaje. Cada sub-assert
    compara el MENSAJE, nunca un conteo."""
    from services.profile_completeness import estado_perfil

    def _incs(perfil):
        proyectos("DEMO", perfil=perfil)
        return estado_perfil("DEMO")["inconsistencias"]

    # (1) client_profile.<seccion> debe ser <tipo>, recibi <tipo>
    incs = _incs({"code_layout": ["src"]})
    hit = [i for i in incs if i["seccion"] == "code_layout" and "debe ser" in i["detalle"]]
    assert hit, f"forma 1 no mapeada. inconsistencias: {incs}"

    # (2) tracker_state_machine.<rol> debe ser un objeto.
    incs = _incs({"tracker_state_machine": {"functional": ["New"]}})
    hit = [
        i for i in incs
        if i["seccion"] == "tracker_state_machine" and "functional" in i["detalle"]
    ]
    assert hit, f"forma 2 no mapeada. inconsistencias: {incs}"

    # (3) client_profile no debe contener secretos. Claves detectadas: ...
    incs = _incs({"database": {"password": "x"}})
    hit = [i for i in incs if "secretos" in i["detalle"]]
    assert hit, f"forma 3 no mapeada. inconsistencias: {incs}"
    assert hit[0]["seccion"] == "general", f"seccion real: {hit[0]['seccion']!r}"
    assert hit[0]["sensible"] is True, "un secreto detectado no quedo marcado como sensible"

    # (4) schema_version <N> mas nuevo que el soportado
    incs = _incs({"schema_version": 99})
    hit = [i for i in incs if "schema_version" in i["detalle"] and i["seccion"] == "general"]
    assert hit, f"forma 4 no mapeada. inconsistencias: {incs}"


# ── 15 ───────────────────────────────────────────────────────────────────────
def test_toda_pregunta_tiene_texto_y_motivo_no_vacios(proyectos):
    from services.profile_completeness import (
        SECCIONES_OPCIONALES,
        SECCIONES_REQUERIDAS,
        estado_perfil,
        preguntas_pendientes,
    )

    proyectos("DEMO")
    pendientes = preguntas_pendientes(estado_perfil("DEMO"))
    cubiertas = {p.seccion for p in pendientes}
    esperadas = set(SECCIONES_REQUERIDAS) | set(SECCIONES_OPCIONALES) | {"process_catalog"}
    assert esperadas <= cubiertas, f"secciones sin pregunta: {sorted(esperadas - cubiertas)}"

    mudas = [p.id for p in pendientes if not (p.texto or "").strip() or not (p.motivo or "").strip()]
    assert mudas == [], f"preguntas sin texto o sin motivo: {mudas}"


# ── 16 ───────────────────────────────────────────────────────────────────────
def test_no_importa_la_capa_web():
    """C5 - por AST, NO por texto."""
    from services import profile_completeness

    src = pathlib.Path(profile_completeness.__file__).read_text(encoding="utf-8")
    arbol = ast.parse(src)
    ofensores: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            ofensores += [a.name for a in nodo.names if a.name.split(".")[0] == "api"]
        elif isinstance(nodo, ast.ImportFrom):
            if (nodo.module or "").split(".")[0] == "api":
                ofensores.append(nodo.module)
    assert ofensores == [], f"services/ no puede importar api/. Ofensores: {ofensores}"
