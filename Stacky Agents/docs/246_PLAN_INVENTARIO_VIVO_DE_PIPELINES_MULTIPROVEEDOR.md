# Plan 246 — Inventario vivo de pipelines multiproveedor

> **Estado:** PROPUESTO v1
> **Serie:** "Mago de las Pipelines" (246–252) — **este plan es el 1 de 7 y el CIMIENTO**.
> **Fecha:** 2026-07-26
> **Flag:** `STACKY_PIPELINE_INVENTORY_ENABLED` — default **ON**
> **Núcleo:** determinista, **sin LLM** (ver §3.1)
> **Fases:** F0..F5 (6 fases)

---

## 0. Hoja de ruta de la serie 246–252 (este plan es además el índice)

### 0.1 Las 7 piezas y su frontera dura

| Nº | Título corto | Alcance EXCLUSIVO | Prohibido tocar |
|----|--------------|-------------------|-----------------|
| **246** | Inventario vivo de pipelines multiproveedor | Descubrir TODAS las pipelines (definiciones ADO + GitLab + YAMLs del repo), unificarlas en un registro con estado de última corrida, proveedor, ruta, rama default y trigger. Listado en el panel. **Además: este §0 con la hoja de ruta y el mapa de colisiones.** | No clasifica stack ni propósito (247). No audita (248). No edita (250). |
| **247** | Perfilador: stack + anatomía + propósito | Dado un YAML ya descubierto por el 246, extraer stack tecnológico, fases (build/test/deploy), artefactos, entornos tocados y un propósito en 1 línea. Determinista primero; el propósito narrado es la única parte con LLM y es opcional. | No descubre (consume el registro del 246). No emite hallazgos de seguridad (248). |
| **248** | Auditoría: seguridad, malas prácticas y recomendaciones | Reglas `SEC001..SECnn` + recomendaciones de optimización. Read-only, no autofixea. | No repite `PL001..PL014` de `pipeline_lint.py` ni `RS001..RS009` de `cicd_semantic_rules.py`: las **consume**. No aplica cambios (250). |
| **249** | Paridad GitLab del motor inteligente | Catálogo de constructos GitLab + reglas `GL001..GLnn` + endurecimiento del renderer/parser GitLab. | No toca el catálogo ADO salvo para leerlo. No inventa NL (244). |
| **250** | Edición/optimización por lenguaje natural | Patch **quirúrgico** sobre el YAML existente (no regeneración), diff visible, commit HITL por el flujo existente. | No crea pipelines desde cero (243/244). No define reglas nuevas (248/249). |
| **251** | Matriz de entornos | Detectar qué valores por entorno exige una pipeline, formulario por entorno, marcar faltantes, resolver contra la caja fuerte del Plan 94. | No escribe en el servidor. No genera el zip (252). |
| **252** | Paquete de entrega + frontera de capacidades | Declarar qué puede hacer Stacky solo y qué no; empaquetar `.zip` + README operativo. | No ejecuta nada en el servidor. Consume 246/247/251, no los reimplementa. |

### 0.2 Grafo de dependencias

```
                    ┌─────────────┐
                    │  246        │  ← ESTE PLAN (cimiento: crea el registro)
                    │ Inventario  │
                    └──────┬──────┘
                           │
              ┌────────────┼──────────────────┐
              │            │                  │
              ▼            ▼                  ▼
        ┌─────────┐   ┌─────────┐      (independiente
        │  247    │   │  249    │       de la cadena)
        │Perfilador│  │ GitLab  │
        └────┬────┘   └─────────┘
             │
    ┌────────┼─────────┐
    ▼        ▼         ▼
┌──────┐ ┌──────┐ ┌───────┐
│ 248  │ │ 250  │ │  251  │
│Audit │ │Editor│ │Entornos│
└───┬──┘ └───┬──┘ └───┬───┘
    └────────┼────────┘
             ▼
        ┌─────────┐
        │  252    │  ← consume 246 + 247 + 251
        │ Bundle  │
        └─────────┘
```

**Regla literal:** `246 → 247 → {248, 250, 251} → 252`. El **249 es independiente** de esa cadena
y puede implementarse en cualquier momento **después** del 246.

**Regla de degradación cruzada (obligatoria para los 6 planes siguientes):** cada plan declara en
su §2 qué consume de los anteriores y **degrada explícito si el anterior no está implementado**.
Concretamente para este plan: si el 247/248/251/252 no encuentran `services/pipeline_inventory.py`,
deben mostrar "inventario no disponible" y seguir funcionando; **nunca** reimplementar el
descubrimiento.

### 0.3 Mapa de colisiones — qué archivo comparte cada plan y en qué orden mergear

> Precedente de la casa: `docs/195_PLAN_DEVOPS_HOJA_DE_RUTA_SERIE_186_193_...md:128-148` (§5 "Orden
> canónico"). Este §0.3 es el equivalente para la serie 246–252.

**Superficies compartidas por TODOS los 7 planes** (colisión garantizada en cada merge):

| Archivo compartido | Anclaje verificado | Qué agrega cada plan | Tipo de conflicto |
|---|---|---|---|
| `backend/services/harness_flags.py` | `:120 (_CATEGORY_KEYS)`, `:241` (entrada devops), `:2023 (FlagSpec STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED)` | 1 `FlagSpec` + 1 línea en `_CATEGORY_KEYS` | **Aditivo** — unión de líneas |
| `backend/config.py` | `:1337-1339` (patrón `os.getenv(...).lower() == "true"`) | 1 atributo | **Aditivo** |
| `backend/tests/test_harness_flags.py` | `:467 (_CURATED_DEFAULTS_ON)`, `:887` (assert de igualdad exacta) | 1 clave por flag default-ON | **Aditivo, pero el assert es igualdad de conjuntos ⇒ un merge que pierda una línea deja rojo** |
| `backend/scripts/run_harness_tests.sh` | `:20 (HARNESS_TEST_FILES=()` | 1 línea por test nuevo | **Aditivo** |
| `backend/scripts/run_harness_tests.ps1` | `:13 ($HarnessTestFiles = @()` | idem (**la gemela Windows**) | **Aditivo** |

**Superficies compartidas por los planes con blueprint + sección de panel** (246, 248, 250, 251, 252):

| Archivo compartido | Anclaje verificado | Colisión |
|---|---|---|
| `backend/api/__init__.py` | `:44` (import `pipeline_generator_bp`), `:117` (`api_bp.register_blueprint`) | 2 líneas por plan, en dos bloques distintos |
| `backend/api/devops.py` | `:28 (_health_payload)`, `:72` (`cockpit_enabled`), `:73-84` (cola de keys) | 1 key de health por plan, al final del dict |
| `frontend/src/pages/DevOpsPage.tsx` | `:32 (DevOpsHealth)`, `:113 (DEVOPS_SECTIONS)`, `:216-226` (entrada del Plan 201) | 1 key en la interfaz + 1 import + 1 entrada en el array |
| `frontend/src/api/endpoints.ts` | `:3818 (DevOps)`, `:4426 (PipelineGenerator)` | 1 namespace `export const` nuevo por plan, al final |

**Superficies EXCLUSIVAS (cero colisión entre planes):**

| Plan | Archivos que sólo él toca |
|---|---|
| 246 | `services/pipeline_inventory.py` (crea), `api/pipeline_inventory.py` (crea), `services/ado_pipeline_definitions.py` (+1 función), `services/ado_ci_provider.py` (+1 método opcional), `services/gitlab_ci_provider.py` (+1 método opcional), `frontend/src/devops/pipelineInventoryModel.ts`, `components/devops/PipelineInventorySection.tsx` |
| 247 | `services/pipeline_profiler.py`, `frontend/src/devops/pipelineProfileModel.ts`, `components/devops/PipelineProfileCard.tsx` — **y EXTIENDE `api/pipeline_inventory.py` del 246 (secuencia dura: nunca en paralelo con el 246)** |
| 248 | `services/cicd_security_rules.py`, `services/pipeline_recommendations.py`, `api/pipeline_audit.py`, `pipelineAuditModel.ts`, `PipelineAuditPanel.tsx` |
| 249 | `services/cicd_gitlab_catalog.py`, **`services/cicd_semantic_rules.py`** (único plan que lo edita), `services/pipeline_renderers.py`, `gitlabProfileModel.ts` |
| 250 | `services/pipeline_patcher.py`, `services/pipeline_diff.py`, `api/pipeline_editor.py`, `pipelineEditModel.ts`, `PipelineEditNlPanel.tsx` |
| 251 | `services/pipeline_environments.py`, `api/pipeline_environments.py`, `pipelineEnvMatrixModel.ts`, `PipelineEnvMatrixPanel.tsx` |
| 252 | `services/pipeline_handoff_bundle.py`, `services/pipeline_capability_frontier.py`, `api/pipeline_handoff.py`, `pipelineHandoffModel.ts`, `PipelineHandoffPanel.tsx` |

**Orden de merge canónico (no negociable):**

1. **246** — primero SIEMPRE. Crea `services/pipeline_inventory.py`, `api/pipeline_inventory.py` y
   los dos métodos opcionales del seam CI. Todo lo demás los consume.
2. **247** — segundo. Es el ÚNICO que edita `api/pipeline_inventory.py` además del 246 ⇒
   **jamás en paralelo con el 246**, siempre sobre el árbol del 246 ya mergeado.
3. **249** — puede entrar en cualquier momento después del 246. Es el único que toca
   `cicd_semantic_rules.py` y `pipeline_renderers.py` ⇒ no choca con nadie salvo en las 5
   superficies universales.
4. **248, 250, 251** — en paralelo entre sí (archivos disjuntos), cada uno rebasado sobre el 247.
5. **252** — último. Consume 246 + 247 + 251 ya mergeados.

**Gate obligatorio después de CADA merge de la serie** (mitiga el gotcha de merge duplicado
silencioso: git fusiona sin marcar conflicto cuando dos ramas agregan la misma línea de cierre):

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m compileall -q services api
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
```

---

## 1. Objetivo y valor

**Objetivo.** Que el operador abra el panel DevOps → **Pipelines → Inventario** y vea, **sin
configurar nada**, TODAS las pipelines que ya existen en su proyecto: las registradas en Azure
DevOps, las de GitLab, y **las que existen como archivo en el repo pero no están registradas en
ningún proveedor** (huérfanas). Cada una con proveedor, nombre, ruta del YAML, rama por default,
estado de la última corrida, fecha de esa corrida y trigger declarado.

**Read-only absoluto.** El inventario no crea, no edita, no registra y no dispara nada.

**KPI / impacto medible:**

| KPI | Antes (hoy) | Después (con el 246) |
|---|---|---|
| KPI-1 · Pipelines visibles en el panel sin salir de Stacky | **0** — el panel sólo muestra lo que el operador está construyendo en el builder | **N** — las 3 fuentes unificadas en una lista |
| KPI-2 · Detección de huérfanas (YAML en repo, no registrado) | Imposible sin abrir el portal ADO/GitLab y comparar a mano | **1 clic**, categoría `en_repo_sin_registrar` |
| KPI-3 · Detección de definiciones rotas (registradas apuntando a un YAML borrado) | Se descubre cuando falla la corrida | **1 clic**, categoría `registrada_sin_archivo` |
| KPI-4 · Llamadas de red por refresco | N/A | **≤ 3 en el camino feliz, ≤ 13 en el peor caso** (cap duro, §3.3) |
| KPI-5 · Trabajo de configuración del operador | N/A | **cero** (flag default ON, sin formularios, sin rutas que cargar) |
| KPI-6 · Pantallas rotas por integración no configurada | N/A | **0** — HTTP 200 siempre, con `available:false` por fuente |

**Valor estratégico:** los 6 planes siguientes de la serie no tienen sobre qué trabajar hasta que
exista este registro. El 247 perfila lo que el 246 descubrió; el 248 audita lo que el 247 perfiló;
el 250 edita lo que el 246 localizó; el 252 empaqueta lo que el 246 listó.

---

## 2. Evidencia (todo verificado por lectura directa el 2026-07-26)

> **Regla de anclajes de esta serie (§5 del dossier, §7.2 del Plan 243):** todo anclaje lleva el
> **símbolo**, no sólo el número. El número es una pista; si no coincide, greppeá el símbolo.
> **Nada de lo que está en §2.1–§2.3 fue escrito sin abrir el archivo.** Lo que no abrí está
> declarado en §2.4.

### 2.1 Lo que YA existe y este plan reutiliza sin reinventar

| Pieza | Anclaje (archivo:línea — símbolo) | Qué aporta al 246 |
|---|---|---|
| Definiciones ADO | `backend/services/ado_pipeline_definitions.py:82 (find_yaml_definition)` | La llamada `GET {base_proj}/_apis/build/definitions?api-version=7.1` ya está escrita y probada |
| Cap de definiciones | `ado_pipeline_definitions.py:5 (_MAX_DEFINITIONS = 50)` | **Cap ya existente y con comentario `[C12] cap explícito — el click no cuelga`**: se REUSA, no se redefine |
| Degradación a None | `ado_pipeline_definitions.py:89,116-117` (`try/except Exception: return None`) | Precedente literal: *"Nunca lanza hacia arriba: TrackerApiError/errores -> None (el caller degrada a 'unavailable')"* (`:87-88`) |
| Cliente ADO | `backend/services/ado_client.py:269 (AdoClient._request)`, `:38 (_TIMEOUT_SEC = 30)` | HTTP con timeout ya fijado ⇒ el 246 **no** define timeouts propios |
| Mapa de estados ADO→vocabulario común | `backend/services/ado_ci_provider.py:135 (_map_status)` | Tabla literal `notStarted→created / inProgress→running / postponed→pending / completed+succeeded→success / completed+(failed\|partiallySucceeded)→failed / completed+canceled→canceled`. **Se reusa tal cual** |
| Última corrida por ref (ADO) | `ado_ci_provider.py:107 (last_pipeline_for_ref)` | Patrón `$top=1&queryOrder=queueTimeDescending`, con `except Exception: return None` (`:131-132`) |
| Última corrida (GitLab) | `backend/services/gitlab_provider.py:487 (fetch_pipelines)` | Devuelve `id/status/ref/sha/web_url/created_at/updated_at`; **ya devuelve `[]` ante cualquier error** (`:510-511`) |
| Seam multiproveedor | `backend/services/ci_provider.py:83 (CIProvider Protocol)`, `:107 (get_ci_provider)` | Fábrica que elige adapter por `tracker_type` y **valida `STACKY_GITLAB_ENABLED` antes de instanciar GitLab** (`:121-124`) |
| Cliente GitLab | `backend/services/gitlab_client.py:98 (_project_path)`, `:107 (_request)` → **devuelve `tuple[object, dict]` = `(body, headers)`** (`:116,120-121`) y **lanza `TrackerApiError`** (`:124-125`) | Primitiva HTTP para la fuente GitLab |
| Capacidad ausente ≠ bug | `backend/services/tracker_provider.py:55 (CapabilityUnavailable)`, `:69 (to_payload)` → `{available, capability, provider, reason, workaround}` | **Shape exacto** que el 246 emite por fuente degradada |
| Traducción HTTP 200 | `backend/api/errors.py:73 (capability_unavailable_envelope)` + `backend/app.py:793-796` (handler global gateado por `STACKY_CAPABILITY_DEGRADATION_ENABLED`) | Precedente Plan 218 F6 / Plan 148: **200 + `available:false`, nunca 500 mudo** |
| Flag de degradación | `backend/config.py:1203-1205 (STACKY_CAPABILITY_DEGRADATION_ENABLED)` — default `"true"` | Ya está ON por default; el 246 se apoya en ella, no la crea |
| Barrido de disco determinista | `backend/services/pipeline_stack_detector.py:19 (detect_stack)`, `:36-37` (lista de carpetas ignoradas), `:40,48` (tope de 500 entradas) | **Receta de barrido acotado ya validada**: profundidad máxima, ignore-list, tope de entradas, `except OSError: return None` (`:54-55`) |
| Raíz del workspace | `backend/runtime_paths.py:66 (_active_workspace_root)`, `:138 (repo_root)` | Cómo se resuelve la carpeta que hay que barrer, sin preguntarle nada al operador |
| Patrón de blueprint | `backend/api/pipeline_generator.py:24 (bp = Blueprint(..., url_prefix="/pipeline-generator"))`, `:37` (guard **per-request** con `abort(404)`) | Patrón EXACTO a copiar. También `backend/api/pipelines.py:11 (_ensure_enabled)` |
| Registro de blueprint | `backend/api/__init__.py:44` (import), `:117` (`api_bp.register_blueprint(pipeline_generator_bp)`) | Dos líneas, dos bloques |
| Health del panel | `backend/api/devops.py:28 (_health_payload)`, `:72` (`cockpit_enabled`), `:88 (devops_health_route)` — *"SIEMPRE 200"* (`:90`) | Dónde va la key nueva. **`/bootstrap` reusa el mismo payload** (`:102`) ⇒ la paridad sale gratis |
| Registro de secciones del panel | `frontend/src/pages/DevOpsPage.tsx:113 (DEVOPS_SECTIONS)`, `:75 (interface DevOpsSection)`, `:216-226` (entrada del Plan 201 como plantilla) | *"Sumar una sección DevOps futura = 1 entrada + 1 componente, CERO cambios en este archivo"* (`:8`) |
| Grupos del cockpit | `frontend/src/pages/devopsCockpitShell.ts:9 (DevOpsGroupId)`, `:20 (DEVOPS_SECTION_GROUPS)` — grupo `construir` = *"Pipelines y variables"* (`:23`) | Dónde se monta la sección nueva |
| Contrato anti-sondeo | `DevOpsPage.tsx:68-71` (`visible?: boolean` — *"Las secciones que sondean DEBEN gatear su refetchInterval con esto"*), `:466` (`visible: activeId === s.id`) | El 246 **no sondea**: cumple por construcción |
| Bitácora CI local | `backend/services/ci_run_ledger.py:23 (ENTRY_FIELDS)`, `:84 (list_runs)` | Ver §2.3: **NO sirve** como fuente de última corrida por definición |
| Corpus dorado | `backend/tests/fixtures/cicd_nl/golden/` — **9 `.yml`, verificados por listado**: `agendaweb-ci.yml`, `bootstrap-server-environment.yml`, `cd-deploy-test.yml`, `ci-batch.yml`, `ci-cd-online.yml`, `ci-dacpac.yml`, `nightly-build-online.yml`, `pr-validation-online.yml`, `security-scan-online.yml` | **Fixture real de F1**, en vez de YAMLs de juguete |
| YAML disponible | `backend/services/pipeline_renderers.py:13 (import yaml)` | PyYAML está en el backend; `yaml.safe_load` es legal |
| Ratchet de tests | **DOS listas**: `backend/scripts/run_harness_tests.sh:20 (HARNESS_TEST_FILES=()` y `backend/scripts/run_harness_tests.ps1:13 ($HarnessTestFiles = @()`. El meta-test `backend/tests/test_harness_ratchet_meta.py:19 (_ratchet_files)` **parsea sólo el `.sh`** | Registrar en las DOS; el `.sh` es el que pone verde al meta-test |
| Flags | `backend/services/harness_flags.py:120 (_CATEGORY_KEYS)`, `:241` (última entrada devops), `:2023-2035 (FlagSpec de STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED)` + `backend/tests/test_harness_flags.py:467 (_CURATED_DEFAULTS_ON)`, `:887` | Receta de 5 patas de una flag default-ON |
| Namespaces de API del front | `frontend/src/api/endpoints.ts:3818 (export const DevOps)`, `:4426 (export const PipelineGenerator)`, `:4428 (preview)` | Patrón del accesor nuevo |

### 2.2 El gap: hoy el panel no sabe qué pipelines existen

Verificado abriendo los tres archivos que podrían saberlo:

- **`ado_pipeline_definitions.py` resuelve UNA definición, no lista.** `find_yaml_definition(project,
  yaml_path)` (`:82`) itera las definiciones **buscando una coincidencia** con `yaml_path` y devuelve
  `{'id','name'}` **o `None`** (`:113,115`). No hay ninguna función que devuelva el conjunto.
- **El seam CI no tiene método de inventario.** `CI_PORT_METHODS` (`ci_provider.py:100`) está
  **congelado** en exactamente 3 métodos: `("infer_item_pipeline", "monitor_pipeline",
  "trigger_pipeline")`, con el comentario *"Contrato congelado — no renombrar sin actualizar
  centinela del Plan 71/72"* (`:98-99`). Ninguno de los tres lista pipelines: los tres operan sobre
  **un ítem de tracker** o **un pipeline_id ya conocido**.
- **El panel no tiene sección de inventario.** `DEVOPS_SECTIONS` (`DevOpsPage.tsx:113-227`) tiene 11
  entradas y ninguna lista pipelines existentes: `pipelines` (`:127`) monta
  `PipelineBuilderSection` (el **constructor**, no un inventario).

**Consecuencia:** hoy, para saber qué pipelines tiene su proyecto, el operador abre el portal de
Azure DevOps en el navegador y compara a mano contra el árbol del repo. Ese es exactamente el
trabajo que este plan elimina.

### 2.3 Los dos riesgos reales de este dominio (y por qué el diseño es el que es)

**(a) Costo y latencia — listar es I/O de red.**

- `_MAX_DEFINITIONS = 50` (`ado_pipeline_definitions.py:5`) existe con el comentario
  `[C12] cap explícito — el click no cuelga`. Es la prueba de que la casa YA sufrió este problema.
- Peor todavía: `find_yaml_definition` hace **N+1 llamadas**. Cuando la lista no trae `process`,
  hidrata cada definición con un `GET` de detalle (`:99-110`). Con 50 definiciones sin `process`,
  son **51 llamadas de red** para resolver UNA pipeline.
- **Por eso el 246 NO reusa `find_yaml_definition` para listar.** F2 escribe una función nueva de
  listado con **hidratación acotada** (`hydrate_missing=10`) y **el conteo de llamadas es un
  criterio de aceptación binario** (§F2), no una promesa.

**(b) El ledger local NO sirve como fuente de última corrida.**

`ci_run_ledger.ENTRY_FIELDS` (`:23-26`) es una **ALLOWLIST estricta** de 10 campos:
`project, tracker_type, ref, sha, pipeline_id, web_url, triggered_at, source, last_status,
finished_at`. **No hay `yaml_path` ni `definition_id`.** Y `pipeline_id` es el id de la **corrida**,
no el de la definición. Además el ledger sólo registra corridas **que Stacky disparó**
(`append_run` se llama desde el hook del trigger, `:71-72`).

⇒ **Decisión de diseño, con su porqué:** el estado de última corrida se pide **al proveedor**, no
al ledger. El ledger queda fuera del 246. Escribirlo distinto habría producido un inventario que
sólo conoce las corridas que Stacky mismo lanzó — es decir, casi ninguna.

**(c) Degradación por integración no configurada.**

`get_ci_provider` (`ci_provider.py:107`) **lanza `TrackerConfigError`** si el tracker es GitLab y
`STACKY_GITLAB_ENABLED` está en false (`:121-124`), y lanza si el tracker no tiene adapter (`:133`).
Sin PAT de ADO, `AdoClient._request` falla. Un inventario ingenuo revienta con 500 en las dos
situaciones, que son **el caso normal** de un operador que usa un solo proveedor.

⇒ El 246 **nunca deja escapar una excepción**: cada fuente devuelve su propio bloque
`{available:false, capability, provider, reason, workaround}` con el shape exacto de
`CapabilityUnavailable.to_payload()` (`tracker_provider.py:69-72`), y el endpoint responde
**200 siempre**. Precedente: Plan 148 y Plan 218 F6 (`api/errors.py:76-79`).

### 2.4 Lo NO verificado (declarado)

Esto **no** lo abrí y por lo tanto no lo doy por cierto. Cada ítem lleva su plan B escrito.

1. **La API de Build de ADO acepta `definitions=<csv>` combinado con `queryOrder` / `$top`.**
   NO VERIFICADO (sin red y sin abrir documentación). Lo que sí verifiqué es que
   `last_pipeline_for_ref` (`ado_ci_provider.py:114-117`) usa `branchName` + `$top=1` +
   `queryOrder=queueTimeDescending`, o sea que **esos** parámetros existen.
   **Plan B escrito en F2:** si la llamada batch devuelve algo inservible o falla, la fuente marca
   `last_run.status = "unknown"` con `status_detail = "batch_no_soportado"` para TODAS las entradas.
   **Prohibido caer a un bucle de N llamadas** — el cap de §3.3 es duro.

2. **`GET /projects/{path}` de GitLab devuelve `ci_config_path`.** NO VERIFICADO. Confirmado en
   cambio que **`ci_config_path` no aparece en ningún archivo de `backend/services/`** (grep = 0
   hits) ⇒ hoy nadie lo lee. **Plan B escrito en F3:** si la key falta o la llamada falla, se asume
   el default de GitLab `.gitlab-ci.yml` y se marca `yaml_path_source: "convencion"`.

3. **Si la lista `/build/definitions` de ADO trae o no `process` para cada definición.**
   NO VERIFICADO contra un tenant real. La evidencia indirecta (`ado_pipeline_definitions.py:100-101`,
   comentario *"La lista no siempre trae 'process' completo: hidratar detalle"*) dice que **a veces
   no**. Por eso F2 lleva hidratación acotada y un flag de salida `truncated_hydration`.

4. **El contenido de los 9 YAML del corpus dorado.** Verifiqué que **existen** (listado de
   directorio con tamaños). **No abrí ninguno.** Los datos de caso borde que uso en F1
   (`nightly-build-online.yml:110` script crudo; `ci-batch.yml:58-59` matrix;
   `bootstrap-server-environment.yml` con 17 expresiones `${{ }}`; refs a tareas dentro de
   comentarios en `agendaweb-ci.yml:142` y `ci-dacpac.yml:102`) los tomo del **§2.4 del dossier de
   la serie y del §2.2 del Plan 243**, no de lectura propia.
   **Consecuencia práctica:** F1 **no** afirma cuántos de los 9 clasifican como `ado`; su criterio
   de aceptación se escribe como *"los 9 archivos se clasifican sin lanzar y ninguno queda `None`"*
   más un test por regla, no como un número de reparto inventado.

5. **`pipeline_lint.py`, `cicd_semantic_rules.py`, `cicd_task_catalog.py`, `cicd_corpus_mirror.py`,
   `PipelineBuilderSection.tsx`.** NO ABIERTOS en esta corrida. Los cito sólo por nombre (para
   declarar que el 246 **no** los toca), nunca con `archivo:línea` propio.

6. **Deriva detectada en un docstring existente (no la arreglo, la declaro):**
   `ado_pipeline_definitions.py:83-84` dice *"via AdoClient._request, ado_client.py:257"*, pero
   `def _request` está en **`ado_client.py:269`**. Es exactamente el tipo de anclaje que la regla
   §5 del dossier prohíbe. **No corregirlo en este plan** (fuera de alcance); anotado para que
   quien implemente no se confunda.

7. **El frontend no tiene jsdom ni `@testing-library/react`.** Lo tomo del arnés conocido de la
   casa, **no reverificado en esta corrida**. Consecuencia asumida en F5: **sólo el modelo puro
   `.ts` lleva tests automatizados**; el `.tsx` se valida con `npx tsc --noEmit` + smoke visual del
   operador. F5 **no promete** un test de componente.

---

## 3. Principios, guardarraíles y recorte declarado de alcance

### 3.1 El núcleo NO usa LLM — y eso es una decisión, no una omisión

**Descubrir y reconciliar pipelines es determinista.** Listar definiciones es una llamada HTTP;
barrer el repo es `os.walk` + `yaml.safe_load`; reconciliar es comparar claves normalizadas;
clasificar el trigger es leer una key del documento. **Ninguna de esas operaciones necesita un
modelo.**

Consecuencias directas, todas verificables:

- **Paridad de los 3 runtimes es trivial y demostrable.** Codex CLI, Claude Code CLI y GitHub
  Copilot Pro ejecutan el mismo código Python/TS determinista. No hay prompt, no hay temperatura,
  no hay `fixture_id`, no hay respuesta que varíe. **El mismo input produce el mismo output byte a
  byte en los 3.** El "fallback por runtime" de cada fase es literalmente *no aplica*.
- **Cero costo de tokens.** El inventario no consume presupuesto de modelo, ni al abrir el panel ni
  al refrescar.
- **Testeable sin red y sin modelo.** F0 es 100% puro; F1 sólo toca disco; F2/F3 se prueban con
  clientes falsos.

La parte narrada/interpretativa (qué hace esta pipeline, si es segura, qué le falta) es
**explícitamente de otros planes**: 247 y 248.

### 3.2 Guardarraíles no negociables (§6 del dossier)

| Riel | Cómo lo cumple este plan | Verificable en |
|---|---|---|
| **Paridad 3 runtimes** | Núcleo determinista sin LLM ⇒ idéntico en Codex / Claude Code / Copilot Pro. Fallback por ítem: *no aplica, no hay llamada a modelo*. | §3.1, y la línea "Impacto por runtime" de cada fase |
| **Cero trabajo extra al operador** | Flag `STACKY_PIPELINE_INVENTORY_ENABLED` **default ON**. **Ninguna de las 4 excepciones duras aplica**: (1) no bypasea revisión humana — es read-only y no dispara nada; (2) no es destructiva ni irreversible — no escribe una sola línea en ningún lado; (3) no tiene prerequisito extra — degrada solo si falta el proveedor; (4) no reduce seguridad — no expone secretos ni abre superficie. Sin formularios, sin rutas que cargar, sin credenciales nuevas. | Línea literal `Trabajo del operador: ninguno` en cada fase |
| **Human-in-the-loop innegociable** | El plan es **read-only absoluto**. No hay ningún camino de código que cree, registre, edite, commitee ni dispare. No hay autonomía proactiva: el inventario se calcula **cuando el operador abre la sección** o pulsa "Actualizar". Sin daemons, sin hilos, sin polling. | §F4 (no hay verbos POST/PUT/DELETE) y §F5 (sin `refetchInterval`) |
| **Mono-operador sin auth real** | Cero RBAC, cero roles, cero chequeos de permiso. El endpoint no lee `current_user`. | §F4 |
| **No degradar performance** | ≤3 llamadas de red en el camino feliz (≤13 peor caso), TTL de 300s, barrido de disco acotado a 400 archivos / profundidad 4 / 512 KB por archivo, sin hilos de fondo. | §3.3 + criterio binario de F2 |
| **No degradar seguridad** | Read-only; no imprime contenido de YAML (sólo rutas, nombres y el bloque de trigger); no toca la caja fuerte de variables. | §F1 (el extractor devuelve estructura, nunca el texto crudo) |
| **No degradar estabilidad** | Ninguna función del 246 puede lanzar hacia el endpoint: cada fuente atrapa `Exception`. El endpoint responde 200 siempre. | §F3 + §F4 |
| **Backward-compatible** | **`CIProvider` Protocol y `CI_PORT_METHODS` quedan INTACTOS.** Los métodos nuevos son opcionales y duck-typed. Health y `/bootstrap` sólo suman una key. | §3.4 |
| **Reusar lo existente** | `_MAX_DEFINITIONS`, `_map_status`, `AdoClient._request`, `_TIMEOUT_SEC`, `fetch_pipelines`, `CapabilityUnavailable`, la lista de ignorados de `pipeline_stack_detector`, el patrón de blueprint, `DEVOPS_SECTIONS`. | §2.1 |

### 3.3 Caps, timeouts y cacheo — todos explícitos

Constantes de módulo en `services/pipeline_inventory.py` (**precedente literal:
`_MAX_DEFINITIONS = 50` en `ado_pipeline_definitions.py:5`, que es una constante de módulo y no una
flag**):

| Constante | Valor | Por qué |
|---|---|---|
| `_MAX_SCAN_FILES` | `400` | Tope de archivos inspeccionados en el barrido. `pipeline_stack_detector.py:40` usa 500 para un barrido más superficial; 400 acá porque cada candidato se parsea |
| `_MAX_SCAN_DEPTH` | `4` | Profundidad máxima desde la raíz. `pipeline_stack_detector.py:33` usa 2; 4 porque las pipelines suelen vivir en `pipelines/`, `.azuredevops/`, `build/ci/` |
| `_MAX_YAML_BYTES` | `512_000` | Un archivo mayor se salta **sin parsear** (`skipped_too_big`). Evita colgar el parser con un YAML generado |
| `_MAX_BUILDS_SCAN` | `100` | `$top` de la llamada batch de builds |
| `_MAX_HYDRATE` | `10` | Tope de `GET` de detalle para definiciones sin `process` (§2.3-a) |
| `_CACHE_TTL_SEC` | `300` | TTL del cache en proceso |
| `_MAX_DEFINITIONS` | **importado de `ado_pipeline_definitions`** | No se redefine |
| Timeout de red | **heredado de `ado_client._TIMEOUT_SEC = 30`** (`ado_client.py:38`) | No se redefine |

**Presupuesto de red por refresco (criterio binario de F2/F3):**

```
Camino feliz:  1 (definiciones ADO) + 1 (builds batch) + 1 (pipelines GitLab)   = 3
Peor caso:     1 + 10 (hidratación acotada) + 1 + 1                              = 13
NUNCA:         un bucle de una llamada por definición
```

**Cacheo:** diccionario en proceso `_CACHE: dict[str, tuple[float, dict]]` con clave
`f"{project or ''}"`. `?refresh=1` en el endpoint lo saltea. **Sin daemon, sin hilo, sin
`threading.Timer`, sin polling.** El cache se llena sólo cuando alguien pide el inventario.

**Por qué el TTL es constante y no flag:** el operador no tiene por qué decidir un TTL de cache;
es un detalle interno de performance, exactamente como `_MAX_DEFINITIONS`. Una flag extra sería
trabajo extra para el operador (viola el riel de §3.2) y una superficie más en
`_CURATED_DEFAULTS_ON`. **Este plan declara UNA sola flag.**

### 3.4 Cómo se engancha al seam multiproveedor sin romperlo

`CI_PORT_METHODS` está **congelado** (`ci_provider.py:98-100`). Agregar un cuarto método al
`Protocol` rompería el centinela del Plan 71/72.

**Precedente que resuelve esto, verificado abriendo los dos adapters:** `last_pipeline_for_ref`
existe en **`ado_ci_provider.py:107`** y en **`gitlab_ci_provider.py:70`**, pero **NO** está en el
`Protocol` (`ci_provider.py:88-95`) **ni** en `CI_PORT_METHODS`. Es decir: la casa ya tiene el
patrón de **capacidad opcional duck-typed** sobre los adapters, sin tocar el contrato congelado.

**El 246 sigue exactamente ese patrón:**

```python
# En pipeline_inventory.py — consumo duck-typed, nunca isinstance:
lister = getattr(provider, "list_pipeline_definitions", None)
if not callable(lister):
    return _source_unavailable(
        source_id="provider_definitions",
        capability="list_pipeline_definitions",
        provider=getattr(provider, "name", "desconocido"),
        reason="El adapter de CI de este proveedor todavia no expone el inventario.",
        workaround="Actualiza Stacky o usa el barrido del repositorio, que ya esta listado abajo.",
    )
```

**Consecuencia buscada:** un adapter futuro (o un deploy viejo) que no tenga el método **no rompe
nada** — la fuente aparece como no disponible y el resto del inventario sigue.

### 3.5 Recorte de alcance declarado (para que entre en UNA corrida)

El dossier obliga a un máximo de 6-7 fases. Recorto yo, acá, y lo declaro:

| Recortado | Adónde va |
|---|---|
| Estado de última corrida **por rama** (no sólo la más reciente) | Fuera de la serie. El 246 muestra **la última corrida, punto** |
| Historial / tendencia de corridas por pipeline | Ya existe el Centro de Costos y la telemetría del 171/199. Fuera |
| Inventario de **variable groups**, service connections, environments de ADO | Es del **251** (matriz de entornos) |
| Inventario de **runners/agent pools** | Fuera de la serie |
| Detección de pipelines en ramas distintas de la default | Fuera. El barrido es sobre el **working tree local** |
| Persistencia del inventario en disco (JSONL/BD) | Fuera. El cache es en proceso y volátil, a propósito: un inventario viejo es peor que ninguno |
| Cualquier interpretación del contenido del YAML más allá del bloque de trigger | **247** |

---

## 4. Fases

### F0 — Núcleo determinista de reconciliación (PURO: sin red, sin disco, sin LLM)

**Objetivo (1 frase):** definir el modelo de datos del inventario y la función que reconcilia
entradas de N fuentes en un registro único con 3 categorías, sin tocar red ni disco.

**Valor que entrega:** el contrato que consumen los planes 247–252, testeable al 100% en
milisegundos.

**Archivos a CREAR:**
- `Stacky Agents/backend/services/pipeline_inventory.py`
- `Stacky Agents/backend/tests/test_plan246_pipeline_inventory.py`

**Símbolos EXACTOS a crear en `services/pipeline_inventory.py`:**

```python
"""services/pipeline_inventory.py — Plan 246. Inventario vivo de pipelines multiproveedor.

F0 es PURO: sin red, sin disco, sin LLM. Mismas entradas ⇒ mismas salidas.
READ-ONLY ABSOLUTO: este módulo no crea, no edita, no registra y no dispara nada.
"""
from __future__ import annotations

# ── Vocabularios CERRADOS (contrato congelado para 247..252) ──────────────────
CATEGORY_REGISTERED_WITH_FILE: str = "registrada+en_repo"
CATEGORY_REGISTERED_NO_FILE: str = "registrada_sin_archivo"
CATEGORY_FILE_NOT_REGISTERED: str = "en_repo_sin_registrar"
CATEGORIES: tuple[str, ...] = (
    CATEGORY_REGISTERED_WITH_FILE,
    CATEGORY_REGISTERED_NO_FILE,
    CATEGORY_FILE_NOT_REGISTERED,
)

RUN_STATUSES: tuple[str, ...] = ("success", "failed", "never_ran", "unknown")

PROVIDERS: tuple[str, ...] = ("azure_devops", "gitlab")

SOURCE_ADO_DEFINITIONS: str = "ado_definitions"
SOURCE_GITLAB_PIPELINES: str = "gitlab_pipelines"
SOURCE_REPO_SCAN: str = "repo_scan"

# ── Caps (§3.3) ───────────────────────────────────────────────────────────────
_MAX_SCAN_FILES: int = 400
_MAX_SCAN_DEPTH: int = 4
_MAX_YAML_BYTES: int = 512_000
_MAX_BUILDS_SCAN: int = 100
_MAX_HYDRATE: int = 10
_CACHE_TTL_SEC: int = 300


def normalize_yaml_path(raw: str | None) -> str:
    """Normaliza una ruta de YAML a la forma canonica de la clave de identidad.

    Reglas, EN ESTE ORDEN:
      1. None/""            -> ""
      2. "\\" -> "/"
      3. strip() de espacios
      4. quitar TODOS los prefijos "./" repetidos (while, no strip)
      5. quitar "/" iniciales (lstrip("/"))
      6. lower()

    TRAMPA (test negativo obligatorio): NO usar lstrip("./") — eso borra el punto
    inicial de ".gitlab-ci.yml" y lo convierte en "gitlab-ci.yml", partiendo en dos
    la identidad de la unica pipeline que GitLab tiene por proyecto.
    """


def identity_key(provider: str, yaml_path: str | None, definition_id: str | None = None) -> str:
    """Clave de identidad DETERMINISTA.

    - Con yaml_path no vacio:  f"{provider}::{normalize_yaml_path(yaml_path)}"
    - Sin yaml_path:           f"{provider}::#def{definition_id}"   (definicion clasica
                               de ADO sin YAML declarado)
    - Sin yaml_path y sin definition_id: f"{provider}::#desconocida"
    """


def make_entry(
    *,
    provider: str,
    name: str,
    yaml_path: str | None,
    default_branch: str | None,
    definition_id: str | None,
    category: str,
    category_reason: str = "",
    last_run: dict | None = None,
    trigger: dict | None = None,
    found_in: tuple[str, ...] = (),
) -> dict:
    """Construye una entrada del inventario con TODAS las claves siempre presentes.

    Shape CONGELADO (contrato que consumen 247..252):
      key, provider, name, yaml_path, default_branch, definition_id,
      category, category_reason, last_run, trigger, found_in
    last_run por defecto: {"status": "unknown", "status_detail": "sin_datos",
                           "at": None, "web_url": None, "run_id": None, "source": None}
    trigger  por defecto: {"kind": "unknown", "branches": [], "has_paths": False,
                           "has_schedule": False, "has_pr": False, "source": None}
    """


def reconcile(registered: list[dict], files: list[dict]) -> list[dict]:
    """Une definiciones registradas y archivos del repo en UN registro. PURO.

    Algoritmo LITERAL:
      1. index_reg  = {identity_key(r): r for r in registered}   (ultima gana en empate)
      2. index_file = {identity_key(f): f for f in files}
      3. Para cada key en sorted(set(index_reg) | set(index_file)):
         a. en ambos      -> CATEGORY_REGISTERED_WITH_FILE.
                             Campos: name/default_branch/definition_id/last_run del
                             REGISTRADO (el proveedor manda); yaml_path y trigger del
                             ARCHIVO (el disco manda). found_in = ambas fuentes.
         b. solo registrado -> CATEGORY_REGISTERED_NO_FILE.
                             category_reason = "sin_yaml_declarado" si yaml_path es None,
                             si no "archivo_ausente_en_repo".
                             trigger queda en su default (no hay archivo que leer).
         c. solo archivo   -> CATEGORY_FILE_NOT_REGISTERED.
                             category_reason = "huerfana".
                             last_run = {"status": "never_ran",
                                         "status_detail": "no_registrada", ...}
      4. Devuelve la lista ORDENADA por sort_key() (determinismo obligatorio).
    """


def sort_key(entry: dict) -> tuple:
    """Orden CANONICO, mas accionable primero:
       (rank_categoria, provider, name.lower(), key)
    rank: registrada_sin_archivo=0 (rota), en_repo_sin_registrar=1 (huerfana),
          registrada+en_repo=2 (sana).
    """


def counts(entries: list[dict]) -> dict:
    """{"total": n, "registrada+en_repo": n, "registrada_sin_archivo": n,
        "en_repo_sin_registrar": n}. Las 4 claves SIEMPRE presentes, aunque valgan 0."""


def source_ok(source_id: str, count: int, **extra) -> dict:
    """{"id", "available": True, "count", "capability": "", "provider": "",
        "reason": "", "workaround": "", **extra}"""


def source_unavailable(
    source_id: str, *, capability: str, provider: str, reason: str, workaround: str
) -> dict:
    """MISMO shape que source_ok pero available=False y count=0.

    Las claves capability/provider/reason/workaround son EXACTAMENTE las de
    CapabilityUnavailable.to_payload() (services/tracker_provider.py:69-72), para
    que la UI use un solo renderer para los dos caminos.
    """
```

**Tests PRIMERO — `backend/tests/test_plan246_pipeline_inventory.py` (casos EXACTOS):**

| # | Test | Verifica |
|---|---|---|
| 1 | `test_normalize_preserva_punto_inicial_de_gitlab_ci` | `normalize_yaml_path(".gitlab-ci.yml") == ".gitlab-ci.yml"` — **el test negativo de la trampa `lstrip("./")`** |
| 2 | `test_normalize_backslash_y_prefijos` | `"..\\\\pipelines\\\\CI.yml"`, `"./pipelines/ci.yml"`, `"/pipelines/ci.yml"`, `"pipelines/CI.yml"` → todas terminan en `"pipelines/ci.yml"` salvo la primera, que conserva el `..` (documentado: no se resuelve `..`) |
| 3 | `test_normalize_none_y_vacio` | `None` y `""` → `""` |
| 4 | `test_identity_key_con_y_sin_yaml` | `identity_key("azure_devops","pipelines/ci.yml") == "azure_devops::pipelines/ci.yml"`; sin yaml y con `definition_id="7"` → `"azure_devops::#def7"`; sin nada → `"azure_devops::#desconocida"` |
| 5 | `test_identity_key_es_estable_entre_llamadas` | 100 llamadas con la misma entrada dan el mismo string |
| 6 | `test_make_entry_tiene_las_11_claves` | Todas las claves del shape congelado presentes aunque se pasen sólo las obligatorias |
| 7 | `test_reconcile_ambas_fuentes_da_registrada_en_repo` | 1 registrada + 1 archivo con la misma key → 1 entrada, `category == "registrada+en_repo"`, `found_in == ("ado_definitions","repo_scan")` |
| 8 | `test_reconcile_prioriza_proveedor_para_nombre_y_disco_para_trigger` | Con `name` distinto en cada fuente gana el registrado; con `trigger` sólo en el archivo, gana el archivo |
| 9 | `test_reconcile_solo_registrada_sin_archivo` | `category == "registrada_sin_archivo"`, `category_reason == "archivo_ausente_en_repo"` |
| 10 | `test_reconcile_definicion_sin_yaml_declarado` | Registrada con `yaml_path=None` → `category_reason == "sin_yaml_declarado"` |
| 11 | `test_reconcile_huerfana` | Sólo archivo → `category == "en_repo_sin_registrar"`, `last_run["status"] == "never_ran"`, `last_run["status_detail"] == "no_registrada"` |
| 12 | `test_reconcile_es_determinista` | Las mismas listas en orden invertido producen **la misma lista** (byte a byte por `json.dumps(sort_keys=True)`) |
| 13 | `test_reconcile_listas_vacias` | `reconcile([], []) == []` y `counts([])` da las 4 claves en 0 |
| 14 | `test_sort_key_pone_las_rotas_primero` | Mezcla de las 3 categorías → orden `registrada_sin_archivo`, `en_repo_sin_registrar`, `registrada+en_repo` |
| 15 | `test_counts_suma_total` | `counts(e)["total"] == len(e)` y la suma de las 3 categorías == total |
| 16 | `test_source_unavailable_tiene_el_shape_de_capability_unavailable` | Las 4 claves `capability/provider/reason/workaround` presentes y de tipo `str`; `available is False`; `count == 0` |
| 17 | `test_f0_no_importa_red_ni_disco` | El módulo no importa `urllib`, `requests`, `os.walk`, `ado_client` ni `gitlab_client` a nivel de módulo (assert sobre `pipeline_inventory.__dict__` y sobre el AST del archivo) |

**Comando exacto:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan246_pipeline_inventory.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```
> **Ratchet:** agregar `tests/test_plan246_pipeline_inventory.py` a `HARNESS_TEST_FILES`
> (`backend/scripts/run_harness_tests.sh:20`) **y** a `$HarnessTestFiles`
> (`backend/scripts/run_harness_tests.ps1:13`). Sin la primera, el meta-test queda rojo.

**Criterio de aceptación BINARIO:** `pytest tests/test_plan246_pipeline_inventory.py -q` reporta
**17 passed, 0 failed**, y `pytest tests/test_harness_ratchet_meta.py -q` reporta **passed**.

**Flag:** `STACKY_PIPELINE_INVENTORY_ENABLED` (default **ON**) — se declara en F4. F0 es un módulo
puro sin consumidor: **inerte** hasta F4.

**Impacto por runtime (Codex / Claude Code / Copilot):** ninguno. La fase no invoca LLM; el código
es determinista puro. **Fallback por runtime: no aplica.**

`Trabajo del operador: ninguno`

---

### F1 — Fuente C: barrido del repositorio (huérfanas + trigger declarado)

**Objetivo (1 frase):** encontrar en el working tree local todos los archivos que **son** una
pipeline, clasificarlos por proveedor con reglas cerradas y extraer su bloque de trigger — sin red
y sin LLM.

**Valor que entrega:** la fuente que ningún proveedor puede dar: las pipelines huérfanas.

**Archivos a EDITAR:**
- `Stacky Agents/backend/services/pipeline_inventory.py` (agrega la sección de barrido)

**Archivos a CREAR:**
- `Stacky Agents/backend/tests/test_plan246_repo_scan.py`

**Símbolos EXACTOS a crear:**

```python
_IGNORED_DIRS: frozenset[str] = frozenset(
    # Las 7 primeras son LITERALMENTE las de pipeline_stack_detector.py:36-37 (reuso).
    {"node_modules", ".git", "venv", ".venv", "bin", "obj", "__pycache__",
     # extras propias del 246, declaradas:
     "dist", "build", "packages", ".vs", ".idea", "TestResults"}
)

_PIPELINE_DIR_HINTS: frozenset[str] = frozenset(
    {"pipelines", ".azuredevops", ".pipelines", "azure-pipelines", "ci", ".ci"}
)


def scan_repo_pipelines(root: str | None) -> tuple[list[dict], dict]:
    """Barre `root` buscando archivos de pipeline. Devuelve (entradas, meta).

    NUNCA lanza: cualquier OSError/UnicodeError/yaml.YAMLError se traduce a que ese
    archivo se salta (y se cuenta en meta), igual que detect_stack (pipeline_stack_detector.py:54-55).

    root None / inexistente -> ([], {"available": False, "reason": "sin_workspace_activo", ...})

    Recorrido (idéntico en espíritu a detect_stack, con los caps de §3.3):
      - os.walk desde normpath(root)
      - profundidad > _MAX_SCAN_DEPTH  -> dirnames[:] = []
      - dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
      - sólo se CONSIDERAN archivos cuyo nombre termina en ".yml" o ".yaml"
      - scanned += 1 por archivo considerado; scanned > _MAX_SCAN_FILES -> corta y
        meta["truncated"] = True
      - os.path.getsize(f) > _MAX_YAML_BYTES -> saltar, meta["skipped_too_big"] += 1
      - el ORDEN de recorrido se estabiliza con dirnames.sort() y filenames sorted()
        (os.walk no garantiza orden; sin esto el resultado no es determinista)

    meta = {"available": True, "scanned_files": int, "matched": int,
            "truncated": bool, "skipped_too_big": int, "skipped_unparseable": int,
            "root": str}
    """


def classify_pipeline_doc(basename: str, doc: object) -> str | None:
    """Clasifica un YAML ya parseado como 'azure_devops' | 'gitlab' | None.

    REGLAS CERRADAS, EVALUADAS EN ESTE ORDEN (primera que matchea gana):
      R1. basename.lower() in (".gitlab-ci.yml", ".gitlab-ci.yaml")      -> "gitlab"
      R2. not isinstance(doc, dict)                                       -> None
      R3. doc["stages"] es list no vacia y TODOS str                      -> "gitlab"
      R4. doc["stages"] es list y ALGUNO es dict con "stage" o "template" -> "azure_devops"
      R5. "pool" in doc or "steps" in doc or "jobs" in doc                -> "azure_devops"
      R6. "trigger" in doc and (es list, or es dict, or == "none")        -> "azure_devops"
          (en GitLab `trigger:` es clave de JOB, nunca top-level)
      R7. "workflow" in doc or "include" in doc                           -> "gitlab"
      R8. algun VALOR top-level es dict y tiene la clave "script"         -> "gitlab"
      R9. resto                                                            -> None

    DISCIPLINA C20 (Plan 243, docs/243_...md:106-113): el documento SIEMPRE llega
    parseado por yaml.safe_load. PROHIBIDO clasificar por grep/regex sobre el texto:
    el corpus real tiene refs a tareas DENTRO DE COMENTARIOS, y un regex las levanta.
    """


def extract_trigger(doc: object, provider: str) -> dict:
    """Extrae SOLO el bloque de disparo. Estructura, nunca texto crudo.

    Shape devuelto (5 claves + source, SIEMPRE presentes):
      {"kind": str, "branches": list[str], "has_paths": bool,
       "has_schedule": bool, "has_pr": bool, "source": "yaml"}

    ADO (tabla cerrada sobre doc.get("trigger", _ABSENT)):
      _ABSENT            -> kind="default"  (ADO sin trigger dispara en toda rama)
      "none" / None      -> kind="none"
      list[str]          -> kind="ci",  branches = esa lista
      dict con "branches"-> kind="ci",  branches = doc["trigger"]["branches"].get("include", [])
                                        has_paths = bool(doc["trigger"].get("paths"))
      otro               -> kind="unknown"
      has_schedule = "schedules" in doc
      has_pr       = doc.get("pr", _ABSENT) not in (_ABSENT, "none", None)

    GitLab:
      kind = "ci" si doc tiene "workflow" o al menos un job (valor dict con "script"),
             si no "unknown"
      branches = []            <- LIMITACION DECLARADA: GitLab no declara las ramas de
                                  disparo en un bloque top-level cerrado; interpretarlo
                                  es del plan 249. Se devuelve vacio, no se adivina.
      has_paths = False        <- idem
      has_schedule = False     <- LIMITACION DECLARADA: los schedules de GitLab viven en
                                  la UI del proyecto, no en el YAML.
      has_pr = True si en workflow.rules (lista de dicts) algun valor de "if" (str)
               contiene "merge_request_event". Busqueda ESTRUCTURAL sobre la lista,
               no grep sobre el archivo.
    """


def pipeline_name_from_path(path: str) -> str:
    """Nombre visible = basename sin extension. ".gitlab-ci.yml" -> ".gitlab-ci".
    Deterministico, sin heuristicas."""
```

**Fixture:** los **9 pipelines reales** de `Stacky Agents/backend/tests/fixtures/cicd_nl/golden/`
(§2.1). El test copia el directorio a un `tmp_path` con la estructura
`tmp/pipelines/<los 9>` + `tmp/.gitlab-ci.yml` (sintético mínimo, 3 líneas) +
`tmp/node_modules/malo.yml` (para probar el ignore) + `tmp/docs/notas.yml` (YAML que **no** es
pipeline, para probar R9 → `None`).

**Tests PRIMERO — `backend/tests/test_plan246_repo_scan.py`:**

| # | Test | Verifica |
|---|---|---|
| 1 | `test_scan_encuentra_los_nueve_del_corpus_dorado` | `meta["matched"] >= 9` y los 9 basenames del corpus aparecen en las rutas devueltas |
| 2 | `test_ningun_archivo_del_corpus_queda_sin_clasificar` | Para los 9, `classify_pipeline_doc(...) is not None` (§2.4-4: **no** afirmo el reparto ado/gitlab, sólo que ninguno queda `None`) |
| 3 | `test_scan_ignora_node_modules` | `tmp/node_modules/malo.yml` **no** está en el resultado |
| 4 | `test_scan_ignora_yaml_que_no_es_pipeline` | `tmp/docs/notas.yml` no está (R9) |
| 5 | `test_scan_root_none_devuelve_vacio_y_no_lanza` | `scan_repo_pipelines(None) == ([], meta)` con `meta["available"] is False` y `meta["reason"] == "sin_workspace_activo"` |
| 6 | `test_scan_root_inexistente_no_lanza` | idem con una ruta que no existe |
| 7 | `test_scan_yaml_corrupto_no_lanza` | Un archivo con `":\n  - [" ` inválido → se salta, `meta["skipped_unparseable"] == 1`, sin excepción |
| 8 | `test_scan_respeta_max_scan_files` | Con `_MAX_SCAN_FILES` monkeypatcheado a 3 → `meta["truncated"] is True` y `meta["scanned_files"] <= 3` |
| 9 | `test_scan_salta_archivo_gigante_sin_parsear` | Archivo de `_MAX_YAML_BYTES + 1` bytes → `meta["skipped_too_big"] == 1` y no aparece en el resultado |
| 10 | `test_scan_es_determinista` | Dos corridas sobre el mismo tmp devuelven listas **idénticas** (`json.dumps(sort_keys=True)`) |
| 11 | `test_classify_r1_gitlab_por_nombre` | `.gitlab-ci.yml` con doc `{}` → `"gitlab"` (R1 gana antes que R2) |
| 12 | `test_classify_r2_doc_no_dict` | `classify_pipeline_doc("x.yml", ["a"]) is None` y `(..., None) is None` |
| 13 | `test_classify_r3_stages_lista_de_strings` | `{"stages": ["build","test"]}` → `"gitlab"` |
| 14 | `test_classify_r4_stages_lista_de_dicts` | `{"stages": [{"stage": "Build"}]}` → `"azure_devops"` |
| 15 | `test_classify_r5_pool_steps_jobs` | `{"pool": {...}}`, `{"steps": []}`, `{"jobs": []}` → los 3 `"azure_devops"` |
| 16 | `test_classify_r6_trigger_top_level_es_ado` | `{"trigger": "none"}`, `{"trigger": ["main"]}`, `{"trigger": {"branches": {...}}}` → los 3 `"azure_devops"` |
| 17 | `test_classify_r7_workflow_include` | `{"workflow": {...}}` y `{"include": [...]}` → `"gitlab"` |
| 18 | `test_classify_r8_job_con_script` | `{"build": {"script": ["make"]}}` → `"gitlab"` |
| 19 | `test_classify_r9_ninguna_regla` | `{"foo": "bar"}` → `None` |
| 20 | `test_trigger_ado_ausente_es_default` | `extract_trigger({}, "azure_devops")["kind"] == "default"` |
| 21 | `test_trigger_ado_none` | `{"trigger": "none"}` → `kind == "none"` |
| 22 | `test_trigger_ado_lista_de_ramas` | `{"trigger": ["main","dev"]}` → `kind=="ci"`, `branches==["main","dev"]` |
| 23 | `test_trigger_ado_dict_con_include_y_paths` | `{"trigger": {"branches": {"include": ["main"]}, "paths": {"include": ["src"]}}}` → `branches==["main"]`, `has_paths is True` |
| 24 | `test_trigger_ado_schedules_y_pr` | `{"schedules": [...], "pr": "none"}` → `has_schedule is True`, `has_pr is False`; con `{"pr": {"branches": {...}}}` → `has_pr is True` |
| 25 | `test_trigger_gitlab_merge_request_event` | `{"workflow": {"rules": [{"if": "$CI_PIPELINE_SOURCE == \\"merge_request_event\\""}]}}` → `has_pr is True` |
| 26 | `test_trigger_gitlab_declara_sus_limitaciones` | Para gitlab, `branches == []` y `has_schedule is False` **siempre**, incluso con un YAML que tenga `only:` (documenta que no se adivina) |
| 27 | `test_trigger_shape_siempre_completo` | Las 6 claves presentes en todos los casos anteriores |
| 28 | `test_extract_trigger_no_devuelve_texto_crudo` | El dict devuelto no contiene ningún valor que sea el contenido del archivo (seguridad §3.2) |

**Comando exacto:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan246_repo_scan.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```
> Registrar `tests/test_plan246_repo_scan.py` en las **dos** listas del ratchet.

**Criterio de aceptación BINARIO:** `pytest tests/test_plan246_repo_scan.py -q` → **28 passed,
0 failed**; y `pytest tests/test_plan73_round_trip.py -q` sigue en verde (no regresión del motor de
pipelines, que este plan no toca).

**Flag:** `STACKY_PIPELINE_INVENTORY_ENABLED` (default ON) — inerte hasta F4.

**Impacto por runtime:** ninguno; no hay LLM. La única diferencia entre entornos es el **separador
de rutas de Windows**, que `normalize_yaml_path` resuelve (test #2 de F0). **Fallback por runtime:
no aplica.**

`Trabajo del operador: ninguno`

---

### F2 — Fuente A: definiciones de Azure DevOps + última corrida en una sola llamada

**Objetivo (1 frase):** listar las definiciones registradas en ADO y su última corrida
respetando un presupuesto de red duro y verificable.

**Valor que entrega:** la mitad del inventario que hoy sólo se ve abriendo el portal de ADO.

**Archivos a EDITAR:**
- `Stacky Agents/backend/services/ado_pipeline_definitions.py` (agrega **una** función read-only)
- `Stacky Agents/backend/services/ado_ci_provider.py` (agrega **un** método opcional, §3.4)

**Archivos a CREAR:**
- `Stacky Agents/backend/tests/test_plan246_inventory_sources.py`

**Símbolos EXACTOS:**

En `services/ado_pipeline_definitions.py` (**no tocar nada de lo existente**; agregar al final):

```python
def list_definitions(project: str | None, *, hydrate_missing: int = 10) -> tuple[list[dict], dict]:
    """Plan 246 F2 — LISTA las definitions de ADO. SOLO LECTURA. Nunca lanza.

    Por que NO se reusa find_yaml_definition (ado_pipeline_definitions.py:82):
    esa funcion hidrata SIN TOPE (`:99-110`) — con 50 definitions sin `process` son
    51 llamadas de red para resolver UNA pipeline. Aca la hidratacion tiene tope duro.

    Algoritmo:
      1. UNA llamada: GET {client._base_proj}/_apis/build/definitions?api-version=7.1
         via AdoClient._request  (ado_client.py:269; timeout _TIMEOUT_SEC=30, :38)
      2. definitions = (body.get("value") or [])[:_MAX_DEFINITIONS]     (:5, cap reusado)
      3. Para cada definition:
           yaml_path = (definition.get("process") or {}).get("yamlFilename")
           Si yaml_path is None y quedan cupos de hydrate_missing:
               GET .../definitions/{id}?api-version=7.1   (mismo patron que `:102-110`)
               hydrated += 1
           Si yaml_path is None y NO quedan cupos:
               yaml_path queda None, meta["truncated_hydration"] = True
      4. Salida por definition:
           {"definition_id": str(d.get("id")), "name": d.get("name") or "",
            "yaml_path": yaml_path,
            "default_branch": _strip_refs_heads(d.get("repository", {}).get("defaultBranch")),
            "queue_status": d.get("queueStatus") or ""}
      5. Excepcion en CUALQUIER punto -> ([], meta con available=False y reason=str(exc)[:200])

    meta = {"available": bool, "reason": str, "calls": int, "hydrated": int,
            "truncated_hydration": bool, "capped": bool}

    `calls` es el CONTADOR REAL de llamadas hechas: es lo que asierta el test del cap.
    """


def _strip_refs_heads(ref: str | None) -> str:
    """'refs/heads/main' -> 'main'. None/'' -> ''. Misma regla que _default_branch (`:76-79`)."""
```

En `services/ado_ci_provider.py`, **método nuevo en `AdoCIProvider`** (junto a
`last_pipeline_for_ref`, `:107`, que es el precedente de capacidad opcional fuera del Protocol):

```python
    def list_pipeline_definitions(self) -> tuple[list[dict], dict]:
        """Plan 246 F2 — inventario de definiciones ADO + ultima corrida por definicion.

        METODO OPCIONAL: NO esta en el Protocol CIProvider (ci_provider.py:83-95) ni en
        CI_PORT_METHODS (`:100`, contrato CONGELADO). Mismo patron que
        last_pipeline_for_ref (`:107`). Se consume duck-typed con getattr.

        1. defs, meta = list_definitions(self._project)          -> 1 llamada (+<=10 hidratacion)
        2. Si no defs: devolver ([], meta)
        3. UNA sola llamada batch de builds:
             GET {base}/_apis/build/builds?definitions={ids_csv}&$top={_MAX_BUILDS_SCAN}
                 &queryOrder=queueTimeDescending&api-version=7.1
           - ids_csv = ",".join(d["definition_id"] for d in defs)
           - agrupar el resultado por build["definition"]["id"] y quedarse con el PRIMERO
             de cada grupo (la respuesta ya viene ordenada por queueTimeDescending)
        4. Mapear cada build con _map_status (ado_ci_provider.py:135, REUSO) y despues con
           RUN_STATUS_FROM_PROVIDER (tabla de abajo).
        5. Si el paso 3 lanza o devuelve algo sin "value": TODAS las entradas quedan
           last_run.status="unknown", status_detail="batch_no_soportado".
           PROHIBIDO caer a un bucle de una llamada por definicion (§2.4-1).
        """
```

En `services/pipeline_inventory.py`, la tabla de traducción (cerrada, 8 filas):

```python
# _map_status (ado_ci_provider.py:135) devuelve el vocabulario GitLab.
# Esta tabla lo lleva al vocabulario de 4 valores del inventario, sin perder el detalle.
RUN_STATUS_FROM_PROVIDER: dict[str, tuple[str, str]] = {
    "success":  ("success", "success"),
    "failed":   ("failed",  "failed"),
    "canceled": ("unknown", "canceled"),   # cancelada no es roja: no dice nada de la salud
    "running":  ("unknown", "running"),
    "pending":  ("unknown", "pending"),
    "created":  ("unknown", "created"),
    "skipped":  ("unknown", "skipped"),
    "manual":   ("unknown", "manual"),
}
# Sin corridas             -> ("never_ran", "sin_corridas")
# Fuente caida / sin datos -> ("unknown",   "sin_datos")
```

**Tests PRIMERO — `backend/tests/test_plan246_inventory_sources.py` (parte ADO):**

Todos con un **`FakeAdoClient`** que registra cada URL pedida en `self.calls` y devuelve payloads
fijos. Se inyecta con `monkeypatch.setattr("services.ado_client.AdoClient", FakeAdoClient)`.

| # | Test | Verifica |
|---|---|---|
| 1 | `test_list_definitions_una_sola_llamada_cuando_hay_process` | 5 definitions **con** `process` → `meta["calls"] == 1`, `meta["hydrated"] == 0` |
| 2 | `test_list_definitions_hidrata_como_mucho_diez` | 25 definitions **sin** `process` → `meta["calls"] == 11`, `meta["hydrated"] == 10`, `meta["truncated_hydration"] is True` |
| 3 | `test_list_definitions_respeta_max_definitions` | 80 definitions → devuelve **50**, `meta["capped"] is True` |
| 4 | `test_list_definitions_strip_refs_heads` | `defaultBranch: "refs/heads/main"` → `default_branch == "main"` |
| 5 | `test_list_definitions_excepcion_no_lanza` | El fake tira `RuntimeError` → `([], meta)` con `available is False` y `reason` no vacío |
| 6 | `test_list_definitions_body_vacio` | `{"value": []}` → `([], meta)` con `available is True` y `calls == 1` |
| 7 | `test_provider_lista_y_ultima_corrida_en_tres_llamadas` | 5 definitions con `process` + builds batch → **`len(fake.calls) == 2`** (definiciones + builds). Sumado a GitLab (F3) el total del refresco es 3 |
| 8 | `test_provider_agrupa_builds_por_definicion` | 3 builds de la definición 7 y 1 de la 9 → cada definición recibe **su** build más reciente |
| 9 | `test_provider_mapea_status_con_map_status` | `{"status":"completed","result":"succeeded"}` → `("success","success")`; `{"completed","failed"}` → `("failed","failed")`; `{"completed","canceled"}` → `("unknown","canceled")`; `{"inProgress"}` → `("unknown","running")` |
| 10 | `test_provider_definicion_sin_builds_es_never_ran` | Definición sin builds → `status == "never_ran"`, `status_detail == "sin_corridas"` |
| 11 | `test_provider_batch_caido_no_hace_n_llamadas` | El fake tira en la URL de builds → **`len(fake.calls) == 2`** (nunca N), y todas las entradas quedan `("unknown","batch_no_soportado")` |
| 12 | `test_provider_nunca_lanza` | El fake tira en las **dos** URLs → devuelve `([], meta)` con `available is False`, sin excepción |
| 13 | `test_ci_port_methods_sigue_congelado` | `ci_provider.CI_PORT_METHODS == ("infer_item_pipeline","monitor_pipeline","trigger_pipeline")` — **centinela de que F2 no rompió el contrato del Plan 71/72** |

**Comando exacto:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan246_inventory_sources.py -q
```

**Criterio de aceptación BINARIO:**
1. `pytest tests/test_plan246_inventory_sources.py -q` → todos verdes.
2. **El test #7 y el #11 asertan un número exacto de llamadas.** Si el conteo sube, falla. Ese es
   el cap de red de §3.3, verificado, no prometido.
3. `pytest tests/test_plan95_*.py -q` (los tests existentes de `ado_pipeline_definitions` /
   `AdoCIProvider`, si existen con ese prefijo; si no existen, se omite este punto y se declara)
   sigue verde ⇒ **F2 no regresiona `find_yaml_definition` ni `ensure_yaml_definition`**.

**Flag:** `STACKY_PIPELINE_INVENTORY_ENABLED` (default ON) — inerte hasta F4.

**Impacto por runtime:** ninguno; sin LLM. **Fallback por runtime: no aplica.** El único fallback
real es de **proveedor**, no de runtime: sin PAT de ADO la fuente devuelve `available:false`
(test #12) y el inventario sigue mostrando lo que sí encontró.

`Trabajo del operador: ninguno`

---

### F3 — Fuente B: GitLab + ensamblado de las 3 fuentes con degradación honesta

**Objetivo (1 frase):** agregar la fuente GitLab con el mismo método opcional, y escribir la
función que arma el inventario completo sin dejar escapar jamás una excepción.

**Valor que entrega:** paridad multiproveedor real y la garantía de que una integración no
configurada nunca produce una pantalla rota.

**Archivos a EDITAR:**
- `Stacky Agents/backend/services/gitlab_ci_provider.py` (agrega **un** método opcional)
- `Stacky Agents/backend/services/pipeline_inventory.py` (agrega `build_inventory` y el cache)
- `Stacky Agents/backend/tests/test_plan246_inventory_sources.py` (agrega la parte GitLab)

**Símbolos EXACTOS:**

En `services/gitlab_ci_provider.py`, método nuevo en `GitLabCIProvider` (junto a
`last_pipeline_for_ref`, `:70`):

```python
    def list_pipeline_definitions(self) -> tuple[list[dict], dict]:
        """Plan 246 F3 — inventario GitLab. Metodo OPCIONAL (mismo criterio que F2).

        DIFERENCIA CONCEPTUAL con ADO, importante: GitLab NO tiene "definitions".
        Un proyecto GitLab tiene UN archivo de CI (por default `.gitlab-ci.yml`, o el
        `ci_config_path` del proyecto) y muchas CORRIDAS. Por eso esta fuente devuelve
        COMO MUCHO UNA entrada por proyecto.

        1. Resolver la ruta del YAML:
             body, _headers = self._delegate._client._request(
                 "GET", f"/projects/{self._delegate._client._project_path()}")
             (gitlab_client.py:107 devuelve tuple[object, dict] = (body, headers) y
              LANZA TrackerApiError ante no-2xx — `:116,120-125`)
             yaml_path = (body or {}).get("ci_config_path") or ".gitlab-ci.yml"
             yaml_path_source = "proyecto" si vino la key, "convencion" si no
           Si esa llamada LANZA: yaml_path = ".gitlab-ci.yml",
                                 yaml_path_source = "convencion"  (§2.4-2, plan B)
           -> NO se propaga la excepcion.
        2. runs = self._delegate.fetch_pipelines()      (gitlab_provider.py:487;
           ya devuelve [] ante cualquier error, `:510-511`)
        3. last = runs[0] if runs else None   (la API de GitLab devuelve mas nuevo primero)
        4. Entrada unica:
             {"definition_id": "", "name": pipeline_name_from_path(yaml_path),
              "yaml_path": yaml_path, "default_branch": (last or {}).get("ref", ""),
              "queue_status": "", "yaml_path_source": yaml_path_source,
              "last_run": mapear(last)}
           mapear: status via RUN_STATUS_FROM_PROVIDER (el vocabulario de GitLab YA es
           el de la tabla); at = last.get("updated_at") or last.get("created_at");
           web_url = last.get("web_url"); run_id = last.get("id"); source = "provider".
           Sin runs -> ("never_ran", "sin_corridas").
        5. Cualquier excepcion no prevista -> ([], meta con available=False).

        Llamadas de red: 2 como maximo (proyecto + pipelines). En el peor caso la
        primera falla y quedan 1.
        """
```

En `services/pipeline_inventory.py`:

```python
_CACHE: dict[str, tuple[float, dict]] = {}   # {project_key: (expires_at_monotonic, payload)}


def build_inventory(project: str | None = None, *, refresh: bool = False) -> dict:
    """Arma el inventario COMPLETO. NUNCA LANZA. Devuelve siempre un dict valido.

    1. cache_key = project or ""
       Si not refresh y hay entrada viva (time.monotonic() < expires_at):
           devolver {**payload, "cached": True, "cache_age_sec": int(...)}
    2. Fuente proveedor (A o B, la que corresponda al tracker activo):
         try:  provider = get_ci_provider(project)      (ci_provider.py:107)
         except Exception as exc:
               src_prov = source_unavailable(
                   source_id=<segun tracker>, capability="list_pipeline_definitions",
                   provider="desconocido", reason=str(exc)[:200],
                   workaround="Configura el tracker del proyecto en Configuracion -> Proyectos.")
               registered = []
         Si hay provider:
             lister = getattr(provider, "list_pipeline_definitions", None)   (§3.4)
             if not callable(lister): -> source_unavailable(...) y registered = []
             else: registered, meta = lister();  src_prov = source_ok/unavailable segun meta
       OJO: get_ci_provider LANZA TrackerConfigError si el tracker es gitlab y
       STACKY_GITLAB_ENABLED esta en false (ci_provider.py:121-124). Ese es el caso
       NORMAL de un operador solo-ADO: tiene que degradar, no romper.
    3. Fuente C: files, meta_scan = scan_repo_pipelines(str(_active_workspace_root() or ""))
       (runtime_paths.py:66). Envuelto en try/except igual que todo lo demas.
    4. entries = reconcile(registered, files)      (F0, puro)
    5. payload = {"ok": True, "generated_at": <ISO-8601 UTC>, "cached": False,
                  "cache_age_sec": 0, "project": project or "",
                  "counts": counts(entries), "sources": [src_prov, src_scan],
                  "pipelines": entries}
    6. _CACHE[cache_key] = (time.monotonic() + _CACHE_TTL_SEC, payload)
    7. return payload

    INVARIANTE (test dedicado): esta funcion no puede lanzar. Si algo imprevisto pasa,
    devuelve el payload con listas vacias y una fuente en available=False.
    """


def clear_cache() -> None:
    """Vacia _CACHE. Existe para los tests y para el ?refresh=1 del endpoint."""
```

**Tests PRIMERO — `backend/tests/test_plan246_inventory_sources.py` (parte GitLab + ensamblado):**

| # | Test | Verifica |
|---|---|---|
| 14 | `test_gitlab_usa_ci_config_path_cuando_viene` | Fake `_request` devuelve `({"ci_config_path": "ci/gl.yml"}, {})` → `yaml_path == "ci/gl.yml"`, `yaml_path_source == "proyecto"` |
| 15 | `test_gitlab_cae_a_convencion_si_falta_la_key` | Fake devuelve `({}, {})` → `yaml_path == ".gitlab-ci.yml"`, `yaml_path_source == "convencion"` |
| 16 | `test_gitlab_cae_a_convencion_si_la_llamada_lanza` | Fake `_request` tira `TrackerApiError` → misma salida que #15, **sin excepción** |
| 17 | `test_gitlab_sin_corridas_es_never_ran` | `fetch_pipelines` → `[]` → `status == "never_ran"` |
| 18 | `test_gitlab_toma_la_corrida_mas_reciente` | 3 pipelines → usa el primero de la lista, con su `web_url` y su `updated_at` |
| 19 | `test_gitlab_como_mucho_dos_llamadas` | Contador del fake ≤ 2 |
| 20 | `test_build_inventory_sin_proveedor_no_lanza` | `get_ci_provider` monkeypatcheado para tirar `TrackerConfigError` → payload con `ok is True`, `sources[0]["available"] is False`, y `pipelines` con las huérfanas del scan |
| 21 | `test_build_inventory_sin_metodo_opcional_degrada` | Provider falso **sin** `list_pipeline_definitions` → `sources[0]["available"] is False`, `capability == "list_pipeline_definitions"` (§3.4) |
| 22 | `test_build_inventory_sin_workspace_degrada` | `_active_workspace_root` → `None` → `sources[1]["available"] is False`, sin excepción |
| 23 | `test_build_inventory_las_dos_fuentes_caidas_sigue_200` | Ambas caídas → `ok is True`, `pipelines == []`, `counts["total"] == 0`, las 2 fuentes con `available is False` |
| 24 | `test_build_inventory_nunca_lanza` | Parametrizado: se hace tirar a cada dependencia por turno (5 casos) y **ninguno** propaga excepción |
| 25 | `test_build_inventory_cachea_y_refresh_saltea` | 2 llamadas seguidas → la 2ª tiene `cached is True` y **0** llamadas nuevas al fake; con `refresh=True` → `cached is False` y sí llama |
| 26 | `test_build_inventory_payload_tiene_las_ocho_claves` | `ok, generated_at, cached, cache_age_sec, project, counts, sources, pipelines` |
| 27 | `test_build_inventory_es_determinista` | Mismas fuentes → mismo `json.dumps(payload["pipelines"], sort_keys=True)` |

**Comando exacto:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan246_inventory_sources.py -q
```

**Criterio de aceptación BINARIO:** los **27** tests del archivo pasan (13 de F2 + 14 de F3), y el
test #24 cubre las 5 dependencias que pueden fallar. Además `pytest tests/test_plan218_capability_unavailable.py -q`
sigue verde (no se rompió el contrato de degradación del Plan 218).

**Flag:** `STACKY_PIPELINE_INVENTORY_ENABLED` (default ON) — inerte hasta F4.

**Impacto por runtime:** ninguno; sin LLM. **Fallback por runtime: no aplica.** Los fallbacks de
esta fase son de **integración** (sin PAT, sin GitLab, sin workspace) y están cubiertos por los
tests #20 a #24.

`Trabajo del operador: ninguno`

---

### F4 — Endpoint, flag (5 patas) y health key

**Objetivo (1 frase):** exponer el inventario en `GET /api/pipeline-inventory/list`, siempre 200,
protegido por una flag default ON y visible en el health del panel.

**Valor que entrega:** el backend queda consumible por el panel y por los planes 247–252.

**Archivos a CREAR:**
- `Stacky Agents/backend/api/pipeline_inventory.py`
- `Stacky Agents/backend/tests/test_plan246_inventory_endpoint.py`

**Archivos a EDITAR (5 patas de la flag + 2 de wiring):**

| # | Archivo | Cambio exacto |
|---|---|---|
| 1 | `backend/services/harness_flags.py` | 1 `FlagSpec` nuevo (bloque de abajo) |
| 2 | `backend/services/harness_flags.py:241` | Agregar `"STACKY_PIPELINE_INVENTORY_ENABLED",  # Plan 246 — inventario vivo de pipelines` **al final de la tupla `devops` de `_CATEGORY_KEYS`** (`:120`) |
| 3 | `backend/config.py` | Atributo nuevo, patrón de `:1337-1339` |
| 4 | `backend/tests/test_harness_flags.py:467` | Agregar la clave a `_CURATED_DEFAULTS_ON` |
| 5 | `backend/api/devops.py:85` | Agregar la key `pipeline_inventory_enabled` al final de `_health_payload()` |
| 6 | `backend/api/__init__.py:44` y `:117` | Import + `api_bp.register_blueprint(pipeline_inventory_bp)` |
| 7 | `backend/scripts/run_harness_tests.sh:20` **y** `.ps1:13` | 3 líneas: los 3 tests nuevos de F0/F1/F2-F3 + el de F4 |

**FlagSpec exacto** (patrón de `harness_flags.py:2023-2035`):

```python
    # ── Plan 246 — Inventario vivo de pipelines ─────────────────────────────────
    FlagSpec(
        key="STACKY_PIPELINE_INVENTORY_ENABLED",
        type="bool",
        default=True,  # default ON: NINGUNA de las 4 excepciones duras aplica (read-only,
                       # no destructivo, sin prerequisito extra, no reduce seguridad).
                       # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        label="Inventario de pipelines",
        description=(
            "Plan 246 - Lista TODAS las pipelines del proyecto: las registradas en Azure "
            "DevOps, las de GitLab y los YAML que existen en el repo sin estar registrados "
            "(huerfanas). Solo lectura: no crea, no edita y no dispara nada. Si falta el PAT "
            "o el proveedor no responde, muestra lo que si pudo descubrir. "
            "OFF: desaparece la seccion Inventario del panel DevOps y el endpoint responde "
            "404; todo lo demas queda identico."
        ),
        group="global",
    ),
```

**`config.py`** (patrón de `:1337-1339`):
```python
    # ── Plan 246 — Inventario vivo de pipelines (read-only, default ON) ──
    STACKY_PIPELINE_INVENTORY_ENABLED: bool = os.getenv(
        "STACKY_PIPELINE_INVENTORY_ENABLED", "true"
    ).strip().lower() == "true"
```

**`api/devops.py`** — al final del dict de `_health_payload()` (después de `:84`):
```python
        "pipeline_inventory_enabled": bool(
            getattr(cfg, "STACKY_PIPELINE_INVENTORY_ENABLED", False)
        ),  # Plan 246 — Inventario de pipelines
```
> **Gratis:** `/bootstrap` reusa el mismo payload (`api/devops.py:102`), así que
> `test_bootstrap_health_matches_health_endpoint` sigue en paridad sin tocar nada más.

**Blueprint nuevo — `backend/api/pipeline_inventory.py`** (copia literal del patrón de
`api/pipeline_generator.py:1-26,37`):

```python
"""api/pipeline_inventory.py — Blueprint del inventario vivo de pipelines. Plan 246 F4.

url_prefix="/pipeline-inventory" -> ruta final /api/pipeline-inventory/...
NO poner url_prefix="/api/..." (daria /api/api/...) y NO registrar en app.py:
se registra sobre api_bp en api/__init__.py.
Guard de la flag PER-REQUEST (abort(404)), nunca gateado en el registro.

READ-ONLY: este blueprint no define ningun POST/PUT/PATCH/DELETE. A proposito.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, abort, jsonify, request

from services.pipeline_inventory import build_inventory

bp = Blueprint("pipeline_inventory", __name__, url_prefix="/pipeline-inventory")


@bp.get("/list")
def list_inventory_route():
    """Inventario completo. SIEMPRE 200 con la flag ON (nunca 500).

    Query params:
      project  (opcional) nombre del proyecto; None => proyecto activo
      refresh  "1"/"true" => saltea el cache TTL (accion explicita del operador)
    """
    # GOTCHA: leer la INSTANCIA (_config.config), no el modulo. getattr del modulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_INVENTORY_ENABLED", False):
        abort(404)
    project = request.args.get("project") or None
    refresh = (request.args.get("refresh") or "").strip().lower() in ("1", "true", "yes")
    return jsonify(build_inventory(project, refresh=refresh))
```

**Tests PRIMERO — `backend/tests/test_plan246_inventory_endpoint.py`:**

| # | Test | Verifica |
|---|---|---|
| 1 | `test_flag_off_da_404` | `monkeypatch.setattr(config_module.config, "STACKY_PIPELINE_INVENTORY_ENABLED", False)` → `GET /api/pipeline-inventory/list` → **404** |
| 2 | `test_flag_on_da_200_con_el_shape` | Flag ON → 200 y las 8 claves del payload |
| 3 | `test_endpoint_siempre_200_aunque_todo_falle` | `build_inventory` monkeypatcheado para devolver el payload degradado → **200**, nunca 500 |
| 4 | `test_endpoint_pasa_refresh` | `?refresh=1` → `build_inventory` recibe `refresh=True`; sin el param → `refresh=False` |
| 5 | `test_endpoint_pasa_project` | `?project=RSPACIFICO` → `build_inventory` recibe `"RSPACIFICO"`; sin el param → `None` |
| 6 | `test_endpoint_no_expone_verbos_de_escritura` | `POST`, `PUT`, `PATCH`, `DELETE` sobre `/api/pipeline-inventory/list` → **405** (read-only estructural) |
| 7 | `test_health_expone_pipeline_inventory_enabled` | `GET /api/devops/health` → 200 y `"pipeline_inventory_enabled" in body` con `isinstance(..., bool)` |
| 8 | `test_health_refleja_la_flag_off` | Con la flag en False → `body["pipeline_inventory_enabled"] is False` |
| 9 | `test_bootstrap_y_health_siguen_en_paridad` | La key aparece igual en `/api/devops/bootstrap` (reusa `_health_payload`, `api/devops.py:102`) |
| 10 | `test_endpoint_no_lee_current_user` | El módulo `api/pipeline_inventory.py` **no** importa `current_user` (mono-operador sin auth, §3.2) |

**Comandos exactos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan246_inventory_endpoint.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

**Criterio de aceptación BINARIO:**
1. Los 10 tests del archivo pasan.
2. `pytest tests/test_harness_flags.py -q` **no suma fallos nuevos**.
   > **Rojo preexistente ajeno declarado:** `test_harness_flags_help` tiene **4 fallos ajenos** que
   > **no son de este plan**. Validá TU entrada de forma aislada con
   > `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q -k "curated or category"`.
   > Prohibido "arreglar" los 4 ajenos dentro de este plan.
3. `pytest tests/test_harness_ratchet_meta.py -q` verde (los 4 tests nuevos registrados en el `.sh`).
4. `python -m compileall -q services api` sin errores.

**Flag:** `STACKY_PIPELINE_INVENTORY_ENABLED`, **default ON**. Excepción dura aplicable: **ninguna**
(justificación completa en §3.2). Configurable desde **Configuración → Arnés, categoría DevOps**,
sin tocar archivos.

**Impacto por runtime:** ninguno; el endpoint no invoca LLM. **Fallback por runtime: no aplica.**

`Trabajo del operador: ninguno` (la flag viene ON; si la quiere apagar, un clic en la UI del arnés)

---

### F5 — Sección "Inventario" en el panel DevOps

**Objetivo (1 frase):** montar la lista en el cockpit DevOps, grupo *Construir*, con estados vacíos
y de error honestos y sin ningún sondeo automático.

**Valor que entrega:** el operador ve sus pipelines sin salir de Stacky. Es el KPI-1.

**Archivos a CREAR:**
- `Stacky Agents/frontend/src/devops/pipelineInventoryModel.ts` (**modelo PURO**, toda la lógica)
- `Stacky Agents/frontend/src/devops/__tests__/pipelineInventoryModel.test.ts`
- `Stacky Agents/frontend/src/components/devops/PipelineInventorySection.tsx`

**Archivos a EDITAR:**
- `Stacky Agents/frontend/src/api/endpoints.ts` (1 namespace nuevo al final, patrón de `:4426`)
- `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` (1 key en `DevOpsHealth` `:32`, 1 import,
  1 entrada en `DEVOPS_SECTIONS` `:113`)

**Símbolos EXACTOS — `frontend/src/devops/pipelineInventoryModel.ts` (PURO, sin React, sin DOM):**

```typescript
/** Plan 246 F5 — modelo puro del inventario de pipelines. Sin DOM, sin React, sin fetch.
 *  Los tipos son el ESPEJO del contrato congelado de services/pipeline_inventory.py (F0). */

export type InventoryCategory =
  | 'registrada+en_repo'
  | 'registrada_sin_archivo'
  | 'en_repo_sin_registrar';

export type RunStatus = 'success' | 'failed' | 'never_ran' | 'unknown';

export interface InventoryLastRun {
  status: RunStatus; status_detail: string; at: string | null;
  web_url: string | null; run_id: string | null; source: string | null;
}
export interface InventoryTrigger {
  kind: string; branches: string[]; has_paths: boolean;
  has_schedule: boolean; has_pr: boolean; source: string | null;
}
export interface InventoryEntry {
  key: string; provider: string; name: string; yaml_path: string | null;
  default_branch: string | null; definition_id: string | null;
  category: InventoryCategory; category_reason: string;
  last_run: InventoryLastRun; trigger: InventoryTrigger; found_in: string[];
}
export interface InventorySource {
  id: string; available: boolean; count: number;
  capability: string; provider: string; reason: string; workaround: string;
}
export interface InventoryPayload {
  ok: boolean; generated_at: string; cached: boolean; cache_age_sec: number;
  project: string; counts: Record<string, number>;
  sources: InventorySource[]; pipelines: InventoryEntry[];
}

/** Etiqueta en castellano + tono para la UI. Tabla CERRADA, sin default silencioso. */
export function statusLabel(r: InventoryLastRun): { text: string; tone: 'ok' | 'bad' | 'faint' | 'warn' };
//  success   -> {'Verde',          'ok'}
//  failed    -> {'Rojo',           'bad'}
//  never_ran -> {'Nunca corrio',   'faint'}
//  unknown   -> {'Desconocido',    'warn'}   + status_detail entre parentesis si != 'sin_datos'

/** Etiqueta + explicacion de cada categoria. Tabla CERRADA. */
export function categoryLabel(c: InventoryCategory): { text: string; hint: string; tone: 'ok' | 'bad' | 'warn' };
//  'registrada+en_repo'      -> {'Registrada',        'Registrada en el proveedor y con su YAML en el repo.', 'ok'}
//  'registrada_sin_archivo'  -> {'Sin archivo',       'Registrada en el proveedor pero su YAML no esta en el repo.', 'bad'}
//  'en_repo_sin_registrar'   -> {'Huerfana',          'El YAML esta en el repo pero no esta registrada en ningun proveedor.', 'warn'}

/** Texto del trigger en una linea, deterministico. Nunca inventa: 'unknown' -> 'Sin datos'. */
export function triggerLabel(t: InventoryTrigger): string;
//  kind 'default' -> 'Toda rama (sin bloque trigger)'
//  kind 'none'    -> 'Manual (trigger: none)'
//  kind 'ci'      -> 'CI: ' + (branches.length ? branches.join(', ') : 'sin ramas declaradas')
//                    + (has_paths ? ' [filtra paths]' : '')
//  kind 'unknown' -> 'Sin datos'
//  sufijos: has_schedule ? ' + programado' : '' ; has_pr ? ' + PR' : ''

/** Agrupa por categoria conservando el orden del backend dentro de cada grupo. */
export function groupByCategory(entries: InventoryEntry[]): Record<InventoryCategory, InventoryEntry[]>;

/** Filtro de texto: match case-insensitive sobre name, yaml_path y provider. '' => todo. */
export function filterEntries(entries: InventoryEntry[], q: string): InventoryEntry[];

/** Linea de resumen del header. Ej: '12 pipelines - 2 sin archivo - 3 huerfanas'.
 *  Con 0 pipelines devuelve 'Sin pipelines descubiertas'. Nunca devuelve ''. */
export function summarize(p: InventoryPayload | null): string;

/** Fuentes caidas, para el banner honesto. [] si todas estan bien. */
export function unavailableSources(p: InventoryPayload | null): InventorySource[];

/** Mensaje del estado vacio, DISCRIMINANDO la causa (no un 'no hay nada' mudo):
 *  - payload null                          -> 'Todavia no se consulto el inventario.'
 *  - todas las fuentes caidas              -> 'No se pudo consultar ninguna fuente. Mira el detalle de abajo.'
 *  - fuentes ok y 0 pipelines              -> 'No hay pipelines en este proyecto (ni registradas ni en el repo).'
 *  - hay pipelines pero el filtro no matchea -> 'Ninguna pipeline coincide con el filtro.' */
export function emptyStateMessage(p: InventoryPayload | null, filtered: number): string;
```

**`endpoints.ts`** — namespace nuevo al final (patrón de `:4426-4435`):
```typescript
export const PipelineInventory = {
  /** GET /api/pipeline-inventory/list — inventario multiproveedor. SIEMPRE 200 con la flag ON. */
  list: (project?: string | null, refresh = false) =>
    api.get<InventoryPayload>(
      `/api/pipeline-inventory/list?${new URLSearchParams({
        ...(project ? { project } : {}),
        ...(refresh ? { refresh: '1' } : {}),
      }).toString()}`,
    ),
};
```
> **GOTCHA de la casa:** `api.get`/`api.post` **lanzan** ante non-2xx. Acá está bien: con la flag
> ON el endpoint responde 200 siempre (F4, criterio #3), y con la flag OFF la sección ni se
> renderiza porque el `healthKey` la gatea. **No hace falta `rawGet`.**

**`DevOpsPage.tsx`** — 3 ediciones puntuales:
```typescript
// (1) en DevOpsHealth (:32-55), junto a build_workshop_enabled:
  pipeline_inventory_enabled?: boolean; // Plan 246 — Inventario de pipelines

// (2) import, junto a los de :106-109:
import { PipelineInventorySection } from '../components/devops/PipelineInventorySection';

// (3) entrada nueva al final de DEVOPS_SECTIONS (:113-227), modelada sobre :216-226:
  // Plan 246 — Inventario vivo de pipelines (read-only, multiproveedor)
  {
    id: 'inventario-pipelines',
    label: 'Inventario',
    group: 'construir',
    icon: '📋',
    summary: 'Todas las pipelines del proyecto: registradas, huerfanas y sin archivo.',
    healthKey: 'pipeline_inventory_enabled',
    gateFlagKey: 'STACKY_PIPELINE_INVENTORY_ENABLED',
    gateMessage: 'La seccion Inventario necesita la flag STACKY_PIPELINE_INVENTORY_ENABLED (Configuracion → Arnes, categoria DevOps).',
    render: (ctx) => <PipelineInventorySection ctx={ctx} />,
  },
```
> Contrato honrado: *"Sumar una sección DevOps futura = 1 entrada + 1 componente"*
> (`DevOpsPage.tsx:8`). El id `inventario-pipelines` no colisiona con ninguno de los 11 existentes
> (verificado contra `:117,127,133,142,152,163,174,185,196,207,218`).

**`PipelineInventorySection.tsx`** — reglas duras del componente:
- `useQuery({ queryKey: ['pipeline-inventory', project], queryFn: ..., retry: false })`.
- **`refetchInterval` PROHIBIDO.** El plan 239 F6 obliga a gatear cualquier sondeo con
  `ctx.visible` (`DevOpsPage.tsx:68-71`); este plan **no sondea en absoluto**, así que cumple por
  construcción. El único refetch es el botón **"Actualizar"** (`refresh=1`), acción explícita del
  operador.
- **Sin `style={{...}}` inline** (gotcha del `uiDebtRatchet`: un archivo `.tsx` nuevo arranca con
  alcance 0). Usar un `PipelineInventorySection.module.css` con `var(--token)`; **nada de literales
  HEX**.
- Tabla con 7 columnas: Estado · Nombre · Proveedor · Ruta del YAML · Rama · Última corrida ·
  Trigger. Toda la lógica de etiquetas viene del modelo puro; el `.tsx` sólo pinta.
- Banner honesto arriba con `unavailableSources(payload)`: por cada fuente caída, `reason` +
  `workaround` (mismos campos que el envelope del Plan 218).
- Estado vacío con `emptyStateMessage(...)` — **discrimina la causa**, no dice "no hay nada".

**Tests PRIMERO — `frontend/src/devops/__tests__/pipelineInventoryModel.test.ts`:**

| # | Test | Verifica |
|---|---|---|
| 1 | `statusLabel cubre los 4 estados` | `success/failed/never_ran/unknown` → los 4 textos y tonos de la tabla |
| 2 | `statusLabel muestra el detalle cuando aporta` | `{status:'unknown', status_detail:'running'}` → texto contiene `running`; con `'sin_datos'` **no** lo agrega |
| 3 | `categoryLabel cubre las 3 categorias` | Los 3 textos, hints y tonos |
| 4 | `triggerLabel default / none / ci` | Los 3 textos base |
| 5 | `triggerLabel con ramas y paths` | `{kind:'ci',branches:['main'],has_paths:true}` → contiene `main` y `[filtra paths]` |
| 6 | `triggerLabel con ci y sin ramas` | `{kind:'ci',branches:[]}` → `'CI: sin ramas declaradas'` (no rompe, no inventa) |
| 7 | `triggerLabel sufijos schedule y PR` | `has_schedule`/`has_pr` agregan sus sufijos, en ese orden |
| 8 | `triggerLabel unknown` | → `'Sin datos'` |
| 9 | `groupByCategory con las 3 categorias` | 3 claves, cada entrada en la suya, orden interno preservado |
| 10 | `groupByCategory con lista vacia` | Las 3 claves presentes con arrays vacíos |
| 11 | `filterEntries case-insensitive sobre 3 campos` | Match por `name`, por `yaml_path` y por `provider` |
| 12 | `filterEntries con query vacia devuelve todo` | Identidad |
| 13 | `summarize con datos` | `'12 pipelines · 2 sin archivo · 3 huerfanas'` (formato exacto) |
| 14 | `summarize con cero` | `'Sin pipelines descubiertas'` |
| 15 | `summarize con null` | No lanza y devuelve un string no vacío |
| 16 | `unavailableSources filtra las caidas` | 1 ok + 1 caída → devuelve sólo la caída |
| 17 | `unavailableSources con null` | `[]` |
| 18 | `emptyStateMessage discrimina las 4 causas` | Los 4 mensajes distintos de la tabla |

**Comandos exactos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineInventoryModel.test.ts
npx tsc --noEmit
```
> **No usar `npm test`**: el `package.json` del frontend **no tiene script `test`** (§7).
> **Correr el archivo solo**, nunca la suite completa (contaminación cross-file conocida).

**Criterio de aceptación BINARIO:**
1. `npx vitest run src/devops/__tests__/pipelineInventoryModel.test.ts` → **18 passed, 0 failed**.
2. `npx tsc --noEmit` → **0 errores**.
3. `grep -c "style={{" PipelineInventorySection.tsx` → **0**.
4. Smoke visual del operador: panel DevOps → *Construir* → **Inventario** muestra la lista, y con
   la flag OFF muestra el `FlagGateBanner` en vez de una pantalla en blanco.

> **Limitación declarada (§2.4-7):** el frontend no tiene jsdom ni `@testing-library/react`, así
> que **el `.tsx` no lleva test automatizado**. El gate real del componente es `tsc --noEmit` + el
> smoke visual. Este plan **no promete** un test de componente que no se puede escribir.

**Flag:** `STACKY_PIPELINE_INVENTORY_ENABLED` (default **ON**). Con la flag OFF, la sección se
atenúa y muestra el `FlagGateBanner` (mecánica declarativa existente, `DevOpsPage.tsx:462-476`).

**Impacto por runtime:** ninguno; el componente consume un endpoint determinista. **Fallback por
runtime: no aplica.**

`Trabajo del operador: ninguno` (con la flag ON de fábrica, la sección aparece sola)

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación (escrita en una fase concreta) |
|---|---|---|---|---|
| R1 | La API de builds de ADO **no** acepta `definitions=<csv>` (§2.4-1) y el inventario queda sin estado de corrida | Media | Medio | **F2 paso 5**: fallback a `("unknown","batch_no_soportado")` para todas las entradas. **Prohibido** el bucle de N llamadas. Test #11 lo asierta contando llamadas |
| R2 | La lista `/build/definitions` no trae `process` y todas las definiciones quedan sin `yaml_path` (§2.4-3) ⇒ ninguna reconcilia con el repo | Media | Alto | **F2**: hidratación acotada `_MAX_HYDRATE=10` + `truncated_hydration` en el meta, que la UI muestra honestamente. Tests #1, #2 |
| R3 | Un repo grande hace lento el barrido | Media | Medio | **F1**: `_MAX_SCAN_FILES=400`, `_MAX_SCAN_DEPTH=4`, `_MAX_YAML_BYTES=512_000`, ignore-list heredada de `pipeline_stack_detector.py:36-37`. Tests #8, #9 |
| R4 | Falsos positivos: se lista como pipeline un YAML que no lo es (un `docker-compose.yml`, un `appsettings.yml`) | Media | Bajo | **F1**: las 9 reglas cerradas de `classify_pipeline_doc`, con R9 → `None`. Tests #11–#19. Un falso positivo es visible y no rompe nada: aparece como huérfana |
| R5 | Falsos negativos: una pipeline real queda fuera del listado | Baja | Medio | La fuente del proveedor la trae igual (categoría `registrada_sin_archivo`). **Las dos fuentes se cubren mutuamente** — ese es el punto de reconciliar |
| R6 | Sin PAT / sin GitLab configurado ⇒ pantalla rota | **Alta** (es el caso normal) | Alto | **F3**: `build_inventory` nunca lanza; 200 con `available:false` por fuente. Tests #20–#24. Precedente Plan 148 / Plan 218 F6 |
| R7 | La normalización de rutas parte la identidad de `.gitlab-ci.yml` (trampa `lstrip("./")`) | **Alta** si nadie lo advierte | Alto | **F0**: la trampa está escrita en el docstring y tiene **test negativo dedicado** (#1) |
| R8 | El orden de `os.walk` no es estable ⇒ salida no determinista entre corridas | Media | Medio | **F1**: `dirnames.sort()` + `sorted(filenames)` + `sort_key` final en `reconcile`. Tests F0#12 y F1#10 |
| R9 | Alguien agrega el método al `Protocol` y rompe el centinela del Plan 71/72 | Media | Alto | **§3.4** + **test centinela F2 #13** que asierta `CI_PORT_METHODS` literal |
| R10 | El cache sirve un inventario viejo y el operador toma una decisión sobre datos rancios | Baja | Medio | TTL corto (300s), `cached`/`cache_age_sec` **en el payload y visibles en la UI**, y botón "Actualizar" con `refresh=1` |
| R11 | Alguien agrega un `refetchInterval` "para que se vea vivo" y el panel empieza a golpear ADO en loop | Media | Alto | **F5**: prohibición explícita escrita + el contrato `ctx.visible` del Plan 239 F6. Revisar en el code review de la fase |
| R12 | La flag `default=True` sin curar deja rojo `test_default_known_only_for_curated` | **Alta** si se olvida | Medio | **F4 pata #4** es explícita: agregar la clave a `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`) en el mismo commit |
| R13 | El test nuevo no se registra en el ratchet y `test_harness_ratchet_meta` queda rojo | **Alta** si se olvida | Bajo | **Cada fase** repite el comando del ratchet y F4 pata #7 nombra las **dos** listas (`.sh` y `.ps1`) |
| R14 | Merge con las otras 6 ramas de la serie pisa líneas en los 5 archivos universales | **Alta** | Alto | **§0.3** con el orden canónico y el gate post-merge (compileall + flags + ratchet + tsc) |

---

## 6. Fuera de scope (nombrando los planes de la serie)

Lo siguiente **NO** lo hace este plan. Está nombrado con su dueño para que nadie lo implemente acá:

- **Clasificar el stack tecnológico** (python/node/dotnet/otro) de una pipeline, su **anatomía**
  (qué pasos son build, cuáles test, cuáles deploy), sus **artefactos**, los **entornos que toca** y
  su **propósito en una línea** → **plan 247**. El 246 extrae **sólo** el bloque de trigger, y lo
  hace porque el trigger es un dato de identificación, no de interpretación.
- **Hallazgos de seguridad** (`SEC001..SECnn`: secretos en claro, imagen sin pin, `allow_failure`
  que enmascara, deploy a prod sin aprobación, artefacto público, checkout con credenciales
  persistidas) y **recomendaciones de optimización** (cache ausente, jobs serializados, pasos
  redundantes) → **plan 248**. El 246 **no emite ni un solo juicio** sobre lo que encuentra.
- **Reglas semánticas GitLab `GL001..GLnn`**, catálogo de constructos GitLab y endurecimiento del
  parser/renderer de GitLab → **plan 249**. Por eso las limitaciones del `extract_trigger` de
  GitLab (branches vacías, `has_schedule` siempre false) están **declaradas** en F1 y no
  disimuladas.
- **Editar pipelines** — patch quirúrgico por lenguaje natural, diff, commit HITL → **plan 250**.
  El 246 es read-only absoluto: no define ni un verbo de escritura (test F4 #6).
- **Matriz de entornos** — qué valores por entorno exige cada pipeline, formulario, faltantes,
  caja fuerte del Plan 94 → **plan 251**. El 246 no inventaría variables, ni service connections,
  ni environments de ADO.
- **Bundle descargable + README operativo + frontera de capacidades** → **plan 252**.
- **Crear pipelines desde cero por lenguaje natural** → **planes 243 (F0..F3.5, ya implementado) y
  244 (F4..F9)**. El 246 no genera YAML.
- **Registrar una definición nueva en ADO** — ya existe con HITL en
  `ado_pipeline_definitions.ensure_yaml_definition` (`:125`) y `DefinitionConfirmRequired` (`:120`).
  El 246 **no** lo llama ni lo envuelve.
- **Disparar corridas** — ya existe (`trigger_pipeline`, Planes 72/95). Fuera.
- Y todo lo recortado por mí en **§3.5** (historial por rama, persistencia en disco, runners/pools,
  ramas remotas).

---

## 7. Glosario, orden de implementación, comandos y DoD binaria

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **Definición** (ADO) | Objeto registrado en Azure DevOps que apunta a un YAML (`process.yamlFilename`). Tiene id y nombre |
| **Pipeline registrada** | Una definición ADO, o el archivo de CI declarado del proyecto GitLab |
| **Huérfana** | YAML de pipeline presente en el working tree que **no** corresponde a ninguna definición registrada. Categoría `en_repo_sin_registrar` |
| **Rota** | Definición registrada cuyo YAML **no** está en el repo. Categoría `registrada_sin_archivo` |
| **Clave de identidad** | `f"{provider}::{ruta_normalizada}"`, o `f"{provider}::#def{id}"` sin YAML. Determinista |
| **Fuente** | Uno de los 3 orígenes: `ado_definitions`, `gitlab_pipelines`, `repo_scan`. Cada una reporta su propio `available` |
| **Degradación** | Una fuente que no se pudo consultar devuelve `{available:false, capability, provider, reason, workaround}` y el resto sigue. Nunca un 500 |
| **Camino feliz** | Las 3 fuentes disponibles y la lista de ADO trayendo `process` ⇒ 3 llamadas de red |
| **Read-only absoluto** | Ninguna ruta de código de este plan escribe en disco, en el repo, en el proveedor ni en la BD |

### 7.2 Orden de implementación (estricto)

```
F0  núcleo puro           → sin dependencias         → 17 tests
F1  barrido del repo      → usa F0 (make_entry)      → 28 tests
F2  fuente ADO            → usa F0                   → 13 tests
F3  fuente GitLab + armado→ usa F0 + F1 + F2         → 14 tests
F4  endpoint + flag       → usa F3 (build_inventory) → 10 tests
F5  panel                 → usa F4 (endpoint)        → 18 tests
```
F1 y F2 son **independientes entre sí** y pueden hacerse en cualquier orden después de F0.
Todo lo demás es estrictamente secuencial. **F5 no se empieza hasta que F4 esté verde**: sin el
endpoint no hay nada que pintar.

### 7.3 Comandos exactos (verificados el 2026-07-26 en esta máquina)

> **Trampa de la casa:** en `backend/` conviven **dos** entornos — `backend/.venv` (Python
> **3.13.5**) y `backend/venv` (Python **3.11.9**), ambos con pytest 8.3.3. **Usá `.venv`.**
> El frontend **no tiene script `test`** en `package.json`: `npm test` **falla**; se usa `npx vitest`.

```powershell
# --- BACKEND: los 4 archivos de test de este plan (SIEMPRE por archivo) ---
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan246_pipeline_inventory.py -q     # F0
.venv\Scripts\python.exe -m pytest tests/test_plan246_repo_scan.py -q              # F1
.venv\Scripts\python.exe -m pytest tests/test_plan246_inventory_sources.py -q      # F2 + F3
.venv\Scripts\python.exe -m pytest tests/test_plan246_inventory_endpoint.py -q     # F4

# --- BACKEND: ratchet del arnés (OBLIGATORIO tras crear CUALQUIER test_*.py nuevo) ---
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q

# --- BACKEND: flags (OBLIGATORIO tras tocar services/harness_flags.py) ---
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
#   Rojo AJENO conocido: test_harness_flags_help tiene 4 fallos que NO son de este plan.
#   Validá TU entrada aislada:
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q -k "curated or category"

# --- BACKEND: no regresión de lo que este plan roza ---
.venv\Scripts\python.exe -m pytest tests/test_plan73_pipeline_spec.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan218_capability_unavailable.py -q
.venv\Scripts\python.exe -m compileall -q services api

# --- FRONTEND: un archivo de test ---
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineInventoryModel.test.ts

# --- FRONTEND: gate de tipos ---
npx tsc --noEmit
```

> Si un comando falla por dependencias, probá el mismo con `venv\Scripts\python.exe` (3.11.9)
> **antes** de tocar el código: puede ser el entorno, no tu cambio.

### 7.4 Regla de anclajes (obligatoria para quien implemente y para quien critique)

1. **Todo anclaje lleva el símbolo, no sólo el número:** `ado_ci_provider.py:135 (_map_status)`.
2. **El número es una pista, no un contrato.** Si la línea no coincide, **greppeá el símbolo**.
3. **Prohibido concluir "no existe" porque la línea no coincide**, y prohibido reimplementar algo
   que ya está. Si el símbolo no aparece con `grep`, **frená y reportalo**.
4. **No escribas un anclaje que no hayas abierto.** Lo no verificado va a §2.4.
5. **Deriva ya detectada en el árbol (no la arregles acá):**
   `ado_pipeline_definitions.py:83-84` cita `ado_client.py:257` pero `def _request` está en
   **`ado_client.py:269`**.

### 7.5 DoD binaria del Plan 246

El plan está **HECHO** cuando **las 12 líneas** son verdes. Nada de "casi".

| # | Criterio | Comando / verificación |
|---|---|---|
| 1 | F0 verde | `pytest tests/test_plan246_pipeline_inventory.py -q` → 17 passed |
| 2 | F1 verde | `pytest tests/test_plan246_repo_scan.py -q` → 28 passed |
| 3 | F2+F3 verdes | `pytest tests/test_plan246_inventory_sources.py -q` → 27 passed |
| 4 | F4 verde | `pytest tests/test_plan246_inventory_endpoint.py -q` → 10 passed |
| 5 | F5 verde | `npx vitest run src/devops/__tests__/pipelineInventoryModel.test.ts` → 18 passed |
| 6 | Tipos | `npx tsc --noEmit` → 0 errores |
| 7 | Compila | `python -m compileall -q services api` → sin salida |
| 8 | Ratchet | `pytest tests/test_harness_ratchet_meta.py -q` → passed (**4** archivos nuevos en `run_harness_tests.sh:20` **y** en `run_harness_tests.ps1:13`) |
| 9 | Flags | `pytest tests/test_harness_flags.py -q -k "curated or category"` → passed (flag en `_CATEGORY_KEYS` **y** en `_CURATED_DEFAULTS_ON`) |
| 10 | Contrato CI intacto | `CI_PORT_METHODS == ("infer_item_pipeline","monitor_pipeline","trigger_pipeline")` (test centinela F2 #13) |
| 11 | Cap de red | Los tests F2 #7 y #11 asertan un **número exacto** de llamadas al fake y pasan |
| 12 | Read-only | El test F4 #6 confirma **405** en POST/PUT/PATCH/DELETE, y `grep -rn "commit_file\|trigger_pipeline\|ensure_yaml_definition" services/pipeline_inventory.py api/pipeline_inventory.py` → **0 hits** |

**Smoke visual del operador (no automatizable, §2.4-7):** abrir el panel DevOps → grupo
*Construir* → pestaña **Inventario**; verificar que (a) lista pipelines, (b) el banner de fuentes
caídas aparece si falta el PAT o GitLab, (c) el botón "Actualizar" refresca, (d) apagando la flag
desde Configuración → Arnés aparece el `FlagGateBanner` en vez de una pantalla en blanco.
