from flask import Blueprint

from .ado_manager import bp as ado_manager_bp
from .docs_rag import bp as docs_rag_bp
from .adoption import bp as adoption_bp
from .agent_roles import bp as agent_roles_bp
from .agents import bp as agents_bp
from .chat import bp as chat_bp
from .client_profile import bp as client_profile_bp
from .config_transfer import bp as config_transfer_bp
from .db_query import bp as db_query_bp
from .docs import bp as docs_bp
from .global_config import bp as global_config_bp
from .flow_config import bp as flow_config_bp
from .anti_patterns import bp as anti_patterns_bp
from .decisions import bp as decisions_bp
from .diag import bp as diag_bp
from .executions import bp as executions_bp
from .extras import bp as extras_bp
from .git import bp as git_bp
from .glossary import bp as glossary_bp
from .logs import bp as logs_bp
from .packs import bp as packs_bp
from .phase4 import bp as phase4_bp
from .phase5 import bp as phase5_bp
from .phase6 import bp as phase6_bp
from .pm import bp as pm_bp
from .preferences import bp as preferences_bp
from .projects import bp as projects_bp
from .qa_browser import bp as qa_browser_bp
from .qa_uat import bp as qa_uat_bp
from .similarity import bp as similarity_bp
from .metrics import bp as metrics_bp
from .tickets import bp as tickets_bp
from .ui_sections import bp as ui_sections_bp
from .webhooks import bp as webhooks_bp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(ado_manager_bp)
api_bp.register_blueprint(agent_roles_bp)
api_bp.register_blueprint(agents_bp)
api_bp.register_blueprint(chat_bp)
api_bp.register_blueprint(executions_bp)
api_bp.register_blueprint(tickets_bp)
api_bp.register_blueprint(packs_bp)
api_bp.register_blueprint(similarity_bp)
api_bp.register_blueprint(anti_patterns_bp)
api_bp.register_blueprint(webhooks_bp)
api_bp.register_blueprint(decisions_bp)
api_bp.register_blueprint(git_bp)
api_bp.register_blueprint(extras_bp)
api_bp.register_blueprint(glossary_bp)
api_bp.register_blueprint(logs_bp)
api_bp.register_blueprint(phase4_bp)
api_bp.register_blueprint(phase5_bp)
api_bp.register_blueprint(phase6_bp)
api_bp.register_blueprint(pm_bp)
api_bp.register_blueprint(preferences_bp)
api_bp.register_blueprint(projects_bp)
api_bp.register_blueprint(qa_browser_bp)
api_bp.register_blueprint(qa_uat_bp)
api_bp.register_blueprint(metrics_bp)
api_bp.register_blueprint(diag_bp)
api_bp.register_blueprint(docs_bp)
api_bp.register_blueprint(flow_config_bp)
api_bp.register_blueprint(global_config_bp)
api_bp.register_blueprint(ui_sections_bp)
api_bp.register_blueprint(adoption_bp)
api_bp.register_blueprint(docs_rag_bp)
api_bp.register_blueprint(config_transfer_bp)
api_bp.register_blueprint(client_profile_bp)
api_bp.register_blueprint(db_query_bp)


@api_bp.get("/health")
def health():
    return {"ok": True}
