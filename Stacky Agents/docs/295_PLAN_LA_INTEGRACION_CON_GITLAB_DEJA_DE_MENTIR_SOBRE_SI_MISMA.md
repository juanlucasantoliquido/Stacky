# Plan 295 — La integración con GitLab deja de mentir sobre sí misma

**Versión: v1 -> v2.** **Estado:** **v2 — CRITICADO Y CORREGIDO (sin implementar).** 2026-08-02, rama `docs/plan-279`.
**Autor:** StackyArchitectaUltraEficientCode. **Serie:** continúa 286 · 289 · 290 · 291 · 292.
**Juez v2: subagente independiente, misma corrida, contexto limpio.**

> **VEREDICTO (v1): RECHAZADO.** Criterio binario aplicado: **≥ 1 hallazgo BLOQUEANTE ⇒ RECHAZADO**. Se encontraron **9** bloqueantes y **9** importantes (**18** hallazgos). Los cuatro decisivos, todos **medidos ejecutando**, no leídos:
> 1. **C1** — `test_plan218_capability_matrix.py::test_full_y_partial_exigen_evidencia` exige evidencia `archivo.py:DÍGITOS` (`_EVIDENCE_RE = ^[\w/\.]+\.py:\d+$`) para **todo** `full`/`partial`. F2 y F4 convierten **8** entradas a `archivo:símbolo` ⇒ el test rompe con cada una. Y **ya está ROJO** hoy (`2 failed, 8 passed`) por la deuda que el 292 dejó en `tracker.sync.full`. El v1 declaraba ese archivo **verde con 10 passed** y lo usaba como gate de arranque: **el plan se auto-bloqueaba**.
> 2. **C2** — `_CATEGORY_KEYS["global"]` **no existe** (hay 20 categorías, ninguna se llama así; la del 292 vive en `paridad_proveedores`). El guardián 3 de F10 y el caso 4 de su test daban `KeyError`.
> 3. **C3** — el plan crea **9** archivos de test de backend y registraba **4**: `test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests` habría quedado **ROJO al commitear**, y la vía del allowlist está cerrada (`194` entradas contra `_ALLOWLIST_MAX = 197`).
> 4. **C18** — el gate de arranque de F0 exigía `4 passed` en `test_harness_ratchet_meta.py` y ordenaba, si salía rojo, "resolver eso antes de crear los propios". El archivo sale **`1 failed, 3 passed`** por `tests/test_plan293_commit.py`, **de la sesión paralela**: el gate, tal como estaba escrito, **sólo se satisfacía tocando trabajo ajeno**, que esta corrida tiene prohibido.
>
> **La v2 corrige los 18 hallazgos SIN relajar un solo criterio:** se **agrega** una fase (**F2a**), sube el número de casos de aceptación y no se borra ningún assert. El detalle está en `## CHANGELOG v1 -> v2`.
> **Conteo de anclajes verificados abriendo los archivos: 149/171 OK · 18 DESFASADOS (corregidos en esta v2, no borrados) · 4 INEXISTENTES.**

> ℹ️ **NUMERACIÓN: COLISIÓN DETECTADA Y RESUELTA — el número definitivo es `295`.**
> Este plan se escribió como `293`, pinneado por el orquestador con una verificación en frío que decía "el máximo es 292 y `293_*` no existe". **Esa foto caducó DENTRO de la misma corrida:** mientras el arquitecto redactaba, una **sesión paralela viva** commiteó dos planes:
> - `293_PLAN_EL_TRABAJO_SE_PUBLICA_SIN_TERMINAL_TABLERO_DE_GIT_GUIADO.md` (12:40, commit `0d0b303b`)
> - `294_PLAN_EL_PIPELINE_SE_CREA_SIN_SABER_YAML_WIZARD_GUIADO_PARA_NO_TECNICOS.md` (13:11, commit `fe9b17ec`)
>
> **Resolución aplicada por el orquestador (regla: gana el primero commiteado).** Los dos de la sesión paralela estaban commiteados y este estaba untracked, así que **este se renumeró de `293` a `295`**: se renombró el archivo y se reescribieron las **122 referencias internas** (título, `plan-295`, los 13 archivos de test `test_plan295_*` / `plan295*.test.ts`, el fixture `_plan295_autocrear_habilitado` y la base `plan295.db`). Verificado: cero ocurrencias de `293` restantes, y el rango de líneas `:284-295` de `useTicketSync.ts` quedó intacto. **Este número ya NO se vuelve a cambiar**: los commits lo citan.
>
> **Forward-references:** todas las referencias al plan que va a construir I3 dicen **"PLAN DEL WEBHOOK"** en vez de un número, precisamente porque la numeración es disputada. **No hay ningún forward-reference numérico que pueda romperse.**

## CHANGELOG v1 -> v2

Una entrada por hallazgo resuelto. **Nada se resolvió borrando un criterio, un assert ni un archivo de test.** Delta declarado: **fases 13 → 14** (se agrega **F2a**), **archivos de test nuevos 13 → 13** (9 backend + 4 frontend; F2a no crea archivo, agrega 3 casos al de F2), **casos de aceptación 91 → 113**, **archivos de test ajenos modificados 0 → 1** (`test_plan218_capability_matrix.py`, declarado en F2a), **archivos de test registrados en los DOS ratchets 5 → 9**, **archivos ajenos en la batería de no-regresión 9 → 11**, **riesgos 12 → 14**.

**Casos agregados, uno por uno (ninguno reemplaza a otro):** F2 `+3` (casos 5-7, el regex del guardián) · F3 `+1` (**[ADICIÓN ARQUITECTO 1]**, ningún símbolo repetido) · F5 `+1` (caso 9, bundle por entorno) y el caso 7 pasa de 5 a **6** escenarios parametrizados · F6 `+1` (caso 11, el 422 real) y el caso 6 sube de 6 a **7** mensajes · F7/F8 `+1` (caso 16, éxito ADO no toca `gitlab_sync`) · F10 `+1` (**[ADICIÓN ARQUITECTO 2]**, caso 8, los seis guardianes) · F11 `+1` (caso 6, la variable real `trackerType`).

**Los dos `[ADICIÓN ARQUITECTO]` están en el CUERPO de su fase, no sólo acá:** la 1 en F3 (`test_ningun_simbolo_se_repite_entre_capacidades`, con su código completo) y la 2 en **F10.5.bis** (`test_los_seis_guardianes_de_la_flag_numerica`, con su código completo y su mitad de contraste).

| # | Hallazgo | Severidad | Qué se cambió en la v2 |
|---|---|---|---|
| **C1** | `test_full_y_partial_exigen_evidencia` (`test_plan218_capability_matrix.py:60-67`) exige `archivo.py:DÍGITOS` para todo `full`/`partial`; F2 y F4 convierten 8 entradas a símbolo ⇒ insatisfacible. Y el archivo **ya está rojo** (`2 failed, 8 passed`) por `gitlab/tracker.sync.full`. | **BLOQ** | **Fase nueva `F2a`** que AMPLÍA `_EVIDENCE_RE` para aceptar línea **o** símbolo (sigue rechazando vacío y `archivo.py` pelado), con su mitad de contraste y 3 casos nuevos en `test_plan295_matriz_no_miente.py`. El criterio de F2/F4 pasa de "10 passed / delta cero" a "**de `2 failed, 8 passed` medido a `10 passed`**", declarado como mejora. |
| **C2** | `_CATEGORY_KEYS["global"]` **no existe**: 20 categorías, la del 292 está en `paridad_proveedores` (`harness_flags.py:617`). El caso 4 de F10 daba `KeyError`. | **BLOQ** | Guardián 3 y caso 4 de F10 apuntan a **`paridad_proveedores`**. Se agrega el assert `categorize(key) != "otros"`. Se aclara que `group="global"` de la `FlagSpec` es **otro campo** (433 flags lo usan) y sí es correcto. |
| **C3** | 9 archivos de test nuevos, 4 registrados ⇒ `test_harness_ratchet_meta.py` ROJO al commitear. Allowlist saturado (194 vs `_ALLOWLIST_MAX = 197`). El DoD decía 5. | **BLOQ** | Los **9** se registran en `.sh` **y** `.ps1` (tabla explícita en F12). `test_harness_ratchet_meta.py` entra en la batería de no-regresión. DoD y F12 corrigen 5 → 9. |
| **C4** | `_CAPABILITY_TO_SYMBOL["links.item"]["gitlab"] = "services.gitlab_deep_links:url_de_issue"` — **el símbolo no existe** (el real es `compose_issue_url`) y el status es `full` ⇒ el gate nace rojo. | **BLOQ** | Mapa con el símbolo **verificado**: `services.gitlab_deep_links:compose_issue_url`. Se elimina el comando de "búsqueda" cuya interpretación quedaba al modelo. |
| **C5** | Dos entradas del mapa apuntaban a `services.ado_client:AdoClient` — una clase que existe siempre ⇒ **el gate era adorno** para `azure_devops` e inflaba K1. | **BLOQ** | Símbolos que **hacen el trabajo**, verificados: `services.ado_sync:upsert_single_work_item` (`:235`) y `services.ado_client:_RETRY_AFTER_MAX` (`:49`). Más **[ADICIÓN ARQUITECTO 1]**: un caso que prohíbe que dos capacidades distintas compartan el mismo `módulo:símbolo` por proveedor — el antídoto mecánico y permanente a esta clase de adorno. |
| **C6** | `_FROZEN_BOUNDS` **no puede avisar**: `test_bounds_map_is_frozen` ya está ROJO (`1 failed, 17 passed`) por 6 numéricas del plan 284. Con criterio "delta cero", F10 se cerraba sin la entrada y nada lo cazaba. | **BLOQ** | El criterio deja de apoyarse en el archivo rojo: **[ADICIÓN ARQUITECTO 2]** mete en `test_plan295_flag_intervalo.py` (verde) un caso que asertá los **seis** guardianes de la flag numérica de una sola vez, incluida la entrada exacta de `_FROZEN_BOUNDS`. |
| **C7** | Dos rutas INEXISTENTES sostenían decisiones de "fuera de alcance": `frontend/src/lib/trackerUrls.ts` y `frontend/src/services/__tests__/plan288SuperficieClasificacion.test.ts`. | **BLOQ** | Rutas reales: **`frontend/src/utils/trackerUrls.ts`** (confirmado por `plan282Censo.test.ts:78`) y **`frontend/src/__tests__/plan288SuperficieClasificacion.test.ts`**. |
| **C8** | F0 declaraba verdes dos archivos que están rojos y el "8 rojos de fábrica" no estaba medido (el real, en los 11 archivos que el plan nombra, es **13 fallos en 6 archivos**: 4+3+1+2+1+2). | **BLOQ** | Tabla de baseline **MEDIDA** en F0 (archivo por archivo, con el venv del repo) y todos los criterios reescritos como delta contra esos números. Actualizado también en el principio 9 de §3, el objetivo de F0, el riesgo R11 y el glosario. |
| **C18** | **El gate de arranque de F0 le ORDENABA al implementador tocar trabajo ajeno.** Decía que `test_harness_ratchet_meta.py` tiene que salir `4 passed` y que "si sale rojo … hay que resolver eso antes de crear los propios". Re-medido: sale **`1 failed, 3 passed`** por **`tests/test_plan293_commit.py`**, de la **sesión paralela**, creado sin registrar **después** de la primera medición. "Resolverlo" = registrar el test de otro ⇒ violar el alcance. Y era un criterio **absoluto** sobre un archivo con rojo ajeno. | **BLOQ** | Baseline corregido a **`1 failed, 3 passed`** con la causa nombrada, y el gate convertido en **DELTA CON LISTA**: los no clasificados tienen que seguir siendo **exactamente** `['tests/test_plan293_commit.py']` en F0 **y** en F12, con **cero** `test_plan295_*`. Se declara por escrito que **este plan NO arregla ese rojo** y por qué. Riesgos **R13** y **R14** nuevos, y **§10.6** para el operador. |
| **C9** | El `record_success("gitlab_sync", …)` de F7 **no consultaba el tracker**: corría en todo sync exitoso de `sync-v2`, reintroduciendo en el camino de éxito el acoplamiento cross-proveedor que F8 elimina del de fallo. | IMP | El bloque de éxito se mueve dentro del ruteo por tracker y se agrega el **caso 16**: "sync exitoso de un proyecto ADO ⇒ `gitlab_sync` intacto". |
| **C10** | `_sesion_para` llamaba `crear_contexto_openssl(ca_bundle)` con el string crudo, salteando `resolver_ca_bundle` ⇒ la sonda **no** habla el TLS del sync si el bundle viene por entorno (`STACKY_GITLAB_CA_BUNDLE` / `REQUESTS_CA_BUNDLE`). | IMP | `_sesion_para` copia el idioma exacto del cliente (`gitlab_client.py:155-181`): `resolver_ca_bundle(...)` y después `crear_contexto_openssl(ruta)`. **Caso 9** nuevo: con el campo vacío y la env apuntando a un `.pem` real, el `mount()` ocurre. |
| **C11** | El v1 contaba "cuatro `return` tempranos" y listaba cinco, y **olvidaba el `return out` final (`:173`)**: son **SEIS** caminos de salida. | IMP | Los 6 enumerados; el caso 7 asertá `len(checks) == 6` en **6** escenarios (era 5). |
| **C12** | `_COPY_GITLAB_POR_KIND` ignoraba `"unknown"`, que `_kind_for_status` **sí produce** para 400/409/422 (y es el default de `TrackerApiError.__init__`). | IMP | Séptima entrada `"unknown"` con copy accionable; el caso 6 sube de "6 mensajes distintos" a "**7**". |
| **C13** | Aritmética del ratchet mal: F2 convierte 2 entradas pero **sólo una** era por línea (la otra tenía evidencia vacía) ⇒ tras F2 son **103**, no 102; tras F4 son **95**, no 96. El output rojo literal ("102") era inalcanzable. | IMP | 104 → 103 → **95**, `_TOPE_EVIDENCIAS_POR_LINEA = 95`, y el output rojo literal corregido. Verificado que las dos regex (B2 sin anclar y la de F4 anclada) dan **el mismo 104**, así que el baseline es comparable. |
| **C14** | F4 dejaba `<símbolo real>` ×3 y `<N>` ×1 para que el implementador adivinara. Y `tracker.updates.history` gitlab apuntaba a `:606`, que cae dentro de `find_child_by_marker` (`:587`), no de la capacidad. | IMP | Los cuatro nombres literales y verificados: `fetch_open_work_items` (`ado_client.py:319`), `_RETRY_AFTER_MAX` (`ado_client.py:49`), `fetch_item_updates` (`gitlab_provider.py:619`), y `tracker.items.get` gitlab hoy es `services/gitlab_provider.py:164` (no `<N>`). |
| **C15** | El v1 decía que `EpicChildrenPanel` **no** recibe el tracker y abría una decisión (a)/(b). **Lo recibe**: `:45` ya tiene `trackerType` vía `useWorkbench` (Plan 282 F4). Y el JSX usaba `trackerActivo`, que no existe ⇒ `tsc` rojo. | IMP | Se usa la variable real **`trackerType`**, se borra la decisión (a)/(b) y el test asertá `nombreDeNivel(trackerType`. |
| **C16** | Cuatro anclajes de `sync_from_ado` corridos 1-2 líneas y `import config` corrido 9. Insertar el `except` nuevo "entre `:1247` y `:1248`" lo mete **dentro** del handler de `AdoApiError`, antes de su `return`. | IMP | Líneas reales: `CapabilityUnavailable :1231`, `AdoConfigError :1244`, `AdoApiError :1247`, `Exception :1249`, `_sync_via_provider_or_ado :1230`, `import config :48`. El punto de inserción se ancla por **símbolo** y se dice cuál es la línea siguiente. |
| **C17** | Frases y huecos que un modelo menor tiene que inferir: el archivo de `docs/sistema/` sin nombrar, `config.config` en un módulo que **no importa `config`**, `_FROZEN_BOUNDS` "junto a la del 292" cuando el propio archivo exige **al final**, "se BORRA esa entrada del mapa". | IMP | Todo literal: el `import config` explícito, la posición **AL FINAL** de `_FROZEN_BOUNDS` con la razón (`_first_key_with_min()` toma la primera key con `min_value`), y el archivo de `docs/sistema/` resuelto con un comando cuyo resultado es un nombre, no una decisión. |
| — | `endpoints.ts` **no menciona** `gitlab_ca_bundle` en ningún lado (0 ocurrencias): la justificación del `slice` del caso 1 de F5 era falsa. El `slice` se conserva (es correcto igual) con la razón corregida. | MEN | Nota corregida en F5.4. |
| — | Verificado **correcto** y sin cambio: la mecánica de `_CURATED_DEFAULTS_ON` (bool ON sí / numérica no y sin `default=`), `TrackerApiError` con `.status`/`.kind` y **sin** `status_code`/`retry_after`, `deployment/harness_defaults.env` **no** es guardián por flag, `len(CAPABILITY_KEYS) == 71`, `len(_CAPABILITY_TO_PORT_METHOD) == 17`, `TicketBoard.tsx` **sí** pasa `intervalMs` en dos lugares, el diferimiento de I3 (los 6 puntos de escritura existen y `gitlab_ca_bundle` está en los 6). | — | Se anotan como CONFIRMADOS para que nadie los vuelva a auditar. |

---

## Estado de implementación por fase

**A completar por quien implemente.** Una fila por fase, con el hash del commit y la evidencia medida (conteo de `passed` + el output de la mitad de contraste). Una fila sin evidencia **no cuenta como IMPLEMENTADA**.

| Fase | Estado | Commit | Evidencia (conteo + mitad de contraste ejecutada) |
|---|---|---|---|
| **F0** — línea base medida | PENDIENTE | (sin commit propio) | B1..B6 + baseline MEDIDO de 11 archivos + `tsc --noEmit` |
| **F1** — dead code `gitlabProfileModel` | PENDIENTE | | |
| **F2** — la matriz deja de mentir | PENDIENTE | | |
| **F2a** — el guardián del 218 admite evidencia por SÍMBOLO | PENDIENTE | | |
| **F3** — gate de las transversales | PENDIENTE | | |
| **F4** — ratchet de evidencias | PENDIENTE | | |
| **F5** — la sonda habla el TLS del proyecto | PENDIENTE | | |
| **F6** — `except TrackerApiError` ⇒ 502 | PENDIENTE | | |
| **F7** — breaker `gitlab_sync` | PENDIENTE | | |
| **F8** — el breaker se consulta tras rutear | PENDIENTE | | |
| **F9** — webhooks por proyecto+tracker | PENDIENTE | | |
| **F10** — el intervalo es del operador | PENDIENTE | | |
| **F11** — rótulos ruteados (2 pantallas) | PENDIENTE | | |
| **F12** — paridad, docs y no-regresión | PENDIENTE | | |

---

## 1. Objetivo y KPI

La serie 276→292 construyó una integración GitLab que **funciona**: TLS propio por proyecto, sync incremental de 1 request, ruteo de escritura por proyecto, contexto del agente, `start_branch`, degradación visible. Lo que **no** construyó es la capacidad del sistema de **decir la verdad sobre lo que ya sabe hacer**. Hoy la sonda de configuración pinta rojo mientras el producto anda; un PAT vencido de GitLab sale como `HTTP 500 {"error":"unexpected"}`; la matriz de paridad declara ausentes las dos capacidades que los planes 276 y 292 acabaron de construir; el circuit breaker de ADO se consulta antes de saber qué tracker es; dos receptores de webhook machean tickets por una columna que en GitLab **no es única**; y la única perilla de tráfico que el operador querría tocar exige editar un archivo `.ts`.

Este plan cierra esos seis defectos. No agrega capacidad nueva de integración: **hace que la capacidad existente sea visible, diagnosticable y del operador**. Es el plan que convierte "anda pero no se entiende" en "anda y se explica".

### KPI medible sin credenciales

| # | KPI | Hoy (MEDIDO 2026-08-02) | Después | Cómo se mide |
|---|---|---|---|---|
| K1 | Claves de la matriz de paridad que el gate anti-mentira puede vigilar | **17 de 71** (`_CAPABILITY_TO_PORT_METHOD`) | **≥ 24 de 71** (17 por método de puerto + ≥ 7 por símbolo) | `len(_CAPABILITY_TO_PORT_METHOD) + len(_CAPABILITY_TO_SYMBOL)` |
| K2 | Entradas de la matriz cuya evidencia es `archivo:línea` (caduca al primer commit ajeno) | **104** (ADO 50 + GitLab 54) | **≤ 95** (ratchet descendente, −9: F2 convierte 1 y F4 convierte 8) | test `test_ratchet_evidencias_por_simbolo` |
| K2b | **[v2, C1]** Entradas `full`/`partial` cuya evidencia el guardián del 218 admite | **hoy el guardián RECHAZA toda evidencia por símbolo y ya está rojo por 1 entrada** | **todas** (línea o símbolo; sigue rechazando vacío y `archivo.py` pelado) | `test_plan218_capability_matrix.py` **de `2 failed, 8 passed` a `10 passed`** |
| K3 | Capacidades declaradas `absent` para GitLab que en realidad existen | **2** (`tracker.sync.incremental`, y `tracker.rate_limit.clamp` declarada `partial` con la pérdida ya resuelta) | **0** | gate nuevo de F3 corrido contra el commit anterior |
| K4 | Referencias a claves de circuit breaker en producción | `ado_sync` **7** · `jira_sync` **5** · `ado_identity` **2** · `gitlab_sync` **0** | `gitlab_sync` **≥ 3** | `grep -rn '"gitlab_sync"' backend --include=*.py \| grep -v /tests/` |
| K5 | Errores de API de GitLab que salen como `500 unexpected` | **todos** (`TrackerApiError` no está en ningún `except` de `/sync` ni `/sync-v2`) | **0**: `502` + `kind` + copy que nombra GitLab | test de F6 con `TrackerApiError(401, kind="auth")` |
| K6 | Consultas `filter_by(ado_id=...)` sin `stacky_project_name` en receptores de webhook | **2** (`api/phase6.py:167`, `:221`) | **0** | `grep -c 'filter_by(ado_id=int(ado_id))' backend/api/phase6.py` |
| K7 | Perillas de tráfico del sync que el operador puede tocar desde la UI | **0** | **1** (`STACKY_TICKET_SYNC_INTERVAL_MS`) | flag en `FLAG_REGISTRY` + `GET /api/tickets/config/frontend` |
| K8 | Módulos de frontend con cero referencias de producción (dead code medido) | **1** (`gitlabProfileModel.ts`) | **0** | `grep -rn gitlabProfileModel frontend/src` = 0 |
| K9 | Rótulos ADO hardcodeados en superficie ruteable de las dos pantallas en alcance | **4** (`EpicChildrenPanel.tsx:125,130,134`; `FinishWorkButton.tsx:244`) | **0** | test de censo de F11 |

**Lo que NO se puede medir sin las credenciales del operador:** que la sonda de F5 devuelva `chk-tls = ok` contra el GitLab interno real, y que el `ca_bundle` cierre el handshake de verdad. Eso queda como humo en `## PENDIENTES DEL OPERADOR`. Todo lo demás de este plan se mide con `pytest` y con `grep`, sin red.

---

## 2. Por qué ahora — el gap que cierra, apoyado en la serie 286-292

Los cinco planes anteriores tienen un patrón que este plan ataca de frente. Los cinco fueron **RECHAZADOS en v1 por el juez**, y **ninguno cayó por un anclaje `archivo:línea` equivocado** (dieron 15/16, 34/34, ~101, 101/103 y 101/104 anclajes correctos). Cayeron por **supuesto de capacidad**: el plan asumía que el sistema ya sabía hacer algo que no sabía.

La contracara de eso es este plan. Los seis defectos que cierra son, todos, **el mismo defecto visto seis veces**: el sistema tiene una capacidad y su propia superficie de reporte no la conoce.

- **El 276** construyó el adaptador TLS OpenSSL por sesión (`services/tls_openssl_context.py`, `services/gitlab_client.py:177-183`) y el clamp del `Retry-After` a 30 s (`services/gitlab_client.py:37,40-57`). La sonda de configuración del 259 **no recibió el adaptador** y la matriz de paridad **sigue declarando** que GitLab "no clampea Retry-After" (`services/provider_capabilities.py:275-278`). Dos capacidades construidas y dos superficies que las niegan.
- **El 281 F4** arregló el ruteo del breaker en el arranque y lo documentó por escrito en `backend/app.py:204` ("*Con este return un proyecto GitLab deja de tocar el breaker "ado_sync"*"). Dejó `sync-v2` sin tocar y lo declaró en sus propios diferidos. Es el caso puro del gotcha **G6**: un patrón arreglado en un camino y vivo en el hermano.
- **El 286** hizo que el ruteo de escritura le pregunte al proyecto y no a la columna (`tracker_efectivo_de_ticket`, `services/project_context.py:206`), precisamente porque `models.py:49` declara `tracker_type` con `default="azure_devops"` y ese valor es indistinguible de "nadie la seteó". Los dos receptores de webhook de `api/phase6.py` **no pasaron por ese arreglo**: siguen macheando por `ado_id` sin filtro, y el auto-creado de `:170-175` escribe un ticket sin `tracker_type` — o sea, uno que cae en el default y que el 286 tiene que adivinar después.
- **El 292** implementó el sync incremental y lo dejó **ON al nacer** (`services/gitlab_sync.py:235,259-277`), midió el ahorro y emitió los contadores `omitidos_cerrados_desconocidos` y `bytes_recibidos` (`:504-505`). La matriz declara `"tracker.sync.incremental": _a()` — **ausente** — en `services/provider_capabilities.py:259`, y el panel `ParityMatrixPanel` la muestra así en `frontend/src/pages/DiagnosticsPage.tsx:338`. El 292 también **midió** la recomendación de subir el intervalo de polling de 45 s a 180 s (−75 % del tráfico) y hoy aplicarla **exige editar `frontend/src/hooks/useTicketSync.ts:40`**.

La razón estructural de que esto se repita está medida: el gate anti-mentira que existe, `test_matriz_no_miente_estructuralmente` (`backend/tests/test_plan218_capability_matrix.py:107-133`), recorre **solo** `_CAPABILITY_TO_PORT_METHOD`, que son **17 claves de 71**. Toda capacidad **transversal** — que no tiene un método del puerto `TrackerProvider` detrás — es invisible para el gate. Y `test_doc_de_paridad_esta_sincronizado` (`:84-96`) mantiene `docs/_roadmap/PARIDAD_ADO_GITLAB.md` perfectamente sincronizado **con la mentira**. La matriz se degrada exactamente donde el producto avanza (gotcha **G2**).

Este plan cierra el lazo: corrige las dos entradas, **extiende el gate a las transversales**, y pone un ratchet que empuja las evidencias de `archivo:línea` (que caducan) a `archivo:símbolo` (que no).

---

## 3. Principios y guardarraíles (no negociables — codificados en cada fase)

1. **Tres runtimes con paridad.** Codex CLI, Claude Code CLI y GitHub Copilot Pro. Nada de este plan depende de un runtime: todo el código nuevo es Python puro del backend, TypeScript puro del frontend, y tests que no invocan ningún CLI de agente. Cada fase declara su línea de impacto por runtime.
2. **Cero trabajo extra para el operador.** Todo lo de este plan es invisible/automático o `default ON`. **Ninguna fase de este plan cae en las categorías de excepción (A) ni (B)**: ninguna quema tokens en reposo (no hay loop, daemon, barrido, polling nuevo ni inyección de contexto que llame a un modelo) y ninguna escribe en un sistema real del operador. Las seis fases son leer, calcular, mostrar, clasificar y avisar. **Solo-lectura nunca es excepción: va ON.** La única flag que nace `OFF` en este plan es **ninguna**.
3. **Mecánica exacta del default ON** — son **tres** lugares: `backend/config.py`, la `FlagSpec` de `backend/services/harness_flags.py`, y `_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py`. Y `_CURATED_DEFAULTS_ON` es **solo para booleanas ON**: la flag numérica de F10 **no va ahí** y **no lleva `default=`** en su `FlagSpec` (ver el precedente exacto del 292 en `backend/services/harness_flags.py:7386-7395`, con el comentario que explica por qué).
4. **Config por UI, tres patas, superficie existente.** Toda flag de este plan se maneja desde el panel de flags que ya existe (`frontend/src/components/HarnessFlagsPanel.tsx`), que ya renderiza `type="int"` en `:115-128`. **Cero pantallas nuevas.** No se usa `_MANAGED_KEYS` de `backend/api/global_config.py` para nada de este plan (esa superficie es para credenciales y rutas, y registrar una clave en las dos crea **dos escritores del mismo valor** — la razón está escrita en `frontend/src/pages/DiagnosticsPage.tsx:330-333`).
5. **Human-in-the-loop innegociable.** Nada de este plan decide por el operador. La sonda de F5 **informa** que el certificado no cerró; no lo instala. El breaker de F7 **informa** que GitLab está degradado; no reintenta solo. La perilla de F10 le **da** el control del intervalo; no lo cambia por él (el default sigue siendo 45 000).
6. **Mono-operador sin auth real.** Cero RBAC. Cero multiusuario. Un `403` en este plan significa **flag apagada**, nunca *permiso* (ver `backend/api/setup_guide.py:95-96`, que ya usa esa semántica).
7. **No degradar. Backward-compatible. Reusar.** Se reusa `services/integration_breaker.py` **tal cual** (F7 no le agrega una función: le agrega dos constantes `REASON_*` y una key), los helpers de `frontend/src/lib/trackerLabels.ts` **tal cual** (F11 no escribe un helper nuevo), el adaptador `_AdaptadorOpenSSL` de `services/gitlab_client.py:60-79` (F5 lo importa, no lo copia), y `services/maintenance.py:17-42` si alguna vez hiciera falta un periódico (**no hace falta en este plan: cero threads nuevos**, ver `backend/app.py:641` "*NO agregar threads nuevos*").
8. **`services/` no importa de `api/`.** Verificado y respetado en las 13 fases. F5 pone la lógica nueva en `services/gitlab_setup_check.py` y F7 en `services/integration_breaker.py`; los dos siguen sin importar nada de `api/`.
9. **Sin falsos verdes** (gotcha **G7**). Cada fase nombra **archivos de test concretos** y el comando por archivo. **Sin `-k`** (`pytest -k` sin match da **exit 0**). Un archivo inexistente da **exit 4**, así que el criterio siempre exige un conteo de `passed`, nunca "no falló". `pytest tests` completo **no es un veredicto** (contaminación cruzada). **[v2, C8+C18] Hay 13 tests rojos de fábrica repartidos en 6 de los 11 archivos que este plan nombra** (medido, tabla en F0 — el v1 decía "8" sin fuente): todos los criterios de este plan son **delta**, no absolutos. Y **donde el archivo rojo no puede discriminar** —`test_harness_flags_bounds.py`, `test_harness_flags_help.py`— **el criterio se muda a un archivo verde con un assert de contenido** (F10.5.bis), porque "delta cero sobre un archivo rojo" pasa igual con el cableado puesto y sin él.

---

## 4. ALCANCE DE ESTE PLAN Y CORTE DECLARADO

El insumo del operador pide cubrir **6 iniciativas (I1..I6) + 6 quick wins (QW1..QW6)**. Lo hago explícito, ítem por ítem, sin omitir nada en silencio.

### Entra en este plan (fases firmes)

| Ítem del insumo | Fase | Por qué entra |
|---|---|---|
| **I1** — la sonda habla el TLS del proyecto (arregla **D1**) | **F5** | Costo S, riesgo bajo. Es solo-lectura pura. Reusa el adaptador del 276 sin reintroducir `GitLabClient`. |
| **I2a** — `except TrackerApiError` ⇒ `502` con `kind` (arregla **D2**) | **F6** | Costo S. Cinco líneas de `except` y un mapa de copy. Es el ítem con mejor relación valor/riesgo del insumo. |
| **I2b** — breaker `"gitlab_sync"` (arregla **D3**, mitad 1) | **F7** | Costo S. Reusa `integration_breaker` tal cual. |
| **I2c** — mover el `should_skip("ado_sync")` debajo del ruteo (arregla **D3**, mitad 2) | **F8** | Costo S. Cierra el hermano que el 281 dejó abierto. Camino ADO byte-idéntico. |
| **I4a+b** — corregir las 2 entradas y regenerar el doc (= **QW1**) | **F2** | Costo XS. 10 minutos. |
| **I4c** — el gate cubre las transversales | **F3** | **El ítem más importante del plan**: sin esto, la matriz vuelve a mentir en el PLAN DEL WEBHOOK. |
| **I4d** — ratchet de evidencias `archivo:símbolo` | **F4** | Costo S. Convierte una clase entera de anclaje caduco en deuda que solo baja. |
| **I5** — el intervalo de sync pasa a ser del operador (arregla **D6**, = **QW5**) | **F10** | Costo M por los guardianes, riesgo bajo. Desbloquea la recomendación medida del 292 sin editar un archivo. |
| **I6 parcial** — `EpicChildrenPanel` + `FinishWorkButton` | **F11** | Los dos archivos están **limpios** (verificado con `git status`). |
| **Corrección de D5** (= **QW4**) — los webhooks machean por proyecto+tracker | **F9** | Bug latente **garantizado** en multiproyecto GitLab, con riesgo de correr el DebugAgent sobre el ticket equivocado. Se arregla acá **aunque I3 se difiera**: vale por sí mismo. |
| **QW6** — borrar el dead code `gitlabProfileModel.ts` | **F1** | El único quick win independiente. 20 minutos. |
| **QW2** ⊂ I2 · **QW3** ⊂ I1 · **QW1** ⊂ I4 · **QW4** ⊂ D5 · **QW5** ⊂ I5 | — | **No se duplican como fases separadas**, tal como pide el insumo. |

### NO entra — y la decisión está justificada, no omitida

**I3 (el webhook entrante) se difiere al PLAN DEL WEBHOOK.** La razón no es el costo L declarado en el insumo: es que **I3 apoya en una capacidad que verifiqué y NO existe**, y ese es exactamente el error que hundió los cinco planes anteriores.

I3 necesita un **secreto por proyecto guardado en el auth del proyecto**. Medí lo que hace falta para agregar un campo nuevo a la configuración de tracker de un proyecto, y son **seis** puntos de escritura, no uno:

- `backend/api/projects.py:35` — la allowlist de campos de texto (`gitlab_ca_bundle` está ahí; el secreto no).
- `backend/api/projects.py:187` — la serialización de salida (`"gitlab_ca_bundle": tracker.get("ca_bundle", "")`).
- `backend/api/projects.py:467` y `:477` — el camino de **creación**.
- `backend/api/projects.py:652` y `:662` — el camino de **actualización**.
- `backend/project_manager.py` — la función que arma el bloque `issue_tracker` de GitLab.
- `frontend/src/components/NewProjectModal.tsx` y `frontend/src/components/EditProjectModal.tsx` — las dos pantallas.

Y **dos** de esos puntos, si se olvidan, **no dan error**: el campo simplemente vuelve vacío en el siguiente `GET`, y un secreto de webhook vacío convierte la comparación de tiempo constante en un `401` permanente que el operador va a leer como "GitLab no manda nada". Sumado a que I3 abre **superficie HTTP nueva** y a que su flag tendría que nacer `OFF` por excepción **(B)** (quién la configura en GitLab es el operador), el resultado es un plan de 6 fases propias **arriba** de las 13 de este. Trece fases ya es el techo de lo que un modelo menor implementa sin perder el hilo.

**La decisión: el plan 295 deja el terreno preparado y el PLAN DEL WEBHOOK construye I3.** F9 de este plan corrige D5 — la dependencia dura de I3 — así que el PLAN DEL WEBHOOK arranca sin deuda: no habrá un tercer receptor de webhook conviviendo con dos que machean por `ado_id` sin filtro. Ver `## DIFERIDOS` §D-1 para el detalle completo de lo que el PLAN DEL WEBHOOK tiene que construir.

**Lo demás que queda afuera** está en `## DIFERIDOS` con su iniciativa de origen: la parte de I6 que toca `EpicFromBriefModal.tsx` (§D-2) y el retiro de su entrada de la allowlist de `plan282Censo.test.ts:64-65` (§D-3).

---
## 5. Fases

**Orden de dependencia (grafo real):**

```
F0 (línea base, sin código)
 ├─ F1  QW6 dead code            ── independiente
 ├─ F2  I4a+b matriz             ─→ F3  I4c gate transversal ─→ F4  I4d ratchet evidencias
 ├─ F5  I1 sonda TLS             ── independiente
 ├─ F6  I2a except TrackerApiError ─→ F7  I2b breaker gitlab_sync ─→ F8  I2c reordenar should_skip
 ├─ F9  D5 webhooks por proyecto ── independiente (prerequisito del PLAN DEL WEBHOOK)
 ├─ F10 I5 intervalo del operador ── independiente
 └─ F11 I6 parcial rótulos       ── independiente
F12 (paridad de runtimes + docs + no-regresión) ── requiere F1..F11
```

Cada fase es **autocontenida y verificable sola**. Un implementador puede parar después de cualquier fase y el repo queda consistente.

---

### F0 — Línea base medida (sin código de producción)

**Objetivo:** medir el estado exacto del repo **antes** de tocar nada, para que los criterios de las fases siguientes sean **delta** y no absolutos. Sin esto, los **13 rojos de fábrica medidos** (en 6 archivos) se confunden con daño propio — y peor: **dos de esos archivos rojos no pueden discriminar si el cableado está o no**, así que "delta cero" sobre ellos no es un criterio.

**Valor:** es la fase que hace que las otras doce sean auditables. Sin F0 no hay mitad de contraste creíble.

**Archivos a crear/editar:** **NINGUNO.** F0 no escribe código. Su entregable es la tabla de abajo, completada con números reales, pegada en este documento en la sección "Estado de implementación por fase" al implementar.

**Comandos exactos a correr y anotar (uno por línea, desde la raíz del repo):**

```bash
# B1 — cuántas claves tiene la matriz de capacidades
"Stacky Agents/backend/.venv/Scripts/python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.provider_capabilities import CAPABILITY_KEYS, _CAPABILITY_TO_PORT_METHOD as M; print('CAPABILITY_KEYS', len(CAPABILITY_KEYS)); print('PORT_METHOD', len(M))"

# B2 — cuántas evidencias son archivo:LÍNEA (el baseline del ratchet de F4)
"Stacky Agents/backend/.venv/Scripts/python.exe" -c "import sys,re; sys.path.insert(0,'Stacky Agents/backend'); from services.provider_capabilities import CAPABILITY_MATRIX as C; p=re.compile(r'(py|ts|tsx):[0-9]+'); print(sum(1 for pr in C for k,v in C[pr].items() if v.get('evidence') and p.search(str(v['evidence']))))"

# B3 — cuántas flags tiene el registro (F10 lo mueve en +1)
"Stacky Agents/backend/.venv/Scripts/python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.harness_flags import FLAG_REGISTRY; print(len(FLAG_REGISTRY))"

# B4 — brecha de los DOS ratchets de test files (crítico: está EXACTAMENTE en el límite)
grep -cE "^\s*tests/[a-zA-Z0-9_/]+\.py\s*$" "Stacky Agents/backend/scripts/run_harness_tests.sh"
grep -cE '^\s*"tests/[a-zA-Z0-9_/]+\.py"\s*,?\s*$' "Stacky Agents/backend/scripts/run_harness_tests.ps1"

# B5 — censo de claves de breaker en PRODUCCIÓN (sin tests)
grep -rn '"ado_sync"\|"jira_sync"\|"ado_identity"\|"gitlab_sync"' "Stacky Agents/backend" --include=*.py | grep -v "/tests/" | wc -l
grep -rn '"gitlab_sync"' "Stacky Agents/backend" --include=*.py | grep -v "/tests/" | wc -l

# B6 — el dead code de QW6 sigue sin consumidores
grep -rn "gitlabProfileModel" "Stacky Agents/frontend/src" | wc -l
```

**Valores MEDIDOS al escribir este plan (2026-08-02). Si el implementador mide otros, gana lo que mide y lo anota:**

| ID | Qué mide | Valor medido |
|---|---|---|
| B1 | `len(CAPABILITY_KEYS)` | **71** |
| B1 | `len(_CAPABILITY_TO_PORT_METHOD)` | **17** |
| B2 | evidencias con `archivo:línea` (ADO 50 + GitLab 54) | **104** |
| B3 | `len(FLAG_REGISTRY)` | **495** |
| B4 | rutas en `run_harness_tests.sh` | **836** |
| B4 | rutas en `run_harness_tests.ps1` | **772** |
| B4 | **brecha `sh − ps1`** | **64** ⚠️ |
| B5 | referencias de breaker en producción (total) | **14** (`ado_sync` 7 + `jira_sync` 5 + `ado_identity` 2) |
| B5 | referencias de `"gitlab_sync"` | **0** |
| B6 | referencias a `gitlabProfileModel` | **1** (solo su propio test) |

⚠️ **B4 es la trampa de commit más peligrosa de este plan.** `backend/tests/test_plan259_ratchet_script_parity.py:46` fija `_PS1_LAG_MAX = 64` y el assert de `:93` es `len(solo_en_sh) <= _PS1_LAG_MAX`. La brecha real es **exactamente 64**. Consecuencia dura: **cada archivo de test nuevo que este plan agregue al `.sh` tiene que agregarse también al `.ps1`, en la misma corrida.** Registrar uno solo en el `.sh` deja la brecha en 65 y pone el ratchet **rojo**, y como es trampa de commit, revienta al final, cuando el implementador cree que terminó. El formato difiere: el `.sh` lleva la ruta **pelada** (`  tests/test_plan295_foo.py`) y el `.ps1` la lleva **entrecomillada y con coma** (`  "tests/test_plan295_foo.py",`). El **último** elemento del array `.ps1` va **sin** coma final (ver `backend/scripts/run_harness_tests.ps1:1008`).

**Baseline de rojos de fábrica — MEDIDO EN LA CRÍTICA v2, no estimado.** Se corrió cada archivo **por separado** con `backend/.venv/Scripts/python.exe -m pytest tests/<archivo> -q` desde `backend/`. **Estos son los números contra los que se mide el delta. El v1 declaraba verdes dos de ellos y no lo estaban.**

| Archivo | Medido 2026-08-02 | Este plan lo modifica? | Nota |
|---|---|---|---|
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** | no | rojo ajeno conocido (`PLAIN_HELP` no se deriva de `description`) |
| `tests/test_error_fingerprints_catalog.py` | **3 failed, 5 passed** | no | rojo ajeno conocido |
| `tests/test_harness_flags.py` | **59 passed** | **sí** (`_CURATED_DEFAULTS_ON`, 2 booleanas ON) | **VERDE**: cualquier rojo acá es daño propio |
| `tests/test_harness_flags_bounds.py` | **1 failed, 17 passed** | **sí** (`_FROZEN_BOUNDS`) | ⚠️ **el que falla es `test_bounds_map_is_frozen`**, por **6** numéricas del plan 284 (`STACKY_DOCS_*`) ausentes del mapa. **Ver C6: este guardián NO discrimina** |
| `tests/test_plan218_capability_matrix.py` | **2 failed, 8 passed** | **sí** (F2a) | ⚠️ falla `test_full_y_partial_exigen_evidencia` (`gitlab/tracker.sync.full` trae un símbolo) y `test_doc_de_paridad_esta_sincronizado` (el doc en disco dice `gitlab \| 34 \| 14 \| 21 \| 2` y el render da `33 \| 14 \| 22 \| 2`). **Ver C1 y C8** |
| `tests/test_plan259_ratchet_script_parity.py` | **12 passed** | no (sólo se le agregan rutas a los scripts) | VERDE |
| `tests/test_harness_ratchet_meta.py` | **1 failed, 3 passed** | no | ⚠️ **el v1 no lo nombraba (C3), y su rojo es AJENO Y EN VUELO (C18).** Falla `test_ratchet_clasifica_todos_los_tests` por **`tests/test_plan293_commit.py`**, de la **sesión paralela** (su plan 293, el tablero de Git), creado sin registrar en el `.sh`/`.ps1` ni en el allowlist. **Este plan NO lo arregla** |
| `tests/test_p7_sync_endpoints.py` | **3 passed** | roza (F10) | VERDE |
| `tests/test_plan259_setup_guide_api.py` | **27 passed** | roza (F5) | VERDE |
| `tests/test_plan259_setup_guide_data.py` | **14 passed** | roza (F5) | VERDE |
| `tests/test_plan276_gitlab_sync.py` | **2 failed, 19 passed** | no | rojo ajeno; archivo tocado por la sesión paralela |

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_error_fingerprints_catalog.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_bounds.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_ratchet_script_parity.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_ratchet_meta.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_p7_sync_endpoints.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_setup_guide_api.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_setup_guide_data.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan276_gitlab_sync.py" -q
```

> **[v2, C8 + C18] "8 rojos de fábrica" era un número sin fuente.** El real, en los 11 archivos que este plan nombra, es **13 tests fallando repartidos en 6 archivos** (4 + 3 + 1 + 2 + 1 + 2). Y **tres de esos seis** son guardianes sobre los que el v1 apoyaba criterios binarios: `test_plan218_capability_matrix.py` (C1), `test_harness_flags_bounds.py` (C6) y `test_harness_ratchet_meta.py` (C18). **Todo criterio de este plan es delta contra la tabla de arriba, y donde el archivo rojo no discrimina, el criterio se muda a un archivo verde (ver F10.5.bis).**
>
> ⚠️ **La foto se mueve DENTRO de la corrida.** El baseline de `test_harness_ratchet_meta.py` pasó de `4 passed` a `1 failed, 3 passed` **entre dos mediciones de esta misma crítica**, porque la sesión paralela creó `tests/test_plan293_commit.py` en el medio. **El implementador re-mide la tabla completa en F0 y gana lo que mide**, con una excepción que no es negociable: **si el rojo nuevo es un archivo de OTRA sesión, se anota y NO se arregla.**

**B7 — el censo del ratchet meta (nuevo en v2, C3):**

```bash
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -c "import pathlib,re; b=pathlib.Path('.'); al=b/'tests'/'harness_ratchet_allowlist.txt'; ent={l.split('#',1)[0].strip() for l in al.read_text(encoding='utf-8').splitlines() if l.split('#',1)[0].strip()}; sh=(b/'scripts'/'run_harness_tests.sh').read_text(encoding='utf-8'); r=set(re.findall(r'^[ \t]*(tests/[\w/]+\.py)[ \t]*$', sh, re.M)); todos={p.as_posix() for p in (b/'tests').rglob('test_*.py')}; todos={t[t.index('tests/'):] for t in todos}; print('allowlist',len(ent),'ratchet',len(r),'total',len(todos),'sin clasificar',sorted(todos-r-ent))"
```

| ID | Qué mide | Valor medido |
|---|---|---|
| B7 | entradas de `harness_ratchet_allowlist.txt` | **194** (tope `_ALLOWLIST_MAX = 197`, `test_harness_ratchet_meta.py:66`) |
| B7 | rutas en `HARNESS_TEST_FILES` del `.sh` (parser del meta-test) | **838** |
| B7 | archivos `tests/test_*.py` totales | **1032** |
| B7 | **sin clasificar HOY** | **1** — `tests/test_plan293_commit.py`, **de la SESIÓN PARALELA** ⇒ el meta-ratchet está **rojo de fábrica** ([v2, C18]) |

⚠️ **[v2, C3] Consecuencia dura:** los **9** archivos de test nuevos del backend van a `HARNESS_TEST_FILES` del `.sh` **y** al `.ps1`. **No** al allowlist: con 194 entradas y tope 197, meter 5 daría 199 y pondría rojo `test_allowlist_grandfathered_solo_baja` también. Registrar los 9 en los dos scripts deja la brecha `sh − ps1` en **64**, que es el máximo permitido.

**Criterio de aceptación BINARIO:** la tabla B1..B7 está completa con números reales, y el baseline de los **11** archivos está anotado con su conteo `passed`/`failed`. Si algún número difiere de los medidos acá, se anota el nuevo y **se ajustan los criterios de la fase que lo usa** (F2a usa el baseline del 218, F3 usa B1, F4 usa B2, F10 usa B3, todas las fases con test nuevo usan B4 y B7).

**Mitad de contraste de F0:** F0 no tiene código, así que su mitad de contraste es **positiva y obligatoria**:

1. `test_plan218_capability_matrix.py` tiene que salir **`2 failed, 8 passed`** con los DOS nombres exactos de la tabla. **Si sale `10 passed`, alguien ya arregló esos dos rojos y F2a queda sin objeto: hay que releer el archivo antes de tocarlo.**
2. **[v2, C18]** `test_harness_ratchet_meta.py` tiene que salir **`1 failed, 3 passed`**, y el mensaje del fallo tiene que listar **exactamente un** archivo: `tests/test_plan293_commit.py`. Se anota la lista completa, tal cual sale.

#### [v2, C18] El gate del meta-ratchet es DELTA CON LISTA, y NO se arregla el rojo ajeno

**Lo que decía el v1 y por qué estaba mal:** *"`test_harness_ratchet_meta.py` tiene que salir `4 passed` (si sale rojo, hay un test nuevo sin registrar de OTRA sesión y **hay que resolver eso antes de crear los propios**)"*. Dos defectos:

1. **Le ordenaba al implementador tocar trabajo ajeno.** "Resolverlo" significa registrar `tests/test_plan293_commit.py` en `run_harness_tests.sh` / `.ps1` o meterlo en el allowlist. Ese archivo es de la **sesión paralela** (su plan 293) y esta corrida tiene **prohibido** tocar su trabajo. Un gate que sólo se satisface violando el alcance no es un gate: es una trampa.
2. **Era un criterio ABSOLUTO sobre un archivo con rojo ajeno**, que es exactamente lo que este plan prohíbe en todas las demás fases.

**El criterio correcto, binario y que sí puede fallar:**

```bash
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

| Momento | Resultado exigido | Lista de no clasificados exigida |
|---|---|---|
| **F0** (antes de crear un solo test) | `1 failed, 3 passed` | **exactamente** `['tests/test_plan293_commit.py']` |
| **F12** (con los 9 archivos nuevos registrados) | `1 failed, 3 passed` — **delta CERO** | **exactamente** `['tests/test_plan293_commit.py']` — **cero** `test_plan295_*` |

**Lo que este criterio caza y el absoluto no:** que uno de los 9 archivos nuevos quede sin registrar. Si eso pasa, la lista crece a **dos** entradas y aparece un `test_plan295_*` en el mensaje. **Lo que NO exige: arreglar el rojo ajeno.**

> **`tests/test_plan293_commit.py` NO se registra en este plan, y la razón es de alcance, no de pereza.** Es un archivo de test en vuelo de otra sesión: su autor sabe si pasa aislado (condición para el `.sh`) o si va al allowlist con motivo. Decidirlo desde acá es escribir en su plan. **Si el operador quiere que se arregle, es una línea suya en §10.6, no una decisión de este plan.**
>
> **Y el allowlist tampoco es opción para nada de este plan:** 194 entradas contra `_ALLOWLIST_MAX = 197`. Quedan 3 slots y este plan crea 9 archivos. **Los nueve van al `.sh` y al `.ps1`.**

> **[v2, C1] El gate de arranque del v1 estaba invertido.** Decía: "si `test_plan218_capability_matrix.py` sale rojo en F0, este plan no puede empezar por F2". Está rojo, y **F2a existe precisamente para arreglarlo**, porque los dos rojos son la deuda que F2 y F4 tienen que pagar: uno es un símbolo que el guardián no admite (lo que este plan hace 8 veces más) y el otro es el doc de paridad desincronizado (que F2 regenera). **No es rojo ajeno: es el rojo que este plan cierra.**

**Flag que la protege:** ninguna (no hay código).

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. F0 son comandos de shell y `pytest`; ningún runtime de agente participa. Fallback: si el runtime no puede correr `grep`, los conteos de B4 y B6 se obtienen con `Select-String` de PowerShell; los valores no cambian.

**Trabajo del operador: ninguno.**

---

### F1 — QW6: se borra el dead code medido de `gitlabProfileModel`

**Objetivo:** eliminar un módulo de frontend con **cero referencias de producción**, para que el próximo lector no lo confunda con código vivo del perfilador de pipelines de GitLab.

**Valor:** −1 archivo que miente sobre existir. Es la fase de calentamiento: pequeña, aislada, y su gate es un `grep` que no puede dar falso verde.

**Censo POR REFERENCIA que justifica el borrado (medido, gotcha G5):**

```
grep -rn "gitlabProfileModel" "Stacky Agents/frontend/src"
→ 1 sola línea: frontend/src/components/devops/gitlabProfileModel.test.ts:9 ("} from './gitlabProfileModel';")
```

`frontend/src/components/devops/PipelineLintPanel.tsx` **no lo importa** (verificado). Los tres símbolos exportados —`GL_RULE_TITLES`, `toLintFinding`, `groupSemantic`— tienen **cero** consumidores fuera de su propio test. **No es "código que todavía no se cableó": es código cuyo único lector es el test que lo prueba.**

**Archivos a BORRAR (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\components\devops\gitlabProfileModel.ts`
2. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\components\devops\gitlabProfileModel.test.ts`

> **El test se borra JUNTO con el módulo, no antes ni después.** Borrar solo el `.ts` deja el `.test.ts` con un `import` a un archivo inexistente, y `tsc` lo marca. Borrar solo el test deja el módulo sin cobertura y sigue muerto.

**Archivos a crear:**

3. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\components\devops\__tests__\plan295DeadCodeGitlabProfile.test.ts`

**Contenido del test nuevo (TDD: se escribe ANTES de borrar y falla):**

```ts
// Plan 295 F1 — gate de que el dead code medido de gitlabProfileModel NO vuelva.
// Se prueba con lectura de disco (no con import) porque el punto ES la ausencia
// del archivo: un import fallaría en compilación y no en el assert.
import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = dirname(fileURLToPath(import.meta.url));
const DEVOPS = resolve(AQUI, "..");

describe("plan 295 F1 — gitlabProfileModel es dead code borrado", () => {
  it("el modulo NO existe", () => {
    expect(existsSync(resolve(DEVOPS, "gitlabProfileModel.ts"))).toBe(false);
  });

  it("su test tampoco existe (se borro junto con el modulo)", () => {
    expect(existsSync(resolve(DEVOPS, "gitlabProfileModel.test.ts"))).toBe(false);
  });

  // ASSERT DE PRESENCIA, no de ausencia (G7): comprueba que el archivo que SÍ
  // debe existir sigue existiendo. Sin este, un typo en DEVOPS haria pasar los
  // dos asserts de arriba EN FALSO (todo "no existe" en una ruta equivocada).
  it("el panel que se creia consumidor sigue en su lugar", () => {
    expect(existsSync(resolve(DEVOPS, "PipelineLintPanel.tsx"))).toBe(true);
  });
});
```

> El tercer caso es el **antídoto al falso verde de assert de ausencia**: los dos primeros `toBe(false)` pasarían igual si `DEVOPS` apuntara a una carpeta que no existe. El tercero ancla la ruta.

**Tests PRIMERO — comando exacto:**

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run "src/components/devops/__tests__/plan295DeadCodeGitlabProfile.test.ts"
```

> **Este archivo es `.ts` PURO a propósito.** RTL y jsdom **no están instalados** en este repo: un `.test.tsx` con RTL reporta "no tests" y sale con **exit 0** — un falso verde de manual. Vitest sí corre `.ts` puro.

**Criterio de aceptación BINARIO:** `3 passed`, y además:

```
grep -rn "gitlabProfileModel" "Stacky Agents/frontend/src" | grep -v plan295DeadCode
→ debe devolver 0 líneas (exit 1 de grep, que acá es el resultado CORRECTO)
```

**Mitad de contraste (esperado en ROJO antes de borrar):** con los dos archivos todavía en disco, los casos 1 y 2 fallan con `expected true to be false`. **Los dos.** Si uno pasa antes de borrar, la ruta `DEVOPS` está mal y el test es un adorno.

**Flag que la protege:** **ninguna, y es correcto.** Borrar código sin consumidores de producción no cambia ningún comportamiento observable, así que una flag sería una perilla que no controla nada. La reversión es `git revert` del commit de la fase.

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. Es un borrado de archivos y un test de `vitest`. Fallback: si `npx vitest` no está disponible en el runtime, el criterio de aceptación se cumple con el `grep` solo, y se anota que el test quedó sin correr (**no** se declara verde).

**Trabajo del operador: ninguno.**

---

### F2 — I4a+b (= QW1): la matriz deja de mentir en las dos capacidades que el 276 y el 292 construyeron

**Objetivo:** corregir las **dos** entradas de `CAPABILITY_MATRIX["gitlab"]` que declaran ausente o degradada una capacidad **implementada y ON**, y regenerar el documento de paridad.

**Valor:** el panel `ParityMatrixPanel` (`frontend/src/pages/DiagnosticsPage.tsx:338`) deja de decirle al operador que GitLab no sabe hacer sync incremental — que es la característica que el plan 292 acabó de construir y midió en **1 request**.

**Archivos EXACTOS a editar (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\provider_capabilities.py`
2. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\docs\_roadmap\PARIDAD_ADO_GITLAB.md` (**generado — nunca se edita a mano**)

**Cambio 1 — `services/provider_capabilities.py:259`.** Hoy:

```python
        "tracker.sync.incremental": _a(),
```

Pasa a:

```python
        # Plan 295 F2 — DEJA DE MENTIR. El plan 292 implementó el sync incremental
        # para GitLab y nace ON: `decidir_modo_de_sync` elige "incremental" y emite
        # TrackerQuery(state="all", updated_after=marca) — 1 request. La matriz lo
        # declaraba ausente y el panel de Diagnóstico lo mostraba así.
        # Evidencia por SÍMBOLO (F4): una línea se corre con el primer commit ajeno.
        "tracker.sync.incremental": _f("services/gitlab_sync.py:sync_gitlab_tickets"),
```

**Cambio 2 — `services/provider_capabilities.py:275-278`.** Hoy:

```python
        "tracker.rate_limit.clamp": _p(
            "services/gitlab_client.py:146",
            "no clampea Retry-After: un valor hostil bloquea el hilo (ADO lo clampea a 30 s)",
        ),
```

Pasa a:

```python
        # Plan 295 F2 — el 276 F9 puso el clamp a 30 s en _resolver_retry_after y la
        # matriz seguía declarando la pérdida YA RESUELTA. Además el anclaje
        # "gitlab_client.py:146" estaba CADUCO: el clamp vive en _resolver_retry_after
        # (hoy línea 40) y _RETRY_AFTER_MAX en la 37. Se ancla por SÍMBOLO.
        "tracker.rate_limit.clamp": _f("services/gitlab_client.py:_resolver_retry_after"),
```

**Casos borde y por qué `_f` y no `_p`:**

- `_p(...)` **exige** una nota de pérdida no vacía — lo vigila `test_partial_exige_loss_no_vacio` (`backend/tests/test_plan218_capability_matrix.py:50`). Si se dejara `partial` habría que inventar una pérdida que ya no existe.
- `_f(evidence)` **exige** evidencia no vacía — lo vigila `test_full_y_partial_exigen_evidencia` (`:60-67`). Las dos entradas nuevas la traen.
- **`CAPABILITY_KEYS` NO se toca.** `test_claves_congeladas_no_se_renombran` (`:99`) compara un `sha256` de las claves unidas por `\n`. Este cambio toca **valores**, no claves: ese hash **no se mueve**. Si el implementador ve ese test rojo, tocó una clave por error.

> 🛑 **[v2, C1] DEPENDENCIA DURA: F2 NO PUEDE CERRARSE SIN F2a.** `test_full_y_partial_exigen_evidencia` no exige "evidencia no vacía": exige que **matchee `_EVIDENCE_RE = re.compile(r"^[\w/\.]+\.py:\d+$")`** — o sea `archivo.py:DÍGITOS`. Verificado abriendo `test_plan218_capability_matrix.py:60-67`. Las dos entradas que F2 pasa a `archivo:símbolo` **rompen ese test**, igual que las 6 de F4. Y el test **ya está rojo** por `gitlab/tracker.sync.full`, que el plan 292 dejó con `services/gitlab_sync.py:sync_gitlab_tickets`.
>
> **Orden obligatorio: F2a se implementa ANTES de F2, o los dos en el mismo commit.** El v1 tenía este mismo grafo mal: ponía F2 primero y declaraba que el archivo del 218 no se modificaba.

**Cambio 3 — regenerar el documento.** El doc es **generado** por `render_markdown_matrix()` y `test_doc_de_paridad_esta_sincronizado` (`:84-96`) lo compara **normalizado a `\n`**. Comando exacto de regeneración:

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from services.provider_capabilities import render_markdown_matrix; import pathlib; p = pathlib.Path('..') / 'docs' / '_roadmap' / 'PARIDAD_ADO_GITLAB.md'; p.write_text(render_markdown_matrix(), encoding='utf-8', newline='\n')"
```

> `newline='\n'` es **obligatorio**. En Windows, escribir sin él mete `\r\n`; el test normaliza al comparar, así que **pasaría igual** — pero el archivo quedaría con final de línea distinto al del resto del repo y el siguiente `git diff` sería ruido puro.

**Tests PRIMERO — archivo a crear:**

3. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_matriz_no_miente.py`

**Casos a cubrir (7 — los 4 del v1 más los 3 de F2a; todos de PRESENCIA del valor correcto, no de ausencia):**

| # | Caso | Assert | Fase |
|---|---|---|---|
| 1 | GitLab declara **full** el sync incremental | `capability_status("gitlab", "tracker.sync.incremental") == "full"` | F2 |
| 2 | GitLab declara **full** el clamp de `Retry-After` | `capability_status("gitlab", "tracker.rate_limit.clamp") == "full"` | F2 |
| 3 | Las dos evidencias nuevas son `archivo:SÍMBOLO`, no `archivo:línea` | para las 2 claves: `re.search(r":\d+$", evidence) is None` **y** `":" in evidence` | F2 |
| 4 | `supports()` — la vía consultiva que usa el código de producción — dice `True` para las dos | `supports("gitlab", k) is True` para las 2 claves | F2 |
| 5 | **[v2, F2a]** el guardián del 218 **acepta** una evidencia por símbolo | `_EVIDENCE_RE.match("services/gitlab_sync.py:sync_gitlab_tickets")` no es `None` | F2a |
| 6 | **[v2, F2a]** el guardián del 218 **sigue rechazando** evidencia vacía y `archivo.py` pelado | `_EVIDENCE_RE.match("")` es `None` **y** `_EVIDENCE_RE.match("services/x.py")` es `None` | F2a |
| 7 | **[v2, F2a]** el guardián del 218 **sigue rechazando** un símbolo que no es un identificador Python | `_EVIDENCE_RE.match("services/x.py:no es un simbolo")` es `None` **y** `_EVIDENCE_RE.match("services/x.py:")` es `None` | F2a |

> Los casos 5-7 importan `_EVIDENCE_RE` **desde `tests.test_plan218_capability_matrix`**, no lo redefinen. Redefinirlo sería probar una copia del regex en vez del que corre en el gate: el falso verde clásico.

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_matriz_no_miente.py" -q
```

**Criterio de aceptación BINARIO de F2 (delta contra el baseline MEDIDO de F0, nunca absoluto):** `7 passed` en el archivo nuevo **y** `test_plan218_capability_matrix.py` pasa de **`2 failed, 8 passed`** (medido) a **`10 passed`**:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q
```

> **[v2, C1] Los DOS rojos del 218 se cierran acá y es correcto que se cierren:**
> - `test_full_y_partial_exigen_evidencia` lo cierra **F2a** (amplía el regex del guardián).
> - `test_doc_de_paridad_esta_sincronizado` lo cierra **F2** (regenera el doc: hoy el archivo en disco declara `gitlab | 34 | 14 | 21 | 2` y `render_markdown_matrix()` produce `gitlab | 33 | 14 | 22 | 2`).
>
> **Es un delta de +2 declarado, no "delta cero".** Si el implementador ve `2 failed` después de F2+F2a, la fase **no** está lista.

**Mitad de contraste (esperado en ROJO antes del cambio):** con `services/provider_capabilities.py` sin tocar, el caso 1 falla con `assert 'absent' == 'full'` y el caso 2 con `assert 'partial' == 'full'`. El caso 3 falla para `tracker.rate_limit.clamp` (hoy la evidencia es `services/gitlab_client.py:146`, que **termina en dígitos**) y falla para `tracker.sync.incremental` por evidencia **vacía**. **Los 4 casos rojos antes, los 4 verdes después.** Si alguno pasa antes, el test no está mirando la matriz real.

**Flag que la protege:** **ninguna, y es deliberado.** Corregir un dato declarativo que describe lo que el código ya hace no es una capacidad nueva: es la eliminación de una mentira. Poner una flag equivaldría a ofrecerle al operador la opción de seguir viendo el dato falso. El panel que consume la matriz ya está detrás de `STACKY_PROVIDER_PARITY_ENABLED`, que **no se toca**.

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. `services/provider_capabilities.py` es un módulo **puro**: sin red, sin BD, sin importar adaptadores (lo dice su propio docstring, `:1-11`). Fallback: ninguno necesario, no hay dependencia externa.

**Trabajo del operador: ninguno.**

---

### F2a — [v2, C1] El guardián del 218 admite evidencia por SÍMBOLO (fase NUEVA de la crítica)

**Por qué existe esta fase.** El v1 no la tenía y sin ella **F2 y F4 son inimplementables**. `backend/tests/test_plan218_capability_matrix.py:56-67` dice, verificado:

```python
_EVIDENCE_RE = re.compile(r"^[\w/\.]+\.py:\d+$")


def test_full_y_partial_exigen_evidencia():
    for provider, caps in CAPABILITY_MATRIX.items():
        for key, entry in caps.items():
            if entry["status"] in ("full", "partial"):
                assert _EVIDENCE_RE.match(entry.get("evidence", "")), (
                    f"{provider}/{key}: evidencia inválida {entry.get('evidence')!r} "
                    "(se espera 'ruta/archivo.py:linea')"
                )
```

O sea: **el guardián de la matriz EXIGE hoy exactamente lo que este plan quiere eliminar** — el anclaje por número de línea. Y el conflicto no es teórico: **el test ya está ROJO**, con este output medido:

```
FAILED tests/test_plan218_capability_matrix.py::test_full_y_partial_exigen_evidencia
E  AssertionError: gitlab/tracker.sync.full: evidencia inválida
   'services/gitlab_sync.py:sync_gitlab_tickets' (se espera 'ruta/archivo.py:linea')
```

El plan 292 puso el primer anclaje por símbolo de la matriz y **dejó el guardián rojo**. Este plan pone 8 más. **Sin F2a, el implementador se encuentra un test que le pide lo contrario de lo que el plan le pide, y la salida barata es borrar el assert.** Eso es el falso verde que este plan existe para no cometer.

**Objetivo:** que el guardián exija **evidencia con ancla**, no **evidencia con número**. Se **amplía** el regex; no se relaja ninguna de las tres cosas que hoy rechaza (vacío, `archivo.py` pelado, ancla no válida).

**Valor:** convierte un guardián que contradice al plan en un guardián que lo respalda. Y desbloquea de un solo cambio el ratchet completo de F4.

**Archivo EXACTO a editar (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan218_capability_matrix.py` — **una constante y un mensaje**. Nada más. **Ninguno de sus 10 tests se borra ni se debilita.**

**El cambio, literal:**

```python
# Plan 295 F2a — el guardián exige evidencia CON ANCLA, no evidencia con NÚMERO.
# ANTES: r"^[\w/\.]+\.py:\d+$" -- sólo archivo.py:LÍNEA. Eso contradecía al ratchet
# del plan 295 F4 (los anclajes por línea caducan con el primer commit ajeno) y ya
# estaba ROJO porque el plan 292 ancló tracker.sync.full por SÍMBOLO.
# AHORA: archivo.py:LÍNEA  o  archivo.py:SIMBOLO_PYTHON_VALIDO.
# LO QUE SIGUE RECHAZANDO, sin ceder nada:
#   ""                              -> evidencia vacía
#   "services/x.py"                 -> archivo sin ancla
#   "services/x.py:"                -> ancla vacía
#   "services/x.py:no es simbolo"   -> ancla que no es un identificador
_EVIDENCE_RE = re.compile(r"^[\w/\.]+\.py:(?:\d+|[A-Za-z_][A-Za-z0-9_]*)$")
```

Y el mensaje del assert pasa a decir la verdad nueva (**el assert NO se toca, sólo su texto**):

```python
                assert _EVIDENCE_RE.match(entry.get("evidence", "")), (
                    f"{provider}/{key}: evidencia inválida {entry.get('evidence')!r} "
                    "(se espera 'ruta/archivo.py:linea' o 'ruta/archivo.py:nombre_de_simbolo'; "
                    "el plan 295 F4 lleva un ratchet que empuja las de LÍNEA a SÍMBOLO)"
                )
```

**Casos borde declarados, uno por uno:**

| Evidencia | Antes | Después | Por qué |
|---|---|---|---|
| `services/gitlab_client.py:146` | acepta | **acepta** | el ratchet de F4 es descendente: las 95 que quedan por línea siguen siendo válidas |
| `services/gitlab_sync.py:sync_gitlab_tickets` | **rechaza (rojo hoy)** | acepta | es el anclaje que no caduca |
| `services/gitlab_client.py:_resolver_retry_after` | rechaza | acepta | símbolo privado: `[A-Za-z_]` cubre el `_` inicial |
| `""` (vacío) | rechaza | **rechaza** | `full`/`partial` sin evidencia sigue prohibido |
| `services/x.py` | rechaza | **rechaza** | archivo sin ancla no dice a dónde mirar |
| `services/x.py:` | rechaza | **rechaza** | el `(?:\d+\|[A-Za-z_]…)` no matchea vacío |
| `services/x.py:no es un simbolo` | rechaza | **rechaza** | el espacio no está en la clase de caracteres |
| `services/x.py:Clase.metodo` | rechaza | **rechaza** | deliberado: el mapa de F3 y las evidencias usan el nombre **top-level** del módulo, que es lo que `getattr(modulo, nombre)` resuelve. Un `Clase.metodo` no se resuelve con un solo `getattr` y sería un anclaje que el gate no puede verificar |
| `services/x.ts:12` | rechaza | **rechaza** | fuera de alcance: el guardián del 218 es de módulos Python. La matriz no tiene evidencias `.ts` hoy (medido: 0) |

**Tests PRIMERO:** los casos **5, 6 y 7** de `test_plan295_matriz_no_miente.py` (ver F2). **No se crea un archivo de test nuevo**: importan `_EVIDENCE_RE` del archivo del 218 y prueban las tres direcciones. Así el ratchet del arnés no gana un archivo más y el gate prueba el regex **real**, no una copia.

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_matriz_no_miente.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q
```

**Criterio de aceptación BINARIO:**

1. El caso **5** de `test_plan295_matriz_no_miente.py` pasa (antes fallaba).
2. Los casos **6 y 7** pasan **antes y después** — son los que impiden que "ampliar" se convierta en "aceptar cualquier cosa". Si alguno falla después, el regex se aflojó demasiado.
3. `test_plan218_capability_matrix.py::test_full_y_partial_exigen_evidencia` pasa de **FAILED** a **PASSED**, sin tocar `CAPABILITY_MATRIX` en esta fase.
4. Los otros **9** tests de ese archivo: **sin cambio** respecto del baseline de F0 (8 passed + el de doc que cierra F2).

**Mitad de contraste (obligatoria, con el output esperado literal):**

1. **El rojo de partida ya está en disco.** Antes de tocar el regex:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py::test_full_y_partial_exigen_evidencia" -q
FAILED ... AssertionError: gitlab/tracker.sync.full: evidencia inválida
   'services/gitlab_sync.py:sync_gitlab_tickets' (se espera 'ruta/archivo.py:linea')
```

**Ese output se pega en el doc.** Es la prueba de que la fase arregla algo real y no un supuesto.

2. **La mitad que prueba que NO se aflojó** (obligatoria, se corre y se revierte): con el regex nuevo puesto, poner a mano `"tracker.items.list": _f("services/gitlab_provider.py")` (archivo **sin ancla**) y correr. Esperado:

```
FAILED tests/test_plan218_capability_matrix.py::test_full_y_partial_exigen_evidencia
E  AssertionError: gitlab/tracker.items.list: evidencia inválida
   'services/gitlab_provider.py' (se espera 'ruta/archivo.py:linea' o
   'ruta/archivo.py:nombre_de_simbolo'; ...)
```

Después **se revierte** (`git diff` de `services/provider_capabilities.py` limpio respecto de F2). **Sin esta segunda mitad, "amplié el regex" es indistinguible de "borré el gate".**

**Registro en los DOS ratchets:** ninguno nuevo — F2a no crea archivos de test.

**Flag que la protege:** **ninguna.** Es el criterio de un guardián. Un guardián detrás de una flag no es un guardián.

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. Es un `re.compile` en un archivo de test. Fallback: ninguno necesario.

**Trabajo del operador: ninguno.**

---
### F3 — I4c: el gate anti-mentira cubre las capacidades TRANSVERSALES (la fase más importante del plan)

**Objetivo:** extender el detector de mentiras de la matriz a las capacidades que **no tienen método del puerto `TrackerProvider`**, con un mapa nuevo `_CAPABILITY_TO_SYMBOL` que asocia una capacidad a un **símbolo de producción** y asertá las dos direcciones: `full`/`partial` ⇒ el símbolo **existe**; `absent` ⇒ el símbolo **NO existe**.

**Valor:** sin esta fase, F2 arregla dos mentiras y el PLAN DEL WEBHOOK crea la tercera. El gate que existe hoy vigila **17 de 71** claves (medido en F0/B1): las **54** restantes son invisibles, y son exactamente las transversales — TLS, rate limit, webhooks, deep links, CI — que es donde el producto avanzó en la serie 276-292. **Esta fase convierte "acordate de actualizar la matriz" en "el CI no te deja olvidarte".**

**Por qué el gate de hoy no alcanza (medido, gotcha G2):** `test_matriz_no_miente_estructuralmente` (`backend/tests/test_plan218_capability_matrix.py:107-133`) itera `_CAPABILITY_TO_PORT_METHOD.items()` y resuelve `getattr(cls, metodo)` sobre la clase del adaptador. Eso solo funciona si la capacidad **es** un método del puerto. `tracker.sync.incremental` **no lo es** (vive en `services/gitlab_sync.py`, que no es un adaptador), y `tracker.rate_limit.clamp` **tampoco** (vive en el cliente HTTP). Por eso las dos mentiras de F2 sobrevivieron a un gate que existe y funciona.

**Archivos EXACTOS a editar/crear (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\provider_capabilities.py` — se agrega el mapa `_CAPABILITY_TO_SYMBOL`.
2. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_gate_transversal.py` — **crear**.

**Nombres EXACTOS que se crean:**

- `_CAPABILITY_TO_SYMBOL: dict[str, dict[str, str]]` — en `services/provider_capabilities.py`, **inmediatamente debajo** de `_CAPABILITY_TO_PORT_METHOD` (que termina antes de la línea de `CAPABILITY_MATRIX`).
- `resolver_simbolo(ruta_simbolo: str) -> object | None` — helper del **test**, no del módulo de producción (el módulo tiene que seguir **puro**: sin importar adaptadores, `:1-11`).

**Forma exacta del mapa nuevo:**

```python
# Plan 295 F3 — SEGUNDO eje del detector de mentiras. _CAPABILITY_TO_PORT_METHOD
# solo cubre las capacidades que SON un método del puerto: 17 de las 71 claves.
# Toda capacidad TRANSVERSAL (TLS, rate limit, webhooks, deep links, sync) era
# invisible para el gate, y por eso el plan 295 F2 tuvo que corregir a mano dos
# entradas que mentían desde los planes 276 y 292.
#
# CONTRATO: {capability: {provider: "modulo.dotted.path:SIMBOLO"}}
#   * status full/partial  => el símbolo TIENE que existir en ese módulo.
#   * status absent        => el símbolo NO tiene que existir.
#   * capability/provider ausente de este mapa => el gate no opina (ratchet, F4).
#
# El símbolo se nombra por NOMBRE, nunca por línea: un anclaje de línea caduca
# con el primer commit ajeno y este mapa tiene que sobrevivir a la serie entera.
_CAPABILITY_TO_SYMBOL: dict[str, dict[str, str]] = {
    "tracker.sync.incremental": {
        "gitlab": "services.gitlab_sync:sync_gitlab_tickets",
        "azure_devops": "services.ado_client:AdoClient",
    },
    "tracker.rate_limit.clamp": {
        "gitlab": "services.gitlab_client:_resolver_retry_after",
        "azure_devops": "services.ado_client:AdoClient",
    },
    "tracker.auth.html_redirect": {
        "gitlab": "services.gitlab_client:_validar_base_url",
    },
    "events.webhook.inbound": {
        "gitlab": "api.tracker_webhooks:recibir_webhook_gitlab",
    },
    "events.webhook.verify": {
        "gitlab": "api.tracker_webhooks:verificar_firma_gitlab",
    },
    "links.item": {
        "gitlab": "services.gitlab_deep_links:url_de_issue",
    },
    "tracker.sync.full": {
        "gitlab": "services.gitlab_sync:sync_gitlab_tickets",
    },
}
```

> **ATENCIÓN — dos entradas del mapa apuntan a símbolos que HOY NO EXISTEN, y eso es CORRECTO y es el punto de la fase.** `api.tracker_webhooks:recibir_webhook_gitlab` y `api.tracker_webhooks:verificar_firma_gitlab` **no existen** en este plan: el módulo `api/tracker_webhooks.py` lo crea el **PLAN DEL WEBHOOK** (I3, diferido). Como la matriz declara `events.webhook.inbound` y `events.webhook.verify` **`absent`** para GitLab (verificado en `services/provider_capabilities.py:322` y en la clave hermana), el gate asertá que **NO existan** — y hoy no existen, así que **pasa**. El día que el PLAN DEL WEBHOOK cree el webhook y **se olvide de actualizar la matriz**, este gate se pone **ROJO** y lo obliga. **Eso es exactamente el mecanismo que faltaba.**

**Verificaciones que el implementador DEBE hacer antes de escribir el mapa** (si alguna falla, corrige el nombre del símbolo en el mapa, **no** el código de producción):

```bash
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); import services.gitlab_sync as m; print('sync_gitlab_tickets', hasattr(m,'sync_gitlab_tickets'))"
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); import services.gitlab_client as m; print('_resolver_retry_after', hasattr(m,'_resolver_retry_after')); print('_validar_base_url', hasattr(m,'_validar_base_url'))"
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); import services.ado_client as m; print('AdoClient', hasattr(m,'AdoClient'))"
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); import services.gitlab_deep_links as m; print([n for n in dir(m) if 'issue' in n.lower() or 'url' in n.lower()])"
```

> El último comando es una **búsqueda**, no una verificación: el nombre exacto de la función de deep link de issue de `services/gitlab_deep_links.py` hay que **leerlo** y poner el real en el mapa. Si el módulo expone `url_de_issue`, queda como está escrito arriba; si expone otro nombre, se usa ese. **Si no expone ninguno que corresponda a `links.item`, se BORRA esa entrada del mapa** (el mapa es opt-in: una capacidad ausente del mapa simplemente no se vigila, y el ratchet de F4 la cuenta como deuda).

**Contenido del test nuevo (TDD — se escribe ANTES del mapa y falla con `ImportError`):**

```python
"""Plan 295 F3 — el detector de mentiras de la matriz cubre las TRANSVERSALES.

POR QUÉ EXISTE: test_matriz_no_miente_estructuralmente (test_plan218_capability_matrix
.py:107) recorre SOLO _CAPABILITY_TO_PORT_METHOD = 17 de las 71 claves. Las 54
restantes -- TLS, rate limit, webhooks, deep links, sync -- eran invisibles, y ahí
es donde el producto avanzó en la serie 276-292: el plan 295 F2 tuvo que corregir a
mano dos entradas que mentían desde entonces.

DISEÑO -- IMPORTACIÓN DINÁMICA EN EL TEST, NO EN EL MÓDULO. provider_capabilities
es PURO a propósito (su docstring :1-11 lo declara: sin red, sin DB, sin importar
adaptadores). El mapa nuevo guarda STRINGS; resolverlos es trabajo del test.
"""
from __future__ import annotations

import importlib

import pytest

from services.provider_capabilities import (
    CAPABILITY_MATRIX,
    _CAPABILITY_TO_SYMBOL,
    capability_status,
)


def resolver_simbolo(ruta: str):
    """'services.gitlab_sync:sync_gitlab_tickets' -> el objeto, o None si no existe.

    Un módulo inexistente devuelve None (no explota): para una capacidad `absent`
    que apunta a un módulo que el plan siguiente va a crear, "no existe el módulo"
    y "no existe el símbolo" son el MISMO veredicto.
    """
    modulo, _, nombre = ruta.partition(":")
    assert nombre, f"ruta de símbolo sin ':' -> {ruta!r}"
    try:
        mod = importlib.import_module(modulo)
    except ModuleNotFoundError:
        return None
    return getattr(mod, nombre, None)


def test_el_mapa_no_esta_vacio_y_sus_claves_son_de_la_matriz():
    """Un mapa vacío haría pasar EN FALSO al gate de abajo (bucle de cero vueltas)."""
    assert len(_CAPABILITY_TO_SYMBOL) >= 5, f"solo {len(_CAPABILITY_TO_SYMBOL)} entradas"
    for capacidad, por_proveedor in _CAPABILITY_TO_SYMBOL.items():
        assert capacidad in CAPABILITY_MATRIX["gitlab"], f"{capacidad} no es clave de la matriz"
        assert por_proveedor, f"{capacidad} sin proveedores"
        for proveedor in por_proveedor:
            assert proveedor in CAPABILITY_MATRIX, f"proveedor desconocido: {proveedor}"


def test_el_mapa_cubre_al_menos_una_capacidad_sin_metodo_de_puerto():
    """El PUNTO de la fase: si todas las entradas ya estaban cubiertas por
    _CAPABILITY_TO_PORT_METHOD, este mapa no agrega nada y es un adorno."""
    from services.provider_capabilities import _CAPABILITY_TO_PORT_METHOD

    nuevas = set(_CAPABILITY_TO_SYMBOL) - set(_CAPABILITY_TO_PORT_METHOD)
    assert len(nuevas) >= 5, f"solo {len(nuevas)} capacidades transversales nuevas: {nuevas}"


def test_ningun_simbolo_se_repite_entre_capacidades():
    """[ADICIÓN ARQUITECTO 1 — Plan 295 F3, hallazgo C5 de la crítica v2]

    UN SÍMBOLO POR CAPACIDAD Y POR PROVEEDOR. Sin esto, el gate de abajo se
    convierte en ADORNO de la forma más fácil de cometer: apuntar varias
    capacidades al símbolo "grande" del módulo -- una clase de cliente, un
    `__init__`, un router -- que EXISTE SIEMPRE, cualquiera sea el estado real de
    la capacidad. El assert `obj is not None` pasa por construcción y el gate deja
    de vigilar sin dejar rastro: sigue verde, sigue contando para el KPI.

    Es exactamente lo que tenía el v1 de este plan: `tracker.sync.incremental` y
    `tracker.rate_limit.clamp` apuntaban las DOS a `services.ado_client:AdoClient`.

    La regla: dentro de un mismo proveedor, dos capacidades distintas NO pueden
    declarar el mismo `modulo:simbolo`. Si dos capacidades de verdad las resuelve
    el mismo símbolo, entonces son la MISMA capacidad y sobra una clave de la
    matriz -- que también es un hallazgo, y este test lo hace visible.
    """
    from collections import defaultdict

    por_proveedor: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for capacidad, por_prov in _CAPABILITY_TO_SYMBOL.items():
        for proveedor, ruta in por_prov.items():
            por_proveedor[proveedor][ruta].append(capacidad)

    repetidos = {
        f"{proveedor} -> {ruta}": sorted(caps)
        for proveedor, rutas in por_proveedor.items()
        for ruta, caps in rutas.items()
        if len(caps) > 1
    }
    assert not repetidos, (
        "un mismo símbolo vigila DOS capacidades distintas del mismo proveedor, así "
        "que el gate no puede fallar para ninguna de las dos (símbolo 'siempre existe'):\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(repetidos.items()))
        + "\nAncla cada capacidad al símbolo que HACE ESE trabajo, no al del módulo."
    )


@pytest.mark.parametrize("capacidad", sorted(_CAPABILITY_TO_SYMBOL))
def test_el_status_declarado_coincide_con_la_existencia_del_simbolo(capacidad):
    """LAS DOS DIRECCIONES.

      full/partial => el símbolo EXISTE  (caza la matriz que subestima al proveedor)
      absent       => el símbolo NO existe (caza la matriz que quedó atrás cuando
                      el plan siguiente construyó la capacidad y no la declaró)
    """
    for proveedor, ruta in _CAPABILITY_TO_SYMBOL[capacidad].items():
        status = capability_status(proveedor, capacidad)
        obj = resolver_simbolo(ruta)
        if status in ("full", "partial"):
            assert obj is not None, (
                f"{proveedor}/{capacidad} declarado {status} pero {ruta} no existe. "
                "O la matriz miente, o el símbolo se renombró: arreglá el que esté mal."
            )
        elif status == "absent":
            assert obj is None, (
                f"{proveedor}/{capacidad} declarado ABSENT pero {ruta} YA EXISTE. "
                "Alguien construyó la capacidad y no actualizó la matriz: pasala a "
                "_f() con evidencia por SÍMBOLO."
            )
        # status 'n/a' no se opina: es una capacidad que no aplica al proveedor.
```

**Casos borde declarados:**

- **`n/a`**: no se asertá nada. Es el único status que significa "la pregunta no aplica" (p. ej. una capacidad de ADO sin equivalente conceptual en GitLab).
- **Módulo inexistente**: `resolver_simbolo` devuelve `None` sin explotar. Es lo que permite que las dos entradas de webhook del PLAN DEL WEBHOOK pasen hoy.
- **Símbolo privado (`_resolver_retry_after`)**: `getattr` lo encuentra igual. Se ancla al privado a propósito: **es el símbolo que hace el trabajo**, y si alguien lo renombra, la matriz tiene que enterarse.
- **`parametrize` sobre un dict**: se usa `sorted(...)` para que el orden de los casos sea **determinista** entre corridas (un `dict` mantiene orden de inserción, pero el orden de inserción es un detalle de edición, no un contrato).

**Tests PRIMERO — comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_gate_transversal.py" -q
```

**Criterio de aceptación BINARIO [v2, C5]:** el archivo pasa con **`3 + N` passed**, donde `N` = cantidad de entradas de `_CAPABILITY_TO_SYMBOL` (el `parametrize` genera un caso por capacidad) y el `3` son los tres tests no parametrizados, incluido el de **[ADICIÓN ARQUITECTO 1]**. Con las 7 entradas del mapa: **10 passed**. Y el conteo se verifica con:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.provider_capabilities import _CAPABILITY_TO_SYMBOL as S, _CAPABILITY_TO_PORT_METHOD as P; print('cubiertas por gate:', len(P) + len(set(S) - set(P)), 'de 71')"
```

**K1 se cumple si ese número es `>= 24`.** Con 17 de puerto + 7 nuevas = **24**.

**Mitad de contraste (esperado en ROJO antes del código):**

1. **Antes de agregar el mapa:** el archivo entero falla en la **importación** con `ImportError: cannot import name '_CAPABILITY_TO_SYMBOL'`. Eso es rojo, pero es rojo **barato** — no prueba que el gate funcione.
2. **La mitad de contraste que SÍ prueba el gate** (obligatoria, se corre y se revierte): con el mapa ya puesto, **revertir a mano** la entrada de F2 en `services/provider_capabilities.py` a `"tracker.sync.incremental": _a(),` y volver a correr. Salida esperada:

```
FAILED test_plan295_gate_transversal.py::test_el_status_declarado_coincide_con_la_existencia_del_simbolo[tracker.sync.incremental]
E  AssertionError: gitlab/tracker.sync.incremental declarado ABSENT pero
   services.gitlab_sync:sync_gitlab_tickets YA EXISTE.
```

**Ese es el output que hay que ver y pegar en el doc.** Después se revierte el parche (`git diff` de `services/provider_capabilities.py` tiene que quedar limpio respecto de F2). Sin esta mitad, F3 es un test que pasa y no prueba nada.

3. **Segunda mitad de contraste (la dirección opuesta):** crear un archivo vacío `backend/api/tracker_webhooks.py` con `def recibir_webhook_gitlab(): ...` y correr de nuevo. Esperado:

```
FAILED ...[events.webhook.inbound]
E  AssertionError: gitlab/events.webhook.inbound declarado ABSENT pero
   api.tracker_webhooks:recibir_webhook_gitlab YA EXISTE.
```

Después **se borra el archivo**. Esto demuestra que el mecanismo que va a proteger al PLAN DEL WEBHOOK **funciona hoy**.

**Registro en los DOS ratchets (trampa de commit — B4 está en el límite exacto):**

- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\scripts\run_harness_tests.sh` — agregar la línea `  tests/test_plan295_gate_transversal.py` (ruta **pelada**).
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\scripts\run_harness_tests.ps1` — agregar `  "tests/test_plan295_gate_transversal.py",` (**entrecomillada y con coma**; si va última, **sin** coma y se le agrega coma a la anterior).

**Flag que la protege:** **ninguna.** Es un test. Un test detrás de una flag es un test que se puede apagar, o sea, no es un gate.

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. El test usa `importlib` de la stdlib y no invoca ningún CLI. Fallback: ninguno necesario. El único requisito es que `backend` esté en `sys.path`, que es lo que hace `conftest.py` en todos los runtimes.

**Trabajo del operador: ninguno.**

---

### F4 — I4d: ratchet DESCENDENTE de evidencias `archivo:línea` → `archivo:símbolo`

**Objetivo:** empezar a convertir las **104** evidencias ancladas a número de línea (que caducan con el primer commit ajeno) en evidencias ancladas a símbolo, con un **ratchet que solo baja** — nunca un corte a cero.

**Valor:** las evidencias de la matriz son el mapa que un lector usa para verificar si la matriz dice la verdad. Un anclaje caduco convierte ese mapa en ruido, y F2 encontró **uno concreto**: `"tracker.items.list": _f("services/gitlab_provider.py:155")` cae **dentro** de `_normalize_issue` (que empieza en `services/gitlab_provider.py:145`), cuando `fetch_open_items` está en **`:324`**. La evidencia apunta a la función equivocada.

**Por qué RATCHET y no corte a cero (medido):** hay **104** evidencias con `archivo:línea` (ADO **50**, GitLab **54**). Exigir cero pondría en rojo **104** entradas de las dos columnas de golpe, obligaría a resolver el símbolo correcto de cada una en una sola fase, y sería **rojo de fábrica masivo** — precisamente lo que este plan prohíbe. El ratchet convierte la deuda en un número que **solo puede bajar**.

**Archivos EXACTOS a editar/crear (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\provider_capabilities.py` — se convierten **al menos 8** evidencias a símbolo.
2. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\docs\_roadmap\PARIDAD_ADO_GITLAB.md` — **regenerar** (mismo comando de F2).
3. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_ratchet_evidencias.py` — **crear**.

**Las 8 evidencias a convertir (mínimo obligatorio, ya verificadas contra el código real):**

| Clave | Proveedor | Evidencia hoy | Pasa a | Verificado |
|---|---|---|---|---|
| `tracker.items.list` | gitlab | `services/gitlab_provider.py:155` ← **CADUCA, cae en `_normalize_issue`** | `services/gitlab_provider.py:fetch_open_items` | `fetch_open_items` está en `:324` |
| `tracker.items.get` | gitlab | `services/gitlab_provider.py:<N>` | `services/gitlab_provider.py:get_item` | `get_item` está en `:333` |
| `tracker.sync.full` | gitlab | `services/gitlab_sync.py:sync_gitlab_tickets` | (ya es símbolo — **no cuenta**) | `:259` |
| `tracker.auth.html_redirect` | gitlab | `services/gitlab_client.py:164` | `services/gitlab_client.py:_validar_base_url` | `_validar_base_url` está en `:81` |
| `tracker.items.list` | azure_devops | `services/ado_client.py:319` | `services/ado_client.py:<símbolo real>` | **leer el archivo y usar el nombre real** |
| `tracker.rate_limit.clamp` | azure_devops | `services/ado_client.py:49` | `services/ado_client.py:<símbolo real>` | **leer el archivo y usar el nombre real** |
| `events.webhook.inbound` | gitlab | `services/webhooks.py:123` ← **APUNTA AL EMISOR, no al receptor** | `""` (vacío) | ver nota abajo |
| `events.webhook.verify` | gitlab | `services/webhooks.py:70` ← **idem** | `""` (vacío) | ver nota abajo |
| `tracker.updates.history` | gitlab | `services/gitlab_provider.py:606` | `services/gitlab_provider.py:<símbolo real>` | **leer el archivo** |

> **Hallazgo colateral que hay que corregir en esta fase.** `events.webhook.inbound` y `events.webhook.verify` de GitLab traen como evidencia `services/webhooks.py:123` y `:70`. Verifiqué el módulo: `services/webhooks.py:123` es `def fire(...)` y `:70` es `def _sign(...)` — **son el emisor de webhooks SALIENTES de Stacky**, no un receptor entrante. La evidencia de una capacidad `absent` que apunta al módulo equivocado es peor que la evidencia vacía, porque manda al lector a leer código que no tiene nada que ver. `_a()` acepta evidencia vacía (`def _a(evidence: str = "")`) y `test_full_y_partial_exigen_evidencia` (`test_plan218_capability_matrix.py:60`) **solo** exige evidencia para `full`/`partial`. **Se dejan vacías.** Eso baja el contador del ratchet en 2 y elimina dos punteros falsos.

**Procedimiento obligatorio para cada conversión** (el implementador **no adivina** el símbolo):

```bash
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
# 1. Ver qué hay REALMENTE en la línea que la evidencia declara
sed -n '150,160p' services/gitlab_provider.py
# 2. Encontrar el símbolo que ENVUELVE esa línea
grep -n "    def \|^def \|^class " services/gitlab_provider.py
# 3. El símbolo correcto es el ÚLTIMO cuya línea sea <= la de la evidencia...
#    ...PERO si ese símbolo no es el que la capacidad describe (caso
#    tracker.items.list -> _normalize_issue), el anclaje estaba MAL: se usa el
#    símbolo que la capacidad describe de verdad (fetch_open_items).
```

**Contenido del test nuevo:**

```python
"""Plan 295 F4 — RATCHET de evidencias: los anclajes por LÍNEA solo bajan.

POR QUÉ. Una evidencia "archivo:123" caduca con el primer commit ajeno al archivo.
Este plan encontró una CADUCA en producción: tracker.items.list de GitLab apuntaba
a gitlab_provider.py:155, que cae dentro de _normalize_issue (:145), cuando
fetch_open_items está en :324. La evidencia mandaba a leer la función equivocada.

RATCHET, NO CORTE A CERO. Al escribir este plan había 104 evidencias por línea
(ADO 50 + GitLab 54). Exigir cero pondría 104 entradas en rojo de golpe -- rojo de
fábrica masivo, que este plan prohíbe. El tope solo puede BAJAR.
"""
from __future__ import annotations

import re

from services.provider_capabilities import CAPABILITY_MATRIX

# MEDIDO al implementar este plan. Este número SOLO PUEDE BAJAR: si tu cambio lo
# sube, estás agregando un anclaje que va a caducar. Anclá por SÍMBOLO.
_TOPE_EVIDENCIAS_POR_LINEA = 96

_POR_LINEA = re.compile(r"\.(py|ts|tsx|ps1|sh):\d+\s*$")


def _evidencias_por_linea() -> list[str]:
    fuera = []
    for proveedor, entradas in CAPABILITY_MATRIX.items():
        for clave, entrada in entradas.items():
            ev = str(entrada.get("evidence") or "")
            if ev and _POR_LINEA.search(ev):
                fuera.append(f"{proveedor}/{clave} -> {ev}")
    return sorted(fuera)


def test_hay_evidencias_para_medir():
    """Si el regex deja de matchear (cambio de formato), _evidencias_por_linea()
    devolvería [] y el ratchet pasaría EN FALSO para siempre. Este lo tapa:
    la matriz TIENE evidencias, así que el conjunto no puede ser vacío por diseño."""
    con_evidencia = [
        1
        for entradas in CAPABILITY_MATRIX.values()
        for e in entradas.values()
        if e.get("evidence")
    ]
    assert len(con_evidencia) >= 90, f"solo {len(con_evidencia)} entradas con evidencia"


def test_ratchet_evidencias_por_simbolo():
    fuera = _evidencias_por_linea()
    assert len(fuera) <= _TOPE_EVIDENCIAS_POR_LINEA, (
        f"{len(fuera)} evidencias ancladas por LÍNEA (tope {_TOPE_EVIDENCIAS_POR_LINEA}). "
        "Un anclaje por línea caduca con el primer commit ajeno. Anclá por SÍMBOLO "
        "('archivo.py:nombre_de_funcion') y BAJÁ el tope en el mismo commit.\n"
        + "\n".join(fuera[:15])
    )


def test_las_convertidas_por_este_plan_no_volvieron_a_linea():
    """ASSERT DE PRESENCIA del valor correcto (G7): el ratchet por sí solo permitiría
    convertir 8 cualesquiera. Estas 4 son las que este plan corrigió a propósito
    porque su anclaje era DEMOSTRABLEMENTE equivocado."""
    esperadas = {
        ("gitlab", "tracker.items.list"): "fetch_open_items",
        ("gitlab", "tracker.items.get"): "get_item",
        ("gitlab", "tracker.auth.html_redirect"): "_validar_base_url",
        ("gitlab", "tracker.rate_limit.clamp"): "_resolver_retry_after",
    }
    for (proveedor, clave), simbolo in esperadas.items():
        ev = str(CAPABILITY_MATRIX[proveedor][clave].get("evidence") or "")
        assert ev.endswith(f":{simbolo}"), f"{proveedor}/{clave} evidencia={ev!r}"


def test_los_webhooks_no_apuntan_al_emisor_saliente():
    """services/webhooks.py es el EMISOR de webhooks salientes de Stacky (fire/_sign).
    Citarlo como evidencia de events.webhook.inbound/verify manda al lector a leer
    código que no tiene nada que ver. Una capacidad absent puede ir sin evidencia."""
    for clave in ("events.webhook.inbound", "events.webhook.verify"):
        ev = str(CAPABILITY_MATRIX["gitlab"][clave].get("evidence") or "")
        assert "webhooks.py" not in ev, f"gitlab/{clave} sigue citando el emisor: {ev!r}"
```

**Tests PRIMERO — comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_ratchet_evidencias.py" -q
```

**Criterio de aceptación BINARIO:** **4 passed**, y el conteo medido:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -c "import sys,re; sys.path.insert(0,'Stacky Agents/backend'); from services.provider_capabilities import CAPABILITY_MATRIX as C; p=re.compile(r'\.(py|ts|tsx):[0-9]+\s*$'); n=sum(1 for pr in C for k,v in C[pr].items() if v.get('evidence') and p.search(str(v['evidence']))); print(n); assert n <= 96, n"
```

**K2 se cumple si ese número es `<= 96`** (baseline 104 − 8 convertidas). Si el implementador convierte más, **baja el tope en el mismo commit** — es un ratchet, no un piso.

**Mitad de contraste (esperado en ROJO antes del código):** con `services/provider_capabilities.py` en el estado de F2 (104 evidencias por línea, salvo las 2 que F2 ya pasó a símbolo — o sea **102**):

```
FAILED test_plan295_ratchet_evidencias.py::test_ratchet_evidencias_por_simbolo
E  AssertionError: 102 evidencias ancladas por LÍNEA (tope 96).
FAILED test_plan295_ratchet_evidencias.py::test_las_convertidas_por_este_plan_no_volvieron_a_linea
E  AssertionError: gitlab/tracker.items.list evidencia='services/gitlab_provider.py:155'
FAILED test_plan295_ratchet_evidencias.py::test_los_webhooks_no_apuntan_al_emisor_saliente
E  AssertionError: gitlab/events.webhook.inbound sigue citando el emisor: 'services/webhooks.py:123'
```

**Tres de los cuatro tests rojos antes.** El primero (`test_hay_evidencias_para_medir`) pasa antes y después a propósito: es el anti-falso-verde del regex, no un gate de la fase.

**Registro en los DOS ratchets:** `tests/test_plan295_ratchet_evidencias.py` en el `.sh` (pelada) **y** en el `.ps1` (entrecomillada). Ver la advertencia de B4.

**Flag que la protege:** **ninguna.** Es un test más una corrección de datos declarativos.

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. Solo `re` y un import puro.

**Trabajo del operador: ninguno.**

---
### F5 — I1 (= QW3): la sonda de configuración habla el TLS del proyecto y distingue certificado de red

**Objetivo:** que `run_gitlab_checks` reciba el `ca_bundle` que el operador **acaba de tipear** y monte el adaptador OpenSSL para el prefijo de ese host, y que agregue un chequeo `chk-tls` que distinga **certificado** de **red** con el vocabulario que `services/local_diagnostics.py` ya usa bien.

**Valor:** hoy, en el escenario para el que se escribió el plan 276 —GitLab self-hosted con CA interna—, "Verificar ahora" devuelve `chk-instancia = fail` con el texto *"No se pudo llegar a esa dirección."* **mientras el sync real funciona perfectamente**. El operador lee "problema de red" cuando el problema es el **certificado**, y los otros tres chequeos quedan en `unknown`. Esta fase hace que la sonda diga la verdad.

**La causa exacta, medida (gotcha G1 — el más caro de este repo):** `backend/app.py:26` llama `truststore.inject_into_ssl()`, que reemplaza `ssl.SSLContext` para **todo el proceso**. `services/tls_openssl_context.py:3-13` lo explica y lo declara **necesario** (la red tiene inspección TLS de Zscaler) y **letal** para el GitLab interno (verifica por Windows CryptoAPI, ignora `VERIFY_X509_PARTIAL_CHAIN`, y `get_ca_certs()` **omite** los certs que no son CA — y el que hace falta es la **hoja**). Consecuencia dura: **`services/gitlab_setup_check.py:32-33` usa `requests.get(...)` pelado y NACE ROTO**, y el síntoma **miente**.

**Lo PROHIBIDO (está escrito en `services/tls_openssl_context.py:11-13`, no es opinión):** `truststore.extract_from_ssl()` (es global y el backend es multi-hilo), `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` / `CURL_CA_BUNDLE` (globales), `verify=False`, y parchear `urllib3`. **Un `verify=<bundle>` a secas NO alcanza**: `truststore` ya reemplazó la clase de contexto.

**Lo PROHIBIDO por decisión de diseño del 259 (no se revierte):** reescribir `gitlab_setup_check` para que use `GitLabClient`. Las tres razones están en su docstring `:7-12` y **siguen siendo correctas**: (1) `GitLabClient` lee `GITLAB_TOKEN` del entorno y **taparía** el token que el operador acaba de tipear ⇒ falso verde; (2) lanza `TrackerConfigError` en `__init__` sin token, y acá "no hay token" es un **resultado**, no una excepción; (3) acá hace falta `allow_redirects=False`, que el cliente general no impone. **Se conserva el camino HTTP propio y se le monta el adaptador.**

#### F5 tiene SEIS patas. Si falta una, el `ca_bundle` no llega y la fase queda de adorno.

Esto **no** es "reenviar un campo": es una cadena de seis puntos, medida abriendo cada archivo.

| # | Archivo (ruta completa) | Anclaje verificado | Qué cambia |
|---|---|---|---|
| 1 | `...\backend\services\gitlab_setup_check.py` | `:28-33` (`_get`), `:36-37` (firma) | acepta `ca_bundle`, monta el adaptador en una `Session`, agrega `chk-tls` |
| 2 | `...\backend\api\setup_guide.py` | `:102-110` (la llamada) | lee `gitlab_ca_bundle` del body y lo pasa |
| 3 | `...\frontend\src\api\endpoints.ts` | `:3486-3491` (tipo del payload) | agrega `gitlab_ca_bundle: string` |
| 4 | `...\frontend\src\components\SetupGuideDialog.tsx` | `:15-24` (`Props.values`) y `:92-98` (`runVerify`) | agrega el campo al tipo **y** al body enviado |
| 5 | `...\frontend\src\components\NewProjectModal.tsx` | `:934-939` (el `values={{...}}`) | pasa `form.gitlab_ca_bundle ?? ""` |
| 6 | `...\frontend\src\components\EditProjectModal.tsx` | `:966-971` (el `values={{...}}`) | pasa `String(form.gitlab_ca_bundle ?? "")` |

> **Verificado: los dos modales YA tienen el campo en su estado de formulario** — `NewProjectModal.tsx:55` (`gitlab_ca_bundle: ""`) y `:851-861` (el input), `EditProjectModal.tsx:52` y `:814-815`. Así que las patas 5 y 6 son **una línea cada una**. Lo que faltaba era el conducto.

#### F5.1 — `services/gitlab_setup_check.py`

**Nombres EXACTOS que se crean en este módulo:**

- `_sesion_para(base: str, ca_bundle: str | None) -> tuple[requests.Session, str]` — devuelve la sesión y un `motivo_tls` (`""` si todo bien, o el texto del problema del bundle).
- `_res_tls_ok`, `_res_tls_fail` — no son funciones nuevas: se usa `_res("chk-tls", ...)` que ya existe (`:24-25`).
- Constante `_ID_TLS = "chk-tls"`.

**Firma nueva de `run_gitlab_checks` (aditiva, backward-compatible — `ca_bundle` es keyword con default):**

```python
def run_gitlab_checks(base_url: str, project_path: str, token: str,
                      engine_enabled: bool, engine_will_enable: bool = False,
                      *, ca_bundle: str | None = None) -> list[dict]:
```

> `ca_bundle` va **después del `*`** a propósito: obliga a pasarlo por nombre y hace imposible que un llamador viejo lo pise por posición. Los tests existentes del 259 (`backend/tests/test_plan259_setup_guide_api.py`, `test_plan259_setup_guide_data.py`) no lo pasan y **siguen pasando**.

**Pseudocódigo del montaje (las mismas 7 líneas de `services/gitlab_client.py:177-183`, importadas, no copiadas):**

```python
def _sesion_para(base: str, ca_bundle: str | None) -> tuple[requests.Session, str]:
    """Sesión con el contexto OpenSSL GENUINO montado SOLO para el prefijo de este
    host. Ver G1: truststore.inject_into_ssl() (app.py:26) reemplaza ssl.SSLContext
    para TODO el proceso, así que `verify=<bundle>` NO alcanza y un requests.get()
    pelado contra el GitLab interno NACE ROTO con un síntoma que miente.

    Devuelve (sesion, motivo_tls). motivo_tls != "" significa que el bundle DECLARADO
    no se pudo usar: eso ya es un veredicto de chk-tls, sin tocar la red.
    """
    from services.gitlab_client import _AdaptadorOpenSSL           # reusar, no copiar
    from services.tls_openssl_context import CaBundleInvalido, crear_contexto_openssl

    sesion = requests.Session()
    if not ca_bundle:
        return sesion, ""                       # sin bundle declarado: camino de hoy
    habilitado = bool(getattr(config.config, "STACKY_GITLAB_TLS_ADAPTER_ENABLED", True))
    if not habilitado:
        return sesion, ""                       # flag OFF: byte-idéntico a hoy
    try:
        contexto = crear_contexto_openssl(ca_bundle)
    except CaBundleInvalido as exc:
        # NO se lanza: acá "el bundle no sirve" es un RESULTADO, igual que
        # "no hay token" (razón 2 del docstring :7-12).
        return sesion, str(exc)
    if contexto is not None and base:
        sesion.mount(base, _AdaptadorOpenSSL(contexto))
    return sesion, ""
```

**`_get` pasa a recibir la sesión (cambio mínimo de `:28-33`):**

```python
def _get(sesion, base: str, path: str, token: str | None):
    headers = {"Accept": "application/json"}
    if token:
        headers["PRIVATE-TOKEN"] = token
    # allow_redirects=False SE CONSERVA: un 30x reenviaría PRIVATE-TOKEN a otro host.
    return sesion.get(f"{base}/api/v4{path}", headers=headers,
                      timeout=_TIMEOUT_S, allow_redirects=False)
```

**El chequeo `chk-tls` — dónde va y qué dice.** Va **entre** `chk-flag` y `chk-instancia`, porque el TLS es lo que ocurre **antes** de que haya una respuesta HTTP. Vocabulario tomado de `services/local_diagnostics.py:158-174` (`_mensaje_de_falla_gitlab`), que ya nombra la **pieza** que falló:

```python
    # ── chk-tls (Plan 295 F5) ────────────────────────────────────────────────
    # Va ANTES de chk-instancia porque el handshake ocurre antes de que exista un
    # status HTTP. Sin este chequeo, un cert que no cierra salía como
    # chk-instancia=fail "No se pudo llegar a esa dirección" -> culpaba a la RED.
    sesion, motivo_bundle = _sesion_para(base, ca_bundle)
    if motivo_bundle:
        out.append(_res(_ID_TLS, _FAIL,
                        "El certificado de la empresa que declaraste no se pudo usar. "
                        "Revisá el campo 'Certificado de la empresa' del proyecto.",
                        motivo_bundle))
        for cid in ("chk-instancia", "chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN,
                            "No se pudo probar: el certificado declarado no se pudo leer."))
        return out
    try:
        _get(sesion, base, "/version", None)
        out.append(_res(_ID_TLS, _OK, "El TLS cerró: el certificado del servidor es válido."))
    except requests.exceptions.SSLError as exc:
        # LA DISTINCIÓN QUE ESTE PLAN AGREGA. NO dice "no se pudo llegar".
        out.append(_res(_ID_TLS, _FAIL,
                        "El certificado del servidor no cerró la cadena de confianza. "
                        "Si tu GitLab usa un certificado de la empresa, pegalo en el "
                        "campo 'Certificado de la empresa' del proyecto.",
                        type(exc).__name__))
        for cid in ("chk-instancia", "chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN,
                            "No se pudo probar: el certificado no cerró."))
        return out
    except requests.RequestException:
        # Cualquier otro fallo de transporte NO es del certificado: chk-tls queda
        # en unknown y el veredicto lo da chk-instancia, que ya sabe decirlo.
        out.append(_res(_ID_TLS, _UNKNOWN,
                        "No se pudo evaluar el certificado: la dirección no respondió."))
```

**Casos borde declarados, uno por uno:**

| Entrada | Salida esperada |
|---|---|
| `ca_bundle=None` o `""` | `chk-tls` se evalúa **igual** (sin montar adaptador): si el server tiene cert público, `ok`; si no cierra, `fail` con el mensaje que **invita a pegar el certificado**. Es el caso más valioso: le dice al operador qué campo llenar. |
| `ca_bundle` con ruta que **no existe** | `chk-tls = fail` con el texto de `CaBundleInvalido` en `detail`. **Sin tocar la red.** Los otros 4 en `unknown`. |
| `ca_bundle` válido pero el cert **no corresponde** al host | `chk-tls = fail` por `SSLError`. |
| flag `STACKY_GITLAB_TLS_ADAPTER_ENABLED` en **OFF** | sesión pelada: comportamiento **byte-idéntico** al de hoy. `chk-tls` sigue existiendo (la UI necesita la lista completa) y da el veredicto que dé el `requests` sin adaptador. |
| URL sin `http://`/`https://` | el `return` temprano de `:63-68` **se conserva**, y hay que agregar `chk-tls` a la lista de `unknown` de ese camino. **Sin esto la UI recibe 5 resultados en un camino y 6 en otro.** |
| `base` vacío | no se monta nada (`if contexto is not None and base`), sesión pelada. |

> **REGLA DURA de esta fase, y es la que rompe si se olvida:** `run_gitlab_checks` **devuelve SIEMPRE la MISMA cantidad de resultados en TODOS los caminos de salida** — lo dice su propio docstring `:45-47` ("*la UI lo necesita para pintar la lista*"). Con `chk-tls` pasa de **5 a 6**. Hay **cuatro** `return` tempranos en la función actual (`:68`, `:88`, `:98`, `:105`, `:151`) y **cada uno** tiene que emitir los 6. El test de F5 lo asertá.

#### F5.2 — `api/setup_guide.py`

Cambio en la llamada de `:102-110`:

```python
        checks = run_gitlab_checks(
            base_url=str(body.get("gitlab_url") or "").strip(),
            project_path=str(body.get("gitlab_project") or "").strip(),
            token=str(body.get("gitlab_token") or "").strip(),
            engine_enabled=_flag("STACKY_GITLAB_ENABLED", default=False),
            engine_will_enable=bool(body.get("gitlab_enable_engine", False)),
            # Plan 295 F5 — el certificado que el operador ACABA de tipear (no el
            # guardado): mismo criterio que el token. Sin esto la sonda hablaba un
            # TLS distinto del que usa el sync y daba rojo con el producto andando.
            ca_bundle=str(body.get("gitlab_ca_bundle") or "").strip() or None,
        )
```

> **Nada más se toca en este archivo.** El `except Exception` de `:112-114` **se conserva** (no loguea el bundle, solo el tipo de excepción), y la línea de log de `:116` sigue siendo **solo** el mapa `id -> status`: `chk-tls` entra ahí sin filtrar nada nuevo. **El `ca_bundle` NUNCA se loguea** — es una ruta, no un secreto, pero el criterio del módulo es no emitir nada del body.

#### F5.3 — las cuatro patas del frontend

**`frontend/src/api/endpoints.ts:3486-3491`:**

```ts
  verifyGitlab: (payload: {
    gitlab_url: string;
    gitlab_project: string;
    gitlab_token: string;
    gitlab_enable_engine: boolean;
    gitlab_ca_bundle: string;      // Plan 295 F5
  }) =>
```

**`frontend/src/components/SetupGuideDialog.tsx`** — dos ediciones:

- en `Props` (`:21-24`): agregar `gitlab_ca_bundle: string;`
- en `runVerify` (`:92-98`): agregar `gitlab_ca_bundle: values.gitlab_ca_bundle,`

**`frontend/src/components/NewProjectModal.tsx:934-939`:** agregar `gitlab_ca_bundle: form.gitlab_ca_bundle ?? "",`

**`frontend/src/components/EditProjectModal.tsx:966-971`:** agregar `gitlab_ca_bundle: String(form.gitlab_ca_bundle ?? ""),`

> **`SetupGuideDialog.tsx` NO guarda el bundle en su estado**, igual que el token (ver el comentario de `:93-94`: "*El token se pasa como ARGUMENTO y se descarta*"). Se lee de `values` y se manda. Cero estado nuevo.

#### F5.4 — Tests

**Archivos de test a crear:**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_sonda_tls.py`
2. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\projects\__tests__\plan295VerifyPayload.test.ts`

**Casos del test de backend (8):**

| # | Caso | Assert exacto |
|---|---|---|
| 1 | `SSLError` en `/version` ⇒ `chk-tls = fail` y el mensaje habla de **certificado** | `r["status"] == "fail"` y `"certificado" in r["message"].lower()` |
| 2 | ese mensaje **NO** dice "no se pudo llegar" (la mentira de hoy) | `"no se pudo llegar" not in r["message"].lower()` |
| 3 | con `SSLError`, los otros 4 quedan `unknown` (no `fail`) | ningún otro `status == "fail"` |
| 4 | **el `ca_bundle` llega hasta el `mount()`** | monkeypatch de `requests.Session.mount`; se captura `(prefijo, adaptador)` y se asertá `prefijo == base` y `type(adaptador).__name__ == "_AdaptadorOpenSSL"` |
| 5 | `ca_bundle` con ruta inexistente ⇒ `chk-tls = fail` **sin tocar la red** | monkeypatch de `Session.get` que **lanza** `AssertionError("no debió llamarse")`; el test pasa solo si no se llama |
| 6 | camino feliz ⇒ `chk-tls = ok` | `r["status"] == "ok"` y `"cerró" in r["message"]` |
| 7 | **[v2, C11] los 6 resultados en los SEIS caminos de salida** | `@pytest.mark.parametrize` sobre los **6** escenarios de la tabla de abajo: `len(checks) == 6` y `{c["id"] for c in checks} == {"chk-flag","chk-tls","chk-instancia","chk-token","chk-scope","chk-proyecto"}` |
| 8 | `allow_redirects=False` se conserva | capturar los kwargs de `Session.get` y asertá `kwargs["allow_redirects"] is False` |
| 9 | **[v2, C10] el bundle declarado por ENTORNO también llega al `mount()`** | campo del proyecto vacío (`ca_bundle=None`) **y** `monkeypatch.setenv("STACKY_GITLAB_CA_BUNDLE", str(pem_real))` ⇒ el `mount()` ocurre igual. Sin esto la sonda habla un TLS distinto del sync cuando el operador configuró el bundle por env |

**[v2, C11] Los SEIS caminos de salida de `run_gitlab_checks`, enumerados uno por uno (leídos del archivo, no contados de memoria):**

| # | Línea del `return out` | Escenario que lo dispara | Hoy emite | Después de F5 tiene que emitir |
|---|---|---|---|---|
| 1 | **`:68`** | `base_url` sin `http://` ni `https://` | 4 (`chk-flag` + `chk-instancia` fail + 3 unknown) | **6** — hay que agregar `chk-tls` a la lista de `unknown` de ese camino |
| 2 | **`:88`** | `/version` responde 301/302/307/308 | 5 | **6** |
| 3 | **`:98`** | `requests.RequestException` en `/version` | 5 | **6** |
| 4 | **`:105`** | no hay token | 5 | **6** |
| 5 | **`:151`** | falta el `project_path` | 5 | **6** |
| 6 | **`:173`** | **el `return out` FINAL — camino completo** | 5 | **6** |

> 🛑 **[v2, C11] El v1 decía "Hay CUATRO `return` tempranos (`:68`, `:88`, `:98`, `:105`, `:151`)" — contaba cuatro y listaba cinco — y OMITÍA el `return out` final de `:173`.** Son **SEIS** puntos de salida. Y los dos caminos nuevos que agrega F5 (bundle inválido y `SSLError`) también hacen `return out`, así que al terminar la fase son **OCHO**: los 6 de arriba más 2 propios, y **los ocho** emiten 6 resultados.
>
> **Por qué importa y no es cosmético:** el docstring `:45-47` dice textual "*Devuelve SIEMPRE 5 resultados … en todos los caminos de salida: la UI lo necesita para pintar la lista*". Si el implementador parchea 5 de 6, hay un camino que devuelve **5** cuando el resto devuelve 6, y el `SetupGuideDialog` pinta una lista corta sin error visible. El caso 7 con **6** escenarios parametrizados es lo único que lo caza.
>
> **Y el docstring se actualiza:** "*Devuelve SIEMPRE **6** resultados*". Dejarlo en 5 deja una mentira nueva en el archivo cuyo objetivo es dejar de mentir.

> **El caso 4 es el que el insumo pide explícitamente** ("*test que el `ca_bundle` del body llega hasta el `mount()`*") y es **el único** que prueba que la fase hizo algo. Los otros 8 prueban que no rompió nada.
>
> **Ningún caso toca la red.** Todos monkeypatchean `requests.Session.get` / `.mount`. Base SQLite: **no se usa BD** en este módulo, así que no hace falta fixture de DB — pero el archivo **igual** tiene que evitar `create_app()` (que fuera de pytest tiene efectos reales).

**Casos del test de frontend (3, en `.ts` PURO):**

El test **no** renderiza el diálogo (RTL/jsdom no están instalados). Prueba la **forma del payload** con una función pura extraída, o —más simple y sin refactor— **leyendo el archivo fuente** y verificando que las 4 patas están:

```ts
// Plan 295 F5 — gate de las CUATRO patas de frontend del ca_bundle. Es un test de
// TEXTO FUENTE a propósito: RTL/jsdom no están instalados en este repo, y lo que
// hay que garantizar es que el conducto está soldado en los 4 archivos. Un test
// de render no lo probaría mejor y no puede correr acá.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const leer = (p: string) => readFileSync(resolve(SRC, p), "utf-8");

describe("plan 295 F5 — el ca_bundle llega al verificador", () => {
  it("el tipo del payload de verifyGitlab lo declara", () => {
    const t = leer("api/endpoints.ts");
    const bloque = t.slice(t.indexOf("verifyGitlab:"), t.indexOf("verifyGitlab:") + 400);
    expect(bloque).toContain("gitlab_ca_bundle");
  });

  it("el dialogo lo manda en runVerify", () => {
    const t = leer("components/SetupGuideDialog.tsx");
    expect(t).toContain("gitlab_ca_bundle: values.gitlab_ca_bundle");
  });

  it("los DOS modales lo pasan en values", () => {
    expect(leer("components/NewProjectModal.tsx")).toContain("gitlab_ca_bundle: form.gitlab_ca_bundle");
    expect(leer("components/EditProjectModal.tsx")).toContain("gitlab_ca_bundle: String(form.gitlab_ca_bundle");
  });
});
```

> El caso 1 **acota la búsqueda al bloque de `verifyGitlab`** en vez de grepear el archivo entero: `endpoints.ts` menciona `gitlab_ca_bundle` en otros lugares y un `toContain` sobre todo el archivo pasaría **en falso**.

**Comandos exactos:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_sonda_tls.py" -q
```

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run "src/projects/__tests__/plan295VerifyPayload.test.ts"
```

**No-regresión obligatoria (los tests del 259 que tocan esta función):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_setup_guide_api.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_setup_guide_data.py" -q
```

> **Estos dos archivos pueden ponerse rojos legítimamente** si asertán `len(checks) == 5`. Si pasa, **se actualizan a 6** y se anota en el doc: es el contrato que esta fase cambia a propósito, y el cambio es **aditivo** para la UI (`SetupGuideDialog` itera la lista que recibe con `setChecks(res.data.checks)`, no un largo fijo — verificado en `:98-100`). **Si asertán los 5 ids como conjunto exacto, también se actualizan.** Cualquier otro rojo en esos archivos es daño y hay que arreglarlo. **Baseline medido en F0: `test_plan259_setup_guide_api.py` = `27 passed`, `test_plan259_setup_guide_data.py` = `14 passed`. Los dos VERDES: cualquier rojo que no sea un `== 5` es daño propio.**

**Criterio de aceptación BINARIO [v2, C10 + C11]:** **`9 passed`** en `test_plan295_sonda_tls.py` (8 del v1 + el caso 9 del bundle por entorno; y el caso 7 corre **parametrizado sobre 6 escenarios**, no 5), `3 passed` en el test de frontend, y los dos archivos del 259 con **delta cero** respecto de F0 (o actualizados al largo 6 y verdes).

**Mitad de contraste (esperado en ROJO antes del código):** con `services/gitlab_setup_check.py` sin tocar:

```
FAILED test_plan295_sonda_tls.py::test_ssl_error_da_chk_tls_fail
E  AssertionError: no hay ningún resultado con id 'chk-tls' (ids: chk-flag,
   chk-instancia, chk-token, chk-scope, chk-proyecto)
FAILED test_plan295_sonda_tls.py::test_el_ca_bundle_llega_al_mount
E  TypeError: run_gitlab_checks() got an unexpected keyword argument 'ca_bundle'
```

**El segundo output es el más importante:** `TypeError` por el kwarg inexistente demuestra que hoy **no hay forma** de que el bundle llegue. Y del lado del frontend, los 3 casos fallan con `expected ... to contain 'gitlab_ca_bundle'`.

**Flag que la protege:** **`STACKY_GITLAB_TLS_ADAPTER_ENABLED`** — **REUSADA, no creada**. Ya existe, ya está **ON** (`deployment/harness_defaults.env:261` la lista en `true`) y ya gobierna exactamente esta decisión en `services/gitlab_client.py:158-160`. Con la flag **OFF**, `_sesion_para` devuelve una sesión pelada y el comportamiento es **byte-idéntico** al de hoy. **Cero flags nuevas en esta fase**, y eso es una virtud: una flag nueva para el mismo interruptor conceptual crearía dos escritores de la misma decisión.

**Impacto por runtime:**
- **Codex CLI** — sin impacto. La sonda es HTTP del backend; el runtime no participa.
- **Claude Code CLI** — sin impacto, ídem.
- **GitHub Copilot Pro** — sin impacto, ídem.
- **Fallback común:** si `services/tls_openssl_context.crear_contexto_openssl` devolviera `None` (bundle vacío o `_ssl` sin los descriptores esperados), `_sesion_para` **no monta nada** y la sonda se comporta como hoy. Degrada, no rompe. **Ningún runtime queda sin la funcionalidad.**

**Trabajo del operador: ninguno** para que la fase funcione. **PENDIENTE DEL OPERADOR** aparte: el humo con su GitLab interno real (ver §10).

---
### F6 — I2a (= QW2): un fallo de la API de GitLab deja de salir como `500 unexpected`

**Objetivo:** agregar `except TrackerApiError` a los **dos** endpoints de sync y traducirlo a `502` con `{"error": "gitlab_api", "kind": exc.kind, "message": ...}` y copy accionable por `kind`.

**Valor:** hoy un PAT de GitLab vencido produce `TrackerApiError(401, kind="auth")`, cae en `except Exception`, y el operador recibe `HTTP 500 {"ok": false, "error": "unexpected", "message": "..."}`. El equivalente ADO recibe copy accionable, `502` semántico y alimentación del breaker (`_ado_sync_error_response`, `backend/api/tickets.py:308-359`). **El operador de GitLab ve un bug del backend donde hay una credencial que renovar.**

**La causa exacta, medida (gotcha G4):** `TrackerApiError` **no es hermana** de `AdoApiError`. Deriva de una rama separada: `TrackerError(RuntimeError)` → `TrackerApiError` (`backend/services/tracker_provider.py:46,52-57`). La lista de `except` de `sync-v2` **se ve completa** —captura `AdoConfigError` (`:6679`), `AdoApiError` (`:6683`), `CapabilityUnavailable` (`:6686`), `TrackerConfigError` (`:6692`)— y **no lo está**: falta la única excepción que los adaptadores de tracker genéricos levantan de verdad. `POST /sync` (`:1219-1249`) tiene el mismo hueco: captura `CapabilityUnavailable` (`:1229`), `AdoConfigError` (`:1243`), `AdoApiError` (`:1246`) y `Exception` (`:1248`).

**Firma verificada de la excepción:**

```python
class TrackerApiError(TrackerError):
    def __init__(self, status: int, message: str, *, kind: str = "unknown"):
        self.status = status
        self.kind = kind
```

> **`.status`, NO `.status_code`.** `_ado_sync_error_response` lee `getattr(exc, "status_code", None)` (`:324`) porque `AdoApiError` usa ese nombre. **Confundirlos hace que el handler nuevo lea `None` siempre** y clasifique todo como genérico. Es el error más fácil de cometer en esta fase.

**[v2, C12] Los SIETE `kind` que el cliente produce de verdad** (verificado abriendo `services/gitlab_client.py:103-123` y los `except` de `_request`):

| `kind` | Origen | Nace de un status HTTP? |
|---|---|---|
| `auth` | 401 / 403 | sí |
| `not_found` | 404 | sí |
| `rate_limited` | 429 | sí |
| `server` | ≥ 500 | sí |
| **`unknown`** | **`return "unknown"` final de `_kind_for_status` ⇒ 400, 409, 422 y todo 4xx no listado. Además es el `default` de `TrackerApiError.__init__`** | sí |
| `tls` | asignado en el `except` de `_request`: el handshake no cerró | **no** |
| `network` | asignado en el `except` de `_request`: murió antes de tener respuesta | **no** |

> 🛑 **[v2, C12] El v1 decía "los SEIS kind que el cliente produce de verdad" y omitía `unknown`.** No es un caso teórico: `_kind_for_status` (`:117-123`) tiene `return "unknown"` como última línea, así que **400, 409 y 422 — los errores de validación más comunes de la API de GitLab — llegan con `kind="unknown"`**. Con el mapa de seis entradas, el segundo caso más frecuente después de `auth` recibía el copy genérico "*Stacky no pudo clasificar*", que es el menos accionable de todos. La séptima entrada lo arregla.
>
> El docstring de `_kind_for_status:106-113` sigue mandando en lo demás: **`kind == "tls"` significa "el certificado/la cadena no cerró"; cualquier otro kind implica que el TLS anduvo porque hubo respuesta HTTP.**

**Archivos EXACTOS a editar (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\tickets.py` — se crea un helper y se agregan dos `except`.

**Nombre EXACTO del helper que se crea:** `_gitlab_sync_error_response(exc, *, route_label: str, project_name: str | None)`, ubicado **inmediatamente después** de `_ado_sync_error_response` (que termina en `:359`), para que sea evidente que son el par simétrico.

**Copy por `kind` (mapa literal, sin inventar nada en runtime):**

```python
# Plan 295 F6 — copy ACCIONABLE por kind. Cada mensaje nombra (a) el sistema
# GitLab, y (b) QUÉ tiene que hacer el operador. Ninguno dice "unexpected".
_COPY_GITLAB_POR_KIND: dict[str, str] = {
    "auth": (
        "GitLab rechazó las credenciales del proyecto (401/403). El token venció, "
        "fue revocado o está mal copiado: renovalo en la configuración del proyecto."
    ),
    "not_found": (
        "GitLab respondió 'no existe' (404). Revisá el campo 'Proyecto' del proyecto "
        "(tiene que ser grupo/proyecto) y que la dirección del servidor NO incluya el "
        "namespace pegado."
    ),
    "rate_limited": (
        "GitLab está limitando los pedidos (429) y los reintentos automáticos se "
        "agotaron. Esperá hasta 30 segundos y volvé a sincronizar."
    ),
    "server": (
        "El servidor de GitLab devolvió un error propio (5xx). No es un problema de "
        "Stacky ni de tus credenciales: reintentá en unos minutos."
    ),
    "tls": (
        "El certificado del GitLab no cerró la cadena de confianza. Pegá el "
        "certificado de la empresa en el campo 'Certificado de la empresa' del "
        "proyecto y verificá la configuración desde la guía."
    ),
    "network": (
        "No se pudo llegar al servidor de GitLab. Revisá la dirección del servidor y "
        "la conexión de red o la VPN."
    ),
    # Plan 295 F6 [v2, C12] — SÉPTIMA entrada, y NO es un caso hipotético.
    # _kind_for_status (gitlab_client.py:103-123) devuelve "unknown" para TODO status
    # que no sea 401/403/404/429/>=500 -- o sea 400, 409 y 422, que en GitLab son los
    # errores de VALIDACIÓN más comunes. Y TrackerApiError.__init__ tiene
    # `kind: str = "unknown"` por default. Sin esta entrada, el caso más frecuente
    # después de auth caía en el fallback genérico, que es el copy MENOS accionable.
    "unknown": (
        "GitLab rechazó el pedido y no dijo por qué de forma estándar (suele ser un "
        "400, 409 o 422: un dato del pedido que GitLab no acepta). El detalle técnico "
        "está en 'detail'. Si se repite, revisá la configuración del proyecto en "
        "Stacky contra el proyecto real de GitLab."
    ),
}
# Sólo para un kind que NO esté en el mapa: un kind nuevo que agregue un plan futuro.
# Los siete que el cliente produce HOY están todos arriba.
_COPY_GITLAB_FALLBACK = (
    "GitLab devolvió un error que Stacky no pudo clasificar. El detalle técnico va "
    "en el campo 'detail'."
)
```

> El texto de `rate_limited` dice **"hasta 30 segundos"** y no un número calculado: `TrackerApiError` **no expone `retry_after`** (verificado en su `__init__`), y el cliente ya clampeó y reintentó internamente hasta 3 veces (`_RETRY_MAX = 3`, `services/gitlab_client.py:33`) con tope de `_RETRY_AFTER_MAX = 30.0` (`:37`). Que un `rate_limited` llegue al endpoint significa que **los reintentos se agotaron**. Los 30 s son el tope real del clamp, no una invención.

**Pseudocódigo del helper:**

```python
def _gitlab_sync_error_response(exc, *, route_label: str, project_name: str | None):
    """Plan 295 F6 — el par simétrico de _ado_sync_error_response, para GitLab.

    POR QUÉ EXISTE: TrackerApiError NO es hermana de AdoApiError (rama separada
    desde TrackerError(RuntimeError), tracker_provider.py:46,52), así que la lista
    de `except` de estos endpoints se VEÍA completa y no lo estaba: un PAT vencido
    caía en `except Exception` y salía como 500 "unexpected".

    502, no 500: el fallo es de un sistema AGUAS ARRIBA, no de Stacky. Mismo código
    que el camino ADO (:328, :359).
    """
    kind = str(getattr(exc, "kind", "") or "unknown")
    # OJO: TrackerApiError usa `.status`, NO `.status_code` (que es de AdoApiError).
    status_upstream = getattr(exc, "status", None)
    mensaje = _COPY_GITLAB_POR_KIND.get(kind, _COPY_GITLAB_FALLBACK)

    ctx = resolve_project_context(project_name=project_name)
    nombre = (ctx.stacky_project_name if ctx else project_name) or "<sin proyecto>"

    # El log NO incluye el token ni el cuerpo de la respuesta: solo la clasificación.
    logger.warning(
        "GitLab %s — api fallo (project=%s kind=%s status=%s): %s",
        route_label, nombre, kind, status_upstream, str(exc)[:200],
    )

    # F7 engancha acá la alimentación del breaker. En F6 este bloque NO existe todavía.

    return jsonify({
        "ok": False,
        "error": "gitlab_api",          # machine-readable, distinto de "ado_api"
        "kind": kind,                   # auth|not_found|rate_limited|server|tls|network
        "message": mensaje,             # copy accionable que NOMBRA GitLab
        "detail": str(exc)[:300],       # técnico, para el que sabe leerlo
        "gitlab_status_code": status_upstream,
        "project_name": nombre,
        "tracker_type": "gitlab",
    }), 502
```

**Los dos `except` a agregar. Ubicación EXACTA y por qué ahí:**

**En `sync_from_ado_v2`** — entre `except AdoApiError as e:` (`:6683-6685`) y `except _CapabilityUnavailable:` (`:6686`):

```python
    except TrackerApiError as e:
        # Plan 295 F6 — el hueco: esta excepción NO es hermana de AdoApiError y caía
        # en el `except Exception` de abajo => 500 "unexpected".
        _sync_in_progress_by_project.discard(sync_scope)
        return _gitlab_sync_error_response(e, route_label="sync-v2", project_name=project_name)
```

**En `sync_from_ado`** — entre `except AdoApiError as e:` (`:1246-1247`) y `except Exception as e:` (`:1248`):

```python
    except TrackerApiError as e:
        # Plan 295 F6 — ídem sync-v2. Este endpoint lo dispara el operador A MANO
        # desde el selector de tickets (:1223-1227), así que es EL camino donde un
        # 500 "unexpected" es más visible y más confuso.
        return _gitlab_sync_error_response(e, route_label="sync", project_name=project_name)
```

**Casos borde y reglas de orden que NO se pueden violar:**

| Regla | Por qué |
|---|---|
| El `except TrackerApiError` va **ANTES** del `except TrackerConfigError` en `sync-v2` | Las dos derivan de `TrackerError`, pero son **hermanas** (ninguna es subclase de la otra), así que el orden entre ellas es indiferente para Python. **Se ubica antes por legibilidad**: los dos `Tracker*` quedan juntos y se lee que la lista está completa. |
| El `except TrackerApiError` va **DESPUÉS** del `except _CapabilityUnavailable` **NO** — va antes | `CapabilityUnavailable` **sí** deriva de `TrackerError` (`tracker_provider.py:59`), **pero no de `TrackerApiError`**, así que tampoco hay captura accidental. Verificado. **Si alguna vez se agregara un `except TrackerError` genérico, tendría que ir ÚLTIMO de los cuatro.** |
| El `except Exception` **se conserva tal cual** | Es la red de seguridad. Este plan le quita una clase de fallo, no lo borra. |
| `_sync_in_progress_by_project.discard(sync_scope)` en el `except` de `sync-v2` | Los otros `except` de ese endpoint lo hacen (`:6680`, `:6684`, `:6700`). Hay un `finally` que también lo hace (`:6702-6703`), así que es redundante — **se pone igual, por simetría con los hermanos**: un lector que ve 4 `except` con `discard` y 1 sin él va a asumir que es un bug. |
| `sync_from_ado` **no** toca `_sync_in_progress_by_project` | Ese set es de `sync-v2` solamente. Agregarlo ahí sería inventar estado. |

**Tests PRIMERO — archivo a crear:**

`N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_errores_gitlab.py`

**Casos a cubrir (10):**

| # | Caso | Assert |
|---|---|---|
| 1 | `sync-v2` + `TrackerApiError(401, "...", kind="auth")` ⇒ **502** | `resp.status_code == 502` |
| 2 | ese cuerpo trae `error == "gitlab_api"` | `data["error"] == "gitlab_api"` |
| 3 | ese cuerpo trae `kind == "auth"` | `data["kind"] == "auth"` |
| 4 | **el mensaje NOMBRA GitLab** | `"gitlab" in data["message"].lower()` |
| 5 | el mensaje **no** dice "unexpected" | `"unexpected" not in data["message"].lower()` |
| 6 | **[v2, C12]** los **7** `kind` producen **7** mensajes **distintos** | `len({_COPY_GITLAB_POR_KIND[k] for k in ("auth","not_found","rate_limited","server","tls","network","unknown")}) == 7` |
| 7 | un `kind` **fuera del mapa** cae en el fallback y sigue dando 502 | `TrackerApiError(418, "...", kind="marciano")` ⇒ 502, `data["kind"] == "marciano"` y `data["message"] == _COPY_GITLAB_FALLBACK` |
| 8 | `POST /sync` (el otro endpoint) ⇒ **502**, no 500 | `resp.status_code == 502` |
| 9 | `AdoApiError` sigue yendo por el camino ADO (**no-regresión**) | `data["error"] in ("ado_api", "ado_auth_invalid")` — verificado: `_ado_sync_error_response` devuelve `"ado_api"` con 502 para status ≠ 401/403 y `"ado_auth_invalid"` con 502 para 401/403 |
| 10 | `.status` y no `.status_code`: el status upstream llega al cuerpo | `data["gitlab_status_code"] == 401` |
| 11 | **[v2, C12] un HTTP 422 real produce `kind="unknown"` y copy ACCIONABLE, no el fallback** | `TrackerApiError(422, "...", kind=_kind_for_status(422))` ⇒ `data["kind"] == "unknown"` **y** `data["message"] != _COPY_GITLAB_FALLBACK` **y** `"gitlab" in data["message"].lower()` |

> **[v2, C12] El caso 11 es el que impide que la séptima entrada se agregue "de adorno".** Sin él, alguien podría dejar `unknown` fuera del mapa y el caso 7 (que usa `"marciano"`) pasaría igual. El 11 llama a `_kind_for_status(422)` de verdad — no hardcodea el string — así que si mañana el cliente cambia la clasificación de 422, el test lo dice.

**Cómo se inyecta la excepción (sin red, sin credenciales):** monkeypatch de `_sync_via_provider_or_ado` en el módulo `api.tickets` para que **lance** la excepción pedida. Es el único punto que los dos endpoints comparten (`:1228` y `:6677`).

```python
import pytest
from services.tracker_provider import TrackerApiError

@pytest.fixture
def app_cliente(tmp_path, monkeypatch):
    """Base SQLite FRESCA por archivo. NUNCA la del operador: un pytest suelto
    escribe en la BD real si no se aísla DATABASE_URL."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'plan295.db'}")
    monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path))   # aislar data_dir() también
    ...
```

> **Aislar `DATABASE_URL` NO aisla `data_dir()`.** El breaker de F7 escribe `integration_breaker.json` en `data_dir()`. Si no se aísla, **el test deja archivos reales en la carpeta del operador**. Este fixture se comparte con F7 y F8.

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_errores_gitlab.py" -q
```

**Criterio de aceptación BINARIO:** **10 passed**.

**Mitad de contraste (esperado en ROJO antes del código):**

```
FAILED test_plan295_errores_gitlab.py::test_sync_v2_pat_vencido_da_502
E  assert 500 == 502
FAILED test_plan295_errores_gitlab.py::test_el_cuerpo_dice_gitlab_api
E  assert 'unexpected' == 'gitlab_api'
FAILED test_plan295_errores_gitlab.py::test_el_mensaje_nombra_gitlab
E  KeyError: 'kind'
```

**Este es el output que el insumo pide explícitamente** ("*debe dar `500`/"unexpected" contra el commit anterior*"). Los casos 1-8 y 10 fallan antes; el caso 9 (no-regresión de ADO) **pasa antes y después**, y eso es correcto: prueba que la fase no rompió el hermano.

**Flag que la protege:** **`STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED`** — **NUEVA, default ON**.

- **Categoría de excepción: NINGUNA.** Esta flag no quema tokens en reposo (no hay loop ni modelo) y no escribe en ningún sistema real del operador. Es **traducir un error que ya ocurre** en una respuesta HTTP más honesta: leer, clasificar, mostrar. **Solo-lectura ⇒ va ON**, sin excepción que citar.
- **Por qué existe la flag entonces:** para que F8 —que **reordena** código en el camino caliente compartido con ADO— tenga una reversión de una sola perilla. Las tres fases de I2 (F6, F7, F8) van detrás de **la misma** flag, porque revertir una sin las otras deja un estado intermedio sin sentido (un breaker que se alimenta y nadie consulta).
- **Con la flag OFF:** el `except TrackerApiError` **existe** pero re-lanza (`raise`), y el fallo vuelve a caer en `except Exception` ⇒ `500 "unexpected"`, byte-idéntico a hoy. **No se borra el `except`**: se hace transparente. Así el camino apagado es una línea, no una rama duplicada.
- **Los TRES lugares del default ON:** (1) `backend/config.py` — `STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED: bool = os.getenv("STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED", "true").lower() != "false"`; (2) la `FlagSpec` en `backend/services/harness_flags.py` con `default=True`; (3) `_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py` (**es booleana ON, así que SÍ va acá** — a diferencia de la numérica de F10). Más `_CATEGORY_KEYS` y `harness_flags_help.py` (ver el detalle completo en F10, que enumera los guardianes; **esta flag los necesita todos igual**).

**Impacto por runtime:**
- **Codex CLI / Claude Code CLI / GitHub Copilot Pro** — **idéntico**. Es un handler HTTP del backend. Ningún runtime de agente participa en el camino de sync.
- **Fallback común:** con la flag OFF, comportamiento de hoy. Si `resolve_project_context` devolviera `None` (proyecto no resoluble), `nombre` cae a `"<sin proyecto>"` y la respuesta sale igual: **el handler nunca puede ser la causa de un 500**.

**Trabajo del operador: opt-in (default ON).**

---

### F7 — I2b: GitLab tiene su propio circuit breaker

**Objetivo:** dar a GitLab una key de breaker propia, `"gitlab_sync"`, alimentada **solo** por los `kind` que son fallos terminales de configuración, reusando `services/integration_breaker.py` **tal cual**.

**Valor:** hoy un GitLab con PAT vencido se golpea en cada sync, cada 45 segundos, indefinidamente. ADO y Jira tienen backoff exponencial (15 min → tope 6 h, `services/integration_breaker.py:22-23`); GitLab no tiene nada.

**Censo POR REFERENCIA de claves de breaker en producción (medido, gotcha G6 — el que exige censar los hermanos):**

```
grep -rn '"ado_sync"\|"jira_sync"\|"ado_identity"\|"gitlab_sync"' backend --include=*.py | grep -v "/tests/"
```

| Key | Referencias en producción | Dónde |
|---|---|---|
| `"ado_sync"` | **7** (6 llamadas de breaker + 1 rótulo de log) | `api/tickets.py:322` (`record_failure`), `:6635` (`should_skip`), `:6636` (`get_state`), `:6711` (**rótulo de `stacky_logger`, NO breaker**), `app.py:236` (`should_skip`), `:245` (`record_success`), `:256` (`record_failure`), `project_manager.py:511` (`reset`), `services/completion_sync.py:92` (selector de key) |
| `"jira_sync"` | **5** | `app.py:124,130,139`, `project_manager.py:535`, `services/completion_sync.py:95` |
| `"ado_identity"` | **2** | `api/tickets.py:6538`, `project_manager.py:512` |
| **`"gitlab_sync"`** | **0** | — |

> **El insumo declaraba 5 / 2 / 1. Los números reales son 7 / 5 / 2.** La conclusión —**GitLab tiene CERO**— se mantiene intacta y es la única que importa para esta fase, pero los conteos del insumo estaban bajos y quedan corregidos acá.

**Archivos EXACTOS a editar (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services\integration_breaker.py` — **dos constantes nuevas y una función de clasificación**. Nada más.
2. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\tickets.py` — el helper de F6 alimenta el breaker.

**Nombres EXACTOS que se crean en `services/integration_breaker.py`** (junto a las 6 `REASON_*` existentes, `:26-31`):

```python
REASON_GITLAB_TOKEN_INVALID  = "gitlab_token_invalid"
REASON_GITLAB_PROJECT_MISSING = "gitlab_project_not_found"
```

```python
def classify_gitlab_error(kind: str, mensaje: str) -> tuple[str, str] | None:
    """Plan 295 F7 — traduce un `kind` de TrackerApiError a (reason, message), o
    None si ese kind NO debe abrir el breaker.

    SOLO abren el breaker los fallos TERMINALES DE CONFIGURACIÓN: los que no se
    arreglan reintentando. `rate_limited`, `server`, `network` y `tls` son
    TRANSITORIOS o de entorno: abrir por ellos dejaría a GitLab apagado hasta 6 h
    por un blip de red, que es peor que el problema. El hermano ADO usa el mismo
    criterio (classify_ado_error, :141-152, solo PAT y proyecto inexistente).
    """
    if kind == "auth":
        return REASON_GITLAB_TOKEN_INVALID, (
            "El token de GitLab no sirve: venció, fue revocado o está mal copiado. "
            "Renovalo en la configuración del proyecto."
        )
    if kind == "not_found":
        return REASON_GITLAB_PROJECT_MISSING, (
            "El proyecto de GitLab configurado no existe o el token no tiene acceso. "
            "Revisá el campo 'Proyecto' (grupo/proyecto) del proyecto."
        )
    return None
```

> **`classify_gitlab_error` NO recibe la excepción, recibe el `kind`.** Motivo dura: `services/integration_breaker.py` está en `services/` y **no puede importar de `api/`** ni conocer los tipos del adaptador. Recibir un `str` lo deja **puro** y testeable sin construir excepciones. El hermano `classify_ado_error` (`:141`) sí recibe `exc` y clasifica por mensaje/status — es más frágil y **no se replica**.

**Nombre EXACTO de la función de key:** **NO se crea una.** Se reusa `integration_key(integration, project)` (`:37`) a través de las funciones públicas, y el `project` que se le pasa es **`ctx.stacky_project_name`**, no `ado_breaker_project(...)`.

**Por qué `stacky_project_name` y no una función `gitlab_breaker_project`:** `ado_breaker_project` (`:40`) existe porque en ADO la unidad de fallo es la **organización + proyecto ADO** (un PAT vale para toda la org). En GitLab la unidad de fallo es el **proyecto de Stacky**, porque el token, la URL y el `ca_bundle` son **por proyecto** (verificado: `api/projects.py:35,187,467,652` los guarda por proyecto). Usar `ado_breaker_project` acá mezclaría el estado de degradación de dos proveedores distintos — **exactamente** lo que `backend/app.py:204-208` documenta como el bug que el 281 arregló.

**Cambio en `api/tickets.py`** — dentro de `_gitlab_sync_error_response`, en el lugar marcado en F6:

```python
    # Plan 295 F7 — alimentar el breaker "gitlab_sync". Key propia (nunca
    # ado_breaker_project: mezclaría dos proveedores, ver app.py:204-208). Solo los
    # kind TERMINALES abren: classify_gitlab_error devuelve None para el resto.
    if getattr(config.config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True) and _flag_i2():
        from services import integration_breaker as _brk
        clasificado = _brk.classify_gitlab_error(kind, str(exc))
        if clasificado is not None:
            reason, message = clasificado
            _brk.record_failure("gitlab_sync", nombre, reason, message)
```

**Y el éxito tiene que cerrarlo** — si no, el breaker abierto no vuelve a cerrarse nunca. En `sync_from_ado_v2`, **después** del `finally` y antes de armar la respuesta feliz (o sea, en el bloque que ya calcula `duration_ms`, `:6705`):

```python
    # Plan 295 F7 — el breaker se CIERRA al primer éxito. Sin esto queda abierto para
    # siempre y el operador tiene que reiniciar el backend. record_success es idempotente
    # (si la key no está, no hace nada) y NO loguea salvo que viniera abierta (:107-112).
    if getattr(config.config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True) and _flag_i2():
        from services import integration_breaker as _brk
        _ctx_ok = resolve_project_context(project_name=project_name)
        _brk.record_success("gitlab_sync", (_ctx_ok.stacky_project_name if _ctx_ok else project_name))
```

> **`_flag_i2()` es un helper local de una línea** que lee `getattr(config.config, "STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED", True)`. Se escribe **una vez** y se usa en los tres lugares de I2. **`config` en `tickets.py` es el MÓDULO** (`import config`, `:39`): hay que leer por **`config.config`**, nunca `config` pelado. Está documentado en `:315-317` y es un error real que ya pasó en este archivo.

**La consulta del breaker (`should_skip`) NO se agrega en F7. Va en F8**, porque consultarlo requiere el reordenamiento del ruteo, y mezclarlo acá haría que F7 no se pueda verificar sola.

**Casos borde:**

| Entrada | Comportamiento |
|---|---|
| `kind="rate_limited"` / `"server"` / `"network"` / `"tls"` | `classify_gitlab_error` devuelve `None` ⇒ **el breaker NO se abre**. La respuesta 502 de F6 sale igual. |
| `kind="marciano"` (desconocido) | `None` ⇒ no abre. **Fail-safe: un kind nuevo no apaga la integración.** |
| `project_name` no resoluble ⇒ `nombre == "<sin proyecto>"` | `record_failure("gitlab_sync", "<sin proyecto>", ...)` — key válida, no crashea. Es un caso degenerado que solo ocurre sin proyecto activo. |
| `STACKY_INTEGRATION_DEGRADATION_ENABLED` OFF | ni se abre ni se cierra: el breaker queda inerte, como para ADO y Jira. **Se reusa la misma flag maestra**, no se crea una. |
| Éxito con el breaker ya cerrado | `record_success` no hace nada y no loguea (`:107-112`). Cero costo. |

**Tests PRIMERO — archivo a crear:**

`N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_breaker_gitlab.py`

**Casos a cubrir (9):**

| # | Caso | Assert |
|---|---|---|
| 1 | `classify_gitlab_error("auth", ...)` devuelve `REASON_GITLAB_TOKEN_INVALID` | tupla con `[0] == "gitlab_token_invalid"` |
| 2 | `classify_gitlab_error("not_found", ...)` devuelve `REASON_GITLAB_PROJECT_MISSING` | `[0] == "gitlab_project_not_found"` |
| 3 | los **cuatro** kinds transitorios devuelven `None` | `all(classify_gitlab_error(k, "x") is None for k in ("rate_limited","server","network","tls"))` |
| 4 | un kind desconocido devuelve `None` | `classify_gitlab_error("marciano", "x") is None` |
| 5 | `TrackerApiError(401, kind="auth")` en `sync-v2` **abre** `"gitlab_sync"` | `get_state("gitlab_sync", "<proj>").open is True` |
| 6 | y **NO** toca `"ado_sync"` | `get_state("ado_sync", ...).open is False` ← **el assert que prueba el aislamiento** |
| 7 | `TrackerApiError(429, kind="rate_limited")` **no** abre nada | `get_state("gitlab_sync", ...).open is False` |
| 8 | un sync exitoso **cierra** el breaker abierto | abrir a mano con `record_failure`, sync OK, `.open is False` |
| 9 | las dos `REASON_*` nuevas no colisionan con las 6 existentes | conjunto de las 8 constantes `REASON_*` tiene `len == 8` |

> **El caso 6 es el corazón de la fase.** Sin él, el test pasaría con un breaker que abre la key equivocada — que es literalmente el bug que el 281 arregló en el arranque.

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_breaker_gitlab.py" -q
```

**Aislamiento obligatorio del fixture:** `STACKY_DATA_DIR` a `tmp_path` (el breaker escribe `integration_breaker.json` en `data_dir()`, `services/integration_breaker.py:55`). **Sin esto el test escribe en la carpeta real del operador y contamina su estado de degradación.**

**Criterio de aceptación BINARIO:** **9 passed**. Y el censo de K4:

```
grep -rn '"gitlab_sync"' "Stacky Agents/backend" --include=*.py | grep -v "/tests/" | wc -l
→ debe ser >= 3 (record_failure, record_success, y el should_skip que agrega F8)
```

Después de F7 solo son **2**; el tercero llega en F8. **El criterio de K4 se evalúa al cerrar F8, no acá.**

**Mitad de contraste (esperado en ROJO antes del código):**

```
FAILED test_plan295_breaker_gitlab.py::test_auth_clasifica
E  ImportError: cannot import name 'classify_gitlab_error' from 'services.integration_breaker'
FAILED test_plan295_breaker_gitlab.py::test_pat_vencido_abre_gitlab_sync
E  assert False is True
   (get_state("gitlab_sync", "Demo").open == False: la key NUNCA se escribe)
```

**El segundo output es el que vale.** Y hay una **mitad de contraste adicional obligatoria** que prueba el aislamiento: parchear a mano `record_failure("ado_sync", ...)` en vez de `"gitlab_sync"` y correr — el caso 6 tiene que **fallar** con `assert True is False`. Después se revierte. Sin esa comprobación, el caso 6 puede estar pasando porque el breaker no se abre en absoluto.

**Flag que la protege:** **`STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED`** (la misma de F6, **default ON**) **más** la flag maestra ya existente `STACKY_INTEGRATION_DEGRADATION_ENABLED` (**reusada, no creada**). **Cero flags nuevas en F7.**

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. El breaker es un JSON en disco y funciones puras. Fallback: si `data_dir()` no fuera escribible, `_save` de `integration_breaker` ya maneja su propio error (verificar `:62-77`) y el sync sigue: **el breaker degrada a no-breaker, nunca a crash**.

**Trabajo del operador: opt-in (default ON).**

---
### F8 — I2c: el breaker de ADO se consulta DESPUÉS de saber qué tracker es

**Objetivo:** mover el bloque `should_skip("ado_sync", ado_breaker_project(project_name))` de `backend/api/tickets.py:6631-6642` para que corra **debajo** de la resolución del contexto, y consultarlo **solo si el proyecto es ADO**. Y agregar la consulta simétrica de `"gitlab_sync"` para los proyectos GitLab.

**Valor:** hoy un proyecto **GitLab** puede recibir `{"ok": false, "error": "ado_degraded"}` porque el breaker de **Azure DevOps** de otro proyecto está abierto. El operador lee "Azure DevOps degradado" en un proyecto que no usa Azure DevOps. **Es el mismo bug que el plan 281 F4 arregló en el arranque y dejó vivo acá.**

**La evidencia de que es deuda declarada, no un descubrimiento (gotcha G6):** `backend/app.py:204-209` dice **textual**: "*Con este return un proyecto GitLab deja de tocar el breaker "ado_sync" en el arranque: la key `ado_breaker_project(active)` mezclaba el estado de degradación de dos proveedores distintos.*" El 281 arregló `_startup_sync` y **puso `sync-v2` en su propia lista de diferidos**. Esta fase paga ese diferido. **Es el tercer estado del gotcha G6: arreglado en un camino y no en el hermano.**

**Censo de los hermanos, POR REFERENCIA, hecho para esta fase** (para no declarar el patrón muerto sin haberlo medido):

| Consumidor de `should_skip("ado_sync", ...)` | Estado |
|---|---|
| `backend/app.py:236` (`_startup_sync`) | **YA ARREGLADO** por el 281 F4: el `return` de `:209` corta antes para proyectos no-ADO |
| `backend/api/tickets.py:6635` (`sync-v2`) | **ROTO — es lo que arregla esta fase** |
| `backend/api/tickets.py:322` (`_ado_sync_error_response`) | **CORRECTO**: solo se llega ahí desde `except AdoApiError`, o sea ya se sabe que es ADO |
| `backend/api/tickets.py:6538` (`"ado_identity"`) | **FUERA DE ALCANCE**: es la identidad del usuario ADO, un camino ADO-only por definición (`/ado-user`) |
| `backend/project_manager.py:511-512` (`reset`) | **CORRECTO**: resetear una key que no está es no-op |
| `backend/services/completion_sync.py:92-95` | **CORRECTO**: es un selector que devuelve `("ado_sync", ...)` o `("jira_sync", ...)` **según el tracker** — ya rutea |

> **Con este censo, `sync-v2` es el ÚLTIMO hermano roto del patrón.** Después de F8 el patrón queda muerto de verdad, y eso se puede afirmar porque se midió.

**Archivos EXACTOS a editar (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\tickets.py` — se mueve un bloque y se agrega su gemelo.

**El estado de hoy, verificado línea por línea:**

```python
# :6631-6642  (ANTES de saber qué tracker es)
    if getattr(config.config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True):
        from services import integration_breaker as _brk
        _bkey_v2 = _brk.ado_breaker_project(project_name)
        if _brk.should_skip("ado_sync", _bkey_v2):
            st = _brk.get_state("ado_sync", _bkey_v2)
            return jsonify({...  "error": "ado_degraded" ...}), 200

# :6645  (ACÁ recién se sabe)
    ctx = resolve_project_context(project_name=project_name)
```

**El estado después:** el bloque del breaker se **borra de `:6631-6642`** y se **reinserta después de `:6645`**, con el ruteo por tracker:

```python
    ctx = resolve_project_context(project_name=project_name)

    # ── Plan 295 F8 — el breaker se consulta DESPUÉS de saber qué tracker es ──
    # ANTES este bloque vivía ARRIBA de resolve_project_context, así que un proyecto
    # GitLab podía recibir {"error":"ado_degraded"} por el breaker de Azure DevOps de
    # OTRO proyecto. Es el mismo defecto que el plan 281 F4 arregló en el arranque
    # (app.py:204-209 lo dice textual) y dejó vivo acá, en su propia lista de diferidos.
    #
    # El camino ADO queda BYTE-IDÉNTICO: mismo `if` de la flag maestra, misma key
    # (ado_breaker_project), mismo cuerpo de respuesta, mismo 200. Lo único que cambia
    # es CUÁNDO se evalúa y que ahora hay un `elif` para GitLab.
    if getattr(config.config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True):
        from services import integration_breaker as _brk
        _tipo_v2 = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()
        if _tipo_v2 == "azure_devops":
            _bkey_v2 = _brk.ado_breaker_project(project_name)  # [C3] misma key que _startup_sync/ado-user
            if _brk.should_skip("ado_sync", _bkey_v2):
                st = _brk.get_state("ado_sync", _bkey_v2)
                return jsonify({
                    "ok": False, "error": "ado_degraded", "degraded": True,
                    "reason": st.reason, "message": st.message,
                    "retry_after": st.retry_after,
                    "seconds_until_retry": st.seconds_until_retry,
                }), 200  # 200 "degradado", no red
        elif _tipo_v2 == "gitlab" and _flag_i2():
            # Plan 295 F8 — el gemelo. Misma forma, error DISTINTO: el frontend puede
            # distinguir qué integración está degradada sin adivinar por el mensaje.
            _bkey_gl = (getattr(ctx, "stacky_project_name", None) or project_name)
            if _brk.should_skip("gitlab_sync", _bkey_gl):
                st = _brk.get_state("gitlab_sync", _bkey_gl)
                return jsonify({
                    "ok": False, "error": "gitlab_degraded", "degraded": True,
                    "reason": st.reason, "message": st.message,
                    "retry_after": st.retry_after,
                    "seconds_until_retry": st.seconds_until_retry,
                }), 200
```

**El `_tipo_v2` se lee de `ctx.tracker_type` — verificado que el campo existe** (`services/project_context.py:271`, `ProjectContext` es un `@dataclass(frozen=True)` con `tracker_type: str`). Y el idioma `(getattr(x, "tracker_type", None) or "azure_devops").strip().lower()` es **el que ya usa este mismo archivo** en `_sync_via_provider_or_ado:1184`. **Se copia ese idioma, no se inventa otro.**

**Casos borde, todos declarados:**

| Entrada | Comportamiento |
|---|---|
| `ctx is None` (proyecto no resoluble) | `getattr(None, "tracker_type", None) or "azure_devops"` ⇒ `"azure_devops"` ⇒ **camino ADO, idéntico a hoy**. No crashea. |
| tracker `jira` o `mantis` | **ninguna** rama del `if/elif` aplica ⇒ el sync sigue sin consultar breaker, que es lo que pasa hoy para esos trackers en este endpoint. **Sin cambio de comportamiento.** |
| flag `STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED` OFF | el `elif` no entra (`_flag_i2()` es `False`) ⇒ GitLab no consulta breaker ⇒ comportamiento de hoy. **Y el camino ADO sigue funcionando** porque su `if` no depende de esa flag. |
| flag `STACKY_INTEGRATION_DEGRADATION_ENABLED` OFF | ni ADO ni GitLab consultan. Idéntico a hoy. |
| proyecto ADO con breaker abierto | `{"error": "ado_degraded"}`, 200, **byte-idéntico** al de hoy — solo se evalúa unas líneas más abajo. |

**El riesgo de esta fase y su mitigación explícita.** Mover un bloque en el camino caliente de sync es el cambio de mayor riesgo del plan. La mitigación es triple:

1. **El camino ADO es byte-idéntico**: mismo `if` de flag maestra, misma key, mismo dict de respuesta, mismo `200`. Se puede verificar con un `diff` conceptual del cuerpo del `if`.
2. **Reordenamiento, no reescritura**: `resolve_project_context` **no tiene efectos secundarios de red ni de BD** (es resolución de config en memoria con memo por `mtime`), así que llamarla antes del breaker no agrega costo ni riesgo. Lo único que se pierde es un microahorro: antes, con el breaker abierto se salteaba `resolve_project_context`. Ahora se resuelve siempre. **Costo medido conceptualmente: una lectura de config memoizada. Aceptable.**
3. **Flag de reversión de una perilla**: `STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED` OFF deja GitLab sin consultar el breaker; el reordenamiento en sí **no se revierte por flag** (mover código no es una rama), y eso es correcto: el reordenamiento es la **corrección del bug**, no una feature.

**Tests PRIMERO — se agregan al archivo de F7** (`test_plan295_breaker_gitlab.py`), porque comparten el fixture de aislamiento y el mismo dominio. **Casos nuevos (5):**

| # | Caso | Assert |
|---|---|---|
| 11 | proyecto **GitLab** + breaker `"ado_sync"` **abierto** ⇒ el sync **NO** devuelve `ado_degraded` | `data.get("error") != "ado_degraded"` ← **el bug de hoy** |
| 12 | proyecto **ADO** + breaker `"ado_sync"` abierto ⇒ **sí** devuelve `ado_degraded` con 200 (**no-regresión**) | `resp.status_code == 200` y `data["error"] == "ado_degraded"` |
| 13 | proyecto **GitLab** + breaker `"gitlab_sync"` abierto ⇒ `gitlab_degraded` con 200 | `data["error"] == "gitlab_degraded"` |
| 14 | proyecto **GitLab** + breaker `"gitlab_sync"` abierto ⇒ el mensaje viene del breaker, no hardcodeado | `data["message"] == st.message` |
| 15 | con `STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED` **OFF**, el caso 13 **no** dispara | `data.get("error") != "gitlab_degraded"` |

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_breaker_gitlab.py" -q
```

**No-regresión obligatoria** (el archivo que cubre estos endpoints hoy):

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_p7_sync_endpoints.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan276_gitlab_sync.py" -q
```

> **`test_plan276_gitlab_sync.py` está en la lista de archivos MODIFICADOS por la sesión paralela** (`git status` al empezar este plan). Su baseline se mide en F0 y el criterio es **delta cero respecto de ese baseline**, no un número absoluto. Si viene rojo de fábrica, sigue rojo y **no se toca**.

**Criterio de aceptación BINARIO:** **14 passed** en `test_plan295_breaker_gitlab.py` (9 de F7 + 5 de F8), delta cero en los dos archivos de no-regresión, y K4 cumplido:

```
grep -rn '"gitlab_sync"' "Stacky Agents/backend" --include=*.py | grep -v "/tests/" | wc -l
→ debe ser >= 3
```

**Mitad de contraste (esperado en ROJO antes del código):**

```
FAILED test_plan295_breaker_gitlab.py::test_proyecto_gitlab_no_recibe_ado_degraded
E  AssertionError: assert 'ado_degraded' != 'ado_degraded'
   (un proyecto GitLab recibió el error de degradación de Azure DevOps)
FAILED test_plan295_breaker_gitlab.py::test_proyecto_gitlab_con_su_breaker_abierto
E  KeyError: 'error'  /  assert None == 'gitlab_degraded'
```

**El primero es el bug del insumo reproducido en un test.** Y el caso 12 (no-regresión ADO) **pasa antes y después**: es la prueba de que el camino ADO no se movió.

**Flag que la protege:** **`STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED`** (la misma de F6 y F7, **default ON**). El reordenamiento del bloque ADO **no va detrás de flag** porque es la corrección del defecto, y una flag para "seguir consultando el breeaker equivocado" sería una perilla para conservar un bug.

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. Fallback: con la flag OFF, GitLab sigue sin breaker (comportamiento de hoy) y ADO sigue igual.

**Trabajo del operador: opt-in (default ON).**

---

### F9 — corrección de D5 (= QW4): los receptores de webhook dejan de machear un ticket ajeno

**Objetivo:** que los **dos** receptores de webhook de `backend/api/phase6.py` filtren por `stacky_project_name` **y** tracker, y que el auto-creado deje de inventar un ticket ADO sintético dentro de un proyecto GitLab.

**Valor:** hoy, con dos proyectos GitLab que tengan cada uno un issue **#42**, el webhook de CI machea el ticket del proyecto **equivocado** y **corre el DebugAgent sobre él**. Es el defecto de mayor consecuencia del insumo: no es un mensaje confuso, es un agente trabajando sobre el ticket de otro proyecto. **Y es el prerequisito duro del PLAN DEL WEBHOOK**: no se agrega un tercer receptor de webhook mientras los dos existentes machean por una columna que no es única.

**La causa exacta, medida (gotcha G3):**

- `backend/models.py:42` — `ado_id: Mapped[int] = mapped_column(Integer, nullable=False)`. **`nullable=False` pero NO `unique=True`.**
- `backend/models.py:77-83` — el único índice único es `ux_tickets_stacky_tracker_external` sobre la **terna** `("stacky_project_name", "tracker_type", "external_id")`.
- `backend/services/gitlab_sync.py:12-16` — el docstring lo dice textual: "*`ado_id` acá lleva el **iid** (el número visible DENTRO del proyecto, que se repite entre proyectos distintos de GitLab) y NO está en el índice*".
- `backend/api/phase6.py:167` y `:221` — `session.query(Ticket).filter_by(ado_id=int(ado_id)).first()`, **sin `stacky_project_name`, sin `tracker_type`**.
- `backend/api/phase6.py:170-175` — el auto-creado: `project=p.get("project", "RSPacifico")` **hardcodeado**, sin `stacky_project_name`, sin `tracker_type` ⇒ cae en el default `"azure_devops"` de `models.py:49` ⇒ **un ticket ADO sintético dentro de un proyecto GitLab**, que después el 286 tiene que adivinar (`tracker_efectivo_de_ticket`, `services/project_context.py:206-218`, cuya precedencia dice que el default es indistinguible de "nadie la seteó").
- `backend/api/phase6.py:209` — el docstring de `/pr/review-webhook` dice "*Triggered by ADO Repos / GitHub*": **ni nombra a GitLab**.

**Archivos EXACTOS a editar (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api\phase6.py`

> **`backend/services/project_context.py` NO SE EDITA.** Está en la lista de archivos que la sesión paralela está tocando **ahora**. F9 **importa** de él (`resolve_project_context`, `tracker_efectivo_de_ticket`) y no le cambia una línea. Verificado que las dos funciones existen: `:373` y `:206`.

**Nombre EXACTO del helper que se crea en `api/phase6.py`:** `_ticket_del_webhook(session, ado_id: int, payload: dict) -> tuple[object | None, object | None]`, que devuelve `(ticket, ctx)`.

**Pseudocódigo:**

```python
def _ticket_del_webhook(session, ado_id: int, payload: dict):
    """Plan 295 F9 — resuelve el ticket de un webhook entrante SIN ambigüedad.

    POR QUÉ EXISTE: `filter_by(ado_id=...)` pelado es un bug latente GARANTIZADO en
    GitLab. `ado_id` no es único (models.py:42; el único es la terna
    `(stacky_project_name, tracker_type, external_id)`, models.py:77-83) y en GitLab
    lleva el IID, que se repite entre proyectos (gitlab_sync.py:12-16). Dos proyectos
    GitLab con el issue #42 y el webhook macheaba el del proyecto equivocado -- y el
    DebugAgent corría sobre él.

    Stacky es MONO-OPERADOR: si el payload no nombra el proyecto, el proyecto activo
    es la respuesta correcta y honesta. NO se adivina por `ado_id`.

    Devuelve (ticket|None, ctx|None). NO crea nada: crear es decisión del llamador.
    """
    from services.project_context import resolve_project_context

    # 1. ¿El payload nombra el proyecto? Se aceptan las DOS claves: la nueva,
    #    explícita, y la vieja `project`, que en la práctica trae el tracker_project.
    nombrado = (payload.get("stacky_project") or payload.get("project") or "").strip() or None
    ctx = resolve_project_context(project_name=nombrado)   # sin nombre => proyecto ACTIVO

    if ctx is None:
        return None, None

    # 2. Filtro por PROYECTO, con la misma tolerancia que _ticket_project_filter
    #    de api/tickets.py:362-371: las filas viejas tienen stacky_project_name NULL
    #    y solo `project` (el tracker_project). Ignorar eso rompería los tickets
    #    ADO históricos, que es exactamente lo que este plan NO puede hacer.
    from sqlalchemy import and_, or_
    from models import Ticket

    filtro_proyecto = or_(
        Ticket.stacky_project_name == ctx.stacky_project_name,
        and_(Ticket.stacky_project_name.is_(None), Ticket.project == ctx.tracker_project),
    )
    fila = (
        session.query(Ticket)
        .filter(Ticket.ado_id == ado_id)
        .filter(filtro_proyecto)
        .first()
    )
    return fila, ctx
```

**Cambio 1 — `ci_webhook` (`api/phase6.py:166-175`).** Hoy:

```python
    with session_scope() as session:
        t = session.query(Ticket).filter_by(ado_id=int(ado_id)).first()
        if t is None:
            # Auto-crear ticket placeholder si no existe
            t = Ticket(
                ado_id=int(ado_id), project=p.get("project", "RSPacifico"),
                title=f"CI failure ADO-{ado_id}", ado_state="To Do",
            )
            session.add(t); session.flush()
        ticket_id = t.id
```

Pasa a:

```python
    with session_scope() as session:
        t, ctx = _ticket_del_webhook(session, int(ado_id), p)
        if ctx is None:
            # Sin proyecto resoluble no se puede saber A QUÉ proyecto pertenece este
            # ticket. Crear a ciegas era peor: metía un ticket con project="RSPacifico"
            # HARDCODEADO y sin tracker_type (=> default azure_devops, models.py:49),
            # o sea un ticket ADO sintético dentro de un proyecto GitLab.
            abort(409, "no hay proyecto activo ni el payload nombra uno: no se puede "
                       "resolver a qué proyecto pertenece este ticket")
        if t is None:
            if not _plan295_autocrear_habilitado():
                abort(404, f"no existe el ticket {ado_id} en el proyecto "
                           f"'{ctx.stacky_project_name}'")
            # Placeholder con la IDENTIDAD COMPLETA. Los tres campos que faltaban
            # (stacky_project_name, tracker_type, external_id) son los del índice
            # único de models.py:77-83: sin ellos el upsert del sync crea un DUPLICADO.
            t = Ticket(
                ado_id=int(ado_id),
                external_id=int(ado_id),
                project=ctx.tracker_project,
                stacky_project_name=ctx.stacky_project_name,
                tracker_type=ctx.tracker_type,
                title=f"Fallo de CI — ítem {ado_id}",
                ado_state="To Do",
            )
            session.add(t); session.flush()
        ticket_id = t.id
```

**Cambio 2 — `pr_review_webhook` (`api/phase6.py:220-223`).** Hoy:

```python
    with session_scope() as session:
        t = session.query(Ticket).filter_by(ado_id=int(ado_id)).first()
        if t is None:
            abort(404, f"ticket ADO-{ado_id} not found")
        ticket_id = t.id
```

Pasa a:

```python
    with session_scope() as session:
        t, ctx = _ticket_del_webhook(session, int(ado_id), p)
        if ctx is None:
            abort(409, "no hay proyecto activo ni el payload nombra uno")
        if t is None:
            # NO auto-crea: este endpoint nunca lo hizo y no es el momento de empezar.
            abort(404, f"no existe el ticket {ado_id} en el proyecto "
                       f"'{ctx.stacky_project_name}'")
        ticket_id = t.id
```

**Cambio 3 — el docstring de `:209-211`.** Hoy dice "*Triggered by ADO Repos / GitHub when reviewer mentions @stacky-bot*". Pasa a nombrar los tres:

```python
    """Recibe el aviso de una revisión de PR/MR y dispara el agente de revisión.

    Lo disparan Azure DevOps Repos, GitHub o GitLab (Merge Request) cuando un
    revisor menciona a @stacky-bot. Payload: { pr_id, ticket_ado_id, diff,
    description, stacky_project? }.

    `ticket_ado_id` conserva su nombre por compatibilidad con los webhooks ya
    configurados en los servidores del operador: en GitLab lleva el IID del issue.
    Plan 295 F9 — el match es por (ado_id + proyecto), NUNCA por ado_id solo: el iid
    se repite entre proyectos de GitLab.
    """
```

**Nombre EXACTO del helper de flag:** `_plan295_autocrear_habilitado()` — lee `getattr(config.config, "STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED", True)`.

**Casos borde, todos declarados:**

| Entrada | Comportamiento |
|---|---|
| payload con `stacky_project: "Demo"` | se resuelve ese proyecto; el ticket se busca **solo ahí** |
| payload con `project: "Strategist_Pacifico"` (tracker_project, formato viejo) | `resolve_project_context` acepta un tracker_project como `project_name` (su docstring `:381-386` lo dice: "*project_name explícito (Stacky project o tracker_project)*") ⇒ **funciona sin cambiar los webhooks ya configurados** |
| payload **sin** ninguna de las dos claves | proyecto **activo**. Correcto en mono-operador. |
| sin proyecto activo y sin claves | **`409`**, con mensaje accionable. **Antes creaba un ticket `RSPacifico` inventado.** |
| dos proyectos GitLab con issue #42, payload nombra el proyecto B | machea el de **B**. Antes macheaba el primero que la BD devolviera (**orden no determinista**). |
| ticket **inexistente** en `/ci/failure-webhook` con la flag de autocreado **ON** | crea el placeholder con identidad completa (los 3 campos del índice único) |
| ticket inexistente con la flag **OFF** | **`404`** accionable en vez de crear |
| fila vieja con `stacky_project_name = NULL` | el `or_` la machea por `project == ctx.tracker_project`. **Los tickets ADO históricos siguen funcionando.** |
| `ado_id` no numérico | `int(ado_id)` levanta `ValueError` ⇒ hoy sale como 500. **Se agrega un `abort(400, "ticket_ado_id debe ser numérico")`** en los dos endpoints, junto al `if not ado_id` que ya existe (`:163-164`, `:217-218`). |

**Tests PRIMERO — archivo a crear:**

`N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_webhooks_por_proyecto.py`

**Casos a cubrir (11):**

| # | Caso | Assert |
|---|---|---|
| 1 | **el bug**: dos proyectos GitLab con `ado_id=42`; webhook nombra el B ⇒ machea el ticket de **B** | `ticket_usado.stacky_project_name == "ProyB"` |
| 2 | el mismo escenario **sin** nombrar el proyecto ⇒ machea el del proyecto **activo** | `ticket_usado.stacky_project_name == "<activo>"` |
| 3 | ticket inexistente + autocreado ON ⇒ la fila nueva tiene `stacky_project_name` no nulo | `fila.stacky_project_name == ctx.stacky_project_name` |
| 4 | ídem ⇒ la fila nueva tiene `tracker_type` del contexto, **no** el default | `fila.tracker_type == "gitlab"` |
| 5 | ídem ⇒ la fila nueva tiene `external_id` poblado (la 3ª pata del índice único) | `fila.external_id == 42` |
| 6 | ídem ⇒ **`project` NO es "RSPacifico"** salvo que el contexto lo diga | `fila.project == ctx.tracker_project` |
| 7 | sin proyecto resoluble ⇒ **409**, y **cero filas creadas** | `resp.status_code == 409` y `session.query(Ticket).count() == 0` |
| 8 | autocreado OFF + ticket inexistente ⇒ **404**, cero filas | `resp.status_code == 404` y count sin cambio |
| 9 | `/pr/review-webhook` con ticket de otro proyecto ⇒ **404**, y **el agente NO se lanza** | monkeypatch de `agent_runner.run_agent` que cuenta llamadas: `llamadas == 0` |
| 10 | `ticket_ado_id` no numérico ⇒ **400** en los dos endpoints | `resp.status_code == 400` |
| 11 | **no-regresión ADO**: proyecto ADO con `ado_id=99` y `stacky_project_name=NULL`, payload con `project` = tracker_project ⇒ **machea** | `ticket_usado.ado_id == 99` |

> **El caso 9 es el que mide la consecuencia real:** que el DebugAgent **no corra** sobre el ticket equivocado. Contar llamadas a `agent_runner.run_agent` es un **assert de presencia del valor correcto** (`== 0`), no de ausencia.
>
> **El caso 11 es la red de seguridad de los datos históricos.** Sin él, F9 podría romper todos los webhooks ADO que ya funcionan.

**Aislamiento del fixture:** `DATABASE_URL` a `tmp_path` **y** `STACKY_DATA_DIR` a `tmp_path` **y** replicar `active_project.json` + la carpeta `projects/` en el tmp, porque `resolve_project_context` lee del disco. **Un pytest suelto sin este aislamiento escribe en la BD real del operador** — y este archivo **crea filas**, así que el riesgo es concreto.

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_webhooks_por_proyecto.py" -q
```

**Criterio de aceptación BINARIO:** **11 passed**, y K6:

```
grep -c "filter_by(ado_id=int(ado_id))" "Stacky Agents/backend/api/phase6.py"
→ debe ser 0
```

**Mitad de contraste (esperado en ROJO antes del código):**

```
FAILED test_plan295_webhooks_por_proyecto.py::test_machea_el_proyecto_nombrado
E  AssertionError: assert 'ProyA' == 'ProyB'
   (el webhook macheó el ticket del proyecto EQUIVOCADO)
FAILED ...::test_el_autocreado_pone_el_tracker_type_del_contexto
E  AssertionError: assert 'azure_devops' == 'gitlab'
FAILED ...::test_el_autocreado_no_inventa_rspacifico
E  AssertionError: assert 'RSPacifico' == 'grupo/proy-b'
FAILED ...::test_sin_proyecto_resoluble_no_crea_nada
E  assert 1 == 0   (creó un ticket fantasma)
```

**Los cuatro outputs son el defecto D5 reproducido.** El caso 11 (no-regresión ADO) pasa antes y después.

**Registro en los DOS ratchets:** `tests/test_plan295_webhooks_por_proyecto.py` en `.sh` y `.ps1`.

**Flag que la protege:** **`STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED`** — **NUEVA, default ON**.

- **Categoría de excepción: NINGUNA.** No quema tokens en reposo. **No escribe en un sistema real del operador**: escribe en la **BD local de Stacky**, que es el propio almacén de la app, y solo cuando un webhook externo se lo pide explícitamente. No destruye datos ni le saca una decisión.
- **Nace ON porque ON es el comportamiento de hoy** (`api/phase6.py:169-174` ya auto-crea). Nacer OFF **cambiaría** el comportamiento actual, y "no cambiar el comportamiento actual" **no es un motivo válido** para apagar una flag — pero acá el razonamiento es el inverso: ON **es** el comportamiento actual, y la flag existe para darle al operador la opción de que su webhook de CI **no** cree placeholders si no los quiere. Esa opción es nueva y es valor.
- **El corazón del arreglo NO está detrás de flag.** El filtro por proyecto y la identidad completa del placeholder son la **corrección del bug** y van siempre. La flag solo gobierna **si se crea o se devuelve 404**.
- **Los TRES lugares del default ON:** `backend/config.py`, la `FlagSpec` con `default=True`, y `_CURATED_DEFAULTS_ON` (booleana ON ⇒ **sí** va).

**Impacto por runtime:**
- **Codex CLI / Claude Code CLI / GitHub Copilot Pro** — **idéntico en la resolución del ticket**. El webhook resuelve el ticket **antes** de elegir runtime.
- **Nota de paridad que hay que respetar:** `api/phase6.py:192-193` llama `resolve_run_selection(runtime="github_copilot", project_name=None)` — **hardcodea el runtime y pasa `project_name=None`**. Esta fase **no lo cambia** (está fuera de su objetivo y tocarlo sin un test de los tres runtimes sería peor), pero **se anota como hallazgo** en `## DIFERIDOS` §D-4, porque significa que el webhook de CI corre el DebugAgent **siempre** con Copilot, ignorando la selección del proyecto.
- **Fallback:** si `resolve_project_context` devuelve `None`, el endpoint responde `409` accionable en vez de crear basura. **Degrada informando, nunca en silencio.**

**Trabajo del operador: opt-in (default ON).**

---
### F10 — I5 (= QW5): el intervalo de sync pasa a ser del operador

**Objetivo:** registrar `STACKY_TICKET_SYNC_INTERVAL_MS` como `FlagSpec` numérica, hacer que el endpoint la lea de `config.config` en vez de `os.environ`, y que el frontend use el valor recibido en vez de su constante.

**Valor:** el plan 292 **midió** que subir el intervalo de 45 s a 180 s baja el tráfico contra el GitLab del operador un **75 %**. Hoy aplicar esa recomendación **exige editar `frontend/src/hooks/useTicketSync.ts:40` y recompilar el frontend**. Esta fase la convierte en una perilla del panel de flags. Es la fase que viola menos código y desbloquea más valor.

**La causa exacta, medida (gotcha G5 — perilla fantasma):**

- `backend/api/tickets.py:6778` — `"ticket_sync_interval_ms": int(os.environ.get("STACKY_TICKET_SYNC_INTERVAL_MS", 45000))`. Se lee de `os.environ`, **nunca de `config.config`**, así que el panel de flags no puede moverla.
- La clave tiene **1 sola referencia en el backend fuera de tests** (esa). **No está en `FLAG_REGISTRY`** (verificado con `grep` en todo el repo: aparece en `config.py`? **no**; en `harness_flags.py`? **no**).
- `frontend/src/api/endpoints.ts:182` declara `ticket_sync_interval_ms: number` en `FrontendConfig`, así que **el valor SE PUBLICA**.
- El **único** consumidor de `Tickets.frontendConfig()` es `frontend/src/components/EpicFromBriefModal.tsx:163`, y lee **otra clave** (`issue_from_brief_enabled`). **La perilla se publica y nadie la lee: es una perilla fantasma.**

**CORRECCIÓN AL INSUMO, medida.** El insumo afirma que "*`useTicketSync.ts:40` hardcodea `DEFAULT_INTERVAL_MS = 45_000` **sin que ningún componente pase `intervalMs`**". **Eso es falso.** `frontend/src/pages/TicketBoard.tsx:12` importa `DEFAULT_INTERVAL_MS as TICKET_SYNC_INTERVAL_MS` y lo pasa en **dos** lugares:

- `:1110` — `useTicketSync({ intervalMs: TICKET_SYNC_INTERVAL_MS, syncOnMount: true })`
- `:1353` — `<SyncStatusBar ... intervalMs={TICKET_SYNC_INTERVAL_MS} />`

La **sustancia** del defecto se mantiene (el valor sigue siendo una constante compilada), pero la **consecuencia de diseño es distinta y hay que respetarla**: son **dos** consumidores del mismo valor, y `SyncStatusBar` lo usa para derivar el umbral de "stale". **Si F10 alimenta solo el hook, la barra de estado calcula "hace mucho que no sincroniza" contra 45 s mientras el hook sincroniza cada 180 s: el operador vería la barra en rojo permanente.** Los dos tienen que salir de la misma fuente.

#### F10.1 — Los NUEVE guardianes de una flag numérica (medidos con la flag del 292 como plantilla)

Se trazó `STACKY_GITLAB_SYNC_FULL_CADA_N` (la numérica más reciente, del plan 292) por **todo el repo** para saber exactamente dónde hay que tocar:

| # | Guardián | Archivo (ruta completa) | Ancla verificada | Obligatorio para numérica |
|---|---|---|---|---|
| 1 | El valor efectivo | `...\backend\config.py` | `:2743-2745` (la del 292) | **SÍ** |
| 2 | La `FlagSpec` | `...\backend\services\harness_flags.py` | `:7386-7395` (la del 292) | **SÍ** |
| 3 | `_CATEGORY_KEYS` | `...\backend\services\harness_flags.py` | `:617` (la del 292) — **la tupla se llama `paridad_proveedores`, NO `global`** ([v2, C2]) | **SÍ** — si falta, `test_every_registry_flag_is_categorized` rompe CI a propósito (`:622-623` lo dice) |
| 4 | `PLAIN_HELP` | `...\backend\services\harness_flags_help.py` | `:2511-2517` (la del 292) | **SÍ** — **NO se deriva de `description`**: es un objeto `PlainHelp(what=, on_effect=, off_effect=, example=)` escrito a mano |
| 5 | `_FROZEN_BOUNDS` | `...\backend\tests\test_harness_flags_bounds.py` | `:227` (la del 292: `(1, 1000)`) | **SÍ para numéricas** — `test_bounds_map_is_frozen` (`:232`) compara **igualdad exacta** del dict |
| 6 | `_CURATED_DEFAULTS_ON` | `...\backend\tests\test_harness_flags.py` | `:1129` dice **textual** que la numérica del 292 **NO figura ahí a propósito** | **NO — PROHIBIDO** |
| 7 | `_REQUIRES_MAP_FROZEN` | `...\backend\services\harness_flags.py` | solo si la `FlagSpec` declara `requires=` | **NO** (esta flag no declara `requires`) |
| 8 | El panel de UI | `...\frontend\src\components\HarnessFlagsPanel.tsx` | `:115-128` ya renderiza `type === "int"` con `<input type="number">` | **AUTOMÁTICO** — cero código |
| 9 | Los DOS ratchets de test files | `...\backend\scripts\run_harness_tests.sh` y `.ps1` | brecha **exactamente 64** (B4) | **SÍ para los archivos de test nuevos** |

> **`deployment\harness_defaults.env` NO es un guardián por flag.** Verificado: `STACKY_GITLAB_SYNC_FULL_CADA_N` **no aparece** en ese archivo, que tiene 449 claves y es un **snapshot generado** por `deployment\export_harness_defaults.py`. **No hay que agregarla a mano.** (El insumo la listaba entre los ocho; queda corregido.)

#### F10.2 — Contenido exacto de cada guardián

**Guardián 1 — `backend/config.py`**, junto a las otras de GitLab/sync (después de `:2745`):

```python
    # Plan 295 F10 — cada cuántos milisegundos el frontend pide un sync automático.
    # El plan 292 MIDIÓ que subirlo de 45 s a 180 s baja el tráfico contra el GitLab
    # del operador un 75 %. Hasta ahora aplicar esa recomendación exigía editar
    # frontend/src/hooks/useTicketSync.ts:40 y recompilar: era una perilla FANTASMA
    # (se publicaba en /api/tickets/config/frontend y nadie la leía).
    # El default se conserva en 45000: este plan da el control, no cambia la conducta.
    STACKY_TICKET_SYNC_INTERVAL_MS: int = int(
        os.getenv("STACKY_TICKET_SYNC_INTERVAL_MS", "45000")
    )
```

**Guardián 2 — la `FlagSpec` en `backend/services/harness_flags.py`**, al final de `FLAG_REGISTRY`:

```python
    FlagSpec(
        key="STACKY_TICKET_SYNC_INTERVAL_MS",
        # SIN default= A PROPOSITO (regla dura, misma razón que la numérica del plan
        # 292 en :7386): `default_is_known(spec)` es literalmente
        # `spec.default is not None`, y declararlo metería esta key en el conjunto que
        # test_default_known_only_for_curated exige que sea EXACTAMENTE
        # _CURATED_DEFAULTS_ON -- que es SÓLO para booleanas ON. El valor 45000 vive
        # SOLO en config.py.
        type="int",
        min_value=5000,
        max_value=3600000,
        label="Cada cuántos milisegundos se sincronizan los tickets solo",
        description=(
            "Plan 295 — Cada cuánto el tablero de tickets le pide a Stacky que "
            "traiga novedades del tracker sin que vos aprietes nada. Con 45000 "
            "(45 segundos) es el valor histórico. El plan 292 midió que con 180000 "
            "(3 minutos) el tráfico contra el servidor de la empresa baja un 75 % "
            "y las novedades siguen llegando solas."
        ),
        group="global",
        env_only=False,
    ),
```

> **Los límites (`5000`, `3600000`) son deliberados y hay que justificarlos.** El mínimo de **5 s** está por encima del rate-limit del propio endpoint (`_SYNC_MIN_INTERVAL_SEC = 15`, `backend/api/tickets.py:6605`): poner menos de 15 s haría que el frontend reciba `429` sistemáticamente, así que el mínimo evita que el operador se dispare en el pie — pero **no** se pone en 15000 porque el rate-limit es configurable por su propia env y el mínimo de la flag no debe atarse a otro valor movible. El máximo de **1 hora** evita que el operador apague de hecho el auto-sync creyendo que lo está ralentizando; para apagarlo hay otras vías.
>
> **`env_only=False` es obligatorio.** Con `env_only=True` la flag queda **inerte** si no tiene entrada en `config.py` — y aunque acá sí la tiene, `env_only=False` es lo que la hace escribible desde el panel, que es el objetivo de la fase.

**Guardián 3 — `_CATEGORY_KEYS`**, en la misma tupla donde están las del 292 (`:617`). **[v2, C2] Esa tupla se llama `paridad_proveedores`, NO `"global"`.**

```python
        # Plan 295 — el intervalo de sync pasa a ser del operador
        "STACKY_TICKET_SYNC_INTERVAL_MS",
```

> 🛑 **[v2, C2] El v1 decía "en la misma tupla `"global"`" y eso es FALSO: `_CATEGORY_KEYS` NO TIENE una clave `"global"`.** Medido abriendo `backend/services/harness_flags.py`: el dict tiene **20** categorías — `runtimes_cli`, `contexto_memoria`, `calidad_verificacion`, `integridad_grounding`, `epicas_ado`, `migrador_ado_gitlab`, `gitlab_deep_links`, `devops`, `flujo_funcional`, `routing_costo`, `fiabilidad_ciclo_vida`, `observabilidad_notif`, `aprendizaje`, `preflight_intencion`, `base_datos`, `avanzado`, `capacidades_optin`, `comparador_bd`, `interfaz_ui`, **`paridad_proveedores`** — más `"otros"` intencionalmente vacío (es el fallback de `categorize()`). `STACKY_GITLAB_SYNC_FULL_CADA_N` (línea 617) vive en **`paridad_proveedores`**, que es además la categoría correcta para esta flag: gobierna el tráfico contra el tracker.
>
> **La causa de la confusión, para que no se repita:** `group="global"` de la `FlagSpec` (guardián 2) **es otro campo distinto** y ahí `"global"` **sí** es un valor válido — lo usan **433** de las 495 specs. `group` es la agrupación del panel; `_CATEGORY_KEYS` es la categorización del arnés. **Son dos cosas y hay que llenar las dos, cada una con su vocabulario.**
>
> El comando que lo resuelve sin adivinar, si el implementador quiere confirmarlo:
>
> ```bash
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> .venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from services.harness_flags import _CATEGORY_KEYS as C; print('hay global?', 'global' in C); print([c for c,ks in C.items() if 'STACKY_GITLAB_SYNC_FULL_CADA_N' in ks])"
> ```
>
> Salida esperada: `hay global? False` y `['paridad_proveedores']`.

**Guardián 4 — `PLAIN_HELP` en `backend/services/harness_flags_help.py`**, junto a las del 292 (`:2511`):

```python
    "STACKY_TICKET_SYNC_INTERVAL_MS": PlainHelp(
        what="Cada cuántos milisegundos el tablero de tickets busca novedades del tracker por su cuenta, sin que apretes Sincronizar.",
        on_effect="Si subís el número: Stacky consulta menos seguido, así que le da menos trabajo al servidor de la empresa y las novedades tardan un poco más en aparecer.",
        off_effect="Si bajás el número: las novedades aparecen antes, pero Stacky consulta más seguido y el servidor de la empresa trabaja más.",
        example="Con 45000 consulta cada 45 segundos, que es como venía. Con 180000 consulta cada 3 minutos: se hacen cuatro veces menos consultas y las novedades siguen llegando solas.",
    ),
```

> **`PLAIN_HELP` no se deriva de `description`.** Son dos textos con audiencias distintas: `description` es técnica y va en el tooltip del panel; `PlainHelp` es la explicación llana con `example`. Escribir uno y esperar que el otro aparezca es un error conocido de este repo.

**Guardián 5 — `_FROZEN_BOUNDS` en `backend/tests/test_harness_flags_bounds.py`**, junto a la del 292 (`:227`):

```python
    "STACKY_TICKET_SYNC_INTERVAL_MS": (5000, 3600000),   # Plan 295
```

> `test_bounds_map_is_frozen` (`:232-240`) construye el dict real desde `FLAG_REGISTRY` y lo compara con **`==`**. Olvidar esta línea da un fallo con el diff completo: es un guardián que **avisa fuerte**, no en silencio.

**Guardián 6 — `_CURATED_DEFAULTS_ON`: NO SE TOCA.** `backend/tests/test_harness_flags.py:1129` ya dice, sobre la numérica del 292: "*Su hermana `STACKY_GITLAB_SYNC_FULL_CADA_N` NO figura acá a propósito*". **Agregar la de este plan pone rojo `test_default_known_only_for_curated`.**

#### F10.3 — El backend deja de leer `os.environ`

`backend/api/tickets.py:6778`. Hoy:

```python
        "ticket_sync_interval_ms": int(os.environ.get("STACKY_TICKET_SYNC_INTERVAL_MS", 45000)),
```

Pasa a:

```python
        # Plan 295 F10 — se lee de config.config, NO de os.environ: el panel de flags
        # escribe en config, y leyendo el entorno la perilla era inmovible desde la UI.
        # `config` en tickets.py es el MÓDULO (import config, :39) => `config.config`.
        "ticket_sync_interval_ms": int(
            getattr(config.config, "STACKY_TICKET_SYNC_INTERVAL_MS", 45000)
        ),
```

> **Las otras dos claves del endpoint (`sync_min_interval_sec`, `stale_threshold_sec`) NO se tocan.** Siguen leyendo `os.environ`. Son fuera de alcance de este plan, y convertirlas exigiría dos flags más con sus nueve guardianes cada una. **Se anota en `## DIFERIDOS` §D-5.**

#### F10.4 — El frontend usa el valor recibido

**Archivos a editar:**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\pages\TicketBoard.tsx` — **la fuente única del valor**.

**Nombre EXACTO del hook nuevo:** **NINGUNO.** Se usa `useQuery` de React Query, que ya está en este archivo, contra el endpoint que ya existe. **Cero infraestructura nueva.**

```tsx
// Plan 295 F10 — el intervalo sale del backend (flag del operador), con el 45 000
// histórico como fallback. UNA sola fuente para los DOS consumidores: el hook
// (:1110) y la barra de estado (:1353). Si solo se alimentara el hook, la barra
// derivaría "stale" contra 45 s mientras el sync corre cada 180 s, y el operador
// vería la barra en rojo permanente.
const { data: cfgSync } = useQuery({
  queryKey: ["tickets", "config", "frontend"],
  queryFn: () => Tickets.frontendConfig(),
  staleTime: Infinity,          // se lee UNA vez al montar; no es un dato que cambie solo
  retry: false,                 // si falla, el fallback alcanza: no hay que insistir
});
const intervaloSync = cfgSync?.ticket_sync_interval_ms ?? TICKET_SYNC_INTERVAL_MS;
```

Y las **dos** líneas de consumo:

```tsx
// :1110
} = useTicketSync({ intervalMs: intervaloSync, syncOnMount: true });
// :1353
  intervalMs={intervaloSync}
```

> **`TICKET_SYNC_INTERVAL_MS` (el alias de `DEFAULT_INTERVAL_MS`) SE CONSERVA como fallback.** No se borra el import de `:12`. Motivo: `Tickets.frontendConfig()` pasa por el wrapper `api.get`, que **lanza en non-2xx** — si el endpoint estuviera caído, `cfgSync` queda `undefined` y el `??` salva el tablero. **Borrar la constante convertiría un fallo del endpoint de config en un tablero sin auto-sync.**
>
> **`useTicketSync.ts` NO se edita.** Ya soporta `intervalMs` por opción (`:110`, `:126-128`, con `intervalMsRef` para evitar closures obsoletas). La fase le **pasa** un valor distinto; no le cambia una línea. **Esa es la razón por la que I5 es riesgo bajo.**

#### F10.5 — Tests

**Archivos a crear:**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_flag_intervalo.py`
2. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\pages\__tests__\plan295IntervaloDelOperador.test.ts`

**Casos del test de backend (7):**

| # | Caso | Assert |
|---|---|---|
| 1 | la flag está **en** `FLAG_REGISTRY` | `"STACKY_TICKET_SYNC_INTERVAL_MS" in {s.key for s in FLAG_REGISTRY}` |
| 2 | es `type="int"` con los bounds declarados | `spec.type == "int"` y `(spec.min_value, spec.max_value) == (5000, 3600000)` |
| 3 | **NO** declara `default=` (la regla dura de las numéricas) | `spec.default is None` |
| 4 | **[v2, C2]** está categorizada, y **en la categoría real** | `"STACKY_TICKET_SYNC_INTERVAL_MS" in _CATEGORY_KEYS["paridad_proveedores"]` **y** `categorize("STACKY_TICKET_SYNC_INTERVAL_MS") != "otros"` |
| 5 | tiene `PLAIN_HELP` con los 4 campos no vacíos | `plain_help_for(key)` devuelve dict y `all(v for v in d.values())` |
| 6 | **flag en 180000 ⇒ el endpoint devuelve `180000`** | `monkeypatch.setattr(config.config, key, 180000)`; `data["ticket_sync_interval_ms"] == 180000` |
| 7 | el endpoint **ya no** lee `os.environ` | poner `os.environ[key] = "999"` **y** `config.config` en `180000` ⇒ el endpoint devuelve **`180000`**, no `999` |
| 8 | **[ADICIÓN ARQUITECTO 2 — v2, C6]** los **SEIS guardianes** de la flag numérica, en un solo assert que corre en un archivo VERDE | ver el bloque de abajo |

> **El caso 7 es el que prueba la fase.** Los casos 1-5 prueban el registro; el 6 prueba la lectura; **el 7 prueba que la vieja fuente dejó de mandar**. Sin él, un endpoint que leyera las dos fuentes pasaría el 6 igual.
>
> **[v2, C2] El caso 4 del v1 daba `KeyError`**, no un assert rojo: `_CATEGORY_KEYS["global"]` no existe. Un `KeyError` en un test es indistinguible de un bug del test, y la salida barata del modelo menor es borrar el caso. Ahora apunta a la categoría real **y** agrega el assert de `categorize()`, que es el que caza el caso en que alguien mete la key en la tupla equivocada: la key estaría "categorizada" pero en el cajón que no le toca.

#### F10.5.bis — [ADICIÓN ARQUITECTO 2] Los SEIS guardianes de la flag numérica, en un solo caso binario

**El problema que resuelve (medido, C6).** El v1 apoyaba dos de los seis guardianes en archivos que están **rojos de fábrica**:

- `test_harness_flags_bounds.py` → **`1 failed, 17 passed`** medido. El que falla es **`test_bounds_map_is_frozen`**, porque `FLAG_REGISTRY` trae **6** numéricas del plan 284 (`STACKY_DOCS_CITATION_GATE_MIN_RATIO`, `STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS`, `STACKY_DOCS_PIPELINE_MAX_LLM_CALLS`, `STACKY_DOCS_RIGOR_MIN_CITATIONS`, y dos más) ausentes de `_FROZEN_BOUNDS`.
- `test_harness_flags_help.py` → **`4 failed, 4 passed`** medido.

El v1 decía de `_FROZEN_BOUNDS`: "*Olvidar esta línea da un fallo con el diff completo: es un guardián que **avisa fuerte**, no en silencio*". **Es falso hoy.** Con el criterio "delta cero en los 5 guardianes", el archivo sale `1 failed, 17 passed` **con o sin** la entrada nueva: **el guardián no discrimina**, y F10 podía cerrarse sin `_FROZEN_BOUNDS` ni `PLAIN_HELP` y nada lo cazaba. Es el gotcha de "criterio de conteo sobre archivo rojo".

**La solución: el criterio se muda a un archivo VERDE y asertá el CONTENIDO, no el conteo.** Se agrega a `test_plan295_flag_intervalo.py` (que nace verde) un caso que verifica los seis puntos de cableado de una vez:

```python
def test_los_seis_guardianes_de_la_flag_numerica():
    """[ADICIÓN ARQUITECTO 2 — Plan 295 F10] Los SEIS guardianes de una flag
    numérica, asertados por CONTENIDO en un archivo VERDE.

    POR QUÉ NO ALCANZA CON "correr los guardianes y pedir delta cero":
    test_harness_flags_bounds.py está ROJO DE FÁBRICA (1 failed, 17 passed: le
    faltan 6 numéricas del plan 284 a _FROZEN_BOUNDS) y test_harness_flags_help.py
    también (4 failed, 4 passed). Un criterio de CONTEO sobre un archivo rojo no
    discrimina: sale igual con la entrada y sin ella. Este caso sí.

    Es reutilizable tal cual por la próxima flag numérica: cambiá KEY y BOUNDS.
    """
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS, categorize
    from services.harness_flags_help import PLAIN_HELP
    from tests.test_harness_flags_bounds import _FROZEN_BOUNDS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    import config as _config

    KEY = "STACKY_TICKET_SYNC_INTERVAL_MS"
    BOUNDS = (5000, 3600000)
    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)

    # G1 — el valor efectivo vive en config.py y conserva el 45000 histórico.
    assert getattr(_config.config, KEY, None) == 45000, "G1 config.py"

    # G2 — la FlagSpec existe, es int, con bounds, escribible y SIN default=.
    assert spec is not None, "G2 FlagSpec ausente"
    assert spec.type == "int" and (spec.min_value, spec.max_value) == BOUNDS, "G2 tipo/bounds"
    assert spec.env_only is False, "G2 env_only=True la dejaría fuera del panel"
    assert spec.default is None, "G2 una numérica NO declara default= (ver G6)"
    assert spec.requires is None, "G2 sin requires => no toca _REQUIRES_MAP_FROZEN"

    # G3 — categorizada, y en la categoría REAL (NO existe _CATEGORY_KEYS["global"]).
    assert KEY in _CATEGORY_KEYS["paridad_proveedores"], "G3 categoría"
    assert categorize(KEY) != "otros", "G3 cayó en el fallback"

    # G4 — PLAIN_HELP escrito A MANO (no se deriva de description), 4 campos llenos.
    assert KEY in PLAIN_HELP, "G4 PLAIN_HELP ausente"
    ayuda = PLAIN_HELP[KEY]
    for campo in ("what", "on_effect", "off_effect", "example"):
        assert getattr(ayuda, campo, "").strip(), f"G4 PlainHelp.{campo} vacío"

    # G5 — _FROZEN_BOUNDS. ESTE es el que el archivo rojo NO puede vigilar.
    assert _FROZEN_BOUNDS.get(KEY) == BOUNDS, (
        f"G5 _FROZEN_BOUNDS[{KEY}] = {_FROZEN_BOUNDS.get(KEY)!r}, se esperaba {BOUNDS}. "
        "test_bounds_map_is_frozen NO puede avisarte: ya está rojo por el plan 284."
    )

    # G6 — _CURATED_DEFAULTS_ON es SOLO para booleanas ON: la numérica NO va.
    assert KEY not in _CURATED_DEFAULTS_ON, (
        "G6 una numérica en _CURATED_DEFAULTS_ON pone rojo "
        "test_default_known_only_for_curated"
    )
```

**Mitad de contraste de este caso (obligatoria, se corre y se revierte):** con los seis guardianes ya cableados, **borrar a mano** la línea de `_FROZEN_BOUNDS` y correr sólo este archivo. Esperado:

```
FAILED tests/test_plan295_flag_intervalo.py::test_los_seis_guardianes_de_la_flag_numerica
E  AssertionError: G5 _FROZEN_BOUNDS[STACKY_TICKET_SYNC_INTERVAL_MS] = None, se esperaba
   (5000, 3600000). test_bounds_map_is_frozen NO puede avisarte: ya está rojo por el plan 284.
```

Y **la comprobación que prueba el punto**: correr `test_harness_flags_bounds.py` **con la línea borrada** y verificar que sigue diciendo **`1 failed, 17 passed`** — o sea, **exactamente lo mismo** que con la línea puesta. Ese par de outputs, pegados juntos en el doc, es la evidencia de que el guardián viejo no discriminaba y el nuevo sí. Después se restaura la línea.

> **Por qué esta adición vale más allá de este plan:** el bloque es una plantilla. Toda flag numérica futura de este repo tiene los mismos seis guardianes y dos de ellos viven en archivos que probablemente sigan rojos. Copiar este caso cambiando `KEY` y `BOUNDS` convierte "acordate de los seis lugares" en un assert.

**Casos del test de frontend (3, `.ts` PURO — RTL/jsdom no están instalados):**

Se prueba la **lógica de selección del valor** con una función pura extraída a un módulo nuevo, para que el test no dependa de renderizar:

**Archivo nuevo:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\pages\ticketSyncIntervalo.ts`

```ts
/** Plan 295 F10 — de qué valor sale el intervalo de auto-sync.
 *
 *  Vive en un módulo propio y PURO para poder probarlo con vitest sin renderizar:
 *  RTL y jsdom NO están instalados en este repo, y un .test.tsx con RTL reporta
 *  "no tests" y sale con exit 0 -- un falso verde. Vitest sí corre .ts puro.
 */
export function intervaloDeSync(
  delBackend: number | null | undefined,
  fallback: number,
): number {
  if (typeof delBackend !== "number" || !Number.isFinite(delBackend)) return fallback;
  if (delBackend <= 0) return fallback;
  return delBackend;
}
```

Y `TicketBoard.tsx` la usa: `const intervaloSync = intervaloDeSync(cfgSync?.ticket_sync_interval_ms, TICKET_SYNC_INTERVAL_MS);`

| # | Caso | Assert |
|---|---|---|
| 1 | con `180000` del backend ⇒ devuelve **`180000`**, no la constante | `intervaloDeSync(180000, 45000) === 180000` |
| 2 | con `undefined` (endpoint caído) ⇒ devuelve el fallback | `intervaloDeSync(undefined, 45000) === 45000` |
| 3 | con `0`, `-1` o `NaN` ⇒ fallback (un intervalo de 0 sería un bucle de red) | los tres `=== 45000` |
| 4 | **los DOS consumidores usan la misma variable** (test de texto fuente) | el archivo `TicketBoard.tsx` contiene `intervalMs: intervaloSync` **y** `intervalMs={intervaloSync}` |

**Comandos exactos:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_flag_intervalo.py" -q
```

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run "src/pages/__tests__/plan295IntervaloDelOperador.test.ts"
```

**Guardianes que hay que correr ADEMÁS (son trampa de commit, no de edición):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_bounds.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_ratchet_script_parity.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_p7_sync_endpoints.py" -q
```

> **`test_harness_flags_help.py` tiene 4 rojos AJENOS de fábrica** (medido en F0). El criterio es **delta cero**: si venía 4F/4P, tiene que seguir 4F/4P. **Si aparece un 5º rojo, es de esta fase** y hay que arreglarlo.
>
> **`test_p7_sync_endpoints.py:16` hace `monkeypatch.setenv("STACKY_TICKET_SYNC_INTERVAL_MS", "45000")` y `:47` asertá `data["ticket_sync_interval_ms"] == 45000`.** Después de F10 el endpoint **ya no lee el entorno**, así que ese `setenv` no hace nada — pero el assert **sigue pasando** porque el default de `config.py` es 45000. **Verificarlo explícitamente**: si sale rojo, es porque `config.py` no quedó en 45000.

**Criterio de aceptación BINARIO [v2, C2 + C6]:** **8 passed** en el test de backend (7 del v1 + el caso 8 de los seis guardianes), **4 passed** en el de frontend, y `len(FLAG_REGISTRY)` = **B3 + 1** (con B3 = 495 ⇒ **496**; **más 2 de F6 y F9** si esas fases ya están ⇒ **498**).

**Los guardianes ajenos se corren igual, con criterio DELTA contra el baseline MEDIDO de F0 — y NINGUNO de ellos es el criterio de la fase:**

| Archivo | Baseline medido (F0) | Después de F10 | Discrimina? |
|---|---|---|---|
| `test_harness_flags.py` | **59 passed** | **61 passed** (+2 de las booleanas ON de F6 y F9; si F10 va sola, **59 passed**) | **SÍ** — está verde: cualquier rojo es daño propio |
| `test_harness_flags_bounds.py` | **1 failed, 17 passed** | **1 failed, 17 passed** | **NO** — rojo de fábrica. Lo cubre el caso 8 |
| `test_harness_flags_help.py` | **4 failed, 4 passed** | **4 failed, 4 passed** | **NO** — rojo de fábrica. Lo cubre el caso 8 (G4) |
| `test_plan259_ratchet_script_parity.py` | **12 passed** | **12 passed** | SÍ |
| `test_harness_ratchet_meta.py` | **4 passed** | **4 passed** | SÍ — **[v2, C3]** y sólo si el test nuevo se registró en el `.sh` |
| `test_p7_sync_endpoints.py` | **3 passed** | **3 passed** | SÍ |

**Mitad de contraste (esperado en ROJO antes del código):**

```
FAILED test_plan295_flag_intervalo.py::test_la_flag_esta_registrada
E  AssertionError: STACKY_TICKET_SYNC_INTERVAL_MS no está en FLAG_REGISTRY
   (0 de 495 specs la declaran)
FAILED test_plan295_flag_intervalo.py::test_flag_en_180000_llega_al_endpoint
E  assert 45000 == 180000
FAILED test_plan295_flag_intervalo.py::test_el_endpoint_ignora_os_environ
E  assert 999 == 180000   ← el endpoint sigue leyendo el ENTORNO
```

**El tercero es el que demuestra el defecto.** Y del lado del frontend, los 4 casos fallan con `Cannot find module './ticketSyncIntervalo'`.

**Registro en los DOS ratchets:** `tests/test_plan295_flag_intervalo.py` en `.sh` **y** `.ps1`.

**Flag que la protege:** **la flag ES la fase.** `STACKY_TICKET_SYNC_INTERVAL_MS` — **NUEVA, tipo `int`, default efectivo `45000` en `config.py`, SIN `default=` en la `FlagSpec`**.

- **Categoría de excepción: NINGUNA.** No es booleana ON/OFF: es un número. No quema tokens en reposo (**al contrario: subirla los BAJA**), no escribe en ningún sistema del operador, no le saca ninguna decisión — **se la da**.
- **El default conserva el comportamiento de hoy (45 000).** Este plan **no** aplica la recomendación del 292 por el operador: le da la perilla y le dice cuánto ganaría. **Eso es human-in-the-loop.** Cambiar el default a 180 000 sería decidir por él sobre el tráfico contra su servidor corporativo, y va en `## PENDIENTES DEL OPERADOR`.

**Impacto por runtime:**
- **Codex CLI / Claude Code CLI / GitHub Copilot Pro** — **idéntico**. El intervalo es del **navegador**; ningún runtime de agente participa en el auto-sync.
- **Fallback por runtime:** ninguno necesario. **Fallback de la fase:** si `GET /api/tickets/config/frontend` falla o devuelve un valor inválido, `intervaloDeSync` devuelve **45 000** y el tablero se comporta como hoy. Probado en los casos 2 y 3.

**Trabajo del operador: opt-in (default ON)** — la perilla aparece en el panel de flags con su valor actual y su ayuda llana. **No tiene que hacer nada para que siga funcionando como hoy.**

---

### F11 — I6 parcial: los rótulos de las dos pantallas limpias dejan de decir "Feature" y "Done"

**Objetivo:** rutear los **4** rótulos ADO hardcodeados de `EpicChildrenPanel.tsx` y `FinishWorkButton.tsx` con los helpers que **ya existen**.

**Valor:** un operador de GitLab lee "Feature(s)", "[Feature]", "[Task]" y "Ej: Done, Closed, Resolved" — vocabulario de Azure DevOps en una pantalla que está mostrando issues de GitLab.

**Los 4 rótulos, verificados uno por uno:**

| Archivo | Línea verificada | Texto actual |
|---|---|---|
| `frontend\src\components\EpicChildrenPanel.tsx` | **:125** | `{preview.features.length} Feature(s) derivada(s) de los bloques RF de la épica:` |
| `frontend\src\components\EpicChildrenPanel.tsx` | **:130** | `<strong>[Feature]</strong> {feat.title}` |
| `frontend\src\components\EpicChildrenPanel.tsx` | **:134** | `<li key={ti}><strong>[Task]</strong> {task.title}</li>` |
| `frontend\src\components\FinishWorkButton.tsx` | **:244** | `placeholder="Ej: Done, Closed, Resolved"` |

**Los helpers que YA existen y se reusan (cero helpers nuevos):**

| Helper | Archivo:línea verificada | Qué devuelve |
|---|---|---|
| `nombreDeTracker(tipo)` | `frontend\src\lib\trackerLabels.ts:61` | `"Azure DevOps"` / `"GitLab"` / … |
| `refDeTicket(...)` | `frontend\src\lib\trackerLabels.ts:101` | la referencia corta de un ítem según el tracker |
| `sugerenciasDeEstadoFinal(tipo)` | `frontend\src\lib\trackerLabels.ts:131` | la lista de estados finales del tracker |

> **`FinishWorkButton.tsx:248-252` YA usa `sugerenciasDeEstadoFinal(trackerDelTicket)`** para poblar el `<datalist id="ado-state-suggestions">`. **El `placeholder` de `:244` es el único que quedó hardcodeado**, contradiciendo el `datalist` que está tres líneas más abajo. **La corrección es derivar el placeholder de la misma llamada.**

**Cambio 1 — `FinishWorkButton.tsx:244`:**

```tsx
                // Plan 295 F11 — el placeholder sale de la MISMA fuente que el
                // datalist de :248-252, que ya rutea por tracker. Antes decía
                // "Ej: Done, Closed, Resolved" (Azure DevOps) en un ticket de GitLab.
                placeholder={`Ej: ${sugerenciasDeEstadoFinal(trackerDelTicket).slice(0, 3).join(", ")}`}
```

> **`.slice(0, 3)` es deliberado:** el placeholder tiene que caber en el input. Si el helper devolviera 8 estados, el placeholder se cortaría visualmente y el operador no vería ninguno completo. Con 3 se conserva la forma del texto actual.
>
> **Caso borde:** si `sugerenciasDeEstadoFinal` devolviera `[]` (tracker desconocido), el placeholder queda `"Ej: "`. **Hay que guardarlo:**

```tsx
placeholder={
  sugerenciasDeEstadoFinal(trackerDelTicket).length > 0
    ? `Ej: ${sugerenciasDeEstadoFinal(trackerDelTicket).slice(0, 3).join(", ")}`
    : "Estado final del ítem"
}
```

**Cambio 2 — `EpicChildrenPanel.tsx:125,130,134`.** Los tres nombran **tipos de work item**, no estados. Se usa `refDeTicket` no —eso es para referencias— sino un mapa de tipos por tracker. **Verificación obligatoria antes de escribir:**

```bash
grep -n "export function\|export const" "Stacky Agents/frontend/src/lib/trackerLabels.ts" | grep -i "tipo\|type\|feature\|task"
```

**Si existe un helper de tipos de work item, se usa.** Si **no existe**, se agrega **uno solo** a `trackerLabels.ts` (que es el módulo canónico de rótulos, no un archivo nuevo):

```ts
/** Plan 295 F11 — cómo se llama en cada tracker el nivel intermedio y el nivel
 *  hoja de una descomposición. ADO: Feature / Task. GitLab: no tiene tipos nativos
 *  de work item -- el plan 277 F4 clasifica LOCALMENTE con etiquetas type::*, así
 *  que el vocabulario honesto es genérico. */
export function nombreDeNivel(
  tipo: string | undefined | null,
  nivel: "intermedio" | "hoja",
): string {
  const t = (tipo ?? "").trim().toLowerCase();
  if (t === "gitlab") return nivel === "intermedio" ? "Grupo" : "Tarea";
  return nivel === "intermedio" ? "Feature" : "Task";
}
```

Y los tres usos:

```tsx
// :125
{preview.features.length} {nombreDeNivel(trackerType, "intermedio")}(s) derivada(s) de los bloques RF de la épica:
// :130
<strong>[{nombreDeNivel(trackerType, "intermedio")}]</strong> {feat.title}
// :134
<li key={ti}><strong>[{nombreDeNivel(trackerType, "hoja")}]</strong> {task.title}</li>
```

> ✅ **[v2, C15] `trackerType` YA EXISTE en el componente. No hay nada que cablear y no hay decisión que tomar.** El v1 decía "*`EpicChildrenPanel` **no** recibe hoy el tracker*" y abría una elección entre (a) prop del padre y (b) `useWorkbench`. **Es falso**, verificado abriendo el archivo:
>
> ```tsx
> // frontend/src/components/EpicChildrenPanel.tsx
> :15  import { useWorkbench } from "../store/workbench";
> :16  import { nombreDeTracker } from "../lib/trackerLabels";
> ...
> :44  // Plan 282 F4 — los rotulos siguen al tracker del proyecto activo.
> :45  const trackerType = useWorkbench((s) => s.activeProject?.tracker_type ?? null);
> ```
>
> El plan 282 F4 ya hizo ese trabajo y el componente **ya usa** `nombreDeTracker(trackerType)` en `:89`, `:90` y `:178`. **La variable se llama `trackerType`** — el `trackerActivo` del v1 no existe en ninguna parte del archivo y habría dado `TS2304: Cannot find name 'trackerActivo'` en el `npx tsc --noEmit` de F12, o sea al final, cuando el implementador cree que terminó.
>
> **Consecuencia de alcance:** los tres rótulos de `:125`, `:130` y `:134` son **tres sustituciones de una línea cada una**, sin tocar props, sin tocar el padre (`OutputPanel.tsx:300`) y sin agregar un `import` (el de `trackerLabels` ya está en `:16`; sólo hay que sumar `nombreDeNivel` a la lista de nombres importados). **Cero riesgo de tocar un archivo de la lista prohibida.**

**Tests PRIMERO — archivo a crear:**

`N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\lib\__tests__\plan295RotulosRuteados.test.ts`

**Casos (5, `.ts` puro):**

| # | Caso | Assert |
|---|---|---|
| 1 | `nombreDeNivel("gitlab", "intermedio")` **no** dice "Feature" | `!== "Feature"` y es no vacío |
| 2 | `nombreDeNivel("azure_devops", "intermedio") === "Feature"` (**no-regresión**) | igualdad exacta |
| 3 | `nombreDeNivel(null, "hoja") === "Task"` (fallback ADO, comportamiento de hoy) | igualdad exacta |
| 4 | censo: `EpicChildrenPanel.tsx` **no** contiene `Feature(s)` ni `[Feature]` ni `[Task]` como literales | `expect(fuente).not.toContain("[Feature]")` etc. |
| 5 | censo: `FinishWorkButton.tsx` **no** contiene `"Ej: Done, Closed, Resolved"` | `not.toContain` |
| 6 | **[v2, C15]** `EpicChildrenPanel.tsx` usa la variable **REAL** del componente, no una inventada | `expect(fuente).toContain("nombreDeNivel(trackerType")` **y** `expect(fuente).not.toContain("trackerActivo")` |

> Los casos 4 y 5 son de **ausencia**, que es lo que G7 desaconseja — así que van **acompañados** del **caso 6**, que es de **presencia** sobre el mismo archivo. Sin él, un error en la ruta haría pasar los censos en falso.
>
> **[v2, C15] El caso 6 caza además el error concreto del v1**: `nombreDeNivel(trackerActivo, …)`. `trackerActivo` no existe en `EpicChildrenPanel.tsx` (la variable es `trackerType`, `:45`), y un `tsc --noEmit` lo diría recién en F12. Este caso lo dice en la fase.

**Comando exacto:**

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run "src/lib/__tests__/plan295RotulosRuteados.test.ts"
```

**No-regresión obligatoria — el censo del plan 282:**

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run "src/services/__tests__/plan282Censo.test.ts"
```

> **`plan282Censo.test.ts` tiene una lista `NUNCA_ALLOWLISTEABLES` que incluye `components/FinishWorkButton.tsx`** (verificado). Eso significa que ese archivo **no puede** entrar en la allowlist de deuda declarada: si F11 lo deja con rótulos ADO, el censo lo caza. **Es un gate que ya existe y que esta fase satisface.**

**Criterio de aceptación BINARIO [v2, C15]:** **6 passed** en el test nuevo (5 del v1 + el caso 6 de la variable real), delta cero en `plan282Censo.test.ts`, y K9:

```
grep -c "\[Feature\]\|\[Task\]\|Feature(s)" "Stacky Agents/frontend/src/components/EpicChildrenPanel.tsx"
grep -c "Ej: Done, Closed, Resolved" "Stacky Agents/frontend/src/components/FinishWorkButton.tsx"
→ los dos deben dar 0
```

**Mitad de contraste (esperado en ROJO antes del código):** el caso 1 falla con `Cannot find module` (el helper no existe), y los casos 4 y 5 fallan con `expected '...' not to contain '[Feature]'` / `not to contain 'Ej: Done, Closed, Resolved'`. **Los censos rojos antes del cambio son la prueba de que los 4 rótulos estaban ahí.**

**Flag que la protege:** **ninguna.** Cambiar un rótulo por el rótulo correcto del tracker activo no es una capacidad: es la corrección de un texto. Una flag para "seguir mostrando el vocabulario del tracker equivocado" no tiene sentido.

**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro — **idéntico**. Son rótulos de UI. Fallback: `nombreDeNivel(null, ...)` devuelve el vocabulario ADO, que es el de hoy: **un tracker desconocido no deja la pantalla en blanco**.

**Trabajo del operador: ninguno.**

---
### F12 — Paridad de los tres runtimes, documentación y no-regresión

**Objetivo:** demostrar con un test que **ninguna** de las once fases anteriores ató nada a un runtime, actualizar la documentación del sistema, y correr la batería completa de no-regresión con **delta** contra los baselines de F0.

**Valor:** es la fase que convierte "creo que funciona" en "está medido". Sin F12, el plan entrega once cambios y cero evidencia de que el conjunto es coherente.

**Archivos EXACTOS a crear/editar (ruta completa):**

1. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan295_paridad_runtimes.py` — **crear**.
2. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\docs\sistema\` — actualizar el documento que describa la integración GitLab (**leer el índice de esa carpeta antes de elegir el archivo; no crear uno nuevo si ya hay uno del tema**).
3. `N:\GIT\RS\STACKY\Stacky\Stacky Agents\docs\295_PLAN_LA_INTEGRACION_CON_GITLAB_DEJA_DE_MENTIR_SOBRE_SI_MISMA.md` — **este archivo**: completar la tabla "Estado de implementación por fase".

**Casos del test de paridad (6):**

| # | Caso | Assert |
|---|---|---|
| 1 | **ningún** módulo tocado por este plan menciona un runtime concreto | grep-por-AST sobre los 6 archivos de backend editados: cero ocurrencias de `"codex"`, `"claude_code"`, `"github_copilot"` |
| 2 | `services/gitlab_setup_check.py` **no** importa de `api/` | `"from api" not in fuente and "import api" not in fuente` |
| 3 | `services/integration_breaker.py` **no** importa de `api/` | ídem |
| 4 | `services/provider_capabilities.py` sigue siendo **puro** (sin red, sin BD, sin adaptadores) | `not any(x in fuente for x in ("requests", "session_scope", "gitlab_provider", "ado_provider"))` |
| 5 | las **3** flags nuevas están en `FLAG_REGISTRY`, categorizadas y con `PLAIN_HELP` | las 3 keys presentes en las 3 estructuras |
| 6 | ninguna de las 3 flags nuevas declara `requires=` sin estar en `_REQUIRES_MAP_FROZEN` | para cada una: `spec.requires is None` |

> **El caso 1 es una excepción documentada.** `backend/api/phase6.py:192` **sí** menciona `runtime="github_copilot"` — pero eso **es preexistente** y F9 **no lo tocó**. El test excluye ese archivo de la regla del caso 1 y lo anota como deuda en §D-4. **Excluirlo sin decirlo sería un gate vacío**; excluirlo con el motivo escrito es un ratchet honesto.

#### F12.bis — [v2, C3] LOS NUEVE archivos de test del backend van a los DOS ratchets. Tabla literal.

**El defecto del v1:** creaba **9** archivos de test de backend y nombraba el registro sólo en 4 fases (F3, F4, F9, F10). El DoD decía "los 5". **Los que faltaran ponen ROJO `test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests`**, que exige que **todo** `tests/test_*.py` esté en `HARNESS_TEST_FILES` del `.sh` **o** en `harness_ratchet_allowlist.txt`. Es trampa de **commit**: revienta al final, con `--no-verify` prohibido.

**Y la vía del allowlist está cerrada:** medido, `harness_ratchet_allowlist.txt` tiene **194** entradas y `test_harness_ratchet_meta.py:66` fija `_ALLOWLIST_MAX = 197`. Meter 5 daría **199** y pondría rojo `test_allowlist_grandfathered_solo_baja` **además** del otro. **La única salida correcta es registrar los nueve en el `.sh`.**

| # | Archivo de test (backend) | Fase | En `run_harness_tests.sh` (ruta **pelada**) | En `run_harness_tests.ps1` (**entrecomillada + coma**) |
|---|---|---|---|---|
| 1 | `tests/test_plan295_matriz_no_miente.py` | F2 / F2a | **SÍ** | **SÍ** |
| 2 | `tests/test_plan295_gate_transversal.py` | F3 | **SÍ** | **SÍ** |
| 3 | `tests/test_plan295_ratchet_evidencias.py` | F4 | **SÍ** | **SÍ** |
| 4 | `tests/test_plan295_sonda_tls.py` | F5 | **SÍ** | **SÍ** |
| 5 | `tests/test_plan295_errores_gitlab.py` | F6 | **SÍ** | **SÍ** |
| 6 | `tests/test_plan295_breaker_gitlab.py` | F7 / F8 | **SÍ** | **SÍ** |
| 7 | `tests/test_plan295_webhooks_por_proyecto.py` | F9 | **SÍ** | **SÍ** |
| 8 | `tests/test_plan295_flag_intervalo.py` | F10 | **SÍ** | **SÍ** |
| 9 | `tests/test_plan295_paridad_runtimes.py` | F12 | **SÍ** | **SÍ** |

> **Formato, que difiere entre los dos archivos y es donde se cometen los errores:**
> - `.sh` → `  tests/test_plan295_matriz_no_miente.py` — ruta **pelada**, sin comillas, sin coma.
> - `.ps1` → `  "tests/test_plan295_matriz_no_miente.py",` — **entrecomillada y con coma**. El **último** elemento del array va **sin** coma final (`run_harness_tests.ps1:1008`).
> - `test_plan259_ratchet_script_parity.py::test_el_ps1_no_tiene_rutas_sin_comillas` caza exactamente el error de pegar la ruta pelada en el `.ps1`: PowerShell la lee como nombre de comando y **el array la pierde en silencio**.
>
> **Los 4 archivos de test del frontend (`.test.ts`) NO van a estos ratchets**: los scripts del arnés sólo listan `tests/*.py` del backend. Sus gates son el `npx vitest run` de su fase y el `npx tsc --noEmit` de F12.
>
> **Brecha después de registrar:** +9 en el `.sh` y +9 en el `.ps1` ⇒ `solo_en_sh` se mantiene en **64**, que es exactamente `_PS1_LAG_MAX`. **Registrar en uno solo la lleva a 65 y pone rojo `test_el_ps1_no_pierde_terreno`.**

**Comando de verificación (se corre ANTES de commitear código, no después):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_ratchet_meta.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_ratchet_script_parity.py" -q
```

**Las TRES flags nuevas del plan, en una tabla (para que el implementador no se pierda):**

| Flag | Tipo | Default | `_CURATED_DEFAULTS_ON` | `default=` en la `FlagSpec` | Fases |
|---|---|---|---|---|---|
| `STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED` | `bool` | **ON** | **SÍ** | `default=True` | F6, F7, F8 |
| `STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED` | `bool` | **ON** | **SÍ** | `default=True` | F9 |
| `STACKY_TICKET_SYNC_INTERVAL_MS` | `int` | **45000** (en `config.py`) | **NO — PROHIBIDO** | **SIN `default=`** | F10 |

**Reusadas, no creadas (cero guardianes que tocar):** `STACKY_GITLAB_TLS_ADAPTER_ENABLED` (F5), `STACKY_INTEGRATION_DEGRADATION_ENABLED` (F7, F8), `STACKY_PROVIDER_PARITY_ENABLED` (F2, sin tocar), `STACKY_SETUP_GUIDE_VERIFY_ENABLED` (F5, sin tocar).

**Impacto por runtime — la tabla completa del plan, fase por fase:**

| Fase | Codex CLI | Claude Code CLI | GitHub Copilot Pro | Fallback |
|---|---|---|---|---|
| F0 | igual | igual | igual | conteos por `Select-String` si no hay `grep` |
| F1 | igual | igual | igual | criterio por `grep` si `vitest` no corre |
| F2 | igual | igual | igual | ninguno (módulo puro) |
| F3 | igual | igual | igual | ninguno (`importlib` de stdlib) |
| F4 | igual | igual | igual | ninguno (`re` de stdlib) |
| F5 | igual | igual | igual | contexto OpenSSL `None` ⇒ sesión pelada ⇒ conducta de hoy |
| F6 | igual | igual | igual | flag OFF ⇒ `500` de hoy |
| F7 | igual | igual | igual | `data_dir()` no escribible ⇒ breaker inerte, sync sigue |
| F8 | igual | igual | igual | flag OFF ⇒ GitLab sin breaker, ADO igual |
| F9 | igual | igual | igual¹ | sin proyecto ⇒ `409` accionable, cero filas |
| F10 | igual | igual | igual | endpoint caído ⇒ 45 000 |
| F11 | igual | igual | igual | tracker desconocido ⇒ vocabulario ADO |
| F12 | igual | igual | igual | — |

¹ **Con la deuda preexistente de §D-4:** `api/phase6.py:192` corre el DebugAgent **siempre** con `runtime="github_copilot"`, hardcodeado y con `project_name=None`. F9 **no lo cambia** y lo declara. **Es asimetría preexistente, no introducida por este plan.**

**Batería completa de no-regresión (todos los archivos que este plan toca o roza), con criterio DELTA contra F0:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_matriz_no_miente.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_gate_transversal.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_ratchet_evidencias.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_sonda_tls.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_errores_gitlab.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_breaker_gitlab.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_webhooks_por_proyecto.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_flag_intervalo.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan295_paridad_runtimes.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_setup_guide_api.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_setup_guide_data.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_ratchet_script_parity.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan276_gitlab_sync.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_p7_sync_endpoints.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_bounds.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_ratchet_meta.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_error_fingerprints_catalog.py" -q
```

> **[v2, C3 + C18] Los dos últimos son nuevos en la v2.** `test_harness_ratchet_meta.py` **no estaba en la batería del v1** y es el que caza los archivos de test sin registrar (C3); su criterio es **delta CON LISTA** contra `1 failed, 3 passed` + `['tests/test_plan293_commit.py']`, nunca `4 passed`. `test_error_fingerprints_catalog.py` (`3 failed, 5 passed`) entra para que su rojo ajeno esté medido y no se confunda con daño de este plan.

Frontend:

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run "src/components/devops/__tests__/plan295DeadCodeGitlabProfile.test.ts"
npx vitest run "src/projects/__tests__/plan295VerifyPayload.test.ts"
npx vitest run "src/pages/__tests__/plan295IntervaloDelOperador.test.ts"
npx vitest run "src/lib/__tests__/plan295RotulosRuteados.test.ts"
npx vitest run "src/services/__tests__/plan282Censo.test.ts"
npx tsc --noEmit
```

> **`npx tsc --noEmit` es obligatorio en F12** porque F5, F10 y F11 cambian tipos (`verifyGitlab` payload, `Props.values`, el helper nuevo). **`TicketGraphView.jsx` es `.jsx` y `tsc` NO lo cubre** — no es relevante para este plan, pero conviene saberlo para no interpretar un verde como cobertura total.
>
> **PROHIBIDO correr `pytest tests` completo como veredicto.** Da ~2260 errores por contaminación cruzada y **no es un veredicto**. El arnés se corre con `backend/scripts/run_harness_tests.sh` (o `.ps1`), que corre **archivo por archivo aislado**.

**Criterio de aceptación BINARIO de F12 (y del plan entero):**

1. Los **9** archivos de test nuevos del backend: **todos verdes**, con el conteo de `passed` que su fase declara.
2. Los **4** archivos de test nuevos del frontend: **todos verdes**.
3. **[v2, C3+C18]** Los **11** archivos ajenos de no-regresión: **delta cero** respecto de los baselines **MEDIDOS** de F0 (no "verde": delta contra el número de la tabla). Un rojo nuevo es daño y **bloquea el cierre**. Para `test_harness_ratchet_meta.py` el criterio es **delta con lista**.
4. `npx tsc --noEmit`: **0 errores nuevos** respecto del baseline de F0 (medirlo en F0 también).
5. Los **9** KPI de §1 medidos con sus comandos y anotados.
6. **[v2, C3]** `test_plan259_ratchet_script_parity.py` **verde** (`12 passed`, baseline de F0): la brecha `solo_en_sh` sigue **≤ 64**. **Con los 9 archivos de test nuevos del backend registrados en los DOS scripts, la brecha se mantiene en 64.**
7. **[v2, C18]** `test_harness_ratchet_meta.py` con **delta cero** contra su baseline medido (`1 failed, 3 passed`), y la lista de no clasificados del mensaje de error conteniendo **exactamente** `['tests/test_plan293_commit.py']` — **ningún** `test_plan295_*`. Ver el gate delta de F0.

**Mitad de contraste de F12:** el caso 1 del test de paridad se prueba **inyectando** la palabra `"codex"` en un comentario de `services/gitlab_setup_check.py`, corriendo (tiene que **fallar** nombrando el archivo), y revirtiendo. Sin eso, un test de paridad que solo grepea puede estar buscando en la ruta equivocada.

**Actualización de documentación — qué se escribe y dónde:**

`docs/sistema/` es la **fuente única** de la documentación del sistema. **Antes de crear un archivo, listar la carpeta y buscar el que ya habla de la integración GitLab.** Lo que hay que dejar escrito ahí (3 párrafos, no más):

1. **El TLS de la sonda:** que `run_gitlab_checks` monta el adaptador OpenSSL con el `ca_bundle` del proyecto, **por qué** (G1: `truststore` global) y que `verify=<bundle>` **no alcanza**. Con el `chk-tls` nuevo y su vocabulario.
2. **Los errores de GitLab:** que `TrackerApiError` **no** es hermana de `AdoApiError` y por eso los `except` de los endpoints se ven completos sin estarlo; que ahora hay `_gitlab_sync_error_response` simétrico a `_ado_sync_error_response`; y que el breaker `"gitlab_sync"` usa **`stacky_project_name`** como key, no `ado_breaker_project`.
3. **El match del webhook:** que `ado_id` **no es único** (el único es la terna) y que en GitLab lleva el IID; que los dos receptores filtran por proyecto; y que el placeholder auto-creado escribe los **tres** campos del índice único.

**Y en `docs/_roadmap/PARIDAD_ADO_GITLAB.md`:** ya se regeneró en F2 y F4. **Verificar que `test_doc_de_paridad_esta_sincronizado` está verde**, que es la garantía de que el doc y el código dicen lo mismo.

**Flag que la protege:** ninguna (es verificación y documentación).

**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación concreta |
|---|---|---|---|---|
| R1 | **F8 mueve código en el camino caliente de sync** y rompe el sync de ADO | media | alto | El cuerpo del `if` ADO queda **byte-idéntico** (misma flag, misma key, mismo dict, mismo 200). El caso 12 del test es la no-regresión explícita y **pasa antes y después**. `resolve_project_context` no tiene efectos de red ni BD, así que adelantarla no agrega riesgo. |
| R2 | **F5 monta un adaptador TLS y rompe la sonda** para un GitLab público (gitlab.com) | media | medio | `_sesion_para` **no monta nada** si `ca_bundle` es vacío (`if not ca_bundle: return sesion, ""`). Un GitLab público sigue por `truststore`, que es lo que resuelve Zscaler. Caso borde declarado y testeado. |
| R3 | **F5 cambia el largo del contrato de `run_gitlab_checks` de 5 a 6** y la UI rompe | media | medio | `SetupGuideDialog` itera la lista recibida, no un largo fijo (verificado). Los tests del 259 que asertén 5 se **actualizan a 6** y se anota. El test de F5 asertá los 6 ids **en los 5 caminos de salida**. |
| R4 | **F9 rompe los webhooks ADO ya configurados** en el servidor del operador | media | **alto** | El filtro usa el mismo `or_` tolerante de `api/tickets.py:362-371`, que machea filas con `stacky_project_name = NULL` por `project == tracker_project`. **El caso 11 del test es exactamente ese escenario.** Y `resolve_project_context` acepta un `tracker_project` como `project_name` (su docstring `:381-386`), así que los payloads viejos siguen resolviendo. |
| R5 | **F9 devuelve 409/404 donde antes creaba** y el operador cree que el webhook se rompió | media | medio | Los dos mensajes son **accionables** y nombran el proyecto. El auto-creado queda **ON** por default: el `404` solo aparece si el operador **apaga** la flag. El `409` solo aparece sin proyecto activo, que es un estado que ya rompe todo lo demás. |
| R6 | **F10 rompe el tablero** si el endpoint de config falla | baja | medio | `intervaloDeSync` devuelve **45 000** ante `undefined`, `0`, negativo o `NaN`. Los casos 2 y 3 del test cubren los cuatro. El import de `DEFAULT_INTERVAL_MS` **se conserva** a propósito. |
| R7 | **F10 desincroniza la barra de estado** del intervalo real | media | bajo | Los **dos** consumidores (`:1110` y `:1353`) salen de la **misma** variable `intervaloSync`. El caso 4 del test de frontend lo verifica por texto fuente. **Este riesgo lo encontró la re-verificación de anclajes: el insumo no lo veía.** |
| R8 | **El ratchet `_PS1_LAG_MAX = 64` revienta al commitear** | **alta si no se lee F0** | alto | B4 lo mide y F0 lo advierte con ⚠️. **[v2, C3] Los NUEVE archivos de test nuevos del backend se registran en los DOS scripts**, con el formato de cada uno (tabla literal en F12.bis). Es trampa de **commit**: aparece al final, cuando parece que terminó. |
| R13 | **[v2, C18] `test_harness_ratchet_meta.py` ya viene rojo por un test AJENO en vuelo** (`tests/test_plan293_commit.py`, de la sesión paralela, sin registrar) | **confirmada, ya ocurrió** | medio | Baseline medido en F0: **`1 failed, 3 passed`**. El criterio es **delta con lista**: los no clasificados tienen que seguir siendo **exactamente** `['tests/test_plan293_commit.py']`. **Este plan NO registra ese archivo** — es trabajo ajeno en vuelo y esta corrida tiene prohibido tocarlo. |
| R14 | **[v2, C18] El hook de pre-commit podría correr el ratchet meta en el commit de CÓDIGO y frenarlo por el rojo ajeno** | media | **alto** | **Dato medido, no supuesto:** el commit del doc de este plan (`e3d6bbca`, solo-docs) **pasó** con el ratchet ya rojo, así que el hook **no** corre este test para cambios de sólo documentación. **Para el commit de código eso NO está verificado y no se puede asumir en ninguna dirección.** Mitigación: el implementador corre `test_harness_ratchet_meta.py` **antes** del primer commit de código; si el hook lo frena por `tests/test_plan293_commit.py`, **se para y se le pregunta al operador** (§10.6). **PROHIBIDO `--no-verify` y PROHIBIDO registrar el archivo ajeno para desbloquearse.** |
| R9 | **La sesión paralela pisa un archivo** que este plan edita | media | medio | Los archivos prohibidos están enumerados y **ninguna fase los toca**. `test_plan276_gitlab_sync.py` y `test_plan288_catalogo_vivo.py` figuran como modificados en `git status`: su criterio es **delta contra F0**, no absoluto. **Prohibido `git stash`, `reset`, `checkout --`, `clean`, `amend`, `rebase`.** El commit va con **pathspec explícito**, nunca `git add -A`. |
| R10 | **F3 declara un símbolo que no existe** y el gate queda de adorno | media | alto | La fase incluye los **comandos de verificación por `hasattr`** de cada símbolo antes de escribir el mapa, y **dos** mitades de contraste (una por dirección del assert). Si un símbolo no se puede verificar, **se borra del mapa** en vez de adivinarlo. |
| R11 | **Los rojos de fábrica del backend** se confunden con daño propio | alta | medio | **[v2, C8+C18] Son 13 tests en 6 archivos, MEDIDOS** (no los "8" del v1): `test_harness_flags_help.py` 4 · `test_error_fingerprints_catalog.py` 3 · `test_harness_flags_bounds.py` 1 · `test_plan218_capability_matrix.py` 2 · `test_harness_ratchet_meta.py` 1 · `test_plan276_gitlab_sync.py` 2. F0 los mide **archivo por archivo** antes de tocar nada. **Todos los criterios son delta**, y los dos que no discriminan se reemplazan por asserts de contenido en archivos verdes (F10.5.bis, gate delta-con-lista de F0). |
| R12 | **F4 baja el ratchet a 96 y no llega** | media | bajo | El tope se ajusta al número **medido** al implementar; el requisito real es que **baje respecto del baseline de F0**, no que sea exactamente 96. La tabla de 8 conversiones es el mínimo, y 2 de las 8 (los webhooks) son borrar evidencia falsa, que es trivial. |

---

## 7. DIFERIDOS

Cada ítem con su **iniciativa de origen** y la **justificación** del diferimiento. Ninguno se omite en silencio.

### D-1 — I3 completa: el webhook entrante de GitLab ⇒ **PLAN DEL WEBHOOK**

**Origen:** I3 del insumo (costo **L**, riesgo medio-alto). **Es el salto estructural**, no un incremento.

**Qué es:** hoy la frescura del tablero es "hasta 45 s de atraso, **y solo si hay una pestaña abierta y VISIBLE**" (`frontend/src/hooks/useTicketSync.ts:40`, `:265` — `if (respectVisibility && document.visibilityState === "hidden")`, `:284-295`), con rate-limit de 15 s en el backend (`backend/api/tickets.py:6605,6635-6649`) y guard anti-concurrencia (`:6666-6673`). I3 reemplaza el reloj del navegador por un aviso del servidor.

**El hueco está reconocido en el propio contrato:** `events.webhook.inbound` **ya existe** como clave de capacidad (`backend/services/provider_capabilities.py:47`) declarada `_a()` para GitLab. **No hay que inventar la clave: hay que llenarla.** Y F3 de este plan **ya dejó puesto el gate** que va a obligar al PLAN DEL WEBHOOK a declararla (`_CAPABILITY_TO_SYMBOL` apunta a `api.tracker_webhooks:recibir_webhook_gitlab`, que hoy no existe y por eso el gate pasa; el día que exista sin actualizar la matriz, **se pone rojo**).

**Diseño que el PLAN DEL WEBHOOK tiene que construir (queda escrito para que no se re-diseñe):**

1. `POST /api/tracker/gitlab/webhook` que valida `X-Gitlab-Token` contra un secreto **POR PROYECTO** con comparación de **tiempo constante** (`hmac.compare_digest`, **no** `==`).
2. Acepta solo `object_kind in {"issue", "note"}`.
3. **NO escribe nada por su cuenta**: dispara `sync_gitlab_tickets(project, forzar_full=False)`, que con el incremental del 292 cuesta **1 request** (verificado: `services/gitlab_sync.py:235,259-277`).
4. Responde **`202` SIEMPRE**, incluso ante payload desconocido. **Un webhook que devuelve 500 se auto-deshabilita en GitLab**, y recuperarlo exige entrar al servidor.
5. Frontend: `useTicketSync` sube a latido de respaldo (~300 s) **SOLO** cuando el backend reporta `webhook_activo: true` para ese proyecto.
6. La UI muestra URL y secreto **para copiar**; **NUNCA los genera y aplica sola** (human-in-the-loop).
7. Flag `STACKY_GITLAB_WEBHOOK_INBOUND_ENABLED` **OFF al nacer** ⇒ **excepción (B)**: abre superficie HTTP nueva **y** quién la configura en el GitLab real del operador es él. **Esa justificación va escrita en la línea de la flag.**
8. Gates: firma inválida ⇒ `401` y **CERO** llamadas al sync; firma válida + `object_kind="issue"` ⇒ **exactamente UNA** llamada con `forzar_full=False`; `object_kind` desconocido ⇒ `202` y **CERO** llamadas.
9. KPI sin credenciales: `omitidos_cerrados_desconocidos` y `bytes_recibidos`, que el 292 ya emite (`services/gitlab_sync.py:504-505`).

**Por qué se parte (la razón medida, no el costo):** I3 necesita un **secreto por proyecto** y ese campo **no existe**. Agregarlo son **seis** puntos de escritura —`backend/api/projects.py:35`, `:187`, `:467`, `:477`, `:652`, `:662`, más `backend/project_manager.py`, más los dos modales— y **dos de ellos, si se olvidan, no dan error**: el campo vuelve vacío en el siguiente `GET` y un secreto vacío convierte la comparación de tiempo constante en un `401` permanente que el operador lee como "GitLab no manda nada". **Sumar eso a las 13 fases de este plan es el patrón exacto que hundió los cinco planes de la serie 286-292: asumir una capacidad que no se verificó.**

**Estado de la dependencia dura:** **PAGADA por F9 de este plan.** El PLAN DEL WEBHOOK arranca sin deuda.

### D-2 — I6, la parte de `EpicFromBriefModal.tsx`

**Origen:** I6 del insumo. **Justificación:** `frontend/src/components/EpicFromBriefModal.tsx` **está siendo editado por la sesión paralela AHORA** (confirmado en `git status`: aparece como ` M` y hay un test nuevo `test_epic_from_brief_idempotencia.py` sin trackear). Editarlo generaría un conflicto sobre trabajo ajeno en vuelo. **Los rótulos de `:539`, `:629`, `:638` quedan para el barrido siguiente.**

### D-3 — El retiro de `EpicFromBriefModal.tsx` de la allowlist de deuda declarada

**Origen:** I6 del insumo. **Justificación:** `frontend/src/services/__tests__/plan282Censo.test.ts:64-65` lo tiene en la allowlist con el motivo escrito: "*DEUDA DECLARADA: archivo con cambios sin commitear de OTRA sesion (fix de la epica duplicada). Se rutea en el barrido siguiente, no en este plan*". **Retirarlo de la allowlist SIN rutear los rótulos pone el censo rojo.** Va junto con D-2, en el mismo plan, no antes.

### D-4 — `api/phase6.py:192` hardcodea `runtime="github_copilot"` y `project_name=None`

**Origen:** hallazgo de la re-verificación de anclajes de F9 (**no estaba en el insumo**). **Justificación:** `resolve_run_selection(runtime="github_copilot", project_name=None)` significa que el webhook de CI corre el DebugAgent **siempre** con Copilot, ignorando la selección de runtime del proyecto. Es una **asimetría de paridad preexistente**. Arreglarlo exige un test de los tres runtimes sobre ese camino, que es alcance propio. **F9 lo declara y lo excluye del gate de paridad de F12 con el motivo escrito, en vez de excluirlo en silencio.**

### D-5 — `sync_min_interval_sec` y `stale_threshold_sec` siguen leyendo `os.environ`

**Origen:** I5 del insumo (alcance ampliado). **Justificación:** `backend/api/tickets.py:6779-6780` lee las dos de `os.environ`, igual que hacía la del intervalo. Convertirlas son **dos flags más con sus nueve guardianes cada una** (18 puntos de escritura), y ninguna de las dos tiene una recomendación medida detrás como la del 292 para el intervalo. **Valor/costo desfavorable en este plan.**

### D-6 — La evidencia de las **~96** entradas de la matriz que siguen ancladas por línea

**Origen:** I4d del insumo. **Justificación:** son 96 después de F4 y el ratchet **solo baja**. Convertirlas todas en una fase exige resolver 96 símbolos correctos y sería rojo de fábrica masivo. **El ratchet las convierte en deuda visible que cada plan siguiente puede bajar un poco.**

---

## 8. Fuera de scope — la PODA, escrita como DECISIONES TOMADAS

**Estos once puntos NO se proponen. Si el implementador los "descubre" y los agrega, es un DEFECTO del trabajo, no una mejora.** Cada uno tiene su razón medida.

1. **Daemon de sync GitLab en el backend — DESCARTADO.** El plan 292 ya lo descartó con tres motivos medidos; `backend/app.py:641` prohíbe threads nuevos **por escrito** ("*NO agregar threads nuevos*") y el patrón es `MaintenanceTask` (`backend/services/maintenance.py:17-42`); y el webhook de D-1 lo vuelve obsoleto. **No se agrega un thread. No se agrega una `MaintenanceTask` de sync tampoco: nadie la pidió.**
2. **Bajar el intervalo de polling — DESCARTADO.** Va **al revés** del objetivo. Visibilidad (`useTicketSync.ts:265`) y backoff (`:255-256`) ya están hechos. F10 le da al operador la perilla para **subirlo**, que es la dirección correcta.
3. **Épicas nativas de GitLab — DESCARTADO.** Exigen licencia **Premium** del operador. El fallback Free ya existe (`services/gitlab_deep_links.py:104-152`). La matriz lo declara `partial` con el motivo escrito (`provider_capabilities.py:261-264`).
4. **Renombrar `ado_id` / `ado_state` / `ado_url` — DESCARTADO por tres planes (276, 277, 282).** El costo es migrar la base **viva** del operador. **No se toca ni una columna.**
5. **Migrar filas con `tracker_type` mal poblado — DESCARTADO, fuera de TODA la serie 281.** Toca la base viva. `tracker_efectivo_de_ticket` (`services/project_context.py:206`) ya neutraliza el síntoma. **F9 escribe `tracker_type` en las filas NUEVAS que crea; no migra ninguna existente.**
6. **Llevar PM / Sprint Board / User Stats a GitLab — DESCARTADO.** `backend/api/pm.py` es ADO-only con **diez** guards, y GitLab **no tiene el modelo de datos** (iteraciones, area paths, capacidad). El gate `TABS_SOLO_ADO` (`frontend/src/lib/tabsPorTracker.ts:14`) **ya es la respuesta correcta**.
7. **Cerrar el fail-open de `tabDisponible`** (`frontend/src/lib/tabsPorTracker.ts:43`) — **DESCARTADO.** Mataría el deep link. Es decisión documentada en `:32-36`.
8. **Un segundo compositor de deep links en el frontend — DESCARTADO.** **[v2, C7]** `frontend/src/utils/trackerUrls.ts:43-52` compone **solo** ADO y devuelve `null` **a propósito**: solo el backend conoce el `base_url` real del GitLab del proyecto. **La ruta del v1 (`frontend/src/lib/trackerUrls.ts`) NO EXISTE**: el archivo vive en `utils/`, no en `lib/`, confirmado dos veces — por el árbol del repo y por `frontend/src/services/__tests__/plan282Censo.test.ts:78`, que lo lista como `"utils/trackerUrls.ts"` dentro de `NUNCA_ALLOWLISTEABLES`.
9. **Remontar `JerarquiaLocalControl` / `PublicarEtiquetasGitLab` — DESCARTADO.** **[v2, C7]** `frontend/src/__tests__/plan288SuperficieClasificacion.test.ts:24-27,37-38,71-74` **EXIGE que NO estén montados**. Montarlos pone ese test rojo. **La ruta del v1 (`frontend/src/services/__tests__/…`) NO EXISTE**: el archivo está en `frontend/src/__tests__/`, un nivel arriba.

> **[v2, C7] Por qué estas dos rutas eran BLOQUEANTES y no erratas.** Las dos sostienen una decisión de "no construyas esto". Un modelo menor que va a verificar la restricción abre la ruta, no encuentra el archivo, y tiene dos salidas malas: concluir que la restricción ya no aplica (y construir lo prohibido), o inventar el contenido del archivo. Es el mismo mecanismo que hundió a los cinco planes de la serie 286-292: **el supuesto de capacidad**, acá en su forma negativa — dar por existente un gate ajeno sin abrirlo.
10. **Encender por código `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED`, `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` o `STACKY_AUTOCOMMIT_REDACT_ENABLED` — DESCARTADO.** Las tres **escriben en el GitLab REAL del operador** ⇒ **excepción (B)** ⇒ **se le PREGUNTA**. Van en §10 como pendientes suyos. **Mencionarlas sí; encenderlas nunca.**
11. **Reescribir `gitlab_setup_check` para que use `GitLabClient` — DESCARTADO.** Las tres razones del docstring `:7-12` siguen siendo correctas y están citadas íntegras en F5. **El arreglo pasa el bundle SIN reintroducir el cliente.**

---

## 9. Glosario, orden de implementación y DoD

### Glosario

| Término | Significado en este plan |
|---|---|
| **Mitad de contraste** | El output **ROJO** que un gate tiene que producir **antes** del código. Un gate que no se vio fallar es un adorno. |
| **Delta** | Criterio relativo al baseline de F0, no absoluto. Obligatorio porque el backend tiene **13 rojos de fábrica medidos en 6 archivos** ([v2, C8]). |
| **Delta con lista** | **[v2, C18]** Variante para un archivo cuyo rojo es AJENO y en vuelo: no alcanza con "mismo conteo", hay que exigir que **el conjunto de items que fallan sea el mismo**. Es lo que impide que un rojo propio entre tapado por uno ajeno. Se usa en el gate de `test_harness_ratchet_meta.py`. |
| **Guardián que no discrimina** | **[v2, C6]** Un test que ya está rojo por deuda ajena y por lo tanto sale **igual** con el cableado puesto y sin él. `test_harness_flags_bounds.py` y `test_harness_flags_help.py` lo son hoy. **Un criterio de conteo sobre ellos no es un criterio**: el assert se muda a un archivo verde y se hace **por contenido**. |
| **Ratchet** | Un tope numérico que **solo puede bajar** (F4) o una brecha que **solo puede cerrarse** (los dos scripts del arnés). |
| **Perilla fantasma** | Config publicada por un endpoint que **ningún** consumidor lee (`ticket_sync_interval_ms` antes de F10). Se detecta censando **por referencia**, no por quién llama al endpoint. |
| **Excepción (A)** | Quema tokens en **reposo**: loop, daemon, barrido, polling, prefetch o inyección de contexto que llama a un modelo sin que el operador pida nada. **Ninguna fase de este plan cae acá.** |
| **Excepción (B)** | Escribe en un sistema **real** del operador, destruye datos o le saca la decisión. **Ninguna fase de este plan cae acá.** |
| **`kind`** | Clasificación semántica de un fallo de la API de GitLab: `auth`, `not_found`, `rate_limited`, `server`, `tls`, `network`. Los 4 primeros nacen del status HTTP (`_kind_for_status`); `tls` y `network` se asignan en los `except` de `_request`. |
| **Terna** | `(stacky_project_name, tracker_type, external_id)` — la **única** clave única de `tickets` (`models.py:77-83`). `ado_id` **no** lo es. |
| **G1..G8** | Los gotchas del insumo, todos re-verificados y citados en la fase que los respeta. |

### Orden de implementación (un commit por fase, sin `push`)

```
F0  →  medir y anotar                                (sin commit propio)
F1  →  feat(plan-295): F1 - se borra el dead code de gitlabProfileModel
F2  →  fix(plan-295): F2 - la matriz deja de mentir en incremental y clamp
F3  →  test(plan-295): F3 - el gate anti-mentira cubre las transversales
F4  →  refactor(plan-295): F4 - ratchet de evidencias por simbolo
F5  →  fix(plan-295): F5 - la sonda habla el TLS del proyecto y distingue el cert de la red
F6  →  fix(plan-295): F6 - un fallo de GitLab deja de ser un 500 unexpected
F7  →  feat(plan-295): F7 - GitLab tiene su propio circuit breaker
F8  →  fix(plan-295): F8 - el breaker se consulta despues de saber que tracker es
F9  →  fix(plan-295): F9 - los webhooks machean por proyecto, no por ado_id
F10 →  feat(plan-295): F10 - el intervalo de sync pasa a ser del operador
F11 →  fix(plan-295): F11 - los rotulos de dos pantallas dejan de decir Feature y Done
F12 →  test(plan-295): F12 - paridad de los tres runtimes, docs y no-regresion
```

**Reglas de commit, no negociables:**
- **Pathspec EXPLÍCITO siempre.** `git commit -- "<ruta>" "<ruta>"`. **Nunca `git add -A`**: hay una sesión paralela viva y le robaría el trabajo.
- **`git commit -m` va ANTES del `--`.** Después del `--` todo es pathspec.
- Un archivo **untracked** necesita `git add -- "<ruta>"` primero.
- Si el mensaje lleva backticks, usar **`git commit -F <archivo>`** (hubo corrupción por sustitución de comando).
- **PROHIBIDO** `git stash`, `reset`, `checkout -- <ruta>`, `clean`, `amend`, `rebase`, `push`. **El árbol está sucio con trabajo ajeno: no se limpia.**
- **PROHIBIDO `--no-verify`.** Si un hook falla, se investiga.

### Definition of Done

- [ ] **F0** medido y anotado: B1..B6 con números reales + baseline de los 7 archivos + baseline de `tsc --noEmit`.
- [ ] Las **12** fases con su commit propio, en orden.
- [ ] Los **9** archivos de test nuevos del backend, verdes con el conteo declarado.
- [ ] Los **4** archivos de test nuevos del frontend, verdes.
- [ ] **[v2, C3]** Los **9** archivos de test nuevos **del backend** registrados en **`run_harness_tests.sh` Y `run_harness_tests.ps1`** (la tabla literal de F12.bis), y `test_plan259_ratchet_script_parity.py` **verde** (brecha `solo_en_sh` = **64**, el máximo).
- [ ] **[v2, C18]** `test_harness_ratchet_meta.py` con **delta cero** contra el baseline medido (`1 failed, 3 passed`) y la lista de no clasificados conteniendo **sólo** `tests/test_plan293_commit.py` — **cero** `test_plan295_*`.
- [ ] Las **12** mitades de contraste **ejecutadas, con el output pegado** en este documento, y los parches **revertidos** (`git diff` limpio).
- [ ] **[v2, C3+C18]** Los **11** archivos ajenos de no-regresión con **delta cero contra el baseline MEDIDO de F0** (no "verdes"): `test_plan218_capability_matrix.py` **de `2 failed, 8 passed` a `10 passed`** (mejora declarada, F2+F2a) · `test_plan259_setup_guide_api.py` 27 · `test_plan259_setup_guide_data.py` 14 · `test_plan259_ratchet_script_parity.py` 12 · `test_plan276_gitlab_sync.py` `2 failed, 19 passed` · `test_p7_sync_endpoints.py` 3 · `test_harness_flags.py` 59 (+2 con las booleanas ON) · `test_harness_flags_bounds.py` `1 failed, 17 passed` · `test_harness_flags_help.py` `4 failed, 4 passed` · `test_error_fingerprints_catalog.py` `3 failed, 5 passed` · `test_harness_ratchet_meta.py` `1 failed, 3 passed` **con delta CON LISTA**.
- [ ] `npx tsc --noEmit` sin errores nuevos.
- [ ] Los **9** KPI de §1 medidos con su comando y anotados.
- [ ] Las **3** flags nuevas con sus guardianes completos: `config.py`, `FlagSpec`, `_CATEGORY_KEYS`, `PLAIN_HELP`, y —**solo las booleanas ON**— `_CURATED_DEFAULTS_ON`; la numérica **con `_FROZEN_BOUNDS` y SIN `default=`**.
- [ ] `docs/_roadmap/PARIDAD_ADO_GITLAB.md` regenerado y `test_doc_de_paridad_esta_sincronizado` verde.
- [ ] `docs/sistema/` actualizado con los 3 párrafos de F12.
- [ ] La tabla "Estado de implementación por fase" de este documento completa, con commit y evidencia por fase.
- [ ] **Sin `push`.** El push lo decide el operador.

---

## 10. PENDIENTES DEL OPERADOR

Nada de esta lista lo decide el plan. Todo requiere que el operador diga sí.

### 10.1 — Las tres flags que escriben en su GitLab REAL (excepción B — se PREGUNTA, no se decide)

| Flag | Qué hace si la enciende | Por qué es su decisión |
|---|---|---|
| `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED` | Escribe etiquetas `type::*` y de jerarquía **en los issues reales** de su GitLab | Modifica datos en el servidor de la empresa. Las etiquetas quedan visibles para todo su equipo. |
| `STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED` | Hace que el commit del agente **cree la rama** que necesita en el repo real | Crea ramas en el repositorio de la empresa. |
| `STACKY_AUTOCOMMIT_REDACT_ENABLED` | Modifica el contenido que se commitea (redacción de secretos) | Cambia lo que queda escrito en el historial del repo. |

**Las tres están OFF y este plan NO las toca.** Se listan para que sepa que existen y que la decisión es suya.

### 10.2 — Los humos con credenciales reales (no se pueden medir sin su GitLab)

1. **F5 — la sonda contra el GitLab interno.** Abrir la guía de configuración de un proyecto GitLab **con CA interna**, pegar el certificado de la empresa en "Certificado de la empresa", apretar **"Verificar ahora"**, y confirmar que:
   - `chk-tls` da **`ok`** (hoy `chk-instancia` da `fail` con "*No se pudo llegar a esa dirección*" **mientras el sync funciona**);
   - los otros cuatro chequeos dejan de estar en `unknown`.
   **Es el único humo que valida el objetivo de F5.** Si sale mal, el detalle de `chk-tls` va a nombrar la pieza.
2. **F6/F7 — un PAT vencido de verdad.** Con un token de GitLab revocado a propósito, disparar un sync y confirmar que el tablero muestra el mensaje **"El token venció, fue revocado o está mal copiado: renovalo…"** en vez de un error genérico, y que un segundo sync inmediato **no golpea la red** (el breaker abrió).
3. **F9 — un webhook de CI real.** Si tiene webhooks de CI configurados apuntando a Stacky, confirmar que siguen funcionando después de F9. **El caso 11 del test cubre el escenario ADO histórico, pero un humo real es la única prueba definitiva.**

### 10.3 — La decisión de una sola línea que vale un 75 % del tráfico

El plan 292 **midió** que subir el intervalo de auto-sync de **45 s a 180 s** baja el tráfico contra su GitLab un **75 %**, sin perder novedades (siguen llegando solas, solo un poco más tarde).

**Después de F10 esto es una perilla del panel de flags:** `STACKY_TICKET_SYNC_INTERVAL_MS`, de `45000` a `180000`. **El plan NO lo cambia por usted**: el default sigue en 45 000, porque el tráfico contra el servidor de su empresa es su decisión. La perilla viene con su ayuda llana y su ejemplo.

### 10.4 — Las tres flags nuevas de este plan, para su información

Las tres nacen **ON** y **ninguna** escribe en su GitLab ni consume tokens en reposo. No tiene que hacer nada. Si alguna vez quiere volver atrás:

| Flag | Apagarla vuelve a… |
|---|---|
| `STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED` | los errores de GitLab salen como `500 unexpected` (conducta de hoy) y GitLab no consulta breaker |
| `STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED` | el webhook de CI devuelve `404` en vez de crear un ticket placeholder |
| `STACKY_TICKET_SYNC_INTERVAL_MS` | es un número, no un interruptor: `45000` es el valor histórico |

### 10.6 — [v2, C18] Un test de la sesión paralela tiene el ratchet del arnés en rojo

**Qué pasa.** `backend/tests/test_harness_ratchet_meta.py` está **rojo** (`1 failed, 3 passed`) porque existe `backend/tests/test_plan293_commit.py` y no está registrado ni en `run_harness_tests.sh` / `.ps1` ni en `harness_ratchet_allowlist.txt`. Ese archivo es de la **sesión paralela** (su plan 293, el tablero de Git guiado).

**Qué NO hace este plan.** No lo registra ni lo mueve. Es trabajo ajeno en vuelo, y sólo su autor sabe si el test pasa aislado (condición para entrar al `.sh`) o si va al allowlist con motivo escrito. Este plan sólo garantiza **no empeorarlo**: después de sus 14 fases, la lista de no clasificados tiene que seguir teniendo **exactamente** ese archivo.

**Lo que puede necesitar su decisión.** El commit del **documento** de este plan (`e3d6bbca`, sólo docs) **pasó** con el ratchet ya rojo, así que el hook no corre este test para cambios de sólo documentación. **Para los commits de CÓDIGO eso no está verificado.** Si al commitear F1 el hook frena por `tests/test_plan293_commit.py`:

- **PROHIBIDO `--no-verify`.**
- **PROHIBIDO registrar el archivo ajeno** para desbloquearse.
- El implementador **se detiene y le pregunta**. Las opciones son suyas: (a) pedirle a la sesión paralela que lo registre, (b) autorizar explícitamente que este plan lo registre, o (c) esperar a que esa rama cierre.

### 10.5 — Aprobación del corte de alcance

Este plan **difiere I3 (el webhook entrante) al PLAN DEL WEBHOOK** y paga su dependencia dura (la corrección de D5) en F9. La justificación completa está en §4 y §D-1. **Si prefiere que I3 entre acá, hay que agregar 6 fases más y construir primero el campo de secreto por proyecto (6 puntos de escritura, 2 de los cuales fallan en silencio).** La recomendación es el corte propuesto.

---

**FIN DEL PLAN 295.**

