# Plan 283 — El calendario de reuniones: de la transcripción a los pendientes accionables

**Estado:** **v1 -> v2 — MEJORADO tras crítica adversarial, 2026-08-01. Veredicto de v1: RECHAZADO (5 bloqueantes).**
**IMPLEMENTADO 2026-08-01 — F0..F10, commits `fe08faea` (backend F0..F8) y `0f0fc395` (frontend F9 + ratchets F10), sin push.**
Medido, no afirmado: los 12 archivos en una sola invocación dan **`99 passed, 0 failed`** (el número exacto del DoD #13), `npx tsc --noEmit` da 0 errores, y el lag entre los dos ratchets queda en **64 == `_PS1_LAG_MAX`**.
**Desvíos declarados (3):** (1) el namespace de la API del frontend NO va en `api/endpoints.ts` sino en `api/meetings.ts` propio — ese archivo tiene cambios sin commitear de una sesión paralela, y se aplica el mismo criterio que D6 aplica a `api/tickets.py`; (2) `api/__init__.py` se editó UNA sola vez (las 2 líneas de F7 y las 2 de F8 juntas) para minimizar el roce en un archivo compartido; (3) los baselines de §7 que el plan predecía como `70 passed` y `16 passed` estaban **ya rojos por causas ajenas** al empezar (`1 failed, 69 passed` y `1 failed, 15 passed`) — el criterio aplicado fue **delta cero contra lo MEDIDO**, no contra la foto del plan.
**Pendiente: solo los 3 smokes manuales S1, S2 y S3** (exigen backend levantado y un tenant real de Microsoft).
**Rama:** `docs/plan-279` (los planes 281 y 282 se escribieron en paralelo en otras sesiones)
✅ **Colisión de número RESUELTA por el operador, 2026-08-01:** este plan nació como `280` (pinneado) pero una sesión paralela commiteó `280_PLAN_EL_DESENLACE_*.md` con el mismo número. El operador dictaminó que **el commiteado conserva el 280** y **este documento se renumera a 283** (primer libre real). Renombrado de `280_PLAN_CALENDARIO_*.md` a `283_PLAN_CALENDARIO_*.md`; el contenido no cambió.
**Origen:** pedido textual del operador (2026-08-01):

> *"Calendario de reuniones conectado con teams y que pueda pasarle u obtener transcripciones y entregue minutas y datos utiles de cada reunion, pendientes obtenidos, fechas etc"*

**Tipo:** capacidad NUEVA (eje nuevo del producto). No toca pipelines, GitLab, jerarquía ni publicación de épicas.

---

## CHANGELOG v1 -> v2

Todos los hallazgos salieron de **abrir los archivos** y **ejecutar los gates**, no de leer el v1.

| # | Sev. | Qué estaba mal en v1 | Cómo se resolvió en v2 |
|---|------|----------------------|------------------------|
| **C1** | **BLOQ** | El criterio de F1 y el DoD #11 exigían **`75 passed`** = "70 medidos + 5 casos parametrizados que aportan las 5 keys". **Aritmética falsa:** `--collect-only` da 56 + 5 + 9 = **70**, y los 3 archivos tienen **cero `parametrize`** — iteran `for spec in FLAG_REGISTRY` **dentro** de un único test. 5 flags nuevas suman **0** casos. El criterio era insatisfacible, y el plan ordenaba "si no da 75, se investiga" ⇒ caza de un fantasma, o peor, inventar 5 tests para llegar al número. | Criterio de F1 = **`70 passed`, delta cero** (las 7 patas evitan que las 5 flags **rompan** los tests congelados). El gate que **sí discrimina** es un archivo nuevo: `tests/test_plan283_flags.py`, **7 casos, uno por pata**. |
| **C2** | **BLOQ** | Un tab nuevo rompe `shellNav.test.ts`, que el v1 **no lista entre las "11 patas… todas verificadas"** ni corre en el criterio de F9. `shellNav.test.ts:11-15` congela `ALL_TABS` con los 18 tabs **literales** y assertea `Object.keys(TAB_META).sort() == ALL_TABS` (`:18-20`) y `SHELL_NAV_GROUPS.flatMap(tabs).sort() == ALL_TABS` (`:23-26`). El plan podía declararse VERDE dejando **2 rojos que él mismo causó**. | **Pata 12** nueva (editar `ALL_TABS` y el título "los 18 tabs"→19), y el criterio de F9 ahora **corre los 3 archivos de shell** con baseline medido. |
| **C3** | **BLOQ** | La pata 4 escribía `iconName: "…"` — puntos suspensivos literales — asumiendo que el ícono ya existiría. **`shellIcons.ts:8-12` tiene exactamente 18 íconos y los 18 están tomados**: no hay ninguno libre. `shellIconsCoverage.test.ts` convierte un `iconName` inexistente en rojo determinista. | **Pata 13** nueva: importar `CalendarDays` de `lucide-react` en `shellIcons.ts` y agregarlo a `ICON_BY_NAME`. `iconName: "CalendarDays"` **literal**. |
| **C4** | **BLOQ** | F0 caso 6 era un `xfail(strict=False)`. Un `xfail` no-estricto que **pasa** reporta **`xpassed`**, no `passed` ⇒ el criterio `6 passed` era **insatisfacible** (daría `5 passed, 1 xpassed`), y arrastraba el criterio de F2. Además congelaba **80**, un número volátil de un archivo compartido. | Caso 6 reescrito como test normal que **mide sin congelar**: assertea el **invariante** ("ninguna de las 5 keys del plan está entre las que faltan en `PLAIN_HELP`") y **reporta** el número por `print`. Criterio `6 passed` real. |
| **C5** | **BLOQ** | §11 ponía **F7 antes que F5**, pero `/api/meetings/calendar` (F7) llama `meetings_source.list_upcoming()` (F5) y el **caso 6 de F7** lo assertea ⇒ "10 passed" insatisfacible en esa posición. Y el argumento que sostenía el orden ("que el valor llegue antes que el riesgo R1") es **falso**: los 10 casos de F4 y los 8 de F5 corren con **transporte falso, cero red** — R1 no se materializa al implementar, solo en el smoke S1. | Orden nuevo: F0, F1, F2, F3, F6, **F4, F5**, F7, F9, F8, F10. §11 explica por qué R1 es riesgo de **runtime**, no de implementación. |
| **C6** | IMP | El gate K4 era **tautológico**: corría por `ast` sobre `services/meeting_minutes.py`, archivo que **el propio plan escribe**, para verificar que no importe algo que nadie iba a importar. Pasa por construcción y seguiría pasando aunque la paridad se rompiera. (La *afirmación* del v1 sí es correcta y la verifiqué: `copilot_bridge.py:157` despacha por `config.LLM_BACKEND`, eje distinto del runtime de agente.) | K4 en dos partes: (a) el `ast` se mantiene como higiene; (b) **[ADICIÓN ARQUITECTO A2]** `tests/test_plan283_backend_parity.py` corre `build_minutes_payload` **una vez por cada uno de los 5 valores** de `LLM_BACKEND` y exige salida idéntica. La paridad pasa de argumento a **medición**. |
| **C7** | IMP | El criterio de la ayuda ("`4 failed, 4 passed`", delta cero) **no discrimina**: los 4 rojos son de **conjunto**; 5 entradas nuevas con jerga prohibida o sin `"Si "` **no suben el conteo**, se suman a la lista del test que ya falla. El v1 lo intuía y proponía filtrar las reglas a las 5 keys — **en prosa, sin archivo, sin comando, sin criterio**. | `tests/test_plan283_help_limpio.py`, **4 casos** que aplican las 4 reglas **solo a las 5 keys**. Criterio `4 passed`. Las reglas van **literales y medidas** en la pata 4. |
| **C8** | IMP | La pata 5 enunciaba la biyección como `spec.default is True`. **El predicado real es `default_is_known(spec)` = `spec.default is not None`** (`harness_flags.py:6527-6529`). Con la regla del v1, un modelo menor concluye que `default="common"` es seguro ("no es `True`") y **rompe `test_default_known_only_for_curated`**, uno de los 70 verdes. Y dejaba una incoherencia de producto: el panel mostraría el default del tenant como `""` mientras `config.py` resolvía `"common"` ⇒ **el panel miente**. | Predicado literal en la pata 5. Y `config.py` defaultea el tenant a `""`; `"common"` vive como `DEFAULT_TENANT` en `graph_client.py` y se resuelve cuando el valor está vacío ⇒ hint de UI y default efectivo **coinciden**, y ninguna `str` declara `default=`. |
| **C9** | IMP | La pata 7 afirmaba "si se implementa F1 sola, el test de wiring queda rojo hasta F7. **Declarado a propósito**". **Falso.** `tests/test_flag_wiring.py:24-33` dice textualmente: *"NOTA: harness_profiles.py y **config.py SÍ cuentan**"*. La pata 1 (los 5 `os.getenv` en `config.py`) ya satisface la pata 7. | Corregido. Refuerza C1: F1 sola deja las 3 suites en **70 verdes**, sin rojo diferido. |
| **C10** | IMP | K3 se medía con "F9 caso 4: el modelo expone las 4 acciones sin `nav_path`". **Ese caso no existe**: los 8 casos de `meetingsModel.test.ts` son agrupar / sin-fecha / 4× etiqueta / puedePublicar / resumenCalendario. KPI sin gate. | `meetingsModel.ts` expone `accionesDisponibles()` y F9 gana el **caso 9** que lo mide. K3 apunta ahí. |
| **C11** | IMP | `GraphClient` **sin `timeout`** en ninguna llamada, y ni una mención. Un Graph colgado cuelga el request de Flask — y es **peor acá que en GitLab**, porque D8 hace `POST /transcript` **importar y destilar en el mismo request síncrono**. Molde del repo: `gitlab_client.py:301` usa `timeout=20`. | `GRAPH_TIMEOUT_S = 20` en todas las llamadas + caso de test (transporte falso que lanza `requests.Timeout` → `GraphApiError(kind="timeout")`, y `list_upcoming` → `estado="error"`). |
| **C12** | IMP | F10.2 mandaba "leer el enum del schema real" **sin darlo**, y su criterio ("el conteo no puede subir de 5") **no discrimina**: una huella mal formada se suma a los **mismos 3 tests que ya fallan**. | El enum y los 9 campos obligatorios van **literales y medidos** (`tests/test_error_fingerprints_catalog.py:18-19`). Criterio nuevo: **por `id`**, la huella nueva no aparece en el mensaje de fallo de ninguno de los 5 rojos (assert sobre el **mensaje**, no sobre el conteo). |
| **C13** | IMP | §3.7 afirmaba que con la flag apagada la app queda **"byte-idéntica"**. Falso: F9 edita `type Tab`, `TAB_PATHS`, `ShellTab`, `TAB_META`, `SHELL_NAV_GROUPS`, `shellIcons.ts` y 5 puntos de `App.tsx`. Además "byte-idéntico" es **término de arte** de este repo (el guard de `shellIntegration.test.ts:7`) y usarlo mal invita a escribir un test imposible. | Reformulado a **"funcionalmente inerte"**, con el gate honesto que ya existía (F10.3 caso 6). |
| **C14** | IMP | El molde de `rawGet` que daba el v1 (`endpoints.ts:5593-5598`) es **un `api.get`** (`runCoverage`) — exactamente el wrapper que el plan **prohíbe** para `/calendar`, `/graph/probe`, `draft` y `confirm`. Un modelo menor copiando el molde citado hace **lo contrario** de la regla dura. Y la regla escrita no está en `:3436-3442` (ahí vive `export const Health`). | Moldes reales: `rawGet` en `:3340`, `:3361`, `:3453`; `rawPost` en `:3462`, `:3786`, `:4030`. La regla está en **`:3444-3445`**. |
| **C15** | IMP | El v1 hablaba de "la descripción" del work item sin nombrar el campo. `TrackerItem` (`tracker_provider.py:32-39`) exige **`description_html`**: `item_type, title, description_html, labels, assignee, parent_id, fields`. Texto plano rompe el markup, y F8 caso 9 asserteaba sobre un campo sin nombre. | Campos enumerados; la descripción se arma como **HTML**. |
| **C16** | MEN | **13 anclajes desfasados** (ninguno inventado, todos existen a ±1-4 líneas o apuntan a un comentario en vez de al molde). | Tabla completa de "Anclajes verificados" más abajo; corregidos en el cuerpo. |
| **C17** | MEN | Congelaba **conteos absolutos de archivos COMPARTIDOS** (787/723, 447, 367, 80, 70). Una sesión paralela los movió **dentro de la misma hora** (`.sh` 787→788, `.ps1` 723→724): el plan nació con fecha de vencimiento. | Los criterios anclan en el **invariante** (`lag == _PS1_LAG_MAX`), no en la foto. Los absolutos quedan marcados **VOLÁTILES + fecha**. |
| **C18** | MEN | F4 decía "se usa el `verify` por defecto de `requests`". **Falso**: `backend/app.py:26` llama `truststore.inject_into_ssl()`, **global al proceso**. Para Graph (CA pública) funciona —y además es lo que salva la inspección TLS corporativa— pero hay que declararlo. | Declarado, con la prohibición de `truststore.extract_from_ssl()` que ya está escrita en `tls_openssl_context.py:11`. |
| **C19** | MEN | Ambigüedad para modelos menores: `iconName: "…"`; `to_dict(self) -> dict: ...` con F2 caso 4 pidiendo "las claves del contrato" **sin enumerarlas**; "cue-ids numéricos **o UUID**" sin regex; la tabla de F7 dice `POST` y el caso 5 dice "`PUT` de transcripción"; §9.9 "Prohibido por §3.8, **F1 y F1**"; F10.1 dice "los **8** archivos" y lista **9**. | Todo literal: claves enumeradas, regex dada, verbo unificado en `POST`, conteos corregidos. |
| **C20** | MEN | `MeetingActionItem.meeting_id` sin `ForeignKey`, pero F2 caso 6 pedía "no deja pendientes huérfanos" ⇒ probaba una **disciplina de código**, no una garantía del esquema. | Declarado honestamente: SQLite no aplica FK sin `PRAGMA foreign_keys=ON`, así que el borrado en cascada es **responsabilidad del código** y el caso 6 lo dice. |

**Añadido en v2:** **[ADICIÓN ARQUITECTO A1]** — anclaje de atribución (D9, §5) y **[ADICIÓN ARQUITECTO A2]** — matriz de paridad de `LLM_BACKEND` (C6).

---

## ANCLAJES VERIFICADOS (abriendo el archivo, 2026-08-01)

**OK = la línea citada contiene lo que el plan dice.** Verificados los ~60 anclajes del v1.

| Anclaje del v1 | Estado |
|---|---|
| `db.py:218` `class Base`, `:250` molde import, `:265` `create_all`, `:389` `_rebuild_tickets_table_if_needed`, `:464` `DROP TABLE tickets`, `:178` `run_with_retry`, `:181-184` docstring, `:223-263` bloque de imports | **OK** (los 8) |
| `db.py:498` `session_scope()` | **DESFASADO → `:499`** (`:498` es el `@contextmanager`) |
| `copilot_bridge.py:145` `invoke` | **OK** |
| `copilot_bridge.py:157-186` ramas de `LLM_BACKEND` | **DESFASADO → `:157-185`** (`:185` es el `raise NotImplementedError`) |
| `config.py:81` `LLM_BACKEND` default `vscode_bridge` | **OK** |
| `config.py:1395-1397` molde OFF | **OK** (ojo: usa `.lower()` **sin** `.strip()`) |
| `config.py:2473-2475` molde ON | **DESFASADO → `:2472-2474`** (la sentencia completa) |
| `local_insights.py:46-53` `HITL_RULES`, `:58` `truncate_middle`, `:115`, `:146`, `:158`, `:291` | **OK** (los 6, exactos) |
| `egress_policies.py:64-93` `_DETECTORS`, `:126` `check` | **OK** (el rango 64-93 es exacto) |
| `confirm_token.py:39` `issue_token`, `:55` `consume_token`, `:75` `expire_token_for_tests` | **OK** (los 3) |
| `secrets_store.py:191`, `:258`, `:181` `write_json_file`, `:277-279` (reescritura al migrar) | **OK** (los 4, exactos) |
| `tracker_provider.py:45` `TrackerConfigError`, `:48-52` `TrackerApiError` (**`status` POSICIONAL**, confirmado en `:49`), `:125` `get_tracker_provider` | **OK** (los 3) |
| `gitlab_provider.py:387` `create_item` | **OK** |
| `gitlab_client.py:103` `_kind_for_status`, `:125` clase, `:131-137` ctor, `:143-146` razón `REQUESTS_CA_BUNDLE`, `:175` `Session()`, `:179-183` adapter, `:210-217` aviso | **OK** (los 7) |
| `gitlab_client.py:127` "no hace red en `__init__`" | **DESFASADO → `:128`** (`:127` es línea en blanco) |
| `ado_sync.py:53` `_parse_iso`, `:57` cuerpo | **OK** (exactos) |
| `local_diagnostics.py:217` `_probe_gitlab`, `:252-255` razón de los sub-veredictos | **OK** (y el comentario dice **CUATRO**, como afirma el plan) |
| `api/evolution.py:47-54` `/health` | **OK** (rango exacto) |
| `api/incidents.py:55` único `request.files` | **OK** |
| `api/__init__.py:90` molde import | **OK** |
| `api/__init__.py:124` molde `register_blueprint` | **DESFASADO → `:125-127`** (`:124` es un **comentario**) |
| `api/__init__.py:178` regla R6 "NUNCA declarar /api" | **DESFASADO → `:181`** |
| `api/__init__.py:179-181` razón del gate dentro de la ruta | **DESFASADO → `:182-184`** |
| `harness_flags.py:20-41` `FlagSpec`, `:29` `default`, `:120` `_CATEGORY_KEYS`, `:437` `capacidades_optin`, `:552` cierre, `:554-555` aviso, `:6484-6497` molde, `:6497` cierre de `FLAG_REGISTRY`, `:6569` `validate_requires_graph` | **OK** (los 9, exactos) |
| `test_harness_flags.py:467` / `:999` `_CURATED_DEFAULTS_ON`, `:1074-1083` biyección | **OK** (pero el predicado es `default_is_known`, ver C8) |
| `test_flag_wiring.py:52-61` consumidor real | **OK** |
| `test_flag_wiring.py:18-23` `RESERVED_KEYS` | **DESFASADO → `:17-22`** |
| `test_harness_flags_help.py:17-20` denylist, `:44-53` bounds, `:56-60` `"Si "` | **OK** (los 3, exactos) |
| `test_harness_flags_requires.py:120` apertura | **OK** |
| `test_harness_flags_requires.py:355` cierre | **DESFASADO → `:354`** |
| `test_harness_flags_restart_required.py:233-245` | **OK** |
| `test_plan259_ratchet_script_parity.py:46` `_PS1_LAG_MAX = 64` | **OK** |
| `test_harness_ratchet_meta.py:66` `_ALLOWLIST_MAX = 197` | **OK** |
| `run_harness_tests.sh:20` apertura, `.ps1:13` apertura | **OK** (ambas) |
| `run_harness_tests.sh:1020` cierre | **DESFASADO → `:1024`** (y **volátil**, ver C17) |
| `run_harness_tests.ps1:937` cierre | **DESFASADO → `:941`** (y **volátil**) |
| `routes.ts:5-9` `type Tab` (18 tabs), `:15-22` `TAB_PATHS` | **OK** (ambos, exactos) |
| `shellNav.ts:3-4` aviso de drift, `:5-9` `ShellTab`, `:16` `TAB_META`, `:44` grupo `trabajo`, `:68` `computeVisibleTabs` | **OK** (los 5, exactos) |
| `App.tsx:21` import, `:122` estado, `:186` probe, `:344` redirect, `:346` deps, `:361` gate, `:404-406` render | **OK** (los 7, exactos) |
| `App.tsx:457-464` nav v1 legacy | **OK** (bloque del botón de Incidencias). **Anclaje que faltaba: el `<nav>` v1 abre en `:442`.** |
| `client.ts:51` `rawPost`, `:100` `rawGet` | **OK** (ambos) |
| `endpoints.ts:1026` molde `api.get` | **DESFASADO → `:1024-1025`** (`:1026` es un comentario) |
| `endpoints.ts:3436-3442` regla "`api.*` lanza" | **DESFASADO → `:3444-3445`** |
| `endpoints.ts:5593-5598` molde `rawGet` | **INCORRECTO: es un `api.get`.** Ver C14 |
| `flagHealth.ts:34` `probeFlagHealth`; `gateState.ts:22`/`:31`/`:48` | **OK** (los 4) |
| `models.py:522-552` molde `AgentPromptVersion` | **OK** (la clase abre en `:522`) |
| `project_manager.py:689` `resolve_gitlab_auth_path` | **OK** |
| `test_pipeline_copilot_api.py:16` cabecera `DATABASE_URL` | **OK** |
| `provider_contract.py:326` único hit de `login.microsoftonline.com` | **OK** |
| `SprintBoardPage.tsx:108` vista huérfana | **OK** |
| `EpicFromBriefModal.tsx:524` placeholder "notas de reunión" | **DESFASADO → `:529`** |
| `requirements.txt` 14 líneas, `requests` `:8`, `keyring` `:11`, `alembic` `:4` sin `alembic.ini` | **OK**. **Dato que el v1 omitió: `truststore==0.10.4` en `:9`** (ver C18) |

---

## 0. Resumen para el implementador apurado

Se construye un módulo **Reuniones** con cuatro capas separadas por contratos, cada una testeable sola:

```
  FUENTE            →  PARSEO          →  DESTILADO         →  SALIDA
  (de dónde viene)     (puro, sin red)    (LLM, 1 tiro)        (HITL)

  manual: pegar        WebVTT / texto     minuta + pendientes  borrador de ticket
  graph:  Teams        → turnos           DOS LLAVES:          → publicar (flag OFF)
                       → hablantes        1. cita literal      → assignee SOLO si
                                          2. dueño verificado     la atribución se probó
```

**Las dos llaves del anti-alucinación (v2, [ADICIÓN A1] / D9).** Un pendiente publicable tiene que probar
**dos** cosas distintas, y el v1 solo pedía la primera:
1. **¿Se dijo?** — la `cita` es subcadena **literal** de la transcripción. Si no, **se descarta** (D4).
2. **¿Quién?** — el `responsable` es **un hablante real** de esa reunión. Si no, **no se descarta pero no se
   asigna**: `assignee=None` y el ítem queda marcado `sin_hablante` (D9).
Sin la llave 2, un modelo puede citar textualmente *"lo vemos el viernes"* y atribuírselo a alguien que no
estuvo — la cita es válida, la atribución es inventada, y D4 **no lo ve**.

**La decisión que hace este plan implementable:** el valor **no depende de Microsoft Graph**.
El camino manual (pegar el `.vtt` que Teams deja descargar) funciona el día 1, sin credenciales, sin
permisos de administrador de Teams y sin red. Graph es **aditivo**: si el tenant del operador no lo
permite, el módulo sigue entregando minutas y pendientes. El operador pidió literalmente *"pasarle
**u** obtener"*: son dos caminos, y este plan los implementa detrás del **mismo contrato**.

---

## 1. Objetivo y KPI

Hoy Stacky **no tiene nada** de calendario ni de reuniones. Verificado, no inferido:

| Afirmación | Comando / evidencia | Resultado |
|---|---|---|
| No hay cliente Microsoft Graph, ni MSAL, ni OAuth de Microsoft | `grep -rniE "graph\.microsoft\|login\.microsoftonline\|msal\|onlineMeetings\|callTranscripts" --include=*.py --include=*.ts` (excluyendo venvs) | **1 hit, y es ajeno**: `backend/tests/contract/provider_contract.py:326` usa `login.microsoftonline.com` como URL de un fixture de redirección. **Cero código de Graph.** |
| No existe pantalla ni ruta de calendario/agenda/reuniones | `type Tab` en `frontend/src/services/routes.ts:5-9` (18 tabs) y `TAB_PATHS` en `:15-22` | Ninguno es de reuniones. La única vista temporal, `frontend/src/pages/SprintBoardPage.tsx:108`, está **huérfana**: no figura en `Tab`, ni en `TAB_PATHS`, ni se importa en `App.tsx`. |
| No hay dependencia de OAuth ni de parseo de subtítulos | `backend/requirements.txt` (14 líneas) | Hay `requests==2.32.3` y `keyring==25.6.0`. **Este plan no agrega ni una dependencia.** |

### KPI binarios

| # | KPI | Hoy (medido) | Meta | Cómo se mide (comando/test) |
|---|-----|--------------|------|------------------------------|
| **K1** | Reuniones que llegan de transcripción a minuta dentro de Stacky | **0** (el módulo no existe) | **≥ 1**, por los **dos** caminos de fuente | F10 caso 1 (manual) y F10 caso 2 (graph con transporte falso) |
| **K2** | Pendientes publicables **sin cita literal** en la transcripción | N/A | **0, por contrato** | F6 caso 6: un pendiente cuya `cita` NO es subcadena literal de la transcripción normalizada se descarta. **Con guard positivo primero** (F6 caso 5): el mismo test prueba que un pendiente CON cita válida SÍ sobrevive. |
| **K3** | Pantallas que el operador visita para ir de una transcripción a un borrador de ticket | **imposible hoy** | **1** (`reuniones`) | **v2/C10** — F9 **caso 9**: `accionesDisponibles()` devuelve las 4 acciones del ciclo y **ninguna** trae `navPath` a otra sección. *(El v1 apuntaba a "F9 caso 4", que era un caso de `etiquetaEstadoMinuta`: KPI sin gate.)* |
| **K4** | Que el destilado funcione **idéntico** con los 3 runtimes | N/A | **5/5 backends idénticos** + 0 imports de runners | **v2/C6 — dos partes.** (a) higiene, F6 caso 9: por `ast`, `services/meeting_minutes.py` no importa `codex_cli_runner`, `claude_code_cli_runner` ni `agent_runner`. (b) **la medición de verdad, [ADICIÓN A2]**: `tests/test_plan283_backend_parity.py` corre `build_minutes_payload` una vez por cada valor de `LLM_BACKEND` (`mock, vscode_bridge, copilot, claude_cli, local_llm`) y exige salida **idéntica**. *(v2: el v1 remitía a un "§3.5" que no contiene eso; la discusión de paridad vive en **F6 → "Impacto por runtime"**.)* |
| **K8** | **[ADICIÓN A1]** Pendientes publicados con un responsable que **nadie dijo en la reunión** | N/A | **0 auto-asignados**: si el responsable no es un hablante de la transcripción, `assignee` va vacío y el ítem se marca `atribucion="sin_hablante"` | F6 casos 11-12 y F8 caso 10 (`create_item` recibe `assignee=None`) |
| **K5** | Transcripciones que salen a un modelo sin pasar por el gate de egress | N/A | **0, con test** | F6 caso 8: `build_minutes_payload()` llama a `egress_policies.check()` **antes** de armar el prompt, y con `allowed=False` devuelve `blocked` sin invocar el bridge |
| **K6** | Escrituras al tracker real sin confirmación explícita del operador | N/A | **0, con test** | F8 caso 4: sin `confirm_token` válido el endpoint devuelve **409** y `create_item()` no se llama (espiado) |
| **K7** | Turnos de transcripción perdidos en silencio al truncar | N/A | **0**: todo truncado se declara | F3 caso 8: `normalize_transcript()` devuelve `turnos_totales` y `turnos_incluidos`; si difieren, la minuta lo dice en `aviso_truncado` |

---

## 2. Por qué ahora — el gap que cierra

Los planes 276-279 cerraron el eje **tracker/pipelines** (GitLab self-hosted, jerarquía, publicación de
épica, copiloto de pipelines). Todos comparten una forma: **el trabajo ya estaba en un sistema y Stacky
lo orquestaba**. Este plan ataca el eje contrario: **el trabajo que todavía no está en ningún sistema**.

Una reunión de una hora produce decisiones, compromisos y fechas que hoy viven en la cabeza del operador
o en un `.vtt` que Teams deja descargar y nadie vuelve a abrir. Ese es el único insumo del ciclo de Stacky
que **no tiene puerta de entrada**: hay puerta para tickets (`api/tickets.py`), para incidencias
(`api/incidents.py:55`, el único `request.files` del repo), para briefs (`EpicFromBriefModal.tsx`) — y
para reuniones, ninguna.

El plan 278 dejó además un precedente directo: `EpicFromBriefModal.tsx:524` tiene un placeholder que dice
literalmente **"notas de reunión"**. O sea: el producto ya asume que las notas de reunión son materia prima
de una épica, pero nunca construyó de dónde salen.

---

## 3. Principios y guardarraíles

1. **El valor no depende de Microsoft.** El camino manual es el principal y funciona sin credenciales,
   sin permisos de admin y sin red. Graph es aditivo (§5, D1).
2. **Anti-alucinación por construcción, no por prompt.** Un pendiente sin **cita literal** verificable
   contra la transcripción **se descarta en código**, no se le pide al modelo que se porte bien (D4).
3. **Human-in-the-loop innegociable.** Nada se publica en el tracker del operador sin `confirm_token`
   explícito (`services/confirm_token.py:39` / `:55`) **y** flag encendida a mano.
4. **La transcripción es PII.** Antes de mandarla a cualquier modelo pasa por
   `egress_policies.check()` (`services/egress_policies.py:126`), que ya existe y ya detecta email/DNI/CUIT
   (`_DETECTORS`, `:64-93`). Este plan no inventa un motor de privacidad: usa el que hay (D5).
5. **Cero dependencias nuevas.** OAuth device-code y WebVTT se resuelven con `requests` y `re`, que ya están.
6. **Mono-operador sin auth real.** Cero RBAC. Un 403/404 significa flag apagada, nunca "sin permiso".
7. **Backward-compatible.** Con `STACKY_MEETINGS_ENABLED` apagada, la app queda **funcionalmente inerte**:
   el tab no se pinta (`computeVisibleTabs`, `shellNav.ts:68`) y las rutas devuelven 404.
   ⚠ **v2/C13 — NO es "byte-idéntica", y decirlo así sería mentira.** F9 edita `type Tab`, `TAB_PATHS`,
   `ShellTab`, `TAB_META`, `SHELL_NAV_GROUPS`, `shellIcons.ts` y 5 puntos de `App.tsx`. "Byte-idéntico" es
   **término de arte de este repo** (el guard de `shellIntegration.test.ts:7` sobre la rama OFF de la nav v1);
   usarlo mal invita a escribir un test imposible. El gate honesto de esta propiedad es **F10.3 caso 6**.
8. **No se toca `api/tickets.py`.** Ese archivo tiene 8.000+ líneas y **cambios sin commitear del
   operador** en este árbol. La publicación de este plan usa el puerto `get_tracker_provider()`
   (`services/tracker_provider.py:125`), no el endpoint de tickets. Ver D6.

---

## 4. Lo que ya existe y se REUSA (nada de esto se reimplementa)

Todo verificado abriendo el archivo.

| Capacidad | Símbolo exacto | Archivo:línea | Cómo lo usa este plan |
|---|---|---|---|
| Llamada a un modelo, 1 tiro, agnóstica del runtime | `invoke(*, agent_type, system, user, on_log, execution_id=None, model=None, ...) -> BridgeResponse` | `backend/copilot_bridge.py:145` | Destilado de la minuta (F6) |
| Patrón de prompt + parseo defensivo de JSON | `build_insight_prompt` / `_strip_fences` / `parse_insight_response` | `services/local_insights.py:115`, `:146`, `:158` | Molde literal de F6 |
| Truncado que declara lo que recorta | `truncate_middle(text, head, tail)` | `services/local_insights.py:58` | Cap de transcripción (F3) |
| Regla HITL inyectada al system prompt | `HITL_RULES` | `services/local_insights.py:46-53` | Se concatena igual en F6 |
| Gate de egress de datos sensibles | `check(*, project, model, context_text) -> EgressDecision` | `services/egress_policies.py:126` | K5 (F6) |
| Confirmación de dos pasos | `issue_token(action, payload, ttl_s)` / `consume_token(action, token)` | `services/confirm_token.py:39` / `:55` | K6 (F8) |
| Secreto cifrado con DPAPI + JSON | `set_encrypted_secret(payload, field, value, *, format_field=None, ...)` / `read_secret_from_file(path, field, *, format_field=None, ...)` | `services/secrets_store.py:191` / `:258` | Refresh token de Graph (F4) |
| Sesión de BD + retry por lock | `session_scope()` / `run_with_retry(fn, *, attempts=3, ...)` | `backend/db.py:499` / `:178` — **v2/C16: era `:498`, ahí está el `@contextmanager`** | F2, F7, F8 |
| Creación de work item en el tracker activo | `get_tracker_provider(project)` → `.create_item(item: TrackerItem)` | `services/tracker_provider.py:125` → `services/gitlab_provider.py:387` | F8 |
| **Contrato del work item** — **v2/C15**: los campos son **exactamente** `item_type, title, **description_html**, labels, assignee, parent_id, fields`. **La descripción es HTML, no texto plano.** | `@dataclass class TrackerItem` | `services/tracker_provider.py:32-39` | F8 |
| **Timeout de HTTP saliente** — **v2/C11**: el repo pone timeout explícito en cada llamada | `timeout=20` | `services/gitlab_client.py:301` | Molde de `GRAPH_TIMEOUT_S` (F4) |
| Excepción tipada de API externa | `TrackerApiError(status, message, *, kind)` — **`status` es POSICIONAL** | `services/tracker_provider.py:48-52` | Molde de `GraphApiError` (F4) |
| Normalizador de fecha ISO → naive UTC | `_parse_iso(value)` | `services/ado_sync.py:53` (cuerpo en `:57`) | F3/F4: Graph devuelve ISO con `Z` |
| Cliente HTTP con `requests.Session` propia | `class GitLabClient` | `services/gitlab_client.py:125` (ctor `:131-137`) | Molde de `GraphClient` (F4) |
| Sonda de conexión con sub-veredictos (anti falso verde) | `_probe_gitlab(project_name, tracker) -> dict` | `services/local_diagnostics.py:217` | Molde de la sonda de Graph (F5) |
| `/health` que responde 200 SIEMPRE para el gating de nav | patrón `@bp.get("/health")` | `api/evolution.py:47-54` | F7 |
| Gate de tab en el frontend (3 estados) | `probeFlagHealth` / `gateStateFromVerdict` / `isGateOn` / `shouldRedirectAway` | `frontend/src/utils/flagHealth.ts:34`, `services/gateState.ts:31`/`:48`/`:22` | F9 |

---

## 5. Decisiones de diseño D1..D8

### D1 — Dos fuentes, un solo contrato; el manual es el principal

- **Problema.** Obtener transcripciones de Teams por Graph exige permisos que un tenant corporativo
  puede negar. Si el módulo depende de eso, puede quedar en cero valor.
- **Decisión.** `services/meetings_source.py` define **un** dataclass `MeetingRecord` y **dos**
  implementaciones que lo producen: `ManualSource` y `GraphSource`. Las capas de arriba (parseo,
  destilado, salida) **no saben** de dónde vino el dato.
- **Alternativas rechazadas.** (a) Solo Graph — rechazada: el requerimiento dice *"pasarle **u** obtener"*.
  (b) Solo manual — rechazada: el requerimiento dice *"conectado con teams"*.
- **Riesgo.** Duplicar esfuerzo. Aceptado: el contrato común lo acota a un dataclass y dos funciones.

### D2 — Device code flow, no client credentials

- **Problema.** El flujo `client_credentials` (app-only) para leer transcripciones exige que un
  administrador de Teams cree una *application access policy*. Eso es trabajo del operador y de un tercero.
- **Decisión.** OAuth **device code** (cliente público, sin secreto de aplicación): el operador abre una
  URL, escribe un código, y Stacky guarda el `refresh_token` cifrado con DPAPI
  (`secrets_store.set_encrypted_secret`, `:191`). Encaja con mono-operador y no necesita secreto de app.
- **⚠ SUPUESTO NO VERIFICADO CONTRA EL REPO.** Los `scope` exactos y si el tenant del operador habilita
  device-code son hechos de la plataforma Microsoft, **no del código de Stacky**. El plan **no puede**
  verificarlos con `grep`. Por eso D1 existe: si este supuesto falla, se pierde F4/F5-graph y **nada más**.
  El implementador debe tratar los scopes de §6.F4 como *valor por defecto editable*, no como verdad.

### D3 — El parseo es puro y determinista; el LLM solo destila

- **Problema.** Si el modelo también tuviera que separar hablantes y timestamps, cada error de parseo
  se volvería una alucinación imposible de auditar.
- **Decisión.** `services/transcript_parser.py` **no importa `copilot_bridge` ni `requests`** (gate por
  `ast` en F3 caso 9). Convierte WebVTT o texto plano de Teams en `list[TranscriptTurn]`. Determinista,
  100% testeable sin red y sin modelo.

### D4 — Cita obligatoria: el anti-alucinación es código, no prompt

- **Problema.** Un pendiente inventado ("Juan se comprometió a migrar la base el viernes") es peor que
  ningún pendiente: el operador actúa sobre él.
- **Decisión.** El contrato de salida exige que **cada** pendiente traiga `cita`. En
  `parse_minutes_response()` se verifica que `cita` sea **subcadena literal** del texto normalizado
  (comparación exacta sobre la cadena que se le mandó al modelo). El que no cumple **se descarta** y se
  cuenta en `descartados_sin_cita`.
- **Por qué no basta el prompt.** Pedirlo en el prompt es una preferencia; verificarlo en código es un
  invariante. K2 lo mide.
- **Guard positivo obligatorio (gotcha de la casa).** Un assert de ausencia puede pasar por accidente
  —por ejemplo si el parser devuelve lista vacía por un bug—. Por eso **el mismo test** (F6 caso 5)
  afirma primero que un pendiente con cita válida SÍ sobrevive.

### D5 — La transcripción pasa por el gate de egress que ya existe

- **Problema.** Una transcripción tiene nombres, emails, a veces datos de clientes. Mandarla a un modelo
  de un tercero (`LLM_BACKEND=copilot`) es una decisión, no un detalle.
- **Decisión.** `build_minutes_payload()` llama a `egress_policies.check(project=..., model=...,
  context_text=<transcripción normalizada>)` **antes** de armar el prompt. Si `allowed=False`, devuelve
  `{"estado": "blocked", "clases": [...]}` y **no invoca el bridge**. La UI muestra qué clase de dato la
  bloqueó y el operador decide (crear una política o editar el texto).
- **Nota honesta.** Los detectores actuales (`_DETECTORS`, `egress_policies.py:64-93`) reconocen email,
  DNI, CUIT, CBU, tarjeta, "producción", jerga regulatoria y secretos. **No** reconocen "nombre y apellido
  de persona". Este plan **no** agrega detectores (fuera de scope, §11): reusa lo que hay y lo declara.

### D6 — La publicación NO toca `api/tickets.py`

- **Problema.** `api/tickets.py` tiene ~8.000 líneas y **está modificado sin commitear** en este árbol
  (fixes vivos de GitLab del operador). Un plan que lo edite crea conflicto con trabajo real.
- **Decisión.** F8 crea `api/meetings_publish.py` con su propio blueprint y usa
  `get_tracker_provider(project).create_item(...)`. Cero ediciones en `api/tickets.py`.
- **Gate.** F8 caso 8: por `ast`, `api/meetings_publish.py` no importa nada de `api.tickets`.

### D7 — Sin polling, sin daemon, sin barrido

- **Problema.** Un sincronizador de calendario que corre solo cae en la **categoría (A)** de la regla de
  flags (quema recursos en reposo) y obligaría a que la flag nazca OFF.
- **Decisión.** El sync de Graph es **on-demand**: solo cuando el operador aprieta "Actualizar" o abre la
  pantalla. **No se registra ningún hilo, ningún `_loop`, ningún `register_post_hook`.**
- **Gate.** F5 caso 7: por `ast`, ningún módulo de este plan contiene `threading.Thread`, `Timer`,
  `schedule` ni una función cuyo nombre termine en `_loop`.
- **Consecuencia buscada:** las 4 flags de lectura pueden nacer **ON** sin violar la regla.

### D8 — La generación de minuta es automática al importar, pero cancelable

- **Problema.** Si el operador tiene que apretar "generar minuta" después de importar, el módulo agrega
  trabajo en vez de sacarlo.
- **Decisión.** `POST /api/meetings/<id>/transcript` importa **y** destila en el mismo request
  (síncrono, sin cola). Si el bridge falla, la reunión queda guardada con `minutes_state="failed"` y el
  botón "Reintentar" aparece. La transcripción **nunca** se pierde por un fallo del modelo.
- **Por qué no es categoría (A):** no gasta nada en reposo — gasta **solo** cuando el operador acaba de
  pegar una transcripción, que es un acto explícito suyo.

### D9 — [ADICIÓN ARQUITECTO A1] Anclaje de atribución: la cita no alcanza, el pendiente necesita DUEÑO

- **El agujero que deja D4.** D4 exige que la `cita` sea subcadena literal de la transcripción. Eso prueba
  que **la frase se dijo**. **No prueba quién se comprometió.** Un modelo puede citar textualmente
  *"lo vemos el viernes"* y atribuírselo a **"Marcela"**, que no habló en esa reunión — o que no existe.
  El resultado es peor que un pendiente sin responsable: es un pendiente **con responsable equivocado**,
  y si además F8 lo autocompleta como `assignee`, Stacky le asigna trabajo real a una persona real por
  una alucinación. D4, tal como está en v1, **no lo detecta**: la cita es válida.
- **Decisión.** La verificación pasa a tener **dos llaves, igual que la publicación**:
  1. **¿Se dijo?** → `cita` es subcadena literal de `texto_fuente` (D4). Si no, **se descarta**.
  2. **¿Quién?** → `responsable` se coteja contra el **conjunto de hablantes reales** de la transcripción,
     que el parser **ya tiene** (`TranscriptTurn.speaker`) y hoy tira a la basura.
- **Contrato.** `normalize_transcript()` suma `hablantes: tuple[str, ...]` (distintos, en orden de
  aparición, sin el vacío). `parse_minutes_response(..., hablantes=...)` calcula, por pendiente:

  | `atribucion` | Cuándo | Qué hace el sistema |
  |---|---|---|
  | `"confirmada"` | `responsable` matchea un hablante (comparación por **tokens**, `casefold`, ignorando orden: `"Juan Pérez"` ≡ `"Perez, Juan"`) | La UI lo muestra normal. F8 **puede** proponer `assignee` |
  | `"sin_hablante"` | `responsable` no vacío y **ningún** hablante matchea | Badge de advertencia. F8 manda **`assignee=None`** (K8) |
  | `"sin_responsable"` | `responsable` es `null` | Normal: no todo pendiente tiene dueño |

- **El ítem NO se descarta.** Descartarlo sería peor: el compromiso probablemente existe, lo que falla es
  la atribución. Se **degrada y se marca**. Es el mismo criterio que `descartados_sin_cita`: contar y
  mostrar, nunca borrar en silencio.
- **Por qué es barato.** Es una **función pura** de ~20 líneas sobre datos que el parser ya produce. Cero
  dependencias, cero red, cero llamadas extra al modelo, cero trabajo del operador, cero impacto en los
  3 runtimes. Se testea entera sin backend.
- **Riel que respeta.** Human-in-the-loop: el sistema **nunca adivina de quién es el trabajo**. Cuando no
  puede probarlo, deja el campo vacío y se lo pregunta al operador — que es exactamente lo que el operador
  ya hace hoy a mano, sin ayuda.

---

## 6. Fases

> **Comando base de tests (todo el plan).** Desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`:
> ```
> $env:DATABASE_URL="sqlite:///:memory:"; .\venv\Scripts\python.exe -m pytest tests/<archivo> -q
> ```
> El venv que funciona es **`backend\venv` (Python 3.11.9)**, verificado. Existe también
> `backend\.venv` (3.13.5); **no usar ese**. `DATABASE_URL` en memoria es **obligatorio**: sin él, un
> pytest suelto escribe en la base viva del operador.
> **Prohibido correr `pytest tests` entero** como veredicto: la suite completa tiene contaminación
> cruzada conocida. Se corre **por archivo**.

---

### F0 — Censo de baseline (nace parcialmente ROJO, a propósito)

**Objetivo.** Congelar por medición el estado "antes", para que ningún criterio posterior pueda
declararse verde contra una foto imaginaria.

**Archivo a crear:** `backend/tests/test_plan283_baseline.py`

**Casos (6):**

| # | Caso | Estado al escribirlo | Cierra en |
|---|------|----------------------|-----------|
| 1 | `test_cero_codigo_graph_en_produccion`: recorre `backend/**/*.py` y `frontend/src/**/*.{ts,tsx}` (excluyendo `backend/tests/`, `venv`, `.venv`, `node_modules`) y afirma que **ninguno** contiene `graph.microsoft.com`. | **VERDE hoy**; se **INVIERTE** en F4 a "exactamente 1 archivo: `services/graph_client.py`" | F4 |
| 2 | `test_no_existe_tab_reuniones`: `TAB_PATHS` de `frontend/src/services/routes.ts` no tiene la clave `reuniones`. | **VERDE hoy**; se invierte en F9 | F9 |
| 3 | `test_las_5_flags_del_plan_no_existen`: ninguna de las 5 keys de F1 está en `FLAG_REGISTRY`. | **VERDE hoy**; se invierte en F1 | F1 |
| 4 | `test_no_existen_las_tablas`: `Base.metadata.tables` no tiene `meetings` ni `meeting_action_items`. | **VERDE hoy**; se invierte en F2 | F2 |
| 5 | `test_las_5_keys_no_estan_en_ningun_congelado`: ninguna de las 5 keys aparece en `_CURATED_DEFAULTS_ON`, `_REQUIRES_MAP_FROZEN`, `RESERVED_KEYS` ni `_EXPECTED_RESTART_REQUIRED`. **v2/C1+C17 — reemplaza al `test_baseline_flags_suites_verdes` del v1**, que lanzaba un **subproceso pytest anidado de 22 s** para congelar un **70** que otra sesión puede mover en cualquier momento. Un baseline se **mide al empezar**, no se hornea en un test. | **VERDE hoy**; se invierte parcialmente en F1 | F1 |
| 6 | `test_las_5_keys_no_agravan_el_rojo_ajeno_de_ayuda`: **v2/C4** — calcula `faltantes = {s.key for s in FLAG_REGISTRY} - set(PLAIN_HELP)`. **Guard positivo PRIMERO, en el mismo test:** `assert len(faltantes) > 0` (prueba que el cálculo funciona y que el rojo ajeno existe de verdad; sin esto el assert siguiente pasaría por accidente si `faltantes` fuera vacío por un bug). **Después:** `assert not (KEYS_280 & faltantes)`. Y un `print(len(faltantes))` que deja el número en el log **sin congelarlo** (hoy 80, **volátil**). | **VERDE hoy** (vacuo pero con guard); **discrimina desde F1**: si F1 registra las 5 flags sin escribir su `PLAIN_HELP`, este test se pone **rojo** | — |

⚠ **v2/C4 — por qué se eliminó el `xfail`.** El v1 marcaba el caso 6 como `xfail(strict=False)`. Un `xfail`
no estricto que **pasa** se reporta como **`xpassed`**, no como `passed`: el comando habría dado
`5 passed, 1 xpassed` y el criterio **`6 passed` era literalmente inalcanzable**, arrastrando además el
criterio de F2. **Prohibido usar `xfail` en cualquier test de este plan.**

**Criterio de aceptación BINARIO (F0):** `pytest tests/test_plan283_baseline.py -q` → **`6 passed`**
(seis, sin `xpassed`, sin `xfailed`, sin `skipped` en el resumen).

**Flag:** ninguna (es un test). **Trabajo del operador: ninguno.**
**Impacto por runtime:** ninguno (no corre en runtime de agente).

---

### F1 — Las 5 flags, con sus 7 patas cada una

**Objetivo.** Registrar la configuración del módulo de forma que el operador la vea y la toque **por UI**,
sin editar archivos.

**Las 5 entradas** (todas van en `services/harness_flags.py`, dentro de `FLAG_REGISTRY`, que hoy cierra
en `:6497` y tiene **447** entradas medidas):

| key | type | default | Justificación del default |
|-----|------|---------|---------------------------|
| `STACKY_MEETINGS_ENABLED` | `bool` | **`True`** | Lectura y escritura **en la base local de Stacky**. No gasta en reposo (D7: cero daemons) y no escribe en ningún sistema del operador. **No aplica ninguna excepción ⇒ nace ON.** |
| `STACKY_MEETINGS_GRAPH_ENABLED` | `bool` | **`True`** | Conector de Graph **solo lectura** y **on-demand** (D7). Si faltan credenciales, la UI deshabilita el botón con un hint; **"prerequisito no garantizado" NO es excepción válida** ⇒ nace ON. |
| `STACKY_MEETINGS_PUBLISH_ENABLED` | `bool` | **`False`** | **EXCEPCIÓN (B) — escribe en un sistema REAL del operador.** Crea work items en su Azure DevOps o GitLab llamando a `create_item()` (`services/gitlab_provider.py:387`). Es exactamente el precedente de `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`: **ver/proponer va ON, escribir de verdad va OFF.** |
| `STACKY_MEETINGS_GRAPH_TENANT` | `str` | **`""`** | **v2/C8 — cambiado.** Valor de configuración, no interruptor. Va por UI. **El default `"common"` NO vive acá**: vive como `DEFAULT_TENANT = "common"` en `graph_client.py` y se aplica cuando el valor está vacío. Razón: una flag `str` **no puede** declarar `default=` en su `FlagSpec` (rompe la biyección, pata 5), así que el panel mostraría `""` mientras `config.py` resolvía `"common"` ⇒ **el panel mentiría sobre el default**. Con `""` en ambos lados, el panel dice la verdad. |
| `STACKY_MEETINGS_GRAPH_CLIENT_ID` | `str` | `""` | Idem. **El secreto NO va acá**: el `refresh_token` se guarda cifrado (F4). |

**Las 7 patas de CADA flag** (esto es un **bloque atómico**: dejar una sin hacer pone rojo un test ajeno):

1. **`backend/config.py`** — el `os.getenv` con el default **efectivo**. Es el único default real; el
   `default=` del `FlagSpec` es solo hint de UI (`harness_flags.py:29`). Moldes literales:
   ON → `config.py:2473-2475`; OFF → `config.py:1395-1397`.
   ```python
   # backend/config.py — dentro de class Config
   STACKY_MEETINGS_ENABLED: bool = os.getenv(
       "STACKY_MEETINGS_ENABLED", "true"
   ).strip().lower() in ("1", "true", "yes")
   STACKY_MEETINGS_GRAPH_ENABLED: bool = os.getenv(
       "STACKY_MEETINGS_GRAPH_ENABLED", "true"
   ).strip().lower() in ("1", "true", "yes")
   STACKY_MEETINGS_PUBLISH_ENABLED: bool = os.getenv(
       "STACKY_MEETINGS_PUBLISH_ENABLED", "false"
   ).strip().lower() in ("1", "true", "yes")
   STACKY_MEETINGS_GRAPH_TENANT: str = os.getenv("STACKY_MEETINGS_GRAPH_TENANT", "")   # v2/C8: "" y NO "common"
   STACKY_MEETINGS_GRAPH_CLIENT_ID: str = os.getenv("STACKY_MEETINGS_GRAPH_CLIENT_ID", "")
   ```
   ⚠ El molde ON real es **`config.py:2472-2474`** (la sentencia completa; el v1 citaba `:2473-2475`, que
   arranca a mitad de una y termina a mitad de la siguiente). El molde OFF real es `config.py:1395-1397`,
   y **usa `.lower()` sin `.strip()`** — este plan usa `.strip().lower()` a propósito, como el molde ON.
2. **`services/harness_flags.py` → `_CATEGORY_KEYS`** (abre en `:120`, cierra en `:552`). Las 5 keys van
   en la categoría **`capacidades_optin`** (abre en `:437`). El aviso está escrito en el propio archivo,
   `:554-555`: *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS` o el test
   `test_every_registry_flag_is_categorized` rompe CI a propósito"*. Caer en `otros` **rompe** el test.
3. **`services/harness_flags.py` → `FLAG_REGISTRY`**. Molde literal: la entrada
   `STACKY_CONSOLE_AUDIT_LOG_ENABLED` en `:6484-6497`. Las 4 flags hijas llevan
   `requires="STACKY_MEETINGS_ENABLED"`; la madre **no lleva `requires`** (regla R4: profundidad máxima 1,
   `validate_requires_graph()` en `harness_flags.py:6569`).
4. **`services/harness_flags_help.py` → `PLAIN_HELP`** (abre `:25`, cierra `:2296`). Molde literal:
   `:2235-2240`. **Reglas duras del test `tests/test_harness_flags_help.py`:**
   - `what` entre 10 y 200 caracteres; `on_effect` ≤ 240; `off_effect` ≤ 240; `example` ≤ 300 (`:44-53`).
   - `on_effect` y `off_effect` **deben empezar literalmente con `"Si "`** (`:56-60`) — con espacio, **sin tilde**.
   - Denylist de jerga CONGELADA (`:17-20`), palabra completa y **plural incluido**:
     `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime`.
     **Prohibido** citar keys `SCREAMING_SNAKE` y referencias `F<n>`.
     ⚠ Esto obliga a redactar la ayuda de `STACKY_MEETINGS_GRAPH_CLIENT_ID` **sin decir "token"**: hay que
     decir *"la credencial"* o *"el código de aplicación"*.
5. **`tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON`** (abre `:467`, cierra `:999`). Las **2**
   flags que declaran `default=True` (`STACKY_MEETINGS_ENABLED`, `STACKY_MEETINGS_GRAPH_ENABLED`) van acá
   con su comentario.
   ⚠ **v2/C8 — el predicado real, copiado del código, no parafraseado.** El test
   `test_default_known_only_for_curated` (`:1074-1083`) exige `{s.key for s in FLAG_REGISTRY if
   default_is_known(s)} == _CURATED_DEFAULTS_ON`, y **`default_is_known(spec)` es literalmente
   `return spec.default is not None`** (`services/harness_flags.py:6527-6529`). **NO es `spec.default is
   True`**, como decía el v1. Consecuencia dura: **declarar `default="common"` en una flag `str` la mete en
   `known_keys` y ROMPE ese test**, que hoy es uno de los 70 verdes. Por eso las 2 flags `str` de este plan
   **no declaran `default=` en ningún caso** (ver C8 en la tabla de la flag `..._GRAPH_TENANT`), y **no** van
   a `_CURATED_DEFAULTS_ON`. `declared_default()` (`:6522-6524`) les devolverá el type-zero `""`, que es
   exactamente lo que `config.py` resuelve.
6. **`tests/test_harness_flags_requires.py` → `_REQUIRES_MAP_FROZEN`** (abre `:120`, cierra **`:354`** —
   v2/C16, el v1 decía `:355`). **4 aristas** nuevas, exactas: cada flag hija → `"STACKY_MEETINGS_ENABLED"`.
   Las 4 pasan R1-R4 de `validate_requires_graph()` (`harness_flags.py:6569`): el master existe, es `bool`,
   no hay auto-referencia y el master **no** declara `requires` (profundidad 1). **Verificado: R2 mira el
   tipo del MASTER, no el de la hija** ⇒ que 2 hijas sean `str` es legal.
7. **Consumidor real en código productivo.** `tests/test_flag_wiring.py:52-61` exige que la key aparezca
   como **literal** en `backend/**/*.py` o en `frontend/src/**/*.{ts,tsx}`. Sin consumidor hay que marcarla
   `reserved=True`, y `RESERVED_KEYS` (**`:17-22`** — v2/C16, el v1 decía `:18-23`) es un **set congelado
   de 4** ⇒ **no es escapatoria**.
   ⚠ **v2/C9 — el v1 se equivocaba y sembraba un rojo fantasma.** Decía: *"si se implementa F1 sola, el
   test queda rojo hasta F7. Declarado a propósito."* **Es falso.** El docstring de `_production_corpus()`
   (`tests/test_flag_wiring.py:24-33`) dice textualmente: excluye `tests/`, `services/harness_flags.py` y
   `services/harness_flags_help.py`, y **"NOTA: harness_profiles.py y `config.py` SÍ cuentan"**. La **pata 1**
   (los 5 `os.getenv` en `config.py`) **ya satisface la pata 7**. **F1 sola deja las 3 suites en 70 verdes.**

**Prohibido (pata 8, la que NO se toca):** `backend/harness_defaults.env` es un snapshot **parcial** y los
planes lo declaran "NO tocar a mano". `tests/test_plan120_flags.py` ya está rojo por eso, y es ajeno.

**Prohibición adicional que ahorra un rojo:** ninguna de estas 5 keys puede aparecer como token en
`backend/app.py`. `tests/test_harness_flags_restart_required.py:233-245` exige que **toda** key
`STACKY_*` que aparezca en `app.py` sea `restart_required=True`. Este plan no arranca daemons (D7), así
que **no debe tocar `app.py`**.

**Tests (TDD, primero):**
```
$env:DATABASE_URL="sqlite:///:memory:"
.\venv\Scripts\python.exe -m pytest tests/test_harness_flags.py tests/test_flag_wiring.py tests/test_harness_flags_requires.py -q
```
**Criterio BINARIO (F1):** **`70 passed`** — el **mismo** número de hoy. **Delta cero.**

⚠ **v2/C1 — el v1 exigía `75 passed` y era aritmética falsa. Medido en esta corrida:**
```
tests/test_harness_flags.py            => 56 tests collected
tests/test_flag_wiring.py              =>  5 tests collected
tests/test_harness_flags_requires.py   =>  9 tests collected
                                          -----------------
                                          70, y CERO `parametrize` en los tres archivos
```
Los 3 archivos **no generan un caso por flag**: iteran `for spec in FLAG_REGISTRY` **adentro** de un único
test. Agregar 5 flags aporta **0 casos nuevos**. El número se queda en 70 para siempre.
**Qué mide realmente este criterio:** que las 5 flags **no ROMPAN** los tests congelados
(`test_default_known_only_for_curated`, `test_requires_map_is_frozen`, `test_reserved_set_is_frozen`,
`test_every_registry_flag_is_categorized`, `test_every_non_reserved_flag_is_wired`). Es un criterio de
**no-regresión**, no de cobertura — y hay que decirlo, porque un `70 passed` con 3 patas sin hacer también
da `70 passed`.

**Por eso F1 trae su PROPIO gate, que sí discrimina.**

**Archivo a crear:** `backend/tests/test_plan283_flags.py` — **7 casos, uno por pata**, sobre las 5 keys:

| # | Caso | Qué prueba |
|---|------|-----------|
| 1 | Pata 1 — las 5 keys son atributos de `Config` con el default efectivo esperado (`True, True, False, "", ""`), leído por `getattr(config.Config, key)` con el entorno limpio | El `os.getenv` existe **y** el default es el declarado |
| 2 | Pata 2 — las 5 keys están en `_CATEGORY_KEYS["capacidades_optin"]` y `categorize()` **no** devuelve `"otros"` para ninguna | Categorización |
| 3 | Pata 3 — las 5 están en `FLAG_REGISTRY`; las 3 `bool` tienen `type=="bool"`, las 2 `str` `type=="str"`; las 4 hijas tienen `requires=="STACKY_MEETINGS_ENABLED"` y la madre `requires is None`; `validate_requires_graph() == []` | Registro + grafo R1-R4 |
| 4 | Pata 4 — las 5 tienen entrada en `PLAIN_HELP` | Ayuda presente (la **calidad** la mide `test_plan283_help_limpio.py`) |
| 5 | Pata 5 — `default_is_known(spec)` es `True` **solo** para las 2 `bool` ON, y `False` para las 2 `str` y para la de publicación | La biyección de C8, probada del lado del plan |
| 6 | Pata 6 — `_REQUIRES_MAP_FROZEN` contiene las 4 aristas nuevas | Mapa congelado |
| 7 | Pata 7 — cada key aparece **literal** en `backend/config.py`, y **ninguna** aparece en `backend/app.py`. **Guard positivo primero:** el mismo test verifica que una key inventada (`STACKY_MEETINGS_KEY_QUE_NO_EXISTE`) **no** se encuentra en `config.py` — sin eso, un lector de archivo roto haría pasar el assert | Consumidor real + la prohibición de `app.py` (`test_harness_flags_restart_required.py:233-245`) |

**Criterio BINARIO adicional (F1):** `pytest tests/test_plan283_flags.py -q` → **`7 passed`**.

#### El rojo ajeno de la ayuda — v2/C7: el conteo NO discrimina

`pytest tests/test_harness_flags_help.py -q` debe seguir dando **`4 failed, 4 passed`** (medido hoy).
⚠ **Pero ese criterio solo no alcanza, y el v1 lo dejaba así.** Los 4 rojos son **de conjunto**: cada uno
acumula violaciones de **todas** las entradas en una lista y assertea `== []`. Cinco entradas nuevas con
jerga prohibida, o sin `"Si "`, o pasadas de largo **no suben el conteo de 4** — se suman a la lista del
test que **ya** falla. El v1 proponía filtrar las reglas a las 5 keys, pero **en prosa**: sin archivo, sin
comando y sin criterio binario. En este repo eso equivale a no tenerlo.

**Archivo a crear:** `backend/tests/test_plan283_help_limpio.py` — aplica las 4 reglas **solo a las 5 keys**:

| # | Regla (copiada del test real, medida) | Fuente |
|---|---|---|
| 1 | Las 5 keys tienen entrada en `PLAIN_HELP` (cobertura) | `:36-41` |
| 2 | `10 <= len(what) <= 200`; `len(on_effect) <= 240`; `len(off_effect) <= 240`; `len(example) <= 300`; ningún campo vacío | `:44-53` |
| 3 | `on_effect` y `off_effect` **empiezan con `"Si "`** — con espacio, **sin tilde** | `:56-60` |
| 4 | Ningún campo matchea `rf"\b{term}s?\b"` (case-insensitive, **plural incluido**) para los 15 términos de `JARGON_DENYLIST` (`:17-20`): `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime`; ni `_KEY_RE = r"\b[A-Z]+_[A-Z0-9_]+\b"`; ni `_PHASE_RE` (referencias `F<n>`) | `:63-76` |

⚠ **Consecuencias concretas de la regla 4 para ESTE plan** (las 3 se verificaron contra la denylist real):
- `..._GRAPH_CLIENT_ID` **no puede decir "token"** ni "tokens". Decir *"la credencial"* o *"el código de aplicación"*.
- `..._PUBLISH_ENABLED` **no puede decir "endpoint" ni "gate"**. Decir *"la ruta"* / *"el permiso"*.
- Ninguna puede decir **"runtime"**, **"backend"** ni **"frontend"**, ni citar `STACKY_MEETINGS_*`, ni nombrar `F4`.

**Criterio BINARIO:** `pytest tests/test_plan283_help_limpio.py -q` → **`4 passed`**.

**Flag que protege F1:** las 5, se auto-registran. **Trabajo del operador: ninguno.**
**Impacto por runtime:** ninguno (registro de configuración).

---

### F2 — Las dos tablas

**Objetivo.** Persistir reuniones, transcripciones, minutas y pendientes.

**Archivo a crear:** `backend/services/meetings_store.py`
**Archivo a editar:** `backend/db.py` (una sola línea, en el bloque de imports de `init_db()`)

**Modelo (molde literal: `models.py:522-552`, tabla `agent_prompt_versions`):**

```python
# backend/services/meetings_store.py
from datetime import datetime
from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from db import Base                      # db.py:218

class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)      # "manual" | "graph"
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stacky_project_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(400), nullable=False)
    organizer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # naive UTC
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    join_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_format: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "vtt"|"txt"
    minutes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes_state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("stacky_project_name", "source", "external_id",
                         name="uq_meetings_proyecto_fuente_externo"),
        Index("ix_meetings_started_at", "started_at"),
    )
    def to_dict(self) -> dict: ...     # convención: TODA tabla expone to_dict()

class MeetingActionItem(Base):
    __tablename__ = "meeting_action_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    titulo: Mapped[str] = mapped_column(String(400), nullable=False)
    responsable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_compromiso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cita: Mapped[str] = mapped_column(Text, nullable=False)     # D4: obligatoria, nunca vacía
    estado: Mapped[str] = mapped_column(String(16), nullable=False, default="propuesto")
    tracker_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_action_items_meeting", "meeting_id"),)
    def to_dict(self) -> dict: ...
```

**⚠ La única edición en `db.py`.** Sin esto, `Base.metadata.create_all(engine)` (`db.py:265`) **no ve las
tablas**. Va en el bloque de imports `# noqa: F401` de `init_db()` (`db.py:223-263`), junto al molde
`db.py:250`:
```python
    from services.meetings_store import Meeting, MeetingActionItem  # noqa: F401  (Plan 283)
```

**⚠ TRAMPA VERIFICADA — no aplica acá, pero hay que saberla.** `db.py:389`
`_rebuild_tickets_table_if_needed(conn)` reconstruye la tabla `tickets` con una lista de columnas
**hardcodeada en dos lugares** (`:405-425` y `:432-461`) y hace `DROP TABLE tickets` (`:464`). **Afecta
únicamente a `tickets`.** Este plan **no agrega columnas a `tickets`**, así que no lo toca. Si un
implementador se tienta con agregar `meeting_id` a `tickets`: **no lo haga** — el rebuild la borraría en
silencio junto con el dato del operador. El vínculo va al revés (`MeetingActionItem.external_id`).

**Archivo de test a crear:** `backend/tests/test_plan283_store.py`

**Casos (7):** 1) `init_db()` crea ambas tablas. 2) la terna única rechaza el duplicado. 3) `external_id`
nulo se permite (fuente manual). 4) `to_dict()` devuelve **exactamente** estas claves — **v2/C19, el v1
decía "las claves del contrato" sin enumerarlas**:
`Meeting` → `{id, source, external_id, stacky_project_name, subject, organizer, started_at, ended_at,
join_url, transcript_format, minutes_state, created_at, updated_at, action_items_count}`
(**`transcript_text` y `minutes_json` NO se serializan en el listado**: son grandes y `minutes_json` va por
`GET /meetings/<id>`);
`MeetingActionItem` → `{id, meeting_id, titulo, responsable, fecha_compromiso, cita, estado, atribucion,
tracker_type, external_id, created_at}`. Fechas en ISO-8601 con `Z`.
5) `cita` `nullable=False` rechaza `None`. 6) borrar una reunión borra sus pendientes. 7) `minutes_state`
por defecto es `"pending"`.

⚠ **v2/C20 — honestidad sobre el caso 6.** `MeetingActionItem.meeting_id` **no declara `ForeignKey`**, y
aunque lo declarara, **SQLite no aplica las FK sin `PRAGMA foreign_keys=ON`**, que este repo no activa. Por
lo tanto el borrado en cascada es **responsabilidad del código**, no una garantía del esquema: el caso 6
prueba que `meetings_store.delete_meeting()` borra los hijos **en la misma sesión** antes que el padre, y
el docstring del test lo dice con esas palabras. No se declara una garantía que la base no da.

**Criterio BINARIO (F2):** `pytest tests/test_plan283_store.py -q` → **`7 passed`**, y
`pytest tests/test_plan283_baseline.py -q` → **`5 passed, 1 failed`** (el caso 4 se invierte; se corrige
en el mismo commit dando `6 passed`).

**Escrituras:** usar siempre `run_with_retry` (`db.py:178`) porque toda escritura en SQLite es susceptible
a `SQLITE_LOCKED`. Regla del docstring (`db.py:181-184`): `fn` **debe abrir su propia sesión adentro**;
prohibido pasarle una lambda con `Session` ya abierta.

**Flag:** `STACKY_MEETINGS_ENABLED`. **Trabajo del operador: ninguno.**
**Impacto por runtime:** ninguno (capa de datos).

---

### F3 — `transcript_parser.py`: puro, sin red, sin modelo

**Objetivo.** Convertir lo que el operador pegue en turnos estructurados, de forma determinista.

**Archivo a crear:** `backend/services/transcript_parser.py`

**Símbolos exactos:**
```python
MAX_TRANSCRIPT_CHARS = 120_000        # constante del módulo, NO flag (no es decisión del operador)

@dataclass(frozen=True)
class TranscriptTurn:
    speaker: str            # "" si el formato no lo trae
    start_ms: int | None    # None si no hay timestamp
    text: str

def detect_format(raw: str) -> str: ...
    # "vtt" si la primera línea no vacía es exactamente "WEBVTT" (case-insensitive); si no, "txt"

def parse_vtt(raw: str) -> list[TranscriptTurn]: ...
def parse_plain(raw: str) -> list[TranscriptTurn]: ...

def normalize_transcript(raw: str, *, max_chars: int = MAX_TRANSCRIPT_CHARS) -> dict: ...
    # -> {"formato": str, "turnos": list[TranscriptTurn], "texto": str,
    #     "turnos_totales": int, "turnos_incluidos": int, "chars": int,
    #     "hablantes": tuple[str, ...]}      # <-- [ADICIÓN A1] D9

def hablante_matchea(responsable: str, hablantes: tuple[str, ...]) -> bool: ...
    # [ADICIÓN A1] Función PURA. Compara por TOKENS, no por cadena:
    #   - `casefold()` en ambos lados, split por espacios/comas/puntos
    #   - matchea si el conjunto de tokens de `responsable` está CONTENIDO en el de
    #     algún hablante, o viceversa (cubre "Juan" ~ "Juan Pérez" y "Perez, Juan")
    #   - `responsable` vacío o `hablantes` vacío -> False
    # NO usa fuzzy ni distancia de edición: determinista y explicable, o no sirve
    # como evidencia. Un falso negativo degrada a `sin_hablante` (seguro);
    # un falso positivo asignaría trabajo real a alguien (inseguro).
```

⚠ **`hablantes`** es el conjunto de `speaker` **distintos y no vacíos** de los turnos **incluidos** (los
mismos que forman `texto`), en orden de aparición. Se calcula sobre los incluidos, no sobre los totales:
si un hablante quedó fuera por truncado (K7), su frase tampoco está en `texto`, así que tampoco puede
respaldar una cita.

**Reglas de parseo (sin ambigüedad):**
- **WebVTT.** Bloques separados por línea en blanco. Línea de tiempo:
  `HH:MM:SS.mmm --> HH:MM:SS.mmm` (también se acepta `MM:SS.mmm`). El hablante viene como
  `<v Nombre Apellido>texto</v>` **o** como prefijo `Nombre Apellido: texto`. Se descartan la cabecera
  `WEBVTT`, las líneas `NOTE ...` y los identificadores de cue.
  ⚠ **v2/C19 — el v1 decía "cue-ids numéricos o UUID" sin definirlo.** Regla literal: se descarta una línea
  como cue-id **si y solo si** es la **primera** del bloque, la **siguiente** es una línea de tiempo, y
  matchea `^[0-9]+$` **o** `^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(/\d+-\d+)?$`
  (Teams emite `<uuid>/1-0`). Cualquier otra cosa antes de la línea de tiempo **se conserva como texto**:
  ante la duda **no se descarta**, porque perder un turno en silencio es peor que arrastrar un id.
- **Texto plano.** Cada línea `Nombre: texto` abre un turno; una línea sin `:` se **concatena al turno
  anterior** con un espacio. Si no hay ningún `:` en todo el texto, se produce **un solo turno** con
  `speaker=""`.
- **Timestamps.** `start_ms` es el inicio del cue en milisegundos. En texto plano, `None`.
- **Truncado (K7).** Si la concatenación supera `max_chars`, se recortan turnos **desde el final** hasta
  entrar, y `turnos_incluidos < turnos_totales`. **Nunca** se corta un turno por la mitad. El texto
  resultante es el que se usa para verificar citas (D4), así que **debe** ser el mismo string que se manda
  al modelo.
- **`texto`** = `"\n".join(f"{t.speaker}: {t.text}" if t.speaker else t.text for t in turnos_incluidos)`.
  Esta es la **cadena canónica**: la verificación de cita de F6 se hace contra ella y ninguna otra.

**Archivo de test a crear:** `backend/tests/test_plan283_transcript_parser.py`

**Casos (10):**
1. `detect_format` con un `.vtt` real → `"vtt"`; con texto suelto → `"txt"`.
2. VTT con `<v Nombre>` → speaker extraído sin las etiquetas.
3. VTT con prefijo `Nombre: ` → speaker extraído.
4. VTT: `NOTE`, cabecera y cue-ids **no** producen turnos.
5. Timestamp `00:01:23.450` → `start_ms == 83450`. Formato corto `01:23.450` → `83450`.
6. Texto plano: línea sin `:` se concatena al turno previo.
7. Texto plano sin ningún `:` → exactamente 1 turno, `speaker == ""`.
8. **K7:** con `max_chars=200` sobre una entrada de 20 turnos → `turnos_incluidos < turnos_totales` y
   `len(texto) <= 200`; y **ningún** turno incluido aparece cortado (el `text` de cada turno incluido es
   idéntico al original).
9. **Pureza (gate por `ast`):** el AST de `services/transcript_parser.py` no tiene `Import`/`ImportFrom`
   que nombre `requests`, `copilot_bridge`, `flask`, `db` ni `config`.
   ⚠ **El gate se prueba contra el defecto primero**: el mismo test corre el detector sobre un fuente de
   prueba en memoria que **sí** importa `requests` y afirma que lo detecta. Sin ese guard, el caso pasaría
   por accidente si el detector estuviera roto.
10. Entrada vacía o solo espacios → `turnos == []`, `texto == ""`, `hablantes == ()`, **no lanza**.
11. **[ADICIÓN A1]** `hablantes` con un VTT de 3 hablantes que hablan 8 veces → exactamente 3 entradas, en
    orden de aparición, sin duplicados y sin el vacío. Y con truncado a `max_chars` que deja fuera al
    tercero → `hablantes` trae **2**, no 3.
12. **[ADICIÓN A1]** `hablante_matchea`: `("Juan", ("Juan Pérez",))` → `True`; `("Perez, Juan",
    ("Juan Pérez",))` → `True`; `("Marcela", ("Juan Pérez", "Ana Gómez"))` → `False`; `("", (...))` →
    `False`; `("Juan", ())` → `False`.

**Criterio BINARIO (F3):** `pytest tests/test_plan283_transcript_parser.py -q` → **`12 passed`**.

**Flag:** `STACKY_MEETINGS_ENABLED`. **Trabajo del operador: ninguno.**
**Impacto por runtime:** ninguno (código puro).

---

### F4 — `graph_client.py`: OAuth device-code + lectura, con transporte inyectable

**Objetivo.** Hablar con Microsoft Graph sin agregar dependencias y **sin tocar la red en los tests**.

**Archivo a crear:** `backend/services/graph_client.py`

**Símbolos exactos:**
```python
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTH_BASE  = "https://login.microsoftonline.com"
DEFAULT_SCOPES = ("offline_access", "Calendars.Read", "OnlineMeetingTranscript.Read.All")
# ⚠ D2: valor por defecto EDITABLE. Los scopes exactos son un hecho de la plataforma
#    Microsoft, NO del repo; el plan no puede verificarlos con grep.
DEFAULT_TENANT = "common"     # v2/C8 — el default vive ACÁ, no en config.py ni en el FlagSpec.
                              # Se aplica cuando config.STACKY_MEETINGS_GRAPH_TENANT está vacío.
GRAPH_TIMEOUT_S = 20          # v2/C11 — molde: services/gitlab_client.py:301

class GraphConfigError(RuntimeError): ...          # molde: TrackerConfigError (tracker_provider.py:45)

class GraphApiError(RuntimeError):                 # molde LITERAL: TrackerApiError (:48-52)
    def __init__(self, status: int, message: str, *, kind: str = "unknown"):
        super().__init__(message)
        self.status = status
        self.kind = kind
    # ⚠ `status` es POSICIONAL y obligatorio. Construirlo con kwargs revienta.

def _kind_for_status(status: int) -> str: ...      # molde: gitlab_client.py:103
    # 401/403 -> "auth" | 404 -> "not_found" | 429 -> "rate_limited" | >=500 -> "server" | else "unknown"
    # v2/C11: además, requests.Timeout / ConnectionError se capturan en el punto de
    # llamada y se re-lanzan como GraphApiError(0, "...", kind="timeout"|"network").

class GraphClient:
    def __init__(self, *, tenant: str | None = None, client_id: str | None = None,
                 auth_path: str | None = None, transport=None): ...
        # transport=None -> usa una requests.Session() PROPIA (molde gitlab_client.py:175).
        # transport != None -> se usa tal cual. ES EL SEAM DE TEST: cero red.
        # NO hace red en __init__ (molde gitlab_client.py:127).

    # --- OAuth device code (D2) ---
    def start_device_login(self) -> dict: ...
        # POST {AUTH_BASE}/{tenant}/oauth2/v2.0/devicecode
        # -> {"user_code","verification_uri","device_code","expires_in","interval"}
        # NUNCA devuelve el device_code al frontend: se guarda en memoria del proceso.
    def poll_device_login(self, device_code: str) -> dict: ...
        # POST {AUTH_BASE}/{tenant}/oauth2/v2.0/token grant_type=urn:ietf:params:oauth:grant-type:device_code
        # "authorization_pending" -> {"estado": "pending"} (NO es error)
        # ok -> guarda refresh_token cifrado y devuelve {"estado": "ok"}
    def _access_token(self) -> str: ...
        # refresca con el refresh_token guardado. Sin credenciales -> GraphConfigError.

    # --- Lectura ---
    def list_events(self, *, desde: datetime, hasta: datetime) -> list[dict]: ...
        # GET /me/calendarView?startDateTime=..&endDateTime=..&$top=50, header Prefer: outlook.timezone="UTC"
    def get_transcript(self, *, meeting_id: str) -> str | None: ...
        # GET /me/onlineMeetings/{id}/transcripts, luego /content?$format=text/vtt
        # 404 -> None (no es error: la reunión puede no tener transcripción)
```

**Persistencia del refresh token (reusa lo que hay, no inventa):**
- Ruta: `backend/projects/<PROYECTO>/auth/graph_auth.json`. El resolvedor sigue el molde de
  `project_manager.py:689` (`resolve_gitlab_auth_path`).
- Guardado: `secrets_store.set_encrypted_secret(payload, "refresh_token", valor, format_field="refresh_token_format")`
  (`services/secrets_store.py:191`) + `secrets_store.write_json_file(path, payload)` (`:181`).
- Lectura: `secrets_store.read_secret_from_file(path, "refresh_token", format_field="refresh_token_format")`
  (`:258`).
- ⚠ **Trampa documentada del repo:** `read_secret_from_file` **no es solo lectura** — si encuentra el
  secreto en claro, lo cifra y **reescribe el archivo** (`secrets_store.py:277-279`, avisado en
  `gitlab_client.py:210-217`). Es el comportamiento deseado; el test no debe sorprenderse.

**TLS — v2/C18, corregido: el v1 describía mal lo que pasa.** Graph es un servicio **público** con
certificado de CA pública, así que **no** se monta el adaptador OpenSSL de `gitlab_client.py:179-183` (ese
existe porque los GitLab internos presentan CA privada). Hasta ahí, bien. Pero el v1 decía *"se usa el
`verify` por defecto de `requests`"*, y **eso no es lo que ocurre en este repo**: `backend/app.py:26` llama
**`truststore.inject_into_ssl()`**, que es **global al proceso** (`truststore==0.10.4`,
`requirements.txt:9`). La verificación va por el **almacén de certificados del sistema operativo**, no por
el bundle de `certifi`. Para Graph eso es **bueno y necesario**: es justamente lo que hace que funcione
detrás de la inspección TLS corporativa (Zscaler), documentado en `gitlab_client.py:174`.
**Tres prohibiciones, las tres ya escritas en el repo:**
- **Prohibido tocar `REQUESTS_CA_BUNDLE`** — es global al proceso y rompería el resto
  (`gitlab_client.py:143-146`).
- **Prohibido llamar `truststore.extract_from_ssl()`** — global, y desarmaría el TLS de todo el backend
  (prohibición literal en `services/tls_openssl_context.py:11`).
- **Prohibido pasar `verify=<ruta>` en las llamadas a Graph** — con truststore inyectado el efecto es el
  contrario al esperado (es la causa raíz que el plan 276 tardó en encontrar: se manifiesta como
  `RecursionError`, no como error de TLS).

**Archivo de test a crear:** `backend/tests/test_plan283_graph_client.py`

**Casos (10):**
1. `GraphClient(transport=fake)` **no hace ninguna llamada** en `__init__` (el fake cuenta invocaciones: 0).
2. `start_device_login` devuelve `user_code` y `verification_uri` desde la respuesta del fake.
3. `poll_device_login` con `error="authorization_pending"` → `{"estado": "pending"}` y **no** lanza.
4. `poll_device_login` con `refresh_token` → escribe el archivo y el `refresh_token` **no aparece en claro**
   en los bytes del archivo. ⚠ **Guard positivo primero**: el mismo test afirma que el valor SÍ está en el
   payload en memoria antes de escribir, para que el assert de ausencia no pase por un archivo vacío.
5. `_access_token()` sin archivo de credenciales → `GraphConfigError` (no `GraphApiError`).
6. `list_events` mapea el JSON del fake a la lista, y las fechas ISO con `Z` quedan **naive UTC** (mismo
   criterio que `ado_sync._parse_iso`, `services/ado_sync.py:57`).
7. `get_transcript` con 404 → `None`, sin excepción.
8. Un 401 del fake → `GraphApiError` con `.status == 401` y `.kind == "auth"`.
9. Un 429 → `.kind == "rate_limited"`.
10. **Cero red real:** por `ast`, el módulo no llama a `requests.get`/`requests.post` a nivel módulo, y el
    test corre con `transport` falso en los 9 casos anteriores.
11. **v2/C11 — timeout.** (a) Por `ast`, **toda** llamada del módulo al transporte pasa `timeout=` (se
    recorre cada `ast.Call` cuyo `func` termine en `get`/`post`/`request` y se exige el keyword `timeout`;
    **guard positivo primero**: el detector se corre contra un fuente de prueba que **sí** omite `timeout`
    y debe encontrarlo). (b) Un transporte falso que lanza `requests.Timeout` → `GraphApiError` con
    `.kind == "timeout"`, **no** una excepción cruda que suba hasta Flask.
    ⚠ **Por qué esto importa más acá que en GitLab:** D8 hace que `POST /transcript` **importe y destile en
    el mismo request síncrono**. Un Graph colgado sin timeout cuelga el request y la pantalla.

**Criterio BINARIO (F4):** `pytest tests/test_plan283_graph_client.py -q` → **`11 passed`**, y
`pytest tests/test_plan283_baseline.py -q` → **`6 passed`** con el caso 1 ya invertido
("exactamente 1 archivo de producción menciona `graph.microsoft.com`, y es `services/graph_client.py`").

**Flag:** `STACKY_MEETINGS_GRAPH_ENABLED`. **Trabajo del operador:** opt-in — para usar Graph tiene que
pegar un `client_id` en el panel del arnés y hacer el device login una vez. **Sin eso, el módulo entero
sigue funcionando por el camino manual** (D1).
**Impacto por runtime:** ninguno — es HTTP, no depende del runtime de agente.

---

### F5 — `meetings_source.py`: dos fuentes, un contrato, más la sonda

**Objetivo.** Que las capas de arriba no sepan de dónde vino la reunión.

**Archivo a crear:** `backend/services/meetings_source.py`

```python
@dataclass(frozen=True)
class MeetingRecord:
    source: str                  # "manual" | "graph"
    external_id: str | None
    subject: str
    organizer: str | None
    started_at: datetime | None  # naive UTC SIEMPRE
    ended_at: datetime | None
    join_url: str | None

def from_manual(*, subject: str, started_at=None, ended_at=None,
                organizer=None) -> MeetingRecord: ...
def from_graph_event(event: dict) -> MeetingRecord: ...
def list_upcoming(*, project: str, dias: int = 14) -> dict: ...
    # -> {"estado": "ok"|"sin_credenciales"|"apagado"|"error", "reuniones": [...], "detalle": str}
    # NUNCA lanza. Degradación explícita, molde: _probe_gitlab (local_diagnostics.py:217).
def probe_graph(*, project: str) -> dict: ...
    # -> {"config": bool, "auth": bool, "calendario": bool, "detalle": str}
    # TRES sub-veredictos, por la misma razón que la sonda de GitLab tiene cuatro:
    # un solo check da falso verde (local_diagnostics.py:252-255 lo explica).
```

**Degradación honesta (esto es lo que permite que la flag nazca ON):** si no hay `client_id`, si no hay
credenciales guardadas o si la flag está apagada, `list_upcoming` devuelve `estado` distinto de `"ok"` con
un `detalle` accionable en castellano. **Nunca lanza y nunca rompe la pantalla.**

**Archivo de test a crear:** `backend/tests/test_plan283_meetings_source.py`

**Casos (8):** 1) `from_graph_event` con un evento real de Graph (fixture) → `MeetingRecord` con fechas
naive UTC. 2) evento sin `onlineMeeting` → `join_url is None`, no lanza. 3) `list_upcoming` con la flag
apagada → `estado == "apagado"` y `reuniones == []`. 4) sin `client_id` → `estado == "sin_credenciales"`.
5) con transporte falso OK → `estado == "ok"` y N reuniones. 6) `GraphApiError(401)` → `estado == "error"`
y el `detalle` **nombra** que hay que rehacer el login (sin filtrar el valor de ninguna credencial).
7) **D7, gate por `ast`:** ningún módulo `services/meetings_*.py` ni `services/graph_client.py` contiene
`threading.Thread`, `threading.Timer`, ni una `FunctionDef` cuyo nombre termine en `_loop`.
⚠ Con guard positivo: el detector se corre primero contra un fuente de prueba que **sí** define
`def _tick_loop()` y debe encontrarlo. 8) `from_manual` sin fechas → `started_at is None`, no lanza.

**Criterio BINARIO (F5):** `pytest tests/test_plan283_meetings_source.py -q` → **`8 passed`**.

**Flag:** `STACKY_MEETINGS_GRAPH_ENABLED`. **Trabajo del operador: ninguno** por el camino manual.
**Impacto por runtime:** ninguno.

---

### F6 — `meeting_minutes.py`: el destilado con cita obligatoria

**Objetivo.** De la transcripción a minuta + pendientes + fechas, con anti-alucinación verificable.

**Archivo a crear:** `backend/services/meeting_minutes.py`

**Símbolos exactos (molde literal: `services/local_insights.py:115-208`):**
```python
RESUMEN_MAX = 1200
TITULO_MAX = 300
CITA_MAX = 400
MAX_PENDIENTES = 25
MAX_DECISIONES = 15

def build_minutes_prompt(*, texto: str, subject: str, fecha_ref: datetime) -> tuple[str, str]: ...
    # system: rol + HITL_RULES (se REUSA local_insights.HITL_RULES, :46-53)
    # user: transcripción + instrucción de JSON estricto.
    # `fecha_ref` se inyecta LITERAL en el prompt (ISO) para que "el viernes" se pueda resolver.

def parse_minutes_response(text: str, *, texto_fuente: str,
                           hablantes: tuple[str, ...] = ()) -> dict: ...
    # 1) _strip_fences (se REUSA local_insights._strip_fences, :146)
    # 2) json.loads; si falla -> ValueError("json_parse_error: ...")
    # 3) LLAVE 1 (D4): si `cita` NO es subcadena literal de `texto_fuente`, SE DESCARTA.
    # 4) LLAVE 2 (D9, [ADICIÓN A1]): al pendiente que sobrevivió se le calcula
    #    `atribucion` = "confirmada" | "sin_hablante" | "sin_responsable"
    #    con transcript_parser.hablante_matchea(). NO se descarta: se MARCA.
    # -> {"resumen","decisiones":[...],"pendientes":[...],"riesgos":[...],
    #     "descartados_sin_cita": int, "sin_hablante": int, "aviso_truncado": str|None}

def build_minutes_payload(*, meeting_id: int, project: str) -> dict: ...
    # 1) lee la reunión, normaliza con transcript_parser.normalize_transcript()
    # 2) K5: egress_policies.check(project=project, model=<modelo efectivo>,
    #        context_text=<texto normalizado>)  -> si allowed=False: {"estado":"blocked", ...}
    #        y NO se invoca el bridge.
    # 3) copilot_bridge.invoke(agent_type="meeting_minutes", system=..., user=..., on_log=...)
    # 4) parse + persistencia (minutes_json, minutes_state, MeetingActionItem por pendiente)
    # NUNCA lanza: devuelve {"ok": bool, ...} (molde generate_insight_for_execution, :291)
```

**Contrato JSON que se le pide al modelo (literal en el prompt):**
```json
{"resumen": "…",
 "decisiones": [{"texto": "…", "cita": "…"}],
 "pendientes": [{"titulo": "…", "responsable": "…|null",
                 "fecha_compromiso": "YYYY-MM-DD|null", "cita": "…"}],
 "riesgos": [{"texto": "…", "cita": "…"}]}
```
La instrucción incluye, palabra por palabra: *"`cita` debe ser un fragmento COPIADO TAL CUAL de la
transcripción. Si no podés copiar un fragmento textual que lo respalde, NO incluyas ese ítem."*

**Fechas.** `fecha_compromiso` se acepta **solo** en `YYYY-MM-DD`. Cualquier otra forma → `None`
(no se intenta interpretar lenguaje natural en código; el prompt ya recibió `fecha_ref` para resolverlo).
Se guarda como `datetime` naive a medianoche UTC.

**Archivo de test a crear:** `backend/tests/test_plan283_minutes.py`

**Casos (10):**
1. `build_minutes_prompt` incluye `HITL_RULES` literal y la `fecha_ref` en ISO.
2. `parse_minutes_response` con JSON envuelto en ```` ```json ```` → parsea (usa `_strip_fences`).
3. JSON inválido → `ValueError` que empieza con `"json_parse_error"`.
4. Caps: un `resumen` de 5.000 chars queda en `RESUMEN_MAX`; 40 pendientes quedan en `MAX_PENDIENTES`.
5. **K2 — guard POSITIVO (va PRIMERO, en el mismo test):** un pendiente cuya `cita` **sí** es subcadena de
   `texto_fuente` sobrevive → `len(pendientes) == 1` y `descartados_sin_cita == 0`.
6. **K2 — el descarte:** en el **mismo** test, un segundo pendiente con `cita` inventada se descarta →
   `len(pendientes) == 1`, `descartados_sin_cita == 1`. *(5 y 6 comparten fixture a propósito: así el
   assert de ausencia no puede pasar por un parser roto.)*
7. `fecha_compromiso: "el viernes"` → `None`; `"2026-08-07"` → `datetime(2026,8,7)`.
8. **K5:** con un `egress_policies.check` monkeypatcheado a `allowed=False`, `build_minutes_payload`
   devuelve `estado == "blocked"` **y** el espía sobre `copilot_bridge.invoke` registra **0** llamadas.
9. **K4 — gate por `ast`:** el AST de `services/meeting_minutes.py` no tiene ningún `Import`/`ImportFrom`
   que nombre `codex_cli_runner`, `claude_code_cli_runner` ni `agent_runner`. Con guard positivo contra
   un fuente de prueba que sí los importa.
10. Si `invoke` lanza, `build_minutes_payload` devuelve `{"ok": False, ...}`, deja `minutes_state="failed"`
    y **la transcripción sigue guardada** (D8) — se relee de la BD y se compara carácter por carácter.
11. **[ADICIÓN A1] / K8 — guard POSITIVO primero, en el mismo test:** un pendiente con `cita` válida **y**
    `responsable="Juan"` con `hablantes=("Juan Pérez","Ana Gómez")` → sobrevive con
    `atribucion == "confirmada"`.
12. **[ADICIÓN A1] / K8 — el marcado:** en el **mismo** test, un segundo pendiente con `cita` **válida** y
    `responsable="Marcela"` (que no habló) → **NO se descarta**, queda con
    `atribucion == "sin_hablante"`, y `sin_hablante == 1`. Un tercero con `responsable=None` →
    `atribucion == "sin_responsable"`.
    ⚠ *Este es el caso que D4 sola no atrapa: la cita es literal y verdadera, y el responsable igual está
    inventado.* Por eso 11 y 12 comparten fixture: sin el guard positivo de 11, un parser que devolviera
    todo como `"sin_hablante"` haría pasar 12.

**Criterio BINARIO (F6):** `pytest tests/test_plan283_minutes.py -q` → **`12 passed`**.

#### [ADICIÓN ARQUITECTO A2] — La paridad de runtimes deja de ser un argumento y pasa a ser una medición

**Archivo a crear:** `backend/tests/test_plan283_backend_parity.py`

**El problema con el gate K4 del v1 (v2/C6).** Corría por `ast` sobre `services/meeting_minutes.py` para
verificar que **no importa** `codex_cli_runner`, `claude_code_cli_runner` ni `agent_runner`. Pero ese
archivo **lo escribe este mismo plan**: nadie iba a importar un runner ahí. El gate **pasa por
construcción**, no puede fallar nunca, y seguiría verde aunque la paridad se rompiera en el único lugar
donde puede romperse, que es `copilot_bridge`. Un gate que no puede ponerse rojo no mide nada.

**Lo que sí se verificó, abriendo el archivo:** `copilot_bridge.invoke()` (`copilot_bridge.py:145`)
despacha en `:157` por **`config.LLM_BACKEND`**, cuyos valores son
`mock | vscode_bridge | copilot | claude_cli | local_llm` (ramas en `:157-185`, default `vscode_bridge` en
`config.py:81`), y **ese eje es ortogonal al runtime de agente** (`codex_cli`, `claude_code_cli`,
`github_copilot`). La afirmación del plan es correcta. Lo que faltaba era **medirla**.

**Casos (6):**
1-5. **Parametrizado sobre los 5 valores** de `LLM_BACKEND`. Con `copilot_bridge.invoke` stubbeado a una
   respuesta JSON fija y `config.LLM_BACKEND` monkeypatcheado, `build_minutes_payload()` devuelve un dict
   **idéntico** (`==`) en los 5 — mismo resumen, mismos pendientes, mismas citas, mismas `atribucion`.
6. **Guard positivo obligatorio:** el mismo archivo afirma que el parametrize **seleccionó 5 casos**
   (`len(BACKENDS) == 5` y la lista es exactamente la de `copilot_bridge.py:157-185`).
   ⚠ Sin esto, un `parametrize` vacío o un `-k` sin match daría **exit 0** y parecería verde.

**Criterio BINARIO:** `pytest tests/test_plan283_backend_parity.py -q` → **`6 passed`**.
**Valor extra:** es un molde reutilizable. Cualquier plan futuro que llame al modelo puede copiarlo para
convertir su "paridad por no participación" en una matriz medida.

**Flag:** `STACKY_MEETINGS_ENABLED`. **Trabajo del operador: ninguno** (D8: automático al importar).

**Impacto por runtime — leer con atención, acá se juega la paridad:**
`copilot_bridge.invoke()` (`copilot_bridge.py:145`) despacha por `config.LLM_BACKEND`, cuyos valores son
`mock | vscode_bridge | copilot | claude_cli | local_llm` (`:157-186`; default `vscode_bridge`,
`config.py:81`). **Ese NO es el mismo eje que el runtime de agente** (`codex_cli`, `claude_code_cli`,
`github_copilot`). La paridad de este plan es por **no participación**: el destilado es una llamada de un
solo tiro y **no lanza ningún agente**, así que la elección de runtime del operador **no interviene** —
funciona idéntico con los tres. K4 lo mide por `ast` en vez de afirmarlo. Fallback: si `invoke` falla con
cualquier backend, D8 conserva la transcripción y ofrece reintentar.

---

### F7 — La API de reuniones

**Objetivo.** Exponer el módulo por HTTP, con el gate de flag dentro de la ruta.

**Archivos a crear:** `backend/api/meetings.py`
**Archivo a editar:** `backend/api/__init__.py` (**dos** líneas)

```python
# backend/api/meetings.py
bp = Blueprint("meetings", __name__, url_prefix="/meetings")
# ⚠ R6: NUNCA declarar "/api" acá (api/__init__.py:181) → daría /api/api/...
#    v2/C16: el v1 citaba :178, que es un register_blueprint, no la regla.
```

⚠ **v2/C5 — F7 depende de F5, y en el v1 iba ANTES.** La ruta `/api/meetings/calendar` llama
`meetings_source.list_upcoming()` y el **caso 6** de esta fase lo assertea. Con el orden del v1
(F7 en el paso 6, F5 en el paso 8) el criterio "10 passed" era **insatisfacible**. Ver §11.

| Método | Ruta | Función | Qué hace |
|---|---|---|---|
| GET | `/api/meetings/health` | `health()` | **SIEMPRE 200** con `{"ok": True, "flag_enabled": ...}` (molde `api/evolution.py:47-54`). Es lo que consume el gate de nav del frontend. |
| GET | `/api/meetings` | `list_meetings()` | Reuniones del proyecto activo, orden `started_at` desc |
| POST | `/api/meetings` | `create_meeting()` | Alta manual (`subject` obligatorio) |
| GET | `/api/meetings/calendar` | `calendar()` | `meetings_source.list_upcoming()` — **nunca 500**: devuelve el `estado` |
| POST | `/api/meetings/<int:mid>/transcript` | `put_transcript()` | Body `{"content": str, "format": "vtt"\|"txt"\|null}`. Guarda **y** destila (D8) |
| POST | `/api/meetings/<int:mid>/minutes/retry` | `retry_minutes()` | Re-destila |
| GET | `/api/meetings/<int:mid>` | `get_meeting()` | Reunión + minuta + pendientes |
| POST | `/api/meetings/graph/device-login` | `device_login()` | Arranca device code |
| POST | `/api/meetings/graph/device-poll` | `device_poll()` | Consulta el device code |
| GET | `/api/meetings/graph/probe` | `graph_probe()` | `probe_graph()`, 3 sub-veredictos |

**Gate.** Todas las rutas **salvo `/health`** empiezan con:
```python
if not _cfg.STACKY_MEETINGS_ENABLED:
    return jsonify({"ok": False, "error": "feature_disabled"}), 404
```
El gate va **dentro** de la ruta, no en el registro: la razón está escrita en **`api/__init__.py:182-184`**
(el registro se evalúa una sola vez al importar, y gatearlo ahí obligaría a reiniciar el backend).
**v2/C16:** el v1 citaba `:179-181`, que son las 2 últimas líneas de `register_blueprint` y el título del
comentario del plan 218.

**Body por JSON, no multipart.** El repo tiene **un solo** `request.files` (`api/incidents.py:55`); el
patrón dominante es JSON. El frontend lee el `.vtt` con `FileReader` y manda texto. Cero dependencias,
test hermético.

**Las 2 líneas en `api/__init__.py`** (moldes exactos: import en **`:90`**, registro en **`:125-127`** —
**v2/C16: el v1 citaba `:124`, que es la 2ª línea de un comentario**):
```python
from .meetings import bp as meetings_bp          # Plan 283 — reuniones, minutas y pendientes
...
api_bp.register_blueprint(meetings_bp)           # Plan 283 — url_prefix="/meetings" → /api/meetings/...
```

**Archivo de test a crear:** `backend/tests/test_plan283_api.py`
Cabecera **obligatoria** (molde `tests/test_pipeline_copilot_api.py:16`), antes de importar la app:
```python
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
```

**Casos (10):** 1) `/health` responde **200 con la flag apagada** y `flag_enabled: false`. 2) con la flag
apagada, `GET /api/meetings` → **404** `feature_disabled`. 3) alta manual → 201 con `id`. 4) alta sin
`subject` → 400. 5) **`POST`** de transcripción con `invoke` monkeypatcheado → 200, `minutes_state == "done"`,
pendientes persistidos. *(**v2/C19:** el v1 decía "`PUT`" acá y `POST` en la tabla de rutas. **Es `POST`**,
en la tabla y en el test.)* 6) `/calendar` con Graph apagado → **200** con `estado == "apagado"` (nunca 500).
7) `/graph/device-login` **no** devuelve el `device_code` en el body. 8) `retry` sobre una reunión sin
transcripción → 409. 9) `/meetings/<id>` de un id inexistente → 404. 10) por `ast`, `api/meetings.py`
**no** importa `api.tickets` (D6) ni llama a `create_item` (eso es F8).

**Criterio BINARIO (F7):** `pytest tests/test_plan283_api.py -q` → **`10 passed`**.

**Flag:** `STACKY_MEETINGS_ENABLED` (+ `..._GRAPH_ENABLED` en las 3 rutas de Graph).
**Trabajo del operador: ninguno.** **Impacto por runtime:** ninguno (HTTP).

---

### F8 — De pendiente a ticket: el único camino que escribe

**Objetivo.** Convertir un pendiente en un work item real del tracker, con **doble** llave.

**Archivo a crear:** `backend/api/meetings_publish.py` (blueprint propio, D6)
**Archivo a editar:** `backend/api/__init__.py` (2 líneas más)

| Método | Ruta | Función | Qué hace |
|---|---|---|---|
| POST | `/api/meetings-publish/<int:item_id>/draft` | `draft()` | **No escribe nada.** Devuelve el borrador (título, descripción con la cita, tipo, proyecto destino) **y** un `confirm_token` de 120 s (`confirm_token.issue_token("meetings_publish", payload)`, `services/confirm_token.py:39`) |
| POST | `/api/meetings-publish/<int:item_id>/confirm` | `confirm()` | Exige `confirm_token`. Llama `get_tracker_provider(project).create_item(TrackerItem(...))` y marca el pendiente `estado="publicado"` con `external_id` y `tracker_type` |

**Las DOS llaves (K6), ambas obligatorias:**
1. `STACKY_MEETINGS_PUBLISH_ENABLED` en **ON** (nace OFF, excepción B) — si no, **404**.
2. `confirm_token` válido y no vencido — si no, **409**.

**El work item que se crea — v2/C15, campos literales.** `TrackerItem` (`services/tracker_provider.py:32-39`)
tiene **exactamente** `item_type, title, description_html, labels, assignee, parent_id, fields`. Este plan
llena:

| Campo | Valor |
|---|---|
| `item_type` | `"Task"` |
| `title` | `item.titulo` recortado a 255 |
| **`description_html`** | **HTML, no texto plano** (el v1 decía "la descripción" sin nombrar el campo ni su formato): `<p>` con el responsable y la fecha, `<blockquote>` con **la cita textual escapada** (`html.escape`), y `<p>` con el enlace de vuelta a la reunión en Stacky |
| `labels` | `("reunion",)` |
| **`assignee`** | **[ADICIÓN A1] / K8** — `item.responsable` **solo si** `atribucion == "confirmada"`. En cualquier otro caso **`None`**: el sistema no le asigna trabajo real a nadie por una atribución que no pudo probar |
| `parent_id` | `None` (§9.7: no se vincula a tickets existentes) |
| `fields` | `{}` |

**Cero PII al tracker que no esté ya en la cita.** **No** se sube la transcripción completa.

**Archivo de test a crear:** `backend/tests/test_plan283_publish.py`

**Casos (9):**
1. `draft` con la flag OFF → **404** (la flag de publicación gatea también el borrador: el borrador ya
   nombra el proyecto destino).
2. `draft` con la flag ON → 200, `confirm_token` presente, y el espía sobre `create_item` cuenta **0**.
3. `confirm` con token válido → 200 y `create_item` cuenta **1**.
4. **K6 — sin token:** `confirm` sin `confirm_token` → **409** y `create_item` cuenta **0**.
   ⚠ **Guard positivo primero**: el caso 3 (que sí llama) corre en el mismo archivo con el mismo espía,
   así que un espía roto no puede hacer pasar el caso 4.
5. Token vencido (`confirm_token.expire_token_for_tests`, `services/confirm_token.py:75`) → **409**.
6. Token reutilizado dos veces → la segunda da **409** (`consume_token` es de un solo uso).
7. `create_item` lanza `TrackerApiError(500, "boom")` → 502 y el pendiente **sigue** en `"propuesto"`
   (no queda marcado publicado por un fallo).
8. **D6 — gate por `ast`:** `api/meetings_publish.py` no tiene `Import`/`ImportFrom` que nombre
   `api.tickets`. Con guard positivo contra un fuente de prueba que sí lo importa.
9. El **`description_html`** enviado a `create_item` **contiene** la `cita` (escapada) y **no contiene** el
   texto completo de la transcripción (se afirma con una marca única sembrada en el fixture fuera de la
   cita). **Guard positivo primero:** el mismo test verifica que la marca **sí** está en la transcripción
   guardada — sin eso, un `description_html` vacío haría pasar el assert de ausencia.
10. **[ADICIÓN A1] / K8 — el sistema no adivina de quién es el trabajo.** Con el mismo espía: un pendiente
    `atribucion == "confirmada"` → `create_item` recibe `assignee == "Juan Pérez"`; un pendiente
    `atribucion == "sin_hablante"` → `create_item` recibe **`assignee is None`** y el `description_html`
    **dice en castellano** que el responsable no pudo verificarse contra los hablantes de la reunión.
    *(Guard positivo: el primer sub-caso corre antes que el segundo, con el mismo espía.)*

**Criterio BINARIO (F8):** `pytest tests/test_plan283_publish.py -q` → **`10 passed`**.

**Flag:** `STACKY_MEETINGS_PUBLISH_ENABLED` — **default OFF, excepción (B)**: escribe en el Azure DevOps o
GitLab real del operador vía `create_item()` (`services/gitlab_provider.py:387`).
**Trabajo del operador:** encenderla una vez por UI **y** confirmar cada publicación. Es el
human-in-the-loop, no fricción accidental.
**Impacto por runtime:** ninguno.

---

### F9 — La pantalla `Reuniones`

**Objetivo.** Una sola pantalla para todo el ciclo (K3).

**Archivos a crear:**
- `frontend/src/services/meetingsModel.ts` — **lógica pura, sin React** (RTL/jsdom **no** están instalados)
- `frontend/src/services/meetingsModel.test.ts`
- `frontend/src/pages/MeetingsPage.tsx`
- `frontend/src/pages/MeetingsPage.module.css`

**Archivos a editar — v2/C2+C3: son 13 patas, NO 11.** El v1 decía "las 11 patas de un tab nuevo, **todas
verificadas**" y se le escapaban las **dos que ponen rojos tests ajenos**. Las 13 se verificaron abriendo
cada archivo:

| # | Archivo | Línea de referencia | Qué se agrega |
|---|---|---|---|
| 1 | `frontend/src/services/routes.ts` | `:5-9` (`type Tab`) | `\| "reuniones"` |
| 2 | `frontend/src/services/routes.ts` | `:15-22` (`TAB_PATHS`) | `reuniones: "/reuniones"` |
| 3 | `frontend/src/components/shell/shellNav.ts` | `:5-9` (`ShellTab`) | `\| "reuniones"` — debe ser **1:1** con `Tab`, hay test de drift (`shellNav.ts:3-4`) |
| 4 | `frontend/src/components/shell/shellNav.ts` | `:16` (`TAB_META`) | `reuniones: { label: "Reuniones", iconName: **"CalendarDays"** }` — **v2/C3: el v1 dejaba `"…"` literal.** Ver pata 13 |
| 5 | `frontend/src/components/shell/shellNav.ts` | `:44` (grupo `trabajo`) | agregar `"reuniones"` a la lista |
| 6 | `frontend/src/components/shell/shellNav.ts` | `:68` (`computeVisibleTabs`) | `if (input.meetingsEnabled) v.add("reuniones");` + el campo en `VisibilityInput` |
| 7 | `frontend/src/App.tsx` | `:21` (molde import) | `import MeetingsPage from "./pages/MeetingsPage";` |
| 8 | `frontend/src/App.tsx` | `:122` (molde estado) | `const [meetingsGate, setMeetingsGate] = useState<GateState>("unknown");` |
| 9 | `frontend/src/App.tsx` | `:186` (molde probe) | `void probeFlagHealth("/api/meetings/health").then(...)` |
| 10 | `frontend/src/App.tsx` | `:344` (redirect) + deps `:346` | `else if (tab === "reuniones" && shouldRedirectAway(meetingsGate)) avisarYSalir("reuniones");` |
| 11 | `frontend/src/App.tsx` | `:361` + `:404-406` (render) | `meetingsEnabled: isGateOn(meetingsGate)` y el bloque de render con `Skeleton` |
| **12** | **`frontend/src/components/shell/__tests__/shellNav.test.ts`** | **`:11-15`** (`ALL_TABS`) **y `:18`** (título) | **v2/C2 — LA PATA QUE FALTABA.** `ALL_TABS` congela los **18 tabs LITERALES**, y dos casos assertean contra él: `Object.keys(TAB_META).sort() == ALL_TABS` (`:18-20`) y `SHELL_NAV_GROUPS.flatMap(g=>g.tabs).sort() == ALL_TABS` (`:23-26`). Las patas 3-5 **ponen esos 2 casos en ROJO** si no se agrega `"reuniones"` acá y se cambia el título `"…los 18 tabs"` → **19** |
| **13** | **`frontend/src/components/shell/shellIcons.ts`** | **`:8-12`** (`ICON_BY_NAME`) | **v2/C3 — LA OTRA PATA QUE FALTABA.** Medido: `ICON_BY_NAME` tiene **exactamente 18 íconos y los 18 están tomados** por los 18 tabs. **No hay ninguno libre.** Hay que `import { CalendarDays } from "lucide-react"` y agregarlo al objeto. `shellIconsCoverage.test.ts` convierte un `iconName` inexistente en **rojo determinista** (y su comentario dice que existe *"para este plan y para los tabs futuros"* — o sea, para este) |

**Nota — la nav v1 legacy.** El `<nav className={styles.nav} data-tour="nav">` abre en **`App.tsx:442`**
(anclaje que el v1 no daba) y se sigue pintando si `shellV2Enabled` es `false` (`App.tsx:425`). El bloque
del botón de Incidencias, molde de un tab gateado, está en `App.tsx:457-464`. Agregar el botón ahí es
**opcional** y no lo cubre ningún test; si se omite, **declararlo en el commit**.

**`meetingsModel.ts` — lo que se testea de verdad (lógica, no pixeles):**
```ts
export type MeetingsView = "calendario" | "detalle";
export interface MeetingRow { id: number; subject: string; startedAt: string | null;
                              minutesState: "pending" | "done" | "failed" | "blocked";
                              pendientes: number; }
export function agruparPorDia(rows: MeetingRow[]): { dia: string; rows: MeetingRow[] }[]
export function etiquetaEstadoMinuta(s: MeetingRow["minutesState"]): string   // castellano
export function puedePublicar(item: {estado: string}, flagOn: boolean): boolean
export function resumenCalendario(estado: string): { texto: string; accionable: boolean }

// v2/C10 — K3 necesitaba un gate y no lo tenía.
export interface AccionReunion { id: "importar" | "regenerar" | "publicar" | "actualizar";
                                 label: string; habilitada: boolean; navPath: null }
export function accionesDisponibles(m: MeetingRow, flags: {publishOn: boolean}): AccionReunion[]
// Devuelve SIEMPRE las 4 acciones del ciclo, con `navPath: null` en todas:
// el KPI K3 es "una sola pantalla", y una acción con navPath lo violaría.
```

**API en el frontend.** Namespace `Meetings` en `frontend/src/api/endpoints.ts`.
⚠ **Regla dura de la casa:** `api.*` **lanza** en cualquier non-2xx. Las rutas donde un 404
(`feature_disabled`) o un 409 son **respuestas normales que hay que pintar** deben usar
**`rawGet`/`rawPost`** (`frontend/src/api/client.ts:100` / `:51`) y leer `res.errorBody`.
Esto aplica **obligatoriamente** a: `/calendar`, `/graph/probe`, `draft` y `confirm`.

⚠ **v2/C14 — los moldes que daba el v1 eran los equivocados, y uno era el CONTRARIO de la regla.**

| Qué | Anclaje del v1 | **Anclaje real (verificado)** |
|---|---|---|
| La regla escrita | `:3436-3442` | **`:3444-3445`** (`:3436-3442` es `export const Health`) |
| Molde de `api.get` | `:1026` (un comentario) | **`:1024-1025`** (`directiveHealth`) |
| Molde de **`rawGet`** | `:5593-5598` — **es un `api.get`** (`runCoverage`), justo el wrapper prohibido | **`:3340`**, **`:3361`**, **`:3453`** |
| Molde de **`rawPost`** | no daba | **`:3462`**, **`:3786`**, **`:4030`** |

Un modelo menor copiando el molde del v1 para `/calendar` habría escrito `api.get` y la pantalla habría
explotado con la flag apagada — exactamente el bug que la regla existe para evitar.

**Ratchets de deuda del frontend que hay que respetar** (no son de registro; escanean contenido):
`uiDebtRatchet` (cero estilos inline ⇒ todo por `MeetingsPage.module.css`), `undoConfirmRatchet` (cero
`confirm()`/`alert()` nativos ⇒ usar las primitivas de `components/ui`), `formDebtRatchet`,
`copyDebtRatchet`, `motionDebtRatchet`, `formatDebtRatchet`.
⚠ Los tokens CSS válidos son `--accent`, `--success`, `--danger`, `--border`, `--text-primary`,
`--bg-panel`. **`--color-*` NO existe en el tema.**

**Casos de `meetingsModel.test.ts` (9):** 1) `agruparPorDia` agrupa por fecha local y ordena desc.
2) `startedAt` nulo cae en un grupo "Sin fecha" al final. 3-6) `etiquetaEstadoMinuta` devuelve castellano
para los 4 estados. 7) `puedePublicar` es `false` con `flagOn=false` **y** `false` si el pendiente ya está
`"publicado"`. 8) `resumenCalendario("sin_credenciales")` es accionable y nombra qué falta.
**9) v2/C10 — K3:** `accionesDisponibles()` devuelve **4** acciones y **todas** con `navPath === null`;
con `publishOn=false`, la de publicar viene `habilitada: false` pero **sigue estando** (se muestra
deshabilitada con motivo, no se esconde).

**Comandos:** desde `Stacky Agents/frontend`:
```
npx vitest run src/services/meetingsModel.test.ts
npx vitest run src/components/shell/__tests__/shellNav.test.ts
npx vitest run src/components/shell/__tests__/shellIconsCoverage.test.ts
npx vitest run src/components/shell/__tests__/shellIntegration.test.ts
npx tsc --noEmit
```
⚠ Correr **por archivo**: vitest sufre contaminación por orden. Un `.test.tsx` con RTL reporta
"no tests" y **exit 0** — por eso toda la lógica va en `.ts` puro.

**Criterio BINARIO (F9) — v2/C2, el del v1 no cubría lo que el propio plan rompía:**

| Comando | Resultado exigido | Baseline **medido hoy** |
|---|---|---|
| `vitest run src/services/meetingsModel.test.ts` | **`9 passed`** | (archivo nuevo) |
| `vitest run …/shellNav.test.ts` | **`9 passed`** — el mismo número de hoy, **delta cero** | **9 passed** |
| `vitest run …/shellIconsCoverage.test.ts` | **`1 passed`** | **1 passed** |
| `vitest run …/shellIntegration.test.ts` | **`2 passed, 1 failed`** — **el mismo, delta cero** | **2 passed, 1 failed** |
| `npx tsc --noEmit` | 0 errores | 0 |
| `pytest tests/test_plan283_baseline.py -q` | `6 passed` (caso 2 invertido) | — |

⚠ **ROJO AJENO NUEVO, medido en esta corrida y NO declarado por el v1:**
`shellIntegration.test.ts::"conserva la <nav> v1 verbatim (rama OFF byte-idéntica, KPI-1)"` **ya está
rojo**, y no lo causa este plan. El guard hace `expect(APP).toContain('<nav className={styles.nav}>')`
(`:8`), pero `App.tsx:442` hoy dice `<nav className={styles.nav} data-tour="nav">`: alguien agregó el
atributo del tour y rompió una comparación por **literal**. **Este plan no lo arregla** (es de otro dueño),
pero **debe** dejarlo en 1, no en 2 — por eso el criterio es `2 passed, 1 failed`, no "verde".

**Flag:** `STACKY_MEETINGS_ENABLED` vía el gate de nav. **Trabajo del operador: ninguno.**
**Impacto por runtime:** ninguno (la UI no depende del runtime de agente).

---

### F10 — Ratchets, huella de error y E2E

**Objetivo.** Que el plan quede registrado donde el arnés lo vigila, y probado de punta a punta.

#### F10.1 — Los DOS ratchets (esto es lo que más se olvida)

Los **12** archivos de test nuevos van en **los dos** scripts (**v2/C19: el v1 decía "8" y listaba 9**):

| Script | Ruta | Lista | Formato |
|---|---|---|---|
| bash | `backend/scripts/run_harness_tests.sh` | `HARNESS_TEST_FILES=(` abre en **`:20`**, cierra en **`:1024`** | ruta **pelada**: `  tests/test_plan283_store.py` |
| powershell | `backend/scripts/run_harness_tests.ps1` | `$HarnessTestFiles = @(` abre en **`:13`**, cierra en **`:941`** | **entrecomillada y con coma**: `  "tests/test_plan283_store.py",` |

**Los 12:** `test_plan283_baseline.py`, `test_plan283_flags.py`, `test_plan283_help_limpio.py`,
`test_plan283_store.py`, `test_plan283_transcript_parser.py`, `test_plan283_graph_client.py`,
`test_plan283_meetings_source.py`, `test_plan283_minutes.py`, `test_plan283_backend_parity.py`,
`test_plan283_api.py`, `test_plan283_publish.py`, `test_plan283_e2e.py`.

⚠ **CERO HOLGURA, y el criterio es un INVARIANTE — no una foto (v2/C17).**
`tests/test_plan259_ratchet_script_parity.py:93` assertea `len(solo_en_sh) <= _PS1_LAG_MAX`, con
`_PS1_LAG_MAX = 64` congelado en **`:46`**. **Hoy el lag es exactamente 64: no sobra ni uno.**
**Agregar un archivo al `.sh` sin agregarlo al `.ps1` lo lleva a 65 y pone ROJO ese test.**

> **Los conteos absolutos son VOLÁTILES y no sirven como criterio.** El v1 escribió "el `.sh` tiene **787**
> y el `.ps1` **723**". Medido de nuevo el **2026-08-01 ~18:0x**, una sesión paralela ya los había movido a
> **788 / 724** — **en menos de una hora**. Son archivos **compartidos por todo el repo**: cualquier plan
> hermano los toca. **Un criterio anclado en un absoluto de un archivo compartido nace con fecha de
> vencimiento.**
> **Regla para el implementador:** **medí el lag vos, inmediatamente antes de tocar nada**, y exigí que
> **después** siga valiendo `lag == _PS1_LAG_MAX`. Ese es el invariante load-bearing. Los absolutos van al
> log, nunca al criterio.

Y no hay escapatoria por `harness_ratchet_allowlist.txt`: es ratchet **solo-baja**, tope congelado
`_ALLOWLIST_MAX = 197` (`tests/test_harness_ratchet_meta.py:66`).
Pegar la ruta en el `.ps1` **sin comillas** no rompe el parseo: **pierde la ruta en silencio.**

**Criterio BINARIO (F10.1):**
```
pytest tests/test_harness_ratchet_meta.py tests/test_plan259_ratchet_script_parity.py -q
```
→ **`16 passed`** (medido hoy: `16 passed in 1.93s`), con **`lag == _PS1_LAG_MAX`** después de agregar
los 12 archivos a **ambos** scripts.

#### F10.2 — Huella de error

Registrar **1** huella (`id: "meeting_minutes_failed"`) en `Stacky Agents/docs/sistema/error_fingerprints.json`
para el fallo más probable del módulo: *transcripción importada pero minuta fallida*
(`minutes_state == "failed"`).

⚠ **El catálogo está ROJO DE FÁBRICA.** Medido hoy: **57 huellas**, **19 sin `self_test`**, **1 con
`status:"guarded"`** que no está en el enum ⇒ **5 rojos ajenos**.

**v2/C12 — el v1 mandaba "leerlo del schema real" pero no lo daba. Acá está, copiado del test:**

```python
# tests/test_error_fingerprints_catalog.py:18-19  (medido 2026-08-01)
_STATUS_ENUM = {"resolved", "open", "by_design"}          # "guarded" NO está
_REQUIRED = ("id", "title", "class", "status", "log_pattern",
             "log_guarded", "killed_by", "guard_test", "self_test")
```
- Los **9** campos de `_REQUIRED` son obligatorios. `evidence`, `note`, `killed_commit` y `date_resolved`
  son **opcionales** (existen en el catálogo pero el test no los exige).
- `self_test` es `{"matches": [...], "clean": [...]}`: cada `matches` **debe** matchear `log_pattern` y
  cada `clean` **no** debe (`test_self_test_coherente`).
- `test_sin_control_chars_crudos` prohíbe **todo byte 0x00-0x1F** salvo `\t \n \r` — **ojo al pegar un
  fragmento de `.vtt` de ejemplo en `self_test`**: un ESC crudo pone rojo el catálogo entero.
- El `status` de esta huella es **`"open"`** (el fallo existe y no está resuelto; es una huella de
  detección, no de regresión cerrada).

**Criterio BINARIO — v2/C12: por `id`, NO por conteo.** El criterio del v1 ("el conteo no puede subir de
5") **no discrimina**: los 3 tests que fallan acumulan violaciones de **todas** las huellas en una lista, y
una huella nueva mal formada se suma a la lista **sin subir el conteo de tests fallados**. Criterio real:

```
pytest tests/test_error_fingerprints_catalog.py tests/test_error_fingerprints_scan.py -q
```
1. Sigue dando **`5 failed, 12 passed`** (medido hoy: `5 failed, 12 passed in 5.20s`). **Delta cero.**
2. **Y** — lo que de verdad discrimina — el **mensaje** de los 5 fallos **no menciona
   `meeting_minutes_failed`**. Se verifica con `-q --tb=long` y un `grep` del id sobre la salida, o con un
   caso propio en `test_plan283_baseline.py` que valide la huella nueva **sola** contra las 9 reglas.

#### F10.3 — E2E

**Archivo a crear:** `backend/tests/test_plan283_e2e.py`

**Casos (6):**
1. **Camino manual completo:** crear reunión → `PUT` de un `.vtt` de 12 turnos (fixture inline, sin red) →
   con `invoke` monkeypatcheado a una respuesta válida → `GET /meetings/<id>` devuelve minuta con
   **3 pendientes**, todos con `cita` no vacía.
2. **Camino Graph con transporte falso:** `list_upcoming` → alta → transcripción vía
   `GraphClient.get_transcript` (fake) → misma minuta. **Cero red.**
3. **K5:** con una política de egress que bloquea, el ciclo devuelve `estado == "blocked"` y `invoke`
   cuenta 0.
4. **K6:** publicar sin `confirm_token` → 409 y `create_item` cuenta 0; con token → 1.
5. **K7:** una transcripción de 300.000 caracteres → `turnos_incluidos < turnos_totales` y la minuta trae
   `aviso_truncado` no nulo.
6. **Backward-compat:** con `STACKY_MEETINGS_ENABLED=false`, `GET /api/meetings` → 404 y
   `computeVisibleTabs` (probado en el `.ts`) **no** incluye `reuniones`.

**Criterio BINARIO (F10.3):** `pytest tests/test_plan283_e2e.py -q` → **`6 passed`**.

**Flag:** todas. **Trabajo del operador: ninguno.** **Impacto por runtime:** ninguno.

---

## 7. Rojos AJENOS y PREEXISTENTES (medidos hoy, no los causa este plan)

| Suite | Estado medido HOY | Causa (ajena) |
|---|---|---|
| `tests/test_harness_flags_help.py` | **`4 failed, 4 passed`** | **80** flags del registro (447) no tienen entrada en `PLAIN_HELP` (367); además 15 entradas ajenas citan keys `SCREAMING_SNAKE` o usan jerga de la denylist. **Este plan debe dejar el número en 4, no en 5.** |
| `tests/test_plan120_flags.py` | 1 rojo | `harness_defaults.env` es un snapshot parcial; el propio docstring del test lo declara preexistente y ajeno. |
| `tests/test_flags_env_read_meta.py` | 1 rojo | `services/validation_playbook.py` lee env con default local. |
| `tests/test_error_fingerprints_catalog.py` + `_scan.py` | 5 rojos | 19 huellas ajenas sin `self_test` + 1 con `status:"guarded"` fuera del enum. |
| Ratchets de deuda del frontend | 6 rojos | 24 archivos ajenos (dbcompare, docs, PlansBoard, TicketBoard, ui/Dialog…). |
| `tests/test_plan218_tracker_contract.py::[gitlab]` | rojo, **sale a la red** | El plan 276 migró `gitlab_client` a `requests.Session` y el fake parchea el `requests.request` de módulo, que `Session.request` no usa. |
| **`frontend .../shellIntegration.test.ts`** | **`2 passed, 1 failed`** | **v2 — ROJO AJENO NUEVO, no declarado por el v1 y directamente en el camino de F9.** El guard `expect(APP).toContain('<nav className={styles.nav}>')` (`:8`) compara por **literal**, y `App.tsx:442` hoy dice `<nav className={styles.nav} data-tour="nav">`. Alguien agregó el atributo del tour. **Sin declararlo, F9 se lo comería como propio.** |

**Regla del plan:** ninguno de estos se arregla acá. Se **miden antes** y el criterio es **delta cero**.
⚠ **v2/C7+C12 — pero "delta cero en el CONTEO" no alcanza cuando el archivo ya está rojo.** Los tests de
ayuda y los del catálogo de huellas acumulan violaciones en una **lista** y assertean `== []`: una entrada
nueva mal hecha se suma a la lista **sin mover el conteo de tests fallados**. Por eso este plan agrega,
además del delta cero, un criterio que **asserta el MENSAJE o filtra a lo propio**: `test_plan283_help_limpio.py`
(F1) y la verificación por `id` de la huella (F10.2).

**Gates de este plan re-medidos el 2026-08-01, con `backend\venv` y `DATABASE_URL="sqlite:///:memory:"`:**

| Comando | Resultado real |
|---|---|
| `test_harness_flags.py` + `test_flag_wiring.py` + `test_harness_flags_requires.py` | **`70 passed in 22.10s`** (y `--collect-only`: 56 + 5 + 9, **cero `parametrize`**) |
| `test_harness_flags_help.py` | **`4 failed, 4 passed in 2.78s`** |
| `test_harness_ratchet_meta.py` + `test_plan259_ratchet_script_parity.py` | **`16 passed in 1.93s`** |
| `test_error_fingerprints_catalog.py` + `_scan.py` | **`5 failed, 12 passed in 5.20s`** |
| `len(FLAG_REGISTRY)` / `len(PLAIN_HELP)` / diferencia | **447 / 367 / 80** — **VOLÁTILES** |
| lag `.sh` ↔ `.ps1` vs `_PS1_LAG_MAX` | **64 == 64** — **el invariante, cero holgura** |
| `shellNav` + `shellIconsCoverage` + `shellIntegration` (vitest) | **`12 passed, 1 failed`** (9 + 1 + [2 passed, 1 failed]) |

---

## 8. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| R1 | **Los scopes o el device-code de Graph no funcionan en el tenant del operador** (supuesto no verificable contra el repo, D2). | Alta | D1: el camino manual no depende de nada de esto. Si R1 se materializa, se pierden F4 y la mitad de F5; F0-F3 y F6-F10 siguen dando valor. **El plan se implementa en el orden de §12 justamente para que el valor llegue antes que el riesgo.** |
| R2 | **El modelo inventa pendientes.** | Alta | D4: cita literal obligatoria verificada en código, con guard positivo (K2). Los descartados se cuentan y se muestran. |
| R3 | **La transcripción con PII sale a un modelo de terceros.** | Alta | D5 + K5: gate de egress antes del prompt. **Limitación declarada:** los detectores actuales no reconocen nombres propios. |
| R4 | **Una transcripción larga revienta el contexto o el costo.** | Media | F3: cap de 120.000 chars, truncado por turnos completos, y K7 obliga a declarar lo truncado en la minuta. |
| R5 | **Escritura accidental en el tracker del operador.** | Alta | Doble llave (F8): flag OFF de fábrica (excepción B) + `confirm_token` de un solo uso y 120 s. |
| R6 | **Se rompe el ratchet `.ps1` por olvido.** | Media | F10.1 lo declara con el número medido: lag exactamente 64/64, cero holgura. |
| R7 | **`api/tickets.py` está modificado sin commitear y un merge pisa el trabajo del operador.** | Media | D6: blueprint propio, cero ediciones en ese archivo, gateado por `ast` (F8 caso 8). |
| R8 | **Un pytest sin `DATABASE_URL` escribe en la base viva del operador.** | Alta | Cabecera obligatoria `os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")` **antes** de importar la app, en **los 12** archivos de test (molde `tests/test_pipeline_copilot_api.py:16`). |
| **R11** | **[A1] `hablante_matchea` da un falso POSITIVO y Stacky le asigna trabajo real a la persona equivocada.** | Media | Por eso la comparación es **determinista y conservadora** (tokens + `casefold`, sin fuzzy ni distancia de edición): un falso **negativo** degrada a `sin_hablante`, que es seguro; un falso **positivo** no. Ante duda, el sistema no asigna. |
| **R12** | **[A1] La transcripción no trae hablantes** (VTT sin `<v>` ni prefijo `Nombre:`) ⇒ `hablantes == ()` y **todo** queda `sin_hablante`. | Baja | Es el comportamiento correcto: sin hablantes no hay nada que verificar, así que no se autocompleta ningún `assignee`. La UI lo dice una vez, a nivel reunión, en vez de repetirlo por ítem. |
| R9 | **Zona horaria.** Graph devuelve ISO con offset; SQLite guarda naive. | Media | Todo se normaliza a **naive UTC** con el mismo criterio de `services/ado_sync.py:57`. La UI formatea a local. Test explícito en F4 caso 6. |
| R10 | **El operador espera que el calendario se actualice solo.** | Baja | D7 lo prohíbe a propósito (evita categoría A). La UI dice "Actualizado hace N min" con botón explícito. |

---

## 9. Fuera de scope (explícito)

1. **Grabaciones de audio/video.** Solo texto (VTT o plano). Nada de transcribir audio.
2. **Detectores nuevos de PII.** Se reusan los de `egress_policies._DETECTORS` (`:64-93`) tal como están.
3. **Escribir en el calendario** (crear, mover o cancelar reuniones). Solo lectura de Graph.
4. **Enviar la minuta por mail o postearla en Teams.** Fuera. La salida es: pantalla + ticket.
5. **Multiusuario / permisos por asistente.** Mono-operador, sin RBAC.
6. **Traducción.** La minuta sale en el idioma de la transcripción; el prompt pide castellano si la
   transcripción es en castellano.
7. **Vincular un pendiente a un ticket ya existente.** Solo creación (F8).
8. **`.docx`.** Teams permite descargar `.docx`, pero requeriría una dependencia nueva. Solo `.vtt`/`.txt`.
9. **Modificar `api/tickets.py`, `backend/app.py` o `backend/harness_defaults.env`.** Prohibido por **§3.8**
   (tickets: tiene cambios sin commitear del operador), por la **prohibición adicional de F1**
   (`app.py`: `test_harness_flags_restart_required.py:233-245` exigiría `restart_required=True` en las 5
   keys) y por la **pata 8 de F1** (`harness_defaults.env` es un snapshot parcial, "NO tocar a mano").
   *(v2/C19: el v1 decía "por §3.8, F1 y F1".)*
11. **Arreglar los rojos ajenos de §7**, incluido el de `shellIntegration.test.ts`. Cada uno tiene dueño.
12. **Detección de hablante por fuzzy / distancia de edición** (`[A1]`, D9). La comparación es por tokens y
    determinista **a propósito**: ver R11.
10. **Alembic.** El repo **no lo usa** (está en `requirements.txt:4` pero no hay `alembic.ini` ni
    `versions/`). Las tablas se crean con `Base.metadata.create_all` (`db.py:265`).

---

## 10. Glosario

| Término | Qué es en este repo |
|---|---|
| **Arnés / flag del arnés** | El registro `FLAG_REGISTRY` de `services/harness_flags.py` (447 entradas hoy) que el operador ve y toca desde el panel de la UI, sin editar archivos. |
| **Ratchet** | Test que congela una métrica para que no empeore. Acá importan dos: el de registro de archivos de test (`run_harness_tests.sh`/`.ps1`) y los de deuda del frontend. |
| **Runtime** | El CLI que ejecuta agentes: Codex CLI, Claude Code CLI o GitHub Copilot Pro. **Distinto** de `LLM_BACKEND`, que es qué backend usa `copilot_bridge.invoke()`. |
| **`LLM_BACKEND`** | `mock \| vscode_bridge \| copilot \| claude_cli \| local_llm` (`config.py:81`, default `vscode_bridge`). |
| **HITL** | Human-in-the-loop: el operador confirma; el sistema nunca decide solo. |
| **Puerto de tracker** | `get_tracker_provider(project)` (`services/tracker_provider.py:125`): la fachada única para hablar con ADO o GitLab. |
| **Egress** | Salida de datos hacia un modelo. `egress_policies.check()` decide si se permite. |
| **`confirm_token`** | Token de un solo uso con TTL que materializa una confirmación de dos pasos (`services/confirm_token.py`). |
| **WebVTT** | Formato de subtítulos (`WEBVTT` en la primera línea) en el que Teams exporta transcripciones. |
| **Device code flow** | OAuth donde el usuario abre una URL y escribe un código; no necesita secreto de aplicación. |
| **Cita** | Fragmento **copiado tal cual** de la transcripción que respalda un pendiente. Sin cita, el pendiente se descarta. |
| **Turno** | Una intervención de un hablante: `(speaker, start_ms, text)`. |
| **Naive UTC** | `datetime` sin `tzinfo`, ya convertido a UTC. Es la convención del repo (`ado_sync.py:57`). |

---

## 11. Orden de implementación

**v2/C5 — el orden del v1 era imposible de cumplir. Este es el corregido.**

1. **F0** — censo (6 casos). Sin esto, todo lo demás se puede declarar verde contra una foto imaginaria.
2. **F1** — las 5 flags con sus 7 patas + `test_plan283_flags.py` + `test_plan283_help_limpio.py`.
   Bloque **atómico**: no dejar ninguna a medias.
3. **F2** — las 2 tablas + la línea en `db.py:250`.
4. **F3** — `transcript_parser.py` (puro), **incluida `hablantes` y `hablante_matchea` [A1]**.
5. **F6** — el destilado + la matriz de paridad [A2]. ⚠ **Va antes que Graph a propósito:** con F0-F3 + F6
   el operador ya obtiene minuta y pendientes de una transcripción pegada. Todo el valor, cero Microsoft.
6. **F4** — `graph_client.py`.
7. **F5** — `meetings_source.py` + sonda.
8. **F7** — la API. **Ahora va DESPUÉS de F5**, porque `/api/meetings/calendar` llama
   `meetings_source.list_upcoming()` y el **caso 6 de F7 lo assertea**.
9. **F9** — la pantalla (13 patas).
10. **F8** — publicación al tracker. **Último a propósito:** es lo único que escribe afuera.
11. **F10** — ratchets, huella y E2E.

⚠ **Por qué el v1 puso F4/F5 al final, y por qué el argumento era falso.** El v1 los difería *"para que el
valor llegue antes que el riesgo R1"* (los scopes/tenant de Microsoft). Pero **los 11 casos de F4 y los 8
de F5 corren con transporte falso y CERO red**: R1 **no se puede materializar al implementar**, solo en el
smoke **S1**, que ya está declarado como no automatizable. Diferir F4/F5 no reducía **ningún** riesgo de
implementación — y a cambio volvía insatisfacible el criterio de F7. **R1 es un riesgo de runtime, no de
construcción.** Lo que sí protege contra R1 es D1 (el camino manual), que es independiente del orden.

---

## 12. Definición de Hecho (DoD)

**Automatizable — todo esto debe medirse, no afirmarse:**

| # | Comando | Resultado exigido | Fase |
|---|---|---|---|
| 1 | `pytest tests/test_plan283_baseline.py -q` | `6 passed` | F0 |
| 2 | `pytest tests/test_plan283_flags.py -q` | `7 passed` | F1 |
| 3 | `pytest tests/test_plan283_help_limpio.py -q` | `4 passed` | F1 |
| 4 | `pytest tests/test_plan283_store.py -q` | `7 passed` | F2 |
| 5 | `pytest tests/test_plan283_transcript_parser.py -q` | `12 passed` | F3 |
| 6 | `pytest tests/test_plan283_graph_client.py -q` | `11 passed` | F4 |
| 7 | `pytest tests/test_plan283_meetings_source.py -q` | `8 passed` | F5 |
| 8 | `pytest tests/test_plan283_minutes.py -q` | `12 passed` | F6 |
| 9 | `pytest tests/test_plan283_backend_parity.py -q` | `6 passed` | F6 [A2] |
| 10 | `pytest tests/test_plan283_api.py -q` | `10 passed` | F7 |
| 11 | `pytest tests/test_plan283_publish.py -q` | `10 passed` | F8 |
| 12 | `pytest tests/test_plan283_e2e.py -q` | `6 passed` | F10.3 |
| 13 | **Los 12 anteriores en una sola invocación** | **`99 passed, 0 failed`** | — |
| 14 | `pytest tests/test_harness_flags.py tests/test_flag_wiring.py tests/test_harness_flags_requires.py -q` | **`70 passed`** — el mismo de hoy, **delta cero** (v2/C1: **no** 75) | F1 |
| 15 | `pytest tests/test_harness_flags_help.py -q` | `4 failed, 4 passed` — delta cero **y** el #3 en verde | F1 |
| 16 | `pytest tests/test_error_fingerprints_catalog.py tests/test_error_fingerprints_scan.py -q` | `5 failed, 12 passed` — delta cero **y** `meeting_minutes_failed` **no** aparece en ningún mensaje de fallo | F10.2 |
| 17 | `pytest tests/test_harness_ratchet_meta.py tests/test_plan259_ratchet_script_parity.py -q` | `16 passed`, con **`lag == _PS1_LAG_MAX`** (medilo, no lo copies) | F10.1 |
| 18 | `npx vitest run src/services/meetingsModel.test.ts` | `9 passed` | F9 |
| 19 | `npx vitest run src/components/shell/__tests__/shellNav.test.ts` | **`9 passed`** — delta cero | F9 |
| 20 | `npx vitest run src/components/shell/__tests__/shellIconsCoverage.test.ts` | **`1 passed`** | F9 |
| 21 | `npx vitest run src/components/shell/__tests__/shellIntegration.test.ts` | **`2 passed, 1 failed`** — delta cero (el rojo es ajeno, §7) | F9 |
| 22 | `npx tsc --noEmit` | 0 errores | F9 |
| 23 | `python -m compileall backend/services backend/api -q` | sin errores | — |

⚠ **Sobre el punto 13:** `99` es la suma de los 12 criterios de fase —
`6+7+4+7+12+11+8+12+6+10+10+6 = 99`. **Sumala vos antes de empezar.** Si al implementar no da 99, el
criterio **NO se ajusta**: se investiga qué fase quedó corta. *(El v1 exigía 76 y esa suma **sí** cerraba;
lo que no cerraba era el 75 del punto 11 — ver C1.)*
⚠ **Prohibido `xfail`** en cualquier test de este plan: un `xfail(strict=False)` que pasa reporta
`xpassed`, y ningún criterio `N passed` lo cuenta (v2/C4).
⚠ **Prohibido usar `pytest -k`** como evidencia sin declarar el conteo de seleccionados: `-k` sin match
da **exit 0** y parece verde.
⚠ **Prohibido tomar `pytest tests` entero como veredicto:** la suite completa tiene contaminación cruzada
conocida. **Por archivo, siempre.**

**NO automatizable en la corrida (exige backend levantado + un tenant real) — se declara PENDIENTE, nunca verde:**
- **S1.** Device login real contra un tenant de Microsoft: abrir la URL, escribir el código, y que
  `/graph/probe` devuelva los 3 sub-veredictos en verde.
- **S2.** Descargar el `.vtt` de una reunión real de Teams, pegarlo, y verificar a ojo que la minuta y los
  pendientes son **correctos** (la exactitud semántica no la mide ningún test).
- **S3.** Publicar un pendiente real en el ADO o GitLab del operador y confirmar que el work item aparece
  con la cita.

---

## 13. Lo que este plan NO pudo verificar (honestidad explícita)

Un plan que no distingue lo medido de lo supuesto es una trampa para el que lo implementa.

**VERIFICADO en v2 abriendo el archivo o ejecutando el comando** — la tabla completa de anclajes está al
principio del documento (**13 desfasados, 1 incorrecto, el resto OK**). Además, re-medido hoy:
`FLAG_REGISTRY=447` / `PLAIN_HELP=367` / 80 sin ayuda (**volátiles**); `70 passed` de las 3 suites de flags
**y su `--collect-only` = 56+5+9 sin `parametrize`** (la evidencia dura de C1); `4 failed, 4 passed` de la
suite de ayuda; `16 passed` de los ratchets; `5 failed, 12 passed` del catálogo de huellas con
`_STATUS_ENUM = {"resolved","open","by_design"}`; `lag == _PS1_LAG_MAX == 64`; `12 passed, 1 failed` de los
3 archivos de shell; que `ICON_BY_NAME` tiene 18 íconos y los 18 están tomados; que `ALL_TABS` de
`shellNav.test.ts` está hardcodeado; que `truststore.inject_into_ssl()` corre en `app.py:26`; la ausencia
total de código de Graph y de cualquier símbolo `meetings`/`reuniones` en `backend/api`, `backend/services`,
`frontend/src/services` y `frontend/src/pages`; que `SprintBoardPage.tsx:108` está huérfana; que
`api/incidents.py:55` es el único `request.files` del repo.

**MEDIDO PERO VOLÁTIL — no usar como criterio (v2/C17):** los conteos absolutos de archivos **compartidos**
(`FLAG_REGISTRY`=447, `PLAIN_HELP`=367, la diferencia 80, los 788/724 de los ratchets, el 70 de las suites
de flags). Una sesión paralela movió los dos ratchets **dentro de la hora** en que se escribió el v1
(787/723 → 788/724). Los criterios de v2 apuntan a **invariantes** (`lag == _PS1_LAG_MAX`, delta cero,
"mi id no aparece en el mensaje"), no a fotos.

**SUPUESTO, NO VERIFICABLE contra este repo** (son hechos de la plataforma Microsoft):
1. Que `offline_access + Calendars.Read + OnlineMeetingTranscript.Read.All` sean los scopes correctos.
2. Que el tenant del operador habilite device-code para clientes públicos.
3. Que la transcripción sea alcanzable como `/me/onlineMeetings/{id}/transcripts/{tid}/content?$format=text/vtt`
   para reuniones donde el operador **no** es organizador.
4. Que el `.vtt` que exporta Teams hoy tenga la forma `<v Nombre>texto</v>`.

**Los 4 supuestos viven enteros dentro de F4 y la mitad de F5.** Por eso §11 los deja para el paso 7 y 8:
si alguno falla, el operador ya tiene el módulo funcionando por el camino manual.
