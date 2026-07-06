"""Plan 97 F2 — detect_stack (tests primero, determinista, sin LLM)."""
from services.pipeline_stack_detector import detect_stack


def test_detect_python_by_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    assert detect_stack(str(tmp_path)) == "python"


def test_detect_python_by_pyproject_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert detect_stack(str(tmp_path)) == "python"


def test_detect_node_by_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert detect_stack(str(tmp_path)) == "node"


def test_detect_dotnet_by_csproj(tmp_path):
    app_dir = tmp_path / "App"
    app_dir.mkdir()
    (app_dir / "Foo.csproj").write_text("<Project />", encoding="utf-8")
    assert detect_stack(str(tmp_path)) == "dotnet"


def test_detect_none_when_empty_dir(tmp_path):
    assert detect_stack(str(tmp_path)) is None


def test_detect_none_when_path_missing(tmp_path):
    assert detect_stack(str(tmp_path / "no-existe")) is None


def test_detect_none_when_path_is_none():
    assert detect_stack(None) is None


def test_detect_precedence_python_over_node(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert detect_stack(str(tmp_path)) == "python"


def test_detect_ignores_node_modules_depth(tmp_path):
    nm_dir = tmp_path / "node_modules" / "algo"
    nm_dir.mkdir(parents=True)
    (nm_dir / "package.json").write_text("{}", encoding="utf-8")
    assert detect_stack(str(tmp_path)) is None


def test_detect_depth_cap_finds_nested_manifest(tmp_path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "requirements.txt").write_text("flask\n", encoding="utf-8")
    assert detect_stack(str(tmp_path)) == "python"
