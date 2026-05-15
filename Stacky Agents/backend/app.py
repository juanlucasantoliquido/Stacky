import logging
import os
import time

# Usar el truststore del SO (Windows / macOS) para SSL — necesario en redes con
# inspección TLS corporativa (Zscaler, etc.) que firman con un root no presente
# en el bundle de certifi.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from flask import Flask, g, jsonify, request
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
        target_project = (
            tracker.get("project")
            or config.ADO_PROJECT
            or "Strategist_Pacifico"
        ).strip()
        purged = purge_non_project_tickets(target_project)
        if purged:
            logger.info("purgados %d tickets ajenos al proyecto %s", purged, target_project)
        try:
            from services.ado_client import AdoClient
            kw: dict = {}
            if tracker.get("organization") and tracker.get("project"):
                kw = {"org": tracker["organization"], "project": tracker["project"]}
            result = _ado_sync(client=AdoClient(**kw))
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


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": config.ALLOWED_ORIGINS}})
    app.register_blueprint(api_bp)

    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
    logger = logging.getLogger("stacky_agents.app")

    init_db()
    install_console_log_handler()
    fixed = reconcile_orphans()
    if fixed:
        logger.info("reconciled %d orphan executions", fixed)

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

    _startup_sync(logger)

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

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, threaded=True, debug=False)
