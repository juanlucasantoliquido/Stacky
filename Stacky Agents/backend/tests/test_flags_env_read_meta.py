"""Plan 154 F4 — Meta-test: flags registradas se leen desde config.config.

Clase de bug que extingue (3 ocurrencias conocidas: planes 131, 148 y
api/executions.py): leer una flag que YA existe en FLAG_REGISTRY tomando
el valor directo del entorno con un default local, que puede divergir del
default real de config.py y de la FlagSpec curada. Regla: en backend/api/
y backend/services/, toda flag registrada se lee desde la instancia
config.config. Las ocurrencias legacy viven en una allowlist congelada
(tests/flags_env_read_allowlist.txt) que SOLO puede bajar.
"""
import pathlib
import re

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_ALLOWLIST = _BACKEND / "tests" / "flags_env_read_allowlist.txt"
_SCAN_DIRS = ("api", "services")
_PATTERN = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*['"](STACKY_[A-Z0-9_]+)['"]\s*,"""
)


def _registered_flags() -> set[str]:
    from services.harness_flags import FLAG_REGISTRY
    return {spec.key for spec in FLAG_REGISTRY}


def _allowlisted() -> set[str]:
    out = set()
    if _ALLOWLIST.exists():
        for line in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.add(line)
    return out


def _scan_occurrences() -> set[str]:
    registered = _registered_flags()
    found: set[str] = set()
    for d in _SCAN_DIRS:
        for py in sorted((_BACKEND / d).rglob("*.py")):
            rel = py.relative_to(_BACKEND).as_posix()
            for match in _PATTERN.finditer(py.read_text(encoding="utf-8")):
                flag = match.group(1)
                if flag in registered:
                    found.add(f"{rel}:{flag}")
            # nota: el regex tambien caza texto en comentarios/docstrings;
            # es deliberado (ver plan 154 §9: la prosa no debe contener el patron).
    return found


def test_flags_registradas_no_se_leen_del_entorno_con_default_local():
    found = _scan_occurrences()
    allow = _allowlisted()
    nuevas = sorted(found - allow)
    assert not nuevas, (
        "Lectura directa de entorno con default local para flags REGISTRADAS "
        "(leer desde config.config; ver plan 154 F4):\n  - " + "\n  - ".join(nuevas)
    )
    curadas_de_mas = sorted(allow - found)
    assert not curadas_de_mas, (
        "Entradas de flags_env_read_allowlist.txt que ya no existen en el "
        "codigo (sacarlas: la allowlist solo baja):\n  - " + "\n  - ".join(curadas_de_mas)
    )


def test_execution_history_default_on(monkeypatch):
    """Regresion del fix: sin la env var, /api/executions/history responde 200."""
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("STACKY_EXECUTION_HISTORY_ENABLED", raising=False)
    import app as _app_mod
    # C1 v2 — F4 se implementa ANTES que F5.ii: hacer create_app() hermetico aca
    # tambien (defensa-en-profundidad; sin esto, en la maquina dev con proyecto
    # activo este test dispararia el _startup_sync REAL contra la org ADO productiva).
    monkeypatch.setattr(_app_mod, "_startup_sync", lambda *a, **k: None)
    app = _app_mod.create_app()
    client = app.test_client()
    resp = client.get("/api/executions/history")
    assert resp.status_code == 200, resp.get_data(as_text=True)
