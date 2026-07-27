"""Plan 256 F3+F4 — la cuarentena, visible y accionable.

F3 EXTIENDE el endpoint `GET /api/diag/intake-quarantine` que ya existe desde el
plan 149 (prohibido crear un gemelo): conserva `path`/`reason`/`mtime_ns` tal
cual y agrega causa, antiguedad, ocurrencias y si se puede reintentar.

F4 cierra el ciclo con dos acciones que decide SIEMPRE el operador: `retry`
(reusa `clear_quarantine`, no destructivo, un clic) y `discard` (no borra ni
modifica el artefacto: marca el sidecar, exige confirmacion y vive detras de una
flag apagada por defecto).

Correr POR ARCHIVO:
    .venv\\Scripts\\python.exe -m pytest tests/test_plan256_quarantine_api.py -v
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


# ── infraestructura ─────────────────────────────────────────────────────────


def _reset_quarantine(ow) -> None:
    ow._SEEN_TERMINAL_PENDING.clear()
    ow._QUARANTINE_REASON.clear()
    for name in ("_QUARANTINE_CAUSE", "_QUARANTINE_META"):
        bucket = getattr(ow, name, None)
        if isinstance(bucket, dict):
            bucket.clear()


@pytest.fixture(autouse=True)
def _clean_quarantine_state():
    from services import output_watcher as ow

    _reset_quarantine(ow)
    yield
    _reset_quarantine(ow)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client (mismo patron que tests/test_plan253_health_guard.py)."""
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


@pytest.fixture
def outputs_dir(tmp_path, monkeypatch):
    """`outputs_dir` del watcher VIVO apuntando a un temporal.

    Se instala el singleton con override explicito: es lo que consulta la
    validacion anti-traversal de los endpoints (la property `outputs_dir`
    respeta `_outputs_dir_override`)."""
    from services import output_watcher as ow

    base = tmp_path / "Agentes" / "outputs"
    base.mkdir(parents=True)
    monkeypatch.setattr(ow, "_GLOBAL_WATCHER", ow.AdoOutputWatcher(outputs_dir=base))
    return base


def _artifact(outputs_dir: Path, *, epic: int = 28, rf: str = "rf-028",
              body: str = "") -> Path:
    from services.output_watcher import PENDING_TASK_FILENAME

    rf_dir = outputs_dir / f"epic-{epic}" / rf
    rf_dir.mkdir(parents=True, exist_ok=True)
    pt_file = rf_dir / PENDING_TASK_FILENAME
    pt_file.write_text(body, encoding="utf-8")
    return pt_file


def _cuarentenar(pt_file: Path, *, cause_code: str = "INTAKE_EMPTY",
                 reason: str | None = None) -> None:
    from services.output_watcher import _quarantine_pending_once

    _quarantine_pending_once(
        pt_file,
        reason or ("intake rechazo el artefacto: el archivo esta vacio o solo tiene "
                   "espacios; el agente no llego a escribir el contenido."),
        cause_code=cause_code,
    )


def _envejecer(pt_file: Path, dias: int) -> None:
    """Retrocede el `first_seen` de la entrada (y de su sidecar) N dias."""
    from datetime import datetime, timedelta, timezone

    from services import output_watcher as ow

    viejo = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    key = str(pt_file)
    ow._QUARANTINE_META[key]["first_seen"] = viejo


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _items(client, *, query: str = "") -> list[dict]:
    payload = client.get("/api/diag/intake-quarantine" + query).get_json()
    return payload["items"]


# ── F3 — el endpoint EXISTENTE, extendido ──────────────────────────────────


def test_endpoint_vacio_devuelve_count_cero(client, outputs_dir):
    payload = client.get("/api/diag/intake-quarantine").get_json()
    assert payload["enabled"] is True
    assert payload["count"] == 0
    assert payload["items"] == []


def test_endpoint_conserva_las_claves_del_plan_149(client, outputs_dir):
    """Anti-regresion de contrato: el plan 149 ya publicaba estas 3 claves y
    hay consumidores. Agregar campos es legal; renombrarlos no."""
    pt_file = _artifact(outputs_dir)
    _cuarentenar(pt_file)

    item = _items(client)[0]
    assert item["path"] == str(pt_file)
    assert isinstance(item["reason"], str) and item["reason"].strip() != ""
    assert isinstance(item["mtime_ns"], int)


def test_endpoint_expone_cause_code_y_age_days(client, outputs_dir):
    pt_file = _artifact(outputs_dir)
    _cuarentenar(pt_file)
    _envejecer(pt_file, 10)

    item = _items(client)[0]
    assert item["cause_code"] == "INTAKE_EMPTY"
    assert item["age_days"] == 10, "la antiguedad es el campo que hace visible el caso testigo"
    assert item["file_name"] == "pending-task.json"
    assert item["occurrences"] == 1
    assert item["discarded"] is False
    assert item["has_original_backup"] is False
    assert item["first_seen"]


def test_endpoint_nunca_devuelve_reason_vacia(client, outputs_dir):
    for i, cause in enumerate(("INTAKE_EMPTY", "INTAKE_TRUNCATED", "WATCHER_UNREADABLE")):
        pt_file = _artifact(outputs_dir, rf=f"rf-{i:03d}")
        _cuarentenar(pt_file, cause_code=cause, reason=f"razon concreta {i}")

    items = _items(client)
    assert len(items) == 3
    for item in items:
        assert item["reason"].strip() != ""


def test_retryable_false_solo_para_orig_backup_failed(client, outputs_dir):
    fallado = _artifact(outputs_dir, rf="rf-orig")
    _cuarentenar(fallado, cause_code="ORIG_BACKUP_FAILED",
                 reason="reparacion abortada: no se pudo escribir la copia .orig")
    vacio = _artifact(outputs_dir, rf="rf-vacio")
    _cuarentenar(vacio, cause_code="INTAKE_EMPTY")

    por_path = {i["path"]: i for i in _items(client)}
    assert por_path[str(fallado)]["retryable"] is False
    assert por_path[str(vacio)]["retryable"] is True


def test_descartados_ocultos_salvo_include_discarded(client, outputs_dir):
    from services.output_watcher import quarantine_discard

    descartado = _artifact(outputs_dir, rf="rf-descartado")
    _cuarentenar(descartado)
    vivo = _artifact(outputs_dir, rf="rf-vivo")
    _cuarentenar(vivo)
    assert quarantine_discard(descartado, operator="operador")["ok"] is True

    default = _items(client)
    assert [i["path"] for i in default] == [str(vivo)]

    con_descartados = _items(client, query="?include_discarded=1")
    assert {i["path"] for i in con_descartados} == {str(vivo), str(descartado)}
    marcado = [i for i in con_descartados if i["path"] == str(descartado)][0]
    assert marcado["discarded"] is True


def test_flag_surface_off_devuelve_enabled_false(client, outputs_dir, monkeypatch):
    """Es la flag del plan 149, no una nueva."""
    import config as cfg

    pt_file = _artifact(outputs_dir)
    _cuarentenar(pt_file)
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", False)

    payload = client.get("/api/diag/intake-quarantine").get_json()
    assert payload["enabled"] is False
    assert payload["items"] == []


# ── F4 — reintentar o descartar, con el operador decidiendo ────────────────


@pytest.fixture
def discard_on(monkeypatch):
    """La flag del descarte nace APAGADA (accion irreversible desde la UI)."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED", True)
    from services.confirm_token import reset_for_tests

    reset_for_tests()
    yield
    reset_for_tests()


def _discard(client, pt_file: Path, *, token: str | None = None):
    body = {"path": str(pt_file)}
    if token is not None:
        body["confirm_token"] = token
    return client.post("/api/diag/intake-quarantine/discard", json=body)


def _discard_confirmado(client, pt_file: Path):
    """Los dos pasos del interlock: pedir y confirmar."""
    primero = _discard(client, pt_file)
    assert primero.status_code == 409
    token = primero.get_json()["confirm_token"]
    return _discard(client, pt_file, token=token)


def test_retry_reusa_clear_quarantine(client, outputs_dir, monkeypatch):
    """Prueba el REUSO, no una copia: el plan 149 ya publico `clear_quarantine`
    con el gotcha de la clave en Windows documentado. Un gemelo lo perderia."""
    from services import output_watcher as ow

    pt_file = _artifact(outputs_dir)
    _cuarentenar(pt_file)

    llamadas: list[Path] = []
    real = ow.clear_quarantine

    def _espia(path):
        llamadas.append(path)
        return real(path)

    monkeypatch.setattr(ow, "clear_quarantine", _espia)
    resp = client.post("/api/diag/intake-quarantine/retry", json={"path": str(pt_file)})

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert [str(p) for p in llamadas] == [str(pt_file)]
    assert _items(client) == []


def test_retry_no_modifica_el_archivo(client, outputs_dir):
    pt_file = _artifact(outputs_dir, body='{"a": 1}')
    _cuarentenar(pt_file)
    hash_antes = _sha256(pt_file)
    mtime_antes = pt_file.stat().st_mtime_ns

    resp = client.post("/api/diag/intake-quarantine/retry", json={"path": str(pt_file)})

    assert resp.status_code == 200
    assert _sha256(pt_file) == hash_antes
    assert pt_file.stat().st_mtime_ns == mtime_antes


def test_retry_es_idempotente(client, outputs_dir):
    from services import output_watcher as ow

    pt_file = _artifact(outputs_dir)
    _cuarentenar(pt_file)

    primero = client.post("/api/diag/intake-quarantine/retry", json={"path": str(pt_file)})
    segundo = client.post("/api/diag/intake-quarantine/retry", json={"path": str(pt_file)})

    assert primero.status_code == 200 and primero.get_json()["was_quarantined"] is True
    assert segundo.status_code == 200 and segundo.get_json()["ok"] is True
    assert segundo.get_json()["was_quarantined"] is False
    assert not ow._sidecar_path(pt_file).exists(), "el sidecar sobrevivio al reintento"


def test_discard_sin_token_devuelve_409(client, outputs_dir, monkeypatch):
    import config as cfg

    pt_file = _artifact(outputs_dir)
    _cuarentenar(pt_file)

    # Con la flag apagada (default) el descarte ni siquiera existe.
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED", False)
    assert _discard(client, pt_file).status_code == 404

    # Encendida, sin confirmar: 409 y el artefacto sigue vivo en la lista.
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED", True)
    resp = _discard(client, pt_file)
    assert resp.status_code == 409
    cuerpo = resp.get_json()
    assert cuerpo["ok"] is False
    assert cuerpo["confirm_token"], "sin identificador de confirmacion no hay como confirmar"
    assert [i["path"] for i in _items(client)] == [str(pt_file)]

    # Un identificador inventado tampoco alcanza.
    assert _discard(client, pt_file, token="inventado").status_code == 409


def test_discard_no_toca_el_artefacto(client, outputs_dir, discard_on):
    pt_file = _artifact(outputs_dir, body='{"trabajo": "del agente"}')
    _cuarentenar(pt_file)
    hash_antes = _sha256(pt_file)
    mtime_antes = pt_file.stat().st_mtime_ns

    resp = _discard_confirmado(client, pt_file)

    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    assert _sha256(pt_file) == hash_antes, "el descarte modifico el trabajo del agente"
    assert pt_file.stat().st_mtime_ns == mtime_antes
    assert pt_file.read_text(encoding="utf-8") == '{"trabajo": "del agente"}'


def test_discard_marca_el_sidecar_y_el_watcher_lo_omite(client, outputs_dir, discard_on):
    from services import output_watcher as ow

    pt_file = _artifact(outputs_dir)
    _cuarentenar(pt_file)
    _discard_confirmado(client, pt_file)

    sidecar = ow._read_sidecar(pt_file)
    assert sidecar["discarded_at"], "el marcador de descarte no quedo en el sidecar"
    assert sidecar["discarded_by"]
    assert ow._pending_is_quarantined(pt_file) is True, "el watcher volveria a intentarlo"

    # Y sobrevive al reinicio: el operador no tiene que descartarlo dos veces.
    _reset_quarantine(ow)
    ow._rehydrate_quarantine(outputs_dir)
    assert ow._pending_is_quarantined(pt_file) is True

    # Idempotente: descartar de nuevo no pisa la marca original.
    otra = _discard_confirmado(client, pt_file)
    assert otra.get_json()["discarded_at"] == sidecar["discarded_at"]


def test_discard_con_sidecar_no_escribible_mantiene_la_entrada(client, outputs_dir,
                                                               discard_on, monkeypatch):
    from services import output_watcher as ow

    pt_file = _artifact(outputs_dir)
    _cuarentenar(pt_file)
    sidecar = ow._sidecar_path(pt_file)
    real_write_text = Path.write_text

    def _falla_solo_el_sidecar(self, *args, **kwargs):
        if str(self) == str(sidecar):
            raise OSError("carpeta de solo lectura (simulado)")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _falla_solo_el_sidecar)
    resp = _discard_confirmado(client, pt_file)
    monkeypatch.undo()

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "sidecar_not_writable"
    # Lo importante: el item NO se pierde de la vista del operador.
    assert [i["path"] for i in _items(client)] == [str(pt_file)]
    assert _items(client)[0]["discarded"] is False


@pytest.mark.parametrize("ruta", ["traversal", "absoluto_ajeno", "prefijo_evil"])
def test_path_fuera_de_outputs_dir_devuelve_400(client, outputs_dir, discard_on, ruta, tmp_path):
    candidatos = {
        "traversal": str(outputs_dir / ".." / ".." / ".." / "Windows" / "win.ini"),
        "absoluto_ajeno": str(tmp_path / "ajeno" / "pending-task.json"),
        "prefijo_evil": str(Path(str(outputs_dir) + "-evil") / "x.json"),
    }
    body = {"path": candidatos[ruta]}

    retry = client.post("/api/diag/intake-quarantine/retry", json=body)
    discard = client.post("/api/diag/intake-quarantine/discard", json=body)

    assert retry.status_code == 400, retry.get_json()
    assert discard.status_code == 400, discard.get_json()
    assert retry.get_json()["error"] == "path_outside_outputs"


def test_ninguna_accion_es_automatica(outputs_dir, monkeypatch):
    """Reemplaza al grep del v1 (gameable: lo rompia un comentario).

    Es un test DE COMPORTAMIENTO: se corre un `scan_once()` real sobre un epic
    dir con un artefacto en cuarentena, con espias en las dos acciones, y se
    exige cero llamadas. Si el watcher reintentara o descartara por su cuenta,
    la entrada desapareceria de la cuarentena y el espia lo registraria.
    """
    import os as _os

    import requests

    from db import init_db, run_with_retry
    from services import output_watcher as ow

    # El camino caliente consulta la base (resolucion del epic efectivo). Crear
    # el esquema en la sqlite en memoria evita que el scan muera antes de llegar
    # al gate de cuarentena y deje un verde vacio.
    run_with_retry(init_db, label="plan256-init-db")

    pt_file = _artifact(outputs_dir, body="")
    _cuarentenar(pt_file)
    # Un hermano SANO en el mismo epic: prueba que el camino caliente corrio de
    # verdad (si no, `posts == []` seria un verde vacio).
    import json as _json

    sano = _artifact(outputs_dir, rf="rf-sano", body=_json.dumps({
        "title": "RF sano",
        "description_html": "<p>x</p>",
        "epic_id": 28,
        "rf_id": "RF-SANO",
        "status": "pending",
        "generated_at": "2026-07-27T00:00:00Z",
        "generated_by": "test-plan256",
        "parent_link_type": "child",
        "plan_de_pruebas_path": "plan-de-pruebas.md",
    }))
    # Envejecer los artefactos para pasar el debounce y llegar al camino caliente.
    for f in (pt_file, sano):
        viejo = _os.stat(f).st_mtime - 3600
        _os.utime(f, (viejo, viejo))
    ow._SEEN_TERMINAL_PENDING[str(pt_file)] = pt_file.stat().st_mtime_ns

    retries: list = []
    discards: list = []
    posts: list = []
    monkeypatch.setattr(ow, "clear_quarantine", lambda p: retries.append(p) or True)
    monkeypatch.setattr(ow, "quarantine_discard", lambda p, **kw: discards.append(p) or {})
    monkeypatch.setenv("STACKY_TEST_ALLOW_WATCHER_SELF_POST", "1")
    monkeypatch.setattr(requests, "post", lambda url, **kw: posts.append(url))

    watcher = ow.get_output_watcher()
    run_with_retry(watcher.scan_once, label="plan256-scan-once")

    assert retries == [], "scan_once reintento por su cuenta"
    assert discards == [], "scan_once descarto por su cuenta"
    assert ow._pending_is_quarantined(pt_file) is True, "el scan saco el artefacto de cuarentena"
    # El camino caliente CORRIO (el hermano sano llego al endpoint) y aun asi el
    # artefacto en cuarentena no se toco: la barrera es el gate, no un skip mudo.
    assert len(posts) == 1, f"el camino caliente no corrio: {posts}"
    assert ow._sidecar_path(pt_file).exists()
    assert ow._read_sidecar(pt_file)["discarded_at"] is None
