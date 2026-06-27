# Plan 73 — Generador declarativo de pipelines ADO ↔ GitLab

> Estado: BOCETO (pendiente formalizar con proponer-plan-stacky cuando Plan 72 esté implementado y Plan 74 también — este plan se hace DESPUÉS de 74).
> Bloque roadmap: GitLab-Main 70-76 (eslabón 4, game-changer).
> Depende de: Plan 72 (trigger/monitor) y Plan 74 (migrador, que estresa el contract del `PipelineSpec`).
> Versión: boceto v0.

## 1. Objetivo + KPI
Un `PipelineSpec` (dataclass puro, tracker-agnóstico) que se **renderiza** a YAML ADO (`azure-pipelines.yml`) o `.gitlab-ci.yml`, con validación determinista, y se **commitea** vía la API del tracker. Hace que crear/migrar un pipeline sea trivial y robusto desde Stacky.

**KPI:** el operador describe un pipeline una vez en Stacky (UI o YAML del spec) y obtiene YAML válido para ADO y GitLab, commiteado en el repo correcto, idempotente.

## 2. Por qué / gap que cierra
- Hoy los pipelines se escriben a mano en YAML ADO o GitLab, duplicando conocimiento y sin validación hasta runtime.
- Migrar pipelines ADO↔GitLab a mano es el trabajo más tedioso y error-prone del roadmap GitLab.
- No existe en Stacky un modelo de pipeline independiente del tracker; los planes 71/72 sólo consumen CI pre-existente.
- Un `PipelineSpec` puro permite validación determinista (schema), diff/preview, y es reutilizable por el Plan 74 (migrador) como contract compartido.

## 3. Fases (alto nivel)
- **F0** — Diseñar `PipelineSpec` (dataclass puro): stages, jobs, steps, variables, triggers, runner tags. Sin dependencias de ADO ni GitLab.
- **F1** — Renderer `to_ado_yaml(spec) -> str` (pure function) — sintaxis `azure-pipelines.yml`.
- **F2** — Renderer `to_gitlab_yaml(spec) -> str` (pure function) — sintaxis `.gitlab-ci.yml`.
- **F3** — Validador determinista `validate(spec) -> list[ValidationError]` (schema, sin LLM).
- **F4** — Commitear vía API del tracker: `provider.commit_file(path, content, branch, message)` — método puerto nuevo.
- **F5** — UI: editor del spec + preview YAML lado-a-lado (ADO | GitLab) + botón "Commitear" con confirmación HITL.
- **F6** — Round-trip test: spec → YAML → parse → spec (idempotencia semántica) + ratchet.

## 4. Supuestos clave a verificar al formalizar
- **CRÍTICO:** definir el subset de features de pipeline que `PipelineSpec` cubre. ADO y GitLab tienen capacidades no equivalentes (templates ADO, `extends:`/`include:` GitLab, environments, artifacts, services, matrix strategy). Un spec minimalista cubre 80% pero hay que decidir qué cae fuera.
- Verificar si ya existe un parser YAML ADO/GitLab en el repo para no reescribir (F6 round-trip) — probable no.
- Confirmar el método puerto para commitear archivos: ¿existe `commit_file` en `TrackerProvider`? (hoy hay `comment_exists`, `fetch_*`, pero commit de archivo al repo es nuevo — verificar en `PORT_METHODS`).
- Decidir rama/branch por defecto para commitear (¿feature branch con MR, o directo a default?).
- Validar que el operador quiere commits directos vs MR/PR (HITL fuerte).

## 5. Dependencias y bloqueos
- **Plan 72** debe estar implementado: el trigger/monitor consume el YAML generado aquí; hacerlo antes invalidaría la prueba end-to-end.
- **Plan 74 se hace ANTES**: el migrador estresa el `PipelineSpec` (convierte pipelines ADO reales → spec → GitLab), revelando gaps del subset antes de que este plan se formalice. El contract del spec madura con 74.
- Depende transitivamente de 70 (puerto base).

## 6. Riesgos principales
- **R1 — Subset demasiado chico o demasiado grande.** Mitigación: F0 explicita la matriz de features soportadas; fuera de scope va a YAML crudo (escape hatch).
- **R2 — Commitear al repo default sin guard.** Mitigación: HITL + default a feature branch + MR.
- **R3 — Renderers que divergen silenciosamente (ADO válido, GitLab roto).** Mitigación: F6 round-trip + CI en ambos trackers en el plan completo.
- **R4 — Spec creep (parsear TODO ADO/GitLab).** Mitigación: fuera de scope explícito en sección 7.

## 7. Fuera de schema
- Parseo inverso YAML → spec para pipelines arbitrarios (sólo se hace en 74 como Input).
- Soporte de templates/herencia compleja ADO en F0 (queda como "YAML crudo" escape hatch).
- Ejecución local de pipelines.
- Validación contra runner real (sólo validación de schema determinista).

## 8. Rieles duros heredados
3 runtimes (no toca prompts) / cero trabajo operador (flag `STACKY_PIPELINE_GENERATOR_ENABLED` default OFF, UI) / HITL en todo commit / mono-operador sin auth / TDD + funciones puras (renderers y validador son puros) + ratchet / backward-compatible.

## 9. Próximo paso
`proponer-plan-stacky` (después de 72 y 74) → `criticar-y-mejorar-plan` → `implementar-plan-stacky`.
