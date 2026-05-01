---
name: Contratos de los módulos de observabilidad F1-F4
description: Firmas canónicas de estimation_store, pipeline_events, ticket_scoring, sse_bus para referencia rápida.
type: reference
---

Firmas de los módulos F1-F4 en Stacky (confirmadas al 2026-04-21, verificar con Read antes de usar si pasa mucho tiempo):

**`estimation_store`**
- `record_estimate(ticket_id, scoring, *, project=None, created_at=None) -> dict`
- `record_actual(ticket_id, *, actual_minutes=None, per_stage_actual=None, rework_cycles=None, corrections_sent=None, first_attempt_approved=None, closed_at=None) -> dict | None`  ← OJO: `per_stage_actual`, no `per_stage`.
- `get_entry(ticket_id) -> dict | None`
- `maybe_close_from_state(ticket_id, state_entry) -> bool`
- `list_entries(*, project=None, days=None, closed_only=False) -> list[dict]`
- `compute_accuracy(*, days=30, project=None) -> dict`
- `suggest_delta_calibration(*, min_samples=20, project=None, days=90) -> dict`
- `apply_calibration(*, global_delta_pct=None, project_deltas=None) -> dict`  ← OJO: no usa `scope=`, separa en 2 parámetros.
- `load_calibration() -> dict`

**`pipeline_events`**
- `emit(*, kind, execution_id=None, parent_execution_id=None, ticket_id=None, project=None, action=None, subaction=None, phase=None, pct=None, duration_ms=None, error_kind=None, message=None, user_friendly=None, stack=None, detail=None, correlation=None, ts=None) -> PipelineEvent | None`
- `read_events(*, ticket_id=None, kind=None, since=None, limit=500, days_back=7) -> list[dict]`  ← OJO: `kind` singular, no `kinds`.
- `subscribe(maxsize=200) -> Queue`
- `unsubscribe(q) -> None`
- `new_execution_id() -> str` (UUID4 completo)
- EventKinds: `action_started|action_progress|action_done|action_error|notification|state_transition|estimation_recorded|estimation_actualized`
- EventPhases: `pm|dev|tester|dba|tl|deploy|sync|other`
- ErrorKinds: `technical|functional|auth|network|data|user`

**`ticket_scoring`**
- `compute_scoring(inc_content, *, project=None, ticket_type=None, work_item_id=0, scorer=None, global_calibration=None) -> TicketScoring`
- `read_incident_content(ticket_folder, ticket_id=None) -> str`
- `load_scoring_config(project_name=None) -> dict`  (merge: defaults ← config.json.scoring_defaults ← projects/<P>/config.json.scoring)
- `resolve_delta_pct(cfg, *, ticket_type=None, project=None, global_calibration=None) -> (float, source)`
- `TicketScoring` incluye `estimation_method ∈ {"heuristic","regression"}` — qué motor produjo la estimación.
- Fórmula Fase 1 (heurística): est = base_minutes × module_factor × (0.5+score/100×1.5) × (1+unc/100×k_unc) × (1+fr/100×k_fr) × (1+ext/100×k_ext) × (1+files/100×k_files) × (1+delta/100). Todos los coefs viven en `scoring_defaults.multipliers` + `scoring_defaults.base_minutes`.

**`estimation_model`** (Fase 2 — regresión lineal en Python puro, sin numpy)
- `train_model(store_path=None, *, min_samples=20) -> ModelStats | None`
- `predict(factors, similar_count) -> int | None`  (None si no hay modelo entrenado o incompatible)
- `load_model() -> dict | None` / `save_model(stats)`
- `maybe_retrain_after_close(n_closed_samples) -> bool` — dispara si `n ≥ 20 and n % 5 == 0`. Lo invoca `estimation_store.record_actual` como hook best-effort.
- `FEATURE_ORDER`: `(tech_complexity, uncertainty, impact, files_affected, functional_risk, external_dep, similar_tickets_count)` — NO CAMBIAR sin migrar el modelo persistido.
- Persistencia en `data/estimation_model.json`; ridge λ=1e-3 para evitar singularidad.

**`action_tracker`**
- `ActionContext(action, *, ticket_id=None, project=None, phase=None, parent_execution_id=None, execution_id=None, correlation=None, ticket_folder=None)`
- `current_execution_id() -> str | None` (desde ContextVar)
- `@track_action(action, *, phase=None, ticket_id_arg=, project_arg=, folder_arg=)` decorator
- El tracker NUNCA propaga errores al caller — todo emit es try/except silencioso.

**`sse_bus`**
- `event_stream(*, last_event_id=None, ticket_id=None, kind_filter=None, max_seconds=None) -> Generator[str]` (apto para Flask Response mimetype='text/event-stream')
- `format_sse(event_id, kind, data) -> str` (puro, para tests)

**`stacky_log.slog`** (en `_StackyLogger`)
- `action(exec_id, ticket_id, action, phase="", detail="", pct=None)` — log estructurado de acción.
- `error_classified(exec_id, ticket_id, action, kind, exc, user_friendly="")` — log ERROR corto + stack a DEBUG.
