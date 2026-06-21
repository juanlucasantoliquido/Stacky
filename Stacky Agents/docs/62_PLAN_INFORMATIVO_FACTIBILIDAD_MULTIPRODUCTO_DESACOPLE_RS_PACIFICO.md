> # ⛔️ BANNER — DOCUMENTO INFORMATIVO / EXPLORATORIO — **NO IMPLEMENTAR** ⛔️
>
> **Este NO es un plan de trabajo.** Es un **análisis prospectivo** que responde una
> pregunta estratégica del operador. **NINGUNA** fase de este documento debe ser
> construida por `implementar-plan-stacky`, por `supervisar-implementaciones-planes`,
> ni por nadie todavía.
>
> - La pipeline (proponer → criticar → implementar → supervisar) **debe IGNORAR este
>   archivo** como trabajo pendiente.
> - Las "fases F0..Fn" de abajo describen trabajo **HIPOTÉTICO FUTURO**, solo para
>   dimensionar esfuerzo/riesgo. No son tareas aprobadas.
> - Si en el futuro se decide ejecutar alguna línea, deberá re-proponerse como un plan
>   **propio y numerado** que pase por el juez (`criticar-y-mejorar-plan`) antes de tocar
>   código.
> - El `ledger.json` de supervisión NO debe registrar este documento.

---

# Plan 62 (INFORMATIVO) — ¿Stacky es solo para RS/Pacífico o sirve para cualquier producto? Factibilidad multi-producto y desacople

**Tipo:** Documento informativo/exploratorio (no ejecutable).
**Pregunta que responde:** ¿Stacky es factible **solo** para RS/Pacífico, o se puede
implementar para **cualquier otro producto/cliente**? ¿Qué **faltaría** para hacerlo
multi-producto?
**Fecha de análisis:** 2026-06-21.
**Método:** auditoría de evidencia real del repo (archivo:línea), sin especulación.

---

## 1. Resumen ejecutivo (TL;DR)

**Stacky NO está atado a RS/Pacífico a nivel de arquitectura.** El sustrato multi-cliente
ya existe y está en uso: hay un `project_manager.py` con proyectos en disco, **dos clientes
reales ya onboardeados** (`projects/RSPACIFICO/` y `projects/RSSICREA/`), prompts de agente
**explícitamente cliente-agnósticos**, y soporte de **tres trackers** (Azure DevOps, Jira,
Mantis) vía plantillas de `client_profile`.

El acoplamiento residual a Pacífico es **superficial** (defaults de fallback, ejemplos
embebidos en prompts, fixtures/docs), **no estructural**.

El límite verdadero NO es "RS vs otro cliente". Es **el TIPO de producto**: el modelo
mental completo de Stacky asume el dominio _"app legacy/batch con catálogo de procesos →
épica grounded en ese catálogo → tickets en un tracker"_. Para **otro cliente del mismo
tipo de producto** (otra app legacy/batch con su propio catálogo y tracker) Stacky es
**factible HOY con configuración, casi sin código nuevo**. Para **cualquier producto de
software arbitrario** (p. ej. un SaaS web moderno, una librería, un microservicio cloud sin
"catálogo de procesos batch") faltaría re-modelar el grounding y los contratos de salida.

---

## 2. Diagnóstico de acoplamiento a RS/Pacífico (evidencia)

Cada hallazgo está clasificado: **[GENÉRICO]** ya parametrizable por configuración /
`client_profile` / `projects/`; **[ACOPLADO-BLANDO]** sesgo o default que conviene limpiar
pero no bloquea; **[ACOPLADO-DURO]** habría que extraer código para portarlo.

### 2.1 Catálogo de procesos (`process_catalog`, Mul2Bane/IncHost/RSCore/RsExtrae)

- **Evidencia:** los nombres de proceso Pacífico (`Mul2Bane`, `IncHost`, `RSCore`,
  `RsExtrae`, `RSActBD`) **NO aparecen en ningún módulo de runtime** (`backend/services`,
  `backend/api`, `backend/harness`). Solo aparecen en **tests, fixtures y docs**:
  `backend/evals/catalog_diff_fixtures/*.json`, `backend/tests/test_golden_catalog_diff.py`,
  `backend/tests/test_epic_gate.py`, `docs/44`, `docs/45`, `docs/50`.
- **Cómo se consume realmente:** el catálogo es **dato** del perfil de cliente, editable
  por UI (planes 42/45). `process_catalog` se referencia desde
  `backend/services/context_enrichment.py`, `backend/services/grounding_observatory.py`,
  `backend/harness/epic_gate.py`, `backend/api/client_profile.py` — todos lo leen como
  estructura inyectada, no lo hardcodean.
- **Clasificación: [GENÉRICO].** El catálogo es configuración por cliente. Cambiar de
  cliente = cargar otro catálogo en su `client_profile`. Los procesos Pacífico viven en
  fixtures de test (correcto: son golden-set de Pacífico, no código de producción).

### 2.2 Grounding / `technical_master`

- **Evidencia:** `technical_master` se referencia en `context_enrichment.py`,
  `project_autoprofile.py`, `client_profile.py` y los prompts de agente como **bloque de
  contexto inyectado** ("client-profile"). No hay un `technical_master` de Pacífico
  hardcodeado en runtime.
- **Clasificación: [GENÉRICO]** en mecánica (se inyecta por perfil), pero con un
  **supuesto de dominio [ACOPLADO-DURO a nivel conceptual]**: el grounding asume que el
  producto **tiene** un catálogo de procesos y un master técnico de ese estilo. Un producto
  sin esa forma (un SaaS web) no llena estos campos de forma natural.

### 2.3 Integración con el tracker (ADO org/proyecto/área)

- **Evidencia:** `backend/services/ado_client.py:239-240` usa como **fallback**
  `config.ADO_ORG or "UbimiaPacifico"` y `config.ADO_PROJECT or "Strategist_Pacifico"`.
  PERO la resolución real pasa **antes** por `_resolve_active_project_defaults()`
  (`ado_client.py:121-161`), que lee la org/proyecto/auth del **proyecto activo** vía
  `project_manager` (`get_active_project`, `get_project_config`, `find_project_for_tracker`).
- **Evidencia adicional:** `backend/config.py:445-446` define `ADO_ORG`/`ADO_PROJECT` como
  `os.getenv(..., "")` — vacío por defecto; los valores Pacífico solo aparecen como
  **último recurso** literal en `ado_client.py`.
- **Multi-tracker real:** `backend/services/client_profile_defaults/` tiene
  `azure_devops.json`, `jira.json`, `mantis.json`. `project_manager.py` tiene
  `initialize_ado_project()` **y** `initialize_jira_project()` (líneas 270, 317).
- **Clasificación: [ACOPLADO-BLANDO].** La org/proyecto reales se resuelven por proyecto
  activo; lo único atado a Pacífico es el **string de fallback** en `ado_client.py:239-240`.

### 2.4 Prompts de los agentes (`.agent.md`)

- **Evidencia (cliente-agnósticos por diseño):**
  - `TechnicalAnalyst.v2.agent.md:2` — _"Analista Técnico **cliente-agnóstico** v2. Lee el
    perfil del cliente desde el context block 'client-profile'… **NO hardcodea valores
    Pacífico**."_ y línea 174 _"No hardcodear valores Pacífico. Todo lo específico viene del
    `client-profile`."_
  - `Developer.agent.md:2` — _"Developer **cliente-agnóstico**… Funciona contra **cualquier
    proyecto Pacífico / CREA / B2Impact / RSSICREA / etc.**"_
  - `FunctionalAnalyst.agent.md:301` — _"No hardcodear valores Pacífico/cliente. Si
    necesitás algo que no está en `client-profile`, reportarlo como gap."_
- **Acoplamiento blando residual:** los mismos prompts **embeben ejemplos Pacífico** como
  ilustración: `FunctionalAnalyst.agent.md:75` (_"Ej. real Pacífico: el punto de entrada de
  la carga es `mul2bane`…"_), `Developer.agent.md:138` (_"Ejemplo (Pacífico ADO):"_).
- **Acoplamiento de transición:** `TechnicalAnalyst.v2.agent.md:231` menciona el cutover
  del legacy `TechnicalAnalyst.agent.md` y `TechnicalAnalystPacifico.legacy.agent.md`.
- **Clasificación: [ACOPLADO-BLANDO].** Diseño agnóstico correcto; quedan **ejemplos
  Pacífico** que sesgan al modelo y un prompt legacy de transición todavía presente.

### 2.5 Rutas de datos y outputs

- **Evidencia:** la DB viva y los outputs **no se hardcodean a Pacífico en runtime**: las
  rutas de proyecto se resuelven por `project_manager.py` (`PROJECTS_DIR`,
  `data_dir()/active_project.json`, `validate_workspace_root()`, `validate_docs_paths()`).
- Las rutas físicas tipo `DeployStackyAgents\data` y `C:\desarrollo\…\RSPACIFICO\…\outputs`
  pertenecen al **deploy del operador**, no al código fuente versionado.
- **Clasificación: [GENÉRICO].** `workspace_root`, `docs_paths` y `agents_dir` son por
  proyecto (`initialize_project()` los valida y persiste por cliente).

### 2.6 Sustrato multi-proyecto ya operativo

- **Evidencia:** `project_manager.py` ofrece `get_all_projects()`, `get_active_project()`,
  `set_active_project()`, `initialize_project()`, `initialize_ado_project()`,
  `initialize_jira_project()`, `find_project_for_tracker()`, `get_project_pinned_agents()`,
  `set_agent_workflow_config()`.
- **Dos clientes reales ya en disco:** `backend/projects/RSPACIFICO/` **y**
  `backend/projects/RSSICREA/` (cada uno con `config.json` y `auth/`).
- **Clasificación: [GENÉRICO].** El multi-cliente no es teórico: ya hay un segundo cliente
  (`RSSICREA`) conviviendo con Pacífico.

### 2.7 Tabla-resumen de acoplamiento

| Área | Evidencia | Clasificación |
|------|-----------|---------------|
| `process_catalog` (Mul2Bane…) | solo en fixtures/tests/docs; runtime lo lee como dato | **[GENÉRICO]** |
| `technical_master` / grounding | inyectado por perfil, pero asume "producto con catálogo de procesos" | **[GENÉRICO]** mecánica / **[ACOPLADO-DURO]** conceptual |
| ADO org/proyecto | resuelto por proyecto activo; fallback `"UbimiaPacifico"/"Strategist_Pacifico"` en `ado_client.py:239-240` | **[ACOPLADO-BLANDO]** |
| Trackers | plantillas ADO + Jira + Mantis; `initialize_jira_project()` existe | **[GENÉRICO]** |
| Prompts `.agent.md` | declarados cliente-agnósticos; ejemplos Pacífico embebidos | **[ACOPLADO-BLANDO]** |
| Rutas data/outputs | por proyecto (`workspace_root`, `docs_paths`); rutas físicas = deploy operador | **[GENÉRICO]** |
| Sustrato multi-proyecto | `project_manager.py` + `projects/RSPACIFICO` + `projects/RSSICREA` | **[GENÉRICO]** |

---

## 3. Veredicto de factibilidad (honesto)

**Hay que distinguir DOS preguntas distintas:**

### 3.1 ¿Multi-cliente dentro del MISMO tipo de producto? → **SÍ, factible HOY, casi sin código.**

Otra app legacy/batch con su propio catálogo de procesos y su tracker (ADO/Jira/Mantis)
**ya está soportada**: se crea un `projects/<NUEVO>/`, se carga su `client_profile`
(catálogo + technical_master) por UI, se setea su auth de tracker y se marca activo. El
prompt de los agentes ya es agnóstico y lee todo del `client-profile`. **Prueba viviente:**
`RSSICREA` coexiste con `RSPACIFICO`. El residual es limpieza cosmética (defaults de
fallback y ejemplos Pacífico en prompts), no construcción.

### 3.2 ¿Cualquier producto de software ARBITRARIO? → **NO sin trabajo conceptual.**

El valor diferencial de Stacky (grounding, epic_gate, catalog_diff, descomposición
épica→procesos) está **modelado alrededor de "catálogo de procesos batch"**. Un producto
que no tenga esa forma (SaaS web moderno, microservicios, librería, app móvil) puede usar
Stacky como orquestador de tickets, **pero pierde el grounding** que lo hace bueno, porque
no hay catálogo de procesos contra el cual aterrizar la épica. Para ese salto faltaría
**generalizar el modelo de grounding** de "catálogo de procesos" a "modelo de dominio
configurable" (ver gaps F2/F3).

### 3.3 Conclusión de una línea

> Stacky **no es solo para RS/Pacífico**: es **multi-cliente HOY** para productos del mismo
> tipo (legacy/batch con catálogo + tracker), con sustrato ya probado por `RSSICREA`. Para
> productos arbitrarios faltaría **abstraer el grounding**, que hoy asume el dominio de
> procesos batch. El acoplamiento a "Pacífico" es cosmético; el acoplamiento real es al
> **tipo de producto**, no al cliente.

---

## 4. Gap analysis — trabajo HIPOTÉTICO (NO IMPLEMENTAR)

> ⚠️ Las fases siguientes son **dimensionamiento**, no tareas aprobadas. Ordenadas por
> esfuerzo/riesgo creciente. Cada una respetaría los rieles duros (sección 5). **Ninguna
> debe ejecutarse desde este documento.**

### F0 — Limpieza de acoplamiento blando (esfuerzo: bajo / riesgo: bajo)

- **Objetivo hipotético:** eliminar los strings y ejemplos Pacífico residuales para que el
  default sea neutro.
- **Dónde tocaría:** `backend/services/ado_client.py:239-240` (quitar fallback literal
  `"UbimiaPacifico"/"Strategist_Pacifico"` → fallar ruidoso o pedir proyecto activo);
  ejemplos Pacífico en `FunctionalAnalyst.agent.md:75`, `Developer.agent.md:138`
  (parametrizar como "ejemplo del client-profile activo" en vez de Pacífico literal).
- **Criterio binario hipotético:** `grep -ri "pacifico\|ubimia\|mul2bane" backend/services
  backend/api backend/harness` devuelve **0** coincidencias en runtime (solo quedan en
  tests/fixtures/docs).
- **Test nombrado hipotético:** `test_no_client_hardcode_in_runtime.py` (centinela que
  falla si aparece un literal de cliente en `services/`, `api/`, `harness/`).
- **Flag:** ninguno (limpieza). **Trabajo del operador: ninguno.**
- **Runtimes:** sin impacto diferencial (es texto/prompt común a los 3).

### F1 — Onboarding de cliente nuevo asistido por UI (esfuerzo: medio / riesgo: bajo)

- **Objetivo hipotético:** un wizard que cree `projects/<NUEVO>/` (config + auth + catálogo
  vacío editable) sin tocar disco a mano, reusando `initialize_project()` /
  `initialize_jira_project()` ya existentes.
- **Dónde tocaría:** nuevo endpoint sobre `backend/api/projects.py` + pantalla de alta en
  frontend reusando `ClientProfileEditor.tsx`.
- **Criterio binario hipotético:** crear un cliente nuevo desde UI, marcarlo activo y correr
  un brief sin editar archivos manualmente.
- **Test nombrado hipotético:** `test_project_onboarding_wizard.py`.
- **Flag:** `STACKY_PROJECT_ONBOARDING_UI_ENABLED` (default **off**).
- **Trabajo del operador:** opt-in; reemplaza pasos manuales actuales, no agrega carga.
- **Runtimes:** agnóstico (es backend + UI, no toca runners).

### F2 — Abstracción del modelo de grounding (esfuerzo: alto / riesgo: medio)

- **Objetivo hipotético:** generalizar el grounding de "catálogo de procesos" a un
  **"modelo de dominio" configurable por cliente** (p. ej. `domain_model.kind =
  "process_catalog" | "feature_map" | "service_map"`), para soportar productos no-batch.
- **Dónde tocaría (conceptual):** `context_enrichment.py`, `grounding_observatory.py`,
  `harness/epic_gate.py`, `harness/regression_goldens.py` — donde hoy asumen
  `process_catalog`.
- **Criterio binario hipotético:** un cliente con `domain_model.kind="feature_map"` genera
  épicas grounded sin un catálogo de procesos, y el epic_gate las valida contra su modelo.
- **Test nombrado hipotético:** `test_domain_model_grounding_kinds.py` (cubre los 3 kinds).
- **Flag:** `STACKY_DOMAIN_MODEL_ABSTRACTION_ENABLED` (default **off**; fallback al
  `process_catalog` actual si OFF → backward-compatible con Pacífico).
- **Trabajo del operador:** ninguno si OFF; opt-in al definir un kind nuevo.
- **Runtimes:** los 3 reciben el mismo bloque de contexto; sin divergencia.

### F3 — Plantillas de agente neutrales por tipo de producto (esfuerzo: alto / riesgo: medio)

- **Objetivo hipotético:** juego de `.agent.md` parametrizables por `domain_model.kind`, de
  modo que los ejemplos y el vocabulario los provea el perfil, no el prompt.
- **Dónde tocaría:** `backend/Stacky/agents/*.agent.md` + el inyector de contexto que ya
  arma el bloque `client-profile`.
- **Criterio binario hipotético:** mismo agente produce salida correcta para un cliente
  batch y para uno feature-map cambiando solo el perfil.
- **Test nombrado hipotético:** `test_agent_prompts_domain_neutral.py`.
- **Flag:** cubierto por F2.
- **Runtimes:** paridad obligatoria (mismo prompt para los 3).

### F4 — Aislamiento de datos multi-cliente (esfuerzo: alto / riesgo: alto — ver sección 5)

- **Objetivo hipotético:** garantizar que outputs/auth/DB de un cliente no se filtren a
  otro al cambiar de proyecto activo (hoy mono-operador, un solo activo a la vez).
- **Dónde tocaría:** `project_manager.py` (resolución de `active`), rutas de outputs,
  manejo de auth por proyecto.
- **Criterio binario hipotético:** correr con cliente A no deja artefactos accesibles desde
  el contexto de cliente B; los auth nunca se mezclan.
- **Test nombrado hipotético:** `test_project_isolation.py`.
- **Flag:** N/A (propiedad de seguridad, no feature).
- **Riesgo:** ver 5.2 — esto **no** es RBAC ni multiusuario; es aislamiento de datos para
  el **mismo** operador conmutando clientes.

---

## 5. Riesgos y supuestos del salto multi-producto

### 5.1 Supuesto de dominio (el riesgo real)

El mayor riesgo no es técnico sino **de modelo**: gran parte del valor (grounding,
epic_gate, catalog_diff) presupone "producto = catálogo de procesos batch". Forzar Stacky a
productos arbitrarios **sin** F2/F3 degrada la calidad (épicas sin grounding) — violaría
"no degradar". Por eso F2 es el verdadero parteaguas, no el desacople de strings.

### 5.2 Mono-operador sin auth (riel duro)

Stacky es mono-operador y **no tiene auth real** (`current_user` es un header sin validar).
El salto multi-cliente **NO** debe interpretarse como multiusuario/RBAC — eso está prohibido
por los rieles. El "aislamiento" de F4 es **aislamiento de datos por proyecto para un único
operador que conmuta de cliente**, no control de acceso entre personas. Confundir ambos
sería construir teatro de seguridad.

### 5.3 Human-in-the-loop

Onboarding de cliente nuevo y cambio de `domain_model` deben seguir siendo **decisión del
operador** (opt-in, default off). Nada de auto-detectar y cambiar de cliente solo.

### 5.4 Paridad de 3 runtimes

Todo lo conceptual (grounding, prompts, perfil) viaja en el bloque de contexto común a
Codex / Claude Code / Copilot, así que la paridad se preserva por construcción. El riesgo de
divergencia aparecería solo si alguna abstracción se cableara en un runner específico — a
evitar.

### 5.5 Backward-compatibility con Pacífico

Cualquier abstracción (F2/F3) debe degradar al comportamiento actual cuando su flag está
OFF, para no romper `RSPACIFICO`/`RSSICREA` ya en producción.

---

## 6. Fuera de scope

- RBAC, login, multiusuario, roles (prohibido por los rieles; Stacky es mono-operador).
- Implementar **cualquiera** de las fases F0..F4 (este documento es informativo).
- Migrar a Pacífico/RSSICREA a un nuevo modelo (no hay necesidad; funcionan).
- Soporte de trackers nuevos más allá de ADO/Jira/Mantis ya existentes.

---

## 7. Glosario

- **`client_profile`** — perfil de cliente (catálogo de procesos, technical_master,
  defaults de tracker) inyectado como bloque de contexto a los agentes; editable por UI.
- **`process_catalog`** — lista canónica de procesos del cliente (en Pacífico: Mul2Bane,
  IncHost, RSCore, RsExtrae) usada para aterrizar (grounding) las épicas.
- **`technical_master`** — master técnico del cliente que da contexto de implementación.
- **grounding** — anclar la salida del agente a hechos verificables del cliente para evitar
  alucinación.
- **`project_manager.py`** — sustrato multi-proyecto: crea/activa/resuelve `projects/<X>/`.
- **runtime / runner** — motor de ejecución del agente: Codex CLI, Claude Code CLI o GitHub
  Copilot Pro.
- **riel duro** — restricción innegociable (mono-operador, human-in-the-loop, paridad de 3
  runtimes, no degradar).

---

## 8. Orden de implementación (SI alguna vez se aprobara — hoy NO)

1. F0 (limpieza de acoplamiento blando) — barato, sin riesgo.
2. F1 (onboarding por UI) — habilita probar un 3er cliente fácil.
3. F2 (abstracción de grounding) — parteaguas para productos no-batch.
4. F3 (prompts neutrales por dominio) — depende de F2.
5. F4 (aislamiento de datos) — solo si se opera más de un cliente intensivamente.

## 9. Definición de Hecho (de ESTE documento informativo)

- [x] Diagnóstico de acoplamiento con evidencia archivo:línea y clasificación
      genérico/acoplado.
- [x] Veredicto de factibilidad honesto, distinguiendo "mismo tipo de producto" vs
      "producto arbitrario".
- [x] Gap analysis F0..F4 ordenado por esfuerzo/riesgo, con criterios binarios y tests
      nombrados (hipotéticos).
- [x] Riesgos y supuestos del salto, respetando rieles duros.
- [x] Banner NO-IMPLEMENTAR visible. **Este documento no genera trabajo para la pipeline.**
