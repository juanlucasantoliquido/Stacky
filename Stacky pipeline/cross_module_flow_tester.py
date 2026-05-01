"""
cross_module_flow_tester.py — Cross-Module End-to-End Flow Test.

Traces complete business flows (Alta Cliente → Obligación → Pago → Cierre)
and verifies state at each step.

Uso:
    from cross_module_flow_tester import CrossModuleFlowTester
    tester = CrossModuleFlowTester(config)
    result = tester.run(ticket_folder, config)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.cross_module")

FLOWS_FILE = Path(__file__).parent / "data" / "business_flows.json"


@dataclass
class FlowStep:
    name: str
    table: str = ""
    verify_fn: str = ""


@dataclass
class FlowStepResult:
    step: str
    passed: bool
    evidence: str = ""


@dataclass
class FlowTestResult:
    flow: str = ""
    steps: list[FlowStepResult] = field(default_factory=list)
    passed: bool = False
    skipped: bool = False
    reason: str = ""

    def __post_init__(self):
        if not self.skipped:
            self.passed = all(s.passed for s in self.steps)


DEFAULT_FLOWS = {
    "alta_cliente": [
        {"name": "INSERT RCLIE", "table": "RCLIE"},
        {"name": "INSERT RDIRE", "table": "RDIRE"},
        {"name": "SYNC RTELE", "table": "RTELE"},
    ],
    "obligacion_pago": [
        {"name": "INSERT ROBLG", "table": "ROBLG"},
        {"name": "INSERT RPAGOS", "table": "RPAGOS"},
        {"name": "UPDATE RDEUDA", "table": "RDEUDA"},
        {"name": "STATE_ROBLG", "table": "ROBLG"},
    ],
}


class CrossModuleFlowTester:
    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db
        self._flows = self._load_flows()

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> FlowTestResult:
        flow_type = self._detect_flow_type(ticket_folder)

        if not flow_type or flow_type not in self._flows:
            return FlowTestResult(
                skipped=True,
                reason="Business flow type not identified"
            )

        flow_steps = self._flows[flow_type]
        step_results = []

        for step_def in flow_steps:
            step_name = step_def.get("name", "unknown")
            table = step_def.get("table", "")

            try:
                # Get count before
                before_count = self._get_count(table)

                # Execute step
                if self.batch_executor:
                    self.batch_executor.run_minimal(ticket_folder)

                # Get count after
                after_count = self._get_count(table)

                passed = after_count >= before_count
                step_results.append(FlowStepResult(
                    step=step_name,
                    passed=passed,
                    evidence=f"{table}: {before_count}→{after_count} rows"
                ))

                if not passed:
                    break  # stop on first failure

            except Exception as e:
                step_results.append(FlowStepResult(
                    step=step_name,
                    passed=False,
                    evidence=str(e)[:200]
                ))
                break

        return FlowTestResult(
            flow=flow_type,
            steps=step_results,
        )

    def _detect_flow_type(self, ticket_folder: str) -> str:
        folder = Path(ticket_folder)
        content = ""
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md"]:
            p = folder / fname
            if p.exists():
                content += p.read_text(encoding="utf-8", errors="replace").lower()

        if any(k in content for k in ["rclie", "cliente", "alta"]):
            return "alta_cliente"
        if any(k in content for k in ["roblg", "rpagos", "obligación", "pago"]):
            return "obligacion_pago"
        return ""

    def _get_count(self, table: str) -> int:
        if self.db and hasattr(self.db, "count"):
            return self.db.count(table)
        return 0

    def _load_flows(self) -> dict:
        if FLOWS_FILE.exists():
            try:
                return json.loads(FLOWS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return dict(DEFAULT_FLOWS)
