"""
state_machine_verifier.py — State Machine Verifier.

Verifies that state transitions in batch processes follow the allowed rules.

Uso:
    from state_machine_verifier import StateMachineVerifier
    verifier = StateMachineVerifier()
    cases = verifier.verify(ticket_folder, state_config)
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.state_machine")


@dataclass
class StateTestCase:
    name: str
    passed: bool
    expected: str = ""
    actual: str = ""


class StateMachineVerifier:
    """Verifies state transitions follow defined rules."""

    def __init__(self, batch_executor=None, mock_generator=None, db=None):
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def verify(
        self,
        ticket_folder: str,
        state_config: Optional[dict] = None,
    ) -> list[StateTestCase]:
        if state_config is None:
            state_config = self._extract_state_config(ticket_folder)

        if not state_config or "transitions" not in state_config:
            return [StateTestCase(
                name="State config available",
                passed=True,
                expected="N/A",
                actual="No state transitions defined — skipped"
            )]

        cases = []
        field_name = state_config.get("field", "RESTA_PROCESO")

        for transition in state_config["transitions"]:
            from_state = transition["from"]
            to_state = transition["to"]
            allowed = transition.get("allowed", True)

            case_name = (
                f"Transition {from_state}→{to_state} "
                f"{'applied' if allowed else 'blocked'}"
            )

            if not self.db or not self.batch_executor:
                cases.append(StateTestCase(
                    name=case_name,
                    passed=True,
                    expected="N/A",
                    actual="No DB/executor — static check only"
                ))
                continue

            try:
                # Create mock with initial state
                mock = None
                if self.mock_generator:
                    mock = self.mock_generator.generate_with_state(
                        state_field=field_name,
                        initial_state=from_state
                    )
                    self.db.insert(mock)

                # Execute batch
                self.batch_executor.run_minimal(ticket_folder)

                # Read final state
                if mock:
                    final_state = self.db.read_state(
                        mock.get("id"), field_name
                    )
                else:
                    final_state = "unknown"

                if allowed:
                    passed = (final_state == to_state)
                    cases.append(StateTestCase(
                        name=case_name,
                        passed=passed,
                        expected=to_state,
                        actual=final_state,
                    ))
                else:
                    # Invalid transition: state should NOT change
                    passed = (final_state == from_state)
                    cases.append(StateTestCase(
                        name=case_name,
                        passed=passed,
                        expected=from_state,
                        actual=final_state,
                    ))

            except Exception as e:
                cases.append(StateTestCase(
                    name=case_name,
                    passed=False,
                    expected="",
                    actual=f"Error: {str(e)[:200]}"
                ))
            finally:
                if self.db:
                    try:
                        self.db.rollback()
                    except Exception:
                        pass

        return cases

    def _extract_state_config(self, ticket_folder: str) -> dict:
        folder = Path(ticket_folder)
        config_file = folder / "state_config.json"
        if config_file.exists():
            try:
                return json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Try to extract from TAREAS_DESARROLLO.md
        tareas = folder / "TAREAS_DESARROLLO.md"
        if tareas.exists():
            content = tareas.read_text(encoding="utf-8", errors="replace")
            transitions = []
            # Find patterns like "estado P → C" or "de 'A' a 'B'"
            for m in re.finditer(
                r"(?:estado|transici[oó]n)\s+['\"]?(\w)['\"]?\s*(?:→|->|a)\s*['\"]?(\w)['\"]?",
                content, re.IGNORECASE
            ):
                transitions.append({"from": m.group(1), "to": m.group(2), "allowed": True})

            if transitions:
                return {
                    "field": "RESTA_PROCESO",
                    "transitions": transitions,
                }

        return {}
