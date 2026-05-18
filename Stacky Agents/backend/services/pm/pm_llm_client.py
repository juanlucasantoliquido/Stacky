"""Cliente LLM para PM Intelligence Suite — Fase 2 (advisory only).

Única puerta de salida a LLM desde el dominio PM. Garantiza:
- Tracking automático de tokens consumidos y costo USD en `pm_ai_usage`.
- Verificación de PII pre-envío (rechaza si detecta tokens PII sin enmascarar).
- `advisory_only=True` inmutable a nivel de aplicación.

Backends soportados (vía env `STACKY_PM_LLM_BACKEND`):
- `mock`: respuestas predecibles, sin red ni API key. Para tests y evals.
- `anthropic`: Claude vía SDK oficial (`pip install anthropic` + API key).
- `copilot`: GitHub Copilot Pro vía `copilot_bridge.invoke()` reusando el
  token OAuth de `gh auth`. Cero costo adicional para usuarios Copilot Pro
  (entra en la suscripción mensual). Tokens reportados son los reales del
  API de Copilot.

Uso:

    from services.pm.pm_llm_client import call_llm, LLMCallSpec

    spec = LLMCallSpec(
        project="RSPacifico",
        agent_kind="sentiment",
        prompt_type="comment_sentiment_v1",
        model="claude-haiku-4-5",     # o "gpt-4o" si backend=copilot
        system="Eres un clasificador...",
        user="Comentario: ...",
        max_output_tokens=512,
        fixture_id=None,
    )
    result = call_llm(spec)
    # result.text, result.tokens_in, result.tokens_out, result.cost_usd
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("stacky_agents.pm.llm_client")

# Pricing en USD por 1M tokens — alineado con services/cost_estimator.py.
# Para backend=copilot el costo real al usuario es $0 (entra en la suscripción
# de Copilot Pro). Estos números son list prices de referencia para reporting:
# permiten ver "cuánto te habrías gastado si llamabas al API directo".
PRICING: dict[str, dict[str, float]] = {
    # Claude (anthropic backend o copilot con modelos Claude expuestos)
    "claude-haiku-4-5":     {"input": 1.00,  "output": 5.00},
    "claude-sonnet-4-6":    {"input": 3.00,  "output": 15.00},
    "claude-opus-4-7":      {"input": 15.00, "output": 75.00},
    "claude-3.5-sonnet":    {"input": 3.00,  "output": 15.00},
    "claude-3.7-sonnet":    {"input": 3.00,  "output": 15.00},
    # OpenAI vía Copilot
    "gpt-4o":               {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":          {"input": 0.15,  "output": 0.60},
    "o1":                   {"input": 15.00, "output": 60.00},
    "o1-mini":              {"input": 3.00,  "output": 12.00},
    # Otros expuestos por Copilot
    "gemini-2.0-flash-001": {"input": 0.10,  "output": 0.40},
    # Mock para tests
    "mock-1.0":             {"input": 0.00,  "output": 0.00},
}

# Backends válidos
_VALID_BACKENDS = {"mock", "anthropic", "copilot"}

# Patrón para detectar que el texto ya pasó por pii_masker (tokens ZZZ_PII_*)
_PII_TOKEN_RE = re.compile(r"ZZZ_PII_(EMAIL|PHONE|DNI|CUIT|CBU|CARD)_\d+")

# Patrones que NO deberían llegar nunca al LLM en input — si aparecen, falla.
_RAW_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CUIT", re.compile(r"\b\d{2}-\d{8}-\d\b")),
    ("CBU", re.compile(r"\b\d{22}\b")),
]


class PiiLeakError(RuntimeError):
    """Se detectó PII cruda en el input al LLM. Bloqueamos la llamada."""


class LLMBackendError(RuntimeError):
    """Backend no disponible o falla al invocar el modelo."""


@dataclass
class LLMCallSpec:
    project: str
    agent_kind: str           # "sentiment" | "recommendation"
    prompt_type: str          # ej. "comment_sentiment_v1"
    model: str                # claude-haiku-4-5 | claude-sonnet-4-6 | mock-1.0
    system: str
    user: str
    max_output_tokens: int = 1024
    temperature: float = 0.0
    fixture_id: str | None = None
    # Output esperado en JSON estricto — el caller puede validar después.
    expect_json: bool = True


@dataclass
class LLMCallResult:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    model: str
    backend: str
    success: bool
    error: str | None
    correlation_id: str
    usage_id: int | None = None
    parsed_json: Any = field(default=None)


# ── PII guard ──────────────────────────────────────────────────────────────────

def _ensure_no_raw_pii(text: str) -> None:
    """Bloquea la llamada si detecta patrones PII no enmascarados."""
    for kind, rx in _RAW_PII_PATTERNS:
        if rx.search(text):
            raise PiiLeakError(
                f"Input al LLM contiene PII tipo {kind} sin enmascarar. "
                f"Pasá el texto por pii_masker.mask_text() antes de llamar."
            )


# ── backends ───────────────────────────────────────────────────────────────────

def _backend_name() -> str:
    """Selecciona backend: env STACKY_PM_LLM_BACKEND tiene prioridad,
    si no usa config.LLM_BACKEND, default mock."""
    explicit = os.environ.get("STACKY_PM_LLM_BACKEND", "").strip().lower()
    if explicit in _VALID_BACKENDS:
        return explicit
    try:
        from config import config
        global_backend = (config.LLM_BACKEND or "mock").lower()
        if global_backend in _VALID_BACKENDS:
            return global_backend
        return "mock"
    except Exception:
        return "mock"


def _call_mock(spec: LLMCallSpec) -> tuple[str, int, int]:
    """Backend mock: devuelve un JSON predecible para que tests/evals sean determinísticos.

    Tokens calculados aproximación: 1 token ≈ 4 caracteres del input + del output.
    """
    tokens_in = max(1, (len(spec.system) + len(spec.user)) // 4)

    if spec.agent_kind == "sentiment":
        # Devuelve un único resultado con estructura mínima válida — útil para
        # pipelines de validación de schema y eval fixtures.
        text = (
            '{"analyzer_output_version": "1.0", "results": [{'
            '"comment_id": 1, "sentiment_label": "neutral", '
            '"sentiment_score": 0.5, "flags": [], "confidence": 0.7}], '
            '"model_used": "mock-1.0"}'
        )
    elif spec.agent_kind == "recommendation":
        text = (
            '{"rec_output_version": "1.0", "recommendations": [], '
            '"model_used": "mock-1.0", "advisory_only": true}'
        )
    else:
        text = '{"ok": true, "model_used": "mock-1.0"}'

    tokens_out = max(1, len(text) // 4)
    return text, tokens_in, tokens_out


def _call_anthropic(spec: LLMCallSpec) -> tuple[str, int, int]:
    """Llama a Claude vía SDK oficial. Requiere `anthropic` instalado + ANTHROPIC_API_KEY."""
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise LLMBackendError(
            "Backend 'anthropic' requiere `pip install anthropic`. "
            "Cambiá STACKY_PM_LLM_BACKEND=mock para tests."
        ) from e

    api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not api_key:
        raise LLMBackendError(
            "ANTHROPIC_API_KEY no está seteada. Setealo en el .env del backend "
            "o forzá STACKY_PM_LLM_BACKEND=mock."
        )

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=spec.model,
        max_tokens=spec.max_output_tokens,
        temperature=spec.temperature,
        system=spec.system,
        messages=[{"role": "user", "content": spec.user}],
    )
    # Concatenar bloques de texto
    text_parts: list[str] = []
    for block in (msg.content or []):
        if getattr(block, "type", None) == "text":
            text_parts.append(getattr(block, "text", ""))
    text = "".join(text_parts)
    usage = getattr(msg, "usage", None)
    tokens_in = getattr(usage, "input_tokens", 0) if usage else 0
    tokens_out = getattr(usage, "output_tokens", 0) if usage else 0
    return text, int(tokens_in), int(tokens_out)


def _call_copilot(spec: LLMCallSpec) -> tuple[str, int, int]:
    """Llama a Copilot Pro via `copilot_bridge.invoke()`.

    Reusa el token OAuth de `gh auth` que Stacky ya tiene configurado para
    otros agentes. Cero gasto adicional para usuarios Copilot Pro (entra en
    la suscripción mensual). Los tokens devueltos son los REALES del API
    de Copilot (campo `usage.prompt_tokens` / `completion_tokens`).

    El parámetro `temperature` del LLMCallSpec se respeta solo si el modelo
    lo soporta — copilot_bridge maneja modelos de razonamiento (o1, o3) que
    no aceptan `temperature` ni `max_tokens` y los re-mapea internamente.
    """
    try:
        import copilot_bridge  # type: ignore
    except ImportError as e:
        raise LLMBackendError(
            "Backend 'copilot' requiere copilot_bridge.py en el backend. "
            "Verificá que `Stacky Agents/backend/copilot_bridge.py` existe."
        ) from e

    # copilot_bridge.invoke expone un on_log callback; lo reemplazamos por un
    # logger silencioso porque PM persiste eventos en pm_ai_usage, no en logs.
    def _noop_log(_level: str, _msg: str) -> None:
        logger.debug("copilot_bridge: %s %s", _level, _msg)

    try:
        # IMPORTANTE: copilot_bridge.invoke despacha según config.LLM_BACKEND
        # global, NO según un argumento explícito. Para forzar el path copilot
        # cuando STACKY_PM_LLM_BACKEND=copilot pero LLM_BACKEND≠copilot,
        # llamamos directamente a _invoke_copilot.
        response = copilot_bridge._invoke_copilot(
            agent_type=spec.agent_kind,
            system=spec.system,
            user=spec.user,
            on_log=_noop_log,
            execution_id=None,
            model=spec.model,
        )
    except RuntimeError as e:
        raise LLMBackendError(f"Copilot bridge falló: {e}") from e

    text = response.text or ""
    metadata = response.metadata or {}
    tokens_in = int(metadata.get("tokens_in") or 0)
    tokens_out = int(metadata.get("tokens_out") or 0)
    return text, tokens_in, tokens_out


# ── pricing ────────────────────────────────────────────────────────────────────

def _compute_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    price = PRICING.get(model)
    if not price:
        return 0.0
    return round(
        (tokens_in / 1_000_000.0) * price["input"]
        + (tokens_out / 1_000_000.0) * price["output"],
        6,
    )


# ── core API ───────────────────────────────────────────────────────────────────

def call_llm(spec: LLMCallSpec) -> LLMCallResult:
    """Invoca al LLM, trackea tokens + costo y persiste en pm_ai_usage.

    Bloquea si detecta PII cruda. Nunca lanza excepción al caller por fallas
    de red/SDK: devuelve `success=False` con el error capturado.
    """
    correlation_id = str(uuid.uuid4())[:36]
    _ensure_no_raw_pii(spec.system)
    _ensure_no_raw_pii(spec.user)

    backend = _backend_name()
    start = time.monotonic()
    text = ""
    tokens_in = 0
    tokens_out = 0
    success = True
    error: str | None = None

    try:
        if backend == "anthropic":
            text, tokens_in, tokens_out = _call_anthropic(spec)
        elif backend == "copilot":
            text, tokens_in, tokens_out = _call_copilot(spec)
        elif backend == "mock":
            text, tokens_in, tokens_out = _call_mock(spec)
        else:
            # Backend desconocido: fallback a mock para no romper.
            backend = "mock"
            text, tokens_in, tokens_out = _call_mock(spec)
    except (LLMBackendError, Exception) as e:  # noqa: BLE001
        success = False
        error = f"{type(e).__name__}: {e}"
        logger.warning(
            "pm_llm_client: backend=%s model=%s falló: %s",
            backend, spec.model, error,
        )

    latency_ms = int((time.monotonic() - start) * 1000)
    cost_usd = _compute_cost_usd(spec.model, tokens_in, tokens_out)

    # Parse JSON si aplica
    parsed: Any = None
    if success and spec.expect_json and text:
        try:
            import json
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            success = False
            error = f"JSONDecodeError: {e}"

    usage_id = _persist_usage(
        project=spec.project,
        agent_kind=spec.agent_kind,
        prompt_type=spec.prompt_type,
        model=spec.model,
        backend=backend,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        success=success,
        error=error,
        fixture_id=spec.fixture_id,
        correlation_id=correlation_id,
    )

    return LLMCallResult(
        text=text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        model=spec.model,
        backend=backend,
        success=success,
        error=error,
        correlation_id=correlation_id,
        usage_id=usage_id,
        parsed_json=parsed,
    )


def _persist_usage(
    *,
    project: str,
    agent_kind: str,
    prompt_type: str,
    model: str,
    backend: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: int,
    success: bool,
    error: str | None,
    fixture_id: str | None,
    correlation_id: str,
) -> int | None:
    """Inserta una fila en pm_ai_usage. Devuelve el id, o None si falla la persistencia."""
    try:
        from db import session_scope
        from services.pm.models import PmAiUsage

        with session_scope() as session:
            row = PmAiUsage(
                project=project,
                agent_kind=agent_kind,
                prompt_type=prompt_type,
                model=model,
                backend=backend,
                tokens_in=int(tokens_in),
                tokens_out=int(tokens_out),
                cost_usd=float(cost_usd),
                latency_ms=int(latency_ms),
                success=bool(success),
                error=error,
                fixture_id=fixture_id,
                advisory_only=True,
                correlation_id=correlation_id,
            )
            session.add(row)
            session.flush()
            return row.id
    except Exception as e:  # noqa: BLE001
        logger.error("pm_llm_client: no pude persistir pm_ai_usage: %s", e)
        return None
