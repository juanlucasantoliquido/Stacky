"""
artifact_registry.py — Registro de artifacts con sha256 para QA UAT Agent.

Cada artifact generado durante un run (screenshot, trace, video, log,
JSON, HTML, etc.) debe registrarse con:
  - artifact_id único
  - sha256 del contenido
  - tamaño en bytes
  - tipo de artifact
  - path relativo al run_dir
  - event_id que lo creó

Los artifacts se registran en:
  - EventStore (tabla artifacts en SQLite)
  - <run_dir>/artifacts/_registry.json (resumen portable)

Regla: ningún artifact puede ser referenciado en un evento sin estar registrado.
       Todo artifact debe tener sha256.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def compute_sha256(path: Path) -> Optional[str]:
    """Calcular sha256 de un archivo. Devuelve None si el archivo no existe."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def compute_sha256_bytes(data: bytes) -> str:
    """Calcular sha256 de bytes en memoria."""
    return hashlib.sha256(data).hexdigest()


def new_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


# ── ArtifactRegistry ──────────────────────────────────────────────────────────

class ArtifactRegistry:
    """
    Registra y consulta artifacts de un run.

    Usage:
        registry = ArtifactRegistry(run_id="uat-70-...", run_dir=Path("evidence/70/uat-70-..."))
        art = registry.register_file(
            path=Path("playwright/screenshots/P01.png"),
            artifact_type="screenshot",
            created_by_event_id="evt_123",
            scenario_id="P01",
        )
        print(art["artifact_id"], art["sha256"])
    """

    def __init__(self, run_id: str, run_dir: Path, store: Any = None) -> None:
        """
        store: EventStore opcional. Si se provee, los artifacts se persisten en SQLite.
        """
        self.run_id = run_id
        self.run_dir = run_dir
        self._store = store
        self._registry: list[dict] = []
        self._registry_path = run_dir / "artifacts" / "_registry.json"
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _load_existing(self) -> None:
        if self._registry_path.exists():
            try:
                self._registry = json.loads(self._registry_path.read_text(encoding="utf-8"))
            except Exception:
                self._registry = []

    def _save(self) -> None:
        self._registry_path.write_text(
            json.dumps(self._registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Registro desde archivo ─────────────────────────────────────────────────

    def register_file(
        self,
        path: Path,
        artifact_type: str,
        *,
        artifact_id: Optional[str] = None,
        created_by_event_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        ticket_id: Any = None,
        extra: Optional[dict] = None,
    ) -> dict:
        """
        Registrar un archivo existente como artifact.

        Calcula sha256 y tamaño automáticamente.
        Devuelve el registro del artifact.
        """
        # Path relativo al run_dir para portabilidad
        try:
            rel_path = str(path.relative_to(self.run_dir))
        except ValueError:
            rel_path = str(path)

        sha = compute_sha256(path)
        size = path.stat().st_size if path.exists() else None

        return self._register(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            path=rel_path,
            sha256=sha,
            size_bytes=size,
            created_by_event_id=created_by_event_id,
            scenario_id=scenario_id,
            ticket_id=ticket_id,
            extra=extra,
        )

    def register_bytes(
        self,
        data: bytes,
        dest_path: Path,
        artifact_type: str,
        *,
        artifact_id: Optional[str] = None,
        created_by_event_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        ticket_id: Any = None,
        extra: Optional[dict] = None,
    ) -> dict:
        """
        Escribir bytes en dest_path y registrarlos como artifact.
        """
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(data)

        sha = compute_sha256_bytes(data)
        size = len(data)

        try:
            rel_path = str(dest_path.relative_to(self.run_dir))
        except ValueError:
            rel_path = str(dest_path)

        return self._register(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            path=rel_path,
            sha256=sha,
            size_bytes=size,
            created_by_event_id=created_by_event_id,
            scenario_id=scenario_id,
            ticket_id=ticket_id,
            extra=extra,
        )

    def register_json(
        self,
        data: Any,
        dest_path: Path,
        artifact_type: str,
        *,
        artifact_id: Optional[str] = None,
        created_by_event_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        ticket_id: Any = None,
        extra: Optional[dict] = None,
    ) -> dict:
        """
        Serializar data como JSON, escribir en dest_path y registrar como artifact.
        """
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        return self.register_bytes(
            data=content,
            dest_path=dest_path,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            created_by_event_id=created_by_event_id,
            scenario_id=scenario_id,
            ticket_id=ticket_id,
            extra=extra,
        )

    def _register(
        self,
        artifact_type: str,
        path: str,
        sha256: Optional[str],
        *,
        artifact_id: Optional[str] = None,
        size_bytes: Optional[int] = None,
        created_by_event_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        ticket_id: Any = None,
        extra: Optional[dict] = None,
    ) -> dict:
        aid = artifact_id or new_artifact_id()
        ts = _utcnow()
        record = {
            "artifact_id": aid,
            "run_id": self.run_id,
            "ticket_id": ticket_id,
            "type": artifact_type,
            "artifact_type": artifact_type,  # alias
            "path": path,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "created_by_event_id": created_by_event_id,
            "scenario_id": scenario_id,
            "ts": ts,
            "extra": extra or {},
        }
        self._registry.append(record)
        self._save()

        if self._store is not None:
            try:
                self._store.register_artifact(record)
            except Exception:
                pass

        return record

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_by_id(self, artifact_id: str) -> Optional[dict]:
        return next((a for a in self._registry if a["artifact_id"] == artifact_id), None)

    def get_by_type(self, artifact_type: str) -> list[dict]:
        return [a for a in self._registry if a.get("type") == artifact_type]

    def get_all(self) -> list[dict]:
        return list(self._registry)

    def validate_all_exist(self) -> list[str]:
        """
        Verificar que todos los artifacts registrados existen físicamente.

        Devuelve lista de artifact_ids con archivos faltantes.
        """
        missing = []
        for art in self._registry:
            rel = art.get("path", "")
            full = self.run_dir / rel
            if not full.exists():
                missing.append(art["artifact_id"])
        return missing

    def validate_all_have_sha256(self) -> list[str]:
        """Devuelve artifact_ids sin sha256."""
        return [a["artifact_id"] for a in self._registry if not a.get("sha256")]

    def summary(self) -> dict:
        return {
            "total": len(self._registry),
            "by_type": {},  # se puede popular si se necesita
            "missing_files": len(self.validate_all_exist()),
            "missing_sha256": len(self.validate_all_have_sha256()),
        }
