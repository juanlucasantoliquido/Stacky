"""
evidence_collector_dynamic.py — Consolidates evidence from dynamic tests (E-01..E-04).

Builds a unified professional report from batch, UI, and DDL test results,
attaches it to ADO.

Uso:
    from evidence_collector_dynamic import DynamicEvidenceCollector
    collector = DynamicEvidenceCollector()
    report = collector.build_report(ticket_folder, batch_result, ui_result, ddl_result)
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.evidence_dynamic")


class DynamicEvidenceCollector:
    def __init__(self, ado_attachment_manager=None):
        self._ado_mgr = ado_attachment_manager

    def build_report(
        self,
        ticket_folder: str,
        batch_result=None,
        ui_result=None,
        ddl_result=None,
        extra_sections: Optional[list[str]] = None,
    ) -> str:
        lines = [
            "# REPORTE DE EJECUCIÓN — Test Dinámico",
            f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Resumen",
        ]

        # Collect all cases
        all_cases = []
        if batch_result:
            all_cases.extend(getattr(batch_result, "cases", []))
        if ui_result:
            all_cases.extend(getattr(ui_result, "cases", []))
        if ddl_result:
            all_cases.extend(getattr(ddl_result, "cases", []))

        total = len(all_cases)
        passed = sum(1 for c in all_cases if getattr(c, "passed", False))
        verdict = "PASS" if passed == total and total > 0 else f"FAIL ({total - passed}/{total} fallaron)"
        lines.append(f"**Veredicto: {verdict}** — {passed}/{total} casos pasaron")
        lines.append("")

        # Batch section
        if batch_result:
            lines.append("## Batch Tests")
            for c in getattr(batch_result, "cases", []):
                status = "PASS" if c.passed else "FAIL"
                lines.append(f"- [{status}] {c.name}")
                if hasattr(c, "evidence") and c.evidence and not c.passed:
                    lines.append(f"  > {str(c.evidence)[:200]}")
            lines.append("")

        # UI section
        if ui_result:
            lines.append("## UI Tests")
            for c in getattr(ui_result, "cases", []):
                status = "PASS" if c.passed else "FAIL"
                lines.append(f"- [{status}] {c.name}")
            lines.append("")

        # DDL section
        if ddl_result:
            lines.append("## DDL Tests")
            for c in getattr(ddl_result, "cases", []):
                status = "PASS" if c.passed else "FAIL"
                lines.append(f"- [{status}] {c.name}")
                if hasattr(c, "evidence") and c.evidence and not c.passed:
                    lines.append(f"  > {str(c.evidence)[:200]}")
            lines.append("")

        # Extra sections
        if extra_sections:
            for sec in extra_sections:
                lines.append(sec)
            lines.append("")

        report = "\n".join(lines)

        # Write to ticket folder
        out_path = Path(ticket_folder) / "TEST_EXECUTION_REPORT.md"
        out_path.write_text(report, encoding="utf-8")

        # Attach to ADO
        if self._ado_mgr:
            try:
                self._ado_mgr.attach(ticket_folder, "qa_completado")
            except Exception as e:
                logger.warning("Failed to attach report to ADO: %s", e)

        logger.info("[Evidence] Report written: %s (%d cases, %d passed)",
                     out_path, total, passed)
        return report
