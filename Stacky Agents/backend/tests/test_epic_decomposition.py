"""Plan 59 — Descomposición vertical épica→hijos.

Tests F1 (parser puro), F2 (endpoint preview), F3 (publicador idempotente),
F4 (endpoint creación) + §4bis (anti-drift fingerprint).

NO toca ADO real ni BD real: todo mockeado con FakeAdo / monkeypatch.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest


# ── HTML de fixtures ──────────────────────────────────────────────────────────

HTML_TWO_RF = (
    "<h1>EP-1 Épica de prueba</h1>"
    "<h2>RF-1 — Autenticación</h2><p>El usuario debe poder autenticarse.</p>"
    "<h2>RF-2 — Reportes</h2><p>El sistema debe generar reportes.</p>"
)

HTML_WITH_TASKS = (
    "<h1>EP-1 Épica</h1>"
    "<h2>RF-1 — Feature con tareas</h2>"
    "<p>Descripción</p>"
    "<ul><li>T- hacer X</li><li>nota suelta</li></ul>"
)

HTML_NO_TASKS = (
    "<h1>EP-1 Épica</h1>"
    "<h2>RF-1 — Feature sin tareas</h2>"
    "<p>Descripción sin tareas. Solo prosa.</p>"
)

HTML_NO_RF = "<h1>Épica</h1><p>prosa libre sin bloques RF</p>"

# Output completo (como lo devuelve el agente — con fences) para tests de endpoint
OUTPUT_WITH_TWO_RF = (
    "Aquí la épica:\n\n"
    "```html\n"
    + HTML_TWO_RF
    + "\n```\n"
    "Resumen: listo ✅"
)

OUTPUT_WITH_ONE_RF = (
    "Aquí la épica:\n\n"
    "```html\n"
    "<h1>EP-2 Épica</h1>"
    "<h2>RF-1 — Módulo único</h2><p>Descripción del módulo.</p>"
    "\n```\n"
)

OUTPUT_EMPTY = ""


# ── FakeAdo ───────────────────────────────────────────────────────────────────

class FakeAdo:
    """ADO fake para tests de idempotencia y publicación.

    Registra cada create_work_item. find_child_by_marker busca el marcador
    en System.Description (como hace el ADO real via WIQL System.Parent).
    """

    def __init__(self, next_id: int = 100):
        self._next_id = next_id
        self.create_calls: list[dict] = []
        self._store: dict[int, dict] = {}  # id → work item dict

    def create_work_item(
        self,
        work_item_type: str,
        fields: dict,
        parent_ado_id: int | None = None,
        **kwargs,
    ) -> dict:
        wi_id = self._next_id
        self._next_id += 1
        desc = fields.get("System.Description", "")
        title = fields.get("System.Title", "")
        self._store[wi_id] = {
            "id": wi_id,
            "work_item_type": work_item_type,
            "fields": {
                "System.Title": title,
                "System.Description": desc,
                "System.Parent": parent_ado_id,
            },
            "parent_ado_id": parent_ado_id,
        }
        self.create_calls.append({
            "work_item_type": work_item_type,
            "fields": fields.copy(),
            "parent_ado_id": parent_ado_id,
        })
        return {"id": wi_id}

    def find_child_by_marker(self, parent_id: int, marker: str) -> dict | None:
        for wi in self._store.values():
            desc = wi["fields"].get("System.Description", "")
            if marker in desc and wi["parent_ado_id"] == parent_id:
                return wi
        return None


# ── Fixtures Flask ────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        with app.app_context():
            yield c


# ═══════════════════════════════════════════════════════════════════════════════
# F1 — Parser PURO épica→hijos
# ═══════════════════════════════════════════════════════════════════════════════

def test_children_plan_empty_html_returns_error():
    """HTML vacío o None → ok=False, error='empty_html'."""
    from api.tickets import build_epic_children_plan
    r = build_epic_children_plan(epic_html=None)
    assert r.ok is False
    assert r.error == "empty_html"
    assert r.total_children == 0

    r2 = build_epic_children_plan(epic_html="")
    assert r2.ok is False
    assert r2.error == "empty_html"


def test_children_plan_two_rf_blocks_two_features():
    """HTML con 2 <h2>RF-N → 2 Features, total_children >= 2."""
    from api.tickets import build_epic_children_plan
    r = build_epic_children_plan(epic_html=HTML_TWO_RF)
    assert r.ok is True
    assert len(r.features) == 2
    assert r.total_children >= 2
    assert r.error is None
    assert r.features[0].work_item_type == "Feature"
    assert r.features[1].work_item_type == "Feature"
    assert "Autenticación" in r.features[0].title or "RF-1" in r.features[0].title
    assert "Reportes" in r.features[1].title or "RF-2" in r.features[1].title


def test_children_plan_parses_tasks_with_prefix():
    """Un bloque RF con <li>T- hacer X</li> → Feature tiene exactamente 1 Task."""
    from api.tickets import build_epic_children_plan
    r = build_epic_children_plan(epic_html=HTML_WITH_TASKS)
    assert r.ok is True
    assert len(r.features) == 1
    feat = r.features[0]
    assert len(feat.children) == 1
    task = feat.children[0]
    assert task.work_item_type == "Task"
    assert "hacer X" in task.title


def test_children_plan_feature_without_tasks():
    """Bloque RF sin <li> de tarea → Feature con children == []."""
    from api.tickets import build_epic_children_plan
    r = build_epic_children_plan(epic_html=HTML_NO_TASKS)
    assert r.ok is True
    assert len(r.features) == 1
    assert r.features[0].children == []


def test_children_plan_no_rf_blocks_fallback():
    """HTML sin bloques RF → ok=False, error='no_children_parseable', total_children==0."""
    from api.tickets import build_epic_children_plan
    r = build_epic_children_plan(epic_html=HTML_NO_RF)
    assert r.ok is False
    assert r.error == "no_children_parseable"
    assert r.total_children == 0


def test_children_plan_pure_never_raises():
    """Input basura → no lanza, devuelve EpicChildrenPlan."""
    from api.tickets import build_epic_children_plan, EpicChildrenPlan
    r = build_epic_children_plan(epic_html="<h2>RF-1<<<malformed")
    assert isinstance(r, EpicChildrenPlan)
    # Puede ser ok=True o False, pero nunca lanza.


# ═══════════════════════════════════════════════════════════════════════════════
# F2 — Endpoint POST /api/tickets/epic-children-preview
# ═══════════════════════════════════════════════════════════════════════════════

def test_preview_endpoint_flag_off_returns_disabled(client, monkeypatch):
    """Con flag OFF → 200, enabled=False."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "false")
    resp = client.post(
        "/api/tickets/epic-children-preview",
        json={"output": OUTPUT_WITH_TWO_RF, "brief": "b", "project_name": "P"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is False
    assert data["features"] == []
    assert data["total_children"] == 0


def test_preview_endpoint_returns_features(client, monkeypatch):
    """Con flag ON + output con 2 RF → features tiene 2 items, total_children >= 2."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    resp = client.post(
        "/api/tickets/epic-children-preview",
        json={"output": OUTPUT_WITH_TWO_RF, "brief": "b", "project_name": "P"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is True
    assert data["epic_ok"] is True
    assert len(data["features"]) == 2
    assert data["total_children"] >= 2


def test_preview_endpoint_empty_output(client, monkeypatch):
    """Con flag ON + output vacío → epic_ok=False."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    resp = client.post(
        "/api/tickets/epic-children-preview",
        json={"output": "", "brief": "b", "project_name": "P"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is True
    assert data["epic_ok"] is False


def test_preview_endpoint_does_not_touch_ado(client, monkeypatch):
    """El endpoint preview NUNCA llama a build_ado_client."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    import api.tickets as t_mod

    def _raise_if_called(*a, **k):
        raise AssertionError("build_ado_client fue llamado en el preview — no debe ocurrir")

    monkeypatch.setattr(t_mod, "build_ado_client", _raise_if_called, raising=False)
    resp = client.post(
        "/api/tickets/epic-children-preview",
        json={"output": OUTPUT_WITH_TWO_RF, "brief": "b", "project_name": "P"},
    )
    assert resp.status_code == 200  # sin excepción → ADO no fue llamado


# ═══════════════════════════════════════════════════════════════════════════════
# F3 — Publicador idempotente `publish_epic_children`
# ═══════════════════════════════════════════════════════════════════════════════

def _make_plan_one_feature_one_task():
    """Plan con 1 Feature + 1 Task para tests F3."""
    from api.tickets import build_epic_children_plan
    html = (
        "<h1>EP-1 Épica</h1>"
        "<h2>RF-1 — Feature principal</h2>"
        "<p>Descripción</p>"
        "<ul><li>T- tarea uno</li></ul>"
    )
    return build_epic_children_plan(epic_html=html)


def test_publish_children_flag_off_skips(monkeypatch):
    """Con flag OFF → skipped=True, FakeAdo.create_calls == []."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "false")
    from api.tickets import publish_epic_children
    plan = _make_plan_one_feature_one_task()
    fake = FakeAdo()
    result = publish_epic_children(epic_ado_id=1, children_plan=plan, project_name="P", ado=fake)
    assert result.skipped is True
    assert fake.create_calls == []


def test_publish_children_creates_features_and_tasks(monkeypatch):
    """Plan con 1 Feature + 1 Task → created_ids tiene 2 ids con parent links correctos."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    from api.tickets import publish_epic_children
    plan = _make_plan_one_feature_one_task()
    fake = FakeAdo(next_id=200)
    epic_id = 999
    result = publish_epic_children(epic_ado_id=epic_id, children_plan=plan, project_name="P", ado=fake)
    assert result.error is None
    assert result.skipped is False
    assert len(result.created_ids) == 2
    # Feature cuelga del epic
    f_call = next(c for c in fake.create_calls if c["work_item_type"] == "Feature")
    assert f_call["parent_ado_id"] == epic_id
    # Task cuelga del feature_id
    feature_id = result.created_ids[0]
    t_call = next(c for c in fake.create_calls if c["work_item_type"] == "Task")
    assert t_call["parent_ado_id"] == feature_id
    # Marcadores embebidos en la descripción
    f_desc = f_call["fields"]["System.Description"]
    assert "<!-- stacky-child:" in f_desc
    t_desc = t_call["fields"]["System.Description"]
    assert "<!-- stacky-child:" in t_desc


def test_publish_children_idempotent_by_marker(monkeypatch):
    """Dos llamadas idénticas → 2ª tiene created_ids=[], reused_ids con los ids de la 1ª."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    from api.tickets import publish_epic_children
    plan = _make_plan_one_feature_one_task()
    fake = FakeAdo(next_id=300)
    epic_id = 888

    r1 = publish_epic_children(epic_ado_id=epic_id, children_plan=plan, project_name="P", ado=fake)
    assert r1.error is None
    assert len(r1.created_ids) == 2

    r2 = publish_epic_children(epic_ado_id=epic_id, children_plan=plan, project_name="P", ado=fake)
    assert r2.created_ids == []
    assert set(r2.reused_ids) == set(r1.created_ids)


def test_publish_children_idempotent_survives_rename(monkeypatch):
    """Renombrar el hijo en ADO no afecta la idempotencia — el marcador en Description manda."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    from api.tickets import publish_epic_children
    plan = _make_plan_one_feature_one_task()
    fake = FakeAdo(next_id=400)
    epic_id = 777

    r1 = publish_epic_children(epic_ado_id=epic_id, children_plan=plan, project_name="P", ado=fake)
    feature_id = r1.created_ids[0]

    # Simular renombre del operador: mutar el título en el store del FakeAdo.
    fake._store[feature_id]["fields"]["System.Title"] = "TÍTULO RENOMBRADO POR OPERADOR"

    r2 = publish_epic_children(epic_ado_id=epic_id, children_plan=plan, project_name="P", ado=fake)
    # La 2ª llamada encuentra el hijo por MARCADOR (no por título) → reused, sin duplicar.
    assert r2.created_ids == []
    assert feature_id in r2.reused_ids


def test_publish_children_empty_plan_skips(monkeypatch):
    """Plan con ok=False → skipped=True, 0 llamadas a ADO."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    from api.tickets import publish_epic_children, EpicChildrenPlan
    empty_plan = EpicChildrenPlan(ok=False, features=[], total_children=0, error="no_children_parseable")
    fake = FakeAdo()
    result = publish_epic_children(epic_ado_id=1, children_plan=empty_plan, project_name="P", ado=fake)
    assert result.skipped is True
    assert fake.create_calls == []


def test_publish_children_task_template_rejected_returns_error(monkeypatch):
    """Si la creación de Task bajo Feature falla → error empieza con 'task_under_feature_rejected'
    y created_ids contiene la Feature ya creada."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    from api.tickets import publish_epic_children

    class FakeAdoTaskFails(FakeAdo):
        def create_work_item(self, work_item_type, fields, parent_ado_id=None, **kwargs):
            if work_item_type == "Task":
                raise RuntimeError("Template ADO no permite Task bajo Feature")
            return super().create_work_item(work_item_type, fields, parent_ado_id=parent_ado_id, **kwargs)

    plan = _make_plan_one_feature_one_task()
    fake = FakeAdoTaskFails(next_id=500)
    result = publish_epic_children(epic_ado_id=111, children_plan=plan, project_name="P", ado=fake)
    assert result.error is not None
    assert result.error.startswith("task_under_feature_rejected")
    # La Feature SÍ fue creada
    assert len(result.created_ids) == 1
    feature_call = fake.create_calls[0]
    assert feature_call["work_item_type"] == "Feature"


# ═══════════════════════════════════════════════════════════════════════════════
# F4 — Endpoint POST /api/tickets/epic-children (creación tras aprobación)
# ═══════════════════════════════════════════════════════════════════════════════

def _patch_ado_for_endpoint(monkeypatch, fake_ado: FakeAdo):
    """Parchea build_ado_client en tickets para devolver el FakeAdo."""
    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "build_ado_client", lambda proj: fake_ado, raising=False)


def test_children_endpoint_flag_off(client, monkeypatch):
    """Con flag OFF → 200, enabled=False."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "false")
    resp = client.post(
        "/api/tickets/epic-children",
        json={"epic_ado_id": 1, "output": OUTPUT_WITH_ONE_RF, "project_name": "P"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is False
    assert data["created_ids"] == []


def test_children_endpoint_missing_epic_id_400(client, monkeypatch):
    """Body sin epic_ado_id → 400."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    resp = client.post(
        "/api/tickets/epic-children",
        json={"output": OUTPUT_WITH_ONE_RF, "project_name": "P"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "epic_ado_id_required"


def test_children_endpoint_creates_via_fake_ado(client, monkeypatch):
    """Flag ON + output con 1 RF + FakeAdo → 200, created_ids no vacío."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    fake = FakeAdo(next_id=600)
    _patch_ado_for_endpoint(monkeypatch, fake)
    resp = client.post(
        "/api/tickets/epic-children",
        json={"epic_ado_id": 42, "output": OUTPUT_WITH_ONE_RF, "project_name": "P"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is True
    assert len(data["created_ids"]) >= 1


def test_children_endpoint_rederives_server_side(client, monkeypatch):
    """El body puede traer un campo espurio 'children'; el backend lo ignora
    y deriva los hijos del output (re-derivación anti-tamper)."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    fake = FakeAdo(next_id=700)
    _patch_ado_for_endpoint(monkeypatch, fake)
    resp = client.post(
        "/api/tickets/epic-children",
        json={
            "epic_ado_id": 99,
            "output": OUTPUT_WITH_ONE_RF,
            "project_name": "P",
            # Campo espurio que debería ser ignorado.
            "children": [{"work_item_type": "Feature", "title": "INVENTADO POR CLIENTE"}],
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    # Los features creados salen del output, NO del campo espurio.
    titles_created = [c["fields"]["System.Title"] for c in fake.create_calls]
    assert "INVENTADO POR CLIENTE" not in titles_created


# ═══════════════════════════════════════════════════════════════════════════════
# §4bis — Anti-drift fingerprint
# ═══════════════════════════════════════════════════════════════════════════════

def _get_fingerprint_for_output(client, output: str, monkeypatch) -> str:
    """Llama al endpoint preview y retorna el plan_fingerprint devuelto."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    resp = client.post(
        "/api/tickets/epic-children-preview",
        json={"output": output, "brief": "b", "project_name": "P"},
    )
    data = resp.get_json()
    return data.get("plan_fingerprint", "")


def test_children_endpoint_rejects_plan_drift(client, monkeypatch):
    """Preview de output A → fingerprint Fa; POST a F4 con output modificado + approved_fingerprint=Fa → 409."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    fake = FakeAdo(next_id=800)
    _patch_ado_for_endpoint(monkeypatch, fake)

    # Obtener fingerprint del output original
    fp_a = _get_fingerprint_for_output(client, OUTPUT_WITH_ONE_RF, monkeypatch)
    assert fp_a, "El preview debe devolver plan_fingerprint"

    # POST con output DIFERENTE pero fingerprint del original → drift detectado
    resp = client.post(
        "/api/tickets/epic-children",
        json={
            "epic_ado_id": 10,
            "output": OUTPUT_WITH_TWO_RF,  # output distinto → plan distinto
            "project_name": "P",
            "approved_fingerprint": fp_a,
        },
    )
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error"] == "plan_drift"
    # No creó nada
    assert fake.create_calls == []


def test_children_endpoint_fingerprint_match_creates(client, monkeypatch):
    """Output A → approved_fingerprint correcto → crea normal."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    fake = FakeAdo(next_id=900)
    _patch_ado_for_endpoint(monkeypatch, fake)

    fp = _get_fingerprint_for_output(client, OUTPUT_WITH_ONE_RF, monkeypatch)

    resp = client.post(
        "/api/tickets/epic-children",
        json={
            "epic_ado_id": 11,
            "output": OUTPUT_WITH_ONE_RF,
            "project_name": "P",
            "approved_fingerprint": fp,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is True
    assert len(data["created_ids"]) >= 1


def test_children_endpoint_no_fingerprint_is_backward_compatible(client, monkeypatch):
    """Sin approved_fingerprint en el body → crea normal (backward-compatible con v1)."""
    monkeypatch.setenv("STACKY_EPIC_DECOMPOSITION_ENABLED", "true")
    fake = FakeAdo(next_id=950)
    _patch_ado_for_endpoint(monkeypatch, fake)

    resp = client.post(
        "/api/tickets/epic-children",
        json={"epic_ado_id": 12, "output": OUTPUT_WITH_ONE_RF, "project_name": "P"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is True
    assert len(data["created_ids"]) >= 1
