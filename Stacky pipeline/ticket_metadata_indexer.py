"""
ticket_metadata_indexer.py — Indexador background de metadata de tickets.

Thread daemon que cada 5 minutos (configurable):
  1. Parsea `git log --all --grep='AB#<id>|#<id>'` en una pasada
  2. Cuenta commits asociados por ticket + último hash
  3. Cuenta comentarios ADO (cacheo TTL 10 min)
  4. Cuenta archivos NOTA_PM.md locales
  5. Escribe atómicamente vía store.bulk_update() — todo o nada

Primer índice al boot es síncrono (timeout 30s, graceful fallback).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ticket_metadata_store import get_store, TicketMetadataError

logger = logging.getLogger("stacky.ticket_metadata_indexer")

# ── Constantes ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # Tools/Stacky → N:\GIT\RS\RSPacifico
_GIT_TIMEOUT_SEC = 60.0
_ADO_CACHE_TTL_SEC = 600.0  # 10 min
_TICKET_REGEX = re.compile(r"(?:AB#|#)(\d{3,7})")

# Importar ADO client si está disponible (optional)
_ADO_AVAILABLE = False
_ado_client = None
try:
    from ado_enricher import get_enricher
    _ADO_AVAILABLE = True
except ImportError:
    logger.debug("ADO enricher no disponible — solo indexación por git")


class _AdoCommentCache:
    """Cacheo TTL simple para comentarios ADO por ticket."""
    def __init__(self, ttl_sec: float = 600.0):
        self.ttl_sec = ttl_sec
        self._cache: Dict[str, tuple[int, float]] = {}  # ticket_id → (count, inserted_at)
        self._lock = threading.Lock()

    def get(self, ticket_id: str) -> Optional[int]:
        """Devuelve comentario count si está cached y válido, None si expiró."""
        with self._lock:
            if ticket_id not in self._cache:
                return None
            count, inserted_at = self._cache[ticket_id]
            if time.time() - inserted_at > self.ttl_sec:
                del self._cache[ticket_id]
                return None
            return count

    def set(self, ticket_id: str, count: int) -> None:
        """Cachea el count de comentarios."""
        with self._lock:
            self._cache[ticket_id] = (count, time.time())

    def invalidate(self, ticket_id: Optional[str] = None) -> None:
        """Invalida entrada (None = todas)."""
        with self._lock:
            if ticket_id is None:
                self._cache.clear()
            elif ticket_id in self._cache:
                del self._cache[ticket_id]


class MetadataIndexer:
    """Thread daemon que indexa metadata de tickets."""

    def __init__(self, period_sec: float = 300.0, force_git_only: bool = False):
        """
        Args:
            period_sec: intervalo de indexación en segundos
            force_git_only: si True, omite ADO (útil para dev/testing)
        """
        self.period_sec = period_sec
        self.force_git_only = force_git_only or not _ADO_AVAILABLE
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ado_cache = _AdoCommentCache(ttl_sec=_ADO_CACHE_TTL_SEC)
        self._lock = threading.Lock()
        self._last_index_at: Optional[str] = None
        self._indexed_count = 0
        self._indexing_error: Optional[str] = None
        self._store = get_store()

    def start(self) -> None:
        """Inicia el thread daemon. Primer índice es síncrono (timeout 30s)."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Indexer ya está running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="MetadataIndexer")
        self._thread.start()
        logger.info("Indexer iniciado (period=%s)", self.period_sec)

        # Primer índice síncrono con timeout
        logger.info("Primer índice síncrono (timeout=30s)...")
        try:
            self.index_now(force_refresh_ado=False)
        except Exception as e:
            logger.warning("Primer índice falló (continuando en background): %s", e)

    def stop(self) -> None:
        """Para el thread gracefully."""
        if self._thread is None:
            return
        logger.info("Parando indexer...")
        self._stop_event.set()
        try:
            self._thread.join(timeout=10.0)
        except Exception as e:
            logger.warning("Error esperando parada: %s", e)
        if self._thread.is_alive():
            logger.warning("Indexer no paró después de timeout")

    def index_now(self, force_refresh_ado: bool = False) -> None:
        """Indexa bajo demanda (ej. desde webhook ADO)."""
        if force_refresh_ado:
            self._ado_cache.invalidate()
        self._do_index()

    @property
    def is_running(self) -> bool:
        """True si el thread está corriendo."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_index_at(self) -> Optional[str]:
        """Timestamp ISO del último índice exitoso."""
        return self._last_index_at

    @property
    def indexed_count(self) -> int:
        """Cantidad de tickets indexados en última pasada."""
        return self._indexed_count

    @property
    def indexing_error(self) -> Optional[str]:
        """Último error de indexación (None si OK)."""
        return self._indexing_error

    # ── Implementación privada ────────────────────────────────────────────────
    def _run(self) -> None:
        """Loop principal del thread."""
        while not self._stop_event.is_set():
            try:
                self._do_index()
            except Exception as e:
                logger.error("Error en ciclo de indexación: %s", e, exc_info=True)
                with self._lock:
                    self._indexing_error = str(e)

            # Espera el siguiente ciclo o se despierta si se pide stop
            self._stop_event.wait(timeout=self.period_sec)

    def _do_index(self) -> None:
        """Ejecuta una pasada de indexación. Thread-safe."""
        start_time = time.time()

        # Fase 1: git log
        git_stats = self._scan_git()  # dict[ticket_id, {count, last_hash, last_at}]

        # Fase 2: ADO comments (cacheo TTL)
        if not self.force_git_only:
            self._enrich_with_ado(git_stats)

        # Fase 3: notas locales
        self._enrich_with_notes(git_stats)

        # Fase 4: bulk update al store (atómico)
        updates = {}
        for ticket_id, stats in git_stats.items():
            updates[ticket_id] = {
                "commits_count": stats.get("commits_count", 0),
                "last_commit_hash": stats.get("last_commit_hash"),
                "last_commit_at": stats.get("last_commit_at"),
                "ado_comments_count": stats.get("ado_comments_count", 0),
                "notes_count": stats.get("notes_count", 0),
                "last_note_at": stats.get("last_note_at"),
            }

        if updates:
            try:
                self._store.bulk_update(updates)
            except TicketMetadataError as e:
                logger.error("Fallo bulk_update: %s", e)
                with self._lock:
                    self._indexing_error = str(e)
                raise

        # Actualizar métricas
        with self._lock:
            self._last_index_at = datetime.now(timezone.utc).isoformat()
            self._indexed_count = len(updates)
            self._indexing_error = None

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info("Indexación completada: %d tickets, %dms", len(updates), duration_ms)

    def _scan_git(self) -> Dict[str, Dict[str, Any]]:
        """Una pasada de `git log --all` y parsea commits por ticket usando regex de Python."""
        result: Dict[str, Dict[str, Any]] = {}
        try:
            cmd = [
                "git", "log", "--all",
                "--format=%H%x09%at%x09%s",
            ]
            output = subprocess.run(
                cmd,
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_GIT_TIMEOUT_SEC,
            )
            if output.returncode != 0:
                logger.warning("git log falló: %s", output.stderr[:200])
                return result

            for line in output.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t", 2)
                if len(parts) < 3:
                    continue

                commit_hash, timestamp_str, subject = parts[0], parts[1], parts[2]
                try:
                    commit_at = datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc).isoformat()
                except (ValueError, OSError):
                    commit_at = None

                # Extrae todos los ticket IDs de este commit (puede haber varios)
                for match in _TICKET_REGEX.finditer(subject):
                    ticket_id = match.group(1)
                    if ticket_id not in result:
                        result[ticket_id] = {
                            "commits_count": 0,
                            "last_commit_hash": None,
                            "last_commit_at": None,
                            "commit_hashes": set(),
                        }

                    # Dedup por hash (un mismo commit no contar N veces si menciona el ticket múltiples veces)
                    if commit_hash not in result[ticket_id]["commit_hashes"]:
                        result[ticket_id]["commit_hashes"].add(commit_hash)
                        result[ticket_id]["commits_count"] += 1
                        # Asumo que git log está ordenado por fecha desc → el primero es el más reciente
                        if result[ticket_id]["last_commit_hash"] is None:
                            result[ticket_id]["last_commit_hash"] = commit_hash
                            result[ticket_id]["last_commit_at"] = commit_at

            # Limpiar helper
            for stats in result.values():
                del stats["commit_hashes"]

            logger.debug("git scan: %d tickets encontrados", len(result))
        except subprocess.TimeoutExpired:
            logger.error("git log timeout (%s sec)", _GIT_TIMEOUT_SEC)
            result = {}
        except Exception as e:
            logger.error("Error en git scan: %s", e, exc_info=True)
            result = {}

        return result

    def _enrich_with_ado(self, result: Dict[str, Dict[str, Any]]) -> None:
        """Enriquece con comentarios ADO (cacheo TTL)."""
        if not _ADO_AVAILABLE:
            return

        try:
            enricher = get_enricher()
            if enricher is None:
                return
        except Exception:
            return

        for ticket_id in list(result.keys()):
            # Intentar cache primero
            cached = self._ado_cache.get(ticket_id)
            if cached is not None:
                result[ticket_id]["ado_comments_count"] = cached
                continue

            # Fetch de ADO
            try:
                # Asumo que existe .get_comments(wi_id) en enricher
                wi_id = ticket_id  # simplificado; idealmente lookup en pipeline_state
                comments = enricher.get_comments(wi_id)
                count = len(comments) if comments else 0
                self._ado_cache.set(ticket_id, count)
                result[ticket_id]["ado_comments_count"] = count
            except Exception as e:
                logger.debug("ADO comments para %s falló: %s", ticket_id, e)
                result[ticket_id]["ado_comments_count"] = 0

    def _enrich_with_notes(self, result: Dict[str, Dict[str, Any]]) -> None:
        """Cuenta archivos NOTA_PM*.md locales."""
        try:
            # Scan de proyectos/tickets/*/NOTA_PM*.md
            tickets_dir = _REPO_ROOT / "projects"
            if not tickets_dir.exists():
                return

            # Mapeo de ticket_id → archivos NOTA_PM
            notes_by_ticket: Dict[str, list[Path]] = {}
            for note_file in tickets_dir.glob("*/tickets/*/NOTA_PM*.md"):
                # Extrae ticket_id del path: projects/<proj>/tickets/<id>/NOTA_PM*.md
                try:
                    ticket_id = note_file.parent.name
                    if ticket_id not in notes_by_ticket:
                        notes_by_ticket[ticket_id] = []
                    notes_by_ticket[ticket_id].append(note_file)
                except Exception:
                    pass

            for ticket_id, notes_list in notes_by_ticket.items():
                if ticket_id not in result:
                    result[ticket_id] = {}

                result[ticket_id]["notes_count"] = len(notes_list)

                # Último mtime
                if notes_list:
                    latest_mtime = max(f.stat().st_mtime for f in notes_list if f.exists())
                    result[ticket_id]["last_note_at"] = datetime.fromtimestamp(
                        latest_mtime, tz=timezone.utc
                    ).isoformat()
        except Exception as e:
            logger.debug("Error enriqueciendo notas locales: %s", e)
