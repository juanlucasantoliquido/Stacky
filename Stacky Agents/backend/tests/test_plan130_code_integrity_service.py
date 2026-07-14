"""tests/test_plan130_code_integrity_service.py — Plan 130 F1.

Servicio puro services/code_integrity.py (ast.parse + resolucion de imports de
primera parte). 13 casos, todos con tmp_path salvo el caso 13 (backend real).
"""
from pathlib import Path

from services.code_integrity import (
    backend_root,
    check_file,
    collect_exempt_linenos,
    first_party_names,
    iter_py_files,
    resolve_module,
    run_checks,
)


def test_iter_py_files_exclusiones(tmp_path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "y.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "z.py").write_text("z = 1\n", encoding="utf-8")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "ok.py").write_text("ok = 1\n", encoding="utf-8")

    files = iter_py_files(tmp_path)
    rel = sorted(p.relative_to(tmp_path).as_posix() for p in files)
    assert rel == ["api/ok.py"]
    assert files == sorted(files)


def test_first_party_names(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "config.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "sueltos").mkdir()
    (tmp_path / "sueltos" / "algo.py").write_text("x = 1\n", encoding="utf-8")

    names = first_party_names(tmp_path)
    assert names == {"app", "config", "api", "services"}


def test_resolve_module(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "api" / "sub").mkdir()
    (tmp_path / "api" / "sub" / "__init__.py").write_text("", encoding="utf-8")

    assert resolve_module(tmp_path, "api.foo") is True
    assert resolve_module(tmp_path, "api.sub") is True
    assert resolve_module(tmp_path, "api.nada") is False


def test_sintaxis_error_linea(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "roto.py").write_text(
        '"""placeholder"""\n# comentario\ndef f(:\n    pass\n', encoding="utf-8"
    )
    first_party = first_party_names(tmp_path)
    finding, broken = check_file(tmp_path, tmp_path / "api" / "roto.py", first_party)
    assert finding is not None
    assert finding["file"] == "api/roto.py"
    assert finding["line"] == 3
    assert finding["message"]
    assert broken == []


def test_null_bytes(tmp_path):
    (tmp_path / "api").mkdir()
    path = tmp_path / "api" / "nulo.py"
    path.write_bytes(b"x = 1\n\x00\n")
    first_party = first_party_names(tmp_path)
    finding, broken = check_file(tmp_path, path, first_party)
    assert finding is not None
    assert finding["line"] == 0
    assert broken == []


def test_import_absoluto_roto(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text(
        "import api.pr_reviewx\n", encoding="utf-8"
    )
    first_party = first_party_names(tmp_path)
    finding, broken = check_file(tmp_path, tmp_path / "api" / "__init__.py", first_party)
    assert finding is None
    assert len(broken) == 1
    assert broken[0]["import"] == "api.pr_reviewx"
    assert broken[0]["line"] == 1


def test_from_import_modulo_ok_nombres_ignorados(tmp_path):
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "user.py").write_text(
        "from services import lo_que_sea\n", encoding="utf-8"
    )
    first_party = first_party_names(tmp_path)
    finding, broken = check_file(tmp_path, tmp_path / "api" / "user.py", first_party)
    assert finding is None
    assert broken == []


def test_import_relativo(tmp_path):
    (tmp_path / "api").mkdir()
    init_path = tmp_path / "api" / "__init__.py"
    init_path.write_text("from .foo import bp\n", encoding="utf-8")
    first_party = first_party_names(tmp_path)

    finding, broken = check_file(tmp_path, init_path, first_party)
    assert finding is None
    assert len(broken) == 1

    (tmp_path / "api" / "foo.py").write_text("bp = 1\n", encoding="utf-8")
    finding2, broken2 = check_file(tmp_path, init_path, first_party)
    assert finding2 is None
    assert broken2 == []


def test_terceros_ignorados(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "user.py").write_text(
        "import flask\nfrom sqlalchemy import or_\n", encoding="utf-8"
    )
    first_party = first_party_names(tmp_path)
    finding, broken = check_file(tmp_path, tmp_path / "api" / "user.py", first_party)
    assert finding is None
    assert broken == []


def test_exencion_try_import_error(tmp_path):
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api").mkdir()

    exento = tmp_path / "api" / "exento.py"
    exento.write_text(
        "try:\n    import services.opcional\nexcept ImportError:\n    pass\n",
        encoding="utf-8",
    )
    first_party = first_party_names(tmp_path)
    finding, broken = check_file(tmp_path, exento, first_party)
    assert finding is None
    assert broken == []

    no_exento = tmp_path / "api" / "no_exento.py"
    no_exento.write_text("import services.opcional\n", encoding="utf-8")
    finding2, broken2 = check_file(tmp_path, no_exento, first_party)
    assert finding2 is None
    assert len(broken2) == 1


def test_run_checks_shape_y_orden(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "b_roto.py").write_text("def f(:\n    pass\n", encoding="utf-8")
    (tmp_path / "api" / "a_roto.py").write_text("def f(:\n    pass\n", encoding="utf-8")
    (tmp_path / "api" / "ok.py").write_text("x = 1\n", encoding="utf-8")

    report = run_checks(tmp_path)
    assert set(report.keys()) == {
        "ok", "root", "files_scanned", "elapsed_ms", "syntax_errors", "broken_imports",
    }
    assert report["ok"] is False
    assert report["files_scanned"] == 4
    assert isinstance(report["elapsed_ms"], int)
    assert report["elapsed_ms"] >= 0
    files_order = [f["file"] for f in report["syntax_errors"]]
    assert files_order == sorted(files_order)


def test_no_escribe_nada(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "api" / "ok.py").write_text("x = 1\n", encoding="utf-8")

    run_checks(tmp_path)

    assert list(tmp_path.rglob("__pycache__")) == []
    assert list(tmp_path.rglob("*.pyc")) == []


def test_backend_real_sin_hallazgos():
    """Si este test falla, hay codigo Python roto DE VERDAD en el working tree
    (sintaxis o import de primera parte roto) — eso es el gate funcionando, NO
    un bug del test. Mirar report["syntax_errors"]/["broken_imports"], no
    "arreglar" este test."""
    report = run_checks()
    assert report["ok"] is True, report
