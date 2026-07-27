# Plan 260 — Ninguna pipeline corre a ciegas: nombres declarados, faltantes visibles y disparo bloqueado

> ## ESTADO: **CRITICADO v1 -> v2 — NO IMPLEMENTADO**
>
> Escrito el 2026-07-27 sobre la rama `feat/plan-217-migrador-mantis-gitlab` (HEAD `cd20f646`).
> Criticado adversarialmente el 2026-07-27 sobre `83d3b8e0`. Toda la evidencia de este documento
> fue leída del código de esos commits y, donde dice **MEDIDO**, ejecutada de verdad con
> `backend/.venv/Scripts/python.exe` (py3.13.5).
>
> Siguiente eslabón del pipeline de la casa: `implementar-plan-stacky`.

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
| **KPI-2** | Declarar los nombres **no** apaga la alerta de faltantes | `pending_count` **no baja** al declarar (hoy baja a 0 — **MEDIDO**, §2.3) |
| **KPI-3** | Disparos de pipeline con valores obligatorios sin cargar | **0** con evidencia positiva de faltantes; **advertencia** cuando Stacky no puede saberlo |
| **KPI-4** | Caminos de escritura de YAML que commitean un secreto literal | **0** de 2 (hoy **2** de 2 — §2.2) |
| **KPI-5** | Valores de variables que salen por una respuesta HTTP o un log | **0** (control negativo explícito en F1, F3 y F5) |
| **KPI-6** *(v2, C1)* | Códigos declarados bloqueantes que el motor invocado **no puede producir** | **0** (probado regla por regla con su `repro`) |
| **KPI-7** *(v2, C4)* | Milisegundos que el gate agrega al camino del botón de disparo | **<= 1500 ms**; excedido ⇒ `degradado`, nunca bloqueo |

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
| **`repro` obligatorio por regla** *(v2, ADICIÓN 1)* | `services/cicd_audit_core.py:106-115`: sin `repro=(provider, yaml_minimo)` la regla **no se registra** | **Completo — es la palanca anti-inerte** |

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
`por_key` solo con `key` + `environment_scope`, y `_resolver_celda:140-145` devuelve
`("definido", "caja_fuerte", None)` por la **mera presencia de la key**.

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
   código lo asume (`ado_variables.py:53-79` hace GET y mutila el dict), pero no se ejecutó contra
   un ADO real. F1 debe degradar a `None` (desconocido) si el campo no viene, **nunca** asumir.
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
   body). Lo único verificado es que **existe un reintento** ante un 400 (`:96-112`). ⇒ F3 **no
   decide de antemano**: manda `secret=True` y deja que el reintento ya probado decida, leyendo
   el `masked` que `set_variable` devuelve en `:123-127`.

---

## 3. Principios y guardarraíles (NO negociables)

### 3.1 El valor nunca sale, ni siquiera por un booleano de más
Este plan hace `has_value` **verdadero**, y eso es exactamente `bool(value)` — un bit. Está
permitido porque el campo **ya existe y ya promete eso**. Lo que sigue prohibido, con control
negativo en F1, F3 y F5: que el `value` entre a un retorno, a un payload JSON, a un log o a un
mensaje de excepción. Se conserva `_mensaje_seguro` (`pipeline_env_resolver.py:63-76`): prohibido
`str(e)` de una excepción desconocida.

### 3.2 Declarar un nombre no es cargar un valor, y el sistema nunca los confunde
Un nombre declarado con valor vacío es **una variable que sigue faltando**. Estado de celda:
`falta`. `pending_count` **no baja**. La única diferencia visible es el `source`, que pasa a
decir por qué: `declarada_sin_valor`.

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
- `SOURCES` (`:24-25`) **sí** crece en un elemento (`"declarada_sin_valor"`), al final, aditivo.
  La tupla actual tiene **7** elementos: el control de regresión es `SOURCES[:7]` byte-idéntica.
- `VARIABLES_PORT_METHODS` (`ci_variables.py:63`) **no se toca**.
- `list_variables()` conserva sus claves; `has_value` cambia de literal `True` a
  `True|False|None`. Baselines a respetar: `test_plan94_variables_providers.py` **13 passed**,
  `test_plan94_variables_endpoints.py` **14 passed**, `test_plan94_variables_pure.py` **3 passed**
  (**MEDIDOS hoy**).
- **(v2, C7)** `trigger_preview_route` sigue siendo un **GET** y sigue devolviendo todo lo que
  devuelve hoy. El campo `readiness` es **aditivo y opcional**: sin `yaml_path` en la query, el
  payload es byte-idéntico al actual salvo `readiness: {"verdict": "degradado", ...}`.
- **(v2, C10)** `ENTRY_FIELDS` (`services/ci_run_ledger.py:30-34`) crece en 2 claves **al final**.
  Consecuencia declarada: **todas** las filas del ledger (incluso las que no vienen de este plan)
  pasan a llevar `env_ack: null` y `pending_fingerprint: null`, porque `_project_entry` (`:74`)
  proyecta el conjunto completo. Es aditivo y `schema_version` **no** se bumpea (el 258 lo
  reservó para cambios de forma, no de allowlist).

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

Regla de resolución en `_resolver_celda` (F1):

| `has_value` | Celda |
|---|---|
| `True` | `("definido", "caja_fuerte" \| "scope_proveedor", None)` — como hoy |
| `False` | `("falta", "declarada_sin_valor", "el nombre existe en el proveedor pero no tiene valor")` |
| `None` | `("manual", "caja_fuerte", "el proveedor no informa si este secreto tiene valor: verificalo vos")` |

`None` cae en `manual`, no en `definido` ni en `falta`: no bloquea el disparo (§3.4, no bloquear
por ignorancia) pero entra en `pending_fingerprint` (`pipeline_environments.py:464-468` cuenta
`falta` **y** `manual`), así que el operador lo ve.

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

@dataclass(frozen=True)
class Readiness:
    verdict: str
    pending_count: int          # celdas 'falta'
    unknown_count: int          # celdas 'manual'
    pending_fingerprint: str
    missing: tuple              # tuple[(name, environment)] — SOLO nombres, jamas valores
    reasons: tuple
    resolved: bool              # (v2, C4) True SOLO si se consulto al proveedor de verdad

def evaluate_readiness(matrix, *, source: str, resolved: bool) -> Readiness: ...
```

| Situación | `verdict` | Efecto en `POST /trigger` |
|---|---|---|
| **`resolved is False`** *(v2, C4)* | `degradado` | deja pasar, lo dice en la respuesta. **Se evalúa PRIMERO: sin resolución no hay bloqueo posible** |
| `pending_count > 0` | `bloquea` | **409** salvo `acknowledge_missing=True` |
| `pending_count == 0` y `unknown_count > 0` | `advierte` | deja pasar, lo dice en la respuesta |
| `pending_count == 0` y `unknown_count == 0` | `ok` | deja pasar |
| No se pudo obtener el YAML | `degradado` | deja pasar, lo dice en la respuesta |

### 4.4 **(v2, C2 — NUEVO)** Los dos vocabularios de proveedor que conviven en el repo

Este plan cruza dos subsistemas que nombran al mismo proveedor de forma distinta. **Confundirlos
apaga reglas en silencio** (falla abierto). Tabla congelada:

| Subsistema | Archivo que lo define | ADO | GitLab |
|---|---|---|---|
| Matriz de entornos / declaración (F1-F4) | `services/pipeline_environments.py:28-30` `PROVIDER_ADO` | `"azure_devops"` | `"gitlab"` |
| Auditor + linter + reglas semánticas (F5) | `api/pipeline_audit.py:22` `_PROVIDERS`; `pipeline_lint.py:70` `_rule(..., providers=("ado","gitlab"))`; `cicd_security_rules.py:471,474,477` `if provider == "ado"` | **`"ado"`** | `"gitlab"` |
| Body de `commit_route` (F5) | `api/pipeline_generator.py:65-70` `body["target"]` | **`"ado"`** | `"gitlab"` |

**Reglas de uso, literales:**

1. En F5 el proveedor que se le pasa a `audit_yaml` y a `lint_yaml` es **`target` tal cual**,
   sin traducir. Escribir `"azure_devops"` ahí es un bug: SEC003/SEC005/SEC007 y las reglas
   `providers=("ado", ...)` dejan de aplicar y el gate **deja pasar** lo que debía frenar.
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
   - presupuesto duro: 1500 ms  (KPI-7)
   - cualquier excepcion, timeout o proveedor no configurado -> resolved=False -> 'degradado'
4. build_matrix(...) -> evaluate_readiness(matrix, source=..., resolved=True)
```

**Reglas duras:**

- **`resolved=False` NUNCA bloquea.** Es el corolario de §3.4. Sin este candado, una matriz sin
  resolver devuelve `falta` en todas las celdas (`_nota_por_kind`,
  `pipeline_environments.py:479`) y una flag **default ON** frenaría **todos** los disparos del
  operador desde el primer deploy. Este es el modo de fallo más caro del plan.
- **El presupuesto de 1500 ms es del gate entero, no por request al proveedor.** Se mide con
  `time.monotonic()` alrededor del paso 3 y se compara **después**: no se cancela el request en
  vuelo (no hay cancelación segura acá), se **descarta el resultado tardío** y se degrada. El
  request queda huérfano y no pasa nada: era un GET de solo lectura.
- **El gate no hace ninguna llamada de red que el panel de la matriz no haga ya.** Es el mismo
  `resolve()` que `/analyze` ejecuta cuando el operador abre la matriz.

#### **[ADICIÓN ARQUITECTO 2] — reuso del veredicto por `pending_fingerprint`**

El disparo real casi siempre viene precedido del preview (el modal HITL lo pide). Calcular la
readiness dos veces es pagar dos veces la latencia por la misma verdad. Y ya existe en `api/ci.py`
una ventana de 60 s con su almacén en memoria: la de idempotencia (`_recent_triggers`,
`should_trigger(..., window_seconds=60)`, `:105-106`).

**Se reusa esa misma ventana**, con un almacén hermano y explícito:

```python
# api/ci.py — memoria de veredictos (misma ventana de 60 s que la idempotencia)
# clave: (provider_name, ref_value)  ->  (Readiness, ts_monotonic)
# NO es un cache de datos del proveedor: es el resultado ya calculado del gate.
_RECENT_READINESS: dict = {}
```

- `trigger-preview` **escribe** el veredicto.
- `trigger` **lo reusa** si: misma `(provider, ref)`, antigüedad < 60 s, **y** el `yaml_sha256`
  con el que se calculó coincide con el del disparo. Cualquier diferencia ⇒ se recalcula.
- Si no hay entrada, se calcula normalmente (nada depende del preview).

**Por qué es seguro:** el `pending_fingerprint` ya existe y ya es el identificador canónico del
"trabajo pendiente" (`pipeline_environments.py:464-468`). Si el operador cargó un valor entre el
preview y el disparo, cambia el fingerprint del proveedor, pero el veredicto reusado sería el
**viejo (más restrictivo o igual)**: en el peor caso el operador ve un 409 que ya no corresponde,
aprieta de nuevo y a los 60 s se recalcula. **Nunca al revés** (nunca deja pasar algo que el
cálculo fresco hubiera frenado)… salvo que el operador **borre** un valor en 60 s, caso en que el
disparo pasa: se declara como riesgo aceptado R12 y se documenta en la respuesta con
`readiness.source == "preview_reusado"`.

- Test obligatorio: `test_f4_veredicto_reusado_declara_su_origen` y
  `test_f4_yaml_distinto_no_reusa_el_veredicto`.

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
5. `services/pipeline_environments.py:24-25` — `SOURCES` gana `"declarada_sin_valor"` **al final**.

**Tests PRIMERO** — `backend/tests/test_plan260_has_value_veraz.py`:
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
- `test_f1_sources_solo_crecio` — `SOURCES[:7]` es byte-idéntica a la tupla anterior.

**Criterio BINARIO:** los 9 propios verdes **y** las baselines **medidas hoy** intactas:
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
            pending_count_after }

POST /api/pipeline-environments/declare-preview      # mismo body sin confirm; NO escribe
  guard: _guard()   (solo la flag de la matriz: ver que se declararia es SOLO LECTURA)
  ->  200 { plan: DeclarePlan serializado,
            pending_count_actual, pending_count_proyectado }   # (v2, ADICION 3)
```

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

`declare-preview` devuelve **`pending_count_actual` y `pending_count_proyectado`**, calculados con
el mismo núcleo puro: se toma la matriz, se marcan las keys del plan como
`has_value=False` y se vuelve a `build_matrix`. Con F1 correcto, **los dos números son iguales**.

Por qué vale: el KPI-2 del plan es contraintuitivo ("declaro y la alerta no baja") y el operador
podría leerlo como que la función no hizo nada. Mostrar los dos números **antes** de escribir
convierte una sorpresa en una decisión informada, y además es un **canario en producción**: si
alguna vez `pending_count_proyectado < pending_count_actual`, el bug de §2.3 volvió y el operador
lo ve en la pantalla antes que cualquier test.

- Test: `test_f3_preview_proyecta_el_mismo_pending_count`.

**Tests PRIMERO** — `backend/tests/test_plan260_declare_endpoint.py`:
- `test_f3_flag_off_404` — leyendo `config.config`, no el módulo.
- **`test_f3_flag_declare_off_pero_matriz_on_da_404` (v2, C5)** — con
  `STACKY_PIPELINE_ENV_MATRIX_ENABLED=True` y `STACKY_PIPELINE_ENV_DECLARE_ENABLED=False`,
  `/declare` da **404** y el doble de `set_variable` registra **0 llamadas**. **Este test es el
  que prueba que la excepción dura de la flag existe en el código y no solo en el papel.**
- `test_f3_sin_confirm_400_y_no_escribe` — 0 llamadas.
- `test_f3_preview_no_escribe` — 0 llamadas, y funciona con la flag de declare en OFF.
- `test_f3_preview_proyecta_el_mismo_pending_count` *(ADICIÓN 3)*.
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
- **`test_f3_pending_count_no_baja_al_declarar` (KPI-2, el corazón del plan)** — se declara y se
  re-analiza; `pending_count_after == pending_count_antes`. **Este es el test que, si se cae,
  significa que el plan reintrodujo el bug de §2.3.**
- `test_f3_keys_fuera_del_plan_se_rechazan_con_400`

**Criterio BINARIO:** los 13 verdes **y** `test_plan251_env_matrix_endpoints.py` en su baseline
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
  casa descarta campos no declarados EN SILENCIO** (`services/ci_run_ledger.py:30-34`, proyección
  en `:74`) ⇒ hay que agregar las dos claves **al final** de esa tupla, o el campo se pierde sin
  error. Ver §3.7 para la consecuencia declarada sobre las filas existentes.

**Tests PRIMERO** — `backend/tests/test_plan260_trigger_gate.py`:
- `test_f4_evaluate_readiness_puro` — sin red, sin I/O.
- `test_f4_bloquea_con_faltantes` — 409, `kind == "env_pending"`, y el provider **no** recibió
  `trigger_pipeline` (0 llamadas).
- `test_f4_ack_explicito_deja_pasar` — con `acknowledge_missing=True` dispara.
- `test_f4_sin_faltantes_dispara` — no cambia el comportamiento actual.
- **`test_f4_sin_yaml_no_bloquea`** (§3.4: nunca bloquear por ignorancia) — `degradado`, dispara,
  y la respuesta lo dice.
- **`test_f4_sin_resolver_no_bloquea_aunque_todo_sea_falta` (v2, C4 — el test más importante de
  la fase)** — se arma una matriz **sin resolver** (todas las celdas `falta` por
  `_nota_por_kind`) y se pasa `resolved=False`: el verdict es `degradado` y el disparo **sale**.
  Si este test se cae, la flag default ON frena todos los disparos del operador.
- **`test_f4_timeout_de_resolucion_degrada` (v2, KPI-7)** — el doble de `resolve` tarda más que el
  presupuesto ⇒ `degradado`, dispara.
- **`test_f4_desconocido_advierte_pero_no_bloquea`** — `unknown_count > 0`, `pending_count == 0`.
- **`test_f4_una_excepcion_del_gate_no_rompe_el_trigger`** — se hace lanzar a
  `extract_requirements` y el disparo igual sale.
- `test_f4_flag_off_no_cambia_nada` — leyendo `config.config`.
- `test_f4_el_gate_corre_antes_de_la_idempotencia` — un disparo bloqueado no consume la ventana:
  el siguiente intento con ack **dispara de verdad**, no devuelve `reused`.
- **`test_f4_ningun_valor_en_el_409`** (KPI-5) — `missing` trae solo nombres.
- `test_f4_ledger_conserva_env_ack` — la clave sobrevive a `ENTRY_FIELDS`.
- `test_f4_preview_trae_readiness` — **(v2)** con `?yaml_path=` resuelto, y con el caso sin
  `yaml_path` dando `degradado`. Sin los dos casos el test no prueba nada (C7).
- **`test_f4_veredicto_reusado_declara_su_origen`** *(ADICIÓN 2)* — el preview calcula, el trigger
  reusa, y la respuesta trae `readiness.source == "preview_reusado"`.
- **`test_f4_yaml_distinto_no_reusa_el_veredicto`** *(ADICIÓN 2)* — otro `yaml_sha256` ⇒ recalcula.

**Criterio BINARIO:** los 16 verdes **y** las baselines **medidas hoy**:
`test_plan72_trigger_endpoint.py` **11 passed**, `test_plan191_ci_ledger_hook.py` **8 passed**,
**y (v2, C10) los dos archivos que congelan `ENTRY_FIELDS`:**
`test_plan202_ledger.py` (asserta `set(item.keys()) == set(L.ENTRY_FIELDS)` en `:48` y `:64`) y
`test_plan258_ledger_veracidad.py` (`:155-158` exige `env`/`schema_version`; `:395` asserta la
línea literal de la proyección). Correrlos **en su baseline previa a tocar nada** y compararlos.

> **Flaky conocido de esta casa:** todo test que toque la DB bajo pytest con shared-cache puede
> dar `database table is locked`. Estos archivos se corren **8 veces cada uno** antes de
> declararlos verdes, y se usa el helper de reintento del Plan 253 donde aplique.

---

### F5 — Ningún camino escribe un YAML con un secreto literal — **REESCRITA (v2: C1, C2, C3, C9)**

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
_SECRET_BLOCKING_AUDIT = ("SEC001",)

# Motor: services.pipeline_lint.lint_yaml  (PL001..PL014)
# OJO: son SEV_WARNING. Se filtra POR CODIGO, jamas por severidad: filtrar por
# severity=="error" las descarta a las tres y el gate queda inerte (bug del plan v1).
_SECRET_BLOCKING_LINT = ("PL012", "PL014")
```

- **`PL013` NO bloquea**: dice "el secreto no está en la caja fuerte", que es exactamente lo
  que este plan viene a resolver y **degrada a `unknown` cuando `known_variables is None`**
  (`pipeline_lint.py:736`). Bloquear con PL013 volvería incommiteable media pipeline legítima.

#### 5.2 Camino 1 — `api/pipeline_generator.py:52` `commit_route` (el hueco literal)

Antes de `writer.commit_file` (`:77`):

```python
if getattr(_config.config, "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED", False):
    from services.ci_env_gate import evaluar_gate_secretos   # noqa: PLC0415
    duros, auditado = evaluar_gate_secretos(yaml_str, provider=target)   # (v2, C2) target TAL CUAL
    if not auditado:                                                     # (v2, C9)
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
    `auditado` es False cuando el YAML no se pudo analizar (>512 KB o no-dict):
    en ese caso NO se commitea, porque un gate que no vio nada no es un gate verde.
    """
```

- **(v2, C2)** `provider=target`, **identidad**. `body["target"]` ya vale `"ado"` | `"gitlab"`
  (`api/pipeline_generator.py:65-70`), que es exactamente el vocabulario de las reglas (§4.4).
  Escribir `"azure_devops"` apaga SEC003/SEC005/SEC007 en silencio.
- **(v2, C9)** `audit_yaml` devuelve `ok=True` con `findings=()` si el YAML supera 512 KB
  (`cicd_audit_core.py:258-259`) o no es un dict (`:265-267`). Eso es "no analicé", no "está
  limpio". El gate distingue los dos casos con `auditado`.

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

**Fix, en `services/pipeline_diff.py`, aditivo y mínimo:**

```python
# services/pipeline_diff.py — dentro de review_patch, junto al gate G-LINT actual
from services.ci_env_gate import _SECRET_BLOCKING_LINT  # o la constante re-exportada

_fuga = tuple(f for f in nuevos if f.code in _SECRET_BLOCKING_LINT)
gates.append(GateDelta(
    gate=GATE_SECRET, passed=not _fuga, new_errors=_fuga,
    new_warnings=(), resolved=()))
```

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
- El gate nuevo se gatea con `STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED`: con la flag OFF,
  `_fuga` se fuerza a `()` y `passed=True`.

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
    """KPI-6. Para CADA codigo de los dos conjuntos, existe un YAML que lo produce
    en el motor que el gate realmente invoca. Un codigo que no dispara es codigo
    muerto en un gate de seguridad: peor que no tenerlo, porque parece que protege."""
    from services.cicd_audit_core import AUDIT_RULES
    for code in _SECRET_BLOCKING_AUDIT:
        assert code in AUDIT_RULES, "%s no existe en el motor de audit" % code
        prov, yaml_min = AUDIT_RULES[code].repro
        rep = audit_yaml(yaml_min, provider=prov)
        assert any(f.code == code for f in rep.findings), \
            "%s esta declarado bloqueante pero su propio repro no lo dispara" % code
    for code in _SECRET_BLOCKING_LINT:
        prov, yaml_min = _REPRO_LINT[code]      # fixture local: el linter no expone repro
        rep = lint_yaml(yaml_min, prov)
        assert any(f.code == code for f in rep.findings), \
            "%s esta declarado bloqueante pero lint_yaml no lo produce" % code
```

**Con este test escrito PRIMERO, el diseño del v1 se cae en F5 antes de escribir el endpoint**:
`audit_yaml` nunca produce PL012/PL014 y el assert lo dice con el mensaje exacto. Es el test que
convierte un falso verde estructural en un rojo temprano, y su costo es de una sola función.

`_REPRO_LINT` es un dict de 2 entradas en el propio archivo de test (el linter, a diferencia del
auditor, no exige `repro` por contrato). Se documenta como deuda del linter, no se arregla acá.

**Tests PRIMERO** — `backend/tests/test_plan260_secret_commit_gate.py`:
- **`test_f5_cada_codigo_bloqueante_dispara_de_verdad`** *(ADICIÓN 1, KPI-6)*.
- **`test_f5_vocabulario_de_provider`** *(v2, C2)* — el string que llega a `audit_yaml` está en
  `api.pipeline_audit._PROVIDERS`; `"azure_devops"` hace fallar el test.
- `test_f5_generator_rechaza_secreto_literal` — 422, `kind == "secret_in_yaml"`, y
  `commit_file` recibió **0 llamadas**.
- `test_f5_generator_deja_pasar_yaml_limpio` — el camino feliz no se rompió.
- **`test_f5_yaml_no_auditable_no_se_commitea`** *(v2, C9)* — YAML > 512 KB y YAML no-dict ⇒
  `422 secret_gate_indeterminado`, 0 llamadas a `commit_file`.
- `test_f5_editor_rechaza_secreto_literal` — vía `review_patch`, gate `GATE_SECRET`.
- **`test_f5_editor_gate_lint_intacto`** *(v2, C3)* — el `GateDelta` de `GATE_LINT` es idéntico al
  de antes del cambio para un caso sin fuga (backward-compatible).
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

**Criterio BINARIO:** los 12 verdes **y** las baselines **medidas hoy**: `test_plan248_api.py`
**7 passed**, **más (v2, C3)** los del editor y el diff, que ahora se tocan de verdad:
`test_plan250_flag.py` y `test_plan250_edit_intent.py` en su baseline previa.

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

**Tests PRIMERO** — `frontend/src/devops/__tests__/pipelineDeclareModel.test.ts` y
`triggerGateModel.test.ts`:
- `test_f6_resumen_dice_cuantos_nombres`
- `test_f6_skipped_agrupado_por_motivo`
- **`test_f6_aviso_contador_no_baja`** *(ADICIÓN 3)*
- **`test_f6_aviso_masking_lista_las_keys`** *(v2, C6)*
- `test_f6_mensaje_de_bloqueo_lista_nombres_no_valores`
- `test_f6_puede_disparar_solo_con_ack`
- `test_f6_degradado_no_bloquea_el_boton`
- `test_f6_advierte_muestra_aviso_pero_habilita`

**Comandos:**
```powershell
npx vitest run src/devops/__tests__/pipelineDeclareModel.test.ts
npx vitest run src/devops/__tests__/triggerGateModel.test.ts
npx tsc --noEmit
```
**Correr por archivo:** la corrida completa de vitest contamina cross-file en este repo.

**Criterio BINARIO:** los 8 verdes, `npx tsc --noEmit` en **0 errores**, y los 8 ratchets del
frontend sin crecer (medir el baseline **antes** de tocar nada: hay rojos **ajenos** conocidos —
`formDebtRatchet` y `devopsPollingRatchet` por `BuildWorkshopSection.tsx:93`. Un rojo ajeno se
prueba con un **worktree en el commit base**, no se argumenta).

**Pendiente declarado (no automatizable):** smoke visual — abrir DevOps -> *Matriz de entornos*,
pegar una pipeline real, apretar *Declarar los nombres*, confirmar que la alerta **sigue diciendo
"te faltan N"**, cargar un valor, ver bajar el contador, e intentar disparar con y sin faltantes.

---

### F7 — **(v2, C14) Huella de regresión**

**Objetivo:** que los dos falsos verdes que este plan corrige queden registrados como huella, para
que el próximo que los reintroduzca los vea nombrados.

**Archivo:** `Stacky Agents/docs/sistema/error_fingerprints.json` — dos entradas **al final**, en
el formato que ya usa el archivo (leerlo antes de escribir; **no** inventar campos):

1. **`declarar_apaga_la_alerta`** — síntoma: `pending_count` cae a 0 después de declarar nombres
   sin valor. Causa: `has_value` hardcodeado a `True` en los proveedores + `_resolver_celda`
   resolviendo por mera presencia de la key. Test que lo cubre:
   `test_plan260_declare_endpoint.py::test_f3_pending_count_no_baja_al_declarar`.
2. **`gate_de_secretos_inerte`** — síntoma: el gate de commit está ON, el YAML tiene un secreto
   literal y el commit pasa. Causa: código bloqueante declarado contra un motor que no lo produce,
   o filtro por severidad sobre reglas `SEV_WARNING`. Test que lo cubre:
   `test_plan260_secret_commit_gate.py::test_f5_cada_codigo_bloqueante_dispara_de_verdad`.

**Tests PRIMERO** — `backend/tests/test_plan260_fingerprints.py`:
- `test_f7_json_valido_y_solo_crecio` — el archivo parsea y las entradas previas son idénticas.
- `test_f7_las_dos_huellas_apuntan_a_un_test_que_existe` — el `test` de cada huella se resuelve a
  un archivo y un nombre de función que existen de verdad (si no, la huella es decorativa).

**Criterio BINARIO:** los 2 verdes y el archivo parseable con `json.loads`.

---

## 6. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Declarar apaga la alerta** (§2.3, MEDIDO) | F1 va antes que F3; `test_f3_pending_count_no_baja_al_declarar` es el criterio binario del plan; ADICIÓN 3 lo hace visible en producción |
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

> **(v2) Nota de numeración:** al momento de la crítica, los planes **261 y 262 no tienen
> documento** y el rango con documento de esta camada es **260, 263, 264, 265**. La reserva del
> 261 de este plan sigue en pie; el 262 queda libre.

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

**Frontend (2 modelos puros, 2 tests):**
- `frontend/src/devops/pipelineDeclareModel.ts` + `__tests__/pipelineDeclareModel.test.ts`
- `frontend/src/devops/triggerGateModel.ts` + `__tests__/triggerGateModel.test.ts`

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
`Stacky Agents/docs/sistema/error_fingerprints.json` *(v2, F7)*.

**Total de tests nuevos esperados: 66 backend + 8 frontend** (v1: 52 + 6).

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

**Si el 260 se mergea después de un hermano:** antes de commitear, correr
`.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py -q`
**por archivo** y `rg -c "STACKY_PIPELINE_ENV_DECLARE_ENABLED" backend/config.py backend/services/harness_flags.py`
⇒ **1 en cada uno**. Un 2 es el duplicado silencioso del merge 3-way.
