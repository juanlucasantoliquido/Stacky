"""tests/test_mg_cache_view.py — caché de `view.php` del adapter de scraping.

## Por qué existe

`fetch_issue_detail`, `fetch_comments`, `fetch_attachments` y
`fetch_relationships` piden **el mismo recurso**: `view.php?id=N`. Sin caché, un
barrido de 1008 issues cuesta ~4000 GET en vez de 1008 — y `execute` hace ese
barrido dos veces (`plan_migration` para comparar el hash, y la pasada de
relaciones), así que el desperdicio se duplica: ~8000 requests evitables contra
la instancia real.

Además de ahorrar, el caché **mejora la corrección**: garantiza que descripción,
notas, adjuntos y relaciones de un ticket salgan todas de la MISMA foto. Sin
caché, un ticket modificado a mitad del barrido produce un issue con la
descripción de un instante y las notas de otro.
"""
from __future__ import annotations

import pytest

from tools.migrar_mantis_gitlab.adapters import scraping_adapter as sa
from tools.migrar_mantis_gitlab.adapters.scraping_adapter import (
    MantisWebScrapingReadAdapter,
)


class _AdapterEspia(MantisWebScrapingReadAdapter):
    """Adapter con el login neutralizado y los GET contados, para poder afirmar
    cuántos requests se emiten de verdad."""

    def __init__(self, html_por_id: dict):
        # Se saltea __init__ del padre a propósito: no queremos login ni sesión.
        self._base_url = "https://mantis.ejemplo.local/mantis"
        self._project_ids = [310]
        self._username = "u"
        self._password = "p"
        self._timeout = 5
        self._include_resolved_closed = True
        self._page_size = 500
        self._authenticated = True
        self._view_cache = {}
        self._view_cache_hits = 0
        self._view_cache_misses = 0
        self._html_por_id = html_por_id
        self.gets: list[str] = []

    def _authenticated_get(self, url: str) -> str:
        self.gets.append(url)
        for issue_id, html in self._html_por_id.items():
            if f"id={issue_id}" in url:
                return html
        return "<html></html>"


_HTML = (
    '<html><body>'
    '<td class="bug-summary">0000042: Titulo</td>'
    '<td class="bug-status"><i class="status-80-fg"></i></td>'
    '<td class="bug-date-submitted">10/01/2026 09:15</td>'
    '</body></html>'
)


def test_cuatro_metodos_sobre_el_mismo_issue_hacen_UN_solo_get():
    """Ésta es la afirmación central: 4 llamadas -> 1 request."""
    a = _AdapterEspia({42: _HTML})

    a.fetch_issue_detail(42)
    a.fetch_comments(42)
    a.fetch_attachments(42)
    a.fetch_relationships(42)

    assert len(a.gets) == 1, f"se emitieron {len(a.gets)} GET en vez de 1: {a.gets}"
    assert a.cache_stats() == {"hits": 3, "misses": 1, "entradas": 1}


def test_issues_distintos_no_comparten_entrada():
    a = _AdapterEspia({42: _HTML, 43: _HTML})
    a.fetch_issue_detail(42)
    a.fetch_issue_detail(43)
    assert len(a.gets) == 2
    assert a.cache_stats()["entradas"] == 2


def test_el_contenido_devuelto_es_el_mismo_con_y_sin_cache():
    """El caché no puede cambiar el resultado: mismo HTML, mismo parseo."""
    a = _AdapterEspia({42: _HTML})
    primero = a.fetch_issue_detail(42)
    segundo = a.fetch_issue_detail(42)
    assert primero == segundo
    assert primero["status"] == "resolved"
    assert primero["date_submitted"] == "10/01/2026 09:15"


def test_el_cache_se_vacia_al_llegar_al_tope(monkeypatch):
    """Evita que un proyecto enorme haga crecer la memoria sin límite."""
    monkeypatch.setattr(sa, "_VIEW_CACHE_MAX", 3)
    a = _AdapterEspia({i: _HTML for i in range(1, 10)})

    for i in range(1, 4):
        a.fetch_issue_detail(i)
    assert a.cache_stats()["entradas"] == 3

    # El 4º miss encuentra el caché lleno: lo vacía y guarda sólo el nuevo.
    a.fetch_issue_detail(4)
    assert a.cache_stats()["entradas"] == 1

    # Y sigue funcionando: el 4 ahora está cacheado.
    antes = len(a.gets)
    a.fetch_comments(4)
    assert len(a.gets) == antes


def test_ahorro_medido_en_un_barrido_del_tamano_real():
    """Simula el patrón de `plan_migration` (detalle + comments + attachments) y
    la pasada de relaciones sobre 50 issues: 200 llamadas -> 50 requests."""
    n = 50
    a = _AdapterEspia({i: _HTML for i in range(1, n + 1)})

    for i in range(1, n + 1):          # plan_migration
        a.fetch_issue_detail(i)
        a.fetch_comments(i)
        a.fetch_attachments(i)
    for i in range(1, n + 1):          # segunda pasada: relaciones
        a.fetch_relationships(i)

    llamadas = n * 4
    assert len(a.gets) == n, f"{llamadas} llamadas debieron costar {n} GET, costaron {len(a.gets)}"
    st = a.cache_stats()
    assert st["misses"] == n and st["hits"] == llamadas - n
