"""Plan 279 F2 — Maquina de estados de creacion de pipeline.

PURO: sin flask, sin config, sin IO, sin red, sin modelo. Calca la disciplina de
services/devops_action_catalog.py (dataclasses + datos + lookups).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

SESSION_VERSION = "1"
MAX_SESSION_BYTES = 8192
MAX_AUTO_RETRIES = 2

#: Los 8 estados. Cerrado: nada fuera de esta tupla es un estado valido.
PIPELINE_SESSION_STATES = (
    "intake",      # 1. recogiendo el pedido en texto libre
    "discovery",   # 2. stack y proveedor detectados, requisitos abiertos
    "draft",       # 3. hay un borrador de spec
    "review",      # 4. lint + explain + preflight corridos sobre el borrador
    "secrets",     # 5. faltan variables, identificadas POR NOMBRE
    "confirm",     # 6. esperando confirmacion explicita del operador
    "committed",   # 7. escrito en el repositorio real
    "failed",      # 8. terminal con causa declarada
)

#: Transiciones legales. Clave = origen, valor = destinos permitidos.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "intake":    ("discovery", "failed"),
    "discovery": ("draft", "secrets", "failed"),
    "draft":     ("review", "failed"),
    "review":    ("secrets", "confirm", "draft", "failed"),
    "secrets":   ("review", "confirm", "failed"),
    "confirm":   ("committed", "draft", "failed"),
    "committed": (),
    "failed":    (),
}

TERMINAL_STATES = ("committed", "failed")


#: [ADICION ARQUITECTO] Nombre del archivo que la escritura va a crear, por proveedor.
#: Es la MISMA convencion que ya usa api/pipeline_generator.py:
#:   path = "azure-pipelines.yml" if target == "ado" else ".gitlab-ci.yml"
#: Cerrado: 2 proveedores. Un provider fuera de este dict NO produce hint.
PIPELINE_FILENAME: dict[str, str] = {
    "ado": "azure-pipelines.yml",
    "gitlab": ".gitlab-ci.yml",
}


@dataclass(frozen=True)
class PipelineSession:
    state: str = "intake"
    provider: str = ""            # "ado" | "gitlab" | ""
    stack: str = ""               # "python" | "node" | "dotnet" | ""
    project: str = ""
    branch: str = ""              # rama destino de la escritura
    draft_ref: str = ""           # REFERENCIA al borrador, nunca el YAML entero
    missing_variables: tuple[str, ...] = ()   # NOMBRES, jamas valores
    open_questions: tuple[str, ...] = ()
    last_action_id: str = ""
    retries: int = 0
    failure_reason: str = ""
    version: str = SESSION_VERSION


def can_transition(origen: str, destino: str) -> bool:
    """True si la transicion es legal. NUNCA lanza."""
    try:
        destinos = TRANSITIONS.get(str(origen or ""), ())
    except Exception:  # pragma: no cover - defensa, no camino esperado
        return False
    return str(destino or "") in destinos


def advance(session: PipelineSession, destino: str, **campos) -> tuple[PipelineSession, str]:
    """Devuelve (sesion_nueva, "") si la transicion es legal;
    (sesion_original, motivo) si no. NUNCA lanza."""
    try:
        origen = getattr(session, "state", "") or ""
        if origen in TERMINAL_STATES:
            return session, "estado_terminal"
        if not can_transition(origen, destino):
            return session, "transicion_ilegal"
        # Solo se aplican campos que el dataclass declara: un campo inventado no
        # puede colarse en la sesion (replace() lanzaria y perderiamos el estado).
        validos = {
            k: v for k, v in (campos or {}).items()
            if k in PipelineSession.__dataclass_fields__ and k != "state"
        }
        return replace(session, state=destino, **validos), ""
    except Exception:  # pragma: no cover - defensa: NUNCA lanza
        return session, "error_interno"


def session_to_dict(s: PipelineSession) -> dict:
    """Serializacion 1:1, json.dumps-able sin encoder custom.

    `undo_hint` NO viaja: se DERIVA de provider+branch cada vez que se necesita,
    para que no pueda quedar desfasado respecto de lo que el commit hace.
    """
    return {
        "state": s.state,
        "provider": s.provider,
        "stack": s.stack,
        "project": s.project,
        "branch": s.branch,
        "draft_ref": s.draft_ref,
        "missing_variables": list(s.missing_variables),
        "open_questions": list(s.open_questions),
        "last_action_id": s.last_action_id,
        "retries": s.retries,
        "failure_reason": s.failure_reason,
        "version": s.version,
    }


def _txt(d: dict, key: str) -> str:
    v = d.get(key, "")
    return v if isinstance(v, str) else ""


def _tup(d: dict, key: str) -> tuple[str, ...]:
    v = d.get(key)
    if not isinstance(v, (list, tuple)):
        return ()
    return tuple(str(x) for x in v)


def session_from_dict(d: dict | None) -> PipelineSession:
    """Tolerante: cualquier dict invalido devuelve PipelineSession() por defecto.
    NUNCA lanza (mismo criterio que _chat_meta en api/devops_agent.py:31-40)."""
    if not isinstance(d, dict):
        return PipelineSession()
    try:
        estado = d.get("state")
        if not isinstance(estado, str) or estado not in PIPELINE_SESSION_STATES:
            return PipelineSession()
        retries = d.get("retries", 0)
        return PipelineSession(
            state=estado,
            provider=_txt(d, "provider"),
            stack=_txt(d, "stack"),
            project=_txt(d, "project"),
            branch=_txt(d, "branch"),
            draft_ref=_txt(d, "draft_ref"),
            missing_variables=_tup(d, "missing_variables"),
            open_questions=_tup(d, "open_questions"),
            last_action_id=_txt(d, "last_action_id"),
            retries=retries if isinstance(retries, int) and not isinstance(retries, bool) else 0,
            failure_reason=_txt(d, "failure_reason"),
            version=_txt(d, "version") or SESSION_VERSION,
        )
    except Exception:  # pragma: no cover - defensa: NUNCA lanza
        return PipelineSession()


def next_question(s: PipelineSession) -> str:
    """La UNICA pregunta que falta hacer, o "" si no falta ninguna. Determinista:
    recorre open_questions en orden y devuelve la primera."""
    try:
        for q in (getattr(s, "open_questions", ()) or ()):
            texto = str(q or "").strip()
            if texto:
                return texto
    except Exception:  # pragma: no cover - defensa: NUNCA lanza
        return ""
    return ""


def undo_hint(s: PipelineSession) -> str:
    """[ADICION ARQUITECTO] Como deshacer la escritura que se esta por confirmar.

    Determinista, PURO, sin IO y sin modelo. Devuelve "" si todavia no hay nada
    que deshacer (provider o branch vacios). NUNCA lanza.

    Formato EXACTO (una sola frase, castellano, sin markdown):
      "Para deshacer: borra '<archivo>' en la rama '<branch>' del proyecto
       '<project>' (o reverti con git el commit que devuelva Stacky)."

    donde <archivo> = PIPELINE_FILENAME[s.provider]. Si el provider no esta en
    PIPELINE_FILENAME, devuelve "" (no inventa un nombre de archivo).
    """
    try:
        provider = (getattr(s, "provider", "") or "").strip()
        branch = (getattr(s, "branch", "") or "").strip()
        if not provider or not branch:
            return ""
        archivo = PIPELINE_FILENAME.get(provider)
        if not archivo:
            return ""
        project = (getattr(s, "project", "") or "").strip()
        return (
            f"Para deshacer: borra '{archivo}' en la rama '{branch}' del proyecto "
            f"'{project}' (o reverti con git el commit que devuelva Stacky)."
        )
    except Exception:  # pragma: no cover - defensa: NUNCA lanza
        return ""
