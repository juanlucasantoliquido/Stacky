"""Plan 290 F2 — el preflight declara, y NADA de lo que ya funcionaba cambia.

Los cinco primeros casos son de EJECUCION. El sexto es ESTATICO a proposito: lo
que vigila es CABLEADO (que los 3 runtimes pasen el execution_id), que es un
hecho estatico. Es el defecto que el Plan 289 tuvo que arreglar en 2 de 3
runtimes; aca se congela para que no vuelva.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["STACKY_SIMILAR_TICKETS_ENABLED"] = "false"
os.environ["ADO_CONTEXT_ENRICH_AGENTS"] = "__none__"
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

PROYECTO_GITLAB = "Plan290_Preflight_GitLab"
PROYECTO_ADO = "Plan290_Preflight_ADO"
_ADO_SEQ = iter(range(930000, 939999))

MOTIVO = "tracker no-ADO: sin cross-check de comentarios"


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def cfg_proyectos(monkeypatch):
    import project_manager

    def _cfg(nombre):
        nombre = (nombre or "").strip()
        if nombre == PROYECTO_GITLAB:
            return {"issue_tracker": {"type": "gitlab"}}
        if nombre == PROYECTO_ADO:
            return {"issue_tracker": {"type": "azure_devops"}}
        return None

    monkeypatch.setattr(project_manager, "get_project_config", _cfg)
    from services import project_context

    project_context._reset_memo_tracker_declarado()
    yield
    project_context._reset_memo_tracker_declarado()


@pytest.fixture
def flags_on(monkeypatch):
    from config import config

    monkeypatch.setattr(config, "STACKY_RUN_DIRECTIVE_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", True)
    return config


def _crear(proyecto: str):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as sesion:
        t = Ticket(
            ado_id=next(_ADO_SEQ), project=proyecto, stacky_project_name=proyecto,
            title="t", ado_state="Doing", work_item_type="Task", tracker_type="gitlab",
        )
        sesion.add(t)
        sesion.flush()
        e = AgentExecution(
            ticket_id=t.id, agent_type="functional", status="running",
            input_context_json="[]", started_by="plan290",
        )
        sesion.add(e)
        sesion.flush()
        return t.id, e.id


def _metadata(execution_id: int) -> dict:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as sesion:
        return dict(sesion.get(AgentExecution, execution_id).metadata_dict or {})


def _enriquecer(ticket_id, execution_id):
    from services import context_enrichment

    return context_enrichment.enrich_blocks(
        ticket_id=ticket_id, agent_type="functional", raw_blocks=[],
        execution_id=execution_id,
    )


# ── No-regresión del valor neutro ────────────────────────────────────────────

def test_el_valor_neutro_no_cambio(app_ctx, cfg_proyectos, flags_on):
    """Byte a byte lo de hoy: este plan agrega una línea ANTES del return."""
    from services import business_preflight

    ticket_id, execution_id = _crear(PROYECTO_GITLAB)
    r = business_preflight.evaluate(
        ticket_id=ticket_id, agent_type="functional", execution_id=execution_id
    )
    assert r.ok is True
    assert r.mode is None
    assert r.warnings == [MOTIVO]


def test_proyecto_ado_no_declara_nada(app_ctx, cfg_proyectos, flags_on):
    """Sentinela negativo: un proyecto ADO no atraviesa el guard, no declara."""
    ticket_id, execution_id = _crear(PROYECTO_ADO)
    _enriquecer(ticket_id, execution_id)
    assert "capability_degraded" not in _metadata(execution_id)


def test_flag_apagada_no_declara_nada(app_ctx, cfg_proyectos, flags_on, monkeypatch):
    """El kill-switch heredado apaga el guard Y su declaración en un movimiento."""
    from config import config

    monkeypatch.setattr(config, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", False)
    ticket_id, execution_id = _crear(PROYECTO_GITLAB)
    _enriquecer(ticket_id, execution_id)
    assert "capability_degraded" not in _metadata(execution_id)


def test_sin_execution_id_no_levanta(app_ctx, cfg_proyectos, flags_on):
    """Cubre api/agents.py:542, que evalúa antes de que exista la fila y NO se
    toca: sin el kwarg el resultado es idéntico y no lanza."""
    from services import business_preflight

    ticket_id, _execution_id = _crear(PROYECTO_GITLAB)
    r = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert r.ok is True
    assert r.mode is None
    assert r.warnings == [MOTIVO]


def test_dos_warnings_llegan_completos_al_prompt(app_ctx, flags_on, monkeypatch):
    """Se afirma sobre el `content` del bloque, que es el CONSUMIDOR, no sobre
    `_bp.warnings`, que es el productor. Hoy ningún camino de producción genera
    dos warnings: lo que se fija es el contrato del consumidor."""
    from services import business_preflight, context_enrichment, run_ticket_refresh
    from services.business_preflight import BusinessPreflightResult

    ticket_id, execution_id = _crear(PROYECTO_GITLAB)
    monkeypatch.setattr(
        business_preflight, "evaluate",
        lambda **kw: BusinessPreflightResult(
            ok=True, mode=None, warnings=["primero", "segundo"]
        ),
    )
    monkeypatch.setattr(
        run_ticket_refresh, "refresh_ticket_snapshot",
        lambda tid: {"refreshed": False, "reason": "x"},
    )
    blocks = context_enrichment._inject_run_directive(
        ticket_id=ticket_id, agent_type="functional", blocks=[],
        log=lambda *a, **k: None, execution_id=execution_id,
    )
    contenido = blocks[0]["content"]
    assert "primero; segundo" in contenido, (
        f"el segundo warning se perdió. content={contenido!r}"
    )


# ── Cableado de los 3 runtimes (estático, a propósito) ───────────────────────

RUNTIMES = {
    "GitHub Copilot Pro": BACKEND / "agent_runner.py",
    "Claude Code CLI": BACKEND / "services" / "claude_code_cli_runner.py",
    "Codex CLI": BACKEND / "services" / "codex_cli_runner.py",
}


def _llamadas_a_enrich_blocks(ruta: Path) -> list[ast.Call]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return [
        n for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "enrich_blocks"
    ]


def test_los_tres_runtimes_pasan_el_execution_id():
    """R12 — el Plan 289 cableó 2 de 3 runtimes y el tercero tiró el dato en
    silencio. Sin este test, el mismo defecto vuelve sin que nada se ponga rojo.

    El `== 3` NO es decorativo: si el parser deja de encontrar las llamadas
    (renombre, alias, cambio de import) el test tiene que caerse con mensaje
    propio, no dar verde por lista vacía."""
    encontradas = 0
    sin_kwarg = []
    for nombre, ruta in RUNTIMES.items():
        llamadas = _llamadas_a_enrich_blocks(ruta)
        assert llamadas, f"{nombre}: el parser no encontró ninguna llamada en {ruta.name}"
        for c in llamadas:
            encontradas += 1
            if not any(k.arg == "execution_id" for k in c.keywords):
                sin_kwarg.append(f"{nombre} ({ruta.name}:{c.lineno})")

    assert encontradas == 3, (
        f"se esperaban exactamente 3 llamadas a enrich_blocks (una por runtime) y "
        f"se vieron {encontradas}: el censo se rompió o alguien agregó un camino."
    )
    assert sin_kwarg == [], (
        f"runtimes que NO pasan execution_id a enrich_blocks: {sin_kwarg}. "
        "Cablear 2 de 3 es exactamente el defecto del Plan 289."
    )
