"""Tests TDD para H4.2 — stacky_skills service."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_skill(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_load_skills_valid(tmp_path):
    """Carga una skill con frontmatter válido → Skill con campos correctos."""
    from services.stacky_skills import load_skills, _clear_cache

    _write_skill(
        tmp_path,
        "mi-skill.skill.md",
        """\
        ---
        name: mi-skill
        description: Una skill de prueba
        agents: [qa]
        projects: [proyectoA]
        keywords: [plan, regresion]
        ---
        Cuerpo de la skill.
        """,
    )
    _clear_cache()
    skills = load_skills(root=tmp_path)
    assert len(skills) == 1
    s = skills[0]
    assert s.name == "mi-skill"
    assert s.description == "Una skill de prueba"
    assert s.agents == ("qa",)
    assert s.projects == ("proyectoa",)  # lowercase
    assert "plan" in s.keywords
    assert "Cuerpo de la skill." in s.body
    assert s.path.endswith(".skill.md")


def test_load_skills_broken_frontmatter(tmp_path):
    """Un .skill.md con frontmatter roto → se skipea (no crash), el resto carga."""
    from services.stacky_skills import load_skills, _clear_cache

    _write_skill(
        tmp_path,
        "buena.skill.md",
        """\
        ---
        name: buena
        description: Skill válida
        agents: []
        projects: []
        keywords: [test]
        ---
        Cuerpo bueno.
        """,
    )
    # Frontmatter con YAML inválido (indentación rota que produce error)
    _write_skill(
        tmp_path,
        "rota.skill.md",
        """\
        ---
        name: rota
          agents: [  broken: yaml: here
        ---
        Cuerpo roto.
        """,
    )
    _clear_cache()
    skills = load_skills(root=tmp_path)
    # El roto NO crashea, puede cargarse con fallback o skipearse
    # Lo importante: no hay excepción y "buena" está presente
    names = [s.name for s in skills]
    assert "buena" in names


def test_select_filters_agent(tmp_path):
    """Skill con agents:[qa] no aparece en select para agent_type='dev'."""
    from services.stacky_skills import load_skills, select_for_run, _clear_cache

    _write_skill(
        tmp_path,
        "qa-only.skill.md",
        """\
        ---
        name: qa-only
        description: Solo para QA
        agents: [qa]
        projects: []
        keywords: []
        ---
        Cuerpo QA.
        """,
    )
    _clear_cache()
    result = select_for_run(
        agent_type="dev",
        project=None,
        context_text="cualquier cosa",
        root=tmp_path,
    )
    assert not any(s.name == "qa-only" for s in result)


def test_select_filters_project(tmp_path):
    """Skill con projects:[proyectoX] no aparece para project='proyectoY'."""
    from services.stacky_skills import select_for_run, _clear_cache

    _write_skill(
        tmp_path,
        "px-only.skill.md",
        """\
        ---
        name: px-only
        description: Solo proyecto X
        agents: []
        projects: [proyectoX]
        keywords: []
        ---
        Cuerpo PX.
        """,
    )
    _clear_cache()
    result = select_for_run(
        agent_type="dev",
        project="proyectoY",
        context_text="cualquier cosa",
        root=tmp_path,
    )
    assert not any(s.name == "px-only" for s in result)


def test_select_keywords_match(tmp_path):
    """Skill con keyword presente en context_text → aparece en select."""
    from services.stacky_skills import select_for_run, _clear_cache

    _write_skill(
        tmp_path,
        "kw-skill.skill.md",
        """\
        ---
        name: kw-skill
        description: Skill con keywords
        agents: []
        projects: []
        keywords: [regresion, smoke]
        ---
        Cuerpo kw.
        """,
    )
    _clear_cache()
    result = select_for_run(
        agent_type="qa",
        project=None,
        context_text="Necesitamos hacer un plan de regresion para esta feature",
        root=tmp_path,
    )
    assert any(s.name == "kw-skill" for s in result)


def test_select_keywords_no_match(tmp_path):
    """Skill con keywords que NO están en context_text → no aparece."""
    from services.stacky_skills import select_for_run, _clear_cache

    _write_skill(
        tmp_path,
        "kw-miss.skill.md",
        """\
        ---
        name: kw-miss
        description: Skill sin match
        agents: []
        projects: []
        keywords: [perfromance, benchmark]
        ---
        Cuerpo miss.
        """,
    )
    _clear_cache()
    result = select_for_run(
        agent_type="dev",
        project=None,
        context_text="Implementar endpoint de login",
        root=tmp_path,
    )
    assert not any(s.name == "kw-miss" for s in result)


def test_render_index(tmp_path):
    """render_index genera lineas '- name: description'."""
    from services.stacky_skills import load_skills, render_index, _clear_cache

    _write_skill(
        tmp_path,
        "s1.skill.md",
        """\
        ---
        name: skill-uno
        description: Primera skill
        agents: []
        projects: []
        keywords: []
        ---
        """,
    )
    _write_skill(
        tmp_path,
        "s2.skill.md",
        """\
        ---
        name: skill-dos
        description: Segunda skill
        agents: []
        projects: []
        keywords: []
        ---
        """,
    )
    _clear_cache()
    skills = load_skills(root=tmp_path)
    idx = render_index(skills)
    assert "- skill-uno: Primera skill" in idx
    assert "- skill-dos: Segunda skill" in idx


def test_get_skill_found(tmp_path):
    """get_skill con nombre existente → retorna Skill."""
    from services.stacky_skills import get_skill, _clear_cache

    _write_skill(
        tmp_path,
        "target.skill.md",
        """\
        ---
        name: target-skill
        description: Skill objetivo
        agents: []
        projects: []
        keywords: []
        ---
        Cuerpo objetivo.
        """,
    )
    _clear_cache()
    result = get_skill("target-skill", root=tmp_path)
    assert result is not None
    assert result.name == "target-skill"


def test_get_skill_not_found(tmp_path):
    """get_skill con nombre inexistente → None."""
    from services.stacky_skills import get_skill, _clear_cache

    _clear_cache()
    result = get_skill("no-existe", root=tmp_path)
    assert result is None
