"""Regresion: la operadora corre PrepararPublicacion.bat, el deploy queda
fresco en disco (dist con hash de contenido, VERSION.txt, backend congelado
todos con mtime nuevo), pero al abrir la app en el navegador sigue viendo la
UI vieja. Root cause: `/` (index.html) se sirve via `send_from_directory`
sin Cache-Control explicito, asi que el navegador puede servir una copia
cacheada de index.html que referencia el bundle JS/CSS hasheado ANTERIOR
(heuristic caching de Flask/Werkzeug: sin `Cache-Control`, solo agrega
ETag/Last-Modified condicionales, que no fuerzan revalidacion en todos los
navegadores/proxies).

Fix: forzar `Cache-Control: no-store` en la respuesta de `/` (el HTML raiz,
el UNICO archivo sin hash de contenido en el bundle Vite) para que el
navegador SIEMPRE pida el index.html fresco, que a su vez apunta a los
assets hasheados correctos. Los assets estaticos (con hash en el nombre)
pueden cachearse agresivamente sin riesgo porque su URL cambia con el
contenido.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def spa_client(tmp_path, monkeypatch):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text(
        '<html><script src="/assets/index-ABC123.js"></script></html>',
        encoding="utf-8",
    )
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "index-ABC123.js").write_text("console.log('hi')", encoding="utf-8")

    monkeypatch.setenv("STACKY_FRONTEND_DIST", str(dist_dir))
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_spa_index_response_forces_no_cache(spa_client):
    """GET / (index.html) nunca debe quedar cacheado por el navegador."""
    resp = spa_client.get("/")
    assert resp.status_code == 200
    cache_control = (resp.headers.get("Cache-Control") or "").lower()
    assert "no-store" in cache_control, (
        f"index.html debe llevar Cache-Control: no-store para que el "
        f"navegador nunca sirva una version vieja de la UI tras un deploy. "
        f"Header actual: {resp.headers.get('Cache-Control')!r}"
    )


def test_spa_fallback_route_also_forces_no_cache(spa_client):
    """El fallback SPA (ruta desconocida -> index.html) tampoco debe cachearse."""
    resp = spa_client.get("/alguna-ruta-de-react-router")
    assert resp.status_code == 200
    cache_control = (resp.headers.get("Cache-Control") or "").lower()
    assert "no-store" in cache_control
