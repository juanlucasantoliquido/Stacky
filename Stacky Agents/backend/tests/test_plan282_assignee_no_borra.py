"""Plan 282 F3 — un username GitLab que no resuelve FALLA diciendolo.

Antes vaciaba `assignee_ids` en silencio: un typo en el username, o un fallo
transitorio de `/users`, desasignaba el issue del operador sin avisar. Era el
silencio mas caro de la matriz de paridad.
"""
from __future__ import annotations

import pytest

from services.tracker_provider import TrackerApiError


class _ClienteFalso:
    """Registra TODAS las llamadas: el gate necesita probar que el PUT no salio."""

    def __init__(self, usuarios=None, explota_users=False):
        self.llamadas: list[tuple] = []
        self._usuarios = usuarios or {}
        self._explota_users = explota_users

    def _project_path(self):
        return "grupo/proyecto"

    def _request(self, metodo, ruta, **kwargs):
        self.llamadas.append((metodo, ruta, kwargs))
        if ruta == "/users":
            if self._explota_users:
                raise RuntimeError("GitLab /users caido")
            username = (kwargs.get("params") or {}).get("username")
            uid = self._usuarios.get(username)
            return ([{"id": uid}] if uid else []), 200
        return {"iid": 1115, "title": "t", "state": "opened", "labels": []}, 200

    @property
    def puts_de_update(self):
        return [c for c in self.llamadas if c[0] == "PUT"]


def _provider(cliente):
    from services.gitlab_provider import GitLabTrackerProvider

    prov = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    prov._client = cliente
    prov._project = "grupo/proyecto"
    return prov


# ── 1 — camino feliz ──────────────────────────────────────────────────────────


def test_username_valido_asigna():
    cliente = _ClienteFalso(usuarios={"jsantoliquido": 77})
    _provider(cliente).update_item_assignee("1115", "jsantoliquido")

    puts = cliente.puts_de_update
    assert len(puts) == 1
    assert puts[0][2]["json_body"] == {"assignee_ids": [77]}


# ── 2 — la intencion legitima de desasignar se CONSERVA ───────────────────────


def test_username_vacio_desasigna_a_proposito():
    cliente = _ClienteFalso()
    _provider(cliente).update_item_assignee("1115", "")

    puts = cliente.puts_de_update
    assert len(puts) == 1, "desasignar explicitamente sigue siendo un caso valido"
    assert puts[0][2]["json_body"] == {"assignee_ids": []}


# ── 3 — el que NO resuelve: lanza Y no manda nada ─────────────────────────────


def test_username_que_no_resuelve_lanza_y_no_manda_body():
    cliente = _ClienteFalso(usuarios={})

    with pytest.raises(TrackerApiError) as info:
        _provider(cliente).update_item_assignee("1115", "no-existe")

    assert "no-existe" in str(info.value)
    assert info.value.status == 404
    # Los DOS asserts: sin el segundo, el test pasa aunque el borrado ocurra
    # antes de lanzar.
    assert cliente.puts_de_update == [], "se mando el PUT destructivo igual"


# ── 4 — fallo transitorio de /users: tampoco desasigna ────────────────────────


def test_fallo_transitorio_de_users_no_desasigna():
    cliente = _ClienteFalso(explota_users=True)

    with pytest.raises(TrackerApiError):
        _provider(cliente).update_item_assignee("1115", "jsantoliquido")

    assert cliente.puts_de_update == []


# ── 5 — reversibilidad + congelacion del camino previo ────────────────────────


def test_ado_no_cambia(monkeypatch):
    """El camino ADO no pasa por aca, y con la flag OFF vuelve el de antes.

    `update_item_assignee` es GitLab-only: el equivalente ADO
    (`AdoTrackerProvider`) no comparte una linea con este metodo. Lo que se
    congela es que apagar la flag reproduce EXACTAMENTE el comportamiento
    previo al plan 282 — el gate se corre CONTRA el defecto.
    """
    import config as _config
    from services.ado_provider import AdoTrackerProvider

    assert AdoTrackerProvider.update_item_assignee is not (
        __import__("services.gitlab_provider", fromlist=["x"])
        .GitLabTrackerProvider.update_item_assignee
    ), "los dos caminos son metodos distintos: tocar GitLab no toca ADO"

    monkeypatch.setattr(_config.config, "STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED",
                        False, raising=False)
    cliente = _ClienteFalso(usuarios={})
    _provider(cliente).update_item_assignee("1115", "no-existe")

    puts = cliente.puts_de_update
    assert len(puts) == 1
    assert puts[0][2]["json_body"] == {"assignee_ids": []}, (
        "con la flag OFF debe volver el borrado silencioso: si no, no hay defecto "
        "que este plan este arreglando"
    )


# ── 6 — el radio de impacto se respeto ────────────────────────────────────────


def test_los_otros_dos_llamadores_no_cambian():
    """`_resolve_assignee_id` sigue devolviendo None (no lanza).

    Lo consumen el camino de creacion/actualizacion de item y el migrador
    Mantis->GitLab, que corre en batch. Si alguien "arregla" ese metodo en vez
    de agregar el strict, este test se pone rojo.
    """
    cliente = _ClienteFalso(usuarios={})
    prov = _provider(cliente)

    assert prov._resolve_assignee_id("no-existe") is None
    assert prov._resolve_assignee_id("tampoco") is None
    assert cliente.puts_de_update == []
