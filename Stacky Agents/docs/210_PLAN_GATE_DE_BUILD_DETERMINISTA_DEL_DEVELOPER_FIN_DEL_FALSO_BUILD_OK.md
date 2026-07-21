# Plan 210 — Gate de build determinista del Developer: fin del falso "Build OK"

> Estado: **PROPUESTO v1** (2026-07-21). Pipeline: proponer → **[este paso ✓]** → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8).
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).

---

## Planes relacionados (leer antes de implementar)

- **DEPENDE de Plan 201** — "Taller de Compilación: detección de `.sln`, build en Release 1-click y artefactos descargables" (`Stacky Agents/docs/201_PLAN_TALLER_DE_COMPILACION_DETECCION_SLN_BUILD_RELEASE_1CLICK_Y_ARTEFACTOS_DESCARGABLES.md`, CRITICADO v2 — APROBADO-CON-CAMBIOS, aún SIN implementar). Este plan **reusa su builder** (`solution_builder.start_build`/`get_status`, F5 del 201), su `build.summary.json` (returncode/toolchain/salidas), su detección de toolchain + doctor (`build_toolchain.detect_toolchain`, F3 del 201), su scanner (`solution_scanner.scan_solutions_ex`, F1 del 201) y su store de catálogo (`solution_store.rescan_and_save`/`load_catalog`, F2 del 201). **210 NO reimplementa nada de eso**; lo invoca. Si el 201 todavía no está mergeado al implementar el 210, el 210 **degrada de forma controlada** (verdicto `build_workshop_unavailable` = "no verificado", nunca "Build OK") — ver F2, G7.
- **Es prerequisito de Plan 211** — "Inspector post-build y barrido de residuos de port entre clientes" (`Stacky Agents/docs/211_PLAN_INSPECTOR_POST_BUILD_Y_BARRIDO_DE_RESIDUOS_DE_PORT_ENTRE_CLIENTES.md`). El 211 **consume el `BuildVerdict`** y el `build.summary.json` que produce este plan, y se engancha en la **seam de contribuidores de evidencia** que expone F5 (`register_evidence_contributor`). No implementar 211 sin 210.
- **Coordina con Plan 208** — "Sincronización ADO al completar + Matriz de estados" (`Stacky Agents/docs/208_PLAN_SINCRONIZACION_ADO_AL_COMPLETAR_AGENTE_Y_MATRIZ_DE_ESTADOS_POR_TIPO_DE_TICKET_Y_AGENTE.md`, PROPUESTO v1). Cuando el 208 cablee la transición de estado ADO en los paths de runner (hoy solo el path manual la hace, ver §2), **debe llamar a `dev_build_verify.gate_final_state(...)`** (F4) para el `agent_type == "developer"`. Este plan expone esa función precisamente para que 208 la reuse. No hay colisión: 208 decide *a qué estado* transiciona la matriz; 210 decide *si el developer puede avanzar* a `next_state_ok` (requiere veredicto de máquina).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Hoy el Developer agéntico de Stacky **narra** "Build OK" como texto libre en su entregable (el LLM escribe `✓ Build OK`), y esa narración es lo que dispara la transición del ticket a "listo para QA" y lo que ve el revisor en Azure DevOps — sin que **ninguna máquina** haya compilado nada. Este plan agrega un **servicio determinista** (`dev_build_verify`) que resuelve la **entrada canónica de build** del proyecto (prefiere `.sln`), invoca el **builder real del Plan 201**, captura el `build.summary.json` y devuelve un **veredicto tipado** (`BuildVerdict`); y **endurece el DoD** para que el "Build OK" que llega a ADO — y la transición de estado que lo acompaña — **solo puedan emitirse si el veredicto de máquina es `ok` Y `entry_kind == 'sln'`**. El gate es **server-side y determinista**: no confía en la prosa del LLM (que puede narrar cualquier cosa) — el hecho lo produce la máquina, y la **ausencia** de veredicto se trata como **no verificado**, nunca como OK. Si no hay `.sln` o falta el toolchain .NET, el ticket va a estado de revisión/bloqueo con la razón exacta, jamás a "Build OK".

**Gap que cierra.** El "Build OK" es hoy 100% inverificable (ver §2 con anclas). Este plan convierte "el developer terminó y compila" de una **afirmación narrada** a un **hecho verificado por máquina**, sin agregar trabajo al operador y sin romper el contrato de salida existente.

**KPI / impacto medible (binarios).**
- **KPI-1 — Cero falsos verdes de estado:** % de transiciones del developer a `next_state_ok` (p.ej. "Reviewed by Dev") respaldadas por un `build.verdict.json` con `ok == true` y `entry_kind == 'sln'` = **100%**. Medible: contar transiciones final del developer vs. veredictos válidos (log `dev_build_gate.*`).
- **KPI-2 — Cero "Build OK" narrado sin respaldo:** en los deliverables publicados por el developer, el bloque "3. BUILD" que llega a ADO es **siempre** el bloque autoritativo de máquina (verde solo si veredicto `ok+sln`). Medible: sentinel de F5 (grep) verde + contador `dev_build_gate.neutralized_claim`.
- **KPI-3 — Trazabilidad:** 100% de las corridas del developer con la flag ON producen un `build.verdict.json` (aunque sea `reason == "toolchain_missing"` o `"no_sln"`). Medible: presencia del archivo por `ado_id`.
- **KPI-4 — Paridad 3 runtimes:** el núcleo (resolución de entrada + build + veredicto + gate) es Python determinista → **idéntico** en Codex/Claude/Copilot. Único roce con el LLM: la instrucción de prompt que dispara el endpoint (F6), con fallback duro (ausencia = no verificado).
- **KPI-5 — Cero regresión:** flag OFF → comportamiento byte-idéntico al actual (el developer narra como hoy). Ningún test existente se rompe.

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia verificada)

Cada ancla `archivo:línea` fue releída contra el repo el 2026-07-21 (no se cita de memoria):

1. **El "developer agéntico" = prompt + runner mínimo, y el runner NO compila ni verifica.** El runner `Stacky Agents/backend/agents/developer.py` tiene 36 líneas y solo define `system_prompt()` (`developer.py:27-35`): arma texto y nada más. La conducta de "compilar" vive únicamente en el prompt `Stacky Agents/backend/Stacky/agents/Developer.agent.md` (v2.1.1, `stacky_completion_contract: v1`, frontmatter `:4,:6`).

2. **"Build OK" es texto libre que narra el LLM — en DOS lugares del prompt:**
   - Seed boilerplate en el "RESUMEN RÁPIDO": `...para implementar la validación requerida. Build OK."` (`Developer.agent.md:301`).
   - Bloque HTML de build: `<p><span style="color:green"><strong>✓ Build OK</strong></span> — [solución compilada, configuración usada]</p>` (`Developer.agent.md:325-327`).
   No hay ningún gate determinista que verifique esa afirmación.

3. **El PASO 4 define "verificar" = correr el build y, si falla, iterar o reportar bloqueante — pero el DoD TERMINA en el exit code, narrado por el LLM.** `Developer.agent.md:197-199`: "Ejecutar el build descripto en la sección 'Compilación'. Si falla, iterar hasta que compile o reportar bloqueante." Cero verificación server-side; cero mención a que el hecho deba ser producido por máquina.

4. **El contrato de build del prompt apunta a `client_profile.build.online_solutions` (el `.sln`), pero el perfil default lo trae VACÍO.** `Developer.agent.md:152-168` (sección COMPILACIÓN) dice que las soluciones vienen de `client_profile.build.online_solutions`. Pero `Stacky Agents/backend/services/client_profile_defaults/azure_devops.json:39` trae `"online_solutions": []`. El fallback para vacío es "No compilar automáticamente; indicar al operador" (`Developer.agent.md:69`). **Nada prohíbe que el LLM derive a compilar un `.csproj` suelto (o nada) y lo cante como "Build OK".**

5. **No hay verificación de build en el cierre del run.** Grep de `build|compil|completion_contract` en `Stacky Agents/backend/app.py` → solo `build_ado_client` / `build_error_envelope`; nada compila. El cierre universal de agente es `services/ticket_status.py::on_execution_end` (registro de post-hooks en `ticket_status.register_post_hook`, usado en `app.py:853-855`), y ninguno de esos hooks verifica build.

6. **La transición de estado "developer terminó → next_state_ok" existe y HOY se dispara con la narración.** El developer cierra con un PATCH a `POST /api/tickets/by-ado/{ADO_ID}/stacky-status` (`Developer.agent.md:242-267`) mandando `target_ado_state`. En el modo determinista (default ON, `config.py:1192-1194` `STACKY_DETERMINISTIC_TASK_STATES_ENABLED`), el handler `set_stacky_status_by_ado` **ignora** el `target_ado_state` del agente y resuelve el estado final con `_apply_task_state(ticket=t, agent_type=agent_type, phase="final", ...)` (`api/tickets.py:1375-1384`), que usa `resolve_task_state_plan` + `_safe_transition`. **Ese `_apply_task_state` (`api/tickets.py:530`) es el punto exacto donde "el developer terminó bien" se materializa en ADO — hoy sin ninguna prueba de que compiló.** El path legacy (flag OFF) aplica el `target_ado_state` del agente directo (`api/tickets.py:1385-1416`).

7. **El publish del deliverable a ADO tiene un chokepoint universal.** Toda publicación pasa por `services/ado_publisher.py::publish_from_execution` (`ado_publisher.py:212`), que lee el HTML del agente con `agent_html_output.read_and_validate(ado_id, hint=...)` (`ado_publisher.py:306`; validador en `agent_html_output.py:123`) y lo manda a ADO. Lo invocan el post-hook (`ado_publish_post_hook`, `ado_publisher.py:514,:539`), el gateway (`agent_completion.py:840`) y el rescate (`rescue_execution.py:460`). **Un solo lugar donde interceptar el HTML antes de publicar** = `publish_from_execution` justo después de `read_and_validate`.

8. **Confirmación estructural del vacío:** el propio Plan 201 declara que "**Ninguna** pieza compila desde fuente" (`201_PLAN_...:34`). Hoy nada en Stacky compila código de cliente de forma determinista, así que el "Build OK" del developer es, por construcción, inverificable. Este plan crea el productor de ese hecho (reusando el builder del 201) y el gate que lo exige.

**Conclusión:** el trabajo es **aditivo, server-side y determinista**: un servicio nuevo (`dev_build_verify`) que reusa el builder del 201, un endpoint que lo dispara durante el run, y dos gates en puntos ya identificados (`_apply_task_state` para el estado; `publish_from_execution` para el deliverable). El prompt se endurece pero **el gate no confía en el prompt**.

---

## 3. Principios y guardarraíles (NO negociables — codificados en cada fase)

- **G1 · El hecho lo produce la máquina, no el LLM.** El `BuildVerdict` sale de correr el builder real del 201 sobre un `.sln` resuelto determinísticamente. El LLM **no puede fabricarlo**. La **ausencia** de veredicto = **no verificado** (nunca OK). Prompt-only está PROHIBIDO como única defensa.
- **G2 · Human-in-the-loop innegociable.** El build corre **dentro del run que el operador ya inició** (el agente lo dispara vía endpoint como parte de su trabajo autorizado). **No** se auto-compila fuera de un run, **no** se auto-instala toolchain, **no** se bypasea al operador. El gate **degrada** el estado a revisión/bloqueo; nunca fuerza un "Blocked" duro por sí solo (respeta el `block_guard` existente, `api/tickets.py:1345-1368`).
- **G3 · Determinista-primero, cero LLM en el núcleo.** Resolución de entrada + build + veredicto + gates + anotación del deliverable son Python puro/determinista → idéntico en los 3 runtimes.
- **G4 · Paridad de 3 runtimes.** El único punto que roza el LLM es la instrucción de prompt (F6) que dispara el endpoint; y aun si un runtime la ignora, la ausencia de veredicto degrada el estado igual (el gate es server-side). Fallback explícito en cada fase.
- **G5 · Mono-operador sin auth.** Cero RBAC. `current_user`/`X-User-Email` es informativo (se usa solo para distinguir "origen agente" vs "operador", igual que el `block_guard` actual).
- **G6 · No degradar performance/seguridad/estabilidad/DX.** El build ya está acotado por el timeout del 201 (`_BUILD_TIMEOUT_SEC = 1800`) y su cancelación. El veredicto se cachea en `build.verdict.json`. Backward-compatible: flag OFF = byte-idéntico. Ningún import de red/LLM en `dev_build_verify`.
- **G7 · EXCEPCIÓN DURA #3 (prerequisito no garantizado: MSBuild/.NET SDK).** El build depende de un toolchain ausente en instalación default. Esto NO se respeta apagando la feature: la flag queda **default ON** (resolución + veredicto + gate son seguros y read-only sobre el toolchain), y cuando el toolchain falta, el veredicto es `reason == "toolchain_missing"` con el **doctor** del 201 (`build_toolchain.detect_toolchain`), el estado va a revisión (no "Build OK") y el deliverable dice la verdad. **Nunca crashea, nunca auto-instala.** Mismo criterio si el builder del 201 aún no está mergeado: `reason == "build_workshop_unavailable"` (degrada, no rompe). Citada en F2, F3, F4.
- **G8 · Config vía UI.** La flag `STACKY_DEV_BUILD_VERIFY_ENABLED` es visible/toggleable desde **Configuración → Arnés → categoría DevOps** (cableada en `harness_flags.py`, no solo env var).

---

## 4. Flag del arnés + campo de perfil nuevo (default seguro) — cableado EXACTO

**Flag nueva:** `STACKY_DEV_BUILD_VERIFY_ENABLED` · tipo `bool` · **default ON** · categoría `devops` · sin `requires`.

Los 5 lugares (idéntico patrón al Plan 201 §4 y a la receta de memoria "Receta flag DEVOPS default-ON = 5 lugares"; anclas verificadas 2026-07-21):

| # | Archivo | Qué agregar | Ancla verificada |
|---|---------|-------------|------------------|
| 1 | `Stacky Agents/backend/services/harness_flags.py` | `FlagSpec(key="STACKY_DEV_BUILD_VERIFY_ENABLED", type="bool", label="Verificación de build del Developer", description="Verifica de forma determinista que el Developer compiló (.sln) antes de permitir 'Build OK' y la transición de estado. El build requiere toolchain .NET.", group="global", default=True)` dentro de `FLAG_REGISTRY`. | `class FlagSpec` = `harness_flags.py:21`; `FLAG_REGISTRY` = `harness_flags.py:379` |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | Agregar `"STACKY_DEV_BUILD_VERIFY_ENABLED",` a la tupla `_CATEGORY_KEYS["devops"]`. | `_CATEGORY_KEYS` = `harness_flags.py:117`; tupla `"devops"` = `harness_flags.py:202` |
| 3 | `Stacky Agents/backend/tests/test_harness_flags.py` | Agregar `"STACKY_DEV_BUILD_VERIFY_ENABLED",` al conjunto `_CURATED_DEFAULTS_ON`. | `test_harness_flags.py:467` (mismo set que usó el 201) |
| 4 | `Stacky Agents/backend/config.py` | Nuevo atributo de `Config`: `STACKY_DEV_BUILD_VERIFY_ENABLED: bool = os.getenv("STACKY_DEV_BUILD_VERIFY_ENABLED", "true").lower() in ("1", "true", "yes")` — espejá la forma de `STACKY_DETERMINISTIC_TASK_STATES_ENABLED`. | `config.py:1192-1194` (patrón default "true") |
| 5 | `Stacky Agents/backend/api/devops.py` | En el dict de `_health_payload()`, agregar `"dev_build_verify_enabled": bool(getattr(cfg, "STACKY_DEV_BUILD_VERIFY_ENABLED", False)),`. | patrón `*_enabled` en `devops.py` (mismo que el 201 lugar #5) |

> **NO hand-editar** `Stacky Agents/backend/harness_defaults.env` (lo genera `deployment/export_harness_defaults.py`; prohibido a mano — memoria "generador harness_defaults"). El default ON efectivo lo da `config.py` (lugar #4).
> **NO** hay `requires=` → NO se toca `_REQUIRES_MAP_FROZEN` ni bounds-map (es `bool`).
> Efecto colateral inocuo del lugar #5: la key aparece también en `/devops/bootstrap` (dict compartido); es intencional (paridad), igual que documentó el 201 (C10).

**Campo de perfil nuevo (default seguro):** `build.allow_csproj_entry` · tipo `bool` · **default `false`**.
- Semántica: un `.csproj` suelto (sin `.sln`) **NO** cuenta como entrada de build verificable **salvo** que el perfil lo declare `true` explícitamente. Con `false` (default), si no hay `.sln`, el veredicto es `reason == "no_sln"` → **bloqueante** (nunca "Build OK").
- Se agrega al template default en `Stacky Agents/backend/services/client_profile_defaults/azure_devops.json` dentro de `"build"` (junto a `online_solutions`, `azure_devops.json:35-41`): `"allow_csproj_entry": false`.
- **No** requiere migración: `resolve_build_entry` lee `profile.get("build", {}).get("allow_csproj_entry", False)` → los perfiles viejos (sin la clave) se comportan como `false` (el más seguro). El editor de perfil (`ClientProfileEditor.tsx`) puede exponerlo en un follow-up; no es requisito de este plan (G1: default seguro sin tocar UI).

---

## 5. Arquitectura objetivo (mapa de artefactos)

```
BACKEND (Stacky Agents/backend/)
  services/dev_build_verify.py     (F1/F2/F4/F5) NÚCLEO determinista:
                                     - resolve_build_entry (F1, PURO)
                                     - BuildVerdict + verify_build (F2, invoca builder del 201)
                                     - write_verdict/read_verdict/verdict_path (F2)
                                     - gate_final_state (F4)  ← lo reusa Plan 208
                                     - annotate_build_evidence + register_evidence_contributor (F5)  ← lo reusa Plan 211
  api/dev_build.py                 (F3) blueprint: POST /api/tickets/by-ado/<ado_id>/dev/build-verify
  api/tickets.py                   (F4) wiring del gate en _apply_task_state (:530) + rama legacy (:1385)
  services/ado_publisher.py        (F5) wiring de annotate_build_evidence en publish_from_execution (:306)
  Stacky/agents/Developer.agent.md (F6) prompt endurecido (quita seed, reescribe PASO 4 + BUILD, v2.2.0)

FRONTEND (Stacky Agents/frontend/src/)
  components/OutputPanel.tsx        (F7) pane "Build (verificado por máquina)" desde execution.metadata.build_verdict
  components/devBuildModel.ts       (F7) helpers PUROS testeables (label/color/formato)
  components/devBuildModel.test.ts  (F7) vitest del modelo puro

DATOS (en el workspace del cliente, junto al deliverable)
  <workspace_root>/Agentes/outputs/<ado_id>/build.verdict.json   veredicto persistido (F2)
  <workspace_root>/Agentes/outputs/<ado_id>/comment.html         deliverable (anotado por F5 al publicar)
```

**Contrato `BuildVerdict` (CONGELADO por F2 — Plan 211 lo consume tal cual):**

```json
{
  "ok": false,
  "gate_ok": false,
  "entry_kind": "none",
  "solution": "",
  "solutions": [],
  "returncode": -1,
  "summary_path": "",
  "reason": "no_sln",
  "toolchain": { "available": false, "builder": null, "version": null },
  "build_id": "",
  "verified_at": "2026-07-21T12:00:00Z",
  "blocking_findings": [],
  "warnings": []
}
```
- `ok` = el build corrió y **todas** las soluciones devolvieron returncode 0.
- `entry_kind` ∈ `{"sln","csproj","none"}`.
- `gate_ok` = `ok and entry_kind == "sln" and not blocking_findings` → **este** es el booleano que gobierna el estado y el verde del deliverable.
- `solution` = ruta de la `.sln` primaria (primera) construida, o `""`. `solutions` = todas las construidas.
- `returncode` = agregado (0 sii todas 0; el peor returncode si alguna falló; `-1` si no se construyó).
- `reason` ∈ el conjunto congelado `_REASONS` (ver F2).
- `blocking_findings` / `warnings` = **puntos de extensión** que los contribuidores de F5 (Plan 211) rellenan; cada item `{ "kind": str, "severity": "blocking"|"warning", "file": str, "detail": str }`.

---

## 6. Fases

> Convención de tests: **backend** = pytest **por archivo** con el intérprete del backend; **frontend** = vitest **por archivo** (contaminación cross-file conocida — memoria `gotcha-vitest-test-order-pollution-frontend`).
> **Comando backend** (desde `Stacky Agents/backend`): `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q` — si `.venv` no existe, usar `venv\Scripts\python.exe` (mismo py3.13).
> **Comando frontend** (desde `Stacky Agents/frontend`): `npx vitest run src\components\<archivo>.test.ts`.
> **Registrar** CADA `test_*.py` nuevo en `Stacky Agents/backend/scripts/run_harness_tests.sh` array `HARNESS_TEST_FILES` (`run_harness_tests.sh:20`) o el meta-ratchet se pone rojo (memoria `stacky-ratchet-obliga-registrar-tests`).

---

### F0 — Flag + campo de perfil + esqueleto (gate primero)

**Objetivo:** dejar la flag cableada (5 lugares §4) y el campo `build.allow_csproj_entry` en el template default, con `dev_build_verify.py` creado exponiendo solo constantes y firmas (stubs que devuelven `not_verified`), sin lógica. Valor: de-riesga toda la ceremonia de flags/health antes de la lógica.

**Archivos a editar/crear:**
- Los 5 de §4 (harness_flags.py ×2, test_harness_flags.py, config.py, api/devops.py).
- `Stacky Agents/backend/services/client_profile_defaults/azure_devops.json` — agregar `"allow_csproj_entry": false` dentro de `"build"` (`azure_devops.json:35-41`).
- Crear `Stacky Agents/backend/services/dev_build_verify.py` con: la constante `_REASONS` (tupla congelada, ver F2), el dataclass `BuildVerdict` (campos de §5, `@dataclass(frozen=True)`) con un factory `_not_verified(reason: str) -> BuildVerdict`, y las firmas públicas de F1-F5 como stubs (`raise NotImplementedError` NO; devolver `_not_verified("not_verified")` o `html` sin cambios, para que importar el módulo nunca rompa).

**Nombres exactos:** flag `STACKY_DEV_BUILD_VERIFY_ENABLED`; health key `dev_build_verify_enabled`; campo perfil `build.allow_csproj_entry`; módulo `services/dev_build_verify.py`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_flag.py`:**
- `test_flag_registered_and_curated`: la key está en `FLAG_REGISTRY`, en `_CATEGORY_KEYS["devops"]` y en `_CURATED_DEFAULTS_ON`.
- `test_health_exposes_dev_build_verify_enabled`: `/api/devops/health` incluye `dev_build_verify_enabled` (molde `test_plan120_api.py`).
- `test_default_profile_has_allow_csproj_entry_false`: `json.load(azure_devops.json)["build"]["allow_csproj_entry"] is False`.
- `test_module_imports_clean`: `import services.dev_build_verify` no lanza; `_not_verified("x").gate_ok is False`.
- Registrar `tests/test_plan210_flag.py` en `HARNESS_TEST_FILES`.
- Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan210_flag.py tests\test_harness_flags.py -q`

**Criterio de aceptación BINARIO:**
- Comando anterior → verde.
- `grep -rn "STACKY_DEV_BUILD_VERIFY_ENABLED" "Stacky Agents/backend/config.py"` → 1+ match.
- `grep -n "allow_csproj_entry" "Stacky Agents/backend/services/client_profile_defaults/azure_devops.json"` → 1 match.

**Flag:** `STACKY_DEV_BUILD_VERIFY_ENABLED` (default ON). **Impacto runtime:** idéntico 3/3 (solo registro/stubs). **Trabajo del operador:** ninguno.

---

### F1 — Resolución determinista de la entrada de build (`resolve_build_entry`)

**Objetivo:** función pura que decide, sin LLM, cuál es la entrada canónica de build del proyecto: prefiere `.sln`; si `online_solutions` está vacío, escanea; si no hay `.sln`, es bloqueante; un `.csproj` suelto no cuenta salvo `allow_csproj_entry`. Valor: es el corazón "nunca 'Build OK' sin un `.sln` real".

**Archivo a editar:** `Stacky Agents/backend/services/dev_build_verify.py`.

**API pública (nombres exactos):**
```python
def resolve_build_entry(profile: dict, workspace_root: str | None) -> dict
# devuelve {"entry_kind": "sln"|"csproj"|"none", "solutions": list[str], "reason": str}
```

**Reglas (deterministas, en orden):**
1. `workspace_root` falsy o no es dir → `{"entry_kind":"none","solutions":[],"reason":"workspace_missing"}`.
2. `declared = profile.get("build", {}).get("online_solutions") or []`. Para cada entrada declarada, resolver a ruta absoluta bajo `workspace_root` (si es relativa) y quedarse con las que existen y terminan en `.sln`. Si queda ≥1 → `{"entry_kind":"sln","solutions":[...abs...],"reason":"ok"}`.
3. Si `declared` no rindió `.sln`: **escanear** con el scanner del Plan 201 → `from services.solution_scanner import scan_solutions_ex` dentro de un `try/except ImportError` (el 201 puede no estar mergeado). `found = [s["sln_path"] for s in scan_solutions_ex(workspace_root)["solutions"]]`. Si ≥1 → `{"entry_kind":"sln","solutions": sorted(found), "reason":"ok"}`. Si `ImportError` → seguir al paso 4 con `found = []` (no romper).
4. Sin `.sln`: si `profile.get("build", {}).get("allow_csproj_entry", False)` es `True`, intentar hallar un `.csproj` (via `scan_solutions_ex` proyectos, o un `os.walk` acotado propio idéntico al patrón `pipeline_stack_detector.py:31-49` si el scanner no está): si hay ≥1 → `{"entry_kind":"csproj","solutions":[...],"reason":"csproj_entry"}`. Si no → `{"entry_kind":"none","solutions":[],"reason":"no_sln"}`.
5. Sin `.sln` y `allow_csproj_entry` False → `{"entry_kind":"none","solutions":[],"reason":"csproj_not_allowed"}` si detectó `.csproj` pero no está permitido, o `"no_sln"` si no hay nada. (Distinguirlos ayuda al mensaje; ambos son bloqueantes.)

**Casos borde (cubrir en tests):** perfil sin `build` → trata como `online_solutions=[]`, `allow_csproj_entry=False`; `online_solutions` con rutas inexistentes → se descartan, cae a escaneo; `.sln` declarado relativo → se resuelve contra `workspace_root`; scanner ausente (`ImportError`) → no crashea, degrada a `no_sln`/`csproj_*`; workspace con solo `.csproj` y `allow_csproj_entry=True` → `entry_kind="csproj"`; ídem con `False` → `entry_kind="none"`, `reason="csproj_not_allowed"`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_resolve_entry.py`:** (usar `tmp_path`, escribir `.sln`/`.csproj` fixtures; monkeypatch `services.solution_scanner.scan_solutions_ex` cuando se quiera aislar del 201)
- `test_workspace_missing_returns_none`
- `test_declared_online_solutions_win` (perfil con `online_solutions=["src/App.sln"]` real → `entry_kind=="sln"`, ruta absoluta)
- `test_empty_online_solutions_falls_back_to_scan` (perfil `online_solutions=[]`, un `.sln` en disco → `entry_kind=="sln"`)
- `test_no_sln_is_blocking` (solo `.csproj`, `allow_csproj_entry` ausente → `entry_kind=="none"`, `reason in {"no_sln","csproj_not_allowed"}`)
- `test_csproj_allowed_when_opted_in` (`allow_csproj_entry=True`, un `.csproj` → `entry_kind=="csproj"`)
- `test_scanner_import_error_degrades` (monkeypatch para simular `ImportError` del scanner → no crashea, `entry_kind=="none"`)
- Registrar en `HARNESS_TEST_FILES`. Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan210_resolve_entry.py -q`

**Criterio BINARIO:** comando verde; `grep -nE "import requests|import runtime$|copilot|llm" "Stacky Agents/backend/services/dev_build_verify.py"` → **0 matches** (núcleo sin red/LLM).

**Flag:** el servicio no chequea flag (lo hace el endpoint F3/los gates F4-F5). **Runtime:** idéntico 3/3. **Trabajo del operador:** ninguno.

---

### F2 — `verify_build` + persistencia del veredicto (invoca el builder del 201)

**Objetivo:** correr el build real (builder del Plan 201) sobre la entrada resuelta, capturar el `build.summary.json`, y producir/persistir un `BuildVerdict`. Valor: el hecho producido por máquina.

**Archivo a editar:** `Stacky Agents/backend/services/dev_build_verify.py`.

**Constante congelada de razones (parte del contrato):**
```python
_REASONS = ("ok", "no_sln", "csproj_not_allowed", "csproj_entry", "build_failed",
            "toolchain_missing", "build_workshop_unavailable", "workspace_missing", "not_verified")
```

**API pública (nombres exactos):**
```python
def verdict_path(ado_id: int, workspace_root: str | None) -> Path
def write_verdict(ado_id: int, workspace_root: str | None, verdict: BuildVerdict) -> None
def read_verdict(ado_id: int, workspace_root: str | None) -> BuildVerdict | None
def verify_build(*, ado_id: int, project_name: str, workspace_root: str | None) -> BuildVerdict
```

- **`verdict_path`**: `Path(workspace_root)/"Agentes"/"outputs"/str(ado_id)/"build.verdict.json"` (mismo layout que el deliverable, `Developer.agent.md:209-210`). Si `workspace_root` es None → `data_dir()/"dev_build_verdicts"/f"{ado_id}.json"` (fallback dev; `from runtime_paths import data_dir`).
- **`write_verdict`**: `mkdir(parents=True, exist_ok=True)` + `json.dumps(asdict(verdict), indent=2, ensure_ascii=False)` con `errors="replace"`. Nunca lanza hacia afuera (best-effort; loguea y sigue).
- **`read_verdict`**: lee y reconstruye el `BuildVerdict`; si el archivo no existe o es inválido → `None` (el caller trata `None` como "no verificado").

**Pseudocódigo `verify_build` (EXCEPCIÓN DURA #3 y dependencia del 201):**
```python
def verify_build(*, ado_id, project_name, workspace_root):
    from services.client_profile import load_effective_client_profile
    profile = load_effective_client_profile(project_name) or {}
    entry = resolve_build_entry(profile, workspace_root)
    now = _utcnow_iso()
    if entry["entry_kind"] != "sln":
        # sin .sln => BLOQUEANTE. Nunca "Build OK".
        v = _not_verified(entry["reason"], entry_kind=entry["entry_kind"],
                          solutions=entry["solutions"], verified_at=now)
        write_verdict(ado_id, workspace_root, v); return v
    # toolchain (doctor del 201) — read-only, nunca instala (G7)
    tc = _detect_toolchain_safe()          # try import build_toolchain.detect_toolchain; si ImportError => {"available": False,...}
    if not tc.get("available"):
        v = _not_verified("toolchain_missing", entry_kind="sln",
                          solutions=entry["solutions"], toolchain=tc, verified_at=now)
        write_verdict(ado_id, workspace_root, v); return v
    # invocar el builder real del 201 (F2 depende de que exista)
    try:
        from services import solution_builder, solution_store
    except ImportError:
        v = _not_verified("build_workshop_unavailable", entry_kind="sln",
                          solutions=entry["solutions"], toolchain=tc, verified_at=now)
        write_verdict(ado_id, workspace_root, v); return v
    # mapear cada .sln -> slug del catálogo (rescan idempotente del 201)
    solution_store.rescan_and_save(workspace_root)
    slugs = _slugs_for_solutions(entry["solutions"], workspace_root, solution_store)
    build_id = solution_builder.start_build(slugs, unified=(len(slugs) > 1), workspace_root=str(workspace_root))
    summary = _poll_until_terminal(solution_builder, build_id)   # respeta _VERIFY_POLL_TIMEOUT_SEC
    rc = _aggregate_returncode(summary)          # 0 sii todas 0
    ok = (summary.get("status") == "success" and rc == 0)
    v = BuildVerdict(
        ok=ok, gate_ok=ok, entry_kind="sln",
        solution=(entry["solutions"][0] if entry["solutions"] else ""),
        solutions=tuple(entry["solutions"]),
        returncode=rc,
        summary_path=summary.get("_summary_path", ""),
        reason=("ok" if ok else "build_failed"),
        toolchain={"available": True, "builder": tc.get("builder"), "version": tc.get("version")},
        build_id=build_id, verified_at=now,
        blocking_findings=(), warnings=())
    write_verdict(ado_id, workspace_root, v); return v
```
- `_detect_toolchain_safe()`: `try: from services.build_toolchain import detect_toolchain; return detect_toolchain() except Exception: return {"available": False, "builder": None, "version": None, "remediation": None}`.
- `_poll_until_terminal(builder, build_id)`: loop leyendo `builder.get_status(build_id)` cada `_POLL_INTERVAL_SEC = 2` hasta `status in {"success","failed","cancelled","toolchain_missing"}` o `_VERIFY_POLL_TIMEOUT_SEC = 1800`; devuelve el `summary` (contenido de `build.summary.json` del 201, ADICIÓN 2 del 201) + `_summary_path`. Si expira → status sintético `"failed"`.
- `_slugs_for_solutions(...)`: para cada `.sln` en `solutions`, buscar en `solution_store.load_catalog(workspace_root)["solutions"]` el `slug` cuyo `sln_path == esa ruta`; si no está, saltarla (defensivo).
- `_aggregate_returncode(summary)`: `max(abs(rc) for rc in summary.get("returncodes", {}).values())` con 0 si vacío; devuelve 0 sii todos 0.

**Casos borde:** sin `.sln` → `no_sln`/`csproj_not_allowed`, no corre build; toolchain ausente → `toolchain_missing`; builder del 201 ausente (`ImportError`) → `build_workshop_unavailable`; build falla → `build_failed`, `ok=False`; timeout de poll → `build_failed`; `.sln` sin slug en catálogo → se omite (si quedan 0 slugs → `ok=False`, `build_failed`).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_verify_build.py`:** (monkeypatch: `services.dev_build_verify._detect_toolchain_safe`, `services.solution_builder.start_build`/`get_status`, `services.solution_store.rescan_and_save`/`load_catalog`; `load_effective_client_profile`; `tmp_path` como workspace)
- `test_no_sln_writes_blocking_verdict_no_build` (assert `start_build` NUNCA se llamó; `read_verdict(...).reason in {"no_sln","csproj_not_allowed"}`, `gate_ok is False`)
- `test_toolchain_missing_verdict` (`_detect_toolchain_safe` → `available False` → `reason=="toolchain_missing"`, `ok is False`, `start_build` no llamado)
- `test_workshop_unavailable_when_builder_import_fails` (simular `ImportError` de `solution_builder` → `reason=="build_workshop_unavailable"`)
- `test_success_verdict_ok_and_gate_ok` (fake `get_status` termina en `success` con `returncodes={"app":0}` → `ok`, `gate_ok`, `entry_kind=="sln"`, `summary_path` no vacío)
- `test_build_failed_sets_reason` (fake `returncodes={"app":1}` → `ok False`, `reason=="build_failed"`)
- `test_verdict_roundtrip` (`write_verdict` luego `read_verdict` reconstruye el mismo `BuildVerdict`)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "start_build" "Stacky Agents/backend/services/dev_build_verify.py"` → 1+ match (invoca el builder del 201); el veredicto de `no_sln`/`toolchain_missing` NUNCA tiene `gate_ok True`.

**Flag:** el endpoint F3 gatea. **Runtime:** idéntico 3/3 (el build es MSBuild/dotnet, no LLM). **EXCEPCIÓN DURA #3** citada (ramas `toolchain_missing` y `build_workshop_unavailable`). **Operador:** ninguno directo (corre dentro del run del agente).

---

### F3 — Endpoint disparador (`POST /api/tickets/by-ado/<ado_id>/dev/build-verify`)

**Objetivo:** exponer `verify_build` por HTTP para que el Developer lo dispare durante su PASO 4. Determinista, server-side. Valor: el agente produce el hecho de máquina como parte de su run.

**Archivo a crear:** `Stacky Agents/backend/api/dev_build.py`.

**Blueprint (patrón `devops_deployments.py` / registro `api/__init__.py`):**
```python
bp = Blueprint("dev_build", __name__)

@bp.post("/tickets/by-ado/<int:ado_id>/dev/build-verify")
def build_verify_route(ado_id: int):
    import config as _config
    if not bool(getattr(_config.config, "STACKY_DEV_BUILD_VERIFY_ENABLED", False)):
        return jsonify({"error": "dev_build_verify deshabilitado"}), 404
    # resolver proyecto + workspace del ticket
    project_name = _project_name_for_ado(ado_id)     # del Ticket.stacky_project_name (session_scope)
    workspace_root = _workspace_root_for_project(project_name)  # runtime_paths / project config
    verdict = dev_build_verify.verify_build(ado_id=ado_id, project_name=project_name,
                                            workspace_root=workspace_root)
    return jsonify({"verdict": asdict(verdict)}), 200
```
- Guard por flag con `404` (patrón del 201 F4), usando la **instancia** `_config.config` (memoria `gotcha-config-config-vs-modulo`).
- **Helper público canónico (definido en `dev_build_verify.py`, lo reusan F3/F4/F5 y el Plan 211 — una sola implementación, cero duplicación):**
  - `dev_build_verify.project_name_for_ado(ado_id) -> str | None`: `with session_scope() as s: t = s.query(Ticket).filter(Ticket.ado_id==ado_id).first(); return t.stacky_project_name if t else None`.
  - `dev_build_verify.workspace_root_for_ado(ado_id) -> str | None`: compone `project_name_for_ado` + resolución de workspace (leer `projects/<name.upper()>/config.json → workspace_root`; si el ticket es del proyecto activo, `runtime_paths._active_workspace_root()`; si no, `project_manager.get_project_config(name)["workspace_root"]`). Si no resuelve → `None` (los callers degradan; `verify_build` devuelve `workspace_missing`, no 500).
- El endpoint F3 usa `ws = dev_build_verify.workspace_root_for_ado(ado_id)`; el gate F4 y la anotación F5 usan **el mismo** helper (no reimplementan la resolución).
- **Siempre responde 200** con el veredicto (aun bloqueante), para que el `api.post` del front/agente lo renderice (memoria `gotcha-frontend-api-wrapper-lanza-en-non-2xx`). Solo `404` si la flag está OFF.

**Registro del blueprint (patrón `api/__init__.py`):**
- Import: `from .dev_build import bp as dev_build_bp  # Plan 210 — gate de build del Developer`
- Registro: `api_bp.register_blueprint(dev_build_bp)  # Plan 210 — /api/tickets/by-ado/<ado_id>/dev/build-verify`

**Casos borde:** flag OFF → `404`; ado_id sin ticket en BD → `project_name=None` → `verify_build` degrada a `workspace_missing` → 200 bloqueante; sin workspace → 200 `workspace_missing`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_api.py`:** (Flask test client; monkeypatch `dev_build_verify.verify_build` para no correr build real; `_config.config` para flag)
- `test_verify_off_returns_404` (flag OFF)
- `test_verify_returns_verdict_200` (monkeypatch `verify_build` → un `BuildVerdict` fake → `resp.json["verdict"]["gate_ok"]` presente)
- `test_verify_unknown_ado_still_200_blocking` (sin ticket → `verify_build` recibe `project_name None`; assert 200)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.
- **GOTCHA:** para flag OFF/ON en test usar `monkeypatch.setattr(_config.config, "STACKY_DEV_BUILD_VERIFY_ENABLED", False)` sobre la **instancia**, NO `importlib.reload(config)` (memoria `gotcha-config-reload-harness-flags-contamina`).

**Criterio BINARIO:** comando verde; `grep -rn "dev_build_bp" "Stacky Agents/backend/api/__init__.py"` → 2 matches (import + register).

**Flag:** `STACKY_DEV_BUILD_VERIFY_ENABLED`. **Runtime:** idéntico 3/3. **EXCEPCIÓN DURA #3** (rutas doctor/unavailable). **Operador:** ninguno (lo dispara el agente).

---

### F4 — Gate de estado en `_apply_task_state` (fin del avance sin build)

**Objetivo:** que la transición del developer a `next_state_ok` **solo** ocurra si `gate_ok`; si no, degradar a estado de revisión (nunca "Blocked" duro, nunca avanzar). Valor: el consecuencial "developer terminó" pasa a exigir el hecho de máquina.

**Archivo a editar:** `Stacky Agents/backend/api/tickets.py` (y la función pública en `dev_build_verify.py`).

**API pública nueva en `dev_build_verify.py` (la reusa Plan 208):**
```python
def gate_final_state(*, project_name: str | None, agent_type: str | None,
                     ado_id: int, workspace_root: str | None,
                     proposed_state: str | None) -> tuple[str | None, dict]
```
- Si flag OFF o `agent_type != "developer"` → `(proposed_state, {"applied": False, "reason": "not_applicable"})`.
- `verdict = read_verdict(ado_id, workspace_root)`. Si `verdict is None` → tratar como no verificado (`gate_ok=False`, `reason="not_verified"`).
- Si `verdict.gate_ok` → `(proposed_state, {"applied": True, "gate_ok": True, "reason": verdict.reason})` (deja pasar el estado que resolvió la config/matriz).
- Si NO `gate_ok` → resolver estado de revisión reusando `_resolve_agent_block_states(project_name, "developer")` (está en `api/tickets.py:505`): tomar `review_state`. Devolver `(review_state, {"applied": True, "gate_ok": False, "reason": verdict.reason, "downgraded_from": proposed_state})`. Si `review_state` es None → `(None, {...})` (cancelar la transición: mejor dejar el ticket donde está que avanzar en falso — mismo criterio que el `block_guard`, `api/tickets.py:1366-1368`).

**Wiring en `_apply_task_state` (`api/tickets.py:530`):** localizar, dentro de esa función, el punto donde se resuelve el estado final (via `resolve_task_state_plan`) y ANTES de `_safe_transition`, envolver el estado con el gate SOLO para `phase == "final"`:
```python
# Plan 210 — gate de build del Developer: no avanzar a next_state_ok sin veredicto de máquina.
if phase == "final":
    _ws = dev_build_verify.workspace_root_for_ado(int(ticket.ado_id) if ticket.ado_id else 0)  # helper público (F3)
    resolved_state, _gate_meta = dev_build_verify.gate_final_state(
        project_name=ticket.stacky_project_name, agent_type=agent_type,
        ado_id=int(ticket.ado_id) if ticket.ado_id else 0,
        workspace_root=_ws, proposed_state=resolved_state)
    if _gate_meta.get("applied"):
        logger.info("dev_build_gate: ADO-%s agent=%s gate_ok=%s reason=%s state=%s",
                    ticket.ado_id, agent_type, _gate_meta.get("gate_ok"),
                    _gate_meta.get("reason"), resolved_state)
```
- Si `resolved_state` termina `None`, `_apply_task_state` debe devolver `{"skipped": True, "reason": "dev_build_gate_no_state"}` sin llamar a `_safe_transition` (agregá el early-return).
- **Rama legacy (flag determinista OFF, `api/tickets.py:1385`):** aplicar el MISMO gate sobre `target_ado_state` antes de `update_item_state`: si el agente propuso su `next_state_ok` pero `gate_final_state` degrada → usar el estado degradado (o cancelar). Esto cubre el caso `STACKY_DETERMINISTIC_TASK_STATES_ENABLED=false`.

**Casos borde:** `agent_type != "developer"` → passthrough (no toca ningún otro agente); flag OFF → passthrough; sin veredicto → degrada (ausencia = no verificado); `review_state` desconocido → cancela transición; ticket sin `ado_id` → gate corre con `ado_id=0` y `read_verdict` da None → degrada (no crashea).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_state_gate.py`:** (test unitario de `gate_final_state` + un test de integración de `_apply_task_state` con monkeypatch de `read_verdict` y `_resolve_agent_block_states`)
- `test_gate_passthrough_for_non_developer` (agent_type "technical" → estado intacto)
- `test_gate_passthrough_when_flag_off`
- `test_gate_allows_when_verdict_gate_ok` (verdict `gate_ok True` → estado propuesto intacto)
- `test_gate_downgrades_when_no_verdict` (`read_verdict → None` → estado = review_state, nunca next_state_ok)
- `test_gate_downgrades_when_build_failed` (verdict `reason="build_failed"`, `gate_ok False` → review_state)
- `test_gate_cancels_when_no_review_state` (review_state None → `(None, ...)`)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "gate_final_state" "Stacky Agents/backend/api/tickets.py"` → 1+ match; test existente `test_...` de `_apply_task_state`/`stacky-status` (si lo hay) sigue verde con flag OFF.

**Flag:** `STACKY_DEV_BUILD_VERIFY_ENABLED`. **Runtime:** idéntico 3/3 (Python determinista; ningún runner difiere). **Operador:** ninguno; el estado refleja la verdad de máquina.

---

### F5 — Anotación autoritativa del deliverable (fin del "Build OK" narrado en ADO)

**Objetivo:** que el bloque "3. BUILD" que llega a ADO sea el **veredicto de máquina** (verde solo si `gate_ok`), neutralizando cualquier verde no respaldado que el LLM haya escrito. Punto único: `publish_from_execution`. Además, exponer la **seam de contribuidores** que consume Plan 211. Valor: ADO muestra la verdad, no la narración.

**Archivos a editar:** `Stacky Agents/backend/services/dev_build_verify.py` (funciones) + `Stacky Agents/backend/services/ado_publisher.py` (wiring).

**API pública nueva en `dev_build_verify.py`:**
```python
_EVIDENCE_CONTRIBUTORS: list = []   # Plan 211 registra acá
def register_evidence_contributor(fn) -> None    # fn(ado_id, verdict) -> {"title","section_html","blocking":[...],"warnings":[...]}
def annotate_build_evidence(*, ado_id: int, agent_type: str | None,
                            workspace_root: str | None, html: str) -> str
```

**Lógica de `annotate_build_evidence`:**
1. Si flag OFF o `agent_type != "developer"` → devolver `html` sin cambios (passthrough).
2. `verdict = read_verdict(ado_id, workspace_root)`; si None → construir un veredicto sintético `_not_verified("not_verified")` (para anotar "no verificado").
3. Correr los contribuidores registrados (Plan 211): acumular `section_html` extra, y **fusionar** sus `blocking`/`warnings` en el veredicto; recomputar `gate_ok = verdict.ok and verdict.entry_kind=="sln" and not blocking`. **Re-persistir** el veredicto con `write_verdict` (para que el gate de estado F4, que corre después en el mismo request del PATCH, lea los findings del 211).
4. Construir el **bloque autoritativo** de máquina (HTML), verde solo si `gate_ok`:
   - `gate_ok True`: `<span style="color:green"><strong>✓ Build OK (verificado por máquina)</strong></span>` + solución(es) + toolchain + returncode + link/nombre del `build.summary.json`.
   - `gate_ok False`: `<span style="color:red"><strong>✗ Build NO verificado</strong></span>` + razón legible (`_REASON_LABEL[reason]`, p.ej. `no_sln`→"No se encontró ninguna solución .sln para compilar", `toolchain_missing`→"Falta el toolchain .NET (ver doctor)", `build_failed`→"La compilación devolvió errores", `build_workshop_unavailable`→"El Taller de Compilación (Plan 201) no está disponible") + los `blocking_findings` si los hay.
5. **Neutralizar** el verde no respaldado del LLM: si `not gate_ok`, reemplazar en `html` cualquier coincidencia (case-insensitive) de un verde de build por una marca tachada. Regex determinista acotada al patrón del prompt: `re.sub(r'(?is)<span[^>]*color\s*:\s*green[^>]*>\s*<strong>\s*[✓✔]?\s*Build OK.*?</strong>\s*</span>', _STRUCK_BUILD_CLAIM, html)`. `_STRUCK_BUILD_CLAIM = '<span style="color:#888"><s>Build OK (afirmación no verificada — ver veredicto de máquina)</s></span>'`. Contador `dev_build_gate.neutralized_claim` (log).
6. Insertar el bloque autoritativo: reemplazar el contenido bajo el marcador `<h2>3. BUILD</h2>` si existe (regex hasta el próximo `<hr>`); si no existe el marcador, **anexar** el bloque al final del `html`. Idempotente: si ya está el bloque de máquina (marca comentario `<!-- dev_build_verify -->`), no duplicar.

**Wiring en `ado_publisher.publish_from_execution` (`ado_publisher.py:212`):** justo después de `output = html_io.read_and_validate(ado_id, hint=hint)` (`ado_publisher.py:306`) y antes de mandar el HTML a ADO, interceptar el cuerpo:
```python
# Plan 210 — anotar el deliverable con el veredicto de build de máquina (developer).
try:
    _agent_type = _agent_type_for_execution(execution_id)   # helper local, del AgentExecution
    _ws = dev_build_verify.workspace_root_for_ado(ado_id)   # helper público (F3), no reimplementar
    output = html_io.replace_body(output, dev_build_verify.annotate_build_evidence(
        ado_id=ado_id, agent_type=_agent_type, workspace_root=_ws, body=output.html))
except Exception:
    logger.exception("dev_build_verify: anotación falló (se publica el original)")  # G6: nunca romper publish
```
- Si `agent_html_output` no expone un `replace_body`, aplicar la anotación sobre el string HTML directamente antes de construir el payload de publicación (el implementador confirma el shape de `output` leyendo `agent_html_output.py:123` — es el `read_and_validate`). Lo esencial: **el HTML publicado es el anotado**.
- Envuelto en `try/except` total: si algo falla, se publica el HTML original (G6: la anotación **nunca** rompe la publicación).

**Casos borde:** no developer → passthrough; sin veredicto → bloque "no verificado" + neutraliza verde; deliverable sin sección "3. BUILD" → anexa bloque al final; doble publicación (idempotencia) → no duplica el bloque; HTML sin verde → solo inserta el bloque autoritativo.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_annotate.py`:** (unit de `annotate_build_evidence` con HTML fixture; monkeypatch `read_verdict`)
- `test_passthrough_non_developer`
- `test_ok_verdict_inserts_green_authoritative_block` (verdict `gate_ok True` → contiene "Build OK (verificado por máquina)" en verde)
- `test_no_verdict_neutralizes_llm_green` (HTML con `<span style="color:green"><strong>✓ Build OK</strong></span>`; verdict None → el verde queda tachado y hay bloque rojo "no verificado")
- `test_build_failed_shows_red_reason`
- `test_idempotent_double_annotation` (anotar dos veces no duplica el bloque)
- `test_contributor_findings_flip_gate_and_persist` (registrar un contribuidor fake que devuelve un `blocking` → `gate_ok` pasa a False y `read_verdict` refleja el finding) — cierra la seam de Plan 211
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "annotate_build_evidence" "Stacky Agents/backend/services/ado_publisher.py"` → 1+ match; `grep -n "register_evidence_contributor" "Stacky Agents/backend/services/dev_build_verify.py"` → 1+ match.

**Flag:** `STACKY_DEV_BUILD_VERIFY_ENABLED`. **Runtime:** idéntico 3/3 (Python; se aplica sea cual sea el runtime que produjo el HTML). **Operador:** ninguno; ve la verdad en ADO.

---

### F6 — Endurecer el prompt del Developer (paridad 3 runtimes)

**Objetivo:** que el prompt deje de sembrar "Build OK" narrado, dispare el endpoint de verificación en PASO 4, e interprete el veredicto de máquina. Valor: alinea la conducta del LLM con el gate (aunque el gate no dependa de esto).

**Archivo a editar:** `Stacky Agents/backend/Stacky/agents/Developer.agent.md`. Bump `version: "2.1.1"` → `version: "2.2.0"` (frontmatter `:4`).

**Ediciones EXACTAS:**
1. **Quitar el seed "Build OK." (`:301`).** Reemplazar:
   `<p>[2-3 líneas. Ej: "Se modificó <code>ClaseBus.MetodoX()</code> para implementar la validación requerida. Build OK."]</p>`
   por:
   `<p>[2-3 líneas. Ej: "Se modificó <code>ClaseBus.MetodoX()</code> para implementar la validación requerida."]</p>`
   (elimina el string " Build OK." del ejemplo).
2. **Reescribir la sección "3. BUILD" (`:325-327`).** Reemplazar el `<p>` con el verde hardcodeado por:
   ```html
   <h2>3. BUILD</h2>
   <p>[Stacky anexa aquí el <strong>veredicto de build verificado por máquina</strong>. NO escribas "Build OK" a mano: el verde, la publicación y la transición de estado dependen del veredicto determinista de Stacky, no de este texto.]</p>
   <hr>
   ```
3. **Reescribir PASO 4 (`:197-199`).** Reemplazar por:
   ```
   ### PASO 4 — Compilar y verificar (VEREDICTO DE MÁQUINA)

   La verificación de build la produce Stacky, no vos. Tras implementar, dispará el
   veredicto determinista (server-side, sin LLM):

       POST http://localhost:5050/api/tickets/by-ado/{ADO_ID}/dev/build-verify

   Interpretá la respuesta `verdict`:
   - `gate_ok: true` (y `entry_kind: "sln"`) → build verificado. Continuá al PASO 5 con
     `target_ado_state = next_state_ok` del client-profile.
   - `gate_ok: false` → NO afirmes "Build OK". Reportá el bloqueante con `verdict.reason`
     (p.ej. `no_sln`, `toolchain_missing`, `build_failed`) y usá
     `target_ado_state = blocked_state` (o dejá el ticket en revisión). Iterá si `build_failed`
     es por tu cambio; si es `no_sln`/`toolchain_missing`, es un gap de entorno/config: reportalo.

   Aunque no dispares este endpoint, Stacky NO publicará "Build OK" ni avanzará el estado
   sin un veredicto de máquina válido (la ausencia de veredicto = no verificado).
   ```
4. **Nota en COMPILACIÓN (`:152-168`).** Agregar al final de la sección:
   `> Stacky resuelve la solución a compilar así: prefiere client_profile.build.online_solutions; si está vacío, escanea el workspace y toma los .sln encontrados. Un .csproj suelto NO cuenta como build verificable salvo que el perfil declare build.allow_csproj_entry: true.`
5. **Nota en target_ado_state (`:236-240`).** Agregar: `> En modo determinista, Stacky ignora el target_ado_state que mandes y decide next_state_ok vs blocked según el veredicto de build de máquina (Plan 210). No dependas de narrar "Build OK".`
6. Actualizar la firma final `_Developer cliente-agnóstico v2.1.1 — Stacky Agents._` (`:361`) → `v2.2.0`.

**Paridad 3 runtimes:** el prompt es el mismo para Codex/Claude/Copilot; los tres reciben la misma instrucción. Ninguno puede fabricar el veredicto (lo produce el endpoint). Fallback: si un runtime ignora PASO 4, el gate server-side (F4/F5) degrada igual.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_prompt.py`:** (lee el archivo del prompt como texto)
- `test_no_hardcoded_build_ok_seed`: el string `Build OK."` (con la comilla del ejemplo) YA NO está en `:301` — assert que la ocurrencia del seed original desapareció. (Buscar la línea del RESUMEN RÁPIDO y verificar que no contiene "Build OK".)
- `test_build_section_is_machine_authored`: la sección `3. BUILD` contiene "verificado por máquina" y NO contiene el `<span style="color:green"><strong>✓ Build OK` hardcodeado.
- `test_paso4_calls_verify_endpoint`: el texto contiene `dev/build-verify`.
- `test_version_bumped`: frontmatter contiene `version: "2.2.0"`.
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

> **GOTCHA (memoria `gotcha-plan-comment-matches-own-gate`):** este plan menciona literalmente `Build OK` en su prosa; los tests deben grepear el **archivo del prompt** (`Developer.agent.md`), NO este doc de plan. Escribí los asserts con la ruta del prompt explícita.

**Criterio BINARIO:** comando verde; el patrón del **span verde hardcodeado** desaparece: `grep -nE 'color:green[^>]*>\s*<strong>\s*.{0,3}Build OK' "Stacky Agents/backend/Stacky/agents/Developer.agent.md"` → **0 matches**. (OJO: un `grep "Build OK"` a secas NO da 0 — el texto que queda incluye la instrucción "NO escribas 'Build OK'", que es correcta y no es un claim verde. El gate cuenta SOLO el patrón del span verde.)

**Flag:** el prompt no chequea flag (el gate sí). **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F7 — Pane de evidencia en la UI (opcional, alto valor, default ON)

**Objetivo:** mostrar el veredicto de build al operador en el panel de salida, con color y razón. Valor: el operador ve de un vistazo si el build fue verificado.

**Archivos a crear/editar:**
- `Stacky Agents/frontend/src/components/devBuildModel.ts` — helpers PUROS: `verdictColor(v): 'green'|'red'|'gray'`, `verdictLabel(reason): string`, `verdictBadge(v): { text, color }`. Sin render, sin `style={{}}` inline (memoria `gotcha-ratchet-nuevo-archivo-cero-inline-style`).
- `Stacky Agents/frontend/src/components/devBuildModel.test.ts` — vitest por función.
- `Stacky Agents/frontend/src/components/OutputPanel.tsx` — leer `execution.metadata.build_verdict` (poblado en F4/F5 vía metadata) y renderizar un pane distinguible (patrón de los panes auxiliares que cuelgan de `execution.metadata`, `OutputPanel.tsx:140`). Solo para `agentType === "developer"` y si el veredicto existe.

> **Nota de metadata:** para que la UI reciba el veredicto, F4/F5 deben escribir un resumen en `execution.metadata["build_verdict"]` (`{gate_ok, reason, entry_kind, solution}`) al gatear/anotar. Agregar esa escritura de metadata en F4 (donde ya se tiene el `AgentExecution` en `session_scope`) es el sub-paso mínimo. Backward-compatible: sin la key, el pane no se renderiza.

**Casos borde:** sin `build_verdict` en metadata → pane no aparece (no rompe); `agentType != developer` → no aplica.

**Tests (TDD) — `devBuildModel.test.ts`:** un `it` por función (color/label/badge para `gate_ok true`, `no_sln`, `toolchain_missing`, `build_failed`). Correr: `npx vitest run src\components\devBuildModel.test.ts`.

**Criterio BINARIO:** comando verde; `tsc` del frontend sin errores nuevos (el gate real de UI, memoria `gotcha-rtl-jsdom-structural-gap`: no hay RTL; validar con `tsc` + modelo puro).

**Flag:** el pane depende de que la metadata exista (poblada solo con flag ON). **Runtime:** N/A (UI). **Operador:** ninguno; ve el pane solo.

---

## 5-bis. Orden de implementación (dependencias entre fases)

F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7. F1 no depende de F2; F4 y F5 dependen de F2 (leen el veredicto); F7 depende de F4/F5 (metadata). F6 es independiente pero se implementa tras F3 (el prompt cita el endpoint de F3). **Prerequisito externo:** el builder del Plan 201 (F5 del 201). Si aún no está mergeado, F2 degrada a `build_workshop_unavailable` y los tests de F2 monkeypatchean el builder — el plan es implementable y verde, pero el valor real (build verificado de verdad) se materializa cuando el 201 esté en `main`.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | El 201 no está mergeado → el gate degrada TODO a "no verificado" y bloquea a todos los developers. | `reason == "build_workshop_unavailable"` degrada a **review_state** (no "Blocked" duro); el operador puede avanzar a mano. La flag es toggleable: si molesta antes del 201, se apaga desde UI. KPI-5 (flag OFF = byte-idéntico) garantiza salida. |
| R2 | Toolchain .NET ausente en la máquina del operador → todos los builds `toolchain_missing`. | EXCEPCIÓN DURA #3: doctor del 201 + degradación a review; **nunca** auto-instala. El deliverable dice exactamente qué instalar. |
| R3 | Build lento (hasta 30 min) bloquea el request del endpoint. | El build ya está acotado (`_BUILD_TIMEOUT_SEC=1800` del 201) + `_VERIFY_POLL_TIMEOUT_SEC`. El endpoint corre dentro del run del agente (ya largo). Follow-up posible: modo async con polling desde el agente (fuera de scope). |
| R4 | La regex de neutralización del verde no matchea una variante que el LLM invente. | El gate de **estado** (F4) no depende del HTML: aunque el verde se cuele visualmente, el ticket NO avanza sin `gate_ok`. Además el bloque autoritativo de máquina se inserta siempre. Defensa en profundidad. |
| R5 | Falso negativo: hay `.sln` válido pero el scanner no lo encuentra (árbol raro). | `resolve_build_entry` prefiere `online_solutions` declarado (el operador lo puede fijar en el perfil); el scan es fallback. `truncated` del scanner del 201 avisa. |
| R6 | Colisión con Plan 208 (ambos tocan la transición de estado). | 208 decide *a qué* estado; 210 decide *si el developer puede avanzar*. 210 expone `gate_final_state` para que 208 lo llame. Documentado en "Planes relacionados". Sin colisión de símbolos. |
| R7 | Romper el publish si la anotación falla. | F5 envuelve la anotación en `try/except` total → se publica el original (G6). |

---

## 7. Fuera de scope (explícito)

- **NO** se implementa el builder ni la UI del Taller de Compilación (eso es Plan 201).
- **NO** se auto-compila fuera de un run del agente ni se auto-instala toolchain (G2/G7).
- **NO** se toca el flujo de otros agentes (technical/functional/QA): el gate es exclusivo de `agent_type == "developer"`.
- **NO** se implementa el inspector post-build ni el barrido de residuos (eso es Plan 211; este plan solo expone la seam `register_evidence_contributor`).
- **NO** se agrega RBAC ni multiusuario (G5).
- **NO** se modifica `harness_defaults.env` a mano (§4).

---

## 8. Glosario + DoD

**Glosario:**
- **`BuildVerdict`** — objeto tipado con el resultado de máquina del build (contrato §5, congelado por F2).
- **`gate_ok`** — booleano rector: `ok and entry_kind=="sln" and not blocking_findings`. Gobierna estado y verde.
- **Entrada canónica** — la(s) `.sln` a compilar: `online_solutions` declarado, o escaneadas; nunca un `.csproj` suelto salvo `allow_csproj_entry`.
- **Doctor** — remediación read-only del toolchain (del Plan 201); nunca instala.
- **Contribuidor de evidencia** — función que Plan 211 registra para sumar findings/HTML al bloque de build (seam de F5).

**Definition of Done (binario):**
1. Los 8 archivos de test (`test_plan210_flag`, `_resolve_entry`, `_verify_build`, `_api`, `_state_gate`, `_annotate`, `_prompt`, + `devBuildModel.test.ts`) → **verdes**, corridos por archivo con el venv del repo, y todos los `test_plan210_*.py` registrados en `HARNESS_TEST_FILES`.
2. `grep -n "gate_final_state\|annotate_build_evidence\|register_evidence_contributor" "Stacky Agents/backend/services/dev_build_verify.py"` → 3+ matches.
3. `grep -rn "dev_build_bp" "Stacky Agents/backend/api/__init__.py"` → 2 matches.
4. Con flag OFF: la suite existente de `stacky-status`/`_apply_task_state`/`ado_publisher` pasa **byte-idéntica** (KPI-5).
5. El prompt `Developer.agent.md` no contiene el patrón `color:green...Build OK` hardcodeado y sí contiene `dev/build-verify` (F6).
6. **Smoke E2E (manual, documentado como pendiente):** correr un developer real sobre un proyecto con `.sln` y toolchain presente → `build.verdict.json` con `gate_ok true`, ADO recibe "Build OK (verificado por máquina)" verde y transiciona a `next_state_ok`; repetir con un cambio que no compila → `gate_ok false`, ADO en rojo y ticket en revisión. (El smoke real depende del Plan 201 mergeado.)

**Trabajo del operador:** ninguno (opt-in default ON; degrada solo y con doctor si falta toolchain). Config toggleable desde Configuración → Arnés → DevOps.
