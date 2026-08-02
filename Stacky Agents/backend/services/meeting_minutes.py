"""Plan 283 F6 - De la transcripcion a minuta + pendientes, con anti-alucinacion
verificable EN CODIGO.

Las DOS LLAVES (D4 + D9). Un pendiente publicable tiene que probar dos cosas
distintas, y verificar solo la primera es una trampa:

  1. Se dijo?  -> `cita` es subcadena LITERAL de la cadena canonica que se le
     mando al modelo. Si no, SE DESCARTA. Pedirlo en el prompt es una
     preferencia; verificarlo en codigo es un invariante.
  2. Quien?    -> `responsable` se coteja contra los hablantes REALES de esa
     transcripcion. Si no matchea, NO se descarta: se MARCA `sin_hablante` y
     mas adelante NO se propone como responsable de la tarea.

Sin la llave 2, un modelo puede citar textualmente "lo vemos el viernes" y
atribuirselo a alguien que no estuvo: la cita es valida, la atribucion es
inventada, y la llave 1 no lo ve.

Paridad de runtimes: este modulo NO importa ningun runner de agente. La llamada
al modelo es de UN SOLO TIRO por `copilot_bridge.invoke`, cuyo eje
(`LLM_BACKEND`) es ORTOGONAL al runtime de agente (Codex CLI / Claude Code CLI /
GitHub Copilot). Hay un gate por AST (F6 caso 9) y ademas una MATRIZ MEDIDA
(`tests/test_plan283_backend_parity.py`) que corre esto con los 5 backends y
exige salida identica.
"""
from __future__ import annotations

import json
from datetime import datetime

import config as _config
from services import egress_policies, meetings_store
from services import transcript_parser
from services.local_insights import HITL_RULES, _strip_fences

RESUMEN_MAX = 1200
TITULO_MAX = 300
CITA_MAX = 400
TEXTO_MAX = 600
MAX_PENDIENTES = 25
MAX_DECISIONES = 15
MAX_RIESGOS = 15

AGENT_TYPE = "meeting_minutes"

# Contrato JSON que se le pide al modelo, LITERAL en el prompt.
_CONTRATO = (
    '{"resumen": "...", '
    '"decisiones": [{"texto": "...", "cita": "..."}], '
    '"pendientes": [{"titulo": "...", "responsable": "...|null", '
    '"fecha_compromiso": "YYYY-MM-DD|null", "cita": "..."}], '
    '"riesgos": [{"texto": "...", "cita": "..."}]}'
)


def build_minutes_prompt(*, texto: str, subject: str, fecha_ref: datetime) -> tuple[str, str]:
    """`(system, user)`. `fecha_ref` va LITERAL en ISO para que el modelo pueda
    resolver "el viernes" sin que el codigo interprete lenguaje natural."""
    system = (
        "Sos un asistente que redacta minutas de reunion en castellano claro. "
        "Tu UNICA tarea es resumir lo que efectivamente se dijo y devolverlo en "
        "JSON estricto. No inventes participantes, compromisos ni fechas."
        + HITL_RULES
    )
    partes = [
        "== REUNION ==",
        f"asunto: {subject}",
        f"fecha_de_referencia: {fecha_ref.isoformat()}",
        "",
        "== TRANSCRIPCION ==",
        texto,
        "",
        f"Responde EXCLUSIVAMENTE con un objeto JSON (sin markdown) con esta forma: {_CONTRATO}",
        (
            "`cita` debe ser un fragmento COPIADO TAL CUAL de la transcripcion. "
            "Si no podes copiar un fragmento textual que lo respalde, NO incluyas ese item."
        ),
        (
            "`responsable` solo puede ser alguien que HABLO en la transcripcion. "
            "Si no sabes de quien es el compromiso, poné null."
        ),
        (
            "`fecha_compromiso` va en formato YYYY-MM-DD o null. Usá "
            "fecha_de_referencia para resolver expresiones como 'el viernes'."
        ),
    ]
    return system, "\n".join(partes)


def _texto_limpio(valor, tope: int) -> str:
    return str(valor or "").strip()[:tope]


def _parse_fecha(valor) -> datetime | None:
    """SOLO `YYYY-MM-DD`. Cualquier otra forma da `None`: el codigo no interpreta
    lenguaje natural (el prompt ya recibio `fecha_ref` para eso)."""
    texto = str(valor or "").strip()
    if len(texto) != 10:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        return None


def parse_minutes_response(
    text: str,
    *,
    texto_fuente: str,
    hablantes: tuple[str, ...] = (),
    aviso_truncado: str | None = None,
) -> dict:
    """Parsea, VERIFICA las dos llaves y devuelve el contrato de la minuta.

    Levanta `ValueError("json_parse_error: ...")` si la respuesta no es un JSON
    objeto. Todo lo demas degrada: un campo raro se ignora, no rompe la minuta.
    """
    crudo = _strip_fences(text)
    try:
        data = json.loads(crudo)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"json_parse_error: {exc}")
    if not isinstance(data, dict):
        raise ValueError("json_parse_error: not an object")

    fuente = texto_fuente or ""
    descartados = 0

    def _cita_valida(item: dict) -> str | None:
        """LLAVE 1 (D4). Se verifica la cita CRUDA y recien despues se recorta:
        el prefijo de una subcadena sigue siendo subcadena, pero el prefijo de
        algo inventado podria colarse por accidente."""
        cita = str(item.get("cita") or "").strip()
        if not cita or cita not in fuente:
            return None
        return cita[:CITA_MAX]

    decisiones: list[dict] = []
    for item in (data.get("decisiones") or []):
        if not isinstance(item, dict):
            continue
        cita = _cita_valida(item)
        if cita is None:
            descartados += 1
            continue
        texto_item = _texto_limpio(item.get("texto"), TEXTO_MAX)
        if texto_item:
            decisiones.append({"texto": texto_item, "cita": cita})

    riesgos: list[dict] = []
    for item in (data.get("riesgos") or []):
        if not isinstance(item, dict):
            continue
        cita = _cita_valida(item)
        if cita is None:
            descartados += 1
            continue
        texto_item = _texto_limpio(item.get("texto"), TEXTO_MAX)
        if texto_item:
            riesgos.append({"texto": texto_item, "cita": cita})

    pendientes: list[dict] = []
    sin_hablante = 0
    for item in (data.get("pendientes") or []):
        if not isinstance(item, dict):
            continue
        cita = _cita_valida(item)
        if cita is None:
            descartados += 1
            continue
        titulo = _texto_limpio(item.get("titulo"), TITULO_MAX)
        if not titulo:
            continue
        responsable = str(item.get("responsable") or "").strip() or None

        # LLAVE 2 (D9). El item NO se descarta: descartarlo seria peor, porque
        # el compromiso probablemente existe y lo que falla es la atribucion.
        # Se degrada y se marca, igual que `descartados_sin_cita`: contar y
        # mostrar, nunca borrar en silencio.
        if responsable is None:
            atribucion = "sin_responsable"
        elif transcript_parser.hablante_matchea(responsable, hablantes):
            atribucion = "confirmada"
        else:
            atribucion = "sin_hablante"
            sin_hablante += 1

        pendientes.append({
            "titulo": titulo,
            "responsable": responsable,
            "fecha_compromiso": _parse_fecha(item.get("fecha_compromiso")),
            "cita": cita,
            "atribucion": atribucion,
        })

    return {
        "resumen": _texto_limpio(data.get("resumen"), RESUMEN_MAX),
        "decisiones": decisiones[:MAX_DECISIONES],
        "pendientes": pendientes[:MAX_PENDIENTES],
        "riesgos": riesgos[:MAX_RIESGOS],
        "descartados_sin_cita": descartados,
        "sin_hablante": sin_hablante,
        "aviso_truncado": aviso_truncado,
    }


def _serializable(minuta: dict) -> dict:
    """Copia con las fechas en ISO, apta para `json.dumps` y para la pantalla."""
    salida = dict(minuta)
    salida["pendientes"] = [
        {**p, "fecha_compromiso": (
            p["fecha_compromiso"].date().isoformat() if p.get("fecha_compromiso") else None
        )}
        for p in minuta.get("pendientes", [])
    ]
    return salida


def _aviso_truncado(normalizado: dict) -> str | None:
    """K7 - nada se pierde en silencio: si se recorto algo, la minuta lo dice."""
    fuera = normalizado["turnos_totales"] - normalizado["turnos_incluidos"]
    if fuera > 0:
        return (
            f"Se analizaron {normalizado['turnos_incluidos']} de "
            f"{normalizado['turnos_totales']} intervenciones: la transcripcion supera "
            f"el maximo que se puede analizar de una vez."
        )
    if normalizado["chars"] < normalizado["chars_totales"]:
        return (
            f"Se analizaron {normalizado['chars']} de {normalizado['chars_totales']} "
            f"caracteres: la transcripcion supera el maximo que se puede analizar de una vez."
        )
    return None


def build_minutes_payload(*, meeting_id: int, project: str) -> dict:
    """Destila la minuta de una reunion ya guardada. NUNCA lanza.

    Molde: `local_insights.generate_insight_for_execution`. Devuelve siempre un
    dict con `ok` y `estado`; el estado se persiste en la reunion para que la
    pantalla sepa si ofrecer "Reintentar".

    D8 - la transcripcion NUNCA se pierde por un fallo del modelo: si `invoke`
    revienta, la reunion queda en `failed` con su transcripcion intacta.
    """
    guardada = meetings_store.get_transcript(meeting_id)
    if guardada is None:
        return {
            "ok": False, "estado": "pending", "meeting_id": meeting_id,
            "minutes": None, "detalle": "La reunion todavia no tiene transcripcion.",
        }
    crudo, _formato = guardada
    normalizado = transcript_parser.normalize_transcript(crudo)
    texto = normalizado["texto"]
    aviso = _aviso_truncado(normalizado)

    # K5 - la transcripcion es dato del operador: pasa por el filtro de salida
    # que YA existe ANTES de armar el prompt. Con allowed=False no se invoca el
    # modelo, y se dice que clase de dato lo bloqueo para que el operador decida.
    # El `model` del filtro es el MODELO configurado, no el backend: el eje
    # `LLM_BACKEND` no puede filtrarse a la salida o la matriz de paridad (los
    # 5 backends deben dar un dict IDENTICO) dejaria de cerrar.
    modelo = str(getattr(_config.config, "LLM_MODEL", "") or "")
    decision = egress_policies.check(project=project, model=modelo, context_text=texto)
    if not decision.allowed:
        meetings_store.set_minutes(meeting_id, minutes=None, state="blocked")
        return {
            "ok": False,
            "estado": "blocked",
            "meeting_id": meeting_id,
            "minutes": None,
            "clases": list(decision.blocked_classes),
            "detalle": (
                "No se envio la transcripcion: contiene datos de clase "
                f"{', '.join(decision.blocked_classes) or 'sensible'}. "
                "Editá el texto o creá una politica que lo permita."
            ),
        }

    detalle_reunion = meetings_store.get_meeting_dict(meeting_id, project=project) or {}
    subject = str(detalle_reunion.get("subject") or "Reunion")
    fecha_ref = datetime.utcnow()
    system, user = build_minutes_prompt(texto=texto, subject=subject, fecha_ref=fecha_ref)

    try:
        # Import perezoso a proposito: `copilot_bridge` arrastra el mundo, y este
        # modulo tiene que poder importarse (y testearse) sin el.
        from copilot_bridge import invoke

        respuesta = invoke(agent_type=AGENT_TYPE, system=system, user=user, on_log=_sin_log)
        minuta = parse_minutes_response(
            getattr(respuesta, "text", "") or "",
            texto_fuente=texto,
            hablantes=normalizado["hablantes"],
            aviso_truncado=aviso,
        )
    except Exception as exc:  # noqa: BLE001 - el fallo del modelo NO pierde el dato
        meetings_store.set_minutes(meeting_id, minutes=None, state="failed")
        return {
            "ok": False, "estado": "failed", "meeting_id": meeting_id, "minutes": None,
            "detalle": f"No se pudo generar la minuta: {exc}",
        }

    serializable = _serializable(minuta)
    meetings_store.set_minutes(meeting_id, minutes=serializable, state="done")
    meetings_store.replace_action_items(meeting_id, minuta["pendientes"])
    return {
        "ok": True,
        "estado": "done",
        "meeting_id": meeting_id,
        "minutes": serializable,
        "descartados_sin_cita": minuta["descartados_sin_cita"],
        "sin_hablante": minuta["sin_hablante"],
        "aviso_truncado": aviso,
        "detalle": "",
    }


def _sin_log(_nivel: str, _mensaje: str) -> None:
    """`invoke` exige un `on_log`; esta llamada es de un solo tiro y sincrona,
    asi que no hay a donde transmitir."""
    return None
