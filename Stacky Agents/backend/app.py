import logging
import mimetypes
import os
import threading
import time
from pathlib import Path

# En Windows, `mimetypes` deriva las asociaciones del registro
# (HKEY_CLASSES_ROOT\.js -> "Content Type"). Si una máquina tiene `.js` mapeado a
# text/plain o text/html — algo que pisan varios instaladores — Flask sirve los
# módulos ES con el Content-Type equivocado y el navegador los rechaza
# ("Failed to load module script: Expected a JavaScript module script..."),
# dejando la pantalla en negro. Forzamos los tipos correctos para que el release
# funcione igual en todas las máquinas, sin depender del registro del SO.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/svg+xml", ".svg")

# Usar el truststore del SO (Windows / macOS) para SSL — necesario en redes con
# inspección TLS corporativa (Zscaler, etc.) que firman con un root no presente
# en el bundle de certifi.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

from api import api_bp
from config import config
from db import init_db
from log_streamer import reconcile_orphans
from project_manager import get_active_project, get_project_config
from services.ado_sync import (
    AdoApiError,
    AdoConfigError,
    purge_non_project_tickets,
    sync_tickets as _ado_sync,
)
from services.stacky_logger import logger as stacky_logger
from services.console_log_handler import install_console_log_handler
from services.local_file_logging import install_file_log_handler
from runtime_paths import frontend_dist_dir

# Endpoints whose request body should NOT be logged (may contain credentials)
_NO_LOG_BODY_PATHS: frozenset[str] = frozenset({"/api/logs/frontend"})
# Paths excluded from HTTP logging entirely (health / high-frequency polls)
_SKIP_LOG_PATHS: frozenset[str] = frozenset({"/api/health"})


def _startup_sync(logger) -> None:
    """
    Sincroniza los tickets del proyecto activo al arrancar.
    Soporta Azure DevOps, Jira y Mantis BT.
    Si no hay proyecto configurado cae al comportamiento original
    (ADO con config global del .env).
    """
    active = get_active_project()
    tracker_type = "azure_devops"
    tracker: dict = {}

    if active:
        cfg     = get_project_config(active) or {}
        tracker = cfg.get("issue_tracker") or {}
        tracker_type = tracker.get("type", "azure_devops")

    if tracker_type == "jira":
        from services.jira_sync import sync_tickets as jira_sync
        from services.jira_client import JiraApiError, JiraConfigError
        try:
            result = jira_sync(tracker_config=tracker)
            logger.info(
                "sync Jira ok: project=%s fetched=%d created=%d updated=%d removed=%d",
                result["project"], result["fetched"], result["created"],
                result["updated"], result["removed"],
            )
        except JiraConfigError as e:
            logger.warning("sync Jira saltado: %s", e)
        except JiraApiError as e:
            logger.warning("sync Jira falló: %s", e)
        except Exception:
            logger.exception("sync Jira error inesperado en arranque")

    elif tracker_type == "mantis":
        from services.mantis_sync import sync_tickets as mantis_sync
        from services.mantis_client import MantisApiError, MantisConfigError
        try:
            result = mantis_sync(tracker_config=tracker)
            logger.info(
                "sync Mantis ok: project=%s fetched=%d created=%d updated=%d removed=%d",
                result["project"], result["fetched"], result["created"],
                result["updated"], result["removed"],
            )
        except MantisConfigError as e:
            logger.warning("sync Mantis saltado: %s", e)
        except MantisApiError as e:
            logger.warning("sync Mantis falló: %s", e)
        except Exception:
            logger.exception("sync Mantis error inesperado en arranque")

    else:
        # Azure DevOps
        active_ctx = None
        if active:
            try:
                from services.project_context import resolve_project_context

                active_ctx = resolve_project_context(project_name=active)
            except Exception:
                active_ctx = None
        target_project = (
            (active_ctx.tracker_project if active_ctx else None)
            or tracker.get("project")
            or config.ADO_PROJECT
            or "Strategist_Pacifico"
        ).strip()
        purged = purge_non_project_tickets(target_project)
        if purged:
            logger.info("purgados %d tickets ajenos al proyecto %s", purged, target_project)
        try:
            from services.project_context import build_ado_client

            client = build_ado_client(project_name=active) if active else None
            result = _ado_sync(client=client)
            logger.info(
                "sync ADO ok: project=%s fetched=%d created=%d updated=%d removed=%d",
                result["project"], result["fetched"], result["created"],
                result["updated"], result["removed"],
            )
        except AdoConfigError as e:
            logger.warning("sync ADO saltado: %s", e)
        except AdoApiError as e:
            logger.warning("sync ADO falló: %s", e)
        except Exception:
            logger.exception("sync ADO error inesperado en arranque")


def _log_completion_preflight(logger) -> None:
    """Loguea (y advierte) sobre la salud del cierre automático al arrancar.

    Cubre la Fase P2 del PLAN_FIX_REGISTRO_COMPLETION_OPENCHAT: el deploy debe
    gritar temprano en vez de fallar silencioso. Nunca lanza — el arranque no
    debe abortar por esto.
    """
    try:
        from runtime_paths import repo_root
        from services.agent_html_output import outputs_dir
        from services.ado_client import ado_pat_present
        from project_manager import get_active_project

        rr = repo_root()
        od = outputs_dir()
        od_exists = od.exists()
        active = get_active_project()
        logger.info(
            "preflight cierre open-chat: repo_root=%s outputs_dir=%s (existe=%s) active_project=%s",
            rr, od, od_exists, active or "(ninguno)",
        )
        if not od_exists:
            logger.warning(
                "preflight: outputs_dir NO existe (%s) — el output_watcher no "
                "encontrará artifacts. Revisá proyecto activo / STACKY_REPO_ROOT.",
                od,
            )

        auto_create = (
            os.getenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true").lower() != "false"
        )
        if auto_create and not ado_pat_present():
            logger.warning(
                "preflight: auto-create de Tasks habilitado pero ADO PAT ausente "
                "→ las Tasks NO se crearán. Setea ADO_PAT en .env o llena Tools/PAT-ADO."
            )
    except Exception:  # noqa: BLE001
        logger.exception("preflight de cierre open-chat falló (continuando)")


def create_app() -> Flask:
    dist_dir = frontend_dist_dir()
    app = Flask(__name__)
    if dist_dir is None or config.ENABLE_CORS:
        CORS(app, resources={r"/api/*": {"origins": config.ALLOWED_ORIGINS}})
    app.register_blueprint(api_bp)

    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
    install_file_log_handler()
    logger = logging.getLogger("stacky_agents.app")

    init_db()
    install_console_log_handler()

    # ── Bootstrap canonical Stacky/agents ───────────────────────────────────
    # Stacky/agents es la fuente versionada. El bootstrap solo refresca
    # manifest.json para que el resto del backend lea siempre desde el
    # canonical; no copia agentes desde GitHub Copilot/VS Code.
    try:
        from runtime_paths import stacky_agents_dir, stacky_home
        from services import stacky_agents as _stacky_agents_svc

        _materialized = _stacky_agents_svc.materialize_agents()
        logger.info(
            "stacky_home=%s stacky_agents_dir=%s materialized=%d",
            stacky_home(), stacky_agents_dir(), len(_materialized),
        )
        if not _materialized:
            logger.warning(
                "Stacky/agents está vacío tras el bootstrap. "
                "Importá agentes con POST /api/agents/import o copiá .agent.md "
                "a %s antes de despachar runs CLI.",
                stacky_agents_dir(),
            )
    except Exception:  # noqa: BLE001
        logger.exception("bootstrap stacky_agents falló (continuando)")

    try:
        from services.db_backup import ensure_weekly_backup

        backup = ensure_weekly_backup()
        if backup.get("skipped"):
            logger.info("db backup omitido: %s", backup.get("reason"))
        else:
            logger.info("db backup creado: %s", backup.get("backup_path"))
    except Exception:
        logger.exception("db backup automático falló (continuando)")

    # Demo seed (C2 PLAN_ADOPCION_DEVS) — idempotente, sólo crea tickets si faltan.
    try:
        from services.demo_seed import seed_demo_project
        if os.getenv("STACKY_DEMO_SEED_ENABLED", "true").lower() == "true":
            seed_demo_project()
    except Exception:
        logger.exception("demo seed falló (continuando sin demo)")

    # Seed inicial de flow_config.json (Feature #4 — DO-4.4).
    # No regenera si el operador ya tiene reglas configuradas.
    try:
        from services.flow_config_store import seed_defaults_if_empty
        seeded = seed_defaults_if_empty()
        if seeded:
            logger.info("flow_config seed: %d reglas iniciales creadas", seeded)
    except Exception:
        logger.exception("flow_config seed falló (continuando sin reglas iniciales)")
    fixed = reconcile_orphans()
    if fixed:
        logger.info("reconciled %d orphan executions", fixed)

    # R0.3 — Orphan reaper: barrido inicial + daemon periodico (si habilitado).
    try:
        from services.orphan_reaper import start_background_reaper
        start_background_reaper()
    except Exception:
        logger.exception("orphan_reaper startup fallo (continuando)")

    # ── V0.1 — Perfil del arnés en boot ──────────────────────────────────────
    # STACKY_HARNESS_PROFILE=off|safe|full (default: "" = no aplicar).
    # Respeta env vars individuales ya seteadas explícitamente por el operador.
    _harness_profile = os.getenv("STACKY_HARNESS_PROFILE", "").strip().lower()
    if _harness_profile:
        try:
            from services.harness_profiles import apply_profile
            applied = apply_profile(_harness_profile, respect_explicit_env=True)
            logger.info(
                "perfil de arnés '%s' aplicado en boot (%d flags)",
                _harness_profile, len(applied),
            )
        except ValueError as exc:
            logger.warning("STACKY_HARNESS_PROFILE inválido, ignorado: %s", exc)

    # ── Startup recovery (P5) ────────────────────────────────────────────────
    # STACKY_RECOVERY_ON_STARTUP=true|false (default: true cuando gateway=on, false si no)
    _gateway_mode = os.getenv("STACKY_COMPLETION_GATEWAY", "off").lower().strip()
    _recovery_default = "true" if _gateway_mode == "on" else "false"
    _recovery_on_startup = os.getenv("STACKY_RECOVERY_ON_STARTUP", _recovery_default).lower() == "true"

    if _recovery_on_startup:
        from services.ticket_status import recover_stale_running_tickets
        stale_details = recover_stale_running_tickets(trigger="startup")
        if stale_details:
            logger.info(
                "startup recovery: corregidos %d items (tickets stale + executions con timeout)",
                len(stale_details),
            )
            for detail in stale_details:
                logger.debug("recovery detail: %s", detail)
    else:
        logger.debug(
            "startup recovery omitido: STACKY_RECOVERY_ON_STARTUP=false (gateway=%s)",
            _gateway_mode,
        )

    # ── Stale recovery guardian (reaper periódico) ───────────────────────────
    # Daemon thread que re-ejecuta recover_stale_running_tickets cada N seg.
    # STACKY_REAPER_ENABLED=true|false (default: true)
    # STACKY_REAPER_INTERVAL_SECONDS=int (default: 120)
    _reaper_enabled = os.getenv("STACKY_REAPER_ENABLED", "true").lower() == "true"
    if _reaper_enabled:
        from services.ticket_status import schedule_stale_recovery
        _reaper_interval = int(os.getenv("STACKY_REAPER_INTERVAL_SECONDS", "120"))
        schedule_stale_recovery(interval_seconds=_reaper_interval)
        logger.info("stale recovery guardian armed (interval=%ds)", _reaper_interval)
    else:
        logger.debug("stale recovery guardian disabled (STACKY_REAPER_ENABLED=false)")

    # ── Manifest watcher ─────────────────────────────────────────────────────
    # Polea backend/data/codex_runs/<id>/MANIFEST.json y cierra runs huérfanos.
    # STACKY_MANIFEST_WATCHER_ENABLED=true|false (default: true)
    # STACKY_MANIFEST_WATCHER_INTERVAL_SECONDS=float (default: 2.0)
    _watcher_enabled = os.getenv("STACKY_MANIFEST_WATCHER_ENABLED", "true").lower() == "true"
    if _watcher_enabled:
        from services.manifest_watcher import start_manifest_watcher
        _watcher_interval = float(os.getenv("STACKY_MANIFEST_WATCHER_INTERVAL_SECONDS", "2.0"))
        start_manifest_watcher(poll_interval=_watcher_interval)
        logger.info("manifest watcher armed (interval=%.1fs)", _watcher_interval)
    else:
        logger.debug("manifest watcher disabled (STACKY_MANIFEST_WATCHER_ENABLED=false)")

    # ── Output watcher (Modo A + Modo B) ─────────────────────────────────────
    # Cierre automático de runs VSCode (open-chat) cuando el agente deposita
    # artifacts en Agentes/outputs/ pero no PATCHea stacky-status.
    # STACKY_OUTPUT_WATCHER_ENABLED=true|false (default: true)
    # STACKY_OUTPUT_WATCHER_INTERVAL_SECONDS=float (default: 3.0)
    _output_watcher_enabled = os.getenv("STACKY_OUTPUT_WATCHER_ENABLED", "true").lower() == "true"
    if _output_watcher_enabled:
        from services.output_watcher import start_output_watcher
        _output_watcher_interval = float(os.getenv("STACKY_OUTPUT_WATCHER_INTERVAL_SECONDS", "3.0"))
        start_output_watcher(poll_interval=_output_watcher_interval)
        logger.info("output watcher armed (interval=%.1fs)", _output_watcher_interval)
    else:
        logger.debug("output watcher disabled (STACKY_OUTPUT_WATCHER_ENABLED=false)")

    # ── Evals programados (V2.3 — golden loop) ───────────────────────────────
    # Daemon que corre `evals run all` cada STACKY_EVALS_INTERVAL_HOURS y persiste
    # en la tabla eval_runs. Default 0 = off (retro-compat).
    try:
        _evals_interval = float(os.getenv("STACKY_EVALS_INTERVAL_HOURS", "0") or 0)
    except ValueError:
        _evals_interval = 0.0
    if _evals_interval > 0:
        from services.eval_history import schedule_evals
        schedule_evals(_evals_interval)
        logger.info("evals scheduler armed (interval=%.1fh)", _evals_interval)
    else:
        logger.debug("evals scheduler disabled (STACKY_EVALS_INTERVAL_HOURS=0)")

    # ── Preflight de configuración (Fase P2) ─────────────────────────────────
    # Gritar temprano si el cierre automático del flujo open-chat no va a
    # funcionar: directorio vigilado inexistente (C1) o PAT ausente (C2).
    _log_completion_preflight(logger)

    _startup_sync(logger)

    # ── U2.1 — Hook de avance de pipeline por finalización de ejecución ─────
    try:
        from services import pipeline_orchestrator

        pipeline_orchestrator.register_ticket_status_hook()
    except Exception:
        logger.exception("pipeline orchestrator hook registration failed")

    # ── U1.5 — Digest periódico a webhooks (opcional) ──────────────────────
    # STACKY_DIGEST_INTERVAL_HOURS=0 => apagado (default).
    if int(config.STACKY_DIGEST_INTERVAL_HOURS) > 0:
        interval_seconds = int(config.STACKY_DIGEST_INTERVAL_HOURS) * 3600

        def _digest_loop() -> None:
            from services import webhooks
            from services.run_digest import compose_digest

            while True:
                try:
                    digest_payload = compose_digest(days=7)
                    webhooks.fire("digest.ready", {"event": "digest.ready", "digest": digest_payload})
                except Exception:
                    logger.exception("digest daemon: dispatch falló")
                time.sleep(interval_seconds)

        threading.Thread(target=_digest_loop, name="stacky-digest-daemon", daemon=True).start()
        logger.info("digest daemon armed (interval=%ds)", interval_seconds)

    # ── M0.3 — Barrido de revisión de memoria (opcional) ───────────────────
    # STACKY_MEMORY_REVIEW_SWEEP_HOURS=0 => apagado (default, byte-idéntico).
    if int(config.STACKY_MEMORY_REVIEW_SWEEP_HOURS) > 0:
        _review_sweep_seconds = int(config.STACKY_MEMORY_REVIEW_SWEEP_HOURS) * 3600

        def _memory_review_sweep_loop() -> None:
            from services import memory_store

            while True:
                try:
                    marked = memory_store.mark_stale_for_review()
                    if marked:
                        logger.info("memory review sweep: %d -> needs_review", marked)
                except Exception:
                    logger.exception("memory review sweep daemon falló")
                time.sleep(_review_sweep_seconds)

        threading.Thread(
            target=_memory_review_sweep_loop,
            name="stacky-memory-review-daemon",
            daemon=True,
        ).start()
        logger.info("memory review daemon armed (interval=%ds)", _review_sweep_seconds)

    # ── Structured logging middleware ─────────────────────────────────────

    @app.before_request
    def _before_request() -> None:
        g.request_id = stacky_logger.new_request_id()
        g.request_start = time.monotonic()

    @app.after_request
    def _after_request(response):
        path = request.path
        if path in _SKIP_LOG_PATHS:
            return response

        duration_ms = int((time.monotonic() - g.get("request_start", time.monotonic())) * 1000)
        user = request.headers.get("X-User-Email") or "anonymous"

        # Capture request body for non-sensitive endpoints
        input_data: dict | None = None
        if path not in _NO_LOG_BODY_PATHS:
            try:
                body = request.get_json(silent=True, force=True)
                if body:
                    input_data = body
            except Exception:
                pass

        stacky_logger.request(
            request.method,
            path,
            response.status_code,
            duration_ms,
            user=user,
            request_id=g.get("request_id"),
            input_data=input_data,
        )
        # Propagate request ID to client for correlation
        response.headers["X-Request-ID"] = g.get("request_id", "")
        return response

    @app.errorhandler(Exception)
    def _handle_unhandled_error(exc: Exception):
        """Log every unhandled exception before Flask returns 500.

        HTTPExceptions (4xx / 5xx raised via abort()) are re-raised so that
        Flask handles them normally — we only intercept true 500s.
        """
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        stacky_logger.error(
            "http.middleware",
            "unhandled_exception",
            exc=exc,
            endpoint=request.path,
            method=request.method,
            user=request.headers.get("X-User-Email", "anonymous"),
            tags=["http", "unhandled_exception"],
        )
        logger.exception("unhandled exception in %s %s", request.method, request.path)
        return jsonify({"error": "Internal server error", "request_id": g.get("request_id", "")}), 500

    if dist_dir is not None:
        dist_path = Path(dist_dir)

        # Content-Type explícito por extensión. No dependemos de `mimetypes` ni
        # del registro de Windows: en algunas máquinas `.js` queda mapeado a
        # text/plain y el navegador rechaza los módulos ES ("Expected a
        # JavaScript module script..."), dejando la pantalla en negro.
        _ASSET_CONTENT_TYPES = {
            ".js": "text/javascript",
            ".mjs": "text/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".svg": "image/svg+xml",
            ".wasm": "application/wasm",
            ".map": "application/json",
        }

        @app.get("/")
        def _serve_spa_index():
            return send_from_directory(dist_path, "index.html")

        @app.get("/<path:asset_path>")
        def _serve_spa_asset(asset_path: str):
            if asset_path == "api" or asset_path.startswith("api/"):
                return jsonify({"error": "Not found"}), 404

            candidate = dist_path / asset_path
            if candidate.exists() and candidate.is_file():
                response = send_from_directory(dist_path, asset_path)
                forced = _ASSET_CONTENT_TYPES.get(candidate.suffix.lower())
                if forced is not None:
                    response.headers["Content-Type"] = forced
                return response

            return send_from_directory(dist_path, "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, threaded=True, debug=False)
