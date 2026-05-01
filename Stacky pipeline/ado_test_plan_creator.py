"""
ado_test_plan_creator.py — Create ADO Test Plans from QA-generated test cases.

Parses TESTER_COMPLETADO.md and creates Test Cases in ADO Test Plans,
links them to the work item, and records test run results.

Uso:
    from ado_test_plan_creator import ADOTestPlanCreator
    creator = ADOTestPlanCreator()
    test_case_ids = creator.create_test_cases_from_qa_report(wi_id, folder, plan_id)
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.ado_test_plan")

AUTH_FILE = Path(__file__).parent / "auth" / "ado_auth.json"


class ADOTestPlanCreator:
    def __init__(self, ado_client=None, config: Optional[dict] = None):
        self._ado_client = ado_client
        self._config = config or {}

    @property
    def ado_client(self):
        if self._ado_client is None:
            try:
                from ado_enricher import _get_ado_client
                self._ado_client = _get_ado_client()
            except Exception as e:
                logger.error("Cannot init ADO client: %s", e)
                raise
        return self._ado_client

    def create_test_cases_from_qa_report(
        self,
        work_item_id: int,
        ticket_folder: str,
        test_plan_id: int = 0,
    ) -> list[int]:
        """
        Parse TESTER_COMPLETADO.md and create Test Cases in ADO.

        Returns list of created test case work item IDs.
        """
        cases = self._parse_tester_completado(ticket_folder)
        if not cases:
            logger.info("[TestPlan] No test cases found in TESTER_COMPLETADO.md")
            return []

        created_ids = []
        area_path = self._config.get("area_path", "Strategist_Pacifico")
        project = self._config.get("project", "Strategist_Pacifico")

        for case in cases:
            try:
                # Create test case as work item of type "Test Case"
                title = f"[#{work_item_id}] {case['title']}"
                description = f"Steps:\n{case.get('steps', '')}\n\nExpected: {case.get('expected', '')}"

                ops = [
                    {"op": "add", "path": "/fields/System.Title", "value": title},
                    {"op": "add", "path": "/fields/System.Description", "value": description},
                    {"op": "add", "path": "/fields/System.AreaPath", "value": area_path},
                ]

                # Try to create via ADO client
                if hasattr(self.ado_client, "create_work_item"):
                    tc_id = self.ado_client.create_work_item(
                        project=project,
                        wi_type="Test Case",
                        operations=ops
                    )
                    if tc_id:
                        created_ids.append(tc_id)
                        # Link test case to source work item
                        self._link_to_work_item(work_item_id, tc_id)
                        logger.info("[TestPlan] Created test case %d for WI#%d",
                                     tc_id, work_item_id)

            except Exception as e:
                logger.error("[TestPlan] Failed to create test case: %s", e)

        return created_ids

    def record_test_run_result(
        self,
        test_case_ids: list[int],
        verdict: str,
        test_plan_id: int = 0,
    ):
        """
        Record test run results in ADO.

        Args:
            test_case_ids: List of test case work item IDs
            verdict: "APROBADO" or "CON OBSERVACIONES" or "RECHAZADO"
            test_plan_id: ADO Test Plan ID
        """
        outcome_map = {
            "APROBADO": "Passed",
            "CON OBSERVACIONES": "Failed",
            "RECHAZADO": "Failed",
        }
        outcome = outcome_map.get(verdict, "NotExecuted")

        for tc_id in test_case_ids:
            try:
                if hasattr(self.ado_client, "update_work_item"):
                    self.ado_client.update_work_item(tc_id, [
                        {"op": "add", "path": "/fields/System.State",
                         "value": "Closed" if outcome == "Passed" else "Active"}
                    ])
            except Exception as e:
                logger.error("[TestPlan] Failed to record result for TC#%d: %s",
                              tc_id, e)

    def _parse_tester_completado(self, ticket_folder: str) -> list[dict]:
        """Parse test cases from TESTER_COMPLETADO.md."""
        tester_file = Path(ticket_folder) / "TESTER_COMPLETADO.md"
        if not tester_file.exists():
            return []

        content = tester_file.read_text(encoding="utf-8", errors="replace")
        cases = []

        # Pattern: - [PASS] or - [FAIL] title
        for m in re.finditer(
            r"^-\s*\[(PASS|FAIL|OK|ERROR)\]\s*(.+?)$",
            content, re.MULTILINE
        ):
            status = m.group(1)
            title = m.group(2).strip()
            cases.append({
                "title": title,
                "status": status,
                "steps": "",
                "expected": "Pass" if status in ("PASS", "OK") else "Needs fix",
            })

        # Alternative pattern: ## Case N / ### Test N
        for m in re.finditer(
            r"^#{2,3}\s*(?:Caso|Test|Case)\s*\d*\s*[:\-]?\s*(.+?)$",
            content, re.MULTILINE
        ):
            cases.append({
                "title": m.group(1).strip(),
                "steps": "",
                "expected": "",
            })

        return cases

    def _link_to_work_item(self, source_id: int, target_id: int):
        """Link test case to source work item with 'Tests' relation."""
        try:
            if hasattr(self.ado_client, "link_work_items"):
                self.ado_client.link_work_items(
                    source_id=source_id,
                    target_id=target_id,
                    relation_type="Microsoft.VSTS.Common.TestedBy-Forward"
                )
        except Exception as e:
            logger.warning("[TestPlan] Failed to link TC#%d to WI#%d: %s",
                            target_id, source_id, e)
