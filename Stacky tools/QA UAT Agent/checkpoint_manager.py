"""
checkpoint_manager.py — Gestión de checkpoints por stage para QA UAT Agent.

Cada stage del pipeline puede escribir un checkpoint cuando termina.
Los checkpoints permiten reanudar un run bloqueado desde el último stage
completado, sin repetir acciones ya ejecutadas.

Estructura de archivos:
  evidence/<ticket_id>/<run_id>/checkpoints/
  ├── 00_environment_preflight.completed.json
  ├── 01_load_ticket.completed.json
  ├── 02_resolve_scenario.completed.json
  └── 03_resolve_playbook.blocked.json

Cada checkpoint es un JSON con:
{
  "run_id": "...",
  "stage": "resolve_playbook",
  "status": "completed",  // completed | failed | blocked
  "seq": 3,
  "event_id": "evt_000234",
  "ts": "...",
  "payload": { ... }   // resumen de lo que produjo el stage
}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class CheckpointManager:
    """
    Gestiona checkpoints de stages para un run específico.

    Los checkpoints se almacenan como archivos JSON individuales en:
      <run_dir>/checkpoints/<seq>_<stage>.<status>.json

    Adicionalmente escribe al EventStore si se provee.
    """

    def __init__(self, run_id: str, run_dir: Path) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.checkpoints_dir = run_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._completed_stages: set[str] = set()
        self._load_existing()

    def _load_existing(self) -> None:
        """Cargar checkpoints existentes del directorio (para reanudación)."""
        for f in sorted(self.checkpoints_dir.glob("*.completed.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                stage = data.get("stage", "")
                if stage:
                    self._completed_stages.add(stage)
                seq = data.get("seq", 0)
                if seq > self._seq:
                    self._seq = seq
            except Exception:
                pass

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # ── Escritura de checkpoints ───────────────────────────────────────────────

    def write(
        self,
        stage: str,
        status: str,
        *,
        event_id: Optional[str] = None,
        payload: Optional[dict] = None,
        store: Any = None,  # EventStore, opcional
    ) -> Path:
        """
        Escribir un checkpoint para un stage.

        status: 'completed' | 'failed' | 'blocked'
        Devuelve el path del archivo creado.
        """
        seq = self._next_seq()
        ts = _utcnow()

        data = {
            "run_id": self.run_id,
            "stage": stage,
            "status": status,
            "seq": seq,
            "event_id": event_id,
            "ts": ts,
            "payload": payload or {},
        }

        filename = f"{seq:02d}_{stage}.{status}.json"
        fpath = self.checkpoints_dir / filename
        fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if status == "completed":
            self._completed_stages.add(stage)

        # Persistir en EventStore si disponible
        if store is not None:
            try:
                store.upsert_checkpoint(
                    run_id=self.run_id,
                    stage=stage,
                    status=status,
                    event_id=event_id,
                    payload=payload,
                )
            except Exception:
                pass

        return fpath

    def mark_completed(self, stage: str, event_id: Optional[str] = None,
                       payload: Optional[dict] = None, store: Any = None) -> Path:
        return self.write(stage, "completed", event_id=event_id, payload=payload, store=store)

    def mark_failed(self, stage: str, event_id: Optional[str] = None,
                    payload: Optional[dict] = None, store: Any = None) -> Path:
        return self.write(stage, "failed", event_id=event_id, payload=payload, store=store)

    def mark_blocked(self, stage: str, event_id: Optional[str] = None,
                     payload: Optional[dict] = None, store: Any = None) -> Path:
        return self.write(stage, "blocked", event_id=event_id, payload=payload, store=store)

    # ── Consultas ─────────────────────────────────────────────────────────────

    def is_completed(self, stage: str) -> bool:
        """Verificar si un stage ya tiene checkpoint 'completed'."""
        return stage in self._completed_stages

    def last_completed_stage(self) -> Optional[str]:
        """Devolver el último stage con checkpoint 'completed'."""
        # Buscar en archivos por número de seq más alto
        last_seq = -1
        last_stage: Optional[str] = None
        for f in self.checkpoints_dir.glob("*.completed.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                s = data.get("seq", 0)
                if s > last_seq:
                    last_seq = s
                    last_stage = data.get("stage")
            except Exception:
                pass
        return last_stage

    def get_all(self) -> list[dict]:
        """Devolver lista de todos los checkpoints, ordenados por seq."""
        checkpoints = []
        for f in sorted(self.checkpoints_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                checkpoints.append(data)
            except Exception:
                pass
        return sorted(checkpoints, key=lambda x: x.get("seq", 0))

    def has_any(self) -> bool:
        """Verificar si existe al menos un checkpoint (para detección de run reanudable)."""
        return any(self.checkpoints_dir.glob("*.json"))

    def summary(self) -> dict:
        """Resumen de checkpoints del run."""
        all_cp = self.get_all()
        return {
            "total": len(all_cp),
            "completed": len([c for c in all_cp if c.get("status") == "completed"]),
            "failed": len([c for c in all_cp if c.get("status") == "failed"]),
            "blocked": len([c for c in all_cp if c.get("status") == "blocked"]),
            "stages": [c.get("stage") for c in all_cp],
            "last_completed": self.last_completed_stage(),
        }
