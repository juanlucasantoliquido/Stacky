"""test_data_forge.py — Valores de prueba que cruzan el umbral (Plan 241 F3).

POR QUE. El ADO-367 fallo aqui: el criterio decia "el campo Poliza admite hasta
50 caracteres" (el bug truncaba a 20) y el test uso el literal del ticket
`VM12-P-1816961389-60`, que mide EXACTAMENTE 20 caracteres. Ese dato NO cruza el
umbral: el test pasa igual con el bug presente.

100% DETERMINISTA: cero random. El mismo criterio produce SIEMPRE el mismo valor
=> el spec generado es identico en los 3 runtimes y la suite golden (F9) es
reproducible.

OJO: este modulo se llama test_data_forge y NO empieza con `test_`, asi que
pytest no lo colecta como archivo de tests (su prefijo es "test_data_", no
"test_"). El archivo de tests que lo cubre es tests/unit/test_plan241_test_data_forge.py.
"""
from __future__ import annotations

import re

# Alfabeto de relleno determinista: seguro para inputs de texto de AgendaWeb
# (sin espacios, sin acentos, sin comillas).
_FILL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_QUOTED_RE = re.compile(r"[\"“”']([^\"“”']{2,60})[\"“”']")


def _pad_to(seed: str, length: int) -> str:
    """Extiende/recorta `seed` a EXACTAMENTE `length` chars, sin aleatoriedad."""
    if length <= 0:
        return ""
    base = re.sub(r"[^A-Za-z0-9\-]", "", str(seed or "")) or "X"
    if len(base) >= length:
        return base[:length]
    out = list(base)
    i = 0
    while len(out) < length:
        out.append(_FILL_ALPHABET[i % len(_FILL_ALPHABET)])
        i += 1
    return "".join(out)


def _literal_of(criterion: dict):
    tokens = [str(t).strip() for t in (criterion.get("tokens") or []) if str(t).strip()]
    if tokens:
        return tokens[0]
    quoted = _QUOTED_RE.findall(str(criterion.get("text") or ""))
    return quoted[0].strip() if quoted else None


def forge(criterion: dict) -> dict:
    """{"positivo": str|None, "negativo": str|None, "rationale": str}. NUNCA lanza.

    Reglas EXACTAS por kind:
      maxlength: positivo = cadena de longitud int(expected) EXACTA, construida a
                 partir del literal del ticket y rellenada con [A-Z0-9-]
                 deterministas; negativo = cadena de longitud
                 (control_negativo + 1), que el campo PRE-FIX habria rechazado.
                 (ADO-367: positivo de 50 chars, negativo de 21 => discrimina)
      value    : positivo = expected literal.
      catalog  : positivo = el primer token esperado.
      resto    : positivo = el literal entrecomillado del criterio, si existe.
    `rationale` explica en una linea POR QUE ese valor discrimina (va a la evidencia).
    """
    out = {"positivo": None, "negativo": None, "rationale": ""}
    try:
        criterion = criterion if isinstance(criterion, dict) else {}
        kind = str(criterion.get("kind") or "").strip().lower()
        expected = criterion.get("expected")
        literal = _literal_of(criterion)

        if kind == "maxlength":
            if expected is None or not str(expected).strip().isdigit():
                out["rationale"] = (
                    "sin `expected` numerico no hay umbral que cruzar: el criterio no "
                    "puede forjar un dato discriminante y queda not_verifiable"
                )
                return out
            limite = int(str(expected).strip())
            out["positivo"] = _pad_to(literal or "QAUAT", limite)
            try:
                from discrimination_prover import negative_control_for
                control = negative_control_for(
                    criterion, {"tipo": "attribute_equals", "valor": str(limite)})
            except Exception:  # noqa: BLE001
                control = None
            prev = None
            if control and str(control.get("valor")).strip().isdigit():
                prev = int(str(control["valor"]).strip())
            if prev is None:
                prev = max(1, limite // 2)
            out["negativo"] = _pad_to(literal or "QAUAT", prev + 1)
            out["rationale"] = (
                f"positivo de {limite} chars = el umbral EXACTO del criterio; negativo "
                f"de {prev + 1} chars supera el maximo pre-fix ({prev}), asi que el "
                "campo con el bug lo habria truncado => la asercion sabe fallar"
            )
            return out

        if kind == "value":
            if expected in (None, ""):
                out["positivo"] = literal
                out["rationale"] = (
                    "sin `expected` se usa el literal entrecomillado del criterio como "
                    "valor esperado" if literal else
                    "el criterio no declara ni `expected` ni un literal entrecomillado: "
                    "no hay valor concreto que forjar"
                )
                return out
            out["positivo"] = str(expected)
            out["rationale"] = (
                f"el criterio declara el valor esperado {expected!r}: se tipea tal cual "
                "para que la comparacion sea exacta"
            )
            return out

        if kind == "catalog":
            tokens = [str(t).strip() for t in (criterion.get("tokens") or []) if str(t).strip()]
            out["positivo"] = tokens[0] if tokens else literal
            out["rationale"] = (
                "la opcion esperada del catalogo se selecciona literalmente: si el "
                "catalogo no la ofrece, la asercion falla"
            )
            return out

        out["positivo"] = literal
        out["rationale"] = (
            f"kind={kind or '?'}: se usa el literal del criterio ({literal!r}) como dato "
            "de prueba" if literal else
            f"kind={kind or '?'}: el criterio no aporta un literal concreto; el "
            "escenario se limita a navegacion + llegada"
        )
        return out
    except Exception as exc:  # noqa: BLE001 — NUNCA lanza
        out["rationale"] = f"forge_error:{type(exc).__name__}: {exc}"
        return out
