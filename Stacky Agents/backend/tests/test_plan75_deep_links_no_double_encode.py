"""Plan 75 F6 ADICION — Centinela de no-double-encoding real (plan 75).

Instancia GitLabTrackerProvider con _project='rs/pacifico/strat' (valor crudo,
con barras literales, tal como viene del config) y llama item_url("42").

Cierra la ventana entre los tests F1 (que usan strings ya-encoded como input)
y el wiring real F2 (donde _project_path() encodea en el momento): si el
implementador accidentalmente pasa _project_path() por _enc(), este test falla.

Gate de significancia (plan 75 C3):
  (a) URL contiene 'rs%2Fpacifico%2Fstrat' (encoding correcto).
  (b) URL NO contiene '%25' (doble-encoding ausente).
"""
import config as config_module


def test_centinela_no_double_encode_real_wiring(monkeypatch):
    """GitLabTrackerProvider real con project crudo -> item_url sin %25."""
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True)

    # Instanciar el provider con project crudo (con barras literales)
    from services.gitlab_provider import GitLabTrackerProvider
    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)

    # Construir el client con base_url y project real (sin pre-encodear)
    from services.gitlab_client import GitLabClient
    client = GitLabClient.__new__(GitLabClient)
    client._base_url = "https://gl.example.com"
    client._project_id = "rs/pacifico/strat"  # barras literales, sin encodear
    client._token = ""
    provider._client = client
    provider._project = "rs/pacifico/strat"
    provider._group = ""
    provider._epics_native = False

    result = provider.item_url("42")

    assert result is not None, "item_url devolvio None con flag ON"
    assert "rs%2Fpacifico%2Fstrat" in result, (
        f"Encoding incorrecto: esperaba 'rs%2Fpacifico%2Fstrat' en {result!r}"
    )
    assert "%25" not in result, (
        f"Double-encoding detectado: '%25' encontrado en {result!r} "
        "(project_path paso por _enc() dos veces)"
    )
