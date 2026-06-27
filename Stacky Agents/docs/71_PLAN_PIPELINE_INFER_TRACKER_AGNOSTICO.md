# Plan 71 — Pipeline-infer tracker-agnóstico

> Estado: BOCETO (pendiente formalizar con proponer-plan-stacky cuando Plan 70 esté implementado).
> Bloque roadmap: GitLab-Main 70-76 (eslabón 2).
> Depende de: Plan 70 (consumers migrados al puerto `TrackerProvider`).
> Versión: boceto v0.

## 1. Objetivo + KPI
Unificar la inferencia de pipeline de un ítem detrás del puerto `TrackerProvider` (o un sub-puerto de CI), de modo que deja de ser ADO-only. GitLab ya expone `fetch_pipelines`/`infer_pipeline` hoy desconectados.

**KPI:** un proyecto `issue_tracker.type=gitlab` con `STACKY_GITLAB_ENABLED=true` devuelve estado de pipeline para un ítem sin construir `AdoClient` ni invocar `ado_pipeline_inference.infer_pipeline` en ningún punto del path.

## 2. Por qué / gap que cierra
- `services/pipeline_status.py:40` define `_COMMENT_PATTERNS` y `PIPELINE_STAGES` sobre texto HTML de comentarios **ADO** (regex `RF-\d{3}`, `ANÁLISIS TÉCNICO — ADO-`); la fuente `source="ado_comment"` (pipeline_status.py:177) está hardcodeada a ADO.
- `services/ado_pipeline_inference.py:319` `infer_pipeline(ado_id, ...)` toma `ado_id: int` y usa `INFERENCE_MODEL` (gpt-4o-mini) — contract ADO-específico, no portátil a GitLab que usa `ref`/`sha`.
- `services/gitlab_provider.py:432` `fetch_pipelines(ref)` y `gitlab_provider.py:458` `infer_pipeline(ref)` **ya existen** y devuelven `{source:"ci"|"llm", status, ref, sha, web_url}`, pero el comentario de l.472-474 admite que el consumer superior puede escalar — hoy **nadie los invoca** desde el flujo principal.
- Resultado: la inferencia de pipeline está particionada; un ítem GitLab no tiene visibilidad de CI desde Stacky.

## 3. Fases (alto nivel)
- **F0** — Inventario: mapear callers de `pipeline_status.*` y `ado_pipeline_inference.infer_pipeline`; clasificar ADO-acoplados.
- **F1** — Decisión de puerto: extender `TrackerProvider` con método `infer_item_pipeline(item_id, ref?)` O definir sub-puerto `CIProvider` separado (documentar trade-off).
- **F2** — Adapter ADO: envuelve `ado_pipeline_inference` existente (sin romperla) detrás del método puerto.
- **F3** — Adapter GitLab: cablea `gitlab_provider.fetch_pipelines/infer_pipeline` al método puerto.
- **F4** — Migración de callers (los de F0) al puerto; flag opt-in default OFF.
- **F5** — UI/observabilidad: fuente `source` y `tracker_type` en el reporte; ratchet.

## 4. Supuestos clave a verificar al formalizar
- **CRÍTICO:** confirmar que `_COMMENT_PATTERNS` (pipeline_status.py:40) es aplicable tal cual a comentarios GitLab Markdown, o requiere patrones distintos (GitLab no tiene `RF-\d{3}` necesariamente). Define si F1 extiende el puerto con `infer_item_pipeline` que normaliza o si cada adapter interpreta patrones.
- Verificar si `ado_pipeline_inference` cachea en BD local con clave `ado_id` — un ítem GitLab no tiene `ado_id`; la caché necesita clave agnóstica (`tracker_type + item_id + ref`).
- Verificar el contrato real de `PipelineInferenceResult` (campos) vs el dict que devuelve GitLab — F2/F3 necesitan normalización.
- Confirmar que `fetch_pipelines` GitLab no requiere permisos adicionales que el PAT actual del client_profile no tenga (scope `read_api`).
- Decidir si el sub-puerto `CIProvider` merece existir o se sobrecarga `TrackerProvider` (principio ISP).

## 5. Dependencias y bloqueos
- **Plan 70 DEBE estar implementado primero**: los callers viven en `api/tickets.py` y capas de servicios que 70 migra al puerto. Sin 70, migrar la inferencia es paralelo al mismo acoplamiento.
- No depende de 72-76.

## 6. Riesgos principales
- **R1 — Patrones ADO no trasladables a GitLab.** Mitigación: F0 explicita qué patrones son ADO-específicos; cada adapter aporta los suyos o un fallback.
- **R2 — Caché con clave ADO-acoplada.** Mitigación: rediseñar la clave en F2/F3 antes de migrar callers.
- **R3 — Falso verde "GitLab devuelve pipeline unknown".** Mitigación: F5 requiere que `source="ci"` se observe al menos una vez en un proyecto GitLab real con pipelines antes de dar verde.
- **R4 — Scope creep hacia trigger/monitor (Plan 72).** Mitigación: este plan es solo-lectura; trigger queda en 72.

## 7. Fuera de scope
- Disparar/monitorear pipelines (Plan 72).
- Generar pipelines declarativos (Plan 73).
- Migración ADO→GitLab (Plan 74).
- Deep links a pipelines (Plan 75).

## 8. Rieles duros heredados
3 runtimes sin tocar / cero trabajo operador (flag `STACKY_PIPELINE_PROVIDER_ENABLED` default OFF, editable por UI) / HITL / mono-operador sin auth / TDD + funciones puras + ratchet / backward-compatible (flag OFF = byte-idéntico).

## 9. Próximo paso
`proponer-plan-stacky` → `criticar-y-mejorar-plan` → `implementar-plan-stacky`.
