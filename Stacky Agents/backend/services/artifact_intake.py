"""V1.3 — Contrato universal de intake de outputs file-based.

Punto único de validación + reparación determinista para TODO output que entra
por archivos (no por los submit_* MCP). Da a codex (y a cualquier runtime futuro
sin MCP) la misma garantía server-side que claude obtiene de los submit_*:
nada inválido llega a ADO; nada se descarta en silencio.

Contrato:
    validate_and_normalize(*, raw, kind, ticket_context=None) -> IntakeResult

kinds:
    - "pending_task_json": repara + parsea + valida schema + regla anti-ordinal.
    - "comment_html":      valida no-vacío; sin reparaciones agresivas.

Default OFF: el cableado en el watcher está detrás de STACKY_ARTIFACT_INTAKE_ENABLED.
Reusa las reglas de schema de artifact_validator (no las duplica).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("stacky.services.artifact_intake")

_KINDS = ("pending_task_json", "comment_html")

_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*\n(.*?)\n?\s*```\s*$", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


@dataclass(frozen=True)
class IntakeResult:
    ok: bool
    normalized: dict | str | None
    repaired: bool
    repairs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "repaired": self.repaired,
            "repairs": list(self.repairs),
            "errors": list(self.errors),
        }


def validate_and_normalize(
    *,
    raw: str,
    kind: str,
    ticket_context: dict | None = None,
) -> IntakeResult:
    if kind not in _KINDS:
        raise ValueError(f"kind desconocido: {kind!r}. Válidos: {_KINDS}")
    if kind == "comment_html":
        return _intake_html(raw)
    return _intake_pending_task(raw, ticket_context or {})


# ── HTML ──────────────────────────────────────────────────────────────────────
def _intake_html(raw: str) -> IntakeResult:
    if not raw or not raw.strip():
        return IntakeResult(
            ok=False, normalized=None, repaired=False,
            errors=["comment.html vacío"],
        )
    return IntakeResult(ok=True, normalized=raw, repaired=False)


# ── pending-task.json ──────────────────────────────────────────────────────────
def _intake_pending_task(raw: str, ticket_context: dict) -> IntakeResult:
    repairs: list[str] = []
    text = raw if raw is not None else ""

    # (1) BOM
    if text.startswith("﻿"):
        text = text.lstrip("﻿")
        repairs.append("stripped_bom")

    # (2) code fences ```json ... ```
    m = _FENCE_RE.match(text.strip())
    if m:
        text = m.group(1)
        repairs.append("stripped_code_fence")

    # (3) prosa antes/después: extraer el primer objeto {...} balanceado
    extracted = _extract_balanced_object(text)
    if extracted is not None and extracted != text.strip():
        text = extracted
        repairs.append("extracted_json_object")
    else:
        text = text.strip()

    # (4) comillas tipográficas
    if any(ch in text for ch in ("“", "”", "‘", "’")):
        text = (
            text.replace("“", '"').replace("”", '"')
            .replace("‘", "'").replace("’", "'")
        )
        repairs.append("normalized_smart_quotes")

    # (5) comas finales
    if _TRAILING_COMMA_RE.search(text):
        text = _TRAILING_COMMA_RE.sub(r"\1", text)
        repairs.append("stripped_trailing_comma")

    # parse
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return IntakeResult(
            ok=False, normalized=None, repaired=bool(repairs), repairs=repairs,
            errors=[
                f"JSON inválido tras reparaciones (línea {exc.lineno}, col {exc.colno}): "
                f"{exc.msg}. Reescribí el archivo completo con JSON válido."
            ],
        )

    if not isinstance(payload, dict):
        return IntakeResult(
            ok=False, normalized=None, repaired=bool(repairs), repairs=repairs,
            errors=["el JSON raíz debe ser un objeto, no una lista/escalar"],
        )

    # schema (reusa el contrato canónico de artifact_validator)
    errors = _validate_schema(payload)
    # regla anti-ordinal (ids referenciados deben existir en el contexto real)
    errors += _validate_anti_ordinal(payload, ticket_context)

    if errors:
        return IntakeResult(
            ok=False, normalized=None, repaired=bool(repairs), repairs=repairs,
            errors=errors,
        )

    return IntakeResult(
        ok=True, normalized=payload, repaired=bool(repairs), repairs=repairs,
    )


def _validate_schema(payload: dict) -> list[str]:
    from services import artifact_validator as av

    errors: list[str] = []
    required = av._required_fields()
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"faltan campos requeridos: {', '.join(missing)}")
    status = payload.get("status")
    if status is not None and status not in av._allowed_statuses():
        errors.append(f"status '{status}' inválido; usar 'pending_manual_creation'")
    return errors


def _validate_anti_ordinal(payload: dict, ticket_context: dict) -> list[str]:
    """Si el contexto trae los ids ADO reales, los ids referenciados deben existir.

    Sin contexto de ids → no se puede chequear (skip, no inventa).
    """
    valid_ids = ticket_context.get("valid_ado_ids")
    if not valid_ids:
        return []
    valid_set = {int(x) for x in valid_ids}
    errors: list[str] = []
    for field_name in ("epic_id", "parent_id", "rf_ado_id"):
        ref = payload.get(field_name)
        if ref is None:
            continue
        try:
            ref_int = int(ref)
        except (TypeError, ValueError):
            continue
        if ref_int not in valid_set:
            errors.append(
                f"{field_name}={ref_int} no existe en el ticket; "
                f"usar el id ADO real (no un ordinal 1..N). "
                f"ids válidos: {sorted(valid_set)}"
            )
    return errors


def _extract_balanced_object(text: str) -> str | None:
    """Extrae el primer objeto JSON balanceado {...}, ignorando prosa alrededor.

    Respeta strings y escapes para no cortar dentro de un valor. None si no
    encuentra un objeto balanceado.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None
