"""tests/test_plan218_tracker_contract.py -- Plan 218 F3.

Corre EL MISMO cuerpo de contrato contra AdoTrackerProvider y GitLabTrackerProvider
REALES, doblando únicamente el transporte HTTP. Es el mecanismo central del plan: la
paridad deja de ser una declaración y pasa a ser un gate.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config as config_module  # noqa: E402

from services.provider_capabilities import (  # noqa: E402
    CAPABILITY_KEYS,
    _CAPABILITY_TO_PORT_METHOD,
    capability_status,
)
from tests.contract.fake_transport import (  # noqa: E402
    FakeHttp,
    install_for_ado,
    install_for_gitlab,
)
from tests.contract.known_gaps import KNOWN_GAPS  # noqa: E402
from tests.contract.provider_contract import SCENARIOS, run_tracker_contract  # noqa: E402

# Alcance declarado del contrato de F3. Cada subplan que cierra un puerto agrega su
# dominio acá EN EL MISMO COMMIT (§7 del plan): nada de "cobertura total" prometida
# de entrada y nunca alcanzada.
_DOMINIOS_CUBIERTOS: frozenset[str] = frozenset({"tracker"})

# Capacidades `tracker.*` que este plan NO ejercita todavía, con el subplan que debe
# agregarles escenario. Estar acá es una DECISIÓN EXPLÍCITA y auditable: sin la entrada,
# el test de cobertura queda rojo. Las que no tienen método del puerto no se pueden
# ejercitar desde el contrato del tracker (viven en ado_sync / pm / taxonomía).
_SIN_ESCENARIO_CON_DUENO: dict[str, int] = {
    "tracker.items.list": 220,          # motor de sync agnóstico
    "tracker.query.search": 220,
    "tracker.sync.full": 220,
    "tracker.sync.incremental": 220,
    "tracker.comments.list": 222,       # publicación agnóstica (misma forma que list_all)
    "tracker.comments.post": 222,
    "tracker.attachments.list": 222,
    "tracker.attachments.upload": 222,
    "tracker.attachments.link": 222,
    "tracker.updates.history": 225,     # aprendizaje de ediciones
    "tracker.types.list": 224,          # taxonomía de tipos
    "tracker.hierarchy.link_parent": 224,
    "tracker.epics.list": 224,
    "tracker.epics.create_native": 224,
    "tracker.iterations.list": 224,
    "tracker.milestones.list": 224,
    "tracker.labels.ensure": 224,
}


# ── Constructores de providers REALES (solo se dobla el transporte) ───────────

def _make_ado_provider(monkeypatch, fake):
    from services.ado_provider import AdoTrackerProvider

    class _Ctx:
        stacky_project_name = "TESTPROJ"
        tracker_type = "azure_devops"
        tracker_project = "testproj"
        organization = "testorg"
        workspace_root = None
        auth_path = None
        vscode_port = None

    monkeypatch.setenv("ADO_PAT", "pat-de-test-no-real")
    monkeypatch.setattr(
        "services.project_context.resolve_project_context", lambda *a, **k: _Ctx()
    )
    install_for_ado(monkeypatch, fake)

    def _factory(ctx):
        import services.ado_client as ado_client

        monkeypatch.setattr(ado_client.time, "sleep", lambda s: ctx["sleeps"].append(s))
        return AdoTrackerProvider(project="TESTPROJ")

    return _factory


def _make_gitlab_provider(monkeypatch, fake):
    from services.gitlab_provider import GitLabTrackerProvider

    monkeypatch.setenv("GITLAB_TOKEN", "token-de-test-no-real")
    monkeypatch.setattr(config_module.config, "GITLAB_URL", "https://gl.test")
    monkeypatch.setattr(config_module.config, "GITLAB_PROJECT", "grupo/proyecto")
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_GROUP", "")
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_EPICS_NATIVE", False)
    install_for_gitlab(monkeypatch, fake)

    def _factory(ctx):
        import services.gitlab_client as gitlab_client

        monkeypatch.setattr(gitlab_client.time, "sleep", lambda s: ctx["sleeps"].append(s))
        return GitLabTrackerProvider(project="grupo/proyecto")

    return _factory


_FACTORIES = {"azure_devops": _make_ado_provider, "gitlab": _make_gitlab_provider}


@pytest.mark.parametrize("provider_name", ["azure_devops", "gitlab"])
def test_contrato_del_puerto_tracker(provider_name, monkeypatch):
    fake = FakeHttp(provider=provider_name)
    make_provider = _FACTORIES[provider_name](monkeypatch, fake)

    verificadas = run_tracker_contract(make_provider, provider_name, fake)

    assert len(verificadas) >= 1, f"{provider_name}: el contrato no verificó ninguna capacidad"


def test_contrato_cubre_toda_capacidad_full_o_partial():
    """Acotado al dominio `tracker.*` (el puerto que F3 ejercita).

    Toda capacidad `tracker.*` marcada full/partial está ejercitada por un escenario
    O declarada en `_SIN_ESCENARIO_CON_DUENO` con el subplan responsable. No hay
    tercera opción: marcar `full` y desaparecer del contrato deja este test ROJO.
    """
    ejercitadas = {esc.capability for esc in SCENARIOS}
    sin_cubrir = []
    for key in CAPABILITY_KEYS:
        if key.split(".", 1)[0] not in _DOMINIOS_CUBIERTOS:
            continue
        estados = {capability_status(p, key) for p in ("azure_devops", "gitlab")}
        if not (estados & {"full", "partial"}):
            continue
        if key in ejercitadas or key in _SIN_ESCENARIO_CON_DUENO:
            continue
        sin_cubrir.append(key)

    assert sin_cubrir == [], (
        "capacidades tracker.* marcadas full/partial sin escenario de contrato ni dueño "
        f"declarado: {sin_cubrir}"
    )


def test_sin_escenario_declarado_no_esconde_capacidad_ejercitada():
    """La lista de excepciones no puede usarse para tapar algo que YA se ejercita."""
    ejercitadas = {esc.capability for esc in SCENARIOS}
    solapadas = ejercitadas & set(_SIN_ESCENARIO_CON_DUENO)
    assert solapadas == set(), f"declaradas sin escenario pero ejercitadas: {sorted(solapadas)}"
    for key, dueno in _SIN_ESCENARIO_CON_DUENO.items():
        assert key in CAPABILITY_KEYS, key
        assert 219 <= dueno <= 236, f"{key}: dueño fuera de la serie ({dueno})"


def test_known_gaps_bien_formado():
    evidencia_re = re.compile(r"^[\w/\.]+\.py:\d+$")
    for clave, valor in KNOWN_GAPS.items():
        assert isinstance(clave, tuple) and len(clave) == 2, clave
        provider, capability = clave
        assert provider in ("azure_devops", "gitlab"), provider
        assert capability in CAPABILITY_KEYS, capability
        assert 219 <= valor["owner_plan"] <= 236, f"{clave}: dueño fuera de la serie"
        assert len(valor["reason"]) >= 20, f"{clave}: motivo demasiado corto"
        assert evidencia_re.match(valor["evidence"]), f"{clave}: evidencia inválida"


def test_gap_conocido_exige_capacidad_no_full():
    """Un gap conocido y una matriz que dice 'full' no pueden coexistir."""
    for (provider, capability), valor in KNOWN_GAPS.items():
        estado = capability_status(provider, capability)
        assert estado == "partial", (
            f"{provider}/{capability} está en KNOWN_GAPS (plan {valor['owner_plan']}) "
            f"pero la matriz lo declara '{estado}'. Un gap firmado se declara 'partial' "
            "con su pérdida, o se borra del registro."
        )


def test_ningun_test_de_contrato_parchea_config_ni_provider():
    """Codifica P4: prohibido mockear el seam bajo prueba."""
    # Los patrones se ARMAN por concatenación: este archivo se escanea a sí mismo y
    # deletrearlos enteros sería un falso positivo permanente
    # (memoria `gotcha-plan-comment-matches-own-gate`: reescribir, no gamear).
    _p = "patch("
    _objetivos = (
        "services.gitlab_provider.config",
        "config",
        "services.gitlab_variables.GitLabTrackerProvider",
        "services.ado_provider.AdoTrackerProvider",
    )
    prohibidos = tuple(
        f'{_p}{comilla}{objetivo}' for objetivo in _objetivos for comilla in ('"', "'")
    ) + ("MagicMock(spec=" + "GitLabTrackerProvider",)
    archivos = list((_BACKEND / "tests" / "contract").rglob("*.py"))
    archivos.append(Path(__file__))
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        for patron in prohibidos:
            assert patron not in texto, (
                f"{archivo.name} parchea el seam bajo prueba ({patron!r}). "
                "El contrato solo puede doblar el TRANSPORTE (P4)."
            )


def test_fixtures_sin_pii():
    raiz = _BACKEND / "tests" / "fixtures" / "provider_contract"
    email_re = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    token_re = re.compile(r"\b[A-Za-z0-9]{20,}\b")
    fixtures = list(raiz.rglob("*.json"))
    assert fixtures, "el contrato declara fixtures grabados pero no hay ninguno"
    for fixture in fixtures:
        texto = fixture.read_text(encoding="utf-8")
        assert not email_re.search(texto), f"{fixture.name} contiene un email"
        assert "PRIVATE-TOKEN" not in texto, f"{fixture.name} contiene una cabecera de token"
        sospechosos = [t for t in token_re.findall(texto) if not t.isalpha()]
        assert not sospechosos, f"{fixture.name} contiene algo que parece un token: {sospechosos}"


def test_conformance_legacy_deja_de_mentir():
    ruta = _BACKEND / "tests" / "test_tracker_provider_conformance.py"
    texto = ruta.read_text(encoding="utf-8")
    assert "no que esté hardcoded NotImplementedError" not in texto, (
        "el test de conformance sigue prometiendo lo que no verifica"
    )


def test_mapa_de_puerto_es_consistente():
    from services.tracker_provider import PORT_METHODS

    for capability, metodo in _CAPABILITY_TO_PORT_METHOD.items():
        assert capability in CAPABILITY_KEYS, capability
        assert metodo in PORT_METHODS, metodo
