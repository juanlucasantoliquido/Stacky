"""
evidence_collector.py — E-05: Evidence Collector & Reporter.

Consolida la evidencia de tests dinámicos (E-01..E-15, F-01..F-15)
en un único reporte TEST_EXECUTION_REPORT.md dentro del ticket.

Uso:
    from evidence_collector import EvidenceCollector
    collector = EvidenceCollector()
    collector.add_section("Batch Tests", cases_batch)
    collector.add_section("Data Integrity", cases_integrity)
    collector.build_report(ticket_folder)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.evidence_collector")


@dataclass
class TestCase:
    name: str
    passed: bool
    evidence: Optional[str] = None
    category: str = ""


@dataclass
class TestSection:
    title: str
    cases: list[TestCase] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed


class EvidenceCollector:
    def __init__(self):
        self._sections: list[TestSection] = []

    def add_section(self, title: str, cases: list[TestCase]) -> None:
        self._sections.append(TestSection(title=title, cases=cases))

    def add_case(self, section_title: str, case: TestCase) -> None:
        for sec in self._sections:
            if sec.title == section_title:
                sec.cases.append(case)
                return
        self._sections.append(TestSection(title=section_title, cases=[case]))

    @property
    def total_cases(self) -> int:
        return sum(s.total for s in self._sections)

    @property
    def total_passed(self) -> int:
        return sum(s.passed for s in self._sections)

    @property
    def total_failed(self) -> int:
        return self.total_cases - self.total_passed

    @property
    def all_passed(self) -> bool:
        return self.total_failed == 0

    def build_report(self, ticket_folder: str) -> str:
        lines = [
            "# TEST EXECUTION REPORT — Tests Dinámicos",
            f"*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
        ]

        # Summary
        verdict = "PASS" if self.all_passed else "FAIL"
        lines.append("## Resumen ejecutivo")
        lines.append("")
        lines.append(f"**Veredicto: {verdict}** — {self.total_passed}/{self.total_cases} casos pasaron")
        if self.total_failed > 0:
            lines.append(f"**Casos fallidos: {self.total_failed}**")
        lines.append("")

        # Summary table
        lines.append("| Sección | Total | Pass | Fail | % |")
        lines.append("|---------|-------|------|------|---|")
        for sec in self._sections:
            pct = round(sec.passed / sec.total * 100) if sec.total > 0 else 0
            status = "✅" if sec.failed == 0 else "❌"
            lines.append(f"| {status} {sec.title} | {sec.total} | {sec.passed} | {sec.failed} | {pct}% |")
        lines.append("")

        # Detail per section
        for sec in self._sections:
            lines.append(f"## {sec.title}")
            lines.append("")
            for case in sec.cases:
                icon = "✅" if case.passed else "❌"
                lines.append(f"### {icon} {case.name}")
                lines.append(f"- **Resultado:** {'PASS' if case.passed else 'FAIL'}")
                if case.evidence:
                    # Truncate very long evidence
                    ev = case.evidence if len(case.evidence) < 2000 else case.evidence[:2000] + "\n...(truncado)"
                    lines.append(f"- **Evidencia:**")
                    lines.append(f"```")
                    lines.append(ev)
                    lines.append(f"```")
                lines.append("")

        report = "\n".join(lines)

        # Write to file
        out_path = Path(ticket_folder) / "TEST_EXECUTION_REPORT.md"
        out_path.write_text(report, encoding="utf-8")
        logger.info("[Evidence] Reporte generado: %s (%d casos, %d secciones)",
                    out_path, self.total_cases, len(self._sections))

        return report

    def reset(self) -> None:
        self._sections.clear()
