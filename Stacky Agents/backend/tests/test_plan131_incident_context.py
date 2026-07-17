"""tests/test_plan131_incident_context.py — Plan 131 F3.

Manifest de adjuntos + catálogo de épicas. CERO red: todo con tmp_path y
providers fake.
"""
import runtime_paths
from services import incident_context, incident_store


def _make_incident(tmp_path, monkeypatch, text, files):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return incident_store.create_incident(text, files)


def test_manifest_image_and_log(tmp_path, monkeypatch):
    incident = _make_incident(
        tmp_path, monkeypatch, "la pantalla se rompe",
        [("captura.png", b"\x89PNG-fake"), ("error.log", b"traceback linea 1\nlinea 2")],
    )
    manifest = incident_context.build_attachments_manifest(incident)
    assert "<attachments-manifest>" in manifest
    assert "captura.png" in manifest
    assert str(tmp_path) in manifest  # ruta absoluta presente
    assert "traceback linea 1" in manifest  # inline del log
    assert "Si tu runtime puede leer imágenes del disco" in manifest
    assert "[PENDIENTE: verificar captura" in manifest


def test_manifest_truncation_per_file_and_total(tmp_path, monkeypatch):
    big_log = ("x" * 20_000).encode("utf-8")
    incident = _make_incident(tmp_path, monkeypatch, "x", [("big.log", big_log)])
    manifest = incident_context.build_attachments_manifest(incident)
    assert "[TRUNCADO: quedaron 12000 bytes sin mostrar]" in manifest

    files = [(f"f{i}.log", (f"y{i}" * 4000).encode("utf-8")) for i in range(6)]
    incident2 = _make_incident(tmp_path, monkeypatch, "x", files)
    manifest2 = incident_context.build_attachments_manifest(incident2)
    inline_section = manifest2.split("--- Contenido de archivos de texto (inline, truncado) ---")[1]
    inline_section = inline_section.split("</attachments-manifest>")[0]
    # Cada archivo real mide 8000 chars; con 6 archivos, el total inline no
    # puede superar 40000 chars sumados (cap _INLINE_MAX_TOTAL).
    per_file_bodies = [
        line for line in inline_section.split("\n")
        if line and not line.startswith("###") and not line.startswith("[TRUNCADO")
    ]
    total_inline_chars = sum(len(b) for b in per_file_bodies)
    assert total_inline_chars <= 40_000


def test_fetch_epic_catalog_uses_fetch_epics_when_present():
    calls = {"fetch_open_items": 0}

    class FakeProviderWithEpics:
        def fetch_epics(self, limit=50):
            return [{"id": 267, "title": "Mul2Bane", "state": "open"}]

        def fetch_open_items(self, query):
            calls["fetch_open_items"] += 1
            return []

    catalog = incident_context.fetch_epic_catalog(FakeProviderWithEpics())
    assert catalog == [{"id": 267, "title": "Mul2Bane", "state": "open"}]
    assert calls["fetch_open_items"] == 0


def test_fetch_epic_catalog_gitlab_style_labels_substring():
    class FakeGitLabProvider:
        def fetch_open_items(self, query):
            return [
                {"iid": "5", "title": "Epica GitLab", "state": "opened", "labels": ["type::epic"]},
                {"iid": "6", "title": "No es epica", "state": "opened", "labels": ["bug"]},
            ]

    catalog = incident_context.fetch_epic_catalog(FakeGitLabProvider())
    assert catalog == [{"id": "5", "title": "Epica GitLab", "state": "opened"}]


def test_fetch_epic_catalog_provider_raises_returns_empty():
    class FakeBrokenProvider:
        def fetch_open_items(self, query):
            raise RuntimeError("tracker caído")

    assert incident_context.fetch_epic_catalog(FakeBrokenProvider()) == []


def test_fetch_epic_catalog_empty_everything():
    class FakeEmptyProvider:
        def fetch_open_items(self, query):
            return []

    assert incident_context.fetch_epic_catalog(FakeEmptyProvider()) == []


def test_build_epic_catalog_block_empty_says_ninguna():
    block = incident_context.build_epic_catalog_block([])
    assert "EPICA: ninguna" in block
    assert "<epic-catalog>" in block
    assert "</epic-catalog>" in block


def test_build_incident_prompt_order_and_verbatim(tmp_path, monkeypatch):
    incident = _make_incident(tmp_path, monkeypatch, "texto verbatim del operador", [])
    catalog = [{"id": 267, "title": "Mul2Bane", "state": "open"}]
    prompt = incident_context.build_incident_prompt(incident, catalog)

    assert "texto verbatim del operador" in prompt
    idx_text = prompt.index("texto verbatim del operador")
    idx_manifest = prompt.index("<attachments-manifest>")
    idx_catalog = prompt.index("<epic-catalog>")
    assert idx_text < idx_manifest < idx_catalog


def test_ado_fetch_epics_normalizes_excludes_done_respects_limit(monkeypatch):
    from services.ado_provider import AdoTrackerProvider

    class FakeAdoClient:
        def fetch_open_work_items(self, wiql=None):
            return [
                {"id": 267, "fields": {
                    "System.Title": "Mul2Bane", "System.State": "Doing",
                    "System.WorkItemType": "Epic",
                }},
                {"id": 300, "fields": {
                    "System.Title": "Ya cerrada", "System.State": "Done",
                    "System.WorkItemType": "Epic",
                }},
                {"id": 301, "fields": {
                    "System.Title": "AgendaWeb", "System.State": "New",
                    "System.WorkItemType": "Epic",
                }},
            ]

    monkeypatch.setattr(
        "services.ado_provider.build_ado_client",
        lambda project_name=None: FakeAdoClient(),
    )
    provider = AdoTrackerProvider(project="demo")

    catalog = provider.fetch_epics(limit=50)
    ids = {c["id"] for c in catalog}
    assert 300 not in ids  # excluida por estado terminal "Done"
    assert ids == {267, 301}
    for item in catalog:
        assert set(item) == {"id", "title", "state"}

    limited = provider.fetch_epics(limit=1)
    assert len(limited) == 1
