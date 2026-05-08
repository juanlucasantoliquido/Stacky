"""
learning_candidate_generator.py — Generador automático de candidatos de learning.

Analiza los eventos de un run completado y propone candidatos de learning
para revisión humana. Los patrones detectados son:

  1. SELECTOR_FIX: click/fill falló con un selector → hubo un workaround exitoso
  2. TIMEOUT_FIX: playwright timeout en una acción → timeout insuficiente
  3. FLOW_FIX: navegación falló (URL inesperada) → pantalla incorrecta en playbook
  4. DATA_FIX: fill con valor vacío o inválido detectado por screen_error
  5. BLOCKER_RESOLVED: un blocker fue resuelto con respuesta → la respuesta es el learning
  6. REPLAN_SUCCESS: hubo replan exitoso → qué cambió es el learning

Los candidatos se guardan en LearningStore (requiere aprobación humana).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from learning_store import LearningStore

_py_logger = logging.getLogger("stacky.qa_uat.learning_candidate_generator")

# Máximo de candidatos por run (para no sobrecargar)
_MAX_CANDIDATES_PER_RUN = 20


class LearningCandidateGenerator:
    """
    Analiza eventos de un run y propone candidatos de learning.

    Uso:
        gen = LearningCandidateGenerator(
            run_id="uat-70-...", ticket_id=70,
            events_jsonl=Path("evidence/70/uat-70-.../events.jsonl"),
            blockers_json=Path("evidence/70/uat-70-.../blockers.json"),
        )
        candidates = gen.generate()
        # candidates = [{"learning_id": ..., "title": ..., "category": ...}]
    """

    def __init__(
        self,
        run_id: str,
        ticket_id: Any,
        events_jsonl: Path,
        *,
        blockers_json: Optional[Path] = None,
        run_dir: Optional[Path] = None,
        store: Optional[LearningStore] = None,
    ) -> None:
        self.run_id = run_id
        self.ticket_id = ticket_id
        self.events_jsonl = events_jsonl
        self.blockers_json = blockers_json
        self.run_dir = run_dir or events_jsonl.parent
        self._store = store or LearningStore()
        self._candidates: list[dict] = []

    # ── Entrada pública ────────────────────────────────────────────────────────

    def generate(self) -> list[dict]:
        """
        Analizar eventos y generar candidatos.

        Devuelve lista de candidatos registrados en el LearningStore.
        """
        events = self._load_events()
        blockers = self._load_blockers()

        self._detect_selector_fixes(events)
        self._detect_timeout_hints(events)
        self._detect_flow_fixes(events)
        self._detect_blocker_resolutions(blockers)
        self._detect_replan_patterns(events)

        return list(self._candidates)

    # ── Carga de datos ─────────────────────────────────────────────────────────

    def _load_events(self) -> list[dict]:
        if not self.events_jsonl.exists():
            return []
        events = []
        try:
            with open(self.events_jsonl, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            _py_logger.warning("LearningCandidateGenerator: error leyendo events: %s", exc)
        return events

    def _load_blockers(self) -> list[dict]:
        if self.blockers_json is None:
            # Intentar path por defecto
            default = self.run_dir / "blockers.json"
            if not default.exists():
                return []
            self.blockers_json = default
        try:
            return json.loads(self.blockers_json.read_text(encoding="utf-8"))
        except Exception:
            return []

    # ── Detectores ────────────────────────────────────────────────────────────

    def _detect_selector_fixes(self, events: list[dict]) -> None:
        """
        Detectar patrones de selector fallido → acción exitosa posterior.

        Patrón: playwright.click.failed o playwright.fill.failed
        seguido de playwright.click.completed o playwright.fill.completed
        en el mismo step o step cercano, con selector diferente.
        """
        failed_actions: list[dict] = []
        for evt in events:
            et = evt.get("event_type", "")
            status = evt.get("status", "")
            category = evt.get("category", "")

            if status == "failed" and category in ("page_click", "page_fill"):
                failed_actions.append(evt)
            elif status == "completed" and category in ("page_click", "page_fill") and failed_actions:
                # Hay una acción exitosa después de fallas
                last_fail = failed_actions[-1]
                fail_sel = (last_fail.get("payload") or {}).get("selector") or last_fail.get("selector")
                ok_sel = (evt.get("payload") or {}).get("selector") or evt.get("selector")
                if fail_sel and ok_sel and fail_sel != ok_sel:
                    if len(self._candidates) < _MAX_CANDIDATES_PER_RUN:
                        self._add_candidate(
                            category="selector_fix",
                            title=f"Selector fallido reemplazado: {str(fail_sel)[:60]}",
                            description=(
                                f"La acción '{last_fail.get('action', 'action')}' falló con "
                                f"selector '{fail_sel}' y tuvo éxito con '{ok_sel}'. "
                                f"Considerar actualizar el selector en el playbook."
                            ),
                            evidence={
                                "failed_selector": fail_sel,
                                "working_selector": ok_sel,
                                "action": last_fail.get("action"),
                                "stage": last_fail.get("stage"),
                            },
                            source_event_ids=[
                                last_fail.get("event_id", ""),
                                evt.get("event_id", ""),
                            ],
                            stage=last_fail.get("stage", "runner"),
                        )
                failed_actions = []

    def _detect_timeout_hints(self, events: list[dict]) -> None:
        """
        Detectar eventos con error de timeout de Playwright.
        """
        for evt in events:
            error = str((evt.get("payload") or {}).get("error") or evt.get("error") or "")
            if "timeout" in error.lower() and "exceeded" in error.lower():
                sel = (evt.get("payload") or {}).get("selector") or evt.get("selector")
                if len(self._candidates) < _MAX_CANDIDATES_PER_RUN:
                    self._add_candidate(
                        category="timeout_fix",
                        title=f"Timeout detectado en acción: {evt.get('action', 'action')}",
                        description=(
                            f"La acción '{evt.get('action', 'action')}' "
                            f"{'en selector ' + str(sel)[:60] if sel else ''} "
                            f"superó el timeout. Considerar aumentar QA_UAT_STEP_TIMEOUT_MS "
                            f"o verificar que el elemento aparece en esa pantalla."
                        ),
                        evidence={
                            "action": evt.get("action"),
                            "selector": sel,
                            "error": error[:300],
                            "stage": evt.get("stage"),
                        },
                        source_event_ids=[evt.get("event_id", "")],
                        stage=evt.get("stage", "runner"),
                    )

    def _detect_flow_fixes(self, events: list[dict]) -> None:
        """
        Detectar navegaciones que terminaron en pantalla inesperada.
        """
        for evt in events:
            et = evt.get("event_type", "")
            payload = evt.get("payload") or {}
            # Error de "Session expired" o URL inesperada en beforeEach
            error = str(evt.get("error") or "")
            msg = str(evt.get("message") or "")
            if ("frmlogin" in error.lower() or "session expired" in msg.lower() or
                    "session expired" in error.lower()):
                if len(self._candidates) < _MAX_CANDIDATES_PER_RUN:
                    self._add_candidate(
                        category="flow_fix",
                        title="Sesión expiró antes del test — pantalla de login inesperada",
                        description=(
                            "El test encontró la pantalla de login cuando esperaba otra pantalla. "
                            "La sesión de AgendaWeb expiró. Considerar reducir el tiempo entre "
                            "global.setup y la ejecución del spec, o aumentar el timeout de sesión."
                        ),
                        evidence={
                            "event_type": et,
                            "stage": evt.get("stage"),
                            "error": error[:300],
                        },
                        source_event_ids=[evt.get("event_id", "")],
                        stage=evt.get("stage", "runner"),
                    )
                    break  # un solo candidato por este patrón

    def _detect_blocker_resolutions(self, blockers: list[dict]) -> None:
        """
        Para cada blocker resuelto, generar un learning con la respuesta.
        """
        for b in blockers:
            if b.get("status") != "resolved":
                continue
            answer = b.get("answer", "")
            if not answer:
                continue
            if len(self._candidates) < _MAX_CANDIDATES_PER_RUN:
                self._add_candidate(
                    category="other",
                    title=f"Blocker resuelto: {b.get('reason', '')[:60]}",
                    description=(
                        f"El blocker '{b.get('reason')}' en stage '{b.get('stage')}' "
                        f"fue resuelto con respuesta: '{answer}'. "
                        f"Pregunta original: '{b.get('question', '')}'."
                    ),
                    evidence={
                        "blocker_id": b.get("blocker_id"),
                        "reason": b.get("reason"),
                        "question": b.get("question"),
                        "answer": answer,
                        "answered_by": b.get("answered_by"),
                    },
                    source_event_ids=[],
                    stage=b.get("stage", "unknown"),
                )

    def _detect_replan_patterns(self, events: list[dict]) -> None:
        """
        Detectar eventos de replan exitoso.
        """
        for evt in events:
            et = evt.get("event_type", "")
            if "replan" in et.lower() and evt.get("status") == "completed":
                payload = evt.get("payload") or {}
                if len(self._candidates) < _MAX_CANDIDATES_PER_RUN:
                    self._add_candidate(
                        category="flow_fix",
                        title=f"Replan exitoso en stage {evt.get('stage', 'unknown')}",
                        description=(
                            f"El replan fue necesario y exitoso. "
                            f"Detalles: {json.dumps(payload)[:300]}"
                        ),
                        evidence={"payload": payload, "event_type": et},
                        source_event_ids=[evt.get("event_id", "")],
                        stage=evt.get("stage", "unknown"),
                    )

    # ── Helper interno ─────────────────────────────────────────────────────────

    def _add_candidate(
        self,
        category: str,
        title: str,
        description: str,
        evidence: dict,
        source_event_ids: list[str],
        stage: str,
    ) -> Optional[str]:
        """Agregar candidato al store y a la lista local."""
        # Evitar duplicados por título en este run
        for existing in self._candidates:
            if existing.get("title") == title:
                return existing.get("learning_id")

        try:
            lid = self._store.add_candidate(
                run_id=self.run_id,
                ticket_id=self.ticket_id,
                category=category,
                title=title,
                description=description,
                stage=stage,
                evidence=evidence,
                source_event_ids=[s for s in source_event_ids if s],
            )
            self._candidates.append({
                "learning_id": lid,
                "category": category,
                "title": title,
                "stage": stage,
            })
            return lid
        except Exception as exc:
            _py_logger.warning("LearningCandidateGenerator: error registrando candidato: %s", exc)
            return None
