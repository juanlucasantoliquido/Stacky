"""discrimination_prover.py — Una asercion que no puede fallar no es una asercion.

LEY (Plan 241 F2): un criterio solo cuenta como `verified` si su asercion viene
con un CONTROL NEGATIVO: el valor/estado PRE-FIX contra el cual la MISMA
asercion da `fail`. La comprobacion es puramente LOGICA (se evalua el oraculo
contra el control negativo con el mismo `_evaluate_deterministic`): NO abre el
navegador ni toca la app => barata, determinista e identica en los 3 runtimes.

Esto es *mutation testing* aplicado al ORACULO, no al codigo: no preguntamos
"¿el test paso?" sino "¿este test SABRIA fallar?".

CASO QUE ORIGINO EL MODULO (ADO-367, 2026-07-25): el criterio decia "el campo
Poliza admite hasta 50 caracteres" (el bug truncaba a 20) y el test generado
llenaba `VM12-P-1816961389-60`, que mide EXACTAMENTE 20 caracteres. Ese test
pasa igual con el bug presente.
"""
from __future__ import annotations

import re

# Kinds con umbral/valor concreto: sin control negativo, su PASS no prueba nada.
_REQUIRE_DISCRIMINATION = frozenset({
    "maxlength", "value", "catalog", "absence", "ordering", "color",
})
# `presence` y `no_error` NO lo requieren: su control negativo es trivialmente el
# estado contrario (el elemento ausente / la consola con errores) y ya lo cubre
# el evaluador.
_NO_DISCRIMINATION_NEEDED = frozenset({"presence", "no_error"})

_CODE_OK = ""
_CODE_NONE = "NO_DISCRIMINATION"
_CODE_FAILED = "DISCRIMINATION_FAILED"

# "truncaba a 20", "trunca en 20", "solo permite 20", "maximo actual 20"
_PREFIX_NUM_RES = (
    re.compile(r"trunc\w*\s+(?:a|en|hasta)?\s*(\d{1,4})", re.I),
    re.compile(r"solo\s+(?:permite|admite|acepta|deja)\s+(?:hasta\s+)?(\d{1,4})", re.I),
    re.compile(r"m[aá]ximo\s+(?:actual|real|previo)\s*(?:de|=|:)?\s*(\d{1,4})", re.I),
    re.compile(r"limitad[oa]\s+a\s+(\d{1,4})", re.I),
)
# "Hoy solo ofrece No Identificado, Fijo, Movil y Trabajo."
_PREV_LIST_RE = re.compile(
    r"(?:solo|s[oó]lo)\s+(?:ofrece|muestra|incluye|tiene|lista|contiene)\s*:?\s*"
    r"([^.;]{3,200})",
    re.I,
)
# "Comportamiento observado: el campo queda vacio"
_OBSERVED_RE = re.compile(
    r"comportamiento\s+observado\s*[:\-]\s*([^.;]{2,120})", re.I)
# "aparece 3 veces", "se repite 2 veces"
_PREV_COUNT_RE = re.compile(r"(?:aparece|se\s+repite|figura)\s+(\d{1,3})\s+veces", re.I)


def requires_discrimination(kind: str) -> bool:
    """True para los kinds con umbral/valor concreto. NUNCA lanza."""
    k = str(kind or "").strip().lower()
    if k in _NO_DISCRIMINATION_NEEDED:
        return False
    return k in _REQUIRE_DISCRIMINATION


def _criterion_corpus(criterion: dict) -> str:
    """Todo el texto del ticket disponible para buscar el estado pre-fix."""
    parts = []
    for key in ("text", "descripcion", "observed", "comportamiento_observado",
                "repro_text", "detail"):
        val = (criterion or {}).get(key)
        if isinstance(val, str) and val:
            parts.append(val)
        elif isinstance(val, (list, tuple)):
            parts.extend(str(v) for v in val)
    return " ".join(parts)


def negative_control_for(criterion: dict, assertion: dict):
    """Deriva el control negativo del texto del criterio. NUNCA lanza.

    Reglas EXACTAS por kind:
      maxlength : el valor PRE-FIX citado en el ticket ("truncaba a 20" -> "20");
                  si el ticket no lo cita, str(int(expected) // 2) con
                  `fuente: "derivado"`.
      catalog   : la lista de opciones PREVIAS citadas ("solo ofrece No
                  Identificado, Fijo, Movil y Trabajo") -> el token esperado NO
                  esta en ella. Sin cita: catalogo vacio, `derivado`.
      absence   : el conteo PREVIO (duplicado) -> 2.
      ordering  : el orden inverso.
      value/color: el valor observado ("Comportamiento observado: ...").
                  SIN cita NO se inventa: devuelve None.
    Devuelve {"valor": <control>, "fuente": "ticket"|"derivado"} o None.
    """
    try:
        criterion = criterion if isinstance(criterion, dict) else {}
        assertion = assertion if isinstance(assertion, dict) else {}
        kind = str(criterion.get("kind") or "").strip().lower()
        corpus = _criterion_corpus(criterion)

        explicit = criterion.get("negative_control")
        if explicit not in (None, ""):
            return {"valor": explicit, "fuente": "ticket"}

        if kind == "maxlength":
            expected = str(assertion.get("valor") or criterion.get("expected") or "")
            for rx in _PREFIX_NUM_RES:
                m = rx.search(corpus)
                if m and m.group(1) != expected:
                    return {"valor": m.group(1), "fuente": "ticket"}
            if expected.isdigit() and int(expected) > 1:
                return {"valor": str(int(expected) // 2), "fuente": "derivado"}
            return None

        if kind == "catalog":
            m = _PREV_LIST_RE.search(corpus)
            if m:
                return {"valor": m.group(1).strip(), "fuente": "ticket"}
            return {"valor": "", "fuente": "derivado"}

        if kind == "absence":
            m = _PREV_COUNT_RE.search(corpus)
            if m and m.group(1) != str(assertion.get("valor")):
                return {"valor": int(m.group(1)), "fuente": "ticket"}
            return {"valor": 2, "fuente": "derivado"}

        if kind == "ordering":
            direccion = str(assertion.get("valor") or "asc").strip().lower()
            # Lista concreta EN EL ORDEN CONTRARIO al esperado.
            inverso = ["b", "a"] if direccion != "desc" else ["a", "b"]
            return {"valor": inverso, "fuente": "derivado"}

        if kind in ("value", "color"):
            m = _OBSERVED_RE.search(corpus)
            if m:
                return {"valor": m.group(1).strip(), "fuente": "ticket"}
            return None

        return None
    except Exception:  # noqa: BLE001 — NUNCA lanza
        return None


def prove(assertion: dict, criterion: dict) -> dict:
    """{"proven": bool, "negative_control": <valor|None>, "code": str,
        "detail": str, "fuente": str}. NUNCA lanza.

    proven=True SOLO si `_evaluate_deterministic(tipo, expected, control)`
    devuelve "fail". Si devuelve "pass" => la asercion NO discrimina =>
    code DISCRIMINATION_FAILED (es un BUG DEL TEST, no del desarrollo).
    Sin control negativo => code NO_DISCRIMINATION.
    """
    out = {"proven": False, "negative_control": None, "code": _CODE_NONE,
           "detail": "", "fuente": ""}
    try:
        assertion = assertion if isinstance(assertion, dict) else {}
        criterion = criterion if isinstance(criterion, dict) else {}
        kind = str(criterion.get("kind") or "").strip().lower()

        if not requires_discrimination(kind):
            out.update({
                "proven": True, "code": _CODE_OK,
                "fuente": "no_aplica",
                "detail": (f"kind={kind or '?'} no requiere control negativo: su "
                           "estado contrario ya lo cubre el evaluador"),
            })
            return out

        control = negative_control_for(criterion, assertion)
        if control is None:
            out["detail"] = (
                f"el ticket no cita el estado pre-fix para kind={kind}: sin control "
                "negativo la asercion no puede demostrar que sabe fallar"
            )
            return out

        out["negative_control"] = control["valor"]
        out["fuente"] = control["fuente"]

        from uat_assertion_evaluator import _evaluate_deterministic
        tipo = str(assertion.get("tipo") or "")
        expected = assertion.get("valor")
        veredicto = _evaluate_deterministic(tipo, expected, control["valor"])

        if veredicto == "fail":
            out.update({
                "proven": True, "code": _CODE_OK,
                "detail": (f"{tipo}(esperado={expected!r}) da FAIL contra el control "
                           f"negativo {control['valor']!r} ({control['fuente']})"),
            })
            return out

        out.update({
            "proven": False, "code": _CODE_FAILED,
            "detail": (f"{tipo}(esperado={expected!r}) da {veredicto.upper()} contra el "
                       f"control negativo {control['valor']!r}: la asercion NO sabe "
                       "fallar (bug del arnes, no del desarrollo)"),
        })
        return out
    except Exception as exc:  # noqa: BLE001 — NUNCA lanza
        out["detail"] = f"prove_error:{type(exc).__name__}: {exc}"
        return out
