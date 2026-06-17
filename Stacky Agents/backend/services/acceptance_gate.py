"""A1.1 — Gate del contrato de aceptación + pase correctivo.

Responsabilidades:
- execute_contract_gate(contract, workspace) → result_dict
  Ejecuta checks_kept del contrato en el workspace POST-RUN.
  Todos pasan → satisfied=True; alguno falla → satisfied=False.
- attempt_acceptance_repair(...) → repair_dict
  Un único pase correctivo si el runtime soporta resume y queda presupuesto.
  Re-ejecuta el contrato una vez: si pasa → recovered=True.

Reglas:
- n/a → satisfied=None (sin gate, byte-idéntico al pipeline sin plan 32)
- is_active_gate=False → sin gate
- Sin resume → no repara
- budget_remaining=0 → no repara
- El repair corrige el CÓDIGO, no el contrato (inmutable)
- Cap: STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES (default 1, compartido)
- Presupuesto compartido con autocorrect/run_repair/Q1.1/E1.1
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Any, Callable

from harness.capabilities import CAPABILITIES

logger = logging.getLogger("stacky.acceptance_gate")

_EXEC_TIMEOUT_S = 60


# ── Ejecución de un chequeo individual ───────────────────────────────────────

def _run_single_check(check: dict, workspace: str) -> tuple[str, str]:
    """Ejecuta un chequeo del contrato en el workspace.

    Returns:
        ("green", detail) — pasa
        ("red", detail)   — falla
        ("could-not-run", detail) — no ejecutable (toolchain ausente, timeout)
    """
    kind = check.get("kind", "command")
    artifact = check.get("artifact", "")

    if not artifact:
        return ("could-not-run", "artifact vacío")

    try:
        if kind == "file_predicate":
            from pathlib import Path
            path = Path(workspace) / artifact
            return ("green", f"existe: {artifact}") if path.exists() else ("red", f"no existe: {artifact}")

        if kind == "schema":
            from pathlib import Path
            import json
            schema_path = Path(workspace) / artifact
            if not schema_path.exists():
                return ("could-not-run", f"no encontrado: {artifact}")
            try:
                json.loads(schema_path.read_text(encoding="utf-8", errors="replace"))
                return ("green", "schema válido")
            except Exception as e:
                return ("red", str(e)[:200])

        # command o generated_test
        import tempfile
        from pathlib import Path

        cmd_to_run = artifact
        tmp_file = None

        try:
            if kind == "generated_test":
                suffix = ".py"
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=suffix, dir=workspace,
                    prefix="_ac_gate_", delete=False, encoding="utf-8"
                ) as f:
                    f.write(artifact)
                    tmp_file = f.name
                cmd_to_run = f"python -m pytest {tmp_file} -x -q"

            result = subprocess.run(
                cmd_to_run,
                shell=True,
                capture_output=True,
                text=True,
                timeout=_EXEC_TIMEOUT_S,
                cwd=workspace,
            )
            detail = (result.stdout + result.stderr)[:500]
            return ("green", detail) if result.returncode == 0 else ("red", detail)
        finally:
            if tmp_file:
                try:
                    from pathlib import Path as _P
                    _P(tmp_file).unlink(missing_ok=True)
                except Exception:
                    pass

    except subprocess.TimeoutExpired:
        return ("could-not-run", "timeout")
    except Exception as exc:  # noqa: BLE001
        return ("could-not-run", str(exc)[:200])


# ── Gate ──────────────────────────────────────────────────────────────────────

def execute_contract_gate(contract: Any, workspace: str) -> dict:
    """Ejecuta el gate del contrato de aceptación.

    Returns dict con:
        satisfied: True | False | None (None = n/a o is_active_gate=False)
        failed_checks: list de chequeos que fallaron
        ran: lista de artefactos ejecutados
    """
    # Si el contrato es n/a o no está en modo gate → sin gate
    if contract.n_a or not contract.is_active_gate:
        return {"satisfied": None, "failed_checks": [], "ran": []}

    failed: list[dict] = []
    ran: list[str] = []

    for check in contract.checks_kept:
        artifact = check.get("artifact", "")
        ran.append(artifact[:80])
        status, detail = _run_single_check(check, workspace)
        if status != "green":
            failed.append({**check, "gate_status": status, "gate_detail": detail[:300]})

    satisfied = len(failed) == 0
    return {"satisfied": satisfied, "failed_checks": failed, "ran": ran}


# ── Pase correctivo ───────────────────────────────────────────────────────────

def attempt_acceptance_repair(
    *,
    contract: Any,
    failed_checks: list[dict],
    runtime: str,
    workspace: str,
    send_fn: Callable | None,
    budget_remaining: int,
) -> dict:
    """Intenta un único pase correctivo dirigido al fallo del contrato.

    El repair modifica el CÓDIGO del workspace, no el contrato.
    Re-ejecuta el contrato una vez y reporta si se recuperó.

    Returns dict:
        attempted: bool
        recovered: bool
        failed_before: list de artefactos que fallaron
    """
    failed_before = [c.get("artifact", "")[:80] for c in failed_checks]

    # Sin budget → no reparar
    if budget_remaining <= 0:
        return {"attempted": False, "recovered": False, "failed_before": failed_before}

    # Sin resume → no reparar
    cap = CAPABILITIES.get(runtime)
    if cap is None or not cap.supports_resume:
        return {"attempted": False, "recovered": False, "failed_before": failed_before}

    # Sin send_fn → no reparar
    if send_fn is None:
        return {"attempted": False, "recovered": False, "failed_before": failed_before}

    # Construir mensaje correctivo
    lines = ["Los siguientes chequeos del contrato de aceptación fallaron:"]
    for ch in failed_checks:
        lines.append(f"- [{ch.get('kind', 'command')}] {ch.get('ticket_clause', '')}")
        detail = ch.get("gate_detail") or ch.get("baseline_detail", "")
        if detail:
            lines.append(f"  Log: {detail[:200]}")
    lines.append("\nCorregí el código para que todos los chequeos pasen. NO modifiques los tests del contrato.")

    try:
        send_fn("\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        logger.warning("acceptance_repair: send_fn falló: %s", exc)
        return {"attempted": True, "recovered": False, "failed_before": failed_before}

    # Re-ejecutar los chequeos fallidos
    still_failing = []
    for check in failed_checks:
        status, _ = _run_single_check(check, workspace)
        if status != "green":
            still_failing.append(check)

    recovered = len(still_failing) == 0
    return {
        "attempted": True,
        "recovered": recovered,
        "failed_before": failed_before,
    }
