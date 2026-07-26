"""Plan 214 F5 — Los playbooks aprendidos llegan también al Codex Browser.

Sin esto, ese camino improvisa la navegación mientras el pipeline determinista
ya sabe cómo llegar a la pantalla: la KB solo mejoraba un runtime de tres.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.qa_browser_plan import (  # noqa: E402
    BrowserRunInput,
    build_guarded_browser_spec,
    playbook_candidates,
)


def _sembrar(root: Path, nombre: str, doc) -> Path:
    carpeta = root / "cache" / "playbooks"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{nombre}.json"
    destino.write_text(
        doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False),
        encoding="utf-8",
    )
    return destino


def test_candidates_dir_inexistente(tmp_path):
    assert playbook_candidates(tmp_path) == []
    assert playbook_candidates(None) == []


def test_candidates_json_invalido_se_saltea(tmp_path):
    _sembrar(tmp_path, "bueno", {"goal": "abrir agenda", "steps": [1, 2]})
    _sembrar(tmp_path, "roto", "no soy json")

    candidatos = playbook_candidates(tmp_path)

    assert len(candidatos) == 1, "un playbook corrupto no invalida los demás"
    assert candidatos[0]["id"] == "bueno"


def test_candidates_shape(tmp_path):
    _sembrar(tmp_path, "p_agenda", {"goal": "abrir la agenda",
                                    "steps": ["ir al menu", "click Agenda"]})

    candidato = playbook_candidates(tmp_path)[0]

    assert candidato["id"] == "p_agenda"
    assert candidato["title"] == "abrir la agenda"
    assert candidato["source"] == "playbook"
    assert candidato["steps"] == 2
    # Lo que el consumidor lee de verdad: sin `text`, el candidato entraria a la
    # lista y no produciria NINGUN escenario — un no-op mudo.
    assert candidato["text"] == "P1: ir al menu\nP2: click Agenda"
    assert candidato["source_id"] == "playbook:p_agenda"


def test_candidates_sin_goal_usa_el_nombre(tmp_path):
    _sembrar(tmp_path, "sin_goal", {"steps": []})

    assert playbook_candidates(tmp_path)[0]["title"] == "sin_goal"


def test_candidates_steps_no_lista_cuenta_cero(tmp_path):
    _sembrar(tmp_path, "raro", {"goal": "x", "steps": "no soy lista"})

    assert playbook_candidates(tmp_path)[0]["steps"] == 0


def test_candidates_pasos_como_dicts(tmp_path):
    """Un playbook real guarda pasos como objetos, no como strings sueltos."""
    _sembrar(tmp_path, "p", {"goal": "g", "steps": [
        {"action": "click en Guardar"}, {"selector": "#btnOk"}]})

    assert playbook_candidates(tmp_path)[0]["text"] == "P1: click en Guardar\nP2: #btnOk"


def test_candidates_es_determinista(tmp_path):
    _sembrar(tmp_path, "z", {"goal": "z"})
    _sembrar(tmp_path, "a", {"goal": "a"})

    assert [c["id"] for c in playbook_candidates(tmp_path)] == ["a", "z"]


def _candidato_previo() -> dict:
    """Un candidato con la forma que el extractor consume de verdad (`text` con
    plan numerado). Sin eso no produce escenarios y el test no probaria nada."""
    return {
        "kind": "acceptance",
        "title": "criterio previo",
        "source_id": "acc:1",
        "confidence": 0.8,
        "reason": "criterio de aceptacion",
        "text": "P1: abrir el detalle del cliente y verificar el criterio previo",
    }


def _escenarios(spec: dict):
    """Los escenarios del spec, sin el prompt (que lleva timestamp propio)."""
    return spec.get("scenarios") or spec.get("plan") or []


def _entrada(candidatos: list) -> BrowserRunInput:
    return BrowserRunInput(
        ticket_id=1, ticket_ado_id=100, ticket_title="t", ticket_state="Active",
        ticket_url=None, allowed_base_url="http://localhost:35017/AgendaWeb/",
        context={"plan_candidates": candidatos},
    )


def test_spec_incluye_playbooks(tmp_path):
    _sembrar(tmp_path, "p1", {"goal": "abrir agenda", "steps": [1]})
    previo = _candidato_previo()

    spec = build_guarded_browser_spec(_entrada([previo]), pipeline_root=tmp_path)

    fuentes = json.dumps(spec, ensure_ascii=False, default=str)
    assert "playbook" in fuentes
    assert "criterio previo" in fuentes, "los candidatos previos NO se reemplazan"


def test_sin_pipeline_root_el_spec_es_el_de_siempre(tmp_path):
    """Todos los callers previos pasan None: comportamiento byte-idéntico."""
    previo = _candidato_previo()

    con_none = build_guarded_browser_spec(_entrada([previo]))
    sin_arg = build_guarded_browser_spec(_entrada([previo]), pipeline_root=None)

    # El spec lleva un timestamp propio: se comparan los escenarios, que es lo
    # que este test afirma que no cambia.
    assert _escenarios(con_none) == _escenarios(sin_arg)


def test_sin_playbooks_no_cambia_nada(tmp_path):
    previo = _candidato_previo()

    con_root_vacio = build_guarded_browser_spec(_entrada([previo]), pipeline_root=tmp_path)
    sin_root = build_guarded_browser_spec(_entrada([previo]))

    assert _escenarios(con_root_vacio) == _escenarios(sin_root)


def test_prompt_de_qauat1_exige_playbooks_primero():
    """Paridad del tercer runtime: el agente de Claude también los consume."""
    prompt = (ROOT / "Stacky" / "agents" / "QAUat1.agent.md").read_text(encoding="utf-8")

    assert "PLAYBOOKS PRIMERO" in prompt
    assert "navigation_contracts.yml" in prompt
    assert "noWaitAfter" in prompt, "el gotcha de WebForms tiene que estar en el prompt"
    assert "playbooks_used" in prompt
