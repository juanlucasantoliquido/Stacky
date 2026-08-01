# Plan 279 — El copiloto de pipelines: un solo hilo conversacional

**Estado:** v2 (MEJORADO — criticado). Veredicto v1: **RECHAZADO** (4 bloqueantes). v2 los resuelve.
**Rama:** `docs/plan-279`
**Origen:** pedido del operador (2026-08-01): rediseñar la creación y gestión de pipelines como experiencia *agentic-first*.
**Tipo:** orquestación de capacidades existentes. **NO** reimplementa generación, lint, diff, auditoría, preflight ni matriz de entornos.
**Juez v2: subagente independiente, misma corrida, contexto limpio**

## CHANGELOG v1 -> v2

Todo lo de abajo se verificó **abriendo los archivos reales** y, donde se podía, **ejecutando el gate**.

| C# | Sev | Qué estaba mal en v1 | Cómo se resolvió en v2 |
|----|-----|----------------------|------------------------|
| **C1** | BLOQ | Criterios mutuamente insatisfacibles: F0 caso 4 exige `writes == 8`, y `tests/test_devops_action_catalog.py:177` exige `len(escrituras) == 7` (**igualdad**, medido). Los criterios "22 passed" (F3) y "115 passed, 0 failed" (F9) eran aritméticamente imposibles. Un modelo menor lo "resuelve" borrando el assert ⇒ falso verde. | F3 **edita** ese assert a `== 8` como parte del ratchet, con caso propio. Conteos recalculados en F3, F9, §9 y §12. |
| **C2** | BLOQ | El gate de K1 era un **substring**: F0 caso 3 y F6 caso 1 sólo pedían que el fuente "referencie `pipeline_copilot_prompt`" — un comentario lo satisface. Y K1 se abría con `grep -c "devops_action_catalog"` y se cerraba con `grep -c "pipeline_copilot_prompt"`: dos métricas distintas. | Gate por **`ast` + comportamiento**: F6 caso 8 exige un `ast.ImportFrom` real y un `ast.Call` a `build_copilot_prompt`; F6 caso 3 es el gate de comportamiento. K1 pasa a tener **una sola** definición. |
| **C3** | BLOQ | Paridad de 3 runtimes **inalcanzable**: `DevOpsAgentSection.tsx:28` declara `type CliRuntime = 'claude_code_cli' \| 'codex_cli'` y el `<select>` (`:147-149`) tiene sólo 2 opciones ⇒ el operador **no puede elegir GitHub Copilot**. Y el gate K6 pegaba a `/api/devops/actions/propose`, que **ignora** el runtime (`devops_actions.py:95`) ⇒ verde sin probar nada. | F8 agrega `github_copilot` al tipo y al `<select>` del copiloto. K6 pasa a pegarle a `/api/devops/agent/start` con `runtime="github_copilot"` y exigir `200 + mode=="deterministic"`, más el `400` con la flag OFF. |
| **C4** | BLOQ | F3 decía que las 6 usan `callEndpoint()` "porque las 6 sí tienen endpoint real", pero la tabla nombraba **funciones de servicio Python** (`lint_yaml()`, `explain_plan()`, `check_placeholders`) que un binding **TypeScript no puede llamar**. Verificado: `frontend/src/api/endpoints.ts` **no** expone cliente para `pipeline-lint/validate` ni `pipeline-lint/explain`. | La tabla de F3 pasa a nombrar **ruta HTTP + función de `endpoints.ts`**, y se declara explícito que agregar 2 wrappers tipados para rutas backend que **ya existen** NO viola §7.4 (que prohíbe **endpoints backend** nuevos). |
| **C5** | IMP | Las 6 acciones no traían `label` ni `summary`, y **el gate de colisión los evalúa**: `test_frases_no_colisionan_entre_read_y_write:114` arma `universo(a) = (*a.phrases, a.label)`. `test_label_y_summary_no_vacios` (`:166`) además exige `summary` no vacío en las 6. | F3 congela los **6 `label` y los 6 `summary`** literales. (Las 18 frases de v1 se verificaron corriendo el gate real: **0 choques**.) |
| **C6** | IMP | Dependencia de flag no declarada: las acciones 1 y 6 envuelven `/api/pipeline-generator/{preview,commit}`, que hacen `abort(404)` si `STACKY_PIPELINE_GENERATOR_ENABLED` está OFF (`api/pipeline_generator.py:37` y `:56`). Con esa flag apagada el copiloto muere con un 404 mudo en su camino principal. | Declarada en F3 y F5, con degradación honesta (`blocked_reason` que nombra la flag) y caso 9 en F5. |
| **C7** | IMP | El piso `>= 23` de `devopsActionCatalogRatchet.test.ts:62` quedaba **sin apretar** (v1 sólo subía `:56` y `:67`). Un ratchet que no se aprieta es inerte. | F3 sube también `:62` a `29`. |
| **C8** | IMP | F3 declaraba "`50 passed` salvo uno rojo": un criterio binario no puede decir eso. | F3 declara literal **`49 passed, 1 failed`** y nombra el nodeid del único fallo esperado. |
| **C9** | IMP | `stacky_logger` no expone `.info()` a nivel módulo: es un singleton `logger = _StackyLogger()` (`services/stacky_logger.py:511`). El snippet de F9 (`stacky_logger.info(...)`) sólo funciona con el `import ... as` del precedente. | F9 fija el import literal `from services.stacky_logger import logger as stacky_logger`. |
| **C10** | IMP | 9 anclajes desfasados (ninguno inexistente). Ver tabla de anclajes abajo. | Corregidos con la línea real. Ninguno sostenía una decisión de alcance. |
| **C11** | MEN | Ninguna huella en `docs/sistema/error_fingerprints.json` (0 menciones de "279"), pese a que el plan mata dos clases de error. | F9 registra 1 huella. |
| **C12** | MEN | `pipeline_stack_detector.py:13-15` citado para los 3 stacks; los literales viven en `_MANIFEST_SIGNALS` (`:12-16`). | Anclaje corregido. |
| **[ADICIÓN ARQUITECTO]** | — | v1 admite en §9.7 que "si el commit falla, el operador revierte con git" — pero **nunca le dice qué revertir**. El human-in-the-loop pide confirmar una escritura sin mostrar el deshacer. | **Deshacer-primero**: la sesión calcula y muestra el `undo_hint` (ruta exacta del archivo + comando de reversión) **antes** de que el operador confirme. Ver §6.F2 / §6.F4 / §6.F5 / §6.F9, todo marcado `[ADICIÓN ARQUITECTO]`. Sin flag nueva, sin trabajo extra, sin endpoint nuevo. |

### Anclajes verificados (v2 los corrige; ninguno se borra)

| Anclaje de v1 | Estado | Línea real |
|---|---|---|
| **TESIS (i)** `devops_agent.py` no importa el catálogo | **OK — CONFIRMADA** | `grep -c "action_catalog\|assistant_actions\|DevOpsAction" api/devops_agent.py` → **0** |
| **TESIS (ii)** `assistant_actions()` lo consume sólo `api/devops_actions.py` | **OK — CONFIRMADA** | único consumidor productivo: `:112` y `:118` (el resto son tests) |
| Baseline "69 casos verdes en 4 suites" | **OK — REPRODUCIDO** | corrido en esta crítica: **`69 passed in 12.83s`** (22+19+15+13) |
| `DEVOPS_ACTION_CATALOG` = 23 acciones, 16 read / 7 write | **OK** | medido: 23 / 16 / 7 |
| `class ActionParam` `:54` | DESFASADO | `:55` (`:54` es el `@dataclass`) |
| `class DevOpsAction` `:64` | DESFASADO | `:65` (`:64` es el `@dataclass`) |
| `ActionProposal` `:47` | DESFASADO | `:48` (`:47` es el `@dataclass`) |
| los 6 `BLOCKED_*` `:22-30` | DESFASADO | `:22-27` (`:30` es `BLOCKED_REASONS`) |
| `remote_console_prompt.py:27-28` (regla de credenciales) | DESFASADO | `:28-29` |
| `devops_actions.py:63-65` (CERO PII) | DESFASADO | `:64-66` |
| `harness_flags.py:6194` (`STACKY_DEVOPS_ACTION_CATALOG_ENABLED`) | DESFASADO | `FlagSpec(` en `:6194`, `key=` en `:6195` — **la afirmación de fondo (sin `requires=`) es CORRECTA** |
| `harness_flags.py:6234-6240` (la OFF sin `default=`) | DESFASADO | `:6232-6240` — **el comentario del repo confirma la TRAMPA nº1 palabra por palabra** |
| `harness_flags.py:3605-3609` (`..._NL_EDIT_COMMIT_...`) | DESFASADO | `key=` en `:3603` |
| `pipeline_stack_detector.py:13-15` | DESFASADO | `_MANIFEST_SIGNALS` en `:12-16`; `detect_stack` en `:19` (OK) |
| `_health_payload` "tras `:116`" | **OK** | el `}` de cierre está en `:117`; la def está en `api/devops.py:28` |
| `catalog:411` (antes del bloque de escrituras) y `:412` (1ª escritura) | **OK — EXACTOS** | `:411` comentario `# 7 de ESCRITURA`, `:412` `DevOpsAction(` |
| `PRJ` `:123` | **OK — EXACTO** | `PRJ = ActionParam(...)` en `:123` |
| `DevOpsPage.tsx` `:145` / `:159` / `:184` / `:296` | **OK — EXACTOS** | 17 secciones medidas |
| `test_devops_action_ratchet.py` `:26 :31 :48 :53 :59 :68 :77 :90 :96 :111 :133` | **OK — LOS 11 EXACTOS** | — |
| `devopsActionCatalogRatchet.test.ts` `:21` / `:47` / caso 5 / caso 6 | **OK** | `:21` regex exacta; `:48` el assert del caso 3; pisos en `:56`, `:62`, `:67` |
| `pipeline_spec/lint/preflight/patcher/diff` (12 anclajes) | **OK — LOS 12 EXACTOS** | `:134 :140 :33 :43 :791 :841 :1031 :37 :79 :102 :537 :803 :81 :197` |
| `pipeline_editor.py` `:60 :141 :171 :199 :428` | **OK — LOS 5 EXACTOS** | — |
| `ci_variables.py:31/:50`, `secrets_store.py:204/:258`, `secret_masking.py:20` | **OK — EXACTOS** | — |
| `run_harness_tests.sh:978-981` / `.ps1:872-875` | **OK** | bloque del plan 267 en `:977-981` / `:871-875` |
| `devops_action_matcher.py` `:14 :15 :16 :28 :49 :59 :80 :100` + docstring `:1-5` | **OK — LOS 9 EXACTOS** | — |
| `devops_agent.py` `:13 :15 :24-28 :31-40 :61 :70 :157 :308 :322 :328` | **OK — EXACTOS** | inserción de F6: bloque `server_alias` en `:129-136` y `:212-222` (OK) |
| Las 18 frases nuevas no colisionan read↔write | **OK — GATE EJECUTADO** | corrí `_content_tokens`+`normalize_text` contra las 23 acciones reales: **0 choques** |

---

## 1. Objetivo y KPI

Hoy Stacky tiene **dos cerebros DevOps que no se hablan**, y las capacidades de pipeline están repartidas en 7 pestañas
que el operador tiene que recorrer a mano, en el orden correcto, trasladando resultados de una a otra.

Este plan pone **un solo hilo conversacional** encima de lo que ya existe: el operador describe en castellano lo que
necesita y el agente interpreta, pregunta solo lo ambiguo, arma el borrador, lo valida, dice qué va a pasar **antes**
de escribir, pide confirmación explícita y entrega un resumen operable. El motor no se reescribe: se **envuelve** el
catálogo tipado del plan 267 y los servicios de pipeline que ya están construidos y verdes.

### KPI binarios

| # | KPI | Hoy (medido en esta corrida) | Meta | Cómo se mide |
|---|-----|------------------------------|------|--------------|
| **K1** | Acciones del catálogo alcanzables desde el **turno del agente** | **0** | **6** | **[C2]** Gate único, por `ast` **y** por comportamiento: F6 caso 8 (hay `ImportFrom` de `services.pipeline_copilot_prompt` **y** una `Call` a `build_copilot_prompt` en `api/devops_agent.py`) **+** F6 caso 3 (el mensaje que llega a `run_agent` está envuelto). **Prohibido medir K1 con `grep`**: un comentario satisface un substring. |
| **K2** | Pestañas que el operador debe visitar para crear una pipeline de cero y dejarla verificada | **≥ 4** (`pipelines`, `editar-pipeline`, `pipeline-audit`, `matriz-entornos`) | **1** (`copiloto-pipelines`) | F8 test 3: la sección nueva declara las 6 acciones sin `nav_path` a otra sección |
| **K3** | Valor de secreto que llega al prompt del modelo | sin gate | **0, con test** | F7 caso 5, **con el guard positivo primero** (§F7): el test afirma que el valor SÍ está en el fixture antes de afirmar que NO está en el prompt |
| **K4** | Acciones del catálogo / deriva catálogo↔bindings | 23 / 0 | 29 / **0** | `devopsActionCatalogRatchet.test.ts` caso 3 (igualdad exacta de conjuntos) |
| **K5** | Estados de creación explícitos y cerrados | **0** (no existe máquina de estados) | **8**, con transiciones cerradas | F2 test 1: `len(PIPELINE_SESSION_STATES) == 8` |
| **K6** | Paridad real de los 3 runtimes en el chat DevOps | **2 de 3** (`DevOpsAgentSection.tsx:28` sólo tipa `claude_code_cli \| codex_cli`) | **3 de 3** | **[C3]** F9 caso 2: `POST /api/devops/agent/start` con `runtime="github_copilot"` → **200 + `mode=="deterministic"`** con la flag ON, y **400** con la flag OFF. **Prohibido medir K6 contra `/api/devops/actions/propose`**: ese endpoint **ignora** el runtime (`api/devops_actions.py:95`) y daría verde sin probar nada. |
| **K7** | `[ADICIÓN ARQUITECTO]` Escrituras que el operador confirma **viendo su deshacer** | **0** | **1/1** (la única write del plan) | F9 caso 6: la sesión en `confirm` expone `undo_hint` no vacío con la ruta exacta del archivo |

**Baseline de tests medido hoy (todos VERDES, con `backend/venv`, py3.11.9).
REPRODUCIDO por el juez en esta misma corrida: `69 passed in 12.83s`.**

| Suite | Casos verdes hoy |
|---|---|
| `backend/tests/test_devops_action_catalog.py` | 22 |
| `backend/tests/test_devops_actions_api.py` | 19 |
| `backend/tests/test_devops_action_matcher.py` | 15 |
| `backend/tests/test_devops_action_ratchet.py` | 13 |
| **Total** | **69** |

Cualquier rojo en estas 4 suites durante la implementación **es del implementador**, no heredado.

---

## 2. Por qué ahora — el gap medido

### 2.1 Las dos piezas caras ya existen

**(a) Registro de herramientas tipado — `backend/services/devops_action_catalog.py` (663 líneas, plan 267).**
Es puro (sin flask, sin IO, sin red) y ya modela exactamente lo que un agente necesita para actuar con seguridad:

- `CATALOG_VERSION` (`:12`), `EFFECTS = ("read","write")` (`:14`), `IMPACTS = ("none","low","high")` (`:15`),
  `PARAM_TYPES` (`:16`), `REACHES` (`:21`), `REACH_READ` (`:27`), `REACH_WRITE` (`:28`), `canonical_reach()` (`:31`).
- `@dataclass(frozen=True) class ActionParam` (`:55`) y `class DevOpsAction` (`:65`), con `phrases` (`:78`) —
  **frases de intención para matcheo determinista**.
- `DEVOPS_ACTION_CATALOG` (`:146`): **23 acciones**, 16 de lectura (desde `:148`) y 7 de escritura (desde `:412`).
- Lookups: `get_action()` (`:589`), `visible_actions()` (`:594`), `palette_actions()` (`:618`),
  **`assistant_actions()` (`:625`)**, `param_of()` (`:631`), `action_to_dict()` (`:638`), `catalog_payload()` (`:656`).

**(b) Motor de intención y contrato de propuesta — también del plan 267, y el brief no los mencionaba:**

- `backend/services/devops_action_matcher.py`: `normalize_text()` (`:49`), `_phrase_score()` (`:59`),
  `match_intent()` (`:80`), `is_ambiguous()` (`:100`), con `MIN_SCORE = 0.6` (`:14`), `AMBIGUITY_DELTA = 0.10` (`:15`),
  `MAX_MATCHES = 3` (`:16`) y `_STOPWORDS` (`:28`). Su docstring (`:1-5`) lo declara literalmente:
  *"Es el piso de paridad: con GitHub Copilot (o sin runtime disponible) este matcher es TODO el motor de intención"*.
- `backend/services/devops_action_proposal.py`: `ActionProposal` (`:48`) con `what_will_happen` (`:59`),
  `open_questions` (`:60`), `confidence`, **`needs_confirmation`** (`:63`) y `blocked_reason` (`:64`);
  `build_proposal()` (`:78`), `describe()` (`:68`), `proposal_to_dict()` (`:129`), y los 6 estados `BLOCKED_*`
  (`:22-27`; la tupla `BLOCKED_REASONS` está en `:30`).

**Conclusión dura:** el contrato "explicá qué vas a hacer antes de hacerlo, preguntá solo lo faltante, pedí
confirmación si escribís" **ya está construido y verde**. Reimplementarlo sería el error más caro de este plan.

### 2.2 El gap real: el catálogo no llega al turno del agente

`backend/api/devops_agent.py` (365 líneas) **no importa** `devops_action_catalog`. Verificado:

```
$ grep -n "action_catalog\|assistant_actions\|DevOpsAction" backend/api/devops_agent.py
(cero resultados)
```

El alcance `"assistant"` del catálogo lo consume **únicamente** `backend/api/devops_actions.py` (`:112`, `:118`),
que es un endpoint HTTP **de un solo tiro y sin memoria**: texto → propuesta → fin. No acumula requisitos, no tiene
estado, no sabe que la propuesta anterior existió.

Y del otro lado, `devops_agent.py` sí tiene el hilo multi-turno (`start_conversation()` `:61`, `send_message()` `:157`,
`_launch_turn()` `:308`) pero su turno es **texto libre**: `_launch_turn` arma un `context_blocks` de tipo
`"raw-conversation"` (`:320-326`) y llama a `agent_runner.run_agent()` (`:328`). El modelo **no tiene forma de emitir
una acción tipada**.

En la UI los dos conviven pegados pero siguen siendo dos cerebros: `DevOpsActionConsole` se monta **encima** del chat
dentro de la misma sección (`frontend/src/components/devops/DevOpsAgentSection.tsx:21` y `:129-135`), con el comentario
literal *"montada ENCIMA del chat existente y sin borrarlo"*.

> **Tesis del plan.** El determinista puede **actuar** pero no **conversar**; el conversacional puede **conversar**
> pero no **actuar**. Este plan los une con una **máquina de estados** y conecta el catálogo al turno del agente.

### 2.3 La capacidad de pipelines está fragmentada, no ausente

`frontend/src/pages/DevOpsPage.tsx` define `DEVOPS_SECTIONS` (`:145`) con 17 secciones nacidas de planes distintos:
`pipelines` (`:159`, Builder), `agente` (`:184`), `inventario-pipelines` (plan 246), `pipeline-audit` (plan 248),
`editar-pipeline` (`:296`, plan 250), `matriz-entornos` (plan 251), `paquete-entrega` (plan 252).

Y el backend ya construido que se va a **envolver**, con su API pública verificada:

| Módulo | Entrada principal | Línea | Devuelve |
|---|---|---|---|
| `services/pipeline_spec.py` | `dict_to_spec(d)` / `PipelineSpec.validate()` | `:140` / `:134` | `PipelineSpec` / `list[ValidationError]` |
| `services/pipeline_lint.py` | `lint_yaml(yaml_text, provider, known_variables=None)` | `:791` | `LintReport` (`:43`) con `LintFinding` (`:33`: `code`, `severity`, `message`, `line`, `node`, `fix`) |
| `services/pipeline_lint.py` | `explain_plan(yaml_text, provider)` | `:1031` | `ExecutionPlan` (`:841`) |
| `services/pipeline_preflight.py` | `check_placeholders` / `check_undefined_variables` | `:37` / `:102` | dict `{"id","status","title","detail","fix_hint"}` (contrato en `:4-5`) |
| `services/pipeline_patcher.py` | `plan_edit(yaml, intent, profile)` / `validate_intent_dict` | `:537` / `:803` | `(ops, errores)` |
| `services/pipeline_diff.py` | `review_patch(before, after, hunks, ...)` | `:197` | `EditReview` (`:81`) |
| `services/pipeline_stack_detector.py` | `detect_stack(project_root)` | `:19` | `'python'\|'node'\|'dotnet'\|None` — literales en `_MANIFEST_SIGNALS` (`:12-16`) **[C12]** |
| `api/pipeline_generator.py` | `POST /preview` / `POST /commit` | `:34` / `:52` | commit ya exige `confirm is True` (`:59`). **Ambas hacen `abort(404)` si `STACKY_PIPELINE_GENERATOR_ENABLED` está OFF (`:37` y `:56`) [C6]** |
| `api/pipeline_editor.py` | `/verbs` `/plan` `/commit` `/interpret` | `:141` `:171` `:199` `:428` | commit con doble flag (`_guard_commit` `:60`) |

**[C4] Las rutas HTTP que el copiloto necesita — MEDIDAS, no supuestas.** Un binding vive en TypeScript: **no puede
llamar a una función de servicio Python**. Estas son las rutas reales y su estado en `frontend/src/api/endpoints.ts`:

| Capacidad | Ruta HTTP real | Anclaje | ¿Ya hay cliente tipado en `endpoints.ts`? |
|---|---|---|---|
| Renderizar borrador | `POST /api/pipeline-generator/preview` | `api/pipeline_generator.py:34` | **SÍ** — `:4873-4874` |
| Lint del YAML | `POST /api/devops/pipeline-lint/validate` | `api/devops.py:228` | **NO — falta (se agrega en F3)** |
| Explicar el plan | `POST /api/devops/pipeline-lint/explain` | `api/devops.py:260` | **NO — falta (se agrega en F3)** |
| Preflight | `POST /api/devops/preflight/check` | `api/devops.py:483` | **SÍ** — `:4374` |
| Variables (sólo nombres) | `GET /api/devops/variables` | `api/devops_variables.py:45` | **SÍ** — `:4742` |
| Crear en el repo | `POST /api/pipeline-generator/commit` | `api/pipeline_generator.py:52` | **SÍ** — `:4879` |

> **Agregar un wrapper tipado en `endpoints.ts` para una ruta backend que YA existe NO viola §7.4 del plan 267.**
> Lo que §7.4 prohíbe (`devopsActionBindings.ts:1-2`) es **endpoints backend nuevos**. Los 2 wrappers que faltan
> son cliente, no servidor.

**Ningún servicio ni endpoint backend se reescribe.**

---

## 3. Principios y guardarraíles

1. **Orquestar, no reimplementar.** Toda capacidad nueva es una entrada del catálogo que llama a un servicio o
   endpoint que ya existe.
2. **El catálogo se EXTIENDE, no se clona.** Se agregan 6 entradas a `DEVOPS_ACTION_CATALOG`; no nace un segundo registro.
3. **Human-in-the-loop innegociable.** Ninguna escritura ocurre sin `needs_confirmation` + confirmación explícita del
   operador en la UI.
4. **El valor del secreto NUNCA llega al modelo.** El agente maneja **nombres** de variables, jamás valores (§7).
5. **Paridad de los 3 runtimes.** El piso determinista (matcher + propuesta) funciona igual en Codex CLI, Claude Code
   CLI y GitHub Copilot Pro, porque no depende del modelo.
6. **Mono-operador sin auth real.** Cero RBAC: `current_user` es un header sin validar (`api/_helpers.py`, usado en
   `devops_agent.py:24-28`).
7. **Backward-compatible.** Con las 2 flags nuevas apagadas, el panel DevOps queda **byte-idéntico** a hoy.
8. **Cero trabajo extra al operador.** Todo nace ON salvo la única que escribe en el repositorio real.

---

## 4. Diagnóstico del flujo actual y problemas de UX

### 4.1 El flujo de hoy, paso a paso

Para crear una pipeline de cero y dejarla verificada, el operador hace hoy:

1. Va a **Pipelines** (`DevOpsPage.tsx:159`) y usa el Builder o el generador.
2. Va a **Editar pipeline** (`:296`) si quiere ajustar por lenguaje natural (plan 250).
3. Va a **Auditoría** (plan 248) para ver hallazgos.
4. Va a **Matriz de entornos** (plan 251) para comparar ambientes.
5. Va a **Variables** para descubrir qué variables faltan — y las descubre **después** de que la pipeline falla.
6. Vuelve a **Pipelines** para disparar y ver si anda.

### 4.2 Problemas de UX, con su causa en el código

| # | Problema | Causa verificada |
|---|---|---|
| **U1** | El operador debe saber **a qué pestaña ir y en qué orden**. La secuencia correcta es conocimiento tácito. | 7 secciones independientes en `DEVOPS_SECTIONS` (`DevOpsPage.tsx:145`), cada una de un plan distinto, sin orquestador. |
| **U2** | El resultado de una pestaña se traslada **a mano** a la siguiente (el YAML, la rama, el nombre). | No hay estado compartido: cada panel tiene su propio modelo (`pipelineEditModel.ts`, `pipelineAuditModel.ts`, …). |
| **U3** | El asistente **olvida** entre frases: cada `POST /propose` es de un solo tiro. | `propose_action()` (`devops_actions.py:91`) no persiste nada; no recibe ni devuelve estado de sesión. |
| **U4** | El chat **no puede actuar**: entiende pero no ejecuta. | `_launch_turn()` (`devops_agent.py:308`) manda texto libre; cero referencias al catálogo. |
| **U5** | Las variables/secretos faltantes se descubren **tarde**, cuando la corrida falla. | `check_undefined_variables` (`pipeline_preflight.py:102`) existe pero no está en el camino conversacional. |
| **U6** | No hay un "qué va a pasar" **antes** de escribir, salvo dentro de la tarjeta de acción suelta. | `describe()` (`devops_action_proposal.py:68`) y `explain_plan()` (`pipeline_lint.py:1031`) existen y están desconectados entre sí. |
| **U7** | El chat rechaza GitHub Copilot con **400**. | `start_conversation()` valida `runtime not in _CLI_RUNTIMES` (`devops_agent.py:70-79`). El endpoint determinista sí acepta los 3 (`devops_actions.py:93-96`). |
| **U8** | **[C3] El operador ni siquiera puede *elegir* GitHub Copilot en el chat DevOps.** Arreglar sólo el backend deja el fix inalcanzable. | `DevOpsAgentSection.tsx:28` declara `type CliRuntime = 'claude_code_cli' \| 'codex_cli'` y el `<select>` (`:147-149`) tiene **exactamente 2** `<option>`. El resto del producto sí conoce el runtime (`endpoints.ts:1157`, `AgentLaunchModal.tsx:251`). |

**U7+U8 son el riesgo de paridad más concreto del plan.** U7 se resuelve en F6 con degradación explícita (no borrando
el gate) y **U8 en F8** agregando la opción al selector: sin las dos, K6 sería un gate que pasa sin probar nada.

---

## 5. Decisiones de diseño D1..D9

### D1 — El agente propone; el frontend ejecuta

- **Problema.** Si el agente ejecutara acciones directamente, una alucinación escribiría en un sistema real.
- **Recomendación.** El agente **solo** puede llegar hasta `ActionProposal`. La ejecución sigue en
  `frontend/src/services/devopsActionBindings.ts`, que ya reusa los endpoints existentes.
- **Alternativas.** (a) Endpoint de ejecución para el agente — rechazada: viola el §7.4 del plan 267, escrito literal
  en `devopsActionBindings.ts:1-2` (*"PROHIBIDO agregar endpoints nuevos acá"*). (b) Que el agente llame a los
  endpoints por curl como en la consola remota — rechazada: saltea la tarjeta de confirmación.
- **Riesgo.** Un paso más para el operador (un clic). Aceptado: ese clic **es** el human-in-the-loop.

### D2 — El contrato con el agente va por PROMPT, no por tool-calling nativo

- **Problema.** Los 3 runtimes exponen tool-calling distinto (o no lo exponen).
- **Recomendación.** Un prompt-builder que declara el contrato y le da al agente una URL local, calcando
  `services/remote_console_prompt.py::build_console_prompt` (`:8`), que ya resuelve exactamente este problema y
  **ya declara** que la credencial la maneja Stacky (`:27-28`: *"la credencial la maneja Stacky; NUNCA pidas ni uses
  passwords"*).
- **Alternativas.** (a) Tool-calling nativo — rechazada: rompe paridad de runtimes. (b) Parsear un bloque JSON de la
  salida — rechazada: frágil y sin auditoría.
- **Riesgo.** El agente puede ignorar el contrato. Mitigado: si no llama, la sesión queda en su estado actual y el
  matcher determinista sigue siendo el piso (D3).

### D3 — El matcher determinista es el piso de paridad, no un fallback de segunda

- **Problema.** Con Copilot no hay turno CLI (U7) **y hoy el operador ni siquiera puede elegirlo (U8)**.
- **Recomendación.** Dos mitades, **las dos obligatorias**:
  **(a) backend (F6):** la sesión avanza igual con `match_intent()` (`devops_action_matcher.py:80`), sin modelo, y
  `start_conversation()` devuelve `200 + mode:"deterministic"` en vez de `400`.
  **(b) frontend (F8) [C3]:** `github_copilot` se agrega al tipo `CliRuntime` y al `<select>`, con la etiqueta
  `"GitHub Copilot (modo determinista)"`. **Un fix backend sin (b) es inalcanzable para el operador.**
- **Alternativas.** Bloquear Copilot — rechazada: viola la regla de los 3 runtimes. Arreglar sólo el backend —
  rechazada: es la definición de "gate que pasa sin probar nada".
- **Riesgo.** Menor riqueza conversacional con Copilot. Declarado como degradación controlada, no como falla, y
  **dicho en la propia etiqueta del selector** para que el operador sepa qué está eligiendo.

### D10 — `[ADICIÓN ARQUITECTO]` Deshacer-primero: no se confirma una escritura sin ver su reversión

- **Problema.** v1 admite en §9.7 que *"si `devops.pipeline_new.commit` falla, la sesión va a `failed` y el operador
  revierte con git"* — pero **nunca le dice qué revertir**. Pedirle al humano que confirme una escritura en su
  repositorio real sin mostrarle el deshacer es human-in-the-loop de forma, no de fondo: el operador aprueba a ciegas.
- **Recomendación.** La sesión lleva un campo `undo_hint: str` que se **calcula en `review`/`confirm`, antes de
  escribir**, y que la tarjeta muestra junto al botón de confirmar. Es texto determinista, sin IO ni modelo:
  la ruta exacta del archivo que se va a crear (`azure-pipelines.yml` o `.gitlab-ci.yml`, según `provider`), la rama,
  y el comando de reversión. Ejemplo literal:
  `"Para deshacer: borrá 'azure-pipelines.yml' en la rama 'feature/x' (o 'git revert' el commit que devuelva Stacky)."`
- **Alternativas.** (a) Rollback automático — **rechazada**: sacaría al humano del lazo y podría pisar trabajo ajeno.
  (b) Mostrar el undo *después* del commit — rechazada: llega tarde para la decisión, que es el momento que importa.
- **Costo.** 1 campo en el dataclass, 1 función pura, 3 casos de test. **Cero** flags nuevas, **cero** endpoints
  nuevos, **cero** trabajo extra al operador (aparece solo), backward-compatible (`undo_hint=""` por defecto).
- **Riesgo.** Que el hint quede desactualizado respecto de lo que el commit hace. Mitigado: se deriva de los **mismos**
  `provider` + `branch` que el binding manda a `/api/pipeline-generator/commit`, y F9 caso 6 lo congela.

### D4 — El estado de sesión vive en el JSON de `Ticket.description`, sin migración

- **Problema.** La sesión necesita persistir entre turnos.
- **Recomendación.** Extender el JSON que `_chat_meta()` (`devops_agent.py:31-40`) ya lee, agregando la clave
  `pipeline_session`. El parser ya es tolerante (`except (json.JSONDecodeError, TypeError): return {}`).
- **Alternativas.** (a) Tabla nueva — rechazada por costo y por el riesgo conocido de que un rebuild de tabla con
  lista de columnas hardcodeada borre la columna nueva. (b) Columna nueva en `tickets` — mismo riesgo.
- **Riesgo.** `description` crece. Mitigado: F2 impone `MAX_SESSION_BYTES = 8192` y la sesión guarda **referencias**
  (ids, nombres, rutas), nunca YAML completo.

### D5 — 6 acciones nuevas, ni una más

- **Problema.** "Envolver todo" es alcance infinito.
- **Recomendación.** Exactamente **6**: 5 de lectura + 1 de escritura (§6.F3). Cubren el ciclo completo
  borrador→validar→explicar→preflight→variables→crear.
- **Alternativas.** Envolver las 15 capacidades de pipeline — rechazada: 8 de las 23 acciones existentes ya son
  "delega a la pantalla" porque no tienen endpoint propio (`devopsActionBindings.ts:12-19`); sumar más delegaciones no
  agrega valor conversacional.
- **Riesgo.** Quedan capacidades fuera del hilo (handoff, profiler). Declarado en §9 Fuera de scope.

### D6 — Los secretos se manejan por NOMBRE, con el puerto que ya existe

- **Problema.** El agente necesita saber qué credenciales faltan sin verlas.
- **Recomendación.** Usar `CIVariablesProvider.list_variables()` (`services/ci_variables.py:50`), cuyo docstring dice
  literal *"Lista variables del proyecto (sin values)"*, y cuyo dict es solo
  `{"key", "is_secret", "has_value", "masked"}` (`services/ado_variables.py:44-49`). Es exactamente un handle.
- **Alternativas.** Pasar valores enmascarados — rechazada: `mask_token_values` (`secret_masking.py:20`) es defensa en
  profundidad, no arquitectura. El valor no debe **existir** en ese camino.
- **Riesgo.** Ninguno estructural: `pipeline_lint.py` ya consume `known_variables` como lista de nombres (`:791`).

### D7 — Dos flags: ver/planear ON, escribir OFF

- **Problema.** La regla de "cero trabajo al operador" choca con "no escribir sin permiso".
- **Recomendación.** Partir en 2, calcando el precedente exacto del plan 250
  (`STACKY_PIPELINE_NL_EDIT_ENABLED` ON vs `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` OFF) y del plan 267
  (`STACKY_DEVOPS_ACTION_NL_ENABLED` ON vs `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` OFF).
- **Riesgo.** Ninguno: es el patrón ya establecido dos veces.

### D8 — La sección nueva no borra ninguna existente

- **Problema.** Reemplazar pestañas rompería flujos y tests ajenos.
- **Recomendación.** Agregar `copiloto-pipelines` como sección 18. Las 17 actuales quedan intactas.
- **Alternativas.** Fusionar las 7 pestañas de pipeline — rechazada: alcance enorme y regresión garantizada.
- **Riesgo.** Más superficie. Aceptado: el guardarraíl *"sin eliminar la posibilidad de hacerlo manualmente"* está
  congelado por `test_reach_incluye_button_siempre` (`test_devops_action_ratchet.py:133`).

### D9 — Reintentos: solo lo idempotente se reintenta solo

- **Problema.** "Corregir solo cuando es seguro" necesita una regla, no criterio.
- **Recomendación.** Regla cerrada: se reintenta automáticamente **solo** si `effect == "read"`, máximo
  `MAX_AUTO_RETRIES = 2`. Toda acción `write` que falla **detiene** la sesión en `failed` y pide intervención.
- **Alternativas.** Reintento con backoff en writes — rechazada: puede duplicar un commit o una corrida.
- **Riesgo.** Menos automatismo. Aceptado: es la frontera segura.

---

## 6. Fases

> **Entorno para TODOS los comandos.** El venv que anda es `backend/venv` (py3.11.9, verificado en esta corrida).
> **NO** usar `backend/.venv`. Las rutas tienen espacios: citar siempre.
> Prefijo obligatorio `DATABASE_URL="sqlite:///:memory:"` en todo pytest, para no escribir en la base viva del operador.

---

### F0 — Censo congelado y guarda anti-falso-verde

**Objetivo.** Congelar el estado de hoy para que cualquier deriva posterior sea visible.
**Valor.** Sin esto, un test que deja de matchear da dos listas vacías iguales y pasa en verde.

**Archivos a crear**
- `Stacky Agents/backend/tests/test_plan279_baseline.py`

**Contenido exacto (4 casos)**

| # | Caso | Aserción |
|---|---|---|
| 1 | `test_catalogo_tiene_29_acciones_al_terminar_el_plan` | `len(DEVOPS_ACTION_CATALOG) == 29` |
| 2 | `test_las_6_acciones_nuevas_existen` | los 6 ids de F3 están en el índice vía `get_action(id) is not None` |
| 3 | `test_la_suite_hermana_cuenta_8_escrituras` | **[C1]** leer `tests/test_devops_action_catalog.py` como texto y afirmar que contiene `assert len(escrituras) == 8`. Este caso existe porque el gate hermano se actualiza, **no se borra**. |
| 4 | `test_lectura_y_escritura_siguen_separadas` | `len([a for a in DEVOPS_ACTION_CATALOG if a.effect=="write"]) == 8` **y** `... if a.effect=="read"]) == 21` |

> **[C1] CONTRADICCIÓN RESUELTA — leé esto antes de tocar el catálogo.**
> `tests/test_devops_action_catalog.py:177` dice hoy, **con igualdad**:
> ```python
> assert len(escrituras) == 7, sorted(escrituras)
> ```
> El caso 4 de arriba exige **8**. **Los dos no pueden estar verdes a la vez.** La resolución correcta y **única**
> es la de F3: **editar** ese `== 7` a `== 8` (un ratchet que se aprieta). **PROHIBIDO borrar, comentar o relajar a
> `>=` ese assert**: es el guard que impide que nazca una escritura fuera del conteo, y borrarlo deja el agujero
> abierto con los dos tests en verde. El caso 3 de F0 está justamente para que borrarlo **no** pase inadvertido.

> **[C2] Lo que este archivo NO gatea.** K1 (el catálogo llega al turno del agente) **no** se mide acá con un
> `grep`/substring sobre `api/devops_agent.py`: un comentario satisfaría el criterio. K1 se mide **sólo** en
> F6 casos 3 y 8 (`ast` + comportamiento).

**Nota de orden.** F0 nace **ROJO a propósito** y se pone verde al terminar F3. Es el ratchet del plan, no un gate de arranque.

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_plan279_baseline.py -q
```

**Criterio binario.** Al cerrar el plan: `4 passed`. Antes de F3: se espera rojo.
**Flag.** Ninguna (es un test).
**Runtimes.** Sin impacto (test puro).
**Trabajo del operador:** ninguno.

---

### F1 — Las 2 flags

**Objetivo.** Registrar las flags que gatean el copiloto, respetando los 9 lugares de registro.
**Valor.** Sin flag registrada, `test_flag_key_existe_en_el_registro` (`test_devops_action_ratchet.py:68`) deja F3 en rojo.

**Flags**

| Key | Default | `requires=` | Categoría | Motivo |
|---|---|---|---|---|
| `STACKY_PIPELINE_COPILOT_ENABLED` | **ON** | `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` | `devops` | Solo lee, planea, simula y explica. Ninguna excepción dura aplica. |
| `STACKY_PIPELINE_COPILOT_COMMIT_ENABLED` | **OFF** | `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` | `devops` | **EXCEPCIÓN DURA (B)**: escribe el archivo de pipeline en el repositorio real del operador. |

> **Depth-1 verificado:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` (`FlagSpec(` en `harness_flags.py:6194`, `key=` en
> `:6195`) **no** declara `requires=`, así que apuntarle cumple la regla de `validate_requires_graph`.

> **[C6] Flag PREEXISTENTE de la que este plan depende y que NO se toca:**
> `STACKY_PIPELINE_GENERATOR_ENABLED` (default **ON**, `config.py:1632-1634`). Las acciones 1 (`draft`) y 6 (`commit`)
> envuelven `/api/pipeline-generator/{preview,commit}`, que hacen `abort(404)` si está OFF (`api/pipeline_generator.py:37`
> y `:56`). **NO se crea ninguna flag equivalente** (ya hay 13 `STACKY_PIPELINE_*` registradas). Lo que sí se hace es
> **degradar honesto**: F5 caso 9. Con esa flag apagada el copiloto debe **decir cuál flag falta**, no morir en un 404 mudo.

**TRAMPA nº1 (un modelo menor la pisa seguro).** La flag que nace OFF **NO declara `default=` en absoluto**. El OFF
vive **solo** en `config.py`. Precedentes literales: `harness_flags.py:6232-6240`
(`STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED`, cuyo comentario en `:6234-6237` explica la regla palabra por palabra) y
`:3602-3609` (`STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`, `key=` en `:3603`).
Escribir `default=False` **rompe** `test_harness_flags.py::test_default_known_only_for_curated`.

**Archivos a editar (los 6 obligatorios)**

1. `backend/services/harness_flags.py` → `FLAG_REGISTRY`: 2 `FlagSpec(...)`. La ON con `default=True`; la OFF **sin** `default=`.
2. `backend/services/harness_flags.py` → `_CATEGORY_KEYS` (dict desde `:120`): ambas keys al bucket `devops`.
3. `backend/config.py`: `STACKY_PIPELINE_COPILOT_ENABLED: bool = os.getenv("STACKY_PIPELINE_COPILOT_ENABLED", "true").strip().lower() == "true"` y la COMMIT con `"false"`. Patrón en `config.py:2409-2417`.
4. `backend/services/harness_flags_help.py` → `PLAIN_HELP`: 2 entradas `PlainHelp(what=, on_effect=, off_effect=, example=)`. `on_effect`/`off_effect` **deben** empezar con `"Si la activás"` / `"Si la apagás"`.
5. `backend/tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON` (desde `:467`): agregar **solo** `STACKY_PIPELINE_COPILOT_ENABLED` (la OFF **no** va).
6. `backend/tests/test_harness_flags_requires.py` → `_REQUIRES_MAP_FROZEN` (desde `:120`): las 2 keys → `"STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`.

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_help.py tests/test_harness_flags_requires.py tests/test_flag_wiring.py -q
```

**Criterio binario.** Las 4 suites en verde, `0 failed`.
**Nota sobre `test_flag_wiring.py:52` (sin placebo).** Exige consumidor real en producción. Las flags quedan
consumidas en F5 y F8; si se corre F1 aislada, ese test puede salir rojo hasta F5. **No** marcar `reserved=True`: se
resuelve solo al llegar a F5.
**Runtimes.** Sin impacto (config).
**Trabajo del operador:** ninguno para la ON. La COMMIT es opt-in consciente por UI (categoría B).

---

### F2 — La máquina de estados (módulo PURO)

**Objetivo.** Un módulo sin IO que define los 8 estados y las transiciones legales.
**Valor.** Es el cerebro que hoy no existe (K5): convierte "el agente charla" en "el agente avanza un procedimiento".

**Archivo a crear**
- `Stacky Agents/backend/services/pipeline_session.py`

**Contrato exacto**

```python
"""Plan 279 F2 — Maquina de estados de creacion de pipeline.

PURO: sin flask, sin config, sin IO, sin red, sin modelo. Calca la disciplina de
services/devops_action_catalog.py (dataclasses + datos + lookups).
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace

SESSION_VERSION = "1"
MAX_SESSION_BYTES = 8192
MAX_AUTO_RETRIES = 2

#: Los 8 estados. Cerrado: nada fuera de esta tupla es un estado valido.
PIPELINE_SESSION_STATES = (
    "intake",      # 1. recogiendo el pedido en texto libre
    "discovery",   # 2. stack y proveedor detectados, requisitos abiertos
    "draft",       # 3. hay un borrador de spec
    "review",      # 4. lint + explain + preflight corridos sobre el borrador
    "secrets",     # 5. faltan variables, identificadas POR NOMBRE
    "confirm",     # 6. esperando confirmacion explicita del operador
    "committed",   # 7. escrito en el repositorio real
    "failed",      # 8. terminal con causa declarada
)

#: Transiciones legales. Clave = origen, valor = destinos permitidos.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "intake":    ("discovery", "failed"),
    "discovery": ("draft", "secrets", "failed"),
    "draft":     ("review", "failed"),
    "review":    ("secrets", "confirm", "draft", "failed"),
    "secrets":   ("review", "confirm", "failed"),
    "confirm":   ("committed", "draft", "failed"),
    "committed": (),
    "failed":    (),
}

TERMINAL_STATES = ("committed", "failed")


#: [ADICION ARQUITECTO] Nombre del archivo que la escritura va a crear, por proveedor.
#: Es la MISMA convencion que ya usa api/pipeline_generator.py. Cerrado: 2 proveedores.
PIPELINE_FILENAME: dict[str, str] = {
    "ado": "azure-pipelines.yml",
    "gitlab": ".gitlab-ci.yml",
}


@dataclass(frozen=True)
class PipelineSession:
    state: str = "intake"
    provider: str = ""            # "ado" | "gitlab" | ""
    stack: str = ""               # "python" | "node" | "dotnet" | ""
    project: str = ""
    branch: str = ""              # rama destino de la escritura
    draft_ref: str = ""           # REFERENCIA al borrador, nunca el YAML entero
    missing_variables: tuple[str, ...] = ()   # NOMBRES, jamas valores
    open_questions: tuple[str, ...] = ()
    last_action_id: str = ""
    retries: int = 0
    failure_reason: str = ""
    version: str = SESSION_VERSION


def can_transition(origen: str, destino: str) -> bool:
    """True si la transicion es legal. NUNCA lanza."""


def advance(session: PipelineSession, destino: str, **campos) -> tuple[PipelineSession, str]:
    """Devuelve (sesion_nueva, "") si la transicion es legal;
    (sesion_original, motivo) si no. NUNCA lanza."""


def session_to_dict(s: PipelineSession) -> dict:
    """Serializacion 1:1, json.dumps-able sin encoder custom."""


def session_from_dict(d: dict | None) -> PipelineSession:
    """Tolerante: cualquier dict invalido devuelve PipelineSession() por defecto.
    NUNCA lanza (mismo criterio que _chat_meta en api/devops_agent.py:31-40)."""


def next_question(s: PipelineSession) -> str:
    """La UNICA pregunta que falta hacer, o "" si no falta ninguna. Determinista:
    recorre open_questions en orden y devuelve la primera."""


def undo_hint(s: PipelineSession) -> str:
    """[ADICION ARQUITECTO] Como deshacer la escritura que se esta por confirmar.

    Determinista, PURO, sin IO y sin modelo. Devuelve "" si todavia no hay nada
    que deshacer (provider o branch vacios). NUNCA lanza.

    Formato EXACTO (una sola frase, castellano, sin markdown):
      "Para deshacer: borra '<archivo>' en la rama '<branch>' del proyecto
       '<project>' (o revertí con git el commit que devuelva Stacky)."

    donde <archivo> = PIPELINE_FILENAME[s.provider]. Si el provider no esta en
    PIPELINE_FILENAME, devuelve "" (no inventa un nombre de archivo)."""
```

**Casos borde obligatorios**
- `advance()` a un estado terminal desde otro terminal → rechazada con motivo `"estado_terminal"`.
- `session_from_dict(None)` / `{}` / `{"state": "inventado"}` → `PipelineSession()` por defecto.
- `session_to_dict` serializado con `json.dumps` debe pesar `<= MAX_SESSION_BYTES`.
- `undo_hint()` con `provider="jenkins"` (fuera del vocabulario) → `""`, no un nombre inventado.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_pipeline_session.py` (**11 casos**)

| # | Caso |
|---|---|
| 1 | `test_hay_exactamente_8_estados` → `len(PIPELINE_SESSION_STATES) == 8` (KPI K5) |
| 2 | `test_toda_clave_de_transitions_es_un_estado` |
| 3 | `test_todo_destino_de_transitions_es_un_estado` |
| 4 | `test_los_terminales_no_tienen_salida` |
| 5 | `test_can_transition_acepta_las_legales` |
| 6 | `test_can_transition_rechaza_las_ilegales` (ej. `intake`→`committed`) |
| 7 | `test_advance_ilegal_devuelve_la_sesion_original_y_motivo` |
| 8 | `test_session_from_dict_es_tolerante` (None, {}, basura) |
| 9 | `test_roundtrip_to_dict_from_dict` (incluye `branch` y que `undo_hint` **no** se serializa: se **deriva**) |
| 10 | `test_next_question_es_determinista_y_vacia_si_no_faltan` |
| 11 | **`test_undo_hint_nombra_el_archivo_y_la_rama`** — `[ADICIÓN ARQUITECTO]` con `provider="ado", branch="feature/x"` el texto contiene `"azure-pipelines.yml"` **y** `"feature/x"`; con `provider="gitlab"` contiene `".gitlab-ci.yml"`; con `provider=""` **y** con `provider="jenkins"` devuelve `""` |

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_pipeline_session.py -q
```

**Criterio binario.** `11 passed`.
**Flag.** Ninguna (módulo puro; lo gatean sus consumidores).
**Runtimes.** Idéntico en los 3 (sin modelo, sin IO).
**Trabajo del operador:** ninguno.

---

### F3 — Las 6 acciones nuevas + sus 6 bindings (en la MISMA fase)

**Objetivo.** Extender el catálogo con el ciclo de creación y mantener la paridad con los bindings.
**Valor.** Convierte capacidades sueltas en herramientas tipadas que el agente puede proponer.

> **TRAMPA nº2 — por qué backend y frontend van juntos.**
> `frontend/src/__tests__/devopsActionCatalogRatchet.test.ts:47` exige **igualdad EXACTA de conjuntos** entre los ids
> del `.py` y las claves de `DEVOPS_ACTION_BINDINGS`. Agregar acciones sin binding deja el ratchet ROJO.

**Archivos a editar (los 5)**
1. `Stacky Agents/backend/services/devops_action_catalog.py` — agregar 5 lecturas **antes de `:411`** (el comentario
   `# ---- 7 de ESCRITURA ----`; verificado exacto) y 1 escritura **antes del `)` de cierre de la tupla**.
2. `Stacky Agents/backend/tests/test_devops_action_catalog.py` — **`:177`: `== 7` → `== 8`** **[C1, OBLIGATORIO]**.
   Cambiar además el comentario del bloque `# ---- 7 de ESCRITURA ----` a `# ---- 8 de ESCRITURA ----` y
   `# ---- 16 de LECTURA ----` (`:147`) a `# ---- 21 de LECTURA ----`.
3. `Stacky Agents/frontend/src/api/endpoints.ts` — **[C4]** agregar los **2 wrappers tipados que faltan** para rutas
   backend que **ya existen** (`POST /api/devops/pipeline-lint/validate` y `POST /api/devops/pipeline-lint/explain`),
   calcando la forma de `preflightCheck` (`:4374`). **Esto NO es un endpoint nuevo**: §7.4 prohíbe rutas backend
   nuevas, no clientes tipados.
4. `Stacky Agents/frontend/src/services/devopsActionBindings.ts` — los 6 bindings.
5. `Stacky Agents/frontend/src/__tests__/devopsActionCatalogRatchet.test.ts` (subir los **3** pisos, ver abajo).

> **TRAMPA nº3 — escribir las entradas EXPANDIDAS.** El comentario `devops_action_catalog.py:140-144` lo dice literal:
> los ratchets parsean este archivo **como TEXTO** buscando `id="..."`, `effect="..."` y `reach=canonical_reach("...")`
> línea por línea. **PROHIBIDO** un helper o un bucle que arme las entradas: dejaría los ratchets inertes.
>
> **TRAMPA nº4 — el id debe matchear `/^\s*id="(devops\.[a-z_]+\.[a-z_]+)"/`** (`devopsActionCatalogRatchet.test.ts:21`):
> exactamente **dos** segmentos después de `devops.`, minúsculas y guión bajo. `devops.pipeline_new.draft` sirve;
> `devops.pipeline.new.draft` **no matchea**.

**Las 6 entradas — [C4] la columna "Envuelve" es una RUTA HTTP, no una función de servicio Python**

Un binding es TypeScript: **no puede llamar a `lint_yaml()`**. Lo que llama es la ruta HTTP que envuelve a esa función.

| # | id | effect | impact | health_key | flag_key | Ruta HTTP que llama el binding | Función de `endpoints.ts` |
|---|----|--------|--------|-----------|----------|-------------------------------|---------------------------|
| 1 | `devops.pipeline_new.draft` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `POST /api/pipeline-generator/preview` (`api/pipeline_generator.py:34`) | **existe** (`endpoints.ts:4873`) |
| 2 | `devops.pipeline_new.lint` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `POST /api/devops/pipeline-lint/validate` (`api/devops.py:228`) | **FALTA — crearla en F3** |
| 3 | `devops.pipeline_new.explain` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `POST /api/devops/pipeline-lint/explain` (`api/devops.py:260`) | **FALTA — crearla en F3** |
| 4 | `devops.pipeline_new.preflight` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `POST /api/devops/preflight/check` (`api/devops.py:483`) | **existe** (`endpoints.ts:4374`) |
| 5 | `devops.pipeline_new.secrets` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `GET /api/devops/variables` (`api/devops_variables.py:45`) — **solo nombres** | **existe** (`endpoints.ts:4742`) |
| 6 | `devops.pipeline_new.commit` | **write** | **high** | `pipeline_copilot_commit_enabled` | `STACKY_PIPELINE_COPILOT_COMMIT_ENABLED` | `POST /api/pipeline-generator/commit` (`api/pipeline_generator.py:52`) | **existe** (`endpoints.ts:4879`) |

> **[C6]** Las acciones **1 y 6** dependen además de `STACKY_PIPELINE_GENERATOR_ENABLED` (default ON), que hace
> `abort(404)` si está OFF. No se crea flag nueva; se degrada honesto en F5 caso 9.

**[C5] Los 6 `label` y los 6 `summary` — CONGELADOS, no improvisar.**
`test_label_y_summary_no_vacios` (`test_devops_action_catalog.py:166`) exige ambos no vacíos en las 6, **y el `label`
entra al gate de colisión** (`test_devops_action_ratchet.py:114`: `universo(a) = (*a.phrases, a.label)`). Un label
corto tipo `"Pipeline"` volvería el conjunto un subconjunto y pondría rojo el gate.

```
1 draft      label="Armar borrador de pipeline"
             summary="Genera un borrador de pipeline a partir de lo que necesitas. No escribe nada."
2 lint       label="Revisar borrador de pipeline"
             summary="Corre el lint sobre el borrador y devuelve los hallazgos con su linea."
3 explain    label="Explicar borrador de pipeline"
             summary="Describe en castellano que etapas y pasos va a correr el borrador."
4 preflight  label="Chequeos previos del borrador"
             summary="Semaforo estatico del borrador: placeholders y variables sin definir."
5 secrets    label="Variables que faltan para el borrador"
             summary="Lista por NOMBRE las variables y secretos que el borrador necesita y el proyecto no define."
6 commit     label="Crear la pipeline en el repositorio"
             summary="Escribe el archivo de pipeline en la rama elegida del repositorio real. Pide confirmacion."
```

**Reglas del ratchet que estas 6 deben cumplir** (`backend/tests/test_devops_action_ratchet.py`):
- las 5 lecturas: `impact="none"` **exacto** (`:48`), `reach=canonical_reach("read")`;
- la escritura: `impact != "none"` (`:26`) y `flag_key != ""` (`:53`), `reach=canonical_reach("write")`;
- `targets_environment=False` en las 6 (ninguna recibe un `environment`; si fuera `True`, `:31` exigiría un param
  `environment` enum required, y **ningún endpoint de estas 6 lo consume**);
- `section_id="copiloto-pipelines"` y `nav_path="/devops/copiloto-pipelines"` en las 6 (`:90`);
- `summary` no vacío en la escritura (`:96`);
- `health_key` debe existir en `_health_payload()` → se agrega en F8; **hasta entonces `:59` sale rojo**.

**TRAMPA nº5 — las frases NO pueden colisionar entre lectura y escritura.**
`test_frases_no_colisionan_entre_read_y_write` (`:111`) falla si el conjunto de tokens de contenido de **cualquier**
frase **o `label`** de lectura es subconjunto o superconjunto del de **cualquier** frase **o `label`** de escritura
(stopwords excluidas, `devops_action_matcher.py:28`). El universo evaluado es `(*a.phrases, a.label)` (`:114`).

> **VERIFICADO POR EL JUEZ (no es una promesa):** se ejecutó ese mismo algoritmo (`_content_tokens` + `normalize_text`
> reales) sobre las 23 acciones del catálogo actual cruzadas con las **18 frases + los 6 `label`** de abajo:
> **0 choques**. **No improvisar ni frases ni labels**: cualquier reemplazo invalida esta verificación.

```
1 devops.pipeline_new.draft     phrases=("borrador de pipeline nueva",
                                         "armar el borrador de una pipeline",
                                         "disenar una pipeline nueva")
2 devops.pipeline_new.lint      phrases=("revisar el borrador de pipeline",
                                         "validar el yaml del borrador",
                                         "que errores tiene el borrador")
3 devops.pipeline_new.explain   phrases=("explicar el borrador de pipeline",
                                         "que va a hacer el borrador",
                                         "explicame los pasos del borrador")
4 devops.pipeline_new.preflight phrases=("preflight del borrador de pipeline",
                                         "semaforo del borrador",
                                         "chequeos previos del borrador")
5 devops.pipeline_new.secrets   phrases=("que variables le faltan al borrador",
                                         "secretos que necesita el borrador",
                                         "credenciales que faltan para la pipeline")
6 devops.pipeline_new.commit    phrases=("crear la pipeline nueva en el repositorio",
                                         "publicar el borrador de pipeline",
                                         "guardar la pipeline nueva en el repo")
```

**Params.** Las 6 llevan `PRJ` (`:123`, `project` required) como primer param
(`test_todas_declaran_project`). Además:
- `draft`: `ActionParam(name="need", type="string", label="Que necesitas", required=True)`
- `lint` / `explain` / `preflight` / `secrets` / `commit`: `ActionParam(name="draft_ref", type="string", label="Borrador", required=True)`
- `commit` suma `ActionParam(name="branch", type="string", label="Rama", required=True)`

**Bindings** en `frontend/src/services/devopsActionBindings.ts`: las **6** usan `callEndpoint()` (`:72`); **ninguna**
usa `goToPanel()` (`:47`), porque las 6 tienen ruta HTTP real (tabla de arriba).
**PROHIBIDO agregar endpoints BACKEND nuevos** (`:1-2`). **[C4] Agregar en `endpoints.ts` los 2 wrappers tipados que
faltan (lint y explain) para rutas backend que YA existen NO es un endpoint nuevo y está permitido.**

**Subir los pisos del ratchet frontend — son TRES, no dos** (un ratchet que nunca se aprieta es inerte):
- caso 5, línea `:56`: `toBeGreaterThanOrEqual(23)` → **`29`**
- caso 6, línea `:62`: `expect(entradas.length).toBeGreaterThanOrEqual(23)` → **`29`** **[C7 — v1 lo olvidaba]**
- caso 6, línea `:67`: `toBeGreaterThanOrEqual(12)` → **`21`**
  (medido por el juez con la regex real del ratchet: hoy hay **exactamente 16** `read`/`read`; 16 + 5 = 21)

**Tests**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_devops_action_ratchet.py tests/test_devops_action_catalog.py tests/test_devops_action_matcher.py -q
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts
```

**Criterio binario [C8] — literal, sin "salvo".**
Backend: **`49 passed, 1 failed`**, y el ÚNICO fallo permitido es exactamente este nodeid:
`tests/test_devops_action_ratchet.py::test_health_key_existe_en_health_payload`
(porque `pipeline_copilot_enabled` recién nace en `_health_payload()` en F8). **Cualquier otro rojo es del
implementador.** F8 debe llevarlo a `50 passed, 0 failed`.
Frontend: **`7 passed`** y `npx tsc --noEmit` con **0 errores** (los 2 wrappers nuevos de `endpoints.ts` tipan).
**Flag.** `STACKY_PIPELINE_COPILOT_ENABLED` (ON) para 1–5; `STACKY_PIPELINE_COPILOT_COMMIT_ENABLED` (OFF) para 6.
**Runtimes.** Idéntico en los 3: el catálogo es un dato, no depende del modelo.
**Trabajo del operador:** ninguno (1–5). La 6 es opt-in por UI.

---

### F4 — El contrato del agente (prompt-builder, sin secretos)

**Objetivo.** Un módulo que envuelve el mensaje del operador con el contrato de herramientas del copiloto.
**Valor.** Es lo que convierte el turno de texto libre en un turno con herramientas (K1).

**Archivo a crear**
- `Stacky Agents/backend/services/pipeline_copilot_prompt.py`

**Contrato**

```python
"""Plan 279 F4 — Prompt de copiloto de pipelines: contrato del agente (sin secretos).

Calca services/remote_console_prompt.py:8 (plan 105): el agente NO tiene acceso
directo a nada; todo pasa por un endpoint HTTP local que Stacky controla.
"""
from __future__ import annotations
from services.pipeline_session import PipelineSession

def build_copilot_prompt(
    session: PipelineSession,
    base_url: str,
    message: str,
    conversation_id: int,
    *,
    commit_enabled: bool,
) -> str:
    """Envuelve el mensaje del operador con el contrato del copiloto.
    NUNCA incluye valores de variables ni de secretos: solo NOMBRES."""
```

**El prompt debe declarar, literal:**
1. El estado actual de la sesión y los destinos legales desde ahí (de `TRANSITIONS`).
2. Que para proponer una acción debe llamar a
   `POST {base_url}/api/devops/actions/propose` con `{"text": "...", "params": {...}}` — el endpoint **que ya existe**
   (`api/devops_actions.py:91`) y que es **solo lectura**.
3. Que **jamás** debe pedir, adivinar ni escribir el **valor** de una variable o secreto: solo puede nombrarlas.
   Texto obligatorio: `"Los valores de variables y secretos los maneja Stacky; NUNCA pidas ni escribas un valor."`
4. Que si `commit_enabled` es `False`, **no** puede proponer `devops.pipeline_new.commit`, y debe explicarle al
   operador que active la flag por UI.
5. Que una sola pregunta por turno (la de `next_question()`).
6. **`[ADICIÓN ARQUITECTO]`** Que si la sesión está en `review`/`secrets`/`confirm` y `undo_hint(session)` no es `""`,
   el prompt **incluye ese texto literal** y le ordena al agente mostrárselo al operador **antes** de pedir la
   confirmación. Texto obligatorio que precede al hint:
   `"Antes de pedir confirmacion, decile al operador como deshacer esto:"`.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_pipeline_copilot_prompt.py` (**7 casos**)

| # | Caso |
|---|---|
| 1 | `test_el_prompt_nombra_el_estado_actual` |
| 2 | `test_el_prompt_lista_solo_las_transiciones_legales` |
| 3 | `test_el_prompt_incluye_la_url_de_propose` |
| 4 | `test_con_commit_off_el_prompt_prohibe_la_accion_de_commit` |
| 5 | `test_el_prompt_incluye_la_regla_de_no_pedir_valores` |
| 6 | `test_los_nombres_de_variables_aparecen_pero_ningun_valor` — construir la sesión con `missing_variables=("DB_PASSWORD","API_TOKEN")`, y afirmar que el prompt **contiene** esos nombres |
| 7 | **`test_en_confirm_el_prompt_trae_el_deshacer`** — `[ADICIÓN ARQUITECTO]` con `state="confirm", provider="ado", branch="feature/x"` el prompt contiene `"azure-pipelines.yml"`, `"feature/x"` y la frase obligatoria; con `state="intake"` **no** la contiene |

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_pipeline_copilot_prompt.py -q
```

**Criterio binario.** `7 passed`.
**Flag.** `STACKY_PIPELINE_COPILOT_ENABLED`; el punto 4 lee `STACKY_PIPELINE_COPILOT_COMMIT_ENABLED`.
**Runtimes.** El prompt es texto: idéntico en los 3. Es **el** mecanismo de paridad.
**Trabajo del operador:** ninguno.

---

### F5 — El endpoint de sesión

**Objetivo.** Exponer la sesión: crearla, leerla, avanzarla. **Sin ejecutar ninguna escritura.**
**Valor.** Da persistencia al hilo (resuelve U3) y es el consumidor real que exige `test_flag_wiring.py:52`.

**Archivo a crear**
- `Stacky Agents/backend/api/pipeline_copilot.py`

**Contrato**

```python
bp = Blueprint("pipeline_copilot", __name__, url_prefix="/pipeline-copilot")
# -> rutas /api/pipeline-copilot/...
# NO poner /api/ en el prefix (mismo gotcha que api/devops_agent.py:3-4).
```

| Método | Ruta | Función | Gate | Devuelve |
|---|---|---|---|---|
| `GET` | `/session/<int:conversation_id>` | `get_session()` | `_flag_off()` → 404 | `{"ok":True,"session":{...}}` |
| `POST` | `/session/<int:conversation_id>/advance` | `advance_session()` | `_flag_off()` → 404 | sesión nueva o `{"ok":False,"error":"transicion_ilegal","detail":motivo}` (409) |
| `GET` | `/session/<int:conversation_id>/question` | `next_question_route()` | `_flag_off()` → 404 | `{"ok":True,"question":str}` |
| `GET` | `/session/<int:conversation_id>/undo-hint` | `undo_hint_route()` | `_flag_off()` → 404 | `[ADICIÓN ARQUITECTO]` `{"ok":True,"undo_hint":str}` (`""` si todavía no aplica) |

**Reglas de implementación**
- `_flag_off()` lee `config.config.STACKY_PIPELINE_COPILOT_ENABLED` — **nunca** `os.getenv` con default local
  (lo gatea `tests/test_flags_env_read_meta.py`).
- La sesión se lee/escribe en el JSON de `Ticket.description` bajo la clave `pipeline_session` (D4), reusando el
  patrón tolerante de `_chat_meta()` (`api/devops_agent.py:31-40`). **Conservar** cualquier otra clave existente
  (ej. `server_alias` del plan 108) — leer, mutar solo `pipeline_session`, reescribir.
- El blueprint se registra en `backend/api/__init__.py` junto a los demás.
- `advance_session()` **no** ejecuta acciones: solo mueve el estado. Toda escritura sigue pasando por la tarjeta de
  confirmación del frontend (D1).

**[C6] Degradación honesta de `STACKY_PIPELINE_GENERATOR_ENABLED`.** `advance_session()` no llama al generador, pero
el copiloto no puede prometer un camino que va a morir en un 404 mudo. Regla cerrada: si esa flag está OFF,
`GET /session/<id>` devuelve además `"unavailable_actions": ["devops.pipeline_new.draft","devops.pipeline_new.commit"]`
y `"unavailable_reason": "STACKY_PIPELINE_GENERATOR_ENABLED"`. Con la flag ON, ambas claves salen vacías (`[]` y `""`).
**No se crea flag nueva.**

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_pipeline_copilot_api.py` (**10 casos**)

| # | Caso |
|---|---|
| 1 | `test_flag_off_da_404` en las **4** rutas |
| 2 | `test_get_session_de_conversacion_inexistente_da_404` |
| 3 | `test_get_session_nueva_devuelve_intake` |
| 4 | `test_advance_legal_persiste_el_estado` (releer con un `GET` posterior) |
| 5 | `test_advance_ilegal_da_409_y_no_muta` |
| 6 | `test_advance_preserva_server_alias_del_plan_108` — **guard anti-regresión de D4** |
| 7 | `test_question_devuelve_la_primera_pregunta_abierta` |
| 8 | `test_el_endpoint_no_ejecuta_ninguna_accion` — parsear el módulo con `ast` y afirmar que no hay `Import`/`ImportFrom` de `pipeline_generator` ni `Call` a `commit_route` |
| 9 | **`test_con_generator_off_la_sesion_declara_que_falta`** — **[C6]** con `STACKY_PIPELINE_GENERATOR_ENABLED=False`, `unavailable_actions` trae los 2 ids **y** `unavailable_reason == "STACKY_PIPELINE_GENERATOR_ENABLED"`; con la flag ON, `[]` y `""`. **El test guarda PRIMERO el caso ON** para que el assert de lista vacía no pase por accidente. |
| 10 | **`test_undo_hint_route_devuelve_el_texto_en_confirm_y_vacio_en_intake`** — `[ADICIÓN ARQUITECTO]` |

**Cabecera obligatoria en el archivo de test:** fijar `DATABASE_URL="sqlite:///:memory:"` antes de importar la app.

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_pipeline_copilot_api.py -q
```

**Criterio binario.** `10 passed`.
**Flag.** `STACKY_PIPELINE_COPILOT_ENABLED` (ON).
**Runtimes.** HTTP puro: idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F6 — Conectar el catálogo al turno del agente (el corazón del plan)

**Objetivo.** Que `_launch_turn()` envuelva el mensaje con el contrato del copiloto cuando la conversación tiene sesión.
**Valor.** Cierra K1: hoy **0** acciones del catálogo son alcanzables desde el turno; después, las 6.

**Archivo a editar**
- `Stacky Agents/backend/api/devops_agent.py`

**Cambio 1 — envolver el mensaje.** En `start_conversation()` (`:61`) y `send_message()` (`:157`), **después** del
bloque de `server_alias` que ya envuelve con `build_console_prompt` (`:129-135` y `:212-222`), agregar el envoltorio
del copiloto. Patrón calcado, mismo lugar, misma forma:

```python
# Plan 279 F6 — envolver con el contrato del copiloto SOLO si la conversacion
# tiene sesion de pipeline. Sin sesion => byte-compat total con hoy.
if _copilot_on() and session_dict:
    from services.pipeline_copilot_prompt import build_copilot_prompt
    from services.pipeline_session import session_from_dict
    message = build_copilot_prompt(
        session_from_dict(session_dict),
        request.host_url.rstrip("/"),
        message,
        conversation_id,
        commit_enabled=bool(
            getattr(_config.config, "STACKY_PIPELINE_COPILOT_COMMIT_ENABLED", False)
        ),
    )
```

**Orden obligatorio.** El envoltorio del copiloto va **después** del de consola remota, para que una conversación
anclada a un servidor conserve su contrato (el de consola es el más restrictivo).

**Cambio 2 — resolver U7 (paridad con Copilot) SIN borrar el gate.** Hoy `start_conversation()` devuelve **400**
para `github_copilot` (`:70-79`). El gate **no se borra**: se le agrega una salida honesta. Cuando el runtime no es
CLI **y** la flag del copiloto está ON, responder **200** con el camino determinista:

```python
if runtime not in _CLI_RUNTIMES:
    if _copilot_on():
        # Paridad plan 279: sin turno CLI, el piso determinista alcanza para
        # proponer y previsualizar (services/devops_action_matcher.py:1-5).
        return jsonify({
            "ok": True,
            "mode": "deterministic",
            "detail": ("Con GitHub Copilot el copiloto de pipelines usa el motor "
                       "determinista: proponé con POST /api/devops/actions/propose."),
            "propose_url": "/api/devops/actions/propose",
        }), 200
    return jsonify({...}), 400   # <- el 400 de hoy, INTACTO, para el resto
```

> **Por qué no se borra el 400.** Borrarlo dejaría a un `run` con Copilot terminando `completed` **sin conversación y
> sin error** — exactamente el falso verde que el gate existe para evitar.

> **[C3] ESTE CAMBIO SOLO NO ALCANZA.** Medido: `DevOpsAgentSection.tsx:28` declara
> `type CliRuntime = 'claude_code_cli' | 'codex_cli'` y su `<select>` (`:147-149`) tiene **exactamente 2** `<option>`.
> Con F6 solo, el operador **nunca puede mandar `runtime="github_copilot"`** y esta rama queda inalcanzable desde el
> producto. **La mitad frontend es F8 y es obligatoria.**

**Cambio 3 — helper local.**
```python
def _copilot_on() -> bool:
    return bool(getattr(_config.config, "STACKY_PIPELINE_COPILOT_ENABLED", False))
```

**[C2] EL GATE DE K1 ES POR `ast`, NO POR SUBSTRING.** Un `grep` / `"pipeline_copilot_prompt" in src` lo satisface un
**comentario**. El precedente del repo es explícito: un conteo por texto sobre un símbolo premia el bug. El caso 8 mira
el árbol sintáctico **y** el caso 3 mira el comportamiento. **Los dos son obligatorios**: el AST solo probaría que el
código existe, no que corre; el comportamiento solo probaría el efecto, y podría lograrse por un camino paralelo.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan279_agent_turn.py` (**8 casos**)

| # | Caso |
|---|---|
| 1 | `test_sin_flag_ni_sesion_el_modulo_importa_igual` — smoke de que F6 no rompe el import de `api.devops_agent` |
| 2 | `test_sin_sesion_el_mensaje_no_se_toca` — byte-compat: mockear `run_agent` y afirmar que `context_blocks[0]["content"]` es el mensaje crudo, **carácter por carácter** |
| 3 | `test_con_sesion_el_mensaje_se_envuelve` — **gate de comportamiento de K1**: mockear `run_agent`, mandar un `send_message` en una conversación con `pipeline_session`, y afirmar que `context_blocks[0]["content"]` **contiene el estado de la sesión y difiere del mensaje crudo** |
| 4 | `test_con_flag_off_el_mensaje_no_se_envuelve` |
| 5 | `test_copilot_con_flag_on_da_200_determinista` — `mode == "deterministic"` y `propose_url` presente |
| 6 | `test_copilot_con_flag_off_sigue_dando_400` — **anti-regresión del gate**, con el mensaje del 400 asertado (no sólo el status) |
| 7 | `test_conversacion_anclada_conserva_el_contrato_de_consola` — los dos envoltorios conviven **en orden** (consola primero, copiloto después) |
| 8 | **`test_ast_el_turno_llama_al_constructor_del_contrato`** — **gate estructural de K1**. Literal: parsear `api/devops_agent.py` con `ast.parse` y afirmar las **dos** cosas: (a) existe un `ast.ImportFrom` con `node.module == "services.pipeline_copilot_prompt"` y `"build_copilot_prompt"` entre sus `names`; (b) existe un `ast.Call` cuyo `func` es un `ast.Name(id="build_copilot_prompt")`. **Guard anti-falso-verde obligatorio en el mismo test:** antes de las 2 aserciones, correr el mismo censo sobre una constante de fuente que contiene sólo `# build_copilot_prompt` en un comentario y afirmar que da **0 imports y 0 calls** — si el censo no distingue el comentario del código, el gate no vale. |

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_plan279_agent_turn.py -q
```

**Criterio binario.** `8 passed`.
**Flag.** `STACKY_PIPELINE_COPILOT_ENABLED` (ON). Con la flag OFF, `devops_agent.py` se comporta **exactamente** como hoy.
**Runtimes.**
- *Claude Code CLI*: turno completo con contrato en el prompt.
- *Codex CLI*: idéntico (mismo camino `_launch_turn`).
- *GitHub Copilot Pro*: **fallback explícito** — 200 con `mode:"deterministic"` y la URL de `propose`; el operador
  conserva la capacidad completa vía matcher determinista + tarjeta de acción.

**Trabajo del operador:** ninguno.

---

### F7 — Secretos por referencia, con gate

**Objetivo.** Que el copiloto sepa **qué** credenciales faltan sin que ningún valor exista en su camino.
**Valor.** Resuelve U5 y cierra K3 con un test, no con una promesa.

**Archivo a crear**
- `Stacky Agents/backend/services/pipeline_copilot_secrets.py`

**Contrato**

```python
"""Plan 279 F7 — Variables faltantes POR NOMBRE. El valor no entra a este modulo.

Regla dura: este archivo NO puede importar secrets_store (resolve_secret_in_payload
:204 / read_secret_from_file :258 devuelven PLAINTEXT). El gate lo verifica.
"""
from __future__ import annotations

def required_variable_names(spec_dict: dict, provider: str, project: str) -> tuple[str, ...]:
    """Nombres de variables que la spec referencia y el proyecto NO define.

    Cruza:
      - services/pipeline_preflight.py:79  referenced_variables(spec_dict, target)
      - services/ci_variables.py:50        CIVariablesProvider.list_variables()  <- SIN valores
    Devuelve NOMBRES ordenados. NUNCA lanza; ante cualquier error devuelve ()."""

def secret_names(names: tuple[str, ...]) -> tuple[str, ...]:
    """Subconjunto que parece secreto, por services/ci_variables.py:31 looks_secret(key)
    ("Solo por key, nunca por valor"). NUNCA lanza."""
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_pipeline_copilot_secrets.py` (6 casos)

| # | Caso |
|---|---|
| 1 | `test_devuelve_solo_las_que_faltan` |
| 2 | `test_ordenado_y_sin_duplicados` |
| 3 | `test_secret_names_usa_looks_secret` |
| 4 | **`test_el_modulo_no_importa_secrets_store`** — parsear el fuente con `ast` y afirmar que ningún `ast.Import`/`ast.ImportFrom` menciona `secrets_store`. **Gate de K3.** |
| 5 | `test_ningun_valor_llega_al_prompt` — construir `PipelineSession(missing_variables=required_variable_names(...))`, pasarla a `build_copilot_prompt`, y afirmar que el prompt **no contiene** el valor de prueba `"valor-secreto-de-prueba"` inyectado en el fixture del provider |
| 6 | `test_error_del_provider_degrada_a_tupla_vacia` |

> **Guard anti-falso-verde del caso 5.** El test debe afirmar **primero** que el valor de prueba **sí** está en el
> fixture del provider (si no, un fixture vacío haría pasar el assert de ausencia por accidente), y **después** que no
> está en el prompt.

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_pipeline_copilot_secrets.py -q
```

**Criterio binario.** `6 passed`, y en particular el caso 4 (`0` imports de `secrets_store`).
**Flag.** `STACKY_PIPELINE_COPILOT_ENABLED`.
**Runtimes.** Idéntico en los 3 (módulo puro).
**Trabajo del operador:** ninguno. Si falta una variable, el copiloto la nombra y da el deep-link a **Variables**;
el operador la carga ahí, donde ya se cargan hoy.

---

### F8 — La sección `copiloto-pipelines`

**Objetivo.** Un solo lugar donde ocurre todo el flujo (K2).
**Valor.** Elimina el peregrinaje entre 4 pestañas.

**Archivos a crear**
- `Stacky Agents/frontend/src/components/devops/pipelineCopilotModel.ts` (lógica PURA)
- `Stacky Agents/frontend/src/components/devops/PipelineCopilotSection.tsx` (cascarón de presentación)
- `Stacky Agents/frontend/src/components/devops/__tests__/pipelineCopilotModel.test.ts`

**Archivos a editar**
- `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` (agregar la sección 18)
- `Stacky Agents/backend/services/devops_action_catalog.py` (`DEVOPS_SECTION_IDS`, `:46-51`)
- `Stacky Agents/backend/api/devops.py` (`_health_payload` — la def está en `:28`; las 2 keys nuevas van **tras `:116`**, justo antes del `}` de `:117`)
- **`Stacky Agents/frontend/src/components/devops/DevOpsAgentSection.tsx` — [C3], OBLIGATORIO**

**[C3] La mitad frontend de la paridad — sin esto, F6 es código muerto.**

En `DevOpsAgentSection.tsx`, **dos** ediciones literales:

1. `:28` — `type CliRuntime = 'claude_code_cli' | 'codex_cli';`
   → `type CliRuntime = 'claude_code_cli' | 'codex_cli' | 'github_copilot';`
2. tras `:149` (`<option value="codex_cli">Codex</option>`), agregar:
   ```tsx
   {/* Plan 279 F8 [C3] — GitHub Copilot no tiene turno CLI: el backend responde
       200 con mode:"deterministic" y el operador conserva la capacidad completa
       via matcher determinista + tarjeta de accion. Degradacion DECLARADA. */}
   <option value="github_copilot">GitHub Copilot (modo determinista)</option>
   ```

El default (`:49`, `useState<CliRuntime>('claude_code_cli')`) **no se toca**: el operador que no elige nada sigue
exactamente como hoy. **Cero trabajo extra**; es una opción más, no un paso más.

> **TRAMPA nº6 — la sección nueva va en TRES lugares o el ratchet se pone rojo.**
> `test_section_ids_espejan_el_tsx` (`test_devops_action_ratchet.py:77-87`) exige **igualdad exacta** entre los
> `id: '...'` del `.tsx` y `DEVOPS_SECTION_IDS`. Y `test_health_key_existe_en_health_payload` (`:59`) exige que
> `pipeline_copilot_enabled` y `pipeline_copilot_commit_enabled` existan en `_health_payload()`.
> Los tres cambios van juntos: `.tsx` + `DEVOPS_SECTION_IDS` + `_health_payload`.

**Entrada en `DEVOPS_SECTIONS`** (`DevOpsPage.tsx:145`), calcando la forma de la sección `agente` (`:184-192`):

```tsx
// Plan 279 — Copiloto de pipelines: un solo hilo conversacional.
{
  id: 'copiloto-pipelines',
  label: 'Copiloto de pipelines',
  group: 'construir',
  icon: '🧭',
  summary: 'Describí lo que necesitás y el copiloto arma, valida y explica la pipeline.',
  healthKey: 'pipeline_copilot_enabled',
  gateFlagKey: 'STACKY_PIPELINE_COPILOT_ENABLED',
  gateMessage: 'El copiloto de pipelines necesita la flag STACKY_PIPELINE_COPILOT_ENABLED (Configuración → Arnés, categoría DevOps).',
  render: (ctx) => <PipelineCopilotSection ctx={ctx} />,
},
```

**Añadir a `_health_payload()`** (`backend/api/devops.py`, tras `:116`), con el patrón exacto de las 3 keys del plan 267:

```python
"pipeline_copilot_enabled": bool(
    getattr(cfg, "STACKY_PIPELINE_COPILOT_ENABLED", False)
),  # Plan 279 — copiloto conversacional de pipelines (solo lectura)
"pipeline_copilot_commit_enabled": bool(
    getattr(cfg, "STACKY_PIPELINE_COPILOT_COMMIT_ENABLED", False)
),  # Plan 279 — crear la pipeline en el repo REAL (default OFF)
```

**Componentes REUSADOS (no se reescriben):**
- La tarjeta de propuesta: `frontend/src/components/devops/DevOpsActionProposalCard.tsx`.
- El modelo de la consola: `devopsActionConsoleModel.ts` — `ProposalView` (`:36`), `PROPOSAL_BLOCKS` (`:18`),
  `primaryActionLabel()` (`:57`).
- El runner: `frontend/src/services/devopsActionRunner.ts` vía `DEVOPS_ACTION_BINDINGS`.

**`pipelineCopilotModel.ts` (lógica pura, testeable sin DOM)** — el repo **no tiene RTL ni jsdom**, así que toda la
lógica va acá y el `.tsx` queda como cascarón:

```ts
export type SessionState =
  | 'intake' | 'discovery' | 'draft' | 'review'
  | 'secrets' | 'confirm' | 'committed' | 'failed';

/** Espejo de PIPELINE_SESSION_STATES (backend). */
export const SESSION_STATES: SessionState[] = [...];

/** Texto del paso actual, en castellano. Nunca vacío. */
export function stateLabel(s: SessionState): string;

/** Qué se le ofrece al operador en cada estado. Determinista. */
export function availableActionIds(s: SessionState): string[];

/** true si el estado exige confirmación explícita antes de seguir. */
export function needsOperatorConfirmation(s: SessionState): boolean;

/** [ADICIÓN ARQUITECTO] true si la tarjeta DEBE mostrar el undo_hint antes del
 *  botón de confirmar. Determinista: 'review' | 'secrets' | 'confirm'. */
export function mustShowUndoHint(s: SessionState): boolean;

/** Los 3 runtimes que el copiloto soporta, con su modo. Espejo de F6. */
export const COPILOT_RUNTIMES: { id: string; label: string; mode: 'cli' | 'deterministic' }[];
```

**Tests** — `__tests__/pipelineCopilotModel.test.ts` (**8 casos**)

| # | Caso |
|---|---|
| 1 | `SESSION_STATES` tiene 8 entradas |
| 2 | `stateLabel` no devuelve vacío para ninguno de los 8 |
| 3 | `availableActionIds('confirm')` incluye `devops.pipeline_new.commit` |
| 4 | `availableActionIds('intake')` **no** incluye ninguna acción de escritura. **Guard:** el test afirma primero que `availableActionIds('confirm')` **sí** trae una escritura, para que el assert de ausencia no pase con una lista vacía |
| 5 | `needsOperatorConfirmation('confirm') === true` y `('review') === false` |
| 6 | los ids devueltos son subconjunto de los 6 del plan |
| 7 | **`COPILOT_RUNTIMES` tiene los 3 ids y `github_copilot` tiene `mode === 'deterministic'`** — **[C3]**, espejo del `<select>` |
| 8 | **`mustShowUndoHint`** es `true` en `review`/`secrets`/`confirm` y `false` en los otros 5 — `[ADICIÓN ARQUITECTO]` |

**Comandos**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_devops_action_ratchet.py -q
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/components/devops/__tests__/pipelineCopilotModel.test.ts && npx tsc --noEmit
```

**Criterio binario.** Backend **`13 passed, 0 failed`** en `test_devops_action_ratchet.py` (**ahora sí completo**:
`test_health_key_existe_en_health_payload`, el único rojo permitido en F3, queda **cerrado acá**).
Frontend **`8 passed`** y `npx tsc --noEmit` con **0 errores**.
**Flag.** `STACKY_PIPELINE_COPILOT_ENABLED`. Con la flag OFF la pestaña se atenúa y el panel queda como hoy.
**Runtimes.** UI **con los 3**: el selector de `DevOpsAgentSection.tsx` se **extiende** a `github_copilot` (arriba),
que es lo que vuelve alcanzable la salida determinista de F6. Claude Code CLI y Codex CLI, sin cambios.
**Trabajo del operador:** ninguno (nace ON; el default del selector no se toca).

---

### F9 — Observabilidad, auditoría y cierre

**Objetivo.** Dejar rastro de las decisiones del agente y registrar todo lo nuevo en los ratchets.
**Valor.** Sin esto, "el agente decidió algo" no es auditable y los tests nuevos no corren en el arnés.

**Archivos a editar**
- `Stacky Agents/backend/scripts/run_harness_tests.sh`
- `Stacky Agents/backend/scripts/run_harness_tests.ps1`
- `Stacky Agents/backend/api/pipeline_copilot.py` (log de transición)

**Registro en los DOS ratchets — sintaxis DISTINTA.**
Son **7 archivos, no 6** (el E2E va en la misma tanda). En `.sh`, junto al bloque del plan 267 (`:977-981`), líneas desnudas:
```
  tests/test_plan279_baseline.py
  tests/test_pipeline_session.py
  tests/test_pipeline_copilot_prompt.py
  tests/test_pipeline_copilot_api.py
  tests/test_pipeline_copilot_secrets.py
  tests/test_plan279_agent_turn.py
  tests/test_plan279_e2e.py
```
En `.ps1`, junto al mismo bloque (`:871-875`), entre comillas y con coma:
```
  "tests/test_plan279_baseline.py",
  "tests/test_pipeline_session.py",
  "tests/test_pipeline_copilot_prompt.py",
  "tests/test_pipeline_copilot_api.py",
  "tests/test_pipeline_copilot_secrets.py",
  "tests/test_plan279_agent_turn.py",
  "tests/test_plan279_e2e.py",
```

**Auditoría de decisiones.** En `advance_session()`, dejar **una** línea por transición, calcando
`_log_si_quedo_bloqueada()` (`api/devops_actions.py:55-80`).

> **[C9] TRAMPA nº7 — el import.** `services/stacky_logger.py` **no** expone `info()` a nivel de módulo: define
> `class _StackyLogger` (`:153`) y **una instancia** `logger = _StackyLogger()` (`:511`). Un
> `import services.stacky_logger as stacky_logger` seguido de `.info(...)` revienta con `AttributeError`.
> El import es **exactamente** el del precedente (`devops_actions.py:71`):

```python
from services.stacky_logger import logger as stacky_logger

stacky_logger.info(
    "pipeline_copilot",
    "session_advance",
    conversation_id=conversation_id,
    origen=origen,
    destino=destino,
    action_id=session.last_action_id,
)
```

Todo el bloque va dentro de un `try/except Exception: pass`, igual que el precedente: **el log nunca puede romper la
request**.

**CERO PII, igual que el precedente (`devops_actions.py:64-66`):** se registran `conversation_id`, estados y
`action_id` (constantes del catálogo). **NO** se registra el texto del operador, ni el proyecto, ni la rama, ni
ningún nombre de variable, **ni el `undo_hint`** (que contiene la rama).

**[C11] Huella de regresión.** Agregar **una** entrada a `Stacky Agents/docs/sistema/error_fingerprints.json`
(hoy tiene **0** menciones de "279"), con el mismo esquema que las vecinas del plan 267:
`id: "plan279-sesion-de-copiloto-atascada"`, cuyo `log_pattern` matchee la línea `session_advance` con
`destino == "failed"`. Sin esto, "la sesión se murió" no deja rastro buscable.

**Tests E2E** — `Stacky Agents/backend/tests/test_plan279_e2e.py` (**6 casos**)

| # | Caso |
|---|---|
| 1 | `test_recorrido_feliz_intake_a_confirm` — 5 transiciones encadenadas por HTTP, terminando en `confirm` |
| 2 | **`test_los_3_runtimes_llegan_al_copiloto`** — **gate de K6, corregido [C3]**. v1 pegaba a `/api/devops/actions/propose`, que **ignora el runtime** (`api/devops_actions.py:95`) y habría dado verde sin probar nada. El gate real son **dos** aserciones sobre `POST /api/devops/agent/start`: (a) con `runtime` en `("claude_code_cli","codex_cli")` y la flag ON → arranca el turno CLI; (b) con `runtime="github_copilot"` y la flag ON → **`200`** con `mode == "deterministic"` y `propose_url == "/api/devops/actions/propose"`. **Más** el guard de que ese mismo request con la flag **OFF** sigue dando **`400`** (anti-regresión, espejo de F6 caso 6). |
| 3 | `test_commit_con_flag_off_queda_bloqueado` — la propuesta sale con `blocked_reason == "agent_write_disabled"` (`devops_action_proposal.py:27`) |
| 4 | `test_la_sesion_nunca_salta_a_committed_sin_pasar_por_confirm` |
| 5 | `test_la_transicion_deja_una_linea_de_log_sin_pii` — **guard anti-falso-verde obligatorio**: afirmar **primero** que el log capturado **contiene** `"session_advance"` (si el capturador no engancha, el assert de ausencia pasaría vacío), y **después** que **no** contiene el texto del operador, ni el nombre del proyecto, ni la rama |
| 6 | **`test_en_confirm_el_operador_ve_el_deshacer`** — `[ADICIÓN ARQUITECTO]`, **gate de K7**: recorrido HTTP hasta `confirm` con `provider="ado", branch="feature/x"`; `GET /api/pipeline-copilot/session/<id>/undo-hint` devuelve un texto que contiene `"azure-pipelines.yml"` **y** `"feature/x"`. Guard: en `intake` la misma ruta devuelve `""`. |

> **Registrar `test_plan279_e2e.py` también en los dos ratchets.**

**Comando final del plan**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_plan279_baseline.py tests/test_pipeline_session.py tests/test_pipeline_copilot_prompt.py tests/test_pipeline_copilot_api.py tests/test_pipeline_copilot_secrets.py tests/test_plan279_agent_turn.py tests/test_plan279_e2e.py tests/test_devops_action_ratchet.py tests/test_devops_action_catalog.py tests/test_devops_actions_api.py tests/test_devops_action_matcher.py -q
```

**Criterio binario [C1, C8] — la aritmética, explícita.**

| Archivo | Casos |
|---|---|
| `test_plan279_baseline.py` | 4 |
| `test_pipeline_session.py` | 11 |
| `test_pipeline_copilot_prompt.py` | 7 |
| `test_pipeline_copilot_api.py` | 10 |
| `test_pipeline_copilot_secrets.py` | 6 |
| `test_plan279_agent_turn.py` | 8 |
| `test_plan279_e2e.py` | 6 |
| **nuevos** | **52** |
| baseline (22+19+15+13, **medido: `69 passed`**; `test_devops_action_catalog.py` sigue en 22 porque su `:177` se **edita**, no se borra) | 69 |
| **TOTAL** | **121 passed, 0 failed** |

**Sin `-k` en ningún comando** (un `pytest -k` sin match da exit 0 = falso verde). **Sin `pytest tests` entero**
(hay contaminación cruzada conocida): el veredicto es **por archivo**, y el gate del arnés es `run_harness_tests`.
Además, `python -m pytest tests/test_harness_ratchet_meta.py tests/test_plan259_ratchet_script_parity.py -q` en verde.
**Flag.** Ninguna nueva.
**Runtimes.** El caso 2 **es** el gate de paridad, y sólo vale con la mitad frontend de F8 aplicada.
**Trabajo del operador:** ninguno.

---

## 7. Manejo seguro de credenciales — resumen del contrato

| Capa | Qué ve | Anclaje |
|---|---|---|
| Modelo (prompt) | **Solo nombres** de variables | F4 test 6, F7 test 5 |
| `pipeline_copilot_secrets.py` | Solo nombres; **prohibido** importar `secrets_store` | F7 test 4 (gate por `ast`) |
| `ci_variables.list_variables()` | `{"key","is_secret","has_value","masked"}` — sin valores | `services/ci_variables.py:50`, `ado_variables.py:44-49` |
| Resolución de valor | `resolve_secret_in_payload` (`secrets_store.py:204`) — **fuera** del camino del copiloto | — |
| Defensa en profundidad | `mask_token_values` (`secret_masking.py:20`), gate de secretos en commit (`STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED`) | `api/pipeline_generator.py:77` |

**Permisos.** No hay RBAC ni lo habrá: Stacky es mono-operador. El único control real es la **flag + confirmación
explícita**, que es exactamente lo que el plan usa.

---

## 8. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| **R1** | El implementador escribe `default=False` en la flag OFF | **Alta** | Rompe `test_harness_flags.py` | F1 lo marca como TRAMPA nº1 con los 2 precedentes literales |
| **R2** | Agrega acciones sin binding → ratchet frontend rojo | **Alta** | Bloquea F3 | F3 obliga a backend+frontend en la misma fase (TRAMPA nº2) |
| **R3** | Inventa frases que colisionan read/write | **Alta** | `test_frases_no_colisionan` rojo | F3 da las 18 frases literales y prohíbe improvisar (TRAMPA nº5) |
| **R4** | Agrega la sección al `.tsx` y olvida `DEVOPS_SECTION_IDS` | **Alta** | `test_section_ids_espejan_el_tsx` rojo | F8 TRAMPA nº6: los 3 lugares juntos |
| **R5** | Arma las entradas del catálogo con un helper | Media | Ratchets **inertes** (falso verde) | F3 TRAMPA nº3, citando `devops_action_catalog.py:140-144` |
| **R6** | El agente ignora el contrato del prompt | Media | Sesión no avanza | El matcher determinista es el piso (D3); la sesión no se corrompe |
| **R7** | `Ticket.description` crece sin control | Baja | Fila pesada | `MAX_SESSION_BYTES = 8192`; la sesión guarda referencias, no YAML |
| **R8** | Un pytest sin `DATABASE_URL` escribe en la base viva del operador | Media | Corrupción de datos reales | Prefijo obligatorio en **todos** los comandos del plan |
| **R9** | Borrar el 400 de Copilot deja falsos verdes | Media | Regresión silenciosa | F6 **no** borra el gate: agrega salida 200 explícita, con test anti-regresión (caso 6) |
| **R10** | El envoltorio del copiloto pisa el de consola remota | Baja | Pierde el anclaje del plan 108 | F6 fija el orden y lo congela (caso 7) |

---

## 9. Fuera de scope (explícito)

**Alcance cerrado, en números:**
- **Proveedores: exactamente 2** — `ado` y `gitlab` (`pipeline_lint.py:59`). Nada de Jenkins, GitHub Actions o CircleCI.
- **Stacks: exactamente 3** — `python`, `node`, `dotnet` (`_MANIFEST_SIGNALS`, `pipeline_stack_detector.py:12-16`). **[C12]**
- **Acciones nuevas: exactamente 6** (5 read + 1 write). El catálogo pasa de 23 a **29** (21 read + 8 write).
- **Flags nuevas: exactamente 2.** **Cero** flags equivalentes a las 13 `STACKY_PIPELINE_*` que ya existen.
- **Endpoints backend nuevos: 0.** Wrappers tipados nuevos en `endpoints.ts` para rutas existentes: **exactamente 2**. **[C4]**
- **Estados: exactamente 8.**
- **Tests nuevos: exactamente 52 casos backend** en 7 archivos, **+ 8 casos frontend** en 1 archivo.
- **Archivos de test AJENOS que se editan: exactamente 2** — `test_devops_action_catalog.py:177` (`7`→`8`, **[C1]**) y
  `devopsActionCatalogRatchet.test.ts` (3 pisos, **[C7]**). Ambos son ratchets que **se aprietan**; **ningún assert se borra**.

**NO se hace en este plan:**
1. No se elimina ni fusiona ninguna de las 17 secciones actuales.
2. No se toca el motor de generación, lint, patcher, diff ni preflight (solo se los llama).
3. No se agregan endpoints de ejecución (§7.4 del plan 267 sigue vigente).
4. No se envuelven Handoff (plan 252), Profiler ni Matriz de entornos (plan 251) como acciones del copiloto.
5. No hay ejecución real de la pipeline creada dentro del hilo: disparar sigue siendo `devops.pipeline.trigger`.
6. No hay sandbox de ejecución de pipeline: la "prueba automática" del copiloto es **lint + explain + preflight**
   (estático), no una corrida real. Una corrida en sandbox es otro plan.
7. No hay rollback **automático** de un commit: si `devops.pipeline_new.commit` falla, la sesión va a `failed` y el
   operador revierte con git (D9). **[ADICIÓN ARQUITECTO]** Lo que **sí** hay ahora es el `undo_hint`: el operador ve
   **antes de confirmar** exactamente qué archivo y qué rama tendría que revertir (D10). Deshacer **informado**, no
   deshacer automático — el humano sigue siendo quien decide.

---

## 10. Glosario

| Término | Significado |
|---|---|
| **Acción** | Entrada de `DEVOPS_ACTION_CATALOG`: identidad + seguridad de una operación. El *cómo* vive en el binding. |
| **Binding** | Función en `devopsActionBindings.ts` que ejecuta una acción llamando a un endpoint **existente**. |
| **Propuesta** | `ActionProposal` (`devops_action_proposal.py:47`): qué se haría, con qué params, qué falta, si necesita confirmación. |
| **Sesión** | `PipelineSession` (F2): el estado del procedimiento de creación, persistido en el JSON de `Ticket.description`. |
| **Piso determinista** | `match_intent()` sin modelo: el mecanismo que garantiza paridad con GitHub Copilot. |
| **Handle de secreto** | El **nombre** de una variable. El copiloto solo maneja handles. |

---

## 11. Orden de implementación

```
F0 (censo, nace rojo)
  └─> F1 (flags)            ← bloquea F3: el ratchet exige la flag en FLAG_REGISTRY
        └─> F2 (estados)    ← puro, sin dependencias
              └─> F3 (6 acciones + 6 bindings)   ← backend y frontend JUNTOS
                    └─> F4 (prompt)              ← necesita PipelineSession de F2
                          └─> F5 (endpoint)      ← cierra test_flag_wiring de F1
                                └─> F6 (turno del agente)   ← el corazón, cierra K1
                                      └─> F7 (secretos)     ← cierra K3
                                            └─> F8 (UI)     ← cierra K2 y el health_key de F3
                                                  └─> F9 (ratchets + E2E)  ← cierra F0
```

**Ninguna fase puede saltearse.** F3 deja `test_health_key_existe_en_health_payload` rojo a propósito hasta F8: es la
**única** excepción declarada (nodeid exacto en §6.F3), y F8 debe cerrarla.

**[C3] F6 y F8 son inseparables para la paridad.** F6 sin F8 deja la rama `github_copilot` inalcanzable desde el
producto; F8 sin F6 ofrece una opción que devuelve 400. Si por alguna razón se implementa una sola, **K6 no se marca**.

---

## 12. Definition of Done

- [ ] **`121 passed, 0 failed`** en el comando final de F9 (desglose en §6.F9).
- [ ] `npx tsc --noEmit` en `frontend/`: **0 errores**.
- [ ] `npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts`: **7 passed** con los **3** pisos en **29 / 29 / 21** (`:56`, `:62`, `:67`). **[C7]**
- [ ] `npx vitest run src/components/devops/__tests__/pipelineCopilotModel.test.ts`: **8 passed**.
- [ ] `test_harness_ratchet_meta.py` y `test_plan259_ratchet_script_parity.py` en verde (los 7 tests nuevos en `.sh` **y** `.ps1`).
- [ ] **K1 [C2]**: F6 casos 3 **y** 8 verdes (`ast` + comportamiento). **NO se acepta un `grep`/substring como evidencia de K1.**
- [ ] **K3**: F7 casos 4 y 5 verdes — `0` imports de `secrets_store` en `pipeline_copilot_secrets.py`, y el valor de prueba **primero** confirmado en el fixture y **después** ausente del prompt.
- [ ] **K4**: `len(DEVOPS_ACTION_CATALOG) == 29` (21 read + 8 write) y deriva catálogo↔bindings = 0.
- [ ] **K6 [C3]**: F9 caso 2 verde **y** el `<select>` de `DevOpsAgentSection.tsx` ofrece las 3 opciones. Con una sola de las dos mitades, K6 **no se marca**.
- [ ] **K7 [ADICIÓN ARQUITECTO]**: F9 caso 6 verde — en `confirm` el operador ve la ruta y la rama exactas a revertir.
- [ ] **[C1]** `tests/test_devops_action_catalog.py:177` dice `== 8` y **sigue siendo una igualdad** (no `>=`, no borrado, no comentado). F0 caso 3 lo vigila.
- [ ] **[C11]** `docs/sistema/error_fingerprints.json` tiene la huella `plan279-sesion-de-copiloto-atascada` y el JSON parsea.
- [ ] Con **ambas flags OFF**, el panel DevOps es funcionalmente idéntico a hoy (F6 casos 2, 4 y 6).
- [ ] Smoke manual (requiere backend + token, no automatizable): crear una pipeline de cero por el hilo, en un
      proyecto ADO y en uno GitLab, hasta `confirm` **sin** activar la flag de commit, **verificando que el
      `undo_hint` nombra el archivo correcto en cada proveedor**.
- [ ] Smoke manual de paridad **[C3]**: elegir "GitHub Copilot (modo determinista)" en el selector y confirmar que la
      sección responde con el camino determinista en vez del 400.
