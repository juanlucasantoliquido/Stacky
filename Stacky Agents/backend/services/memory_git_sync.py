"""Git sync for Stacky collaborative memory (Phase E).

This module keeps Phase E behind explicit calls/flags and reuses the local
memory store from Phase A-D. It exports eligible local memory into append-only
`.jsonl.gz` chunks in a dedicated repository under `Stacky/memory_repos/<project>`
and imports chunks idempotently from that repository.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import random
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from db import Base, session_scope
from runtime_paths import ensure_stacky_home
from services import memory_store, pii_masker
from services.secret_scanner import find_secret

logger = logging.getLogger("stacky.memory_git_sync")

# Lock por-proyecto (in-proc) para serializar sync_once del mismo proyecto.
_project_locks: dict[str, threading.Lock] = {}
_project_locks_guard = threading.Lock()


def _project_lock(project: str) -> threading.Lock:
    with _project_locks_guard:
        lock = _project_locks.get(project)
        if lock is None:
            lock = threading.Lock()
            _project_locks[project] = lock
        return lock


EXPORTABLE_SCOPES = ("project", "team", "global")
OUTBOX_STATUSES = ("pending", "exported", "error")
CHUNK_STATUSES = ("pending_push", "pushed", "imported", "quarantined", "unreadable")
DEFAULT_BRANCH = "main"


class StackyMemorySyncOutbox(Base):
    __tablename__ = "stacky_memory_sync_outbox"

    id = Column(Integer, primary_key=True)
    project = Column(String(80), nullable=False)
    event_type = Column(String(40), nullable=False)
    entity_id = Column(String(80), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    chunk_id = Column(String(80))
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime)
    last_error = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    exported_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("project", "event_type", "entity_id", "payload_hash", name="uq_stacky_memsync_outbox_event"),
        Index("ix_stacky_memsync_outbox_project_status", "project", "status", "next_attempt_at"),
        Index("ix_stacky_memsync_outbox_chunk", "chunk_id"),
    )

    @property
    def payload(self) -> dict:
        return _json_loads(self.payload_json) or {}

    @payload.setter
    def payload(self, value: dict) -> None:
        self.payload_json = _canonical_json(value)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "event_type": self.event_type,
            "entity_id": self.entity_id,
            "payload_hash": self.payload_hash,
            "status": self.status,
            "chunk_id": self.chunk_id,
            "attempts": self.attempts,
            "next_attempt_at": _iso(self.next_attempt_at),
            "last_error": self.last_error,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "exported_at": _iso(self.exported_at),
        }


class StackyMemorySyncChunk(Base):
    __tablename__ = "stacky_memory_sync_chunks"

    id = Column(Integer, primary_key=True)
    project = Column(String(80), nullable=False)
    chunk_id = Column(String(80), nullable=False)
    sha256 = Column(String(64), nullable=False)
    rel_path = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="imported")
    event_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    imported_at = Column(DateTime)
    pushed_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project", "chunk_id", name="uq_stacky_memsync_chunk_project_chunk"),
        Index("ix_stacky_memsync_chunks_project_status", "project", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "chunk_id": self.chunk_id,
            "sha256": self.sha256,
            "rel_path": self.rel_path,
            "status": self.status,
            "event_count": self.event_count,
            "error_message": self.error_message,
            "created_at": _iso(self.created_at),
            "imported_at": _iso(self.imported_at),
            "pushed_at": _iso(self.pushed_at),
            "updated_at": _iso(self.updated_at),
        }


@dataclass
class GitCommandResult:
    ok: bool
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    skipped: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": _redact_command(self.command),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "skipped": self.skipped,
        }


@dataclass
class SyncResult:
    project: str
    repo_path: str
    enabled: bool
    remote_url: str | None = None
    bootstrapped: bool = False
    imported_chunks: int = 0
    quarantined_chunks: int = 0
    unreadable_chunks: int = 0
    enqueued_events: int = 0
    exported_events: int = 0
    chunk_id: str | None = None
    pushed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    git_steps: list[GitCommandResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "project": self.project,
            "repo_path": self.repo_path,
            "enabled": self.enabled,
            "remote_url": self.remote_url,
            "bootstrapped": self.bootstrapped,
            "imported_chunks": self.imported_chunks,
            "quarantined_chunks": self.quarantined_chunks,
            "unreadable_chunks": self.unreadable_chunks,
            "enqueued_events": self.enqueued_events,
            "exported_events": self.exported_events,
            "chunk_id": self.chunk_id,
            "pushed": self.pushed,
            "errors": self.errors,
            "warnings": self.warnings,
            "git_steps": [s.to_dict() for s in self.git_steps],
        }


def sync_once(
    *,
    project: str,
    enabled: bool | None = None,
    remote_url: str | None = None,
    push: bool = True,
    timeout_seconds: int | None = None,
    max_events: int = 200,
) -> dict:
    """Runs one import/export/push cycle.

    Default is disabled via `STACKY_MEMORY_GIT_SYNC_ENABLED=false`; callers can
    pass `enabled=True` for explicit operator-triggered syncs/tests.
    """
    project = _normalize_project(project)
    enabled = _env_bool("STACKY_MEMORY_GIT_SYNC_ENABLED", False) if enabled is None else bool(enabled)
    remote_url = remote_url or _resolve_remote_url(project)
    repo = repo_path_for_project(project)
    result = SyncResult(
        project=project,
        repo_path=str(repo),
        enabled=enabled,
        remote_url=remote_url,
    )
    if not enabled:
        result.warnings.append("STACKY_MEMORY_GIT_SYNC_ENABLED=false; sync omitido")
        return result.to_dict()

    timeout_seconds = timeout_seconds or _env_int("STACKY_MEMORY_GIT_TIMEOUT_SECONDS", 30)

    # Lock por-proyecto (in-proc): bootstrap + commit + push tocan el mismo repo
    # git dedicado y el mismo outbox. Dos sync_once concurrentes del mismo
    # proyecto se serializan para evitar carreras en index.lock / doble export.
    with _project_lock(project):
        result.bootstrapped = bootstrap_repo(project=project, remote_url=remote_url, timeout_seconds=timeout_seconds, steps=result.git_steps)

        if remote_url:
            _fetch_and_ff_merge(repo, timeout_seconds, result.git_steps, result.warnings)

        import_summary = import_chunks(project=project, repo_path=repo)
        result.imported_chunks = import_summary["imported_chunks"]
        result.quarantined_chunks = import_summary["quarantined_chunks"]
        result.unreadable_chunks = import_summary["unreadable_chunks"]

        result.enqueued_events = enqueue_exportable(project=project)
        pending_push = _pending_push_chunk_ids(project)
        if pending_push and remote_url and push:
            pushed = _push_with_retry(project, repo, timeout_seconds, result.git_steps, result.warnings)
            result.pushed = pushed
            if not pushed:
                result.errors.append("git push falló; outbox queda pending para el próximo ciclo")
                return result.to_dict()

        chunk = export_pending_chunk(project=project, repo_path=repo, max_events=max_events)
        if chunk:
            result.chunk_id = chunk["chunk_id"]
            result.exported_events = chunk["event_count"]
            commit = _commit_all(repo, f"stacky memory sync {chunk['chunk_id']}", timeout_seconds)
            result.git_steps.append(commit)
            if not commit.ok:
                result.errors.append(f"git commit falló: {commit.stderr or commit.stdout}")
                return result.to_dict()

        if remote_url and push and (chunk or _pending_push_chunk_ids(project)):
            pushed = _push_with_retry(project, repo, timeout_seconds, result.git_steps, result.warnings)
            result.pushed = pushed
            if not pushed:
                result.errors.append("git push falló; outbox queda pending para el próximo ciclo")
        elif not remote_url:
            _mark_project_pending_chunks_pushed(project)
            _mark_project_pending_outbox_exported(project)
            result.pushed = False
            result.warnings.append("remote_url no configurado; chunk committeado solo en repo local dedicado")

    return result.to_dict()


def status(project: str, *, remote_url: str | None = None, timeout_seconds: int | None = None) -> dict:
    project = _normalize_project(project)
    repo = repo_path_for_project(project)
    remote_url = remote_url or _resolve_remote_url(project)
    counts = {"outbox": {}, "chunks": {}}
    with session_scope() as session:
        for st in OUTBOX_STATUSES:
            counts["outbox"][st] = (
                session.query(StackyMemorySyncOutbox)
                .filter(StackyMemorySyncOutbox.project == project, StackyMemorySyncOutbox.status == st)
                .count()
            )
        for st in CHUNK_STATUSES:
            counts["chunks"][st] = (
                session.query(StackyMemorySyncChunk)
                .filter(StackyMemorySyncChunk.project == project, StackyMemorySyncChunk.status == st)
                .count()
            )
    probe = None
    if remote_url:
        auth_header = _resolve_auth_header_for_project(project)
        probe = _run_git(
            repo if repo.exists() else ensure_stacky_home(),
            ["ls-remote", "--heads", remote_url],
            timeout_seconds or _env_int("STACKY_MEMORY_GIT_TIMEOUT_SECONDS", 30),
            auth_header=auth_header,
        ).to_dict()
    return {
        "project": project,
        "enabled": _env_bool("STACKY_MEMORY_GIT_SYNC_ENABLED", False),
        "repo_path": str(repo),
        "repo_exists": repo.exists(),
        "remote_url": remote_url,
        "counts": counts,
        "ls_remote": probe,
    }


def bootstrap_repo(
    *,
    project: str,
    remote_url: str | None = None,
    timeout_seconds: int = 30,
    steps: list[GitCommandResult] | None = None,
) -> bool:
    project = _normalize_project(project)
    repo = repo_path_for_project(project)
    repo.mkdir(parents=True, exist_ok=True)
    steps = steps if steps is not None else []
    bootstrapped = False

    if not (repo / ".git").exists():
        init = _run_git(repo, ["init", "-b", DEFAULT_BRANCH], timeout_seconds)
        if not init.ok and "unknown switch" in (init.stderr or ""):
            init = _run_git(repo, ["init"], timeout_seconds)
            if init.ok:
                steps.append(_run_git(repo, ["checkout", "-B", DEFAULT_BRANCH], timeout_seconds))
        steps.append(init)
        bootstrapped = True

    steps.append(_run_git(repo, ["config", "core.autocrlf", "false"], timeout_seconds))
    steps.append(_run_git(repo, ["config", "core.longpaths", "true"], timeout_seconds))
    steps.append(_run_git(repo, ["config", "user.email", "stacky-memory@local"], timeout_seconds))
    steps.append(_run_git(repo, ["config", "user.name", "Stacky Memory Sync"], timeout_seconds))

    if remote_url:
        remote = _run_git(repo, ["remote", "get-url", "origin"], timeout_seconds)
        if remote.ok and remote.stdout.strip() != remote_url:
            steps.append(_run_git(repo, ["remote", "set-url", "origin", remote_url], timeout_seconds))
        elif not remote.ok:
            steps.append(_run_git(repo, ["remote", "add", "origin", remote_url], timeout_seconds))

    if not (repo / ".gitignore").exists():
        _atomic_write_text(repo / ".gitignore", ".quarantine/\n*.tmp\n")
        steps.append(_commit_all(repo, "bootstrap stacky memory repo", timeout_seconds))
        bootstrapped = True
    else:
        head = _run_git(repo, ["rev-parse", "--verify", "HEAD"], timeout_seconds)
        steps.append(head)
        if not head.ok:
            steps.append(_commit_all(repo, "bootstrap stacky memory repo", timeout_seconds))
            bootstrapped = True
    return bootstrapped


def repo_path_for_project(project: str) -> Path:
    return ensure_stacky_home() / "memory_repos" / _project_slug(project)


def _quarantine_secrets_before_export(project: str) -> None:
    """Cuarentena de memorias activas con secretos, en su propia transacción.

    Query → mutate → commit sin SELECTs intermedios (el patrón con un segundo
    query en la misma sesión dispara 'database table is locked' en SQLite al
    autoflushear el UPDATE). Best-effort por fila.
    """
    now = datetime.utcnow()
    with session_scope() as session:
        rows = (
            session.query(memory_store.StackyMemoryObservation)
            .filter(
                memory_store.StackyMemoryObservation.project == project,
                memory_store.StackyMemoryObservation.status == "active",
                memory_store.StackyMemoryObservation.scope.in_(EXPORTABLE_SCOPES),
                memory_store.StackyMemoryObservation.deleted_at.is_(None),
            )
            .all()
        )
        for row in rows:
            if find_secret(f"{row.title or ''}\n{row.content or ''}") is not None:
                row.status = "quarantined"
                row.updated_at = now
                logger.warning(
                    "memoria %s con secreto detectado: cuarentena, no se exporta",
                    row.memory_id,
                )


def enqueue_exportable(*, project: str) -> int:
    """Creates outbox rows for active non-private local memory and relations."""
    project = _normalize_project(project)
    # Invariante de seguridad: cuarentena de secretos ANTES de exportar, en su
    # propia transacción. Ningún secreto cruza el límite de confianza hacia el
    # repo compartido, independiente de que haya corrido o no un validation run.
    _quarantine_secrets_before_export(project)

    created = 0
    now = datetime.utcnow()
    with session_scope() as session:
        rows = (
            session.query(memory_store.StackyMemoryObservation)
            .filter(
                memory_store.StackyMemoryObservation.project == project,
                memory_store.StackyMemoryObservation.status == "active",
                memory_store.StackyMemoryObservation.scope.in_(EXPORTABLE_SCOPES),
                memory_store.StackyMemoryObservation.deleted_at.is_(None),
            )
            .order_by(memory_store.StackyMemoryObservation.updated_at.asc())
            .all()
        )
        for row in rows:
            payload = _observation_payload(row)
            created += _ensure_outbox_event(
                session=session,
                project=project,
                event_type="observation",
                entity_id=row.memory_id,
                payload=payload,
                now=now,
            )

        rels = (
            session.query(memory_store.StackyMemoryRelation)
            .filter(memory_store.StackyMemoryRelation.project == project)
            .order_by(memory_store.StackyMemoryRelation.updated_at.asc())
            .all()
        )
        for rel in rels:
            payload = _relation_payload(rel)
            created += _ensure_outbox_event(
                session=session,
                project=project,
                event_type="relation",
                entity_id=rel.relation_id,
                payload=payload,
                now=now,
            )
    return created


def export_pending_chunk(*, project: str, repo_path: Path | None = None, max_events: int = 200) -> dict | None:
    project = _normalize_project(project)
    repo = repo_path or repo_path_for_project(project)
    now = datetime.utcnow()
    with session_scope() as session:
        rows = (
            session.query(StackyMemorySyncOutbox)
            .filter(
                StackyMemorySyncOutbox.project == project,
                StackyMemorySyncOutbox.status == "pending",
                StackyMemorySyncOutbox.chunk_id.is_(None),
            )
            .order_by(StackyMemorySyncOutbox.created_at.asc(), StackyMemorySyncOutbox.id.asc())
            .limit(max_events)
            .all()
        )
        if not rows:
            return None
        chunk_id = f"chunk-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:12]}"
        events = []
        for row in rows:
            events.append(
                {
                    "schema_version": 1,
                    "chunk_id": chunk_id,
                    "event_id": f"evt-{row.id}",
                    "event_type": row.event_type,
                    "entity_id": row.entity_id,
                    "payload_hash": row.payload_hash,
                    "payload": row.payload,
                    "exported_at": now.isoformat(),
                }
            )
        rel_path = Path("chunks") / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d") / f"{chunk_id}.jsonl.gz"
        abs_path = repo / rel_path
        sha = write_chunk_atomic(abs_path, events)
        for row in rows:
            row.chunk_id = chunk_id
            row.updated_at = now
        chunk = StackyMemorySyncChunk(
            project=project,
            chunk_id=chunk_id,
            sha256=sha,
            rel_path=str(rel_path).replace("\\", "/"),
            status="pending_push",
            event_count=len(events),
            created_at=now,
            updated_at=now,
        )
        session.add(chunk)
        session.flush()
        return {"chunk_id": chunk_id, "event_count": len(events), "rel_path": str(rel_path), "sha256": sha}


def write_chunk_atomic(path: Path, events: list[dict]) -> str:
    """Writes deterministic gzip JSONL bytes with temp + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join((_canonical_json(evt) + "\n").encode("utf-8") for evt in events)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with tmp_path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
                gz.write(payload)
        sha = _sha256_file(tmp_path)
        os.replace(tmp_path, path)
        return sha
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def import_chunks(*, project: str, repo_path: Path | None = None) -> dict:
    project = _normalize_project(project)
    repo = repo_path or repo_path_for_project(project)
    summary = {"imported_chunks": 0, "quarantined_chunks": 0, "unreadable_chunks": 0, "events_imported": 0}
    if not repo.exists():
        return summary
    for path in sorted((repo / "chunks").glob("**/*.jsonl.gz")):
        chunk_id = path.name.removesuffix(".jsonl.gz")
        sha = _sha256_file(path)
        existing = _get_chunk(project, chunk_id)
        if existing and existing["sha256"] == sha and existing["status"] in {"imported", "pushed"}:
            continue
        try:
            events = _read_chunk_events(path)
        except Exception as exc:  # noqa: BLE001
            _record_chunk(project, chunk_id, sha, path.relative_to(repo), "unreadable", 0, str(exc))
            summary["unreadable_chunks"] += 1
            continue
        if existing and existing["sha256"] != sha:
            _quarantine_chunk(repo, path, chunk_id)
            _record_chunk(
                project,
                chunk_id,
                sha,
                path.relative_to(repo),
                "quarantined",
                len(events),
                f"chunk sha changed from {existing['sha256']} to {sha}",
            )
            summary["quarantined_chunks"] += 1
            continue
        imported = 0
        for event in events:
            if _import_event(project, event):
                imported += 1
        _record_chunk(project, chunk_id, sha, path.relative_to(repo), "imported", len(events), None)
        summary["imported_chunks"] += 1
        summary["events_imported"] += imported
    return summary


def _import_event(project: str, event: dict) -> bool:
    event_type = event.get("event_type")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if find_secret(_canonical_json(payload)):
        return False
    if event_type == "observation":
        return _import_observation(project, payload)
    if event_type == "relation":
        return _import_relation(project, payload)
    if event_type == "tombstone":
        memory_id = payload.get("memory_id") or event.get("entity_id")
        return bool(memory_id and memory_store.set_status(memory_id, "deleted"))
    return False


def _import_observation(project: str, payload: dict) -> bool:
    memory_id = payload.get("memory_id")
    if not memory_id:
        return False
    now = datetime.utcnow()
    with session_scope() as session:
        row = (
            session.query(memory_store.StackyMemoryObservation)
            .filter(memory_store.StackyMemoryObservation.memory_id == memory_id)
            .first()
        )
        if row is not None:
            if row.normalized_hash == payload.get("normalized_hash"):
                return False
            incoming_updated = _parse_dt(payload.get("updated_at"))
            if incoming_updated and row.updated_at and incoming_updated <= row.updated_at:
                return False
        else:
            row = memory_store.StackyMemoryObservation(memory_id=memory_id, created_at=_parse_dt(payload.get("created_at")) or now)
            session.add(row)
        row.project = project
        row.scope = payload.get("scope") or "project"
        row.type = payload.get("type") or "discovery"
        row.title = payload.get("title") or "(sin titulo)"
        row.content = payload.get("content") or ""
        row.topic_key = payload.get("topic_key")
        row.status = payload.get("status") or "active"
        row.confidence = payload.get("confidence")
        row.source_kind = payload.get("source_kind")
        row.source_execution_id = payload.get("source_execution_id")
        row.source_ticket_id = payload.get("source_ticket_id")
        row.source_ado_id = payload.get("source_ado_id")
        row.source_agent_type = payload.get("source_agent_type")
        row.author_email = payload.get("author_email")
        row.author_role = payload.get("author_role")
        row.tags_json = json.dumps(payload.get("tags") or [])
        row.normalized_hash = payload.get("normalized_hash") or memory_store._normalized_hash(row.title, row.content)
        row.revision_count = int(payload.get("revision_count") or 1)
        row.duplicate_count = int(payload.get("duplicate_count") or 1)
        row.last_seen_at = _parse_dt(payload.get("last_seen_at")) or now
        row.expires_at = _parse_dt(payload.get("expires_at"))
        row.updated_at = _parse_dt(payload.get("updated_at")) or now
        return True


def _import_relation(project: str, payload: dict) -> bool:
    relation_id = payload.get("relation_id")
    if not relation_id:
        return False
    now = datetime.utcnow()
    with session_scope() as session:
        rel = (
            session.query(memory_store.StackyMemoryRelation)
            .filter(memory_store.StackyMemoryRelation.relation_id == relation_id)
            .first()
        )
        if rel is not None:
            return False
        rel = memory_store.StackyMemoryRelation(
            relation_id=relation_id,
            project=project,
            source_memory_id=payload.get("source_memory_id") or "",
            target_memory_id=payload.get("target_memory_id") or "",
            relation=payload.get("relation") or "related",
            status=payload.get("status") or "judged",
            reason=payload.get("reason"),
            evidence=payload.get("evidence"),
            confidence=payload.get("confidence"),
            marked_by_actor=payload.get("marked_by_actor"),
            marked_by_kind=payload.get("marked_by_kind"),
            marked_by_model=payload.get("marked_by_model"),
            created_at=_parse_dt(payload.get("created_at")) or now,
            updated_at=_parse_dt(payload.get("updated_at")) or now,
        )
        session.add(rel)
        if rel.relation == "supersedes":
            old = (
                session.query(memory_store.StackyMemoryObservation)
                .filter(memory_store.StackyMemoryObservation.memory_id == rel.target_memory_id)
                .first()
            )
            if old is not None and old.status == "active":
                old.status = "superseded"
                old.updated_at = now
        return True


def _push_with_retry(
    project: str,
    repo: Path,
    timeout_seconds: int,
    steps: list[GitCommandResult],
    warnings: list[str],
) -> bool:
    auth_header = _resolve_auth_header_for_project(project)
    attempts = _env_int("STACKY_MEMORY_GIT_PUSH_ATTEMPTS", 6)
    cap = float(os.getenv("STACKY_MEMORY_GIT_PUSH_BACKOFF_CAP", "30"))
    base = float(os.getenv("STACKY_MEMORY_GIT_PUSH_BACKOFF_BASE", "1"))
    for attempt in range(1, attempts + 1):
        step = _run_git(repo, ["push", "-u", "origin", DEFAULT_BRANCH], timeout_seconds, auth_header=auth_header)
        steps.append(step)
        if step.ok:
            _mark_project_pending_chunks_pushed(project)
            _mark_project_pending_outbox_exported(project)
            return True
        _bump_pending_push_attempts(project, step.stderr or step.stdout or "git push failed")
        if attempt < attempts:
            sleep = random.uniform(0, min(cap, base * (2 ** (attempt - 1))))
            warnings.append(f"push retry {attempt}/{attempts} en {sleep:.2f}s")
            time.sleep(sleep)
    return False


def _fetch_and_ff_merge(repo: Path, timeout_seconds: int, steps: list[GitCommandResult], warnings: list[str]) -> None:
    fetch = _run_git(repo, ["fetch", "--prune", "origin"], timeout_seconds)
    steps.append(fetch)
    if not fetch.ok:
        warnings.append("git fetch origin falló; se continúa con el estado local")
        return
    merge = _run_git(repo, ["merge", "--ff-only", f"origin/{DEFAULT_BRANCH}"], timeout_seconds)
    steps.append(merge)
    if not merge.ok:
        warnings.append("git merge --ff-only origin/main falló; se continúa con el estado local")


def _commit_all(repo: Path, message: str, timeout_seconds: int) -> GitCommandResult:
    add = _run_git(repo, ["add", "-A"], timeout_seconds)
    if not add.ok:
        return add
    diff = _run_git(repo, ["diff", "--cached", "--quiet"], timeout_seconds)
    if diff.ok:
        return GitCommandResult(ok=True, command=["git", "commit"], stdout="sin cambios para commitear", skipped=True)
    return _run_git(repo, ["commit", "-m", message], timeout_seconds)


def _run_git(cwd: Path, args: list[str], timeout_seconds: int, *, auth_header: str | None = None) -> GitCommandResult:
    cmd = ["git"]
    if auth_header:
        cmd.extend(["-c", f"http.extraheader=Authorization: {auth_header}", "-c", "credential.helper="])
    cmd.extend(args)
    env = os.environ.copy()
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
        }
    )
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return GitCommandResult(
            ok=proc.returncode == 0,
            command=cmd,
            stdout=(proc.stdout or "").strip(),
            stderr=(proc.stderr or "").strip(),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except subprocess.TimeoutExpired as exc:
        return GitCommandResult(
            ok=False,
            command=cmd,
            stdout=(exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            stderr=f"timeout after {timeout_seconds}s",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except OSError as exc:
        return GitCommandResult(
            ok=False,
            command=cmd,
            stderr=str(exc),
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def _ensure_outbox_event(
    *,
    session,
    project: str,
    event_type: str,
    entity_id: str,
    payload: dict,
    now: datetime,
) -> int:
    payload_hash = _payload_hash(payload)
    exists = (
        session.query(StackyMemorySyncOutbox)
        .filter(
            StackyMemorySyncOutbox.project == project,
            StackyMemorySyncOutbox.event_type == event_type,
            StackyMemorySyncOutbox.entity_id == entity_id,
            StackyMemorySyncOutbox.payload_hash == payload_hash,
        )
        .first()
    )
    if exists is not None:
        return 0
    row = StackyMemorySyncOutbox(
        project=project,
        event_type=event_type,
        entity_id=entity_id,
        payload_hash=payload_hash,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    row.payload = payload
    session.add(row)
    return 1


def _observation_payload(row: memory_store.StackyMemoryObservation) -> dict:
    # Redacción PII IRREVERSIBLE antes de cruzar al repo compartido: el map
    # reversible de pii_masker es per-run y no sobrevive a la exportación.
    # Recomputamos normalized_hash sobre el contenido redactado para que el
    # check de checksum del receptor no falle al importar.
    data = row.to_dict()
    title = pii_masker.redact_irreversible(data.get("title"))
    content = pii_masker.redact_irreversible(data.get("content"))
    data["title"] = title
    data["content"] = content
    return {
        **data,
        "normalized_hash": memory_store._normalized_hash(title, content),
        "last_seen_at": _iso(row.last_seen_at),
        "expires_at": _iso(row.expires_at),
        "deleted_at": _iso(row.deleted_at),
    }


def _relation_payload(rel: memory_store.StackyMemoryRelation) -> dict:
    return {
        "relation_id": rel.relation_id,
        "project": rel.project,
        "source_memory_id": rel.source_memory_id,
        "target_memory_id": rel.target_memory_id,
        "relation": rel.relation,
        "status": rel.status,
        "reason": rel.reason,
        "evidence": rel.evidence,
        "confidence": rel.confidence,
        "marked_by_actor": rel.marked_by_actor,
        "marked_by_kind": rel.marked_by_kind,
        "marked_by_model": rel.marked_by_model,
        "source_validation_run_id": rel.source_validation_run_id,
        "created_at": _iso(rel.created_at),
        "updated_at": _iso(rel.updated_at),
    }


def _record_chunk(
    project: str,
    chunk_id: str,
    sha: str,
    rel_path: Path,
    status: str,
    event_count: int,
    error: str | None,
) -> None:
    now = datetime.utcnow()
    with session_scope() as session:
        row = (
            session.query(StackyMemorySyncChunk)
            .filter(StackyMemorySyncChunk.project == project, StackyMemorySyncChunk.chunk_id == chunk_id)
            .first()
        )
        if row is None:
            row = StackyMemorySyncChunk(project=project, chunk_id=chunk_id, created_at=now)
            session.add(row)
        row.sha256 = sha
        row.rel_path = str(rel_path).replace("\\", "/")
        row.status = status
        row.event_count = event_count
        row.error_message = error
        row.updated_at = now
        if status == "imported":
            row.imported_at = now


def _get_chunk(project: str, chunk_id: str) -> dict | None:
    with session_scope() as session:
        row = (
            session.query(StackyMemorySyncChunk)
            .filter(StackyMemorySyncChunk.project == project, StackyMemorySyncChunk.chunk_id == chunk_id)
            .first()
        )
        return row.to_dict() if row is not None else None


def _pending_push_chunk_ids(project: str) -> list[str]:
    with session_scope() as session:
        rows = (
            session.query(StackyMemorySyncChunk.chunk_id)
            .filter(StackyMemorySyncChunk.project == project, StackyMemorySyncChunk.status == "pending_push")
            .all()
        )
        return [r[0] for r in rows]


def _mark_project_pending_chunks_pushed(project: str) -> None:
    now = datetime.utcnow()
    with session_scope() as session:
        rows = (
            session.query(StackyMemorySyncChunk)
            .filter(StackyMemorySyncChunk.project == project, StackyMemorySyncChunk.status == "pending_push")
            .all()
        )
        for row in rows:
            row.status = "pushed"
            row.pushed_at = now
            row.updated_at = now


def _mark_project_pending_outbox_exported(project: str) -> None:
    now = datetime.utcnow()
    with session_scope() as session:
        rows = (
            session.query(StackyMemorySyncOutbox)
            .filter(
                StackyMemorySyncOutbox.project == project,
                StackyMemorySyncOutbox.status == "pending",
                StackyMemorySyncOutbox.chunk_id.isnot(None),
            )
            .all()
        )
        for row in rows:
            row.status = "exported"
            row.exported_at = now
            row.updated_at = now


def _bump_pending_push_attempts(project: str, error: str) -> None:
    now = datetime.utcnow()
    with session_scope() as session:
        rows = (
            session.query(StackyMemorySyncOutbox)
            .filter(
                StackyMemorySyncOutbox.project == project,
                StackyMemorySyncOutbox.status == "pending",
                StackyMemorySyncOutbox.chunk_id.isnot(None),
            )
            .all()
        )
        for row in rows:
            row.attempts = (row.attempts or 0) + 1
            row.last_error = error[:1000]
            row.updated_at = now


def _read_chunk_events(path: Path) -> list[dict]:
    events: list[dict] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            event = json.loads(raw)
            if not isinstance(event, dict) or "event_type" not in event:
                raise ValueError(f"invalid event at line {line_no}")
            events.append(event)
    return events


def _quarantine_chunk(repo: Path, path: Path, chunk_id: str) -> None:
    qdir = repo / ".quarantine"
    qdir.mkdir(parents=True, exist_ok=True)
    target = qdir / path.name
    if target.exists():
        target = qdir / f"{chunk_id}-{uuid.uuid4().hex[:8]}.jsonl.gz"
    shutil.copy2(path, target)


def _resolve_remote_url(project: str) -> str | None:
    env = os.getenv("STACKY_MEMORY_GIT_REMOTE_URL", "").strip()
    if env:
        return env
    try:
        from project_manager import get_project_config

        cfg = get_project_config(project) or get_project_config(project.upper()) or {}
        memory_cfg = cfg.get("memory") or cfg.get("git_sync") or {}
        return (memory_cfg.get("remote_url") or memory_cfg.get("git_remote_url") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def _resolve_auth_header_for_project(project: str) -> str | None:
    try:
        from services.ado_client import _resolve_auth_header
        from services.project_context import resolve_project_context

        ctx = resolve_project_context(project_name=project)
        return _resolve_auth_header(ctx.auth_path if ctx else None)
    except Exception:  # noqa: BLE001
        return None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _normalize_project(project: str) -> str:
    raw = (project or "").strip()
    if not raw:
        raise ValueError("project is required")
    return raw.upper()


def _project_slug(project: str) -> str:
    keep = []
    for ch in _normalize_project(project):
        keep.append(ch.lower() if ch.isalnum() else "-")
    slug = "".join(keep).strip("-")
    return slug or "project"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _redact_command(cmd: list[str]) -> list[str]:
    redacted = []
    for part in cmd:
        if part.startswith("http.extraheader=Authorization:"):
            redacted.append("http.extraheader=Authorization: <redacted>")
        else:
            redacted.append(part)
    return redacted
