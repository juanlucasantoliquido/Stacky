# Plan 293 — El trabajo se publica sin terminal: tablero de Git guiado para quien no sabe Git

**Estado:** **v3 — PARCIALMENTE IMPLEMENTADO.** Backend **COMPLETO y cableado**; frontend **a medias**. 2026-08-02, rama `docs/plan-279`, **sin push**.

## Estado de implementación por fase (2026-08-02)

| Fase | Estado | Commit | Evidencia **medida** |
|---|---|---|---|
| **F0** — baselines | ✅ **MEDIDA** | (en el cuerpo) | 13 valores re-medidos; brecha de ratchets **64 = `_PS1_LAG_MAX`**, holgura cero |
| **F1** — catálogo cerrado | ✅ **IMPL** | `9ef70c0e` + `c27b948b` | **54 passed**. Contraste: con el guard desactivado **26 fallan** |
| **F2** — las 3 opciones | ✅ **IMPL** | `84f93dd4` | **27 passed**. `FLAG_REGISTRY` 495→**498**, `PLAIN_HELP` 403→**406** |
| **F3** — estado enriquecido | ✅ **IMPL** | `88950066` + `c27b948b` | **45 passed** (junto con F4). `--porcelain=v2 --branch` |
| **F4** — el semáforo | ✅ **IMPL** | `88950066` + `c27b948b` | Contraste: devolver sólo el primer bloqueo pone rojo `test_30` |
| **F5** — conflictos (frontend) | ✅ **IMPL** | `106e7c1b` | **21 passed**, `tsc` limpio. Contraste **con inyección verificada**: 2 rojos |
| **F6** — elegir y confirmar | ✅ **IMPL** | `584bc4c6` | **15 passed**. **Contraste del riesgo #1**: con `add -A` + commit sin pathspec ⇒ **3 rojos** |
| **F7** — traer cambios | ✅ **IMPL** | `cab2852b` | **8 passed**; `test_pre_run_git` **5** (delta cero). Contraste: 2 rojos |
| **F8** — enviar | ✅ **IMPL** | `49b09eac` | **9 passed** contra un remoto `--bare` real |
| **F9** — ramas | ✅ **IMPL** | `d0916e99` | **22 passed** (junto con F10) |
| **F10** — historial | ✅ **IMPL** | `d0916e99` | idem |
| **F11** — propuesta REST + evidencias | ❌ **NO IMPLEMENTADA** | — | Ver §Pendientes |
| **F12** — diccionario de errores | ✅ **IMPL** | `fed80e7c` | **9 passed**. Contraste con inyección verificada: 3 rojos |
| **F13** — la pantalla (13 patas) | ⚠️ **PARCIAL: sólo el backend** | `4c5ca572` | **15 passed**. Las 9 rutas `/api/workbench/...` existen y responden. **Las 13 patas del tab NO están hechas** |
| **F14** — cierre | ⚠️ **PARCIAL** | — | Ratchets y no-regresión hechos; docs de sistema **no** escritas |

**Total propio: 195 tests de backend + 30 de frontend, todos verdes.**

### Pendientes reales, con nombre y apellido

1. **F11 completa** — `change_proposal.py` (descripción + `create_merge_request`) y `work_evidence.py` (subida de capturas). **Nada de esto existe todavía.**
2. **F13 frontend** — las **13 patas** del tab `publicar`, `WorkbenchPage.tsx` y el asistente de 5 pasos. Quedaron sin commitear `ReposGitPanel.tsx` y su `.module.css`, **incompletos y sin test**.
3. **F14** — `docs/sistema/17-tablero-de-trabajo.md` y el registro de la huella de regresión.
4. **Humo con credenciales reales** (§11.3): sigue siendo trabajo del operador y **no** es criterio de ninguna fase.

### Desvíos respecto del plan, medidos al implementar

1. **`git commit` SIN `user.email` NO falla.** Git deriva la identidad de usuario+máquina y guarda con exit 0. El plan preveía bloquear por la sonda `config --get user.email`; eso habría sido un **falso bloqueo permanente**. `identidad_derivada` pasó de bloqueo a **aviso**.
2. **Una fusión a medias hace IMPOSIBLE el commit por rutas** (`fatal: cannot do a partial commit during a merge`), y el `status` **deja de mostrarla** apenas el usuario resuelve el conflicto. Se agregó `operacion_en_curso`, que se detecta **por sistema de archivos** (`MERGE_HEAD`, `CHERRY_PICK_HEAD`, …), no por `status`.
3. **`git push origin +rama` es un force-push completo sin escribir `--force`**, y **`git switch -C`** resetea una rama existente destruyendo commits. Validar `push` por aridad no alcanzaba: se validan las **formas** de `push`, `switch` y `fetch`.
4. **Una pathspec de carpeta es RECURSIVA**: `commit -- sub` arrastra todo lo de abajo. Se rechazan carpetas; sólo archivos.
5. **La API no estaba en el plan como fase propia** y sin ella todo F1..F12 era **inalcanzable por HTTP** — el patrón "construido y jamás cableado". Se construyó `api/workbench.py` con 9 rutas.
**Juez v2: subagente independiente, misma corrida, contexto limpio.** El eje de publicación del v2 quedó **DEROGADO** por el operador; ver **CHANGELOG v2 → v3**.
**Fecha:** 2026-08-02
**Rama en la que se escribió:** `docs/plan-279`
**Alcance:** backend (`services/` + `api/`) y frontend (una pantalla nueva). **Cero migraciones de esquema. Cero escritura en la base del operador. Cero threads nuevos.**
**Depende de:** Plan 265 F4 (`services/console_repo.py`, el panel de repositorio de solo lectura), Plan 73 F4 (`services/repo_writer.py`, el puerto `RepoWriter`), Plan 110 (`services/merge_request_provider.py`, el puerto `MergeRequestProvider`), Plan 177/291 (`services/incident_dev_autocommit.py`, el auto-PR que ya publica por REST), Plan 175 F1 (`frontend/src/services/confirmGateway.ts`), Plan 273 (`frontend/src/services/gateState.ts`, el gate de tres estados), Plan 283 (`backend/api/meetings.py`, el molde de tab nuevo con `/health`).

> Todo número, ruta y línea de este documento se midió **abriendo el archivo o ejecutando el comando** el 2026-08-02 sobre `docs/plan-279`. Lo que **no** se pudo medir sin tocar el GitLab/ADO del operador está marcado **NO VERIFICABLE DESDE EL REPO** y **no se usa como criterio de aceptación**.

---

## CHANGELOG v2 → v3 — **el eje cambió: git LOCAL, no REST**

**Decisión D2 del operador:** el tablero opera con **git local sobre el working tree**. Las dos
variantes REST quedan **derogadas** como eje de publicación.

| Qué | v2 (derogado) | v3 |
|---|---|---|
| Commit | `RepoWriter.commit_file` (REST, un archivo por contenido) | **`git commit -F <msg> -- <pathspec>`** local |
| Push | no existía (el REST ya escribía en el remoto) | **`git push` local**, reusando la autenticación de `pre_run_git` |
| Ramas | rama creada por la API del tracker | **`git switch -c` / `git switch`** locales |
| Historial | fuera del MVP | **dentro** (F10) |
| Estado local tras publicar | quedaba sucio (§3.3 del v2, el "precio de M1") | **coherente**: es un commit local de verdad |
| PR / MR | REST | **sigue REST** — `create_merge_request` es el único camino, y no tiene equivalente en git |

**Lo que la decisión DISUELVE:**
- **C1 y §3.4 (candado optimista de GitLab)** dejan de ser el eje del riesgo de sobrescritura:
  git rechaza el **non-fast-forward** de fábrica. **D7 sigue vivo como deuda separada**, porque
  `commit_file` lo sigue usando el auto-PR, el editor y el generador de pipelines.
- **§3.3 (el precio de M1)** desaparece: ya no hay desfase entre lo local y lo publicado.

**Lo que la decisión AGRANDA (querido):** vuelven al MVP `commit`, `push`, `pull`, **crear y
cambiar de rama** e **historial** — los cuatro los pedía el pliego original **por nombre**.

**Lo que SIGUE afuera** (la decisión no lo cambia): leer comentarios y aprobaciones de PR (**no
existen en el puerto**, §2.2-3), conflictos asistidos, multi-repo por proyecto.

**Lo que NO se toca** (la decisión no lo alcanza): evidencias, checklist de pruebas, diccionario
de errores, auditoría por `SystemLog`, y **D1/RBAC** con su respuesta honesta.

**El riesgo #1 cambió de lugar y subió de categoría.** Ver **§3 nueva** y **R1**: correr git con
verbos de escritura sobre el repo real del operador, que **ahora mismo** tiene ~30 archivos
sucios de otras series y una **sesión paralela viva commiteando**. La promesa *"la pérdida de
trabajo es estructuralmente imposible"* **queda prohibida** salvo anclaje en un mecanismo
verificable; lo que este plan sí puede probar está en R1 y F6.

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

## 3. La arquitectura: git LOCAL, con catálogo cerrado — **y el riesgo #1 del plan**

> **Decisión D2 tomada por el operador.** El tablero opera sobre el **working tree real**.
> El único paso que sigue siendo REST es **abrir la propuesta de cambio**, porque
> *"abrir una PR" no tiene equivalente en git*. Es **híbrido a propósito**, no por omisión.

### 3.1. El reparto exacto

| Acción del usuario | Mecanismo | Verbo/función |
|---|---|---|
| Ver estado, rama, al día/atrasado, conflictos | git local, **lectura** | `status --porcelain=v2 --branch`, `rev-parse` |
| Ver diferencias de un archivo | git local, **lectura** | `diff --` (ya existe: `console_repo.repo_diff`) |
| Ver historial | git local, **lectura** | `log --format=... -n` |
| Listar ramas | git local, **lectura** | `for-each-ref` |
| Elegir archivos y **confirmar cambios** | git local, **escritura** | `add -- <pathspec>` + `commit -F <archivo> -- <pathspec>` |
| **Traer** cambios | git local, **escritura** | `fetch --prune` + `merge --ff-only` (ya existe: `run_pull_check`) |
| **Enviar** cambios | git local, **escritura** | `push <remote> <rama>` |
| Crear / cambiar de rama | git local, **escritura** | `switch -c <n>` / `switch <n>` |
| **Abrir la propuesta de cambio** | **REST** | `create_merge_request(source, target, title, description)` — 4 parámetros y nada más (§2.4) |

### 3.2. EL RIESGO #1 — correr git de escritura sobre un repo con trabajo ajeno vivo

**Esto no es un caso borde: es el estado normal de esta máquina.** Medido al escribir el v3:
el working tree tiene **~30 archivos modificados sin commitear** de las series 286·289·290·291·292
y del 287, y hay una **sesión paralela VIVA commiteando entre mis commits** que
`git worktree list` **no detecta** (se quedó con el número de plan 294 mientras yo escribía el 293).

Los dos modos de falla, concretos:

1. **Robo de trabajo ajeno.** Un botón *"Confirmar mis cambios"* que ejecute `git add -A` o
   `git add .` mete en el commit los ~30 archivos de otra serie y **los publica**.
2. **Destrucción de trabajo ajeno.** Un *"descartar cambios"* con `checkout --`, `reset --hard`
   o `clean -fd` **borra trabajo real de otro** sin recuperación.

**Las reglas del servicio de escritura — no negociables:**

- **ALLOWLIST de verbos, JAMÁS denylist.** El contraejemplo está medido dentro de este mismo repo:
  `services/doc_documenter.py:651` usa denylist `{"push","merge","stash"}` y **se olvidó de
  `branch`** ⇒ `git branch -D` (`:714`) llega al repo del operador por
  `POST /api/docs/documenter/decide`. El molde correcto es
  `services/night_foundry_workers.py:44-51`, que usa **allowlist** y **lanza `ValueError`**.
  Con denylist, olvidarse **abre** un agujero; con allowlist, olvidarse **cierra** una función y
  se ve en el acto.
- **Prohibidos y no expresables, ni detrás de flag:** `add -A`, `add .`, `stash`, `reset`,
  `checkout --`, `clean`, `commit --amend`, `rebase`, `push --force`/`-f`, `branch -D`, `filter-branch`.
- **Stage SIEMPRE por pathspec explícito**, únicamente sobre los archivos tildados en la UI.
- **`pull` sólo `--ff-only`** (ya era así).
- **La UI muestra los archivos NO seleccionados** y los deja intactos, sin insinuar que se incluyen.

**El mecanismo que lo hace cierto, no la buena intención:** el commit se arma como
`git commit -F <archivo-mensaje> -- <ruta1> <ruta2> …`. **La pathspec en el `commit` es lo que
salva**: git commitea *esas rutas* desde el working tree **sin importar qué haya en el índice**,
así que aunque la sesión paralela deje archivos suyos stageados, **no entran**. Los `??`
(sin seguimiento) sí necesitan un `add -- <ruta>` previo, porque git no los conoce.

> **Lo único que este plan puede prometer sobre pérdida de trabajo**, y está probado en F6:
> *"el commit contiene exactamente los archivos que tildaste, aunque haya trabajo ajeno sucio en
> la misma carpeta"*. **No** promete que sea imposible perder trabajo: `merge --ff-only` puede
> fallar, `push` puede ser rechazado, y ninguna de esas dos cosas es un daño — son negativas
> seguras. Lo que sí queda cerrado es que **ningún verbo de este plan puede destruir ni
> sobrescribir** trabajo no commiteado.

### 3.3. Autenticación del `push`, sin inventar un camino nuevo

Se **reusa exactamente** el mecanismo de `services/pre_run_git.py:248-311` `_run_git`, que ya
autentica operaciones de red no interactivas y ya está en producción:

- `-c credential.helper=` **siempre** (desactiva el gestor de credenciales aunque no haya PAT, así
  no cuelga esperando un prompt) y `-c core.longpaths=true` (rutas profundas en Windows).
- `-c http.extraheader=Authorization: <header>` sólo cuando hay PAT, resuelto por
  `_resolve_auth_header_for_project` (`:351-365`), que usa el PAT DPAPI del proyecto.
- Entorno: `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=Never`, `GIT_ASKPASS=""`, `SSH_ASKPASS=""`.
- **`_redact_command` (`:313-321`) enmascara el PAT** antes de que el comando llegue a un log o a
  la respuesta HTTP. **Ningún comando sin redactar sale del backend.**

### 3.4. El supuesto de capacidad que el cambio de eje NO disuelve

El botón *Traer cambios* lo sigue necesitando, y sigue siendo el más caro de este plan:

> **`run_pull_check` NO mergea con la configuración de fábrica, y `policy` no es un parámetro.**
> `services/pre_run_git.py:102` hace `policy = config.STACKY_PRE_RUN_GIT_WORKSPACE_POLICY or "fetch_only_warn"`. El bloque que mergea (`:231-240`) sólo corre `if policy == "ff_only_block_on_dirty"`. El default de fábrica es `"fetch_only_warn"` (`backend/config.py:865-866`).
> **Un plan que dijera "el botón *Traer cambios* reusa `run_pull_check`" entregaría un botón que hace `fetch` y no baja nada, en verde, sin que ningún test lo note.** F4 agrega el parámetro `policy` (retrocompatible, `None` → sigue leyendo config).

### 3.5. Concurrencia con git local: las tres barreras que git ya trae

El cambio de eje **mueve** el problema de concurrencia, no lo elimina. Con git local:

| Escenario | Qué pasa | Barrera |
|---|---|---|
| La sesión paralela tiene el índice tomado | `git` falla con `index.lock` | Ya detectado antes de correr nada (`console_repo.py:90-94`) y **se repite** en el escritor |
| Otro pusheó a la misma rama antes que yo | `push` **rechazado** por non-fast-forward | **Barrera de git, de fábrica.** No se fuerza nunca: `--force` no está en la allowlist |
| El remoto avanzó y mi copia quedó atrás | `merge --ff-only` **falla** en vez de fusionar | Ya era así (`pre_run_git.py:232`) |
| La sesión paralela dejó archivos suyos **stageados** | **No entran al commit** | La pathspec del `commit --` (§3.2) |

> **Lo que NO se arregla, dicho de frente:** si el usuario tilda un archivo y la sesión paralela
> lo modifica en ese mismo instante, se commitea **la versión del disco al momento del `commit`**,
> que puede no ser la que el usuario vio en el diff. Es una carrera inherente a trabajar sobre un
> working tree compartido y **ninguna herramienta la cierra sin bloquear la carpeta**. Se mitiga
> mostrando el `oid` corto de cada archivo en el paso de confirmación, y se **declara** en R15.

### 3.6. Dos capacidades que hay que verificar, no suponer

1. **`git commit` falla si el repo no tiene `user.name` / `user.email`.** No hay ningún lugar del
   backend que los configure ni los verifique (verificado: 0 hits de `user.email` en llamadas git
   de `backend/`, más allá de `memory_git_sync`). El error nativo de git es largo y en inglés. El
   tablero **sondea `config --get user.email` antes de ofrecer el botón** y, si falta, lo dice en
   castellano. **`config` entra a la allowlist SÓLO con la forma exacta `["config","--get",<clave>]`**
   — `git config <clave> <valor>` **escribe**, así que el verbo solo no alcanza: se valida la forma.
2. **La rama por defecto del remoto** no se puede suponer `main`. Se resuelve leyendo
   `origin/HEAD` con `rev-parse --abbrev-ref origin/HEAD` y, si no está, `main` y después `master`,
   **verificando existencia** con `for-each-ref`. Sin esto, la propuesta de cambio apunta a una
   rama destino inexistente y el REST falla con un error del proveedor.

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

**MEDIDO el 2026-08-02 con el comando de arriba.** Todos los criterios del plan son **delta** contra esto:

| Suite / métrica | Valor **medido** | Criterio |
|---|---|---|
| `tests/test_harness_flags.py` | **59 passed, 0 failed** — VERDE | **59 + N, 0 failed** |
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** — ROJO DE FÁBRICA | sigue **exactamente** en `4F/4P` |
| `tests/test_harness_flags_bounds.py` | **1 failed, 17 passed** — ROJO DE FÁBRICA | congelado (no hay flags numéricas) |
| `tests/test_harness_ratchet_meta.py` | **4 passed, 0 failed** — **VERDE** | **absoluto: 0 failed** |
| `tests/test_plan259_ratchet_script_parity.py` | **12 passed, 0 failed** — **VERDE** | **absoluto: 0 failed** |
| `tests/test_pre_run_git.py` | **5 passed** | **5 + N** |
| `tests/test_plan265_git_readonly.py` | **13 passed** | **13** (delta cero) |
| `tests/test_plan265_secret_mask.py` | **8 passed** | **8** (delta cero) |
| `frontend .../consoleRepoPanel.test.ts` | **6 passed** | pasa a **20** (F5) |
| `FLAG_REGISTRY` | **495** | **498** tras F2 |
| `PLAIN_HELP` | **403** | **406** tras F2 |
| Ratchet `.sh` / `.ps1` / brecha | **836 / 772 / 64** | `medido + 10` en **cada uno**, brecha **64** |
| `harness_ratchet_allowlist.txt` | **194** | sin cambio |

**Las tres trampas que estos baselines desactivan:**

1. **La brecha de ratchets está EXACTAMENTE en su límite** (`_PS1_LAG_MAX = 64`,
   `tests/test_plan259_ratchet_script_parity.py:46`). Registrar en uno y no en el otro pone rojo
   el gate **al instante**. Los **10** archivos nuevos van en los **dos**, en el mismo commit.
   Sintaxis **divergente**: `.sh` ruta pelada; `.ps1` `"ruta",` **entrecomillada** — sin comillas
   PowerShell la lee como nombre de comando y **la pierde muda**.
2. **Los 4 rojos de la ayuda llana son asserts de CONJUNTO**: omitir una entrada de `PLAIN_HELP`
   **no cambia** el `4 failed`. Un criterio "delta cero en el conteo" **no discrimina nada**.
   Por eso F2 exige archivo propio con **caso de discriminación**.
3. **Los ratchets están VERDES** (v1 creía que había un rojo de fábrica). Eso **endurece** el
   criterio: absoluto `0 failed`, no delta.

**Criterio binario:** los 13 valores se re-miden **antes de tocar código** y coinciden; si alguno
se movió (sesión paralela), se re-ancla y se anota el desvío.
**Flag:** ninguna. **Operador: ninguno.** **Runtimes:** N/A.

---

### F1 — El catálogo cerrado de verbos git *(el corazón de la seguridad — R1)*

**Objetivo:** que sea **imposible** que este plan ejecute un verbo git fuera de un conjunto cerrado,
y que las formas peligrosas de los verbos permitidos tampoco sean expresables.

> 🚨 **GUARDIÁN G1 — el que decide DÓNDE puede vivir este código.**
> `tests/test_plan265_git_readonly.py:228-238` (`test_11_barrido_de_escritura`) lee el **texto
> crudo** de **`backend/api/git.py`** y **`backend/services/console_repo.py`** y falla si aparece
> **como subcadena literal** cualquiera de 11 subcomandos entrecomillados
> (`"commit"`, `'add'`, `"push"`, `"checkout"`, `"reset"`, `"rm"`, `"merge"`, `"rebase"`,
> `"stash"`, `"clean"`, `"apply"`, y sus variantes con comilla simple — `:213-225`).
> **No es AST: es `if bad in text`.** No se puede escribir esa palabra ni en un comentario.
> **Consecuencia dura:** el escritor **NO puede vivir** en esos dos archivos, y el blueprint
> **NO puede ser `api/git.py`**. Por eso este plan crea `services/git_workbench.py`,
> `services/git_local_writer.py` y `api/workbench.py`. **Importar** `console_repo` desde ellos
> **sí está permitido** — el barrido mira el texto de esos dos archivos, no el de quien los usa.
> Los tests 1/2/3/10 del mismo archivo además exigen `subprocess.run` **cero veces** con entrada
> inválida o flag apagada, y el 9 exige lista de argumentos con `shell` falsy.

**Archivo nuevo:** `backend/services/git_workbench.py`

```python
_VERBOS_LECTURA = frozenset({"status","rev-parse","diff","for-each-ref","log","config","ls-files"})
_VERBOS_ESCRITURA = frozenset({"add","commit","switch","push","fetch","merge"})
_FORMAS_PROHIBIDAS = ("--force","-f","--hard","--amend","-A","--all","-D","--allow-empty")

def _validar(args): ...   # verbo en la allowlist Y forma permitida, o ValueError
def _run_git(args, cwd, *, escritura=False, auth_header=None, timeout=None): ...
```

**Reglas que valida `_validar`, cada una con su caso de test:**
1. Verbo vacío ⇒ `ValueError`.
2. Verbo fuera de `_VERBOS_LECTURA | _VERBOS_ESCRITURA` ⇒ `ValueError`.
3. Verbo de escritura pedido con `escritura=False` ⇒ `ValueError` (el camino de lectura **no puede** escribir).
4. Cualquier token en `_FORMAS_PROHIBIDAS` ⇒ `ValueError`, **en cualquier posición**.
5. `add` sin `--` ⇒ `ValueError`. `add` con `.` o sin rutas ⇒ `ValueError`.
6. `commit` sin `--` ⇒ `ValueError` (la pathspec es obligatoria, §3.2).
7. `config` que no tenga **exactamente** la forma `["config","--get",<clave>]` ⇒ `ValueError`
   (`git config <k> <v>` escribe).
8. `push` con más de `["push", <remote>, <rama>]` ⇒ `ValueError`.
9. `merge` que no sea exactamente `["merge","--ff-only", …]` ⇒ `ValueError`.
10. `switch` con `-f`/`--discard-changes` ⇒ `ValueError`.

`_run_git` copia el hardening probado: lista de argumentos (nunca string), `shell=False` implícito,
`timeout`, `encoding="utf-8"`, `errors="replace"`, `CREATE_NO_WINDOW`, y para escritura los
`-c credential.helper=` / `-c core.longpaths=true` / `http.extraheader` + env no interactivo de
`services/pre_run_git.py:248-311`, con **`_redact_command` reusado** para que el PAT no salga nunca.

**Test:** `backend/tests/test_plan293_catalogo.py` — un caso por regla (10) · los verbos prohibidos
uno por uno: `reset`, `clean`, `stash`, `rebase`, `checkout`, `branch`, `filter-branch`,
`cherry-pick` (8) · `push --force` y `push -f` (2) · `commit --amend` (1) · `add -A` y `add .` (2) ·
lectura feliz no lanza (1) · escritura feliz con `escritura=True` no lanza (1) ·
**censo por REFERENCIA**: `subprocess.run` aparece **una sola vez** en el módulo y está dentro de
`_run_git` (1). **26 casos.**

**Mitad de contraste (obligatoria):** se comenta la llamada a `_validar` dentro de `_run_git`,
se corre, **≥20 casos fallan**, se revierte.
**Criterio binario:** 26 passed; con `_validar` desactivado, ≥20 fallan.
**Flag:** ninguna (módulo sin consumidor). **Operador: ninguno.** **Runtimes:** N/A.

---

### F2 — Las tres opciones y sus ocho guardianes

**Son 7 archivos en 8 bloques** para una booleana `default OFF`:

| # | Archivo | Bloque |
|---|---|---|
| 1 | `backend/services/harness_flags.py` | `FLAG_REGISTRY` — `FlagSpec(...)`. **Con default OFF NO se declara `default=`** |
| 2 | `backend/services/harness_flags.py` | `_CATEGORY_KEYS` — categoría `capacidades_optin` |
| 3 | `backend/config.py` | `class Config` — `os.getenv(...)` |
| 4 | `backend/services/harness_flags_help.py` | `PLAIN_HELP` — `PlainHelp(what, on_effect, off_effect, example)` |
| 5 | `backend/scripts/run_harness_tests.sh` | ruta **pelada** |
| 6 | `backend/scripts/run_harness_tests.ps1` | `"ruta",` **entrecomillada** |
| 7 | `backend/tests/test_plan293_flags.py` | el guardián real |
| **8** | `backend/tests/test_harness_flags.py` | `_CURATED_DEFAULTS_ON` — **SÓLO** la flag ON |

> ⚠️ **`_CURATED_DEFAULTS_ON` son DOS ediciones acopladas**, no una: la key en el conjunto
> **y** `default=True` en su `FlagSpec`. `test_declared_default_true_set`
> (`tests/test_harness_flags.py:1196-1204`) exige `declared_default(spec) is True` para toda key
> curada, y `test_default_known_only_for_curated` (`:1207`) exige **igualdad exacta de conjuntos**.
> Hacer una sola de las dos ediciones pone rojos **dos tests distintos por razones distintas**.

> ⚠️ **`PLAIN_HELP`:** `what` 10-200 chars; `on_effect`/`off_effect` ≤ **240** y **ambos empiezan
> con `"Si "` — SIN TILDE**; `example` ≤ 300; prohibida la `JARGON_DENYLIST`
> (`tests/test_harness_flags_help.py:17-20`).

**Las tres flags:**

| Flag | Default | Justificación |
|---|---|---|
| `STACKY_WORKBENCH_ENABLED` | **ON** | **Solo lectura**: estado, diff, historial, ramas. Ninguna excepción aplica y el riel dice que lo de solo lectura **nunca** es excepción. Precedente: `STACKY_CONSOLE_REPO_PANEL_ENABLED` nace `"true"` (`backend/config.py:2622-2623`) |
| `STACKY_WORKBENCH_WRITE_ENABLED` | **OFF — excepción (B)** | Habilita `add`/`commit`/`switch` **sobre el working tree real del operador**: cambia el índice, la historia local y la rama activa de su disco. Precedente: `STACKY_PRE_RUN_GIT_PULL_ENABLED` nace `"false"` (`backend/config.py:859-860`) por tocar su árbol |
| `STACKY_WORKBENCH_PUSH_ENABLED` | **OFF — excepción (B)** | **Publica en el remoto real del operador** (`push`) y abre la propuesta de cambio en su GitLab/ADO. Precedente: `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` nace apagada por lo mismo |

> **Por qué `push` va en flag separada de `commit`:** un commit local es **reversible por el
> usuario** y no sale de su máquina; un push **es visible para todo el equipo**. Son dos niveles de
> compromiso distintos y el riel de partir la flag (ver/planear ON vs escribir OFF) pide separarlos.

**Test:** `backend/tests/test_plan293_flags.py`, acotado a **estas 3 keys** — las 3 en el registro (1) ·
`WORKBENCH_ENABLED` nace ON y las otras dos OFF (3) · las 3 en `config.py` (1) · ninguna declara
`requires` (1) · las 3 categorizadas (1) · las 3 con ayuda llana (1) · denylist respetada (1) ·
`"Si "` sin tilde (1) · `WORKBENCH_ENABLED` **está** en `_CURATED_DEFAULTS_ON` y las otras **no** (1) ·
`declared_default` de la ON es **True** (1) · **caso de discriminación**: se borra la entrada de
`PLAIN_HELP` de una de las 3 y el gate **se pone rojo** (1). **13 casos.**

**Criterio binario:** 13 passed · `FLAG_REGISTRY` 495→**498** · `PLAIN_HELP` 403→**406** ·
`test_harness_flags.py` de 59 a **59+**, **0 failed** · `test_harness_flags_help.py` **exactamente
4F/4P** · caso de discriminación **ejecutado y fallando**, y revertido.
**Operador:** enciende las dos de escritura cuando quiera. **Runtimes:** idénticas en los 3.

---

### F3 — Estado enriquecido del repositorio

**Objetivo:** rama, upstream, adelante/atrás y **conflictos**, en una pasada.

**Archivo:** `backend/services/git_workbench.py` — `repo_overview(workspace: Path) -> dict`.
- Resuelve el repo real con `rev-parse --show-toplevel` (**R11**: el `workspace_root` puede no ser la raíz).
- `status --porcelain=v2 --branch`; parsea `# branch.head`, `# branch.upstream`, `# branch.ab +N -M`
  y las líneas `1`/`2`/`u`/`?`. **Las `u` son conflictos** — v1 no las distingue.
- Reusa `console_repo.resolve_known_workspace` (allow-list) — **no** reimplementa la validación.
- Sonda `config --get user.email` (§3.6-1) y devuelve `identidad_ok: bool`.
- Degrada como `console_repo`: `{ok:True, available:False, reason:"..."}`, **nunca lanza**.

**Test:** `backend/tests/test_plan293_overview.py` — sin `.git`; `index.lock` presente; rama sin
upstream; `+3 -0`; `+0 -2`; línea `u` ⇒ `conflictos`; HEAD desprendido; salida vacía ⇒ 0 archivos;
workspace no registrado ⇒ `None`; `user.email` ausente ⇒ `identidad_ok=False`; rutas con espacios
(el `-z` no se usa: v2 no cita, así que se parsea por posición). **11 casos.**

**Criterio binario:** 11 passed **y** un caso que corre `--porcelain=v1` sobre el mismo fixture y
comprueba que **NO** trae `branch.head` — la mitad de contraste de por qué se cambió de versión.
**Flag:** `STACKY_WORKBENCH_ENABLED` (ON). **Operador: ninguno.** **Runtimes:** igual en los 3.

---

### F4 — El semáforo de "¿es seguro operar?", calculado en UN lugar

*(Heredado del v2 como `[ADICIÓN ARQUITECTO]`; los códigos cambian con el eje.)*

**Archivo:** `backend/services/git_workbench.py` — función **pura**:

```python
def evaluar_operacion(*, repo: dict, accion: str, flags: dict, seleccion: list[str]) -> dict:
    """{'puede': bool, 'bloqueos': [{'codigo','severidad'}], 'avisos': [...]}.
    NO decide textos: sólo códigos. El castellano lo pone F12."""
```

**Códigos de bloqueo, cerrados (8):** `conflictos_presentes` · `sin_cambios` · `nada_seleccionado` ·
`escritura_apagada` · `push_apagado` · `sin_identidad_git` · `repo_no_disponible` · `sin_upstream`.
**Avisos (3):** `hay_cambios_no_seleccionados` (§3.2, **el que evita el robo silencioso**) ·
`rama_sin_upstream` · `carrera_working_tree` (R15).

**Lo que compra:** `/overview` devuelve el veredicto ya calculado ⇒ el paso 1 del asistente lo
muestra **completo** sin re-derivar; cada endpoint de escritura lo **re-evalúa en el servidor**
antes de tocar nada (**la UI nunca es la autoridad**); y el botón se deshabilita en un solo sitio.

**Test:** `backend/tests/test_plan293_semaforo.py` — un caso por bloqueo (8) · uno por aviso (3) ·
sin bloqueos ⇒ `puede=True` (1) · **bloqueos acumulables** (1) · orden **estable** (1) · la función
**no importa nada de `api/` ni de Flask** (1). **15 casos.**

**Criterio binario:** 15 passed **y** la mitad de contraste: se saca **un** código del `frozenset`
⇒ el caso de ese código **falla**.
**Flag:** ninguna (pura). **Runtimes:** N/A.

---

### F5 — El agrupador deja de mentir sobre los conflictos

*(Sin cambios respecto del v2 — la decisión no lo toca. Se conserva íntegro, incluida la
advertencia C2/C3 sobre reescribir 2 casos y actualizar `CodexConsoleFull.tsx:415-422`.)*

**Archivo:** `frontend/src/services/consoleRepoPanel.ts` — se agregan `conflictos` y `renombrados`
a `GroupedRepoFiles`, y **el orden de evaluación pasa a ser: conflictos primero**.

**Criterio binario:** el test pasa de **6** a **20** casos, 0 fallidos; `npx tsc --noEmit` limpio; y
el caso de texto que exige que las **7** claves aparezcan en el array `groups` de
`CodexConsoleFull.tsx`. **Mitad de contraste:** revertir sólo esa edición ⇒ el caso **falla**.
**Flag:** ninguna. **Runtimes:** N/A.

---

### F6 — Elegir archivos y confirmar cambios *(EL RIESGO #1 — la fase más importante del plan)*

**Objetivo:** que el commit contenga **exactamente** los archivos tildados, con trabajo ajeno sucio
en la misma carpeta.

**Archivo nuevo:** `backend/services/git_local_writer.py`

```python
def confirmar_cambios(*, workspace, rutas: list[str], mensaje: str) -> dict:
    # 1. re-evaluar el semáforo en el servidor (F4). Si no puede -> return, sin tocar nada.
    # 2. validar CADA ruta con console_repo.resolve_safe_path -> descarta absolutas y '..'
    # 3. rechazar si .git/index.lock existe
    # 4. add SOLO de las rutas sin seguimiento:  ["add","--", *nuevas]
    # 5. mensaje a archivo temporal UTF-8 ->     ["commit","-F",<tmp>,"--", *rutas]
    # 6. devolver {ok, sha, archivos, no_incluidos}
```

**Por qué `-F` y no `-m`:** un mensaje con comillas, backticks o saltos de línea **rompe** el
armado por argumentos y en Windows es un camino de inyección. El repo ya pagó ese error con
`git commit -m` y backticks. El archivo temporal se borra siempre en `finally`.

**Por qué la pathspec en el `commit`:** es **la** barrera. `git commit -- <rutas>` commitea esas
rutas desde el working tree **sin importar el índice**, así que lo que la sesión paralela haya
stageado **no entra**.

**Test:** `backend/tests/test_plan293_commit.py`, sobre un **repo git de verdad creado en un
temporal** (no dobles: acá el comportamiento de git *es* lo que se prueba):

1. **EL CASO QUE JUSTIFICA LA FASE.** Repo con 5 archivos modificados; se seleccionan **2**; se
   hace `git add -A` **por fuera** para simular a la sesión paralela dejando todo stageado;
   `confirmar_cambios` con las 2 rutas ⇒ `git show --stat HEAD` lista **exactamente 2** archivos, y
   los otros 3 **siguen modificados y sin commitear**.
2. Un archivo **sin seguimiento** seleccionado ⇒ entra (se le hizo `add --` primero).
3. Un archivo sin seguimiento **NO** seleccionado ⇒ **no** entra y sigue sin seguimiento.
4. Ruta absoluta en la selección ⇒ rechazada, **cero** comandos git corridos.
5. Ruta con `..` ⇒ rechazada.
6. `index.lock` presente ⇒ `ok=False` con motivo, **cero** comandos.
7. Selección vacía ⇒ bloqueo `nada_seleccionado`, sin commit.
8. Mensaje con comillas, backticks y salto de línea ⇒ commitea y el mensaje llega **literal**
   (`git log -1 --format=%B`).
9. Sin `user.email` ⇒ `ok=False` con motivo en castellano, **sin** dejar el índice tocado.
10. Conflictos presentes ⇒ bloqueado.
11. El archivo temporal del mensaje **no existe** al terminar (ni en el camino de error).
12. **`add -A` nunca se ejecuta**: se espía la lista de comandos y se exige que ninguno contenga `-A`.

**Mitad de contraste (OBLIGATORIA, y es la del riesgo #1):** se cambia el paso 4 por
`["add","-A"]` y el paso 5 por `["commit","-F",tmp]` **sin pathspec**; se corre; **el caso 1 y el
caso 12 tienen que fallar**; se revierte y se pega el fallo en el commit. **Si el caso 1 no se
puede poner rojo, el gate es un adorno y la fase no está hecha.**

**Criterio binario:** 12 passed, y los casos 1 y 12 **demostrados rojos** con el defecto inyectado.
**Flag:** `STACKY_WORKBENCH_WRITE_ENABLED` (**OFF**, excepción **(B)**).
**Operador:** enciende la opción. **Runtimes:** backend; idéntico en los 3.

---

### F7 — Traer cambios *(pull `--ff-only`)*

**Archivo:** `backend/services/pre_run_git.py` — se agrega `policy: str | None = None` a
`run_pull_check`; la línea 102 pasa a `policy = policy or config.STACKY_… or "fetch_only_warn"`.
**Retrocompatible**: los **5** llamadores de producción (`agent_runner.py:627` —**en la raíz de
`backend/`, no en `services/`**—, `api/diag.py:737`, `services/claude_code_cli_runner.py:3085`,
`services/codex_cli_runner.py:1904`, `services/memory_validator.py:497`) no pasan `policy`.

**Test:** `backend/tests/test_plan293_pull.py` — `policy=None` lee config (2) · `policy` explícito
gana sobre la config (1) · sucio + política bloqueante ⇒ `ok=False` y **cero** `merge` (1) · sin
upstream ⇒ aviso y sin merge (1) · **retrocompatibilidad por firma** con `inspect.signature`:
`policy` tiene `default=None` y va **al final** (1) · llamada sin `policy` da idéntico resultado (1).
**7 casos.**

**Criterio binario:** 7 passed **y** `test_pre_run_git.py` sigue en **5 passed** (delta cero).
**Mitad de contraste:** poner `policy` **antes** de un parámetro existente ⇒ el caso de
`inspect.signature` **falla** (ataja que un modelo menor rompa a los 5 llamadores posicionales).
**Flag:** `STACKY_WORKBENCH_WRITE_ENABLED` (OFF). **Runtimes:** idéntico en los 3.

---

### F8 — Enviar cambios *(push, sin fuerza posible)*

**Archivo:** `backend/services/git_local_writer.py` — `enviar_cambios(*, workspace, rama) -> dict`.
- `["push", remote, rama]` y nada más. `--force`/`-f` **no son expresables** (F1, regla 4 y 8).
- Autenticación **reusada** de `pre_run_git` (§3.3); comando **redactado** con `_redact_command`
  antes de cualquier log o respuesta.
- Un rechazo por **non-fast-forward** **no es un error del tablero**: es la barrera funcionando.
  Se traduce a *"alguien más subió cambios antes que vos; traé los cambios y volvé a intentar"* (F12).
- Timeout de red: `STACKY_PRE_RUN_GIT_TIMEOUT_SECONDS` (**30 s** de fábrica, `backend/config.py:868`).

**Test:** `backend/tests/test_plan293_push.py` — push feliz contra un **remoto local de verdad**
(`git init --bare` en un temporal) (1) · non-fast-forward ⇒ `ok=False` con código
`push_rechazado`, **sin** reintento con fuerza (1) · el comando **jamás** contiene `--force`/`-f` (1) ·
el PAT **no aparece** en la respuesta ni en el comando devuelto (1) · sin upstream ⇒ se usa
`push <remote> <rama>` y funciona (1) · flag apagada ⇒ bloqueo `push_apagado`, **cero** comandos (1).
**6 casos.**

**Criterio binario:** 6 passed. **Mitad de contraste:** agregar `--force` al comando ⇒ el caso 3
falla **y** F1 lanza `ValueError` (doble red).
**Flag:** `STACKY_WORKBENCH_PUSH_ENABLED` (**OFF**, excepción **(B)**). **Runtimes:** idéntico en los 3.

---

### F9 — Ramas: listar, crear, cambiar

**Archivo:** `backend/services/git_workbench.py` (`listar_ramas`) y
`backend/services/git_local_writer.py` (`crear_rama`, `cambiar_rama`).
- Listar: `for-each-ref --format=... refs/heads` (lectura).
- Crear: `["switch","-c",<nombre>]`. Cambiar: `["switch",<nombre>]`.
- **`switch` sin `-f` se niega solo** si el cambio pisaría trabajo no commiteado. Esa negativa es
  **la barrera**, y se traduce a castellano en vez de forzarse.
- Validación del nombre: `^[A-Za-z0-9._/-]{1,100}$`, sin `..`, sin empezar con `-`, sin terminar en
  `.lock`. Un nombre inválido **no llega a git**.
- **`branch -D` no existe en este plan**: borrar ramas no está en la allowlist (F1).

**Test:** `backend/tests/test_plan293_ramas.py` — listar devuelve las ramas y marca la actual (1) ·
crear con nombre válido (1) · crear con nombre inválido ⇒ rechazado **sin llamar a git** (5 formas: `-x`, `a..b`, `x.lock`, vacío, 101 chars) · cambiar con árbol sucio que colisiona ⇒ `ok=False` traducido, **trabajo intacto** (1) · cambiar limpio (1) · **ningún comando contiene `-D` ni `-f`** (1). **10 casos.**

**Criterio binario:** 10 passed. **Mitad de contraste:** pasar `-f` a `switch` ⇒ F1 lanza.
**Flag:** `STACKY_WORKBENCH_WRITE_ENABLED` (OFF). **Runtimes:** N/A.

---

### F10 — Historial de commits

**Archivo:** `backend/services/git_workbench.py` — `historial(workspace, n=20) -> dict`.
`["log", f"-n{n}", "--format=%H%x1f%h%x1f%an%x1f%aI%x1f%s"]`, separador `\x1f` (**nunca** un carácter
que pueda aparecer en un asunto). `n` acotado a **1..100** en el servidor.

**Test:** `backend/tests/test_plan293_historial.py` — repo con 3 commits ⇒ 3 entradas en orden (1) ·
asunto con `|`, comillas y tildes ⇒ intacto (1) · repo sin commits ⇒ lista vacía, `available=True` (1) ·
`n` fuera de rango ⇒ acotado, no error (2) · campos completos (1). **6 casos.**

**Criterio binario:** 6 passed. **Flag:** `STACKY_WORKBENCH_ENABLED` (ON). **Runtimes:** N/A.

---

### F11 — La propuesta de cambio *(el único paso REST)* + descripción + evidencias

**Archivos:** `backend/services/change_proposal.py` (`build_description`, `abrir_propuesta`) y
`backend/services/work_evidence.py`.

- `build_description(...)`: **Qué cambié** · **Archivos incluidos** · **Pruebas que hice**
  (checklist) · **Evidencia adjunta** · **⚠️ Revisar antes de integrar** (sospechas de secreto,
  reusando los **6 patrones de alta confianza** de `services/incident_dev_autocommit.py:41-48`).
  **Ya no lleva** la "nota sobre el estado local" del v2: con git local **no hay desfase**.
- `abrir_propuesta(...)`: resuelve la rama destino (§3.6-2) y llama a
  `get_merge_request_provider(project).create_merge_request(source, target, title, description)`.
- Evidencias: se guardan en `runtime_paths.data_dir()/work_evidence/<id>/` con los topes ya
  probados de `services/incident_store.py:23-30` (10 archivos, 10 MB c/u, 25 MB total) y
  **`sanitize_filename` importado, no reescrito** (`:61-67`).
- GitLab: `upload_attachment` → se **embebe el `markdown`** en la `description` **al crearla**.
  **PROHIBIDO `link_attachment`** (`services/gitlab_provider.py:521-537`): si el GET previo falla
  asume `""` y **pisa la descripción entera**. ADO: **degradación declarada** (§5.4).

**Test:** `backend/tests/test_plan293_propuesta.py` — orden de secciones estable (1) · sin evidencia
la sección no aparece (1) · con sospechas el aviso aparece **siempre** (1) · markdown sin inyección (1) ·
rama destino resuelta por `origin/HEAD` y con los dos fallbacks (3) · `link_attachment` **nunca** se
llama (**caso negativo**) (1) · `pr_review_sanitize.redact_secrets` **nunca** se importa acá
(**caso negativo**, es camino de lectura y destruye código legítimo) (1) · falla la evidencia ⇒ la
propuesta **igual se crea** (1) · tracker sin propuestas ⇒ error claro (1). **11 casos.**
`backend/tests/test_plan293_evidence.py` — tope por archivo, tope total, extensión no permitida,
nombre con `../` saneado, `content_length` excedido ⇒ **413 antes de leer**, y aislamiento verificado.
**6 casos.**

> ⚠️ **`test_plan293_evidence.py` DEBE monkeypatchear `runtime_paths.data_dir()`.** Es el único test
> del plan que escribe en disco; sin el monkeypatch deja archivos reales en `backend/data/`.

**Criterio binario:** 11 + 6 passed, **con los dos casos negativos y su mitad de contraste**.
**Flag:** `STACKY_WORKBENCH_PUSH_ENABLED` (OFF, **(B)**). **Runtimes:** idéntico en los 3.

---

### F12 — El diccionario de errores en castellano llano

**Archivo:** `frontend/src/services/workbenchErrors.ts` — `traducir(codigo) -> {titulo, queSignifica, queHacer}`.
Sin default mudo. **Entradas mínimas (18):** los 4 de `console_repo` · `index.lock` · no-es-repo ·
sin-upstream · conflictos-presentes · **sin-identidad-git** · **push-rechazado (non-fast-forward)** ·
**cambio-de-rama-bloqueado** · nada-seleccionado · escritura-apagada · push-apagado ·
tracker-sin-propuestas · archivo-muy-grande · sospecha-de-secreto · sin-cambios.

**Test:** `frontend/src/services/__tests__/workbenchErrors.test.ts` — un caso por entrada (18) ·
código desconocido ⇒ texto genérico útil (1) · **caso anti-jerga**: ninguna traducción contiene
`git`, `commit`, `branch`, `HEAD`, `upstream`, `merge`, `porcelain`, `fast-forward`, `index` (1).
**20 casos.**

**Criterio binario:** 20 passed; el caso anti-jerga **falla** si se agrega una entrada con jerga
(mitad de contraste ejecutada). **Flag:** ninguna. **Runtimes:** N/A.

---

### F13 — La pantalla: las 13 patas, el asistente y las evidencias

*(Las 13 patas se conservan íntegras del v2 — la decisión no las toca. Ver la tabla de §F13.1.)*

**Nombre del tab:** `publicar`, ruta `/publicar`, label **"Publicar mi trabajo"**. **No** `trabajo`:
ese `id` **ya existe** como grupo de la barra lateral (`shellNav.ts:45`) y la colisión es invisible
para `tsc`.

**Lógica en `.ts` puro** (RTL/jsdom **no están instalados**: un `.test.tsx` con RTL reporta
*"no tests"* y sale **exit 0** — falso verde perfecto):
`frontend/src/services/publishWizardModel.ts` con `PASOS`, `pasoSiguiente`, `puedeAvanzar`,
`resumenSeleccion`, `validarEvidencias`.

**Regla de UX obligatoria:** la degradación se avisa **en el paso 1, no en el 5** — es lo que
compra F4. Y **los archivos NO seleccionados se muestran** en una lista aparte rotulada
*"No se van a incluir"* (R1: el usuario tiene que **ver** que existen y que quedan afuera).

**Test:** `plan293Patas.test.ts` (13 casos de texto, uno por pata) + `publishWizardModel.test.ts`
(10 casos) + `npx tsc --noEmit`.
**Criterio binario:** 23 passed; `tsc` limpio; `shellNav.test.ts` actualizado de 19 a **20** tabs.
**Flag:** `STACKY_WORKBENCH_ENABLED` (ON) para ver. **Runtimes:** N/A.

---

### F14 — Auditoría, paridad de runtimes, documentación y no-regresión

1. **Auditoría:** 9 acciones emiten su fila en `system_logs` vía
   `stacky_logger.info(source="git_workbench", action=...)`: `overview`, `diff`, `historial`,
   `ramas`, `commit_intento`, `commit_ok`, `commit_error`, `push`, `propuesta`.
   `context_json` **sin contenido de archivos y sin rutas absolutas**.
2. **Paridad de los 3 runtimes:** el plan no invoca a Codex, Claude Code ni Copilot; la superficie
   sensible es que **el tablero lee y escribe el mismo working tree que los tres modifican**.
   Test: con el árbol tocado por cada runtime (dobles), `repo_overview` devuelve lo mismo, y
   `confirmar_cambios` respeta la selección. **3 casos.** Fallback: `index.lock` ⇒ degrada igual en los 3.
3. **Docs:** `docs/sistema/17-tablero-de-trabajo.md` + enlace desde `INDEX.md`.
4. **Ratchets:** los **10** archivos de test nuevos en los **DOS** scripts, `medido + 10` en cada uno,
   brecha **64**. Se registran **a medida que nacen**, no todos al final: con holgura cero, acumular
   registros pendientes vuelve **imposible** que pase cualquier commit intermedio.
   ⚠️ **Hay un CUARTO guardián** que el v2 no nombraba: `tests/test_plan266_harness_runner_paridad.py`
   exige paridad `.sh`↔`.ps1` (`:65-66`) **y prohíbe la coma colgante** en el array del `.ps1`
   (`:42`). La **última** entrada del array va **sin coma** (referencia: `scripts/run_harness_tests.ps1:466`).
   Insertar en el medio, no al final, evita el problema.
5. **Guardián G3:** `tests/test_plan202_workers.py:37-55` corre git **contra este repo** y compara
   `status --porcelain` antes/después. Ningún módulo de este plan puede ser importado desde el
   planner o los workers de la Fragua.
5. **No-regresión:** delta **cero** contra los 13 baselines de F0.

**Criterio binario:** 8 + 3 passed; `.sh` = 846 y `.ps1` = 782 (medido + 10), brecha **64**; los dos
tests de ratchet en **0 failed**; delta cero en F0.

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
| **1 — Mirar** | `STACKY_WORKBENCH_ENABLED` (**ON de fábrica**) | Ninguno: solo lectura (estado, diff, historial, ramas) | Apagar la opción |
| **2 — Confirmar y traer** | `STACKY_WORKBENCH_WRITE_ENABLED` (**OFF**) | Toca el working tree y la historia **local**: `add`/`commit`/`switch`/`merge --ff-only`. Nada sale de la máquina | Apagar. Un commit local ya hecho **no se deshace solo** — se dice en pantalla. **Este plan no ofrece deshacer** porque deshacer es `reset`, y `reset` no está en la allowlist |
| **3 — Enviar** | `STACKY_WORKBENCH_PUSH_ENABLED` (**OFF**) | `push` al remoto real + abre la propuesta de cambio en su GitLab/ADO | Apagar. **Las ramas, commits y propuestas ya enviados NO se borran** — eso es decisión del operador, a mano |

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
Leer comentarios y aprobaciones de una propuesta (**no existen en el puerto**, §2.2-3) · estado de
CI en vivo con reintento · diff lado a lado y resaltado de sintaxis · `revert` guiado (§D8) ·
`last_commit_id` en `RepoWriter.commit_file` (§D7, toca 3 consumidores).

> **Historial** y **crear/cambiar de rama** ya **NO** están acá: la decisión D2 los devolvió al MVP
> (F10 y F9). El pliego original los pedía por nombre.

### 14.2. Funcionalidades avanzadas
Resolución de conflictos asistida dentro de Stacky · `cherry-pick`/`revert` guiados · múltiples repos por proyecto (hoy el config admite **exactamente uno**, clave `workspace_root`) · plantillas de propuesta por proyecto · firma de commits.

### 14.3. Explícitamente descartado en este plan
`git push --force`, `reset`, `clean`, `rebase`, `stash`, borrado de ramas: **no entran ni detrás de una opción**. El pliego los prohíbe y §5.2 los hace inexpresables.

---

## 15. Decisiones que REQUIEREN al operador

| # | Decisión | Por qué no la toma el plan | Recomendación |
|---|---|---|---|
| **D1** | **Control de acceso por usuario / rol / cliente.** El pliego lo pide. **Stacky es mono-operador y no tiene autenticación**: `current_user` es una cabecera sin validar y un `403` significa *"opción apagada"*, no *"sin permiso"* | Construir RBAC acá sería **teatro de seguridad**: daría sensación de control sin control | **Honesto y suficiente hoy:** el control de acceso real es la **allow-list de carpetas** (`console_repo.resolve_known_workspace`) + el PAT del proyecto + la auditoría en `system_logs`. Si de verdad hace falta multiusuario, es **su propio plan**, con autenticación primero |
| **D2** | ~~M1 (REST) vs M2 (git local)~~ — **RESUELTA POR EL OPERADOR: git local.** El eje REST del v2 queda derogado | — | **Cerrada.** El tablero usa git local para todo salvo abrir la propuesta de cambio, que no tiene equivalente en git |
| **D8** | **No hay "deshacer".** Deshacer un commit local es `reset`, y `reset` **no está ni puede estar** en la allowlist (R1). El pliego pedía *"permitir deshacer cuando técnicamente sea posible"* | Un `reset` alcanzable por HTTP sobre un repo con trabajo ajeno vivo es exactamente el modo de falla #2 de §3.2 | **Aceptar que no hay deshacer en el MVP** y decirlo en pantalla. Si se quiere, un plan aparte puede estudiar `revert` (que **crea** un commit nuevo y no destruye nada) — es el único verbo de deshacer que sería admisible |
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

### Orden de implementación *(v3 — reordenado por el cambio de eje, respetando los tres cortes)*

**Corte A (desplegable, CERO escritura):** **F0** → **F1** *(catálogo cerrado)* → **F2** *(las 3 opciones)* →
**F3** *(overview)* → **F4** *(semáforo)* → **F5** *(conflictos + el consumidor `CodexConsoleFull.tsx`)* →
**F10** *(historial)* → **F12** *(errores)* → **F13** *(las 13 patas)*. **Acá se puede mergear y ya sirve:**
el tablero muestra estado, diferencias, historial y ramas, sin poder escribir nada.
**Corte B (escritura local, nada sale de la máquina):** **F6** *(elegir y confirmar)* → **F7** *(traer)* → **F9** *(ramas)*.
**Corte C (sale al remoto):** **F8** *(enviar)* → **F11** *(propuesta + evidencias)* → **F14** *(cierre)*.

> **Dependencias, cruzadas y verificadas:** F1 va antes de todo lo que corra git. F2 va antes de
> F3/F6/F7/F8/F9, que consumen sus flags. F4 va antes de F6/F8/F9/F13, que re-evalúan el semáforo
> **en el servidor**. F13 va antes del asistente, que se monta dentro del tab. F5 y F12 son
> independientes. **Ninguna fase tiene un criterio que dependa de algo que se construya después**
> — se re-cruzaron los criterios de las 15 fases del v3.
>
> **Los 10 archivos de test se registran en los dos ratchets a medida que nacen.** La brecha está
> en su límite exacto (64 = `_PS1_LAG_MAX`); acumular registros pendientes vuelve **imposible** que
> pase cualquier commit intermedio. F14 sólo **verifica** los conteos finales.

### Definición de Hecho (global)
- [ ] Los 3 anillos de §11.1 existen, con las **dos** flags de escritura **apagadas de fábrica** y su excepción **(B)** citada por escrito, y la de lectura **encendida** y presente en `_CURATED_DEFAULTS_ON` **con `default=True` declarado en su `FlagSpec`** (las dos ediciones acopladas).
- [ ] **`K2 = 0` verbos destructivos**: `reset`, `clean`, `stash`, `rebase`, `checkout`, `branch`, `add -A`, `commit --amend`, `push --force` **no son expresables**, probado por los 26 casos de F1 **con la mitad de contraste ejecutada**.
- [ ] **EL GATE DEL RIESGO #1 (F6, caso 1) está VERDE y se demostró ROJO** con `add -A` + `commit` sin pathspec inyectados: con trabajo ajeno sucio y stageado en la misma carpeta, el commit contiene **exactamente** los archivos tildados.
- [ ] `K3 = 0` conflictos mal clasificados (F5), con `CodexConsoleFull.tsx` mostrando los **7** grupos y su caso de texto demostrado rojo al revertir.
- [ ] `K4 = 0` mensajes crudos (F12), con el caso anti-jerga verde y demostrado rojo.
- [ ] Las **13 patas** de F13 verificadas una por una; `npx tsc --noEmit` limpio; `shellNav.test.ts` de 19 a **20** tabs.
- [ ] El tab se llama **`publicar`**, no `trabajo` (colisión con el `id` del grupo de la barra).
- [ ] Cero tablas nuevas, cero migraciones, **cero threads nuevos** (**`backend/app.py:641`** dice textual *"NO agregar threads nuevos"*).
- [ ] `FLAG_REGISTRY` 495 → **498**; `PLAIN_HELP` 403 → **406**; `test_harness_flags.py` en **0 failed**; `test_harness_flags_help.py` **exactamente** en `4 failed / 4 passed`.
- [ ] Los **10** archivos de test registrados en los **dos** ratchets: `.sh` **836 + 10 = 846**, `.ps1` **772 + 10 = 782**, brecha **64**; `test_harness_ratchet_meta.py` y `test_plan259_ratchet_script_parity.py` en **0 failed** (criterio **absoluto**: están verdes); y **sin coma colgante** en el `.ps1` (`test_plan266_harness_runner_paridad.py:42`).
- [ ] **El escritor NO vive en `api/git.py` ni en `services/console_repo.py`** (guardián G1, barrido de texto literal), y `test_plan265_git_readonly.py` sigue en **13 passed**.
- [ ] `test_plan293_evidence.py` monkeypatchea `data_dir()` y `backend/data/work_evidence/` **no existe** tras correrlo.
- [ ] Delta **cero** contra los **13** baselines de F0, **re-medidos al empezar**.
- [ ] Los **tres cortes** quedaron mergeables por separado; el corte A se mergea sin encender ninguna flag de escritura.
- [ ] `docs/sistema/17-tablero-de-trabajo.md` escrito, con lo que **no** se puede prometer (incluido: **no hay deshacer**, §D8).
- [ ] Un commit por fase, con pathspec explícito. **Sin push**, sin `--no-verify`, sin `amend`/`reset`/`rebase`/`stash`.
