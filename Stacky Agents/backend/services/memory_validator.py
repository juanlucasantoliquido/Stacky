"""Deterministic validator for Stacky memory (Phase D MVP)."""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from db import Base, session_scope
from services import memory_store
from services.secret_scanner import find_secret

logger = logging.getLogger("stacky.memory_validator")

RUN_STATUSES = ("queued", "running", "completed", "error")
FINDING_STATUSES = ("open", "resolved")
# Checks baratos y deterministas = MVP de Fase D; corren siempre por default.
_CHEAP_CHECKS = ("schema", "checksum", "secret", "duplicate_exact")
# Checks caros (O(n^2) / LLM judge) = material de Fase F; gateados detrás de
# STACKY_MEMORY_VALIDATOR_ADVANCED para no gastar tokens ni CPU sin pedirlo.
_ADVANCED_CHECKS = ("duplicate_semantic", "conflict_graph", "llm_judge")
CHECKS = _CHEAP_CHECKS + _ADVANCED_CHECKS


def _advanced_enabled() -> bool:
    return os.getenv("STACKY_MEMORY_VALIDATOR_ADVANCED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
VALID_SCOPES = ("project", "team", "global", "personal", "private")
FINDING_ACTIONS = (
    "resolve_finding",
    "activate_memory",
    "needs_review_memory",
    "quarantine_memory",
    "mark_supersedes",
    "mark_duplicates",
    "mark_conflicts_with",
    "mark_not_conflict",
)


class StackyMemoryValidationRun(Base):
    __tablename__ = "stacky_memory_validation_runs"

    id = Column(Integer, primary_key=True)
    project = Column(String(80))
    status = Column(String(20), nullable=False, default="queued")
    requested_by = Column(String(200))
    checks_json = Column(Text)
    summary_json = Column(Text)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_stacky_memval_runs_status", "status", "created_at"),
        Index("ix_stacky_memval_runs_project", "project", "created_at"),
    )

    @property
    def checks(self) -> list[str]:
        return _json_loads(self.checks_json) or []

    @checks.setter
    def checks(self, value: list[str]) -> None:
        self.checks_json = json.dumps(value or [])

    @property
    def summary(self) -> dict:
        return _json_loads(self.summary_json) or {}

    @summary.setter
    def summary(self, value: dict) -> None:
        self.summary_json = json.dumps(value or {})

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "status": self.status,
            "requested_by": self.requested_by,
            "checks": self.checks,
            "summary": self.summary,
            "error_message": self.error_message,
            "started_at": _iso(self.started_at),
            "completed_at": _iso(self.completed_at),
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


class StackyMemoryFinding(Base):
    __tablename__ = "stacky_memory_findings"

    id = Column(Integer, primary_key=True)
    validation_run_id = Column(Integer, nullable=False)
    project = Column(String(80), nullable=False)
    check_name = Column(String(40), nullable=False)
    severity = Column(String(20), nullable=False, default="warning")
    status = Column(String(20), nullable=False, default="open")
    memory_id = Column(String(40))
    title = Column(Text, nullable=False)
    detail = Column(Text)
    evidence_json = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_stacky_memfinding_project_status", "project", "status"),
        Index("ix_stacky_memfinding_run", "validation_run_id"),
        Index("ix_stacky_memfinding_memory", "memory_id"),
    )

    @property
    def evidence(self) -> dict:
        return _json_loads(self.evidence_json) or {}

    @evidence.setter
    def evidence(self, value: dict) -> None:
        self.evidence_json = json.dumps(value or {})

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "validation_run_id": self.validation_run_id,
            "project": self.project,
            "check_name": self.check_name,
            "severity": self.severity,
            "status": self.status,
            "memory_id": self.memory_id,
            "title": self.title,
            "detail": self.detail,
            "evidence": self.evidence,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


def start_validation_run(
    *,
    project: str | None = None,
    requested_by: str | None = None,
    checks: list[str] | None = None,
) -> int:
    selected = _normalize_checks(checks)
    now = datetime.utcnow()
    with session_scope() as session:
        row = StackyMemoryValidationRun(
            project=(project or "").strip() or None,
            status="queued",
            requested_by=requested_by,
            created_at=now,
            updated_at=now,
        )
        row.checks = selected
        row.summary = {"queued": True}
        session.add(row)
        session.flush()
        run_id = row.id

    thread = threading.Thread(
        target=_run_validation_background,
        args=(run_id,),
        daemon=True,
        name=f"stacky-memory-validator-{run_id}",
    )
    thread.start()
    return run_id


def run_validation_sync(
    *,
    project: str | None = None,
    requested_by: str | None = None,
    checks: list[str] | None = None,
) -> int:
    selected = _normalize_checks(checks)
    now = datetime.utcnow()
    with session_scope() as session:
        row = StackyMemoryValidationRun(
            project=(project or "").strip() or None,
            status="queued",
            requested_by=requested_by,
            created_at=now,
            updated_at=now,
        )
        row.checks = selected
        row.summary = {"queued": True}
        session.add(row)
        session.flush()
        run_id = row.id
    _run_validation_background(run_id)
    return run_id


def get_run(run_id: int) -> dict | None:
    with session_scope() as session:
        row = session.get(StackyMemoryValidationRun, run_id)
        return row.to_dict() if row else None


def list_runs(*, project: str | None = None, limit: int = 50) -> list[dict]:
    with session_scope() as session:
        q = session.query(StackyMemoryValidationRun)
        if project:
            q = q.filter(StackyMemoryValidationRun.project == project)
        rows = q.order_by(StackyMemoryValidationRun.created_at.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def list_findings(
    *,
    project: str | None = None,
    run_id: int | None = None,
    status: str | None = "open",
    check_name: str | None = None,
    severity: str | None = None,
    limit: int = 200,
) -> list[dict]:
    with session_scope() as session:
        q = session.query(StackyMemoryFinding)
        if project:
            q = q.filter(StackyMemoryFinding.project == project)
        if run_id is not None:
            q = q.filter(StackyMemoryFinding.validation_run_id == run_id)
        if status:
            q = q.filter(StackyMemoryFinding.status == status)
        if check_name:
            q = q.filter(StackyMemoryFinding.check_name == check_name)
        if severity:
            q = q.filter(StackyMemoryFinding.severity == severity)
        rows = q.order_by(StackyMemoryFinding.created_at.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def get_finding(finding_id: int) -> dict | None:
    with session_scope() as session:
        row = session.get(StackyMemoryFinding, finding_id)
        return row.to_dict() if row else None


def apply_finding_action(
    *,
    finding_id: int,
    action: str,
    actor: str | None = None,
    source_memory_id: str | None = None,
    target_memory_id: str | None = None,
    reason: str | None = None,
) -> dict:
    """Aplica una accion de curacion y resuelve el finding como mutacion auditada."""
    if action not in FINDING_ACTIONS:
        raise ValueError(f"unsupported finding action: {action}")

    with session_scope() as session:
        finding = session.get(StackyMemoryFinding, finding_id)
        if finding is None:
            raise LookupError("finding not found")
        evidence = finding.evidence or {}
        project = finding.project
        memory_ids = [
            str(x)
            for x in (evidence.get("memory_ids") or [])
            if isinstance(x, str) and x.strip()
        ]
        if finding.memory_id and finding.memory_id not in memory_ids:
            memory_ids.insert(0, finding.memory_id)

    source = source_memory_id or (memory_ids[0] if memory_ids else None)
    target = target_memory_id or (memory_ids[1] if len(memory_ids) > 1 else None)
    relation_id = None

    if action == "resolve_finding":
        pass
    elif action == "activate_memory":
        if not source:
            raise ValueError("source_memory_id is required")
        memory_store.set_status(source, "active")
    elif action == "needs_review_memory":
        if not source:
            raise ValueError("source_memory_id is required")
        memory_store.set_status(source, "needs_review")
    elif action == "quarantine_memory":
        if not source:
            raise ValueError("source_memory_id is required")
        memory_store.set_status(source, "quarantined")
    elif action == "mark_supersedes":
        if not source or not target:
            raise ValueError("source_memory_id and target_memory_id are required")
        relation_id = memory_store.mark_relation(
            project=project,
            source_memory_id=source,
            target_memory_id=target,
            relation="supersedes",
            reason=reason or f"finding:{finding_id}",
            marked_by_actor=actor,
            marked_by_kind="human",
        )
    elif action == "mark_duplicates":
        if not source or not target:
            raise ValueError("source_memory_id and target_memory_id are required")
        relation_id = memory_store.mark_relation(
            project=project,
            source_memory_id=source,
            target_memory_id=target,
            relation="duplicates",
            reason=reason or f"finding:{finding_id}",
            marked_by_actor=actor,
            marked_by_kind="human",
        )
    elif action == "mark_conflicts_with":
        if not source or not target:
            raise ValueError("source_memory_id and target_memory_id are required")
        relation_id = memory_store.mark_relation(
            project=project,
            source_memory_id=source,
            target_memory_id=target,
            relation="conflicts_with",
            reason=reason or f"finding:{finding_id}",
            marked_by_actor=actor,
            marked_by_kind="human",
        )
    elif action == "mark_not_conflict":
        if not source or not target:
            raise ValueError("source_memory_id and target_memory_id are required")
        relation_id = memory_store.resolve_conflicts_between(
            project=project,
            source_memory_id=source,
            target_memory_id=target,
            marked_by_actor=actor,
            reason=reason or f"finding:{finding_id}",
        )

    now = datetime.utcnow()
    with session_scope() as session:
        finding = session.get(StackyMemoryFinding, finding_id)
        if finding is None:
            raise LookupError("finding not found")
        next_evidence = finding.evidence or {}
        next_evidence["resolution"] = {
            "action": action,
            "actor": actor,
            "source_memory_id": source,
            "target_memory_id": target,
            "relation_id": relation_id,
            "reason": reason,
            "resolved_at": now.isoformat(),
        }
        finding.evidence = next_evidence
        finding.status = "resolved"
        finding.updated_at = now
        session.flush()
        return finding.to_dict()


def ticket_badges(*, project: str | None = None, status: str = "open") -> dict:
    """Agrupa hallazgos abiertos por `source_ticket_id` para badges en TicketBoard."""
    with session_scope() as session:
        q = session.query(StackyMemoryFinding)
        if project:
            q = q.filter(StackyMemoryFinding.project == project)
        if status:
            q = q.filter(StackyMemoryFinding.status == status)
        findings = q.order_by(StackyMemoryFinding.created_at.desc()).limit(1000).all()
        memory_ids = {f.memory_id for f in findings if f.memory_id}
        memory_by_id = {}
        if memory_ids:
            rows = (
                session.query(memory_store.StackyMemoryObservation)
                .filter(memory_store.StackyMemoryObservation.memory_id.in_(tuple(memory_ids)))
                .all()
            )
            memory_by_id = {r.memory_id: r for r in rows}

        by_ticket: dict[str, dict] = {}
        for finding in findings:
            row = memory_by_id.get(finding.memory_id)
            ticket_id = row.source_ticket_id if row is not None else None
            if ticket_id is None:
                continue
            key = str(ticket_id)
            entry = by_ticket.setdefault(
                key,
                {
                    "ticket_id": ticket_id,
                    "open_findings": 0,
                    "critical": 0,
                    "error": 0,
                    "warning": 0,
                    "info": 0,
                    "checks": {},
                },
            )
            entry["open_findings"] += 1
            sev = finding.severity or "warning"
            entry[sev] = int(entry.get(sev, 0)) + 1
            checks = entry["checks"]
            checks[finding.check_name] = int(checks.get(finding.check_name, 0)) + 1
        return by_ticket


def _run_validation_background(run_id: int) -> None:
    try:
        with session_scope() as session:
            run = session.get(StackyMemoryValidationRun, run_id)
            if run is None:
                return
            run.status = "running"
            run.started_at = datetime.utcnow()
            run.updated_at = run.started_at
            run.summary = {"queued": False, "running": True}
            project = run.project
            checks = run.checks

        pull_check = _best_effort_pull_check(project)
        findings_created = _execute_checks(run_id=run_id, project=project, checks=checks)

        with session_scope() as session:
            run = session.get(StackyMemoryValidationRun, run_id)
            if run is None:
                return
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.updated_at = run.completed_at
            run.summary = {
                "findings_created": findings_created,
                "checks": checks,
                "project": project,
                "pull_check": pull_check,
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("memory validation run failed: run_id=%s", run_id)
        with session_scope() as session:
            run = session.get(StackyMemoryValidationRun, run_id)
            if run is not None:
                run.status = "error"
                run.error_message = str(exc)
                run.completed_at = datetime.utcnow()
                run.updated_at = run.completed_at
                run.summary = {"traceback": traceback.format_exc(limit=8)}


def _execute_checks(*, run_id: int, project: str | None, checks: list[str]) -> int:
    with session_scope() as session:
        q = session.query(memory_store.StackyMemoryObservation).filter(
            memory_store.StackyMemoryObservation.deleted_at.is_(None)
        )
        if project:
            q = q.filter(memory_store.StackyMemoryObservation.project == project)
        rows = q.order_by(memory_store.StackyMemoryObservation.updated_at.desc()).all()

        findings: list[StackyMemoryFinding] = []
        if "schema" in checks:
            findings.extend(_check_schema(run_id, rows))
        if "checksum" in checks:
            findings.extend(_check_checksum(run_id, rows))
        if "secret" in checks:
            findings.extend(_check_secrets(run_id, rows))
        if "duplicate_exact" in checks:
            findings.extend(_check_duplicate_exact(run_id, rows))
        if "duplicate_semantic" in checks:
            findings.extend(_check_duplicate_semantic(run_id, rows))
        if "conflict_graph" in checks:
            findings.extend(_check_conflict_graph(run_id, project, rows))
        if "llm_judge" in checks:
            findings.extend(_check_llm_judge(run_id, rows))

        for finding in findings:
            session.add(finding)
        session.flush()
        return len(findings)


def _best_effort_pull_check(project: str | None) -> dict:
    """Non-blocking freshness diagnostic; never gates validation."""
    try:
        from services.pre_run_git import run_pull_check
        from services.project_context import resolve_project_context

        ctx = resolve_project_context(project_name=project)
        workspace_root = ctx.workspace_root if ctx is not None else None
        if not workspace_root:
            return {"ok": True, "skipped": True, "reason": "workspace_root_missing"}
        result = run_pull_check(
            workspace_root,
            enabled=False,
            required=False,
            fetch=False,
            timeout_seconds=5,
        )
        payload = result.to_dict()
        payload["skipped"] = False
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory validation pull-check skipped: %s", exc)
        return {"ok": True, "skipped": True, "reason": str(exc)}


def _check_schema(run_id: int, rows: list[memory_store.StackyMemoryObservation]) -> list[StackyMemoryFinding]:
    findings: list[StackyMemoryFinding] = []
    for row in rows:
        problems: list[str] = []
        if not (row.memory_id or "").strip():
            problems.append("memory_id missing")
        if not (row.project or "").strip():
            problems.append("project missing")
        if not (row.type or "").strip():
            problems.append("type missing")
        if not (row.title or "").strip():
            problems.append("title missing")
        if not (row.content or "").strip():
            problems.append("content missing")
        if row.status not in memory_store.ALL_STATUSES:
            problems.append(f"invalid status: {row.status}")
        if row.scope not in VALID_SCOPES:
            problems.append(f"invalid scope: {row.scope}")
        if row.tags_json:
            try:
                tags = json.loads(row.tags_json)
            except (json.JSONDecodeError, ValueError):
                problems.append("tags_json is not valid JSON")
            else:
                if not isinstance(tags, list):
                    problems.append("tags_json must be a JSON array")
        if problems:
            findings.append(
                _finding(
                    run_id=run_id,
                    row=row,
                    check_name="schema",
                    severity="error",
                    title="Memory schema is invalid",
                    detail="; ".join(problems),
                    evidence={"problems": problems},
                )
            )
    return findings


def _check_checksum(run_id: int, rows: list[memory_store.StackyMemoryObservation]) -> list[StackyMemoryFinding]:
    findings: list[StackyMemoryFinding] = []
    for row in rows:
        expected = memory_store._normalized_hash(row.title or "", row.content or "")
        if row.normalized_hash != expected:
            findings.append(
                _finding(
                    run_id=run_id,
                    row=row,
                    check_name="checksum",
                    severity="warning",
                    title="Memory checksum mismatch",
                    detail="normalized_hash does not match title/content",
                    evidence={"stored": row.normalized_hash, "expected": expected},
                )
            )
    return findings


def _check_secrets(run_id: int, rows: list[memory_store.StackyMemoryObservation]) -> list[StackyMemoryFinding]:
    findings: list[StackyMemoryFinding] = []
    now = datetime.utcnow()
    for row in rows:
        match = find_secret(f"{row.title or ''}\n{row.content or ''}")
        if match is None:
            continue
        row.status = "quarantined"
        row.updated_at = now
        findings.append(
            _finding(
                run_id=run_id,
                row=row,
                check_name="secret",
                severity="critical",
                title="Secret detected in memory",
                detail="memory was quarantined before export/injection",
                evidence={"secret": match.to_dict(), "action": "quarantined"},
            )
        )
    return findings


def _check_duplicate_exact(
    run_id: int,
    rows: list[memory_store.StackyMemoryObservation],
) -> list[StackyMemoryFinding]:
    groups: dict[tuple[str, str, str, str], list[memory_store.StackyMemoryObservation]] = defaultdict(list)
    for row in rows:
        if row.status in {"deleted", "quarantined"}:
            continue
        digest = row.normalized_hash or memory_store._normalized_hash(row.title or "", row.content or "")
        groups[(row.project or "", row.scope or "", row.type or "", digest)].append(row)

    findings: list[StackyMemoryFinding] = []
    for (_project, _scope, _type, digest), group in groups.items():
        if len(group) < 2:
            continue
        memory_ids = [row.memory_id for row in group]
        for row in group:
            row.duplicate_count = max(row.duplicate_count or 1, len(group))
        findings.append(
            _finding(
                run_id=run_id,
                row=group[0],
                check_name="duplicate_exact",
                severity="warning",
                title="Exact duplicate memories",
                detail=f"{len(group)} memories share the same normalized hash",
                evidence={"memory_ids": memory_ids, "normalized_hash": digest},
            )
        )
    return findings


def _check_duplicate_semantic(
    run_id: int,
    rows: list[memory_store.StackyMemoryObservation],
) -> list[StackyMemoryFinding]:
    threshold = float(os.getenv("STACKY_MEMORY_SEMANTIC_DUP_THRESHOLD", "0.82"))
    candidates = [
        row
        for row in rows
        if row.status in {"active", "draft", "needs_review"}
        and row.scope in {"project", "team", "global"}
    ][:500]
    vectors: dict[str, Counter] = {}
    for row in candidates:
        tokens = memory_store._tokenize(f"{row.title or ''}\n{row.content or ''}")
        if tokens:
            vectors[row.memory_id] = Counter(tokens)

    findings: list[StackyMemoryFinding] = []
    seen_pairs: set[frozenset[str]] = set()
    for left, right in combinations(candidates, 2):
        if left.normalized_hash == right.normalized_hash:
            continue
        if left.type != right.type or left.scope != right.scope:
            continue
        pair = frozenset((left.memory_id, right.memory_id))
        if pair in seen_pairs:
            continue
        score = _cosine(vectors.get(left.memory_id), vectors.get(right.memory_id))
        if score < threshold:
            continue
        seen_pairs.add(pair)
        findings.append(
            _finding(
                run_id=run_id,
                row=left,
                check_name="duplicate_semantic",
                severity="warning",
                title="Semantic duplicate memories",
                detail=f"Two memories are semantically similar (score={score:.2f})",
                evidence={
                    "memory_ids": [left.memory_id, right.memory_id],
                    "score": round(score, 4),
                    "threshold": threshold,
                },
            )
        )
    return findings


def _check_conflict_graph(
    run_id: int,
    project: str | None,
    rows: list[memory_store.StackyMemoryObservation],
) -> list[StackyMemoryFinding]:
    if not project:
        return []
    active_ids = {row.memory_id for row in rows if row.status == "active"}
    if not active_ids:
        return []
    with session_scope() as session:
        rels = (
            session.query(memory_store.StackyMemoryRelation)
            .filter(
                memory_store.StackyMemoryRelation.project == project,
                memory_store.StackyMemoryRelation.relation.in_(("conflicts_with", "not_conflict")),
                memory_store.StackyMemoryRelation.status.notin_(("rejected", "resolved")),
            )
            .all()
        )
    allowed_pairs = {
        frozenset((r.source_memory_id, r.target_memory_id))
        for r in rels
        if r.relation == "not_conflict"
    }
    findings: list[StackyMemoryFinding] = []
    row_by_id = {row.memory_id: row for row in rows}
    for rel in rels:
        if rel.relation != "conflicts_with":
            continue
        pair = frozenset((rel.source_memory_id, rel.target_memory_id))
        if pair in allowed_pairs:
            continue
        if rel.source_memory_id not in active_ids or rel.target_memory_id not in active_ids:
            continue
        row = row_by_id.get(rel.source_memory_id)
        if row is None:
            continue
        findings.append(
            _finding(
                run_id=run_id,
                row=row,
                check_name="conflict_graph",
                severity="error",
                title="Active memories conflict",
                detail="Two active memories are marked as conflicting and are suppressed from injection",
                evidence={
                    "memory_ids": [rel.source_memory_id, rel.target_memory_id],
                    "relation_id": rel.relation_id,
                    "reason": rel.reason,
                },
            )
        )
    return findings


def _check_llm_judge(
    run_id: int,
    rows: list[memory_store.StackyMemoryObservation],
) -> list[StackyMemoryFinding]:
    candidates = [
        row
        for row in rows
        if row.status in {"active", "draft", "needs_review"}
        and row.scope in {"project", "team", "global"}
    ][: int(os.getenv("STACKY_MEMORY_LLM_JUDGE_LIMIT", "25"))]
    findings: list[StackyMemoryFinding] = []
    for row in candidates:
        verdict = _judge_memory(row)
        if not verdict:
            continue
        action = str(verdict.get("verdict") or verdict.get("action") or "").lower()
        if action in {"approve", "approved", "active", "ok"}:
            continue
        if action not in {"needs_review", "quarantine", "reject", "rejected"}:
            continue
        severity = "critical" if action == "quarantine" else "warning"
        reason = str(verdict.get("reason") or "LLM judge requested human review")
        findings.append(
            _finding(
                run_id=run_id,
                row=row,
                check_name="llm_judge",
                severity=severity,
                title="LLM judge flagged memory",
                detail=reason,
                evidence={
                    "memory_ids": [row.memory_id],
                    "verdict": action,
                    "confidence": verdict.get("confidence"),
                    "model": verdict.get("model_used"),
                },
            )
        )
    return findings


def _judge_memory(row: memory_store.StackyMemoryObservation) -> dict | None:
    from services import pii_masker
    from services.pm import pm_llm_client

    model = os.getenv("STACKY_MEMORY_JUDGE_MODEL", "mock-1.0")
    text = (
        f"project={row.project}\n"
        f"type={row.type}\n"
        f"scope={row.scope}\n"
        f"status={row.status}\n"
        f"title={row.title}\n"
        f"content={row.content}"
    )
    masked, _ = pii_masker.mask_text(text)
    spec = pm_llm_client.LLMCallSpec(
        project=row.project or "memory",
        agent_kind="memory_judge",
        prompt_type="stacky_memory_judge_v1",
        model=model,
        system=(
            "You are a conservative memory curator. Return strict JSON with "
            "verdict one of approve, needs_review, quarantine, reject; reason; "
            "confidence 0..1. Quarantine secrets, credentials, unsafe policy, "
            "or unverifiable commands. Do not enforce permissions."
        ),
        user=masked,
        max_output_tokens=300,
        temperature=0.0,
        expect_json=True,
    )
    result = pm_llm_client.call_llm(spec)
    if not result.success or not isinstance(result.parsed_json, dict):
        return None
    verdict = dict(result.parsed_json)
    verdict.setdefault("model_used", result.model)
    return verdict


def _cosine(left: Counter | None, right: Counter | None) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    if not common:
        return 0.0
    dot = sum(left[t] * right[t] for t in common)
    left_norm = math.sqrt(sum(v * v for v in left.values()))
    right_norm = math.sqrt(sum(v * v for v in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _finding(
    *,
    run_id: int,
    row: memory_store.StackyMemoryObservation,
    check_name: str,
    severity: str,
    title: str,
    detail: str,
    evidence: dict,
) -> StackyMemoryFinding:
    now = datetime.utcnow()
    finding = StackyMemoryFinding(
        validation_run_id=run_id,
        project=row.project or "(unknown)",
        check_name=check_name,
        severity=severity,
        status="open",
        memory_id=row.memory_id,
        title=title,
        detail=detail,
        created_at=now,
        updated_at=now,
    )
    finding.evidence = evidence
    return finding


def _normalize_checks(checks: list[str] | None) -> list[str]:
    advanced_on = _advanced_enabled()
    if not checks:
        selected = list(_CHEAP_CHECKS)
        if advanced_on:
            selected += list(_ADVANCED_CHECKS)
        return selected
    selected = [str(c).strip() for c in checks if str(c).strip()]
    unknown = [c for c in selected if c not in CHECKS]
    if unknown:
        raise ValueError(f"unsupported memory validation checks: {unknown}")
    if not advanced_on:
        blocked = [c for c in selected if c in _ADVANCED_CHECKS]
        if blocked:
            raise ValueError(
                "advanced memory validation checks "
                f"{blocked} require STACKY_MEMORY_VALIDATOR_ADVANCED=true"
            )
    return selected


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
