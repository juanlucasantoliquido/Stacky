# Stacky Agents QA UAT — Roadmap QUINTA Parte: Navegación Certera, Determinística y Verificable

**Producto:** Stacky / Stacky Agents — QA UAT Agent  
**Area:** Navegacion robusta, WebForms ASP.NET, Playwright, contratos de estrategia, evidencia forense  
**Version del roadmap:** v5.0  
**Fecha:** 2026-05-11  
**Autor:** Arquitecto Senior QA Automation / SDET — Stacky Agents  
**Audiencia:** Tech Lead, QA Automation Lead, SDET, Backend, DevOps, Operadores de Stacky Agents  
**Continuacion de:**
- [PRIMERA PARTE](../../../Tools/Stacky/Stacky%20tools/QA%20UAT%20Agent/roadmap_qa_uat_agent_big_tech.md) — Plataforma estratificada, preflight, fingerprint, evidence bundle
- [SEGUNDA PARTE](../../../Tools/Stacky/Stacky%20tools/QA%20UAT%20Agent/roadmap_qa_uat_agent_big_tech_SEGUNDA_PARTE.md) — Gestion activa de datos de prueba, seed SQL seguro, oracle
- [TERCERA PARTE](../../../Tools/Stacky/Stacky%20Agents%20QA%20UAT%20roadmap%20tercera%20parte.md) — Pipeline gobernado por gates, run_id, contratos duros, flake governance
- [CUARTA PARTE](../../../Tools/Stacky/Stacky%20Agents%20QA%20UAT%20roadmap%20CUARTA%20parte.md) — Contratos de navegacion por pantalla, navigation_contracts.yml, strategy_resolver, navigation_driver

---

## 0. Lectura ejecutiva

Las cuatro partes anteriores de este roadmap construyeron la plataforma de calidad estratificada de Stacky: fingerprint de deploy, evidence bundle, gates de datos, oracle, flake governance, contratos de navegacion declarativos y un resolver de estrategia. Sin embargo, subsiste un defecto estructural critico que ninguna de esas partes resolvio de raiz:

**El template `playwright_test.spec.ts.j2` navega con `page.goto(TARGET_SCREEN)` en `beforeEach` (linea 381) y con `page.goto(pantalla)` en el cuerpo del test (linea 418), ignorando por completo el resultado del `navigation_strategy_resolver.py` y el contrato `direct_entry_allowed: false` de `navigation_contracts.yml`.**

Esto significa que, incluso con todos los controles de la Parte IV activados, el spec generado para `FrmDetalleClie.aspx` sigue ejecutando:

```typescript
// linea 381 del template — beforeEach
await page.goto(`${BASE_URL}FrmDetalleClie.aspx`, { waitUntil: 'domcontentloaded', timeout: 20_000 });

// linea 418 del template — cuerpo del test (SETUP)
await page.goto(`${BASE_URL}FrmDetalleClie.aspx`, { waitUntil: 'domcontentloaded' });
```

Estas dos llamadas independientes sin contexto de sesion causan crash del app pool de ASP.NET porque `FrmDetalleClie.aspx` requiere `CLCOD` en QueryString y ViewState emitido por `FrmBusqueda.aspx`. La pantalla no puede construir su contexto internamente cuando se llega por `goto()` directo.

Esta quinta parte propone el plan mas robusto posible para convertir la navegacion del QA UAT Agent en un sistema **certera, deterministica, verificable y completamente trazable**, eliminando para siempre la posibilidad de que el generator produzca `goto()` directo contra pantallas que no lo permiten.

El cambio de mentalidad central es:

> La navegacion no es un detalle de implementacion del spec. La navegacion es un **artefacto de primera clase** declarado en contratos, resuelto antes de la generacion, codificado en un `navigation_plan` tipado, ejecutado por helpers especializados y verificado por assertions de llegada antes de cualquier paso de negocio.

---

## 1. Diagnostico actual — referencias exactas al codigo

### 1.1. El problema raiz — dos `goto()` en el template

Archivo: `Tools/Stacky/Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2`

**Punto de falla 1 — `beforeEach` (linea 381):**

```typescript
await page.goto(`${BASE_URL}${TARGET_SCREEN}`, { waitUntil: 'domcontentloaded', timeout: 20_000 });
```

`TARGET_SCREEN` se renderiza como `{{ pantalla }}`, que para ticket 120/RF-007 es `FrmDetalleClie.aspx`. Este `goto()` directo viola `direct_entry_allowed: false` declarado en `navigation_contracts.yml` (linea 87-88 de ese archivo).

**Punto de falla 2 — cuerpo del test, bloque SETUP (linea 418):**

```typescript
await page.goto(`${BASE_URL}{{ pantalla }}`, { waitUntil: 'domcontentloaded' });
```

Segunda ocurrencia del mismo error. Si el `beforeEach` no crashea (porque el app pool se recupera entre tests), el cuerpo lo provoca de nuevo.

**Punto de falla 3 — accion `navigate` en steps del escenario (linea 492):**

```typescript
await page.goto(`${BASE_URL}{{ step.target }}`, { waitUntil: 'domcontentloaded' });
```

Cualquier step con `accion: navigate` genera un `goto()` incondicional. No verifica si `step.target` admite entrada directa.

### 1.2. El desconexion entre el resolver y el generator

Archivo: `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_strategy_resolver.py`

El resolver existe y funciona correctamente. Produce decisiones como:

```json
{
  "decision": "ALLOW_GENERATION",
  "strategy": "human_path",
  "path_id": "open_from_busqueda",
  "entrypoint": "FrmBusqueda.aspx",
  "target_screen": "FrmDetalleClie.aspx",
  "requires_data": ["CLCOD"],
  "data_available": true
}
```

Pero esta decision **no llega al generator** (`playwright_test_generator.py`) como parametro que modifique la logica de renderizado del template. El generator simplemente renderiza el `pantalla` del escenario sin considerar la estrategia de navegacion resuelta.

### 1.3. El `navigation_driver.py` no esta integrado en el template

Archivo: `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_driver.py`

`NavigationDriver` tiene implementados correctamente los tres mecanismos de navegacion WebForms (`via_form_submit`, `via_dopostback`, `via_link_click`) con retry y backoff. Pero el template no lo usa para la navegacion inicial. Solo usa el helper TypeScript `navigateViaFormSubmit` para steps con `accion: navigate_webforms`, no para la navegacion de contexto inicial.

### 1.4. La validacion de llegada es incompleta

El template (lineas 382-398) valida la URL despues del `goto()`, pero esta validacion es post-hoc: si el `goto()` provoco crash del app pool, la pagina cargada es la de error ASP.NET (`<title>Runtime Error</title>`), no `FrmDetalleClie.aspx`. La validacion de URL detecta el problema, pero ya es demasiado tarde: el crash ocurrio.

### 1.5. El `playbook_router.py` no esta conectado al pipeline de navegacion

Archivo: `Tools/Stacky/Stacky tools/QA UAT Agent/playbook_router.py`

Existe un router de playbooks que busca playbooks preconstruidos para escenarios, pero en este momento no existen playbooks en `cache/playbooks/` (el directorio no contiene archivos `.yml` ni `.json`). El router tiene la infraestructura pero sin contenido navegable.

### 1.6. Resumen de brechas criticas

| ID | Brecha | Archivo | Severidad |
|---|---|---|---|
| B-01 | `beforeEach` usa `goto(TARGET_SCREEN)` incondicional | `playwright_test.spec.ts.j2:381` | P0 |
| B-02 | Cuerpo del test usa `goto(pantalla)` incondicional | `playwright_test.spec.ts.j2:418` | P0 |
| B-03 | Accion `navigate` usa `goto()` sin verificar el contrato | `playwright_test.spec.ts.j2:492` | P0 |
| B-04 | El resolver no pasa `navigation_plan` al generator | `playwright_test_generator.py` | P0 |
| B-05 | No existe `arrival_validator` post-navegacion obligatorio | template + generator | P1 |
| B-06 | Los playbooks no tienen navegacion ejecutable | `cache/playbooks/` vacio | P1 |
| B-07 | `navigation_contracts.yml` no tiene schema de version | `navigation_contracts.yml` | P2 |
| B-08 | No hay evento `navigation_step_*` en `execution.jsonl` | todos los modulos | P1 |
| B-09 | `session_expiry_detector` no existe como modulo independiente | — | P2 |
| B-10 | La accion `navigate_webforms` no verifica assertions de llegada | template:499-527 | P1 |

---

## 2. Principios de diseno de navegacion

Estos principios son no negociables para cualquier cambio en el sistema de navegacion.

### Principio 1 — La navegacion es un contrato, no un detalle

Ningun spec puede ser generado sin un `navigation_plan` explicito, tipado y validado contra schema. El plan no es un comentario: es el conjunto de instrucciones que el spec ejecuta. Si el plan no existe o es invalido, el generator se bloquea.

### Principio 2 — El contrato decide, no el generator

El `navigation_strategy_resolver.py` es la unica fuente de verdad sobre como llegar a una pantalla. El generator consume su output. Nunca infiere la estrategia por su cuenta.

### Principio 3 — Zero `goto()` contra pantallas de sesion

`page.goto(screen)` solo es valido cuando `navigation_contracts.yml` declara `direct_entry_allowed: true` para esa pantalla. Para cualquier otra pantalla, el template genera el mecanismo correcto (human path, deeplink, form submit) segun la estrategia resuelta.

### Principio 4 — Llegar no es suficiente: hay que verificar que se llego bien

Despues de cada paso de navegacion (no solo el final), el spec ejecuta assertions de llegada:
- URL contiene el nombre esperado de la pantalla
- DOM marker unico de la pantalla esta visible
- No hay `<title>Runtime Error</title>` ni URL `Errors.aspx`
- No hay redirect a `FrmLogin.aspx`

Si alguna assertion falla, el test termina con categoria `NAV` y motivo clasificado, no con timeout generico.

### Principio 5 — La sesion es un artefacto verificado, no asumido

Antes de ejecutar cualquier navegacion que requiera sesion activa, el spec verifica que el `storageState` existe y es reciente. Si no existe o es mas antiguo que el TTL configurado, el test bloquea con categoria `ENV` y accion humana requerida: re-ejecutar `global.setup.ts`.

### Principio 6 — Cada paso de navegacion es observable

Cada paso de navegacion emite tres eventos en `execution.jsonl`: `navigation_step_started`, `navigation_step_completed` o `navigation_step_failed`. Estos eventos contienen: numero de paso, metodo usado, URL antes, URL despues, tiempo transcurrido, assertions verificadas y error_code si fallo.

### Principio 7 — Fail early, fail classified

Si la navegacion falla, la categoria del fallo es deterministica:
- `NAV` — la pantalla existe pero no se pudo llegar
- `ENV` — la sesion expiro, el servidor no responde o el app pool caido
- `DATA` — faltan datos para ejecutar el human path
- `PIP` — la estrategia de navegacion no es compatible con el lane

Nunca se debe reportar `NAV_TIMEOUT` como diagnostico final si la causa real es `ENV` (app pool caido) o `DATA` (CLCOD faltante).

### Principio 8 — El humano aprueba la estrategia no estandar

Si el operador quiere usar deeplink en un lane que requiere human path (o viceversa), debe haber un override explicito en la configuracion del run, auditado en `execution.jsonl`. El sistema nunca silencia esta decision.

### Principio 9 — Los playbooks son contratos ejecutables, no documentacion

Un playbook es un archivo JSON con schema validado que contiene: entrypoint, pasos de navegacion tipados, assertions de llegada y campos parametrizables. El generator lo usa como fuente primaria de navegacion. Si existe un playbook para la pantalla y el escenario, se usa; si no existe, el generator busca el human_path del contrato; si tampoco existe, bloquea.

### Principio 10 — Anti-fragil ante actualizaciones de la aplicacion

Cuando la aplicacion cambia (nuevo control en una pantalla, cambio de URL, nueva pantalla intermedia), el sistema detecta el cambio porque las assertions de llegada fallan con precision. El fallo es diagnosticado como `NAV ARRIVAL_ASSERTION_FAILED` con evidencia exacta de que assertion fallo, en vez de un timeout generico.

---

## 3. Arquitectura objetivo

### 3.1. Flujo de resolucion de navegacion (nuevo)

```
ticket.json
    |
    v
[QA Intake]
    |
    v
[navigation_strategy_resolver.py]
    |-- Lee navigation_contracts.yml
    |-- Verifica lane, available_data, direct_entry_allowed
    |-- Produce navigation_decision.json
    |
    +---> BLOCKED (DATA/NAV/PIP) --> execution.jsonl + result.json --> STOP
    |
    v
[playbook_router.py]
    |-- Busca playbook en cache/playbooks/ para (screen, goal)
    |-- Si encuentra: navigation_plan = playbook.navigation_steps
    |-- Si no encuentra: navigation_plan = human_paths del contrato
    |-- Produce navigation_plan.json (schema tipado)
    |
    +---> BLOCKED (PIP NO_PLAYBOOK_NO_CONTRACT) --> STOP
    |
    v
[navigation_plan_validator.py] (NUEVO)
    |-- Valida navigation_plan.json contra NavigationPlan.schema.json
    |-- Verifica que cada step tiene: method, target, assertions
    |-- Verifica que los datos requeridos estan disponibles
    |-- Produce navigation_plan_validation.json
    |
    +---> BLOCKED (PIP INVALID_NAV_PLAN) --> STOP
    |
    v
[playwright_test_generator.py]
    |-- Recibe navigation_plan validado como parametro
    |-- Renderiza template con navegacion correcta (NO goto directo)
    |-- Genera arrival_assertions block segun plan
    |-- Produce .spec.ts
    |
    v
[playwright runner]
    |-- Ejecuta spec
    |-- Cada paso de navegacion emite navigation_step_* a execution.jsonl
    |-- Arrival assertions verificadas en cada paso
    |-- Evidence: screenshots pre/post/error por paso
```

### 3.2. Flujo de ejecucion en el spec generado (nuevo)

```
global.setup.ts         storageState validado por fingerprint + TTL
        |
        v
test.beforeEach
    [1] Verificar que storageState existe y es valido
    [2] NO goto() directo — el navigation_plan define como llegar
    [3] Ejecutar navigation_plan.steps[0..n] usando helpers tipados
    [4] Verificar arrival_assertions despues del ultimo paso
    [5] Screenshot post-navegacion con nombre descriptivo
    [6] Si falla: emitir navigation_step_failed + categoria + STOP
        |
        v
test body
    [7] Ejecutar pasos de negocio
    [8] Cada paso captura screenshots
    [9] Oracle assertions al final
        |
        v
test.afterEach
   [10] Escribir assertions.json, step_bboxes.json, screen_errors.json
   [11] Emitir navigation_summary event a execution.jsonl
```

### 3.3. Diagrama de componentes (ASCII)

```
+-----------------------------------+
| navigation_contracts.yml          |  <-- contrato declarativo por pantalla
| (schema: NavigationContracts v2)  |
+-----------------------------------+
             |
             v
+-----------------------------------+
| navigation_strategy_resolver.py   |  <-- resuelve estrategia por escenario
| input:  ScenarioNavInput.schema   |  <-- lane, screen, available_data
| output: NavigationDecision.schema |  <-- strategy, path_id, blocked_reason
+-----------------------------------+
             |
             v
+-----------------------------------+
| playbook_router.py                |  <-- busca playbook preconstruido
| input:  NavigationDecision        |
| output: NavigationPlan.schema     |  <-- pasos tipados + assertions
+-----------------------------------+
             |
             v
+-----------------------------------+
| navigation_plan_validator.py (NEW)|  <-- valida plan contra schema
| input:  NavigationPlan.schema     |
| output: NavigationPlanValidation  |
+-----------------------------------+
             |
             v
+-----------------------------------+
| playwright_test_generator.py      |  <-- genera .spec.ts
| recibe: navigation_plan validado  |
| renderiza: template con helpers   |
| NUNCA genera goto() sin plan      |
+-----------------------------------+
             |
             v
+-----------------------------------+
| playwright_test.spec.ts.j2        |  <-- template renovado
| beforeEach: executeNavigationPlan |  <-- helper TypeScript nuevo
| body SETUP: ELIMINADO goto directo|
| steps navigate: con contrato      |
+-----------------------------------+
             |
             v
+-----------------------------------+
| playwright/helpers/               |
| navigation_executor.ts   (NEW)    |  <-- ejecuta NavigationPlan en browser
| webforms_nav.ts          (exists) |  <-- form.submit(), doPostBack()
| arrival_validator.ts     (NEW)    |  <-- assertions de llegada tipadas
| session_guard.ts         (NEW)    |  <-- verifica storageState antes de nav
+-----------------------------------+
             |
             v
+-----------------------------------+
| execution.jsonl                   |  <-- evidencia de cada paso de navegacion
| navigation_plan.json              |  <-- plan resuelto (artefacto)
| navigation_step_results.json      |  <-- resultado por paso (artefacto) (NEW)
| arrival_assertions.json           |  <-- resultado de assertions de llegada (NEW)
+-----------------------------------+
```

---

## 4. Contratos de datos

### 4.1. `NavigationPlan.schema.json` (nuevo artefacto central)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "NavigationPlan/1.0",
  "description": "Plan de navegacion resuelto para un escenario UAT. Input del generator y del executor.",
  "type": "object",
  "required": ["plan_version", "ticket_id", "scenario_id", "target_screen", "lane", "strategy", "steps", "arrival_assertions"],
  "properties": {
    "plan_version": { "type": "string", "const": "1.0" },
    "ticket_id": { "type": "integer" },
    "scenario_id": { "type": "string" },
    "target_screen": { "type": "string" },
    "lane": { "type": "string" },
    "strategy": {
      "type": "string",
      "enum": ["direct_entry", "deeplink", "human_path", "playbook"]
    },
    "path_id": { "type": ["string", "null"] },
    "playbook_id": { "type": ["string", "null"] },
    "entrypoint": { "type": "string" },
    "deeplink_url": { "type": ["string", "null"] },
    "steps": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["step_index", "method", "description"],
        "properties": {
          "step_index": { "type": "integer" },
          "method": {
            "type": "string",
            "enum": ["goto_direct", "goto_deeplink", "form_submit", "dopostback", "link_click", "menu_click", "row_click", "tab_click", "button_click"]
          },
          "description": { "type": "string" },
          "target_url": { "type": ["string", "null"] },
          "eventtarget": { "type": ["string", "null"] },
          "eventargument": { "type": ["string", "null"] },
          "selector": { "type": ["string", "null"] },
          "wait_url_contains": { "type": ["string", "null"] },
          "timeout_ms": { "type": "integer", "default": 45000 },
          "retries": { "type": "integer", "default": 3 },
          "data_bindings": {
            "type": "object",
            "description": "Mapeo de campos de formulario a datos de prueba",
            "additionalProperties": { "type": "string" }
          },
          "intermediate_assertions": {
            "type": "array",
            "items": { "$ref": "#/$defs/AssertionSpec" }
          },
          "screenshot_label": { "type": "string" }
        }
      }
    },
    "arrival_assertions": {
      "type": "array",
      "minItems": 1,
      "description": "Assertions obligatorias despues del ultimo paso de navegacion",
      "items": { "$ref": "#/$defs/AssertionSpec" }
    },
    "session_requirements": {
      "type": "object",
      "properties": {
        "require_valid_storagestate": { "type": "boolean", "default": true },
        "storagestate_max_age_minutes": { "type": "integer", "default": 120 }
      }
    },
    "resolved_at": { "type": "string", "format": "date-time" },
    "resolver_version": { "type": "string" }
  },
  "$defs": {
    "AssertionSpec": {
      "type": "object",
      "required": ["assertion_id", "type", "description"],
      "properties": {
        "assertion_id": { "type": "string" },
        "type": {
          "type": "string",
          "enum": [
            "url_contains",
            "url_not_contains",
            "dom_visible",
            "dom_not_visible",
            "dom_text_contains",
            "page_title_contains",
            "page_title_not_contains",
            "no_aspnet_error",
            "no_login_redirect",
            "no_500_response"
          ]
        },
        "description": { "type": "string" },
        "selector": { "type": ["string", "null"] },
        "expected_value": { "type": ["string", "null"] },
        "timeout_ms": { "type": "integer", "default": 10000 },
        "severity": {
          "type": "string",
          "enum": ["hard", "soft"],
          "default": "hard",
          "description": "hard: falla el test. soft: registra pero no falla."
        },
        "category_on_fail": {
          "type": "string",
          "enum": ["NAV", "ENV", "DATA", "APP"],
          "default": "NAV"
        }
      }
    }
  }
}
```

### 4.2. Eventos de navegacion en `execution.jsonl`

Cada paso del `NavigationPlan` emite tres eventos:

```json
{ "event": "navigation_step_started",
  "timestamp": "2026-05-11T14:00:00.000Z",
  "ticket_id": 120,
  "scenario_id": "P02",
  "step_index": 1,
  "method": "goto_direct",
  "target_url": "FrmBusqueda.aspx",
  "description": "Navegar a pantalla de busqueda"
}

{ "event": "navigation_step_completed",
  "timestamp": "2026-05-11T14:00:01.500Z",
  "ticket_id": 120,
  "scenario_id": "P02",
  "step_index": 1,
  "method": "goto_direct",
  "url_before": "about:blank",
  "url_after": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
  "elapsed_ms": 1500,
  "attempts": 1,
  "arrival_assertions_passed": ["url_contains:FrmBusqueda", "dom_visible:#c_btnBuscar"],
  "screenshot": "evidence/120/P02/nav_step_01_completed.png"
}

{ "event": "navigation_step_failed",
  "timestamp": "2026-05-11T14:00:03.000Z",
  "ticket_id": 120,
  "scenario_id": "P02",
  "step_index": 2,
  "method": "form_submit",
  "url_before": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
  "url_after": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
  "elapsed_ms": 45000,
  "attempts": 3,
  "error_code": "NAV_TIMEOUT",
  "category": "NAV",
  "reason": "FORM_SUBMIT_TIMEOUT_AFTER_3_ATTEMPTS",
  "failed_assertion": "url_contains:FrmDetalleClie",
  "screenshot": "evidence/120/P02/nav_step_02_failed.png",
  "human_action_required": "Verificar que la grilla de resultados retorna al menos una fila para CLCOD=12345"
}
```

Evento de resumen al final del bloque de navegacion:

```json
{ "event": "navigation_plan_result",
  "ticket_id": 120,
  "scenario_id": "P02",
  "strategy": "human_path",
  "path_id": "open_from_busqueda",
  "steps_total": 3,
  "steps_completed": 2,
  "steps_failed": 1,
  "navigation_ok": false,
  "final_url": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
  "expected_screen": "FrmDetalleClie.aspx",
  "elapsed_ms_total": 48500,
  "category": "NAV",
  "reason": "FORM_SUBMIT_TIMEOUT_AFTER_3_ATTEMPTS"
}
```

### 4.3. Extension de `navigation_contracts.yml` a v2

Campos nuevos por pantalla:

```yaml
_meta:
  version: "2.0"
  schema: "NavigationContracts/2.0"
  created_at: "2026-05-11"

FrmDetalleClie.aspx:
  schema_version: "2.0"
  screen_type: detail
  direct_entry_allowed: false
  deeplink_allowed: true
  human_path_required_for_uat: true

  # NUEVO en v2: arrival_assertions obligatorias para esta pantalla
  arrival_assertions:
    - assertion_id: no_aspnet_error
      type: no_aspnet_error
      description: "No YSOD ni Errors.aspx visible"
      severity: hard
      category_on_fail: ENV
    - assertion_id: no_login_redirect
      type: no_login_redirect
      description: "No redirigido a FrmLogin"
      severity: hard
      category_on_fail: ENV
    - assertion_id: url_contains_frmdetalleclie
      type: url_contains
      expected_value: FrmDetalleClie
      description: "URL contiene FrmDetalleClie"
      severity: hard
      category_on_fail: NAV
    - assertion_id: detalle_form_visible
      type: dom_visible
      selector: "#c_pnlDetalle, #ctl00_c_pnlDetalle, form#aspnetForm"
      description: "Panel principal del detalle visible"
      severity: hard
      category_on_fail: APP

  # NUEVO en v2: timeouts especificos por pantalla
  timeouts:
    navigation_timeout_ms: 45000
    arrival_assertion_timeout_ms: 10000
    updatepanel_settle_ms: 5000

  # NUEVO en v2: indicadores de error ASP.NET especificos
  aspnet_error_markers:
    title_contains: ["Runtime Error", "Server Error", "Application Error"]
    url_contains: ["Errors.aspx", "Error.aspx"]
    body_contains: ["Server Error in '/' Application", "Unhandled exception"]

  deeplink:
    pattern: "FrmDetalleClie.aspx?clcod={CLCOD}"
    required_params:
      - CLCOD
    reconstructs_context:
      - authenticated_user
      - selected_client
      - permissions
      - navigation_context
    required_assertions:
      - selected_client_loaded
      - detalle_cliente_visible
      - no_server_error
    allowed_lanes:
      - smoke_deeplink
      - regression_deeplink
      - diagnostic
      - forensic_rerun
    forbidden_lanes:
      - uat_human
      - uat_human_simulation

  human_paths:
    open_from_busqueda:
      entrypoint: FrmBusqueda.aspx
      steps:
        - step_index: 1
          method: goto_direct
          description: "Navegar a FrmBusqueda.aspx"
          target_url: "FrmBusqueda.aspx"
          wait_url_contains: "FrmBusqueda"
          timeout_ms: 20000
          retries: 2
          intermediate_assertions:
            - assertion_id: search_form_visible
              type: dom_visible
              selector: "#c_btnBuscar, #ctl00_c_btnBuscar"
              description: "Boton Buscar visible en FrmBusqueda"
              severity: hard
              category_on_fail: NAV

        - step_index: 2
          method: fill
          description: "Ingresar CLCOD en el campo de filtro"
          selector: "#c_abfCliente, #ctl00_c_abfCliente"
          data_bindings:
            value: "CLCOD"
          timeout_ms: 5000
          retries: 1

        - step_index: 3
          method: button_click
          description: "Hacer click en boton Buscar"
          selector: "#c_btnBuscar, #ctl00_c_btnBuscar"
          wait_url_contains: "FrmBusqueda"
          timeout_ms: 30000
          retries: 2
          intermediate_assertions:
            - assertion_id: search_results_visible
              type: dom_visible
              selector: "#c_gvClientes tr:nth-child(2), .grid-result tr:nth-child(2)"
              description: "Al menos una fila de resultado visible en la grilla"
              severity: hard
              category_on_fail: DATA

        - step_index: 4
          method: row_click
          description: "Click en la primera fila de resultado que coincide con CLCOD"
          selector: "#c_gvClientes tr:nth-child(2) td:first-child, .grid-result tr:nth-child(2) td"
          wait_url_contains: "FrmDetalleClie"
          timeout_ms: 45000
          retries: 3

      required_data:
        - CLCOD
      emits_context:
        - selected_client
        - navigation_context
      required_assertions:
        - search_results_visible
        - selected_client_loaded
        - detalle_cliente_visible
```

### 4.4. Schema de `playbook.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "Playbook/1.0",
  "description": "Playbook ejecutable para QA UAT Agent. Contrato de navegacion + acciones para un goal especifico.",
  "type": "object",
  "required": ["playbook_id", "schema_version", "target_screen", "goal_slug", "navigation_steps", "action_steps", "arrival_assertions"],
  "properties": {
    "playbook_id": { "type": "string" },
    "schema_version": { "type": "string", "const": "1.0" },
    "target_screen": { "type": "string" },
    "goal_slug": { "type": "string" },
    "description": { "type": "string" },
    "tags": { "type": "array", "items": { "type": "string" } },
    "confidence_keywords": { "type": "array", "items": { "type": "string" } },
    "created_at": { "type": "string", "format": "date-time" },
    "created_from_recording": { "type": "boolean" },
    "recording_session_id": { "type": ["string", "null"] },
    "allowed_lanes": { "type": "array", "items": { "type": "string" } },
    "required_data": { "type": "array", "items": { "type": "string" } },
    "navigation_steps": {
      "type": "array",
      "description": "Pasos de navegacion para llegar a target_screen",
      "items": { "$ref": "NavigationPlan/1.0#/properties/steps/items" }
    },
    "action_steps": {
      "type": "array",
      "description": "Pasos de interaccion de negocio despues de llegar a la pantalla"
    },
    "arrival_assertions": {
      "type": "array",
      "items": { "$ref": "NavigationPlan/1.0#/$defs/AssertionSpec" }
    },
    "parameterizable_fields": {
      "type": "object",
      "description": "Campos que el escenario puede sobreescribir via data_bindings"
    }
  }
}
```

---

## 5. Plan de sprints

### Sprint N5-01 — Eliminar los tres `goto()` incondicionales del template

**Objetivo:** Cerrar las brechas B-01, B-02 y B-03. Ningun spec generado puede tener `page.goto()` contra una pantalla con `direct_entry_allowed: false`.

**Duracion estimada:** 3 dias  
**Lane:** `compile-only` (no requiere Playwright para validarse)

#### 5.1.1. Archivos afectados

- `Tools/Stacky/Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2`
- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright_test_generator.py`

#### 5.1.2. Cambios en `playwright_test.spec.ts.j2`

**Cambio 1 — `beforeEach` (lineas 376-398):**

Reemplazar la logica actual de `goto()` + validacion reactiva por una llamada al nuevo helper `executeNavigationPlan()`:

```typescript
// ANTES (lineas 376-398) — ELIMINAR
test.beforeEach(async ({ page }) => {
  await page.goto(`${BASE_URL}${TARGET_SCREEN}`, ...);
  // validacion reactiva post-goto...
});

// DESPUES — template Jinja2
test.beforeEach(async ({ page }) => {
  // [NAV] Ejecutar plan de navegacion resuelto por navigation_strategy_resolver.py
  // Strategy: {{ navigation_plan.strategy }}
  // Entrypoint: {{ navigation_plan.entrypoint }}
  // Steps: {{ navigation_plan.steps | length }}
{% if navigation_plan.session_requirements.require_valid_storagestate %}
  // [SESSION] Verificar storageState antes de navegar
  await verifyStorageStateValid({{ navigation_plan.session_requirements.storagestate_max_age_minutes }});
{% endif %}
  const _navPlanResult = await executeNavigationPlan(page, NAVIGATION_PLAN, {
    evidenceDir: 'evidence/{{ ticket_id }}/{{ scenario_id }}',
    screenshotPrefix: 'nav',
    emitEvents: true,
  });
  if (!_navPlanResult.ok) {
    throw new Error(
      `[NAV_PLAN_FAILED] No se pudo completar la navegacion a {{ target_screen }}. ` +
      `strategy={{ navigation_plan.strategy }} ` +
      `step=${_navPlanResult.failedStep} ` +
      `errorCode=${_navPlanResult.errorCode} ` +
      `category=${_navPlanResult.category} ` +
      `detail=${_navPlanResult.detail}`
    );
  }
});
```

**Cambio 2 — bloque SETUP del cuerpo del test (linea 418):**

Eliminar el segundo `goto()`. La navegacion ya fue resuelta en `beforeEach` por `executeNavigationPlan`. El bloque SETUP queda solo como screenshot y verificacion opcional:

```typescript
// ANTES (linea 418) — ELIMINAR
await page.goto(`${BASE_URL}{{ pantalla }}`, { waitUntil: 'domcontentloaded' });

// DESPUES
// [SETUP] La navegacion fue completada en beforeEach via executeNavigationPlan.
// Solo capturamos screenshot inicial del estado de negocio.
await page.screenshot({ path: 'evidence/{{ ticket_id }}/{{ scenario_id }}/step_00_setup.png' });
```

**Cambio 3 — accion `navigate` en steps (linea 492):**

Agregar verificacion de contrato antes de emitir `goto()`:

```typescript
// ANTES
await page.goto(`${BASE_URL}{{ step.target }}`, { waitUntil: 'domcontentloaded' });

// DESPUES — con verificacion de estrategia desde navigation_plan
{% if step.navigation_strategy == 'direct_entry' %}
    // [NAV DIRECT] {{ step.target }} permite entrada directa segun navigation_contracts.yml
    await page.goto(`${BASE_URL}{{ step.target }}`, { waitUntil: 'domcontentloaded', timeout: {{ step.timeout_ms | default(20000) }} });
{% elif step.navigation_strategy == 'form_submit' %}
    // [NAV FORM_SUBMIT] {{ step.target }} requiere postback via HTMLFormElement.prototype.submit
    const _navStep_{{ loop.index }} = await navigateViaFormSubmit(
      page, {{ step.eventtarget | tojson }}, {{ step.eventargument | tojson }},
      {{ step.wait_url_contains | tojson }}, { timeoutMs: {{ step.timeout_ms | default(45000) }}, maxAttempts: {{ step.retries | default(3) }} }
    );
    if (!_navStep_{{ loop.index }}.ok) {
      throw new Error(`[NAV_STEP_FAILED] step {{ loop.index }}: ${_navStep_{{ loop.index }}.errorCode}`);
    }
{% elif step.navigation_strategy == 'blocked' %}
    // [NAV BLOCKED] Esta accion fue bloqueada por navigation_strategy_resolver.
    // Razon: {{ step.blocked_reason }}
    throw new Error('[NAV_BLOCKED] {{ step.blocked_reason }}');
{% endif %}
```

**Cambio 4 — Agregar importaciones de helpers nuevos al inicio del template:**

```typescript
import { executeNavigationPlan } from '../../playwright/helpers/navigation_executor';
import { verifyStorageStateValid } from '../../playwright/helpers/session_guard';
import { ArrivalValidator } from '../../playwright/helpers/arrival_validator';

// NAVIGATION_PLAN — resuelto por navigation_strategy_resolver.py y codificado en el spec.
// NO editar manualmente. Regenerar el spec si la estrategia cambia.
const NAVIGATION_PLAN = {{ navigation_plan | tojson(indent=2) }};
```

#### 5.1.3. Cambios en `playwright_test_generator.py`

El generator debe:
1. Recibir `navigation_plan: dict` como parametro de la funcion `run()`.
2. Validar que el plan no es `None` antes de renderizar.
3. Pasar el plan al contexto Jinja2.
4. Si `navigation_plan` es `None` y la pantalla tiene `direct_entry_allowed: false`, retornar `BLOCKED GEN NAVIGATION_PLAN_MISSING`.

Pseudocodigo del cambio:

```python
def run(
    scenarios_path: Path,
    ui_maps_dir: Path,
    out_dir: Path,
    navigation_plans_dir: Optional[Path] = None,  # NUEVO
    ...
) -> dict:
    ...
    for scenario in scenarios:
        screen = scenario.get("pantalla")
        # Cargar navigation_plan para este escenario
        nav_plan = _load_navigation_plan(
            navigation_plans_dir, scenario["scenario_id"]
        )
        # Verificar si la pantalla requiere plan
        if nav_plan is None and _screen_requires_nav_plan(screen, contracts):
            results.append({
                "scenario_id": scenario["scenario_id"],
                "ok": False,
                "blocked": True,
                "category": "GEN",
                "reason": "NAVIGATION_PLAN_MISSING",
                "human_action_required": (
                    f"Ejecutar navigation_strategy_resolver.py para el escenario "
                    f"'{scenario['scenario_id']}' y pantalla '{screen}' antes de generar el spec."
                )
            })
            continue
        # Renderizar template con nav_plan
        context = _build_template_context(scenario, ui_map, nav_plan=nav_plan, ...)
        ...
```

#### 5.1.4. Tests obligatorios

- `tests/unit/test_template_no_direct_goto.py` — verifica que el template renderizado para `FrmDetalleClie.aspx` con `direct_entry_allowed: false` NO contiene `page.goto(BASE_URL + 'FrmDetalleClie.aspx')` como instruccion de setup
- `tests/unit/test_generator_blocks_without_nav_plan.py` — verifica que el generator retorna `BLOCKED GEN NAVIGATION_PLAN_MISSING` cuando `navigation_plan` es `None` para una pantalla con `direct_entry_allowed: false`
- `tests/unit/test_generator_allows_direct_entry.py` — verifica que para `FrmBusqueda.aspx` (`direct_entry_allowed: true`) el generator sigue generando `goto()` correctamente

#### 5.1.5. Criterios de aceptacion verificables

- `grep -r "goto.*FrmDetalleClie" evidence/120/` retorna cero resultados despues de regenerar el spec
- El generator retorna `"blocked": true, "reason": "NAVIGATION_PLAN_MISSING"` para cualquier pantalla con `direct_entry_allowed: false` sin plan
- Los tres tests unitarios pasan

#### 5.1.6. Metricas que mueve

- `generator_block_rate` por `NAVIGATION_PLAN_MISSING`: baja cuando se integran los planes
- `nav_direct_goto_violations`: debe llegar a 0
- `time_to_first_actionable_failure`: baja porque el bloqueo ocurre antes de Playwright

---

### Sprint N5-02 — `navigation_plan_validator.py` y `NavigationPlan.schema.json`

**Objetivo:** Cerrar la brecha B-04. Crear el validador del plan de navegacion como gate obligatorio entre el resolver y el generator.

**Duracion estimada:** 2 dias

#### 5.2.1. Archivos a crear

- `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_plan_validator.py`
- `Tools/Stacky/Stacky tools/QA UAT Agent/schemas/NavigationPlan.schema.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/schemas/NavigationContracts.v2.schema.json`

#### 5.2.2. Contrato del validador

Entrada:

```json
{
  "navigation_plan": { "...": "NavigationPlan/1.0 object" },
  "available_data": { "CLCOD": "12345" }
}
```

Salida exitosa:

```json
{
  "ok": true,
  "plan_id": "120_P02",
  "validation_version": "1.0",
  "steps_validated": 4,
  "data_bindings_resolved": { "CLCOD": "12345" },
  "assertions_declared": 5,
  "warnings": []
}
```

Salida de bloqueo:

```json
{
  "ok": false,
  "verdict": "BLOCKED",
  "category": "PIP",
  "reason": "INVALID_NAV_PLAN",
  "failed_validation": "step_index_2_missing_selector",
  "human_action_required": "El step 2 del plan de navegacion para P02 no tiene selector definido para method=fill. Verificar el contrato en navigation_contracts.yml o el playbook.",
  "plan_errors": [
    { "step_index": 2, "field": "selector", "error": "required when method=fill" }
  ]
}
```

#### 5.2.3. Reglas de validacion implementadas

1. El plan tiene al menos un step.
2. Cada step tiene `method` valido del enum.
3. Steps con `method=fill` tienen `selector` y `data_bindings`.
4. Steps con `method=form_submit` tienen `eventtarget` y `wait_url_contains`.
5. Steps con `method=goto_direct` o `method=goto_deeplink` tienen `target_url`.
6. `arrival_assertions` tiene al menos `no_aspnet_error` y `url_contains`.
7. Todos los `data_bindings` de todos los steps tienen valores en `available_data`.
8. Ningun step con `method=goto_direct` tiene como `target_url` una pantalla con `direct_entry_allowed: false` en los contratos.

#### 5.2.4. Evento en `execution.jsonl`

```json
{
  "event": "navigation_plan_validation",
  "ok": true,
  "plan_id": "120_P02",
  "steps_validated": 4,
  "assertions_declared": 5,
  "warnings": []
}
```

#### 5.2.5. Tests obligatorios

- `tests/unit/test_nav_plan_validator_valid.py`
- `tests/unit/test_nav_plan_validator_missing_selector.py`
- `tests/unit/test_nav_plan_validator_direct_goto_violation.py`
- `tests/unit/test_nav_plan_validator_data_binding_missing.py`

#### 5.2.6. Criterios de aceptacion

- El validator rechaza cualquier plan con `goto_direct` a pantalla con `direct_entry_allowed: false`
- El validator rechaza planes sin `arrival_assertions`
- El validator resuelve `data_bindings` contra `available_data` y reporta los faltantes

---

### Sprint N5-03 — `navigation_executor.ts` y `arrival_validator.ts` (TypeScript helpers)

**Objetivo:** Cerrar la brecha B-05. Crear los helpers TypeScript que ejecutan el `NavigationPlan` en el browser de Playwright y verifican las assertions de llegada.

**Duracion estimada:** 4 dias

#### 5.3.1. Archivos a crear

- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/helpers/navigation_executor.ts`
- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/helpers/arrival_validator.ts`
- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/helpers/session_guard.ts`

#### 5.3.2. Contrato de `navigation_executor.ts`

```typescript
export interface NavigationPlan {
  plan_version: string;
  ticket_id: number;
  scenario_id: string;
  target_screen: string;
  strategy: 'direct_entry' | 'deeplink' | 'human_path' | 'playbook';
  steps: NavigationStep[];
  arrival_assertions: AssertionSpec[];
  session_requirements: { require_valid_storagestate: boolean; storagestate_max_age_minutes: number };
}

export interface NavigationResult {
  ok: boolean;
  strategy: string;
  steps_completed: number;
  steps_failed: number;
  failedStep: number | null;
  errorCode: string | null;
  category: 'NAV' | 'ENV' | 'DATA' | 'APP' | null;
  detail: string | null;
  elapsedMs: number;
  screenshots: string[];
  arrivalAssertionsPassed: string[];
  arrivalAssertionsFailed: string[];
}

export async function executeNavigationPlan(
  page: Page,
  plan: NavigationPlan,
  options: {
    evidenceDir: string;
    screenshotPrefix?: string;
    emitEvents?: boolean;
    baseUrl?: string;
  }
): Promise<NavigationResult>
```

El `executeNavigationPlan` itera sobre `plan.steps` y por cada step:
1. Captura screenshot pre-step.
2. Ejecuta el metodo correspondiente (goto, form_submit, click, fill, etc.).
3. Espera la URL o DOM esperada.
4. Verifica `intermediate_assertions` si existen.
5. Captura screenshot post-step.
6. Si falla, captura screenshot de error, clasifica el error code y retorna.

Despues del ultimo step, ejecuta `ArrivalValidator.validateAll(plan.arrival_assertions)`.

#### 5.3.3. Contrato de `arrival_validator.ts`

```typescript
export interface AssertionSpec {
  assertion_id: string;
  type: 'url_contains' | 'url_not_contains' | 'dom_visible' | 'dom_not_visible' |
        'dom_text_contains' | 'page_title_contains' | 'page_title_not_contains' |
        'no_aspnet_error' | 'no_login_redirect' | 'no_500_response';
  selector?: string | null;
  expected_value?: string | null;
  timeout_ms?: number;
  severity: 'hard' | 'soft';
  category_on_fail: 'NAV' | 'ENV' | 'DATA' | 'APP';
}

export interface ArrivalValidationResult {
  ok: boolean;
  passed: string[];
  failed: string[];
  errors: { assertion_id: string; type: string; actual: string; expected: string; category: string }[];
}

export class ArrivalValidator {
  static async validateAll(
    page: Page,
    assertions: AssertionSpec[],
    options: { screenshotOnFail?: string }
  ): Promise<ArrivalValidationResult>

  // Implementaciones por tipo:
  static async checkUrlContains(page, expected): Promise<boolean>
  static async checkDomVisible(page, selector, timeout): Promise<boolean>
  static async checkNoAspnetError(page): Promise<boolean>
  static async checkNoLoginRedirect(page): Promise<boolean>
  static async checkNo500Response(page): Promise<boolean>
}
```

La deteccion de error ASP.NET (`checkNoAspnetError`) verifica:
- `page.title()` contiene alguno de: "Runtime Error", "Server Error in '/' Application", "Application Error"
- `page.url()` contiene "Errors.aspx" o "Error.aspx"
- DOM contiene `h1:has-text('Server Error')` o el clasico amarillo `<div id="ctl00_c_lblError">`

#### 5.3.4. Contrato de `session_guard.ts`

```typescript
export async function verifyStorageStateValid(
  maxAgeMinutes: number,
  authFilePath?: string
): Promise<void>
```

Lee el fingerprint del `.auth/agenda.fingerprint.json`. Si el archivo no existe o tiene mas de `maxAgeMinutes` minutos, lanza:

```
[SESSION_EXPIRED] storageState tiene {age} minutos (max: {maxAgeMinutes}).
Re-ejecutar el pipeline para refresh. category=ENV reason=STORAGESTATE_EXPIRED
```

#### 5.3.5. Tests obligatorios

- `playwright/helpers/__tests__/arrival_validator.test.ts` — mock de page, verifica cada tipo de assertion
- `playwright/helpers/__tests__/navigation_executor.test.ts` — mock de page, verifica flujo happy path y fallo en step 2
- `playwright/helpers/__tests__/session_guard.test.ts` — verifica comportamiento con archivo ausente, expirado y valido

#### 5.3.6. Criterios de aceptacion

- `ArrivalValidator.checkNoAspnetError()` detecta el YSOD de ASP.NET en un HTML de fixture
- `executeNavigationPlan()` emite screenshot por cada step fallido
- `verifyStorageStateValid()` lanza `ENV SESSION_EXPIRED` cuando el auth tiene mas de 120 minutos

---

### Sprint N5-04 — Playbooks ejecutables para pantallas criticas

**Objetivo:** Cerrar la brecha B-06. Crear los primeros playbooks con schema completo y navegacion ejecutable para `FrmDetalleClie.aspx`, `FrmBusqueda.aspx` y `FrmAgenda.aspx`.

**Duracion estimada:** 3 dias

#### 5.4.1. Archivos a crear

- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/open_detalle_cliente_from_busqueda.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/open_busqueda_directa.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/open_agenda_personal.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/index.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/schemas/Playbook.schema.json`

#### 5.4.2. Ejemplo de playbook completo: `open_detalle_cliente_from_busqueda.json`

```json
{
  "playbook_id": "open_detalle_cliente_from_busqueda",
  "schema_version": "1.0",
  "target_screen": "FrmDetalleClie.aspx",
  "goal_slug": "abrir_detalle_cliente",
  "description": "Navegar desde FrmBusqueda.aspx a FrmDetalleClie.aspx buscando por CLCOD",
  "tags": ["detalle_cliente", "busqueda", "human_path", "uat_human"],
  "confidence_keywords": ["detalle cliente", "ficha cliente", "perfil cliente", "abrir cliente"],
  "created_at": "2026-05-11T00:00:00Z",
  "created_from_recording": false,
  "allowed_lanes": ["uat_human", "uat_human_simulation", "full-uat"],
  "required_data": ["CLCOD"],
  "navigation_steps": [
    {
      "step_index": 1,
      "method": "goto_direct",
      "description": "Navegar a FrmBusqueda.aspx (entrypoint)",
      "target_url": "FrmBusqueda.aspx",
      "wait_url_contains": "FrmBusqueda",
      "timeout_ms": 20000,
      "retries": 2,
      "screenshot_label": "nav_01_busqueda_loaded",
      "intermediate_assertions": [
        {
          "assertion_id": "search_form_visible",
          "type": "dom_visible",
          "selector": "#c_btnBuscar",
          "description": "Boton Buscar visible",
          "severity": "hard",
          "category_on_fail": "NAV",
          "timeout_ms": 10000
        }
      ]
    },
    {
      "step_index": 2,
      "method": "fill",
      "description": "Ingresar CLCOD en el campo de busqueda",
      "selector": "#c_abfCliente",
      "data_bindings": { "value": "CLCOD" },
      "timeout_ms": 5000,
      "retries": 1,
      "screenshot_label": "nav_02_clcod_filled"
    },
    {
      "step_index": 3,
      "method": "button_click",
      "description": "Click en boton Buscar y esperar resultados",
      "selector": "#c_btnBuscar",
      "wait_url_contains": "FrmBusqueda",
      "timeout_ms": 30000,
      "retries": 2,
      "screenshot_label": "nav_03_search_results",
      "intermediate_assertions": [
        {
          "assertion_id": "grid_has_results",
          "type": "dom_visible",
          "selector": "#c_gvClientes tbody tr:nth-child(1)",
          "description": "Al menos una fila en la grilla de resultados",
          "severity": "hard",
          "category_on_fail": "DATA",
          "timeout_ms": 15000
        }
      ]
    },
    {
      "step_index": 4,
      "method": "row_click",
      "description": "Click en la primera fila que coincide con CLCOD",
      "selector": "#c_gvClientes tbody tr:nth-child(1) td:first-child",
      "wait_url_contains": "FrmDetalleClie",
      "timeout_ms": 45000,
      "retries": 3,
      "screenshot_label": "nav_04_detalle_loaded"
    }
  ],
  "arrival_assertions": [
    {
      "assertion_id": "no_aspnet_error",
      "type": "no_aspnet_error",
      "description": "No YSOD ni pagina de error ASP.NET",
      "severity": "hard",
      "category_on_fail": "ENV",
      "timeout_ms": 5000
    },
    {
      "assertion_id": "no_login_redirect",
      "type": "no_login_redirect",
      "description": "No redirigido a FrmLogin (sesion expirada)",
      "severity": "hard",
      "category_on_fail": "ENV",
      "timeout_ms": 3000
    },
    {
      "assertion_id": "url_contains_detalle",
      "type": "url_contains",
      "expected_value": "FrmDetalleClie",
      "description": "URL contiene FrmDetalleClie",
      "severity": "hard",
      "category_on_fail": "NAV",
      "timeout_ms": 5000
    },
    {
      "assertion_id": "detalle_panel_visible",
      "type": "dom_visible",
      "selector": "#ctl00_c_pnlDetalle, #c_pnlDetalle",
      "description": "Panel principal del detalle de cliente visible",
      "severity": "hard",
      "category_on_fail": "APP",
      "timeout_ms": 10000
    }
  ],
  "action_steps": [],
  "parameterizable_fields": {
    "CLCOD": { "type": "string", "description": "Codigo de cliente a buscar y abrir" }
  }
}
```

#### 5.4.3. Actualizacion del `playbook_router.py`

El router actual usa `cache/playbooks/index.json` como indice. Despues de crear los playbooks, ejecutar:

```
python playbook_router.py --rebuild-index
```

Verificar que el output del router para `screen=FrmDetalleClie.aspx` retorna `playbook_id=open_detalle_cliente_from_busqueda` con score >= 4.

#### 5.4.4. Tests obligatorios

- `tests/unit/test_playbook_schema_valid.py` — verifica que cada playbook en `cache/playbooks/` valida contra `Playbook.schema.json`
- `tests/unit/test_playbook_router_finds_detalle.py` — verifica que el router resuelve `FrmDetalleClie.aspx + "abrir cliente"` al playbook correcto
- `tests/unit/test_playbook_arrival_assertions_complete.py` — verifica que todos los playbooks tienen al menos `no_aspnet_error` y `url_contains` en `arrival_assertions`

---

### Sprint N5-05 — Integracion end-to-end del pipeline de navegacion

**Objetivo:** Conectar todos los componentes: resolver -> validador -> router -> generator -> template con helpers. El pipeline debe producir un spec correcto sin ningun `goto()` directo para `FrmDetalleClie.aspx`.

**Duracion estimada:** 4 dias

#### 5.5.1. Flujo integrado

```python
# pipeline_orchestrator.py (seudocodigo del cambio)

# Stage 1: Resolver
nav_decision = resolve_navigation_strategy(
    ticket_id=ticket_id,
    scenario_id=scenario_id,
    target_screen=screen,
    lane=lane,
    available_data=available_data,
)
emit_event("navigation_contract_validation", nav_decision)

if nav_decision["decision"] == "BLOCKED":
    return blocked_result(nav_decision)

# Stage 2: Playbook router
if nav_decision["strategy"] == "human_path":
    playbook_result = playbook_router.resolve(screen, scenario_text)
    if playbook_result["ok"]:
        navigation_plan = build_nav_plan_from_playbook(playbook_result, available_data)
    else:
        navigation_plan = build_nav_plan_from_contract(nav_decision, navigation_contracts, available_data)
elif nav_decision["strategy"] == "deeplink":
    navigation_plan = build_nav_plan_from_deeplink(nav_decision, available_data)
elif nav_decision["strategy"] == "direct_entry":
    navigation_plan = build_nav_plan_direct(nav_decision)

# Stage 3: Validador
plan_validation = navigation_plan_validator.validate(navigation_plan, available_data)
emit_event("navigation_plan_validation", plan_validation)

if not plan_validation["ok"]:
    return blocked_result(plan_validation)

# Stage 4: Generator (recibe navigation_plan validado)
gen_result = playwright_test_generator.run(
    scenarios_path=scenarios_path,
    ui_maps_dir=ui_maps_dir,
    out_dir=out_dir,
    navigation_plans={scenario_id: navigation_plan},  # NUEVO
)
emit_event("generator_summary", gen_result)
```

#### 5.5.2. Nuevo modulo `navigation_plan_builder.py`

Crear `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_plan_builder.py` que construye un `NavigationPlan` tipado a partir de:
- Un `NavigationDecision` del resolver
- Un playbook (si existe) del router
- Los contratos de `navigation_contracts.yml`
- Los `available_data` del escenario

Salida: objeto Python equivalente a `NavigationPlan.schema.json`, serializable como JSON.

#### 5.5.3. Evento de summary de navegacion en `execution.jsonl`

```json
{
  "event": "navigation_pipeline_summary",
  "ticket_id": 120,
  "scenario_id": "P02",
  "resolver_decision": "ALLOW_GENERATION",
  "strategy": "human_path",
  "playbook_used": "open_detalle_cliente_from_busqueda",
  "plan_validated": true,
  "plan_steps": 4,
  "plan_arrival_assertions": 4,
  "spec_generated": true,
  "spec_path": "evidence/120/tests/P02_frmdetalleclie.spec.ts"
}
```

#### 5.5.4. Tests obligatorios

- `tests/integration/test_pipeline_detalleclie_human_path.py` — ejecuta el pipeline completo para ticket 120, verifica que el spec generado contiene `executeNavigationPlan` y NO contiene `goto.*FrmDetalleClie` en el setup
- `tests/integration/test_pipeline_detalleclie_no_clcod.py` — verifica que sin CLCOD el pipeline retorna `BLOCKED DATA NAVIGATION_DATA_MISSING`
- `tests/integration/test_pipeline_busqueda_direct.py` — verifica que para `FrmBusqueda.aspx` el pipeline genera `goto_direct` correctamente

#### 5.5.5. Criterios de aceptacion

- El spec generado para ticket 120/P02 tiene `const NAVIGATION_PLAN = {...}` con 4 steps
- El spec no contiene ninguna llamada `page.goto(BASE_URL + 'FrmDetalleClie.aspx')` en `beforeEach` ni en SETUP
- El pipeline retorna `BLOCKED DATA` cuando `CLCOD` no esta en `available_data`
- El evento `navigation_pipeline_summary` aparece en `execution.jsonl`

---

### Sprint N5-06 — Observabilidad de navegacion: `navigation_step_results.json` y `arrival_assertions.json`

**Objetivo:** Cerrar la brecha B-08. Todo run que ejecute navegacion debe producir evidencia granular de cada paso.

**Duracion estimada:** 2 dias

#### 5.6.1. Nuevos artefactos de evidencia

```
evidence/<ticket_id>/<run_id>/
  navigation_plan.json                  (plan resuelto y validado)
  navigation_step_results.json          (resultado de cada paso del plan)
  arrival_assertions.json               (resultado de assertions de llegada)
```

#### 5.6.2. Schema de `navigation_step_results.json`

```json
{
  "schema_version": "1.0",
  "ticket_id": 120,
  "scenario_id": "P02",
  "strategy": "human_path",
  "navigation_ok": true,
  "steps": [
    {
      "step_index": 1,
      "method": "goto_direct",
      "description": "Navegar a FrmBusqueda.aspx",
      "ok": true,
      "attempts": 1,
      "elapsed_ms": 1850,
      "url_before": "about:blank",
      "url_after": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
      "intermediate_assertions_passed": ["search_form_visible"],
      "intermediate_assertions_failed": [],
      "screenshots": ["evidence/120/P02/nav_step_01_completed.png"]
    },
    {
      "step_index": 2,
      "method": "fill",
      "description": "Ingresar CLCOD",
      "ok": true,
      "attempts": 1,
      "elapsed_ms": 230,
      "screenshots": ["evidence/120/P02/nav_step_02_completed.png"]
    },
    {
      "step_index": 3,
      "method": "button_click",
      "description": "Click Buscar",
      "ok": true,
      "attempts": 1,
      "elapsed_ms": 4200,
      "intermediate_assertions_passed": ["grid_has_results"],
      "intermediate_assertions_failed": [],
      "screenshots": ["evidence/120/P02/nav_step_03_completed.png"]
    },
    {
      "step_index": 4,
      "method": "row_click",
      "description": "Click primera fila",
      "ok": true,
      "attempts": 1,
      "elapsed_ms": 3100,
      "url_after": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx?clcod=12345",
      "screenshots": ["evidence/120/P02/nav_step_04_completed.png"]
    }
  ],
  "elapsed_ms_total": 9380
}
```

#### 5.6.3. Schema de `arrival_assertions.json`

```json
{
  "schema_version": "1.0",
  "ticket_id": 120,
  "scenario_id": "P02",
  "target_screen": "FrmDetalleClie.aspx",
  "navigation_strategy": "human_path",
  "all_passed": true,
  "assertions": [
    {
      "assertion_id": "no_aspnet_error",
      "type": "no_aspnet_error",
      "passed": true,
      "actual": null,
      "severity": "hard"
    },
    {
      "assertion_id": "no_login_redirect",
      "type": "no_login_redirect",
      "passed": true,
      "actual": null,
      "severity": "hard"
    },
    {
      "assertion_id": "url_contains_detalle",
      "type": "url_contains",
      "expected": "FrmDetalleClie",
      "actual": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx?clcod=12345",
      "passed": true,
      "severity": "hard"
    },
    {
      "assertion_id": "detalle_panel_visible",
      "type": "dom_visible",
      "selector": "#ctl00_c_pnlDetalle",
      "passed": true,
      "severity": "hard",
      "elapsed_ms": 320
    }
  ],
  "timestamp": "2026-05-11T14:01:30Z"
}
```

#### 5.6.4. Tests obligatorios

- `tests/unit/test_nav_step_results_schema.py` — valida que el JSON generado por el helper TypeScript cumple el schema
- `tests/unit/test_arrival_assertions_schema.py` — idem para arrival_assertions.json

---

### Sprint N5-07 — Gestion de sesion expirada y `session_expiry_detector`

**Objetivo:** Cerrar la brecha B-09. La expiracion de sesion durante navegacion debe clasificarse como `ENV` inmediatamente, no como `NAV_TIMEOUT` despues de 45 segundos.

**Duracion estimada:** 2 dias

#### 5.7.1. Archivo a crear

- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/helpers/session_guard.ts` (descrito en Sprint N5-03)

#### 5.7.2. Logica de deteccion de sesion expirada

La sesion puede expirar en tres momentos distintos:
1. **Pre-navegacion** — el `storageState` tiene mas de N minutos. Detectado por `verifyStorageStateValid()`.
2. **Durante navegacion** — el `goto()` o `form_submit` resulta en redirect a `FrmLogin.aspx`. Detectado por `arrival_validator` en `intermediate_assertions` con `no_login_redirect`.
3. **Post-navegacion** — el panel de login aparece dentro de la pantalla target (session timeout silencioso). Detectado por `arrival_validator` con `dom_visible selector=#ctl00_c_pnlLogin`.

En todos los casos, el error_code es `NAV_AUTH_EXPIRED`, la categoria es `ENV` y la accion humana es:

```
Re-ejecutar el pipeline para refrescar la sesion. 
El storageState en .auth/agenda.json es invalido o expiro.
Comando: ejecutar la etapa global.setup desde el pipeline o manualmente via
  npx playwright test --project setup
```

#### 5.7.3. Actualizacion del `global.setup.ts`

Agregar escritura del timestamp de creacion del auth al fingerprint file:

```json
{
  "fingerprint": "abc123...",
  "created_at": "2026-05-11T14:00:00Z",
  "user": "qauser",
  "base_url": "http://localhost:35017/AgendaWeb/"
}
```

La `session_guard.ts` lee este timestamp para calcular la edad del auth.

#### 5.7.4. Tests obligatorios

- `tests/unit/test_session_guard_expired.py` — fingerprint con `created_at` de 3 horas atras, verifica que lanza ENV SESSION_EXPIRED
- `tests/unit/test_session_guard_valid.py` — fingerprint de 10 minutos, no lanza excepcion
- `tests/unit/test_session_guard_missing_file.py` — sin archivo, lanza ENV STORAGESTATE_MISSING

---

### Sprint N5-08 — Clasificacion deterministica de errores de navegacion (NAV vs ENV vs DATA)

**Objetivo:** Garantizar que ningun fallo de navegacion quede clasificado como `UNKNOWN` o como `NAV_TIMEOUT` cuando la causa real es `ENV` o `DATA`.

**Duracion estimada:** 3 dias

#### 5.8.1. Ampliacion del clasificador de errores en `navigation_driver.py`

La funcion `_classify_error` actual (linea 496 de `navigation_driver.py`) solo distingue cuatro casos. Ampliar a:

```python
def _classify_error(exc_str: str, current_url: str, page_title: str = "", response_status: int = 0) -> dict:
    """
    Clasifica un error de navegacion con categoria y reason precisos.
    Retorna: {"error_code": str, "category": str, "reason": str, "is_terminal": bool}
    """
    exc_lower = exc_str.lower()
    url_lower = current_url.lower()
    title_lower = page_title.lower()

    # ENV — sesion expirada
    if "frmlogin" in url_lower or ("login" in url_lower and "frmlogin" not in url_lower and "FrmBusqueda" not in current_url):
        return {"error_code": "NAV_AUTH_EXPIRED", "category": "ENV", "reason": "SESSION_EXPIRED_LOGIN_REDIRECT", "is_terminal": True}

    # ENV — crash del app pool o servidor caido
    if response_status >= 500 or "runtime error" in title_lower or "server error" in title_lower:
        return {"error_code": "NAV_SERVER_ERROR", "category": "ENV", "reason": "ASPNET_APPPOOL_ERROR", "is_terminal": True}

    if "errors.aspx" in url_lower or "error.aspx" in url_lower:
        return {"error_code": "NAV_SERVER_ERROR", "category": "ENV", "reason": "ASPNET_REDIRECT_TO_ERRORS_PAGE", "is_terminal": True}

    # DATA — grilla sin resultados (context: busqueda sin resultados)
    if "grid_empty" in exc_lower or "no rows" in exc_lower:
        return {"error_code": "NAV_DATA_GRID_EMPTY", "category": "DATA", "reason": "SEARCH_RESULTS_EMPTY", "is_terminal": True}

    # NAV — form no encontrado
    if "form_not_found" in exc_lower or "cannot read" in exc_lower:
        return {"error_code": "NAV_FORM_NOT_FOUND", "category": "NAV", "reason": "ASPNET_FORM_MISSING", "is_terminal": True}

    # NAV — timeout (puede ser transitorio)
    if "timeout" in exc_lower or "timed out" in exc_lower:
        return {"error_code": "NAV_TIMEOUT", "category": "NAV", "reason": "NAVIGATION_TIMEOUT", "is_terminal": False}

    # NAV — error generico de Playwright (posiblemente transitorio)
    return {"error_code": "NAV_PLAYWRIGHT_ERROR", "category": "NAV", "reason": "PLAYWRIGHT_EXCEPTION", "is_terminal": False}
```

Los errores `is_terminal=True` no deben reintentarse. Los `is_terminal=False` pueden reintentarse hasta `retries` veces.

#### 5.8.2. Integracion con `arrival_validator.ts`

El `ArrivalValidator` debe pasar el resultado de `checkNo500Response` y `checkNoAspnetError` como informacion adicional al `navigation_executor.ts` para que pueda clasificar correctamente el fallo.

#### 5.8.3. Actualizacion de `triage.json` con causa de navegacion

Cuando el veredicto es `FAIL` o `BLOCKED` y la causa esta en el bloque de navegacion, el `triage.json` debe incluir:

```json
{
  "triage_version": "1.0",
  "verdict": "BLOCKED",
  "category": "ENV",
  "reason": "ASPNET_APPPOOL_ERROR",
  "confidence": 0.97,
  "evidence": [
    "navigation_step_4 failed: NAV_SERVER_ERROR",
    "page title contains 'Runtime Error'",
    "HTTP response status 500 from FrmDetalleClie.aspx",
    "arrival_assertion 'no_aspnet_error' FAILED"
  ],
  "navigation_blame": {
    "step_index": 4,
    "method": "row_click",
    "error_code": "NAV_SERVER_ERROR",
    "category": "ENV",
    "reason": "ASPNET_APPPOOL_ERROR"
  },
  "owner": "infrastructure",
  "next_action": "Verificar logs del IIS Express. El app pool crasheo al navegar a FrmDetalleClie.aspx con CLCOD=12345. Verificar la excepcion en el Event Viewer de Windows o en los logs de la Agenda Web.",
  "publish_recommended": false,
  "human_approval_required": true
}
```

#### 5.8.4. Tests obligatorios

- `tests/unit/test_error_classifier_session_expired.py`
- `tests/unit/test_error_classifier_apppool_crash.py`
- `tests/unit/test_error_classifier_grid_empty.py`
- `tests/unit/test_error_classifier_timeout_not_terminal.py`
- `tests/unit/test_triage_includes_nav_blame.py`

---

### Sprint N5-09 — Actualizacion de `navigation_contracts.yml` a v2 con assertions y timeouts

**Objetivo:** Cerrar la brecha B-07. Migrar todos los contratos existentes al schema v2 con `arrival_assertions`, `timeouts` y `aspnet_error_markers` declarados.

**Duracion estimada:** 2 dias

#### 5.9.1. Archivos afectados

- `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_contracts.yml` — agregar campos v2 a todas las pantallas

#### 5.9.2. Pantallas a actualizar

| Pantalla | Cambios v2 |
|---|---|
| `FrmDetalleClie.aspx` | `arrival_assertions`, `timeouts`, `aspnet_error_markers` |
| `FrmBusqueda.aspx` | `arrival_assertions` minimos, `timeouts` |
| `FrmAgenda.aspx` | `arrival_assertions` minimos, `timeouts` |
| `FrmDetalleObligacion.aspx` | `arrival_assertions`, `timeouts`, steps detallados en `human_paths` |
| `FrmAgendaEquipo.aspx` | `arrival_assertions` minimos |
| `FrmAgendaJudicial.aspx` | `arrival_assertions` minimos |

#### 5.9.3. Script de migracion y validacion

Crear `Tools/Stacky/Stacky tools/QA UAT Agent/scripts/validate_navigation_contracts.py`:

```
python scripts/validate_navigation_contracts.py --contracts navigation_contracts.yml --schema schemas/NavigationContracts.v2.schema.json
```

Output esperado:

```json
{
  "ok": true,
  "screens_validated": 12,
  "screens_v2": 7,
  "screens_v1_legacy": 5,
  "warnings": ["FrmReportes.aspx no tiene arrival_assertions definidas"]
}
```

#### 5.9.4. Retrocompatibilidad

El resolver (v1) sigue funcionando con contratos v1. Los contratos v1 sin `arrival_assertions` reciben assertions minimas por defecto:
- `no_aspnet_error` (severity: hard, category: ENV)
- `no_login_redirect` (severity: hard, category: ENV)
- `url_contains:<screen_name_without_extension>` (severity: hard, category: NAV)

#### 5.9.5. Tests obligatorios

- `tests/unit/test_contracts_v2_schema_valid.py` — valida cada pantalla v2 contra el schema
- `tests/unit/test_contracts_v1_default_assertions.py` — verifica que pantallas v1 reciben assertions por defecto

---

### Sprint N5-10 — Evals de navegacion, anti-regresion y metricas

**Objetivo:** Crear el conjunto de evals que garantizan que ningun cambio futuro al pipeline de navegacion puede regresar los problemas resueltos.

**Duracion estimada:** 3 dias

#### 5.10.1. Fixtures de evals a crear

```
Tools/Stacky/Stacky tools/QA UAT Agent/evals/navigation/
  nav_direct_goto_violation_regression.json
  nav_detalleclie_human_path_allowed.json
  nav_detalleclie_no_clcod_blocked.json
  nav_detalleclie_uat_human_deeplink_rejected.json
  nav_busqueda_direct_entry_allowed.json
  nav_agenda_direct_entry_allowed.json
  nav_unknown_screen_safe_default.json
  nav_session_expired_env_classification.json
  nav_apppool_crash_env_classification.json
  nav_grid_empty_data_classification.json
  nav_arrival_assertion_aspnet_error.json
  nav_arrival_assertion_login_redirect.json
```

Estructura de cada eval fixture:

```json
{
  "eval_id": "nav_detalleclie_no_clcod_blocked",
  "description": "Sin CLCOD disponible, la navegacion a FrmDetalleClie.aspx debe bloquearse como DATA",
  "input": {
    "ticket_id": 120,
    "scenario_id": "P02",
    "target_screen": "FrmDetalleClie.aspx",
    "lane": "uat_human",
    "available_data": {}
  },
  "expected_output": {
    "decision": "BLOCKED",
    "category": "DATA",
    "reason": "NAVIGATION_DATA_MISSING",
    "missing_data": ["CLCOD"]
  },
  "tolerance": {
    "decision": "exact",
    "category": "exact",
    "reason": "exact"
  }
}
```

#### 5.10.2. Runner de evals

Crear `Tools/Stacky/Stacky tools/QA UAT Agent/scripts/run_navigation_evals.py`:

```
python scripts/run_navigation_evals.py --evals evals/navigation/ --verbose
```

Output esperado:

```json
{
  "ok": true,
  "total": 12,
  "passed": 12,
  "failed": 0,
  "unknown": 0,
  "results": [...]
}
```

Regla: `failed > 0` o `unknown > 0` bloquea el pipeline. Las evals de navegacion son una condicion necesaria para habilitar la generacion de specs para nuevos tickets.

#### 5.10.3. Metricas de navegacion a exponer

| Metrica | Formula | Target |
|---|---|---|
| `nav_direct_goto_violations` | specs con `goto()` directo a pantalla `direct_entry_allowed: false` | 0 |
| `nav_plan_missing_rate` | scenarios bloqueados por `NAVIGATION_PLAN_MISSING` | < 5% |
| `nav_arrival_assertion_fail_rate` | failures en arrival assertions por categoria | ENV < 2%, NAV < 10% |
| `nav_session_expired_rate` | runs bloqueados por sesion expirada | < 5% |
| `nav_apppool_crash_rate` | runs con `ASPNET_APPPOOL_ERROR` | 0 en QA estable |
| `nav_data_grid_empty_rate` | navigaciones fallidas por grilla vacia | trazable a DATA |
| `nav_step_p95_ms` | percentil 95 de tiempo de cada tipo de step | form_submit < 45s |
| `nav_eval_pass_rate` | porcentaje de evals de navegacion que pasan | 100% |

#### 5.10.4. Tests obligatorios

- `tests/unit/test_nav_evals_all_pass.py` — ejecuta todos los evals de navegacion y verifica que pasan
- `tests/regression/test_no_direct_goto_violations.py` — verifica que ningun spec existente en `evidence/` tiene `goto()` directo a pantalla `direct_entry_allowed: false`

---

## 6. Anti-patrones explicitos

Estos patrones estan **prohibidos** en cualquier cambio al QA UAT Agent. Si se detectan en revision de codigo o en generacion de specs, se debe abrir un bug P0.

### AP-01 — `page.goto(TARGET_SCREEN)` contra pantalla de sesion (P0)

```typescript
// PROHIBIDO
await page.goto(`${BASE_URL}FrmDetalleClie.aspx`, { waitUntil: 'domcontentloaded' });
// Razon: FrmDetalleClie.aspx tiene direct_entry_allowed: false.
// Provoca crash del app pool si se navega sin contexto de sesion.
```

### AP-02 — `page.goto()` en `beforeEach` para pantallas con `direct_entry_allowed: false` (P0)

```typescript
// PROHIBIDO en beforeEach para pantallas de sesion
test.beforeEach(async ({ page }) => {
  await page.goto(`${BASE_URL}${TARGET_SCREEN}`, ...);
  // Razon: beforeEach se ejecuta antes de que el navigation_plan
  // haya establecido el contexto de sesion correcto.
});
```

### AP-03 — `sleep(N)` en lugar de `waitFor*` (P1)

```typescript
// PROHIBIDO
await page.waitForTimeout(3000);
// Usar en cambio:
await waitForAgendaStable(page);
// o
await page.waitForURL(url => url.includes('FrmDetalleClie'), { timeout: 45_000 });
```

### AP-04 — Asumir que `storageState` es valido sin verificar (P1)

```typescript
// PROHIBIDO (en el cuerpo del test o en beforeEach sin guard)
// No hay verificacion de validez del auth antes de navegar.
// Usar:
await verifyStorageStateValid(120); // 120 minutos max age
```

### AP-05 — Clasificar `NAV_TIMEOUT` como diagnostico final (P1)

```python
# PROHIBIDO en triage.json
{
  "category": "NAV",
  "reason": "NAV_TIMEOUT"  # Nunca debe ser el reason final
}
# NAV_TIMEOUT es un error_code de la operacion de navegacion.
# El reason del triage debe ser el diagnostico causal:
# "SESSION_EXPIRED_LOGIN_REDIRECT", "ASPNET_APPPOOL_ERROR", "SEARCH_RESULTS_EMPTY", etc.
```

### AP-06 — Generator que ignora `navigation_plan` (P0)

```python
# PROHIBIDO en playwright_test_generator.py
context = {
  "pantalla": scenario["pantalla"],
  # navigation_plan no incluido en el contexto Jinja2
}
# Razon: el template renderizado sin navigation_plan usara el goto() fallback.
```

### AP-07 — Playbook sin `arrival_assertions` (P1)

```json
{
  "playbook_id": "...",
  "navigation_steps": [...],
  "arrival_assertions": []  // PROHIBIDO: lista vacia
}
// Todo playbook debe tener al menos no_aspnet_error y url_contains.
```

### AP-08 — Retry de errores terminales de navegacion (P1)

```python
# PROHIBIDO: reintentar cuando is_terminal=True
if error_code == "NAV_AUTH_EXPIRED":
    # No reintentar — es terminal. La sesion expiro.
    # Un retry solo desperdiciara tiempo y producira el mismo resultado.
    pass  # CORRECTO: terminar inmediatamente
```

### AP-09 — Inventar selectores en steps de navegacion sin ui_map (P0)

```python
# PROHIBIDO
navigation_step = {
  "method": "button_click",
  "selector": "#c_btnBuscarCliente"  # Inventado — no verificado contra ui_map
}
# Los selectores en steps de navegacion deben provenir del ui_map o
# de la seccion de assertions del navigation_contracts.yml.
```

### AP-10 — Publicar veredicto de navegacion sin evidence bundle completo (P1)

El veredicto de un run con fallo de navegacion no puede publicarse en ADO/Jira/Mantis sin:
- `navigation_plan.json`
- `navigation_step_results.json`
- `arrival_assertions.json`
- Al menos un screenshot por cada paso fallido

---

## 7. Casos de uso de referencia

### Caso A — `FrmDetalleClie.aspx` con CLCOD conocido (human_path, lane=uat_human)

**Contexto:** Ticket 120/P02, operador tiene CLCOD=12345, lane=uat_human.

**Paso a paso completo:**

1. `navigation_strategy_resolver.py` recibe:
   ```json
   { "target_screen": "FrmDetalleClie.aspx", "lane": "uat_human", "available_data": {"CLCOD": "12345"} }
   ```

2. Resolver lee contrato de `FrmDetalleClie.aspx`:
   - `direct_entry_allowed: false` → no se puede hacer goto
   - `deeplink_allowed: true` pero `forbidden_lanes: [uat_human]` → deeplink rechazado
   - `human_path_required_for_uat: true` → usar human_path
   - `human_paths.open_from_busqueda.required_data: [CLCOD]` → CLCOD disponible: OK

3. Resolver retorna `ALLOW_GENERATION strategy=human_path path_id=open_from_busqueda`.

4. `playbook_router.py` busca playbook para `FrmDetalleClie.aspx + "abrir detalle cliente"`:
   - Encuentra `open_detalle_cliente_from_busqueda.json` con score=7.

5. `navigation_plan_builder.py` construye `NavigationPlan` con 4 steps del playbook + arrival_assertions del contrato.

6. `navigation_plan_validator.py` valida el plan:
   - 4 steps, todos con method valido
   - `CLCOD` resuelto en data_bindings del step 2
   - `arrival_assertions` tiene `no_aspnet_error` y `url_contains`
   - Ningún `goto_direct` a pantalla `direct_entry_allowed: false`
   - OK

7. `playwright_test_generator.py` renderiza el template con el plan. El spec generado contiene:
   ```typescript
   const NAVIGATION_PLAN = {
     "strategy": "human_path",
     "steps": [
       { "step_index": 1, "method": "goto_direct", "target_url": "FrmBusqueda.aspx" },
       { "step_index": 2, "method": "fill", "selector": "#c_abfCliente", "data_bindings": {"value": "CLCOD"} },
       { "step_index": 3, "method": "button_click", "selector": "#c_btnBuscar" },
       { "step_index": 4, "method": "row_click", "selector": "#c_gvClientes tbody tr:nth-child(1) td" }
     ],
     "arrival_assertions": [...]
   };
   test.beforeEach(async ({ page }) => {
     await verifyStorageStateValid(120);
     const _navResult = await executeNavigationPlan(page, NAVIGATION_PLAN, {...});
     if (!_navResult.ok) throw new Error(...);
   });
   ```

8. Playwright ejecuta el spec. `executeNavigationPlan` navega paso a paso.

9. Al llegar al paso 4, verifica `intermediate_assertions`: la grilla tiene resultados. Click en la primera fila.

10. URL cambia a `FrmDetalleClie.aspx`. `arrival_validator.ts` verifica las 4 assertions: todas pasan.

11. El test body ejecuta los pasos de negocio (seleccionar provincia, guardar, etc.).

12. `execution.jsonl` contiene `navigation_plan_result` con `navigation_ok: true` y 4 `navigation_step_completed`.

13. `navigation_step_results.json` y `arrival_assertions.json` escritos en el evidence dir.

**Veredicto esperado:** `PASS` con confidence alta.

---

### Caso B — `FrmDetalleClie.aspx` sin CLCOD (bloqueo temprano)

**Contexto:** Ticket 120/P02, CLCOD no disponible, lane=uat_human.

**Paso a paso:**

1. `navigation_strategy_resolver.py` recibe:
   ```json
   { "target_screen": "FrmDetalleClie.aspx", "lane": "uat_human", "available_data": {} }
   ```

2. Resolver encuentra `human_paths.open_from_busqueda.required_data: [CLCOD]`.

3. `CLCOD` no esta en `available_data`. Retorna:
   ```json
   {
     "decision": "BLOCKED",
     "category": "DATA",
     "reason": "NAVIGATION_DATA_MISSING",
     "missing_data": ["CLCOD"],
     "human_action_required": "Proveer CLCOD en los datos de prueba. Es necesario para navegar via 'open_from_busqueda' a FrmDetalleClie.aspx."
   }
   ```

4. El pipeline registra el evento `navigation_contract_validation` con `decision=BLOCKED` en `execution.jsonl`.

5. El pipeline NO llama al playbook_router. NO llama al plan_builder. NO llama al validator. NO llama al generator. NO abre Playwright.

6. `result.json` contiene:
   ```json
   {
     "ok": false,
     "verdict": "BLOCKED",
     "category": "DATA",
     "reason": "NAVIGATION_DATA_MISSING",
     "failed_stage": "navigation_contract_validation",
     "runner_started": false,
     "human_action_required": "Proveer CLCOD en los datos de prueba.",
     "time_to_first_actionable_failure_ms": 45
   }
   ```

7. `triage.json` clasifica: `category=DATA`, `reason=NAVIGATION_DATA_MISSING`, `confidence=1.0`.

**Veredicto esperado:** `BLOCKED DATA` en menos de 1 segundo. Playwright no se abre.

---

### Caso C — `FrmBusqueda.aspx` con `direct_entry_allowed: true` (smoke)

**Contexto:** Ticket de smoke, pantalla `FrmBusqueda.aspx`, lane=smoke_deeplink.

**Paso a paso:**

1. Resolver lee contrato: `FrmBusqueda.aspx`, `direct_entry_allowed: true`.

2. Caso 0 del resolver: pantalla de entrada directa, sin human_path_required. Retorna:
   ```json
   { "decision": "ALLOW_GENERATION", "strategy": "direct_entry", "target_screen": "FrmBusqueda.aspx" }
   ```

3. `navigation_plan_builder.py` construye un plan simple con un unico step:
   ```json
   {
     "steps": [
       { "step_index": 1, "method": "goto_direct", "target_url": "FrmBusqueda.aspx", "wait_url_contains": "FrmBusqueda" }
     ],
     "arrival_assertions": [
       { "assertion_id": "no_aspnet_error", "type": "no_aspnet_error", "severity": "hard" },
       { "assertion_id": "url_contains_busqueda", "type": "url_contains", "expected_value": "FrmBusqueda" },
       { "assertion_id": "search_form_visible", "type": "dom_visible", "selector": "#c_btnBuscar" }
     ]
   }
   ```

4. Template genera:
   ```typescript
   const NAVIGATION_PLAN = { "strategy": "direct_entry", "steps": [...], "arrival_assertions": [...] };
   test.beforeEach(async ({ page }) => {
     // verifyStorageStateValid
     const _navResult = await executeNavigationPlan(page, NAVIGATION_PLAN, {...});
     // Para direct_entry: executeNavigationPlan ejecuta goto_direct
   });
   ```

5. El spec incluye el `goto_direct` pero solo para `FrmBusqueda.aspx`, que tiene `direct_entry_allowed: true`.

6. Arrival assertions verifican: no error ASP.NET, URL contiene `FrmBusqueda`, boton Buscar visible.

**Veredicto esperado:** Navegacion en < 3 segundos, `arrival_assertions: all_passed=true`.

---

## 8. Glosario

| Termino | Definicion |
|---|---|
| `arrival_assertion` | Verificacion obligatoria ejecutada despues de completar la navegacion a una pantalla. Puede ser de tipo URL, DOM, titulo o ausencia de error. |
| `NavigationPlan` | Artefacto JSON tipado que describe como llegar a una pantalla: entrypoint, pasos, metodos, datos y assertions. Es el contrato entre el resolver y el generator. |
| `navigation_plan_builder` | Modulo Python que construye un `NavigationPlan` a partir de una decision del resolver y/o un playbook. |
| `navigation_plan_validator` | Modulo Python que valida un `NavigationPlan` contra su JSON Schema antes de pasarlo al generator. |
| `human_path` | Estrategia de navegacion que simula el recorrido real de un usuario: entrypoint → formulario → busqueda → resultado → pantalla target. |
| `deeplink` | URL con parametros que permite llegar a una pantalla de sesion sin navegar por las pantallas intermedias, porque la pantalla reconstruye el contexto internamente desde los parametros. |
| `direct_entry` | Navegacion via `page.goto(screen)` valida solo para pantallas con `direct_entry_allowed: true`. |
| `direct_entry_allowed` | Atributo del contrato de navegacion que indica si una pantalla puede recibir un `page.goto()` directo sin crashear. |
| `YSOD` | Yellow Screen Of Death — pagina de error HTML que ASP.NET muestra cuando ocurre una excepcion no manejada. Detectado por titulo o contenido del body. |
| `ViewState` | Campo hidden de ASP.NET WebForms que contiene el estado del formulario serializado. Se pierde cuando se navega directamente a una pantalla sin haber pasado por el ciclo de postback correcto. |
| `EventValidation` | Campo hidden de ASP.NET que valida que el evento fue emitido por un control del formulario. Si no existe, ASP.NET rechaza el postback. |
| `UpdatePanel` | Control ASP.NET que realiza postbacks parciales via AJAX (ScriptManager). Requiere esperar `PageRequestManager.get_isInAsyncPostBack()` en vez de `waitForNavigation`. |
| `form.submit()` | Mecanismo primario de navegacion WebForms: ejecuta el submit del formulario ASP.NET directamente, bypaseando el ScriptManager. Mas confiable que `__doPostBack` en modo headless. |
| `storageState` | Archivo JSON de Playwright que contiene las cookies y el localStorage de una sesion autenticada. Producido por `global.setup.ts` y consumido por todos los specs. |
| `session_guard` | Helper que verifica que el `storageState` existe y no ha expirado antes de ejecutar navegacion que requiere sesion. |
| `NavigationDecision` | Output del `navigation_strategy_resolver.py`: decision de `ALLOW_GENERATION` o `BLOCKED` con la estrategia elegida. |
| `playbook` | Archivo JSON con schema validado que describe navegacion ejecutable + pasos de negocio para un goal especifico en una pantalla. Fuente primaria del `NavigationPlan`. |
| `lane` | Categoria de ejecucion que determina que estrategias de navegacion estan permitidas: `uat_human`, `smoke_deeplink`, `regression_deeplink`, `forensic_rerun`, etc. |
| `CLCOD` | Codigo de cliente en la Agenda Web. Parametro obligatorio para abrir `FrmDetalleClie.aspx`. Sin CLCOD, la navegacion se bloquea con `DATA NAVIGATION_DATA_MISSING`. |
| `navigation_contract_validation` | Evento de `execution.jsonl` emitido despues de que el resolver toma su decision. Es el primer gate del pipeline de navegacion. |
| `navigation_pipeline_summary` | Evento de `execution.jsonl` que resume el resultado completo del pipeline de navegacion para un escenario. |

---

## 9. Anexo A — Matriz completa de estrategias por (target_screen, lane, data)

| target_screen | lane | CLCOD disponible | Estrategia | Decision | Razon |
|---|---|---|---|---|---|
| FrmDetalleClie.aspx | uat_human | SI | human_path:open_from_busqueda | ALLOW | Todos los requisitos cumplidos |
| FrmDetalleClie.aspx | uat_human | NO | — | BLOCKED DATA | NAVIGATION_DATA_MISSING: CLCOD |
| FrmDetalleClie.aspx | smoke_deeplink | SI | deeplink | ALLOW | Lane permite deeplink, CLCOD disponible |
| FrmDetalleClie.aspx | smoke_deeplink | NO | — | BLOCKED DATA | DEEPLINK_PARAM_MISSING: CLCOD |
| FrmDetalleClie.aspx | uat_human_simulation | SI | human_path | ALLOW | Requiere human path, datos OK |
| FrmDetalleClie.aspx | regression_deeplink | SI | deeplink | ALLOW | Lane deeplink permitido |
| FrmDetalleClie.aspx | diagnostic | SI | deeplink | ALLOW | Lane diagnostic permite deeplink |
| FrmDetalleClie.aspx | forensic_rerun | SI | deeplink | ALLOW | Lane forensic permite deeplink |
| FrmBusqueda.aspx | uat_human | N/A | direct_entry | ALLOW | direct_entry_allowed=true |
| FrmBusqueda.aspx | smoke_deeplink | N/A | direct_entry | ALLOW | direct_entry_allowed=true |
| FrmAgenda.aspx | cualquier | N/A | direct_entry | ALLOW | direct_entry_allowed=true |
| FrmDetalleObligacion.aspx | uat_human | SI (CLCOD+OBLCOD) | human_path:open_from_detalle_cliente | ALLOW | Requiere pantalla intermedia |
| FrmDetalleObligacion.aspx | uat_human | CLCOD SI, OBLCOD NO | — | BLOCKED DATA | NAVIGATION_DATA_MISSING: OBLCOD |
| FrmDetalleObligacion.aspx | smoke_deeplink | — | — | BLOCKED NAV | DEEPLINK_NOT_SUPPORTED_FOR_SCREEN |
| Pantalla sin contrato | uat_human | cualquier | — | BLOCKED NAV | NAV_CONTRACT_MISSING |
| Pantalla sin contrato | smoke_deeplink | cualquier | direct_entry + warning | ALLOW (con warning) | Fallback seguro para lanes no-human |

---

## 10. Anexo B — Checklist de navegacion

### Pre-navegacion (antes de abrir el browser)

| # | Check | Herramienta | Categoria de fallo |
|---|---|---|---|
| 1 | `navigation_contracts.yml` cargado y parseado sin errores | `navigation_strategy_resolver._load_contracts()` | PIP |
| 2 | Contrato para `target_screen` existe | resolver | NAV |
| 3 | Lane es compatible con la estrategia declarada | resolver | PIP |
| 4 | Datos requeridos para la estrategia disponibles en `available_data` | resolver | DATA |
| 5 | `NavigationPlan` construido y validado contra schema | `navigation_plan_validator` | PIP |
| 6 | `storageState` existe y no expiro | `session_guard.py` | ENV |
| 7 | `playbook` encontrado o `human_paths` del contrato como fallback | `playbook_router` | PIP |

### Durante navegacion (en ejecucion del NavigationPlan)

| # | Check | Herramienta | Categoria de fallo |
|---|---|---|---|
| 8 | URL actual no contiene `frmlogin` antes del primer paso | `arrival_validator.checkNoLoginRedirect()` | ENV |
| 9 | Despues de cada step: intermediate_assertions pasan | `ArrivalValidator.validateAll()` | NAV/DATA/ENV |
| 10 | Si step es `form_submit`: verificar que `<form>` existe en el DOM antes del execute | `navigateViaFormSubmit` | NAV |
| 11 | Si step es `row_click`: verificar que la grilla tiene al menos una fila antes del click | intermediate_assertion `dom_visible(grid_row)` | DATA |
| 12 | Timeout por step: no mas de `timeout_ms` del plan, no un valor hardcodeado | `NavigationStep.timeout_ms` | — |
| 13 | Error `is_terminal=true`: NO reintentar | `_classify_error(is_terminal)` | — |
| 14 | Screenshot capturado en cada fallo de step | `NavigationDriver._screenshot()` | OBS |

### Post-navegacion (despues del ultimo paso)

| # | Check | Herramienta | Categoria de fallo |
|---|---|---|---|
| 15 | `no_aspnet_error`: titulo de pagina no contiene "Runtime Error" | `ArrivalValidator.checkNoAspnetError()` | ENV |
| 16 | `no_login_redirect`: URL no contiene `frmlogin` | `ArrivalValidator.checkNoLoginRedirect()` | ENV |
| 17 | `url_contains:<screen_name>`: URL contiene el nombre de la pantalla target | `ArrivalValidator.checkUrlContains()` | NAV |
| 18 | `dom_visible:<panel_selector>`: panel principal de la pantalla visible | `ArrivalValidator.checkDomVisible()` | APP |
| 19 | `arrival_assertions.json` escrito en el evidence dir | `navigation_executor` | OBS |
| 20 | `navigation_step_results.json` escrito | `navigation_executor` | OBS |
| 21 | Evento `navigation_plan_result` emitido en `execution.jsonl` | pipeline orchestrator | OBS |

---

## 11. Anexo C — Mapping de severidades y categorias de navegacion

| Error Code | Categoria | Reason | is_terminal | Descripcion | Accion humana |
|---|---|---|---|---|---|
| `NAV_AUTH_EXPIRED` | ENV | SESSION_EXPIRED_LOGIN_REDIRECT | true | Redirigido a FrmLogin durante navegacion | Re-ejecutar el pipeline para refrescar el storageState |
| `NAV_SERVER_ERROR` | ENV | ASPNET_APPPOOL_ERROR | true | HTTP 5xx o YSOD detectado | Verificar logs del IIS/App Pool. Problema en la aplicacion, no en el test. |
| `NAV_SERVER_ERROR` | ENV | ASPNET_REDIRECT_TO_ERRORS_PAGE | true | URL cambio a Errors.aspx o Error.aspx | Idem anterior. Navegar manualmente y confirmar el error. |
| `NAV_STORAGESTATE_MISSING` | ENV | STORAGESTATE_FILE_NOT_FOUND | true | Archivo `.auth/agenda.json` no existe | Ejecutar `global.setup.ts` antes de correr los tests. |
| `NAV_STORAGESTATE_EXPIRED` | ENV | STORAGESTATE_MAX_AGE_EXCEEDED | true | storageState mas antiguo que el TTL | Re-ejecutar el pipeline para refrescar la sesion. |
| `NAV_DATA_GRID_EMPTY` | DATA | SEARCH_RESULTS_EMPTY | true | La grilla de busqueda no retorno resultados para el dato dado | Verificar que CLCOD existe en el ambiente de prueba. Usar el seed SQL o pedir dato al usuario. |
| `NAV_DATA_MISSING` | DATA | NAVIGATION_DATA_MISSING | true | Datos requeridos por el human_path no disponibles | Proveer los datos faltantes en el payload de ejecucion. |
| `NAV_FORM_NOT_FOUND` | NAV | ASPNET_FORM_MISSING | true | `<form>` no encontrado en el DOM para ejecutar form.submit | Verificar que la pagina cargo correctamente. Puede indicar pantalla incorrecta. |
| `NAV_CONTRACT_MISSING` | NAV | NAV_CONTRACT_MISSING | true | Pantalla sin contrato en navigation_contracts.yml | Agregar contrato para la pantalla o usar lane no-human. |
| `NAV_PATH_MISSING` | NAV | NAV_PATH_MISSING | true | No existe human_path definido para la pantalla en el lane | Definir human_path en navigation_contracts.yml. |
| `DEEPLINK_NOT_SUPPORTED` | NAV | DEEPLINK_NOT_SUPPORTED_FOR_SCREEN | true | La pantalla no admite deeplink | Usar human_path o cambiar de lane. |
| `INVALID_STRATEGY_FOR_LANE` | PIP | INVALID_NAVIGATION_STRATEGY_FOR_LANE | true | La estrategia elegida no es compatible con el lane | Cambiar el lane o la estrategia. |
| `NAV_TIMEOUT` | NAV | NAVIGATION_TIMEOUT | false (retriable) | Timeout de un paso de navegacion sin causa identificada | Revisar logs del servidor. Puede ser transitorio. Aumentar timeout o investigar slowness. |
| `NAV_PLAYWRIGHT_ERROR` | NAV | PLAYWRIGHT_EXCEPTION | false (retriable) | Excepcion inesperada de Playwright | Revisar el trace de Playwright. Puede ser un flake de selector. |
| `ARRIVAL_ASSERTION_FAILED` | NAV/APP/ENV | Segun `category_on_fail` | true | Una assertion de llegada fallo despues de la navegacion | Analizar el screenshot post-navegacion y el `arrival_assertions.json` para determinar que assertion especifica fallo. |

---

## 12. Resumen de sprints y dependencias

| Sprint | Titulo | Dias | Depende de | Brechas que cierra |
|---|---|---|---|---|
| N5-01 | Eliminar `goto()` incondicionales del template | 3 | Ninguno | B-01, B-02, B-03 |
| N5-02 | `navigation_plan_validator.py` y schemas | 2 | N5-01 | B-04 |
| N5-03 | Helpers TypeScript: `navigation_executor`, `arrival_validator`, `session_guard` | 4 | N5-01 | B-05, B-09 |
| N5-04 | Playbooks ejecutables para pantallas criticas | 3 | N5-02 | B-06 |
| N5-05 | Integracion end-to-end del pipeline de navegacion | 4 | N5-02, N5-03, N5-04 | B-04 (completo) |
| N5-06 | Observabilidad: `navigation_step_results.json` y `arrival_assertions.json` | 2 | N5-03, N5-05 | B-08 |
| N5-07 | Gestion de sesion expirada y `session_expiry_detector` | 2 | N5-03 | B-09 |
| N5-08 | Clasificacion deterministica de errores NAV/ENV/DATA | 3 | N5-03, N5-05 | B-07 (parcial) |
| N5-09 | Actualizacion de `navigation_contracts.yml` a v2 | 2 | N5-02 | B-07 |
| N5-10 | Evals de navegacion, anti-regresion y metricas | 3 | N5-05, N5-08 | todos los P2 |

**Total estimado:** 28 dias de desarrollo incremental. Cada sprint es ejecutable independientemente.

**Orden critico:** N5-01 es el prerequisito de todo. N5-02 y N5-03 pueden hacerse en paralelo despues de N5-01. N5-05 requiere N5-02, N5-03 y N5-04 completos.

---

*Documento generado el 2026-05-11. Proximo roadmap: SEXTA parte — grabacion de sesiones de usuario y conversion automatica a playbooks.*
