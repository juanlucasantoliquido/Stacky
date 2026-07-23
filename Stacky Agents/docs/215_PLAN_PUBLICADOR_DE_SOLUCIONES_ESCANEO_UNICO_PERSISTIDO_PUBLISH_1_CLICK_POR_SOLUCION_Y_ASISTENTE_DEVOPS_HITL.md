# Plan 215 — Publicador de Soluciones: escaneo único persistido, publish 1-click por solución y asistente DevOps HITL

> Estado: **PROPUESTO v1** (2026-07-23). Pipeline: **[este paso ✓]** proponer → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: StackyArchitectaUltraEficientCode (perfil normal, heredado de Fable 5).
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).
> Origen: pedido EXPLÍCITO del operador — "El publicador actual no me resulta cómodo. La idea es que la herramienta realice un escaneo inicial de todos los archivos .sln del proyecto, identifique cada solución y permita configurar su proceso de publicación de manera individual. Luego, desde una interfaz simple, debería ser posible seleccionar una solución y generar su publish con un solo botón. Además […] una opción asistida por un agente de DevOps […] cuando el proceso de publicación presente errores […]. El primer escaneo debería ejecutarse una única vez y guardar […] una lista con todas las soluciones detectadas y sus respectivas rutas. […] Idealmente, el escaneo inicial debería realizarse de forma determinística. Sin embargo, si ese mecanismo no logra identificar correctamente las soluciones, debería existir la posibilidad de ejecutar un escaneo de forma agéntica como alternativa."

---

## 0. Relación con los planes 201 / 210 / 211 (leer ANTES de implementar)

- **DEPENDE DURO del Plan 201** (`Stacky Agents/docs/201_PLAN_TALLER_DE_COMPILACION_DETECCION_SLN_BUILD_RELEASE_1CLICK_Y_ARTEFACTOS_DESCARGABLES.md`, CRITICADO v2 — APROBADO-CON-CAMBIOS, aún SIN implementar al escribir este plan). Este plan **REUSA sin reimplementar**:
  - `services/solution_scanner.py` (201 F1): `scan_solutions_ex`, `slugify_solution` y el contrato de catálogo (slug/sln_path/sln_name/friendly_name/projects). El "escaneo inicial determinístico" que pidió el operador **ES el scanner del 201** — este plan NO define un escaneo `.sln` paralelo.
  - `services/solution_store.py` (201 F2): `rescan_and_save`, `load_catalog`, `store_path` y el archivo `data/build_solutions.json` como **única fuente de verdad** de "soluciones detectadas y sus rutas". Así el Taller de Compilación (201) y el Publicador (215) ven exactamente el mismo catálogo.
  - `services/build_toolchain.py` (201 F3): `detect_toolchain()` + doctor. No se reimplementa detección de MSBuild/dotnet.
  - El patrón runner del `solution_builder.py` (201 F5): subprocess con **lista de args** (jamás `shell=True`), log buffer propio con shape `LogEvent` (SIN `log_streamer.close()` — FK), `_ts()` único, `_terminate_tree`, timeout 1800, ledger `.jsonl`, `*.summary.json`, `prune_old_*`. El publisher de F4 **espeja** ese patrón (mismos nombres de conceptos, archivo distinto).
  - El bridge al Plan 120 (201 F8): `deploy_store.upsert_app` para "registrar el artefacto publicado como DeployApp".
- **Extensiones ADITIVAS al 201 (permitidas, no modifican contratos existentes):**
  - `solution_scanner.py`: se AGREGA la función pública `scan_single_solution(sln_path, existing_slugs)` (F3). No se toca ninguna función existente.
  - `solution_store.py`: se AGREGAN `add_manual_solution(workspace_root, sln_path)` y `rescan_preserving_manual(workspace_root)` (F3). No se toca `rescan_and_save` ni el schema salvo una key opcional nueva por solución: `"origin": "scan"|"manual"` (ausente = `"scan"`; backward-compatible: ningún consumidor existente la lee).
- **Coordinación con Plan 210** (gate de build del Developer): 210 consume el builder del 201 para el flujo del **agente Developer**; 215 es una herramienta del **operador**. Cero archivos compartidos entre 210 y 215 salvo el 201 (que ninguno modifica en sus contratos). Sin colisión.
- **Coordinación con Plan 211** (inspector post-build): 211 inspecciona artefactos del gate del 210. 215 NO se engancha en `register_evidence_contributor` ni en `BuildVerdict`. Sin colisión.
- **NO TOCA:** la sección "Publicaciones" existente del Plan 88 (`frontend/src/components/devops/PublicationsSection.tsx`, `POST /api/devops/publications/materialize`, `api/devops.py:191-215`, `services/publication_spec.py`) — ese es el "publicador actual" incómodo (presets de catálogo de procesos → PipelineSpec YAML, pensado para pipelines, no para `.sln`). Se deja intacto y funcionando; este plan agrega una sección NUEVA. Tampoco toca `services/publish_ledger.py` (Plan 153 — ledger de publicaciones **a ADO**, dominio distinto pese al nombre) ni `deployment/Prepare-Publication.ps1` (publica Stacky mismo).
- **Regla de secuencia:** si al implementar 215 el 201 aún no está mergeado, **implementar primero 201 (F0-F5 como mínimo)**. Defensa adicional en runtime (paridad con 210 G7): los endpoints de 215 envuelven los imports del 201 y, si faltan, responden `200 {"error": "build_workshop_unavailable"}` y la UI muestra "Requiere el Taller de Compilación (Plan 201)" — degradación controlada, nunca crash (ver F5).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Agregar al dashboard DevOps una sección nueva **"Publicar Soluciones"** que: (a) al **primer uso** escanea **una única vez, determinísticamente y sin ningún paso manual** todos los `.sln` del workspace del proyecto activo (lazy: se dispara sola al abrir la sección si no hay catálogo persistido) y **guarda la lista de soluciones y rutas** (reusa `data/build_solutions.json` del Plan 201 — en usos siguientes NO se re-escanea); (b) permite **configurar el proceso de publicación de cada solución individualmente** (modo `dotnet publish` / `msbuild` + `.pubxml` / solo-build, proyecto objetivo, configuración, perfil de publicación detectado automáticamente); (c) publica la solución seleccionada con **un solo botón** (confirmación HITL con preview del comando exacto), dejando artefacto descargable + ledger; (d) ante errores, configuraciones faltantes o situaciones que exceden lo determinístico, ofrece **asistencia por el agente DevOps existente (Plan 90)** con un click: se arma un contexto enmascarado (log del fallo + config + doctor) y se abre una conversación HITL donde el agente diagnostica y propone — **jamás ejecuta ni cambia config sin confirmación del operador**; y (e) si el escaneo determinístico no encontró (todas) las soluciones, ofrece una **escalera de fallback**: escaneo profundo determinista → alta manual validada por ruta → **escaneo agéntico** (chat DevOps prellenado que localiza `.sln` y cuyas rutas se importan con validación determinista server-side).

**Gap que cierra.** Hoy "publicar" una solución de cliente es un proceso manual en Visual Studio (abrir, elegir perfil, publicar, ubicar salida). La sección "Publicaciones" del Plan 88 arma specs de pipeline desde presets de procesos — no publica `.sln`. El Plan 201 (aún sin implementar) compila Release pero **no publica** (no `dotnet publish`, no `.pubxml`, no config por solución persistida). Ninguna pieza une "escaneo persistido una única vez + config individual por solución + publish 1-click + asistencia agéntica ante fallos".

**KPI / impacto medible.**
- **KPI-1 — Primer uso sin pasos:** abrir la sección por primera vez dispara el escaneo solo; el operador NO clickea "Escanear" (0 pasos manuales para tener el catálogo).
- **KPI-2 — Usos siguientes sin re-scan:** con catálogo persistido, `GET /catalog` NO recorre el disco (verificable: el test lo prueba con un workspace inexistente y catálogo pre-sembrado).
- **KPI-3 — Publish en 2 clicks:** seleccionar solución → `Publicar` → confirmar. 0 caracteres tipeados en el camino feliz.
- **KPI-4 — Fallo a asistencia en 1 click:** un run `failed` muestra el botón "Asistir con agente DevOps"; un click crea la conversación con el contexto ya cargado (enmascarado).
- **KPI-5 — Paridad de runtimes:** núcleo (scan/config/publish/doctor) determinista, 3/3 idéntico; escalones agénticos con fallback explícito por runtime (§F6/F7).
- **KPI-6 — Cero regresión:** flag OFF → todo byte-idéntico al estado actual (sección ausente, endpoints 404); ningún test existente se rompe.

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia verificada 2026-07-23)

1. **El "publicador actual" es preset-based y no toca `.sln`.** `frontend/src/pages/DevOpsPage.tsx:104-110` registra la sección `publicaciones` (Plan 88) que llama `POST /api/devops/publications/materialize` (`api/devops.py:191-215`) → `build_publication_spec` (`services/publication_spec.py:79`): arma un spec de pipeline desde `client_profile.devops_publication_presets` + `process_catalog`. Correcto para procesos batch, **incómodo e inaplicable** para "publicá esta solución web con su perfil".
2. **El Plan 201 ya especifica (CRITICADO v2) el escaneo determinista y su persistencia** — exactamente lo que el operador pide para el paso 1: `scan_solutions_ex` (201 F1), `data/build_solutions.json` con merge de `tracked` (201 F2), doctor de toolchain (201 F3). Reusar, no duplicar (ver §0).
3. **El agente DevOps HITL ya existe y es conversacional.** `backend/agents/devops.py:4-30` (`DevOpsAgent`, `type="devops"`, regla R-HITL: "NUNCA ejecutes una acción que modifique estado sin […] la palabra CONFIRMO"); API `POST /api/devops/agent/conversations` (`api/devops_agent.py:59-152`) con `{project, message, runtime, model, effort}`, runtimes CLI `("claude_code_cli", "codex_cli")` (`devops_agent.py:14`) y degradación documentada a Copilot vía `open_chat` (`devops_agent.py:69-78`). El "agente de DevOps que interviene ante errores" NO se construye: se **prellena**.
4. **El enmascarado de secretos ya existe:** `services/secret_masking.py:20` `mask_token_values(text)` (Plan 195, ya lo importan 186/193). El contexto del assist lo usa tal cual.
5. **El registro declarativo de secciones DevOps hace la UI barata:** una entrada en `DEVOPS_SECTIONS` (`DevOpsPage.tsx:97+`) + componente; y `ctx.setActiveSection` existe (`DevOpsPage.tsx:237`) para saltar a la sección `agente` tras crear la conversación de asistencia.
6. **El bridge de despliegue ya existe:** `deploy_store.upsert_app` valida y persiste `DeployApp {kind:'folder', path}` (Plan 120), como documenta 201 F8 — el artefacto publicado se registra con un click.

**Conclusión:** trabajo aditivo: 1 flag, 3 servicios nuevos (perfil de publish, config store, publisher), 2 extensiones aditivas al store/scanner del 201, 1 blueprint, 1 sección UI, y cableado de contexto hacia el chat DevOps existente.

---

## 3. Principios y guardarraíles (NO negociables — codificados en cada fase)

- **G1 · Cero trabajo extra al operador.** Primer escaneo lazy/automático al abrir la sección (read-only, acotado — no requiere confirmación). Sin tipeo en el camino feliz. Config por solución = selects prellenados con defaults deterministas (`mode:"auto"` funciona sin tocar nada). Backward-compatible.
- **G2 · Human-in-the-loop innegociable.** `Publicar`, `Cancelar`, `Importar rutas` y `Registrar como app de despliegue` exigen `confirm:true` en el body (patrón `devops_deployments.py`). El agente DevOps **solo diagnostica y propone**; cualquier cambio de config lo aplica el operador desde la UI (o pegando el JSON propuesto en el editor, que valida server-side). Prohibida la autonomía proactiva: nada corre sin click.
- **G3 · Determinista-primero, agéntico como fallback.** Escaneo, config, resolución de modo, publish, doctor y clasificación de errores: Python determinista, sin LLM → idéntico 3/3. Los escalones agénticos (escaneo asistido F5-esc.3, asistencia F6) son opt-in por click y sus SALIDAS se validan determinísticamente antes de tocar estado (rutas importadas: `os.path.isfile` + extensión + `commonpath` dentro del workspace).
- **G4 · Paridad de 3 runtimes.** Núcleo idéntico 3/3. Escalones agénticos: `claude_code_cli`/`codex_cli` vía chat DevOps; **GitHub Copilot Pro** degrada a "Copiar contexto" (copyService) + flujo interactivo `open_chat` — el MISMO fallback que ya documenta `devops_agent.py:69-78`. Declarado por fase.
- **G5 · Mono-operador sin auth.** Cero RBAC. `current_user` informativo.
- **G6 · No degradar performance/seguridad/estabilidad/DX.** Escaneos read-only y acotados (topes de 201; deep-scan con presupuesto de tiempo duro). Publish produce carpetas nuevas (no destructivo, nunca escribe en el workspace del cliente). Descargas con guard `commonpath`. `extra_args` validados por allowlist (sin espacios ni metacaracteres). Retención con prune. Reuso total de lo existente.
- **G7 · EXCEPCIÓN DURA #3 (prerequisito no garantizado: MSBuild/.NET SDK).** Igual que 201 G7: la flag queda **default ON** (catálogo/config/UI son read-only y seguras) y el botón `Publicar` se auto-gatea con `detect_toolchain()`; sin toolchain → doctor + no-op (`status:"toolchain_missing"`), nunca crash, nunca auto-instala. Segundo prerequisito no garantizado: **el Plan 201 implementado** — si sus módulos no existen, los endpoints degradan a `build_workshop_unavailable` (F5), nunca crash. Citada en F1, F4, F5.
- **G8 · Config vía UI.** La flag `STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED` es toggleable desde **Configuración → Arnés → categoría DevOps**. La config por solución se edita SOLO en la sección (modal con el `Dialog` canónico del Plan 164). Cero env vars nuevas para el operador.

---

## 4. Flag del arnés (una sola, default ON) — cableado EXACTO en 5 lugares

**Flag nueva:** `STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED` · tipo `bool` · **default ON** · categoría `devops` · sin `requires`.

> **GOTCHA DURO (memoria "Receta flag DEVOPS default-ON = 5 lugares").** `FlagSpec` con `default=True` DEBE estar en `_CURATED_DEFAULTS_ON` o `test_default_known_only_for_curated` se pone rojo. El default EFECTIVO lo da `config.py`, leído SIEMPRE vía la **instancia** `config.config` (`getattr(_config.config, ...)`) — NUNCA `getattr(config, ...)` del módulo (memoria `gotcha-config-config-vs-modulo-tickets`). Toda flag nueva DEBE estar categorizada o `test_every_registry_flag_is_categorizado` rompe.

| # | Archivo | Qué agregar | Ancla |
|---|---------|-------------|-------|
| 1 | `Stacky Agents/backend/services/harness_flags.py` | `FlagSpec(key="STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED", type="bool", label="Publicador de Soluciones", description="Escanea una única vez los .sln del workspace, permite configurar el publish de cada solución y publicarla con un click; asistencia del agente DevOps ante fallos (el publish requiere toolchain .NET).", group="global", default=True)` en `FLAG_REGISTRY`. | `class FlagSpec` = `harness_flags.py:21`; `FLAG_REGISTRY` = `harness_flags.py:379` |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | `"STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED",` en la tupla `_CATEGORY_KEYS["devops"]`. | `_CATEGORY_KEYS` = `harness_flags.py:117`; tupla devops = `harness_flags.py:202` |
| 3 | `Stacky Agents/backend/tests/test_harness_flags.py` | `"STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED",` en `_CURATED_DEFAULTS_ON`. | `test_harness_flags.py:467` |
| 4 | `Stacky Agents/backend/config.py` | `STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED: bool = os.getenv("STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED", "true").lower() == "true"` — espejo exacto de `STACKY_DEVOPS_PUBLICATIONS_ENABLED` (`config.py:1239-1241`). | `config.py:1239` |
| 5 | `Stacky Agents/backend/api/devops.py` | En `_health_payload()`: `"solution_publisher_enabled": bool(getattr(cfg, "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED", False)),`. | patrón `publications_enabled` = `devops.py:42` |

> **NO hand-editar** `Stacky Agents/backend/harness_defaults.env` (lo genera `deployment/export_harness_defaults.py`). **NO** hay `requires=` → NO tocar `_REQUIRES_MAP_FROZEN` ni bounds-map. La key #5 aparece también en `/devops/bootstrap` (dict compartido) — intencional, igual que 201 C10: NO "arreglarlo".
> La flag NO quema tokens ociosa: gatea endpoints y una sección; nada corre en background (cumple la directiva flags-ON salvo idle-tokens).

---

## 5. Arquitectura objetivo y modelo de datos

```
BACKEND (Stacky Agents/backend/)
  services/publish_profile_scanner.py   (F1) PURO — descubre .pubxml por proyecto + sdk_style + resolve_publish_plan
  services/publish_config_store.py      (F2) persistencia idempotente de la config de publish por (workspace, slug)
  services/solution_scanner.py          (F3, ADITIVO 201) + scan_single_solution(sln_path, existing_slugs)
  services/solution_store.py            (F3, ADITIVO 201) + add_manual_solution / rescan_preserving_manual
  services/solution_deep_scan.py        (F3) PURO — deep_scan_sln_paths con presupuesto de tiempo
  services/solution_publisher.py        (F4) runner de publish (espejo del patrón solution_builder del 201)
  api/devops_solution_publisher.py      (F5/F6) blueprint /devops/solution-publisher (catalog, rescan, config,
                                        import, deep-scan, run, status, cancel, download, runs, assist-context)

FRONTEND (Stacky Agents/frontend/src/)
  components/devops/solutionPublisherModel.ts        (F7) helpers PUROS testeables
  components/devops/solutionPublisherModel.test.ts   (F7) vitest del modelo puro
  components/devops/SolutionPublisherSection.tsx     (F7) UI de la sección
  pages/DevOpsPage.tsx                               (F0) +1 entrada en DEVOPS_SECTIONS
  api/endpoints.ts                                   (F7) +objeto DevOpsSolutionPublisher

DATOS (data_dir() = Stacky Agents/backend/data/ en dev)
  data/build_solutions.json                    catálogo de soluciones — DEL PLAN 201, fuente única (NO se crea otro)
  data/publish_configs.json                    config de publish por (workspace, slug) (F2)
  data/solution_publish_artifacts/<slug>/<ts>/ staging del publish (F4); <ts> único vía _ts() (patrón 201 C5)
  data/solution_publish_runs.jsonl             ledger append-only de publishes (F4)
```

### 5.1 Dónde vive la "lista de soluciones detectadas y sus rutas" (pedido explícito del operador)

En **`data/build_solutions.json`** (contrato del 201 F2, keyed por `workspace_root` absoluto — es decir, **por proyecto**). Este plan NO crea un catálogo paralelo: un solo escaneo sirve al Taller de Compilación (201) y al Publicador (215). El "primer escaneo una única vez" se cumple porque `GET /catalog` (F5) solo dispara `rescan_preserving_manual` cuando `load_catalog(ws)["scanned_at"] is None`; con catálogo persistido, lee el JSON y NO toca el disco del workspace. Cambio aditivo al schema: cada solución puede llevar `"origin": "scan"|"manual"` (ausente = `"scan"`).

### 5.2 Contrato de datos de `data/publish_configs.json` (schema NUEVO, congelado por F2)

```json
{
  "<workspace_root_absoluto>": {
    "<slug>": {
      "mode": "auto",
      "configuration": "Release",
      "project_csproj": null,
      "publish_profile": null,
      "extra_args": [],
      "register_as_deploy_app": false,
      "updated_at": "2026-07-23T12:00:00Z"
    }
  }
}
```

- `mode` ∈ `{"auto","dotnet_publish","msbuild_pubxml","build_only"}`. `"auto"` = el modo efectivo lo decide `resolve_publish_plan` (F1) determinísticamente en cada publish (así soluciones nuevas funcionan sin configurar nada — G1).
- `configuration`: string, default `"Release"`; validado contra `^[A-Za-z0-9._\-]{1,40}$`.
- `project_csproj`: ruta absoluta del proyecto objetivo dentro de la solución, o `null` (= auto: primer proyecto `type=="web"`, si no primer `type ∈ {console,service}`, si no `null` → build de la `.sln` completa).
- `publish_profile`: nombre (sin extensión) de un `.pubxml` detectado por F1, o `null`.
- `extra_args`: lista de strings; **validación dura** (G6): máx 8 items, cada uno matchea `^[A-Za-z0-9/:=._,()\\\-]{1,120}$` (sin espacios, sin `;|&<>"'`). Se anexan al final del argv (que es SIEMPRE lista → sin inyección de shell).
- `register_as_deploy_app`: bool; si `true`, al terminar `success` la UI ofrece (con confirm) registrar el staging como `DeployApp` (no es automático — G2).
- Falta la entrada de un slug → config **default efectiva** = el bloque de arriba con `updated_at: null` (el store la sintetiza; no hace falta escribir nada para publicar — G1).
- Slugs que desaparecen del catálogo NO se borran de este archivo (la config es barata y sobrevive a un re-scan que recupere la solución); la UI simplemente no los muestra.

### 5.3 Detección de `.sln` borrados/movidos + botón "Re-escanear"

- `GET /catalog` (F5) computa **en cada lectura** `missing: not os.path.exists(sln_path)` por solución (campo calculado, NO persistido). La UI muestra badge "no encontrado" + sugerencia "Re-escanear".
- Botón **Re-escanear** (manual, siempre visible) → `POST /rescan` → `rescan_preserving_manual(ws)` (F3): corre el scanner del 201, preserva `tracked` y las entradas `origin:"manual"` cuyo archivo sigue existiendo (aunque el walk acotado no las haya visto), y elimina las scaneadas cuyo `.sln` desapareció. Es un click explícito del operador; no requiere `confirm` (read-only sobre el workspace, idempotente sobre el catálogo).

---

## 6. Fases

> Convención de tests: **backend** = pytest **por archivo** con el venv del backend; **frontend** = vitest **por archivo** (memoria `gotcha-vitest-test-order-pollution-frontend`).
> **Comando backend** (desde `Stacky Agents/backend`): `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q` (si `.venv` no existe, `venv\Scripts\python.exe`; ambos py3.13).
> **Comando frontend** (desde `Stacky Agents/frontend`): `npx vitest run src\components\devops\<archivo>.test.ts`.
> **Registrar** CADA `test_*.py` nuevo en `Stacky Agents/backend/scripts/run_harness_tests.sh` array `HARNESS_TEST_FILES` (`run_harness_tests.sh:20`) o el meta-ratchet se pone rojo.
> **Tests de flag OFF/ON:** monkeypatchear la **instancia** — `monkeypatch.setattr(_config.config, "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED", False)`; PROHIBIDO `importlib.reload(config)` (memoria `gotcha-config-reload-harness-flags-contamina`).

---

### F0 — Flag + esqueleto de sección (gate primero)

**Objetivo (1 frase):** dejar la flag cableada en los 5 lugares (§4) y la sección "Publicar Soluciones" visible con placeholder. Valor: de-riesga flags/health/sección antes de la lógica.

**Archivos a editar/crear:**
- Los 5 de §4.
- `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — agregar al final del array `DEVOPS_SECTIONS` (después de la entrada `despliegues`, y después de `taller-compilacion` si el 201 ya la agregó):

```tsx
// Plan 215 — Publicador de Soluciones (scan único persistido + publish 1-click + asistente DevOps)
{
  id: 'publicador-soluciones',
  label: 'Publicar Soluciones',
  icon: '🚀',
  healthKey: 'solution_publisher_enabled',
  gateFlagKey: 'STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED',
  gateMessage: 'La sección Publicar Soluciones necesita la flag STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED (Configuración → Arnés, categoría DevOps).',
  render: (ctx) => <SolutionPublisherSection ctx={ctx} />,
},
```
- Import junto a los demás: `import { SolutionPublisherSection } from '../components/devops/SolutionPublisherSection';`
- Placeholder `Stacky Agents/frontend/src/components/devops/SolutionPublisherSection.tsx` (cero `style={{}}` inline — memoria `gotcha-ratchet-nuevo-archivo-cero-inline-style`):

```tsx
import React from 'react';
import type { DevOpsSectionContext } from '../../pages/DevOpsPage';
export const SolutionPublisherSection: React.FC<{ ctx: DevOpsSectionContext }> = () => {
  return <div>Publicador de Soluciones (Plan 215) — próximamente</div>;
};
```

**Nombres exactos:** flag `STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED`; health key `solution_publisher_enabled`; section id `publicador-soluciones`; componente `SolutionPublisherSection`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan215_flag.py`:**
- `test_flag_registered_and_curated`: la key está en `FLAG_REGISTRY`, en `_CATEGORY_KEYS["devops"]` y en `_CURATED_DEFAULTS_ON`.
- `test_health_exposes_solution_publisher_enabled`: `/api/devops/health` incluye `solution_publisher_enabled` (molde `test_plan120_api.py`).
- Registrar en `HARNESS_TEST_FILES`.
- Frontend: `Stacky Agents/frontend/src/pages/__tests__/SolutionPublisherSection.test.ts`: `DEVOPS_SECTIONS` contiene `{ id:'publicador-soluciones', gateFlagKey:'STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED' }` (molde `RemoteConsoleSection.test.ts:7-11`).

**Criterio BINARIO:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan215_flag.py tests\test_harness_flags.py -q` verde; `npx vitest run src\pages\__tests__\SolutionPublisherSection.test.ts` verde; `grep -rn "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED" "Stacky Agents/backend/config.py"` → 1+ match.

**Flag:** la propia (default ON, sin excepción — read-only). **Runtimes:** idéntico 3/3. **Trabajo del operador:** ninguno.

---

### F1 — Descubrimiento de perfiles de publish + plan determinista (`publish_profile_scanner.py`)

**Objetivo:** módulo PURO que descubre los `.pubxml` de cada proyecto, detecta si el proyecto es SDK-style y resuelve el **plan de publish efectivo** de una solución. Valor: "configurar el publish individualmente" arranca prellenado y `mode:"auto"` funciona sin configurar nada.

**Archivo a crear:** `Stacky Agents/backend/services/publish_profile_scanner.py`.

**API pública (nombres exactos):**
```python
def scan_publish_profiles(projects: list[dict]) -> dict
# projects = lista del catálogo 201 ({"name","csproj_path","type","target_framework"})
# → { "<csproj_path>": [ {"name": "Prod", "path": "<abs .pubxml>",
#                          "method": "FileSystem"|"MSDeploy"|"Package"|"FTP"|"unknown",
#                          "publish_url": str } ] }
def detect_sdk_style(csproj_path: str) -> bool
def resolve_publish_plan(solution: dict, cfg: dict, toolchain: dict) -> dict
# → {"mode_effective": "dotnet_publish"|"msbuild_pubxml"|"build_only",
#    "supported": bool, "reason": str, "target": str, "argv_tail": list[str]}
```

**Constantes de módulo:**
```python
_PUBXML_SUBDIR = os.path.join("Properties", "PublishProfiles")
_PUBXML_HEAD_BYTES = 32768
_METHOD_RE = re.compile(r"<webpublishmethod[^>]*>([^<]+)</webpublishmethod", re.I)
_PUBURL_RE = re.compile(r"<publishurl[^>]*>([^<]+)</publishurl", re.I)
_SDK_ATTR_RE = re.compile(r"<project\s[^>]*\bsdk\s*=", re.I)
```

**Pseudocódigo:**
```python
def scan_publish_profiles(projects):
    out = {}
    for p in projects or []:
        csproj = p.get("csproj_path") or ""
        prof_dir = os.path.join(os.path.dirname(csproj), _PUBXML_SUBDIR)
        entries = []
        try:
            names = sorted(os.listdir(prof_dir))
        except OSError:
            names = []
        for fname in names:
            if not fname.lower().endswith(".pubxml"):
                continue
            path = os.path.join(prof_dir, fname)
            try:
                with open(path, "rb") as fh:
                    head = fh.read(_PUBXML_HEAD_BYTES).decode("utf-8", errors="replace")
            except OSError:
                continue
            m = _METHOD_RE.search(head)
            method_raw = (m.group(1).strip() if m else "")
            method = method_raw if method_raw in ("FileSystem", "MSDeploy", "Package", "FTP") else ("unknown" if not method_raw else method_raw)
            u = _PUBURL_RE.search(head)
            entries.append({"name": os.path.splitext(fname)[0], "path": path,
                            "method": method, "publish_url": (u.group(1).strip() if u else "")})
        if entries:
            out[csproj] = entries
    return out

def detect_sdk_style(csproj_path):
    try:
        with open(csproj_path, "rb") as fh:
            head = fh.read(_PUBXML_HEAD_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return False
    return bool(_SDK_ATTR_RE.search(head))
```

**`resolve_publish_plan` — reglas CONGELADAS (orden estricto; determinista):**
```python
def resolve_publish_plan(solution, cfg, toolchain):
    # 1) proyecto objetivo
    target_csproj = cfg.get("project_csproj")
    projects = solution.get("projects", [])
    if not target_csproj:
        target_csproj = next((p["csproj_path"] for p in projects if p.get("type") == "web"), None) \
            or next((p["csproj_path"] for p in projects if p.get("type") in ("console", "service")), None)
    mode = cfg.get("mode") or "auto"
    profiles = scan_publish_profiles(projects)
    # 2) modo explícito: validar requisitos
    if mode == "build_only" or (mode == "auto" and target_csproj is None):
        return _plan_build_only(solution, cfg, toolchain)      # target = sln_path
    if mode == "dotnet_publish" or (mode == "auto" and detect_sdk_style(target_csproj)):
        if not toolchain.get("dotnet_path") and toolchain.get("builder") != "dotnet":
            return {"mode_effective": "dotnet_publish", "supported": False,
                    "reason": "requiere_dotnet_sdk", "target": target_csproj, "argv_tail": []}
        return {"mode_effective": "dotnet_publish", "supported": True, "reason": "",
                "target": target_csproj,
                "argv_tail": ["publish", target_csproj, "-c", cfg.get("configuration") or "Release", "--nologo"]}
    # 3) clásico (.NET Framework): pubxml FileSystem o degradar
    profs = profiles.get(target_csproj, [])
    chosen = None
    if cfg.get("publish_profile"):
        chosen = next((e for e in profs if e["name"] == cfg["publish_profile"]), None)
        if chosen is None:
            return {"mode_effective": "msbuild_pubxml", "supported": False,
                    "reason": "pubxml_no_encontrado", "target": target_csproj, "argv_tail": []}
    else:
        chosen = next((e for e in profs if e["method"] == "FileSystem"), None)
    if mode == "msbuild_pubxml" or (mode == "auto" and chosen is not None):
        if chosen is None:
            return {"mode_effective": "msbuild_pubxml", "supported": False,
                    "reason": "sin_pubxml_filesystem", "target": target_csproj, "argv_tail": []}
        if chosen["method"] != "FileSystem":
            return {"mode_effective": "msbuild_pubxml", "supported": False,
                    "reason": "pubxml_remoto_no_soportado", "target": target_csproj, "argv_tail": []}
        if not toolchain.get("msbuild_path"):
            return {"mode_effective": "msbuild_pubxml", "supported": False,
                    "reason": "requiere_msbuild", "target": target_csproj, "argv_tail": []}
        return {"mode_effective": "msbuild_pubxml", "supported": True, "reason": "",
                "target": target_csproj,
                "argv_tail": [target_csproj, "/p:DeployOnBuild=true",
                              "/p:PublishProfile=" + chosen["name"],
                              "/p:Configuration=" + (cfg.get("configuration") or "Release"), "/nologo"]}
    # 4) auto sin pubxml y no-SDK → build_only
    return _plan_build_only(solution, cfg, toolchain)

def _plan_build_only(solution, cfg, toolchain):
    # espejo EXACTO del contrato de comando del 201 F5 (build de la .sln completa)
    return {"mode_effective": "build_only", "supported": toolchain.get("available", False),
            "reason": "" if toolchain.get("available") else "toolchain_missing",
            "target": solution.get("sln_path") or "", "argv_tail": []}
```
> El argv COMPLETO (con ejecutable, `-o`/`/p:publishUrl=` staging y `extra_args`) lo arma el runner en F4 — `argv_tail` es la parte determinista previewable. NUNCA hay `shell=True` en ningún punto.

**Casos borde (cubrir en tests):** proyecto sin carpeta `Properties/PublishProfiles` → sin entrada; `.pubxml` ilegible → se salta; `publish_profile` configurado que no existe → `supported:false, reason:"pubxml_no_encontrado"`; pubxml `MSDeploy` → `supported:false, reason:"pubxml_remoto_no_soportado"` (publicar remoto directo es del Plan 120, fuera de scope); solución sin proyectos → `build_only`; toolchain sin dotnet con modo dotnet → `supported:false, reason:"requiere_dotnet_sdk"`. Ninguna función lanza jamás (OSError → degradar).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan215_publish_profile_scanner.py`:**
- `test_scan_profiles_finds_pubxml_and_method` (fixture: escribir `Properties/PublishProfiles/Prod.pubxml` con `<WebPublishMethod>FileSystem</WebPublishMethod><publishUrl>C:\out</publishUrl>` bajo un csproj de `tmp_path`)
- `test_scan_profiles_missing_dir_returns_empty`
- `test_detect_sdk_style_true_and_false` (`<Project Sdk="Microsoft.NET.Sdk">` → True; `<Project ToolsVersion="15.0" ...>` → False)
- `test_resolve_auto_sdk_web_is_dotnet_publish`
- `test_resolve_auto_classic_with_filesystem_pubxml_is_msbuild_pubxml`
- `test_resolve_auto_no_target_project_is_build_only`
- `test_resolve_msdeploy_pubxml_unsupported`
- `test_resolve_configured_pubxml_missing_reports_reason`
- `test_resolve_never_raises_on_bad_paths`
- Registrar en `HARNESS_TEST_FILES`. Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan215_publish_profile_scanner.py -q`

**Criterio BINARIO:** comando verde; `grep -n "shell=True\|import requests\|copilot\|llm" "Stacky Agents/backend/services/publish_profile_scanner.py"` → 0 matches.

**Flag:** gateada aguas arriba por el endpoint (F5). **Runtimes:** idéntico 3/3 (PURO). **G7:** los `reason` de toolchain hacen la degradación. **Trabajo del operador:** ninguno.

---

### F2 — Store de config de publish por solución (`publish_config_store.py`)

**Objetivo:** persistir/leer la config individual por `(workspace_root, slug)` con defaults sintetizados y validación dura. Valor: "configurar su proceso de publicación de manera individual" con cero config obligatoria.

**Archivo a crear:** `Stacky Agents/backend/services/publish_config_store.py`.

**API pública (nombres exactos):**
```python
def store_path() -> Path                                   # data_dir()/"publish_configs.json"
def default_config() -> dict                                # el bloque de §5.2 con updated_at=None
def load_config(workspace_root: str, slug: str) -> dict     # guardada o default sintetizada (SIEMPRE dict completo)
def save_config(workspace_root: str, slug: str, cfg: dict) -> dict   # valida, mergea sobre default, persiste, devuelve
def validate_config(cfg: dict) -> list[str]                 # lista de errores; [] = válida
```

**Reglas:**
- Mismo patrón del `solution_store` 201 F2: `from runtime_paths import data_dir`, `threading.Lock()` de módulo, escritura atómica `json.dumps(..., indent=2, ensure_ascii=False)`, JSON corrupto → `{}` con `logger.warning`.
- `validate_config` (bodies exactos, sin inferencia):
```python
_MODES = ("auto", "dotnet_publish", "msbuild_pubxml", "build_only")
_CONFIGURATION_RE = re.compile(r"^[A-Za-z0-9._\-]{1,40}$")
_EXTRA_ARG_RE = re.compile(r"^[A-Za-z0-9/:=._,()\\\-]{1,120}$")
_MAX_EXTRA_ARGS = 8

def validate_config(cfg):
    errors = []
    if cfg.get("mode") not in _MODES:
        errors.append("mode inválido")
    if not _CONFIGURATION_RE.match(str(cfg.get("configuration") or "")):
        errors.append("configuration inválida")
    pc = cfg.get("project_csproj")
    if pc is not None and (not isinstance(pc, str) or not pc.lower().endswith((".csproj", ".vbproj"))):
        errors.append("project_csproj debe ser .csproj/.vbproj o null")
    pp = cfg.get("publish_profile")
    if pp is not None and (not isinstance(pp, str) or not re.match(r"^[A-Za-z0-9._\- ]{1,80}$", pp)):
        errors.append("publish_profile inválido")
    extra = cfg.get("extra_args")
    if not isinstance(extra, list) or len(extra) > _MAX_EXTRA_ARGS \
       or any(not isinstance(a, str) or not _EXTRA_ARG_RE.match(a) for a in extra):
        errors.append("extra_args inválidos (máx 8; sin espacios ni ;|&<>\"')")
    if not isinstance(cfg.get("register_as_deploy_app"), bool):
        errors.append("register_as_deploy_app debe ser bool")
    return errors
```
- `save_config` primero completa el input con `default_config()` (merge por key faltante), valida, y si `validate_config` devuelve errores lanza `ValueError("; ".join(errors))` (el endpoint la traduce a 400). Sella `updated_at` con ISO UTC.

**Casos borde:** slug nunca configurado → `load_config` devuelve default (nunca `None`, nunca lanza); archivo inexistente → `{}`; workspace vacío → default; `save_config` con extra_args `["-p:X=Y; rm -rf /"]` → `ValueError` (espacio y `;` prohibidos).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan215_publish_config_store.py`:** (monkeypatch `store_path` → `tmp_path/"publish_configs.json"`)
- `test_load_missing_returns_default`
- `test_save_and_reload_roundtrip`
- `test_save_merges_partial_input_over_default`
- `test_invalid_mode_rejected`
- `test_extra_args_with_space_or_semicolon_rejected`
- `test_extra_args_valid_msbuild_property_accepted` (`["/p:Platform=AnyCPU"]` pasa)
- `test_corrupt_json_degrades_to_empty`
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; round-trip byte-estable salvo `updated_at`.

**Flag/Runtimes/Operador:** como F1.

---

### F3 — Extensiones ADITIVAS de catálogo: alta manual, re-scan preservador y deep-scan

**Objetivo:** cubrir "el determinístico no encontró la solución": alta manual validada, re-scan que no pierde altas manuales, y escaneo profundo con presupuesto de tiempo. Valor: escalera de fallback determinista completa (el escalón agéntico la usa en F6).

**Archivos a editar/crear:**

1. `Stacky Agents/backend/services/solution_scanner.py` (**ADITIVO** — solo AGREGAR al final, no tocar lo existente):
```python
def scan_single_solution(sln_path, existing_slugs=None):
    # Construye la entrada de catálogo de UNA .sln concreta (para alta manual).
    # Devuelve dict con el MISMO shape del catálogo 201, o None si la ruta no es una .sln legible.
    if not sln_path or not os.path.isfile(sln_path) or not sln_path.lower().endswith(".sln"):
        return None
    name = os.path.splitext(os.path.basename(sln_path))[0]
    seen = set(existing_slugs or [])
    slug = _dedupe(slugify_solution(name), seen)
    return {"slug": slug, "sln_path": os.path.normpath(sln_path), "sln_name": name,
            "friendly_name": _title_case(name), "projects": _parse_sln_projects(sln_path)}
```

2. `Stacky Agents/backend/services/solution_store.py` (**ADITIVO** — usa el `_LOCK`/`_load_doc`/`_save_doc` existentes):
```python
def add_manual_solution(workspace_root, sln_path):
    # Valida y agrega una solución al catálogo con origin="manual", tracked=_is_deployable.
    # Devuelve el bloque del workspace actualizado, o lanza ValueError con razón legible.
    from solution_scanner import scan_single_solution
    root = os.path.normpath(workspace_root or "")
    target = os.path.normpath(os.path.abspath(sln_path or ""))
    if not root or os.path.commonpath([root, target]) != root:      # dentro del workspace, siempre
        raise ValueError("La ruta debe estar dentro del workspace del proyecto activo")
    with _LOCK:
        doc = _load_doc()
        block = doc.get(root) or {"scanned_at": None, "truncated": False, "solutions": []}
        existing = block["solutions"]
        if any(os.path.normcase(s.get("sln_path", "")) == os.path.normcase(target) for s in existing):
            return block                                             # idempotente: ya está
        entry = scan_single_solution(target, existing_slugs=[s["slug"] for s in existing])
        if entry is None:
            raise ValueError("La ruta no es un archivo .sln legible")
        entry["tracked"] = _is_deployable(entry)
        entry["origin"] = "manual"
        existing.append(entry)
        existing.sort(key=lambda s: s.get("sln_path", ""))
        doc[root] = block
        _save_doc(doc)
        return block

def rescan_preserving_manual(workspace_root):
    # rescan_and_save del 201 + re-anexar las entradas manuales previas cuyo .sln sigue existiendo
    # y que el walk acotado no reencontró. Devuelve el bloque final.
    with _LOCK:
        prev = (_load_doc().get(workspace_root) or {}).get("solutions", [])
    manual_prev = [s for s in prev if s.get("origin") == "manual" and os.path.exists(s.get("sln_path", ""))]
    block = rescan_and_save(workspace_root)                          # 201 F2, intacto
    found_paths = {os.path.normcase(s["sln_path"]) for s in block["solutions"]}
    for m in manual_prev:
        if os.path.normcase(m["sln_path"]) not in found_paths:
            block = add_manual_solution(workspace_root, m["sln_path"])
    return block
```
> NOTA de preservación: `rescan_preserving_manual` re-agrega por RUTA; el `tracked` de una manual re-agregada vuelve al default `_is_deployable`. Documentado y aceptable (caso raro: manual fuera del alcance del walk + re-scan). Si la manual SÍ fue encontrada por el walk, el merge normal del 201 preserva su `tracked` por slug.

3. `Stacky Agents/backend/services/solution_deep_scan.py` (**NUEVO, PURO**):
```python
_DEEP_MAX_DEPTH = 16
_DEEP_IGNORE_DIRS = ("node_modules", ".git", "__pycache__", ".vs", "packages")  # NO ignora bin/obj: una .sln nunca vive ahí, pero venv/dist de repos mixtos sí pueden esconder carpetas hondas — mantener lista corta a propósito
_DEEP_TIME_BUDGET_SEC = 45

def deep_scan_sln_paths(workspace_root, time_budget_sec=_DEEP_TIME_BUDGET_SEC):
    # Recorre SOLO buscando nombres *.sln (barato: no parsea proyectos). Corta por presupuesto de tiempo.
    # → {"paths": [rutas absolutas ordenadas], "timed_out": bool}
    if not workspace_root or not os.path.isdir(workspace_root):
        return {"paths": [], "timed_out": False}
    root = os.path.normpath(workspace_root)
    deadline = time.monotonic() + max(1, int(time_budget_sec))
    paths, timed_out = [], False
    for dirpath, dirnames, filenames in os.walk(root):
        if time.monotonic() > deadline:
            timed_out = True
            break
        depth = dirpath[len(root):].count(os.sep)
        if depth >= _DEEP_MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in _DEEP_IGNORE_DIRS]
        for fname in filenames:
            if fname.lower().endswith(".sln"):
                paths.append(os.path.join(dirpath, fname))
    return {"paths": sorted(paths), "timed_out": timed_out}
```

**Casos borde:** alta manual de ruta fuera del workspace → `ValueError` (commonpath); alta duplicada → no-op idempotente; alta de `.txt` → `ValueError`; deep-scan de workspace inexistente → vacío sin crash; presupuesto agotado → `timed_out:true` con parciales.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan215_catalog_ops.py`:** (monkeypatch `solution_store.store_path` → tmp; fixtures `.sln` LITERALES del 201 F1 C11 — copiarlas tal cual de `201_PLAN_...md:395-411`)
- `test_scan_single_solution_builds_entry`
- `test_scan_single_rejects_non_sln_and_missing`
- `test_add_manual_inside_workspace_persists_with_origin_manual`
- `test_add_manual_outside_workspace_rejected`
- `test_add_manual_duplicate_is_noop`
- `test_rescan_preserving_manual_keeps_manual_beyond_walk` (manual con `.sln` real en tmp; monkeypatch `solution_store.scan_solutions_ex` para que NO la devuelva → tras rescan sigue en el catálogo con `origin:"manual"`)
- `test_rescan_drops_manual_whose_file_disappeared`
- `test_deep_scan_finds_sln_and_respects_budget` (monkeypatch `solution_deep_scan._DEEP_TIME_BUDGET_SEC`… no: pasar `time_budget_sec=0` → `timed_out` True con walk cortado en la primera iteración; y caso normal con budget default → encuentra la fixture)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "def scan_single_solution" "Stacky Agents/backend/services/solution_scanner.py"` → 1 match; `grep -n "def add_manual_solution\|def rescan_preserving_manual" "Stacky Agents/backend/services/solution_store.py"` → 2 matches.

**Flag/Runtimes:** idéntico 3/3 (determinista). **Operador:** ninguno (son primitivas; la UI las expone en F7).

---

### F4 — Runner de publish (`solution_publisher.py`)

**Objetivo:** ejecutar el publish de UNA solución según su plan efectivo, con log vivo, timeout, cancelación, staging descargable, summary y ledger. Valor: el botón único "Publicar".

**Archivo a crear:** `Stacky Agents/backend/services/solution_publisher.py`.

**API pública (nombres exactos):**
```python
def start_publish(slug: str, workspace_root: str) -> str       # run_id (uuid4 hex); lanza thread daemon; NO bloquea
def get_status(run_id: str) -> dict | None
def cancel(run_id: str) -> bool
def artifact_zip_path(run_id: str) -> Path | None              # resuelto de registro en memoria o ledger (patrón 201)
def list_runs(workspace_root: str, slug: str | None = None, limit: int = 20) -> list[dict]   # lee el ledger, más nuevos primero
```

**Estado y almacenamiento (espejo del 201 F5 — mismos conceptos, archivos propios):**
```python
_LOCK = threading.Lock()
_RUNS: dict[str, dict] = {}   # run_id -> {status, slug, mode_effective, argv, base_dir, zip_path, log:[...], started_at, finished_at, error, _proc, _cancel}
_PUBLISH_TIMEOUT_SEC = 1800
_MAX_RETAINED_RUNS = 10
```
- `status` ∈ `{"running","success","failed","cancelled","toolchain_missing","unsupported"}`.
- Log = lista `{"ts","level","message"}` (shape `log_streamer.LogEvent.to_dict`, `log_streamer.py:31-43`), buffer PROPIO — **PROHIBIDO `log_streamer.close()`** (misma razón FK que 201 F5: un publish no es un `AgentExecution`). Volcado final a `<base_dir>/publish.log`.
- Staging: `base_dir = data_dir()/"solution_publish_artifacts"/<slug>/<ts>/` con `<ts> = _ts()` (copiar el body de `_ts()` del 201 F5 C5: `strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]`). Bits en `base_dir/out/`.
- Ledger append-only `data/solution_publish_runs.jsonl`: una línea al terminar con `{"run_id","slug","mode_effective","status","returncode","zip_path","base_dir","workspace_root","finished_at","duration_sec"}`. (Nombre distinto de `publish_ledger` del Plan 153 — dominio ADO, no confundir.)
- `publish.summary.json` en `base_dir` al terminar (siempre, aun failed): `{"run_id","slug","mode_effective","argv","status","returncode","started_at","finished_at","duration_sec","staging_dir","zip_path","toolchain":{"builder","version"},"files":N,"bytes":N}`.
- Retención: `prune_old_publish_runs(scope_dir)` — copiar el body de `prune_old_builds` del 201 F5 (ADICIÓN 1) con `_MAX_RETAINED_RUNS`.

**Construcción del argv (SIEMPRE lista; NUNCA `shell=True`):**
```python
def _build_argv(plan, cfg, toolchain, staging_out):
    extra = list(cfg.get("extra_args") or [])
    if plan["mode_effective"] == "dotnet_publish":
        return [toolchain["dotnet_path"]] + plan["argv_tail"] + ["-o", staging_out] + extra
    if plan["mode_effective"] == "msbuild_pubxml":
        return [toolchain["msbuild_path"]] + plan["argv_tail"] + ["/p:publishUrl=" + staging_out + os.sep] + extra
    # build_only — espejo EXACTO de los comandos del 201 F5:
    if toolchain.get("builder") == "dotnet":
        return [toolchain["dotnet_path"], "build", plan["target"], "-c",
                cfg.get("configuration") or "Release", "-o", staging_out, "--nologo"] + extra
    return [toolchain["msbuild_path"], plan["target"], "/t:Build",
            "/p:Configuration=" + (cfg.get("configuration") or "Release"),
            "/p:OutDir=" + staging_out + os.sep, "/nologo"] + extra
```
> `/p:publishUrl=` con el `os.sep` final DENTRO del elemento de lista — el bug `"...\"` solo existe con strings de shell, prohibidos acá (idéntico razonamiento 201 F5).

**Flujo `start_publish` (pseudocódigo):**
```python
def start_publish(slug, workspace_root):
    run_id = uuid.uuid4().hex
    _RUNS[run_id] = {"status": "running", "slug": slug, "log": [], "_cancel": False, ...}
    threading.Thread(target=_run, args=(run_id, slug, workspace_root), daemon=True).start()
    return run_id

def _run(run_id, slug, workspace_root):
    from services import solution_store, publish_config_store, publish_profile_scanner
    from services.build_toolchain import detect_toolchain
    tc = detect_toolchain()
    sol = next((s for s in solution_store.load_catalog(workspace_root).get("solutions", [])
                if s.get("slug") == slug), None)
    if sol is None or not os.path.exists(sol.get("sln_path", "")):
        _finish(run_id, "failed", error="solucion_no_encontrada"); return
    cfg = publish_config_store.load_config(workspace_root, slug)
    plan = publish_profile_scanner.resolve_publish_plan(sol, cfg, tc)
    if not tc["available"]:
        _push(run_id, "error", tc["remediation"]["message"]); _finish(run_id, "toolchain_missing"); return
    if not plan["supported"]:
        _push(run_id, "error", "Plan de publish no soportado: " + plan["reason"])
        _finish(run_id, "unsupported", error=plan["reason"]); return
    base_dir = data_dir() / "solution_publish_artifacts" / slug / _ts()
    staging_out = str(base_dir / "out"); os.makedirs(staging_out, exist_ok=True)
    argv = _build_argv(plan, cfg, tc, staging_out)
    _set(run_id, argv=argv, base_dir=str(base_dir), mode_effective=plan["mode_effective"])
    _push(run_id, "info", "Publicando " + slug + " (" + plan["mode_effective"] + ")…")
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", cwd=os.path.dirname(plan["target"]))
    _set(run_id, _proc=proc)
    try:
        for line in proc.stdout:
            if _RUNS[run_id]["_cancel"]:
                _terminate_tree(proc); _finish(run_id, "cancelled"); return
            _push(run_id, "info", line.rstrip())
        proc.wait(timeout=_PUBLISH_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        _terminate_tree(proc); _push(run_id, "error", "timeout"); _finish(run_id, "failed", returncode=-1); return
    status = "success" if proc.returncode == 0 else "failed"
    if status == "success":
        zip_path = shutil.make_archive(str(base_dir), "zip", root_dir=staging_out)
        _set(run_id, zip_path=zip_path)
        prune_old_publish_runs((data_dir() / "solution_publish_artifacts" / slug))
    _finish(run_id, status, returncode=proc.returncode)   # _finish escribe summary + publish.log + línea de ledger SIEMPRE
```
- `_terminate_tree(proc)`: copiar del 201 F5 (`terminate()` + `taskkill /PID /T /F` best-effort; nunca lanza).
- `_finish` NUNCA lanza: summary/ledger con try/except + `logger.warning`.

**Casos borde:** slug inexistente → `failed/solucion_no_encontrada`; `.sln` movido → idem; plan no soportado → `unsupported` con `reason` (la UI ofrece el asistente — F6); doble click Publicar mismo slug → dos runs con `<ts>` únicos (no colisionan); cancel a mitad → `cancelled`; rutas con espacios/acentos → OK (lista de args).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan215_solution_publisher.py`:** (monkeypatch `detect_toolchain`, `subprocess.Popen` fake, `data_dir` → tmp, stores → tmp)
- `test_toolchain_missing_sets_status`
- `test_unsupported_plan_sets_status_and_reason`
- `test_success_produces_staging_zip_summary_and_ledger_line`
- `test_failed_returncode_sets_failed_and_still_writes_summary`
- `test_cancel_terminates`
- `test_argv_dotnet_publish_shape` (assert argv exacto: `["dotnet","publish",csproj,"-c","Release","--nologo","-o",staging]`-orden según `_build_argv`, y que `extra_args` van al final)
- `test_argv_msbuild_pubxml_includes_deployonbuild_and_publishurl`
- `test_no_shell_true` (inspección del source: ver criterio binario)
- `test_list_runs_reads_ledger_newest_first`
- `test_prune_keeps_max_retained`
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "shell=True" "Stacky Agents/backend/services/solution_publisher.py"` → 0; `grep -n "log_streamer" ...solution_publisher.py` → 0; `grep -n "publish.summary.json\|def prune_old_publish_runs" ...solution_publisher.py` → 2+.

**Flag:** gatea F5. **Runtimes:** idéntico 3/3 (MSBuild/dotnet, no LLM). **G7 citada** (rama `toolchain_missing`). **Operador:** click Publicar + confirm (HITL por diseño — no es excepción).

---

### F5 — API del publicador (`devops_solution_publisher.py`)

**Objetivo:** exponer catálogo lazy, re-scan, config, import, deep-scan, run/status/cancel/download/historial. Valor: todo el flujo por clicks.

**Archivo a crear:** `Stacky Agents/backend/api/devops_solution_publisher.py`.

```python
bp = Blueprint("devops_solution_publisher", __name__, url_prefix="/devops/solution-publisher")

import config as _config
def _guard():
    if not bool(getattr(_config.config, "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED", False)):
        abort(404)

def _deps_or_none():
    # G7 bis: el Plan 201 podría no estar mergeado. NUNCA ImportError al cliente.
    try:
        from services import solution_store, build_toolchain
        return solution_store, build_toolchain
    except ImportError:
        return None, None
```

**Endpoints (rutas finales `/api/devops/solution-publisher/...`):**

| Método | Ruta | Body | Respuesta | HITL |
|--------|------|------|-----------|------|
| `GET`  | `/catalog` | — | `{workspace_root, catalog:{scanned_at,truncated,solutions:[...+missing,+origin,+config,+plan]}, toolchain, first_scan_ran:bool}` | — (lazy scan automático) |
| `POST` | `/rescan` | `{}` | igual que `/catalog` (tras `rescan_preserving_manual`) | click (sin confirm: read-only) |
| `POST` | `/config` | `{slug, config:{...}}` | `{config}` o `400 {"error"}` | click Guardar |
| `POST` | `/solutions/import` | `{paths:[str], confirm:true}` | `{added:[slug], rejected:[{path,reason}], catalog}` | `confirm:true` |
| `POST` | `/deep-scan` | `{}` | `{paths:[...], new_paths:[...], timed_out}` (`new_paths` = no presentes en catálogo) | click |
| `POST` | `/run` | `{slug, confirm:true}` | `200 {run_id}` **o** `200 {status:"toolchain_missing", toolchain}` **o** `200 {status:"unsupported", reason}` | `confirm:true` |
| `GET`  | `/runs/<run_id>/status` | — | `{status, slug, mode_effective, argv, log:[...], artifact_ready, summary\|null, error}` | — |
| `POST` | `/runs/<run_id>/cancel` | `{confirm:true}` | `{cancelled:bool}` | `confirm:true` |
| `GET`  | `/runs/<run_id>/artifact/download` | — | `send_file(zip)` con guard `commonpath` contra `data_dir()/"solution_publish_artifacts"` (copiar el patrón EXACTO del 201 F7) | — |
| `GET`  | `/runs?slug=<slug>` | — | `{runs:[...]}` (ledger, máx 20) | — |
| `POST` | `/register-deploy-app` | `{run_id, confirm:true}` | `{app}` o `400` | `confirm:true` |

**Reglas clave:**
- **Lazy first-scan (KPI-1/2):** `GET /catalog` resuelve `ws = _active_workspace_root()` (`runtime_paths.py:66`); si `ws is None` → `200` con catálogo vacío + `"warning":"No hay proyecto activo con workspace_root."`. Si `load_catalog(str(ws))["scanned_at"] is None` → llamar `solution_store.rescan_preserving_manual(str(ws))` inline (walk acotado del 201: segundos) y responder con `first_scan_ran: true`. Si ya hay catálogo → NO escanear (`first_scan_ran: false`).
- Cada solución en la respuesta de `/catalog` se enriquece con: `missing` (§5.3), `config` (=`publish_config_store.load_config`), `plan` (=`resolve_publish_plan(sol, config, toolchain)`) y `publish_profiles` (=`scan_publish_profiles(sol["projects"])` aplanado por proyecto). Así la UI pinta TODO con un solo GET.
- `/solutions/import`: por cada path → normalizar, validar con `add_manual_solution` (que ya exige commonpath dentro del workspace + `.sln` legible); acumular `rejected` con `reason` = mensaje del `ValueError`. NUNCA 500 por una ruta mala.
- `/run`: `_guard()`; body sin `confirm:true` → `400 {"error":"confirm requerido"}`; slug ausente del catálogo → `400`. Responder SIEMPRE `200` para `toolchain_missing`/`unsupported` (la UI los renderiza; memoria `gotcha-frontend-api-wrapper-lanza-en-non-2xx` — `api.post` lanza en non-2xx).
- `/register-deploy-app`: exige run `success`; usa el ledger/summary para resolver `staging_dir` (= `base_dir/out`); payload y validación IDÉNTICOS al 201 F8 (`deploy_store.upsert_app`, `artifact:{kind:"folder", path:abspath}`, `id=slug` — `slugify_solution` ya garantiza `_APP_ID_RE`).
- Degradación 201 ausente: si `_deps_or_none()` da `None` → `200 {"error":"build_workshop_unavailable","detail":"Requiere el Taller de Compilación (Plan 201) implementado."}` en `/catalog`, `/rescan`, `/run`.
- Registro del blueprint en `Stacky Agents/backend/api/__init__.py` (patrón `:107-123`): `from .devops_solution_publisher import bp as devops_solution_publisher_bp  # Plan 215` + `api_bp.register_blueprint(devops_solution_publisher_bp)  # Plan 215 — url_prefix="/devops/solution-publisher"`.

**Casos borde:** flag OFF → 404 en todos; sin workspace activo → 200 vacío + warning; `run_id` inexistente → 404 en status/cancel/download; zip movido → 404; path con `..` en import → rechazado por commonpath.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan215_api.py`:** (Flask test client; monkeypatch `_active_workspace_root`, stores → tmp, `detect_toolchain`, `solution_publisher.start_publish`; molde `test_plan120_api.py:40`; flag por instancia `_config.config`)
- `test_endpoints_404_when_flag_off`
- `test_catalog_no_workspace_returns_empty_200`
- `test_catalog_first_open_triggers_scan_once` (1ª llamada: `first_scan_ran True` y `rescan_preserving_manual` invocado — spy; 2ª llamada: `first_scan_ran False` y spy NO re-invocado) — **KPI-1/2**
- `test_catalog_marks_missing_solutions`
- `test_config_save_validates_and_persists`
- `test_import_valid_and_invalid_paths_mixed`
- `test_run_requires_confirm`
- `test_run_toolchain_missing_returns_doctor_200`
- `test_run_unsupported_returns_reason_200`
- `test_run_starts_and_returns_run_id`
- `test_download_guard_rejects_outside_root`
- `test_register_deploy_app_requires_success_run`
- `test_catalog_degrades_when_201_absent` (monkeypatch `_deps_or_none` → `(None, None)` → `build_workshop_unavailable`)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -rn "devops_solution_publisher_bp" "Stacky Agents/backend/api/__init__.py"` → 2 matches; `grep -n "commonpath" "Stacky Agents/backend/api/devops_solution_publisher.py"` → 1+.

**Flag:** la de §4. **Runtimes:** idéntico 3/3. **G7 citada** (doctor en `/run`; `build_workshop_unavailable`). **Operador:** ninguno (lazy scan) / clicks HITL.

---

### F6 — Asistente DevOps ante fallos (contexto enmascarado + conversación HITL)

**Objetivo:** un click convierte un publish fallido (o `unsupported`/`toolchain_missing`, o un escaneo sin resultados) en una conversación con el **agente DevOps existente** (Plan 90), con todo el contexto ya cargado y enmascarado. Valor: "opción asistida por un agente de DevOps cuando el proceso presente errores o exceda lo determinístico" — sin construir un agente nuevo.

**Archivos a editar:** `Stacky Agents/backend/api/devops_solution_publisher.py` (+1 endpoint) y `Stacky Agents/backend/services/solution_publisher.py` (+1 función pura de composición).

**Función de composición (en `solution_publisher.py`; PURA respecto de sus inputs):**
```python
_ASSIST_LOG_TAIL = 120

def build_assist_message(run: dict, cfg: dict, solution: dict, toolchain: dict) -> str:
    # Texto plano para el chat DevOps. TODO el contenido variable pasa por mask_token_values (Plan 195).
    from services.secret_masking import mask_token_values
    lines = [
        "Necesito ayuda con la publicación de una solución (Publicador de Soluciones, Plan 215).",
        f"Solución: {solution.get('friendly_name')} ({solution.get('sln_path')})",
        f"Modo efectivo: {run.get('mode_effective')} | Estado: {run.get('status')} | Returncode: {run.get('returncode')}",
        "Comando ejecutado (argv): " + json.dumps(run.get("argv") or [], ensure_ascii=False),
        "Config actual (data/publish_configs.json): " + json.dumps(cfg, ensure_ascii=False),
        "Toolchain: " + json.dumps({k: toolchain.get(k) for k in ("available", "builder", "version")}, ensure_ascii=False),
    ]
    if toolchain.get("remediation"):
        lines.append("Doctor: " + toolchain["remediation"]["message"])
    tail = [e.get("message", "") for e in (run.get("log") or [])][-_ASSIST_LOG_TAIL:]
    lines.append("Últimas líneas del log del publish:")
    lines.append(mask_token_values("\n".join(tail)))
    lines.append(
        "Diagnosticá la causa raíz y proponé la corrección EXACTA (por ejemplo el JSON de config "
        "corregido para esta solución, o el comando de instalación del toolchain). NO ejecutes nada: "
        "yo aplico los cambios desde la UI y confirmo con CONFIRMO si hace falta ejecutar algo."
    )
    return "\n".join(lines)
```

**Endpoint nuevo:**
| Método | Ruta | Respuesta |
|--------|------|-----------|
| `GET` | `/runs/<run_id>/assist-context` | `{project, message}` o `404` |

- `project` = `project_manager.get_active_project()` (`project_manager.py:65`); si `None` → `400 {"error":"sin proyecto activo"}`.
- `message` = `build_assist_message(...)` con el run (memoria o ledger+summary), config, solución y `detect_toolchain()` frescos.
- **La creación de la conversación la hace el FRONTEND** llamando al endpoint EXISTENTE `POST /api/devops/agent/conversations` (`api/devops_agent.py:59`) con `{project, message, runtime}` — no se duplica lógica de lanzamiento, clamp de modelo (sin Opus, `devops_agent.py:87-92`) ni gestión de tickets `-2`. El backend de 215 solo COMPONE el contexto.
- **Paridad de runtimes (G4):**
  - `claude_code_cli` / `codex_cli`: conversación real (los dos runtimes de `_CLI_RUNTIMES`, `devops_agent.py:14`).
  - `copilot` (GitHub Copilot Pro): el endpoint del chat lo rechaza por diseño (`devops_agent.py:69-78`) → la UI NO ofrece "iniciar conversación" con copilot; ofrece **"Copiar contexto"** (copyService del Plan 194) para pegarlo en el flujo interactivo `open_chat` de VS Code. Fallback explícito, documentado en la UI.
  - Chat DevOps con flag `STACKY_DEVOPS_AGENT_ENABLED` OFF (health `agent_enabled` false): la UI muestra SOLO "Copiar contexto". No se agrega arista `requires=` entre flags (chequeo suave por health, no dependencia dura).
- **HITL:** el agente DevOps ya tiene la regla R-HITL en su system prompt (`agents/devops.py:21-29`); el mensaje la refuerza. El agente NUNCA edita `publish_configs.json`: propone el JSON y el operador lo pega en el editor de config (F7), que valida server-side (F2).

**Casos borde:** run inexistente → 404; run `success` → el contexto igual se puede pedir (botón visible solo en fallo, pero el endpoint no lo prohíbe — es read-only); log vacío → mensaje sin tail; secretos en el log (connection strings) → enmascarados por `mask_token_values`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan215_assist.py`:**
- `test_assist_context_includes_argv_config_and_tail`
- `test_assist_context_masks_secrets` (sembrar en el log un valor tipo token — PARTIR el literal en el fixture para no gatillar push-protection, memoria `gotcha-github-push-protection-test-fixture-secret` — y assert que NO aparece en `message`)
- `test_assist_context_unknown_run_404`
- `test_assist_context_no_active_project_400`
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "mask_token_values" "Stacky Agents/backend/services/solution_publisher.py"` → 1+ match.

**Flag:** la de §4 (+ health `agent_enabled` como chequeo suave en UI). **Runtimes:** claude/codex conversación; copilot copiar-contexto (fallback explícito). **Operador:** 1 click (asistir) — el agente jamás actúa solo.

---

### F7 — Frontend: modelo puro, sección y endpoints

**Objetivo:** la pantalla real: lista de soluciones con config individual, publish 1-click con preview del comando, log vivo, descarga, historial, re-scan/deep-scan/import y asistente. Valor: la "interfaz simple" pedida.

**Archivos a crear/editar:**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — agregar (espejo de `DevOpsBuildWorkshop` del 201 F10):
```ts
export const DevOpsSolutionPublisher = {
  catalog: () => api.get('/devops/solution-publisher/catalog'),
  rescan: () => api.post('/devops/solution-publisher/rescan', {}),
  saveConfig: (slug: string, config: unknown) => api.post('/devops/solution-publisher/config', { slug, config }),
  importSolutions: (paths: string[]) => api.post('/devops/solution-publisher/solutions/import', { paths, confirm: true }),
  deepScan: () => api.post('/devops/solution-publisher/deep-scan', {}),
  run: (slug: string) => api.post('/devops/solution-publisher/run', { slug, confirm: true }),
  runStatus: (runId: string) => api.get(`/devops/solution-publisher/runs/${runId}/status`),
  cancelRun: (runId: string) => api.post(`/devops/solution-publisher/runs/${runId}/cancel`, { confirm: true }),
  runs: (slug?: string) => api.get(`/devops/solution-publisher/runs${slug ? `?slug=${encodeURIComponent(slug)}` : ''}`),
  registerDeployApp: (runId: string) => api.post('/devops/solution-publisher/register-deploy-app', { run_id: runId, confirm: true }),
  assistContext: (runId: string) => api.get(`/devops/solution-publisher/runs/${runId}/assist-context`),
  artifactDownloadUrl: (runId: string) => `/api/devops/solution-publisher/runs/${runId}/artifact/download`,
};
export const DevOpsAgentChat = {
  // reusa el endpoint del Plan 90 — verificar si ya existe un objeto equivalente en endpoints.ts antes de agregarlo (grep "devops/agent/conversations"); si existe, usar ESE.
  startConversation: (project: string, message: string, runtime: string) =>
    api.post('/devops/agent/conversations', { project, message, runtime }),
};
```
> GOTCHA: `api.get/post` LANZAN en non-2xx (memoria `gotcha-frontend-api-wrapper-lanza-en-non-2xx`); por eso F5 responde 200 para doctor/unsupported/unavailable. Descarga = `<a href download>`, no `api.get`.

2. `Stacky Agents/frontend/src/components/devops/solutionPublisherModel.ts` + `.test.ts` — helpers PUROS (nombres exactos):
```ts
export interface PublishConfig { mode: 'auto'|'dotnet_publish'|'msbuild_pubxml'|'build_only'; configuration: string; project_csproj: string|null; publish_profile: string|null; extra_args: string[]; register_as_deploy_app: boolean; updated_at: string|null }
export interface PublishPlan { mode_effective: string; supported: boolean; reason: string; target: string; argv_tail: string[] }
export interface PublisherSolution { slug: string; sln_path: string; friendly_name: string; tracked: boolean; missing: boolean; origin?: 'scan'|'manual'; projects: { name: string; csproj_path: string; type: string }[]; config: PublishConfig; plan: PublishPlan; publish_profiles: { name: string; method: string; csproj_path: string }[] }

export function canPublish(sol: PublisherSolution, toolchainAvailable: boolean): boolean
// !sol.missing && sol.plan.supported && toolchainAvailable
export function publishStatusLabel(s: 'running'|'success'|'failed'|'cancelled'|'toolchain_missing'|'unsupported'): string
// español: 'Publicando…','Publicado','Falló','Cancelado','Falta toolchain .NET','No soportado' (sin colisionar con labels de deployments/buildWorkshop)
export function commandPreview(argv: string[]): string
// join con espacios, cada elemento con comillas si contiene espacio — SOLO para mostrar en el confirm (evidencia), jamás se ejecuta
export function planReasonLabel(reason: string): string
// mapa fijo: requiere_dotnet_sdk/requiere_msbuild/sin_pubxml_filesystem/pubxml_remoto_no_soportado/pubxml_no_encontrado/toolchain_missing → texto español accionable
export function parseSolutionPathsFromText(text: string): string[]
// extrae líneas que terminan en .sln (trim, dedup, ignora bullets/comillas) — para prellenar el import desde la respuesta del agente (F6/escalón 3)
export function needsAttention(sol: PublisherSolution): boolean
// missing || !plan.supported
```
Tests (`solutionPublisherModel.test.ts`): un `it` por función; bordes: `parseSolutionPathsFromText("- \"C:\\x\\A.sln\"\ntexto\nC:\\y\\B.sln")` → 2 rutas; `commandPreview(["msbuild","C:\\con espacio\\a.csproj"])` → segundo elemento entre comillas; `canPublish` con `missing:true` → false. Correr: `npx vitest run src\components\devops\solutionPublisherModel.test.ts`.

3. `Stacky Agents/frontend/src/components/devops/SolutionPublisherSection.tsx` — reemplaza el placeholder de F0. Comportamiento (todo clicks):
   1. Al montar: `useQuery(['solution-publisher-catalog'], DevOpsSolutionPublisher.catalog)` — **el primer GET dispara el scan solo** (F5). Si `first_scan_ran`, toast "Se escanearon las soluciones del proyecto (una única vez)". Si `error === 'build_workshop_unavailable'` → panel "Requiere el Taller de Compilación (Plan 201)".
   2. Header: chip de toolchain (verde/doctor con **Copiar comando** vía copyService — patrón 201 F10.1) + botones `Re-escanear` (→ `rescan`, invalida la query), `Escaneo profundo` (→ `deepScan`; muestra `new_paths` como checkboxes → botón `Importar seleccionadas` con confirm → `importSolutions`) y `Agregar .sln…` (modal `Dialog` canónico del Plan 164 con textarea; `parseSolutionPathsFromText` prellena/limpia; import validado server-side; muestra `rejected` con razones).
   3. Si el catálogo quedó vacío tras deep-scan: bloque "Escaneo agéntico" con botón **Buscar con agente DevOps** → `assistContext`-like mensaje fijo (NO requiere run): texto estático `"Buscá todos los archivos .sln del workspace <ws> y respondé SOLO la lista de rutas absolutas, una por línea."` armado en el componente + `DevOpsAgentChat.startConversation(project, message, 'claude_code_cli')` → al 202, `ctx.setActiveSection('agente')` (`DevOpsPage.tsx:237`) + toast "Conversación creada — pegá las rutas que devuelva en 'Agregar .sln…'". Con health `agent_enabled` false o runtime copilot: solo botón **Copiar pedido** (copyService).
   4. Tabla de soluciones: `friendly_name`, `sln_path` (badge `manual` si `origin==='manual'`, badge rojo "no encontrado" si `missing`), chips de proyectos, `plan.mode_effective` + (si `!plan.supported`) `planReasonLabel(reason)` en ámbar, botón **Configurar** y botón **Publicar** (deshabilitado según `canPublish`).
   5. **Configurar** abre modal (Dialog canónico): select `mode` (4 opciones), select `project_csproj` (proyectos de la solución + "auto"), select `publish_profile` (de `publish_profiles`, con method visible; solo FileSystem seleccionable), input `configuration`, editor de `extra_args` (chips; validación espejo del regex de F2 antes de enviar), toggle `register_as_deploy_app`. Guardar → `saveConfig` → invalida catálogo. Errores 400 del server se muestran textuales.
   6. **Publicar** abre confirm HITL mostrando `commandPreview` del argv previsto (derivado de `plan.argv_tail` + staging placeholder) → `run(slug)`. Respuesta `toolchain_missing` → doctor; `unsupported` → razón + botón asistente.
   7. Con `run_id`: `useQuery(['solution-publisher-run', runId], () => runStatus(runId), { refetchInterval: 1500, enabled: !!runId })` — log vivo, `publishStatusLabel`, **Cancelar** (confirm) mientras `running`.
   8. Al terminar: `success` → evidencia del `summary` (duración, files, bytes — reusar `formatBytes` de `buildWorkshopModel` si el 201 ya lo creó; si no, duplicar la función en `solutionPublisherModel` y anotar TODO de unificación), botón **Descargar** (`<a download>`), y si `config.register_as_deploy_app` botón **Registrar como app de despliegue** (confirm → `registerDeployApp` → toast + invalidar `['devops-deployments-overview']`). `failed`/`unsupported`/`toolchain_missing` → botón **Asistir con agente DevOps**: `assistContext(runId)` → modal con preview del mensaje + selector runtime (`claude_code_cli` default / `codex_cli`) + botones **Iniciar conversación** (→ `DevOpsAgentChat.startConversation` → `ctx.setActiveSection('agente')`) y **Copiar contexto** (copyService — único camino con copilot o chat OFF).
   9. Historial: acordeón por solución con `runs(slug)` (fecha, estado, duración, descargar si zip vigente).

**Ratchets (memoria):** cero `style={{}}` inline (clases en `./devops.module.css`); portapapeles SIEMPRE vía copyService (Plan 194); si `uiDebtRatchet`/`formDebtBaseline.json` marcan el archivo, agregar baseline propio sin empeorar deuda ajena; RTL/jsdom NO están instalados → el test de la sección valida SOLO el export (memoria `gotcha-rtl-jsdom-structural-gap`), gate real = `npx tsc --noEmit` + smoke manual.

**Tests (TDD):**
- `solutionPublisherModel.test.ts` (arriba).
- `Stacky Agents/frontend/src/components/devops/__tests__/SolutionPublisherSection.test.ts`: exporta `SolutionPublisherSection`. Correr por archivo.
- `npx tsc --noEmit` desde `Stacky Agents/frontend`.

**Criterio BINARIO:** vitest de los 2 archivos verdes; `tsc --noEmit` sin errores nuevos; `grep -rn "navigator.clipboard" "Stacky Agents/frontend/src/components/devops/SolutionPublisherSection.tsx"` → 0 matches; smoke manual: abrir la sección por primera vez lista soluciones sin clickear nada.

**Flag:** la de §4. **Runtimes:** UI idéntica 3/3; los botones agénticos degradan según §F6. **Operador:** ninguno para ver el catálogo; clicks HITL para actuar.

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación (fase) |
|--------|-------------------|
| Plan 201 no implementado al arrancar 215 | Regla de secuencia (§0: implementar 201 F0-F5 primero) + degradación `build_workshop_unavailable` en runtime (F5) — nunca crash. |
| Toolchain .NET ausente (EXCEPCIÓN #3) | Doctor del 201 + `status:"toolchain_missing"` + no-op; flag sigue ON (F4/F5, G7). |
| `.pubxml` remoto (MSDeploy/FTP) publicaría fuera de la máquina | `resolve_publish_plan` lo marca `unsupported/pubxml_remoto_no_soportado`; publicar a destinos es del Plan 120 (F1). |
| `extra_args` maliciosos/rotos | Allowlist regex sin espacios ni metacaracteres + máx 8 + argv en lista (sin shell) (F2/F4). |
| Publish escribe en el workspace del cliente | Salida SIEMPRE a staging propio (`-o` / `/p:publishUrl=` hacia `data/solution_publish_artifacts`); nunca se escribe el workspace (F4). |
| Disco lleno por artefactos | `prune_old_publish_runs` (≤10 por slug) + zip hermano (F4). |
| Path traversal en download | `commonpath` contra `data/solution_publish_artifacts` (F5, patrón 201 F7). |
| Doble-click Publicar | `<ts>` único (`_ts()` del 201 C5) → runs independientes (F4). |
| Secretos en el log del assist | `mask_token_values` sobre TODO el tail antes de componer el mensaje (F6). |
| Agente DevOps "arregla" solo | R-HITL del system prompt (Plan 90) + el agente no tiene endpoint de escritura de config; el operador pega/edita y el server valida (F2/F6). |
| Re-scan pierde altas manuales | `rescan_preserving_manual` re-anexa manuales existentes en disco (F3). |
| Merge duplicado silencioso con sesión paralela (TicketBoard/UnblockerPage activos) | 215 no toca esos archivos; en `api/__init__.py`/`endpoints.ts`/`DevOpsPage.tsx` (archivos de registro compartidos) verificar tras merge con grep del símbolo único (memoria `gotcha-merge-silent-duplicate-keyword`). |
| Meta-tests de flags/tests rojos | Cableado 5 lugares (§4) + registro en `HARNESS_TEST_FILES` en CADA fase. |
| Falsos verdes | Cada fase corre pytest POR ARCHIVO con el venv del backend y se lee el output real (regla dura del arnés). |

---

## 8. Fuera de scope (explícito)

- **Publicar a destinos remotos** (IIS remoto, MSDeploy, FTP, carpetas de servidores): eso es el **Plan 120** (Centro de Despliegues) — 215 produce el artefacto local y ofrece el bridge `register-deploy-app`.
- **Modificar la sección "Publicaciones" del Plan 88** (presets de procesos): queda intacta; si a futuro se quiere fusionar/retirar, es otro plan.
- **Compilación 1-click y artefactos del Taller** — es el Plan 201 (reusado, no absorbido).
- **Auto-instalar toolchain**, firmar binarios, transformaciones `web.config` por ambiente (XDT), y edición del catálogo del agente (el agente solo propone).
- **Ejecutar el escaneo agéntico con parsing automático de la respuesta del agente** — la frontera agéntico→estado es SIEMPRE el import validado (G3); automatizar ese parsing sería autonomía proactiva.
- **Promover `_PUBLISH_TIMEOUT_SEC`/`_MAX_RETAINED_RUNS` a flags de UI** (constantes, follow-up idéntico al 201).

---

## 9. Glosario (para modelo menor)

- **`.sln` / `.csproj` / `.vbproj`:** solución / proyectos .NET (ver glosario del 201 §9; los fixtures literales están en `201_PLAN_...md:395-411`).
- **publish vs build:** *build* compila (`bin/Release`); *publish* produce la carpeta LISTA para desplegar (binarios + estáticos + config), vía `dotnet publish` (proyectos SDK-style) o MSBuild `DeployOnBuild` + perfil `.pubxml` (proyectos clásicos .NET Framework).
- **`.pubxml`:** perfil de publicación de Visual Studio, en `<dir del csproj>/Properties/PublishProfiles/`. `<WebPublishMethod>FileSystem</WebPublishMethod>` publica a carpeta local (el único método que 215 ejecuta).
- **SDK-style:** `.csproj` moderno con atributo `Sdk=` en `<Project>`; se publica con `dotnet publish`. Los clásicos (ToolsVersion) requieren MSBuild.
- **workspace_root:** raíz del repo del proyecto activo (`projects/<active>/config.json`), resuelta por `runtime_paths._active_workspace_root()`.
- **slug:** id estable de una solución (`slugify_solution`, 201 F1), compatible con `deploy_planner._APP_ID_RE`.
- **catálogo:** `data/build_solutions.json` (201 F2) — la "lista de soluciones detectadas y sus rutas" que pide el operador.
- **doctor:** payload de remediación cuando falta MSBuild/.NET (`build_toolchain.detect_toolchain`, 201 F3).
- **chat DevOps (Plan 90):** conversación multi-turno con `DevOpsAgent` (`agents/devops.py`), tickets `ado_id=-2`, endpoint `POST /api/devops/agent/conversations`; regla R-HITL: nada se ejecuta sin "CONFIRMO" del operador.
- **copyService (Plan 194):** servicio central de portapapeles del frontend; `navigator.clipboard.writeText` directo está prohibido por ratchet.
- **Dialog canónico (Plan 164):** primitiva de modal con focus-trap de la casa; no inventar modales ad-hoc.
- **flag del arnés:** interruptor en `harness_flags.py` + `config.py`, toggleable desde Configuración → Arnés; el guard SIEMPRE lee la instancia `config.config`.
- **runtime vs LLM_BACKEND:** runtime = quién ejecuta agentes (codex_cli / claude_code_cli / copilot); el núcleo de 215 no usa ninguno.

---

## 10. Orden de implementación (numerado)

1. **F0** — Flag 5 lugares + sección + placeholder (meta-tests de flags verdes primero).
2. **F1** — `publish_profile_scanner.py` (PURO) + tests.
3. **F2** — `publish_config_store.py` + tests.
4. **F3** — extensiones aditivas scanner/store + `solution_deep_scan.py` + tests.
5. **F4** — `solution_publisher.py` (runner) + tests.
6. **F5** — blueprint + registro + tests de API.
7. **F6** — `build_assist_message` + endpoint assist-context + tests.
8. **F7** — modelo puro + sección + endpoints.ts + `tsc` + smoke.

F1/F2/F3 son independientes entre sí tras F0; F4 depende de F1+F2 (+201 F3); F5 depende de F3+F4; F6 depende de F4/F5; F7 depende de F5/F6.

---

## 11. Definición de Hecho (DoD) — binaria

- [ ] `STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED` en los 5 lugares (§4); `pytest tests\test_harness_flags.py -q` verde; `/api/devops/health` incluye `solution_publisher_enabled`.
- [ ] La sección "Publicar Soluciones" aparece (default ON) y respeta el gate declarativo.
- [ ] **Escaneo único:** el PRIMER `GET /catalog` escanea y persiste; el SEGUNDO no toca el disco del workspace (`test_catalog_first_open_triggers_scan_once` verde).
- [ ] El catálogo vive en `data/build_solutions.json` (el del 201 — un solo catálogo para 201 y 215) y marca `missing` para `.sln` borrados/movidos.
- [ ] Config individual por solución persistida en `data/publish_configs.json` con el shape de §5.2; `extra_args` inválidos rechazados con 400.
- [ ] `resolve_publish_plan` decide determinísticamente (`auto` → dotnet_publish / msbuild_pubxml / build_only) y reporta `reason` cuando no puede; pubxml no-FileSystem = `unsupported`.
- [ ] `POST /run` exige `confirm:true`; publica a staging propio; produce `publish.log`, `publish.summary.json`, `.zip` y línea en `data/solution_publish_runs.jsonl`; jamás `shell=True`.
- [ ] Sin toolchain → doctor 200 (no crash); sin Plan 201 → `build_workshop_unavailable` 200 (no crash).
- [ ] Download con guard `commonpath`; `register-deploy-app` crea la `DeployApp` vía `deploy_store.upsert_app`.
- [ ] Escalera de fallback operativa: `Re-escanear` (preserva manuales y `tracked`), `Escaneo profundo` (presupuesto de tiempo, `timed_out`), `Agregar .sln…`/import (validación commonpath + `.sln` legible; `rejected` con razones), y botón de escaneo agéntico que abre el chat DevOps prellenado (o copia el pedido con copilot/chat OFF).
- [ ] Run fallido → `assist-context` compone mensaje con argv + config + tail ENMASCARADO (`mask_token_values`); 1 click crea la conversación DevOps (claude/codex) o copia el contexto (copilot); el agente solo propone (R-HITL).
- [ ] Todos los `test_plan215_*.py` registrados en `HARNESS_TEST_FILES` y verdes POR ARCHIVO con el venv del backend; `solutionPublisherModel.test.ts` verde; `npx tsc --noEmit` sin errores nuevos.
- [ ] Flag OFF → endpoints 404 y sección oculta (byte-idéntico al estado actual).
- [ ] Paridad 3 runtimes: núcleo sin LLM (grep sin imports de llm/copilot/requests en los servicios nuevos deterministas); escalones agénticos con fallback explícito por runtime.
- [ ] Trabajo del operador: cero pasos nuevos obligatorios (scan lazy, config opcional con defaults, acciones por click HITL).
