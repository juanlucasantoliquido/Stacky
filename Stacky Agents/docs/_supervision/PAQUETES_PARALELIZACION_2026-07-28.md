# Censo de planes pendientes y paquetes de paralelización — 2026-07-28

**Autor:** StackyArchitectaUltraEficientCode · **Tipo:** inventario + empaquetado (NO implementa nada)
**Base:** rama `feat/plan-217-migrador-mantis-gitlab` @ `77abb7c2` · 213 commits por delante de `main`, 26 por delante de `origin`
**Worktrees:** UNO solo (`C:/desarrollo/GIT/RS/STACKY/Stacky` = `N:/GIT/RS/STACKY/Stacky`, mismo árbol). **No hay aislamiento hoy.**
**Layout real verificado:** el código NO cuelga de la raíz. Es `Stacky Agents/backend/…` y `Stacky Agents/frontend/src/…`.
**venv:** `Stacky Agents/backend/venv/Scripts/python.exe` (py3.13).

---

## 0. Resumen ejecutivo (leer esto primero)

| Métrica | Valor |
|---|---|
| Documentos `<NNN>_PLAN_*.md` en `Stacky Agents/docs/` | **143** (100 → 271, con huecos) |
| IMPLEMENTADOS / META / OBSOLETOS (nada que hacer) | **130** |
| Con trabajo pendiente REAL | **13** |
| De esos 13, **implementables hoy** (última crítica no los rechazó) | **2** → planes **242 (recortado)** y **116 F4** |
| De esos 13, **bloqueados por crítica RECHAZADA** | **11** → 259, 260, 263, 264, 265, 266, 267, 268, 269, 270, 271 |
| Continuaciones **declaradas pero SIN documento** | **2** → plan **244** (=243 F4..F9) y plan **245** (=242 F3..F9) |
| Paquetes propuestos | **8** (P0 costura + P1..P7) |
| Agentes en paralelo REALES hoy | **2** (OLA 1) |
| Agentes en paralelo si el operador desbloquea los 11 | **6** (OLA 2), tras 1 agente de costura secuencial |

**Hallazgo que gobierna todo el diseño:** los 12 planes con trabajo pendiente declaran flags `STACKY_*` nuevas, y **una flag toca los MISMOS 7 archivos compartidos, siempre**. Medido —no supuesto— sobre los `git show --stat` de `0b38da29` (plan 258) y `c077c743` (plan 253). Con un único working tree y sin worktrees, **dos agentes que declaren flags se pisan sí o sí**. La paralelización solo funciona si esos 7 archivos se escriben UNA vez, por UN agente, ANTES del fan-out (paquete **P0**).

---

## 1. Censo

### 1.1 Método y confianza

Prioridad de evidencia, de más fuerte a más débil:

1. **Existencia del símbolo/archivo que el plan promete crear** (`ls` / `Grep` sobre el árbol real).
2. **Existencia de `backend/tests/test_plan<NNN>_*.py`** — convención estable del repo; si el plan se construyó, sus tests existen.
3. **Commit `feat|fix|test(plan-NNN)`** en `git log`.
4. Ledger `_supervision/ledger.json` (47 entradas, 40 `APROBADO` + 6 `TERMINADO-POR-SUPERVISOR` + 1 `INCOMPLETO`).

**El header `**Estado:**` del propio doc NO se usó como evidencia: miente.** Los 7 planes 246-252 dicen "CRITICADO v2" y están construidos (`feat(plan-246..252): F0..F5/F6 implementadas` + 30 archivos `test_plan24X_*.py`). Los 4 planes UX 185/187/192/194 dicen "CRITICADO v2" y entraron por el merge `35651bcb`. El header del 171 también quedó stale respecto de `380e141e`.

### 1.2 Bloques SIN trabajo pendiente (verificados, no se auditan más)

| Rango | Estado | Evidencia |
|---|---|---|
| **100, 101** | ❌ OBSOLETO / NO IMPLEMENTAR | header literal del doc: `**Estado:** ❌ **OBSOLETO / SUPERADO — NO IMPLEMENTAR**`, veredicto de vigencia 2026-07-26 |
| **102, 103** | IMPLEMENTADO | `test_plan102_*.py`, `test_plan103_*.py` + 1 commit impl c/u |
| **104-115, 117, 119-121** | IMPLEMENTADO | símbolos verificados uno a uno: `api/devops_section_doctor.py:108`, `services/remote_exec.py`, `services/environment_init.py::validate_sandbox_override`, `services/doc_graph.py::classify_doc_health`, `services/docs_rag.py:491::search_hybrid`, `services/doc_staleness.py:56::annotate_staleness`, `services/lexical_core.py:61`, `services/local_insights.py:352`, `services/egress_sentinel.py:260`, `services/deploy_planner.py` |
| **118** | NO EXISTE | renumerado a 119 (`1652f72a` "quitar 118_PLAN residual") |
| **122-139** | IMPLEMENTADO (18/18) | `services/dbcompare_{registry,snapshot,diff,runs,engine,scripts,data}.py`; `api/plans_board.py`; `scripts/check_code_integrity.py`; `api/incidents.py`; `services/agent_contract.py:44`; `components/ui/` completo; `components/shell/` + `test_plan139_shell_flag.py` |
| **140-160** | APROBADO en ledger | 20 entradas con hash del doc — no se re-auditan (155 no existe) |
| **161-175** | IMPLEMENTADO (15/15) | `services/format.ts`, `components/ui/Dialog.tsx`, `services/routes.ts`, `services/incident_store.py`, `services/evolution_cycle.py`, `evals/fitness_runner.py`, `services/evolution_optimizer.py`, `api/evolution_knowledge.py`, `services/operational_health.py:54`, `services/shortcuts.ts`, `components/SavedViewsBar.tsx`, `hooks/useVirtualList.ts`, `components/peek/PeekCard.tsx` |
| **176-183** | IMPLEMENTADO | los 8 tienen `test_plan1XX_*.py`; 176 con 12 commits impl incluyendo `6261b95d` (F9) |
| **184** | META — EJECUTADO | hoja de ruta DB Compare; `fd4db409 docs(plan-184): GATE-0 CORRIDO` |
| **185, 187, 192, 194** | IMPLEMENTADO | `services/undoManager.ts`, `components/bulk/BulkActionsBar.tsx`, `components/ConnectionBanner.tsx`, `services/copyService.ts` — llegaron por merge `35651bcb`, por eso `grep plan-185` solo muestra `docs(...)` |
| **186, 188-191, 193, 198** | IMPLEMENTADO | `test_plan186..193_*.py` + `services/env_apply_ledger.py` |
| **195, 197** | META | hojas de ruta; su accionable existe: `services/secret_masking.py`, `scripts/check_serie_gates.sh`, `scripts/check_serie_ux_gates.sh` |
| **196, 199, 200, 201, 202** | IMPLEMENTADO | `test_plan196..202_*.py`; 202 cerrado por `a8c60cf5` "plan COMPLETO E1..E7" |
| **208-218** | IMPLEMENTADO | `test_plan208..218_*.py`; 214 cerrado por `51144e3e` (F1+F2, lo que `3a2c73fb` había marcado PARCIAL); 216 confirmado por `aa5cc2e6`; 217 = `backend/tools/migrar_mantis_gitlab/` + 8 commits |
| **237-241** | IMPLEMENTADO | `test_plan237..241_*.py`; 240 por `82dd14be`+`43f6bcd6`+`f49fc919` |
| **246-252** | IMPLEMENTADO | 30 archivos `test_plan246..252_*.py` + 7 commits `feat(plan-24X): F0..F5/F6 implementadas`. **La memoria del operador dice "NINGUNO implementado" — está STALE.** |
| **253-258** | IMPLEMENTADO | 18 archivos `test_plan253..258_*.py` + 6 commits `feat(plan-25X): F0..F7/F8 implementadas` |

### 1.3 Los 13 con trabajo pendiente

| NN | Estado | Evidencia concreta (símbolo ausente verificado) | Última crítica |
|---|---|---|---|
| **116** | **PARCIAL** — falta F4-frontend | Backend OK (`services/connection_doctor.py:263::probe_tracker`, `api/devops_connections.py`, `RemediationCard.tsx`). `components/devops/ServersSection.tsx` no tiene `diag`/`remediation`/estado vacío (grep 0 hits). El propio doc lo declara DIFERIDO | n/a — implementable |
| **242** | **PENDIENTE** | `frontend/src/lib/costForecast.logic.ts` AUSENTE · `services/cost_stats.py` AUSENTE · `services/cost_scoring.py` AUSENTE · 0 archivos `test_plan242_*` | v2 · **APROBADO-CON-CAMBIOS** (literal en el doc) |
| **243** | **PARCIAL** — F0..F3.5 hechas, F4..F9 **remitidas al plan 244 que NO EXISTE** | Existen `test_plan243_{corpus_mirror,reglas_semanticas,renderer_ado,spec_extendido,task_catalog}.py` + `services/pipeline_spec.py` + `devops/specBuilder.ts`. Faltan los tests de ledger/flag/activación | v3 · **APROBADO-CON-CAMBIOS** — pero **sin documento para el resto** |
| **259** | PENDIENTE | `frontend/src/projects/setupGuideModel.ts` AUSENTE · 0 `test_plan259_*` | v2 (v1 RECHAZADO, 5 bloq) — **v2 sin re-juzgar** |
| **260** | PENDIENTE | 0 `test_plan260_*`. (`devops/pipelineEnvMatrixModel.ts` EXISTE pero es anclaje del plan 251, no producto del 260) | **v3 · v2 RECHAZADO (7 bloq)** — 2 rechazos seguidos |
| **263** | PENDIENTE | `services/plans_estado_migration.py` AUSENTE · 0 `test_plan263_*` | **v3 · v2 RECHAZADO** — 2 rechazos |
| **264** | PENDIENTE | `frontend/src/services/modelEffortTrace.ts` AUSENTE · 0 `test_plan264_*`. (`config/model_catalog.json` EXISTE, es del plan 159) | **v3 · v2 RECHAZADO** — 2 rechazos |
| **265** | PENDIENTE | 0 `test_plan265_*`. (`CodexConsoleDock.tsx` EXISTE: es el archivo que el plan MODIFICA, del plan 132) | **v3 · v2 RECHAZADO (5 bloq NUEVOS)** — 2 rechazos |
| **266** | PENDIENTE | `components/dbcompare/summaryShape.test.ts` AUSENTE · 0 `test_plan266_*`. (`radarLogic.ts` EXISTE: es el archivo con el bug vivo) | **v3 · v2 RECHAZADO (2 bloq introducidos por el propio v2)** — 2 rechazos |
| **267** | PENDIENTE | `services/devops_action_catalog.py` AUSENTE · `api/devops_actions.py` AUSENTE · 0 `test_plan267_*` | v2 (v1 RECHAZADO, 5 bloq) — **v2 sin re-juzgar** |
| **268** | PENDIENTE | `frontend/src/docs/graphSearch.ts` AUSENTE · 0 `test_plan268_*`. (`docs/forceLayout.ts` EXISTE, es del plan 111) | v2 (v1 RECHAZADO, 5 bloq) — **v2 sin re-juzgar** |
| **269** | PENDIENTE | `services/run_verdict.py` AUSENTE · 0 `test_plan269_*`. (`run_outcome.py`, `run_reconciliation.py` EXISTEN: anclajes del 254) | v2 — **sin re-juzgar** |
| **270** | PENDIENTE | `frontend/src/incidents/incidentDivergence.ts` AUSENTE · 0 `test_plan270_*`. (`services/run_ticket_refresh.py` EXISTE, es anclaje) | v2 (v1 RECHAZADO, 5 bloq) — **v2 sin re-juzgar** |
| **271** | PENDIENTE | `services/final_state_resolver.py` AUSENTE · 0 `test_plan271_*`. (`harness/task_states.py`, `services/completion_state.py` EXISTEN: anclajes) | **v3 · v2 RECHAZADO (6 bloq) · v1 RECHAZADO (8 bloq)** — 2 rechazos |

### 1.4 Nota honesta sobre la regla "RECHAZADO ⇒ no implementable"

La consigna dice clasificar aparte todo plan cuya última crítica fue RECHAZADO, y lista ahí a **246-252**. La evidencia lo contradice: **esos 7 se construyeron igual y están verdes** (30 archivos de test + 7 commits `F0..F5 implementadas`). El patrón real del pipeline es: el juez emite el veredicto sobre la versión ANTERIOR y **reescribe el documento** con los fixes; el doc en disco es siempre la versión corregida, nunca la rechazada.

Por eso separo en dos grados de riesgo, en vez de un bucket plano:

- **Grado A — un solo rechazo (v1 RECHAZADO → v2 con fixes):** 259, 267, 268, 269, 270. Misma forma exacta que 246-252, que se construyeron sin drama. Riesgo comparable al histórico.
- **Grado B — dos rechazos seguidos (v2 también RECHAZADO → v3):** 260, 263, 264, 265, 266, 271. Acá el patrón se degrada: el 265 recibió *"5 BLOQUEANTES **nuevos**"* y el 266 v2 **introdujo 2 bloqueantes propios** (coma colgante que rompe el `.ps1`, `log_pattern: null` que rompe el catálogo de huellas). Un v3 escrito en la misma corrida que su crítica no equivale a revisión independiente.

**Los 11 quedan igual fuera de los paquetes de implementación** (§6), como pide la consigna. La distinción A/B sirve para priorizar el desbloqueo: los 5 de grado A necesitan **una** pasada de juez independiente; los 6 de grado B necesitan que el juez **ejecute** el gate (correr el `.ps1` por su parser, correr el test de esquema, medir el baseline), no que lo relea.

---

## 2. Archivos imán (medidos, no supuestos)

Frecuencia de modificación en los 213 commits de `main..HEAD`:

| # | Archivo (bajo `Stacky Agents/`) | Toques | Por qué es imán |
|---|---|---:|---|
| 1 | `backend/scripts/run_harness_tests.sh` | **56** | ratchet `HARNESS_TEST_FILES` — todo `test_*.py` nuevo entra acá o `test_harness_ratchet_meta.py` se pone rojo |
| 2 | `backend/scripts/run_harness_tests.ps1` | **52** | **gemelo con sintaxis distinta**: `$HarnessTestFiles = @(` (`:13`), no `HARNESS_TEST_FILES=(`. Una coma colgante lo rompe |
| 3 | `backend/services/harness_flags.py` | **39** | `FLAG_REGISTRY` + `_CATEGORY_KEYS` |
| 4 | `backend/config.py` | **39** | atributo `Config` = default EFECTIVO de la flag |
| 5 | `backend/tests/test_harness_flags.py` | **37** | test de registro por flag |
| 6 | `frontend/src/api/endpoints.ts` | **32** | toda ruta nueva se declara acá |
| 7 | `docs/sistema/error_fingerprints.json` | **23** | catálogo de huellas de error |
| 8 | `backend/services/harness_flags_help.py` | **22** | ayuda por flag (con límite de 240 chars) |
| 9 | `backend/tests/test_harness_flags_requires.py` | **15** | aristas `requires` (R4, profundidad 1) |
| 10 | `backend/api/devops.py` | 13 | superficie DevOps |
| 11 | `backend/api/__init__.py` | 12 | **registro de blueprints** — todo `api/*.py` nuevo pasa por acá |
| 12 | `backend/app.py` | 9 | daemons y arranque |

### 2.1 El cableado de una flag es un bloque atómico de 7 archivos

Verificado sobre dos implementaciones independientes:

```
git show --stat 0b38da29   (plan 258)     git show --stat c077c743   (plan 253)
  backend/config.py                          backend/config.py
  backend/services/harness_flags.py          backend/services/harness_flags.py
  backend/services/harness_flags_help.py     backend/services/harness_flags_help.py
  backend/tests/test_harness_flags.py        backend/tests/test_harness_flags.py
  backend/tests/test_harness_flags_requires.py  backend/tests/test_harness_flags_bounds.py
  backend/scripts/run_harness_tests.sh       backend/scripts/run_harness_tests.sh
  backend/scripts/run_harness_tests.ps1      backend/scripts/run_harness_tests.ps1
```

**Los 12 planes con trabajo pendiente declaran flags nuevas.** Contadas del propio texto: 242→13, 259→4, 260→5, 263→4, 264→7, 265→5, 266→1, 267→4, 268→1, 269→5, 270→7, 271→5.

**Consecuencia dura:** en un árbol compartido, la disjunción de archivos entre dos paquetes cualesquiera es **imposible por construcción** mientras cada uno declare sus propias flags. No hay merge de git que salve esto: dos agentes escribiendo el mismo archivo en el mismo working tree pierden escrituras, no generan conflicto.

### 2.2 Política por archivo imán

| Archivo | Política | Quién |
|---|---|---|
| `config.py`, `harness_flags.py`, `harness_flags_help.py`, `test_harness_flags.py`, `test_harness_flags_requires.py`, `run_harness_tests.sh`, `run_harness_tests.ps1` | **PRE-DECLARACIÓN ATÓMICA en P0.** Todas las flags de todos los paquetes se registran de una, `default=False` explícito, en un solo commit, ANTES del fan-out. Después **nadie más los toca** | solo P0 |
| `frontend/src/api/endpoints.ts` | **PRE-DECLARACIÓN en P0** de los stubs de endpoint de cada paquete. Si un paquete necesita uno no previsto → lo pide a P0, no lo escribe | solo P0 |
| `backend/api/__init__.py` | **PRE-REGISTRO en P0** de los blueprints nuevos (`devops_actions`, etc.), apuntando a módulos que P0 crea vacíos | solo P0 |
| `frontend/src/theme.css` | **DUEÑO ÚNICO = P5 (268).** 263 y 270 también lo citan; ambos quedan detrás y usan los tokens que ya existen | solo P5 |
| `docs/sistema/error_fingerprints.json` | **COSTURA FINAL, un solo agente.** Es un catálogo de `log_pattern`s; el 266 v2 ya lo rompió una vez con `log_pattern: null` | costura |
| `backend/services/plans_board.py`, `frontend/src/pages/PlansBoardPage.tsx` | **DUEÑO ÚNICO = P3.** 263, 264 y 265 los tocan los tres → van juntos y en serie | solo P3 |
| `backend/harness/task_states.py`, `backend/api/incident_inbox.py`, `backend/api/tickets.py` | **DUEÑO ÚNICO = P1.** 269, 270 y 271 los tocan los tres → juntos y en serie | solo P1 |
| `backend/app.py` | Ningún paquete pendiente lo necesita. Si aparece → costura | costura |

---

## 3. Paquetes

Regla de corte aplicada, en el orden pedido: **(a)** disjunción de archivos → **(b)** archivos imán con dueño único → **(c)** dependencias duras → **(d)** tamaño parejo.

### P0 — COSTURA PREVIA (secuencial, bloquea todo lo demás)
- **Planes:** ninguno. Es infraestructura de paralelización.
- **Trabajo:** registrar TODAS las flags de los paquetes que se vayan a lanzar (default OFF), en los 7 archivos del bloque atómico; registrar TODOS los `test_plan<NNN>_*.py` previstos en **ambos** ratchets (`.sh` y `.ps1`, sintaxis distinta); crear los módulos vacíos y registrar sus blueprints en `api/__init__.py`; declarar los stubs en `endpoints.ts`.
- **Footprint:** los 7 imanes + `api/__init__.py` + `endpoints.ts`.
- **Terminado cuando:** `venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_harness_ratchet_meta.py` verde, y `bash scripts/run_harness_tests.sh` no reporta `MISSING`.

### P1 — Verdad del estado del ticket (269 + 270 + 271)
- **Orden interno OBLIGATORIO y SECUENCIAL:** `271` → `270` → `269`.
- **Por qué juntos:** colisión dura triple. 269∩270 en `api/tickets.py`, `api/incident_inbox.py`, `pages/IncidentInboxPage.tsx`. 270∩271 en `harness/task_states.py`. No se pueden separar.
- **Por qué ese orden:** 271 define quién escribe el estado final (`final_state_resolver.py`); 270 usa ese resolutor para cerrar en ADO y GitLab; 269 lee el resultado para emitir veredicto. Al revés hay que reescribir.
- **Footprint:** `backend/harness/task_states.py`, `backend/services/{final_state_resolver,completion_state,agent_completion_internal,completion_sync,run_ticket_refresh,gitlab_provider,run_verdict,run_evidence,status_vocabulary}.py`, `backend/api/{tickets,incident_inbox,executions}.py`, `backend/harness/post_run.py`, `frontend/src/pages/{IncidentInboxPage,ExecutionHistoryPage,StatesConfigPage}.tsx`, `frontend/src/incidents/*.ts`, `frontend/src/utils/{outcomeReason,finalStateOutcome}.ts`, `frontend/src/components/RunReconciliationCard.tsx`.
- **Tamaño:** grande (3 planes, 35 fases sumadas). Es el paquete más caro y el único irreductible.

### P2 — DevOps: variables y acciones (260 + 267)
- **Orden interno SECUENCIAL:** `260` → `267`.
- **Por qué:** el 267 cita `STACKY_PIPELINE_ENV_MATRIX_ENABLED` y `STACKY_PIPELINE_TRIGGER_ENABLED` como anclajes existentes; ambos son superficie del 260. Colisionan en `frontend/src/components/devops/` y en `backend/api/devops_agent.py`.
- **Footprint:** `backend/services/devops_action_catalog.py` (nuevo), `backend/api/{devops_actions,devops_agent}.py`, `frontend/src/devops/{pipelineDeclareModel,triggerGateModel}.ts`, `frontend/src/components/devops/{VariablesSection,PipelineEnvMatrixPanel}.tsx`, `frontend/src/components/PipelineTriggerCard.tsx`, `frontend/src/services/{devopsActionRunner,devopsActionBindings}.ts`, `frontend/src/components/commandPaletteData.ts`.

### P3 — Tablero de planes, modelo/effort y consola (263 + 264 + 265)
- **Orden interno SECUENCIAL:** `263` → `264` → `265`.
- **Por qué juntos:** 263∩264 en `frontend/src/pages/PlansBoardPage.tsx`; 263∩265 en `backend/services/plans_board.py`. Los tres comparten el tablero.
- **Footprint:** `backend/services/{plans_board,plans_estado_migration,parallel_runs,runtime_capabilities,codex_cli_runner,claude_code_cli_runner}.py`, `backend/agent_runner.py`, `backend/api/{phase6,agents}.py`, `backend/harness/runaway_guard.py`, `frontend/src/pages/PlansBoardPage.tsx(+.module.css)`, `frontend/src/plansBoard/actions.ts`, `frontend/src/services/{modelEffortTrace,entityActions,shortcuts}.ts`, `frontend/src/components/{IncidentResolverModal,CodexConsoleDock,AppearanceSettings}.tsx`, `frontend/src/store/workbench*.ts`.
- **Nota:** `frontend/src/theme.css` lo cita el 263 pero su dueño es **P5**. P3 usa tokens existentes (`--accent`, `--danger`, `--success`, `--border`, `--text-primary`, `--bg-panel`).

### P4 — Comparador de BD: cero pantalla rota (266)
- **Footprint (aislado):** `backend/services/{dbcompare_watch,dbcompare_runs,dbcompare_diff}.py`, `backend/api/db_compare_watch.py`, `frontend/src/components/dbcompare/{radarLogic,svgMath,EnvironmentRadar,SummaryHero,RunsTimeline}.*`, `frontend/src/components/PageErrorBoundary.tsx`, `frontend/src/__tests__/dbcompareSummaryShapeRatchet.test.ts`.
- **Único paquete con un bug VIVO reproducible:** `radarLogic.ts:60` `reading 'danger'`.

### P5 — Explorador del grafo documental (268)
- **Footprint (aislado):** `backend/api/docs.py`, `frontend/src/docs/{graphSearch,graphPreview,graphPalette,graphNeighborhood,forceLayout}.ts`, `frontend/src/components/docs/{DocGraphView,DocGraphExplorer.module.css}`, **`frontend/src/theme.css` (dueño único)**.
- **Restricción del propio plan:** Grapify es INVIABLE (charts de Node.js). No re-proponerlo.

### P6 — Alta de proyecto GitLab (259)
- **Footprint (aislado):** `backend/api/projects.py`, `backend/project_manager.py`, `backend/services/{gitlab_client,client_profile_default_templates}.py`, `frontend/src/components/{NewProjectModal,EditProjectModal,SetupGuideDialog}.tsx`, `frontend/src/projects/{setupGuideModel,newProjectGitlabModel}.ts`, `frontend/src/types.ts`, **`config.json`**.
- **`config.json` es dueño único de P6.** Ningún otro paquete pendiente lo toca.

### P7 — Centro de Costos, mitad read-only (242 recortado)
- **Alcance EXACTO — no negociable, está en §0.3 del propio plan:** **F0, F1, F2, F6-parcial** (`/cost-stats`, `/cost-scores`), **F7-parcial** (sub-tabs Estadísticas y Scoring), **F8-parcial** (solo 2 flags: `STACKY_COST_STATS_ENABLED`, `STACKY_COST_SCORING_ENABLED`).
- **F3, F4, F5, F6-resto, F7-resto, F9 son el plan 245, que NO EXISTE. NO implementarlas.** Regla literal del doc: *"no se arranca el 245 hasta que el DoD del 242 esté verde"*.
- **Footprint (aislado):** `backend/services/{cost_signals,cost_stats,cost_scoring,cost_analytics}.py`, `backend/api/metrics.py`, `backend/models.py`, `frontend/src/pages/CostCenterPage.tsx`, `frontend/src/lib/costCenterTypes.ts`, `frontend/src/services/routes.ts`, `backend/tests/test_plan242_{cost_signals,cost_stats,cost_scoring,cost_api,flags_off,no_new_deps,runtime_parity}.py`.
- **IMPLEMENTABLE HOY** (v2 APROBADO-CON-CAMBIOS explícito).

### P8 — Micro: 116 F4-frontend
- **Alcance:** un solo archivo. Diagnóstico tipificado desde `test.detail` + estado vacío con CTA en `ServersSection.tsx`.
- **Footprint:** `frontend/src/components/devops/ServersSection.tsx` (y opcionalmente `FlagGateBanner.tsx`, solo facelift visual).
- **Sin flags nuevas ⇒ NO depende de P0.** Es el único paquete que puede arrancar sin costura previa.
- **IMPLEMENTABLE HOY.**

---

## 4. Olas

### OLA 1 — HOY, sin desbloquear nada (**2 agentes en paralelo**)

| Paquete | Depende de | Puede arrancar |
|---|---|---|
| **P8** (116 F4) | nada | inmediato |
| **P7** (242 recortado) | P0 reducido: solo sus 2 flags | inmediato si el mismo agente hace su propio cableado de flags |

Con solo estos dos, **P0 no hace falta**: sus footprints son disjuntos y solo P7 toca los imanes. Se le da a P7 la propiedad exclusiva del bloque de 7 archivos durante su corrida.

**2 agentes simultáneos. Es el techo real de hoy.**

### OLA 2 — CONDICIONAL, si el operador desbloquea los 11 (§6)

- **Paso 0 (secuencial, 1 agente):** **P0** costura previa.
- **Paso 1 (paralelo, 6 agentes):** **P1, P2, P3, P4, P5, P6**.

Sin P0, el máximo honesto de la OLA 2 baja a **3 agentes** (P4 + P5 + P6, los tres aislados) y P1/P2/P3 quedan en serie detrás de ellos por la colisión de flags.

### OLA 3 — Costura final (secuencial, 1 agente)
`docs/sistema/error_fingerprints.json` (todas las huellas nuevas de todos los paquetes, de una) + corrida completa de `run_harness_tests.sh` **y** `run_harness_tests.ps1` + `npx tsc --noEmit`.

---

## 5. Protocolo de concurrencia (obligatorio para TODO agente implementador)

Estos rieles no son sugerencias. Cada uno viene de un incidente registrado en este repo.

1. **PROHIBIDO** `git stash`, `git reset`, `git commit --amend`, `git rebase`, `git checkout <rama>`. Hubo y puede haber sesiones paralelas sobre este árbol; el HEAD se mueve solo. Un `stash` se lleva puesto el trabajo de otro agente.
2. **Commitear SIEMPRE con pathspec explícito:** `git commit -- "Stacky Agents/backend/services/mi_modulo.py" "Stacky Agents/backend/tests/test_planNNN_x.py"`. El índice es compartido; un `git commit -a` o `git add .` roba los cambios ajenos.
3. **Tests POR ARCHIVO, nunca la suite entera:** `"Stacky Agents/backend/venv/Scripts/python.exe" -m pytest tests/test_planNNN_x.py -q` desde `Stacky Agents/backend`. La suite completa contamina cross-file. En frontend, vitest también contamina por orden: correr por archivo.
4. **Flakiness conocida:** `SQLITE_LOCKED` por shared-cache en todo test que toque la DB. Si un test de DB falla, correrlo 8-12 veces antes de declararlo roto.
5. **"Ya estaba rojo de antes" se PRUEBA, no se afirma:** `git worktree add <tmp> <commit-base>` y correr ahí el mismo archivo. Sin eso, no vale como excusa.
6. **Todo `test_*.py` NUEVO va registrado en los DOS ratchets:** `HARNESS_TEST_FILES=(` en `run_harness_tests.sh` y `$HarnessTestFiles = @(` en `run_harness_tests.ps1` (`:13`). **Sintaxis distinta.** Si no, `test_harness_ratchet_meta.py` se pone rojo. Una coma colgante rompe el `.ps1` entero: validarlo pasándolo por su parser, no leyéndolo.
7. **Una flag son 7 archivos, siempre** (§2.1). Declarar el `default=False` **explícito** en `config.py` — el default efectivo vive ahí, no en `harness_flags.py`. Y categorizar en `_CATEGORY_KEYS` o el registro falla.
8. **`config.config` vs módulo:** no hay regla global. `import config` ⇒ `config.config.X`. `from config import config` ⇒ `getattr(config, "X")`. Errar da AttributeError/500 en runtime, no en tests.
9. **Reservar nombres ANTES de escribir código:** si tu paquete crea `services/foo.py`, verificá que ningún otro paquete de la misma ola lo declare. El footprint de §3 es el contrato.
10. **Anclajes `archivo:línea` de los planes son ORIENTATIVOS.** Localizá el símbolo con `grep -n "<simbolo>" <archivo>` y usá la línea real. Un número que no coincide no es permiso para inventar.
11. **Prohibido tocar archivos fuera del footprint de tu paquete.** Si necesitás uno ajeno, parás y lo reportás. No lo editás.
12. **No pushear.** El push es siempre manual del operador.

---

## 6. Bucket aparte — NO empaquetar

### 6.1 Bloqueados por crítica (11 planes)

| NN | Grado | Qué falta para desbloquear |
|---|---|---|
| 259 | A (1 rechazo) | Una pasada de juez independiente sobre el v2 (contexto limpio, otro subagente) |
| 267 | A | Ídem. Su v2 ya resolvió los 5 bloqueantes del v1 con anclaje exacto; el eje `reach` fue una adición del arquitecto |
| 268 | A | Ídem. Verificar en particular que no vuelva a pedir tokens `--color-*`: **esa familia no existe en `theme.css`** |
| 269 | A | Ídem. Verificar las 5 trampas de superficie: la clave `verdict` ya está ocupada, hay DOS handlers de listado, el campo real es `passed` |
| 270 | A | Ídem. Verificar que `resolve_closed_states()` se desempaqueta: devuelve **2-tupla** `(estados, fuente)` y pasarla entera NO lanza, solo hace que nada matchee |
| 260 | B (2 rechazos) | Juez que **ejecute**: correr el gate, medir el baseline. Hay DOS motores CI/CD ciegos entre sí |
| 263 | B | Juez que ejecute: sus reglas daban 61 propuestas y 0 en PROPUESTO. Verificar que `load_ledger()` no borre las 47 aprobaciones |
| 264 | B | Juez que ejecute: el v2 parcheaba **código muerto** (`agent_runner:254-264`); el camino vivo es `_start_cli_runtime:442` |
| 265 | B | Juez que ejecute: el v2 metió 5 bloqueantes NUEVOS. Hay DOS funciones `cancel` |
| 266 | B | Juez que ejecute: el v2 metió 2 bloqueantes propios (coma colgante que rompe el `.ps1`, `log_pattern: null` que rompe el catálogo). **El bug de producción sigue vivo** en `radarLogic.ts:60` |
| 271 | B | Juez que ejecute: los 6 bloqueantes del v2 salieron de CORRER, no de releer. Son **SEIS motores de estado / NUEVE entradas**, no cuatro |

**Recomendación de secuencia:** desbloquear primero los 5 de grado A (una corrida de `criticar-y-mejorar-plan` con juez independiente por plan) y **con eso solo ya se habilitan P1-parcial, P2-parcial, P5 y P6**. Los 6 de grado B necesitan una crítica que ejecute el gate, que es sustancialmente más cara.

### 6.2 Continuaciones sin documento (2)

| Falta | Qué es | Qué hace falta |
|---|---|---|
| **Plan 244** | F4..F9 del 243 (generador de pipelines NL). El 243 las remitió formalmente al 244 | Correr `proponer-plan-stacky` fijando el número **244** y el alcance = F4..F9 del 243 |
| **Plan 245** | F3..F9 del 242 (modelo predictivo, backtesting, ledger forecast-vs-real). Reservado explícitamente | Correr `proponer-plan-stacky` fijando **245**, y **solo después de que el DoD del 242 esté verde** |

Los números **261** y **262** siguen libres (huecos preexistentes). El próximo número libre por arriba es el **272**.

### 6.3 Bloqueados por componente ajeno

Ninguno vigente. Los 6 ítems que la memoria del operador lista como "esperando TicketBoard" (planes 216, 212, 200, 172, 173, 175) están todos construidos: `a2f2e2ff feat(plan-216/173/175): los 3 montajes del tablero que faltaban`.

---

## 7. Recetas de lanzamiento

> Preámbulo común a TODOS los prompts. Pegarlo entero.

```
Trabajás en N:\GIT\RS\STACKY\Stacky sobre la rama feat/plan-217-migrador-mantis-gitlab.
El código vive bajo "Stacky Agents/backend/" y "Stacky Agents/frontend/src/" — NO cuelga de la raíz.
venv: "Stacky Agents/backend/venv/Scripts/python.exe" (py3.13).

HAY OTROS AGENTES TRABAJANDO EN ESTE MISMO WORKING TREE AL MISMO TIEMPO.

RIELES DUROS (violarlos destruye trabajo ajeno):
- PROHIBIDO git stash, git reset, git commit --amend, git rebase, git checkout <rama>.
- Commiteá SIEMPRE con pathspec explícito: git commit -- "<ruta1>" "<ruta2>". NUNCA git add . ni git commit -a.
- NO pushees. El push lo hace el operador.
- NO toques ningún archivo fuera de tu lista PERMITIDA. Si necesitás uno prohibido, PARÁ y reportalo.

TESTS:
- Por ARCHIVO, nunca la suite: cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_X.py -q
- Flakiness SQLITE_LOCKED conocida: si falla un test de DB, corrélo 8-12 veces antes de darlo por roto.
- "ya estaba rojo": se prueba con git worktree add <tmp> <commit-base>, no se afirma.
- Todo test_*.py NUEVO va en LOS DOS ratchets: HARNESS_TEST_FILES=( en scripts/run_harness_tests.sh
  Y $HarnessTestFiles = @( en scripts/run_harness_tests.ps1 (línea 13, sintaxis PowerShell distinta).
  Validá el .ps1 pasándolo por su parser, no leyéndolo: una coma colgante lo rompe entero.

ANCLAJES: todo "archivo:línea" del plan es ORIENTATIVO. La verdad es el símbolo.
Localizalo con grep -n "<simbolo>" <archivo>. Un número que no coincide NO es permiso para inventar.

FLAGS: una flag son 7 archivos (config.py, services/harness_flags.py, services/harness_flags_help.py,
tests/test_harness_flags.py, tests/test_harness_flags_requires.py, scripts/run_harness_tests.sh, .ps1).
Declará default=False EXPLÍCITO en config.py: el default efectivo vive ahí.
config.config vs módulo: "import config" ⇒ config.config.X ; "from config import config" ⇒ getattr(config,"X").
```

### P8 — 116 F4 (implementable HOY)
```
Corré /implementar-plan-stacky sobre el plan 116, SOLO la fase F4-frontend.
El backend del 116 YA está construido (services/connection_doctor.py:263 probe_tracker,
api/devops_connections.py, components/devops/RemediationCard.tsx). NO lo re-implementes.

Lo único que falta: ServersSection.tsx no expone diagnóstico tipificado desde test.detail
ni estado vacío con CTA (verificado: grep de "RemediationCard|diag|remediation" da 0 hits).

PERMITIDO tocar SOLO:
  Stacky Agents/frontend/src/components/devops/ServersSection.tsx
  Stacky Agents/frontend/src/components/devops/FlagGateBanner.tsx  (opcional, solo facelift)

PROHIBIDO tocar: cualquier archivo backend, cualquier flag, ambos run_harness_tests.*,
config.py, endpoints.ts, theme.css.

Este paquete NO declara flags nuevas: no necesitás tocar ninguno de los 7 archivos de flags.

TERMINADO cuando: npx tsc --noEmit da 0 errores, el diagnóstico tipificado se renderiza
desde test.detail, y el estado vacío con CTA aparece cuando no hay servidores.
Commit con pathspec explícito. Sin push.
```

### P7 — 242 recortado (implementable HOY)
```
Corré /implementar-plan-stacky sobre el plan 242, con el ALCANCE RECORTADO de su §0.3.

IMPLEMENTÁS SOLO: F0, F1, F2, F6-parcial (endpoints /cost-stats y /cost-scores),
F7-parcial (sub-tabs "Estadísticas" y "Scoring" del Centro de Costos),
F8-parcial (SOLO 2 flags: STACKY_COST_STATS_ENABLED y STACKY_COST_SCORING_ENABLED).

NO IMPLEMENTES F3, F4, F5, F6-resto, F7-resto ni F9. Son el plan 245, que NO EXISTE todavía.
Regla literal del doc: "no se arranca el 245 hasta que el DoD del 242 esté verde".
Todo lo que ESCRIBE en disco (cost_model.json, ledger forecast) queda FUERA.
Esta mitad es estrictamente READ-ONLY: no escribe archivos, no registra hooks.

PERMITIDO tocar:
  Stacky Agents/backend/services/{cost_signals,cost_stats,cost_scoring,cost_analytics}.py
  Stacky Agents/backend/api/metrics.py
  Stacky Agents/backend/models.py
  Stacky Agents/backend/tests/test_plan242_{cost_signals,cost_stats,cost_scoring,cost_api,flags_off,no_new_deps,runtime_parity}.py
  Stacky Agents/frontend/src/pages/CostCenterPage.tsx
  Stacky Agents/frontend/src/lib/costCenterTypes.ts
  Stacky Agents/frontend/src/services/routes.ts
  Stacky Agents/frontend/src/api/endpoints.ts
  Y el bloque de 7 archivos de flags — tenés PROPIEDAD EXCLUSIVA de ellos durante tu corrida.

PROHIBIDO tocar: services/plans_board.py, api/tickets.py, api/incident_inbox.py,
harness/task_states.py, frontend/src/theme.css, docs/sistema/error_fingerprints.json,
y todo lo de components/dbcompare/, components/devops/, docs/.

RESTRICCIÓN DEL PLAN: Python puro. Sin numpy, sin sklearn, sin dependencias nuevas
(hay un test que lo verifica: test_plan242_no_new_deps.py).

TERMINADO cuando: los 7 archivos test_plan242_* verdes corridos POR ARCHIVO con el venv
(pegá el output real, no un "pasó todo"), las 2 flags registradas en los 7 lugares con
default=False explícito, ambos ratchets actualizados, npx tsc --noEmit en 0.
Commit con pathspec explícito. Sin push.
```

### P0 — Costura previa (solo si se lanza la OLA 2)
```
NO implementás ningún plan. Preparás el terreno para 6 agentes en paralelo.

Registrá, en UN SOLO commit, TODAS las flags de los paquetes P1..P6 con default=False,
en los 7 archivos del bloque atómico de flags. Registrá TODOS los test_plan<NNN>_*.py
previstos en AMBOS ratchets. Creá los módulos nuevos VACÍOS (solo docstring) y registrá
sus blueprints en backend/api/__init__.py. Declará los stubs en frontend/src/api/endpoints.ts.

Después de tu commit, NINGÚN otro agente toca esos archivos.

TERMINADO cuando: pytest de test_harness_flags.py, test_harness_flags_requires.py y
test_harness_ratchet_meta.py verde (output pegado), y run_harness_tests.sh sin MISSING,
y run_harness_tests.ps1 pasa por su parser sin error de sintaxis.
```

> Las recetas de P1..P6 se emiten cuando el operador desbloquee los planes del §6.1. Emitirlas antes sería mandar agentes a construir documentos que el juez rechazó.

---

## 8. Memoria: novedades durables de esta corrida

- La memoria del operador estaba **STALE en 3 puntos verificables**: (a) 246-252 figuran "NINGUNO implementado" y los 7 están construidos; (b) el 202 figura "falta F1-F5" y está COMPLETO E1..E7 (`a8c60cf5`); (c) los 6 ítems "bloqueados por TicketBoard" están todos montados (`a2f2e2ff`).
- **El header `**Estado:**` de un plan no es evidencia de nada.** Los `test_plan<NNN>_*.py` sí lo son: es la señal más barata y más fiable del repo para saber si un plan se construyó.
- El cableado de una flag es un **bloque atómico de 7 archivos**, medido sobre dos commits independientes. Eso es lo que hace imposible la paralelización ingenua en un árbol compartido.
