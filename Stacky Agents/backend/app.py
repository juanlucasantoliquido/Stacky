import logging

# Usar el truststore del SO (Windows / macOS) para SSL — necesario en redes con
# inspección TLS corporativa (Zscaler, etc.) que firman con un root no presente
# en el bundle de certifi.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from flask import Flask
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

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, threaded=True, debug=False)
