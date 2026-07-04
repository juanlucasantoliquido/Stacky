"""
Test de contrato anti-drift para Plan 92: reforja agente StackyArchitectaUltraEficientCode.

Valida que el agente esté versionado en el repo con estructura de perfiles correcta.
"""

from pathlib import Path


def resolve_repo_root():
    """Resuelve la raíz del repo desde este archivo."""
    return Path(__file__).resolve().parents[2]


def test_agente_ultraeficient_existe_en_repo():
    """Test: existe `.claude/agents/StackyArchitectaUltraEficientCode.md`"""
    repo_root = resolve_repo_root()
    agent_file = repo_root / ".claude" / "agents" / "StackyArchitectaUltraEficientCode.md"
    assert agent_file.exists(), f"Archivo no encontrado: {agent_file}"


def test_agente_tiene_perfiles():
    """Test: contenido incluye `## Perfil eco`, `## Perfil normal`, `## Perfil max` y `default: herencia`"""
    repo_root = resolve_repo_root()
    agent_file = repo_root / ".claude" / "agents" / "StackyArchitectaUltraEficientCode.md"
    content = agent_file.read_text(encoding="utf-8")

    assert "## Perfil eco" in content, "Falta sección '## Perfil eco'"
    assert "## Perfil normal" in content, "Falta sección '## Perfil normal'"
    assert "## Perfil max" in content, "Falta sección '## Perfil max'"
    assert "default: herencia" in content, "Falta 'default: herencia'"


def test_agente_regla_implementacion_core():
    """Test: incluye la cadena exacta `NUNCA delegues la implementación core a un modelo menor`"""
    repo_root = resolve_repo_root()
    agent_file = repo_root / ".claude" / "agents" / "StackyArchitectaUltraEficientCode.md"
    content = agent_file.read_text(encoding="utf-8")

    assert "NUNCA delegues la implementación core a un modelo menor" in content, \
        "Falta regla exacta de implementación core"


def test_agente_reporta_perfil_activo():
    """Test: incluye la cadena exacta `Perfil activo:`"""
    repo_root = resolve_repo_root()
    agent_file = repo_root / ".claude" / "agents" / "StackyArchitectaUltraEficientCode.md"
    content = agent_file.read_text(encoding="utf-8")

    assert "Perfil activo:" in content, "Falta obligación de reportar 'Perfil activo:'"


def test_skill_criticar_sin_haiku_forzado():
    """Test: `.claude/skills/criticar-y-mejorar-plan/SKILL.md` NO contiene `corré con model haiku`"""
    repo_root = resolve_repo_root()
    skill_file = repo_root / ".claude" / "skills" / "criticar-y-mejorar-plan" / "SKILL.md"
    assert skill_file.exists(), f"Skill no encontrada: {skill_file}"

    content = skill_file.read_text(encoding="utf-8")
    assert "corré con model haiku" not in content, \
        "Skill aún contiene 'corré con model haiku' (hardcodeado a Haiku)"


def test_toml_codex_menciona_perfiles():
    """Test: `.codex/agents/stacky-architecta-ultra-eficient-code.toml` contiene `PERFIL` y `herencia`"""
    repo_root = resolve_repo_root()
    toml_file = repo_root / ".codex" / "agents" / "stacky-architecta-ultra-eficient-code.toml"
    assert toml_file.exists(), f"Archivo TOML no encontrado: {toml_file}"

    content = toml_file.read_text(encoding="utf-8")
    assert "PERFIL" in content, "Falta 'PERFIL' en TOML"
    assert "herencia" in content, "Falta 'herencia' en TOML"
