"""Tests de deployment/export_harness_defaults.py.

Cubren lo que importa para el operador:
- Solo se exportan flags del arnés (FLAG_REGISTRY); las credenciales se filtran.
- Precedencia de fuentes: backend\\.env (autoritativo) gana sobre _internal\\.env.
- Sin deploy vivo, NO se pisa el harness_defaults.env versionado existente.
"""
from __future__ import annotations

import sys
from pathlib import Path

DEPLOYMENT_DIR = Path(__file__).resolve().parents[1]
if str(DEPLOYMENT_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOYMENT_DIR))

import export_harness_defaults as ehd  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_env_file_ignores_comments_and_malformed(tmp_path: Path) -> None:
    env = _write(
        tmp_path / ".env",
        "# comentario\n\nSTACKY_QUALITY_KPIS_ENABLED=true\nlinea sin igual\n",
    )
    parsed = ehd.parse_env_file(env)
    assert parsed == {"STACKY_QUALITY_KPIS_ENABLED": "true"}


def test_collect_filters_to_registry_and_drops_credentials(tmp_path: Path) -> None:
    env = _write(
        tmp_path / ".env",
        "ADO_PAT=topsecret\n"
        "ADO_ORG=myorg\n"
        "OPENAI_API_KEY=sk-xxx\n"
        "STACKY_QUALITY_KPIS_ENABLED=true\n"
        "NOT_A_REGISTRY_FLAG=x\n",
    )
    defaults = ehd.collect_harness_defaults([env])
    assert defaults == {"STACKY_QUALITY_KPIS_ENABLED": "true"}
    for leaked in ("ADO_PAT", "ADO_ORG", "OPENAI_API_KEY", "NOT_A_REGISTRY_FLAG"):
        assert leaked not in defaults


def test_collect_last_source_wins(tmp_path: Path) -> None:
    internal = _write(tmp_path / "_internal" / ".env", "STACKY_QUALITY_KPIS_ENABLED=false\n")
    root = _write(tmp_path / ".env", "STACKY_QUALITY_KPIS_ENABLED=true\n")
    # deploy_env_sources devuelve [_internal, backend\.env] → backend\.env gana.
    assert ehd.collect_harness_defaults([internal, root])["STACKY_QUALITY_KPIS_ENABLED"] == "true"


def test_collect_keeps_internal_only_keys_when_root_is_skeleton(tmp_path: Path) -> None:
    internal = _write(tmp_path / "_internal" / ".env", "STACKY_CONTEXT_DEDUP_ENABLED=true\n")
    root = _write(tmp_path / ".env", "LLM_BACKEND=copilot\n")  # skeleton, sin flags del arnés
    defaults = ehd.collect_harness_defaults([internal, root])
    assert defaults == {"STACKY_CONTEXT_DEDUP_ENABLED": "true"}


def test_deploy_env_sources_precedence_order(tmp_path: Path) -> None:
    sources = ehd.deploy_env_sources(tmp_path)
    assert sources[0].as_posix().endswith("backend/_internal/.env")
    assert sources[1].as_posix().endswith("backend/.env")


def test_render_is_sorted_and_has_header(tmp_path: Path) -> None:
    text = ehd.render({"STACKY_B_ENABLED": "1", "STACKY_A_ENABLED": "2"})
    assert text.startswith("# harness_defaults.env")
    body = [line for line in text.splitlines() if "=" in line and not line.startswith("#")]
    assert body == ["STACKY_A_ENABLED=2", "STACKY_B_ENABLED=1"]


def test_main_without_deploy_preserves_existing_versioned_file(
    tmp_path: Path, monkeypatch
) -> None:
    out = _write(tmp_path / "harness_defaults.env", "# versionado\nSTACKY_QUALITY_KPIS_ENABLED=true\n")
    original = out.read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["export_harness_defaults.py", "--out", str(out)])
    assert ehd.main() == 0
    assert out.read_text(encoding="utf-8") == original  # intacto


def test_main_with_live_deploy_writes_filtered_snapshot(tmp_path: Path, monkeypatch) -> None:
    deploy = tmp_path / "DeployStackyAgents"
    _write(
        deploy / "backend" / "_internal" / ".env",
        "ADO_PAT=secret\nSTACKY_CONTEXT_DEDUP_ENABLED=true\n",
    )
    out = tmp_path / "out" / "harness_defaults.env"
    monkeypatch.setattr(
        sys, "argv", ["x", "--deploy-root", str(deploy), "--out", str(out)]
    )
    assert ehd.main() == 0
    written = out.read_text(encoding="utf-8")
    assert "STACKY_CONTEXT_DEDUP_ENABLED=true" in written
    assert "ADO_PAT" not in written
