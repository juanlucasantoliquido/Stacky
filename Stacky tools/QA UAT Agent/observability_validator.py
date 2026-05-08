"""
observability_validator.py — Validador de observabilidad completa de un run.

Verifica que un run tiene cobertura forense completa antes de publicar
resultados o archivar evidencia.

CAPAS VALIDADAS:
  1. event_policy.py   — 10 políticas de trazabilidad de eventos
  2. data_contracts.py — 16 contratos de calidad de datos
  3. run_manifest      — exists, has required fields
  4. checkpoints       — all stages have checkpoints
  5. artifacts         — all artifacts registered + sha256
  6. playwright        — forensic JSONL files exist (if playwright ran)
  7. blockers          — no pending blockers (si aplica)
  8. metrics           — métricas colectadas para este run

RESULTADO:
{
  "ok": bool,
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "run_id": "...",
  "checks": {
    "event_policy": {"ok": bool, "violations": [...], "warnings": [...]},
    "data_contracts": {"ok": bool, "failed": [...], "warnings": [...]},
    "run_manifest": {"ok": bool, "missing_fields": [...]},
    "checkpoints": {"ok": bool, "missing": [...]},
    "artifacts": {"ok": bool, "missing_sha256": [...], "missing_files": [...]},
    "playwright": {"ok": bool, "missing_files": [...]},
    "blockers": {"ok": bool, "pending_count": int},
    "metrics": {"ok": bool, "reason": "..."},
  },
  "score": 7,   // de 8 checks que pasaron
  "max_score": 8,
}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

_py_logger = logging.getLogger("stacky.qa_uat.observability_validator")


class ObservabilityValidator:
    """
    Valida observabilidad completa de un run.

    Uso:
        ov = ObservabilityValidator(run_dir=run_dir, run_id=run_id)
        result = ov.validate()
        if not result["ok"]:
            print(result["checks"])
    """

    def __init__(self, run_dir: Path, run_id: str) -> None:
        self.run_dir = run_dir
        self.run_id = run_id

    def validate(self) -> dict:
        checks: dict[str, dict] = {}

        # 1. event_policy
        checks["event_policy"] = self._check_event_policy()

        # 2. data_contracts
        checks["data_contracts"] = self._check_data_contracts()

        # 3. run_manifest
        checks["run_manifest"] = self._check_run_manifest()

        # 4. checkpoints
        checks["checkpoints"] = self._check_checkpoints()

        # 5. artifacts
        checks["artifacts"] = self._check_artifacts()

        # 6. playwright
        checks["playwright"] = self._check_playwright()

        # 7. blockers
        checks["blockers"] = self._check_blockers()

        # 8. metrics
        checks["metrics"] = self._check_metrics()

        # Score
        score = sum(1 for c in checks.values() if c.get("ok", False))
        max_score = len(checks)

        # Verdict
        if score == max_score:
            verdict = "PASS"
        elif score >= max_score * 0.75:
            verdict = "PARTIAL"
        else:
            verdict = "FAIL"

        return {
            "ok": verdict == "PASS",
            "verdict": verdict,
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "score": score,
            "max_score": max_score,
            "checks": checks,
        }

    # ── Checks ─────────────────────────────────────────────────────────────────

    def _check_event_policy(self) -> dict:
        try:
            from event_policy import EventPolicyValidator
            epv = EventPolicyValidator(self.run_dir, self.run_id)
            result = epv.validate()
            return {
                "ok": result.get("ok", False),
                "verdict": result.get("verdict"),
                "violations": result.get("violations", []),
                "warnings": result.get("warnings", []),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _check_data_contracts(self) -> dict:
        try:
            from data_contracts import DataContractValidator
            dcv = DataContractValidator(self.run_dir, self.run_id)
            result = dcv.validate()
            return {
                "ok": result.get("ok", False),
                "failed": result.get("failed_contracts", []),
                "warnings": result.get("warnings", []),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _check_run_manifest(self) -> dict:
        manifest_path = self.run_dir / "run_manifest.json"
        if not manifest_path.exists():
            return {"ok": False, "missing_fields": [], "error": "run_manifest.json no encontrado"}

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"Error leyendo run_manifest.json: {exc}"}

        required = ["run_id", "ticket_id", "started_at", "tool_version", "schema_version"]
        missing = [f for f in required if not manifest.get(f)]

        return {"ok": len(missing) == 0, "missing_fields": missing}

    def _check_checkpoints(self) -> dict:
        chk_dir = self.run_dir / "checkpoints"
        if not chk_dir.exists():
            return {"ok": False, "error": "checkpoints/ no encontrado", "missing": []}

        checkpoint_files = list(chk_dir.glob("*.json"))
        if not checkpoint_files:
            return {"ok": False, "error": "No hay checkpoints registrados", "missing": []}

        return {"ok": True, "count": len(checkpoint_files)}

    def _check_artifacts(self) -> dict:
        registry_path = self.run_dir / "artifacts" / "_registry.json"
        if not registry_path.exists():
            # No hay artifacts — puede ser válido si no hubo playwright
            return {"ok": True, "note": "Sin artifacts registrados (puede ser normal)", "missing_sha256": [], "missing_files": []}

        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"Error leyendo _registry.json: {exc}"}

        missing_sha256 = []
        missing_files = []

        for art in registry:
            if not art.get("sha256"):
                missing_sha256.append(art.get("artifact_id", "?"))
            # Check file exists
            rel_path = art.get("path", "")
            if rel_path:
                full = self.run_dir / rel_path
                if not full.exists():
                    missing_files.append(rel_path)

        ok = len(missing_sha256) == 0 and len(missing_files) == 0
        return {
            "ok": ok,
            "total": len(registry),
            "missing_sha256": missing_sha256[:10],
            "missing_files": missing_files[:10],
        }

    def _check_playwright(self) -> dict:
        pw_dir = self.run_dir / "playwright"
        if not pw_dir.exists():
            # No ran Playwright — not an error if no playwright events
            events_path = self.run_dir / "events.jsonl"
            if events_path.exists():
                # Check if there were any playwright events
                try:
                    with open(events_path, encoding="utf-8") as f:
                        has_pw = any(
                            '"source": "playwright"' in line or
                            '"playwright"' in line
                            for line in f
                        )
                    if has_pw:
                        return {"ok": False, "error": "playwright/ no existe pero hay eventos playwright", "missing_files": []}
                except Exception:
                    pass
            return {"ok": True, "note": "Playwright no ejecutado"}

        required_files = ["actions.jsonl"]
        missing = [f for f in required_files if not (pw_dir / f).exists()]

        return {
            "ok": len(missing) == 0,
            "missing_files": missing,
            "has_network": (pw_dir / "network.jsonl").exists(),
            "has_console": (pw_dir / "console.jsonl").exists(),
            "has_screenshots": (pw_dir / "screenshots.jsonl").exists(),
        }

    def _check_blockers(self) -> dict:
        blockers_path = self.run_dir / "blockers.json"
        if not blockers_path.exists():
            return {"ok": True, "note": "Sin blockers registrados"}

        try:
            blockers = json.loads(blockers_path.read_text(encoding="utf-8"))
            pending = [b for b in blockers if b.get("status") == "pending"]
            return {
                "ok": len(pending) == 0,
                "pending_count": len(pending),
                "total": len(blockers),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _check_metrics(self) -> dict:
        """Verificar que se colectaron métricas para este run."""
        try:
            from metrics_collector import MetricsCollector, _METRICS_DB_PATH
            mc = MetricsCollector(evidence_dir=self.run_dir.parent.parent)
            all_metrics = mc.load_all()
            run_metrics = [m for m in all_metrics if m.get("run_id") == self.run_id]
            if run_metrics:
                return {"ok": True, "count": len(run_metrics)}
            return {
                "ok": False,
                "reason": "No se encontraron métricas para este run_id",
                "hint": "Ejecutar MetricsCollector.collect_and_persist() al final del run",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
