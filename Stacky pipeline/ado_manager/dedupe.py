"""
dedupe — Cache de dedupe para publicaciones ADO.

Usa SHA256(work_item_id || ":" || body) como clave. Persiste en un archivo
JSON-lines en state/ado_dedupe_cache.jsonl para sobrevivir reinicios.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Optional


class DedupeCache:
    """
    Cache de hashes para detectar comentarios ADO duplicados.

    Parámetros
    ----------
    cache_path:
        Ruta al archivo de persistencia JSON-lines.
        Si es None, opera en memoria (útil para tests).
    """

    def __init__(self, cache_path: Optional[str] = None) -> None:
        self._hashes: set[str] = set()
        self._cache_path = cache_path
        if cache_path:
            self._load(cache_path)

    # ── Lectura ───────────────────────────────────────────────────────────────

    def _load(self, path: str) -> None:
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    self._hashes.add(record["hash"])
                except (json.JSONDecodeError, KeyError):
                    pass

    # ── API pública ───────────────────────────────────────────────────────────

    @staticmethod
    def compute_key(work_item_id: int, body: str) -> str:
        """Calcula SHA256(work_item_id:body)."""
        raw = f"{work_item_id}:{body}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def is_duplicate(self, hash_key: str) -> bool:
        """Devuelve True si el hash ya fue registrado."""
        return hash_key in self._hashes

    def register(self, hash_key: str) -> None:
        """Registra un hash como publicado."""
        self._hashes.add(hash_key)
        if self._cache_path:
            self._persist(hash_key)

    def _persist(self, hash_key: str) -> None:
        os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
        record = {
            "hash": hash_key,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._cache_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def clear(self) -> None:
        """Limpia el cache en memoria (no toca el archivo de persistencia)."""
        self._hashes.clear()

    def __len__(self) -> int:
        return len(self._hashes)
