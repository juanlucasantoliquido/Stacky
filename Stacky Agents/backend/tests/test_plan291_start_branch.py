"""Plan 291 — El commit del agente crea la rama que necesita (GitLab).

F1  branch_exists / _default_branch_name (+ F1.b: api/ delega en el provider)
F2  _detect_commit_action deja de confundir "no hay rama" con "no hay archivo"
F3  registro de las TRES flags (dos OFF por (B), una ON)
F4  start_branch en el body del POST, detrás de la flag

CERO RED. Todo va contra dobles: el provider se instancia con __new__ (sin
__init__, o sea sin TLS ni cliente HTTP) y el cliente se falsea.
"""
from __future__ import annotations

import base64
import urllib.parse
from unittest.mock import MagicMock

import pytest

from services.tracker_provider import TrackerApiError


# ── Doble del cliente: idioma exacto de tests/test_plan73_repo_writer.py:11-21 ──

def _provider_con_doble():
    from services.gitlab_provider import GitLabTrackerProvider
    p = GitLabTrackerProvider.__new__(GitLabTrackerProvider)   # sin __init__: cero red, cero TLS
    p._client = MagicMock()
    p._client._project_path.return_value = "grp%2Fproj"
    p._project = "proj"
    p._group = ""
    p._epics_native = False
    return p, p._client


# ══════════════════════════════════════════════════════════════════════════════
# F1 — branch_exists: preguntar si la rama existe en vez de deducirlo de un 404
# ══════════════════════════════════════════════════════════════════════════════

def test_f1_1_branch_exists_true_y_url_encodeada():
    """F1.1 — 200 → True, y la barra de la rama va URL-encodeada (%2F).

    Sin quote(safe=""), GitLab leería 'stacky/incidencia-12-exec-34' como DOS
    segmentos de path y el GET pegaría en otro endpoint.
    """
    provider, cliente = _provider_con_doble()
    cliente._request.return_value = ({}, {})

    assert provider.branch_exists("stacky/incidencia-12-exec-34") is True

    url = cliente._request.call_args[0][1]
    assert "stacky%2Fincidencia-12-exec-34" in url
    assert "stacky/incidencia-12-exec-34" not in url


def test_f1_2_branch_exists_false_en_404():
    """F1.2 — 404 → False (la rama no existe)."""
    provider, cliente = _provider_con_doble()
    cliente._request.side_effect = TrackerApiError(404, "not found", kind="not_found")

    assert provider.branch_exists("stacky/x") is False


def test_f1_3_branch_exists_propaga_403():
    """F1.3 — 401/403/500 NO es 'no existe': se PROPAGA.

    Tratarlo como False haría que commit_file intentara crear una rama que
    quizás ya está (C1 del plan 73).
    """
    provider, cliente = _provider_con_doble()
    cliente._request.side_effect = TrackerApiError(403, "forbidden", kind="auth")

    with pytest.raises(TrackerApiError) as exc:
        provider.branch_exists("stacky/x")
    assert exc.value.status == 403


def test_f1_4_default_branch_name_lee_master_no_adivina_main():
    """F1.4 — la rama base se LEE de /projects/:id, no se adivina."""
    provider, cliente = _provider_con_doble()
    cliente._request.return_value = ({"default_branch": "master"}, {})

    assert provider._default_branch_name() == "master"


def test_f1_5_default_branch_name_repo_vacio_devuelve_cadena_vacia():
    """F1.5 — repo sin rama default (vacío) → "" (F4 lo traduce a repo_empty)."""
    provider, cliente = _provider_con_doble()
    cliente._request.return_value = ({}, {})

    assert provider._default_branch_name() == ""


# ── F1.b — api/devops_production._default_branch DELEGA en el provider ────────

class _ProviderDoble:
    """Doble mínimo de un provider GitLab: expone SOLO _default_branch_name.

    Deliberadamente NO expone `_client`: si `_default_branch` siguiera haciendo
    el GET por su cuenta, el test explota con AttributeError. Eso es el rojo.
    """

    name = "gitlab"

    def __init__(self, rama):
        self._rama = rama

    def _default_branch_name(self):
        return self._rama


def test_f1_6_devops_production_default_branch_delega_en_el_provider():
    """F1.b / F1.6 — la implementación única vive en el provider."""
    from api.devops_production import _default_branch

    assert _default_branch(_ProviderDoble("develop"), "P") == "develop"


def test_f1_7_devops_production_preserva_el_fallback_historico_main():
    """F1.b / F1.7 — con "" del provider, el helper de api/ sigue devolviendo
    'main'. Guarda la PRESENCIA del contrato histórico, que es justo lo que un
    refactor descuidado rompería."""
    from api.devops_production import _default_branch

    assert _default_branch(_ProviderDoble(""), "P") == "main"
