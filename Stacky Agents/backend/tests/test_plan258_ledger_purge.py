"""Plan 258 F4 — limpieza asistida de los ledgers (la UNICA pieza destructiva).

Stacky no borra datos del operador por su cuenta, ni siquiera datos que SABE que
son basura. Cuatro candados en serie:
  1. la perilla nace APAGADA (excepcion dura #2: destructiva/irreversible);
  2. `dry_run=True` es el default del parametro Y en el endpoint manda el
     cuerpo: solo un `false` booleano explicito borra (C14);
  3. hace falta la confirmacion emitida por GET /ledgers/health, que transporta
     el conteo EXACTO que se le mostro al operador;
  4. copia previa obligatoria; si la copia falla, se ABORTA.

`unknown` NUNCA se purga: solo lo probadamente `test`.

Correr POR ARCHIVO:
    .venv\\Scripts\\python.exe -m pytest tests/test_plan258_ledger_purge.py -v
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import runtime_paths  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def data_tmp(tmp_path, monkeypatch):
    """TODO este archivo escribe en tmp. Autouse a proposito: un test de purga
    que apunte sin querer al `data/` real borraria datos del operador."""
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    from services.confirm_token import reset_for_tests
    reset_for_tests()
    return tmp_path


@pytest.fixture(autouse=True)
def purga_habilitada(monkeypatch):
    """La perilla nace OFF; los tests del servicio la encienden a proposito."""
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_LEDGER_PURGE_ENABLED", True, raising=False)


def _sembrar(data_tmp, nombre: str = "ci_runs") -> list[dict]:
    """3 lineas de test (inferidas), 1 de prod y 1 unknown."""
    filas = [
        {"project": "myproject", "tracker_type": "gitlab", "pipeline_id": "42",
         "sha": "newsha", "web_url": "http://gitlab/p/42",
         "triggered_at": "2026-07-20T21:40:38+00:00"},
        {"project": "myproject", "tracker_type": "gitlab", "pipeline_id": "7",
         "sha": "newsha", "triggered_at": "2026-07-20T21:41:00+00:00"},
        {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "1",
         "triggered_at": "2026-07-21T00:00:00+00:00", "env": "test"},
        {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "2",
         "triggered_at": "2026-07-22T00:00:00+00:00", "env": "prod"},
        {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "3",
         "triggered_at": "2026-07-23T00:00:00+00:00"},          # unknown
    ]
    (data_tmp / f"{nombre}.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")
    return filas


def _leer(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _token(nombre: str, borrables: int) -> str:
    from services.confirm_token import issue_token
    from services.ledger_writer import PURGE_ACTION
    return issue_token(PURGE_ACTION, {"ledger": nombre, "deletable": borrables})


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------

def test_purge_dry_run_es_el_default(data_tmp):
    """Sin pasar `dry_run`, NO borra. Un llamador distraido no puede destruir."""
    from services.ledger_writer import purge_test_lines

    _sembrar(data_tmp)
    antes = (data_tmp / "ci_runs.jsonl").read_bytes()

    res = purge_test_lines("ci_runs", confirm_token="")
    assert res["dry_run"] is True
    assert res["deletable"] == 3
    assert res["deleted"] == 0
    assert (data_tmp / "ci_runs.jsonl").read_bytes() == antes


def test_purge_sin_token_devuelve_409(data_tmp, client):
    """En el endpoint, un pedido real sin confirmacion valida es 409 y no toca nada."""
    _sembrar(data_tmp)
    antes = (data_tmp / "ci_runs.jsonl").read_bytes()

    res = client.post("/api/diag/ledgers/purge-test-lines",
                      json={"ledger": "ci_runs", "dry_run": False})
    assert res.status_code == 409
    body = res.get_json()
    assert body["error"] == "confirmation_required"
    assert body["deletable"] == 3
    assert isinstance(body["confirm_token"], str) and body["confirm_token"]
    assert (data_tmp / "ci_runs.jsonl").read_bytes() == antes


def test_purge_hace_backup_antes(data_tmp):
    from services.ledger_writer import backups_dir, purge_test_lines

    original = (data_tmp / "ci_runs.jsonl")
    _sembrar(data_tmp)
    contenido_original = original.read_bytes()

    res = purge_test_lines("ci_runs", confirm_token=_token("ci_runs", 3), dry_run=False)
    assert res["ok"] is True
    assert res["deleted"] == 3
    assert res["kept"] == 2

    copias = sorted(backups_dir().glob("ci_runs-*.jsonl"))
    assert len(copias) == 1, "no se guardo la copia previa"
    assert copias[0].read_bytes() == contenido_original, "la copia no es fiel al original"
    assert len(_leer(original)) == 2


def test_purge_aborta_si_falla_el_backup(data_tmp, monkeypatch):
    """Si la copia falla, el ledger queda INTACTO."""
    from services import ledger_writer

    _sembrar(data_tmp)
    antes = (data_tmp / "ci_runs.jsonl").read_bytes()

    def _revienta(*_a, **_kw):
        raise OSError("disco lleno")

    monkeypatch.setattr(ledger_writer, "_hacer_backup", _revienta)
    res = ledger_writer.purge_test_lines("ci_runs", confirm_token=_token("ci_runs", 3),
                                         dry_run=False)
    assert res["ok"] is False
    assert res["error"] == "backup_fallido"
    assert res["deleted"] == 0
    assert (data_tmp / "ci_runs.jsonl").read_bytes() == antes


def test_purge_nunca_borra_unknown_ni_prod(data_tmp):
    from services.ledger_writer import purge_test_lines

    _sembrar(data_tmp)
    purge_test_lines("ci_runs", confirm_token=_token("ci_runs", 3), dry_run=False)

    quedaron = _leer(data_tmp / "ci_runs.jsonl")
    ids = sorted(str(f["pipeline_id"]) for f in quedaron)
    assert ids == ["2", "3"], "se borro una linea de produccion o de origen desconocido"
    assert {f.get("env") for f in quedaron} == {"prod", None}


def test_purge_con_archivo_abierto_no_corrompe(data_tmp):
    """Gotcha de Windows: `tmp.replace(path)` falla si otro handle tiene el
    archivo abierto. Sea cual sea el desenlace (purga o `ledger_locked`), el
    archivo NUNCA puede quedar corrupto ni perder las lineas de produccion."""
    from services.ledger_writer import purge_test_lines

    destino = data_tmp / "ci_runs.jsonl"
    _sembrar(data_tmp)

    with destino.open("r", encoding="utf-8") as _handle_abierto:
        res = purge_test_lines("ci_runs", confirm_token=_token("ci_runs", 3), dry_run=False)

    assert res["ledger"] == "ci_runs"
    quedaron = _leer(destino)                      # JSONL valido: no hay corrupcion
    conservados = {str(f["pipeline_id"]) for f in quedaron}
    assert {"2", "3"} <= conservados, "se perdieron lineas que no eran de test"
    if res.get("error") == "ledger_locked":
        assert len(quedaron) == 5                  # intacto, como debe ser
    else:
        assert res["deleted"] == 3 and len(quedaron) == 2


def test_purge_ledger_inexistente_devuelve_cero(data_tmp):
    from services.ledger_writer import purge_test_lines

    assert not (data_tmp / "ci_runs.jsonl").exists()
    res = purge_test_lines("ci_runs", confirm_token="", dry_run=True)
    assert res["ok"] is True and res["deleted"] == 0 and res["deletable"] == 0

    res2 = purge_test_lines("ci_runs", confirm_token="", dry_run=False)
    assert res2["deleted"] == 0        # sin nada que borrar no se pide confirmacion


def test_purge_ledger_sin_lock_no_soportado(data_tmp):
    """`db_query.py`, `config_transfer.py` y `solution_builder.py` escriben con
    un `open(..., "a")` sin lock propio: purgarlos seria inseguro, asi que se
    declara NO SOPORTADO en vez de hacerlo mal."""
    from services.ledger_writer import purge_test_lines, purgeable

    assert purgeable("ci_runs") and purgeable("env_applies")
    for nombre in ("db_query_audit", "config_transfer_events", "build_runs"):
        assert not purgeable(nombre)
        res = purge_test_lines(nombre, confirm_token="", dry_run=False)
        assert res["ok"] is False and res["error"] == "ledger_no_soportado"
        assert res["deleted"] == 0


def test_purge_token_de_otro_ledger_no_sirve(data_tmp):
    from services.confirm_token import ConfirmTokenError
    from services.ledger_writer import purge_test_lines

    _sembrar(data_tmp)
    with pytest.raises(ConfirmTokenError):
        purge_test_lines("ci_runs", confirm_token=_token("env_applies", 3), dry_run=False)
    assert len(_leer(data_tmp / "ci_runs.jsonl")) == 5


def test_purge_token_con_conteo_viejo_no_sirve(data_tmp):
    """El identificador transporta el conteo que se le MOSTRO al operador: si el
    archivo cambio desde entonces, no puede confirmar una cifra que no vio."""
    from services.confirm_token import ConfirmTokenError
    from services.ledger_writer import purge_test_lines

    _sembrar(data_tmp)
    with pytest.raises(ConfirmTokenError):
        purge_test_lines("ci_runs", confirm_token=_token("ci_runs", 99), dry_run=False)
    assert len(_leer(data_tmp / "ci_runs.jsonl")) == 5


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")

    tmp_env = tmp_path / ".env"
    tmp_env.write_text("", encoding="utf-8")
    monkeypatch.setattr("api.global_config._ENV_PATH", tmp_env)
    monkeypatch.setattr("api.harness_flags._ENV_PATH", tmp_env, raising=False)

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


@pytest.mark.parametrize("cuerpo", [
    {"ledger": "ci_runs"},                       # sin dry_run
    {"ledger": "ci_runs", "dry_run": "false"},   # string, no booleano
    {"ledger": "ci_runs", "dry_run": 0},         # int, no booleano
    {"ledger": "ci_runs", "dry_run": None},
])
def test_endpoint_sin_dry_run_en_el_body_no_borra(client, data_tmp, cuerpo):
    """Regresion de C14: solo un `false` BOOLEANO explicito borra. Ausente, de
    otro tipo o nulo significan dry-run, y un pedido mal formado nunca destruye."""
    _sembrar(data_tmp)
    antes = (data_tmp / "ci_runs.jsonl").read_bytes()

    res = client.post("/api/diag/ledgers/purge-test-lines", json=cuerpo)
    assert res.status_code == 200
    body = res.get_json()
    assert body["dry_run"] is True
    assert body["deleted"] == 0
    assert body["deletable"] == 3
    assert (data_tmp / "ci_runs.jsonl").read_bytes() == antes


def test_endpoint_purga_completa_con_confirmacion(client, data_tmp):
    """Camino feliz de dos pasos, tal como lo hace la interfaz."""
    _sembrar(data_tmp)

    paso1 = client.post("/api/diag/ledgers/purge-test-lines",
                        json={"ledger": "ci_runs", "dry_run": False})
    assert paso1.status_code == 409
    confirmacion = paso1.get_json()["confirm_token"]

    paso2 = client.post("/api/diag/ledgers/purge-test-lines",
                        json={"ledger": "ci_runs", "dry_run": False,
                              "confirm_token": confirmacion})
    assert paso2.status_code == 200
    assert paso2.get_json()["deleted"] == 3
    assert len(_leer(data_tmp / "ci_runs.jsonl")) == 2


def test_endpoint_404_con_la_perilla_apagada(client, data_tmp, monkeypatch):
    import config as _config

    _sembrar(data_tmp)
    monkeypatch.setattr(_config.config, "STACKY_LEDGER_PURGE_ENABLED", False, raising=False)
    res = client.post("/api/diag/ledgers/purge-test-lines",
                      json={"ledger": "ci_runs", "dry_run": False})
    assert res.status_code == 404
    assert len(_leer(data_tmp / "ci_runs.jsonl")) == 5


def test_endpoint_ledger_desconocido_400(client, data_tmp):
    res = client.post("/api/diag/ledgers/purge-test-lines",
                      json={"ledger": "../../etc/passwd", "dry_run": False})
    assert res.status_code == 400
    assert res.get_json()["error"] == "ledger_desconocido"
