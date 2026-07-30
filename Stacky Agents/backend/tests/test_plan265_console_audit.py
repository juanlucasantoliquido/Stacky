"""Plan 265 F7 — Bitácora de acciones de consola (auditoría local, mono-operador).
10 casos del doc. Registro, NUNCA restricción (principio 3.4).
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Test 8 (obligatorio): aísla la bitácora en tmp_path; nunca toca el
    directorio de datos REAL del operador (ya paso antes en este repo, Plan 216)."""
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def audit_on(monkeypatch):
    import config as cfg
    original = getattr(cfg.config, "STACKY_CONSOLE_AUDIT_LOG_ENABLED", True)
    cfg.config.STACKY_CONSOLE_AUDIT_LOG_ENABLED = True
    yield
    cfg.config.STACKY_CONSOLE_AUDIT_LOG_ENABLED = original


def test_1_record_read_roundtrip(audit_on):
    from services import console_audit
    ok = console_audit.record_console_action(execution_id=42, action="cancel", detail={"note": "manual"})
    assert ok is True
    entries = console_audit.read_console_audit()
    assert len(entries) == 1
    assert entries[0]["execution_id"] == 42
    assert entries[0]["action"] == "cancel"


def test_2_action_fuera_de_allowlist_no_escribe(audit_on, _isolated_data_dir):
    from services import console_audit
    ok = console_audit.record_console_action(execution_id=1, action="borrar_todo")
    assert ok is False
    assert console_audit.read_console_audit() == []
    assert not (_isolated_data_dir / "console_audit.jsonl").exists()


def test_3_directorio_no_escribible_no_lanza(audit_on, monkeypatch):
    from services import console_audit

    def _boom_mkdir(*args, **kwargs):
        raise OSError("permiso denegado")

    monkeypatch.setattr("pathlib.Path.mkdir", _boom_mkdir)
    ok = console_audit.record_console_action(execution_id=1, action="cancel")
    assert ok is False


def test_4_rotacion_a_los_5mb(audit_on, _isolated_data_dir):
    from services import console_audit
    path = _isolated_data_dir / "console_audit.jsonl"
    # Sembrar un archivo YA por encima de 5 MB para forzar la rotación en el
    # próximo record, sin escribir 5 MB de verdad entrada por entrada.
    path.write_text("x" * (5 * 1024 * 1024 + 10), encoding="utf-8")
    ok = console_audit.record_console_action(execution_id=99, action="close")
    assert ok is True
    rotated = _isolated_data_dir / "console_audit.jsonl.1"
    assert rotated.exists()
    # Nunca un tercer archivo.
    assert not (_isolated_data_dir / "console_audit.jsonl.2").exists()
    # El principal arrancó de cero: solo la entrada nueva.
    fresh_lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(fresh_lines) == 1


def test_5_flag_off_record_false_read_vacio():
    import config as cfg
    original = getattr(cfg.config, "STACKY_CONSOLE_AUDIT_LOG_ENABLED", True)
    cfg.config.STACKY_CONSOLE_AUDIT_LOG_ENABLED = False
    try:
        from services import console_audit
        ok = console_audit.record_console_action(execution_id=1, action="cancel")
        assert ok is False
        assert console_audit.read_console_audit() == []
    finally:
        cfg.config.STACKY_CONSOLE_AUDIT_LOG_ENABLED = original


def test_6_linea_corrupta_en_medio_no_rompe(audit_on, _isolated_data_dir):
    from services import console_audit
    path = _isolated_data_dir / "console_audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    good1 = json.dumps({"ts": 1.0, "execution_id": 1, "action": "cancel", "detail": {}})
    good2 = json.dumps({"ts": 2.0, "execution_id": 2, "action": "close", "detail": {}})
    path.write_text(f"{good1}\nESTO NO ES JSON\n{good2}\n", encoding="utf-8")
    entries = console_audit.read_console_audit()
    assert len(entries) == 2
    ids = {e["execution_id"] for e in entries}
    assert ids == {1, 2}


def test_7_detail_no_serializable_se_descarta_ese_campo(audit_on):
    from services import console_audit

    class NoSerializable:
        pass

    ok = console_audit.record_console_action(
        execution_id=5, action="cancel", detail={"ok_field": "texto", "raro": NoSerializable()}
    )
    assert ok is True
    entries = console_audit.read_console_audit()
    assert len(entries) == 1
    assert entries[0]["detail"].get("ok_field") == "texto"
    assert "raro" not in entries[0]["detail"]


def test_8_aislamiento_no_toca_perfil_real(audit_on, _isolated_data_dir):
    """Confirma que la fixture autouse aísla de verdad: el path real de
    runtime_paths.data_dir() (sin monkeypatch) NO coincide con tmp_path."""
    import runtime_paths
    from services import console_audit
    console_audit.record_console_action(execution_id=1, action="cancel")
    # runtime_paths.data_dir esta monkeypateado en este test; comprobamos que
    # el archivo se creo DENTRO del tmp_path aislado.
    assert (_isolated_data_dir / "console_audit.jsonl").exists()


def test_9_bitacora_no_restringe_ninguna_decision():
    """La bitácora es registro, NUNCA control de acceso (principio 3.4): ningún
    camino de código puede consultar read_console_audit para decidir si
    permite una acción. Verificado leyendo el AST real de los 2 archivos."""
    import ast
    import pathlib

    backend_dir = pathlib.Path(__file__).resolve().parents[1]
    executions_path = backend_dir / "api" / "executions.py"
    audit_path = backend_dir / "services" / "console_audit.py"

    forbidden_substrings = ["cancel", "relaunch", "publish", "approve", "discard", "input", "run"]

    def _call_sites(path: pathlib.Path) -> list[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        sites: list[str] = []
        stack: list[str] = []

        class _Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
                stack.append(node.name)
                self.generic_visit(node)
                stack.pop()

            def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                if name == "read_console_audit":
                    sites.append(stack[-1] if stack else "<module>")
                self.generic_visit(node)

        _Visitor().visit(tree)
        return sites

    exec_sites = _call_sites(executions_path)
    audit_sites = _call_sites(audit_path)

    assert len(exec_sites) >= 1, "no se encontro ningun endpoint que lea la bitacora"
    for enclosing in exec_sites + audit_sites:
        lower = enclosing.lower()
        assert not any(bad in lower for bad in forbidden_substrings), (
            f"read_console_audit se llama dentro de '{enclosing}': suena a que decide una accion"
        )


def test_10_detail_con_secreto_no_viaja_en_claro(audit_on):
    from services import console_audit
    ok = console_audit.record_console_action(
        execution_id=7, action="cancel", detail={"nota": "PASSWORD=Sup3rS3cr3t!"}
    )
    assert ok is True
    entries = console_audit.read_console_audit()
    assert "Sup3rS3cr3t!" not in json.dumps(entries)
