# Plan 75 — Deep links bidireccionales GitLab

> Estado: BOCETO (pendiente formalizar con proponer-plan-stacky cuando Plan 70 esté implementado).
> Bloque roadmap: GitLab-Main 70-76 (eslabón 6, Boost).
> Depende de: Plan 70 (puerto `TrackerProvider` con `item_url`).
> Versión: boceto v0.

## 1. Objetivo + KPI
Componer URLs profundas (deep links) GitLab en la UI de Stacky — épica ↔ MR ↔ pipeline ↔ issue ↔ commit — reutilizando el patrón de deep links ADO ya existente.

**KPI:** en la UI de un proyecto `issue_tracker.type=gitlab`, toda card/relación de un ítem muestra el deep link clickeable al recurso correcto en GitLab, sin construcción manual de URLs.

## 2. Por qué / gap que cierra
- Hoy los deep links en la UI están construidos para ADO (`work_item_url`, etc. — ver Plan 70 F0 tabla fila 7: `provider.item_url(item_id)`).
- `gitlab_provider` devuelve `web_url` ya armado en `fetch_pipelines` (gitlab_provider.py:449), pero los deep links a issues/MRs/epics no están compuestos en la capa de UI.
- Sin deep links, el operador copia-pega IDs entre Stacky y GitLab: fricción alta, rompe el flujo centauro.
- Es un Boost: poco código, mucho valor de UX.

## 3. Fases (alto nivel)
- **F0** — Inventario de links necesarios: issue, epic, MR, pipeline, commit, blob/archivo.
- **F1** — Helper puro `gitlab_deep_link(kind, project_path, id) -> str` (URL builder, sin I/O).
- **F2** — Método puerto `item_url(item_id)` ya existe para ADO (Plan 70); verificar cobertura GitLab (issue_url, mr_url, pipeline_url, commit_url) — extender si hace falta.
- **F3** — UI: componentes `DeepLink`/`ExternalLink` reutilizables en cards (épica, issue, task, ejecución con pipeline).
- **F4** — Composición bidireccional: desde una épica, links a sus MRs/pipelines relacionados; desde un pipeline, link al issue que lo disparó.
- **F5** — Ratchet + tests de que los URLs son válidos (schema + path).

## 4. Supuestos clave a verificar al formalizar
- **CRÍTICO:** confirmar el `project_path` canónico que usa GitLab (URL-encoded `namespace/project`) — `gitlab_provider` ya lo maneja vía `_client._project_path()`; reusar ese helper y no recalcular.
- Verificar el formato de URL de cada recurso en la versión self-hosted vs SaaS de GitLab (¿mismo path?).
- Confirmar que los deep links a épicas requieren GitLab Premium+ (las épicas no existen en Free) — fallback a label/search link.
- Decidir si los links abren en tab nueva (target=_blank con `rel="noopener"`) — seguridad.

## 5. Dependencias y bloqueos
- **Plan 70 DEBE estar implementado primero**: el puerto `item_url` ya estandarizado es la base; este plan extiende para GitLab.
- Es **paralelo** a 71/72/73/74 — puede formalizarse y ejecutarse en cualquier momento tras 70.

## 6. Riesgos principales
- **R1 — URLs rotas en self-hosted con subpath.** Mitigación: F1 usa el `web_url` devuelto por el provider cuando existe (fuente de verdad), no recorta/compone a mano salvo para sub-recursos.
- **R2 — Link a épica en GitLab Free.** Mitigación: F4 detecta tier o provee fallback.
- **R3 — Injection por `project_path` malicioso.** Mitigación: helpers puramente URL-encodean inputs; tests de boundary.

## 7. Fuera de schema
- Embeber el contenido del recurso en Stacky (sólo linkeamos).
- Notificaciones push al recurso externo.
- Links a merge request diffs o comentarios puntuales (se agrega después si hay demanda).

## 8. Rieles duros heredados
3 runtimes (cambio UI+helper puro, no toca prompts) / cero trabajo operador (default ON para proyectos gitlab; sin flag nueva — reusa `STACKY_GITLAB_ENABLED`) / HITL (sólo son links clickeables) / mono-operador / TDD + helper puro + ratchet / backward-compatible (ADO links se preservan).

## 9. Próximo paso
`proponer-plan-stacky` → `criticar-y-mejorar-plan` → `implementar-plan-stacky`.
