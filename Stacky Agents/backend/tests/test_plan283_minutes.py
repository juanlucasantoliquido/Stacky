"""Plan 283 F6 - El destilado con cita obligatoria y atribucion verificada.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

_MODULO = pathlib.Path(__file__).resolve().parents[1] / "services" / "meeting_minutes.py"

FUENTE = (
    "Juan Perez: arrancamos con el estado del proyecto.\n"
    "Ana Gomez: yo reviso el informe el viernes.\n"
    "Juan Perez: perfecto, lo vemos el lunes entonces."
)


@pytest.fixture(autouse=True)
def _db():
    import db

    db.init_db()
    with db.session_scope() as s:
        from services.meetings_store import Meeting, MeetingActionItem

        s.query(MeetingActionItem).delete(synchronize_session=False)
        s.query(Meeting).delete(synchronize_session=False)
    yield


class _RespuestaFalsa:
    def __init__(self, text: str):
        self.text = text
        self.format = "markdown"
        self.metadata = {}


def _reunion_con_transcripcion(project="P283", texto=FUENTE) -> int:
    from services import meetings_store as st

    mid = st.create_meeting(project=project, subject="Semanal de proyecto")
    st.save_transcript(mid, content=texto, fmt="txt")
    return mid


def test_1_el_prompt_trae_las_reglas_y_la_fecha_de_referencia():
    from services.local_insights import HITL_RULES
    from services.meeting_minutes import build_minutes_prompt

    fecha = datetime(2026, 8, 1, 12, 0, 0)
    system, user = build_minutes_prompt(texto=FUENTE, subject="Semanal", fecha_ref=fecha)

    assert HITL_RULES in system                 # se REUSA, no se reescribe
    assert "2026-08-01T12:00:00" in user        # literal, en ISO
    assert "Semanal" in user
    assert FUENTE in user
    assert "COPIADO TAL CUAL" in user


def test_2_json_envuelto_en_cercas_se_parsea():
    from services.meeting_minutes import parse_minutes_response

    crudo = "```json\n" + json.dumps({
        "resumen": "Se reviso el estado.",
        "pendientes": [{"titulo": "Revisar informe", "responsable": "Ana Gomez",
                        "fecha_compromiso": "2026-08-07",
                        "cita": "yo reviso el informe el viernes"}],
    }, ensure_ascii=False) + "\n```"

    salida = parse_minutes_response(crudo, texto_fuente=FUENTE, hablantes=("Ana Gomez",))
    assert salida["resumen"] == "Se reviso el estado."
    assert len(salida["pendientes"]) == 1


def test_3_json_invalido_lanza_json_parse_error():
    from services.meeting_minutes import parse_minutes_response

    with pytest.raises(ValueError) as exc:
        parse_minutes_response("esto no es json", texto_fuente=FUENTE)
    assert str(exc.value).startswith("json_parse_error")

    # Un JSON valido que NO es objeto tambien.
    with pytest.raises(ValueError):
        parse_minutes_response("[1, 2, 3]", texto_fuente=FUENTE)


def test_4_los_topes_recortan():
    from services.meeting_minutes import (
        MAX_DECISIONES, MAX_PENDIENTES, RESUMEN_MAX, parse_minutes_response,
    )

    cita = "arrancamos con el estado del proyecto"
    payload = {
        "resumen": "x" * 5000,
        "decisiones": [{"texto": f"decision {i}", "cita": cita} for i in range(40)],
        "pendientes": [{"titulo": f"tarea {i}", "responsable": None,
                        "fecha_compromiso": None, "cita": cita} for i in range(40)],
    }
    salida = parse_minutes_response(json.dumps(payload), texto_fuente=FUENTE)
    assert len(salida["resumen"]) == RESUMEN_MAX
    assert len(salida["pendientes"]) == MAX_PENDIENTES
    assert len(salida["decisiones"]) == MAX_DECISIONES
    assert salida["descartados_sin_cita"] == 0


def _payload_k2() -> str:
    """FIXTURE COMPARTIDA por los casos 5 y 6: un pendiente con cita real y otro
    con cita inventada, en la MISMA respuesta."""
    return json.dumps({
        "resumen": "r",
        "pendientes": [
            {"titulo": "Revisar informe", "responsable": None, "fecha_compromiso": None,
             "cita": "yo reviso el informe el viernes"},            # SI esta en la fuente
            {"titulo": "Migrar la base el jueves", "responsable": None,
             "fecha_compromiso": None,
             "cita": "Juan se comprometio a migrar la base"},        # INVENTADA
        ],
    })


def test_5_k2_guard_positivo_el_pendiente_con_cita_real_sobrevive():
    """GUARD POSITIVO de K2. Va PRIMERO y sobre la MISMA fixture que el caso 6:
    sin el, el assert de ausencia del 6 pasaria igual si el parser devolviera
    lista vacia por un bug — que es exactamente como se ve un falso verde."""
    from services.meeting_minutes import parse_minutes_response

    salida = parse_minutes_response(_payload_k2(), texto_fuente=FUENTE)
    assert len(salida["pendientes"]) == 1, "el pendiente con cita valida tiene que sobrevivir"
    assert salida["pendientes"][0]["titulo"] == "Revisar informe"
    assert salida["pendientes"][0]["cita"] == "yo reviso el informe el viernes"


def test_6_k2_el_pendiente_con_cita_inventada_se_descarta():
    """K2 - el descarte. Repite el guard positivo ANTES del assert de ausencia
    para que este caso valga solo aunque se corra aislado (`pytest -k`)."""
    from services.meeting_minutes import parse_minutes_response

    salida = parse_minutes_response(_payload_k2(), texto_fuente=FUENTE)
    assert salida["pendientes"][0]["titulo"] == "Revisar informe"   # guard, primero
    assert len(salida["pendientes"]) == 1
    assert salida["descartados_sin_cita"] == 1
    assert all("Migrar la base" not in p["titulo"] for p in salida["pendientes"])


def test_7_la_fecha_solo_se_acepta_en_formato_iso_corto():
    from services.meeting_minutes import parse_minutes_response

    cita = "yo reviso el informe el viernes"
    base = {"titulo": "t", "responsable": None, "cita": cita}
    salida = parse_minutes_response(json.dumps({"pendientes": [
        {**base, "fecha_compromiso": "el viernes"},
        {**base, "fecha_compromiso": "2026-08-07"},
        {**base, "fecha_compromiso": "07/08/2026"},
        {**base, "fecha_compromiso": None},
    ]}), texto_fuente=FUENTE)

    fechas = [p["fecha_compromiso"] for p in salida["pendientes"]]
    assert fechas == [None, datetime(2026, 8, 7), None, None]


def test_8_k5_el_filtro_de_salida_corta_antes_de_llamar_al_modelo(monkeypatch):
    from services import egress_policies, meeting_minutes, meetings_store

    mid = _reunion_con_transcripcion()
    llamadas: list[str] = []

    import copilot_bridge

    def _espia(**kwargs):
        llamadas.append(kwargs.get("agent_type", ""))
        return _RespuestaFalsa("{}")

    monkeypatch.setattr(copilot_bridge, "invoke", _espia)

    # GUARD POSITIVO, PRIMERO: con el filtro permisivo SI se invoca al modelo.
    monkeypatch.setattr(
        egress_policies, "check",
        lambda **kw: egress_policies.EgressDecision(True, [], [], [], "ok"),
    )
    assert meeting_minutes.build_minutes_payload(meeting_id=mid, project="P283")["ok"] is False or True
    assert len(llamadas) == 1, "el guard positivo no llamo al modelo: el espia esta roto"

    # Y ahora el bloqueo real.
    llamadas.clear()
    monkeypatch.setattr(
        egress_policies, "check",
        lambda **kw: egress_policies.EgressDecision(False, ["pii"], [], ["pii"], "bloqueado"),
    )
    salida = meeting_minutes.build_minutes_payload(meeting_id=mid, project="P283")

    assert salida["estado"] == "blocked"
    assert salida["ok"] is False
    assert "pii" in salida["clases"]
    assert llamadas == [], "se invoco al modelo con el filtro en bloqueo"
    detalle = meetings_store.get_meeting_dict(mid, project="P283")
    assert detalle["minutes_state"] == "blocked"


def test_9_k4_gate_por_ast_sin_runners_de_agente():
    """El destilado no lanza ningun agente: por eso funciona identico con los 3
    runtimes. Guard positivo primero, contra un fuente que SI los importa."""
    prohibidos = {"codex_cli_runner", "claude_code_cli_runner", "agent_runner"}

    def _imports(fuente: str) -> set[str]:
        encontrados: set[str] = set()
        for nodo in ast.walk(ast.parse(fuente)):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    encontrados.update(alias.name.split("."))
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.module:
                    encontrados.update(nodo.module.split("."))
                for alias in nodo.names:
                    encontrados.add(alias.name)
        return encontrados

    # GUARD POSITIVO, PRIMERO. Este guard YA encontro un agujero real al
    # escribirlo: `from services import agent_runner` deja el nombre en
    # `node.names`, NO en `node.module`, asi que un detector que solo mire
    # `module` no lo ve. Por eso se miran los dos.
    sucio = "from services import agent_runner\nimport services.codex_cli_runner\n"
    assert _imports(sucio) & prohibidos == {"agent_runner", "codex_cli_runner"}

    real = _imports(_MODULO.read_text(encoding="utf-8"))
    assert real & prohibidos == set(), f"meeting_minutes.py importa {sorted(real & prohibidos)}"


def test_10_si_el_modelo_falla_la_transcripcion_sigue_guardada(monkeypatch):
    """D8 - la transcripcion NUNCA se pierde por un fallo del modelo."""
    import copilot_bridge
    from services import meeting_minutes, meetings_store

    mid = _reunion_con_transcripcion()

    def _revienta(**kwargs):
        raise RuntimeError("el proveedor devolvio 500")

    monkeypatch.setattr(copilot_bridge, "invoke", _revienta)
    salida = meeting_minutes.build_minutes_payload(meeting_id=mid, project="P283")

    assert salida["ok"] is False
    assert salida["estado"] == "failed"
    detalle = meetings_store.get_meeting_dict(mid, project="P283")
    assert detalle["minutes_state"] == "failed"
    # Se relee de la base y se compara caracter por caracter.
    guardada, _fmt = meetings_store.get_transcript(mid)
    assert guardada == FUENTE


_HABLANTES_K8 = ("Juan Perez", "Ana Gomez")


def _payload_k8() -> str:
    """FIXTURE COMPARTIDA por los casos 11 y 12. Las TRES citas son literales:
    lo unico que cambia entre los tres pendientes es la atribucion."""
    return json.dumps({"pendientes": [
        {"titulo": "Revisar informe", "responsable": "Juan",
         "fecha_compromiso": None, "cita": "perfecto, lo vemos el lunes entonces"},
        {"titulo": "Cerrar el presupuesto", "responsable": "Marcela",
         "fecha_compromiso": None, "cita": "perfecto, lo vemos el lunes entonces"},
        {"titulo": "Alguien confirma la sala", "responsable": None,
         "fecha_compromiso": None, "cita": "arrancamos con el estado del proyecto"},
    ]})


def test_11_k8_guard_positivo_el_responsable_que_hablo_queda_confirmado():
    """GUARD POSITIVO de K8, sobre la MISMA fixture que el caso 12. Sin el, un
    parser que marcara TODO como `sin_hablante` haria pasar el 12."""
    from services.meeting_minutes import parse_minutes_response

    salida = parse_minutes_response(
        _payload_k8(), texto_fuente=FUENTE, hablantes=_HABLANTES_K8
    )
    assert salida["pendientes"][0]["atribucion"] == "confirmada"
    assert salida["pendientes"][0]["responsable"] == "Juan"        # ~ "Juan Perez"


def test_12_k8_el_responsable_inventado_se_marca_pero_no_se_descarta():
    """El caso que la llave 1 SOLA no atrapa: la cita es literal y verdadera, y
    el responsable igual esta inventado. Descartarlo seria peor — el compromiso
    probablemente existe; lo que falla es la atribucion. Se degrada y se marca."""
    from services.meeting_minutes import parse_minutes_response

    salida = parse_minutes_response(
        _payload_k8(), texto_fuente=FUENTE, hablantes=_HABLANTES_K8
    )
    assert salida["pendientes"][0]["atribucion"] == "confirmada"   # guard, primero
    assert len(salida["pendientes"]) == 3, "ninguno se descarta: las 3 citas son literales"
    assert [p["atribucion"] for p in salida["pendientes"]] == [
        "confirmada", "sin_hablante", "sin_responsable",
    ]
    assert salida["sin_hablante"] == 1
    assert salida["descartados_sin_cita"] == 0
