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
from .evals import bp as evals_bp
from .executions import bp as executions_bp
from .extras import bp as extras_bp
from .git import bp as git_bp
from .glossary import bp as glossary_bp
from .logs import bp as logs_bp
from .memory import bp as memory_bp
from .packs import bp as packs_bp
from .phase4 import bp as phase4_bp
from .phase5 import bp as phase5_bp
from .phase6 import bp as phase6_bp
from .pm import bp as pm_bp
from .preferences import bp as preferences_bp
from .projects import bp as projects_bp
from .qa_browser import bp as qa_browser_bp
from .qa_uat import bp as qa_uat_bp
from .pipelines import bp as pipelines_bp
from .similarity import bp as similarity_bp
from .harness_flags import bp as harness_flags_bp
from .metrics import bp as metrics_bp
from .reports import bp as reports_bp
from .tickets import bp as tickets_bp
from .ui_sections import bp as ui_sections_bp
from .webhooks import bp as webhooks_bp
from .ci import bp as ci_bp  # Plan 72 — trigger/monitor CI (HITL)
from .pipeline_generator import bp as pipeline_generator_bp  # Plan 73 — generador declarativo PipelineSpec→YAML
from .migrator import bp as migrator_bp  # Plan 74 — Migrador ADO→GitLab seguro e idempotente
from .devops import bp as devops_bp  # Plan 87 — panel DevOps: creador gráfico de pipelines
from .devops_agent import bp as devops_agent_bp  # Plan 90 — agente DevOps interactivo
from .devops_servers import bp as devops_servers_bp  # Plan 91 — registro de servidores DevOps
from .devops_variables import bp as devops_variables_bp  # Plan 94 — caja fuerte variables secretas
from .devops_production import bp as devops_production_bp  # Plan 95 — llevar a producción: MR/PR
from .devops_section_doctor import bp as devops_section_doctor_bp  # Plan 104 — doctores IA por sección
from .devops_remote_console import bp as devops_remote_console_bp  # Plan 105 — consola remota
from .codebase_memory_mcp import bp as codebase_memory_mcp_bp  # Plan 76 — eval codebase-memory-mcp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(ado_manager_bp)
api_bp.register_blueprint(agent_roles_bp)
api_bp.register_blueprint(agents_bp)
api_bp.register_blueprint(chat_bp)
api_bp.register_blueprint(evals_bp)
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
api_bp.register_blueprint(memory_bp)
api_bp.register_blueprint(phase4_bp)
api_bp.register_blueprint(phase5_bp)
api_bp.register_blueprint(phase6_bp)
api_bp.register_blueprint(pm_bp)
api_bp.register_blueprint(preferences_bp)
api_bp.register_blueprint(projects_bp)
api_bp.register_blueprint(qa_browser_bp)
api_bp.register_blueprint(qa_uat_bp)
api_bp.register_blueprint(pipelines_bp)
api_bp.register_blueprint(harness_flags_bp)
api_bp.register_blueprint(metrics_bp)
api_bp.register_blueprint(reports_bp)
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
api_bp.register_blueprint(ci_bp)  # Plan 72 — url_prefix="/ci" → /api/ci/...
api_bp.register_blueprint(pipeline_generator_bp)  # Plan 73 — url_prefix="/pipeline-generator" → /api/pipeline-generator/...
api_bp.register_blueprint(migrator_bp)  # Plan 74 — url_prefix="/migrator" → /api/migrator/...
api_bp.register_blueprint(devops_bp)  # Plan 87 — url_prefix="/devops" → /api/devops/...
api_bp.register_blueprint(devops_agent_bp)  # Plan 90 — url_prefix="/devops/agent" → /api/devops/agent/...
api_bp.register_blueprint(devops_servers_bp)  # Plan 91 — url_prefix="/devops/servers" → /api/devops/servers/...
api_bp.register_blueprint(devops_variables_bp)  # Plan 94 — url_prefix="/devops/variables" → /api/devops/variables/...
api_bp.register_blueprint(devops_production_bp)  # Plan 95 — url_prefix="/devops/production" → /api/devops/production/...
api_bp.register_blueprint(devops_section_doctor_bp)  # Plan 104 — url_prefix="/devops/sections" → /api/devops/sections/...
api_bp.register_blueprint(devops_remote_console_bp)  # Plan 105 — url_prefix="/devops/console" → /api/devops/console/...
api_bp.register_blueprint(codebase_memory_mcp_bp)  # Plan 76 — url_prefix="/codebase-memory-mcp" → /api/codebase-memory-mcp/...


@api_bp.get("/health")
def health():
    return {"ok": True}
