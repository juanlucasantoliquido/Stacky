# Stacky Agents QA UAT — Roadmap FIFTH Part: Accurate, Deterministic, and Verifiable Navigation

**Product:** Stacky / Stacky Agents — QA UAT Agent  
**Area:** Robust navigation, ASP.NET WebForms, Playwright, strategy contracts, forensic evidence  
**Roadmap version:** v5.0  
**Date:** 2026-05-11  
**Author:** Senior QA Automation / SDET Architect — Stacky Agents  
**Audience:** Tech Lead, QA Automation Lead, SDET, Backend, DevOps, Stacky Agents Operators  
**Continuation of:**
- [FIRST PART](../../../Tools/Stacky/Stacky%20tools/QA%20UAT%20Agent/roadmap_qa_uat_agent_big_tech.md) — Stratified platform, preflight, fingerprint, evidence bundle
- [SECOND PART](../../../Tools/Stacky/Stacky%20tools/QA%20UAT%20Agent/roadmap_qa_uat_agent_big_tech_SEGUNDA_PARTE.md) — Active test-data management, safe seed SQL, oracle
- [THIRD PART](../../../Tools/Stacky/Stacky%20Agents%20QA%20UAT%20roadmap%20tercera%20parte.md) — Gate-governed pipeline, run_id, hard contracts, flake governance
- [FOURTH PART](../../../Tools/Stacky/Stacky%20Agents%20QA%20UAT%20roadmap%20CUARTA%20parte.md) — Per-screen navigation contracts, navigation_contracts.yml, strategy_resolver, navigation_driver

---

## 0. Executive reading

The previous four parts of this roadmap built Stacky's stratified quality platform: deploy fingerprint, evidence bundle, data gates, oracle, flake governance, declarative navigation contracts, and a strategy resolver. However, a critical structural defect remains that none of those parts solved at the root:

**The `playwright_test.spec.ts.j2` template navigates with `page.goto(TARGET_SCREEN)` in `beforeEach` (line 381) and with `page.goto(pantalla)` in the test body (line 418), completely ignoring the output of `navigation_strategy_resolver.py` and the `direct_entry_allowed: false` contract in `navigation_contracts.yml`.**

This means that, even with all Part IV controls enabled, the spec generated for `FrmDetalleClie.aspx` still executes:

```typescript
// template line 381 — beforeEach
await page.goto(`${BASE_URL}FrmDetalleClie.aspx`, { waitUntil: 'domcontentloaded', timeout: 20_000 });

// template line 418 — test body (SETUP)
await page.goto(`${BASE_URL}FrmDetalleClie.aspx`, { waitUntil: 'domcontentloaded' });
```

These two independent calls without session context crash the ASP.NET app pool because `FrmDetalleClie.aspx` requires `CLCOD` in the QueryString and ViewState emitted by `FrmBusqueda.aspx`. The screen cannot build its context internally when reached through a direct `goto()`.

This fifth part proposes the strongest possible plan to turn QA UAT Agent navigation into an **accurate, deterministic, verifiable, and fully traceable** system, permanently eliminating the possibility that the generator produces a direct `goto()` against screens that do not allow it.

The central mindset shift is:

> Navigation is not an implementation detail of the spec. Navigation is a **first-class artifact** declared in contracts, resolved before generation, encoded in a typed `navigation_plan`, executed by specialized helpers, and verified by arrival assertions before any business step.

---

## 1. Current diagnosis — exact code references

### 1.1. The root problem — two `goto()` calls in the template

File: `Tools/Stacky/Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2`

**Failure point 1 — `beforeEach` (line 381):**

```typescript
await page.goto(`${BASE_URL}${TARGET_SCREEN}`, { waitUntil: 'domcontentloaded', timeout: 20_000 });
```

`TARGET_SCREEN` is rendered as `{{ pantalla }}`, which for ticket 120/RF-007 is `FrmDetalleClie.aspx`. This direct `goto()` violates `direct_entry_allowed: false` declared in `navigation_contracts.yml` (lines 87-88 of that file).

**Failure point 2 — test body, SETUP block (line 418):**

```typescript
await page.goto(`${BASE_URL}{{ pantalla }}`, { waitUntil: 'domcontentloaded' });
```

Second occurrence of the same error. If `beforeEach` does not crash (because the app pool recovers between tests), the body triggers it again.

**Failure point 3 — `navigate` action in scenario steps (line 492):**

```typescript
await page.goto(`${BASE_URL}{{ step.target }}`, { waitUntil: 'domcontentloaded' });
```

Any step with `accion: navigate` generates an unconditional `goto()`. It does not verify whether `step.target` allows direct entry.

### 1.2. The disconnect between the resolver and the generator

File: `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_strategy_resolver.py`

The resolver exists and works correctly. It produces decisions such as:

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

But this decision **does not reach the generator** (`playwright_test_generator.py`) as a parameter that changes the template rendering logic. The generator simply renders the scenario `pantalla` without considering the resolved navigation strategy.

### 1.3. `navigation_driver.py` is not integrated into the template

File: `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_driver.py`

`NavigationDriver` correctly implements the three WebForms navigation mechanisms (`via_form_submit`, `via_dopostback`, `via_link_click`) with retry and backoff. But the template does not use it for initial navigation. It only uses the TypeScript helper `navigateViaFormSubmit` for steps with `accion: navigate_webforms`, not for initial context navigation.

### 1.4. Arrival validation is incomplete

The template (lines 382-398) validates the URL after the `goto()`, but this validation is post-hoc: if the `goto()` crashed the app pool, the loaded page is the ASP.NET error page (`<title>Runtime Error</title>`), not `FrmDetalleClie.aspx`. The URL validation detects the problem, but it is already too late: the crash has occurred.

### 1.5. `playbook_router.py` is not connected to the navigation pipeline

File: `Tools/Stacky/Stacky tools/QA UAT Agent/playbook_router.py`

There is a playbook router that searches for prebuilt playbooks for scenarios, but currently there are no playbooks in `cache/playbooks/` (the directory contains no `.yml` or `.json` files). The router has the infrastructure but no navigable content.

### 1.6. Summary of critical gaps

| ID | Gap | File | Severity |
|---|---|---|---|
| B-01 | `beforeEach` uses unconditional `goto(TARGET_SCREEN)` | `playwright_test.spec.ts.j2:381` | P0 |
| B-02 | Test body uses unconditional `goto(pantalla)` | `playwright_test.spec.ts.j2:418` | P0 |
| B-03 | `navigate` action uses `goto()` without verifying the contract | `playwright_test.spec.ts.j2:492` | P0 |
| B-04 | The resolver does not pass `navigation_plan` to the generator | `playwright_test_generator.py` | P0 |
| B-05 | There is no mandatory post-navigation `arrival_validator` | template + generator | P1 |
| B-06 | Playbooks do not contain executable navigation | empty `cache/playbooks/` | P1 |
| B-07 | `navigation_contracts.yml` has no schema version | `navigation_contracts.yml` | P2 |
| B-08 | There is no `navigation_step_*` event in `execution.jsonl` | all modules | P1 |
| B-09 | `session_expiry_detector` does not exist as an independent module | — | P2 |
| B-10 | The `navigate_webforms` action does not verify arrival assertions | template:499-527 | P1 |

---

## 2. Navigation design principles

These principles are non-negotiable for any change to the navigation system.

### Principle 1 — Navigation is a contract, not a detail

No spec can be generated without an explicit, typed `navigation_plan` validated against schema. The plan is not a comment: it is the set of instructions that the spec executes. If the plan does not exist or is invalid, the generator blocks.

### Principle 2 — The contract decides, not the generator

`navigation_strategy_resolver.py` is the single source of truth on how to reach a screen. The generator consumes its output. It never infers the strategy on its own.

### Principle 3 — Zero `goto()` against session screens

`page.goto(screen)` is valid only when `navigation_contracts.yml` declares `direct_entry_allowed: true` for that screen. For any other screen, the template generates the correct mechanism (human path, deeplink, form submit) according to the resolved strategy.

### Principle 4 — Reaching the screen is not enough: arrival must be verified

After each navigation step (not only the final one), the spec runs arrival assertions:
- URL contains the expected screen name
- The unique DOM marker for the screen is visible
- There is no `<title>Runtime Error</title>` and no `Errors.aspx` URL
- There is no redirect to `FrmLogin.aspx`

If any assertion fails, the test ends with category `NAV` and a classified reason, not with a generic timeout.

### Principle 5 — The session is a verified artifact, not an assumption

Before executing any navigation that requires an active session, the spec verifies that `storageState` exists and is recent. If it does not exist or is older than the configured TTL, the test blocks with category `ENV` and required human action: re-run `global.setup.ts`.

### Principle 6 — Every navigation step is observable

Every navigation step emits three events in `execution.jsonl`: `navigation_step_started`, `navigation_step_completed`, or `navigation_step_failed`. These events contain: step number, method used, URL before, URL after, elapsed time, verified assertions, and error_code if it failed.

### Principle 7 — Fail early, fail classified

If navigation fails, the failure category is deterministic:
- `NAV` — the screen exists but could not be reached
- `ENV` — the session expired, the server does not respond, or the app pool is down
- `DATA` — data required to execute the human path is missing
- `PIP` — the navigation strategy is not compatible with the lane

`NAV_TIMEOUT` must never be reported as the final diagnosis if the real cause is `ENV` (app pool down) or `DATA` (missing CLCOD).

### Principle 8 — The human approves non-standard strategies

If the operator wants to use deeplink in a lane that requires human path (or vice versa), there must be an explicit override in the run configuration, audited in `execution.jsonl`. The system never hides this decision.

### Principle 9 — Playbooks are executable contracts, not documentation

A playbook is a JSON file with a validated schema containing: entrypoint, typed navigation steps, arrival assertions, and parameterizable fields. The generator uses it as the primary navigation source. If a playbook exists for the screen and scenario, it is used; if not, the generator looks for the contract `human_path`; if that also does not exist, it blocks.

### Principle 10 — Anti-fragile against application updates

When the application changes (new control on a screen, URL change, new intermediate screen), the system detects the change because arrival assertions fail precisely. The failure is diagnosed as `NAV ARRIVAL_ASSERTION_FAILED` with exact evidence of which assertion failed, instead of a generic timeout.

---

## 3. Target architecture

### 3.1. Navigation resolution flow (new)

```
ticket.json
    |
    v
[QA Intake]
    |
    v
[navigation_strategy_resolver.py]
    |-- Reads navigation_contracts.yml
    |-- Verifies lane, available_data, direct_entry_allowed
    |-- Produces navigation_decision.json
    |
    +---> BLOCKED (DATA/NAV/PIP) --> execution.jsonl + result.json --> STOP
    |
    v
[playbook_router.py]
    |-- Searches playbook in cache/playbooks/ for (screen, goal)
    |-- If found: navigation_plan = playbook.navigation_steps
    |-- If not found: navigation_plan = human_paths from the contract
    |-- Produces navigation_plan.json (typed schema)
    |
    +---> BLOCKED (PIP NO_PLAYBOOK_NO_CONTRACT) --> STOP
    |
    v
[navigation_plan_validator.py] (NEW)
    |-- Validates navigation_plan.json against NavigationPlan.schema.json
    |-- Verifies that each step has: method, target, assertions
    |-- Verifies that required data is available
    |-- Produces navigation_plan_validation.json
    |
    +---> BLOCKED (PIP INVALID_NAV_PLAN) --> STOP
    |
    v
[playwright_test_generator.py]
    |-- Receives validated navigation_plan as a parameter
    |-- Renders template with correct navigation (NO direct goto)
    |-- Generates arrival_assertions block according to plan
    |-- Produces .spec.ts
    |
    v
[playwright runner]
    |-- Executes spec
    |-- Each navigation step emits navigation_step_* to execution.jsonl
    |-- Arrival assertions verified at each step
    |-- Evidence: screenshots pre/post/error per step
```

### 3.2. Execution flow in the generated spec (new)

```
global.setup.ts         storageState validated by fingerprint + TTL
        |
        v
test.beforeEach
    [1] Verify that storageState exists and is valid
    [2] NO direct goto() — the navigation_plan defines how to reach the screen
    [3] Execute navigation_plan.steps[0..n] using typed helpers
    [4] Verify arrival_assertions after the last step
    [5] Post-navigation screenshot with descriptive name
    [6] If it fails: emit navigation_step_failed + category + STOP
        |
        v
test body
    [7] Execute business steps
    [8] Each step captures screenshots
    [9] Oracle assertions at the end
        |
        v
test.afterEach
   [10] Write assertions.json, step_bboxes.json, screen_errors.json
   [11] Emit navigation_summary event to execution.jsonl
```

### 3.3. Component diagram (ASCII)

```
+-----------------------------------+
| navigation_contracts.yml          |  <-- declarative contract per screen
| (schema: NavigationContracts v2)  |
+-----------------------------------+
             |
             v
+-----------------------------------+
| navigation_strategy_resolver.py   |  <-- resolves strategy per scenario
| input:  ScenarioNavInput.schema   |  <-- lane, screen, available_data
| output: NavigationDecision.schema |  <-- strategy, path_id, blocked_reason
+-----------------------------------+
             |
             v
+-----------------------------------+
| playbook_router.py                |  <-- searches prebuilt playbook
| input:  NavigationDecision        |
| output: NavigationPlan.schema     |  <-- typed steps + assertions
+-----------------------------------+
             |
             v
+-----------------------------------+
| navigation_plan_validator.py (NEW)|  <-- validates plan against schema
| input:  NavigationPlan.schema     |
| output: NavigationPlanValidation  |
+-----------------------------------+
             |
             v
+-----------------------------------+
| playwright_test_generator.py      |  <-- generates .spec.ts
| receives: validated navigation_plan|
| renders: template with helpers    |
| NEVER generates goto() without plan|
+-----------------------------------+
             |
             v
+-----------------------------------+
| playwright_test.spec.ts.j2        |  <-- renewed template
| beforeEach: executeNavigationPlan |  <-- new TypeScript helper
| body SETUP: direct goto REMOVED   |
| steps navigate: with contract     |
+-----------------------------------+
             |
             v
+-----------------------------------+
| playwright/helpers/               |
| navigation_executor.ts   (NEW)    |  <-- executes NavigationPlan in browser
| webforms_nav.ts          (exists) |  <-- form.submit(), doPostBack()
| arrival_validator.ts     (NEW)    |  <-- typed arrival assertions
| session_guard.ts         (NEW)    |  <-- verifies storageState before nav
+-----------------------------------+
             |
             v
+-----------------------------------+
| execution.jsonl                   |  <-- evidence of each navigation step
| navigation_plan.json              |  <-- resolved plan (artifact)
| navigation_step_results.json      |  <-- result per step (artifact) (NEW)
| arrival_assertions.json           |  <-- arrival assertion results (NEW)
+-----------------------------------+
```

---

## 4. Data contracts

### 4.1. `NavigationPlan.schema.json` (new central artifact)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "NavigationPlan/1.0",
  "description": "Resolved navigation plan for a UAT scenario. Input for the generator and the executor.",
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
            "description": "Mapping of form fields to test data",
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
      "description": "Mandatory assertions after the last navigation step",
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
          "description": "hard: fails the test. soft: records but does not fail."
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

### 4.2. Navigation events in `execution.jsonl`

Each `NavigationPlan` step emits three events:

```json
{ "event": "navigation_step_started",
  "timestamp": "2026-05-11T14:00:00.000Z",
  "ticket_id": 120,
  "scenario_id": "P02",
  "step_index": 1,
  "method": "goto_direct",
  "target_url": "FrmBusqueda.aspx",
  "description": "Navigate to search screen"
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
  "human_action_required": "Verify that the result grid returns at least one row for CLCOD=12345"
}
```

Summary event at the end of the navigation block:

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

### 4.3. Extension of `navigation_contracts.yml` to v2

New fields per screen:

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

  # NEW in v2: mandatory arrival_assertions for this screen
  arrival_assertions:
    - assertion_id: no_aspnet_error
      type: no_aspnet_error
      description: "No YSOD or Errors.aspx visible"
      severity: hard
      category_on_fail: ENV
    - assertion_id: no_login_redirect
      type: no_login_redirect
      description: "Not redirected to FrmLogin"
      severity: hard
      category_on_fail: ENV
    - assertion_id: url_contains_frmdetalleclie
      type: url_contains
      expected_value: FrmDetalleClie
      description: "URL contains FrmDetalleClie"
      severity: hard
      category_on_fail: NAV
    - assertion_id: detalle_form_visible
      type: dom_visible
      selector: "#c_pnlDetalle, #ctl00_c_pnlDetalle, form#aspnetForm"
      description: "Main detail panel visible"
      severity: hard
      category_on_fail: APP

  # NEW in v2: screen-specific timeouts
  timeouts:
    navigation_timeout_ms: 45000
    arrival_assertion_timeout_ms: 10000
    updatepanel_settle_ms: 5000

  # NEW in v2: specific ASP.NET error indicators
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
          description: "Navigate to FrmBusqueda.aspx"
          target_url: "FrmBusqueda.aspx"
          wait_url_contains: "FrmBusqueda"
          timeout_ms: 20000
          retries: 2
          intermediate_assertions:
            - assertion_id: search_form_visible
              type: dom_visible
              selector: "#c_btnBuscar, #ctl00_c_btnBuscar"
              description: "Search button visible on FrmBusqueda"
              severity: hard
              category_on_fail: NAV

        - step_index: 2
          method: fill
          description: "Enter CLCOD in the filter field"
          selector: "#c_abfCliente, #ctl00_c_abfCliente"
          data_bindings:
            value: "CLCOD"
          timeout_ms: 5000
          retries: 1

        - step_index: 3
          method: button_click
          description: "Click the Search button"
          selector: "#c_btnBuscar, #ctl00_c_btnBuscar"
          wait_url_contains: "FrmBusqueda"
          timeout_ms: 30000
          retries: 2
          intermediate_assertions:
            - assertion_id: search_results_visible
              type: dom_visible
              selector: "#c_gvClientes tr:nth-child(2), .grid-result tr:nth-child(2)"
              description: "At least one result row visible in the grid"
              severity: hard
              category_on_fail: DATA

        - step_index: 4
          method: row_click
          description: "Click the first result row matching CLCOD"
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

### 4.4. `playbook.schema.json` schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "Playbook/1.0",
  "description": "Executable playbook for QA UAT Agent. Navigation contract + actions for a specific goal.",
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
      "description": "Navigation steps to reach target_screen",
      "items": { "$ref": "NavigationPlan/1.0#/properties/steps/items" }
    },
    "action_steps": {
      "type": "array",
      "description": "Business interaction steps after reaching the screen"
    },
    "arrival_assertions": {
      "type": "array",
      "items": { "$ref": "NavigationPlan/1.0#/$defs/AssertionSpec" }
    },
    "parameterizable_fields": {
      "type": "object",
      "description": "Fields the scenario can override via data_bindings"
    }
  }
}
```

---

## 5. Sprint plan

### Sprint N5-01 — Remove the three unconditional `goto()` calls from the template

**Objective:** Close gaps B-01, B-02, and B-03. No generated spec may contain `page.goto()` against a screen with `direct_entry_allowed: false`.

**Estimated duration:** 3 days  
**Lane:** `compile-only` (does not require Playwright to validate)

#### 5.1.1. Affected files

- `Tools/Stacky/Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2`
- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright_test_generator.py`

#### 5.1.2. Changes in `playwright_test.spec.ts.j2`

**Change 1 — `beforeEach` (lines 376-398):**

Replace the current `goto()` + reactive validation logic with a call to the new `executeNavigationPlan()` helper:

```typescript
// BEFORE (lines 376-398) — REMOVE
test.beforeEach(async ({ page }) => {
  await page.goto(`${BASE_URL}${TARGET_SCREEN}`, ...);
  // reactive post-goto validation...
});

// AFTER — Jinja2 template
test.beforeEach(async ({ page }) => {
  // [NAV] Execute navigation plan resolved by navigation_strategy_resolver.py
  // Strategy: {{ navigation_plan.strategy }}
  // Entrypoint: {{ navigation_plan.entrypoint }}
  // Steps: {{ navigation_plan.steps | length }}
{% if navigation_plan.session_requirements.require_valid_storagestate %}
  // [SESSION] Verify storageState before navigating
  await verifyStorageStateValid({{ navigation_plan.session_requirements.storagestate_max_age_minutes }});
{% endif %}
  const _navPlanResult = await executeNavigationPlan(page, NAVIGATION_PLAN, {
    evidenceDir: 'evidence/{{ ticket_id }}/{{ scenario_id }}',
    screenshotPrefix: 'nav',
    emitEvents: true,
  });
  if (!_navPlanResult.ok) {
    throw new Error(
      `[NAV_PLAN_FAILED] Navigation to {{ target_screen }} could not be completed. ` +
      `strategy={{ navigation_plan.strategy }} ` +
      `step=${_navPlanResult.failedStep} ` +
      `errorCode=${_navPlanResult.errorCode} ` +
      `category=${_navPlanResult.category} ` +
      `detail=${_navPlanResult.detail}`
    );
  }
});
```

**Change 2 — SETUP block in the test body (line 418):**

Remove the second `goto()`. Navigation was already resolved in `beforeEach` by `executeNavigationPlan`. The SETUP block remains only as a screenshot and optional verification:

```typescript
// BEFORE (line 418) — REMOVE
await page.goto(`${BASE_URL}{{ pantalla }}`, { waitUntil: 'domcontentloaded' });

// AFTER
// [SETUP] Navigation was completed in beforeEach via executeNavigationPlan.
// We only capture the initial screenshot of the business state.
await page.screenshot({ path: 'evidence/{{ ticket_id }}/{{ scenario_id }}/step_00_setup.png' });
```

**Change 3 — `navigate` action in steps (line 492):**

Add contract verification before emitting `goto()`:

```typescript
// BEFORE
await page.goto(`${BASE_URL}{{ step.target }}`, { waitUntil: 'domcontentloaded' });

// AFTER — with strategy verification from navigation_plan
{% if step.navigation_strategy == 'direct_entry' %}
    // [NAV DIRECT] {{ step.target }} allows direct entry according to navigation_contracts.yml
    await page.goto(`${BASE_URL}{{ step.target }}`, { waitUntil: 'domcontentloaded', timeout: {{ step.timeout_ms | default(20000) }} });
{% elif step.navigation_strategy == 'form_submit' %}
    // [NAV FORM_SUBMIT] {{ step.target }} requires postback via HTMLFormElement.prototype.submit
    const _navStep_{{ loop.index }} = await navigateViaFormSubmit(
      page, {{ step.eventtarget | tojson }}, {{ step.eventargument | tojson }},
      {{ step.wait_url_contains | tojson }}, { timeoutMs: {{ step.timeout_ms | default(45000) }}, maxAttempts: {{ step.retries | default(3) }} }
    );
    if (!_navStep_{{ loop.index }}.ok) {
      throw new Error(`[NAV_STEP_FAILED] step {{ loop.index }}: ${_navStep_{{ loop.index }}.errorCode}`);
    }
{% elif step.navigation_strategy == 'blocked' %}
    // [NAV BLOCKED] This action was blocked by navigation_strategy_resolver.
    // Reason: {{ step.blocked_reason }}
    throw new Error('[NAV_BLOCKED] {{ step.blocked_reason }}');
{% endif %}
```

**Change 4 — Add new helper imports at the beginning of the template:**

```typescript
import { executeNavigationPlan } from '../../playwright/helpers/navigation_executor';
import { verifyStorageStateValid } from '../../playwright/helpers/session_guard';
import { ArrivalValidator } from '../../playwright/helpers/arrival_validator';

// NAVIGATION_PLAN — resolved by navigation_strategy_resolver.py and encoded in the spec.
// DO NOT edit manually. Regenerate the spec if the strategy changes.
const NAVIGATION_PLAN = {{ navigation_plan | tojson(indent=2) }};
```

#### 5.1.3. Changes in `playwright_test_generator.py`

The generator must:
1. Receive `navigation_plan: dict` as a parameter of the `run()` function.
2. Validate that the plan is not `None` before rendering.
3. Pass the plan to the Jinja2 context.
4. If `navigation_plan` is `None` and the screen has `direct_entry_allowed: false`, return `BLOCKED GEN NAVIGATION_PLAN_MISSING`.

Pseudocode for the change:

```python
def run(
    scenarios_path: Path,
    ui_maps_dir: Path,
    out_dir: Path,
    navigation_plans_dir: Optional[Path] = None,  # NEW
    ...
) -> dict:
    ...
    for scenario in scenarios:
        screen = scenario.get("pantalla")
        # Load navigation_plan for this scenario
        nav_plan = _load_navigation_plan(
            navigation_plans_dir, scenario["scenario_id"]
        )
        # Verify whether the screen requires a plan
        if nav_plan is None and _screen_requires_nav_plan(screen, contracts):
            results.append({
                "scenario_id": scenario["scenario_id"],
                "ok": False,
                "blocked": True,
                "category": "GEN",
                "reason": "NAVIGATION_PLAN_MISSING",
                "human_action_required": (
                    f"Run navigation_strategy_resolver.py for scenario "
                    f"'{scenario['scenario_id']}' and screen '{screen}' before generating the spec."
                )
            })
            continue
        # Render template with nav_plan
        context = _build_template_context(scenario, ui_map, nav_plan=nav_plan, ...)
        ...
```

#### 5.1.4. Mandatory tests

- `tests/unit/test_template_no_direct_goto.py` — verifies that the rendered template for `FrmDetalleClie.aspx` with `direct_entry_allowed: false` does NOT contain `page.goto(BASE_URL + 'FrmDetalleClie.aspx')` as a setup instruction
- `tests/unit/test_generator_blocks_without_nav_plan.py` — verifies that the generator returns `BLOCKED GEN NAVIGATION_PLAN_MISSING` when `navigation_plan` is `None` for a screen with `direct_entry_allowed: false`
- `tests/unit/test_generator_allows_direct_entry.py` — verifies that for `FrmBusqueda.aspx` (`direct_entry_allowed: true`) the generator still generates `goto()` correctly

#### 5.1.5. Verifiable acceptance criteria

- `grep -r "goto.*FrmDetalleClie" evidence/120/` returns zero results after regenerating the spec
- The generator returns `"blocked": true, "reason": "NAVIGATION_PLAN_MISSING"` for any screen with `direct_entry_allowed: false` without a plan
- The three unit tests pass

#### 5.1.6. Metrics moved

- `generator_block_rate` for `NAVIGATION_PLAN_MISSING`: decreases when plans are integrated
- `nav_direct_goto_violations`: must reach 0
- `time_to_first_actionable_failure`: decreases because blocking happens before Playwright

---

### Sprint N5-02 — `navigation_plan_validator.py` and `NavigationPlan.schema.json`

**Objective:** Close gap B-04. Create the navigation plan validator as a mandatory gate between the resolver and the generator.

**Estimated duration:** 2 days

#### 5.2.1. Files to create

- `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_plan_validator.py`
- `Tools/Stacky/Stacky tools/QA UAT Agent/schemas/NavigationPlan.schema.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/schemas/NavigationContracts.v2.schema.json`

#### 5.2.2. Validator contract

Input:

```json
{
  "navigation_plan": { "...": "NavigationPlan/1.0 object" },
  "available_data": { "CLCOD": "12345" }
}
```

Successful output:

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

Blocking output:

```json
{
  "ok": false,
  "verdict": "BLOCKED",
  "category": "PIP",
  "reason": "INVALID_NAV_PLAN",
  "failed_validation": "step_index_2_missing_selector",
  "human_action_required": "Step 2 of the navigation plan for P02 has no selector defined for method=fill. Verify the contract in navigation_contracts.yml or the playbook.",
  "plan_errors": [
    { "step_index": 2, "field": "selector", "error": "required when method=fill" }
  ]
}
```

#### 5.2.3. Implemented validation rules

1. The plan has at least one step.
2. Each step has a valid enum `method`.
3. Steps with `method=fill` have `selector` and `data_bindings`.
4. Steps with `method=form_submit` have `eventtarget` and `wait_url_contains`.
5. Steps with `method=goto_direct` or `method=goto_deeplink` have `target_url`.
6. `arrival_assertions` has at least `no_aspnet_error` and `url_contains`.
7. All `data_bindings` from all steps have values in `available_data`.
8. No step with `method=goto_direct` has as `target_url` a screen with `direct_entry_allowed: false` in the contracts.

#### 5.2.4. Event in `execution.jsonl`

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

#### 5.2.5. Mandatory tests

- `tests/unit/test_nav_plan_validator_valid.py`
- `tests/unit/test_nav_plan_validator_missing_selector.py`
- `tests/unit/test_nav_plan_validator_direct_goto_violation.py`
- `tests/unit/test_nav_plan_validator_data_binding_missing.py`

#### 5.2.6. Acceptance criteria

- The validator rejects any plan with `goto_direct` to a screen with `direct_entry_allowed: false`
- The validator rejects plans without `arrival_assertions`
- The validator resolves `data_bindings` against `available_data` and reports missing values

---

### Sprint N5-03 — `navigation_executor.ts` and `arrival_validator.ts` (TypeScript helpers)

**Objective:** Close gap B-05. Create the TypeScript helpers that execute the `NavigationPlan` in the Playwright browser and verify arrival assertions.

**Estimated duration:** 4 days

#### 5.3.1. Files to create

- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/helpers/navigation_executor.ts`
- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/helpers/arrival_validator.ts`
- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/helpers/session_guard.ts`

#### 5.3.2. `navigation_executor.ts` contract

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

`executeNavigationPlan` iterates over `plan.steps` and, for each step:
1. Captures a pre-step screenshot.
2. Executes the corresponding method (goto, form_submit, click, fill, etc.).
3. Waits for the expected URL or DOM.
4. Verifies `intermediate_assertions` if they exist.
5. Captures a post-step screenshot.
6. If it fails, captures an error screenshot, classifies the error code, and returns.

After the last step, it runs `ArrivalValidator.validateAll(plan.arrival_assertions)`.

#### 5.3.3. `arrival_validator.ts` contract

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

  // Implementations by type:
  static async checkUrlContains(page, expected): Promise<boolean>
  static async checkDomVisible(page, selector, timeout): Promise<boolean>
  static async checkNoAspnetError(page): Promise<boolean>
  static async checkNoLoginRedirect(page): Promise<boolean>
  static async checkNo500Response(page): Promise<boolean>
}
```

ASP.NET error detection (`checkNoAspnetError`) verifies:
- `page.title()` contains one of: "Runtime Error", "Server Error in '/' Application", "Application Error"
- `page.url()` contains "Errors.aspx" or "Error.aspx"
- DOM contains `h1:has-text('Server Error')` or the classic yellow `<div id="ctl00_c_lblError">`

#### 5.3.4. `session_guard.ts` contract

```typescript
export async function verifyStorageStateValid(
  maxAgeMinutes: number,
  authFilePath?: string
): Promise<void>
```

Reads the fingerprint from `.auth/agenda.fingerprint.json`. If the file does not exist or is older than `maxAgeMinutes` minutes, it throws:

```
[SESSION_EXPIRED] storageState is {age} minutes old (max: {maxAgeMinutes}).
Re-run the pipeline to refresh. category=ENV reason=STORAGESTATE_EXPIRED
```

#### 5.3.5. Mandatory tests

- `playwright/helpers/__tests__/arrival_validator.test.ts` — page mock, verifies every assertion type
- `playwright/helpers/__tests__/navigation_executor.test.ts` — page mock, verifies happy path flow and failure on step 2
- `playwright/helpers/__tests__/session_guard.test.ts` — verifies behavior with missing, expired, and valid file

#### 5.3.6. Acceptance criteria

- `ArrivalValidator.checkNoAspnetError()` detects ASP.NET YSOD in an HTML fixture
- `executeNavigationPlan()` emits a screenshot for every failed step
- `verifyStorageStateValid()` throws `ENV SESSION_EXPIRED` when auth is older than 120 minutes

---

### Sprint N5-04 — Executable playbooks for critical screens

**Objective:** Close gap B-06. Create the first playbooks with complete schema and executable navigation for `FrmDetalleClie.aspx`, `FrmBusqueda.aspx`, and `FrmAgenda.aspx`.

**Estimated duration:** 3 days

#### 5.4.1. Files to create

- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/open_detalle_cliente_from_busqueda.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/open_busqueda_directa.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/open_agenda_personal.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/cache/playbooks/index.json`
- `Tools/Stacky/Stacky tools/QA UAT Agent/schemas/Playbook.schema.json`

#### 5.4.2. Complete playbook example: `open_detalle_cliente_from_busqueda.json`

```json
{
  "playbook_id": "open_detalle_cliente_from_busqueda",
  "schema_version": "1.0",
  "target_screen": "FrmDetalleClie.aspx",
  "goal_slug": "abrir_detalle_cliente",
  "description": "Navigate from FrmBusqueda.aspx to FrmDetalleClie.aspx by searching for CLCOD",
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
      "description": "Navigate to FrmBusqueda.aspx (entrypoint)",
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
          "description": "Search button visible",
          "severity": "hard",
          "category_on_fail": "NAV",
          "timeout_ms": 10000
        }
      ]
    },
    {
      "step_index": 2,
      "method": "fill",
      "description": "Enter CLCOD in the search field",
      "selector": "#c_abfCliente",
      "data_bindings": { "value": "CLCOD" },
      "timeout_ms": 5000,
      "retries": 1,
      "screenshot_label": "nav_02_clcod_filled"
    },
    {
      "step_index": 3,
      "method": "button_click",
      "description": "Click Search button and wait for results",
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
          "description": "At least one row in the results grid",
          "severity": "hard",
          "category_on_fail": "DATA",
          "timeout_ms": 15000
        }
      ]
    },
    {
      "step_index": 4,
      "method": "row_click",
      "description": "Click the first row that matches CLCOD",
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
      "description": "No YSOD or ASP.NET error page",
      "severity": "hard",
      "category_on_fail": "ENV",
      "timeout_ms": 5000
    },
    {
      "assertion_id": "no_login_redirect",
      "type": "no_login_redirect",
      "description": "Not redirected to FrmLogin (expired session)",
      "severity": "hard",
      "category_on_fail": "ENV",
      "timeout_ms": 3000
    },
    {
      "assertion_id": "url_contains_detalle",
      "type": "url_contains",
      "expected_value": "FrmDetalleClie",
      "description": "URL contains FrmDetalleClie",
      "severity": "hard",
      "category_on_fail": "NAV",
      "timeout_ms": 5000
    },
    {
      "assertion_id": "detalle_panel_visible",
      "type": "dom_visible",
      "selector": "#ctl00_c_pnlDetalle, #c_pnlDetalle",
      "description": "Main client detail panel visible",
      "severity": "hard",
      "category_on_fail": "APP",
      "timeout_ms": 10000
    }
  ],
  "action_steps": [],
  "parameterizable_fields": {
    "CLCOD": { "type": "string", "description": "Client code to search and open" }
  }
}
```

#### 5.4.3. Update to `playbook_router.py`

The current router uses `cache/playbooks/index.json` as an index. After creating the playbooks, run:

```
python playbook_router.py --rebuild-index
```

Verify that the router output for `screen=FrmDetalleClie.aspx` returns `playbook_id=open_detalle_cliente_from_busqueda` with score >= 4.

#### 5.4.4. Mandatory tests

- `tests/unit/test_playbook_schema_valid.py` — verifies that every playbook in `cache/playbooks/` validates against `Playbook.schema.json`
- `tests/unit/test_playbook_router_finds_detalle.py` — verifies that the router resolves `FrmDetalleClie.aspx + "abrir cliente"` to the correct playbook
- `tests/unit/test_playbook_arrival_assertions_complete.py` — verifies that all playbooks have at least `no_aspnet_error` and `url_contains` in `arrival_assertions`

---

### Sprint N5-05 — End-to-end integration of the navigation pipeline

**Objective:** Connect all components: resolver -> validator -> router -> generator -> template with helpers. The pipeline must produce a correct spec without any direct `goto()` to `FrmDetalleClie.aspx`.

**Estimated duration:** 4 days

#### 5.5.1. Integrated flow

```python
# pipeline_orchestrator.py (pseudocode for the change)

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

# Stage 3: Validator
plan_validation = navigation_plan_validator.validate(navigation_plan, available_data)
emit_event("navigation_plan_validation", plan_validation)

if not plan_validation["ok"]:
    return blocked_result(plan_validation)

# Stage 4: Generator (receives validated navigation_plan)
gen_result = playwright_test_generator.run(
    scenarios_path=scenarios_path,
    ui_maps_dir=ui_maps_dir,
    out_dir=out_dir,
    navigation_plans={scenario_id: navigation_plan},  # NEW
)
emit_event("generator_summary", gen_result)
```

#### 5.5.2. New `navigation_plan_builder.py` module

Create `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_plan_builder.py`, which builds a typed `NavigationPlan` from:
- A `NavigationDecision` from the resolver
- A playbook (if it exists) from the router
- The contracts in `navigation_contracts.yml`
- The scenario `available_data`

Output: a Python object equivalent to `NavigationPlan.schema.json`, serializable as JSON.

#### 5.5.3. Navigation summary event in `execution.jsonl`

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

#### 5.5.4. Mandatory tests

- `tests/integration/test_pipeline_detalleclie_human_path.py` — executes the full pipeline for ticket 120 and verifies that the generated spec contains `executeNavigationPlan` and does NOT contain `goto.*FrmDetalleClie` in setup
- `tests/integration/test_pipeline_detalleclie_no_clcod.py` — verifies that without CLCOD, the pipeline returns `BLOCKED DATA NAVIGATION_DATA_MISSING`
- `tests/integration/test_pipeline_busqueda_direct.py` — verifies that for `FrmBusqueda.aspx`, the pipeline generates `goto_direct` correctly

#### 5.5.5. Acceptance criteria

- The generated spec for ticket 120/P02 has `const NAVIGATION_PLAN = {...}` with 4 steps
- The spec does not contain any `page.goto(BASE_URL + 'FrmDetalleClie.aspx')` call in `beforeEach` or SETUP
- The pipeline returns `BLOCKED DATA` when `CLCOD` is not in `available_data`
- The `navigation_pipeline_summary` event appears in `execution.jsonl`

---

### Sprint N5-06 — Navigation observability: `navigation_step_results.json` and `arrival_assertions.json`

**Objective:** Close gap B-08. Every run that executes navigation must produce granular evidence for each step.

**Estimated duration:** 2 days

#### 5.6.1. New evidence artifacts

```
evidence/<ticket_id>/<run_id>/
  navigation_plan.json                  (resolved and validated plan)
  navigation_step_results.json          (result of each plan step)
  arrival_assertions.json               (result of arrival assertions)
```

#### 5.6.2. `navigation_step_results.json` schema

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
      "description": "Navigate to FrmBusqueda.aspx",
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
      "description": "Enter CLCOD",
      "ok": true,
      "attempts": 1,
      "elapsed_ms": 230,
      "screenshots": ["evidence/120/P02/nav_step_02_completed.png"]
    },
    {
      "step_index": 3,
      "method": "button_click",
      "description": "Click Search",
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
      "description": "Click first row",
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

#### 5.6.3. `arrival_assertions.json` schema

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

#### 5.6.4. Mandatory tests

- `tests/unit/test_nav_step_results_schema.py` — validates that the JSON generated by the TypeScript helper complies with the schema
- `tests/unit/test_arrival_assertions_schema.py` — same for `arrival_assertions.json`

---

### Sprint N5-07 — Expired-session management and `session_expiry_detector`

**Objective:** Close gap B-09. Session expiry during navigation must be classified immediately as `ENV`, not as `NAV_TIMEOUT` after 45 seconds.

**Estimated duration:** 2 days

#### 5.7.1. File to create

- `Tools/Stacky/Stacky tools/QA UAT Agent/playwright/helpers/session_guard.ts` (described in Sprint N5-03)

#### 5.7.2. Expired-session detection logic

The session can expire at three different moments:
1. **Pre-navigation** — `storageState` is older than N minutes. Detected by `verifyStorageStateValid()`.
2. **During navigation** — `goto()` or `form_submit` results in redirect to `FrmLogin.aspx`. Detected by `arrival_validator` in `intermediate_assertions` with `no_login_redirect`.
3. **Post-navigation** — the login panel appears inside the target screen (silent session timeout). Detected by `arrival_validator` with `dom_visible selector=#ctl00_c_pnlLogin`.

In all cases, the error_code is `NAV_AUTH_EXPIRED`, the category is `ENV`, and the human action is:

```
Re-run the pipeline to refresh the session.
The storageState in .auth/agenda.json is invalid or expired.
Command: execute the global.setup stage from the pipeline or manually via
  npx playwright test --project setup
```

#### 5.7.3. Update to `global.setup.ts`

Add writing of the auth creation timestamp to the fingerprint file:

```json
{
  "fingerprint": "abc123...",
  "created_at": "2026-05-11T14:00:00Z",
  "user": "qauser",
  "base_url": "http://localhost:35017/AgendaWeb/"
}
```

`session_guard.ts` reads this timestamp to calculate auth age.

#### 5.7.4. Mandatory tests

- `tests/unit/test_session_guard_expired.py` — fingerprint with `created_at` 3 hours in the past; verifies that it throws ENV SESSION_EXPIRED
- `tests/unit/test_session_guard_valid.py` — fingerprint from 10 minutes ago; no exception
- `tests/unit/test_session_guard_missing_file.py` — no file; throws ENV STORAGESTATE_MISSING

---

### Sprint N5-08 — Deterministic classification of navigation errors (NAV vs ENV vs DATA)

**Objective:** Ensure that no navigation failure is classified as `UNKNOWN` or as `NAV_TIMEOUT` when the real cause is `ENV` or `DATA`.

**Estimated duration:** 3 days

#### 5.8.1. Expansion of the error classifier in `navigation_driver.py`

The current `_classify_error` function (line 496 of `navigation_driver.py`) only distinguishes four cases. Expand it to:

```python
def _classify_error(exc_str: str, current_url: str, page_title: str = "", response_status: int = 0) -> dict:
    """
    Classifies a navigation error with precise category and reason.
    Returns: {"error_code": str, "category": str, "reason": str, "is_terminal": bool}
    """
    exc_lower = exc_str.lower()
    url_lower = current_url.lower()
    title_lower = page_title.lower()

    # ENV — expired session
    if "frmlogin" in url_lower or ("login" in url_lower and "frmlogin" not in url_lower and "FrmBusqueda" not in current_url):
        return {"error_code": "NAV_AUTH_EXPIRED", "category": "ENV", "reason": "SESSION_EXPIRED_LOGIN_REDIRECT", "is_terminal": True}

    # ENV — app pool crash or server down
    if response_status >= 500 or "runtime error" in title_lower or "server error" in title_lower:
        return {"error_code": "NAV_SERVER_ERROR", "category": "ENV", "reason": "ASPNET_APPPOOL_ERROR", "is_terminal": True}

    if "errors.aspx" in url_lower or "error.aspx" in url_lower:
        return {"error_code": "NAV_SERVER_ERROR", "category": "ENV", "reason": "ASPNET_REDIRECT_TO_ERRORS_PAGE", "is_terminal": True}

    # DATA — grid without results (context: search without results)
    if "grid_empty" in exc_lower or "no rows" in exc_lower:
        return {"error_code": "NAV_DATA_GRID_EMPTY", "category": "DATA", "reason": "SEARCH_RESULTS_EMPTY", "is_terminal": True}

    # NAV — form not found
    if "form_not_found" in exc_lower or "cannot read" in exc_lower:
        return {"error_code": "NAV_FORM_NOT_FOUND", "category": "NAV", "reason": "ASPNET_FORM_MISSING", "is_terminal": True}

    # NAV — timeout (may be transient)
    if "timeout" in exc_lower or "timed out" in exc_lower:
        return {"error_code": "NAV_TIMEOUT", "category": "NAV", "reason": "NAVIGATION_TIMEOUT", "is_terminal": False}

    # NAV — generic Playwright error (possibly transient)
    return {"error_code": "NAV_PLAYWRIGHT_ERROR", "category": "NAV", "reason": "PLAYWRIGHT_EXCEPTION", "is_terminal": False}
```

Errors with `is_terminal=True` must not be retried. Errors with `is_terminal=False` may be retried up to `retries` times.

#### 5.8.2. Integration with `arrival_validator.ts`

`ArrivalValidator` must pass the result of `checkNo500Response` and `checkNoAspnetError` as additional information to `navigation_executor.ts`, so it can correctly classify the failure.

#### 5.8.3. Update `triage.json` with navigation cause

When the verdict is `FAIL` or `BLOCKED` and the cause is in the navigation block, `triage.json` must include:

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
  "next_action": "Check IIS Express logs. The app pool crashed while navigating to FrmDetalleClie.aspx with CLCOD=12345. Verify the exception in Windows Event Viewer or in Agenda Web logs.",
  "publish_recommended": false,
  "human_approval_required": true
}
```

#### 5.8.4. Mandatory tests

- `tests/unit/test_error_classifier_session_expired.py`
- `tests/unit/test_error_classifier_apppool_crash.py`
- `tests/unit/test_error_classifier_grid_empty.py`
- `tests/unit/test_error_classifier_timeout_not_terminal.py`
- `tests/unit/test_triage_includes_nav_blame.py`

---

### Sprint N5-09 — Update `navigation_contracts.yml` to v2 with assertions and timeouts

**Objective:** Close gap B-07. Migrate all existing contracts to schema v2 with declared `arrival_assertions`, `timeouts`, and `aspnet_error_markers`.

**Estimated duration:** 2 days

#### 5.9.1. Affected files

- `Tools/Stacky/Stacky tools/QA UAT Agent/navigation_contracts.yml` — add v2 fields to all screens

#### 5.9.2. Screens to update

| Screen | v2 changes |
|---|---|
| `FrmDetalleClie.aspx` | `arrival_assertions`, `timeouts`, `aspnet_error_markers` |
| `FrmBusqueda.aspx` | minimum `arrival_assertions`, `timeouts` |
| `FrmAgenda.aspx` | minimum `arrival_assertions`, `timeouts` |
| `FrmDetalleObligacion.aspx` | `arrival_assertions`, `timeouts`, detailed steps in `human_paths` |
| `FrmAgendaEquipo.aspx` | minimum `arrival_assertions` |
| `FrmAgendaJudicial.aspx` | minimum `arrival_assertions` |

#### 5.9.3. Migration and validation script

Create `Tools/Stacky/Stacky tools/QA UAT Agent/scripts/validate_navigation_contracts.py`:

```
python scripts/validate_navigation_contracts.py --contracts navigation_contracts.yml --schema schemas/NavigationContracts.v2.schema.json
```

Expected output:

```json
{
  "ok": true,
  "screens_validated": 12,
  "screens_v2": 7,
  "screens_v1_legacy": 5,
  "warnings": ["FrmReportes.aspx has no arrival_assertions defined"]
}
```

#### 5.9.4. Backward compatibility

The resolver (v1) continues to work with v1 contracts. v1 contracts without `arrival_assertions` receive minimum default assertions:
- `no_aspnet_error` (severity: hard, category: ENV)
- `no_login_redirect` (severity: hard, category: ENV)
- `url_contains:<screen_name_without_extension>` (severity: hard, category: NAV)

#### 5.9.5. Mandatory tests

- `tests/unit/test_contracts_v2_schema_valid.py` — validates each v2 screen against the schema
- `tests/unit/test_contracts_v1_default_assertions.py` — verifies that v1 screens receive default assertions

---

### Sprint N5-10 — Navigation evals, anti-regression, and metrics

**Objective:** Create the eval set that guarantees no future change to the navigation pipeline can regress the solved problems.

**Estimated duration:** 3 days

#### 5.10.1. Eval fixtures to create

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

Structure of each eval fixture:

```json
{
  "eval_id": "nav_detalleclie_no_clcod_blocked",
  "description": "Without CLCOD available, navigation to FrmDetalleClie.aspx must be blocked as DATA",
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

#### 5.10.2. Eval runner

Create `Tools/Stacky/Stacky tools/QA UAT Agent/scripts/run_navigation_evals.py`:

```
python scripts/run_navigation_evals.py --evals evals/navigation/ --verbose
```

Expected output:

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

Rule: `failed > 0` or `unknown > 0` blocks the pipeline. Navigation evals are a necessary condition to enable spec generation for new tickets.

#### 5.10.3. Navigation metrics to expose

| Metric | Formula | Target |
|---|---|---|
| `nav_direct_goto_violations` | specs with direct `goto()` to screen `direct_entry_allowed: false` | 0 |
| `nav_plan_missing_rate` | scenarios blocked by `NAVIGATION_PLAN_MISSING` | < 5% |
| `nav_arrival_assertion_fail_rate` | failures in arrival assertions by category | ENV < 2%, NAV < 10% |
| `nav_session_expired_rate` | runs blocked by expired session | < 5% |
| `nav_apppool_crash_rate` | runs with `ASPNET_APPPOOL_ERROR` | 0 in stable QA |
| `nav_data_grid_empty_rate` | navigations failed due to empty grid | traceable to DATA |
| `nav_step_p95_ms` | p95 duration for each step type | form_submit < 45s |
| `nav_eval_pass_rate` | percentage of navigation evals that pass | 100% |

#### 5.10.4. Mandatory tests

- `tests/unit/test_nav_evals_all_pass.py` — runs all navigation evals and verifies that they pass
- `tests/regression/test_no_direct_goto_violations.py` — verifies that no existing spec in `evidence/` has direct `goto()` to a screen with `direct_entry_allowed: false`

---

## 6. Explicit anti-patterns

These patterns are **prohibited** in any change to the QA UAT Agent. If detected during code review or spec generation, a P0 bug must be opened.

### AP-01 — `page.goto(TARGET_SCREEN)` against a session screen (P0)

```typescript
// PROHIBITED
await page.goto(`${BASE_URL}FrmDetalleClie.aspx`, { waitUntil: 'domcontentloaded' });
// Reason: FrmDetalleClie.aspx has direct_entry_allowed: false.
// It crashes the app pool if navigated without session context.
```

### AP-02 — `page.goto()` in `beforeEach` for screens with `direct_entry_allowed: false` (P0)

```typescript
// PROHIBITED in beforeEach for session screens
test.beforeEach(async ({ page }) => {
  await page.goto(`${BASE_URL}${TARGET_SCREEN}`, ...);
  // Reason: beforeEach runs before navigation_plan
  // has established the correct session context.
});
```

### AP-03 — `sleep(N)` instead of `waitFor*` (P1)

```typescript
// PROHIBITED
await page.waitForTimeout(3000);
// Use instead:
await waitForAgendaStable(page);
// or
await page.waitForURL(url => url.includes('FrmDetalleClie'), { timeout: 45_000 });
```

### AP-04 — Assuming `storageState` is valid without verifying it (P1)

```typescript
// PROHIBITED (in the test body or in beforeEach without a guard)
// There is no auth validity check before navigation.
// Use:
await verifyStorageStateValid(120); // 120 minutes max age
```

### AP-05 — Classifying `NAV_TIMEOUT` as the final diagnosis (P1)

```python
# PROHIBITED in triage.json
{
  "category": "NAV",
  "reason": "NAV_TIMEOUT"  # Must never be the final reason
}
# NAV_TIMEOUT is an error_code for the navigation operation.
# The triage reason must be the causal diagnosis:
# "SESSION_EXPIRED_LOGIN_REDIRECT", "ASPNET_APPPOOL_ERROR", "SEARCH_RESULTS_EMPTY", etc.
```

### AP-06 — Generator that ignores `navigation_plan` (P0)

```python
# PROHIBITED in playwright_test_generator.py
context = {
  "pantalla": scenario["pantalla"],
  # navigation_plan not included in the Jinja2 context
}
# Reason: the rendered template without navigation_plan will use the goto() fallback.
```

### AP-07 — Playbook without `arrival_assertions` (P1)

```json
{
  "playbook_id": "...",
  "navigation_steps": [...],
  "arrival_assertions": []  // PROHIBITED: empty list
}
// Every playbook must have at least no_aspnet_error and url_contains.
```

### AP-08 — Retrying terminal navigation errors (P1)

```python
# PROHIBITED: retry when is_terminal=True
if error_code == "NAV_AUTH_EXPIRED":
    # Do not retry — it is terminal. The session expired.
    # A retry will only waste time and produce the same result.
    pass  # CORRECT: end immediately
```

### AP-09 — Inventing selectors in navigation steps without ui_map (P0)

```python
# PROHIBITED
navigation_step = {
  "method": "button_click",
  "selector": "#c_btnBuscarCliente"  # Invented — not verified against ui_map
}
# Selectors in navigation steps must come from the ui_map or
# from the assertions section of navigation_contracts.yml.
```

### AP-10 — Publishing a navigation verdict without a complete evidence bundle (P1)

The verdict of a run with a navigation failure cannot be published to ADO/Jira/Mantis without:
- `navigation_plan.json`
- `navigation_step_results.json`
- `arrival_assertions.json`
- At least one screenshot for each failed step

---

## 7. Reference use cases

### Case A — `FrmDetalleClie.aspx` with known CLCOD (human_path, lane=uat_human)

**Context:** Ticket 120/P02, operator has CLCOD=12345, lane=uat_human.

**Full step by step:**

1. `navigation_strategy_resolver.py` receives:
   ```json
   { "target_screen": "FrmDetalleClie.aspx", "lane": "uat_human", "available_data": {"CLCOD": "12345"} }
   ```

2. Resolver reads the contract for `FrmDetalleClie.aspx`:
   - `direct_entry_allowed: false` → cannot do goto
   - `deeplink_allowed: true` but `forbidden_lanes: [uat_human]` → deeplink rejected
   - `human_path_required_for_uat: true` → use human_path
   - `human_paths.open_from_busqueda.required_data: [CLCOD]` → CLCOD available: OK

3. Resolver returns `ALLOW_GENERATION strategy=human_path path_id=open_from_busqueda`.

4. `playbook_router.py` searches for a playbook for `FrmDetalleClie.aspx + "abrir detalle cliente"`:
   - Finds `open_detalle_cliente_from_busqueda.json` with score=7.

5. `navigation_plan_builder.py` builds `NavigationPlan` with 4 steps from the playbook + arrival_assertions from the contract.

6. `navigation_plan_validator.py` validates the plan:
   - 4 steps, all with valid method
   - `CLCOD` resolved in data_bindings for step 2
   - `arrival_assertions` has `no_aspnet_error` and `url_contains`
   - No `goto_direct` to a screen with `direct_entry_allowed: false`
   - OK

7. `playwright_test_generator.py` renders the template with the plan. The generated spec contains:
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

8. Playwright executes the spec. `executeNavigationPlan` navigates step by step.

9. When reaching step 4, it verifies `intermediate_assertions`: the grid has results. Clicks the first row.

10. URL changes to `FrmDetalleClie.aspx`. `arrival_validator.ts` verifies the 4 assertions: all pass.

11. The test body executes business steps (select province, save, etc.).

12. `execution.jsonl` contains `navigation_plan_result` with `navigation_ok: true` and 4 `navigation_step_completed` events.

13. `navigation_step_results.json` and `arrival_assertions.json` are written in the evidence dir.

**Expected verdict:** `PASS` with high confidence.

---

### Case B — `FrmDetalleClie.aspx` without CLCOD (early block)

**Context:** Ticket 120/P02, CLCOD not available, lane=uat_human.

**Step by step:**

1. `navigation_strategy_resolver.py` receives:
   ```json
   { "target_screen": "FrmDetalleClie.aspx", "lane": "uat_human", "available_data": {} }
   ```

2. Resolver finds `human_paths.open_from_busqueda.required_data: [CLCOD]`.

3. `CLCOD` is not in `available_data`. It returns:
   ```json
   {
     "decision": "BLOCKED",
     "category": "DATA",
     "reason": "NAVIGATION_DATA_MISSING",
     "missing_data": ["CLCOD"],
     "human_action_required": "Provide CLCOD in the test data. It is required to navigate via 'open_from_busqueda' to FrmDetalleClie.aspx."
   }
   ```

4. The pipeline records the `navigation_contract_validation` event with `decision=BLOCKED` in `execution.jsonl`.

5. The pipeline does NOT call the playbook_router. It does NOT call the plan_builder. It does NOT call the validator. It does NOT call the generator. It does NOT open Playwright.

6. `result.json` contains:
   ```json
   {
     "ok": false,
     "verdict": "BLOCKED",
     "category": "DATA",
     "reason": "NAVIGATION_DATA_MISSING",
     "failed_stage": "navigation_contract_validation",
     "runner_started": false,
     "human_action_required": "Provide CLCOD in the test data.",
     "time_to_first_actionable_failure_ms": 45
   }
   ```

7. `triage.json` classifies: `category=DATA`, `reason=NAVIGATION_DATA_MISSING`, `confidence=1.0`.

**Expected verdict:** `BLOCKED DATA` in under 1 second. Playwright does not open.

---

### Case C — `FrmBusqueda.aspx` with `direct_entry_allowed: true` (smoke)

**Context:** Smoke ticket, screen `FrmBusqueda.aspx`, lane=smoke_deeplink.

**Step by step:**

1. Resolver reads contract: `FrmBusqueda.aspx`, `direct_entry_allowed: true`.

2. Resolver case 0: direct-entry screen, without human_path_required. Returns:
   ```json
   { "decision": "ALLOW_GENERATION", "strategy": "direct_entry", "target_screen": "FrmBusqueda.aspx" }
   ```

3. `navigation_plan_builder.py` builds a simple plan with a single step:
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

4. Template generates:
   ```typescript
   const NAVIGATION_PLAN = { "strategy": "direct_entry", "steps": [...], "arrival_assertions": [...] };
   test.beforeEach(async ({ page }) => {
     // verifyStorageStateValid
     const _navResult = await executeNavigationPlan(page, NAVIGATION_PLAN, {...});
     // For direct_entry: executeNavigationPlan executes goto_direct
   });
   ```

5. The spec includes `goto_direct`, but only for `FrmBusqueda.aspx`, which has `direct_entry_allowed: true`.

6. Arrival assertions verify: no ASP.NET error, URL contains `FrmBusqueda`, Search button visible.

**Expected verdict:** Navigation in < 3 seconds, `arrival_assertions: all_passed=true`.

---

## 8. Glossary

| Term | Definition |
|---|---|
| `arrival_assertion` | Mandatory verification executed after completing navigation to a screen. It may be URL, DOM, title, or absence-of-error type. |
| `NavigationPlan` | Typed JSON artifact that describes how to reach a screen: entrypoint, steps, methods, data, and assertions. It is the contract between the resolver and the generator. |
| `navigation_plan_builder` | Python module that builds a `NavigationPlan` from a resolver decision and/or a playbook. |
| `navigation_plan_validator` | Python module that validates a `NavigationPlan` against its JSON Schema before passing it to the generator. |
| `human_path` | Navigation strategy that simulates the real user path: entrypoint → form → search → result → target screen. |
| `deeplink` | URL with parameters that allows reaching a session screen without navigating through intermediate screens, because the screen reconstructs the context internally from the parameters. |
| `direct_entry` | Navigation via `page.goto(screen)`, valid only for screens with `direct_entry_allowed: true`. |
| `direct_entry_allowed` | Navigation contract attribute that indicates whether a screen can receive a direct `page.goto()` without crashing. |
| `YSOD` | Yellow Screen Of Death — HTML error page shown by ASP.NET when an unhandled exception occurs. Detected by title or body content. |
| `ViewState` | ASP.NET WebForms hidden field containing serialized form state. It is lost when navigating directly to a screen without going through the correct postback cycle. |
| `EventValidation` | ASP.NET hidden field that validates that the event was emitted by a control in the form. If it does not exist, ASP.NET rejects the postback. |
| `UpdatePanel` | ASP.NET control that performs partial postbacks via AJAX (ScriptManager). Requires waiting for `PageRequestManager.get_isInAsyncPostBack()` instead of `waitForNavigation`. |
| `form.submit()` | Primary WebForms navigation mechanism: executes the ASP.NET form submit directly, bypassing ScriptManager. More reliable than `__doPostBack` in headless mode. |
| `storageState` | Playwright JSON file containing cookies and localStorage for an authenticated session. Produced by `global.setup.ts` and consumed by all specs. |
| `session_guard` | Helper that verifies that `storageState` exists and has not expired before executing navigation that requires a session. |
| `NavigationDecision` | Output from `navigation_strategy_resolver.py`: `ALLOW_GENERATION` or `BLOCKED` decision with the chosen strategy. |
| `playbook` | JSON file with validated schema that describes executable navigation + business steps for a specific goal on a screen. Primary source of the `NavigationPlan`. |
| `lane` | Execution category that determines which navigation strategies are allowed: `uat_human`, `smoke_deeplink`, `regression_deeplink`, `forensic_rerun`, etc. |
| `CLCOD` | Client code in Agenda Web. Mandatory parameter to open `FrmDetalleClie.aspx`. Without CLCOD, navigation blocks with `DATA NAVIGATION_DATA_MISSING`. |
| `navigation_contract_validation` | `execution.jsonl` event emitted after the resolver makes its decision. It is the first gate of the navigation pipeline. |
| `navigation_pipeline_summary` | `execution.jsonl` event summarizing the complete result of the navigation pipeline for a scenario. |

---

## 9. Annex A — Complete strategy matrix by (target_screen, lane, data)

| target_screen | lane | CLCOD available | Strategy | Decision | Reason |
|---|---|---|---|---|---|
| FrmDetalleClie.aspx | uat_human | YES | human_path:open_from_busqueda | ALLOW | All requirements met |
| FrmDetalleClie.aspx | uat_human | NO | — | BLOCKED DATA | NAVIGATION_DATA_MISSING: CLCOD |
| FrmDetalleClie.aspx | smoke_deeplink | YES | deeplink | ALLOW | Lane allows deeplink, CLCOD available |
| FrmDetalleClie.aspx | smoke_deeplink | NO | — | BLOCKED DATA | DEEPLINK_PARAM_MISSING: CLCOD |
| FrmDetalleClie.aspx | uat_human_simulation | YES | human_path | ALLOW | Requires human path, data OK |
| FrmDetalleClie.aspx | regression_deeplink | YES | deeplink | ALLOW | Deeplink lane allowed |
| FrmDetalleClie.aspx | diagnostic | YES | deeplink | ALLOW | Diagnostic lane allows deeplink |
| FrmDetalleClie.aspx | forensic_rerun | YES | deeplink | ALLOW | Forensic lane allows deeplink |
| FrmBusqueda.aspx | uat_human | N/A | direct_entry | ALLOW | direct_entry_allowed=true |
| FrmBusqueda.aspx | smoke_deeplink | N/A | direct_entry | ALLOW | direct_entry_allowed=true |
| FrmAgenda.aspx | any | N/A | direct_entry | ALLOW | direct_entry_allowed=true |
| FrmDetalleObligacion.aspx | uat_human | YES (CLCOD+OBLCOD) | human_path:open_from_detalle_cliente | ALLOW | Requires intermediate screen |
| FrmDetalleObligacion.aspx | uat_human | CLCOD YES, OBLCOD NO | — | BLOCKED DATA | NAVIGATION_DATA_MISSING: OBLCOD |
| FrmDetalleObligacion.aspx | smoke_deeplink | — | — | BLOCKED NAV | DEEPLINK_NOT_SUPPORTED_FOR_SCREEN |
| Screen without contract | uat_human | any | — | BLOCKED NAV | NAV_CONTRACT_MISSING |
| Screen without contract | smoke_deeplink | any | direct_entry + warning | ALLOW (with warning) | Safe fallback for non-human lanes |

---

## 10. Annex B — Navigation checklist

### Pre-navigation (before opening the browser)

| # | Check | Tool | Failure category |
|---|---|---|---|
| 1 | `navigation_contracts.yml` loaded and parsed without errors | `navigation_strategy_resolver._load_contracts()` | PIP |
| 2 | Contract for `target_screen` exists | resolver | NAV |
| 3 | Lane is compatible with the declared strategy | resolver | PIP |
| 4 | Data required by the strategy available in `available_data` | resolver | DATA |
| 5 | `NavigationPlan` built and validated against schema | `navigation_plan_validator` | PIP |
| 6 | `storageState` exists and has not expired | `session_guard.py` | ENV |
| 7 | `playbook` found or contract `human_paths` used as fallback | `playbook_router` | PIP |

### During navigation (while executing NavigationPlan)

| # | Check | Tool | Failure category |
|---|---|---|---|
| 8 | Current URL does not contain `frmlogin` before the first step | `arrival_validator.checkNoLoginRedirect()` | ENV |
| 9 | After each step: intermediate_assertions pass | `ArrivalValidator.validateAll()` | NAV/DATA/ENV |
| 10 | If step is `form_submit`: verify that `<form>` exists in the DOM before execute | `navigateViaFormSubmit` | NAV |
| 11 | If step is `row_click`: verify that the grid has at least one row before click | intermediate_assertion `dom_visible(grid_row)` | DATA |
| 12 | Step timeout: no more than `timeout_ms` from the plan, not a hardcoded value | `NavigationStep.timeout_ms` | — |
| 13 | Error `is_terminal=true`: DO NOT retry | `_classify_error(is_terminal)` | — |
| 14 | Screenshot captured on each step failure | `NavigationDriver._screenshot()` | OBS |

### Post-navigation (after the last step)

| # | Check | Tool | Failure category |
|---|---|---|---|
| 15 | `no_aspnet_error`: page title does not contain "Runtime Error" | `ArrivalValidator.checkNoAspnetError()` | ENV |
| 16 | `no_login_redirect`: URL does not contain `frmlogin` | `ArrivalValidator.checkNoLoginRedirect()` | ENV |
| 17 | `url_contains:<screen_name>`: URL contains the target screen name | `ArrivalValidator.checkUrlContains()` | NAV |
| 18 | `dom_visible:<panel_selector>`: main panel of the screen visible | `ArrivalValidator.checkDomVisible()` | APP |
| 19 | `arrival_assertions.json` written to evidence dir | `navigation_executor` | OBS |
| 20 | `navigation_step_results.json` written | `navigation_executor` | OBS |
| 21 | `navigation_plan_result` event emitted in `execution.jsonl` | pipeline orchestrator | OBS |

---

## 11. Annex C — Mapping of navigation severities and categories

| Error Code | Category | Reason | is_terminal | Description | Human action |
|---|---|---|---|---|---|
| `NAV_AUTH_EXPIRED` | ENV | SESSION_EXPIRED_LOGIN_REDIRECT | true | Redirected to FrmLogin during navigation | Re-run the pipeline to refresh storageState |
| `NAV_SERVER_ERROR` | ENV | ASPNET_APPPOOL_ERROR | true | HTTP 5xx or YSOD detected | Check IIS/App Pool logs. Problem is in the application, not the test. |
| `NAV_SERVER_ERROR` | ENV | ASPNET_REDIRECT_TO_ERRORS_PAGE | true | URL changed to Errors.aspx or Error.aspx | Same as above. Navigate manually and confirm the error. |
| `NAV_STORAGESTATE_MISSING` | ENV | STORAGESTATE_FILE_NOT_FOUND | true | `.auth/agenda.json` file does not exist | Run `global.setup.ts` before running the tests. |
| `NAV_STORAGESTATE_EXPIRED` | ENV | STORAGESTATE_MAX_AGE_EXCEEDED | true | storageState older than TTL | Re-run the pipeline to refresh the session. |
| `NAV_DATA_GRID_EMPTY` | DATA | SEARCH_RESULTS_EMPTY | true | Search grid returned no results for the given data | Verify that CLCOD exists in the test environment. Use seed SQL or ask the user for data. |
| `NAV_DATA_MISSING` | DATA | NAVIGATION_DATA_MISSING | true | Data required by the human_path not available | Provide the missing data in the execution payload. |
| `NAV_FORM_NOT_FOUND` | NAV | ASPNET_FORM_MISSING | true | `<form>` not found in the DOM to execute form.submit | Verify that the page loaded correctly. May indicate wrong screen. |
| `NAV_CONTRACT_MISSING` | NAV | NAV_CONTRACT_MISSING | true | Screen without contract in navigation_contracts.yml | Add a contract for the screen or use a non-human lane. |
| `NAV_PATH_MISSING` | NAV | NAV_PATH_MISSING | true | No human_path defined for the screen in the lane | Define human_path in navigation_contracts.yml. |
| `DEEPLINK_NOT_SUPPORTED` | NAV | DEEPLINK_NOT_SUPPORTED_FOR_SCREEN | true | Screen does not support deeplink | Use human_path or change lane. |
| `INVALID_STRATEGY_FOR_LANE` | PIP | INVALID_NAVIGATION_STRATEGY_FOR_LANE | true | Chosen strategy is not compatible with the lane | Change the lane or the strategy. |
| `NAV_TIMEOUT` | NAV | NAVIGATION_TIMEOUT | false (retriable) | Timeout of a navigation step without identified cause | Review server logs. May be transient. Increase timeout or investigate slowness. |
| `NAV_PLAYWRIGHT_ERROR` | NAV | PLAYWRIGHT_EXCEPTION | false (retriable) | Unexpected Playwright exception | Review the Playwright trace. May be a selector flake. |
| `ARRIVAL_ASSERTION_FAILED` | NAV/APP/ENV | According to `category_on_fail` | true | An arrival assertion failed after navigation | Analyze the post-navigation screenshot and `arrival_assertions.json` to determine which specific assertion failed. |

---

## 12. Sprint and dependency summary

| Sprint | Title | Days | Depends on | Gaps closed |
|---|---|---|---|---|
| N5-01 | Remove unconditional `goto()` calls from the template | 3 | None | B-01, B-02, B-03 |
| N5-02 | `navigation_plan_validator.py` and schemas | 2 | N5-01 | B-04 |
| N5-03 | TypeScript helpers: `navigation_executor`, `arrival_validator`, `session_guard` | 4 | N5-01 | B-05, B-09 |
| N5-04 | Executable playbooks for critical screens | 3 | N5-02 | B-06 |
| N5-05 | End-to-end integration of the navigation pipeline | 4 | N5-02, N5-03, N5-04 | B-04 (complete) |
| N5-06 | Observability: `navigation_step_results.json` and `arrival_assertions.json` | 2 | N5-03, N5-05 | B-08 |
| N5-07 | Expired-session management and `session_expiry_detector` | 2 | N5-03 | B-09 |
| N5-08 | Deterministic classification of NAV/ENV/DATA errors | 3 | N5-03, N5-05 | B-07 (partial) |
| N5-09 | Update `navigation_contracts.yml` to v2 | 2 | N5-02 | B-07 |
| N5-10 | Navigation evals, anti-regression, and metrics | 3 | N5-05, N5-08 | all P2 |

**Estimated total:** 28 days of incremental development. Each sprint is executable independently.

**Critical order:** N5-01 is the prerequisite for everything. N5-02 and N5-03 can be done in parallel after N5-01. N5-05 requires N5-02, N5-03, and N5-04 to be complete.

---
