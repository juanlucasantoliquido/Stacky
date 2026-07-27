# Plan 260 — Ninguna pipeline corre a ciegas: nombres declarados, faltantes visibles y disparo bloqueado

> ## ESTADO: **CRITICADO v2 -> v3 — NO IMPLEMENTADO**
>
> Escrito el 2026-07-27 sobre la rama `feat/plan-217-migrador-mantis-gitlab` (HEAD `cd20f646`).
> Criticado adversarialmente el 2026-07-27 sobre `83d3b8e0` (v1 -> v2) y **re-criticado el
> 2026-07-27 sobre `53276284` por un juez independiente (v2 -> v3)**, porque la v2 la produjo el
> mismo agente que escribió el plan y eso NO es revisión independiente. Toda la evidencia de este
> documento fue leída del código de esos commits y, donde dice **MEDIDO**, ejecutada de verdad con
> `backend/.venv/Scripts/python.exe` (py3.13.5).
>
> Siguiente eslabón del pipeline de la casa: `implementar-plan-stacky`.

---

## CHANGELOG v2 -> v3

**Veredicto del juez sobre el v2: RECHAZADO (7 bloqueantes).** La v2 arregló de verdad los tres
cables que iban al motor equivocado y su mecánica de flags es **impecable** (verificada pata por
pata contra el código: las 7 patas y sus 7 anclajes dan exacto). Los 4 baselines que el juez
re-corrió dan **el número declarado**: `test_plan251_env_matrix_build.py` 14,
`test_plan251_env_matrix_resolve.py` 15, `test_harness_flags.py` 56,
`test_harness_flags_requires.py` 9. Lo que la v2 **no** vio es que su propia tabla de resolución
reintroduce el falso verde que el plan existe para matar, y que cuatro de sus afirmaciones sobre
el código no son ciertas. Lo corregido:

- **C1 (BLOQUEANTE) — la tabla §4.1 reintroduce el falso verde de §2.3 en ADO+secreto. MEDIDO.**
  §4.1 mandaba `has_value is None` -> celda `manual`. En ADO, todo lo que se declare con
  `secret=True` vuelve del proveedor con `isSecret: true` (`ado_variables.py:38`, escrito en
  `:74`) ⇒ F1 lo convierte en `has_value=None` ⇒ `manual`. Y `pending_count` cuenta **solo**
  `falta` (`pipeline_environments.py:514`). **Medido con el código vivo: declarar baja el contador
  de 2 a 1**; con un único pendiente secreto baja a 0 y `headline()`
  (`frontend/src/devops/pipelineEnvMatrixModel.ts:75-79`, que lee `m.pending_count`) pasa a decir
  *"No falta nada: esta pipeline tiene todo lo que necesita"* con **cero** valores cargados.
  Peor: `test_f3_pending_count_no_baja_al_declarar` no fijaba proveedor ni `kind`, así que un
  modelo menor elige gitlab+variable y sale **verde**. Y la ADICIÓN 3 proyectaba marcando
  `has_value=False`, que en ADO+secreto **no es lo que el proveedor devuelve** ⇒ el canario medía
  otra cosa que la producción. **v3:** §4.1 reescrita (fuente nueva
  `declarada_sin_valor_verificable`), KPI-2 reformulado sobre el **pendiente visible**
  (`falta` + esa fuente), titular del panel corregido en F6, test **parametrizado sobre los 4
  casos** `(proveedor x kind)` y proyección de la ADICIÓN 3 por caso +
  **[ADICIÓN ARQUITECTO 4]**.
- **C2 (BLOQUEANTE) — §4.5 contradecía el KPI-7: la latencia NO quedaba acotada.** El texto decía
  presupuesto duro de 1500 ms y, dos líneas después, *"se compara **después**: no se cancela el
  request en vuelo"*. `resolve()` (`pipeline_env_resolver.py:87`) es **sincrónico y no acepta
  timeout**: medir después no acota nada — si el proveedor tarda 30 s el operador espera 30 s
  **y encima** se degrada. `test_f4_timeout_de_resolucion_degrada` salía verde con un doble lento
  mientras la latencia real seguía sin techo. **v3:** §4.5 usa
  `ThreadPoolExecutor(max_workers=1)` + `fut.result(timeout=1.5)`; el criterio del test es el
  **tiempo de pared medido**, no el verdict.
- **C3 (BLOQUEANTE) — `Readiness` no tenía el campo `source` que dos tests exigían.** §4.3
  congelaba 7 campos y ni uno era `source`, pero
  `test_f4_veredicto_reusado_declara_su_origen` assertaba `readiness.source == "preview_reusado"`.
  **v3:** `source` y `elapsed_ms` declarados en §4.3, con valores cerrados.
- **C4 (BLOQUEANTE) — la ADICIÓN 2 podía reusar un veredicto `degradado` y abrir el gate.** El
  preview sin `?yaml_path=` devuelve `degradado, resolved=False`; si ese veredicto entraba al
  almacén, el `trigger` (que sí trae `yaml_text` y sí podría resolver) reusaba el `degradado` y
  **dejaba pasar** lo que el cálculo fresco habría frenado — exactamente lo contrario de la
  garantía que la propia ADICIÓN 2 declaraba. Además, sin `yaml_path` no hay `yaml_sha256` y la
  clave de reuso quedaba indefinida. **v3:** regla dura — **solo se almacena y solo se reusa un
  veredicto con `resolved=True` y `yaml_sha256` no vacío**, con test.
- **C5 (BLOQUEANTE) — anclaje falso: "el linter no expone `repro`".** La ADICIÓN 1 mandaba a
  escribir un `_REPRO_LINT` a mano *"porque el linter, a diferencia del auditor, no exige `repro`
  por contrato"*. **Falso:** `pipeline_lint.py:70-77` `_rule(code, severity, providers,
  repro=None)` con docstring *"OBLIGATORIO para toda regla"*, `_RULES` guarda la 5-tupla (`:75`) y
  se itera en `:815`; **PL012/PL013/PL014 declaran su `repro`** (`:704-706`, `:732-733`,
  `:750-751`) — verificado en runtime. Un fixture a mano prueba que existe *un* YAML que dispara
  la regla, no que **el repro del catálogo** la dispare: es el mismo falso verde estructural que
  la ADICIÓN 1 decía matar. **v3:** la ADICIÓN 1 lee el repro **del catálogo** en los dos motores.
- **C6 (BLOQUEANTE) — anclaje falso: `audit_yaml` NO devuelve `findings=()` con YAML > 512 KB.**
  C9 del v2 lo afirmaba citando `cicd_audit_core.py:258-259`. Real: ese branch devuelve
  `_aud000(...)` y `_aud000` (`:239-248`) devuelve `AuditReport(ok=True, findings=(f,))` con **un
  finding `AUD000`**. Idem el YAML no parseable (`:260-264`), caso que el v2 **ni mencionaba**.
  Solo el no-dict (`:265-267`) da `findings=()`. Con la premisa falsa, un modelo menor escribe
  `auditado = bool(rep.findings)` y el gate **falla abierto**. **v3:** regla literal
  (`AUD000` + `isinstance(doc, dict)`) y **tres** casos de test.
- **C7 (BLOQUEANTE) — `provider=target` propagaba un valor sin validar y reabría C2 por otra
  puerta.** `commit_route` **no valida** `target`: `api/pipeline_generator.py:65`
  `target = body.get("target")`, y `:67`/`:70` deciden con `target == "ado"` (todo lo demás ⇒
  GitLab). Pasar `target` tal cual a `audit_yaml` manda `None`/`"ADO"`/`"azure_devops"` y
  `check_security` apaga SEC003/SEC005/SEC007 en silencio (`:471,474,477`). **v3:** el gate espeja
  la **misma decisión binaria** que el endpoint, con test de `target` basura.
- **C8 (IMPORTANTE) — F5 5.3 rompía la pureza de `services/pipeline_diff.py`.** El módulo declara
  *"PURO salvo la verificacion opcional de rutas"* (`:9`) y tiene **cero** referencias a `config`
  (verificado). El v2 decía "el gate nuevo se gatea con la flag" sin decir **dónde** se lee ⇒ un
  modelo menor mete `import config` adentro de `review_patch`. Y `GATE_SECRET` **no existe**: las
  constantes viven en `:26-29`. **v3:** la flag la lee el **caller**; `review_patch` recibe
  `secret_gate: bool = True`.
- **C9 (IMPORTANTE) — anclaje falso: `test_plan202_ledger.py` no congela
  `ci_run_ledger.ENTRY_FIELDS`.** Ese archivo prueba **`services/night_foundry_ledger`** (`:17`,
  `:26`) — otro módulo, con su propia `ENTRY_FIELDS`. Verificado además que **ningún** test
  congela el conjunto completo de `ci_run_ledger.ENTRY_FIELDS`: `test_plan258_ledger_veracidad.py`
  solo chequea **pertenencia** (`:155-156`) y un literal del código fuente (`:395`). Y el símbolo
  citado estaba mal: la proyección la hace **`_clean_entry`** (`ci_run_ledger.py:72-79`), no
  `_project_entry`. **v3:** anclajes corregidos y criterio bajado a lo real.
- **C10 (IMPORTANTE) — F7 usaba nombres de campo que el archivo no tiene.**
  `docs/sistema/error_fingerprints.json` es `{schema_version, description, fingerprints:[...]}` y
  cada una de sus **42** huellas usa `id, title, class, status, log_pattern, log_guarded,
  killed_by, killed_commit, date_resolved, guard_test, evidence, note`. No existe un campo `test`
  (es `guard_test`, y en las 42 es una **ruta de archivo**, sin `::funcion`). **v3:** F7 escribe
  con el schema real y el test lo valida contra la última huella existente.
- **C11 (IMPORTANTE) — `test_f4_el_gate_corre_antes_de_la_idempotencia` no probaba el orden.** La
  ventana se escribe en `_record_trigger` (`api/ci.py:130`), que solo corre **después** de un
  disparo exitoso: un request bloqueado nunca llega ahí, **esté el gate antes o después** de
  `:105`. El test pasaba con el gate en cualquier posición. **v3:** se espía
  `should_trigger` y se assertan **0 llamadas**.
- **C12 (IMPORTANTE) — `_RECENT_READINESS` sin poda ni tope.** **v3:** poda por ventana en cada
  escritura + cap duro de 32 entradas, con test.
- **C13 (MENOR) — §4.5 afirmaba "todas las celdas `falta`" y no es cierto.** `_nota_por_kind` está
  en `:471-479` (no `:479`) y devuelve `manual` para `service_connection`, `deploy_path` de
  confianza baja y **cualquier** requirement de confianza baja (`:473-478`). MEDIDO: un YAML ADO
  con `$(DEPLOY_HOST)`/`$(SONAR_TOKEN)` da confianza `baja` para los dos ⇒ sin resolver,
  `pending_count = 0`, no 2. El candado `resolved=False` sigue siendo correcto y necesario, pero
  el test que lo prueba tiene que construir `confidence="alta"` explícita o **no prueba nada**.
- **C14 (MENOR) — anclajes de detalle:** `ado_variables.py:53-79` es `set_variable`, no el camino
  de lectura (`list_variables` es `:25-45`, GET en `:31`); el almacén de idempotencia es
  `_RECENT_TRIGGERS` (`api/ci.py:33`), `_recent_triggers` (`:44`) es el **lector**; el comentario
  de excepciones duras es `:481-489` (no `:483-489`); y la nota de numeración de §7 quedó stale.

**Adiciones del arquitecto (no estaban en el v2):**
- **[ADICIÓN ARQUITECTO 4]** — *Corpus de paridad `proveedor x kind`*: la tabla de verdad de
  `has_value` se congela en un JSON, se prueba **entera** en F1/F3/F4 y un test de completitud
  exige el producto cartesiano. Es lo que habría matado a C1 antes de escribir una línea (§4.6).
- **[ADICIÓN ARQUITECTO 5]** — *El gate declara su propia latencia*: `readiness.elapsed_ms` viaja
  siempre en la respuesta. El KPI-7 deja de ser una promesa del papel y pasa a ser un número que
  el operador ve y que el test compara (§4.3, §4.5).

---

## CHANGELOG v1 -> v2

**Veredicto del juez sobre el v1: RECHAZADO (5 bloqueantes).** El v1 tenía la mecánica de flags
impecable (es la vara alta de su serie) y el orden de fases bien argumentado, pero **tres de sus
cuatro cables de producción estaban conectados al módulo equivocado**. Lo corregido:

- **C1 (BLOQUEANTE) — F5 auditaba con un motor que no contiene las reglas que decía bloquear.**
  `audit_yaml` (`services/cicd_audit_core.py:269-273`) corre `check_security` (SEC\*) +
  `check_recommendations` (OPT\*) y **nada más**: de `pipeline_lint` sólo importa las constantes de
  severidad (`:26`). `PL012`/`PL013`/`PL014` **jamás** entran en `rep.findings`. Encima el filtro
  del v1 pedía `severity == "error"` y las tres PL son `SEV_WARNING`
  (`pipeline_lint.py:703,731,749`). ⇒ `_SECRET_BLOCKING` tenía **2 de 3 códigos inertes** y
  `test_f5_pl013_no_bloquea` era un falso verde estructural. **v2:** dos conjuntos, dos motores,
  filtro **por código, nunca por severidad** (§5 F5) + **[ADICIÓN ARQUITECTO 1]** que hace
  imposible volver a caer en esto.
- **C2 (BLOQUEANTE) — F5 llamaba al auditor con un vocabulario de proveedor que no existe.**
  El v1 escribía `provider=("azure_devops" if target == "ado" else "gitlab")`. El motor de
  auditoría/lint habla **`"ado"`**: `api/pipeline_audit.py:22` `_PROVIDERS = ("ado", "gitlab")`,
  y `check_security` gatea SEC003/SEC005/SEC007 con `if provider == "ado"`
  (`cicd_security_rules.py:471,474,477`). Pasar `"azure_devops"` **apaga reglas en silencio**:
  falla abierto. **v2:** `provider=target` (identidad) + §4.4 nuevo, que declara los **dos
  vocabularios vivos** del repo y dónde se traduce.
- **C3 (BLOQUEANTE) — el diagnóstico del Hueco C sobre el editor NL era falso.**
  `services/pipeline_diff.py:203-204` **ya corre `lint_yaml`** (con PL010..PL014 adentro) en el
  gate G-LINT; lo que pasa es que `:206` sólo falla con `SEV_ERROR`. El fix no es "sumar las
  reglas PL" (ya están) sino **promover el subconjunto de fuga a bloqueante**, y el archivo a
  editar es `services/pipeline_diff.py`, **no** `api/pipeline_editor.py:256`. §2.2 y §5 F5
  reescritos.
- **C4 (BLOQUEANTE) — F4 no decía si el gate resuelve contra el proveedor.** Sin resolver,
  `_nota_por_kind` (`pipeline_environments.py:479`) devuelve `falta` para todo ⇒ una flag
  **default ON** bloquearía **todos** los disparos del operador. Resolviendo, mete una llamada de
  red sincrónica sin techo en el camino crítico del botón rojo. **v2:** §4.5 nuevo (contrato de
  resolución del gate, con presupuesto de latencia duro) + **[ADICIÓN ARQUITECTO 2]**.
- **C5 (BLOQUEANTE) — la flag de escritura quedaba inerte.** `_guard()`
  (`api/pipeline_environments.py:30-36`) es **compartido por todas las rutas del blueprint** y
  chequea `STACKY_PIPELINE_ENV_MATRIX_ENABLED` (default ON). Si `/declare` llamaba `_guard()`,
  la excepción dura de la flag OFF no protegía nada. **v2:** `_guard_declare()` explícito que
  exige **las dos** flags, con test dedicado.
- **C6 (IMPORTANTE) — §3.6 contradecía el código vivo y creaba una fuga.**
  `gitlab_variables.py:96-112` **ya reintenta** con `masked=False` ante un 400 (C8 del Plan 94), y
  la UI ya tiene `canBeMasked` (`VariablesSection.tsx:72`). Peor: declarar siempre `secret=False`
  deja la variable con `masked:false`, así que **cuando el operador cargue el secreto, GitLab lo
  imprime en claro en el log del job**. §3.6 reescrito: se declara con `secret=True` y se **reusa
  el reintento existente**, devolviendo `needs_masking`.
- **C7 (IMPORTANTE) — `trigger_preview_route` es un GET** (`api/ci.py:156`, `request.args`): no
  tiene body, así que la fuente 1 del YAML era inalcanzable y el preview habría dado `degradado`
  siempre. **v2:** el preview pasa a aceptar el YAML por el canal correcto (§5 F4).
- **C8 (IMPORTANTE) — divergencia de nombre de campo:** el hermano `/analyze` usa **`yaml_text`**
  (`api/pipeline_environments.py:41`), el v1 escribía `yaml`. Unificado a `yaml_text`.
- **C9 (IMPORTANTE) — el gate F5 fallaba abierto con YAML grande o no parseable:** `audit_yaml`
  devuelve `ok=True` y `findings=()` si el YAML supera 512 KB (`cicd_audit_core.py:258-259`) o no
  es un dict (`:265-267`). Cubierto con dos casos y una regla de "no auditado ⇒ no se commitea".
- **C10 (IMPORTANTE) — baselines faltantes:** tocar `ENTRY_FIELDS` impacta
  `tests/test_plan202_ledger.py:48` y `tests/test_plan258_ledger_veracidad.py:155-158,395`.
  Agregados a los criterios binarios de F4.
- **C11 (IMPORTANTE) — frontera de merge ausente.** §10 nuevo: cómo se ordena el 260 con sus
  hermanos 263/264/265 en los 6 archivos compartidos.
- **C12 (IMPORTANTE) — casos borde de `/declare` sin cubrir:** ADO sin definition
  (`ado_variables.py:20-23` `VariablesUnavailableError`) y el status del rechazo de `keys`.
- **C13 (MENOR) — citas degradadas corregidas:** `ado_variables.py:41`->**42**;
  `gitlab_variables.py:38`->**41**; `PipelineEnvMatrixPanel.tsx:80`->**79/84**;
  `pipeline_generator.py:63`->**62**; `PipelineTriggerCard.tsx:111-134` es el handler
  `handleTrigger`, **no** el modal.
- **C14 (MENOR)** — huella de regresión en `docs/sistema/error_fingerprints.json` (F7, nueva).
- **C15 (MENOR)** — la "lista de excepciones duras" de `test_harness_flags.py:483-489` es **prosa
  en un comentario**, no una estructura ejecutable: se dice así para que nadie busque una tupla.
- **C16 (MENOR)** — `CIPipeline.trigger` tiene firma **posicional de 5 argumentos**
  (`PipelineTriggerCard.tsx:117`) y su `catch` (`:128-131`) colapsa el 409 a `err.message`.

**Adiciones del arquitecto (no estaban en el v1):**
- **[ADICIÓN ARQUITECTO 1]** — *Gate anti-inerte*: cada código bloqueante se prueba con el
  `repro` que el propio motor ya exige por contrato (§5 F5).
- **[ADICIÓN ARQUITECTO 2]** — *Presupuesto de latencia + reuso del veredicto por
  `pending_fingerprint`* dentro de la ventana de 60 s que ya existe para idempotencia (§4.5, F4).
- **[ADICIÓN ARQUITECTO 3]** — *`declare-preview` proyecta el `pending_count` posterior*: el
  operador ve **antes** de escribir que la alerta no va a bajar (§5 F3).

---

## 0. Frontera de superficie — enmienda declarada al §3.2 del Plan 251

El Plan 251 declaró, textualmente y por escrito, *"SOLO LECTURA: no escribe en el repo, ni en
el proveedor, ni en el servidor"* (`backend/config.py:1461-1462`), y su panel lo repite como
decisión de diseño (`frontend/src/components/devops/PipelineEnvMatrixPanel.tsx:23-25`:
*"acá no hay una segunda superficie de escritura"*).

**Este plan enmienda esa frontera de forma explícita y acotada**, y no en silencio:

- La escritura **no** vive en el módulo del 251. `services/pipeline_environments.py` sigue PURO
  y su `test_f1_modulo_puro` sigue válido.
- La única escritura nueva pasa por el **puerto ya existente del Plan 94**
  (`VARIABLES_PORT_METHODS = ("list_variables", "set_variable", "delete_variable")`,
  `services/ci_variables.py:63`), detrás de una flag **default OFF** y con `confirm=True`.
- Lo que se escribe es **un nombre con valor vacío**. Nunca un valor, nunca un secreto,
  nunca un placeholder que parezca un valor real.
- **(v2, C5)** La frontera se hace cumplir con un guard **propio**, no con el compartido del 251:
  ver §5 F3. El guard compartido `_guard()` chequea la flag de la matriz, que está **ON**; usarlo
  para `/declare` dejaría la excepción dura escrita en el papel y abierta en el código.

---

## 1. Objetivo + KPI

**Objetivo:** que entre "Stacky detectó que esta pipeline necesita `DEPLOY_HOST` y `SONAR_TOKEN`"
y "la pipeline corre" no quede ni un paso a cargo de la memoria del operador, ni un disparo a
ciegas, ni un secreto en claro en el YAML.

| KPI | Medición | Meta |
|---|---|---|
| **KPI-1** | Nombres que el operador tiene que tipear a mano para completar una pipeline detectada | **0** (los declara Stacky; el operador solo pega el valor) |
| **KPI-2** *(v3, C1)* | Declarar los nombres **no** apaga la alerta de faltantes | El **pendiente visible** (`falta` + `manual` con `source == "declarada_sin_valor_verificable"`) **no baja** al declarar, en **los 4 casos** `proveedor x kind`. Hoy baja a 0 (**MEDIDO**, §2.3) y con la tabla del v2 seguía bajando en ADO+secreto (**MEDIDO**, §2.5) |
| **KPI-3** | Disparos de pipeline con valores obligatorios sin cargar | **0** con evidencia positiva de faltantes; **advertencia** cuando Stacky no puede saberlo |
| **KPI-4** | Caminos de escritura de YAML que commitean un secreto literal | **0** de 2 (hoy **2** de 2 — §2.2) |
| **KPI-5** | Valores de variables que salen por una respuesta HTTP o un log | **0** (control negativo explícito en F1, F3 y F5) |
| **KPI-6** *(v2, C1)* | Códigos declarados bloqueantes que el motor invocado **no puede producir** | **0** (probado regla por regla con su `repro`) |
| **KPI-7** *(v2, C4; mecanismo reescrito v3, C2)* | Milisegundos que el gate agrega al camino del botón de disparo | **<= 1500 ms de espera REAL**, acotados con `future.result(timeout=1.5)` — no con una medición post-hoc. Excedido ⇒ `degradado`, nunca bloqueo. El número viaja en `readiness.elapsed_ms` (ADICIÓN 5) y el test compara **tiempo de pared**, no el verdict |

**Trabajo extra para el operador: ninguno.** Todo lo que este plan agrega son cosas que hoy el
operador hace a mano (crear la variable, acordarse de cargarla) o que hoy no hace nadie
(chequear antes de disparar).

---

## 2. Evidencia real (leída, y donde dice MEDIDO, ejecutada)

### 2.1 Lo que YA existe y este plan REUSA sin tocar

| Capacidad | Dónde | Estado |
|---|---|---|
| Detección de qué valores exige una pipeline (6 clases) | `services/pipeline_environments.py:321` `extract_requirements` | **Completa.** `VALUE_KINDS` en `:22` |
| Entornos derivados + matriz + conteo de faltantes | `:418` `derive_environments`, `:482` `build_matrix`, `pending_count` en `:514` | **Completa** |
| Resolución solo-lectura contra 5 fuentes | `services/pipeline_env_resolver.py:87` `resolve` | **Completa** |
| Alerta al operador | endpoint `api/pipeline_environments.py:39`; titular *"Te faltan N valores…"* en `frontend/src/devops/pipelineEnvMatrixModel.ts:75` | **Completa** |
| Puerto de escritura de variables (ADO + GitLab) | `services/ado_variables.py:53`, `services/gitlab_variables.py:62`, puerto en `services/ci_variables.py:63` | **Completo, y ya empuja de verdad** |
| **Reintento determinista de masking en GitLab (C8 del 94)** *(v2, C6)* | `services/gitlab_variables.py:96-112` | **Completo — se REUSA, no se reinventa** |
| Reglas de secretos en el **linter** | `services/pipeline_lint.py:703` (PL012), `:731` (PL013), `:749` (PL014) — entry point `:791` `lint_yaml(yaml_text, provider, known_variables=None)` | **Completas** |
| Reglas de secretos en el **auditor** | `services/cicd_security_rules.py:110` (SEC001), entry point `check_security` en `:454` | **Completas** |
| Auditor determinista | `services/cicd_audit_core.py:251` `audit_yaml(yaml_text, *, provider, profile, mode, pipeline_key, suppressions)` | **Completo** |
| **`repro` obligatorio por regla — en LOS DOS motores** *(v2 ADICIÓN 1; corregido v3, C5)* | Auditor: `services/cicd_audit_core.py:106-115` (sin `repro=(provider, yaml_minimo)` la regla **no se registra**). **Linter: `services/pipeline_lint.py:70-77`** — `_rule(..., repro=None)` con docstring *"OBLIGATORIO para toda regla"*, guardado en `_RULES` (`:75`) y desempaquetado en `:815`; PL012/PL013/PL014 lo declaran (`:704-706`, `:732-733`, `:750-751`) | **Completo en los dos — es la palanca anti-inerte, y NO hay que escribir fixtures a mano** |

**No hay que construir ni un motor.** Todo el material es puro, determinista y está probado.
Lo que falta son tres cables y una verdad. **Pero (v2) los cables van a motores distintos, y
conectarlos al equivocado es exactamente el error que el v1 cometió tres veces.**

### 2.2 Los tres huecos, con archivo:línea

**Hueco A — nadie declara los nombres.** `grep set_variable` sobre `api/` + `services/` da **un
solo** call-site: `api/devops_variables.py:82`, el alta manual de a una. Y la UI **exige** valor:
`frontend/src/components/devops/VariablesSection.tsx:71`
`const canSubmit = !!key.trim() && !keyError && !!value;` ⇒ desde la UI es **imposible** declarar
un nombre sin valor. El CTA "Completar" de la matriz solo navega
(`PipelineEnvMatrixPanel.tsx:79` `irAVariables = () => ctx.setActiveSection?.("variables")`,
usado en `:84`) y **no lleva el nombre**: el operador tiene que volver a tipearlo.

**Hueco B — el disparo no mira nada.** `api/ci.py:75-149` `trigger_pipeline_route`: flag (`:82`),
`confirm=True` (`:88`), `normalize_ref` (`:93`), `validate_trigger_credentials` (`:100`, y
`_read_pat_scopes` **siempre devuelve `None`** — `api/ci.py:60-68` — así que nunca bloquea) e
idempotencia (`:105-106`). **Ni una línea consulta variables, matriz de entornos ni preflight.**
`services/ci_preflight.py:22` `PREFLIGHT_PORT_METHODS = ("lint_yaml", "list_runners")`: el puerto
de preflight **no tiene** método de variables. `services/ci_trigger_rules.py` son 3 funciones
puras sobre scopes/ref/idempotencia, ninguna sobre valores.

**Hueco C — los dos caminos que escriben YAML no bloquean por secreto literal.**
**(v2, C3: el diagnóstico del v1 era parcialmente falso y hay que decirlo con precisión, porque el
fix cambia según el camino.)**

| Camino | Qué corre hoy | Qué falta de verdad |
|---|---|---|
| `api/pipeline_generator.py:52-89` `commit_route` | `confirm=True` (`:59`) + `spec.validate()` (`:62`) + `writer.commit_file` (`:77-82`) | **Cero lint, cero audit.** Es el hueco literal que describía el v1 |
| `api/pipeline_editor.py:256-262` (422 `gates_en_rojo`) | El `review` lo arma **`services/pipeline_diff.py:196` `review_patch`**, que en `:203-204` **YA CORRE `lint_yaml`** (PL010..PL014 incluidas) y en `:212+` corre el audit semántico | **El gate ve PL012/PL014 y decide no bloquear**: `:206` `lint_err = tuple(f for f in nuevos if f.severity == SEV_ERROR)` y las PL de secreto son `SEV_WARNING` ⇒ caen en `new_warnings` y `passed=True` |

`grep audit_yaml` da un único consumidor: `api/pipeline_audit.py:49`, un endpoint bajo demanda que
no es gate de nada.

> **Deuda ajena anotada, NO se arregla acá:** `pipeline_diff.py:203-204` llama `lint_yaml(..., "ado")`
> **hardcodeado**, así que para un proyecto GitLab el gate del editor corre el perfil ADO. Es del
> Plan 250. Se documenta como riesgo (R11) y se deja quieto: arreglarlo es scope creep.

### 2.3 La trampa central del plan, **MEDIDA** (no argumentada)

Ambos proveedores **hardcodean** `has_value: True`:

- `services/ado_variables.py:42` -> `"has_value": True,  # Si está en la definition, tiene valor`
- `services/gitlab_variables.py:41` -> `"has_value": True,  # Si está en la lista, tiene valor`
  (y de nuevo, sin comentario, en `list_variables_scoped`, `services/gitlab_variables.py:57`)

Y `resolve()` **ni siquiera mira ese campo**: `services/pipeline_env_resolver.py:105-109` arma
`por_key` solo con `key` + `environment_scope`, y `_resolver_celda` (la función arranca en `:131`)
devuelve `("definido", "caja_fuerte", None)` por la **mera presencia de la key**: en `:142-143`
para ADO y en `:144-147` para GitLab. **Son dos branches: cambiar uno solo deja el bug vivo en el
otro proveedor.**

Corrida real (`backend/.venv`, py3.13.5), sobre una pipeline ADO con `WebAppName: $(DEPLOY_HOST)`:

```
reqs: [('DEPLOY_HOST', 'variable', False), ('$(SONAR_TOKEN)', 'service_connection', False)]
A) nadie declaro nada            -> pending_count = 1  [('DEPLOY_HOST', 'falta',    'ninguna')]
B) nombres declarados SIN valor  -> pending_count = 0  [('DEPLOY_HOST', 'definido', 'caja_fuerte')]
```

> **Declarar el nombre APAGA la alerta.** Un plan que empezara por el Hueco A y dejara esto para
> después construiría, con la mejor intención, exactamente el falso verde que el requerimiento
> quiere evitar: la pipeline queda "sin faltantes" y sin un solo valor cargado. **Por eso F1 (la
> verdad sobre `has_value`) va ANTES que F2/F3 (declarar), y no al revés.**

Esto además ya es un bug latente **hoy**: si el operador crea a mano una variable y le deja el
valor vacío, la matriz le dice `definido`.

**(v2)** F4 también depende de F1: sin `has_value` veraz, el gate del disparo hereda el mismo
falso verde y deja pasar pipelines con variables declaradas y vacías. El orden **F1 -> F2 -> F3 ->
F4** no es cosmético.

### 2.4 Lo NO verificado (declarado, para que el implementador NO lo asuma)

1. **Que ADO devuelva el `value` de una variable no-secreta en el GET de la definition.** El
   camino de lectura es `ado_variables.py:25-45` `list_variables` (el GET está en `:31` y el dict
   se construye en `:37-44`) — **(v3, C14)** el v2 citaba `:53-79`, que es `set_variable`. El
   código asume que `var_def` trae `value`, pero no se ejecutó contra un ADO real. F1 debe
   degradar a `None` (desconocido) si el campo no viene, **nunca** asumir.
2. **Que ADO permita distinguir un secreto vacío de uno cargado.** Casi seguro que **no**: ADO
   devuelve `value: null` para `isSecret: true`. F1 lo trata como `None` explícito, no como `True`.
3. **Que el inventario del Plan 246 permita resolver el YAML por `(project, ref)`.**
   `services/pipeline_inventory.py:511` `scan_repo_pipelines(root)` escanea el repo local y
   `:108` `normalize_yaml_path` normaliza rutas, así que la entrada tiene `yaml_path`; **no se
   verificó** que se pueda mapear una `ref` a un archivo del workspace. F4 lo usa como fuente
   **2 de 3** y degrada con nota explícita si no puede.
4. **Smoke visual** (F6): no automatizable, no hay `jsdom` ni RTL instalados.
5. **(v2, C6) Que GitLab rechace `masked=true` con valor vacío.** El v1 lo afirmaba como hecho
   citando `gitlab_variables.py:83-90`, que **no muestra ningún rechazo** (es la construcción del
   body, `:87-92`). Lo único verificado es que **existe un reintento** ante un 400 (`:96-112`). ⇒
   F3 **no decide de antemano**: manda `secret=True` y deja que el reintento ya probado decida,
   leyendo el `masked` que `set_variable` devuelve en `:123-127`.

### 2.5 **(v3, C1 — NUEVA)** La trampa que la v2 dejó viva en ADO+secreto, **MEDIDA**

La v2 arregló los tres cables al motor equivocado pero su tabla §4.1 reabría el falso verde de
§2.3 por el camino más peligroso. Cadena de hechos, cada uno leído del código:

1. `/declare` escribe con `set_variable(key, "", secret=True)` para un requirement secreto.
2. ADO guarda `{"value": "", "isSecret": True, "allowOverride": False}`
   (`services/ado_variables.py:72-76`).
3. Al releer, `list_variables` calcula `is_secret = bool(var_def.get("isSecret"))`
   (`:38`) ⇒ **True**.
4. La regla F1 del v2 dice: `is_secret` ⇒ `has_value = None`.
5. La tabla §4.1 del v2 dice: `None` ⇒ celda `("manual", "caja_fuerte", ...)`.
6. `pending_count` cuenta **solo** `state == "falta"` (`pipeline_environments.py:514`).

Corrida real (`backend/.venv`, py3.13.5), con dos requirements `confidence="alta"`
(`SONAR_TOKEN`/secret y `DEPLOY_HOST`/variable) sobre `provider="azure_devops"`:

```
A) nadie declaro nada                 -> pending_count = 2  [SONAR_TOKEN falta,  DEPLOY_HOST falta]
B) declarados con la tabla del v2     -> pending_count = 1  [SONAR_TOKEN manual, DEPLOY_HOST falta]
```

**El contador BAJÓ al declarar.** Y `headline()`
(`frontend/src/devops/pipelineEnvMatrixModel.ts:75-79`) lee **`m.pending_count`**: en una
pipeline cuyo único pendiente es un secreto, el titular pasa de *"Te falta 1 valor"* a
***"No falta nada: esta pipeline tiene todo lo que necesita"*** con **cero** valores cargados.

> **La causa raíz no fue un typo: fue razonar sobre "declarar" como si los dos proveedores y los
> dos `kind` se comportaran igual.** No lo hacen, y la asimetría vive en el código desde el Plan
> 94. Por eso el fix del v3 no es cambiar un `if`: es §4.1 + el **corpus de paridad** de la
> [ADICIÓN ARQUITECTO 4] (§4.6), que hace que un caso no cubierto sea **rojo**, no invisible.

---

## 3. Principios y guardarraíles (NO negociables)

### 3.1 El valor nunca sale, ni siquiera por un booleano de más
Este plan hace `has_value` **verdadero**, y eso es exactamente `bool(value)` — un bit. Está
permitido porque el campo **ya existe y ya promete eso**. Lo que sigue prohibido, con control
negativo en F1, F3 y F5: que el `value` entre a un retorno, a un payload JSON, a un log o a un
mensaje de excepción. Se conserva `_mensaje_seguro` (`pipeline_env_resolver.py:63-76`): prohibido
`str(e)` de una excepción desconocida.

### 3.2 Declarar un nombre no es cargar un valor, y el sistema nunca los confunde
Un nombre declarado con valor vacío es **una variable que sigue faltando**. La única diferencia
visible es el `source`, que pasa a decir por qué.

**(v3, C1) Y hay DOS formas de "declarada sin valor", porque los proveedores no son simétricos:**

| Caso | Celda | Cuenta en el pendiente **visible** | ¿Bloquea el disparo? |
|---|---|---|---|
| El proveedor confirma que está vacía (`has_value=False`) | `("falta", "declarada_sin_valor")` | **sí** | **sí** (evidencia positiva) |
| El proveedor no puede saberlo (`has_value=None`, ADO+secreto) | `("manual", "declarada_sin_valor_verificable")` | **sí** | **no** (§3.4: nunca bloquear por ignorancia) |

**Separar "lo que bloquea" de "lo que el operador todavía tiene que hacer" es el corazón del
arreglo del v3.** El gate del disparo no puede frenar por ignorancia (riel duro), pero la
**alerta** sí tiene que seguir encendida, porque el trabajo sigue pendiente. Confundir las dos
cosas en un solo contador es lo que produjo el falso verde de §2.5.

Nota de coherencia: `pending_fingerprint` **ya** tiene la semántica correcta — canoniza
`falta` **y** `manual` (`pipeline_environments.py:464-468`). El único lugar donde el sistema se
mentía era el **titular**, que lee `pending_count`.

### 3.3 Nunca un placeholder que parezca un valor
Prohibido escribir `"CHANGEME"`, `"TODO"`, `"xxx"` o cualquier cosa que un runner pueda tomar
como válida. El valor declarado es la cadena vacía y nada más. Un placeholder es peor que la
ausencia: hace fallar el deploy en producción en vez de fallar en el gate.

### 3.4 Human-in-the-loop
- Declarar nombres: flag **default OFF** + `confirm=True` + preview de exactamente qué nombres se
  van a crear, antes de crear ninguno. **(v2)** El preview además dice cuánto **NO** va a bajar el
  contador (ADICIÓN 3): el operador confirma con la consecuencia a la vista.
- Disparar con faltantes: **no se autocompleta nada**. El operador puede seguir adelante, pero
  solo con un `acknowledge_missing=True` explícito, que queda en la bitácora.
- El gate **nunca bloquea por ignorancia**: sin evidencia positiva de faltantes, advierte.
- **(v2, C4) Corolario duro:** "no pude resolver" e "ignorancia" son lo mismo. Un gate que no
  logró consultar al proveedor **no bloquea jamás**, aunque la matriz sin resolver diga `falta`
  en todas las celdas.

### 3.5 Núcleo determinista, sin LLM ⇒ paridad de runtimes trivial
Nada de este plan llama a un modelo. Los 3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot
Pro) se comportan idéntico porque no hay nada que dependa de un modelo: no hay prompt, no hay
tool-calling, no hay parsing de salida de LLM. **Impacto por runtime: ninguno. Fallback por
runtime: no aplica (no hay capacidad diferencial que degradar).** Los tests corren con
`LLM_BACKEND=mock`, que es el default de tests, y por eso son idénticos en los 3.

### 3.6 Multiproveedor sin denominador común falso — **REESCRITO (v2, C6)**
ADO y GitLab **no** son simétricos y el plan no finge que lo sean:

| | ADO | GitLab |
|---|---|---|
| Distingue vacío de cargado (no-secreto) | sí, si el GET trae `value`; si la clave falta -> `None` | sí (el GET trae `value`) |
| Distingue vacío de cargado (secreto) | **no** (`value: null`) ⇒ `has_value=None` | sí |
| Acepta declarar una key vacía enmascarada | sí (`isSecret` es un bit aparte) | **no verificado** (§2.4 punto 5) |

**Lo que el v1 hacía mal:** decidía de antemano declarar **siempre** `secret=False` en GitLab.
Eso tiene dos problemas y ninguno es teórico:

1. **Contradice el código vivo.** `gitlab_variables.py:96-112` (C8 del Plan 94) ya reintenta con
   `masked=False` ante un 400 y **devuelve el `masked` real** en `:123-127`. El v1 reinventaba,
   peor, una decisión que el puerto ya toma bien.
2. **Crea la fuga que el plan dice evitar.** Una variable creada con `masked:false` en GitLab
   **no se enmascara en la salida del job**. Si el operador después pega ahí un token, GitLab lo
   imprime en claro en el log de la corrida. El KPI-5 del propio plan quedaba violado por su
   propia decisión de diseño, un paso después.

**Regla v2:** en GitLab se declara con **`secret=True` cuando el requirement es un secreto**, se
deja actuar al reintento existente, y `/declare` devuelve por cada key el `masked` **efectivo**.
Las keys que quedaron en `masked=False` se listan en `needs_masking`, y la UI (F6) muestra un
aviso accionable: *"al cargar el valor, marcá la casilla 'secreta' — si no, GitLab lo va a
imprimir en el log del job"*. **Ese aviso no es trabajo extra: es la misma casilla que el
formulario ya tiene** (`VariablesSection.tsx:72` ya calcula `maskingWarning` con `canBeMasked`).

### 3.7 No degradar / backward-compatible
- `CELL_STATES` (`pipeline_environments.py:23`) **no se toca**: un nombre declarado sin valor es
  `falta`, un estado que ya existe. `build_matrix` acepta cualquier `(state, source, note)` que
  venga en `resolutions` (`:495-500`) y `pending_count` cuenta `state == "falta"` (`:514`), así
  que **no hace falta ni una línea nueva en `build_matrix`**.
- **(v3, C1)** `SOURCES` (`:24-25`) crece en **DOS** elementos, al final, aditivo:
  `"declarada_sin_valor"` y `"declarada_sin_valor_verificable"`. La tupla actual tiene **7**
  elementos: el control de regresión sigue siendo `SOURCES[:7]` byte-idéntica.
- `VARIABLES_PORT_METHODS` (`ci_variables.py:63`) **no se toca**.
- `list_variables()` conserva sus claves; `has_value` cambia de literal `True` a
  `True|False|None`. Baselines a respetar: `test_plan94_variables_providers.py` **13 passed**,
  `test_plan94_variables_endpoints.py` **14 passed**, `test_plan94_variables_pure.py` **3 passed**
  (**MEDIDOS hoy**).
- **(v2, C7)** `trigger_preview_route` sigue siendo un **GET** y sigue devolviendo todo lo que
  devuelve hoy. El campo `readiness` es **aditivo y opcional**: sin `yaml_path` en la query, el
  payload es byte-idéntico al actual salvo `readiness: {"verdict": "degradado", ...}`.
- **(v2, C10; anclajes corregidos v3, C9)** `ENTRY_FIELDS` (`services/ci_run_ledger.py:30-34`)
  crece en 2 claves **al final**. Consecuencia declarada: **todas** las filas del ledger (incluso
  las que no vienen de este plan) pasan a llevar `env_ack: null` y `pending_fingerprint: null`,
  porque **`_clean_entry`** (`:72-79`, la proyección literal está en `:74`) proyecta el conjunto
  completo. El símbolo se llama `_clean_entry`, **no** `_project_entry`: grepear el nombre
  equivocado da 0 hits. Es aditivo y `schema_version` **no** se bumpea (el 258 lo reservó para
  cambios de forma, no de allowlist).

### 3.8 Mono-operador
Sin roles, sin permisos. `current_user` es un header sin validar. Nada de este plan asume que
alguien "no puede" hacer algo por quién es. El `acknowledge_missing` no es un permiso: es una
confirmación del único operador que hay.

---

## 4. Contrato de datos

### 4.1 `has_value` pasa a ser tri-estado (F1)

```python
# services/ci_variables.py — documentación del puerto (la tupla NO cambia)
# has_value: True  -> el proveedor confirma que hay un valor cargado
#            False -> el proveedor confirma que el valor esta VACIO
#            None  -> el proveedor NO puede saberlo (ADO + isSecret) -> tratar como DESCONOCIDO
```

Regla de resolución en `_resolver_celda` (F1) — **REESCRITA (v3, C1)**:

| `has_value` | Celda | Pendiente **visible** | Gate del disparo |
|---|---|---|---|
| `True` | `("definido", "caja_fuerte" \| "scope_proveedor", None)` — como hoy | no | `ok` |
| `False` | `("falta", "declarada_sin_valor", "el nombre existe en el proveedor pero no tiene valor")` | **sí** | `bloquea` |
| `None` | `("manual", "declarada_sin_valor_verificable", "el proveedor no informa si este secreto tiene valor: verificalo vos")` | **sí** | `advierte` |

**Lo que cambió respecto del v2 y por qué (§2.5, MEDIDO):** el v2 mandaba el caso `None` a
`source="caja_fuerte"`, que es **el mismo `source` que usa una variable con valor cargado**. Con
eso, la celda quedaba indistinguible de "resuelta" para cualquier consumidor que mirara el
`source`, y como `pending_count` solo cuenta `falta`, el contador **bajaba al declarar** en
ADO+secreto. La fuente nueva `declarada_sin_valor_verificable` es lo que hace la diferencia
**observable y contable** sin tocar `CELL_STATES` ni `pending_count`.

`None` sigue cayendo en `manual`, no en `definido` ni en `falta`: **no bloquea el disparo**
(§3.4, no bloquear por ignorancia) pero **sí cuenta como pendiente visible** (§3.2). Y entra en
`pending_fingerprint` (`pipeline_environments.py:464-468` canoniza `falta` **y** `manual`), que
ya tenía la semántica correcta.

**Regla de conteo visible (única, y se implementa UNA vez, en el modelo puro del frontend):**

```
pendiente_visible(m) = #{ c in m.cells : c.state == "falta" }
                     + #{ c in m.cells : c.state == "manual"
                                     and c.source == "declarada_sin_valor_verificable" }
```

`to_json_payload` serializa cada celda con `asdict(c)` (`pipeline_environments.py:534`), así que
`source` **ya viaja** por la frontera JSON: no hace falta ni un campo nuevo en el contrato del
251. `pending_count` **no se toca** (contrato congelado del 251, `test_plan251_env_matrix_build.py`
lo cubre) — lo que cambia es **qué número muestra el titular**, y eso vive en `.ts` puro.

### 4.2 Plan de declaración (F2) — puro, sin I/O

```python
# services/pipeline_env_declare.py   (módulo NUEVO — el 251 queda intacto)
@dataclass(frozen=True)
class DeclareItem:
    key: str            # nombre a crear en el proveedor
    secret: bool        # is_secret del requirement, en AMBOS proveedores (v2 §3.6)
    reason: str         # por que se declara (kind + entorno donde falta)
    note: str           # que tiene que hacer el operador despues

@dataclass(frozen=True)
class DeclarePlan:
    items: tuple        # tuple[DeclareItem, ...], orden determinista (por key)
    skipped: tuple      # tuple[(key, motivo)] — lo que NO se declara y por que
    provider: str

def plan_declaration(matrix, provider: str) -> DeclarePlan: ...

def proyectar_has_value(provider: str, es_secreto: bool) -> object:
    """(v3, C1) Que va a devolver el proveedor DESPUES de declarar la key con valor vacio.
    UNICA fuente de verdad de la proyeccion (ADICION 3). ADO+secreto -> None; el resto
    -> False. Lo prueba, fila por fila, plan260_corpus/declare_matrix.json (§4.6)."""
```

**Qué se declara** (y nada más): celdas con `state == "falta"` cuyo requirement tenga
`kind in ("variable", "secret")` y `name` que pase `validate_variable_key`
(`ci_variables.py:13`).

**Qué se SALTA, con motivo explícito en `skipped`:**

| kind | Motivo |
|---|---|
| `server` | no es una variable: se carga en el registro de servidores (Plan 91) |
| `deploy_path` | es una ruta, no una variable de pipeline |
| `service_connection` | se crea en la UI del proveedor, no por API de variables |
| `parameter` | tiene default en el YAML o se elige al encolar |
| key inválida | `validate_variable_key` la rechaza |
| `state != "falta"` | ya está resuelta, o es `manual` (no sabemos si falta) |

**(v2)** `provider` acá es el vocabulario de `pipeline_environments` (`"azure_devops"` /
`"gitlab"`, ver §4.4). `plan_declaration` **no** traduce: sólo lo propaga.

### 4.3 Veredicto de disparo (F4) — puro, sin I/O

```python
# services/ci_env_gate.py   (módulo NUEVO)
VERDICTS = ("ok", "bloquea", "advierte", "degradado")
SOURCES_READINESS = ("calculado", "preview_reusado")     # (v3, C3) valores CERRADOS

@dataclass(frozen=True)
class Readiness:
    verdict: str
    pending_count: int          # celdas 'falta'  (evidencia POSITIVA de faltante)
    unknown_count: int          # celdas 'manual' (el proveedor no puede saberlo)
    pending_fingerprint: str
    missing: tuple              # tuple[(name, environment)] — SOLO nombres, jamas valores
    reasons: tuple
    resolved: bool              # (v2, C4) True SOLO si se consulto al proveedor de verdad
    source: str = "calculado"   # (v3, C3) uno de SOURCES_READINESS — lo exigen 2 tests de F4
    elapsed_ms: int = 0         # (v3, ADICION 5) ms REALES que el gate espero por el proveedor

def evaluate_readiness(matrix, *, resolved: bool,
                       source: str = "calculado", elapsed_ms: int = 0) -> Readiness: ...
```

> **(v3, C3)** El v2 congelaba 7 campos y ninguno era `source`, pero
> `test_f4_veredicto_reusado_declara_su_origen` assertaba `readiness.source == "preview_reusado"`:
> el test no compilaba contra su propio contrato. `source` y `elapsed_ms` son **campos con
> default**, así que van al final del dataclass y no rompen ninguna construcción posicional.
> Ojo con la firma: el v2 escribía `evaluate_readiness(matrix, *, source, resolved)` con `source`
> **obligatorio**; acá es opcional, porque el 99 % de las llamadas son el cálculo normal.

| Situación | `verdict` | Efecto en `POST /trigger` |
|---|---|---|
| **`resolved is False`** *(v2, C4)* | `degradado` | deja pasar, lo dice en la respuesta. **Se evalúa PRIMERO: sin resolución no hay bloqueo posible** |
| `pending_count > 0` | `bloquea` | **409** salvo `acknowledge_missing=True` |
| `pending_count == 0` y `unknown_count > 0` | `advierte` | deja pasar, lo dice en la respuesta |
| `pending_count == 0` y `unknown_count == 0` | `ok` | deja pasar |
| No se pudo obtener el YAML | `degradado` | deja pasar, lo dice en la respuesta |

**Orden de evaluación literal (no negociable):** `resolved is False` se chequea **antes que
todo lo demás**. Escribirlo al revés (mirar `pending_count` primero) es el modo de fallo más caro
del plan: bloquearía todos los disparos del operador. Test: `test_f4_orden_de_evaluacion` pasa
`resolved=False` **con** `pending_count > 0` y exige `degradado`.

### 4.4 **(v2, C2 — NUEVO)** Los dos vocabularios de proveedor que conviven en el repo

Este plan cruza dos subsistemas que nombran al mismo proveedor de forma distinta. **Confundirlos
apaga reglas en silencio** (falla abierto). Tabla congelada:

| Subsistema | Archivo que lo define | ADO | GitLab |
|---|---|---|---|
| Matriz de entornos / declaración (F1-F4) | `services/pipeline_environments.py:28-30` `PROVIDER_ADO` | `"azure_devops"` | `"gitlab"` |
| Auditor + linter + reglas semánticas (F5) | `api/pipeline_audit.py:22` `_PROVIDERS`; `pipeline_lint.py:70` `_rule(..., providers=("ado","gitlab"))`; `cicd_security_rules.py:471,474,477` `if provider == "ado"` | **`"ado"`** | `"gitlab"` |
| Body de `commit_route` (F5) | `api/pipeline_generator.py:65-70` `body["target"]` | **`"ado"`** | `"gitlab"` |

**Reglas de uso, literales:**

1. **(v3, C7)** En F5 el proveedor que se le pasa a `audit_yaml` y a `lint_yaml` es
   **`"ado" if target == "ado" else "gitlab"`** — la **misma decisión binaria** que
   `api/pipeline_generator.py` ya toma en `:67` (qué renderer usa) y `:70` (qué ruta escribe).
   **El v2 decía "`target` tal cual, identidad", asumiendo que `body["target"]` ya vale `"ado"` o
   `"gitlab"`. El endpoint NO lo valida** (`:65` es un `body.get("target")` pelado), así que
   `None`, `"ADO"` o `"azure_devops"` llegan crudos al motor de reglas: SEC003/SEC005/SEC007 y las
   reglas `providers=("ado", ...)` dejan de aplicar y el gate **deja pasar** lo que debía frenar.
   Espejar la decisión del endpoint es lo único que garantiza que el gate audite **el mismo
   dialecto que se está por commitear**.
2. Si alguna vez hace falta traducir, se hace en **una sola función**, en el módulo nuevo
   `services/ci_env_gate.py`:
   ```python
   def to_rules_provider(p: str) -> str:
       """pipeline_environments ('azure_devops'|'gitlab') -> vocabulario de reglas ('ado'|'gitlab')."""
       return "ado" if p in ("azure_devops", "ado") else "gitlab"
   ```
   y **nunca** en línea dentro de un endpoint.
3. Test obligatorio (F5): `test_f5_vocabulario_de_provider` — asserta que el string que llega a
   `audit_yaml` pertenece a `api.pipeline_audit._PROVIDERS`. Si alguien vuelve a escribir
   `"azure_devops"`, ese test se cae.

### 4.5 **(v2, C4 — NUEVO)** Contrato de resolución del gate de disparo

`evaluate_readiness` es **puro** y recibe la matriz ya armada. Quien la arma es el helper
`_evaluar_readiness(project, body_o_args)` **dentro de `api/ci.py`**, y su contrato es:

```
1. Obtener el YAML  (fuentes en orden, §5 F4). Si ninguna acierta -> Readiness(degradado, resolved=False)
2. extract_requirements + derive_environments        (PURO, sin red, sin I/O)
3. resolve(...) contra el proveedor                  (UNICA llamada de red del gate)
   - techo REAL de espera: 1500 ms  (KPI-7) — ver "Cómo se acota" abajo
   - cualquier excepcion, timeout o proveedor no configurado -> resolved=False -> 'degradado'
4. build_matrix(...) -> evaluate_readiness(matrix, resolved=True, elapsed_ms=<medido>)
```

#### **(v3, C2) Cómo se acota la espera — literal, porque el v2 se contradecía**

El v2 decía "presupuesto duro de 1500 ms" y dos líneas después "se compara **después**: no se
cancela el request en vuelo". **Eso no acota nada.** `resolve()`
(`services/pipeline_env_resolver.py:87`) es sincrónico y **no acepta timeout**: si el proveedor
tarda 30 s, el operador espera 30 s **y encima** el gate se declara degradado. El KPI-7 quedaba
infalsable y el riel "no degradar performance" roto en el camino crítico del botón rojo.

No hace falta cancelar el request: hace falta **dejar de esperarlo**. Eso sí se puede, con
stdlib y sin daemons:

```python
# api/ci.py — dentro de _evaluar_readiness. NO hay pool global, NO hay hilo de fondo:
# el executor nace y muere dentro del request que el operador disparo.
import concurrent.futures as _fut
from services.ci_env_gate import GATE_BUDGET_S          # = 1.5, constante del modulo nuevo

t0 = time.monotonic()
try:
    with _fut.ThreadPoolExecutor(max_workers=1) as ex:
        f = ex.submit(resolve, reqs, envs, provider_env, project, True, yaml_text)
        resoluciones, degradaciones = f.result(timeout=GATE_BUDGET_S)
    resolved = True
except (_fut.TimeoutError, Exception):     # timeout, red, proveedor sin configurar, lo que sea
    resolved = False
elapsed_ms = int((time.monotonic() - t0) * 1000)
```

- **`with ThreadPoolExecutor(...)` hace `shutdown(wait=True)` al salir**, así que en el camino
  de timeout el `with` **volvería a esperar** al hilo huérfano. Por eso el `submit`/`result` va
  dentro del `with` pero, si hay `TimeoutError`, se sale con
  `ex.shutdown(wait=False, cancel_futures=True)` explícito **antes** de propagar. En py3.13
  `cancel_futures=True` existe y es lo correcto; el hilo que ya arrancó termina solo (era un GET
  de solo lectura) y su resultado se descarta.
- **Criterio del test, binario y sobre tiempo de pared:** `test_f4_timeout_de_resolucion_degrada`
  monta un doble de `resolve` que duerme **3 s**, mide `time.monotonic()` alrededor del request y
  exige **`elapsed < 2.0` segundos** *y* `verdict == "degradado"`. Assertar solo el verdict —como
  hacía el v2— es un falso verde: pasa aunque el operador haya esperado los 3 s.

**Reglas duras:**

- **`resolved=False` NUNCA bloquea.** Es el corolario de §3.4. Sin este candado, una matriz sin
  resolver deja las celdas en el default de `_nota_por_kind`
  (`pipeline_environments.py:471-479`) y una flag **default ON** frenaría disparos del operador
  desde el primer deploy. Es el modo de fallo más caro del plan.
  **(v3, C13) Precisión que el v2 tenía mal:** `_nota_por_kind` **no** devuelve `falta` para
  todo. Devuelve `manual` para `service_connection` (`:473-474`), para `deploy_path` de confianza
  baja (`:475-476`) y para **cualquier** requirement de confianza baja (`:477-478`); solo el resto
  cae en `falta` (`:479`). **MEDIDO:** un YAML ADO con `script: deploy --host $(DEPLOY_HOST) --key
  $(SONAR_TOKEN)` produce los dos requirements con `confidence="baja"` ⇒ sin resolver,
  `pending_count = 0`. Consecuencia para el implementador: el test
  `test_f4_sin_resolver_no_bloquea_aunque_todo_sea_falta` **tiene que construir `Requirement`s con
  `confidence="alta"` explícita**; armado con un YAML "natural" no prueba nada.
- **El gate no hace ninguna llamada de red que el panel de la matriz no haga ya.** Es el mismo
  `resolve()` que `/analyze` ejecuta cuando el operador abre la matriz.
- **El gate corre a pedido, dentro del request del operador. No hay loop, ni daemon, ni polling,
  ni prefetch.** Por eso su flag es default **ON** (ninguna de las dos categorías de excepción
  aplica) y por eso el `ThreadPoolExecutor` es local al request y no un pool global.

#### **[ADICIÓN ARQUITECTO 5] (v3) — el gate declara su propia latencia**

`readiness.elapsed_ms` (entero, ms que el gate **realmente esperó** al proveedor) viaja siempre:
en el `200` del `trigger-preview`, en el `409` del bloqueo y en el `200` del disparo que pasó.

Por qué vale, y por qué es una línea:

- **El KPI-7 deja de ser una promesa del papel.** Hoy la única forma de saber si el gate está
  costando caro es cronometrar a mano. Con el campo, el número está en la respuesta que el
  operador ya está mirando, y el test lo compara contra el presupuesto en vez de assertar un
  verdict (que es lo que hacía verde el falso positivo de C2).
- **Convierte "degradado" en algo accionable.** Un `degradado` con `elapsed_ms: 1502` le dice al
  operador *"tu ADO está lento"*; el mismo `degradado` con `elapsed_ms: 3` le dice *"no pude
  obtener el YAML"*. Son dos problemas distintos y hoy se ven iguales.
- **Human-in-the-loop:** es información para el operador, no autonomía. No cambia ninguna
  decisión automática. Cero trabajo extra, cero config nueva.
- **Costo:** un `int` en el dataclass, una resta que ya se calcula, y un campo en el JSON.

#### **[ADICIÓN ARQUITECTO 2] — reuso del veredicto por `pending_fingerprint`**

El disparo real casi siempre viene precedido del preview (el modal HITL lo pide). Calcular la
readiness dos veces es pagar dos veces la latencia por la misma verdad. Y ya existe en `api/ci.py`
una ventana de 60 s con su almacén en memoria: la de idempotencia — el **almacén** es
`_RECENT_TRIGGERS` (`api/ci.py:33`), el **lector** es `_recent_triggers` (`:44`) y la ventana la
aplica `should_trigger(..., window_seconds=60)` (`:105-106`). *(v3, C14: el v2 citaba el lector
como si fuera el almacén.)*

**Se reusa esa misma ventana**, con un almacén hermano y explícito:

```python
# api/ci.py — memoria de veredictos (misma ventana de 60 s que la idempotencia)
# clave: (provider_name, ref_value, yaml_sha256)  ->  (Readiness, ts_monotonic)
# NO es un cache de datos del proveedor: es el resultado ya calculado del gate.
_RECENT_READINESS: dict = {}
_MAX_READINESS = 32              # (v3, C12) cap duro
_READINESS_WINDOW_S = 60.0       # misma ventana que la idempotencia
```

- `trigger-preview` **escribe** el veredicto.
- `trigger` **lo reusa** si: misma `(provider, ref, yaml_sha256)` y antigüedad < 60 s.
  Cualquier diferencia ⇒ se recalcula.
- Si no hay entrada, se calcula normalmente (nada depende del preview).

#### **(v3, C4) Las dos reglas que impiden que el reuso abra el gate**

El v2 decía "el preview **escribe** el veredicto", sin filtro. Pero el preview sin `?yaml_path=`
devuelve **`degradado` con `resolved=False`** — y ese veredicto no bloquea nada. Si entraba al
almacén, el `trigger` (que **sí** trae `yaml_text` en el body y **sí** podría resolver) reusaba el
`degradado` y **dejaba pasar** un disparo que el cálculo fresco habría frenado: exactamente lo
contrario de la garantía que la propia ADICIÓN 2 declaraba ("nunca deja pasar algo que el cálculo
fresco hubiera frenado"). Encima, sin `yaml_path` no hay `yaml_sha256` y la clave quedaba
indefinida.

1. **Solo entra al almacén un veredicto con `resolved is True` y `yaml_sha256` no vacío.**
   Cualquier otro se calcula y se devuelve, pero **no se guarda**. Un `degradado` jamás se
   persiste ni se reusa.
2. **El `yaml_sha256` es parte de la CLAVE, no un campo a comparar después.** Así, un YAML
   distinto es una entrada distinta y no hay forma de "olvidarse de comparar".
3. **(v3, C12) Poda y tope.** En cada escritura se descartan las entradas con
   `monotonic() - ts > _READINESS_WINDOW_S` y, si quedan más de `_MAX_READINESS`, se elimina la
   más vieja. Sin esto el dict crece una entrada por cada `(proveedor, ref, sha)` visto y nunca
   suelta objetos `Readiness` (que traen `missing` y `reasons`).

**Por qué es seguro:** el `pending_fingerprint` ya existe y ya es el identificador canónico del
"trabajo pendiente" (`pipeline_environments.py:464-468`). Si el operador cargó un valor entre el
preview y el disparo, cambia el fingerprint del proveedor, pero el veredicto reusado sería el
**viejo (más restrictivo o igual)**: en el peor caso el operador ve un 409 que ya no corresponde,
aprieta de nuevo y a los 60 s se recalcula. **Nunca al revés** (nunca deja pasar algo que el
cálculo fresco hubiera frenado)… salvo que el operador **borre** un valor en 60 s, caso en que el
disparo pasa: se declara como riesgo aceptado R12 y se documenta en la respuesta con
`readiness.source == "preview_reusado"`.

- Tests obligatorios: `test_f4_veredicto_reusado_declara_su_origen`,
  `test_f4_yaml_distinto_no_reusa_el_veredicto`,
  **`test_f4_degradado_no_se_almacena_ni_se_reusa`** *(v3, C4)* y
  **`test_f4_almacen_de_veredictos_acotado`** *(v3, C12)*.

### 4.6 **[ADICIÓN ARQUITECTO 4] (v3, C1 — NUEVA)** Corpus de paridad `proveedor x kind`

**El problema que resuelve:** C1 no fue un typo, fue razonar sobre "declarar" como si los dos
proveedores y los dos `kind` declarables se comportaran igual. La casa ya tiene el patrón para
esto (el corpus dorado del 249): **si la tabla de verdad no está congelada en un archivo y
recorrida por un test parametrizado, un caso se cae del razonamiento y nadie se entera.**

**Archivo NUEVO (dato, no código):** `backend/tests/plan260_corpus/declare_matrix.json`

Una fila por combinación de `PROVIDERS x ("variable", "secret")` — **4 filas, ni una menos**:

```json
{
  "schema_version": 1,
  "rows": [
    {"provider": "azure_devops", "kind": "variable", "declared_secret": false,
     "provider_devuelve": {"is_secret": false, "value": ""},
     "has_value": false, "state": "falta",  "source": "declarada_sin_valor",
     "cuenta_en_pendiente_visible": true, "gate": "bloquea"},
    {"provider": "azure_devops", "kind": "secret",   "declared_secret": true,
     "provider_devuelve": {"is_secret": true,  "value": null},
     "has_value": null,  "state": "manual", "source": "declarada_sin_valor_verificable",
     "cuenta_en_pendiente_visible": true, "gate": "advierte"},
    {"provider": "gitlab", "kind": "variable", "declared_secret": false,
     "provider_devuelve": {"masked": false, "value": ""},
     "has_value": false, "state": "falta",  "source": "declarada_sin_valor",
     "cuenta_en_pendiente_visible": true, "gate": "bloquea"},
    {"provider": "gitlab", "kind": "secret",   "declared_secret": true,
     "provider_devuelve": {"masked": true,  "value": ""},
     "has_value": false, "state": "falta",  "source": "declarada_sin_valor",
     "cuenta_en_pendiente_visible": true, "gate": "bloquea"}
  ]
}
```

**Quién lo consume (tres fases, un solo dato):**

| Fase | Test parametrizado | Qué prueba con la fila |
|---|---|---|
| F1 | `test_f1_tabla_de_verdad_declare[4]` | `provider_devuelve` -> `has_value` -> `(state, source)` |
| F3 | `test_f3_pendiente_visible_no_baja[4]` | el pendiente **visible** antes == después de declarar |
| F4 | `test_f4_veredicto_por_fila[4]` | el `verdict` del gate para esa fila |

**Y el test que hace que un caso nuevo sea ROJO en vez de invisible:**

```python
def test_f2_corpus_cubre_el_producto_cartesiano():
    """Si manana entra un proveedor nuevo o un kind declarable nuevo, este test se cae
    ANTES de que alguien razone de memoria sobre como se comporta."""
    from services.pipeline_environments import PROVIDERS
    esperados = {(p, k) for p in PROVIDERS for k in ("variable", "secret")}
    reales = {(r["provider"], r["kind"]) for r in _corpus()["rows"]}
    assert reales == esperados, "faltan filas en declare_matrix.json: %s" % (esperados - reales)
```

**Costo:** un JSON de 4 filas y un `@pytest.mark.parametrize`. **Valor:** el falso verde de §2.5
se habría caído en F1, antes de escribir el endpoint. Es exactamente el mismo criterio que el
repo ya aplica con `repro` en `cicd_audit_core.py:106-115` — declarar un comportamiento sin un
reproductor que lo pruebe es declarar verde falso.

---

## 5. Fases

> **Corte declarado:** 8 fases (F0..F7). Todo lo que tenga que ver con **generar** una pipeline
> desde lenguaje natural, elegir modelo/effort o arreglar el intérprete NL queda **fuera** y va al
> Plan 261 (§7). Este plan no toca `api/pipeline_editor.py:346` `interpret_edit`.

---

### F0 — Tres flags, en sus **7 patas**

**Objetivo:** las tres flags existen, tienen el default correcto, son editables por UI y no
ponen rojo ningún meta-test.

| Flag | Default | `requires` | Por qué |
|---|---|---|---|
| `STACKY_PIPELINE_ENV_DECLARE_ENABLED` | **OFF** | `STACKY_DEVOPS_PANEL_ENABLED` | **Excepción dura (B):** es la única ruta NUEVA que **escribe en un sistema externo real del operador** (su ADO/GitLab). Misma categoría exacta que `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` (`config.py:1474-1480`) |
| `STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED` | **ON** | `STACKY_PIPELINE_TRIGGER_ENABLED` | Solo lee. No escribe, no quema tokens en reposo (no hay loop ni daemon: corre **a pedido**, dentro del request de disparo que el operador inició), no llama a un modelo. Bloquea **solo** con evidencia positiva, y con `resolved=True` (§4.5) |
| `STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED` | **ON** | `STACKY_DEVOPS_PANEL_ENABLED` | Un gate que solo puede **impedir** una fuga. Apagarlo es la decisión rara, no encenderlo. No escribe nada, no consume tokens |

> **(v2) Nota sobre las dos flags ON:** ninguna de las dos categorías de excepción aplica.
> No hay gasto en reposo **(A)** porque no hay loop/daemon/barrido/polling/prefetch: ambas corren
> sincrónicamente dentro de un request que el operador disparó. No hay escritura ni destrucción
> **(B)**: una lee, la otra frena. Motivos explícitamente **rechazados** y que no figuran acá:
> "default seguro", "por las dudas", "no cambiar el comportamiento actual", "prerequisito no
> garantizado".

**Las 7 patas:**

1. **`backend/config.py`** — los tres atributos, con el patrón exacto del archivo, junto a
   `STACKY_PIPELINE_ENV_MATRIX_ENABLED` (`:1464-1466`) y `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`
   (`:1478-1480`). Los dos ON con `"true"`, el OFF con `"false"`.
   **Gotcha dura:** el consumidor lee **la instancia** (`getattr(_config.config, KEY, False)`).
   `getattr` del **módulo** devuelve el default y mata el branch OFF: falso verde perfecto.
2. **`backend/services/harness_flags.py`** — dos ediciones:
   - las 3 keys en `_CATEGORY_KEYS["devops"]`, después de `:213` (la tupla cierra en `:214`);
   - 3 `FlagSpec` junto a los de `:3123` (251) y `:3166` (250).
   **Gotcha `requires` (R4, profundidad 1):** **prohibido** poner
   `requires="STACKY_PIPELINE_ENV_MATRIX_ENABLED"`, porque esa flag **ya** declara
   `requires="STACKY_DEVOPS_PANEL_ENABLED"` (`test_harness_flags_requires.py:308`) y encadenar
   rompe `validate_requires_graph`. El master legal de raíz es `STACKY_DEVOPS_PANEL_ENABLED`.
   **Gotcha default-OFF:** `STACKY_PIPELINE_ENV_DECLARE_ENABLED` **NO debe declarar
   `default=False`** en su `FlagSpec`. `default_is_known(spec)` es `spec.default is not None`, y
   `False is not None` ⇒ `True` ⇒ exige estar en el conjunto curado ⇒ rompe
   `test_default_known_only_for_curated`. Se **omite el kwarg** y se copia textualmente el patrón
   ya escrito en `harness_flags.py:3169-3173`.
3. **`backend/services/harness_flags_help.py`** — 3 `PlainHelp`, junto a `:721` y `:733`.
   **Gotcha:** el texto llano tiene tope de **240 caracteres** y hay un ratchet que castiga
   ciertas palabras en la prosa. Si el gate salta, **se reescribe el texto, jamás el gate**.
4. **`backend/tests/test_harness_flags.py`** — las **dos** flags ON van al conjunto
   `_CURATED_DEFAULTS_ON` (abre en `:467`; el bloque de pipelines está en `:537-545`); la OFF se
   menciona en el **comentario de excepciones duras** de `:483-489`.
   **(v2, C15)** Ese comentario es **prosa**, no una tupla: no busques una estructura para
   apendear. Lo que hace verde el meta-test es la **ausencia** de la flag OFF en el conjunto
   curado, que se logra omitiendo `default=` en su `FlagSpec` (pata 2). Sin las dos ON en el
   conjunto, `test_default_known_only_for_curated` queda rojo con "Extras (no curadas)".
5. **`backend/tests/test_harness_flags_requires.py`** — 3 aristas nuevas en
   `_REQUIRES_MAP_FROZEN`, junto a `:296-308` (el dict cierra en `:309`). Sin esto
   `test_requires_map_is_frozen` queda rojo **en silencio**.
6. **`backend/scripts/run_harness_tests.sh`** — los **7** archivos de test nuevos (6 del v1 + el
   de F7) en `HARNESS_TEST_FILES` (`:20`), al FINAL, con la sintaxis del `.sh` (sin comillas, sin
   coma; patrón `:820-825`).
7. **`backend/scripts/run_harness_tests.ps1`** — los mismos 7 en `$HarnessTestFiles` (`:13`), al
   FINAL, con la sintaxis de PowerShell (**con** comillas y coma; patrón `:733-738`).
   **El meta-test NO mira el `.ps1`**: olvidarlo no da rojo y el runner que corre el operador en
   Windows deja de cubrir 7 archivos en silencio.

**NO tocar `backend/harness_defaults.env`** (está congelado, y su generador vive en
`deployment/`).

> **(v3) `backend/tests/plan260_corpus/declare_matrix.json` (§4.6) NO va al ratchet.** Es un
> archivo de **datos**, no un `test_*.py`: el meta-test solo exige registrar archivos de test.
> Meterlo en `HARNESS_TEST_FILES` pone el runner en rojo al intentar correrlo con pytest.

**Tests PRIMERO** — `backend/tests/test_plan260_env_gate_flags.py`:
- `test_f0_tres_flags_en_registry`
- `test_f0_tres_flags_en_categoria_devops`
- `test_f0_defaults` — las 2 ON con `spec.default is True` **y** presentes en
  `_CURATED_DEFAULTS_ON`; la OFF **sin** `default` declarado (`spec.default is None`) **y**
  ausente del conjunto curado.
- `test_f0_config_efectivo` — `import config` y `getattr(config.config, KEY)` da `True`,`True`,
  `False`. **Este test cierra el falso verde real:** el default EFECTIVO lo manda `config.py`,
  no el `FlagSpec`.
- `test_f0_requires_profundidad_1` — ninguna de las 3 apunta a una flag que a su vez declare
  `requires`.
- `test_f0_plain_help_existe_y_entra_en_240`

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan260_env_gate_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

**Criterio BINARIO:** los 6 tests propios verdes **y** los 3 de no-regresión en su baseline
**medido hoy**: `test_harness_flags.py` **56 passed**, `test_harness_flags_requires.py`
**9 passed**, `test_harness_ratchet_meta.py` **4 passed**. **Y** el gate manual de paridad:
`rg -c "test_plan260" backend/scripts/run_harness_tests.sh backend/scripts/run_harness_tests.ps1`
⇒ **7 en cada uno**.

---

### F1 — La verdad sobre `has_value` (va PRIMERA, y por eso)

**Objetivo:** que el sistema pueda distinguir "la variable existe" de "la variable tiene valor".
**Sin esto, F3 construye un falso verde y F4 hereda el mismo** (§2.3, MEDIDO).

**Archivos:**

1. `services/ado_variables.py:25-45` `list_variables` — `has_value` deja de ser el literal `True`
   (hoy en `:42`):
   ```python
   # ADO no devuelve el value de un secreto (isSecret=true -> value: null) => None = DESCONOCIDO.
   # Para una variable normal, ausencia de la clave "value" tambien es DESCONOCIDO, no False.
   has_value = None if is_secret or "value" not in var_def else bool(var_def.get("value"))
   ```
   `list_variables_scoped` (`:47-51`) hereda por construcción (hace `{**v, ...}`).
2. `services/gitlab_variables.py:22-44` (hoy `:41`) y `:46-60` (hoy `:57`) — GitLab **sí** devuelve
   `value` en el listado: `has_value = bool(v.get("value"))` si la clave viene; `None` si no.
   **Ojo: son DOS sitios**, uno por método; `list_variables_scoped` **no** delega en
   `list_variables` (repite el `_request_paginated` en `:53`). Cambiar uno solo deja el bug vivo
   por el camino de la matriz, que usa el `scoped`.
   **Prohibido** guardar, loguear o retornar `v["value"]`: solo se consume el `bool()`.
3. `services/ci_variables.py` — documentar el tri-estado en el docstring del puerto.
   `VARIABLES_PORT_METHODS` (`:63`) **no se toca**.
4. `services/pipeline_env_resolver.py:105-109` — `por_key` pasa a guardar
   `(environment_scope, has_value)`; `_resolver_celda:137-148` aplica la tabla de §4.1.
   **Ojo:** el branch que hoy devuelve `("definido", "caja_fuerte", None)` para ADO está en
   `:142-143` y el de GitLab en `:144-147`; **los dos** tienen que consultar `has_value`.
5. `services/pipeline_environments.py:24-25` — **(v3, C1)** `SOURCES` gana **DOS** elementos
   **al final**: `"declarada_sin_valor"` y `"declarada_sin_valor_verificable"`.

**Tests PRIMERO** — `backend/tests/test_plan260_has_value_veraz.py`:
- **`test_f1_tabla_de_verdad_declare` (v3, ADICIÓN 4)** — parametrizado sobre las **4** filas de
  `plan260_corpus/declare_matrix.json` (§4.6): de `provider_devuelve` a `has_value` y de ahí a
  `(state, source)`. **Este es el test que se cae si alguien vuelve a mandar el caso `None` a
  `source="caja_fuerte"`.**
- **`test_f1_ado_secreto_declarado_no_queda_como_caja_fuerte` (v3, C1)** — control explícito del
  bug medido en §2.5: `is_secret=True` ⇒ `source == "declarada_sin_valor_verificable"`, **nunca**
  `"caja_fuerte"`.
- `test_f1_ado_secreto_es_desconocido` — `isSecret: true` ⇒ `has_value is None`.
- `test_f1_ado_valor_vacio_es_false` — `{"value": "", "isSecret": false}` ⇒ `has_value is False`.
- `test_f1_ado_sin_clave_value_es_none` — degradación honesta (§2.4 punto 1).
- `test_f1_gitlab_valor_vacio_es_false` y `test_f1_gitlab_con_valor_es_true`.
- **`test_f1_gitlab_scoped_tambien_es_veraz` (v2)** — el mismo caso sobre
  `list_variables_scoped()`, que es el que consume la matriz. Sin este test, cambiar un solo
  método da verde y deja el bug donde importa.
- **`test_f1_ningun_value_sale_del_provider` (CONTROL NEGATIVO, KPI-5):** se inyecta
  `{"key":"K","value":"Xk7#pQ2mZr9Lw4Tv"}` y se asserta que esa cadena **no aparece** en
  `repr(list_variables())` ni en `repr(list_variables_scoped())`.
- **`test_f1_declarada_sin_valor_sigue_contando_como_falta` (KPI-2, el test que da vuelta la
  medición de §2.3):** con `has_value=False`, la celda queda `("falta","declarada_sin_valor")` y
  `build_matrix(...).pending_count == 1`.
- `test_f1_desconocido_cae_en_manual_no_en_definido`.
- `test_f1_sources_solo_crecio` — `SOURCES[:7]` es byte-idéntica a la tupla anterior **y**
  `len(SOURCES) == 9`.

**Criterio BINARIO:** los 11 propios verdes **y** las baselines **medidas hoy** intactas
(re-verificadas por el juez de la v3 corriendo cada archivo con `backend/.venv`):
`test_plan94_variables_providers.py` **13**, `test_plan94_variables_endpoints.py` **14**,
`test_plan94_variables_pure.py` **3**, `test_plan251_env_matrix_resolve.py` **15**,
`test_plan251_env_matrix_build.py` **14**.

> **Si `test_plan251_env_matrix_resolve.py` se pone rojo, NO se toca el test para que pase.** Ese
> rojo significaría que había un test congelando el bug de §2.3; se corrige el test y se
> documenta el desvío en el estado del plan.

---

### F2 — Núcleo PURO del plan de declaración

**Objetivo:** decidir, sin red y sin I/O, qué nombres se declaran y cuáles no, y por qué.

**Archivo NUEVO:** `services/pipeline_env_declare.py` — contrato exacto en §4.2.
Determinista: mismo `(matrix, provider)` ⇒ mismo `DeclarePlan`, mismo orden.

**Tests PRIMERO** — `backend/tests/test_plan260_declare_core.py`:
- `test_f2_modulo_puro` — el módulo no contiene `\bprint\(`, `\blogger\.`, `requests`, `import yaml`.
  **Gotcha recurrido 6 veces en esta casa:** el gate se escribe con `\bprint\(`, no con la
  subcadena suelta, porque un símbolo legítimo puede contenerla (`Blueprint(` es el caso real).
  **El test verifica su propio gate** con un fixture que contiene `Blueprint(` y debe pasar.
- `test_f2_solo_declara_lo_que_falta` — celdas `definido`/`default`/`manual` no generan `DeclareItem`.
- `test_f2_salta_server_deploy_path_service_connection_parameter` — 4 casos, y cada uno aparece en
  `skipped` **con motivo**.
- `test_f2_key_invalida_va_a_skipped` — `$(SONAR_TOKEN)` (que es como llega un
  `service_connection`, §2.3) no se intenta crear jamás.
- **`test_f2_secret_se_conserva_en_ambos_proveedores` (v2, §3.6)** — con un requirement
  `is_secret=True`, `item.secret is True` **tanto** para `azure_devops` **como** para `gitlab`.
  (El v1 tenía acá `test_f2_gitlab_nunca_declara_secret_true`, que congelaba la decisión
  equivocada de C6: **se elimina**.)
- `test_f2_note_gitlab_avisa_del_masking` — para `gitlab` + secreto, la `note` menciona que hay
  que confirmar el enmascarado al cargar el valor.
- `test_f2_determinista` — dos llamadas dan tuplas idénticas.
- **`test_f2_ningun_placeholder` (§3.3)** — ningún `DeclareItem` lleva valor; el módulo **no
  contiene** las cadenas prohibidas de §3.3.

**Criterio BINARIO:** los 8 verdes. Sin red: el archivo de test no importa `flask` ni `app`.

---

### F3 — Endpoint `/declare` con HITL y escritura por el puerto del 94

**Objetivo:** crear los nombres en el proveedor, con valor vacío, previa confirmación explícita.

**Archivo:** `api/pipeline_environments.py` (ya existe; guard compartido `_guard()` en `:30-36`).

#### **(v2, C5) El guard propio — esto es lo primero que se escribe**

`_guard()` (`:30-36`) chequea **`STACKY_PIPELINE_ENV_MATRIX_ENABLED`**, que es **default ON**, y
lo comparte todo el blueprint. Si `/declare` lo usa, la flag OFF de escritura **no protege nada**.
Se agrega, en el mismo archivo, inmediatamente debajo:

```python
def _guard_declare():
    """Guard de la ruta de ESCRITURA. Exige LAS DOS flags: la del blueprint (matriz)
    y la propia de declaracion. La instancia (_config.config), nunca el modulo."""
    _guard()                                   # 404 si la matriz esta OFF + chequeo de JSON
    if not getattr(_config.config, "STACKY_PIPELINE_ENV_DECLARE_ENABLED", False):
        abort(404)
```

#### Contrato de las rutas

```
POST /api/pipeline-environments/declare
  body: { yaml_text, provider, project, confirm: true, keys?: [...] }   # keys OPCIONAL: subconjunto
  guard: _guard_declare()   (cualquiera de las 2 flags OFF -> 404)
  sin confirm=true -> 400 {"error": "confirm=True requerido (HITL)"}
  ->  200 { declared: [...], skipped: [...], failed: [...],
            needs_masking: [...],            # (v2, C6) keys que quedaron masked=false
            pending_count_after,             # el del contrato 251 (solo celdas 'falta')
            pendiente_visible_after }        # (v3, C1) 'falta' + declarada_sin_valor_verificable

POST /api/pipeline-environments/declare-preview      # mismo body sin confirm; NO escribe
  guard: _guard()   (solo la flag de la matriz: ver que se declararia es SOLO LECTURA)
  ->  200 { plan: DeclarePlan serializado,
            pendiente_visible_actual, pendiente_visible_proyectado }   # (v2 ADICION 3; v3 C1)
```

> **(v3, C1)** El preview compara **pendiente visible**, no `pending_count`. Con `pending_count`
> los dos números divergen legítimamente en ADO+secreto (§2.5) y el canario se vuelve ruido: el
> operador vería "va a bajar de 1 a 0" **y sería cierto**, aunque no se cargó ningún valor. La
> respuesta de `/declare` devuelve **los dos** contadores porque el de arriba es el contrato del
> 251 y no se rompe; el de abajo es el que el titular usa.

- **(v2, C8)** El campo del YAML se llama **`yaml_text`**, igual que en el hermano `/analyze`
  (`api/pipeline_environments.py:41`). No `yaml`.
- La escritura llama `get_variables_provider(project).set_variable(key, "", item.secret)`
  (`ci_variables.py:66`), **una key por vez**, y **nunca aborta el lote**: una key que falla va a
  `failed` con mensaje sanitizado y el resto sigue.
- **(v2, C6)** `set_variable` devuelve `{"key","is_secret","masked"}`
  (`gitlab_variables.py:123-127`). Toda key con `secret=True` que vuelva con `masked` falsy entra
  en `needs_masking`. **Nunca** se reintenta a mano: el reintento ya vive en el proveedor.
- `keys` permite al operador declarar un subconjunto: intersección con el plan; una key que no
  esté en el plan se rechaza con **`400 {"error": "keys_fuera_del_plan", "keys": [...]}`**
  *(v2, C12: el v1 no decía el status)*. **No** se crea lo que el operador tipeó de más.
- **(v2, C12)** Si el proveedor no está disponible —ADO sin pipeline definition lanza
  `VariablesUnavailableError` (`ado_variables.py:20-23`)— la respuesta es
  **`409 {"error": "proveedor_sin_variables", "detail": <mensaje del proveedor, ya en llano>}`**
  y **0 escrituras**. Ese mensaje ya es accionable y no trae valores.
- Idempotente: declarar dos veces no rompe (`set_variable` hace upsert en ambos proveedores).
  **Pero:** si la key ya tiene valor, `plan_declaration` no la incluye (su celda es `definido`)
  ⇒ **no se pisa un valor cargado**. Test dedicado.

#### **[ADICIÓN ARQUITECTO 3] — el preview dice lo que NO va a pasar**

`declare-preview` devuelve **`pendiente_visible_actual` y `pendiente_visible_proyectado`**,
calculados con el mismo núcleo puro: se toma la matriz, se aplica a las keys del plan **la
respuesta que ESE proveedor va a dar para ESE `kind`** y se vuelve a `build_matrix`. Con F1
correcto, **los dos números son iguales**.

> **(v3, C1) La proyección NO es "marcar todo como `has_value=False`", que es lo que decía el v2.**
> En ADO+secreto el proveedor devuelve `isSecret: true` ⇒ `has_value=None` ⇒ celda `manual`, no
> `falta`. Proyectar `False` para ese caso hace que el canario **mida algo distinto de lo que va a
> pasar**: el test salía verde mientras la producción divergía. La proyección usa **la misma tabla
> de §4.6** que el resto del plan:
>
> ```python
> # services/pipeline_env_declare.py — PURO, sin red
> def proyectar_has_value(provider: str, es_secreto: bool) -> object:
>     """Que va a devolver el proveedor DESPUES de declarar la key con valor vacio.
>     Unica fuente de verdad de la proyeccion; la prueba declare_matrix.json (§4.6)."""
>     if provider == PROVIDER_ADO and es_secreto:
>         return None          # ADO: isSecret=true -> value: null -> DESCONOCIDO
>     return False             # el resto: el proveedor confirma el vacio
> ```

Por qué vale: el KPI-2 del plan es contraintuitivo ("declaro y la alerta no baja") y el operador
podría leerlo como que la función no hizo nada. Mostrar los dos números **antes** de escribir
convierte una sorpresa en una decisión informada, y además es un **canario en producción**: si
alguna vez `pendiente_visible_proyectado < pendiente_visible_actual`, el bug de §2.3/§2.5 volvió y
el operador lo ve en la pantalla antes que cualquier test.

- Tests: `test_f3_preview_proyecta_el_mismo_pendiente_visible` **parametrizado sobre las 4 filas
  del corpus** (§4.6) y **`test_f3_proyeccion_ado_secreto_es_none`** *(v3, C1)*, que se cae si
  alguien vuelve a proyectar `False` para todo.

**Tests PRIMERO** — `backend/tests/test_plan260_declare_endpoint.py`:
- `test_f3_flag_off_404` — leyendo `config.config`, no el módulo.
- **`test_f3_flag_declare_off_pero_matriz_on_da_404` (v2, C5)** — con
  `STACKY_PIPELINE_ENV_MATRIX_ENABLED=True` y `STACKY_PIPELINE_ENV_DECLARE_ENABLED=False`,
  `/declare` da **404** y el doble de `set_variable` registra **0 llamadas**. **Este test es el
  que prueba que la excepción dura de la flag existe en el código y no solo en el papel.**
- `test_f3_sin_confirm_400_y_no_escribe` — 0 llamadas.
- `test_f3_preview_no_escribe` — 0 llamadas, y funciona con la flag de declare en OFF.
- `test_f3_preview_proyecta_el_mismo_pendiente_visible` *(ADICIÓN 3, parametrizado x4)*.
- **`test_f3_proyeccion_ado_secreto_es_none`** *(v3, C1)*.
- `test_f3_declara_con_valor_vacio` — cada llamada capturada tiene `value == ""`.
- **`test_f3_nunca_pisa_una_variable_con_valor`** — key ya cargada ⇒ 0 llamadas para esa key.
- `test_f3_una_falla_no_aborta_el_lote` — 3 keys, la 2ª lanza `TrackerApiError`; el resultado
  tiene 2 en `declared` y 1 en `failed`.
- **`test_f3_gitlab_masked_false_va_a_needs_masking` (v2, C6)** — el doble devuelve
  `masked=False` para una key secreta ⇒ la key aparece en `needs_masking`.
- **`test_f3_ado_sin_definition_da_409_y_no_escribe` (v2, C12)**.
- `test_f3_mensaje_de_error_sanitizado` — una excepción desconocida **no** propaga `str(e)`.
- **`test_f3_ningun_valor_en_la_respuesta` (CONTROL NEGATIVO, KPI-5)** — se inyecta un valor
  cargado y esa cadena no aparece en el cuerpo de la respuesta.
- **`test_f3_pendiente_visible_no_baja_al_declarar` (KPI-2, el corazón del plan) —
  PARAMETRIZADO sobre las 4 filas del corpus (v3, C1)**: `(azure_devops, variable)`,
  **`(azure_devops, secret)`**, `(gitlab, variable)`, `(gitlab, secret)`. Se declara, se
  re-analiza y se exige `pendiente_visible_después == pendiente_visible_antes`.
  **Este es el test que, si se cae, significa que el plan reintrodujo el bug de §2.3/§2.5.**
  > **Por qué parametrizado y no un caso suelto:** el v2 lo dejaba sin fijar proveedor ni `kind`.
  > Un modelo menor elige el caso fácil (gitlab+variable), sale verde, y el falso verde **medido**
  > en §2.5 llega a producción intacto. El caso `(azure_devops, secret)` es obligatorio.
- **`test_f3_ado_secreto_declarado_no_apaga_el_titular` (v3, C1)** — control de punta a punta del
  bug de §2.5: con un único requirement secreto en ADO, tras declarar, el pendiente visible sigue
  siendo **1** (aunque `pending_count` sea 0, que es correcto y esperado).
- `test_f3_keys_fuera_del_plan_se_rechazan_con_400`

**Criterio BINARIO:** los 16 verdes **y** `test_plan251_env_matrix_endpoints.py` en su baseline
**medida hoy: 16 passed**.

---

### F4 — El gate antes de disparar

**Objetivo:** que `POST /api/ci/<project>/trigger` no dispare a ciegas **y que jamás frene un
disparo por no haber podido averiguar** (§3.4, §4.5).

**Archivo NUEVO:** `services/ci_env_gate.py` — `evaluate_readiness` (contrato en §4.3) + el
traductor de vocabulario de §4.4. PURO: sin red, sin I/O, sin `datetime.now`.

**Resolución del YAML** (en orden, primera que acierta; ninguna hace red saliente nueva):
1. `body["yaml_text"]` explícito — es lo que manda la UI (F6), que ya lo tiene.
2. `yaml_path` de la entrada del inventario del Plan 246 (`services/pipeline_inventory.py:511`
   `scan_repo_pipelines`), leído del workspace **local**. Import **blando**: si no se puede
   mapear `ref`->archivo, se salta (§2.4 punto 3).
3. Ninguna ⇒ `Readiness(verdict="degradado", resolved=False)`. **No bloquea.**

**Resolución contra el proveedor:** contrato completo en **§4.5**, con presupuesto de 1500 ms y
la regla `resolved=False` nunca bloquea. **Leerlo antes de escribir una línea de F4.**

**Cableado en `api/ci.py`:**
- `trigger_pipeline_route` (`:75`) — el chequeo va **después** de `get_ci_provider` (`:98`, hace
  falta el `provider.name` para el reuso de veredicto) y **antes** de la idempotencia (`:105`),
  para no consumir la ventana de 60 s con un disparo que se va a rechazar:
  ```python
  if getattr(_config.config, "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED", False):
      readiness = _evaluar_readiness(project, body, ref_value, provider)   # nunca lanza
      if readiness.verdict == "bloquea" and body.get("acknowledge_missing") is not True:
          return jsonify({
              "error": "faltan %d valor(es) obligatorio(s) para esta pipeline"
                       % readiness.pending_count,
              "kind": "env_pending",
              "missing": [{"name": n, "environment": e} for n, e in readiness.missing],
              "pending_fingerprint": readiness.pending_fingerprint,
              "hint": "cargá los valores en Variables, o reintentá con acknowledge_missing=true",
          }), 409
  ```
- El bloque `_evaluar_readiness` va envuelto en `try/except Exception` que degrada a
  `Readiness(verdict="degradado", resolved=False)`: **el gate jamás puede romper un disparo por un
  bug propio.**
- **(v2, C7)** `trigger_preview_route` (`:156`) es un **GET** y usa `request.args` (`:166`). **No
  tiene body**, así que la fuente 1 del YAML no le sirve. Se resuelve así, sin romper nada:
  - el preview acepta **`?yaml_path=`** (una ruta relativa del workspace, no el YAML entero: un
    YAML no entra en una query string y ponerlo ahí lo dejaría en los logs de acceso del servidor,
    violando el KPI-5 por la puerta de atrás);
  - sin `yaml_path`, el preview usa la fuente 2 (inventario) y, si tampoco, devuelve
    `readiness.verdict == "degradado"`;
  - el campo `readiness` es **aditivo**: todo lo que el preview devuelve hoy sigue igual (§3.7).
  - El preview además **escribe** el veredicto en `_RECENT_READINESS` (§4.5, ADICIÓN 2).
- Cuando se dispara con `acknowledge_missing=True`, el `append_run` del ledger (`api/ci.py:136`)
  suma `"env_ack": True` y `"pending_fingerprint"`. **`ENTRY_FIELDS` de los ledgers JSONL de esta
  casa descarta campos no declarados EN SILENCIO** (`services/ci_run_ledger.py:30-34`; la
  proyección la hace **`_clean_entry`**, `:72-79`, y la línea literal es `:74`) ⇒ hay que agregar
  las dos claves **al final** de esa tupla, o el campo se pierde sin error. Ver §3.7 para la
  consecuencia declarada sobre las filas existentes.
  **Ojo (v3, C11):** ese `append_run` está adentro de `if ...STACKY_CI_RUN_LEDGER_ENABLED`
  (`api/ci.py:133`). El test del ledger tiene que **encender esa flag**, o no escribe nada y el
  assert de `env_ack` pasa por vacío.

**Tests PRIMERO** — `backend/tests/test_plan260_trigger_gate.py`:
- `test_f4_evaluate_readiness_puro` — sin red, sin I/O.
- `test_f4_bloquea_con_faltantes` — 409, `kind == "env_pending"`, y el provider **no** recibió
  `trigger_pipeline` (0 llamadas).
- `test_f4_ack_explicito_deja_pasar` — con `acknowledge_missing=True` dispara.
- `test_f4_sin_faltantes_dispara` — no cambia el comportamiento actual.
- **`test_f4_sin_yaml_no_bloquea`** (§3.4: nunca bloquear por ignorancia) — `degradado`, dispara,
  y la respuesta lo dice.
- **`test_f4_sin_resolver_no_bloquea_aunque_todo_sea_falta` (v2, C4 — el test más importante de
  la fase)** — se arma una matriz **sin resolver** y se pasa `resolved=False`: el verdict es
  `degradado` y el disparo **sale**. Si este test se cae, la flag default ON frena todos los
  disparos del operador.
  **(v3, C13) Cómo se construye, literal:** los `Requirement` se arman **a mano con
  `confidence="alta"`**, no de un YAML. Con un YAML "natural" tipo
  `script: deploy --host $(DEPLOY_HOST)` los requirements salen con `confidence="baja"` y
  `_nota_por_kind` (`pipeline_environments.py:471-479`) los manda a `manual`, no a `falta`:
  **MEDIDO, `pending_count = 0`** ⇒ el test no probaría nada.
- **`test_f4_orden_de_evaluacion` (v3, C3)** — `resolved=False` **con** `pending_count > 0` ⇒
  `degradado`. Si alguien mira `pending_count` primero, se cae.
- **`test_f4_timeout_de_resolucion_degrada` (v2 KPI-7; criterio reescrito v3, C2)** — el doble de
  `resolve` **duerme 3 s**; el test mide `time.monotonic()` alrededor del request y exige
  **`elapsed < 2.0` s** *y* `verdict == "degradado"` *y* `readiness.elapsed_ms <= 1600`.
  **Assertar solo el verdict es un falso verde:** pasa aunque el operador haya esperado 3 s.
- **`test_f4_degradado_no_se_almacena_ni_se_reusa` (v3, C4)** — el preview sin `yaml_path` da
  `degradado`; el trigger posterior **con** `yaml_text` y faltantes reales devuelve **409**, no
  un pase por reuso.
- **`test_f4_almacen_de_veredictos_acotado` (v3, C12)** — 40 escrituras ⇒
  `len(_RECENT_READINESS) <= 32`, y una entrada de más de 60 s no se reusa.
- **`test_f4_desconocido_advierte_pero_no_bloquea`** — `unknown_count > 0`, `pending_count == 0`.
- **`test_f4_una_excepcion_del_gate_no_rompe_el_trigger`** — se hace lanzar a
  `extract_requirements` y el disparo igual sale.
- `test_f4_flag_off_no_cambia_nada` — leyendo `config.config`.
- **`test_f4_el_gate_corre_antes_de_la_idempotencia` — REESCRITO (v3, C11).** El test del v2
  assertaba "un disparo bloqueado no consume la ventana: el siguiente intento con ack dispara de
  verdad". **Eso pasa con el gate en cualquier posición**, porque la ventana se escribe en
  `_record_trigger` (`api/ci.py:130`), que solo corre **después** de un disparo exitoso: un
  request bloqueado nunca llega ahí. El test no probaba el orden que su nombre declara.
  **Versión que sí lo prueba:** se espía `services.ci_trigger_rules.should_trigger` (monkeypatch
  con un contador) y, en el request bloqueado por el gate, se assertan **0 llamadas**. Si el gate
  se mueve después de `:105`, el contador da 1 y el test se cae.
- **`test_f4_ningun_valor_en_el_409`** (KPI-5) — `missing` trae solo nombres.
- `test_f4_ledger_conserva_env_ack` — la clave sobrevive a `ENTRY_FIELDS`, **con
  `STACKY_CI_RUN_LEDGER_ENABLED=True`** (si no, `api/ci.py:133` ni entra y el test pasa por vacío).
- `test_f4_preview_trae_readiness` — **(v2)** con `?yaml_path=` resuelto, y con el caso sin
  `yaml_path` dando `degradado`. Sin los dos casos el test no prueba nada (C7).
- **`test_f4_veredicto_reusado_declara_su_origen`** *(ADICIÓN 2)* — el preview calcula, el trigger
  reusa, y la respuesta trae `readiness.source == "preview_reusado"`.
- **`test_f4_yaml_distinto_no_reusa_el_veredicto`** *(ADICIÓN 2)* — otro `yaml_sha256` ⇒ recalcula.
- **`test_f4_veredicto_por_fila`** *(v3, ADICIÓN 4)* — parametrizado sobre las 4 filas de §4.6:
  cada `(provider, kind)` produce el `gate` que la fila declara.

**Criterio BINARIO:** los 22 verdes **y** las baselines **medidas hoy**:
`test_plan72_trigger_endpoint.py` **11 passed**, `test_plan191_ci_ledger_hook.py` **8 passed**.

> **(v3, C9) Corrección de la lista de baselines del v2, verificada archivo por archivo:**
> - `tests/test_plan202_ledger.py` **NO congela `ci_run_ledger.ENTRY_FIELDS`**. Ese archivo prueba
>   **`services/night_foundry_ledger`** (import en `:17`, factory `_L()` en `:25-28`), otro módulo
>   con su propia `ENTRY_FIELDS`. Sus asserts `:48`/`:64` son sobre el ledger de la Fragua
>   Nocturna. **Tocar `ci_run_ledger` no lo mueve.** Sale de la lista.
> - `tests/test_plan258_ledger_veracidad.py` **sí** toca `ci_run_ledger.ENTRY_FIELDS`, pero solo
>   por **pertenencia** (`:155-156`: `"env" in ...`, `"schema_version" in ...`) y por un literal
>   del código fuente (`:395`). Agregar 2 claves al final es **seguro** en los dos casos. Se
>   corre igual, como control.
> - Verificado además con un barrido sobre `backend/tests/*.py`: **ningún** test asserta el
>   conjunto **completo** de `ci_run_ledger.ENTRY_FIELDS`. El único riesgo real es el silencio de
>   la allowlist, que ya está cubierto.

> **Flaky conocido de esta casa:** todo test que toque la DB bajo pytest con shared-cache puede
> dar `database table is locked`. Estos archivos se corren **8 veces cada uno** antes de
> declararlos verdes, y se usa el helper de reintento del Plan 253 donde aplique.

---

### F5 — Ningún camino escribe un YAML con un secreto literal — **REESCRITA (v2: C1, C2, C3, C9; v3: C5, C6, C7, C8)**

**Objetivo:** cerrar el KPI-4. Hoy los **dos** caminos de escritura commitean sin frenar por
secreto literal, pero **por motivos distintos** (§2.2 Hueco C). El fix es distinto en cada uno.

#### 5.1 Dos motores, dos conjuntos, y el filtro es POR CÓDIGO

**Hecho verificado que hunde el diseño del v1:** `audit_yaml` (`cicd_audit_core.py:269-273`) corre
**`check_security` (SEC\*) + `check_recommendations` (OPT\*)** y nada más. De `pipeline_lint` sólo
importa constantes de severidad (`:26`). **`PL012`/`PL013`/`PL014` no existen para `audit_yaml`.**
Y las tres son `SEV_WARNING` (`pipeline_lint.py:703,731,749`; `SEV_WARNING = "warning"` en `:19`),
así que un filtro `severity == "error"` las descarta aunque estuvieran.

Conjuntos congelados, en **un solo lugar**, en `services/ci_env_gate.py`:

```python
# Motor: services.cicd_audit_core.audit_yaml  (SEC* + OPT*)
SECRET_BLOCKING_AUDIT = ("SEC001",)

# Motor: services.pipeline_lint.lint_yaml  (PL001..PL014)
# OJO: son SEV_WARNING. Se filtra POR CODIGO, jamas por severidad: filtrar por
# severity=="error" las descarta a las tres y el gate queda inerte (bug del plan v1).
SECRET_BLOCKING_LINT = ("PL012", "PL014")
```

> **(v3, C8) Los dos nombres son PÚBLICOS (sin guion bajo)**: `SECRET_BLOCKING_LINT` la importa
> `services/pipeline_diff.py` (§5.3) y las dos las importa el archivo de tests. Un nombre privado
> cruzando el borde del módulo es deuda inmediata.

- **`PL013` NO bloquea**: dice "el secreto no está en la caja fuerte", que es exactamente lo
  que este plan viene a resolver y **degrada a `unknown` cuando `known_variables is None`**
  (`pipeline_lint.py:736`). Bloquear con PL013 volvería incommiteable media pipeline legítima.

#### 5.2 Camino 1 — `api/pipeline_generator.py:52` `commit_route` (el hueco literal)

Antes de `writer.commit_file` (`:77`):

```python
if getattr(_config.config, "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED", False):
    from services.ci_env_gate import evaluar_gate_secretos   # noqa: PLC0415
    # (v3, C7) MISMA decision binaria que el endpoint ya toma en :67 y :70 para elegir
    # el renderer y la ruta. `target` NO esta validado (`:65` es un body.get pelado):
    # pasarlo crudo mete None/"ADO"/"azure_devops" en el motor de reglas y apaga
    # SEC003/SEC005/SEC007 en silencio (cicd_security_rules.py:471,474,477).
    prov_reglas = "ado" if target == "ado" else "gitlab"
    duros, auditado = evaluar_gate_secretos(yaml_str, provider=prov_reglas)
    if not auditado:                                                     # (v2, C9 / v3, C6)
        return jsonify({"error": "no se pudo auditar el YAML: no se commitea",
                        "kind": "secret_gate_indeterminado"}), 422
    if duros:
        return jsonify({"error": "el YAML contiene un secreto literal",
                        "kind": "secret_in_yaml",
                        "findings": [{"code": c, "location": l, "message": m}
                                     for c, l, m in duros]}), 422
```

y en `services/ci_env_gate.py`:

```python
def evaluar_gate_secretos(yaml_text: str, *, provider: str) -> tuple:
    """-> (duros, auditado). PURO respecto de red; llama a los DOS motores.
    provider viene en vocabulario de reglas ('ado'|'gitlab') — ver §4.4.
    `auditado` es False cuando el auditor NO analizo el documento; en ese caso NO se
    commitea, porque un gate que no vio nada no es un gate verde.
    """
```

- **(v2, C2 / v3, C7)** El proveedor que entra acá es **`"ado"` | `"gitlab"`, y punto**. La
  traducción la hace el llamador espejando la decisión que el endpoint ya toma (`:67`, `:70`).
  El v2 decía `provider=target` "identidad", asumiendo que `body["target"]` **ya** valía `"ado"` o
  `"gitlab"`; el código **no lo valida** (`:65` `target = body.get("target")`), así que la
  identidad propaga basura al motor de reglas. Es el mismo fallo-abierto de C2, por otra puerta.

- **(v2, C9 — REESCRITO v3, C6) Cómo se calcula `auditado`, literal.** El v2 afirmaba que
  `audit_yaml` devuelve `findings=()` cuando el YAML supera 512 KB. **Es falso.** Los tres
  caminos de "no analicé" son distintos y solo uno da findings vacío:

  | Caso | Dónde | Qué devuelve `audit_yaml` |
  |---|---|---|
  | YAML > 512 KB | `cicd_audit_core.py:258-259` | `_aud000(...)` ⇒ `ok=True`, **`findings=(AUD000,)`** |
  | YAML no parseable | `:260-264` | `_aud000(...)` ⇒ `ok=True`, **`findings=(AUD000,)`** — el v2 **ni lo mencionaba** |
  | YAML no-dict | `:265-267` | `ok=True`, `findings=()` |

  (`_aud000` está en `:239-248` y construye el finding `code="AUD000", severity=SEV_WARNING`.)

  Con la premisa del v2, un modelo menor escribe `auditado = not rep.findings` o
  `auditado = bool(rep.findings)` y **falla abierto** en el caso >512 KB. Regla correcta, para
  copiar tal cual:

  ```python
  import yaml as _yaml
  rep = audit_yaml(yaml_text, provider=provider)
  _no_analizado = any(f.code == "AUD000" for f in rep.findings)
  try:
      _es_dict = isinstance(_yaml.safe_load(yaml_text), dict)
  except Exception:
      _es_dict = False
  auditado = (not _no_analizado) and _es_dict
  ```

**Gotcha dura (recurrida en esta casa):** el enmascarado corre **después** del gate, nunca antes.
Si se pasa el YAML por `mask_token_values` y recién ahí se audita, SEC001 no encuentra nada
(`cicd_security_rules.py:121-122` justamente usa `mask_token_values(valor) == valor` como test de
"no parece token") y el gate **falla abierto** — verde perfecto y fuga real.

#### 5.3 Camino 2 — el editor NL: **promover, no agregar** (v2, C3)

El v1 decía "sumar las reglas SEC/PL al conjunto que evalúa `api/pipeline_editor.py:256`". Es
falso y manda al archivo equivocado:

- `api/pipeline_editor.py:256-262` sólo **serializa** un `review` que le llega hecho (`:130`).
- Quien lo arma es **`services/pipeline_diff.py:196` `review_patch`**, y en `:203-204` **ya corre
  `lint_yaml`** sobre `before` y `after`. PL012/PL014 **ya están calculadas**.
- Lo que las hace inocuas es `:206`: `lint_err = tuple(f for f in nuevos if f.severity == SEV_ERROR)`
  y `passed=not lint_err`.

**Fix, en `services/pipeline_diff.py`, aditivo y mínimo — REESCRITO (v3, C8):**

```python
# services/pipeline_diff.py — junto a las constantes de gate (:26-29)
GATE_SECRET = "SECRET"          # (v3, C8) NO existia: hay que declararla acá

# firma: el gate se decide AFUERA y entra como parametro. `pipeline_diff` sigue PURO.
def review_patch(before: str, after: str, hunks: tuple, *, profile: str,
                 repo_root: Optional[str] = None, verb: str = "",
                 secret_gate: bool = True) -> EditReview:
    ...
    # dentro de review_patch, DESPUES del gate G-LINT actual (que no se toca)
    from services.ci_env_gate import SECRET_BLOCKING_LINT   # noqa: PLC0415

    _fuga = tuple(f for f in nuevos if f.code in SECRET_BLOCKING_LINT) if secret_gate else ()
    gates.append(GateDelta(
        gate=GATE_SECRET, passed=not _fuga, new_errors=_fuga,
        new_warnings=(), resolved=()))
```

> **(v3, C8) Por qué la flag NO se lee acá.** `services/pipeline_diff.py` declara en su docstring
> *"PURO salvo la verificacion opcional de rutas contra `repo_root`"* (`:9`) y **verificado: tiene
> CERO referencias a `config`**. El v2 decía "el gate nuevo se gatea con
> `STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED`: con la flag OFF, `_fuga` se fuerza a `()`" sin
> decir **dónde** se lee la flag ⇒ un modelo menor mete `import config` adentro de `review_patch`
> y rompe la pureza del módulo.
> **Quien lee la flag es el llamador**, `api/pipeline_editor.py:130`, que ya importa config:
> ```python
> review = review_patch(yaml_text, res.text, res.hunks, profile=perfil,
>                       repo_root=repo_root, verb=intent.verb,
>                       secret_gate=getattr(_cfg(), "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED", False))
> ```
> `secret_gate` es **kwarg con default `True`**, así que cualquier otro call-site de
> `review_patch` (si existiera) sigue compilando y con el gate puesto.
>
> **Nombre de la constante:** `SECRET_BLOCKING_LINT`, **público (sin guion bajo)**, porque cruza
> el borde del módulo. El v2 escribía `_SECRET_BLOCKING_LINT` privado y después lo importaba
> desde otro archivo, que es la contradicción que produce el clásico "o la renombro o la
> re-exporto" a mitad de la implementación.
>
> **Test de pureza (binario):** `grep -c "config" backend/services/pipeline_diff.py` ⇒ **0**.

- Es un **gate NUEVO** (`GATE_SECRET`), no una mutación del G-LINT existente: las reglas RS/GL y
  el comportamiento actual de G-LINT quedan **byte-idénticos** (backward-compatible, §3.7).
- `EditReview.ok` ya es la conjunción de los gates, así que `api/pipeline_editor.py:257`
  (`if not review.ok`) devuelve el `422 gates_en_rojo` **sin tocar una línea del endpoint**.
- `_serializar_review` (`api/pipeline_editor.py:91-110`) itera `review.gates` genéricamente y
  serializa cada finding con `_serializar_finding`. Como los findings del gate nuevo son
  **`LintFinding`, la misma clase que ya come el G-LINT**, no hay mezcla de shapes.
  **Gotcha de esta casa que esto evita:** los findings de lint y los de las reglas semánticas
  tienen **campos disjuntos**; meter unos en el gate del otro revienta el serializador. Por eso el
  gate nuevo se alimenta **sólo** de `lint_yaml`, y SEC001 **no** entra por este camino (el editor
  ya tiene su propio audit semántico en `:212+`).
- El gate nuevo se gatea con `STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED`: con la flag OFF, el
  llamador pasa `secret_gate=False`, `_fuga` queda en `()` y `passed=True`. **La flag se lee en
  `api/pipeline_editor.py`, jamás en `pipeline_diff.py`** (v3, C8).

#### **[ADICIÓN ARQUITECTO 1] — gate anti-inerte: cada código bloqueante se prueba con su `repro`**

El error de fondo del v1 no fue tipear mal un código: fue **declarar un conjunto bloqueante sin
poder probar que el motor invocado lo produce**. El repo ya resolvió ese problema para sus propias
reglas y hay que reusarlo, no reinventarlo:

`services/cicd_audit_core.py:106-115` — `audit_rule` **rechaza registrar** una regla sin
`repro=(provider, yaml_minimo)`, con este motivo escrito en el código:

> *"`repro` es OBLIGATORIO: sin el, la regla podria quedar inerte (0 hits por bug y no por corpus
> limpio) y el panel mostraria verde falso."*

Se aplica el mismo criterio al conjunto bloqueante de este plan:

```python
# tests/test_plan260_secret_commit_gate.py
def test_f5_cada_codigo_bloqueante_dispara_de_verdad():
    """KPI-6. Para CADA codigo de los dos conjuntos, el repro QUE EL PROPIO CATALOGO
    DECLARA lo produce en el motor que el gate realmente invoca. Un codigo que no
    dispara es codigo muerto en un gate de seguridad: peor que no tenerlo, porque
    parece que protege."""
    from services.cicd_audit_core import AUDIT_RULES, audit_yaml
    from services.pipeline_lint import _RULES, lint_yaml
    from services.ci_env_gate import SECRET_BLOCKING_AUDIT, SECRET_BLOCKING_LINT

    for code in SECRET_BLOCKING_AUDIT:
        assert code in AUDIT_RULES, "%s no existe en el motor de audit" % code
        assert AUDIT_RULES[code].repro, "%s sin repro en el catalogo" % code
        prov, yaml_min = AUDIT_RULES[code].repro
        rep = audit_yaml(yaml_min, provider=prov)
        assert any(f.code == code for f in rep.findings), \
            "%s esta declarado bloqueante pero su propio repro no lo dispara" % code

    # (v3, C5) El linter TAMBIEN declara repro por regla: se lee del catalogo, NO se
    # escribe un fixture a mano. `_RULES` guarda (code, severity, providers, fn, repro)
    # — pipeline_lint.py:66-77, y se itera igual en :815.
    repros_lint = {c: r for c, _s, _p, _f, r in _RULES}
    for code in SECRET_BLOCKING_LINT:
        assert repros_lint.get(code), "%s sin repro en el catalogo del linter" % code
        prov, yaml_min = repros_lint[code]
        rep = lint_yaml(yaml_min, prov)
        assert any(f.code == code for f in rep.findings), \
            "%s esta declarado bloqueante pero lint_yaml no lo produce" % code
```

**Con este test escrito PRIMERO, el diseño del v1 se cae en F5 antes de escribir el endpoint**:
`audit_yaml` nunca produce PL012/PL014 y el assert lo dice con el mensaje exacto. Es el test que
convierte un falso verde estructural en un rojo temprano, y su costo es de una sola función.

> **(v3, C5) Corrección de un anclaje falso del v2.** El v2 decía *"`_REPRO_LINT` es un dict de 2
> entradas en el propio archivo de test (el linter, a diferencia del auditor, no exige `repro` por
> contrato)"*. **Falso, y verificado en runtime:** `pipeline_lint.py:70-77` define
> `_rule(code, severity, providers=(...), repro=None)` con docstring *"repro: (provider,
> yaml_minimo_que_dispara_la_regla) — **OBLIGATORIO para toda regla**"*, guarda la 5-tupla en
> `_RULES` (`:75`) y la desempaqueta en `:815`. **PL012, PL013 y PL014 declaran su `repro`**
> (`:704-706`, `:732-733`, `:750-751`).
> Por qué importa y no es cosmético: un fixture escrito a mano prueba que existe **algún** YAML que
> dispara la regla, **no** que el reproductor que el catálogo declara la dispare. Si mañana la
> regla cambia su condición, el fixture a mano sigue verde — que es **exactamente** el falso verde
> estructural que esta ADICIÓN dice matar. Leer el catálogo cuesta una línea y no miente.

**Tests PRIMERO** — `backend/tests/test_plan260_secret_commit_gate.py`:
- **`test_f5_cada_codigo_bloqueante_dispara_de_verdad`** *(ADICIÓN 1, KPI-6)*.
- **`test_f5_vocabulario_de_provider`** *(v2, C2)* — el string que llega a `audit_yaml` está en
  `api.pipeline_audit._PROVIDERS`; `"azure_devops"` hace fallar el test.
- **`test_f5_target_basura_no_apaga_reglas`** *(v3, C7)* — con `target=None`, `target="ADO"` y
  `target="azure_devops"`, el string que llega a `audit_yaml` sigue siendo `"ado"` o `"gitlab"`
  y **espeja** el renderer elegido en `:67`. Se espía `audit_yaml` y se compara el kwarg.
- `test_f5_generator_rechaza_secreto_literal` — 422, `kind == "secret_in_yaml"`, y
  `commit_file` recibió **0 llamadas**.
- `test_f5_generator_deja_pasar_yaml_limpio` — el camino feliz no se rompió.
- **`test_f5_yaml_no_auditable_no_se_commitea`** *(v2 C9; ampliado v3, C6)* — **TRES** casos:
  YAML > 512 KB, YAML **no parseable** y YAML no-dict ⇒ `422 secret_gate_indeterminado`, 0
  llamadas a `commit_file`. El caso "no parseable" es el que el v2 no cubría y el que devuelve
  `AUD000` con `findings` **no vacío**: sin él, una implementación con `auditado = not findings`
  pasa los otros dos y falla abierto justo acá.
- `test_f5_editor_rechaza_secreto_literal` — vía `review_patch`, gate `GATE_SECRET`.
- **`test_f5_editor_gate_lint_intacto`** *(v2, C3)* — el `GateDelta` de `GATE_LINT` es idéntico al
  de antes del cambio para un caso sin fuga (backward-compatible).
- **`test_f5_pipeline_diff_sigue_puro`** *(v3, C8)* — el fuente de `services/pipeline_diff.py`
  **no contiene** la subcadena `config`, y `review_patch` acepta `secret_gate` con default `True`.
- **`test_f5_pl013_no_bloquea`** (control negativo: un gate que bloquea de más es inservible).
  **(v2)** Ahora corre contra `lint_yaml`, donde PL013 **sí existe**: antes era vacuo.
- **`test_f5_el_gate_corre_antes_del_masking`** — se audita el texto crudo; con el orden invertido
  el test se cae.
- **`test_f5_el_mensaje_de_error_no_trae_el_secreto`** (KPI-5) — el 422 trae `code` + `location`,
  y el valor inyectado **no** aparece en el cuerpo.
- `test_f5_flag_off_no_bloquea` — leyendo `config.config`, en **los dos** caminos.
- `test_f5_conjuntos_bloqueantes_son_cerrados` — las dos tuplas congeladas, enumeradas literales
  (si alguien agrega una regla, este test lo obliga a pensarlo **y** la ADICIÓN 1 lo obliga a
  probar que dispara).

**Criterio BINARIO:** los 15 verdes **y** las baselines **medidas hoy**: `test_plan248_api.py`
**7 passed**, **más (v2, C3)** los del editor y el diff, que ahora se tocan de verdad:
`test_plan250_flag.py`, `test_plan250_edit_intent.py` **y `test_plan250_gates_delta.py`** (que
importa `services.pipeline_diff` directo, `:11`, y es el que rompería un `GateDelta` de más) en su
baseline previa. **Medir los tres ANTES de tocar nada.**

---

### F6 — UI: declarar en un clic y ver el bloqueo antes de confirmar

**Objetivo:** que el operador no vuelva a tipear un nombre que Stacky ya conoce, y que vea el
bloqueo **antes** de apretar el botón rojo.

**Gotcha estructural de esta casa:** RTL y jsdom **no** están instalados. Toda la lógica testeable
va en `.ts` **puro**; el `.tsx` queda como cableado fino y su validación es `npx tsc --noEmit` + el
smoke visual del operador. Un `.tsx` **nuevo** tiene alcance 0 en `uiDebtRatchet`, así que si hace
falta estilo dinámico se usa `ref` + `effect`, **nunca** `style={{}}`.

**Archivos:**
1. **NUEVO** `frontend/src/devops/pipelineDeclareModel.ts` — puro:
   `resumenDeclaracion(plan)` -> *"Stacky va a crear N nombres; vos solo pegás los valores"*;
   `agruparSkipped(plan)` -> motivo -> keys;
   **(v2, ADICIÓN 3)** `avisoContadorNoBaja(actual, proyectado)` -> el texto que explica que la
   alerta **no** va a bajar y por qué eso es correcto;
   **(v2, C6)** `avisoMasking(needsMasking)` -> *"estas N quedaron sin enmascarar: marcá 'secreta'
   al cargar el valor o GitLab lo va a imprimir en el log del job"*.
2. **NUEVO** `frontend/src/devops/triggerGateModel.ts` — puro:
   `mensajeDeBloqueo(readiness)` -> *"No podés disparar: faltan N valores (X, Y, Z)"*;
   `puedeDisparar(readiness, ack)`.
2bis. **(v3, C1) `frontend/src/devops/pipelineEnvMatrixModel.ts` — el titular pasa a contar el
   pendiente VISIBLE.** Es el único lugar donde el sistema se mentía: `headline()` (`:75-79`) lee
   `m.pending_count`, que cuenta **solo** `falta`, así que una celda `manual` recién declarada
   desaparecía del titular (§2.5, MEDIDO). Cambio mínimo y **aditivo**:
   ```ts
   /** (Plan 260) trabajo que el operador todavia tiene que hacer, incluido lo que el
    *  proveedor no puede verificar. `pending_count` NO se toca: es el contrato del 251. */
   export function pendienteVisible(m: EnvMatrixResponse): number {
     let n = 0;
     for (const c of m.cells || []) {
       if (c.state === 'falta') n += 1;
       else if (c.state === 'manual' && c.source === 'declarada_sin_valor_verificable') n += 1;
     }
     return n;
   }
   ```
   `headline()` pasa a usar `pendienteVisible(m)` en vez de `m.pending_count`.
   **`pendingByEnvironment` (`:63-72`) usa el mismo criterio**, o el titular y la tabla por
   entorno dicen números distintos. `source` ya viaja por la frontera JSON: `to_json_payload`
   serializa cada celda con `asdict(c)` (`pipeline_environments.py:534`).
3. `frontend/src/components/devops/PipelineEnvMatrixPanel.tsx` — botón **"Declarar los nombres"**
   -> `declare-preview` -> lista exacta de qué se va a crear **+ los dos contadores** -> `confirm`
   -> `declare`. Visible solo con `STACKY_PIPELINE_ENV_DECLARE_ENABLED` (las flags de UI se leen
   de `/api/diag/health`). El CTA "Completar" (`:81-88`, handler en `:79`) pasa a llevar la key
   preseleccionada a la sección de variables.
4. `frontend/src/components/devops/VariablesSection.tsx:71` — `canSubmit` deja de exigir `value`
   **solo** cuando el alta viene de una declaración (`modo="declarar"`). El alta manual sigue
   exigiendo valor: no se degrada el formulario existente. **(v2, C6)** El aviso de masking reusa
   `maskingWarning` / `canBeMasked`, que **ya existen** en `:72`.
5. `frontend/src/components/PipelineTriggerCard.tsx` — el modal HITL muestra la `readiness` del
   `trigger-preview`; con `bloquea` el botón de confirmar queda deshabilitado y aparece un
   checkbox explícito *"Entiendo que faltan valores y quiero disparar igual"* que habilita
   `acknowledge_missing`.
   **(v2, C13/C16, literal para el implementador):**
   - `handleTrigger` está en **`:112-135`** (el rango `:111-134` del v1 apuntaba al handler, no al
     modal; el `return` del JSX arranca en `:137`).
   - `CIPipeline.trigger(project, ref, sha, itemId, true)` (`:117`) tiene firma **posicional de 5
     argumentos**: `acknowledge_missing` se agrega como **6º parámetro opcional con default
     `false`**, así los otros 2 call-sites (si existieran) siguen compilando.
   - El `catch` de `:128-131` colapsa todo a `err.message` ⇒ **el cuerpo del 409 se pierde**. Hay
     que leer el 409 con `rawPost` y renderizar `missing` con `mensajeDeBloqueo`.
   - Este archivo **ya tiene** `style={{...}}` inline (`:138-139`): medir el baseline de
     `uiDebtRatchet` **antes** de tocarlo y no sumar ni uno nuevo (usar el CSS module o `ref`).
6. `frontend/src/api/endpoints.ts` — wrappers de `/declare`, `/declare-preview`, el `?yaml_path=`
   del preview y el 6º parámetro de `trigger`.
   **Gotcha dura:** `api.get`/`api.post` **lanzan excepción** en non-2xx. El 409 del gate y el 422
   del F5 traen cuerpo útil ⇒ hay que usar `rawPost`/`rawGet` o el detalle se pierde y el operador
   ve un error genérico.

**Tests PRIMERO** — `frontend/src/devops/__tests__/pipelineDeclareModel.test.ts`,
`triggerGateModel.test.ts` y `pipelineEnvMatrixModel.plan260.test.ts` *(v3, C1: archivo **nuevo**;
el `pipelineEnvMatrixModel.test.ts` del 251 **no se toca**, para no mover su baseline)*:
- `test_f6_resumen_dice_cuantos_nombres`
- `test_f6_skipped_agrupado_por_motivo`
- **`test_f6_aviso_contador_no_baja`** *(ADICIÓN 3)*
- **`test_f6_aviso_masking_lista_las_keys`** *(v2, C6)*
- `test_f6_mensaje_de_bloqueo_lista_nombres_no_valores`
- `test_f6_puede_disparar_solo_con_ack`
- `test_f6_degradado_no_bloquea_el_boton`
- `test_f6_advierte_muestra_aviso_pero_habilita`
- **`test_f6_titular_cuenta_declarada_sin_valor_verificable`** *(v3, C1)* — con una celda
  `("manual","declarada_sin_valor_verificable")` y `pending_count === 0`, el titular dice
  *"Te falta 1 valor…"*, **no** *"No falta nada"*. Este test es el gemelo en el frontend del
  `test_f3_ado_secreto_declarado_no_apaga_el_titular`.
- **`test_f6_titular_ignora_manual_ajeno`** *(v3, C1, control negativo)* — una celda `manual` con
  `source === "ninguna"` (un `service_connection` sin resolver) **NO** suma al titular: el plan
  no convierte todo `manual` en pendiente, solo el declarado-sin-valor-verificable.
- **`test_f6_pending_by_environment_usa_el_mismo_criterio`** *(v3, C1)* — la suma por entorno
  coincide con el titular.
- **`test_f6_readiness_muestra_la_latencia`** *(v3, ADICIÓN 5)* — con `elapsed_ms > 1500` y
  `verdict === "degradado"`, el texto dice que no se pudo verificar a tiempo y **no** bloquea.

**Comandos:**
```powershell
npx vitest run src/devops/__tests__/pipelineDeclareModel.test.ts
npx vitest run src/devops/__tests__/triggerGateModel.test.ts
npx vitest run src/devops/__tests__/pipelineEnvMatrixModel.plan260.test.ts
npx vitest run src/devops/__tests__/pipelineEnvMatrixModel.test.ts
npx tsc --noEmit
```
**Correr por archivo:** la corrida completa de vitest contamina cross-file en este repo.

**Criterio BINARIO:** los 12 verdes, **el archivo del 251
(`pipelineEnvMatrixModel.test.ts`) en su baseline previa sin tocarlo**,
`npx tsc --noEmit` en **0 errores**, y los 8 ratchets del
frontend sin crecer (medir el baseline **antes** de tocar nada: hay rojos **ajenos** conocidos —
`formDebtRatchet` y `devopsPollingRatchet` por `BuildWorkshopSection.tsx:93`. Un rojo ajeno se
prueba con un **worktree en el commit base**, no se argumenta).

**Pendiente declarado (no automatizable):** smoke visual — abrir DevOps -> *Matriz de entornos*,
pegar una pipeline real **con al menos un secreto** *(v3, C1: es el caso que se rompía)*, apretar
*Declarar los nombres*, confirmar que la alerta **sigue diciendo "te faltan N"**, cargar un valor,
ver bajar el contador, e intentar disparar con y sin faltantes.

---

### F7 — **(v2, C14) Huella de regresión**

**Objetivo:** que los dos falsos verdes que este plan corrige queden registrados como huella, para
que el próximo que los reintroduzca los vea nombrados.

**Archivo:** `Stacky Agents/docs/sistema/error_fingerprints.json`.

#### **(v3, C10) El schema REAL del archivo — el v2 inventaba campos**

**Verificado:** el archivo es un objeto `{"schema_version", "description", "fingerprints": [...]}`
con **42** huellas, y cada huella usa **estas** claves:

```
id · title · class · status · log_pattern · log_guarded · killed_by · killed_commit
   · date_resolved · guard_test · evidence · note
```

**No existe un campo `test`** — es **`guard_test`**, y en las 42 entradas es una **ruta de
archivo** (`"tests/test_plan258_estanqueidad_arnes.py"`), **sin** `::funcion`. El v2 hablaba de
"síntoma / causa / Test que lo cubre" y su test decía *"el `test` de cada huella"*: con eso, un
modelo menor inventa un campo nuevo y rompe la homogeneidad de un corpus de 42 entradas.

Se agregan **dos entradas al final de `fingerprints`**, con **exactamente** las mismas claves que
la última entrada existente (ni una más, ni una menos). El nombre de la función de guardia va en
`note`, que es texto libre:

1. **`id: "declarar_apaga_la_alerta"`** — `title`: *"Declarar los nombres apago la alerta de
   faltantes"*. `class`: `"false-green"`. `status`: `"resolved"`. `killed_by`: `"plan 260 F1+F3"`.
   `guard_test`: `"tests/test_plan260_declare_endpoint.py"`.
   `note`: menciona `test_f3_pendiente_visible_no_baja_al_declarar` **y** el caso `(azure_devops,
   secret)`, que es el que sobrevivió a la v2 (§2.5).
   `evidence`: `has_value` hardcodeado a `True` (`services/ado_variables.py:42`,
   `services/gitlab_variables.py:41,57`) + `_resolver_celda` resolviendo por mera presencia de la
   key (`services/pipeline_env_resolver.py:140-147`) + `pending_count` contando solo `falta`
   (`services/pipeline_environments.py:514`).
2. **`id: "gate_de_secretos_inerte"`** — `title`: *"Un gate de secretos declarado contra un motor
   que no produce sus codigos"*. `class`: `"false-green"`. `killed_by`: `"plan 260 F5"`.
   `guard_test`: `"tests/test_plan260_secret_commit_gate.py"`.
   `note`: menciona `test_f5_cada_codigo_bloqueante_dispara_de_verdad` y que el repro se lee
   **del catálogo** (`AUDIT_RULES[code].repro` y `pipeline_lint._RULES`), nunca de un fixture.
   `evidence`: `audit_yaml` corre solo SEC*+OPT* (`services/cicd_audit_core.py:269-273`) y las PL
   de secreto son `SEV_WARNING` (`services/pipeline_lint.py:703,731,749`).

**Tests PRIMERO** — `backend/tests/test_plan260_fingerprints.py`:
- `test_f7_json_valido_y_solo_crecio` — el archivo parsea, `len(fingerprints) == 44` y las
  **42** entradas previas son **byte-idénticas** (se compara el `json.dumps(sort_keys=True)` de
  cada una contra un baseline capturado antes de tocar el archivo).
- **`test_f7_las_huellas_nuevas_usan_el_schema_existente`** *(v3, C10)* — para cada huella nueva,
  `set(nueva.keys()) == set(fingerprints[-3].keys())` (la última existente). **Este test es el
  que impide inventar campos.**
- **`test_f7_guard_test_apunta_a_un_archivo_que_existe`** *(v3, C10)* — el `guard_test` de cada
  huella nueva se resuelve contra `backend/` y el archivo **existe**. (No se exige `::funcion`:
  ninguna de las 42 existentes la usa y romper esa forma es deuda gratis.)

**Criterio BINARIO:** los 3 verdes y el archivo parseable con `json.loads`.

---

## 6. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Declarar apaga la alerta** (§2.3 y §2.5, **MEDIDO dos veces**) | F1 va antes que F3; `test_f3_pendiente_visible_no_baja_al_declarar` **parametrizado sobre los 4 casos `proveedor x kind`** es el criterio binario del plan; el corpus de §4.6 hace que un caso nuevo sea rojo; ADICIÓN 3 lo hace visible en producción con la proyección **por caso** |
| **R14** *(v3, C1)* | **El titular del panel y `pending_count` dicen cosas distintas y alguien "arregla" el titular volviéndolo a `pending_count`** | El titular cuenta el **pendiente visible** por diseño (§3.2) y hay dos tests que lo congelan (`test_f6_titular_cuenta_declarada_sin_valor_verificable` y su control negativo). `pending_count` **no se toca**: es el contrato del 251 y sigue significando "evidencia positiva de faltante", que es lo que el gate usa para bloquear |
| **R15** *(v3, C2)* | **El gate agrega espera real sin techo al botón de disparo** | `future.result(timeout=1.5)` acota la **espera**, no la medición; el test compara **tiempo de pared** y `readiness.elapsed_ms` viaja en la respuesta (ADICIÓN 5) |
| R2 | El gate bloquea disparos legítimos por un falso positivo de detección | Bloquea **solo** con `state == "falta"` **y** `resolved=True`; `manual`/desconocido **advierte**. `acknowledge_missing` siempre disponible. Flag apagable por UI |
| R3 | Un bug del gate deja al operador sin poder disparar nada | `try/except` que degrada a `degradado`; test dedicado (`test_f4_una_excepcion_del_gate_no_rompe_el_trigger`) |
| R4 | Fuga de un valor por el nuevo `has_value` o por el 409 | 3 controles negativos con un password real que **no** es un token conocido (los prefijos canónicos no lo atrapan — lección medida del Plan 251) |
| **R5** *(v2, C6)* | **Un secreto queda sin enmascarar en GitLab y sale en el log del job** | Se declara con `secret=True` y se reusa el reintento del 94; `needs_masking` + aviso accionable en la UI, reusando `canBeMasked` que ya existe |
| R6 | Se pisa una variable que ya tenía valor | `plan_declaration` no incluye celdas `definido`; `test_f3_nunca_pisa_una_variable_con_valor` |
| R7 | El gate SEC bloquea de más y vuelve incommiteable una pipeline legítima | Conjuntos **cerrados** y chicos (1 + 2 reglas); PL013 explícitamente excluido con test |
| R8 | `test_plan251_env_matrix_resolve.py` se pone rojo porque congelaba el bug | Se corrige el test, **no** se corrige el plan para complacerlo; el desvío se documenta |
| R9 | Flakiness de SQLite bajo pytest | Correr **por archivo**, 8 veces, con el helper de reintento del 253 |
| **R10** *(v2, C1)* | **Un gate de seguridad inerte que parece verde** | ADICIÓN 1: cada código bloqueante se prueba con su `repro` contra el motor que el gate invoca (KPI-6) |
| **R11** *(v2, C3)* | `pipeline_diff.py:203-204` corre el linter con `"ado"` hardcodeado, así que en un proyecto GitLab el gate del editor usa el perfil ADO | **Deuda ajena del Plan 250. NO se arregla acá** (scope creep). Se documenta para que el gate nuevo no se lea como una garantía completa en GitLab |
| **R12** *(v2, ADICIÓN 2)* | El operador **borra** un valor entre el preview y el disparo, dentro de los 60 s, y el veredicto reusado deja pasar | Ventana chica (la misma que ya existe para idempotencia), el `yaml_sha256` corta el reuso ante cualquier cambio de YAML, y la respuesta declara `readiness.source == "preview_reusado"`. Riesgo aceptado y visible |
| **R13** *(v2, C4)* | El gate agrega latencia perceptible al botón de disparo | Presupuesto duro de 1500 ms (KPI-7) + reuso del veredicto del preview; excedido ⇒ `degradado`, nunca espera indefinida |
| **R16** *(v3, C4)* | **Un veredicto `degradado` del preview se reusa y abre el gate** | Solo entra al almacén un veredicto con `resolved=True` y `yaml_sha256` no vacío; el sha es parte de la **clave**, no una comparación posterior. Test dedicado |
| **R17** *(v3, C6)* | **El gate de secretos falla abierto con un YAML no parseable** | `auditado` se calcula con `AUD000` + `isinstance(doc, dict)`, no con `findings == ()`; los **tres** casos tienen test |

---

## 7. Fuera de alcance — va al Plan **261**

Este plan **no** toca el eje "generar una pipeline desde lenguaje natural con un agente de Claude
Code eligiendo modelo y effort". Ese eje está **ausente** hoy y necesita su propio plan:

- **No existe** un camino "texto libre -> PipelineSpec nueva". El único NL que existe
  (`api/pipeline_editor.py:346` `interpret_edit`) **edita un YAML preexistente** con un catálogo
  cerrado de 7 verbos (`services/pipeline_patcher.py:443-451`) y exige `beforeYaml`.
- **No hay selector de modelo ni de effort** en todo el eje de pipelines. `ModelEffortPicker.tsx:19`
  tiene 3 consumidores y ninguno es de pipelines.
- **Bug vivo (§8)** que el 261 debe cerrar en su F0.
- Todo el material existe y está probado: catálogo `services/model_catalog.py:71`, clamp
  `services/llm_router.py:60` `clamp_effort_for_model`, endpoint `api/agents.py:1362`, picker
  `ModelEffortPicker.tsx:19`, y `agent_runner.run_agent` (`backend/agent_runner.py:77-100`) que
  **ya** acepta `model_override` (`:86`) y `effort_override` (`:87`) y los baja al CLI como
  `--model` / `--effort` (`services/claude_code_cli_runner.py:2293-2302`).

**El número 261 queda reservado. Los números 244 y 245 están reservados por referencia** (el 243
remite sus F4..F9 al 244, y el 242 su corte F3..F9 al 245) **y no tienen documento: no usarlos.**

> **(v3, C14) Nota de numeración — actualizada al 2026-07-27, leída de `docs/` en frío.** Con
> documento existen hoy: **260, 263, 264, 265, 266, 267, 268, 269**. **261 y 262 siguen SIN
> documento**, así que la reserva del 261 de este plan sigue en pie y el 262 queda libre. El
> **próximo número libre para un plan nuevo es el 270**. (La nota del v2 decía que la camada era
> "260, 263, 264, 265": quedó stale cuando nacieron 266-269.)

---

## 8. Bug VIVO detectado al escribir este plan (no lo arregla este plan)

`api/pipeline_editor.py:337-343`:

```python
def _modelo_para_intent() -> str:
    try:
        return str(getattr(_cfg(), "PM_LLM_MODEL", "") or "mock-1.0")
    except Exception:
        return "mock-1.0"
```

**`PM_LLM_MODEL` no existe en `backend/config.py`** (verificado: `grep -n "PM_LLM" config.py` ⇒
**0 hits**; en todo el backend la única aparición es esa misma línea). ⇒ `_modelo_para_intent()`
devuelve **siempre** el literal `"mock-1.0"`.

Y ese string **no es solo una etiqueta de costo**: `services/pm/pm_llm_client.py:197` lo pasa como
`model=spec.model` a `anthropic.Anthropic().messages.create(...)`, y `:251` hace lo propio con el
backend de Copilot. ⇒ **con `STACKY_PM_LLM_BACKEND` en cualquier valor que no sea `mock`, el
intérprete NL de pipelines llama al proveedor con un id de modelo inexistente.** Además
`_compute_cost_usd(spec.model, ...)` (`:316`) atribuye el costo a un modelo que no corrió.

El arreglo correcto **no** es hardcodear otro id: es cablear la elección de modelo/effort del
operador, que es precisamente la **F0 del Plan 261**. Se documenta acá para que no se pierda.

---

## 9. Resumen de archivos nuevos

**Backend (2 módulos, 7 tests):**
- `backend/services/pipeline_env_declare.py`
- `backend/services/ci_env_gate.py` (incluye `to_rules_provider`, `evaluar_gate_secretos` y los
  dos conjuntos bloqueantes)
- `backend/tests/test_plan260_env_gate_flags.py`
- `backend/tests/test_plan260_has_value_veraz.py`
- `backend/tests/test_plan260_declare_core.py`
- `backend/tests/test_plan260_declare_endpoint.py`
- `backend/tests/test_plan260_trigger_gate.py`
- `backend/tests/test_plan260_secret_commit_gate.py`
- `backend/tests/test_plan260_fingerprints.py` *(v2, F7)*
- **`backend/tests/plan260_corpus/declare_matrix.json`** *(v3, ADICIÓN 4 — es **dato**, no un
  `test_*.py`: **no** va al ratchet de `HARNESS_TEST_FILES`)*

**Frontend (2 modelos puros nuevos + 1 modelo existente que se toca, 3 tests):**
- `frontend/src/devops/pipelineDeclareModel.ts` + `__tests__/pipelineDeclareModel.test.ts`
- `frontend/src/devops/triggerGateModel.ts` + `__tests__/triggerGateModel.test.ts`
- **`frontend/src/devops/__tests__/pipelineEnvMatrixModel.plan260.test.ts`** *(v3, C1 — archivo
  de test NUEVO sobre el modelo del 251, que se MODIFICA; el `.test.ts` del 251 no se toca)*

**Archivos existentes que se MODIFICAN (ninguno se crea):** `backend/config.py`,
`backend/services/harness_flags.py`, `backend/services/harness_flags_help.py`,
`backend/tests/test_harness_flags.py`, `backend/tests/test_harness_flags_requires.py`,
`backend/scripts/run_harness_tests.sh` + `.ps1`, `backend/services/ado_variables.py`,
`backend/services/gitlab_variables.py`, `backend/services/ci_variables.py`,
`backend/services/pipeline_env_resolver.py`, `backend/services/pipeline_environments.py`,
`backend/services/pipeline_diff.py` *(v2, C3)*, `backend/services/ci_run_ledger.py`,
`backend/api/pipeline_environments.py`, `backend/api/ci.py`, `backend/api/pipeline_generator.py`,
`frontend/src/components/devops/PipelineEnvMatrixPanel.tsx`,
`frontend/src/components/devops/VariablesSection.tsx`,
`frontend/src/components/PipelineTriggerCard.tsx`, `frontend/src/api/endpoints.ts`,
**`frontend/src/devops/pipelineEnvMatrixModel.ts`** *(v3, C1)*,
`Stacky Agents/docs/sistema/error_fingerprints.json` *(v2, F7)*.

**Total de tests nuevos esperados: 79 backend + 12 frontend** (v2: 66 + 8; v1: 52 + 6). El
crecimiento del v3 es casi todo **parametrización sobre el corpus de §4.6**, no funciones nuevas
escritas a mano: 4 filas x 3 fases + los 8 controles de los bloqueantes.

---

## 10. **(v2, C11 — NUEVO) Frontera de merge con los planes hermanos 263, 264 y 265**

Los cuatro planes de esta camada editan **los mismos seis archivos**. El gotcha real de este repo
es que **git hace 3-way merge SIN marcar conflicto cuando dos ramas agregan la misma línea de
cierre a una estructura existente**, dejando un duplicado silencioso que ni los marcadores ni el
compilador atrapan. Reglas de convivencia, obligatorias:

| Archivo compartido | Regla para el 260 |
|---|---|
| `backend/config.py` | Los 3 atributos van **contiguos, en un bloque propio, encabezado por el comentario literal `# Plan 260 — …`**, insertado **inmediatamente después** del bloque del Plan 251 (`:1461-1466`). Nunca intercalados entre atributos de otro plan |
| `backend/services/harness_flags.py` | Las 3 keys van **al final** de la tupla `_CATEGORY_KEYS["devops"]` (que hoy cierra en `:214`), en 3 líneas consecutivas con el sufijo `# Plan 260`. Los 3 `FlagSpec` van **contiguos, después** del del Plan 250 (`:3166`) |
| `backend/tests/test_harness_flags.py` | Las 2 keys ON van **al final** del conjunto `_CURATED_DEFAULTS_ON`, con su comentario `# ── Plan 260 …` propio, **después** del bloque del 252 (`:544-545`) |
| `backend/scripts/run_harness_tests.sh` y `.ps1` | Los 7 archivos van **al final** de la lista, en un bloque con el comentario `# Plan 260 …`, **después** del bloque del 252. Recordar que la sintaxis de los dos archivos **es distinta** (`.sh` sin comillas ni coma; `.ps1` con comillas y coma) |
| `frontend/src/api/endpoints.ts` | Los wrappers nuevos van **al final del objeto/namespace correspondiente**, agrupados bajo un comentario `// Plan 260`. Nunca reordenar ni reformatear lo existente |

**Colisiones concretas verificadas contra los hermanos:**

- **260 <-> 264:** ambos tocan `services/claude_code_cli_runner.py`, `services/llm_router.py`,
  `services/model_catalog.py` y `api/agents.py`. **El 260, tal como quedó en v2, NO toca ninguno
  de los cuatro** (§9): todo ese eje se fue al Plan 261 (§7). **La colisión es nula por diseño**;
  si un implementador se ve editando uno de esos archivos "para el 260", está haciendo el 261.
- **260 <-> 263/265:** sin archivos en común más allá de los 6 compartidos de la tabla.
- **Ninguna flag del 260 colisiona en nombre** con las de 263/264/265.
- **(v3, C14) La camada creció: al 2026-07-27 existen además los planes 266, 267, 268 y 269.** No
  se re-auditó archivo por archivo contra ellos (sería scope creep de la crítica), y **no hace
  falta**: la regla de convivencia de la tabla de arriba (bloque propio, al final, con comentario
  `# Plan 260`) es la que evita el duplicado silencioso, **sin importar cuántos hermanos haya**.
  Lo que sí es obligatorio es correr el **gate de verificación de abajo** antes de commitear,
  porque es lo único que detecta el merge 3-way que agrega la misma línea dos veces.

**Si el 260 se mergea después de un hermano:** antes de commitear, correr
`.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py -q`
**por archivo** y `rg -c "STACKY_PIPELINE_ENV_DECLARE_ENABLED" backend/config.py backend/services/harness_flags.py`
⇒ **1 en cada uno**. Un 2 es el duplicado silencioso del merge 3-way.
