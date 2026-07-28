# Plan 259 — Alta de proyecto GitLab de primera clase + guía de configuración verificable (botón INFO)

**Estado:** CRITICADO — **v2 → v3** (juez independiente; v2 **RECHAZADO**, 7 bloqueantes)
**Serie:** Paridad multi-proveedor (65 → 218 → 249 → **259**). Cierra el último tramo que quedó a mitad de camino: el **alta**.
**Fuente:** pedido del operador ("al crear un nuevo proyecto debe de darme la opción de GitLab y un botón de INFO que podamos abrir y nos dé info muy detallada de cómo configurarlo exactamente"), **verificado contra el árbol de trabajo** en la rama `feat/plan-217-migrador-mantis-gitlab`.

> **Hallazgo central de la verificación:** GitLab está implementado en el motor (7 módulos `services/gitlab_*.py`, fábrica en `tracker_provider.py:130-148`, tipo declarado en `frontend/src/types.ts:245`) y **está ofrecido en el modal de EDICIÓN** (`EditProjectModal.tsx:449-452`) — pero **no existe en el modal de ALTA** y **el backend no sabe crearlo**. Peor: apretar ese botón de GitLab en Edición y guardar **convierte el proyecto en Azure DevOps en silencio**. El pedido del operador no es una feature nueva: es cerrar un agujero que hoy corrompe datos.

---

## CHANGELOG v2 → v3

Veredicto de la crítica sobre v2: **RECHAZADO** (7 hallazgos BLOQUEANTES). Juez **independiente**, en corrida aparte del arquitecto que escribió v2.

> **Método de esta pasada — se criticó EJECUTANDO, no leyendo.** Precedente de la casa: 4 de 4 críticas hechas releyendo volvieron RECHAZADAS por bloqueantes que solo aparecen corriendo, y hay casos donde el propio v2 introdujo bloqueantes invisibles a la lectura. Acá: cada anclaje se verificó con `grep`/`ast` contra el símbolo (los números de línea son orientativos, la verdad es el símbolo); el módulo `setup_guides.py` de F0 se **extrajo del plan, se escribió a disco y se corrieron contra él los 10 tests verificables que F0 propone** (los 10 en verde); el `.ps1` se pasó por el **parser real de PowerShell y además se evaluó en runtime**; el catálogo de huellas, el gate de ayuda llana y los 8 archivos de test del DoD se **corrieron de verdad** con `.venv\Scripts\python.exe` (py3.13.5) para medir el baseline en números. **6 de los 7 bloqueantes salieron de ejecutar, no de leer.**

**Bloqueantes NUEVOS (v3)**

- **B1 — La huella de F8 vuelve a romper el catálogo: `match` vs `matches`.** *(v2 introdujo este bloqueante al "arreglar" C3.)* El gate real, `tests/test_error_fingerprints_catalog.py::test_self_test_coherente`, lee `fp["self_test"]["matches"]` — **plural**. Las **42** huellas vivas del catálogo usan `matches`. La entrada de v2 escribe `"match"` (singular) ⇒ `KeyError: 'matches'`. Ejecutado: con `"match"` el gate explota; con `"matches"` pasa (el `log_pattern` y los samples de v2 son correctos, el error es **solo** la clave anidada). v2 acertó los 9 campos de primer nivel y erró el único campo anidado. F8 corregida.
- **B2 — La DoD exige VERDE en 3 gates que están ROJOS de fábrica.** Baseline medido corriendo, por archivo, 2 repeticiones idénticas (deterministas, sin `SQLITE_LOCKED`):
  | Gate que la DoD exige en verde | Baseline REAL medido |
  |---|---|
  | `tests/test_error_fingerprints_catalog.py` (F8 pide "los 8 en verde") | **3 failed / 5 passed** — la huella `PLAN239-OUTLET-EN-BLANCO` tiene `status:"guarded"` (fuera de `_STATUS_ENUM`) y **no tiene `self_test`** |
  | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` (F5 y F6 piden "en verde sin regenerar la línea base") | **1 failed / 2 passed** — `ExecutionDetailDrawer.module.css` 23 > 21 y `RunReconciliationCard.module.css` 1 > 0 |
  | `tests/test_harness_flags_help.py` (ni siquiera está en la DoD, y las 3 flags nuevas lo tocan) | **4 failed / 4 passed** |
  Verde real hoy: `test_harness_flags.py` 56 passed · `test_harness_ratchet_meta.py` 4 · `test_plan208_profile_schema.py` 10 · `test_plan218_gitlab_reachable.py` 13 · `test_plan70_smoke_gitlab.py` 5 · `test_harness_flags_requires.py` 9 · `npx tsc --noEmit` **0 errores**. La DoD de v3 distingue **"pasa"** (tests nuevos del plan) de **"no empeora contra el baseline numerado"** (gates rojos ajenos), y prohíbe arreglar rojo ajeno adentro de este plan.
- **B3 — El guardián de F9 es rojo por diseño: `initialize_azure_devops_project` no existe.** Ejecutado sobre `project_manager`: los helpers reales son `initialize_ado_project`, `initialize_jira_project`, `initialize_mantis_project`. v2 declara tabla de alias **solo** para `write_{t}_auth` y deja `initialize_{t}_project` sin alias ⇒ `test_cada_tracker_tiene_helper_de_alta` falla en `azure_devops` **antes** de llegar a GitLab. La [ADICIÓN ARQUITECTO] de v2 no podía pasar su propio criterio. F9 ahora declara **una sola** tabla `_ALIAS` que cubre las dos familias.
- **B4 — El `FakeRequests` que F4 prescribe rompe el manejo de excepciones.** `services/gitlab_setup_check.py` hace `except requests.RequestException`, y el test monkeypatchea el **símbolo** `requests` del módulo. Ejecutado: con un `FakeRequests` que no expone `RequestException`, los 4 escenarios de red del plan (instancia caída, token, scope, proyecto) mueren con `AttributeError: type object 'FakeRequests' has no attribute 'RequestException'` en vez de devolver `unknown`. F4 ahora congela el contrato mínimo del doble.
- **B5 — El bloque de 7 líneas de F8 deja el ratchet `.ps1` VACÍO, y parsea sin error.** El plan da la lista **una sola vez**, en sintaxis `.sh` (rutas peladas), y para el `.ps1` dice solo *"el equivalente Windows, misma lista"*. Ejecutado con el parser real (`[Parser]::ParseInput`) y evaluado en runtime: el `.ps1` actual parsea con **0 errores**, y con las 7 líneas peladas dentro de `@( )` **sigue dando 0 errores de parseo** pero el array evalúa a **`Count = 0`** — la lista se vacía en silencio. Con la sintaxis correcta (`"ruta",`) evalúa a `Count = N`. Es la misma clase de bug que la coma colgante que rompió el `.ps1` del plan 266. F8 ahora escribe las 7 líneas **dos veces**, una por sintaxis.
- **B6 — F1.0 manda escribir `initialize_gitlab_project` en el archivo equivocado.** v2 insertó la subsección `F1.0 — Template GitLab embebido`, cuyo único archivo nombrado es `services/client_profile_default_templates.py`, e inmediatamente después escribió *"Agregar al final del archivo, **antes** de `__all__`"* seguido del código de `project_manager.py`, **sin abrir subsección nueva**. Verificado ejecutando: ese archivo **no tiene `__all__`** (`'__all__' in src` → `False`). Un modelo menor mete el helper de alta en el archivo de templates. F1 partida en `F1.0` (templates) y `F1.a` (project_manager), cada una con su archivo en el encabezado.
- **B7 — `flags` no existe en `NewProjectModal.tsx`, y leerlo de `/api/diag/health` no compila.** F5.c punto 2 y F6.d condicionan el botón GitLab y el botón INFO a `flags.STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` / `flags.STACKY_SETUP_GUIDE_ENABLED` *"leído de `/api/diag/health`"*. Verificado: (a) el componente **no importa ningún mecanismo de flags** — sus únicos imports son `react`, `../api/endpoints`, `../types`, `./ui`, `../hooks/useOptimisticPending` y su CSS; (b) `HealthResponse` (`api/endpoints.ts:3290-3302`) tiene claves **fijas y sin index signature**, así que `flags.STACKY_...` **no compila** — y `npx tsc --noEmit` está hoy en **0 errores**, o sea que este plan lo rompería; (c) las 3 flags **no se emiten** en `/api/diag/health` (0 hits en código: solo existen dentro de este `.md`). Faltaban 4 piezas que v2 nunca nombró. Se agrega **F4.c** (el backend las emite) y **F5.0** (el hook + el tipo).

**Importantes NUEVOS (v3)**

- **B8 — `_project_to_dict` filtra el path de GitLab por `ado_project`.** `api/projects.py:96` hace `"ado_project": tracker.get("project", "")` **sin condicionar por tracker**. Para un proyecto GitLab, `issue_tracker.project` vale `acme/api` ⇒ el listado emite `ado_project:"acme/api"`, `EditProjectModal.tsx:25` lo semilla **incondicionalmente** en el form y `buildPayload()` lo reenvía en cada PATCH. v2 agrega los 4 campos `gitlab_*` condicionados pero deja esta fuga. Corregido en F2 Cambio 3.
- **B9 — `styles.btnInfo` no existe, y el CSS del modal está congelado.** Grep sobre **todo** `frontend/src`: **0 matches** de `btnInfo`. Y `uiDebtBaseline.json:41` congela `components/NewProjectModal.module.css` en **24** hex: agregar un color literal rompe `uiDebtRatchet` (que además ya está rojo, B2). F6.d ahora nombra la clase a crear y obliga a tokens de `theme.css`.
- **B10 — Las 3 flags nuevas no se cablean en `services/harness_flags_help.py`.** Regla de la casa: una flag toca varios lugares, y `test_harness_flags_help.py::test_plain_help_covers_all_registry_keys` exige cobertura **100 %** de `FLAG_REGISTRY`. F0.b de v2 toca 3 archivos y omite `harness_flags_help.py`. Atenuante medido: ese gate **ya está rojo** (79 flags sin ayuda, incluida `STACKY_PROVIDER_PARITY_ENABLED` del plan 218), así que no lo pone rojo — pero sí degrada, y el plan ni siquiera lo corre. F0.b agrega las 3 entradas `PLAIN_HELP` con las **5 restricciones reales** que el gate impone.
- **B11 — `api.post` lanza en non-2xx: el "rechazo explícito" de la flag OFF se ve como JSON crudo.** `Projects.init` usa `api.post`, que en `api/client.ts:206-209` hace `throw new Error(\`${status} ${statusText}: ${text}\`)`. La rama `else` de `handleSubmit` (`result.ok === false`) es **inalcanzable**: un 400 cae en el `catch` y el operador lee `400 BAD REQUEST: {"ok": false, "error": ...}`. F5 ahora extrae el mensaje.
- **B12 — `Dialog` anidado dentro de un overlay ad-hoc.** `NewProjectModal.tsx:253-254` es un overlay a mano (`styles.backdrop`/`styles.panel`), **no** usa `Dialog`. Montar `SetupGuideDialog` con el `Dialog` canónico **adentro** anida un portal: doble backdrop y doble `inert` sobre `#root` vía `openDialogCount`. F6.c fija dónde se monta.
- **B13 — `gitlab_client.py` no tiene `logger`.** Verificado: **0** ocurrencias de la cadena `logger` en el archivo. F3 afirma *"`json` y `logger` ya están disponibles"* y solo después lo matiza. Corregido a instrucción única.
- **B14 — F7.a mueve `_write_env` y el hot-apply DENTRO del `try/except ValueError`.** v2 dice "cero cambio funcional", pero hoy el `try` solo envuelve `apply_updates`: un `ValueError` de `_write_env` da **500** y con el fix daría **400**. Se acota el `try`.

**Menores (v3):** anclajes corridos con el símbolo verificado presente — `handleSubmit` está en `:225` (no `:229`), `rawPost` en `:47` (el `:88` del plan es su `return`), el bloque GitLab de Edición en `:695-753` y su campo de ruta en `:737-748` (no `:735-750`), el botón GitLab en `:447-453`, `_read_default_template` en `:88`, `_tracker_project_for` en `:90`, `get_project_credentials` en `:544`, `json.loads` en `:87`, `def update_project` en `:407`. Se marcan como orientativos en §2.

**[ADICIÓN ARQUITECTO v3] — F8.b, guardián de paridad `.sh` ↔ `.ps1` del ratchet.** El bloqueante B5 fue posible porque **nada guarda el `.ps1`**: verificado, `test_harness_ratchet_meta.py:19-21` parsea **solo** el `.sh`, y la única garantía del gemelo Windows es un comentario que dice *"Mantener en sync"*. Ya falló dos veces (plan 266 con una coma colgante que sí rompía el parser; este plan con comillas faltantes que **no** lo rompen y vacían el array en silencio). F8.b agrega un test que compara los dos archivos por conjunto de rutas y **rechaza específicamente la forma pelada dentro del `.ps1`** — el modo de falla exacto que ningún parser detecta. Es texto puro (`re` + `pathlib`), **no ejecuta PowerShell**, así que corre igual en los 3 runtimes y también fuera de Windows. Sin flag, sin trabajo del operador, sin tocar producto.

**Lo que v2 hizo BIEN y v3 conserva intacto** (verificado ejecutando, no por cortesía): E8 es exacto (`apply_updates` en `services/harness_flags.py:5709` dice textual *"No persiste ni aplica"*, y `put_harness_flags` en `api/harness_flags.py:118-176` hace los 3 pasos, con `logger` en `:19` y `_write_env` en `:32`) — la extracción `set_flag_values` de F7.a es correcta; E9 es exacto (`DEFAULT_TEMPLATES` tiene exactamente `['azure_devops','jira','mantis']`, sin `gitlab`, y `gitlab.json` difiere de `azure_devops.json` en 8 claves incluida `tracker_state_machine`); E11 es exacto (`read_secret_from_file` reescribe si `result.migrated`); los 4 guards de `ci_*` están en las líneas exactas que E6 cita; `set_encrypted_secret(payload, "token", token, format_field="token_format")` coincide byte por byte con la firma real; el `test_sin_jerga` determinista de v2 **pasa** contra su propia guía; y los 5 chequeos de F4 devuelven **siempre 5 resultados** en los 7 caminos de salida (trazado uno por uno).

---

## CHANGELOG v1 → v2

Veredicto de la crítica sobre v1: **RECHAZADO** (5 hallazgos BLOQUEANTES). Todos los fixes están aplicados abajo. Cada hallazgo se verificó leyendo el árbol, no infiriéndolo.

**Bloqueantes resueltos**

- **C1 — F7 no encendía nada (falso verde de manual).** `services/harness_flags.py:5699-5710` dice, textual, *"No persiste ni aplica (eso es responsabilidad del endpoint)"*: `apply_updates` **solo valida y castea**. El camino real vive en `api/harness_flags.py:118-175` (`apply_updates` → `_write_env` → `setattr(config, key, val)`). El `_enable_gitlab_engine` de v1 llamaba solo a `apply_updates` y sus 6 tests **espiaban esa llamada** ⇒ los 6 en verde con la funcionalidad muerta y el KPI "sincroniza al primer intento" clavado en 0 %. F7 reescrita: nuevo helper reusable `set_flag_values()` y tests que afirman **estado observable** (`config.config.STACKY_GITLAB_ENABLED is True` + línea en el `.env`), nunca una llamada espiada. Ver E8.
- **C2 — `NameError` que rompía el alta de ADO / Jira / Mantis.** `init_project` tiene **un solo `return`** compartido (`api/projects.py:383-384`); v1 asignaba `engine_result` solo dentro de la rama GitLab y decía que la respuesta "suma `gitlab_engine`". Implementado al pie de la letra ⇒ `NameError` en cada alta no-GitLab. F2/F7 ahora inicializan la variable antes de la cadena y escriben el `return` completo; test de no-regresión agregado.
- **C3 — La huella de F8 rompía un guardián y no huellaba el bug matado.** `tests/test_error_fingerprints_catalog.py:18` exige 9 campos (`id, title, class, status, log_pattern, log_guarded, killed_by, guard_test, self_test`); v1 proponía `id/pattern/meaning/fix` ⇒ `test_campos_obligatorios` **ROJO**. Además el patrón elegido era el mensaje del guard **preexistente** del plan 65, no el bug que este plan mata (la degradación a ADO **no escribe ninguna línea de log**: por eso es silenciosa). F8 reescrita con el esquema completo, `self_test` coherente y el patrón del rechazo **explícito** que introduce F2.
- **C4 — El plan introducía su propia degradación silenciosa sobre `gitlab_auth_file`.** `EditProjectModal.tsx:735-750` tiene un campo **"Ruta al archivo de token"** ligado a `gitlab_auth_file` (placeholder `C:\secrets\gitlab_token.txt`) y una nota que dice *"El archivo debe contener solo el token en texto plano"*. v1 hardcodeaba `auth_file="auth/gitlab_auth.json"` en el alta **y en el PATCH** ⇒ un guardado desde Edición **descartaba en silencio** la ruta que el operador tipeó, en el mismo modal que este plan viene a arreglar. F1/F2 ahora **preservan** el `auth_file` existente; F5.d corrige el campo y la nota (que además miente: `_load_token_from_file` hace `json.loads`, así que un `.txt` con el token pelado **nunca** funcionó) y agrega el campo Token que Edición no tenía. Ver E10.
- **C5 — La DoD era inalcanzable por contradicción interna.** `chk-flag` leía `config.config.STACKY_GITLAB_ENABLED`, que F7 recién enciende **al crear**; entonces "Verificar ahora" **siempre** daba rojo antes de crear, mientras la DoD exigía "con datos reales, los 5 en verde". F4 ahora distingue *encendido* de *declarado en el formulario* (tres estados, sin permitir que el cliente pinte un verde falso sobre el estado real) y la DoD dice la verdad.

**Importantes resueltos**

- **C6 — `client_profile` de un proyecto GitLab = el de Azure DevOps en el deploy congelado.** `services/client_profile_defaults/gitlab.json` existe (camino de dev), pero `services/client_profile_default_templates.py` **no tiene ninguna ocurrencia de "gitlab"** (solo `AZURE_DEVOPS:27`, `JIRA:114`, `MANTIS:192`), y su propio docstring avisa que en PyInstaller los `*.json` no se empaquetan ⇒ `_read_default_template` cae a `DEFAULT_TEMPLATES["azure_devops"]`. El `test_client_profile_sembrado` de v1 (`"client_profile" in cfg`) daba **verde en dev y perfil equivocado en el deploy**. F1 agrega el template embebido y el test verifica **cuál** perfil quedó, con el directorio de JSONs neutralizado.
- **C7 — F3 describía como lectura algo que ESCRIBE.** `read_secret_from_file` (`secrets_store.py:277-279`) reescribe el archivo cuando migra un secreto plano a DPAPI. Consecuencias no cubiertas por v1: un `gitlab_auth.json` **de solo lectura** pasaba de funcionar hoy a `TrackerConfigError`, y la migración a DPAPI ata el archivo a ese usuario de Windows. F3 documenta la migración, agrega fallback al lector plano de hoy y 2 tests nuevos.
- **C8 — Criterios de aceptación que espiaban llamadas en vez de estado.** Regla transversal nueva en §3.8: **todo criterio afirma estado observable** (archivo en disco, valor de `config.config`, cuerpo HTTP). Aplicada a F1, F3, F4, F7 y F8.
- **C9 — Contrato F5↔F7 sin definir.** `handleSubmit` hace `onCreated(...); onClose()` (`NewProjectModal.tsx:229-246`): el modal ya no existe cuando llegaría el mensaje de `gitlab_engine`. F7 y F5 ahora declaran quién lo pinta y dónde.
- **C10 — Doctrina de flags desactualizada.** v1 citaba "las 4 excepciones duras" y apoyaba el OFF de `STACKY_GITLAB_ENABLED` en *"prerequisito no garantizado"*, motivo que **el operador invalidó**. La regla vigente son **2 categorías**: **(A)** quema tokens en reposo, **(B)** escribe en un sistema real del operador / destruye datos / le saca la decisión. §3, §2-E6 y el glosario reescritos. Las 3 flags nuevas siguen ON (ninguna categoría aplica) y este plan sigue **sin tocar** el default preexistente de `STACKY_GITLAB_ENABLED` — pero ahora por la razón honesta: es un default heredado, fuera del alcance de este plan, y F7 lo vuelve irrelevante en el camino real.

**Menores resueltos:** anclajes corridos 1-2 líneas (§2, F5); `rawGet` devuelve `RawResponse<T>` y no el cuerpo (F6.a); comandos PowerShell con comillas escapadas frágiles y `cwd` implícito (F7, F8); regla ambigua de `test_sin_jerga_sin_explicar` (F0); `chk-instancia` daba verde ante un portal SSO que responde 401 (F4); el meta-ratchet solo parsea el `.sh` (F8).

**[ADICIÓN ARQUITECTO] — F9, guardián de paridad de trackers (AST).** Este plan existe porque un cuarto tracker quedó cableado a medias y nadie lo notó durante ~194 planes. F9 hace que esa clase de bug sea **imposible de reintroducir**: un test que recorre por AST las 4 piezas obligatorias de cada tracker (helper de alta, escritor de credencial, rama en `init_project` **y** en `update_project`, caso en `_has_credentials`, template embebido) más un property test que afirma que **ningún** tipo de tracker termina degradado a otro. Sin trabajo del operador, sin flag, y usando AST en vez de regex (gotcha de la casa).

---

## 1. Objetivo y KPI

Que crear un proyecto GitLab sea tan directo como crear uno de Azure DevOps, y que el operador **no tenga que adivinar ni buscar en ningún lado** cómo configurarlo: la propia pantalla se lo explica paso a paso y **verifica en vivo** cuál de los pasos falta.

| KPI | Hoy (medido en el árbol) | Meta |
|---|---|---|
| Trackers seleccionables al **crear** un proyecto | **3 de 4** (`NewProjectModal.tsx:373-393`: ADO, Jira, Mantis) | **4 de 4** |
| Proyectos GitLab creables vía `POST /api/init_project` | **0** — cae al `else # azure_devops` (`api/projects.py:360`) y responde `400 "organization requerida"` | **1 llamada, 200 OK** |
| `PATCH /api/projects/<n>` con `tracker_type="gitlab"` que **preserva** el tipo | **0 %** — reescribe `issue_tracker.type` a `azure_devops` (`api/projects.py:504-518`) | **100 %** |
| Campos GitLab devueltos por `GET /api/projects` | **0 de 4** (`_project_to_dict`, `api/projects.py:80-109`, no emite ninguno) | **4 de 4** |
| `_has_credentials` correcto para GitLab | **NO** — busca `mantis_auth.json` (`api/projects.py:69-77`) | **SÍ** (`gitlab_auth.json`) |
| Writer de credencial GitLab cifrada | **no existe** (`project_manager.py` tiene `write_ado_auth`/`write_jira_auth`/`write_mantis_auth`, no GitLab) | **existe, DPAPI, igual que los otros 3** |
| Pasos de configuración explicados dentro de la UI | **0** | **12 pasos** + **5 chequeos ejecutables** |
| Chequeos que el operador puede correr sin salir del modal | **0** | **5**, cada uno con el paso exacto que arregla el fallo |
| Proyecto GitLab recién creado que sincroniza al primer intento | **0 %** — `STACKY_GITLAB_ENABLED` nace en `false` (`config.py:1185`) y la fábrica tira `TrackerConfigError` | **100 %** (casilla "Activar el motor GitLab", tildada por default, visible y destildable) |
| *(v2)* `client_profile` correcto de un proyecto GitLab en el **ejecutable congelado** | **0 %** — hereda el de Azure DevOps: no hay template GitLab embebido (E9) | **100 %** |
| *(v2)* Ruta de credencial que el operador escribe en Edición y sobrevive al guardado | **n/a** (el PATCH degradaba el proyecto entero a ADO) — y con la F1 de v1 habría quedado en **0 %** | **100 %** |
| *(v2)* Trackers con las 6 piezas obligatorias verificadas por un test | **0 de 4** (no existe el guardián; por eso GitLab quedó a medias sin que nada avisara) | **4 de 4** (F9) |

---

## 2. Evidencia real (anclaje anti-alucinación)

Todo lo que sigue fue leído del árbol, no inferido.

> **Cómo leer los `archivo:línea` de este documento *(v3)*.** Los **símbolos** son la verdad y fueron verificados uno por uno con `grep`/`ast` contra el árbol en la rama `feat/plan-217-migrador-mantis-gitlab`; los **números de línea son orientativos** y se corren solos cuando una sesión paralela toca el archivo. Antes de editar, localizá el símbolo (`grep -n "<simbolo>" <archivo>`), no confíes en el número. Anclajes que en v2 estaban corridos y v3 corrige: `handleSubmit` está en `NewProjectModal.tsx:225` (v2 decía `:229`); `rawPost` en `api/client.ts:47` (el `:88` de v2 es su `return`); el bloque GitLab de Edición en `EditProjectModal.tsx:695-753` con su campo de ruta en `:737-748` (v2 decía `:695-750` y `:735-750`); el botón GitLab de Edición en `:447-453` (v2 decía `:449-452`); `_read_default_template` en `client_profile.py:88` (v2 decía `:102-116`); `_tracker_project_for` en `project_context.py:90` (v2 decía `:98`); `get_project_credentials` en `api/projects.py:544` (v2 decía `:543`); `json.loads` del lector GitLab en `gitlab_client.py:87` (v2 decía `:86`); `def update_project` en `api/projects.py:407` (v2 citaba el rango `:424-521`). **En los 9 casos el símbolo existe** — ninguno es una alucinación, todos son deriva de líneas.
>
> **Anclajes verificados EXACTOS** (sin corrimiento): `NewProjectModal.tsx` `EMPTY:13-38`, `buildPayload:79-85`, `validate:199-220`, `NP_FIELD_DOM_ORDER:223`, `trackerRow:372-394`, `isAdo/isJira/isMantis:248-250`; `types.ts` `TrackerType:245`, `InitProjectPayload:296-329` con su bloque GitLab en `:324-328`; `api/client.ts` `rawGet:96`; `api/projects.py` `_has_credentials:69-77`, `_project_to_dict:80-109`, `else # azure_devops:360`, `if tracker_type == "jira":290`; `config.py:1185-1187` (y el literal `"STACKY_GITLAB_ENABLED", "false"` **sí** aparece contiguo, o sea que el test de F7 funciona), `STACKY_CAPABILITY_DEGRADATION_ENABLED:1203`; `harness_flags.py` `apply_updates:5699` con su docstring en `:5709`, `_CATEGORY_KEYS["paridad_proveedores"]:478-484`; `api/harness_flags.py` `logger:19`, `_write_env:32`, `put_harness_flags:118`; `tracker_provider.py:130-136`; `ci_provider.py:121`, `ci_variables.py:82`, `ci_preflight.py:39`, `ci_logs_provider.py:38` (los 4 exactos); `test_harness_ratchet_meta.py` `_ALLOWLIST_MAX = 197`; `test_harness_flags.py` `_CURATED_DEFAULTS_ON:467`; `harness_flags_help.py` `plain_help_for:1915`.

### E1 — El alta no ofrece GitLab; la edición sí (y miente)

`frontend/src/components/NewProjectModal.tsx:372-394` — la fila de trackers tiene **exactamente tres** botones:

```tsx
<div className={styles.trackerRow}>
  <button ... onClick={() => setTrackerType("azure_devops")}>🔷 Azure DevOps</button>
  <button ... onClick={() => setTrackerType("jira")}>🔵 Jira</button>
  <button ... onClick={() => setTrackerType("mantis")}>🟢 Mantis BT</button>
</div>
```

`frontend/src/components/EditProjectModal.tsx:449-452` — el de edición tiene el cuarto:

```tsx
<button ... onClick={() => patch("tracker_type", "gitlab" as TrackerType)}>🦊 GitLab</button>
```

y sus campos en `:695-746` (`gitlab_url`, `gitlab_project`, `gitlab_group`, `gitlab_auth_file`).

### E2 — El backend no tiene rama GitLab: degradación silenciosa a ADO

`backend/api/projects.py:290-383` (`init_project`) ramifica `if tracker_type == "jira" / elif "mantis" / else: # azure_devops`. **No hay rama `gitlab`.** Con `tracker_type="gitlab"` cae al `else`, exige `organization` y responde `400`.

`backend/api/projects.py:424-521` (`update_project`) tiene la misma estructura. Con `tracker_type="gitlab"` cae al `else` y llama `initialize_ado_project(...)`, que escribe `{"type": "azure_devops", ...}` en `config.json` (`project_manager.py:294-299`). **El botón GitLab de la pantalla de edición es una trampa: convierte el proyecto a ADO sin avisar.**

### E3 — Falta el escritor de credencial

`backend/project_manager.py:628-648` (`__all__`) exporta `write_ado_auth`, `write_jira_auth`, `write_mantis_auth` e `initialize_ado_project`, `initialize_jira_project`, `initialize_mantis_project`. **No hay ninguna función `*_gitlab_*`.**

### E4 — El lector de token NO descifra

`backend/services/gitlab_client.py:75-93`:

```python
data = json.loads(path.read_text(encoding="utf-8"))
tok = str(data.get("token") or data.get("private_token") or "").strip()
```

Lee el campo **crudo**. Los otros trackers guardan cifrado con DPAPI (`set_encrypted_secret`, `secrets_store.py:191-201`) y leen con `read_secret_from_file` (`:258-280`). Si el alta escribiera el token con el mecanismo de la casa, **GitLab enviaría el criptograma como `PRIVATE-TOKEN` y daría 401**. Esta incompatibilidad hay que cerrarla en el mismo plan o el alta nace rota.

### E5 — La variable de entorno gana sobre el archivo del proyecto

`backend/services/gitlab_client.py:62-64`:

```python
token = os.getenv("GITLAB_TOKEN") or ""
if not token:
    token = self._load_token_from_file(auth_path)
```

Si `GITLAB_TOKEN` está en el entorno, **todos** los proyectos GitLab usan ese token y el archivo por proyecto se ignora. Es una trampa real que la guía tiene que decir con todas las letras (paso `gl-10-env-precedencia`).

### E6 — El motor GitLab nace apagado

`backend/config.py:1185-1187`: `STACKY_GITLAB_ENABLED` default `"false"`. `backend/services/tracker_provider.py:133-136` lanza `TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")`. Mismo guard en `ci_provider.py:121`, `ci_variables.py:82`, `ci_preflight.py:39`, `ci_logs_provider.py:38`.

Este plan **no cambia ese default**, por dos razones honestas: (1) es un default **preexistente** (plan 65), y moverlo es alcance de otro plan, no de éste; (2) F7 lo vuelve **irrelevante en el camino real** — se enciende en el mismo acto en el que el operador declara instancia y token. Lo que **sí** se corrige acá es la doctrina escrita: el comentario de `config.py:1191-1193` justifica el OFF por *"exige instancia GitLab + token, que no existen en una instalación limpia"*, es decir el motivo **"prerequisito no garantizado"**, que el operador **invalidó** expresamente (lo on-demand degrada sin romper). Ese motivo **no se propaga** en este plan: ninguna flag nueva lo usa (ver §3).

### E8 — `apply_updates` NO persiste ni aplica: el camino real es el endpoint

`backend/services/harness_flags.py:5699-5710`, docstring textual:

```
    No persiste ni aplica (eso es responsabilidad del endpoint).
```

Solo valida contra `_REGISTRY_INDEX` y castea. El camino que de verdad enciende una flag es `backend/api/harness_flags.py:118-175`, en tres pasos: `apply_updates(raw_updates)` → serializar a strings → `_write_env(env_strings)` (`api/harness_flags.py:32`, que además actualiza `os.environ` en `:63-68`) → hot-apply `setattr(config, key, val)` para las `env_only=False` (`:157-164`). **Cualquier "encender una flag desde código" que no haga los tres pasos es un no-op.** Esto invalidó la F7 de v1 y es la base del fix.

### E9 — No hay template GitLab embebido: en el deploy congelado el perfil es el de ADO

`backend/services/client_profile_defaults/gitlab.json` **existe** (los 4 archivos están: `azure_devops.json`, `gitlab.json`, `jira.json`, `mantis.json`). Pero `backend/services/client_profile_default_templates.py` **no contiene la cadena "gitlab" ni una vez**: define `AZURE_DEVOPS` (`:27`), `JIRA` (`:114`), `MANTIS` (`:192`) y arma `DEFAULT_TEMPLATES` (`:272`). Y `_read_default_template` (`client_profile.py:102-116`) resuelve así: primero el JSON en disco, y si no está, `DEFAULT_TEMPLATES.get(key) or DEFAULT_TEMPLATES["azure_devops"]`. El docstring del módulo dice, textual, que en el deploy congelado *"los `*.json` no se empaquetan, pero el módulo `.py` sí"*. **Conclusión: en dev el perfil GitLab es correcto y en el ejecutable es el de Azure DevOps.** `initialize_project:165-169` nunca explota — el riesgo R5 de v1 estaba mal diagnosticado.

### E10 — El modal de edición ya pide una ruta de token, y su nota es falsa

`frontend/src/components/EditProjectModal.tsx:735-750` renderiza el campo **"Ruta al archivo de token"** ligado a `gitlab_auth_file`, con placeholder `Ej: C:\secrets\gitlab_token.txt`, seguido de:

```
El archivo debe contener solo el token en texto plano (sin comillas ni saltos de línea extra).
```

Dos problemas verificados: (a) `gitlab_client._load_token_from_file` hace `json.loads(path.read_text(...))` (`gitlab_client.py:86`), así que **un `.txt` con el token pelado nunca funcionó** — la nota le pide al operador exactamente lo que rompe; (b) el modal de edición **no tiene campo de Token**, con lo cual convertir un proyecto a GitLab desde ahí no puede guardar credencial por el camino de la casa. Ambos se arreglan en F5.d. Y todo `initialize_gitlab_project` **debe preservar** el `auth_file` que ya tenga el proyecto: hardcodearlo sería repetir, con otro campo, la degradación silenciosa que este plan mata.

### E11 — `read_secret_from_file` ESCRIBE cuando migra

`backend/services/secrets_store.py:204-256` (`resolve_secret_in_payload`): si el campo está en texto plano, llama `set_encrypted_secret(...)` y marca `migrated=True`; `read_secret_from_file:277-279` entonces hace `write_json_file(path, payload)` y loguea *"Secretos legacy migrados a DPAPI"*. Es decir: la "lectura compatible hacia atrás" de F3 **reescribe el archivo del operador en el primer uso**. Hay que decirlo y hay que cubrir el caso de archivo no escribible.

### E7 — Lo que SÍ está resuelto (no reinventar)

- `project_context._auth_path_for` ya resuelve `auth/gitlab_auth.json` (`project_context.py:129-132`).
- `build_tracker_target` ya arma `project_path` / `base_url` / `group` / `auth_path` por proyecto (`project_context.py:232-273`).
- `GitLabTrackerProvider.__init__` ya acepta `base_url`, `group`, `auth_path` (`gitlab_provider.py:33-51`).
- `api/global_config.py:335-372` ya prueba conexión GitLab; **pero usa `GitLabClient`, que lee `GITLAB_TOKEN` del entorno primero (E5)** ⇒ no sirve para verificar lo que el operador acaba de tipear. Por eso F4 usa un camino HTTP propio y mínimo.
- Precedente exacto para el contenido de la guía: `backend/services/harness_flags_help.py` (módulo **puro**, dataclass congelada, `plain_help_for(key)` en `:1915-1925`, cobertura verificada por test centinela).

---

## 3. Principios y guardarraíles

1. **Paridad de los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro).** Nada de este plan invoca un LLM. La guía es **dato estático** y la verificación es **HTTP determinista**. Por construcción, los 3 runtimes ven byte por byte lo mismo. Cada fase declara igual su impacto y su fallback.
2. **Cero trabajo extra para el operador.** Todo nace **ON**. La única casilla nueva viene **tildada** y su efecto está escrito al lado. No hay archivo nuevo que editar a mano, no hay variable de entorno obligatoria.
3. **Human-in-the-loop innegociable.** El plan **no** crea proyectos solo, **no** apaga ni prende nada sin un clic, y **no** manda el token a ningún lado que no sea la instancia que el operador escribió en ese mismo formulario. Todos los chequeos son `GET` de **solo lectura**.
4. **Mono-operador, sin auth real.** Ni roles ni permisos: se reusa el modelo actual.
5. **No degradar.** Backward-compatible: los proyectos ADO/Jira/Mantis existentes no cambian ni un byte de su `config.json`; el lector de token GitLab sigue aceptando el formato plano de hoy — **con la migración a DPAPI declarada por escrito** (E11) y con fallback si el archivo no es escribible.
6. **Reusar.** `Dialog` canónico (plan 164), `Field/Input/Select/Checkbox` (plan 162), el camino de persistencia de flags de `api/harness_flags.py` (E8), `secrets_store`, el patrón de `harness_flags_help.py`, la categoría de flags `paridad_proveedores` (plan 218).
7. **Sin RTL/jsdom.** No están instalados (gotcha de la casa): **toda** lógica de UI testeable vive en módulos puros `.ts` bajo `frontend/src/projects/`, y el `.tsx` solo pinta.
8. **Estado observable, nunca llamadas espiadas.** *(nuevo en v2, hallazgo C8.)* Un criterio de aceptación afirma **lo que quedó**: el archivo en disco, el valor de `config.config`, el cuerpo HTTP, la línea del `.env`. Está **prohibido** que un criterio de aceptación se satisfaga con "se llamó a la función X" — así fue como la F7 de v1 se autocertificaba en verde sin hacer nada (E8). Un spy sirve como aserción **secundaria**, jamás como la única.

### Flags de este plan

La regla de la casa son **2 categorías de excepción** para que una flag nazca OFF: **(A)** quema tokens en **reposo** (loop/daemon/barrido/polling/prefetch que llama a un modelo sin que el operador pida nada); **(B)** **escribe en un sistema real** del operador, destruye datos o le saca la decisión. Nada más cuenta: ni "default seguro", ni "por las dudas", ni "prerequisito no garantizado" (motivo **invalidado** por el operador), ni ninguna capacidad de solo lectura.

| Flag | Tipo | Default | Categoría | Justificación del default |
|---|---|---|---|---|
| `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` | bool | **ON** | `paridad_proveedores` | Ni (A) ni (B). **No (A):** no hay loop ni llamada a modelo; solo corre cuando el operador aprieta "Crear e inicializar". **No (B):** escribe únicamente en la carpeta del propio Stacky (`backend/projects/<NOMBRE>/`), no toca ningún sistema del operador, y el token queda **cifrado** donde hoy no se guarda de ninguna forma. La decisión sigue siendo del operador: un clic explícito por proyecto. |
| `STACKY_SETUP_GUIDE_ENABLED` | bool | **ON** | `paridad_proveedores` | Ni (A) ni (B). Texto de solo lectura servido desde un módulo puro. Sin red, sin escritura, sin modelo. |
| `STACKY_SETUP_GUIDE_VERIFY_ENABLED` | bool | **ON** | `paridad_proveedores` | Ni (A) ni (B). 5 `GET` de solo lectura contra la URL que el operador escribió, disparados por su clic, sin redirecciones y sin persistir nada. Queda como kill-switch por si el operador quiere el panel sin salida de red. |

`STACKY_GITLAB_ENABLED` **no cambia su default en este plan**: es un default **preexistente** (plan 65) y moverlo es alcance de otro plan. F7 lo enciende en el acto de creación, que es el único momento en que importa. *(v2: se retira la apelación a "excepción dura #3" que traía v1 — ver E6 y C10.)*

---

## 4. Fases

> **Comando base backend** (desde `Stacky Agents/backend`, PowerShell):
> `.venv\Scripts\python.exe -m pytest tests/<archivo> -v`
> **Comando base frontend** (desde `Stacky Agents/frontend`):
> `npx vitest run src/__tests__/<archivo>`
> **Correr SIEMPRE por archivo** (gotcha de la casa: la corrida completa contamina cross-file, y `importlib.reload(config)` ensucia los tests de flag OFF).

---

### F0 — Registro puro de guías de configuración + flags

**Objetivo:** que el contenido de la guía exista como dato puro, testeable y sin IO, antes de que ninguna pantalla lo consuma.
**Valor:** el 100 % del texto que verá el operador queda bajo test; ningún runtime puede "redactarlo distinto".

**Archivos a CREAR:**
- `Stacky Agents/backend/services/setup_guides.py`
- `Stacky Agents/backend/tests/test_plan259_setup_guide_data.py`

**Archivos a EDITAR:**
- `Stacky Agents/backend/config.py`
- `Stacky Agents/backend/services/harness_flags.py`
- `Stacky Agents/backend/tests/test_harness_flags.py`

#### F0.a — `services/setup_guides.py` (NUEVO, PURO)

Sin `flask`, sin `config`, sin IO, sin red. Solo dataclasses + datos + 3 funciones de lookup. Mismo criterio que `harness_flags_help.py:1-11`.

```python
"""Plan 259 — Guías de configuración exactas por proveedor de tickets.

PURO: sin flask, sin config, sin IO, sin red. Datos + 3 funciones de lookup.
El contenido es el MISMO en Codex CLI, Claude Code CLI y GitHub Copilot Pro
porque no interviene ningún LLM: es una tabla.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideStep:
    id: str          # kebab-case estable; los checks lo referencian
    title: str       # ≤ 90 chars
    detail: str      # texto llano, puede tener varias frases
    where: str       # "gitlab" | "stacky" | "windows"
    trap: str = ""   # "" o la trampa concreta a evitar


@dataclass(frozen=True)
class GuideCheck:
    id: str          # "chk-*"
    title: str
    fixes_step: str  # DEBE ser el .id de un GuideStep de la misma guía


@dataclass(frozen=True)
class SetupGuide:
    provider: str          # "gitlab"
    display_name: str      # "GitLab"
    summary: str           # 1 párrafo
    required_fields: tuple[str, ...]
    steps: tuple[GuideStep, ...]
    checks: tuple[GuideCheck, ...]


GITLAB_GUIDE = SetupGuide(
    provider="gitlab",
    display_name="GitLab",
    summary=(
        "Stacky se conecta a GitLab por su API v4 con un token personal. Necesitás tres "
        "datos: la URL base de tu GitLab, el path del proyecto y un token con permiso de "
        "API. El token se guarda cifrado en tu equipo y nunca sale de acá salvo hacia tu "
        "propia instancia de GitLab."
    ),
    required_fields=("gitlab_url", "gitlab_project", "gitlab_token"),
    steps=(
        GuideStep(
            id="gl-01-instancia",
            title="1. Identificá la URL base de tu GitLab",
            detail=(
                "Si usás GitLab en la nube es https://gitlab.com . Si tu empresa tiene el "
                "suyo, es la raíz del sitio, por ejemplo https://gitlab.miempresa.com . "
                "Va SIN barra al final y SIN /api/v4 : eso lo agrega Stacky. "
                "Para confirmar, abrí <URL>/api/v4/version en el navegador: si te devuelve "
                "un JSON o un 401, la URL está bien; si te devuelve 404, está mal."
            ),
            where="gitlab",
            trap="Pegar la URL del proyecto en vez de la del sitio. La URL base NO incluye el nombre del grupo ni del proyecto.",
        ),
        GuideStep(
            id="gl-02-token",
            title="2. Creá un Personal Access Token con permiso 'api'",
            detail=(
                "En GitLab (versiones 16.x y 17.x): hacé clic en tu foto arriba a la derecha "
                "→ 'Edit profile' → en el menú de la izquierda 'Access tokens' → 'Add new token'. "
                "Ponele de nombre 'stacky-agents'. Elegí una fecha de vencimiento (GitLab obliga "
                "a poner una). En la lista de permisos ('scopes') marcá 'api'. "
                "Con 'read_api' Stacky solo puede LEER: no podría comentar el ticket, cambiar la "
                "etiqueta ni cerrarlo. Apretá 'Create' y COPIÁ el token en ese momento: GitLab no "
                "te lo vuelve a mostrar nunca más."
            ),
            where="gitlab",
            trap="Cerrar la pantalla sin copiar el token. Si pasa, no se puede recuperar: hay que crear otro.",
        ),
        GuideStep(
            id="gl-03-rol",
            title="3. Verificá que tu usuario tenga rol suficiente en el proyecto",
            detail=(
                "En el proyecto de GitLab: menú 'Manage' → 'Members'. Buscá tu usuario. "
                "Con rol 'Reporter' Stacky puede leer los tickets. Para comentar, cambiar "
                "etiquetas y cerrar, necesitás 'Developer' o superior. "
                "El token nunca te da más permisos de los que ya tenés vos."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-04-project-path",
            title="4. Anotá el path del proyecto",
            detail=(
                "Es lo que viene después del dominio en la URL del proyecto, sin https:// y "
                "sin la parte /-/algo. Ejemplo: si la URL es "
                "https://gitlab.com/acme/backend/api entonces el path es acme/backend/api . "
                "También se acepta el número de ID del proyecto, que figura en "
                "'Settings' → 'General', arriba de todo, como 'Project ID'. "
                "Las barras las codifica Stacky solo."
            ),
            where="gitlab",
            trap="Escribir solo el último tramo ('api'). Hay que poner el path completo con los grupos y subgrupos.",
        ),
        GuideStep(
            id="gl-05-issues",
            title="5. Confirmá que el proyecto tenga los Issues habilitados",
            detail=(
                "En el proyecto: 'Settings' → 'General' → 'Visibility, project features, "
                "permissions' → la perilla 'Issues' tiene que estar encendida. "
                "Si está apagada, GitLab responde 404 cuando Stacky pide la lista de tickets, "
                "aunque la URL y el token estén perfectos."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-06-grupo",
            title="6. (Opcional) Grupo, solo si vas a usar épicas nativas",
            detail=(
                "El campo 'Grupo' es únicamente para las épicas nativas de GitLab, que son una "
                "función de los planes Premium y Ultimate. Es el path del grupo raíz, por "
                "ejemplo 'acme'. Si lo dejás vacío, Stacky trabaja con issues comunes, que "
                "funcionan en todos los planes incluido el gratuito."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-07-stacky-alta",
            title="7. Cargá los datos en Stacky",
            detail=(
                "En Stacky: 'Nuevo Proyecto' → elegí el botón '🦊 GitLab' → completá "
                "Nombre interno, Workspace root, URL base (paso 1), Path del proyecto (paso 4) "
                "y pegá el Token (paso 2). El Grupo (paso 6) es opcional."
            ),
            where="stacky",
        ),
        GuideStep(
            id="gl-08-motor",
            title="8. Dejá tildada la casilla 'Activar el motor GitLab'",
            detail=(
                "Viene tildada. Enciende la perilla STACKY_GITLAB_ENABLED, que es el interruptor "
                "general del soporte GitLab y de fábrica viene apagada. Se enciende recién cuando "
                "apretás 'Crear e inicializar': hasta ese momento el control 'El motor GitLab está "
                "encendido' de 'Verificar ahora' te va a decir que está apagado y que se va a "
                "activar al crear. Si la destildás, el proyecto se crea igual pero cada "
                "sincronización va a fallar con el mensaje "
                "'issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false'. "
                "La podés prender o apagar después desde el panel de Configuración del arnés, "
                "categoría 'Paridad de proveedores'."
            ),
            where="stacky",
        ),
        GuideStep(
            id="gl-09-donde-queda",
            title="9. Dónde queda guardado el token",
            detail=(
                "En backend/projects/<NOMBRE>/auth/gitlab_auth.json , cifrado con DPAPI de "
                "Windows y atado a tu usuario de Windows. Ni Stacky ni nadie puede leerlo desde "
                "otro usuario o desde otra máquina. Si copiás la carpeta a otra PC, hay que "
                "volver a pegar el token. "
                "Si ya tenías un gitlab_auth.json viejo con el token sin cifrar, la primera vez "
                "que Stacky lo lea lo va a cifrar y a reescribir en ese mismo lugar: desde ahí "
                "queda atado a tu usuario de Windows igual que los demás."
            ),
            where="windows",
        ),
        GuideStep(
            id="gl-10-env-precedencia",
            title="10. Cuidado con la variable de entorno GITLAB_TOKEN",
            detail=(
                "Si en tu equipo existe la variable de entorno GITLAB_TOKEN, esa GANA sobre el "
                "token guardado por proyecto. Con dos proyectos GitLab distintos, los dos "
                "terminarían usando el mismo token y uno de los dos va a fallar. "
                "Recomendación: no definas GITLAB_TOKEN en el entorno y dejá que cada proyecto "
                "use el suyo."
            ),
            where="windows",
            trap="Un token viejo en el entorno hace fallar un token nuevo y correcto cargado por pantalla.",
        ),
        GuideStep(
            id="gl-11-ssl",
            title="11. Redes de empresa con certificado propio",
            detail=(
                "Si tu GitLab usa un certificado emitido por la autoridad certificante de la "
                "empresa, importá esa autoridad al almacén de certificados de Windows "
                "('Entidades de certificación raíz de confianza'). "
                "Stacky no ofrece 'desactivar la verificación SSL' para GitLab a propósito: "
                "sería mandar tu token por un canal que no se puede verificar."
            ),
            where="windows",
        ),
        GuideStep(
            id="gl-12-verificar",
            title="12. Verificá antes de crear",
            detail=(
                "Apretá 'Verificar ahora' en este mismo panel. Corre 5 controles de solo lectura "
                "contra tu GitLab y te dice exactamente cuál falla y qué paso de esta guía lo "
                "arregla. No crea ni modifica nada en GitLab."
            ),
            where="stacky",
        ),
    ),
    checks=(
        GuideCheck(id="chk-flag",      title="El motor GitLab está encendido",              fixes_step="gl-08-motor"),
        GuideCheck(id="chk-instancia", title="La URL responde y es un GitLab",              fixes_step="gl-01-instancia"),
        GuideCheck(id="chk-token",     title="El token es válido",                          fixes_step="gl-02-token"),
        GuideCheck(id="chk-scope",     title="El token tiene el permiso 'api'",              fixes_step="gl-02-token"),
        GuideCheck(id="chk-proyecto",  title="El proyecto existe y tiene Issues habilitado", fixes_step="gl-04-project-path"),
    ),
)


SETUP_GUIDES: dict[str, SetupGuide] = {"gitlab": GITLAB_GUIDE}


def guide_exists(provider: str) -> bool:
    return (provider or "").strip().lower() in SETUP_GUIDES


def guide_for(provider: str) -> SetupGuide | None:
    return SETUP_GUIDES.get((provider or "").strip().lower())


def guide_as_dict(provider: str) -> dict | None:
    """Serializa la guía para la API. None si el proveedor no tiene guía."""
    g = guide_for(provider)
    if g is None:
        return None
    return {
        "provider": g.provider,
        "display_name": g.display_name,
        "summary": g.summary,
        "required_fields": list(g.required_fields),
        "steps": [
            {"id": s.id, "title": s.title, "detail": s.detail, "where": s.where, "trap": s.trap}
            for s in g.steps
        ],
        "checks": [
            {"id": c.id, "title": c.title, "fixes_step": c.fixes_step} for c in g.checks
        ],
    }


__all__ = ["GuideStep", "GuideCheck", "SetupGuide", "SETUP_GUIDES",
           "GITLAB_GUIDE", "guide_exists", "guide_for", "guide_as_dict"]
```

#### F0.b — Flags

`config.py`, **inmediatamente después** del bloque del plan 218 (después de la línea `STACKY_CAPABILITY_DEGRADATION_ENABLED`, hoy `config.py:1203-1205`):

```python
    # ── Plan 259 — Alta de proyecto GitLab + guía de configuración ────────────
    # Las 3 nacen ON: ninguna dispara las 4 excepciones duras. El alta guarda el
    # token CIFRADO (hoy no se guarda de ninguna forma), la guía es texto de solo
    # lectura y la verificación son 5 GET sin redirecciones contra la instancia
    # que el propio operador tipeó. El kill-switch del eje GitLab sigue siendo
    # STACKY_GITLAB_ENABLED, que NO cambia su default (OFF, excepción dura #3).
    STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED: bool = os.getenv(
        "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_SETUP_GUIDE_ENABLED: bool = os.getenv(
        "STACKY_SETUP_GUIDE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_SETUP_GUIDE_VERIFY_ENABLED: bool = os.getenv(
        "STACKY_SETUP_GUIDE_VERIFY_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

`services/harness_flags.py` — agregar las 3 keys a `_CATEGORY_KEYS["paridad_proveedores"]` (hoy `harness_flags.py:478-484`, después de `STACKY_GITLAB_SEMANTIC_RULES_ENABLED`):

```python
        "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED",  # Plan 259 F1/F2/F5 — alta de proyecto GitLab
        "STACKY_SETUP_GUIDE_ENABLED",                # Plan 259 F4/F6 — botón INFO + guía
        "STACKY_SETUP_GUIDE_VERIFY_ENABLED",         # Plan 259 F4/F6 — "Verificar ahora"
```

y 3 `FlagSpec` al final de `FLAG_REGISTRY`, con `group="global"`, `env_only=False`, `default=True` y el comentario `# Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).`:

| key | label | description |
|---|---|---|
| `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` | `Crear proyectos GitLab desde la pantalla de alta` | `Plan 259 — Agrega GitLab a los sistemas de tickets elegibles al crear un proyecto y habilita la rama GitLab del alta en el backend. Si la apagás, el botón no aparece y el backend rechaza tracker_type=gitlab con un mensaje explícito en vez de convertir el proyecto a Azure DevOps.` |
| `STACKY_SETUP_GUIDE_ENABLED` | `Botón INFO con la guía de configuración paso a paso` | `Plan 259 — Muestra un botón INFO junto al sistema de tickets elegido que abre la guía exacta de configuración (12 pasos para GitLab). Texto de solo lectura, sin red.` |
| `STACKY_SETUP_GUIDE_VERIFY_ENABLED` | `Botón "Verificar ahora" dentro de la guía` | `Plan 259 — Corre 5 controles de solo lectura contra la instancia que escribiste en el formulario y marca cuál falla. No escribe nada, ni en GitLab ni en disco.` |

`tests/test_harness_flags.py` — agregar las 3 keys a `_CURATED_DEFAULTS_ON` (hoy `:467`), encabezadas por el bloque de comentario del plan 259 igual que hacen los planes 254-258.

##### F0.b.4 — `services/harness_flags_help.py` *(v3, hallazgo B10 — OBLIGATORIO, v2 lo omitía)*

`tests/test_harness_flags_help.py:33-35` exige que `PLAIN_HELP` cubra el **100 %** de `FLAG_REGISTRY`. Agregar las 3 entradas al dict `PLAIN_HELP`. **Las 5 restricciones son del gate, no son estilo** (verificadas en el fuente del test, no inferidas):

| # | Restricción | Test que la impone |
|---|---|---|
| 1 | `10 <= len(what) <= 200` | `test_plain_help_fields_non_empty_and_bounded` |
| 2 | `len(on_effect) <= 240` y `len(off_effect) <= 240`; `example <= 300`; ningún campo vacío | ídem |
| 3 | `on_effect` y `off_effect` arrancan **literalmente** con `"Si "` | `test_plain_help_on_off_start_with_si` |
| 4 | **Prohibido** citar una key SCREAMING_SNAKE en cualquier campo (`_KEY_RE = r"\b[A-Z]+_[A-Z0-9_]+\b"`) | `test_plain_help_avoids_jargon_denylist` |
| 5 | **Prohibido** referenciar una fase de plan (`_PHASE_RE = r"\bF\d"`) y toda palabra de `JARGON_DENYLIST` (con plural opcional, case-insensitive: `token`/`tokens`, `endpoint`, `gate`, `prompt`, `backend`, …) | ídem |

> **Trampa concreta:** las `description` que este plan propone para `FLAG_REGISTRY` (tabla de arriba) **violan las reglas 4 y 5** — dicen `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED=false` y `Plan 259 — …`. Eso está **bien** ahí (el gate solo mira `PLAIN_HELP`), pero **no se pueden copiar** a `PLAIN_HELP`. Hay que redactarlas de nuevo. Texto exacto a usar:

```python
    "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED": PlainHelp(
        what="Permite elegir GitLab como sistema de tickets al crear un proyecto nuevo.",
        on_effect="Si está encendida, la pantalla de alta ofrece GitLab y el servidor guarda el proyecto como GitLab.",
        off_effect="Si está apagada, GitLab no aparece al crear y el servidor rechaza el pedido con un aviso claro.",
        example="Crear un proyecto contra tu GitLab de empresa sin pasar por la pantalla de edición.",
    ),
    "STACKY_SETUP_GUIDE_ENABLED": PlainHelp(
        what="Muestra un botón de información con la guía de configuración paso a paso.",
        on_effect="Si está encendida, aparece el botón que abre la guía con los pasos exactos para dejar la conexión andando.",
        off_effect="Si está apagada, el botón no aparece y hay que configurar la conexión sin la ayuda en pantalla.",
        example="Abrir la guía y seguir los doce pasos sin salir de la pantalla de alta.",
    ),
    "STACKY_SETUP_GUIDE_VERIFY_ENABLED": PlainHelp(
        what="Agrega un boton que prueba la conexion en vivo desde adentro de la guia.",
        on_effect="Si está encendida, podés probar los datos que escribiste y ver cuál de los cinco controles falla.",
        off_effect="Si está apagada, la guía se ve igual pero sin el botón que prueba la conexión.",
        example="Apretar el botón de probar y descubrir que al permiso del acceso le falta el nivel de escritura.",
    ),
```

> Redacción validada contra el gate: cero SCREAMING_SNAKE, cero `F<n>`, cero términos de la denylist (por eso dice *"acceso"* y no *"token"*, *"servidor"* y no *"backend"*, *"control"* y no *"gate"*), y `on_effect`/`off_effect` arrancan con `"Si "`.

**Baseline honesto de este archivo** *(v3, B2)*: `test_harness_flags_help.py` está **ROJO de fábrica** — medido corriendo: **4 failed / 4 passed**, con 79 flags del registro sin ayuda (entre ellas `STACKY_PROVIDER_PARITY_ENABLED` del plan 218). Agregar estas 3 entradas **no lo pone en verde** y **no es responsabilidad de este plan ponerlo en verde**. El criterio binario es el de abajo: **las 3 keys de este plan no pueden figurar en la lista de faltantes**, y el número de fallos no puede subir de 4.

#### Tests (PRIMERO)

`backend/tests/test_plan259_setup_guide_data.py`:

| Test | Qué asegura |
|---|---|
| `test_modulo_es_puro` | Leer el fuente de `services/setup_guides.py` y afirmar que **no** contiene `import flask`, `import config`, `import requests`, `open(`, `Path(`. |
| `test_gitlab_tiene_los_12_pasos` | `len(GITLAB_GUIDE.steps) == 12` y los `id` son exactamente los 12 `gl-*` listados, en orden. |
| `test_ids_de_paso_unicos` | No hay `id` repetido en `steps` ni en `checks`, para **toda** guía de `SETUP_GUIDES`. |
| `test_cada_check_apunta_a_un_paso_existente` | Para toda guía y todo `check`: `check.fixes_step in {s.id for s in guide.steps}`. **Este es el invariante que hace útil la verificación.** |
| `test_campos_no_vacios` | Para toda guía: `summary`, y por paso `title`/`detail`/`where` no vacíos; `where in {"gitlab","stacky","windows"}`. |
| `test_titulos_acotados` | `len(step.title) <= 90` para todo paso. |
| `test_sin_jerga` | *(v2 — regla determinista, sin juicio; C14.)* `_JERGA_PROHIBIDA = ("PAT", "namespace", "endpoint", "payload", "scope")`. Para cada `step.detail`, ningún término de esa tupla puede aparecer **salvo** que aparezca dentro de la lista literal `_JERGA_PERMITIDA_LITERAL = ("'scopes'",)` — es decir, entrecomillado, porque es el rótulo que el operador ve en la pantalla de GitLab. Búsqueda case-sensitive con `in`, sin regex y sin "explicación en la misma frase" (criterio subjetivo que v1 no podía verificar). Los literales `'api'` y `'read_api'` no están en la denylist: son valores a tipear, no jerga. |
| `test_guide_as_dict_serializa_y_es_json` | `json.dumps(guide_as_dict("gitlab"))` no lanza; el dict tiene 6 claves; `len(d["steps"]) == 12`; `len(d["checks"]) == 5`. |
| `test_guide_as_dict_desconocido_es_none` | `guide_as_dict("azure_devops") is None` y `guide_exists("azure_devops") is False`. |
| `test_menciona_los_anclajes_operativos` | El texto concatenado de los 12 pasos menciona literalmente `STACKY_GITLAB_ENABLED`, `GITLAB_TOKEN`, `gitlab_auth.json`, `/api/v4/version` y `'api'`. Blinda que la guía no pierda los datos duros. |

**Comando:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan259_setup_guide_data.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -v
```

**Criterio de aceptación BINARIO** *(v3, B2 — separa "pasa" de "no empeora")*:

1. `test_plan259_setup_guide_data.py` — **todos en verde** (archivo nuevo, no tiene baseline).
2. `test_harness_flags.py` — **56 passed**, igual que el baseline medido. Ni uno menos.
3. `test_harness_flags_help.py` — **rojo ajeno preexistente**: el baseline medido es **4 failed / 4 passed**. Criterio: sigue en **4 failed** (no 5) y este comando imprime `[]`:
   ```
   .venv\Scripts\python.exe -c "from services.harness_flags import FLAG_REGISTRY; from services.harness_flags_help import PLAIN_HELP; print(sorted({'STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED','STACKY_SETUP_GUIDE_ENABLED','STACKY_SETUP_GUIDE_VERIFY_ENABLED'} - set(PLAIN_HELP)))"
   ```
   **Prohibido** arreglar los otros 79 faltantes acá: es rojo ajeno y es alcance de otro plan.
4. ```
   .venv\Scripts\python.exe -c "from services.setup_guides import guide_as_dict; d=guide_as_dict('gitlab'); print(len(d['steps']), len(d['checks']))"
   ```
   imprime exactamente `12 5`.

> **Nota de verificación (v3):** el módulo `services/setup_guides.py` tal como está escrito arriba fue extraído del plan, escrito a disco y sometido a los **10 tests verificables** de esta fase con el venv py3.13.5 — **los 10 pasaron**, incluido `test_sin_jerga` (la única ocurrencia de un término de la denylist es `'scopes'` en `gl-02-token`, cubierta por `_JERGA_PERMITIDA_LITERAL`) y `test_menciona_los_anclajes_operativos` (los 5 anclajes presentes). Esta fase se implementa **tal cual**, sin retocar el texto: cualquier reescritura del `detail` de un paso tiene que volver a pasar por `test_sin_jerga`.

**Flag:** `STACKY_SETUP_GUIDE_ENABLED` (default **ON**). El módulo de datos en sí no se gatea (es inerte sin consumidor).
**Impacto por runtime:** ninguno — módulo puro sin LLM. **Fallback Codex / Claude Code / Copilot:** idéntico, el dato es el mismo.
**Trabajo del operador:** ninguno.

---

### F1 — `initialize_gitlab_project` + `write_gitlab_auth` + template embebido de perfil

**Objetivo:** que `project_manager.py` sepa crear un proyecto GitLab y guardar su token cifrado, igual que los otros 3 trackers, y que el `client_profile` sembrado sea **el de GitLab también en el ejecutable congelado**.
**Valor:** el `config.json` GitLab queda con la **forma exacta** que ya consumen `project_context._auth_path_for` y `build_tracker_target` (E7) — sin tocarlos.

**Archivos a EDITAR:**
- `Stacky Agents/backend/project_manager.py`
- `Stacky Agents/backend/services/client_profile_default_templates.py` *(v2, hallazgo C6/E9)*

**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_project_manager_gitlab.py`

#### F1.0 — Template GitLab embebido *(v2 — obligatorio, no condicional)*

`services/client_profile_default_templates.py` define hoy `AZURE_DEVOPS` (`:27`), `JIRA` (`:114`) y `MANTIS` (`:192`), y arma `DEFAULT_TEMPLATES` (`:272`). **No hay GitLab.** Agregar, con la misma forma que los otros tres:

```python
GITLAB: dict = { ... }   # contenido = el de services/client_profile_defaults/gitlab.json, tal cual
```

y sumar `"gitlab": GITLAB` a `DEFAULT_TEMPLATES`. El contenido **se copia literalmente** del JSON que ya existe en disco (`services/client_profile_defaults/gitlab.json`): no se inventa nada, no se traduce nada. Sin este paso, en el deploy congelado todo proyecto GitLab arranca con la máquina de estados de Azure DevOps (E9).

> **Verificado ejecutando (v3):** `sorted(DEFAULT_TEMPLATES)` devuelve hoy exactamente `['azure_devops', 'jira', 'mantis']` — falta `gitlab`, tal como dice E9. Y `gitlab.json` **sí** difiere de `azure_devops.json`: 8 claves distintas (`build`, `code_layout`, `conventions`, `database`, `docs_indexes`, `language`, `port_residue`, `tracker_state_machine`), así que el test de F1.a puede comparar por `tracker_state_machine` sin ambigüedad.
>
> **ATENCIÓN — este archivo NO tiene `__all__`.** Verificado ejecutando: `'__all__' in src` → `False` (276 líneas, sin bloque de exports). En `client_profile_default_templates.py` se agrega **solo** la constante `GITLAB` y su entrada en `DEFAULT_TEMPLATES`. **Nada más.** Todo lo que sigue (F1.a) va en **otro archivo**.

#### F1.a — `project_manager.py` (ARCHIVO DISTINTO) *(v3, hallazgo B6)*

> **Corte explícito de archivo.** Todo lo de acá abajo se agrega a **`Stacky Agents/backend/project_manager.py`**, al final, **antes de su `__all__`** (que sí existe, hoy en `project_manager.py:628-649`). **No** va en `client_profile_default_templates.py`. v2 encadenaba este bloque adentro de la subsección F1.0 sin abrir una nueva, y el archivo que F1.0 nombra ni siquiera tiene `__all__`: un modelo menor metía el helper de alta en el archivo de templates.
>
> **Símbolos verificados presentes en `project_manager.py` — no hay que importar nada nuevo:** `Path` (`:27`), `PROJECTS_DIR` (`:33`), `get_project_config` (`:55`), `initialize_project` (`:105`), y `set_encrypted_secret` + `write_json_file` (`:30`, ambos desde `services.secrets_store`). La firma real es `set_encrypted_secret(payload, field, value, *, format_field=None, preencoded=False)`, o sea que la llamada de abajo es correcta byte por byte. Precedente idéntico: `write_mantis_auth` (`:599-624`), que también resuelve con `PROJECTS_DIR / name.upper() / "auth"`.

Agregar al final de `project_manager.py`, **antes** de su `__all__`:

```python
# ── GitLab ────────────────────────────────────────────────────────────────────

DEFAULT_GITLAB_AUTH_FILE = "auth/gitlab_auth.json"


def initialize_gitlab_project(
    name: str,
    url: str,
    project_path: str,
    workspace_root: str,
    display_name: str = "",
    group: str = "",
    auth_file: str = "",
    docs_paths: dict | None = None,
    agents_dir: str | None = None,
) -> dict:
    """Helper de alto nivel para dar de alta un proyecto GitLab (Plan 259 F1).

    `project_path` es 'grupo/subgrupo/proyecto' o el ID numérico. Se guarda en
    `issue_tracker.project` y `issue_tracker.base_url`, que son las claves que ya
    leen project_context._tracker_project_for (:98) y _base_url_for (:107-110).

    `auth_file` vacío NO significa "poné el default": significa "conservá el que
    ya tenga el proyecto" (Plan 259 v2, hallazgo C4). El modal de edición expone
    ese campo como ruta editable (EditProjectModal.tsx:735-750); pisarlo con el
    default sería la misma degradación silenciosa que este plan viene a matar.
    Solo cuando el proyecto no tiene ninguno se usa DEFAULT_GITLAB_AUTH_FILE.
    """
    previous = (get_project_config(name) or {}).get("issue_tracker") or {}
    resolved_auth = (
        (auth_file or "").strip()
        or str(previous.get("auth_file") or "").strip()
        or DEFAULT_GITLAB_AUTH_FILE
    )
    tracker: dict = {
        "type":      "gitlab",
        "base_url":  url.rstrip("/"),
        "project":   project_path.strip(),
        "auth_file": resolved_auth,
    }
    if group:
        tracker["group"] = group.strip()

    return initialize_project(
        name=name,
        display_name=display_name or name,
        workspace_root=workspace_root,
        issue_tracker=tracker,
        docs_paths=docs_paths,
        agents_dir=agents_dir,
    )


def resolve_gitlab_auth_path(name: str, auth_file: str = "") -> Path:
    """Ruta ABSOLUTA del archivo de credencial GitLab de un proyecto (Plan 259 v2).

    `auth_file` puede ser: vacío (se usa el del config.json, y si tampoco hay,
    DEFAULT_GITLAB_AUTH_FILE), una ruta relativa (se resuelve bajo la carpeta del
    proyecto) o una ruta absoluta que el operador cargó en el campo "Ruta al
    archivo de token" del modal de edición (se respeta tal cual).
    """
    declared = (auth_file or "").strip()
    if not declared:
        tracker = (get_project_config(name) or {}).get("issue_tracker") or {}
        declared = str(tracker.get("auth_file") or "").strip() or DEFAULT_GITLAB_AUTH_FILE
    candidate = Path(declared)
    if candidate.is_absolute():
        return candidate
    return PROJECTS_DIR / name.upper() / candidate


def write_gitlab_auth(name: str, url: str, token: str,
                      project_path: str = "", auth_file: str = "") -> Path:
    """Escribe el archivo de credencial GitLab del proyecto con el token cifrado.

    El campo se llama `token` y el formato queda declarado en `token_format`
    (DPAPI), igual que Jira y Mantis. El lector se adapta en F3.
    La ruta sale de `resolve_gitlab_auth_path`: por default
    backend/projects/{NAME}/auth/gitlab_auth.json, pero se respeta la ruta que el
    operador haya declarado (Plan 259 v2, hallazgo C4).
    """
    auth_path = resolve_gitlab_auth_path(name, auth_file)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"url": url.rstrip("/")}
    if project_path:
        payload["project"] = project_path.strip()
    set_encrypted_secret(payload, "token", token, format_field="token_format")
    write_json_file(auth_path, payload)
    return auth_path
```

y sumar `"initialize_gitlab_project"`, `"write_gitlab_auth"`, `"resolve_gitlab_auth_path"` y `"DEFAULT_GITLAB_AUTH_FILE"` a `__all__` (hoy `project_manager.py:628-648`).

> **Nota de diseño, no ambigua:** `base_url` (no `url`) porque es la clave que lee `_base_url_for` (`project_context.py:110`), y `project` (no `project_path`) porque es la que lee `_tracker_project_for` (`project_context.py:98`). Usar otros nombres dejaría el proyecto creado pero **inalcanzable**.

#### Tests (PRIMERO) — `test_plan259_project_manager_gitlab.py`

Usar `monkeypatch.setattr(project_manager, "PROJECTS_DIR", tmp_path)` para no tocar el perfil real (gotcha del plan 216).

| Test | Qué asegura |
|---|---|
| `test_crea_config_con_forma_canonica` | `issue_tracker == {"type":"gitlab","base_url":"https://gitlab.com","project":"acme/api","auth_file":"auth/gitlab_auth.json"}`. |
| `test_group_opcional_ausente_si_vacio` | Sin `group`, la clave **no está** en el dict (no `""`). |
| `test_group_presente_si_se_pasa` | Con `group="acme"`, `issue_tracker["group"] == "acme"`. |
| `test_url_sin_barra_final` | `url="https://gitlab.com/"` → `base_url == "https://gitlab.com"`. |
| `test_client_profile_es_el_de_gitlab_no_el_de_ado` | *(v2, C6.)* No alcanza con `"client_profile" in cfg`. El test **afirma cuál** perfil quedó: crea el proyecto y compara `cfg["client_profile"]` contra `json.loads(Path("services/client_profile_defaults/gitlab.json").read_text())` en las claves que difieren de `azure_devops.json` (al menos `tracker_state_machine`). |
| `test_client_profile_gitlab_en_deploy_congelado` | *(v2, C6/E9 — el que destapa el bug real.)* Con `monkeypatch.setattr(client_profile, "_DEFAULTS_DIR", tmp_path / "no-existe")` (simula PyInstaller: los `*.json` no se empaquetan), `get_default_client_profile("gitlab")` **no** debe devolver `DEFAULT_TEMPLATES["azure_devops"]`. Falla contra el árbol actual; pasa con F1.0. |
| `test_token_no_queda_en_claro` | Tras `write_gitlab_auth(..., token="glpat-SECRETO")`, el texto del archivo **no** contiene `glpat-SECRETO` y `payload["token_format"]` está seteado. |
| `test_token_se_puede_releer` | `read_secret_from_file(path, "token", format_field="token_format").value == "glpat-SECRETO"`. |
| `test_idempotente_preserva_extras` | Un `config.json` previo con `pinned_agents` conserva esa clave tras re-inicializar. |
| `test_auth_file_custom_se_preserva` | *(v2, C4.)* Proyecto cuyo `issue_tracker.auth_file` vale `C:/secretos/gl.json`; re-inicializar con `auth_file=""` deja **`C:/secretos/gl.json`**, no el default. **Este test falla contra la F1 de v1.** |
| `test_auth_file_default_si_no_habia` | Proyecto nuevo sin `auth_file` previo ⇒ queda `auth/gitlab_auth.json`. |
| `test_write_gitlab_auth_respeta_ruta_declarada` | *(v2, C4.)* Con `auth_file=str(tmp_path/"custom"/"gl.json")`, el token se escribe **ahí** y **no** en `projects/<NAME>/auth/gitlab_auth.json`. |
| `test_auth_path_resuelve_a_gitlab_auth` | `project_context._auth_path_for(cfg)` termina en `auth/gitlab_auth.json` cuando se usó el default. |
| `test_build_tracker_target_lee_lo_escrito` | Con el proyecto creado y activo, `build_tracker_target(name)` devuelve `project_path=="acme/api"` y `base_url=="https://gitlab.com"`. **Cierra el lazo escritura↔lectura.** |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_project_manager_gitlab.py -v`
Si aparece `SQLITE_LOCKED`, correr el archivo 8-12 veces seguidas (gotcha shared-cache de la casa) y estabilizar con `run_with_retry` alrededor de la unidad de trabajo.

**Criterio de aceptación BINARIO:** los 14 tests en verde y
```
.venv\Scripts\python.exe -c "import project_manager as p, services.client_profile_default_templates as t; print(all(k in p.__all__ for k in ('initialize_gitlab_project','write_gitlab_auth','resolve_gitlab_auth_path')), 'gitlab' in t.DEFAULT_TEMPLATES)"
```
imprime `True True`.

**Flag:** `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` (default **ON**). Las funciones son aditivas y no tienen call site hasta F2, así que no llevan guard interno: el guard vive en el endpoint.
**Impacto por runtime:** ninguno. **Fallback:** idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F2 — Cablear `api/projects.py`: rama GitLab en alta, edición, credenciales y listado

**Objetivo:** que la API cree, actualice y devuelva proyectos GitLab, y que **deje de convertirlos a Azure DevOps en silencio**.
**Valor:** cierra un bug de corrupción de datos vivo hoy (E2).

**Archivo a EDITAR:** `Stacky Agents/backend/api/projects.py`
**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_api_projects_gitlab.py`

**Cambio 1 — import** (`api/projects.py:39-59`): agregar `initialize_gitlab_project` y `write_gitlab_auth` a la lista importada de `project_manager`.

**Cambio 2 — `_has_credentials` (`:69-77`)**, que hoy manda GitLab al archivo de Mantis:

```python
def _has_credentials(name: str, tracker_type: str) -> bool:
    """Indica si el proyecto tiene archivo de credenciales almacenado."""
    if tracker_type == "azure_devops":
        auth_filename = "ado_auth.json"
    elif tracker_type == "jira":
        auth_filename = "jira_auth.json"
    elif tracker_type == "gitlab":            # Plan 259 F2 — antes caía en mantis_auth.json
        auth_filename = "gitlab_auth.json"
    else:  # mantis
        auth_filename = "mantis_auth.json"
    return (PROJECTS_DIR / name / "auth" / auth_filename).exists()
```

**Cambio 3 — `_project_to_dict` (`:80-109`)**: agregar los 4 campos que `EditProjectModal.tsx:41-44` ya lee y que hoy llegan siempre vacíos, con el mismo patrón condicional que usan `jira_url`/`mantis_url`:

```python
        # GitLab fields (Plan 259 F2)
        "gitlab_url":        tracker.get("base_url", "") if t_type == "gitlab" else "",
        "gitlab_project":    tracker.get("project", "")  if t_type == "gitlab" else "",
        "gitlab_group":      tracker.get("group", "")    if t_type == "gitlab" else "",
        "gitlab_auth_file":  tracker.get("auth_file", "") if t_type == "gitlab" else "",
```

**Cambio 3-bis — tapar la fuga de `ado_project`** *(v3, hallazgo B8 — NO opcional)*. `api/projects.py:96` hace hoy:

```python
        "ado_project":       tracker.get("project", ""),
```

**sin condicionar por tracker.** La clave `issue_tracker.project` es compartida: para GitLab vale `acme/api` (es la forma canónica que fija F1.a). Consecuencia verificada en el árbol: un proyecto GitLab se lista con `ado_project:"acme/api"`, `EditProjectModal.tsx:25` lo semilla **incondicionalmente** (`ado_project: project.ado_project ?? ""`, fuera de cualquier `{isAdo && …}`) y `buildPayload()` lo reenvía en **cada** PATCH. Es la misma clase de mezcla de campos que este plan viene a matar. Cambiarlo por:

```python
        "ado_project":       tracker.get("project", "") if t_type == "azure_devops" else "",
```

**Backward-compat:** para los 3 trackers preexistentes el valor no se mueve — Jira guarda su clave en `project_key` y Mantis en `project_id`, así que `tracker.get("project")` ya venía vacío en ambos; el único tipo cuyo valor cambia es el que este plan estrena. Cubierto por `test_listado_no_filtra_ado_project_en_gitlab`.

**Cambio 4 — helper de guard, nuevo, después de `_has_credentials`:**

```python
def _gitlab_onboarding_enabled() -> bool:
    """Plan 259 F2 — la flag vive en la INSTANCIA (config.config), no en el módulo.
    Mismo idioma que tracker_provider.py:133 y ci_provider.py:121."""
    try:
        import config as _config
        return bool(getattr(_config.config, "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED", False))
    except Exception:
        return False
```

**Cambio 5 — rama GitLab en `init_project`**, insertada **antes** del `else: # azure_devops` (`:360`).

> **v2 (hallazgo C2) — la variable del motor se declara ANTES de la cadena.** `init_project` tiene **un único `return` compartido** por los 4 trackers (`api/projects.py:383-384`). Si `engine_result` solo existiera dentro de la rama GitLab, el alta de ADO / Jira / Mantis reventaría con `NameError`. Por eso, **inmediatamente antes** del `if tracker_type == "jira":` (`:290`) se agrega:
> ```python
>         engine_result: dict | None = None   # Plan 259 F7 — None en los 3 trackers no-GitLab
> ```
> y el `return` compartido del final (`:383-384`) pasa a ser, **textualmente**:
> ```python
>         active_name = get_active_project()
>         payload = {"ok": True, "project": _project_to_dict(cfg, active_name)}
>         if engine_result is not None:       # Plan 259 F7 — solo en el alta GitLab
>             payload["gitlab_engine"] = engine_result
>         return jsonify(payload)
> ```

```python
        elif tracker_type == "gitlab":
            if not _gitlab_onboarding_enabled():
                return jsonify({"ok": False, "error":
                    "El alta de proyectos GitLab está apagada "
                    "(STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED=false)."}), 400
            gitlab_url     = (data.get("gitlab_url") or "").strip()
            gitlab_project = (data.get("gitlab_project") or "").strip()
            gitlab_group   = (data.get("gitlab_group") or "").strip()
            gitlab_token   = (data.get("gitlab_token") or "").strip()
            enable_engine  = bool(data.get("gitlab_enable_engine", True))

            if not gitlab_url:
                return jsonify({"ok": False, "error": "gitlab_url requerida"}), 400
            if not gitlab_project:
                return jsonify({"ok": False, "error": "gitlab_project requerido"}), 400

            gitlab_auth_file = (data.get("gitlab_auth_file") or "").strip()  # v2 C4: vacío = default

            cfg = initialize_gitlab_project(
                name=name,
                display_name=display_name or name,
                workspace_root=workspace_root,
                url=gitlab_url,
                project_path=gitlab_project,
                group=gitlab_group,
                auth_file=gitlab_auth_file,
                docs_paths=docs_paths,
                agents_dir=agents_dir,
            )
            if gitlab_token:
                write_gitlab_auth(name=name, url=gitlab_url,
                                  token=gitlab_token, project_path=gitlab_project,
                                  auth_file=gitlab_auth_file)
            engine_result = _enable_gitlab_engine() if enable_engine else {
                "changed": False, "already_on": False, "skipped": True
            }   # F7
```

**Cambio 6 — misma rama en `update_project`**, antes del `else` (`:504`), con `_resolve_text_field` para PATCH parcial:

```python
        elif tracker_type == "gitlab":
            if not _gitlab_onboarding_enabled():
                return jsonify({"ok": False, "error":
                    "La edición de proyectos GitLab está apagada "
                    "(STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED=false)."}), 400
            tracker        = cfg.get("issue_tracker") or {}
            gitlab_url     = _resolve_text_field(data, "gitlab_url",     tracker.get("base_url", ""))
            gitlab_project = _resolve_text_field(data, "gitlab_project", tracker.get("project", ""))
            gitlab_group   = _resolve_text_field(data, "gitlab_group",   tracker.get("group", ""))
            # v2 C4: el modal de edición YA expone este campo (EditProjectModal.tsx:735-750).
            # Hardcodearlo pisaría en silencio lo que el operador escribió.
            gitlab_auth_file = _resolve_text_field(data, "gitlab_auth_file", tracker.get("auth_file", ""))
            gitlab_token   = (data.get("gitlab_token") or "").strip()
            new_cfg = initialize_gitlab_project(
                name=project_name,
                display_name=(data.get("display_name") or cfg.get("display_name", project_name)).strip(),
                workspace_root=workspace_root,
                url=gitlab_url,
                project_path=gitlab_project,
                group=gitlab_group,
                auth_file=gitlab_auth_file,
                docs_paths=docs_paths,
                agents_dir=agents_dir,
            )
            if gitlab_token:
                write_gitlab_auth(name=project_name, url=gitlab_url,
                                  token=gitlab_token, project_path=gitlab_project,
                                  auth_file=gitlab_auth_file)
```

> **`update_project` NO enciende el motor.** Es deliberado y está testeado (`test_no_se_dispara_en_patch`, F7): encender una perilla global es del **alta**, donde el operador ve y tilda la casilla. En la edición, si el motor está apagado, la respuesta ya lo dice por el camino normal de sincronización y el operador lo prende desde Configuración → Paridad de proveedores.

**Cambio 7 — `get_project_credentials` (`:543-...`)**: agregar al `result` la clave `"gitlab_token_saved": (PROJECTS_DIR / project_name / "auth" / "gitlab_auth.json").exists()`. Nunca devolver el token.

**Cambio 8 — docstring del módulo (`:11-27`)**: agregar el bloque de campos GitLab, para que el contrato quede escrito donde ya están los otros 3.

#### Tests (PRIMERO) — `test_plan259_api_projects_gitlab.py`

Cliente Flask de test + `monkeypatch` de `PROJECTS_DIR` a `tmp_path` en `project_manager` **y** en `api.projects` (importa el símbolo por valor).

| Test | Qué asegura |
|---|---|
| `test_init_gitlab_devuelve_200` | `POST /api/init_project` con `tracker_type="gitlab"` → 200 y `project["tracker_type"] == "gitlab"`. |
| `test_init_gitlab_escribe_type_gitlab` | El `config.json` en disco tiene `issue_tracker.type == "gitlab"`. **Anti-regresión del bug E2.** |
| `test_init_gitlab_sin_url_400` | Falta `gitlab_url` → 400 con `"gitlab_url requerida"`. |
| `test_init_gitlab_sin_project_400` | Falta `gitlab_project` → 400 con `"gitlab_project requerido"`. |
| `test_init_gitlab_no_exige_organization` | El body **no** manda `organization` y responde 200 (hoy responde 400). |
| `test_patch_a_gitlab_no_degrada_a_ado` | Proyecto ADO existente + `PATCH {"tracker_type":"gitlab","gitlab_url":...,"gitlab_project":...}` → `config.json` queda con `type=="gitlab"`. **Este test falla contra el árbol actual: es la prueba del bug.** |
| `test_patch_parcial_preserva_url` | `PATCH {"display_name":"X"}` sobre un proyecto GitLab conserva `base_url` y `project`. |
| `test_listado_expone_campos_gitlab` | `GET /api/projects` → el proyecto trae `gitlab_url`, `gitlab_project`, `gitlab_group`, `gitlab_auth_file` con los valores escritos. |
| `test_listado_no_filtra_gitlab_en_proyecto_ado` | Un proyecto ADO trae los 4 campos GitLab en `""`. |
| `test_has_credentials_gitlab` | Con `auth/gitlab_auth.json` presente → `has_credentials is True`; sin él → `False`. |
| `test_token_nunca_en_la_respuesta` | El token enviado en el body **no** aparece en `json.dumps(response.get_json())` de init, patch, listado ni `/credentials`. |
| `test_flag_off_rechaza_explicito` | Con `monkeypatch.setattr(config.config, "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED", False)`: 400 con el mensaje que nombra la flag, y **el `config.json` NO se creó**. Nunca degradación silenciosa. |
| `test_alta_ado_jira_mantis_sigue_ok` | *(v2, C2 — el test que atrapa el `NameError`.)* `POST /api/init_project` con `tracker_type` en `azure_devops`, `jira` y `mantis` responde **200** y el cuerpo **no** trae la clave `gitlab_engine`. Falla con la F7 de v1 tal como estaba escrita. |
| `test_patch_preserva_auth_file_custom` | *(v2, C4.)* Proyecto GitLab con `auth_file="C:/secretos/gl.json"` + `PATCH {"display_name":"X"}` ⇒ el `config.json` **conserva** esa ruta. |
| `test_patch_cambia_auth_file_si_viene_en_el_body` | `PATCH {"gitlab_auth_file":"auth/otro.json"}` ⇒ queda `auth/otro.json` (el operador manda, el default no). |
| `test_listado_no_filtra_ado_project_en_gitlab` | *(v3, B8.)* Proyecto GitLab con `issue_tracker.project == "acme/api"` ⇒ `GET /api/projects` devuelve `ado_project == ""` y `gitlab_project == "acme/api"`. **Falla contra el árbol actual: es la prueba de la fuga.** |
| `test_listado_conserva_ado_project_en_ado` | No-regresión del Cambio 3-bis: un proyecto Azure DevOps sigue trayendo su `ado_project` con el valor de siempre. |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_api_projects_gitlab.py -v`

**Criterio de aceptación BINARIO:** **17** tests en verde *(v3: 15 + los 2 de la fuga `ado_project`)*, y esta verificación de no-regresión de los otros trackers en **10 passed**, que es el baseline medido:
```
.venv\Scripts\python.exe -m pytest tests/test_plan208_profile_schema.py -v
```

**Flag:** `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` (default **ON**). Con la flag OFF el endpoint **rechaza explícito**; jamás vuelve a caer al `else` de ADO.
**Impacto por runtime:** ninguno. **Fallback:** idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F3 — Que GitLab pueda leer el token cifrado (sin romper el formato plano actual)

**Objetivo:** que `GitLabClient` descifre el token que F1 escribe, y siga leyendo los archivos en texto plano que existan hoy.
**Valor:** sin esto, F1+F2 crean un proyecto que da **401 en la primera llamada** — un falso verde de manual.

**Archivo a EDITAR:** `Stacky Agents/backend/services/gitlab_client.py`
**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_gitlab_token_dpapi.py`

Reemplazar `_load_token_from_file` (`gitlab_client.py:75-93`) por:

```python
    def _load_token_from_file(self, auth_path: Optional[str]) -> str:
        """Busca el token en el archivo de credencial GitLab bajo auth_path.

        Plan 259 F3: usa read_secret_from_file, que descifra DPAPI cuando el
        archivo declara token_format y devuelve el valor tal cual cuando está en
        texto plano.

        ATENCIÓN (Plan 259 v2, hallazgo C7): read_secret_from_file NO es solo
        lectura. Cuando encuentra el secreto en claro lo cifra y REESCRIBE el
        archivo (secrets_store.py:277-279). Eso es lo que queremos —el archivo
        queda al nivel de los otros 3 trackers— pero significa que un archivo no
        escribible haría fallar la lectura. Por eso, si el camino cifrado lanza,
        se cae al lector plano EXACTO de hoy: una configuración que funciona no
        puede dejar de funcionar por este plan.
        """
        from services.secrets_store import read_secret_from_file  # import local: evita ciclo

        candidates: list[Path] = []
        if auth_path:
            candidates.append(Path(auth_path) / "auth" / "gitlab_auth.json")
            candidates.append(Path(auth_path))
        candidates.append(Path("auth") / "gitlab_auth.json")

        for path in candidates:
            if not path.exists():
                continue
            for field, fmt in (("token", "token_format"), ("private_token", "private_token_format")):
                try:
                    tok = (read_secret_from_file(path, field, format_field=fmt).value or "").strip()
                except Exception:
                    tok = ""
                if tok:
                    return tok
            # Fallback literal al comportamiento previo a este plan (archivo de
            # solo lectura, disco lleno, JSON con el token plano que no se pudo
            # migrar). NO se pierde ninguna instalación que hoy anda.
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tok = str(data.get("token") or data.get("private_token") or "").strip()
                if tok:
                    logger.warning(
                        "GitLab: token leído en texto plano de %s (no se pudo migrar a DPAPI)", path
                    )
                    return tok
            except Exception:
                pass
        return ""
```

> **No se toca** la precedencia `env > archivo` de `:62-64`: cambiarla rompería instalaciones que hoy dependen de `GITLAB_TOKEN`. La trampa queda **documentada** en el paso `gl-10-env-precedencia` y **detectada** por el chequeo `chk-token` de F4, que no usa esa precedencia.
> **Nota de implementación *(v3, hallazgo B13 — corregida)*.** Verificado ejecutando sobre el archivo real: `json` (`:15`) y `Path` (`:19`) **sí** están importados, pero **`logger` NO existe** — la cadena `logger` aparece **0 veces** en `services/gitlab_client.py`. v2 afirmaba que ya estaba. Paso obligatorio, no condicional: agregar `import logging` junto a los imports de `:13-19` y, después del bloque de imports, la línea
> ```python
> logger = logging.getLogger(__name__)
> ```
> (mismo patrón que `api/harness_flags.py:19`). Sin esto, el `logger.warning` del fallback tira `NameError` justo en el camino de recuperación — es decir, cuando el archivo es de solo lectura, que es exactamente el caso que `test_archivo_solo_lectura_sigue_dando_el_token` cubre.

#### Tests (PRIMERO) — `test_plan259_gitlab_token_dpapi.py`

| Test | Qué asegura |
|---|---|
| `test_lee_token_cifrado_dpapi` | Escribir con `write_gitlab_auth(token="glpat-XYZ")` y construir `GitLabClient(auth_path=<dir_proyecto>)` → `client._token == "glpat-XYZ"`. |
| `test_lee_token_plano_legacy` | `{"token": "glpat-PLANO"}` sin `token_format` → `client._token == "glpat-PLANO"`. **Backward-compat.** |
| `test_lee_private_token_legacy` | `{"private_token": "glpat-VIEJO"}` → se lee igual. |
| `test_archivo_corrupto_no_lanza` | JSON inválido → `_load_token_from_file` devuelve `""` y el constructor tira `TrackerConfigError` (no `JSONDecodeError`). |
| `test_env_sigue_ganando` | Con `GITLAB_TOKEN=env-token` en el entorno y un archivo cifrado distinto → `client._token == "env-token"`. **Congela la precedencia documentada.** |
| `test_sin_token_error_claro` | Sin env y sin archivo → `TrackerConfigError` con el mensaje actual, byte por byte. |
| `test_plano_se_migra_a_dpapi_en_disco` | *(v2, C7 — declara el efecto, no lo esconde.)* Partiendo de `{"token": "glpat-PLANO"}`, tras construir el cliente el **archivo en disco cambió**: ya no contiene `glpat-PLANO` en claro y sí tiene `token_format`. Afirma **estado observable**, no una llamada. |
| `test_archivo_solo_lectura_sigue_dando_el_token` | *(v2, C7 — la regresión que v1 no veía.)* Archivo plano marcado de solo lectura (`os.chmod(path, stat.S_IREAD)`; en Windows alcanza para que `write_json_file` falle): `client._token == "glpat-PLANO"` igual. **Sin el fallback de F3 este test es rojo y una instalación que hoy anda se rompería.** |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_gitlab_token_dpapi.py -v`

**Criterio de aceptación BINARIO:** 8 tests en verde **y** los tests GitLab preexistentes sin tocar:
```
.venv\Scripts\python.exe -m pytest tests/test_plan218_gitlab_reachable.py -v
.venv\Scripts\python.exe -m pytest tests/test_plan70_smoke_gitlab.py -v
```

**Flag:** ninguna nueva. Es una corrección de compatibilidad interna del lector, no una funcionalidad conmutable; ponerla detrás de un flag dejaría un camino en el que F1 escribe cifrado y el cliente lee criptograma.
**Impacto por runtime:** ninguno. **Fallback:** si DPAPI no está disponible (no-Windows), `read_secret_from_file` devuelve el valor tal cual y el archivo plano sigue funcionando, exactamente como hoy.
**Trabajo del operador:** ninguno.

---

### F4 — Endpoints: servir la guía y verificar en vivo

**Objetivo:** exponer la guía de F0 y 5 chequeos de solo lectura que le digan al operador **cuál** de los 12 pasos le falta.
**Valor:** convierte "info detallada" en "info detallada **verificada**". Es la diferencia entre un manual y un diagnóstico.

**Archivos a CREAR:**
- `Stacky Agents/backend/api/setup_guide.py`
- `Stacky Agents/backend/services/gitlab_setup_check.py`
- `Stacky Agents/backend/tests/test_plan259_setup_guide_api.py`

**Archivo a EDITAR:** `Stacky Agents/backend/api/__init__.py` (registrar el blueprint junto a los demás, patrón de `:37` y `:111`).

#### F4.a — `services/gitlab_setup_check.py`

Camino HTTP **propio y mínimo**, deliberadamente separado de `GitLabClient` por tres razones concretas: (1) `GitLabClient` lee `GITLAB_TOKEN` del entorno y **taparía** el token tipeado (E5) → falso verde; (2) lanza `TrackerConfigError` en `__init__` si no hay token, y acá "no hay token" es un **resultado**, no una excepción; (3) acá hace falta `allow_redirects=False`, que el cliente general no impone.

```python
"""Plan 259 F4 — 5 chequeos de SOLO LECTURA de una configuración GitLab.

NUNCA escribe: ni en GitLab, ni en disco, ni en os.environ.
NUNCA loguea el token ni lo devuelve.
allow_redirects=False: un 30x podría reenviar el header PRIVATE-TOKEN a otro host.
"""
from __future__ import annotations

import urllib.parse
import requests

_TIMEOUT_S = 8
_OK, _FAIL, _UNKNOWN = "ok", "fail", "unknown"


def _res(check_id, status, message, detail=""):
    return {"id": check_id, "status": status, "message": message, "detail": detail}


def _get(base: str, path: str, token: str | None):
    headers = {"Accept": "application/json"}
    if token:
        headers["PRIVATE-TOKEN"] = token
    return requests.get(f"{base}/api/v4{path}", headers=headers,
                        timeout=_TIMEOUT_S, allow_redirects=False)


def run_gitlab_checks(base_url: str, project_path: str, token: str,
                      engine_enabled: bool, engine_will_enable: bool = False) -> list[dict]:
    """Plan 259 v2 (hallazgo C5): `engine_enabled` es el estado REAL del servidor
    (`config.config.STACKY_GITLAB_ENABLED`) y el cliente no puede mentirlo.
    `engine_will_enable` es la INTENCIÓN declarada en el formulario (la casilla
    'Activar el motor GitLab'): no pinta un verde sobre el estado real, pinta el
    tercer estado honesto "apagado, se activa al crear". Sin esto, 'Verificar
    ahora' antes de crear daba SIEMPRE rojo en el camino feliz.
    """
    out: list[dict] = []

    # chk-flag — local, sin red. Tres estados, ninguno mentiroso.
    if engine_enabled:
        out.append(_res("chk-flag", _OK, "El motor GitLab está encendido."))
    elif engine_will_enable:
        out.append(_res("chk-flag", _OK,
                        "El motor GitLab está apagado ahora y se va a activar al crear el "
                        "proyecto, porque dejaste tildada la casilla."))
    else:
        out.append(_res("chk-flag", _FAIL,
                        "El motor GitLab está apagado y la casilla 'Activar el motor GitLab' "
                        "está destildada: la sincronización va a fallar."))

    base = (base_url or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        out.append(_res("chk-instancia", _FAIL,
                        "La URL tiene que empezar con http:// o https://."))
        for cid in ("chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN, "No se pudo probar: falta una URL válida."))
        return out

    # chk-instancia — sin token
    try:
        r = _get(base, "/version", None)
        if r.status_code == 200:
            out.append(_res("chk-instancia", _OK, "La URL responde y es un GitLab."))
        elif r.status_code == 401:
            # v2 (C15): un 401 dice "pide autenticación", no "es GitLab". Un portal
            # SSO corporativo responde igual. No mentimos: es OK provisorio y el
            # veredicto real lo da chk-token, que sí habla con /user.
            out.append(_res("chk-instancia", _OK,
                            "La dirección responde y pide autenticación, como corresponde. "
                            "Si no fuera un GitLab, el control del token lo va a decir."))
        elif r.status_code in (301, 302, 307, 308):
            out.append(_res("chk-instancia", _FAIL,
                            "La URL redirige a otro lado. Usá la dirección final.",
                            f"HTTP {r.status_code}"))
            for cid in ("chk-token", "chk-scope", "chk-proyecto"):
                out.append(_res(cid, _UNKNOWN, "No se pudo probar: la URL redirige."))
            return out
        else:
            out.append(_res("chk-instancia", _FAIL,
                            "La dirección responde pero no parece un GitLab.",
                            f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-instancia", _FAIL,
                        "No se pudo llegar a esa dirección.", type(exc).__name__))
        for cid in ("chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN, "No se pudo probar: la dirección no responde."))
        return out

    if not token:
        for cid, msg in (("chk-token",    "Falta pegar el token."),
                         ("chk-scope",    "No se pudo probar: falta el token."),
                         ("chk-proyecto", "No se pudo probar: falta el token.")):
            out.append(_res(cid, _FAIL if cid == "chk-token" else _UNKNOWN, msg))
        return out

    # chk-token
    try:
        r = _get(base, "/user", token)
        if r.status_code == 200:
            out.append(_res("chk-token", _OK,
                            f"Token válido (usuario: {r.json().get('username', '?')})."))
        elif r.status_code in (401, 403):
            out.append(_res("chk-token", _FAIL,
                            "El token no sirve: está mal copiado, venció o fue revocado."))
        else:
            out.append(_res("chk-token", _UNKNOWN,
                            "Respuesta inesperada al validar el token.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-token", _UNKNOWN, "No se pudo validar el token.", type(exc).__name__))

    # chk-scope — GitLab 15.x+; 404 en tokens de proyecto o versiones viejas ⇒ unknown, no rojo
    try:
        r = _get(base, "/personal_access_tokens/self", token)
        if r.status_code == 200:
            scopes = r.json().get("scopes") or []
            if "api" in scopes:
                out.append(_res("chk-scope", _OK, "El token tiene el permiso 'api'."))
            elif "read_api" in scopes:
                out.append(_res("chk-scope", _FAIL,
                                "El token solo puede LEER ('read_api'). Stacky no va a poder "
                                "comentar ni cerrar tickets.", f"permisos: {', '.join(scopes)}"))
            else:
                out.append(_res("chk-scope", _FAIL,
                                "Al token le falta el permiso 'api'.",
                                f"permisos: {', '.join(scopes) or 'ninguno'}"))
        else:
            out.append(_res("chk-scope", _UNKNOWN,
                            "Tu GitLab no informa los permisos del token. "
                            "Revisá a mano que tenga 'api'.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-scope", _UNKNOWN,
                        "No se pudieron consultar los permisos.", type(exc).__name__))

    # chk-proyecto
    pp = (project_path or "").strip()
    if not pp:
        out.append(_res("chk-proyecto", _FAIL, "Falta el path del proyecto."))
        return out
    enc = urllib.parse.quote(pp, safe="") if not pp.isdigit() else pp
    try:
        r = _get(base, f"/projects/{enc}", token)
        if r.status_code == 200:
            body = r.json()
            if body.get("issues_enabled") is False:
                out.append(_res("chk-proyecto", _FAIL,
                                "El proyecto existe pero tiene los Issues deshabilitados.",
                                body.get("name_with_namespace", "")))
            else:
                out.append(_res("chk-proyecto", _OK,
                                f"Proyecto encontrado: {body.get('name_with_namespace', pp)}."))
        elif r.status_code == 404:
            out.append(_res("chk-proyecto", _FAIL,
                            "No existe un proyecto con ese path, o tu usuario no tiene acceso."))
        else:
            out.append(_res("chk-proyecto", _UNKNOWN,
                            "Respuesta inesperada al buscar el proyecto.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-proyecto", _UNKNOWN,
                        "No se pudo buscar el proyecto.", type(exc).__name__))
    return out


__all__ = ["run_gitlab_checks"]
```

#### F4.b — `api/setup_guide.py`

```python
GET  /api/setup-guide/<provider>          → { ok, guide }        (404 si no hay guía)
POST /api/setup-guide/gitlab/verify       → { ok, checks: [...] }
```

- El `GET` responde `{"ok": False, "error": "guía deshabilitada"}`, **403**, si `config.config.STACKY_SETUP_GUIDE_ENABLED` es `False`.
- El `POST` responde **403** si `STACKY_SETUP_GUIDE_VERIFY_ENABLED` es `False`.
- Body del `POST`: `{"gitlab_url": str, "gitlab_project": str, "gitlab_token": str, "gitlab_enable_engine": bool}`. **`engine_enabled` NO viene del cliente**: lo lee el servidor de `config.config.STACKY_GITLAB_ENABLED`. Lo único que aporta el cliente es `gitlab_enable_engine`, que el handler pasa como `engine_will_enable` — la **intención declarada**, que nunca pinta verde sobre un motor apagado sin decirlo, solo distingue "apagado y se va a encender al crear" de "apagado y va a seguir apagado" (v2, C5).
- El handler envuelve todo en `try/except Exception` y **nunca** loguea el body. La línea de log es exactamente:
  `logger.info("setup-guide verify gitlab: %s", {c["id"]: c["status"] for c in checks})`.

#### F4.c — Exponer las 3 flags en `/api/diag/health` *(v3, hallazgo B7 — fase nueva, sin ella F5/F6 no compilan)*

**Archivo a EDITAR:** `Stacky Agents/backend/api/diag.py` (handler `health`).

F5 y F6 condicionan el botón GitLab y el botón INFO al valor de las 3 flags, y la regla de la casa es que **las flags de UI se leen de `/api/diag/health`**. Verificado: hoy ese endpoint **no las emite** (las 3 keys tienen 0 hits en código; solo existen dentro de este `.md`). Agregar al cuerpo de la respuesta un sub-objeto `flags`, leyendo de la **instancia** `config.config` (nunca del módulo — gotcha de la casa):

```python
        "flags": {
            "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED": bool(
                getattr(config.config, "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED", True)),
            "STACKY_SETUP_GUIDE_ENABLED": bool(
                getattr(config.config, "STACKY_SETUP_GUIDE_ENABLED", True)),
            "STACKY_SETUP_GUIDE_VERIFY_ENABLED": bool(
                getattr(config.config, "STACKY_SETUP_GUIDE_VERIFY_ENABLED", True)),
        },
```

**Aditivo y backward-compatible:** es una clave nueva; ningún consumidor actual de `/api/diag/health` la lee. El default del `getattr` es `True` para que la UI falle **hacia la funcionalidad** (fail-open), igual que el resto del plan.

Tests, en `test_plan259_setup_guide_api.py`:

| Test | Qué asegura |
|---|---|
| `test_health_expone_las_3_flags` | `GET /api/diag/health` → `body["flags"]` tiene las 3 keys y las 3 en `True` por default. **Estado observable, no una llamada.** |
| `test_health_refleja_la_flag_apagada` | Con `monkeypatch.setattr(config.config, "STACKY_SETUP_GUIDE_ENABLED", False)` ⇒ `body["flags"]["STACKY_SETUP_GUIDE_ENABLED"] is False`. |
| `test_health_no_rompe_las_claves_viejas` | El cuerpo sigue trayendo `version`, `ok`, `healthy` y `source_commit`. **No-regresión.** |

#### Tests (PRIMERO) — `test_plan259_setup_guide_api.py`

`monkeypatch.setattr(services.gitlab_setup_check, "requests", FakeRequests)` — **cero red real** (guard de red del plan 154).

> **Contrato OBLIGATORIO del doble `FakeRequests`** *(v3, hallazgo B4).* El módulo hace `except requests.RequestException`, y ese `requests` es el **símbolo del módulo**, que el test acaba de reemplazar. Ejecutado con el patrón que v2 prescribía: si el doble no expone `RequestException`, los 4 escenarios de red mueren con `AttributeError: type object 'FakeRequests' has no attribute 'RequestException'` en vez de devolver `unknown` — o sea que `test_verify_devuelve_siempre_5_chequeos` y los 3 casos de fallo de red son **rojos por construcción**. El doble tiene que ser, como mínimo:
>
> ```python
> class FakeRequests:
>     """Doble de `requests` para services.gitlab_setup_check.
>
>     RequestException es OBLIGATORIO: el módulo bajo prueba lo usa en su
>     `except`, y tras el monkeypatch se resuelve contra ESTA clase, no
>     contra el paquete real (Plan 259 v3, hallazgo B4).
>     """
>     RequestException = Exception          # <-- sin esto, AttributeError
>     calls: list[dict] = []
>
>     @classmethod
>     def get(cls, url, **kw):
>         cls.calls.append({"url": url, **kw})
>         return cls._next(url)             # 200/401/404/302, o raise cls.RequestException(...)
> ```
>
> Como los escenarios de caída se simulan con `raise FakeRequests.RequestException(...)`, alcanza con que sea `Exception`; **no** hace falta importar `requests` en el test. Un test que afirme esto en su primera línea (`assert hasattr(FakeRequests, "RequestException")`) evita que alguien "simplifique" el doble más adelante.

| Test | Qué asegura |
|---|---|
| `test_get_guia_gitlab_200` | 200, `guide["provider"]=="gitlab"`, 12 pasos, 5 chequeos. |
| `test_get_guia_desconocida_404` | `GET /api/setup-guide/azure_devops` → 404. |
| `test_get_flag_off_403` | `STACKY_SETUP_GUIDE_ENABLED=False` → 403. |
| `test_verify_flag_off_403` | `STACKY_SETUP_GUIDE_VERIFY_ENABLED=False` → 403 **y `FakeRequests.get` con 0 llamadas**. |
| `test_verify_todo_ok` | Fake que responde 200 a `/version`, `/user`, `/personal_access_tokens/self` (con `scopes:["api"]`) y `/projects/...` (con `issues_enabled:True`) → los 5 chequeos en `ok`. |
| `test_verify_devuelve_siempre_5_chequeos` | En **todos** los escenarios (sin URL, URL caída, sin token, 404 de proyecto) hay exactamente 5 resultados y los `id` son los 5 de la guía. **Invariante que la UI necesita para pintar la lista.** |
| `test_verify_url_invalida` | `gitlab_url="gitlab.com"` (sin esquema) → `chk-instancia` en `fail`, los 3 siguientes en `unknown`, **0 llamadas HTTP**. |
| `test_verify_redirect_no_reenvia_token` | Fake que devuelve 302 en `/version` → `chk-instancia` en `fail` y **`FakeRequests.get` fue llamado exactamente 1 vez**, sin `PRIVATE-TOKEN` en esa llamada. **Anti-fuga de credencial.** |
| `test_verify_token_401` | `/user` → 401 ⇒ `chk-token` en `fail`. |
| `test_verify_scope_read_api` | `scopes:["read_api"]` ⇒ `chk-scope` en `fail` con el texto de solo lectura. |
| `test_verify_scope_404_es_unknown` | `/personal_access_tokens/self` → 404 ⇒ `chk-scope` en `unknown`, **no** `fail`. |
| `test_verify_issues_deshabilitado` | `issues_enabled:False` ⇒ `chk-proyecto` en `fail`. |
| `test_verify_project_path_numerico_no_se_encodea` | `gitlab_project="4711"` ⇒ la URL pedida termina en `/projects/4711`. |
| `test_verify_project_path_con_barras_se_encodea` | `"acme/backend/api"` ⇒ `/projects/acme%2Fbackend%2Fapi`. |
| `test_verify_nunca_devuelve_el_token` | El token del body no aparece en `json.dumps(response.get_json())`. |
| `test_verify_timeout_y_sin_redirects` | Toda llamada del fake recibió `timeout=8` y `allow_redirects=False`. |
| `test_engine_enabled_lo_pone_el_servidor` | *(v2.)* Body con `{"engine_enabled": true}` mentiroso (clave que el handler **ignora**) y `config.config.STACKY_GITLAB_ENABLED=False`, **sin** `gitlab_enable_engine` ⇒ `chk-flag` en `fail`. El cliente no puede forzar un verde. |
| `test_chk_flag_intencion_declarada_no_es_rojo` | *(v2, C5 — el camino feliz antes de crear.)* `STACKY_GITLAB_ENABLED=False` + body con `gitlab_enable_engine: true` ⇒ `chk-flag` en `ok` **y** el `message` contiene `se va a activar al crear`. Con la F4 de v1 este caso era `fail` y volvía inalcanzable la DoD. |
| `test_chk_flag_destildada_es_rojo` | `STACKY_GITLAB_ENABLED=False` + `gitlab_enable_engine: false` ⇒ `chk-flag` en `fail`. |
| `test_chk_instancia_401_es_ok_pero_lo_dice` | *(v2, C15.)* `/version` → 401 ⇒ `chk-instancia` en `ok` con un `message` que **no** afirma "es un GitLab" a secas. |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_setup_guide_api.py -v`

**Criterio de aceptación BINARIO:** 20 tests en verde y
```
.venv\Scripts\python.exe -c "from app import create_app; a=create_app(); print(sorted(str(r) for r in a.url_map.iter_rules() if 'setup-guide' in str(r)))"
```
imprime las 2 rutas.

**Flag:** `STACKY_SETUP_GUIDE_ENABLED` y `STACKY_SETUP_GUIDE_VERIFY_ENABLED`, ambas default **ON**.
**Impacto por runtime:** ninguno (HTTP determinista, sin LLM). **Fallback:** si el endpoint responde 403/500, F6 pinta la copia embebida de la guía y oculta el botón "Verificar ahora".
**Trabajo del operador:** ninguno.

---

### F5 — UI: el botón GitLab en el alta (lógica en módulo puro)

**Objetivo:** que "Nuevo Proyecto" ofrezca **🦊 GitLab** con sus campos y su validación.
**Valor:** el pedido literal del operador, parte 1.

**Archivos a CREAR:**
- `Stacky Agents/frontend/src/projects/newProjectGitlabModel.ts` (PURO)
- `Stacky Agents/frontend/src/__tests__/plan259GitlabOnboarding.test.ts`

**Archivos a EDITAR:**
- `Stacky Agents/frontend/src/types.ts`
- `Stacky Agents/frontend/src/api/endpoints.ts`
- `Stacky Agents/frontend/src/components/NewProjectModal.tsx`

#### F5.a — `types.ts`

En `InitProjectPayload` (`:296-329`), el bloque GitLab ya existe (`:324-328`). Agregar **solo** las 2 claves que faltan:

```ts
  gitlab_token?: string;
  gitlab_enable_engine?: boolean;
```

y, fuera de `InitProjectPayload`, el resultado que devuelve F7 *(v2, C9)*:

```ts
export interface GitlabEngineResult {
  changed?: boolean;
  already_on?: boolean;
  skipped?: boolean;
  error?: string;
}
```

`EditProjectModal` ya tipa su form con los 4 campos GitLab (`:41-44`); agregarle `gitlab_token?: string` al tipo del form local para F5.d.

#### F5.0 — De dónde sale `flags` *(v3, hallazgo B7 — BLOQUEANTE de v2; sin esto F5.c y F6.d no compilan)*

v2 escribía *"leído de `/api/diag/health` (las flags de UI viven ahí, gotcha de la casa)"* y daba por hecho que existía un objeto `flags`. **No existe.** Verificado sobre el árbol:

- `NewProjectModal.tsx` importa **solo** `react`, `../api/endpoints`, `../types`, `./ui`, `../hooks/useOptimisticPending` y su `.module.css`. **Cero** `fetch`, cero react-query, cero context de flags.
- `HealthResponse` (`api/endpoints.ts:3290-3302`) tiene claves **fijas** (`version, ok, healthy, shell_v2_enabled, source_commit, built_at, repo_head, build_drift, warnings, db_runtime`) y **no tiene index signature** ⇒ `flags.STACKY_...` **no compila**. Y `npx tsc --noEmit` está hoy en **0 errores**: este plan lo rompería.
- Las 3 flags no se emiten en `/api/diag/health` — eso lo arregla **F4.c**, que es prerequisito de esta fase.

**Archivo a CREAR:** `Stacky Agents/frontend/src/hooks/usePlan259Flags.ts`
**Archivo a EDITAR:** `Stacky Agents/frontend/src/api/endpoints.ts` (extender `HealthResponse`)

1. En `endpoints.ts`, agregar a `HealthResponse` (`:3290-3302`) el campo opcional — **opcional, para no romper ningún consumidor actual**:
   ```ts
     /** Plan 259 F4.c — flags de UI expuestas por el backend. */
     flags?: Record<string, boolean>;
   ```
   `Record<string, boolean>` y no una interfaz cerrada: así la próxima flag de UI no obliga a tocar el tipo.

2. `hooks/usePlan259Flags.ts`, calcado del precedente `hooks/useUiPerfFlags.ts:19-41` (react-query + `staleTime: Infinity` + fail-open):
   ```ts
   import { useQuery } from "@tanstack/react-query";
   import { Health } from "../api/endpoints";

   export interface Plan259Flags {
     onboardingGitlab: boolean;
     setupGuide: boolean;
     setupGuideVerify: boolean;
   }

   /** Fail-open: si /api/diag/health no responde, TODO se muestra.
    *  El backend igual valida (F2), así que mostrar de más nunca corrompe datos. */
   export const PLAN259_FLAGS_FALLBACK: Plan259Flags = {
     onboardingGitlab: true, setupGuide: true, setupGuideVerify: true,
   };

   export function usePlan259Flags(): Plan259Flags {
     const { data } = useQuery({
       queryKey: ["plan259-flags"],
       queryFn: () => Health.get(),
       staleTime: Infinity,
       retry: false,
     });
     const f = data?.flags;
     if (!f) return PLAN259_FLAGS_FALLBACK;
     return {
       onboardingGitlab:  f.STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED !== false,
       setupGuide:        f.STACKY_SETUP_GUIDE_ENABLED !== false,
       setupGuideVerify:  f.STACKY_SETUP_GUIDE_VERIFY_ENABLED !== false,
     };
   }
   ```
   `!== false` y no `=== true`: una clave ausente (backend viejo) se comporta como encendida.

3. La **decisión** de mostrar u ocultar vive en el módulo puro, para que sea testeable sin jsdom. En `newProjectGitlabModel.ts`:
   ```ts
   export function showGitlabTrackerButton(f: { onboardingGitlab?: boolean }): boolean {
     return f.onboardingGitlab !== false;
   }
   export function showInfoButton(trackerType: string, f: { setupGuide?: boolean }): boolean {
     return trackerType === "gitlab" && f.setupGuide !== false;
   }
   ```
   `NewProjectModal.tsx` hace `const flags = usePlan259Flags();` y llama a estas dos. El `.tsx` no decide nada.

#### F5.b — `newProjectGitlabModel.ts` (PURO — sin React, sin fetch)

```ts
/** Plan 259 F5 — lógica pura del alta GitLab. Sin React y sin red:
 *  RTL/jsdom no están instalados en este repo, así que TODO lo testeable vive acá. */

export interface GitlabFormValues {
  gitlab_url?: string;
  gitlab_project?: string;
  gitlab_token?: string;
  gitlab_group?: string;
  gitlab_enable_engine?: boolean;
}

/** Errores por campo del bloque GitLab. {} = válido. */
export function validateGitlabFields(f: GitlabFormValues): Record<string, string> {
  const errs: Record<string, string> = {};
  const url = (f.gitlab_url ?? "").trim();
  const proj = (f.gitlab_project ?? "").trim();
  if (!url) errs.gitlab_url = "Ingresá la URL base de GitLab (ej: https://gitlab.com)";
  else if (!/^https?:\/\//i.test(url)) errs.gitlab_url = "La URL tiene que empezar con http:// o https://";
  else if (/\/api\/v4\/?$/i.test(url)) errs.gitlab_url = "Quitá el /api/v4 del final: lo agrega Stacky";
  if (!proj) errs.gitlab_project = "Ingresá el path del proyecto (ej: grupo/proyecto)";
  else if (/^https?:\/\//i.test(proj)) errs.gitlab_project = "Poné solo el path, sin https:// ni el dominio";
  if (!(f.gitlab_token ?? "").trim()) errs.gitlab_token = "Pegá el token de acceso de GitLab";
  return errs;
}

/** Quita la barra final y un /api/v4 pegado; no toca nada más. */
export function normalizeGitlabUrl(raw: string): string {
  return (raw ?? "").trim().replace(/\/+$/, "").replace(/\/api\/v4$/i, "");
}

/** 'https://gitlab.com/acme/api/-/issues' → 'acme/api'. Un path ya limpio queda igual. */
export function normalizeGitlabProjectPath(raw: string): string {
  let v = (raw ?? "").trim();
  v = v.replace(/^https?:\/\/[^/]+\//i, "");
  v = v.split("/-/")[0];
  return v.replace(/^\/+/, "").replace(/\/+$/, "");
}

/** Default del motor: tildado salvo que el operador lo haya destildado. */
export function engineCheckboxDefault(current: boolean | undefined): boolean {
  return current === undefined ? true : current;
}

/** Orden DOM del bloque GitLab, para el foco-al-primer-error (patrón NP_FIELD_DOM_ORDER). */
export const GITLAB_FIELD_DOM_ORDER = ["gitlab_url", "gitlab_project", "gitlab_token"] as const;
```

#### F5.c — `NewProjectModal.tsx`

1. `EMPTY` (`:13-38`): agregar `gitlab_url: ""`, `gitlab_project: ""`, `gitlab_group: ""`, `gitlab_token: ""`, `gitlab_enable_engine: true`.
2. Cuarto botón en `trackerRow` (`:372-394`), después de Mantis:
   ```tsx
   <button type="button"
     className={`${styles.trackerBtn} ${isGitlab ? styles.trackerBtnActive : ""}`}
     onClick={() => setTrackerType("gitlab")}>🦊 GitLab</button>
   ```
   Renderizado solo si `showGitlabTrackerButton(flags)` — la función pura de **F5.0**, alimentada por `usePlan259Flags()`. Si `/api/diag/health` no responde, se **muestra** (fail-open hacia la funcionalidad; el backend igual valida). *(v3: v2 escribía `flags.STACKY_...` sin que `flags` existiera ni compilara — hallazgo B7.)*
   **Clase CSS:** reusar `styles.trackerBtn` + `styles.trackerBtnActive`, igual que hace el botón GitLab de Edición (`EditProjectModal.tsx:449`). **No** crear un `.trackerBtnGitlab` con el naranja del zorro: `uiDebtBaseline.json:41` congela `NewProjectModal.module.css` en **24** hex y un color literal más rompe `uiDebtRatchet`. Si se quisiera color propio, va con un token de `theme.css`, nunca con un hex.
3. `const isGitlab = form.tracker_type === "gitlab";` junto a `:248-250` (donde ya viven `isAdo`, `isJira`, `isMantis`).
4. Bloque `{isGitlab && (...)}` con `Field` + `Input`, ids `np-gitlab_url`, `np-gitlab_project`, `np-gitlab_token`, `np-gitlab_group`:
   - URL base — placeholder `Ej: https://gitlab.com`
   - Path del proyecto — placeholder `Ej: grupo/subgrupo/proyecto`
   - Token de acceso — `type="password"`, placeholder `Pegá el token con permiso 'api'`
   - `<details>` "🔍 Opciones avanzadas GitLab" → Grupo (para épicas nativas)
   - `Checkbox` `label="Activar el motor GitLab (necesario para que sincronice)"`, `checked={form.gitlab_enable_engine !== false}`
   - `<p className={styles.note}>` con: `Las credenciales se guardan cifradas en backend/projects/{nombre}/auth/gitlab_auth.json`
5. `validate` (`:199-220`): `if (f.tracker_type === "gitlab") return { ...errs, ...validateGitlabFields(f) };` **antes** del `else` de Mantis — hoy ese `else` es el catch-all y aplicaría reglas de Mantis a GitLab.
6. `NP_FIELD_DOM_ORDER` (`:223`): insertar `"gitlab_url","gitlab_project","gitlab_token"` después de `"mantis_token"`.
7. `buildPayload` (`:79-85`): si es GitLab, normalizar con `normalizeGitlabUrl` / `normalizeGitlabProjectPath` antes de enviar.
8. **Cero `style={{}}`**: todo por clases de `NewProjectModal.module.css` (ratchet `uiDebtRatchet`).
9. **Dónde se pinta `gitlab_engine`** *(v2, hallazgo C9 — v1 decía "F5 lo pinta" sin decir cómo, y el modal se cierra).* `handleSubmit` (**`:225-246`**, v3: v2 lo anclaba en `:229`) hoy hace `onCreated(...); onClose();` en el camino feliz (`:238-239`): cualquier mensaje pintado adentro del modal sería invisible. Regla exacta:
   - Si `result.gitlab_engine` **no existe** o trae `changed === true` / `already_on === true` / `skipped === true`, el flujo **no cambia**: `onCreated(...); onClose();`.
   - Si trae `error`, el modal **no se cierra**: se setea `setError("El proyecto se creó, pero no se pudo activar el motor GitLab. Activalo en Configuración → Paridad de proveedores.")` y se muestra un botón "Listo" que llama `onCreated(...)` + `onClose()`. El proyecto YA existe: el mensaje informa, no bloquea.
   - La decisión de qué texto corresponde vive en el módulo puro, testeada: `export function engineNoticeFor(r: GitlabEngineResult | undefined): { level: "none" | "info" | "warn"; text: string }`.

10. **El rechazo de la flag OFF llega como excepción, no como `result.ok === false`** *(v3, hallazgo B11).* `Projects.init` usa `api.post`, que en `api/client.ts:206-209` hace `throw new Error(\`${res.status} ${res.statusText}: ${text}\`)` para **cualquier** respuesta no-2xx. O sea que la rama `else` de `handleSubmit` (`result.ok === false`, `:241`) es **inalcanzable en la práctica**: el 400 de `test_flag_off_rechaza_explicito` cae en el `catch` y hoy el operador leería, literal, `400 BAD REQUEST: {"ok": false, "error": "El alta de proyectos GitLab está apagada (...)"}`. Un mensaje "explícito" servido como JSON crudo no es explícito. Fix, en el módulo puro para que sea testeable:
    ```ts
    /** Saca el mensaje humano de un Error de api.* ("400 BAD REQUEST: {json}").
     *  Devuelve el texto crudo si no hay JSON parseable. */
    export function humanizeApiError(raw: string): string {
      const i = raw.indexOf("{");
      if (i < 0) return raw;
      try {
        const body = JSON.parse(raw.slice(i));
        return String(body.error || body.message || raw);
      } catch { return raw; }
    }
    ```
    y en el `catch` de `handleSubmit`: `setError(humanizeApiError(e?.message || "Error de conexión"))`.
    **No** se cambia `Projects.init` a `rawPost`: tocar el camino que usan los otros 3 trackers está fuera del alcance de este plan y sería una regresión de superficie mucho mayor que el fix.
    Tests en `plan259GitlabOnboarding.test.ts`: `humanizeApiError('400 BAD REQUEST: {"ok":false,"error":"X"}') === "X"`; `humanizeApiError("Error de conexión") === "Error de conexión"`; `humanizeApiError('500 X: no-json{') === '500 X: no-json{'`.

#### F5.d — `EditProjectModal.tsx`: cerrar la trampa que ya estaba ahí *(v2, hallazgo C4/E10)*

El modal de edición ya ofrece GitLab (botón en **`:447-453`**) y sus 4 campos (bloque **`:695-753`**), pero: *(v3: anclajes corregidos; v2 decía `:449-452` y `:695-750`. Los símbolos existen, los rangos estaban corridos.)*

1. **Falta el campo Token.** Agregar, dentro del bloque `{isGitlab && (...)}`, después de "Proyecto (namespace/repo)":
   ```tsx
   <Field label="Token de acceso (dejalo vacío para no cambiarlo)" labelClassName={styles.label}>
     {(ctl) => (
       <Input {...ctl} className={styles.input} type="password"
         placeholder="Pegá el token con permiso 'api'"
         value={form.gitlab_token ?? ""}
         onChange={(e) => patch("gitlab_token", e.target.value)} />
     )}
   </Field>
   ```
   El backend ya lo acepta (F2, Cambio 6) y solo escribe si viene no vacío.
   > *(v3)* `patch` está tipado `patch(key: keyof InitProjectPayload, value: unknown)` (`EditProjectModal.tsx:191`), así que `patch("gitlab_token", …)` **no compila** hasta que F5.a agregue `gitlab_token?: string` a `InitProjectPayload`. Por eso **F5.a va antes que F5.d**, sin excepción. El form local es `useState<Partial<InitProjectPayload>>` (`:18`): con la clave en el tipo base alcanza, no hay tipo local aparte que tocar.

2. **La nota de `:750` es falsa y hay que reemplazarla.** *(v3: el texto está en la línea `:750`, dentro del `<p className={styles.note}>` de `:749-751`.)* Hoy dice *"El archivo debe contener solo el token en texto plano (sin comillas ni saltos de línea extra)"*, pero `gitlab_client._load_token_from_file` hace `json.loads` (`gitlab_client.py:87`): un `.txt` con el token pelado **nunca** funcionó. Texto nuevo, exacto:
   ```
   Es un archivo JSON con la forma {"token": "..."} . Si lo dejás vacío, Stacky usa
   auth/gitlab_auth.json dentro de la carpeta del proyecto y guarda ahí el token cifrado.
   ```
3. **El campo `gitlab_auth_file` se sigue enviando en el PATCH** y el backend lo preserva (F2). Prohibido borrarlo del modal: es la ruta que el operador pudo haber cargado antes de este plan.
4. Botón **ℹ️ INFO** también acá, con la misma condición que en el alta (F6.d), para que la guía esté donde el operador está mirando.
5. **Cero `style={{}}` nuevo.**

#### Tests (PRIMERO) — `plan259GitlabOnboarding.test.ts`

| Test | Qué asegura |
|---|---|
| `valida url vacia` | `validateGitlabFields({})` trae `gitlab_url`, `gitlab_project`, `gitlab_token`. |
| `valida url sin esquema` | `"gitlab.com"` ⇒ error de esquema. |
| `rechaza /api/v4 al final` | `"https://gitlab.com/api/v4"` ⇒ error con el texto de quitar `/api/v4`. |
| `acepta config completa` | URL + path + token ⇒ `{}`. |
| `rechaza url completa como path` | `gitlab_project="https://gitlab.com/acme/api"` ⇒ error. |
| `normaliza barra final` | `normalizeGitlabUrl("https://gitlab.com/")` ⇒ `"https://gitlab.com"`. |
| `normaliza /api/v4` | `"https://gl.io/api/v4"` ⇒ `"https://gl.io"`. |
| `normaliza path desde url completa` | `"https://gitlab.com/acme/backend/api/-/issues"` ⇒ `"acme/backend/api"`. |
| `path limpio no se toca` | `"acme/api"` ⇒ `"acme/api"`. |
| `path numerico no se toca` | `"4711"` ⇒ `"4711"`. |
| `motor tildado por default` | `engineCheckboxDefault(undefined) === true`; `engineCheckboxDefault(false) === false`. |
| `orden dom cubre los 3 obligatorios` | `GITLAB_FIELD_DOM_ORDER` tiene exactamente las 3 keys que `validateGitlabFields({})` reporta. **Sin esto, el foco-al-primer-error apunta a un campo inexistente.** |
| `aviso de motor: sin resultado no dice nada` | *(v2, C9.)* `engineNoticeFor(undefined)` ⇒ `level:"none"`. |
| `aviso de motor: encendido` | `{changed:true}` ⇒ `level:"info"` y texto con `activado`. |
| `aviso de motor: ya estaba` | `{already_on:true}` ⇒ `level:"info"`. |
| `aviso de motor: destildada` | `{skipped:true}` ⇒ `level:"none"` (el operador lo decidió, no hay nada que avisar). |
| `aviso de motor: error` | `{error:"boom"}` ⇒ `level:"warn"` y el texto nombra `Configuración → Paridad de proveedores`. |

**Comando (desde `Stacky Agents/frontend`):** `npx vitest run src/__tests__/plan259GitlabOnboarding.test.ts`

**Criterio de aceptación BINARIO** *(v3, hallazgo B2 — el de v2 era inalcanzable)*:

1. **20** tests en verde *(17 + los 3 de `humanizeApiError`)*.
2. ```
   npx tsc --noEmit
   ```
   con **0 errores**. El baseline medido es **0**, así que acá sí vale "verde absoluto" — y es el criterio que atrapa el hallazgo B7 si alguien saltea F5.0.
3. ```
   npx vitest run src/__tests__/uiDebtRatchet.test.ts
   ```
   **NO "en verde"**: ese test está **ROJO de fábrica**, baseline medido **1 failed / 2 passed**, por dos regresiones ajenas a este plan (`components/ExecutionDetailDrawer.module.css` 23 > 21 y `components/RunReconciliationCard.module.css` 1 > 0). Criterio real, en dos partes:
   - la salida del test **no nombra ningún archivo de este plan** (`NewProjectModal.tsx`, `NewProjectModal.module.css`, `EditProjectModal.tsx`, `SetupGuideDialog.tsx`, `SetupGuideDialog.module.css`);
   - sigue habiendo **exactamente 2** archivos excedidos, los dos de arriba.
   **Prohibido** correr `UI_DEBT_REGEN=1`: regenerar el baseline taparía tanto la deuda ajena como la propia.
   > Recordatorio de por qué esto importa: `NewProjectModal.tsx` **no figura** en `inlineStyleByFile`, así que su presupuesto de `style={{` es **0**; y `EditProjectModal.tsx` figura con **9**, que es un techo, no una licencia para sumar.
4. `npx vitest run src/__tests__/adhocModalRatchet.test.ts` sin fallos nuevos: su allowlist está topada en `FROZEN_MAX = 11` y **no puede crecer**. Cualquier `.tsx` nuevo con `role="dialog"`, `aria-modal` o `createPortal(` que no importe `Dialog` del barrel `ui` lo rompe.

**Flag:** `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` (default **ON**).
**Impacto por runtime:** ninguno — es la UI del backend, común a los 3. **Fallback:** si `/api/diag/health` no responde, el botón se muestra igual y el backend valida.
**Trabajo del operador:** ninguno.

---

### F6 — UI: el botón INFO y el panel de la guía

**Objetivo:** un botón **ℹ️ INFO** junto al selector de tracker que abre la guía completa, con "Verificar ahora".
**Valor:** el pedido literal del operador, parte 2.

**Archivos a CREAR:**
- `Stacky Agents/frontend/src/projects/setupGuideModel.ts` (PURO)
- `Stacky Agents/frontend/src/components/SetupGuideDialog.tsx`
- `Stacky Agents/frontend/src/components/SetupGuideDialog.module.css`
- `Stacky Agents/frontend/src/__tests__/plan259SetupGuideModel.test.ts`

**Archivos a EDITAR:** `endpoints.ts`, `NewProjectModal.tsx`, `types.ts`.

#### F6.a — `endpoints.ts`

```ts
export const SetupGuide = {
  get: (provider: string) =>
    rawGet<{ ok: boolean; guide?: SetupGuideDoc; error?: string }>(`/api/setup-guide/${provider}`),
  verifyGitlab: (payload: {
    gitlab_url: string; gitlab_project: string; gitlab_token: string;
    gitlab_enable_engine: boolean;
  }) =>
    rawPost<{ ok: boolean; checks?: GuideCheckResult[]; error?: string }>(
      "/api/setup-guide/gitlab/verify", payload),
};
```

> **`rawGet`/`rawPost`, no `api.get`/`api.post`**: el wrapper `api.*` **lanza** en cualquier respuesta no-2xx (gotcha de la casa), y acá un `403` (flag apagada) y un `404` (sin guía) son respuestas normales que hay que pintar, no excepciones.
> **Forma del retorno** *(v2, C12 — para que `npx tsc --noEmit` dé 0):* `rawGet<T>` / `rawPost<T>` devuelven `RawResponse<T>`, **no** el cuerpo. El consumidor escribe `const res = await SetupGuide.get("gitlab"); const guide = res.ok ? res.data?.guide ?? null : null;` — nunca `res.guide`.
> *(v3 — anclajes corregidos y tipo verificado textual.)* `rawPost<T>` se declara en **`api/client.ts:47`** (el `:88` que citaba v2 es su `return`, no su firma) y `rawGet<T>` en **`:96`** (exacto). El tipo, textual de `api/client.ts:28-34`:
> ```ts
> export interface RawResponse<T> {
>   status: number;
>   ok: boolean;
>   data: T | null;
>   /** Error parseado del cuerpo si la respuesta no es ok. */
>   errorBody: GatewayErrorBody | null;
> }
> ```
> con `GatewayErrorBody = { error?, message?, correlation_id?, detail? }` (`:36-41`). Detalle que importa para el fallback de F6.c: `raw*` **no lanza** en 4xx/5xx (deja `data: null` y llena `errorBody`), pero **sí re-lanza** errores de red y abort (`:63-66`, `:110-113`) — o sea que el consumidor necesita `try/catch` **además** de mirar `res.ok`.

#### F6.b — `setupGuideModel.ts` (PURO)

```ts
export type CheckStatus = "ok" | "fail" | "unknown";
export interface GuideCheckResult { id: string; status: CheckStatus; message: string; detail?: string }
export interface GuideStepDoc { id: string; title: string; detail: string; where: string; trap?: string }
export interface GuideCheckDoc { id: string; title: string; fixes_step: string }
export interface SetupGuideDoc {
  provider: string; display_name: string; summary: string;
  required_fields: string[]; steps: GuideStepDoc[]; checks: GuideCheckDoc[];
}

/** Resumen para el encabezado del panel. */
export function summarizeChecks(rs: GuideCheckResult[]): { ok: number; fail: number; unknown: number; verdict: CheckStatus } {
  const ok = rs.filter(r => r.status === "ok").length;
  const fail = rs.filter(r => r.status === "fail").length;
  const unknown = rs.filter(r => r.status === "unknown").length;
  return { ok, fail, unknown, verdict: fail > 0 ? "fail" : unknown > 0 ? "unknown" : "ok" };
}

/** Ids de paso a resaltar: los que arreglan los chequeos en 'fail'. */
export function stepsToHighlight(guide: SetupGuideDoc | null, rs: GuideCheckResult[]): string[] {
  if (!guide) return [];
  const failed = new Set(rs.filter(r => r.status === "fail").map(r => r.id));
  return guide.checks.filter(c => failed.has(c.id)).map(c => c.fixes_step);
}

/** El botón "Verificar ahora" se habilita solo con URL y path cargados. */
export function canVerify(v: { gitlab_url?: string; gitlab_project?: string }): boolean {
  return Boolean((v.gitlab_url ?? "").trim()) && Boolean((v.gitlab_project ?? "").trim());
}

/** Copia embebida mínima si el endpoint no responde. NUNCA deja al operador sin nada. */
export const GITLAB_FALLBACK_GUIDE: SetupGuideDoc = { /* provider gitlab, summary + 3 pasos:
   gl-01-instancia, gl-02-token, gl-04-project-path, checks: [] */ };

/** true si la guía viene del servidor; false si es la copia embebida. */
export function isServerGuide(g: SetupGuideDoc | null): boolean {
  return Boolean(g) && g !== GITLAB_FALLBACK_GUIDE;
}
```

#### F6.c — `SetupGuideDialog.tsx`

- Usa `Dialog` canónico con `size="lg"`, `title={`Cómo configurar ${guide.display_name}`}`. **No** reimplementa portal, focus-trap ni Escape. Props verificadas contra `components/ui/Dialog.tsx:17-45`: `open`, `onClose`, `title`, `size?: "sm"|"md"|"lg"`, `children`, `footer?`, `closeGuard?`, `bare?`. **Ojo:** `size` se **ignora** si `bare === true` (`Dialog.tsx:183-185`) — no pasar `bare`.
- **DÓNDE SE MONTA** *(v3, hallazgo B12 — v2 no lo decía y el default rompía la UX)*. `NewProjectModal.tsx` y `EditProjectModal.tsx` **no usan `Dialog`**: son overlays a mano (`<div className={styles.backdrop}>` / `styles.panel`, `NewProjectModal.tsx:253-254`), sin `role="dialog"` ni `aria-modal` — por eso escapan del `adhocModalRatchet`. Montar `<SetupGuideDialog>` **adentro** del JSX de esos modales anida un portal dentro de un overlay ad-hoc: doble backdrop, y doble `inert` sobre `#root` por el `openDialogCount` de `Dialog`. Regla: `SetupGuideDialog` se renderiza como **hermano** del modal, no como hijo —
  ```tsx
  return (
    <>
      <div className={styles.backdrop}> …el modal de siempre… </div>
      <SetupGuideDialog open={guideOpen} onClose={() => setGuideOpen(false)} … />
    </>
  );
  ```
  El estado `guideOpen` sigue viviendo en el modal (es quien tiene los valores del formulario para "Verificar ahora"); lo único que cambia es el punto de montaje. Verificación manual, una sola vez: abrir la guía y confirmar **un solo** backdrop y que Escape cierra la guía sin cerrar el modal de alta.
- Estructura: resumen → lista numerada de pasos (badge `where`: `GitLab` / `Stacky` / `Windows`; la `trap` en una tira `⚠️`) → bloque "Verificar ahora".
- Un paso resaltado por `stepsToHighlight` lleva la clase `stepHighlight` y un `aria-current="step"`.
- Botón "Verificar ahora" `disabled={!canVerify(values)}`; mientras corre, `aria-busy`.
- Resultados: una fila por chequeo con `✅ / ❌ / ❔`, el `message` y, si es `fail`, `→ ver paso N`.
- **Fallback:** si `SetupGuide.get` responde no-2xx o tira, se pinta `GITLAB_FALLBACK_GUIDE` con una tira `Mostrando la guía básica embebida: no se pudo leer la guía del servidor.` y el bloque de verificación oculto.
- **Cero `style={{}}`** (ratchet `uiDebtRatchet` es `forcedZero` para archivos nuevos).
- El token **no** se guarda en estado del diálogo: se pasa como argumento a `verifyGitlab` y se descarta.

#### F6.d — El botón INFO en `NewProjectModal.tsx`

En la fila del selector, después de los 4 botones:

```tsx
{guideAvailable && (
  <button type="button" className={styles.btnInfo} onClick={() => setGuideOpen(true)}
          title="Cómo configurar este sistema de tickets" aria-label="Información de configuración">
    ℹ️ INFO
  </button>
)}
```

`guideAvailable` = `showInfoButton(form.tracker_type, flags)` — la función pura de **F5.0**, con `flags` de `usePlan259Flags()`. En este plan **solo GitLab tiene guía**; el botón no aparece para los otros 3 (honesto: nada de un INFO que abre un panel vacío).

> **`styles.btnInfo` NO EXISTE** *(v3, hallazgo B9)*. Grep sobre **todo** `frontend/src`: **0 matches** de `btnInfo`, ni en `NewProjectModal.module.css` ni en ningún otro `.module.css`. Hay que crearla en `NewProjectModal.module.css`, y **sin un solo hex nuevo**: `uiDebtBaseline.json:41` congela ese archivo en **24** colores literales y el ratchet no admite 25. Regla: la clase se define con las variables que `theme.css` ya expone (`var(--accent)`, `var(--fg)`, `var(--border)`, `var(--radius)`) y con las mismas medidas que `.trackerBtn` (`:155`), del que puede heredar por composición. Cero `style={{}}` inline: `NewProjectModal.tsx` no figura en `inlineStyleByFile`, o sea presupuesto **0**.

#### Tests (PRIMERO) — `plan259SetupGuideModel.test.ts`

| Test | Qué asegura |
|---|---|
| `resumen todo ok` | 5 `ok` ⇒ `{ok:5,fail:0,unknown:0,verdict:"ok"}`. |
| `un fail manda` | 4 `ok` + 1 `fail` ⇒ `verdict:"fail"`. |
| `unknown sin fail` | 4 `ok` + 1 `unknown` ⇒ `verdict:"unknown"`. |
| `lista vacia` | `[]` ⇒ `verdict:"ok"` y los 3 contadores en 0. |
| `resalta el paso del check fallado` | `chk-token` en `fail` ⇒ `["gl-02-token"]`. |
| `resalta varios sin repetir orden` | 2 fails ⇒ los 2 `fixes_step`, en el orden de `guide.checks`. |
| `no resalta si no hay guia` | `stepsToHighlight(null, [...]) === []`. |
| `no resalta los ok` | Todos `ok` ⇒ `[]`. |
| `canVerify exige url y path` | 4 combinaciones cubiertas. |
| `fallback tiene contenido` | `GITLAB_FALLBACK_GUIDE.steps.length >= 3` y todos con `title` y `detail` no vacíos. |
| `isServerGuide distingue` | `isServerGuide(GITLAB_FALLBACK_GUIDE) === false`; con un doc del servidor, `true`; con `null`, `false`. |

**Comando:** `npx vitest run src/__tests__/plan259SetupGuideModel.test.ts`

**Criterio de aceptación BINARIO** *(v3, B2)*: 11 tests en verde; `npx tsc --noEmit` en **0 errores**; y `uiDebtRatchet` / `adhocModalRatchet` bajo la **misma regla de baseline** que fija F5 (el `uiDebtRatchet` está rojo de fábrica con 2 archivos ajenos excedidos: el criterio es que ningún archivo de este plan aparezca en la salida y que sigan siendo exactamente 2). **Prohibido** `UI_DEBT_REGEN=1`.

**Flag:** `STACKY_SETUP_GUIDE_ENABLED` (panel) y `STACKY_SETUP_GUIDE_VERIFY_ENABLED` (botón verificar), ambas **ON**.
**Impacto por runtime:** ninguno. **Fallback:** guía embebida si el servidor no responde; el botón de verificar se oculta si su flag está OFF.
**Trabajo del operador:** ninguno (el INFO es opcional; si no lo abre, el alta funciona igual).

---

### F7 — Encender el motor GitLab en el mismo acto de creación (HITL, visible, reversible)

**Objetivo:** que el proyecto recién creado **sincronice al primer intento**, sin mandar al operador a otra pantalla.
**Valor:** sin esta fase el KPI "sincroniza al primer intento" queda en 0 %: `STACKY_GITLAB_ENABLED` nace en `false` (E6).

**Archivos a EDITAR:**
- `Stacky Agents/backend/api/harness_flags.py` *(v2 — extracción del camino real, hallazgo C1)*
- `Stacky Agents/backend/api/projects.py`

**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_enable_engine.py`

> **v2 — POR QUÉ CAMBIÓ ESTA FASE ENTERA (hallazgo C1, BLOQUEANTE).** La v1 llamaba `services.harness_flags.apply_updates({"STACKY_GITLAB_ENABLED": "true"})` afirmando que eso hacía ".env + os.environ + hot-apply". **Es falso.** El docstring de esa función (`services/harness_flags.py:5709`) dice, textual: *"No persiste ni aplica (eso es responsabilidad del endpoint)"* — solo valida y castea, y **devuelve** el dict tipado. El camino real vive en `api/harness_flags.py:118-175`. Con la v1, la perilla nunca se encendía, el KPI "sincroniza al primer intento" quedaba en 0 %, y los 6 tests de la fase —que **espiaban `apply_updates`**— daban los 6 en verde. Es el falso verde de manual que los planes 254/255 vinieron a matar.

#### F7.a — Extraer el camino real como función reusable

En `api/harness_flags.py`, **antes** de `put_harness_flags` (`:118`), agregar la función que hoy está inlineada en el handler, y hacer que el handler la llame (mismo comportamiento, cero cambio funcional para el endpoint):

```python
def set_flag_values(raw_updates: dict) -> dict:
    """Plan 259 F7 — valida + persiste + hot-aplica flags del arnés.

    Es EXACTAMENTE lo que hacía inline put_harness_flags (pasos 1-3 de su
    docstring), extraído para que se pueda encender una perilla desde código sin
    hacer un POST a nuestro propio servidor. `apply_updates` por sí sola NO
    persiste ni aplica (services/harness_flags.py:5709).

    Devuelve el dict tipado de lo aplicado. Propaga ValueError si una key no
    existe o el valor no castea (el endpoint lo traduce a 400).
    """
    from services.harness_flags import apply_updates, _REGISTRY_INDEX
    from config import config

    typed = apply_updates(raw_updates)                     # 1. validar + castear

    env_strings: dict[str, str] = {}
    for key, val in typed.items():
        env_strings[key] = ("true" if val else "false") if isinstance(val, bool) else str(val)
    _write_env(env_strings)                                # 2. persistir .env + os.environ

    for key, val in typed.items():                         # 3. hot-apply al singleton
        if not _REGISTRY_INDEX[key].env_only:
            try:
                setattr(config, key, val)
            except (AttributeError, TypeError) as exc:
                logger.warning("hot-apply fallback para %s: %s", key, exc)
    return typed
```

`put_harness_flags` queda con su cuerpo reemplazado por `typed = set_flag_values(raw_updates)`; **no se toca** su contrato HTTP ni su respuesta (`applied`, `restart_required_keys`).

> **Alcance EXACTO del `try` (v3, hallazgo B14).** v2 decía "dentro del `try/except ValueError` ya existente" y afirmaba "cero cambio funcional". No es lo mismo: hoy ese `try` envuelve **solo** `apply_updates` (`api/harness_flags.py:139-142`); `_write_env` y el hot-apply quedan **afuera**, así que un `ValueError` de la persistencia sale por el manejador genérico y da **500**. Metiendo todo adentro del `try`, ese mismo fallo pasaría a dar **400** — un cambio de contrato silencioso en el endpoint que usa medio sistema. Escritura correcta, que sí es cero-cambio:
> ```python
>     try:
>         typed = apply_updates(raw_updates)      # el ÚNICO paso que puede dar 400
>     except ValueError as exc:
>         return jsonify({"ok": False, "error": str(exc)}), 400
>     set_flag_values(raw_updates, typed=typed)   # persistir + hot-apply, FUERA del try
> ```
> es decir, `set_flag_values(raw_updates, typed=None)` acepta el dict ya casteado para no validar dos veces, y cuando se la llama desde `_enable_gitlab_engine` (F7.b) valida ella misma. Cubierto por `test_endpoint_de_flags_sigue_igual` y por `test_endpoint_500_si_falla_persistir` (nuevo): con `_write_env` lanzando `ValueError`, `PUT /api/harness-flags` responde **500**, no 400.
>
> **Símbolos verificados presentes (v3):** `logger` en `api/harness_flags.py:19`, `_write_env` en `:32`, `put_harness_flags` en `:118`, y `from services.harness_flags import apply_updates, _REGISTRY_INDEX` ya se hace en `:130`. Los 3 pasos que `set_flag_values` extrae están textualmente en `:139-176`. La extracción de v2 es **correcta**; lo único que se corrige es el borde del `try`.

#### F7.b — El disparo desde el alta

En `api/projects.py`:

```python
def _enable_gitlab_engine() -> dict:
    """Plan 259 F7 — enciende STACKY_GITLAB_ENABLED por el camino canónico de la
    casa: api.harness_flags.set_flag_values (.env + os.environ + hot-apply).

    Se dispara SOLO desde init_project con tracker_type="gitlab" y la casilla
    `gitlab_enable_engine` tildada — es decir, tras un clic explícito del operador
    en "Crear e inicializar". NO hay ningún camino automático que llegue acá.
    Best-effort: si falla, el proyecto igual se crea y se informa en la respuesta.
    """
    try:
        import config as _config
        if bool(getattr(_config.config, "STACKY_GITLAB_ENABLED", False)):
            return {"changed": False, "already_on": True}
        from api.harness_flags import set_flag_values
        set_flag_values({"STACKY_GITLAB_ENABLED": True})
        logger.info("Plan 259 F7: STACKY_GITLAB_ENABLED encendido al crear un proyecto GitLab")
        return {"changed": True, "already_on": False}
    except Exception as exc:
        logger.warning("Plan 259 F7: no se pudo encender STACKY_GITLAB_ENABLED: %s", exc)
        return {"changed": False, "already_on": False, "error": str(exc)}
```

La respuesta de `init_project` para GitLab suma `"gitlab_engine": engine_result` **por el `return` reescrito en F2 Cambio 5** (no por una asignación suelta), y **F5 punto 9** define exactamente quién lo pinta y dónde.

> **Por qué esto NO viola las reglas.** No es autonomía proactiva: el disparo exige (a) elegir GitLab, (b) dejar tildada una casilla que dice qué hace, (c) apretar "Crear e inicializar". No es destructivo ni irreversible: `apply_updates` es el mismo camino que ya usa el panel de flags, y la perilla se apaga desde ahí. No reduce la seguridad: `STACKY_GITLAB_ENABLED` no abre nada por sí sola — sin un proyecto de tipo `gitlab` la rama ni se evalúa (`tracker_provider.py:130`). Y **no cambia ningún default**: `config.py:1185` sigue diciendo `"false"`.

#### Tests (PRIMERO) — `test_plan259_enable_engine.py`

**Regla de la fase (v2, C1+C8):** el criterio principal de cada test es **estado observable** — el valor de `config.config.STACKY_GITLAB_ENABLED` y el contenido del `.env`. Un spy sobre `set_flag_values` puede acompañar, **nunca** ser la única aserción. Aislamiento obligatorio: `monkeypatch` del archivo `.env` que usa `api.harness_flags._write_env` a `tmp_path` (**nunca** el `.env` real del operador) y restauración de `config.config.STACKY_GITLAB_ENABLED` en el teardown.

| Test | Qué asegura |
|---|---|
| `test_enciende_de_verdad` | Con `STACKY_GITLAB_ENABLED=False`: tras `_enable_gitlab_engine()`, **`config.config.STACKY_GITLAB_ENABLED is True`** y el `.env` de `tmp_path` contiene la línea `STACKY_GITLAB_ENABLED=true`. Devuelve `changed=True`. **Este test es ROJO con la F7 de v1** — es la prueba del hallazgo C1. |
| `test_apply_updates_solo_no_alcanza` | Test-centinela de la trampa: llamar `services.harness_flags.apply_updates({"STACKY_GITLAB_ENABLED": True})` **no** cambia `config.config.STACKY_GITLAB_ENABLED` ni escribe el `.env`. Congela por qué existe `set_flag_values` y evita que alguien "simplifique" volviendo a v1. |
| `test_no_toca_si_ya_estaba_on` | Con `True`: `already_on=True`, el `.env` **no se modificó** (mtime/contenido idéntico). |
| `test_falla_no_rompe_el_alta` | `set_flag_values` lanza ⇒ `POST /api/init_project` responde **200**, el `config.json` existe y `gitlab_engine.error` está poblado. |
| `test_checkbox_destildada_no_enciende` | Body con `gitlab_enable_engine: false` ⇒ `config.config.STACKY_GITLAB_ENABLED` sigue en `False`, `gitlab_engine.skipped is True` y el proyecto se creó igual. |
| `test_no_se_dispara_en_otros_trackers` | Alta ADO / Jira / Mantis ⇒ la flag sigue en `False` **y** la respuesta no trae `gitlab_engine` (cubre también C2). |
| `test_no_se_dispara_en_patch` | `PATCH` a un proyecto GitLab ⇒ la flag sigue en `False`. Encender es del alta, no de la edición. |
| `test_endpoint_de_flags_sigue_igual` | *(v2 — no-regresión de la extracción F7.a.)* `PUT /api/harness-flags` con `{"updates": {"STACKY_SETUP_GUIDE_ENABLED": false}}` responde 200, trae `applied` y `restart_required_keys`, y deja `config.config.STACKY_SETUP_GUIDE_ENABLED is False`. |
| `test_endpoint_400_si_key_desconocida` | *(v3, B14.)* `PUT /api/harness-flags` con una key inexistente ⇒ **400** (el `ValueError` de `apply_updates` sigue siendo el único camino a 400). |
| `test_endpoint_500_si_falla_persistir` | *(v3, B14 — congela el borde del `try`.)* Con `_write_env` monkeypatcheado para lanzar `ValueError("disco lleno")` ⇒ el endpoint responde **500**, no 400. Sin este test, meter la persistencia adentro del `try` pasa desapercibido. |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_enable_engine.py -v`

**Criterio de aceptación BINARIO:** **9 tests en verde** (los 8 de la tabla + el centinela de abajo). *(v2, C13: el comando `python -c "...\"...\""` de v1 dependía de cómo PowerShell 5.1 parte las comillas escapadas y del `cwd`; se reemplaza por un test, que es determinista en los 3 runtimes.)*
```
.venv\Scripts\python.exe -m pytest tests/test_plan259_enable_engine.py::test_default_de_config_no_se_movio -v
```
con el test:
```python
def test_default_de_config_no_se_movio():
    src = (pathlib.Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
    assert '"STACKY_GITLAB_ENABLED", "false"' in src
```
**El default no se movió** — y ahora se verifica desde pytest, sin depender del `cwd` ni del parser de comillas de PowerShell.

**Flag:** `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` (default **ON**) — es la misma que gatea toda la rama de alta GitLab.
**Impacto por runtime:** ninguno. **Fallback:** si `apply_updates` falla, el proyecto queda creado y el mensaje dice exactamente dónde prender la perilla a mano.
**Trabajo del operador:** ninguno (casilla tildada por default, destildable).

---

### F8 — Cierre: registro en el arnés, huella de regresión y documentación

**Objetivo:** que los **8** archivos de test nuevos *(v3: 7 + el de F8.b)* queden bajo el ratchet del arnés — **en los dos scripts, cada uno con su sintaxis** — y que el bug de degradación silenciosa quede huellado.
**Valor:** sin esto, la cobertura del arnés se encoge en silencio y `test_ratchet_clasifica_todos_los_tests` (`tests/test_harness_ratchet_meta.py:43-53`) queda **ROJO**.

**Archivos a EDITAR:**
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar al array `HARNESS_TEST_FILES` (`:20`), una línea por archivo, con la forma exacta `tests/test_planNNN_*.py` que exige el regex `^\s*(tests/[\w/]+\.py)\s*$` (`test_harness_ratchet_meta.py:21`):
  ```
  tests/test_plan259_setup_guide_data.py
  tests/test_plan259_project_manager_gitlab.py
  tests/test_plan259_api_projects_gitlab.py
  tests/test_plan259_gitlab_token_dpapi.py
  tests/test_plan259_setup_guide_api.py
  tests/test_plan259_enable_engine.py
  tests/test_plan259_tracker_parity_guard.py
  tests/test_plan259_ratchet_script_parity.py
  ```
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — **SINTAXIS DISTINTA, no es "la misma lista"** *(v3, hallazgo B5 — BLOQUEANTE de v2)*. El array es `$HarnessTestFiles = @(` (línea **13**) y sus elementos van **entre comillas y separados por coma**. Las 7 líneas, en la forma exacta que hay que pegar:
  ```powershell
  "tests/test_plan259_setup_guide_data.py",
  "tests/test_plan259_project_manager_gitlab.py",
  "tests/test_plan259_api_projects_gitlab.py",
  "tests/test_plan259_gitlab_token_dpapi.py",
  "tests/test_plan259_setup_guide_api.py",
  "tests/test_plan259_enable_engine.py",
  "tests/test_plan259_tracker_parity_guard.py",
  "tests/test_plan259_ratchet_script_parity.py",
  ```
  **Por qué esto es bloqueante y no cosmético** (verificado ejecutando, no razonando): el `.ps1` actual parsea con **0 errores**; pegándole las 7 rutas *peladas* del bloque `.sh` de arriba **sigue parseando con 0 errores** — pero el array evalúa a **`Count = 0`**. PowerShell interpreta cada ruta pelada como un **nombre de comando**, no como un string: el ratchet queda vacío **en silencio**, sin una sola línea de error. Con la sintaxis de arriba evalúa a `Count = N`. Es exactamente la clase de bug que rompió el `.ps1` del plan 266 (coma colgante), solo que al revés: allá el parser gritaba, acá no grita nadie.

  **Verificación obligatoria después de editar el `.ps1`** (no alcanza con mirarlo):
  ```powershell
  powershell -NoProfile -Command ". { $c = Get-Content 'scripts/run_harness_tests.ps1' -Raw; $e=$null; [System.Management.Automation.Language.Parser]::ParseInput($c,[ref]$null,[ref]$e) | Out-Null; Write-Output \"errores=$($e.Count)\" }"
  ```
  tiene que decir `errores=0`, **y además** el conteo de rutas `test_plan259` dentro de `$HarnessTestFiles` tiene que ser **7**, no 0.

  *(v2, C16: el meta-ratchet solo parsea el `.sh` (`test_harness_ratchet_meta.py:19`, regex `^\s*(tests/[\w/]+\.py)\s*$`); mantener el `.ps1` en paridad es convención de la casa y **ningún test lo guarda** — por eso el fallo es mudo y por eso la verificación de arriba es obligatoria.)*
- `Stacky Agents/docs/sistema/error_fingerprints.json` — entrada nueva.

> **v2 — la huella de v1 rompía un guardián y además no huellaba nada (hallazgo C3, BLOQUEANTE).** `tests/test_error_fingerprints_catalog.py:18` exige **9 campos**: `id, title, class, status, log_pattern, log_guarded, killed_by, guard_test, self_test`. v1 proponía `id/pattern/meaning/fix` ⇒ `test_campos_obligatorios` **ROJO**. Y el patrón elegido era el mensaje del guard **preexistente** del plan 65, no el bug que este plan mata: la degradación a ADO es silenciosa, **no escribe ninguna línea**, así que no hay patrón que buscar. Lo que sí es huellable es el **rechazo explícito** que F2 introduce en su lugar. Entrada completa a agregar dentro de `d["fingerprints"]`:

```json
{
  "id": "plan259_gitlab_onboarding_off",
  "title": "Alta/edición GitLab rechazada por flag de onboarding apagada",
  "class": "config-flag-off",
  "status": "resolved",
  "log_pattern": "(alta|edición) de proyectos GitLab está apagada",
  "log_guarded": false,
  "killed_by": "plan 259 (alta de proyecto GitLab de primera clase)",
  "killed_commit": "PENDIENTE — completar con el hash del commit de implementación",
  "date_resolved": "PENDIENTE — completar con la fecha de implementación",
  "guard_test": "tests/test_plan259_api_projects_gitlab.py",
  "self_test": {
    "matches": ["El alta de proyectos GitLab está apagada (STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED=false)."],
    "clean": ["issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"]
  },
  "evidence": "backend/api/projects.py (rama gitlab de init_project y update_project); antes de este plan el mismo caso caía al else de azure_devops SIN loguear nada",
  "note": "Antes del plan 259, tracker_type=gitlab en init_project/update_project caía al else de Azure DevOps y CONVERTÍA el proyecto en silencio (cero líneas de log: por eso no hay huella del bug viejo, solo del rechazo explícito que lo reemplaza)."
}
```

**Reglas duras de esta entrada** (las verifica el catálogo, no son opcionales): `status` tiene que estar en `_STATUS_ENUM = {"resolved","open","by_design"}`; `log_pattern` tiene que **compilar** como regex (`test_patrones_compilan`); cada string de **`self_test.matches`** tiene que matchear ese patrón vía `re.search` y cada uno de `self_test.clean` **no** debe matchearlo (`test_self_test_coherente`); y el archivo no puede tener bytes de control crudos (`test_sin_control_chars_crudos`, gotcha del byte ESC de la casa).

> **La clave anidada es `matches`, en PLURAL** *(v3, hallazgo B1 — v2 escribía `"match"`)*. El gate hace, textual, `for sample in fp["self_test"]["matches"]:`. Verificado ejecutando contra el catálogo vivo: las **42** huellas existentes usan `matches`, y con la entrada de v2 el test muere con `KeyError: 'matches'` **antes** de comprobar nada. Corregido arriba. Comprobado también que, con la clave corregida, el `log_pattern` y los dos samples de v2 **sí** son coherentes: `re.search` acierta en el `matches` y no acierta en el `clean`.

> **BASELINE DEL CATÁLOGO — este archivo está ROJO DE FÁBRICA** *(v3, hallazgo B2)*. Medido corriendo, 2 repeticiones idénticas: `tests/test_error_fingerprints_catalog.py` da hoy **3 failed / 5 passed** sobre 8 tests. Causa **ajena a este plan**: la huella `PLAN239-OUTLET-EN-BLANCO` tiene `status: "guarded"` (valor fuera del enum) y **no tiene `self_test`**, lo que rompe `test_campos_obligatorios`, `test_status_enum` y `test_self_test_coherente`. **No es el gotcha del plan 266** (`log_pattern: null`), es otra rotura. **Prohibido arreglarla en este plan**: es alcance de quien sembró esa huella. Consecuencia para F8: el criterio de aceptación **no puede ser "los 8 en verde"** (era inalcanzable en v2) — ver abajo.

- `Stacky Agents/backend/api/projects.py` — docstring del módulo con el bloque de campos GitLab (Cambio 8 de F2).

**Prohibido:** agregar cualquiera de los **8** a `tests/harness_ratchet_allowlist.txt`. Son tests nuevos que pasan aislados; la allowlist solo puede **bajar** (`_ALLOWLIST_MAX = 197`, verificado exacto en `test_harness_ratchet_meta.py:64-77`).

**Tests:**
```
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -v
.venv\Scripts\python.exe -m pytest tests/test_error_fingerprints_catalog.py -v
```

**Criterio de aceptación BINARIO** *(v3, hallazgos B1+B2+B5 — el de v2 era inalcanzable)*:

1. `tests/test_harness_ratchet_meta.py` → **4 passed** (baseline medido: 4 passed; acá sí vale verde absoluto).
2. `tests/test_error_fingerprints_catalog.py` → **exactamente 3 failed / 5 passed**, los **mismos 3** del baseline (`test_campos_obligatorios`, `test_status_enum`, `test_self_test_coherente`, todos por `PLAN239-OUTLET-EN-BLANCO`). Si aparece un 4º fallo, o si el mensaje de alguno de los 3 nombra `plan259_gitlab_onboarding_off`, **la entrada está mal** — es el detector del hallazgo B1.
3. La entrada propia pasa el gate **aislada del rojo ajeno**, con este comando determinista:
   ```
   .venv\Scripts\python.exe -c "import json,re,pathlib; d=json.loads(pathlib.Path('../docs/sistema/error_fingerprints.json').read_text(encoding='utf-8')); fp=[x for x in d['fingerprints'] if x['id']=='plan259_gitlab_onboarding_off'][0]; p=fp['log_pattern']; print(all(re.search(p,s) for s in fp['self_test']['matches']) and not any(re.search(p,s) for s in fp['self_test']['clean']))"
   ```
   imprime `True`. Es el mismo código que corre `test_self_test_coherente`, aplicado **solo** a la huella de este plan.
4. El `.ps1` verifica `errores=0` **y 7 rutas `test_plan259`** en `$HarnessTestFiles` (comando en el bullet del `.ps1`).

*(v2, C3+C13: el comando `python -c` de v1 solo miraba si la cadena `plan259` aparecía en el JSON — daba verde con una entrada de esquema inválido, y encima resolvía `../docs/...` contra el `cwd`. v3 conserva la idea de v2 de usar el guardián real, pero lo acota al baseline medido y le agrega el chequeo aislado de la huella propia, que es el que hubiera atrapado el `match`/`matches`.)*

#### F8.b — [ADICIÓN ARQUITECTO v3] Guardián de paridad `.sh` ↔ `.ps1` del ratchet

**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_ratchet_script_parity.py` (y registrarlo en las dos listas, igual que los otros 7 ⇒ pasan a ser **8**).

**Por qué.** El hallazgo B5 fue posible porque **nada guarda el `.ps1`**: `test_harness_ratchet_meta.py:19-21` parsea **solo** el `.sh`, y el comentario del propio `.ps1` (*"Mantener en sync con run_harness_tests.sh"*) es una convención escrita, no un test. Verificado ejecutando: con las rutas peladas el `.ps1` parsea con 0 errores y el array queda en `Count = 0` — la lista se vacía sin que nada avise. Arreglar el caso de este plan (F8) no impide que el próximo plan repita el error; de hecho ya pasó dos veces (plan 266 con la coma colgante, este con las comillas). Esta fase lo cierra para siempre, y es **barata**: un solo archivo de test, sin tocar producto.

**Diseño — texto, no PowerShell.** El test **no invoca** PowerShell: sería atarlo a un runtime. Parsea los dos archivos con `re` y compara conjuntos. Corre igual en Codex CLI, Claude Code CLI y GitHub Copilot Pro, en Windows y fuera.

```python
_SH  = _BACKEND / "scripts" / "run_harness_tests.sh"
_PS1 = _BACKEND / "scripts" / "run_harness_tests.ps1"

# .sh:  rutas peladas, una por línea       -> tests/foo.py
_SH_RE  = re.compile(r"^\s*(tests/[\w/]+\.py)\s*$", re.M)
# .ps1: rutas ENTRECOMILLADAS, con coma    -> "tests/foo.py",
_PS1_RE = re.compile(r'^\s*"(tests/[\w/]+\.py)"\s*,?\s*$', re.M)
```

| Test | Qué asegura |
|---|---|
| `test_las_dos_listas_tienen_el_mismo_contenido` | `_SH_RE` sobre el `.sh` y `_PS1_RE` sobre el `.ps1` devuelven **el mismo conjunto**. El mensaje de error imprime `solo_en_sh` y `solo_en_ps1` por separado, para que el fallo diga qué falta y dónde. |
| `test_el_ps1_no_tiene_rutas_sin_comillas` | Ninguna línea del `.ps1` matchea `_SH_RE` (la forma pelada del `.sh`). **Este es el test que hubiera atrapado B5**: es el modo de falla exacto — parsea bien, evalúa a nada. |
| `test_las_dos_listas_son_no_vacias` | Ambas tienen `>= 100` entradas. Un regex que deja de matchear por un cambio de formato daría dos conjuntos vacíos e **iguales**, y el primer test pasaría en falso. Este lo tapa. |
| `test_ninguna_ruta_apunta_a_un_archivo_inexistente` | Toda ruta de **ambas** listas existe en disco. `test_harness_ratchet_meta.py` ya lo hace para el `.sh`; acá se extiende al `.ps1`, que no lo tenía. |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_ratchet_script_parity.py -v`
**Criterio de aceptación BINARIO:** los 4 en verde. Y la prueba de que el guardián **sirve**: borrar las comillas de **una** línea del `.ps1` tiene que poner en rojo `test_el_ps1_no_tiene_rutas_sin_comillas` **y** `test_las_dos_listas_tienen_el_mismo_contenido`. *(Verificación manual de una sola vez durante la implementación; se restauran las comillas inmediatamente.)*

**Flag:** ninguna — es un test, no tiene superficie que conmutar ni camino de ejecución en producción.
**Impacto por runtime:** ninguno; `re` y `pathlib` son stdlib y el test **no ejecuta PowerShell**. **Fallback:** N/A.
**Trabajo del operador:** ninguno. **Human-in-the-loop:** intacto — no decide nada, solo avisa.

#### Metadatos de F8 (fase completa)

**Flag:** ninguna (infraestructura de tests y documentación).
**Impacto por runtime:** ninguno. **Fallback:** N/A.
**Trabajo del operador:** ninguno.

---

### F9 — [ADICIÓN ARQUITECTO v2] Guardián de paridad de trackers: que este agujero no pueda volver

**Objetivo:** que sea **imposible** agregar (o dejar a medias) un tracker sin que un test lo diga.
**Valor:** este plan entero existe porque GitLab quedó cableado a medias — botón en Edición, tipo en `types.ts`, 7 módulos de motor — y el alta y el PATCH nunca se enteraron, degradando proyectos a Azure DevOps **durante ~194 planes sin que nada avisara**. Arreglar el caso de GitLab (F1-F8) no impide que pase de nuevo con el quinto tracker. Esta fase sí.

**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_tracker_parity_guard.py`
**Archivos a EDITAR:** ninguno de producto. Si el guardián sale rojo por algo que F1-F8 no cubrieron, se arregla el producto — **nunca** se afloja el guardián.

**Diseño — AST, no regex.** El chequeo recorre el árbol sintáctico de `api/projects.py` y `project_manager.py` con `ast.parse` + `ast.walk`. Está **prohibido** el centinela textual: la casa ya se quemó con eso (gotcha "exigir `config.config` en masa rompe el motor de flags: AST, nunca regex").

**Tabla de nombres — OBLIGATORIA, y cubre las DOS familias** *(v3, hallazgo B3)*.

v2 declaraba la tabla de alias **solo** para `write_{t}_auth` y dejaba `initialize_{t}_project` a la fórmula literal. Verificado ejecutando sobre `project_manager`: los helpers reales son `initialize_ado_project`, `initialize_jira_project`, `initialize_mantis_project` — **`initialize_azure_devops_project` NO existe**. Con la especificación de v2, `test_cada_tracker_tiene_helper_de_alta` fallaba en `azure_devops` **antes de llegar a GitLab**: la [ADICIÓN ARQUITECTO] no pasaba su propio criterio de aceptación. La tabla va **una sola vez** y la usan los dos tests:

```python
TRACKERS = ("azure_devops", "jira", "mantis", "gitlab")   # fuente: frontend/src/types.ts:245 TrackerType

# El producto usa "ado" como abreviatura histórica de azure_devops en project_manager.
# Tabla EXPLÍCITA, no heurística: si mañana se agrega un tracker con nombre corto,
# se declara acá y el guardián sigue siendo honesto.
_SLUG = {"azure_devops": "ado", "jira": "jira", "mantis": "mantis", "gitlab": "gitlab"}

def _init_fn(t: str) -> str:  return f"initialize_{_SLUG[t]}_project"
def _auth_fn(t: str) -> str:  return f"write_{_SLUG[t]}_auth"
```

Con esta tabla, los nombres esperados son `initialize_ado_project` / `write_ado_auth` para `azure_devops`, y `initialize_gitlab_project` / `write_gitlab_auth` para GitLab — que es exactamente lo que F1.a crea. **Verificación del estado actual, ejecutada:** `initialize_{ado,jira,mantis}_project` y `write_{ado,jira,mantis}_auth` existen y están en `__all__`; los dos de `gitlab` no existen todavía (los crea F1.a) — o sea que estos dos tests son **rojos hoy y verdes después de F1.a**, que es la definición de un guardián útil.

| Test | Qué asegura |
|---|---|
| `test_cada_tracker_tiene_helper_de_alta` | Para cada `t` en `TRACKERS`, `project_manager` expone `_init_fn(t)` **y** ese nombre está en `__all__`. |
| `test_cada_tracker_tiene_escritor_de_credencial` | Ídem con `_auth_fn(t)`. |
| `test_la_tabla_de_slugs_cubre_todos_los_trackers` | *(v3.)* `set(_SLUG) == set(TRACKERS)`. Evita que alguien agregue un tracker a `TRACKERS` y se olvide del slug, dejando un `KeyError` en vez de un fallo legible. |
| `test_init_project_ramifica_por_cada_tracker` | Parseando el AST de la función `init_project`: el conjunto de literales string comparados contra `tracker_type` en sus `if/elif` **más** el tracker del `else` cubre exactamente `TRACKERS`. |
| `test_update_project_ramifica_por_cada_tracker` | Ídem sobre `update_project`. **Este es el test que hubiera atrapado el bug original.** |
| `test_has_credentials_conoce_todos_los_trackers` | Llamando la función real: para cada `t`, `_has_credentials("X", t)` mira un archivo **distinto** (4 nombres únicos). Hoy GitLab comparte el de Mantis. |
| `test_todo_tracker_tiene_template_embebido` | Para cada `t`, `t in DEFAULT_TEMPLATES`. Cubre C6/E9 y evita que el próximo tracker herede el perfil de ADO en el deploy congelado. |
| `test_ningun_alta_degrada_el_tipo` | *(property test, el corazón de la fase.)* Para cada `t` en `TRACKERS`: `POST /api/init_project` con el cuerpo mínimo válido de ese tracker ⇒ el `config.json` en disco tiene `issue_tracker.type == t`. Sin excepciones, sin "salvo GitLab". |
| `test_ningun_patch_degrada_el_tipo` | Para cada par `(origen, destino)` de `TRACKERS` (12 combinaciones): crear como `origen`, `PATCH` a `destino` ⇒ el `config.json` queda en `destino`. **Contra el árbol actual falla en las 3 combinaciones que van a GitLab: es la reproducción exacta del bug E2.** |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_tracker_parity_guard.py -v`
Aislamiento: `monkeypatch` de `PROJECTS_DIR` a `tmp_path` en `project_manager` **y** en `api.projects`. Si aparece `SQLITE_LOCKED`, correr el archivo 8-12 veces (gotcha de la casa).

> **Nota sobre `_has_credentials` (v3).** `api/projects.py:77` resuelve `PROJECTS_DIR / name / "auth" / …` **sin** `.upper()`, mientras que todos los `write_*_auth` escriben en `PROJECTS_DIR / name.upper() / "auth"`. No es un bug hoy porque `initialize_project` hace `name = name.upper()` (`project_manager.py:120`) y guarda ese valor en `cfg["name"]` (`:153`), que es lo que `_project_to_dict` le pasa. `test_has_credentials_conoce_todos_los_trackers` debe llamar la función con el nombre **en mayúsculas**, igual que hace el código de producción; llamarla en minúsculas daría un falso rojo que no prueba nada.

**Criterio de aceptación BINARIO:** los **9** tests en verde *(v3: 8 + `test_la_tabla_de_slugs_cubre_todos_los_trackers`)*. Y la prueba de que el guardián **sirve**: comentar la rama `elif tracker_type == "gitlab"` de `update_project` tiene que poner en rojo `test_update_project_ramifica_por_cada_tracker` y `test_ningun_patch_degrada_el_tipo`. *(Verificación manual de una sola vez durante la implementación; se deshace el comentario inmediatamente.)*

**Flag:** ninguna. Es un test; no tiene camino de ejecución en producción ni superficie que conmutar.
**Impacto por runtime:** ninguno — `ast` es stdlib y el test corre igual en los 3. **Fallback:** N/A.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta, en este plan) |
|---|---|---|---|
| R1 | F1 escribe el token cifrado y `GitLabClient` sigue leyéndolo crudo ⇒ **401 con todo "bien configurado"**. | **Alta** si F3 no se hace | F3 es **obligatoria** y va antes de habilitar la UI; `test_lee_token_cifrado_dpapi` cierra el lazo escritura↔lectura. |
| R2 | El chequeo `chk-token` da verde con un `GITLAB_TOKEN` viejo del entorno, tapando el token recién tipeado (E5). | Media | `gitlab_setup_check` **no** usa `GitLabClient` ni lee `os.environ`: manda el header con el token del body y nada más. Cubierto por `test_engine_enabled_lo_pone_el_servidor` y el diseño de `_get`. |
| R3 | Una URL maliciosa/mal tipeada redirige y `requests` reenvía `PRIVATE-TOKEN` a otro host. | Baja, impacto alto | `allow_redirects=False` en toda llamada; un 30x en `/version` **corta** la verificación antes de mandar el token. `test_verify_redirect_no_reenvia_token` lo blinda. |
| R4 | Los tests de F4 salen a internet de verdad y quedan flaky / violan el guard de red del plan 154. | Media | `monkeypatch` del símbolo `requests` **dentro** de `services.gitlab_setup_check`. `test_verify_url_invalida` afirma **0 llamadas**. |
| R5 | ~~`get_default_client_profile("gitlab")` no tiene template y `initialize_project:165-169` explota al crear.~~ **Mal diagnosticado en v1: nunca explota.** Lo que pasa de verdad (E9) es peor porque es mudo: en el **deploy congelado** el proyecto GitLab hereda el `client_profile` de **Azure DevOps**, porque `client_profile_default_templates.py` no tiene GitLab y `_read_default_template` cae a `azure_devops`. | **Certeza, no probabilidad** (verificado: 0 ocurrencias de "gitlab" en ese módulo) | **F1.0** agrega el template embebido copiando literalmente `client_profile_defaults/gitlab.json`, y `test_client_profile_gitlab_en_deploy_congelado` neutraliza `_DEFAULTS_DIR` para probar el camino del ejecutable, no el de dev. |
| R6 | Editar `NewProjectModal.tsx` choca con la sesión paralela viva (memoria: `TicketBoard.tsx`/`UnblockerPage.tsx` bloqueados). | Media | `NewProjectModal.tsx` **no** está en la lista de bloqueados. Aun así: `git worktree list` **antes** de tocar, y commit con `git commit -- "<ruta>"` explícito, sin `add -A`, sin `reset`, sin `amend`. |
| R7 | Las 3 flags nuevas rompen `test_default_known_only_for_curated` por olvidar `_CURATED_DEFAULTS_ON`. | Media | Está explícito en F0.b y verificado por el comando de aceptación de F0 (`test_harness_flags.py`). |
| R8 | El texto de menús de GitLab ("Edit profile" → "Access tokens") cambia en una versión futura. | Media | Los pasos declaran su alcance ("versiones 16.x y 17.x") y **cada uno tiene un chequeo que verifica el resultado**, no el camino: aunque el menú se mueva, `chk-token` sigue diciendo si el token sirve. |
| R9 | F7 escribe el `.env` y pisa algo. | Baja | Es **exactamente** el mismo camino que ya usa el panel de flags, ahora extraído a `set_flag_values` (F7.a) y usado por los dos; `_write_env` (`api/harness_flags.py:32-68`) solo reescribe la clave pedida y preserva el resto. Envuelto en `try/except`: nunca rompe el alta. Los tests de F7 **nunca** tocan el `.env` real (`monkeypatch` a `tmp_path`). |
| R11 | *(v2)* La extracción de `set_flag_values` (F7.a) cambia el comportamiento del endpoint `PUT /api/harness-flags`, que usa medio sistema. | Baja | Es un *move* literal de los pasos 1-3 que ya estaban inline; el handler queda llamándola. `test_endpoint_de_flags_sigue_igual` (F7) y `tests/test_harness_flags.py` corren como no-regresión en la DoD. |
| R12 | *(v2)* Al preservar `auth_file`, un proyecto con una ruta vieja e inválida queda con ella y el token nuevo se escribe en un lugar raro. | Media | `resolve_gitlab_auth_path` es explícita y testeada en los 3 casos (vacío / relativo / absoluto); `write_gitlab_auth` crea el directorio padre; F5.d corrige la nota del modal para que la ruta que se cargue tenga la forma correcta. Preservar es siempre mejor que pisar en silencio: el operador ve la ruta en pantalla y la puede cambiar. |
| R13 | *(v2)* La migración a DPAPI de un `gitlab_auth.json` plano rompe una instalación compartida entre usuarios de Windows. | Media | Está **declarada** en el paso `gl-09-donde-queda` (el operador se entera antes), y el fallback de F3 evita el modo de falla duro: si el archivo no se puede reescribir, se sigue leyendo plano como hoy (`test_archivo_solo_lectura_sigue_dando_el_token`). |
| R14 | *(v2)* Alguien "simplifica" F7 volviendo a `apply_updates` a secas y reintroduce el falso verde. | Media | `test_apply_updates_solo_no_alcanza` es un centinela explícito: afirma que `apply_updates` **no** cambia `config.config` ni el `.env`. Si alguien revierte, ese test lo dice con su propio nombre. |
| R10 | Los tests que tocan la DB fallan con `SQLITE_LOCKED` bajo pytest. | Alta (gotcha conocido) | Correr cada archivo 8-12 veces y envolver la unidad de trabajo en `run_with_retry`. Declarado en F1. **Medido en esta pasada:** los 8 archivos del DoD corrieron 2 veces cada uno **sin un solo `SQLITE_LOCKED`**; los rojos que aparecieron son deterministas, no flaky. |
| R15 | *(v3, B2)* El implementador ve `test_error_fingerprints_catalog` / `uiDebtRatchet` en rojo, cree que los rompió él, y "arregla" rojo ajeno — o peor, regenera el baseline visual y tapa deuda de otros. | **Alta** (los 3 gates ya están rojos) | La DoD trae la tabla de baselines **con números**, y la palabra clave es *"exactamente N failed, los mismos N"*. `UI_DEBT_REGEN=1` está prohibido por escrito en F5, F6 y la DoD. |
| R16 | *(v3, B7)* Se implementa F5/F6 sin F4.c y sin F5.0: `flags` no existe, `HealthResponse` no tiene la clave, y `npx tsc --noEmit` pasa de 0 a N errores. | **Certeza si se saltea el orden** | F4.c y F5.0 son fases propias, y el orden de implementación las pone **antes** de F5.c/F6.d. El criterio `tsc --noEmit == 0 errores` es el detector: el baseline es 0, así que cualquier error nuevo es de este plan. |
| R17 | *(v3, B5)* El `.ps1` queda con el array vacío y nadie se entera, porque ningún test lo parsea y PowerShell no protesta. | **Alta** (fallo mudo, ya pasó en el plan 266) | F8 escribe las 7 líneas **dos veces**, una por sintaxis, y agrega una verificación ejecutable que exige `errores=0` **y** 7 rutas `test_plan259` dentro de `$HarnessTestFiles`. |
| R18 | *(v3, B1)* La huella se escribe con una clave anidada equivocada y el catálogo se rompe, igual que en v1 y v2. | **Alta** (van 2 de 2) | El criterio de F8 no es "el catálogo en verde" (imposible: rojo de fábrica) sino un comando que corre **el mismo `re.search` del gate** sobre la huella de este plan, aislado del rojo ajeno. Es el chequeo que hubiera atrapado `match` vs `matches`. |

---

## 6. Fuera de scope

- Guías de configuración para Azure DevOps, Jira y Mantis. La infraestructura queda lista (`SETUP_GUIDES` es un dict, `guide_exists` decide si se pinta el botón), pero **este plan solo escribe la de GitLab**, que es lo pedido. El botón INFO no aparece para los otros 3.
- Descubrir proyectos GitLab por API para ofrecer un desplegable (lo análogo a "Cargar proyectos de Mantis").
- Épicas nativas de GitLab (`STACKY_GITLAB_EPICS_NATIVE`): el campo Grupo se carga y se guarda, pero encender esa funcionalidad es otro plan.
- Cambiar el default de `STACKY_GITLAB_ENABLED` en `config.py`. *(v2: sigue OFF porque es un default **preexistente** del plan 65 y moverlo es alcance de otro plan — **no** por "excepción dura #3", motivo que el operador invalidó. F7 lo vuelve irrelevante en el camino real. Ver E6 y §3.)*
- Escribir guías de configuración para los otros 3 trackers, o extender F9 a validar la UI del frontend: F9 cubre el backend, que es donde se corrompían los datos.
- Migrar tickets de otro tracker a GitLab (eso es el plan 74 / el migrador Mantis→GitLab del plan 217).
- Soporte de GitLab en el asistente DevOps de pipelines (planes 246-252 ya cubren ese eje).
- Deshabilitar la verificación SSL para GitLab: decisión explícita de **no** ofrecerlo (paso `gl-11-ssl`).

---

## 7. Glosario

| Término | Qué es en este plan |
|---|---|
| **Tracker** | Sistema de tickets del que Stacky lee y en el que escribe: Azure DevOps, Jira, Mantis o GitLab. |
| **`issue_tracker`** | Bloque dentro de `backend/projects/<NOMBRE>/config.json` que describe el tracker del proyecto. Su clave `type` decide todo el ruteo. |
| **Project path (GitLab)** | `grupo/subgrupo/proyecto`. Es lo que va después del dominio en la URL. También se acepta el ID numérico. Stacky codifica las barras como `%2F` (`gitlab_client.py:98-105`). |
| **PAT / Personal Access Token** | Token personal de GitLab. En la guía se lo llama siempre "token de acceso" para no usar la sigla. |
| **Scope `api`** | Permiso del token que habilita leer **y** escribir por la API. `read_api` solo lee. |
| **DPAPI** | Cifrado de Windows atado al usuario que lo hizo. Es como Stacky guarda todas las credenciales. No es portable a otro usuario ni a otra máquina. |
| **Flag del arnés** | Perilla de configuración editable desde Configuración → Arnés en la UI, persistida en el `.env`. Registrada en `FLAG_REGISTRY` (`services/harness_flags.py`). |
| **Excepción para nacer OFF** | *(v2 — corregido: son **2 categorías**, no 4.)* **(A)** la flag quema tokens en **reposo** (loop/daemon/barrido/polling/prefetch que llama a un modelo sin que el operador pida nada); **(B)** escribe en un sistema **real** del operador, destruye datos o le saca la decisión. Nada más califica. En particular, "prerequisito no garantizado en una instalación default" **NO** es una excepción válida: el operador la invalidó porque lo on-demand degrada sin romper. Tampoco "default seguro", "por las dudas" ni ninguna capacidad de solo lectura. |
| **Ratchet del arnés** | Guardia que exige que todo `tests/test_*.py` nuevo figure en `HARNESS_TEST_FILES` o en la allowlist. Lo verifica `tests/test_harness_ratchet_meta.py`. |
| **Módulo puro** | `.py`/`.ts` sin IO, sin red, sin framework: solo datos y funciones. Es lo único testeable en este repo del lado del frontend, porque RTL/jsdom no están instalados. |
| **`config.config`** | La **instancia** de `Config`. Leer la flag del **módulo** `config` devuelve siempre el default y mata el camino OFF (gotcha de la casa, `tracker_provider.py:131-133`). |
| **Degradación silenciosa** | Que el sistema haga algo distinto de lo pedido sin avisar. Es lo que hace hoy `update_project` con GitLab (E2) y lo que este plan elimina. |

---

## 8. Orden de implementación

> **PASO 0 (v3, obligatorio antes de escribir una línea): tomar el baseline.** Correr los 10 comandos de la tabla de la DoD y anotar los números. Sin eso no se puede distinguir "lo rompí yo" de "ya estaba roto", y 3 de esos 10 **están rojos de fábrica**.

1. **F0** — `services/setup_guides.py` (copiar el módulo **tal cual**: ya pasó sus 10 tests) + las 3 flags en los **4** archivos: `config.py`, `services/harness_flags.py` (`_CATEGORY_KEYS` + `FLAG_REGISTRY`), `tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`) y **`services/harness_flags_help.py`** (`PLAIN_HELP`, F0.b.4 — v3, hallazgo B10) + su test.
2. **F1.0** — template GitLab embebido en `services/client_profile_default_templates.py` (solo la constante `GITLAB` y su entrada en `DEFAULT_TEMPLATES`; ese archivo **no tiene `__all__`**).
3. **F1.a** — `initialize_gitlab_project` + `resolve_gitlab_auth_path` + `write_gitlab_auth` en **`project_manager.py`** (archivo distinto, antes de su `__all__`) + su test. *(v3, B6: v2 encadenaba los dos pasos en una sola subsección y mandaba el helper al archivo equivocado.)*
4. **F3** — lector DPAPI + fallback plano en `gitlab_client.py`, **agregando `import logging` y `logger`** (no existen — v3, B13) + su test. **Va antes que F2**: sin esto, todo lo que F2 cree nace con 401.
5. **F7.a** — extraer `set_flag_values` en `api/harness_flags.py`, con el `try/except ValueError` acotado a `apply_updates` (v3, B14), y dejar el endpoint llamándola. Correr `tests/test_harness_flags.py` acá: tiene que seguir en **56 passed**.
6. **F2** — cableado de `api/projects.py` (`engine_result` declarada antes de la cadena, init, patch, `_has_credentials`, `_project_to_dict` **incluido el Cambio 3-bis que tapa la fuga de `ado_project`**, credentials, docstring) + su test.
7. **F7.b** — `_enable_gitlab_engine` + su test.
8. **F4** — `services/gitlab_setup_check.py` + `api/setup_guide.py` + registro del blueprint + **F4.c (`api/diag.py` emite las 3 flags)** + su test, con el `FakeRequests` que expone `RequestException` (v3, B4).
9. **F5.0** — `HealthResponse.flags?` en `endpoints.ts` + `hooks/usePlan259Flags.ts`. *(v3, B7: va **antes** de tocar los `.tsx`, o `npx tsc --noEmit` pasa de 0 errores a N.)*
10. **F5** — `newProjectGitlabModel.ts` + `types.ts` (`gitlab_token`, `gitlab_enable_engine`, `GitlabEngineResult`) + `NewProjectModal.tsx` + **F5.d `EditProjectModal.tsx`** + su test vitest.
11. **F6** — `setupGuideModel.ts` + `SetupGuideDialog.tsx` (montado como **hermano**, no como hijo — v3, B12) + `.module.css` (incluida la clase `btnInfo`, que **no existe** — v3, B9) + `endpoints.ts` + botón INFO + su test vitest.
12. **F9** — guardián de paridad de trackers, con la tabla `_SLUG` única (v3, B3). *(Va acá y no antes: sus 9 tests son la verificación independiente de que F1-F7 quedaron bien. Si algo sale rojo, se arregla el producto, nunca el guardián.)*
13. **F8** — `run_harness_tests.sh` **y** `.ps1` con **su propia sintaxis** (v3, B5) + `error_fingerprints.json` con `self_test.matches` en **plural** (v3, B1) + las verificaciones acotadas al baseline.

---

## 9. Definición de Hecho (DoD)

El plan está hecho cuando **todo** lo siguiente es cierto y verificado corriendo:

- [ ] Los **8 archivos de test backend** en verde, corridos **de a uno** *(v3: 7 + el de F8.b)*. Son archivos **nuevos**: acá sí vale "verde absoluto", no tienen baseline.
  ```
  .venv\Scripts\python.exe -m pytest tests/test_plan259_setup_guide_data.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_project_manager_gitlab.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_gitlab_token_dpapi.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_api_projects_gitlab.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_enable_engine.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_setup_guide_api.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_tracker_parity_guard.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_ratchet_script_parity.py -v
  ```
- [ ] Los **2 archivos de test frontend** en verde:
  ```
  npx vitest run src/__tests__/plan259GitlabOnboarding.test.ts
  npx vitest run src/__tests__/plan259SetupGuideModel.test.ts
  ```
- [ ] **Sin regresiones contra el BASELINE MEDIDO** *(v3, hallazgo B2 — la DoD de v2 exigía "verde" en 3 gates que están rojos de fábrica, o sea que era inalcanzable).* Baseline tomado corriendo cada archivo **de a uno** con `.venv\Scripts\python.exe` (py3.13.5), 2 repeticiones idénticas, cero `SQLITE_LOCKED`, cero flakiness. La regla es **"igual o mejor que este número"**, nunca "verde" a secas:

  | Comando | Baseline medido | Criterio de la DoD |
  |---|---|---|
  | `pytest tests/test_harness_flags.py -v` | **56 passed** | 56 passed |
  | `pytest tests/test_harness_ratchet_meta.py -v` | **4 passed** | 4 passed |
  | `pytest tests/test_plan208_profile_schema.py -v` | **10 passed** | 10 passed |
  | `pytest tests/test_plan218_gitlab_reachable.py -v` | **13 passed** | 13 passed |
  | `pytest tests/test_plan70_smoke_gitlab.py -v` | **5 passed** | 5 passed |
  | `pytest tests/test_harness_flags_requires.py -v` | **9 passed** | 9 passed |
  | `pytest tests/test_error_fingerprints_catalog.py -v` | **3 failed / 5 passed** (rojo ajeno: `PLAN239-OUTLET-EN-BLANCO`) | **3 failed**, los mismos 3, ninguno nombrando `plan259_*` |
  | `pytest tests/test_harness_flags_help.py -v` | **4 failed / 4 passed** (rojo ajeno: 79 flags sin ayuda) | **4 failed**, y las 3 keys de este plan **fuera** de la lista de faltantes |
  | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` | **1 failed / 2 passed** (`ExecutionDetailDrawer.module.css` 23>21, `RunReconciliationCard.module.css` 1>0) | **1 failed**, exactamente esos 2 archivos, ninguno de este plan |
  | `npx tsc --noEmit` | **0 errores** | **0 errores** |

  **Prohibido, y es parte de la DoD:** arreglar cualquiera de esos 3 rojos ajenos adentro de este plan (es alcance de otro), y correr `UI_DEBT_REGEN=1` (taparía la deuda propia junto con la ajena).
- [ ] `npx vitest run src/__tests__/adhocModalRatchet.test.ts` sin fallos nuevos (`FROZEN_MAX = 11`, ya topado: `SetupGuideDialog.tsx` **tiene** que usar el `Dialog` canónico).
- [ ] `.venv\Scripts\python.exe -m compileall -q backend` sin errores.
- [ ] `config.py` sigue teniendo `STACKY_GITLAB_ENABLED` con default `"false"` (`test_default_de_config_no_se_movio`, F7).
- [ ] **El motor se enciende de verdad** *(v2, C1)*: `test_enciende_de_verdad` verde — es decir, `config.config.STACKY_GITLAB_ENABLED is True` y la línea en el `.env`, no una llamada espiada.
- [ ] **Smoke manual (HITL, lo corre el operador):** abrir "Nuevo Proyecto" → aparece **🦊 GitLab** → aparece **ℹ️ INFO** → el panel abre con **12 pasos** → "Verificar ahora" con datos falsos marca en rojo el chequeo correcto y señala el paso que lo arregla → con datos reales y la casilla del motor tildada, los 5 controles quedan **sin ningún rojo**: cuatro en verde y `chk-flag` en verde con el texto *"se va a activar al crear el proyecto"* si la perilla todavía está apagada *(v2, C5: exigir "los 5 en verde" antes de crear era imposible, porque F7 recién enciende el motor al crear)* → "Crear e inicializar" → el proyecto aparece en la lista con tipo **GitLab** y `has_credentials` en true → el `config.json` en disco dice `"type": "gitlab"` → volver a abrir "Verificar ahora" desde Edición muestra ahora `chk-flag` en verde por estado real.
- [ ] **Smoke manual de la trampa vieja** *(v2, C4)*: abrir un proyecto GitLab en **Editar**, escribir una ruta en "Ruta al archivo de token", guardar, reabrir ⇒ la ruta **sigue ahí** (con v1 se perdía en silencio).
- [ ] Ningún archivo bajo `frontend/src/components/` nuevo tiene `style={{`.
- [ ] El token no aparece en ningún log ni en ninguna respuesta HTTP (verificado por `test_token_nunca_en_la_respuesta` y `test_verify_nunca_devuelve_el_token`).
- [ ] Commit con `git commit -- "<rutas explícitas>"`. **Sin `git add -A`, sin `reset`, sin `amend`, sin `--no-verify`.** `git push` **solo** si el operador lo pide.
