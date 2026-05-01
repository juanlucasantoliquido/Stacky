"""
ticket_metadata_store.py — Store persistente de metadata por ticket (FASE 1).

Persistencia: ``data/ticket_metadata.json`` (schema v1).
Concurrencia: ``threading.RLock`` + file lock cross-process (msvcrt.locking en
Windows, fcntl en POSIX) + escritura atómica temp + rename + fsync.
Cache: mtime-cache — solo re-lee del disco cuando cambió.
Corrupción: si el JSON está inválido o falla el schema, se renombra a
``.json.bak.<timestamp>`` y se vuelve a arrancar con store vacío.
Migraciones: stub defensivo v0 → v1 (no hay v0 real desplegado).

Uso:
    from ticket_metadata_store import get_store
    store = get_store()
    store.set_color("27698", "#ff00aa")
    store.add_user_tag("27698", "urgente")
    meta = store.get("27698")           # → TicketMetadata | None
    all_ = store.get_all()              # → Dict[str, TicketMetadata]
    store.bulk_update({
        "27698": {"color": "#aabbcc", "user_tags": ["bug", "frontend"]},
        "27699": {"color": None},
    })
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ticket_metadata_schema import (
    MAX_TAGS_PER_TICKET,
    TicketColor,
    TicketMetadata,
    TicketMetadataStore as _StoreModel,
    TicketUserTags,
)

# ── Constantes ────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parent
_DATA_DIR = _BASE_DIR / "data"
_STORE_PATH = _DATA_DIR / "ticket_metadata.json"
_LOCK_PATH = _DATA_DIR / "ticket_metadata.json.lock"
_STORE_VERSION = 1
_FILE_LOCK_TIMEOUT_SEC = 10.0

logger = logging.getLogger("stacky.ticket_metadata")


class TicketMetadataError(Exception):
    """Error de dominio del store (I/O, schema o migración)."""


# ── Observabilidad opcional (slog) ────────────────────────────────────────────
try:
    from stacky_log import slog  # type: ignore
except Exception:  # pragma: no cover
    slog = None  # el store funciona sin slog instalado


def _safe_slog_action(ticket_id: str, action: str, detail: str = "") -> None:
    if slog is None:
        return
    try:
        slog.action(exec_id="", ticket_id=ticket_id or "-", action=action, detail=detail)
    except Exception:
        pass


def _safe_slog_error(ticket_id: str, action: str, kind: str, exc: BaseException,
                    user_friendly: str = "") -> None:
    if slog is None:
        logger.error("[%s] %s (%s): %s", ticket_id or "-", action, kind, exc)
        return
    try:
        slog.error_classified(exec_id="", ticket_id=ticket_id or "-",
                              action=action, kind=kind, exc=exc,
                              user_friendly=user_friendly or str(exc))
    except Exception:
        logger.error("[%s] %s (%s): %s", ticket_id or "-", action, kind, exc)


# ── Cross-process file lock (Windows msvcrt / POSIX fcntl) ────────────────────
def _acquire_file_lock(lock_path: Path, timeout_sec: float = _FILE_LOCK_TIMEOUT_SEC):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_sec
    last_exc: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            fh = open(str(lock_path), "a+b")
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl  # type: ignore
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fh
            except OSError as e:
                last_exc = e
                fh.close()
                time.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            last_exc = e
            time.sleep(0.05)
    logger.warning("file lock timeout sobre %s: %s", lock_path, last_exc)
    return None


def _release_file_lock(fh) -> None:
    if fh is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl  # type: ignore
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            fh.close()
        except Exception:
            pass


# ── Migraciones ───────────────────────────────────────────────────────────────
def _migrate(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Lleva el dict crudo al schema v1. Stub defensivo — no hay v0 desplegado."""
    if not isinstance(raw, dict):
        raise TicketMetadataError("raíz del store no es dict")
    version = int(raw.get("version", 0) or 0)
    tickets = raw.get("tickets")
    if version == 0 or "tickets" not in raw:
        # v0 → v1: si viene dict plano {ticket_id: {...}}, envolver.
        if isinstance(tickets, dict):
            pass
        elif isinstance(raw.get("data"), dict):
            tickets = raw["data"]
        else:
            tickets = {k: v for k, v in raw.items()
                       if k not in {"version", "tickets", "data"} and isinstance(v, dict)}
        raw = {"version": _STORE_VERSION, "tickets": tickets or {}}
        logger.info("migrated store v0 → v%d (tickets=%d)", _STORE_VERSION, len(tickets or {}))
    elif version > _STORE_VERSION:
        raise TicketMetadataError(f"store version {version} > soportada {_STORE_VERSION}")
    return raw


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Store singleton ───────────────────────────────────────────────────────────
class _TicketMetadataStore:
    """Store thread-safe + cross-process safe con mtime-cache."""

    def __init__(self) -> None:
        self._rlock = threading.RLock()
        self._cache: Optional[_StoreModel] = None
        self._cache_mtime: float = 0.0

    # ── Helpers internos ──────────────────────────────────────────────────────
    def _ensure_dirs(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _load_locked(self) -> _StoreModel:
        """Carga del disco respetando mtime-cache. Requiere self._rlock."""
        self._ensure_dirs()
        if not _STORE_PATH.exists():
            self._cache = _StoreModel(version=_STORE_VERSION, tickets={})
            self._cache_mtime = 0.0
            return self._cache
        try:
            mtime = _STORE_PATH.stat().st_mtime
        except OSError as e:
            _safe_slog_error("-", "metadata_stat", "data", e)
            self._cache = _StoreModel(version=_STORE_VERSION, tickets={})
            return self._cache
        if self._cache is not None and mtime == self._cache_mtime:
            return self._cache
        try:
            raw_text = _STORE_PATH.read_text(encoding="utf-8")
            raw = json.loads(raw_text) if raw_text.strip() else {"version": _STORE_VERSION, "tickets": {}}
            migrated = _migrate(raw)
            self._cache = _StoreModel(**migrated)
            self._cache_mtime = mtime
            return self._cache
        except (json.JSONDecodeError, TicketMetadataError, ValueError, TypeError) as e:
            self._backup_corrupt(e)
            self._cache = _StoreModel(version=_STORE_VERSION, tickets={})
            self._cache_mtime = 0.0
            return self._cache

    def _backup_corrupt(self, exc: BaseException) -> None:
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            bak = _STORE_PATH.with_suffix(f".json.bak.{ts}")
            _STORE_PATH.replace(bak)
            logger.error("ticket_metadata.json corrupto → backup %s (%s)", bak.name, exc)
            _safe_slog_error("-", "metadata_corrupt", "data", exc,
                             user_friendly=f"Metadata corrupta movida a {bak.name}")
        except Exception as mv_exc:  # noqa: BLE001
            logger.error("fallo moviendo backup de corrupción: %s", mv_exc)

    def _flush_locked(self, model: _StoreModel) -> None:
        """Persiste ``model`` al disco con file lock + atomic write. Requiere self._rlock."""
        self._ensure_dirs()
        fh_lock = _acquire_file_lock(_LOCK_PATH, _FILE_LOCK_TIMEOUT_SEC)
        try:
            tmp_path = _STORE_PATH.with_suffix(".json.tmp")
            payload = model.to_dict()
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, _STORE_PATH)
            try:
                self._cache_mtime = _STORE_PATH.stat().st_mtime
            except OSError:
                self._cache_mtime = 0.0
            self._cache = model
        finally:
            _release_file_lock(fh_lock)
            try:
                if _LOCK_PATH.exists():
                    _LOCK_PATH.unlink()
            except Exception:
                pass

    def _touch(self, meta: TicketMetadata) -> TicketMetadata:
        meta.updated_at = _utc_now_iso()
        return meta

    # ── API pública ────────────────────────────────────────────────────────────
    def get(self, ticket_id: str) -> Optional[TicketMetadata]:
        with self._rlock:
            model = self._load_locked()
            return model.tickets.get(str(ticket_id))

    def get_all(self) -> Dict[str, TicketMetadata]:
        with self._rlock:
            model = self._load_locked()
            return dict(model.tickets)

    def set_color(self, ticket_id: str, hex_color: str) -> TicketMetadata:
        tid = str(ticket_id)
        with self._rlock:
            model = self._load_locked()
            meta = model.tickets.get(tid) or TicketMetadata(ticket_id=tid)
            try:
                meta.color = TicketColor(hex=hex_color)
            except Exception as e:
                _safe_slog_error(tid, "metadata_set_color", "user", e)
                raise TicketMetadataError(f"color inválido: {e}") from e
            model.tickets[tid] = self._touch(meta)
            self._flush_locked(model)
            _safe_slog_action(tid, "metadata_set_color", detail=meta.color.hex)
            return meta

    def clear_color(self, ticket_id: str) -> Optional[TicketMetadata]:
        tid = str(ticket_id)
        with self._rlock:
            model = self._load_locked()
            meta = model.tickets.get(tid)
            if not meta or meta.color is None:
                return meta
            meta.color = None
            model.tickets[tid] = self._touch(meta)
            self._flush_locked(model)
            _safe_slog_action(tid, "metadata_clear_color")
            return meta

    def set_user_tags(self, ticket_id: str, tags: Iterable[str]) -> TicketMetadata:
        tid = str(ticket_id)
        with self._rlock:
            model = self._load_locked()
            meta = model.tickets.get(tid) or TicketMetadata(ticket_id=tid)
            try:
                meta.user_tags = TicketUserTags(tags=list(tags or []))
            except Exception as e:
                _safe_slog_error(tid, "metadata_set_user_tags", "user", e)
                raise TicketMetadataError(f"tags inválidos: {e}") from e
            model.tickets[tid] = self._touch(meta)
            self._flush_locked(model)
            _safe_slog_action(tid, "metadata_set_user_tags",
                              detail=f"count={len(meta.user_tags.tags)}")
            return meta

    def add_user_tag(self, ticket_id: str, tag: str) -> TicketMetadata:
        tid = str(ticket_id)
        with self._rlock:
            current = self.get(tid)
            existing: List[str] = list(current.user_tags.tags) if current else []
            if len(existing) >= MAX_TAGS_PER_TICKET:
                raise TicketMetadataError(
                    f"ticket {tid} ya tiene {MAX_TAGS_PER_TICKET} tags (máx alcanzado)")
            existing.append(tag)  # dedup/normalización en validator
            return self.set_user_tags(tid, existing)

    def remove_user_tag(self, ticket_id: str, tag: str) -> TicketMetadata:
        tid = str(ticket_id)
        norm = (tag or "").strip().lower()
        with self._rlock:
            current = self.get(tid)
            if not current:
                return self.set_user_tags(tid, [])
            new_tags = [t for t in current.user_tags.tags if t != norm]
            return self.set_user_tags(tid, new_tags)

    def bulk_update(self, updates: Dict[str, Dict[str, Any]]) -> Dict[str, TicketMetadata]:
        """Aplica múltiples updates en una sola escritura.

        ``updates`` es ``{ticket_id: {campo: valor, ...}}``.
        Campos soportados: color, user_tags, commits_count, last_commit_hash,
                          last_commit_at, ado_comments_count, notes_count,
                          last_note_at, last_indexed_at
        Claves ausentes = no tocar. Valor ``None`` en campos = borrar/clear.
        Errores por ticket se recolectan y lanzan al final (escritura all-or-nothing).
        """
        if not updates:
            return {}
        results: Dict[str, TicketMetadata] = {}
        errors: List[str] = []
        with self._rlock:
            current = self._load_locked()
            # Trabajar sobre una copia (staging) para garantizar all-or-nothing:
            # si algún patch falla, ni el cache ni el disco quedan tocados.
            staged = _StoreModel(**current.to_dict())
            for raw_tid, patch in updates.items():
                tid = str(raw_tid)
                try:
                    src = staged.tickets.get(tid)
                    # Copy defensiva para no compartir referencias con el cache original
                    if src is not None:
                        meta = TicketMetadata(**src.to_dict())
                    else:
                        meta = TicketMetadata(ticket_id=tid)

                    # Actualizar campos genéricamente
                    if "color" in patch:
                        hex_color = patch["color"]
                        meta.color = TicketColor(hex=hex_color) if hex_color else None
                    if "user_tags" in patch:
                        meta.user_tags = TicketUserTags(tags=list(patch["user_tags"] or []))

                    # Campos del indexador
                    for field in ("commits_count", "last_commit_hash", "last_commit_at",
                                  "ado_comments_count", "notes_count", "last_note_at",
                                  "last_indexed_at"):
                        if field in patch:
                            setattr(meta, field, patch[field])

                    staged.tickets[tid] = self._touch(meta)
                    results[tid] = meta
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{tid}: {e}")
            if errors:
                _safe_slog_error("-", "metadata_bulk_update", "user",
                                 TicketMetadataError("; ".join(errors)))
                raise TicketMetadataError(f"bulk_update errores: {'; '.join(errors)}")
            self._flush_locked(staged)
            _safe_slog_action("-", "metadata_bulk_update",
                              detail=f"updated={len(results)}")
        return results


# ── Singleton ─────────────────────────────────────────────────────────────────
_SINGLETON: Optional[_TicketMetadataStore] = None
_SINGLETON_LOCK = threading.Lock()


def get_store() -> _TicketMetadataStore:
    """Retorna la instancia singleton del store."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = _TicketMetadataStore()
    return _SINGLETON


def reset_singleton_for_tests() -> None:
    """Limpia el singleton — solo para uso en tests."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None
