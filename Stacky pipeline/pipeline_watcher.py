"""
pipeline_watcher.py — Watcher de filesystem para avance inmediato del pipeline.

En lugar de pollear cada 5s, usa watchdog para reaccionar en el instante que
un agente crea un flag de completado (PM_COMPLETADO.flag, DEV_COMPLETADO.md,
TESTER_COMPLETADO.md) o un flag de error (PM_ERROR.flag, etc.).

Latencia: 0ms vs hasta 5s con polling.

Fallback: si watchdog no está instalado, usa un hilo de polling rápido (500ms).

Integración:
    from pipeline_watcher import PipelineWatcher
    watcher = PipelineWatcher(tickets_base, state_path, on_advance=mi_callback)
    watcher.start()
    ...
    watcher.stop()
"""

import logging
import os
import threading
import time

logger = logging.getLogger("stacky.watcher")

try:
    from stacky_log import slog as _slog
except ImportError:
    _slog = None

def _sl(ticket_id, component, msg, level="info"):
    if _slog:
        getattr(_slog, level)(ticket_id, component, msg)

# Intentar importar el validador de output (opcional — si no existe, se omite)
try:
    from output_validator import validate_stage_output, write_error_flag_if_invalid
    _VALIDATOR_AVAILABLE = True
except ImportError:
    _VALIDATOR_AVAILABLE = False
    logger.debug("output_validator no disponible — validación de output deshabilitada")

# Git changes reporter
_GIT_REPORTER_AVAILABLE = False

def _generate_git_changes(workspace_root: str, ticket_folder: str) -> None:
    """Generate GIT_CHANGES.md with git status + diff summary."""
    import subprocess, os
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15
        )
        status = r.stdout
        r2 = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=workspace_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30
        )
        diff_stat = r2.stdout
        out_path = os.path.join(ticket_folder, "GIT_CHANGES.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Git Changes\n\n## Status\n```\n")
            f.write(status or "(sin cambios)\n")
            f.write("```\n\n## Diff Summary\n```\n")
            f.write(diff_stat or "(sin diff)\n")
            f.write("```\n")
        logger.info("[GIT] GIT_CHANGES.md generado en %s", ticket_folder)
    except Exception as e:
        logger.warning("[GIT] Error generando GIT_CHANGES.md: %s", e)

_GIT_REPORTER_AVAILABLE = True

# Intentar importar el generador de commit messages
try:
    from commit_generator import generate_commit_message
    _COMMIT_GEN_AVAILABLE = True
except ImportError:
    _COMMIT_GEN_AVAILABLE = False
    logger.debug("commit_generator no disponible")

# G-01: Build Gate — ejecutar tests post-DEV antes de invocar QA
try:
    from test_runner import run_post_dev_tests
    _TEST_RUNNER_AVAILABLE = True
except ImportError:
    _TEST_RUNNER_AVAILABLE = False
    logger.debug("test_runner no disponible — build gate deshabilitado")

# Q-09: Production Readiness Gate — pre-close post-QA
try:
    from production_readiness_gate import ProductionReadinessGate, ReadinessReport
    _READINESS_GATE_AVAILABLE = True
except ImportError:
    _READINESS_GATE_AVAILABLE = False
    logger.debug("production_readiness_gate no disponible — readiness gate deshabilitado")

# X-01: Self-Improving Prompt Engine
try:
    from self_improving_engine import get_engine as _get_self_improving_engine
    _SELF_IMPROVING_AVAILABLE = True
except ImportError:
    _SELF_IMPROVING_AVAILABLE = False
    _get_self_improving_engine = None
    logger.debug("self_improving_engine no disponible")

# ── Mapping flag → (stage_completado, siguiente_estado) ──────────────────────
_FLAG_TRANSITIONS = {
    "PM_COMPLETADO.flag":    ("pm",     "pm_completado"),
    "DEV_COMPLETADO.md":     ("dev",    "dev_completado"),
    "TESTER_COMPLETADO.md":  ("tester", "tester_completado"),
}
_ERROR_FLAGS = {"PM_ERROR.flag", "DEV_ERROR.flag", "TESTER_ERROR.flag"}

# Todos los flags que disparan una reacción
_WATCH_FLAGS = set(_FLAG_TRANSITIONS.keys()) | _ERROR_FLAGS


def _ticket_id_from_path(path: str, tickets_base: str) -> str | None:
    """Extrae ticket_id a partir de la ruta de un archivo de flag."""
    try:
        rel = os.path.relpath(path, tickets_base)
        parts = rel.replace("\\", "/").split("/")
        # Estructura: {estado}/{ticket_id}/{flag}
        if len(parts) >= 3:
            return parts[1]
        # Estructura: {ticket_id}/{flag}  (si tickets_base ya incluye el estado)
        if len(parts) == 2:
            return parts[0]
    except Exception:
        pass
    return None


class PipelineWatcher:
    """
    Monitorea la carpeta de tickets y llama a callbacks cuando detecta flags
    de completado o error.

    Callbacks:
        on_advance(ticket_id, stage_completed, new_state, folder)
        on_error(ticket_id, error_stage, reason, folder)

    Ambos se llaman desde un thread worker — deben ser thread-safe.
    """

    def __init__(self, tickets_base: str, state_path: str,
                 on_advance=None, on_error=None,
                 poll_interval: float = 0.5):
        self._tickets_base   = tickets_base
        self._state_path     = state_path
        self._on_advance     = on_advance
        self._on_error       = on_error
        self._poll_interval  = poll_interval
        self._stop_event     = threading.Event()
        self._thread         = None
        self._use_watchdog   = False

        # Intentar usar watchdog (más eficiente que polling)
        try:
            from watchdog.observers import Observer          # noqa: F401
            from watchdog.events import FileSystemEventHandler  # noqa: F401
            self._use_watchdog = True
        except ImportError:
            logger.debug("watchdog no instalado — usando polling cada %.1fs", poll_interval)

    # ── API pública ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Inicia el watcher en un thread daemon."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        if self._use_watchdog:
            self._thread = threading.Thread(
                target=self._run_watchdog, daemon=True, name="pipeline-watcher"
            )
        else:
            self._thread = threading.Thread(
                target=self._run_polling, daemon=True, name="pipeline-watcher"
            )
        self._thread.start()
        logger.info("PipelineWatcher iniciado (%s)", "watchdog" if self._use_watchdog else "polling")

    def stop(self) -> None:
        """Detiene el watcher."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("PipelineWatcher detenido")

    # ── Implementación watchdog ───────────────────────────────────────────────

    def _run_watchdog(self) -> None:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        watcher = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                fname = os.path.basename(event.src_path)
                if fname in _WATCH_FLAGS:
                    watcher._handle_flag(event.src_path)

            def on_modified(self, event):
                # DEV_COMPLETADO.md puede crearse vacío y luego escribirse
                if event.is_directory:
                    return
                fname = os.path.basename(event.src_path)
                if fname in _WATCH_FLAGS:
                    watcher._handle_flag(event.src_path)

        observer = Observer()
        if os.path.isdir(self._tickets_base):
            observer.schedule(_Handler(), self._tickets_base, recursive=True)
        observer.start()
        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        finally:
            observer.stop()
            observer.join()

    # ── Implementación polling ────────────────────────────────────────────────

    def _run_polling(self) -> None:
        """Polling rápido de 500ms como fallback cuando watchdog no está disponible.

        Usa dict {path: mtime} en lugar de set de paths: detecta tanto flags nuevos
        como flags re-creados (mismo path, distinto mtime) — caso clave cuando PM
        falla validación, se relanza, y escribe el mismo PM_COMPLETADO.flag de nuevo.
        """
        seen: dict[str, float] = {}  # path → mtime

        while not self._stop_event.is_set():
            try:
                current = self._scan_flags_with_mtime()
                for flag_path, mtime in current.items():
                    prev_mtime = seen.get(flag_path)
                    if prev_mtime is None or prev_mtime != mtime:
                        # Flag nuevo O re-escrito (retry del agente)
                        logger.debug("[POLL] Flag detectado/actualizado: %s (mtime=%.0f → %.0f)",
                                     flag_path, prev_mtime or 0.0, mtime)
                        self._handle_flag(flag_path)
                        seen[flag_path] = mtime
                # Limpiar flags que ya no existen (fueron renombrados/borrados)
                for path in list(seen):
                    if path not in current:
                        del seen[path]
            except Exception as e:
                logger.debug("Error en polling: %s", e)
            time.sleep(self._poll_interval)

    def _scan_flags_with_mtime(self) -> dict[str, float]:
        """Escanea carpeta de tickets y retorna {path: mtime} para cada flag conocido."""
        flags: dict[str, float] = {}
        if not os.path.isdir(self._tickets_base):
            return flags
        for root, dirs, files in os.walk(self._tickets_base):
            dirs[:] = [d for d in dirs if d != "archivado"]
            for fname in files:
                if fname in _WATCH_FLAGS:
                    full = os.path.join(root, fname)
                    try:
                        flags[full] = os.path.getmtime(full)
                    except OSError:
                        pass
        return flags

    def _scan_flags(self) -> set[str]:
        """Escanea toda la carpeta de tickets buscando flags conocidos (compat. legado)."""
        return set(self._scan_flags_with_mtime().keys())

    # ── Procesamiento de flags ────────────────────────────────────────────────

    def _handle_flag(self, flag_path: str) -> None:
        """Procesa un flag detectado y dispara el callback correspondiente."""
        fname     = os.path.basename(flag_path)
        folder    = os.path.dirname(flag_path)
        ticket_id = _ticket_id_from_path(flag_path, self._tickets_base)

        if not ticket_id:
            logger.debug("No se pudo extraer ticket_id de: %s", flag_path)
            return

        if fname in _ERROR_FLAGS:
            stage = fname.replace("_ERROR.flag", "").lower()
            try:
                with open(flag_path, encoding="utf-8", errors="replace") as fh:
                    reason = fh.read(500).strip()
            except Exception:
                reason = "Error desconocido"
            logger.info("[WATCHER] Error flag detectado: %s → %s: %s",
                        ticket_id, stage, reason[:80])
            if self._on_error:
                self._on_error(ticket_id, stage, reason, folder)
            return

        if fname in _FLAG_TRANSITIONS:
            stage_done, new_state = _FLAG_TRANSITIONS[fname]
            logger.info("[WATCHER] Completado: %s → %s → %s",
                        ticket_id, stage_done, new_state)
            if _slog:
                _slog.flag_detected(ticket_id, fname, folder)

            # ── Validación de output antes de avanzar ────────────────────────
            if _VALIDATOR_AVAILABLE:
                try:
                    val = validate_stage_output(stage_done, folder, ticket_id)
                    if _slog:
                        _slog.validation(ticket_id, stage_done, val.ok,
                                         issues=val.issues, warnings=val.warnings)
                    if val.warnings:
                        for w in val.warnings:
                            logger.warning("[VALIDATOR] %s/%s: %s", ticket_id, stage_done, w)
                    if not val.ok:
                        logger.warning(
                            "[VALIDATOR] Output de %s/%s inválido — creando error flag:\n%s",
                            ticket_id, stage_done, val.issues_str()
                        )
                        write_error_flag_if_invalid(val, folder)
                        err_reason = f"Validación automática falló:\n{val.issues_str()}"
                        if _slog:
                            _slog.stage_error(ticket_id, stage_done, err_reason)
                        # Disparar on_error en lugar de on_advance
                        if self._on_error:
                            self._on_error(ticket_id, stage_done, err_reason, folder)
                        return
                except Exception as ve:
                    logger.warning("[VALIDATOR] Error al validar %s/%s: %s",
                                   ticket_id, stage_done, ve)
                    _sl(ticket_id, "valid", f"Excepción al validar {stage_done}: {ve}", "warning")
            # ── Fin validación ───────────────────────────────────────────────

            # ── G-01: Build Gate — ejecutar tests post-DEV antes de QA ───────
            if stage_done == "dev" and _TEST_RUNNER_AVAILABLE:
                try:
                    ws_root = self._get_workspace_root()
                    if ws_root:
                        logger.info("[BUILD-GATE] Ejecutando tests post-DEV para %s...", ticket_id)
                        test_result = run_post_dev_tests(folder, ticket_id, ws_root)
                        if test_result is not None:
                            if not test_result.success:
                                err_reason = (
                                    f"Build Gate falló:\n"
                                    f"  Build: {'OK' if test_result.build_ok else 'FAILED'}\n"
                                    f"  Tests: {test_result.tests_passed}/{test_result.tests_run} passed\n"
                                )
                                if test_result.build_errors:
                                    err_reason += "  Build errors:\n" + "\n".join(
                                        f"    - {e}" for e in test_result.build_errors[:5]
                                    )
                                if test_result.test_errors:
                                    err_reason += "\n  Test errors:\n" + "\n".join(
                                        f"    - {e}" for e in test_result.test_errors[:5]
                                    )
                                logger.error("[BuildGate] Build fallido — QA no invocado. Ticket: %s", ticket_id)
                                _sl(ticket_id, "build-gate", err_reason, "warning")
                                # Write DEV_ERROR.flag to block QA
                                err_flag = os.path.join(folder, "DEV_ERROR.flag")
                                with open(err_flag, "w", encoding="utf-8") as ef:
                                    ef.write(err_reason)
                                if self._on_error:
                                    self._on_error(ticket_id, "dev", err_reason, folder)
                                return  # Do NOT advance to QA
                            else:
                                logger.info(
                                    "[BUILD-GATE] %s PASÓ — build OK, %d/%d tests passed",
                                    ticket_id, test_result.tests_passed, test_result.tests_run
                                )
                except Exception as bge:
                    logger.warning("[BUILD-GATE] Error ejecutando build gate: %s", bge)
                    _sl(ticket_id, "build-gate", f"Excepción: {bge}", "warning")
            # ── Fin Build Gate ───────────────────────────────────────────────

            # ── Static Analysis Tests post-DEV (E-05 + F-01 + E-13) ─────────
            if stage_done == "dev":
                try:
                    from evidence_collector import EvidenceCollector, TestCase
                    collector = EvidenceCollector()

                    # F-01: Idempotency check
                    try:
                        from idempotency_tester import IdempotencyTester
                        idem_cases = IdempotencyTester().check_for_idempotency_risks(folder)
                        if idem_cases:
                            collector.add_section("Idempotency Analysis", idem_cases)
                    except ImportError:
                        pass

                    # E-13: Rollback verification
                    try:
                        from rollback_verifier import RollbackVerifier
                        rb_cases = RollbackVerifier().verify(folder)
                        if rb_cases:
                            collector.add_section("Rollback Verification", rb_cases)
                    except ImportError:
                        pass

                    if collector.total_cases > 0:
                        collector.build_report(folder)
                        logger.info(
                            "[STATIC-TESTS] %s: %d/%d casos pasaron",
                            ticket_id, collector.total_passed, collector.total_cases
                        )
                except Exception as ste:
                    logger.warning("[STATIC-TESTS] Error: %s", ste)
            # ── Fin Static Analysis ──────────────────────────────────────────

            # ── M-01/Y-01: Feedback loop QA → (DEV rework | PM revision) ────
            # Delega el routing de veredicto a pipeline_runner._auto_advance.
            # Este watcher solo deja pasar el control si verdict = APROBADO.
            if stage_done == "tester" and _VALIDATOR_AVAILABLE:
                try:
                    from output_validator import validate_stage_output
                    qa_val = validate_stage_output("tester", folder, ticket_id)
                    verdict = getattr(qa_val, "verdict", None)
                    if verdict in ("CON OBSERVACIONES", "RECHAZADO"):
                        logger.info(
                            "[REWORK] %s: QA verdict=%s — routing lo maneja _auto_advance",
                            ticket_id, verdict
                        )
                        return
                except Exception as re:
                    logger.warning("[REWORK] Error inspeccionando veredicto QA: %s", re)
            # ── Fin feedback loop ─────────────────────────────────────────────

            # ── Commit message post-QA aprobado ─────────────────────────────
            if stage_done == "tester" and _COMMIT_GEN_AVAILABLE:
                try:
                    proj = self._get_active_project()
                    generate_commit_message(folder, ticket_id, proj)
                    logger.info("[COMMIT] COMMIT_MESSAGE.txt generado para %s", ticket_id)
                except Exception as ce:
                    logger.warning("[COMMIT] Error generando commit message: %s", ce)
            # ── Fin commit message ───────────────────────────────────────────

            # ── Git changes report post-DEV ──────────────────────────────────────────
            if stage_done == "dev" and _GIT_REPORTER_AVAILABLE:
                try:
                    ws_root = self._get_workspace_root()
                    if ws_root:
                        threading.Thread(
                            target=_generate_git_changes,
                            args=(ws_root, folder),
                            daemon=True,
                            name=f"git-report-{ticket_id}",
                        ).start()
                        logger.info("[GIT] Generando GIT_CHANGES.md para %s", ticket_id)
                except Exception as se:
                    logger.warning("[GIT] Error generando changes report: %s", se)
            # ── Fin Git report ───────────────────────────────────────────────

            # ── Q-09: Production Readiness Gate — pre-close post-QA ─────────
            readiness_blocked = False
            if stage_done == "tester" and _READINESS_GATE_AVAILABLE:
                try:
                    try:
                        wid_int = int(ticket_id)
                    except (TypeError, ValueError):
                        wid_int = 0
                    gate   = ProductionReadinessGate()
                    report = gate.evaluate(folder, wid_int)
                    if not report.ready:
                        readiness_blocked = True
                        logger.warning(
                            "[READINESS] %s: %d blockers — no se marcará Resolved",
                            ticket_id, len(report.blockers)
                        )
                        for b in report.blockers:
                            logger.warning("[READINESS]   - %s", b)
                            _sl(ticket_id, "readiness", f"Blocker: {b}", "warning")
                        try:
                            out_path = os.path.join(folder, "READINESS_BLOCKED.md")
                            with open(out_path, "w", encoding="utf-8") as f:
                                f.write(f"# Readiness Gate Blocked — Ticket {ticket_id}\n\n")
                                f.write("QA aprobó, pero el Production Readiness Gate "
                                        "detectó los siguientes bloqueantes:\n\n")
                                for b in report.blockers:
                                    f.write(f"- {b}\n")
                                f.write("\n## Detalle de checks\n\n")
                                for cid, result in report.check_results.items():
                                    desc = gate.CHECKS.get(cid, cid)
                                    if result is True:
                                        mark = "OK"
                                    elif result is False:
                                        mark = "FAIL"
                                    else:
                                        mark = "UNKNOWN"
                                    f.write(f"- [{mark}] {cid}: {desc}\n")
                        except Exception as we:
                            logger.warning("[READINESS] No se pudo escribir READINESS_BLOCKED.md: %s", we)
                    else:
                        logger.info("[READINESS] %s: todos los checks OK — procediendo a Resolved",
                                    ticket_id)
                except Exception as ge:
                    logger.warning("[READINESS] Error evaluando gate: %s", ge)
            # ── Fin Readiness Gate ───────────────────────────────────────────

            # ── X-01: Self-Improving Prompt Engine ──────────────────────────
            # Registrar como "golden example" solo si: QA APROBADO + primer intento
            if (stage_done == "tester"
                    and _SELF_IMPROVING_AVAILABLE
                    and not readiness_blocked):
                try:
                    self._maybe_record_golden_success(ticket_id, folder)
                except Exception as se:
                    logger.warning("[GOLDEN] Error registrando success: %s", se)
            # ── Fin Self-Improving Engine ────────────────────────────────────

            # ── A3: Postflight validation ────────────────────────────────────
            # Antes de marcar *_completado, validar que los outputs esperados
            # existen y son útiles. Si fallan → error_{stage} y NO avanzar.
            if new_state.endswith("_completado") and stage_done in ("pm", "dev", "tester"):
                try:
                    from postflight_validator import validate_stage_outputs
                    pf = validate_stage_outputs(folder, stage_done)
                    if not pf.ok:
                        logger.warning(
                            "[POSTFLIGHT] %s/%s falló validación: %s — marcando error_%s",
                            ticket_id, stage_done, pf.reason, stage_done,
                        )
                        try:
                            from pipeline_state import load_state, save_state, mark_error
                            _st = load_state(self._state_path)
                            mark_error(_st, ticket_id, stage_done,
                                       f"postflight: {pf.reason}")
                            save_state(self._state_path, _st)
                        except Exception as me:
                            logger.error("[POSTFLIGHT] No se pudo marcar error_%s: %s",
                                         stage_done, me)
                        if self._on_error:
                            try:
                                self._on_error(ticket_id, stage_done, pf.reason, folder)
                            except Exception as oe:
                                logger.debug("[POSTFLIGHT] on_error callback falló: %s", oe)
                        return
                except ImportError:
                    logger.debug("postflight_validator no disponible — skipping")
                except Exception as pe:
                    logger.warning("[POSTFLIGHT] error inesperado para %s/%s: %s — "
                                   "permitiendo transición por seguridad",
                                   ticket_id, stage_done, pe)
            # ── Fin Postflight ───────────────────────────────────────────────

            # Actualizar pipeline_state
            self._advance_state(ticket_id, new_state, folder)
            if _slog:
                _slog.transition(ticket_id, f"{stage_done}_en_proceso", new_state, source="watcher")
            if readiness_blocked:
                logger.info("[READINESS] %s: on_advance omitido (QA approved pending readiness)",
                            ticket_id)
                return
            if self._on_advance:
                self._on_advance(ticket_id, stage_done, new_state, folder)

    def _get_rework_count(self, ticket_id: str) -> int:
        """Retorna cuántos ciclos de rework ya se hicieron para el ticket."""
        try:
            from pipeline_state import load_state
            state = load_state(self._state_path)
            entry = state.get("tickets", {}).get(ticket_id, {})
            return entry.get("rework_count", 0)
        except Exception:
            return 0

    def _maybe_record_golden_success(self, ticket_id: str, folder: str) -> None:
        """X-01: Si QA aprobó al primer intento, guardar ticket como golden example."""
        if _get_self_improving_engine is None:
            return
        # Sólo primer intento (sin reworks)
        if self._get_rework_count(ticket_id) > 0:
            return
        # Verificar veredicto APROBADO en TESTER_COMPLETADO.md
        tester_path = os.path.join(folder, "TESTER_COMPLETADO.md")
        if not os.path.isfile(tester_path):
            return
        try:
            with open(tester_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return
        if "APROBADO" not in content.upper():
            return
        # "APROBADO" no debe estar contenido en "RECHAZADO"/"CON OBSERVACIONES"
        upper = content.upper()
        if "CON OBSERVACIONES" in upper or "RECHAZADO" in upper:
            # Verificar que el veredicto efectivo sea APROBADO puro
            import re as _re
            m = _re.search(r"veredicto[^\n:]*[:\-]\s*(\w[\w ]*)", content, _re.IGNORECASE)
            if m and "APROBADO" not in m.group(1).upper():
                return

        engine = _get_self_improving_engine()

        # Intentar recuperar los prompts usados desde prompt_tracker (solo hashes)
        # prompt_tracker.py almacena hashes, no el texto completo — usamos ""
        # como fallback y dejamos que el prompt_snapshot quede vacío.
        for stage in ("pm", "dev", "tester"):
            try:
                engine.record_success(folder, stage, "")
            except Exception as e:
                logger.debug("[GOLDEN] record_success(%s) falló: %s", stage, e)

    def _launch_rework(self, ticket_id: str, folder: str,
                       qa_findings: list[str], rework_num: int) -> None:
        """Lanza el agente DEV con prompt de rework."""
        try:
            from pipeline_state import load_state, save_state, set_ticket_state
            from prompt_builder import build_rework_prompt
            from copilot_bridge import invoke_agent

            # Obtener workspace y agente DEV
            ws_root = self._get_workspace_root() or ""
            agents  = self._get_agents()
            dev_agent = agents.get("dev", "DevStack3")

            prompt = build_rework_prompt(folder, ticket_id, ws_root,
                                         qa_findings, rework_num)

            # Registrar rework en state
            state = load_state(self._state_path)
            entry = state.setdefault("tickets", {}).setdefault(ticket_id, {})
            entry["rework_count"] = rework_num
            entry["rework_inicio_at"] = __import__("datetime").datetime.now().isoformat()
            set_ticket_state(state, ticket_id, "dev_rework_en_proceso", folder=folder)
            save_state(self._state_path, state)

            # Lanzar agente DEV para rework
            # Eliminar TESTER_COMPLETADO.md para que QA re-valide
            tester_flag = os.path.join(folder, "TESTER_COMPLETADO.md")
            if os.path.exists(tester_flag):
                os.rename(tester_flag, tester_flag + ".prev")

            invoke_agent(dev_agent, prompt, workspace=ws_root)
            logger.info("[REWORK] Agente DEV invocado para rework de %s", ticket_id)
        except Exception as e:
            logger.error("[REWORK] Error lanzando rework para %s: %s", ticket_id, e)

    def _get_agents(self) -> dict:
        """Retorna la configuración de agentes del proyecto activo."""
        try:
            from project_manager import get_active_project, get_project_config
            proj = get_active_project()
            cfg  = get_project_config(proj) or {}
            return cfg.get("agents", {})
        except Exception:
            return {}

    def _get_active_project(self) -> str:
        """Retorna el nombre del proyecto activo."""
        try:
            from project_manager import get_active_project
            return get_active_project()
        except Exception:
            return ""

    def _get_workspace_root(self) -> str | None:
        """Intenta obtener el workspace root del proyecto activo."""
        try:
            from project_manager import get_active_project, get_project_config
            proj = get_active_project()
            cfg  = get_project_config(proj) or {}
            return cfg.get("workspace_root")
        except Exception:
            return None

    def _advance_state(self, ticket_id: str, new_state: str, folder: str) -> None:
        """Actualiza el pipeline_state.json con el nuevo estado del ticket."""
        try:
            from pipeline_state import load_state, save_state, set_ticket_state
            state = load_state(self._state_path)
            set_ticket_state(state, ticket_id, new_state, folder=folder)
            save_state(self._state_path, state)
            logger.debug("[WATCHER] State actualizado: %s → %s", ticket_id, new_state)
        except Exception as e:
            logger.error("[WATCHER] Error actualizando state para %s: %s", ticket_id, e)
