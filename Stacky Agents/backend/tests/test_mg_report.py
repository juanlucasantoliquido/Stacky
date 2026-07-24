"""tests/test_mg_report.py — Plan 217 Batch 5, F7b (§14 + [ADICIÓN 2]).

Valida `tools/migrar_mantis_gitlab/migrator_mg_report.py`:
  - genera ambos formatos (Markdown + JSON) en un `tmp_path`.
  - el Markdown contiene las secciones esperadas.
  - `redact_pii=True` enmascara un email de ejemplo; `redact_pii=False` no.
  - `dry_run=True` incluye `[SIMULACRO]` en ambos formatos.
"""
from __future__ import annotations

import json

from tools.migrar_mantis_gitlab.migrator_mg_executor import MgExecutionResult
from tools.migrar_mantis_gitlab.migrator_mg_report import generate_report
from tools.migrar_mantis_gitlab.migrator_mg_verify import MgVerificationResult


def _verification_con_pii() -> MgVerificationResult:
    return MgVerificationResult(
        total_origin=10,
        total_migrated=9,
        count_gap=1,
        duplicate_markers=["gitlab_iid=100 mapeado a mantis_issue_id=['1', '2']"],
        sample_mismatches=[
            {
                "mantis_issue_id": "5",
                "gitlab_iid": "105",
                "mismatches": [{"field": "title", "expected": "t5", "actual": "t5-corrompido"}],
            }
        ],
        unmapped_fallbacks_used=[
            {"mantis_issue_id": "1", "field": "category", "value": "raro", "fallback_used": "otros"}
        ],
        users_fallback=[
            {
                "mantis_username": "jdoe",
                "full_name": "John Doe",
                "email": "jdoe@example.com",
                "fallback": "unassigned",
            }
        ],
        attachments_skipped=[{"mantis_issue_id": "2", "filename": "big.zip", "size_mb": 120.5}],
        passed=False,
    )


def _execution() -> MgExecutionResult:
    return MgExecutionResult(
        applied=9,
        skipped=1,
        failed=[{"mantis_issue_id": "3", "op_kind": "post_comment", "error": "timeout"}],
        orphaned=["4"],
    )


# ── genera ambos formatos ────────────────────────────────────────────────


def test_genera_markdown_y_json_en_tmp_path(tmp_path):
    paths = generate_report(
        _verification_con_pii(),
        _execution(),
        run_id="run-1",
        project_path="grupo/proyecto",
        formats=["markdown", "json"],
        output_dir=str(tmp_path),
    )

    assert set(paths.keys()) == {"markdown", "json"}
    md_path = tmp_path / "reports" / "grupo_proyecto_run-1.md"
    json_path = tmp_path / "reports" / "grupo_proyecto_run-1.json"
    assert md_path.exists()
    assert json_path.exists()
    assert paths["markdown"] == str(md_path)
    assert paths["json"] == str(json_path)


def test_genera_solo_el_formato_pedido(tmp_path):
    paths = generate_report(
        _verification_con_pii(),
        _execution(),
        run_id="run-2",
        project_path="grupo/proyecto",
        formats=["markdown"],
        output_dir=str(tmp_path),
    )

    assert set(paths.keys()) == {"markdown"}
    assert not (tmp_path / "reports" / "grupo_proyecto_run-2.json").exists()


# ── secciones esperadas en el Markdown ───────────────────────────────────


def test_markdown_contiene_las_secciones_esperadas(tmp_path):
    paths = generate_report(
        _verification_con_pii(),
        _execution(),
        run_id="run-3",
        project_path="grupo/proyecto",
        formats=["markdown"],
        output_dir=str(tmp_path),
    )

    content = open(paths["markdown"], encoding="utf-8").read()

    assert "Resumen ejecutivo" in content
    assert "_unmapped_fallback" in content
    assert "default_fallback" in content
    assert "Adjuntos saltados" in content
    assert "NO migrada" in content
    assert "Markers duplicados" in content
    assert "Diferencias campo a campo" in content
    assert "t5-corrompido" in content
    assert "big.zip" in content


# ── redact-pii ────────────────────────────────────────────────────────────


def test_redact_pii_true_enmascara_email_y_oculta_nombre_completo(tmp_path):
    paths = generate_report(
        _verification_con_pii(),
        _execution(),
        run_id="run-4",
        project_path="grupo/proyecto",
        formats=["markdown", "json"],
        output_dir=str(tmp_path),
        redact_pii=True,
    )

    md_content = open(paths["markdown"], encoding="utf-8").read()
    json_content = open(paths["json"], encoding="utf-8").read()

    assert "jdoe@example.com" not in md_content
    assert "j***@example.com" in md_content
    assert "John Doe" not in md_content

    assert "jdoe@example.com" not in json_content
    assert "j***@example.com" in json_content
    assert "John Doe" not in json_content


def test_redact_pii_false_muestra_email_y_nombre_completo_tal_cual(tmp_path):
    paths = generate_report(
        _verification_con_pii(),
        _execution(),
        run_id="run-5",
        project_path="grupo/proyecto",
        formats=["markdown", "json"],
        output_dir=str(tmp_path),
        redact_pii=False,
    )

    md_content = open(paths["markdown"], encoding="utf-8").read()
    json_content = open(paths["json"], encoding="utf-8").read()

    assert "jdoe@example.com" in md_content
    assert "John Doe" in md_content
    assert "jdoe@example.com" in json_content
    assert "John Doe" in json_content


# ── dry-run marca [SIMULACRO] en ambos formatos ──────────────────────────


def test_dry_run_incluye_simulacro_en_ambos_formatos(tmp_path):
    paths = generate_report(
        _verification_con_pii(),
        _execution(),
        run_id="run-6",
        project_path="grupo/proyecto",
        formats=["markdown", "json"],
        output_dir=str(tmp_path),
        dry_run=True,
    )

    md_content = open(paths["markdown"], encoding="utf-8").read()
    json_content = json.loads(open(paths["json"], encoding="utf-8").read())

    assert "[SIMULACRO]" in md_content
    assert json_content["dry_run"] is True


def test_sin_dry_run_no_incluye_simulacro():
    from tools.migrar_mantis_gitlab.migrator_mg_report import _render_markdown, _build_report_payload

    payload = _build_report_payload(
        _verification_con_pii(), _execution(),
        run_id="run-7", project_path="grupo/proyecto", dry_run=False, relationships=[],
    )
    md = _render_markdown(payload, redact_pii=True)
    assert "[SIMULACRO]" not in md


# ── JSON es machine-readable con el resumen esperado ─────────────────────


def test_json_incluye_resumen_ejecutivo_con_conteos(tmp_path):
    paths = generate_report(
        _verification_con_pii(),
        _execution(),
        run_id="run-8",
        project_path="grupo/proyecto",
        formats=["json"],
        output_dir=str(tmp_path),
    )

    data = json.loads(open(paths["json"], encoding="utf-8").read())
    summary = data["summary"]
    assert summary["issues_migrados"] == 9
    assert summary["issues_origen"] == 10
    assert summary["gap_conteo"] == 1
    assert summary["operaciones_aplicadas_total"] == 9
    assert summary["operaciones_salteadas_idempotencia"] == 1
    assert summary["operaciones_fallidas_total"] == 1
    assert summary["operaciones_fallidas_por_tipo"] == {"post_comment": 1}
    assert summary["issues_huerfanos_sin_padre_resuelto"] == 1
    assert summary["verificacion_aprobada"] is False
