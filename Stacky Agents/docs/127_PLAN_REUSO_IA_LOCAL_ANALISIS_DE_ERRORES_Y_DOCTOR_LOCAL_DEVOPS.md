# Plan 127 — Reuso de la IA local: análisis de errores de ejecuciones y doctor local DevOps

**Estado:** IMPLEMENTADO (F0..F7 completas, 2026-07-14, rama `plan-127-ia-local-doctor`, HEAD `d2bbf4d2`; ver §7 DoD)
**Dependencias duras:** Plan 106 (`invoke_local_llm`, ya implementado, commit 344f3124), Plan 110 (`services/pr_review_sanitize.py`, ya implementado, commit bb4e8373)
**Superficies que EXTIENDE (sin romper):** Plan 104 (doctor de sección DevOps), Plan 96 (doctor de pipelines), Plan 117 (insights locales — solo se agregan literales a su lista de exclusión)
**Ortogonal a:** Plan 121 (centinela de egreso — ver §6), Plan 120 (Centro de Despliegues), serie 122-126 (DB compare)

> **NOTA DE NUMERACIÓN (H4, RESUELTA):** hubo una colisión: el tablero de evolución
> de planes también nació como "127" (commit 42061170). Ya fue renumerado a
> `128_PLAN_TABLERO_EVOLUCION_PLANES.md` por su sesión (commit d0864ceb). ESTE
> documento conserva el 127 (propuesto con ese número en e922b78f). No queda nada
> pendiente por este punto.

## CHANGELOG v1 → v2 (crítica adversarial 2026-07-12)

- **DIRECTIVA DEL OPERADOR (H1):** las 2 flags nuevas pasan de opt-in default OFF a
  **DEFAULT ON** (pedido textual "HACELO DEFAULT ON", 2026-07-12; precedente: flags
  DevOps 93-108 promovidas el 2026-07-09, master del Plan 110 default ON). Reescritos
  coherentes: KPI-1, KPI-6, §1 "Trabajo del operador", §3.2, §3.6, F0 completo,
  gates y tests de F3/F5/F6/F7, riesgos y DoD.
- **H2:** §3.6 invertido al patrón triple EXACTO de flag curada default ON, verificado
  en código: FlagSpec `default=True` explícito + key en `_CURATED_DEFAULTS_ON` +
  `config.py` default `"true"`. El patrón v1 ("SIN default=") ahora está PROHIBIDO
  para estas flags.
- **H3:** sección nueva §3.11 sobre `harness_defaults.env`: NO se regenera, con
  justificación y test negativo; prohibido el assert legacy `KEY=false` (patrón del
  drift rojo conocido, `test_plan96_doctor_flag.py:53-59`).
- **H4:** nota de colisión de numeración en el encabezado (arriba).
- **H5:** `local_doctor_enabled` del health pasa a ser la CONJUNCIÓN
  `flag AND LOCAL_LLM_ENABLED` para que la UI nunca muestre un botón que muere en 404.
- **H6:** KPI-6 y no-regresión redefinidos para el mundo default ON (el único delta
  observable con ON es la key nueva del health); no-regresión ampliada con
  `test_plan87_devops_flag.py` y fallback explícito del `-k bootstrap_health`.
- **H7:** decisión explícita sobre ejecuciones colgadas en `running`: NO analizables
  (409), con test; el post-mortem es solo para runs terminados.
- **H8:** F5 deja de usar `blocks[0]["content"]`: concatena TODOS los bloques.
- **H9:** parseo del body literal (`request.get_json(silent=True) or {}`).
- **H10:** hints 404 del frontend reescritos para el mundo default ON.
- **H11:** claims archivo:línea corregidos tras re-verificación: `diag.py:44` (era 43),
  `devops.py:28` (era 38), `SECTION_DOCTORS` en `devops_section_doctor.py:32` (era 27),
  gates cloud en `devops_section_doctor.py:68-71` (era 70-72).
- **[ADICIÓN ARQUITECTO]:** observabilidad de latencia del modelo local: `elapsed_ms`
  + `model` persistidos y mostrados en UI (mitiga R1 con costo ~0; ver F3 paso 9,
  F5 paso 8 y F6).

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Toda afirmación sobre código existente
> cita `archivo:línea` verificada el 2026-07-12 sobre `main` (HEAD 4a67e2c2;
> re-verificación puntual en la crítica v2 del mismo día).
> Prohibido desviarse de los nombres exactos. Prohibido "etc." y "según corresponda":
> si algo no está escrito acá, NO se hace.

---

## 1. Título, objetivo y KPIs

### Objetivo

La IA local (Ollama/Qwen, Plan 106) ya está integrada, encendida por default
(`LOCAL_LLM_ENABLED` default `true`, `config.py:81-83`) y probada en 3 consumidores
(análisis de código, sugerencia de pipeline, revisor de PRs local). Este plan la
**reusa** en los dos puntos de mayor ROI detectados en la auditoría 2026-07-12,
sin duplicar una línea de infraestructura:

- **C1 — Análisis IA local de errores de ejecuciones (prioridad 1):** botón HITL
  en el detalle de una ejecución fallida que manda el snapshot forense determinista
  de `api/diag.py` + el error + la cola del output al modelo LOCAL y devuelve causa
  raíz probable + próximos pasos, persistido en `metadata_json["error_analysis"]`.
  Hoy el operador diagnostica a mano leyendo varios endpoints y logs.
- **C3 — Doctor local DevOps por sección (prioridad 2):** alternativa GRATIS y
  SIN egreso al doctor Copilot/CLI del Plan 104: mismo contexto por sección
  (pipeline/environments/publications), respuesta síncrona en markdown del modelo
  local. No exige `STACKY_DEVOPS_AGENT_ENABLED` ni runtime CLI.
- **C2 — Explicar fallo de CI con IA local (secundario, fase final F7, DIFERIBLE):**
  botón por job fallido en el doctor de pipelines (Plan 96) que baja el log,
  lo sanea/trunca y pide al modelo local causa raíz + fix sugerido.

*(Nomenclatura: C1/C2/C3 nombran CAPACIDADES del plan; los hallazgos de la crítica
v2 usan prefijo H# para no colisionar.)*

### KPIs (binarios, cada uno con su test)

- **KPI-1 (C1 funciona):** con los defaults de código (sin env vars:
  `LOCAL_LLM_ENABLED=true` y `STACKY_EXEC_ERROR_ANALYSIS_ENABLED=true`) e
  `invoke_local_llm` mockeado, `POST /api/llm/executions/<id>/error-analysis` sobre una
  ejecución con `status="error"` devuelve 200 y deja `metadata_json["error_analysis"]["analysis"]`
  no vacío en la ejecución analizada. Con la flag APAGADA A MANO devuelve 404. (F3)
- **KPI-2 (cero regresión forense):** `GET /api/diag/execution/<id>` devuelve exactamente
  el mismo JSON antes y después del refactor F1 (`tests/test_diag_endpoint.py` verde sin tocar).
- **KPI-3 (C3 funciona sin agente DevOps):** con `STACKY_DEVOPS_AGENT_ENABLED=false`,
  `POST /api/devops/sections/pipeline/doctor/local` devuelve 200 con markdown (bridge
  mockeado). El doctor cloud del Plan 104 exige esa flag (`devops_section_doctor.py:68-71`);
  el local NO. (F5)
- **KPI-4 (cero regresión doctor cloud):** `tests/test_plan104_section_doctor.py` verde
  sin modificar después de F4/F5.
- **KPI-5 (ningún secreto viaja ni persiste en claro):** un `error_message` o payload con
  `password=hunter2` plantado produce prompts y análisis persistidos donde ese valor
  aparece SOLO enmascarado (`redact_secrets`, `pr_review_sanitize.py:27`). (F2/F3/F5)
- **KPI-6 (default ON sin regresión — reescrito v2, H1/H6):** con las 2 flags nuevas
  en su DEFAULT ON, ningún test existente cambia de resultado y ningún flujo existente
  cambia de comportamiento: nada del sistema actual llama a los endpoints nuevos, y el
  ÚNICO delta observable es la key nueva `local_doctor_enabled` en
  `GET /api/devops/health` (cubierta por la no-regresión de F5). Con las flags
  APAGADAS A MANO (UI del arnés o env var), los endpoints nuevos devuelven 404 y el
  sistema es byte-idéntico a hoy.

**Trabajo del operador: ninguno.** Ambas flags nuevas son **DEFAULT ON por directiva
explícita del operador (2026-07-12**, precedente 93-108/110): no hay que prender nada.
Siguen siendo apagables desde el HarnessFlagsPanel (UI), como manda la regla de la
casa. Encendidas (default), todo es a un click (HITL); apagadas a mano, el sistema es
byte-idéntico a hoy.

---

## 2. Por qué ahora / gap que cierra

| Hecho verificado | Evidencia (archivo:línea) |
|---|---|
| `invoke_local_llm(*, agent_type, system, user, on_log, execution_id=None, model=None) -> BridgeResponse` va SIEMPRE al endpoint local, sin mirar `LLM_BACKEND`, sin tool use | `backend/copilot_bridge.py:190-204` |
| `LOCAL_LLM_ENABLED` default `true` con tupla truthy `("true", "1", "yes")`; endpoint default Ollama; modelo default `qwen3:32b`; timeout 120s | `backend/config.py:81-88` |
| Blueprint local ya montado en `/api/llm` con guard canónico `_guard()` (404 flag OFF / 503 endpoint vacío / 400 POST sin JSON) | `backend/api/local_llm_analysis.py:24,44-52` |
| Patrón completo de ejecución interna auditada: ticket ancla `ado_id=-5` + `external_id=-ticket.id` + `AgentExecution` + `_finish_execution` | `backend/api/local_llm_analysis.py:28,55-112` |
| Patrón de flag hija chequeada en runtime (404 propio tras `_guard()`): route de insights del Plan 117 | `backend/api/local_llm_analysis.py:404-427` |
| Snapshot forense determinista de una ejecución YA existe: execution+ticket+manifest+heartbeat+recovery_history+diagnosis+recommended_action+thresholds — pero es solo lectura humana, nadie lo analiza | `backend/api/diag.py:44-127` |
| Doctor de sección DevOps existe SOLO vía `agent_runner.run_agent` (runtimes cloud/CLI): exige `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` Y `STACKY_DEVOPS_AGENT_ENABLED` (`:68-71`), crea conversación con ticket ancla `ado_id=-3` | `backend/api/devops_section_doctor.py:66-176` |
| Las instrucciones por sección son datos declarativos reutilizables (`SECTION_DOCTORS`) con HITL como primera línea | `backend/api/devops_section_doctor.py:32-62` |
| Doctor de pipelines (Plan 96) baja logs de jobs fallidos y clasifica con regex determinista; el log NO se persiste; cap 10 jobs | `backend/api/devops.py:376-407` |
| Saneador reutilizable de secretos ya existe y está testeado (Plan 110) | `backend/services/pr_review_sanitize.py:27-49` |
| Anti-recursión de insights: `EXCLUDED_AGENT_TYPES` es un frozenset de literales; todo agent_type nuevo de IA local debe agregarse ahí | `backend/services/local_insights.py:17-23` |
| `truncate_middle(text, head, tail)` y `HITL_RULES` son puros e importables | `backend/services/local_insights.py:41-57` |
| Flags LOCAL_LLM viven en categoría `avanzado`; masters sin `requires`; hijas `requires="LOCAL_LLM_ENABLED"`; el master del 117 NO declara `requires` estático hacia LOCAL_LLM (R4 prohíbe cadenas) — la dependencia se chequea en runtime | `backend/services/harness_flags.py:256-263,2557-2598,2682` |
| Patrón EXACTO de flag curada default ON (tanda 93-108, precedente de esta directiva): FlagSpec con `default=True` explícito y descripción "Default ON (activado <fecha>, decisión explícita del operador)" | `backend/services/harness_flags.py:2120-2137` (PANEL), `:2139-2153` (PUBLICATIONS, hija con `requires` Y `default=True`) |
| Set curado que habilita defaults ON: `_CURATED_DEFAULTS_ON`; bloque de la tanda 93-108 con comentario de activación | `backend/tests/test_harness_flags.py:465,518-531` |
| Meta-tests que fuerzan el patrón triple: curada ⇒ `declared_default is True`; default conocido ⇔ curada (drift bidireccional "Extras"/"Faltantes") | `backend/tests/test_harness_flags.py:619-634` |
| `STACKY_DEVOPS_PANEL_ENABLED` (el `requires` de la flag devops nueva) es HOY default ON: config `"true"`, FlagSpec `default=True`, curada | `backend/config.py:940-941`, `harness_flags.py:2131`, `test_harness_flags.py:510` |
| `AgentExecution.metadata_dict` es property tolerante a JSON corrupto (`_json_loads(...) or {}`) con setter | `backend/models.py:260-265` |
| Health del panel DevOps centralizado en `_health_payload()`; bootstrap reusa el mismo dict (paridad automática) | `backend/api/devops.py:28-64,81` |
| Generador de `harness_defaults.env`: snapshotea SOLO keys del FLAG_REGISTRY desde el .env del deploy vivo; sin deploy vivo conserva el archivo versionado | `deployment/export_harness_defaults.py:1-19` |
| Frontend: grupo `LocalLlmApi` en `endpoints.ts:3595`; drawer de ejecución `ExecutionDetailDrawer.tsx` con bloque hermano `ExecutionInsightBlock.tsx` (Plan 117); botón doctor `SectionDoctorButton.tsx`; panel doctor CI `PipelineDoctorPanel.tsx`; modelo puro testeable `src/devops/doctorModel.ts` (+ test) | `frontend/src/api/endpoints.ts:3595`, `frontend/src/components/` |

**Gap:** Stacky ya paga el costo de tener un modelo local corriendo, pero lo usa en
3 puntos. Los dos flujos donde el operador MÁS tiempo pierde hoy — "¿por qué falló
este run?" y "¿está bien este pipeline/environment?" — o no tienen IA (diag) o la
tienen solo por el camino caro/externo (doctor Copilot/CLI). Todo el sustrato para
cerrarlo existe; este plan solo conecta piezas.

---

## 3. Principios y guardarraíles (codificados, no decorativos)

1. **Human-in-the-loop innegociable.** TODO es on-demand por click del operador.
   Cero sweeps nuevos, cero daemons nuevos, cero acciones automáticas. Los prompts
   llevan las reglas HITL (`local_insights.HITL_RULES`) y el resultado es SIEMPRE
   advisory en markdown: el operador decide. **Default ON no cambia esto:** ON solo
   hace VISIBLES los botones; nada corre sin click.
2. **Cero trabajo extra del operador.** 2 flags nuevas, ambas **DEFAULT ON por
   directiva explícita del operador (2026-07-12)**, apagables SOLO por UI
   (HarnessFlagsPanel). Sin pasos manuales nuevos, sin migraciones,
   backward-compatible: nada existente consume los endpoints nuevos, y apagadas a
   mano ⇒ byte-idéntico a hoy.
3. **Paridad de los 3 runtimes (declaración obligatoria).** La IA local es un
   servicio HTTP del BACKEND, ortogonal a los runtimes de ejecución: C1 analiza
   ejecuciones producidas por CUALQUIER runtime (Codex CLI, Claude Code CLI,
   GitHub Copilot Pro) porque lee `AgentExecution`, que es runtime-agnóstica;
   C3/C2 ni siquiera despachan a un runtime. **Degradación controlada:** con
   `LOCAL_LLM_ENABLED=false` o flag del plan apagada a mano ⇒ 404 (endpoints
   invisibles, UI muestra hint accionable); con Ollama caído ⇒ 502 con mensaje
   accionable (patrón `local_llm_analysis.py:252-254`) que la UI muestra en el
   estado error del bloque (F6). En ambos casos el sistema se comporta EXACTAMENTE
   como hoy: nada depende de estos endpoints.
4. **Mono-operador sin auth.** Nada de RBAC, roles ni multiusuario. `started_by`
   descriptivo, como en `local_llm_analysis.py:90`.
5. **Reusar, no reinventar.** Prohibido crear otro cliente HTTP LLM, otro saneador,
   otro patrón de ticket ancla u otro truncador. Se importan: `invoke_local_llm`
   (copilot_bridge), `redact_secrets` (pr_review_sanitize), `truncate_middle` +
   `HITL_RULES` (local_insights — funciones/constantes puras, import de solo lectura),
   `_guard`/`_ensure_internal_ticket`/`_create_execution`/`_finish_execution`
   (local_llm_analysis — precedente de import de helper entre blueprints:
   `devops_section_doctor.py:129` importa `_current_user` de `devops_agent`).
6. **Gotcha de flags — patrón triple default ON (REESCRITO v2, H2).** Con la
   directiva default ON, el patrón correcto es el de la tanda 93-108, y son TRES
   piezas OBLIGATORIAS Y SIMULTÁNEAS:
   1. **FlagSpec con `default=True` explícito** (patrón exacto:
      `harness_flags.py:2131` para un master, `:2151-2152` para una hija con
      `requires` Y `default=True` a la vez).
   2. **Key agregada a `_CURATED_DEFAULTS_ON`** en
      `backend/tests/test_harness_flags.py:465` (bloque nuevo al final del set, con
      comentario `# ── Activación operador 2026-07-12 — Plan 127 ... ──`, patrón del
      bloque `:518-531`).
   3. **`config.py` con default `"true"`** en el `os.getenv(...)`.
   Romper la simultaneidad rompe meta-tests en cualquier dirección:
   `default=True` sin curar ⇒ `test_default_known_only_for_curated` falla por
   "Extras" (`test_harness_flags.py:625-634`); curada sin `default=True` ⇒ falla por
   "Faltantes" y por `declared_default is True` (`:619-622`); config `"true"` sin
   FlagSpec `default=True` ⇒ gotcha runtime-vs-UI (la UI muestra OFF con el sistema
   ON — prohibido). El patrón v1 "SIN `default=`" queda PROHIBIDO para estas 2 flags.
   La flag devops declara `requires="STACKY_DEVOPS_PANEL_ENABLED"` (profundidad 1;
   el padre es HOY default ON — `config.py:940-941` — así que el `requires`
   declarativo informa en UI y no degrada nada) y exige alta de la arista en
   `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py`). La flag
   de C1 NO declara `requires` (precedente exacto: `harness_flags.py:2682`, Plan 117);
   la dependencia de LOCAL_LLM se chequea en runtime vía `_guard()`.
7. **Ratchet de tests.** Todo archivo de test backend nuevo se registra en
   `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh` Y su espejo
   `run_harness_tests.ps1`, en orden alfabético, o el meta-test del Plan 49 falla.
8. **Help de flags.** Toda key nueva del registry necesita entrada en
   `backend/services/harness_flags_help.py` (qué hace / cuándo apagarla, en
   castellano llano, campo `what` ≤ 200 caracteres, sin jerga) o
   `test_plain_help_covers_all_registry_keys` falla (KPI-7 del Plan 86).
9. **No tocar archivos con WIP ajeno vivo.** Al 2026-07-12 el working tree tiene
   modificaciones sin commitear de una sesión concurrente (entre otros
   `copilot_bridge.py`, `services/llm_router.py`, `config.py`, `harness/pricing.py`).
   Este plan NO modifica `copilot_bridge.py` ni `llm_router.py`. Los archivos
   compartidos que SÍ toca (`config.py`, `services/harness_flags.py`,
   `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`,
   `scripts/run_harness_tests.*`) exigen **staging quirúrgico por hunk** al
   commitear (precedente Plan 110/111); PROHIBIDO `git stash`, `git reset`,
   `git checkout --`, `git add -A`.
10. **No degradar.** Los refactors F1 y F4 son extractivos (misma lógica, misma
    respuesta); su criterio de aceptación es que los tests EXISTENTES pasen sin
    modificarse.
11. **`harness_defaults.env` — NO se regenera (NUEVO v2, H3).** El archivo
    versionado `backend/harness_defaults.env` es un snapshot del .env del deploy
    vivo filtrado por FLAG_REGISTRY (`deployment/export_harness_defaults.py:1-19`);
    las 2 keys nuevas NO existen en ningún deploy vivo, así que no hay nada que
    snapshotear, y con env limpio el default EFECTIVO de un deploy nuevo sale del
    código (config `"true"` + FlagSpec `default=True`), que es exactamente lo que
    la directiva pide. Por lo tanto: **no correr el generador como parte de este
    plan** (correrlo re-snapshotearía el deploy vivo entero y arrastraría el drift
    preexistente documentado — fuera de scope). PROHIBIDO replicar el assert legacy
    `"<KEY>=false" in content` sobre `harness_defaults.env` (patrón viejo
    `test_plan96_doctor_flag.py:53-59`, que es HOY el drift rojo conocido); en su
    lugar F0 agrega el test NEGATIVO `test_harness_defaults_sin_linea_off` (ver F0).

---

## 4. Fases

### F0 — Flags, config, help, set curado y ratchet

**Objetivo:** dar de alta las 2 flags del plan con **DEFAULT ON** (patrón triple
§3.6), visibles y apagables en UI.
**Valor:** todo lo demás queda gateado desde el minuto cero y disponible sin que el
operador tenga que prender nada.

**Archivos:**
- `Stacky Agents/backend/config.py`
- `Stacky Agents/backend/services/harness_flags.py`
- `Stacky Agents/backend/services/harness_flags_help.py`
- `Stacky Agents/backend/tests/test_harness_flags.py` (SOLO agregar las 2 keys a `_CURATED_DEFAULTS_ON`)
- `Stacky Agents/backend/tests/test_plan127_flags.py` (NUEVO)
- `Stacky Agents/backend/tests/test_harness_flags_requires.py` (arista nueva en `_REQUIRES_MAP_FROZEN`)
- `Stacky Agents/backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1` (ratchet)

**Flags nuevas (nombres EXACTOS):**

1. `STACKY_EXEC_ERROR_ANALYSIS_ENABLED` — bool, categoría `avanzado`
   (agregar la key a la tupla de `_CATEGORY_KEYS["avanzado"]`, junto a las del
   Plan 117, `harness_flags.py:261-263`). FlagSpec: `type="bool"`,
   `label="Análisis de errores con IA local"`,
   `description="Plan 127 — Botón en el detalle de una ejecución fallida que pide al modelo local (Plan 106) causa raíz y próximos pasos. Default ON (directiva del operador 2026-07-12). Requiere el modelo local habilitado (chequeo en runtime)."`,
   `group="global"`, `env_only=False`, **`default=True`** (§3.6). **SIN `requires=`.**
2. `STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED` — bool, categoría `devops`
   (agregar a la tupla devops de `_CATEGORY_KEYS`). FlagSpec: `type="bool"`,
   `label="Doctor local DevOps (IA local)"`,
   `description="Plan 127 — Alternativa gratuita y sin egreso al doctor de sección: analiza pipeline/environments/publicaciones y fallos de CI con el modelo local. Nada sale de tu máquina. Default ON (directiva del operador 2026-07-12)."`,
   `group="global"`, `env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`,
   **`default=True`** (precedente hija con requires+default=True:
   `harness_flags.py:2151-2152`).

**config.py** (mismo patrón truthy de `config.py:81-83`, ubicar junto al bloque LOCAL_LLM):

```python
STACKY_EXEC_ERROR_ANALYSIS_ENABLED = os.getenv(
    "STACKY_EXEC_ERROR_ANALYSIS_ENABLED", "true"
).lower() in ("true", "1", "yes")
STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED = os.getenv(
    "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", "true"
).lower() in ("true", "1", "yes")
```

*(Tupla truthy verificada idéntica a la de `config.py:81-83`; si al implementar
difiere, gana la del archivo.)*

**`_CURATED_DEFAULTS_ON`** (`tests/test_harness_flags.py:465`): agregar al FINAL del set:

```python
    # ── Activación operador 2026-07-12 — Plan 127: reuso IA local ON por default
    # (directiva explícita "HACELO DEFAULT ON"; HITL on-demand, cero costo pasivo) ──
    "STACKY_EXEC_ERROR_ANALYSIS_ENABLED",
    "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED",
```

**harness_flags_help.py:** 2 entradas nuevas, castellano llano, `what` ≤ 200 chars.
Ejemplo para la primera: what=`"Agrega un botón en el detalle de una ejecución fallida que le pide al modelo local de tu máquina una explicación del error y qué hacer."`,
when=`"Viene encendida. Apagala solo si no querés usar el modelo local para diagnósticos."`.

**_REQUIRES_MAP_FROZEN:** agregar la arista
`"STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED"` en el mapa
congelado de `tests/test_harness_flags_requires.py` (patrón de las flags del Plan 110).

**Tests PRIMERO — `tests/test_plan127_flags.py`:**
- `test_flags_registradas_en_registry` — ambas keys existen en el registro de FlagSpec.
- `test_flags_categorizadas` — `STACKY_EXEC_ERROR_ANALYSIS_ENABLED` ∈ categoría
  `avanzado`; `STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED` ∈ categoría `devops`.
- `test_local_doctor_requires_panel` — `spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_error_analysis_sin_requires` — `spec.requires is None`.
- `test_config_defaults_on` — sin env vars, ambos atributos de config valen `True`
  (patrón `test_plan96_doctor_flag.py:41-45`, invertido a ON).
- `test_flagspec_default_true` — `spec.default is True` para ambas.
- `test_flags_en_set_curado` — ambas keys ∈ `_CURATED_DEFAULTS_ON`
  (`from tests.test_harness_flags import _CURATED_DEFAULTS_ON`; precedente de import
  inter-test: `test_plan96_doctor_flag.py:64`).
- `test_harness_defaults_sin_linea_off` (H3) — `backend/harness_defaults.env` NO
  contiene `"STACKY_EXEC_ERROR_ANALYSIS_ENABLED=false"` ni
  `"STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED=false"` (key ausente o `=true` son válidos;
  una línea `=false` horneada pisaría el default de código en cada deploy nuevo).

**Comando:** desde `Stacky Agents/backend`:
`.venv\Scripts\python -m pytest tests\test_plan127_flags.py -q`
**No-regresión:** `.venv\Scripts\python -m pytest tests\test_harness_flags.py tests\test_harness_flags_requires.py tests\test_harness_flags_help.py -q`
*(Nota: `test_harness_flags_help.py` tiene 2 fallas PREEXISTENTES ajenas documentadas
— keys de planes 93/94/105; el criterio es que NO aparezcan fallas NUEVAS.)*

**Aceptación (binaria):** los 8 tests nuevos verdes; no-regresión sin fallas nuevas.
**Flag:** son las flags (default ON, §3.6). **Runtimes:** sin impacto (solo registro).
**Trabajo del operador:** ninguno (default ON por directiva; nada que prender).

---

### F1 — Refactor extractivo del snapshot forense (`api/diag.py`)

**Objetivo:** exponer el snapshot de `diagnose_execution` como función reutilizable
sin cambiar la respuesta HTTP en un byte.
**Valor:** C1 consume el diagnóstico determinista completo (manifest, heartbeat,
historia de transiciones, diagnosis, thresholds) sin duplicar lógica.

**Archivo:** `Stacky Agents/backend/api/diag.py`

**Cambio (extractivo, sin lógica nueva):** mover el cuerpo de `diagnose_execution`
(`diag.py:44-127`) a:

```python
def build_diagnosis_snapshot(execution_id: int) -> dict | None:
    """Snapshot forense completo de una ejecución (dict listo para jsonify).
    None si la ejecución no existe. Reusada por el Plan 127 (error-analysis)."""
```

que devuelve EXACTAMENTE el dict que hoy se pasa a `jsonify` en `diag.py:113-127`
(keys: `ok, execution, ticket, manifest, heartbeat, recovery_history, diagnosis,
recommended_action, thresholds`). La route queda:

```python
@bp.get("/execution/<int:execution_id>")
def diagnose_execution(execution_id: int):
    snapshot = build_diagnosis_snapshot(execution_id)
    if snapshot is None:
        return jsonify({"ok": False, "error": "execution_not_found",
                        "execution_id": execution_id}), 404
    return jsonify(snapshot)
```

*(El 404 conserva la forma EXACTA de `diag.py:49`.)*

**Tests PRIMERO — `tests/test_plan127_diag_snapshot.py`:**
- `test_snapshot_none_si_no_existe` — `build_diagnosis_snapshot(999999) is None`.
- `test_snapshot_keys_completas` — para una ejecución sembrada, el dict contiene
  las 9 keys listadas arriba.
- `test_route_intacta_200_y_404` — la route devuelve 200 con las mismas keys y
  404 con la forma exacta `{"ok": False, "error": "execution_not_found", ...}`.

**Comando:** `.venv\Scripts\python -m pytest tests\test_plan127_diag_snapshot.py -q`
**No-regresión (KPI-2):** `.venv\Scripts\python -m pytest tests\test_diag_endpoint.py -q`
(archivo EXISTENTE, prohibido modificarlo).

**Aceptación:** 3 tests nuevos verdes + `test_diag_endpoint.py` verde sin tocar.
**Flag:** ninguna (refactor puro). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

---

### F2 — Núcleo puro `services/error_analysis.py` (C1)

**Objetivo:** construir el prompt de análisis de error a partir del snapshot, con
saneado y truncado deterministas, sin Flask ni red.
**Valor:** testeable al 100% sin mocks de HTTP; un modelo menor no puede
equivocarse en la capa con efectos si esta capa es pura.

**Archivo NUEVO:** `Stacky Agents/backend/services/error_analysis.py`

**Contenido EXACTO (contratos):**

```python
"""services/error_analysis.py — Plan 127 C1. Núcleo puro del análisis de errores.

Prompt determinista desde el snapshot forense de api.diag (Plan 127 F1).
Sin Flask, sin red, sin ORM. La llamada al LLM vive en api/local_llm_analysis.py.
"""
from __future__ import annotations

from services.local_insights import HITL_RULES, truncate_middle   # puros, solo lectura
from services.pr_review_sanitize import redact_secrets            # Plan 110

ERROR_ANALYSIS_KEY = "error_analysis"   # key en AgentExecution.metadata_json
ANALYSIS_MAX = 4000                     # cap del markdown persistido
OUTPUT_HEAD_CHARS = 3000
OUTPUT_TAIL_CHARS = 3000
RECOVERY_HISTORY_MAX = 10               # últimas N transiciones al prompt
ANALYZABLE_STATUSES = frozenset({"error", "needs_review"})


def is_analyzable(status: str, error_message: str) -> bool:
    """True si status ∈ ANALYZABLE_STATUSES o hay error_message no vacío.

    DECISIÓN EXPLÍCITA (v2, H7): "running" NO es analizable — el análisis es
    post-mortem sobre runs TERMINADOS. Un run colgado/zombie se diagnostica con el
    snapshot determinista de diag (stale-running) y el flujo de recovery existente;
    analizarlo con el LLM daría conclusiones sobre un output parcial. Un run
    "running" sin error_message devuelve False ⇒ la API responde 409.
    """


def build_error_analysis_prompt(snapshot: dict, output_text: str) -> tuple[str, str]:
    """(system, user). El user se pasa ÍNTEGRO por redact_secrets al final."""


def cap_analysis(text: str) -> str:
    """Recorta a ANALYSIS_MAX conservando el inicio; agrega '\n... [recortado]' si recortó."""
```

**`build_error_analysis_prompt` — especificación:**
- `system` = `"Sos un ingeniero senior de debugging de sistemas de agentes IA. "
  "Tu ÚNICA tarea es analizar el fallo de una ejecución y explicarlo en markdown."
  + HITL_RULES`.
- `user` se arma con estas secciones EN ESTE ORDEN, tomando los datos del snapshot
  (keys de F1) con `.get(...)` defensivo (cualquier key ausente ⇒ sección omitida,
  nunca KeyError):
  1. `== EJECUCIÓN ==` — id, agent_type, status, started_by, started_at,
     completed_at, completion_source (del dict `snapshot["execution"]`).
  2. `== ERROR ==` — `snapshot["execution"]["error_message"]`.
  3. `== DIAGNOSIS DETERMINISTA ==` — `snapshot["diagnosis"]` y
     `snapshot["recommended_action"]` (texto literal: son la salida de `_diagnose`
     de diag.py, ya en llano).
  4. `== HEARTBEAT ==` — `json.dumps(snapshot["heartbeat"], ensure_ascii=False)`.
  5. `== MANIFEST ==` — `json.dumps(snapshot["manifest"], ensure_ascii=False)`
     (si es None ⇒ literal `"(sin manifest)"`).
  6. `== TRANSICIONES (últimas 10) ==` — `snapshot["recovery_history"][-RECOVERY_HISTORY_MAX:]`,
     una línea por evento: `old→new (changed_by, changed_at): reason`.
  7. `== COLA DEL OUTPUT ==` — `truncate_middle(output_text, OUTPUT_HEAD_CHARS, OUTPUT_TAIL_CHARS)`.
  8. Instrucción de salida FIJA:
     `"Respondé en markdown con EXACTAMENTE estas secciones:\n"
      "## Qué pasó\n## Causa raíz más probable\n## Próximos pasos sugeridos (para el operador)\n"
      "Si la evidencia no alcanza, decilo explícitamente en 'Causa raíz'; NO inventes."`
- Último paso, obligatorio: `user = redact_secrets(user)` (una sola pasada sobre el
  string completo ⇒ KPI-5 por construcción: el modelo nunca ve el secreto).

**Tests PRIMERO — `tests/test_plan127_error_analysis_core.py`:**
- `test_is_analyzable_error_y_needs_review` — True para ambos status con error vacío.
- `test_is_analyzable_completed_con_error_message` — True.
- `test_is_analyzable_completed_limpio` — False (`("completed", "")`).
- `test_is_analyzable_running_false` (H7) — False (`("running", "")`): los zombies
  se diagnostican con diag/recovery, no con el LLM.
- `test_prompt_incluye_diagnosis_y_error` — el user contiene los textos de
  `diagnosis`, `recommended_action` y `error_message` del snapshot de prueba.
- `test_prompt_redacta_secretos` — snapshot con
  `error_message="fallo con password=hunter2"` ⇒ `"hunter2" not in user` y la
  máscara de `pr_review_sanitize` presente.
- `test_prompt_trunca_output_largo` — `output_text` de 20000 chars ⇒ el user
  contiene el marcador de recorte de `truncate_middle` y len acotada.
- `test_prompt_tolera_snapshot_incompleto` — snapshot `{"execution": {"id": 1}}`
  no lanza; devuelve (system, user) no vacíos.
- `test_cap_analysis` — 10000 chars ⇒ ≤ `ANALYSIS_MAX + 20` y sufijo de recorte.

**Comando:** `.venv\Scripts\python -m pytest tests\test_plan127_error_analysis_core.py -q`
**Aceptación:** 9 tests verdes. **Flag:** ninguna (módulo puro sin consumidores aún).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

---

### F3 — Endpoint C1: `POST /api/llm/executions/<id>/error-analysis`

**Objetivo:** exponer el análisis on-demand, persistirlo en la ejecución analizada
y auditar la llamada como ejecución interna.
**Valor:** el operador diagnostica un run fallido en un click, gratis y offline.

**Archivos:**
- `Stacky Agents/backend/api/local_llm_analysis.py` (route nueva)
- `Stacky Agents/backend/services/local_insights.py` (SOLO ampliar `EXCLUDED_AGENT_TYPES`)
- `Stacky Agents/backend/tests/test_plan127_error_analysis_api.py` (NUEVO)

**Decisión de ruta (explícita):** el path pedido "en diag" se implementa en el
blueprint `/api/llm` y NO en `/api/diag`, porque ahí viven `_guard()` y todo el
patrón de ejecución interna del Plan 106/117 (`local_llm_analysis.py:44-112,404-427`);
`diag.py` queda determinista/forense. Es el mismo criterio que usó el Plan 117 con
`POST /api/llm/insights/<id>/generate`.

**Route (patrón EXACTO de `generate_insight_route`, `local_llm_analysis.py:404-427`):**

```python
_ERROR_ANALYSIS_FALLBACK_PROJECT = "__error_analysis__"

@bp.post("/executions/<int:execution_id>/error-analysis")
def error_analysis_route(execution_id: int):
    """Plan 127 C1 — análisis del fallo de UNA ejecución con el modelo local (HITL).

    404 LOCAL_LLM_ENABLED off (_guard) | 404 STACKY_EXEC_ERROR_ANALYSIS_ENABLED off
    | 404 execution inexistente | 409 nada que analizar | 502 fallo del modelo
    | 503 endpoint local vacío | 400 POST sin body JSON (_guard; mandar json={}).
    """
```

**Flujo (numerado, sin libertad de interpretación):**
1. `guard = _guard()`; si truthy, devolverlo.
2. `if not getattr(_config.config, "STACKY_EXEC_ERROR_ANALYSIS_ENABLED", False):
   return jsonify({"error": "error_analysis_disabled"}), 404`.
   *(El fallback `False` del getattr es deliberado: atributo ausente = apagado.)*
3. `body = request.get_json(silent=True) or {}` (H9 — literal; `_guard` ya garantizó
   `is_json`, esto solo normaliza `{}`).
4. `from api.diag import build_diagnosis_snapshot` (import lazy, patrón del repo).
   `snapshot = build_diagnosis_snapshot(execution_id)`; `None` ⇒
   `jsonify({"error": "execution_not_found"}), 404`.
5. Dentro de `session_scope()`: leer la fila target
   (`session.get(AgentExecution, execution_id)`) para obtener `output` (no está en
   el snapshot) y `ticket.project` (vía `session.get(Ticket, row.ticket_id)`;
   si no hay project usable ⇒ `_ERROR_ANALYSIS_FALLBACK_PROJECT`).
6. `from services.error_analysis import (is_analyzable, build_error_analysis_prompt,
   cap_analysis, ERROR_ANALYSIS_KEY)`. Si
   `not is_analyzable(status, error_message)` ⇒
   `jsonify({"error": "nothing_to_analyze", "status": status}), 409`
   *(cubre también `running`/zombies — decisión H7 documentada en F2)*.
7. `system, user = build_error_analysis_prompt(snapshot, output_text)`.
8. Crear la ejecución interna auditora (patrón `analyze_code_route`,
   `local_llm_analysis.py:237-242`): `_ensure_internal_ticket(session, project)` +
   `_create_execution(session, ticket.id, "local_llm_error_analyst",
   {"target_execution_id": execution_id})`. **El prompt NO se persiste** en
   `input_context_json` (solo el payload chico de arriba) — misma política de
   no-persistencia del crudo que el Plan 110.
9. `t0 = time.monotonic()` **[ADICIÓN ARQUITECTO]**, luego
   `invoke_local_llm(agent_type="local_llm_error_analyst", system=system, user=user,
   on_log=lambda level, msg: None, execution_id=analyzer_id, model=body.get("model"))`
   dentro de try/except; excepción ⇒ `_finish_execution(analyzer_id, status="error",
   error=str(e))` + `jsonify({"ok": False, "error": str(e),
   "execution_id": analyzer_id}), 502`. **En el camino 502 NO se escribe nada en la
   ejecución target.**
10. Éxito: `elapsed_ms = int((time.monotonic() - t0) * 1000)` **[ADICIÓN ARQUITECTO
    — observabilidad de latencia del modelo local: mitiga R1 (32B lento) con costo
    ~0; el operador ve cuánto tardó y con qué modelo]**.
    `analysis = cap_analysis(redact_secrets(response.text))` (doble defensa:
    por si el modelo parafrasea un secreto que vio en texto ya enmascarado).
    `_finish_execution(analyzer_id, status="completed", output=analysis)`.
    En `session_scope()` nuevo, sobre la fila TARGET:
    `md = row.metadata_dict or {}` (property tolerante a JSON corrupto,
    `models.py:260-265` — un `metadata_json` roto degrada a `{}` sin excepción);
    `md[ERROR_ANALYSIS_KEY] = {"analysis": analysis, "model": resolved_model,
    "generated_at": <utcnow ISO>, "analyzer_execution_id": analyzer_id,
    "elapsed_ms": elapsed_ms}; row.metadata_dict = md`.
    Regenerar = sobrescribir la key (idempotente).
11. `return jsonify({"ok": True, "analysis": analysis, "model": resolved_model,
    "analyzer_execution_id": analyzer_id, "elapsed_ms": elapsed_ms})` —
    `resolved_model` con el patrón de `playground_route` (`local_llm_analysis.py:395`).

**`local_insights.py` (cambio de UNA línea de datos):** agregar a
`EXCLUDED_AGENT_TYPES` (`local_insights.py:17-23`) los literales
`"local_llm_error_analyst"`, `"local_llm_devops_doctor"` y `"local_llm_ci_explainer"`
(los 3 agent_types nuevos del plan, de una sola vez). Motivo: anti-recursión — el
sweep del 117 no debe anotar las ejecuciones del propio analizador. Nota de
ortogonalidad: la restricción "no tocar local_insights.py" era del Plan 121 para SU
alcance; acá es una adición de literales al frozenset existente, con test propio,
sin cambio de comportamiento para los tipos ya listados.

**Tests PRIMERO — `tests/test_plan127_error_analysis_api.py`**
(mockear `invoke_local_llm` con `monkeypatch.setattr` sobre el MÓDULO ORIGEN
`copilot_bridge.invoke_local_llm` — la route lo importa lazy, gotcha documentado
del repo; los POST llevan `json={}`):
- `test_flag_off_404` — LOCAL_LLM on, flag del plan APAGADA A MANO
  (`monkeypatch.setattr(_config.config, "STACKY_EXEC_ERROR_ANALYSIS_ENABLED", False)`)
  ⇒ 404 `error_analysis_disabled`. *(Con default ON ya no existe el estado
  "off sin tocar nada": el test DEBE apagarla explícitamente.)*
- `test_local_llm_off_404` — `LOCAL_LLM_ENABLED` apagada a mano (mismo patrón
  monkeypatch) ⇒ 404 (vía `_guard`).
- `test_execution_inexistente_404`.
- `test_nothing_to_analyze_409` — ejecución `completed` sin error_message.
- `test_ok_persiste_metadata` — ejecución sembrada con `status="error"`; 200;
  `metadata_dict["error_analysis"]["analysis"]` no vacío; `elapsed_ms` presente y
  `>= 0`; `analyzer_execution_id` apunta a una AgentExecution
  `agent_type="local_llm_error_analyst"` con `status="completed"`.
- `test_regenerar_sobrescribe` — segunda llamada reemplaza `generated_at`.
- `test_bridge_caido_502_sin_persistencia` — mock lanza RuntimeError ⇒ 502 y la
  target NO tiene la key `error_analysis`.
- `test_secreto_no_persiste` — target con `error_message="password=hunter2 en el deploy"`
  y mock que DEVUELVE ese mismo texto ⇒ el análisis persistido no contiene `hunter2`.
- `test_agent_types_excluidos_de_insights` — los 3 literales nuevos ∈
  `services.local_insights.EXCLUDED_AGENT_TYPES`.

**Comando:** `.venv\Scripts\python -m pytest tests\test_plan127_error_analysis_api.py -q`
**No-regresión:** `.venv\Scripts\python -m pytest tests\test_plan106_analyze_code_api.py tests\test_plan117_insights_api.py tests\test_plan117_insights_sweep.py -q`
**Aceptación (KPI-1):** 9 tests verdes + no-regresión verde.
**Flag:** `STACKY_EXEC_ERROR_ANALYSIS_ENABLED` (default ON; apagada a mano ⇒ 404).
**Runtimes:** analiza ejecuciones de los 3 runtimes por igual (lee AgentExecution);
fallback: 404/502 accionables, sistema idéntico a hoy.
**Trabajo del operador:** ninguno (default ON; nada que prender).

---

### F4 — Refactor extractivo del contexto del doctor (`api/devops_section_doctor.py`)

**Objetivo:** compartir la construcción de contexto por sección entre el doctor
cloud (Plan 104) y el doctor local nuevo, sin duplicar el render YAML server-side.
**Valor:** una sola fuente de verdad del contexto; el doctor local hereda gratis
las mejoras futuras.

**Archivo:** `Stacky Agents/backend/api/devops_section_doctor.py`

**Cambio (extractivo):** mover la lógica de `devops_section_doctor.py:89-120`
(render YAML condicional para `section_id=="pipeline"` + armado de `context_blocks`) a:

```python
def build_doctor_context_blocks(section_id: str, project: str, payload: dict) -> list[dict] | None:
    """Bloques de contexto del doctor de una sección. None si la sección no existe.
    MUTA payload agregando yaml_ado/yaml_gitlab para pipeline (comportamiento actual).
    Compartida por el doctor cloud (Plan 104) y el doctor local (Plan 127)."""
```

- Devuelve `None` si `SECTION_DOCTORS.get(section_id) is None`
  (`SECTION_DOCTORS` en `devops_section_doctor.py:32`).
- El cuerpo es el código actual movido VERBATIM (incluidos los comentarios de
  invariantes sobre `kind` y el render YAML gateado por
  `STACKY_PIPELINE_GENERATOR_ENABLED`).
- La route cloud (`section_doctor_route`) pasa a llamarla; sus gates
  (`devops_section_doctor.py:68-71`), el ticket ancla `ado_id=-3` y el despacho a
  `run_agent` quedan INTACTOS.

**Tests PRIMERO — `tests/test_plan127_doctor_context.py`:**
- `test_none_para_seccion_desconocida`.
- `test_context_incluye_instruccion_y_payload` — para `section_id="environments"`,
  el `content` del bloque contiene la instrucción de `SECTION_DOCTORS["environments"]`
  y el JSON del payload.
- `test_pipeline_renderiza_yaml_con_generador_on` — con
  `STACKY_PIPELINE_GENERATOR_ENABLED=true` y un spec mínimo válido, `payload`
  termina con keys `yaml_ado`/`yaml_gitlab`.

**Comando:** `.venv\Scripts\python -m pytest tests\test_plan127_doctor_context.py -q`
**No-regresión (KPI-4):** `.venv\Scripts\python -m pytest tests\test_plan104_section_doctor.py -q`
(archivo EXISTENTE, prohibido modificarlo).
**Aceptación:** 3 nuevos verdes + Plan 104 verde sin tocar.
**Flag:** ninguna (refactor). **Runtimes:** sin impacto. **Operador:** ninguno.

---

### F5 — Endpoint C3: `POST /api/devops/sections/<section_id>/doctor/local`

**Objetivo:** doctor de sección síncrono con el modelo local: mismo contexto,
respuesta markdown inmediata, sin conversación, sin agente DevOps, sin egreso.
**Valor:** el análisis experto por sección pasa de "caro y externo" a "gratis y
privado"; funciona incluso con `STACKY_DEVOPS_AGENT_ENABLED=false`.

**Archivos:**
- `Stacky Agents/backend/api/devops_section_doctor.py` (route nueva)
- `Stacky Agents/backend/api/devops.py` (UNA key nueva en `_health_payload()`)
- `Stacky Agents/backend/tests/test_plan127_devops_doctor_local.py` (NUEVO)

**Route:**

```python
@bp.post("/<section_id>/doctor/local")
def section_doctor_local_route(section_id: str):
    """Plan 127 C3 — doctor de sección con el modelo LOCAL (síncrono, HITL).
    NO exige STACKY_DEVOPS_AGENT_ENABLED (no usa agent_runner) ni
    STACKY_DEVOPS_SECTION_DOCTOR_ENABLED (camino independiente al cloud)."""
```

**Flujo:**
1. `if not getattr(_config.config, "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", False): abort(404)`
   (patrón `devops_section_doctor.py:68-69`; fallback `False` deliberado).
2. `from api.local_llm_analysis import _guard, _ensure_internal_ticket, _create_execution, _finish_execution`
   (precedente de import entre blueprints: `devops_section_doctor.py:129`).
   `guard = _guard()`; si truthy, devolverlo (cubre LOCAL_LLM off ⇒ 404, endpoint
   vacío ⇒ 503, POST sin JSON ⇒ 400).
3. `body = request.get_json(silent=True) or {}` (H9). Contrato:
   `{"project": str (required), "payload": dict (required), "model": str (optional)}`
   — MISMO contrato que el cloud menos `runtime` (acá no aplica). Validación
   idéntica a `devops_section_doctor.py:81-82` ⇒ 400.
4. `blocks = build_doctor_context_blocks(section_id, project, payload)` (F4);
   `None` ⇒ `jsonify({"error": "unknown_section", "section": section_id}), 404`.
5. Prompt: `from services.local_insights import HITL_RULES` y
   `from services.pr_review_sanitize import redact_secrets`.
   `system = "Sos un ingeniero DevOps senior. Analizá el contexto de la sección y "
   "respondé en markdown con secciones 'Hallazgos' y 'Cambios sugeridos'." + HITL_RULES`.
   `user = redact_secrets("\n\n".join(b["content"] for b in blocks))` (H8 — TODOS
   los bloques, no solo el primero: si F4 devuelve más de un bloque, nada se pierde;
   el content ya incluye la instrucción específica de la sección con su primera
   línea HITL; el redact protege valores de variables/secretos del payload — KPI-5).
6. Ejecución interna auditora: `_ensure_internal_ticket(session, project)`
   (reusa el ancla `ado_id=-5` por proyecto del Plan 106 — NO se crea un ado_id
   nuevo) + `_create_execution(session, ticket.id, "local_llm_devops_doctor",
   {"section": section_id, "project": project})`.
7. `t0 = time.monotonic()`; `invoke_local_llm(agent_type="local_llm_devops_doctor",
   system=system, user=user, on_log=lambda level, msg: None,
   execution_id=analyzer_id, model=body.get("model"))`
   en try/except ⇒ 502 + `_finish_execution(error)` (patrón F3 paso 9).
8. Éxito: `elapsed_ms = int((time.monotonic() - t0) * 1000)` **[ADICIÓN ARQUITECTO]**;
   `_finish_execution(analyzer_id, status="completed", output=response.text[:10000])`
   y `return jsonify({"ok": True, "analysis": response.text, "model": resolved_model,
   "execution_id": analyzer_id, "section": section_id, "elapsed_ms": elapsed_ms})`.

**`api/devops.py` (REESCRITO v2, H5):** agregar en `_health_payload()`
(`devops.py:28-64`), al final del dict:

```python
"local_doctor_enabled": bool(
    getattr(cfg, "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", False)
    and getattr(cfg, "LOCAL_LLM_ENABLED", False)
),  # Plan 127 — CONJUNCIÓN: la UI solo ofrece el botón si el camino completo sirve
```

Motivo (H5): si fuera solo la flag, con `LOCAL_LLM_ENABLED` apagada a mano la UI
mostraría un botón que muere en 404 — con default ON en ambas esto no pasa, pero el
health debe ser honesto ante cualquier combinación. La paridad health/bootstrap es
automática (`devops.py:81` reusa `_health_payload()`), pero correr el test de paridad
como no-regresión: `.venv\Scripts\python -m pytest tests\ -q -k bootstrap_health`;
**si `-k bootstrap_health` no colecta ningún test, correr en su lugar
`.venv\Scripts\python -m pytest tests\test_plan87_devops_flag.py -q`** (H6 — sin
pasos "buscar a ver qué hay": uno de los dos comandos es el criterio).

**Tests PRIMERO — `tests/test_plan127_devops_doctor_local.py`** (mock de
`copilot_bridge.invoke_local_llm`, POST con `json={...}`; los estados "off" se
logran APAGANDO a mano vía `monkeypatch.setattr` sobre `_config.config`):
- `test_flag_off_404` — `STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED` apagada a mano ⇒ 404.
- `test_local_llm_off_404` — `LOCAL_LLM_ENABLED` apagada a mano ⇒ 404.
- `test_unknown_section_404`.
- `test_body_invalido_400` — sin `project` o sin `payload` dict.
- `test_ok_sin_agente_devops` (KPI-3) — `STACKY_DEVOPS_AGENT_ENABLED=false` y
  `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED=false`; 200; `analysis` no vacío;
  `elapsed_ms >= 0`; la AgentExecution auditora tiene
  `agent_type="local_llm_devops_doctor"`.
- `test_redacta_secretos_en_user` — payload con `{"vars": {"DB_PASSWORD": "hunter2"}}`;
  capturar el `user` que recibió el mock ⇒ `"hunter2" not in user`.
- `test_bridge_caido_502`.
- `test_health_expone_local_doctor_enabled` — `GET /api/devops/health` contiene la
  key `local_doctor_enabled == True` con ambas flags en default.
- `test_health_conjuncion_local_llm_off` (H5) — con `LOCAL_LLM_ENABLED` apagada a
  mano, `local_doctor_enabled == False` aunque la flag del doctor siga ON.

**Comando:** `.venv\Scripts\python -m pytest tests\test_plan127_devops_doctor_local.py -q`
**No-regresión:** `.venv\Scripts\python -m pytest tests\test_plan104_section_doctor.py tests\test_plan96_doctor_endpoint.py tests\test_plan87_devops_flag.py -q`
*(el tercero cubre el delta del health payload — H6)*
**Aceptación:** 9 verdes + no-regresión verde.
**Flag:** `STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED` (default ON; apagada a mano ⇒ 404).
**Runtimes:** no despacha a ningún runtime (HTTP backend puro); el doctor cloud
de los 3 runtimes queda intacto como opción. Fallback: 404/502/503 accionables.
**Trabajo del operador:** ninguno (default ON; nada que prender).

---

### F6 — Frontend: botón de análisis de error + modo local del doctor

**Objetivo:** exponer C1 y C3 en la UI con degradación honesta.
**Valor:** los dos análisis quedan a un click donde el operador ya está mirando;
con default ON aparecen sin configurar nada.

**Archivos:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — extender el grupo `LocalLlmApi`
  (`endpoints.ts:3595`) con DOS métodos:
  `errorAnalysis(executionId: number)` → `POST /api/llm/executions/${executionId}/error-analysis`
  (body `{}`), y `sectionDoctorLocal(sectionId: string, body: {project: string; payload: object; model?: string})`
  → `POST /api/devops/sections/${sectionId}/doctor/local`. Mismo helper HTTP que
  usa `insights/…/generate` (`endpoints.ts:3599`).
- `Stacky Agents/frontend/src/executions/errorAnalysisModel.ts` (NUEVO, puro):
  `shouldOfferErrorAnalysis(status: string, metadata: Record<string, unknown> | null): boolean`
  — true si `status ∈ {"error","needs_review"}` o `metadata?.error_analysis` existe;
  `disabledHint(httpStatus: number): string` — para 404 devuelve el texto EXACTO
  (H10, redactado para default ON)
  `"El análisis con IA local está apagado en el Arnés: reactivá STACKY_EXEC_ERROR_ANALYSIS_ENABLED y LOCAL_LLM_ENABLED."`,
  para 502 `"El modelo local no respondió: verificá que Ollama esté corriendo."`,
  para cualquier otro `"No se pudo analizar (HTTP <status>)."`.
- `Stacky Agents/frontend/src/components/ExecutionErrorAnalysisBlock.tsx` (NUEVO)
  + `ExecutionErrorAnalysisBlock.module.css` — componente hermano de
  `ExecutionInsightBlock.tsx` (mismo patrón visual): si
  `metadata.error_analysis` existe muestra el markdown persistido + botón
  "Regenerar" + caption chico **[ADICIÓN ARQUITECTO]** con
  `"{model} · {(elapsed_ms/1000).toFixed(1)}s"` (si ambas keys existen en el
  metadata persistido) — el operador ve de un vistazo qué modelo respondió y cuánto
  tardó (clave con un 32B lento, R1); si no existe, botón
  "Analizar error con IA local". Estados: idle / loading (spinner + texto
  "El modelo local puede tardar 1-3 minutos…") / result / error(hint de
  `disabledHint`). Se monta en `ExecutionDetailDrawer.tsx` junto al bloque de
  insights del Plan 117, gateado por `shouldOfferErrorAnalysis` (SIN fetch extra de
  flags: la degradación es el 404 — con default ON el camino feliz es directo).
- `Stacky Agents/frontend/src/components/devops/SectionDoctorButton.tsx` — agregar
  una acción secundaria "Doctor local (no sale de tu máquina)" visible cuando el
  health del panel (que el componente ya recibe o puede recibir por props desde su
  contenedor) trae `local_doctor_enabled === true` (con default ON esto es el caso
  normal; la conjunción H5 garantiza que el botón solo aparece si el camino sirve);
  al click llama `LocalLlmApi.sectionDoctorLocal` y muestra el markdown en un panel
  colapsable inline (estado local del componente; NO navega a la consola como el cloud).
- `Stacky Agents/frontend/src/devops/doctorModel.ts` (+ su test EXISTENTE
  `doctorModel.test.ts`) — agregar helpers puros:
  `canUseLocalDoctor(health: {local_doctor_enabled?: boolean} | null): boolean` y
  `buildLocalDoctorBody(project: string, payload: object): {project: string; payload: object}`.

**Tests (gap RTL/jsdom preexistente ⇒ SOLO tests puros + tsc, patrón planes 107/110/119):**
- `frontend/src/executions/errorAnalysisModel.test.ts` (NUEVO, vitest):
  `shouldOfferErrorAnalysis` (4 casos: error sin metadata / completed limpio /
  completed con metadata.error_analysis / needs_review) y `disabledHint`
  (404, 502, 500 — asserts sobre los textos EXACTOS de arriba).
- `frontend/src/devops/doctorModel.test.ts`: 2 casos nuevos de `canUseLocalDoctor`
  (health null ⇒ false; `{local_doctor_enabled: true}` ⇒ true).

**Comandos:** desde `Stacky Agents/frontend`:
`npx vitest run src/executions/errorAnalysisModel.test.ts src/devops/doctorModel.test.ts`
y `npx tsc --noEmit`.
**Aceptación (binaria):** vitest verde + `tsc --noEmit` con 0 errores.
**Flags:** las mismas de F3/F5 (default ON ⇒ los botones aparecen de entrada; si el
operador apaga a mano, `error_analysis` ausente + `local_doctor_enabled=false` +
hints del 404 explican cómo volver).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

---

### F7 — (OPCIONAL / DIFERIBLE) C2: explicar fallo de CI con IA local

> Si al implementar la sesión viene justa de presupuesto, esta fase se DIFIERE
> completa a un plan futuro sin tocar nada de F0-F6 (no hay dependencias inversas).
> No implementarla NO es falso-incompleto: el plan se considera hecho con F0-F6.

**Objetivo:** en el doctor de pipelines (Plan 96), botón por job fallido que pide
al modelo local causa raíz + fix a partir del log ya clasificado.
**Valor:** hoy el doctor 96 clasifica con regex y muestra snippet; la explicación
en llano la hace el operador a mano.

**Archivos:**
- `Stacky Agents/backend/api/devops.py` — route nueva DEBAJO de
  `doctor_diagnose_route` (`devops.py:376-407`):

```python
@bp.post("/doctor/explain-failure")
def doctor_explain_failure_route():
    """Plan 127 C2 — explica UN job fallido con el modelo LOCAL. El log NO se persiste."""
```

  Gates en orden: `STACKY_DEVOPS_DOCTOR_ENABLED` off ⇒ `abort(404)` (hereda la flag
  del 96, HOY default ON — curada en `test_harness_flags.py:524`);
  `STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED` off ⇒ `abort(404)` (reusa
  la flag de C3 — cero flags nuevas); `_guard()` importado de
  `api.local_llm_analysis`. `body = request.get_json(silent=True) or {}` (H9);
  `{"project", "pipeline_id", "job_id"}` los 3
  required ⇒ 400 si falta alguno. Flujo: `get_ci_logs_provider(project)` →
  `log = provider.get_job_log(str(job_id))` (mismos except/status que
  `devops.py:391-396`) → `from services.failure_doctor import classify_failure`;
  `diagnosis = classify_failure(log)` →
  `user = redact_secrets("== CLASIFICACIÓN DETERMINISTA ==\n" + json.dumps(diagnosis, ensure_ascii=False)
  + "\n\n== LOG (recortado) ==\n" + truncate_middle(log, 4000, 4000)
  + "\n\nExplicá en markdown: ## Qué falló / ## Causa raíz más probable / ## Fix sugerido")`
  → `system = "Sos un ingeniero DevOps senior experto en debugging de CI." + HITL_RULES`
  → ejecución interna `agent_type="local_llm_ci_explainer"` con payload
  `{"project", "pipeline_id", "job_id", "log_chars": len(log)}` (**el log NO va a
  `input_context_json`** — invariante del Plan 96) → `invoke_local_llm(...)` →
  200 `{"ok": True, "analysis", "model", "job_id", "execution_id"}` | 502 patrón F3.
- `Stacky Agents/frontend/src/components/devops/PipelineDoctorPanel.tsx` — botón
  "Explicar con IA local" por job fallido, visible con `local_doctor_enabled`;
  resultado markdown colapsable bajo la fila del job. Endpoint nuevo en el grupo
  API que el panel ya usa para `doctor/diagnose`:
  `doctorExplainFailure(body: {project: string; pipeline_id: string; job_id: string})`.
- `Stacky Agents/backend/tests/test_plan127_ci_explain_local.py` (NUEVO; los
  estados "off" se logran apagando a mano vía monkeypatch, como en F3/F5):
  - `test_404_sin_flag_96` / `test_404_sin_flag_local` / `test_400_body_incompleto`.
  - `test_ok_con_mocks` — provider fake (get_job_log devuelve un log con
    `npm ERR!`) + bridge mockeado ⇒ 200 y `analysis` no vacío.
  - `test_log_no_persiste` — `input_context_json` de la ejecución auditora NO
    contiene el contenido del log (solo `log_chars`).
  - `test_log_con_secreto_no_llega_al_modelo` — log con `password=hunter2` ⇒ el
    `user` capturado por el mock no contiene `hunter2`.

**Comando:** `.venv\Scripts\python -m pytest tests\test_plan127_ci_explain_local.py -q`
**No-regresión:** `.venv\Scripts\python -m pytest tests\test_plan96_doctor_endpoint.py tests\test_plan96_failure_doctor.py -q`
**Aceptación:** 6 verdes + no-regresión verde + tsc 0.
**Flags:** `STACKY_DEVOPS_DOCTOR_ENABLED` (existente, default ON) AND
`STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED` (nueva, default ON) ⇒ disponible de entrada.
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El modelo local (32B en hardware consumer) tarda minutos y el operador cree que se colgó | Timeout ya configurable (`LOCAL_LLM_TIMEOUT_SEC`, 10..600, `harness_flags.py:2589-2597`); UI con estado loading explícito ("puede tardar 1-3 minutos"); el resultado de C1 queda PERSISTIDO (no se pierde si cierra el drawer); **[ADICIÓN ARQUITECTO]** `elapsed_ms` + `model` visibles calibran la expectativa en usos siguientes |
| R2 | El modelo parafrasea en su respuesta un secreto visto en el contexto | El secreto nunca llega al modelo (redact en el user prompt, F2/F5/F7) + `redact_secrets` de nuevo sobre el análisis antes de persistir (F3 paso 10). Residual: redacción por patrones no exhaustiva ⇒ HITL + todo queda LOCAL (no hay egreso ni siquiera en el peor caso) |
| R3 | Refactors F1/F4 rompen respuestas existentes | Criterio binario: `test_diag_endpoint.py` y `test_plan104_section_doctor.py` EXISTENTES verdes SIN modificarse (KPI-2/KPI-4) |
| R4 | El sweep del Plan 117 anota las ejecuciones del propio analizador (recursión/ruido) | Los 3 agent_types nuevos entran a `EXCLUDED_AGENT_TYPES` en F3, con test dedicado |
| R5 | Commit arrastra WIP ajeno del working tree (config.py, harness_flags.py, test_harness_flags.py están tocados o son compartidos) | Guardarraíl §3.9: staging quirúrgico por hunk, verificación `git diff --cached` contra la lista de archivos del plan antes de commitear; prohibido stash/reset/add -A |
| R6 | Flags nuevas rompen los meta-tests del arnés | §3.6/3.7/3.8 codifican los gotchas conocidos EN SU VERSIÓN DEFAULT ON (patrón triple: default=True + curada + config "true"; arista requires; help + ratchet); F0 los cubre con tests antes de escribir features |
| R7 | El snapshot forense crece en el futuro y el prompt se hace enorme | Caps duros en F2 (truncate_middle 3000+3000, historia limitada a 10, cap_analysis 4000); `.get()` defensivo tolera keys nuevas o ausentes |
| R8 | Doble click / regeneración concurrente sobre la misma ejecución | Última escritura gana sobre `metadata_json["error_analysis"]` (dict completo reemplazado, sin merge parcial); aceptable en mono-operador, documentado |
| R9 (v2) | Default ON expone botones cuando Ollama no está corriendo | Los endpoints son HITL puros (cero sweeps: ON no consume nada solo). Ante click con Ollama caído ⇒ 502 con hint accionable mostrado por la UI (F6); el botón del doctor DevOps además se auto-oculta por la conjunción H5 si LOCAL_LLM está apagada. Peor caso = un click que devuelve un mensaje claro |
| R10 (v2) | Drift `harness_defaults.env` (documentado, preexistente) contamina las flags nuevas | §3.11: NO se regenera el archivo (el default vive en código); test negativo `test_harness_defaults_sin_linea_off` garantiza que ninguna línea `=false` horneada pise el default ON en deploys nuevos; prohibido el assert legacy `=false` |

---

## 6. Fuera de scope (explícito)

- **Plan 121 (centinela de egreso) — DESLINDE OBLIGATORIO:** el 121 audita la
  ENTRADA de las ejecuciones (prompts salientes, secretos/PII, sweep en background,
  clase `secrets` en `egress_policies.py`). Este plan analiza la SALIDA/fallo
  (error de un run ya terminado) y contextos DevOps, siempre on-demand. Cero
  archivos compartidos de negocio: el 121 tocará `egress_policies.py` y creará su
  propio módulo; este plan no toca `egress_policies.py`. Único punto de contacto
  potencial: `EXCLUDED_AGENT_TYPES` (si el 121 se implementa después, agregará sus
  propios literales — apéndices independientes, sin conflicto semántico).
- **Plan 117:** NO se modifica su sweep, sus prompts, sus caps ni su flag; solo se
  amplía el frozenset de exclusión (F3). El insight (TL;DR/triage del OUTPUT) y el
  análisis de error (forense del FALLO con manifest/heartbeat/transiciones) son
  features distintas y coexisten en el mismo drawer.
- **Sin sweep/daemon nuevo:** C1 es solo on-demand. Un barrido automático de
  errores queda para un plan futuro si el operador lo pide. **Default ON no cambia
  esto:** las flags encendidas NO disparan trabajo pasivo alguno.
- **Análisis de runs `running`/zombies (H7):** explícitamente fuera — el análisis
  es post-mortem; los colgados se cubren con el diagnóstico determinista de diag
  (stale-running) y el flujo de recovery existente. `is_analyzable` devuelve False
  y la API responde 409.
- **Sin fallback cloud:** si el modelo local no está, NO se degrada a
  Copilot/Haiku. El camino externo existente (doctor 104, revisor 110 Haiku) queda
  como opción separada y explícita del operador.
- **Sin selector de modelo en UI** para estos botones (el body acepta `model`
  opcional a nivel API, heredado del patrón 106, pero la UI usa el default de
  `LOCAL_LLM_MODEL`; el Playground del 106 ya cubre la experimentación).
- **Regenerar/corregir `harness_defaults.env` y su drift preexistente (§3.11):**
  fuera de scope; este plan solo garantiza no empeorarlo (test negativo F0).
- **Renumerar `127_PLAN_TABLERO_EVOLUCION_PLANES.md` (H4):** acción aparte
  recomendada, NO la ejecuta quien implemente este plan.
- **Plan 120 F6 (diagnóstico IA de deploys):** ya especificado dentro del 120; no
  se duplica acá.
- **Análisis de logs de CI multi-job / batch:** F7 explica UN job por click; nada
  de "analizar todos los jobs" automático.
- **Paridad de skills/prompts en los 3 runtimes CLI:** no aplica — la IA local es
  HTTP backend-side (no-objetivo explícito heredado del Plan 106, C5/KPI-4).

---

## 7. Glosario, orden de implementación y DoD

### Glosario corto (dominio Stacky)

- **IA local / modelo local:** servidor OpenAI-compatible en la máquina del
  operador (Ollama/LM Studio/vLLM, típicamente Qwen), consumido vía
  `invoke_local_llm` (`copilot_bridge.py:190`). Nada de lo que procesa sale de la máquina.
- **Arnés / HarnessFlagsPanel:** registro central de flags (`services/harness_flags.py`)
  con UI genérica; TODA config de operador se activa/apaga ahí (regla de la casa).
- **Flag curada default ON:** flag cuyo default efectivo es True; exige el patrón
  triple §3.6 (FlagSpec `default=True` + key en `_CURATED_DEFAULTS_ON` + config
  `"true"`), vía canónica desde el Plan 63.
- **Snapshot forense:** dict de `GET /api/diag/execution/<id>` con estado DB +
  manifest + heartbeat + historia de transiciones + diagnosis determinista.
- **Doctor de sección (Plan 104):** análisis IA de una sección del panel DevOps
  despachado a un runtime (Claude/Codex/Copilot) vía `agent_runner.run_agent`.
- **Doctor de pipelines (Plan 96):** clasificador determinista de jobs de CI
  fallidos con snippet de log, sin LLM.
- **HITL:** human-in-the-loop; acá: la IA SOLO analiza y propone en markdown, el
  operador decide; se refuerza por instrucción de prompt (`HITL_RULES`).
- **Ejecución interna auditora:** fila `AgentExecution` con ticket ancla de
  `ado_id` negativo que deja rastro de cada invocación IA (patrón Plan 90/104/106).
- **Ratchet:** meta-test que obliga a registrar todo archivo de test backend nuevo
  en `run_harness_tests.sh`/`.ps1`.

### Orden de implementación (estricto)

1. **F0** flags default ON + set curado + help + arista requires + ratchet (todo lo
   demás depende del gating; el patrón triple §3.6 se valida acá con tests antes de
   escribir una sola feature).
2. **F1** refactor snapshot diag (independiente de F0, pero va antes de F2/F3).
3. **F2** núcleo puro error_analysis.
4. **F3** endpoint C1 + exclusión anti-recursión. ← *primer valor entregable: C1 completo por API*
5. **F4** refactor contexto doctor.
6. **F5** endpoint C3 + health key (conjunción H5). ← *segundo valor entregable: C3 completo por API*
7. **F6** frontend C1+C3 (última fase obligatoria).
8. **F7** C2 explicar fallo CI (OPCIONAL; si se difiere, declararlo en el reporte de implementación).

### Definición de Hecho (DoD) global

- [ ] Los 6 KPIs de §1 verdes con sus tests nombrados.
- [ ] Todos los archivos de test nuevos (`test_plan127_flags.py`,
  `test_plan127_diag_snapshot.py`, `test_plan127_error_analysis_core.py`,
  `test_plan127_error_analysis_api.py`, `test_plan127_doctor_context.py`,
  `test_plan127_devops_doctor_local.py` y, si F7 entra,
  `test_plan127_ci_explain_local.py`) verdes corriendo POR ARCHIVO con el venv
  real: `.venv\Scripts\python -m pytest tests\<archivo> -q` desde
  `Stacky Agents/backend`.
- [ ] Registrados en `HARNESS_TEST_FILES` (sh + ps1, alfabético); meta-test del
  ratchet sin fallas nuevas.
- [ ] **Default ON verificado (H1/H2):** sin env vars, ambos atributos de config
  valen `True`; ambas FlagSpec con `default=True`; ambas keys en
  `_CURATED_DEFAULTS_ON`; `test_harness_flags.py` sin fallas nuevas
  (`test_default_known_only_for_curated` y `test_curated` de `:619-634` verdes).
- [ ] `backend/harness_defaults.env` SIN líneas `=false` para las 2 keys nuevas
  (test negativo F0); el generador NO se corrió (§3.11).
- [ ] No-regresión verde SIN modificar los archivos existentes:
  `test_diag_endpoint.py`, `test_plan104_section_doctor.py`,
  `test_plan96_doctor_endpoint.py`, `test_plan106_analyze_code_api.py`,
  `test_plan117_insights_api.py`, `test_plan117_insights_sweep.py`,
  `test_plan87_devops_flag.py`, `test_harness_flags.py` (salvo el bloque nuevo del
  set curado), `test_harness_flags_requires.py` (salvo la arista nueva).
- [ ] Frontend: `npx tsc --noEmit` = 0 errores; vitest de los modelos puros verde.
- [ ] **Con las flags APAGADAS A MANO** (monkeypatch en tests; UI del arnés o env
  var en vivo): `POST /api/llm/executions/1/error-analysis`,
  `POST /api/devops/sections/pipeline/doctor/local` (y F7 si entra) devuelven 404,
  y `GET /api/devops/health` expone `local_doctor_enabled: false`. Con los
  defaults (ON), los endpoints responden y el único delta observable del sistema
  existente es esa key nueva del health (KPI-6).
- [ ] Ningún secreto de prueba plantado aparece en claro en prompts capturados ni
  en `metadata_json`/`output` persistidos (tests de KPI-5).
- [ ] `copilot_bridge.py`, `services/llm_router.py`, `services/local_insights.py`
  (salvo el frozenset), `egress_policies.py`: SIN cambios de lógica.
- [ ] Commit quirúrgico: `git diff --cached --name-only` contiene SOLO archivos
  listados en este plan; WIP ajeno del working tree intacto.
- [ ] Encabezado de estado de este documento actualizado a IMPLEMENTADO con fecha
  y commit (regla de la casa: sincronizar estado del plan en el doc).
