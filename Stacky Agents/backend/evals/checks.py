"""Plan 168 F2 — Checks deterministas del arnés de fitness (§4.3).

Chequeos SIN LLM: contains/not_contains/regex/min_len/max_len/json_valid/
artifact_contract. `run_check` NUNCA lanza (un patrón regex inválido devuelve
ok=False con detalle, no excepción); `validate_check_spec` sí lanza al validar
la definición de un caso (ValueError con kind/campo).
"""
from __future__ import annotations

import json
import re

VALID_CHECK_KINDS = (
    "contains", "not_contains", "regex", "min_len", "max_len",
    "json_valid", "artifact_contract",
)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_check_spec(spec: dict) -> None:
    """Valida la DEFINICIÓN de un check. ValueError("unknown_check_kind:<kind>")
    si el kind no existe; ValueError("invalid_check:<campo>") si falta/es
    inválido un parámetro obligatorio."""
    if not isinstance(spec, dict):
        raise ValueError("invalid_check:spec")
    kind = spec.get("kind")
    if kind not in VALID_CHECK_KINDS:
        raise ValueError(f"unknown_check_kind:{kind}")
    if kind in ("contains", "not_contains"):
        if not isinstance(spec.get("value"), str) or not spec.get("value"):
            raise ValueError("invalid_check:value")
    elif kind == "regex":
        if not isinstance(spec.get("pattern"), str) or not spec.get("pattern"):
            raise ValueError("invalid_check:pattern")
    elif kind in ("min_len", "max_len"):
        if not _is_int(spec.get("value")):
            raise ValueError("invalid_check:value")
    elif kind == "artifact_contract":
        if not isinstance(spec.get("agent_type"), str) or not spec.get("agent_type"):
            raise ValueError("invalid_check:agent_type")


def run_check(spec: dict, text: str) -> dict:
    """Corre un check sobre `text`. Devuelve {"kind","ok","detail"}. NUNCA lanza."""
    kind = spec.get("kind")
    text = text or ""

    if kind == "contains":
        value = str(spec.get("value", ""))
        cs = bool(spec.get("case_sensitive", False))
        ok = (value in text) if cs else (value.casefold() in text.casefold())
        return {"kind": kind, "ok": ok, "detail": ("presente" if ok else f"no contiene: {value!r}")}

    if kind == "not_contains":
        value = str(spec.get("value", ""))
        cs = bool(spec.get("case_sensitive", False))
        present = (value in text) if cs else (value.casefold() in text.casefold())
        return {"kind": kind, "ok": not present, "detail": (f"contiene (prohibido): {value!r}" if present else "ausente")}

    if kind == "regex":
        pattern = spec.get("pattern", "")
        try:
            match = re.search(pattern, text, re.MULTILINE)
        except re.error as exc:
            return {"kind": kind, "ok": False, "detail": f"regex_invalida: {exc}"}
        ok = match is not None
        return {"kind": kind, "ok": ok, "detail": ("match" if ok else f"sin match: {pattern}")}

    if kind == "min_len":
        value = spec.get("value")
        if not _is_int(value):
            return {"kind": kind, "ok": False, "detail": "min_len sin value entero"}
        ok = len(text) >= value
        return {"kind": kind, "ok": ok, "detail": f"len={len(text)} min={value}"}

    if kind == "max_len":
        value = spec.get("value")
        if not _is_int(value):
            return {"kind": kind, "ok": False, "detail": "max_len sin value entero"}
        ok = len(text) <= value
        return {"kind": kind, "ok": ok, "detail": f"len={len(text)} max={value}"}

    if kind == "json_valid":
        try:
            json.loads(text)
            return {"kind": kind, "ok": True, "detail": "json válido"}
        except Exception as exc:  # noqa: BLE001 — cualquier error de parseo => no válido
            return {"kind": kind, "ok": False, "detail": f"json inválido: {str(exc)[:120]}"}

    if kind == "artifact_contract":
        agent_type = str(spec.get("agent_type", ""))
        min_score = spec.get("min_score", 0)
        if not _is_int(min_score):
            min_score = 0
        must_pass = bool(spec.get("must_pass", True))
        try:
            import contract_validator  # lazy (módulo top-level de backend/)

            result = contract_validator.validate(agent_type, text)
        except Exception as exc:  # noqa: BLE001 — nunca tumbar la corrida
            return {"kind": kind, "ok": False, "detail": f"contrato_error: {str(exc)[:120]}"}
        ok = result.score >= min_score and (result.passed if must_pass else True)
        return {
            "kind": kind, "ok": ok,
            "detail": f"score={result.score} min={min_score} passed={result.passed}",
        }

    return {"kind": kind, "ok": False, "detail": f"unknown_check_kind:{kind}"}


def run_checks(specs: list[dict], text: str) -> list[dict]:
    return [run_check(spec, text) for spec in (specs or [])]
