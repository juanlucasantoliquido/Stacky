"""
deploy_history.py — Historial de paquetes de despliegue por ticket.

Mantiene un DEPLOY_LOG.json en la carpeta del ticket con cada deploy generado.
Permite al dashboard mostrar "N deploys generados" y links a ZIPs anteriores.
"""

import json
import os
from datetime import datetime
from pathlib import Path


class DeployHistory:
    """Gestiona DEPLOY_LOG.json dentro de la carpeta de un ticket."""

    LOG_FILE = "DEPLOY_LOG.json"

    def __init__(self, ticket_folder):
        self.folder   = Path(ticket_folder)
        self.log_path = self.folder / self.LOG_FILE

    def record(self, zip_name: str, files: list, excluded: list,
               warnings: list, rollback_zip: str = None) -> dict:
        """Agrega una entrada al historial."""
        history = self.load()
        entry = {
            "ts":           datetime.now().isoformat(),
            "zip_name":     zip_name,
            "rollback_zip": rollback_zip,
            "file_count":   len(files),
            "excluded":     len(excluded),
            "warnings":     len(warnings),
            "files_summary": [
                {"type": f.get("type"), "arc": f.get("arc")}
                for f in files
            ],
        }
        history.setdefault("deploys", []).append(entry)
        history["last_deploy_at"] = entry["ts"]
        history["total_deploys"]  = len(history["deploys"])
        self._save(history)
        return entry

    def load(self) -> dict:
        if self.log_path.exists():
            try:
                return json.loads(self.log_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"deploys": [], "total_deploys": 0}

    def list_zips(self) -> list:
        """Retorna lista de ZIPs existentes (deploy + rollback), del más reciente al más viejo."""
        history = self.load()
        result  = []
        for entry in reversed(history.get("deploys", [])):
            for key in ("zip_name", "rollback_zip"):
                name = entry.get(key)
                if not name:
                    continue
                path = self.folder / name
                result.append({
                    "name":     name,
                    "type":     "rollback" if key == "rollback_zip" else "deploy",
                    "ts":       entry["ts"],
                    "exists":   path.exists(),
                    "size_kb":  round(path.stat().st_size / 1024, 1) if path.exists() else None,
                })
        return result

    def _save(self, data: dict):
        self.log_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
