# Plan 279 — El copiloto de pipelines: un solo hilo conversacional

**Estado:** v1 (PROPUESTO — sin criticar)
**Rama:** `docs/plan-279`
**Origen:** pedido del operador (2026-08-01): rediseñar la creación y gestión de pipelines como experiencia *agentic-first*.
**Tipo:** orquestación de capacidades existentes. **NO** reimplementa generación, lint, diff, auditoría, preflight ni matriz de entornos.

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
| **K1** | Acciones del catálogo alcanzables desde el **turno del agente** | **0** | **≥ 6** | `grep -c "devops_action_catalog" backend/api/devops_agent.py` hoy da **0** (verificado). Gate: F6 test 1 |
| **K2** | Pestañas que el operador debe visitar para crear una pipeline de cero y dejarla verificada | **≥ 4** (`pipelines`, `editar-pipeline`, `pipeline-audit`, `matriz-entornos`) | **1** (`copiloto-pipelines`) | F8 test 3: la sección nueva declara las 6 acciones sin `nav_path` a otra sección |
| **K3** | Valor de secreto que llega al prompt del modelo | sin gate | **0, con test** | F7 test 4: gate por sustring sobre el prompt construido |
| **K4** | Acciones del catálogo / deriva catálogo↔bindings | 23 / 0 | 29 / **0** | `devopsActionCatalogRatchet.test.ts` caso 3 (igualdad exacta de conjuntos) |
| **K5** | Estados de creación explícitos y cerrados | **0** (no existe máquina de estados) | **8**, con transiciones cerradas | F2 test 1: `len(PIPELINE_SESSION_STATES) == 8` |
| **K6** | Paridad de los 3 runtimes en el piso determinista | ya cierta, sin gate propio | gate propio | F9 test 2: el mismo texto produce la misma propuesta con los 3 valores de `runtime` |

**Baseline de tests medido hoy (todos VERDES, con `backend/venv`, py3.11.9):**

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
- `@dataclass(frozen=True) class ActionParam` (`:54`) y `class DevOpsAction` (`:64`), con `phrases` (`:78`) —
  **frases de intención para matcheo determinista**.
- `DEVOPS_ACTION_CATALOG` (`:146`): **23 acciones**, 16 de lectura (desde `:148`) y 7 de escritura (desde `:412`).
- Lookups: `get_action()` (`:589`), `visible_actions()` (`:594`), `palette_actions()` (`:618`),
  **`assistant_actions()` (`:625`)**, `param_of()` (`:631`), `action_to_dict()` (`:638`), `catalog_payload()` (`:656`).

**(b) Motor de intención y contrato de propuesta — también del plan 267, y el brief no los mencionaba:**

- `backend/services/devops_action_matcher.py`: `normalize_text()` (`:49`), `_phrase_score()` (`:59`),
  `match_intent()` (`:80`), `is_ambiguous()` (`:100`), con `MIN_SCORE = 0.6` (`:14`), `AMBIGUITY_DELTA = 0.10` (`:15`),
  `MAX_MATCHES = 3` (`:16`) y `_STOPWORDS` (`:28`). Su docstring (`:1-5`) lo declara literalmente:
  *"Es el piso de paridad: con GitHub Copilot (o sin runtime disponible) este matcher es TODO el motor de intención"*.
- `backend/services/devops_action_proposal.py`: `ActionProposal` (`:47`) con `what_will_happen`, `open_questions`,
  `alternatives`, `confidence`, **`needs_confirmation`** y `blocked_reason`; `build_proposal()` (`:78`),
  `describe()` (`:68`), `proposal_to_dict()` (`:129`), y los 6 estados `BLOCKED_*` (`:22-30`).

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
| `services/pipeline_stack_detector.py` | `detect_stack(project_root)` | `:19` | `'python'\|'node'\|'dotnet'\|None` (`:13-15`) |
| `api/pipeline_generator.py` | `POST /preview` / `POST /commit` | `:34` / `:52` | commit ya exige `confirm is True` (`:59`) |
| `api/pipeline_editor.py` | `/verbs` `/plan` `/commit` `/interpret` | `:141` `:171` `:199` `:428` | commit con doble flag (`_guard_commit` `:60`) |

**Nada de esto se reescribe.**

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

**U7 es el riesgo de paridad más concreto del plan** y se resuelve en F6 con degradación explícita, no borrando el gate.

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

- **Problema.** Con Copilot no hay turno CLI (U7).
- **Recomendación.** La sesión avanza igual con `match_intent()` (`devops_action_matcher.py:80`), sin modelo.
- **Alternativas.** Bloquear Copilot — rechazada: viola la regla de los 3 runtimes.
- **Riesgo.** Menor riqueza conversacional con Copilot. Declarado como degradación controlada, no como falla.

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
| 3 | `test_el_turno_del_agente_conoce_el_catalogo` | el fuente de `api/devops_agent.py` referencia `pipeline_copilot_prompt` (gate de K1) |
| 4 | `test_lectura_y_escritura_siguen_separadas` | `len([a for a in DEVOPS_ACTION_CATALOG if a.effect=="write"]) == 8` |

**Nota de orden.** F0 nace **ROJO a propósito** y se pone verde al terminar F3/F6. Es el ratchet del plan, no un gate de arranque.

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

> **Depth-1 verificado:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` (`harness_flags.py:6194`) **no** declara `requires=`,
> así que apuntarle cumple la regla de `validate_requires_graph`.

**TRAMPA nº1 (un modelo menor la pisa seguro).** La flag que nace OFF **NO declara `default=` en absoluto**. El OFF
vive **solo** en `config.py`. Precedentes literales: `harness_flags.py:6234-6240`
(`STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED`) y `:3605-3609` (`STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`).
Escribir `default=False` **rompe** `test_harness_flags.py`.

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


@dataclass(frozen=True)
class PipelineSession:
    state: str = "intake"
    provider: str = ""            # "ado" | "gitlab" | ""
    stack: str = ""               # "python" | "node" | "dotnet" | ""
    project: str = ""
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
```

**Casos borde obligatorios**
- `advance()` a un estado terminal desde otro terminal → rechazada con motivo `"estado_terminal"`.
- `session_from_dict(None)` / `{}` / `{"state": "inventado"}` → `PipelineSession()` por defecto.
- `session_to_dict` serializado con `json.dumps` debe pesar `<= MAX_SESSION_BYTES`.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_pipeline_session.py` (10 casos)

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
| 9 | `test_roundtrip_to_dict_from_dict` |
| 10 | `test_next_question_es_determinista_y_vacia_si_no_faltan` |

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_pipeline_session.py -q
```

**Criterio binario.** `10 passed`.
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

**Archivos a editar**
- `Stacky Agents/backend/services/devops_action_catalog.py` (agregar 5 lecturas antes de `:411` y 1 escritura antes del cierre `:584`)
- `Stacky Agents/frontend/src/services/devopsActionBindings.ts`
- `Stacky Agents/frontend/src/__tests__/devopsActionCatalogRatchet.test.ts` (subir los pisos, ver abajo)

> **TRAMPA nº3 — escribir las entradas EXPANDIDAS.** El comentario `devops_action_catalog.py:140-144` lo dice literal:
> los ratchets parsean este archivo **como TEXTO** buscando `id="..."`, `effect="..."` y `reach=canonical_reach("...")`
> línea por línea. **PROHIBIDO** un helper o un bucle que arme las entradas: dejaría los ratchets inertes.
>
> **TRAMPA nº4 — el id debe matchear `/^\s*id="(devops\.[a-z_]+\.[a-z_]+)"/`** (`devopsActionCatalogRatchet.test.ts:21`):
> exactamente **dos** segmentos después de `devops.`, minúsculas y guión bajo. `devops.pipeline_new.draft` sirve;
> `devops.pipeline.new.draft` **no matchea**.

**Las 6 entradas**

| # | id | effect | impact | health_key | flag_key | Envuelve |
|---|----|--------|--------|-----------|----------|----------|
| 1 | `devops.pipeline_new.draft` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `POST /api/pipeline-generator/preview` (`api/pipeline_generator.py:34`) |
| 2 | `devops.pipeline_new.lint` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `lint_yaml()` (`pipeline_lint.py:791`) |
| 3 | `devops.pipeline_new.explain` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `explain_plan()` (`pipeline_lint.py:1031`) |
| 4 | `devops.pipeline_new.preflight` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `check_placeholders` + `check_undefined_variables` (`pipeline_preflight.py:37`, `:102`) |
| 5 | `devops.pipeline_new.secrets` | read | none | `pipeline_copilot_enabled` | `STACKY_PIPELINE_COPILOT_ENABLED` | `GET /api/devops/variables` (`api/devops_variables.py:46`) — **solo nombres** |
| 6 | `devops.pipeline_new.commit` | **write** | **high** | `pipeline_copilot_commit_enabled` | `STACKY_PIPELINE_COPILOT_COMMIT_ENABLED` | `POST /api/pipeline-generator/commit` (`api/pipeline_generator.py:52`) |

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
frase de lectura es subconjunto o superconjunto del de **cualquier** frase de escritura (stopwords excluidas,
`devops_action_matcher.py:28`). Las frases de abajo están diseñadas para no colisionar; **no improvisar otras**.

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

**Bindings** en `frontend/src/services/devopsActionBindings.ts`, reusando los helpers ya presentes:
`callEndpoint()` (`:72`) para 1–5 y para 6; ninguno usa `goToPanel()` (`:47`) porque las 6 sí tienen endpoint real.
**PROHIBIDO agregar endpoints nuevos** (`:1-2`).

**Subir los pisos del ratchet frontend** (un ratchet que nunca se aprieta es inerte):
- caso 5 (`:55`): `toBeGreaterThanOrEqual(23)` → **`29`**
- caso 6 (`:59-67`): `toBeGreaterThanOrEqual(12)` → **`21`** (16 lecturas actuales + 5 nuevas)

**Tests**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_devops_action_ratchet.py tests/test_devops_action_catalog.py tests/test_devops_action_matcher.py -q
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts
```

**Criterio binario.** Backend: `13 + 22 + 15 = 50 passed` (salvo `test_health_key_existe_en_health_payload`, que
queda rojo hasta F8 — **es la única excepción permitida y debe cerrarse en F8**). Frontend: `7 passed`.
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

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_pipeline_copilot_prompt.py` (6 casos)

| # | Caso |
|---|---|
| 1 | `test_el_prompt_nombra_el_estado_actual` |
| 2 | `test_el_prompt_lista_solo_las_transiciones_legales` |
| 3 | `test_el_prompt_incluye_la_url_de_propose` |
| 4 | `test_con_commit_off_el_prompt_prohibe_la_accion_de_commit` |
| 5 | `test_el_prompt_incluye_la_regla_de_no_pedir_valores` |
| 6 | `test_los_nombres_de_variables_aparecen_pero_ningun_valor` — construir la sesión con `missing_variables=("DB_PASSWORD","API_TOKEN")`, y afirmar que el prompt **contiene** esos nombres |

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_pipeline_copilot_prompt.py -q
```

**Criterio binario.** `6 passed`.
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

**Reglas de implementación**
- `_flag_off()` lee `config.config.STACKY_PIPELINE_COPILOT_ENABLED` — **nunca** `os.getenv` con default local
  (lo gatea `tests/test_flags_env_read_meta.py`).
- La sesión se lee/escribe en el JSON de `Ticket.description` bajo la clave `pipeline_session` (D4), reusando el
  patrón tolerante de `_chat_meta()` (`api/devops_agent.py:31-40`). **Conservar** cualquier otra clave existente
  (ej. `server_alias` del plan 108) — leer, mutar solo `pipeline_session`, reescribir.
- El blueprint se registra en `backend/api/__init__.py` junto a los demás.
- `advance_session()` **no** ejecuta acciones: solo mueve el estado. Toda escritura sigue pasando por la tarjeta de
  confirmación del frontend (D1).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_pipeline_copilot_api.py` (8 casos)

| # | Caso |
|---|---|
| 1 | `test_flag_off_da_404` en las 3 rutas |
| 2 | `test_get_session_de_conversacion_inexistente_da_404` |
| 3 | `test_get_session_nueva_devuelve_intake` |
| 4 | `test_advance_legal_persiste_el_estado` (releer con un `GET` posterior) |
| 5 | `test_advance_ilegal_da_409_y_no_muta` |
| 6 | `test_advance_preserva_server_alias_del_plan_108` — **guard anti-regresión de D4** |
| 7 | `test_question_devuelve_la_primera_pregunta_abierta` |
| 8 | `test_el_endpoint_no_ejecuta_ninguna_accion` — afirmar que el módulo no importa `devopsActionBindings` ni llama a `pipeline_generator.commit_route` |

**Cabecera obligatoria en el archivo de test:** fijar `DATABASE_URL="sqlite:///:memory:"` antes de importar la app.

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_pipeline_copilot_api.py -q
```

**Criterio binario.** `8 passed`.
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

**Cambio 3 — helper local.**
```python
def _copilot_on() -> bool:
    return bool(getattr(_config.config, "STACKY_PIPELINE_COPILOT_ENABLED", False))
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan279_agent_turn.py` (7 casos)

| # | Caso |
|---|---|
| 1 | `test_el_modulo_referencia_el_contrato_del_copiloto` — gate de **K1** |
| 2 | `test_sin_sesion_el_mensaje_no_se_toca` — byte-compat: mockear `run_agent` y afirmar que `context_blocks[0]["content"]` es el mensaje crudo |
| 3 | `test_con_sesion_el_mensaje_se_envuelve` — el contenido contiene el estado de la sesión |
| 4 | `test_con_flag_off_el_mensaje_no_se_envuelve` |
| 5 | `test_copilot_con_flag_on_da_200_determinista` |
| 6 | `test_copilot_con_flag_off_sigue_dando_400` — **anti-regresión del gate** |
| 7 | `test_conversacion_anclada_conserva_el_contrato_de_consola` — los dos envoltorios conviven en orden |

**Comando**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_plan279_agent_turn.py -q
```

**Criterio binario.** `7 passed`.
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
- `Stacky Agents/backend/api/devops.py` (`_health_payload`, agregar 2 keys tras `:116`)

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
```

**Tests** — `__tests__/pipelineCopilotModel.test.ts` (6 casos)

| # | Caso |
|---|---|
| 1 | `SESSION_STATES` tiene 8 entradas |
| 2 | `stateLabel` no devuelve vacío para ninguno de los 8 |
| 3 | `availableActionIds('confirm')` incluye `devops.pipeline_new.commit` |
| 4 | `availableActionIds('intake')` **no** incluye ninguna acción de escritura |
| 5 | `needsOperatorConfirmation('confirm') === true` y `('review') === false` |
| 6 | los ids devueltos son subconjunto de los 6 del plan |

**Comandos**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_devops_action_ratchet.py -q
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/components/devops/__tests__/pipelineCopilotModel.test.ts && npx tsc --noEmit
```

**Criterio binario.** Backend `13 passed` (**ahora sí completo**, incluido `test_health_key_existe_en_health_payload`).
Frontend `6 passed` y `tsc --noEmit` con **0 errores**.
**Flag.** `STACKY_PIPELINE_COPILOT_ENABLED`. Con la flag OFF la pestaña se atenúa y el panel queda como hoy.
**Runtimes.** UI: idéntica en los 3. El selector de runtime existente (`DevOpsAgentSection.tsx:147-150`) se reusa.
**Trabajo del operador:** ninguno (nace ON).

---

### F9 — Observabilidad, auditoría y cierre

**Objetivo.** Dejar rastro de las decisiones del agente y registrar todo lo nuevo en los ratchets.
**Valor.** Sin esto, "el agente decidió algo" no es auditable y los tests nuevos no corren en el arnés.

**Archivos a editar**
- `Stacky Agents/backend/scripts/run_harness_tests.sh`
- `Stacky Agents/backend/scripts/run_harness_tests.ps1`
- `Stacky Agents/backend/api/pipeline_copilot.py` (log de transición)

**Registro en los DOS ratchets — sintaxis DISTINTA.**
En `.sh`, junto a `:978-981`, líneas desnudas:
```
  tests/test_plan279_baseline.py
  tests/test_pipeline_session.py
  tests/test_pipeline_copilot_prompt.py
  tests/test_pipeline_copilot_api.py
  tests/test_pipeline_copilot_secrets.py
  tests/test_plan279_agent_turn.py
```
En `.ps1`, junto a `:872-875`, entre comillas y con coma:
```
  "tests/test_plan279_baseline.py",
  "tests/test_pipeline_session.py",
  "tests/test_pipeline_copilot_prompt.py",
  "tests/test_pipeline_copilot_api.py",
  "tests/test_pipeline_copilot_secrets.py",
  "tests/test_plan279_agent_turn.py",
```

**Auditoría de decisiones.** En `advance_session()`, dejar **una** línea por transición con
`services/stacky_logger.py`, calcando `_log_si_quedo_bloqueada()` (`api/devops_actions.py:55-79`):

```python
stacky_logger.info(
    "pipeline_copilot",
    "session_advance",
    conversation_id=conversation_id,
    origen=origen,
    destino=destino,
    action_id=session.last_action_id,
)
```

**CERO PII, igual que el precedente (`devops_actions.py:63-65`):** se registran `conversation_id`, estados y
`action_id` (constantes del catálogo). **NO** se registra el texto del operador, ni el proyecto, ni la rama, ni
ningún nombre de variable.

**Tests E2E** — `Stacky Agents/backend/tests/test_plan279_e2e.py` (5 casos)

| # | Caso |
|---|---|
| 1 | `test_recorrido_feliz_intake_a_confirm` — 5 transiciones encadenadas por HTTP, terminando en `confirm` |
| 2 | `test_los_3_runtimes_producen_la_misma_propuesta` — **gate de K6**: `POST /api/devops/actions/propose` con el mismo texto y `runtime` en `("claude_code_cli","codex_cli","github_copilot")` → el `action_id` y el `confidence` deben ser **idénticos** |
| 3 | `test_commit_con_flag_off_queda_bloqueado` — la propuesta sale con `blocked_reason == "agent_write_disabled"` (`devops_action_proposal.py:27`) |
| 4 | `test_la_sesion_nunca_salta_a_committed_sin_pasar_por_confirm` |
| 5 | `test_la_transicion_deja_una_linea_de_log_sin_pii` — capturar el log y afirmar que **no** contiene el texto del operador |

> **Registrar `test_plan279_e2e.py` también en los dos ratchets.**

**Comando final del plan**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && DATABASE_URL="sqlite:///:memory:" ./venv/Scripts/python.exe -m pytest tests/test_plan279_baseline.py tests/test_pipeline_session.py tests/test_pipeline_copilot_prompt.py tests/test_pipeline_copilot_api.py tests/test_pipeline_copilot_secrets.py tests/test_plan279_agent_turn.py tests/test_plan279_e2e.py tests/test_devops_action_ratchet.py tests/test_devops_action_catalog.py tests/test_devops_actions_api.py tests/test_devops_action_matcher.py -q
```

**Criterio binario.** `4+10+6+8+6+7+5 = 46` casos nuevos verdes **más** los 69 de baseline = **115 passed, 0 failed**.
Y `python -m pytest tests/test_harness_ratchet_meta.py tests/test_plan259_ratchet_script_parity.py -q` en verde.
**Flag.** Ninguna nueva.
**Runtimes.** El caso 2 **es** el gate de paridad.
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
- **Stacks: exactamente 3** — `python`, `node`, `dotnet` (`pipeline_stack_detector.py:13-15`).
- **Acciones nuevas: exactamente 6** (5 read + 1 write). El catálogo pasa de 23 a **29**.
- **Flags nuevas: exactamente 2.**
- **Estados: exactamente 8.**
- **Tests nuevos: exactamente 46 casos** en 7 archivos.

**NO se hace en este plan:**
1. No se elimina ni fusiona ninguna de las 17 secciones actuales.
2. No se toca el motor de generación, lint, patcher, diff ni preflight (solo se los llama).
3. No se agregan endpoints de ejecución (§7.4 del plan 267 sigue vigente).
4. No se envuelven Handoff (plan 252), Profiler ni Matriz de entornos (plan 251) como acciones del copiloto.
5. No hay ejecución real de la pipeline creada dentro del hilo: disparar sigue siendo `devops.pipeline.trigger`.
6. No hay sandbox de ejecución de pipeline: la "prueba automática" del copiloto es **lint + explain + preflight**
   (estático), no una corrida real. Una corrida en sandbox es otro plan.
7. No hay rollback automático de un commit: si `devops.pipeline_new.commit` falla, la sesión va a `failed` y el
   operador revierte con git (D9).

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
**única** excepción declarada, y F8 debe cerrarla.

---

## 12. Definition of Done

- [ ] `115 passed, 0 failed` en el comando final de F9.
- [ ] `npx tsc --noEmit` en `frontend/`: **0 errores**.
- [ ] `npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts`: **7 passed** con los pisos en 29 y 21.
- [ ] `test_harness_ratchet_meta.py` y `test_plan259_ratchet_script_parity.py` en verde (los 7 tests nuevos en `.sh` **y** `.ps1`).
- [ ] **K1**: `grep -c "pipeline_copilot_prompt" backend/api/devops_agent.py` ≥ 1 (hoy el catálogo da 0).
- [ ] **K3**: F7 caso 4 verde — `0` imports de `secrets_store` en `pipeline_copilot_secrets.py`.
- [ ] **K4**: `len(DEVOPS_ACTION_CATALOG) == 29` y deriva catálogo↔bindings = 0.
- [ ] **K6**: F9 caso 2 verde — los 3 runtimes producen la misma propuesta.
- [ ] Con **ambas flags OFF**, el panel DevOps es funcionalmente idéntico a hoy (F6 casos 2, 4 y 6).
- [ ] Smoke manual (requiere backend + token, no automatizable): crear una pipeline de cero por el hilo, en un
      proyecto ADO y en uno GitLab, hasta `confirm` **sin** activar la flag de commit.
