"""
prompt_tracker.py — E-04: Prompt Scoring y Evolución Automática.

Registra cada versión de prompt utilizada y su resultado (éxito/falla/rework).
Con el tiempo, permite identificar qué variaciones de prompt tienen mejor
tasa de éxito y cuáles correlacionan con más reworks o rechazos QA.

Los prompts se hashean para rastrear versiones sin almacenar el texto completo.
Los scores se persisten en knowledge/{project}/prompt_scores.json.

Uso:
    from prompt_tracker import PromptTracker
    pt = PromptTracker(project_name)
    hash_id = pt.record_prompt(ticket_id, stage, prompt_text)
    pt.record_outcome(hash_id, success=True, rework=False, qa_verdict="APROBADO")
    report = pt.get_evolution_report()
"""

import hashlib
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.prompt_tracker")

_MAX_RECORDS = 2000


class PromptTracker:
    """
    Rastrea versiones de prompts y su correlación con resultados del pipeline.
    """

    def __init__(self, project_name: str):
        self._project = project_name
        self._lock    = threading.RLock()
        self._path    = self._get_path()
        self._data    = self._load()

    # ── API pública ───────────────────────────────────────────────────────

    def record_prompt(self, ticket_id: str, stage: str,
                      prompt_text: str) -> str:
        """
        Registra un prompt y retorna su hash_id para posterior tracking.
        No almacena el texto completo — solo el hash y características.
        """
        hash_id  = self._hash_prompt(prompt_text)
        features = self._extract_features(prompt_text, stage)

        with self._lock:
            records  = self._data.setdefault("records", [])
            # Actualizar o crear registro para este hash
            existing = next((r for r in records if r["hash"] == hash_id), None)
            if existing:
                existing["use_count"] = existing.get("use_count", 0) + 1
                existing["last_used"] = datetime.now().isoformat()
                existing.setdefault("tickets", [])
                if ticket_id not in existing["tickets"]:
                    existing["tickets"].append(ticket_id)
            else:
                records.append({
                    "hash":       hash_id,
                    "stage":      stage,
                    "features":   features,
                    "use_count":  1,
                    "success":    0,
                    "fail":       0,
                    "rework":     0,
                    "tickets":    [ticket_id],
                    "created_at": datetime.now().isoformat(),
                    "last_used":  datetime.now().isoformat(),
                })
                # Mantener límite
                if len(records) > _MAX_RECORDS:
                    self._data["records"] = records[-_MAX_RECORDS:]
            self._save()

        return hash_id

    def record_outcome(self, hash_id: str, success: bool,
                       rework: bool = False, qa_verdict: str = "") -> None:
        """
        Registra el resultado de un prompt previamente tracked.
        """
        with self._lock:
            records  = self._data.get("records", [])
            existing = next((r for r in records if r["hash"] == hash_id), None)
            if not existing:
                return
            if success:
                existing["success"] = existing.get("success", 0) + 1
            else:
                existing["fail"] = existing.get("fail", 0) + 1
            if rework:
                existing["rework"] = existing.get("rework", 0) + 1
            if qa_verdict:
                existing.setdefault("qa_verdicts", {})
                existing["qa_verdicts"][qa_verdict] = \
                    existing["qa_verdicts"].get(qa_verdict, 0) + 1
            self._save()

    def get_best_prompts(self, stage: str, top_k: int = 5) -> list[dict]:
        """
        Retorna los prompts con mejor tasa de éxito para una etapa.
        Solo considera prompts con al menos 3 usos.
        """
        with self._lock:
            records = [r for r in self._data.get("records", [])
                       if r["stage"] == stage and r.get("use_count", 0) >= 3]

        scored = []
        for r in records:
            total   = r.get("success", 0) + r.get("fail", 0)
            if total == 0:
                continue
            success_rate = r["success"] / total
            rework_rate  = r.get("rework", 0) / r.get("use_count", 1)
            # Score combinado: success_rate penalizado por rework
            score = success_rate * (1 - rework_rate * 0.3)
            scored.append({**r, "success_rate": round(success_rate, 3),
                           "rework_rate": round(rework_rate, 3),
                           "composite_score": round(score, 3)})

        scored.sort(key=lambda x: -x["composite_score"])
        return scored[:top_k]

    def get_evolution_report(self) -> str:
        """Genera un reporte de texto sobre la evolución de los prompts."""
        lines = [
            f"# Prompt Evolution Report — {self._project}",
            f"> Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        for stage in ("pm", "dev", "tester"):
            best = self.get_best_prompts(stage, top_k=3)
            all_stage = [r for r in self._data.get("records", [])
                         if r["stage"] == stage]
            if not all_stage:
                continue

            total_uses    = sum(r.get("use_count", 0) for r in all_stage)
            total_success = sum(r.get("success", 0)   for r in all_stage)
            total_fail    = sum(r.get("fail", 0)       for r in all_stage)
            total_rework  = sum(r.get("rework", 0)     for r in all_stage)
            total_out     = total_success + total_fail

            lines += [
                f"## {stage.upper()}",
                "",
                f"- Versiones de prompt distintas: {len(all_stage)}",
                f"- Usos totales: {total_uses}",
                f"- Éxito: {total_success}/{total_out} ({total_success/total_out:.0%})"
                  if total_out else "- Sin datos de outcome",
                f"- Reworks: {total_rework}",
                "",
            ]

            if best:
                lines.append("**Top prompts por composite score:**")
                lines.append("")
                for i, p in enumerate(best, 1):
                    feat = ", ".join(f"{k}={v}" for k, v in
                                    list(p.get("features", {}).items())[:3])
                    lines.append(
                        f"{i}. `{p['hash'][:8]}` — score {p['composite_score']:.2f} "
                        f"| éxito {p['success_rate']:.0%} | {feat}"
                    )
                lines.append("")

        return "\n".join(lines)

    def get_stats(self) -> dict:
        """Retorna estadísticas rápidas."""
        with self._lock:
            records = self._data.get("records", [])
            return {
                "total_versions": len(records),
                "total_uses":     sum(r.get("use_count", 0) for r in records),
                "by_stage":       {s: len([r for r in records if r["stage"] == s])
                                   for s in ("pm", "dev", "tester")},
            }

    # ── Internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _hash_prompt(prompt_text: str) -> str:
        """Hash SHA-256 truncado del prompt."""
        return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _extract_features(prompt_text: str, stage: str) -> dict:
        """Extrae características numéricas del prompt para análisis."""
        import re
        return {
            "char_count":     len(prompt_text),
            "has_kb":         "Knowledge Base" in prompt_text,
            "has_patterns":   "Patrones de solución" in prompt_text,
            "has_schema":     "Schema Oracle" in prompt_text,
            "has_memory":     "Memoria del Proyecto" in prompt_text,
            "has_changes":  "GIT_CHANGES" in prompt_text,
            "has_blast":      "BLAST_RADIUS" in prompt_text,
            "section_count":  len(re.findall(r'^##', prompt_text, re.MULTILINE)),
        }

    def _get_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, "prompt_scores.json")

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"records": []}
        except Exception as e:
            logger.warning("[PROMPT_TRACKER] Error cargando: %s", e)
            return {"records": []}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:
            logger.error("[PROMPT_TRACKER] Error guardando: %s", e)


# ── Singleton por proyecto ────────────────────────────────────────────────────

_pt_instances: dict[str, PromptTracker] = {}
_pt_lock = threading.Lock()


def get_prompt_tracker(project_name: str) -> PromptTracker:
    with _pt_lock:
        if project_name not in _pt_instances:
            _pt_instances[project_name] = PromptTracker(project_name)
        return _pt_instances[project_name]
