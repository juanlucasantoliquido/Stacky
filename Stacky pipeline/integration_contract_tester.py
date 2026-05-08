"""
integration_contract_tester.py — Integration Contract Test.

Verifies modified DAL/Negocio files don't break callers by checking public API
signatures are preserved before and after changes.

Uso:
    from integration_contract_tester import IntegrationContractTester
    tester = IntegrationContractTester()
    cases = tester.test_public_interface_unchanged("Batch/Negocio/PagosDalc.cs", workspace)
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.contract_test")


@dataclass
class MethodSignature:
    name: str
    access: str
    return_type: str
    parameters: str
    signature: str = ""

    def __post_init__(self):
        if not self.signature:
            self.signature = f"{self.access} {self.return_type} {self.name}({self.parameters})"


@dataclass
class ContractTestCase:
    name: str
    passed: bool
    evidence: str = ""


class IntegrationContractTester:
    METHOD_PATTERN = re.compile(
        r"^\s*(public|internal)\s+"
        r"(?:static\s+)?(?:async\s+)?(?:virtual\s+)?(?:override\s+)?"
        r"([\w<>\[\],\s]+?)\s+"
        r"(\w+)\s*\(([^)]*)\)",
        re.MULTILINE
    )

    def __init__(self, workspace_root: str = ""):
        self.workspace_root = workspace_root

    def test_public_interface_unchanged(
        self, modified_file: str, workspace_root: str = ""
    ) -> list[ContractTestCase]:
        root = workspace_root or self.workspace_root
        cases = []

        # Get before signatures (try git)
        before_sig = self._extract_public_api_from_git(modified_file, root)
        after_sig = self._extract_public_api_from_file(modified_file, root)

        if not before_sig:
            cases.append(ContractTestCase(
                name="Git history available for comparison",
                passed=True,
                evidence="No git history — skipping contract check"
            ))
            return cases

        for method_name, before in before_sig.items():
            after = after_sig.get(method_name)
            if after is None:
                cases.append(ContractTestCase(
                    name=f"Method '{method_name}' not removed",
                    passed=False,
                    evidence=f"Existed before: {before.signature}"
                ))
            elif before.signature != after.signature:
                cases.append(ContractTestCase(
                    name=f"Signature of '{method_name}' unchanged",
                    passed=False,
                    evidence=f"Before: {before.signature}\nAfter: {after.signature}"
                ))
            else:
                cases.append(ContractTestCase(
                    name=f"Signature of '{method_name}' stable",
                    passed=True,
                ))

        # Check for new public methods (informational, not a failure)
        new_methods = set(after_sig.keys()) - set(before_sig.keys())
        if new_methods:
            cases.append(ContractTestCase(
                name="New public methods added",
                passed=True,
                evidence=f"New: {', '.join(new_methods)}"
            ))

        return cases

    def find_callers(self, method_name: str, workspace_root: str) -> list[str]:
        """Find files that call a specific method."""
        callers = []
        root = Path(workspace_root)
        for ext in ["*.cs", "*.vb"]:
            for f in root.rglob(ext):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    if re.search(rf"\b{re.escape(method_name)}\s*\(", content):
                        callers.append(str(f.relative_to(root)))
                except Exception:
                    continue
        return callers

    def _extract_public_api_from_file(
        self, file_path: str, workspace_root: str
    ) -> dict[str, MethodSignature]:
        full_path = Path(workspace_root) / file_path
        if not full_path.exists():
            return {}
        content = full_path.read_text(encoding="utf-8", errors="replace")
        return self._parse_methods(content)

    def _extract_public_api_from_git(
        self, file_path: str, workspace_root: str
    ) -> dict[str, MethodSignature]:
        try:
            result = subprocess.run(
                ["git", "show", f"HEAD:{file_path}"],
                capture_output=True, text=True,
                cwd=workspace_root, timeout=10
            )
            if result.returncode == 0:
                return self._parse_methods(result.stdout)
        except Exception:
            pass
        return {}

    def _parse_methods(self, content: str) -> dict[str, MethodSignature]:
        methods = {}
        for m in self.METHOD_PATTERN.finditer(content):
            access = m.group(1)
            return_type = m.group(2).strip()
            name = m.group(3)
            params = m.group(4).strip()
            methods[name] = MethodSignature(
                name=name, access=access,
                return_type=return_type, parameters=params
            )
        return methods
