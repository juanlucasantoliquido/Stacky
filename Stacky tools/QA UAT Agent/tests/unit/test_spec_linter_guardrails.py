from pathlib import Path


def test_spec_linter_blocks_direct_goto_and_retries(tmp_path):
    from spec_linter import lint_directory

    spec = tmp_path / "P01.spec.ts"
    spec.write_text(
        """
import { test } from '@playwright/test';
test('bad deterministic spec', async ({ page }) => {
  await page.goto(`${BASE_URL}FrmBusqueda.aspx`);
  const plan = { steps: [{ method: 'goto_direct', retries: 2 }] };
  await helper({ maxAttempts: 3 });
});
""",
        encoding="utf-8",
    )

    result = lint_directory(tmp_path)

    assert result["ok"] is False
    assert result["reason"] == "INVALID_GENERATED_SPEC_GUARDRAIL"
    descriptions = " ".join(v["description"] for v in result["violations"])
    assert "Direct page.goto" in descriptions
    assert "retries greater than 0" in descriptions
    assert "maxAttempts greater than 1" in descriptions


def test_spec_linter_blocks_placeholders_force_and_credentials(tmp_path):
    from spec_linter import lint_single

    spec = tmp_path / "P02.spec.ts"
    spec.write_text(
        """
test('bad placeholders', async ({ page }) => {
  await page.locator('#x').click({ force: true });
  const password = process.env.AGENDA_WEB_PASS;
  const value = "{{CLCOD}}";
});
""",
        encoding="utf-8",
    )

    result = lint_single(spec)

    assert result["ok"] is False
    descriptions = " ".join(v["description"] for v in result["violations"])
    assert "force:true" in descriptions
    assert "AGENDA_WEB_PASS" in descriptions
    assert "placeholder" in descriptions.lower()
