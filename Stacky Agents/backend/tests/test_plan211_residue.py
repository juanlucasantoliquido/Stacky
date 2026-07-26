"""Plan 211 F2 — Barrido de residuos de port entre clientes.

El falso positivo acá es caro (baja el gate del developer), así que hay dos
guardas: match por límite de palabra y bloqueo solo con tokens de alta confianza.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import port_residue_scanner as prs  # noqa: E402


def _cfg(name, ws, *, server=None, product=None, label=None, online=None):
    return {
        "name": name,
        "workspace_root": ws,
        "client_profile": {
            "database": {"server": server} if server else {},
            "terminology": {**({"product_name": product} if product else {}),
                            **({"client_label": label} if label else {})},
            "code_layout": {"online_path": online} if online else {},
        },
    }


def _proyectos(monkeypatch, cfgs):
    import project_manager

    monkeypatch.setattr(project_manager, "get_all_projects", lambda: cfgs, raising=True)
    monkeypatch.setattr(project_manager, "get_active_project", lambda: None, raising=True)


def _archivo(tmp_path: Path, nombre: str, contenido: str) -> str:
    p = tmp_path / nombre
    p.write_text(contenido, encoding="utf-8")
    return str(p)


def test_catalog_excludes_ticket_project(monkeypatch):
    _proyectos(monkeypatch, [
        _cfg("pacifico", "N:\\ws\\pacifico", server="dbpacifico01", product="RSPacifico"),
        _cfg("ripley", "N:\\ws\\ripley", server="dbripley01", product="RSRipley"),
    ])

    catalog = prs.build_foreign_token_catalog("pacifico")

    assert "dbripley01" in catalog
    assert "dbpacifico01" not in catalog, "el proyecto DEL TICKET no aporta tokens"
    assert catalog["dbripley01"]["source_project"] == "ripley"


def test_catalog_excludes_by_workspace_root(monkeypatch):
    _proyectos(monkeypatch, [
        _cfg("PACIFICO", "N:\\ws\\pacifico", server="dbpacifico01"),
        _cfg("pacifico-alias", "N:/ws/pacifico", server="dbotroalias01"),
        _cfg("ripley", "N:\\ws\\ripley", server="dbripley01"),
    ])

    catalog = prs.build_foreign_token_catalog("pacifico")

    assert "dbripley01" in catalog
    assert "dbotroalias01" not in catalog, "mismo workspace_root normalizado ⇒ excluido"


def test_catalog_applies_stoplist_and_minlen(monkeypatch):
    _proyectos(monkeypatch, [
        _cfg("ripley", "N:\\ws\\ripley", server="dbripley01", online="trunk/OnLine/src"),
    ])

    catalog = prs.build_foreign_token_catalog("pacifico")

    assert "online" not in catalog and "src" not in catalog and "trunk" not in catalog
    assert "dbripley01" in catalog
    assert "ripley" in catalog, "el nombre del workspace ajeno sí entra"


def test_word_boundary_not_substring(tmp_path):
    catalog = {"crea": {"source_project": "crea", "kind": "server"}}
    dentro = _archivo(tmp_path, "a.cs", "var x = new CrearCliente();")
    palabra = _archivo(tmp_path, "b.cs", "// server crea prod")

    assert prs.scan_files_for_foreign_tokens([dentro], catalog, workspace_root=str(tmp_path)) == []
    assert len(prs.scan_files_for_foreign_tokens([palabra], catalog,
                                                 workspace_root=str(tmp_path))) == 1


def test_short_common_token_is_warning_not_blocking(tmp_path):
    catalog = {"crea": {"source_project": "crea", "kind": "server"}}
    f = _archivo(tmp_path, "a.cs", "// host: crea")

    findings = prs.scan_files_for_foreign_tokens([f], catalog, workspace_root=str(tmp_path))

    assert findings[0].severity == "warning", \
        "un token corto y común NUNCA baja el gate del developer"


def test_high_confidence_server_is_blocking(tmp_path):
    catalog = {"dbripley01": {"source_project": "ripley", "kind": "server"},
               "10.10.1.5": {"source_project": "ripley", "kind": "server"}}
    f = _archivo(tmp_path, "web.config", 'server=dbripley01;host=10.10.1.5')

    findings = prs.scan_files_for_foreign_tokens([f], catalog, workspace_root=str(tmp_path))

    assert len(findings) == 2
    assert all(x.severity == "blocking" for x in findings)


def test_allowlist_suppresses_token(tmp_path):
    catalog = {"dbripley01": {"source_project": "ripley", "kind": "server"}}
    f = _archivo(tmp_path, "a.cs", "// dbripley01")

    assert prs.scan_files_for_foreign_tokens([f], catalog, workspace_root=str(tmp_path),
                                             allowlist=["dbripley01"]) == []


def test_scan_client_label_is_warning(tmp_path):
    catalog = {"ripleychile": {"source_project": "ripley", "kind": "client_label"}}
    f = _archivo(tmp_path, "a.cs", "// cliente RipleyChile")

    findings = prs.scan_files_for_foreign_tokens([f], catalog, workspace_root=str(tmp_path))

    assert findings[0].severity == "warning"


def test_scan_own_tokens_zero_findings(tmp_path):
    f = _archivo(tmp_path, "a.cs", "// dbpacifico01 es el nuestro")

    assert prs.scan_files_for_foreign_tokens([f], {}, workspace_root=str(tmp_path)) == []


def test_archivo_no_fuente_se_saltea(tmp_path):
    catalog = {"dbripley01": {"source_project": "ripley", "kind": "server"}}
    f = _archivo(tmp_path, "notas.txt", "dbripley01")

    assert prs.scan_files_for_foreign_tokens([f], catalog, workspace_root=str(tmp_path)) == []


def test_evidence_is_masked(tmp_path):
    from services.secret_masking import mask_token_values

    catalog = {"dbripley01": {"source_project": "ripley", "kind": "server"}}
    linea = 'connectionString="Server=dbripley01;Password=SuperSecreto123;"'
    f = _archivo(tmp_path, "web.config", linea)

    findings = prs.scan_files_for_foreign_tokens([f], catalog, workspace_root=str(tmp_path))

    assert findings[0].evidence == mask_token_values(linea.strip()[:200])
    assert findings[0].line == 1


def test_changed_files_degrades_without_git(tmp_path):
    assert prs.changed_files(str(tmp_path)) == []
    assert prs.changed_files(None) == []
    assert prs.changed_files(str(tmp_path / "no-existe")) == []


def test_parse_porcelain_rename_and_quoted():
    porcelain = 'R  vieja.cs -> nueva.cs\n M  simple.cs\n?? "con espacio.cs"\n'

    salida = prs._parse_porcelain(porcelain)

    assert "nueva.cs" in salida, "en un rename se toma el destino"
    assert "vieja.cs" not in salida
    assert "simple.cs" in salida
    assert "con espacio.cs" in salida, "los paths entrecomillados se descomillan"


def test_residue_to_dicts_shape(tmp_path):
    catalog = {"dbripley01": {"source_project": "ripley", "kind": "server"}}
    f = _archivo(tmp_path, "a.cs", "// dbripley01")

    dicts = prs.residue_to_dicts(
        prs.scan_files_for_foreign_tokens([f], catalog, workspace_root=str(tmp_path)))

    assert set(dicts[0].keys()) == {"kind", "severity", "file", "detail"}
    assert "dbripley01" in dicts[0]["detail"]
    assert "ripley" in dicts[0]["detail"]


def test_allowlist_for_project_sin_perfil_es_vacia(monkeypatch):
    from services import client_profile

    monkeypatch.setattr(client_profile, "load_effective_client_profile",
                        lambda p: {}, raising=True)

    assert prs.allowlist_for_project("x") == []


def test_allowlist_for_project_lee_el_perfil(monkeypatch):
    from services import client_profile

    monkeypatch.setattr(client_profile, "load_effective_client_profile",
                        lambda p: {"port_residue": {"allowlist": [" Ripley ", "otro"]}},
                        raising=True)

    assert prs.allowlist_for_project("x") == ["ripley", "otro"]


def test_catalogo_vacio_no_escanea(tmp_path):
    f = _archivo(tmp_path, "a.cs", "cualquier cosa")

    assert prs.scan_files_for_foreign_tokens([f], {}, workspace_root=str(tmp_path)) == []


def test_catalog_nunca_lanza(monkeypatch):
    import project_manager

    def _boom():
        raise RuntimeError("registro roto")

    monkeypatch.setattr(project_manager, "get_all_projects", _boom, raising=True)

    assert prs.build_foreign_token_catalog("x") == {}
