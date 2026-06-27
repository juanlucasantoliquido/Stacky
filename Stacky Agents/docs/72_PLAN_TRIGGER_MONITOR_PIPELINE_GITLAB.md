# Plan 72 — Trigger y monitoreo de pipelines GitLab CI

> Estado: BOCETO (pendiente formalizar con proponer-plan-stacky cuando Plan 71 esté implementado).
> Bloque roadmap: GitLab-Main 70-76 (eslabón 3, Boost).
> Depende de: Plan 71 (pipeline-infer tracker-agnóstico).
> Versión: boceto v0.

## 1. Objetivo + KPI
Que Stacky pueda **disparar** (trigger) y **monitorear** pipelines CI en GitLab — capacidad que ADO no tenía fácil — desde la UI, con confirmación explícita del operador (HITL) y visualización de status.

**KPI:** el operador puede, desde la UI de Stacky, disparar un pipeline sobre un `ref` (branch/SHA) de un proyecto GitLab y ver su status en tiempo real, sin salir de Stacky ni usar `git push` manual.

## 2. Por qué / gap que cierra
- `gitlab_provider.py:432` solo lista (`fetch_pipelines`) e infiere (`infer_pipeline`); **no existe** `trigger_pipeline` ni `retry_pipeline` en el adapter.
- ADO no exponía un trigger de pipeline cómodo desde el backend de Stacky (requería API REST de Azure Pipelines con scopes separados); GitLab lo permite con un POST `/projects/:id/pipeline` scope `api`.
- Hoy, para correr CI de un ítem GitLab desde Stacky, el operador debe ir a la web de GitLab: fricción que rompe el centauro.
- Plan 71 deja el puerto de CI listo; este plan **consume** ese puerto en modo escritura.

## 3. Fases (alto nivel)
- **F0** — Extender el adapter GitLab con `trigger_pipeline(ref)` y `poll_pipeline(pipeline_id)` (POST + GET sobre `/projects/:id/pipeline[s]/...`).
- **F1** — Método puerto `CIProvider.trigger_pipeline` + `poll_pipeline` (o extender `TrackerProvider` según decisión del Plan 71).
- **F2** — Endpoint API backend `POST /api/ci/{project}/trigger` con validación de `ref`, idempotencia (no disparar 2x el mismo SHA en ventana de N segundos) y rate-limit.
- **F3** — UI: botón "Disparar pipeline" en la card del ítem con modal de confirmación (HITL), muestra `pipeline_id` + `web_url` + estado.
- **F4** — Monitoreo: polling del status (reutilizar el watcher existente de ejecuciones) con cancelación; notificación al operador (toast) en success/failure.
- **F5** — Ratchet + tests de permisos/scope del PAT.

## 4. Supuestos clave a verificar al formalizar
- **CRÍTICO:** confirmar que el token GitLab del `client_profile` tiene scope `api` (no solo `read_api`); si no, trigger falla con 403 y el operador no sabrá por qué. Validar mensaje de error claro + guía en UI.
- Verificar si GitLab Cloud vs self-hosted tienen límites de rate distinto para `POST /pipeline` (afecta idempotencia de F2).
- Confirmar el contract del `ref`: ¿branch name, SHA, o ambos? GitLab acepta branch o tag; SHA requiere `commits/:sha/pipelines`.
- Decidir política de re-trigger: ¿permitir disparar sobre un SHA con pipeline en progreso? (riesgo: pipelines duplicados).
- Verificar si el watcher de ejecuciones existente es reutilizable o requiere un watcher de pipelines aparte (F4).

## 5. Dependencias y bloqueos
- **Plan 71 DEBE estar implementado**: define el puerto `CIProvider` (o método en `TrackerProvider`) sobre el que este plan escribe.
- No depende de 73/74/75.

## 6. Riesgos principales
- **R1 — Trigger silencioso fallido por scope.** Mitigación: F0 valida scopes del token al inicializar el provider y surfacea el error en la UI antes del trigger.
- **R2 — Pipelines duplicados.** Mitigación: idempotencia por SHA+ventana en F2; UI bloquea el botón mientras hay uno en progreso.
- **R3 — Polling agrega carga al GitLab.** Mitigación: backoff exponencial + cancelación al cerrar la UI; cap de concurrencia.
- **R4 — Trigger automático sin HITL.** Mitigación: riel duro; el botón siempre muestra modal de confirmación; nunca auto-disparar desde un agente.

## 7. Fuera de scope
- Generar pipelines YAML declarativos (Plan 73).
- Migración ADO→GitLab (Plan 74).
- Deep links (Plan 75) — se reusa la URL devuelta pero la composición visual profunda es del 75.

## 8. Rieles duros heredados
3 runtimes (cambio solo backend+UI, no toca prompts) / cero trabajo operador (flag `STACKY_CI_TRIGGER_ENABLED` default OFF, editable UI) / HITL innegociable en el trigger / mono-operador sin auth / TDD + funciones puras + ratchet / backward-compatible.

## 9. Próximo paso
`proponer-plan-stacky` → `criticar-y-mejorar-plan` → `implementar-plan-stacky`.
