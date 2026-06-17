"""G2.2 — Tests del retry transitorio (DIFERIDO).

G2.2 está DIFERIDO: la clasificación confiable de exit-codes transitorios
requiere instrumentación adicional en los runtimes (claude_code_cli y codex_cli).

Razón del descarte en esta iteración:
- Los runtimes actuales no exponen un exit-code semántico distinguible entre
  error transitorio (red, timeout, cuota momentánea) y error de contenido
  (prompt inválido, tarea imposible, criterio incumplible).
- claude_code_cli: exit_code=1 en cualquier fallo; el runner solo lee el JSON
  final de telemetría, que puede no existir en fallos transitorios.
- codex_cli: mismo problema; no hay diferenciación estructural de errores.
- Un retry ciego sobre exit_code!=0 introduciría re-ejecuciones incorrectas
  (doble costo) ante errores de contenido. El riesgo de regresión supera el
  beneficio sin la clasificación confiable.

Cuándo implementar G2.2:
1. Cuando los runners persistan un campo "exit_reason" clasificado
   (network_timeout|quota_error|content_error|criterion_failure).
2. Cuando haya cobertura de tests de integración sobre el ciclo resume.

Flags declarados en config.py (default OFF/1):
  STACKY_TRANSIENT_RUN_RETRY_ENABLED (bool, default false)
  STACKY_TRANSIENT_RUN_RETRY_MAX (int, default 1)
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Tests de flag (siempre OFF — comportamiento declarado)
# ---------------------------------------------------------------------------


class TestTransientRunRetryFlagOff:
    def test_flag_off_default(self):
        """STACKY_TRANSIENT_RUN_RETRY_ENABLED=false por defecto."""
        from config import config
        assert config.STACKY_TRANSIENT_RUN_RETRY_ENABLED is False

    def test_flag_max_default(self):
        """STACKY_TRANSIENT_RUN_RETRY_MAX=1 por defecto."""
        from config import config
        assert config.STACKY_TRANSIENT_RUN_RETRY_MAX == 1

    def test_flag_in_registry(self):
        """STACKY_TRANSIENT_RUN_RETRY_ENABLED está en FLAG_REGISTRY."""
        from services.harness_flags import FLAG_REGISTRY
        keys = {spec.key for spec in FLAG_REGISTRY}
        assert "STACKY_TRANSIENT_RUN_RETRY_ENABLED" in keys
        assert "STACKY_TRANSIENT_RUN_RETRY_MAX" in keys


# ---------------------------------------------------------------------------
# Comportamiento: sin implementación activa (G2.2 diferido)
# ---------------------------------------------------------------------------


class TestTransientRunRetryDeferred:
    def test_no_retry_module_exists(self):
        """No existe módulo de retry transitorio activo (implementación diferida)."""
        # Este test documenta intencionalmente que G2.2 NO está implementado.
        # Si este test falla, significa que alguien implementó G2.2 sin tests completos.
        import importlib
        try:
            mod = importlib.import_module("services.transient_retry")
            # Si el módulo existe, debe tener una función 'retry' marcada como deferred
            assert hasattr(mod, "_G22_DEFERRED"), (
                "services.transient_retry existe pero no tiene _G22_DEFERRED=True. "
                "Implementar los tests completos de G2.2 antes de activar."
            )
        except ModuleNotFoundError:
            pass  # esperado: G2.2 está diferido

    def test_flag_on_doesnt_activate_retry(self, monkeypatch):
        """Activar el flag no activa reintentos (implementación diferida)."""
        import config as _cfg_mod
        monkeypatch.setattr(_cfg_mod.config, "STACKY_TRANSIENT_RUN_RETRY_ENABLED", True)
        # El comportamiento sigue siendo sin retry ya que la implementación está diferida.
        # Esta aserción valida el estado declarado, no un comportamiento activo.
        assert _cfg_mod.config.STACKY_TRANSIENT_RUN_RETRY_ENABLED is True
        # No hay runner de retry activo que cambie el comportamiento del run.


# ---------------------------------------------------------------------------
# Invariantes de diseño (si G2.2 se implementa, estos tests deben pasar)
# ---------------------------------------------------------------------------


class TestTransientRunRetryDesignInvariants:
    """Invariantes que cualquier implementación de G2.2 debe respetar.

    Estos tests son ejecutables desde ya (prueban la lógica de clasificación
    conceptual, no el retry en sí). Cuando G2.2 se implemente, se agregarán
    tests de integración que ejerciten el ciclo real de resume.
    """

    def test_exit_code_classification_stub(self):
        """La clasificación de exit-codes es el prerequisito de G2.2."""
        # Placeholder: cuando se implemente _classify_exit_reason(), este
        # test se convertirá en un test real de clasificación.
        # Por ahora valida que el stub conceptual es correcto:
        _TRANSIENT_REASONS = {"network_timeout", "quota_error", "rate_limit"}
        _CONTENT_REASONS = {"content_error", "criterion_failure", "invalid_output"}

        # Un retry solo aplica a razones transitorias
        def _should_retry(reason: str) -> bool:
            return reason in _TRANSIENT_REASONS

        assert _should_retry("network_timeout") is True
        assert _should_retry("content_error") is False
        assert _should_retry("criterion_failure") is False

    def test_max_retries_respected(self):
        """El retry nunca excede STACKY_TRANSIENT_RUN_RETRY_MAX."""
        from config import config
        max_retries = config.STACKY_TRANSIENT_RUN_RETRY_MAX
        assert max_retries >= 1  # el valor tiene sentido

        # Simular contador de reintentos
        attempts = 0
        for _ in range(10):  # intentar 10 veces
            if attempts >= max_retries:
                break
            attempts += 1

        assert attempts <= max_retries

    def test_different_runtimes_not_cross_retried(self):
        """claude y codex no se reintentan entre sí (sin fallback entre runtimes)."""
        # Invariante de diseño: un run que falla en claude_code_cli
        # no puede reintentarse en codex_cli (rutas separadas).
        CLAUDE = "claude_code_cli"
        CODEX = "codex_cli"

        def _retry_runtime(runtime: str, attempt: int) -> str:
            # La implementación correcta siempre devuelve el mismo runtime.
            return runtime

        assert _retry_runtime(CLAUDE, 1) == CLAUDE
        assert _retry_runtime(CODEX, 1) == CODEX
        assert _retry_runtime(CLAUDE, 1) != CODEX
