"""Plan 256 F0/F1/F2 — Intake sin perdida: ningun artefacto rechazado sin razon.

F0 hace DOS cosas distintas y hay que no confundirlas:

  * CONGELA lo que ya funciona. El v1 del plan creia que el watcher rechazaba
    artefactos sin decir por que; se midio y es falso (0 de 26 mensajes con la
    razon vacia). Los casos 1, 2 y 8 nacen VERDES a proposito: son la red que
    caza la regresion de un invariante que hoy se cumple por construccion.
  * REPRODUCE lo que si esta roto. Los casos 3, 4, 5, 6 y 7 nacen ROJOS: la
    cuarentena vive en un dict de RAM que el reinicio borra, sin causa tipada,
    sin antiguedad y sin copia del original.

Reparto esperado en F0: 3 verdes (1, 2, 8) + 5 rojos (3, 4, 5, 6, 7).
Correr POR ARCHIVO (la suite completa del backend tiene contaminacion conocida):
    .venv\\Scripts\\python.exe -m pytest tests/test_plan256_intake_razon.py -v
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────


def _reset_quarantine(ow) -> None:
    """Simula el reinicio del backend: vacia TODOS los dicts de modulo de la
    cuarentena. Los dos historicos (plan 149) y los que agrega el plan 256; los
    nuevos se limpian con getattr para que el archivo importe en F0."""
    ow._SEEN_TERMINAL_PENDING.clear()
    ow._QUARANTINE_REASON.clear()
    for name in ("_QUARANTINE_CAUSE", "_QUARANTINE_META"):
        bucket = getattr(ow, name, None)
        if isinstance(bucket, dict):
            bucket.clear()


@pytest.fixture(autouse=True)
def _clean_quarantine_state():
    """La cuarentena es estado de MODULO: sin limpieza en setup y teardown, un
    test contamina al siguiente (mismo patron que test_plan149_*)."""
    from services import output_watcher as ow

    _reset_quarantine(ow)
    yield
    _reset_quarantine(ow)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(tmp_path: Path, *, name: str = "rf-028", body: str = "") -> Path:
    """Crea <tmp>/outputs/epic-28/<name>/pending-task.json con el layout real."""
    from services.output_watcher import PENDING_TASK_FILENAME

    rf_dir = tmp_path / "outputs" / "epic-28" / name
    rf_dir.mkdir(parents=True, exist_ok=True)
    pt_file = rf_dir / PENDING_TASK_FILENAME
    pt_file.write_text(body, encoding="utf-8")
    return pt_file


# ── 1 — VERDE: el invariante que el v1 creia roto ────────────────────────────


def test_ok_false_siempre_trae_errors():
    """Ningun camino ok=False de artifact_intake devuelve errors vacio.

    Es caracterizacion, no un fix: hoy pasa. Si algun dia alguien agrega un
    `return IntakeResult(ok=False, errors=[])`, este test lo caza.
    """
    from services.artifact_intake import validate_and_normalize

    ctx = {"valid_ado_ids": [28]}
    for raw in ("", "{", "[]", '{"foo": 1}'):
        result = validate_and_normalize(
            raw=raw, kind="pending_task_json", ticket_context=ctx
        )
        assert result.ok is False, f"{raw!r} deberia ser rechazado"
        assert len(result.errors) >= 1, f"{raw!r} rechazado SIN razon"
        assert "".join(result.errors).strip() != "", f"{raw!r} con razon en blanco"

    html = validate_and_normalize(raw="   ", kind="comment_html")
    assert html.ok is False and len(html.errors) >= 1


# ── 2 — VERDE: anti-regresion de C2 (el campo es reason_code, NO code) ───────


def test_reason_code_es_el_nombre_del_campo():
    """El v1 leia un atributo `code` que no existe: AttributeError en el camino
    caliente del intake. El campo real se llama `reason_code`."""
    from services.artifact_intake import IntakeResult

    campos = IntakeResult.__dataclass_fields__
    assert "reason_code" in campos
    assert "code" not in campos


# ── 3 — ROJO en F0: el mapeo unico reason_code -> cause_code ────────────────


def test_cause_from_intake_mapea_los_5_reason_codes():
    from services.artifact_intake import IntakeResult
    from services.output_watcher import _cause_from_intake

    esperado = {
        "empty": "INTAKE_EMPTY",
        "truncated": "INTAKE_TRUNCATED",
        "malformed": "INTAKE_MALFORMED",
        "schema": "INTAKE_SCHEMA",
        "anti_ordinal": "INTAKE_ANTI_ORDINAL",
    }

    def _res(reason_code):
        return IntakeResult(
            ok=False, normalized=None, repaired=False,
            errors=["x"], reason_code=reason_code,
        )

    for reason_code, cause in esperado.items():
        assert _cause_from_intake(_res(reason_code)) == cause

    assert _cause_from_intake(_res(None)) == "UNKNOWN"
    assert _cause_from_intake(_res("un_codigo_marciano")) == "UNKNOWN"


# ── 4 — ROJO en F0: la cuarentena sobrevive al reinicio ─────────────────────


def test_cuarentena_sobrevive_al_reinicio(tmp_path):
    """El caso testigo real: epic-28/rf-028 lleva 11 dias atascado y el
    contador se resetea en cada arranque porque la cuarentena es un dict."""
    from services import output_watcher as ow

    pt_file = _artifact(tmp_path)
    razon = (
        "intake rechazo el artefacto: el archivo esta vacio o solo tiene espacios; "
        "el agente no llego a escribir el contenido."
    )
    ow._quarantine_pending_once(pt_file, razon, cause_code="INTAKE_EMPTY")

    antes = ow.quarantine_snapshot()[str(pt_file)]
    first_seen = antes["first_seen"]
    assert first_seen, "la entrada nace sin first_seen"

    _reset_quarantine(ow)  # ← reinicio del backend
    assert ow.quarantine_snapshot() == {}

    ow._rehydrate_quarantine(tmp_path / "outputs")

    despues = ow.quarantine_snapshot()
    assert str(pt_file) in despues, "la cuarentena no sobrevivio al reinicio"
    assert despues[str(pt_file)]["reason"] == razon
    assert despues[str(pt_file)]["cause_code"] == "INTAKE_EMPTY"
    assert despues[str(pt_file)]["first_seen"] == first_seen


# ── 5 — ROJO en F0: el sidecar NUNCA toca el artefacto ──────────────────────


def test_sidecar_no_toca_el_artefacto(tmp_path):
    from services import output_watcher as ow

    pt_file = _artifact(tmp_path, body='{"titulo": "algo"}')
    hash_antes = _sha256(pt_file)
    mtime_antes = pt_file.stat().st_mtime_ns

    ow._quarantine_pending_once(pt_file, "intake rechazo el artefacto: x",
                                cause_code="INTAKE_SCHEMA")

    # Sin esta assert el test seria un falso verde: hoy tampoco toca el
    # artefacto, simplemente porque no escribe nada en ningun lado.
    assert ow._sidecar_path(pt_file).exists(), "el sidecar no se escribio"
    assert _sha256(pt_file) == hash_antes
    assert pt_file.stat().st_mtime_ns == mtime_antes


# ── 6 — ROJO en F0, regresion despues: el glob no recoge el sidecar ─────────


def test_sidecar_no_es_recogido_por_el_glob(tmp_path):
    from services import output_watcher as ow

    pt_file = _artifact(tmp_path)
    epic_dir = pt_file.parent.parent
    ow._write_sidecar(pt_file, reason="vacio", cause_code="INTAKE_EMPTY",
                      mtime_ns=pt_file.stat().st_mtime_ns)
    assert ow._sidecar_path(pt_file).exists()

    encontrados = list(epic_dir.glob("*/" + ow.PENDING_TASK_FILENAME))
    assert encontrados == [pt_file], f"el glob recogio de mas: {encontrados}"


# ── 7 — ROJO en F0: occurrences incrementa, first_seen se preserva ──────────


def test_occurrences_incrementa_y_first_seen_se_preserva(tmp_path):
    from services import output_watcher as ow

    pt_file = _artifact(tmp_path)
    ow._quarantine_pending_once(pt_file, "razon estable", cause_code="INTAKE_EMPTY")
    primero = ow._read_sidecar(pt_file)
    assert primero["occurrences"] == 1

    _reset_quarantine(ow)  # ← reinicio: es lo que produjo los 25 relogueos
    ow._quarantine_pending_once(pt_file, "razon estable", cause_code="INTAKE_EMPTY")
    segundo = ow._read_sidecar(pt_file)

    assert segundo["occurrences"] == 2
    assert segundo["first_seen"] == primero["first_seen"]
    assert segundo["last_seen"] > primero["last_seen"]


# ── 8 — VERDE: invariante de la cuarentena, congelado ──────────────────────


def test_quarantine_snapshot_nunca_devuelve_reason_vacia(tmp_path):
    """Todo lo que entra por _quarantine_pending_once sale con razon util."""
    from services import output_watcher as ow
    from services.artifact_intake import validate_and_normalize

    ctx = {"valid_ado_ids": [28]}
    for i, raw in enumerate(("", "{", "[]", '{"foo": 1}')):
        pt_file = _artifact(tmp_path, name=f"rf-{i:03d}", body=raw)
        result = validate_and_normalize(
            raw=raw, kind="pending_task_json", ticket_context=ctx
        )
        assert result.ok is False
        ow._quarantine_pending_once(
            pt_file, "intake rechazo el artefacto: " + "; ".join(result.errors)
        )

    snap = ow.quarantine_snapshot()
    assert len(snap) == 4
    for path, entry in snap.items():
        assert entry["reason"].strip() != "", f"{path} quedo con razon vacia"


# ── F2 — nunca perder el original ───────────────────────────────────────────
#
# La reparacion automatica reescribe EL ARCHIVO DEL OPERADOR in place. Estos
# tests fijan que antes de hacerlo quede una copia cruda, y que si la copia no
# se puede escribir la reparacion se ABORTE (un artefacto en cuarentena con
# razon clara es mejor que un artefacto del agente destruido).

_PAYLOAD_VALIDO = {
    "title": "RF-028 filtros CP",
    "description_html": "<p>algo</p>",
    "epic_id": 28,
    "rf_id": "RF-028",
    "status": "pending",
    "generated_at": "2026-07-27T00:00:00Z",
    "generated_by": "test-plan256",
    "parent_link_type": "child",
    "plan_de_pruebas_path": "plan-de-pruebas.md",
}


def _artefacto_reparable(tmp_path: Path) -> tuple[Path, str]:
    """Artefacto que el intake REPARA (viene envuelto en un cerco de codigo):
    ok=True + repaired=True, que es la unica rama que reescribe el archivo."""
    crudo = "```json\n" + json.dumps(_PAYLOAD_VALIDO) + "\n```"
    return _artifact(tmp_path, body=crudo), crudo


def _correr_auto_create(ow, pt_file: Path, monkeypatch):
    """Corre el helper real de auto-create con el self-POST neutralizado.

    `requests.post` se reemplaza a nivel del MODULO requests (el helper hace
    `import requests as _req` adentro, asi que toma el parcheado): cero red,
    cero backend vivo, pero el codigo que se ejercita es el de produccion.
    """
    import requests

    llamadas: list = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "created": True}

        text = "{}"

    def _fake_post(url, **kwargs):
        llamadas.append((url, kwargs))
        return _Resp()

    monkeypatch.setenv("STACKY_TEST_ALLOW_WATCHER_SELF_POST", "1")
    monkeypatch.setattr(requests, "post", _fake_post)
    resumen = ow._auto_create_pending_tasks(epic_ado_id=28, pending_files=[pt_file])
    return resumen, llamadas


def test_reparacion_preserva_el_original(tmp_path, monkeypatch):
    from services import output_watcher as ow

    pt_file, crudo = _artefacto_reparable(tmp_path)
    _correr_auto_create(ow, pt_file, monkeypatch)

    orig = ow._original_backup_path(pt_file)
    assert orig.exists(), "la reparacion no dejo copia del original"
    assert orig.read_text(encoding="utf-8") == crudo, "el .orig no es el crudo del agente"
    # Y la reparacion efectivamente ocurrio (si no, el test seria vacio).
    assert pt_file.read_text(encoding="utf-8") != crudo


def test_reparacion_no_pisa_el_orig_en_el_segundo_pase(tmp_path, monkeypatch):
    from services import output_watcher as ow

    pt_file, crudo = _artefacto_reparable(tmp_path)
    _correr_auto_create(ow, pt_file, monkeypatch)
    orig = ow._original_backup_path(pt_file)
    assert orig.read_text(encoding="utf-8") == crudo

    # Segundo pase sobre el archivo YA reparado: el .orig debe seguir teniendo
    # el crudo, no la version normalizada.
    pt_file.write_text("```json\n" + json.dumps(_PAYLOAD_VALIDO) + "\n```", encoding="utf-8")
    _correr_auto_create(ow, pt_file, monkeypatch)
    assert orig.read_text(encoding="utf-8") == crudo


def test_reparacion_abortada_si_falla_el_orig(tmp_path, monkeypatch):
    from services import output_watcher as ow

    pt_file, crudo = _artefacto_reparable(tmp_path)
    hash_antes = _sha256(pt_file)
    orig = ow._original_backup_path(pt_file)

    real_write_text = Path.write_text

    def _write_text_que_falla_solo_el_orig(self, *args, **kwargs):
        if str(self) == str(orig):
            raise OSError("disco lleno (simulado)")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _write_text_que_falla_solo_el_orig)
    _correr_auto_create(ow, pt_file, monkeypatch)
    monkeypatch.undo()

    assert not orig.exists()
    assert _sha256(pt_file) == hash_antes, "se destruyo el artefacto del agente"
    assert pt_file.read_text(encoding="utf-8") == crudo

    snap = ow.quarantine_snapshot()
    assert str(pt_file) in snap, "la reparacion abortada no dejo el artefacto en cuarentena"
    assert snap[str(pt_file)]["cause_code"] == "ORIG_BACKUP_FAILED"
    assert snap[str(pt_file)]["reason"].strip() != ""


def test_orig_backup_failed_no_es_retryable(tmp_path):
    from services import output_watcher as ow

    pt_file = _artifact(tmp_path, body="{}")
    ow._quarantine_pending_once(pt_file, "reparacion abortada: no se pudo escribir la copia .orig",
                                cause_code="ORIG_BACKUP_FAILED")
    entrada = ow.quarantine_snapshot()[str(pt_file)]
    assert entrada["retryable"] is False

    otro = _artifact(tmp_path, name="rf-029", body="")
    ow._quarantine_pending_once(otro, "vacio", cause_code="INTAKE_EMPTY")
    assert ow.quarantine_snapshot()[str(otro)]["retryable"] is True

    assert ow._NON_RETRYABLE_CAUSES == frozenset({"ORIG_BACKUP_FAILED"})


def test_las_3_flags_en_off_dejan_el_comportamiento_de_hoy(tmp_path, monkeypatch):
    """Fallback declarado: con las 3 apagadas no queda un solo byte nuevo en la
    carpeta del operador y la cuarentena vuelve a ser exactamente la de hoy."""
    import config as cfg

    from services import output_watcher as ow

    for key in (
        "STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED",
        "STACKY_INTAKE_PRESERVE_ORIGINAL_ENABLED",
        "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED",
    ):
        monkeypatch.setattr(cfg.config, key, False)

    # 1) cuarentena: sin sidecar, con las claves historicas intactas.
    pt_file, crudo = _artefacto_reparable(tmp_path)
    _correr_auto_create(ow, pt_file, monkeypatch)
    assert not ow._sidecar_path(pt_file).exists(), "escribio el sidecar con la flag apagada"

    # 2) reparacion: sin copia .orig y el archivo reescrito, como hoy.
    assert not ow._original_backup_path(pt_file).exists(), "escribio el .orig con la flag apagada"
    assert pt_file.read_text(encoding="utf-8") != crudo, "no reparo: eso SI seria un cambio"

    vacio = _artifact(tmp_path, name="rf-vacio", body="")
    ow._quarantine_pending_once(vacio, "razon de siempre", cause_code="INTAKE_EMPTY")
    assert not ow._sidecar_path(vacio).exists()
    entrada = ow.quarantine_snapshot()[str(vacio)]
    assert entrada["reason"] == "razon de siempre"
    assert isinstance(entrada["mtime_ns"], int)

    # 3) rehidratacion: no lee disco.
    _reset_quarantine(ow)
    assert ow._rehydrate_quarantine(tmp_path / "outputs") == 0
    assert ow.quarantine_snapshot() == {}

    # 4) la carpeta del operador quedo sin archivos nuevos de este plan.
    sobrantes = [
        p.name for p in (tmp_path / "outputs").rglob("*")
        if p.name.endswith((".quarantine.json", ".orig"))
    ]
    assert sobrantes == [], f"archivos nuevos con las flags apagadas: {sobrantes}"


def test_glob_del_scan_ignora_los_orig(tmp_path):
    """Regresion barata: el v1 del plan daba por obligatorio filtrar los .orig
    del glob. Se midio y el riesgo no existe (el glob es literal), pero si
    alguien lo vuelve un comodin este test lo caza."""
    from services import output_watcher as ow

    pt_file = _artifact(tmp_path)
    epic_dir = pt_file.parent.parent
    ow._original_backup_path(pt_file).write_text("crudo", encoding="utf-8")
    ow._write_sidecar(pt_file, reason="x", cause_code="INTAKE_EMPTY",
                      mtime_ns=pt_file.stat().st_mtime_ns)

    encontrados = list(epic_dir.glob("*/" + ow.PENDING_TASK_FILENAME))
    assert encontrados == [pt_file], f"el glob recogio de mas: {encontrados}"
