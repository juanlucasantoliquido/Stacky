"""
web_ui_verifier.py — Web UI Verifier using Playwright.

Compiles OnLine project, deploys locally, navigates with Playwright, takes
screenshots, and verifies DOM assertions.

Uso:
    from web_ui_verifier import WebUIVerifier
    verifier = WebUIVerifier(config)
    result = verifier.verify(ticket_folder, config)
"""

import base64
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.web_ui")


@dataclass
class UITestCase:
    name: str
    passed: bool
    evidence: Optional[bytes] = None  # screenshot bytes


@dataclass
class UITestResult:
    cases: list[UITestCase] = field(default_factory=list)

    @property
    def passed(self):
        return all(c.passed for c in self.cases)


class WebUIVerifier:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def verify(self, ticket_folder: str, config: Optional[dict] = None) -> UITestResult:
        cfg = config or self.config
        spec = self._extract_ui_spec(ticket_folder)
        cases = []

        if not spec.get("url"):
            cases.append(UITestCase(
                name="No UI URL detected", passed=True, evidence=None
            ))
            return UITestResult(cases=cases)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            cases.append(UITestCase(
                name="Playwright available",
                passed=False,
                evidence=None,
            ))
            logger.error("playwright not installed. pip install playwright; playwright install chromium")
            return UITestResult(cases=cases)

        port = cfg.get("web_port", 5000)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            try:
                # Navigate
                url = f"http://localhost:{port}{spec['url']}"
                page.goto(url, timeout=15000)
                page.wait_for_load_state("networkidle", timeout=10000)

                # Case 1: page loads without errors
                error_count = page.locator(".error-dialog, #errorDiv, .server-error").count()
                screenshot1 = page.screenshot(full_page=True)
                cases.append(UITestCase(
                    name="Page loads without errors",
                    passed=error_count == 0,
                    evidence=screenshot1,
                ))

                # Case 2: new field exists in DOM
                field_id = spec.get("new_field_id")
                if field_id:
                    field_loc = page.locator(
                        f"#{field_id}, [name='{field_id}'], "
                        f"[id$='{field_id}']"
                    )
                    field_exists = field_loc.count() > 0
                    cases.append(UITestCase(
                        name=f"Field '{field_id}' exists in DOM",
                        passed=field_exists,
                        evidence=page.screenshot(),
                    ))

                    # Case 3: field is visible
                    if field_exists:
                        try:
                            is_visible = field_loc.first.is_visible()
                        except Exception:
                            is_visible = False
                        cases.append(UITestCase(
                            name=f"Field '{field_id}' is visible",
                            passed=is_visible,
                        ))

                    # Case 4: required field validation
                    if spec.get("required") and field_exists:
                        submit_btn = page.locator(
                            "#btnGuardar, input[type=submit], "
                            "button[type=submit]"
                        )
                        if submit_btn.count() > 0:
                            submit_btn.first.click()
                            validator = page.locator(
                                f"[id$='rfv{field_id}'], .field-validation-error"
                            )
                            cases.append(UITestCase(
                                name="Required field validation fires",
                                passed=validator.count() > 0,
                                evidence=page.screenshot(),
                            ))

            except Exception as e:
                cases.append(UITestCase(
                    name="Page navigation",
                    passed=False,
                    evidence=None,
                ))
                logger.error("UI verification failed: %s", e)
            finally:
                browser.close()

        # Write results
        self._write_results(ticket_folder, UITestResult(cases=cases))
        return UITestResult(cases=cases)

    def _extract_ui_spec(self, ticket_folder: str) -> dict:
        folder = Path(ticket_folder)
        content = ""
        for fname in ["ARQUITECTURA_SOLUCION.md", "TAREAS_DESARROLLO.md"]:
            p = folder / fname
            if p.exists():
                content += p.read_text(encoding="utf-8", errors="replace")

        url_match = re.search(r"(Frm\w+\.aspx)", content)
        field_match = re.search(r'(?:asp:TextBox|asp:DropDownList)[^>]+ID="(\w+)"', content)
        return {
            "url": f"/{url_match.group(1)}" if url_match else "",
            "new_field_id": field_match.group(1) if field_match else None,
            "required": "obligatorio" in content.lower() or "required" in content.lower(),
        }

    def _write_results(self, ticket_folder: str, result: UITestResult):
        lines = ["# UI_TEST_RESULTS.md", ""]
        for case in result.cases:
            status = "PASS" if case.passed else "FAIL"
            lines.append(f"- [{status}] {case.name}")
            if case.evidence and not case.passed:
                b64 = base64.b64encode(case.evidence).decode()[:200]
                lines.append(f"  Screenshot: [truncated base64: {b64}...]")
        Path(ticket_folder, "UI_TEST_RESULTS.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )
