"""Plan 258 — Telemetria veraz: ledgers sin fixtures ni ciclos abiertos.

F0 (contaminacion probada), F1 (portero de validacion y procedencia),
F2 (procedencia de lo historico), F3 (huerfanos de CI + endpoint de salud),
F5 (blindaje del aislamiento del log) y F6 (alta de las 6 perillas).

MEDIDO al escribir este archivo:
  data/ci_runs.jsonl      -> 8 lineas, 8 con project="myproject" (100 % fixture)
  data/env_applies.jsonl  -> 10 lineas, 10 con root bajo el tmpdir de pytest
  data/config_transfer_events.jsonl -> 444 lineas LIMPIAS (0 marcadores)

ESTANQUEIDAD DE ESTE ARCHIVO: los casos que hoy escriben en el ledger REAL del
operador (los rojos de F0) pasan por la fixture `_preserva_ledgers_reales`, que
huellea los bytes ANTES y los restaura en el teardown pase lo que pase. Un test
que prueba una contaminacion no puede contaminar.

Correr POR ARCHIVO:
    .venv\\Scripts\\python.exe -m pytest tests/test_plan258_ledger_veracidad.py -v
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import runtime_paths  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
DATA_REAL = BACKEND / "data"
LEDGERS_REALES = ("ci_runs", "env_applies", "db_query_audit",
                  "config_transfer_events", "build_runs")


# ---------------------------------------------------------------------------
# Red de seguridad: ningun caso de este archivo puede dejar tocado un ledger real
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _preserva_ledgers_reales():
    """Huella + restauracion byte a byte de los .jsonl del operador.

    Los casos de F0 estan escritos para FALLAR mientras el portero no exista, y
    en ese estado `append_run` escribe de verdad en `backend/data/ci_runs.jsonl`.
    Sin esta fixture, correr el test rojo contaminaria exactamente el archivo
    cuya contaminacion se esta denunciando.
    """
    previos: dict[Path, bytes | None] = {}
    for nombre in LEDGERS_REALES:
        p = DATA_REAL / f"{nombre}.jsonl"
        previos[p] = p.read_bytes() if p.is_file() else None
    try:
        yield
    finally:
        for p, contenido in previos.items():
            try:
                if contenido is None:
                    if p.is_file():
                        p.unlink()
                elif not p.is_file() or p.read_bytes() != contenido:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(contenido)
            except OSError:  # pragma: no cover — best effort de restauracion
                pass


@pytest.fixture
def data_tmp(tmp_path, monkeypatch):
    """Redirige data_dir() a tmp. El portero NO aisla cuando el data_dir ya fue
    desviado: respeta el desvio explicito del llamador (asi siguen andando los
    tests del 191/198, que huellean el archivo dentro de tmp_path).

    Se parchea `runtime_paths.data_dir` Y el alias local de los tres writers que
    hacen `from runtime_paths import data_dir` (ese `from ... import` congela la
    referencia en import time: parchear solo el modulo origen no los alcanza).
    """
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    for modulo in ("services.db_query", "services.config_transfer", "services.solution_builder"):
        monkeypatch.setattr(importlib.import_module(modulo), "data_dir",
                            lambda: tmp_path, raising=False)
    return tmp_path


def _recargar(nombre_modulo: str):
    mod = importlib.import_module(nombre_modulo)
    return importlib.reload(mod)


# ---------------------------------------------------------------------------
# F0 — casos 1..6: HOY FALLAN. Casos 7 y 8: HOY PASAN.
# ---------------------------------------------------------------------------

def test_append_en_test_mode_no_escribe_el_ledger_real():
    """F0-1 — con STACKY_TEST_MODE activo, un append NO toca backend/data/."""
    assert os.getenv("STACKY_TEST_MODE", "").lower() in ("1", "true", "yes"), \
        "conftest.py:11 debe dejar STACKY_TEST_MODE activo"

    real = DATA_REAL / "ci_runs.jsonl"
    antes = real.read_bytes() if real.is_file() else None

    from services import ci_run_ledger
    ci_run_ledger.append_run({
        "project": "PLAN258_SONDA",
        "tracker_type": "gitlab",
        "pipeline_id": "999258",
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    })

    despues = real.read_bytes() if real.is_file() else None
    assert despues == antes, (
        "una corrida de test escribio en el ledger del operador "
        f"({real}): {len(antes or b'')} -> {len(despues or b'')} bytes"
    )


def test_append_en_test_mode_escribe_ruta_aislada():
    """F0-2 — en test-mode la ruta del ledger cae bajo stacky-test-ledgers."""
    from services.ledger_writer import ledger_path, test_ledgers_dir

    destino = ledger_path("ci_runs")
    aislada = test_ledgers_dir()
    assert aislada == Path(tempfile.gettempdir()) / "stacky-test-ledgers"
    assert destino.parent == aislada, f"{destino} no esta aislada"
    assert DATA_REAL not in destino.parents


def test_todo_evento_lleva_campo_env():
    """F0-3 — todo evento sellado declara procedencia en {prod, test}."""
    from services.ledger_writer import stamp_event

    sellado = stamp_event("ci_runs", {
        "project": "P", "tracker_type": "gitlab",
        "pipeline_id": "1", "triggered_at": "2026-07-27T00:00:00+00:00",
    })
    assert sellado is not None
    assert sellado["env"] in ("prod", "test")
    assert sellado["env"] == "test", "bajo pytest la procedencia es 'test'"
    assert sellado["schema_version"] >= 1


def test_entry_fields_incluye_env():
    """F0-4 — regresion de C4: sin `env` en la ALLOWLIST el campo se descarta."""
    from services import ci_run_ledger, env_apply_ledger

    assert "env" in ci_run_ledger.ENTRY_FIELDS
    assert "schema_version" in ci_run_ledger.ENTRY_FIELDS
    assert "env" in env_apply_ledger.ENTRY_FIELDS
    assert "schema_version" in env_apply_ledger.ENTRY_FIELDS


def test_ledger_valida_esquema_al_escribir(data_tmp):
    """F0-5 — un evento sin las claves obligatorias NO se escribe."""
    from services import ci_run_ledger
    from services.ledger_writer import stamp_event

    assert stamp_event("ci_runs", {"project": "P"}) is None

    ci_run_ledger.append_run({"web_url": "http://x"})  # sin project ni pipeline_id
    destino = data_tmp / "ci_runs.jsonl"
    contenido = destino.read_text(encoding="utf-8") if destino.is_file() else ""
    assert contenido.strip() == "", f"se escribio un evento invalido: {contenido!r}"


def test_orphan_ci_runs_solo_cuenta_prod(data_tmp):
    """F0-6 — un evento de test viejo NO es huerfano; uno de prod si."""
    from services import ci_run_ledger

    viejo = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    filas = [
        {"project": "myproject", "tracker_type": "gitlab", "pipeline_id": "42",
         "triggered_at": viejo, "last_status": None, "env": "test"},
        {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "77",
         "triggered_at": viejo, "last_status": None, "env": "prod"},
    ]
    (data_tmp / "ci_runs.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")

    huerfanos = ci_run_ledger.orphan_ci_runs(older_than_h=24.0)
    assert [h["pipeline_id"] for h in huerfanos] == ["77"]


def test_lector_ignora_campos_desconocidos(data_tmp):
    """F0-7 — HOY PASA: una clave futura no rompe el lector."""
    from services import ci_run_ledger

    fila = {"project": "P", "tracker_type": "gitlab", "pipeline_id": "9",
            "triggered_at": "2026-07-27T00:00:00+00:00",
            "campo_del_futuro": {"anidado": [1, 2, 3]}}
    (data_tmp / "ci_runs.jsonl").write_text(json.dumps(fila) + "\n", encoding="utf-8")

    filas = ci_run_ledger.list_runs()
    assert len(filas) == 1
    assert filas[0]["campo_del_futuro"] == {"anidado": [1, 2, 3]}


def test_update_run_status_existe_y_esta_cableado():
    """F0-8 — HOY PASA: anti-regresion de C2. El cierre YA existe (plan 191) y ya
    esta enganchado al poller. Nadie debe reimplementarlo como `close_ci_run`."""
    from services import ci_run_ledger

    assert callable(getattr(ci_run_ledger, "update_run_status", None))
    src = (BACKEND / "api" / "ci.py").read_text(encoding="utf-8")
    assert "from services.ci_run_ledger import update_run_status" in src
    assert "close_ci_run" not in src


# ---------------------------------------------------------------------------
# F2 — procedencia de lo historico (inferencia POR CAMPO, nunca por substring)
# ---------------------------------------------------------------------------

def test_infer_env_detecta_pytest_root():
    """La PRIMERA linea real de data/env_applies.jsonl -> 'test'."""
    from services.ledger_writer import infer_env_for_legacy_line

    linea = {
        "root": ("C:\\Users\\juanluca\\AppData\\Local\\Temp\\pytest-of-juanluca"
                 "\\pytest-1877\\test_f4_apply_creates_and_repo0"),
        "server_alias": None, "paths": ["IN_", "productivas", "salida"],
        "fingerprint": "c6cb5b63c18e02f2", "result_ok": True,
    }
    assert infer_env_for_legacy_line("env_applies", linea) == "test"


def test_infer_env_detecta_fixture_ci_run():
    """La PRIMERA linea real de data/ci_runs.jsonl -> 'test'."""
    from services.ledger_writer import infer_env_for_legacy_line

    linea = {"project": "myproject", "tracker_type": "gitlab", "ref": "develop",
             "sha": "newsha", "pipeline_id": "42",
             "web_url": "http://gitlab/p/42",
             "triggered_at": "2026-07-20T21:40:38.076369+00:00",
             "source": "stacky", "last_status": None, "finished_at": None}
    assert infer_env_for_legacy_line("ci_runs", linea) == "test"


def test_infer_env_nunca_devuelve_prod():
    """Invariante: afirmar 'prod' sin marca seria inventar el dato."""
    from services.ledger_writer import infer_env_for_legacy_line

    for i in range(100):
        eventos = [
            {"project": f"P{i}", "sha": f"sha{i}", "root": f"/srv/app{i}"},
            {"ts": f"2026-07-{(i % 27) + 1:02d}T00:00:00Z", "result": "ok"},
            {"query": f"SELECT {i} FROM prod", "project": "prod"},
            {"env": "prod"},  # ni siquiera con el campo puesto: esto NO lo lee
            {},
        ]
        for ev in eventos:
            for nombre in LEDGERS_REALES:
                assert infer_env_for_legacy_line(nombre, ev) != "prod"


def test_infer_env_no_marca_por_substring_en_texto_libre():
    """Regresion de C9: la palabra 'pytest' dentro de una query auditada NO es
    evidencia de que la linea la haya escrito un test."""
    from services.ledger_writer import infer_env_for_legacy_line

    linea = {"ts": "2026-07-23T11:10:00Z", "project": "RSPACIFICO",
             "result": "would_execute", "actor": "operator",
             "query": "SELECT * FROM pytest_runs WHERE id > 0"}
    assert infer_env_for_legacy_line("db_query_audit", linea) == "unknown"

    otra = {"ts": "2026-07-23T11:10:00Z", "project": "RSPACIFICO",
            "result": "would_execute",
            "query": "SELECT 'myproject' AS nombre, 'newsha' AS sha"}
    assert infer_env_for_legacy_line("db_query_audit", otra) == "unknown"


def test_infer_env_no_se_llama_si_env_presente(monkeypatch):
    """El campo explicito SIEMPRE gana: la inferencia ni se invoca."""
    from services import ledger_writer

    def _explota(*_a, **_kw):  # pragma: no cover — no debe ejecutarse
        raise AssertionError("infer_env_for_legacy_line no debe llamarse")

    monkeypatch.setattr(ledger_writer, "infer_env_for_legacy_line", _explota)
    assert ledger_writer.event_env("ci_runs", {"env": "prod"}) == "prod"
    assert ledger_writer.event_env("ci_runs", {"env": "test"}) == "test"


def test_read_events_default_incluye_unknown(data_tmp):
    """Regresion de C7: el default ('prod','unknown') NO oculta lo historico."""
    from services.ledger_writer import read_events

    filas = [
        {"ts": "2026-06-19T10:00:00Z", "action": "export", "project": "RSPACIFICO",
         "result": "applied"},                               # sin env -> unknown
        {"ts": "2026-07-27T10:00:00Z", "action": "export", "project": "RSPACIFICO",
         "result": "applied", "env": "prod"},
        {"ts": "2026-07-27T11:00:00Z", "action": "export", "project": "myproject",
         "result": "applied", "env": "test"},
    ]
    (data_tmp / "config_transfer_events.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")

    visibles = read_events("config_transfer_events")
    assert len(visibles) == 2
    assert {v["env"] for v in visibles} == {"unknown", "prod"}


def test_read_events_env_none_devuelve_todo(data_tmp):
    from services.ledger_writer import read_events

    filas = [{"ts": "1", "action": "a", "project": "p", "result": "r"},
             {"ts": "2", "action": "a", "project": "p", "result": "r", "env": "test"}]
    (data_tmp / "config_transfer_events.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")

    assert len(read_events("config_transfer_events", env=None)) == 2
    assert len(read_events("config_transfer_events", env=("prod",))) == 0


def test_read_events_ci_runs_prod_puro_esta_vacio():
    """DoD — la verdad MEDIDA: las 8 lineas del ledger real son fixture y ni una
    se clasifica como produccion.

    El assert de `prod == []` se evalua solo mientras el archivo siga siendo la
    foto medida (8 lineas, todas de fixture). Si algun dia entra una corrida
    REAL, aparecera como `prod` y el test se saltea en vez de ponerse rojo: un
    candado que se dispara con el uso NORMAL del sistema es ruido, no un gate.
    Lo que se verifica siempre es lo que de verdad importa: una linea de fixture
    JAMAS puede contar como produccion.
    """
    from services.ledger_writer import read_events

    real = DATA_REAL / "ci_runs.jsonl"
    if not real.is_file():
        pytest.skip("no hay ledger de CI en este checkout")

    todas = read_events("ci_runs", env=None, path=real)
    fixtures = [f for f in todas if f.get("project") == "myproject"]
    assert fixtures, "el ledger real ya no tiene las lineas de fixture medidas"
    assert all(f["env"] == "test" for f in fixtures), \
        "una linea de fixture NO quedo clasificada como de test"

    if len(fixtures) != len(todas):
        pytest.skip("el ledger real ya tiene lineas ajenas a la foto medida")
    assert read_events("ci_runs", env=("prod",), path=real) == []
    assert len(read_events("ci_runs", env=("test",), path=real)) == len(todas) == 8


def test_marcadores_de_fixture_son_configurables(monkeypatch):
    """La lista de proyectos-fixture sale de la perilla CSV, no de una constante
    incrustada: un operador con un proyecto llamado `myproject` puede vaciarla."""
    import config as _config
    from services import ledger_writer

    linea = {"project": "myproject", "sha": "no-es-el-de-fixture",
             "web_url": "https://gitlab.interno/p/1"}
    assert ledger_writer.infer_env_for_legacy_line("ci_runs", linea) == "test"

    monkeypatch.setattr(_config.config, "STACKY_LEDGER_TEST_MARKERS", "", raising=False)
    assert ledger_writer.infer_env_for_legacy_line("ci_runs", linea) == "unknown"


def test_inferencia_off_deja_todo_en_unknown(monkeypatch):
    """Con la perilla de inferencia apagada nadie marca nada."""
    import config as _config
    from services import ledger_writer

    linea = {"project": "myproject", "sha": "newsha"}
    monkeypatch.setattr(_config.config, "STACKY_LEDGER_LEGACY_INFERENCE_ENABLED",
                        False, raising=False)
    assert ledger_writer.infer_env_for_legacy_line("ci_runs", linea) == "unknown"


# ---------------------------------------------------------------------------
# F1 — el portero no degrada el mecanismo de escritura que ya existe
# ---------------------------------------------------------------------------

def test_ledger_path_respeta_el_desvio_explicito(data_tmp):
    """Si el llamador ya desvio data_dir(), el portero NO lo pisa: es lo que
    mantiene verdes los tests del 191/198, que huellean dentro de tmp_path."""
    from services.ledger_writer import ledger_path

    assert ledger_path("ci_runs") == data_tmp / "ci_runs.jsonl"


def test_append_conserva_lock_atomicidad_y_retencion():
    """Regresion de C3/C10: el portero NO reemplaza el mecanismo de escritura."""
    src = (BACKEND / "services" / "ci_run_ledger.py").read_text(encoding="utf-8")
    assert "_LOCK = threading.Lock()" in src
    assert "tmp.replace(path)" in src
    assert "MAX_ROWS = 500" in src
    assert "out = {k: entry.get(k) for k in ENTRY_FIELDS}" in src


def test_evento_sellado_sobrevive_la_allowlist(data_tmp):
    """El campo `env` llega al disco: la ALLOWLIST lo dejo pasar."""
    from services import ci_run_ledger

    ci_run_ledger.append_run({
        "project": "P", "tracker_type": "gitlab", "pipeline_id": "5",
        "secreto_que_no_debe_pasar": "AKIA-XXXX",
    })
    filas = [json.loads(l) for l in
             (data_tmp / "ci_runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(filas) == 1
    assert filas[0]["env"] == "test"
    assert filas[0]["schema_version"] >= 1
    assert "secreto_que_no_debe_pasar" not in filas[0]


def test_env_apply_sella_procedencia(data_tmp):
    from services import env_apply_ledger

    env_apply_ledger.append_apply({
        "root": str(data_tmp / "app"), "server_alias": None,
        "paths": ["IN_"], "fingerprint": "abc", "result_ok": True,
    })
    filas = [json.loads(l) for l in
             (data_tmp / "env_applies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert filas and filas[0]["env"] == "test"


def test_config_transfer_sella_y_no_pisa_su_schema_version(data_tmp):
    """El ledger LIMPIO de 444 lineas migra ULTIMO y sirve de regresion.

    `config_transfer_events` YA usa `schema_version` para otra cosa (la version
    del perfil del cliente): el sello NO puede pisarlo."""
    from services import config_transfer

    config_transfer.record_event(action="export", project="RSPACIFICO",
                                 result="applied", schema_version=7)
    filas = [json.loads(l) for l in
             (data_tmp / "config_transfer_events.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()]
    assert filas[0]["env"] == "test"
    assert filas[0]["schema_version"] == 7


def test_db_query_audit_sella_procedencia(data_tmp):
    from services import db_query

    db_query.record_audit_event(ticket_id=None, project="RSPACIFICO",
                                query="SELECT 1", duration_ms=1, row_count=0,
                                result="would_execute")
    filas = [json.loads(l) for l in
             (data_tmp / "db_query_audit.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()]
    assert filas and filas[0]["env"] == "test"


def test_los_cinco_ledgers_en_scope_estan_declarados():
    from services.ledger_writer import LEDGER_NAMES, REQUIRED_KEYS

    assert LEDGER_NAMES == ("ci_runs", "env_applies", "db_query_audit",
                            "config_transfer_events", "build_runs")
    for nombre in LEDGER_NAMES:
        assert (nombre, "run") in REQUIRED_KEYS
    # publish_ledger es DB-backed y telemetry_harvest es del plan 255: fuera.
    assert "publish_ledger" not in LEDGER_NAMES
    assert "telemetry_harvest" not in LEDGER_NAMES


def test_strict_schema_off_no_rechaza(monkeypatch):
    """Con la perilla apagada el portero degrada a permisivo (sella pero no
    rechaza): apagarla nunca puede TIRAR eventos."""
    import config as _config
    from services.ledger_writer import stamp_event

    monkeypatch.setattr(_config.config, "STACKY_LEDGER_STRICT_SCHEMA_ENABLED",
                        False, raising=False)
    sellado = stamp_event("ci_runs", {"project": "solo-esto"})
    assert sellado is not None and sellado["env"] == "test"


# ---------------------------------------------------------------------------
# F3 — reconciliacion por (project, pipeline_id) y huerfanos
# ---------------------------------------------------------------------------

def test_update_run_status_reconciliacion_por_project_y_pipeline_id(data_tmp):
    """EL BUG REAL: el pipeline_id 42 se repite 6 veces en la evidencia medida.
    Sin `project`, el cierre de un proyecto se escribia sobre otro."""
    from services import ci_run_ledger

    filas = [
        {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "42",
         "triggered_at": "2026-07-27T10:00:00+00:00", "last_status": None},
        {"project": "RIPLEY", "tracker_type": "gitlab", "pipeline_id": "42",
         "triggered_at": "2026-07-27T11:00:00+00:00", "last_status": None},
    ]
    (data_tmp / "ci_runs.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")

    assert ci_run_ledger.update_run_status("42", "success", project="RSPACIFICO") is True

    leidas = {r["project"]: r for r in ci_run_ledger.list_runs()}
    assert leidas["RSPACIFICO"]["last_status"] == "success"
    assert leidas["RIPLEY"]["last_status"] is None, \
        "el cierre de RSPACIFICO se escribio sobre la corrida de RIPLEY"


def test_update_run_status_sin_project_es_compatible(data_tmp):
    """Backward-compat: el call-site viejo sigue funcionando (el mas reciente)."""
    from services import ci_run_ledger

    filas = [
        {"project": "A", "tracker_type": "ado", "pipeline_id": "7",
         "triggered_at": "2026-07-27T10:00:00+00:00", "last_status": None},
        {"project": "B", "tracker_type": "ado", "pipeline_id": "7",
         "triggered_at": "2026-07-27T12:00:00+00:00", "last_status": None},
    ]
    (data_tmp / "ci_runs.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")

    assert ci_run_ledger.update_run_status("7", "failed") is True
    leidas = {r["project"]: r for r in ci_run_ledger.list_runs()}
    assert leidas["B"]["last_status"] == "failed"
    assert leidas["A"]["last_status"] is None
    assert ci_run_ledger.update_run_status("99999", "failed") is False


def test_update_run_status_project_desconocido_es_noop(data_tmp):
    from services import ci_run_ledger

    filas = [{"project": "A", "tracker_type": "ado", "pipeline_id": "7",
              "triggered_at": "2026-07-27T10:00:00+00:00", "last_status": None}]
    (data_tmp / "ci_runs.jsonl").write_text(json.dumps(filas[0]) + "\n", encoding="utf-8")
    assert ci_run_ledger.update_run_status("7", "success", project="OTRO") is False
    assert ci_run_ledger.list_runs()[0]["last_status"] is None


def test_orphan_ci_runs_ignora_test_y_unknown(data_tmp):
    from services import ci_run_ledger

    viejo = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    filas = [
        {"project": "myproject", "tracker_type": "gitlab", "pipeline_id": "1",
         "sha": "newsha", "triggered_at": viejo, "last_status": None},      # infiere test
        {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "2",
         "triggered_at": viejo, "last_status": None},                       # unknown
        {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "3",
         "triggered_at": viejo, "last_status": None, "env": "prod"},        # SI
        {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "4",
         "triggered_at": viejo, "last_status": "success", "env": "prod"},   # cerrada
    ]
    (data_tmp / "ci_runs.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")

    assert [h["pipeline_id"] for h in ci_run_ledger.orphan_ci_runs()] == ["3"]


def test_orphan_ci_runs_now_inyectable(data_tmp):
    """El test no depende del reloj de la maquina."""
    from services import ci_run_ledger

    disparo = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
    fila = {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "5",
            "triggered_at": disparo.isoformat(), "last_status": None, "env": "prod"}
    (data_tmp / "ci_runs.jsonl").write_text(json.dumps(fila) + "\n", encoding="utf-8")

    casi = disparo + timedelta(hours=23, minutes=59)
    pasado = disparo + timedelta(hours=24, minutes=1)
    assert ci_run_ledger.orphan_ci_runs(now=casi) == []
    assert len(ci_run_ledger.orphan_ci_runs(now=pasado)) == 1
    assert ci_run_ledger.orphan_ci_runs(older_than_h=48.0, now=pasado) == []


def test_orphan_ci_runs_off_devuelve_vacio(data_tmp, monkeypatch):
    import config as _config
    from services import ci_run_ledger

    viejo = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    fila = {"project": "RSPACIFICO", "tracker_type": "ado", "pipeline_id": "3",
            "triggered_at": viejo, "last_status": None, "env": "prod"}
    (data_tmp / "ci_runs.jsonl").write_text(json.dumps(fila) + "\n", encoding="utf-8")

    monkeypatch.setattr(_config.config, "STACKY_LEDGER_ORPHAN_REPORT_ENABLED",
                        False, raising=False)
    assert ci_run_ledger.orphan_ci_runs() == []


def test_env_breakdown_desglosa_por_procedencia(data_tmp):
    from services.ledger_writer import env_breakdown

    filas = [
        {"project": "myproject", "sha": "newsha", "pipeline_id": "1",
         "tracker_type": "gitlab", "triggered_at": "2026-07-20T00:00:00+00:00"},
        {"project": "RSPACIFICO", "pipeline_id": "2", "tracker_type": "ado",
         "triggered_at": "2026-07-21T00:00:00+00:00"},
        {"project": "RSPACIFICO", "pipeline_id": "3", "tracker_type": "ado",
         "triggered_at": "2026-07-22T00:00:00+00:00", "env": "prod"},
    ]
    (data_tmp / "ci_runs.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")

    d = env_breakdown("ci_runs")
    assert d == {"total": 3, "prod": 1, "test": 1, "unknown": 1}


# ---------------------------------------------------------------------------
# F3 — endpoint GET /api/diag/ledgers/health
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client (mismo patron que tests/test_plan257_log_noise_api.py)."""
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


def test_endpoint_ledgers_health_desglosa_por_env(client, tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    viejo = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    filas = [
        {"project": "myproject", "sha": "newsha", "pipeline_id": "42",
         "tracker_type": "gitlab", "triggered_at": viejo, "last_status": None},
        {"project": "RSPACIFICO", "pipeline_id": "77", "tracker_type": "ado",
         "triggered_at": viejo, "last_status": None, "env": "prod"},
    ]
    (tmp_path / "ci_runs.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")

    res = client.get("/api/diag/ledgers/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True

    porn = {l["name"]: l for l in body["ledgers"]}
    assert set(porn) == set(LEDGERS_REALES)
    assert porn["ci_runs"]["total"] == 2
    assert porn["ci_runs"]["test"] == 1
    assert porn["ci_runs"]["prod"] == 1
    assert porn["ci_runs"]["unknown"] == 0
    assert [o["pipeline_id"] for o in body["orphans"]] == ["77"]


def test_endpoint_ledgers_health_sin_datos_no_rompe(client, tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    body = client.get("/api/diag/ledgers/health").get_json()
    assert body["ok"] is True
    assert all(l["total"] == 0 for l in body["ledgers"])
    assert body["orphans"] == []
    assert body["deletable_total"] == 0


def test_endpoint_health_emite_confirmacion_solo_con_purga_on(client, tmp_path, monkeypatch):
    import config as _config

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    fila = {"project": "myproject", "sha": "newsha", "pipeline_id": "42",
            "tracker_type": "gitlab", "triggered_at": "2026-07-20T00:00:00+00:00"}
    (tmp_path / "ci_runs.jsonl").write_text(json.dumps(fila) + "\n", encoding="utf-8")

    monkeypatch.setattr(_config.config, "STACKY_LEDGER_PURGE_ENABLED", False, raising=False)
    porn = {l["name"]: l for l in client.get("/api/diag/ledgers/health").get_json()["ledgers"]}
    assert porn["ci_runs"]["deletable"] == 1
    assert porn["ci_runs"]["confirm_token"] is None

    monkeypatch.setattr(_config.config, "STACKY_LEDGER_PURGE_ENABLED", True, raising=False)
    porn = {l["name"]: l for l in client.get("/api/diag/ledgers/health").get_json()["ledgers"]}
    assert isinstance(porn["ci_runs"]["confirm_token"], str)
    assert porn["ci_runs"]["confirm_token"]


# ---------------------------------------------------------------------------
# F5 — blindar (no reabrir) el aislamiento del log del operador
# ---------------------------------------------------------------------------

def test_log_del_operador_sin_mocks_despues_del_fix_145():
    """Plan 258 F5 — regresion del hallazgo real: 'DB exploded'
    (tests/test_adaptive_selector_wiring.py:260) y 'test_reaper'
    (tests/test_cutover_p5.py:505) llegaron al log del operador HASTA el
    2026-07-16. El plan 145 (commit f00f161f, 2026-07-16 02:05:19 -0300) lo
    cerro redirigiendo el handler a %TEMP% (local_file_logging.py:165).

    Este test NO exige borrar la historia: escanea solo los logs con fecha
    POSTERIOR al fix. Si vuelve a aparecer un mock ahi, el aislamiento se rompio.

    El log del DIA del fix queda FUERA de la ventana (`day <= FIX_DATE`) porque
    contiene las 4 lineas de `test_reaper` de las 01:23-01:43, anteriores al
    commit de las 02:05. No es una excepcion arbitraria.
    """
    from datetime import date

    FIX_DATE = date(2026, 7, 16)
    log_dir = BACKEND / "data" / "logs"
    for f in sorted(log_dir.glob("stacky-*.log")):
        crudo = f.stem.replace("stacky-", "")
        crudo = crudo.split(".")[0]          # partes numeradas del 257: stacky-YYYY-MM-DD.3
        try:
            day = date.fromisoformat(crudo)
        except ValueError:
            continue
        if day <= FIX_DATE:
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        assert "DB exploded" not in txt, f"mock de test en {f.name}"
        assert "test_reaper" not in txt, f"trigger de test en {f.name}"


def test_conftest_guard_detecta_handler_al_log_real(guard_log_handlers):
    """Se instala a mano un handler apuntando a data/logs/ y el guard lo nombra."""
    log_real = BACKEND / "data" / "logs"
    log_real.mkdir(parents=True, exist_ok=True)
    destino = log_real / "plan258-sonda-del-guard.log"

    assert guard_log_handlers() == []
    h = logging.FileHandler(destino, delay=True, encoding="utf-8")
    root = logging.getLogger()
    root.addHandler(h)
    try:
        ofensores = guard_log_handlers()
        assert ofensores, "el guard no detecto un handler apuntando al log del operador"
        assert any("plan258-sonda-del-guard.log" in o for o in ofensores)
    finally:
        root.removeHandler(h)
        h.close()
        destino.unlink(missing_ok=True)
    assert guard_log_handlers() == []


def test_install_file_log_handler_conserva_su_firma():
    """Anti-regresion de C1: el plan 145 redirige, NO desinstala. Un implementador
    futuro no puede 'arreglar' esto cambiandole la firma (seria del plan 257,
    ademas: local_file_logging.py NO se toca en este plan)."""
    import inspect

    from services.local_file_logging import install_file_log_handler

    sig = inspect.signature(install_file_log_handler)
    assert "base_dir" in sig.parameters
    assert "retention_days" in sig.parameters
    assert sig.return_annotation in (None, "None")


# ---------------------------------------------------------------------------
# F6 — las 6 perillas, en la UI (no alcanza con el atributo en config.py)
# ---------------------------------------------------------------------------

_FLAGS_258 = {
    "STACKY_LEDGER_STRICT_SCHEMA_ENABLED": True,
    "STACKY_LEDGER_LEGACY_INFERENCE_ENABLED": True,
    "STACKY_LEDGER_ORPHAN_REPORT_ENABLED": True,
    "STACKY_LEDGER_PURGE_ENABLED": False,
    "STACKY_LEDGER_TEST_MARKERS": None,          # csv, sin default declarado
    "STACKY_HARNESS_AIRTIGHT_GUARD_ENABLED": True,
}


def test_las_6_flags_del_258_estan_en_el_registry():
    from services.harness_flags import FLAG_REGISTRY

    specs = {s.key: s for s in FLAG_REGISTRY}
    faltantes = sorted(set(_FLAGS_258) - set(specs))
    assert faltantes == [], f"perillas del 258 sin FlagSpec: {faltantes}"

    for key, esperado in _FLAGS_258.items():
        spec = specs[key]
        assert spec.type == ("csv" if key.endswith("_MARKERS") else "bool")
        # Una flag default OFF NO declara default=: `default is not None` es lo
        # que vuelve conocido el default y rompe test_default_known_only_for_curated.
        assert spec.default is (esperado if esperado else None), \
            f"{key}: default declarado {spec.default!r}, esperado {esperado or None!r}"


def test_flags_del_258_tienen_categoria():
    from services.harness_flags import _CATEGORY_KEYS

    en_obs = set(_CATEGORY_KEYS["observabilidad_notif"])
    faltantes = sorted(set(_FLAGS_258) - en_obs)
    assert faltantes == [], f"perillas del 258 sin categoria: {faltantes}"


def test_defaults_on_del_258_estan_curados():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON  # noqa: PLC0415

    on = {k for k, v in _FLAGS_258.items() if v is True}
    assert on <= set(_CURATED_DEFAULTS_ON)
    assert "STACKY_LEDGER_PURGE_ENABLED" not in _CURATED_DEFAULTS_ON


def test_purge_requires_inference():
    from services.harness_flags import FLAG_REGISTRY

    specs = {s.key: s for s in FLAG_REGISTRY}
    assert specs["STACKY_LEDGER_PURGE_ENABLED"].requires == \
        "STACKY_LEDGER_LEGACY_INFERENCE_ENABLED"
    # Profundidad 1 (regla R4): la madre no puede declarar requires.
    assert specs["STACKY_LEDGER_LEGACY_INFERENCE_ENABLED"].requires is None


def test_flags_del_258_tienen_ayuda_llana():
    from services.harness_flags_help import PLAIN_HELP

    faltantes = sorted(set(_FLAGS_258) - set(PLAIN_HELP))
    assert faltantes == [], f"perillas del 258 sin ayuda: {faltantes}"
    for key in _FLAGS_258:
        entrada = PLAIN_HELP[key]
        assert entrada.on_effect.startswith("Si ")
        assert entrada.off_effect.startswith("Si ")
        assert len(entrada.what) <= 200
        assert len(entrada.on_effect) <= 240
        assert len(entrada.off_effect) <= 240
        assert len(entrada.example) <= 300


def test_flags_del_258_existen_en_config():
    import config as _config

    for key in _FLAGS_258:
        assert hasattr(_config.config, key), f"config.config sin atributo {key}"
