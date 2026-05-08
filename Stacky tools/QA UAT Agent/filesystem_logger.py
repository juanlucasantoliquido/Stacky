"""
filesystem_logger.py — Logger de operaciones de sistema de archivos para QA UAT Agent.

Registra:
  - Cada archivo leído (path, tamaño, éxito/fallo)
  - Cada archivo escrito (path, tamaño, sha256)
  - Cada parse error (JSON/YAML malformado)
  - Cada archivo no encontrado

Integra con ForensicEventLogger para emitir:
  - file_read | file_written | file_missing | file_parse_failed

Uso:
    from filesystem_logger import FilesystemLogger

    fs = FilesystemLogger(run_dir=run_dir, forensic_log=log, stage="reader")

    # Leer JSON con logging forense
    data = fs.read_json("evidence/70/ticket.json")
    if data is None:
        # El logger ya emitió file_missing o file_parse_failed

    # Escribir con logging + artifact registration
    art = fs.write_json(
        data={"key": "value"},
        path=Path("evidence/70/output.json"),
        artifact_type="output",
        artifact_registry=registry,  # opcional
    )
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from artifact_registry import ArtifactRegistry
from redactor import scan_for_unredacted_secrets

import logging

_py_logger = logging.getLogger("stacky.qa_uat.filesystem_logger")


class FilesystemLogger:
    """
    Wrapper de operaciones de archivos con logging forense automático.
    """

    def __init__(
        self,
        run_dir: Path,
        stage: str,
        forensic_log: Any = None,
        artifact_registry: Optional[ArtifactRegistry] = None,
        run_id: str = "",
        ticket_id: Any = "",
    ) -> None:
        self.run_dir = run_dir
        self.stage = stage
        self.forensic_log = forensic_log
        self.artifact_registry = artifact_registry
        self.run_id = run_id
        self.ticket_id = ticket_id

    def _emit(self, category: str, path: str, message: str, level: str = "info",
              extra: Optional[dict] = None) -> Optional[str]:
        if self.forensic_log is None:
            return None
        try:
            return self.forensic_log.emit(
                source="filesystem",
                event_type=f"file.{category.replace('file_', '')}",
                category=category,
                stage=self.stage,
                action=category,
                status="completed" if "read" in category or "written" in category else "failed",
                level=level,
                message=message,
                payload={"path": path, **(extra or {})},
            )
        except Exception:
            return None

    # ── Lectura ───────────────────────────────────────────────────────────────

    def read_text(self, path: Path, encoding: str = "utf-8") -> Optional[str]:
        """Leer archivo de texto con logging. Devuelve None si falla."""
        p = Path(path)
        if not p.exists():
            self._emit("file_missing", str(path), f"Archivo no encontrado: {path}", level="warning")
            return None
        try:
            content = p.read_text(encoding=encoding, errors="replace")
            size = p.stat().st_size
            self._emit("file_read", str(path), f"Archivo leído: {path}", extra={"size_bytes": size})
            return content
        except Exception as exc:
            self._emit("file_parse_failed", str(path), f"Error leyendo {path}: {exc}",
                       level="error", extra={"error": str(exc)})
            return None

    def read_json(self, path: Path, encoding: str = "utf-8") -> Optional[Any]:
        """Leer y parsear JSON con logging. Devuelve None si falla."""
        p = Path(path)
        if not p.exists():
            self._emit("file_missing", str(path), f"JSON no encontrado: {path}", level="warning")
            return None
        try:
            content = p.read_text(encoding=encoding, errors="replace")
            size = p.stat().st_size
            data = json.loads(content)
            self._emit("file_read", str(path), f"JSON leído: {path}", extra={"size_bytes": size})
            return data
        except json.JSONDecodeError as exc:
            self._emit("file_parse_failed", str(path),
                       f"JSON malformado en {path}: {exc}",
                       level="error", extra={"error": str(exc), "parse_type": "json"})
            return None
        except Exception as exc:
            self._emit("file_parse_failed", str(path),
                       f"Error leyendo JSON {path}: {exc}",
                       level="error", extra={"error": str(exc)})
            return None

    def read_bytes(self, path: Path) -> Optional[bytes]:
        """Leer archivo binario con logging."""
        p = Path(path)
        if not p.exists():
            self._emit("file_missing", str(path), f"Archivo binario no encontrado: {path}", level="warning")
            return None
        try:
            content = p.read_bytes()
            self._emit("file_read", str(path), f"Binario leído: {path}",
                       extra={"size_bytes": len(content)})
            return content
        except Exception as exc:
            self._emit("file_parse_failed", str(path),
                       f"Error leyendo binario {path}: {exc}",
                       level="error", extra={"error": str(exc)})
            return None

    # ── Escritura ─────────────────────────────────────────────────────────────

    def write_text(
        self,
        content: str,
        path: Path,
        *,
        encoding: str = "utf-8",
        artifact_type: Optional[str] = None,
        created_by_event_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Escribir texto en un archivo con logging forense.

        Devuelve el registro del artifact si se registra, o un dict básico.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(content, encoding=encoding)
            size = p.stat().st_size

            art = None
            if artifact_type and self.artifact_registry:
                art = self.artifact_registry.register_file(
                    path=p,
                    artifact_type=artifact_type,
                    created_by_event_id=created_by_event_id,
                    scenario_id=scenario_id,
                    ticket_id=self.ticket_id,
                )

            eid = self._emit(
                "file_written",
                str(path),
                f"Texto escrito: {path}",
                extra={
                    "size_bytes": size,
                    "artifact_type": artifact_type,
                    "artifact_id": art.get("artifact_id") if art else None,
                },
            )

            return art or {"path": str(path), "size_bytes": size, "event_id": eid}

        except Exception as exc:
            self._emit("file_parse_failed", str(path),
                       f"Error escribiendo {path}: {exc}",
                       level="error", extra={"error": str(exc)})
            return None

    def write_json(
        self,
        data: Any,
        path: Path,
        *,
        encoding: str = "utf-8",
        indent: int = 2,
        artifact_type: Optional[str] = None,
        created_by_event_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        check_secrets: bool = False,
    ) -> Optional[dict]:
        """
        Serializar y escribir JSON con logging forense.

        Si check_secrets=True, escanea el JSON resultante por secretos sin redactar
        (útil para artifacts críticos como ticket.json, dossier.json).
        """
        try:
            content = json.dumps(data, ensure_ascii=False, indent=indent)
        except Exception as exc:
            _py_logger.error("FilesystemLogger: error serializando JSON para %s: %s", path, exc)
            return None

        if check_secrets:
            found = scan_for_unredacted_secrets(content)
            if found:
                _py_logger.warning("FilesystemLogger: posibles secretos en %s: %s", path, found[:3])
                if self.forensic_log:
                    self.forensic_log.emit_warning(
                        self.stage,
                        f"Posibles secretos sin redactar en {path}",
                        {"path": str(path), "warnings": found[:5]},
                    )

        return self.write_text(
            content=content,
            path=path,
            encoding=encoding,
            artifact_type=artifact_type,
            created_by_event_id=created_by_event_id,
            scenario_id=scenario_id,
        )

    def write_bytes(
        self,
        data: bytes,
        path: Path,
        *,
        artifact_type: Optional[str] = None,
        created_by_event_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Escribir bytes con logging forense."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_bytes(data)
            size = len(data)

            art = None
            if artifact_type and self.artifact_registry:
                art = self.artifact_registry.register_file(
                    path=p,
                    artifact_type=artifact_type,
                    created_by_event_id=created_by_event_id,
                    scenario_id=scenario_id,
                    ticket_id=self.ticket_id,
                )

            self._emit(
                "file_written",
                str(path),
                f"Binario escrito: {path}",
                extra={
                    "size_bytes": size,
                    "artifact_type": artifact_type,
                },
            )
            return art or {"path": str(path), "size_bytes": size}

        except Exception as exc:
            self._emit("file_parse_failed", str(path),
                       f"Error escribiendo binario {path}: {exc}",
                       level="error", extra={"error": str(exc)})
            return None

    def ensure_dir(self, path: Path) -> bool:
        """Crear directorio si no existe, con logging."""
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as exc:
            _py_logger.warning("FilesystemLogger: no se pudo crear dir %s: %s", path, exc)
            return False

    def file_exists(self, path: Path, emit_if_missing: bool = True) -> bool:
        """Verificar existencia de archivo con logging opcional si falta."""
        if Path(path).exists():
            return True
        if emit_if_missing:
            self._emit("file_missing", str(path), f"Archivo esperado no existe: {path}", level="warning")
        return False
