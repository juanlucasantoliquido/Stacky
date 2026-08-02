# Plan 290 — La degradación deja de ser muda (y el switch de GitLab llega a la UI)

- **Estado:** PROPUESTO (v1)
- **Rama de trabajo:** `docs/plan-279`
- **Depende de:** Plan 281 F7 (los ocho guards), Plan 286 (`tracker_efectivo_de_ticket`), Plan 289 (`persistir_stats_de_contexto` y la paridad de los 3 runtimes), Plan 218 (`CAPABILITY_MATRIX` y `ParityMatrixPanel`), Plan 257 F4 (`LogLevelPanel`, precedente de configuración que SÍ aplica)
- **Fecha:** 2026-08-02

---

## 1. Objetivo y KPI

### 1.1 Objetivo en una frase

Cuando Stacky corre sobre un tracker que no es Azure DevOps y **decide a propósito no hacer algo**, hoy devuelve un valor neutro y no queda rastro para el operador; este plan hace que esa decisión quede **declarada en la metadata de la ejecución y visible en la interfaz**, sin cambiar ni un valor de retorno.

### 1.2 Qué NO es este plan

**No se arregla ninguna degradación.** Las degradaciones del Plan 281 F7 son **correctas y deliberadas**: `Microsoft.VSTS.Common.AcceptanceCriteria` no existe en GitLab, WIQL no existe en GitLab, `System.Rev` no existe en GitLab. Devolver el valor neutro es la conducta **correcta** y **se conserva byte a byte**.

> ⚠️ **AVISO AL IMPLEMENTADOR (leer dos veces).** Si en algún momento te parece que hay que "arreglar" `acceptance_criteria.py:43` o `self_review.py:57` para que traigan los criterios desde GitLab: **NO**. Ese campo no existe en GitLab. Cambiar el `return ""` por otra cosa es un cambio de semántica que rompe `review_artifact` (que espera `""` para devolver `skipped_reason="no_acceptance_criteria"`) y `acceptance_contract._get_criteria_text` (que trata `""` como "sin criterios"). Lo único que este plan agrega es **una línea de declaración antes del `return`**. El `return` no se toca.

### 1.3 KPIs binarios

| # | KPI | Hoy (medido 2026-08-02) | Meta |
|---|---|---|---|
| **K1** | % de ejecuciones que atraviesan un sitio de degradación instrumentado y lo declaran en `metadata["capability_degraded"]` | **0 %** (la clave no existe en el modelo de datos) | **100 %** |
| **K2** | Cantidad de `FlagSpec` cuya descripción afirma un default y el código tiene el contrario | **23** (medido por AST, §2.4) | **0** |
| **K3** | `STACKY_GITLAB_ENABLED` modificable desde la interfaz, con efecto en caliente verificable | **No** (0 referencias en `frontend/src/`) | **Sí** |
| **K4** | `base_url` de GitLab normalizada server-side igual que en el cliente | **No** (`rstrip("/")` vs. `normalizeGitlabUrl`) | **Sí** |

K1 se mide con el script de §F8.2. K2 se mide con el test de §F7.3, que es además el guardián permanente.

---

## 2. Por qué ahora — el gap, con evidencia

### 2.1 El Plan 281 F7 dejó ocho sitios que deciden en silencio

Censo exacto, por símbolo (`grep -rn "Plan 281 F7 sitio" --include=*.py`, ejecutado 2026-08-02):

| # | Archivo:línea del comentario | Línea del guard | Valor neutro que devuelve |
|---|---|---|---|
| 1 | `backend/api/agents.py:1911` | `:1921` | `sections` (lista vacía) |
| 2 | `backend/api/tickets.py:5102` | `:5111` | `"unknown"` |
| 3 | `backend/api/tickets.py:7763` | `:7762` | `_baseline_rev = None` |
| 4 | `backend/services/acceptance_criteria.py:38` | `:43` | `""` |
| 5 | `backend/services/business_preflight.py:85` | `:94` | `ok=True, mode=None` |
| 6 | `backend/services/self_review.py:50` | `:57` | `""` |
| 7 | `backend/services/similar_tickets.py:113` | `:122` | `[]` |
| 8 | `backend/services/ticket_assigner.py:390` | `:401` | `None` |

El más dañino es el **5**: `BusinessPreflightResult(ok=True, mode=None, ...)`. El operador que mira ese resultado lee **"preflight OK"**. No se validó nada.

### 2.2 El dato YA EXISTE en el productor y muere antes del consumidor operativo

Este es el hallazgo central y hay que escribirlo con precisión, porque una versión simplificada ("nadie lee el warning") llevaría al implementador a romper algo que hoy funciona.

`BusinessPreflightResult` **ya declara** el campo (`backend/services/business_preflight.py:27`):

```python
warnings: list[str] = field(default_factory=list)
```

y el sitio 5 **ya lo puebla** (`business_preflight.py:94-99`):

```python
if not tracker_is_azure_devops(project_name) and ruteo_estricto_por_tracker():
    return BusinessPreflightResult(
        ok=True,
        mode=None,
        warnings=["tracker no-ADO: sin cross-check de comentarios"],
    )
```

Quién lo consume hoy, verificado uno por uno:

| Consumidor | Lee `.warnings` | Qué hace |
|---|---|---|
| `backend/services/context_enrichment.py:1319` | **SÍ, pero solo `warnings[0]`** | `_reason = _bp.reason or (_bp.warnings[0] if _bp.warnings else "preflight_off")` → entra al bloque `run-directive` del prompt. **El AGENTE sí se entera.** |
| `backend/api/agents.py:542-561` | **NO** | Lee `.ok`, `.check`, `.reason`. Con `ok=True` sigue de largo y descarta el objeto entero. |
| Cualquier otro módulo de `api/`, `services/`, `harness/` | **NO** | `grep -rn "\.warnings" api/ services/ harness/ agent_runner.py` no devuelve ningún consumidor de `BusinessPreflightResult`. |

**Conclusión precisa del gap:** el dato **llega al agente** (por el prompt) y **no llega nunca al operador** (no hay metadata, no hay interfaz, no hay forma de contar cuántas corridas degradaron). Además `warnings[0]` **descarta del segundo en adelante**.

Y hay una confirmación literal de que esto es el defecto del 289 repitiéndose: `backend/tests/test_business_preflight.py:233` afirma

```python
assert result.warnings
```

o sea, **hay un test que verifica el campo en el PRODUCTOR y ningún test ni consumidor de producción que lo verifique en el destino**. Es exactamente el bloqueante central del Plan 289: *poné el assert en el consumidor, no donde se produce*.

### 2.3 El master switch de GitLab no está en la interfaz — pero el seam del backend YA existe

Verificado el 2026-08-02:

- `backend/config.py:1297-1299` → `os.getenv("STACKY_GITLAB_ENABLED", "false")`. **Default `false` en código.**
- `backend/.env:7` → `STACKY_GITLAB_ENABLED=true`. Está encendido **solo** por el `.env` del operador.
- **No tiene `FlagSpec`.** Y `backend/api/harness_flags.py:134` lo dice explícitamente: *"global_config (STACKY_GITLAB_ENABLED), que NO vive en este registro"*.
- **PERO** `backend/api/global_config.py:82` ya lo tiene en `_MANAGED_KEYS`. O sea: `PUT /api/global-config` **ya acepta la clave hoy**.
- `grep -rn "STACKY_GITLAB_ENABLED" frontend/src/` → **cero resultados**. Tampoco `GITLAB_URL`, ni `STACKY_GITLAB_GROUP`, ni `STACKY_GITLAB_EPICS_NATIVE`. **Ninguna** clave GitLab de `_MANAGED_KEYS` tiene superficie de interfaz.
- Hoy se enciende **de costado**, al crear un proyecto GitLab: `backend/api/projects.py:141-142`.
- Y `backend/services/setup_guides.py:147` ya lo denuncia por escrito: *"STACKY_GITLAB_ENABLED, y hoy no hay ninguna pantalla que la muestre"*.

**Sub-defecto que un modelo menor NO puede inferir y que decide el diseño de F5:** `_write_env` (`global_config.py:136-168`) escribe el `.env` y `os.environ`, **pero nunca hace `setattr` sobre el singleton `config.config`**. Y todos los consumidores leen `config.config.STACKY_GITLAB_ENABLED` (`services/tracker_provider.py:133`, `ci_provider.py:121`, `ci_variables.py:87`, `ci_preflight.py:39`, `ci_logs_provider.py:38`). Por lo tanto: **un panel que solo llame al PUT diría "guardado" y el motor seguiría con el valor viejo hasta reiniciar.** Sería un falso verde nuevo — precisamente el que `LogLevelPanel.tsx:9-11` documenta como razón para no usar el panel de flags.

`backend/api/projects.py:141-142` ya resuelve esto y es el patrón a copiar:

```python
_write_global_env({"STACKY_GITLAB_ENABLED": "true"})   # .env + os.environ
setattr(_config.config, "STACKY_GITLAB_ENABLED", True)  # hot-apply al singleton
```

### 2.4 Veintitrés flags mienten sobre su default (no dos)

El encargo hablaba de 2 flags con anclajes `harness_flags.py:4591` y `:4446`. **Esos dos anclajes son incorrectos** (ver §9, tabla de anclajes). La medición real, por AST sobre `backend/services/harness_flags.py` cruzada contra `backend/config.py`, da **23** sobre **490 `FlagSpec`**:

| # | Flag | Línea del `FlagSpec` | Dice | `default=` | `config.py` |
|---|---|---|---|---|---|
| 1 | `STACKY_TRACE_PROMPT_TEXT_ENABLED` | 2207 | OFF | `True` | `"true"` |
| 2 | `STACKY_RAG_CATALOG_ENABLED` | 2636 | OFF | `True` | (sin entrada) |
| 3 | `STACKY_DOCS_GRAPH_ENABLED` | 2650 | OFF | `True` | `"true"` |
| 4 | `STACKY_DOCS_RAG_HYBRID_ENABLED` | 2679 | OFF | `True` | `"true"` |
| 5 | `STACKY_DOCS_DOCUMENTER_ENABLED` | 2740 | OFF | `True` | `"true"` |
| 6 | `STACKY_DOCS_STALENESS_ENABLED` | 2804 | OFF | `True` | `"true"` |
| 7 | `STACKY_PROCESS_DISCIPLINE_ENABLED` | 3141 | OFF | `True` | `"true"` |
| 8 | `STACKY_PROJECT_AUTOPROFILE_ENABLED` | 3182 | OFF | `True` | (sin entrada) |
| 9 | `STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED` | 3231 | OFF | `True` | (sin entrada) |
| 10 | `INTENT_PREFLIGHT_ENABLED` | 3255 | OFF | `True` | `"true"` |
| 11 | `STACKY_ARTIFACT_RESCUE_ENABLED` | 3287 | OFF | `True` | (sin entrada) |
| 12 | `STACKY_PUSH_REJECTIONS_ENABLED` | 3315 | OFF | `True` | `"true"` |
| 13 | `STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED` | 3354 | OFF | `True` | (sin entrada) |
| 14 | `STACKY_EPIC_CATALOG_GATE_ENABLED` | 3411 | OFF | `True` | (sin entrada) |
| 15 | `STACKY_TASK_GATE_ENABLED` | 3426 | OFF | `True` | (sin entrada) |
| 16 | `STACKY_TASK_GATE_BLOCKING` | 3439 | OFF | `True` | (sin entrada) |
| 17 | `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` | 3454 | OFF | `True` | `"true"` |
| 18 | `STACKY_ADAPTIVE_SELECTOR_ENABLED` | 3566 | OFF | `True` | `"true"` |
| 19 | `STACKY_EPIC_PORTFOLIO_ENABLED` | 3593 | OFF | `True` | (sin entrada) |
| 20 | `STACKY_EPIC_DECOMPOSITION_ENABLED` | 3635 | OFF | `True` | (sin entrada) |
| 21 | `STACKY_ADO_EDIT_LEARNING_ENABLED` | 3672 | OFF | `True` | (sin entrada) |
| 22 | `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED` | 4608 | OFF | `True` | `"true"` |
| 23 | `STACKY_GITLAB_DEEP_LINKS_ENABLED` | 4753 | OFF | `True` | `"true"` |

> Las líneas son del `FlagSpec(` (nodo AST), no del texto. **Reproducí la medición antes de editar** (§F7.1): si el número que te da no es 23, las líneas se movieron y hay que re-medir, no adivinar.

Cuatro verificadas a mano contra el texto real:

- `STACKY_TRACE_PROMPT_TEXT_ENABLED` → *"...incluye el texto completo del prompt (JSON de context_blocks) en la metadata. **Privacidad: default OFF.** Solo activar en ambientes controlados donde el contenido del prompt no es sensible."* — y está **ON**. Es la más grave: la descripción promete una garantía de privacidad que el código no cumple.
- `STACKY_ARTIFACT_RESCUE_ENABLED` → *"...lo publica. **Default OFF.**"* — `default=True`, `env_only=True`.
- `STACKY_TASK_GATE_BLOCKING` → *"...impide la creación en ADO (devuelve 400 TASK_GATE_BLOCKED). **Default OFF.**"* — `default=True`, `env_only=True`.
- `STACKY_GITLAB_DEEP_LINKS_ENABLED` → *"...muestra el ID como texto plano. **Default OFF.** Activa cuando..."* — `default=True`.

### 2.5 `base_url` se normaliza solo del lado del cliente

- Cliente: `frontend/src/projects/newProjectGitlabModel.ts:39` → `normalizeGitlabUrl` saca barra final, `/api/vN` **y cualquier path** (arreglo del Plan 276 F8.3 al namespace pegado).
- Servidor: `backend/project_manager.py:670` → `"base_url": url.rstrip("/")`. **Solo la barra final.**

Cualquier alta que no pase por ese formulario (importación, edición manual del JSON, un cliente futuro) deja `https://host/grupo/proyecto` como base y todas las llamadas salen a `.../grupo/proyecto/api/v4/...` → 404.

### 2.6 Lo que ya existe y hay que reusar (no construir de nuevo)

| Pieza | Dónde | Estado medido |
|---|---|---|
| `CAPABILITY_MATRIX` | `backend/services/provider_capabilities.py:95` | 71 capacidades. ADO: 38 full / 8 partial / 25 absent. GitLab: 34 full / 14 partial / **21** absent / 2 n/a. |
| `capability_status` / `supports` / `capability_loss` | `provider_capabilities.py:344` / `:349` / `:354` | `capability_status` ya es fail-closed: lo desconocido devuelve `"absent"`. |
| Endpoint de paridad | `backend/api/parity.py:15` → `GET /api/parity/matrix` | Gateado por `STACKY_PROVIDER_PARITY_ENABLED`; 404 si está apagada. |
| `ParityMatrixPanel` | `frontend/src/components/ParityMatrixPanel.tsx` | Montado en `DiagnosticsPage.tsx:331`, **sin prop `project`**. |
| `parityMatrixModel.ts` | `frontend/src/services/parityMatrixModel.ts` | Lógica pura testeable; `statusLabel`/`statusMark` ya caen a "Ausente"/"✕" en lo desconocido. |
| `persistir_stats_de_contexto` | `backend/services/context_enrichment.py:284` | Idioma de escritura en `metadata_dict`: nunca levanta, idempotente, escribe temprano. Llamada por los 3 runtimes: `agent_runner.py:819`, `claude_code_cli_runner.py:685`, `codex_cli_runner.py:342`. |
| `ruteo_estricto_por_tracker` | `backend/services/project_context.py:78` | Kill-switch de los 8 guards. Se lee del **objeto** `config`, nunca con `os.getenv` (lo vigila `test_flags_env_read_meta.py`). |
| `LogLevelPanel` | `frontend/src/components/LogLevelPanel.tsx` | Precedente exacto de "configuración del operador que SÍ aplica en caliente", montado en `DiagnosticsPage.tsx:328`. |
| Patrón de aviso en el drawer | `ExecutionDetailDrawer.tsx:74-102` | `metadata.egress_sentinel`, `metadata.local_insight`, `metadata.blocked_downgrade`: cada uno un sub-componente + modelo puro. |

---

## 3. Principios y guardarraíles

1. **El valor neutro no se toca.** Todas las fases agregan una llamada **antes** del `return`. Ningún `return` cambia de valor, de tipo ni de posición. Hay un test dedicado por sitio (§F2.4, §F3.4).
2. **Cero flags nuevas.** Justificación completa en §3.1.
3. **Nunca levanta.** El registro de degradación es telemetría: cualquier excepción se traga y se loguea. Una corrida jamás se cae por no poder anotar un aviso.
4. **Human-in-the-loop.** Nada de esto decide por el operador: declara y muestra. `STACKY_GITLAB_ENABLED` sigue siendo una perilla que el operador mueve a mano.
5. **Mono-operador sin auth.** No hay RBAC. Un `403` acá significaría "flag apagada", nunca "permiso". Ninguna fase agrega chequeos de permiso.
6. **Backward-compatible.** No cambia ninguna firma pública. `metadata["capability_degraded"]` es una clave **nueva**: su ausencia es el estado válido de todas las ejecuciones históricas y de toda corrida que no degrade.
7. **Paridad de 3 runtimes verificada, no asumida.** §3.2.
8. **Trabajo del operador: ninguno** en todas las fases. Se declara explícitamente fase por fase.

### 3.1 Por qué este plan NO registra ninguna flag nueva

El riel dice que toda flag nueva nace ON salvo que queme tokens en reposo o escriba en un sistema real. Registrar una degradación es **solo lectura + una escritura local en la propia fila de la ejecución** ⇒ le correspondería nacer ON. **Pero una flag que nace ON y no apaga nada útil es una flag de más**, y en este repo cuesta caro:

- Una flag nueva es un bloque atómico con **ocho guardianes**, incluido `test_requires_map_is_frozen`, que está indexado **por key de flag**: no se esquiva ni declarando `requires=` ni omitiéndolo.
- Registrarla ON obliga a los TRES lugares: `config.py` con `"true"`, `FlagSpec(default=True)` y la key en `_CURATED_DEFAULTS_ON` de `backend/tests/test_harness_flags.py`.

**Y ya existe el kill-switch correcto.** Los 8 sitios están, sin excepción, dentro de `... and ruteo_estricto_por_tracker()` (verificado en las 8 líneas de §2.1). La declaración de degradación va **dentro de ese mismo `if`**. Por lo tanto:

> Apagar `STACKY_TRACKER_STRICT_ROUTING` (la flag que lee `ruteo_estricto_por_tracker`) apaga el guard **y** su declaración, en un solo movimiento, y el rollback es byte-idéntico al estado previo al Plan 281 F7. Una flag nueva sería un segundo interruptor para la misma luz.

Para F4 (interfaz) el gate ya es `STACKY_PROVIDER_PARITY_ENABLED`: apagada, el endpoint da 404 y `ParityMatrixPanel` no se monta. El aviso nuevo del drawer se alimenta de `metadata`, que simplemente no existe si no hubo degradación: no necesita gate propio.

**Consecuencia operativa para el implementador:** ninguna fase de este plan toca `backend/services/harness_flags.py` para AGREGAR una flag. F7 lo toca **solo para corregir texto de `description=`**, sin tocar `key`, `type`, `default`, `group`, `requires`, `env_only` ni `min/max`.

### 3.2 Paridad de los 3 runtimes — verificada archivo por archivo

El Plan 289 encontró que 2 de 3 runtimes tiraban el stat. Acá se verificó antes de diseñar, y los dos sitios elegidos tienen paridad **por construcción**, cada uno por una vía distinta:

**Sitio `business_preflight`** — se alcanza por dos caminos, ambos comunes a los 3 runtimes:

| Camino | Archivo:línea | Cubre |
|---|---|---|
| Lanzamiento (API) | `backend/api/agents.py:542` | Los 3: es el endpoint de arranque, anterior a cualquier bifurcación de runtime. |
| Enriquecimiento | `backend/services/context_enrichment.py:1288` | Los 3: es el armador de bloques que el Plan 289 F6 unificó. |

**Sitio `self_review`** — se alcanza por `apply_to_execution(execution_id=...)` desde tres call sites distintos, uno por runtime:

| Runtime | Archivo:línea |
|---|---|
| GitHub Copilot Pro (vía `agent_runner`) | `backend/services/agent_completion_internal.py:174` |
| Claude Code CLI | `backend/services/claude_code_cli_runner.py:3227` |
| Codex CLI | `backend/services/codex_cli_runner.py:2008` |

⚠️ **Los tres llaman a `apply_to_execution`, no a `review_artifact`.** `apply_to_execution` llega a `review_artifact` por `self_review.py:168`. La instrumentación va en `review_artifact` (§F3), que es el punto único por el que pasan los tres. **No** hay que instrumentar los tres call sites: sería triplicar el mismo registro.

**Fallback explícito:** si por cualquier motivo `execution_id` no se puede resolver (por ejemplo `review_artifact` invocado desde `harness/criteria_repair.py` en un contexto sin fila), `declarar()` devuelve `False` y no escribe. No levanta, no loguea a nivel warning, no cambia el retorno de la función que la llamó.

---

## 4. Fases

Cada fase es autocontenida y se commitea sola. El orden es de dependencia: F1 antes que F2/F3; F2/F3 antes que F4.

Comando de test, **siempre por archivo, nunca la suite entera**:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "<ruta>" -q
```

> El intérprete es `backend/.venv` (py3.13.5), **no** `backend/venv` (py3.11.9, sin las dependencias).

---

### F0 — Los dos centinelas en ROJO

**Objetivo:** dejar escrito, en un test que hoy falla, qué significa "la degradación dejó rastro".

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan290_degradacion_declarada.py`

**Casos (los 2 son de EJECUCIÓN, no estáticos):**

1. `test_preflight_no_ado_declara_la_degradacion_en_la_metadata` — crea un `Ticket` de un proyecto no-ADO y un `AgentExecution`, corre el camino que llega a `business_preflight.evaluate`, y afirma que `AgentExecution.metadata_dict["capability_degraded"]` contiene una entrada con `capability == "tracker.comments.list"`.
2. `test_self_review_sin_criterios_declara_la_degradacion` — ídem con `self_review.review_artifact(execution_id=..., artifact_text="x")`, afirmando una entrada con `capability == "tracker.acceptance_criteria"`.

**Cómo se comprueba el ROJO (obligatorio, y así se reporta):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_degradacion_declarada.py" -q
```

Debe salir **2 failed**. El modo de falla esperado es **`KeyError: 'capability_degraded'`** o un `assert` sobre un `dict` sin esa clave — **no** `ImportError` ni `ModuleNotFoundError`. Si falla por import, el test está mal escrito: está probando que el módulo de F1 no existe (una tautología), no que el comportamiento falta. **Pegá la salida real en el commit de F0.**

> **Trampa de gate (molde b).** Estos dos tests **deben ejecutar** el camino real. Un test que se limite a `grep` el fuente buscando la llamada a `declarar(` pasa igual si la llamada está dentro de una rama muerta. Se verifica el efecto en la fila de la base, no la presencia del símbolo en el archivo.

**Criterio binario:** el comando de arriba sale con **exit code 1** y **2 failed**, y ninguno de los 2 fallos es un error de importación.

**Flag:** ninguna. **Impacto por runtime:** ninguno (solo agrega un archivo de tests). **Trabajo del operador: ninguno.**

**Registro en los ratchets:** ver §F0.1.

#### F0.1 — Registro del archivo de tests en los DOS ratchets

> ⚠️ **Los dos archivos NO tienen "ratchet" en el nombre.** Buscarlos por esa palabra no los encuentra. Son, verificado el 2026-08-02:
>
> | Archivo | Símbolo del array | Entradas |
> |---|---|---|
> | `Stacky Agents/backend/scripts/run_harness_tests.sh` | `HARNESS_TEST_FILES=(` (línea 20) | **820** |
> | `Stacky Agents/backend/scripts/run_harness_tests.ps1` | `$HarnessTestFiles = @(` (línea 13) | **756** |
>
> **Divergen en 64 entradas.** No asumas que lo que está en uno está en el otro.

**Sintaxis exacta de cada uno — son distintas y NO son intercambiables.**

`run_harness_tests.sh` — dos espacios de indent, ruta **cruda sin comillas**, **sin coma**:

```bash
  tests/test_plan288_cuenta_local.py
  # Plan 289 - El agente deja de trabajar a ciegas sobre un ticket de GitLab
  tests/test_plan289_contexto_por_tracker.py
  tests/test_plan289_stat_de_contexto.py
)
```

`run_harness_tests.ps1` — dos espacios de indent, ruta **entre comillas dobles**, **coma al final salvo la última**:

```powershell
  "tests/test_plan288_cuenta_local.py",
  # Plan 289 - El agente deja de trabajar a ciegas sobre un ticket de GitLab
  "tests/test_plan289_contexto_por_tracker.py",
  "tests/test_plan289_stat_de_contexto.py"
)
```

> ⚠️ **Trampa del `.ps1`:** hoy `"tests/test_plan289_stat_de_contexto.py"` es la última y **no lleva coma**. Al agregar entradas nuevas después hay que **agregarle la coma a esa línea**. En el `.sh` no hace falta tocar la línea previa. Olvidarse rompe el array de PowerShell.

**Reglas:**

- El registro va **en el commit que crea el archivo de tests**, no al final del plan: los ratchets son trampa de **commit**, no solo de edición.
- **Anclá por SÍMBOLO, no por línea.** La cola se mueve en horas (pasó de `test_plan287_*` a `test_plan288_*` a `test_plan289_*` en un día). Buscá la última entrada `tests/test_plan28*` o `tests/test_plan29*` y agregá **después**, con un comentario `# Plan 290 - La degradacion deja de ser muda` siguiendo el estilo (sin tildes, igual que los vecinos).
- **Rutas relativas al backend y sin espacios** (`tests/test_plan290_*.py`). Los ratchets no admiten rutas con espacios.
- **Allowlist:** `Stacky Agents/backend/tests/harness_ratchet_allowlist.txt` **existe** (207 líneas, 194 efectivas). Verificado: **no menciona** `self_review` ni `business_preflight`; la única línea con `capability` es `tests/test_harness_capabilities.py  # pendiente-de-triage`, que **no** es ninguno de los archivos de este plan. Por lo tanto **ningún archivo nuevo de este plan necesita salir del allowlist** — pero si al implementar agregás un archivo que sí figure ahí, **hay que sacarlo**: estar en el ratchet y en el allowlist son dos declaraciones contradictorias.

**Los 6 archivos de tests que este plan debe registrar en AMBOS:**

```
tests/test_plan290_degradacion_declarada.py      (F0)
tests/test_plan290_registro_degradacion.py       (F1)
tests/test_plan290_preflight_no_regresion.py     (F2)
tests/test_plan290_self_review_no_regresion.py   (F3)
tests/test_plan290_gitlab_switch_ui.py           (F5)
tests/test_plan290_base_url_normalizada.py       (F6)
tests/test_plan290_defaults_no_mienten.py        (F7)
```

(Son **7** contando F7; los 6 del cuerpo más el guardián de descripciones.)

**Criterio binario:** después de cada registro, el conteo de entradas del `.sh` y del `.ps1` sube en **exactamente 1**, y correr los dos scripts da el mismo veredicto que en el commit base (**delta cero**, §5.1). Ninguno pasa de verde a rojo.

---

### F1 — El registro de degradación

**Objetivo:** un único escritor de `metadata["capability_degraded"]`, con la misma disciplina que `persistir_stats_de_contexto`.

**Archivo nuevo:** `Stacky Agents/backend/services/capability_degradation.py`

**Símbolos exactos a crear:**

```python
CLAVE_METADATA = "capability_degraded"

def construir_entrada(*, capability: str, reason: str, provider: str, site: str) -> dict:
    """PURA. Devuelve la forma canónica. Sin I/O, sin base, sin config."""

def declarar(*, execution_id: int | None, capability: str, reason: str,
             provider: str, site: str, session_factory=None,
             log=None) -> bool:
    """Anota la degradación en metadata. NUNCA levanta. Idempotente."""
```

**Forma canónica de la entrada** (contrato congelado; el consumidor de F4 depende de estas cinco claves y de ninguna más):

```python
{
    "capability": "tracker.comments.list",   # key de CAPABILITY_MATRIX, o clave lógica propia
    "reason": "tracker no-ADO: sin cross-check de comentarios",
    "provider": "gitlab",
    "site": "business_preflight.evaluate",   # símbolo, NUNCA archivo:línea (las líneas caducan)
    "at": "2026-08-02T14:05:00+00:00",       # ISO-8601 UTC
}
```

**Pseudocódigo de `declarar` — copiar la disciplina de `context_enrichment.py:284-321`:**

```
si execution_id es None  -> return False           # sin destino, no-op silencioso
si capability vacío       -> return False
try:
    session_factory = session_factory or (from db import session_scope)   # import LOCAL: evita ciclos
    with session_factory() as sesion:
        fila = sesion.get(AgentExecution, execution_id)
        si fila is None -> return False
        md = dict(fila.metadata_dict or {})
        lista = list(md.get(CLAVE_METADATA) or [])
        entrada = construir_entrada(...)
        # DEDUP por (capability, site): la misma degradación en la misma corrida
        # se anota UNA vez. Sin esto, un backlog de 200 tickets escribe 200 veces.
        si existe e en lista con (e["capability"], e["site"]) == (entrada["capability"], entrada["site"]):
            return False
        lista.append(entrada)
        md[CLAVE_METADATA] = lista
        fila.metadata_dict = md      # reasignación COMPLETA del dict
    return True
except Exception as exc:
    log("warn", f"no se pudo declarar la degradación: {exc}")
    return False
```

**Casos borde que el pseudocódigo ya cubre y hay que testear:**

| Caso | Conducta esperada |
|---|---|
| `execution_id=None` | `False`, sin tocar la base, sin excepción. |
| `execution_id` inexistente en la tabla | `False`, sin excepción. |
| `metadata_dict` es `None` | Se crea el dict; la lista arranca vacía. |
| `metadata_dict` ya tiene otras claves (`ado_context`, `egress_sentinel`) | **Se preservan intactas.** |
| Misma `(capability, site)` dos veces | La segunda devuelve `False` y **no** duplica. |
| Distinta `capability`, mismo `site` | Se agregan **las dos**. |
| La sesión revienta (base bloqueada) | `False` + log `warn`. **Nunca propaga.** |

> ⚠️ **`fila.metadata_dict = md` con reasignación completa es obligatorio.** Mutar el dict devuelto por el getter no marca la fila como sucia en SQLAlchemy y el cambio se pierde en silencio. Es el mismo idioma de `persistir_stats_de_contexto` (`context_enrichment.py:315-317`) y hay que respetarlo tal cual.

**Tests (archivo nuevo):** `Stacky Agents/backend/tests/test_plan290_registro_degradacion.py` — un caso por fila de la tabla de bordes (7 casos), más uno que verifica que `construir_entrada` es pura (dos llamadas con los mismos argumentos, salvo `at`, dan el mismo dict).

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_registro_degradacion.py" -q
```

**Criterio binario:** **8 passed, 0 failed**. Y el test de "preserva otras claves" debe afirmar **la PRESENCIA** de `ado_context` después de escribir, no solo la ausencia de errores (un `assert` de ausencia suelto pasa por accidente).

**Flag:** ninguna (§3.1). **Impacto por runtime:** ninguno todavía — nadie lo llama aún. **Trabajo del operador: ninguno.**

**Ratchets:** registrar `tests/test_plan290_registro_degradacion.py` en los dos, con las reglas de §F0.1.

---

### F2 — Sitio 1: `business_preflight` declara, y los DOS consumidores consumen

**Objetivo:** que la degradación del preflight quede en la metadata de la ejecución y que el consumidor del prompt deje de tirar los warnings del segundo en adelante.

**Archivo:** `Stacky Agents/backend/services/business_preflight.py`

**F2.1 — Firma: `evaluate` acepta `execution_id` OPCIONAL.**

```python
# ANTES (línea 161)
def evaluate(*, ticket_id: int, agent_type: str) -> BusinessPreflightResult:

# DESPUÉS
def evaluate(
    *, ticket_id: int, agent_type: str, execution_id: int | None = None
) -> BusinessPreflightResult:
```

> **Backward-compatible por construcción:** es keyword-only con default `None`. Los dos call sites existentes siguen funcionando sin tocarlos. `tests/test_business_preflight.py` la llama sin el argumento en todos sus casos y **no debe modificarse**.

**F2.2 — La declaración, dentro del guard existente** (`business_preflight.py:94-99`). Se agrega **antes** del `return`, el `return` no cambia:

```python
if not tracker_is_azure_devops(project_name) and ruteo_estricto_por_tracker():
    _motivo = "tracker no-ADO: sin cross-check de comentarios"
    # Plan 290 F2 — la degradación deja rastro. NO cambia el retorno.
    from services import capability_degradation
    capability_degradation.declarar(
        execution_id=execution_id,
        capability="tracker.comments.list",
        reason=_motivo,
        provider=tracker_efectivo_de_ticket(_ticket) if _ticket else "desconocido",
        site="business_preflight.evaluate",
    )
    return BusinessPreflightResult(ok=True, mode=None, warnings=[_motivo])
```

- `capability="tracker.comments.list"` es una key **real** de `CAPABILITY_MATRIX` (`provider_capabilities.py`, dominio `tracker`). Es la capacidad que el Modo B necesita y no tiene.
- El `provider` sale de **`tracker_efectivo_de_ticket`** (Plan 286, `services/project_context.py:206`). **No inventes otro resolvedor** y no leas `ticket.tracker_type` crudo: la precedencia columna-explícita > config > default ya está resuelta ahí.
- Import **local** dentro de la función, no a nivel de módulo: `business_preflight` ya usa ese idioma para evitar ciclos.

**F2.3 — El consumidor del prompt deja de tirar warnings.** `services/context_enrichment.py:1319`:

```python
# ANTES
_reason = _bp.reason or (_bp.warnings[0] if _bp.warnings else "preflight_off")

# DESPUÉS
_reason = _bp.reason or ("; ".join(_bp.warnings) if _bp.warnings else "preflight_off")
```

> Hoy hay **un solo** warning, así que este cambio es un no-op observable en el estado actual. Se hace igual porque el `[0]` es una bomba silenciosa: el día que un sitio agregue el segundo warning, se pierde sin aviso. El test de F2.4 lo fija con **dos** warnings.

**F2.4 — Y el consumidor que NO consumía, consume.** `services/context_enrichment.py:1288` es el call site que **sí** tiene contexto de ejecución en el enriquecimiento. Hay que pasarle el `execution_id` que ya circula por `context_enrichment`:

```python
_bp = business_preflight.evaluate(
    ticket_id=ticket_id, agent_type=agent_type, execution_id=execution_id
)
```

> ⚠️ **Verificá que `execution_id` esté realmente en el scope de esa función antes de escribir la línea.** Si no lo está, hay que subirlo por parámetro **con default `None`** desde el armador que sí lo tiene, sin cambiar ninguna firma pública de forma incompatible. **Si no se puede sin romper una firma pública, pasá `None` y decilo en el commit** — F3 sigue cubriendo el KPI y esta rama queda documentada como límite conocido. Lo que **no** se acepta es inventar que el argumento existe.
>
> `api/agents.py:542` (lanzamiento) **se deja como está**: en ese punto todavía no hay fila de `AgentExecution`, así que no hay destino donde anotar. Pasarle un `execution_id` inventado sería peor que no anotar.

**F2.5 — Tests.** En el mismo `test_plan290_degradacion_declarada.py` de F0 (que pasa de rojo a verde en su caso 1), más en un archivo nuevo `Stacky Agents/backend/tests/test_plan290_preflight_no_regresion.py`:

| Caso | Afirma |
|---|---|
| `test_el_valor_neutro_no_cambio` | Con proyecto no-ADO: `result.ok is True`, `result.mode is None`, `result.warnings == ["tracker no-ADO: sin cross-check de comentarios"]`. **Byte a byte lo de hoy.** |
| `test_proyecto_ado_no_declara_nada` | Con proyecto ADO: `metadata` **no** tiene la clave `capability_degraded`. Sentinela negativo. |
| `test_flag_apagada_no_declara_nada` | Con `ruteo_estricto_por_tracker()` falso (monkeypatch sobre el objeto `config`): ni guard ni declaración. |
| `test_sin_execution_id_no_levanta` | `evaluate(ticket_id=..., agent_type=...)` sin el kwarg: devuelve el mismo resultado y no lanza. |
| `test_dos_warnings_llegan_completos_al_prompt` | Con dos warnings, el bloque `run-directive` contiene **los dos**, separados por `; `. Se afirma sobre el `content` del bloque, que es **el consumidor**, no sobre `_bp.warnings`. |

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_preflight_no_regresion.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_business_preflight.py" -q
```

**Criterio binario:** el archivo nuevo da **5 passed**; `test_business_preflight.py` da **exactamente el mismo conteo que en el commit base** (§5.1) **sin haber sido editado** (`git diff --stat` sobre ese archivo debe salir vacío).

**Flag:** ninguna. Kill-switch heredado: `ruteo_estricto_por_tracker()`.
**Impacto por runtime:** los 3, por los dos caminos de §3.2. **Fallback:** sin `execution_id`, `declarar` devuelve `False` y el preflight se comporta idéntico a hoy.
**Trabajo del operador: ninguno.**

**Ratchets:** registrar `tests/test_plan290_preflight_no_regresion.py` en los dos (§F0.1).

---

### F3 — Sitio 2: `self_review` declara (con el `execution_id` que ya tiene en la mano)

**Objetivo:** que un self-review omitido por falta de criterios deje de parecer un self-review aprobado.

**Por qué este sitio y no otro:** `review_artifact(*, execution_id: int, artifact_text: str)` (`services/self_review.py:76`) **ya recibe el `execution_id`**. Es el único de los ocho donde el destino está en el scope inmediato, sin plomería nueva. Y el daño es alto: cuando `_resolve_criteria` devuelve `""`, `review_artifact` devuelve `SelfReviewResult(score=1.0, checklist=[], skipped_reason="no_acceptance_criteria")` — un **score de 1.0**, o sea "perfecto", para un artefacto que nadie revisó.

**Archivo:** `Stacky Agents/backend/services/self_review.py`

**F3.1 — La declaración va en `review_artifact`, NO en `_resolve_criteria`.** Razón: `_resolve_criteria(ticket)` no tiene `execution_id` y lo llaman también otros caminos; instrumentarla exigiría cambiarle la firma. En `review_artifact` el dato está a tres líneas.

```python
    criteria_text = _resolve_criteria(ticket)
    if not criteria_text:
        # Plan 290 F3 — el self-review se saltea. Que quede dicho, no solo devuelto.
        # NO cambia el retorno: sigue score=1.0 + skipped_reason.
        from services import capability_degradation
        from services.project_context import (
            ruteo_estricto_por_tracker,
            tracker_efectivo_de_ticket,
            tracker_is_azure_devops,
        )
        if (
            not tracker_is_azure_devops(getattr(ticket, "stacky_project_name", None))
            and ruteo_estricto_por_tracker()
        ):
            capability_degradation.declarar(
                execution_id=execution_id,
                capability="tracker.acceptance_criteria",
                reason=(
                    "el tracker no expone criterios de aceptación "
                    "(Microsoft.VSTS.Common.AcceptanceCriteria es un campo de Azure DevOps): "
                    "el self-review se saltea y NO evaluó el artefacto"
                ),
                provider=tracker_efectivo_de_ticket(ticket),
                site="self_review.review_artifact",
            )
        return SelfReviewResult(score=1.0, checklist=[], skipped_reason="no_acceptance_criteria")
```

> **Por qué se repite el guard `tracker_is_azure_devops(...) and ruteo_estricto_por_tracker()`:** `criteria_text` puede venir vacío por **dos** motivos distintos — el tracker no tiene el campo (degradación declarada, sitio 6) o el ticket ADO simplemente no tiene criterios cargados (que **no** es una degradación de capacidad, es un ticket incompleto). Sin el guard se declararían falsos positivos sobre proyectos ADO y el KPI se inflaría con ruido. **Este guard es obligatorio.**

**F3.2 — `capability="tracker.acceptance_criteria"` no existe hoy en `CAPABILITY_MATRIX`.** Hay dos caminos y hay que elegir **uno** y escribirlo:

- **Elegido:** usar la clave lógica `"tracker.acceptance_criteria"` **sin** agregarla a `CAPABILITY_MATRIX`.
- **Motivo:** agregar una key cambia `len(CAPABILITY_KEYS)` de 71 a 72, y `render_markdown_matrix()` (`provider_capabilities.py:364`) genera el documento de paridad a partir de esa lista, que `test_plan218_capability_matrix.py::test_doc_de_paridad_esta_sincronizado` exige idéntico al `.md` versionado. Habría que **regenerar el documento de paridad** dentro de un plan que no es sobre paridad, y además declarar `evidence` para la nueva key en los dos proveedores (lo exige `test_full_y_partial_exigen_evidencia`). **Fuera de scope** (§6).
- ⚠️ **Ojo con el criterio:** `test_plan218_capability_matrix.py` **ya está rojo de fábrica** (**2 failed, 8 passed**, §5.1) y **esos dos rojos son exactamente esos dos tests**. O sea: no se puede usar "el test pasa" como criterio acá. El criterio correcto es **delta cero** — el archivo tiene que seguir en 2 failed / 8 passed. Si al terminar tiene 3 failed, este plan rompió algo.
- **Consecuencia que F4 DEBE manejar:** el aviso de la interfaz va a recibir una `capability` que **no está** en la matriz. Ver §F4.3 — es exactamente el caso "capacidad desconocida" que el plan exige testear.

**F3.3 — Tests.** El caso 2 de `test_plan290_degradacion_declarada.py` (F0) pasa a verde. Más, en `Stacky Agents/backend/tests/test_plan290_self_review_no_regresion.py`:

| Caso | Afirma |
|---|---|
| `test_el_retorno_no_cambio` | `result.score == 1.0`, `result.checklist == []`, `result.skipped_reason == "no_acceptance_criteria"`. |
| `test_proyecto_ado_sin_criterios_no_declara` | Proyecto ADO + criterios vacíos: retorno idéntico y **sin** clave `capability_degraded`. Es el sentinela que impide el falso positivo de F3.1. |
| `test_flag_apagada_no_declara` | `ruteo_estricto_por_tracker()` falso ⇒ no declara. |
| `test_declarar_falla_y_el_review_sigue` | Con `capability_degradation.declarar` parcheado para levantar: `review_artifact` devuelve el resultado normal. Prueba el riel "nunca levanta". |

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_self_review_no_regresion.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_degradacion_declarada.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_u1_self_review.py" -q
```

> ⚠️ El archivo de tests del servicio se llama **`test_u1_self_review.py`**, no `test_self_review.py` (ese **no existe** y `pytest` sale con exit 4, que parece "sin fallos"). Ver §5.1.

**Criterio binario:** archivo nuevo **4 passed**; `test_plan290_degradacion_declarada.py` pasa de **2 failed** (F0) a **2 passed**; `test_u1_self_review.py` en **2 passed** (baseline §5.1), sin editarlo.

**Flag:** ninguna. **Impacto por runtime:** los 3, por el punto único `review_artifact` (§3.2). **Fallback:** `declarar` devuelve `False` y el review sigue igual.
**Trabajo del operador: ninguno.**

**Ratchets:** registrar `tests/test_plan290_self_review_no_regresion.py` en los dos (§F0.1).

---

### F4 — El aviso llega a la interfaz

**Objetivo:** que el operador vea, en el detalle de la ejecución, qué capacidad se degradó y por qué.

**Restricción dura:** **RTL/jsdom no están instalados y vitest de componentes tampoco.** Toda la lógica va en `.ts` puro y el `.tsx` solo pinta. **No propongas ni escribas tests de componentes.** El único gate del frontend es `npx tsc --noEmit` con **0 errores**.

**F4.1 — Modelo puro (archivo nuevo):** `Stacky Agents/frontend/src/services/capabilityDegradedModel.ts`

```typescript
export interface DegradacionDeclarada {
  capability: string;
  reason: string;
  provider: string;
  site: string;
  at: string;
}

/** Lee metadata.capability_degraded de forma DEFENSIVA. Nunca lanza.
 *  Una metadata sin la clave, con la clave en null, o con un valor que no es
 *  array, devuelve []. Las entradas que no son objeto se descartan. */
export function leerDegradaciones(metadata: Record<string, unknown> | null | undefined): DegradacionDeclarada[];

/** Etiqueta legible. Una capacidad DESCONOCIDA devuelve la key cruda,
 *  NUNCA undefined ni "". Mismo criterio que statusLabel de parityMatrixModel. */
export function etiquetaDeCapacidad(capability: string): string;

/** Agrupa por provider, preservando orden de llegada. */
export function agruparPorProveedor(items: DegradacionDeclarada[]): Array<[string, DegradacionDeclarada[]]>;
```

**Diccionario de etiquetas — cerrado y con default explícito:**

```typescript
const ETIQUETAS: Record<string, string> = {
  "tracker.comments.list": "Lectura de comentarios del tracker",
  "tracker.acceptance_criteria": "Criterios de aceptación",
};
export function etiquetaDeCapacidad(capability: string): string {
  return ETIQUETAS[capability] ?? capability;   // ?? y NO ||: "" no debe caer al default
}
```

**F4.2 — Componente (archivo nuevo):** `Stacky Agents/frontend/src/components/AvisoDegradacionPanel.tsx`

- Recibe `metadata: Record<string, unknown>` (el drawer ya lo tiene como `Record<string, unknown>` en `ExecutionDetailDrawer.tsx:74`).
- Si `leerDegradaciones(metadata).length === 0` → **devuelve `null`**. No se monta, no ocupa espacio, no cambia el layout de ninguna ejecución existente.
- Sigue el patrón exacto de los vecinos del drawer (`metadata.egress_sentinel` en `:198`, `metadata.local_insight` en `:189`).
- **Estilos:** un `.module.css` propio usando **solo tokens del tema**. Los tokens que existen son `--accent`, `--success`, `--danger`, `--border`, `--text-primary`, `--bg-panel`. **`--color-*` NO existe** y **el ratchet de UI prohíbe hex crudos** — un `#RRGGBB` en el CSS pone el ratchet en rojo.
- **No es solo color:** cada fila lleva un ícono/marca además del color (mismo criterio de accesibilidad que `statusMark` en `parityMatrixModel.ts:81`).

**F4.3 — Montaje:** en `Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx`, junto a los otros paneles alimentados por `metadata`, pasando `metadata={metadata}`. **No se toca `DiagnosticsPage.tsx` ni `ParityMatrixPanel.tsx`.**

> ⚠️ **Capacidad desconocida — el caso que el plan exige.** Como F3.2 emite `"tracker.acceptance_criteria"`, que **no** está en `CAPABILITY_MATRIX` ni (si nadie la agrega) en `ETIQUETAS`, el camino "desconocido" **es el camino normal desde el día uno**, no un borde teórico. Por eso `etiquetaDeCapacidad` devuelve la key cruda en vez de `undefined`: la fila se pinta con el texto `tracker.acceptance_criteria` y el `reason`, que igual es informativo. **Un `Record` sin default haría que React renderice vacío y el aviso quedaría mudo — exactamente el defecto que este plan viene a arreglar, reintroducido en la capa de arriba.**

**F4.4 — Tests (lógica pura, con vitest sobre `.ts`):** `Stacky Agents/frontend/src/services/__tests__/capabilityDegradedModel.test.ts`

| Caso | Afirma |
|---|---|
| `metadata` sin la clave | `[]` |
| `capability_degraded: null` | `[]` |
| `capability_degraded: "texto"` (no array) | `[]` |
| array con una entrada válida y una `null` | devuelve **1** entrada |
| capacidad conocida | etiqueta traducida |
| **capacidad desconocida** | **devuelve la key cruda, no `undefined` ni `""`** |
| `etiquetaDeCapacidad("")` | devuelve `""`, no el default (prueba el `??` frente a `||`) |

```
cd "Stacky Agents/frontend" && npx vitest run "src/services/__tests__/capabilityDegradedModel.test.ts"
```

> ⚠️ `npx vitest run <ruta inexistente>` **sale 1 pero pipeado se pierde el exit code**, y un `.test.tsx` con RTL reporta "no tests" con **exit 0**. Verificá que la salida diga explícitamente **7 passed** y que el archivo sea `.ts` (no `.tsx`).

**Criterio binario, dos comandos:**

```
cd "Stacky Agents/frontend" && npx tsc --noEmit          # 0 errores, exit 0
cd "Stacky Agents/frontend" && npx vitest run "src/services/__tests__/capabilityDegradedModel.test.ts"   # 7 passed
```

**Flag:** ninguna. El aviso solo aparece si hay dato; sin dato no se monta.
**Impacto por runtime:** ninguno (es interfaz; lee metadata que los 3 escriben igual).
**Trabajo del operador: ninguno.**

---

### F5 — `STACKY_GITLAB_ENABLED` llega a la interfaz (y aplica de verdad)

**Objetivo:** que el master switch de GitLab sea una perilla de la interfaz con efecto inmediato, sin editar archivos a mano.

**F5.1 — La decisión, con su motivo escrito.**

> **DECISIÓN: `STACKY_GITLAB_ENABLED` NO se registra como `FlagSpec`. Se expone por la interfaz a través del canal que YA lo gestiona: `_MANAGED_KEYS` de `api/global_config.py`.**
>
> **Motivos, en orden de peso:**
> 1. **Ya vive ahí.** `api/global_config.py:82` la tiene en `_MANAGED_KEYS` desde el Plan 65. Registrarla además como `FlagSpec` crearía **dos escritores del mismo valor**, que es el defecto que `api/global_config.py:88-93` documenta para `LOG_LEVEL` con la frase *"UN solo escritor"*.
> 2. **El panel de flags mentiría.** Su hot-apply hace `setattr` sobre `config` y nada más. Para esta clave hace falta además persistir en `.env` (si no, se pierde al reiniciar) — el panel diría "aplicado" con persistencia a medias.
> 3. **Costo desproporcionado.** Una `FlagSpec` nueva arrastra ocho guardianes, incluido `test_requires_map_is_frozen` indexado por key, para una clave que ya tiene endpoint.
> 4. **`api/harness_flags.py:134` ya dejó escrita esta misma decisión** ("NO vive en este registro"). Este plan la respeta, no la revierte.
>
> **Su default en código NO se toca.** `config.py:1298` sigue en `"false"`. Motivo: GitLab exige instancia + token que no existen en una instalación limpia; encenderlo por default haría fallar el arranque de cualquier instalación nueva. **El `.env` del operador, que hoy tiene `STACKY_GITLAB_ENABLED=true` (`backend/.env:7`), no se modifica**: el `.env` gana sobre el default de código y el operador sigue exactamente como está hoy. Este plan **no cambia el comportamiento de ninguna instalación existente**.

**F5.2 — El hot-apply que falta (backend).** Archivo: `Stacky Agents/backend/api/global_config.py`, dentro de `put_global_config` (`:190`), con el mismo idioma que `api/projects.py:141-142`:

```python
# Plan 290 F5 — `_write_env` actualiza .env y os.environ, pero NO el singleton
# `config.config`, que es de donde leen tracker_provider.py:133, ci_provider.py:121,
# ci_variables.py:87, ci_preflight.py:39 y ci_logs_provider.py:38. Sin este
# setattr la interfaz diría "guardado" y el motor seguiría con el valor viejo
# hasta reiniciar: un falso verde.
if "STACKY_GITLAB_ENABLED" in updates:
    import config as _config
    setattr(
        _config.config,
        "STACKY_GITLAB_ENABLED",
        updates["STACKY_GITLAB_ENABLED"].strip().lower() in ("1", "true", "yes"),
    )
```

> El parseo replica **exactamente** el de `config.py:1297-1299` (`.lower() in ("1","true","yes")`). No inventes otro conjunto de valores verdaderos: `"on"` **no** está y agregarlo divergiría del arranque.

**F5.3 — El panel (frontend).** Archivo nuevo `Stacky Agents/frontend/src/components/GitlabEngineSwitch.tsx`, **calcado de `LogLevelPanel.tsx`**: `useState` + `useEffect` que lee del GET, un control, y mensajes de ok/error. Se monta en `DiagnosticsPage.tsx` **inmediatamente después de `<LogLevelPanel />`** (hoy en `:328`; anclá por el símbolo `<LogLevelPanel />`, no por el número).

- Lógica pura en `Stacky Agents/frontend/src/services/gitlabEngineModel.ts`: normalización del valor que llega del GET (que es un **string** del `.env`, no un bool) a `boolean`, con la MISMA tabla que el backend.
- Endpoints en `frontend/src/api/endpoints.ts`: reusar `api.get`/`api.put` sobre `/api/global-config` (ya existen en `:3392` y `:2371`).
- **Aviso en la interfaz** cuando se apaga: los proyectos GitLab van a empezar a fallar con `TrackerConfigError`. Texto explícito, no un toggle mudo.

**F5.4 — Tests.**

Backend, archivo nuevo `Stacky Agents/backend/tests/test_plan290_gitlab_switch_ui.py`:

| Caso | Afirma |
|---|---|
| `test_put_enciende_y_aplica_en_caliente` | Tras el PUT con `"true"`, `config.config.STACKY_GITLAB_ENABLED is True` **y** el `.env` de prueba contiene la línea. **Los dos, en el mismo test.** |
| `test_put_apaga_y_aplica_en_caliente` | Ídem con `"false"` → `is False`. |
| `test_get_devuelve_la_clave` | El GET incluye `STACKY_GITLAB_ENABLED`. |
| `test_valor_basura_no_enciende` | `"quizas"` → `is False` (no truthy por ser string no vacío). |

> ⚠️ El test **debe** apuntar `_ENV_PATH` a un archivo temporal (monkeypatch). **Está prohibido que un test escriba el `.env` real del operador.**

Frontend: `Stacky Agents/frontend/src/services/__tests__/gitlabEngineModel.test.ts` — `"true"`/`"1"`/`"yes"` → `true`; `"false"`/`""`/`"quizas"`/`undefined` → `false`.

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_gitlab_switch_ui.py" -q
cd "Stacky Agents/frontend" && npx vitest run "src/services/__tests__/gitlabEngineModel.test.ts"
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio binario:** backend **4 passed**; frontend **7 passed**; `tsc` **0 errores**.

**Flag:** ninguna nueva. **Impacto por runtime:** ninguno (configuración, no ejecución).
**Trabajo del operador: ninguno.** Su `.env` actual sigue igual y el switch aparece ya reflejando `true`.

**Ratchets:** registrar `tests/test_plan290_gitlab_switch_ui.py` en los dos (§F0.1).

---

### F6 — `base_url` se normaliza también del lado del servidor

**Objetivo:** que un `base_url` con namespace pegado quede normalizado aunque no pase por el formulario.

**Archivo:** `Stacky Agents/backend/project_manager.py` (raíz del backend, **no** `services/`), línea **670**.

```python
# ANTES
"base_url":  url.rstrip("/"),

# DESPUÉS
"base_url":  _normalizar_base_url_gitlab(url),
```

**Función nueva** en el mismo archivo — puerto exacto de `normalizeGitlabUrl` (`frontend/src/projects/newProjectGitlabModel.ts:39`):

```python
_RE_API_V = re.compile(r"/api/v[0-9]+$", re.IGNORECASE)
_RE_ORIGEN = re.compile(r"^(https?://[^/]+)(/.*)?$", re.IGNORECASE)

def _normalizar_base_url_gitlab(raw: str) -> str:
    """Plan 290 F6 — puerto server-side de normalizeGitlabUrl.

    Deja SOLO el origen: saca barras finales, un /api/vN pegado y cualquier path.
    Un valor sin esquema se devuelve limpio de barras finales y nada más: acá no
    corresponde inventar un origen (el formulario ya lo rechaza antes).
    """
    limpio = _RE_API_V.sub("", (raw or "").strip().rstrip("/"))
    m = _RE_ORIGEN.match(limpio)
    return m.group(1) if m else limpio
```

**Tabla de equivalencia obligatoria (mismo input → mismo output que el cliente):**

| Entrada | Salida |
|---|---|
| `https://gitlab.com` | `https://gitlab.com` |
| `https://gitlab.com/` | `https://gitlab.com` |
| `https://gitlab.com///` | `https://gitlab.com` |
| `https://gitlab.com/api/v4` | `https://gitlab.com` |
| `https://gitlab.com/api/v4/` | `https://gitlab.com` |
| `https://git.interno/grupo/proyecto` | `https://git.interno` |
| `https://git.interno:8443/grupo/proyecto` | `https://git.interno:8443` |
| `HTTP://GitLab.com/API/V4` | `HTTP://GitLab.com` |
| `""` | `""` |
| `gitlab.com/grupo` | `gitlab.com/grupo` (sin esquema: no se inventa origen) |

> ⚠️ Ojo con el orden: hay que sacar la barra final **antes** de intentar el `/api/vN`, porque `https://host/api/v4/` no matchea `/api/v[0-9]+$` con la barra puesta. El pseudocódigo de arriba ya lo hace (`.rstrip("/")` dentro del `sub`).

**Tests:** `Stacky Agents/backend/tests/test_plan290_base_url_normalizada.py` — un caso por fila (10 casos), más un caso de **paridad declarada**: un test que lista los mismos 10 pares y afirma que la tabla del test coincide con la del docstring, para que el día que el cliente cambie se vea la divergencia.

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_base_url_normalizada.py" -q
```

**Criterio binario:** **11 passed**.

**Flag:** ninguna. Es una corrección de normalización sin superficie configurable.
**Impacto por runtime:** ninguno (alta/edición de proyecto, no ejecución).
**Trabajo del operador: ninguno.** Los proyectos ya creados **no se migran** (§6): la función solo actúa al escribir.

**Ratchets:** registrar `tests/test_plan290_base_url_normalizada.py` en los dos (§F0.1).

---

### F7 — Las 23 descripciones que mienten, y el guardián que impide la 24

**Objetivo:** que ninguna descripción de flag afirme un default que el código contradice, para siempre.

**F7.1 — Re-medir antes de tocar.** Correr el script de §2.4 (reproducible: AST sobre `harness_flags.py` + regex sobre `config.py`). Si el conteo **no** da 23, las líneas se movieron: re-generá la tabla, **no** edites por número de línea.

**F7.2 — Corregir el TEXTO y solo el texto.** En `Stacky Agents/backend/services/harness_flags.py`, para cada una de las 23: reemplazar la afirmación falsa (`Default OFF.`, `Privacidad: default OFF.`, etc.) por la verdadera (`Default ON.`).

> ⚠️ **Prohibido cambiar `default=`, `key`, `type`, `group`, `requires`, `env_only`, `min_value`, `max_value`.** Este plan **no** cambia el comportamiento de ninguna flag. Si al leer una descripción te parece que la conducta correcta sería OFF, **no la apagues**: anotalo en el commit y dejalo para el operador. Apagar una flag que hoy está ON es un cambio de comportamiento no solicitado que puede tumbar funcionalidad viva.
>
> ⚠️ **`STACKY_TRACE_PROMPT_TEXT_ENABLED` merece una línea aparte.** Su texto promete *"Privacidad: default OFF"* y está **ON**: hoy el texto completo del prompt se está escribiendo en la metadata. La corrección de texto **dice la verdad pero no arregla la privacidad**. En la misma edición, agregá a su descripción una frase explícita del tipo *"Hoy nace ON: el texto completo del prompt SÍ queda en la metadata. Apagala si el contenido de tus prompts es sensible."* — para que la perilla sea una decisión informada del operador y no una sorpresa. **No la apagues vos** (§5, R6).

**F7.3 — El guardián (archivo nuevo):** `Stacky Agents/backend/tests/test_plan290_defaults_no_mienten.py`

```python
def test_ninguna_descripcion_contradice_su_default():
    """KPI K2. Recorre TODAS las FlagSpec por AST y cruza el texto contra el
    default efectivo (FlagSpec.default y la entrada de config.py)."""
```

**Diseño del gate — los tres moldes de gate muerto, evitados a propósito:**

- **(a) centinela sobre un símbolo que una fase posterior borra** → no aplica: recorre `FlagSpec` genéricamente, no una key concreta. Ninguna fase de este plan borra `FlagSpec`.
- **(b) test estático sobre un defecto de ejecución** → acá el defecto **es** estático (una discrepancia texto↔código), así que un análisis del fuente es la herramienta correcta. Se hace por **AST**, no por regex sobre el archivo entero: una `FlagSpec` alcanzada por alias o con la descripción partida en varias líneas debe contarse igual.
- **(c) `assert` de ausencia suelto** → el test afirma **las dos cosas en la misma función**: que el barrido encontró **≥ 400 `FlagSpec`** (o sea, que efectivamente parseó algo — hoy son 490) **y** que la lista de contradicciones está vacía. Sin la primera mitad, un parser roto que devuelve cero flags daría verde eterno.

```python
    assert len(flags) >= 400, f"el barrido solo vio {len(flags)} FlagSpec: el parser se rompió"
    assert contradicciones == [], f"descripciones que mienten: {contradicciones}"
```

**¿Qué tiene que pasar para que se ponga rojo, y ese escenario sigue existiendo después de la última fase?** Sí: alcanza con que alguien escriba una `FlagSpec` nueva con `default=True` y `"Default OFF"` en la descripción — el caso más común del repo, 23 veces cometido. El gate se prueba **contra el defecto**: antes de F7.2 el test debe dar **1 failed** listando las 23; después, **1 passed**.

```
# ANTES de F7.2 (obligatorio, pegar la salida en el commit):
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_defaults_no_mienten.py" -q   # 1 failed, con las 23 en el mensaje
# DESPUÉS de F7.2:
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_defaults_no_mienten.py" -q   # 1 passed
```

**F7.4 — Las suites que este cambio puede mover.** Editar `harness_flags.py`, aunque sea solo texto, toca un archivo que vigilan varias suites. Correr **cada una por separado** y comparar contra el baseline de §5.1:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flags_env_read_meta.py" -q
```

**Criterio binario:** el guardián en **1 passed**, y las tres suites de arriba con **exactamente el mismo conteo de passed/failed que en el commit base** — criterio **delta cero**, no absoluto: varias están rojas de fábrica por deuda ajena (§5.1).

**Flag:** ninguna. **Impacto por runtime:** ninguno (texto de descripciones).
**Trabajo del operador: ninguno.** (Queda para él **una decisión informada** sobre `STACKY_TRACE_PROMPT_TEXT_ENABLED`, que este plan **declara** pero no ejecuta — §7.)

**Ratchets:** registrar `tests/test_plan290_defaults_no_mienten.py` en los dos (§F0.1).

---

### F8 — Documentación, métrica y barrido de no-regresión

**F8.1 — Documentación del sistema.** Actualizar `Stacky Agents/docs/sistema/` con una sección "Degradación declarada": qué es `metadata["capability_degraded"]`, las cinco claves de la forma canónica, los dos sitios instrumentados, y **la lista explícita de los seis que quedaron fuera y por qué** (§6). Un `.md` en `docs/sistema/` entra al corpus RAG; escribilo pensando en que un agente lo va a recuperar.

**F8.2 — El script de la métrica K1.** `Stacky Agents/backend/scripts/medir_degradacion_declarada.py`, **solo lectura**:

- Cuenta ejecuciones con `metadata["capability_degraded"]` no vacío, sobre el total de ejecuciones de proyectos no-ADO posteriores al despliegue del plan.
- Imprime `declaradas / candidatas = N %`.
- ⚠️ **Abre la base en modo lectura y NUNCA escribe.** La base viva es `Stacky Agents/backend/data`. Para medir en desarrollo, **copiar** el archivo al directorio temporal y medir sobre la copia.

**F8.3 — Barrido de no-regresión.** Correr, **por archivo**, todas las suites que las fases tocaron o vecinan, y comparar contra §5.1:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_business_preflight.py" -q            # 12 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_u1_self_review.py" -q                # 2 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q                 # 59 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q            # 4 failed, 4 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flags_env_read_meta.py" -q           # 1 failed, 1 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q     # 2 failed, 8 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_coupling_ratchet.py" -q      # 3 failed, 7 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan289_contexto_por_tracker.py" -q  # 34 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan289_stat_de_contexto.py" -q      # 6 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan281_ruteo_por_tracker.py" -q     # 13 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan281_sitios_ado_only.py" -q       # 18 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan281_ratchet_ado_only.py" -q      # 11 passed
cd "Stacky Agents/frontend" && npx tsc --noEmit                                                                                   # 0 errores
```

> **`pytest tests` entero NO es un veredicto.** La suite completa da miles de errores por contaminación cruzada. Cualquier criterio basado en correrla es inválido.

> **`test_plan281_sitios_ado_only.py` (18 passed) es el más importante de este barrido:** es el que vigila los ocho guards que este plan instrumenta. Si F2 o F3 lo mueven, tocaste el `return` en vez de agregar una línea antes.

**Criterio binario:** cada suite con **exactamente el conteo comentado arriba** (= §5.1) y `tsc` en **0 errores**.

**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

### 5.1 Baselines — hay SEIS suites rojas de fábrica; todo criterio es DELTA

**Regla dura para todas las fases: los criterios se comparan contra el conteo del commit base, nunca contra "0 failed".** Varias suites de este repo están rojas por deuda ajena y una fase que las deje igual de rojas **cumple**.

**Baseline MEDIDO el 2026-08-02** sobre `docs/plan-279`, cada archivo por separado con
`"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "<ruta>" -q --no-header -p no:cacheprovider`:

| Suite | Baseline medido | Rojo de fábrica | Criterio de este plan |
|---|---|---|---|
| `tests/test_harness_flags.py` | **59 passed** | no | delta cero |
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** | **sí** | delta cero |
| `tests/test_flags_env_read_meta.py` | **1 failed, 1 passed** | **sí** | delta cero |
| `tests/test_plan218_coupling_ratchet.py` | **3 failed, 7 passed** | **sí** | delta cero |
| `tests/test_plan218_capability_matrix.py` | **2 failed, 8 passed** | **sí** | delta cero |
| `tests/test_business_preflight.py` | **12 passed** | no | delta cero y **sin editar el archivo** |
| `tests/test_u1_self_review.py` | **2 passed** | no | delta cero y **sin editar el archivo** |
| `tests/test_plan289_contexto_por_tracker.py` | **34 passed** | no | delta cero |
| `tests/test_plan289_stat_de_contexto.py` | **6 passed** | no | delta cero |
| `tests/test_plan281_ruteo_por_tracker.py` | **13 passed** | no | delta cero |
| `tests/test_plan281_sitios_ado_only.py` | **18 passed** | no | delta cero |
| `tests/test_plan281_ratchet_ado_only.py` | **11 passed** | no | delta cero |
| `npx tsc --noEmit` (frontend) | **0 errores** | no | **0 errores** (gate absoluto, es el único) |

> ⚠️ **`tests/test_self_review.py` NO EXISTE.** El archivo de tests del servicio `services/self_review.py` es **`tests/test_u1_self_review.py`**. Un `pytest tests/test_self_review.py` sale con **exit 4** (`file or directory not found`), que es fácil de confundir con "no hay fallos". Usá el nombre correcto.

**Los 10 rojos de fábrica, por nombre exacto** (son deuda ajena; **no se arreglan en este plan** y hay que descontarlos del delta):

```
test_harness_flags_help.py::test_plain_help_covers_all_registry_keys
test_harness_flags_help.py::test_plain_help_fields_non_empty_and_bounded
test_harness_flags_help.py::test_plain_help_on_off_start_with_si
test_harness_flags_help.py::test_plain_help_avoids_jargon_denylist
test_flags_env_read_meta.py::test_flags_registradas_no_se_leen_del_entorno_con_default_local
test_plan218_coupling_ratchet.py::test_ratchet_importers_no_crece
test_plan218_coupling_ratchet.py::test_ratchet_literales_no_crece
test_plan218_coupling_ratchet.py::test_ratchet_rutas_ado_no_crece
test_plan218_capability_matrix.py::test_full_y_partial_exigen_evidencia
test_plan218_capability_matrix.py::test_doc_de_paridad_esta_sincronizado
```

> **Re-medí igual antes de empezar.** La sesión paralela commitea cada pocos minutos y estos números pueden moverse. Anotá `git rev-parse HEAD` y volvé a correr la tabla; si un conteo difiere, **actualizá la tabla en el commit de F0** y usá ese número como baseline. Lo que no se acepta es comparar contra "0 failed": cuatro de estas suites nunca llegan a cero.

### 5.2 Riesgos, uno por uno

| # | Riesgo | Mitigación |
|---|---|---|
| **R1** | El implementador "arregla" las degradaciones y cambia semántica. | §1.2 con aviso destacado, y un test de no-regresión por sitio que fija el valor neutro exacto (§F2.5, §F3.3). |
| **R2** | `declarar()` levanta y tumba una corrida. | `try/except` total en F1 + test `test_declarar_falla_y_el_review_sigue` (§F3.3), que parchea la función para que levante. |
| **R3** | Falsos positivos: se declara degradación en proyectos ADO. | El guard `tracker_is_azure_devops(...) and ruteo_estricto_por_tracker()` se repite en F3.1, con sentinela negativo dedicado (`test_proyecto_ado_sin_criterios_no_declara`). |
| **R4** | La interfaz no renderiza una capacidad desconocida. | `etiquetaDeCapacidad` devuelve la key cruda; y como F3.2 emite una key **fuera** de la matriz, ese camino es el normal desde el día uno, no un borde. Test dedicado en §F4.4. |
| **R5** | El toggle de GitLab dice "guardado" y el motor no cambia. | F5.2 agrega el `setattr` sobre el singleton, y el test lo afirma **junto con** la persistencia en el `.env` temporal, en la misma función. |
| **R6** | Apagar por error una de las 23 flags al corregir su texto. | F7.2 prohíbe explícitamente tocar cualquier campo que no sea `description=`. El gate de F7.3 **no** mira los defaults: mira la coherencia texto↔código, así que apagar una flag para "cumplir" el test también lo pondría verde — por eso la prohibición es textual y el revisor debe mirar el `git diff` de `harness_flags.py` y confirmar que **solo** hay cambios dentro de strings de `description`. |
| **R7** | `STACKY_TRACE_PROMPT_TEXT_ENABLED` está ON y filtra prompts completos a la metadata. | Este plan **declara** el hecho en la descripción (F7.2) y **no** cambia la conducta. Queda como decisión del operador (§7), porque apagarla es un cambio de comportamiento fuera del alcance. |
| **R8** | La sesión paralela pisa los mismos archivos. | Está viva y commitea cada pocos minutos; `api/agents.py`, `services/project_context.py` y `frontend/src/pages/*` figuran sucios. **Antes de cada commit: `git status --short`, y commitear con pathspec explícito** (`git commit -- "<ruta>"`). **Nunca** `amend`, `reset`, `rebase`, `stash` ni `checkout`. |
| **R9** | Los ratchets se ponen rojos al agregar 6 archivos de tests. | Registro **por fase, en el commit que crea el archivo** (§F0.1), en **los dos** archivos, anclando por símbolo, sin rutas con espacios, y sacando del allowlist si estuviera. |
| **R10** | `execution_id` no está en el scope de `context_enrichment.py:1288`. | §F2.4 lo declara como incertidumbre a verificar, con salida explícita: pasar `None` y documentarlo. **F3 sostiene el KPI por sí solo**, así que el plan no depende de que F2.4 salga bien. |
| **R11** | Un test escribe en la base o el `.env` reales. | F5.4 exige monkeypatch de `_ENV_PATH`; F8.2 exige copia read-only. Un pytest suelto **sí** escribe en la base viva de este repo. |

---

## 6. Fuera de scope (con motivo)

**Los seis sitios de degradación que NO se instrumentan en este plan:**

| Sitio | Motivo de la exclusión |
|---|---|
| `api/agents.py:1921` (`_build_ado_enrichment_sections`) | No tiene `execution_id` en el scope y su llamador (`:1687`) tampoco de forma directa. Requeriría plomería nueva por varias capas — el defecto de alcance que hundió planes anteriores. |
| `api/tickets.py:5111` (`_equivalent_task_status`) | Es un **closure** dentro de un handler, sin `execution_id`, y su propio comentario lo declara *"guard COSMÉTICO para el gate: la función ya está funcionalmente protegida"*. Bajo daño. |
| `api/tickets.py:7762` (`System.Rev`) | Degrada un sellado de aprendizaje bidireccional (Plan 60 F1), no una capacidad que el operador espere. Bajo daño. |
| `services/acceptance_criteria.py:43` | Gemelo funcional de `self_review`, pero **ninguno de sus llamadores tiene `execution_id`**. F3 ya cubre el mismo hecho de negocio ("no hay criterios de aceptación en este tracker") desde el punto donde el dato existe. Instrumentar los dos duplicaría la entrada. |
| `services/similar_tickets.py:122` | Devuelve `[]`, que es indistinguible de "no hubo coincidencias" — un resultado legítimo y frecuente. Declararlo generaría ruido de alta frecuencia y bajo valor. Sin `execution_id` además. |
| `services/ticket_assigner.py:401` | Devuelve `None` y ya loguea en `debug`. Sin `execution_id`. Bajo daño: el ticket queda sin asignar, que es visible en el propio tracker. |

> **Por qué se acotó a dos y no "los 8, y si falta alguno se agrega":** un criterio así es **alcance infinito con forma de criterio binario** y no se puede declarar cumplido. Los dos elegidos son los únicos donde el destino (`execution_id`) está al alcance sin cambiar firmas públicas, y son los de mayor daño (`ok=True` que se lee como "validado"; `score=1.0` que se lee como "revisado"). **Los otros seis quedan documentados en F8.1 como deuda conocida**, no como olvido.

**Otras exclusiones explícitas:**

- **No se agrega `tracker.acceptance_criteria` a `CAPABILITY_MATRIX`** (motivo técnico completo en §F3.2: rompería `test_plan218_capability_matrix.py` y arrastraría regenerar el documento de paridad).
- **No se migran los `base_url` ya guardados.** F6 normaliza al escribir; los proyectos existentes se corrigen solos la próxima vez que se guarden. Una migración masiva sobre configuraciones del operador exige human-in-the-loop y es un plan aparte.
- **No se apaga ninguna flag**, incluida `STACKY_TRACE_PROMPT_TEXT_ENABLED` (§R7).
- **No se toca `ParityMatrixPanel` ni `DiagnosticsPage`** salvo el montaje de una línea en F5.3.
- **No se cambia el default de `STACKY_GITLAB_ENABLED` en `config.py`** (§F5.1).
- **No se muestra `metadata["ado_context"]`** (el stat que persiste el Plan 289) en la interfaz, pese a que se verificó que tiene **cero** consumidores en `frontend/src/`. Es un hallazgo real pero es alcance del 289, no de este plan.

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **Degradación** | Stacky decide **a propósito** no ejecutar una capacidad porque el tracker del proyecto no la tiene, y devuelve un valor neutro. **No es un error.** |
| **Valor neutro** | El retorno que la función da cuando degrada (`""`, `[]`, `None`, `"unknown"`, `ok=True/mode=None`). **Nunca se modifica en este plan.** |
| **Sitio** | Uno de los ocho guards del Plan 281 F7. Se identifica por **símbolo** (`business_preflight.evaluate`), nunca por `archivo:línea`. |
| **Declarar** | Anotar la degradación en `metadata["capability_degraded"]` de la fila `AgentExecution`. Solo lectura hacia afuera; una escritura local. |
| **Delta cero** | Criterio de aceptación en el que una suite debe terminar con **el mismo** conteo de passed/failed que en el commit base, no con cero fallos. |
| **Rojo de fábrica** | Suite que ya falla antes de tocar nada, por deuda de otro plan. Se mide, se registra y **no se arregla acá**. |

### 7.2 Orden de implementación

```
F0  (centinelas ROJOS)  →  F1  (registro)  →  F2  (business_preflight)  →  F3  (self_review)  →  F4  (interfaz)
                                                                                                    │
F5 (switch GitLab) ── F6 (base_url) ── F7 (23 descripciones) ─── independientes entre sí ────────────┤
                                                                                                    ▼
                                                                                            F8 (docs + métrica)
```

- **F0 → F1 → F2 → F3 → F4** es la cadena obligatoria: F4 no tiene qué mostrar sin F2/F3, y F2/F3 no tienen dónde escribir sin F1.
- **F5, F6 y F7 son independientes** entre sí y del resto: se pueden hacer en cualquier orden, incluso antes que F0. Si el presupuesto se corta, **cada una entrega valor sola**.
- **F8 va última** porque documenta lo que quedó construido y mide el KPI.

Un commit por fase. Mensaje: `feat(plan-290): F<n> — <qué hace>` (o `test(plan-290): F0 — ...`, `docs(plan-290): F8 — ...`).

### 7.3 Definition of Done

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Los centinelas de F0 se vieron **rojos** antes de F1, con salida pegada en el commit | Salida de pytest en el mensaje del commit de F0, **2 failed**, sin `ImportError` |
| 2 | `test_plan290_degradacion_declarada.py` en **2 passed** tras F3 | comando §F3.3 |
| 3 | `test_plan290_registro_degradacion.py` en **8 passed** | comando §F1 |
| 4 | `test_plan290_preflight_no_regresion.py` en **5 passed** | comando §F2.5 |
| 5 | `test_plan290_self_review_no_regresion.py` en **4 passed** | comando §F3.3 |
| 6 | `test_plan290_gitlab_switch_ui.py` en **4 passed** | comando §F5.4 |
| 7 | `test_plan290_base_url_normalizada.py` en **11 passed** | comando §F6 |
| 8 | `test_plan290_defaults_no_mienten.py`: **1 failed** antes de F7.2 (con las 23 listadas) y **1 passed** después | comandos §F7.3, **ambas salidas** en el commit |
| 9 | **K2 = 0** flags con descripción contradictoria | ídem #8 |
| 10 | **K3**: el switch de GitLab aplica en caliente **y** persiste | test `test_put_enciende_y_aplica_en_caliente` (§F5.4) |
| 11 | **K4**: las 10 filas de la tabla de `base_url` coinciden cliente/servidor | §F6 |
| 12 | `npx tsc --noEmit` en **0 errores** | §F8.3 |
| 13 | Todas las suites de §5.1 en **delta cero** contra el baseline medido | §F8.3 |
| 14 | `test_business_preflight.py` (12 passed) y `test_u1_self_review.py` (2 passed) **sin editar** | `git diff --stat <base>..HEAD -- "<ruta>"` vacío para los dos |
| 15 | Los **7** archivos de tests nuevos registrados en **los DOS** scripts (`run_harness_tests.sh` y `.ps1`), y ambos en delta cero | §F0.1 |
| 15b | El `.ps1` sigue siendo un array válido: la que era última entrada ahora lleva coma | inspección del `git diff` de `scripts/run_harness_tests.ps1` |
| 16 | **Cero flags nuevas** en `harness_flags.py`; el único cambio ahí es dentro de strings `description=` | `git diff` de `harness_flags.py` revisado a mano |
| 17 | Ningún archivo de la sesión paralela commiteado | `git status --short` antes de cada commit + pathspec explícito |
| 18 | Documentación de F8.1 escrita, con los 6 sitios fuera de scope enumerados | inspección |

### 7.4 Pendiente del operador (no bloquea el DoD)

1. **Decidir sobre `STACKY_TRACE_PROMPT_TEXT_ENABLED`.** Está **ON** y su descripción prometía privacidad. Con F7 la descripción dice la verdad; apagarla o no es decisión del operador (human-in-the-loop). Es la única acción que este plan le deja, y es **informativa**, no un trabajo que el plan haya creado.
2. **Smoke visual** del aviso de F4 y del switch de F5 con un proyecto GitLab real.

---

## 8. Restricciones no negociables (recordatorio para el implementador)

1. **3 runtimes con paridad** — verificada archivo por archivo en §3.2, no asumida. Fallback explícito: `declarar()` devuelve `False` sin `execution_id`.
2. **Cero trabajo extra al operador** — declarado fase por fase.
3. **Toda flag nueva nace ON** salvo que queme tokens en reposo o escriba en un sistema real. **Este plan no registra ninguna flag nueva** y explica por qué (§3.1).
4. **Human-in-the-loop** — nada decide por el operador.
5. **Mono-operador sin auth real** — no hay RBAC; `403` = flag apagada, no permiso.
6. **No degradar** performance, seguridad, estabilidad ni DX. Backward-compatible.
7. **Reusar lo existente** — `CAPABILITY_MATRIX`, `ParityMatrixPanel`, `persistir_stats_de_contexto` (como idioma), `tracker_efectivo_de_ticket`, `LogLevelPanel` (como patrón), `_MANAGED_KEYS`.
8. **Nada de vaguedad.** Si al implementar encontrás una ambigüedad que este documento no resuelve, **paralo y reportala** — no la resuelvas inventando.

---

## 9. Tabla de anclajes verificados (2026-08-02)

Todos los anclajes de este documento fueron abiertos y verificados. Los que llegaron en el encargo y estaban mal, corregidos:

| Anclaje del encargo | Estado | Anclaje real verificado |
|---|---|---|
| `services/business_preflight.py:94` | **OK** | `:94` — el `if` del guard |
| `services/similar_tickets.py:122` | **OK** | `:122` |
| `services/ticket_assigner.py:400` | **OK (±1)** | `:400` abre el `if`, `:401` la condición |
| `services/acceptance_criteria.py:42` | **OK (±1)** | `:42` abre el `if`, `:43` la condición |
| `services/self_review.py:56` | **OK (±1)** | `:56` abre el `if`, `:57` la condición |
| `api/agents.py:1920` | **±1** | `:1921` (comentario del sitio en `:1911`) |
| `api/tickets.py:4944` | **INCORRECTO** | El sitio real es **`:5111`**. `:4944` es validación de esquema de `pending-task.json`, nada que ver. |
| `api/tickets.py:7595` | **INCORRECTO** | El sitio real es **`:7762`**. `:7595` es el rescate de artefactos (`artifact_rescue`). |
| `config.py:1297-1299` | **OK** | `os.getenv("STACKY_GITLAB_ENABLED", "false")` |
| `backend/.env:7` | **OK** | `STACKY_GITLAB_ENABLED=true` |
| `api/projects.py:141-142` | **OK** | `_write_global_env` + `setattr` |
| `harness_flags.py:4591` ("miente sobre el default") | **INCORRECTO** | `:4591` es `default=True` de `STACKY_PIPELINE_*`, cuya descripción **no** afirma OFF. Las que sí mienten son **23** y están tabuladas en §2.4. |
| `harness_flags.py:4446` ("miente sobre el default") | **INCORRECTO** | `:4446` es el `FlagSpec` de `STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC`, un `int` sin afirmación de default booleano. |
| `frontend/.../newProjectGitlabModel.ts:37` | **±2** | `:39` — `normalizeGitlabUrl`. Ruta real: `frontend/src/projects/newProjectGitlabModel.ts` (**no** `frontend/src/services/`). |
| `project_manager.py:670` | **OK** | `"base_url": url.rstrip("/")`. Ruta real: `backend/project_manager.py` (raíz del backend, **no** `services/`). |
| `services/provider_capabilities.py:200` | **≈** | `CAPABILITY_MATRIX` se define en **`:95`**; `:200` cae dentro del bloque de `gitlab`. |
| `ParityMatrixPanel.tsx:16` | **OK** | Componente en `frontend/src/components/ParityMatrixPanel.tsx` |
| `DiagnosticsPage.tsx:329` | **±2** | `<ParityMatrixPanel />` está en **`:331`**; `<LogLevelPanel />` en `:328` |
| Conteo GitLab "34/14/**22**/2" | **CORREGIDO** | Medido en proceso: **34 full / 14 partial / 21 absent / 2 n-a** = 71. ADO 38/8/25 = 71 ✓ |
| `persistir_stats_de_contexto` llamada por los 3 runtimes | **OK** | `agent_runner.py:819`, `claude_code_cli_runner.py:685`, `codex_cli_runner.py:342` |
| `tracker_efectivo_de_ticket` | **OK** | `services/project_context.py:206` |
| "`business_preflight` es mudo" | **MATIZADO** | El campo `warnings` **existe** (`:27`), **se puebla** (`:94-99`) y **`context_enrichment.py:1319` lo lee** (solo `warnings[0]`, hacia el prompt). Lo que falta es el canal hacia el **operador**. Ver §2.2. |
| "el master switch no está en la UI" | **CONFIRMADO, con matiz** | Correcto de cara al operador (**0 referencias** en `frontend/src/`), pero el seam del backend **ya existe**: `api/global_config.py:82` la tiene en `_MANAGED_KEYS`. Eso cambia el diseño de F5: no hace falta `FlagSpec`, hace falta superficie + hot-apply. |
| "`test_self_review.py`" | **NO EXISTE** | El archivo real es **`tests/test_u1_self_review.py`** (2 passed). Un pytest sobre el nombre inexistente sale **exit 4**, no 0. |
| "los ratchets" (por nombre) | **NO se llaman así** | Son `backend/scripts/run_harness_tests.sh` (array `HARNESS_TEST_FILES=(`, 820 entradas) y `run_harness_tests.ps1` (array `$HarnessTestFiles = @(`, 756 entradas). Divergen en 64. |
| "SEIS rojos de fábrica" | **CORREGIDO: son 4 ARCHIVOS / 10 TESTS** | Medidos y nombrados en §5.1. `test_harness_flags.py` **NO** es uno de ellos: da **59 passed** limpio. |
| `test_plan218_capability_matrix.py` (supuesto verde) | **ROJO DE FÁBRICA** | **2 failed, 8 passed**, y los dos rojos son justo los que citaba el argumento de §F3.2. Corregido ahí: el criterio es delta cero, no "pasa". |
| `tests/harness_ratchet_allowlist.txt` | **EXISTE** | 207 líneas (194 efectivas). **No** menciona `self_review` ni `business_preflight`. Única línea con `capability`: `tests/test_harness_capabilities.py  # pendiente-de-triage`, ajena a este plan. |
