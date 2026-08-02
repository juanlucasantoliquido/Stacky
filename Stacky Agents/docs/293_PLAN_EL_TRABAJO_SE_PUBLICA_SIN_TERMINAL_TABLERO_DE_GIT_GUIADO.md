# Plan 293 — El trabajo se publica sin terminal: tablero de Git guiado para quien no sabe Git

**Estado:** **v2 — CRITICADO Y CORREGIDO.** 2026-08-02, rama `docs/plan-279`, sin push. (v1 → v2: **RECHAZADO** con 7 bloqueantes; corregidos abajo.)
**Juez v2: subagente independiente, misma corrida, contexto limpio**
**Fecha:** 2026-08-02
**Rama en la que se escribió:** `docs/plan-279`
**Alcance:** backend (`services/` + `api/`) y frontend (una pantalla nueva). **Cero migraciones de esquema. Cero escritura en la base del operador. Cero threads nuevos.**
**Depende de:** Plan 265 F4 (`services/console_repo.py`, el panel de repositorio de solo lectura), Plan 73 F4 (`services/repo_writer.py`, el puerto `RepoWriter`), Plan 110 (`services/merge_request_provider.py`, el puerto `MergeRequestProvider`), Plan 177/291 (`services/incident_dev_autocommit.py`, el auto-PR que ya publica por REST), Plan 175 F1 (`frontend/src/services/confirmGateway.ts`), Plan 273 (`frontend/src/services/gateState.ts`, el gate de tres estados), Plan 283 (`backend/api/meetings.py`, el molde de tab nuevo con `/health`).

> Todo número, ruta y línea de este documento se midió **abriendo el archivo o ejecutando el comando** el 2026-08-02 sobre `docs/plan-279`. Lo que **no** se pudo medir sin tocar el GitLab/ADO del operador está marcado **NO VERIFICABLE DESDE EL REPO** y **no se usa como criterio de aceptación**.

---

## CHANGELOG v1 → v2

El juez verificó **147 anclajes y afirmaciones** abriendo los archivos y **corriendo los comandos**: **132 OK · 8 DESFASADOS · 7 NÚMEROS FALSOS**. Veredicto de la v1: **RECHAZADO** (7 bloqueantes). Ninguno era un anclaje inventado — como en los 5 planes anteriores de la serie, **lo que hundió la v1 fueron supuestos de capacidad y baselines movidos**, no citas falsas.

| # | Bloqueante corregido en v2 | Dónde |
|---|---|---|
| **C1** | **La v1 prometía "pérdida de trabajo estructuralmente imposible" y no lo es en GitLab.** `commit_file` de GitLab **no manda `last_commit_id`** (`services/gitlab_provider.py:877-881`): es **último-que-escribe-gana**. ADO **sí** valida con `old_object_id` (`services/ado_provider.py:163-193`) y rechaza. Asimetría no declarada, en el eje crítico del pliego | §2.5, §3.1, §3.4, R13, U15, F6 |
| **C2** | **F3 tenía un criterio mutuamente insatisfacible.** El caso 5 de `consoleRepoPanel.test.ts:34-39` **ya asertea `UU` → `otros`** y suma un total sobre **las 5 claves viejas**. Pedir "mover `UU` a conflictos" **y** "los casos previos siguen verdes" no se puede cumplir | §F3 |
| **C3** | **F3 rompía en silencio un consumidor de producción que la v1 no nombraba.** `CodexConsoleFull.tsx:415-422` arma su lista con **las 5 claves viejas**: agregar `conflictos` haría **desaparecer** de la pantalla de Repositorio los archivos que hoy sí se ven bajo "Otros" | §F3, §12 |
| **C4** | **Baseline de ratchets FALSO por 1 en cada uno.** Medido con **el regex del propio test**: `.sh` = **836** (no 835), `.ps1` = **772** (no 771). Los objetivos `843`/`779` de la v1 eran **aritméticamente imposibles**: un implementador que parara en 843 dejaría **un archivo sin registrar** y pondría rojo un test hoy **verde** | §F0, §F10, DoD |
| **C5** | **El "rojo de fábrica" del ratchet NO EXISTE: está VERDE.** Medido: `test_harness_ratchet_meta.py` **4 passed / 0 failed** y `test_plan259_ratchet_script_parity.py` **12 passed / 0 failed** (la v1 decía "1 failed, 15 passed"). La v1 **debilitó** el criterio de F10 apoyándose en ese rojo inexistente | §F0, §F10 |
| **C6** | **F1.b nunca decía `default=True`.** La plantilla de `FlagSpec` de la v1 no declara `default=`, y `test_declared_default_true_set` exige `declared_default(spec) is True` para toda key de `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:1196-1204`). Siguiendo la v1 al pie de la letra, la flag ON **rompía dos tests hoy verdes** | §F1.b |
| **C7** | **`run_pull_check` tiene 5 llamadores de producción, no 6**, y "correr los 6 llamadores" no es un caso de test ejecutable. La v1 contaba "y los tests" como el sexto | §F4 |

**Anclajes desfasados corregidos (8), con su línea real:** `ado_provider.commit_file` `:216`→**`:146`** · `incident_dev_autocommit` `commit_file` `:151`→**`:168`**, `create_merge_request` `:170`→**`:187`**, import de `api/` `:232`→**`:249`**, descarte de binarios `:139`→**`:156`**, criterio de exclusión `:210-225`→**`:227-244`** · `app.py` "NO agregar threads nuevos" `:635`→**`:641`** · `conftest.py` `:20`→**`:19`**.

**Números falsos corregidos (7):** `.sh` 835→**836** · `.ps1` 771→**772** · objetivos 843/779→**845/781** (836/772 **+9**, porque F2.b suma un archivo de test) · ratchets "1 failed/15 passed"→**16 passed/0 failed** · "sólo 3 tests monkeypatchean `data_dir`"→**110** · "6 llamadores"→**5**.

**Números de la v1 RE-MEDIDOS Y CONFIRMADOS (no se tocan):** `FLAG_REGISTRY` **495** (bool 367 · int 73 · csv 26 · float 14 · str 14 · json 1) · `PLAIN_HELP` **403** (faltan 92) · brecha `.sh−.ps1` **64** con `_PS1_LAG_MAX = 64` · allowlist **194** · `test_harness_flags.py` **59/0** · `test_harness_flags_help.py` **4F/4P** · `test_harness_flags_bounds.py` **1F/17P** · `ALL_TABS` **19** · `create_merge_request` **exactamente 4 parámetros** en los dos proveedores · `link_attachment` **sí** pisa la descripción · **no** hay `MAX_CONTENT_LENGTH` · `declarar` **sí** exige `execution_id` · `groupFilesByStatus` **sí** clasifica mal los 3 conflictos.

**Además:** §3.4 nueva (el modelo de concurrencia, que la v1 no tenía) · R13/R14 nuevos · U15/U16 nuevos · §11.0 nueva (**los tres cortes desplegables**, porque la v1 no tenía ninguna entrega intermedia) · una **[ADICIÓN ARQUITECTO]** en §F2.b.

---

## 0. Lo que se EJECUTÓ contra el código de hoy

Antes de proponer nada se corrieron cuatro sondas de solo lectura. Salida literal:

```
== A) git status --porcelain=v2 --branch (lo que el panel NECESITA) ==
# branch.oid f6a7b485bb89e5af4d46905978d252dd8e6ef037
# branch.head docs/plan-279
1 .M N... 100644 100644 100644 49fdb7ac... 49fdb7ac... Capacitaciones/.../PRESENTACION_SESION_IA_2026-08-05.html
(47 líneas en total)

== B) git status --porcelain=v1 (lo que console_repo.py USA HOY) ==
 M "Capacitaciones/Onboarding Stack Agentico/PRESENTACION_SESION_IA_2026-08-05.html"
 M "Stacky Agents/backend/api/agents.py"
```

| | Lo que se midió | Consecuencia para este plan |
|---|---|---|
| **A vs B** | `--porcelain=v1` **no trae** `# branch.head`, ni `# branch.upstream`, ni `# branch.ab` (adelante/atrás). `console_repo.repo_status` usa v1 (`services/console_repo.py:97`) | El requisito *"consultar estado local y remoto"* **no se puede cumplir con el código de hoy**. F2 cambia a `v2 --branch`, que trae las tres cosas en el mismo proceso |
| **C** | `run_pull_check` lee la política de `config.STACKY_PRE_RUN_GIT_WORKSPACE_POLICY` en `services/pre_run_git.py:102`; **`policy` NO es parámetro de la función** | Ver §3.3. Es el supuesto de capacidad más caro de este plan |
| **D** | `GET /api/diag/git/pull-check` (`api/diag.py:717-746`) llama a `run_pull_check(..., enabled=False, required=False, fetch=fetch)` y marca `report_only: True` (`api/diag.py:745`) | Ya hay un endpoint de *diagnóstico* de frescura. **No trae los cambios**: con la política de fábrica `fetch_only_warn` el bloque de merge de `pre_run_git.py:231-240` no se ejecuta nunca |

---

## 1. Objetivo y KPI honesto

**Objetivo:** que una persona sin conocimientos técnicos pueda entender el estado de su repositorio, revisar lo que cambió, publicar su trabajo como una propuesta de cambio revisable, adjuntar capturas como evidencia de prueba y entender qué pasó cuando algo falla — **todo visual, guiado y sin terminal**.

### 1.1. El KPI, y por qué NO es "cantidad de comandos ahorrados"

| # | Indicador | Hoy (**medido** 2026-08-02) | Meta | Cómo se mide |
|---|---|---|---|---|
| **K1** | Pantallas de Stacky desde las que una persona no técnica puede publicar su trabajo a una propuesta de cambio revisable | **0**. El único camino que existe es el **automático** del Dev Resolutor (`services/incident_dev_autocommit.py:80`), que se dispara solo al terminar una ejecución de agente y **no tiene entrada manual** | **1** | §F8, criterio binario: existe el tab y su `/health` responde `flag_enabled` |
| **K2** | Verbos git **destructivos** alcanzables desde el código nuevo de este plan (`push --force`, `reset`, `clean`, `checkout --`, `branch -D`, `rebase`, `stash`) | — (el módulo no existe) | **0, probado por un test que enumera por AST** | §F1, `test_plan293_catalogo_cerrado.py` |
| **K3** | Archivos en conflicto que el agrupador del frontend clasifica **mal** hoy | **3 de 3** (`AA`→"nuevos", `DD`→"borrados", `UU`→"otros"), medido leyendo `frontend/src/services/consoleRepoPanel.ts:29-37` | **0** | §F3, caso por caso |
| **K4** | Mensajes de error de git que hoy llegan al operador **en crudo** desde el panel de repositorio | **4 de 4** (`console_repo.py:101,104,128,148`: *"git status devolvió un error"*, *"git no está disponible o se agotó el tiempo de espera"*, …) | **0**: los 4 tienen traducción llana **con instrucción de qué hacer** | §F7, diccionario con caso por entrada |
| **K5** | Propuestas de cambio abiertas desde el tablero nuevo contra el GitLab/ADO real del operador | 0 | ≥1 | **NO VERIFICABLE DESDE EL REPO.** Requiere credenciales reales. Es el humo de §11.3, **trabajo del operador**, y **no** es criterio de aceptación de ninguna fase |

> **K1 = 0 no es una queja: es el gap.** Stacky ya sabe publicar código a una rama y abrir un MR — lo hace solo, al final de una ejecución de agente. Lo que **no** existe es que una persona lo haga **a mano, viendo lo que manda, antes de mandarlo**.

### 1.2. Lo que este plan NO promete

- **No promete reemplazar git.** Promete cubrir el camino feliz de una persona que trabaja sobre un repo ya clonado y configurado.
- **No promete `git commit` ni `git push` locales.** Ver §3 — la decisión de arquitectura, con su tabla de contraste y la alternativa perdedora escrita.
- **No promete leer comentarios ni aprobaciones de una PR.** No existen en el puerto (§2.4) y construirlos es otro plan.

---

## 2. Diagnóstico del estado actual *(entregable 1)*

**El hallazgo que ordena todo el plan: Stacky ya tiene casi todas las piezas, y ninguna está conectada a una pantalla que una persona pueda usar.**

### 2.1. Lo que YA existe y este plan REUSA (no se reescribe nada de esto)

| Capacidad | Dónde vive | Estado |
|---|---|---|
| Leer el estado del repo (`git status --porcelain=v1`) | `services/console_repo.py:83-113` `repo_status` | Existe. **Insuficiente**: sin rama, sin upstream, sin adelante/atrás (§0-A) |
| Leer el diff de un archivo, con secretos tapados y cota de 200 KB | `services/console_repo.py:116-168` `repo_diff` | Existe y sirve tal cual |
| Allow-list de carpetas de trabajo (**el control de acceso real de Stacky**) | `services/console_repo.py:35-46` `resolve_known_workspace` | Existe. Compara rutas **ya resueltas**, no strings (`:36-37`) |
| Anti path-traversal de rutas de archivo | `services/console_repo.py:49-63` `resolve_safe_path` | Existe y sirve tal cual |
| Tapado de secretos en texto que va al navegador | `services/console_secret_mask.py:40` `mask_secrets(text) -> tuple[str, int]` | Existe. Cobertura acotada, ver §9-R4 |
| Traer novedades del remoto (`fetch --prune`, `merge --ff-only`) con PAT no interactivo y PAT redactado en logs | `services/pre_run_git.py:88` `run_pull_check`, `:220`, `:232`, `:313` `_redact_command` | Existe. **Le falta un parámetro**, ver §3.3 |
| Commitear archivos a una rama del remoto **por REST** | `services/repo_writer.py:17` `RepoWriter.commit_file`; GitLab `services/gitlab_provider.py:853`, ADO **`services/ado_provider.py:146`** (v1 decía `:216`) | Existe y se usa en producción. **Sin candado optimista en GitLab**, ver §3.4 |
| Crear la rama en el primer commit | GitLab `start_branch` (Plan 291), ADO desde el Plan 95 (`services/ado_provider.py:183-190`) | Existe. GitLab **detrás de flag apagada**, ver §9-R2 |
| Abrir la propuesta de cambio | `services/merge_request_provider.py:78` `get_merge_request_provider` → `create_merge_request(source_branch, target_branch, title, description)` | Existe. **Exactamente 4 parámetros**, ver §2.4 |
| Listar y ver propuestas, con diff saneado y acciones con doble candado | `api/pr_review.py:174`, `:188`, `:375-414` | Existe, con UI (`frontend/src/components/devops/PrReviewerSection.tsx`) |
| Subir un archivo binario al tracker | ADO `services/ado_client.py:687` `upload_attachment`; GitLab `services/gitlab_provider.py:509` `upload_attachment` → devuelve `{markdown, url}` | Existe |
| Recibir archivos del navegador con topes y nombre saneado | `api/incidents.py:70-117` + `services/incident_store.py:23-30`, `:61-67` `sanitize_filename` | Existe. **Es el único `request.files` del backend** |
| Motor de diff por líneas, puro y sin dependencias | `frontend/src/components/dbcompare/lineDiff.ts:22` `diffLines`, cap `MAX_LINES = 3000` (`:12`) | Existe, importable desde cualquier página |
| Punto único de confirmación de acciones con efecto, que **niega por defecto** | `frontend/src/services/confirmGateway.ts:19-21` `denyByDefault` | Existe |
| Gate de navegación de tres estados que **no mata el deep link** | `frontend/src/services/gateState.ts:22-24`, `:48` `isGateOn` | Existe |
| Registro de eventos indexado, con `source`/`action`/`context_json` | `backend/models.py:434-477` `SystemLog`, escrito por `services/stacky_logger.py:187` `logger.info(source, action, **kwargs)` | Existe. **Es la auditoría**, ver §7 |
| Forma canónica de una degradación declarada + su renderer | `services/capability_degradation.py:79` `construir_entrada`; `frontend/src/services/capabilityDegradedModel.ts:17-23` (5 claves congeladas) | Existe, con una limitación: ver §5.4 |

### 2.2. Lo que NO existe (verificado, con lo que se grepeó)

1. **No hay `git add`, `git commit` ni `git push` sobre el repo de un proyecto alcanzable desde un endpoint de propósito general.** Se inventariaron los **17** módulos del backend que invocan `git` por subprocess; **15 son de solo lectura**. Los dos que escriben son:
   - `services/memory_git_sync.py` (`add -A` `:708`, `commit` `:714`, `push` `:681`) — **sobre un repo sintético propio de Stacky**, `ensure_stacky_home()/memory_repos/<slug>` (`:368-369`), **no** sobre el `workspace_root` del operador.
   - `services/doc_documenter.py` (`worktree add -b` `:675`, `add -A` `:1686`, `commit` `:1688`, `branch -D` `:714`) — sí sobre el repo del operador, gateado por `STACKY_DOCS_DOCUMENTER_ENABLED` (default `False`).
2. **No hay librería de git.** `backend/requirements.txt` (14 líneas): 0 hits de `GitPython`, `pygit2`, `dulwich`. Todo es `subprocess` con lista de argumentos.
3. **No hay lectura de comentarios, hilos ni aprobaciones de una PR.** Grepeado `merge_requests|pullrequests` en todo el backend: los `fetch_comments` que aparecen son del puerto de **tickets**, no de PRs.
4. **No hay campo de conflictos en la PR.** El único proxy es el booleano `mergeable` (GitLab `services/gitlab_provider.py:971-975`; ADO `services/ado_provider.py:351-352`).
5. **No hay `MAX_CONTENT_LENGTH` en la app Flask.** Un solo hit en todo `backend/` y es un comentario admitiéndolo (`api/incidents.py:80`). Todo endpoint nuevo hereda **cero** protección de tamaño de cuerpo.
6. **No hay `secure_filename` de werkzeug** (0 hits). La sanitización propia vive en `services/incident_store.py:61-67`.
7. **No hay componente `Tooltip`, ni `Stepper`/`Wizard` genérico, ni uploader reutilizable, ni visor de diff genérico** en el frontend. El uploader está **inline y duplicado 5 veces**; el molde vivo es `frontend/src/components/IncidentResolverModal.tsx:446-457`.

### 2.3. El agrupador de archivos del frontend clasifica MAL los conflictos

`frontend/src/services/consoleRepoPanel.ts:22-40` `groupFilesByStatus` decide por `includes()` y en este orden: `"??"` → sin seguimiento, luego `includes("A")` → nuevos, luego `includes("D")` → borrados, luego `includes("M")` → modificados.

Consecuencia **medida leyendo el código**, no supuesta:

| Código de git | Qué es de verdad | Dónde cae hoy | Línea |
|---|---|---|---|
| `AA` | **conflicto**: agregado por los dos lados | `new` (nuevos) | `:29-30` |
| `DD` | **conflicto**: borrado por los dos lados | `deleted` (borrados) | `:31-32` |
| `UU` | **conflicto**: modificado por los dos lados | `otros` | `:35-36` |
| `R` (renombrado) | renombrado | `otros` | `:35-36` |
| `AM` | agregado y luego modificado | `new` | `:29-30` |

El pliego pide explícitamente *"identificar archivos … con conflictos"*. **Hoy no sólo no se identifican: dos de los tres se muestran como si todo estuviera bien.** Es el defecto más peligroso del código existente para el objetivo de este plan.

### 2.4. `create_merge_request` acepta **cuatro** parámetros y nada más

Firma idéntica en los dos proveedores: `create_merge_request(self, source_branch, target_branch, title, description) -> dict` (GitLab `services/gitlab_provider.py:924`; ADO `services/ado_provider.py:265`). Grepeado `reviewers|draft|squash|remove_source_branch|assignee_id|isDraft` en `backend/services`: **cero hits** en ambos providers. El catálogo declarativo lo confirma: `services/provider_capabilities.py:153-154` y `:297-298` marcan `mr.reviewers` y `mr.policies` como **ausentes** en los dos.

**Consecuencia de diseño, no negociable:** todo lo que el pliego pide para el formulario de PR — resumen automático de los cambios, checklist de testing, evidencias adjuntas — **tiene que renderizarse dentro del string `description`**, porque es el único campo libre que los proveedores aceptan. Este plan lo asume explícitamente y construye ese renderizador (§F6).

### 2.5. Asimetría ADO / GitLab en lo que este plan toca

| Capacidad | GitLab | ADO | Anclaje |
|---|---|---|---|
| Diff textual de una PR | **Sí** | **No, nunca**: `diff_available=False`, `diff_text=""` fijos | `services/ado_provider.py:455-457` |
| Estado de CI en el **listado** | Real | **Hardcodeado `"none"`** | `services/ado_provider.py:425` |
| Costo de red de `get_merge_request` | 1 request | **2** (PR + builds del branch) | `services/ado_provider.py:320-323` |
| Crear la rama en el primer commit | Sólo con `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` **encendida** | Siempre | `services/gitlab_provider.py:904-907`; `services/ado_provider.py:183-190` |
| Adjunto → markdown embebible | `upload_attachment` devuelve `{markdown, url}` | `upload_attachment` devuelve `{id, url}` de **work item**, no de PR | `services/gitlab_provider.py:509-519`; `services/ado_client.py:687-735` |
| **Candado optimista al commitear** *(hallazgo v2, el más caro)* | **NO.** El cuerpo del POST es `{branch, commit_message, actions:[{action, file_path, content}]}` — **sin `last_commit_id`**. Es **último-que-escribe-gana** | **SÍ.** Resuelve `old_object_id` del ref y pushea contra él; ADO **rechaza** el push si el ref se movió | `services/gitlab_provider.py:877-881`; `services/ado_provider.py:163-193` |

Estas **seis** asimetrías se **declaran** (§5.4), no se esconden. Un plan que prometa "evidencias embebidas en la PR" sin distinguir proveedor está prometiendo algo que en ADO no pasa. Y un plan que prometa "es imposible perder trabajo" sin distinguir proveedor está prometiendo algo que **en GitLab no es cierto** (§3.4).

---

## 3. La decisión de arquitectura, con su alternativa perdedora escrita

### 3.1. Los dos caminos posibles para "publicar mi trabajo"

| | **M1 — por REST del tracker** (el elegido) | **M2 — git local** (`add`/`commit`/`push`) |
|---|---|---|
| Qué usa | `RepoWriter.commit_file` + `create_merge_request` | subprocess nuevo con `add`/`commit`/`push` |
| ¿Existe hoy? | **Sí**, y en producción (`services/incident_dev_autocommit.py:151,170`) | **No** (§2.2-1) |
| ¿Puede hacer force push? | **Estructuralmente imposible**: el endpoint `POST /projects/:id/repository/commits` no tiene ese verbo | Sí, salvo que un guard lo impida |
| ¿Puede reescribir historia o borrar ramas? | **No** | Sí |
| **¿Puede pisar el commit de otro?** | **SÍ en GitLab** — sin `last_commit_id` es último-que-escribe-gana. **No en ADO**. Ver §3.4 y R13 | Sí |
| Credenciales | Ya resueltas por el provider | Habría que meter el PAT en `http.extraheader` (camino nuevo de secreto) |
| Estado local después de publicar | **Queda igual**: los archivos siguen modificados localmente | Coherente |
| Archivos binarios / >1 MB | **Se descartan** (`services/incident_dev_autocommit.py:139`, `:210-225`) | Los sube |

### 3.2. Por qué el MVP elige M1

1. **El requisito de seguridad más duro del pliego se cumple por construcción, no por checklist.** El pliego dice *"NUNCA acciones destructivas, sobrescrituras, force push o borrado de ramas"*. Con M1 esos verbos **no son expresables**. Con M2 dependerían de que un guard esté bien escrito — y el repo ya tiene el contraejemplo: `services/doc_documenter.py:651` usa denylist `{"push","merge","stash"}` y **se olvidó de `branch`**, así que `git branch -D` (`:714`) llega al repo del operador por `POST /api/docs/documenter/decide`.
2. **Reusa un camino ya ejercitado**, en vez de abrir una superficie de escritura nueva.
3. **No agrega un camino nuevo para el PAT.**

### 3.3. El precio de M1, dicho de frente (y el supuesto de capacidad que casi hunde este plan)

**Después de publicar, los archivos locales siguen apareciendo como modificados.** Es correcto —el commit fue en el remoto— pero para una persona no técnica es desconcertante. El plan lo resuelve **diciéndolo**, no escondiéndolo: F5 obliga a que la pantalla de resultado muestre la frase exacta y ofrezca el botón de traer cambios.

Y acá está el supuesto de capacidad que hay que matar antes de escribir una línea:

> **`run_pull_check` NO mergea con la configuración de fábrica, y `policy` no es un parámetro.**
> `services/pre_run_git.py:102` hace `policy = config.STACKY_PRE_RUN_GIT_WORKSPACE_POLICY or "fetch_only_warn"`. El bloque que mergea (`:231-240`) sólo corre `if policy == "ff_only_block_on_dirty"`. El default de fábrica es `"fetch_only_warn"` (`backend/config.py:865-866`).
> **Un plan que dijera "el botón *Traer cambios* reusa `run_pull_check`" entregaría un botón que hace `fetch` y no baja nada, en verde, sin que ningún test lo note.** F4 agrega el parámetro `policy` (retrocompatible, `None` → sigue leyendo config).

### 3.4. El modelo de concurrencia — **el hueco de la v1, y el eje crítico del pliego**

La v1 afirmaba que con M1 *"perder trabajo es estructuralmente imposible"*. **Es falso en GitLab, y se verificó leyendo el cuerpo de la request:**

```python
# services/gitlab_provider.py:877-881 — el cuerpo REAL del POST
cuerpo = {
    "branch": branch,
    "commit_message": message,
    "actions": [{"action": action, "file_path": path, "content": content}],
}
```

**No hay `last_commit_id`.** La API de commits de GitLab lo acepta por acción justamente para el candado optimista, y `commit_file` **no lo manda**. Consecuencia exacta: entre el GET de `_detect_commit_action` (`gitlab_provider.py:861-863`, que sólo decide *crear/actualizar/sin-cambios*) y el POST, **cualquier commit ajeno sobre ese archivo en esa rama se pisa sin aviso y sin error**. ADO **no** tiene el problema: resuelve `old_object_id` del ref (`ado_provider.py:163-193`) y el push falla si el ref se movió.

**Qué hace este plan al respecto — tres medidas, ninguna toca el contrato compartido de `commit_file`** (cambiarlo afectaría al Dev Resolutor, al editor y al generador de pipelines: es otro plan):

1. **La rama es nueva y única.** `stacky/trabajo-<AAAAMMDD-HHMMSS>-<4 hex>`. El sufijo aleatorio existe porque **el timestamp al segundo colisiona** entre dos pestañas o dos publicaciones seguidas — y una colisión de rama es exactamente el escenario donde el último-que-escribe-gana muerde.
2. **`preview` consulta `branch_exists(rama)` y, si existe, NO deja publicar**: regenera el nombre. Publicar sobre una rama preexistente es el único camino por el que este tablero podría pisar algo, y queda cerrado.
3. **El reintento de U13 reusa la MISMA rama a propósito** (es lo que hace idempotente al reintento), y por eso el reintento **sólo se ofrece dentro de la misma sesión de publicación**, nunca como un botón suelto.

> **Lo que este plan NO arregla, dicho de frente:** si el operador enciende el anillo 3 y **dos personas** publican con el mismo PAT sobre GitLab, el candado optimista sigue sin existir en la capa compartida. Se declara como degradación `git.commit.optimistic_lock` (§5.4) y se documenta en D7. Arreglarlo de verdad es agregar `last_commit_id` a `RepoWriter.commit_file`, lo que cambia un contrato que hoy usan **3 consumidores** — **plan aparte**.

---

## 4. Flujos del usuario y casos de uso *(entregables 2 y 3)*

### 4.1. Flujo principal — "Publicar mi trabajo" (5 pasos)

```
[1 Revisar]  ->  [2 Elegir]  ->  [3 Describir]  ->  [4 Evidencia]  ->  [5 Confirmar]  ->  Resultado
```

1. **Revisar.** La pantalla muestra: en qué proyecto y carpeta estás, en qué rama, si estás al día con el remoto, y la lista de archivos agrupada en **Modificados / Nuevos / Borrados / En conflicto / Renombrados**. Cada archivo abre su diff.
2. **Elegir.** Casillas por archivo. Por defecto **ninguna marcada** (elegir es un acto deliberado). Contador: "3 de 12 archivos seleccionados".
3. **Describir.** Título y descripción. Botón *"Sugerir un texto"* (opcional, on-demand). Debajo, el **resumen automático** de los archivos incluidos, ya renderizado.
4. **Evidencia.** Checklist de pruebas (texto libre + casillas) y zona para arrastrar capturas, con previsualización y botón *Quitar*.
5. **Confirmar.** Pantalla de "esto es exactamente lo que va a pasar": rama que se va a crear, N archivos, destino. Confirmación por `confirmGateway`. Recién ahí se ejecuta.

**Resultado.** Éxito: link a la propuesta + la frase sobre el estado local + próximos pasos. Error: mensaje llano + qué hacer + botón de reintentar en el paso que falló.

### 4.2. Casos de uso normales, alternativos y de error *(entregable 3)*

| # | Caso | Tipo | Comportamiento exigido | Fase |
|---|---|---|---|---|
| U1 | Hay cambios, todo limpio, se publica | Normal | Propuesta creada, link mostrado | F6 |
| U2 | No hay ningún cambio | Alternativo | Estado vacío: *"No hay cambios para publicar."* Botón de publicar **deshabilitado** | F8 |
| U3 | La carpeta no es un repositorio | Alternativo | *"Esta carpeta no está preparada para guardar historial de cambios."* Sin jerga | F7 |
| U4 | Hay archivos en conflicto | **Error** | Banner **bloqueante**: no se puede publicar hasta resolverlos. Se listan por nombre | F3+F8 |
| U5 | Otra ventana está usando el repositorio (`index.lock`) | Error | *"Hay otra operación en curso sobre esta carpeta. Esperá unos segundos y volvé a intentar."* Ya detectado en `services/console_repo.py:90-94` | F7 |
| U6 | git no está instalado o tardó demasiado | Error | *"No se pudo consultar el estado de la carpeta."* + qué hacer | F7 |
| U7 | El proyecto no tiene tracker con propuestas (ni GitLab ni ADO) | Alternativo | La sección de publicar **no se ofrece**; se explica por qué | F6 |
| U8 | GitLab y la creación de rama está apagada | Error | Mensaje que **nombra la opción exacta** y dónde encenderla | F7 |
| U9 | Un archivo seleccionado es binario o pesa más de 1 MB | Alternativo | Se avisa **antes** de confirmar que ese archivo **no se va a incluir**, y por qué | F6 |
| U10 | El texto de un archivo contiene algo que parece una clave | **Error de seguridad** | Se avisa **antes** de confirmar, con el archivo y el tipo | F6 |
| U11 | Se selecciona más de 60 archivos | Alternativo | Se avisa y se pide acotar (mismo tope que `_MAX_FILES` de `services/incident_dev_autocommit.py:24`) | F6 |
| U12 | Falla al subir una evidencia | Alternativo | La propuesta **se crea igual**; la evidencia se marca como no adjuntada. Nunca se pierde la publicación por una captura | F6 |
| U13 | La red se cae a mitad de la publicación | Error | Se informa qué archivos alcanzaron a subir; reintentar es **idempotente** (`commit_file` devuelve `"unchanged"` si el contenido es idéntico, `services/gitlab_provider.py:864-871`) y **reusa la misma rama**, sólo dentro de la misma sesión (§3.4-3) | F6 |
| U14 | Traer cambios con la copia local sucia | Alternativo | Se avisa y **no se mergea** | F4 |
| **U15** | **La rama propuesta ya existe en el remoto** | **Error de seguridad** | `preview` lo detecta con `branch_exists` y **regenera el nombre**; **nunca** se publica sobre una rama preexistente (§3.4-2). Es el único camino por el que este tablero podría pisar un commit ajeno | F6 |
| **U16** | El proyecto no tiene `workspace_root`, o apunta a una carpeta que no está en la allow-list | Alternativo | *"Esta carpeta no está habilitada para trabajar desde Stacky."* Se nombra dónde se configura. **No** se revela la ruta absoluta | F7 |

---

## 5. Arquitectura propuesta *(entregable 4)* y pantallas *(entregable 5)*

### 5.1. Módulos nuevos del backend (4 archivos)

| Archivo nuevo | Responsabilidad | Qué NO hace |
|---|---|---|
| `backend/services/git_workbench.py` | Estado enriquecido del repo: rama, upstream, adelante/atrás, archivos agrupados **con conflictos**. Catálogo **cerrado** de verbos | No escribe. No conoce Flask |
| `backend/services/change_proposal.py` | Orquesta la publicación: valida selección, arma la `description`, llama a `commit_file` por archivo y a `create_merge_request` | No ejecuta git. No conoce Flask |
| `backend/services/work_evidence.py` | Guarda las evidencias en `data_dir()/work_evidence/<proposal_id>/`, con topes y nombre saneado | No sube al tracker (eso es `change_proposal`) |
| `backend/api/workbench.py` | Blueprint `/workbench`: parsea, delega, serializa | Cero lógica |

**Riel respetado:** ninguno de los tres `services/` importa de `api/`. (El repo tiene una violación conocida y consciente en **`services/incident_dev_autocommit.py:249`** — `from api.devops_production import _default_branch`, v1 decía `:232`; este plan **no la replica**.)

### 5.2. El catálogo cerrado de verbos git — el corazón de la seguridad

En `backend/services/git_workbench.py`, copiando el patrón **allowlist** de `services/night_foundry_workers.py:44-51` (que **lanza `ValueError`**), no el denylist de `doc_documenter.py:651` (que se olvidó de `branch`):

```python
_VERBOS_PERMITIDOS = frozenset({"status", "rev-parse", "diff", "for-each-ref"})

def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess | None:
    if not args or args[0] not in _VERBOS_PERMITIDOS:
        raise ValueError(f"verbo git no permitido en el tablero: {args[0] if args else '<vacio>'}")
    ...  # mismo hardening que services/console_repo.py:66-80
```

**Por qué una allowlist y no una denylist:** con denylist, olvidarse de un verbo **abre** un agujero; con allowlist, olvidarse **cierra** una función y se ve en el acto. El repo ya pagó ese error una vez (§3.2-1).

### 5.3. Pantallas *(entregable 5)*

Un tab nuevo **`publicar`** (label *"Publicar mi trabajo"*, ruta `/publicar`) dentro del grupo cuyo `id` es `trabajo` de la barra lateral. **El `id` del tab NO puede ser `trabajo`: colisiona con el `id` del grupo** — ver la nota de F8 y D6. Cinco zonas:

| Zona | Componente | Reuso |
|---|---|---|
| Cabecera de contexto (proyecto · carpeta · rama · al día/atrasado) | `WorkbenchHeader.tsx` | `SectionHeader`, `StatusChip` |
| Lista de archivos por grupo, con casillas | `WorkbenchFileList.tsx` | `groupFilesByStatus` corregido (F3) |
| Visor de diferencias | `WorkbenchDiff.tsx` | **`diffLines` de `frontend/src/components/dbcompare/lineDiff.ts:22`** + 2 clases CSS propias |
| Asistente de 5 pasos | `PublishWizard.tsx` (cascarón) + `publishWizardModel.ts` (**toda la lógica**) | Molde de `PipelineCopilotSection.tsx:35-38` |
| Evidencias | `EvidenceDropzone.tsx` | Molde de `IncidentResolverModal.tsx:446-457` |

**Regla dura del repo, heredada:** RTL/jsdom **no están instalados**. Un `.test.tsx` con RTL reporta *"no tests"* y sale con **exit 0** — un falso verde perfecto. Por eso **toda** la lógica testeable va en `.ts` puro y el `.tsx` sólo pinta.

### 5.4. Degradación declarada

Se reusa la **forma** de `services/capability_degradation.py:79` `construir_entrada(capability, reason, provider, site)` (5 claves, congeladas por `frontend/src/services/capabilityDegradedModel.ts:17-23`).

> **Límite medido:** `capability_degradation.declarar` **exige `execution_id`** (`services/capability_degradation.py:100`, `:123-124` devuelve `False` si es `None`) porque anota en la fila de una ejecución. El tablero **no tiene ejecución**. Por eso este plan usa `construir_entrada` (que es **pura**) y devuelve las entradas **en la respuesta del endpoint**, sin persistirlas. Suponer que `declarar` sirve acá sería un no-op silencioso.

Capacidades que se declaran degradadas (**5**): `git.pr.diff_text` y `git.pr.pipeline_status_en_listado` (ADO, §2.5), `git.evidence.embed` (ADO), `git.branch.create` (GitLab con la flag apagada) y **`git.commit.optimistic_lock` (GitLab siempre, §3.4)** — esta última es de la v2 y es la que más importa: es la única que el usuario no puede deducir mirando la pantalla.

---

## 6. Contratos de API *(entregable 6)*

Blueprint `bp = Blueprint("workbench", __name__, url_prefix="/workbench")` en `backend/api/workbench.py`, registrado en `backend/api/__init__.py` (import + `api_bp.register_blueprint`). **No declarar `/api` en el blueprint**: `api_bp` ya lo aporta y declararlo produce `/api/api/...` (el defecto documentado en `backend/api/meetings.py:4-5`).

| Método | Ruta | Cuerpo / query | Respuesta | Flag |
|---|---|---|---|---|
| GET | `/api/workbench/health` | — | `{ok, flag_enabled, publish_enabled, tracker_type}`. **200 SIEMPRE** | — |
| GET | `/api/workbench/overview` | `project` | `{ok, available, reason, repo:{branch, upstream, ahead, behind, detached}, files:[{path,status,grupo}], conflictos:[...], degradaciones:[...]}` | `STACKY_WORKBENCH_ENABLED` |
| GET | `/api/workbench/diff` | `project`, `path` | `{ok, available, diff, truncated, masked, reason}` — delega en `console_repo.repo_diff` | `STACKY_WORKBENCH_ENABLED` |
| POST | `/api/workbench/preview` | `{project, paths[], title, description, testing[]}` | `{ok, rama, destino, incluidos[], excluidos:[{path,motivo}], sospechas[], description_markdown}` — **no escribe nada** | `STACKY_WORKBENCH_ENABLED` |
| POST | `/api/workbench/evidence` | multipart: `proposal_id`, `files` | `{ok, archivos:[{nombre, bytes, preview_url}]}` | `STACKY_WORKBENCH_ENABLED` |
| POST | `/api/workbench/publish` | `{project, paths[], title, description, testing[], evidence_ids[], confirm:true}` | `{ok, pr_url, pr_id, rama, archivos_publicados, evidencias_adjuntadas, avisos[]}` | **`STACKY_WORKBENCH_PUBLISH_ENABLED`** |
| POST | `/api/workbench/pull` | `{project, confirm:true}` | `{ok, mergeado, pasos[], avisos[]}` | **`STACKY_WORKBENCH_PULL_ENABLED`** |

**Reglas transversales de los endpoints**
- `/health` responde **200 siempre**, incluso con la flag apagada, y la clave del veredicto es literalmente **`flag_enabled`**: `frontend/src/utils/flagHealth.ts:9-16` sólo acepta esa clave; `{"ok":true,"enabled":true}` da `"unknown"` y el tab queda eternamente en esqueleto.
- Los `POST` que escriben exigen `confirm=true` (molde de `api/pr_review.py:389-390`).
- **Guard de tamaño obligatorio en `/evidence`**: `request.content_length` contra el tope **antes de leer nada**, porque la app **no define `MAX_CONTENT_LENGTH`** (§2.2-5). Molde exacto: `api/incidents.py:80-87`.
- Ningún endpoint devuelve rutas absolutas del disco del operador ni valores de PAT.

---

## 7. Modelo de datos *(entregable 7)*

**Cero tablas nuevas. Cero migraciones.**

| Qué | Dónde | Por qué así |
|---|---|---|
| Evidencias subidas | `runtime_paths.data_dir()/work_evidence/<proposal_id>/` + `meta.json` | Espejo exacto de `services/incident_store.py:36-37`, que ya funciona |
| Auditoría de acciones | Filas en `system_logs` vía `stacky_logger.info(source="git_workbench", action=...)` | La tabla **ya existe** con `source`, `action`, `user`, `context_json` e índices (`backend/models.py:434-477`). Crear una tabla de auditoría paralela sería duplicar |
| Estado de la propuesta | **No se persiste** | Es una operación sincrónica que termina en una URL. Persistirla obligaría a limpiarla, y el repo ya tiene la lección: los sidecars de `data_dir()/incident_dev_pr/` **se acumulan sin retención** |

**Acciones auditadas** (una fila cada una, con `context_json` **sin contenido de archivos**): `workbench_overview`, `workbench_preview`, `workbench_publish_intento`, `workbench_publish_ok`, `workbench_publish_error`, `workbench_pull`, `workbench_evidence_subida`.

**Topes de evidencia** (mismos valores que el intake ya probado, `services/incident_store.py:23-30`): 10 archivos, 10 MB por archivo, 25 MB total, extensiones de `IMAGE_EXTENSIONS ∪ {".pdf", ".txt", ".log", ".md"}`. Nombre por `incident_store.sanitize_filename` (**se importa, no se reescribe**).

---

## 8. Integraciones necesarias *(entregable 8)*

| Integración | Cómo | Anclaje |
|---|---|---|
| Ruteo ADO / GitLab | `services/tracker_provider.py:129` `get_tracker_provider`. **Sólo 2 valores**: `"gitlab"` y `"azure_devops"`; default `"azure_devops"` | `tracker_provider.py:131-132` |
| Commit remoto | `services/repo_writer.py:30` `get_repo_writer(project).commit_file(...)` | — |
| Propuesta de cambio | `services/merge_request_provider.py:78` `get_merge_request_provider(project).create_merge_request(...)` | — |
| Rama destino | `_default_branch_for` (`incident_dev_autocommit.py:245`) **NO se reusa**: arrastra el import de `api/` de **`:249`**. Se resuelve con `for-each-ref` local y fallback `"main"` | §5.2 |
| Evidencia → GitLab | `upload_attachment` → se **embebe el `markdown`** devuelto en la `description` de la propuesta, **al crearla** | `gitlab_provider.py:509-519` |
| Evidencia → ADO | **Degradación declarada.** Las evidencias quedan en Stacky y se listan por nombre en la descripción | §5.4 |

> ⚠️ **Prohibido llamar a `link_attachment` de GitLab** (`services/gitlab_provider.py:521-537`): lee la descripción actual del issue y si el `GET` falla asume `""` (`:526-529`), **pisando la descripción entera**. Es riesgo de pérdida de datos. La vía correcta es embeber el markdown en la `description` que ya se manda en `create_merge_request`, en **una sola** llamada.

---

## 9. Riesgos técnicos, funcionales y de seguridad *(entregable 9)*

| # | Riesgo | Severidad | Mitigación | Verificado por |
|---|---|---|---|---|
| **R1** | Una operación destructiva llega al repo del operador | **Alta** | Allowlist de verbos que **lanza** (§5.2) + M1 no expresa esos verbos | F1: test que enumera **por referencia** (no por AST del nombre: el AST da cero si la llamada va por alias) |
| **R2** | GitLab con `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` apagada ⇒ la publicación falla con un `400` que no menciona la rama | Alta | El `preview` lo detecta **antes** y el mensaje **nombra la opción y dónde encenderla** | F7, caso U8 |
| **R3** | Se publica un secreto | **Alta** | Se reusan los **6 patrones de alta confianza** de `services/incident_dev_autocommit.py:41-48`, que **avisan** sin tocar el contenido | F6, caso U10 |
| **R4** | El operador cree que el tapado de secretos es total | Media | Se declara: `console_secret_mask` cubre 6 prefijos + 8 nombres de clave y **no** cubre JWT, PATs de ADO (52 chars sin prefijo), claves PEM ni `user:pass@host` | F7, texto en pantalla |
| **R5** | Usar `pr_review_sanitize.redact_secrets` para el contenido a publicar | **Alta** | **Prohibido y escrito.** Es camino de **lectura** (hacia el modelo). Ya rompió código real: convierte `password = cfg.get("db_password")` en `password = ***REDACTED***` (`incident_dev_autocommit.py:28-40`) | F6, test negativo |
| **R6** | Confusión por el estado local tras publicar | **Media-alta (UX)** | §3.3: frase obligatoria + botón de traer cambios | F5 |
| **R7** | El tab no aparece o el deep link muere | Media | Las **13 patas** de §F8, y el gate de **tres** estados (`gateState.ts`) | F8 |
| **R8** | Cuerpo gigante en `/evidence` tumba el backend | Media | Guard por `content_length` antes de leer (§6) | F6 |
| **R9** | Publicar dos veces crea dos propuestas | Media | `commit_file` es idempotente por contenido (`gitlab_provider.py:864-871`); el botón se deshabilita mientras corre | F6, caso U13 |
| **R10** | Los tests nuevos del plan chocan con los rojos de fábrica | Media | **Todos los criterios son DELTA**, nunca absolutos (§F0) | F0 |
| **R11** | El plan asume un `workspace_root` que no es un repo git | Media | `validate_workspace_root` (`project_manager.py:185-202`) **no verifica que sea repo git**; y el repo real puede ser un **ancestro** (`incident_dev_pr.py:77` usa `rev-parse --show-toplevel`). Se resuelve con `rev-parse`, no asumiendo | F2 |
| **R12** | Se toca el trabajo de la sesión paralela | Media | Commits con pathspec explícito; cero `add -A`, cero `amend`/`reset`/`rebase`/`stash` | Orden de implementación |
| **R13** | **Publicar pisa el commit de otro en GitLab** (sin `last_commit_id`, §3.4) | **Alta** | Rama nueva con sufijo aleatorio + `branch_exists` en `preview` que **impide** publicar sobre una rama preexistente + degradación declarada `git.commit.optimistic_lock` | F6, caso **U15**, con mitad de contraste |
| **R14** | **F3 hace desaparecer archivos de una pantalla que hoy funciona.** Agregar claves a `GroupedRepoFiles` sin tocar `CodexConsoleFull.tsx:415-422` (que enumera **las 5 viejas a mano**) borra de la vista los archivos en conflicto y renombrados del panel de Repositorio ya existente | **Alta** | F3 actualiza el consumidor **en el mismo commit** y lo verifica con un test de texto | F3, con el consumidor **nombrado** |

---

## 10. Fases *(entregables 10, 11, 12, 13)*

**Comando base de test (backend)** — `backend/.venv` es **py3.13.5** (el otro, `backend/venv`, es py3.11.9). Siempre **por archivo**, nunca `pytest tests` entero (da miles de errores de contaminación, declarado en `backend/scripts/run_harness_tests.sh:4-6`):

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
$env:DATABASE_URL     = "sqlite:///:memory:"
$env:LLM_BACKEND      = "mock"
$env:STACKY_TEST_MODE = "1"
$env:STACKY_DATA_DIR  = "$env:TEMP\stacky_test_data"   # <- OBLIGATORIO, ver abajo
.\.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q -p no:warnings
```

**Frontend:** `cd "…\frontend"; npx vitest run src/<ruta>.test.ts` y `npx tsc --noEmit`.

> ⚠️ **`STACKY_DATA_DIR` no es opcional en este plan.** Medido: **no existe `backend/conftest.py`**; el único conftest (**`backend/tests/conftest.py:19`**, v1 decía `:20`) sólo hace `os.environ.setdefault("STACKY_TEST_MODE","1")`, que apaga logging/daemons pero **NO redirige `runtime_paths.data_dir()`** (`backend/runtime_paths.py:48-55`). Como F9 escribe evidencias en `data_dir()`, un test sin aislar **deja archivos reales en la carpeta del operador**. Es el mismo defecto que ya ocurrió con el sync de GitLab.
>
> **Corrección de la v2:** la v1 decía *"en todo el repo sólo 3 archivos de test lo monkeypatchean"*. **Es falso: son 110** (`grep -rln "monkeypatch.setattr.*data_dir" backend/tests/*.py | wc -l`). El dato importa al revés de como lo usaba la v1: **no es un patrón exótico, es la norma del repo**, así que hay 110 moldes para copiar y ninguna excusa para no hacerlo. El molde vivo más cercano sigue siendo `tests/test_plan291_guardia_repo.py` (**verificado: existe**).

> ⚠️ **Dos falsos verdes clásicos que invalidan un criterio:** `pytest -k` sin match sale **exit 0**, y un archivo de test inexistente sale **exit 4**. Todo criterio de este plan exige el **conteo de casos**, no el código de salida.

---

### F0 — Baselines medidos (sin código de producto)

**Objetivo:** que todos los criterios de este plan sean **delta**, nunca absolutos. **Ya medido el 2026-08-02** con el comando de arriba:

| Suite / métrica | Valor **medido hoy** | Cómo se usa como criterio |
|---|---|---|
| `tests/test_harness_flags.py` | **59 passed, 0 failed** — **VERDE** | Absoluto permitido: debe quedar en **59 + N, 0 failed** |
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** — ROJO DE FÁBRICA | **Sólo delta**: sigue en `4 failed / 4 passed`. Ver la trampa abajo |
| `tests/test_harness_flags_bounds.py` | **1 failed, 17 passed** — ROJO DE FÁBRICA | Congelado. Este plan **no declara flags numéricas**, así que no lo toca |
| `tests/test_harness_ratchet_meta.py` | **4 passed, 0 failed** — **VERDE** (la v1 decía "1 failed"; **se re-midió y el rojo ya no existe**) | Absoluto permitido: debe quedar en **4 passed, 0 failed** |
| `tests/test_plan259_ratchet_script_parity.py` | **12 passed, 0 failed** — **VERDE** | Absoluto permitido: **12 passed, 0 failed** |
| `FLAG_REGISTRY` | **495** flags (`bool` 367, `int` 73, `csv` 26, `float` 14, `str` 14, `json` 1) | Debe quedar en **498** tras F1.b |
| `PLAIN_HELP` | **403** entradas (faltan **92**) | Debe quedar en **406** |
| Ratchet `.sh` (`run_harness_tests.sh`) | **836** rutas (v1 decía 835) | **836 + 9 = 845** (9 archivos: los 8 de la v1 + `semaforo` de F2.b) |
| Ratchet `.ps1` (`run_harness_tests.ps1`) | **772** rutas (v1 decía 771) | **772 + 9 = 781** |
| Brecha `.sh − .ps1` | **64** | `_PS1_LAG_MAX` (`tests/test_plan259_ratchet_script_parity.py:46`) = **64**. `64 <= 64` pasa con **HOLGURA CERO** |
| `harness_ratchet_allowlist.txt` | **194** entradas efectivas | No cambia: los 8 tests nuevos van al ratchet, no al allowlist |
| `_CURATED_DEFAULTS_ON` | **12** keys | **13** tras F1.b (sólo `STACKY_WORKBENCH_ENABLED`) |

**Comando exacto para re-medir los dos ratchets — el mismo regex del test, no uno propio:**

```powershell
.\.venv\Scripts\python.exe -c "import re,pathlib; sh=pathlib.Path('scripts/run_harness_tests.sh').read_text(encoding='utf-8',errors='replace'); ps=pathlib.Path('scripts/run_harness_tests.ps1').read_text(encoding='utf-8',errors='replace'); SH=re.compile(r'^\s*(tests/[\w/]+\.py)\s*$',re.M); PS=re.compile(r'^\s*\"(tests/[\w/]+\.py)\"\s*,?\s*$',re.M); a=set(SH.findall(sh)); b=set(PS.findall(ps)); print('sh',len(a),'ps1',len(b),'brecha',len(a)-len(b))"
```

**Las CUATRO trampas que estos baselines desactivan:**

1. **La brecha de ratchets está EXACTAMENTE en su límite.** Registrar **un solo** archivo en el `.sh` sin registrarlo en el `.ps1` pone rojo `test_el_ps1_no_pierde_terreno` (`:85`) al instante. **Los 9 archivos van en los DOS, en el mismo commit.** Y la sintaxis **difiere**: `.sh` = ruta pelada sin comillas ni coma; `.ps1` = `"ruta",` con comillas. Una ruta sin comillas en el `.ps1` **no rompe el parseo: PowerShell la lee como nombre de comando y la pierde MUDA**.
2. **Los 4 rojos de la ayuda llana son asserts de CONJUNTO.** Omitir la entrada `PLAIN_HELP` de una flag nueva **no cambia el `4 failed`**. Un criterio *"delta cero en el conteo"* **no discrimina nada**. Por eso F1.b exige archivo propio con caso de discriminación.
3. **El ratchet está VERDE, y eso ENDURECE el criterio en vez de ablandarlo** *(corrección C5 de la v2)*. La v1 se apoyaba en un rojo ajeno que **ya no existe** para relajar F10 a *"ningún archivo de este plan aparece en sin-clasificar"*. Con la suite verde, ese criterio es **estrictamente más débil de lo alcanzable**: pasaría aunque el plan pusiera rojo el archivo. **El criterio de F10 vuelve a ser el absoluto: `test_harness_ratchet_meta.py` termina en 4 passed / 0 failed.** `test_ratchet_clasifica_todos_los_tests` (`tests/test_harness_ratchet_meta.py:43-52`) asertea `not sin_clasificar` sobre `todos - ratchet - allow`: **un solo archivo de este plan sin registrar lo pone rojo**, y eso es exactamente lo que queremos que vigile.
4. **Los conteos de ratchet SE MUEVEN entre corridas** *(corrección C4)*. Entre la v1 y la v2 subieron de 835/771 a **836/772** porque la sesión paralela registró un archivo. **Por eso los objetivos de F10 se expresan como `medido_en_F0 + 9`, nunca como el literal `845`/`781`**: si al implementar el baseline volvió a moverse, el objetivo se recalcula y se anota el desvío. Un plan que hardcodea el literal condena al implementador a parar en el número equivocado y dejar un archivo sin registrar.

**Criterio binario:** los **11** valores de la tabla se re-miden **con los comandos de arriba** antes de tocar código y **coinciden uno por uno**; si alguno se movió (sesión paralela), se re-ancla, **se recalculan los objetivos derivados de F10** y se anota el desvío en el commit de F0.
**Flag:** ninguna. **Trabajo del operador: ninguno.** **Runtimes:** N/A.

---

### F1.b — Las tres opciones y sus guardianes

**Objetivo:** registrar las 3 flags del plan de forma que pasen **todos** los guardianes.

**Son 7 archivos en 8 bloques** para una booleana `default OFF` (medido):

| # | Archivo | Bloque | Qué se agrega |
|---|---|---|---|
| 1 | `backend/services/harness_flags.py` | `FLAG_REGISTRY` (`:624`–`:7407`) | **Las dos OFF:** `FlagSpec(key=..., type="bool", label=..., description=..., group="global", env_only=False)` — **sin `default=`**. **La ON (`STACKY_WORKBENCH_ENABLED`): el MISMO `FlagSpec` PERO con `default=True` explícito.** Ver la trampa de abajo |
| 2 | `backend/services/harness_flags.py` | `_CATEGORY_KEYS` (`:120`–`:620`) | la key en **una** categoría — se propone `capacidades_optin` |
| 3 | `backend/config.py` | `class Config` (`:60`–`:2745`) | `STACKY_X: bool = os.getenv("STACKY_X", "false").strip().lower() in ("1","true","yes")` |
| 4 | `backend/services/harness_flags_help.py` | `PLAIN_HELP` (`:25`–`:2517`) | `PlainHelp(what, on_effect, off_effect, example)` |
| 5 | `backend/scripts/run_harness_tests.sh` | `HARNESS_TEST_FILES` (`:20`–`:1091`) | ruta **pelada** |
| 6 | `backend/scripts/run_harness_tests.ps1` | `$HarnessTestFiles` (`:13`–`:1007`) | `"ruta",` **entrecomillada** |
| 7 | `backend/tests/test_plan293_flags.py` | archivo nuevo | el guardián **real** |
| **8** | `backend/tests/test_harness_flags.py` | `_CURATED_DEFAULTS_ON` (`:467`–`:1132`) | **SÓLO** para `STACKY_WORKBENCH_ENABLED`, que nace **ON** |

> ⚠️ **`_CURATED_DEFAULTS_ON` es igualdad EXACTA de conjuntos** (`test_default_known_only_for_curated`, `tests/test_harness_flags.py:1207`: `assert known_keys == _CURATED_DEFAULTS_ON`). La flag **ON** debe estar ahí; las dos **OFF** **NO** deben estar. No hay término medio: cualquiera de los dos errores pone rojo un test hoy verde.
>
> ⚠️⚠️ **La trampa que hundió la v1 (C6): el conjunto y el `default=` son DOS ediciones, y la v1 sólo pedía una.** Hay **dos** tests que se miran entre sí:
> - `test_declared_default_true_set` (`tests/test_harness_flags.py:1196-1204`) exige, para **cada** key de `_CURATED_DEFAULTS_ON`, que `declared_default(spec) is True` **y** `default_is_known(spec) is True`.
> - `test_default_known_only_for_curated` (`:1207-1218`) exige que `{s.key for s in FLAG_REGISTRY if default_is_known(s)}` sea **igual** a `_CURATED_DEFAULTS_ON`.
>
> `default_is_known` es True **sólo si el `FlagSpec` declara `default=`**. Entonces: agregar `STACKY_WORKBENCH_ENABLED` a `_CURATED_DEFAULTS_ON` **sin** poner `default=True` en su `FlagSpec` pone **rojos los dos** (uno por "no es True", el otro por "faltante"). Y poner `default=False` en cualquiera de las dos OFF pone rojo el segundo por "extras". **La regla operativa, sin ambigüedad para un modelo menor: `default=` se declara si y sólo si la key está en `_CURATED_DEFAULTS_ON`, y ahí vale siempre `True`.**

> ⚠️ **Reglas de `PLAIN_HELP` que rompen si se ignoran:** `what` entre 10 y 200 chars; `on_effect` y `off_effect` ≤ **240** y **ambos empiezan con `"Si "`** — *sin tilde*; `example` ≤ 300; prohibida la `JARGON_DENYLIST` (`tests/test_harness_flags_help.py:17-20`, 19 términos con plural), las keys SCREAMING_SNAKE y los `F<n>`.

**Las tres flags:**

| Flag | Default | Justificación |
|---|---|---|
| `STACKY_WORKBENCH_ENABLED` | **ON** | Es **solo lectura**: mira el estado del repo, agrupa y muestra diffs. Ninguna de las 2 excepciones aplica, y el riel dice que lo de solo lectura **nunca** es excepción. Precedente medido: `STACKY_CONSOLE_REPO_PANEL_ENABLED` nace `"true"` (`backend/config.py:2622-2623`) |
| `STACKY_WORKBENCH_PULL_ENABLED` | **OFF — excepción (B)** | `merge --ff-only` **escribe en el árbol de trabajo real del operador** (`services/pre_run_git.py:232`), cambiando archivos de su disco sin que los haya pedido. Precedente exacto: `STACKY_PRE_RUN_GIT_PULL_ENABLED` nace `"false"` (`backend/config.py:859-860`) por esta misma razón |
| `STACKY_WORKBENCH_PUBLISH_ENABLED` | **OFF — excepción (B)** | **Publica en el GitLab/ADO real del operador**: crea rama, commits y una propuesta de cambio. Precedente exacto: `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` nace apagada por lo mismo |

**Test:** `backend/tests/test_plan293_flags.py`, acotado a **estas 3 keys** (molde vigente: `tests/test_plan292_flags.py`, 12 passed):
las 3 están en el registro (1) · `WORKBENCH_ENABLED` nace **ON** y las otras dos **OFF** (3) · las 3 existen en `config.py` (1) · ninguna declara `requires` (1) · las 3 categorizadas (1) · las 3 tienen ayuda llana (1) · la ayuda respeta la denylist (1) · empieza con `"Si "` **sin tilde** (1) · `WORKBENCH_ENABLED` **está** en `_CURATED_DEFAULTS_ON` y las otras dos **no** (1) · **caso de discriminación** (molde `tests/test_plan271_flags.py:74-93`): se borra la entrada de `PLAIN_HELP` de una de las 3 y **se exige que el gate se ponga rojo** (1) · **[v2, C6] `default_is_known(spec) is True` para `WORKBENCH_ENABLED` y `is False` para las dos OFF** — el caso que ataja el error que la v1 no veía (1). **13 casos.**

**Criterio binario:** 13 passed · `FLAG_REGISTRY` 495 → **498** · `PLAIN_HELP` 403 → **406** · `_CURATED_DEFAULTS_ON` 12 → **13** · `test_harness_flags.py` sigue en **0 failed** (de 59 a **60**: `test_declared_default_true_set` es paramétrico sobre el conjunto, así que verificar el conteo exacto tras la edición y anotarlo) · `test_harness_flags_help.py` sigue **exactamente** en `4 failed / 4 passed` · **el caso de discriminación ejecutado y fallando** con la entrada borrada, y revertido.

> **Mitad de contraste obligatoria de F1.b:** correr `test_harness_flags.py` **con `default=True` quitado** de `STACKY_WORKBENCH_ENABLED` pero la key ya en `_CURATED_DEFAULTS_ON`. **Tienen que fallar 2 casos** (`test_declared_default_true_set` y `test_default_known_only_for_curated`). Se revierte y se pega el fallo en el commit. Es la prueba de que se entendió C6 y no se copió la plantilla equivocada.
**Operador:** enciende las dos de escritura cuando quiera (§11.1). **Runtimes:** las flags son del backend; idénticas en los 3.

---

### F1 — El catálogo cerrado de verbos git

**Objetivo:** que sea **imposible** que este plan ejecute un verbo git que no sea de lectura.

**Archivo nuevo:** `backend/services/git_workbench.py` — `_VERBOS_PERMITIDOS`, `_run_git` (§5.2), con el mismo hardening de `services/console_repo.py:66-80` (lista de argumentos, `shell=False` implícito, `timeout`, `encoding="utf-8"`, `errors="replace"`, nunca lanza hacia afuera salvo el `ValueError` del catálogo).

**Test primero:** `backend/tests/test_plan293_catalogo_cerrado.py`
1. `_run_git(["status", ...])` no lanza.
2. `_run_git(["push"], ...)` lanza `ValueError`; ídem `reset`, `clean`, `checkout`, `branch`, `rebase`, `stash`, `commit`, `add`, `merge` (**10 casos**).
3. `_run_git([], ...)` lanza `ValueError` y el mensaje dice `<vacio>`.
4. **Censo por REFERENCIA** (no por AST del nombre: si la llamada va por alias, el AST cuenta cero): se lee el archivo y se exige que **toda** aparición de `subprocess.run` en `git_workbench.py` esté precedida por el guard — conteo de `subprocess.run` == conteo de llamadas a `_run_git` internas + 1.

**Mitad de contraste (obligatoria):** se borra la línea del guard, se corre, **tiene que fallar**, se revierte y se pega el fallo en el commit. Un gate que no se probó contra su defecto es un adorno.

**Criterio binario:** 13 casos passed; y con el guard borrado, ≥10 fallan.
**Flag:** ninguna (módulo sin consumidor todavía). **Operador: ninguno.** **Runtimes:** idéntico en los 3 (no hay runtime involucrado).

---

### F2 — Estado enriquecido del repositorio

**Objetivo:** entregar rama, upstream, adelante/atrás y archivos **con conflictos** en una sola pasada.

**Archivo:** `backend/services/git_workbench.py` — `repo_overview(workspace: Path) -> dict`.
- Resuelve el repo real con `rev-parse --show-toplevel` (**R11**: el `workspace_root` puede no ser la raíz).
- Corre `status --porcelain=v2 --branch` y parsea `# branch.head`, `# branch.upstream`, `# branch.ab +N -M`, y las líneas `1`/`2`/`u`/`?`.
- Las líneas `u` son **conflictos** (es lo que v2 entrega y v1 no distingue).
- Reusa `console_repo.resolve_known_workspace` para el allow-list; **no** reimplementa la validación.
- Degrada como `console_repo`: `{ok:True, available:False, reason:"..."}`, **nunca** lanza.

**Test:** `backend/tests/test_plan293_overview.py` — repo sin `.git`; `index.lock` presente; rama sin upstream; `+3 -0`; `+0 -2`; una línea `u` ⇒ aparece en `conflictos`; HEAD desprendido; salida vacía ⇒ 0 archivos; `workspace` no registrado ⇒ `None`. **9 casos.**

**Criterio binario:** 9 passed **y** un caso que corre `--porcelain=v1` sobre el mismo fixture y **comprueba que NO trae `branch.head`** — la mitad de contraste que prueba que el cambio de versión era necesario.
**Flag:** `STACKY_WORKBENCH_ENABLED` (**ON**), ya registrada en F1.b.
**Operador: ninguno.** **Runtimes:** igual en los 3.

---

### F2.b — **[ADICIÓN ARQUITECTO]** El semáforo de "¿es seguro publicar?", calculado en UN lugar

**Por qué existe esta fase (y por qué la v1 la necesitaba sin saberlo).** La v1 repartía las condiciones que impiden publicar por **cinco** lugares distintos: el banner de conflictos (F8/U4), el aviso de flag apagada (F9), el chequeo de tracker (U7), el de rama de GitLab (U8) y el de rama preexistente (U15, nuevo de la v2). Cinco dueños de la misma pregunta es **exactamente** el patrón que produce la pantalla que deja apretar *Publicar* y falla después — el defecto que `PipelineCopilotSection.tsx:246-256` ya documentó para el copiloto de pipelines (*"evita que el operador recorra los 8 pasos para chocarse al final"*). La v1 heredó esa **regla** pero no la **estructura** que la hace cumplible.

**Archivo:** `backend/services/git_workbench.py` — una función **pura**:

```python
def evaluar_publicacion(*, repo: dict, tracker_type: str, flags: dict, rama_libre: bool) -> dict:
    """{'puede': bool, 'bloqueos': [{'codigo','severidad'}], 'avisos': [...]}.
    NO decide textos: sólo códigos. El castellano lo pone F7."""
```

**Los 6 códigos de bloqueo, cerrados y enumerados:** `conflictos_presentes` · `sin_cambios` · `tracker_sin_propuestas` · `publicar_apagado` · `gitlab_rama_apagada` · `rama_ya_existe`. Y 2 de aviso: `local_quedara_modificado` (§3.3) · `sin_candado_optimista` (§3.4, sólo GitLab).

**Lo que compra:** `/overview` devuelve el veredicto ya calculado, así que **el paso 1 del asistente lo muestra completo** sin re-derivar nada; `/publish` lo **vuelve a evaluar en el servidor** antes de escribir (la UI nunca es la autoridad); y el botón *Publicar* se deshabilita con `puede === false` en un solo sitio. Sin esta función, la regla *"la degradación se avisa en el paso 1, no en el 5"* de F9 es una **buena intención sin mecanismo**: seis condiciones dispersas se avisan tarde por construcción.

**Test:** `backend/tests/test_plan293_semaforo.py` — un caso por código de bloqueo (6) · uno por aviso (2) · sin bloqueos ⇒ `puede=True` (1) · **bloqueos acumulables**: conflictos + flag apagada ⇒ los **dos** en la lista, no el primero que aparece (1) · el orden de `bloqueos` es **estable** (1). **11 casos.**

**Criterio binario:** 11 passed **y** la mitad de contraste: se le saca **un** código al `frozenset` de bloqueos ⇒ el caso de ese código **falla**. Además, un caso que asertea que `evaluar_publicacion` **no importa nada de `api/` ni de Flask** (es pura y testeable sin app).
**Flag:** ninguna (función pura sin consumidor todavía). **Operador: ninguno.** **Runtimes:** N/A.
**Dónde entra en el orden:** después de F2 y **antes** de F6/F8/F9, que la consumen.

---

### F3 — El agrupador deja de mentir sobre los conflictos

**Objetivo:** cerrar el defecto de §2.3.

**Archivo:** `frontend/src/services/consoleRepoPanel.ts` — se agrega el grupo `conflictos` y `renombrados` a `GroupedRepoFiles` (`:11-17`), y **el orden de evaluación pasa a ser: conflictos primero**. Se conserva `otros` como red de seguridad.

> ⚠️ **[C2 — la v1 pedía algo imposible.] El test existente NO se puede "sólo ampliar": hay que REESCRIBIR dos de sus casos.** Medido abriendo `frontend/src/services/__tests__/consoleRepoPanel.test.ts`:
> - **Caso 5 (`:34-39`)** se llama literalmente *"status desconocido cae en 'otros', nunca se pierde"* y usa **`status: "UU"`**, aserteando `g.otros == ["f.py"]`. F3 manda `UU` a `conflictos`: **este caso TIENE que fallar**, y su título además **miente** (`UU` no es desconocido, es un conflicto).
> - El mismo caso 5 cierra con `const total = g.modified + g.new + g.deleted + g.untracked + g.otros` y `expect(total).toBe(1)`: esa suma **enumera las 5 claves viejas a mano**, así que con `UU` en `conflictos` da **0** y falla por segunda razón.
> - **Caso 1 (`:9-16`)** se llama *"entrada vacía -> los 5 grupos vacíos"*: sigue verde (sólo verifica 5 de las 7), pero su **título queda desactualizado** y hay que corregirlo a **7**.
>
> **Por eso el criterio de la v1 ("pasa de N a N+14 y los casos previos siguen verdes") era mutuamente insatisfacible.** El criterio correcto está abajo.

**Test:** `frontend/src/services/__tests__/consoleRepoPanel.test.ts` — se **amplía Y se corrigen 2 casos**:
- **Reescribir el caso 5:** `UU` pasa a aserteear `g.conflictos`, el título pasa a *"UU es conflicto, no desconocido"*, y la suma `total` pasa a enumerar **las 7 claves**. Se agrega un caso 5.b con un status realmente desconocido (p. ej. `"XY"`) → `otros`, que es lo que el caso 5 **creía** estar probando.
- **Corregir el título del caso 1** a *"los 7 grupos vacíos"* y agregar las 2 claves nuevas a sus asserts.
- **Casos nuevos:** `AA`, `DD`, `UU`, `AU`, `UA`, `DU`, `UD` → `conflictos` (7); `R`/`RM` → `renombrados` (2); regresión de `??`, `M`, `A`, `D` (4); status desconocido `"XY"` → `otros` (1). **14 casos nuevos.**

**Consumidor de producción — NOMBRADO, no "grepear y ver" (C3/R14):** **`frontend/src/components/CodexConsoleFull.tsx:415-422`** construye `const groups: Array<[string, ...]>` enumerando **a mano** `["Modificados", grouped.modified] … ["Otros", grouped.otros]` — las 5 claves viejas. **Sin tocarlo, los archivos en conflicto y renombrados DESAPARECEN de la pantalla de Repositorio que hoy funciona** (hoy caen en "Otros" y **sí se ven**). Es una regresión visible, silenciosa para `tsc` y para todos los tests. **Se agregan las dos filas `["En conflicto", grouped.conflictos]` (primera, porque es lo urgente) y `["Renombrados", grouped.renombrados]` en el MISMO commit.** Es el único consumidor: verificado con `grep -rn "groupFilesByStatus" frontend/src` → 2 sitios de producción (`CodexConsoleFull.tsx:28` import, `:419` uso) + el test.

**Criterio binario:** el archivo de test pasa de **6** casos a **20** (6 − 0 borrados + 14 nuevos, con 2 reescritos), **0 fallidos**; `npx tsc --noEmit` limpio; **y un caso de texto que lee `CodexConsoleFull.tsx` y exige que las 7 claves de `GroupedRepoFiles` aparezcan en el array `groups`** — el gate de que el consumidor se actualizó.
**Mitad de contraste (obligatoria):** revertir sólo la edición de `CodexConsoleFull.tsx` ⇒ el caso de texto **tiene que fallar**. Un gate de consumidor que nunca falló no prueba nada.
**Flag:** ninguna (corrección de defecto). **Operador: ninguno.** **Runtimes:** N/A.

---

### F4 — Traer cambios, sin poder pisar nada

**Objetivo:** que el botón *"Traer cambios"* **traiga cambios de verdad** (§3.3).

**Archivo:** `backend/services/pre_run_git.py` — se agrega el parámetro `policy: str | None = None` a `run_pull_check`, y la línea 102 pasa a `policy = policy or config.STACKY_PRE_RUN_GIT_WORKSPACE_POLICY or "fetch_only_warn"`. **Retrocompatible**: los **CINCO** llamadores de producción **no pasan `policy` y no cambian de comportamiento** (la v1 decía "6" contando los tests; **son 5**, censados con `grep -rn "run_pull_check(" backend --include=*.py`):

| # | Llamador | Ruta **exacta desde `backend/`** |
|---|---|---|
| 1 | `run_pull_check(workspace_root, project=project_name, log=log)` | **`agent_runner.py:627`** — ojo: está en la **raíz** de `backend/`, **no** en `services/` |
| 2 | `run_pull_check(...)` | `api/diag.py:737` |
| 3 | `run_pull_check(workspace_root, log=log)` | `services/claude_code_cli_runner.py:3085` |
| 4 | `run_pull_check(workspace_root, log=log)` | `services/codex_cli_runner.py:1904` |
| 5 | `run_pull_check(...)` | `services/memory_validator.py:497` |

`merge --ff-only` es el **único** verbo de merge, y no puede perder trabajo: ante divergencia **falla**, no fusiona. Con la copia local sucia y la política bloqueante, `pre_run_git.py:171-174` corta antes de tocar nada (caso U14).

**Test:** `backend/tests/test_plan293_pull.py` — `policy=None` ⇒ lee config (2 casos: config en cada valor); `policy="ff_only_block_on_dirty"` con config en `fetch_only_warn` ⇒ **sí** entra al bloque de merge (`pre_run_git.py:231-232`); sucio + política bloqueante ⇒ `ok=False` y **cero** llamadas a `merge`; sin upstream ⇒ aviso y sin merge (el `and result.upstream` de `:231`); y **el caso de retrocompatibilidad, ahora ejecutable**: en vez de "correr los 6 llamadores" (que no es un test — la v1 contaba los tests como llamador), se verifica **por firma** con `inspect.signature(run_pull_check)` que `policy` tiene `default=None` y es **keyword-or-positional al final**, y se llama `run_pull_check` **sin** `policy` con la config en cada uno de los 2 valores comprobando que el resultado es idéntico al de antes. **7 casos.**

**Criterio binario:** 7 passed **y** `test_pre_run_git.py` (suite existente) mantiene exactamente su conteo de F0.
**Mitad de contraste:** poner `policy` **antes** de un parámetro existente en la firma ⇒ el caso de `inspect.signature` **falla**. Es lo que ataja que un modelo menor rompa a los 5 llamadores posicionales.
**Flag:** `STACKY_WORKBENCH_PULL_ENABLED` (**OFF**, excepción **(B)**), ya registrada y justificada en F1.b.
**Operador:** enciende la opción una vez si quiere el botón. **Runtimes:** el pull es del backend; idéntico en los 3.

---

### F5 — El renderizador de la descripción

**Objetivo:** meter en el único campo libre que hay (§2.4) todo lo que el pliego pide.

**Archivo:** `backend/services/change_proposal.py` — `build_description(...) -> str`. Secciones fijas y en este orden: **Qué cambié** (texto del usuario) · **Archivos incluidos** (lista con el grupo de cada uno) · **Archivos NO incluidos y por qué** · **Pruebas que hice** (checklist) · **Evidencia adjunta** · **⚠️ Revisar antes de integrar** (sospechas de secreto) · **Nota sobre el estado local** (§3.3, texto **obligatorio**).

**Test:** `backend/tests/test_plan293_description.py` — orden de secciones estable; sin evidencia ⇒ la sección no aparece; con sospechas ⇒ el bloque de aviso aparece **siempre**; la nota de estado local aparece **siempre** (caso que la busca literal); markdown sin inyección (un título con `#` no rompe la estructura); lista vacía de incluidos ⇒ error de validación. **8 casos.**

**Criterio binario:** 8 passed; y la **mitad de contraste**: se borra la línea de la nota de estado local ⇒ el caso que la exige **falla**.
**Flag:** ninguna (función pura sin efecto). **Operador: ninguno.** **Runtimes:** N/A.

---

### F6 — Publicar: previsualizar y ejecutar

**Objetivo:** el acto de publicar, con todo lo que hay que ver **antes**.

**Archivo:** `backend/services/change_proposal.py` — `preview(...)` (no escribe) y `publish(...)`.
`preview` calcula: **rama propuesta `stacky/trabajo-<AAAAMMDD-HHMMSS>-<4 hex>`** (el sufijo aleatorio es de la v2: §3.4-1, el timestamp al segundo colisiona), destino, incluidos, **excluidos con motivo** (binario / >1 MB / no-utf8, reusando el criterio de **`services/incident_dev_autocommit.py:227-244`** `_read_text_or_none` — v1 decía `:210-225`; el sitio que lo aplica es **`:156`**, v1 decía `:139`), sospechas de secreto (los **6 patrones de alta confianza** de `incident_dev_autocommit.py:41-48`, **importados, no reescritos**), el veredicto de **`evaluar_publicacion` (F2.b)** y la `description` de F5.
**`preview` llama `branch_exists(rama)` y si la rama existe REGENERA el nombre** (hasta 3 intentos; al tercero devuelve el bloqueo `rama_ya_existe`). Es la medida §3.4-2 contra el último-que-escribe-gana de GitLab.
`publish` **re-evalúa `evaluar_publicacion` en el servidor** (la UI no es la autoridad), recorre los incluidos con `commit_file`, sube evidencias, y crea la propuesta en **una** llamada con la `description` ya armada.

**Test:** `backend/tests/test_plan293_publish.py`, con dobles (**cero red**) — U9 excluido y con motivo; U10 sospecha listada; U11 >60 archivos rechazado (tope `_MAX_FILES = 60`, `incident_dev_autocommit.py:24`); U12 evidencia falla y la propuesta **igual se crea**; U13 reintento idempotente (`"unchanged"`); U7 tracker sin propuestas ⇒ error claro; `confirm` ausente ⇒ 400; orden **commits antes de crear la propuesta**; `link_attachment` **nunca** se llama (caso negativo explícito, §8); `redact_secrets` de `pr_review_sanitize` **nunca** se importa en este módulo (caso negativo, R5); **[v2] `branch_exists` devuelve True ⇒ el nombre cambia y `commit_file` recibe la rama NUEVA** (caso U15/R13); **[v2] `publish` con un bloqueo activo ⇒ `commit_file` recibe CERO llamadas** (la re-evaluación del servidor). **14 casos.**

**Criterio binario:** 14 passed, incluidos **los cuatro casos negativos** (`link_attachment`, `redact_secrets`, rama preexistente, bloqueo del servidor), **cada uno con su mitad de contraste ejecutada y el fallo pegado en el commit**. El de la rama preexistente es el que vigila R13: sin él, el plan vuelve a prometer una seguridad que no tiene.
**Flag:** `STACKY_WORKBENCH_PUBLISH_ENABLED` (**OFF**, excepción **(B)**), ya registrada y justificada en F1.b.
**Operador:** enciende la opción una vez. **Runtimes:** es backend + REST; idéntico en los 3.

---

### F7 — El diccionario de errores en castellano llano

**Objetivo:** que ningún mensaje técnico llegue crudo (K4).

**Archivo:** `frontend/src/services/workbenchErrors.ts` — `traducir(codigo: string): {titulo, queSignifica, queHacer}`. **Sin default mudo**: un código desconocido devuelve un texto genérico **útil** y se registra.

Entradas mínimas (**14**): los 4 de `console_repo` (§K4), `index.lock`, no-es-repo, sin-upstream, conflictos-presentes, rama-no-se-puede-crear-en-gitlab (**nombra la opción**), tracker-sin-propuestas, archivo-muy-grande, archivo-binario, sospecha-de-secreto, sin-cambios.

**Test:** `frontend/src/services/__tests__/workbenchErrors.test.ts` — un caso por entrada (14) + código desconocido (1) + **caso que exige que ninguna traducción contenga las palabras `git`, `commit`, `branch`, `HEAD`, `upstream`, `merge`, `porcelain`** (1). **16 casos.**

**Criterio binario:** 16 passed, y el caso anti-jerga **falla** si se agrega una entrada con jerga (mitad de contraste ejecutada).
**Flag:** ninguna. **Operador: ninguno.** **Runtimes:** N/A.

---

### F8 — La pantalla, con sus 13 patas

**Objetivo:** que el tab exista, se vea, y el enlace directo funcione.

**Las 13 patas, numeradas y con anclaje** (ninguna salvo 2 y 4 rompe la compilación; **las otras 11 fallan en silencio**):

| # | Archivo:línea | Qué se agrega |
|---|---|---|
| 1 | `frontend/src/services/routes.ts:5-9` | `\| "trabajo"` en `type Tab` |
| 2 | `frontend/src/services/routes.ts:15-23` | `trabajo: "/trabajo"` en `TAB_PATHS` (**tsc lo exige**) |
| 3 | `frontend/src/components/shell/shellNav.ts:5-9` | `\| "trabajo"` en `type ShellTab` (unión **duplicada a mano**) |
| 4 | `frontend/src/components/shell/shellNav.ts:16` | entrada en `TAB_META` (**tsc lo exige**) |
| 5 | `frontend/src/components/shell/shellIcons.ts:2-14` | importar un icono **nuevo** de lucide **y** agregarlo a `ICON_BY_NAME` (dos ediciones; olvidar la segunda es el fingerprint `docs/sistema/error_fingerprints.json:265`) |
| 6 | `frontend/src/components/shell/shellNav.ts:45` | agregar el tab al grupo cuyo `id` es `"trabajo"` (`SHELL_NAV_GROUPS[0]`, hoy `["team","tickets","incidencias","reuniones","review","unblocker"]`). **Sin esto el tab NO aparece y no hay error** |
| 7 | `frontend/src/components/shell/shellNav.ts:52-62` | `trabajoEnabled?: boolean` en `VisibilityInput` |
| 8 | `frontend/src/components/shell/shellNav.ts:70-86` | regla en `computeVisibleTabs` |
| 9 | `frontend/src/App.tsx:106-135` | `const [trabajoGate, setTrabajoGate] = useState<GateState>("unknown")` |
| 10 | `frontend/src/App.tsx:183-213` | `probeFlagHealth("/api/workbench/health")` |
| 11 | `frontend/src/App.tsx:339-378` | redirección con aviso si el gate está `"off"` |
| 12 | `frontend/src/App.tsx:380-396` | `trabajoEnabled: isGateOn(trabajoGate)` |
| 13 | `frontend/src/App.tsx:409-450` + import | montaje `{tab === "trabajo" && (isGateResolving(...) ? <Skeleton/> : isGateOn(...) && <WorkbenchPage/>)}` |

**Patas extra obligatorias:** nav v1 (`App.tsx:479-627`, sigue viva con literales JSX) y `NAV_COMMANDS` (`frontend/src/components/commandPaletteData.ts:84-101`).

**Tests existentes que se ponen rojos y hay que actualizar en el MISMO commit:** `shellNav.test.ts:11-16` (`ALL_TABS`, hoy **19**) y el **título literal** del caso `:19` (*"TAB_META cubre exactamente los 19 tabs"* → 20); `shellIconsCoverage.test.ts:10-11`; `plan273GateState.test.ts:23-31` (hace **grep de texto sobre `App.tsx`**); `plan282Censo.test.ts:59`.

**Regla no negociable:** usar **`isGateOn(...)`**, nunca `{trabajoGate && <X/>}` — `"off"` es **truthy** y el tab se mostraría apagado con `tsc` verde y cero tests rojos (`frontend/src/services/gateState.ts:43-47`).

> ⚠️ **Colisión de nombres detectada en la v2 — decisión de D6.** El `id` del **grupo** de la barra lateral ya es **`"trabajo"`** (`shellNav.ts:45`, label *"Trabajo"*). Ponerle `id: "trabajo"` al **tab** deja un tab *Trabajo* **dentro** del grupo *Trabajo*. `tsc` no se queja (`ShellTab` y `ShellNavGroup.id` son tipos distintos), pero en pantalla se lee raro y cualquier código futuro que mezcle los dos `id` se confunde en silencio. **Se resuelve en D6:** el `id` técnico del tab es **`"publicar"`** (ruta `/publicar`, `TAB_PATHS.publicar`) y su **label visible** sigue siendo **"Publicar mi trabajo"**. Un `id` distinto del `id` del grupo, y un rótulo que dice el verbo en vez del sustantivo — que es además lo que la persona no técnica busca. **Las 13 patas usan `publicar`, no `trabajo`.**

**Test:** `frontend/src/services/__tests__/plan293Patas.test.ts` — lee los archivos como texto y verifica **una aserción por pata** (13) + `tsc --noEmit` limpio + `shellNav.test.ts` actualizado a 20. **13 casos + 2 comandos.**

**Criterio binario:** 13 passed; `npx tsc --noEmit` sin errores; `shellNav.test.ts` verde con el nuevo conteo.
**Flag:** el tab se muestra según `STACKY_WORKBENCH_ENABLED` (ON). **Operador: ninguno.** **Runtimes:** N/A (es UI).

---

### F9 — El asistente de 5 pasos, y las evidencias

**Objetivo:** el flujo de §4.1, con la lógica **fuera** del `.tsx`.

**Archivos nuevos:** `frontend/src/services/publishWizardModel.ts` (**toda** la lógica: `type Paso`, `PASOS`, `pasoSiguiente`, `puedeAvanzar`, `resumenSeleccion`, `validarEvidencias`) y los `.tsx` cascarón de §5.3. Molde: `PipelineCopilotSection.tsx:35-38`.
**Backend:** `backend/services/work_evidence.py` + el endpoint `/evidence` con el guard de `content_length` (§6) y `sanitize_filename` **importado** de `incident_store`.

**Regla de UX heredada, obligatoria:** la degradación se avisa **en el paso 1, no en el 5** — `PipelineCopilotSection.tsx:246-256` documenta por qué: *"evita que el operador recorra los 8 pasos para chocarse al final"*. Si falta la flag de publicar, o el tracker no soporta propuestas, se dice en la primera pantalla.

**Test:** `frontend/src/services/__tests__/publishWizardModel.test.ts` — no se avanza de "Elegir" con 0 archivos; no se avanza de "Describir" sin título; con conflictos presentes **no se puede avanzar en absoluto**; evidencia que excede el tope se rechaza con motivo; el resumen cuenta bien por grupo; retroceder conserva lo cargado. **10 casos.** Backend: `backend/tests/test_plan293_evidence.py` — tope por archivo, tope total, extensión no permitida, nombre con `../` saneado, `content_length` excedido ⇒ **413 antes de leer**, y un caso que verifica que **nada se escribió fuera del directorio temporal**. **7 casos.**

> ⚠️ **`test_plan293_evidence.py` DEBE monkeypatchear `runtime_paths.data_dir()`**, además de setear `STACKY_DATA_DIR`. Es el único archivo de test de este plan que escribe en disco, y en todo el repo **sólo 3 archivos** hacen ese monkeypatch. Sin él, correr este test suelto **deja archivos reales en `backend/data/` del operador**. El molde vivo es `tests/test_plan291_guardia_repo.py`.

**Criterio binario:** 10 + 7 passed. El caso de `413` corre **antes** de leer el cuerpo, y el caso de aislamiento verifica que `backend/data/work_evidence/` **no existe** al terminar.
**Flag:** `STACKY_WORKBENCH_ENABLED` (ON) para ver; `STACKY_WORKBENCH_PUBLISH_ENABLED` (OFF) para ejecutar. **Operador: ninguno para ver.** **Runtimes:** N/A.

---

### F10 — Auditoría, paridad de runtimes, documentación y no-regresión

**Objetivo:** cerrar.

1. **Auditoría:** las 7 acciones de §7 emiten su fila de `system_logs`. Test: `backend/tests/test_plan293_auditoria.py` — una fila por acción, `context_json` **sin contenido de archivo** y **sin rutas absolutas**, y un caso que falla si alguna acción no emite. **8 casos.**
2. **Paridad de los 3 runtimes:** todo este plan es **backend + UI**; no invoca a Codex, Claude Code ni Copilot. La única superficie sensible es que el tablero **lee el árbol de trabajo que los tres runtimes modifican**. Test: con un árbol modificado por cada runtime (dobles), `repo_overview` devuelve lo mismo. **3 casos.** Fallback: si el runtime dejó el repo bloqueado (`index.lock`), el tablero degrada con el aviso de U5 en los tres.
3. **Documentación:** `docs/sistema/17-tablero-de-trabajo.md` nuevo + enlace desde `docs/sistema/INDEX.md`, con los pasos de activación, lo que **no** se puede prometer (§1.2) y las degradaciones por proveedor.
4. **Ratchets:** registrar los **9** archivos de test nuevos del backend (`catalogo_cerrado`, `flags`, `overview`, **`semaforo`**, `pull`, `description`, `publish`, `evidence`, `auditoria`) en los **DOS** ratchets, **en el mismo commit y con la misma cantidad en cada uno**: `.sh` **836 → 845**, `.ps1` **772 → 781**, brecha **64 → 64**.
   > ⚠️ **[C4] Los objetivos se expresan como `medido_en_F0 + 9`, y el literal es sólo informativo.** Los conteos se movieron **entre la v1 y la v2** (835/771 → **836/772**) porque la sesión paralela registró un archivo. **Si al implementar F0 midió otra cosa, el objetivo es ese número + 9, no 845/781.** Un implementador que se aferre al literal para en el número equivocado y deja un archivo **sin registrar**, poniendo rojo un test hoy verde.
   La brecha ya está **exactamente** en `_PS1_LAG_MAX = 64` (`tests/test_plan259_ratchet_script_parity.py:46`), así que registrar de más en uno solo pone rojo el gate al instante. Sintaxis **divergente**: `.sh` ruta pelada sin comillas ni coma; `.ps1` `"ruta",` entrecomillada — una ruta sin comillas en el `.ps1` **se pierde MUDA**. Sin rutas con espacios.
5. **No-regresión:** delta **cero** contra los baselines de F0 en todas las suites vecinas.

**Criterio binario:** 8 + 3 passed; `.sh` = **F0.sh + 9** y `.ps1` = **F0.ps1 + 9** medidos con **el comando de F0** (los mismos regex del test, `_SH_RE:26` / `_PS1_RE:28`), brecha **= 64**; **[C5] `test_harness_ratchet_meta.py` termina en 4 passed / 0 failed y `test_plan259_ratchet_script_parity.py` en 12 passed / 0 failed** — el criterio absoluto, porque **las dos suites están VERDES hoy** y `test_ratchet_clasifica_todos_los_tests` (`:43-52`) se pone rojo con **un solo** archivo sin registrar; delta cero contra F0.
**Mitad de contraste (obligatoria):** sacar **uno** de los 9 archivos del `.sh` ⇒ `test_el_ps1_no_pierde_terreno` o `test_ratchet_clasifica_todos_los_tests` **tiene que fallar**. Se revierte y se pega el fallo. Sin esto, el registro de ratchets es un trámite que nadie verificó.
**Flag:** ninguna nueva. **Operador: ninguno.** **Runtimes:** cubierto por el punto 2.

---

## 11. Estrategia de despliegue progresivo *(entregable 14)* y rollback

### 11.0. Los tres CORTES DESPLEGABLES *(nuevo en v2)*

La v1 tenía tres **anillos de flag** pero **una sola entrega**: las 12 fases had que aterrizar antes de que nada sirviera. Con 21 archivos nuevos y ~145 casos de test, eso es un plan que nadie termina de una sentada — y si se abandona a la mitad, **no queda nada usable**. Se parte en tres cortes, cada uno **desplegable, con valor propio y reversible por flag**:

| Corte | Fases | Qué le sirve al usuario el día que se mergea | Riesgo |
|---|---|---|---|
| **A — El tablero mira** | F0 · F1 · F1.b · F2 · **F2.b** · F3 · F7 · F8 | Ve su repo en castellano: rama, si está al día, archivos agrupados **con los conflictos bien clasificados**, diffs, errores llanos. **Ya arregla el defecto K3 del panel de Repositorio que existe hoy** | **Cero**: sólo lectura |
| **B — El tablero trae** | F4 | El botón *Traer cambios* que de verdad baja | Escribe en el árbol local; `ff-only` no puede perder trabajo |
| **C — El tablero publica** | F5 · F6 · F9 · F10 | El asistente de 5 pasos y la propuesta de cambio con evidencias | Escribe en el tracker real |

**El corte A es el que hay que defender:** entrega valor sin encender **ninguna** flag de escritura y **paga sola** la corrección de `groupFilesByStatus`, que hoy le miente al operador en una pantalla que ya usa. Si el plan se corta después de A, el repo queda **estrictamente mejor** que antes. F10 se corre al cierre de **cada** corte, no sólo al final (los ratchets son trampa de commit).

### 11.1. Tres anillos

| Anillo | Qué se enciende | Riesgo | Reversión |
|---|---|---|---|
| **1 — Mirar** | `STACKY_WORKBENCH_ENABLED` (**ON de fábrica**) | Ninguno: solo lectura | Apagar la opción |
| **2 — Traer** | `STACKY_WORKBENCH_PULL_ENABLED` (**OFF**) | Cambia archivos locales; `ff-only` no puede perder trabajo | Apagar. Lo ya traído no se deshace (se dice en pantalla) |
| **3 — Publicar** | `STACKY_WORKBENCH_PUBLISH_ENABLED` (**OFF**) | Escribe en el tracker real | Apagar. **Las ramas y propuestas creadas NO se borran** — eso es decisión del operador, a mano |

### 11.2. Rollback

Cada fase es un commit propio con pathspec explícito. El rollback de producto es **apagar la opción**: con las dos de escritura apagadas, **ningún byte** cambia respecto de antes del plan, y el tablero sigue sirviendo como panel de lectura. El rollback de código es revertir el commit de la fase; ninguna fase escribe esquema ni migra datos.

### 11.3. El humo con credenciales reales — **trabajo del operador, FUERA del alcance**

Ninguna fase automatiza esto y **ninguna lo usa como criterio**: elegir un proyecto GitLab, encender las opciones de los anillos 2 y 3, publicar una selección de 1 archivo, y verificar la rama, la propuesta `opened`, la descripción con sus secciones y que **no** esté mergeada ni aprobada. Recién ahí K5 pasa a ser medible.

---

## 12. Archivos *(entregables 15 y 16)*

**Nuevos (22).** Backend (4 de producto + **9** de test): `services/git_workbench.py`, `services/change_proposal.py`, `services/work_evidence.py`, `api/workbench.py`; `tests/test_plan293_{catalogo_cerrado,flags,overview,semaforo,pull,description,publish,evidence,auditoria}.py`. Frontend (2 de lógica pura + 6 de UI + 3 de test): `services/workbenchErrors.ts`, `services/publishWizardModel.ts`; `pages/WorkbenchPage.tsx`, `components/workbench/{WorkbenchHeader,WorkbenchFileList,WorkbenchDiff,PublishWizard,EvidenceDropzone}.tsx` + `.module.css`; `services/__tests__/{workbenchErrors,publishWizardModel,plan293Patas}.test.ts`. Docs: `docs/sistema/17-tablero-de-trabajo.md`.

**Existentes a modificar (18):** `backend/services/harness_flags.py` (**2 bloques**: `FLAG_REGISTRY` + `_CATEGORY_KEYS`), `backend/config.py` (3 flags), `backend/services/harness_flags_help.py` (`PLAIN_HELP`), `backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`, **sólo la flag ON, y su `FlagSpec` con `default=True`** — C6), `backend/scripts/run_harness_tests.sh`, `backend/scripts/run_harness_tests.ps1`, `backend/services/pre_run_git.py` (**un parámetro**), `backend/api/__init__.py` (import + registro), `frontend/src/services/consoleRepoPanel.ts` (F3), **`frontend/src/components/CodexConsoleFull.tsx` (F3 — C3/R14: el consumidor que la v1 NO listaba y que rompe en silencio)**, `frontend/src/services/__tests__/consoleRepoPanel.test.ts` (**2 casos REESCRITOS**, C2), `frontend/src/services/routes.ts`, `frontend/src/components/shell/shellNav.ts`, `frontend/src/components/shell/shellIcons.ts`, `frontend/src/App.tsx`, `frontend/src/components/commandPaletteData.ts`, `frontend/src/api/endpoints.ts`, `docs/sistema/INDEX.md`, y los tests de shell/gates que se ponen rojos.

> **Corrección v2 sobre los "4 tests que se ponen rojos":** se verificó abriéndolos. **`shellNav.test.ts`** (`ALL_TABS` `:11-16` + el título literal *"TAB_META cubre exactamente los 19 tabs"* `:19`) y **`shellIconsCoverage.test.ts`** (`:10-11`) **sí** hay que actualizarlos. **`plan273GateState.test.ts`** lee `App.tsx` como texto (`readFileSync` `:19`) y su const `GATES` (`:22-31`) enumera **7** gates de tab: agregar `trabajo` ahí es **opcional pero recomendado** (sin eso el gate nuevo no queda vigilado). **`plan282Censo.test.ts` probablemente NO hay que tocarlo**: su allowlist ya cubre `components/shell/shellNav.ts` (`:57-58`) y el censo cuenta **rótulos de tracker** (`ADO`/`GitLab`), no tabs — un tab llamado "Trabajo" no agrega ninguno. **Verificarlo corriéndolo, no asumirlo**; si sale verde sin tocarlo, se saca de esta lista.

> ⚠️ **`frontend/src/api/endpoints.ts` está SUCIO por la sesión paralela** (aparece modificado en `git status`). F8/F9 tocan ese archivo: commitear **solo con pathspec explícito** y nunca `add -A`.

---

## 13. Complejidad por fase *(entregable 17)*

| Fase | Complejidad | Por qué |
|---|---|---|
| F0 | **Baja** | Sólo medir y pegar |
| F1 | **Baja** | ~40 líneas + 13 casos |
| F1.b | **Media** | 7 archivos / 8 bloques, sintaxis divergente entre ratchets y la trampa de `_CURATED_DEFAULTS_ON` |
| F2 | **Media** | Parsear `porcelain=v2` es formato posicional; el riesgo está en los casos borde |
| **F2.b** | **Baja** | Función pura + 11 casos. **[ADICIÓN ARQUITECTO]** |
| F3 | **Media** *(era Baja en v1)* | Reordenar condiciones + 14 casos **+ REESCRIBIR 2 casos existentes (C2) + actualizar `CodexConsoleFull.tsx` (C3)**. La v1 la subestimó |
| F4 | **Baja** | Un parámetro. El trabajo real es no romper a los **5** llamadores |
| F5 | **Baja** | Función pura |
| F6 | **Alta** | Orquestación con dos providers asimétricos, idempotencia y 2 casos negativos |
| F7 | **Baja** | Diccionario + anti-jerga |
| F8 | **Media-alta** | 13 patas, 11 silenciosas, 4 tests ajenos a actualizar |
| F9 | **Alta** | Wizard + subida de archivos + topes |
| F10 | **Media** | Auditoría + los **dos** ratchets |

---

## 14. Fuera del MVP *(entregable 18)*

### 14.1. Mejoras posteriores (plan propio, sin decisión pendiente)
Historial de commits navegable · crear y cambiar de rama desde la UI · leer comentarios y aprobaciones de una propuesta (**no existen en el puerto**, §2.2-3) · estado de CI en vivo con reintento · diff lado a lado y resaltado de sintaxis · deshacer una selección con `UndoToastHost`.

### 14.2. Funcionalidades avanzadas
Resolución de conflictos asistida dentro de Stacky · `cherry-pick`/`revert` guiados · múltiples repos por proyecto (hoy el config admite **exactamente uno**, clave `workspace_root`) · plantillas de propuesta por proyecto · firma de commits.

### 14.3. Explícitamente descartado en este plan
`git push --force`, `reset`, `clean`, `rebase`, `stash`, borrado de ramas: **no entran ni detrás de una opción**. El pliego los prohíbe y §5.2 los hace inexpresables.

---

## 15. Decisiones que REQUIEREN al operador

| # | Decisión | Por qué no la toma el plan | Recomendación |
|---|---|---|---|
| **D1** | **Control de acceso por usuario / rol / cliente.** El pliego lo pide. **Stacky es mono-operador y no tiene autenticación**: `current_user` es una cabecera sin validar y un `403` significa *"opción apagada"*, no *"sin permiso"* | Construir RBAC acá sería **teatro de seguridad**: daría sensación de control sin control | **Honesto y suficiente hoy:** el control de acceso real es la **allow-list de carpetas** (`console_repo.resolve_known_workspace`) + el PAT del proyecto + la auditoría en `system_logs`. Si de verdad hace falta multiusuario, es **su propio plan**, con autenticación primero |
| **D2** | **M1 (REST) vs M2 (git local).** El MVP elige M1 (§3) y por eso **no hay `commit`/`push` locales**, y los archivos quedan modificados después de publicar | Es un cambio de modelo mental, no un detalle técnico | Empezar con M1. Si el operador confirma que necesita historia local, M2 es un plan aparte **con allowlist de verbos desde el día uno** |
| **D3** | **Encender los anillos 2 y 3.** Las dos flags de escritura nacen apagadas | Escriben en su disco y en su GitLab/ADO | Encenderlas después del humo de §11.3 |
| **D4** | **GitLab: `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED`.** Sin ella, publicar en GitLab falla porque no se puede crear la rama | Ya es una decisión suya de otro plan | Encenderla si el proyecto principal es GitLab. **Alcanza también al editor y al generador de pipelines** |
| **D5** | **Evidencias en ADO.** No se pueden embeber en la propuesta como en GitLab | Es un límite de la API, no una decisión de diseño | Aceptar la degradación declarada, o pedir un plan de adjuntos de PR para ADO |
| **D6** | **Nombre del tab.** La v1 proponía **"Trabajo"**, pero el `id` del **grupo** de la barra ya es `"trabajo"` (`shellNav.ts:45`): quedaba un tab *Trabajo* dentro del grupo *Trabajo*, y `tsc` no lo detecta | Es una decisión de producto **con una colisión técnica real detrás** | **`id: "publicar"`, ruta `/publicar`, label "Publicar mi trabajo".** Sin colisión, y el rótulo dice el **verbo** que la persona busca, no un sustantivo abstracto. Nunca "Git" |
| **D7** | **[v2] El candado optimista de GitLab.** `commit_file` no manda `last_commit_id` (§3.4): en GitLab, dos publicaciones concurrentes sobre la misma rama y archivo **se pisan**. Este plan lo cierra para su propio camino (rama nueva + `branch_exists`) pero **no** arregla la capa compartida | Arreglarlo cambia el contrato de `RepoWriter.commit_file`, que hoy usan **3 consumidores** (Dev Resolutor, editor, generador de pipelines): romperlo de costado sería peor que declararlo | **Aceptar la degradación declarada `git.commit.optimistic_lock` en el MVP.** Si el operador va a dar el tablero a **más de una persona** sobre GitLab, pedir el plan de `last_commit_id` **antes** de encender el anillo 3 |

---

## 16. Glosario, orden de implementación y DoD

### Glosario (para quien implemente)
- **Propuesta de cambio** — lo que git llama *Pull Request* (ADO) o *Merge Request* (GitLab). En toda la UI se dice así, en castellano.
- **Árbol de trabajo** — la carpeta con los archivos como están ahora en el disco.
- **`porcelain=v1` / `v2`** — dos formatos de salida de `git status`. v2 trae rama, upstream, adelante/atrás y conflictos; v1 **no**.
- **Mitad de contraste** — correr el test **contra el defecto** (rompiendo a propósito lo que vigila) para probar que **puede** fallar. Un gate que nunca falló es un adorno.
- **Criterio delta** — "esta suite pasa de N a N+k", nunca "0 fallidos en el repo": hay rojos de fábrica ajenos.
- **Las 13 patas** — los 13 lugares que hay que tocar para que un tab nuevo exista; 11 fallan en silencio.

### Orden de implementación *(reordenado en v2 para respetar los tres cortes de §11.0)*

**Corte A (desplegable, cero escritura):** 1. **F0** → 2. **F1** → 3. **F1.b** → 4. **F2** → 5. **F2.b** *(semáforo)* → 6. **F3** *(conflictos + el consumidor `CodexConsoleFull.tsx`)* → 7. **F7** *(errores)* → 8. **F8** *(las 13 patas)* → **F10 parcial** (ratchets + docs de lo hecho). **Acá se puede mergear y ya sirve.**
**Corte B:** 9. **F4** (pull).
**Corte C:** 10. **F5** (descripción) → 11. **F6** (publicar) → 12. **F9** (asistente + evidencias) → 13. **F10 completo** (auditoría, paridad, docs, ratchets).

> **Dependencias, cruzadas y verificadas:** F1.b va **antes** de F2/F4/F6 porque las tres consumen sus flags. **F2.b va antes de F6/F8/F9**, que consumen `evaluar_publicacion`. F5 va **antes** de F6 porque `publish` consume `build_description`. F8 va **antes** de F9 porque el asistente se monta dentro del tab. F3 y F7 son independientes y pueden adelantarse. **Ninguna fase tiene un criterio que dependa de algo que se construya después** — se re-cruzaron los criterios de las 13 fases en la v2 y la única contradicción encontrada (F3, C2) está corregida.
>
> **Los 9 archivos de test se registran en los dos ratchets a medida que nacen**, no todos juntos en F10: la brecha está en su límite exacto y acumular 9 registros pendientes hasta el final convierte cualquier commit intermedio en un commit que **no puede pasar el gate**. F10 sólo **verifica** los conteos finales.

### Definición de Hecho (global)
- [ ] Los 3 anillos de §11.1 existen, con las dos flags de escritura **apagadas de fábrica** y su excepción **(B)** citada por escrito, y la de lectura **encendida** y presente en `_CURATED_DEFAULTS_ON`.
- [ ] `K2 = 0` verbos destructivos, probado por el censo **por referencia** de F1 con su mitad de contraste ejecutada.
- [ ] `K3 = 0` conflictos mal clasificados (F3).
- [ ] `K4 = 0` mensajes crudos (F7), con el caso anti-jerga verde.
- [ ] Las **13 patas** de F8 verificadas una por una; `npx tsc --noEmit` limpio.
- [ ] Cero tablas nuevas, cero migraciones, **cero threads nuevos** (**`backend/app.py:641`** dice textual *"NO agregar threads nuevos"*; v1 decía `:635-636`).
- [ ] `FLAG_REGISTRY` 495 → **498**; `PLAIN_HELP` 403 → **406**; `_CURATED_DEFAULTS_ON` 12 → **13** **con `default=True` declarado en el `FlagSpec` de la flag ON** (C6); `test_harness_flags.py` en **0 failed**; `test_harness_flags_help.py` **exactamente** en `4 failed / 4 passed`.
- [ ] Los **9** archivos de test registrados en los **dos** ratchets: `.sh` = **F0.sh + 9**, `.ps1` = **F0.ps1 + 9** (referencia medida 2026-08-02: **836**/**772** ⇒ **845**/**781**), brecha **64**; y `test_harness_ratchet_meta.py` en **4 passed / 0 failed** (C4/C5).
- [ ] **R13 cerrado:** la rama lleva sufijo aleatorio, `preview` verifica `branch_exists` y **nunca** se publica sobre una rama preexistente, con su caso negativo y su mitad de contraste corrida.
- [ ] **R14 cerrado:** `CodexConsoleFull.tsx:415-422` muestra los 7 grupos; el caso de texto que lo vigila **falló** al revertir la edición.
- [ ] `test_plan293_evidence.py` monkeypatchea `data_dir()` y `backend/data/work_evidence/` **no existe** tras correrlo.
- [ ] Delta **cero** contra los **11** baselines de F0, **re-medidos con los comandos de F0 al empezar**.
- [ ] Los **tres cortes de §11.0** quedaron mergeables por separado; el corte A se puede mergear sin encender ninguna flag de escritura.
- [ ] `docs/sistema/17-tablero-de-trabajo.md` escrito, con lo que **no** se puede prometer.
- [ ] Un commit por fase, con pathspec explícito. **Sin push**, sin `--no-verify`, sin `amend`/`reset`/`rebase`/`stash`.
