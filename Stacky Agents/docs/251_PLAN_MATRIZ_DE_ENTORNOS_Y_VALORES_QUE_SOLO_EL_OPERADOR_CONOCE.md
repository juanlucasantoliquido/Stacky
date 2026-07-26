# Plan 251 — Matriz de entornos: los valores que sólo el operador conoce

> ## ESTADO REAL AL 2026-07-26: **IMPLEMENTADO — F0..F5 COMPLETAS**
>
> Implementado y commiteado en `feat/plan-217-migrador-mantis-gitlab`. **Backend 81 tests verdes
> corridos por archivo con `backend/.venv` (py3.13.5); frontend 10 verdes + `npx tsc --noEmit`
> en 0 errores.**
>
> | Fase | Estado | Archivo de test | Resultado real |
> |---|---|---|---|
> | F0 flag en sus 7 patas | IMPLEMENTADA | `test_plan251_env_matrix_flag.py` | **7 passed** |
> | F1 núcleo puro de detección | IMPLEMENTADA | `test_plan251_env_matrix_extract.py` | **29 passed** |
> | F2 entornos derivados + matriz | IMPLEMENTADA | `test_plan251_env_matrix_build.py` | **14 passed** |
> | F3 resolución solo-lectura | IMPLEMENTADA | `test_plan251_env_matrix_resolve.py` | **15 passed** |
> | F4 endpoint `/analyze` | IMPLEMENTADA | `test_plan251_env_matrix_endpoints.py` | **16 passed** |
> | F5 modelo puro + panel | IMPLEMENTADA | `pipelineEnvMatrixModel.test.ts` | **10 passed**, `tsc` 0 errores |
>
> No-regresión verde: `test_harness_flags.py` **56**, `test_harness_flags_requires.py` **9**,
> `test_harness_ratchet_meta.py` **4**, `test_plan94_variables_providers.py` **13** y
> `test_plan94_variables_endpoints.py` **14** — los dos últimos **sin tocar ni una línea**
> (el agregado a los adapters fue aditivo y `VARIABLES_PORT_METHODS` quedó intacta).
>
> **Medición real del KPI-6 sobre los 9 goldens** (no los 3 que el plan abrió a mano):
> `agendaweb-ci` 5 · `bootstrap-server-environment` 12 · `cd-deploy-test` 5 · `ci-batch` 4 ·
> `ci-cd-online` 4 · `ci-dacpac` 2 · `nightly-build-online` 3 · `pr-validation-online` 4 ·
> `security-scan-online` 2. **Ninguno pasa de 12; el techo del KPI era 40.**
>
> ### Los 4 bugs del PROPIO PLAN que sólo aparecieron al construirlo
>
> 1. **El `Requirement` del §4.2 no tiene campo `note`, pero su propio test lo exige.**
>    `test_f1_bootstrap_servidor_desde_parametro` pide *"una `note` que contiene la palabra
>    `default`"* (C13: el pool sale del default de un parámetro y eso es una **suposición**, no un
>    hecho). El dataclass del §4.2 no la declara y la `note` del §4.3 vive en la `Cell`, que se
>    construye en F2 y no tiene de dónde sacarla. Corregido: `Requirement.note: str = ""`, aditivo,
>    y `build_matrix` la propaga a todas las celdas del requirement.
> 2. **`test_f1_modulo_puro` era IMPOSIBLE por construcción — el mismo gotcha que el plan
>    corrigió en C1 y se olvidó de aplicar acá.** El test prohíbe la subcadena `print(` en
>    `services/pipeline_environments.py`, y ese módulo **debe** definir `pending_fingerprint(`
>    (§4.2-bis), que la contiene literalmente. Igual que `Blueprint(`. Corregido: el gate va con
>    `\bprint\(` y `\blogger\.`, y el test **verifica el propio gate** contra la cadena
>    `pending_fingerprint(cells)`.
> 3. **`_ABS_PATH_EMBEDDED_RE` tal como está escrita produce exactamente el ruido que el plan
>    dice temer.** La rama unix `(?<=\s)/[^\s"'\)\],]{2,}` matchea, dentro de un `msbuildArgs: >-`
>    multilínea, `/p:WebPublishMethod=Package`, `/p:PackageAsSingleFile=true`,
>    `/p:SkipInvalidConfigurations=true`, `/p:PackageLocation=` y
>    `/p:AutoParameterizationWebConfigConnectionStrings=false`: **5 "rutas de despliegue" falsas en
>    4 de los 9 goldens** (medido). Eso es el riesgo nº1 declarado en el propio plan. Corregido:
>    la rama unix exige **dos segmentos** (`/a/b`); la de Windows queda igual. Test de regresión:
>    `test_f1_corpus_dorado_no_inventa_rutas_de_msbuild`.
> 4. **`resolve()` no puede cumplir su propia regla de precedencia 3.** La firma del §F3 es
>    `resolve(requirements, environments, provider, project, use_provider)` pero la regla 3 es
>    *"`name` en `declared_variables`"*, y `declared_variables` sale del YAML, que la función no
>    recibe. Sin eso, `test_f3_no_pide_lo_que_ya_existe` (KPI-2) no puede dar `pending_count == 0`.
>    Corregido: kwarg `yaml_text: str = ""` (opcional, retrocompatible).
>
> ### El peligro nº1 de este plan (fuga de secretos), verificado de verdad
>
> El v1 filtraba secretos y la v2 lo corrigió **a medias**. Medido leyendo `secret_masking.py`:
> `mask_token_values` reconoce **7 prefijos** y `looks_secret` decide **sólo por nombre**. Por lo
> tanto **el caso `SONAR_HOST: 'Xk7#pQ2mZr9Lw4Tv'` —un password real que no es un token conocido,
> bajo un nombre que no suena a secreto— pasaba por las DOS redes de la v2 y salía verbatim.** Los
> centinelas de la v2 usan `glpat-...`, que **sí** matchea la red A: probaban el caso que ya
> funcionaba, un escalón más arriba que la v1 pero con el mismo vicio.
>
> Se agregó una **red A' por forma genérica** (`looks_like_credential_value`): ≥16 chars, sin
> espacios, sin `$(`/`${{`, sin `/` ni `\`, y con **≥3 clases de caracteres**. Con:
>
> - `test_f1_password_arbitrario_bajo_nombre_inocente_tampoco_sale` y
>   `test_f4_password_arbitrario_bajo_nombre_inocente_no_sale` (el caso adversarial), y
> - **`test_f1_la_red_de_forma_no_tapa_valores_legitimos`, el control negativo**: `Release`,
>   `Any CPU`, `windows-2022`, `AgendaWeb-drop`, `trunk/OnLine/.../AgendaWeb.sln`, `us-east-1`,
>   `$(Build.ArtifactStagingDirectory)`, `C:\AIS\AgendaWeb\Web`, `succeededOrFailed()`, `6.x` y
>   `High` **NO** se enmascaran. Una red que tapa medio corpus es peor que el problema.
>
> Las otras dos garantías siguen firmes y probadas: el `value` del proveedor **nunca** entra al
> payload (`test_f3_ningun_value_en_el_retorno` + `test_f4_ningun_valor_en_la_respuesta`), y el
> `str(e)` de una excepción desconocida **nunca** se propaga (`test_f3_error_inesperado_mensaje_fijo`).
>
> ### Lo que queda pendiente (declarado)
>
> - **Smoke visual del operador** (no automatizable: sin `jsdom`): abrir DevOps → *Matriz de
>   entornos*, pegar una pipeline real, ver el titular *"Te faltan N valores"* y los CTA.
> - La **vía B** (elegir de la lista del inventario del Plan 246) está cableada por `readInventory`
>   pero el 246 no expone `pipelineInventory` en el `ctx`: el panel degrada con la nota explícita y
>   la vía "pegar el YAML" funciona sola, como manda §2.3.
> - **Ratchets rojos AJENOS** (no crecidos por este plan): `formDebtRatchet` (7 ofensores, ninguno
>   de este plan) y `devopsPollingRatchet` (BuildWorkshopSection.tsx:93).
>
> ---
>
> Implementados y commiteados en esta misma rama, en orden: **246** (`f2e63e77`), **247**
> (`d006e406`), **248** (`ed9a1942`), **249** (`7fc345d8`), **250** (`98ee7d15`).

---

**Estado:** CRITICADO v2 (v1 → v2)
**Veredicto del juez:** **RECHAZADO en v1** por 5 bloqueantes → **APROBADO-CON-CAMBIOS en v2**
(los 5 bloqueantes están corregidos abajo; ver §11).
**Juez:** revisión adversarial INDEPENDIENTE (no la escribió el mismo agente que redactó la v1).
**Fecha v1:** 2026-07-26 · **Fecha v2:** 2026-07-26

---

## CHANGELOG v1 → v2

Todos los anclajes `archivo:línea` de la v1 fueron **reverificados uno por uno** abriendo los
archivos. Resultado: **2 anclajes falsos** (off-by-one, C15) sobre ~60 verificados; los 18 anclajes
al corpus dorado dieron **100% correctos** (a diferencia del dossier del 243, que estaba corrido
una línea). Lo que cambió:

- **C1 (BLOQ)** — el criterio de aceptación de F4 era **inalcanzable**: `rg "logger|print\("`
  matchea `Blueprint(` (contiene literalmente `print(`). Gate reescrito con `\bprint\(` en F4, F3 y
  el DoD.
- **C2 (BLOQ)** — `_ABS_PATH_RE` estaba **anclada en `^`** pero las rutas que el plan cita como
  evidencia (`cd-deploy-test.yml:136,175`) están **embebidas** en un `displayName`. El test
  `test_f1_cd_deploy_rutas_absolutas` no podía pasar. Regex partida en dos (anclada + embebida).
- **C3 (BLOQ)** — `EnvMatrix.cells` con **claves tupla** no es serializable: `jsonify` revienta y
  `test_f3_ningun_value_en_el_retorno` (`json.dumps(...)`) **no podía ni correr**
  (`TypeError: keys must be str`). `cells` pasa a ser una **lista de dicts**; muere el separador
  `\u0000` y con él una clase entera de bugs.
- **C4 (BLOQ)** — F5 se **autoprohibía**: exigía "PROHIBIDO tocar `DevOpsPage.tsx` fuera del array"
  pero el panel necesita su `import` (fuera del array) y su key en `DevOpsHealth` (`:32-50`).
  Ahora se enumeran las **3 ediciones exactas** permitidas.
- **C5 (BLOQ, seguridad)** — **KPI-3 no se cumplía**: `mask_token_values` sólo enmascara **7
  prefijos** de token conocidos (`secret_masking.py:11`) y `looks_secret` decide **sólo por
  nombre**. Un secreto en claro bajo nombre inocente salía **verbatim**. Los 2 centinelas usaban
  `DB_PASSWORD` (nombre que sí matchea) ⇒ validaban el caso fácil. Fix: `mask_token_values` se
  aplica **siempre** a `declared_default` + 2 tests negativos nuevos.
- **C6..C14 (IMPORTANTES)** — contradicción regla-4 vs su propio test; `run_harness_tests.ps1`
  omitido (el 251 era el **único** de los 7 planes de la serie que no lo nombra); frontera §0.3
  del 246 excedida en 5 archivos; puntos de inserción contrarios al orden de merge de la serie;
  falta el test del **default efectivo** en `config.py`; costo real en ADO (`find_yaml_definition`
  hace hasta **51 GETs**, no "una lectura"); dependencia del 246 que rompe `tsc`; adivinanza del
  pool por default de parámetro; gate `rg` malformado en F5.
- **C15..C21 (MENORES)** — 2 anclajes off-by-one corregidos, campo muerto `per_environment` ahora
  consumido, enums cerradas ahora testeadas, y limpieza de la dependencia fantasma con el 247.
- **[ADICIÓN ARQUITECTO 1]** — `test_f1_corpus_dorado_sin_ruido`: gate sobre los **9** YAML del
  corpus (la v1 declaró en §2.4 haber abierto sólo 3). Convierte una deuda declarada en un
  criterio binario y ataca el riesgo real nº1 del plan: que la matriz sea ruido.
- **[ADICIÓN ARQUITECTO 2]** — `pending_fingerprint`: huella determinista de "lo que falta", para
  que el operador vea si su trabajo bajó entre dos análisis y para que el Plan 252 sepa a qué foto
  corresponde su paquete. Puro, sin persistencia, sin LLM.

**Conteo de tests: 53 → 60 backend, 7 → 8 vitest.**

---

**Serie:** "Mago de las Pipelines" — plan **251 de 246–252**.
**Dependencias:** consume el registro del **246** y el perfil del **247** si existen; **degrada
sin ellos** (ver §2.3). Se monta ENCIMA de la caja fuerte del **Plan 94** (`services/ci_variables.py`),
del registro de servidores del **Plan 91** (`services/server_registry.py`) y del masking común del
**Plan 195** (`services/secret_masking.py`). **No crea una segunda caja fuerte.**
**Flag:** `STACKY_PIPELINE_ENV_MATRIX_ENABLED`, default **ON**.
**Escribe:** NADA. Ni en el repo, ni en el proveedor, ni en el servidor del operador. Ver §3.2.

---

## 0. Frontera de superficie — enmienda declarada al §0.3 del Plan 246 (C8)

El `§0.3` del **246** (`docs/246_PLAN_INVENTARIO_VIVO_DE_PIPELINES_MULTIPROVEEDOR.md:95-145`,
verificado) reserva al 251 **exactamente 4 archivos exclusivos**:
`services/pipeline_environments.py`, `api/pipeline_environments.py`,
`frontend/src/devops/pipelineEnvMatrixModel.ts`,
`frontend/src/components/devops/PipelineEnvMatrixPanel.tsx`.

Este plan necesita **5 archivos más**. No se los apropia en silencio: los declara, prueba que
**nadie más de la serie los reclama**, y fija cómo se mergean.

| Archivo extra | Por qué | ¿Lo reclama otro plan 246–252? | Tipo de cambio |
|---|---|---|---|
| `backend/services/pipeline_env_resolver.py` (**crea**) | Aísla el I/O para que `pipeline_environments.py` quede puro **para siempre** y `test_f1_modulo_puro` no se vuelva frágil | **NO** — `grep -l "pipeline_env_resolver" docs/24*.md docs/25*.md` devuelve **sólo el 251** (verificado) | Archivo nuevo, cero conflicto |
| `backend/services/gitlab_variables.py` (**edita**) | `+1 método` `list_variables_scoped` | **NO** — sólo el 252 lo *menciona en prosa* (`252:168`, un `ls` de verificación); ningún plan lo edita | **Aditivo**: 1 método al final de la clase |
| `backend/services/ado_variables.py` (**edita**) | idem | **NO** — el 246 lo cita como evidencia (`246:382`) pero su reserva exclusiva es `ado_ci_provider.py`, otro archivo | **Aditivo** |
| `backend/services/harness_flags_help.py` (**edita**) | 1 `PlainHelp` | **SÍ, los 7** (242 y 246–252 lo nombran) — es una **6ª superficie universal** que el §0.3 omitió | **Aditivo**, unión de líneas |
| `backend/tests/test_harness_flags_requires.py` (**edita**) | 1 arista en `_REQUIRES_MAP_FROZEN` | **SÍ, todos los que declaran `requires`** — **7ª superficie universal** omitida por el §0.3 | **Aditivo, pero el assert es igualdad de mapas** (`:288`): un merge que pierda una línea deja rojo |

**Instrucción de merge (respeta el orden canónico del §0.3: 248, 250 y 251 en paralelo, todos
rebasados sobre el 247):** en las 7 superficies universales, **agregar siempre al FINAL** del
bloque correspondiente, nunca en el medio. Ver C9 en §5-F4 y §5-F5.

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
| **KPI-3 — Cero fuga de secretos** | El valor de un secreto no aparece NUNCA en la respuesta, ni en un log, ni en un mensaje de error. Sólo `definido`/`falta`. **Dos ejes, porque `looks_secret` decide por NOMBRE y `mask_token_values` por FORMA del valor, y ninguno solo alcanza (C5):** (a) nombre secreto ⇒ `test_f4_ningun_valor_en_la_respuesta`; (b) **nombre inocente con valor con forma de token** ⇒ `test_f1_valor_token_nombre_inocente` + `test_f4_secreto_con_nombre_inocente_no_sale`. |
| **KPI-6 — Cero ruido en el corpus completo** `[ADICIÓN ARQUITECTO 1]` | Sobre los **9** YAML de `fixtures/cicd_nl/golden/` (no sólo los 3 que se abrieron): ningún archivo produce un `Requirement` con nombre vacío, con espacios, empezado en `$`, ni de la allowlist predefinida; y ninguno supera **40** requirements. Test: `test_f1_corpus_dorado_sin_ruido`. |
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
| Adapter ADO | `backend/services/ado_variables.py:25 (AdoVariablesProvider.list_variables)`, **`:43`** (devuelve `masked: None` — la v1 decía `:44`, **anclaje falso**, C15), `:17` (llama a `find_yaml_definition`, importada en `:3`) | Variables de la pipeline **definition** (globales a la definition). **OJO costo (C11):** `find_yaml_definition` (`services/ado_pipeline_definitions.py:82`) lista hasta 50 definitions y hace **un GET de detalle por cada una sin `process`** (`:97-110`) ⇒ construir el provider ADO cuesta hasta **51 GETs**, no uno. |
| Adapter GitLab | `backend/services/gitlab_variables.py:22 (GitLabVariablesProvider.list_variables)`, `:30 (_request_paginated)`, `:37 (is_secret = masked or protected)` | Variables CI/CD del proyecto, paginadas. |
| Endpoint write-only + HITL | `backend/api/devops_variables.py:8 (bp, url_prefix="/devops/variables")`, **`:60 (def create_variable)`** (la v1 decía `:59`, que es el decorador — **anclaje falso**, C15), `:19 (_call_provider)`, `:72-73` (`confirm=true` requerido) | **El único camino de escritura. Este plan lo enlaza, no lo duplica.** |
| Registro de servidores | `backend/services/server_registry.py:84 (list_servers)`, `:36 (_PUBLIC_KEYS)`, `:196 (has_password)` | Alias/host/credencial de los servidores del operador. `list_servers()` ya devuelve `has_password` sin el password. |
| Masking común (Plan 195) | `backend/services/secret_masking.py:20 (mask_token_values)`, `:25 (strip_secret_keys)`, `:12 (MASK_PLACEHOLDER)`, `:13 (SECRET_KEY_SUFFIXES)`, **`:11 (TOKEN_VALUE_PREFIXES)`** | Se aplica a TODO fragmento de YAML que salga en la respuesta. **LÍMITE MEDIDO, leído del archivo (C5): `mask_token_values` sólo enmascara 7 prefijos conocidos** (`ghp_`, `github_pat_`, `glpat-`, `xoxb-`, `xoxp-`, `AKIA`, `eyJhbGciOi`) **+ ≥8 chars**. NO enmascara un password arbitrario. Por eso hacen falta las **dos** redes del §3.3. |
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
| Ratchet del arnés | `backend/tests/test_harness_ratchet_meta.py:18 (_ratchet_files)` — parsea `HARNESS_TEST_FILES` de **`backend/scripts/run_harness_tests.sh:20`** | Todo `test_*.py` nuevo se registra ahí. **TRAMPA (C7): el meta-test parsea SÓLO el `.sh`.** La gemela Windows `backend/scripts/run_harness_tests.ps1:13` (`$HarnessTestFiles = @(`, con los 4 del Plan 94 en `:133-136`) **no la mira ningún test** ⇒ olvidarla no da rojo, se pudre en silencio. Su propio encabezado (`:6`) dice *"Mantener en sync con run_harness_tests.sh"*, y el `§0.3` del 246 la lista como 5ª superficie universal. **Se registra en LOS DOS.** |
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

### 3.3 El secreto nunca se muestra ni se loguea — DOS redes, porque una sola NO alcanza (C5)

**El agujero que tenía la v1, medido:** `looks_secret` (`ci_variables.py:31`) decide **sólo por el
NOMBRE**. `mask_token_values` (`secret_masking.py:20`) decide **sólo por la FORMA del valor**, y
además sólo reconoce **7 prefijos** (`secret_masking.py:11`). La v1 enmascaraba el
`declared_default` **únicamente cuando el nombre matcheaba** ⇒ una variable llamada
`SONAR_LOGIN`, `SMTP_USER`, `NUGET_SOURCE` o `CI_DEPLOY_USR` con un token real adentro salía
**verbatim** en la respuesta y se pintaba en la UI. Y los dos centinelas de la v1 usaban
`DB_PASSWORD` / `p4ssw0rd`, o sea **probaban el caso que ya funcionaba**.

Reglas, ahora ortogonales:

- La respuesta del endpoint contiene, por celda, **exclusivamente**: `state`, `source`, `note`.
  **Nunca un `value`.**
- **Red A (por FORMA, siempre):** `mask_token_values` se aplica **incondicionalmente** a
  `Evidence.excerpt` **y a `declared_default`** — sin importar el nombre, sin importar
  `is_secret`. Es la red que atrapa el token bajo nombre inocente.
- **Red B (por NOMBRE):** si `looks_secret(name)` es True, `declared_default` se reemplaza
  **entero** por `MASK_PLACEHOLDER` (`secret_masking.py:12`) y la celda se marca
  `is_secret: true` **con advertencia**: hay un secreto en texto plano dentro del YAML.
- **Orden obligatorio: A y después B.** B es más fuerte y gana; A cubre lo que B no ve.
- **Red C (estructural):** el payload completo pasa por `strip_secret_keys` (`:25`) antes de
  `jsonify`. Es una red de *claves de diccionario*, no de valores: **no** sustituye a A ni a B.
- Los `default` NO secretos **sí se muestran** (ya están en el repo en texto plano: ocultarlos
  sería teatro) — pero pasados por la red A.
- **Prohibido** cualquier `logger.*` o `print(` que referencie un valor en los archivos nuevos.
  Grep binario en el criterio de F3 y F4. **El grep va con `\bprint\(`, nunca `print\(` a secas:
  `Blueprint(` contiene literalmente `print(` y volvía el gate imposible (C1).**
- **Ningún modelo LLM ve nada de esto:** las 6 fases tienen 0 llamadas a modelo (§3.7, gate en
  F5). No hay prompt, no hay contexto, no hay transcript donde un valor pueda filtrarse.

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
- **Performance (corregido, C11 — la v1 decía algo falso):** el análisis es **bajo demanda** (un
  click, una pipeline). No hay barrido automático, ni polling, ni trabajo en el arranque.
  - **GitLab:** **una** lectura por análisis (`list_variables()` ya pagina internamente,
    `gitlab_variables.py:30`).
  - **ADO: hasta 51 GETs, no uno.** Construir `AdoVariablesProvider` dispara
    `find_yaml_definition` en su `__init__` (`ado_variables.py:17`), que lista hasta
    `_MAX_DEFINITIONS = 50` definitions y **hidrata el detalle con un GET extra por cada una que
    no traiga `process`** (`ado_pipeline_definitions.py:95-110`). **Este costo es preexistente del
    Plan 94, no lo introduce el 251** — pero mentirlo sí sería nuestro. Consecuencias codificadas:
    (1) el panel **no** analiza solo al montarse: exige un click explícito;
    (2) `resolve:false` evita el proveedor **entero** (`test_f3_use_provider_false_no_toca_red`);
    (3) la degradación por timeout ya está cubierta (`list_scoped_variables` captura todo y sigue).
  - **Prohibido** cachear el resultado: cero estado nuevo (§4). Si el costo molesta, el fix es del
    Plan 94, no de acá.

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
    requirement: str          # nombre del Requirement (C3: la celda se identifica a sí misma)
    environment: str          # nombre del entorno
    state: str                # uno de CELL_STATES
    source: str               # uno de SOURCES
    note: str | None          # nota honesta (p.ej. la de ADO sin scoping)

@dataclass(frozen=True)
class EnvMatrix:
    environments: tuple       # tuple[str, ...] — DERIVADOS, ordenados
    requirements: tuple       # tuple[Requirement, ...]
    cells: tuple              # tuple[Cell, ...] — LISTA, no dict. Ver C3.
    pending_count: int        # celdas en estado "falta" — EL número del titular
    pending_fingerprint: str  # [ADICIÓN ARQUITECTO 2] — ver §4.2-bis
    degraded: tuple           # tuple[str, ...] — motivos de degradación honestos
```

**C3 — por qué `cells` es una LISTA y no un dict (bloqueante de la v1).** La v1 declaraba
`cells: dict  # {(requirement_name, environment): Cell}`. Una **clave tupla no es serializable**:
`jsonify` levanta `TypeError: keys must be str, int, float, bool or None, not tuple`, y el propio
test `test_f3_ningun_value_en_el_retorno` de la v1 (`json.dumps(resolutions, default=str)`)
**no podía ni ejecutarse** (`default=` sólo afecta VALORES, no claves). El parche obvio de la v1 —
una clave string `"<name>\u0000<env>"` — mete un **byte NUL dentro de una clave JSON**, que es
legal pero es un campo minado (logs, proxies, `strip_secret_keys`, y el gotcha conocido de bytes de
control en tool calls). **Una lista de dicts lo resuelve entero**: serializa sola, no necesita
separador, no colisiona nunca y el frontend indexa una vez con `indexCells()`.

### 4.2-bis `pending_fingerprint` — huella de "lo que falta" `[ADICIÓN ARQUITECTO 2]`

```python
def pending_fingerprint(cells: tuple) -> str:
    """sha256 (16 hex) de las celdas que representan trabajo pendiente.

    Entrada canónica: sorted() de "<state>|<requirement>|<environment>" para toda
    celda con state in ("falta", "manual"). PURA, determinista, sin valores adentro
    (sólo nombres y estados: la misma información que ya sale en la respuesta).
    """
```

**Para qué sirve, en concreto:**
1. El operador carga 3 valores, vuelve a analizar y **ve si su trabajo bajó** sin comparar dos
   tablas a ojo. El frontend guarda la huella anterior en `localStorage` (cero persistencia
   backend, riel §4 intacto) y muestra *"bajó de 9 a 6"* o *"sin cambios"*.
2. El **Plan 252** puede estampar la huella en su `README`/`.zip` y así el paquete dice **a qué
   foto de la pipeline corresponde**. Sin esto, un paquete entregado ayer no se distingue del de
   hoy.
3. Es un **detector de no-determinismo gratis**: si dos análisis del mismo YAML dan huellas
   distintas, hay un bug de orden (`test_f2_pending_fingerprint_estable`).

Coste: una función pura de 4 líneas, 0 red, 0 LLM, 0 estado nuevo, 0 trabajo del operador.

### 4.3 Tabla de tipos de valor (contrato de detección y resolución)

| Tipo | Cómo se detecta en **ADO** | Cómo se detecta en **GitLab** | Dónde se busca ANTES de preguntar | Cómo se le pide si falta |
|---|---|---|---|---|
| **`variable`** (simple) | `$(NOMBRE)` en cualquier string del documento parseado, con `NOMBRE` que matchea `^[A-Za-z_][A-Za-z0-9_.]*$`. Descarta las de la allowlist predefinida (§4.4). | `$NOMBRE` / `${NOMBRE}` en `script:` y en valores de `variables:` | 1) bloque `variables:` (raíz/stage/job) del YAML; 2) `list_variables()` de la caja fuerte (94) | Fila con estado `falta`. CTA **"Completar"** → formulario del Plan 94 con `key` pre-cargada y "secreta" **des**tildada. |
| **`secret`** | Igual que `variable`, pero `looks_secret(name)` (`ci_variables.py:31`) da True | Igual | Igual, más el flag `is_secret` que ya devuelve el proveedor | Mismo CTA, con "secreta 🔒" **pre-tildado**. **Nunca se muestra un valor**, ni el default (se enmascara con `MASK_PLACEHOLDER`). |
| **`service_connection`** | Valor de un input cuya key esté en `_ADO_SERVICE_CONNECTION_KEYS` (§4.4) | **No existe** el constructo. En GitLab el equivalente son variables/tokens ⇒ **no se emite este kind para gitlab** | **No se busca: no es resoluble por API en v1** | Estado **`manual`** (nunca `falta`). Texto literal: *"Stacky no puede crear ni verificar service connections: creala en la web de Azure DevOps."* Entra al paquete del **Plan 252**. |
| **`server`** | `pool.name` a nivel raíz, stage, job o `- deployment:` (evidencia `cd-deploy-test.yml:120-121`). Si el valor es `${{ parameters.X }}`, se resuelve X contra el bloque `parameters:` (evidencia `bootstrap:116-117` + `:47-50`) | Cada valor de `tags:` de un job (modelado como `Job.runner_tags`, `pipeline_spec.py:87`) | `server_registry.list_servers()` (`server_registry.py:84`, **verificado SOLO-LECTURA: llama a `_load()`, nunca a `_save()`**): match **case-insensitive** contra `alias` **y** contra `host` | Si matchea ⇒ `definido` + badge `has_password` (`server_registry.py:196`, booleano, **nunca** la credencial). Si no ⇒ `falta` con CTA **"Registrar servidor"** → sección Servidores (Plan 91). **C13 — honestidad obligatoria cuando el pool viene de un parámetro:** el nombre sale del `default` del parámetro, que es lo que ADO usará *si el operador no lo cambia al encolar*. Eso es una **suposición**, y §3.5 dice que Stacky no adivina. Por eso: se conserva `confidence="alta"` (para que un servidor faltante SÍ llegue a `falta`), pero la celda lleva `note` **obligatoria**: *"pool tomado del default del parámetro `<X>`; si al encolar elegís otro, este chequeo no aplica"*, y la `Evidence` apunta a la línea del **parámetro**, no sólo a la del `pool:`. Test: `test_f1_bootstrap_servidor_desde_parametro` verifica la nota y las 2 evidencias. |
| **`deploy_path`** (**C2 — reglas corregidas**) | **DOS reglas distintas, no una:** (a) **ruta que ES el valor entero** — el string matchea `_ABS_PATH_FULL_RE` (anclado) y no tiene `$(` ni `${{` ⇒ `confidence="alta"` **sólo si** la key está en `_PATH_INPUT_KEYS` (§4.4); (b) **ruta EMBEBIDA en un texto** — `_ABS_PATH_EMBEDDED_RE.search()` (SIN ancla) encuentra la ruta dentro de un string mayor ⇒ `confidence="baja"` **siempre**. **La v1 usaba una sola regex anclada en `^` y por eso su propio test `test_f1_cd_deploy_rutas_absolutas` era IMPOSIBLE**: la evidencia que cita (`cd-deploy-test.yml:136` = `displayName: 'Deploy AgendaWeb → C:\AIS\AgendaWeb\Web'`, y `:175`) tiene la ruta **en el medio del string**, nunca al principio. `name` = la ruta capturada, no el string completo. | Igual, sobre valores de `script:` y `environment.url` | **No se busca en ninguna API.** En F5 la UI **sugiere** el `environment_root` del perfil (Plan 89) si está en el `ctx` — sugerencia visual, **no** resolución | `per_environment=True` **siempre**. Estado `falta` si `confidence=="alta"`; si es `"baja"`, estado `manual` con la nota: *"ruta absoluta hardcodeada en el YAML — confirmá el valor de cada entorno."* |
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

### F0 — Flag `STACKY_PIPELINE_ENV_MATRIX_ENABLED` (**7 patas**, la v1 declaraba 6)

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
   en `HARNESS_TEST_FILES` (`:20`), al **FINAL** de la lista. El meta-test parsea **ese** `.sh`
   (`test_harness_ratchet_meta.py:18-21`).
7. **`backend/scripts/run_harness_tests.ps1` — LA PATA QUE FALTABA (C7).** Registrar los mismos 5
   archivos en `$HarnessTestFiles` (`:13`), al **FINAL**, con la sintaxis de PowerShell
   (`"tests/test_plan251_env_matrix_flag.py",` — con comillas y coma, patrón del Plan 94 en
   `:133-136`; el `.sh` no lleva ni comillas ni coma, patrón `:140-143`).
   **Por qué importa:** el meta-test **NO** mira el `.ps1` ⇒ olvidarlo **no da rojo**, y el runner
   de dev local (que es el que corre el operador en Windows) deja de cubrir 5 archivos **en
   silencio**. El propio encabezado del `.ps1` (`:6`) dice *"Mantener en sync con
   run_harness_tests.sh"*, y el `§0.3` del Plan 246 lo lista como la 5ª superficie universal de la
   serie. **El 251 era el único de los 7 planes de la serie que no lo nombraba** (verificado con
   `grep -l "run_harness_tests.ps1" docs/24*.md docs/25*.md`).

**NO tocar `backend/harness_defaults.env`** (§2.4).

**Tests PRIMERO** — `backend/tests/test_plan251_env_matrix_flag.py`:
- `test_f0_flag_en_registry` — la key está en `FLAG_REGISTRY`.
- `test_f0_flag_en_categoria_devops` — está en `_CATEGORY_KEYS["devops"]`.
- `test_f0_default_on` — `spec.default is True` y la key está en `_CURATED_DEFAULTS_ON`.
- **`test_f0_config_efectivo_on` (NUEVO, C10 — cierra un falso verde real):**
  `import config; assert getattr(config.config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED") is True`.
  **Sin este test, el plan tenía un agujero de falso verde:** el default **efectivo** lo manda
  `config.py`, no el `FlagSpec`. Con `FlagSpec(default=True)` y `config.py` en `False`, los otros
  5 tests pasan **verdes** y en producción el endpoint devuelve **404**. Se lee **la instancia**
  `config.config`, nunca el módulo (gotcha citado en la pata 1).
- `test_f0_requires_es_el_master_del_panel` — `spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_f0_plain_help_existe`.

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

**Criterio de aceptación BINARIO:** los **6** tests propios verdes **y** los 3 archivos de
no-regresión verdes (`test_harness_flags.py` — **baseline medido hoy: 56 passed**;
`test_harness_flags_requires.py`; `test_harness_ratchet_meta.py` — **baseline medido hoy:
4 passed**). Cualquier rojo en esos tres = la flag está mal cableada.
**Y** el grep de paridad de ratchet:
`rg -c "test_plan251" backend/scripts/run_harness_tests.sh backend/scripts/run_harness_tests.ps1`
⇒ **5 en cada uno** (C7: el meta-test no puede detectar esto, así que el gate es manual y binario).

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
   - **Rutas (C2, dos reglas en este orden):**
     (a) si `_ABS_PATH_FULL_RE.match(s)` y el string **no** tiene `$(` ni `${{` ⇒
     `kind="deploy_path"`, `name = s`, `per_environment=True`,
     `confidence="alta"` si la key está en `_PATH_INPUT_KEYS`, si no `"baja"`;
     (b) **sólo si (a) no matcheó**, por cada hit de `_ABS_PATH_EMBEDDED_RE.findall(s)` ⇒
     `kind="deploy_path"`, `name = <el hit>`, `per_environment=True`,
     `confidence="baja"` **siempre** (está embebida en prosa: es una pista, no un contrato).
   - Aplicar `_ADO_VAR_RE` / `_GL_VAR_RE` según `provider`. Para cada nombre capturado:
     - si `is_ado_predefined(nombre)` ⇒ **descartar** (no es un requerimiento);
     - si la key del nodo está en `_SHELL_KEYS` y el nombre **no** está en `declared` ni en
       `params` ⇒ emitir con `confidence="baja"`;
     - si no ⇒ emitir con `confidence="alta"`.
     `kind = "secret" if looks_secret(nombre) else "variable"` (importando `looks_secret` de
     `services.ci_variables`, **no** re-implementándolo).
5. Deduplicar por `(name, kind)` **acumulando** las `Evidence` (una key usada en 3 lugares es UN
   requerimiento con 3 evidencias).
6. **`declared_default` para `kind in ("variable","secret")` (C6 — la v1 NUNCA lo asignaba y por
   eso su propio `test_f1_secreto_por_nombre` era imposible):** si `name` está en `declared`
   (el bloque `variables:`), `declared_default = str(declared[name])`. Si no está, `None`.
   Para `kind == "parameter"` ya lo fijó la regla 3. Para los demás kinds, `None`.
7. **Red A — SIEMPRE, sin condición (§3.3, C5):** `Evidence.excerpt` **y** `declared_default`
   pasan por `mask_token_values` (`services/secret_masking.py:20`). Atrapa el token bajo nombre
   inocente, que es el caso que la v1 dejaba pasar.
8. **Red B — después de A:** si `is_secret is True`, `declared_default` se reemplaza **entero**
   por `MASK_PLACEHOLDER` (`secret_masking.py:12`). B es más fuerte y pisa a A.

Regex exactos (**C2: las de ruta son DOS, no una**):
```python
_ADO_VAR_RE = re.compile(r"\$\((?P<n>[A-Za-z_][A-Za-z0-9_.]*)\)")
_ADO_TPL_RE = re.compile(r"\$\{\{\s*parameters\.(?P<n>[A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_GL_VAR_RE  = re.compile(r"\$\{?(?P<n>[A-Za-z_][A-Za-z0-9_]*)\}?")

# (a) el string ENTERO es una ruta absoluta  -> confidence alta si la key es de _PATH_INPUT_KEYS
_ABS_PATH_FULL_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/)[^\s\"']*$")
# (b) la ruta está EMBEBIDA en un texto mayor -> confidence SIEMPRE baja -> estado 'manual'
#     Evidencia obligatoria: cd-deploy-test.yml:136 y :175 tienen la ruta DESPUES de
#     'Deploy AgendaWeb -> '. Con la regex anclada de la v1 nunca se encontraban y el
#     test test_f1_cd_deploy_rutas_absolutas era imposible de pasar.
#     Se usa .findall() sobre el string; cada match es un Requirement.
#     El separador de unidad exige [\\/] para no capturar 'C:' de un 'ratio C:D'.
_ABS_PATH_EMBEDDED_RE = re.compile(r"(?:[A-Za-z]:[\\/]|(?<=\s)/)[^\s\"'\)\],]{2,}")
```
**Regla de precedencia entre (a) y (b): se prueba (a) primero. Si (a) matchea, (b) NO se corre
sobre ese string** (si no, la misma ruta se emitiría dos veces con dos confianzas distintas).

**Tests PRIMERO** — `backend/tests/test_plan251_env_matrix_extract.py`
(fixtures: los YAML **reales** de `backend/tests/fixtures/cicd_nl/golden/`, no juguetes):

- `test_f1_bootstrap_detecta_los_8_parametros` — sobre `bootstrap-server-environment.yml`:
  hay exactamente 8 requirements `kind="parameter"` y sus nombres son
  `{targetEnvironment, agentPool, component, skipIis, iisPort, iisHostHeader, seedConfigs, whatIf}`.
- `test_f1_bootstrap_iisport_default_cero` — el requirement `iisPort` tiene
  `declared_default == "0"` y su evidencia incluye el `displayName` de `:67`.
- `test_f1_bootstrap_servidor_desde_parametro` — existe un requirement `kind="server"` con
  `name == "TEST-Server"` (resuelto desde `${{ parameters.agentPool }}` de `:117` + su default de
  `:50`), **con 2 evidencias** (la del `pool:` y la del parámetro) **y** una `note` que contiene
  la palabra `"default"` (C13: se declara que es una suposición, no un hecho).
- `test_f1_bootstrap_compile_time_vars_no_faltan` — `skipIisArg`, `seedConfigsArg` y `whatIfArg`
  **NO** aparecen como requirements (están declaradas en `:101-112`).
- `test_f1_cd_deploy_variables_declaradas_no_se_piden` — sobre `cd-deploy-test.yml`:
  `buildConfiguration` y `buildPlatform` (declaradas en `:34-36`) **no** aparecen; el resto sí.
- `test_f1_cd_deploy_pool_literal` — hay un requirement `kind="server"`, `name == "TEST-Server"`,
  `confidence == "alta"`.
- `test_f1_cd_deploy_rutas_absolutas` (**C2 — este test era IMPOSIBLE en la v1**) — hay
  requirements `kind="deploy_path"` con `name == "C:\\AIS\\AgendaWeb\\Web"` y
  `name == "C:\\AIS\\Procesos\\Exes"`, ambos con `per_environment is True` **y
  `confidence == "baja"`** (vienen EMBEBIDOS en el `displayName` de `:136` y `:175`, no son el
  string entero) ⇒ y por lo tanto **terminan en estado `manual`, nunca en `falta`**.
- `test_f1_powershell_no_es_variable_de_pipeline` — sobre `cd-deploy-test.yml:81-87`:
  ni `slns`, ni `s`, ni `LASTEXITCODE` aparecen como requirement.
- `test_f1_predefinidas_de_ado_nunca_se_piden` — sobre `nightly-build-online.yml`:
  `Agent.JobStatus`, `Build.BuildNumber`, `Build.ArtifactStagingDirectory` y `Agent.TempDirectory`
  **no** aparecen en el resultado.
- `test_f1_secreto_por_nombre` — fixture sintética mínima con
  `variables: { DB_PASSWORD: 'p4ss' }` referenciada como `$(DB_PASSWORD)`: el requirement tiene
  `is_secret is True` y `declared_default == MASK_PLACEHOLDER` (**el literal `p4ss` no aparece en
  `repr()` del resultado**). Cubre la **red B**. Depende de la regla 6 (C6): sin ella
  `declared_default` quedaba en `None` y este test de la v1 **no podía pasar**.
- **`test_f1_valor_token_nombre_inocente` (NUEVO — C5, el hueco de seguridad real)** — fixture con
  `variables: { SONAR_HOST: 'glpat-AAAAAAAAAAAAAAAAAAAA' }` referenciada como `$(SONAR_HOST)`.
  `looks_secret("SONAR_HOST")` es **False** (no matchea por nombre) ⇒ la **red B no dispara**.
  Assert: `is_secret is False` **pero** `declared_default == MASK_PLACEHOLDER` gracias a la
  **red A** (`mask_token_values` incondicional, §3.3), y el literal `glpat-AAAAAAAAAAAAAAAAAAAA`
  **no aparece en `repr()` del resultado**. *Con el diseño de la v1 este test fallaba: el token
  salía verbatim.*
- **`test_f1_declared_default_de_variable_no_secreta` (NUEVO — C6)** — `variables: { REGION: 'us-east' }`
  usada como `$(REGION)`: `declared_default == "us-east"` (se muestra: no es secreto y ya está en
  el repo en claro) y `is_secret is False`.
- **`test_f1_corpus_dorado_sin_ruido` (NUEVO — `[ADICIÓN ARQUITECTO 1]`, KPI-6)** —
  parametrizado sobre **los 9** `.yml` de `backend/tests/fixtures/cicd_nl/golden/`
  (`agendaweb-ci`, `bootstrap-server-environment`, `cd-deploy-test`, `ci-batch`, `ci-cd-online`,
  `ci-dacpac`, `nightly-build-online`, `pr-validation-online`, `security-scan-online` — listados
  con `ls`, verificado). Para cada archivo, con `provider="azure_devops"`, assert que **todo**
  `Requirement` cumple: `name` no vacío, `name.strip() == name`, sin espacios, no empieza con `$`,
  `is_ado_predefined(name) is False`, `kind in VALUE_KINDS`, `confidence in CONFIDENCE`; y que
  `len(result) <= 40`.
  **Por qué es la adición de mayor valor:** la §2.4 de la v1 **declara honestamente** que sólo se
  abrieron 3 de los 9 YAML, y `ci-batch.yml` (con `matrix`) se tomó de segunda mano. El riesgo
  nº1 de este plan no es fallar: es **producir ruido** — 40 filas basura matan el KPI-2 y el
  operador deja de mirar la matriz para siempre. Este test convierte una deuda declarada en un
  **gate binario** sin abrir un solo archivo a mano, sin LLM y sin red.
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

**Criterio de aceptación BINARIO:** **17** tests verdes (14 de la v1 + 3 nuevos). **Y** el grep
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

    C3: `EnvMatrix.cells` es una TUPLA DE Cell (cada Cell trae su `requirement` y su
    `environment` adentro), NO un dict con claves tupla. El dict `resolutions` sigue
    siendo interno y NUNCA se serializa: la frontera JSON es EnvMatrix, no resolutions.

    Orden de `cells`: por orden de `requirements` y, dentro de cada uno, por orden de
    `environments`. Determinista, sin sort adicional.

    Para los pares SIN entrada en resolutions aplica el default por kind:
      - service_connection            -> Cell(..., "manual", "ninguna", <texto del §4.3>)
      - deploy_path confidence="baja" -> Cell(..., "manual", "ninguna", <texto del §4.3>)
      - confidence == "baja" (cualquier kind) -> Cell(..., "manual", ...)  [§4.4]
      - todo lo demás                 -> Cell(..., "falta", "ninguna", None)
    pending_count = cantidad de celdas con state == "falta".
    pending_fingerprint = pending_fingerprint(cells)   # §4.2-bis
    Si provider == "azure_devops" y len(environments) > 1, TODA celda "definido"
    resuelta por la caja fuerte lleva la nota del §3.6 (ADO no tiene scoping).

    C16 — `per_environment` deja de ser un campo muerto: si es False, TODAS las celdas
    de ese requirement llevan `note` con el sufijo " (mismo valor para todos los
    entornos)". El operador no debe creer que tiene que cargarlo N veces.
    """


def to_json_payload(m: EnvMatrix, provider: str) -> dict:
    """C3 — ÚNICA frontera de serialización. PURA. Devuelve exactamente:
      {"environments": [...], "requirements": [{...}], "cells": [{...}],
       "pending_count": int, "pending_fingerprint": str, "degraded": [...],
       "provider": str}
    Todo dict/lista nativa: `json.dumps()` sobre el retorno NUNCA levanta. La v1 no
    tenía esta función y por eso `jsonify` habría reventado en F4 y el test
    `test_f3_ningun_value_en_el_retorno` no podía ni ejecutarse.
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
- **`test_f2_payload_serializa_sin_error` (NUEVO — C3)** — `json.dumps(to_json_payload(m, "gitlab"))`
  **no levanta**, `payload["cells"]` es una **lista**, cada item tiene las 5 claves
  (`requirement`, `environment`, `state`, `source`, `note`), y **ninguna clave del payload
  contiene el byte NUL** (`"\x00" not in json.dumps(payload)`). *Con el `dict` de claves tupla de
  la v1 este test fallaba con `TypeError`.*
- **`test_f2_pending_fingerprint_estable` (NUEVO — `[ADICIÓN ARQUITECTO 2]`)** — dos
  `build_matrix` con los mismos args dan la **misma** `pending_fingerprint`; resolver **una**
  celda `falta` la **cambia**; reordenar la tupla `environments` de entrada con los mismos
  nombres **no** la cambia (es sobre el conjunto ordenado, no sobre el orden de llegada).
- **`test_f2_per_environment_false_lleva_nota` (NUEVO — C16)** — un requirement con
  `per_environment=False` produce celdas cuya `note` contiene `"todos los entornos"`.

**Comando:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_build.py -q
```

**Criterio de aceptación BINARIO:** **13** tests verdes (10 de la v1 + 3 nuevos), y
`test_f1_modulo_puro` de F1 **sigue verde** (el módulo no ganó I/O: `hashlib` es stdlib y no
cuenta como I/O — el test prohíbe `flask`, `requests`, LLM, `logger.` y `print(`, no `hashlib`).

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
- `test_f3_ningun_value_en_el_retorno` (**C3 — la v1 no podía ejecutar este test**) — centinela: el
  proveedor mockeado devuelve items con `value:"S3cr3t!"`; se serializa con
  **`json.dumps(to_json_payload(build_matrix(...), provider))`** y el texto resultante **no**
  contiene `"S3cr3t!"` ni la clave `"value"`.
  *La v1 hacía `json.dumps(resolutions, default=str)` sobre un dict de **claves tupla** ⇒
  `TypeError: keys must be str, int, float, bool or None, not tuple`. `default=` sólo afecta a los
  VALORES, nunca a las claves: el test reventaba antes de asertar nada.*

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_resolve.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan94_variables_providers.py -q
```

**Criterio de aceptación BINARIO:** 12 tests propios verdes **y**
`test_plan94_variables_providers.py` verde **sin modificar ni una línea** (prueba de que el
agregado fue aditivo; su `test_f2_port_structural_conformance` en `:283-291` usa `hasattr` para
los adapters y sólo compara `VARIABLES_PORT_METHODS` contra una tupla literal — **verificado
leyendo el cuerpo del test**: agregar un método es seguro, tocar la constante rompe).
Además, grep binario **con `\b` obligatorio (C1)**:
`rg -n "logger\.|\bprint\(" backend/services/pipeline_env_resolver.py` ⇒ **0 resultados**.

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
6. **El payload se construye SIEMPRE con `to_json_payload()`** (§5-F2, C3). Está prohibido pasarle
   un `EnvMatrix` o un dict de claves tupla a `jsonify`: revienta.
7. **Antes de `jsonify`**, el payload pasa por `strip_secret_keys`
   (`services/secret_masking.py:25`) como red final. **Nota honesta:** `strip_secret_keys` sólo
   mira **claves de diccionario** (`:31-33`); las claves del payload son fijas
   (`environments`, `requirements`, `cells`, …) ⇒ en la práctica es una red **estructural**, no
   la que protege los valores. Los valores los protegen las redes A y B del §3.3 (C5).
8. **Prohibido** cualquier `logger`/`print(` que toque `yaml_text` o el payload.

**Archivos a editar (C9 — punto de inserción alineado con el orden de merge de la serie):**
- `backend/api/__init__.py` — import **al final del bloque de imports de api** (el del Plan 94
  está en `:50`, verificado) y `api_bp.register_blueprint(pipeline_environments_bp)` **al final
  del bloque de `register_blueprint`** (el del Plan 94 está en `:123`, el último de la cola
  DevOps en `:128`; verificado), con el comentario
  `# Plan 251 — url_prefix="/pipeline-environments" → /api/pipeline-environments/...`.
- `backend/api/devops.py` — en `_health_payload()` (`:28`), **al FINAL del dict**, NO junto al
  `:48` del Plan 94 como decía la v1. El `§0.3` del 246 fija *"1 key de health por plan, al final
  del dict"*: **248, 250, 251 y 252 agregan su key en el mismo merge** y insertar en el medio
  garantiza conflicto de 3 vías.
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
- `test_f4_ningun_valor_en_la_respuesta` — **KPI-3 (a)**: proveedor mockeado con
  `value:"S3cr3t!XYZ"` y un YAML con `variables: { DB_PASSWORD: 'p4ssw0rd' }` ⇒ el **texto crudo**
  de la respuesta no contiene `S3cr3t!XYZ` ni `p4ssw0rd`.
- **`test_f4_secreto_con_nombre_inocente_no_sale` (NUEVO — KPI-3 (b), C5)**: YAML con
  `variables: { SONAR_HOST: 'glpat-AAAAAAAAAAAAAAAAAAAA' }` referenciada como `$(SONAR_HOST)`
  ⇒ el texto crudo de la respuesta **no** contiene `glpat-AAAAAAAAAAAAAAAAAAAA`.
  **Este es el test que la v1 no tenía y que su diseño no habría pasado:** el nombre no matchea
  `looks_secret`, así que sólo la red A incondicional lo salva.
- `test_f4_health_tiene_env_matrix_enabled` — `GET /api/devops/health` trae la key nueva.
- `test_f4_ruta_registrada` — centinela sobre `app.url_map`:
  `/api/pipeline-environments/analyze` existe.

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan251_env_matrix_endpoints.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan94_variables_endpoints.py -q
```

**Criterio de aceptación BINARIO:** **13** tests propios verdes, `test_plan94_variables_endpoints.py`
verde, **y** el grep — **CORREGIDO, C1:**
```bash
rg -n "logger\.|\bprint\(" backend/api/pipeline_environments.py     # ⇒ 0 resultados
```
> **C1 — por qué la v1 tenía un criterio de aceptación IMPOSIBLE.** Decía
> `rg -n "logger|print\(" backend/api/pipeline_environments.py`. La palabra **`Blueprint(`
> contiene literalmente la subcadena `print(`** — y este archivo abre con
> `bp = Blueprint("pipeline_environments", …)`. El gate daba **≥1 hit siempre**, por
> construcción: ninguna implementación correcta podía pasarlo. Es exactamente el gotcha
> conocido de *"el texto del plan choca con su propio grep-gate de 0 hits"*, sólo que acá el
> culpable no era un comentario sino el constructor de Flask.
> `\bprint\(` **no** matchea `Blueprint(` (entre `e` y `p` no hay borde de palabra) y sí matchea
> `print(` y ` print(`. `logger\.` evita matchear la palabra `logger` dentro de un comentario que
> explique justamente esta regla.

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
export interface EnvCellRow extends EnvCell { requirement: string; environment: string; }

export interface EnvMatrixResponse {
  environments: string[]; requirements: EnvRequirement[];
  cells: EnvCellRow[];              // C3: LISTA, no Record. Sin separador, sin byte NUL.
  pending_count: number;
  pending_fingerprint: string;      // [ADICION ARQUITECTO 2]
  degraded: string[]; provider: string;
}

/** indexCells — construye UNA vez el mapa de lookup para pintar la tabla.
 *  Reemplaza al `cellKey` de la v1: la clave se arma del lado del CLIENTE y NUNCA
 *  viaja por la red, así que backend y frontend no pueden desincronizarse en el
 *  separador. Clave interna: requirement + '' + environment (unit separator).
 *  PROHIBIDO el byte NUL en cualquier clave serializable (C3 + gotcha conocido de
 *  bytes de control crudos en docs y tool calls). */
export function indexCells(m: EnvMatrixResponse): Map<string, EnvCellRow>;

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
- **C12 — cómo se pregunta por el 246 SIN romper `tsc --noEmit` (criterio 2 de esta fase).**
  `DevOpsSectionContext` es una interfaz **cerrada** definida en `DevOpsPage.tsx`. Si el 246 no
  está mergeado, el campo no existe y **`ctx.pipelineInventory` es un error de compilación**, no
  un `undefined`. La v1 decía "si `ctx` expone el inventario" sin decir cómo, y un modelo menor
  escribiría el acceso directo y rompería el gate. **Forma obligatoria, sin `any` y sin tocar
  `DevOpsSectionContext`:**
  ```ts
  // pipelineEnvMatrixModel.ts — type guard local, propiedad de ESTE plan
  type WithInventory = { pipelineInventory?: Array<{ id: string; name: string; yaml_path: string }> };
  export function readInventory(ctx: unknown): WithInventory['pipelineInventory'] {
    const c = ctx as WithInventory;
    return Array.isArray(c?.pipelineInventory) ? c.pipelineInventory : undefined;
  }
  ```
  Compila **con y sin** el 246 mergeado, y el día que el 246 entre no hay que tocar nada.
  Test: `readInventory_degrada_sin_246`.
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
- `frontend/src/pages/DevOpsPage.tsx` — **EXACTAMENTE 3 ediciones, enumeradas (C4).**
  > **C4 — la v1 se autoprohibía y era inimplementable.** Decía *"PROHIBIDO tocar
  > `DevOpsPage.tsx` fuera de ese array"* y lo repetía como checkbox del DoD. Pero
  > `render: (ctx) => <PipelineEnvMatrixPanel ctx={ctx} />` **necesita un `import`**, y todos los
  > imports de secciones viven fuera del array (`:88-109`, verificado: `PipelineBuilderSection`
  > `:88`, `VariablesSection` `:99`, `DevOpsOverviewSection` `:109`). Con la regla de la v1 el
  > implementador quedaba sin salida: o violaba el plan o no compilaba.

  **(1)** `import { PipelineEnvMatrixPanel } from '../components/devops/PipelineEnvMatrixPanel';`
  **al final** del bloque de imports de secciones (después de `:109`).
  **(2)** en la interfaz `DevOpsHealth` (`:32`, cuyo comentario dice *"Health con index signature
  para keys aditivas"*), **al final** de la lista de keys opcionales:
  `env_matrix_enabled?: boolean; // Plan 251 — Matriz de entornos`. Es la convención de las 18
  keys que ya están (cada una con su `// Plan NN`).
  **(3)** **UNA** entrada declarativa en `DEVOPS_SECTIONS` (`:113`), **al FINAL del array** —
  **no** "inmediatamente después de `id:'variables'` (`:174-179`)" como decía la v1 (C9): el
  `§0.3` del 246 fija la entrada del Plan 201 (`:216-226`, el final) como punto de inserción de la
  serie, y 248/250/251/252 agregan la suya **en el mismo merge**. Insertar en el medio del array
  garantiza un conflicto de 3 vías evitable. Shape exacto de `:79-81`:
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
  **PROHIBIDO tocar `DevOpsPage.tsx` fuera de esas 3 ediciones enumeradas.**

**Tests PRIMERO** — `frontend/src/devops/pipelineEnvMatrixModel.test.ts`
(**C20: HERMANO del modelo, no en `__tests__/`.** Verificado con `ls src/devops/`: 11 de 12
modelos usan el patrón hermano — `variablesModel.test.ts`, `environmentModel.test.ts`,
`productionModel.test.ts`… — y `__tests__/` tiene **un solo** archivo. Se sigue la mayoría):
- `indexCells_construye_el_mapa` (**reemplaza a `cellKey_es_estable`**, C3) — a partir de la lista
  `cells` arma un `Map` con `requirements.length * environments.length` entradas, y el lookup de
  un par conocido devuelve la celda correcta.
- `pendingByEnvironment_cuenta_solo_falta` — fixture con 3 estados ⇒ conteo exacto por entorno.
- `headline_cero` — `pending_count: 0` ⇒ el string contiene `"No falta nada"`.
- `headline_n` — `pending_count: 3` ⇒ contiene `"3"`.
- `sortRequirements_prioriza_falta` — el primero del array tiene una celda `falta`; el último
  está todo `definido`.
- `sortRequirements_es_inmutable` — el array `requirements` original no cambia de orden.
- `canCompleteInStacky_solo_variable_y_secret` — `true` para `variable`/`secret`; `false` para
  `server`, `service_connection`, `deploy_path`, `parameter`.
- **`readInventory_degrada_sin_246` (NUEVO — C12)** — `readInventory({})` y
  `readInventory(undefined)` devuelven `undefined` sin lanzar; con un array válido lo devuelven
  tal cual.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/pipelineEnvMatrixModel.test.ts
npx vitest run src/devops/variablesModel.test.ts
npx tsc --noEmit
```
> Correr **por archivo**, nunca la suite completa: hay contaminación cross-file conocida en vitest.

**Criterio de aceptación BINARIO:**
1. **8** tests vitest propios verdes **y** `variablesModel.test.ts` verde (no-regresión del 94).
2. `npx tsc --noEmit` ⇒ **0 errores** (ver C12: el acceso al inventario del 246 va por
   `readInventory`, nunca por acceso directo a un campo que puede no existir).
3. Grep `rg -n "style=\{\{" frontend/src/components/devops/PipelineEnvMatrixPanel.tsx` ⇒
   **0 resultados**.
4. **Gate CORREGIDO (C14) — la v1 tenía un comando malformado que daba 0 SIEMPRE:**
   ```bash
   rg -n "STACKY_PIPELINE_ENV_MATRIX_ENABLED" frontend/src/components/devops/PipelineEnvMatrixPanel.tsx
   ```
   ⇒ **0 resultados** (el gate lo hace el shell, no el componente).
   > La v1 escribía `rg -n "PipelineEnvMatrixPanel.tsx" -e "STACKY_..."`. Con `-e` presente,
   > **el primer positional deja de ser el patrón y pasa a ser la RUTA**: `rg` buscaba
   > `STACKY_...` dentro de un archivo llamado `PipelineEnvMatrixPanel.tsx` **relativo al cwd**,
   > que no existe ⇒ 0 hits garantizados aunque el componente estuviera plagado de la flag.
   > Falso verde estructural.
5. **KPI-5 (paridad de runtimes):** grep
   `rg -n "invoke_local_llm|llm_router|copilot_bridge|claude_code_cli|codex_cli" backend/services/pipeline_environments.py backend/services/pipeline_env_resolver.py backend/api/pipeline_environments.py`
   ⇒ **0 resultados**. Cero LLM en todo el plan.
6. **Existe el CSS module hermano** `frontend/src/components/devops/PipelineEnvMatrixPanel.module.css`
   (declarado en §0 como derivado de la superficie reservada del `.tsx`; sin él, el criterio 3 es
   inalcanzable).

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
| Flag mal cableada ⇒ meta-tests rojos en silencio | Las **7** patas de F0, con `_CURATED_DEFAULTS_ON` y `_REQUIRES_MAP_FROZEN` explícitas y sus comandos |
| **Flag verde en los tests pero 404 en producción** (`FlagSpec` ON, `config.py` OFF) | `test_f0_config_efectivo_on` lee **la instancia** `config.config`, no el módulo. C10 |
| `requires` encadenado rompe R4 | `requires="STACKY_DEVOPS_PANEL_ENABLED"` (master de raíz), con la evidencia del desvío análogo del Plan 104 en `harness_flags.py:3158-3168`. `test_f0_requires_es_el_master_del_panel` |
| **Secreto en claro bajo nombre inocente** (`SONAR_LOGIN`, `SMTP_USER`, `CI_DEPLOY_USR`) sale verbatim en `declared_default` (**C5, agujero real de la v1**) | Red A: `mask_token_values` **incondicional** sobre `declared_default` y `excerpt`, no sólo cuando `looks_secret` da True. `test_f1_valor_token_nombre_inocente`, `test_f4_secreto_con_nombre_inocente_no_sale` |
| **Un criterio de aceptación imposible bloquea la fase para siempre** (`Blueprint(` contiene `print(`) | Todos los greps de log usan `\bprint\(`. Y regla nueva: **antes de cerrar una fase, correr su propio grep sobre un archivo de ejemplo del repo** para probar que el gate discrimina (no que da 0 por accidente). C1, C14 |
| **Un test que no puede ni ejecutarse pasa por "pendiente"** (`json.dumps` sobre claves tupla) | La frontera de serialización es una función nombrada (`to_json_payload`) con su propio test (`test_f2_payload_serializa_sin_error`). C3 |
| **El `.ps1` del arnés queda desincronizado sin que nada se ponga rojo** | Checkbox manual + gate `rg -c "test_plan251" <ambos>` ⇒ 5 y 5. El meta-test **no** puede atraparlo (parsea sólo el `.sh`). C7 |
| **Merge de 3 vías con 248/250/252 en `devops.py`, `DevOpsPage.tsx`, `endpoints.ts`** | Inserción **siempre al final** del bloque, nunca en el medio, según el orden canónico del §0.3 del 246. C9 |
| **El panel no compila si el 246 no está mergeado** | `readInventory(ctx: unknown)` con type guard local: compila con y sin el 246. `readInventory_degrada_sin_246`. C12 |
| **El operador cree que el pool es un hecho cuando salió del default de un parámetro** | `note` obligatoria + 2 evidencias (la del `pool:` y la del parámetro). `test_f1_bootstrap_servidor_desde_parametro`. C13 |
| **Byte de control crudo en el doc o en el código** (el separador de claves de la v1 era el byte NUL) | `cells` es una lista: el separador desaparece. Checkbox de bytes de control en la DoD. C3 |
| **Costo real en ADO 51× mayor que el declarado** | §3.8 corregido y honesto; análisis sólo por click explícito; `resolve:false` evita el proveedor entero. C11 |

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

1. **F0** — flag (**7** patas: `config.py`, `harness_flags.py` ×2, `harness_flags_help.py`,
   `_CURATED_DEFAULTS_ON`, `_REQUIRES_MAP_FROZEN`, ratchet en `run_harness_tests.sh`
   **y en `run_harness_tests.ps1`** — C7, la pata que faltaba).
2. **F1** — `services/pipeline_environments.py`: extracción pura (el corazón).
3. **F2** — mismo archivo: `derive_environments` + `build_matrix` + `to_json_payload` +
   `pending_fingerprint`.
4. **F3** — `services/pipeline_env_resolver.py` + los 2 métodos aditivos `list_variables_scoped`.
5. **F4** — `api/pipeline_environments.py` + registro en `api/__init__.py` + key de health.
6. **F5** — `pipelineEnvMatrixModel.ts` + `PipelineEnvMatrixPanel.tsx` +
   `PipelineEnvMatrixPanel.module.css` + las **3** ediciones de `DevOpsPage.tsx` + el namespace
   en `endpoints.ts`.

F1 y F2 se pueden hacer y validar **sin backend levantado ni red**: son puras. Si el
implementador tiene poco presupuesto, F0+F1+F2 ya entregan un núcleo verificable y F3–F5 se
apilan encima sin retrabajo.

---

## 10. Definición de Hecho (DoD binaria)

- [ ] **61 tests backend** propios verdes, corridos **por archivo** con
      `backend\.venv\Scripts\python.exe` (**Python 3.13.5**, no `backend\venv` que es 3.11.9):
      F0 **6** + F1 **17** + F2 **13** + F3 12 + F4 **13** = **61**. Los greps binarios de F1, F3,
      F4 y F5 son criterios de aceptación, no tests, y van aparte.
- [ ] **8 tests vitest** propios verdes + `variablesModel.test.ts` verde + `npx tsc --noEmit` con
      **0 errores**.
- [ ] **Baselines medidos hoy, no supuestos:** `test_harness_flags.py` = **56 passed** y
      `test_harness_ratchet_meta.py` = **4 passed** ANTES de tocar nada. Si tu cambio los deja en
      otro número que no sea el esperado por tu propia flag, es tuyo.
- [ ] **No-regresión verde sin editar esos archivos:** `test_harness_flags.py`,
      `test_harness_flags_requires.py`, `test_harness_ratchet_meta.py`,
      `test_plan94_variables_providers.py`, `test_plan94_variables_endpoints.py`.
      (`test_harness_flags_help` tiene 4 rojos **ajenos** preexistentes: validá tu entrada aparte.)
- [ ] **Flag OFF ⇒ byte-idéntico:** `POST /api/pipeline-environments/analyze` da 404, la sección
      muestra el `FlagGateBanner` del shell y nada más cambia.
- [ ] **KPI-2:** `test_f3_no_pide_lo_que_ya_existe` verde — `pending_count == 0` cuando todo ya
      existe en alguna fuente.
- [ ] **KPI-3 (dos ejes, C5):** (a) nombre secreto ⇒ `test_f4_ningun_valor_en_la_respuesta`;
      (b) **nombre inocente con valor con forma de token** ⇒ `test_f1_valor_token_nombre_inocente`
      **y** `test_f4_secreto_con_nombre_inocente_no_sale`. **Los 4 verdes o KPI-3 no está.**
      Y los 3 greps **`rg -n "logger\.|\bprint\("`** dan 0 (**con `\b`**, C1: sin él,
      `Blueprint(` hace el gate imposible).
- [ ] **KPI-6 (`[ADICIÓN ARQUITECTO 1]`):** `test_f1_corpus_dorado_sin_ruido` verde sobre los
      **9** YAML del corpus dorado.
- [ ] **Serialización (C3):** `json.dumps(to_json_payload(m, provider))` no levanta,
      `payload["cells"]` es una **lista**, y el texto serializado NO contiene el caracter de
      codigo 0: `chr(0) not in json.dumps(payload)` — escrito con `chr(0)` a proposito,
      para no meter un byte de control crudo ni en el test ni en este documento.
- [ ] **KPI-4:** `derive_environments` sobre los 3 YAML reales abiertos da, respectivamente,
      `("Test","Production")`, `("Test",)` y `("(único)",)`.
- [ ] **KPI-5:** el grep de LLM sobre los 3 archivos backend nuevos da **0 resultados**.
- [ ] **Cero escritura:** grep binario
      `rg -n "set_variable|delete_variable|\.write_text|open\(.*[\"']w|requests\.(post|put|delete)|_request\(\"(POST|PUT|DELETE)" backend/services/pipeline_environments.py backend/services/pipeline_env_resolver.py backend/api/pipeline_environments.py`
      ⇒ **0 resultados**.
- [ ] **Contrato del Plan 94 intacto:** `VARIABLES_PORT_METHODS` sin cambios, `Protocol`
      `CIVariablesProvider` sin cambios, `list_variables`/`set_variable`/`delete_variable` sin
      cambios.
- [ ] `DevOpsPage.tsx` tocado **sólo** en las **3 ediciones enumeradas** en F5 (import al final
      del bloque de imports; key en `DevOpsHealth`; entrada al **final** de `DEVOPS_SECTIONS`).
      *(C4: la v1 decía "sólo dentro del array", lo cual hacía imposible importar el panel.)*
- [ ] Los 5 archivos `test_plan251_*.py` registrados en **AMBOS** runners (C7):
      `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh:20` **y** `$HarnessTestFiles`
      de `backend/scripts/run_harness_tests.ps1:13`. Gate:
      `rg -c "test_plan251" backend/scripts/run_harness_tests.sh backend/scripts/run_harness_tests.ps1`
      ⇒ **5 y 5**. *(Ningún test detecta el olvido del `.ps1`: por eso es checkbox manual.)*
- [ ] **Frontera §0 respetada:** los 9 archivos declarados (4 reservados + 5 enmendados) y
      **ninguno más**. En particular: **no** se tocó `pipeline_renderers.py` (es del 249),
      ni `pipeline_inventory.py` / `api/pipeline_inventory.py` (246/247), ni
      `cicd_semantic_rules.py` (249), ni `pipeline_patcher.py` (250), ni
      `pipeline_handoff_bundle.py` (252).
- [ ] **Cero bytes de control crudos** en los archivos nuevos y en este doc:
      `python -c "import pathlib,sys; [sys.exit('CTRL en '+str(f)) for f in pathlib.Path('.').rglob('*') if f.is_file() and any(b in pathlib.Path(f).read_bytes() for b in (b'\x00', b'\x1b'))]"`
      acotado a los archivos del plan. *(Gotcha conocido: un `\x00`/`\x1b` crudo invalida
      `json.loads` y rompe tool calls. La v1 usaba el byte NUL como separador de claves —
      eliminado en la v2, C3.)*
- [ ] `backend/harness_defaults.env` **no** modificado a mano.
- [ ] **Smoke visual (manual, único):** abrir el panel, analizar
      `bootstrap-server-environment.yml`, ver dos columnas (Test / Producción), el titular
      "Te faltan N valores", `iisPort` en estado `default` con su `0`, y `TEST-Server` resuelto o
      en `falta` según el registro de servidores real.


---

## 11. Crítica adversarial v1 → v2 (juez INDEPENDIENTE)

**Método.** Se reverificaron ~60 anclajes `archivo:línea` abriendo cada archivo. Se confirmaron
también los dos datos heredados de otra sesión: `backend/services/devops_variables.py` **NO
existe** (el que existe es `backend/api/devops_variables.py`, que es el que el plan cita bien), y
`environment_scope` tiene **0 ocurrencias** en `backend/**/*.py` (`grep -rn`, verificado) — o sea
que la afirmación del §8 *"este plan es el primero que lo lee"* es **cierta**.

**Calidad de anclajes (muy alta):** 18/18 anclajes al corpus dorado **correctos**
(`bootstrap:38-84`, `:39-45`, `:47-50`, `:66-69`, `:101-112`, `:116-118`, `:128,132-138`;
`cd-deploy:34-36`, `:81-87`, `:120-121`, `:125,164`, `:136`, `:175`; `nightly:99`, `:111-113`, y
la ausencia de `deployment:`/`environment:` en `nightly`, que es lo que sostiene KPI-4). Esto es
**notable**: el dossier del Plan 243 tenía sus anclajes al mismo corpus corridos una línea.
Sólo **2 anclajes falsos**, ambos off-by-one (C15).

### BLOQUEANTES (los 5 que hacían RECHAZADO al v1)

| # | Qué está mal | Por qué importa | Fix aplicado |
|---|---|---|---|
| **C1** | Criterio de F4: `rg -n "logger\|print\("` sobre `api/pipeline_environments.py`. **`Blueprint(` contiene literalmente `print(`** y el archivo abre con `bp = Blueprint(...)`. | El gate daba ≥1 hit **siempre**: ninguna implementación correcta podía cerrar F4. Es el gotcha de *"el plan choca con su propio grep-gate de 0 hits"*, con el constructor de Flask como culpable. | `rg -n "logger\.\|\bprint\("` en F3, F4 y DoD, + regla nueva: validar que el gate discrimina antes de cerrar la fase. |
| **C2** | `_ABS_PATH_RE` anclada en `^`, pero la evidencia que el propio plan cita (`cd-deploy-test.yml:136` = `displayName: 'Deploy AgendaWeb → C:\AIS\AgendaWeb\Web'`) tiene la ruta **en el medio del string**. | `test_f1_cd_deploy_rutas_absolutas` **no podía pasar nunca**: el plan pedía detectar exactamente lo que su regex excluía. | Dos regex (`_ABS_PATH_FULL_RE` anclada, `_ABS_PATH_EMBEDDED_RE` sin ancla) con precedencia declarada; la embebida siempre `confidence="baja"` ⇒ `manual`. |
| **C3** | `EnvMatrix.cells: dict` con **claves tupla**. | `jsonify` levanta `TypeError: keys must be str...`; y `test_f3_ningun_value_en_el_retorno` (`json.dumps(resolutions, default=str)`) **no podía ni ejecutarse** (`default=` no toca las claves). El parche implícito de la v1 —clave `<name>` + byte NUL + `<env>`— metía un **byte de control dentro de una clave JSON**. | `cells` pasa a ser **lista de `Cell`** (cada una trae su `requirement` y su `environment`); frontera única `to_json_payload()`; en el front, `indexCells()`. Muere el separador y con él una clase entera de bugs. |
| **C4** | F5 exigía *"PROHIBIDO tocar `DevOpsPage.tsx` fuera de ese array"* (y lo repetía como checkbox de la DoD), pero el panel **necesita su `import`**, que vive fuera del array (`:88-109`, verificado). | Contradicción sin salida: el implementador o violaba el plan o no compilaba. | Se enumeran **exactamente 3 ediciones**: import al final del bloque, key en `DevOpsHealth` (`:32`), entrada al final de `DEVOPS_SECTIONS`. |
| **C5** | **Seguridad.** KPI-3 prometía *"el valor de un secreto no aparece NUNCA"*, pero `mask_token_values` sólo enmascara **7 prefijos** (`secret_masking.py:11`, leído) y `looks_secret` decide **sólo por nombre**. El `declared_default` se enmascaraba **únicamente si el nombre matcheaba**. | Un secreto en claro bajo nombre inocente (`SONAR_LOGIN`, `SMTP_USER`, `CI_DEPLOY_USR`) salía **verbatim** en la respuesta HTTP y se pintaba en la UI. Peor: **los 2 centinelas usaban `DB_PASSWORD`/`p4ssw0rd`**, o sea probaban el caso que ya funcionaba y dejaban el difícil sin cubrir. | Redes A (por FORMA, **incondicional**) y B (por NOMBRE) ortogonales y en orden fijo; §3.3 reescrito; + 2 tests negativos nuevos con nombre inocente y valor con forma de token. |

### IMPORTANTES

- **C6** — La regla 4 de `extract_requirements` **nunca asignaba `declared_default`** para
  `kind in (variable, secret)`, pero `test_f1_secreto_por_nombre` exigía
  `declared_default == MASK_PLACEHOLDER`. Contradicción interna. **Fix:** regla 6 explícita.
- **C7** — **`run_harness_tests.ps1` omitido.** El §0.3 del Plan 246 lo lista como 5ª superficie
  universal (`:13 $HarnessTestFiles = @(`, *"la gemela Windows"*) y **los otros 6 planes de la
  serie lo nombran; el 251 era el único que no** (verificado con `grep -l`). El meta-test parsea
  **sólo el `.sh`** (`test_harness_ratchet_meta.py:13`) ⇒ el olvido **no da rojo**: se pudre en
  silencio y el runner de dev local del operador deja de cubrir 5 archivos. **Fix:** 7ª pata en
  F0 + gate `rg -c` + checkbox en la DoD.
- **C8** — **Frontera §0.3 excedida en 5 archivos**: `services/pipeline_env_resolver.py` (crea),
  `services/gitlab_variables.py` y `services/ado_variables.py` (edita), más
  `harness_flags_help.py` y `test_harness_flags_requires.py` (que el propio §0.3 **omitió** como
  superficies universales). Verificado por `grep -l` sobre los 7 docs: **ningún otro plan reclama
  esos archivos**, así que no hay choque frontal — pero la reserva es *"no negociable"*. **Fix:**
  nuevo **§0** con la enmienda declarada, la prueba de no-colisión y la regla de merge.
- **C9** — Puntos de inserción **contra** el orden de merge de la serie: la v1 mandaba insertar en
  `api/devops.py` *"junto a `:48`"* y en `DEVOPS_SECTIONS` *"inmediatamente después de
  `id:'variables'` (`:174-179`)"*. El §0.3 fija *"al final del dict"* / *"al final del array"*
  porque 248, 250, 251 y 252 agregan su línea **en el mismo merge**. **Fix:** inserción al final.
- **C10** — **Falso verde de la flag.** No había test del valor **efectivo** en `config.config`.
  Con `FlagSpec(default=True)` y `config.py` en `False`, los 5 tests de F0 pasan verdes y el
  endpoint devuelve **404 en producción**. **Fix:** `test_f0_config_efectivo_on`.
- **C11** — §3.8 afirmaba *"las lecturas al proveedor son **una** por análisis"*. **Falso en ADO:**
  `AdoVariablesProvider.__init__` (`:17`) llama a `find_yaml_definition`
  (`ado_pipeline_definitions.py:82`), que lista hasta 50 definitions y **hidrata el detalle con un
  GET extra por cada una sin `process`** (`:95-110`) ⇒ hasta **51 GETs**. El costo es preexistente
  del Plan 94, pero declararlo mal sí era del 251. **Fix:** §3.8 honesto + 3 consecuencias
  codificadas.
- **C12** — *"Si `ctx` expone el inventario del Plan 246"* sin decir **cómo**.
  `DevOpsSectionContext` es una interfaz cerrada: acceder a un campo que el 246 todavía no agregó
  es **error de compilación**, y el criterio 2 de F5 exige `tsc --noEmit` con 0 errores.
  **Fix:** `readInventory(ctx: unknown)` con type guard local + su test.
- **C13** — El pool se toma del `default` del parámetro `agentPool` y se resuelve contra el
  registro con `confidence="alta"`, sin declarar que es una **suposición** (§3.5: *"Stacky no
  adivina"*). **Fix:** `note` obligatoria + 2 evidencias.
- **C14** — Gate 4 de F5 **malformado**: `rg -n "PATRON" -e "PATRON2"`. Con `-e` presente el primer
  positional pasa a ser **RUTA**, no patrón ⇒ `rg` buscaba en un archivo inexistente y daba **0
  siempre**. Falso verde estructural. **Fix:** comando corregido.

### MENORES

- **C15** — 2 anclajes falsos (off-by-one): `ado_variables.py:44` → **`:43`**;
  `api/devops_variables.py:59` (es el decorador) → **`:60`**. Corregidos en §2.2.
- **C16** — `per_environment` se definía (§4.2) y se seteaba (§4.3) pero **nunca se consumía**:
  campo muerto. Ahora `build_matrix` lo usa para anotar *"mismo valor para todos los entornos"*.
- **C17** — Enums declaradas "CERRADAS" sin test que lo verificara. Ahora
  `test_f1_corpus_dorado_sin_ruido` asserta `kind in VALUE_KINDS` y `confidence in CONFIDENCE`.
- **C18** — El encabezado decía *"consume … el perfil del **247**"* pero **ninguna fase lo
  consume** y el §7 lo pone fuera de scope. Dependencia fantasma.
- **C19** — `config.py` sin anclaje de línea (el §0.3 del 246 da `:1337-1339`).
- **C20** — Ubicación del test vitest: 11 de 12 modelos de `src/devops/` usan el patrón **hermano**
  (`variablesModel.test.ts`) y `__tests__/` tiene **un solo** archivo. Se mueve al mayoritario.
- **C21** — Sin huella de regresión en `docs/sistema/error_fingerprints.json`. Es convención, no
  bloqueante; correspondería registrar la huella de *"gate de grep imposible por subcadena"*
  (C1/C14), que ya apareció antes en el repo.

### Adiciones proactivas

- **`[ADICIÓN ARQUITECTO 1]` — `test_f1_corpus_dorado_sin_ruido` (KPI-6).** La §2.4 de la v1
  declara honestamente que se abrieron **3 de 9** YAML del corpus y que los casos borde de
  `ci-batch.yml` se tomaron de segunda mano. El riesgo nº1 de este plan no es fallar: es
  **producir ruido** — 40 filas basura matan el KPI-2 y el operador no vuelve a mirar la matriz
  nunca más. Este test parametrizado sobre los **9** archivos convierte una deuda declarada en un
  **gate binario**, sin abrir un archivo a mano, sin LLM, sin red y sin trabajo del operador.
- **`[ADICIÓN ARQUITECTO 2]` — `pending_fingerprint` (§4.2-bis).** sha256 (16 hex) de las celdas
  `falta`+`manual` ordenadas. Le da al operador un *"bajó de 9 a 6"* en vez de comparar dos tablas
  a ojo (huella anterior en `localStorage`, **cero persistencia backend**), le da al **Plan 252**
  la identidad de la foto a la que corresponde su paquete, y regala un detector de
  no-determinismo. 4 líneas puras, 0 red, 0 LLM, 0 estado nuevo.

### Veredicto

**v1: RECHAZADO** — 5 bloqueantes, de los cuales **3 hacían el plan literalmente inimplementable**
(C1 gate imposible por construcción; C2 y C3 tests que no podían pasar ni ejecutarse; C4
contradicción sin salida) y **1 era un agujero de seguridad real con un test que lo tapaba** (C5).

**v2: APROBADO-CON-CAMBIOS.** Criterios binarios que lo sostienen:

1. Los 5 bloqueantes tienen fix concreto **y** un test que lo prueba. **Sí**
2. **Ninguna fase escribe**, verificado fase por fase — incluido `server_registry.list_servers()`
   (llama a `_load()`, **nunca** a `_save()`) y `_request_paginated` (GET). El grep de escritura de
   la DoD cubre los 3 archivos backend nuevos. **Sí** ⇒ la flag **default ON** es correcta:
   **ninguna de las 4 excepciones duras aplica**.
3. La caja fuerte del **Plan 94 existe hoy** (`services/ci_variables.py:63,66`;
   `services/ado_variables.py:25`; `services/gitlab_variables.py:22`; `api/devops_variables.py:8`;
   flag en `harness_flags.py:224`/`:3041`), y este plan **no crea una segunda**: el único camino de
   escritura sigue siendo `POST /api/devops/variables` con `confirm:true` (`:72-73`). **Sí**
4. **Cero LLM** en las 6 fases ⇒ paridad trivial de Codex CLI / Claude Code CLI / Copilot Pro,
   con gate de grep. Ningún modelo ve un secreto porque no hay modelo. **Sí**
5. Human-in-the-loop intacto: Stacky enumera y muestra; **no rellena, no adivina, no propone
   valores**, y el CTA lleva al formulario HITL que ya existe. **Sí**
6. Cero trabajo extra al operador; sin RBAC; backward-compatible con la flag OFF. **Sí**

**Pendiente para el implementador (no bloquea la aprobación del papel):** el smoke visual único
del §10 y registrar la huella de regresión de C21.
