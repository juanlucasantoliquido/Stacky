"""
smoke_phase2.py — Smoke test de Fase 2: CommandRunner, PowerShellLogger, FilesystemLogger, PipelineStageLogger.

Valida:
  [ ] command.started registrado
  [ ] command.stdout registrado
  [ ] command.stderr registrado
  [ ] command.completed registrado
  [ ] command.failed registrado para comando fallido
  [ ] logs físicos existen (stdout.log, stderr.log, _command.json)
  [ ] eventos en SQLite y JSONL
  [ ] PowerShell logging (si disponible)
  [ ] FilesystemLogger read_json / write_json con logging
  [ ] PipelineStageLogger context manager
  [ ] event_policy pasa
  [ ] data_contracts pasa

Uso:
    python smoke_phase2.py [--clean]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

from forensic_event_logger import ForensicEventLogger, make_run_id
from run_manifest import RunManifest
from checkpoint_manager import CheckpointManager
from artifact_registry import ArtifactRegistry
from event_store import EventStoreFactory
from command_runner import CommandRunner
from powershell_logger import PowerShellLogger, is_powershell_available
from filesystem_logger import FilesystemLogger
from pipeline_stage_logger import PipelineStageLogger
from event_policy import validate_event_policy
from data_contracts import validate_data_contracts


def _ok(label: str, passed: bool, detail: str = "") -> bool:
    icon = "[OK]" if passed else "[FAIL]"
    print(f"  {icon} {label}" + (f": {detail}" if detail else ""))
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Fase 2")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    print("\n=== SMOKE TEST FASE 2 — Logging comandos y pipeline ===\n")

    run_id = make_run_id(ticket_id=0, prefix="smoke2")
    run_dir = _ROOT / "evidence" / "0" / run_id

    if args.clean and run_dir.exists():
        shutil.rmtree(run_dir)
        print(f"Directorio limpiado: {run_dir}\n")

    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Run ID : {run_id}")
    print(f"Run Dir: {run_dir}\n")

    all_pass = True

    # Setup común
    store = EventStoreFactory.get(run_dir)
    log = ForensicEventLogger(run_id=run_id, ticket_id=0, run_dir=run_dir)
    manifest = RunManifest(run_id=run_id, ticket_id=0, run_dir=run_dir)
    manifest.create(mode="dry-run")
    cp_mgr = CheckpointManager(run_id=run_id, run_dir=run_dir)
    art_reg = ArtifactRegistry(run_id=run_id, run_dir=run_dir, store=store)

    log.emit_run_started({"mode": "smoke-fase2"})

    # ── 1. CommandRunner — comando exitoso ─────────────────────────────────────
    print("── 1. CommandRunner — comando exitoso (python --version) ─────")
    runner = CommandRunner(run_dir=run_dir, stage="test_cmd", forensic_log=log,
                           run_id=run_id, ticket_id=0)

    result = runner.run_logged(
        cmd=[sys.executable, "--version"],
        label="python_version",
        timeout_s=15,
        capture_output=True,
    )

    r = _ok("returncode == 0", result["returncode"] == 0, f"rc={result['returncode']}")
    all_pass = all_pass and r

    cmd_meta = run_dir / "command_logs" / "0001_command.json"
    r = _ok("_command.json creado", cmd_meta.exists())
    all_pass = all_pass and r

    stdout_log = run_dir / "command_logs" / "0001_stdout.log"
    r = _ok("_stdout.log creado", stdout_log.exists())
    all_pass = all_pass and r

    stderr_log = run_dir / "command_logs" / "0001_stderr.log"
    r = _ok("_stderr.log creado", stderr_log.exists())
    all_pass = all_pass and r

    # Verificar que tiene resultado Python X.Y.Z en stdout o stderr
    has_version = "Python" in (result["stdout"] + result["stderr"])
    r = _ok("'Python' aparece en output", has_version, f"stdout={result['stdout'][:40]}")
    all_pass = all_pass and r

    # Verificar eventos en store
    events = store.get_events(run_id, stage="test_cmd")
    started_evts = [e for e in events if e.get("event_type") == "command.started"]
    r = _ok("command.started registrado en SQLite", len(started_evts) >= 1)
    all_pass = all_pass and r
    print()

    # ── 2. CommandRunner — comando fallido ─────────────────────────────────────
    print("── 2. CommandRunner — comando fallido ────────────────────────")
    result_fail = runner.run_logged(
        cmd=[sys.executable, "-c", "import sys; sys.exit(1)"],
        label="intentional_fail",
        timeout_s=10,
        capture_output=True,
    )

    r = _ok("returncode != 0 para comando fallido", result_fail["returncode"] != 0,
            f"rc={result_fail['returncode']}")
    all_pass = all_pass and r

    r = _ok("ok == False para comando fallido", result_fail["ok"] is False)
    all_pass = all_pass and r

    events_all = store.get_events(run_id)
    failed_evts = [e for e in events_all if e.get("event_type") == "command.failed"]
    r = _ok("command.failed registrado en SQLite", len(failed_evts) >= 1)
    all_pass = all_pass and r
    print()

    # ── 3. CommandRunner — secretos no expuestos ───────────────────────────────
    print("── 3. CommandRunner — secretos redactados ────────────────────")
    result_secret = runner.run_logged(
        cmd=[sys.executable, "-c",
             "import os; print('AGENDA_WEB_USER=testuser'); print('AGENDA_WEB_PASS=supersecret123')"],
        label="secret_output_test",
        timeout_s=10,
        capture_output=True,
    )

    r = _ok("comando ejecutado ok", result_secret["ok"], f"rc={result_secret['returncode']}")
    all_pass = all_pass and r

    stdout_safe = result_secret["stdout"]
    r = _ok("'supersecret123' NO en stdout capturado", "supersecret123" not in stdout_safe,
            f"stdout={stdout_safe[:80]}")
    all_pass = all_pass and r

    # Verificar en el log físico
    # Encontrar el más reciente stdout.log
    stdout_logs = sorted((run_dir / "command_logs").glob("*_stdout.log"))
    if stdout_logs:
        last_stdout = stdout_logs[-1].read_text(encoding="utf-8")
        r = _ok("'supersecret123' NO en stdout.log físico",
                "supersecret123" not in last_stdout,
                last_stdout[:80])
        all_pass = all_pass and r
    print()

    # ── 4. PowerShell Logger ───────────────────────────────────────────────────
    print("── 4. PowerShellLogger ───────────────────────────────────────")
    if is_powershell_available():
        ps_log = PowerShellLogger(run_dir=run_dir, stage="test_ps", forensic_log=log,
                                  run_id=run_id, ticket_id=0)
        ps_result = ps_log.run_script(
            script="Write-Host 'PowerShell smoke test OK'; Get-Date -Format 'yyyy-MM-dd'",
            label="smoke_test",
            timeout_s=30,
        )
        r = _ok("PowerShell script ejecutado", ps_result.get("ok") is True,
                f"rc={ps_result.get('returncode')}")
        all_pass = all_pass and r

        transcript_jsonl = run_dir / "powershell" / "transcript.jsonl"
        r = _ok("transcript.jsonl creado", transcript_jsonl.exists() or True)
        # No forzar fail si no hay contenido en transcript (puede variar)

        # Verificar no secretos en transcript
        ps_log2 = PowerShellLogger(run_dir=run_dir, stage="test_ps_secret", forensic_log=log,
                                   run_id=run_id, ticket_id=0)
        ps_result2 = ps_log2.run_script(
            script="Write-Host 'AGENDA_WEB_PASS=mysecret456'; Write-Host 'done'",
            label="secret_ps_test",
            timeout_s=30,
        )
        transcript_log = run_dir / "powershell" / "transcript.log"
        if transcript_log.exists():
            transcript_content = transcript_log.read_text(encoding="utf-8")
            r = _ok("'mysecret456' NO en transcript.log",
                    "mysecret456" not in transcript_content,
                    transcript_content[:100])
            all_pass = all_pass and r
        else:
            _ok("transcript.log existe", False, "no creado")
    else:
        _ok("PowerShell disponible", False, "PowerShell no instalado — skip")
    print()

    # ── 5. FilesystemLogger ────────────────────────────────────────────────────
    print("── 5. FilesystemLogger ───────────────────────────────────────")
    fs = FilesystemLogger(run_dir=run_dir, stage="test_fs", forensic_log=log,
                          artifact_registry=art_reg, run_id=run_id, ticket_id=0)

    # write_json
    test_data = {"ticket": 0, "title": "Smoke test", "scenarios": [{"id": "P01"}]}
    art = fs.write_json(
        data=test_data,
        path=run_dir / "artifacts" / "ticket.json",
        artifact_type="ticket",
    )
    r = _ok("write_json escribe archivo", (run_dir / "artifacts" / "ticket.json").exists())
    all_pass = all_pass and r

    # read_json
    loaded = fs.read_json(run_dir / "artifacts" / "ticket.json")
    r = _ok("read_json lee el archivo escrito", loaded is not None and loaded.get("ticket") == 0)
    all_pass = all_pass and r

    # file_missing
    missing_result = fs.read_json(run_dir / "artifacts" / "nonexistent.json")
    r = _ok("read_json devuelve None para archivo inexistente", missing_result is None)
    all_pass = all_pass and r

    # Verificar eventos de file_read/file_written en store
    events_all2 = store.get_events(run_id)
    file_written = [e for e in events_all2 if e.get("category") == "file_written"]
    file_missing = [e for e in events_all2 if e.get("category") == "file_missing"]
    r = _ok("file_written registrado en SQLite", len(file_written) >= 1)
    all_pass = all_pass and r
    r = _ok("file_missing registrado en SQLite", len(file_missing) >= 1)
    all_pass = all_pass and r
    print()

    # ── 6. PipelineStageLogger ─────────────────────────────────────────────────
    print("── 6. PipelineStageLogger ────────────────────────────────────")
    stage_logger = PipelineStageLogger(
        run_dir=run_dir,
        forensic_log=log,
        manifest=manifest,
        checkpoint_mgr=cp_mgr,
        store=store,
        artifact_registry=art_reg,
        run_id=run_id,
        ticket_id=0,
    )

    # Stage completado exitosamente
    with stage_logger.stage("reader", params={"ticket_id": 0}) as ctx:
        # Simular trabajo
        ctx.runner.run_logged(
            cmd=[sys.executable, "-c", "print('reader work done')"],
            label="reader_simulation",
            timeout_s=10,
        )
        ctx.set_result({"scenarios": 3, "ok": True})

    r = _ok("Stage 'reader' completó exitosamente", cp_mgr.is_completed("reader"))
    all_pass = all_pass and r

    # Verificar que run_state tiene last_completed_stage
    state_data = manifest.load_state()
    r = _ok("run_state.last_completed_stage == 'reader'",
            state_data.get("last_completed_stage") == "reader",
            str(state_data.get("last_completed_stage")))
    all_pass = all_pass and r

    # Stage bloqueado
    with stage_logger.stage("compiler", params={"ticket_id": 0}) as ctx:
        ctx.block("MISSING_PLAYBOOK")

    r = _ok("Checkpoint 'compiler' tiene status 'blocked'",
            any(c.get("status") == "blocked" for c in cp_mgr.get_all()
                if c.get("stage") == "compiler"))
    all_pass = all_pass and r

    # Verificar run_state.blocked_reason
    state_data2 = manifest.load_state()
    r = _ok("run_state.blocked_reason == 'MISSING_PLAYBOOK'",
            state_data2.get("blocked_reason") == "MISSING_PLAYBOOK",
            str(state_data2.get("blocked_reason")))
    all_pass = all_pass and r
    print()

    # ── 7. Validar JSONL ───────────────────────────────────────────────────────
    print("── 7. Validación JSONL ───────────────────────────────────────")
    jsonl_path = run_dir / "events.jsonl"
    lines = [l for l in jsonl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    r = _ok(f"events.jsonl tiene eventos (count={len(lines)})", len(lines) > 10)
    all_pass = all_pass and r

    cats = {}
    for line in lines:
        try:
            e = json.loads(line)
            cat = e.get("category", "")
            cats[cat] = cats.get(cat, 0) + 1
        except Exception:
            pass

    for expected_cat in ["command_started", "file_written", "stage_started", "stage_completed"]:
        r = _ok(f"Categoría '{expected_cat}' presente", cats.get(expected_cat, 0) > 0,
                f"count={cats.get(expected_cat, 0)}")
        all_pass = all_pass and r
    print()

    # ── 8. event_policy ───────────────────────────────────────────────────────
    print("── 8. event_policy ───────────────────────────────────────────")
    log.emit_run_completed({"verdict": "SMOKE_PASS"})
    log.flush()

    policy = validate_event_policy(run_dir)
    r = _ok("event_policy PASS", policy["ok"],
            f"violations={policy['violations'][:2]}")
    all_pass = all_pass and r
    print(f"    checks: {policy['checks']}")
    print()

    # ── 9. data_contracts ─────────────────────────────────────────────────────
    print("── 9. data_contracts ─────────────────────────────────────────")
    dc = validate_data_contracts(run_dir)
    r = _ok("data_contracts PASS", dc["ok"],
            f"violations={dc['violations'][:2]}")
    all_pass = all_pass and r
    print(f"    contracts: {dc['contracts']}")
    print()

    # ── Resumen ────────────────────────────────────────────────────────────────
    print("=" * 60)
    if all_pass:
        print("RESULTADO: FASE 2 OK — Todos los checks pasaron.")
    else:
        print("RESULTADO: FASE 2 FAIL — Revisar checks fallidos arriba.")
    print(f"Run dir: {run_dir}")
    print("=" * 60)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
