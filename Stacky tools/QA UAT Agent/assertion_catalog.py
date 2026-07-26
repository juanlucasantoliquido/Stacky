"""assertion_catalog.py — kind de criterio -> asercion concreta (Plan 241 F1).

POR QUE EXISTE. Hasta el Plan 240 todo criterio terminaba en un oraculo de TEXTO
generico sobre la pagina. Eso produce aserciones que no discriminan: el ADO-367
("el campo Poliza admite hasta 50 caracteres", el bug truncaba a 20) genero un
test que tipeaba un valor de EXACTAMENTE 20 caracteres — pasaba igual con el bug
presente. La traduccion correcta es una asercion EXACTA sobre el DOM:
attribute_equals(#c_abfCodObligacion, maxlength, "50").

100% DETERMINISTA (parseo + matching de strings) => identico en los 3 runtimes.

(C2) REGLA DURA SOBRE `target`. El template resuelve el selector con
`ui_map[oracle.target]`: el `target` NO es un selector CSS, es una CLAVE del dict
ui_map que recibe la plantilla. Un alias inexistente emite `selector: undefined`,
el probe captura `actual = null` y el evaluador devuelve "review" => el criterio
SE PIERDE EN SILENCIO. Por eso `build_assertions` recibe el ui_map y verifica la
pertenencia del alias a sus claves; si no pertenece devuelve [] y el criterio
queda `not_verifiable` de forma VISIBLE.
"""
from __future__ import annotations

import re
import unicodedata

SUPPORTED_KINDS = ("maxlength", "catalog", "absence", "ordering", "presence",
                   "value", "color", "no_error")

# Sustantivos de UI que introducen el nombre del control en la prosa del criterio.
# "El campo Poliza admite ...", "El combo Tipo Telefono debe incluir ...".
_UI_NOUN_RE = re.compile(
    r"\b(?:campo|combo|columna|grilla|tabla|lista\s+desplegable|lista|selector|"
    r"select|boton|bot[oó]n|checkbox|check|input|filtro|chip|celda)\s+"
    r"[\"“”']?([A-Za-z0-9_ÁÉÍÓÚÜÑáéíóúüñ][A-Za-z0-9_ ÁÉÍÓÚÜÑáéíóúüñ\-]{1,39})",
    re.I,
)
_MAX_TARGET_WORDS = 5
_QUOTED_RE = re.compile(r"[\"“”']([^\"“”']{2,60})[\"“”']")
_DESC_RE = re.compile(r"\b(descendente|de\s+mayor\s+a\s+menor|desc\b|mas\s+reciente"
                      r"|m[aá]s\s+reciente)\b", re.I)
_COLUMN_IDX_RE = re.compile(r"columna\s+(\d{1,2})\b", re.I)
_CLASS_RE = re.compile(r"\bclas[es]?\s+[\"“”']?([A-Za-z0-9_\-]{2,40})", re.I)


def _norm(text) -> str:
    """Normaliza para comparar: sin acentos, solo [a-z0-9]."""
    raw = str(text or "")
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(c for c in raw if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", raw.lower())


def _alias_haystacks(alias: str, value) -> list:
    """Textos comparables de una entrada del ui_map: alias, selector y label."""
    out = [alias]
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k in ("label", "selector", "selector_recommended", "id",
                  "alias_semantic", "text"):
            v = value.get(k)
            if isinstance(v, str) and v:
                out.append(v)
    return [h for h in out if h]


def _match_alias(phrase: str, ui_map: dict):
    """Devuelve la CLAVE del ui_map que corresponde a `phrase`, o None.

    Precedencia EXACTA y determinista (gana la primera, y a igual nivel el de
    menor indice de insercion): (1) igualdad normalizada contra alias/label/id,
    (2) la frase contenida en alguno de esos textos.
    """
    target = _norm(phrase)
    if not target or len(target) < 2:
        return None
    partial = None
    for alias, value in (ui_map or {}).items():
        for hay in _alias_haystacks(alias, value):
            nh = _norm(hay)
            if not nh:
                continue
            if nh == target:
                return alias
            if partial is None and target in nh:
                partial = alias
    return partial


def _candidate_phrases(criterion: dict, kind: str) -> list:
    """Frases candidatas a nombrar el control, en orden de precedencia."""
    text = str(criterion.get("text") or "")
    phrases: list = []
    explicit = criterion.get("target_alias")
    if explicit:
        phrases.append(str(explicit))
    # (b) sustantivo de UI + nombre del control ("campo Poliza", "combo Tipo
    #     Telefono"). La prosa sigue despues del nombre ("...admite hasta 50
    #     caracteres"), asi que se prueban los prefijos de MAS a MENOS palabras:
    #     el primero que resuelva contra el ui_map gana. Determinista.
    for raw in _UI_NOUN_RE.findall(text):
        words = [w for w in str(raw).strip().split() if w]
        for n in range(min(len(words), _MAX_TARGET_WORDS), 0, -1):
            phrases.append(" ".join(words[:n]))
    # (c) literales entrecomillados del criterio
    tokens = [str(t).strip() for t in (criterion.get("tokens") or []) if str(t).strip()]
    if not tokens:
        tokens = [t.strip() for t in _QUOTED_RE.findall(text)]
    if kind == "catalog":
        # Para un catalogo los tokens son las OPCIONES esperadas, no el control:
        # solo el PRIMERO puede ser el nombre del combo.
        phrases.extend(tokens[:1])
    else:
        phrases.extend(tokens)
    seen = set()
    out = []
    for p in phrases:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_target(criterion: dict, ui_map: dict, kind: str = ""):
    """Resuelve el alias del ui_map al que apunta el criterio. None si no resuelve.

    NUNCA inventa un alias: si el explicito no es clave del ui_map devuelve None
    (ver C2 en el docstring del modulo).
    """
    ui_map = ui_map if isinstance(ui_map, dict) else {}
    explicit = criterion.get("target_alias")
    if explicit:
        return explicit if explicit in ui_map else None
    for phrase in _candidate_phrases(criterion, kind):
        alias = _match_alias(phrase, ui_map)
        if alias:
            return alias
    return None


def _expected_tokens(criterion: dict, target_alias) -> list:
    tokens = [str(t).strip() for t in (criterion.get("tokens") or []) if str(t).strip()]
    if not tokens:
        tokens = [t.strip() for t in _QUOTED_RE.findall(str(criterion.get("text") or ""))]
    # Si el primer token nombraba el control, ya no es una opcion esperada.
    if tokens and target_alias and _match_alias(tokens[0], {target_alias: target_alias}):
        tokens = tokens[1:]
    return tokens


def build_assertions(criterion: dict, ui_map: dict, screen: str) -> list:
    """Devuelve una lista de oraculos ejecutables. NUNCA lanza; [] si no puede.

    Mapa EXACTO kind -> oraculo:
      maxlength : attribute_equals(target, "maxlength", expected)   (ADO-367)
      catalog   : un contains_literal por cada token esperado       (ADO-366)
      absence   : count_eq(target, 1)                               (ADO-387)
      presence  : visible(target, True)
      ordering  : ordered_by(target, columna, "asc"|"desc")
      value     : equals(target, expected)
      color     : attribute_equals(target, "class", <clase esperada>)
      no_error  : no_console_error (sin target: es un oraculo de pagina entera)
    """
    try:
        criterion = criterion if isinstance(criterion, dict) else {}
        ui_map = ui_map if isinstance(ui_map, dict) else {}
        kind = str(criterion.get("kind") or "").strip().lower()
        if kind not in SUPPORTED_KINDS:
            return []

        text = str(criterion.get("text") or "")
        expected = criterion.get("expected")

        # no_error no necesita target: mira la consola de la pagina entera.
        if kind == "no_error":
            return [{"tipo": "no_console_error", "target": "__page__",
                     "valor": None, "criterio_id": criterion.get("id"),
                     "screen": screen}]

        target = resolve_target(criterion, ui_map, kind)
        if not target or target not in ui_map:
            return []

        base = {"target": target, "criterio_id": criterion.get("id"), "screen": screen}

        if kind == "maxlength":
            if expected in (None, ""):
                return []
            return [{**base, "tipo": "attribute_equals",
                     "atributo": "maxlength", "valor": str(expected)}]

        if kind == "catalog":
            tokens = _expected_tokens(criterion, target)
            return [{**base, "tipo": "contains_literal", "valor": tok}
                    for tok in tokens]

        if kind == "absence":
            return [{**base, "tipo": "count_eq", "valor": 1}]

        if kind == "presence":
            return [{**base, "tipo": "visible", "valor": True}]

        if kind == "ordering":
            m = _COLUMN_IDX_RE.search(text)
            columna = int(m.group(1)) if m else 1
            direccion = "desc" if _DESC_RE.search(text) else "asc"
            return [{**base, "tipo": "ordered_by",
                     "columna": columna, "valor": direccion}]

        if kind == "value":
            if expected in (None, ""):
                tokens = _expected_tokens(criterion, target)
                if not tokens:
                    return []
                expected = tokens[0]
            return [{**base, "tipo": "equals", "valor": str(expected)}]

        if kind == "color":
            m = _CLASS_RE.search(text)
            if not m:
                return []
            return [{**base, "tipo": "attribute_equals",
                     "atributo": "class", "valor": m.group(1)}]

        return []
    except Exception:  # noqa: BLE001 — NUNCA lanza: sin oraculo, not_verifiable visible
        return []
