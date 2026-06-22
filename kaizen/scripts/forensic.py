#!/usr/bin/env python3
"""Logger forense de Kaizen — JSONL append-only, stdlib pura.

Cada evento se escribe como una línea JSON en:
  - el log de la sesión:  sessions/<id>/forensic.jsonl
  - el log global:        sessions/_forensic.jsonl   (agrega todas las sesiones)

Diseño forense:
  - Marca de tiempo UTC ISO + secuencia monotónica + elapsed_ms desde el inicio del run.
  - Nivel (INFO|WARN|ERROR), fase del ciclo y nombre de evento punteado.
  - 'data' arbitraria; los artefactos se referencian por sha256 para reproducibilidad/integridad.
Portabilidad: no importa el proyecto padre; rutas relativas a la raíz kaizen/.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOBAL_LOG = ROOT / "sessions" / "_forensic.jsonl"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


class Forensic:
    """Emisor de eventos forenses para un run de una sesión."""

    def __init__(self, session_id: str, session_dir: Path, run_kind: str = "run"):
        self.session_id = session_id
        self.session_dir = Path(session_dir)
        self.run_kind = run_kind
        self.session_log = self.session_dir / "forensic.jsonl"
        self._seq = 0
        self._t0 = time.perf_counter()
        self.run_id = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    def _now_iso(self) -> str:
        return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()

    def log(self, event: str, phase: str = "run", level: str = "INFO", **data) -> dict:
        self._seq += 1
        record = {
            "ts": self._now_iso(),
            "seq": self._seq,
            "run_id": self.run_id,
            "run_kind": self.run_kind,
            "session_id": self.session_id,
            "phase": phase,
            "event": event,
            "level": level,
            "elapsed_ms": round((time.perf_counter() - self._t0) * 1000, 2),
            "data": data,
        }
        line = json.dumps(record, ensure_ascii=False)
        GLOBAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with self.session_log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        with GLOBAL_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return record

    # Atajos por nivel
    def info(self, event, phase="run", **data):
        return self.log(event, phase, "INFO", **data)

    def warn(self, event, phase="run", **data):
        return self.log(event, phase, "WARN", **data)

    def error(self, event, phase="run", **data):
        return self.log(event, phase, "ERROR", **data)
