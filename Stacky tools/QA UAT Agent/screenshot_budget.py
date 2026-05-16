"""
screenshot_budget.py — Screenshot capture budget enforcement (P1.B ADO-122).

PROBLEMA RESUELTO
-----------------
Sin gating, cada step exitoso captura pre_step.png + step_completed.png,
duplicando el volumen sin valor diagnóstico (ticket 122: ~56 PNG en 4 escenarios).

SOLUCIÓN
--------
Budget configurable por escenario:
  - on_success_per_step: 1  — solo step_NN_after.png en pasos OK
  - on_failure_per_step: 3  — pre_step, assert_failed, step_failed
  - max_total_per_scenario: 25

El budget se inyecta en el template playwright_test.spec.ts.j2 como variable
`screenshot_budget` (dict). El template renderiza una función TS __shouldCapture()
que decide en runtime si continuar. El módulo Python también expone
should_capture() para tests unitarios puros.

OVERRIDE
--------
QA_UAT_SCREENSHOT_BUDGET_DISABLED=1 deshabilita el budget (modo debug).
En ese caso el template renderiza sin límites y el evento
screenshot_budget_disabled=true queda registrado en execution.jsonl.

EVENTO execution.jsonl (al cierre del run)
------------------------------------------
{
  "event": "screenshot_budget_summary",
  "captured": N,
  "budget": M,
  "skipped_by_budget": K,
  "exceeded": false,
  "screenshot_budget_disabled": false
}

USO
---
    from screenshot_budget import ScreenshotBudget, should_capture, load_budget

    budget = load_budget()          # lee env vars y defaults
    ok, reason = should_capture(budget, step_ok=True, taken_so_far=3)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Tuple

# Defaults conservadores — reducen ~56 PNG a ~28 en run nominal
_DEFAULT_ON_SUCCESS_PER_STEP: int = 1
_DEFAULT_ON_FAILURE_PER_STEP: int = 3
_DEFAULT_MAX_TOTAL_PER_SCENARIO: int = 25


@dataclass
class ScreenshotBudget:
    """Contrato de budget de screenshots por escenario.

    Fields
    ------
    on_success_per_step : int
        Capturas máximas por step exitoso (default 1: solo step_NN_after.png).
    on_failure_per_step : int
        Capturas máximas por step fallido (default 3: pre_step, assert_failed, step_failed).
    max_total_per_scenario : int
        Límite total de capturas por escenario antes de suprimir.
    disabled : bool
        True cuando QA_UAT_SCREENSHOT_BUDGET_DISABLED=1 — comportamiento legacy sin límite.
    """
    on_success_per_step: int = _DEFAULT_ON_SUCCESS_PER_STEP
    on_failure_per_step: int = _DEFAULT_ON_FAILURE_PER_STEP
    max_total_per_scenario: int = _DEFAULT_MAX_TOTAL_PER_SCENARIO
    disabled: bool = False

    def to_dict(self) -> dict:
        return {
            "on_success_per_step": self.on_success_per_step,
            "on_failure_per_step": self.on_failure_per_step,
            "max_total_per_scenario": self.max_total_per_scenario,
            "disabled": self.disabled,
        }


def load_budget(
    on_success_per_step: int | None = None,
    on_failure_per_step: int | None = None,
    max_total_per_scenario: int | None = None,
) -> ScreenshotBudget:
    """Carga el budget efectivo desde env vars + overrides opcionales.

    Env vars:
      QA_UAT_SCREENSHOT_BUDGET_DISABLED=1   — deshabilita el budget
      QA_UAT_SCREENSHOT_ON_SUCCESS=N        — capturas por step OK (default 1)
      QA_UAT_SCREENSHOT_ON_FAILURE=N        — capturas por step fallido (default 3)
      QA_UAT_SCREENSHOT_MAX_PER_SCENARIO=N  — máximo total (default 25)
    """
    disabled = os.environ.get("QA_UAT_SCREENSHOT_BUDGET_DISABLED", "").lower() in ("1", "true", "yes")

    def _int_env(key: str, default: int) -> int:
        val = os.environ.get(key, "")
        try:
            return int(val) if val else default
        except ValueError:
            return default

    return ScreenshotBudget(
        on_success_per_step=on_success_per_step if on_success_per_step is not None else _int_env("QA_UAT_SCREENSHOT_ON_SUCCESS", _DEFAULT_ON_SUCCESS_PER_STEP),
        on_failure_per_step=on_failure_per_step if on_failure_per_step is not None else _int_env("QA_UAT_SCREENSHOT_ON_FAILURE", _DEFAULT_ON_FAILURE_PER_STEP),
        max_total_per_scenario=max_total_per_scenario if max_total_per_scenario is not None else _int_env("QA_UAT_SCREENSHOT_MAX_PER_SCENARIO", _DEFAULT_MAX_TOTAL_PER_SCENARIO),
        disabled=disabled,
    )


def should_capture(
    budget: ScreenshotBudget,
    step_ok: bool,
    taken_so_far: int,
    step_capture_index: int = 0,
) -> Tuple[bool, str]:
    """Decide si capturar un screenshot según el budget.

    Parameters
    ----------
    budget : ScreenshotBudget
        Budget efectivo del run.
    step_ok : bool
        True si el step fue exitoso, False si falló.
    taken_so_far : int
        Total de capturas ya realizadas en este escenario.
    step_capture_index : int
        Índice de esta captura dentro del step (0 = primera, 1 = segunda, etc.).

    Returns
    -------
    (bool, reason_str)
        True + "ok" si debe capturar.
        False + reason si debe omitir.
    """
    if budget.disabled:
        return True, "budget_disabled"

    if taken_so_far >= budget.max_total_per_scenario:
        return False, "max_total_per_scenario_exceeded"

    allowed_per_step = budget.on_success_per_step if step_ok else budget.on_failure_per_step
    if step_capture_index >= allowed_per_step:
        return False, f"per_step_limit_reached_{step_capture_index}"

    return True, "ok"


def build_ts_budget_block(budget: ScreenshotBudget) -> str:
    """Genera el bloque TypeScript que gestiona el budget en runtime.

    Este bloque se inyecta en el template como variable __SCREENSHOT_BUDGET_BLOCK__
    en la sección de constantes del spec.
    """
    if budget.disabled:
        return (
            "// Screenshot budget: DISABLED (QA_UAT_SCREENSHOT_BUDGET_DISABLED=1)\n"
            "const __SS_BUDGET_DISABLED = true;\n"
            "const __SS_MAX_PER_SCENARIO = Infinity;\n"
            "const __SS_ON_SUCCESS = Infinity;\n"
            "const __SS_ON_FAILURE = Infinity;\n"
            "let __ss_taken = 0;\n"
            "function __shouldCapture(stepOk: boolean, captureIndex: number): boolean {\n"
            "  return true;\n"
            "}\n"
        )
    return (
        f"// Screenshot budget (P1.B ADO-122)\n"
        f"const __SS_BUDGET_DISABLED = false;\n"
        f"const __SS_MAX_PER_SCENARIO = {budget.max_total_per_scenario};\n"
        f"const __SS_ON_SUCCESS = {budget.on_success_per_step};\n"
        f"const __SS_ON_FAILURE = {budget.on_failure_per_step};\n"
        f"let __ss_taken = 0;\n"
        f"let __ss_skipped = 0;\n"
        f"let __ss_exceeded = false;\n"
        "function __shouldCapture(stepOk: boolean, captureIndex: number): boolean {\n"
        "  if (__ss_taken >= __SS_MAX_PER_SCENARIO) {\n"
        "    if (!__ss_exceeded) {\n"
        "      __ss_exceeded = true;\n"
        "      console.log('[SCREENSHOT_BUDGET] max_total_per_scenario reached, suppressing captures');\n"
        "    }\n"
        "    __ss_skipped++;\n"
        "    return false;\n"
        "  }\n"
        "  const limit = stepOk ? __SS_ON_SUCCESS : __SS_ON_FAILURE;\n"
        "  if (captureIndex >= limit) { __ss_skipped++; return false; }\n"
        "  __ss_taken++;\n"
        "  return true;\n"
        "}\n"
        "async function __captureIfBudget(page: any, path: string, stepOk: boolean, captureIndex = 0): Promise<void> {\n"
        "  if (__shouldCapture(stepOk, captureIndex)) {\n"
        "    await page.screenshot({ path }).catch(() => null);\n"
        "  }\n"
        "}\n"
    )


__all__ = [
    "ScreenshotBudget",
    "load_budget",
    "should_capture",
    "build_ts_budget_block",
]
