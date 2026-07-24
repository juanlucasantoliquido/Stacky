"""tests/test_mg_destination_writer.py — Plan 217 F4 (C1).

Valida `tools/migrar_mantis_gitlab/destination_writer.py` MOCKEANDO
`GitLabTrackerProvider` (nunca red real):
  (a) el writer fija `config.GITLAB_URL` al `destination.base_url` y
      `os.environ["GITLAB_TOKEN"]` al token pasado, ANTES de instanciar el
      provider.
  (b) `effective_target()` devuelve lo que el provider (mockeado) resolvió.
  (c) `assert_target_matches` NO lanza si coincide, y SÍ lanza
      `DestinationMismatchError` si el provider resolvió un destino viejo/
      vacío distinto al configurado (el fallo silencioso que blinda C1).
  (d) `DryRunGitLabWriter`: ninguna llamada real, IDs simulados,
      `simulated_ops` registra cada operación.
"""
from __future__ import annotations

import os

import pytest

import config as _config
from services.tracker_provider import TrackerQuery
from tools.migrar_mantis_gitlab import destination_writer as dw
from tools.migrar_mantis_gitlab.config_schema import DestinationAuthConfig, DestinationConfig


def _make_destination_config(
    base_url: str = "https://srvcgit01.imsolutions.local",
    project_path: str = "juanluca.santoliquido/ripley",
) -> DestinationConfig:
    return DestinationConfig(
        type="gitlab",
        base_url=base_url,
        project_path=project_path,
        auth=DestinationAuthConfig(auth_file="auth/gitlab_auth.json"),
    )


class _FakeGitLabClient:
    """Stub mínimo de GitLabClient: solo lo que destination_writer toca."""

    def __init__(self, base_url: str, project: str):
        self._base_url = base_url
        self._project_id = project

    def _project_path(self) -> str:
        return self._project_id

    def _request(self, method: str, path: str, json_body=None, params=None):
        return ({"iid": "1", "id": 1}, {})


class _FakeGitLabTrackerProvider:
    """Stub fiel al `__init__` REAL (`gitlab_provider.py:33-39`): resuelve
    `base_url` de `config.GITLAB_URL` y `project` del parámetro explícito
    (o `config.GITLAB_PROJECT` si no se pasa) — así el test de (a)/(b)
    verifica el cableado real, no un mock que ignora el config."""

    def __init__(self, project=None):
        base_url = getattr(_config, "GITLAB_URL", "") or ""
        proj = project or getattr(_config, "GITLAB_PROJECT", "") or ""
        self._client = _FakeGitLabClient(base_url, proj)
        self._project = proj
        self.created_items: list = []

    def create_item(self, item):
        self.created_items.append(item)
        return {"iid": "999"}

    def post_comment(self, item_iid, body):
        return {"id": "comment-1"}

    def upload_attachment(self, file_path, filename):
        return {"url": f"/uploads/x/{filename}"}

    def link_attachment(self, item_iid, attachment_meta):
        return {"iid": item_iid}

    def fetch_states(self):
        return ["opened", "closed"]

    def fetch_open_items(self, query):
        self.last_fetch_open_items_query = query
        return [{"iid": "1", "description": "algo"}]

    def comment_exists(self, item_id, marker):
        self.last_comment_exists_args = (item_id, marker)
        return marker == "ya-existe"


class _FakeProviderIgnoresConfig:
    """Simula el fallo silencioso de C1: ignora el config inyectado por el
    writer y resuelve un destino viejo/vacío hardcodeado (como si el
    provider hubiera leído un `config` global stale)."""

    def __init__(self, project=None):
        self._client = _FakeGitLabClient("https://old-stale-gitlab.local", "old/stale-project")
        self._project = "old/stale-project"

    def create_item(self, item):
        return {}

    def post_comment(self, item_iid, body):
        return {}

    def upload_attachment(self, file_path, filename):
        return {}

    def link_attachment(self, item_iid, attachment_meta):
        return {}

    def fetch_states(self):
        return []


@pytest.fixture(autouse=True)
def _patch_provider(monkeypatch):
    """Parchea el provider real y aísla las mutaciones globales que hace
    `GitLabDestinationWriter.__init__` (`config.GITLAB_URL`/`GITLAB_PROJECT`
    y `os.environ["GITLAB_TOKEN"]`) para que no se filtren entre tests si
    algún día se corren en el mismo proceso (el runner oficial del arnés ya
    corre cada archivo en un subproceso propio, pero esto es defensivo)."""
    monkeypatch.setattr(dw, "GitLabTrackerProvider", _FakeGitLabTrackerProvider)
    monkeypatch.setattr(_config, "GITLAB_URL", "", raising=False)
    monkeypatch.setattr(_config, "GITLAB_PROJECT", "", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    yield


# ── (a) config.GITLAB_URL + os.environ["GITLAB_TOKEN"] ────────────────────


def test_writer_fija_config_gitlab_url_al_destino_del_config():
    dest = _make_destination_config(base_url="https://gitlab.acme.local")
    dw.GitLabDestinationWriter(dest, token="tok-123")
    assert _config.GITLAB_URL == "https://gitlab.acme.local"


def test_writer_fija_env_gitlab_token_al_token_pasado():
    dest = _make_destination_config()
    dw.GitLabDestinationWriter(dest, token="super-secreto-xyz")
    assert os.environ["GITLAB_TOKEN"] == "super-secreto-xyz"


# ── (b) effective_target() ─────────────────────────────────────────────────


def test_effective_target_devuelve_lo_que_el_provider_resolvio():
    dest = _make_destination_config(base_url="https://gitlab.acme.local", project_path="grupo/repo")
    writer = dw.GitLabDestinationWriter(dest, token="tok")
    assert writer.effective_target() == ("https://gitlab.acme.local", "grupo/repo")


# ── (c) gate anti-destino-equivocado ───────────────────────────────────────


def test_assert_target_matches_no_lanza_si_coincide():
    dest = _make_destination_config()
    writer = dw.GitLabDestinationWriter(dest, token="tok")
    dw.assert_target_matches(writer, dest)  # no debe lanzar


def test_assert_target_matches_lanza_si_provider_resuelve_destino_viejo(monkeypatch):
    monkeypatch.setattr(dw, "GitLabTrackerProvider", _FakeProviderIgnoresConfig)
    dest = _make_destination_config()
    writer = dw.GitLabDestinationWriter(dest, token="tok")

    with pytest.raises(dw.DestinationMismatchError) as excinfo:
        dw.assert_target_matches(writer, dest)

    mensaje = str(excinfo.value)
    assert "old-stale-gitlab.local" in mensaje
    assert dest.base_url in mensaje


# ── (d) DryRunGitLabWriter ──────────────────────────────────────────────────


def test_dry_run_writer_no_llama_nada_real_y_registra_simulated_ops():
    dest = _make_destination_config()
    writer = dw.DryRunGitLabWriter(dest)

    created = writer.create_item({"title": "Issue simulado"})
    assert created["iid"].startswith("dryrun-")

    writer.post_comment(created["iid"], "hola")
    uploaded = writer.upload_attachment("/tmp/x.png", "x.png")
    writer.link_attachment(created["iid"], {"url": uploaded["url"]})
    writer.create_issue_link(created["iid"], "otra-iid-simulada", "relates_to")

    assert len(writer.simulated_ops) == 5
    kinds = [op["op"] for op in writer.simulated_ops]
    assert kinds == [
        "create_item",
        "post_comment",
        "upload_attachment",
        "link_attachment",
        "create_issue_link",
    ]
    # IDs simulados, nunca reales/None.
    assert all(
        (op.get("id") or op.get("iid") or "").startswith(("dryrun-",)) or op["op"] == "link_attachment"
        for op in writer.simulated_ops
    )


def test_dry_run_writer_fetch_states_y_effective_target_no_tocan_provider_real():
    dest = _make_destination_config(base_url="https://gitlab.acme.local", project_path="grupo/repo")
    writer = dw.DryRunGitLabWriter(dest)
    assert writer.fetch_states() == []
    assert writer.effective_target() == ("https://gitlab.acme.local", "grupo/repo")


# ── (e) fetch_open_items / comment_exists (Batch 4, Paso 0) ────────────────


def test_fetch_open_items_llama_al_provider_con_state_all():
    dest = _make_destination_config()
    writer = dw.GitLabDestinationWriter(dest, token="tok")
    items = writer.fetch_open_items()

    assert items == [{"iid": "1", "description": "algo"}]
    assert writer._provider.last_fetch_open_items_query == TrackerQuery(state="all")


def test_comment_exists_delega_en_el_provider():
    dest = _make_destination_config()
    writer = dw.GitLabDestinationWriter(dest, token="tok")

    assert writer.comment_exists("42", "ya-existe") is True
    assert writer.comment_exists("42", "no-existe") is False
    assert writer._provider.last_comment_exists_args == ("42", "no-existe")


def test_dry_run_writer_fetch_open_items_refleja_create_item_simulados():
    dest = _make_destination_config()
    writer = dw.DryRunGitLabWriter(dest)

    created = writer.create_item({"title": "x", "description": "desc <!-- marker -->"})
    assert writer.fetch_open_items() == [
        {"iid": created["iid"], "description": "desc <!-- marker -->"}
    ]


def test_dry_run_writer_comment_exists_refleja_post_comment_simulados():
    dest = _make_destination_config()
    writer = dw.DryRunGitLabWriter(dest)
    created = writer.create_item({"title": "x"})

    assert writer.comment_exists(created["iid"], "marker-x") is False
    writer.post_comment(created["iid"], "hola marker-x")
    assert writer.comment_exists(created["iid"], "marker-x") is True
