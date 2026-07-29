# Plan 266 — Cero pantalla rota en el Comparador de BD: forma garantizada del `summary`

**Estado:** CRITICADO v4
**Fecha:** 2026-07-29 (v4) · 2026-07-28 (v3) · 2026-07-27 (v1, v2)
**Rama sugerida:** `feat/plan-266-summary-shape`
**Serie:** independiente (cierra una incidencia REAL reportada por el operador)

---

## 0. Changelog v3 → v4 (tercera pasada, juez INDEPENDIENTE que EJECUTÓ los gates)

Veredicto del v3: **RECHAZADO (5 BLOQUEANTES)**. Todo lo de abajo está aplicado.

Esta pasada no releyó el v3: **corrió** los gates, los greps, los conteos y los parsers, contra el
árbol en el commit `760ac455` (que ya incluye la costura P0 `05398601`). Los 5 bloqueantes salieron
de **ejecutar**, no de razonar, y **ninguno** lo había visto una crítica anterior. Tres de ellos son
gates que el propio plan rompe o que nacen rojos; uno es un gate que **no mide nada y sale verde**.

### Lo que la ejecución CONFIRMÓ como correcto (no se tocó)

Se re-midió con el criterio exacto del plan, no con el número del documento:

- **El censo de F4 es exacto:** las dos regex sobre `frontend/src/components/dbcompare/` devuelven
  **8 violaciones** en **57 archivos** censados, y **0** violaciones en el resto de `src/` (o sea
  que el alcance de una carpeta no deja nada afuera). KPI-1 y el umbral `>= 45` del test 12 quedan.
- **La huella de F6.4 es válida:** el bloque de código JSON se extrajo **del propio documento** y se
  pasó por `json.loads` → OK; `re.compile` → OK; los 2 `matches` dan `True`, los 2 `clean` dan
  `False`; `_REQUIRED` completo; `status` en el enum. El baseline del catálogo es **exactamente
  `3 failed, 5 passed`** y `test_patrones_compilan` está VERDE. C13 estaba bien resuelto.
- **La tabla de verdad de F1.5 es válida:** el bloque JSON parsea, 18 casos. Y las 4 clases de
  C16/C21 están confirmadas ejecutando: `Number("0x10")=16`, `Number("0b101")=5`,
  `Number("1_0")=NaN`, `Number("")=0`, `JSON.parse("1e400")=Infinity`.
- **C14 es correcto:** `undefined.danger` produce `Cannot read properties of undefined (reading
  'danger')` y la regex del plan lo matchea; `({})["danger"]` da `undefined` y el caso 4 **no lanza**.
- **La premisa de C12 es correcta:** el parser real de PowerShell sobre `@("x.py",\n"y.py",\n)` da
  `1 ParserError: Falta una expresión después de ','`. (Lo que está mal es el anclaje del fix: C23.)
- **Anclajes correctos, verificados abriendo el archivo:** todos los de `dbcompare_runs.py`
  (`:68` `_write_run`, `:109` `_read_run`, `:127` `_is_stale`, `:131`, `:265`, `:304`, `:316`
  `get_run`, `:326` `list_runs`, `:336` `meta`), y que **no** importa config (`:19-28`); todos los
  de `PageErrorBoundary.tsx` (`:12-16`, `:18-21`, `:24`, `:30-43`, `:32`, `:40`, `:47`, `:52`,
  `:55-72`, `:60`, `:61-63`, `:64-66`, `:67-69`); `config.py:203` (cierra
  `STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES`, punto de inserción limpio);
  `_CURATED_DEFAULTS_ON` en `test_harness_flags.py:467`; y el idiom de lectura de
  `dbcompare_masking.py:206-208` (import dentro de la función + `getattr(_config.config, …)`).
- **`STACKY_DB_COMPARE_ENABLED` existe, `default=True` y `requires is None`** ⇒ la profundidad 1
  (R4) se cumple: colgar la flag nueva de ella no forma cadena.
- **El intérprete `.venv\Scripts\python.exe` es el correcto** (py3.13; `venv` sin punto es py3.11) y
  es la convención de los 6 planes de la serie 259-271. No se cambia.
- **No hay 7ª pata.** `harness_defaults.env` solo se audita por *bounds*
  (`test_harness_flags_bounds.py:254`, que además hace `skip` si el archivo no está) y ningún test
  exige que cubra el registry. Para esta flag el cableado son **SEIS** lugares, ni más ni menos.

### Los 5 bloqueantes

- **C22 (BLOQUEANTE)** — **falta la SEXTA pata del cableado: `_REQUIRES_MAP_FROZEN`.** El plan
  declara `requires="STACKY_DB_COMPARE_ENABLED"` y su tabla de F3 lista **5** lugares; las cadenas
  `_REQUIRES_MAP_FROZEN` y `test_harness_flags_requires.py` aparecen **0 veces en 1972 líneas**.
  Pero `tests/test_harness_flags_requires.py:316` es `assert actual == _REQUIRES_MAP_FROZEN`,
  **igualdad de conjuntos** con reporte de `Extras` en `:318`. Medido hoy: el archivo está en
  **9 passed**, `len(actual) == len(FROZEN) == 146` y `actual == FROZEN → True`. Simulando el plan
  verbatim (agregar la arista sin tocar el mapa): `sim == FROZEN → False`,
  `Extras = ['STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED']`, `AssertionError` reproducida. El plan
  **pone en rojo un gate que hoy está verde** → §F3 tabla (ahora 6 filas), §F3.5, §F6.3, §7.3, R15.
- **C23 (BLOQUEANTE)** — **F6.1(b) es inejecutable: el bloque que manda reemplazar NO existe.** El
  v3 dicta *"Reemplazar el bloque `  "tests/test_plan258_estanqueidad_arnes.py"` + `)`"* y
  *"agregarle una coma al final de la línea del 258, que hoy no la tiene"*. Medido sobre el archivo
  real: `Contains(...)` → **False**. La línea del 258 está en **`:787`** y **ya termina en coma**
  (`-match '…py",'` → **True**); la última entrada es **`:796`
  `"tests/test_plan242_runtime_parity.py"`** (sin coma) y el `)` está en **`:797`** (el plan dice
  `:788`). O sea que la "regla general" del v3 —*la que era última recibe la coma que le faltaba*—
  es falsa en las dos mitades. Un implementador literal no encuentra el bloque, la edición no pasa,
  y el test nuevo **nunca entra al arnés en silencio**; o improvisa, que es justo lo que §1
  prohíbe. Ahora la instrucción está re-anclada a la última entrada real y es **una sola línea
  nueva sin coma** (verificado con el parser: parsea OK) → §F6.1(b), R12.
- **C24 (BLOQUEANTE)** — **F6.5 test 2 nace ROJO con 206 violaciones, y sobre una premisa falsa de
  PowerShell.** El v3 pide que "ninguna línea de entrada del `.ps1` que no sea la última del array
  venga sin coma". Medido: **207** líneas de entrada **no** llevan coma y solo **1** es la última
  del array (`:796`) ⇒ **206 violaciones el día 1**. Y la premisa es falsa: el parser real acepta
  `@("x.py"\n"y.py")` **sin ninguna coma** (0 errores), igual que acepta el archivo real completo
  con sus 207 entradas desnudas. PowerShell **no** exige coma entre elementos separados por salto
  de línea. La afirmación del v3 "las entradas intermedias van entrecomilladas y con coma" es falsa
  para 206 de 623. El test 2 codificaba una regla que no existe → **se elimina** y se explica por
  qué; el test 1 (coma colgante) **se conserva** porque su premisa sí está confirmada → §F6.5.
- **C25 (BLOQUEANTE)** — **F5.2 rompe el `copyDebtRatchet`, y el plan no lo corre.** Existe
  `frontend/src/__tests__/copyDebtRatchet.test.ts` (Plan 194 F5) que congela **por archivo** la
  cantidad de escrituras directas al portapapeles (`/\.writeText\s*\(/`) bajo `src/`, y declara en
  su encabezado: *"El único lugar legítimo de escritura al portapapeles es services/copyService"*.
  Medido: el ratchet está **VERDE hoy (3 passed)**; el baseline `copyByFile` tiene 11 entradas y
  `components/PageErrorBoundary.tsx` **NO figura** ⇒ su cupo es **0**. El `handleCopy` del v3
  escribe `navigator.clipboard?.writeText(` **en ese archivo** ⇒ deuda nueva sobre cupo 0 ⇒ **ROJO**.
  Y ni F5.2 ni F6.3 corren ese ratchet (corren `uiDebtRatchet`), así que el plan no se enteraba.
  Regenerar el baseline no es opción (solo baja). El fix es **reusar el módulo canónico**
  `services/copyService.copyText()` —verificado: no está detrás de ninguna flag, devuelve
  `CopyResult` y trae fallback a `execCommand` para contexto no-seguro, más las constantes
  `COPY_TOAST_SUCCESS`/`COPY_TOAST_ERROR`—, que además es estrictamente mejor que la llamada cruda
  → §F5.1, §F5.2, §F6.3, §7.3, R16.
- **C26 (BLOQUEANTE)** — **el único gate del plan para la entrada nueva de `PLAIN_HELP` es un falso
  verde perfecto.** F3 dice: *"Para validar solo la entrada nueva:
  `pytest tests/test_harness_flags_help.py -q -k SUMMARY_SHAPE`"*. Ejecutado:
  **`8 deselected in 0.19s`, exit code `0`**. Los 8 tests se llaman `test_plain_help_*`; ninguno
  contiene `SUMMARY_SHAPE`, así que `-k` **deselecciona todo, corre CERO tests y sale 0**: parece
  verde y no mide nada. Es exactamente el patrón que esta casa prohíbe (precedente del plan 270: 15
  casos que también pasaban con la implementación prohibida). Además el archivo está en **4 failed /
  4 passed** ajenos, así que "esperar verde" es insatisfacible. El criterio pasa a ser **delta sobre
  el contrato real**: correr el archivo completo y exigir que el conteo siga en 4 y que **ninguna**
  violación mencione la key nueva → §F3, §F6.3, §7.3, R17.
  (El **contenido** de la entrada sí se verificó ejecutando el contrato completo —son **SEIS**
  reglas, no solo longitudes— y pasa las seis: `what`=132≤200, `on_effect`=109≤240,
  `off_effect`=122≤240, `example`=166≤300, los dos empiezan con `"Si "`, cero términos de
  `JARGON_DENYLIST`, cero keys `SCREAMING_SNAKE`, cero referencias `F<n>`. Lo roto era el gate, no
  el texto.)

### Los importantes y menores

- **C27 (IMPORTANTE)** — **categoría equivocada y contradicción dentro de la propia tabla de F3.**
  El v3 manda poner la key en `_CATEGORY_KEYS["capacidades_optin"]` y su test asserta
  `categorize(...) == "capacidades_optin"`. Medido: `capacidades_optin` (abre en `:415`) tiene
  **una sola** key de DB Compare —el master `STACKY_DB_COMPARE_ENABLED`—, mientras que
  `comparador_bd` (abre en `:454`) tiene **20**, incluida `STACKY_DB_COMPARE_MASKING_ENABLED` en
  `:464`; y `categorize("STACKY_DB_COMPARE_MASKING_ENABLED")` devuelve `comparador_bd`. La tabla se
  contradice sola: el ítem 2 dice "junto al `FlagSpec` de MASKING" (cuyo `group` es
  `comparador_bd`) y el ítem 3 la manda a otra categoría. Una flag que declara
  `requires=STACKY_DB_COMPARE_ENABLED` es por definición **hija** y va donde están sus 20 hermanas,
  o el operador la busca en la sección equivocada de la UI de flags → §F3 (categoría, `group=`, y
  la aserción del test).
- **C28 (IMPORTANTE)** — **anclajes derivados que el v3 declaró explícitamente "CONFIRMADOS".**
  Medido: el `FlagSpec` de `STACKY_DB_COMPARE_MASKING_ENABLED` está en **`:4255`**, no en
  `4196-4204` (ese rango es del Plan 157: `CONFIG_IN_PLACE` / `WEBCONFIG_IMPORT`). Y el par
  `default=True` ⇔ pertenencia al set lo verifican `test_declared_default_true_set` (**`:990`**) y
  `test_default_known_only_for_curated` (**`:1001`**), no `:965-983` (ese rango es
  `test_read_current_includes_category_and_default`). `_CATEGORY_KEYS` se define en **`:120`**.
  Corregidos, y con la regla de la casa escrita al lado: **el símbolo manda, el número es
  orientativo** → §F3, R6.
- **C29 (IMPORTANTE)** — **el CSS de F5 rompe el `uiDebtRatchet` y el plan solo prohíbe estilos
  inline.** Medido: el ratchet congela por archivo la cantidad de **colores hex** en `*.module.css`
  (`HEX_RE = /#[0-9a-fA-F]{3,8}\b/g`), y el baseline de
  `components/PageErrorBoundary.module.css` es **2** (los dos que ya tiene: `#fca5a5` y `#fecaca`).
  El v3 manda agregar 4 clases nuevas sin decir nada de color: **un solo hex nuevo lo pone en 3 y el
  gate en ROJO**. Además la familia de tokens `--color-*` **no existe** en el tema (los reales son
  `--accent`, `--danger`, `--success`, `--border`, `--text-primary`, `--bg-panel`), así que "usá
  tokens" a secas también es una trampa. Ahora las 4 clases van **literales**, con `rgba()` como el
  resto del archivo y **cero hex nuevo** → §F5.2, R18.
- **C30 (IMPORTANTE — DATOS PERSONALES)** — **el diagnóstico copiable no tiene cota ni declaración
  de egreso.** Este plan opera sobre un comparador de **bases de datos reales**, así que un mensaje
  de error puede arrastrar un valor de fila. Medido lo bueno: `services/activityCenter.ts` persiste
  en **`localStorage`** (`:35`) y **no hace ningún `fetch`/POST** ⇒ el `body` no sale del navegador;
  y `dbcompare_masking.apply_to_run_response` se aplica en `api/db_compare.py:447`, o sea **aguas
  abajo** de `get_run`, por lo que la normalización de F3 —que se inserta **dentro** de `get_run`—
  queda **antes** del enmascarado y **no lo anula** (no falla abierto). Eso hay que decirlo, no
  suponerlo. Lo que falta: `buildDiagnosticText` embute `message` + `componentStack` **sin cota** y
  el `body` queda en `localStorage` para siempre; y `dbcompare_masking.py` es del backend y
  pattern-based sobre el data-diff: **no puede ver** un crash de render del navegador, así que no
  cubre esto ni podría. Ahora hay cota explícita, tests que la fijan, y la declaración de egreso
  con su anclaje → §3.10, §F5.1, §F5.2, §6 ítem 10, R19.
- **C31 (MENOR)** — **los conteos del arnés están corridos en 7.** Medido hoy: el `.sh` tiene
  **687** entradas y el `.ps1` **623** (el v3 dice 680 y 616). Lo que sí se confirma es el
  invariante: `ps1 − sh = ∅` y `sh − ps1 = 64`. Los umbrales `>= 600` siguen válidos, pero un plan
  que presenta sus números como medidos no puede traerlos corridos → §F6.5, §6 ítem 8.
- **C32 (MENOR)** — el `FIXTURE_HISTORICO` de F4 se declara *"copia textual de las 8 líneas"* y no
  lo es: la línea real de `RunsTimeline.tsx:37` es
  `{run.summary.parity_score}% · 🔴{run.summary.by_severity.danger} 🟠` (con emojis y
  `parity_score`). El fixture **sí** produce las 8 detecciones (verificado línea por línea contra
  R1/R2), así que el test funciona; lo falso es la palabra "textual" → §F4.3.
- **C33 (MENOR)** — F6.5 test 1 se especifica en prosa ("para cada `)` que cierra un array"), que es
  una inferencia y §1 las prohíbe. Medido: hay **exactamente 1** línea que es solo `)` (`:797`), así
  que la implementación literal es trivial y nace verde. Ahora está dada en código → §F6.5.
- **[ADICIÓN ARQUITECTO] A4** — **F3.5 nueva: gate de cableado COMPLETO de la flag.** La causa raíz
  de C22 no es que alguien se olvidó de una fila: es que **la receta de 6 patas vive en una tabla de
  un documento** y el único que la verifica es el juez. F3.5 agrega un test que asserta las **seis**
  patas de esta flag en un solo lugar (atributo en `config.py`, `FlagSpec` con `default=True` +
  `requires`, `_CATEGORY_KEYS`, `_CURATED_DEFAULTS_ON`, `PLAIN_HELP`, y la arista en
  `_REQUIRES_MAP_FROZEN`). Cuesta ~30 líneas, es Python puro, y convierte en gate ejecutable la
  clase de error que hizo rechazar esta versión → §F3.5, KPI-7.
- **[ADICIÓN ARQUITECTO] A5** — **F6.3 pasa de "correr y esperar verde" a una TABLA DE BASELINE
  MEDIDO con criterio DELTA.** Cuatro de los archivos que el plan toca tienen rojos ajenos
  preexistentes (`test_harness_flags_help.py` 4, `test_error_fingerprints_catalog.py` 3) y otros
  cuatro están verdes y **el plan los puede romper** (`test_harness_flags_requires.py`,
  `copyDebtRatchet`, `uiDebtRatchet`, `test_harness_flags.py`). Pedir "verde" es insatisfacible y
  pedir "que pase" es inauditable. La tabla nueva trae, por archivo, el **número medido hoy** y el
  número exigido después → §F6.3.

---

## 0.1. Changelog v2 → v3 (segunda pasada, revisión INDEPENDIENTE)

La crítica que produjo el v2 se corrió en la **misma sesión** que la propuesta: eso no equivale a
revisión independiente (gotcha conocido de la casa). Esta segunda pasada re-verificó los anclajes
**abriendo los archivos reales y ejecutando los gates**, no leyéndolos del documento.

Veredicto del v2: **RECHAZADO (2 BLOQUEANTES)**. Todo lo de abajo está aplicado.

**Lo que la re-verificación CONFIRMÓ como correcto** (no se tocó): el censo de **8 violaciones**
es exacto —las dos regex de F4 corridas contra el árbol real devuelven exactamente esas 8 líneas
únicas—; los **57** archivos de `components/dbcompare/`; los anclajes de `dbcompare_runs.py`
(`:68`, `:109`, `:131`, `:265`, `:304`, `get_run` `:316-323`, `list_runs` `:326-340`, `meta` en
`:336`); los de `radarLogic.ts` (`:31`, `:56`, `:60`, `:104`), `svgMath.ts` (`:39`, `:40`, `:43`,
`:47`), `SummaryHero.tsx` (`:49-50`, `:65`, `:67`, `:145`, `:147`), `RunsTimeline.tsx`
(`:23`, `:35`, `:37`, `:38`) y `PageErrorBoundary.tsx` (`:12-16`, `:18-21`, `:24`, `:30-43`,
`:47`, `:52`, `:55-72`); que `dbcompare_runs.py` **no** importa config; que `_count` no existe;
que `STACKY_DB_COMPARE_ENABLED` existe (`requires=` válido); y los anclajes del motor de flags
(`harness_flags.py:4196-4205` / `:447`, `test_harness_flags.py:467`, `harness_flags_help.py:25`,
`config.py:203`).

- **C12 (BLOQUEANTE)** — **F6.1(b) rompía el arnés de PowerShell.** El v2 mandaba agregar
  `  "tests/test_plan266_summary_shape.py",` —**con coma final**— como **última** entrada antes
  del `)`. La última entrada real (`run_harness_tests.ps1`, `"tests/test_plan258_estanqueidad_arnes.py"`)
  **NO lleva coma**, y PowerShell **no admite coma colgante** en un literal de array: el archivo
  entero deja de parsear. Verificado ejecutando el parser real
  (`[System.Management.Automation.Language.Parser]::ParseInput`) sobre la forma exacta que dicta
  el v2 → `ParserError: Falta una expresión después de ','`. La ironía es que C3 reescribió esta
  fase justamente para dar "las dos líneas literales exactas" y la del `.ps1` es inejecutable.
  Ahora la instrucción es un **par de líneas** (coma que se AGREGA a la entrada del 258 + entrada
  nueva **sin** coma) → §F6.1(b).
- **C13 (BLOQUEANTE)** — **F6.4 ponía en rojo un gate que hoy está verde.** La entrada propuesta
  para `error_fingerprints.json` trae `"log_pattern": null` y **omite `self_test`**. Verificado
  contra `backend/tests/test_error_fingerprints_catalog.py`: `:48-50` hace
  `re.compile(fp["log_pattern"])` **sin guarda** ⇒ `re.compile(None)` lanza `TypeError`, y hoy
  **ninguna** de las 42 huellas tiene `log_pattern: null`, o sea que `test_patrones_compilan`
  **pasa hoy** y el plan lo rompería. Además `self_test` está en `_REQUIRED` (`:18`). Baseline
  ejecutado: `3 failed, 5 passed` — los 3 rojos (`campos_obligatorios`, `status_enum`,
  `self_test_coherente`) son **ajenos y preexistentes**, pero `patrones_compilan` **no**. Ahora la
  huella lleva un `log_pattern` compilable y su `self_test`, **conservando `log_guarded: false`**
  (la justificación del v2 era conceptualmente correcta), y el criterio de F6.4 pasa a **correr el
  test del catálogo** con los 3 rojos ajenos declarados → §F6.4.
- **C14 (IMPORTANTE)** — F0.1 afirmaba "los **4** primeros deben lanzar HOY". Falso: el caso 4
  (`by_severity = {}` → `severityCounters`) **no lanza** — `svgMath.ts:43` evalúa `{}["danger"]`,
  que es `undefined`, y el test falla por **aserción**, no por `throw`. Un implementador literal
  vería "no lanzó" y "arreglaría" el fixture. Ahora se declara 3-que-lanzan + 1-que-falla-por-
  aserción, y el criterio binario deja de ser "el texto del fallo" (ambiguo con varios fallos) y
  pasa a ser **por test nombrado** → §F0.1.
- **C15 (IMPORTANTE)** — F3 declaraba los topes de `PlainHelp` como "`what`/`on_effect`/
  `off_effect` ≤ 240". El tope real de `what` es **200** (`test_harness_flags_help.py:48`:
  `assert len(entry.what) <= 200`). El texto propuesto mide 132 y pasa, pero la **restricción
  escrita** es falsa y habilita a escribir 220 → rojo. Corregido, con las 4 longitudes medidas
  → §F3.
- **C16 (IMPORTANTE)** — la tabla de verdad de F1.5 se declara "la especificación ÚNICA" y **deja
  una clase de divergencia afuera**: los literales numéricos de JS en string. Medido ejecutando
  las dos implementaciones: `"0x10"` → `toCount` **16** / `_count` **0**; `"0b101"` → **5** / **0**.
  `Number()` entiende hex/binario/octal y `float()` no. Se agregan 3 casos y la regla explícita
  → §F1.5.1, KPI-6.
- **C17 (MENOR)** — F5.2 hablaba de "los **14** call-sites de `App.tsx`". Son **2**
  (`App.tsx:346` y `:495`; la tercera aparición es el `import` de `:33`). El fix —`surface?`
  opcional— no cambia; el número sí → §F5.2.
- **C18 (MENOR)** — F2 Edición 5 dicta `:147 → {sum.objects_unchanged} sin diferencias`, pero la
  línea real es `comparados — {summary.objects_unchanged} sin diferencias`. Aplicada al pie de la
  letra —que es lo que §1 exige— **borra el prefijo `comparados — `** de la UI. Ahora la
  instrucción da la línea completa → §F2.
- **C19 (MENOR)** — F3 citaba `dbcompare_masking.py:208` como "precedente **exacto** del idiom"
  para poner `import config as _config` **en el tope del archivo**. El precedente real
  (`dbcompare_masking.py:206`) hace ese import **dentro de la función**. El idiom que sí acredita
  es el de la LECTURA (`getattr(_config.config, …)`). Precisado, y declarado por qué el import de
  módulo es seguro acá (`config.py` no importa `services`: verificado, solo `logging`, `os`,
  `pathlib`, `dotenv`, `runtime_paths`) → §F3.
- **C21 (IMPORTANTE)** — divergencia **simétrica** de la de C16, encontrada al validar el propio
  fix de C16: `float("1_0")` en Python da **10.0** (admite guiones bajos) y `Number("1_0")` da
  **NaN**. O sea que las dos coerciones nativas se pasan de generosas **en direcciones opuestas**,
  y un guard puesto solo en el frontend —como salía el primer intento de fix— habría **cambiado
  de dirección** la divergencia en vez de matarla. La misma regex de decimales va en **los dos**
  normalizadores. Verificado corriendo las 18 filas contra las dos implementaciones: **18/18
  coinciden** → §F1.5.1, §F3, R14.
- **C20 (MENOR)** — el fixture de F1.5 traía 14 casos y el control anti-vaciado exigía `>= 13`:
  margen de **1**, el mismo error de calibración que C6 le marcó al v1 (12 vs 57). Con los casos
  de C16 y C21 el fixture queda en **18** y el umbral en **>= 17** → §F1.5, §7.3.
- **[ADICIÓN ARQUITECTO] A3** — **F6.5 nueva**: guard de las **dos listas del arnés**. El `.ps1`
  dice en su encabezado "Mantener en sync con run_harness_tests.sh" y **nadie lo verifica**: el
  meta-test parsea **solo el `.sh`** (`test_harness_ratchet_meta.py:13`), así que el `.ps1` no
  tiene **ningún** gate — ni de sincronización ni de **sintaxis**. Por eso C12 habría llegado a
  main en silencio. F6.5 agrega un test en Python puro (sin `pwsh`, corre igual en los 3 runtimes)
  que verifica: (a) **cero comas colgantes** antes del `)` —la clase exacta de C12—, (b)
  entradas del `.ps1` **⊆** entradas del `.sh` (invariante que **hoy se cumple**: medido,
  `ps1 − sh = ∅`, con 616 y 680 entradas respectivamente), y
  (c) que el archivo de este plan está en **los dos**. Nace **verde** → §F6.5.

---

## 0.2. Changelog v1 → v2

Crítica adversarial verificada contra el repo (2026-07-27). Veredicto del v1: **RECHAZADO
(3 BLOQUEANTES)**. Todo lo de abajo está aplicado en este documento.

- **C1 (BLOQUEANTE)** — `_count()` capturaba solo `(TypeError, ValueError)`, pero
  `int(float(float("inf")))` lanza **`OverflowError`**; como `json.loads` acepta
  `Infinity`/`-Infinity`/`NaN` por default, un run en disco con `Infinity` habría hecho que
  `list_runs()` **LANCE** (500 en la lista entera). El normalizador que existe para evitar la
  pantalla rota introducía una ruta de crash nueva. Ahora captura también `OverflowError` y hay
  3 tests nuevos → §F0.2, §F3.
- **C2 (BLOQUEANTE)** — divergencia de tabla de verdad entre los dos normalizadores:
  `toCount(true)` daba **0** en el frontend y `_count(True)` daba **1** en el backend (`bool` es
  subclase de `int` en Python). Con la flag ON la UI mostraba 1 y con la flag OFF, 0. `_count`
  ahora corta con `isinstance(value, bool) → 0`, y la fase nueva **F1.5** hace estructuralmente
  imposible que vuelvan a divergir → §F1.5, §F3.
- **C3 (BLOQUEANTE)** — F6 paso 1 era inejecutable para un modelo menor y traía un anclaje
  FALSO: el `.ps1` **no contiene** ninguna variable `HARNESS_TEST_FILES` (se llama
  `$HarnessTestFiles`) y las dos listas tienen **formas distintas** (el `.sh` desnudo, el `.ps1`
  entrecomillado y con coma). "Mirar cómo está declarada y seguir su forma" era exactamente la
  inferencia que §1 prohíbe. Ahora se dan las **dos líneas literales exactas** con su ancla → §F6.1.
- **C4 (IMPORTANTE)** — F3 no normalizaba la copia ANIDADA `run["diff"]["summary"]`, que es la
  que consumen las violaciones #7 y #8 del censo (`get_run` devuelve el run completo, `diff`
  incluido). Se agrega esa normalización, 2 tests nuevos, y se reescribe KPI-3, que afirmaba
  algo falso → §1, KPI-3, §F0.2, §F3.
- **C5 (IMPORTANTE)** — existe una TERCERA salida de summary (`/baseline-diff`) que nunca pasa
  por `list_runs`/`get_run`; el glosario la negaba al definir "borde de lectura" como "cualquier
  consumidor". Se acota a los runs **persistidos**, se agrega el ítem 7 a Fuera de scope con la
  razón real y verificable, y se corrige §6.3 → §1, §2.4, §6, §7.1.
- **C6 (IMPORTANTE)** — el control anti-censo-vacío del centinela pedía `>= 12` archivos cuando
  hoy hay **57**: se podían borrar 45 y el control seguía verde. Umbral subido a `>= 45` con el
  censo y su fecha en el comentario → §F4.3 test 12.
- **C7 (MENOR)** — F3 condicionaba el import de config ("**si** todavía no importa config").
  Verificado que **no** lo importa (`dbcompare_runs.py:20-28`); ahora es una instrucción
  afirmativa, con la línea, la posición y el precedente exacto del idiom de la casa → §F3.
- **C8 (MENOR)** — plan tipo-fix que mata una clase de error sin registrar su huella. Se agrega
  **F6.4** con la entrada exacta para `docs/sistema/error_fingerprints.json` → §F6.4.
- **C9 (MENOR)** — asimetría deliberada no declarada: el backend normaliza solo los 3 mapas y el
  frontend además `parity_score`/`objects_total`/`objects_unchanged`. Ahora está declarada como
  decisión con su razón, para que nadie la "mejore" y rompa
  `test_list_runs_no_altera_summary_completo` → §F3.
- **C10 (MENOR)** — el criterio de F0.1 exigía el texto literal de V8 moderno, frágil ante la
  versión de Node. Ahora acepta `/reading '?danger'?|property 'danger'/` → §F0.1.
- **C11 (MENOR)** — `firstComponentFromStack` devuelve nombres mangleados en un build de
  producción minificado. Declarado como limitación conocida, sin cambiar el diseño → §F5.1, R10.
- **[ADICIÓN ARQUITECTO] A1** — **F1.5 nueva**: una **tabla de verdad ÚNICA compartida**
  (`__fixtures__/summaryShapeTruthTable.json`) que recorren el test de vitest y el de pytest, con
  anti-vaciado (≥17 casos) y anti-skip (falla si el archivo no está). Es el cierre real de la
  "defensa en profundidad": dos implementaciones independientes que no pueden divergir porque
  comparten la **especificación**, no el código → §F1.5, KPI-6, §7.2, §7.3.
- **[ADICIÓN ARQUITECTO] A2** — **F6.4 nueva**: huella de regresión en `error_fingerprints.json`
  con `log_guarded: false` **justificado** (es un crash de render del navegador: nunca llega a un
  log del backend, así que el smoke de huellas por log no puede verlo; el guard real es el
  ratchet de F4) → §F6.4.

---

## 1. Objetivo y KPI

Eliminar de raíz la clase de bug que hoy rompe una pestaña entera del Comparador de BD: la UI
lee campos anidados del `summary` de una corrida (`by_severity`, `by_action`, `by_object_type`)
asumiendo que **siempre** están, mientras que el backend persiste cada corrida como JSON suelto
en disco **sin normalizar ni versionar** y ya se defiende de esa ausencia en cinco lugares
distintos. El plan introduce un único módulo puro de normalización en el frontend
(`summaryShape.ts`), lo adopta en los **8 accesos profundos sin guarda** que existen hoy,
endurece el **borde de lectura de los runs PERSISTIDOS** del backend
(`dbcompare_runs.list_runs`/`get_run`, incluida la copia anidada del summary dentro de `diff`)
para que ningún run persistido salga con el `summary` a medio formar — hay una **tercera salida**
de summary, `/baseline-diff`, que NO pasa por esas dos funciones y se trata explícitamente en
§2.4 y en §6 ítem 7 —, planta un **centinela quirúrgico** que
impide que el patrón vuelva, y convierte el `PageErrorBoundary` de "un mensaje suelto" en un
diagnóstico accionable (superficie + componente + stack copiable en 1 click).

### KPI (medibles, con el comando que los verifica)

| # | KPI | Medición | Comando |
|---|-----|----------|---------|
| KPI-1 | Accesos profundos sin guarda en `frontend/src/components/dbcompare/**`: **8 → 0** | censo del centinela F4 | `npx vitest run src/__tests__/dbcompareSummaryShapeRatchet.test.ts` |
| KPI-2 | Una corrida con `summary` sin `by_severity` **no lanza**: radar, timeline y hero renderizan ceros | tests puros F0 | `npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts` |
| KPI-3 | 100% de los runs `status=done` devueltos por `list_runs`/`get_run` traen los 3 mapas completos con enteros, **tanto en `summary` como en `diff.summary`** (la copia anidada que devuelve `get_run`) | test backend F0/F3 | `.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q` |
| KPI-4 | El fallback del boundary pasa de 1 dato (mensaje) a 4 (superficie, componente, mensaje, stack copiable) | test puro F5 | `npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts` |
| KPI-5 | Gate de tipos verde con todos los cambios | `tsc --noEmit` | `npm run build` (en `Stacky Agents/frontend`) |
| KPI-6 | La tabla de verdad de la normalización es **una sola** (≥17 casos) y la recorren los **dos** lados con el mismo resultado caso por caso: `toCount` (TS) y `_count` (Python) no pueden divergir — incluidas las 3 clases medidas que el v2 no cubría (`"0x10"`, `"0b101"`, `"1_0"`) | fixture compartido F1.5 | `npx vitest run src/components/dbcompare/summaryShape.test.ts` **y** `.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q` |
| KPI-7 | La flag nueva está en **las 6 patas** del cableado (no en 5): `config.py`, `FLAG_REGISTRY`, `_CATEGORY_KEYS`, `_CURATED_DEFAULTS_ON`, `PLAIN_HELP` **y `_REQUIRES_MAP_FROZEN`**; y el gate lo verifica un test, no una tabla de este documento (**A4**, C22) | test de cableado F3.5 | `.venv\Scripts\python.exe -m pytest tests/test_plan266_flag_cableado.py -q` |

---

## 2. Por qué ahora — la incidencia real y la clase de bug

### 2.1 La incidencia (textual, reportada por el operador en el Comparador de BD)

```
Esta pestaña falló al renderizar
Cannot read properties of undefined (reading 'danger')
El resto de la aplicación sigue funcionando. Podés reintentar o cambiar de pestaña.
```

Ese texto no es un error del backend: sale del boundary por página.
`Stacky Agents/frontend/src/components/PageErrorBoundary.tsx:60` renderiza
`Esta pestaña falló al renderizar`, `:62` muestra `this.state.error?.message` (de ahí sale el
`Cannot read properties of undefined (reading 'danger')`) y `:65` el aviso
`El resto de la aplicación sigue funcionando…`. Es decir: **un `throw` en el RENDER de un
componente del Comparador de BD**.

### 2.2 La causa raíz #1 — auto-evidente por inconsistencia interna del mismo archivo

`Stacky Agents/frontend/src/components/dbcompare/radarLogic.ts:60`:

```ts
const sev = r.summary!.by_severity;   // :60
return {
  t: r.finished_at || "",
  danger: sev.danger || 0,            // :63  <-- "Cannot read properties of undefined (reading 'danger')"
```

El filtro previo (`radarLogic.ts:56`) solo comprueba `!!r.summary`, **no** que traiga
`by_severity`. Si un `CompareRun` tiene `summary` truthy pero sin `by_severity`, `sev` es
`undefined` y `sev.danger` lanza **exactamente** el mensaje reportado.

Que el campo PUEDE faltar lo prueba **el mismo archivo**, que ya se defiende dos veces:

- `radarLogic.ts:31` → `const sev = cell.by_severity || { info: 0, warn: 0, danger: 0 };`
- `radarLogic.ts:104` → idéntico.

`trendSeries()` (`radarLogic.ts:45-68`) es la única que no se defiende, y es la que corre en el
render: `EnvironmentRadar.tsx:152` → `const trend = selected ? trendSeries(runs, selected.source, selected.target) : [];`

### 2.3 La clase de bug — censo COMPLETO de los 8 accesos profundos sin guarda

Verificado línea por línea (2026-07-27) sobre `frontend/src/components/dbcompare/`:

| # | Archivo:línea | Expresión hoy | Mensaje que produce si falta el mapa |
|---|---------------|---------------|--------------------------------------|
| 1 | `radarLogic.ts:60` | `const sev = r.summary!.by_severity;` (+ `sev.danger` en `:63`) | `reading 'danger'` |
| 2 | `RunsTimeline.tsx:37` | `run.summary.by_severity.danger` (guardado SOLO por `run.summary &&` en `:35`) | `reading 'danger'` |
| 3 | `RunsTimeline.tsx:38` | `run.summary.by_severity.warn` / `.info` | `reading 'warn'` |
| 4 | `EnvironmentRadar.tsx:144` | `const sev = r.diff.summary.by_severity;` (+ `${sev.danger}` en `:146`) | `reading 'danger'` |
| 5 | `EnvironmentRadar.tsx:215` | `(cell.by_severity.danger \|\| 0) + (cell.by_severity.warn \|\| 0)` | `reading 'danger'` |
| 6 | `SummaryHero.tsx:145` | `summary.by_object_type[t]` con `t ∈ {table,view,sequence}` | `reading 'table'` |
| 7 | `svgMath.ts:43` | `diff.summary.by_severity[severity]` con `SEVERITY_ORDER = ["danger","warn","info"]` (`svgMath.ts:39`) | `reading 'danger'` |
| 8 | `svgMath.ts:47` | `diff.summary.by_action[action]` con `ACTION_ORDER = ["added","removed","changed"]` (`svgMath.ts:40`) | `reading 'added'` |

`svgMath.severityCounters/actionCounters` se llaman en el render de `SummaryHero.tsx:83`,
`:84`, `:116` y `:130` — o sea que el hero del resultado también rompe la pestaña entera.

**Corrección al dossier de entrada:** `EnvironmentRadar.tsx:215` es un acceso crudo real, pero
el par `radarLogic.ts:31` / `:104` **sí** está guardado (ambos con `|| {info,warn,danger}`); no
se cuentan como violaciones, se migran igual para unificar el criterio (y porque hoy no
protegen contra valores **no numéricos**, solo contra el mapa ausente).

### 2.4 Por qué el dato puede venir incompleto (origen backend, verificado)

- Las corridas se persisten como **JSON suelto en disco, sin versión de esquema ni
  normalización de lectura**: `backend/services/dbcompare_runs.py:68` (`_write_run`),
  `:109` (`_read_run`), y `list_runs()` en `:326-340`, que hace
  `_runs_dir().glob("*.json")` y devuelve el JSON **tal cual** (solo saca `diff`/`data_diff`
  en `:336`). Un run escrito por una versión anterior, a medio escribir, o traído de otra
  máquina entra a la UI con la forma que tenga.
- El run **nace** con `"summary": None` (`dbcompare_runs.py:265`) y recién en el éxito se
  setea completo (`:304` → `summary=diff["summary"]`). Una corrida interrumpida queda con
  formas intermedias.
- El **backend ya se defiende** de la falta de `by_severity` en cinco lugares — la prueba
  más dura de que el hueco es real y conocido:
  - `backend/services/dbcompare_watch.py:226` → `sev = (summary or {}).get("by_severity") or {}`
  - `backend/services/dbcompare_watch.py:238-239` → `prev.get("by_severity") or {}` / `new_summary.get("by_severity") or {}`
  - `backend/services/dbcompare_watch.py:397` → `... or {"info": 0, "warn": 0, "danger": 0}`
  - `backend/api/db_compare_watch.py:153` → `sev = (meta["summary"] or {}).get("by_severity") or {}` —
    y este emite `by_severity: {}` (dict **vacío**) hacia la celda del radar en `:161`, que es
    exactamente la forma que revienta `EnvironmentRadar.tsx:215`.
- La forma canónica la produce `backend/services/dbcompare_diff.py:321-337` (`summarize()`,
  con `by_severity = {"info": 0, "warn": 0, "danger": 0}` en `:322`).
- **Tercera salida de summary, FUERA del borde de lectura (verificado, corrección del v1):**
  `EnvironmentRadar.tsx:144` —la violación #4 del censo— no consume un run persistido: llama a
  `DbCompareWatch.baselineDiff(alias)` → `backend/api/db_compare_watch.py:125-133`
  (`baseline_diff_route`) → `backend/services/dbcompare_baseline.py:151-166` (`baseline_diff`),
  que devuelve el resultado de `dbcompare_diff.diff_snapshots(...)` **directo al `jsonify`**, sin
  pasar jamás por `list_runs` ni por `get_run`. Esa ruta **NO** la cubre F3; se declara fuera de
  scope con su razón verificable en §6 ítem 7 (la cubre el productor canónico `summarize()` más
  la normalización del frontend en F2).

**Conclusión:** el frontend confía en un contrato que el backend nunca garantizó. Se arregla
en los dos lados (el backend deja de emitir formas parciales; el frontend deja de asumir), y
se planta un centinela para que el patrón no vuelva por un archivo nuevo.

### 2.5 El gap secundario: el boundary no dice nada útil

`PageErrorBoundary.componentDidCatch` (`:30-43`) recibe `info: React.ErrorInfo` —que trae el
`componentStack`— y **lo descarta**: solo lo manda a `console.error` (`:32`) y publica en el
Centro de Actividad un `body: String(error?.message || error)` (`:40`), sin nombre de
componente ni superficie. El operador ve `Cannot read properties of undefined (reading
'danger')` y no tiene forma de saber **qué** componente ni **qué** pestaña. Esto costó una
sesión entera de investigación para esta incidencia; es deuda de diagnóstico, no cosmética.

---

## 3. Principios y guardarraíles

1. **El arreglo del crash NO va detrás de una flag.** Una flag que pueda re-habilitar un
   `throw` en el render es absurda. F1/F2/F5 son incondicionales. La única flag nueva gatea el
   cambio de **forma del payload** del backend (F3), que sí es un cambio de contrato observable
   y merece kill-switch auditable.
2. **Defensa en profundidad, no sustitución.** El backend normaliza y el frontend igual
   normaliza. Un payload que venga de una versión vieja del backend, de un `localStorage`, o
   de un `fetch` a mano sigue sin poder romper la pantalla.
3. **Normalización solo-lectura, en memoria.** No se reescribe ni migra ningún JSON de corridas
   del operador en disco. (Ver §6, Fuera de scope.)
4. **`summary: null` se conserva como `null`.** Un run `running` legítimamente no tiene summary;
   convertirlo en `{}` con ceros haría que `RunsTimeline.tsx:35` y `db_compare_watch.py:146`
   muestren/cuenten "0 danger" para corridas que todavía no compararon nada. Eso sería mentir.
5. **Toda la lógica testeable vive en `.ts` puros.** El repo **no tiene RTL ni jsdom**
   (restricción estructural conocida; ver la nota en
   `frontend/src/components/__tests__/PageErrorBoundary.test.tsx:1-8`). Ningún test de este plan
   renderiza React. Patrón de la casa a copiar: `radarLogic.ts` + `radarLogic.test.ts`,
   `maskingLogic.ts` + `maskingLogic.test.ts`.
6. **Backward-compatible.** El payload solo **agrega** claves faltantes; nunca quita ni renombra.
   El título `Esta pestaña falló al renderizar` del boundary NO se toca
   (`frontend/src/components/__tests__/PageErrorBoundary.test.tsx:29` lo asserta).
7. **Cero trabajo para el operador.** Nada que configurar, nada que aprobar, nada que migrar.
8. **Centinela quirúrgico, no masivo.** Precedente doloroso de la casa: un centinela por regex
   destructivo ya rompió el motor de flags. El de F4 tiene un patrón determinable, una lista de
   exenciones explícita y controles negativos con fixtures (§F4.4 prueba por qué no puede tener
   falsos positivos masivos).
9. **Este documento vive en `Stacky Agents/docs/`, FUERA del alcance del centinela** (que solo
   escanea `frontend/src/components/dbcompare/`), así que la prosa de acá no puede disparar el
   gate. Gotcha recurrente de la casa: un comentario que contiene su propia cadena prohibida.
   Lo mismo vale para el `copyDebtRatchet` (alcance `frontend/src/`) y el `uiDebtRatchet`
   (alcance `frontend/src/**/*.module.css` y `*.tsx`): este `.md` no está bajo `src/`.
10. **Datos personales: el diagnóstico no puede convertirse en una fuga (C30).** Este plan opera
    sobre un comparador de **bases de datos reales**: un mensaje de error del navegador puede
    arrastrar un valor de fila. Tres reglas, las tres verificables:
    **(a) el enmascarado va ANTES del egreso, nunca después.** La normalización de F3 se inserta
    **dentro** de `dbcompare_runs.get_run`, y `dbcompare_masking.apply_to_run_response` se aplica
    **aguas abajo**, en `backend/api/db_compare.py:447`. Ese orden es el correcto y **no se
    invierte**: enmascarar después de la comprobación anularía la comprobación (falla abierto).
    Ninguna fase de este plan mueve, envuelve ni saltea esa llamada.
    **(b) nada de F5 sale del navegador.** `publishActivity` escribe en el store en memoria y en
    `localStorage` (`frontend/src/services/activityCenter.ts:35`) y el módulo **no hace ningún
    `fetch` ni POST** (verificado: cero llamadas de red en el archivo). El stack **solo** llega al
    portapapeles cuando el operador **hace click** (human-in-the-loop; no hay envío automático).
    **(c) lo que se muestra y se copia está ACOTADO.** `message` y `stack` se truncan
    (§F5.1), así que ni el cartel ni `localStorage` pueden acumular un payload de diff completo.
    `dbcompare_masking.py` **no cubre esto y no podría**: es del backend y trabaja por patrones
    sobre el data-diff, nunca ve un `throw` de render del navegador. Por eso la defensa acá es la
    cota, no el masking.

---

## 4. Fases

Convención de comandos:
- Backend: desde `Stacky Agents/backend`, intérprete `.venv\Scripts\python.exe` (venv py3.13).
  **Correr SIEMPRE por archivo** (contaminación de suite conocida).
- Frontend: desde `Stacky Agents/frontend`, `npx vitest run <ruta>`.
  **Correr SIEMPRE por archivo** (contaminación cross-file conocida).

---

### F0 — Reproducción: los rojos que hoy prueban el bug

**Objetivo (1 frase):** dejar por escrito, en dos tests que HOY fallan, el crash exacto que
reportó el operador y el payload parcial que lo origina.
**Valor:** sin esto el plan no prueba nada; con esto, cualquier regresión futura vuelve a dar rojo.

#### F0.1 — Frontend (rojo por `throw`)

**Archivo nuevo:** `Stacky Agents/frontend/src/components/dbcompare/__tests__/summaryShapeCrash.test.ts`

Casos. **Ojo con cuál falla y cómo (C14):** los casos **1, 2 y 3 LANZAN** hoy; el caso 4 **NO
lanza** —falla por **aserción**— y el caso 5 **pasa en verde ya hoy**. El v2 decía "los 4 primeros
deben lanzar HOY" y era falso: con `by_severity = {}`, `svgMath.ts:43` evalúa `{}["danger"]`, que
es `undefined`, no un `throw`. Un implementador que espere un `throw` ahí concluiría que el
fixture está mal y lo "arreglaría", destruyendo justo el caso que cubre la forma que emite
`api/db_compare_watch.py:153`.

| Caso | Entrada | Aserción |
|------|---------|----------|
| `trendSeries no lanza con summary sin by_severity` | `runs = [runFixture({ summary: { parity_score: 91.7 } })]`, par `("DEV","QA")` | `expect(() => trendSeries(runs, "DEV", "QA")).not.toThrow()` y el punto resultante es `{ t, danger: 0, warn: 0, info: 0 }` |
| `severityCounters no lanza con summary sin by_severity` | `diff = { summary: { parity_score: 91.7 } } as unknown as SchemaDiff` | `not.toThrow()` y `[{danger:0},{warn:0},{info:0}]` (en el orden de `SEVERITY_ORDER`) |
| `actionCounters no lanza con summary sin by_action` | idem | `not.toThrow()` y los 3 en 0 |
| `severityCounters tolera by_severity vacío` | `summary.by_severity = {}` (la forma que emite `api/db_compare_watch.py:153`) | los 3 contadores en 0 |
| `trendSeries sigue devolviendo los valores reales cuando el summary está completo` | run `done` con `by_severity: {info:1, warn:2, danger:3}` | `[{ t: "...", danger: 3, warn: 2, info: 1 }]` — **control positivo: sin esto el fix podría devolver ceros siempre y el test seguiría verde** |

Helper del fixture (escribirlo en el propio archivo de test, sin dependencias nuevas):

```ts
function runFixture(over: Record<string, unknown>): CompareRun {
  return {
    run_id: "run_x", source_alias: "DEV", target_alias: "QA", engine: "sqlserver",
    mode: "fresh", status: "done", phase: "done",
    started_at: "2026-07-27T10:00:00Z", finished_at: "2026-07-27T10:01:00Z",
    duration_ms: 60000, source_snapshot_id: "s1", target_snapshot_id: "s2",
    summary: null, diff: null, error: null,
    ...over,
  } as unknown as CompareRun;
}
```

**Comando:**
`npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts`

**Criterio de aceptación (binario, EN ESTA FASE) — por test nombrado, no por "el texto del
fallo" (C14):** el comando falla, y en el reporte de vitest:

| Test | Estado esperado HOY | Motivo del rojo |
|---|---|---|
| `trendSeries no lanza con summary sin by_severity` | ROJO | `throw`, y el mensaje matchea `/reading '?danger'?\|property 'danger'/` |
| `severityCounters no lanza con summary sin by_severity` | ROJO | `throw`, mismo match |
| `actionCounters no lanza con summary sin by_action` | ROJO | `throw`, mensaje con `'added'` |
| `severityCounters tolera by_severity vacío` | ROJO | **aserción**, NO `throw`: recibe `undefined` donde espera `0` |
| `trendSeries sigue devolviendo los valores reales…` | **VERDE ya hoy** | control positivo; si sale rojo, el fixture está mal |

El v2 pedía "el texto del fallo matchea la regex", ambiguo cuando hay 4 fallos con causas
distintas. Con la tabla de arriba el criterio es binario y no se puede satisfacer por accidente.
**Al menos uno** de los tres primeros debe mencionar `danger`: si ninguno lo hace, el test no
reproduce la incidencia (import roto, typo en el fixture, archivo mal ubicado) y hay que
corregirlo antes de seguir.

Se aceptan las **dos** redacciones a propósito (corrección del v1, que exigía una sola cadena
literal): el mensaje lo produce el motor de JS, no Stacky. V8 moderno dice
`Cannot read properties of undefined (reading 'danger')` y motores/versiones viejas dicen
`Cannot read property 'danger' of undefined`. Atar el criterio a una versión de Node lo hace
frágil. Lo que importa es que **el rojo sea por ESA propiedad** y no por otra cosa (un import
roto, un typo en el fixture, un archivo mal ubicado): si el fallo no menciona `danger`, el test
NO reproduce la incidencia y hay que corregirlo antes de seguir.

#### F0.2 — Backend (rojo por forma del payload)

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan266_summary_shape.py`

Setup común (sin Flask, sin DB — este test **no** importa `app`, así que no toca la base viva):

```python
import json
import pytest
from services import dbcompare_runs

def _run_dict(run_id, **over):
    base = {
        "run_id": run_id, "source_alias": "DEV", "target_alias": "QA",
        "engine": "sqlserver", "initiated_by": "operator", "mode": "fresh",
        "status": "done", "phase": "done",
        "started_at": "2026-07-27T10:00:00Z", "finished_at": "2026-07-27T10:01:00Z",
        "duration_ms": 60000, "source_snapshot_id": "s1", "target_snapshot_id": "s2",
        "summary": None, "diff": None, "error": None,
    }
    base.update(over)
    return base

@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dbcompare_runs, "_runs_dir", lambda: tmp_path)
    return tmp_path

def _write(runs_dir, run):
    (runs_dir / f"{run['run_id']}.json").write_text(
        json.dumps(run, ensure_ascii=False), encoding="utf-8")
```

Casos:

| Test | Entrada en disco | Aserción |
|------|------------------|----------|
| `test_list_runs_completa_by_severity_faltante` | `summary={"parity_score": 91.7}` | `list_runs()[0]["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 0}` |
| `test_list_runs_completa_by_action_y_by_object_type` | idem | ambos mapas completos con las 3 claves canónicas en 0 |
| `test_list_runs_completa_claves_parciales` | `by_severity={"danger": 3}` | `{"info": 0, "warn": 0, "danger": 3}` |
| `test_list_runs_coerce_valores_no_numericos` | `by_severity={"danger": "3", "warn": None, "info": -1}` | `{"info": 0, "warn": 0, "danger": 3}` (todos `int`) |
| `test_list_runs_preserva_summary_none` | `summary=None`, `status="running"` | `list_runs()[0]["summary"] is None` (**NO** un dict de ceros) |
| `test_get_run_normaliza_igual_que_list_runs` | `summary={"parity_score": 91.7}` | `get_run("r1")["summary"]["by_severity"] == {"info":0,"warn":0,"danger":0}` |
| `test_get_run_normaliza_tambien_el_summary_anidado_del_diff` | run con `summary={"parity_score": 91.7}` **y** `diff={"summary": {"parity_score": 91.7}, "objects": []}` | `get_run("r1")["diff"]["summary"]["by_severity"] == {"info":0,"warn":0,"danger":0}` y lo mismo para `by_action` y `by_object_type` (**C4**: `get_run` devuelve el run completo con `diff` adentro, y esa copia anidada es la que consumen `SummaryHero.tsx:49-50` y `svgMath.ts:43`/`:47`) |
| `test_get_run_no_reescribe_el_archivo_en_disco` | idem anterior | tras `get_run("r1")`, `path.read_bytes()` antes == después (la normalización del anidado es una copia superficial en memoria, no toca disco) |
| `test_list_runs_no_altera_summary_completo` | summary canónico de `dbcompare_diff.summarize` | el dict sale **igual** (control positivo: la normalización no puede pisar datos buenos) |
| `test_list_runs_no_reescribe_el_archivo_en_disco` | `summary={"parity_score": 91.7}` | tras `list_runs()`, el contenido del `.json` sigue byte-idéntico (`path.read_bytes()` antes == después) |
| `test_count_infinito_es_cero` | — | `dbcompare_runs._count(float("inf")) == 0` **y** `dbcompare_runs._count(float("-inf")) == 0` (**C1**: `int(float(float("inf")))` lanza `OverflowError`) |
| `test_count_nan_es_cero` | — | `dbcompare_runs._count(float("nan")) == 0` |
| `test_count_booleano_es_cero` | — | `dbcompare_runs._count(True) == 0` y `dbcompare_runs._count(False) == 0` (**C2**: en Python `bool` es subclase de `int`; sin el corte, `True` daría 1 y el frontend daría 0) |
| `test_list_runs_no_lanza_con_infinity_en_disco` | ver el bloque de abajo | `list_runs()` **no lanza** y `list_runs()[0]["summary"]["by_severity"]["danger"] == 0` |

**El test de `Infinity` NO puede usar el helper `_write`** (que serializa con `json.dumps`): el
archivo se escribe **a mano**, con el token crudo `Infinity` dentro del JSON, porque eso es lo
que puede haber realmente en el disco del operador y porque `json.loads` lo acepta por default:

```python
def test_list_runs_no_lanza_con_infinity_en_disco(runs_dir):
    (runs_dir / "r_inf.json").write_text(
        '{"run_id": "r_inf", "source_alias": "DEV", "target_alias": "QA",'
        ' "engine": "sqlserver", "status": "done", "phase": "done",'
        ' "started_at": "2026-07-27T10:00:00Z", "finished_at": "2026-07-27T10:01:00Z",'
        ' "summary": {"parity_score": 91.7, "by_severity": {"danger": Infinity,'
        ' "warn": -Infinity, "info": NaN}}}',
        encoding="utf-8",
    )
    runs = dbcompare_runs.list_runs()          # NO debe lanzar
    assert runs[0]["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 0}
```

**Comando:**
`.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q`

**Criterio de aceptación (binario, EN ESTA FASE):** el comando falla con al menos 6 tests en
rojo por `KeyError`/`AssertionError` sobre el mapa `by_severity`, más los 4 tests de `_count`
(`infinito`, `nan`, `booleano`, `no_lanza_con_infinity`) en rojo por `AttributeError`
(`_count` no existe hasta F3). Los tres controles positivos
(`no_altera_summary_completo`, `list_runs_no_reescribe_el_archivo_en_disco`,
`get_run_no_reescribe_el_archivo_en_disco`) deben salir **verdes ya hoy** — si alguno sale rojo,
el fixture está mal armado.

**Flag que la protege:** ninguna (son tests).
**Impacto por runtime (Codex / Claude Code / Copilot):** neutro/idéntico en los 3 — es
frontend/backend de la app; el runtime solo implementa, no participa en la ejecución. Sin fallback necesario.
**Trabajo del operador:** ninguno.

---

### F1 — `summaryShape.ts`: el módulo puro de normalización

**Objetivo (1 frase):** una única fuente de verdad, testeada, que convierte cualquier cosa en
un `summary` con forma canónica y valores numéricos.
**Valor:** los 8 puntos de render dejan de tener cada uno su propia (o ninguna) defensa.

**Archivo nuevo:** `Stacky Agents/frontend/src/components/dbcompare/summaryShape.ts`

**API EXACTA (nombres congelados — el centinela de F4 depende de ellos):**

```ts
// Plan 266 — Forma garantizada del summary del Comparador de BD.
// ÚNICA fuente de verdad: ningún componente de dbcompare/ puede leer by_severity /
// by_action / by_object_type sin pasar por acá (lo verifica el ratchet
// src/__tests__/dbcompareSummaryShapeRatchet.test.ts).
//
// NOTA DE IMPLEMENTACIÓN (no cosmética): este módulo lee las claves con corchetes y
// literal de string — src["by_severity"] — y NUNCA con punto. Así el archivo no
// contiene el patrón que su propio ratchet prohíbe y no necesita estar en su allowlist.
import type { Severity, DiffAction, ObjectType, DiffSummary } from "./dbcompareTypes";

export const EMPTY_BY_SEVERITY: Record<Severity, number>;
export const EMPTY_BY_ACTION: Record<DiffAction, number>;
export const EMPTY_BY_OBJECT_TYPE: Record<ObjectType, number>;

export function toCount(value: unknown): number;
export function toScore(value: unknown): number;
export function safeBySeverity(raw: unknown): Record<Severity, number>;
export function safeByAction(raw: unknown): Record<DiffAction, number>;
export function safeByObjectType(raw: unknown): Record<ObjectType, number>;
export function safeSummary(raw: unknown): DiffSummary;
```

**Semántica de cada símbolo (sin ambigüedad):**

- `EMPTY_BY_SEVERITY = { info: 0, warn: 0, danger: 0 }` (orden de claves irrelevante).
  `EMPTY_BY_ACTION = { added: 0, removed: 0, changed: 0 }`.
  `EMPTY_BY_OBJECT_TYPE = { table: 0, view: 0, sequence: 0 }`.
  Declarados con `Object.freeze(...)` para que nadie los mute por accidente; las funciones
  **devuelven objetos nuevos**, nunca la constante.
- `toCount(value)` → entero `>= 0`. Reglas, en orden:
  `number` → se usa; `string` → `Number(value)`; cualquier otro tipo (incl. `null`,
  `undefined`, `boolean`, objeto, array) → `NaN`. Si el resultado no es finito o es `< 0` →
  `0`. Si no, `Math.floor(n)`.
- `toScore(value)` → número con 1 decimal, clampeado a `[0, 100]`. Misma coerción que
  `toCount`; no finito → `0`; luego `Math.min(100, Math.max(0, Math.round(n * 10) / 10))`.
  (Se separa de `toCount` porque `parity_score` es un float — `dbcompare_diff.py:329` hace
  `round(..., 1)` — y `Math.floor` lo corrompería.)
- `safeBySeverity(raw)` → `{ info, warn, danger }` con `toCount` en cada clave, leyendo de
  `raw` si es un objeto no-null, y de `{}` en cualquier otro caso.
  Ídem `safeByAction` (added/removed/changed) y `safeByObjectType` (table/view/sequence).
- `safeSummary(raw)` → `DiffSummary` **completo**:
  `by_severity`/`by_action`/`by_object_type` vía las 3 funciones anteriores,
  `objects_total` y `objects_unchanged` vía `toCount`, `parity_score` vía `toScore`.

**Implementación de referencia (pseudocódigo ejecutable):**

```ts
function asRecord(raw: unknown): Record<string, unknown> {
  return raw !== null && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
}

export function toCount(value: unknown): number {
  const n = typeof value === "number" ? value
          : typeof value === "string" ? Number(value)
          : NaN;
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

export function safeBySeverity(raw: unknown): Record<Severity, number> {
  const src = asRecord(raw);
  return { info: toCount(src["info"]), warn: toCount(src["warn"]), danger: toCount(src["danger"]) };
}

export function safeSummary(raw: unknown): DiffSummary {
  const src = asRecord(raw);
  return {
    by_severity: safeBySeverity(src["by_severity"]),
    by_action: safeByAction(src["by_action"]),
    by_object_type: safeByObjectType(src["by_object_type"]),
    objects_total: toCount(src["objects_total"]),
    objects_unchanged: toCount(src["objects_unchanged"]),
    parity_score: toScore(src["parity_score"]),
  };
}
```

**Tests PRIMERO.** Archivo nuevo:
`Stacky Agents/frontend/src/components/dbcompare/summaryShape.test.ts`
(sibling del módulo, patrón exacto de `radarLogic.test.ts` / `maskingLogic.test.ts`).

Casos borde obligatorios (uno por fila, sin agrupar):

| Entrada a `safeBySeverity` | Salida esperada |
|---|---|
| `undefined` | `{info:0, warn:0, danger:0}` |
| `null` | `{info:0, warn:0, danger:0}` |
| `{}` | `{info:0, warn:0, danger:0}` |
| `{ danger: 3 }` (parcial) | `{info:0, warn:0, danger:3}` |
| `{ danger: "3" }` (string numérico) | `{info:0, warn:0, danger:3}` |
| `{ danger: "abc" }` | `{info:0, warn:0, danger:0}` |
| `{ danger: -5 }` | `{info:0, warn:0, danger:0}` |
| `{ danger: 2.9 }` | `{info:0, warn:0, danger:2}` |
| `{ danger: NaN }` / `{ danger: Infinity }` | `{info:0, warn:0, danger:0}` |
| `{ danger: true }` | `{info:0, warn:0, danger:0}` |
| `42` (no objeto) | `{info:0, warn:0, danger:0}` |
| `"texto"` | `{info:0, warn:0, danger:0}` |
| `[1, 2, 3]` | `{info:0, warn:0, danger:0}` |
| `{ danger: 3, extra: 9 }` | `{info:0, warn:0, danger:3}` (la clave extra se descarta) |
| `{ info: 1, warn: 2, danger: 3 }` | `{info:1, warn:2, danger:3}` (**control positivo**) |

Más:
- `toScore`: `91.7 → 91.7`; `"91.7" → 91.7`; `120 → 100`; `-3 → 0`; `undefined → 0`;
  `91.74 → 91.7`; `null → 0`.
- `safeSummary(undefined)` devuelve el objeto completo con los 6 campos y los 3 mapas llenos de ceros.
- `safeSummary` no muta la entrada: `const src = {...}; safeSummary(src); expect(src).toEqual(copia)`.
- `safeBySeverity(EMPTY_BY_SEVERITY) !== EMPTY_BY_SEVERITY` (devuelve objeto nuevo).
- `safeByAction` y `safeByObjectType`: al menos los casos `undefined`, `{}`, parcial, completo.

**Nota (C2 / A1):** la fila `{ danger: true }` → `0` **no es cosmética**. El normalizador gemelo
del backend (`_count`) daría `1` para `True` si no se corta el `bool` explícitamente, porque en
Python `bool` es subclase de `int`. La fase **F1.5** convierte esta tabla de casos en un archivo
compartido por los dos lados para que la divergencia sea imposible, y **agrega tres tests más a
este mismo archivo** (`summaryShape.test.ts`); no se crea un archivo de test nuevo.

**Comando:** `npx vitest run src/components/dbcompare/summaryShape.test.ts`
**Criterio de aceptación (binario):** el comando termina en `0 failed` con **≥ 28 tests**
(después de F1.5, **≥ 31**).
**Flag:** ninguna — es un módulo puro nuevo, sin efecto observable hasta F2. Un módulo detrás de
flag sería código muerto.
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F1.5 — [ADICIÓN ARQUITECTO] Tabla de verdad ÚNICA, compartida por los dos normalizadores

**Objetivo (1 frase):** que `toCount` (TypeScript) y `_count` (Python) no puedan volver a
divergir, porque los dos recorren **el mismo archivo de casos**.

**Valor:** el v1 se apoyaba en "defensa en profundidad: backend y frontend normalizan por
separado" (§3.2) y sin embargo las dos implementaciones daban números **distintos** para la
misma entrada (`true` → `0` en TS, → `1` en Python): con la flag ON la UI habría mostrado 1 y
con la flag OFF, 0 — exactamente la clase de inconsistencia que este plan dice matar. Compartir
el **código** entre un `.ts` y un `.py` es imposible; compartir la **especificación** no lo es.
Dos implementaciones independientes que no pueden divergir porque comparten la spec: eso, y no
la duplicación, es defensa en profundidad de verdad.

**Precedente de la casa:** los ratchets del frontend ya versionan sus baselines como JSON al
lado del test (`frontend/src/__tests__/uiDebtBaseline.json`, `copyDebtBaseline.json`,
`formatDebtBaseline.json`). Este archivo sigue esa forma.

#### F1.5.1 — El fixture compartido

**Archivo nuevo:**
`Stacky Agents/frontend/src/components/dbcompare/__fixtures__/summaryShapeTruthTable.json`

Un array JSON de casos. Cada caso es un objeto con **exactamente** 3 claves:

| Clave | Tipo | Significado |
|---|---|---|
| `in` | valor JSON, o el sobre `{"raw": "<nombre>"}` | la entrada que recibe el normalizador |
| `out` | entero | el resultado esperado, **idéntico** en los dos lenguajes |
| `why` | string | el motivo, en una línea (se imprime cuando el caso falla) |

**Regla del sobre `{"raw": ...}` (sin ambigüedad):** JSON estándar no puede escribir `NaN` ni
`Infinity`. Cuando un caso los necesita, `in` es el objeto `{"raw": "<nombre>"}` con `<nombre>`
∈ `{"NaN", "Infinity", "-Infinity"}` y **nada más**. Cada lado lo materializa en su lenguaje
**antes** de llamar al normalizador:

- TypeScript: `"NaN"` → `NaN`, `"Infinity"` → `Infinity`, `"-Infinity"` → `-Infinity`.
- Python: `"NaN"` → `float("nan")`, `"Infinity"` → `float("inf")`, `"-Infinity"` → `float("-inf")`.

Un objeto con la clave `raw` **nunca** se pasa tal cual al normalizador. Si un caso quiere
probar "un objeto genérico", usa `{}` (que también está en la tabla). Un sobre con un nombre
distinto de esos tres es un **error del fixture** y debe dar ROJO, nunca colarse como "objeto
genérico".

**Contenido exacto del archivo (18 casos — copiarlo literal):**

```json
[
  { "in": 3, "out": 3, "why": "entero positivo: pasa tal cual" },
  { "in": "3", "out": 3, "why": "string numerico: se coerce" },
  { "in": "abc", "out": 0, "why": "string no numerico: 0" },
  { "in": "", "out": 0, "why": "string vacio: 0 (JS lo coerce a 0, Python lanza ValueError; ambos deben dar 0)" },
  { "in": -5, "out": 0, "why": "negativo: se clampea a 0" },
  { "in": 2.9, "out": 2, "why": "float: se trunca hacia abajo" },
  { "in": 0, "out": 0, "why": "cero: se preserva" },
  { "in": null, "out": 0, "why": "ausente: 0" },
  { "in": true, "out": 0, "why": "booleano: NO es un contador; en Python bool es int y daria 1, prohibido" },
  { "in": false, "out": 0, "why": "booleano: NO es un contador" },
  { "in": [], "out": 0, "why": "array: 0" },
  { "in": {}, "out": 0, "why": "objeto: 0" },
  { "in": 1e400, "out": 0, "why": "desborda a infinito al parsear el JSON: 0, y NO puede lanzar" },
  { "in": { "raw": "NaN" }, "out": 0, "why": "NaN materializado por cada lado: 0" },
  { "in": "0x10", "out": 0, "why": "C16 hexadecimal en string: Number() da 16 y float() lanza; la spec manda 0" },
  { "in": "0b101", "out": 0, "why": "C16 binario en string: Number() da 5 y float() lanza; la spec manda 0" },
  { "in": "1e2", "out": 100, "why": "C16 notacion cientifica: los dos lados dan 100; es el control positivo de la familia" },
  { "in": "1_0", "out": 0, "why": "C21 guion bajo: float() de Python da 10.0 y Number() da NaN; la spec manda 0" }
]
```

**Regla que fijan los 4 casos nuevos (C16 + C21), obligatoria para LOS DOS normalizadores:** un
string solo se acepta si es un **decimal**. Las dos coerciones nativas se pasan de generosas, cada
una para su lado, y **en direcciones opuestas** — por eso hace falta el mismo guard en los dos:

| Entrada | `Number()` (JS) | `float()` (Python) | Divergencia sin guard |
|---|---|---|---|
| `"0x10"` | `16` (JS entiende hex) | `ValueError` | TS **16** vs Py **0** |
| `"0b101"` | `5` (JS entiende binario) | `ValueError` | TS **5** vs Py **0** |
| `"1_0"` | `NaN` | `10.0` (Python admite `_`) | TS **0** vs Py **10** |
| `"1e2"` | `100` | `100.0` | ninguna — control positivo |

Las tres primeras filas están **medidas ejecutando las dos implementaciones**, no razonadas. Es la
misma clase de bug que C2 (`true`), sobrevivió a la crítica del v1, y **no estaba en la tabla** que
se declara "la especificación ÚNICA". La regla, entonces, es una sola y se escribe dos veces:

**(a) `toCount` (TypeScript)** — este bloque **sustituye** al `Number(value)` desnudo del
pseudocódigo de §F1:

```ts
// C16/C21 — solo decimales. Number() acepta 0x/0b/0o y float() de Python acepta "1_0":
// sin este guard los dos lados divergen (medido: "0x10" -> 16 en TS / 0 en Python).
const DECIMAL_RE = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

export function toCount(value: unknown): number {
  const n = typeof value === "number" ? value
          : typeof value === "string" ? (DECIMAL_RE.test(value.trim()) ? Number(value) : NaN)
          : NaN;
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}
```

**(b) `_count` (Python)** — la MISMA regex, aplicada antes del `float()`. El detalle está en §F3;
se anota acá para que la spec se lea completa de un lado.

`"1e2" → 100` y `"  3  " → 3` siguen funcionando (los cubre la regex, y `1e2` está en la tabla
como control positivo para que nadie la endurezca de más y rompa la notación científica).
Las 18 filas fueron corridas contra las dos implementaciones con el guard puesto: **18/18
coinciden**.

Tres casos merecen explicación porque son los que atrapan bugs reales:

- **`1e400`** es JSON perfectamente válido y **los dos parsers lo leen como infinito**
  (`JSON.parse` → `Infinity`; `json.loads` → `float("inf")`). Es el caso que prueba C1 desde la
  tabla: si `_count` no captura `OverflowError`, este caso no devuelve `0`, **lanza**.
- **`""`**: `Number("")` en JS es `0` (finito) y `float("")` en Python lanza `ValueError`. Los
  dos caminos terminan en `0`, pero por motivos distintos — por eso el caso está anclado.

#### F1.5.2 — Los dos recorridos

**(a) Frontend** — se **AGREGAN** a
`Stacky Agents/frontend/src/components/dbcompare/summaryShape.test.ts` (el archivo de F1, no uno
nuevo). Lectura por `fs`, no por `import` de JSON: así no depende de `resolveJsonModule` en
`tsconfig` y además permite el test anti-ausencia.

```ts
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

// vitest se invoca desde `Stacky Agents/frontend`, igual que los ratchets de src/__tests__.
const TRUTH_PATH = resolve(
  process.cwd(),
  "src/components/dbcompare/__fixtures__/summaryShapeTruthTable.json",
);
type Caso = { in: unknown; out: number; why: string };
const TRUTH: Caso[] = existsSync(TRUTH_PATH)
  ? (JSON.parse(readFileSync(TRUTH_PATH, "utf-8")) as Caso[])
  : [];

function materializar(v: unknown): unknown {
  if (
    v !== null && typeof v === "object" && !Array.isArray(v) &&
    Object.keys(v as object).length === 1 &&
    typeof (v as { raw?: unknown }).raw === "string"
  ) {
    const raw = (v as { raw: string }).raw;
    if (raw === "NaN") return NaN;
    if (raw === "Infinity") return Infinity;
    if (raw === "-Infinity") return -Infinity;
    throw new Error(`sobre raw desconocido en la tabla de verdad: ${raw}`);
  }
  return v;
}
```

| # | Test | Aserción |
|---|------|----------|
| T1 | `la tabla de verdad compartida existe` | `expect(existsSync(TRUTH_PATH)).toBe(true)` — **anti-skip**: si el archivo no está, el test es ROJO, nunca "salteado" |
| T2 | `la tabla de verdad compartida tiene al menos 17 casos` | `expect(TRUTH.length).toBeGreaterThanOrEqual(17)` — anti-vaciado del fixture |
| T3 | `toCount cumple cada caso de la tabla de verdad` | `for (const c of TRUTH) { expect(toCount(materializar(c.in)), c.why).toBe(c.out); }` — el `why` entra como mensaje para que el fallo diga **cuál** caso falló |

**(b) Backend** — se **AGREGAN** a
`Stacky Agents/backend/tests/test_plan266_summary_shape.py` (el archivo de F0.2, no uno nuevo):

```python
import pathlib

# tests/ -> backend/ -> "Stacky Agents"/
_TRUTH_TABLE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "components" / "dbcompare" / "__fixtures__"
    / "summaryShapeTruthTable.json"
)


def _materializar(v):
    if isinstance(v, dict) and set(v.keys()) == {"raw"} and isinstance(v["raw"], str):
        raw = v["raw"]
        if raw == "NaN":
            return float("nan")
        if raw == "Infinity":
            return float("inf")
        if raw == "-Infinity":
            return float("-inf")
        raise AssertionError(f"sobre raw desconocido en la tabla de verdad: {raw}")
    return v
```

| # | Test | Aserción |
|---|------|----------|
| T4 | `test_tabla_de_verdad_compartida_existe` | `assert _TRUTH_TABLE.is_file()` — **prohibido** `pytest.skip` por archivo faltante: un skip acá es un falso verde |
| T5 | `test_tabla_de_verdad_compartida_tiene_al_menos_17_casos` | `assert len(json.loads(_TRUTH_TABLE.read_text(encoding="utf-8"))) >= 17` |
| T6 | `test_count_cumple_cada_caso_de_la_tabla_de_verdad` | para cada caso: `assert dbcompare_runs._count(_materializar(c["in"])) == c["out"], c["why"]` |

La ruta se arma con `pathlib` a partir de `__file__`, **nunca** relativa al CWD (gotcha de la
casa: un path relativo al CWD rompe según desde dónde se invoque pytest).

**Comandos:**
```
npx vitest run src/components/dbcompare/summaryShape.test.ts
.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q
```

**Criterio de aceptación (binario):** el de vitest en `0 failed` con **≥ 31 tests** (los ≥28 de
F1 más T1/T2/T3). El de pytest sigue **ROJO** en esta fase, porque T6 depende de `_count`, que
nace recién en F3; pasa a verde en F3. **T4 y T5 salen verdes ya acá** (el archivo existe apenas
se crea el fixture): si T4 o T5 salen rojos, el fixture está mal ubicado y hay que corregir la
ruta antes de seguir.

**Flag:** ninguna (es un fixture más tests).
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F2 — Adopción en los 8 puntos de render (el fix del crash)

**Objetivo (1 frase):** que ningún componente de `dbcompare/` vuelva a leer un mapa del summary
sin pasar por `summaryShape.ts`.
**Valor:** cierra la incidencia reportada; F0.1 pasa a verde.

**Regla de estilo obligatoria (la exige el centinela de F4):** siempre **bindear a un local**
en la misma línea que la llamada al normalizador, y recién después leer la propiedad.

```ts
const sev = safeSummary(run.summary).by_severity;   // OK — la línea contiene safeSummary(
{sev.danger}                                        // OK — `sev` ya es un Record completo
```

```ts
{safeSummary(run.summary).by_severity.danger}       // PROHIBIDO por estilo aunque sea seguro:
                                                    // encadenar hace ilegible el censo
```

**Edición 1 — `frontend/src/components/dbcompare/radarLogic.ts`**

- Agregar al tope: `import { safeBySeverity, safeSummary } from "./summaryShape";`
- `:31` → `const sev = safeBySeverity(cell.by_severity);` (reemplaza el `|| {…}` ad-hoc)
- `:60` → `const sev = safeSummary(r.summary).by_severity;` y **borrar el `!`** de `r.summary!`
- `:104` → `const sev = safeBySeverity(cell.by_severity);`
- El filtro de `:56` (`!!r.summary`) se **conserva**: una corrida sin summary sigue sin generar
  punto de tendencia (principio §3.4).

**Edición 2 — `frontend/src/components/dbcompare/RunsTimeline.tsx`**

Convertir el cuerpo del `.map` (`:23`) de expresión a bloque y bindear antes del JSX:

```tsx
{sorted.map((run) => {
  const sum = safeSummary(run.summary);
  const sev = sum.by_severity;
  return (
    <div key={run.run_id} ...>
      ...
      {run.summary && (
        <div className={styles.recency}>
          {sum.parity_score}% · 🔴{sev.danger} 🟠{sev.warn} 🔵{sev.info}
        </div>
      )}
      ...
    </div>
  );
})}
```

El guard `{run.summary && (…)}` de `:35` se **conserva** tal cual (§3.4).
Import nuevo: `import { safeSummary } from "./summaryShape";`

**Edición 3 — `frontend/src/components/dbcompare/EnvironmentRadar.tsx`**

- Agregar `safeBySeverity, safeSummary` al import (el archivo ya importa de `./radarLogic`;
  agregar una línea nueva `import { safeBySeverity, safeSummary } from "./summaryShape";`).
- `:144-147`, dentro de `showBaselineDiff`:

```ts
const sum = safeSummary(r.diff?.summary);
const sev = sum.by_severity;
setBaselineDiffText(
  `Drift vs baseline de ${alias}: ${sev.danger} danger / ${sev.warn} warn / ${sev.info} info (paridad ${sum.parity_score})`,
);
```

- `:215`: dentro del bloque del `.map` de columnas (que ya es un bloque, `:194-218`), justo
  **después** del `if (cell === null) return (…)` de `:200-206`, agregar:

```ts
const sevCell = safeBySeverity(cell.by_severity);
```

y reemplazar `:215` por `{sevCell.danger + sevCell.warn}`.

**Edición 4 — `frontend/src/components/dbcompare/svgMath.ts`**

```ts
import { safeByAction, safeBySeverity } from "./summaryShape";

export function severityCounters(diff: SchemaDiff): { severity: Severity; count: number }[] {
  const sev = safeBySeverity(diff.summary?.by_severity);
  return SEVERITY_ORDER.map((severity) => ({ severity, count: sev[severity] }));
}

export function actionCounters(diff: SchemaDiff): { action: DiffAction; count: number }[] {
  const act = safeByAction(diff.summary?.by_action);
  return ACTION_ORDER.map((action) => ({ action, count: act[action] }));
}
```

Nota: `diff.summary` está tipado no-nullable, pero el `?.` es TypeScript legal y es
precisamente la defensa contra el payload real que no respeta el tipo. No lo saques.

**Edición 5 — `frontend/src/components/dbcompare/SummaryHero.tsx`**

- Import nuevo: `import { safeSummary } from "./summaryShape";`
- Después del guard `if (!diff || !summary) return null;` (`:65`), reemplazar `:67`:

```ts
const sum = safeSummary(summary);
const score = sum.parity_score;
const objTypes = sum.by_object_type;
```

- `:145` → `.map((t) => \`${objTypes[t]} ${OBJECT_TYPE_LABEL[t]}\`)`
- `:147` → **solo cambia el identificador `summary` por `sum`; el resto de la línea NO se toca.**
  La línea real es `          comparados — {summary.objects_unchanged} sin diferencias` y queda
  `          comparados — {sum.objects_unchanged} sin diferencias`.
  (**C18:** el v2 escribía el reemplazo como `{sum.objects_unchanged} sin diferencias` a secas;
  aplicado al pie de la letra —que es lo que §1 exige— **borraba el prefijo `comparados — `** de
  la UI. Ningún cambio de copy es parte de este plan: ver §3.6 y §6 ítem 6.)

**Tests:** los de F0.1 (que pasan de rojo a verde) más un caso nuevo en el mismo archivo:

| Test | Aserción |
|---|---|
| `EnvironmentRadar: celda con by_severity vacío suma 0` | `safeBySeverity({}).danger + safeBySeverity({}).warn === 0` (cubre la forma que emite `api/db_compare_watch.py:153`) |

**Comandos (los 4, por archivo):**
```
npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts
npx vitest run src/components/dbcompare/radarLogic.test.ts
npx vitest run src/components/dbcompare/__tests__/svgMath.test.ts
npx vitest run src/components/dbcompare/__tests__/runHistory.test.ts
```

**Criterio de aceptación (binario):** los 4 comandos terminan en `0 failed`, y el primero —que
antes fallaba con `reading 'danger'`— ahora pasa. Los tests existentes de `svgMath` y
`radarLogic` NO cambian: si alguno hay que tocarlo, el fix cambió comportamiento y hay que
revisarlo.

**Flag:** ninguna (ver §3.1). **Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F3 — Borde de lectura del backend: ningún payload sale a medio formar

**Objetivo (1 frase):** normalizar el `summary` en memoria en las **dos** funciones por las que
salen todos los runs, sin tocar un solo byte del disco.
**Valor:** el radar, la lista y el detalle dejan de emitir formas parciales; F0.2 pasa a verde.

**Archivo:** `Stacky Agents/backend/services/dbcompare_runs.py`

**Función nueva** (colocarla junto a `_is_stale`, después de `dbcompare_runs.py:131`):

```python
import re as _re

_CANON_BY_SEVERITY = ("info", "warn", "danger")
_CANON_BY_ACTION = ("added", "removed", "changed")
_CANON_BY_OBJECT_TYPE = ("table", "view", "sequence")

# Plan 266 C16/C21 — gemela EXACTA de DECIMAL_RE en summaryShape.ts. Si cambia
# una, cambia la otra: lo verifica la tabla de verdad compartida de F1.5.
_DECIMAL_RE = _re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _count(value) -> int:
    """Entero >= 0. Cualquier cosa que no sea un número usable cuenta como 0.

    Plan 266 C21 — el guard de decimales sobre strings es obligatorio y NO es
    simétrico al del frontend por casualidad: `float("1_0")` en Python da 10.0
    (admite guiones bajos) mientras que `Number("1_0")` en JS da NaN. Al revés,
    `Number("0x10")` da 16 y `float("0x10")` lanza. Sin la MISMA regex de los
    dos lados, los normalizadores divergen en ambas direcciones (medido).

    Plan 266 C2 — el corte de `bool` va PRIMERO y es obligatorio: en Python
    `bool` es subclase de `int`, así que `int(float(True))` daría 1, mientras
    que el normalizador gemelo del frontend (`toCount`) da 0 para `true`. Sin
    este corte los dos lados divergen y la UI mostraría 1 con la flag ON y 0
    con la flag OFF. Lo verifica la tabla de verdad compartida de F1.5.

    Plan 266 C1 — `OverflowError` va en el `except` y es obligatorio:
    `json.loads` acepta `Infinity` / `-Infinity` / `NaN` por default, y
    `int(float(float("inf")))` lanza OverflowError (NO TypeError ni
    ValueError). Sin capturarlo, un solo run con `Infinity` en disco haría
    que `list_runs()` LANCE y rompa la lista entera: el normalizador que
    existe para evitar la pantalla rota sería el que la causa.
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, str) and not _DECIMAL_RE.match(value.strip()):
        return 0
    try:
        n = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0
    return n if n > 0 else 0


def _normalize_summary(summary):
    """Plan 266 — forma canónica del summary, SOLO EN MEMORIA.

    `None` se preserva como `None`: una corrida `running` no tiene resumen y
    fabricar ceros haría que la UI muestre '0 danger' para algo que todavía no
    comparó nada (mentira, no defensa).
    """
    if not isinstance(summary, dict):
        return None if summary is None else summary
    out = dict(summary)
    for key, canon in (
        ("by_severity", _CANON_BY_SEVERITY),
        ("by_action", _CANON_BY_ACTION),
        ("by_object_type", _CANON_BY_OBJECT_TYPE),
    ):
        src = out.get(key)
        src = src if isinstance(src, dict) else {}
        out[key] = {k: _count(src.get(k)) for k in canon}
    return out
```

**Asimetría deliberada con el frontend (decisión declarada, C9 — NO la "mejores"):**
`_normalize_summary` toca **solo los 3 mapas** y deja `parity_score`, `objects_total` y
`objects_unchanged` **crudos**, mientras que `safeSummary` del frontend **sí** los normaliza
(`toScore` / `toCount`). Es a propósito y no es un bug: el backend solo **rellena claves
ausentes de los mapas**, nunca reescribe un valor que ya es correcto. `parity_score` es el único
campo float del summary (`dbcompare_diff.py:329` hace `round(..., 1)`); coercionarlo en el
backend cambiaría un dato bueno y rompería el control positivo
`test_list_runs_no_altera_summary_completo`. El frontend completa la normalización de esos tres
campos escalares en el render (F2), que es donde importa. Quien "arregle" esta asimetría tiene
que romper ese test — y no debería.

**Cableado (2 funciones, 3 normalizaciones, todo gateado por la flag):**

1. `get_run` (`dbcompare_runs.py:316-323`) — antes del `return run`. **Normaliza DOS summaries**
   (corrección C4):

```python
def get_run(run_id: str) -> dict | None:
    run = _read_run(run_id)
    if run is None:
        return None
    if _is_stale(run):
        run = dict(run)
        run["stale"] = True
    if getattr(_config.config, "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", True):
        run = dict(run)
        run["summary"] = _normalize_summary(run.get("summary"))
        # Plan 266 C4 — la copia ANIDADA. `get_run` devuelve el run COMPLETO,
        # `diff` incluido (a diferencia de `list_runs`, que lo saca en :336).
        # SummaryHero.tsx:49-50 lee `run.diff` y se lo pasa a
        # svgMath.severityCounters/actionCounters (svgMath.ts:43 y :47), que son
        # las violaciones #7 y #8 del censo: sin esto seguirían recibiendo el
        # summary sin normalizar AUN CON LA FLAG ON. Copia superficial: no toca
        # el disco (lo prueba test_get_run_no_reescribe_el_archivo_en_disco).
        inner = run.get("diff")
        if isinstance(inner, dict):
            inner = dict(inner)
            inner["summary"] = _normalize_summary(inner.get("summary"))
            run["diff"] = inner
    return run
```

2. `list_runs` (`dbcompare_runs.py:326-340`) — después de armar `meta` en `:336`:

```python
        meta["stale"] = _is_stale(run)
        if getattr(_config.config, "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", True):
            meta["summary"] = _normalize_summary(meta.get("summary"))
        runs.append(meta)
```

**Import de config (afirmativo, ya verificado — no hay nada que decidir):**
`dbcompare_runs.py` **NO** importa config hoy. `dbcompare_runs.py:20-28` importa `json`, `os`,
`threading`, `time`, `datetime`, `runtime_paths.data_dir` y
`services.dbcompare_diff` / `registry` / `snapshot`, y nada más. Agregar **exactamente** la línea

```python
import config as _config
```

junto a los imports del tope del archivo, **inmediatamente después de**
`from runtime_paths import data_dir`.

La lectura se hace SIEMPRE por `getattr(_config.config, "…", True)` — **la instancia
`_config.config`, nunca el módulo** (gotcha conocido de la casa: `getattr` sobre el módulo
devuelve el default y mata la rama OFF, dejando la flag inerte). Precedente del idiom de
**lectura**, en esta misma familia de archivos: `backend/services/dbcompare_masking.py:207-208` →
`getattr(_config.config, "STACKY_DB_COMPARE_MASKING_ENABLED", False)`.

**Precisión (C19):** ese precedente acredita la **lectura**, no la **colocación** del import. En
`dbcompare_masking.py:206` el `import config as _config` está **dentro de la función**, no en el
tope del archivo; el v2 lo citaba como "precedente exacto" de un import de módulo y no lo es.
Acá el import va igual en el tope, y es seguro: verificado que `config.py` importa **solo**
`logging`, `os`, `pathlib`, `dotenv` y `runtime_paths` (`config.py:1-6`) — no importa `services`,
así que no hay ciclo. Y como se lee `_config.config` **en cada llamada** (no se captura el valor
al importar), un `importlib.reload(config)` en los tests sigue viéndose reflejado.

**Efecto colateral BUENO y verificado:** `backend/api/db_compare_watch.py:145` alimenta las
celdas del radar desde `dbcompare_runs.list_runs(200)`, y en `:153` hace
`(meta["summary"] or {}).get("by_severity") or {}`. Con la normalización en `list_runs`, ese
`or {}` deja de dispararse y la celda ya nunca lleva `by_severity: {}`.
**`api/db_compare_watch.py` NO se modifica** en este plan. **Ojo (C5):** este efecto colateral
cubre la ruta `/radar` (`db_compare_watch.py:145-161`) y **solo** esa. La otra ruta del mismo
archivo, `/baseline-diff` (`:125-133`), no lee runs persistidos y por lo tanto **no** la toca
F3; su tratamiento está en §6 ítem 7.

**Flag nueva — SEIS lugares de cableado obligatorios (1 a 6) + un séptimo lugar donde
explícitamente NO se cablea (7):**

> **Regla de anclaje (C28).** Los números de línea de esta tabla se midieron el 2026-07-29 sobre
> `760ac455` y **derivan** cada vez que alguien toca esos archivos. **El símbolo manda; el número es
> orientativo.** Si el número no coincide, buscá el símbolo (`FLAG_REGISTRY`, `_CATEGORY_KEYS`,
> `_CURATED_DEFAULTS_ON`, `PLAIN_HELP`, `_REQUIRES_MAP_FROZEN`) — no "adaptes" la instrucción.

| # | Archivo | Qué agregar |
|---|---|---|
| 1 | `Stacky Agents/backend/config.py`, junto al bloque DB Compare (después de `:203`, la línea que cierra `STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES`) | ver bloque de abajo |
| 2 | `Stacky Agents/backend/services/harness_flags.py`, en `FLAG_REGISTRY`, junto al `FlagSpec` de `STACKY_DB_COMPARE_MASKING_ENABLED` (**`harness_flags.py:4255`** — el v3 decía `4196-4204`, que es el `FlagSpec` de otro plan: C28) | `FlagSpec` con `default=True`, `requires="STACKY_DB_COMPARE_ENABLED"` y **`group="comparador_bd"`** (el mismo `group` que sus 20 hermanas) |
| 3 | `Stacky Agents/backend/services/harness_flags.py`, en **`_CATEGORY_KEYS["comparador_bd"]`** (el dict se define en `:120`; esa categoría abre en `:454` y ahí está `STACKY_DB_COMPARE_MASKING_ENABLED` en `:464`) | la key |
| 4 | `Stacky Agents/backend/tests/test_harness_flags.py`, en `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`) | la key |
| 5 | `Stacky Agents/backend/services/harness_flags_help.py`, en `PLAIN_HELP` (`harness_flags_help.py:25`) | entrada `PlainHelp(what=…, on_effect=…, off_effect=…, example=…)` |
| **6** | **`Stacky Agents/backend/tests/test_harness_flags_requires.py`, en `_REQUIRES_MAP_FROZEN`** (el dict cierra en `:~322`; la última sección es "Costura de flags de la OLA 1") | **la arista `"STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED": "STACKY_DB_COMPARE_ENABLED",`** con su comentario `# Plan 266`. **OBLIGATORIA — ver el recuadro de abajo.** |
| 7 | — | **NO** se agrega campo a `GET /api/db-compare/health` (`backend/api/db_compare.py:71-91`): esta flag no gatea nada del frontend. Agregarlo sería ruido. |

> **La SEXTA pata no es opcional (C22 — BLOQUEANTE del v3).** `tests/test_harness_flags_requires.py`
> mantiene `_REQUIRES_MAP_FROZEN`, un mapa **congelado** de todas las aristas `requires` del
> registry, y en `:316` hace `assert actual == _REQUIRES_MAP_FROZEN` — **igualdad de conjuntos**,
> con reporte de `Extras` en `:318`. Medido el 2026-07-29: el archivo está en **`9 passed`**,
> `len(actual) == len(_REQUIRES_MAP_FROZEN) == 146`, y `actual == FROZEN` es `True`.
> Declarar `requires=` en la `FlagSpec` **sin** sumar la arista acá deja `Extras =
> ['STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED']` y el test **ROJO** — un gate que hoy está verde,
> roto por este plan. El v3 no mencionaba `_REQUIRES_MAP_FROZEN` ni una vez en 1972 líneas.
>
> **Profundidad 1 (R4) verificada, hay que declararla en el comentario:**
> `STACKY_DB_COMPARE_ENABLED` **no** declara `requires` (medido: `requires is None`, `default=True`),
> así que la arista nueva **no forma cadena**. Comentario exacto a poner arriba de la arista:
>
> ```python
>     # Plan 266: la forma garantizada del summary cuelga del master del Comparador
>     # (profundidad 1: STACKY_DB_COMPARE_ENABLED no declara `requires`, no hay cadena).
>     "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED": "STACKY_DB_COMPARE_ENABLED",
> ```

`config.py`:

```python
    # ── Plan 266 — Forma garantizada del summary de las corridas ─────────────
    # Default ON: normalización SOLO-LECTURA y en memoria del summary que sale por
    # list_runs/get_run. No escribe disco, no toca ningún sistema del operador, no
    # llama a ningún modelo: no cae en (A) quema de tokens en reposo ni en (B)
    # escritura en sistema real ⇒ ON. Curada en _CURATED_DEFAULTS_ON.
    # OFF = payload byte-idéntico a antes del plan 266 (kill-switch auditable).
    STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", "true"
    ).strip().lower() == "true"
```

`PLAIN_HELP` — **el contrato son SEIS reglas, no solo las longitudes.** El v3 solo hablaba de
topes; el archivo `tests/test_harness_flags_help.py` exige además formato y una denylist de jerga.
Las seis, con su anclaje, y el texto de abajo **verificado contra las seis ejecutando el contrato**:

| # | Regla | Anclaje | El texto de abajo |
|---|---|---|---|
| 1 | `what` ≥ 10 y ≤ **200** (NO 240 — C15); `on_effect` ≤ 240; `off_effect` ≤ 240; `example` ≤ 300 | `:47-51` | 132 / 109 / 122 / 166 ✔ |
| 2 | `on_effect` y `off_effect` empiezan **exactamente** con `"Si "` | `:59-60` | ✔ los dos |
| 3 | cero términos de `JARGON_DENYLIST` (incluye plural): `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime` | `:17-20`, `:70` | ✔ ninguno |
| 4 | cero keys `SCREAMING_SNAKE` citadas (`\b[A-Z]+_[A-Z0-9_]+\b`) | `:22`, `:72` | ✔ ninguna |
| 5 | cero referencias a fases de plan (`\bF\d`) | `:23`, `:74` | ✔ ninguna |
| 6 | la key debe existir en el registry (sin huérfanas) | `:38-41` | ✔ la agrega la pata 2 |

```python
    "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED": PlainHelp(
        what="Controla si el Comparador de BD completa los contadores faltantes del resumen de una comparación antes de mandárselos a la pantalla.",
        on_effect="Si la activás: una comparación vieja o interrumpida se ve con contadores en cero en vez de romper la pestaña.",
        off_effect="Si la apagás: el resumen viaja tal cual está guardado y una comparación incompleta puede romper la pestaña del Comparador.",
        example="Abrís una comparación hecha con una versión anterior de Stacky: con esto activado ves 0 danger / 0 warn / 0 info; apagado, la pestaña muestra el cartel rojo de error.",
    ),
```

**Tests:** los de F0.2 pasan a verde — incluidos los 4 de `_count` (`infinito`, `nan`,
`booleano`, `no_lanza_con_infinity`) y el T6 de la tabla de verdad compartida de F1.5, que
depende de `_count` y recién acá tiene con qué correr. Agregar en el mismo archivo:

| Test | Aserción |
|---|---|
| `test_flag_off_deja_el_payload_crudo` | con `monkeypatch.setattr(config.config, "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", False)`, `list_runs()[0]["summary"] == {"parity_score": 91.7}` (sin claves agregadas) |
| `test_flag_registrada_default_on` | `harness_flags._REGISTRY_INDEX["STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED"].default is True` y `harness_flags.categorize("STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED") == "comparador_bd"` (**C27**: el v3 asertaba `"capacidades_optin"`, donde no vive ninguna hija de DB Compare) |

**Comandos:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q
```
El segundo verifica el par `_CURATED_DEFAULTS_ON` ↔ `default=True`
(`test_declared_default_true_set`, `test_harness_flags.py:990`, y su recíproco
`test_default_known_only_for_curated` en `:1001` — **C28**: el v3 citaba `:965-983`, que es otro
test) y la bijección con `_CATEGORY_KEYS` (`:930`). El **tercero** es el gate de la SEXTA pata.

**Criterio de aceptación (binario):** los tres comandos en `0 failed`; el tercero **exactamente en
`9 passed`** (baseline medido hoy: `9 passed`; si baja a `8 passed, 1 failed`, falta la arista de la
pata 6).

**Cómo se valida la entrada de `PLAIN_HELP` — y cómo NO (C26).**
`tests/test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes** (baseline medido
2026-07-29: **`4 failed, 4 passed`**), así que "esperar verde" es insatisfacible. Y el comando que
proponía el v3 —`-q -k SUMMARY_SHAPE`— es un **falso verde**: ejecutado, devuelve
**`8 deselected in 0.19s` con exit code `0`**. Los 8 tests se llaman `test_plain_help_*`; `-k` filtra
por **nombre de test**, no por contenido, así que corre **CERO** tests y sale 0. Parece verde y no
mide nada. **Prohibido usarlo.**

El criterio correcto es **delta sobre el contrato real**:

```
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q
```

debe seguir dando **exactamente `4 failed, 4 passed`** —los mismos 4 tests
(`covers_all_registry_keys`, `fields_non_empty_and_bounded`, `on_off_start_with_si`,
`avoids_jargon_denylist`)—, y **ninguno** de los mensajes de fallo puede mencionar
`STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED`. Comando que lo verifica de forma binaria:

```
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q 2>&1 | findstr /C:"SUMMARY_SHAPE"
```

**No debe imprimir nada** (`findstr` sale con código 1 = sin coincidencias, que acá es el éxito). Si
imprime algo, la entrada nueva viola una de las seis reglas de la tabla de arriba.

**Flag:** `STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED` — **default ON**.
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno (opt-out disponible en la UI de flags, default ON).

---

### F3.5 — [ADICIÓN ARQUITECTO] Gate de cableado COMPLETO de la flag (A4)

**Objetivo (1 frase):** que las **seis** patas del cableado las verifique un test, no una tabla de
este documento.

**Por qué existe esta fase.** El bloqueante que hizo rechazar el v3 (C22) no fue un descuido
aislado: fue que **la receta de 6 patas vive en prosa** y el único que la audita es el juez. El
mismo error ya pasó en esta casa con otras flags. Un test de ~30 líneas convierte la receta en gate
ejecutable y hace imposible que la próxima flag de este plan (o un refactor) pierda una pata en
silencio. No es scope creep: es el guard de F3, la fase que agrega la flag.

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan266_flag_cableado.py`

Python puro, sin Flask, sin DB, sin red — corre igual en los 3 runtimes. Lee
`_CURATED_DEFAULTS_ON` y `_REQUIRES_MAP_FROZEN` **importándolos de los módulos de test donde viven**
(son constantes de test, no de producción), y el resto del registry de `services.harness_flags`.

```python
"""Plan 266 F3.5 (A4) — las SEIS patas del cableado de la flag, en un solo gate.

El v3 de este plan listaba CINCO y se olvidaba de `_REQUIRES_MAP_FROZEN`
(test_harness_flags_requires.py:316 es una igualdad de conjuntos), lo que ponía
en ROJO un gate que estaba verde. Este test existe para que esa clase de error
no dependa de que alguien lea una tabla.
"""
import config
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS, categorize
from services.harness_flags_help import PLAIN_HELP
from tests.test_harness_flags import _CURATED_DEFAULTS_ON
from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

KEY = "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED"
MADRE = "STACKY_DB_COMPARE_ENABLED"
```

| # | Test | Aserción |
|---|------|----------|
| 1 | `test_pata1_config_declara_el_atributo` | `hasattr(config.config, KEY)` y `getattr(config.config, KEY) is True` (default ON efectivo) |
| 2 | `test_pata2_flagspec_con_default_on_y_requires` | el `FlagSpec` de `KEY` existe en `FLAG_REGISTRY`, con `default is True`, `type == "bool"`, `requires == MADRE` y `group == "comparador_bd"` |
| 3 | `test_pata3_categoria_comparador_bd` | `KEY in _CATEGORY_KEYS["comparador_bd"]` y `categorize(KEY) == "comparador_bd"` (**C27**) |
| 4 | `test_pata4_curada_en_defaults_on` | `KEY in _CURATED_DEFAULTS_ON` |
| 5 | `test_pata5_tiene_ayuda_llana` | `KEY in PLAIN_HELP`, los 4 campos no vacíos, y `len(PLAIN_HELP[KEY].what) <= 200` |
| 6 | `test_pata6_arista_requires_congelada` | `_REQUIRES_MAP_FROZEN.get(KEY) == MADRE` — **el que faltaba** |
| 7 | `test_profundidad_1_la_madre_no_declara_requires` | el `FlagSpec` de `MADRE` tiene `requires is None` ⇒ R4 cumplido, no hay cadena |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan266_flag_cableado.py -q`
**Criterio de aceptación (binario):** `0 failed`, 7 tests.
**Nace ROJO en 6 de 7 antes de F3** (la flag no existe todavía) y pasa a verde cuando F3 completa
las seis patas. Ese rojo es deliberado: es la reproducción del bloqueante C22.
**Registro:** este archivo también va en las **dos** listas del arnés (§F6.1).
**Flag:** ninguna (es un test). **Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F4 — Centinela: el patrón no vuelve por la puerta de atrás

**Objetivo (1 frase):** un ratchet que falla si alguien vuelve a leer `by_severity` /
`by_action` / `by_object_type` sin pasar por `summaryShape.ts`.
**Valor:** F2 arregla los 8 casos de hoy; F4 arregla el caso 9 que todavía no existe.

**Archivo nuevo:** `Stacky Agents/frontend/src/__tests__/dbcompareSummaryShapeRatchet.test.ts`
(mismo directorio y patrón que los 8 ratchets de frontend ya existentes; el más cercano es
`devopsPollingRatchet.test.ts`, del que se copia la estructura de censo + controles negativos).

#### F4.1 — Alcance EXACTO

- Raíz: `frontend/src/components/dbcompare/`, **recursivo**.
- Extensiones: `.ts` y `.tsx`.
- Excluidos: cualquier ruta que matchee `/\.test\.tsx?$/` o que contenga un segmento
  `__tests__`.
- `ALLOWLIST: string[] = []` — **vacía a propósito y verificado**: el único archivo que
  legítimamente toca esas claves es `summaryShape.ts`, y está escrito con corchetes y literal
  de string (`src["by_severity"]`), forma que **no** matchea ninguna de las dos reglas.

#### F4.2 — Las DOS reglas (una sola no alcanza)

```ts
// R1 — acceso profundo: el mapa leído como objeto, con punto o con corchete.
const R1 = /by_(severity|action|object_type)\s*[.[]/;

// R2 — lectura directa del contenedor: el mapa sacado de `.summary` (con o sin `!`).
const R2 = /\.summary\s*!?\s*\.by_(severity|action|object_type)/;

// EXENCIÓN (misma línea): la lectura pasa por el normalizador.
const EXENTO = ["safeSummary(", "safeBySeverity(", "safeByAction(", "safeByObjectType("];
```

R1 sola **no alcanza**: `radarLogic.ts:60` es `const sev = r.summary!.by_severity;` — después
del identificador viene `;`, no `.` ni `[`, así que R1 no lo ve. Y ese es justamente el
crash reportado. R2 lo caza.
R2 sola **tampoco**: `EnvironmentRadar.tsx:215` es `cell.by_severity.danger` — no hay
`.summary` en la línea. R1 lo caza.

Una línea es violación si matchea R1 **o** R2 **y** no contiene ninguna cadena de `EXENTO`.

#### F4.3 — Tests del archivo

| # | Test | Aserción |
|---|------|----------|
| 1 | `no hay accesos profundos sin guarda en dbcompare/` | `censo()` devuelve `[]` |
| 2 | `el detector encuentra las 8 formas históricas` | contra el fixture de F4.4, `violaciones(FIXTURE_HISTORICO)` tiene **8** entradas |
| 3 | `R2 caza el non-null assertion` | `violaciones('const sev = r.summary!.by_severity;')` → 1 |
| 4 | `R1 caza el acceso con punto` | `violaciones('{cell.by_severity.danger}')` → 1 |
| 5 | `R1 caza el acceso computado` | `violaciones('summary.by_object_type[t]')` → 1 |
| 6 | `la forma normalizada NO es violación` | `violaciones('const sev = safeSummary(run.summary).by_severity;')` → 0 |
| 7 | `la declaración de tipo NO es violación` | `violaciones('  by_severity: Record<Severity, number>;')` → 0 |
| 8 | `el literal de objeto NO es violación` | `violaciones('by_severity: { info: 0, warn: 0, danger: 0 },')` → 0 |
| 9 | `la lectura por corchete con literal de string NO es violación` | `violaciones('const src = raw["by_severity"];')` → 0 |
| 10 | `el guard con \|\| NO es violación` | `violaciones('const sev = cell.by_severity \|\| EMPTY_BY_SEVERITY;')` → 0 |
| 11 | `la ALLOWLIST está vacía` | `expect(ALLOWLIST).toEqual([])` |
| 12 | `el censo mira al menos 45 archivos` | `archivos().length >= 45` — control anti-censo-vacío: si un refactor mueve la carpeta, el test 1 pasaría trivialmente |

**Calibración del test 12 (corrección C6):** el v1 pedía `>= 12` y hoy hay **57** archivos
`.ts`/`.tsx` no-test en `frontend/src/components/dbcompare/` — con ese umbral se podían borrar
45 archivos y el control seguía verde, o sea que no protegía de nada (4,7× por debajo de la
realidad). El umbral es `>= 45`, y el test lleva este comentario textual:

```ts
// Censado 2026-07-27: 57 archivos .ts/.tsx no-test en components/dbcompare/.
// El margen (45) tolera borrados legítimos de archivos sueltos, NO un refactor
// que mueva la carpeta y deje el censo vacío (que es lo que este test caza).
```

El test 2 usa este fixture, con **las 8 expresiones de la §2.3** (una por línea), embebido como
string en el archivo de test (no como archivo aparte).

**C32 — no es copia *textual* de las líneas del árbol, y no hace falta que lo sea.** El v3 lo
declaraba "copia textual" y es falso: la línea real de `RunsTimeline.tsx:37` es
`{run.summary.parity_score}% · 🔴{run.summary.by_severity.danger} 🟠` (con emojis y `parity_score`).
Lo que importa es que cada línea del fixture **contenga la expresión prohibida**, y eso está
verificado ejecutando R1/R2 contra las 8 filas de abajo: dan **8** detecciones, una por línea. No
metas los emojis: agregan ruido y ninguna regla los mira.

```ts
const FIXTURE_HISTORICO = [
  'const sev = r.summary!.by_severity;',                                       // radarLogic.ts:60
  '{run.summary.by_severity.danger}',                                          // RunsTimeline.tsx:37
  '{run.summary.by_severity.warn} {run.summary.by_severity.info}',             // RunsTimeline.tsx:38
  'const sev = r.diff.summary.by_severity;',                                   // EnvironmentRadar.tsx:144
  '{(cell.by_severity.danger || 0) + (cell.by_severity.warn || 0)}',           // EnvironmentRadar.tsx:215
  '.map((t) => `${summary.by_object_type[t]} ${OBJECT_TYPE_LABEL[t]}`)',       // SummaryHero.tsx:145
  'return SEVERITY_ORDER.map((s) => ({ s, count: diff.summary.by_severity[s] }));', // svgMath.ts:43
  'return ACTION_ORDER.map((a) => ({ a, count: diff.summary.by_action[a] }));',     // svgMath.ts:47
].join('\n');
```

Esto reemplaza al "ROJO primero" que este archivo no puede tener (F2 ya limpió el censo cuando
llega F4): el detector se prueba contra el bug real, no contra un caso inventado.

#### F4.4 — Por qué NO puede tener falsos positivos masivos (justificación exigida)

1. **R1 exige el identificador pegado a `.` o `[`.** Eso es, por construcción, la forma de
   *desreferenciar el mapa*. Las formas benignas no matchean, y están verificadas en el árbol
   actual:
   - declaración de tipo: `dbcompareTypes.ts:106-108` (`by_severity: Record<Severity, number>;`)
     y `radarTypes.ts:16` / `:31` → después del identificador viene `:` ⇒ **no matchea**.
   - literal de objeto: `radarLogic.ts:31` (`|| { info: 0, warn: 0, danger: 0 }`) ⇒ el
     identificador está antes del `||`, seguido de espacio ⇒ **no matchea**.
   - lectura guardada: `cell.by_severity || …` ⇒ el punto está **antes**, no después ⇒ **no matchea**.
2. **R2 exige `.summary` y `.by_*` contiguos** (solo espacios o `!` en el medio). La forma
   normalizada `safeSummary(r.summary).by_severity` tiene un `)` entre medio ⇒ **no matchea**
   (y además está exenta por nombre).
3. **El alcance es una sola carpeta de producto**, no `src/**`. Nada del motor de flags, del
   runtime, ni del resto de la UI entra al censo. (Precedente: un centinela textual masivo ya
   rompió el motor de flags en esta casa. Este no puede: no lo mira.)
4. **La exención es por nombre de función, no por comentario ni por `eslint-disable`.** No se
   puede silenciar escribiendo prosa; hay que llamar al normalizador de verdad.
5. **El archivo del ratchet vive en `frontend/src/__tests__/`, fuera del alcance escaneado**, así
   que sus propias regex y su fixture no se auto-detectan. Gotcha de la casa evitado por diseño.
6. **Riesgo residual asumido y declarado:** un comentario o un string dentro de
   `frontend/src/components/dbcompare/**` que contenga literalmente `by_severity.` daría rojo.
   Es aceptable y **deseable**: el arreglo es reescribir la prosa (p. ej. "el mapa `by_severity`"),
   nunca aflojar el gate.

**Comando:** `npx vitest run src/__tests__/dbcompareSummaryShapeRatchet.test.ts`
**Criterio de aceptación (binario):** `0 failed`, 12 tests.
**Flag:** ninguna (un test no se gatea).
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F5 — `PageErrorBoundary` accionable: superficie, componente y stack copiable

**Objetivo (1 frase):** que el próximo error de render diga **dónde** pasó, no solo **qué** dijo.
**Valor:** esta incidencia costó una investigación completa porque el cartel solo traía el mensaje.

#### F5.1 — Módulo puro nuevo (lo testeable)

**Archivo nuevo:** `Stacky Agents/frontend/src/components/errorBoundaryDiagnostics.ts`

```ts
// Plan 266 F5 — Lógica pura del diagnóstico del boundary (testeable sin RTL/jsdom).

/** Primer componente del componentStack de React. `null` si no se puede extraer. */
export function firstComponentFromStack(stack: string | null | undefined): string | null;

/** Texto determinista para el portapapeles. Sin timestamps implícitos: el reloj entra por parámetro. */
export function buildDiagnosticText(input: {
  surface: string;
  message: string;
  componentName: string | null;
  stack: string | null;
  iso: string;
}): string;

/** Línea corta para el Centro de Actividad. */
export function buildActivityBody(surface: string, componentName: string | null, message: string): string;

/** Cotas de datos personales (C30). Exportadas para que el test las fije, no las adivine. */
export const MAX_MESSAGE_CHARS: number;   // 500
export const MAX_STACK_CHARS: number;     // 4000
```

**Cotas obligatorias (C30 — datos personales, NO cosmético).** El Comparador trabaja contra bases
de datos **reales**: un `message` de error puede arrastrar un valor de fila, y el `body` que publica
`buildActivityBody` queda en `localStorage` **para siempre**
(`frontend/src/services/activityCenter.ts:35`). Por eso:

- `MAX_MESSAGE_CHARS = 500` y `MAX_STACK_CHARS = 4000`, **exportadas** (no números mágicos adentro).
- `buildActivityBody` y `buildDiagnosticText` truncan `message` a `MAX_MESSAGE_CHARS` y `stack` a
  `MAX_STACK_CHARS`, agregando el sufijo literal `" …[truncado]"` cuando truncan (así el operador
  sabe que falta texto y no cree que el error era corto).
- Nada más entra al texto: **solo** los 5 campos nombrados. Está prohibido meter el run, el diff,
  el payload de la respuesta o cualquier objeto de dominio — ni "por conveniencia". El test lo fija.

Semántica:

- `firstComponentFromStack`: toma la **primera** línea que matchee
  `/^\s*(?:at|in)\s+([A-Za-z0-9_$.]+)/m` y devuelve el grupo 1. Si `stack` es
  `null`/`undefined`/`""` o ninguna línea matchea → `null`.
  Casos: `"\n    in RunsTimeline (at DbComparePage.tsx:81)"` → `"RunsTimeline"`;
  `"    at SummaryHero\n    at DbComparePage"` → `"SummaryHero"`;
  `"basura sin formato"` → `null`; `""` → `null`; `undefined` → `null`.

  **Limitación conocida y declarada (C11), asumida a propósito:** en un build de producción
  **minificado**, el `componentStack` trae nombres **mangleados** (`t`, `Wr`, …), así que
  `firstComponentFromStack` devolverá esa basura en vez del nombre real. No se cambia el diseño
  por esto: (a) el operador corre Stacky en **dev/local**, que es donde el nombre sale real;
  (b) aun mangleado, el **stack completo copiable** —que es el 80% del valor de F5— sigue
  sirviendo igual; (c) resolverlo bien exigiría sourcemaps en runtime, que es un plan aparte y
  mucho más caro que el problema. Registrado también como R10 en §5.
- `buildActivityBody`: `"<surface> · <componentName>: <message>"`; si `componentName` es
  `null` → `"<surface>: <message>"`. Nunca lanza; `message` vacío → `"error desconocido"`.
- `buildDiagnosticText`: exactamente estas 5 líneas, en este orden, unidas con `\n`:
  ```
  Stacky — error de render
  Superficie: <surface>
  Componente: <componentName ?? "desconocido">
  Mensaje: <message>
  Cuándo: <iso>
  ```
  seguidas de `"\n\nStack:\n" + stack` **solo si** `stack` es un string no vacío.
  Determinista: mismos argumentos ⇒ mismo string (por eso `iso` entra por parámetro y no
  se llama a `new Date()` adentro).

**Archivo de test nuevo:**
`Stacky Agents/frontend/src/components/__tests__/errorBoundaryDiagnostics.test.ts`
Casos: los 5 de `firstComponentFromStack`, los 3 de `buildActivityBody` (con y sin componente,
mensaje vacío), y 3 de `buildDiagnosticText` (con stack, sin stack, con `componentName: null`),
**más los 4 de la cota (C30)**:

| Test | Aserción |
|---|---|
| `buildDiagnosticText trunca un stack gigante` | con `stack = "x".repeat(20000)`, el resultado tiene `length < MAX_STACK_CHARS + 400` y **contiene** `…[truncado]` |
| `buildDiagnosticText trunca un mensaje gigante` | con `message = "y".repeat(5000)`, el bloque `Mensaje:` no supera `MAX_MESSAGE_CHARS` + el sufijo |
| `buildActivityBody trunca el mensaje` | idem sobre el `body` que va a `localStorage` |
| `buildDiagnosticText no filtra nada más que los 5 campos` | dado `{surface:"s", message:"m", componentName:"c", stack:"k", iso:"i"}`, el resultado, quitadas las 5 etiquetas fijas y esos 5 valores, **no contiene** ninguna otra subcadena de más de 3 caracteres que no sea de la plantilla — control anti-filtración: si alguien "enriquece" la función con el run, este test se pone rojo |

Mínimo **15 tests**.

**Comando:** `npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts`

#### F5.2 — Cambios en `PageErrorBoundary.tsx`

**Archivo:** `Stacky Agents/frontend/src/components/PageErrorBoundary.tsx`

- `Props` (`:12-16`): agregar `surface?: string;` — **opcional**, para no romper los call-sites
  existentes, que son **2** (`App.tsx:346` y `App.tsx:495`, ambos
  `<PageErrorBoundary resetKey={tab}>{pages}</PageErrorBoundary>`; la tercera aparición del
  símbolo es el `import` de `App.tsx:33`). **C17:** el v2 decía "los 14 call-sites" — número
  inventado; el fix no cambia, pero un plan que se declara verificado no puede traer cifras que
  no lo están. Ninguno de los 2 se modifica en este plan: `surface` es opcional justamente para
  eso. La superficie efectiva es `this.props.surface ?? this.props.resetKey`
  (el `resetKey` ya es el tab activo, ver el comentario de `:13`).
- `State` (`:18-21`): agregar `componentName: string | null;` y `stack: string | null;`
  (inicializados en `null` en `:24` y reseteados en `:47` y `:52`).
- `componentDidCatch` (`:30-43`):
  ```ts
  const stack = info?.componentStack ?? null;
  const componentName = firstComponentFromStack(stack);
  this.setState({ componentName, stack });
  // console.error se conserva tal cual (:32)
  publishActivity({
    key: `error:${Date.now()}`,
    kind: "error",
    severity: "error",
    title: "Error en la UI",
    body: buildActivityBody(this.props.surface ?? this.props.resetKey, componentName, String(error?.message || error)),
    ts: Date.now(),
  });
  ```
  `body` sigue siendo un `string` ⇒ el contrato de `publishActivity` no cambia.
- `render()` (`:55-72`) — **el `<h2>` de `:60` NO se toca** (lo asserta
  `components/__tests__/PageErrorBoundary.test.tsx:29`), y el `<p>` del mensaje de `:61-63`
  tampoco (lo asserta `:30`). Se **agrega**, entre el `<p>` del hint (`:64-66`) y el botón
  Reintentar (`:67-69`):

  ```tsx
  <p className={styles.origin}>
    {this.props.surface ?? this.props.resetKey}
    {this.state.componentName ? ` · ${this.state.componentName}` : ""}
  </p>
  {this.state.stack && (
    <details className={styles.details}>
      <summary>Detalle técnico</summary>
      <pre className={styles.stack}>{this.state.stack}</pre>
    </details>
  )}
  ```

  y, junto al botón Reintentar:

  ```tsx
  <button type="button" className={styles.secondaryAction} onClick={this.handleCopy}>
    ⧉ Copiar diagnóstico
  </button>
  ```

  con

  ```ts
  handleCopy = (): void => {
    void copyText(
      buildDiagnosticText({
        surface: this.props.surface ?? this.props.resetKey,
        message: String(this.state.error?.message || this.state.error || ""),
        componentName: this.state.componentName,
        stack: this.state.stack,
        iso: new Date().toISOString(),
      }),
    );
  };
  ```

  e import nuevo `import { copyText } from "../services/copyService";`.

> **C25 (BLOQUEANTE del v3) — PROHIBIDO `navigator.clipboard.writeText` acá.** El v3 escribía
> `void navigator.clipboard?.writeText(…)` directamente en `PageErrorBoundary.tsx`, y eso **pone en
> ROJO** `frontend/src/__tests__/copyDebtRatchet.test.ts` (Plan 194 F5), que congela **por archivo**
> la cantidad de escrituras directas al portapapeles (`/\.writeText\s*\(/`) bajo `src/` y declara en
> su encabezado: *"El único lugar legítimo de escritura al portapapeles es services/copyService"*.
> Medido el 2026-07-29: el ratchet está **VERDE (`3 passed`)**, su baseline `copyByFile` tiene 11
> entradas y **`components/PageErrorBoundary.tsx` NO figura** ⇒ su cupo es **0**. Una escritura
> nueva ahí es deuda nueva sobre cupo 0 ⇒ rojo. **Regenerar el baseline NO es opción** (solo puede
> bajar, y un DoD que regenera un baseline de ratchet es un defecto en esta casa).
>
> El módulo canónico `frontend/src/services/copyService.ts` ya existe y es **estrictamente mejor**:
> `copyText(text): Promise<CopyResult>` intenta `navigator.clipboard.writeText` y **cae a
> `document.execCommand`** si el permiso se niega o el contexto no es seguro (el `?.` del v3
> simplemente no copiaba, en silencio). Verificado: **no está detrás de ninguna flag**, y expone
> `COPY_TOAST_SUCCESS` / `COPY_TOAST_ERROR` si más adelante se quiere avisar. Esto es la regla de
> reuso de la casa aplicada, no una preferencia de estilo.

  El nombre `Copiar diagnóstico` **no colisiona** con el `getByRole("button", { name: /reintentar/i })`
  de `PageErrorBoundary.test.tsx:46`.

- **CSS (C29 — el `uiDebtRatchet` congela HEX, no solo estilos inline):** agregar las 4 clases a
  `Stacky Agents/frontend/src/components/PageErrorBoundary.module.css`.

  Medido el 2026-07-29: el ratchet cuenta **colores hex por archivo** en `*.module.css`
  (`HEX_RE = /#[0-9a-fA-F]{3,8}\b/g`) y el baseline de `components/PageErrorBoundary.module.css` es
  **2** — exactamente los dos que ya tiene (`#fca5a5` en `.title`, `#fecaca` en `.action`). **Un solo
  hex nuevo lo pone en 3 y el gate en ROJO.** Y "usá tokens" a secas es otra trampa: la familia
  `--color-*` **no existe** en el tema (los reales son `--accent`, `--danger`, `--success`,
  `--border`, `--text-primary`, `--bg-panel`). Para no depender de ninguna de las dos cosas, las 4
  clases van **literales, con `rgba()` como el resto del archivo y CERO hex nuevo**:

  ```css
  .origin {
    margin: 0;
    font-size: 11px;
    letter-spacing: 0.02em;
    color: rgba(255, 255, 255, 0.35);
  }
  .details {
    margin-top: 4px;
    max-width: 640px;
    width: 100%;
    text-align: left;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.55);
  }
  .stack {
    margin: 6px 0 0;
    padding: 8px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(0, 0, 0, 0.25);
    font-size: 11px;
    line-height: 1.45;
    overflow: auto;
    max-height: 40vh;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .secondaryAction {
    margin-top: 8px;
    padding: 8px 18px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.06);
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    font-size: 13px;
  }
  .secondaryAction:hover { background: rgba(255, 255, 255, 0.12); }
  ```

  **CERO estilos inline** (`style={{…}}`) además: el `uiDebtRatchet` también los cuenta por archivo
  y `PageErrorBoundary.tsx` tiene cupo 0.

**Comandos (los TRES — el del portapapeles no estaba y es el que atrapa C25):**
```
npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts
```

**Criterio de aceptación (binario):** los tres en `0 failed` —el de copia **exactamente en
`3 passed`**, su baseline medido hoy—, `grep -c "Esta pestaña falló al renderizar"
src/components/PageErrorBoundary.tsx` = 1, y
`grep -c "navigator.clipboard" src/components/PageErrorBoundary.tsx` = **0**.

**Flag:** ninguna. Es diagnóstico **solo-lectura** de un error que ya ocurrió; la regla de la
casa dice que leer/mostrar/avisar va ON, y acá el "ON" es incondicional porque el fallback ya
existe y solo se enriquece.
**Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno (el botón está ahí cuando lo necesita; no hay nada que activar).

---

### F6 — Cierre: registro en el arnés y gates globales

**Objetivo (1 frase):** que el test backend nuevo quede bajo el arnés y que el árbol compile.
**Valor:** sin el registro, el meta-test del ratchet queda rojo y la cobertura se encoge en silencio.

#### F6.1 — Registrar el test backend en el arnés (DOS archivos, DOS formas distintas)

El v1 decía "agregar a `HARNESS_TEST_FILES` también en el `.ps1`" y "mirar cómo está declarada
la lista en cada uno y seguir su forma". Las dos cosas están mal: el `.ps1` **no contiene**
ninguna variable llamada `HARNESS_TEST_FILES`, y "mirar y seguir la forma" es exactamente la
inferencia que §1 prohíbe. Acá van las líneas **literales**, con su ancla y su forma exacta.
No hay nada que deducir. Son **TRES** archivos de test, no uno:
`test_plan266_summary_shape.py` (F0.2/F3), `test_plan266_flag_cableado.py` (F3.5) y
`test_plan266_harness_runner_paridad.py` (F6.5).

**(a) `Stacky Agents/backend/scripts/run_harness_tests.sh`** — la lista se declara en `:20` como
`HARNESS_TEST_FILES=(` y sus entradas van **DESNUDAS: sin comillas y sin coma**, así:

```
  tests/test_plan258_ledger_purge.py
```

Agregar las **tres** líneas al **FINAL del array**: inmediatamente después de
`  tests/test_plan242_runtime_parity.py` (`run_harness_tests.sh:883`, la **última** entrada real —
medido el 2026-07-29; el `)` está en `:884`), estas líneas **exactas**:

```
  tests/test_plan266_summary_shape.py
  tests/test_plan266_flag_cableado.py
  tests/test_plan266_harness_runner_paridad.py
```

(dos espacios de indentación, sin comillas, sin coma, sin nada más en la línea).

> **Ojo con el ancla (C23).** El v3 mandaba insertar después de
> `  tests/test_plan258_estanqueidad_arnes.py` (`:874`) llamándola "última entrada de la serie
> 253-258". Medido: `:874` es correcto para esa línea, pero **no es la última del array** — después
> vienen 9 entradas más y la última es `:883`. En el `.sh` la posición es indiferente (la regex del
> meta-test acepta la línea desnuda esté donde esté), pero se unifica al final para que la
> instrucción sea **la misma** que en el `.ps1`, donde la posición **sí** importa.

**(b) `Stacky Agents/backend/scripts/run_harness_tests.ps1`** — acá la variable se llama
`$HarnessTestFiles` (NO `HARNESS_TEST_FILES`) y se declara en `run_harness_tests.ps1:13` como
`$HarnessTestFiles = @(`.

> **C23 (BLOQUEANTE del v3) — la instrucción del v3 era inejecutable y su premisa de estilo era
> falsa. Los dos hechos, medidos el 2026-07-29 sobre `760ac455`:**
>
> 1. **El bloque que el v3 mandaba reemplazar NO existe.** `Contains('  "tests/test_plan258_
>    estanqueidad_arnes.py"' + newline + ')')` → **False**. La entrada del 258 está en **`:787`**
>    y **ya termina en coma**; la **última** entrada del array es **`:796`
>    `"tests/test_plan242_runtime_parity.py"`** (sin coma), y el `)` está en **`:797`** (el v3 decía
>    `:788`). O sea que la "regla general" del v3 —*la que era última recibe la coma que le
>    faltaba*— es falsa en las dos mitades: el 258 no es la última y ya tiene su coma.
>    Un implementador literal no encuentra el bloque, **la edición no ocurre**, el test nuevo nunca
>    entra al arnés (pérdida de cobertura en silencio) y el test 4 de F6.5 queda rojo.
> 2. **PowerShell NO exige coma entre elementos separados por salto de línea.** Verificado con el
>    parser real: `@("x.py"` + newline + `"y.py")` **parsea con 0 errores**, igual que el archivo
>    real completo, que tiene **207** entradas sin coma. La afirmación del v3 "las entradas
>    intermedias van entrecomilladas y con coma" es falsa para **206 de 623**.
>
> **Lo que sí se confirma es la premisa de C12:** una coma **colgante** antes del `)` es un
> `ParserError` real (`@("x.py",` + newline + `"y.py",` + newline + `)` → *"Falta una expresión
> después de ','"*). Por eso la entrada nueva va **sin** coma.

Entonces la edición es **UNA sola línea nueva**, no dos. Las entradas van entrecomilladas y con
dos espacios de indentación; la coma es **opcional** entre elementos y **prohibida** antes del `)`.

Agregar, **inmediatamente después** de la línea `  "tests/test_plan242_runtime_parity.py"`
(la ÚLTIMA entrada del array, `run_harness_tests.ps1:796`) y **antes** del `)` de `:797`, estas
**tres** líneas exactas, **ninguna con coma**:

```powershell
  "tests/test_plan266_summary_shape.py"
  "tests/test_plan266_harness_runner_paridad.py"
  "tests/test_plan266_flag_cableado.py"
```

**Regla general, sin nada que inferir:** *las entradas nuevas van al final del array, con dos
espacios de indentación, entre comillas dobles, y SIN coma. No se le agrega ni se le quita coma a
ninguna línea existente.* (Verificado con el parser: agregar entradas sin coma al final deja el
archivo parseando con 0 errores.)

(Las mismas tres, en su forma desnuda, van en el `.sh` — eso es el paso **(a)** de arriba. Las dos
formas son distintas y **ninguna se deriva de la otra**; ver el porqué más abajo.)

**Orden obligatorio:** esta fase va **AL FINAL**, después de que los tres archivos de test existan.
`tests/test_harness_ratchet_meta.py:79` es `test_ratchet_no_referencia_archivos_inexistentes`:
registrar una ruta antes de crear el archivo pone ese gate en ROJO (medido: hoy está en `4 passed`).

Lo verifica automáticamente el guard de F6.5 (que existe justamente porque el `.ps1` no tenía
**ningún** gate de sintaxis).

**Por qué las formas son distintas y no se pueden copiar entre archivos:** el meta-test parsea
**solo el `.sh`** — `backend/tests/test_harness_ratchet_meta.py:13` define
`_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"`, y `:21` usa la regex
`^\s*(tests/[\w/]+\.py)\s*$`, que exige la línea **desnuda**: una entrada entrecomillada
(`"tests/….py",`) **NO** sería reconocida y el meta-test quedaría rojo. El `.ps1` es un script
de PowerShell y necesita la sintaxis de array de PowerShell; pegarle la línea desnuda del `.sh`
lo rompe. Por eso hay dos líneas distintas y ninguna se deriva de la otra.

**NO** usar `harness_ratchet_allowlist.txt`: la allowlist es deuda y solo puede bajar
(`test_harness_ratchet_meta.py:69-76`).

#### F6.2 — Gate de tipos y build

```
npm run build     # desde Stacky Agents/frontend → tsc --noEmit && vite build
```

#### F6.3 — [ADICIÓN ARQUITECTO A5] Suite de cierre con BASELINE MEDIDO y criterio DELTA

**Por qué cambia.** El v3 listaba comandos y pedía "verde". Eso es insatisfacible en 2 de los
archivos (tienen rojos ajenos) e inauditable en los otros: un "pasó" sin número no distingue
"corrió y pasó" de "no corrió". Los números de la columna **HOY** se midieron ejecutando cada
comando el **2026-07-29** sobre `760ac455`, antes de tocar nada. El criterio es la columna
**DESPUÉS**: si un archivo empeora respecto de su baseline, el plan lo rompió; si un rojo ajeno
"desaparece", alguien tocó algo que no era de este plan.

| # | Comando (backend: desde `Stacky Agents/backend`) | HOY (medido) | DESPUÉS (exigido) |
|---|---|---|---|
| 1 | `pytest tests/test_plan266_summary_shape.py -q` | no existe | `0 failed` |
| 2 | `pytest tests/test_plan266_flag_cableado.py -q` | no existe | `0 failed`, 7 tests |
| 3 | `pytest tests/test_plan266_harness_runner_paridad.py -q` | no existe | `0 failed`, 4 tests |
| 4 | `pytest tests/test_harness_flags.py -q` | **56 passed** | `0 failed` (≥ 56 passed) |
| 5 | `pytest tests/test_harness_flags_requires.py -q` | **9 passed** | **`9 passed`** ← el gate de la SEXTA pata (C22) |
| 6 | `pytest tests/test_harness_ratchet_meta.py -q` | **4 passed** | `0 failed` |
| 7 | `pytest tests/test_harness_flags_help.py -q` | **4 failed, 4 passed** (ajenos) | **`4 failed, 4 passed`**, y `findstr /C:"SUMMARY_SHAPE"` sobre su salida **no imprime nada** (C26) |
| 8 | `pytest tests/test_error_fingerprints_catalog.py -q` | **3 failed, 5 passed** (ajenos) | **`3 failed, 5 passed`**; si sube a 4 o si `test_patrones_compilan` se pone rojo, la huella está mal (C13) |

| # | Comando (frontend: desde `Stacky Agents/frontend`) | HOY (medido) | DESPUÉS (exigido) |
|---|---|---|---|
| 9 | `npx vitest run src/components/dbcompare/summaryShape.test.ts` | no existe | `0 failed`, ≥31 tests |
| 10 | `npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts` | no existe | `0 failed` |
| 11 | `npx vitest run src/components/dbcompare/radarLogic.test.ts` | existe y pasa | `0 failed`, **sin tocar el archivo de test** |
| 12 | `npx vitest run src/components/dbcompare/__tests__/svgMath.test.ts` | existe y pasa | `0 failed`, **sin tocar el archivo de test** |
| 13 | `npx vitest run src/components/dbcompare/__tests__/runHistory.test.ts` | existe y pasa | `0 failed` |
| 14 | `npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts` | no existe | `0 failed`, ≥15 tests |
| 15 | `npx vitest run src/__tests__/dbcompareSummaryShapeRatchet.test.ts` | no existe | `0 failed`, 12 tests, censo `[]` |
| 16 | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` | verde | `0 failed` — el hex de `PageErrorBoundary.module.css` sigue en **2** (C29) |
| 17 | `npx vitest run src/__tests__/copyDebtRatchet.test.ts` | **3 passed** | **`3 passed`** ← el gate que atrapa C25; `PageErrorBoundary.tsx` **no** puede aparecer en el baseline |
| 18 | `npm run build` (`tsc --noEmit && vite build`) | verde | exit 0 |

**PROHIBIDO como parte de este plan:** `npm install` / `npm ci`, tocar `frontend/package.json`, y
**regenerar cualquier baseline de ratchet** (`COPY_DEBT_REGEN`, `UI_DEBT_REGEN` o equivalente). Los
baselines solo bajan; si un ratchet se pone rojo, el arreglo es el código, no el baseline.

#### F6.4 — [ADICIÓN ARQUITECTO] Registrar la huella de regresión del error

Este plan **mata una clase de error** (el crash de render por summary a medio formar) y el v1 no
dejaba huella. `Stacky Agents/docs/sistema/error_fingerprints.json` existe y es exactamente el
registro para eso (`schema_version: 1`, lista `fingerprints`, con los campos `id`, `title`,
`class`, `status`, `log_pattern`, `log_guarded`, `killed_by`, `killed_commit`, `date_resolved`,
`guard_test`, `evidence`, `note`).

**C13 — el esquema del catálogo NO admite `log_pattern: null` ni una entrada sin `self_test`.**
Verificado contra `backend/tests/test_error_fingerprints_catalog.py`:

- `:18` → `_REQUIRED = (…, "log_pattern", "log_guarded", "killed_by", "guard_test", "self_test")`
  y `:32-35` exige **todas** esas claves en **cada** huella.
- `:48-50` → `re.compile(fp["log_pattern"])` **sin guarda de `None`**. Con `log_pattern: null`
  eso es `re.compile(None)` ⇒ `TypeError`.
- `:53-59` → `fp["self_test"]["matches"]` / `["clean"]`, indexado directo.

Baseline **ejecutado** hoy sobre ese archivo: `3 failed, 5 passed`. Los 3 rojos
(`test_campos_obligatorios`, `test_status_enum`, `test_self_test_coherente`) son **ajenos y
preexistentes** —16 de las 42 huellas actuales ya no traen `self_test`—, pero
**`test_patrones_compilan` está VERDE** porque hoy **ninguna** huella tiene `log_pattern: null`.
La entrada del v2 lo habría puesto en rojo: un plan que mata una clase de error rompiendo el
gate del catálogo de errores.

El `log_pattern` de abajo **no contradice** `log_guarded: false`: el campo declara *cómo se
reconocería el error si apareciera en un texto*, y `log_guarded` declara si **el smoke de logs del
backend lo vigila** — que es lo que sigue siendo `false`, y por la razón correcta (esto pasa en el
navegador). El patrón es además el que aparece **textualmente en el Centro de Actividad** vía
`buildActivityBody` (F5), así que es reconocible de verdad, no un relleno para pasar el test.

Agregar al array `fingerprints` esta entrada, **literal** (solo se completa `killed_commit` al
implementar, con el SHA corto del commit del fix):

```json
{
  "id": "dbcompare-summary-shape-render-crash",
  "title": "Pantalla rota del Comparador de BD: lectura de by_severity sobre un summary a medio formar",
  "class": "frontend-render-crash",
  "status": "resolved",
  "log_pattern": "Cannot read propert(?:y|ies) of undefined \\(?reading '(danger|warn|info|added|removed|changed|table|view|sequence)'",
  "log_guarded": false,
  "self_test": {
    "matches": [
      "Cannot read properties of undefined (reading 'danger')",
      "Cannot read properties of undefined (reading 'added')"
    ],
    "clean": [
      "Comparador de BD: corrida finalizada sin diferencias",
      "Cannot read properties of undefined (reading 'foo')"
    ]
  },
  "killed_by": "plan-266",
  "killed_commit": "TODO-completar-al-implementar",
  "date_resolved": "2026-07-28",
  "guard_test": "frontend/src/__tests__/dbcompareSummaryShapeRatchet.test.ts",
  "evidence": [
    "frontend/src/components/dbcompare/radarLogic.ts:60",
    "frontend/src/components/dbcompare/RunsTimeline.tsx:37",
    "frontend/src/components/dbcompare/EnvironmentRadar.tsx:144",
    "frontend/src/components/dbcompare/EnvironmentRadar.tsx:215",
    "frontend/src/components/dbcompare/SummaryHero.tsx:145",
    "frontend/src/components/dbcompare/svgMath.ts:43",
    "frontend/src/components/dbcompare/svgMath.ts:47",
    "backend/services/dbcompare_runs.py:336"
  ],
  "note": "El operador veia 'Esta pestana fallo al renderizar / Cannot read properties of undefined'. El guard real es el ratchet, no un patron de log."
}
```

**Por qué `log_guarded: false` (justificación exigida, no un descuido):** esto es un `throw` en el
**render del navegador**. Lo atrapa `PageErrorBoundary` y termina en la consola del cliente y en
el Centro de Actividad — **nunca llega a un log del backend**. Un smoke de huellas que grepea
logs del servidor no podría verlo jamás, y declarar `log_guarded: true` sería afirmar una
protección que no existe (falso verde de catálogo). El guard verificable de esta huella es el
**ratchet de F4**, y por eso va en `guard_test`. Esa parte del v2 estaba bien y se conserva.

Lo que cambia (C13) es **`log_pattern`**: pasa de `null` a un patrón real. `null` no era una
declaración honesta sino un `TypeError` en `test_patrones_compilan`. El patrón describe el texto
que el error produce donde **sí** es observable (consola del navegador y Centro de Actividad, vía
`buildActivityBody` de F5), y la alternancia está acotada a las 9 claves de los 3 mapas canónicos
para que no cace cualquier `reading '…'` ajeno — lo prueba el `clean` con `'foo'`.

**Criterio de aceptación (binario) — dos comandos, no uno:**

```
.venv\Scripts\python.exe -c "import json;d=json.load(open(r'../docs/sistema/error_fingerprints.json',encoding='utf-8'));print(sum(1 for f in d['fingerprints'] if f['id']=='dbcompare-summary-shape-render-crash'))"
.venv\Scripts\python.exe -m pytest tests/test_error_fingerprints_catalog.py -q
```

El primero imprime `1`. El segundo **debe terminar exactamente en `3 failed, 5 passed`**, con los
3 fallos siendo **los mismos 3 de hoy** (`test_campos_obligatorios`, `test_status_enum`,
`test_self_test_coherente`), que son rojos **ajenos y preexistentes** —16 de las 42 huellas
actuales no traen `self_test`— y **no** los causa este plan. Baseline medido el 2026-07-28 antes
de tocar nada: `3 failed, 5 passed`.

**Si aparece un 4.º fallo, o si `test_patrones_compilan` pasa a rojo, la entrada nueva está mal y
NO se sigue.** Ese es el gate real de esta fase: el conteo de fallos no puede subir de 3.
La entrada de arriba fue validada contra los 5 tests del catálogo antes de escribirla acá
(compila, `self_test` coherente, `_REQUIRED` completo, `status` en el enum, sin bytes de control).

#### F6.5 — [ADICIÓN ARQUITECTO] Guard del runner de PowerShell: sintaxis y paridad con el `.sh`

**Por qué existe esta fase.** El encabezado de `run_harness_tests.ps1:6` dice textualmente
*"La lista es un RATCHET: solo crece. Mantener en sync con run_harness_tests.sh"* — y **nadie lo
verifica**. El meta-test del arnés parsea **solo el `.sh`**
(`backend/tests/test_harness_ratchet_meta.py:13` → `_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"`).
El `.ps1` no tiene **ningún** gate: ni de sincronización ni de **sintaxis**. Por eso el error C12
—una coma colgante que tira abajo el archivo entero— habría llegado a main en silencio, y solo se
habría descubierto la próxima vez que un operador corriera el arnés en Windows.

Esto no es scope creep: es el guard de la fase F6.1 de este mismo plan, que es la fase que toca
esos dos archivos.

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan266_harness_runner_paridad.py`

Python puro: **no invoca `pwsh` ni PowerShell**, solo lee los dos archivos como texto. Así corre
igual en los 3 runtimes, en Linux y en CI sin PowerShell instalado — no hace falta fallback
porque no hay capacidad diferencial en juego.

```python
"""Plan 266 F6.5 — el runner .ps1 del arnés no tiene gate propio. Este es.

El .ps1 dice "mantener en sync con run_harness_tests.sh" y nadie lo verificaba;
el meta-test (test_harness_ratchet_meta.py:13) parsea SOLO el .sh.
"""
import re
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_SH = _SCRIPTS / "run_harness_tests.sh"
_PS1 = _SCRIPTS / "run_harness_tests.ps1"

_SH_ENTRY = re.compile(r"^\s*(tests/[\w/]+\.py)\s*$", re.M)
_PS1_ENTRY = re.compile(r'^\s*"(tests/[\w/]+\.py)"\s*,?\s*$', re.M)


def _sh_files() -> set[str]:
    return set(_SH_ENTRY.findall(_SH.read_text(encoding="utf-8")))


def _ps1_files() -> set[str]:
    return set(_PS1_ENTRY.findall(_PS1.read_text(encoding="utf-8")))
```

| # | Test | Aserción |
|---|------|----------|
| 1 | `test_ps1_sin_coma_colgante` | **el corazón de C12.** Implementación **literal** (C33 — nada que inferir): `lineas = _PS1.read_text(encoding="utf-8").splitlines()`; para cada `i` tal que `lineas[i].strip() == ")"`, retroceder al índice `j` de la última línea **no vacía** anterior y assertar `not lineas[j].rstrip().endswith(",")`. Medido hoy: hay **exactamente 1** línea que es solo `)` (`:797`) y su anterior (`:796`) **no** termina en coma ⇒ **nace verde**. |
| 2 | `test_ps1_es_subconjunto_del_sh` | `_ps1_files() - _sh_files() == set()` — invariante **medido y cierto hoy** (2026-07-29: **623** en el `.ps1`, **687** en el `.sh`, diferencia `.ps1 − .sh` = ∅). Cazaría un archivo agregado al `.ps1` y olvidado en el `.sh`, que es el que rompe el meta-test. |
| 3 | `test_los_tests_de_este_plan_estan_en_los_dos` | las **tres** rutas (`tests/test_plan266_summary_shape.py`, `tests/test_plan266_harness_runner_paridad.py`, `tests/test_plan266_flag_cableado.py`) ∈ `_sh_files()` **y** ∈ `_ps1_files()` — el gate directo de F6.1 |
| 4 | `test_ambas_listas_no_estan_vacias` | `len(_sh_files()) >= 600` y `len(_ps1_files()) >= 600` — anti-censo-vacío, calibrado contra los **687/623** reales de hoy (mismo criterio que C6 le exigió al test 12 de F4: el umbral se calibra contra la realidad medida, no contra un número cómodo) |

> **C24 (BLOQUEANTE del v3) — el test "sin entradas pegadas" se ELIMINA porque codificaba una regla
> que no existe, y habría nacido ROJO con 206 violaciones.** El v3 pedía que "ninguna línea de
> entrada del `.ps1` que no sea la última del array venga sin coma". Medido el 2026-07-29:
> **207** líneas de entrada **no** llevan coma y solo **1** es la última del array (`:796`) ⇒
> **206 violaciones el día 1**. Y la premisa es falsa: el parser real de PowerShell acepta
> `@("x.py"` + newline + `"y.py")` **sin ninguna coma** (0 errores), igual que acepta el archivo
> real completo. En un array literal de PowerShell el salto de línea **ya es** separador; la coma es
> opcional. Un gate que exige un estilo inexistente sobre 206 líneas ajenas es exactamente el falso
> rojo que esta casa prohíbe, y además habría empujado a "arreglar" 206 líneas que están bien.
> Lo que **sí** se conserva es el test 1, porque su premisa está confirmada ejecutando el parser.

**Deliberadamente NO se exige `_sh_files() == _ps1_files()`.** Hoy hay **64 archivos que están
solo en el `.sh`** (la serie `test_mg_*` del migrador, `test_plan70_*`, `test_plan72_*`,
`test_rag_*`, `test_plan237/238/239_*`, entre otros). Un test de igualdad **nacería rojo** con 64
fallos ajenos, y este plan no tiene por qué cerrar esa deuda. Se congela el invariante que **sí**
se cumple (`⊆`) y se deja la deuda declarada, no escondida: si alguien quiere cerrarla, es otro
plan.

**Registro:** este archivo también va en las **dos** listas del arnés, con la forma de cada una
(§F6.1) — un test del arnés que no está en el arnés es exactamente el agujero que este plan
cierra.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan266_harness_runner_paridad.py -q`
**Criterio de aceptación (binario):** `0 failed`, **4 tests** (eran 5 en el v3; el test 2 se
eliminó por C24). **Nace verde** una vez hecha la edición de F6.1 — los 4 invariantes se verificaron
ejecutándolos contra el árbol real; si nace rojo, la edición de F6.1 se hizo mal y hay que corregirla
**antes** de seguir.
**Flag:** ninguna (es un test). **Impacto por runtime:** neutro/idéntico en los 3 — Python puro,
sin `pwsh`, sin red. **Trabajo del operador:** ninguno.

---

**Criterio de aceptación de F6 (binario):** las **18** filas de la tabla de F6.3 cumplen su columna
**DESPUÉS**, más los checks de F6.4 y F6.5. El criterio es **delta contra el baseline medido**, no
"verde": pedir verde es insatisfacible en las filas 7 y 8 (rojos ajenos) y no auditable en el resto.
Si un ratchet o un test que hoy está verde se pone rojo, es de este plan hasta que se demuestre lo
contrario **con un worktree en el commit base** — no se argumenta, se prueba.
(`test_harness_flags_help.py` tiene 4 fallos ajenos conocidos: el gate es que sigan siendo **4** y
que ninguno mencione la key nueva; ver F3.)

**Flag:** ninguna. **Impacto por runtime:** neutro/idéntico en los 3.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (verificable) |
|---|--------|--------------|--------------------------|
| R1 | La normalización enmascara un bug real del backend (una corrida que sí debía tener contadores muestra ceros) | media | El backend **no** deja de emitir lo que tiene: solo rellena claves faltantes. Los ceros aparecen exactamente donde antes había un crash. El control positivo `test_list_runs_no_altera_summary_completo` prueba que un summary bueno pasa intacto. |
| R2 | Convertir `summary: null` en `{}` con ceros haría que corridas `running` muestren "0 danger" | alta si se implementa mal | Explícito en §3.4 y cubierto por `test_list_runs_preserva_summary_none`. Los guards `run.summary &&` (`RunsTimeline.tsx:35`) y `if (!diff \|\| !summary) return null` (`SummaryHero.tsx:65`) se conservan textualmente. |
| R3 | El centinela da falsos positivos y bloquea trabajo ajeno | baja | Alcance de una sola carpeta, dos regex determinables, exención por nombre de función, 10 controles con fixtures. Justificación completa en §F4.4. |
| R4 | Una línea de prosa/comentario dentro de `dbcompare/` dispara el gate | baja | Documentado en §F4.4 punto 6. El arreglo es reescribir la prosa (`el mapa \`by_severity\``), NUNCA aflojar el gate. Gotcha recurrente de la casa. |
| R5 | `tsc` se queja del `?.` sobre `diff.summary` (tipado no-nullable) | baja | TypeScript **permite** `?.` sobre tipos no-nullables (no es error, a lo sumo una regla de lint). El gate es `npm run build`; si apareciera, la respuesta es agregar la regla al eslint-ignore, no sacar la defensa. |
| R6 | La flag nueva rompe `test_harness_flags` por drift de `_CURATED_DEFAULTS_ON` | alta si se olvida un lugar | Los **5 lugares** de cableado están tabulados en F3 y el gate es `test_harness_flags.py` (`:965-983` verifica el par exacto `default=True` ⇔ pertenencia al set). Una flag default-**ON** SÍ declara `default=True`; la trampa inversa (una flag OFF que declara `default=False`) no aplica acá. |
| R7 | El test backend corre contra la base VIVA del operador | baja | `test_plan266_summary_shape.py` **no importa `app`** ni llama a `create_app()`; solo `services.dbcompare_runs`, con `_runs_dir` monkeypatcheado a `tmp_path`. Verificable: el archivo no contiene la cadena `create_app`. |
| R8 | Un ratchet por AST/regex congela NOMBRES y se puede evadir renombrando | media | Asumido: si alguien crea `safeSummary2(`, el gate lo caza (no está en `EXENTO`). Si crea otro normalizador legítimo, tiene que agregarlo a `EXENTO` en el diff, que es exactamente la revisión que queremos forzar. |
| R9 | `PageErrorBoundary.test.tsx` sigue sin poder correr (falta RTL/jsdom) | certeza | Preexistente y documentado en el propio archivo (`:1-8`). Por eso toda la lógica nueva de F5 vive en `errorBoundaryDiagnostics.ts` (puro, corre hoy) y el componente solo cablea. El gate real del componente es `npm run build` + smoke visual. |
| R10 | `firstComponentFromStack` devuelve un nombre **mangleado** en un build de producción minificado (`t`, `Wr`, …) en vez del nombre real del componente | certeza en build minificado | **Limitación asumida y declarada** (C11), sin cambiar el diseño: el operador corre Stacky en dev/local, donde el nombre sale real; aun mangleado, el stack completo copiable —el grueso del valor de F5— sigue sirviendo; resolverlo bien exige sourcemaps en runtime, que es un plan aparte y más caro que el problema. Declarado también en §F5.1. |
| R11 | La tabla de verdad compartida de F1.5 se vacía, se borra o se desincroniza de un lado, y los dos normalizadores vuelven a divergir en silencio | media (es un archivo de datos, fácil de "limpiar") | Tres controles, uno por modo de falla: **vaciado** → T2/T5 exigen `>= 17` casos (18 reales; margen de 1, calibrado como exige C6/C20); **borrado** → T1/T4 fallan en ROJO si el archivo no está (**prohibido** `pytest.skip`, que sería un falso verde); **desincronización** → T3 y T6 recorren el MISMO archivo, así que un cambio de spec que se aplique a un solo lado da rojo del otro. Ninguno de los tres se puede silenciar sin tocar el diff. |
| R12 | La edición del `.ps1` (F6.1b) rompe el runner del arnés en Windows y nadie se entera hasta que el operador lo corre | **era certeza en el v2** (la forma que dictaba es un `ParserError`) | Corregido en F6.1(b): la entrada nueva va **sin** coma y la anterior la recibe. Y se agrega el gate que faltaba: **F6.5** test 1 (`test_ps1_sin_coma_colgante`) hace imposible que la clase entera vuelva, sin depender de que alguien corra PowerShell. |
| R13 | La huella de F6.4 pone en rojo el catálogo de errores (`test_patrones_compilan`) | **era certeza en el v2** (`re.compile(None)` ⇒ `TypeError`) | Corregido: `log_pattern` compilable + `self_test`, validados contra los 5 tests del catálogo antes de escribirlos. El criterio de F6.4 dejó de ser "el JSON es válido" y pasó a ser **el conteo de fallos del catálogo no sube de 3** (los 3 ajenos de hoy). |
| R14 | Alguien "simplifica" el guard de decimales de `toCount`/`_count` volviendo al `Number(value)` / `float(value)` desnudo | media (parece código defensivo redundante) | Los 4 casos `"0x10"`, `"0b101"`, `"1_0"`, `"1e2"` están en la tabla de verdad compartida: sacar el guard de **cualquiera** de los dos lados da rojo en T3 (vitest) o T6 (pytest). El comentario de cada implementación dice explícitamente que la otra existe. |
| R15 | La flag declara `requires=` y nadie suma la arista a `_REQUIRES_MAP_FROZEN` ⇒ `test_harness_flags_requires.py` pasa de `9 passed` a rojo | **era certeza en el v3** (la tabla listaba 5 patas y no mencionaba el mapa ni una vez) | Corregido: la pata **6** es obligatoria en la tabla de F3, con el comentario y la nota de profundidad 1 literales. Y **A4/F3.5** lo convierte en gate propio (`test_pata6_arista_requires_congelada`), más la fila 5 de F6.3 que exige `9 passed` exactos. Tres capas: la instrucción, el test de cableado y el baseline delta. |
| R16 | La copia del diagnóstico se escribe con `navigator.clipboard` directo y rompe el `copyDebtRatchet` | **era certeza en el v3** (cupo 0 en ese archivo, ratchet verde hoy con `3 passed`) | Corregido: se usa `services/copyService.copyText()`, el único lugar legítimo según el propio encabezado del ratchet. Gate agregado a F5.2 y a F6.3 (fila 17), más `grep -c "navigator.clipboard" = 0` en el criterio de F5.2. Bonus real: `copyText` cae a `execCommand` cuando el permiso se niega, algo que el `?.` del v3 no hacía. |
| R17 | El gate de la ayuda llana se satisface sin correr nada (`-k` que deselecciona todo y sale 0) | **era certeza en el v3** (medido: `8 deselected`, exit `0`) | Corregido: el criterio es delta sobre el archivo completo (`4 failed, 4 passed`) más un `findstr` que debe NO imprimir la key nueva. Y el contenido se validó contra las **seis** reglas del contrato, no solo las longitudes. |
| R18 | Un color hex nuevo en `PageErrorBoundary.module.css` pone el `uiDebtRatchet` en rojo (baseline congelado en 2) | alta si el CSS se improvisa | Corregido: las 4 clases van **literales** en F5.2, todas con `rgba()`, cero hex nuevo. Trampa adicional declarada: la familia de tokens `--color-*` **no existe** en el tema, así que "usá tokens" sin nombrarlos también fallaba. |
| R19 | El diagnóstico copiable / el Centro de Actividad arrastran un valor de fila de una BD real del operador | media (el `message` de un error es texto arbitrario y el Comparador trabaja contra bases reales) | Tres mitigaciones verificables, §3.10: **(a)** orden de egreso — la normalización de F3 va **dentro** de `get_run`, y el masking (`dbcompare_masking.apply_to_run_response`, `api/db_compare.py:447`) queda **aguas abajo**; el plan no mueve ni envuelve esa llamada, así que no puede fallar abierto; **(b)** cero egreso de red — `activityCenter` solo usa `localStorage` (`:35`), sin `fetch`/POST, y la copia es HITL (solo al click); **(c)** cota — `MAX_MESSAGE_CHARS=500` y `MAX_STACK_CHARS=4000` con 4 tests que la fijan, incluido el control anti-filtración que se pone rojo si alguien "enriquece" el texto con el run. `dbcompare_masking.py` **no cubre** este camino y no podría (es backend y por patrones sobre el data-diff): la defensa acá es la cota, y está dicho. |

---

## 6. Fuera de scope (explícito)

1. **Reescribir o migrar en disco los JSON de corridas viejas del operador.** Sería categoría
   **(B)** de la regla de flags (escribe en datos reales del operador y es irreversible), y
   tendría que nacer **OFF** con su propia flag. **No se propone.** La normalización de este
   plan es 100% en memoria, y `test_list_runs_no_reescribe_el_archivo_en_disco` lo prueba
   byte a byte.
2. **`backend/services/dbcompare_watch.py:293`**, que escribe `by_severity` posiblemente `None`
   dentro del payload de un evento de drift. Verificado: **ningún componente del frontend lee
   ese campo** (el censo de `by_severity` en `frontend/src/` no toca `DriftEventsPanel.tsx`).
   No hay bug observable ⇒ no se toca. Si algún día se renderiza, la regla del centinela lo
   obliga a pasar por `safeBySeverity`.
3. **La ruta `/radar` de `backend/api/db_compare_watch.py`.** No se modifica: la normalización en
   `list_runs` (F3) ya elimina el `by_severity: {}` que emitía en `:161`, porque `:153` lee de
   `dbcompare_runs.list_runs(200)` (`:145`). **Esto cubre `/radar` y SOLO `/radar`** — la otra
   ruta del mismo archivo, `/baseline-diff`, es el ítem 7 (corrección C5: el v1 declaraba el
   archivo entero cubierto, y no lo está).
4. **Versionar el esquema de los runs en disco** (`"schema_version": N` + migrador). Es la
   solución estructural completa y es un plan aparte, más caro. Este plan cierra la incidencia
   con la normalización de borde, que es el 100% del beneficio al 10% del costo.
5. **Instalar RTL/jsdom** para poder correr los tests de componente. Gap estructural del repo,
   ajeno a esta incidencia.
6. **Cambiar el copy del boundary** (`Esta pestaña falló al renderizar`, `El resto de la
   aplicación sigue funcionando…`). Se conservan textualmente.
7. **La ruta `/baseline-diff` (la TERCERA salida de summary del backend).**
   `EnvironmentRadar.tsx:144` llama a `DbCompareWatch.baselineDiff(alias)` →
   `backend/api/db_compare_watch.py:125-133` (`baseline_diff_route`) →
   `backend/services/dbcompare_baseline.py:151-166` (`baseline_diff`), que devuelve el resultado
   de `dbcompare_diff.diff_snapshots(...)` **directo al `jsonify`**, sin pasar por `list_runs` ni
   por `get_run`. **No se toca, y la razón es verificable (no es "se nos pasó"):** ese payload lo
   arma en el momento el productor canónico `dbcompare_diff.summarize()`
   (`backend/services/dbcompare_diff.py:321-337`), que **siempre** construye los 3 mapas
   completos (`:322`) — no hay JSON viejo de disco de por medio, que es justamente el origen del
   bug. Y aun así queda cubierta en el frontend: F2 hace que ese consumidor pase por
   `safeSummary(r.diff?.summary)`. Normalizar además en el backend sería trabajo sin defecto
   observable que lo justifique.
8. **Cerrar el desfasaje entre las dos listas del arnés.** Medido el **2026-07-29** sobre
   `760ac455`: el `.sh` tiene **687** entradas y el `.ps1` **623** (el v3 decía 680/616 — C31);
   hay **64 archivos que están solo en el `.sh`** (la serie
   `test_mg_*` del migrador, `test_plan70_*`, `test_plan72_*`, `test_rag_*`,
   `test_plan237/238/239_*`, entre otros). Es deuda **ajena y preexistente**, de planes que
   registraron su test en un solo runner. **F6.5 no la cierra**: congela el invariante que hoy sí
   se cumple (`.ps1 ⊆ .sh`) y deja la brecha declarada en vez de escondida. Exigir igualdad haría
   nacer el test con 64 fallos ajenos, que es exactamente el falso rojo que esta casa prohíbe.
   Cerrarla es un plan aparte.
9. **Los 3 rojos preexistentes de `test_error_fingerprints_catalog.py`** (16 de las 42 huellas
   del catálogo no traen `self_test`). Ajenos, anteriores a este plan, verificados con el
   baseline de F6.4. Este plan solo se compromete a **no sumar un cuarto**.
10. **Enmascarar el mensaje de error del navegador, y cerrar el masking de los otros
    `get_run` (DATOS PERSONALES — decisión declarada, no omisión).** Medido: `get_run` se llama en
    **9** lugares de `backend/api/db_compare.py` y solo el de `:439` pasa por
    `dbcompare_masking.apply_to_run_response` (`:447`); los otros 8 (`:455`, `:488`, `:680`, `:713`,
    `:796`, `:925`, `:1016`) consumen el run para triage/gates/scripts y **no devuelven el run
    completo al cliente**. Es deuda **ajena y preexistente** del Plan 181, y este plan **no la
    toca**: su cambio se inserta **antes** del masking, así que no lo empeora ni lo saltea
    (§3.10 (a)). Y del lado del navegador **no se propone enmascarar el `message`**: un
    enmascarador por patrones en el frontend daría falsa seguridad (no sabe qué es un dato de
    negocio y qué es parte del mensaje del motor de JS) y el camino no sale del navegador
    (§3.10 (b)). La defensa que sí se implementa es la **cota** (§3.10 (c)). Cerrar el masking de
    los otros 8 call-sites, si algún día devuelven el run entero, es un plan aparte.

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **summary** | El objeto `DiffSummary` de una corrida: `by_severity`, `by_action`, `by_object_type`, `objects_total`, `objects_unchanged`, `parity_score`. Contrato en `frontend/src/components/dbcompare/dbcompareTypes.ts:105-112`; productor canónico en `backend/services/dbcompare_diff.py:321-337`. |
| **forma canónica** | Los 3 mapas presentes con **todas** sus claves y valores enteros `>= 0`. |
| **acceso profundo sin guarda** | Leer una clave de uno de los 3 mapas sin haber garantizado que el mapa existe. Las 8 instancias de hoy están en §2.3. |
| **borde de lectura** | Las funciones por las que sale del backend un run **PERSISTIDO** (leído de un `.json` del disco): `dbcompare_runs.list_runs` y `dbcompare_runs.get_run`. **No** es "cualquier consumidor" (eso decía el v1 y era falso): `/baseline-diff` devuelve un summary recién calculado sin pasar por ninguna de las dos — ver §2.4 y §6 ítem 7. |
| **tabla de verdad compartida** | `frontend/src/components/dbcompare/__fixtures__/summaryShapeTruthTable.json`: la especificación ÚNICA de `toCount` (TS) y `_count` (Python). Los dos lados la recorren; ninguno la interpreta por su cuenta. Ver F1.5. |
| **centinela / ratchet** | Test que falla si un patrón prohibido reaparece. No es una foto del estado actual: caza al archivo nuevo. |
| **defensa en profundidad** | Backend y frontend normalizan por separado; ninguno confía en el otro. |
| **flag default ON** | Nace encendida. Solo nace OFF si (A) quema tokens en reposo o (B) escribe en un sistema real del operador. La única flag de este plan no cae en ninguna ⇒ **ON**. |

### 7.2 Orden de implementación (estricto)

1. **F0.1** — test frontend de reproducción. Confirmar que da **ROJO** con
   `Cannot read properties of undefined (reading 'danger')`.
2. **F0.2** — test backend de reproducción. Confirmar **ROJO** (≥6 fallos) y los 2 controles
   positivos en verde.
3. **F1** — `summaryShape.ts` + `summaryShape.test.ts`. Verde (≥28 tests).
4. **F1.5** — fixture `__fixtures__/summaryShapeTruthTable.json` + los 3 tests de vitest en
   `summaryShape.test.ts` (verde, ≥31 tests) + los 3 de pytest en
   `test_plan266_summary_shape.py` (T4/T5 verdes; **T6 sigue ROJO hasta F3**, porque depende de
   `_count`).
5. **F2** — adopción en `radarLogic.ts`, `RunsTimeline.tsx`, `EnvironmentRadar.tsx`,
   `svgMath.ts`, `SummaryHero.tsx`. **F0.1 pasa a verde.**
6. **F3** — `_normalize_summary` + `_count` (con el corte de `bool` y el `OverflowError`) +
   cableado en `list_runs` y en `get_run` (**incluido el summary anidado de `diff`**) + flag en
   los **SEIS** lugares obligatorios de la tabla de F3 —**la 6.ª es la arista en
   `_REQUIRES_MAP_FROZEN`, C22**— con categoría `comparador_bd` (C27). El ítem 7 de esa tabla es
   un "no se toca", no un cableado. **F0.2 pasa a verde, y el T6 de F1.5 también.**
7. **F3.5** — `test_plan266_flag_cableado.py` (**A4**). Verde (7 tests). Si alguna de las 6 patas
   quedó afuera, esta fase lo dice acá y no 3 fases después.
8. **F4** — centinela `dbcompareSummaryShapeRatchet.test.ts`. Verde (12 tests).
9. **F5** — `errorBoundaryDiagnostics.ts` (con `MAX_MESSAGE_CHARS`/`MAX_STACK_CHARS`) + tests
   (≥15) + cableado en `PageErrorBoundary.tsx` usando **`copyService.copyText`, nunca
   `navigator.clipboard` — C25** + las 4 clases CSS literales sin hex nuevo (C29).
10. **F6** — registro de los **tres** archivos de test en `run_harness_tests.sh` (líneas desnudas)
    **y** en `run_harness_tests.ps1` (líneas entrecomilladas **SIN coma, al final del array, después
    de `:796`** — C23; NO se le toca la coma a ninguna línea existente), huella en
    `error_fingerprints.json` con `log_pattern` compilable y `self_test` (F6.4 — C13), guard del
    runner `.ps1` (**F6.5**, 4 tests, nace verde — el 5.º se eliminó por C24), `npm run build`, y la
    suite de cierre de F6.3 **contra su tabla de baseline medido** (A5).

### 7.3 Definición de Hecho (DoD global) — binaria

- [ ] `npx vitest run src/components/dbcompare/__tests__/summaryShapeCrash.test.ts` → `0 failed`
      (y antes de F2 fallaba con `reading 'danger'`).
- [ ] `npx vitest run src/components/dbcompare/summaryShape.test.ts` → `0 failed`, **≥31 tests**
      (los ≥28 de F1 más los 3 de la tabla de verdad compartida de F1.5).
- [ ] El fixture compartido
      `frontend/src/components/dbcompare/__fixtures__/summaryShapeTruthTable.json` **existe** y
      tiene **≥17 casos** (18 reales) — y lo verifican los **dos** lados: T1/T2 en vitest y T4/T5 en pytest,
      **sin ningún `pytest.skip`** por archivo faltante (un skip acá es un falso verde).
- [ ] `_count` y `toCount` coinciden **caso por caso** contra ese archivo (T3 en vitest, T6 en
      pytest), incluido `true → 0` (C2), `1e400 → 0` sin lanzar (C1), y las tres clases que el v2
      no cubría: `"0x10" → 0` y `"0b101" → 0` (C16: `Number()` daría 16 y 5) y `"1_0" → 0`
      (C21: `float()` de Python daría 10.0). Los **dos** normalizadores llevan la **misma** regex
      de decimales (`DECIMAL_RE` en `summaryShape.ts`, `_DECIMAL_RE` en `dbcompare_runs.py`).
- [ ] `npx vitest run src/__tests__/dbcompareSummaryShapeRatchet.test.ts` → `0 failed`, 12 tests,
      censo = `[]`, el fixture histórico detecta **8**, y el test 12 exige **`>= 45`** archivos
      censados (no 12).
- [ ] `npx vitest run src/components/__tests__/errorBoundaryDiagnostics.test.ts` → `0 failed`,
      **≥15 tests**, incluidos los 4 de la cota de datos personales (C30): stack gigante truncado
      con `…[truncado]`, mensaje gigante truncado, `buildActivityBody` truncado, y el control
      anti-filtración que exige que el texto no contenga nada más que los 5 campos nombrados.
- [ ] `npx vitest run src/__tests__/copyDebtRatchet.test.ts` → **`3 passed`** (su baseline medido) y
      `components/PageErrorBoundary.tsx` **NO** figura en `src/__tests__/copyDebtBaseline.json`
      (C25). Verificación directa:
      `grep -c "navigator.clipboard" src/components/PageErrorBoundary.tsx` = **0** y
      `grep -c "copyService" src/components/PageErrorBoundary.tsx` = **1**.
- [ ] El hex de `src/components/PageErrorBoundary.module.css` sigue en **2** (C29):
      `grep -o -E "#[0-9a-fA-F]{3,8}" src/components/PageErrorBoundary.module.css | wc -l` = 2.
- [ ] `npx vitest run src/components/dbcompare/radarLogic.test.ts` y
      `npx vitest run src/components/dbcompare/__tests__/svgMath.test.ts` → `0 failed`,
      **sin haber modificado esos archivos de test**.
- [ ] `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → `0 failed` (o rojo ajeno probado
      con worktree en el commit base).
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_plan266_summary_shape.py -q` → `0 failed`,
      incluidos `test_list_runs_no_lanza_con_infinity_en_disco` (**C1**, con el token `Infinity`
      escrito a mano en el `.json`, no vía `json.dumps`),
      `test_count_booleano_es_cero` (**C2**),
      `test_get_run_normaliza_tambien_el_summary_anidado_del_diff` y
      `test_get_run_no_reescribe_el_archivo_en_disco` (**C4**).
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` → `0 failed`
      (baseline hoy: 56 passed).
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q` →
      **exactamente `9 passed`** (baseline medido hoy: `9 passed`). Es el gate de la **SEXTA** pata:
      si da `8 passed, 1 failed` con `Extras: ['STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED']`, falta la
      arista en `_REQUIRES_MAP_FROZEN` (**C22**).
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q` →
      **exactamente `4 failed, 4 passed`** (los 4 rojos ajenos de hoy) **y** ninguna línea de la
      salida menciona `SUMMARY_SHAPE`. **PROHIBIDO** usar `-k SUMMARY_SHAPE` como gate: ejecutado da
      `8 deselected` con exit `0` — cero tests corridos y falso verde (**C26**).
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q` → `0 failed`
      (baseline hoy: 4 passed).
- [ ] `npm run build` (`tsc --noEmit && vite build`) → exit 0.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_plan266_flag_cableado.py -q` → `0 failed`,
      **7 tests** (**A4**): las **SEIS** patas de
      `STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED` —`config.py`, `FLAG_REGISTRY` (con `default=True`,
      `requires="STACKY_DB_COMPARE_ENABLED"`, `group="comparador_bd"`),
      `_CATEGORY_KEYS["comparador_bd"]`, `_CURATED_DEFAULTS_ON`, `PLAIN_HELP` y
      **`_REQUIRES_MAP_FROZEN`**— más la verificación de profundidad 1 (la madre no declara
      `requires`). `categorize(...)` devuelve **`"comparador_bd"`**, NO `"capacidades_optin"` (**C27**).
- [ ] Los **tres** archivos `tests/test_plan266_summary_shape.py`,
      `tests/test_plan266_harness_runner_paridad.py` y `tests/test_plan266_flag_cableado.py`
      figuran en **los dos scripts, con la forma de cada uno**: en
      `backend/scripts/run_harness_tests.sh` (variable `HARNESS_TEST_FILES`, `:20`) como líneas
      **desnudas** (sin comillas, sin coma — es lo único que acepta la regex del meta-test), y en
      `backend/scripts/run_harness_tests.ps1` (variable `$HarnessTestFiles`, `:13`)
      entrecomilladas y **SIN coma, al final del array, después de la última entrada real
      (`:796`)**. **No** se le agrega ni se le quita coma a ninguna línea existente (**C23**: la del
      258 ya tiene la suya y no es la última; **C24**: PowerShell no exige coma entre elementos
      separados por salto de línea — 207 entradas del archivo real no la llevan y parsea con 0
      errores). Lo único prohibido es una coma **colgante** justo antes del `)`.
      Y **no** figuran en `backend/tests/harness_ratchet_allowlist.txt`.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_plan266_harness_runner_paridad.py -q` →
      `0 failed`, **4 tests** (**F6.5**; eran 5 en el v3 — el de "entradas pegadas" se eliminó
      porque nacía rojo con 206 violaciones sobre una regla de PowerShell inexistente, C24).
- [ ] `docs/sistema/error_fingerprints.json` contiene **exactamente una** entrada con
      `"id": "dbcompare-summary-shape-render-crash"`, con `status: "resolved"`,
      `log_guarded: false`, un **`log_pattern` compilable** (NO `null` — C13), su `self_test`
      con `matches`/`clean`, y `guard_test` apuntando al ratchet de F4; el archivo sigue siendo
      JSON válido y `killed_commit` quedó completado con el SHA real (no `TODO-…`).
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_error_fingerprints_catalog.py -q` →
      **exactamente `3 failed, 5 passed`**, con los mismos 3 rojos ajenos preexistentes
      (`campos_obligatorios`, `status_enum`, `self_test_coherente`). Si el conteo sube a 4, o si
      `test_patrones_compilan` se pone rojo, la huella nueva está mal (C13).
- [ ] `PageErrorBoundary.tsx` conserva textual `Esta pestaña falló al renderizar` y
      `El resto de la aplicación sigue funcionando`.
- [ ] **Smoke visual (HITL, lo hace el operador):** abrir el Comparador de BD con al menos una
      corrida vieja/incompleta en `data/…/runs/` y confirmar que (a) la pestaña renderiza,
      (b) el radar/timeline/hero muestran ceros donde falta el dato, (c) forzando un error de
      render el cartel muestra superficie + componente y el botón "Copiar diagnóstico" copia
      las 5 líneas + stack.
- [ ] Ningún archivo de corridas en disco fue modificado por la app durante el smoke
      (comparar `Get-FileHash` antes/después de la carpeta de runs).
- [ ] **Datos personales (HITL, lo confirma el operador en el smoke):** el texto que copió el botón
      contiene **solo** las 5 líneas nombradas más el stack, **ningún valor de fila** de la base
      comparada, y si el stack era largo termina en `…[truncado]`. Y en la pestaña Red del navegador
      **no hay ninguna petición** disparada por el cartel de error (el diagnóstico no sale del
      navegador: §3.10 (b)).

---

### Nota de paridad de runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro)

Este plan es **íntegramente frontend React + backend Flask**: no toca el selector de runtime,
ni `agent_runner`, ni prompts, ni el transporte de ninguno de los 3 CLIs. El impacto es
**neutro/idéntico en los tres**, y no requiere fallback porque no hay capacidad diferencial en
juego. Los 3 runtimes pueden **implementarlo** sin degradación: todas las fases son ediciones
de archivos con tests deterministas, sin dependencias nuevas, sin red y sin herramientas
exclusivas de un runtime.
