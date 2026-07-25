"""Gaps conductuales conocidos del contrato. CONGELADO por el Plan 218 (§3.1).

[ADICIÓN ARQUITECTO 2, parte b] — el RATCHET INVERSO de paridad.

Cada entrada es una PROMESA con dueño: el subplan que la cierra la BORRA de acá.
Los escenarios cuyo (provider, capability) está registrado corren esperando el fallo
(equivalente en proceso a `pytest.mark.xfail(strict=True)`, ver provider_contract.py):

  * el gap sigue roto  -> la suite queda VERDE y F3 es implementable hoy.
  * un subplan lo arregla -> "XPASS" = FALLO, y el único camino al verde es BORRAR
    la entrada de acá.

Es decir: es imposible arreglar un gap sin actualizar el registro, e imposible dejar
el registro mintiendo.
"""
from __future__ import annotations

KNOWN_GAPS: dict[tuple[str, str], dict] = {
    # (provider, capability): {"owner_plan": int, "reason": str, "evidence": "archivo:línea"}
    ("gitlab", "tracker.items.url"): {
        "owner_plan": 232,
        "reason": "item_url devuelve None con deep links OFF, violando '-> str'",
        "evidence": "services/gitlab_provider.py:169"},
    ("gitlab", "tracker.comments.list_all"): {
        "owner_plan": 222,
        "reason": "fetch_all_comments es idéntico a fetch_comments y no normaliza la nota "
                  "a la forma neutral author/date/text que devuelve el otro adaptador",
        "evidence": "services/gitlab_provider.py:293"},
    ("gitlab", "tracker.states.list"): {
        "owner_plan": 224,
        "reason": "devuelve 4 claves lógicas hardcodeadas, no estados reales",
        "evidence": "services/gitlab_provider.py:84"},
    ("gitlab", "tracker.hierarchy.find_child"): {
        "owner_plan": 224,
        "reason": "devuelve el padre como proxy del hijo",
        "evidence": "services/gitlab_provider.py:381"},
    ("gitlab", "tracker.items.update_assignee"): {
        "owner_plan": 223,
        "reason": "silencia el usuario inexistente y BORRA el asignado",
        "evidence": "services/gitlab_provider.py:363"},
    ("gitlab", "tracker.rate_limit.clamp"): {
        "owner_plan": 231,
        "reason": "no clampea Retry-After hostil (ADO clampea a 30 s)",
        "evidence": "services/gitlab_client.py:146"},
    ("gitlab", "tracker.auth.html_redirect"): {
        "owner_plan": 231,
        "reason": "devuelve texto crudo ante HTML de login en vez de error de auth",
        "evidence": "services/gitlab_client.py:164"},
    # Hallazgo de la implementación de F3 (2026-07-25): el contrato conductual encontró
    # un gap SIMÉTRICO en el lado ADO que el relevamiento en papel no había visto.
    ("azure_devops", "tracker.items.get"): {
        "owner_plan": 231,
        "reason": "AdoTrackerProvider propaga AdoApiError crudo (RuntimeError ajeno a la "
                  "jerarquía del puerto) en vez de TrackerApiError(kind='not_found')",
        "evidence": "services/ado_provider.py:66"},
}
