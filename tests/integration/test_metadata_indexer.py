"""
Tests del indexador de metadata de tickets.
"""

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from ticket_metadata_indexer import MetadataIndexer, _AdoCommentCache
from ticket_metadata_store import get_store, reset_singleton_for_tests


@pytest.fixture(autouse=True)
def _reset_singletons(tmp_path, monkeypatch):
    """Reset de singletons de store antes de cada test."""
    import ticket_metadata_store
    monkeypatch.setattr(ticket_metadata_store, "_DATA_DIR", tmp_path / "data")
    reset_singleton_for_tests()
    yield
    reset_singleton_for_tests()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Fixture del store con tmp_path."""
    import ticket_metadata_store
    monkeypatch.setattr(ticket_metadata_store, "_DATA_DIR", tmp_path / "data")
    return get_store()


@pytest.fixture
def git_mock_repo(tmp_path):
    """Crea un repo git mock con algunos commits."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir(parents=True)

    # Inicializar repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Crear algunos commits con refs a tickets
    commits = [
        ("AB#12345 first feature", "feat1.txt", "content1"),
        ("AB#12346 second feature", "feat2.txt", "content2"),
        ("#00123 fix bug", "fix1.txt", "fix content"),
        ("Mixed AB#12347 and #00124 in one commit", "mixed.txt", "mixed"),
    ]

    for msg, fname, content in commits:
        (repo_dir / fname).write_text(content)
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=repo_dir, check=True, capture_output=True)

    return repo_dir


class TestAdoCommentCache:
    """Tests del caché TTL de comentarios ADO."""

    def test_get_miss(self):
        cache = _AdoCommentCache(ttl_sec=1.0)
        assert cache.get("ticket1") is None

    def test_set_and_get_hit(self):
        cache = _AdoCommentCache(ttl_sec=10.0)
        cache.set("ticket1", 5)
        assert cache.get("ticket1") == 5

    def test_expiry(self):
        cache = _AdoCommentCache(ttl_sec=0.1)
        cache.set("ticket1", 5)
        assert cache.get("ticket1") == 5
        time.sleep(0.2)
        assert cache.get("ticket1") is None

    def test_invalidate_one(self):
        cache = _AdoCommentCache(ttl_sec=10.0)
        cache.set("ticket1", 5)
        cache.set("ticket2", 3)
        cache.invalidate("ticket1")
        assert cache.get("ticket1") is None
        assert cache.get("ticket2") == 3

    def test_invalidate_all(self):
        cache = _AdoCommentCache(ttl_sec=10.0)
        cache.set("ticket1", 5)
        cache.set("ticket2", 3)
        cache.invalidate()
        assert cache.get("ticket1") is None
        assert cache.get("ticket2") is None


class TestMetadataIndexer:
    """Tests del indexador de metadata."""

    def test_init(self):
        indexer = MetadataIndexer(period_sec=1.0)
        assert indexer.period_sec == 1.0
        assert not indexer.is_running
        assert indexer.last_index_at is None
        assert indexer.indexed_count == 0
        assert indexer.indexing_error is None

    def test_start_stop(self):
        indexer = MetadataIndexer(period_sec=1.0, force_git_only=True)
        indexer.start()
        time.sleep(0.2)  # Dejar que inicie
        assert indexer.is_running
        indexer.stop()
        time.sleep(0.5)  # Dejar que pare
        assert not indexer.is_running

    def test_first_index_on_boot_graceful_if_git_fails(self, tmp_path, monkeypatch):
        """Primer índice síncrono: si git falla, sigue arrancando el thread."""
        import ticket_metadata_indexer
        monkeypatch.setattr(ticket_metadata_indexer, "_REPO_ROOT", tmp_path / "nonexistent")

        indexer = MetadataIndexer(period_sec=0.5, force_git_only=True)
        indexer.start()
        time.sleep(0.2)
        # Debería estar en running aunque el git scan falló
        assert indexer.is_running
        indexer.stop()

    def test_git_scan_basic(self, tmp_path, monkeypatch, git_mock_repo):
        """Test del parseo de git log con refs a tickets."""
        import ticket_metadata_indexer
        monkeypatch.setattr(ticket_metadata_indexer, "_REPO_ROOT", git_mock_repo)

        indexer = MetadataIndexer(force_git_only=True)
        result = indexer._scan_git()

        # Verificar que encontró los tickets
        assert "12345" in result
        assert "12346" in result
        assert "00123" in result
        assert "12347" in result
        assert "00124" in result

        # Verificar counts
        assert result["12345"]["commits_count"] == 1
        assert result["12346"]["commits_count"] == 1
        assert result["00123"]["commits_count"] == 1
        assert result["12347"]["commits_count"] == 1  # En mismo commit que 00124
        assert result["00124"]["commits_count"] == 1  # En mismo commit que 12347

    def test_index_now_writes_to_store(self, tmp_path, monkeypatch, git_mock_repo, store):
        """Test que index_now() escribe al store vía bulk_update."""
        import ticket_metadata_indexer
        monkeypatch.setattr(ticket_metadata_indexer, "_REPO_ROOT", git_mock_repo)

        indexer = MetadataIndexer(force_git_only=True)
        indexer.index_now()

        # Verificar que el store tiene las metadata
        all_metadata = store.get_all()
        assert len(all_metadata) > 0
        assert "12345" in all_metadata
        assert all_metadata["12345"].commits_count == 1

    def test_ado_cache_invalidation_on_demand(self, tmp_path, monkeypatch):
        """Test que index_now(force_refresh_ado=True) invalida el caché ADO."""
        indexer = MetadataIndexer(force_git_only=True)
        indexer._ado_cache.set("ticket1", 5)
        assert indexer._ado_cache.get("ticket1") == 5
        indexer.index_now(force_refresh_ado=True)
        # Caché debe estar limpio
        assert indexer._ado_cache.get("ticket1") is None

    def test_graceful_shutdown_no_hang(self):
        """Test que stop() no cuelga el thread."""
        indexer = MetadataIndexer(period_sec=0.5, force_git_only=True)
        indexer.start()
        time.sleep(0.2)
        assert indexer.is_running

        # Parar debe tomar < 2s incluso si el periodo es 0.5s
        start = time.time()
        indexer.stop()
        elapsed = time.time() - start
        assert elapsed < 2.0
        assert not indexer.is_running

    def test_multiple_index_cycles(self, tmp_path, monkeypatch, git_mock_repo, store):
        """Test de múltiples ciclos de indexación."""
        import ticket_metadata_indexer
        monkeypatch.setattr(ticket_metadata_indexer, "_REPO_ROOT", git_mock_repo)

        indexer = MetadataIndexer(period_sec=0.2, force_git_only=True)
        indexer.start()

        # Esperar 2-3 ciclos
        time.sleep(0.7)

        # Debería haber indexado varias veces
        assert indexer.last_index_at is not None
        assert indexer.indexed_count > 0
        assert indexer.indexing_error is None

        indexer.stop()

    def test_notes_scan(self, tmp_path, monkeypatch, store):
        """Test del scanning de archivos NOTA_PM*.md locales."""
        import ticket_metadata_indexer

        # Crear estructura de proyectos con notas
        projects_dir = tmp_path / "projects" / "TestProj" / "tickets" / "99999"
        projects_dir.mkdir(parents=True)
        (projects_dir / "NOTA_PM.md").write_text("# nota 1")
        (projects_dir / "NOTA_PM_v2.md").write_text("# nota 2")

        monkeypatch.setattr(ticket_metadata_indexer, "_REPO_ROOT", tmp_path)

        indexer = MetadataIndexer(force_git_only=True)
        result = {}
        indexer._enrich_with_notes(result)

        # Debería haber encontrado ticket 99999 con 2 notas
        assert "99999" in result
        assert result["99999"]["notes_count"] == 2
        assert result["99999"].get("last_note_at") is not None
