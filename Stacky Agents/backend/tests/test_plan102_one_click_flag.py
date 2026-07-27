"""Plan 102 F0 — flag STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED (6 patas, default OFF).

Default OFF citando la EXCEPCION DURA (1): el orquestador comprime DOS side effects
externos reales (commit al repo + disparo de pipeline) detras de un unico confirm.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = "STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED"


def test_flag_registrada():
    from services.harness_flags import FLAG_REGISTRY

    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)
    assert spec is not None, f"{KEY} no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.env_only is False, "debe ser editable por UI"


def test_flag_categorizada_en_devops():
    from services.harness_flags import _CATEGORY_KEYS

    assert KEY in _CATEGORY_KEYS["devops"]


def test_requires_apunta_al_panel_no_a_publicaciones():
    """R4: profundidad maxima 1 — el master apuntado no puede tener `requires`.

    STACKY_DEVOPS_PUBLICATIONS_ENABLED declara requires=PANEL, asi que apuntarle
    seria cadena prohibida. Este caso es el que impide que alguien lo "arregle"
    apuntando a Publicaciones porque suena mas preciso.
    """
    from services.harness_flags import FLAG_REGISTRY

    registry = {s.key: s for s in FLAG_REGISTRY}
    spec = registry[KEY]
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"

    master = registry[spec.requires]
    assert getattr(master, "requires", None) in (None, ""), (
        "el master apuntado no puede tener requires (R4 profundidad 1)"
    )

    publicaciones = registry["STACKY_DEVOPS_PUBLICATIONS_ENABLED"]
    assert publicaciones.requires == "STACKY_DEVOPS_PANEL_ENABLED", (
        "si esto cambia, revisar por que este plan NO apunta a Publicaciones"
    )


def test_default_off_efectivo():
    """El default EFECTIVO lo decide config.py, no la FlagSpec."""
    from services.harness_flags import FLAG_REGISTRY

    spec = next(s for s in FLAG_REGISTRY if s.key == KEY)
    # Una flag default-OFF NO declara `default=False`: eso la haria "conocida" y
    # test_default_known_only_for_curated exige que las conocidas esten curadas.
    assert getattr(spec, "default", None) is None

    assert os.getenv(KEY) is None, f"{KEY} seteada en el entorno: este caso mide el DEFAULT"
    import config

    assert getattr(config.config, KEY) is False


def test_no_esta_en_curated_defaults_on():
    """_CURATED_DEFAULTS_ON es exclusivamente para flags con default ON."""
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert KEY not in _CURATED_DEFAULTS_ON


def test_health_expone_la_key():
    from api.devops import _health_payload

    payload = _health_payload()
    assert "one_click_publish_enabled" in payload
    assert payload["one_click_publish_enabled"] is False  # default OFF


def test_ayuda_en_llano_registrada():
    """Sexta pata."""
    from services.harness_flags_help import PLAIN_HELP

    assert KEY in PLAIN_HELP
    h = PLAIN_HELP[KEY]
    assert h.what and h.on_effect and h.off_effect and h.example
    # Limite del gate de ayuda (test_plain_help_fields_non_empty_and_bounded).
    assert len(h.on_effect) <= 240
    assert len(h.off_effect) <= 240
