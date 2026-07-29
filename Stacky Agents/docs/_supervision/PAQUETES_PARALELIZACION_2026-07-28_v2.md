# Censo de planes pendientes y paquetes de paralelización — 2026-07-28 · **v2**

**Autor:** StackyArchitectaUltraEficientCode · **Tipo:** inventario + empaquetado (NO implementa nada, NO pushea)
**Base:** rama `feat/plan-217-migrador-mantis-gitlab` @ `4cb6c4a6` · **227 commits** por delante de `main`, **40** por delante de `origin`
**Worktrees:** UNO solo. `git worktree list` reporta `C:/desarrollo/GIT/RS/STACKY/Stacky` = `N:/GIT/RS/STACKY/Stacky` — **dos rutas, un mismo árbol**, no dos worktrees.
**venv:** `Stacky Agents/backend/venv/Scripts/python.exe` (py3.13). Existe también `.venv/`; ambos tienen `python.exe`.

> ### Por qué existe un v2 el mismo día
> El v1 (`PAQUETES_PARALELIZACION_2026-07-28.md`, commit `83d4c733`, base `77abb7c2`) quedó **desactualizado a las pocas horas**: declaraba **11 planes bloqueados por crítica RECHAZADA** y **2 implementables**. Entre su base y `4cb6c4a6` entraron **cinco críticas** que levantaron cinco de esos once (`78f50973` 259-v4, `edebbe41` 267-v4, `07ea6944` 268-v4, `f2d9c7b9` 269-v4, `4cb6c4a6` 270-v5). **El v1 NO se pisa** — queda como foto de las 15:17.
> Este v2 se construyó **barriendo el directorio de cero**, sin grepear la lista del v1, precisamente por el gotcha del plan 267 (grepear la lista que ya tenés confirma el error en vez de detectarlo).

---

## 0. Resumen ejecutivo

| Métrica | Valor medido | Cómo se midió |
|---|---|---|
| Documentos `*_PLAN_*.md` en `Stacky Agents/docs/` | **222** | `ls` + `grep -E "_PLAN_"` |
| — de ellos, numeración de 3 dígitos (100→271) | **143** | `grep -cE "^[0-9]{3}_PLAN_"` |
| — de ellos, numeración de 2 dígitos (19→99) | **79** | `grep -cE "^[0-9]{2}_PLAN_"` |
| Números de plan con archivo `test_plan*` (repo entero) | **112** | `find -name "test_plan*"` |
| Señal combinada de implementación (tests + comentarios en tests de frontend) | **151** | unión de ambos barridos |
| Candidatos sin ninguna de las dos señales | **75** | `comm -23` |
| **Pendientes REALES con trabajo accionable** | **11** | triple señal: 0 tests **y** 0 commits de implementación |
| **Implementables HOY** | **5** → **259, 267, 268, 269, 270** | veredicto independiente en la versión vigente |
| Pendientes que necesitan una pasada de crítica antes | **6** → 260, 263, 264, 265, 266, 271 | último veredicto = RECHAZADO |
| Marcados explícitamente **OBSOLETO — NO IMPLEMENTAR** | **2** → 100, 101 | header del propio doc |
| Planes meta / hoja de ruta (papel, nada que construir) | **2** → 184, 195 | título y contenido |
| Continuaciones declaradas SIN documento | **2** → 244, 245 | 0 docs; 244 citado como futuro en un test |
| Números libres | **261, 262** (272 RESERVADO por el 271 §6.1) | `271:6` |
| Paquetes propuestos | **1 costura + 4 (OLA 1) + 5 (OLA 2)** | §3 |
| **Techo de paralelismo hoy** | **2** | §6 |
| **Techo con costura + worktrees** | **4** | §6 |

**Los tres hallazgos que gobiernan el diseño:**

1. **El bloque de flags es de 7 archivos, confirmado — pero la ruta que circulaba es FALSA.** Los arneses **no** están en `Stacky Agents/scripts/`; están en **`Stacky Agents/backend/scripts/`**. Un agente que reciba la ruta vieja no encuentra el archivo y "resuelve" creando uno nuevo.
2. **Los imanes de merge son ~3x peores de lo que decía el número que circulaba.** Re-medido con `git log --all --oneline -- <ruta>`: el arnés `.sh` tiene **180** toques (no 56), `harness_flags.py` **153** (no 39), `config.py` **147** (no 39), `endpoints.ts` **146** (no 32).
3. **`endpoints.ts` es el segundo cuello, y la costura de flags NO lo resuelve.** Lo tocan 3 de los 4 paquetes de la OLA 1. Por eso la costura mínima **no levanta** el techo de 2; hace falta costura amplia + worktrees.

---

## 1. Censo en tabla

### 1.1 Método (y por qué el header `**Estado:**` no se usó como evidencia)

Tres señales independientes, en este orden:

| Señal | Comando | Qué prueba | Falsos negativos detectados |
|---|---|---|---|
| **S1 — tests** | `find . -name "test_plan*"` | Existe suite propia | **SÍ**: el plan **240** está implementado y sus tests viven en `Stacky tools/QA UAT Agent/tests/unit/`, no en `backend/tests/`. Los planes de UI pura no generan `test_planNN.py` (no hay RTL/jsdom). |
| **S2 — tests de frontend** | `grep -riE "plan ?[0-9]{2,3}"` en `*.test.ts*` | El plan dejó rastro en vitest | Rescató 39 planes que S1 marcaba pendientes |
| **S3 — commits** | `git log --all --grep="plan-NN"` menos los `docs(...)`/crítica | Hubo implementación real | **SÍ** para planes <100: la convención `plan-NN` en el asunto es posterior |

**El header `**Estado:**` del doc se leyó sólo para extraer el VEREDICTO, nunca para decidir si está implementado.** Confirmado que miente en las dos direcciones: el 217 dice "APROBADO-CON-CAMBIOS, listo para implementar" y tiene **8 commits de implementación** (ya está construido); el 240 no aparece en `backend/tests` y está operativo.

### 1.2 Los 11 pendientes reales — triple señal coincidente (0 tests · 0 commits)

| Plan | Tests | Commits impl. | Veredicto REAL medido en el doc | Bloqueantes abiertos | Implementable | Por qué no |
|---|:-:|:-:|---|---|:-:|---|
| **259** Alta GitLab + guía verificable | no | 0 | **v4 · APROBADO-CON-CAMBIOS** (`:13`, juez independiente, 2ª pasada sobre `b07527a3`) | 0 — los 4 del v3 aplicados en v4 | **SÍ** | — |
| **267** Catálogo único acciones DevOps | no | 0 | **v4 · APROBADO-CON-CAMBIOS** (`:3`) | 0 — los 4 corregidos "en esta misma versión" | **SÍ** | — |
| **268** Explorador grafo documental | no | 0 | **v4 · APROBADO-CON-CAMBIOS** sobre v3 (`:3`) | 0 — N1 (5×`TS2304`) cerrado con contrato de imports por fase | **SÍ** | — |
| **269** Veredicto por evidencia | no | 0 | **v4 · APROBADO-CON-CAMBIOS · 0 BLOQ / 4 IMP / 5 MEN** (`:73`) | 0 — **prohibición "NO implementar" LEVANTADA explícitamente** (`:3`, `:73`) | **SÍ** | — |
| **270** El tablero dice la verdad | no | 0 | **v5** · veredicto v4 **APROBADO-CON-CAMBIOS, cero defectos de diseño**; *"El plan es IMPLEMENTABLE en v5"* (`:8`) | 0 | **SÍ** | — |
| **260** Ninguna pipeline a ciegas | no | 0 | v3 · últimos veredictos **v1 RECHAZADO (5)**, **v2 RECHAZADO (7)**. El v3 **no tiene veredicto** | v3 sin juzgar | **NO** | Dos rechazos y la versión vigente nunca fue revisada por un juez independiente |
| **263** Tablero de planes denso | no | 0 | v3 · **v1 RECHAZADO (6)**, **v2 RECHAZADO (5)**; v3 in place, sin veredicto | v3 sin juzgar | **NO** | ídem |
| **264** Modelo y effort en todo punto | no | 0 | v3 · **v1 RECHAZADO (4)**, **v2 RECHAZADO (5)**; v3 sin veredicto | v3 sin juzgar | **NO** | ídem |
| **265** Consola DevOps pantalla completa | no | 0 | v3 · **v1 RECHAZADO (5)**, **v2 RECHAZADO (5 nuevos)**; v3 sin veredicto | v3 sin juzgar | **NO** | ídem |
| **266** Cero pantalla rota en Comparador | no | 0 | v3 · **v1 RECHAZADO**, **v2 RECHAZADO (2)**; v3 sin veredicto | v3 sin juzgar **+ 1 bloqueante NUEVO medido acá** (§1.4) | **NO** | ídem, y su F3 tiene un hueco verificado que lo pone rojo el día 1 |
| **271** La incidencia se mueve al estado | no | 0 | v3 · **v1 RECHAZADO (8)**, **v2 RECHAZADO (6)**; v3 sin veredicto | v3 sin juzgar | **NO** | ídem. Es el que acumula más rechazos de la serie |

### 1.3 Discrepancias notables del censo

| Plan | Discrepancia | Evidencia |
|---|---|---|
| **217** | Header dice *"listo para `implementar-plan-stacky`"* → **ya está implementado** (8 commits, la rama actual lleva su nombre). Lo que falta es **deuda de tests**: 0 archivos `test_plan217*` en todo el repo. | `git log --grep="plan-217"` = 8 no-doc |
| **240** | 0 tests en `backend/tests` → **implementado**, tests en otra raíz | `Stacky tools/QA UAT Agent/tests/unit/test_plan240_*.py` (5 archivos) |
| **100 / 101** | Ambos con 0 tests y 0 commits — **pero NO son backlog** | Header literal: `**Estado:** ❌ **OBSOLETO / SUPERADO — NO IMPLEMENTAR**`. El 101 fue reemplazado por el plan 108 |
| **244** | No existe como documento; sí está citado como trabajo futuro | `frontend/src/devops/__tests__/specBuilderTaskStep.test.ts:9`: *"F5 (plan 244) le va a entregar un dict construido"* |
| **272** | No existe y **está reservado** | `271:6` — *"El **272** queda reservado para 'un solo escritor de estado' (§6.1)"* |
| **261 / 262** | No existen y **siguen libres** | `271:6` |
| Cola <100 | 34 números sin tests y sin commits (19, 21-54) | Anteriores a ambas convenciones. La memoria del operador los registra como series completadas/supervisadas. **No medibles con este método**; fuera de alcance |
| Tests sin doc | **0** | `comm -13` vacío — no hay suites huérfanas |

### 1.4 Bloqueante NUEVO hallado midiendo (no estaba en ninguna crítica del 266)

El plan **266** declara **una** flag nueva, `STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED`, **con `requires="STACKY_DB_COMPARE_ENABLED"`**. Su tabla de cableado de F3 lista **5** lugares y **nunca menciona** `_REQUIRES_MAP_FROZEN` ni `test_harness_flags_requires.py`.

Medido:
```
grep -c "_REQUIRES_MAP_FROZEN\|test_harness_flags_requires"  266_PLAN_....md   →  0
tests/test_harness_flags_requires.py:316   assert actual == _REQUIRES_MAP_FROZEN
tests/test_harness_flags_requires.py:318   f"Extras: {sorted(set(actual) - set(_REQUIRES_MAP_FROZEN))}"
```

El assert es **igualdad de conjuntos** con reporte de `Extras`. Implementar el 266 verbatim agrega una arista `requires` que el mapa congelado no tiene ⇒ **`test_requires_map_is_frozen` queda ROJO con un `Extras`**, y el plan no lo prevé ni lo nombra. Esto entra como insumo obligatorio de la crítica del 266.

---

## 2. El bloque de flags — re-medido y corregido

### 2.1 Los 7 archivos (ruta CORREGIDA)

Verificado sobre `git show --stat 0b38da29` (plan 258) y `c077c743` (plan 253):

| # | Ruta real | Estructura que se toca | Tamaño hoy | ¿Obligatorio? |
|---|---|---|---|:-:|
| 1 | `Stacky Agents/backend/config.py` | atributo + `default=` (el default EFECTIVO vive acá) | 147 toques | siempre |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | `FlagSpec` en `FLAG_REGISTRY` **+** key en `_CATEGORY_KEYS` | **388** FlagSpec · 20 categorías | siempre |
| 3 | `Stacky Agents/backend/services/harness_flags_help.py` | entrada en `PLAIN_HELP` | **286** entradas | siempre |
| 4 | `Stacky Agents/backend/tests/test_harness_flags.py` | `_CURATED_DEFAULTS_ON` (`:467`) | **247** keys · **igualdad de conjuntos** en `:985` | si default ON |
| 5 | `Stacky Agents/backend/tests/test_harness_flags_requires.py` | `_REQUIRES_MAP_FROZEN` (`:120`) | **49** aristas · **igualdad de conjuntos** en `:316` | si declara `requires=` |
| 6 | **`Stacky Agents/backend/scripts/run_harness_tests.sh`** | `HARNESS_TEST_FILES` | **687** rutas | si agrega `test_*.py` |
| 7 | **`Stacky Agents/backend/scripts/run_harness_tests.ps1`** | `$HarnessTestFiles` (sintaxis DISTINTA, array por comas) | **623** rutas | ídem |
| +8 | `Stacky Agents/backend/tests/test_harness_flags_bounds.py` | bounds declarativos | — | **sólo si la flag es numérica** (visto en `c077c743`) |

> **`Stacky Agents/scripts/` NO EXISTE.** Cualquier receta que diga `scripts/run_harness_tests.sh` manda al agente a un archivo inexistente.

> **Deriva preexistente y ajena, ya medida:** `.sh` = **687** rutas, `.ps1` = **623** ⇒ **64 archivos** están sólo en el `.sh`. Un DoD que pida "las dos listas iguales" es **insatisfacible**. Criterio correcto = **delta**: el paquete sólo agrega SUS rutas a AMBOS y no empeora el conteo.

### 2.2 Imanes de merge — re-medidos

`git log --all --oneline -- "<ruta>" | wc -l`:

| Archivo | Toques medidos | Número que circulaba | Paquetes OLA 1 que lo tocan |
|---|--:|--:|:-:|
| `backend/scripts/run_harness_tests.sh` | **180** | 56 | 3 de 4 |
| `backend/scripts/run_harness_tests.ps1` | **169** | 52 | 3 de 4 |
| `backend/services/harness_flags.py` | **153** | 39 | **4 de 4** |
| `backend/config.py` | **147** | 39 | **4 de 4** |
| `frontend/src/api/endpoints.ts` | **146** | 32 | **3 de 4** ← segundo cuello |
| `backend/tests/test_harness_flags.py` | **95** | 37 | 4 de 4 |
| `backend/services/harness_flags_help.py` | **70** | — | **4 de 4** |
| `backend/tests/test_harness_flags_requires.py` | **67** | — | 2 de 4 |
| `backend/api/__init__.py` | **61** | 12 | 2 de 4 |
| `backend/api/tickets.py` | **47** | — | 1 de 4 |
| `backend/services/plans_board.py` | 4 | — | 0 (OLA 2) |
| `harness/task_states.py` · `api/incident_inbox.py` · `IncidentInboxPage.tsx` | 2 c/u | — | archivos nuevos/chicos |

### 2.3 Las 34 flags de los 11 planes — TODAS ausentes hoy

Verificado key por key contra `config.py` + `harness_flags.py`: **34/34 AUSENTE**, cero colisiones de nombre. Los prerequisitos que invocan sus `requires=` sí existen (`STACKY_DOCS_GRAPH_ENABLED`, `STACKY_DEVOPS_PANEL_ENABLED`, `STACKY_DB_COMPARE_ENABLED`, `STACKY_GITLAB_ENABLED`).

| Plan | # | Keys | `requires=` | Categoría |
|---|:-:|---|:-:|---|
| **259** | 3 | `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED`, `STACKY_SETUP_GUIDE_ENABLED`, `STACKY_SETUP_GUIDE_VERIFY_ENABLED` | no | `paridad_proveedores` |
| **267** | 3 | `STACKY_DEVOPS_ACTION_CATALOG_ENABLED`, `STACKY_DEVOPS_ACTION_NL_ENABLED`, `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` (sin `default=` ⇒ OFF) | 2 sí | `devops` |
| **268** | 1 | `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` | sí | `capacidades_optin` |
| **269** | 5 | `STACKY_RUN_VERDICT_ENABLED`, `STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED`, `STACKY_UI_RUN_VERDICT_BADGE_ENABLED`, `STACKY_INCIDENT_INBOX_VERDICT_ENABLED`, `STACKY_RUN_RECONCILIATION_HITL_ENABLED` | **no (deliberado)** | `observabilidad_notif` |
| **270** | 3 | `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED`, `STACKY_TICKET_STATE_WRITEBACK_ENABLED`, `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED` | no | `paridad_proveedores` |
| — | **15** | **subtotal OLA 1** | | |
| 260 | 3 | `STACKY_PIPELINE_ENV_DECLARE_ENABLED` (**OFF**), `..._SECRET_COMMIT_GATE_ENABLED`, `..._TRIGGER_ENV_GATE_ENABLED` | 1 sí | `devops` |
| 263 | 3 | `STACKY_PLANS_ESTADO_FALLBACK_ENABLED`, `..._NORMALIZE_PREVIEW_ENABLED`, `..._NORMALIZE_APPLY_ENABLED` (**OFF**) | 3 sí | `observabilidad_notif` |
| 264 | 4 | `STACKY_RUNTIME_CAPABILITIES_ENABLED`, `STACKY_CODEX_EFFORT_PARITY_ENABLED`, `STACKY_RUN_SELECTION_PREFS_ENABLED`, `STACKY_MODEL_PICKER_EVERYWHERE_ENABLED` | 3 sí | `_CATEGORY_KEYS:120` |
| 265 | 4 | `STACKY_CONSOLE_FULLSCREEN_ENABLED`, `..._RICH_RENDER_ENABLED`, `..._REPO_PANEL_ENABLED`, `..._AUDIT_LOG_ENABLED` | 3 sí | `interfaz_ui` |
| 266 | 1 | `STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED` | sí (**hueco §1.4**) | `capabilities_optin` |
| 271 | 4 | `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED`, `..._WRITER_ROUTED_ENABLED`, `..._PUBLISH_GATE_PRECISE_ENABLED`, `..._REASON_VISIBLE_ENABLED` | no | `flujo_funcional` |
| — | **34** | **TOTAL** | | |

---

## 3. Colisiones — medidas, no asumidas

### 3.1 La contradicción 270 ↔ 271: RESUELTA. **El 270 NO depende del 271.**

Se midió por símbolos, no leyendo declaraciones:

```
Símbolos NUEVOS del 270 buscados DENTRO del doc del 271:
  tracker_write_router 0 · close_intent 0 · ticket_state_writeback 0 · incidentDivergence 0
  STACKY_TRACKER_STATE_WRITE_ROUTING 0 · STACKY_TICKET_STATE_WRITEBACK 0 · STACKY_INCIDENT_DIVERGENCE_BADGE 0
                                                                              → 7/7 = CERO hits

Símbolos NUEVOS del 271 buscados DENTRO del doc del 270:
  final_state_resolver → líneas 35, 250     final_state_outcome → línea 250
  STACKY_FINAL_STATE_  → líneas 246, 250    finalStateOutcome   → línea 238
  Sección "Frontera con el plan 271" = 223-255.  Fases del 270 = 394-1548.
                                → TODOS los hits están FUERA del bloque de fases
```

**Ninguna fase del 270 consume un símbolo del 271, y el 271 ignora al 270 por completo.** Los dos docs lo declaran de forma concordante e independiente: `270:250` — *"ningún criterio de aceptación de uno depende de un símbolo del otro… el 270 NO está bloqueado por el 271"*; `271:7` — *"**Depende de:** nada"*; `271:1683` (R10) — *"Merge: hacer el del 270 primero si ambos están listos."*

**El orden `271 → 270 → 269` que afirma el 269 (`:123`, `:2092`) es una capa SEMÁNTICA, no una dependencia de build.** Medido: el 269 tampoco consume símbolos del 270 ni del 271 (**0 hits en los 7 símbolos**). Los tres son independientes a nivel de símbolo. Lo que los ata son **archivos compartidos**, no contratos.

**Orden operativo adoptado: 270 → 269. El 271 va aparte (OLA 2) y no bloquea a nadie.** Razón (de los propios docs): el 270 edita `api/tickets.py` y el 271 lo declara intocable, así que el 271 nunca conflictúa contra el 270 en ese archivo; al revés sí habría que rebasar.

### 3.2 Colisiones reales de la OLA 1 — la premisa que circulaba estaba mal

Se afirmaba que 271/270/269 comparten `api/tickets.py`, `api/incident_inbox.py`, `IncidentInboxPage.tsx` y `harness/task_states.py`. **Medido, es distinto:**

| Archivo | 259 | 267 | 268 | 269 | 270 | Realidad |
|---|:-:|:-:|:-:|:-:|:-:|---|
| `backend/api/tickets.py` | · | · | · | **NO** | **SÍ** | **Un solo dueño (270).** El 269 lo *lee*; el 271 lo declara intocable ⇒ **no era compartido** |
| `backend/harness/task_states.py` | · | · | · | NO | **NO** | **Nadie de la OLA 1.** Sólo el 271 (OLA 2) ⇒ **no era compartido** |
| `backend/api/incident_inbox.py` (179 líneas) | · | · | · | **SÍ** | **SÍ** | **Colisión real, 2 planes** |
| `frontend/src/pages/IncidentInboxPage.tsx` (569 líneas) + `.module.css` | · | · | · | **SÍ** | **SÍ** | **Colisión real, 2 planes** |
| `backend/api/executions.py` | · | · | · | **SÍ** (`list_executions:96`, `executions_history:443`) | · | **Colisión con el 271** (`_with_outcome:65`) — **no figuraba en ninguna lista** |
| `frontend/src/api/endpoints.ts` | **SÍ** | NO | **SÍ** | **SÍ** | NO | **3 de 4 paquetes** ← el cuello que la costura de flags no resuelve |
| `backend/api/diag.py` | **SÍ** (F4.c) | · | · | **SÍ** (F8) | · | Colisión real, 2 planes |
| `backend/api/__init__.py` | **SÍ** | **SÍ** | · | · | · | Colisión real, 2 planes (1-2 líneas c/u) |
| `harness_defaults.env` (`backend/` y `deployment/`) | · | · | **SÍ** | · | **SÍ** (los dos) | Colisión real, 2 planes |
| `docs/sistema/error_fingerprints.json` | **SÍ** | **SÍ** | **NO** | **SÍ** | **SÍ** | 4 planes. **Ojo: la ruta es `docs/sistema/`, no `backend/services/`** |
| bloque de flags (7 archivos) | SÍ | SÍ | parcial | SÍ | SÍ | **4 de 4** → lo absorbe la costura P0 |

Notas medidas:
- **268 es el menos acoplado**: **no** toca `run_harness_tests.{sh,ps1}` (crea 0 tests `.py`) ni `error_fingerprints.json` (excluido a propósito por su bloqueante B8/v3).
- **267 NO toca `endpoints.ts`** (0 ocurrencias); sólo consume funciones existentes.
- **271 NO toca `test_harness_flags.py`** (reemplaza `_CURATED_DEFAULTS_ON` por su propio `test_plan271_flags.py`) — una excepción a la receta de 7 patas.
- **265 tiene prohibición dura** de editar `plans_board.py`, que el 263 reescribe ⇒ 263 y 265 **no colisionan por construcción**.
- **263 ∩ 264** comparten `PlansBoardPage.tsx` **particionado por región**: 263 = CSS module + panel al final del árbol; 264 = fila de acciones de la card.
- **260 → 267**: verificado que el 267 sólo *lee* flags de superficie del 260 (`STACKY_PIPELINE_ENV_MATRIX_ENABLED` etc., **ya existentes**), no las que el 260 crea ⇒ **no hay dependencia de orden**.

---

## 4. Paquetes

### P0 — COSTURA DE FLAGS · 1 agente · **CORRE SOLO, ANTES DE TODO**

**No implementa ninguna fase de ningún plan.** Escribe una sola vez el bloque de 7 archivos con las **15 flags de la OLA 1** (o las 34, si el operador desbloquea la OLA 2 — ver Decisión 1).

Qué hace, exactamente:
1. `backend/config.py` — 15 atributos, cada uno en un bloque contiguo `# Plan NNN`, con su `default=` explícito (13 ON; `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` sin `default=` ⇒ OFF).
2. `backend/services/harness_flags.py` — 15 `FlagSpec` + 15 keys en su `_CATEGORY_KEYS` correspondiente (`paridad_proveedores` 6, `devops` 3, `capacidades_optin` 1, `observabilidad_notif` 5).
3. `backend/services/harness_flags_help.py` — 15 entradas `PLAIN_HELP` **literales del doc de cada plan, sin parafrasear**, que ya vienen medidas contra las 6 reglas del gate.
4. `backend/tests/test_harness_flags.py` — 14 keys en `_CURATED_DEFAULTS_ON` (todas menos la OFF).
5. `backend/tests/test_harness_flags_requires.py` — 3 aristas en `_REQUIRES_MAP_FROZEN` (267 ×2, 268 ×1).
6. `backend/scripts/run_harness_tests.sh` **y** `.ps1` — registra los **28** `test_planNNN_*.py` de la OLA 1 en AMBOS, con la sintaxis propia de cada uno.
7. **NO** toca `harness_defaults.env`, `endpoints.ts`, `api/__init__.py`, ni ningún archivo de producto.

**Gate de salida (binario, hay que pegarlo):** `pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_harness_flags_help.py -q` con **su** delta verde, `python -m compileall backend`, y `grep -c` por key en `FLAG_REGISTRY` / `_CURATED_DEFAULTS_ON` / `PLAIN_HELP` = **1** cada una (cazar el duplicado silencioso).
**Ojo — rojo ajeno conocido:** `test_harness_flags_help.py` arrastra 4 fallos preexistentes. Criterio = **delta**, no "todo verde".

---

### P1 — CIERRE REAL DEL TRACKER · **270 → 269** (secuencial adentro) · 1 agente

**Por qué juntos y no en paralelo:** comparten `backend/api/incident_inbox.py` (**179 líneas**) y `frontend/src/pages/IncidentInboxPage.tsx` (**569 líneas**) + su `.module.css`. Son archivos chicos donde dos agentes en el mismo árbol se pisan sin conflicto de git. **Orden 270 primero** (§3.1).

**Footprint** — CREATE: `services/close_intent.py`, `services/tracker_write_router.py`, `services/ticket_state_writeback.py`, `services/run_verdict.py`, `services/run_evidence.py`, `frontend/src/incidents/incidentDivergence.ts`, `frontend/src/utils/runVerdict.ts`, `frontend/src/components/reconciliationActions.ts`. MODIFY: `services/gitlab_provider.py` (`update_item_state:228-260`, mata el fallback `reopen` de `:251`), `api/tickets.py` (F3 `finish_work:2073-2094` + `set_stacky_status_by_ado:1486-1508`; F4; F7 `:1934`), `api/incident_inbox.py`, `api/executions.py` (`:96`, `:443`), `api/diag.py`, `frontend/src/pages/IncidentInboxPage.tsx` + `.module.css`, `ExecutionHistoryPage.tsx` + `.module.css`, `services/tablePrefs.ts`, `incidents/incidentInboxModel.ts`, `api/endpoints.ts`, `harness_defaults.env` (×2), `docs/sistema/error_fingerprints.json`.
**Flags:** 8 (3 del 270 + 5 del 269) — **las declara P0, no este paquete**.
**Disjunto porque:** único dueño de `api/tickets.py`, `incident_inbox.py`, `IncidentInboxPage.tsx`, `gitlab_provider.py`, `executions.py`, `ExecutionHistoryPage.tsx`. Roza a P2 en `api/diag.py` y `endpoints.ts`.
**Prohibido:** tocar `services/agent_completion_internal.py`, `services/completion_state.py`, `harness/task_states.py`, `tests/test_b2_transition_from_config.py` — territorio del 271. El 270 sólo los **lee por AST** en su centinela F6.

---

### P2 — ALTA GITLAB + GUÍA VERIFICABLE · **259** · 1 agente

**Footprint** — CREATE: `services/setup_guides.py`, `services/gitlab_setup_check.py`, `api/setup_guide.py`, `frontend/src/hooks/usePlan259Flags.ts`, `frontend/src/projects/newProjectGitlabModel.ts`, `frontend/src/projects/setupGuideModel.ts`, `frontend/src/components/SetupGuideDialog.tsx`. MODIFY: `api/__init__.py`, `api/projects.py`, `api/diag.py`, `api/harness_flags.py` (`set_flag_values`), `project_manager.py`, `services/secrets_store.py`, `services/gitlab_client.py`, `services/tracker_provider.py:130-136`, `services/client_profile_default_templates.py`, `frontend/src/types.ts`, `NewProjectModal.tsx` + `.module.css`, `EditProjectModal.tsx`, `api/endpoints.ts`, `docs/sistema/error_fingerprints.json`.
**Flags:** 3 — **las declara P0**.
**Disjunto porque:** único dueño de todo el eje de alta/credenciales GitLab (`secrets_store.py`, `gitlab_client.py`, `project_manager.py`, los dos modales de proyecto). Roza a P1 en `api/diag.py` y `endpoints.ts`; a P3 en `api/__init__.py`.
**Cierra un bug VIVO de corrupción de datos:** hoy apretar GitLab en el modal de Edición y guardar **convierte el proyecto en Azure DevOps en silencio**.

---

### P3 — CATÁLOGO ÚNICO DE ACCIONES DEVOPS · **267** · 1 agente

**Footprint** — CREATE: `services/devops_action_catalog.py`, `services/devops_action_matcher.py`, `services/devops_action_proposal.py`, `api/devops_actions.py`, `frontend/src/services/devopsActionTypes.ts` + `devopsActionRunner.ts` + `devopsActionBindings.ts`, `components/devops/DevOpsActionProposalCard.tsx` + `DevOpsActionConsole.tsx` + `devopsActionConsoleModel.ts`. MODIFY: `api/__init__.py`, `api/devops.py` (`_health_payload:28-108`), `components/commandPaletteData.ts`, `CommandPalette.tsx`, y 6 secciones DevOps (`DevOpsAgentSection`, `BuildWorkshopSection`, `SolutionPublisherSection`, `RemoteConsoleSection`, `TriggerPipelineSection`, `DeploymentsSection`, `PublicationsSection`), `docs/sistema/error_fingerprints.json`.
**Flags:** 3 — **las declara P0**.
**Disjunto porque:** **no toca `endpoints.ts`** (0 ocurrencias) y es el único dueño de todo `components/devops/*` y de la paleta de comandos. Único roce: `api/__init__.py` con P2.

---

### P4 — EXPLORADOR DEL GRAFO DOCUMENTAL · **268** · 1 agente

**Footprint** — CREATE: `frontend/src/docs/graphExplorerState.ts`, `graphPalette.ts`, `graphFilters.ts`, `graphSearch.ts`, `graphNeighborhood.ts`, `graphGrouping.ts`, `graphPreview.ts`, `graphMinimap.ts`, `components/docs/DocGraphFilterBar.tsx`, `DocGraphZoomControls.tsx`, `DocGraphPeek.tsx`, `DocGraphExplorer.module.css`. MODIFY: `api/docs.py` (`get_doc_sources:52`), `deployment/harness_defaults.env`, `api/endpoints.ts`, `docs/docGraphModel.ts`, `graphViewport.ts`, `forceLayout.ts`, `components/docs/DocGraphView.tsx` (el más caliente: F0.3/F1.3/F2.2/F3/F4.2/F5/F6.3/F7) + `.module.css`, `pages/DocsPage.tsx`.
**Flags:** 1 — **la declara P0**.
**Disjunto porque:** único dueño de `frontend/src/docs/*`, `components/docs/*` y `DocsPage.tsx`. **No toca los arneses** (0 tests `.py`) ni `error_fingerprints.json`. Roces: `endpoints.ts` (P1, P2) y `harness_defaults.env` (P1).
**PROHIBIDO:** tocar `frontend/package.json` (G1) y `frontend/src/theme.css`. Y la familia de tokens `--color-*` **no existe**: los reales son `--accent`, `--danger`, `--success`, `--border`, `--text-primary`, `--bg-panel`. El plan ya trae los 6 nombres falsos a corregir en F0.6.

---

### OLA 2 — los 6 que necesitan crítica primero (NO lanzar todavía)

| Paquete | Plan(es) | Orden | Disjunto porque | Pre-requisito |
|---|---|---|---|---|
| **P5** | **271** | después de P1 | Único dueño de `completion_state.py`, `agent_completion_internal.py`, `task_states.py`, `test_b2_transition_from_config.py`. Roza a P1 en `api/executions.py` (`_with_outcome:65` vs handlers `:96`/`:443`) | crítica v3→v4 |
| **P6** | **263 → 264** | secuencial | Comparten `PlansBoardPage.tsx` particionado por región; el 263 reescribe `plans_board.py` | crítica de ambos |
| **P7** | **265** | libre | Consola: `frontend/src/services/console*.ts`, `CodexConsoleDock.tsx`, `api/git.py`. Prohibición dura de tocar `plans_board.py` ⇒ no choca con P6 | crítica v3→v4 |
| **P8** | **260** | libre | Todo el eje de pipelines/variables: `pipeline_env_*`, `ci_*`, `ado_variables`, `gitlab_variables`, `api/ci.py` | crítica v3→v4 |
| **P9** | **266** | libre | Todo `components/dbcompare/*` + `services/dbcompare_*`. No toca `endpoints.ts` | crítica **+ cerrar el hueco §1.4** |

---

## 5. Protocolo de concurrencia

### 5.1 Dueño exclusivo del bloque de flags

**El agente de P0 es el ÚNICO que escribe los 7 archivos del bloque, y lo hace cuando ningún otro agente corre.** Después de que P0 commitea:

> **REGLA DURA para P1..P4: está PROHIBIDO editar `config.py`, `services/harness_flags.py`, `services/harness_flags_help.py`, `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`, `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1`.** Sus flags y sus rutas de test **ya están declaradas**. Si un agente cree que falta una, **para y avisa** — no la agrega.

### 5.2 Dueño único por archivo compartido residual (post-costura)

| Archivo | Dueño | Los demás |
|---|---|---|
| `frontend/src/api/endpoints.ts` | **P1** | P2 y P4 **no lo editan**: dejan sus tipos/llamadas anotados en el reporte y P1 (o el operador) los integra. *Alternativa: Decisión 2* |
| `backend/api/diag.py` | **P2** | P1 anota su cambio de `/run-reconciliation` y lo entrega |
| `backend/api/__init__.py` | **P2** | P3 anota su `import` + `register_blueprint` y lo entrega |
| `harness_defaults.env` (×2) | **P1** | P4 anota su línea |
| `docs/sistema/error_fingerprints.json` | **append por plan** | Cada uno agrega SU entrada con `log_pattern` **real no nulo** + `self_test.matches`/`clean` coherentes. **`\.` crudo rompe el catálogo ENTERO** |

### 5.3 Qué hace cada agente ANTES de escribir

1. `git worktree list` y `git log --oneline -3` — confirmar que P0 ya entró y que HEAD es el esperado.
2. Releer en frío los archivos que va a tocar. **Los anclajes `archivo:línea` de los planes pueden haber derivado** (medido: el 269 dice `executions_history:442`, el real es **`:443`**).
3. Verificar que sus flags YA existen (las declaró P0) y **no** volver a declararlas.
4. Medir su baseline de rojos ajenos ANTES de tocar nada (fase F0.0 de cada plan) y usar criterios **delta**.

### 5.4 Cómo commitea

```bash
# SIEMPRE con pathspec explícito. NUNCA -a.
git commit -m "feat(plan-NNN): <fase> — <qué>" -- \
  "Stacky Agents/backend/services/nuevo_modulo.py" \
  "Stacky Agents/backend/tests/test_planNNN_x.py"
```

**PROHIBIDO, sin excepción** (hay o puede haber una sesión paralela viva sobre este mismo árbol y HEAD se mueve): `git stash`, `git reset`, `git commit --amend`, `git rebase`, `git checkout <rama>`, `git commit -a`, `git add -A`.

### 5.5 Después de cada merge — cazar el duplicado silencioso

Git hace 3-way **sin marcar conflicto** cuando dos ramas agregan la misma línea de cierre a un objeto existente. Obligatorio tras cada merge:

```bash
python -m compileall "Stacky Agents/backend"          # sintaxis
cd "Stacky Agents/frontend" && npx tsc --noEmit       # tipos
# duplicados por key: cada una debe dar 1
grep -c "STACKY_<KEY>" "Stacky Agents/backend/services/harness_flags.py"
grep -c "STACKY_<KEY>" "Stacky Agents/backend/tests/test_harness_flags.py"
```

---

## 6. Techo de paralelismo — con su número

| Escenario | Techo | Justificación medida |
|---|:-:|---|
| **Hoy (1 árbol, sin costura)** | **2** | Los 4 paquetes de la OLA 1 tocan `harness_flags.py`, `config.py` y `harness_flags_help.py` (**4 de 4**). Un solo working tree ⇒ dos agentes editando el mismo archivo **pierden escrituras EN SILENCIO** (no hay conflicto de git que avise). El techo honesto es 2, y sólo si esos 2 son el par que menos comparte: **P3 (267) + P4 (268)** — no comparten *ningún* archivo entre sí (267 no toca `endpoints.ts`; 268 no toca los arneses ni `api/__init__.py`) |
| **1 árbol + costura mínima P0** | **2** | La costura saca los 7 archivos de flags de la ecuación, pero queda `endpoints.ts` compartido por **3 de 4** paquetes (P1, P2, P4) + `api/diag.py` (2) + `api/__init__.py` (2) + `harness_defaults.env` (2). Mismo modo de falla, otro archivo ⇒ **la costura mínima NO levanta el techo** mientras haya un solo árbol |
| **1 árbol + costura AMPLIA P0** | **3** | Si P0 también pre-declara los tipos/objetos de `endpoints.ts`, la línea de `api/__init__.py` y las de `harness_defaults.env`, quedan 3 paquetes disjuntos de verdad (P2, P3, P4) + P1. El 4º sigue chocando en `error_fingerprints.json` |
| **Costura + 1 worktree por paquete** | **4** | **Hallazgo nuevo:** `runtime_paths.data_dir()` = `backend_root()/data`, es **relativo al árbol**, y `backend/.env` **no** define `STACKY_DATA_DIR` ni `DATABASE_URL` (verificado). Por lo tanto **cada worktree obtiene su PROPIA base de datos** ⇒ desaparece la contención `SQLITE_LOCKED` entre agentes, que era el argumento principal contra los worktrees. Los 4 paquetes corren aislados; los appends aditivos los resuelve el merge 3-way + el protocolo §5.5. Tope real = capacidad del operador para revisar 4 merges, no el árbol |
| **Con la OLA 2 desbloqueada** | **4** (no más) | 9 paquetes ≠ 9 agentes: P5 depende de P1, P6 es secuencial adentro, y los 34 appends al bloque de flags siguen convergiendo en los mismos 7 archivos |

### 6.1 Costo real de los worktrees (para decidir con números)

| Costo | Medido | Mitigación |
|---|---|---|
| `venv` no se copia (gitignored) | **137 MB** por worktree | Recrear, o junction — pero **la junction de `.venv` es un gotcha conocido de la casa que ya rompió antes** |
| `node_modules` no se copia | **311 MB** por worktree | `npm ci`, o junction (mismo riesgo) |
| `backend/data/` nace vacío | la DB viva son ~168 MB en `Stacky Agents/backend/data/` | **Es una VENTAJA**: aislamiento real. Pero el worktree no tiene `active_project.json` ⇒ los tests que asumen proyecto activo cambian de comportamiento |
| `backend/.env` no se copia (gitignored) | 206 bytes | Copiarlo a mano por worktree |
| Deriva de anclajes | los planes anclan a `archivo:línea` del árbol principal | Crear los worktrees **todos desde `4cb6c4a6`**, el mismo commit |

**Recomendación:** los worktrees **sí** levantan el techo de 2 a 4 y son **más seguros** de lo que se creía (DB aislada por construcción), a costa de ~450 MB y un setup manual por paquete. Si el operador no quiere pagar eso, el techo se queda en **2** y la secuencia honesta es: **P0 → (P3 ‖ P4) → (P1 ‖ P2)**, en dos olas de dos.

---

## 7. Recetas de lanzamiento (listas para pegar)

> Cada receta va a un agente **nuevo, con contexto limpio**. La rama es `feat/plan-217-migrador-mantis-gitlab` @ `4cb6c4a6`. Todas las rutas de plan son `Stacky Agents/docs/`. **Ninguna receta pushea.**

### P0 — Costura de flags

```
PERFIL: normal

Trabajás en N:\GIT\RS\STACKY\Stacky, rama feat/plan-217-migrador-mantis-gitlab.
NO uses /implementar-plan-stacky: esta tarea NO implementa ninguna fase de ningún plan.

TAREA: pre-declarar las 15 flags nuevas de los planes 259, 267, 268, 269 y 270 en el bloque
compartido de 7 archivos, de una sola vez, para que después 4 agentes puedan implementar esos
planes en paralelo sin tocar ese bloque.

Las 15 keys, con su plan, su default y su categoria, estan en la tabla §2.3 de
"Stacky Agents/docs/_supervision/PAQUETES_PARALELIZACION_2026-07-28_v2.md". Leela primero.
Los textos de PlainHelp los saca LITERALES del doc de cada plan (prohibido parafrasear:
el gate test_harness_flags_help.py aplica 6 reglas y ya estan medidos ahi).

Los 7 archivos son (RUTAS EXACTAS, verificadas — NO existe "Stacky Agents/scripts/"):
  Stacky Agents/backend/config.py
  Stacky Agents/backend/services/harness_flags.py          (FlagSpec + _CATEGORY_KEYS)
  Stacky Agents/backend/services/harness_flags_help.py     (PLAIN_HELP)
  Stacky Agents/backend/tests/test_harness_flags.py        (_CURATED_DEFAULTS_ON :467, igualdad de conjuntos)
  Stacky Agents/backend/tests/test_harness_flags_requires.py (_REQUIRES_MAP_FROZEN :120, igualdad de conjuntos)
  Stacky Agents/backend/scripts/run_harness_tests.sh       (HARNESS_TEST_FILES, 687 rutas hoy)
  Stacky Agents/backend/scripts/run_harness_tests.ps1      ($HarnessTestFiles, 623 rutas, sintaxis DISTINTA)

REGLAS:
- Un bloque contiguo "# Plan NNN" por plan en cada archivo. No reordenes nada existente.
- 14 flags default ON van tambien en _CURATED_DEFAULTS_ON. STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED
  va SIN default= (queda OFF) y NO va en esa lista.
- 3 aristas requires= van en _REQUIRES_MAP_FROZEN (2 del 267, 1 del 268).
- Registra los 28 archivos test_planNNN_*.py de esos 5 planes en AMBOS arneses.
- NO toques harness_defaults.env, endpoints.ts, api/__init__.py, ni ningun archivo de producto.

GATE (pega el output real):
  cd "Stacky Agents/backend" && ./venv/Scripts/python.exe -m pytest tests/test_harness_flags.py \
     tests/test_harness_flags_requires.py tests/test_harness_flags_help.py -q
  Baseline: test_harness_flags_help.py arrastra 4 fallos AJENOS preexistentes. Criterio = DELTA:
  ninguna de TUS 15 keys falla, y el conteo total de fallos no sube.
  python -m compileall "Stacky Agents/backend"
  Por cada key: grep -c debe dar exactamente 1 en harness_flags.py y en test_harness_flags.py.

COMMIT: git commit con pathspec explicito de los 7 archivos. SIN push.
PROHIBIDO: git stash / reset / amend / rebase / checkout / commit -a (hay sesion paralela viva).
```

### P1 — Cierre real del tracker (270 → 269)

```
PERFIL: normal
/implementar-plan-stacky 270

Contexto obligatorio antes de empezar:
- Rama feat/plan-217-migrador-mantis-gitlab. Las 8 flags de los planes 270 y 269 YA ESTAN
  DECLARADAS por el paquete P0. PROHIBIDO editar config.py, services/harness_flags.py,
  services/harness_flags_help.py, tests/test_harness_flags*.py y
  backend/scripts/run_harness_tests.{sh,ps1}. Si crees que falta una flag, PARA y avisa.
- Implementa PRIMERO el plan 270 completo (v5, APROBADO-CON-CAMBIOS). Cuando cierre, y en la
  MISMA corrida, implementa el plan 269 (v4, APROBADO-CON-CAMBIOS, prohibicion LEVANTADA).
  Van juntos porque comparten api/incident_inbox.py (179 lineas) y
  frontend/src/pages/IncidentInboxPage.tsx (569 lineas); en paralelo se pisarian.
- El 270 NO depende del 271 (medido: 0 hits cruzados de simbolos). El 271 es de OTRO paquete.
  PROHIBIDO tocar: services/agent_completion_internal.py, services/completion_state.py,
  harness/task_states.py, tests/test_b2_transition_from_config.py. El 270 solo los LEE por AST.
- Sos el DUENO de: api/tickets.py, api/incident_inbox.py, api/executions.py,
  frontend/src/api/endpoints.ts, harness_defaults.env (los dos), IncidentInboxPage.tsx,
  ExecutionHistoryPage.tsx, gitlab_provider.py.
  api/diag.py es del paquete P2: NO lo edites; anota tu cambio de /run-reconciliation en el reporte.
- Los anclajes archivo:linea pueden haber derivado. Medido: el 269 dice executions_history:442,
  el real es :443. Reverifica cada anclaje abriendo el archivo antes de editar.
- Bug real que cierra el 270: en GitLab "cerrar" hoy manda state_event: reopen
  (gitlab_provider.update_item_state, el fallback de :251).

TDD real, tests corridos con "Stacky Agents/backend/venv/Scripts/python.exe -m pytest <archivo> -q",
por archivo (nunca la suite completa). Pega el output. Commits con pathspec explicito. SIN push.
PROHIBIDO: git stash / reset / amend / rebase / checkout / commit -a.
```

### P2 — Alta GitLab + guía verificable (259)

```
PERFIL: normal
/implementar-plan-stacky 259

Contexto obligatorio:
- Plan 259 v4, APROBADO-CON-CAMBIOS (juez independiente, 2a pasada). Rama feat/plan-217-...
- Las 3 flags (STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED, STACKY_SETUP_GUIDE_ENABLED,
  STACKY_SETUP_GUIDE_VERIFY_ENABLED) YA ESTAN DECLARADAS por P0. PROHIBIDO editar el bloque
  de 7 archivos de flags.
- Sos el DUENO de: api/__init__.py, api/projects.py, api/diag.py, api/harness_flags.py,
  project_manager.py, services/secrets_store.py, services/gitlab_client.py,
  services/tracker_provider.py, services/client_profile_default_templates.py,
  NewProjectModal.tsx, EditProjectModal.tsx, frontend/src/types.ts.
  frontend/src/api/endpoints.ts es del paquete P1: NO lo edites; anota tus tipos en el reporte.
- DATOS PERSONALES / CREDENCIALES — leer §8 del doc de paquetes antes de F3 y F4:
  * F3 toca secrets_store.py. read_secret_from_file:277-279 REESCRIBE el archivo del operador
    al migrar un secreto plano a DPAPI, y eso ata el archivo cifrado a ESE usuario de Windows.
    El plan ya manda fallback al lector plano + cubrir el caso de archivo no escribible. Hacelo.
  * F4 define el chequeo chk-token, que habla con /user de GitLab con la credencial REAL del
    operador. NO loguees ni devuelvas el cuerpo crudo de esa respuesta (trae el usuario GitLab).
  * PROHIBIDO poner tokens, PATs, correos o nombres de usuario reales en fixtures, en
    self_test.matches/clean de error_fingerprints.json, o en los textos de PlainHelp.
- Bug VIVO que cierra: hoy elegir GitLab en el modal de Edicion y guardar convierte el proyecto
  en Azure DevOps EN SILENCIO (corrupcion de datos).

TDD real. Tests: "Stacky Agents/backend/venv/Scripts/python.exe -m pytest <archivo> -q", por archivo.
Si tocas UI: cd "Stacky Agents/frontend" && npx tsc --noEmit. Pega los outputs.
Commits con pathspec explicito. SIN push. PROHIBIDO stash/reset/amend/rebase/checkout/commit -a.
```

### P3 — Catálogo único de acciones DevOps (267)

```
PERFIL: normal
/implementar-plan-stacky 267

Contexto obligatorio:
- Plan 267 v4, APROBADO-CON-CAMBIOS (2a pasada independiente). Rama feat/plan-217-...
- Las 3 flags YA ESTAN DECLARADAS por P0 (ojo: STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED quedo
  SIN default= a proposito, o sea OFF). PROHIBIDO editar el bloque de 7 archivos de flags.
- Sos el DUENO de: services/devops_action_*.py, api/devops_actions.py, api/devops.py,
  components/commandPaletteData.ts, CommandPalette.tsx y TODO components/devops/*.
  api/__init__.py es del paquete P2: NO lo edites; anota tu import + register_blueprint
  en el reporte para que P2 lo integre.
- Este plan NO toca frontend/src/api/endpoints.ts (0 ocurrencias): solo consume funciones
  que ya existen. Si te parece que necesitas agregar algo ahi, PARA y avisa.
- El 267 no depende del 260: verificado que solo LEE flags de pipeline que YA existen
  (STACKY_PIPELINE_ENV_MATRIX_ENABLED y companeras), no las que el 260 crea.
- error_fingerprints.json esta en "Stacky Agents/docs/sistema/", NO en backend/services/.
  Tu entrada necesita log_pattern REAL no nulo y self_test.matches/clean coherentes; un "\."
  crudo rompe el catalogo ENTERO.

TDD real. Tests por archivo con el venv. tsc --noEmit si tocas UI. Pega los outputs.
Commits con pathspec explicito. SIN push. PROHIBIDO stash/reset/amend/rebase/checkout/commit -a.
```

### P4 — Explorador del grafo documental (268)

```
PERFIL: normal
/implementar-plan-stacky 268

Contexto obligatorio:
- Plan 268 v4, APROBADO-CON-CAMBIOS sobre el v3. Rama feat/plan-217-...
- La flag STACKY_DOCS_GRAPH_EXPLORER_ENABLED YA ESTA DECLARADA por P0. PROHIBIDO editar el
  bloque de 7 archivos de flags. Este plan crea 0 tests .py, asi que no toca los arneses.
- Sos el DUENO de: TODO frontend/src/docs/*, TODO components/docs/*, pages/DocsPage.tsx,
  api/docs.py.
  frontend/src/api/endpoints.ts es del paquete P1 y harness_defaults.env tambien: NO los edites;
  anota tu cambio de DocsSourcesResponse y tu linea de harness_defaults.env en el reporte.
- PROHIBIDO tocar frontend/package.json (regla G1: cero dependencias nuevas) y
  frontend/src/theme.css.
- La familia de tokens CSS --color-* NO EXISTE en este tema. Los reales son --accent, --danger,
  --success, --border, --text-primary, --bg-panel. F0.6 del plan ya lista los 6 nombres falsos
  a corregir: corregilos, no los inventes de nuevo.
- No hay React Testing Library ni jsdom: toda la logica va en modulos .ts PUROS probados con
  vitest sin DOM; los .tsx son cascarones delgados. Prohibido tests de componente React.
- Los ratchets uiDebtRatchet y motionDebtRatchet YA ESTAN ROJOS por deuda ajena (medido en F0.0
  del plan: 2 y 7 archivos regresivos). Criterio = DELTA: ningun archivo tuyo aparece en una
  linea REGRESION y el conteo no sube. PROHIBIDO regenerar cualquier baseline.
- Cuidado con los closures stale: todo valor que lea draw() va por useRef (regla G12).

Tests: cd "Stacky Agents/frontend" && npx vitest run <archivo> ; y npx tsc --noEmit.
Correlos POR ARCHIVO (la corrida completa contamina cross-file). Pega los outputs.
Commits con pathspec explicito. SIN push. PROHIBIDO stash/reset/amend/rebase/checkout/commit -a.
```

### Recetas de la OLA 2 (sólo después de la crítica)

```
PERFIL: normal
/criticar-y-mejorar-plan 271     # y luego 260, 263, 264, 265, 266

Los 6 estan en v3 con su ULTIMO veredicto = RECHAZADO y la version vigente NUNCA fue juzgada
por un juez independiente. Historial medido de la serie: el v2 de 259, 267, 268, 269 y 270
introdujo bloqueantes PROPIOS en 5 de 5 casos, y salieron de EJECUTAR, no de releer.
El juez tiene que correr el codigo, los greps, los conteos y los numeros de plan.

Insumo OBLIGATORIO para la critica del 266 (medido, ninguna critica anterior lo vio):
declara la flag STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED con requires="STACKY_DB_COMPARE_ENABLED"
pero el doc menciona _REQUIRES_MAP_FROZEN y test_harness_flags_requires.py CERO veces.
El assert de tests/test_harness_flags_requires.py:316 es igualdad de conjuntos con reporte de
Extras => implementarlo verbatim pone ese test ROJO. Falta la 6a pata del cableado.
```

---

## 8. RIESGOS DE DATOS PERSONALES

> Sección obligatoria. Barrido dirigido sobre los 11 planes pendientes buscando PII, tokens, PATs, correos y nombres de usuario.

### 8.1 Resultado del barrido

| Plan | Superficie sensible | Riesgo concreto | Severidad |
|---|---|---|:-:|
| **259** (P2) | `services/secrets_store.py`, `services/gitlab_client.py`, chequeo `chk-token` | **(a)** `chk-token` (`:497`, `:1199`) habla con `/user` de GitLab con la credencial real y *"el veredicto real lo da chk-token, que sí habla con /user"* — la respuesta trae el **nombre de usuario GitLab**; si se loguea o se devuelve cruda en el body, se filtra identidad. **(b)** `read_secret_from_file:277-279` **reescribe el archivo del operador** al migrar un secreto plano a DPAPI ⇒ el cifrado queda **atado a ese usuario de Windows**: otro usuario (o un servicio) no puede descifrarlo, y un `gitlab_auth.json` de sólo lectura pasa de funcionar a `TrackerConfigError`. **(c)** el alta escribe un token de GitLab nuevo. | **ALTA** |
| **260** (P8) | `ado_variables.py`, `gitlab_variables.py`, gate de secretos literales | Maneja **variables secretas de pipeline de ADO y GitLab**. Su flag `STACKY_PIPELINE_ENV_DECLARE_ENABLED` es la única ruta nueva que **escribe en el sistema externo real del operador** — por eso nace **OFF**, y así debe quedar. El gate de commit de secretos, si corre **después** del enmascarado, falla abierto. | **ALTA** |
| **265** (P7) | `console_secret_mask.py`, `api/git.py`, `console_audit.py` | Expone **contenido del repo** por HTTP (`/status`, `/diff`, read-only) y escribe un **log de auditoría a disco**. El enmascarado tiene que correr **antes** de que el diff salga del proceso; `console_audit.py` escribe **sin enmascarar** si la máscara no se aplicó aguas arriba. | **ALTA** |
| **269** (P1) | `X-User-Email` → `changed_by` | Propaga el **correo del operador** a la traza de cambio de estado del ticket (`set_status`). Queda persistido en la base y visible en la UI. | **MEDIA** |
| **270** (P1) | `api/tickets.py`, `gitlab_provider.py` | **Escribe en el tablero real de ADO/GitLab del operador** (cambia el estado de work items). Efecto colateral **externamente visible e irreversible** sobre datos de terceros. El plan blinda el riesgo R5 en tres lugares y **prohíbe** el endpoint `by-ado`; respetarlo. | **MEDIA** |
| **271** (P5) | `agent_completion_internal.py`, `completion_state.py` | Ídem: cambia lo que se escribe en un tracker de terceros. Además `final_state_resolver.py` define **27 razones** que se persisten y se muestran. | **MEDIA** |
| **266** (P9) | `dbcompare_masking.py`, `PageErrorBoundary.tsx` | Comparador de **bases de datos reales**: los payloads de diff pueden contener datos productivos. Y el plan hace el **stack trace copiable** desde la UI — un stack puede arrastrar valores de fila. | **MEDIA** |
| **267** (P3) | catálogo de acciones DevOps | Las acciones disparan despliegues/pipelines; los `ConfirmRequest` pueden citar rutas y nombres de proyecto. Sin PII directa. | **BAJA** |
| **263** (P6) | `plans_board.py` | Sólo metadata de planes. | **BAJA** |
| **264** (P6) | selector de modelo/effort | Sin PII. | **BAJA** |
| **268** (P4) | grafo documental | **Sin PII.** ⚠️ **Falso positivo desarmado:** el barrido textual da 83 coincidencias de "token" en este doc, pero medido (`grep -oiE "token[a-z]*" \| uniq -c`) son **48 `token` + 29 `tokens` + 19 `TOKENS` + 7 `TokenNames`** referidos a **tokens de DISEÑO CSS** (`--accent`, `--danger`, …), no a credenciales. | **NULA** |

### 8.2 Reglas transversales para los agentes que implementen

1. **Cero PII real en fixtures.** Ni correos, ni PATs, ni tokens, ni nombres de usuario, ni títulos de ticket reales, ni rutas de proyecto del operador — tampoco en `self_test.matches` / `self_test.clean` de `error_fingerprints.json`, ni en los ejemplos de `PlainHelp` (que se renderizan en la UI).
2. **Un literal con forma de token bloquea el push** (protección de secretos de GitHub). Si un test necesita algo con forma de credencial, **partir el string**.
3. **El enmascarado va ANTES del gate, nunca después.** Enmascarar después de la comprobación anula la comprobación (falla abierto).
4. **DPAPI es sólo-Windows y por-usuario.** Cualquier cosa que cifre con DPAPI queda atada al usuario que la cifró. Documentarlo y dejar fallback de lectura.
5. **El arnés escribe en la base VIVA** (`Stacky Agents/backend/data/stacky_agents.db`, ~168 MB, con datos reales del operador). Los tests que tocan la DB son **flaky por `SQLITE_LOCKED`** con shared-cache. Un worktree propio evita ambas cosas (§6.1).
6. **259, 260 y 265 mueven credenciales.** Recomendación: que el operador confirme explícitamente antes de que esos tres se implementen, y que P2/P7/P8 no corran desatendidos.

---

## 9. Las 3 decisiones que necesitan al operador

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **1** | **Alcance de la costura P0** | (a) **mínima**: 15 flags de la OLA 1. (b) **total**: las 34 de los 11 planes. (c) **amplia**: 15 flags + `endpoints.ts` + `api/__init__.py` + `harness_defaults.env` | **(c)** si se quiere paralelismo real; **(a)** si se prefiere el commit más chico y auditable. La (b) declara flags de 6 planes que todavía pueden cambiar de forma en su crítica |
| **2** | **¿Worktrees separados, sí o no?** | (a) 1 árbol → techo **2**, secuencia P0 → (P3‖P4) → (P1‖P2). (b) 1 worktree por paquete → techo **4**, costo ~450 MB y setup manual por worktree | **(b)**. El argumento que los frenaba (DB compartida) **quedó desarmado midiendo**: `data_dir()` es relativo al árbol y `.env` no lo sobreescribe ⇒ cada worktree tiene su propia base |
| **3** | **Qué hacer con los 6 de la OLA 2** | (a) criticar los 6 antes de tocarlos. (b) implementar igual (precedente medido: la serie 246-252 fue RECHAZADA 7/7 y se implementó igual). (c) criticar sólo el 271 y el 266 (los de más riesgo) | **(a)** para el **266** — tiene un bloqueante medido y no juzgado (§1.4) — y **(c)** como mínimo. La serie 259-270 muestra que **5 de 5** revisiones v2 introdujeron bloqueantes propios que sólo aparecieron **ejecutando** |

---

## 10. Trazabilidad de las mediciones de este documento

| Afirmación | Comando |
|---|---|
| 222 docs / 143 de 3 dígitos / 79 de 2 dígitos | `ls "Stacky Agents/docs/" \| grep -cE "^[0-9]{3}_PLAN_"` |
| 112 planes con tests | `find . -type f -name "test_plan*" -not -name "*.pyc"` |
| 11 pendientes reales | `comm -23` de universo vs señales + `git log --all --grep="plan-NN"` sin `docs(...)` |
| Veredictos | `grep -nE 'VEREDICTO\|Veredicto\|^\*\*Estado:\*\*'` en cada doc |
| 100/101 obsoletos | `sed -n '3p'` de cada doc |
| 34 flags ausentes | `grep -rl "<KEY>" config.py services/harness_flags.py` |
| Imanes de merge | `git log --all --oneline -- "<ruta>" \| wc -l` |
| Bloque de 7 archivos | `git show --stat 0b38da29` y `c077c743` |
| 687 vs 623 rutas de arnés | `grep -cE "^\s*tests/"` / `grep -cE "^\s*['\"]tests/"` |
| 270 ⊥ 271 | `grep -c` de los 7 símbolos nuevos de cada uno en el doc del otro |
| DB por worktree | `runtime_paths.py:48-54` + `grep -nE "STACKY_DATA_DIR" backend/.env` (sin hits) |
| Hueco del 266 | `grep -c "_REQUIRES_MAP_FROZEN" 266_*.md` = 0 vs `test_harness_flags_requires.py:316` |
| Un solo worktree | `git worktree list` |

**Este documento no implementa nada, no mergea nada y no pushea nada.**
