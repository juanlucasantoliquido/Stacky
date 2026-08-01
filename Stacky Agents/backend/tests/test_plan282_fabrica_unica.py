"""Plan 282 F2 — ningun servicio construye GitLabTrackerProvider a mano.

El constructor directo NO resuelve el `ca_bundle`: contra un GitLab self-hosted
con CA interna —el caso del operador— los 4 servicios morian con
CERTIFICATE_VERIFY_FAILED mientras la sonda y el listado de tickets funcionaban.
"""
from __future__ import annotations

import ast

import pytest

from test_plan282_censo_paridad import _constructores_directos

BUNDLE = "C:/certs/ca-interna.pem"


class _ProviderGitLabFalso:
    """El nombre de la clase importa: build_gitlab_provider compara por NOMBRE.

    (Con `patch(...)` una clase real pasa a ser un MagicMock y `isinstance`
    levanta TypeError; por eso la fabrica compara `type(x).__name__`.)
    """

    def __init__(self, ca_bundle=BUNDLE):
        self.ca_bundle = ca_bundle
        self._client = type("_ClienteFalso", (), {"ca_bundle": ca_bundle})()


# Alias con el nombre EXACTO que la fabrica reconoce.
GitLabTrackerProvider = type("GitLabTrackerProvider", (_ProviderGitLabFalso,), {})


class AdoTrackerProvider:
    """Proveedor de otro tracker: la fabrica debe rechazarlo con error TIPADO."""

    _client = None


def _servicios():
    from services.gitlab_ci_logs import GitLabCILogsProvider
    from services.gitlab_ci_provider import GitLabCIProvider
    from services.gitlab_preflight import GitLabPreflightProvider
    from services.gitlab_variables import GitLabVariablesProvider
    return [
        ("gitlab_ci_logs", GitLabCILogsProvider),
        ("gitlab_ci_provider", GitLabCIProvider),
        ("gitlab_preflight", GitLabPreflightProvider),
        ("gitlab_variables", GitLabVariablesProvider),
    ]


def _provider_de(servicio, fabricado):
    """El provider que el servicio se quedo, sea cual sea el atributo.

    `gitlab_preflight` NO guarda el provider: solo se queda con su `_client`
    (verificado en el codigo, no supuesto). Para ese caso la identidad se
    comprueba por el cliente, que es lo unico que retiene.
    """
    obtenido = getattr(servicio, "_provider", None) or getattr(servicio, "_delegate", None)
    if obtenido is not None:
        return obtenido
    if getattr(servicio, "_client", None) is fabricado._client:
        return fabricado
    return None


# ── Caso 1 — el censo AST queda en CERO ───────────────────────────────────────


def test_ningun_servicio_construye_el_provider_a_mano():
    """GUARDA ANTI-FALSO-VERDE primero: el detector tiene que detectar.

    Un assert de ausencia que nunca vio un positivo no prueba nada: si el censo
    estuviera roto, `[] == []` pasaria con los 4 ofensores vivos.
    """
    fuente_con_ofensor = "def f():\n    p = GitLabTrackerProvider(project=x)\n"
    encontrados = [
        n.lineno
        for n in ast.walk(ast.parse(fuente_con_ofensor))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "GitLabTrackerProvider"
    ]
    assert encontrados == [2], "el detector del censo no detecta: test invalido"

    assert _constructores_directos() == [], (
        "hay servicios construyendo el provider sin pasar por la fabrica"
    )


# ── Caso 2 — el ca_bundle llega a los 4 servicios ─────────────────────────────


def test_los_cuatro_servicios_reciben_el_provider_con_ca_bundle(monkeypatch):
    from services import tracker_provider

    fabricado = GitLabTrackerProvider()
    monkeypatch.setattr(tracker_provider, "get_tracker_provider",
                        lambda *_a, **_k: fabricado)

    for nombre, clase in _servicios():
        servicio = clase(project="RIPLEY")
        obtenido = _provider_de(servicio, fabricado)
        assert obtenido is fabricado, f"{nombre} no uso el provider de la fabrica"
        assert obtenido.ca_bundle == BUNDLE, (
            f"{nombre} perdio el ca_bundle: es el bug que mata a GitLab con CA interna"
        )


# ── Caso 3 — proyecto que no es GitLab: error TIPADO, no AttributeError ───────


def test_servicio_en_proyecto_ado_devuelve_error_tipado(monkeypatch):
    from services import tracker_provider
    from services.tracker_provider import TrackerConfigError

    monkeypatch.setattr(tracker_provider, "get_tracker_provider",
                        lambda *_a, **_k: AdoTrackerProvider())

    for nombre, clase in _servicios():
        with pytest.raises(TrackerConfigError) as info:
            clase(project="RSPACIFICO")
        assert "no usa GitLab" in str(info.value), nombre
        assert not isinstance(info.value, AttributeError), (
            f"{nombre} explota con AttributeError en vez del error tipado del modulo"
        )


# ── Caso 4 — reversibilidad: con la flag OFF vuelve el camino viejo ───────────


def test_con_la_flag_off_vuelve_el_camino_viejo(monkeypatch):
    import config as _config
    from services import gitlab_provider, tracker_provider

    llamadas: list[dict] = []

    class _Recorder:
        def __init__(self, **kwargs):
            llamadas.append(kwargs)
            self._client = None

    monkeypatch.setattr(gitlab_provider, "GitLabTrackerProvider", _Recorder)

    def _no_debe_llamarse(*_a, **_k):
        raise AssertionError("con la flag OFF la fabrica no se consulta")

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", _no_debe_llamarse)
    monkeypatch.setattr(_config.config, "STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED",
                        False, raising=False)

    tracker_provider.build_gitlab_provider("RIPLEY")

    assert llamadas == [{"project": "RIPLEY"}], (
        "el camino viejo debe ser byte-identico: solo project=, sin ca_bundle"
    )
