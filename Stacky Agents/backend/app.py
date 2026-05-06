import logging
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
from services.ado_sync import (
    AdoApiError,
    AdoConfigError,
    purge_non_project_tickets,
    sync_tickets,
)
from services.stacky_logger import logger as stacky_logger

# Endpoints whose request body should NOT be logged (may contain credentials)
_NO_LOG_BODY_PATHS: frozenset[str] = frozenset({"/api/logs/frontend"})
# Paths excluded from HTTP logging entirely (health / high-frequency polls)
_SKIP_LOG_PATHS: frozenset[str] = frozenset({"/api/health"})


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": config.ALLOWED_ORIGINS}})
    app.register_blueprint(api_bp)

    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
    logger = logging.getLogger("stacky_agents.app")

    init_db()
    fixed = reconcile_orphans()
    if fixed:
        logger.info("reconciled %d orphan executions", fixed)

    # Corregir tickets que quedaron con stacky_status='running' por crash/reinicio
    from services.ticket_status import recover_stale_running_tickets
    stale_fixed = recover_stale_running_tickets()
    if stale_fixed:
        logger.info("startup recovery: corregidos %d tickets con status 'running' inconsistente", stale_fixed)

    # Limpia restos de seeds/sandbox sin tocar tickets reales con ejecuciones.
    target_project = (config.ADO_PROJECT or "Strategist_Pacifico").strip()
    purged = purge_non_project_tickets(target_project)
    if purged:
        logger.info("purgados %d tickets ajenos al proyecto %s", purged, target_project)

    # Sync inicial best-effort: si hay PAT y proyecto, traemos work items reales.
    try:
        result = sync_tickets()
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
