"""
multi_empresa_executor.py — Multi-Empresa Execution Matrix.

Executes batch process across all active empresas and collects per-empresa results.

Uso:
    from multi_empresa_executor import MultiEmpresaExecutor
    executor = MultiEmpresaExecutor(config)
    result = executor.run_matrix(ticket_folder, config)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("stacky.multi_empresa")


@dataclass
class MatrixResult:
    empresa_results: dict[str, str] = field(default_factory=dict)
    fail_rate: float = 0.0
    verdict: str = ""  # "PASS", "WARNING", "FAIL"


class MultiEmpresaExecutor:
    FAIL_THRESHOLD = 0.2  # >20% fail → global FAIL

    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def run_matrix(self, ticket_folder: str,
                   config: Optional[dict] = None) -> MatrixResult:
        cfg = config or self.config
        empresas = self._get_active_empresas()

        if not empresas:
            return MatrixResult(
                empresa_results={},
                fail_rate=0.0,
                verdict="SKIP — no empresas found"
            )

        results: dict[str, str] = {}

        for empresa_cod in empresas:
            try:
                mock_data = None
                if self.mock_generator:
                    try:
                        mock_data = self.mock_generator.generate_for_empresa(empresa_cod)
                    except Exception:
                        pass

                if self.batch_executor:
                    batch_result = self.batch_executor.run_for_empresa(
                        ticket_folder, empresa_cod, mock_data
                    )
                    results[empresa_cod] = "PASS" if batch_result.passed else "FAIL"
                else:
                    results[empresa_cod] = "SKIP — no executor"

            except Exception as e:
                results[empresa_cod] = f"ERROR: {str(e)[:100]}"
                logger.error("[MultiEmpresa] Error for %s: %s", empresa_cod, e)

        total = len(results)
        fails = sum(1 for v in results.values() if v != "PASS")
        fail_rate = fails / total if total > 0 else 0.0

        if fail_rate == 0:
            verdict = "PASS"
        elif fail_rate > self.FAIL_THRESHOLD:
            verdict = "FAIL"
        else:
            verdict = "WARNING"

        logger.info("[MultiEmpresa] %s — %d/%d passed (fail_rate=%.0f%%)",
                     verdict, total - fails, total, fail_rate * 100)

        return MatrixResult(
            empresa_results=results,
            fail_rate=round(fail_rate, 3),
            verdict=verdict,
        )

    def _get_active_empresas(self) -> list[str]:
        if self.db:
            try:
                rows = self.db.fetch_all(
                    "SELECT RCOD_EMP FROM REMP WHERE RESTADO = 'A'"
                )
                return [r["RCOD_EMP"] for r in rows]
            except Exception as e:
                logger.warning("Cannot query empresas: %s", e)

        # Fallback to config
        return self.config.get("empresas", ["01"])
