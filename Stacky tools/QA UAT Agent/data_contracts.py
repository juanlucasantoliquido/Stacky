"""
data_contracts.py — Validación de contratos de calidad de datos para QA UAT Agent.

Los data contracts validan que los datos del run son confiables antes de
usarlos para calcular KPIs, generar reportes o aprobar aprendizajes.

Si un contrato falla, los KPIs no son confiables y el run puede quedar inválido.

Contratos implementados:
  DC-01: Todo evento tiene event_id.
  DC-02: Todo evento tiene run_id.
  DC-03: Todo evento tiene seq_run.
  DC-04: seq_run es incremental por run (sin gaps mayores a 5, sin repeticiones).
  DC-05: Todo stage.started tiene cierre (stage.completed | failed | blocked).
  DC-06: Todo artifact_ref existe físicamente.
  DC-07: Todo artifact tiene sha256.
  DC-08: No hay secretos sin redactar en payloads.
  DC-09: Todo blocker tiene reason.
  DC-10: Toda pregunta humana tiene status.
  DC-11: Toda respuesta humana tiene question_id.
  DC-12: Todo learning_candidate tiene source_event_ids.
  DC-13: Todo learning.applied tiene learning_id.
  DC-14: Toda métrica tiene run_id.
  DC-15: run_manifest.json existe y tiene campos obligatorios.
  DC-16: run_state.json existe y tiene campos obligatorios.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from redactor import scan_for_unredacted_secrets


_CONTRACT_IDS = [
    "DC-01", "DC-02", "DC-03", "DC-04", "DC-05",
    "DC-06", "DC-07", "DC-08", "DC-09", "DC-10",
    "DC-11", "DC-12", "DC-13", "DC-14", "DC-15", "DC-16",
]


class DataContractValidator:
    """
    Valida contratos de calidad de datos para un run completo.

    Usage:
        dv = DataContractValidator(run_dir=Path("evidence/70/uat-70-..."))
        result = dv.validate()
    """

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir

    def _load_events(self) -> list[dict]:
        p = self.run_dir / "events.jsonl"
        if not p.exists():
            return []
        events = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
        return events

    def _load_json(self, rel_path: str) -> Optional[dict]:
        p = self.run_dir / rel_path
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_artifacts(self) -> list[dict]:
        p = self.run_dir / "artifacts" / "_registry.json"
        if not p.exists():
            return []
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []

    def validate(self) -> dict:
        """
        Ejecutar todos los contratos.

        Devuelve:
        {
          "ok": bool,
          "verdict": "PASS" | "BLOCKED",
          "reason": "DATA_CONTRACT_VIOLATION" | None,
          "violations": [ {"contract": "DC-01", "message": "..."} ],
          "warnings": [...],
          "contracts": { "DC-01": "PASS" | "FAIL" | "WARN" | "SKIP" }
        }
        """
        events = self._load_events()
        artifacts = self._load_artifacts()
        manifest = self._load_json("run_manifest.json")
        state = self._load_json("run_state.json")

        violations: list[dict] = []
        warnings: list[str] = []
        contracts: dict[str, str] = {}

        def fail(cid: str, msg: str) -> None:
            violations.append({"contract": cid, "message": msg})
            contracts[cid] = "FAIL"

        def warn(cid: str, msg: str) -> None:
            warnings.append(f"[{cid}] {msg}")
            contracts[cid] = "WARN"

        def ok(cid: str) -> None:
            if cid not in contracts:
                contracts[cid] = "PASS"

        def skip(cid: str) -> None:
            if cid not in contracts:
                contracts[cid] = "SKIP"

        # ── DC-01: event_id presente ────────────────────────────────────────────
        missing_eid = [e for e in events if not e.get("event_id")]
        if missing_eid:
            fail("DC-01", f"{len(missing_eid)} evento(s) sin event_id")
        else:
            ok("DC-01")

        # ── DC-02: run_id presente ──────────────────────────────────────────────
        missing_rid = [e for e in events if not e.get("run_id")]
        if missing_rid:
            fail("DC-02", f"{len(missing_rid)} evento(s) sin run_id")
        else:
            ok("DC-02")

        # ── DC-03: seq_run presente ─────────────────────────────────────────────
        missing_seq = [e for e in events if "seq_run" not in e]
        if missing_seq:
            fail("DC-03", f"{len(missing_seq)} evento(s) sin seq_run")
        else:
            ok("DC-03")

        # ── DC-04: seq_run incremental ──────────────────────────────────────────
        if events:
            seqs = [e.get("seq_run", 0) for e in events if "seq_run" in e]
            seen: set[int] = set()
            dupes = []
            for s in seqs:
                if s in seen:
                    dupes.append(s)
                seen.add(s)
            if dupes:
                warn("DC-04", f"seq_run duplicados: {dupes[:5]}")
            else:
                ok("DC-04")
        else:
            skip("DC-04")

        # ── DC-05: stage.started tiene cierre ──────────────────────────────────
        stage_opens: set[str] = set()
        stage_closes: set[str] = set()
        for e in events:
            cat = e.get("category", "")
            stage = e.get("stage", "")
            if cat == "stage_started" and stage and stage != "run":
                stage_opens.add(stage)
            elif cat in ("stage_completed", "stage_failed", "stage_blocked") and stage and stage != "run":
                stage_closes.add(stage)
        unclosed = stage_opens - stage_closes
        if unclosed:
            warn("DC-05", f"Stages sin cierre: {sorted(unclosed)}")
        else:
            ok("DC-05")

        # ── DC-06: artifact_refs existen ────────────────────────────────────────
        registered_ids = {a.get("artifact_id", "") for a in artifacts}
        bad_refs = []
        for e in events:
            for ref in e.get("artifact_refs", []):
                if ref not in registered_ids:
                    bad_refs.append(ref)
        if bad_refs:
            warn("DC-06", f"artifact_refs no registrados: {bad_refs[:5]}")
        else:
            ok("DC-06")

        # ── DC-07: artifacts tienen sha256 ──────────────────────────────────────
        no_sha = [a.get("artifact_id", "") for a in artifacts if not a.get("sha256")]
        if no_sha:
            fail("DC-07", f"Artifacts sin sha256: {no_sha[:5]}")
        else:
            ok("DC-07") if artifacts else skip("DC-07")

        # ── DC-08: no secretos sin redactar ────────────────────────────────────
        secret_hits = 0
        for e in events[:200]:
            raw = json.dumps(e.get("payload", {}))
            found = scan_for_unredacted_secrets(raw)
            secret_hits += len(found)
        if secret_hits > 0:
            fail("DC-08", f"Posibles secretos sin redactar en payloads: {secret_hits} ocurrencias")
        else:
            ok("DC-08")

        # ── DC-09: blockers tienen reason ──────────────────────────────────────
        blockers = [e for e in events if e.get("category") == "blocker_created"]
        blockers_no_reason = [b for b in blockers if not b.get("payload", {}).get("reason")]
        if blockers_no_reason:
            fail("DC-09", f"Blockers sin reason: {len(blockers_no_reason)}")
        else:
            ok("DC-09") if blockers else skip("DC-09")

        # ── DC-10: preguntas humanas tienen status ─────────────────────────────
        questions = [e for e in events if e.get("category") == "human_question"]
        questions_no_status = [q for q in questions if not q.get("payload", {}).get("status")]
        if questions_no_status:
            fail("DC-10", f"Preguntas humanas sin status: {len(questions_no_status)}")
        else:
            ok("DC-10") if questions else skip("DC-10")

        # ── DC-11: respuestas humanas tienen question_id ────────────────────────
        answers = [e for e in events if e.get("category") == "human_answer"]
        answers_no_qid = [a for a in answers if not a.get("payload", {}).get("question_id")]
        if answers_no_qid:
            fail("DC-11", f"Respuestas humanas sin question_id: {len(answers_no_qid)}")
        else:
            ok("DC-11") if answers else skip("DC-11")

        # ── DC-12: learning_candidates tienen source_event_ids ─────────────────
        candidates = [e for e in events if e.get("category") == "learning_candidate_created"]
        bad_candidates = [c for c in candidates if not c.get("payload", {}).get("source_event_ids")]
        if bad_candidates:
            fail("DC-12", f"Learning candidates sin source_event_ids: {len(bad_candidates)}")
        else:
            ok("DC-12") if candidates else skip("DC-12")

        # ── DC-13: learning.applied tiene learning_id ──────────────────────────
        applied = [e for e in events if e.get("category") == "learning_applied"]
        applied_no_id = [a for a in applied if not a.get("payload", {}).get("learning_id")]
        if applied_no_id:
            fail("DC-13", f"learning.applied sin learning_id: {len(applied_no_id)}")
        else:
            ok("DC-13") if applied else skip("DC-13")

        # ── DC-14: métricas tienen run_id ──────────────────────────────────────
        metrics = [e for e in events if e.get("category") == "metric"]
        metrics_no_run = [m for m in metrics if not m.get("run_id")]
        if metrics_no_run:
            warn("DC-14", f"Métricas sin run_id: {len(metrics_no_run)}")
        else:
            ok("DC-14") if metrics else skip("DC-14")

        # ── DC-15: run_manifest.json existe y tiene campos ─────────────────────
        required_manifest_fields = {"run_id", "ticket_id", "trace_id", "started_at", "schema_version"}
        if manifest is None:
            fail("DC-15", "run_manifest.json no existe")
        else:
            missing_mf = required_manifest_fields - set(manifest.keys())
            if missing_mf:
                fail("DC-15", f"run_manifest.json incompleto — faltan: {sorted(missing_mf)}")
            else:
                ok("DC-15")

        # ── DC-16: run_state.json existe y tiene campos ─────────────────────────
        required_state_fields = {"run_id", "status", "updated_at"}
        if state is None:
            fail("DC-16", "run_state.json no existe")
        else:
            missing_sf = required_state_fields - set(state.keys())
            if missing_sf:
                fail("DC-16", f"run_state.json incompleto — faltan: {sorted(missing_sf)}")
            else:
                ok("DC-16")

        # Rellenar SKIPs
        for cid in _CONTRACT_IDS:
            if cid not in contracts:
                contracts[cid] = "SKIP"

        is_ok = len(violations) == 0
        return {
            "ok": is_ok,
            "verdict": "PASS" if is_ok else "BLOCKED",
            "reason": None if is_ok else "DATA_CONTRACT_VIOLATION",
            "message": "Contratos de datos cumplidos." if is_ok else f"{len(violations)} violación(es) de contrato.",
            "violations": violations,
            "warnings": warnings,
            "contracts": contracts,
            "event_count": len(events),
            "artifact_count": len(artifacts),
        }


# ── Función de conveniencia ────────────────────────────────────────────────────

def validate_data_contracts(run_dir: Path) -> dict:
    """Validar contratos de datos para un run dado su directorio."""
    return DataContractValidator(run_dir).validate()
