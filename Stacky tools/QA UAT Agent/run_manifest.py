"""
run_manifest.py — Gestión del run_manifest.json y run_state.json por run.

Cada run de QA UAT debe tener:
  - run_manifest.json: metadata inmutable del run (quién, cuándo, qué)
  - run_state.json:    estado mutable actual (etapa actual, bloqueado, etc.)

Ambos archivos se crean al inicio del run y se actualizan durante su ejecución.

Estructura de run_manifest.json:
{
  "run_id": "uat-70-20260507-153012",
  "ticket_id": 70,
  "trace_id": "trace-uat-70-20260507-153012",
  "schema_version": "1.0",
  "started_at": "2026-05-07T15:30:12.123Z",
  "tool_version": "1.0.0",
  "mode": "dry-run",
  "headed": false,
  "operator": "system",
  "env_summary": { "AGENDA_WEB_USER": "Pablo", "AGENDA_WEB_BASE_URL": "..." }
}

Estructura de run_state.json:
{
  "run_id": "uat-70-20260507-153012",
  "status": "running",  // running | completed | failed | blocked
  "current_stage": "reader",
  "last_completed_stage": null,
  "last_event_id": "evt_000234",
  "resume_from": null,
  "blocked_reason": null,
  "waiting_for_human": false,
  "updated_at": "..."
}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from redactor import redact_env

_TOOL_VERSION = "1.0.0"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _safe_env_summary() -> dict:
    """
    Capturar variables de entorno relevantes para el run, con secretos redactados.
    Solo incluye las vars relacionadas con QA UAT (no toda la env).
    """
    relevant_keys = {
        "AGENDA_WEB_BASE_URL",
        "AGENDA_WEB_USER",
        "AGENDA_WEB_PASS",
        "RS_QA_DB_USER",
        "RS_QA_DB_PASS",
        "RS_QA_DB_DSN",
        "ADO_PAT",
        "QA_UAT_SKIP_SMOKE",
        "QA_UAT_REQUIRE_PLAYBOOK",
        "COMPUTERNAME",
        "USERNAME",
        "OS",
    }
    env_subset = {k: os.environ.get(k, "") for k in relevant_keys if k in os.environ}
    redacted, _ = redact_env(env_subset)
    return redacted


# ── RunManifest ────────────────────────────────────────────────────────────────

class RunManifest:
    """
    Crea y mantiene run_manifest.json y run_state.json para un run.

    Usage:
        manifest = RunManifest(run_id="uat-70-...", ticket_id=70, run_dir=Path(...))
        manifest.create(mode="dry-run", headed=False)
        manifest.update_state(status="running", current_stage="reader")
        manifest.update_state(status="completed", last_completed_stage="publisher")
    """

    def __init__(self, run_id: str, ticket_id: Any, run_dir: Path) -> None:
        self.run_id = run_id
        self.ticket_id = ticket_id
        self.run_dir = run_dir
        self.manifest_path = run_dir / "run_manifest.json"
        self.state_path = run_dir / "run_state.json"

    def create(
        self,
        *,
        mode: str = "dry-run",
        headed: bool = False,
        operator: str = "system",
        tool_version: str = _TOOL_VERSION,
        extra: Optional[dict] = None,
    ) -> dict:
        """
        Crear run_manifest.json y run_state.json iniciales.

        Idempotente: si el manifest ya existe, solo actualiza el state.
        Devuelve el manifest dict.
        """
        self.run_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "trace_id": f"trace-{self.run_id}",
            "schema_version": "1.0",
            "started_at": _utcnow(),
            "tool_version": tool_version,
            "mode": mode,
            "headed": headed,
            "operator": operator,
            "env_summary": _safe_env_summary(),
        }
        if extra:
            manifest.update(extra)

        if not self.manifest_path.exists():
            self.manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # Estado inicial
        state = {
            "run_id": self.run_id,
            "status": "running",
            "current_stage": None,
            "last_completed_stage": None,
            "last_event_id": None,
            "resume_from": None,
            "blocked_reason": None,
            "waiting_for_human": False,
            "updated_at": _utcnow(),
        }
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return manifest

    def update_state(self, **kwargs: Any) -> dict:
        """
        Actualizar run_state.json con los campos provistos.

        Solo actualiza los campos especificados. Preserva el resto.
        Thread-safe a nivel de archivo (write-then-rename no implementado
        en esta fase; suficiente para uso single-threaded del pipeline).
        """
        state = self._load_state()
        for k, v in kwargs.items():
            state[k] = v
        state["updated_at"] = _utcnow()
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return state

    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "run_id": self.run_id,
            "status": "running",
            "updated_at": _utcnow(),
        }

    def load_manifest(self) -> Optional[dict]:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def load_state(self) -> Optional[dict]:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def mark_completed(self, last_completed_stage: Optional[str] = None) -> dict:
        return self.update_state(
            status="completed",
            last_completed_stage=last_completed_stage,
            waiting_for_human=False,
            blocked_reason=None,
        )

    def mark_failed(self, reason: str, stage: Optional[str] = None) -> dict:
        return self.update_state(
            status="failed",
            blocked_reason=reason,
            current_stage=stage,
        )

    def mark_blocked(self, reason: str, stage: Optional[str] = None,
                     waiting_for_human: bool = False) -> dict:
        return self.update_state(
            status="blocked",
            blocked_reason=reason,
            current_stage=stage,
            resume_from=stage,
            waiting_for_human=waiting_for_human,
        )
