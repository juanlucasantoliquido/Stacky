"""Plan 278 F0/F3/F5 — un solo publicador, tres runtimes."""
from __future__ import annotations

import ast
import os
import pathlib
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

BACKEND = pathlib.Path(__file__).resolve().parents[1]
TARGETS = {"autopublish_epic_from_run", "publish_issue_from_run"}
# Directorios excluidos del censo: no son codigo de produccion del backend.
SKIP_PARTS = {"tests", "venv", ".venv", "__pycache__", "evals", "harness", "scripts", "node_modules"}
# api.tickets DEFINE los simbolos: no es un llamador.
SKIP_MODULES = {"api.tickets"}


def publishing_modules() -> set[str]:
    """Modulos de PRODUCCION que REFERENCIAN el publicador.

    Se cuenta por REFERENCIA (ast.ImportFrom + ast.Name + ast.Attribute), NO por
    ast.Call: hoy la invocacion real pasa por un ALIAS
    (claude_code_cli_runner.py:1703 `_publish = publish_issue_from_run if ...`,
    llamado en :1715), y el servicio nuevo hace lo mismo. Un censo por ast.Call
    devuelve el conjunto VACIO en los DOS lados del cambio y no prueba nada.
    Tampoco sirve grep: services/harness_flags.py:2783/2797/2906 nombran los
    simbolos dentro de STRINGS de documentacion.
    """
    found: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND)
        if SKIP_PARTS & set(rel.parts):
            continue
        module = ".".join(rel.with_suffix("").parts)
        if module in SKIP_MODULES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            hit = (
                (isinstance(node, ast.ImportFrom)
                 and any(alias.name in TARGETS for alias in node.names))
                or (isinstance(node, ast.Name) and node.id in TARGETS)
                or (isinstance(node, ast.Attribute) and node.attr in TARGETS)
            )
            if hit:
                found.add(module)
                break
    return found


def test_un_solo_publicador_por_ast():
    # K2: el censo se hace por AST de REFERENCIAS porque el publicador vivia
    # dentro de un CLOSURE y se invoca por ALIAS; un grep -c premia al bug y un
    # censo por ast.Call devuelve vacio en los dos lados del cambio.
    assert publishing_modules() == {"services.epic_autopublish"}


def test_post_hook_de_epica_esta_registrado_y_va_primero():
    # F0 tomo la foto del defecto con el assert INVERSO (el hook NO estaba
    # registrado). F4 lo registra, asi que este caso se invierte igual que el
    # censo por AST: se reescribe, NO se deja convivir con su inverso ni se
    # tapa con un skip.
    from app import create_app          # OBLIGATORIO: _POST_HOOKS se puebla en create_app.
    create_app()                        # Sin esto la lista esta VACIA y el assert
    from services import ticket_status  # de orden pasaria por accidente.
    assert ticket_status._POST_HOOKS, "guarda anti-falso-verde: la lista no puede estar vacia"
    # Se identifica por MODULO, no por __name__: `_post_hook` es un nombre que
    # comparten completion_dispatcher, qa_uat_enqueue y pipeline_orchestrator.
    mods = [getattr(h, "__module__", "") for h in ticket_status._POST_HOOKS]
    assert "services.epic_autopublish" in mods, \
        f"el publicador no esta registrado como post-hook; modulos: {mods}"

    # Orden, no cosmetica: el publicador degrada la fila y el ticket ANTES de que
    # completion_dispatcher sincronice el tracker y de que qa_uat_enqueue encole
    # una validacion E2E de una run cuya epica fallo. Se compara la PRIMERA
    # aparicion de cada uno: _POST_HOOKS es un global de modulo que ACUMULA
    # entre create_app() (contaminacion preexistente entre tests, ajena al plan).
    pos = mods.index("services.epic_autopublish")
    for posterior in ("services.completion_dispatcher", "services.qa_uat_enqueue"):
        assert posterior in mods, f"{posterior} no esta registrado; modulos: {mods}"
        assert pos < mods.index(posterior), \
            f"epic_autopublish debe ir ANTES de {posterior}; orden real: {mods}"


# ── F5 — paridad REAL: los 3 runtimes publican por el mismo camino ────────────

_EPIC_HTML = "<h2>Epica</h2><p>RF-01: el sistema hace algo.</p>"
_ADO_SEQ = [-2000]   # ado_id propio por run: tickets tiene UNIQUE(external_id)


@pytest.mark.parametrize("runtime", ["claude_code_cli", "codex_cli", "github_copilot"])
def test_los_tres_runtimes_publican_por_el_mismo_camino(runtime):
    """K3: el camino de publicacion es el MISMO para los 3 runtimes.

    Se dispara el chokepoint real (ticket_status.on_execution_end), no el hook a
    mano: eso es lo que prueba que el post-hook esta efectivamente cableado.
    """
    from app import create_app
    from db import init_db, session_scope
    from models import AgentExecution, Ticket
    from services import ticket_status

    create_app()          # puebla _POST_HOOKS
    init_db()
    _ADO_SEQ[0] -= 1

    with session_scope() as session:
        ticket = Ticket(ado_id=_ADO_SEQ[0], project="ProyDemo", title="Brief Pool",
                        stacky_project_name="ProyDemo", stacky_status="running")
        session.add(ticket)
        session.flush()
        row = AgentExecution(ticket_id=ticket.id, agent_type="business",
                             status="completed", started_by="test@test.com",
                             output=_EPIC_HTML, started_at=datetime.utcnow())
        row.input_context = [{"id": "brief", "content": "BRIEF X"}]
        row.metadata_dict = {"runtime": runtime, "work_item_type": "Epic"}
        session.add(row)
        session.flush()
        tid, eid = ticket.id, row.id

    from api.tickets import _AutopublishResult
    res = _AutopublishResult(ado_id=4242, error=None, skipped=False,
                             grounding_warnings=[], epic_summary=None,
                             recovery_method=None, published_html=None,
                             baseline_rev=None)
    # NUNCA se toca el tracker real.
    with patch("api.tickets.autopublish_epic_from_run", MagicMock(return_value=res)) as pub:
        ticket_status.on_execution_end(ticket_id=tid, execution_id=eid,
                                       final_status="completed", agent_type="business")

    # call_count == 1: no 0 (no publico) y no 2 (doble publicacion).
    assert pub.call_count == 1, f"runtime={runtime}: call_count={pub.call_count}"
    assert pub.call_args.kwargs["brief"] == "BRIEF X"
    assert pub.call_args.kwargs["project_name"] == "ProyDemo"
