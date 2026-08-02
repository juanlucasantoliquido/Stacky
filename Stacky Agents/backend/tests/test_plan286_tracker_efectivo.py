"""Plan 286 F1 — El helper de tracker efectivo: precedencia y memo por mtime.

NO importa `db`, ni `app`, ni `models` (plan §4.2): `backend/tests/conftest.py`
no aisla la base, asi que un test que importara eso escribiria en la BD REAL del
operador. El ticket es un `SimpleNamespace` y el config del proyecto se inyecta
parcheando `project_manager.get_project_config`, que funciona porque el helper
lo resuelve POR REFERENCIA en cada llamada (import local).
"""
import os
from types import SimpleNamespace

import pytest

from services.project_context import (
    _reset_divergencias_vistas,
    _reset_memo_tracker_declarado,
    tracker_efectivo_de_ticket,
)


@pytest.fixture(autouse=True)
def _memo_limpio():
    """El memo de F1 y el dedupe de F7 son modulo-level: sin esto, el orden de
    los tests decide el resultado y aparecen verdes que no significan nada."""
    _reset_memo_tracker_declarado()
    _reset_divergencias_vistas()
    yield
    _reset_memo_tracker_declarado()
    _reset_divergencias_vistas()


def _ticket(tracker_type=None, proyecto=None):
    return SimpleNamespace(tracker_type=tracker_type, stacky_project_name=proyecto)


def _con_config(monkeypatch, mapa):
    """mapa: {"RIPLEY": "gitlab", "RSPACIFICO": "azure_devops"}; ausente => None.
    Devuelve la lista de nombres consultados: varios casos NO prueban nada si no
    se comprueba que el fake fue LLAMADO (C7)."""
    llamadas = []

    def _fake(nombre):
        llamadas.append(nombre)
        tipo = mapa.get((nombre or "").strip().upper())
        return {"issue_tracker": {"type": tipo}} if tipo else None

    monkeypatch.setattr("project_manager.get_project_config", _fake)
    return llamadas


_MAPA = {"RIPLEY": "gitlab", "RSPACIFICO": "azure_devops"}


# ── 1-9: la precedencia ──────────────────────────────────────────────────────

def test_columna_mentirosa_pierde_contra_el_proyecto(monkeypatch):
    """EL caso de los 2 tickets de la BD viva. Si este falla, el plan no sirve.

    `azure_devops` en la columna es indistinguible de "nadie la seteo"
    (models.py:49, default del ORM), asi que NO puede ganarle al config.
    """
    _con_config(monkeypatch, _MAPA)
    assert tracker_efectivo_de_ticket(_ticket("azure_devops", "RIPLEY")) == "gitlab"


def test_columna_vacia_cae_al_proyecto(monkeypatch):
    _con_config(monkeypatch, _MAPA)
    assert tracker_efectivo_de_ticket(_ticket(None, "RIPLEY")) == "gitlab"


def test_columna_explicita_no_default_gana_al_proyecto(monkeypatch):
    """P2 rama 1: 'jira' solo pudo escribirlo un sync a proposito."""
    _con_config(monkeypatch, _MAPA)
    assert tracker_efectivo_de_ticket(_ticket("jira", "RSPACIFICO")) == "jira"


def test_proyecto_ado_sigue_siendo_ado(monkeypatch):
    """No-regresion ADO: RSPACIFICO son 57 tickets reales."""
    _con_config(monkeypatch, _MAPA)
    assert tracker_efectivo_de_ticket(
        _ticket("azure_devops", "RSPACIFICO")) == "azure_devops"


def test_sin_proyecto_es_fail_closed_a_ado(monkeypatch):
    """P3: comportamiento de HOY, no una regresion."""
    _con_config(monkeypatch, _MAPA)
    assert tracker_efectivo_de_ticket(
        _ticket("azure_devops", None)) == "azure_devops"


def test_proyecto_sin_config_es_fail_closed_a_ado(monkeypatch):
    """P3: las 100 filas de `p`/`P`/ONP/`test` dependen de esto para no moverse."""
    _con_config(monkeypatch, _MAPA)
    assert tracker_efectivo_de_ticket(
        _ticket("azure_devops", "p")) == "azure_devops"


def test_get_project_config_que_explota_es_fail_closed(monkeypatch):
    """C7 — el proyecto es OBLIGATORIO y el contador es lo unico que hace que el
    verde signifique algo: con un ticket SIN proyecto este test pasaria sin
    ejercer el `except`, porque `tracker_declarado_del_proyecto` corta antes en
    `if not raw: return None`."""
    llamadas = []

    def _explota(nombre):
        llamadas.append(nombre)
        raise RuntimeError("config ilegible")

    monkeypatch.setattr("project_manager.get_project_config", _explota)
    assert tracker_efectivo_de_ticket(
        _ticket("azure_devops", "RIPLEY")) == "azure_devops"
    assert len(llamadas) == 1, (
        "el `except` no se ejercio: el helper corto antes de consultar el config"
    )


def test_columna_con_espacios_y_mayusculas_se_normaliza(monkeypatch):
    _con_config(monkeypatch, _MAPA)
    assert tracker_efectivo_de_ticket(
        _ticket("  GitLab  ", "RSPACIFICO")) == "gitlab"


def test_columna_no_string_se_ignora(monkeypatch):
    _con_config(monkeypatch, _MAPA)
    assert tracker_efectivo_de_ticket(_ticket(123, "RIPLEY")) == "gitlab"


# ── 10-11: el kill-switch (P7, rollback de una sola palanca) ─────────────────

def _flag_off(monkeypatch):
    monkeypatch.setattr(
        "config.config.STACKY_TRACKER_ROUTING_STRICT_ENABLED", False,
        raising=False,
    )


def test_kill_switch_apagado_devuelve_la_columna_cruda(monkeypatch):
    _con_config(monkeypatch, _MAPA)
    _flag_off(monkeypatch)
    assert tracker_efectivo_de_ticket(
        _ticket("azure_devops", "RIPLEY")) == "azure_devops"


def test_kill_switch_apagado_sin_columna_da_el_default(monkeypatch):
    _con_config(monkeypatch, _MAPA)
    _flag_off(monkeypatch)
    assert tracker_efectivo_de_ticket(_ticket(None, "RIPLEY")) == "azure_devops"


# ── 12-14: el memo revalidado por mtime (C5) ─────────────────────────────────

def test_el_memo_no_relee_el_config_dos_veces(monkeypatch):
    """C5 — sin este test el memo puede no existir y nadie se entera.
    `backend/projects/RIPLEY/config.json` EXISTE, asi que la firma del `os.stat`
    real es estable entre las dos llamadas y la segunda tiene que pegarle al memo.
    """
    llamadas = _con_config(monkeypatch, _MAPA)
    t = _ticket(None, "RIPLEY")
    assert tracker_efectivo_de_ticket(t) == "gitlab"
    assert tracker_efectivo_de_ticket(t) == "gitlab"
    assert len(llamadas) == 1, f"el memo no cacheo: {llamadas}"


def test_tocar_el_config_invalida_el_memo(monkeypatch):
    """El memo NO puede quedar stale: el operador cambia `issue_tracker.type`
    por UI y cualquier caché que no mire el archivo dejaria a Stacky escribiendo
    en el tracker viejo. Por eso `os.stat` y NO un TTL ni un `lru_cache`."""
    llamadas = []
    valores = ["gitlab", "jira"]

    def _fake(nombre):
        llamadas.append(nombre)
        return {"issue_tracker": {"type": valores[min(len(llamadas) - 1, 1)]}}

    monkeypatch.setattr("project_manager.get_project_config", _fake)

    firmas = [SimpleNamespace(st_mtime_ns=111, st_size=10),
              SimpleNamespace(st_mtime_ns=222, st_size=20)]
    vistas = {"n": 0}
    _stat_real = os.stat

    def _fake_stat(path, *a, **k):
        # Solo el config de RIPLEY: delegar el resto al real deja el test inmune
        # a cualquier `os.stat` ajeno que caiga en la ventana del monkeypatch.
        if "RIPLEY" in str(path):
            i = min(vistas["n"], len(firmas) - 1)
            vistas["n"] += 1
            return firmas[i]
        return _stat_real(path, *a, **k)

    monkeypatch.setattr("os.stat", _fake_stat)

    t = _ticket(None, "RIPLEY")
    assert tracker_efectivo_de_ticket(t) == "gitlab"
    assert tracker_efectivo_de_ticket(t) == "jira"
    assert len(llamadas) == 2, f"el memo quedo stale: {llamadas}"


def test_un_stat_que_explota_cae_al_camino_sin_memo(monkeypatch):
    """Degradacion: sin firma no hay memo, pero NUNCA rompe."""
    llamadas = _con_config(monkeypatch, _MAPA)
    _stat_real = os.stat

    def _fake_stat(path, *a, **k):
        if "RIPLEY" in str(path):
            raise OSError("sin permiso")
        return _stat_real(path, *a, **k)

    monkeypatch.setattr("os.stat", _fake_stat)

    t = _ticket(None, "RIPLEY")
    assert tracker_efectivo_de_ticket(t) == "gitlab"
    assert tracker_efectivo_de_ticket(t) == "gitlab"
    assert len(llamadas) == 2, "sin firma no puede haber memo"


# ── F7 — la contradiccion deja RASTRO en vez de corregirse en silencio ───────

def test_la_divergencia_se_loguea_una_sola_vez(monkeypatch, caplog):
    """Deduplicado por (proyecto, columna, declarado) por proceso: un backlog de
    200 tickets no puede vomitar 200 lineas iguales."""
    import logging

    _con_config(monkeypatch, _MAPA)
    t = _ticket("azure_devops", "RIPLEY")
    with caplog.at_level(logging.INFO, logger="stacky_agents.project_context"):
        for _ in range(10):
            assert tracker_efectivo_de_ticket(t) == "gitlab"

    lineas = [r for r in caplog.records if "la columna no manda" in r.getMessage()]
    assert len(lineas) == 1, f"esperaba 1 linea deduplicada, hubo {len(lineas)}"
    msg = lineas[0].getMessage()
    assert "proyecto=RIPLEY" in msg
    assert "columna=azure_devops" in msg
    assert "efectivo=gitlab" in msg


def test_sin_divergencia_no_se_loguea_nada(monkeypatch, caplog):
    """Guarda la PRESENCIA del test anterior: un assert de 'no loguea' solo
    pasaria igual si el log directamente no existiera."""
    import logging

    _con_config(monkeypatch, _MAPA)
    with caplog.at_level(logging.INFO, logger="stacky_agents.project_context"):
        # La columna coincide con el proyecto: no hay nada que declarar.
        assert tracker_efectivo_de_ticket(_ticket("gitlab", "RIPLEY")) == "gitlab"
        assert tracker_efectivo_de_ticket(
            _ticket("azure_devops", "RSPACIFICO")) == "azure_devops"

    lineas = [r for r in caplog.records if "la columna no manda" in r.getMessage()]
    assert lineas == [], f"logueo una divergencia que no existe: {lineas}"
