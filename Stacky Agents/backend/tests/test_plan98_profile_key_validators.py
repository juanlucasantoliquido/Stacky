"""tests/test_plan98_profile_key_validators.py — Plan 98 F1, validadores por-key
EXTRAIDOS del PUT a services/client_profile_keys.py (paridad de mensajes)."""
from services.client_profile_keys import PATCHABLE_PROFILE_KEYS, validate_profile_key

_KEYS = (
    "devops_pipeline_drafts",
    "devops_publication_presets",
    "devops_publication_settings",
    "devops_environment_settings",
)


def test_allowlist_frozen_exact():
    assert PATCHABLE_PROFILE_KEYS == frozenset(_KEYS)


def test_none_is_valid_for_every_key():
    for key in _KEYS:
        assert validate_profile_key(key, None) is None


def test_unknown_key_rejected():
    assert validate_profile_key("language", []) is not None


def test_drafts_invalid_cases():
    assert validate_profile_key("devops_pipeline_drafts", "no-lista") == \
        "devops_pipeline_drafts debe ser una lista."
    many = [{"name": f"d{i}", "spec": {}} for i in range(51)]
    assert validate_profile_key("devops_pipeline_drafts", many) == \
        "devops_pipeline_drafts: maximo 50 borradores."
    assert validate_profile_key("devops_pipeline_drafts", [{"spec": {}}]) == \
        "devops_pipeline_drafts[0].name es obligatorio (string no vacio)."
    dup = [{"name": "d1", "spec": {}}, {"name": "d1", "spec": {}}]
    assert validate_profile_key("devops_pipeline_drafts", dup) == \
        "devops_pipeline_drafts[1].name duplicado: 'd1'."
    assert validate_profile_key("devops_pipeline_drafts", [{"name": "d1", "spec": "no-dict"}]) == \
        "devops_pipeline_drafts[0].spec debe ser un objeto."


def test_presets_invalid_cases():
    assert validate_profile_key(
        "devops_publication_presets",
        [{"name": "p1", "mode": "raro"}],
    ) == "devops_publication_presets[0].mode debe ser 'selection' o 'todo'."
    assert validate_profile_key(
        "devops_publication_presets",
        [{"name": "p1", "mode": "selection", "process_names": [], "groups": ["no-existe"]}],
    ) == "devops_publication_presets[0].groups: subset de ['agenda', 'batch']."
    assert validate_profile_key(
        "devops_publication_presets",
        [{"name": "p1", "mode": "selection", "process_names": [], "groups": [], "target": "raro"}],
    ) == "devops_publication_presets[0].target debe ser 'ado' o 'gitlab'."
    assert validate_profile_key(
        "devops_publication_presets",
        [{"name": "p1", "mode": "selection", "groups": []}],
    ) == "devops_publication_presets[0].process_names debe ser una lista en mode=selection."


def test_settings_invalid_cases():
    assert validate_profile_key(
        "devops_publication_settings",
        {"step_templates": {"raro": "x"}},
    ) == "step_templates: keys en {entry,processing,output,default} y valores string."
    assert validate_profile_key(
        "devops_publication_settings",
        {"step_templates": {"entry": 123}},
    ) == "step_templates: keys en {entry,processing,output,default} y valores string."


def test_environment_invalid_cases():
    assert validate_profile_key(
        "devops_environment_settings",
        {"environment_root": "relativo/sin/raiz"},
    ) is not None
    assert validate_profile_key(
        "devops_environment_settings",
        {"folder_layout": {"raro": []}},
    ) == "folder_layout: keys en {entry,processing,output,default}."
    assert validate_profile_key(
        "devops_environment_settings",
        {"per_process_subfolder": "no-bool"},
    ) == "per_process_subfolder debe ser booleano."


def test_put_uses_shared_validators_same_errors(monkeypatch):
    import config as cfg
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    from project_manager import get_project_config
    monkeypatch.setattr(
        "api.client_profile.get_project_config",
        lambda name: {"workspace_root": "/tmp/x"},
    )
    monkeypatch.setattr(
        "api.client_profile.load_client_profile",
        lambda name: None,
    )

    resp = client.put(
        "/api/projects/demo/client-profile",
        json={"profile": {"devops_pipeline_drafts": "no-lista"}},
    )
    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "devops_pipeline_drafts debe ser una lista.",
    }
