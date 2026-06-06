"""Tests del módulo canonical Stacky/agents (plan-agentes-bundled-en-stacky-2026-05-29).

Cubre:
- Resolución `stacky_home()` / `stacky_agents_dir()` con env overrides.
- Materialización desde fuentes externas hacia ``<STACKY_HOME>/agents``.
- Generación de ``manifest.json`` con `@mention`, checksum, source.
- Construcción del bloque de invocación que todos los runners deben inyectar.
- Helper ``build_entry_from_path()`` para runners.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import runtime_paths  # noqa: E402
from services import stacky_agents  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Aísla STACKY_HOME / STACKY_AGENTS_DIR por test y apunta a tmp_path."""
    home = tmp_path / "deploy" / "Stacky"
    monkeypatch.setenv("STACKY_HOME", str(home))
    monkeypatch.delenv("STACKY_AGENTS_DIR", raising=False)
    yield home


def _write_agent(directory: Path, filename: str, *, description: str = "", body: str = "contenido del agente") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    if description:
        text = f"---\ndescription: {description}\n---\n\n{body}\n"
    else:
        text = f"# {filename}\n\n{body}\n"
    path = directory / filename
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Resolución
# ---------------------------------------------------------------------------

def test_stacky_home_default_is_app_root_stacky(monkeypatch, tmp_path):
    monkeypatch.delenv("STACKY_HOME", raising=False)
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "app_root", lambda: tmp_path)

    assert runtime_paths.stacky_home() == (tmp_path / "Stacky").resolve()


def test_stacky_home_env_override_wins(monkeypatch, tmp_path):
    target = tmp_path / "custom-home"
    monkeypatch.setenv("STACKY_HOME", str(target))
    monkeypatch.setattr(runtime_paths, "app_root", lambda: tmp_path / "other")

    assert runtime_paths.stacky_home() == target.resolve()


def test_stacky_agents_dir_default(monkeypatch, tmp_path):
    monkeypatch.setenv("STACKY_HOME", str(tmp_path / "deploy" / "Stacky"))
    monkeypatch.delenv("STACKY_AGENTS_DIR", raising=False)

    assert runtime_paths.stacky_agents_dir() == (tmp_path / "deploy" / "Stacky" / "agents").resolve()


def test_stacky_agents_dir_env_override(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere" / "agents"
    monkeypatch.setenv("STACKY_AGENTS_DIR", str(target))

    assert runtime_paths.stacky_agents_dir() == target.resolve()


def test_ensure_stacky_agents_dir_creates_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_HOME", str(tmp_path / "Stacky"))

    result = runtime_paths.ensure_stacky_agents_dir()

    assert result.exists()
    assert result.is_dir()
    assert result.name == "agents"


# ---------------------------------------------------------------------------
# Materialización + manifest
# ---------------------------------------------------------------------------

def test_materialize_copies_from_external_sources(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _write_agent(src, "Developer.agent.md", description="Developer Stacky")
    _write_agent(src, "Functional.agent.md", description="Analista funcional")

    entries = stacky_agents.materialize_agents(sources=[src])

    canonical = runtime_paths.stacky_agents_dir()
    assert canonical.is_dir()
    assert (canonical / "Developer.agent.md").is_file()
    assert (canonical / "Functional.agent.md").is_file()
    assert {e.filename for e in entries} == {"Developer.agent.md", "Functional.agent.md"}


def test_materialize_without_sources_reads_canonical_only(tmp_path):
    canonical = runtime_paths.ensure_stacky_agents_dir()
    _write_agent(canonical, "Developer.agent.md", description="Developer Stacky")

    entries = stacky_agents.materialize_agents()

    assert {e.filename for e in entries} == {"Developer.agent.md"}
    assert (canonical / "manifest.json").is_file()


def test_materialize_does_not_overwrite_existing(tmp_path):
    src = tmp_path / "src"
    _write_agent(src, "Developer.agent.md", body="versión original")
    stacky_agents.materialize_agents(sources=[src])

    canonical = runtime_paths.stacky_agents_dir()
    # operador editó el agente en el deploy
    (canonical / "Developer.agent.md").write_text(
        "# Developer\n\nedición local\n", encoding="utf-8"
    )

    # nueva versión upstream cambia el body — pero NO debe pisar la edición local
    _write_agent(src, "Developer.agent.md", body="nueva versión upstream")
    stacky_agents.materialize_agents(sources=[src])

    body = (canonical / "Developer.agent.md").read_text(encoding="utf-8")
    assert "edición local" in body
    assert "nueva versión upstream" not in body


def test_materialize_force_overwrites_existing(tmp_path):
    src = tmp_path / "src"
    _write_agent(src, "Developer.agent.md", body="upstream nuevo")
    canonical = runtime_paths.ensure_stacky_agents_dir()
    (canonical / "Developer.agent.md").write_text("# vieja\n", encoding="utf-8")

    stacky_agents.materialize_agents(sources=[src], force=True)

    body = (canonical / "Developer.agent.md").read_text(encoding="utf-8")
    assert "upstream nuevo" in body


def test_manifest_contains_mention_path_and_checksum(tmp_path):
    src = tmp_path / "src"
    _write_agent(src, "Developer.agent.md", description="Implementa cambios")

    stacky_agents.materialize_agents(sources=[src])
    manifest = stacky_agents.read_manifest()

    assert manifest is not None
    assert manifest["schema_version"] == 1
    assert manifest["stacky_home"].endswith("/Stacky") or manifest["stacky_home"].endswith("\\Stacky")
    agents = manifest["agents"]
    assert len(agents) == 1
    dev = agents[0]
    assert dev["name"] == "Developer"
    assert dev["mention"] == "@Developer"
    assert dev["filename"] == "Developer.agent.md"
    assert dev["path"].endswith("/Developer.agent.md")
    assert dev["relative_path"] == "Developer.agent.md"
    assert dev["description"] == "Implementa cambios"
    assert len(dev["checksum_sha256"]) == 64  # sha256 hex
    assert dev["source"] in {
        stacky_agents.SOURCE_BUNDLED,
        stacky_agents.SOURCE_CUSTOM,
        stacky_agents.SOURCE_IMPORTED,
    }


def test_manifest_persists_to_disk(tmp_path):
    src = tmp_path / "src"
    _write_agent(src, "QA.agent.md", description="Quality Assurance")
    stacky_agents.materialize_agents(sources=[src])

    manifest_path = runtime_paths.stacky_agents_dir() / "manifest.json"
    assert manifest_path.is_file()
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "agents" in parsed
    assert parsed["agents"][0]["filename"] == "QA.agent.md"


def test_first_source_wins_for_duplicate_filenames(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    _write_agent(a, "Developer.agent.md", body="fuente A")
    _write_agent(b, "Developer.agent.md", body="fuente B")

    entries = stacky_agents.materialize_agents(sources=[a, b])

    canonical = runtime_paths.stacky_agents_dir()
    body = (canonical / "Developer.agent.md").read_text(encoding="utf-8")
    assert "fuente A" in body
    assert "fuente B" not in body
    assert len([e for e in entries if e.filename == "Developer.agent.md"]) == 1


# ---------------------------------------------------------------------------
# Lookup + entry building
# ---------------------------------------------------------------------------

def test_get_canonical_agent_returns_entry(tmp_path):
    src = tmp_path / "src"
    _write_agent(src, "Developer.agent.md", description="Dev")
    stacky_agents.materialize_agents(sources=[src])

    entry = stacky_agents.get_canonical_agent("Developer.agent.md")
    assert entry is not None
    assert entry.name == "Developer"
    assert entry.mention == "@Developer"
    assert entry.path.exists()


def test_get_canonical_agent_rejects_path_traversal(tmp_path):
    runtime_paths.ensure_stacky_agents_dir()

    assert stacky_agents.get_canonical_agent("../etc/passwd") is None
    assert stacky_agents.get_canonical_agent("../../foo.agent.md") is None


def test_get_canonical_agent_rejects_non_agent_extension(tmp_path):
    runtime_paths.ensure_stacky_agents_dir()
    assert stacky_agents.get_canonical_agent("foo.txt") is None
    assert stacky_agents.get_canonical_agent("foo.md") is None


def test_build_entry_from_path_works_outside_canonical(tmp_path):
    src = tmp_path / "external"
    _write_agent(src, "Developer.agent.md", description="Extern Dev")

    entry = stacky_agents.build_entry_from_path(src / "Developer.agent.md")

    assert entry is not None
    assert entry.name == "Developer"
    assert entry.mention == "@Developer"
    assert entry.description == "Extern Dev"
    assert len(entry.checksum_sha256) == 64


def test_build_entry_from_path_returns_none_when_missing(tmp_path):
    assert stacky_agents.build_entry_from_path(tmp_path / "missing.agent.md") is None


# ---------------------------------------------------------------------------
# Invocation contract
# ---------------------------------------------------------------------------

def test_invocation_block_contains_mention_path_and_workspace(tmp_path):
    src = tmp_path / "src"
    _write_agent(src, "Developer.agent.md", description="Dev")
    entries = stacky_agents.materialize_agents(sources=[src])
    dev = entries[0]

    block = stacky_agents.build_invocation_block(
        entry=dev,
        workspace_root="C:/proyecto/cliente",
    )

    assert "## Agente Stacky seleccionado" in block
    assert "@Developer" in block
    assert "Developer.agent.md" in block
    assert "Workspace de trabajo: C:/proyecto/cliente" in block
    assert "STACKY_HOME" in block
    assert "Carpeta de agentes" in block


def test_invocation_metadata_includes_all_keys(tmp_path):
    src = tmp_path / "src"
    _write_agent(src, "Developer.agent.md", description="Dev")
    entries = stacky_agents.materialize_agents(sources=[src])
    dev = entries[0]

    meta = stacky_agents.invocation_metadata(entry=dev, workspace_root="C:/proyecto")
    for key in (
        "agent_mention",
        "agent_name",
        "agent_filename",
        "agent_path",
        "agent_checksum_sha256",
        "agent_source",
        "agents_dir",
        "stacky_home",
        "workspace_root",
    ):
        assert key in meta, f"falta {key} en invocation_metadata"


# ---------------------------------------------------------------------------
# Import endpoint helper
# ---------------------------------------------------------------------------

def test_import_agent_from_path_copies_and_updates_manifest(tmp_path):
    src = tmp_path / "external" / "Custom.agent.md"
    src.parent.mkdir(parents=True)
    src.write_text("---\ndescription: agente importado\n---\n\ncuerpo\n", encoding="utf-8")

    entry = stacky_agents.import_agent_from_path(src)

    canonical = runtime_paths.stacky_agents_dir()
    assert (canonical / "Custom.agent.md").is_file()
    assert entry.name == "Custom"
    manifest = stacky_agents.read_manifest()
    assert any(a["filename"] == "Custom.agent.md" for a in manifest["agents"])


def test_import_agent_fails_when_target_exists_without_overwrite(tmp_path):
    src = tmp_path / "Custom.agent.md"
    src.write_text("# v1\n", encoding="utf-8")
    stacky_agents.import_agent_from_path(src)

    src2 = tmp_path / "Custom.agent.md"
    src2.write_text("# v2\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        stacky_agents.import_agent_from_path(src2)


def test_import_agent_overwrite_replaces_target(tmp_path):
    src = tmp_path / "Custom.agent.md"
    src.write_text("# v1\n", encoding="utf-8")
    stacky_agents.import_agent_from_path(src)

    src.write_text("# v2 nueva\n", encoding="utf-8")
    entry = stacky_agents.import_agent_from_path(src, overwrite=True)

    body = entry.path.read_text(encoding="utf-8")
    assert "v2 nueva" in body


def test_import_agent_rejects_non_agent_extension(tmp_path):
    src = tmp_path / "foo.txt"
    src.write_text("# foo\n", encoding="utf-8")

    with pytest.raises(ValueError):
        stacky_agents.import_agent_from_path(src)


def test_import_agent_fast_fail_when_source_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        stacky_agents.import_agent_from_path(tmp_path / "no_existe.agent.md")


# ---------------------------------------------------------------------------
# Validación de deploy (check_deploy_agents.py) — plan §5 / §9
# ---------------------------------------------------------------------------

def _load_check_deploy_agents():
    """Carga el script de validación pre-release como módulo aislado."""
    import importlib.util

    script = ROOT.parent / "deployment" / "check_deploy_agents.py"
    assert script.is_file(), f"no encontré check_deploy_agents.py en {script}"
    spec = importlib.util.spec_from_file_location("check_deploy_agents", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _materialize_into_canonical(src_dir: Path) -> Path:
    """Materializa un agente externo al canonical y devuelve el stacky_home."""
    _write_agent(src_dir, "Developer.agent.md", description="dev")
    stacky_agents.materialize_agents(sources=[src_dir])
    return stacky_agents.stacky_home()


def test_deploy_package_contains_stacky_agents(tmp_path):
    """El paquete materializado pasa la validación pre-release (manifest + checksum)."""
    check = _load_check_deploy_agents()
    home = _materialize_into_canonical(tmp_path / "external")

    ok, errors = check.validate(home)
    assert ok, f"validación falló inesperadamente: {errors}"
    assert errors == []
    assert (home / "agents" / "manifest.json").is_file()


def test_deploy_validation_fails_when_agents_dir_empty(tmp_path):
    """Bloquea publicación si Stacky/agents no tiene .agent.md (plan §5.4)."""
    check = _load_check_deploy_agents()
    home = stacky_agents.ensure_stacky_home()
    (home / "agents").mkdir(parents=True, exist_ok=True)

    ok, errors = check.validate(home)
    assert not ok
    assert any("*.agent.md" in e for e in errors)


def test_deploy_validation_detects_checksum_mismatch(tmp_path):
    """Detecta corrupción: el .agent.md no coincide con el checksum del manifest."""
    check = _load_check_deploy_agents()
    home = _materialize_into_canonical(tmp_path / "external")

    # Editar el agente en disco sin regenerar el manifest → checksum desalineado.
    agent_file = home / "agents" / "Developer.agent.md"
    agent_file.write_text("contenido alterado tras el manifest\n", encoding="utf-8")

    ok, errors = check.validate(home)
    assert not ok
    assert any("checksum" in e.lower() for e in errors)
