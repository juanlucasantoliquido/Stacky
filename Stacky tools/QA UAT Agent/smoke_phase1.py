"""
smoke_phase1.py — Smoke test de Fase 1: Event Store, esquema, persistencia y contratos.

Valida:
  [ ] events.sqlite contiene eventos
  [ ] events.jsonl contiene eventos
  [ ] run_manifest.json existe
  [ ] run_state.json existe
  [ ] checkpoint existe
  [ ] artifact tiene sha256
  [ ] event_policy pasa
  [ ] data_contracts pasa
  [ ] no hay secretos sin redactar

Uso:
    python smoke_phase1.py
    python smoke_phase1.py --clean   # borrar directorio de smoke antes de correr
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

# ── Setup path ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

from event_schema import build_event, validate_event
from event_store import EventStore, EventStoreFactory
from forensic_event_logger import ForensicEventLogger, make_run_id
from run_manifest import RunManifest
from checkpoint_manager import CheckpointManager
from artifact_registry import ArtifactRegistry, compute_sha256_bytes
from event_policy import validate_event_policy
from data_contracts import validate_data_contracts
from redactor import redact_text, redact_dict, scan_for_unredacted_secrets

_SMOKE_TICKET_ID = 0
_SMOKE_PREFIX = "smoke"


def _print_check(label: str, ok: bool, detail: str = "") -> bool:
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {label}" + (f": {detail}" if detail else ""))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Fase 1 — QA UAT Agent")
    parser.add_argument("--clean", action="store_true", help="Borrar smoke dir antes de correr")
    args = parser.parse_args()

    print("\n=== SMOKE TEST FASE 1 — QA UAT Agent ===\n")

    # ── Directorio del smoke run ───────────────────────────────────────────────
    run_id = make_run_id(ticket_id=_SMOKE_TICKET_ID, prefix=_SMOKE_PREFIX)
    run_dir = _ROOT / "evidence" / str(_SMOKE_TICKET_ID) / run_id
    if args.clean and run_dir.exists():
        shutil.rmtree(run_dir)
        print(f"Directorio limpiado: {run_dir}\n")

    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run ID: {run_id}")
    print(f"Run Dir: {run_dir}\n")

    all_pass = True

    # ── 1. Redacción de secretos ───────────────────────────────────────────────
    print("── 1. Redacción de secretos ──────────────────────────────────")
    test_text = "AGENDA_WEB_USER=Pablo AGENDA_WEB_PASS=supersecret123 ADO_PAT=ghp_abc123xyz"
    redacted, fields = redact_text(test_text)
    ok1a = "supersecret123" not in redacted and "ghp_abc123xyz" not in redacted
    ok1b = "Pablo" in redacted  # usuario NO es secreto
    ok1c = "***REDACTED***" in redacted
    r = _print_check("Secretos redactados en texto libre", ok1a and ok1b and ok1c, f"fields={fields}")
    all_pass = all_pass and r
    print(f"    Texto redactado: {redacted[:80]}...")

    test_dict = {"username": "Pablo", "password": "secretpass", "url": "http://localhost"}
    redacted_d, r_fields, r_applied = redact_dict(test_dict)
    ok1d = redacted_d.get("password") == "***REDACTED***" and redacted_d.get("username") == "Pablo"
    r = _print_check("Secretos redactados en dict", ok1d, f"applied={r_applied}, fields={r_fields}")
    all_pass = all_pass and r

    # Verificar que no se detectan secretos en texto ya redactado
    warnings = scan_for_unredacted_secrets(redacted)
    ok1e = len(warnings) == 0
    r = _print_check("scan_for_unredacted_secrets en texto limpio", ok1e, f"warnings={warnings[:2]}")
    all_pass = all_pass and r
    print()

    # ── 2. Event schema ────────────────────────────────────────────────────────
    print("── 2. Event Schema ───────────────────────────────────────────")
    try:
        evt = build_event(
            run_id=run_id,
            ticket_id=_SMOKE_TICKET_ID,
            trace_id=f"trace-{run_id}",
            seq_run=1,
            source="pipeline",
            event_type="run.started",
            category="run_started",
            stage="run",
            action="run_started",
            status="started",
            level="info",
            message="Smoke run iniciado",
            payload={"mode": "smoke-test", "env": "test"},
        )
        errors = validate_event(evt)
        ok2a = len(errors) == 0
        r = _print_check("build_event + validate_event", ok2a, f"errors={errors}")
        all_pass = all_pass and r
        print(f"    event_id: {evt['event_id']}, seq_run: {evt['seq_run']}")
    except Exception as ex:
        _print_check("build_event", False, str(ex))
        all_pass = False
    print()

    # ── 3. EventStore (SQLite + JSONL) ─────────────────────────────────────────
    print("── 3. EventStore (SQLite + JSONL) ────────────────────────────")
    store = EventStoreFactory.get(run_dir)

    # Construir y escribir varios eventos
    event_defs = [
        ("run.started", "run_started", "run", "run_started", "started", "info", "Run smoke iniciado"),
        ("stage.started", "stage_started", "reader", "stage_started", "started", "info", "Stage reader iniciado"),
        ("decision.select_playbook", "decision", "reader", "select_playbook", "completed", "info", "Playbook seleccionado"),
        ("file.written", "file_written", "reader", "file_written", "completed", "info", "ticket.json escrito"),
        ("artifact.created", "artifact_created", "reader", "artifact_created", "completed", "info", "ticket.json registrado"),
        ("metric.duration", "metric", "reader", "metric_duration", "completed", "info", "Duración registrada"),
        ("stage.completed", "stage_completed", "reader", "stage_completed", "completed", "info", "Stage reader completado"),
        ("run.completed", "run_completed", "run", "run_completed", "completed", "info", "Run smoke completado"),
    ]

    written_event_ids = []
    for i, (etype, cat, stage, action, status, level, msg) in enumerate(event_defs, start=1):
        e = build_event(
            run_id=run_id,
            ticket_id=_SMOKE_TICKET_ID,
            trace_id=f"trace-{run_id}",
            seq_run=i,
            source="pipeline",
            event_type=etype,
            category=cat,
            stage=stage,
            action=action,
            status=status,
            level=level,
            message=msg,
            payload={"seq": i, "smoke": True},
        )
        persisted = store.write_event(e)
        if persisted:
            written_event_ids.append(e["event_id"])

    # Verificar SQLite
    db_path = run_dir / "events.sqlite"
    ok3a = db_path.exists()
    r = _print_check("events.sqlite creado", ok3a)
    all_pass = all_pass and r

    if ok3a:
        count = store.count_events(run_id)
        ok3b = count == len(event_defs)
        r = _print_check(f"events.sqlite contiene {len(event_defs)} eventos", ok3b, f"count={count}")
        all_pass = all_pass and r

        # Verificar consulta
        fetched = store.get_events(run_id, stage="reader")
        ok3c = len(fetched) > 0
        r = _print_check("get_events(stage='reader') devuelve resultados", ok3c, f"count={len(fetched)}")
        all_pass = all_pass and r

    # Verificar JSONL
    jsonl_path = run_dir / "events.jsonl"
    ok3d = jsonl_path.exists()
    r = _print_check("events.jsonl creado", ok3d)
    all_pass = all_pass and r

    if ok3d:
        lines = [l for l in jsonl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        ok3e = len(lines) == len(event_defs)
        r = _print_check(f"events.jsonl contiene {len(event_defs)} líneas", ok3e, f"lines={len(lines)}")
        all_pass = all_pass and r

        # Verificar que cada línea es JSON válido
        parse_errors = 0
        for line in lines:
            try:
                json.loads(line)
            except Exception:
                parse_errors += 1
        ok3f = parse_errors == 0
        r = _print_check("Todas las líneas JSONL son JSON válido", ok3f, f"parse_errors={parse_errors}")
        all_pass = all_pass and r
    print()

    # ── 4. RunManifest ─────────────────────────────────────────────────────────
    print("── 4. RunManifest ────────────────────────────────────────────")
    manifest_mgr = RunManifest(run_id=run_id, ticket_id=_SMOKE_TICKET_ID, run_dir=run_dir)
    manifest = manifest_mgr.create(mode="dry-run", headed=False, operator="smoke_test")

    ok4a = (run_dir / "run_manifest.json").exists()
    r = _print_check("run_manifest.json creado", ok4a)
    all_pass = all_pass and r

    ok4b = (run_dir / "run_state.json").exists()
    r = _print_check("run_state.json creado", ok4b)
    all_pass = all_pass and r

    if ok4a:
        required = {"run_id", "ticket_id", "trace_id", "started_at", "schema_version", "mode"}
        loaded = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        missing = required - set(loaded.keys())
        ok4c = len(missing) == 0
        r = _print_check("run_manifest.json tiene campos obligatorios", ok4c, f"missing={missing}")
        all_pass = all_pass and r

    # Verificar secretos en manifest
    if ok4a:
        manifest_text = (run_dir / "run_manifest.json").read_text(encoding="utf-8")
        secret_w = scan_for_unredacted_secrets(manifest_text)
        ok4d = len(secret_w) == 0
        r = _print_check("run_manifest.json sin secretos", ok4d, f"warnings={secret_w[:2]}")
        all_pass = all_pass and r

    # update_state
    manifest_mgr.update_state(status="running", current_stage="reader")
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    ok4e = state.get("current_stage") == "reader" and state.get("status") == "running"
    r = _print_check("update_state actualiza run_state.json", ok4e)
    all_pass = all_pass and r
    print()

    # ── 5. CheckpointManager ───────────────────────────────────────────────────
    print("── 5. CheckpointManager ──────────────────────────────────────")
    cp_mgr = CheckpointManager(run_id=run_id, run_dir=run_dir)
    cp_path = cp_mgr.mark_completed("reader", payload={"scenarios": 3}, store=store)

    ok5a = cp_path.exists()
    r = _print_check("Checkpoint 'reader.completed' creado", ok5a, str(cp_path.name))
    all_pass = all_pass and r

    ok5b = cp_mgr.is_completed("reader")
    r = _print_check("is_completed('reader') == True", ok5b)
    all_pass = all_pass and r

    ok5c = cp_mgr.last_completed_stage() == "reader"
    r = _print_check("last_completed_stage() == 'reader'", ok5c)
    all_pass = all_pass and r

    cp_mgr.mark_blocked("compiler", payload={"reason": "MISSING_PLAYBOOK"}, store=store)
    summary = cp_mgr.summary()
    ok5d = summary["completed"] == 1 and summary["blocked"] == 1
    r = _print_check("summary() correcto", ok5d, str(summary))
    all_pass = all_pass and r
    print()

    # ── 6. ArtifactRegistry ───────────────────────────────────────────────────
    print("── 6. ArtifactRegistry ───────────────────────────────────────")
    art_registry = ArtifactRegistry(run_id=run_id, run_dir=run_dir, store=store)

    # Crear un artifact de ejemplo
    ticket_data = {"id": 0, "title": "Smoke test ticket", "scenarios": []}
    art = art_registry.register_json(
        data=ticket_data,
        dest_path=run_dir / "artifacts" / "ticket.json",
        artifact_type="ticket",
        created_by_event_id=written_event_ids[3] if len(written_event_ids) > 3 else None,
        ticket_id=_SMOKE_TICKET_ID,
    )

    ok6a = art.get("sha256") is not None
    r = _print_check("Artifact tiene sha256", ok6a, art.get("sha256", "")[:16] + "...")
    all_pass = all_pass and r

    ok6b = art.get("artifact_id", "").startswith("art_")
    r = _print_check("Artifact tiene artifact_id válido", ok6b, art.get("artifact_id"))
    all_pass = all_pass and r

    ok6c = (run_dir / "artifacts" / "_registry.json").exists()
    r = _print_check("_registry.json creado", ok6c)
    all_pass = all_pass and r

    missing_files = art_registry.validate_all_exist()
    ok6d = len(missing_files) == 0
    r = _print_check("Todos los artifacts existen físicamente", ok6d, f"missing={missing_files}")
    all_pass = all_pass and r

    missing_sha = art_registry.validate_all_have_sha256()
    ok6e = len(missing_sha) == 0
    r = _print_check("Todos los artifacts tienen sha256", ok6e, f"missing_sha={missing_sha}")
    all_pass = all_pass and r
    print()

    # ── 7. ForensicEventLogger ─────────────────────────────────────────────────
    print("── 7. ForensicEventLogger ────────────────────────────────────")
    run_id_2 = make_run_id(_SMOKE_TICKET_ID, "smoke2")
    run_dir_2 = _ROOT / "evidence" / str(_SMOKE_TICKET_ID) / run_id_2

    with ForensicEventLogger(run_id=run_id_2, ticket_id=_SMOKE_TICKET_ID, run_dir=run_dir_2) as flog:
        e1 = flog.emit_run_started({"mode": "smoke"})
        e2 = flog.emit_stage_started("reader")
        e3 = flog.emit_decision("reader", "select_playbook", "Playbook seleccionado", {"playbook": "test"})
        e4 = flog.emit_file_written("reader", "ticket.json", size_bytes=120)
        e5 = flog.emit_stage_completed("reader", {"ok": True})
        e6 = flog.emit_run_completed({"verdict": "PASS"})

    ok7a = all([e1, e2, e3, e4, e5, e6])
    r = _print_check("ForensicEventLogger emite 6 eventos con IDs válidos", ok7a, f"ids: {[e1[:10] if e1 else None, '...']}")
    all_pass = all_pass and r

    store2 = EventStoreFactory.get(run_dir_2)
    cnt2 = store2.count_events(run_id_2)
    ok7b = cnt2 == 6
    r = _print_check(f"EventStore2 contiene 6 eventos", ok7b, f"count={cnt2}")
    all_pass = all_pass and r
    print()

    # ── 8. EventPolicy ─────────────────────────────────────────────────────────
    print("── 8. EventPolicy ────────────────────────────────────────────")
    # Crear run_manifest para run_dir_2 antes de validar
    RunManifest(run_id=run_id_2, ticket_id=_SMOKE_TICKET_ID, run_dir=run_dir_2).create(mode="smoke")
    policy_result = validate_event_policy(run_dir_2)

    ok8a = policy_result.get("ok") is True
    r = _print_check("event_policy PASS para ForensicEventLogger run", ok8a,
                     f"verdict={policy_result.get('verdict')}, violations={policy_result.get('violations')[:2]}")
    all_pass = all_pass and r
    print(f"    checks: {policy_result.get('checks')}")
    print()

    # ── 9. DataContracts ───────────────────────────────────────────────────────
    print("── 9. DataContracts ──────────────────────────────────────────")
    dc_result = validate_data_contracts(run_dir_2)

    ok9a = dc_result.get("ok") is True
    r = _print_check("data_contracts PASS para ForensicEventLogger run", ok9a,
                     f"verdict={dc_result.get('verdict')}, violations={dc_result.get('violations')[:2]}")
    all_pass = all_pass and r
    print(f"    contracts: {dc_result.get('contracts')}")
    print()

    # ── Ejemplo de events.jsonl ────────────────────────────────────────────────
    print("── Ejemplo events.jsonl (ForensicEventLogger run) ───────────")
    jsonl2 = run_dir_2 / "events.jsonl"
    if jsonl2.exists():
        lines = jsonl2.read_text(encoding="utf-8").splitlines()
        if lines:
            sample = json.loads(lines[0])
            print(json.dumps(sample, ensure_ascii=False, indent=2)[:600])
    print()

    # ── Resumen final ──────────────────────────────────────────────────────────
    print("=" * 55)
    if all_pass:
        print("RESULTADO: FASE 1 OK — Todos los checks pasaron.")
    else:
        print("RESULTADO: FASE 1 FAIL — Revisar checks fallidos arriba.")
    print(f"Run dir principal: {run_dir}")
    print(f"Run dir logger:    {run_dir_2}")
    print("=" * 55)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
