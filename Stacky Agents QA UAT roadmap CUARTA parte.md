# Prompt para Arquitecto — Mejoras críticas de navegación y confiabilidad en Stacky QA UAT Agent

## Rol que debés asumir

Actuá como **Arquitecto Senior de QA Automation, Playwright, Python, WebForms/ASP.NET legacy, diseño de agentes y análisis forense de pipelines**.

Tu tarea es diseñar e implementar una mejora estructural del **Stacky QA UAT Agent** para que sus pruebas UAT sean confiables, trazables, escalables y fieles al comportamiento de un usuario humano real.

No quiero una mejora cosmética. Quiero que conviertas la navegación del QA UAT Agent en un sistema gobernado por contratos, estrategias explícitas y evidencia forense.

---

## Contexto del sistema

Stacky Agents es un workbench de agentes donde el humano selecciona agentes, ejecuta runs, revisa outputs y aprueba o descarta publicaciones. Dentro de Stacky Agents existe una tool llamada **QA UAT Agent**, basada en Python + Playwright, que genera y ejecuta pruebas UAT sobre tickets.

El QA UAT Agent actualmente tiene o debería tener stages como:

- lectura de ticket;
- detección de pantalla;
- UI map cacheado;
- compilación de escenarios;
- generación Playwright;
- ejecución;
- análisis de logs;
- dossier/evidencia;
- publicación opcional en ADO/Jira/Mantis;
- `execution.jsonl` como evidencia principal.

El objetivo del ecosistema Stacky no es reemplazar al humano: el humano sigue en el loop. El sistema debe producir evidencia clara para que el humano pueda decidir.

---

## Problema real detectado en ticket 120

Luego de una reestructuración del QA UAT Agent, el ticket 120 volvió a fallar. El diagnóstico superficial fue:

```text
ENV / PAGE_LOAD_FAILED
```

Pero el análisis forense posterior encontró que ese diagnóstico era incompleto.

### Qué ocurrió realmente

Los 8 escenarios del ticket 120 fallaron en `beforeEach`, antes de ejecutar pasos de negocio. El `globalSetup` pudo hacer login correctamente, por lo tanto IIS estaba vivo al inicio. Luego los tests intentaron navegar directamente a:

```text
FrmDetalleClie.aspx
```

El problema era que `FrmDetalleClie.aspx` dependía de contexto de sesión ASP.NET que normalmente se setea al pasar por una pantalla previa, como:

```text
FrmBusqueda.aspx -> buscar cliente -> seleccionar resultado -> FrmDetalleClie.aspx
```

Al entrar directo, la pantalla no tenía variables de sesión como cliente seleccionado, contexto de navegación u otros datos necesarios. Eso provocó una excepción no manejada en la app legacy y terminó causando caída/crash del IIS Express/app pool.

### Causa raíz real

La causa raíz primaria no fue ENV. Fue:

```text
NAV / INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN
```

Con consecuencia secundaria:

```text
ENV / APP_POOL_CRASH_AFTER_INVALID_NAVIGATION
```

El triage clasificó el síntoma final, pero no la causa raíz causal.

---

## Cambio reciente de producto

Ya se adaptó `FrmDetalleClie.aspx` para soportar **deeplink**.

Esto significa que ahora puede existir una ruta del tipo:

```text
FrmDetalleClie.aspx?clcod={CLCOD}
```

Pero esto NO significa que todos los UAT deban usar deeplink.

La arquitectura debe distinguir entre:

1. navegación humana real;
2. navegación por deeplink;
3. navegación técnica/diagnóstica;
4. navegación de smoke/regression acelerada;
5. navegación inválida.

---

## Objetivo principal

Diseñar e implementar un sistema de navegación robusto para Stacky QA UAT Agent que impida que el generator vuelva a producir navegación incorrecta.

El objetivo es que cada escenario declare explícitamente **cómo llega a la pantalla** y que el pipeline valide esa estrategia antes de generar o ejecutar Playwright.

El resultado esperado es que Stacky QA UAT pueda decidir:

```text
Este escenario debe simular al humano real, por lo tanto usa FrmBusqueda -> buscar cliente -> seleccionar -> FrmDetalleClie.
```

O:

```text
Este escenario es smoke/regression técnico, puede usar deeplink FrmDetalleClie.aspx?clcod=123, pero debe validar que el contexto se reconstruyó correctamente.
```

O:

```text
No puedo ejecutar: falta CLCOD, falta nav_path, el deeplink no reconstruye contexto o la estrategia elegida no está permitida para este lane.
```

---

# Mejoras requeridas

## 1. Crear contratos de navegación por pantalla

Crear un contrato declarativo, por ejemplo:

```text
navigation_contracts.yml
```

o nombre equivalente.

Debe permitir declarar por pantalla:

- si admite direct entry;
- si admite deeplink;
- qué parámetros requiere el deeplink;
- qué contexto debe reconstruir;
- qué lanes pueden usar deeplink;
- qué lanes deben usar navegación humana;
- qué nav paths humanos están aprobados;
- qué datos mínimos requiere cada path;
- qué assertions post-navegación son obligatorias.

Ejemplo esperado:

```yaml
FrmDetalleClie.aspx:
  screen_type: detail
  direct_entry_allowed: true
  deeplink_allowed: true
  human_path_required_for_uat: true

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
      - regression
      - diagnostic
      - forensic_rerun
    forbidden_lanes:
      - uat_human
      - uat_human_simulation

  human_paths:
    open_from_busqueda:
      entrypoint: FrmBusqueda.aspx
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

### Reglas no negociables

- Ningún spec puede generarse sin `navigation_strategy` explícita.
- Si `lane=uat_human` o `lane=uat_human_simulation`, no se debe usar deeplink salvo override humano explícito y auditado.
- Si una pantalla requiere contexto y no hay nav path ni deeplink válido, el pipeline debe bloquear antes de Playwright.
- Si faltan datos para navegar, el bloqueo debe ser `DATA`, no `NAVIGATION_TIMEOUT`.

---

## 2. Crear `navigation_strategy_resolver.py`

Crear un módulo Python responsable de decidir la estrategia de navegación para cada escenario.

### Entrada esperada

```json
{
  "ticket_id": 120,
  "scenario_id": "P02",
  "target_screen": "FrmDetalleClie.aspx",
  "lane": "uat_human",
  "available_data": {
    "CLCOD": "12345"
  },
  "navigation_contracts": "navigation_contracts.yml"
}
```

### Salida para navegación humana

```json
{
  "decision": "ALLOW_GENERATION",
  "strategy": "human_path",
  "path_id": "open_from_busqueda",
  "entrypoint": "FrmBusqueda.aspx",
  "target_screen": "FrmDetalleClie.aspx",
  "deeplink_available": true,
  "deeplink_rejected_reason": "lane_requires_human_simulation",
  "requires_data": ["CLCOD"],
  "data_available": true
}
```

### Salida para deeplink

```json
{
  "decision": "ALLOW_GENERATION",
  "strategy": "deeplink",
  "target_screen": "FrmDetalleClie.aspx",
  "url": "FrmDetalleClie.aspx?clcod=12345",
  "required_context_assertions": [
    "selected_client_loaded",
    "permissions_valid",
    "detalle_cliente_visible",
    "no_server_error"
  ]
}
```

### Salida bloqueada por datos faltantes

```json
{
  "decision": "BLOCKED",
  "verdict": "BLOCKED",
  "category": "DATA",
  "reason": "NAVIGATION_DATA_MISSING",
  "missing_data": ["CLCOD"],
  "human_action_required": "Proveer CLCOD válido o generar seed de datos"
}
```

### Salida bloqueada por estrategia inválida

```json
{
  "decision": "BLOCKED",
  "verdict": "BLOCKED",
  "category": "PIP",
  "reason": "INVALID_NAVIGATION_STRATEGY_FOR_LANE",
  "lane": "uat_human",
  "strategy": "deeplink",
  "human_action_required": "Usar human_path o aprobar override manual auditado"
}
```

---

## 3. Agregar validación de navegación antes del generator

Agregar un stage explícito antes de generar Playwright:

```text
navigation_contract_validation
```

Debe registrar en `execution.jsonl` un evento como:

```json
{
  "event": "navigation_contract_validation",
  "ticket_id": 120,
  "scenario_id": "P02",
  "target_screen": "FrmDetalleClie.aspx",
  "lane": "uat_human",
  "strategy": "human_path",
  "path_id": "open_from_busqueda",
  "direct_goto_allowed": false,
  "deeplink_available": true,
  "deeplink_used": false,
  "requires_data": ["CLCOD"],
  "data_available": true,
  "decision": "ALLOW_GENERATION"
}
```

Si falla:

```json
{
  "event": "navigation_contract_validation",
  "ticket_id": 120,
  "scenario_id": "P02",
  "target_screen": "FrmDetalleClie.aspx",
  "lane": "uat_human",
  "decision": "BLOCKED",
  "category": "NAV",
  "reason": "NAV_PATH_MISSING",
  "human_action_required": "Crear playbook open_from_busqueda para FrmDetalleClie.aspx"
}
```

---

## 4. Prohibir `page.goto()` directo no gobernado

El generator no debe emitir:

```ts
await page.goto('/FrmDetalleClie.aspx');
```

salvo que la estrategia resuelta sea explícitamente `deeplink`, `direct_entry` o `diagnostic` y el contrato lo permita.

Para `uat_human`, debe emitir algo como:

```ts
await clienteFlow.openDetalleFromBusqueda({ clcod: testData.CLCOD });
```

Para `smoke_deeplink`, debe emitir algo como:

```ts
await clienteFlow.openDetalleByDeeplink({ clcod: testData.CLCOD });
```

---

## 5. Crear Flow Objects Playwright

Crear una capa de **Flow Objects** para navegación de negocio. No meter navegación compleja directamente en specs generados.

Ejemplo esperado:

```ts
export class ClienteFlow {
  constructor(private page: Page) {}

  async openDetalleFromBusqueda(data: { clcod: string }) {
    await this.page.goto('/FrmBusqueda.aspx');

    await this.page.getByLabel(/cliente/i).fill(data.clcod);
    await this.page.getByRole('button', { name: /buscar/i }).click();

    const row = this.page
      .locator('[data-testid="grid-clientes"] tr')
      .filter({ hasText: data.clcod })
      .first();

    await expect(row).toBeVisible();
    await row.click();

    const detalle = new FrmDetalleCliePage(this.page);
    await detalle.assertLoadedForClient(data.clcod);
  }

  async openDetalleByDeeplink(data: { clcod: string }) {
    await this.page.goto(`/FrmDetalleClie.aspx?clcod=${encodeURIComponent(data.clcod)}`);

    const detalle = new FrmDetalleCliePage(this.page);
    await detalle.assertLoadedForClient(data.clcod);
  }
}
```

También crear Page Object:

```ts
export class FrmDetalleCliePage {
  constructor(private page: Page) {}

  async assertLoadedForClient(clcod: string) {
    await expect(this.page).toHaveURL(/FrmDetalleClie\.aspx/);
    await expect(this.page.getByText(clcod)).toBeVisible();
    await expect(this.page.getByRole('heading', { name: /detalle/i })).toBeVisible();
  }
}
```

Si la app todavía no tiene `data-testid`, usar locators por role/label/text y dejar recomendado agregar hooks automation-friendly.

---

## 6. Agregar `deeplink_readiness_check`

Antes de usar deeplink, validar que realmente reconstruye contexto y no solo carga una URL.

Evento esperado:

```json
{
  "event": "deeplink_readiness_check",
  "ticket_id": 120,
  "screen": "FrmDetalleClie.aspx",
  "url_pattern": "FrmDetalleClie.aspx?clcod={CLCOD}",
  "params": {
    "CLCOD": "12345"
  },
  "checks": {
    "http_status_ok": true,
    "redirected_to_login": false,
    "selected_client_context_loaded": true,
    "permission_check_passed": true,
    "business_root_visible": true,
    "server_error_visible": false
  },
  "decision": "PASS"
}
```

Si falla:

```json
{
  "event": "deeplink_readiness_check",
  "ticket_id": 120,
  "screen": "FrmDetalleClie.aspx",
  "decision": "BLOCKED",
  "category": "NAV",
  "reason": "DEEPLINK_CONTEXT_NOT_RECONSTRUCTED",
  "missing_context": ["selected_client"],
  "human_action_required": "Corregir deeplink o usar human_path"
}
```

---

## 7. Mejorar Data Readiness orientado a navegación

Antes de navegar, validar datos necesarios:

Para `FrmDetalleClie.aspx`:

- `CLCOD` existe;
- el usuario QA puede acceder al cliente;
- el cliente tiene las obligaciones necesarias para RF-007;
- la búsqueda humana devolvería al menos una fila;
- el deeplink reconstruiría el mismo cliente.

Evento esperado:

```json
{
  "event": "navigation_data_readiness",
  "ticket_id": 120,
  "scenario_id": "P02",
  "screen": "FrmDetalleClie.aspx",
  "strategy": "human_path",
  "required_data": ["CLCOD"],
  "checks": [
    {"name": "cliente_exists", "passed": true},
    {"name": "user_can_access_cliente", "passed": true},
    {"name": "cliente_has_obligaciones", "passed": true},
    {"name": "busqueda_returns_client", "passed": true}
  ],
  "decision": "PASS"
}
```

Si falta data:

```json
{
  "event": "navigation_data_readiness",
  "decision": "BLOCKED",
  "category": "DATA",
  "reason": "NAVIGATION_DATA_MISSING",
  "missing_data": ["CLCOD"],
  "resolution_options": [
    "ask_user_for_clcod",
    "generate_safe_seed_sql",
    "use_known_fixture"
  ]
}
```

---

## 8. Mejorar triage causal

Modificar `failure_triage.py` o equivalente para que no clasifique ingenuamente:

```text
page.goto timeout -> ENV / PAGE_LOAD_FAILED
```

Debe mirar cadena causal.

### Clasificaciones nuevas requeridas

| Reason | Category | Cuándo usar |
|---|---|---|
| `INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN` | NAV | spec usó direct goto contra pantalla con contexto obligatorio |
| `INVALID_NAVIGATION_STRATEGY_FOR_LANE` | PIP | se usó deeplink en lane que exige human path |
| `NAV_PATH_MISSING` | NAV | no existe camino humano aprobado |
| `NAVIGATION_DATA_MISSING` | DATA | faltan datos para navegar |
| `DEEPLINK_PARAM_MISSING` | DATA | falta parámetro del deeplink |
| `DEEPLINK_ENTITY_NOT_FOUND` | DATA | CLCOD no existe |
| `DEEPLINK_PERMISSION_DENIED` | DATA o APP | usuario no puede ver entidad |
| `DEEPLINK_CONTEXT_NOT_RECONSTRUCTED` | NAV | URL carga pero no setea contexto esperado |
| `DEEPLINK_SERVER_ERROR` | APP | deeplink válido rompe servidor |
| `HUMAN_PATH_STEP_FAILED` | NAV | falló búsqueda/click/selección |
| `HUMAN_PATH_GRID_EMPTY` | DATA | búsqueda no devuelve filas |
| `APP_POOL_CRASH_AFTER_INVALID_NAVIGATION` | ENV secundaria | consecuencia de navegación inválida |

### Regla crítica

Si `globalSetup` login OK y luego falla navegación directa a pantalla que requiere contexto, la clasificación primaria debe ser NAV, no ENV.

Ejemplo:

```json
{
  "verdict": "BLOCKED",
  "primary_category": "NAV",
  "primary_reason": "INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN",
  "secondary_category": "ENV",
  "secondary_reason": "APP_POOL_CRASH_AFTER_INVALID_NAVIGATION",
  "next_action": "Usar nav_path open_from_busqueda o deeplink gobernado"
}
```

---

## 9. Agregar evidencia de navegación

Todo run debe dejar:

```text
navigation_summary.json
navigation_contract_validation.json
navigation_data_readiness.json
```

Y eventos en `execution.jsonl`.

Ejemplo de summary:

```json
{
  "ticket_id": 120,
  "scenario_id": "P02",
  "target_screen": "FrmDetalleClie.aspx",
  "strategy": "human_path",
  "path_id": "open_from_busqueda",
  "direct_goto_used": false,
  "deeplink_available": true,
  "deeplink_used": false,
  "context_assertions": {
    "selected_client_loaded": true,
    "permissions_valid": true,
    "business_root_visible": true
  },
  "duration_ms": 7421
}
```

Para deeplink:

```json
{
  "ticket_id": 120,
  "scenario_id": "P02",
  "target_screen": "FrmDetalleClie.aspx",
  "strategy": "deeplink",
  "url": "FrmDetalleClie.aspx?clcod=12345",
  "human_path_available": true,
  "human_path_used": false,
  "context_assertions": {
    "selected_client_loaded": true,
    "permissions_valid": true,
    "business_root_visible": true
  },
  "duration_ms": 1832
}
```

---

## 10. Separar lanes de navegación

Agregar o formalizar lanes:

```text
uat_human
smoke_deeplink
regression_deeplink
diagnostic
forensic_rerun
```

### Reglas esperadas

| Lane | Navegación permitida | Objetivo |
|---|---|---|
| `uat_human` | human_path | simular operador real |
| `smoke_deeplink` | deeplink | validar carga rápida de pantalla/contexto |
| `regression_deeplink` | deeplink o human_path | regresión focalizada |
| `diagnostic` | deeplink/direct si contrato permite | diagnóstico técnico |
| `forensic_rerun` | repetir estrategia original o forzar estrategia aprobada | reproducir/aislar falla |

---

# Archivos/módulos a analizar y probablemente modificar

Analizá el repo y ubicá los equivalentes reales. Como mínimo revisar:

```text
qa_uat_pipeline.py
uat_scenario_compiler.py
playwright_test_generator.py
failure_triage.py
log_analyzer.py
ui_map_builder.py
agenda_screens.py
execution_logger.py
uat_precondition_checker.py
nav_helper.ts o helper Playwright equivalente
templates Playwright
cache/ui_maps/
playbooks/ si existe
```

Si algún archivo no existe, proponer su creación.

---

# Tests obligatorios

## Unit tests

```text
test_navigation_strategy_required_for_every_scenario
test_frm_detalle_clie_deeplink_contract_requires_clcod
test_uat_human_rejects_deeplink_strategy
test_smoke_deeplink_allows_deeplink_strategy
test_navigation_resolver_returns_human_path_for_uat
test_navigation_resolver_returns_deeplink_for_smoke
test_navigation_resolver_blocks_missing_clcod
test_generator_never_emits_direct_goto_without_strategy
test_generator_uses_cliente_flow_for_human_path
test_generator_uses_deeplink_flow_for_smoke_deeplink
test_deeplink_readiness_context_not_reconstructed_blocks_nav
test_triage_login_ok_then_direct_goto_timeout_is_nav_not_env
test_triage_server_down_before_login_is_env
test_navigation_summary_written
```

## Regression fixture para ticket 120

Crear fixture:

```text
fixtures/ticket_120/direct_goto_frm_detalle_crashes_iis/
```

Expected:

```json
{
  "verdict": "BLOCKED",
  "primary_category": "NAV",
  "primary_reason": "INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN",
  "secondary_category": "ENV",
  "secondary_reason": "APP_POOL_CRASH_AFTER_INVALID_NAVIGATION",
  "business_steps_executed": 0
}
```

Crear fixture adicional:

```text
fixtures/ticket_120/deeplink_valid/
```

Expected:

```json
{
  "verdict": "PASS_OR_CONTINUE_TO_BUSINESS_STEPS",
  "navigation_strategy": "deeplink",
  "deeplink_context_loaded": true,
  "direct_goto_used": false
}
```

Crear fixture:

```text
fixtures/ticket_120/uat_human_valid/
```

Expected:

```json
{
  "navigation_strategy": "human_path",
  "path_id": "open_from_busqueda",
  "direct_goto_used": false,
  "business_steps_executed": 8
}
```

---

# Criterios de aceptación

La mejora se considera aceptada solo si:

1. Ningún escenario se genera sin `navigation_strategy`.
2. `uat_human` no usa deeplink salvo override humano auditado.
3. `smoke_deeplink` puede usar `FrmDetalleClie.aspx?clcod={CLCOD}`.
4. El deeplink se valida con `deeplink_readiness_check` antes de usarlo masivamente.
5. El generator no emite `page.goto('/FrmDetalleClie.aspx')` directo no gobernado.
6. La navegación humana usa Flow Object o helper aprobado.
7. Si falta CLCOD, el resultado es `BLOCKED / DATA / NAVIGATION_DATA_MISSING`.
8. Si falta nav path, el resultado es `BLOCKED / NAV / NAV_PATH_MISSING`.
9. Si se detecta direct goto inválido, el resultado es `BLOCKED / NAV / INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN`.
10. Si el servidor estaba caído antes del login, recién ahí clasifica `ENV / SERVER_UNREACHABLE_BEFORE_TEST`.
11. `navigation_summary.json` se genera por escenario.
12. `execution.jsonl` contiene eventos de navegación.
13. Ticket 120 no vuelve a diagnosticarse como `ENV / PAGE_LOAD_FAILED` primario cuando la causa sea navegación inválida.
14. Los tests unitarios y regression fixtures pasan.
15. El dossier final explica al humano qué estrategia de navegación se usó y por qué.

---

# Entregables esperados del arquitecto

Tu respuesta/PR debe incluir:

1. Diagnóstico de arquitectura actual.
2. Diseño técnico propuesto.
3. Nuevos contratos YAML/JSON.
4. Nuevos módulos Python.
5. Cambios al generator Playwright.
6. Flow Objects TypeScript.
7. Eventos nuevos en `execution.jsonl`.
8. Cambios al triage.
9. Tests unitarios y fixtures.
10. Plan de migración para pantallas existentes.
11. Riesgos y mitigaciones.
12. Criterios de aceptación verificados.

---

# Restricciones

No propongas recomendaciones genéricas.

No digas “mejorar navegación” sin especificar:

- qué contrato;
- qué evento;
- qué archivo;
- qué test;
- qué reason;
- qué criterio de aceptación.

No subas timeouts como solución principal.

No clasifiques todo `page.goto timeout` como ENV.

No uses deeplink para UAT humano por defecto.

No permitas specs sin evidencia de navegación.

No permitas auto-healing o cambio de selector sin aprobación humana.

No publiques a ADO/Jira/Mantis sin aprobación humana.

---

# Resultado ideal para el próximo run del ticket 120

## Si corre como `uat_human`

```json
{
  "ticket_id": 120,
  "lane": "uat_human",
  "navigation_strategy": "human_path",
  "path_id": "open_from_busqueda",
  "target_screen": "FrmDetalleClie.aspx",
  "clcod": "12345",
  "deployment_fingerprint": "matched",
  "navigation_data_readiness": "passed",
  "business_steps_executed": 8,
  "direct_goto_used": false,
  "navigation_timeout_count": 0
}
```

## Si corre como `smoke_deeplink`

```json
{
  "ticket_id": 120,
  "lane": "smoke_deeplink",
  "navigation_strategy": "deeplink",
  "target_screen": "FrmDetalleClie.aspx",
  "url": "FrmDetalleClie.aspx?clcod=12345",
  "deeplink_context_loaded": true,
  "selected_client_loaded": true,
  "business_root_visible": true,
  "direct_goto_used": false
}
```

## Si no puede correr

```json
{
  "ticket_id": 120,
  "verdict": "BLOCKED",
  "category": "DATA|NAV|PIP|ENV",
  "reason": "precise_reason",
  "runner_started": false,
  "human_action_required": "acción concreta"
}
```

---

# Espíritu del cambio

No estamos intentando que Playwright “haga clicks mejor”. Estamos intentando que Stacky QA UAT entienda la navegación como parte del dominio.

El sistema debe saber que:

- hay pantallas entrypoint;
- hay pantallas dependientes de sesión;
- hay deeplinks seguros;
- hay navegación humana real;
- hay lanes que priorizan fidelidad;
- hay lanes que priorizan velocidad;
- hay datos mínimos para navegar;
- hay fallas de navegación que no son ambiente;
- hay evidencia que el humano necesita para decidir.

El objetivo final es que Stacky QA UAT deje de hacer:

```text
page.goto y esperar
```

Y pase a hacer:

```text
resolver estrategia -> validar datos -> navegar con contrato -> afirmar contexto -> ejecutar negocio -> evidenciar resultado
```

