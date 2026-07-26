"""Plan 200 R2 — Detector determinista de "esto hay que desplegar en otro ambiente".

El punto delicado es NO gritar de más: si el badge se enciende cada vez que un
ticket menciona "producción", el operador aprende a ignorarlo y el aviso deja de
servir. Por eso el texto solo cuenta cuando co-ocurren la intención de desplegar
y una señal de que el cambio es SQL.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import runtime_paths  # noqa: E402
from services import incident_store, sql_deploy_detector as D  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(D, "_suggested_envs", lambda: ["DEV", "TEST"])
    yield tmp_path


def _incidencia_con_sql(texto="arreglar el alta") -> dict:
    return incident_store.create_incident(texto, files=[
        ("migracion.sql", b"ALTER TABLE dbo.CLIENTES ADD COLUMN X INT;"),
    ])


def test_incidencia_con_sql_requires_alta():
    need = D.detect_for_incident(_incidencia_con_sql())

    assert need.requires is True
    assert need.confidence == "alta"
    assert len(need.scripts) == 1
    assert need.scripts[0]["source"] == "incident_attachment"
    assert len(need.scripts[0]["sha256"]) == 64


def test_incidencia_solo_keywords_posible():
    inc = incident_store.create_incident(
        "hay que desplegar el script SQL de la tabla en produccion", files=[])

    need = D.detect_for_incident(inc)

    assert need.requires is True
    assert need.confidence == "posible"
    assert need.scripts == []


def test_keywords_sin_senal_sql_no_requiere():
    """Solo intención de deploy, sin señal SQL: no puede encender el badge."""
    inc = incident_store.create_incident("revisar el ambiente de produccion", files=[])

    assert D.detect_for_incident(inc).requires is False


def test_senal_sql_sin_intencion_no_requiere():
    """Mencionar una tabla tampoco alcanza: falta la intención de desplegar."""
    inc = incident_store.create_incident("la tabla CLIENTES tiene datos raros", files=[])

    assert D.detect_for_incident(inc).requires is False


def test_incidencia_sin_nada_no_requiere():
    inc = incident_store.create_incident("el boton no anda", files=[])

    need = D.detect_for_incident(inc)
    assert need.requires is False
    assert need.confidence == "no"
    assert need.scripts == [] and need.suggested_environments == []


def test_ticket_con_sql_en_output(tmp_path):
    salida = tmp_path / "out"
    salida.mkdir()
    (salida / "01_alter.sql").write_bytes(b"ALTER TABLE T ADD C INT;")
    ticket = SimpleNamespace(title="cambio menor", description="")

    need = D.detect_for_ticket(ticket, salida)

    assert need.requires is True and need.confidence == "alta"
    assert need.scripts[0]["name"] == "01_alter.sql"
    assert need.scripts[0]["source"] == "ticket_output"


def test_ticket_sin_output_cae_al_texto():
    ticket = SimpleNamespace(
        title="Migracion de esquema",
        description="hay que aplicar en QA el DDL nuevo")

    need = D.detect_for_ticket(ticket, None)

    assert need.requires is True and need.confidence == "posible"


def test_suggested_envs_son_los_registrados():
    need = D.detect_for_incident(_incidencia_con_sql())

    assert need.suggested_environments == ["DEV", "TEST"]


def test_determinista():
    inc = _incidencia_con_sql()

    from dataclasses import asdict

    assert asdict(D.detect_for_incident(inc)) == asdict(D.detect_for_incident(inc))


def test_read_script_devuelve_contenido():
    inc = _incidencia_con_sql()
    sha = inc["files"][0]["sha256"]

    script = D.read_script({"source": "incident_attachment",
                            "incident_id": inc["id"], "sha256": sha})

    assert script["sha256"] == sha
    assert "ALTER TABLE" in script["sql_text"]


def test_read_script_sha_inexistente_da_none():
    inc = _incidencia_con_sql()

    assert D.read_script({"source": "incident_attachment",
                          "incident_id": inc["id"], "sha256": "0" * 64}) is None


def test_read_script_detecta_archivo_cambiado(tmp_path):
    """Si el .sql cambió desde que se listó, devolver el contenido nuevo bajo el
    sha viejo sería exactamente cómo se ejecuta algo que nadie aprobó."""
    inc = _incidencia_con_sql()
    sha_viejo = inc["files"][0]["sha256"]
    destino = (incident_store.incidents_root() / inc["id"]
               / inc["files"][0]["stored_name"])
    destino.write_bytes(b"DROP TABLE dbo.CLIENTES;")

    assert D.read_script({"source": "incident_attachment",
                          "incident_id": inc["id"], "sha256": sha_viejo}) is None


def test_read_script_ticket_no_permite_traversal(tmp_path):
    salida = tmp_path / "out"
    salida.mkdir()
    (salida / "ok.sql").write_bytes(b"SELECT 1;")
    (tmp_path / "secreto.sql").write_bytes(b"SELECT 'secreto';")

    fuera = D.read_script({"source": "ticket_output", "output_dir": str(salida),
                           "name": "../secreto.sql", "sha256": ""})

    assert fuera is None, "el name no puede escapar del directorio de salida"


def test_detector_no_usa_red_ni_llm():
    """Determinista significa determinista: sin red, sin modelo."""
    import re

    fuente = (ROOT / "services" / "sql_deploy_detector.py").read_text(encoding="utf-8")
    # Se ignoran los comentarios: la prosa explica por qué NO hay LLM.
    codigo = "\n".join(l for l in fuente.splitlines()
                       if not l.lstrip().startswith("#"))

    assert not re.search(r"\b(requests|urllib|httpx|invoke_local_llm|llm_router)\b",
                         codigo), "el detector no puede depender de red ni de un modelo"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_endpoint_incidencia_devuelve_deteccion(client):
    inc = _incidencia_con_sql()

    body = client.get(f"/api/incidents/{inc['id']}/sql-deploy").get_json()

    assert body["ok"] is True and body["confidence"] == "alta"
    assert body["scripts"][0]["name"] == "migracion.sql"


def test_endpoint_sql_script_sirve_el_contenido(client):
    inc = _incidencia_con_sql()
    sha = inc["files"][0]["sha256"]

    body = client.get(f"/api/incidents/{inc['id']}/sql-script?sha={sha}").get_json()

    assert body["ok"] is True and "ALTER TABLE" in body["sql_text"]


def test_endpoint_sql_script_404_sha_desconocido(client):
    inc = _incidencia_con_sql()

    r = client.get(f"/api/incidents/{inc['id']}/sql-script?sha={'0' * 64}")

    assert r.status_code == 404


def test_endpoint_404_flag_off(client, monkeypatch):
    from config import config as cfg

    inc = _incidencia_con_sql()
    monkeypatch.setattr(cfg, "STACKY_SQL_DEPLOY_DETECT_ENABLED", False, raising=False)

    assert client.get(f"/api/incidents/{inc['id']}/sql-deploy").status_code == 404


def test_endpoint_404_flag_off_ticket(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_SQL_DEPLOY_DETECT_ENABLED", False, raising=False)

    assert client.get("/api/tickets/1/sql-deploy").status_code == 404
