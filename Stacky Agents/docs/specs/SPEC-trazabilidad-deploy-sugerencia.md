# SPEC-trazabilidad-deploy-sugerencia — Trazabilidad de ejecución, deploy canónico de agentes y sugerencia técnico/developer

**Versión:** 1.0.0
**Fecha:** 2026-06-09
**Autor:** Stacky Tool Architect (SDD)
**Branch sugerido:** `feat/exec-trace-deploy-canonical-suggestion`
**Estado:** Propuesto (pendiente de aprobación del operador)

---

## 0. Resumen ejecutivo

Este SDD cubre **tres mejoras independientes** que pueden implementarse y mergearse por
separado (cada una tiene su propio set de CA y TU). Se documentan en un solo plan por
pedido del operador, pero **no comparten estado**: el orden recomendado de entrega es
Feature 3 → Feature 1 → Feature 2 (de menor a mayor superficie de cambio).

| # | Feature | Problema que resuelve | Superficie |
|---|---|---|---|
| F1 | **Trazabilidad de ejecución** | Hoy no queda registrado, de forma uniforme y consultable, el prompt final, el agente y el archivo `.agent.md` usados en cada run. Imposible auditar errores post-mortem en el runtime estándar. | Backend (models + runner + api), Frontend (panel de ejecución) |
| F2 | **Deploy canónico de agentes** | Garantizar que el deploy copie SIEMPRE `backend/Stacky/agents` y que esos archivos jamás se muten (ni por el build, ni por el runtime). Mantener un stack idéntico entre publicaciones. | Deployment (ps1 + check), Backend (runtime_paths + stacky_agents) |
| F3 | **Sugerencia técnico/developer** | En la vista ADO, tickets de fase técnica se sugieren como `developer` porque el mapeo es por `ado_state` plano y "Active" → developer tapa la señal real. | Frontend (resolver) + Backend (endpoint de sugerencia opcional) |

---

## 1. Estado actual del sistema (grounding)

Verificado en código antes de escribir este plan:

### 1.1 Trazabilidad (F1)
- `models.py:206` `AgentExecution` persiste: `agent_type`, `input_context_json`
  (bloques de contexto, **no** el prompt final), `metadata_json`, `output`,
  `contract_result_json`, `error_message`, `html_output_path`, `completion_source`.
- `agent_runner.py:703-719` (runtime `github_copilot`): al completar, vuelca
  `metadata_dict` con `duration_ms`, `confidence`, `routing_reason`, y agrega
  `agent_filename` **solo si el objeto agente lo expone**. **El prompt final
  ensamblado por `agent.run()` no se persiste en ningún lado.**
- `codex_cli_runner.py:312-320` construye el prompt y lo escribe en
  `run_dir/prompt.md`, guarda `prompt_file` en `metadata_dict` (línea ~426) y lo
  agrega como artifact. Es decir: los runtimes CLI ya persisten el prompt a disco,
  pero el runtime estándar no, y no hay un contrato uniforme.
- Conclusión: la información está **dispersa, parcial y dependiente del runtime**.

### 1.2 Deploy canónico (F2)
- `deployment/build_release.ps1:191-205` `Resolve-StackyAgentsSource` → fuente
  AUTORIZADA única: `backend\Stacky\agents`. Las flags `-GitHubCopilotAgentsRepo`
  están obsoletas y se ignoran (línea 372).
- `build_release.ps1:255-332` `Copy-StackyAgents` lee la fuente con `Copy-Item`
  (source→target), genera `manifest.json` con checksum por agente. La fuente
  **solo se lee**.
- `check_deploy_agents.py:34-95` valida que el manifest del deploy sea consistente
  consigo mismo (checksum manifest vs disco del deploy). **No** compara contra la
  fuente `backend/Stacky/agents`.
- `services/stacky_agents.py:175-183` `list_external_sources()` ya devuelve `[]`:
  el runtime no materializa desde fuentes externas por defecto.
- **Gaps detectados:**
  - G2.1 — Coexisten `backend/agents/` (módulos `.py` + un `Developer.agent.md`)
    y `backend/Stacky/agents/`. Riesgo de divergencia/confusión sobre cuál es la
    fuente de verdad.
  - G2.2 — En runtime el dir canónico (`stacky_agents_dir()`) es **escribible**:
    `stacky_agents.py:281` `materialize_agents(force=True)` e
    `import_agent_from_path()` pueden mutar los `.agent.md` del deploy → drift
    respecto del stack publicado.
  - G2.3 — No existe gate que verifique que el deploy es copia **byte-a-byte** de
    la fuente (`check_deploy_agents.py` no recibe el source root).
  - G2.4 — `Copy-StackyAgents` usa `-Recurse` y renombra colisiones; puede
    arrastrar `.agent.md` de subcarpetas no previstas.

### 1.3 Sugerencia técnico/developer (F3)
- `frontend/src/utils/resolveSuggestedAgent.ts:55-65`, orden de resolución:
  1. **FlowConfig por `ado_state`** (máxima prioridad).
  2. `pipeline_summary.next_suggested` (inferencia LLM del backend).
  3. `TYPE_FALLBACK` por `work_item_type` (`feature→technical`, `task→developer`).
- `flow_config_store.py:57-62` reglas semilla: `New→business`, **`Active→developer`**,
  `Code Review→qa`, `Resolved→qa`. **No hay regla para `technical`.**
- `ado_pipeline_inference.py:240-272`: el LLM SÍ distingue `technical` vs
  `developer` leyendo evidencia de comentarios/descripción, y expone
  `next_suggested`. Pero esa señal queda **tapada** por el mapa plano de estado.
- **Causa raíz:** en ADO Agile/Scrum la fase técnica y la fase de desarrollo
  comparten el estado `Active`. Mapear `Active→developer` hace que **todo** ticket
  Active se sugiera developer, incluso Features en análisis técnico. La señal
  precisa (inferencia / tipo) está disponible pero subordinada al mapa coarse.

---

# FEATURE 1 — Trazabilidad de ejecución (prompt + agente + archivo)

## F1.1 Identidad

| Campo | Valor |
|---|---|
| Nombre | Execution Trace — prompt/agent/file persistido por ejecución |
| Objetivo | Que cada `AgentExecution`, en **todos** los runtimes, registre de forma uniforme y consultable: (a) el prompt final enviado al modelo, (b) el `agent_type`, (c) el archivo `.agent.md` usado (ruta + checksum), para analizar errores de ejecución post-mortem. |
| Alcance | `models.py` (3 columnas nuevas), `agent_runner.py` (runtime estándar), `codex_cli_runner.py` / `claude_code_cli_runner.py` (homogeneizar), `api/executions.py` (exponer en `to_dict`), frontend `OutputPanel`/`AgentHistory` (mostrar trace). |
| Fuera de scope | Versionado histórico del prompt (solo se guarda el del último run). Diff visual entre prompts de runs distintos (futuro). Re-ejecución desde el trace. Almacenar el prompt de sub-llamadas LLM internas (router, contract validator). |

## F1.2 Contrato de datos

Nuevas columnas en `agent_executions` (todas nullable para compatibilidad hacia atrás):

| Columna | Tipo | Descripción |
|---|---|---|
| `prompt_text` | `Text` (nullable) | Prompt final efectivamente enviado al modelo (system + user concatenados o el bloque exacto que recibe el runner CLI). PII enmascarada (ver Invariante F1-I3). |
| `agent_file_path` | `String(500)` (nullable) | Ruta absoluta del `.agent.md` usado (resuelto vía `stacky_agents`/`AgentEntry.path`). |
| `agent_file_checksum` | `String(64)` (nullable) | `sha256` del `.agent.md` usado (de `AgentEntry.checksum_sha256`). Permite detectar qué versión del agente produjo el resultado. |

`agent_type` ya existe (no se duplica). El prompt grande va a columna propia (no a
`metadata_json`) para no inflar la metadata y permitir índices/consultas futuras.

**Migración:** `ALTER TABLE agent_executions ADD COLUMN ...` × 3. Idempotente
(patrón de migraciones existente; ver `db.py`). Sin backfill: ejecuciones previas
quedan con `NULL` (documentado).

## F1.3 Criterios de aceptación

### CA-F1-01 — Runtime estándar persiste el prompt final
**DADO** un ticket y el runtime `github_copilot`
**CUANDO** se ejecuta `run_agent(...)` y `agent.run()` arma el prompt
**ENTONCES**:
- El prompt final (lo que el agente envía al modelo) se persiste en
  `AgentExecution.prompt_text`.
- `agent_file_path` y `agent_file_checksum` se llenan desde el `AgentEntry`
  resuelto para `agent_type`.
- El prompt persistido tiene la PII **enmascarada** (consistente con
  `pii_masker`, igual que `metadata`).
- **Mapea a:** TU-F1-01

### CA-F1-02 — Runtimes CLI homogeneizan el trace
**DADO** el runtime `codex_cli` (y `claude_code_cli`)
**CUANDO** el runner escribe `prompt.md` y arranca el proceso
**ENTONCES**:
- El mismo prompt que hoy va a `run_dir/prompt.md` se persiste también en
  `AgentExecution.prompt_text`.
- `agent_file_path` = ruta del `.agent.md` seleccionado; `agent_file_checksum` =
  su sha256.
- `metadata.prompt_file` se preserva (no se rompe el comportamiento actual).
- **Mapea a:** TU-F1-02

### CA-F1-03 — El trace se expone por API
**DADO** una ejecución completada con trace
**CUANDO** `GET /api/executions/{id}` la devuelve
**ENTONCES**:
- El payload incluye `prompt_text`, `agent_file_path`, `agent_file_checksum` y
  `agent_type`.
- Para ejecuciones previas a esta feature, esos campos son `null` (no error).
- El prompt se devuelve completo solo en el detalle por id; el listado
  (`GET /api/executions`) **no** incluye `prompt_text` (evitar payloads enormes).
- **Mapea a:** TU-F1-03

### CA-F1-04 — El operador ve el trace en la UI
**DADO** una ejecución con trace en el `OutputPanel`/`AgentHistory`
**CUANDO** el operador abre el detalle
**ENTONCES**:
- Hay una sección colapsable "Trace de ejecución" que muestra: `agent_type`,
  nombre y ruta del `.agent.md`, checksum (corto) y el prompt final (monospace,
  copiable).
- Si `prompt_text` es `null`, la sección muestra "no registrado" sin romper el
  render.
- **Mapea a:** TU-F1-04

### CA-F1-05 — Trace presente incluso en ejecución con error
**DADO** una ejecución que falla en `agent.run()`
**CUANDO** se marca `status="error"`
**ENTONCES**:
- `prompt_text` (si ya se había ensamblado), `agent_file_path` y
  `agent_file_checksum` quedan persistidos junto al `error_message`.
- Esto es el objetivo central: poder analizar el error con el prompt exacto que
  lo causó.
- **Mapea a:** TU-F1-05

## F1.4 Invariantes

- **F1-I1 (uniformidad):** los tres campos se llenan igual en todos los runtimes;
  el consumidor (API/UI) no necesita saber el runtime.
- **F1-I2 (no romper cache):** un hit de `output_cache` NO regenera prompt; en ese
  caso `prompt_text` puede quedar `null` o marcarse `from_cache` (documentado). El
  trace aplica a ejecuciones reales, no a respuestas cacheadas.
- **F1-I3 (PII):** `prompt_text` se guarda enmascarado. Nunca se persiste PII en
  claro (consistente con FA-37 / `pii_masker`).
- **F1-I4 (tamaño):** si el prompt supera `STACKY_MAX_PROMPT_PERSIST_CHARS`
  (default 200k), se trunca con marcador `…[truncado N chars]` y se registra el
  tamaño original en `metadata`.

## F1.5 Plan de tests

| ID | Descripción | Tipo |
|---|---|---|
| TU-F1-01 | `run_agent` estándar persiste `prompt_text` enmascarado + path + checksum | pytest (mock `agent.run`) |
| TU-F1-02 | `codex_cli_runner` persiste el mismo prompt que `prompt.md` en `prompt_text` | pytest |
| TU-F1-03a | `GET /api/executions/{id}` incluye los 3 campos | pytest API |
| TU-F1-03b | `GET /api/executions` (lista) NO incluye `prompt_text` | pytest API |
| TU-F1-04 | `OutputPanel` renderiza la sección Trace y maneja `null` | Vitest |
| TU-F1-05 | Ejecución con excepción persiste prompt+agent+file junto al error | pytest |
| TU-F1-06 | Migración idempotente: correr dos veces no falla; ejecuciones viejas quedan `null` | pytest |
| TU-F1-07 | Prompt > límite se trunca con marcador y registra tamaño original | pytest |

---

# FEATURE 2 — Deploy canónico de agentes (fuente intocable)

## F2.1 Identidad

| Campo | Valor |
|---|---|
| Nombre | Canonical Agents Deploy — fuente única `backend/Stacky/agents`, intocable |
| Objetivo | Garantizar que el deploy siempre se materialice desde `backend/Stacky/agents`, que esos archivos NUNCA se muten (ni por el build ni por el runtime), y agregar un gate que verifique que el deploy es copia fiel de la fuente — para mantener un stack idéntico entre publicaciones. |
| Alcance | `deployment/build_release.ps1`, `deployment/check_deploy_agents.py` (modo drift), `runtime_paths.py` / `services/stacky_agents.py` (canonical read-only en runtime), test de release. |
| Fuera de scope | Cambiar el formato del `.agent.md` o del manifest. Soporte multi-fuente. Firmar individualmente cada `.agent.md`. Migrar `backend/agents/*.py` (lógica de agentes Python) — eso queda donde está. |

## F2.2 Decisiones de diseño

- **DD-2.1 — Fuente de verdad única:** `backend/Stacky/agents/*.agent.md`. Es la
  ÚNICA fuente autorizada (ya lo es en `build_release.ps1`). Este plan lo blinda
  con tests y guard.
- **DD-2.2 — Lectura sin escritura:** el build copia source→deploy con `Copy-Item`
  y nunca escribe en el source (ya se cumple; se agrega aserción explícita).
- **DD-2.3 — Runtime read-only del canonical bundled:** en deploy congelado
  (`is_frozen()`), `materialize_agents(force=True)` e `import_agent_from_path()`
  quedan **bloqueados por defecto** para los agentes con `source="bundled"`. Los
  agentes importados por el operador (`source="imported"/"custom"`) siguen
  permitidos pero en un subdir separado, sin pisar bundled.
- **DD-2.4 — Gate de drift:** `check_deploy_agents.py` acepta `--source-root` y
  compara checksum source vs deploy; el release falla si difieren.
- **DD-2.5 — `backend/agents/Developer.agent.md`:** se documenta como artefacto
  legacy NO usado por el deploy. Si está duplicado respecto del canonical, un test
  lo marca para evitar confusión (G2.1).

## F2.3 Criterios de aceptación

### CA-F2-01 — El build materializa solo desde la fuente autorizada
**DADO** `backend/Stacky/agents` con N `.agent.md`
**CUANDO** corre `build_release.ps1`
**ENTONCES**:
- `<release>/Stacky/agents` contiene exactamente esos N agentes (mismos nombres).
- El `manifest.json` declara `source="bundled"` para todos.
- Ningún `.agent.md` proviene de GitHub Copilot/VS Code ni de bundles legacy.
- **Mapea a:** TU-F2-01

### CA-F2-02 — La fuente nunca se modifica durante el build
**DADO** los checksums de `backend/Stacky/agents/*.agent.md` antes del build
**CUANDO** termina `build_release.ps1`
**ENTONCES**:
- Los checksums de la fuente son **idénticos** a los de antes (mtime y contenido).
- **Mapea a:** TU-F2-02

### CA-F2-03 — Gate de drift source↔deploy
**DADO** un `<release>/Stacky/agents` materializado
**CUANDO** corre `check_deploy_agents.py --source-root backend/Stacky/agents --deploy-root <release>`
**ENTONCES**:
- Si todo `.agent.md` del deploy tiene checksum idéntico al de la fuente y no hay
  faltantes ni sobrantes → exit 0.
- Si un archivo difiere, falta o sobra → exit 1 con el detalle por archivo.
- El build invoca este modo y **cancela el release** ante drift.
- **Mapea a:** TU-F2-03

### CA-F2-04 — Runtime congelado no muta agentes bundled
**DADO** un deploy congelado (`is_frozen()==True`)
**CUANDO** se invoca `materialize_agents(force=True)` o `import_agent_from_path()`
sobre un agente con `source="bundled"`
**ENTONCES**:
- La operación es **no-op bloqueante** sobre el archivo bundled (no lo reescribe)
  y se loguea `warn` con la razón.
- El checksum del `.agent.md` bundled en disco queda intacto.
- **Mapea a:** TU-F2-04

### CA-F2-05 — Importación de agente custom no pisa bundled
**DADO** un deploy congelado y un agente custom importado por el operador
**CUANDO** se importa un `.agent.md` con nombre que colisiona con uno bundled
**ENTONCES**:
- El import se rechaza o se materializa con `source="custom"` sin sobreescribir el
  bundled (decisión: rechazar con error claro `BUNDLED_AGENT_PROTECTED`).
- **Mapea a:** TU-F2-05

### CA-F2-06 — Detección de duplicado legacy
**DADO** `backend/agents/Developer.agent.md` y `backend/Stacky/agents/Developer.agent.md`
**CUANDO** corre el test de consistencia de fuentes
**ENTONCES**:
- El test reporta si ambos existen y difieren, recordando que el canonical es
  `backend/Stacky/agents` (no bloquea el build; es un guard informativo/CI).
- **Mapea a:** TU-F2-06

## F2.4 Invariantes

- **F2-I1:** `backend/Stacky/agents` es la única fuente. El build jamás escribe en
  ella.
- **F2-I2:** el deploy es una copia byte-a-byte verificada por checksum.
- **F2-I3:** en runtime congelado, los agentes `bundled` son inmutables.
- **F2-I4:** el manifest del deploy y el del runtime usan el mismo algoritmo de
  checksum (`sha256(read_bytes())`, ya unificado en `stacky_agents._sha256_file`).

## F2.5 Plan de tests

| ID | Descripción | Tipo |
|---|---|---|
| TU-F2-01 | `Copy-StackyAgents` copia exactamente los N de la fuente con `source=bundled` | pytest (invoca ps o función equivalente) / test de release |
| TU-F2-02 | Checksums de la fuente intactos pre/post build | pytest |
| TU-F2-03 | `check_deploy_agents.py --source-root` detecta diff/faltante/sobrante (exit 1) y OK (exit 0) | pytest |
| TU-F2-04 | `materialize_agents(force=True)` no muta bundled en frozen | pytest (mock `is_frozen`) |
| TU-F2-05 | `import_agent_from_path` rechaza colisión con bundled → `BUNDLED_AGENT_PROTECTED` | pytest |
| TU-F2-06 | Test de consistencia `backend/agents` vs `backend/Stacky/agents` (informativo) | pytest |

---

# FEATURE 3 — Sugerencia precisa técnico vs developer

## F3.1 Identidad

| Campo | Valor |
|---|---|
| Nombre | Accurate Suggested Agent — desambiguar technical/developer en la vista ADO |
| Objetivo | Que el botón "Run Sugerido" proponga `technical` cuando corresponde a la fase técnica, en lugar de caer siempre en `developer` por el mapeo plano `Active→developer`. Hacer la detección multi-señal y explicable. |
| Alcance | `frontend/src/utils/resolveSuggestedAgent.ts` (reordenar/combinar señales), opcional backend `services/` para una resolución única servidora + `metadata` de "razón". Tests Vitest. |
| Fuera de scope | Cambiar el pipeline de inferencia LLM (`ado_pipeline_inference.py`). Reemplazar FlowConfig (se mantiene como override explícito del operador). Aprendizaje automático de transiciones. |

## F3.2 Decisiones de diseño

- **DD-3.1 — FlowConfig sigue siendo override explícito, pero deja de ser un mapa
  plano que tapa todo.** Se vuelve **type-aware**: una regla puede (opcionalmente)
  matchear por `(work_item_type, ado_state)` además de `ado_state` solo. Las reglas
  existentes (solo `ado_state`) siguen funcionando como fallback genérico.
- **DD-3.2 — Reordenar la resolución para no subordinar la señal precisa.** Nuevo
  orden:
  1. **FlowConfig específica** `(work_item_type + ado_state)` — máxima prioridad.
  2. **`pipeline_summary.next_suggested`** (evidencia real; distingue technical de
     developer) — **antes** del mapa plano.
  3. **FlowConfig genérica** `(ado_state)` — el mapa plano actual, ahora como
     desempate, no como autoridad.
  4. **`TYPE_FALLBACK`** por `work_item_type`.
- **DD-3.3 — Regla anti-degradación:** si la FlowConfig genérica dice `developer`
  pero el `work_item_type` es `feature`/`epic` (que típicamente requieren análisis
  técnico antes de codear) y el pipeline indica que `technical` aún no está hecho,
  se prefiere `technical`. Esto ataca exactamente el síntoma reportado.
- **DD-3.4 — Explicabilidad:** el resolver devuelve `{ agentType, reason, source }`
  para que el modal "Run Sugerido" muestre por qué (ej. "fase técnica pendiente
  según comentarios ADO"). Reduce la sorpresa del operador.
- **DD-3.5 — Sembrar regla técnica faltante:** agregar al seed de FlowConfig una
  entrada para el estado técnico real del cliente (configurable; ej.
  `"Technical review"→technical` / `"Análisis Técnico"→technical`). No se asume un
  único string: se documenta como configurable.

## F3.3 Contrato del resolver (nuevo)

```typescript
export interface SuggestedAgentResult {
  agentType: string | null;
  reason: string;                 // explicación legible para la UI
  source: "flow_specific" | "pipeline" | "flow_generic" | "type_fallback" | "none";
}

export function resolveSuggestedAgent(input: {
  workItemType?: string | null;
  adoState?: string | null;
  flowConfigMap: Map<string, string>;            // genérica: ado_state → agent
  flowConfigSpecificMap?: Map<string, string>;   // "type|state" → agent (opcional)
  pipelineNext?: string | null;
  pipelineStages?: Record<string, { done: boolean }> | null; // para DD-3.3
}): SuggestedAgentResult;
```

`resolveSuggestedAgent` mantiene retrocompatibilidad: si se llama sin los campos
nuevos, se comporta como hoy salvo por el reordenamiento (pipeline antes que mapa
genérico) y la regla anti-degradación.

## F3.4 Criterios de aceptación

### CA-F3-01 — Feature en "Active" con técnico pendiente → technical
**DADO** un ticket `work_item_type="Feature"`, `ado_state="Active"`, sin regla
específica, con `pipeline.stages.technical.done=false`
**CUANDO** se resuelve la sugerencia
**ENTONCES**:
- El resultado es `technical` (no `developer`).
- `source` ∈ {`pipeline`, `flow_specific`} y `reason` explica la fase técnica
  pendiente.
- **Mapea a:** TU-F3-01

### CA-F3-02 — Task en "Active" con técnico hecho → developer
**DADO** un ticket `work_item_type="Task"`, `ado_state="Active"`,
`pipeline.stages.technical.done=true`
**CUANDO** se resuelve la sugerencia
**ENTONCES**:
- El resultado es `developer`.
- **Mapea a:** TU-F3-02

### CA-F3-03 — FlowConfig específica tiene prioridad
**DADO** una regla específica `Feature|Active → technical` y una genérica
`Active → developer`
**CUANDO** el ticket es `Feature` en `Active`
**ENTONCES**:
- Gana la específica → `technical`, `source="flow_specific"`.
- **Mapea a:** TU-F3-03

### CA-F3-04 — Retrocompatibilidad
**DADO** el sistema actual sin reglas específicas ni pipeline disponible
**CUANDO** se resuelve un ticket en un estado mapeado en la genérica
**ENTONCES**:
- El resultado coincide con el mapa genérico (no se rompe lo existente), salvo el
  caso explícito de DD-3.3.
- Tasks/Épicas siguen sin proponer `business`.
- **Mapea a:** TU-F3-04

### CA-F3-05 — Explicabilidad en la UI
**DADO** una sugerencia resuelta por `pipeline`
**CUANDO** el operador abre el modal "Run Sugerido"
**ENTONCES**:
- El modal muestra el `reason` (ej. "Sugerido técnico: análisis técnico pendiente
  según evidencia ADO").
- **Mapea a:** TU-F3-05

### CA-F3-06 — Seed de regla técnica
**DADO** un proyecto nuevo sin `flow_config.json`
**CUANDO** se siembran las defaults
**ENTONCES**:
- El seed incluye una regla para el estado técnico configurado del cliente que
  mapea a `technical` (configurable; documentado).
- **Mapea a:** TU-F3-06

## F3.5 Invariantes

- **F3-I1:** la FlowConfig del operador, cuando es específica, siempre gana
  (control humano explícito).
- **F3-I2:** sin señales nuevas, el comportamiento no regresiona (salvo la mejora
  de DD-3.3).
- **F3-I3:** el resolver es la **única** fuente de la lógica de sugerencia (no se
  re-duplica entre `TicketBoard.tsx` y `TicketGraphView.jsx`).

## F3.6 Plan de tests

| ID | Descripción | Tipo |
|---|---|---|
| TU-F3-01 | Feature/Active + technical pendiente → technical | Vitest |
| TU-F3-02 | Task/Active + technical hecho → developer | Vitest |
| TU-F3-03 | FlowConfig específica gana a la genérica | Vitest |
| TU-F3-04 | Retrocompat: estado mapeado sin señales nuevas = comportamiento actual | Vitest |
| TU-F3-05 | El resultado expone `reason`/`source` y el modal lo renderiza | Vitest |
| TU-F3-06 | Seed incluye regla técnica configurable | pytest (`flow_config_store`) |
| TU-F3-07 | `TicketGraphView` y `TicketBoard` usan el mismo resolver (sin lógica duplicada) | Vitest/grep test |

---

## 4. Secuencia de implementación recomendada

1. **F3** (frontend-céntrico, bajo riesgo, alto impacto percibido). Entrega
   independiente.
2. **F1** (backend + migración + UI). Entrega independiente.
3. **F2** (deployment + runtime guard + gate). Entrega independiente; requiere
   validar un build real.

Cada feature se mergea por separado con sus TU en verde. No hay dependencias
cruzadas de datos entre features.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| F1: `prompt_text` infla la DB | Columna `Text` aparte; truncado por `STACKY_MAX_PROMPT_PERSIST_CHARS`; no se incluye en listados. |
| F1: PII en prompt persistido | Enmascarar antes de persistir (F1-I3). |
| F2: bloquear runtime rompe import legítimo de custom | Solo se bloquea sobre `source="bundled"`; custom/imported siguen permitidos en subdir separado. |
| F2: gate de drift falla por line endings/BOM | Usar el mismo `sha256(read_bytes())` ya unificado; el build escribe UTF-8 sin BOM. |
| F3: el estado técnico varía por cliente | Hacerlo configurable (DD-3.5), no hardcodear un único string. |
| F3: reordenar cambia sugerencias existentes | CA-F3-04 fija la retrocompat; la única desviación intencional es DD-3.3, cubierta por TU. |

## 6. Métricas observables

| Métrica | Cómo se mide |
|---|---|
| `executions_with_trace_pct` (F1) | % de `agent_executions` con `prompt_text` no nulo desde el deploy de la feature |
| `deploy_drift_blocks` (F2) | Conteo de releases cancelados por `check_deploy_agents` en modo drift |
| `suggestion_overrides` (F3) | % de runs donde el operador cambió de "sugerido" a "personalizado" (proxy de precisión; debería bajar) |
| `technical_suggestions_count` (F3) | Conteo de sugerencias `technical` antes/después (debería subir para Features en Active) |

---

*Fin de SPEC-trazabilidad-deploy-sugerencia v1.0.0*
