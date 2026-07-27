# Plan 260 — Ninguna pipeline corre a ciegas: nombres declarados, faltantes visibles y disparo bloqueado

> ## ESTADO: **PROPUESTO v1 — NO IMPLEMENTADO**
>
> Escrito el 2026-07-27 sobre la rama `feat/plan-217-migrador-mantis-gitlab` (HEAD `cd20f646`).
> Toda la evidencia de este documento fue leída del código de ese commit y, donde dice
> **MEDIDO**, ejecutada de verdad con `backend/.venv/Scripts/python.exe` (py3.13.5).
>
> Siguiente eslabón del pipeline de la casa: `criticar-y-mejorar-plan`.

---

## 0. Frontera de superficie — enmienda declarada al §3.2 del Plan 251

El Plan 251 declaró, textualmente y por escrito, *"SOLO LECTURA: no escribe en el repo, ni en
el proveedor, ni en el servidor"* (`backend/config.py:1461-1462`), y su panel lo repite como
decisión de diseño (`frontend/src/components/devops/PipelineEnvMatrixPanel.tsx:22-25`:
*"acá no hay una segunda superficie de escritura"*).

**Este plan enmienda esa frontera de forma explícita y acotada**, y no en silencio:

- La escritura **no** vive en el módulo del 251. `services/pipeline_environments.py` sigue PURO
  y su `test_f1_modulo_puro` sigue válido.
- La única escritura nueva pasa por el **puerto ya existente del Plan 94**
  (`VARIABLES_PORT_METHODS = ("list_variables", "set_variable", "delete_variable")`,
  `services/ci_variables.py:63`), detrás de una flag **default OFF** y con `confirm=True`.
- Lo que se escribe es **un nombre con valor vacío**. Nunca un valor, nunca un secreto,
  nunca un placeholder que parezca un valor real.

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
| **KPI-5** | Valores de variables que salen por una respuesta HTTP o un log | **0** (control negativo explícito en F1 y F3) |

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
| Reglas de secretos en YAML | `services/pipeline_lint.py:703` (PL012), `:731` (PL013), `:749` (PL014); `services/cicd_security_rules.py:110` (SEC001) | **Completas** |
| Auditor determinista | `services/cicd_audit_core.py:251` `audit_yaml(yaml_text, *, provider, profile, mode, pipeline_key, suppressions)` | **Completo** |

**No hay que construir ni un motor.** Todo el material es puro, determinista y está probado.
Lo que falta son tres cables y una verdad.

### 2.2 Los tres huecos, con archivo:línea

**Hueco A — nadie declara los nombres.** `grep set_variable` sobre `api/` + `services/` da **un
solo** call-site: `api/devops_variables.py:82`, el alta manual de a una. Y la UI **exige** valor:
`frontend/src/components/devops/VariablesSection.tsx:71`
`const canSubmit = !!key.trim() && !keyError && !!value;` ⇒ desde la UI es **imposible** declarar
un nombre sin valor. El CTA "Completar" de la matriz solo navega
(`PipelineEnvMatrixPanel.tsx:80` `irAVariables = () => ctx.setActiveSection?.("variables")`) y
**no lleva el nombre**: el operador tiene que volver a tipearlo.

**Hueco B — el disparo no mira nada.** `api/ci.py:75-130` `trigger_pipeline_route`: flag (`:82`),
`confirm=True` (`:88`), `normalize_ref` (`:93`), `validate_trigger_credentials` (`:100`, y
`_read_pat_scopes` **siempre devuelve `None`** — `api/ci.py:60-68` — así que nunca bloquea) e
idempotencia (`:106`). **Ni una línea consulta variables, matriz de entornos ni preflight.**
`services/ci_preflight.py:22` `PREFLIGHT_PORT_METHODS = ("lint_yaml", "list_runners")`: el puerto
de preflight **no tiene** método de variables. `services/ci_trigger_rules.py` son 3 funciones
puras sobre scopes/ref/idempotencia, ninguna sobre valores.

**Hueco C — los dos caminos que escriben YAML no corren las reglas de secretos.**
`api/pipeline_generator.py:52-89` `commit_route` valida `confirm=True` (`:59`) y `spec.validate()`
(`:63`) y commitea en `:76-81`: **cero lint, cero audit**. El editor NL sí tiene gate duro
(`api/pipeline_editor.py:256-262`, `422 gates_en_rojo`) pero ese gate corre `check_semantics`
(RS001-009/GL, `services/cicd_semantic_rules.py:510`) — **las reglas SEC/PL no están en ese
camino**. `grep audit_yaml` da un único consumidor: `api/pipeline_audit.py:49`, un endpoint bajo
demanda que no es gate de nada.

### 2.3 La trampa central del plan, **MEDIDA** (no argumentada)

Ambos proveedores **hardcodean** `has_value: True`:

- `services/ado_variables.py:41` → `"has_value": True,  # Si está en la definition, tiene valor`
- `services/gitlab_variables.py:38` → `"has_value": True,  # Si está en la lista, tiene valor`

Y `resolve()` **ni siquiera mira ese campo**: `services/pipeline_env_resolver.py:106-109` arma
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

### 2.4 Lo NO verificado (declarado, para que el juez lo ataque)

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

---

## 3. Principios y guardarraíles (NO negociables)

### 3.1 El valor nunca sale, ni siquiera por un booleano de más
Este plan hace `has_value` **verdadero**, y eso es exactamente `bool(value)` — un bit. Está
permitido porque el campo **ya existe y ya promete eso**. Lo que sigue prohibido, con control
negativo en F1 y F3: que el `value` entre a un retorno, a un payload JSON, a un log o a un
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
  van a crear, antes de crear ninguno.
- Disparar con faltantes: **no se autocompleta nada**. El operador puede seguir adelante, pero
  solo con un `acknowledge_missing=True` explícito, que queda en la bitácora.
- El gate **nunca bloquea por ignorancia**: sin evidencia positiva de faltantes, advierte.

### 3.5 Núcleo determinista, sin LLM ⇒ paridad de runtimes trivial
Nada de este plan llama a un modelo. Los 3 runtimes (Codex, Claude Code, GitHub Copilot Pro) se
comportan idéntico porque no hay nada que dependa de un modelo. **Impacto por runtime: ninguno.**

### 3.6 Multiproveedor sin denominador común falso
ADO y GitLab **no** son simétricos y el plan no finge que lo sean:

| | ADO | GitLab |
|---|---|---|
| Distingue vacío de cargado (no-secreto) | sí (el GET trae `value`) | sí (el GET trae `value`) |
| Distingue vacío de cargado (secreto) | **no** (`value: null`) ⇒ `has_value=None` | sí |
| Acepta declarar una key vacía enmascarada | sí (`isSecret` es un bit aparte) | **no**: `masked=true` con valor vacío lo rechaza el proveedor (`gitlab_variables.py:83-90`) |

⇒ **En GitLab se declara SIEMPRE con `secret=False`**, y la nota le dice al operador que marque
`masked` al cargar el valor. Fingir lo contrario haría fallar el `POST` y el plan mentiría.

### 3.7 No degradar / backward-compatible
- `CELL_STATES` (`pipeline_environments.py:23`) **no se toca**: un nombre declarado sin valor es
  `falta`, un estado que ya existe. `build_matrix` acepta cualquier `(state, source, note)` que
  venga en `resolutions` (`:495-500`) y `pending_count` cuenta `state == "falta"` (`:514`), así
  que **no hace falta ni una línea nueva en `build_matrix`**.
- `SOURCES` (`:24`) **sí** crece en un elemento (`"declarada_sin_valor"`), al final, aditivo.
- `VARIABLES_PORT_METHODS` (`ci_variables.py:63`) **no se toca**.
- `list_variables()` conserva sus claves; `has_value` cambia de literal `True` a
  `True|False|None`. Baselines a respetar: `test_plan94_variables_providers.py` **13 passed**,
  `test_plan94_variables_endpoints.py` **14 passed**, `test_plan94_variables_pure.py` **3 passed**
  (**MEDIDOS hoy**).

### 3.8 Mono-operador
Sin roles, sin permisos. `current_user` es un header sin validar. Nada de este plan asume que
alguien "no puede" hacer algo por quién es.

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
por ignorancia) pero entra en `pending_fingerprint` (`:467` cuenta `falta` **y** `manual`), así
que el operador lo ve.

### 4.2 Plan de declaración (F2) — puro, sin I/O

```python
# services/pipeline_env_declare.py   (módulo NUEVO — el 251 queda intacto)
@dataclass(frozen=True)
class DeclareItem:
    key: str            # nombre a crear en el proveedor
    secret: bool        # ADO: is_secret del requirement. GitLab: SIEMPRE False (§3.6)
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

def evaluate_readiness(matrix, *, source: str) -> Readiness: ...
```

| Situación | `verdict` | Efecto en `POST /trigger` |
|---|---|---|
| `pending_count > 0` | `bloquea` | **409** salvo `acknowledge_missing=True` |
| `pending_count == 0` y `unknown_count > 0` | `advierte` | deja pasar, lo dice en la respuesta |
| `pending_count == 0` y `unknown_count == 0` | `ok` | deja pasar |
| No se pudo obtener el YAML | `degradado` | deja pasar, lo dice en la respuesta |

---

## 5. Fases

> **Corte declarado:** 7 fases (F0..F6). Todo lo que tenga que ver con **generar** una pipeline
> desde lenguaje natural, elegir modelo/effort o arreglar el intérprete NL queda **fuera** y va al
> Plan 261 (§7). Este plan no toca `api/pipeline_editor.py:346` `interpret_edit`.

---

### F0 — Tres flags, en sus **7 patas**

**Objetivo:** las tres flags existen, tienen el default correcto, son editables por UI y no
ponen rojo ningún meta-test.

| Flag | Default | `requires` | Por qué |
|---|---|---|---|
| `STACKY_PIPELINE_ENV_DECLARE_ENABLED` | **OFF** | `STACKY_DEVOPS_PANEL_ENABLED` | **Excepción dura:** es la única ruta NUEVA que escribe en un sistema externo real del operador (su ADO/GitLab). Misma categoría que `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` (`config.py:1477`) |
| `STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED` | **ON** | `STACKY_PIPELINE_TRIGGER_ENABLED` | Solo lee. No escribe, no quema tokens ociosos, no llama a un modelo. Bloquea **solo** con evidencia positiva |
| `STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED` | **ON** | `STACKY_DEVOPS_PANEL_ENABLED` | Un gate que solo puede **impedir** una fuga. Apagarlo es la decisión rara, no encenderlo |

**Las 7 patas:**

1. **`backend/config.py`** — los tres atributos, con el patrón exacto del archivo, junto a
   `STACKY_PIPELINE_ENV_MATRIX_ENABLED` (`:1464`) y `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`
   (`:1478`).
   **Gotcha dura:** el consumidor lee **la instancia** (`getattr(_config.config, KEY, False)`).
   `getattr` del **módulo** devuelve el default y mata el branch OFF: falso verde perfecto.
2. **`backend/services/harness_flags.py`** — dos ediciones:
   - las 3 keys en `_CATEGORY_KEYS["devops"]`, después de `:212`;
   - 3 `FlagSpec` junto a los de `:3124` (251) y `:3167` (250).
   **Gotcha `requires` (R4, profundidad 1):** **prohibido** poner
   `requires="STACKY_PIPELINE_ENV_MATRIX_ENABLED"`, porque esa flag **ya** declara
   `requires="STACKY_DEVOPS_PANEL_ENABLED"` (`test_harness_flags_requires.py:308`) y encadenar
   rompe `validate_requires_graph`. El master legal de raíz es `STACKY_DEVOPS_PANEL_ENABLED`.
   **Gotcha default-OFF:** `STACKY_PIPELINE_ENV_DECLARE_ENABLED` **NO debe declarar
   `default=False`** en su `FlagSpec`. Declararlo pone `default_is_known` en `True` y rompe
   `test_default_known_only_for_curated`. Se omite el kwarg y se registra en la lista de
   excepciones duras (`test_harness_flags.py:485` y el comentario de `:539`).
3. **`backend/services/harness_flags_help.py`** — 3 `PlainHelp`, junto a `:721` y `:733`.
   **Gotcha:** el texto llano tiene tope de **240 caracteres** y hay un ratchet que castiga
   ciertas palabras en la prosa. Si el gate salta, **se reescribe el texto, jamás el gate**.
4. **`backend/tests/test_harness_flags.py`** — las **dos** flags ON van a `_CURATED_DEFAULTS_ON`
   (`:543`); la OFF va a la lista de excepciones duras (`:485`). Sin esto,
   `test_default_known_only_for_curated` queda rojo.
5. **`backend/tests/test_harness_flags_requires.py`** — 3 aristas nuevas en
   `_REQUIRES_MAP_FROZEN`, junto a `:296-308`. Sin esto `test_requires_map_is_frozen` queda rojo
   **en silencio**.
6. **`backend/scripts/run_harness_tests.sh`** — los **6** archivos de test nuevos en
   `HARNESS_TEST_FILES` (`:20`), al FINAL, con la sintaxis del `.sh` (sin comillas, sin coma;
   patrón `:821-825`).
7. **`backend/scripts/run_harness_tests.ps1`** — los mismos 6 en `$HarnessTestFiles` (`:13`), al
   FINAL, con la sintaxis de PowerShell (**con** comillas y coma; patrón `:734-738`).
   **El meta-test NO mira el `.ps1`**: olvidarlo no da rojo y el runner que corre el operador en
   Windows deja de cubrir 6 archivos en silencio.

**NO tocar `backend/harness_defaults.env`** (está congelado, y su generador vive en
`deployment/`).

**Tests PRIMERO** — `backend/tests/test_plan260_env_gate_flags.py`:
- `test_f0_tres_flags_en_registry`
- `test_f0_tres_flags_en_categoria_devops`
- `test_f0_defaults` — las 2 ON en `_CURATED_DEFAULTS_ON` con `spec.default is True`; la OFF
  **sin** `default` declarado.
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
⇒ **6 en cada uno**.

---

### F1 — La verdad sobre `has_value` (va PRIMERA, y por eso)

**Objetivo:** que el sistema pueda distinguir "la variable existe" de "la variable tiene valor".
**Sin esto, F3 construye un falso verde** (§2.3, MEDIDO).

**Archivos:**

1. `services/ado_variables.py:25-46` `list_variables` — `has_value` deja de ser el literal `True`:
   ```python
   # ADO no devuelve el value de un secreto (isSecret=true -> value: null) => None = DESCONOCIDO.
   # Para una variable normal, ausencia de la clave "value" tambien es DESCONOCIDO, no False.
   has_value = None if is_secret or "value" not in var_def else bool(var_def.get("value"))
   ```
   `list_variables_scoped` (`:47`) hereda por construcción (hace `{**v, ...}`).
2. `services/gitlab_variables.py:22-45` y `:46-60` — GitLab **sí** devuelve `value` en el listado:
   `has_value = bool(v.get("value"))` si la clave viene; `None` si no.
   **Prohibido** guardar, loguear o retornar `v["value"]`: solo se consume el `bool()`.
3. `services/ci_variables.py` — documentar el tri-estado en el docstring del puerto.
   `VARIABLES_PORT_METHODS` (`:63`) **no se toca**.
4. `services/pipeline_env_resolver.py:105-109` — `por_key` pasa a guardar
   `(environment_scope, has_value)`; `_resolver_celda:137-148` aplica la tabla de §4.1.
5. `services/pipeline_environments.py:24` — `SOURCES` gana `"declarada_sin_valor"` **al final**.

**Tests PRIMERO** — `backend/tests/test_plan260_has_value_veraz.py`:
- `test_f1_ado_secreto_es_desconocido` — `isSecret: true` ⇒ `has_value is None`.
- `test_f1_ado_valor_vacio_es_false` — `{"value": "", "isSecret": false}` ⇒ `has_value is False`.
- `test_f1_ado_sin_clave_value_es_none` — degradación honesta (§2.4 punto 1).
- `test_f1_gitlab_valor_vacio_es_false` y `test_f1_gitlab_con_valor_es_true`.
- **`test_f1_ningun_value_sale_del_provider` (CONTROL NEGATIVO, KPI-5):** se inyecta
  `{"key":"K","value":"Xk7#pQ2mZr9Lw4Tv"}` y se asserta que esa cadena **no aparece** en
  `repr(list_variables())` ni en `repr(list_variables_scoped())`.
- **`test_f1_declarada_sin_valor_sigue_contando_como_falta` (KPI-2, el test que da vuelta la
  medición de §2.3):** con `has_value=False`, la celda queda `("falta","declarada_sin_valor")` y
  `build_matrix(...).pending_count == 1`.
- `test_f1_desconocido_cae_en_manual_no_en_definido`.
- `test_f1_sources_solo_crecio` — `SOURCES[:7]` es byte-idéntica a la tupla anterior.

**Criterio BINARIO:** los 8 propios verdes **y** las baselines **medidas hoy** intactas:
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
  **Gotcha recurrido 6 veces en esta casa:** el gate se escribe con `\bprint\(`, no con `print(`,
  porque un símbolo legítimo puede contener la subcadena. **El test verifica su propio gate.**
- `test_f2_solo_declara_lo_que_falta` — celdas `definido`/`default`/`manual` no generan `DeclareItem`.
- `test_f2_salta_server_deploy_path_service_connection_parameter` — 4 casos, y cada uno aparece en
  `skipped` **con motivo**.
- `test_f2_key_invalida_va_a_skipped` — `$(SONAR_TOKEN)` (que es como llega un
  `service_connection`, §2.3) no se intenta crear jamás.
- `test_f2_gitlab_nunca_declara_secret_true` (§3.6) — con un requirement `is_secret=True` y
  provider GitLab, `item.secret is False` y la `note` dice que marque `masked` al cargar.
- `test_f2_ado_conserva_is_secret`.
- `test_f2_determinista` — dos llamadas dan tuplas idénticas.
- **`test_f2_ningun_placeholder` (§3.3)** — ningún `DeclareItem` lleva valor; el módulo **no
  contiene** las cadenas `CHANGEME`, `TODO`, `xxx`, `placeholder`.

**Criterio BINARIO:** los 8 verdes. Sin red: el archivo de test no importa `flask` ni `app`.

---

### F3 — Endpoint `/declare` con HITL y escritura por el puerto del 94

**Objetivo:** crear los nombres en el proveedor, con valor vacío, previa confirmación explícita.

**Archivo:** `api/pipeline_environments.py` (ya existe, guard per-request en `:33`).

```
POST /api/pipeline-environments/declare
  body: { yaml, provider, project, confirm: true, keys: [...] }   # keys OPCIONAL: subconjunto
  flag: STACKY_PIPELINE_ENV_DECLARE_ENABLED  (OFF -> 404, guard per-request)
  sin confirm=true -> 400 {"error": "confirm=True requerido (HITL)"}
  ->  200 { declared: [...], skipped: [...], failed: [...], pending_count_after }

POST /api/pipeline-environments/declare-preview      # mismo body sin confirm; NO escribe
  ->  200 { plan: DeclarePlan serializado }
```

- `declare-preview` corre bajo la flag de la **matriz** (`STACKY_PIPELINE_ENV_MATRIX_ENABLED`,
  ya ON): ver qué se declararía es solo lectura y no necesita la flag de escritura.
- La escritura llama `get_variables_provider(project).set_variable(key, "", secret)`
  (`ci_variables.py:66`), **una key por vez**, y **nunca aborta el lote**: una key que falla va a
  `failed` con mensaje sanitizado y el resto sigue.
- `keys` permite al operador declarar un subconjunto: intersección con el plan; una key que no
  esté en el plan se rechaza (**no** se crea lo que el operador tipeó de más).
- Idempotente: declarar dos veces no rompe (`set_variable` hace upsert en ambos proveedores).
  **Pero:** si la key ya tiene valor, `plan_declaration` no la incluye (su celda es `definido`)
  ⇒ **no se pisa un valor cargado**. Test dedicado.

**Tests PRIMERO** — `backend/tests/test_plan260_declare_endpoint.py`:
- `test_f3_flag_off_404` — leyendo `config.config`, no el módulo.
- `test_f3_sin_confirm_400_y_no_escribe` — el doble de `set_variable` registra **0 llamadas**.
- `test_f3_preview_no_escribe` — 0 llamadas, y funciona con la flag de declare en OFF.
- `test_f3_declara_con_valor_vacio` — cada llamada capturada tiene `value == ""`.
- **`test_f3_nunca_pisa_una_variable_con_valor`** — key ya cargada ⇒ 0 llamadas para esa key.
- `test_f3_una_falla_no_aborta_el_lote` — 3 keys, la 2ª lanza `TrackerApiError`; el resultado
  tiene 2 en `declared` y 1 en `failed`.
- `test_f3_mensaje_de_error_sanitizado` — una excepción desconocida **no** propaga `str(e)`.
- **`test_f3_ningun_valor_en_la_respuesta` (CONTROL NEGATIVO, KPI-5)** — se inyecta un valor
  cargado y esa cadena no aparece en el cuerpo de la respuesta.
- **`test_f3_pending_count_no_baja_al_declarar` (KPI-2, el corazón del plan)** — se declara y se
  re-analiza; `pending_count_after == pending_count_antes`. **Este es el test que, si se cae,
  significa que el plan reintrodujo el bug de §2.3.**
- `test_f3_keys_fuera_del_plan_se_rechazan`

**Criterio BINARIO:** los 10 verdes **y** `test_plan251_env_matrix_endpoints.py` en su baseline
**medida hoy: 16 passed**.

---

### F4 — El gate antes de disparar

**Objetivo:** que `POST /api/ci/<project>/trigger` no dispare a ciegas.

**Archivo NUEVO:** `services/ci_env_gate.py` — `evaluate_readiness` (contrato en §4.3), PURO.

**Resolución del YAML** (en orden, primera que acierta; ninguna hace red saliente nueva):
1. `body["yaml"]` explícito — es lo que manda la UI (F6), que ya lo tiene.
2. `yaml_path` de la entrada del inventario del Plan 246 (`services/pipeline_inventory.py:511`
   `scan_repo_pipelines`), leído del workspace **local**. Import **blando**: si no se puede
   mapear `ref`→archivo, se salta (§2.4 punto 3).
3. Ninguna ⇒ `verdict = "degradado"`. **No bloquea.**

**Cableado en `api/ci.py`:**
- `trigger_pipeline_route` (`:75`) — el chequeo va **después** de `confirm` (`:88`) y **antes** de
  la idempotencia (`:105`), para no consumir la ventana de 60 s con un disparo que se va a
  rechazar:
  ```python
  if getattr(_config.config, "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED", False):
      readiness = _evaluar_readiness(project, body, ref_value)   # nunca lanza
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
  `verdict="degradado"`: **el gate jamás puede romper un disparo por un bug propio.**
- `trigger_preview_route` (`:156`) gana la misma `readiness` en su payload, para que el modal HITL
  lo muestre **antes** de confirmar. Ahí es puramente informativo.
- Cuando se dispara con `acknowledge_missing=True`, el `append_run` del ledger (`api/ci.py:136`)
  suma `"env_ack": True` y `"pending_fingerprint"`. **`ENTRY_FIELDS` de los ledgers JSONL de esta
  casa descarta campos no declarados EN SILENCIO** ⇒ hay que agregar las dos claves a la allowlist
  de `services/ci_run_ledger.py`, o el campo se pierde sin error.

**Tests PRIMERO** — `backend/tests/test_plan260_trigger_gate.py`:
- `test_f4_evaluate_readiness_puro` — sin red, sin I/O.
- `test_f4_bloquea_con_faltantes` — 409, `kind == "env_pending"`, y el provider **no** recibió
  `trigger_pipeline` (0 llamadas).
- `test_f4_ack_explicito_deja_pasar` — con `acknowledge_missing=True` dispara.
- `test_f4_sin_faltantes_dispara` — no cambia el comportamiento actual.
- **`test_f4_sin_yaml_no_bloquea`** (§3.4: nunca bloquear por ignorancia) — `degradado`, dispara,
  y la respuesta lo dice.
- **`test_f4_desconocido_advierte_pero_no_bloquea`** — `unknown_count > 0`, `pending_count == 0`.
- **`test_f4_una_excepcion_del_gate_no_rompe_el_trigger`** — se hace lanzar a
  `extract_requirements` y el disparo igual sale.
- `test_f4_flag_off_no_cambia_nada` — leyendo `config.config`.
- `test_f4_el_gate_corre_antes_de_la_idempotencia` — un disparo bloqueado no consume la ventana:
  el siguiente intento con ack **dispara de verdad**, no devuelve `reused`.
- **`test_f4_ningun_valor_en_el_409`** (KPI-5) — `missing` trae solo nombres.
- `test_f4_ledger_conserva_env_ack` — la clave sobrevive a `ENTRY_FIELDS`.
- `test_f4_preview_trae_readiness`

**Criterio BINARIO:** los 12 verdes **y** las baselines **medidas hoy**:
`test_plan72_trigger_endpoint.py` **11 passed**, `test_plan191_ci_ledger_hook.py` **8 passed**.

> **Flaky conocido de esta casa:** todo test que toque la DB bajo pytest con shared-cache puede
> dar `database table is locked`. Estos archivos se corren **8 veces cada uno** antes de
> declararlos verdes, y se usa el helper de reintento del Plan 253 donde aplique.

---

### F5 — Ningún camino escribe un YAML con un secreto literal

**Objetivo:** cerrar el KPI-4. Hoy los **dos** caminos de escritura commitean sin correr SEC/PL.

**Archivos:**
1. `api/pipeline_generator.py:52` `commit_route` — antes de `writer.commit_file` (`:77`):
   ```python
   if getattr(_config.config, "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED", False):
       rep = audit_yaml(yaml_str, provider=("azure_devops" if target == "ado" else "gitlab"))
       duros = [f for f in rep.findings if f.code in _SECRET_BLOCKING and f.severity == "error"]
       if duros:
           return jsonify({"error": "el YAML contiene un secreto literal",
                           "kind": "secret_in_yaml",
                           "findings": [{"code": f.code, "location": f.location,
                                         "message": f.message} for f in duros]}), 422
   ```
2. `api/pipeline_editor.py:256` — el gate existente (`422 gates_en_rojo`) suma las reglas SEC/PL
   al conjunto que evalúa. **Aditivo:** las reglas RS/GL actuales siguen igual.
3. Conjunto **cerrado** de reglas bloqueantes, declarado en un solo lugar:
   `_SECRET_BLOCKING = ("SEC001", "PL012", "PL014")`.
   - **`PL013` NO bloquea**: dice "el secreto no está en la caja fuerte", que es exactamente lo
     que este plan viene a resolver y **degrada a `unknown` cuando `known_variables is None`**
     (`pipeline_lint.py:736`). Bloquear con PL013 volvería incommiteable media pipeline legítima.

**Gotcha dura (recurrida en esta casa):** el enmascarado corre **después** del gate, nunca antes.
Si se pasa el YAML por `mask_token_values` y recién ahí se audita, SEC001 no encuentra nada y el
gate **falla abierto** — verde perfecto y fuga real.

**Tests PRIMERO** — `backend/tests/test_plan260_secret_commit_gate.py`:
- `test_f5_generator_rechaza_secreto_literal` — 422, `kind == "secret_in_yaml"`, y
  `commit_file` recibió **0 llamadas**.
- `test_f5_generator_deja_pasar_yaml_limpio` — el camino feliz no se rompió.
- `test_f5_editor_rechaza_secreto_literal`
- **`test_f5_pl013_no_bloquea`** (control negativo: un gate que bloquea de más es inservible).
- **`test_f5_el_gate_corre_antes_del_masking`** — se audita el texto crudo; con el orden invertido
  el test se cae.
- **`test_f5_el_mensaje_de_error_no_trae_el_secreto`** (KPI-5) — el 422 trae `code` + `location`,
  y el valor inyectado **no** aparece en el cuerpo.
- `test_f5_flag_off_no_bloquea` — leyendo `config.config`.
- `test_f5_conjunto_bloqueante_es_cerrado` — `_SECRET_BLOCKING` es una tupla congelada y el test
  la enumera literal (si alguien agrega una regla, este test lo obliga a pensarlo).

**Criterio BINARIO:** los 8 verdes **y** `test_plan248_api.py` en su baseline **medida hoy:
7 passed**.

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
   `resumenDeclaracion(plan)` → *"Stacky va a crear N nombres; vos solo pegás los valores"*;
   `agruparSkipped(plan)` → motivo → keys.
2. **NUEVO** `frontend/src/devops/triggerGateModel.ts` — puro:
   `mensajeDeBloqueo(readiness)` → *"No podés disparar: faltan N valores (X, Y, Z)"*;
   `puedeDisparar(readiness, ack)`.
3. `frontend/src/components/devops/PipelineEnvMatrixPanel.tsx` — botón **"Declarar los nombres"**
   → `declare-preview` → lista exacta de qué se va a crear → `confirm` → `declare`. Visible solo
   con `STACKY_PIPELINE_ENV_DECLARE_ENABLED` (las flags de UI se leen de `/api/diag/health`).
   El CTA "Completar" (`:80-88`) pasa a llevar la key preseleccionada a la sección de variables.
4. `frontend/src/components/devops/VariablesSection.tsx:71` — `canSubmit` deja de exigir `value`
   **solo** cuando el alta viene de una declaración (`modo="declarar"`). El alta manual sigue
   exigiendo valor: no se degrada el formulario existente.
5. `frontend/src/components/PipelineTriggerCard.tsx:111-134` — el modal HITL muestra la
   `readiness` del `trigger-preview`; con `bloquea` el botón de confirmar queda deshabilitado y
   aparece un checkbox explícito *"Entiendo que faltan valores y quiero disparar igual"* que
   habilita `acknowledge_missing`.
6. `frontend/src/api/endpoints.ts` — wrappers de `/declare`, `/declare-preview` y del nuevo campo
   del preview.
   **Gotcha dura:** `api.get`/`api.post` **lanzan excepción** en non-2xx. El 409 del gate y el 422
   del F5 traen cuerpo útil ⇒ hay que usar `rawPost`/`rawGet` o el detalle se pierde y el operador
   ve un error genérico.

**Tests PRIMERO** — `frontend/src/devops/__tests__/pipelineDeclareModel.test.ts` y
`triggerGateModel.test.ts`:
- `test_f6_resumen_dice_cuantos_nombres`
- `test_f6_skipped_agrupado_por_motivo`
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

**Criterio BINARIO:** los 6 verdes, `npx tsc --noEmit` en **0 errores**, y los 8 ratchets del
frontend sin crecer (medir el baseline **antes** de tocar nada: hay rojos **ajenos** conocidos —
`formDebtRatchet` y `devopsPollingRatchet` por `BuildWorkshopSection.tsx:93`. Un rojo ajeno se
prueba con un **worktree en el commit base**, no se argumenta).

**Pendiente declarado (no automatizable):** smoke visual — abrir DevOps → *Matriz de entornos*,
pegar una pipeline real, apretar *Declarar los nombres*, confirmar que la alerta **sigue diciendo
"te faltan N"**, cargar un valor, ver bajar el contador, e intentar disparar con y sin faltantes.

---

## 6. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Declarar apaga la alerta** (§2.3, MEDIDO) | F1 va antes que F3; `test_f3_pending_count_no_baja_al_declarar` es el criterio binario del plan |
| R2 | El gate bloquea disparos legítimos por un falso positivo de detección | Bloquea **solo** con `state == "falta"`; `manual`/desconocido **advierte**. `acknowledge_missing` siempre disponible. Flag apagable por UI |
| R3 | Un bug del gate deja al operador sin poder disparar nada | `try/except` que degrada a `degradado`; test dedicado (`test_f4_una_excepcion_del_gate_no_rompe_el_trigger`) |
| R4 | Fuga de un valor por el nuevo `has_value` o por el 409 | 3 controles negativos con un password real que **no** es un token conocido (los prefijos canónicos no lo atrapan — lección medida del Plan 251) |
| R5 | GitLab rechaza la declaración de un secreto | §3.6: en GitLab se declara **siempre** `secret=False`; test dedicado |
| R6 | Se pisa una variable que ya tenía valor | `plan_declaration` no incluye celdas `definido`; `test_f3_nunca_pisa_una_variable_con_valor` |
| R7 | El gate SEC bloquea de más y vuelve incommiteable una pipeline legítima | Conjunto **cerrado** de 3 reglas; PL013 explícitamente excluido con test |
| R8 | `test_plan251_env_matrix_resolve.py` se pone rojo porque congelaba el bug | Se corrige el test, **no** se corrige el plan para complacerlo; el desvío se documenta |
| R9 | Flakiness de SQLite bajo pytest | Correr **por archivo**, 8 veces, con el helper de reintento del 253 |

---

## 7. Fuera de alcance — va al Plan **261**

Este plan **no** toca el eje "generar una pipeline desde lenguaje natural con un agente de Claude
Code eligiendo modelo y effort". Ese eje está **ausente** hoy y necesita su propio plan:

- **No existe** un camino "texto libre → PipelineSpec nueva". El único NL que existe
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

**Backend (3 módulos, 6 tests):**
- `backend/services/pipeline_env_declare.py`
- `backend/services/ci_env_gate.py`
- `backend/tests/test_plan260_env_gate_flags.py`
- `backend/tests/test_plan260_has_value_veraz.py`
- `backend/tests/test_plan260_declare_core.py`
- `backend/tests/test_plan260_declare_endpoint.py`
- `backend/tests/test_plan260_trigger_gate.py`
- `backend/tests/test_plan260_secret_commit_gate.py`

**Frontend (2 modelos puros, 2 tests):**
- `frontend/src/devops/pipelineDeclareModel.ts` + `__tests__/pipelineDeclareModel.test.ts`
- `frontend/src/devops/triggerGateModel.ts` + `__tests__/triggerGateModel.test.ts`

**Total de tests nuevos esperados: 52 backend + 6 frontend.**
