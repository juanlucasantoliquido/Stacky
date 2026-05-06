from flask import Blueprint

from .agents import bp as agents_bp
from .anti_patterns import bp as anti_patterns_bp
from .decisions import bp as decisions_bp
from .executions import bp as executions_bp
from .extras import bp as extras_bp
from .git import bp as git_bp
from .glossary import bp as glossary_bp
from .logs import bp as logs_bp
from .packs import bp as packs_bp
from .phase4 import bp as phase4_bp
from .phase5 import bp as phase5_bp
from .phase6 import bp as phase6_bp
from .preferences import bp as preferences_bp
from .qa_uat import bp as qa_uat_bp
from .similarity import bp as similarity_bp
from .tickets import bp as tickets_bp
from .webhooks import bp as webhooks_bp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(agents_bp)
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
api_bp.register_blueprint(preferences_bp)
api_bp.register_blueprint(qa_uat_bp)


@api_bp.get("/health")
def health():
    return {"ok": True}
