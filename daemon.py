"""
daemon.py — Orquestador siempre activo del Mantis Scraper.

Reemplaza el modelo de "ejecutar dos scripts manualmente" con un proceso
continuo que:
  1. Scrapea Mantis cada N minutos para detectar tickets nuevos
  2. Detecta automáticamente tickets en estado "asignada" y lanza el pipeline
  3. Monitorea timeouts por etapa y reintenta o marca error
  4. Verifica la sesión SSO y notifica cuando necesita renovación
  5. Archiva tickets completados más de N días atrás
  6. Envía notificaciones de escritorio en eventos clave

Uso:
    python daemon.py --project RIPLEY --interval 15
    python daemon.py --project RIPLEY --scrape-only
    python daemon.py --project RIPLEY --pipeline-only
    python daemon.py --list-projects
"""

import argparse
import json
import logging
import logging.handlers
import os
import shutil
import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

# ── Rutas base ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Forzar stdout a UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Logger del módulo ─────────────────────────────────────────────────────────
logger = logging.getLogger("mantis.daemon")

try:
    from stacky_log import slog as _slog
except ImportError:
    _slog = None


def _setup_logging(verbose: bool = False, log_file: str = None) -> None:
    """
    Configura el sistema de logging del daemon.
    - Consola: INFO (o DEBUG si verbose)
    - Archivo: DEBUG siempre, rotación a 5MB × 3 backups
    """
    root = logging.getLogger("mantis")
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de consola
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Handler de archivo (con rotación)
    log_path = log_file or os.path.join(BASE_DIR, "daemon.log")
    try:
        fh = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        logger.debug("Log en archivo: %s", log_path)
    except Exception as e:
        logger.warning("No se pudo abrir log file '%s': %s", log_path, e)


# ── Configuración por defecto ─────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "scrape_interval_minutes":  15,
    "auto_pipeline":            True,
    "ticket_states_to_process": ["asignada"],
    "cleanup_after_days":       30,
    "timeout_pm_minutes":       60,
    "timeout_dev_minutes":      120,
    "timeout_tester_minutes":   60,
    "max_retries_per_stage":    2,
    "session_max_age_hours":    8.0,
}


def _load_project_daemon_config(project_name: str) -> dict:
    """Carga el bloque 'daemon' de config del proyecto, aplicando defaults."""
    cfg = dict(DEFAULT_CONFIG)
    try:
        from project_manager import get_project_config
        project_cfg = get_project_config(project_name) or {}
        daemon_cfg  = project_cfg.get("daemon", {})
        cfg.update(daemon_cfg)
    except Exception as e:
        print(f"[DAEMON] No se pudo cargar config de proyecto: {e}")
    return cfg


# ── Clase principal ───────────────────────────────────────────────────────────

class MantisScraperDaemon:
    """
    Daemon siempre activo que orquesta scraping y pipeline automáticamente.
    """

    def __init__(self, project_name: str, scrape_interval_minutes: int = None,
                 auto_pipeline: bool = True, scrape_only: bool = False,
                 pipeline_only: bool = False, verbose: bool = False,
                 dry_run: bool = False):
        self.project_name   = project_name
        self.scrape_only    = scrape_only
        self.pipeline_only  = pipeline_only
        self.verbose        = verbose
        self.dry_run        = dry_run

        # Cargar config del proyecto
        self._cfg = _load_project_daemon_config(project_name)
        if scrape_interval_minutes is not None:
            self._cfg["scrape_interval_minutes"] = scrape_interval_minutes
        if not auto_pipeline:
            self._cfg["auto_pipeline"] = False

        # Resolución de paths
        try:
            from project_manager import get_project_paths
            paths = get_project_paths(project_name)
        except Exception:
            paths = {
                "tickets": os.path.join(BASE_DIR, "tickets"),
                "state":   os.path.join(BASE_DIR, "pipeline", "state.json"),
            }
        self._tickets_base  = paths["tickets"]
        self._state_path    = paths["state"]
        self._auth_path     = os.path.join(BASE_DIR, "auth", "auth.json")

        try:
            from project_manager import get_project_config
            pcfg = get_project_config(project_name) or {}
            self._mantis_url = pcfg.get("mantis_url", "")
            if not self._mantis_url:
                # Fallback al config.json global
                with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
                    gcfg = json.load(f)
                self._mantis_url = gcfg.get("mantis_url", "")
        except Exception:
            self._mantis_url = ""

        self._renewal_in_progress = False
        self._last_cleanup_date   = None

        # N-05: Monitor de escaladas
        try:
            from mantis_change_monitor import MantisChangeMonitor
            self._change_monitor = MantisChangeMonitor(
                tickets_base=self._tickets_base,
                state_path=self._state_path,
                notifier=None,  # se inyecta después de crear el notifier
            )
        except ImportError:
            self._change_monitor = None

        # Pre-importar módulos usados frecuentemente (evita re-import en cada ciclo)
        from notifier import Notifier
        from pipeline_state import (load_state, save_state, set_ticket_state,
                                     mark_error, get_ticket_priority,
                                     is_stage_timed_out, get_retry_count)
        from ticket_detector import get_processable_tickets

        self._notifier = Notifier(app_name=f"Mantis Scraper — {project_name}")
        if self._change_monitor:
            self._change_monitor._notifier = self._notifier

        # N-08: Métricas de calidad
        try:
            from metrics_collector import get_metrics_collector
            self._metrics = get_metrics_collector(project_name)
        except ImportError:
            self._metrics = None

        # N-07: Shadow mode
        try:
            from shadow_mode import get_shadow_mode
            self._shadow = get_shadow_mode(project_name)
        except ImportError:
            self._shadow = None

        # G-06: Memoria de agentes
        try:
            from memory_manager import get_agent_memory
            self._agent_memory = get_agent_memory(project_name)
        except ImportError:
            self._agent_memory = None

        # G-03: Oracle schema injector
        oracle_conn = self._project_cfg.get("oracle_connection_string", "")
        try:
            from oracle_schema_injector import get_schema_injector
            self._schema_injector = get_schema_injector(oracle_conn)
        except ImportError:
            self._schema_injector = None

        # M-06: Agent queue (pipeline lanes)
        slots = self._project_cfg.get("agent_slots", {})
        try:
            from agent_queue import get_agent_queue
            self._agent_queue = get_agent_queue(
                slots_pm=slots.get("pm", 1),
                slots_dev=slots.get("dev", 1),
                slots_tester=slots.get("tester", 1),
            )
        except ImportError:
            self._agent_queue = None

        # E-04: Prompt tracker
        try:
            from prompt_tracker import get_prompt_tracker
            self._prompt_tracker = get_prompt_tracker(project_name)
        except ImportError:
            self._prompt_tracker = None

        # E-03: Grafo de dependencias
        try:
            from dependency_graph import get_dependency_graph
            self._dep_graph = get_dependency_graph(self._tickets_base, project_name)
        except ImportError:
            self._dep_graph = None

        # E-07: Monitor de regresiones
        try:
            from regression_monitor import RegressionMonitor
            self._regression_monitor = RegressionMonitor(
                self._tickets_base, project_name, self._notifier)
        except ImportError:
            self._regression_monitor = None

        # G-02: Codebase indexer (lazy — indexar en background al iniciar)
        try:
            from codebase_indexer import get_codebase_indexer
            self._codebase_indexer = get_codebase_indexer(self._ws_root, project_name)
            # Indexar en background si el índice no existe
            import threading as _t
            _t.Thread(
                target=self._codebase_indexer.build_index,
                daemon=True, name="codebase-indexer-startup"
            ).start()
        except ImportError:
            self._codebase_indexer = None

        # G-09: Autonomy controller
        try:
            from autonomy_controller import AutonomyController
            self._autonomy = AutonomyController(project_name, self._notifier)
        except ImportError:
            self._autonomy = None

        # G-08: Multi-agent deliberator
        try:
            from multi_agent_deliberator import MultiAgentDeliberator
            self._deliberator = MultiAgentDeliberator(project_name)
        except ImportError:
            self._deliberator = None
        self._ps = type("PS", (), {
            "load_state": staticmethod(load_state),
            "save_state": staticmethod(save_state),
            "set_ticket_state": staticmethod(set_ticket_state),
            "mark_error": staticmethod(mark_error),
            "get_ticket_priority": staticmethod(get_ticket_priority),
            "is_stage_timed_out": staticmethod(is_stage_timed_out),
            "get_retry_count": staticmethod(get_retry_count),
        })()
        self._get_processable_tickets = get_processable_tickets

        # Cachear config de proyecto (agents, workspace) — cambia muy raramente
        try:
            from project_manager import get_project_config
            self._project_cfg = get_project_config(project_name) or {}
        except Exception:
            self._project_cfg = {}
        self._agents  = self._project_cfg.get("agents", {"pm": "PM-TL STack 3", "dev": "DevStack3", "tester": "QA"})
        self._ws_root = self._project_cfg.get("workspace_root",
                                               os.path.abspath(os.path.join(BASE_DIR, "..", "..")))

        self._log(f"Iniciando daemon para proyecto: {project_name}")
        self._log(f"Interval: {self._cfg['scrape_interval_minutes']} min | "
                  f"Auto-pipeline: {self._cfg['auto_pipeline']} | "
                  f"Timeout PM/Dev/QA: {self._cfg['timeout_pm_minutes']}/"
                  f"{self._cfg['timeout_dev_minutes']}/"
                  f"{self._cfg['timeout_tester_minutes']} min")

    # ── Loop principal ────────────────────────────────────────────────────

    def run(self):
        """Loop principal — no termina hasta Ctrl+C o señal de parada."""
        self._log("Daemon iniciado. Ctrl+C para detener.")
        interval_sec = self._cfg["scrape_interval_minutes"] * 60

        # Iniciar watcher de filesystem (avance inmediato al detectar flags)
        watcher = self._start_watcher()

        try:
            while True:
                cycle_start = time.time()
                try:
                    if not self.pipeline_only:
                        self._session_check()
                        self._scrape_cycle()

                    if self._cfg["auto_pipeline"] and not self.scrape_only:
                        self._pipeline_cycle()

                    self._cleanup_cycle()

                except KeyboardInterrupt:
                    self._log("Daemon detenido por el usuario.")
                    break
                except Exception as e:
                    self._log(f"[ERROR] Ciclo fallido: {e}", level="error")
                    self._notifier.send(
                        "Error en ciclo del daemon",
                        str(e)[:200],
                        level="error",
                    )

                elapsed = time.time() - cycle_start
                sleep_sec = max(0, interval_sec - elapsed)
                if sleep_sec > 0:
                    self._log(f"Ciclo completado en {elapsed:.0f}s. Próximo en {sleep_sec/60:.1f} min.")
                    time.sleep(sleep_sec)
        finally:
            if watcher:
                watcher.stop()

    def _start_watcher(self):
        """Inicia el PipelineWatcher para avance inmediato sin esperar el ciclo."""
        if self.dry_run or self.scrape_only:
            return None
        try:
            from pipeline_watcher import PipelineWatcher

            def _on_advance(ticket_id, stage_done, new_state, folder):
                self._log(f"[WATCHER] {ticket_id}: {stage_done} → {new_state} — "
                          f"lanzando siguiente etapa")
                self._notifier.notify_ticket_ready(ticket_id, stage_done)

                # N-08: Registrar fin de etapa exitosa en métricas
                if self._metrics:
                    completed_stage = {"pm_completado": "pm", "dev_completado": "dev",
                                       "tester_completado": "tester"}.get(new_state)
                    if completed_stage:
                        self._metrics.record_stage_end(ticket_id, completed_stage,
                                                       success=True)

                # G-05: Blast radius analysis + G-04: Tests post-DEV
                if new_state == "dev_completado":
                    try:
                        from blast_radius_analyzer import analyze_blast_radius
                        threading.Thread(
                            target=analyze_blast_radius,
                            args=(folder, ticket_id, self._ws_root),
                            daemon=True,
                            name=f"blast-{ticket_id}",
                        ).start()
                    except ImportError:
                        pass
                    try:
                        from test_runner import run_post_dev_tests
                        threading.Thread(
                            target=run_post_dev_tests,
                            args=(folder, ticket_id, self._ws_root),
                            daemon=True,
                            name=f"tests-{ticket_id}",
                        ).start()
                    except ImportError:
                        pass

                # Lanzar la siguiente etapa inmediatamente
                next_stage_map = {"pm_completado": "dev", "dev_completado": "tester",
                                  "tester_completado": None}
                next_stage    = next_stage_map.get(new_state)
                _lock_blocked = False
                if next_stage:
                    # ── Guardia watcher: evita disparar si ya hay lock activo ──
                    try:
                        from pipeline_lock import is_locked as _watcher_is_locked
                        if _watcher_is_locked(ticket_id, next_stage):
                            self._log(
                                f"[WATCHER] {ticket_id}/{next_stage} — lock activo, "
                                f"otra instancia ya está ejecutando esta etapa",
                                level="warning",
                            )
                            _lock_blocked = True
                    except ImportError:
                        pass

                if next_stage and not _lock_blocked:
                    # Marcar como en_proceso ANTES de lanzar el thread para que
                    # _pipeline_cycle no lo relance en el siguiente ciclo.
                    try:
                        from pipeline_state import load_state, save_state, set_ticket_state
                        _state = load_state(self._state_path)
                        set_ticket_state(_state, ticket_id, f"{next_stage}_en_proceso",
                                         folder=folder)
                        import datetime as _dt
                        _state["tickets"][ticket_id][f"{next_stage}_inicio_at"] = (
                            _dt.datetime.now().isoformat()
                        )
                        save_state(self._state_path, _state)
                    except Exception as _se:
                        self._log(f"[WATCHER] No se pudo actualizar state para {ticket_id}: {_se}",
                                  level="warning")
                    threading.Thread(
                        target=self._launch_stage,
                        args=(ticket_id, next_stage, folder),
                        daemon=True,
                        name=f"watcher-{ticket_id}-{next_stage}",
                    ).start()
                elif new_state == "tester_completado":
                    # Pipeline completo
                    self._notifier.notify_ticket_completed(ticket_id)
                    # N-06: extraer y guardar patrón de solución
                    try:
                        from pattern_extractor import extract_and_store_pattern
                        threading.Thread(
                            target=extract_and_store_pattern,
                            args=(folder, ticket_id, self.project_name),
                            daemon=True,
                            name=f"pattern-{ticket_id}",
                        ).start()
                    except ImportError:
                        pass
                    # E-01: Indexar en knowledge base
                    try:
                        from knowledge_base import get_kb
                        threading.Thread(
                            target=lambda: get_kb(
                                self._tickets_base, self.project_name
                            ).add_ticket(ticket_id, folder),
                            daemon=True,
                            name=f"kb-{ticket_id}",
                        ).start()
                    except ImportError:
                        pass
                    # G-06: Extraer hechos para la memoria de agentes
                    if self._agent_memory:
                        threading.Thread(
                            target=self._agent_memory.extract_facts_from_ticket,
                            args=(folder, ticket_id),
                            daemon=True,
                            name=f"memory-{ticket_id}",
                        ).start()
                    # E-07: Registrar en monitor de regresiones
                    if self._regression_monitor:
                        threading.Thread(
                            target=self._regression_monitor.watch_ticket,
                            args=(ticket_id, folder),
                            daemon=True,
                            name=f"regression-{ticket_id}",
                        ).start()
                    # E-02: Actualizar Mantis con nota de resolución
                    if self._mantis_url:
                        try:
                            from mantis_updater import update_ticket_on_mantis
                            resolve = self._cfg.get("mantis_auto_resolve", False)
                            threading.Thread(
                                target=update_ticket_on_mantis,
                                args=(ticket_id, folder, self._mantis_url,
                                      self._auth_path),
                                kwargs={"resolve_status": resolve},
                                daemon=True,
                                name=f"mantis-upd-{ticket_id}",
                            ).start()
                        except ImportError:
                            pass

            def _on_error(ticket_id, error_stage, reason, folder):
                self._log(f"[WATCHER] {ticket_id}: error en {error_stage}: {reason[:80]}",
                          level="warning")
                self._handle_error_flag(
                    ticket_id, error_stage, reason, folder,
                    self._ps.load_state(self._state_path)
                )

            watcher = PipelineWatcher(
                tickets_base=self._tickets_base,
                state_path=self._state_path,
                on_advance=_on_advance,
                on_error=_on_error,
            )
            watcher.start()
            return watcher
        except Exception as e:
            self._log(f"[WATCHER] No se pudo iniciar: {e}", level="warning")
            return None

    # ── Ciclo de scraping ─────────────────────────────────────────────────

    def _scrape_cycle(self):
        """Ejecuta el scraper de Mantis y registra tickets nuevos."""
        self._log("--- Inicio ciclo de scraping ---")
        if self.dry_run:
            self._log("[DRY-RUN] Scraping omitido — modo simulación activo")
            return
        try:
            from mantis_scraper import run_scraper
            from session_manager import SessionExpiredError
            run_scraper(project_name=self.project_name)
        except Exception as exc:
            # SessionExpiredError ya fue manejada en _session_check
            err_msg = str(exc)
            if "SessionExpiredError" in type(exc).__name__ or "sesión" in err_msg.lower():
                self._log(f"[SCRAPE] Sesión expirada: {exc}", level="warning")
                self._notifier.notify_session_expiring(self.project_name)
            else:
                self._log(f"[SCRAPE] Error: {exc}", level="error")
                raise

        # N-05: Detectar escaladas en tickets activos después de cada scraping
        if self._change_monitor:
            try:
                events = self._change_monitor.check_for_escalations(self.project_name)
                for ev in events:
                    self._log(f"[ESCALATION] Ticket #{ev.ticket_id} escalado — {ev.reason}",
                              level="warning")
                    self._notifier.send(
                        title=f"Escalada detectada — Ticket #{ev.ticket_id}",
                        message=f"{ev.reason} → prioridad {ev.new_priority}",
                        level="warning",
                        ticket_id=ev.ticket_id,
                    )
            except Exception as e:
                self._log(f"[ESCALATION] Error en monitor: {e}", level="debug")

    # ── Ciclo de pipeline ─────────────────────────────────────────────────

    def _pipeline_cycle(self):
        """Detecta tickets nuevos y lanza agentes para cada etapa pendiente."""
        ps = self._ps
        state   = ps.load_state(self._state_path)
        estados = self._cfg.get("ticket_states_to_process", ["asignada"])

        tickets = self._get_processable_tickets(
            self._tickets_base, state,
            estados_procesables=estados,
        )

        if not tickets:
            self._log("[PIPELINE] Sin tickets procesables en este ciclo")
            return

        # Ordenar por prioridad (auto o manual)
        tickets.sort(key=lambda t: ps.get_ticket_priority(state, t["ticket_id"]))

        self._log(f"[PIPELINE] {len(tickets)} ticket(s) procesable(s)")

        if self.dry_run:
            for t in tickets:
                tid   = t["ticket_id"]
                stage = self._next_stage(
                    state.get("tickets", {}).get(tid, {}).get("estado", "pendiente_pm")
                )
                err_stage = t.get("error_stage")
                tag = f"[ERROR {err_stage}→fix]" if err_stage else f"[{stage}]"
                self._log(f"[DRY-RUN] {tid} {tag} — {t['folder']}")
            return

        for t in tickets:
            tid    = t["ticket_id"]
            folder = t["folder"]
            est    = state.get("tickets", {}).get(tid, {}).get("estado", "pendiente_pm")

            # ── Manejo automático de error flags ────────────────────────────
            # Si el agente dejó PM_ERROR.flag / DEV_ERROR.flag / TESTER_ERROR.flag,
            # lanzar un prompt de corrección con el contexto del error.
            err_stage  = t.get("error_stage")
            err_reason = t.get("error_reason", "")
            if err_stage and err_reason:
                self._log(f"[PIPELINE] {tid} → error flag '{err_stage.upper()}_ERROR.flag' "
                          f"detectado — lanzando fix prompt")
                self._handle_error_flag(tid, err_stage, err_reason, folder, state)
                continue

            # Determinar qué etapa lanzar
            stage = self._next_stage(est)
            if not stage:
                continue

            # E-05: Pre-filtro sin IA antes de lanzar PM (solo en primera pasada)
            if stage == "pm" and est == "pendiente_pm":
                try:
                    from pre_filter import pre_filter_ticket, load_filter_result
                    existing = load_filter_result(folder)
                    if existing is None:
                        fr = pre_filter_ticket(folder, tid,
                                               self._tickets_base, self._ws_root)
                    else:
                        fr = existing
                    if fr.should_skip:
                        self._log(f"[PRE-FILTER] {tid} → SKIP ({fr.category}): {fr.reason[:80]}",
                                  level="warning")
                        self._notifier.send(
                            title=f"Ticket #{tid} omitido automáticamente",
                            message=f"{fr.category}: {fr.reason[:100]}",
                            level="warning",
                            ticket_id=tid,
                        )
                        continue
                except ImportError:
                    pass
                except Exception as e:
                    self._log(f"[PRE-FILTER] Error: {e}", level="debug")

                # M-07: Clasificar complejidad y ajustar timeouts
                try:
                    from ticket_classifier import classify_ticket
                    score = classify_ticket(folder, tid)
                    self._log(f"[CLASSIFIER] {score.summary()}")
                    # Ajustar timeouts para este ticket en el ciclo actual
                    self._cfg[f"_timeout_pm_{tid}"]     = score.recommended_pm_timeout
                    self._cfg[f"_timeout_dev_{tid}"]    = score.recommended_dev_timeout
                    self._cfg[f"_timeout_tester_{tid}"] = score.recommended_tester_timeout
                except ImportError:
                    pass
                except Exception as e:
                    self._log(f"[CLASSIFIER] Error: {e}", level="debug")

            # Verificar timeout si ya está en proceso
            if est.endswith("_en_proceso"):
                stage_name = est.replace("_en_proceso", "")
                timeout    = self._cfg.get(f"timeout_{stage_name}_minutes",
                                           DEFAULT_CONFIG.get(f"timeout_{stage_name}_minutes", 60))
                if ps.is_stage_timed_out(state, tid, stage_name, timeout):
                    retries = ps.get_retry_count(state, tid, stage_name)
                    max_r   = self._cfg["max_retries_per_stage"]
                    if retries >= max_r:
                        reason = (f"Timeout {timeout}min — {retries} reintentos agotados")
                        ps.mark_error(state, tid, stage_name, reason)
                        ps.save_state(self._state_path, state)
                        self._notifier.notify_action_needed(tid, reason)
                        self._log(f"[PIPELINE] {tid} → error por timeout en {stage_name}")
                    else:
                        self._log(f"[PIPELINE] {tid} timeout en {stage_name} "
                                  f"→ reintento {retries+1}/{max_r}")
                        state["tickets"][tid][f"{stage_name}_inicio_at"] = datetime.now().isoformat()
                        ps.save_state(self._state_path, state)
                        self._launch_stage(tid, stage_name, folder,
                                           retry_num=retries + 1)
                continue  # Ya está en proceso

            # E-03: Actualizar grafo de dependencias
            if self._dep_graph and stage == "pm":
                try:
                    self._dep_graph.update_ticket(tid, folder)
                except Exception:
                    pass

            # ── Guardia secundaria: lock activo → skip (la primaria está en _launch_stage)
            try:
                from pipeline_lock import is_locked as _is_locked
                if _is_locked(tid, stage):
                    self._log(
                        f"[PIPELINE] {tid}/{stage} — lock activo detectado en ciclo, "
                        f"esperando a que termine la instancia en curso",
                        level="debug",
                    )
                    continue
            except ImportError:
                pass

            # Lanzar etapa en thread para no bloquear el loop
            self._log(f"[PIPELINE] {tid} → lanzando etapa '{stage}'")
            ps.set_ticket_state(state, tid, f"{stage}_en_proceso",
                                folder=folder, auto_advance=True)
            state["tickets"][tid][f"{stage}_inicio_at"] = datetime.now().isoformat()
            ps.save_state(self._state_path, state)
            threading.Thread(
                target=self._launch_stage,
                args=(tid, stage, folder),
                daemon=True,
                name=f"pipeline-{tid}-{stage}",
            ).start()

    def _next_stage(self, estado: str) -> str | None:
        """Retorna la próxima etapa a lanzar según el estado del ticket."""
        stage_map = {
            "pendiente_pm":  "pm",
            "pm_completado": "dev",
            "dev_completado": "tester",
        }
        return stage_map.get(estado)

    def _handle_error_flag(self, ticket_id: str, err_stage: str, err_reason: str,
                            folder: str, state: dict) -> None:
        """
        Cuando un agente dejó un error flag (PM_ERROR.flag, DEV_ERROR.flag, etc.),
        construye un prompt de corrección con el contexto del error y lo lanza
        en un thread. Limpia el flag después de procesarlo para no re-procesar.
        """
        ps       = self._ps
        retries  = ps.get_retry_count(state, ticket_id, err_stage)
        max_r    = self._cfg["max_retries_per_stage"]

        if retries >= max_r:
            reason = f"Error en {err_stage} — {max_r} reintentos agotados: {err_reason[:100]}"
            ps.mark_error(state, ticket_id, err_stage, reason)
            ps.save_state(self._state_path, state)
            self._notifier.notify_action_needed(ticket_id, reason)
            self._log(f"[PIPELINE] {ticket_id} → {err_stage} agotó reintentos", level="warning")
            return

        self._log(f"[PIPELINE] {ticket_id} → lanzando fix de {err_stage} "
                  f"(reintento {retries+1}/{max_r})")

        # Renombrar/borrar el ERROR flag para que no se reprocese en el próximo ciclo
        error_flag_path = os.path.join(folder, f"{err_stage.upper()}_ERROR.flag")
        try:
            os.rename(error_flag_path,
                      os.path.join(folder, f"{err_stage.upper()}_ERROR.flag.{retries+1}.bak"))
        except Exception:
            pass

        # Limpiar el flag de COMPLETADO previo — es CRÍTICO para el polling:
        # si no se borra, el polling (que usa mtime) no detecta el nuevo flag
        # cuando el agente vuelve a escribirlo al completar el retry.
        done_flag_map = {"pm": "PM_COMPLETADO.flag",
                         "dev": "DEV_COMPLETADO.md",
                         "tester": "TESTER_COMPLETADO.md"}
        done_flag = done_flag_map.get(err_stage)
        if done_flag:
            done_flag_path = os.path.join(folder, done_flag)
            if os.path.exists(done_flag_path):
                try:
                    os.rename(done_flag_path,
                              os.path.join(folder, f"{done_flag}.{retries+1}.bak"))
                    self._log(f"[PIPELINE] {ticket_id} → {done_flag} renombrado a .bak "
                              f"para limpiar estado antes del retry")
                except Exception as e:
                    self._log(f"[PIPELINE] {ticket_id} → no se pudo renombrar {done_flag}: {e}",
                              level="warning")

        # Incrementar contador de reintentos en el estado
        key = f"intentos_{err_stage}"
        if ticket_id not in state["tickets"]:
            state["tickets"][ticket_id] = {}
        state["tickets"][ticket_id][key] = retries + 1
        state["tickets"][ticket_id][f"{err_stage}_inicio_at"] = datetime.now().isoformat()
        ps.save_state(self._state_path, state)

        if _slog:
            _slog.stage_error(ticket_id, err_stage, err_reason,
                              retry_num=retries + 1, max_retries=max_r)
        threading.Thread(
            target=self._launch_stage,
            args=(ticket_id, err_stage, folder),
            kwargs={"retry_num": retries + 1, "error_context": err_reason},
            daemon=True,
            name=f"fix-{ticket_id}-{err_stage}",
        ).start()

    def _launch_stage(self, ticket_id: str, stage: str, folder: str,
                      retry_num: int = 0, error_context: str = None):
        """Invoca el agente para una etapa (fire-and-forget, sin UI fallback)."""
        # ── LOCK: evita ejecuciones paralelas del mismo stage+ticket ────────────
        # Protege contra: daemon + watcher, dos ciclos solapados, dashboard + daemon.
        # File-based → funciona incluso entre procesos distintos.
        try:
            from pipeline_lock import acquire_lock, release_lock
        except ImportError:
            acquire_lock = release_lock = None

        _lock_run_id = None
        if acquire_lock:
            _lock_run_id = acquire_lock(ticket_id, stage)
            if _lock_run_id is None:
                # Otro thread/proceso ya tiene este stage corriendo → skip
                self._log(
                    f"[LOCK] {ticket_id}/{stage} ya en ejecución (lock activo) — "
                    f"invocación duplicada ignorada",
                    level="warning",
                )
                if _slog:
                    _slog.info(ticket_id, "lock",
                               f"Stage {stage} tiene lock activo — duplicado evitado")
                return
        # ── FIN LOCK ─────────────────────────────────────────────────────────────

        if _slog:
            _slog.stage_start(ticket_id, stage, retry=retry_num)
        try:
            from copilot_bridge import invoke_agent
            from prompt_builder import (build_pm_prompt, build_dev_prompt,
                                        build_tester_prompt, build_retry_prompt,
                                        build_error_fix_prompt)

            ps       = self._ps
            agent    = self._agents.get(stage, stage)

            # Usar prompt especializado si es un reintento o viene de un error flag
            if error_context:
                prompt = build_error_fix_prompt(folder, ticket_id, self._ws_root,
                                                stage, error_context)
            elif retry_num > 0:
                prompt = build_retry_prompt(folder, ticket_id, self._ws_root,
                                            stage, retry_num=retry_num)
            else:
                builders = {"pm": build_pm_prompt, "dev": build_dev_prompt,
                            "tester": build_tester_prompt}
                prompt = builders[stage](folder, ticket_id, self._ws_root)
                # N-06 + E-01: Inyectar patrones y KB similares en prompt PM
                if stage == "pm":
                    try:
                        from pathlib import Path as _Path
                        inc_content = _Path(
                            os.path.join(folder, f"INC-{ticket_id}.md")
                        ).read_text(encoding="utf-8", errors="replace")
                        # Patrones de solución conocidos
                        try:
                            from pattern_extractor import (get_relevant_patterns,
                                                           format_patterns_section)
                            patterns    = get_relevant_patterns(inc_content,
                                                                self.project_name, top_k=3)
                            patterns_md = format_patterns_section(patterns)
                            if patterns_md:
                                prompt += "\n" + patterns_md
                        except Exception:
                            pass
                        # Knowledge Base RAG
                        try:
                            from knowledge_base import get_kb
                            kb      = get_kb(self._tickets_base, self.project_name)
                            results = kb.search(inc_content, k=3)
                            kb_md   = kb.format_kb_section(results)
                            if kb_md:
                                prompt += "\n" + kb_md
                        except Exception:
                            pass
                        # G-06: Memoria de agentes
                        if self._agent_memory:
                            try:
                                mem_md = self._agent_memory.format_memory_section()
                                if mem_md:
                                    prompt += "\n" + mem_md
                            except Exception:
                                pass
                        # G-03: Schema Oracle
                        if self._schema_injector:
                            try:
                                schema_md = self._schema_injector.build_schema_section(
                                    folder, ticket_id)
                                if schema_md:
                                    prompt += "\n" + schema_md
                            except Exception:
                                pass
                    except Exception:
                        pass

                # G-10: Predicción IA en prompt PM
                if stage == "pm":
                    try:
                        from predictor import get_predictor
                        from pathlib import Path as _Path2
                        _inc = _Path2(
                            os.path.join(folder, f"INC-{ticket_id}.md")
                        ).read_text(encoding="utf-8", errors="replace")
                        pred   = get_predictor(self.project_name)
                        result = pred.predict(_inc)
                        pred_md = pred.format_prediction_section(result)
                        if pred_md:
                            prompt += "\n" + pred_md
                    except Exception:
                        pass

                # G-08: Multi-agent deliberation para tickets complejos
                if stage == "pm" and self._deliberator:
                    try:
                        if self._deliberator.should_deliberate(folder, ticket_id):
                            self._log(f"[DELIBERATION] Ticket #{ticket_id} es complejo → "
                                      f"activando deliberación multi-agente")
                            prompts = self._deliberator.build_deliberation_prompts(
                                folder, ticket_id, prompt)
                            # Usar el primer prompt (perspectiva técnica) como prompt principal
                            # Los otros 2 serán lanzados en threads separados
                            if prompts:
                                prompt = prompts[0]["prompt"]
                    except Exception:
                        pass

                # E-06: Contexto semántico en prompt DEV
                if stage == "dev":
                    try:
                        from semantic_context import SemanticContextExtractor
                        sce = SemanticContextExtractor()
                        ctx = sce.extract_for_ticket(folder, ticket_id, self._ws_root)
                        sem_md = sce.format_semantic_section(ctx)
                        if sem_md:
                            prompt += "\n" + sem_md
                    except Exception:
                        pass

                # E-03: Inyectar conflictos de dependencias en PM
                if stage == "pm" and self._dep_graph:
                    try:
                        conflict_md = self._dep_graph.format_conflict_report(ticket_id)
                        if conflict_md:
                            prompt += "\n" + conflict_md
                    except Exception:
                        pass

                # G-03: Schema Oracle también en prompt DEV
                if stage == "dev" and self._schema_injector:
                    try:
                        schema_md = self._schema_injector.build_schema_section(
                            folder, ticket_id)
                        if schema_md:
                            prompt += "\n" + schema_md
                    except Exception:
                        pass

                # N-07: Shadow mode — envolver prompt DEV
                if stage == "dev" and self._shadow and self._shadow.is_enabled():
                    try:
                        prompt = self._shadow.wrap_dev_prompt(prompt)
                        self._log(f"[SHADOW] Prompt DEV de #{ticket_id} envuelto en shadow mode")
                    except Exception:
                        pass

            # N-08: Registrar inicio de etapa en métricas
            if self._metrics:
                self._metrics.record_stage_start(ticket_id, stage)

            # E-04: Registrar prompt para tracking
            prompt_hash = None
            if self._prompt_tracker:
                try:
                    prompt_hash = self._prompt_tracker.record_prompt(
                        ticket_id, stage, prompt)
                except Exception:
                    pass

            ok = invoke_agent(prompt, agent_name=agent,
                              project_name=self.project_name,
                              workspace_root=self._ws_root,
                              allow_ui_fallback=False,
                              new_conversation=(stage == "pm"))

            if _slog:
                _slog.invoke_result(ticket_id, stage, ok,
                                    method="bridge_http" if ok else "failed")

            if not ok:
                reason = f"Bridge HTTP no disponible para {stage} — VS Code no responde"
                state = ps.load_state(self._state_path)
                ps.mark_error(state, ticket_id, stage, reason)
                ps.save_state(self._state_path, state)
                self._notifier.notify_action_needed(
                    ticket_id,
                    f"Bridge VS Code no disponible — abrir VS Code y reintentar {stage}"
                )
                self._log(f"[PIPELINE] {ticket_id} → bridge no disponible para {stage}", level="warning")
                if _slog:
                    _slog.error(ticket_id, "bridge",
                                f"invoke_agent retornó False para {stage}. "
                                f"¿VS Code está abierto con la extensión bridge activa en :{5051}?")
                if self._metrics:
                    self._metrics.record_stage_end(ticket_id, stage, success=False,
                                                   retry_num=retry_num)
                if self._prompt_tracker and prompt_hash:
                    try:
                        self._prompt_tracker.record_outcome(prompt_hash, success=False)
                    except Exception:
                        pass
            else:
                self._log(f"[PIPELINE] {ticket_id} → agente {agent} invocado para {stage}")
                if _slog:
                    _slog.info(ticket_id, "agent",
                               f"Agente '{agent}' invocado para {stage} "
                               f"(prompt {len(prompt)} chars)")

        except Exception as e:
            self._log(f"[PIPELINE] Error invocando {stage} para {ticket_id}: {e}", level="error")
            if _slog:
                _slog.error(ticket_id, "agent",
                            f"Excepción al invocar {stage}: {type(e).__name__}: {e}")
            try:
                ps = self._ps
                state = ps.load_state(self._state_path)
                ps.mark_error(state, ticket_id, stage, str(e))
                ps.save_state(self._state_path, state)
            except Exception:
                pass
        finally:
            # Liberar el lock siempre — tanto en éxito como en error/excepción
            if release_lock and _lock_run_id:
                release_lock(ticket_id, stage, _lock_run_id)

    # ── Verificación de sesión ────────────────────────────────────────────

    def _session_check(self):
        """Verifica la sesión SSO y dispara renovación si es necesaria."""
        if self._renewal_in_progress:
            return
        if not self._mantis_url:
            return

        try:
            from session_manager import SessionManager
            sm = SessionManager(self._auth_path, self._mantis_url)
            if sm.needs_renewal(max_age_hours=self._cfg["session_max_age_hours"]):
                self._log("[SESSION] Sesión necesita renovación", level="warning")
                self._renewal_in_progress = True
                self._notifier.notify_session_expiring(self.project_name)

                def _on_complete(success: bool):
                    self._renewal_in_progress = False
                    if success:
                        self._log("[SESSION] Renovación completada")
                    else:
                        self._log("[SESSION] Renovación falló — scraping pausado", level="error")

                sm.prompt_renewal_async(on_complete=_on_complete)
        except Exception as e:
            self._log(f"[SESSION] Error verificando sesión: {e}", level="warning")

    # ── Ciclo de limpieza ─────────────────────────────────────────────────

    def _cleanup_cycle(self):
        """
        Archiva tickets completados más de cleanup_after_days días atrás.
        Solo se ejecuta una vez al día.
        """
        today = datetime.now().date()
        if self._last_cleanup_date == today:
            return
        self._last_cleanup_date = today

        cleanup_days = self._cfg.get("cleanup_after_days", 30)
        if cleanup_days <= 0:
            return

        self._log(f"[CLEANUP] Buscando tickets completados hace más de {cleanup_days} días")
        try:
            from pipeline_state import load_state, save_state
            state    = load_state(self._state_path)
            archivado_base = os.path.join(self._tickets_base, "archivado")
            threshold      = datetime.now() - timedelta(days=cleanup_days)
            archived       = 0

            for tid, entry in list(state.get("tickets", {}).items()):
                if entry.get("estado") != "completado":
                    continue
                if entry.get("no_archive"):
                    continue

                completado_at = entry.get("completado_at")
                if not completado_at:
                    continue

                try:
                    if datetime.fromisoformat(completado_at) >= threshold:
                        continue
                except Exception:
                    continue

                # Buscar carpeta del ticket
                folder = None
                for estado_dir in os.listdir(self._tickets_base):
                    candidate = os.path.join(self._tickets_base, estado_dir, tid)
                    if os.path.isdir(candidate):
                        folder = candidate
                        break

                if not folder:
                    continue

                # Nunca archivar si hay una corrección en proceso
                if os.path.exists(os.path.join(folder, "CORRECCION_DEV.md")):
                    self._log(f"[CLEANUP] {tid}: omitido (CORRECCION_DEV.md presente)")
                    continue

                dest = os.path.join(archivado_base, tid)
                try:
                    os.makedirs(archivado_base, exist_ok=True)
                    shutil.move(folder, dest)
                    entry["archivado_at"] = datetime.now().isoformat()
                    entry["estado"]       = "archivado"
                    archived += 1
                    self._log(f"[CLEANUP] {tid}: archivado → tickets/archivado/")
                except Exception as mv_err:
                    self._log(f"[CLEANUP] {tid}: error archivando: {mv_err}", level="warning")

            if archived > 0:
                save_state(self._state_path, state)
                self._log(f"[CLEANUP] {archived} ticket(s) archivado(s)")
            else:
                self._log("[CLEANUP] Nada que archivar")

        except Exception as e:
            self._log(f"[CLEANUP] Error: {e}", level="error")

        # ── Limpieza de lock files zombie ────────────────────────────────────
        try:
            from pipeline_lock import cleanup_zombie_locks
            cleaned = cleanup_zombie_locks()
            if cleaned:
                self._log(f"[CLEANUP] {cleaned} lock(s) zombie eliminados")
        except ImportError:
            pass
        except Exception as lck_err:
            self._log(f"[CLEANUP] Error limpiando locks: {lck_err}", level="debug")

    # ── Utilidades ─────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "info") -> None:
        """Delega al logger del módulo según el nivel."""
        _fn = {
            "info":    logger.info,
            "warning": logger.warning,
            "error":   logger.error,
            "debug":   logger.debug,
        }.get(level, logger.info)
        _fn("%s", msg)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _list_projects():
    """Lista los proyectos inicializados."""
    try:
        from project_manager import get_all_projects, get_active_project
        projects = get_all_projects()
        active   = get_active_project()
        print("Proyectos disponibles:")
        for p in projects:
            marker = " (activo)" if p["name"] == active else ""
            print(f"  - {p['name']}{marker}  →  {p.get('workspace_root', '')}")
    except Exception as e:
        print(f"Error listando proyectos: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Mantis Scraper Daemon — orquestador automático de tickets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python daemon.py --project RIPLEY
  python daemon.py --project RIPLEY --interval 30 --verbose
  python daemon.py --project RIPLEY --scrape-only
  python daemon.py --project RIPLEY --pipeline-only
  python daemon.py --list-projects
        """,
    )
    parser.add_argument("--project",       default=None,  help="Proyecto a procesar")
    parser.add_argument("--interval",      type=int, default=None,
                        help="Intervalo de scraping en minutos (default: config del proyecto o 15)")
    parser.add_argument("--scrape-only",   action="store_true",
                        help="Solo scrapear, no lanzar pipeline")
    parser.add_argument("--pipeline-only", action="store_true",
                        help="Solo pipeline, no scrapear")
    parser.add_argument("--no-auto-pipeline", action="store_true",
                        help="Desactivar pipeline automático")
    parser.add_argument("--verbose",       action="store_true",
                        help="Logging detallado (DEBUG en consola)")
    parser.add_argument("--log-file",      default=None,
                        help="Ruta al archivo de log (default: daemon.log)")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Simular: mostrar qué se haría sin lanzar agentes ni scrapear")
    parser.add_argument("--list-projects", action="store_true",
                        help="Listar proyectos disponibles y salir")

    args = parser.parse_args()

    # Configurar logging antes de cualquier otra cosa
    _setup_logging(verbose=args.verbose, log_file=args.log_file)

    if args.list_projects:
        _list_projects()
        return

    # Determinar proyecto activo
    project_name = args.project
    if not project_name:
        try:
            from project_manager import get_active_project
            project_name = get_active_project()
        except Exception:
            pass
    if not project_name:
        project_name = "RIPLEY"

    if args.dry_run:
        logger.info("=" * 55)
        logger.info("MODO DRY-RUN — no se lanzarán agentes ni se scrapeará")
        logger.info("=" * 55)

    daemon = MantisScraperDaemon(
        project_name=project_name,
        scrape_interval_minutes=args.interval,
        auto_pipeline=not args.no_auto_pipeline,
        scrape_only=args.scrape_only,
        pipeline_only=args.pipeline_only,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )
    daemon.run()


if __name__ == "__main__":
    main()
