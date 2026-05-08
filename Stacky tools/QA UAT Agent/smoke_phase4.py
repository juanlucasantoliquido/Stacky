"""
smoke_phase4.py — Tests de validacion para Fase 4 (Human Unlock, learning, metrics, analytics, replay).

Valida:
  1.  BlockerRegistry: register, resolve, skip, pending, summary
  2.  BlockerRegistry: idempotencia (registrar mismo blocker_id dos veces)
  3.  HumanUnlock: block/resolve/skip con mock ForensicEventLogger
  4.  HumanUnlock: all_resolved() correcto
  5.  HumanUnlock: resolve_from_cli() sin ForensicEventLogger
  6.  LearningStore: add_candidate, approve, reject
  7.  LearningStore: idempotencia (mismo titulo + run_id)
  8.  LearningStore: get_approved por categoria
  9.  LearningStore: record_application
  10. LearningStore: stats()
  11. LearningCandidateGenerator: detecta selector_fix
  12. LearningCandidateGenerator: detecta blocker_resolved
  13. LearningCandidateGenerator: detecta timeout_hint
  14. MetricsCollector: collect_run_metrics devuelve estructura correcta
  15. MetricsCollector: persist + load_all round-trip
  16. MetricsCollector: load_since filtra por fecha
  17. AnalyticsBuilder: pass_rate con datos de prueba
  18. AnalyticsBuilder: full_report no crashea con 0 datos
  19. KPIBuilder: build_kpis con 0 datos da KPIs con status correcto
  20. KPIBuilder: build_kpis con datos reales calcula correctamente
  21. ObservabilityValidator: valida run_dir vacio con score bajo
  22. ObservabilityValidator: run con run_manifest valido pasa ese check
  23. ReplayRun: replay de run_dir vacio devuelve estructura correcta
  24. ReplayRun: replay con events.jsonl devuelve timeline
  25. CLI cmd_analytics_report importa y ejecuta sin crash
  26. CLI cmd_replay_run con run_dir inexistente devuelve error
  27. CLI cmd_validate_observability con evidence vacia devuelve error
  28. CLI cmd_list_blockers con run vacio devuelve lista vacia
  29. CLI cmd_resolve_blocker resuelve correctamente
  30. qa_uat_pipeline.py importa sin errores (CLI integracion)
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

PASS_STR = "PASS"
FAIL_STR = "FAIL"
_results = []


def chk(name, cond, detail=""):
    status = PASS_STR if cond else FAIL_STR
    _results.append({"name": name, "ok": cond, "detail": detail})
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    return cond


def run_smoke_phase4():
    print("\n" + "=" * 60)
    print("SMOKE -- Fase 4: Human Unlock, Learning, Metrics, Analytics, Replay")
    print("=" * 60 + "\n")

    # ── 1-2: BlockerRegistry ─────────────────────────────────────────────────
    from blocker_registry import BlockerRegistry

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "uat-70-test"
        run_dir.mkdir()
        reg = BlockerRegistry("uat-70-test", run_dir)

        bid1 = reg.register("runner", "session_expired", "Sesion expirada, reintentar?", options=["si", "no"])
        bid2 = reg.register("compiler", "missing_field", "Falta campo X?")

        chk("1. BlockerRegistry.register() crea blocker",
            len(reg.get_pending()) == 2, f"pending={len(reg.get_pending())}")

        ok_resolve = reg.resolve(bid1, "si")
        chk("1b. resolve() devuelve True", ok_resolve)
        chk("1c. blocker resuelto no aparece en pending",
            len(reg.get_pending()) == 1, f"pending={len(reg.get_pending())}")

        ok_skip = reg.skip(bid2, skipped_by="test_op")
        chk("1d. skip() funciona", ok_skip)

        summary = reg.summary()
        chk("1e. summary() correcto",
            summary["total"] == 2 and summary["resolved"] == 1 and summary["skipped"] == 1,
            str(summary))
        chk("1f. all_resolved() True", reg.all_resolved())

        # Idempotencia: registrar mismo blocker_id
        reg2 = BlockerRegistry("uat-70-test", run_dir)
        bid_idem = reg2.register("runner", "r", "q", blocker_id=bid1)
        chk("2. BlockerRegistry idempotencia (mismo blocker_id)",
            bid_idem == bid1, f"bid_idem={bid_idem}")

    # ── 3-5: HumanUnlock ─────────────────────────────────────────────────────
    from human_unlock import HumanUnlock

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "uat-70-hu"
        run_dir.mkdir()

        mock_log = MagicMock()
        mock_log.emit.return_value = "evt-001"

        hu = HumanUnlock("uat-70-hu", run_dir, forensic_log=mock_log)
        bid = hu.block("runner", "session_expired", "Reintentar?", options=["si", "no"])

        chk("3. HumanUnlock.block() registra blocker y emite evento",
            bid.startswith("blk-") and mock_log.emit.called)

        ok_res = hu.resolve(bid, "si")
        chk("3b. HumanUnlock.resolve() OK", ok_res)
        chk("3c. emit() llamado al resolver", mock_log.emit.call_count == 2)

        chk("4. all_resolved() True despues de resolver", hu.all_resolved())

        summary = hu.summary()
        chk("4b. summary() tiene claves correctas",
            all(k in summary for k in ["total", "pending", "resolved", "all_resolved"]))

    # resolve_from_cli
    with tempfile.TemporaryDirectory() as td:
        run_dir2 = Path(td) / "uat-70-cli"
        run_dir2.mkdir()
        hu2 = HumanUnlock("uat-70-cli", run_dir2)
        bid_cli = hu2.block("runner", "test", "q?", emit_event=False)

        result = HumanUnlock.resolve_from_cli(
            run_dir2, "uat-70-cli", bid_cli, "respuesta_test"
        )
        chk("5. resolve_from_cli() funciona",
            result["ok"] and result["remaining_pending"] == 0, str(result))

    # ── 6-10: LearningStore ───────────────────────────────────────────────────
    from learning_store import LearningStore

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_learning.sqlite"
        store = LearningStore(db_path=db_path)

        lid1 = store.add_candidate(
            run_id="uat-70-test", ticket_id=70,
            category="selector_fix", title="Selector #btn1 no funciona",
            description="Usar texto 'Guardar' en lugar de #btn1",
        )
        chk("6. LearningStore.add_candidate() devuelve learning_id",
            lid1.startswith("lrn-"), f"lid={lid1}")

        ok_approve = store.approve(lid1, reviewed_by="test_op")
        chk("6b. approve() devuelve True", ok_approve)

        approved = store.get_approved()
        chk("6c. get_approved() contiene el learning aprobado",
            any(l["learning_id"] == lid1 for l in approved))

        lid2 = store.add_candidate(
            run_id="uat-70-test2", ticket_id=70,
            category="timeout_fix", title="Timeout en click",
            description="Aumentar timeout",
        )
        ok_reject = store.reject(lid2, reviewed_by="test_op", rejection_reason="no aplica")
        chk("6d. reject() devuelve True", ok_reject)
        rejected = store.get_candidates(status="rejected")
        chk("6e. get_candidates(rejected) contiene el rechazado",
            any(l["learning_id"] == lid2 for l in rejected))

        # Idempotencia
        lid_idem = store.add_candidate(
            run_id="uat-70-test", ticket_id=70,
            category="selector_fix", title="Selector #btn1 no funciona",
            description="desc diferente",
        )
        chk("7. LearningStore idempotencia (mismo titulo + run_id)",
            lid_idem == lid1, f"lid_idem={lid_idem}, lid1={lid1}")

        # get_approved por categoria
        approved_sel = store.get_approved(category="selector_fix")
        chk("8. get_approved(category=selector_fix) filtra correctamente",
            all(l["category"] == "selector_fix" for l in approved_sel))

        # record_application
        ok_apply = store.record_application(lid1, "uat-70-test3", 70, applied_by="system",
                                            context={"step": 3}, outcome={"status": "ok"})
        chk("9. record_application() devuelve True", ok_apply)

        stats = store.stats()
        chk("10. stats() tiene claves correctas",
            all(k in stats for k in ["candidates", "approved", "rejected", "total_applications"]),
            str(stats))

        store.close()

    # ── 11-13: LearningCandidateGenerator ────────────────────────────────────
    from learning_candidate_generator import LearningCandidateGenerator

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "uat-70-lcg"
        run_dir.mkdir()
        db_path = Path(td) / "test_lcg.sqlite"
        store = LearningStore(db_path=db_path)

        # Crear events.jsonl con patron selector_fix
        events_path = run_dir / "events.jsonl"
        events = [
            {"seq_run": 1, "event_id": "e1", "event_type": "playwright.click.failed",
             "category": "page_click", "action": "click", "status": "failed",
             "stage": "runner", "source": "playwright",
             "payload": {"selector": "#btn_old"}, "error": "timeout exceeded", "message": "click failed"},
            {"seq_run": 2, "event_id": "e2", "event_type": "playwright.click.completed",
             "category": "page_click", "action": "click", "status": "completed",
             "stage": "runner", "source": "playwright",
             "payload": {"selector": "#btn_new"}, "error": None, "message": "click ok"},
        ]
        with open(events_path, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        gen = LearningCandidateGenerator(
            run_id="uat-70-lcg", ticket_id=70,
            events_jsonl=events_path, store=store,
        )
        candidates = gen.generate()
        chk("11. LearningCandidateGenerator detecta selector_fix",
            any(c.get("category") == "selector_fix" for c in candidates),
            f"candidates={candidates}")

        # Blocker resuelto
        db_path2 = Path(td) / "test_lcg2.sqlite"
        store2 = LearningStore(db_path=db_path2)
        blockers_path = run_dir / "blockers.json"
        blockers = [
            {"blocker_id": "blk-001", "stage": "runner", "reason": "session_expired",
             "question": "Reintentar?", "status": "resolved", "answer": "si",
             "answered_by": "operator"},
        ]
        blockers_path.write_text(json.dumps(blockers))
        gen2 = LearningCandidateGenerator(
            run_id="uat-70-lcg", ticket_id=70,
            events_jsonl=events_path, blockers_json=blockers_path, store=store2,
        )
        cands2 = gen2.generate()
        chk("12. LearningCandidateGenerator detecta blocker_resolved",
            any(c.get("category") == "other" or "Blocker" in c.get("title", "") for c in cands2),
            f"candidates={cands2}")

        # Timeout hint
        db_path3 = Path(td) / "test_lcg3.sqlite"
        store3 = LearningStore(db_path=db_path3)
        timeout_events_path = run_dir / "events_timeout.jsonl"
        timeout_events = [
            {"seq_run": 1, "event_id": "e3", "event_type": "playwright.click.failed",
             "category": "page_click", "action": "click", "status": "failed",
             "stage": "runner", "source": "playwright",
             "payload": {"selector": "#btnX", "error": "Timeout 15000ms exceeded"},
             "error": "Timeout 15000ms exceeded", "message": "timeout"},
        ]
        with open(timeout_events_path, "w") as f:
            for e in timeout_events:
                f.write(json.dumps(e) + "\n")
        gen3 = LearningCandidateGenerator(
            run_id="uat-70-lcg-t", ticket_id=70,
            events_jsonl=timeout_events_path, store=store3,
        )
        cands3 = gen3.generate()
        chk("13. LearningCandidateGenerator detecta timeout_hint",
            any(c.get("category") == "timeout_fix" for c in cands3),
            f"candidates={cands3}")
        store.close()
        store2.close()
        store3.close()

    # ── 14-16: MetricsCollector ───────────────────────────────────────────────
    from metrics_collector import MetricsCollector

    with tempfile.TemporaryDirectory() as td:
        evidence_dir = Path(td) / "evidence" / "70"
        run_id = "uat-70-mc-test"
        run_dir = evidence_dir / run_id
        run_dir.mkdir(parents=True)
        metrics_path = Path(td) / "metrics.jsonl"

        # Crear run_manifest.json y run_state.json minimos
        (run_dir / "run_manifest.json").write_text(json.dumps({
            "run_id": run_id, "ticket_id": "70", "started_at": "2026-05-08T12:00:00.000Z",
            "tool_version": "1.0.0", "schema_version": "1.0", "mode": "dry-run", "headed": False,
        }))
        (run_dir / "run_state.json").write_text(json.dumps({
            "status": "completed", "verdict": "PASS", "duration_ms": 5000,
        }))

        mc = MetricsCollector(evidence_dir=evidence_dir, metrics_path=metrics_path)
        metrics = mc.collect_run_metrics(run_id=run_id, ticket_id=70)

        chk("14. MetricsCollector.collect_run_metrics() devuelve estructura",
            all(k in metrics for k in ["run_id", "ticket_id", "run", "events", "playwright", "stages"]),
            str(list(metrics.keys())))
        chk("14b. run.verdict = PASS", metrics["run"].get("verdict") == "PASS",
            f"verdict={metrics['run'].get('verdict')}")

        ok_persist = mc.persist(metrics)
        chk("15. MetricsCollector.persist() OK", ok_persist)

        loaded = mc.load_all()
        chk("15b. load_all() devuelve el registro",
            any(m.get("run_id") == run_id for m in loaded),
            f"loaded={len(loaded)}")

        since = mc.load_since(days=7)
        chk("16. load_since(7) incluye el registro reciente",
            any(m.get("run_id") == run_id for m in since),
            f"since_count={len(since)}")

    # ── 17-18: AnalyticsBuilder ───────────────────────────────────────────────
    from analytics_builder import AnalyticsBuilder

    with tempfile.TemporaryDirectory() as td:
        evidence_dir = Path(td) / "evidence" / "70"
        evidence_dir.mkdir(parents=True)
        metrics_path = Path(td) / "metrics.jsonl"

        # Escribir 3 registros de prueba
        test_metrics = [
            {"run_id": f"uat-70-{i}", "ticket_id": "70",
             "collected_at": "2026-05-08T12:00:00.000Z",
             "run": {"verdict": "PASS" if i < 2 else "FAIL", "duration_ms": 5000 + i * 1000},
             "events": {"total": 50, "by_level": {"info": 45, "error": 5}, "by_category": {}, "failures": 0, "blockers": 0, "playwright_actions": 10},
             "playwright": {"scenarios": 2, "pass": 2 if i < 2 else 1, "fail": 0 if i < 2 else 1, "blocked": 0, "assertions_total": 10, "assertions_pass": 9, "assertions_fail": 1, "screenshots": 3, "network_errors": 0},
             "stages": {"completed": ["reader", "runner"], "failed": [], "blocked": []},
             "learnings": {"candidates_generated": 1, "approved": 0},
             "blockers_summary": {"total": 0, "resolved": 0, "pending": 0, "skipped": 0},
            }
            for i in range(3)
        ]
        with open(metrics_path, "w") as f:
            for m in test_metrics:
                f.write(json.dumps(m) + "\n")

        mc2 = MetricsCollector(evidence_dir=evidence_dir, metrics_path=metrics_path)
        ab = AnalyticsBuilder(metrics_collector=mc2)
        pr = ab.pass_rate(days=7)

        chk("17. AnalyticsBuilder.pass_rate() calcula tasa correcta",
            pr["total_runs"] == 3 and pr["total_pass"] == 2,
            f"total={pr['total_runs']}, pass={pr['total_pass']}")

        # AnalyticsBuilder con 0 datos no crashea
        empty_metrics = Path(td) / "empty_metrics.jsonl"
        empty_metrics.write_text("")
        mc_empty = MetricsCollector(evidence_dir=evidence_dir, metrics_path=empty_metrics)
        ab_empty = AnalyticsBuilder(metrics_collector=mc_empty)
        try:
            report = ab_empty.full_report(days=7)
            chk("18. AnalyticsBuilder.full_report() con 0 datos no crashea", True)
        except Exception as e:
            chk("18. AnalyticsBuilder.full_report() con 0 datos no crashea", False, str(e))

    # ── 19-20: KPIBuilder ────────────────────────────────────────────────────
    from kpi_builder import KPIBuilder

    # Con 0 datos
    with tempfile.TemporaryDirectory() as td:
        empty_metrics = Path(td) / "empty.jsonl"
        empty_metrics.write_text("")
        mc_e = MetricsCollector(
            evidence_dir=Path(td) / "evidence", metrics_path=empty_metrics
        )
        ab_e = AnalyticsBuilder(mc_e)
        kb_e = KPIBuilder(ab_e)
        try:
            kpis_empty = kb_e.build_kpis(days=7)
            chk("19. KPIBuilder.build_kpis() con 0 datos no crashea",
                "kpis" in kpis_empty, str(list(kpis_empty.keys())))
            chk("19b. KPI-06 runs=0 tiene status yellow o green",
                any(k["id"] == "KPI-06" and k["status"] in ("yellow", "green")
                    for k in kpis_empty.get("kpis", [])))
        except Exception as e:
            chk("19. KPIBuilder.build_kpis() con 0 datos no crashea", False, str(e))

    # Con datos reales
    with tempfile.TemporaryDirectory() as td:
        metrics_path = Path(td) / "metrics.jsonl"
        with open(metrics_path, "w") as f:
            for i in range(5):
                f.write(json.dumps({
                    "run_id": f"uat-70-kpi-{i}",
                    "ticket_id": "70",
                    "collected_at": "2026-05-08T12:00:00.000Z",
                    "run": {"verdict": "PASS", "duration_ms": 90000},
                    "events": {"total": 50, "by_level": {}, "by_category": {}, "failures": 0, "blockers": 0, "playwright_actions": 0},
                    "playwright": {"scenarios": 2, "pass": 2, "fail": 0, "blocked": 0, "assertions_total": 10, "assertions_pass": 10, "assertions_fail": 0, "screenshots": 2, "network_errors": 0},
                    "stages": {"completed": ["runner"], "failed": [], "blocked": []},
                    "learnings": {"candidates_generated": 2, "approved": 1},
                    "blockers_summary": {"total": 1, "resolved": 1, "pending": 0, "skipped": 0},
                }) + "\n")
        mc3 = MetricsCollector(evidence_dir=Path(td) / "evidence", metrics_path=metrics_path)
        ab3 = AnalyticsBuilder(mc3)
        kb3 = KPIBuilder(ab3)
        kpis3 = kb3.build_kpis(days=7)
        kpi01 = next((k for k in kpis3["kpis"] if k["id"] == "KPI-01"), None)
        chk("20. KPI-01 pass_rate=100% es green",
            kpi01 is not None and kpi01["status"] == "green" and kpi01["value"] == 100.0,
            str(kpi01))

    # ── 21-22: ObservabilityValidator ────────────────────────────────────────
    from observability_validator import ObservabilityValidator

    with tempfile.TemporaryDirectory() as td:
        # Run vacio
        run_dir_empty = Path(td) / "uat-70-ov-empty"
        run_dir_empty.mkdir()
        ov = ObservabilityValidator(run_dir=run_dir_empty, run_id="uat-70-ov-empty")
        result = ov.validate()
        chk("21. ObservabilityValidator.validate() con run_dir vacio da score bajo",
            result["score"] < result["max_score"], f"score={result['score']}/{result['max_score']}")

        # Run con run_manifest
        run_dir_m = Path(td) / "uat-70-ov-manifest"
        run_dir_m.mkdir()
        (run_dir_m / "run_manifest.json").write_text(json.dumps({
            "run_id": "uat-70-ov-manifest", "ticket_id": "70",
            "started_at": "2026-05-08T12:00:00.000Z",
            "tool_version": "1.0.0", "schema_version": "1.0",
        }))
        ov2 = ObservabilityValidator(run_dir=run_dir_m, run_id="uat-70-ov-manifest")
        result2 = ov2.validate()
        chk("22. run_manifest check pasa con manifest valido",
            result2["checks"]["run_manifest"]["ok"], str(result2["checks"]["run_manifest"]))

    # ── 23-24: ReplayRun ─────────────────────────────────────────────────────
    from replay_run import ReplayRun

    with tempfile.TemporaryDirectory() as td:
        # Run vacio
        run_dir_r = Path(td) / "uat-70-replay-empty"
        run_dir_r.mkdir()
        rr = ReplayRun("uat-70-replay-empty", run_dir_r)
        report = rr.replay()
        chk("23. ReplayRun.replay() run_dir vacio devuelve estructura",
            all(k in report for k in ["ok", "run_id", "timeline", "stages", "errors"]))
        chk("23b. total_events=0", report["total_events"] == 0, f"={report['total_events']}")

        # Run con events.jsonl
        run_dir_ev = Path(td) / "uat-70-replay-ev"
        run_dir_ev.mkdir()
        events = [
            {"seq_run": 1, "event_id": "e1", "event_type": "run.started", "stage": "init",
             "status": "completed", "level": "info", "message": "Run iniciado",
             "source": "pipeline", "ts": "2026-05-08T12:00:00.000Z", "duration_ms": None, "action": "run_start"},
            {"seq_run": 2, "event_id": "e2", "event_type": "stage.started", "stage": "reader",
             "status": "completed", "level": "info", "message": "Stage reader iniciado",
             "source": "pipeline", "ts": "2026-05-08T12:00:01.000Z", "duration_ms": None, "action": "stage_start"},
            {"seq_run": 3, "event_id": "e3", "event_type": "stage.completed", "stage": "reader",
             "status": "completed", "level": "info", "message": "Stage reader completado",
             "source": "pipeline", "ts": "2026-05-08T12:00:02.000Z", "duration_ms": 1000, "action": "stage_end"},
            {"seq_run": 4, "event_id": "e4", "event_type": "run.completed", "stage": "init",
             "status": "completed", "level": "info", "message": "Run completado",
             "source": "pipeline", "ts": "2026-05-08T12:00:03.000Z", "duration_ms": None, "action": "run_end"},
        ]
        with open(run_dir_ev / "events.jsonl", "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        rr2 = ReplayRun("uat-70-replay-ev", run_dir_ev)
        report2 = rr2.replay()
        chk("24. ReplayRun.replay() con events devuelve timeline correcto",
            report2["total_events"] == 4 and len(report2["timeline"]) == 4,
            f"total={report2['total_events']}")
        chk("24b. stage 'reader' aparece en stages",
            "reader" in report2["stages"], str(list(report2["stages"].keys())))

    # ── 25-30: CLI handlers ──────────────────────────────────────────────────
    try:
        from qa_uat_pipeline import (
            _cmd_analytics_report, _cmd_replay_run,
            _cmd_validate_observability, _cmd_list_blockers, _cmd_resolve_blocker,
        )
        chk("30. qa_uat_pipeline.py importa y expone funciones Fase 4b", True)
    except Exception as e:
        chk("30. qa_uat_pipeline.py importa y expone funciones Fase 4b", False, str(e))
        print("\n[FATAL] No se pudo importar qa_uat_pipeline. Abortando checks CLI.")
        _print_final()
        return False

    # analytics_report con 0 datos
    try:
        result = _cmd_analytics_report(days=7)
        chk("25. _cmd_analytics_report no crashea", result.get("ok", False) or "error" not in result,
            str(result)[:100])
    except Exception as e:
        chk("25. _cmd_analytics_report no crashea", False, str(e))

    # replay_run con run_dir inexistente
    result = _cmd_replay_run(ticket_id=99999, run_id="uat-99999-fakeid")
    chk("26. _cmd_replay_run run_dir inexistente devuelve error",
        result.get("ok") is False and "error" in result, str(result)[:100])

    # validate_observability con evidence vacia
    with tempfile.TemporaryDirectory() as td:
        # Patch _TOOL_ROOT para que apunte al tempdir
        import qa_uat_pipeline as _qp
        orig_root = _qp._TOOL_ROOT
        _qp._TOOL_ROOT = Path(td)
        try:
            result = _cmd_validate_observability(ticket_id=99999)
            chk("27. _cmd_validate_observability evidence vacia devuelve error",
                result.get("ok") is False, str(result)[:100])
        finally:
            _qp._TOOL_ROOT = orig_root

    # list_blockers con run vacio
    with tempfile.TemporaryDirectory() as td:
        run_dir_lb = Path(td) / "uat-70-lb"
        run_dir_lb.mkdir()
        import qa_uat_pipeline as _qp2
        orig_root2 = _qp2._TOOL_ROOT
        _qp2._TOOL_ROOT = Path(td)
        try:
            (Path(td) / "evidence" / "70" / "uat-70-lb").mkdir(parents=True)
            result = _cmd_list_blockers(ticket_id=70, run_id="uat-70-lb")
            chk("28. _cmd_list_blockers run sin blockers devuelve lista vacia",
                result["ok"] and result["total"] == 0, str(result))
        finally:
            _qp2._TOOL_ROOT = orig_root2

    # resolve_blocker
    with tempfile.TemporaryDirectory() as td:
        import qa_uat_pipeline as _qp3
        orig_root3 = _qp3._TOOL_ROOT
        _qp3._TOOL_ROOT = Path(td)
        run_dir_rb = Path(td) / "evidence" / "70" / "uat-70-rb"
        run_dir_rb.mkdir(parents=True)
        hu_rb = HumanUnlock("uat-70-rb", run_dir_rb)
        bid_rb = hu_rb.block("runner", "test_reason", "test_question?", emit_event=False)
        try:
            result = _cmd_resolve_blocker(
                ticket_id=70, run_id="uat-70-rb",
                blocker_id=bid_rb, answer="respuesta_cli",
            )
            chk("29. _cmd_resolve_blocker resuelve correctamente",
                result["ok"] and result["remaining_pending"] == 0, str(result))
        finally:
            _qp3._TOOL_ROOT = orig_root3

    _print_final()
    return all(r["ok"] for r in _results)


def _print_final():
    print("\n" + "-" * 60)
    total = len(_results)
    passed = sum(1 for r in _results if r["ok"])
    failed = total - passed
    if failed == 0:
        print(f"\n[SMOKE PHASE 4] PASS -- {passed}/{total} checks OK\n")
    else:
        print(f"\n[SMOKE PHASE 4] FAIL -- {failed} checks FALLARON\n")
        for r in _results:
            if not r["ok"]:
                print(f"  {FAIL_STR} {r['name']}: {r['detail']}")


if __name__ == "__main__":
    ok = run_smoke_phase4()
    sys.exit(0 if ok else 1)
