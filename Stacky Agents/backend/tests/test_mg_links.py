"""tests/test_mg_links.py — Plan 217 Batch 4, F6b.

Valida `tools/migrar_mantis_gitlab/migrator_mg_links.py`:
  - relaciones resueltas cuando ambos extremos están mapeados.
  - relación saltada (con warning) cuando el target no está mapeado todavía.
  - traducción correcta de cada tipo Mantis -> GitLab según
    `field_mapping.relationships` del config.
  - comentario extra para "duplicate_of"/"has_duplicate" (sin equivalente
    nativo en GitLab).
  - `parent_child` se saltea siempre (se resuelve en create_item, no acá).
  - shape real del adapter (`target_issue_id`, sin `target_mantis_id`)
    también funciona (fallback documentado).
"""
from __future__ import annotations

from tools.migrar_mantis_gitlab.migrator_mg_links import migrate_relationships

_FIELD_MAPPING_RELATIONSHIPS = {
    "parent_child": "gitlab_epic_issue_link",
    "related_to": "relates_to",
    "duplicate_of": "relates_to",
    "has_duplicate": "relates_to",
    "depends_on": "blocks",
    "blocks": "blocks",
}


class _FakeWriter:
    def __init__(self, *, fail_link_for: "set[tuple[str, str]] | None" = None) -> None:
        self.links: list[tuple[str, str, str]] = []
        self.comments: list[tuple[str, str]] = []
        self._fail_link_for = fail_link_for or set()

    def create_issue_link(self, source_iid, target_iid, link_type):
        if (source_iid, target_iid) in self._fail_link_for:
            raise RuntimeError("fallo simulado creando el link")
        self.links.append((source_iid, target_iid, link_type))
        return {"id": f"link-{len(self.links)}"}

    def post_comment(self, item_iid, body):
        self.comments.append((item_iid, body))
        return {"id": f"comment-{len(self.comments)}"}


# ── Ambos extremos mapeados: se crea el link ────────────────────────────


def test_migra_relacion_related_to_cuando_ambos_extremos_estan_mapeados():
    writer = _FakeWriter()
    mapping_lookup = {"100": "iid-100", "200": "iid-200"}
    relationships = [
        {"type": "related_to", "source_mantis_id": "100", "target_mantis_id": "200"},
    ]

    results = migrate_relationships(
        relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS
    )

    assert results == [{"status": "migrated", "type": "related_to", "link_type": "relates_to"}]
    assert writer.links == [("iid-100", "iid-200", "relates_to")]
    assert writer.comments == []  # related_to SÍ tiene equivalente nativo


# ── Target no migrado todavía: se saltea con warning ────────────────────


def test_relacion_saltada_si_target_no_esta_mapeado_todavia():
    writer = _FakeWriter()
    mapping_lookup = {"100": "iid-100"}  # "300" (target) NO está mapeado
    relationships = [
        {"type": "related_to", "source_mantis_id": "100", "target_mantis_id": "300"},
    ]

    results = migrate_relationships(
        relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS
    )

    assert len(results) == 1
    assert results[0]["status"] == "skipped"
    assert "300" in results[0]["reason"]
    assert writer.links == []


def test_relacion_saltada_si_source_no_esta_mapeado_todavia():
    writer = _FakeWriter()
    mapping_lookup = {"200": "iid-200"}  # "100" (source) NO está mapeado
    relationships = [
        {"type": "related_to", "source_mantis_id": "100", "target_mantis_id": "200"},
    ]

    results = migrate_relationships(
        relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS
    )

    assert len(results) == 1
    assert results[0]["status"] == "skipped"
    assert "100" in results[0]["reason"]
    assert writer.links == []


# ── Traducción de cada tipo Mantis -> GitLab ─────────────────────────────


def test_traduccion_de_cada_tipo_mantis_a_gitlab():
    writer = _FakeWriter()
    mapping_lookup = {"1": "iid-1", "2": "iid-2"}
    tipos = ["related_to", "depends_on", "blocks"]
    relationships = [
        {"type": t, "source_mantis_id": "1", "target_mantis_id": "2"} for t in tipos
    ]

    results = migrate_relationships(
        relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS
    )

    assert [r["link_type"] for r in results] == ["relates_to", "blocks", "blocks"]
    assert writer.links == [
        ("iid-1", "iid-2", "relates_to"),
        ("iid-1", "iid-2", "blocks"),
        ("iid-1", "iid-2", "blocks"),
    ]


def test_tipo_sin_mapeo_en_field_mapping_relationships_falla_sin_explotar():
    writer = _FakeWriter()
    mapping_lookup = {"1": "iid-1", "2": "iid-2"}
    relationships = [{"type": "tipo_inventado", "source_mantis_id": "1", "target_mantis_id": "2"}]

    results = migrate_relationships(relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS)

    assert results[0]["status"] == "failed"
    assert "tipo_inventado" in results[0]["error"]
    assert writer.links == []


# ── duplicate_of / has_duplicate: link + comentario extra ──────────────


def test_duplicate_of_crea_link_relates_to_y_comentario_con_tipo_original():
    writer = _FakeWriter()
    mapping_lookup = {"1": "iid-1", "2": "iid-2"}
    relationships = [{"type": "duplicate_of", "source_mantis_id": "1", "target_mantis_id": "2"}]

    results = migrate_relationships(relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS)

    assert results == [{"status": "migrated", "type": "duplicate_of", "link_type": "relates_to"}]
    assert writer.links == [("iid-1", "iid-2", "relates_to")]
    assert len(writer.comments) == 1
    assert writer.comments[0][0] == "iid-1"
    assert "duplicate_of" in writer.comments[0][1]


def test_has_duplicate_tambien_agrega_comentario_extra():
    writer = _FakeWriter()
    mapping_lookup = {"1": "iid-1", "2": "iid-2"}
    relationships = [{"type": "has_duplicate", "source_mantis_id": "1", "target_mantis_id": "2"}]

    migrate_relationships(relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS)

    assert len(writer.comments) == 1
    assert "has_duplicate" in writer.comments[0][1]


# ── parent_child: nunca pasa por Issue Links ─────────────────────────────


def test_parent_child_se_saltea_siempre_no_crea_issue_link():
    writer = _FakeWriter()
    mapping_lookup = {"1": "iid-1", "2": "iid-2"}
    relationships = [{"type": "parent_child", "source_mantis_id": "1", "target_mantis_id": "2"}]

    results = migrate_relationships(relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS)

    assert results[0]["status"] == "skipped"
    assert "create_item" in results[0]["reason"]
    assert writer.links == []
    assert writer.comments == []


# ── Fallback de shape real del adapter (target_issue_id) ────────────────


def test_acepta_target_issue_id_shape_real_del_scraping_adapter():
    writer = _FakeWriter()
    mapping_lookup = {"1": "iid-1", "2": "iid-2"}
    # Shape REAL de `_parse_relationships_html`: sin `target_mantis_id`.
    relationships = [{"type": "related_to", "source_mantis_id": "1", "target_issue_id": 2}]

    results = migrate_relationships(relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS)

    assert results == [{"status": "migrated", "type": "related_to", "link_type": "relates_to"}]
    assert writer.links == [("iid-1", "iid-2", "relates_to")]


def test_relacion_sin_source_ni_target_resolubles_falla_sin_explotar():
    writer = _FakeWriter()
    relationships = [{"type": "related_to"}]  # sin source_mantis_id ni target

    results = migrate_relationships(relationships, writer, {}, _FIELD_MAPPING_RELATIONSHIPS)

    assert results[0]["status"] == "failed"
    assert writer.links == []


# ── Falla al crear el link: se reporta, no explota ──────────────────────


def test_fallo_al_crear_el_link_se_reporta_como_failed():
    writer = _FakeWriter(fail_link_for={("iid-1", "iid-2")})
    mapping_lookup = {"1": "iid-1", "2": "iid-2"}
    relationships = [{"type": "related_to", "source_mantis_id": "1", "target_mantis_id": "2"}]

    results = migrate_relationships(relationships, writer, mapping_lookup, _FIELD_MAPPING_RELATIONSHIPS)

    assert results[0]["status"] == "failed"
    assert "fallo simulado" in results[0]["error"]
