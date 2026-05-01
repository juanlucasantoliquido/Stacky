"""self_improving_engine.py — X-01: Self-Improving Prompt Engine.

Registra tickets que pasaron QA con APROBADO al primer intento como
"golden examples" y los inyecta en futuros prompts para acumular aprendizaje.
"""

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.self_improving")

_STAGE_OUTCOME_FILES = {
    "pm":     "ARQUITECTURA_SOLUCION.md",
    "dev":    "DEV_COMPLETADO.md",
    "tester": "TESTER_COMPLETADO.md",
}

_MAX_EXAMPLES_PER_STAGE = 500


@dataclass
class GoldenExample:
    signature:        str
    stage:            str
    prompt_snapshot:  str
    outcome_snippet:  str
    ticket_type:      str
    date:             str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "GoldenExample":
        return GoldenExample(
            signature=d.get("signature", ""),
            stage=d.get("stage", ""),
            prompt_snapshot=d.get("prompt_snapshot", ""),
            outcome_snippet=d.get("outcome_snippet", ""),
            ticket_type=d.get("ticket_type", "general"),
            date=d.get("date", ""),
        )


class GoldenExampleStore:
    """JSON-backed store para golden examples. Thread-safe."""

    def __init__(self, path: str | None = None):
        base = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base, "data")
        os.makedirs(data_dir, exist_ok=True)
        self._path  = path or os.path.join(data_dir, "golden_examples.json")
        self._lock  = threading.RLock()
        self._data  = self._load()

    def _load(self) -> dict:
        if not os.path.isfile(self._path):
            try:
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump({"examples": []}, f)
            except Exception as e:
                logger.warning("[GOLDEN] No se pudo crear store: %s", e)
            return {"examples": []}
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            if "examples" not in data:
                data["examples"] = []
            return data
        except Exception as e:
            logger.warning("[GOLDEN] Error cargando store: %s", e)
            return {"examples": []}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("[GOLDEN] Error guardando store: %s", e)

    def save(self, example: GoldenExample) -> None:
        with self._lock:
            self._data.setdefault("examples", []).append(example.to_dict())
            # Evict oldest per-stage si excede el límite
            examples = self._data["examples"]
            by_stage: dict[str, list[int]] = {}
            for idx, ex in enumerate(examples):
                by_stage.setdefault(ex.get("stage", ""), []).append(idx)
            if len(by_stage.get(example.stage, [])) > _MAX_EXAMPLES_PER_STAGE:
                # Orden de inserción = orden cronológico; remover los más viejos
                drop_n = len(by_stage[example.stage]) - _MAX_EXAMPLES_PER_STAGE
                to_drop = set(by_stage[example.stage][:drop_n])
                self._data["examples"] = [
                    e for i, e in enumerate(examples) if i not in to_drop
                ]
            self._save()

    def find_similar(self, signature: str, stage: str,
                     top_k: int = 3) -> list[GoldenExample]:
        with self._lock:
            candidates = [
                GoldenExample.from_dict(e)
                for e in self._data.get("examples", [])
                if e.get("stage") == stage
            ]
        if not candidates:
            return []

        def _shared_prefix(a: str, b: str) -> int:
            n = min(len(a), len(b))
            i = 0
            while i < n and a[i] == b[i]:
                i += 1
            return i

        scored: list[tuple[int, GoldenExample]] = []
        for ex in candidates:
            score = _shared_prefix(signature, ex.signature)
            scored.append((score, ex))

        # Ordenar por prefijo compartido desc; si empata, los más recientes primero
        scored.sort(key=lambda t: (-t[0], t[1].date), reverse=False)
        # Ajuste: ordenar por shared prefix desc, luego date desc
        scored.sort(key=lambda t: (t[0], t[1].date), reverse=True)
        return [ex for _, ex in scored[:top_k]]


class SelfImprovingEngine:
    """Motor de auto-mejora: graba golden examples y los recupera por similitud."""

    def __init__(self, store: GoldenExampleStore | None = None):
        self.store = store or GoldenExampleStore()

    def record_success(self, ticket_folder: str, stage: str,
                       prompt_used: str) -> None:
        try:
            signature = self._compute_ticket_signature(ticket_folder)
            example = GoldenExample(
                signature=signature,
                stage=stage,
                prompt_snapshot=(prompt_used or "")[:2000],
                outcome_snippet=self._extract_outcome(ticket_folder, stage),
                ticket_type=self._classify(ticket_folder),
                date=datetime.now().isoformat(),
            )
            self.store.save(example)
            logger.info("[GOLDEN] Guardado ejemplo %s (%s) — firma=%s",
                        stage, example.ticket_type, signature[:8])
        except Exception as e:
            logger.warning("[GOLDEN] Error guardando ejemplo: %s", e)

    def get_similar_examples(self, ticket_folder: str, stage: str,
                             top_k: int = 3) -> list[str]:
        try:
            signature = self._compute_ticket_signature(ticket_folder)
            ticket_type = self._classify(ticket_folder)
        except Exception:
            return []

        try:
            examples = self.store.find_similar(signature, stage, top_k=top_k * 2)
        except Exception:
            return []
        if not examples:
            return []

        # Re-ordenar: preferir ticket_type coincidente
        examples.sort(
            key=lambda ex: (0 if ex.ticket_type == ticket_type else 1)
        )
        examples = examples[:top_k]
        return [
            f"EJEMPLO EXITOSO #{i+1}:\n{ex.outcome_snippet}"
            for i, ex in enumerate(examples)
        ]

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _compute_ticket_signature(self, ticket_folder: str) -> str:
        content = ""
        try:
            folder = Path(ticket_folder)
            inc_files = sorted(folder.glob("INC-*.md"))
            target = inc_files[0] if inc_files else None
            if target is None:
                md_files = sorted(folder.glob("*.md"))
                target = md_files[0] if md_files else None
            if target is not None:
                content = target.read_text(encoding="utf-8", errors="replace")[:500]
        except Exception:
            content = ""
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _extract_outcome(self, ticket_folder: str, stage: str) -> str:
        fname = _STAGE_OUTCOME_FILES.get(stage)
        if not fname:
            return ""
        path = os.path.join(ticket_folder, fname)
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read(1500)
        except Exception:
            return ""

    def _classify(self, ticket_folder: str) -> str:
        # Intentar usar ticket_classifier si expone una clasificación de tipo.
        # Su clasificación es por complejidad (simple/medio/complejo), que no es
        # lo mismo que ticket_type. Usamos inferencia por filenames.
        try:
            folder = Path(ticket_folder)
            filenames = [p.name.lower() for p in folder.iterdir() if p.is_file()]
        except Exception:
            return "general"

        has_sql  = any(n.endswith(".sql") for n in filenames)
        has_aspx = any(n.endswith(".aspx") or n.endswith(".aspx.cs") for n in filenames)

        dev_path = os.path.join(ticket_folder, "DEV_COMPLETADO.md")
        mentions_batch = False
        if os.path.isfile(dev_path):
            try:
                with open(dev_path, encoding="utf-8", errors="replace") as f:
                    mentions_batch = "batch" in f.read().lower()
            except Exception:
                pass

        if has_sql:
            return "ddl"
        if has_aspx:
            return "online"
        if mentions_batch:
            return "batch"
        return "general"


# ── Singleton ────────────────────────────────────────────────────────────────

_engine_instance: SelfImprovingEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> SelfImprovingEngine:
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = SelfImprovingEngine()
        return _engine_instance
