"""tests/test_mg_core.py — Plan 217 F4.

Valida `tools/migrar_mantis_gitlab/migrator_mg_core.plan_migration` con un
adapter FAKE que SOLO implementa métodos `fetch_*` (ningún método de
escritura) — si `plan_migration` intentara escribir algo, explotaría por
`AttributeError` contra este fake. Esa ausencia de excepción ES la prueba
de que el dry-run es real (invariante READ-ONLY), no una promesa de diseño.
"""
from __future__ import annotations

from tools.migrar_mantis_gitlab.migrator_mg_core import compute_plan_hash, plan_migration

_FIELD_MAPPING = {
    "status": {
        "new": {"gitlab_state": "opened", "label": "status::new"},
        "assigned": {"gitlab_state": "opened", "label": "status::assigned"},
        "resolved": {"gitlab_state": "closed", "label": "status::resolved"},
        "closed": {"gitlab_state": "closed", "label": "status::closed"},
        "_unmapped_fallback": {"gitlab_state": "opened", "label": "status::sin_mapear"},
    },
    "priority": {
        "label_prefix": "priority::",
        "scale": {"1": "P1-critica", "2": "P2-alta", "3": "P3-normal", "4": "P4-baja", "5": "P5-trivial"},
    },
    "severity": {"label_prefix": "severity::"},
    "category": {"label_prefix": "category::"},
    "tags": {"label_prefix": "tag::"},
    "version": {},
    "custom_fields": {"mode": "metadata_block"},
}

_USER_MAPPING = {"default_fallback": "unassigned", "map": {}}


class _FakeMantisReadAdapter:
    """SOLO tiene métodos fetch_* — sin create_item/post_comment/etc.
    Si el core intentara escribir algo, fallaría por AttributeError."""

    def __init__(self, issues: list[dict], relationships_by_id: dict[int, list[dict]]):
        self._issues = issues
        self._relationships_by_id = relationships_by_id

    def fetch_all_issues(self) -> list[dict]:
        return self._issues

    def fetch_comments(self, issue_id: int) -> list[dict]:
        return []

    def fetch_attachments(self, issue_id: int) -> list[dict]:
        return []

    def fetch_relationships(self, issue_id: int) -> list[dict]:
        return self._relationships_by_id.get(issue_id, [])


def _build_adapter() -> _FakeMantisReadAdapter:
    issues = [
        {
            "id": 101,
            "project_id": 310,
            "summary": "Issue raíz sin padre",
            "status": "new",
            "priority": 40,  # high -> escala 2
        },
        {
            "id": 102,
            "project_id": 310,
            "summary": "Issue hijo de 101",
            "status": "assigned",
            "priority": 50,  # urgent -> escala 1
        },
        {
            "id": 103,
            "project_id": 310,
            "summary": "Ya migrado (done, debe saltearse)",
            "status": "resolved",
            "priority": 30,
        },
        {
            "id": 104,
            "project_id": 310,
            "summary": "Falló parcialmente antes (partial, debe re-planificarse)",
            "status": "closed",
            "priority": 20,  # low -> escala 5
        },
    ]
    relationships_by_id = {
        102: [{"type": "child of", "target_issue_id": 101}],
    }
    return _FakeMantisReadAdapter(issues, relationships_by_id)


def _existing_map() -> dict:
    return {"103": "done", "104": "partial"}


def test_plan_migration_no_escribe_nada_con_fake_adapter_solo_lectura():
    """Si `plan_migration` intentara llamar create_item/post_comment/etc.
    contra este fake, la ausencia del método haría explotar la prueba con
    AttributeError. Que la corrida termine OK es la prueba de dry-run real."""
    adapter = _build_adapter()
    plan = plan_migration(adapter, _existing_map(), _FIELD_MAPPING, _USER_MAPPING)
    assert plan is not None
    assert all(op.op_kind == "create_item" for op in plan.ops)


def test_plan_migration_orden_topologico_padres_antes_que_hijos():
    adapter = _build_adapter()
    plan = plan_migration(adapter, _existing_map(), _FIELD_MAPPING, _USER_MAPPING)
    ids_en_orden = [op.mantis_issue_id for op in plan.ops]
    # 101 y 104 no tienen padre (rank 0); 102 tiene padre=101 (rank 1).
    assert ids_en_orden == ["101", "104", "102"]
    op_102 = next(op for op in plan.ops if op.mantis_issue_id == "102")
    assert op_102.dest_parent_mantis_id == "101"
    op_101 = next(op for op in plan.ops if op.mantis_issue_id == "101")
    assert op_101.dest_parent_mantis_id is None


def test_plan_migration_skipped_at_plan_cuenta_solo_los_done():
    adapter = _build_adapter()
    plan = plan_migration(adapter, _existing_map(), _FIELD_MAPPING, _USER_MAPPING)
    # 103 (done) se saltea; 104 (partial) SE RE-PLANIFICA (no cuenta como skip).
    assert plan.skipped_at_plan == 1
    assert "103" not in [op.mantis_issue_id for op in plan.ops]
    assert "104" in [op.mantis_issue_id for op in plan.ops]


def test_plan_migration_counts_by_type():
    adapter = _build_adapter()
    plan = plan_migration(adapter, _existing_map(), _FIELD_MAPPING, _USER_MAPPING)
    assert plan.counts_by_type == {"create_item": 3}


def test_compute_plan_hash_es_determinista_mismo_plan_mismo_hash():
    adapter1 = _build_adapter()
    adapter2 = _build_adapter()
    plan1 = plan_migration(adapter1, _existing_map(), _FIELD_MAPPING, _USER_MAPPING)
    plan2 = plan_migration(adapter2, _existing_map(), _FIELD_MAPPING, _USER_MAPPING)
    assert compute_plan_hash(plan1) == compute_plan_hash(plan2)


def test_compute_plan_hash_cambia_si_un_issue_es_distinto():
    adapter = _build_adapter()
    plan_base = plan_migration(adapter, _existing_map(), _FIELD_MAPPING, _USER_MAPPING)

    # Existing map distinto: ahora 104 también está "done" -> plan con 1 issue menos.
    otro_existing_map = {"103": "done", "104": "done"}
    adapter2 = _build_adapter()
    plan_distinto = plan_migration(adapter2, otro_existing_map, _FIELD_MAPPING, _USER_MAPPING)

    assert compute_plan_hash(plan_base) != compute_plan_hash(plan_distinto)


def test_plan_migration_status_sin_mapeo_usa_fallback_y_registra_warning():
    issues = [{"id": 201, "project_id": 311, "summary": "Status raro", "status": "estado_no_mapeado"}]
    adapter = _FakeMantisReadAdapter(issues, {})
    plan = plan_migration(adapter, {}, _FIELD_MAPPING, _USER_MAPPING)
    op = plan.ops[0]
    assert op.payload["state"] == "opened"
    assert "status::sin_mapear" in op.payload["labels"]
    assert any("estado_no_mapeado" in w for w in plan.warnings)


def test_plan_migration_marker_contiene_project_id_e_issue_id():
    adapter = _build_adapter()
    plan = plan_migration(adapter, {}, _FIELD_MAPPING, _USER_MAPPING)
    op_101 = next(op for op in plan.ops if op.mantis_issue_id == "101")
    assert op_101.marker == "<!-- stacky-migrated:mantis:310:101 -->"
    assert op_101.marker in op_101.payload["description"]


# ── Comentarios y adjuntos en el plan (regresión: faltaban por completo) ──


class _FakeAdapterConNotasYAdjuntos(_FakeMantisReadAdapter):
    """Adapter con notas/adjuntos, para verificar que el plan los incluye."""

    def fetch_comments(self, issue_id: int) -> list[dict]:
        return [
            {"id": "9001", "reporter": "Usuario Ejemplo",
             "date": "13/01/2026 10:00", "text": "Primera nota.", "private": False},
            {"id": "9002", "reporter": "otro.demo",
             "date": "14/01/2026 11:30", "text": "Segunda nota.", "private": False},
        ]

    def fetch_attachments(self, issue_id: int) -> list[dict]:
        return [{"id": "501", "name": "captura.png", "size": 1024, "url": "file_download.php?file_id=501"}]


def test_plan_incluye_comentarios_y_adjuntos():
    """El plan generaba SOLO create_item: los comentarios y adjuntos no se
    migraban en absoluto, pese a ser criterio de aceptación (§18). Peor: al
    quedar el issue marcado `done` por su marker, una corrida posterior lo
    salteaba por idempotencia y ya no había forma de rellenarlos."""
    adapter = _FakeAdapterConNotasYAdjuntos(
        [{"id": 1001, "project_id": 310, "summary": "Uno", "status": "new", "priority": "normal"}],
        {},
    )

    plan = plan_migration(adapter, {}, _FIELD_MAPPING, _USER_MAPPING)

    assert plan.counts_by_type["create_item"] == 1
    assert plan.counts_by_type["post_comment"] == 2
    assert plan.counts_by_type["upload_attachment"] == 1

    kinds = [op.op_kind for op in plan.ops]
    assert kinds[0] == "create_item", "el issue debe crearse ANTES de sus notas/adjuntos"

    # Cada nota/adjunto lleva marker PROPIO: si compartieran el del issue,
    # re-ejecutar duplicaría comentarios en los issues ya migrados.
    markers = [op.marker for op in plan.ops]
    assert len(set(markers)) == len(markers), "markers duplicados entre ops"

    comment_op = next(op for op in plan.ops if op.op_kind == "post_comment")
    # La autoría original de Mantis se preserva en el cuerpo (§6).
    assert "Usuario Ejemplo" in comment_op.payload["body"]
    assert "Primera nota." in comment_op.payload["body"]

    attach_op = next(op for op in plan.ops if op.op_kind == "upload_attachment")
    # Solo metadatos serializables: el binario se descarga en ejecución.
    assert attach_op.payload["attachment_meta"]["id"] == "501"


# ── El plan debe leer el DETALLE, no solo el listado (bug en produccion) ──


class _FakeAdapterListadoYDetalle(_FakeMantisReadAdapter):
    """El listado de Mantis NO trae descripción/reporter/handler: viven en la
    página de detalle. Este fake reproduce esa asimetría real."""

    def fetch_issue_detail(self, issue_id: int) -> dict:
        return {
            "id": issue_id,
            "description": "Cuerpo real del ticket.",
            "steps_to_reproduce": "1. Abrir. 2. Fallar.",
            "reporter": "Xavier Torres",
            "handler": "otro.usuario",
            "date_submitted": "10/01/2026 09:15",
            "notes": [],
            "attachments": [],
            "relationships": [],
        }

    def fetch_comments(self, issue_id: int) -> list[dict]:
        return [{"id": "1", "reporter": "a", "date": "d", "text": "publica", "private": False},
                {"id": "2", "reporter": "b", "date": "d", "text": "interna", "private": True}]


def test_plan_toma_descripcion_y_autoria_del_detalle():
    """La migración real de Ripley creó 52 issues con el CUERPO VACÍO: el
    plan armaba el payload solo con la fila del listado (id/título/estado/
    prioridad/severidad/categoría) y nunca consultaba `fetch_issue_detail`,
    donde viven descripción, reporter, handler y pasos."""
    adapter = _FakeAdapterListadoYDetalle(
        [{"id": 1001, "project_id": 310, "summary": "Titulo", "status": "new", "priority": "normal"}],
        {},
    )

    plan = plan_migration(adapter, {}, _FIELD_MAPPING, _USER_MAPPING)
    create = next(op for op in plan.ops if op.op_kind == "create_item")
    desc = create.payload["description"]

    assert "Cuerpo real del ticket." in desc
    assert "1. Abrir. 2. Fallar." in desc
    # Autoría preservada: GitLab atribuye el issue al dueño del token.
    assert "Xavier Torres" in desc
    assert "10/01/2026" in desc
    # El título sigue viniendo del listado.
    assert create.payload["title"] == "Titulo"


def test_notas_privadas_de_mantis_quedan_marcadas():
    """GitLab no tiene equivalente de 'nota privada' en issues: si se migran
    sin marca, notas internas quedan indistinguibles de las públicas."""
    adapter = _FakeAdapterListadoYDetalle(
        [{"id": 1001, "project_id": 310, "summary": "T", "status": "new", "priority": "normal"}],
        {},
    )

    plan = plan_migration(adapter, {}, _FIELD_MAPPING, _USER_MAPPING)
    cuerpos = [op.payload["body"] for op in plan.ops if op.op_kind == "post_comment"]

    assert any("NOTA PRIVADA" in c and "interna" in c for c in cuerpos)
    assert all("NOTA PRIVADA" not in c for c in cuerpos if "publica" in c)
