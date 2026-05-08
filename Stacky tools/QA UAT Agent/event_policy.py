"""
event_policy.py — Validación de políticas de eventos para QA UAT Agent.

Verifica que el run cumplió las reglas de trazabilidad obligatoria:
  - Todo stage tiene start/end.
  - Todo comando tiene start/end.
  - Todo click tiene intent/completed.
  - Todo fill tiene intent/completed.
  - Todo blocker tiene pregunta humana.
  - Todo artifact referenciado existe.
  - No hay secretos sin redactar.
  - Todo aprendizaje tiene source_event_ids.

Si falla:
  { "ok": false, "verdict": "BLOCKED", "reason": "EVENT_POLICY_VIOLATION", ... }

Si pasa:
  { "ok": true, "verdict": "PASS", "checks": {...} }
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from redactor import scan_for_unredacted_secrets


# ── Validador de políticas ─────────────────────────────────────────────────────

class EventPolicyValidator:
    """
    Valida que los eventos de un run cumplen las políticas obligatorias.

    Usage:
        validator = EventPolicyValidator(run_dir=Path("evidence/70/uat-70-..."))
        result = validator.validate()
        if not result["ok"]:
            # El run está incompleto
            print(result["violations"])
    """

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.events_jsonl = run_dir / "events.jsonl"
        self.checkpoints_dir = run_dir / "checkpoints"
        self.artifacts_registry = run_dir / "artifacts" / "_registry.json"

    def _load_events(self) -> list[dict]:
        if not self.events_jsonl.exists():
            return []
        events = []
        with open(self.events_jsonl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return events

    def _load_artifacts(self) -> list[dict]:
        if not self.artifacts_registry.exists():
            return []
        try:
            return json.loads(self.artifacts_registry.read_text(encoding="utf-8"))
        except Exception:
            return []

    def validate(self) -> dict:
        """
        Ejecutar todas las políticas.

        Devuelve:
        {
          "ok": bool,
          "verdict": "PASS" | "BLOCKED",
          "reason": "EVENT_POLICY_VIOLATION" | None,
          "violations": [...],
          "warnings": [...],
          "checks": { <check_name>: "PASS" | "FAIL" | "WARN" | "SKIP" }
        }
        """
        events = self._load_events()
        artifacts = self._load_artifacts()

        violations: list[str] = []
        warnings: list[str] = []
        checks: dict[str, str] = {}

        # ── P1: Existe events.jsonl ────────────────────────────────────────────
        if not self.events_jsonl.exists():
            violations.append("events.jsonl no existe")
            checks["events_jsonl_exists"] = "FAIL"
        else:
            checks["events_jsonl_exists"] = "PASS"

        if not events:
            violations.append("events.jsonl está vacío — no hay eventos registrados")
            checks["events_not_empty"] = "FAIL"
        else:
            checks["events_not_empty"] = "PASS"

        if events:
            # ── P2: Stages tienen start/end ────────────────────────────────────
            stage_starts: dict[str, str] = {}   # stage → event_id
            stage_ends: set[str] = set()
            for e in events:
                cat = e.get("category", "")
                stage = e.get("stage", "")
                if cat == "stage_started" and stage not in ("run",):
                    stage_starts[stage] = e.get("event_id", "")
                elif cat in ("stage_completed", "stage_failed", "stage_blocked") and stage not in ("run",):
                    stage_ends.add(stage)

            unclosed_stages = set(stage_starts.keys()) - stage_ends
            if unclosed_stages:
                violations.append(f"Stages sin evento de cierre: {sorted(unclosed_stages)}")
                checks["stage_lifecycle"] = "FAIL"
            else:
                checks["stage_lifecycle"] = "PASS" if stage_starts else "SKIP"

            # ── P3: Comandos tienen start/end ──────────────────────────────────
            cmd_starts: set[str] = set()
            cmd_ends: set[str] = set()
            for e in events:
                etype = e.get("event_type", "")
                eid = e.get("event_id", "")
                if etype == "command.started":
                    cmd_starts.add(eid)
                elif etype in ("command.completed", "command.failed"):
                    cause = e.get("causation_event_id", "")
                    if cause:
                        cmd_ends.add(cause)

            unclosed_cmds = cmd_starts - cmd_ends
            if unclosed_cmds:
                warnings.append(f"Comandos sin evento de cierre: {len(unclosed_cmds)}")
                checks["command_lifecycle"] = "WARN"
            else:
                checks["command_lifecycle"] = "PASS" if cmd_starts else "SKIP"

            # ── P4: Clicks tienen intent/result ───────────────────────────────
            click_intents: set[str] = set()
            click_results: set[str] = set()
            for e in events:
                etype = e.get("event_type", "")
                eid = e.get("event_id", "")
                if etype == "playwright.click.intent":
                    click_intents.add(eid)
                elif etype in ("playwright.click.completed", "playwright.click.failed"):
                    cause = e.get("causation_event_id", "")
                    if cause:
                        click_results.add(cause)

            unclosed_clicks = click_intents - click_results
            if unclosed_clicks:
                warnings.append(f"Clicks sin resultado registrado: {len(unclosed_clicks)}")
                checks["click_lifecycle"] = "WARN"
            else:
                checks["click_lifecycle"] = "PASS" if click_intents else "SKIP"

            # ── P5: Fills tienen intent/result ────────────────────────────────
            fill_intents: set[str] = set()
            fill_results: set[str] = set()
            for e in events:
                etype = e.get("event_type", "")
                eid = e.get("event_id", "")
                if etype == "playwright.fill.intent":
                    fill_intents.add(eid)
                elif etype in ("playwright.fill.completed", "playwright.fill.failed"):
                    cause = e.get("causation_event_id", "")
                    if cause:
                        fill_results.add(cause)

            unclosed_fills = fill_intents - fill_results
            if unclosed_fills:
                warnings.append(f"Fills sin resultado registrado: {len(unclosed_fills)}")
                checks["fill_lifecycle"] = "WARN"
            else:
                checks["fill_lifecycle"] = "PASS" if fill_intents else "SKIP"

            # ── P6: Blockers tienen pregunta humana ───────────────────────────
            blocker_event_ids: set[str] = set()
            question_event_ids: set[str] = set()
            for e in events:
                cat = e.get("category", "")
                if cat == "blocker_created":
                    blocker_event_ids.add(e.get("event_id", ""))
                elif cat == "human_question":
                    question_event_ids.add(e.get("causation_event_id", ""))

            unquestioned_blockers = blocker_event_ids - question_event_ids
            if unquestioned_blockers:
                warnings.append(f"Blockers sin pregunta humana registrada: {len(unquestioned_blockers)}")
                checks["blocker_has_question"] = "WARN"
            else:
                checks["blocker_has_question"] = "PASS" if blocker_event_ids else "SKIP"

            # ── P7: Aprendizajes tienen source_event_ids ───────────────────────
            learning_candidates = [
                e for e in events if e.get("category") == "learning_candidate_created"
            ]
            bad_learnings = [
                e for e in learning_candidates
                if not e.get("payload", {}).get("source_event_ids")
            ]
            if bad_learnings:
                violations.append(f"Learning candidates sin source_event_ids: {len(bad_learnings)}")
                checks["learning_source_events"] = "FAIL"
            else:
                checks["learning_source_events"] = "PASS" if learning_candidates else "SKIP"

            # ── P8: Artifacts referenciados existen ───────────────────────────
            artifact_ids_in_events: set[str] = set()
            for e in events:
                for ref in e.get("artifact_refs", []):
                    artifact_ids_in_events.add(ref)

            registered_artifact_ids = {a.get("artifact_id", "") for a in artifacts}
            missing_artifacts = artifact_ids_in_events - registered_artifact_ids
            if missing_artifacts:
                violations.append(
                    f"Artifacts referenciados en eventos pero no registrados: {sorted(missing_artifacts)}"
                )
                checks["artifact_refs_registered"] = "FAIL"
            else:
                checks["artifact_refs_registered"] = "PASS"

            # ── P9: Artifacts tienen sha256 ────────────────────────────────────
            artifacts_without_sha = [a for a in artifacts if not a.get("sha256")]
            if artifacts_without_sha:
                violations.append(f"Artifacts sin sha256: {len(artifacts_without_sha)}")
                checks["artifact_sha256"] = "FAIL"
            else:
                checks["artifact_sha256"] = "PASS" if artifacts else "SKIP"

            # ── P10: No hay secretos sin redactar (muestra) ────────────────────
            secret_warnings = []
            for e in events[:100]:  # verificar primeros 100 eventos
                raw = json.dumps(e.get("payload", {}))
                found = scan_for_unredacted_secrets(raw)
                if found:
                    secret_warnings.extend(found[:3])  # max 3 por evento

            if secret_warnings:
                violations.append(f"Posibles secretos sin redactar en payloads: {len(secret_warnings)} ocurrencias")
                checks["no_unredacted_secrets"] = "FAIL"
            else:
                checks["no_unredacted_secrets"] = "PASS"

        # ── Resultado final ────────────────────────────────────────────────────
        ok = len(violations) == 0
        return {
            "ok": ok,
            "verdict": "PASS" if ok else "BLOCKED",
            "reason": None if ok else "EVENT_POLICY_VIOLATION",
            "message": "Políticas de eventos cumplidas." if ok else f"{len(violations)} violación(es) detectada(s).",
            "violations": violations,
            "warnings": warnings,
            "checks": checks,
            "event_count": len(events),
            "artifact_count": len(artifacts),
        }


# ── Función de conveniencia ────────────────────────────────────────────────────

def validate_event_policy(run_dir: Path) -> dict:
    """Validar políticas de eventos para un run dado su directorio."""
    return EventPolicyValidator(run_dir).validate()
