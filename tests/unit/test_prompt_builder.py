"""Tests unitarios para prompt_builder.py — construcción de prompts para agentes del pipeline."""

import os
import sys
import re
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from prompt_builder import (
    build_pm_prompt,
    build_dev_prompt,
    build_tester_prompt,
    build_retry_prompt,
    build_error_fix_prompt,
    build_rework_prompt,
    build_doc_agent_prompt,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

TICKET_ID = "0099999"
PROJECT_NAME = "RSPACIFICO"

SENSITIVE_PATTERNS = re.compile(
    r"(Bearer\s+[A-Za-z0-9\-._~+/]+=*"
    r"|password\s*[:=]\s*\S+"
    r"|token\s*[:=]\s*\S+"
    r"|api[_-]?key\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


@pytest.fixture
def workspace_root(tmp_path):
    return tmp_path


@pytest.fixture
def ticket_folder(tmp_path):
    folder = tmp_path / "Tools" / "Stacky" / "projects" / PROJECT_NAME / "tickets" / "asignada" / TICKET_ID
    folder.mkdir(parents=True)
    return folder


@pytest.fixture
def ticket_with_inc(ticket_folder):
    """Ticket folder con INC file básico."""
    (ticket_folder / f"INC-{TICKET_ID}.md").write_text(
        f"# INC-{TICKET_ID}\n\nDescripción del error de prueba.\nMódulo: Batch/Negocio\n",
        encoding="utf-8",
    )
    return ticket_folder


@pytest.fixture
def ticket_with_pm_output(ticket_with_inc):
    """Ticket folder con artefactos PM completados."""
    (ticket_with_inc / "ANALISIS_TECNICO.md").write_text(
        "# Análisis Técnico\n\nCausa raíz: error en EjemploDalc.cs línea 42\n",
        encoding="utf-8",
    )
    (ticket_with_inc / "ARQUITECTURA_SOLUCION.md").write_text(
        "# Arquitectura\n\nArchivo: Batch/Negocio/EjemploDalc.cs\nCambio: corregir query\n",
        encoding="utf-8",
    )
    (ticket_with_inc / "TAREAS_DESARROLLO.md").write_text(
        "# Tareas\n- [ ] Corregir query en EjemploDalc.cs\n- [ ] Agregar RIDIOMA\n",
        encoding="utf-8",
    )
    (ticket_with_inc / "NOTAS_IMPLEMENTACION.md").write_text(
        "# Notas\n\nUsar RIDIOMA para mensajes. Oracle DAL sin EF.\n",
        encoding="utf-8",
    )
    return ticket_with_inc


@pytest.fixture
def ticket_with_dev_output(ticket_with_pm_output):
    """Ticket folder con artefactos DEV completados."""
    (ticket_with_pm_output / "DEV_COMPLETADO.md").write_text(
        "# DEV Completado\n\n## Archivos modificados\n- Batch/Negocio/EjemploDalc.cs\n"
        "## Resumen\nSe corrigió la query.\n",
        encoding="utf-8",
    )
    (ticket_with_pm_output / "GIT_CHANGES.md").write_text(
        "fix(Batch): corregir query en EjemploDalc.cs\n",
        encoding="utf-8",
    )
    return ticket_with_pm_output


# ─── Tests PM Prompt ────────────────────────────────────────────────────────

class TestBuildPmPrompt:
    def test_includes_ticket_id(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert TICKET_ID in prompt

    def test_includes_inc_file_reference(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert f"INC-{TICKET_ID}.md" in prompt

    def test_includes_phase_structure(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert "FASE 1" in prompt
        assert "FASE 2" in prompt
        assert "FASE 3" in prompt

    def test_includes_pm_completado_flag(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert "PM_COMPLETADO.flag" in prompt

    def test_includes_pm_error_flag(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert "PM_ERROR.flag" in prompt

    def test_includes_relative_folder(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        # Should contain relative path, not absolute
        assert str(workspace_root) not in prompt or "Carpeta" in prompt

    def test_nota_pm_included_when_exists(self, ticket_with_inc, workspace_root):
        (ticket_with_inc / "NOTA_PM.md").write_text(
            "Contexto adicional: revisar tabla CLIENTES", encoding="utf-8"
        )
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert "Contexto adicional" in prompt or "NOTA_PM" in prompt

    def test_no_sensitive_data_in_prompt(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert not SENSITIVE_PATTERNS.search(prompt), \
            f"Prompt PM contiene datos sensibles: {SENSITIVE_PATTERNS.search(prompt).group()}"

    def test_project_docs_note_when_missing(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert "PROJECT_DOCS.md" in prompt

    def test_project_docs_note_when_exists(self, ticket_with_inc, workspace_root):
        (ticket_with_inc / "PROJECT_DOCS.md").write_text(
            "# Project Docs\nArquitectura del proyecto...", encoding="utf-8"
        )
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert "PROJECT_DOCS" in prompt
        # Should reference reading the docs file
        assert "Leé" in prompt or "contexto" in prompt.lower()

    def test_returns_string(self, ticket_with_inc, workspace_root):
        prompt = build_pm_prompt(str(ticket_with_inc), TICKET_ID, str(workspace_root))
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # non-trivial prompt


# ─── Tests DEV Prompt ───────────────────────────────────────────────────────

class TestBuildDevPrompt:
    def test_includes_ticket_id(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert TICKET_ID in prompt

    def test_includes_architecture_references(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert "ARQUITECTURA_SOLUCION.md" in prompt

    def test_includes_tareas_reference(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert "TAREAS_DESARROLLO.md" in prompt

    def test_includes_dev_completado_signal(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert "DEV_COMPLETADO.md" in prompt

    def test_includes_dev_error_flag(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert "DEV_ERROR.flag" in prompt

    def test_includes_phase_structure(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert "FASE 1" in prompt
        assert "FASE 2" in prompt
        assert "FASE 3" in prompt

    def test_references_analisis_tecnico(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert "ANALISIS_TECNICO.md" in prompt

    def test_includes_ridioma_convention(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert "RIDIOMA" in prompt

    def test_no_sensitive_data_in_prompt(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert not SENSITIVE_PATTERNS.search(prompt), \
            f"Prompt DEV contiene datos sensibles: {SENSITIVE_PATTERNS.search(prompt).group()}"

    def test_returns_string(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert isinstance(prompt, str)
        assert len(prompt) > 100


# ─── Tests Tester Prompt ────────────────────────────────────────────────────

class TestBuildTesterPrompt:
    def test_includes_ticket_id(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert TICKET_ID in prompt

    def test_includes_dev_completado_content(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert "DEV_COMPLETADO" in prompt

    def test_includes_tester_completado_signal(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert "TESTER_COMPLETADO.md" in prompt

    def test_includes_tester_error_flag(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert "TESTER_ERROR.flag" in prompt

    def test_includes_code_review_phase(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert "CODE REVIEW" in prompt or "CODE_REVIEW" in prompt

    def test_includes_acceptance_criteria_section(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        # TAREAS_DESARROLLO.md content should be injected as acceptance criteria
        assert "Criterios de aceptación" in prompt or "TAREAS_DESARROLLO" in prompt

    def test_includes_git_changes_section(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert "GIT_CHANGES" in prompt

    def test_includes_veredicto_options(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert "APROBADO" in prompt
        assert "RECHAZADO" in prompt

    def test_includes_modified_files_hint(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        # DEV_COMPLETADO.md mentions EjemploDalc.cs — should be extracted
        assert "EjemploDalc.cs" in prompt

    def test_no_sensitive_data_in_prompt(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert not SENSITIVE_PATTERNS.search(prompt), \
            f"Prompt Tester contiene datos sensibles: {SENSITIVE_PATTERNS.search(prompt).group()}"

    def test_returns_string(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_without_dev_completado(self, ticket_with_pm_output, workspace_root):
        """Tester prompt should still work even without DEV_COMPLETADO.md."""
        prompt = build_tester_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert isinstance(prompt, str)
        assert TICKET_ID in prompt


# ─── Tests Retry Prompt ─────────────────────────────────────────────────────

class _FakeValidationResult:
    """Simula ValidationResult para testing."""
    def __init__(self, issues=None):
        self.issues = issues or []


class TestBuildRetryPrompt:
    def test_includes_retry_context(self, ticket_with_inc, workspace_root):
        prompt = build_retry_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", retry_num=2,
        )
        assert "REINTENTO" in prompt
        assert "2" in prompt

    def test_includes_stage_label(self, ticket_with_inc, workspace_root):
        prompt = build_retry_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", retry_num=1,
        )
        assert "PM" in prompt.upper()

    def test_includes_ticket_id(self, ticket_with_inc, workspace_root):
        prompt = build_retry_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="dev", retry_num=1,
        )
        assert TICKET_ID in prompt

    def test_lists_existing_files(self, ticket_with_pm_output, workspace_root):
        prompt = build_retry_prompt(
            str(ticket_with_pm_output), TICKET_ID, str(workspace_root),
            stage="pm", retry_num=1,
        )
        assert "ANALISIS_TECNICO.md" in prompt
        assert "bytes" in prompt

    def test_includes_validation_issues(self, ticket_with_inc, workspace_root):
        vr = _FakeValidationResult(issues=[
            "ANALISIS_TECNICO.md tiene placeholder sin resolver",
            "TAREAS_DESARROLLO.md está vacío",
        ])
        prompt = build_retry_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", retry_num=1,
            validation_result=vr,
        )
        assert "placeholder" in prompt.lower()
        assert "TAREAS_DESARROLLO" in prompt

    def test_includes_partial_content_on_issues(self, ticket_with_pm_output, workspace_root):
        vr = _FakeValidationResult(issues=[
            "ANALISIS_TECNICO.md tiene contenido insuficiente",
        ])
        prompt = build_retry_prompt(
            str(ticket_with_pm_output), TICKET_ID, str(workspace_root),
            stage="pm", retry_num=1,
            validation_result=vr,
        )
        # Should include partial content of mentioned file
        assert "Contenido actual" in prompt or "Contenido parcial" in prompt

    def test_dev_retry(self, ticket_with_pm_output, workspace_root):
        prompt = build_retry_prompt(
            str(ticket_with_pm_output), TICKET_ID, str(workspace_root),
            stage="dev", retry_num=3,
        )
        assert "REINTENTO 3" in prompt
        assert "DEV_COMPLETADO" in prompt

    def test_tester_retry(self, ticket_with_dev_output, workspace_root):
        prompt = build_retry_prompt(
            str(ticket_with_dev_output), TICKET_ID, str(workspace_root),
            stage="tester", retry_num=1,
        )
        assert "TESTER_COMPLETADO" in prompt

    def test_no_sensitive_data_in_prompt(self, ticket_with_inc, workspace_root):
        prompt = build_retry_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", retry_num=1,
        )
        assert not SENSITIVE_PATTERNS.search(prompt), \
            f"Prompt Retry contiene datos sensibles: {SENSITIVE_PATTERNS.search(prompt).group()}"


# ─── Tests Error Fix Prompt ─────────────────────────────────────────────────

class TestBuildErrorFixPrompt:
    def test_includes_error_context(self, ticket_with_inc, workspace_root):
        prompt = build_error_fix_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", error_context="No se encontró la tabla CLIENTES en la BD",
        )
        assert "No se encontró la tabla CLIENTES" in prompt

    def test_includes_ticket_id(self, ticket_with_inc, workspace_root):
        prompt = build_error_fix_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="dev", error_context="Error de compilación",
        )
        assert TICKET_ID in prompt

    def test_includes_stage_label(self, ticket_with_inc, workspace_root):
        prompt = build_error_fix_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", error_context="Error",
        )
        assert "PM" in prompt.upper()

    def test_includes_inc_content(self, ticket_with_inc, workspace_root):
        prompt = build_error_fix_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", error_context="Error",
        )
        assert "Descripción del error de prueba" in prompt

    def test_no_sensitive_data_in_prompt(self, ticket_with_inc, workspace_root):
        prompt = build_error_fix_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", error_context="Error genérico",
        )
        assert not SENSITIVE_PATTERNS.search(prompt)


# ─── Tests Rework Prompt ────────────────────────────────────────────────────

class TestBuildReworkPrompt:
    def test_includes_ticket_id(self, ticket_with_dev_output, workspace_root):
        prompt = build_rework_prompt(
            str(ticket_with_dev_output), TICKET_ID, str(workspace_root),
            qa_findings=["Query sin WHERE clause en línea 55"],
            rework_num=1,
        )
        assert TICKET_ID in prompt

    def test_includes_qa_findings(self, ticket_with_dev_output, workspace_root):
        findings = [
            "Falta validación de NULL en EjemploDalc.cs:42",
            "RIDIOMA no insertado para mensaje nuevo",
        ]
        prompt = build_rework_prompt(
            str(ticket_with_dev_output), TICKET_ID, str(workspace_root),
            qa_findings=findings,
            rework_num=1,
        )
        assert "NULL" in prompt
        assert "RIDIOMA" in prompt

    def test_includes_rework_number(self, ticket_with_dev_output, workspace_root):
        prompt = build_rework_prompt(
            str(ticket_with_dev_output), TICKET_ID, str(workspace_root),
            qa_findings=["Issue"],
            rework_num=2,
        )
        assert "2" in prompt
        assert "REWORK" in prompt.upper()

    def test_no_sensitive_data_in_prompt(self, ticket_with_dev_output, workspace_root):
        prompt = build_rework_prompt(
            str(ticket_with_dev_output), TICKET_ID, str(workspace_root),
            qa_findings=["Fix needed"],
            rework_num=1,
        )
        assert not SENSITIVE_PATTERNS.search(prompt)


# ─── Tests Doc Agent Prompt ─────────────────────────────────────────────────

class TestBuildDocAgentPrompt:
    def test_includes_ticket_id(self, ticket_with_dev_output, workspace_root):
        kb_path = str(workspace_root / "KNOWLEDGE_BASE.md")
        prompt = build_doc_agent_prompt(
            str(ticket_with_dev_output), TICKET_ID, str(workspace_root), kb_path,
        )
        assert TICKET_ID in prompt

    def test_includes_kb_path(self, ticket_with_dev_output, workspace_root):
        kb_path = str(workspace_root / "KNOWLEDGE_BASE.md")
        prompt = build_doc_agent_prompt(
            str(ticket_with_dev_output), TICKET_ID, str(workspace_root), kb_path,
        )
        assert "KNOWLEDGE_BASE.md" in prompt

    def test_returns_string(self, ticket_with_dev_output, workspace_root):
        kb_path = str(workspace_root / "KNOWLEDGE_BASE.md")
        prompt = build_doc_agent_prompt(
            str(ticket_with_dev_output), TICKET_ID, str(workspace_root), kb_path,
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 100


# ─── Tests de seguridad transversales ───────────────────────────────────────

class TestNoSensitiveDataLeaks:
    """Verifica que ningún prompt builder inyecte datos sensibles."""

    def test_pm_with_sensitive_inc(self, ticket_folder, workspace_root):
        """INC con tokens no debería filtrar al prompt (tokens en archivo, no en prompt template)."""
        (ticket_folder / f"INC-{TICKET_ID}.md").write_text(
            "# Bug\nEl sistema falla.\n", encoding="utf-8"
        )
        prompt = build_pm_prompt(str(ticket_folder), TICKET_ID, str(workspace_root))
        # The prompt template itself should not contain sensitive patterns
        assert not SENSITIVE_PATTERNS.search(prompt)

    def test_dev_prompt_no_secrets(self, ticket_with_pm_output, workspace_root):
        prompt = build_dev_prompt(str(ticket_with_pm_output), TICKET_ID, str(workspace_root))
        assert not SENSITIVE_PATTERNS.search(prompt)

    def test_tester_prompt_no_secrets(self, ticket_with_dev_output, workspace_root):
        prompt = build_tester_prompt(str(ticket_with_dev_output), TICKET_ID, str(workspace_root))
        assert not SENSITIVE_PATTERNS.search(prompt)

    def test_retry_prompt_no_secrets(self, ticket_with_inc, workspace_root):
        prompt = build_retry_prompt(
            str(ticket_with_inc), TICKET_ID, str(workspace_root),
            stage="pm", retry_num=1,
        )
        assert not SENSITIVE_PATTERNS.search(prompt)
