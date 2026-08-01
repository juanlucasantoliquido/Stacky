"""Plan 279 F4 — Prompt de copiloto de pipelines: contrato del agente (sin secretos).

Calca services/remote_console_prompt.py:8 (plan 105): el agente NO tiene acceso
directo a nada; todo pasa por un endpoint HTTP local que Stacky controla.

PURO: sin flask, sin config, sin IO, sin red. La flag de commit llega COMO
PARAMETRO (`commit_enabled`), no se lee de config acá: así el módulo se testea
sin monkeypatchear nada y el call site conserva un solo lugar donde mirar la flag.
"""
from __future__ import annotations

from services.pipeline_session import (
    TRANSITIONS,
    PipelineSession,
    next_question,
    undo_hint,
)

#: La frase que precede al deshacer. LITERAL: F4 caso 7 la congela.
UNDO_LEAD = "Antes de pedir confirmacion, decile al operador como deshacer esto:"

#: Regla de credenciales. LITERAL: F4 caso 5 la congela.
SECRETS_RULE = (
    "Los valores de variables y secretos los maneja Stacky; NUNCA pidas ni "
    "escribas un valor."
)

#: Estados en los que el operador esta por decidir una escritura y por lo tanto
#: TIENE que ver su deshacer. Espejo de mustShowUndoHint() en el frontend.
_ESTADOS_CON_UNDO = ("review", "secrets", "confirm")

_COMMIT_ACTION_ID = "devops.pipeline_new.commit"
_COMMIT_FLAG = "STACKY_PIPELINE_COPILOT_COMMIT_ENABLED"


def build_copilot_prompt(
    session: PipelineSession,
    base_url: str,
    message: str,
    conversation_id: int,
    *,
    commit_enabled: bool,
) -> str:
    """Envuelve el mensaje del operador con el contrato del copiloto.
    NUNCA incluye valores de variables ni de secretos: solo NOMBRES."""
    estado = getattr(session, "state", "") or "intake"
    destinos = TRANSITIONS.get(estado, ())
    destinos_txt = ", ".join(destinos) if destinos else "ninguno (estado terminal)"

    variables = getattr(session, "missing_variables", ()) or ()
    variables_txt = (
        ", ".join(variables) if variables
        else "(todavia no se detecto ninguna faltante)"
    )

    pregunta = next_question(session)
    pregunta_txt = (
        f'La UNICA pregunta que falta hacer es: "{pregunta}"' if pregunta
        else "No queda ninguna pregunta pendiente: no preguntes de mas."
    )

    if commit_enabled:
        commit_txt = (
            f"Podes proponer {_COMMIT_ACTION_ID} SOLO cuando la sesion este en "
            "'confirm'. Escribe en el repositorio REAL: exige confirmacion "
            "explicita del operador."
        )
    else:
        commit_txt = (
            f"PROHIBIDO proponer {_COMMIT_ACTION_ID}: esta apagado. Si el "
            "operador quiere crear la pipeline en el repositorio, explicale que "
            f"tiene que activar {_COMMIT_FLAG} desde la UI "
            "(Configuracion -> Arnes, categoria DevOps). NO intentes rodear el limite."
        )

    # [ADICION ARQUITECTO] El deshacer viaja ANTES de la confirmacion, no despues.
    hint = undo_hint(session)
    bloque_undo = (
        f"\n7. {UNDO_LEAD}\n   {hint}\n"
        if (estado in _ESTADOS_CON_UNDO and hint) else ""
    )

    return f"""[COPILOTO DE PIPELINES STACKY — conversacion {conversation_id}]

Sos un copiloto de creacion de pipelines. NO tenes acceso directo a nada: no
podes escribir archivos, ni tocar el repositorio, ni ejecutar la pipeline. Lo
UNICO que podes hacer es PROPONER una accion tipada, llamando a este endpoint
HTTP local que Stacky controla (es SOLO LECTURA: arma la propuesta, no la ejecuta):

  curl.exe -s -X POST {base_url}/api/devops/actions/propose ^
    -H "Content-Type: application/json" ^
    -d "{{\\"text\\":\\"<LO QUE QUERES HACER, EN CASTELLANO>\\",\\"params\\":{{}}}}"

Quien ejecuta es el operador, apretando el boton de la tarjeta que Stacky le
muestra. Esa confirmacion es innegociable: no la pidas por chat ni la asumas.

ESTADO DE LA SESION
- Estado actual: {estado}
- Destinos legales desde aca: {destinos_txt}
- Variables que faltan (SOLO NOMBRES): {variables_txt}

Reglas:
1. {SECRETS_RULE}
   Podes NOMBRAR una variable para pedirle al operador que la cargue en la
   seccion Variables, pero su valor no existe para vos.
2. {commit_txt}
3. Una sola pregunta por turno. {pregunta_txt}
4. No inventes un estado: solo podes avanzar a los destinos legales de arriba.
5. Antes de proponer una escritura, deci en castellano llano QUE va a pasar.
6. Si algo falla, decilo; NUNCA simules haberlo hecho.{bloque_undo}
PEDIDO DEL OPERADOR:
{message}
"""
