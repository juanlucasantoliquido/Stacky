"""services/gitlab_hierarchy.py — Plan 277 F1. El contrato de jerarquía de GitLab.

UN SOLO MOTOR. Antes de este módulo había CUATRO lecturas de `type::` con tres
reglas de normalización distintas y cero tests que las compararan:
  - services/gitlab_provider.py:102-111   (primer label del array; orden NO garantizado)
  - services/migrator_verify.py:69-77     (regex type::(\\w+); pierde `type::user story`)
  - services/migrator_epics.py:62         (escribe "type::epic")
  - services/incident_context.py:240      (substring de "epic" a secas: NI SIQUIERA
                                           mira el prefijo, así que `epic::42` -que
                                           marca a un HIJO- le daba True)

FUNCIONES PURAS. Este módulo NO hace I/O: ni HTTP, ni BD, ni lectura de la
configuración. Es la condición que hace que su test corra igual en los 3
runtimes y en CI sin red.

El contrato, escrito una sola vez (§3.3):
    type::<tipo>   en el ITEM   ->  qué es este ticket
    epic::<iid>    en el HIJO   ->  de qué ticket cuelga (iid DENTRO del proyecto)
"""
from __future__ import annotations

import re
import unicodedata

PREFIJO_TIPO: str = "type::"
PREFIJO_PADRE: str = "epic::"

# token de etiqueta -> valor de Ticket.work_item_type (String(40))
TIPOS_CANONICOS: dict[str, str] = {
    "epic":           "Epic",
    "funcional":      "Funcional",
    "tecnico":        "Tecnico",
    "implementacion": "Implementacion",
    "bug":            "Bug",
    "task":           "Task",
    "feature":        "Feature",
    "issue":          "Issue",
}

# campo nativo REST `type`/`issue_type` (GitLab >= 15.2, disponible en Free)
# -> work_item_type. `issue` NO está: es el default de GitLab y no es una afirmación.
TIPOS_NATIVOS: dict[str, str] = {
    "task":      "Task",
    "incident":  "Bug",
    "test_case": "Task",
}

TIPO_POR_DEFECTO: str = "Issue"
_MAX_TIPO: int = 40          # Ticket.work_item_type es String(40) — models.py:55

_SEPARADORES = re.compile(r"[\s\-]+")


def normalizar_token(valor: str | None) -> str:
    """'  Implementación ' -> 'implementacion'. ASCII, minúscula, sin espacios.

    Regla 1 del contrato (§3.3): los tokens no llevan acentos ni espacios porque
    `migrator_verify.py:70` los parsea con `type::(\\w+)`, que no matchea espacios,
    y porque `create_item` (gitlab_provider.py:314) hoy escribe el item_type crudo.
    Espacios y guiones colapsan a '_'; los acentos se pliegan a ASCII vía NFKD.
    """
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = texto.strip().lower()
    return _SEPARADORES.sub("_", texto)


def etiqueta_de_tipo(work_item_type: str | None) -> str:
    """'Análisis Funcional' -> 'type::analisis_funcional'. Nunca devuelve vacío.

    Si no hay señal cae en TIPO_POR_DEFECTO: escribir 'type::' pelado en GitLab
    crea una etiqueta basura que después ninguna lectura sabe interpretar.
    """
    token = normalizar_token(work_item_type) or normalizar_token(TIPO_POR_DEFECTO)
    return f"{PREFIJO_TIPO}{token[:_MAX_TIPO]}"


def etiqueta_de_padre(parent_iid: int | str) -> str:
    """123 -> 'epic::123'. Levanta ValueError si no es un entero positivo.

    Regla 4 del contrato: va el iid, NUNCA el título. El título se renombra;
    el iid no.
    """
    try:
        iid = int(str(parent_iid).strip())
    except (TypeError, ValueError):
        raise ValueError(f"parent_iid no es un entero: {parent_iid!r}") from None
    if iid <= 0:
        raise ValueError(f"parent_iid debe ser positivo, no {iid}")
    return f"{PREFIJO_PADRE}{iid}"


def _como_lista(labels: list[str] | str | None) -> list[str]:
    """Acepta list[str] o el string separado por comas (migrator_verify.py:46-47)."""
    if labels is None:
        return []
    if isinstance(labels, str):
        crudas = labels.split(",")
    elif isinstance(labels, (list, tuple, set, frozenset)):
        crudas = list(labels)
    else:
        return []
    limpias = []
    for cruda in crudas:
        if cruda is None:
            continue
        texto = str(cruda).strip()
        if texto:
            limpias.append(texto)
    return limpias


def _tokens_de_tipo(labels: list[str] | str | None) -> list[str]:
    """Todos los tokens `type::` presentes, normalizados. Sin valor => se descarta."""
    tokens = []
    for etiqueta in _como_lista(labels):
        if not etiqueta.lower().startswith(PREFIJO_TIPO):
            continue
        token = normalizar_token(etiqueta[len(PREFIJO_TIPO):])
        if token:
            tokens.append(token)
    return tokens


def _iids_de_padre(labels: list[str] | str | None) -> list[int]:
    """Todos los iid `epic::` válidos. Lo no entero o <= 0 se descarta, no revienta."""
    iids = []
    for etiqueta in _como_lista(labels):
        if not etiqueta.lower().startswith(PREFIJO_PADRE):
            continue
        try:
            iid = int(etiqueta[len(PREFIJO_PADRE):].strip())
        except (TypeError, ValueError):
            continue
        if iid > 0:
            iids.append(iid)
    return iids


def _tipo_desde_token(token: str) -> str:
    """Token normalizado -> work_item_type. Regla 5: lo desconocido NO se descarta."""
    canonico = TIPOS_CANONICOS.get(token)
    if canonico:
        return canonico
    return token.replace("_", " ").title()[:_MAX_TIPO]


def tipo_desde_labels(labels: list[str] | str | None) -> str | None:
    """Devuelve el work_item_type según la etiqueta `type::`, o None si no hay.

    DETERMINISTA (regla 2 del contrato): si hay MÁS DE UNA etiqueta `type::`,
    gana la primera en ORDEN ALFABÉTICO del token — nunca "la primera del array",
    porque el orden de `labels` que devuelve la API de GitLab no está garantizado
    y hace la clasificación distinta entre dos corridas idénticas.

    Acepta list[str] o el string separado por comas (el migrador lo pasa así,
    migrator_verify.py:46-47). Un token fuera de TIPOS_CANONICOS NO se descarta:
    se devuelve capitalizado y truncado a 40 (regla 5).
    """
    tokens = _tokens_de_tipo(labels)
    if not tokens:
        return None
    return _tipo_desde_token(sorted(tokens)[0])


def padre_desde_labels(labels: list[str] | str | None) -> int | None:
    """Devuelve el iid del padre según `epic::<iid>`, o None.

    Si hay más de una, gana el iid MENOR (determinismo, mismo motivo que arriba)
    y se deja constancia en el warning del llamador. Un valor no entero o <= 0
    se ignora (devuelve None) en vez de reventar.
    """
    iids = _iids_de_padre(labels)
    return min(iids) if iids else None


def clasificar_issue(body: dict) -> dict:
    """El payload crudo de un issue de GitLab -> el veredicto del contrato.

    Returns:
        {
          "work_item_type": str,                  # nunca vacío; TIPO_POR_DEFECTO si no hay señal
          "parent_iid": int | None,               # SOLO de la etiqueta epic:: (ver §3.2)
          "parent_native_epic_iid": int | None,   # del `epic` de Premium; NO va a parent_ado_id
          "origen_tipo": str,                     # "label" | "nativo" | "defecto"
          "origen_padre": str,                    # "label" | "ninguno"
          "avisos": list[str],                    # multi-tipo, multi-padre, token desconocido
        }

    PRECEDENCIA (§3.2), sin excepciones:
      tipo:  etiqueta type::  >  campo nativo type/issue_type  >  TIPO_POR_DEFECTO
      padre: etiqueta epic::  >  None
    El `epic` nativo NO entra en parent_iid: su iid vive en el namespace del GRUPO
    y parent_ado_id se compara contra Ticket.ado_id, que lleva el iid del issue
    dentro del PROYECTO. Escribirlo ahí produce un padre que nunca machea y tapa
    la causa real. Se conserva aparte para diagnóstico y deep-link (epic_url).
    """
    datos = body if isinstance(body, dict) else {}
    labels = datos.get("labels")
    avisos: list[str] = []

    # ── tipo ────────────────────────────────────────────────────────────────
    tokens = sorted(_tokens_de_tipo(labels))
    if tokens:
        ganador = tokens[0]
        work_item_type = _tipo_desde_token(ganador)
        origen_tipo = "label"
        if len(tokens) > 1:
            avisos.append(
                f"multi-tipo: {len(tokens)} etiquetas '{PREFIJO_TIPO}' ({', '.join(tokens)}); "
                f"gana '{ganador}' por orden alfabético"
            )
        if ganador not in TIPOS_CANONICOS:
            avisos.append(
                f"tipo desconocido: '{ganador}' no es canónico; se guarda como '{work_item_type}'"
            )
    else:
        nativo = datos.get("type") or datos.get("issue_type")
        token_nativo = normalizar_token(nativo) if isinstance(nativo, str) else ""
        if token_nativo in TIPOS_NATIVOS:
            work_item_type = TIPOS_NATIVOS[token_nativo]
            origen_tipo = "nativo"
        else:
            # Incluye `type == "issue"`: es el default de GitLab, no una afirmación.
            work_item_type = TIPO_POR_DEFECTO
            origen_tipo = "defecto"

    # ── padre: SOLO la etiqueta epic:: ──────────────────────────────────────
    iids = _iids_de_padre(labels)
    if iids:
        parent_iid = min(iids)
        origen_padre = "label"
        if len(iids) > 1:
            avisos.append(
                f"multi-padre: {len(iids)} etiquetas '{PREFIJO_PADRE}' "
                f"({', '.join(str(i) for i in sorted(iids))}); gana el menor ({parent_iid})"
            )
    else:
        parent_iid = None
        origen_padre = "ninguno"

    # ── epic nativo de Premium: se conserva APARTE, nunca como parent_iid ───
    parent_native_epic_iid = None
    epic = datos.get("epic")
    if isinstance(epic, dict):
        try:
            crudo = int(epic.get("iid"))
        except (TypeError, ValueError):
            crudo = 0
        if crudo > 0:
            parent_native_epic_iid = crudo

    return {
        "work_item_type": work_item_type,
        "parent_iid": parent_iid,
        "parent_native_epic_iid": parent_native_epic_iid,
        "origen_tipo": origen_tipo,
        "origen_padre": origen_padre,
        "avisos": avisos,
    }
