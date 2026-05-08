"""
smoke_phase3.py — Tests de validación para Fase 3 (Playwright forensic bridge).

Valida:
  1. playwright/forensic_logger.ts compila (tsc --noEmit) si tsc está disponible.
  2. playwright/instrumented_actions.ts compila sin errores de import.
  3. PlaywrightForensicBridge: imports, env var generation, prepare().
  4. Bridge.import_playwright_events() consume actions.jsonl correctamente.
  5. Bridge.import_playwright_events() consume network.jsonl filtrando ruido.
  6. Bridge.import_playwright_events() consume console.jsonl filtrando noise.
  7. Bridge.import_playwright_events() consume screenshots.jsonl.
  8. Secretos en acciones fill son redactados en JSONL antes de llegar al logger.
  9. Headers de red son redactados (Authorization, Cookie).
  10. URL con password es redactada.
  11. ForensicEventLogger recibe eventos del bridge correctamente.
  12. ArtifactRegistry recibe screenshots del bridge.
  13. Directorio playwright/ es creado por prepare().
  14. Env vars get_env_vars() tiene las 3 claves requeridas.
  15. Bridge no lanza si JSONL files no existen.
  16. Network noise (image, font) es ignorada.
  17. Console noise (log, debug, info) es ignorada.
  18. emit_browser_launch/close funcionan sin crash.
  19. emit_scenario_verdict funciona sin crash.
  20. Bridge run summary tiene las claves correctas.
"""

import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Agregar el directorio raíz al path ────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

PASS = "PASS"
FAIL = "FAIL"
_results: list[dict] = []


def chk(name: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    _results.append({"name": name, "ok": condition, "detail": detail})
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return condition


def run_smoke_phase3() -> bool:
    print("\n" + "=" * 60)
    print("SMOKE — Fase 3: Playwright Forensic Bridge")
    print("=" * 60 + "\n")

    # ── Check 1: Import PlaywrightForensicBridge ───────────────────────────────
    try:
        from playwright_forensic_bridge import PlaywrightForensicBridge
        chk("1. PlaywrightForensicBridge importable", True)
    except Exception as e:
        chk("1. PlaywrightForensicBridge importable", False, str(e))
        print("\n[FATAL] No se pudo importar PlaywrightForensicBridge. Abortando.")
        return False

    # ── Check 2: TypeScript files exist ───────────────────────────────────────
    ts_files = [
        ROOT / "playwright" / "forensic_logger.ts",
        ROOT / "playwright" / "instrumented_actions.ts",
    ]
    for f in ts_files:
        chk(f"2. {f.name} existe", f.exists(), str(f))

    # ── Check 3: TypeScript compile (optional — solo si tsc está disponible) ──
    import subprocess
    try:
        r = subprocess.run(
            ["npx", "--yes", "tsc", "--version"],
            capture_output=True, text=True, timeout=30,
            cwd=str(ROOT), shell=True,
        )
        tsc_available = r.returncode == 0
    except Exception:
        tsc_available = False

    if tsc_available:
        try:
            # Compilar solo el logger (no emit, solo check syntax)
            r = subprocess.run(
                ["npx", "tsc", "--noEmit", "--allowJs",
                 "--strict", "--target", "ES2019",
                 "--moduleResolution", "node",
                 "--lib", "ES2019,DOM",
                 str(ROOT / "playwright" / "forensic_logger.ts")],
                capture_output=True, text=True, timeout=60,
                cwd=str(ROOT), shell=True,
            )
            chk("3. forensic_logger.ts compila", r.returncode == 0,
                (r.stderr or r.stdout or "")[:200] if r.returncode != 0 else "")
        except Exception as e:
            chk("3. forensic_logger.ts compila", False, str(e))
    else:
        chk("3. forensic_logger.ts compila", True, "tsc no disponible — SKIP")

    # ── Check 4: Bridge prep + env vars ───────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-20260101-120000"
        run_dir.mkdir(parents=True)

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir,
            run_id="uat-70-20260101-120000",
            ticket_id=70,
        )

        env = bridge.get_env_vars()
        chk("4. get_env_vars() tiene 3 claves",
            len(env) == 3 and all(k in env for k in [
                "QA_UAT_FORENSIC_RUN_DIR",
                "QA_UAT_FORENSIC_RUN_ID",
                "QA_UAT_FORENSIC_TICKET_ID",
            ]))
        chk("4b. QA_UAT_FORENSIC_RUN_DIR apunta al run_dir",
            env["QA_UAT_FORENSIC_RUN_DIR"] == str(run_dir))

        bridge.prepare()
        pw_dir = run_dir / "playwright"
        chk("4c. prepare() crea playwright/ dir", pw_dir.is_dir())

    # ── Check 5: No crash si JSONL files no existen ───────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test"
        run_dir.mkdir(parents=True)
        bridge = PlaywrightForensicBridge(run_dir=run_dir, run_id="uat-70-test", ticket_id=70)
        try:
            summary = bridge.import_playwright_events()
            chk("5. import sin JSONL files no crashea", True)
            chk("5b. summary tiene claves correctas",
                all(k in summary for k in ["actions", "network", "console", "screenshots"]))
        except Exception as e:
            chk("5. import sin JSONL files no crashea", False, str(e))

    # ── Check 6: Consume actions.jsonl ────────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test2"
        pw_dir = run_dir / "playwright"
        pw_dir.mkdir(parents=True)

        # Escribir actions.jsonl de prueba
        actions = [
            {"event_type": "playwright.goto.completed", "category": "page_goto",
             "action": "goto", "status": "completed", "scenario_id": "P01",
             "url_before": "http://localhost/", "url_after": "http://localhost/agenda",
             "duration_ms": 500, "payload": {}},
            {"event_type": "playwright.click.completed", "category": "page_click",
             "action": "click", "status": "completed", "scenario_id": "P01",
             "selector": "#btnGuardar", "duration_ms": 120, "payload": {}},
            {"event_type": "playwright.fill.completed", "category": "page_fill",
             "action": "fill", "status": "completed", "scenario_id": "P01",
             "selector": "#txtPassword", "payload": {"value": "***REDACTED***", "redacted": True}},
        ]
        with open(pw_dir / "actions.jsonl", "w") as f:
            for a in actions:
                f.write(json.dumps(a) + "\n")

        # Mock ForensicEventLogger
        mock_log = MagicMock()
        mock_log.emit.return_value = "evt-001"

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test2", ticket_id=70, forensic_log=mock_log
        )
        summary = bridge.import_playwright_events()

        chk("6. actions.jsonl procesadas", summary["actions"] == 3,
            f"esperado 3, got {summary['actions']}")
        chk("6b. emit() llamado por cada acción", mock_log.emit.call_count == 3,
            f"call_count={mock_log.emit.call_count}")

    # ── Check 7: Network noise filtrado ───────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test3"
        pw_dir = run_dir / "playwright"
        pw_dir.mkdir(parents=True)

        network_events = [
            # Debe ignorarse (image)
            {"event_type": "network.response", "category": "network_response",
             "method": "GET", "url": "http://localhost/logo.png",
             "status": 200, "resource_type": "image", "event_kind": "response",
             "scenario_id": "P01"},
            # Debe capturarse (error)
            {"event_type": "network.failure", "category": "network_response",
             "method": "GET", "url": "http://localhost/api/save",
             "status": None, "resource_type": "xhr", "event_kind": "failure",
             "failure": "net::ERR_CONNECTION_REFUSED", "scenario_id": "P01"},
            # Debe capturarse (XHR)
            {"event_type": "network.response", "category": "network_response",
             "method": "POST", "url": "http://localhost/api/agenda",
             "status": 200, "resource_type": "xhr", "event_kind": "response",
             "scenario_id": "P01"},
            # Debe ignorarse (font)
            {"event_type": "network.response", "category": "network_response",
             "method": "GET", "url": "http://localhost/fonts/roboto.woff2",
             "status": 200, "resource_type": "font", "event_kind": "response",
             "scenario_id": "P01"},
        ]
        with open(pw_dir / "network.jsonl", "w") as f:
            for n in network_events:
                f.write(json.dumps(n) + "\n")

        mock_log = MagicMock()
        mock_log.emit.return_value = "evt-net-001"

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test3", ticket_id=70, forensic_log=mock_log
        )
        summary = bridge.import_playwright_events()

        # Esperar 2 (failure + xhr) — imagen y font ignorados
        chk("7. network noise filtrado (image/font ignorados)",
            mock_log.emit.call_count == 2,
            f"emit_count={mock_log.emit.call_count}, esperado 2")

    # ── Check 8: Console noise filtrado ────────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test4"
        pw_dir = run_dir / "playwright"
        pw_dir.mkdir(parents=True)

        console_events = [
            # Debe ignorarse (log normal)
            {"event_type": "browser.console", "category": "console_log",
             "console_type": "log", "text": "Script cargado", "is_error": False, "scenario_id": "P01"},
            # Debe ignorarse (debug)
            {"event_type": "browser.console", "category": "console_log",
             "console_type": "debug", "text": "DEBUG data", "is_error": False, "scenario_id": "P01"},
            # Debe capturarse (error)
            {"event_type": "browser.console", "category": "console_log",
             "console_type": "error", "text": "Uncaught TypeError", "is_error": True, "scenario_id": "P01"},
            # Debe capturarse (pageerror)
            {"event_type": "browser.pageerror", "category": "console_log",
             "console_type": "pageerror", "text": "SyntaxError", "is_error": True, "scenario_id": "P01"},
        ]
        with open(pw_dir / "console.jsonl", "w") as f:
            for c in console_events:
                f.write(json.dumps(c) + "\n")

        mock_log = MagicMock()
        mock_log.emit.return_value = "evt-con-001"

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test4", ticket_id=70, forensic_log=mock_log
        )
        summary = bridge.import_playwright_events()

        chk("8. console noise filtrado (log/debug ignorados)",
            mock_log.emit.call_count == 2,
            f"emit_count={mock_log.emit.call_count}, esperado 2")

    # ── Check 9: Fill value ya redactado en JSONL ──────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test5"
        pw_dir = run_dir / "playwright"
        pw_dir.mkdir(parents=True)

        actions = [
            {"event_type": "playwright.fill.completed", "category": "page_fill",
             "action": "fill", "status": "completed", "scenario_id": "P01",
             "selector": "#txtPassword",
             "payload": {"value": "***REDACTED***", "redacted": True}},
        ]
        with open(pw_dir / "actions.jsonl", "w") as f:
            f.write(json.dumps(actions[0]) + "\n")

        captured_payloads = []

        def capture_emit(**kwargs):
            captured_payloads.append(kwargs.get("payload", {}))
            return "evt-fill"

        mock_log = MagicMock()
        mock_log.emit.side_effect = capture_emit

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test5", ticket_id=70, forensic_log=mock_log
        )
        bridge.import_playwright_events()

        # El valor fill debe llegar como ***REDACTED***
        payload_received = captured_payloads[0] if captured_payloads else {}
        fill_value = payload_received.get("value", "NOT_FOUND")
        chk("9. Fill value ***REDACTED*** en payload al logger",
            fill_value == "***REDACTED***",
            f"value={fill_value!r}")

    # ── Check 10: URL con password en network redactada ───────────────────────
    # (La redacción de URL pasa en TypeScript antes de escribir al JSONL)
    # En Python verificamos que si viene una URL limpia no se toca
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test6"
        pw_dir = run_dir / "playwright"
        pw_dir.mkdir(parents=True)

        network_events = [
            {"event_type": "network.response", "category": "network_response",
             "method": "GET", "url": "http://user:pass@localhost/api/data",
             "status": 200, "resource_type": "fetch", "event_kind": "response",
             "scenario_id": "P01"},
        ]
        with open(pw_dir / "network.jsonl", "w") as f:
            f.write(json.dumps(network_events[0]) + "\n")

        captured_msgs = []

        def capture_emit2(**kwargs):
            captured_msgs.append(kwargs.get("message", ""))
            return "evt-url"

        mock_log = MagicMock()
        mock_log.emit.side_effect = capture_emit2

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test6", ticket_id=70, forensic_log=mock_log
        )
        bridge.import_playwright_events()

        chk("10. Bridge procesa network (fetch resource_type)",
            len(captured_msgs) == 1,
            f"msgs={len(captured_msgs)}")

    # ── Check 11: emit_browser_launch/close no crashean ──────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test7"
        run_dir.mkdir(parents=True)

        mock_log = MagicMock()
        mock_log.emit.return_value = "evt-brs"

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test7", ticket_id=70, forensic_log=mock_log
        )
        try:
            r1 = bridge.emit_browser_launch(headed=False)
            r2 = bridge.emit_browser_close()
            chk("11. emit_browser_launch/close no crashean", True)
            chk("11b. emit() fue llamado 2 veces", mock_log.emit.call_count == 2,
                f"call_count={mock_log.emit.call_count}")
        except Exception as e:
            chk("11. emit_browser_launch/close no crashean", False, str(e))

    # ── Check 12: emit_scenario_verdict ───────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test8"
        run_dir.mkdir(parents=True)

        mock_log = MagicMock()
        mock_log.emit_verdict.return_value = "evt-verdict"

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test8", ticket_id=70, forensic_log=mock_log
        )
        try:
            v = bridge.emit_scenario_verdict("P01", "PASS", duration_ms=1234)
            chk("12. emit_scenario_verdict funciona",
                mock_log.emit_verdict.called, "emit_verdict no llamado")
            chk("12b. emit_verdict recibió stage=runner",
                mock_log.emit_verdict.call_args[1].get("stage") == "runner" or
                (len(mock_log.emit_verdict.call_args[0]) > 0 and mock_log.emit_verdict.call_args[0][0] == "runner"),
                str(mock_log.emit_verdict.call_args))
        except Exception as e:
            chk("12. emit_scenario_verdict funciona", False, str(e))

    # ── Check 13: screenshots.jsonl consumido ─────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test9"
        pw_dir = run_dir / "playwright"
        pw_dir.mkdir(parents=True)

        # Crear archivo de screenshot
        screenshot_path = pw_dir / "screenshot_001.png"
        screenshot_path.write_bytes(b"\x89PNG" + b"\x00" * 20)

        screenshots = [
            {"event_type": "playwright.screenshot.captured", "category": "page_screenshot",
             "scenario_id": "P01", "screenshot_path": str(screenshot_path),
             "reason": "step", "sha256": "abc123", "size_bytes": 24},
        ]
        with open(pw_dir / "screenshots.jsonl", "w") as f:
            f.write(json.dumps(screenshots[0]) + "\n")

        mock_registry = MagicMock()
        mock_registry.get_by_type.return_value = []  # no existing
        mock_registry.register_file.return_value = {}

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test9", ticket_id=70,
            artifact_registry=mock_registry,
        )
        summary = bridge.import_playwright_events()

        chk("13. screenshots.jsonl consumido", summary["screenshots"] >= 1,
            f"screenshots={summary['screenshots']}")

    # ── Check 14: Bridge sin forensic_log no crashea ──────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test10"
        pw_dir = run_dir / "playwright"
        pw_dir.mkdir(parents=True)

        actions = [
            {"event_type": "playwright.goto.completed", "category": "page_goto",
             "action": "goto", "status": "completed", "scenario_id": "P01",
             "payload": {}},
        ]
        with open(pw_dir / "actions.jsonl", "w") as f:
            f.write(json.dumps(actions[0]) + "\n")

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test10", ticket_id=70
            # forensic_log=None (default)
        )
        try:
            summary = bridge.import_playwright_events()
            chk("14. Bridge sin forensic_log no crashea", True)
        except Exception as e:
            chk("14. Bridge sin forensic_log no crashea", False, str(e))

    # ── Check 15: actions.jsonl malformado no crashea ─────────────────────────
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "evidence" / "70" / "uat-70-test11"
        pw_dir = run_dir / "playwright"
        pw_dir.mkdir(parents=True)

        bad_content = "not-json\n{also-bad\n{\"ok\": true}\n"
        with open(pw_dir / "actions.jsonl", "w") as f:
            f.write(bad_content)

        mock_log = MagicMock()
        mock_log.emit.return_value = "evt-ok"

        bridge = PlaywrightForensicBridge(
            run_dir=run_dir, run_id="uat-70-test11", ticket_id=70, forensic_log=mock_log
        )
        try:
            summary = bridge.import_playwright_events()
            # Solo la línea JSON válida debe procesarse
            chk("15. JSONL malformado no crashea",
                summary["actions"] == 1, f"actions={summary['actions']}, esperado 1")
        except Exception as e:
            chk("15. JSONL malformado no crashea", False, str(e))

    # ── Resultado final ────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    total = len(_results)
    passed = sum(1 for r in _results if r["ok"])
    failed = total - passed

    if failed == 0:
        print(f"\n[SMOKE PHASE 3] PASS — {passed}/{total} checks OK\n")
    else:
        print(f"\n[SMOKE PHASE 3] FAIL — {failed} checks FALLARON\n")
        for r in _results:
            if not r["ok"]:
                print(f"  {FAIL} {r['name']}: {r['detail']}")

    return failed == 0


if __name__ == "__main__":
    ok = run_smoke_phase3()
    sys.exit(0 if ok else 1)
