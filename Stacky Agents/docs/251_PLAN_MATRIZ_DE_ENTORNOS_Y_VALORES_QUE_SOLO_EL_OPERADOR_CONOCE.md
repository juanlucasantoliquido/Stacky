# Plan 251 — Matriz de entornos: los valores que sólo el operador conoce

**Estado:** PROPUESTO v1
**Fecha:** 2026-07-26
**Serie:** "Mago de las Pipelines" — plan **251 de 246–252**.
**Dependencias:** consume el registro del **246** y el perfil del **247** si existen; **degrada
sin ellos** (ver §2.3). Se monta ENCIMA de la caja fuerte del **Plan 94** (`services/ci_variables.py`),
del registro de servidores del **Plan 91** (`services/server_registry.py`) y del masking común del
**Plan 195** (`services/secret_masking.py`). **No crea una segunda caja fuerte.**
**Flag:** `STACKY_PIPELINE_ENV_MATRIX_ENABLED`, default **ON**.
**Escribe:** NADA. Ni en el repo, ni en el proveedor, ni en el servidor del operador. Ver §3.2.

---

## 1. Objetivo + KPI

El operador dijo que su única responsabilidad debería ser **describir lo que necesita** y
**completar los valores específicos de cada entorno**. Los planes 243/244/250 cubren la primera
mitad. Este plan es la segunda: **enumerar, de forma determinista y sin LLM, todos los valores que
una pipeline exige para poder correr, cruzarlos contra los entornos reales de esa pipeline, y
resolverlos contra todo lo que Stacky YA sabe — para pedirle al operador únicamente lo que de
verdad falta.**

La entrega es una **matriz entorno × valor** con cuatro estados por celda
(`definido` / `default` / `falta` / `manual`) y un titular único: **"Te faltan N valores"**.
Ese N es, literalmente, todo el trabajo que le queda al operador.

**KPI (aspiracional; criterios binarios por fase en §5):**

| KPI | Medición |
|---|---|
| **KPI-1 — Cero descubrimiento por fallo** | Sobre `bootstrap-server-environment.yml` y `cd-deploy-test.yml` del corpus dorado, la matriz enumera el 100% de los valores parametrizables ANTES de correr la pipeline. Hoy el operador los descubre cuando la corrida falla. |
| **KPI-2 — Cero preguntas de más** | Ninguna celda queda en `falta` si el valor ya existe en la caja fuerte (94), en el registro de servidores (91), en el bloque `variables:`/`parameters:` del YAML, o en la allowlist de variables predefinidas de ADO. Test binario: `test_f3_no_pide_lo_que_ya_existe`. |
| **KPI-3 — Cero fuga de secretos** | El valor de un secreto no aparece NUNCA en la respuesta, ni en un log, ni en un mensaje de error. Sólo `definido`/`falta`. Test centinela: `test_f4_ningun_valor_en_la_respuesta`. |
| **KPI-4 — Entornos derivados, no inventados** | La lista de entornos sale de evidencia del YAML y del proveedor. Si el YAML no está parametrizado por entorno, la matriz muestra UNA columna `(único)` — nunca fabrica "Dev/QA/Prod". Test: `test_f2_sin_evidencia_una_sola_columna`. |
| **KPI-5 — Paridad trivial de runtimes** | 0 llamadas a LLM en las 6 fases. Grep binario en F5. |

---

## 2. Por qué ahora / gap que cierra (evidencia real leída)

### 2.1 El corpus dorado prueba el problema

**`backend/tests/fixtures/cicd_nl/golden/bootstrap-server-environment.yml`** — verificado abriendo
el archivo:

- `:38-84` — bloque `parameters:` con **8 parámetros** (`targetEnvironment`, `agentPool`,
  `component`, `skipIis`, `iisPort`, `iisHostHeader`, `seedConfigs`, `whatIf`).
- `:39-45` — `targetEnvironment` con `values: ['Test','Production']`. **Ahí están los entornos
  reales, escritos en el propio YAML.**
- `:66-69` — `iisPort` con `displayName` que dice literalmente *"SIN evidencia en el repo del
  puerto real - confirmar con infraestructura antes de completar"* y `default: 0`. **Es el caso
  canónico de "valor que sólo el operador conoce", y hoy vive escondido en un `displayName`.**
- `:117` — `pool: name: '${{ parameters.agentPool }}'` y `:118` — `environment:
  '${{ parameters.targetEnvironment }}'`: el servidor y el entorno son parámetros, no literales.
- `:101-112` — `${{ if eq(parameters.skipIis, true) }}: skipIisArg: '-SkipIis'`: variables de
  compile-time derivadas de parámetros.
- `:128,132-138` — `$(Pipeline.Workspace)`, `$(Build.ArtifactStagingDirectory)`, `$(skipIisArg)`,
  `$(seedConfigsArg)`, `$(whatIfArg)` conviviendo en el mismo bloque `arguments`.

**`.../golden/cd-deploy-test.yml`** — verificado abriendo el archivo:

- `:34-36` — `variables: buildConfiguration: 'Release'` / `buildPlatform: 'Any CPU'` (ya definidas:
  **no hay que preguntarlas**).
- `:120-121` — `pool: name: 'TEST-Server'` — nombre de servidor **literal y hardcodeado**.
- `:125,164` — `environment: 'Test'` en los dos `- deployment:`.
- `:136` — `displayName: 'Deploy AgendaWeb → C:\AIS\AgendaWeb\Web'` y `:175` — `'Deploy Batch →
  C:\AIS\Procesos\Exes'`. **Las rutas de despliegue reales están en un `displayName`, no en un
  input: el YAML no las parametriza y el valor efectivo vive dentro de `Deploy-Local.ps1`.** Es
  exactamente el tipo de dato que rompe el día que aparece un servidor de QA.
- `:81-87` — bloque `script: |` con PowerShell (`$slns`, `$s`, `$LASTEXITCODE`): **variables de
  shell que NO son variables de pipeline.** Un detector por regex crudo las reportaría como
  faltantes.

**`.../golden/nightly-build-online.yml:111-113`** — `- script: |` con `$(Agent.JobStatus)` y
`$(Build.BuildNumber)` DENTRO del bloque de shell: variables predefinidas de ADO que **nunca** se
piden. Y `:99` — `$(Agent.TempDirectory)`. Sin allowlist de predefinidas, la matriz sería ruido.

### 2.2 Lo que YA existe y este plan REUSA (verificado abriendo cada archivo)

| Pieza | Anclaje con símbolo | Qué aporta |
|---|---|---|
| Caja fuerte de variables | `backend/services/ci_variables.py:66 (get_variables_provider)`, `:63 (VARIABLES_PORT_METHODS)`, `:40 (VariablesUnavailableError)` | Fuente de verdad de "esta key ya está definida en el proveedor". |
| Heurística de secreto y validación de key | `ci_variables.py:31 (looks_secret)`, `:13 (validate_variable_key)` | No re-implementar: se importan. |
| Adapter ADO | `backend/services/ado_variables.py:25 (AdoVariablesProvider.list_variables)`, `:44` (devuelve `masked: None`), `:17 (find_yaml_definition)` | Variables de la pipeline **definition** (globales a la definition). |
| Adapter GitLab | `backend/services/gitlab_variables.py:22 (GitLabVariablesProvider.list_variables)`, `:30 (_request_paginated)`, `:37 (is_secret = masked or protected)` | Variables CI/CD del proyecto, paginadas. |
| Endpoint write-only + HITL | `backend/api/devops_variables.py:8 (bp, url_prefix="/devops/variables")`, `:59 (create_variable)`, `:19 (_call_provider)` | **El único camino de escritura. Este plan lo enlaza, no lo duplica.** |
| Registro de servidores | `backend/services/server_registry.py:84 (list_servers)`, `:36 (_PUBLIC_KEYS)`, `:196 (has_password)` | Alias/host/credencial de los servidores del operador. `list_servers()` ya devuelve `has_password` sin el password. |
| Masking común (Plan 195) | `backend/services/secret_masking.py:20 (mask_token_values)`, `:25 (strip_secret_keys)`, `:12 (MASK_PLACEHOLDER)`, `:13 (SECRET_KEY_SUFFIXES)` | Se aplica a TODO fragmento de YAML que salga en la respuesta. |
| Recorrido de documento parseado | `backend/services/pipeline_renderers.py:39 (_walk)`, `:51 (scan_unsupported)`, `:36 (_COMPILE_TIME_MARKER = "${{")` | **El patrón de la casa: `yaml.safe_load` y caminar el documento, nunca grep sobre el texto** (C20 del 243: `agendaweb-ci.yml:142` tiene tareas dentro de comentarios). |
| Modelo de spec | `backend/services/pipeline_spec.py:67 (DeploymentJob)`, `:73 (DeploymentJob.environment)`, `:93 (Job.pool_name)`, `:124 (PipelineSpec.parameters)` | Confirma que `environment`, `pool_name` y `parameters` son constructos de primera clase. |
| Health del panel | `backend/api/devops.py:48` (clave `variables_enabled` dentro de `_health_payload`), `:89 (devops_health_route)` | Acá se agrega la key nueva. |
| Registro de blueprints | `backend/api/__init__.py:50 (import devops_variables bp)`, `:123 (register_blueprint(devops_variables_bp))`, `:117 (pipeline_generator_bp)` | Patrón exacto de registro. |
| Registro declarativo de secciones | `frontend/src/pages/DevOpsPage.tsx:113 (DEVOPS_SECTIONS)`, `:79-81 (healthKey/gateFlagKey/gateMessage)`, `:174-179` (entrada `id: 'variables'`) | Una sola entrada nueva. Prohibido tocar el shell fuera del array. |
| Cliente de la caja fuerte | `frontend/src/api/endpoints.ts:4298 (DevOpsVariables)`, `:4299 (list)`, `:4303 (create)` | El CTA "Completar" reusa `DevOpsVariables.create`. |
| Espejo puro de la heurística | `frontend/src/devops/variablesModel.ts:25 (looksSecret)`, `:15 (validateVariableKey)`, `:37 (canBeMasked)` | Se importa; no se re-escribe. |
| Contexto de sección | `frontend/src/components/devops/EnvironmentsSection.tsx:39 (import DevOpsSectionContext)` | Shape del `ctx` que recibe un panel. |
| Flags | `backend/services/harness_flags.py:120 (_CATEGORY_KEYS)`, `:217 (categoría "devops")`, `:224 (STACKY_DEVOPS_VARIABLES_ENABLED)`, `:3040 (FlagSpec del Plan 94)`, `:4709 (validate_requires_graph)` | Patrón y categoría exactos. |
| Mapa congelado de `requires` | `backend/tests/test_harness_flags_requires.py:120 (_REQUIRES_MAP_FROZEN)`, `:161 (arista del Plan 94)`, `:288 (assert actual == _REQUIRES_MAP_FROZEN)` | 6ª pata obligatoria. |
| Defaults curados | `backend/tests/test_harness_flags.py:467 (_CURATED_DEFAULTS_ON)`, `:887 (assert known_keys == _CURATED_DEFAULTS_ON)` | Toda flag con `default=True` va acá o el test queda rojo. |
| Ratchet del arnés | `backend/tests/test_harness_ratchet_meta.py:18 (_ratchet_files)` — parsea `HARNESS_TEST_FILES` de **`backend/scripts/run_harness_tests.sh`** | Todo `test_*.py` nuevo se registra ahí. |
| Conformance del sub-puerto | `backend/tests/test_plan94_variables_providers.py:283 (test_f2_port_structural_conformance)`, `:291 (assert VARIABLES_PORT_METHODS == (...))` | Usa `hasattr`, **no** un set exacto ⇒ agregar un método NUEVO al adapter es seguro **si no se toca `VARIABLES_PORT_METHODS`**. |

### 2.3 El gap concreto, en tres frases

1. **Nadie sabe qué exige una pipeline hasta que falla.** No existe hoy ningún módulo que enumere
   los valores requeridos por un YAML: `grep -rn "environment_scope" backend/` da **0 resultados**
   (verificado) y `list_variables()` de ambos adapters descarta ese campo
   (`gitlab_variables.py:38-43` construye el dict a mano y no lo incluye).
2. **La caja fuerte del 94 es plana.** `ado_variables.py:44` devuelve `masked: None` y
   `gitlab_variables.py:37` colapsa `masked or protected` en un booleano: **no hay noción de
   entorno en ninguna de las dos patas.** El Plan 94 §7 declara `environment_scope` fuera de
   scope explícitamente.
3. **Lo que falta no es un lugar donde guardar valores: es la lista de qué valores.**

**Degradación si 246/247 no están implementados:** este plan **no depende de ellos**. El endpoint
recibe el texto del YAML en el body (mismo transporte que `POST /api/devops/parse-yaml` del Plan
87). Si el 246 existe, el panel ofrece un selector con su inventario; si no existe, el panel usa
el YAML activo del builder. Fase F5, criterio explícito.

### 2.4 Lo NO verificado (declarado)

Honestidad obligatoria (§5 del dossier). No abrí, y por lo tanto **no anclo con símbolo**:

- **Los documentos `docs/89_PLAN_...md` y `docs/91_PLAN_...md`.** Verifiqué su **código**
  (`frontend/src/devops/environmentModel.ts` y `backend/services/server_registry.py`), que es lo
  que este plan consume. Los `.md` no los leí.
- **`backend/services/environment_init.py`** y dónde persiste exactamente `environment_root` del
  Plan 89. Por eso el `environment_root` **no** es fuente de resolución en F3 — sólo se muestra
  como sugerencia en la UI (F5) leyéndolo del `ctx` que el panel ya recibe. Si el implementador
  no lo encuentra en el `ctx`, **omite la sugerencia**: no es bloqueante.
- **`deployment/export_harness_defaults.py`** y el estado de `backend/harness_defaults.env`.
  Verifiqué que el archivo contiene `STACKY_DEVOPS_VARIABLES_ENABLED=true:36` y
  `STACKY_PIPELINE_PROVIDER_ENABLED=false:55`, pero **no** si hay un test que exija una línea por
  flag. **Instrucción: NO tocar `harness_defaults.env` a mano** (tiene drift ajeno conocido y su
  generador vive en `deployment/`). Si aparece un rojo ahí, es ajeno.
- **Los 6 YAML restantes del corpus dorado.** Abrí sólo `bootstrap-server-environment.yml`,
  `cd-deploy-test.yml` y `nightly-build-online.yml`. Los casos borde de `ci-batch.yml` (`matrix`,
  citado por el dossier en `:58-59`) los tomo del dossier, **no de lectura propia**.
- **El nombre exacto del campo `environment_scope` en la respuesta de la API de GitLab.** Es
  contrato externo, cero ocurrencias en el repo. Mitigación codificada: siempre
  `v.get("environment_scope") or "*"` — si el campo no viene, todo cae a scope global y la matriz
  lo dice en llano. Nunca crashea.
- **`frontend/src/devops/pipelineEnvMatrixModel.ts`** y `PipelineEnvMatrixPanel.tsx` no existen:
  los crea este plan (nombres RESERVADOS en el §3 del dossier).

---

## 3. Principios y guardarraíles (NO negociables)

### 3.1 Corte de alcance declarado (el dossier exige máximo 6 fases)

Este plan entra en **6 fases: F0..F5**. Para lograrlo **corté a propósito** tres cosas, que
**no** quedan a medias sino explícitamente afuera (§6):

- **La escritura al proveedor.** No hay endpoint de escritura nuevo. Ver §3.2.
- **El scoping por entorno al ESCRIBIR** (GitLab `environment_scope`, ADO variable groups). Este
  plan lo **lee y lo reporta**; no lo crea.
- **La generación del README/`.zip` con las instrucciones de lo que falta** → es el **Plan 252**.
  Este plan le entrega la lista estructurada; el 252 la convierte en documentación.

### 3.2 Seguridad: este plan NO escribe, y por eso su flag es default ON

**Ninguna de las 4 excepciones duras aplica**, y eso es una consecuencia del diseño, no una
casualidad:

1. *No bypasea revisión humana*: no publica, no crea tickets, no ejecuta nada remoto, no manda
   mensajes. Sólo lee y muestra.
2. *No es destructiva ni irreversible*: no hay una sola operación de escritura en las 6 fases.
3. *No requiere prerequisitos fuera de la instalación default*: si el proveedor no responde, la
   matriz cae al modo puro (`resolve:false`) y sigue siendo útil.
4. *No reduce seguridad por default*: la **sube**. Hoy el operador tiene que abrir el YAML y
   buscar a ojo qué credenciales hacen falta; a partir de acá las ve enumeradas, marcadas como
   secretas, y con el CTA que lleva al único camino seguro que ya existe.

**Regla dura, codificada:** cuando una celda está en `falta` y el valor es un secreto, el botón
"Completar" **no abre un formulario propio**: enlaza el formulario del **Plan 94**
(`DevOpsVariables.create`, `endpoints.ts:4303`), que ya exige `confirm:true` server-side
(`api/devops_variables.py:72-73`), ya es write-only y ya está gateado por su propia flag.
**Cero superficie de escritura nueva. Un solo camino auditado para todo secreto.**

Si algún día se quisiera escritura en lote desde la matriz, sería un plan aparte con flag
`default=False` y confirmación explícita, citando la **excepción 1** (bypasea revisión humana) y
la **excepción 4** (reduce seguridad por default). **No es este plan.**

### 3.3 El secreto nunca se muestra ni se loguea

- La respuesta del endpoint contiene, por celda, **exclusivamente**: `estado`
  (`definido｜default｜falta｜manual`), `fuente`, `es_secreto` y `evidencia`. **Nunca un `value`.**
- Toda `evidencia` (el fragmento del YAML donde apareció el requerimiento) pasa por
  `mask_token_values` (`services/secret_masking.py:20`) antes de salir, y el diccionario completo
  de la respuesta pasa por `strip_secret_keys` (`:25`) como segunda red.
- Los `default` que vienen del propio YAML **sí se muestran** (ya están en el repo en texto plano:
  ocultarlos sería teatro), **salvo** que la key matchee `looks_secret()`
  (`ci_variables.py:31`) — en ese caso el default se reemplaza por `MASK_PLACEHOLDER`
  (`secret_masking.py:12`) y la celda se marca `es_secreto: true` **con una advertencia**: hay un
  secreto en texto plano dentro del YAML.
- **Prohibido** cualquier `logger.*` o `print` que referencie un valor en los archivos nuevos.
  Grep binario en el criterio de F3 y F4.

### 3.4 Cero trabajo extra al operador

Default **ON**, sección nueva, **solo lectura**. El operador no configura nada, no completa nada
nuevo y no aprende ningún flujo. Lo único que hace es lo que ya tenía que hacer —cargar el valor
que sólo él conoce— con la diferencia de que ahora está enumerado en vez de descubierto por una
corrida roja. **Pedir de más está prohibido: KPI-2 es un test binario.**

### 3.5 Human-in-the-loop

Stacky **no** rellena, no adivina, no autocompleta y no propone valores. Presenta hechos
(`definido`/`falta`) y, cuando el YAML trae un `default`, lo muestra tal cual con estado `default`
para que el operador **confirme o cambie**. Igual que el contrato UX del Plan 106 F5
(`PipelineBuilderSection.tsx:382-383`, citado por el dossier §2.3): *nunca pisa lo que el operador
ya escribió*.

### 3.6 Multiproveedor sin denominador común falso

ADO y GitLab **no** tienen el mismo modelo y este plan no finge que sí:

| | ADO | GitLab |
|---|---|---|
| Dónde viven las variables | En la **pipeline definition** (`ado_variables.py:25-45`) | En el **proyecto**, con `environment_scope` |
| ¿Scoping por entorno? | **No** en el modelo del Plan 94. Requiere variable groups o definitions separadas. | **Sí**, nativo. |
| Consecuencia en la matriz | Una variable definida se marca `definido` en **todas** las columnas, **con nota literal**: *"ADO resuelve variables por definition, no por entorno: si Test y Producción necesitan valores distintos hacen falta variable groups o definitions separadas."* | Se marca `definido` sólo en las columnas cuyo `environment_scope` matchea (o en todas si el scope es `*`). |
| Entornos | `environment:` de los `- deployment:` + `values:` de los `parameters:` | `environment:` (string o `environment.name`) de los jobs + `environment_scope` distintos de `*` |

Esa asimetría **se muestra en la UI**, no se esconde.

### 3.7 Núcleo determinista, sin LLM ⇒ paridad de runtimes trivial

**Las 6 fases tienen 0 llamadas a modelo.** F1 y F2 son funciones puras sobre el documento
parseado; F3 hace lecturas HTTP a través de proveedores existentes; F4 es Flask; F5 es React.
Por lo tanto Codex CLI, Claude Code CLI y GitHub Copilot Pro obtienen **resultado idéntico byte a
byte** y no hay fallback que declarar. Cada fase repite la línea igual, y F5 tiene un grep binario
que lo prueba.

### 3.8 No degradar / backward-compatible

- **Prohibido modificar** `list_variables`, `set_variable` y `delete_variable` de los adapters del
  Plan 94, y **prohibido tocar** `VARIABLES_PORT_METHODS` (`ci_variables.py:63`) o el `Protocol`
  `CIVariablesProvider` (`:45`). La capacidad nueva de F3 es un método **adicional**, descubierto
  con `getattr`, que el resolutor **degrada** si no está.
- `PipelineSpec` y los renderers quedan **intactos**: este plan no parsea a `PipelineSpec`
  (es un modelo lossy para este fin — no modela `parameters:` resueltos ni las expresiones
  `${{ }}`), trabaja sobre el documento crudo de `yaml.safe_load`.
- Con la flag OFF: el endpoint da 404 y la sección no aparece. Todo lo demás, byte-idéntico.
- **Performance:** el análisis es **bajo demanda** (un click, una pipeline). No hay barrido
  automático, ni polling, ni trabajo en el arranque. Las lecturas al proveedor son **una** por
  análisis (`list_variables()` ya pagina internamente, `gitlab_variables.py:30`).

### 3.9 Mono-operador

Sin RBAC, sin roles, sin multiusuario. `current_user` no se consulta en ninguna fase.

---

## 4. Contrato de datos

Sin persistencia nueva. Stacky **no guarda** ni la matriz ni los valores: se recalcula en cada
análisis. Cero estado duplicado (mismo riel que el Plan 94 §3.9).

### 4.1 Enumeraciones CERRADAS (`services/pipeline_environments.py`)

```python
VALUE_KINDS = ("variable", "secret", "service_connection", "server", "deploy_path", "parameter")
CELL_STATES = ("definido", "default", "falta", "manual")
SOURCES = ("predefinida", "yaml_variables", "yaml_parameter_default",
           "caja_fuerte", "registro_servidores", "scope_proveedor", "ninguna")
CONFIDENCE = ("alta", "baja")
```

### 4.2 Dataclasses (frozen, puras)

```python
@dataclass(frozen=True)
class Evidence:
    path: str        # ruta del nodo: "stages[1].jobs[0].steps[2].inputs.filePath"
    excerpt: str     # el string donde aparece, YA pasado por mask_token_values

@dataclass(frozen=True)
class Requirement:
    name: str                 # "agentPool", "buildConfiguration", "TEST-Server", "C:\\AIS\\..."
    kind: str                 # uno de VALUE_KINDS
    provider: str             # "azure_devops" | "gitlab"
    is_secret: bool           # looks_secret(name) — sólo por NOMBRE, nunca por valor
    declared_default: str | None   # default del YAML, ya enmascarado si is_secret
    per_environment: bool     # True si el valor razonablemente cambia por entorno
    confidence: str           # "alta" | "baja"
    evidence: tuple           # tuple[Evidence, ...], orden de aparición

@dataclass(frozen=True)
class Cell:
    state: str                # uno de CELL_STATES
    source: str               # uno de SOURCES
    note: str | None          # nota honesta (p.ej. la de ADO sin scoping)

@dataclass(frozen=True)
class EnvMatrix:
    environments: tuple       # tuple[str, ...] — DERIVADOS, ordenados
    requirements: tuple       # tuple[Requirement, ...]
    cells: dict               # {(requirement_name, environment): Cell}
    pending_count: int        # celdas en estado "falta" — EL número del titular
    degraded: tuple           # tuple[str, ...] — motivos de degradación honestos
```

### 4.3 Tabla de tipos de valor (contrato de detección y resolución)

| Tipo | Cómo se detecta en **ADO** | Cómo se detecta en **GitLab** | Dónde se busca ANTES de preguntar | Cómo se le pide si falta |
|---|---|---|---|---|
| **`variable`** (simple) | `$(NOMBRE)` en cualquier string del documento parseado, con `NOMBRE` que matchea `^[A-Za-z_][A-Za-z0-9_.]*$`. Descarta las de la allowlist predefinida (§4.4). | `$NOMBRE` / `${NOMBRE}` en `script:` y en valores de `variables:` | 1) bloque `variables:` (raíz/stage/job) del YAML; 2) `list_variables()` de la caja fuerte (94) | Fila con estado `falta`. CTA **"Completar"** → formulario del Plan 94 con `key` pre-cargada y "secreta" **des**tildada. |
| **`secret`** | Igual que `variable`, pero `looks_secret(name)` (`ci_variables.py:31`) da True | Igual | Igual, más el flag `is_secret` que ya devuelve el proveedor | Mismo CTA, con "secreta 🔒" **pre-tildado**. **Nunca se muestra un valor**, ni el default (se enmascara con `MASK_PLACEHOLDER`). |
| **`service_connection`** | Valor de un input cuya key esté en `_ADO_SERVICE_CONNECTION_KEYS` (§4.4) | **No existe** el constructo. En GitLab el equivalente son variables/tokens ⇒ **no se emite este kind para gitlab** | **No se busca: no es resoluble por API en v1** | Estado **`manual`** (nunca `falta`). Texto literal: *"Stacky no puede crear ni verificar service connections: creala en la web de Azure DevOps."* Entra al paquete del **Plan 252**. |
| **`server`** | `pool.name` a nivel raíz, stage, job o `- deployment:` (evidencia `cd-deploy-test.yml:120-121`). Si el valor es `${{ parameters.X }}`, se resuelve X contra el bloque `parameters:` (evidencia `bootstrap:116-117` + `:47-50`) | Cada valor de `tags:` de un job (modelado como `Job.runner_tags`, `pipeline_spec.py:87`) | `server_registry.list_servers()` (`server_registry.py:84`): match **case-insensitive** contra `alias` **y** contra `host` | Si matchea ⇒ `definido` + badge `has_password` (`server_registry.py:196`, booleano, **nunca** la credencial). Si no ⇒ `falta` con CTA **"Registrar servidor"** → sección Servidores (Plan 91). |
| **`deploy_path`** | Cualquier string **literal absoluto** (`^[A-Za-z]:[\\/]` o `^/`) **sin** `$(` ni `${{`. `confidence="alta"` si está bajo una key de `_PATH_INPUT_KEYS` (§4.4); `"baja"` si aparece en `displayName` u otro texto (evidencia real: `cd-deploy-test.yml:136,175`) | Igual, sobre valores de `script:` y `environment.url` | **No se busca en ninguna API.** En F5 la UI **sugiere** el `environment_root` del perfil (Plan 89) si está en el `ctx` — sugerencia visual, **no** resolución | `per_environment=True` **siempre**. Estado `falta` si `confidence=="alta"`; si es `"baja"`, estado `manual` con la nota: *"ruta absoluta hardcodeada en el YAML — confirmá el valor de cada entorno."* |
| **`parameter`** | Cada entrada del bloque `parameters:` (evidencia `bootstrap:38-84`) con su `name`, `type`, `default` y `values` | `spec.inputs` si existe; si no, no se emite | El propio `default` del YAML | Si trae `default` ⇒ estado **`default`** con el valor mostrado y el CTA **"Confirmar"** (no es trabajo, es un OK). Si no trae `default` ⇒ `falta`. |

### 4.4 Constantes cerradas (evitan el ruido y el falso positivo)

```python
# Variables predefinidas de ADO: JAMÁS se piden. Prefijos + exactas.
_ADO_PREDEFINED_PREFIXES = ("Build.", "System.", "Agent.", "Pipeline.", "Release.",
                            "Environment.", "Deployment.", "Task.", "Common.")
_ADO_PREDEFINED_EXACT = ("Rev",)

# Claves cuyo VALOR es un bloque de shell: ahí `$(algo)` puede ser sustitución de
# comando de bash o una variable de PowerShell, NO una variable de pipeline.
_SHELL_KEYS = ("script", "bash", "pwsh", "powershell")

# Inputs cuyo valor es una ruta de despliegue con confianza ALTA.
_PATH_INPUT_KEYS = ("filePath", "PathtoPublish", "targetPath", "workingDirectory",
                    "destinationFolder", "SourceFolder", "TargetFolder", "packageForLinux")

# Inputs que declaran una service connection de ADO.
_ADO_SERVICE_CONNECTION_KEYS = ("azureSubscription", "ConnectedServiceName",
                                "ConnectedServiceNameARM", "connectedServiceName",
                                "azureResourceManagerConnection", "kubernetesServiceConnection",
                                "dockerRegistryServiceConnection", "publishFeedCredentials")

# Orden canónico de entornos conocidos. Lo NO listado va después, alfabético.
_ENV_RANK = {"dev": 0, "desarrollo": 0, "development": 0,
             "test": 1, "qa": 1, "testing": 1, "staging": 2, "uat": 2,
             "prod": 3, "produccion": 3, "producción": 3, "production": 3}
```

**Regla anti-falso-positivo (F1, obligatoria):** si un `$(X)` aparece dentro del valor de una key
de `_SHELL_KEYS`, sólo se emite `Requirement` si `X` **ya** está declarado en `variables:` /
`parameters:` o está en la allowlist predefinida. En cualquier otro caso se emite con
`confidence="baja"` y **nunca** puede terminar en estado `falta`. Evidencia que lo justifica:
`nightly-build-online.yml:111-113` (`$(Agent.JobStatus)` dentro de `- script: |`) y
`cd-deploy-test.yml:81-87` (`$slns`, `$s`, `$LASTEXITCODE` de PowerShell).

---

## 5. Fases

> **Comandos (§4 del dossier, verificados).** Backend, SIEMPRE por archivo, con `.venv`
> (Python 3.13.5 — **no** `backend/venv`, que es 3.11.9):
> ```powershell
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> .venv\Scripts\python.exe -m pytest tests/<archivo>.py -q
> ```
> Frontend:
> ```powershell
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
> npx vitest run src/devops/__tests__/pipelineEnvMatrixModel.test.ts
> npx tsc --noEmit
> ```
> **`npm test` NO existe en `package.json`: falla.** Usar `npx vitest`.
> **Rojo ajeno conocido:** `test_harness_flags_help` tiene 4 fallos que **no son de este plan**.

---

### F0 — Flag `STACKY_PIPELINE_ENV_MATRIX_ENABLED` (6 patas)

**Objetivo:** la flag existe, es default ON, es editable por UI y no rompe ningún meta-test.

**Archivos a editar:**

1. `backend/config.py` — atributo `STACKY_PIPELINE_ENV_MATRIX_ENABLED`, junto a
   `STACKY_DEVOPS_VARIABLES_ENABLED`, con el patrón exacto del archivo y valor efectivo `True`.
   **Gotcha dura:** el consumidor lee **la instancia** (`from config import config` →
   `getattr(config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", False)`). Hacer `getattr` del **módulo**
   devuelve el default y mata el branch OFF (falso verde en el test flag-off).
2. `backend/services/harness_flags.py` — dos ediciones:
   - En `_CATEGORY_KEYS` (`:120`), dentro de la tupla `"devops"` (`:217`), después de la línea
     `:224` del Plan 94:
     ```python
     "STACKY_PIPELINE_ENV_MATRIX_ENABLED",  # Plan 251 — matriz de entornos y valores faltantes
     ```
   - `FlagSpec` nuevo, junto al del Plan 94 (`:3040`):
     ```python
     FlagSpec(
         key="STACKY_PIPELINE_ENV_MATRIX_ENABLED",
         type="bool",
         label="Matriz de entornos (Plan 251)",
         description=(
             "Plan 251 - Detecta que valores exige una pipeline (variables, secretos, "
             "servidores, rutas de despliegue, parametros) y los cruza contra los entornos "
             "reales de esa pipeline, resolviendo primero contra la caja fuerte (94) y el "
             "registro de servidores (91) para pedir SOLO lo que falta. Solo lectura: no "
             "escribe nada. Default ON: /api/pipeline-environments responde y la seccion "
             "aparece; con OFF da 404 y la seccion no se muestra."
         ),
         group="global",
         env_only=False,  # editable por UI (regla operator-config-always-via-ui)
         requires="STACKY_DEVOPS_PANEL_ENABLED",
         # default ON: ninguna de las 4 excepciones duras aplica (plan de SOLO LECTURA,
         # sin escritura al proveedor ni al repo). Curada en _CURATED_DEFAULTS_ON.
         default=True,
     ),
     ```
     **Gotcha `requires` (R4, profundidad 1):** `requires` **debe** ser
     `STACKY_DEVOPS_PANEL_ENABLED`, que es el master de raíz que usan las 10 secciones DevOps
     hermanas. **Prohibido** poner `requires="STACKY_DEVOPS_VARIABLES_ENABLED"`: esa flag ya
     declara `requires="STACKY_DEVOPS_PANEL_ENABLED"` (`harness_flags.py:3053`) y encadenar rompe
     la regla de profundidad máxima 1 de `validate_requires_graph` (`harness_flags.py:4709`;
     el mismo desvío está documentado en el comentario de `:3158-3168`).
3. `backend/services/harness_flags_help.py` — entrada `PlainHelp` en llano, mismo patrón que la
   del Plan 94.
4. `backend/tests/test_harness_flags.py` — agregar la key a `_CURATED_DEFAULTS_ON` (`:467`).
   **Sin esto, `test_default_known_only_for_curated` (`:887`) queda ROJO.**
5. `backend/tests/test_harness_flags_requires.py` — agregar la arista al mapa congelado
   (`_REQUIRES_MAP_FROZEN`, `:120`), junto a la del Plan 94 (`:161`):
   ```python
   "STACKY_PIPELINE_ENV_MATRIX_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 251
   ```
   **Sin esto, `test_requires_map_is_frozen` (`:288`) queda ROJO en silencio.**
6. `backend/scripts/run_harness_tests.sh` — registrar los 5 archivos de test nuevos de este plan
   en `HARNESS_TEST_FILES` (el meta-test parsea **ese** `.sh`, ver
   `test_harness_ratchet_meta.py:18-21`).

**NO tocar `backend/harness_defaults.env`** (§2.4).

**Tests PRIMERO** — `backend/tests/test_plan251_env_matrix_flag.py`:
- `test_f0_flag_en_registry` — la key está en `FLAG_REGISTRY`.
- `test_f0_flag_en_categoria_devops` — está en `_CATEGORY_KEYS["devops"]`.
- `test_f0_default_on` — `spec.default is True` y la key está en `_CURATED_DEFAULTS_ON`.
- `test_f0_requires_es_el_master_del_panel` — `spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_f0_plain_help_existe`.

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

**Criterio de aceptación BINARIO:** los 5 tests propios verdes **y** los 3 archivos de
no-regresión verdes (`test_harness_flags.py`, `test_harness_flags_requires.py`,
`test_harness_ratchet_meta.py`). Cualquier rojo en esos tres = la flag está mal cableada.

**Flag:** `STACKY_PIPELINE_ENV_MATRIX_ENABLED`, default **ON**.
**Impacto por runtime:** ninguno en los 3 (Codex / Claude Code / Copilot). Sin LLM, sin fallback.
**Trabajo del operador: ninguno.**

---

### F1 — Núcleo PURO de detección: `extract_requirements`

**Objetivo:** dado el texto de un YAML, devolver la lista determinista de todo lo que esa pipeline
exige. Sin I/O, sin red, sin LLM. **Es el corazón del plan.**

**Archivo NUEVO:** `backend/services/pipeline_environments.py`

```python
"""pipeline_environments.py — Plan 251. Matriz de entornos y valores requeridos.

Núcleo PURO (F1/F2): sin I/O, sin red, sin LLM. La extracción camina el documento
PARSEADO con yaml.safe_load y NUNCA hace grep sobre el texto crudo (C20 del Plan 243:
agendaweb-ci.yml:142 y ci-dacpac.yml:102 tienen referencias a tareas DENTRO de
comentarios). El VALOR de un secreto no entra ni sale de este módulo.
"""
```

Símbolos EXACTOS a crear (además de las constantes y dataclasses del §4):

```python
def _iter_nodes(doc, path="") -> Iterator[tuple[str, str, object]]:
    """(path, key, value) de cada nodo del documento. Espejo de _walk
    (pipeline_renderers.py:39) pero llevando la RUTA para la evidencia."""

def _resolve_parameter_expr(text: str, parameters: dict) -> tuple[str | None, str | None]:
    """'${{ parameters.agentPool }}' -> ('agentPool', <default del parámetro>).
    (None, None) si no es una expresión de parámetro. Evidencia: bootstrap:117."""

def _declared_variables(doc: dict) -> dict:
    """Todas las variables declaradas: `variables:` de raíz, de stage y de job.
    Soporta las DOS formas de ADO: mapa {k: v} y lista [{name:, value:}].
    Ignora las claves de compile-time '${{ if ... }}:' pero SÍ registra las
    variables que declaran adentro (bootstrap:101-112 -> skipIisArg, seedConfigsArg,
    whatIfArg quedan DECLARADAS, no faltantes)."""

def _declared_parameters(doc: dict) -> dict:
    """{name: {"type":, "default":, "values": []}} del bloque `parameters:`
    (bootstrap:38-84). Vacío si no hay bloque."""

def is_ado_predefined(name: str) -> bool:
    """True si matchea _ADO_PREDEFINED_PREFIXES o _ADO_PREDEFINED_EXACT."""

def extract_requirements(yaml_text: str, provider: str) -> tuple:
    """tuple[Requirement, ...]. provider ∈ ('azure_devops','gitlab').
    Determinista: mismo input -> mismo output, mismo ORDEN (aparición en el doc,
    desempate alfabético por name). YAML inválido -> () (nunca levanta)."""
```

**Reglas exactas de `extract_requirements` (en este orden):**

1. `doc = yaml.safe_load(yaml_text)`; si levanta `yaml.YAMLError` o `doc` no es `dict` ⇒ `()`.
2. Calcular `declared = _declared_variables(doc)` y `params = _declared_parameters(doc)`.
3. Emitir un `Requirement` `kind="parameter"` por cada entrada de `params`, con
   `declared_default=str(default)` si existe y `per_environment=True` si el nombre matchea
   `_ENV_RANK` o su `values` tiene ≥2 elementos.
4. Recorrer `_iter_nodes(doc)`. Para cada valor **string**:
   - Si la key del nodo está en `_ADO_SERVICE_CONNECTION_KEYS` y `provider=="azure_devops"` ⇒
     `kind="service_connection"`, `confidence="alta"`.
   - Si la key es `name` bajo un nodo `pool` (o el valor de `tags:` en gitlab) ⇒ `kind="server"`.
     Si el string es `${{ parameters.X }}`, resolver con `_resolve_parameter_expr` y usar el
     default del parámetro como `name`; si no resuelve, usar el literal.
   - Si el string es una ruta absoluta literal sin `$(` ni `${{` ⇒ `kind="deploy_path"`,
     `per_environment=True`, `confidence="alta"` si la key está en `_PATH_INPUT_KEYS`, si no
     `"baja"`.
   - Aplicar `_ADO_VAR_RE` / `_GL_VAR_RE` según `provider`. Para cada nombre capturado:
     - si `is_ado_predefined(nombre)` ⇒ **descartar** (no es un requerimiento);
     - si la key del nodo está en `_SHELL_KEYS` y el nombre **no** está en `declared` ni en
       `params` ⇒ emitir con `confidence="baja"`;
     - si no ⇒ emitir con `confidence="alta"`.
     `kind = "secret" if looks_secret(nombre) else "variable"` (importando `looks_secret` de
     `services.ci_variables`, **no** re-implementándolo).
5. Deduplicar por `(name, kind)` **acumulando** las `Evidence` (una key usada en 3 lugares es UN
   requerimiento con 3 evidencias).
6. Todo `Evidence.excerpt` pasa por `mask_token_values` (`services/secret_masking.py:20`).
7. `declared_default` se reemplaza por `MASK_PLACEHOLDER` (`secret_masking.py:12`) si
   `is_secret is True`.

Regex exactos:
```python
_ADO_VAR_RE = re.compile(r"\$\((?P<n>[A-Za-z_][A-Za-z0-9_.]*)\)")
_ADO_TPL_RE = re.compile(r"\$\{\{\s*parameters\.(?P<n>[A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_GL_VAR_RE  = re.compile(r"\$\{?(?P<n>[A-Za-z_][A-Za-z0-9_]*)\}?")
_ABS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/)[^\s\"']*")
```

**Tests PRIMERO** — `backend/tests/test_plan251_env_matrix_extract.py`
(fixtures: los YAML **reales** de `backend/tests/fixtures/cicd_nl/golden/`, no juguetes):

- `test_f1_bootstrap_detecta_los_8_parametros` — sobre `bootstrap-server-environment.yml`:
  hay exactamente 8 requirements `kind="parameter"` y sus nombres son
  `{targetEnvironment, agentPool, component, skipIis, iisPort, iisHostHeader, seedConfigs, whatIf}`.
- `test_f1_bootstrap_iisport_default_cero` — el requirement `iisPort` tiene
  `declared_default == "0"` y su evidencia incluye el `displayName` de `:67`.
- `test_f1_bootstrap_servidor_desde_parametro` — existe un requirement `kind="server"` con
  `name == "TEST-Server"` (resuelto desde `${{ parameters.agentPool }}` + su default de `:50`).
- `test_f1_bootstrap_compile_time_vars_no_faltan` — `skipIisArg`, `seedConfigsArg` y `whatIfArg`
  **NO** aparecen como requirements (están declaradas en `:101-112`).
- `test_f1_cd_deploy_variables_declaradas_no_se_piden` — sobre `cd-deploy-test.yml`:
  `buildConfiguration` y `buildPlatform` (declaradas en `:34-36`) **no** aparecen; el resto sí.
- `test_f1_cd_deploy_pool_literal` — hay un requirement `kind="server"`, `name == "TEST-Server"`,
  `confidence == "alta"`.
- `test_f1_cd_deploy_rutas_absolutas` — hay requirements `kind="deploy_path"` con
  `"C:\\AIS\\AgendaWeb\\Web"` y `"C:\\AIS\\Procesos\\Exes"`, ambos con `per_environment is True`.
- `test_f1_powershell_no_es_variable_de_pipeline` — sobre `cd-deploy-test.yml:81-87`:
  ni `slns`, ni `s`, ni `LASTEXITCODE` aparecen como requirement.
- `test_f1_predefinidas_de_ado_nunca_se_piden` — sobre `nightly-build-online.yml`:
  `Agent.JobStatus`, `Build.BuildNumber`, `Build.ArtifactStagingDirectory` y `Agent.TempDirectory`
  **no** aparecen en el resultado.
- `test_f1_secreto_por_nombre` — fixture sintética mínima con
  `variables: { DB_PASSWORD: 'p4ss' }` referenciada como `$(DB_PASSWORD)`: el requirement tiene
  `is_secret is True` y `declared_default == MASK_PLACEHOLDER` (**el literal `p4ss` no aparece en
  `repr()` del resultado**).
- `test_f1_service_connection_ado` — fixture sintética mínima (el corpus dorado **no tiene**
  service connections; declarado): un `- task:` con `inputs: { azureSubscription: 'MiSub' }`
  ⇒ requirement `kind="service_connection"`.
- `test_f1_determinista` — llamar 3 veces sobre el mismo YAML da la MISMA tupla.
- `test_f1_yaml_invalido_devuelve_vacio` — `extract_requirements("a: [", "azure_devops") == ()`.
- `test_f1_modulo_puro` — leer el FUENTE de `services/pipeline_environments.py` como texto y
  assert que **no** contiene ninguno de: `"import flask"`, `"from flask"`, `"import requests"`,
  `"from requests"`, `"invoke_local_llm"`, `"logger."`, `"print("`.

**Comando:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_extract.py -q
```

**Criterio de aceptación BINARIO:** 14 tests verdes. **Y** el grep
`rg -n "yaml_text\.(find|split)|re\.(search|findall)\(.*yaml_text" backend/services/pipeline_environments.py`
da **0 resultados** (prueba que la extracción es sobre el documento parseado, no sobre el texto).

**Flag:** ninguna (módulo puro, sin consumidores hasta F4).
**Impacto por runtime:** ninguno. Función pura de Python: resultado idéntico en Codex, Claude Code
y Copilot. Sin LLM, sin fallback.
**Trabajo del operador: ninguno.**

---

### F2 — Entornos DERIVADOS + construcción de la matriz (PURO)

**Objetivo:** derivar los entornos reales de la pipeline desde evidencia y armar la grilla. Sin
inventar ninguna lista fija.

**Archivo a editar:** `backend/services/pipeline_environments.py` — agregar:

```python
def derive_environments(yaml_text: str, provider: str,
                        provider_scopes: tuple = ()) -> tuple:
    """tuple[str, ...] de entornos DERIVADOS. Nunca una lista hardcodeada.

    Fuentes, en este orden, todas unidas y deduplicadas (case-insensitive, se
    conserva la PRIMERA grafía vista):
      1. ADO: el valor de `environment:` de cada `- deployment:`
         (cd-deploy-test.yml:125,164 -> 'Test').
      2. ADO: si ese valor es '${{ parameters.X }}', los `values:` del parámetro X;
         si X no tiene `values`, su `default` (bootstrap:118 + :39-45 -> Test, Production).
      3. GitLab: `environment:` de cada job (string, o `environment.name` si es mapa).
      4. Cualquier scope != '*' de provider_scopes (viene de F3; en modo puro es ()).

    Orden final DETERMINISTA: por _ENV_RANK y, dentro del mismo rank o para los
    desconocidos, alfabético case-insensitive.

    Si la unión queda VACÍA -> ("(único)",). NUNCA se fabrica Dev/QA/Prod.
    """

def build_matrix(requirements: tuple, environments: tuple,
                 resolutions: dict, provider: str) -> EnvMatrix:
    """PURA. resolutions = {(name, env): (state, source, note)} que produce F3.
    Para los pares SIN entrada en resolutions aplica el default por kind:
      - service_connection            -> Cell("manual", "ninguna", <texto del §4.3>)
      - deploy_path confidence="baja" -> Cell("manual", "ninguna", <texto del §4.3>)
      - todo lo demás                 -> Cell("falta", "ninguna", None)
    pending_count = cantidad de celdas con state == "falta".
    Si provider == "azure_devops" y len(environments) > 1, TODA celda "definido"
    resuelta por la caja fuerte lleva la nota del §3.6 (ADO no tiene scoping).
    """
```

**Tests PRIMERO** — `backend/tests/test_plan251_env_matrix_build.py`:

- `test_f2_bootstrap_deriva_test_y_production` — sobre `bootstrap-server-environment.yml`:
  `derive_environments(...) == ("Test", "Production")` (rank: test=1 < prod=3).
- `test_f2_cd_deploy_deriva_solo_test` — sobre `cd-deploy-test.yml`: `== ("Test",)`.
- `test_f2_sin_evidencia_una_sola_columna` — sobre `nightly-build-online.yml` (no tiene
  `- deployment:`): `== ("(único)",)`. **KPI-4.**
- `test_f2_orden_canonico` — con scopes `("prod","dev","staging","zeta")` el resultado es
  `("dev","staging","prod","zeta")`.
- `test_f2_dedup_case_insensitive` — `('Test','test','TEST')` ⇒ `("Test",)`.
- `test_f2_matriz_cubre_todas_las_celdas` — `len(m.cells) == len(m.requirements) * len(m.environments)`.
- `test_f2_pending_count_cuenta_solo_falta` — con `resolutions` que marca 2 de 5 como `definido`,
  y 1 `service_connection` que cae a `manual`, `pending_count == 2`.
- `test_f2_nota_ado_sin_scoping` — provider `azure_devops` con 2 entornos: toda celda `definido`
  por `caja_fuerte` trae `note` no vacío que contiene la palabra `"definition"`.
- `test_f2_gitlab_sin_nota_de_ado` — provider `gitlab`: ninguna celda trae esa nota.
- `test_f2_build_matrix_es_pura` — llamarla 2 veces con los mismos args da matrices iguales y
  **no** muta `requirements` ni `resolutions`.

**Comando:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_build.py -q
```

**Criterio de aceptación BINARIO:** 10 tests verdes, y `test_f1_modulo_puro` de F1 **sigue verde**
(el módulo no ganó I/O).

**Flag:** ninguna (puro).
**Impacto por runtime:** ninguno. Sin LLM, sin fallback.
**Trabajo del operador: ninguno.**

---

### F3 — Resolución contra lo que YA existe (SOLO LECTURA)

**Objetivo:** antes de pedir un valor, buscarlo. Es la fase que hace realidad el KPI-2.

**Archivo NUEVO:** `backend/services/pipeline_env_resolver.py`
(módulo aparte **a propósito**: `pipeline_environments.py` queda puro para siempre y
`test_f1_modulo_puro` no se vuelve frágil).

```python
"""pipeline_env_resolver.py — Plan 251 F3. Resolución SOLO LECTURA.

Busca cada requerimiento en las fuentes que Stacky YA tiene, para no pedirle al
operador nada que ya exista. NO escribe en ningún lado. El VALOR de un secreto
nunca entra a este módulo: sólo se consulta la EXISTENCIA de la key.
"""
```

Símbolos EXACTOS:

```python
def list_scoped_variables(project: str | None) -> tuple[list, tuple, list]:
    """(variables, scopes, degradaciones).

    1. provider = get_variables_provider(project)   # ci_variables.py:66
    2. scoped = getattr(provider, "list_variables_scoped", None)
       - si existe -> variables = scoped()  (trae environment_scope)
       - si NO existe -> variables = provider.list_variables()  y a cada item se
         le agrega environment_scope="*"  (DEGRADACIÓN HONESTA, se reporta)
    3. scopes = tuple ordenada de los environment_scope distintos de "*"
    4. Excepciones -> NUNCA propagan crudas:
       VariablesUnavailableError -> ([], (), ["ADO sin pipeline definition: no se
            pudieron leer variables del proveedor (creala con 'Llevar a producción',
            plan 95)"])
       TrackerConfigError        -> ([], (), ["<str(e)>"])
       TrackerApiError           -> ([], (), ["El proveedor no respondió al listar
            variables (código <e.status>)"])       # sin str(e): puede traer datos
       Exception                 -> ([], (), ["Error interno al leer variables"])
                                    # mensaje FIJO, PROHIBIDO str(e)
    """

def resolve(requirements: tuple, environments: tuple, provider: str,
            project: str | None, use_provider: bool = True) -> tuple[dict, tuple]:
    """(resolutions, degradaciones) para alimentar build_matrix.

    Con use_provider=False NO toca la red (modo puro/offline).
    Precedencia por celda — PRIMERA que acierta gana:
      1. kind == "parameter" con declared_default no None
                              -> ("default", "yaml_parameter_default", None)
      2. is_ado_predefined(name)      -> ("definido", "predefinida", None)
      3. name en declared_variables   -> ("definido", "yaml_variables", None)
      4. name en las keys del proveedor:
         - gitlab: sólo si environment_scope == "*" o == este entorno
                              -> ("definido", "caja_fuerte" | "scope_proveedor", None)
         - azure_devops: en TODOS los entornos, con la nota del §3.6
      5. kind == "server": match case-insensitive contra alias u host de
         server_registry.list_servers()   (server_registry.py:84)
                              -> ("definido", "registro_servidores", "credencial guardada"
                                  if has_password else "sin credencial guardada")
      6. sin acierto -> NO se agrega entrada (build_matrix aplica su default por kind)
    """
```

**Archivos a editar (ADITIVO — método NUEVO, contrato del 94 intacto):**

- `backend/services/gitlab_variables.py` — agregar a `GitLabVariablesProvider`:
  ```python
  def list_variables_scoped(self) -> list[dict]:
      """Plan 251 F3 — como list_variables() pero conservando environment_scope.
      ADITIVO: list_variables() (:22) queda BYTE-IDÉNTICA. El value se descarta
      igual (write-only, riel §3.1 del plan 94)."""
      proj = self._project_path()
      items = self._client._request_paginated(f"/projects/{proj}/variables")
      return [{
          "key": v.get("key"),
          "is_secret": bool(v.get("masked") or v.get("protected")),
          "has_value": True,
          "masked": v.get("masked"),
          "environment_scope": v.get("environment_scope") or "*",
      } for v in items]
  ```
- `backend/services/ado_variables.py` — agregar a `AdoVariablesProvider`:
  ```python
  def list_variables_scoped(self) -> list[dict]:
      """Plan 251 F3 — ADO no tiene scope por entorno en el modelo del plan 94
      (las variables viven en la DEFINITION). Devuelve lo mismo que
      list_variables() (:25) con environment_scope='*' fijo. Honestidad, no magia."""
      return [{**v, "environment_scope": "*"} for v in self.list_variables()]
  ```

**PROHIBIDO en esta fase:** tocar `list_variables`, `set_variable`, `delete_variable`,
`VARIABLES_PORT_METHODS` (`ci_variables.py:63`) o el `Protocol` `CIVariablesProvider` (`:45`).
El test `test_f2_port_structural_conformance` (`test_plan94_variables_providers.py:283`) usa
`hasattr` y compara `VARIABLES_PORT_METHODS` con una tupla literal: agregar un método está bien,
cambiar esa constante rompe.

**Tests PRIMERO** — `backend/tests/test_plan251_env_matrix_resolve.py`
(proveedores **mockeados** en su módulo de origen; **nunca** red):

- `test_f3_no_pide_lo_que_ya_existe` — **KPI-2**: requirements
  `[DB_PASSWORD(secret), buildConfiguration(variable), Build.BuildNumber(variable)]`;
  proveedor mockeado devuelve `DB_PASSWORD`; `declared` trae `buildConfiguration`.
  Resultado: `pending_count == 0`.
- `test_f3_gitlab_scope_por_entorno` — proveedor mockeado devuelve
  `[{key:"API_URL", environment_scope:"Test"}]` con entornos `("Test","Production")`:
  la celda Test es `definido/scope_proveedor` y la de Production queda `falta`.
- `test_f3_gitlab_scope_estrella_cubre_todo` — `environment_scope:"*"` ⇒ ambas `definido`.
- `test_f3_ado_definido_en_todos_los_entornos_con_nota` — proveedor `azure_devops`:
  la key definida marca `definido` en las 2 columnas y la nota contiene `"definition"`.
- `test_f3_fallback_sin_list_variables_scoped` — provider mock **sin** el método:
  `list_scoped_variables` cae a `list_variables()`, todo queda scope `"*"` y la tupla de
  degradaciones **no** está vacía.
- `test_f3_servidor_resuelve_por_alias` — `server_registry.list_servers` mockeado con
  `{"alias":"test-server","host":"10.0.0.5","has_password":True}` y requirement
  `kind="server", name="TEST-Server"` ⇒ `definido/registro_servidores`, nota
  `"credencial guardada"`.
- `test_f3_servidor_resuelve_por_host` — mismo mock, requirement `name="10.0.0.5"` ⇒ `definido`.
- `test_f3_servidor_desconocido_falta` — requirement `name="PROD-Server"` ⇒ sin entrada ⇒
  `build_matrix` lo deja en `falta`.
- `test_f3_ado_sin_definition_degrada_409` — el provider levanta `VariablesUnavailableError`:
  `list_scoped_variables` devuelve `([], (), [<mensaje con "plan 95">])` y **no** levanta.
- `test_f3_error_inesperado_mensaje_fijo` — el provider levanta
  `RuntimeError("boom S3cr3t!XYZ")`: la degradación es el mensaje FIJO y el literal
  `S3cr3t!XYZ` **no** aparece en `repr()` del retorno.
- `test_f3_use_provider_false_no_toca_red` — con `use_provider=False`, el mock del provider
  registra `0` llamadas.
- `test_f3_ningun_value_en_el_retorno` — centinela: el proveedor mockeado devuelve items con
  `value:"S3cr3t!"`; `json.dumps(resolutions, default=str)` **no** contiene `"S3cr3t!"` ni la
  clave `"value"`.

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_resolve.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan94_variables_providers.py -q
```

**Criterio de aceptación BINARIO:** 12 tests propios verdes **y**
`test_plan94_variables_providers.py` verde **sin modificar ni una línea** (prueba de que el
agregado fue aditivo). Además, grep binario:
`rg -n "logger|print\(" backend/services/pipeline_env_resolver.py` ⇒ **0 resultados**.

**Flag:** ninguna (sin consumidores hasta F4).
**Impacto por runtime:** ninguno. Lecturas HTTP por proveedores existentes, sin LLM, sin fallback.
**Trabajo del operador: ninguno.**

---

### F4 — Endpoint `/api/pipeline-environments` (solo lectura, con guard)

**Objetivo:** exponer la matriz. Una sola ruta de análisis y una key de health.

**Archivo NUEVO:** `backend/api/pipeline_environments.py`

```python
"""api/pipeline_environments.py — Blueprint de la matriz de entornos. Plan 251 F4."""
from __future__ import annotations
import config as _config
from flask import Blueprint, abort, jsonify, request

# url_prefix="/pipeline-environments" -> ruta final /api/pipeline-environments/...
# (registrado sobre api_bp en api/__init__.py; NO poner "/api" acá, NO registrar en app.py)
bp = Blueprint("pipeline_environments", __name__, url_prefix="/pipeline-environments")


def _guard():
    """Guard PER-REQUEST (nunca en el registro del blueprint)."""
    if not getattr(_config.config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", False):
        abort(404)
    if request.method == "POST" and not request.is_json:
        abort(400, description="Content-Type application/json requerido")
```

Ruta ÚNICA:

```python
@bp.route("/analyze", methods=["POST"])
def analyze():
    """POST por TRANSPORTE (el YAML viaja en el body, mismo patrón que
    POST /api/devops/parse-yaml del plan 87). Semántica de LECTURA: no escribe
    NADA — ni repo, ni proveedor, ni disco del operador.

    body: {yaml_text: str, provider: "azure_devops"|"gitlab",
           project?: str, resolve?: bool (default true)}
    200 -> {environments, requirements, cells, pending_count, degraded, provider}
    400 -> yaml_text ausente/vacío, o provider fuera del enum
    """
```

Reglas duras del handler:
1. `_guard()` primero, siempre.
2. `provider` debe estar en `("azure_devops","gitlab")`; si no ⇒ `abort(400)`.
3. `yaml_text` vacío o no-string ⇒ `abort(400, description="yaml_text requerido")`.
4. **Tope de tamaño:** `len(yaml_text) > 500_000` ⇒ `abort(400, description="YAML demasiado
   grande (máx 500 KB)")`. (Los 9 del corpus dorado están 3 órdenes de magnitud abajo.)
5. `resolve` es `bool`; cualquier otra cosa ⇒ `True`. Se pasa como `use_provider`.
6. **Antes de `jsonify`**, el payload completo pasa por `strip_secret_keys`
   (`services/secret_masking.py:25`) como red final.
7. **Prohibido** cualquier `logger`/`print` que toque `yaml_text` o el payload.

**Archivos a editar:**
- `backend/api/__init__.py` — import junto al del Plan 94 (`:50`) y
  `api_bp.register_blueprint(pipeline_environments_bp)` junto al `:123`, con el comentario
  `# Plan 251 — url_prefix="/pipeline-environments" → /api/pipeline-environments/...`.
- `backend/api/devops.py` — en `_health_payload()`, junto a la línea `:48` del Plan 94:
  ```python
  "env_matrix_enabled": bool(getattr(cfg, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", False)),  # Plan 251
  ```

**Tests PRIMERO** — `backend/tests/test_plan251_env_matrix_endpoints.py`
(cliente Flask; `pipeline_env_resolver.resolve` mockeado donde haga falta):

- `test_f4_flag_off_404` — con la flag OFF, `POST /api/pipeline-environments/analyze` da **404**.
- `test_f4_no_json_400` — `Content-Type` distinto de json ⇒ **400**.
- `test_f4_yaml_vacio_400` / `test_f4_provider_invalido_400`.
- `test_f4_yaml_gigante_400` — `yaml_text` de 500_001 chars ⇒ **400**.
- `test_f4_happy_bootstrap` — body con el contenido de
  `fixtures/cicd_nl/golden/bootstrap-server-environment.yml`, `provider="azure_devops"`,
  `resolve=false` ⇒ 200; `environments == ["Test","Production"]`; `pending_count > 0`;
  hay al menos un requirement con `kind == "server"`.
- `test_f4_happy_cd_deploy` — igual con `cd-deploy-test.yml` ⇒ `environments == ["Test"]`.
- `test_f4_resolve_false_no_toca_proveedor` — con `resolve:false`, el mock de
  `get_variables_provider` registra **0** llamadas.
- `test_f4_degradacion_visible` — el resolver mockeado devuelve degradaciones ⇒ el campo
  `degraded` del body las trae y el status sigue siendo **200** (degradar, no romper).
- `test_f4_ningun_valor_en_la_respuesta` — **KPI-3**: proveedor mockeado con
  `value:"S3cr3t!XYZ"` y un YAML con `variables: { DB_PASSWORD: 'p4ssw0rd' }` ⇒ el **texto crudo**
  de la respuesta no contiene `S3cr3t!XYZ` ni `p4ssw0rd`.
- `test_f4_health_tiene_env_matrix_enabled` — `GET /api/devops/health` trae la key nueva.
- `test_f4_ruta_registrada` — centinela sobre `app.url_map`:
  `/api/pipeline-environments/analyze` existe.

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_endpoints.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan94_variables_endpoints.py -q
```

**Criterio de aceptación BINARIO:** 12 tests propios verdes, `test_plan94_variables_endpoints.py`
verde, **y** el grep
`rg -n "logger|print\(" backend/api/pipeline_environments.py` ⇒ **0 resultados**.

**Flag:** `STACKY_PIPELINE_ENV_MATRIX_ENABLED` (guard **per-request**, `abort(404)` dentro del
handler — nunca gateando el registro del blueprint).
**Impacto por runtime:** ninguno. Flask puro, sin LLM, sin fallback.
**Trabajo del operador: ninguno.**

---

### F5 — Frontend: modelo puro + panel + entrada en el registro

**Objetivo:** que el operador vea la matriz, el titular "Te faltan N valores", y llegue en un
click al único formulario de escritura que ya existe (Plan 94).

**Archivo NUEVO (modelo PURO, sin React, sin I/O):**
`frontend/src/devops/pipelineEnvMatrixModel.ts`

```ts
// Tipos espejo del contrato §4.2 (backend services/pipeline_environments.py)
export type CellState = 'definido' | 'default' | 'falta' | 'manual';
export type ValueKind = 'variable' | 'secret' | 'service_connection'
                      | 'server' | 'deploy_path' | 'parameter';

export interface EnvCell { state: CellState; source: string; note: string | null; }
export interface EnvRequirement {
  name: string; kind: ValueKind; provider: string; is_secret: boolean;
  declared_default: string | null; per_environment: boolean;
  confidence: 'alta' | 'baja';
  evidence: Array<{ path: string; excerpt: string }>;
}
export interface EnvMatrixResponse {
  environments: string[]; requirements: EnvRequirement[];
  cells: Record<string, EnvCell>;   // clave "<name>\u0000<env>"
  pending_count: number; degraded: string[]; provider: string;
}

/** cellKey — la MISMA convención que arma el backend. */
export function cellKey(name: string, env: string): string;

/** pendingByEnvironment — {env: cuántas celdas "falta"}. Puro. */
export function pendingByEnvironment(m: EnvMatrixResponse): Record<string, number>;

/** headline — el titular único. 0 -> "No falta nada: esta pipeline tiene todo lo que
 *  necesita." N -> "Te faltan N valores para que esta pipeline pueda correr." */
export function headline(m: EnvMatrixResponse): string;

/** sortRequirements — orden de presentación DETERMINISTA: primero los que tienen
 *  celdas "falta", después "default", después "manual", después "definido"; dentro de
 *  cada grupo, alfabético por name. Inmutable (no muta el array de entrada). */
export function sortRequirements(m: EnvMatrixResponse): EnvRequirement[];

/** canCompleteInStacky — true sólo para kind 'variable' | 'secret'. Los demás no se
 *  cargan por API en v1 (server -> sección Servidores; service_connection y
 *  deploy_path -> manual). Gobierna qué CTA se muestra. */
export function canCompleteInStacky(r: EnvRequirement): boolean;
```

**Archivo NUEVO (componente):**
`frontend/src/components/devops/PipelineEnvMatrixPanel.tsx`

- Props `{ ctx: DevOpsSectionContext }` (mismo shape que consume
  `EnvironmentsSection.tsx:39`). **El gate de SU flag NO vive acá**: lo renderiza el shell vía la
  entrada declarativa.
- Fuente del YAML, en este orden con degradación explícita:
  1. Si `ctx` expone el inventario del **Plan 246**, selector de pipeline.
  2. Si no, el YAML del builder activo (`PipelineBuilderSection`).
  3. Si no hay ninguno, textarea de pegado + botón "Analizar".
  Con el 246 ausente, el panel **funciona igual** y muestra la nota
  *"El inventario de pipelines (plan 246) no está disponible: analizá el YAML activo o pegá uno."*
- Encabezado: `headline(m)` en grande. Debajo, chips por entorno con `pendingByEnvironment`.
- Tabla: filas = `sortRequirements(m)`, columnas = `m.environments`. Cada celda:
  `definido` ✅ / `default` ⚪ (con el valor del default a la vista) / `falta` 🔴 / `manual` ⚙️.
  **Nunca se renderiza un valor que no venga del backend.**
- Cada fila expande sus `evidence` (`path` + `excerpt`, ya enmascarados por el backend).
- **CTA por fila**, gobernado por `canCompleteInStacky`:
  - `variable`/`secret` ⇒ botón **"Completar"** que abre el modal del **Plan 94** con `key`
    pre-cargada y "Es secreta 🔒" pre-tildado según `is_secret`; el guardado usa
    `DevOpsVariables.create` (`endpoints.ts:4303`) **sin cambios**, con su `confirm:true`.
    **El valor lo escribe el operador; Stacky nunca lo propone.**
    Si `m.provider === 'gitlab'` y `m.environments.length > 1`, mostrar arriba del modal el texto
    literal: *"Se va a crear con alcance global (`*`): el Plan 94 no scopea por entorno todavía."*
  - `server` ⇒ botón **"Registrar servidor"** que navega a la sección `servidores`.
  - `service_connection` / `deploy_path` ⇒ **sin botón**, con la nota `manual` y el texto
    *"Esto no lo puede hacer Stacky: queda documentado en el paquete de entrega (plan 252)."*
- `m.degraded` se muestra siempre como banner ámbar, íntegro. Nunca se oculta una degradación.
- Errores async siempre visibles en pantalla. **Prohibido** `console.*` como único canal.
- **Prohibido `style={{...}}` inline** (el ratchet `uiDebtRatchet` cuenta con alcance 0 en `.tsx`
  nuevos): usar el CSS module hermano `PipelineEnvMatrixPanel.module.css`.

**Archivos a editar:**
- `frontend/src/api/endpoints.ts` — namespace nuevo `PipelineEnvironments`, junto a
  `DevOpsVariables` (`:4298`):
  ```ts
  export const PipelineEnvironments = {
    analyze: (body: { yaml_text: string; provider: string; project?: string; resolve?: boolean }) =>
      api.post<EnvMatrixResponse>("/api/pipeline-environments/analyze", body),
  };
  ```
  **Gotcha:** `api.post` **lanza excepción** en cualquier non-2xx. El panel debe envolver la
  llamada en `try/catch` y mostrar el error; **no** asumir que un 400 llega como valor.
- `frontend/src/pages/DevOpsPage.tsx` — **UNA** entrada declarativa en `DEVOPS_SECTIONS`
  (`:113`), inmediatamente después de la de `id:'variables'` (`:174-179`), con el shape exacto
  de `:79-81`:
  ```tsx
  {
    id: 'matriz-entornos',
    label: 'Matriz de entornos',
    icon: '🧭',
    healthKey: 'env_matrix_enabled',
    gateFlagKey: 'STACKY_PIPELINE_ENV_MATRIX_ENABLED',
    gateMessage: 'La sección Matriz de entornos necesita la flag STACKY_PIPELINE_ENV_MATRIX_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <PipelineEnvMatrixPanel ctx={ctx} />,
  },
  ```
  **PROHIBIDO tocar `DevOpsPage.tsx` fuera de ese array.**

**Tests PRIMERO** — `frontend/src/devops/__tests__/pipelineEnvMatrixModel.test.ts`:
- `cellKey_es_estable` — misma entrada, misma clave; claves distintas para env distintos.
- `pendingByEnvironment_cuenta_solo_falta` — fixture con 3 estados ⇒ conteo exacto por entorno.
- `headline_cero` — `pending_count: 0` ⇒ el string contiene `"No falta nada"`.
- `headline_n` — `pending_count: 3` ⇒ contiene `"3"`.
- `sortRequirements_prioriza_falta` — el primero del array tiene una celda `falta`; el último
  está todo `definido`.
- `sortRequirements_es_inmutable` — el array `requirements` original no cambia de orden.
- `canCompleteInStacky_solo_variable_y_secret` — `true` para `variable`/`secret`; `false` para
  `server`, `service_connection`, `deploy_path`, `parameter`.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineEnvMatrixModel.test.ts
npx vitest run src/devops/variablesModel.test.ts
npx tsc --noEmit
```

**Criterio de aceptación BINARIO:**
1. 7 tests vitest propios verdes **y** `variablesModel.test.ts` verde (no-regresión del 94).
2. `npx tsc --noEmit` ⇒ **0 errores**.
3. Grep `rg -n "style=\{\{" frontend/src/components/devops/PipelineEnvMatrixPanel.tsx` ⇒
   **0 resultados**.
4. Grep `rg -n "PipelineEnvMatrixPanel.tsx" -e "STACKY_PIPELINE_ENV_MATRIX_ENABLED"` ⇒
   **0 resultados** (el gate lo hace el shell, no el componente).
5. **KPI-5 (paridad de runtimes):** grep
   `rg -n "invoke_local_llm|llm_router|copilot_bridge|claude_code_cli|codex_cli" backend/services/pipeline_environments.py backend/services/pipeline_env_resolver.py backend/api/pipeline_environments.py`
   ⇒ **0 resultados**. Cero LLM en todo el plan.

**Flag:** `env_matrix_enabled` (gate declarativo del shell, vía `healthKey`).
**Impacto por runtime:** ninguno. React + Flask, sin LLM, sin fallback.
**Trabajo del operador:** **ninguno** para que la sección aparezca (default ON). Completar los
valores que faltan **es** la feature, y es exactamente el trabajo que ya tenía — con la
diferencia de que ahora está enumerado.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación (codificada, con su test) |
|---|---|
| Falsos positivos: `$(...)` de bash o `$var` de PowerShell reportados como faltantes | Regla `_SHELL_KEYS` del §4.4: dentro de un bloque de shell, sólo cuenta lo ya declarado; el resto va con `confidence="baja"` y **nunca** llega a `falta`. `test_f1_powershell_no_es_variable_de_pipeline` |
| Ruido: 40 variables predefinidas de ADO en la matriz | Allowlist cerrada `_ADO_PREDEFINED_PREFIXES`/`_EXACT`. `test_f1_predefinidas_de_ado_nunca_se_piden` |
| Referencias dentro de **comentarios** contadas como requerimientos | Se camina el documento `yaml.safe_load` (mismo criterio que `scan_unsupported`, `pipeline_renderers.py:51-57`), nunca el texto. Grep binario en el criterio de F1 |
| Inventar entornos que el operador no tiene | `derive_environments` sólo une evidencia; sin evidencia ⇒ una columna `(único)`. `test_f2_sin_evidencia_una_sola_columna` (**KPI-4**) |
| Fuga de un secreto por la respuesta o un log | Triple red: `mask_token_values` en cada `excerpt`, `MASK_PLACEHOLDER` en los defaults de keys secretas, `strip_secret_keys` sobre el payload completo; + grep binario de `logger`/`print` en los 3 archivos nuevos. `test_f3_ningun_value_en_el_retorno`, `test_f4_ningun_valor_en_la_respuesta` (**KPI-3**) |
| Un `str(e)` de una excepción del proveedor filtra un valor | Mensajes FIJOS en `list_scoped_variables`; `TrackerApiError` reporta sólo el código. `test_f3_error_inesperado_mensaje_fijo` |
| ADO no scopea variables por entorno ⇒ la matriz podría mentir "está definido en Producción" | Nota literal obligatoria en cada celda (§3.6). `test_f2_nota_ado_sin_scoping` |
| GitLab no devuelve `environment_scope` (versión vieja / campo distinto) | `v.get("environment_scope") or "*"`: todo cae a global, la degradación se reporta en `degraded` y se ve en el banner. `test_f3_fallback_sin_list_variables_scoped` |
| ADO sin pipeline definition ⇒ `VariablesUnavailableError` rompe el análisis | Se captura y se convierte en degradación; el análisis **sigue** y devuelve 200 con la matriz sin resolución de proveedor. `test_f3_ado_sin_definition_degrada_409`, `test_f4_degradacion_visible` |
| Romper el contrato del Plan 94 al agregar el scope | Método **nuevo** (`list_variables_scoped`), `VARIABLES_PORT_METHODS` y el `Protocol` intactos. Criterio de F3: `test_plan94_variables_providers.py` verde **sin editar** |
| Match servidor↔registro por heurística de nombre (falso positivo) | Match exacto case-insensitive contra `alias` **y** `host` — nunca substring; si no matchea, `falta` honesto. `test_f3_servidor_desconocido_falta` |
| Degradar performance del panel | Análisis **bajo demanda**, una pipeline por vez, una lectura al proveedor por análisis; `resolve:false` no toca la red; tope de 500 KB por YAML. `test_f3_use_provider_false_no_toca_red`, `test_f4_yaml_gigante_400` |
| El operador cree que "Completar" scopea al entorno en GitLab | Texto literal obligatorio en el modal cuando hay >1 entorno (F5) |
| Flag mal cableada ⇒ meta-tests rojos en silencio | Las 6 patas de F0, con `_CURATED_DEFAULTS_ON` y `_REQUIRES_MAP_FROZEN` explícitas y sus comandos |
| `requires` encadenado rompe R4 | `requires="STACKY_DEVOPS_PANEL_ENABLED"` (master de raíz), con la evidencia del desvío análogo del Plan 104 en `harness_flags.py:3158-3168`. `test_f0_requires_es_el_master_del_panel` |

---

## 7. Fuera de scope (nombrando los planes de la serie)

- **Descubrir qué pipelines existen** → **Plan 246** (`pipeline_inventory.py`). Este plan consume
  su registro si está; si no, funciona con el YAML activo o pegado.
- **Perfilar stack / anatomía / propósito** → **Plan 247** (`pipeline_profiler.py`).
- **Reglas de seguridad y malas prácticas (`SEC001..SECnn`)** → **Plan 248**. Este plan **no**
  emite hallazgos de seguridad sobre el YAML: si detecta un secreto en texto plano dentro de
  `variables:`, sólo lo enmascara y lo marca `es_secreto` en su fila. La regla `SEC*` que lo
  denuncia es del 248.
- **Catálogo y reglas GitLab (`GL001..GLnn`)** → **Plan 249**.
- **Editar el YAML por lenguaje natural** → **Plan 250** (`pipeline_patcher.py`). Este plan **no
  toca el YAML**: sólo lo lee.
- **Generar el `.zip` y el README operativo con lo que queda manual** → **Plan 252**. Este plan le
  entrega la lista estructurada de celdas `falta` y `manual`; el 252 la convierte en
  documentación. **No se escribe ningún README acá.**
- **Escribir/publicar variables al proveedor desde la matriz.** Lo hace el **Plan 94** tal cual
  está (`POST /api/devops/variables` con `confirm:true`), sin una línea de cambio. Una escritura
  en lote desde la matriz sería un plan propio con flag `default=False` (excepción 1: bypasea
  revisión humana; excepción 4: reduce seguridad por default).
- **Scoping por entorno al ESCRIBIR:** `environment_scope` de GitLab y variable groups /
  definitions múltiples de ADO. Este plan los **lee y los reporta**; crearlos queda afuera
  (el Plan 94 §7 ya los declaró fuera de scope y esa frontera no se mueve acá).
- **Escribir en el servidor del operador o ejecutar algo remoto.** Fuera de scope **duro**: no
  hay una sola operación de escritura ni de ejecución en las 6 fases.
- **Persistir la matriz.** Se recalcula siempre. Cero estado duplicado (riel §3.9 del Plan 94).
- **Rellenar valores con IA.** Stacky no propone valores. HITL innegociable (§3.5).

---

## 8. Glosario

- **Requerimiento (`Requirement`)**: un valor que la pipeline necesita para correr, con su tipo,
  su evidencia en el YAML y si es secreto. No incluye el valor.
- **Celda (`Cell`)**: el cruce de un requerimiento con un entorno. Cuatro estados:
  `definido` (alguien ya lo tiene), `default` (el YAML trae uno y el operador sólo confirma),
  `falta` (**el único trabajo real**), `manual` (Stacky no puede resolverlo ni pedirlo por API).
- **Entorno derivado**: nombre de entorno obtenido de evidencia (`environment:` de un
  `- deployment:`, `values:` de un parámetro, o `environment_scope` del proveedor). Nunca una
  lista fija.
- **Variable predefinida (ADO)**: `$(Build.*)`, `$(Agent.*)`, `$(Pipeline.*)`, `$(System.*)`… las
  provee el agente. Jamás se le piden al operador.
- **`environment_scope` (GitLab)**: alcance por entorno de una variable CI/CD. `*` = todos.
  Cero ocurrencias en el repo hoy (verificado): este plan es el primero que lo lee.
- **Service connection (ADO)**: credencial gestionada por Azure DevOps hacia un servicio externo.
  No se crea ni se verifica por API en este plan ⇒ estado `manual`.
- **Confianza (`confidence`)**: `alta` = el requerimiento surge de un constructo inequívoco;
  `baja` = surge de un contexto ambiguo (bloque de shell, `displayName`). **Una celda de confianza
  baja nunca llega al estado `falta`** — no se le pide trabajo al operador por una sospecha.
- **Degradación**: motivo, en llano, por el que una fuente no pudo consultarse. Siempre visible,
  nunca silenciada, y nunca convierte el análisis en un error.

---

## 9. Orden de implementación

1. **F0** — flag (6 patas: `config.py`, `harness_flags.py` ×2, `harness_flags_help.py`,
   `_CURATED_DEFAULTS_ON`, `_REQUIRES_MAP_FROZEN`, ratchet en `run_harness_tests.sh`).
2. **F1** — `services/pipeline_environments.py`: extracción pura (el corazón).
3. **F2** — mismo archivo: `derive_environments` + `build_matrix`.
4. **F3** — `services/pipeline_env_resolver.py` + los 2 métodos aditivos `list_variables_scoped`.
5. **F4** — `api/pipeline_environments.py` + registro en `api/__init__.py` + key de health.
6. **F5** — `pipelineEnvMatrixModel.ts` + `PipelineEnvMatrixPanel.tsx` + entrada en
   `DEVOPS_SECTIONS`.

F1 y F2 se pueden hacer y validar **sin backend levantado ni red**: son puras. Si el
implementador tiene poco presupuesto, F0+F1+F2 ya entregan un núcleo verificable y F3–F5 se
apilan encima sin retrabajo.

---

## 10. Definición de Hecho (DoD binaria)

- [ ] **53 tests backend** propios verdes, corridos **por archivo** con
      `backend\.venv\Scripts\python.exe`: F0 5 + F1 14 + F2 10 + F3 12 + F4 12 = **53**. Los
      greps binarios de F1, F3, F4 y F5 son criterios de aceptación, no tests, y van aparte.
- [ ] **7 tests vitest** propios verdes + `variablesModel.test.ts` verde + `npx tsc --noEmit` con
      **0 errores**.
- [ ] **No-regresión verde sin editar esos archivos:** `test_harness_flags.py`,
      `test_harness_flags_requires.py`, `test_harness_ratchet_meta.py`,
      `test_plan94_variables_providers.py`, `test_plan94_variables_endpoints.py`.
      (`test_harness_flags_help` tiene 4 rojos **ajenos** preexistentes: validá tu entrada aparte.)
- [ ] **Flag OFF ⇒ byte-idéntico:** `POST /api/pipeline-environments/analyze` da 404, la sección
      muestra el `FlagGateBanner` del shell y nada más cambia.
- [ ] **KPI-2:** `test_f3_no_pide_lo_que_ya_existe` verde — `pending_count == 0` cuando todo ya
      existe en alguna fuente.
- [ ] **KPI-3:** ningún valor de secreto aparece en respuesta, log ni excepción (los 2 centinelas
      verdes) y los 3 greps de `logger|print` dan 0.
- [ ] **KPI-4:** `derive_environments` sobre los 3 YAML reales abiertos da, respectivamente,
      `("Test","Production")`, `("Test",)` y `("(único)",)`.
- [ ] **KPI-5:** el grep de LLM sobre los 3 archivos backend nuevos da **0 resultados**.
- [ ] **Cero escritura:** grep binario
      `rg -n "set_variable|delete_variable|\.write_text|open\(.*[\"']w|requests\.(post|put|delete)|_request\(\"(POST|PUT|DELETE)" backend/services/pipeline_environments.py backend/services/pipeline_env_resolver.py backend/api/pipeline_environments.py`
      ⇒ **0 resultados**.
- [ ] **Contrato del Plan 94 intacto:** `VARIABLES_PORT_METHODS` sin cambios, `Protocol`
      `CIVariablesProvider` sin cambios, `list_variables`/`set_variable`/`delete_variable` sin
      cambios.
- [ ] `DevOpsPage.tsx` tocado **sólo** dentro del array `DEVOPS_SECTIONS`.
- [ ] Los 5 archivos `test_plan251_*.py` registrados en `HARNESS_TEST_FILES` de
      `backend/scripts/run_harness_tests.sh`.
- [ ] `backend/harness_defaults.env` **no** modificado a mano.
- [ ] **Smoke visual (manual, único):** abrir el panel, analizar
      `bootstrap-server-environment.yml`, ver dos columnas (Test / Producción), el titular
      "Te faltan N valores", `iisPort` en estado `default` con su `0`, y `TEST-Server` resuelto o
      en `falta` según el registro de servidores real.
