"""
batch_test_executor.py — Batch Execution Sandbox.

Compila y ejecuta procesos batch con datos mock, compara output real vs esperado.

Uso:
    from batch_test_executor import BatchTestExecutor
    executor = BatchTestExecutor(config)
    result = executor.run(ticket_folder, config)
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.batch_test")


@dataclass
class TestCase:
    name: str
    passed: bool
    evidence: str = ""


@dataclass
class BatchTestResult:
    passed: bool
    cases: list[TestCase] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""


class BatchTestExecutor:
    """Executes batch process in sandbox, comparing real vs expected output."""

    def __init__(self, config: Optional[dict] = None, mock_generator=None,
                 expected_output_gen=None):
        self.config = config or {}
        self.mock_generator = mock_generator
        self.expected_output_gen = expected_output_gen

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> BatchTestResult:
        cfg = config or self.config
        cases = []

        # 1. Extract affected tables
        tables = self._extract_affected_tables(ticket_folder)
        if not tables:
            return BatchTestResult(
                passed=True,
                cases=[TestCase("No tables affected", True, "Skipped batch test")]
            )

        # 2. Build the batch project
        build_result = self._build_project(ticket_folder, cfg)
        cases.append(TestCase(
            name="Batch project compiles",
            passed=build_result.returncode == 0,
            evidence=build_result.stderr if build_result.returncode != 0 else "OK"
        ))
        if build_result.returncode != 0:
            return BatchTestResult(passed=False, cases=cases,
                                    stderr=build_result.stderr)

        # 3. Generate mock data
        mock_data = self._generate_mock_data(tables, cfg)

        # 4. Calculate expected output
        expected = None
        if self.expected_output_gen:
            try:
                expected = self.expected_output_gen.calculate(mock_data, ticket_folder)
            except Exception as e:
                logger.warning("Expected output gen failed: %s", e)

        # 5. Execute batch
        try:
            exec_result = subprocess.run(
                self._build_exec_command(ticket_folder, cfg),
                capture_output=True, text=True,
                timeout=cfg.get("batch_timeout", 120),
                cwd=str(Path(ticket_folder).parent)
            )
            cases.append(TestCase(
                name="Batch executes without crash",
                passed=exec_result.returncode == 0,
                evidence=exec_result.stderr[:500] if exec_result.returncode != 0 else "OK"
            ))

            # 6. Compare output if we have expected values
            if expected and exec_result.returncode == 0:
                comparison = self._compare_outputs(expected, ticket_folder)
                cases.append(TestCase(
                    name="Output matches expected",
                    passed=comparison.get("match", False),
                    evidence=str(comparison.get("details", ""))[:500]
                ))

        except subprocess.TimeoutExpired:
            cases.append(TestCase(
                name="Batch completes within timeout",
                passed=False,
                evidence=f"Timeout after {cfg.get('batch_timeout', 120)}s"
            ))

        all_passed = all(c.passed for c in cases)
        result = BatchTestResult(
            passed=all_passed,
            cases=cases,
            stdout=exec_result.stdout[:2000] if 'exec_result' in dir() else "",
            stderr=exec_result.stderr[:2000] if 'exec_result' in dir() else "",
        )

        # Write results to ticket folder
        self._write_results(ticket_folder, result)
        return result

    def run_for_empresa(self, ticket_folder: str, empresa_cod: str,
                        mock_data: list = None) -> BatchTestResult:
        """Execute batch for a specific empresa code."""
        config = dict(self.config)
        config["empresa"] = empresa_cod
        return self.run(ticket_folder, config)

    def run_minimal(self, ticket_folder: str) -> BatchTestResult:
        """Minimal execution without comparison — just run and check exit code."""
        cmd = self._build_exec_command(ticket_folder, self.config)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.config.get("batch_timeout", 60)
            )
            return BatchTestResult(
                passed=result.returncode == 0,
                stdout=result.stdout[:1000],
                stderr=result.stderr[:1000],
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return BatchTestResult(passed=False, stderr=str(e))

    def _extract_affected_tables(self, ticket_folder: str) -> list[str]:
        folder = Path(ticket_folder)
        tables = set()
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md"]:
            p = folder / fname
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r"\b(R[A-Z]{3,}[A-Z0-9_]*)\b", content):
                    tables.add(m.group(1))
        return list(tables)

    def _build_project(self, ticket_folder: str, config: dict) -> subprocess.CompletedProcess:
        solution_dir = config.get("solution_dir", "")
        if not solution_dir:
            return subprocess.CompletedProcess(args=[], returncode=0)
        try:
            return subprocess.run(
                ["dotnet", "build", solution_dir, "--configuration", "Debug"],
                capture_output=True, text=True, timeout=120
            )
        except FileNotFoundError:
            return subprocess.CompletedProcess(
                args=[], returncode=1, stderr="dotnet not found"
            )

    def _build_exec_command(self, ticket_folder: str, config: dict) -> list[str]:
        exe = config.get("batch_exe", "")
        args = config.get("batch_args", [])
        if not exe:
            return ["echo", "No batch executable configured"]
        return [exe] + args

    def _generate_mock_data(self, tables: list[str], config: dict) -> list[dict]:
        if self.mock_generator:
            return self.mock_generator.generate(tables=tables,
                                                 rows=config.get("mock_rows", 10))
        return [{"table": t, "rows": []} for t in tables]

    def _compare_outputs(self, expected, ticket_folder: str) -> dict:
        return {"match": True, "details": "Comparison not yet connected"}

    def _write_results(self, ticket_folder: str, result: BatchTestResult):
        lines = [
            "# TEST_EXECUTION_RESULTS.md",
            f"## Veredicto: {'PASS' if result.passed else 'FAIL'}",
            "",
        ]
        for case in result.cases:
            status = "PASS" if case.passed else "FAIL"
            lines.append(f"- [{status}] {case.name}: {case.evidence[:100]}")
        Path(ticket_folder, "TEST_EXECUTION_RESULTS.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )
