# Plan 74 — Migrador ADO → GitLab seguro e idempotente

> Estado: BOCETO (pendiente formalizar con proponer-plan-stacky cuando Plan 70 esté implementado).
> Bloque roadmap: GitLab-Main 70-76 (eslabón 5, Grande).
> Depende de: Plan 70 (paridad de consumers cerrada con el puerto `TrackerProvider`).
> Versión: boceto v0.

## 1. Objetivo + KPI
Migrar **todo** el contenido de un proyecto ADO a GitLab — épicas, issues, tasks, comentarios, attachments, links — de forma segura (read-only sobre el origen), idempotente (re-corrible sin duplicar) y trazable (reporte de mapeo ADO-id ↔ GitLab-id).

**KPI:** dado un proyecto ADO de origen y un proyecto GitLab de destino, el operador ejecuta una migración dry-run, revisa el reporte, y dispara la migración real obteniendo un mapeo 1:1 verificable; re-correr el migrador no crea duplicados.

## 2. Por qué / gap que cierra
- Hoy migrar de ADO a GitLab es manual y error-prone: cada tipo de ítem se recrea a mano, los comentarios se pierden, los attachments no se migran, los links se rompen.
- Plan 65 construyó el puerto con `comment_exists(item_id, marker) -> bool` (gitlab_provider.py:262, ado_provider.py:95) — **marker de idempotencia ya existe** y es la clave para re-correcciones seguras.
- Plan 70 cierra la paridad de consumers: el migrador puede escribir por el mismo puerto por el que ya se lee, sin acoplarse a `AdoClient`.
- Sin este plan, el roadmap GitLab queda en "convivencia" pero nunca en "migración real" — el operador no puede abandonar ADO.

## 3. Fases (alto nivel)
- **F0** — Inventario de tipos a migrar: épica, issue, task, comentario, attachment, link (parent/child/related). Tabla origen ADO → destino GitLab.
- **F1** — Estrategia de mapeo de IDs: tabla persistente `ado_id ↔ gitlab_iid/id` (BD local o archivo versionado); consulta barata para re-corridas.
- **F2** — Extracción ADO read-only: usar el puerto (`fetch_*`) para leer TODO el origen sin escribir nunca en ADO.
- **F3** — Escritura GitLab idempotente: para cada ítem, `comment_exists(marker)` antes de crear; si existe, skip (o actualizar según política).
- **F4** — Migración de attachments: descarga binaria desde ADO, subida a GitLab (adjunto al issue o como link); respetar tamaño máximo.
- **F5** — Migración de links: reconstruir parent/child re-apuntando IDs al mapeo de F1; los links a IDs no migrados se reportan como warnings.
- **F6** — Dry-run mode: genera el reporte completo sin escribir nada; verificación post-migración (re-leer destino y comparar counts).
- **F7** — UI: wizard de migración (origen, destino, dry-run, reporte, confirmación HITL, ejecución, progreso, mapeo final descargable).
- **F8** — Ratchet + tests de idempotencia (correr 2x = sin duplicados).

## 4. Supuestos clave a verificar al formalizar
- **CRÍTICO:** confirmar el mapping de tipos de work item ADO → tipo de issue GitLab. ADO tiene `Epic`/`Feature`/`User Story`/`Task`/`Bug`; GitLab tiene `issue` + `epic` (sólo en Premium+). Verificar qué tier de GitLab tiene el destino; si es Free, las épicas ADO se degradan a labels o a issues.
- Verificar límites del API GitLab para attachments (tamaño máximo, tipos permitidos) — F4.
- Confirmar si `comment_exists` del puerto es suficiente como marker idempotente o hace falta un marker dedicado (ej. custom field o label `migrated-from-ado:<id>`).
- Decidir política de resolución de conflictos: si un ítem GitLab ya existe y NO tiene marker pero el contenido difiere, ¿se sobrescribe, se skip, se reporta?
- Verificar preservación de metadatos (autor original, fecha original) — GitLab permite `created_at`/`author_id` vía API? (restringido en self-managed vs SaaS).

## 5. Dependencias y bloqueos
- **Plan 70 DEBE estar implementado primero**: el migrador escribe por el puerto `TrackerProvider`; sin 70, escribiría acoplado a `AdoClient`/GitLab separadamente.
- **No** depende de 71/72/75 (puede correr en paralelo a 71). Se hace **ANTES** que 73 (el migrador estresa el `PipelineSpec` para pipelines).

## 6. Riesgos principales
- **R1 — Pérdida de datos en attachments.** Mitigación: F4 verifica hash post-subida; reintentos; reporte de fallidos.
- **R2 — Duplicados por idempotencia rota.** Mitigación: marker obligatorio en cada item creado; F8 corre 2x y asume verde sólo si count destino es estable.
- **R3 — Migración parcial silenciosa.** Mitigación: F6 verificación post cuenta diffs por tipo; abortar si gap > 0 con reporte.
- **R4 — Escritura accidental en ADO (origen).** Mitigación: F2 es estrictamente read-only; tests de que ningún método `create_*`/`update_*` se invoque sobre el provider origen.

## 7. Fuera de scope
- Migración inversa GitLab → ADO.
- Migración de pipelines (eso estresa el `PipelineSpec` del Plan 73 pero NO es el foco de 74; los pipelines se listan en el reporte pero su conversión se hace con 73).
- Migración de historial Git (los commits viajan con el repo, no con work items).
- Sincronización continua bidireccional (esto es una migración one-shot idempotente, no un espejo).

## 8. Rieles duros heredados
3 runtimes (no toca prompts) / cero trabajo operador (flag `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED` default OFF, UI) / HITL innegociable (dry-run obligatorio antes de escritura) / mono-operador sin auth (tokens en client_profile) / TDD + funciones puras (mapeo y verificación son puros) + ratchet / backward-compatible / **read-only sobre origen** es riel absoluto.

## 9. Próximo paso
`proponer-plan-stacky` (después de 70) → `criticar-y-mejorar-plan` → `implementar-plan-stacky`.
