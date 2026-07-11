"""Plan 60 F4+F5 — Materializador: edición humana en ADO -> lección en corpus plan 54.

`learn_from_work_item` orquesta:
  1. leer revisiones ADO (fetch_work_item_updates — dead code reactivado)
  2. detectar la edición humana más reciente no procesada (ado_edit_detect.select_latest_human_edit)
  3. diffear contra baseline (ado_edit_diff.diff_edit — función pura)
  4. materializar lección determinista en corpus del plan 54 (memory_store.save_observation,
     type="operator_note" + tags approval_condition+ado_human_edit — C2)
  5. marcar ledger de idempotencia (ado_edit_ledger.mark_learned)

`sweep_recent_runs` es el loop de fondo (wiring en app.py, gateado por STACKY_ADO_EDIT_LEARNING_ENABLED).

Principios:
- Sin LLM: diff puro determinista.
- Sin PII: author se usa solo para decidir, nunca se persiste en corpus (C4).
- Idempotente: ledger (ado_id, rev) impide duplicar la misma revisión.
- Degradación limpia: cualquier paso que falla -> LearnResult(learned=False, reason=...).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("stacky_agents.services.ado_edit_learning")

_MAX_LESSON_CHARS = 1500
_MAX_BULLETS = 6
_SWEEP_RUN_LIMIT = 50


@dataclass(frozen=True)
class LearnResult:
    """Resultado de learn_from_work_item."""
    learned: bool
    lesson_written: bool
    golden_written: bool
    rev: int | None
    reason: str  # "ok"|"not_material"|"no_human_edit"|"already_learned"|"ado_unavailable"
    negative_goldens_written: int = 0   # Plan 81


def edit_to_lesson_content(delta, *, ado_id: int) -> str:
    """PURA. Construye texto de lección determinista a partir del EditDelta.

    Nunca incluye autor (C4 — sin PII). Truncado a _MAX_LESSON_CHARS.
    """
    lines = [f"El operador corrigió a mano la épica/issue (WI {ado_id}). Incorporá:"]
    for s in delta.added_snippets[:_MAX_BULLETS]:
        lines.append(f"- {s}")
    if delta.removed_snippets:
        lines.append("Evitá:")
        for s in delta.removed_snippets[:_MAX_BULLETS]:
            lines.append(f"- {s}")
    return "\n".join(lines)[:_MAX_LESSON_CHARS]


def _golden_available() -> bool:
    """True si el plan 56 (gate de regresión) está presente con su API viva.

    El plan 60 se escribió cuando el 56 NO existía y probaba un símbolo placeholder
    (`epic_gate.register_positive_golden`) que nunca llegó a existir -> el bridge
    quedaba muerto. El 56 ya está implementado en `harness.regression_goldens` con
    otra API (`derive_positive_golden` + `save_golden`): probamos ESA. Degrada limpio
    si falta.
    """
    try:
        from harness import regression_goldens
        return hasattr(regression_goldens, "derive_positive_golden") and hasattr(
            regression_goldens, "save_golden"
        )
    except Exception:
        return False


def _negative_golden_enabled() -> bool:
    """Plan 81 — lee STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED (default ON desde 2026-07-05,
    decisión explícita del operador) en call time."""
    import os
    return os.getenv("STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", "true").strip().lower() in ("1", "true", "on")


def learn_from_work_item(
    *,
    ado_id: int,
    baseline_html: str | None,
    baseline_rev: int | None,
    baseline_author: str | None,
    run_id: str | None,
    project_name: str | None,
    ado_client,
    service_identities: set[str],
) -> LearnResult:
    """Orquesta: leer revisiones ADO -> detectar edición humana -> diff -> lección -> ledger.

    Nunca propaga excepciones (degradación silenciosa con reason explícito).
    """
    from harness.ado_edit_detect import select_latest_human_edit
    from harness.ado_edit_diff import diff_edit
    from services import ado_edit_ledger, memory_store, pii_masker

    # 1. Leer revisiones de ADO
    try:
        revisions = ado_client.fetch_work_item_updates(ado_id)
    except Exception as exc:
        logger.warning("learn_from_work_item: fetch_work_item_updates falló para WI %s: %s", ado_id, exc)
        revisions = []

    if not revisions:
        return LearnResult(learned=False, lesson_written=False, golden_written=False,
                           rev=None, reason="ado_unavailable")

    # 2. Revisiones ya procesadas (para pasar a select_latest_human_edit)
    try:
        already_processed = ado_edit_ledger.processed_revs_for(ado_id)
    except Exception:
        already_processed = set()

    # 3. Detectar la edición humana más reciente no procesada
    he = select_latest_human_edit(
        revisions,
        baseline_rev=baseline_rev,
        baseline_author=baseline_author,
        service_identities=service_identities,
        already_processed_revs=already_processed,
    )

    if he is None:
        return LearnResult(learned=False, lesson_written=False, golden_written=False,
                           rev=None, reason="no_human_edit")

    # Doble barrera de idempotencia (por si processed_revs_for perdió algo)
    try:
        if ado_edit_ledger.already_learned(ado_id, he.rev):
            return LearnResult(learned=False, lesson_written=False, golden_written=False,
                               rev=he.rev, reason="already_learned")
    except Exception:
        pass

    # 4. Baseline: usar el HTML sellado en F1; si falta, '' (aún se aprende de added)
    effective_baseline = baseline_html or ""

    # 5. Diff puro (función pura, nunca lanza)
    delta = diff_edit(effective_baseline, he.edited_html)
    if not delta.is_material:
        return LearnResult(learned=False, lesson_written=False, golden_written=False,
                           rev=he.rev, reason="not_material")

    # 6. Materializar lección — C4: sin author/PII, pasa por pii_masker
    lesson_written = False
    try:
        raw_content = edit_to_lesson_content(delta, ado_id=ado_id)
        content = pii_masker.redact_irreversible(raw_content)
        memory_store.save_observation(
            project=project_name or "",
            type="operator_note",
            title=f"Edición humana en ADO (WI {ado_id})",
            content=content,
            topic_key=f"adoedit/wi-{ado_id}-rev-{he.rev}",
            status="active",
            scope="project",
            source_kind="operator",
            source_ado_id=ado_id,
            tags=["operator_note", "approval_condition", "ado_human_edit"],
        )
        lesson_written = True
    except Exception as exc:
        logger.warning("learn_from_work_item: save_observation falló para WI %s: %s", ado_id, exc)

    # 7. Golden positivo (plan 56) — la versión humana corregida pasa a ser baseline
    #    de calidad. Se guarda con LAS MISMAS keys que lee el gate de autopublish
    #    (api/tickets.py:6103-6107: agent_type="BusinessAgent", work_item_type="Epic"),
    #    si no el golden quedaría huérfano (nadie lo leería). Degrada limpio:
    #    derive_positive_golden devuelve None si el HTML no tiene heading RF que proteger.
    golden_written = False
    try:
        if _golden_available():
            from harness.regression_goldens import derive_positive_golden, save_golden
            g = derive_positive_golden(
                clean_html=he.edited_html,
                project=project_name,
                agent_type="BusinessAgent",
                work_item_type="Epic",
            )
            if g is not None:
                save_golden(g)
                golden_written = True
    except Exception as exc:
        logger.warning("learn_from_work_item: golden falló (no crítico) para WI %s: %s", ado_id, exc)

    # 7b. Goldens negativos (plan 81) — lo que el humano BORRÓ no debe reaparecer.
    #     MISMAS keys que lee el gate del autopublish (api/tickets.py:6513-6517):
    #     agent_type="BusinessAgent", work_item_type="Epic" — si no, el golden queda huérfano.
    negative_goldens_written = 0
    try:
        if _negative_golden_enabled() and _golden_available():
            from harness.regression_goldens import (
                derive_negative_goldens_from_removed,
                save_golden,
            )
            for g in derive_negative_goldens_from_removed(
                removed_snippets=delta.removed_snippets,
                edited_text=delta.edited_text,
                project=project_name,
                agent_type="BusinessAgent",
                work_item_type="Epic",
            ):
                save_golden(g)
                negative_goldens_written += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "learn_from_work_item: negative golden falló (no crítico) para WI %s: %s", ado_id, exc
        )

    # 8. Marcar ledger (idempotencia entre sweeps)
    try:
        ado_edit_ledger.mark_learned(ado_id, he.rev, run_id)
    except Exception as exc:
        logger.warning("learn_from_work_item: mark_learned falló para WI %s rev %s: %s", ado_id, he.rev, exc)

    return LearnResult(
        learned=True,
        lesson_written=lesson_written,
        golden_written=golden_written,
        rev=he.rev,
        reason="ok",
        negative_goldens_written=negative_goldens_written,
    )


def sweep_recent_runs(
    _db_runs=None,
    _ado_client_factory=None,
    _learn_fn=None,
) -> int:
    """Recorre runs recientes con epic_ado_id sellado y aprende de ediciones humanas.

    Parámetros de inyección (_db_runs, _ado_client_factory, _learn_fn) son para tests.
    En producción se usan None (valores reales del repo).

    Devuelve el número de lecciones nuevas en esta pasada.
    """
    import os, json

    if _learn_fn is None:
        _learn_fn = learn_from_work_item

    service_ids_csv = os.environ.get("STACKY_ADO_SERVICE_IDENTITY", "")
    try:
        from harness.ado_edit_detect import _service_identities as _parse_sids
        sids = _parse_sids(service_ids_csv)
    except Exception:
        sids = set()

    new_lessons = 0

    try:
        # En producción: leer runs de la DB viva
        if _db_runs is None:
            from models import Execution, session_scope
            with session_scope() as db:
                raw_runs = (
                    db.query(Execution)
                    .order_by(Execution.id.desc())
                    .limit(_SWEEP_RUN_LIMIT)
                    .all()
                )
        else:
            raw_runs = _db_runs

        for run in raw_runs:
            try:
                meta = (
                    run.metadata
                    if isinstance(run.metadata, dict)
                    else json.loads(run.metadata or "{}")
                )
            except Exception:
                meta = {}

            ado_id = meta.get("epic_ado_id") or meta.get("issue_ado_id")
            if not ado_id:
                continue

            try:
                if _ado_client_factory is not None:
                    ado = _ado_client_factory(meta.get("project_name"))
                else:
                    from services.ado_client import AdoClient
                    from project_manager import get_active_tracker_config
                    cfg = get_active_tracker_config(project_name=meta.get("project_name"))
                    ado = AdoClient(cfg)

                res = _learn_fn(
                    ado_id=int(ado_id),
                    baseline_html=meta.get("epic_baseline_html"),
                    baseline_rev=meta.get("epic_baseline_rev"),
                    baseline_author=None,
                    run_id=str(run.id),
                    project_name=meta.get("project_name"),
                    ado_client=ado,
                    service_identities=sids,
                )
                if res.learned:
                    new_lessons += 1
                    logger.info(
                        "ado edit learning: WI %s rev %s => lección nueva (run %s, neg_goldens=%s)",
                        ado_id, res.rev, run.id, res.negative_goldens_written,
                    )
            except Exception as exc:
                logger.warning("sweep_recent_runs: error en WI %s (no crítico): %s", ado_id, exc)

    except Exception as exc:
        logger.warning("sweep_recent_runs: error general: %s", exc)

    return new_lessons
