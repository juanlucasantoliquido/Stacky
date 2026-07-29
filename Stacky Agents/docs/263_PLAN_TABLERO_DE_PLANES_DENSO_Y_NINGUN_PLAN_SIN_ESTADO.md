# Plan 263 — Tablero de planes denso y ningún plan sin estado: fallback único, migración con evidencia y guardia anti-regresión

**Estado:** CRITICADO v4 (2026-07-29) · **Autor:** pipeline `proponer-plan-stacky` · **Juez:** `criticar-y-mejorar-plan` — **v1 RECHAZADO** (6 BLOQUEANTES) → v2; **v2 RECHAZADO** (5 BLOQUEANTES) → v3; **v3 RECHAZADO** (1 BLOQUEANTE, verificado abriendo el árbol real del 2026-07-29) → v4 in place

---

## 0. CHANGELOG v3 → v4

El v3 fue **RECHAZADO** por un juez independiente (`criticar-y-mejorar-plan`, corrida 2026-07-29) que
abrió el árbol real en vez de confiar en la prosa. **El diseño de v3 no cambia ni una decisión**: los
19 casos de F1, las 24 reglas/tests de F3, el contrato de la transacción de F2.5 y las 8 flags/reglas de
F0 siguen siendo correctos. Lo que falló fue algo más simple y más peligroso: **el tiempo pasó**. Entre
el 2026-07-27 (fecha de este v3) y el 2026-07-29 (fecha de esta crítica), los planes hermanos
267/268/269/270 se mergearon a `main` (`consolidación 9 ramas`, 2026-07-29) y cada uno dio de alta sus
propias flags en los DOS archivos de mayor concurrencia del arnés — exactamente el gotcha ya conocido de
este repo ("la costura corre los anclajes de los planes pendientes"), reproducido ahora sobre el propio
263.

- **C1 (BLOQUEANTE)** — **los anclajes de inserción de F0.1 (`config.py`) y F0.2 (`harness_flags.py`)
  cayeron en drift real, MEDIDO abriendo el árbol de hoy.** F0.1 decía "insertar después de la línea
  1920 (fin del bloque `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED`); `:1922` ya es el comentario del Plan
  167". Medido el 2026-07-29: `config.py:1920` cae **dentro de la llamada `os.getenv(...)` de un flag
  totalmente distinto** (`STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED`, que hoy ocupa `:1916-1922`) —
  insertar ahí de forma literal **parte una llamada a función en dos** y produce un `SyntaxError` que
  tira abajo **todo `config.py`**, y con él todo el backend (cualquier módulo que hace `import config`
  deja de poder importar). El bloque real de `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED` vive hoy en
  `:1930-1935`, y el comentario del Plan 167 en `:1937` (drift de +15/+17 líneas en dos días). Mismo
  fenómeno, mayor magnitud, en `harness_flags.py`: F0.2 anclaba "inmediatamente después de
  `:4544-4558`"; medido hoy, ese `FlagSpec` cierra en `:4616` (**+58 líneas** — la magnitud exacta que
  ya predecía el gotcha del repo sobre `_REQUIRES_MAP_FROZEN`, 143→146). Un tercer punto de datos
  confirma que no es casualidad: la cita de precedente dentro de F0.2
  (`STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`, "`harness_flags.py:3166-3173`") hoy empieza en `:3224`
  (mismo orden de magnitud de drift). **Los anclajes de contenido, en cambio, no fallaron**: F0.4
  (`:467`), F0.5 (`:25`/`:1459`), los seis puntos internos de `plans_board.py` que usa F1
  (`:546-612`, verificados línea por línea, incluida la línea en blanco entre `:568` y `:570` que el
  propio v3 advertía), el esquema de `error_fingerprints.json`, el schema de `ledger.json` (47
  entradas, `version`+`planes`), y las 9 líneas de tokens de `theme.css` (`:100-108`/`:251-259`) — los
  siete coinciden EXACTO con la medición del 2026-07-29. El patrón es preciso: **drift sólo en los dos
  puntos de inserción por número crudo en los dos archivos que edita CADA plan del repo** (todo plan
  nuevo pasa por F0), nunca en los anclajes que ya citaban una estructura (`_CURATED_DEFAULTS_ON`,
  `PLAIN_HELP`) o una constante importada. Corregido: F0.1 y F0.2 pasan de "línea N" a **marcador
  semántico + verificación obligatoria con `Select-String`/grep antes de insertar** — el mismo patrón
  que F0.6 ya usaba ("antes del `}` de cierre") — con los números de hoy como valor ilustrativo, no
  autoritativo.
- **C2 (IMPORTANTE)** — la Regla 1 de F3 hardcodeaba en prosa el vocabulario de veredictos del ledger
  (`"APROBADO"`, `"TERMINADO-POR-SUPERVISOR"`) en vez de importar `_LEDGER_OK_VEREDICTOS`
  (`services/plans_board.py:34`) — la MISMA tupla que ya usan `ledger_ok` en `build_board` (`:566`) y en
  `suggest_next_action` (`:475`), verificado. Es exactamente el pecado que C6/C9 (v2→v3) ya mataron para
  `_PLAN_FILE_RE`/`_ESTADO_RE`: si el día de mañana alguien agrega un tercer veredicto válido tocando
  sólo `_LEDGER_OK_VEREDICTOS`, la Regla 1 de F3 queda desincronizada en silencio. Corregido: Regla 1
  importa la constante, no reescribe la tupla; nuevo caso 25 de F3 congela la identidad de objeto.
- **[ADICIÓN ARQUITECTO 6]** F1(e) — `totals["por_origen"]`: a costo marginal cero (mismo loop que ya
  computa `estado_origen` por card), agrega el desglose agregado `{"declarado": n, "inferido": n,
  "ledger": n}` a los totales del tablero. Fortalece la tesis central del plan ("nunca mentir en
  silencio") a nivel de portafolio: el operador ve de un vistazo qué porción de "todo implementado" es
  verificable y cuál es supuesta, sin abrir el panel de F6 ni pedir un segundo request. Cero I/O nuevo,
  cero flag nueva, cero endpoint nuevo, aditivo y retrocompatible.

*(Re-medido en esta crítica, 2026-07-29: el comando de §1.1 da `total 222 | sin estado 79`. El total
volvió a moverse — nacieron 270 y 271 — pero el 79 no: los dos planes nuevos ya declaran su propio
**Estado:**, confirmando en vivo la tesis del propio v3 de que "el total es una variable, el 79 es el
dato". Los dos "rojos ajenos" también se re-verificaron EXACTOS: `test_harness_flags_help.py` → 4
failed / 4 passed; `test_error_fingerprints_catalog.py` → 3 failed / 5 passed. Y los tres archivos que
el v3 daba por verdes lo siguen estando: `test_harness_flags.py` + `test_harness_flags_requires.py` +
`test_harness_ratchet_meta.py` → 69 passed combinados, 0 failed.)*

---

## 0.1 CHANGELOG v2 → v3

El v2 fue **RECHAZADO**. La v2 no había tenido revisión independiente (la escribió el mismo agente en
la misma corrida), y al abrir los archivos que anclaba aparecieron **cinco bloqueantes**. Los anclajes
de flags que el v2 dice haber arreglado (C1/C2/C3 de la ronda anterior) **verifican todos** — eso se
conserva intacto. Lo que no verificaba era el **diseño de F3**, la lectura de flags en la API, la
relación entre los dos campos nuevos, el criterio binario de F0 y el contrato de escritura del ledger.
**Nada del valor del v2 se podó.**

- **C1 (BLOQUEANTE)** — **las reglas de inferencia de F3 no hacen lo que el plan dice, MEDIDO sobre los
  79 planes vivos.** `_umbral_reciente = max(numeros) - 20 = 269 - 20 = **249**` ⇒ la **regla 4 matchea
  0 archivos** (su propósito declarado —"dejar los recientes pendientes en `PROPUESTO`"— es
  inalcanzable). La **regla 1 matchea 18**, pero los **18** son exactamente los que F1.5 excluye en
  `ya_resueltos_por_ledger` (medido: 18 aprobados sin drift, **0** con drift) ⇒ **regla 1 = código
  muerto**. Resultado real del v2: **61 propuestas, ninguna en `PROPUESTO`, y 45 (74 %) en
  `IMPLEMENTADO`/`baja` = "sin evidencia"**. Es decir, el botón escribía a disco 45 estados que el
  propio plan admite no poder justificar. Corregido: reglas reescritas y medidas, y la
  **[ADICIÓN ARQUITECTO 4]** prohíbe escribir una propuesta sin evidencia.
- **C2 (BLOQUEANTE)** — los endpoints de F3 leían la flag como `config.config.STACKY_...`, pero
  `api/plans_board.py:10` hace `from config import config`: dentro de ESE módulo `config` **ya es la
  instancia**. `config.config` lanza `AttributeError` ⇒ **500 en vez del 404** que exige el criterio
  binario de la propia fase. Corregido: `getattr(config, "…", <default>)`, el patrón literal de
  `api/plans_board.py:16` y `:79-81`.
- **C3 (BLOQUEANTE)** — **falso verde y mentira en pantalla.** El §4 y F1.5 declaraban
  `estado_inferido` como "azúcar de `estado_origen == 'inferido'`", pero el **caso 13 de F1** exigía
  `estado_origen == "ledger"` **y** `estado_inferido is True` a la vez. Con eso, el `estadoChip` de F4
  (`… || card.estado_inferido`) pinta **"Aprobado (inferido)"** en la card real — justo la mentira que
  R9 dice matar — y el **test 4 de F4 sale VERDE** sólo porque su fixture omite `estado_inferido`.
  Corregido: `estado_inferido` pasa a ser **exactamente** `estado_origen == "inferido"`, el caso 13
  cambia a `is False`, y se agrega el test con la card real (las dos claves juntas).
- **C4 (BLOQUEANTE)** — el criterio binario de F0 ("los tres comandos exit 0") es **imposible hoy**:
  `tests/test_harness_flags_help.py` tiene **4 fallos preexistentes ajenos** y el primero es
  `test_plain_help_covers_all_registry_keys` con **79 flags del registry sin entrada en `PLAIN_HELP`**.
  La tabla de causas del v2 atribuía ese rojo a "falta una de las 3 entradas de ayuda llana", que es
  falso. Corregido: criterio binario **por entrada propia**, con el comando exacto que valida las 3
  keys del 263 sin depender del rojo ajeno.
- **C5 (BLOQUEANTE)** — la pata 2 de F2.5 (re-sellado del ledger) **no tenía contrato de escritura**.
  `load_ledger()` (`plans_board.py:425-446`) devuelve **sólo** `data["planes"]`; reusarla para escribir
  deja el archivo sin la clave `version` y sin el envoltorio ⇒ `load_ledger` pasa a devolver `{}` y
  **los 47 planes aprobados pierden su aprobación en silencio**. Ningún test del v2 lo cubría.
  Corregido: contrato de re-escritura del documento COMPLETO + 2 casos de test nuevos.
- **C6 (IMPORTANTE)** — F2 predicaba "la regla se importa, no se reescribe" y a la vez **reimplementaba
  `_PLAN_FILE_RE`** como `^[0-9]+_PLAN_.*\.md$`, cuando el real es `^(\d{2,3})_PLAN_(.+)\.md$`
  (`plans_board.py:23`). Hoy coinciden (220 = 220, medido), pero es el mismo pecado que C9.
  Corregido: se importa `_PLAN_FILE_RE` + **[ADICIÓN ARQUITECTO 5]**.
- **C7 (IMPORTANTE)** — F7 mandaba escribir la huella con los campos "síntoma / causa raíz / detección /
  fix", que **no existen** en el esquema: `tests/test_error_fingerprints_catalog.py:19` exige
  `id, title, class, status, log_pattern, log_guarded, killed_by, guard_test, self_test`, con
  `status ∈ {resolved, open, by_design}` y un `self_test` cuyos `matches` **tienen que matchear** el
  `log_pattern`. Y ese archivo de test no estaba en la lista de F7 (hoy trae **3 rojos ajenos**).
  Corregido: entrada con el esquema real, una línea de registro honesta en el único camino destructivo,
  y el test agregado a F7 con su nota de rojo ajeno.
- **C8 (IMPORTANTE)** — el test 5 de F2 usaba `parse_plan_header`, que **el snippet del módulo no
  importa** (`NameError`), y decía "la línea justo después" sin el `\n` explícito: `_ESTADO_RE` es
  `MULTILINE` y exige inicio de línea. Corregido: import completo y literal exacto del archivo sintético.
- **C9 (IMPORTANTE)** — la regla 2 disparaba por la **subcadena desnuda `"IMPLEMENTADA"`** con
  `confianza: alta`. Medido: de sus 6 hits, **sólo 2** vienen de `"Registro de implementación"`; los
  otros 4 de la subcadena. `"NO IMPLEMENTADA"` la satisface igual. Corregido: marcador **estructural**
  (fila de tabla) y nunca `alta` desde una subcadena suelta.
- **C10 (IMPORTANTE)** — KPI stale otra vez: el v2 fijó `total 216` y el **mismo día** el comando
  imprime **220** (los planes 266-269 nacieron después). Corregido: el total deja de ser una constante.
- **C11 (IMPORTANTE)** — el smoke de F5 mandaba "activar densidad compacto con el `DensityToggle`" sin
  decir dónde vive (`frontend/src/components/AppearanceSettings.tsx:48`, no en el tablero).
- **C12 (IMPORTANTE)** — F6 no decía que `rawGet`/`rawPost` devuelven `Promise<RawResponse<T>>`
  (`api/client.ts:96` y `:47`), ni cómo se lee la flag en la app (`Diag.health()` →
  `flags.find(x => x.key === …)`, patrón de `App.tsx:211`).
- **C13-C16 (MENORES)** — `estado_origen: "declarado"` para un doc que no declara nada con la flag OFF;
  R6 decía "token exacto o inmediatamente superior" y `0.15rem`→`--space-1` baja de 2,4 a 2 px; R1
  citaba `243, 247..252` como no implementados (medido: 243/247/248/249 **no** están sin estado y
  250/251/252 **sí** traen su registro de implementación con tests en verde); y no se citaba
  `claim_plan_path` (`plans_board.py:382-394`), que **ya escribe** `**Estado:** PROPUESTO v1` y es la
  prueba de que KPI-4 no agrega trabajo al operador.
- **[ADICIÓN ARQUITECTO 4]** F3 — **prohibido escribir sin evidencia**: `confianza: "sin_evidencia"`
  no es aplicable, y un centinela corre la inferencia sobre el **corpus vivo** (no un fixture).
- **[ADICIÓN ARQUITECTO 5]** F2 — `test_regla_de_archivo_unica`: el ratchet usa el **mismo**
  `_PLAN_FILE_RE` del tablero, importado; cierra C6 para siempre.

---

## 0.2 CHANGELOG v1 → v2

El v1 fue **RECHAZADO**: su F0 tenía **cinco rojos garantizados** (el arnés se ponía rojo antes de
escribir una sola línea de producto) y su F3 **des-aprobaba** planes que el supervisor ya había
cerrado. Todo el valor del v1 se conserva; nada se podó.

- **C1** — F0 declaraba `default=False` en la flag OFF ⇒ `test_default_known_only_for_curated` rojo.
  Corregido: `default=` **omitido**, con el comentario del precedente `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`.
- **C2** — F0 mandaba las 2 keys ON a `_CURATED_DEFAULTS_ON` "(`harness_flags.py:350`)", que en realidad
  es `_CATEGORY_KEYS`. Corregido: el conjunto curado vive en **`backend/tests/test_harness_flags.py:467`**.
- **C3** — F0 nunca editaba `_CATEGORY_KEYS` ni `PLAIN_HELP` ⇒ 2 rojos más. Corregido: **6 patas**
  enumeradas, con las 3 entradas de ayuda llana ya redactadas y validadas contra la denylist.
- **C4** — las 3 `FlagSpec` declaraban `requires=` sin sumar la arista a `_REQUIRES_MAP_FROZEN`
  (rojo) y la cadena APPLY→PREVIEW→BOARD violaba **R4** (profundidad 2). Corregido: las 3 cuelgan
  directo del master, + 3 aristas congeladas.
- **C5** — el criterio binario de F0 misdiagnosticaba su propio fallo. Corregido: los 5 tests
  nombrados con su causa exacta.
- **C6** — la migración de F3 cambiaba el `sha256` del `.md` ⇒ `doc_drift=True` ⇒ los planes que el
  supervisor ya había aprobado perdían su `APROBADO` y el tablero pedía re-supervisarlos (corrida cara
  que el propio §7 declaraba fuera de scope). Corregido con la **[ADICIÓN ARQUITECTO 1]**.
- **C7** — F3 sin guardia TOCTOU: podía escribir en un offset viejo si el `.md` cambiaba entre el
  preview y el apply. Corregido: `sha256_visto` obligatorio por archivo.
- **C8** — KPI stale (78/212). Medido con la regla EXACTA del parser: **79 sin estado sobre 216**.
- **C9** — el ratchet de F2 reimplementaba la regla del parser en shell (`head -c` cuenta **bytes**,
  el parser lee 4000 **caracteres**). Corregido: fuente única + **[ADICIÓN ARQUITECTO 3]**.
- **C10** — aplicar la migración dejaba el arnés rojo hasta que el operador editara el baseline a mano.
  Corregido: el apply poda el baseline en la misma transacción.
- **C11** — F6 llamaba a `/plans-board/...` sin el prefijo `/api` y usaba `api.get` contra un 404.
- **C12** — el test 15 de F1 traía una corrección tachada adentro ("…**NO**: vuelve a…").
- **C13** — F4 hacía que una clave DESCONOCIDA se pintara "Implementado": la mentira que el plan combate.
- **C14** — el apply no invalidaba el cache de 15 s del tablero.
- **C15** — anclajes con drift (`config.py:1922`→`:1920`, `theme.css:250`→`:251`, patrón `os.getenv`).
- **C16** — F4 dejaba "verificá y decidí": ya está verificado, `actions.ts` **no se toca**.
- **C17** — sin huella de regresión. Agregada en F7.
- **C18** — no decía cómo convive con 260/264/265. Agregado el **§9**.
- **C19** — la regla 4 de F3 usaba `max(ledger)` sobre claves **string** y lanzaba con ledger vacío.
- **[ADICIÓN ARQUITECTO 1]** F2.5 — transacción de normalización de 3 patas con rollback.
- **[ADICIÓN ARQUITECTO 2]** F1.5 — `estado_origen` (enum) además del booleano.
- **[ADICIÓN ARQUITECTO 3]** F2 — test de fuente única de la regla de estado (borde multibyte).

---

## 1. Objetivo y KPI

El Tablero de Planes muestra hoy **79 planes con estado `SIN_ESTADO`** (sobre **220** documentos
catalogados el 2026-07-27, ≈36 %), y para esos 79 la
UI no ofrece **ninguna** acción: `allowedActionsForCard("SIN_ESTADO", null)` devuelve `[]`
(`frontend/src/plansBoard/actions.ts:19-30`, test en `frontend/src/plansBoard/__tests__/actions.test.ts:18-19`).
Son planes invisibles al pipeline: no se pueden criticar, ni implementar, ni supervisar desde el
tablero. Además, el tablero es **sordo al sistema de densidad global** del Plan 150: **31 de 46**
declaraciones de espaciado de `PlansBoardPage.module.css` están hardcodeadas en `rem`/`px` y no
responden al toggle cómodo/compacto, por lo que en pantallas chicas el tablero desperdicia altura y
muestra menos cards.

Este plan cierra las dos cosas con un solo criterio: **un plan nunca tiene estado nulo**. Se aplica
`IMPLEMENTADO` como fallback determinista, se marca explícitamente **de dónde salió** el estado
(para no mentir), se ofrece una migración a disco con evidencia y confirmación humana, y se instala un
ratchet que impide que un plan nuevo nazca sin estado.

> **v2 / C8 + v3 / C10 — los KPI son valores MEDIDOS, no constantes de fe.** Se miden con la regla
> EXACTA del parser (`_ESTADO_RE` + `_HEADER_READ_CHARS=4000` de `services/plans_board.py:25,30`) **y
> con el mismo `_PLAN_FILE_RE` del tablero** (`plans_board.py:23`), no con un grep aproximado ni con
> una regex copiada a mano. El v1 decía 78/212 y no era reproducible; el v2 fijó `total 216` y **el
> mismo día el comando imprime 220** (nacieron los planes 266-269). Moraleja: **el total es una
> variable, no un dato del plan**. El implementador **vuelve a medir al arrancar** con el comando de
> §1.1 y usa **su** número como línea base; el criterio binario es el **0** final, no el 79.

### 1.1 Comando de medición (correr ANTES de F0 y anotar el resultado)

```powershell
& "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); import pathlib; from services.plans_board import _ESTADO_RE, _HEADER_READ_CHARS, _PLAN_FILE_RE; d=pathlib.Path('Stacky Agents/docs'); fs=sorted(p for p in d.iterdir() if p.is_file() and _PLAN_FILE_RE.match(p.name)); sin=[p.name for p in fs if not _ESTADO_RE.search(p.open('r',encoding='utf-8',errors='replace').read(_HEADER_READ_CHARS))]; print('total', len(fs), '| sin estado', len(sin))"
```

Salida medida el 2026-07-27: `total 220 | sin estado 79`. **El `220` cambia con cada plan nuevo; el
`79` es el que importa.** (v3/C6: este comando usa `_PLAN_FILE_RE` **importado**, no una copia.)

| KPI | Antes (medido 2026-07-27) | Después (criterio binario) |
|---|---|---|
| **KPI-1** Planes sin acción disponible en el tablero | **79** | **0** |
| **KPI-2** Declaraciones de espaciado sordas a la densidad en `PlansBoardPage.module.css` | **31** | **0** |
| **KPI-3** `estado_efectivo` con valor `SIN_ESTADO` en la respuesta de `/api/plans-board/list` | **79** | **0** |
| **KPI-4** Planes nuevos que pueden guardarse sin `**Estado:**` sin que nada avise | ilimitado | **0** (ratchet rojo) |
| **KPI-5** Cards visibles sin scroll en el tablero a 1080 px de alto, densidad `compacto` | ~7 | **≥ 11** |
| **KPI-6** *(v2/C6)* Planes aprobados por el supervisor que la normalización des-aprueba | n/a | **0** |
| **KPI-7** *(v3/ADICIÓN 4)* Estados escritos a disco **sin evidencia verificable** | **45** (lo que habría escrito el v2) | **0** |
| **KPI-8** *(v3/C5)* Entradas del ledger dañadas o perdidas por la normalización (sobre 47) | n/a | **0** |

Comandos que miden KPI-1..KPI-4 y KPI-6..KPI-8: ver §8 (DoD).

---

## 2. Por qué ahora / gap que cierra

Los últimos planes leídos (255 fallas mudas, 256 intake sin pérdida, 257 observabilidad antirruido,
258 telemetría veraz, 259 alta de proyecto GitLab) comparten una misma tesis: **ningún artefacto puede
quedar en un limbo silencioso**. El 256 lo dice para los artefactos de intake, el 258 para los ledgers.
El Tablero de Planes es el último lugar donde ese limbo sigue vivo: 216 documentos catalogados,
parseados y mostrados, 79 de ellos clasificados en un estado que la propia UI trata como "no hacer nada".

El Plan 237 construyó el triage y el Plan 196 (IMPLEMENTADO F0..F6, 2026-07-26) le puso los botones de
acción. Ambos asumieron que el estado del documento era confiable. No lo es: el 36,6 % de los planes
nunca escribió su línea `**Estado:**`. Este plan cierra ese supuesto sin tocar el diseño de 237/196.

**El fallback elegido no es arbitrario y no rompe el pipeline.** Con `IMPLEMENTADO`, un plan huérfano
cae en el bucket `SIN_SUPERVISAR` (`services/plans_board.py:58`) y su acción sugerida pasa a ser
**"Supervisar"** (`services/plans_board.py:525-534`). El supervisor
(`/supervisar-implementaciones-planes`) es exactamente la herramienta que **audita el código y
determina el estado real**. Es decir: el fallback no inventa una verdad, **rutea el plan hacia la
auditoría que la resuelve**. Ese es el argumento arquitectónico central de este plan.

> **Riesgo declarado por escrito (R1, §6):** el fallback muestra como "Implementado (inferido)" planes
> que **no** están implementados. Por eso el fallback **nunca** se aplica en silencio: viaja siempre
> acompañado de `estado_origen: "inferido"` (y su derivado `estado_inferido: true`), la UI lo rotula
> "inferido" y la acción sugerida dice explícitamente que el estado no está declarado. La verdad se
> escribe a disco sólo por la migración con evidencia de F3, que es opt-in, confirmada y —desde el
> v3— **incapaz de escribir una propuesta sin evidencia** (ADICIÓN ARQUITECTO 4).
>
> *v3/C15 — los ejemplos del v2 no verificaban.* El v2 citaba `243, 247..252` como "verificablemente no
> implementados": medido el 2026-07-27, **243/247/248/249 ni siquiera están en el conjunto sin estado**
> (declaran el suyo) y **250/251/252 sí traen su registro de implementación con tests en verde**. No se
> reemplazan por otros nombres propios: el riesgo es real sin necesidad de ejemplos que envejecen.

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad.** Todo lo de este plan es Python del servidor + TypeScript de la app + CSS:
   **no invoca ningún modelo**. Corre idéntico bajo Codex CLI, Claude Code CLI y GitHub Copilot Pro.
   El único punto que dispara una corrida es el botón "Supervisar" **ya existente** del Plan 196, que ya
   tiene su propia paridad. **Fallback por runtime explícito: ninguno necesario** — no hay ninguna rama
   de código que dependa del runtime activo, así que no hay nada que degradar; si el runtime activo no
   soporta la acción "Supervisar", eso ya lo resuelve el Plan 196 y este plan no lo altera.
2. **Cero trabajo extra para el operador.** F1, F1.5, F2, F4 y F5 son automáticos e invisibles.
   F3/F6 (escritura a disco) es opt-in con flag **OFF** citando la categoría **(B)**. *v2/C10:* aplicar
   la migración **no** deja tarea manual pendiente — la poda del baseline y el re-sellado del ledger van
   dentro de la misma operación.
3. **Human-in-the-loop innegociable.** La migración de F3 **nunca** corre sola: requiere flag encendida
   + selección explícita archivo por archivo + diff a la vista + confirmación. No hay barrido, ni daemon,
   ni autocorrección, ni "aplicar a todos" implícito.
4. **Mono-operador sin auth.** Nada de RBAC ni multiusuario. El `confirm: true` del body **no** es
   seguridad: es un seguro contra el click accidental y contra un cliente mal escrito.
5. **Backward-compatible.** `SIN_ESTADO` sigue existiendo en el tipo `EstadoPlan`, en `ESTADO_CHIP` y en
   `_ESTADO_A_BUCKET` como defensa: un deploy viejo de la app contra un servidor nuevo (o al revés) no
   rompe. Las firmas públicas de `services/plans_board.py` no cambian de forma incompatible: los
   parámetros nuevos son *keyword-only con default*, y las claves nuevas del card son **aditivas**.
6. **Reusar lo existente.** Densidad: tokens `--space-*` del Plan 150 (`frontend/src/theme.css:100-108`
   y `:251-259`). Ratchet: patrón de baseline JSON ya usado por `silence_ratchet_baseline.json` y
   `uiDebtBaseline.json`. Regla de estado **y regla de qué archivo es un plan**: **se importan** de
   `services/plans_board.py` (`_ESTADO_RE`, `_HEADER_READ_CHARS`, `_PLAN_FILE_RE`), no se reimplementan
   —ni en Python, ni en shell, ni en un comando de una línea (v3/C6). Parser, tablero, triage y
   acciones de 128/237/196: **no se reescriben**.
7. **No degradar.** F1 es aritmética pura sobre datos ya parseados: **cero I/O nuevo**, cero llamadas de
   red, cero costo. El cache TTL de 15 s (`services/plans_board.py:698`) no se toca, sólo se **invalida**
   explícitamente después de una escritura (v2/C14).

---

## 4. Glosario

| Término | Significado en este plan |
|---|---|
| **estado normalizado** | Salida de `normalize_estado()` (`services/plans_board.py:73-86`): uno de `PROPUESTO`, `CRITICADO`, `IMPLEMENTADO`, `IMPLEMENTADO_PARCIAL`, `SIN_ESTADO`. |
| **estado resuelto** | **NUEVO**: el normalizado, salvo que sea `SIN_ESTADO` → entonces `IMPLEMENTADO`. Lo calcula `resolve_estado()`. |
| **estado efectivo** | Ya existe (`services/plans_board.py:568`): el resuelto, salvo que el ledger lo apruebe sin drift → entonces `APROBADO`. Es lo que consume la UI. |
| **estado origen** | **NUEVO (v2, ADICIÓN ARQUITECTO 2)**: `"declarado"` \| `"inferido"` \| `"ledger"`. Explica **de dónde salió el valor de `estado_efectivo`**: `"ledger"` = lo puso el veredicto del supervisor; `"inferido"` = lo puso el fallback del 263; `"declarado"` = salió tal cual del parser del documento. Es el **único** campo con la verdad. |
| **estado inferido** | **NUEVO**: booleano derivado, **exactamente `estado_origen == "inferido"`** — ni más ni menos (v3/C3). Existe sólo por comodidad del consumidor. Un plan sin `**Estado:**` **pero aprobado en el ledger** tiene `estado_origen == "ledger"` y por lo tanto `estado_inferido is False`: el ledger ya dijo la verdad y no hay nada inferido en pantalla. |
| **ledger** | `Stacky Agents/docs/_supervision/ledger.json`: qué planes aprobó el supervisor, con el sha256 del doc. Claves = número de plan **como string**. |
| **drift del doc** | El sha256 actual del `.md` ≠ el que registró el supervisor ⇒ el doc cambió después de aprobarse (`services/plans_board.py:454-463`). |
| **re-sellado del ledger** | **NUEVO (v2)**: tras normalizar un `.md`, actualizar su `doc_sha256` en el ledger para que el cambio cosmético **no** cuente como drift. |
| **bucket de triage** | Etapa del Plan 237: `SIN_IMPLEMENTAR`, `SIN_CRITICAR`, `SIN_DOCUMENTO`, `SIN_SUPERVISAR`, `COMPLETADO`. |
| **ratchet** | Test que congela una deuda conocida en un baseline JSON y **falla si crece**. Sólo se puede achicar. |
| **densidad** | Sistema del Plan 150: `<html data-density="compacto">` re-apunta los tokens `--space-*`. |

---

## 5. Fases

### F0 — Flags: las SEIS patas, exactas

**Objetivo.** Dar de alta las 3 flags del plan sin romper **ninguno** de los meta-tests del arnés.

> **v2 / C1-C5 — por qué esta fase se reescribió entera.** El v1 declaraba "Archivos a editar (3,
> exactos)" y esos 3 no alcanzaban: una flag de Stacky tiene **seis patas**, y el v1 acertaba dos.
> Además mandaba las keys ON a un archivo equivocado y declaraba `default=False` en la flag OFF, que es
> el error que el propio código ya documenta como prohibido. Con el v1, F0 arrancaba con **cinco tests
> rojos** y un criterio binario que culpaba a la causa equivocada.

**Las 6 patas (todas obligatorias; saltarse una = arnés rojo):**

| # | Archivo | Qué se agrega | Test que se pone rojo si falta |
|---|---|---|---|
| 1 | `backend/config.py` | los 3 `os.getenv` (default efectivo) | ninguno directo, pero la flag no existe |
| 2 | `backend/services/harness_flags.py` (`FLAG_REGISTRY`) | las 3 `FlagSpec` | ninguno directo |
| 3 | `backend/services/harness_flags.py` (`_CATEGORY_KEYS`, cat. `"observabilidad_notif"`, abre en `:309`) | las **3** keys | `test_every_registry_flag_is_categorized` (`tests/test_harness_flags.py:929`) |
| 4 | **`backend/tests/test_harness_flags.py`** (`_CURATED_DEFAULTS_ON`, abre en **`:467`**) | **sólo las 2 ON** | `test_default_known_only_for_curated` (`tests/test_harness_flags.py:1001`) |
| 5 | `backend/services/harness_flags_help.py` (`PLAIN_HELP`, abre en `:25`) | las **3** entradas | `test_plain_help_covers_all_registry_keys` (`tests/test_harness_flags_help.py:32`) |
| 6 | `backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`) | las **3** aristas | `test_requires_map_is_frozen` (`tests/test_harness_flags_requires.py:326`) |

> **v4 / C1 — toda la columna de números de esta tabla se re-midió el 2026-07-29** (ver CHANGELOG). Tres
> de las seis celdas de línea habían corrido (`:305`→`:309`, `:902`→`:929`, `:974`→`:1001`); una más
> corrió dentro del propio archivo de requires (`:312`→`:326`, la vieja cifra ya no apunta ni siquiera a
> ese archivo: cae en un comentario de la costura de la OLA 1/P0). **Ninguno de estos números es
> load-bearing**: son para ubicarte rápido, no para copiar-pegar un offset. Confirmá con
> `Select-String -Pattern "def test_nombre"` antes de asumir que el número de esta tabla sigue vigente.

---

#### F0.1 — `backend/config.py`

> **v4 / C1 — este archivo lo edita CADA plan del repo; el número de línea es ilustrativo, no
> autoritativo.** `config.py` es, junto con `harness_flags.py`, el archivo de mayor concurrencia del
> arnés. Medido el **2026-07-29** (dos días después de escrito este documento): el bloque
> `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED` ya no está en `:1918-1920` — vive en `:1930-1935`, corrido
> por las flags que sumaron los planes 267/268/269/270 al mergearse a `main` en el ínterin. Insertar de
> forma literal "después de la línea 1920" **hoy caería dentro de la llamada `os.getenv(...)` de
> `STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED`** (ese bloque ocupa hoy `:1916-1922`) y partiría una
> llamada a función en dos: `SyntaxError` que tira abajo **todo `config.py`** y, con él, todo el
> backend. Por eso la ubicación se busca por marcador de texto, **nunca por número crudo**:

**Paso 1 — ubicar el marcador real con el archivo abierto o con el comando, nunca de memoria:**

```powershell
Select-String -Path "Stacky Agents\backend\config.py" -Pattern "Plan 167 .. Centro de Evolucion|STACKY_PLANS_PIPELINE_ACTIONS_ENABLED"
```

Insertar el bloque nuevo **inmediatamente antes** de la línea que matchea `# ── Plan 167 —` (encabezado
del bloque `STACKY_EVOLUTION_CENTER_ENABLED`) — es decir, justo después de que termine el bloque
`STACKY_PLANS_PIPELINE_ACTIONS_ENABLED` (su última línea es `).strip().lower() == "true"`, seguida de
una línea en blanco). Medido hoy 2026-07-29 eso cae entre `:1935` y `:1937`; **ese número puede haber
vuelto a correrse para cuando vos lo implementes** — por eso el criterio es el comando de arriba, no el
número:

```python
    # ── Plan 263 — el tablero nunca muestra un plan con estado nulo. Calculo
    #    puro en memoria sobre datos ya parseados: sin I/O, sin red, sin costo. ──
    STACKY_PLANS_ESTADO_FALLBACK_ENABLED: bool = os.getenv(
        "STACKY_PLANS_ESTADO_FALLBACK_ENABLED", "true"
    ).strip().lower() == "true"

    # ── Plan 263 — vista previa de normalizacion de estados (SOLO LECTURA). ──
    STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED: bool = os.getenv(
        "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED", "true"
    ).strip().lower() == "true"

    # ── Plan 263 — escritura de la linea de estado en los .md del operador.
    #    Nace OFF por CATEGORIA (B): escribe en un sistema REAL del operador. ──
    STACKY_PLANS_NORMALIZE_APPLY_ENABLED: bool = os.getenv(
        "STACKY_PLANS_NORMALIZE_APPLY_ENABLED", "false"
    ).strip().lower() == "true"
```

> **v2 / C15:** el patrón real vigente en ese bloque es `.strip().lower() == "true"` (re-verificado el
> 2026-07-29 sobre `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED`, hoy en `:1933-1935`), **no**
> `in ("1", "true", "yes")` como decía el v1 — aunque **las dos formas conviven** en el archivo real
> (p. ej. `STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED`, hoy en `:1920-1922`, sigue usando
> `in ("1", "true", "yes")`). Copiá el patrón `.strip().lower() == "true"` de arriba tal cual: es el que
> corresponde a este bloque. Si el archivo real difiere del snippet, **gana el archivo**.

#### F0.2 — `backend/services/harness_flags.py` · las 3 `FlagSpec`

> **v4 / C1 (continuación) — mismo drift, mismo tipo de archivo.** El `FlagSpec` de
> `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED` que este plan usa como ancla ya no cierra en `:4544-4558`:
> medido el 2026-07-29 cierra en `:4616` (**+58 líneas** — la misma magnitud que ya había anticipado el
> gotcha del repo sobre `_REQUIRES_MAP_FROZEN`, 143→146, y sobre este mismo eje en F0.1). Ubicá el
> punto de inserción por texto:

```powershell
Select-String -Path "Stacky Agents\backend\services\harness_flags.py" -Pattern 'key="STACKY_PLANS_PIPELINE_ACTIONS_ENABLED"|Plan 167 .. Centro de Evolucion'
```

Agregar **inmediatamente después** del `),` que cierra el `FlagSpec` de
`STACKY_PLANS_PIPELINE_ACTIONS_ENABLED` (su última línea antes del cierre es
`requires="STACKY_PLANS_BOARD_ENABLED",`) y **antes** del comentario `# ── Plan 167 —`. Medido hoy
2026-07-29 eso cae entre `:4616` y `:4617`; de nuevo, el comando de arriba es el criterio, no el número:

```python
    # ── Plan 263 — ningun plan sin estado + migracion con evidencia ──────────
    FlagSpec(
        key="STACKY_PLANS_ESTADO_FALLBACK_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON (tests/test_harness_flags.py).
        label="Ningun plan sin estado en el tablero",
        description=(
            "Plan 263 — Un plan cuyo documento no declara **Estado:** se muestra como "
            "IMPLEMENTADO (inferido) en vez de 'Sin estado', para que el tablero le "
            "ofrezca la accion Supervisar. Calculo puro en memoria, no toca el disco."
        ),
        group="global",
        requires="STACKY_PLANS_BOARD_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON (tests/test_harness_flags.py).
        label="Vista previa de normalizacion de estados",
        description=(
            "Plan 263 — Calcula, SOLO EN MEMORIA, que linea **Estado:** habria que "
            "escribir en cada plan sin estado, con la evidencia que la respalda "
            "(ledger, contenido del doc, numero del plan). No escribe nada."
        ),
        group="global",
        requires="STACKY_PLANS_BOARD_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PLANS_NORMALIZE_APPLY_ENABLED",
        type="bool",
        # SIN default=: el default EFECTIVO es el de config.py ("false"). Declararlo
        # aca —aunque fuera default=False— la volveria default_is_known
        # (services/harness_flags.py: `spec.default is not None`; False NO es None) y
        # pondria ROJO a test_default_known_only_for_curated, que exige igualdad EXACTA
        # con el conjunto curado. Precedente identico y ya vivo en este archivo:
        # STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED (Plan 250). v4/C1: NO ancles por numero
        # de linea (empieza en :3166 en el v3, en :3224 medido 2026-07-29): ubicalo con
        # Select-String -Pattern 'STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED'.
        #
        # OFF por CATEGORIA (B): escribe en un sistema REAL del operador — los .md de
        # "Stacky Agents"/docs/ en su working tree, que ademas suele tener cambios sin
        # commitear. La escritura vive en
        # services/plans_estado_migration.py::apply_estado_migration.
        label="Aplicar la normalizacion de estados a los .md",
        description=(
            "Plan 263 — Escribe la linea **Estado:** en los planes que no la tienen, "
            "uno por uno, con confirmacion y diff a la vista. Nunca corre sola. "
            "El commit y el push siguen siendo manuales."
        ),
        group="global",
        requires="STACKY_PLANS_BOARD_ENABLED",
    ),
```

> **v2 / C4 — por qué las 3 cuelgan del MISMO master.** El v1 hacía
> `APPLY → PREVIEW → PLANS_BOARD`, una cadena de **profundidad 2**, prohibida por **R4**. El precedente
> literal está en el propio arnés (`tests/test_harness_flags_requires.py:265-266`): las hijas de visión
> del Plan 166 apuntan al ROOT y no a su hermana, "R4 prohíbe cadenas de profundidad >1".
> El candado real —que APPLY exija PREVIEW— **no** se expresa con `requires` (que es metadata
> informativa para la UI: `requires_met` no lo evalúa ningún runner): se chequea en el código del
> handler, exactamente como hizo el Plan 250 con `api/pipeline_editor.py`. Ver F3.

#### F0.3 — `backend/services/harness_flags.py` · `_CATEGORY_KEYS`

Agregar las **3** keys en la categoría `"observabilidad_notif"` (abre en `harness_flags.py:309`,
re-medido 2026-07-29 — drift menor de +4 líneas respecto del v3; anclá por el nombre de la categoría,
no por el número), junto a `"STACKY_PLANS_PIPELINE_ACTIONS_ENABLED"` (`harness_flags.py:359`):

```python
        "STACKY_PLANS_ESTADO_FALLBACK_ENABLED",      # Plan 263 — ningun plan sin estado
        "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED",    # Plan 263 — vista previa (solo lectura)
        "STACKY_PLANS_NORMALIZE_APPLY_ENABLED",      # Plan 263 — escritura HITL en los .md
```

> `test_every_registry_flag_is_categorized` (`tests/test_harness_flags.py:902`) exige **biyección
> completa** registry ↔ `_CATEGORY_KEYS`: las **3**, incluida la OFF.

#### F0.4 — `backend/tests/test_harness_flags.py` · `_CURATED_DEFAULTS_ON`

**Archivo distinto al anterior.** El conjunto curado abre en **`tests/test_harness_flags.py:467`**.
Agregar **sólo las dos ON**:

```python
    "STACKY_PLANS_ESTADO_FALLBACK_ENABLED",     # Plan 263 — calculo puro en memoria, solo lectura
    "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED",   # Plan 263 — vista previa, no escribe nada
```

> `STACKY_PLANS_NORMALIZE_APPLY_ENABLED` **NO** va acá (nace OFF y **no declara `default=`**).
> Meterla acá con la `FlagSpec` sin `default=` deja el test rojo por "Faltantes"; declararle
> `default=False` y no meterla lo deja rojo por "Extras". Las dos cosas juntas son la única
> combinación verde: **sin `default=` y fuera del conjunto**.

#### F0.5 — `backend/services/harness_flags_help.py` · `PLAIN_HELP`

Agregar las **3** entradas (el dict abre en `harness_flags_help.py:25`), junto a la del Plan 196
(`:1459`). Texto ya validado contra los gates de `tests/test_harness_flags_help.py`:
`on_effect`/`off_effect` empiezan con `"Si "`, todos los campos ≤ los límites (200/240/240/300), sin
ninguna palabra de `JARGON_DENYLIST` (`tests/test_harness_flags_help.py:17-20`), sin nombres en
MAYÚSCULAS_CON_GUION_BAJO y sin referencias del tipo `F` + dígito.

```python
    # ── Plan 263 — ningun plan sin estado ────────────────────────────────────
    "STACKY_PLANS_ESTADO_FALLBACK_ENABLED": PlainHelp(
        what="Decide que muestra el tablero de planes cuando el documento de un plan no dice en que etapa esta.",
        on_effect="Si la activas (viene asi de fabrica): esos planes aparecen como implementados y marcados 'inferido', con el boton de supervisar disponible para confirmarlo.",
        off_effect="Si la apagas: esos planes vuelven a mostrarse como 'Sin estado' y quedan sin ninguna accion disponible, como antes.",
        example="Como una carpeta sin etiqueta: en vez de dejarla en el limbo, la ponés en 'a revisar' para que alguien la clasifique.",
    ),
    "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED": PlainHelp(
        what="Arma una vista previa de que etapa habria que anotar en cada plan que no la declara, con la evidencia que respalda cada propuesta.",
        on_effect="Si la activas (viene asi de fabrica): el tablero lista los planes sin etapa declarada, la etapa propuesta para cada uno y por que. No modifica ningun archivo.",
        off_effect="Si la apagas: ese panel desaparece y el tablero queda igual que antes, sin propuesta de normalizacion.",
        example="Como el presupuesto que te pasa el mecanico antes de tocar el auto: te dice que haria y por que, pero todavia no hizo nada.",
    ),
    "STACKY_PLANS_NORMALIZE_APPLY_ENABLED": PlainHelp(
        what="Permite que la app escriba en los documentos de los planes la linea que declara su etapa.",
        on_effect="Si la activas: se habilita el boton que escribe esa linea en los documentos que elijas, de a uno, mostrandote antes el cambio exacto y pidiendote confirmacion.",
        off_effect="Si la apagas (viene asi de fabrica): el boton queda deshabilitado y ningun documento se modifica; solo podes ver la propuesta.",
        example="Como firmar vos mismo el formulario: la app te lo completa y te lo muestra, pero la lapicera la agarras vos.",
    ),
```

#### F0.6 — `backend/tests/test_harness_flags_requires.py` · `_REQUIRES_MAP_FROZEN`

Agregar las **3** aristas al final del dict (antes del `}` de cierre), con su comentario:

```python
    # Plan 263: las tres capas del tablero de planes cuelgan del master del tablero
    # (profundidad 1; STACKY_PLANS_BOARD_ENABLED no declara `requires`). El candado
    # real "APPLY exige PREVIEW" lo chequea api/plans_board.py por su cuenta (patron
    # del Plan 250): la arista es INFORMATIVA para la UI.
    "STACKY_PLANS_ESTADO_FALLBACK_ENABLED": "STACKY_PLANS_BOARD_ENABLED",
    "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED": "STACKY_PLANS_BOARD_ENABLED",
    "STACKY_PLANS_NORMALIZE_APPLY_ENABLED": "STACKY_PLANS_BOARD_ENABLED",
```

**Tests (correr, no escribir nuevos):**

```powershell
$py = "Stacky Agents\backend\.venv\Scripts\python.exe"
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_help.py" -q
```

**Criterio binario (v3 / C4 — reescrito: "los tres exit 0" era IMPOSIBLE).**

`test_harness_flags.py` y `test_harness_flags_requires.py` deben salir **exit 0** (medido el
2026-07-27 en el árbol limpio: **56 passed** y **9 passed** respectivamente — están verdes, un rojo ahí
**es tuyo**).

`test_harness_flags_help.py` **NO puede salir exit 0 y no es culpa de este plan**: medido el
2026-07-27 trae **4 fallos preexistentes ajenos**, y el primero es
`test_plain_help_covers_all_registry_keys` con **79 flags del registry sin entrada en `PLAIN_HELP`**
(`STACKY_DB_COMPARE_*`, `STACKY_UI_*`, `STACKY_COST_*`, …). Por eso su criterio binario es **por
entrada propia**, con este comando —que no depende del rojo ajeno—:

```powershell
& "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.harness_flags_help import PLAIN_HELP; ks=['STACKY_PLANS_ESTADO_FALLBACK_ENABLED','STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED','STACKY_PLANS_NORMALIZE_APPLY_ENABLED']; import re; DENY=('MCP','TF-IDF','LLM','stdin','stdout','endpoint','frontmatter','prompt','token','regex','backend','frontend','gate','hook','runtime'); bad=[]; [bad.append((k,'falta')) for k in ks if k not in PLAIN_HELP]; [ (lambda e: [bad.append((k,m)) for m in ([] if e.on_effect.startswith('Si ') else ['on_effect no empieza con Si ']) + ([] if e.off_effect.startswith('Si ') else ['off_effect no empieza con Si ']) + ([] if len(e.what)<=200 else ['what>200']) + ([] if len(e.on_effect)<=240 else ['on>240']) + ([] if len(e.off_effect)<=240 else ['off>240']) + ([] if len(e.example)<=300 else ['ex>300']) + [f'jerga:{t}' for f in (e.what,e.on_effect,e.off_effect,e.example) for t in DENY if re.search(rf'\b{re.escape(t)}s?\b',f,re.I)] + [f'key SCREAMING:{f[:20]}' for f in (e.what,e.on_effect,e.off_effect,e.example) if re.search(r'\b[A-Z]+_[A-Z0-9_]+\b',f)] + [f'fase F<n>:{f[:20]}' for f in (e.what,e.on_effect,e.off_effect,e.example) if re.search(r'\bF\d',f)])])(PLAIN_HELP[k]) for k in ks if k in PLAIN_HELP]; print('OK' if not bad else bad)"
```

Debe imprimir **`OK`**. Y el **delta** del archivo entero tiene que ser cero: corré
`pytest tests/test_harness_flags_help.py -q` **antes** de tocar nada y **después**, y el conteo
`N failed` debe ser **el mismo (4)**. Si sube, el rojo nuevo es tuyo. **No adoptes la deuda ajena de
las 79 flags sin ayuda llana: está fuera de scope (§7).**

Si algo se pone rojo, la causa es **una de estas cinco y sólo estas cinco**:

| Test rojo | Causa exacta | Pata que falta |
|---|---|---|
| `test_default_known_only_for_curated` → **"Extras (no curadas)"** | una flag `default=True` (o `default=False`, que también cuenta como *conocido*) no está en el conjunto | F0.4 — o le sobra el `default=` a la flag OFF |
| `test_default_known_only_for_curated` → **"Faltantes"** | una key está en el conjunto curado pero su `FlagSpec` no declara `default=` | F0.2 / F0.4 desalineados |
| `test_every_registry_flag_is_categorized` | falta una de las 3 keys en `_CATEGORY_KEYS` | F0.3 |
| el comando de arriba imprime `('STACKY_PLANS_…','falta')` | falta una de las 3 entradas de ayuda llana | F0.5 |
| `test_requires_map_is_frozen` → **"Extras"** | la `FlagSpec` declara `requires=` y la arista no está congelada | F0.6 |

> **Ojo, rojo ajeno MEDIDO (v3/C4):** `test_harness_flags_help.py` sale **4 failed / 4 passed** en el
> árbol limpio del 2026-07-27 (`test_plain_help_covers_all_registry_keys`,
> `test_plain_help_fields_non_empty_and_bounded`, `test_plain_help_on_off_start_with_si`,
> `test_plain_help_avoids_jargon_denylist`). No hace falta un worktree para saberlo: está medido acá.
> Lo que sí hace falta es que **tu delta sea cero**. Los tuyos son sólo los que nombran una de tus 3
> keys. **No adoptes deuda ajena y no la escondas en una allowlist.**

**Flags:** las 3 del plan. 2 ON (cálculo puro / solo lectura) y 1 OFF con justificación de
**categoría (B)** escrita en el propio código.
**Impacto por runtime:** ninguno — son flags de configuración, sin llamada a modelo.
**Trabajo del operador: ninguno.**

---

### F1 — Servidor: `resolve_estado()` y el fallback único (núcleo puro, TDD)

**Objetivo.** Que ningún card salga de `build_board()` con `estado_efectivo == "SIN_ESTADO"`, y que
todo card diga **de dónde salió** su estado.

**Archivo a editar:** `Stacky Agents/backend/services/plans_board.py`.

**Test PRIMERO.** Crear `Stacky Agents/backend/tests/test_plan263_estado_fallback.py` con estos casos
exactos:

| # | Caso | Aserción |
|---|---|---|
| 1 | `resolve_estado("PROPUESTO")` | `== ("PROPUESTO", False)` |
| 2 | `resolve_estado("CRITICADO")` | `== ("CRITICADO", False)` |
| 3 | `resolve_estado("IMPLEMENTADO")` | `== ("IMPLEMENTADO", False)` |
| 4 | `resolve_estado("IMPLEMENTADO_PARCIAL")` | `== ("IMPLEMENTADO_PARCIAL", False)` |
| 5 | `resolve_estado("SIN_ESTADO")` | `== ("IMPLEMENTADO", True)` |
| 6 | `resolve_estado("")` | `== ("IMPLEMENTADO", True)` |
| 7 | `resolve_estado(None)` | `== ("IMPLEMENTADO", True)` (no lanza) |
| 8 | `resolve_estado("BASURA_NO_RECONOCIDA")` | `== ("IMPLEMENTADO", True)` |
| 9 | `build_board(tmp_docs, None)` con un `.md` **sin** `**Estado:**` | el card tiene `estado_efectivo == "IMPLEMENTADO"`, `estado_inferido is True`, `estado_origen == "inferido"`, `triage_bucket == "SIN_SUPERVISAR"` |
| 10 | idem 9 | `card["suggested_action"]["kind"] == "supervisar"` |
| 11 | idem 9 | `"no declara" in card["suggested_action"]["natural_language"]` (la sugerencia AVISA que fue inferido) |
| 12 | `build_board` con un `.md` **con** `**Estado:** PROPUESTO v1` | `estado_inferido is False`, `estado_origen == "declarado"`, `estado_efectivo == "PROPUESTO"` |
| 13 | *(v3/C3 — CAMBIÓ)* `build_board` sobre un doc **sin** estado **pero aprobado en el ledger sin drift** | `estado_efectivo == "APROBADO"` (el ledger sigue ganando), `estado_origen == "ledger"` y **`estado_inferido is False`**. El v2 pedía `True` acá y eso hacía que el chip de la app dijera **"Aprobado (inferido)"**: el ledger ya dijo la verdad, no hay nada inferido en pantalla. |
| 14 | `build_board(tmp_docs, None)` sobre 3 docs sin estado | `"SIN_ESTADO" not in board["totals"]` y `board["totals"]["inferidos"] == 3` |
| 15 | **flag OFF** (`monkeypatch.setattr(config.config, "STACKY_PLANS_ESTADO_FALLBACK_ENABLED", False)`) sobre el mismo doc del caso 9 | **una sola aserción:** `card["estado_efectivo"] == "SIN_ESTADO"`, `card["estado_inferido"] is False`, `card["estado_origen"] == "declarado"`, `card["suggested_action"]["kind"] == "revisar"` — es decir, el comportamiento **byte-idéntico al de antes de este plan (263)** |
| 16 | *(v2)* `build_planned_cards` (bucket `SIN_DOCUMENTO`) | cada card trae `estado_inferido is False` y `estado_origen == "declarado"` — **todas** las cards tienen la misma forma |
| 17 | *(v2)* `suggest_next_action("IMPLEMENTADO", None, None, "07")` llamado **posicionalmente con 4 args** | no lanza `TypeError` y devuelve `kind == "supervisar"` (prueba de que el parámetro nuevo es keyword-only con default) |
| 18 | **[v3/C3 — INVARIANTE]** `build_board` sobre un `tmp_path` con los 4 tipos de card a la vez (uno declarado, uno sin estado, uno sin estado + ledger aprobado, uno `SIN_DOCUMENTO` del roadmap) | para **TODAS** las cards del board: `card["estado_inferido"] == (card["estado_origen"] == "inferido")`, y `card["estado_origen"] in ("declarado","inferido","ledger")`. Un solo `for` sobre `board["plans"]`. Este test es el que impide que los dos campos vuelvan a divergir. |
| 19 | **[v4/ADICIÓN 6]** sobre el mismo board de 4 cards del caso 18 | `sum(board["totals"]["por_origen"].values()) == len(board["plans"])` — todas las cards tienen `estado_origen` (invariante ya fijada por el caso 18), así que el desglose es una partición completa sin resto. |

> **v2 / C12:** el v1 escribía el caso 15 con una corrección tachada adentro ("vuelve a
> `"IMPLEMENTADO"`… **NO**: vuelve a `"SIN_ESTADO"`"). Un modelo menor no puede saber cuál gana. La
> aserción correcta es `"SIN_ESTADO"`. Y el comportamiento de referencia es el **pre-263** (el Plan 260
> es de pipelines y no toca nada de esto).

> **v3 / C13 — por qué `estado_origen` dice `"declarado"` con la flag OFF y un doc sin estado.**
> `estado_origen` no responde "¿el doc declaraba algo?" sino **"¿de dónde salió el valor que estás
> viendo en `estado_efectivo`?"**. Con la flag OFF, ese valor (`"SIN_ESTADO"`) salió **tal cual del
> parser del documento**, así que `"declarado"` es correcto y no hace falta un cuarto valor del enum
> (que rompería el tipo de F4). El "no declara nada" ya está dicho, y con precisión, por el propio
> `estado_efectivo == "SIN_ESTADO"`.

> **Aviso al implementador (gotcha conocido del repo):** para leer la flag usá
> **`config.config.STACKY_PLANS_ESTADO_FALLBACK_ENABLED`** (la *instancia*), no `config.STACKY_...`
> (el *módulo*). El módulo devuelve el default y mata la rama OFF, dejando el caso 15 en falso verde.

**Cambios (diff ilustrativo).**

(a) Constantes nuevas, después de `plans_board.py:34`:

```python
# ── Plan 263 — el fallback de estado, en UN solo literal ────────────────────
ESTADO_FALLBACK = "IMPLEMENTADO"
ESTADOS_VALIDOS: tuple[str, ...] = (
    "PROPUESTO", "CRITICADO", "IMPLEMENTADO", "IMPLEMENTADO_PARCIAL",
)
# Plan 263 — origen del estado que ve la UI. Ver [ADICIÓN ARQUITECTO 2].
ORIGEN_DECLARADO = "declarado"
ORIGEN_INFERIDO = "inferido"
ORIGEN_LEDGER = "ledger"
```

(b) Función nueva, inmediatamente después de `normalize_estado()` (`plans_board.py:86`):

```python
def _fallback_activo() -> bool:
    """Lee la flag por la INSTANCIA config.config. Nunca lanza."""
    try:
        import config as _config
        return bool(getattr(_config.config, "STACKY_PLANS_ESTADO_FALLBACK_ENABLED", True))
    except Exception:      # noqa: BLE001 — sin config, el fallback queda activo
        return True


def resolve_estado(estado_normalizado: str | None) -> tuple[str, bool]:
    """(estado_resuelto, fallback_aplicado).

    v3/C3: el segundo elemento NO es `estado_inferido` del card. Es "¿tuve que
    aplicar el fallback?". `estado_inferido` lo deriva build_board de
    `estado_origen`, porque el ledger puede ganarle al fallback.

    Un estado nulo, vacío, no reconocido o SIN_ESTADO resuelve a ESTADO_FALLBACK
    con inferido=True. Con la flag OFF devuelve el valor tal cual, inferido=False
    (comportamiento byte-idéntico al previo al Plan 263).
    """
    valor = (estado_normalizado or "").strip().upper()
    if valor in ESTADOS_VALIDOS:
        return valor, False
    if not _fallback_activo():
        return (valor or "SIN_ESTADO"), False
    return ESTADO_FALLBACK, True
```

(c) `suggest_next_action()` (`plans_board.py:471-543`) — parámetro **keyword-only con default** (no
rompe llamadores existentes) y sugerencia que avisa:

```python
 def suggest_next_action(
     estado: str, ledger_info: dict | None, unpushed: bool | None, number_str: str,
+    *, estado_inferido: bool = False,
 ) -> dict:
```

y reemplazar el cuerpo de la rama `IMPLEMENTADO/IMPLEMENTADO_PARCIAL` (`plans_board.py:525-534`) por:

```python
    if estado in ("IMPLEMENTADO", "IMPLEMENTADO_PARCIAL"):
        if estado_inferido:
            nl = (
                f"El doc del plan {number_str} no declara **Estado:**, así que el tablero "
                f"lo asume implementado: pedile al agente supervisar el plan {number_str} "
                "para confirmarlo contra el código y escribir el estado real."
            )
            label = "Supervisar (estado inferido)"
        else:
            nl = (
                f"Pedile al agente supervisar la implementación del plan {number_str} contra "
                "su documento y cerrar lo que falte."
            )
            label = "Supervisar"
        return {
            "kind": "supervisar",
            "label": label,
            "command": f"/supervisar-implementaciones-planes {number_str}",
            "natural_language": nl,
        }
```

> La rama final `kind="revisar"` / `"Sin estado"` (`plans_board.py:535-543`) **se conserva intacta**:
> con la flag OFF sigue siendo alcanzable (caso 15), y con la flag ON queda como defensa muerta.
> **No la borres.**

(d) `build_board()` (`plans_board.py:561-591`) — resolver **antes** de aplicar el ledger. Ojo: en el
archivo real hay una **línea en blanco** entre `:568` y `:570`; el bloque queda:

```python
-        estado_efectivo = "APROBADO" if (ledger_ok and doc_drift is not True) else c["estado"]
-
-        action = suggest_next_action(c["estado"], ledger_info, unpushed, c["number_str"])
+        estado_resuelto, fallback_aplicado = resolve_estado(c["estado"])
+        aprobado = bool(ledger_ok and doc_drift is not True)
+        estado_efectivo = "APROBADO" if aprobado else estado_resuelto
+        if aprobado:
+            estado_origen = ORIGEN_LEDGER
+        elif fallback_aplicado:
+            estado_origen = ORIGEN_INFERIDO
+        else:
+            estado_origen = ORIGEN_DECLARADO
+        # v3/C3 — UNA sola fuente de verdad: estado_inferido ES estado_origen.
+        # Nunca se asigna por separado. Un doc sin **Estado:** aprobado por el
+        # supervisor sale con origen "ledger" e inferido False: el ledger ya
+        # dijo la verdad y el chip NO debe decir "(inferido)".
+        estado_inferido = estado_origen == ORIGEN_INFERIDO
+
+        action = suggest_next_action(
+            estado_resuelto, ledger_info, unpushed, c["number_str"],
+            estado_inferido=estado_inferido,
+        )
```

y en el dict `card`, después de `"estado_efectivo": estado_efectivo,` (`plans_board.py:581`), **dos**
claves aditivas:

```python
            "estado_inferido": estado_inferido,
            "estado_origen": estado_origen,
```

(e) Totales (`plans_board.py:610-612`):

```python
    totals["inferidos"] = sum(1 for c in plans if c.get("estado_inferido"))
    # [ADICIÓN ARQUITECTO 6, v4] Desglose agregado de DÓNDE salió cada estado. Mismo
    # loop, mismo dato ya calculado por card (estado_origen, F1(d)): costo marginal
    # cero, sin I/O nuevo, sin flag nueva, aditivo. Fortalece la tesis del plan a
    # nivel portafolio: el operador ve de un vistazo cuánto de "todo implementado"
    # es verificable vs. supuesto, sin abrir el panel de F6 ni pedir un 2do request.
    totals["por_origen"] = {
        ORIGEN_DECLARADO: sum(1 for c in plans if c.get("estado_origen") == ORIGEN_DECLARADO),
        ORIGEN_INFERIDO: sum(1 for c in plans if c.get("estado_origen") == ORIGEN_INFERIDO),
        ORIGEN_LEDGER: sum(1 for c in plans if c.get("estado_origen") == ORIGEN_LEDGER),
    }
```

> **Cuidado:** las cards `SIN_DOCUMENTO` que arma `build_planned_cards()` (`plans_board.py:397-422`)
> **no** pasan por `resolve_estado`. Su `estado_efectivo` es `"SIN_DOCUMENTO"`, así que **no afectan
> KPI-3** — pero sí les falta la forma. Agregá al dict del card (junto a
> `"estado_efectivo": "SIN_DOCUMENTO", "triage_bucket": "SIN_DOCUMENTO",` en `plans_board.py:409`):
> `"estado_inferido": False, "estado_origen": "declarado",`. Aun así, en (e) se usa `.get(...)` para
> ser defensivo ante una card mal formada de un consumidor futuro.

**Comando de test:**

```powershell
& "Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan263_estado_fallback.py" -q
```

> **Gotcha del repo (SQLITE_LOCKED bajo pytest):** este archivo **no toca la DB** (usa `tmp_path` y
> funciones puras), así que no es flaky y **no necesita** `run_with_retry`. Si aun así aparece un
> `SQLITE_LOCKED`, es contaminación de otro archivo: corré **este archivo solo**, nunca la suite completa.

**Criterio binario.** 19 passed, 0 failed. Y:

```powershell
& "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.plans_board import get_board_cached; b=get_board_cached(refresh=True); print(sum(1 for p in b['plans'] if p['estado_efectivo']=='SIN_ESTADO'))"
```
debe imprimir **`0`** (KPI-3). Si imprime otra cosa, es que algún card no pasó por `resolve_estado`.

**Flag:** `STACKY_PLANS_ESTADO_FALLBACK_ENABLED`, default **ON** — cálculo puro en memoria, cero I/O,
cero costo, no escribe nada y no le saca ninguna decisión al operador: **no cae en (A) ni en (B)**.
**Impacto por runtime:** idéntico en los 3 — no invoca modelos. Sin fallback necesario.
**Trabajo del operador: ninguno.**

---

### F1.5 — `estado_origen`: por qué el card dice lo que dice **[ADICIÓN ARQUITECTO 2]**

**Objetivo.** Que la UI pueda explicar el estado sin adivinar, con **un** campo en vez de tres booleanos
derivados.

**Problema real que resuelve.** Con el v1, un card `APROBADO` y un card `IMPLEMENTADO (inferido)` se
distinguen por un booleano que además es ambiguo: un plan **sin estado declarado** pero **aprobado por
el supervisor** llega con `estado_efectivo="APROBADO"`, y la UI no tiene forma de saber que ahí el
ledger ya dijo la verdad y **no hace falta normalizar nada**. Sin este campo, el panel de F6 le propone
al operador reescribir un `.md` que ya está resuelto.

**Contrato (aditivo, backward-compatible).** `estado_origen: "declarado" | "inferido" | "ledger"` es el
**único campo con la verdad**; se computa en `build_board` (ver F1(d)). `estado_inferido` es su
**derivado literal** (`estado_origen == "inferido"`) y existe sólo por comodidad del consumidor.

> **v3 / C3 — esto NO es una redundancia inocua, es el bloqueante que tumbó al v2.** El v2 declaraba
> "azúcar de `estado_origen == 'inferido'`" en el glosario y a la vez pedía, en el caso 13,
> `estado_origen == "ledger"` **con** `estado_inferido is True`. Las dos cosas no pueden ser ciertas.
> Consecuencia medible: el `estadoChip` de F4 (`… || card.estado_inferido`) pintaba **"Aprobado
> (inferido)"** en la card real, y el test 4 de F4 salía **verde** porque su fixture omitía
> `estado_inferido` — un falso verde de manual. En el v3 hay **una sola asignación**
> (`estado_inferido = estado_origen == ORIGEN_INFERIDO`) y el **caso 18 de F1** la congela como
> invariante sobre todas las cards del board.

**Consumidores en este plan:**
- F3 `preview_estado_migration` **excluye por default** los planes con `estado_origen == "ledger"` y
  los reporta aparte en `ya_resueltos_por_ledger` (no hay nada que escribir: el supervisor ya cerró).
- F4 muestra el sufijo `(inferido)` sólo cuando `estado_origen === "inferido"`.

**Tests:** casos 9, 12, 13, 16 y **18** de F1 lo cubren. Sin archivo nuevo, sin flag nueva.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F2 — Servidor: registrar el test y cerrar el ratchet anti-regresión

**Objetivo.** Que un plan **nuevo** no pueda nacer sin `**Estado:**` sin que el arnés se ponga rojo.

> **v2 / C9 — por qué el generador del v1 estaba mal.** Usaba
> `head -c 4000 | grep -qE '^\s*(>\s*)?\*\*Estado:\*\*'`, que reimplementa en shell la regla que ya vive
> en Python. Dos divergencias reales: (1) `head -c` corta **4000 bytes**, mientras el lector real
> (`_read_header_cached`, `plans_board.py:126-140`) abre el archivo en **modo texto UTF-8** y hace
> `fh.read(_HEADER_READ_CHARS)`, o sea **4000 caracteres** — con documentos llenos de acentos el corte
> cae en distinto lugar y un plan puede quedar "sin estado" para el ratchet y "con estado" para el
> tablero; (2) el patrón shell es una copia a mano de `_ESTADO_RE` (`plans_board.py:25`), que puede
> cambiar. **La regla se importa, no se reescribe.**
>
> **Dato que refuerza el punto:** la propia docstring de `_read_header_cached` (`plans_board.py:127`)
> dice *"leyendo COMO MUCHO `_HEADER_READ_CHARS` **bytes**"* — y el código lee **caracteres**. Es decir,
> el repo ya tiene escrita esa confusión: quien lea la docstring y escriba el equivalente en shell
> reintroduce C9 sin darse cuenta. **No corrijas esa docstring en este plan** (es fuera de scope y toca
> un archivo que el 265 también edita); el test 5 de abajo es la defensa.

**Archivos a crear/editar (4):**

1. **Crear** `Stacky Agents/backend/tests/test_plan263_estado_guard.py`. Debe exponer, a nivel de
   módulo, la **función generadora** que también usa el comando de baseline (fuente única):

```python
"""Plan 263 F2 — ratchet: ningún plan nuevo nace sin **Estado:**.

NADA de la regla se reimplementa acá. Se importan de services.plans_board las
TRES piezas que definen "esto es un plan y tiene estado":
  _ESTADO_RE          -> qué línea cuenta como estado
  _HEADER_READ_CHARS  -> cuánto encabezado se lee (CARACTERES, no bytes)
  _PLAN_FILE_RE       -> qué archivo es un plan            (v3/C6)
Ver [ADICIÓN ARQUITECTO 3] (test_regla_unica_de_estado) y
[ADICIÓN ARQUITECTO 5] (test_regla_de_archivo_unica).
"""
import json
import pathlib
import sys

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services.plans_board import (  # noqa: E402
    _ESTADO_RE,
    _HEADER_READ_CHARS,
    _PLAN_FILE_RE,
    parse_plan_header,
)

DOCS_DIR = _BACKEND.parent / "docs"
BASELINE_PATH = _BACKEND / "tests" / "plans_estado_baseline.json"


def _texto_encabezado(path: pathlib.Path) -> str:
    """MISMA lectura que services.plans_board._read_header_cached (:126-140):
    modo texto UTF-8 y N CARACTERES (no bytes)."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return fh.read(_HEADER_READ_CHARS)


def tiene_estado(path: pathlib.Path) -> bool:
    return bool(_ESTADO_RE.search(_texto_encabezado(path)))


def planes_sin_estado(docs_dir: pathlib.Path) -> list[str]:
    return sorted(
        p.name for p in docs_dir.iterdir()
        if p.is_file() and _PLAN_FILE_RE.match(p.name) and not tiene_estado(p)
    )
```

> **v3 / C6 — por qué `_PLAN_FILE_RE` también se importa.** El v2 escribía acá
> `re.compile(r"^[0-9]+_PLAN_.*\.md$")`, una copia a mano. El real es
> `^(\d{2,3})_PLAN_(.+)\.md$` (`plans_board.py:23`): acepta **2 o 3 dígitos**, no "uno o más". Medido
> el 2026-07-27 las dos dan lo mismo (**220 = 220**, cero archivos de diferencia), así que el v2 se
> salvó por el corpus, no por el diseño: el día que exista `9_PLAN_*.md` o `1000_PLAN_*.md`, el ratchet
> y el tablero contarían universos distintos y el arnés se pondría rojo por un archivo que el tablero
> ni ve. Es exactamente el pecado que C9 vino a matar, cometido en el otro eje.

   Y estos tests:

| # | Test | Qué asegura |
|---|---|---|
| 1 | `test_baseline_existe_y_es_json` | El baseline carga y `sin_estado` es una lista de `str`. |
| 2 | `test_ningun_plan_nuevo_sin_estado` | `set(planes_sin_estado(DOCS_DIR)) - set(baseline) == set()`. Mensaje: `"El plan <archivo> no declara **Estado:**. Agregale la linea o corré la normalización del Plan 263."` |
| 3 | `test_el_ratchet_solo_se_achica` | `set(baseline) - set(planes_sin_estado(DOCS_DIR)) == set()` ⇒ obliga a achicar el baseline cuando un plan se normaliza o se borra. Mensaje: `"El baseline quedó stale: sacá <archivo> de plans_estado_baseline.json (o dejá que la normalización del Plan 263 lo pode sola)."` |
| 4 | `test_baseline_sin_duplicados` | `len(sin_estado) == len(set(sin_estado))`. |
| 5 | **`test_regla_unica_de_estado`** **[ADICIÓN ARQUITECTO 3]** | *(v3/C8 — literal exacto, el v2 dejaba dos huecos de inferencia)*. Contenido **textual** del archivo, sin adornos: `p = tmp_path / "263_PLAN_MULTIBYTE.md"` y `p.write_text("# t\n" + "á" * 3900 + "\n**Estado:** PROPUESTO v1\n", encoding="utf-8")`. El `\n` **antes** de `**Estado:**` es obligatorio: `_ESTADO_RE` es `MULTILINE` y ancla en `^`; pegado al relleno no matchea y el test sale rojo por la razón equivocada. Con "á" = 2 bytes en UTF-8, la línea cae **dentro** de los 4000 *caracteres* (≈3.929) y **fuera** de los 4000 *bytes* (≈7.830). Asserta las tres cosas: (a) `tiene_estado(p) is True`; (b) `parse_plan_header(_texto_encabezado(p))["estado"] == "PROPUESTO"` (la función pública real es **`parse_plan_header(text: str)`**, `plans_board.py:89` — recibe **texto**, no un `Path`, y **ya está importada** en el encabezado del módulo de arriba); (c) el equivalente por bytes **NO** lo ve: `_ESTADO_RE.search(p.read_bytes()[:4000].decode("utf-8", "replace")) is None`. Es decir: ratchet y tablero coinciden, y el atajo shell habría mentido. Este test impide que alguien "optimice" el ratchet a shell y reintroduzca C9. |
| 6 | `test_baseline_solo_nombres_de_plan` | Toda entrada del baseline matchea `_PLAN_FILE_RE` (nada de rutas ni `..`). |
| 7 | **`test_regla_de_archivo_unica`** **[ADICIÓN ARQUITECTO 5]** *(v3/C6)* | El ratchet usa **el mismo** objeto regex que el tablero, no una copia equivalente. Dos aserciones: (a) `from services import plans_board; assert _PLAN_FILE_RE is plans_board._PLAN_FILE_RE` — identidad de objeto, `is`, no `==`; (b) el universo coincide: `{p.name for p in DOCS_DIR.iterdir() if p.is_file() and _PLAN_FILE_RE.match(p.name)} == {c["filename"] for c in plans_board.scan_plan_files_with_census(DOCS_DIR)[0]}`. Si alguien vuelve a copiar la regex a mano, (a) falla al instante. |

2. **Crear** `Stacky Agents/backend/tests/plans_estado_baseline.json` — la deuda histórica congelada.
   Generalo con **este comando exacto** (usa la misma función que el test; no lo escribas a mano):

```powershell
& "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys, json, pathlib; sys.path.insert(0,'Stacky Agents/backend/tests'); from test_plan263_estado_guard import planes_sin_estado, DOCS_DIR, BASELINE_PATH; d={'_comment':'Plan 263 - planes historicos sin **Estado:**. RATCHET: esta lista SOLO puede achicarse. Un plan NUEVO sin estado NO se agrega aca: se le escribe el estado.','sin_estado':planes_sin_estado(DOCS_DIR)}; BASELINE_PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding='utf-8'); print('entradas:', len(d['sin_estado']))"
```

Al momento de escribir este plan (2026-07-27) el comando imprime **79**. **Usá el número que te
imprima a vos**, no el de este documento.

3. **Editar** `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar a `HARNESS_TEST_FILES`
   (empieza en `run_harness_tests.sh:20`), respetando el orden del bloque vecino:

```
    tests/test_plan263_estado_fallback.py
    tests/test_plan263_estado_guard.py
    tests/test_plan263_migration.py
```

4. **Editar** `Stacky Agents/backend/scripts/run_harness_tests.ps1` — la misma lista, **con la sintaxis
   propia del `.ps1`** (es un archivo distinto con su propia declaración; **no** copies las líneas del
   `.sh` tal cual). Verificá el formato literal con:

```powershell
Select-String -Path "Stacky Agents\backend\scripts\run_harness_tests.ps1" -Pattern "test_plan25" | Select-Object -First 5
```

> **Por qué es obligatorio:** `tests/test_harness_ratchet_meta.py` falla si un `test_*.py` nuevo no está
> ni en `HARNESS_TEST_FILES` ni en una allowlist con motivo. Saltarse este paso deja el arnés rojo.
> Los **3** archivos de test de este plan se registran acá, de una vez (el de F3 incluido).

**Comando de test:**

```powershell
$py = "Stacky Agents\backend\.venv\Scripts\python.exe"
& $py -m pytest "Stacky Agents\backend\tests\test_plan263_estado_guard.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
```

**Criterio binario.** Ambos exit 0 (**7 passed** en el primero; `test_harness_ratchet_meta.py` da
**4 passed** y está verde en el árbol limpio, medido el 2026-07-27 — un rojo ahí es tuyo).
**Prueba negativa manual obligatoria:**
creá `Stacky Agents/docs/999_PLAN_PRUEBA_RATCHET.md` con una sola línea `# hola`, corré el primer
comando, verificá que **falla** nombrando `999_PLAN_PRUEBA_RATCHET.md`, y **borrá el archivo**
(`Remove-Item "Stacky Agents\docs\999_PLAN_PRUEBA_RATCHET.md"`). Volvé a correr: verde.

**Flag:** ninguna nueva — es un test del arnés, siempre activo.
**Impacto por runtime:** ninguno (test determinista, sin modelo).
**Trabajo del operador: ninguno.**

> **v3 / C16 — por qué KPI-4 no le agrega una sola tarea al operador (verificado, no supuesto).** El
> creador atómico de planes ya escribe la línea: `claim_plan_path` (`plans_board.py:382-394`) hace
> `fh.write(f"# Plan {number} — (borrador)\n\n**Estado:** PROPUESTO v1\n")`, y la skill
> `proponer-plan-stacky` la escribe también en su encabezado. O sea: **todo plan nuevo ya nace con
> estado**; este ratchet no cambia ningún flujo, sólo impide que eso se rompa en silencio. El caso en
> que se pondría rojo es un `.md` escrito a mano — y ahí el mensaje del test 2 dice exactamente qué
> agregar.

---

### F2.5 — La transacción de normalización de 3 patas **[ADICIÓN ARQUITECTO 1]**

**Objetivo.** Que escribir la línea `**Estado:**` en un `.md` sea **una sola operación consistente**, y
no un cambio que deja dos sistemas mintiendo.

**Los tres daños colaterales que el v1 no vio** (todos verificados en el código, no hipotéticos):

1. **Des-aprobación silenciosa (C6).** `ledger_info_for` calcula
   `doc_drift = sha256(path.read_bytes()) != entry["doc_sha256"]` (`services/plans_board.py:454-459`).
   Escribir una línea cambia el sha256 ⇒ `doc_drift=True` ⇒ `estado_efectivo` deja de ser `"APROBADO"`
   (`:568`) y `suggest_next_action` devuelve **"Re-supervisar (drift)"** (`:495-498`). Y la **regla 1**
   de inferencia de F3 apunta EXACTAMENTE a esos planes (los que el ledger aprobó y no declaran
   estado). Resultado del v1: normalizar **dispara re-supervisiones caras** que su propio §7 declaraba
   fuera de scope.
2. **Ratchet rojo por trabajo manual (C10).** Al normalizar un plan del baseline,
   `test_el_ratchet_solo_se_achica` falla hasta que **alguien edita el JSON a mano**. Eso es trabajo
   extra del operador, prohibido por el principio 2.
3. **Cache mintiendo 15 s (C14).** `_BOARD_TTL_SEC = 15` con cache módulo-global
   (`services/plans_board.py:698-701`): tras escribir, el tablero sigue mostrando "inferido" y el
   operador cree que el botón no hizo nada.

**Contrato de la transacción.** `apply_estado_migration` es el **único** escritor y hace las 3 patas o
ninguna:

```
por cada filename confirmado:
  1. releer el .md y verificar sha256 == sha256_visto        (guardia TOCTOU, C7)
     -> si no coincide: omitido, razon="cambio en disco desde la vista previa"
  2. escribir <archivo>.tmp con la linea insertada + os.replace()   [PATA 1: el .md]
  3. si el ledger tenia entrada para ese numero con doc_sha256:
        recalcular sha256 y re-sellarlo en el ledger              [PATA 2: el ledger]
  4. sacar el filename de plans_estado_baseline.json              [PATA 3: el ratchet]
al final, SIEMPRE:
  5. services.plans_board._BOARD_CACHE = None                     (invalidar cache)
```

**Contrato de escritura del ledger (v3 / C5 — BLOQUEANTE del v2: no existía).**
`load_ledger()` (`plans_board.py:425-446`) devuelve **`data["planes"]`, no el documento**: el archivo
real es `{"version": …, "planes": {…}}` (verificado el 2026-07-27: 47 entradas, y cada entrada trae
`plan`, `ruta`, `doc_sha256`, `veredicto`, `fecha`). Si la pata 2 vuelca lo que devolvió `load_ledger`,
el archivo queda **sin `version` y sin el envoltorio** ⇒ `load_ledger` pasa a devolver `{}` para
siempre ⇒ **los 47 planes aprobados pierden su aprobación en silencio** y el tablero pide re-supervisar
todo. Reglas, obligatorias:

1. La pata 2 **NO usa `load_ledger()`**. Lee el archivo completo con
   `json.loads(ledger_path.read_text(encoding="utf-8"))`.
2. Modifica **una sola clave** del documento: `data["planes"][str(number)]["doc_sha256"]`, y le agrega
   a **esa** entrada `normalizado_por: "plan-263"` y `normalizado_en: "<fecha ISO>"`. **Nada más se
   toca**: ni `version`, ni las otras entradas, ni el orden de las claves.
3. Escribe con `json.dumps(data, indent=2, ensure_ascii=False)` + `.tmp` + `os.replace`.
4. Si el archivo no existe, o no parsea, o no tiene la clave `"planes"` como dict ⇒ **no escribe** y
   dispara el rollback de abajo. Nunca lo "repara" ni lo crea.

**Rollback.** Las patas 2 y 3 se escriben con el mismo patrón atómico (`.tmp` + `os.replace`). Si la
pata 2 o la 3 fallan (p. ej. el JSON del ledger está corrupto), la función **restaura el `.md`** desde
el contenido original que guardó en memoria antes de la pata 1 y devuelve ese archivo en `omitidos`
con `razon="rollback: no se pudo actualizar el ledger o el baseline"`. **Ningún archivo queda a medias.**
El rollback además emite **una** línea de registro (la única de todo el plan), porque es el único
camino destructivo y porque es la que sostiene la huella de F7:

```python
logger.error("[plan263] rollback de normalizacion: %s (%s)", filename, razon)
```

**Por qué re-sellar el ledger no es hacer trampa.** El re-sellado se aplica **sólo** a un cambio que
esta misma función acaba de hacer y que es **puramente aditivo en el encabezado**: inserta una línea
`**Estado:**` y no toca ni una palabra del cuerpo. Se registra en el propio ledger con
`normalizado_por: "plan-263"` y la fecha, así que queda auditable. Cualquier otra edición del `.md`
sigue produciendo drift normal.

**Tests (van en `test_plan263_migration.py`, F3):** casos 13-22 de esa lista.

**Flag:** la misma de F3 (`STACKY_PLANS_NORMALIZE_APPLY_ENABLED`, OFF).
**Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno adicional — al contrario, **elimina**
la tarea manual que el v1 le dejaba.

---

### F3 — Servidor: normalización con evidencia (preview ON, escritura OFF)

**Objetivo.** Convertir el estado inferido en un estado **escrito y verdadero**, con la evidencia a la
vista y confirmación humana por plan.

**Archivo a crear:** `Stacky Agents/backend/services/plans_estado_migration.py`.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan263_migration.py`.

**Contrato del módulo (símbolos exactos):**

```python
def infer_estado_con_evidencia(plan_card: dict, docs_dir: Path) -> dict:
    """Propone el **Estado:** a escribir para UN plan, con su evidencia.

    Devuelve SIEMPRE este dict (claves fijas):
      {
        "number": int,
        "filename": str,
        "estado_propuesto": str | None, # "IMPLEMENTADO"|"PROPUESTO"|"CRITICADO"|"IMPLEMENTADO-PARCIAL"
                                        # o None cuando confianza == "sin_evidencia" (v3/ADICIÓN 4)
        "confianza": str,               # "alta" | "media" | "sin_evidencia"
        "aplicable": bool,              # v3 — False si estado_propuesto is None. La UI NO le da
                                        # checkbox y el apply lo RECHAZA salvo estado_elegido explícito.
        "evidencia": list[str],         # frases cortas, verificables, en español
        "linea_a_insertar": str | None, # p.ej. "**Estado:** IMPLEMENTADO (normalizado 2026-07-27, Plan 263) — sin veredicto de supervisor"
                                        # None cuando estado_propuesto is None
        "insert_after_line": int,       # índice 0-based de la línea tras la cual insertar
        "sha256_visto": str,            # v2/C7 — sha256 del archivo COMPLETO al momento del preview
        "resella_ledger": bool,         # v2/C6 — el ledger tiene doc_sha256 para este plan
      }
    NUNCA lanza. NUNCA escribe.
    """
```

**Reglas de inferencia (v3 — REESCRITAS. En este orden exacto; la primera que matchea gana):**

| Orden | Condición (verificable, sin modelo, sin heurística de número) | `estado_propuesto` | `confianza` | Evidencia que se agrega |
|---|---|---|---|---|
| 1 | El ledger tiene entrada para este número con `veredicto` en `_LEDGER_OK_VEREDICTOS` (**v4/C2 — importada** de `services.plans_board`, `:34`; NO se re-escribe la tupla a mano — es la MISMA constante que ya usan `ledger_ok` en `build_board` (`:566`) y `suggest_next_action` (`:475`), hoy `("APROBADO","TERMINADO-POR-SUPERVISOR")`). **Sólo alcanzable con `doc_drift is True`**: los aprobados sin drift ni llegan acá (los filtró `ya_resueltos_por_ledger`, F1.5). | `IMPLEMENTADO` | `alta` | `"El supervisor lo aprobó el <fecha> y el documento cambió después (ledger.json)."` |
| 2 | El doc trae un **marcador estructural** de implementación en los primeros 8000 chars: `re.search(r"^#{1,4}\s*.*Registro de implementaci", texto, re.M)` **o** `re.search(r"^\|[^|\n]*\|\s*IMPLEMENTADA\s*\|", texto, re.M)` (una fila de tabla cuya celda **completa** dice `IMPLEMENTADA`). | `IMPLEMENTADO` | `alta` | `"El documento trae su registro de implementacion (<marcador>)."` |
| 3 | El doc trae `"veredicto"` **y** (`"APROBADO"` o `"RECHAZADO"`) en los primeros 8000 chars. | `CRITICADO` | `media` | `"El documento trae un veredicto del juez, pero no registro de implementacion."` |
| 4 | Ninguna de las anteriores. | **`None`** | **`sin_evidencia`** | `"Sin evidencia en el documento ni en el ledger. El tablero lo muestra como implementado (inferido), pero NO hay nada verificable que escribir: decidilo vos."` |

> **v3 / C1 — las reglas del v2 no hacían lo que el v2 decía. MEDIDO sobre los 79 planes vivos el
> 2026-07-27, con `_umbral_reciente = max(numeros) - 20 = 269 - 20 = 249`:**
>
> | Regla del v2 | Hits | Qué significaba de verdad |
> |---|---|---|
> | 1 (ledger APROBADO → `IMPLEMENTADO`/`alta`) | **18** | pero los **18** son exactamente los que F1.5 excluye en `ya_resueltos_por_ledger` (medido: **18** aprobados sin drift, **0** con drift) ⇒ **código muerto** |
> | 2 (`"Registro de implementación"` **o** `"IMPLEMENTADA"`) | **6** | de los cuales **sólo 2** por el registro; los otros **4** por la subcadena desnuda `"IMPLEMENTADA"` — que también satisface `"NO IMPLEMENTADA"` — y todos con `confianza: alta` |
> | 3 (veredicto) | **10** | razonable |
> | 4 (`number > 249` → `PROPUESTO`) | **0** | **no matchea un solo archivo**: los planes recientes sin estado son 250/251/252, que caen antes en la regla 2. Su propósito declarado —"dejar los pendientes recientes en `PROPUESTO`"— era **inalcanzable** |
> | 5 (fallback → `IMPLEMENTADO`/`baja`) | **45** | **57 % del corpus** escrito a disco como `IMPLEMENTADO` con la evidencia literal *"Sin evidencia"* |
>
> Resultado del v2 sobre el corpus real: **61 propuestas, ninguna en `PROPUESTO`, y 45 (74 % de las
> propuestas) sin ninguna evidencia**. Un botón que escribe 45 mentiras al disco del operador con
> confirmación de un click. Por eso el v3 **borra la regla 5** y la reemplaza por la
> **[ADICIÓN ARQUITECTO 4]**: sin evidencia **no hay propuesta**.
>
> **`_umbral_reciente` se elimina.** No queda ninguna heurística basada en el número del plan: era la
> única regla que dependía de una constante arbitraria (`- 20`) y medía **cero**. Con ella se va el
> problema de C19 (claves string del ledger) y una función menos que testear.

> **v4 / C2 — Regla 1 importa, no reimplementa.** `plans_estado_migration.py` agrega
> `from services.plans_board import _LEDGER_OK_VEREDICTOS` en su encabezado (mismo principio que F2 ya
> aplica para `_ESTADO_RE`/`_HEADER_READ_CHARS`/`_PLAN_FILE_RE`, y que F0 aplica para `_CATEGORY_KEYS`).
> Escribir la tupla de veredictos a mano en la Regla 1 era el mismo riesgo de desincronización que C6/C9
> (v2→v3) ya cerraron para la regex de estado y de archivo: un tercer veredicto agregado el día de
> mañana que sólo toque `_LEDGER_OK_VEREDICTOS` dejaría a la Regla 1 de F3 ciega a planes que el resto
> del tablero ya trata como resueltos. Caso 25 de F3 lo congela con identidad de objeto (mismo patrón
> que `test_regla_de_archivo_unica` de F2): `from services import plans_board, plans_estado_migration;
> assert plans_estado_migration._LEDGER_OK_VEREDICTOS is plans_board._LEDGER_OK_VEREDICTOS`.

> **[ADICIÓN ARQUITECTO 4] — Prohibido escribir sin evidencia.**
>
> `confianza: "sin_evidencia"` ⇒ `estado_propuesto is None`, `linea_a_insertar is None`,
> `aplicable is False`. Consecuencias, todas obligatorias:
> - `preview_estado_migration` los devuelve en `propuestas` **igual** (el operador tiene que verlos:
>   son los 45 casos donde el tablero está adivinando) pero con `aplicable: False`.
> - La UI (F6) los lista **sin checkbox**, con la leyenda *"sin evidencia — elegí vos la etapa"* y un
>   selector de estado por fila. Si el operador elige uno, el item viaja con `estado_elegido`.
> - `apply_estado_migration` **rechaza** cualquier item cuya propuesta sea `sin_evidencia` **salvo**
>   que el item traiga `estado_elegido` en `("PROPUESTO","CRITICADO","IMPLEMENTADO","IMPLEMENTADO-PARCIAL")`.
>   Razón de omisión: `"sin evidencia y sin estado elegido por el operador"`.
> - La línea escrita en ese caso dice quién decidió:
>   `**Estado:** <elegido> (normalizado <fecha>, Plan 263) — elegido por el operador, sin evidencia en el documento`.
>
> Esto **amplifica** al operador (le muestra los 45 y le pide la decisión) en vez de reemplazarlo
> (escribirle 45 estados inventados). Es el mismo criterio de human-in-the-loop de todo el plan,
> aplicado al único lugar donde el v2 lo había perdido.

```python
def preview_estado_migration(docs_dir: Path) -> dict:
    """{"ok": True, "total": int, "propuestas": [<dict de infer_estado_con_evidencia>, ...],
        "por_confianza": {"alta": int, "media": int, "sin_evidencia": int},  # v3
        "aplicables": int,                  # v3 — cuántas propuestas tienen aplicable=True
        "ya_resueltos_por_ledger": [str]}   # v2/F1.5: estado_origen == "ledger", NO se proponen
    SOLO LECTURA. Nunca escribe. Nunca lanza."""


def apply_estado_migration(
    docs_dir: Path, items: list[dict], *, dry_run: bool = True
) -> dict:
    """Escribe la línea **Estado:** en los planes pedidos, UNO POR UNO (transacción F2.5).

    - `items` es una lista EXPLÍCITA de
      {"filename": str, "sha256_visto": str, "estado_elegido": str | None}:
      no existe "aplicar a todos" implícito y no se acepta el comodín "*".
    - v3/ADICIÓN 4: si la propuesta recalculada para ese archivo es
      `sin_evidencia` y el item NO trae `estado_elegido` válido -> omitido con
      razón "sin evidencia y sin estado elegido por el operador". `estado_elegido`
      sólo se acepta con uno de los 4 valores del vocabulario; cualquier otra
      cosa -> omitido con razón "estado elegido invalido".
    - v2/C7 (TOCTOU): si el sha256 actual != sha256_visto -> omitido con razón
      "cambio en disco desde la vista previa". El offset se RE-DERIVA del archivo
      recién leído, nunca se reusa el `insert_after_line` del preview.
    - Rechaza cualquier filename que no matchee `_PLAN_FILE_RE` o que escape de
      docs_dir (guardia de path traversal: `(docs_dir / name).resolve()` debe
      tener `docs_dir.resolve()` como parent).
    - Rechaza un plan que YA tiene **Estado:** (idempotencia: no duplica la línea).
    - Escritura atómica: `<archivo>.tmp` + os.replace(). Preserva encoding utf-8 y
      el fin de línea que ya tenía el archivo (newline="").
    - dry_run=True devuelve el diff unificado sin tocar el disco.
    - Al terminar (dry_run=False) ejecuta las patas 2 y 3 de F2.5 e invalida el cache.
    Devuelve {"ok": bool, "aplicados": [str], "omitidos": [{"filename","razon"}],
              "diffs": {filename: str}, "ledger_resellado": [str],
              "baseline_podado": [str]}
    """
```

**Casos de test (mínimo 25):**

1. `infer_estado_con_evidencia` con ledger APROBADO **y drift** → `IMPLEMENTADO`/`alta`, `aplicable is True`.
2. …con doc que trae un encabezado `## Registro de implementación` → `IMPLEMENTADO`/`alta`.
3. …con doc que trae `veredicto ... APROBADO` → `CRITICADO`/`media`.
4. **(v3/C9)** …con doc cuyo único rastro es la frase suelta `"la fase NO fue IMPLEMENTADA"` → **NO** matchea la regla 2; cae en `sin_evidencia` con `estado_propuesto is None`. *(Este es el caso que el v2 clasificaba `IMPLEMENTADO`/`alta`.)*
5. **(v3/C1)** …doc sin ninguna señal → `confianza == "sin_evidencia"`, `estado_propuesto is None`, `linea_a_insertar is None`, `aplicable is False`. **No existe `baja`**: `assert "baja" not in preview["por_confianza"]`.
6. `linea_a_insertar` empieza con `**Estado:** ` y contiene el string `Plan 263`.
7. `insert_after_line` apunta a la línea del `# ` título (el estado va justo debajo del H1).
8. `preview_estado_migration` sobre un `tmp_path` con 3 docs sin estado → `total == 3`, no escribe (mtime de los 3 archivos idéntico antes/después).
9. `apply_estado_migration(dry_run=True)` → `aplicados == []`, `diffs` no vacío, archivos intactos (sha256 idéntico).
10. `apply_estado_migration(dry_run=False, items=[{"filename":"01_PLAN_X.md","sha256_visto":<real>}])` → el archivo ahora tiene `**Estado:**` y `parse_plan_header` lo reconoce.
11. Idempotencia: correr 10 dos veces → la segunda devuelve `omitidos` con razón `"ya declara estado"` y el archivo **no** cambia (sha256 idéntico).
12. Seguridad: `apply_estado_migration(docs_dir, [{"filename":"../../.env","sha256_visto":"x"}])` → `omitidos`, `ok` sigue True, y `.env` **no** se toca.
13. **v2/C7 TOCTOU:** preview → modificar el `.md` a mano → apply con el `sha256_visto` viejo ⇒ `omitidos` con razón `"cambio en disco desde la vista previa"` y el archivo **intacto**.
14. **v2/C6 re-sellado:** doc sin estado + entrada de ledger con `doc_sha256` correcto ⇒ tras el apply, `ledger_info_for(...)["doc_drift"] is False` y el card sigue en `estado_efectivo == "APROBADO"`. **KPI-6.**
15. **v2/C6 sin ledger:** doc sin estado y sin entrada de ledger ⇒ `ledger_resellado == []` y el ledger no se toca (sha256 del `ledger.json` idéntico).
16. **v2/C10 poda:** el filename normalizado **desaparece** de `plans_estado_baseline.json` y `test_el_ratchet_solo_se_achica` sigue verde después del apply.
17. **v2 rollback:** con el `ledger.json` corrupto (texto no-JSON), el apply devuelve ese archivo en `omitidos` con razón que empieza con `"rollback"` y el `.md` queda **byte-idéntico** al original.
18. **v2/C14 cache:** tras un apply exitoso, `services.plans_board._BOARD_CACHE is None`.
19. **v3/C5 el ledger sobrevive entero:** ledger con `{"version": 1, "planes": {"7": {...}, "8": {...}}}`; se normaliza el plan 7. Después: `data["version"] == 1` **sigue**, `set(data["planes"]) == {"7","8"}`, la entrada `"8"` es **byte-idéntica** (comparar `json.dumps(..., sort_keys=True)`), y la `"7"` conserva `plan`/`ruta`/`veredicto`/`fecha` y sólo cambió `doc_sha256` + ganó `normalizado_por`/`normalizado_en`.
20. **v3/C5 el ledger sin envoltorio no se "repara":** ledger `{"planes": {...}}` **sin** `version` ⇒ el apply respeta el documento tal cual (no inventa `version`) y sigue funcionando; ledger `{"otra_cosa": 1}` (sin `"planes"`) ⇒ rollback, `.md` intacto.
21. **v3/ADICIÓN 4 el apply rechaza lo que no tiene evidencia:** item de un doc `sin_evidencia` **sin** `estado_elegido` ⇒ `omitidos` con razón `"sin evidencia y sin estado elegido por el operador"`, archivo **intacto** (sha256 idéntico). Con `estado_elegido: "PROPUESTO"` ⇒ se aplica y la línea escrita contiene `"elegido por el operador"`.
22. **v3/ADICIÓN 4 vocabulario cerrado:** `estado_elegido: "LO_QUE_SEA"` ⇒ `omitidos` con razón `"estado elegido invalido"`, archivo intacto.
23. **v3/ADICIÓN 4 centinela sobre el CORPUS VIVO** (`test_ninguna_propuesta_alta_sin_marcador_estructural`): corre `preview_estado_migration(plans_board.docs_dir_default())` sobre `Stacky Agents/docs` **real** y asserta, para cada propuesta con `confianza == "alta"`, que su lista `evidencia` nombra el marcador estructural o el ledger (`any("Registro de implementaci" in e or "ledger.json" in e for e in p["evidencia"])`). Es el único test del plan que toca el corpus real: es **solo lectura**, no escribe nada, y es el que impide que una regla laxa vuelva a producir un `alta` de aire. Si `docs/` no existe (deploy congelado), `pytest.skip`.
24. **v3/ADICIÓN 4 ninguna propuesta miente por default:** sobre el mismo corpus vivo, `preview["por_confianza"].get("sin_evidencia", 0) == sum(1 for p in preview["propuestas"] if not p["aplicable"])` y **toda** propuesta con `aplicable is False` tiene `estado_propuesto is None`. Invariante, no número: no se congela el 45.
25. **v4/C2 la Regla 1 importa, no reescribe:** `from services import plans_board, plans_estado_migration; assert plans_estado_migration._LEDGER_OK_VEREDICTOS is plans_board._LEDGER_OK_VEREDICTOS` — identidad de objeto (`is`), no igualdad de valor. Si alguien vuelve a copiar la tupla a mano, este test falla al instante.

**Endpoints (editar `Stacky Agents/backend/api/plans_board.py`):**

> **v3 / C2 — LEÉ ESTO ANTES DE ESCRIBIR UNA LÍNEA EN `api/plans_board.py`.** Ese módulo hace
> `from config import config` (`api/plans_board.py:10`): dentro de él, el nombre `config` **YA ES LA
> INSTANCIA**, no el módulo. Escribir `config.config.STACKY_…` (como hacía el v2) lanza
> `AttributeError` y Flask devuelve **500**, no el 404 que exige el criterio binario de esta fase — y
> lo hace sólo en runtime, así que ningún test unitario del módulo lo atrapa. El patrón correcto y
> vigente en ese archivo es `getattr(config, "<KEY>", <default>)`: ver `_enabled()`
> (`api/plans_board.py:15-16`) y `_actions_enabled()` (`api/plans_board.py:78-81`). El gotcha del repo
> "usá `config.config`, no `config`" aplica a los módulos que hacen `import config`; **acá no**.

```python
# api/plans_board.py — `config` ya es la INSTANCIA (from config import config, :10).

def _normalize_preview_enabled() -> bool:
    # Espejo EXACTO de _actions_enabled() (:78-81). Default True: la flag es ON.
    return _enabled() and bool(
        getattr(config, "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED", True)
    )


def _normalize_apply_enabled() -> bool:
    # Candado 0 (patrón Plan 250, api/pipeline_editor.py): las TRES flags acá, NO
    # se confía en `requires` (que es metadata para la UI y no la evalúa nadie).
    # Esto materializa "APPLY exige PREVIEW". Default False: la flag nace OFF.
    return _normalize_preview_enabled() and bool(
        getattr(config, "STACKY_PLANS_NORMALIZE_APPLY_ENABLED", False)
    )


@bp.get("/normalize/preview")          # ruta final: /api/plans-board/normalize/preview
def plans_normalize_preview():
    if not _normalize_preview_enabled():
        return _disabled_resp()        # api/plans_board.py:19-29 -> 404
    from services import plans_board, plans_estado_migration   # import lazy (patrón :36)
    return jsonify(
        plans_estado_migration.preview_estado_migration(plans_board.docs_dir_default())
    )


@bp.post("/normalize/apply")           # ruta final: /api/plans-board/normalize/apply
def plans_normalize_apply():
    if not _normalize_apply_enabled():
        return _disabled_resp()        # 404 con CUALQUIERA de las 3 flags en OFF
    # Body: {"items": [{"filename": str, "sha256_visto": str,
    #                   "estado_elegido": str | null}],
    #        "dry_run": true|false, "confirm": true}
    # 400 si falta `confirm: true`, si `items` está vacío/ausente/no es lista, o si
    # algún item no trae `sha256_visto`. `items` NUNCA acepta el comodín "*".
    # -> plans_estado_migration.apply_estado_migration(...)
```

> **HITL, explícito:** `confirm: true` es obligatorio y `items` nunca puede ser `"*"`. El servidor
> **no expone ninguna forma de aplicar a todos de una**. Si el operador quiere los 79, la UI manda los
> 79 items tras mostrarlos y tras el diff. No es un control de seguridad (Stacky es mono-operador y no
> tiene auth): es un seguro contra el click accidental.

**Comando de test:**

```powershell
& "Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan263_migration.py" -q
```

(el registro en las dos listas `HARNESS_TEST_FILES` ya se hizo en F2, punto 3/4).

> **Gotcha del repo (SQLITE_LOCKED bajo pytest):** este archivo **no toca la DB** — usa `tmp_path`,
> funciones puras y, en los casos 23-24, lectura de `docs/` en solo lectura. No necesita
> `run_with_retry`. Los casos 23-24 **jamás** escriben en `docs/`; si alguien los ve mutar algo, es un
> bug de la implementación, no del test.

**Criterio binario.** 25 passed, 0 failed. Además, con `STACKY_PLANS_NORMALIZE_APPLY_ENABLED=false`,
`POST /api/plans-board/normalize/apply` responde 404 con el envelope de deshabilitado y **no** modifica
ningún archivo — verificable comparando la salida de
`git status --porcelain "Stacky Agents/docs"` **antes y después** (debe ser idéntica, carácter por
carácter).

**Flags:** `STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED` **ON** (solo lectura, calcula y muestra; no cae en
(A) ni en (B)) · `STACKY_PLANS_NORMALIZE_APPLY_ENABLED` **OFF** — **categoría (B)**: escribe en un
sistema real del operador, editando los `.md` de su working tree en `Stacky Agents/docs/` (que además
suele tener cambios sin commitear) desde
`services/plans_estado_migration.py::apply_estado_migration`, y además re-sella su
`docs/_supervision/ledger.json`.
**Impacto por runtime:** ninguno — inferencia determinista por reglas, **sin modelo**. Idéntico en los 3.
**Trabajo del operador:** opt-in explícito para la escritura (flag + selección + diff + confirmación).
El preview es automático y no pide nada.

---

### F4 — App: el modelo puro, coherente con el servidor

**Objetivo.** Que las dos superficies del tablero (tab "Planes" y Centro de Evolución) apliquen el mismo
fallback y muestren el rótulo "inferido".

**Archivos a editar (1) + tests (1).**

> **v2 / C16 — `actions.ts` NO se toca.** Ya está verificado en el código: `allowedActionsForCard`
> (`frontend/src/plansBoard/actions.ts:26-28`) hace
> `if (estado === "IMPLEMENTADO" || estado === "IMPLEMENTADO_PARCIAL" || docDrift === true) acts.push("supervisar")`,
> y el test `actions.test.ts:14-16` ya asserta `allowedActionsForCard("IMPLEMENTADO", null) === ["supervisar"]`.
> **Cero cambios de código en `actions.ts`.** El v1 dejaba esto como "verificalo y decidí", que es
> justo lo que un modelo menor no puede resolver.

1. `Stacky Agents/frontend/src/plansBoard/model.ts`:

```diff
 export interface PlanCardDto {
   ...
   estado_efectivo: EstadoPlan;
+  /** Plan 263 — el servidor infirió el estado porque el doc no lo declara.
+      Opcional: un deploy viejo del servidor no manda la clave. */
+  estado_inferido?: boolean;
+  /** Plan 263 — de dónde salió el estado: "declarado" | "inferido" | "ledger". */
+  estado_origen?: "declarado" | "inferido" | "ledger";
   ...
 }
```

```diff
 export function estadoChip(card: PlanCardDto): { label: string; color: string } {
-  return ESTADO_CHIP[card.estado_efectivo] ?? ESTADO_CHIP.SIN_ESTADO;
+  const chip = ESTADO_CHIP[card.estado_efectivo] ?? ESTADO_CHIP.SIN_ESTADO;
+  // Plan 263 v3/C3 — `estado_origen` MANDA. `estado_inferido` sólo se mira
+  // cuando el servidor no mandó `estado_origen` (deploy intermedio). Mirar los
+  // dos con `||` pintaba "Aprobado (inferido)" en las cards que el ledger ya
+  // había resuelto: el servidor manda origen "ledger" en esa card.
+  const inferido =
+    card.estado_origen !== undefined
+      ? card.estado_origen === "inferido"
+      : card.estado_inferido === true;
+  return inferido ? { ...chip, label: `${chip.label} (inferido)` } : chip;
 }
```

> **v2 / C13 — el fallback de clave DESCONOCIDA se queda en `SIN_ESTADO`.** El v1 lo cambiaba a
> `"Implementado"`. Eso es incorrecto y contradice la tesis del propio plan: con el fallback del
> servidor ON, `estado_efectivo` **nunca** llega como `SIN_ESTADO`, así que esa rama sólo se alcanza
> cuando el servidor manda un valor que esta versión de la app no conoce (p. ej. un estado nuevo de un
> plan futuro). Pintar eso como "Implementado" es exactamente la mentira que este plan combate:
> "Sin estado" es la respuesta honesta ante lo desconocido. Consecuencia práctica: **el test existente
> de `model.test.ts:55-57` ("cae a SIN_ESTADO ante una clave desconocida") se conserva INTACTO.**

`ESTADO_CHIP.SIN_ESTADO` (`model.ts:57`) y el miembro `"SIN_ESTADO"` del tipo `EstadoPlan`
(`model.ts:8`) **se conservan**: con la flag OFF, o contra un servidor viejo, siguen llegando.

**Tests (vitest):** editar `Stacky Agents/frontend/src/plansBoard/model.test.ts` agregando:

| # | Caso | Aserción |
|---|---|---|
| 1 | `estadoChip(card({estado_efectivo:"IMPLEMENTADO", estado_origen:"inferido"}))` | `.label === "Implementado (inferido)"` |
| 2 | `estadoChip(card({estado_efectivo:"IMPLEMENTADO", estado_inferido:true}))` (sin `estado_origen`, servidor intermedio) | `.label === "Implementado (inferido)"` |
| 3 | `estadoChip(card({estado_efectivo:"IMPLEMENTADO"}))` (sin ninguna clave nueva — deploy viejo) | `.label === "Implementado"` |
| 4 | **(v3/C3 — CAMBIÓ: la card REAL, con las DOS claves)** `estadoChip(card({estado_efectivo:"APROBADO", estado_origen:"ledger", estado_inferido:false}))` | `.label === ESTADO_CHIP.APROBADO.label` (sin sufijo: el ledger **no** es inferencia) |
| 4b | **(v3/C3 — el falso verde, explícito)** `estadoChip(card({estado_efectivo:"APROBADO", estado_origen:"ledger", estado_inferido:true}))` — payload **imposible** que el servidor ya no puede emitir | `.label === ESTADO_CHIP.APROBADO.label`. **`estado_origen` manda sobre `estado_inferido`.** Sin este caso, el fixture del v2 (que omitía `estado_inferido`) hacía pasar un `estadoChip` roto |
| 5 | `filterPlans([...], {estado:"IMPLEMENTADO", ...})` con un card inferido | lo incluye (filtro consistente con el fallback) |
| 6 | el test existente `"cae a SIN_ESTADO ante una clave desconocida"` (`model.test.ts:55-57`) | **sigue verde sin tocarlo** |

**Comando de test (por archivo — nunca la suite completa, por contaminación cross-file conocida):**

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/model.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/__tests__/actions.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** Los tres comandos exit 0. `tsc --noEmit` sin errores. `actions.test.ts` verde
**sin haber tocado `actions.ts`**.

**Flag:** protegido por `STACKY_PLANS_BOARD_ENABLED` (ya existente, ON). El fallback lo decide el
servidor; la app sólo lo refleja — **no hay lógica de fallback duplicada en TypeScript**.
**Impacto por runtime:** ninguno (UI pura).
**Trabajo del operador: ninguno.**

---

### F5 — App: densidad real (0 espaciados sordos)

**Objetivo.** Que el tablero obedezca el toggle cómodo/compacto del Plan 150 y muestre ≥ 11 cards sin
scroll a 1080 px en `compacto`.

**Archivo a editar (1):** `Stacky Agents/frontend/src/pages/PlansBoardPage.module.css`.

**Cambio.** Reemplazar las **31** declaraciones de `padding`/`margin`/`gap` hardcodeadas en `rem`/`px`
por tokens `var(--space-N)`. Tabla de conversión **exacta** (los tokens están en
`frontend/src/theme.css:100-108`; en `compacto` se re-apuntan en **`:251-259`**):

| Valor hardcodeado | Token | px en cómodo | px en compacto |
|---|---|---|---|
| `0.15rem` (2.4px) | `var(--space-1)` | 2 | 2 |
| `0.2rem` / `0.25rem` (3.2-4px) | `var(--space-2)` | 4 | 3 |
| `0.35rem` / `0.375rem` (5.6-6px) | `var(--space-3)` | 6 | 4 |
| `0.4rem` / `0.45rem` / `0.5rem` (6.4-8px) | `var(--space-4)` | 8 | 6 |
| `0.6rem` / `0.75rem` (9.6-12px) | `var(--space-5)` | 12 | 8 |
| `0.9rem` / `1rem` (14.4-16px) | `var(--space-6)` | 16 | 12 |
| `1.5rem` (24px) | `var(--space-7)` | 24 | 16 |
| `2rem` (32px) | `var(--space-8)` | 32 | 24 |
| `3rem` (48px) | `var(--space-9)` | 48 | 32 |

Aplicar a las 31 líneas que lista el comando de verificación de abajo. Ejemplo de las 4 que más
espacio en blanco aportan:

```diff
 /* :7 — contenedor raíz */
-  padding: 1.5rem;
+  padding: var(--space-7);
 /* :31 — estado vacío */
-  padding: 2rem;
+  padding: var(--space-8);
 /* :154 — placeholder de carga */
-  padding: 3rem;
+  padding: var(--space-9);
 /* :267 — panel de detalle */
-  padding: 1.5rem;
+  padding: var(--space-7);
```

**Restricciones duras (ratchets vivos del repo):**

- **Cero literales hex nuevos.** El Plan 196 ya se quemó con esto: agregar fallbacks `#888`/`#fff`
  subió `hexByFile` de 39 a 55 y puso el ratchet en rojo. Usá tokens de `theme.css`, nunca hex.
- **No aumentar los inline styles.** `PlansBoardPage.tsx` tiene **3** `style={{` pre-existentes
  congelados en `frontend/src/__tests__/uiDebtBaseline.json`. Criterio: **no aumentar**. Si el Plan 264
  ya se mergeó y dejó otro número, la línea base es **ese** número (ver §9): el criterio es
  "no aumentar respecto de lo que había al empezar", no "exactamente 3". No intentes bajarlos a 0.
- **Archivos `.tsx` NUEVOS: alcance 0 de inline-style.** Si F6 crea un `.tsx` nuevo, no puede tener
  **ni un** `style={{...}}`: se usa CSS module o `ref` + `effect`.

**Test (verificación por comando, no unit test — es CSS):**

```bash
f="Stacky Agents/frontend/src/pages/PlansBoardPage.module.css"
grep -cE '^\s*(padding|margin|gap)[^:]*:\s*[^;]*(rem|px)' "$f"          # debe dar 0
grep -cE '^\s*(padding|margin|gap)[^:]*:\s*[^;]*var\(--space' "$f"      # debe dar >= 46
```

Y el ratchet de UI:

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts
```

> Si el nombre del archivo del ratchet difiere, ubicalo con
> `Get-ChildItem "Stacky Agents\frontend\src\__tests__\" | Select-String -Pattern ratchet` y corré ese.
> **Los ratchets del frontend son OCHO**, no uno: si alguno más se pone rojo, comprobá primero con un
> worktree del commit base si ya estaba rojo antes de tu cambio.

**Criterio binario.** Primer grep = **0** (KPI-2), segundo grep **≥ 46** (31 convertidas + 15 que ya
usaban token), ratchet de UI verde, `npx tsc --noEmit` exit 0.

**Smoke visual (manual, 2 minutos — NO automatizable):** el repo **no tiene RTL ni jsdom instalados**,
así que la verificación visual es a ojo y va documentada, no scripteada. Pasos exactos *(v3/C11: el
`DensityToggle` **no** está en el tablero)*:

1. Abrir la app y entrar a **Configuración → Apariencia**; el `DensityToggle` vive ahí
   (`frontend/src/components/AppearanceSettings.tsx:48`, componente en
   `frontend/src/components/DensityToggle.tsx`). Ponerlo en **`compacto`** — escribe
   `<html data-density="compacto">` y re-apunta los tokens (`theme.css:250-260`).
2. Ir a `/plans`, dejar la ventana en **1080 px de alto**, contar las cards visibles sin scroll ⇒
   **≥ 11** (KPI-5).
3. Volver a **`cómodo`**, recontar y confirmar que **no** se rompió el layout.
4. Anotar los **dos** números en el "Registro de implementación" de este documento.

**Flag:** ninguna nueva — protegido por `STACKY_PLANS_BOARD_ENABLED` (ON) y por el sistema de densidad
del Plan 150, ya existente y ya ON.
**Impacto por runtime:** ninguno (CSS puro).
**Trabajo del operador: ninguno** (el toggle de densidad ya existía; el tablero simplemente empieza a
obedecerlo).

---

### F6 — App: panel de normalización en el tablero (HITL)

**Objetivo.** Darle al operador la vista previa y el botón de aplicar, con la evidencia y el diff.

**Archivos a editar (2) + 2 archivos nuevos de lógica pura.**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — agregar al objeto `PlansBoard` existente
   (`endpoints.ts:4964`):

```ts
  /** Plan 263 — vista previa de normalización. `rawGet` obligatorio: con la flag
   *  OFF el servidor responde 404 (_disabled_resp) y `api.get` LANZA en non-2xx,
   *  así que el panel explotaría en vez de mostrar el hint. */
  normalizePreview: () =>
    rawGet<NormalizePreviewDto>("/api/plans-board/normalize/preview"),
  /** Plan 263 — escritura HITL. `rawPost`, NUNCA `api.post`, por lo mismo. */
  normalizeApply: (items: NormalizeItem[], dryRun: boolean) =>
    rawPost<NormalizeApplyDto>("/api/plans-board/normalize/apply", {
      items, dry_run: dryRun, confirm: true,
    }),
```

> **v2 / C11 — dos bugs del v1 corregidos acá.**
> (a) **El prefijo `/api` va incluido.** El objeto `PlansBoard` vigente usa rutas absolutas:
> `api.get(\`/api/plans-board/detail/${number}\`)` (`endpoints.ts:4970`) y
> `rawPost("/api/plans-board/actions/run", …)` (`endpoints.ts:4995`). El v1 escribía
> `"/plans-board/normalize/preview"` ⇒ **404 en runtime**.
> (b) **El preview también necesita `rawGet`.** `_disabled_resp()` (`api/plans_board.py:19-29`)
> devuelve **404**, y `api.get` lanza ante cualquier non-2xx. El v1 sólo protegía el apply.
> Ambos helpers ya están importados en `endpoints.ts:1`.
>
> **v3 / C12 — la forma del retorno.** `rawGet<T>` (`api/client.ts:96-99`) y `rawPost<T>`
> (`api/client.ts:47-51`) devuelven **`Promise<RawResponse<T>>`** (`api/client.ts:28`), **no** el DTO
> pelado. El consumidor de F6 tiene que desenvolverlo: `const r = await PlansBoard.normalizePreview();`
> y después mirar `r.status` (404 ⇒ mostrar el hint de flag apagada, no un error) y `r.body`. Es el
> mismo contrato que ya usa `PlansPipeline.run` (`endpoints.ts:4994-4995`). `npx tsc --noEmit` lo
> atrapa si se olvida, pero pierde media hora de un modelo menor.

2. `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` — un panel plegable "Planes sin estado
   declarado (N)", visible sólo si `preview.total > 0`, con:
   - una fila por propuesta: número, título, `estado_propuesto`, chip de `confianza`, y la evidencia;
   - checkbox por fila, **desmarcado por default** (nada se aplica sin marcarlo);
   - **(v3 / ADICIÓN ARQUITECTO 4)** las filas con `aplicable === false` (`confianza ===
     "sin_evidencia"`, medido: **la mayoría**) van **sin checkbox**, con la leyenda *"sin evidencia —
     elegí vos la etapa"* y un `<select>` con los 4 estados del vocabulario + una opción vacía por
     default. Sólo cuando el operador elige uno, esa fila pasa a ser seleccionable y su item viaja con
     `estado_elegido`. **Nunca** se preselecciona un valor: el default es "no decidido";
   - los planes de `ya_resueltos_por_ledger` se listan aparte, **sin checkbox**, con la leyenda
     "ya resuelto por el supervisor — no hace falta normalizar";
   - botón "Ver diff" → llama `normalizeApply(seleccionados, true)` (dry-run) y muestra el diff;
   - botón "Escribir estado en los .md seleccionados" → **deshabilitado** si
     `STACKY_PLANS_NORMALIZE_APPLY_ENABLED` está OFF, con hint: *"Activá 'Aplicar la normalizacion de
     estados a los .md' en Configuración del arnés para habilitarlo."*;
   - al hacer click, confirmación mostrando cuántos archivos se van a modificar. Usá el **Dialog
     canónico del Plan 164** si está disponible (ubicalo con
     `Select-String -Path "Stacky Agents\frontend\src" -Pattern "ConfirmDialog|useConfirm" -Recurse | Select-Object -First 5`),
     **no** un `window.confirm` nuevo;
   - tras un apply exitoso, refrescar el tablero (el servidor ya invalidó su cache en F2.5, así que un
     `refresh=1` devuelve el estado nuevo de inmediato).

> **Cómo sabe la app si la flag está OFF (v3/C12 — literal, no "leé de ahí").** Las flags de UI se
> exponen en **`/api/diag/health`**, ya envuelto en `endpoints.ts:3306`
> (`Diag.get(): Promise<HealthResponse>`), y el patrón de lectura vigente en el repo es
> `const f = r.flags.find((x) => x.key === "STACKY_PLANS_NORMALIZE_APPLY_ENABLED");` — copiá la forma
> de `App.tsx:211`. **No inventes un endpoint nuevo ni agregues una llamada nueva**: si la página ya
> tiene el health cargado, reusá ese estado. Si la clave no aparece (servidor viejo), tratá la flag
> como **apagada** y mostrá el hint: nunca habilites un botón de escritura por falta de información.

**`sha256_visto` en el cliente:** la app **no calcula** ningún hash. Toma el `sha256_visto` que vino en
cada propuesta del preview y lo devuelve tal cual en el item del apply. Si el operador deja el panel
abierto un rato y el archivo cambió, el servidor lo omite con su razón y la UI la muestra (C7).

**Test (vitest, lógica pura — la UI no se testea sin RTL):** crear
`Stacky Agents/frontend/src/plansBoard/normalize.test.ts` sobre helpers puros que **deben vivir en**
`Stacky Agents/frontend/src/plansBoard/normalize.ts` (`.ts` puro, **no** `.tsx`):

| # | Función | Caso |
|---|---|---|
| 1 | `seleccionablesPorDefecto(propuestas)` | devuelve `[]` (nada preseleccionado) |
| 2 | `resumenConfianza(propuestas)` | `{alta: n, media: n, sin_evidencia: n}` correcto *(v3: ya no existe `baja`)* |
| 3 | `puedeAplicar(flagOn, seleccionados)` | `false` si `flagOn === false`; `false` si `seleccionados.length === 0`; `true` si ambos ok |
| 4 | `textoConfirmacion(seleccionados)` | contiene la cantidad y la palabra `"archivos"` |
| 5 | `itemsParaApply(propuestas, seleccionados, elegidos)` | devuelve `[{filename, sha256_visto, estado_elegido}]` — **nunca** pierde el `sha256_visto` ni manda claves de más |
| 6 | `itemsParaApply` con una propuesta sin `sha256_visto` | la **excluye** (no manda un item inválido que el servidor rechazaría con 400) |
| 7 | **(v3/ADICIÓN 4)** `esSeleccionable(propuesta, elegidoDelOperador)` | `false` si `propuesta.aplicable === false` **y** no hay elegido; `true` si `aplicable === true`; `true` si `aplicable === false` **y** el elegido está en los 4 valores; `false` si el elegido es `""` o cualquier otra cosa |
| 8 | **(v3/ADICIÓN 4)** `itemsParaApply` sobre una propuesta `sin_evidencia` **sin** elegido | la **excluye**: la app **no puede** mandar al servidor un item que el servidor va a rechazar. La guardia vive en los dos lados |

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/normalize.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** 8 passed, `tsc --noEmit` exit 0, y
`Select-String -Path "Stacky Agents\frontend\src\pages\PlansBoardPage.tsx" -Pattern "style=\{\{" | Measure-Object`
devuelve el **mismo** número que antes de empezar (ver §9 si el 264 ya se mergeó).

**Flags:** `STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED` (ON) para el panel;
`STACKY_PLANS_NORMALIZE_APPLY_ENABLED` (OFF, categoría B) para el botón de escritura.
**Impacto por runtime:** ninguno (UI + handler determinista).
**Trabajo del operador:** ninguno para ver; opt-in explícito para escribir.

---

### F7 — Cierre: verificación consolidada y huella de regresión

**Objetivo.** Dejar constancia verificable de que los 6 KPI se cumplen.

**Un archivo a editar (v2 / C17, reescrito en v3 / C7):**
`Stacky Agents/docs/sistema/error_fingerprints.json`.

> **v3 / C7 — los campos que pedía el v2 NO EXISTEN.** El v2 mandaba escribir "síntoma / causa raíz /
> detección / fix". El esquema real, congelado por `tests/test_error_fingerprints_catalog.py:19`,
> exige **exactamente** estas 9 claves: `id`, `title`, `class`, `status`, `log_pattern`, `log_guarded`,
> `killed_by`, `guard_test`, `self_test` — con `status ∈ {"resolved","open","by_design"}`, un
> `log_pattern` que **compile** como regex, y un `self_test` = `{"matches": [...], "clean": [...]}`
> cuyos `matches` **tienen que matchear** el patrón y cuyos `clean` **no**. Es un catálogo de
> **patrones de registro**, no de síntomas de pantalla: por eso la huella de este plan cuelga de la
> **única línea de registro** que el plan introduce (la del rollback de F2.5), que es además su único
> camino destructivo. Entrada exacta a agregar al final de `fingerprints`:

```json
{
  "id": "PLAN263-ROLLBACK-NORMALIZACION-ESTADO",
  "title": "La normalizacion de estados de un plan se revirtio sin completar",
  "class": "data-integrity",
  "status": "resolved",
  "log_pattern": "\\[plan263\\] rollback de normalizacion: (\\S+)",
  "log_guarded": true,
  "killed_by": "plan 263 F2.5 (transaccion de 3 patas con rollback) + F3 (guardia TOCTOU por sha256)",
  "killed_commit": null,
  "date_resolved": "2026-07-27",
  "guard_test": "tests/test_plan263_migration.py",
  "self_test": {
    "matches": ["[plan263] rollback de normalizacion: 51_PLAN_X.md (ledger corrupto)"],
    "clean": ["[plan263] normalizacion aplicada: 51_PLAN_X.md"]
  },
  "evidence": "backend/services/plans_estado_migration.py (apply_estado_migration restaura el .md desde memoria si falla la pata 2 o la 3); backend/tests/test_plan263_migration.py casos 17, 19 y 20"
}
```

> **Rojo ajeno MEDIDO:** `tests/test_error_fingerprints_catalog.py` sale **3 failed / 5 passed** en el
> árbol limpio del 2026-07-27 (`PLAN239-OUTLET-EN-BLANCO` sin `self_test`, y un `status: "guarded"`
> fuera del enum). **No los arregles** (deuda de otro plan, §7). Tu entrada **sí** tiene que cumplir el
> esquema: verificalo con el comando de abajo, que valida **sólo la tuya**.

```powershell
& "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import json,re,pathlib; d=json.loads(pathlib.Path('Stacky Agents/docs/sistema/error_fingerprints.json').read_text(encoding='utf-8')); fp=[f for f in d['fingerprints'] if f['id']=='PLAN263-ROLLBACK-NORMALIZACION-ESTADO'][0]; req=('id','title','class','status','log_pattern','log_guarded','killed_by','guard_test','self_test'); assert all(k in fp for k in req), [k for k in req if k not in fp]; assert fp['status'] in ('resolved','open','by_design'); p=re.compile(fp['log_pattern']); assert all(p.search(s) for s in fp['self_test']['matches']); assert not any(p.search(s) for s in fp['self_test']['clean']); print('OK')"
```

**Correr, en este orden**, y pegar la salida en el "Registro de implementación" que se agrega al final
de **este** documento:

```powershell
$py = "Stacky Agents\backend\.venv\Scripts\python.exe"
& $py -m pytest "Stacky Agents\backend\tests\test_plan263_estado_fallback.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan263_estado_guard.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan263_migration.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan128_plans_board_parser.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan128_plans_board_endpoints.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan237_plans_triage.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan196_actions_api.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_help.py" -q   # 4 failed AJENOS: exigí delta 0, no exit 0
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_error_fingerprints_catalog.py" -q  # 3 failed AJENOS: delta 0
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/model.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/__tests__/actions.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/normalize.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

> **Nota sobre los nombres de test de 128/237/196:** si alguno de esos archivos no existe con ese
> nombre exacto, ubicá los reales con
> `Get-ChildItem "Stacky Agents\backend\tests" -Filter "test_plan128*"` (idem 237 y 196) y corré los que
> aparezcan. **No los saltees.**

> **Regresión obligatoria:** los tests `test_plan128_*`, `test_plan237_*` y `test_plan196_*` son de
> planes ya cerrados. Si alguno se pone rojo, el fallback rompió un contrato existente ⇒ **arreglalo
> antes de cerrar**, no lo pongas en una allowlist. Si estaba rojo **antes** de tu cambio, probalo con
> un worktree del commit base y anotalo como rojo ajeno; no lo adoptes.

**Criterio binario (v3 / C4+C7 — "todos exit 0" era falso).** Los **17** comandos salen exit 0
**excepto los dos con deuda ajena medida**, que se juzgan por **delta cero**:

| Comando | Criterio |
|---|---|
| los 14 restantes (`test_plan263_*`, 128, 237, 196, flags, requires, ratchet meta, vitest ×4, `tsc`) | **exit 0**, sin excepciones |
| `test_harness_flags_help.py` | **exactamente 4 failed**, los mismos 4 de la línea base; ni uno más. Más el comando por entrada de F0 imprimiendo `OK` |
| `test_error_fingerprints_catalog.py` | **exactamente 3 failed**, los mismos 3. Más el comando por entrada de arriba imprimiendo `OK` |

Medí la línea base de esos dos **antes** de tocar nada y pegá los dos conteos en el registro. Cualquier
fallo **nuevo** en ellos es tuyo.

**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación |
|---|---|---|---|
| **R1** | El fallback muestra "Implementado" en planes que **no** lo están y el operador les cree. | **Alta** (es el diseño pedido) | `estado_origen: "inferido"` (y su derivado `estado_inferido`) viaja siempre; el chip dice **"(inferido)"**; la acción sugerida dice literalmente *"no declara **Estado:**"*. *(v3/C1: la mitigación del v2 —"la regla 4 los deja en `PROPUESTO`"— era **falsa**: medida, la regla 4 matcheaba **0** archivos. La mitigación real es la **[ADICIÓN ARQUITECTO 4]**: sin evidencia no hay propuesta escribible.)* |
| **R2** | Con el fallback, el bucket `SIN_SUPERVISAR` salta de ~N a ~N+79 y el triage se vuelve inútil por volumen. | Alta | El panel de F6 separa visualmente los inferidos, y `totals["inferidos"]` permite filtrarlos. El filtro por bucket del Plan 237 sigue funcionando. Medir tras F1: si `SIN_SUPERVISAR > 100`, priorizar F3 sobre F5. |
| **R3** | `suggest_next_action` cambia de firma y rompe `test_plan128_plans_board_parser.py`. | Media | El parámetro nuevo es **keyword-only con default** (`*, estado_inferido: bool = False`) ⇒ los llamadores viejos compilan igual. El caso 17 de F1 lo prueba explícitamente y F7 corre ese test. |
| **R4** | La escritura de F3 corrompe un `.md` del operador (que además tiene cambios sin commitear). | Media | Escritura atómica (`.tmp` + `os.replace`), idempotente, guardia de path traversal, guardia TOCTOU por `sha256_visto`, `dry_run` por default, lista explícita de archivos, rollback de 3 patas, y la flag nace **OFF**. El operador ve el diff antes. Y el `.md` sigue versionado en git: el `git diff` es el backup. |
| **R5** | El baseline del ratchet queda stale y el arnés se pone rojo por un archivo borrado o normalizado. | Media | La pata 3 de F2.5 lo poda sola en el mismo apply. Para el borrado manual, el test 3 de F2 da el mensaje exacto de qué sacar del JSON. |
| **R6** | La tokenización del CSS rompe el layout en `cómodo` (los tokens dan menos px que el hardcode). | Media | *(v3/C14 — corregido el enunciado)* La tabla de F5 cubre los **15 valores distintos** que aparecen en las 31 líneas, verificado uno por uno; 14 de ellos mapean a un token **igual o inmediatamente superior** en cómodo (`1.5rem`=24px → `--space-7`=24px exacto), y el único que baja es `0.15rem` (2,4px → 2px): **0,4 px**, imperceptible. `padding: 0 0.35rem` conserva el `0` literal (no hay token cero). Smoke visual obligatorio en las **2** densidades. |
| **R7** | Un deploy congelado (PyInstaller) sin `.git` rompe algo. | Baja | `repo_root()` ya devuelve `None` sin `.git` y `collect_unpushed_docs` degrada a `None` (`plans_board.py:647-652`, `:660-663`). Nada de este plan agrega dependencia de git. En congelado, `docs/` puede ser read-only: `apply_estado_migration` captura el `OSError` y devuelve `omitidos` con razón, sin lanzar. |
| **R8** | `test_harness_flags_help` sale rojo. | Media | Ese archivo puede traer fallos **ajenos preexistentes**. *(v2/C3: el v1 decía que bastaba con `label`/`description` no vacíos — falso.)* Lo que el gate mide es: **cobertura 100 % de `PLAIN_HELP`**, `on/off` empezando con `"Si "`, largos ≤200/240/240/300, y cero palabras de `JARGON_DENYLIST` / cero MAYÚSCULAS_CON_GUION / cero `F`+dígito. Las 3 entradas de F0.5 ya cumplen. Aislá tus rojos de los ajenos con un worktree del commit base. |
| **R9** | *(v2)* Normalizar un plan aprobado lo des-aprueba y dispara una re-supervisión cara. | **Alta si no se mitiga** | F2.5 pata 2 (re-sellado del ledger) + F1.5 (`ya_resueltos_por_ledger` ni siquiera se proponen). Caso 14 de F3 lo prueba (**KPI-6 = 0**). |
| **R10** | *(v2)* Una sesión paralela sobre este mismo árbol edita un `.md` entre el preview y el apply. | Media (hay sesiones paralelas vivas) | Guardia TOCTOU: `sha256_visto` por archivo; el offset se re-deriva del archivo recién leído. Caso 13 de F3. |
| **R11** | *(v2)* El plan colisiona con 260/264/265 en los archivos compartidos de flags y en `PlansBoardPage.tsx`. | **Alta** (los 4 tocan los mismos 5 archivos) | §9: bloques comentados por plan, orden por número, y frontera explícita con el 264 dentro de `PlansBoardPage.tsx`. |
| **R12** | *(v3/C5)* La pata 2 sobrescribe `ledger.json` con lo que devolvió `load_ledger()` (sólo el sub-dict `planes`) y **los 47 planes aprobados pierden su aprobación en silencio**. | **Alta si no se mitiga** — es el modo de fallo natural de reusar la función de lectura | Contrato de escritura explícito en F2.5 (leer el documento COMPLETO, tocar **una** clave, nunca `load_ledger()` para escribir) + casos 19 y 20 de F3, que comparan `version` y la entrada del plan vecino byte a byte. |
| **R13** | *(v3/C1+ADICIÓN 4)* El operador aprieta "aplicar" sobre las filas sin evidencia porque son la mayoría y el diff "se ve bien", y escribe a disco decenas de estados inventados. | Media | Esas filas **no tienen checkbox**: hay que elegir la etapa a mano por fila. El servidor las rechaza igual si llegan sin `estado_elegido` (guardia en los dos lados, casos 21-22), y la línea escrita **dice** que la eligió el operador y que no había evidencia. El `git diff` del `.md` sigue siendo el backup. |

---

## 7. Fuera de scope

- **No** se cambia el diseño del triage del Plan 237 ni el orden de `TRIAGE_BUCKETS`.
- **No** se tocan los botones de acción del Plan 196 (proponer/criticar/implementar/supervisar), ni
  `frontend/src/plansBoard/actions.ts` (v2/C16: verificado, no hace falta).
- **No** se hace `git commit` ni `git push` de los `.md` normalizados: eso queda 100 % manual.
- **No** se corre el supervisor automáticamente sobre los 79 planes (sería categoría A: quema tokens).
- **No** se agrega RBAC, ni multiusuario, ni auth. `confirm: true` es un seguro anti-click, no un permiso.
- **No** se refactoriza `PlansBoardPage.tsx` más allá del panel de F6 y los inline styles congelados.
- **No** se toca `evolution/PlansSection.tsx` salvo que `tsc` lo exija por el tipo nuevo.
- **No** se cambia el TTL ni la política del cache del tablero: sólo se **invalida** tras una escritura.
- **No** se reescribe el parser de encabezados (`_ESTADO_RE`, `parse_plan_header`, `_read_header_cached`,
  `_PLAN_FILE_RE`): se **importan**. Tampoco se corrige la docstring de `_read_header_cached` que dice
  "bytes" donde el código lee caracteres (fuera de scope; archivo compartido con el 265).
- *(v3/C4)* **No** se escriben las **79 entradas faltantes de `PLAIN_HELP`** que tienen a
  `tests/test_harness_flags_help.py` en 4 rojos ni se tocan las entradas ajenas que citan keys en
  MAYÚSCULAS: es deuda de otros planes y merece su propio plan. Sólo se exige **delta cero**.
- *(v3/C7)* **No** se arreglan los **3 rojos** de `tests/test_error_fingerprints_catalog.py`
  (`PLAN239-OUTLET-EN-BLANCO` sin `self_test`, `status: "guarded"` fuera del enum). Misma regla:
  delta cero.
- *(v3/C1)* **No** se infiere estado con ningún modelo, ni con heurísticas basadas en el número del
  plan (`_umbral_reciente` se **elimina**), ni con búsquedas difusas en el cuerpo del documento. Si no
  hay un marcador estructural o el ledger, **no hay propuesta**.

---

## 8. Orden de implementación y DoD

**Orden (estricto, por dependencia):**

1. **Medición inicial (v3 — son CUATRO números, no dos).** Correr §1.1 y anotar `total` y `sin estado`;
   correr `pytest tests/test_harness_flags_help.py -q` y anotar el `N failed` (esperado: **4**); correr
   `pytest tests/test_error_fingerprints_catalog.py -q` y anotar el `N failed` (esperado: **3**). Esos
   dos conteos son tu línea base de deuda ajena: el criterio de F7 es **delta cero**, no exit 0.
   Anotá también el conteo de `style={{` de `PlansBoardPage.tsx` (esperado: **3**).
2. **F0** — flags, las 6 patas (todo lo demás las lee).
3. **F1 + F1.5** — `resolve_estado()` + `estado_origen` + `build_board` (el núcleo; sin esto no hay KPI-1 ni KPI-3).
4. **F2** — ratchet anti-regresión + registro en las dos listas del arnés (protege lo de F1 hacia adelante).
5. **F4** — modelo de la app (consume lo de F1; sin esto la UI muestra un chip incoherente).
6. **F5** — densidad CSS (independiente de F1-F4; se puede hacer en paralelo si hay dos manos).
7. **F3 + F2.5** — migración con evidencia y transacción de 3 patas (necesita F1 para saber qué normalizar y F2 para tener baseline que podar).
8. **F6** — panel de normalización (necesita F3 y F4).
9. **F7** — cierre, huella de regresión y verificación.

**Definición de Hecho (DoD) — global, binaria:**

- [ ] Los **17** comandos de F7 con el criterio de su tabla: 14 en **exit 0** y los 2 con deuda ajena medida (`test_harness_flags_help.py` = **4 failed**, `test_error_fingerprints_catalog.py` = **3 failed**) con **delta cero** respecto de la línea base tomada antes de empezar.
- [ ] **KPI-7:** ninguna propuesta con `confianza == "sin_evidencia"` se escribió sin `estado_elegido` del operador (casos 21-22 de F3 verdes; centinela del corpus vivo, caso 23, verde).
- [ ] **KPI-8:** tras un apply, `ledger.json` conserva `version`, las 47 entradas, y las entradas ajenas byte-idénticas (casos 19-20 de F3 verdes).
- [ ] `estado_inferido == (estado_origen == "inferido")` para **todas** las cards (caso 18 de F1) y el chip de una card `estado_origen: "ledger"` **no** dice "(inferido)" (casos 4 y 4b de F4).
- [ ] **[v4/ADICIÓN 6]** `sum(totals["por_origen"].values()) == totals["total"] menos las SIN_DOCUMENTO`... en la práctica, `sum(totals["por_origen"].values()) == len(board["plans"])` (caso 19 de F1).
- [ ] **[v4/C2]** `plans_estado_migration._LEDGER_OK_VEREDICTOS is plans_board._LEDGER_OK_VEREDICTOS` (caso 25 de F3): la Regla 1 no reescribió la tupla de veredictos a mano.
- [ ] **[v4/C1]** Ni `config.py` ni `harness_flags.py` quedaron con un bloque de Plan 263 insertado a mitad de otra flag: `python -c "import ast; ast.parse(open('Stacky Agents/backend/config.py', encoding='utf-8').read())"` y el mismo chequeo sobre `harness_flags.py` no lanzan `SyntaxError` (verificación mínima de que el punto de inserción se ubicó por marcador, no por número stale).
- [ ] `api/plans_board.py` lee las flags con `getattr(config, …)` y **no** contiene la cadena `config.config` (`Select-String -Path "Stacky Agents\backend\api\plans_board.py" -Pattern "config\.config"` no devuelve nada).
- [ ] `sum(1 for p in board['plans'] if p['estado_efectivo']=='SIN_ESTADO')` ⇒ **0** (KPI-3).
- [ ] `grep -cE '^\s*(padding|margin|gap)[^:]*:\s*[^;]*(rem|px)' PlansBoardPage.module.css` ⇒ **0** (KPI-2).
- [ ] El conteo de `style={{` en `PlansBoardPage.tsx` **no aumentó** respecto de la medición inicial.
- [ ] Ningún literal hex nuevo en `PlansBoardPage.module.css` (ratchet `hexByFile` sin subir).
- [ ] **Las 6 patas de F0 hechas**, en los **5** archivos correctos: `config.py`, `services/harness_flags.py` (registry **y** `_CATEGORY_KEYS`), `services/harness_flags_help.py`, `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`.
- [ ] La flag OFF **no** declara `default=` y **no** está en el conjunto curado; las 2 ON declaran `default=True` y **sí** están.
- [ ] Las 3 aristas `requires` son de **profundidad 1** (todas a `STACKY_PLANS_BOARD_ENABLED`) y están congeladas en `_REQUIRES_MAP_FROZEN`.
- [ ] `tests/test_plan263_*.py` (3 archivos) registrados en **ambas** listas `HARNESS_TEST_FILES` (`.sh` y `.ps1`), y `test_harness_ratchet_meta.py` verde.
- [ ] Prueba negativa del ratchet ejecutada y el archivo `999_PLAN_PRUEBA_RATCHET.md` **borrado**.
- [ ] `test_regla_unica_de_estado` verde (ratchet y tablero comparten la regla del **estado**, borde multibyte incluido) **y** `test_regla_de_archivo_unica` verde (comparten la regla del **archivo**: `_PLAN_FILE_RE` importado, identidad de objeto con `is`).
- [ ] **KPI-6:** tras un apply sobre un plan aprobado en el ledger, su card sigue en `estado_efectivo == "APROBADO"` y `doc_drift is False`.
- [ ] Tras un apply, `plans_estado_baseline.json` quedó podado solo y `test_plan263_estado_guard.py` sigue verde **sin edición manual**.
- [ ] Smoke visual hecho en las **dos** densidades, con los dos conteos de cards anotados (KPI-5 ≥ 11 en compacto).
- [ ] Con `STACKY_PLANS_NORMALIZE_APPLY_ENABLED=false`, `git status --porcelain "Stacky Agents/docs"` es **idéntico** antes y después de llamar al endpoint de apply.
- [ ] Huella `PLAN263-ROLLBACK-NORMALIZACION-ESTADO` registrada en `docs/sistema/error_fingerprints.json` **con las 9 claves del esquema real** (`self_test` incluido) y el comando de validación de F7 imprimiendo `OK`.
- [ ] El "Registro de implementación" se agrega al final de **este** documento con la salida real de los comandos, los números medidos y los desvíos encontrados.
- [ ] `git commit` del trabajo hecho **con pathspec explícito** (`git commit -- "<ruta>" ...`): el working tree tiene cambios de otras sesiones y un commit de índice compartido se los roba. **Prohibido** `git add -A`, `reset`, `amend`, `stash`, `checkout` y `--no-verify`. El `push` es manual.

---

## 9. Convivencia con los planes hermanos 260 / 264 / 265 (v2 / C18)

Los cuatro planes de esta tanda editan **los mismos 5 archivos compartidos**. El riesgo real y ya
documentado del repo: **git hace 3-way merge SIN marcar conflicto cuando dos ramas agregan la misma
línea de cierre a una estructura existente**, dejando un duplicado silencioso que ni los marcadores ni
el compilador atrapan.

> **v4 / C1 — nota de alcance.** El drift medido en el CHANGELOG v3→v4 **no vino de 260/264/265**
> (los tres siguen `NO IMPLEMENTADO`, re-verificado el 2026-07-29 en sus propios encabezados) sino de
> los planes 267/268/269/270, ya mergeados a `main` en el ínterin, que también dan de alta flags en
> `config.py` y `harness_flags.py`. La mitigación de F0.1/F0.2 (anclar por marcador de texto, no por
> número) es general: aplica ante **cualquier** plan que se mergee después, no sólo ante los 3 hermanos
> nombrados en esta sección — `config.py` y `harness_flags.py` los edita prácticamente todo plan del
> repo, así que su línea de inserción nunca es una constante de confiar a ciegas.

**Reglas de convivencia para este plan:**

| Archivo compartido | Regla para el 263 |
|---|---|
| `backend/config.py` | Bloque propio precedido por `# ── Plan 263 — …`, insertado **después de `:1920`**. No tocar los bloques de 260/264/265. |
| `backend/services/harness_flags.py` (registry) | Bloque propio precedido por `# ── Plan 263 — …`, **después** del bloque del Plan 196. |
| `backend/services/harness_flags.py` (`_CATEGORY_KEYS`) | 3 líneas contiguas con comentario `# Plan 263`, **dentro** de `"observabilidad_notif"`, junto a la del Plan 196. |
| `backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`) | 2 líneas contiguas con comentario `# Plan 263`, al final del conjunto. **Nunca** reordenar el conjunto entero (eso genera conflictos gigantes con los hermanos). |
| `backend/services/harness_flags_help.py` | 3 entradas contiguas precedidas por `# ── Plan 263 — …`, junto a la del Plan 196. |
| `backend/tests/test_harness_flags_requires.py` | 3 aristas contiguas con su comentario, **al final** del dict, antes del `}`. |
| `backend/scripts/run_harness_tests.sh` / `.ps1` | 3 líneas `tests/test_plan263_*.py`. El orden alfabético las pone naturalmente antes de las del 264/265. **La sintaxis del `.ps1` es distinta a la del `.sh`**: no copies las líneas de uno al otro. |
| `frontend/src/api/endpoints.ts` | 2 claves dentro del objeto `PlansBoard` existente, con comentario `Plan 263`. El 264 agrega las suyas en **otros** objetos. |

**Frontera con el 264 en `frontend/src/pages/PlansBoardPage.tsx` (el punto caliente):**

Los dos planes editan este archivo. La partición es por **región**, y es innegociable:

- **263 posee:** (a) `PlansBoardPage.module.css` **entero** (el 264 no lo toca), y (b) **un bloque nuevo
  al final del árbol de render**: el panel plegable "Planes sin estado declarado (N)" de F6.
- **264 posee:** la **fila de acciones** de cada card (donde va su selector de modelo/effort). El 263
  **no** toca esa fila.
- **Ninguno de los dos** renombra props, estados ni handlers del otro.
- **Quien llegue segundo** rebasa sobre el primero y, antes de dar por cerrada su fase, corre:
  `npx tsc --noEmit` **y** el ratchet de UI **y** vuelve a contar los `style={{` — la línea base pasa a
  ser el número que dejó el que llegó primero (el criterio es "no aumentar", no "exactamente 3").
- Si el 264 ya se mergeó, el 263 **no** revierte su selector aunque `tsc` proteste: se adapta.

**Frontera con el 265 en `backend/services/plans_board.py`:** el 263 agrega `resolve_estado`,
`_fallback_activo`, las constantes de origen y **dos claves aditivas** al card. No renombra ni borra
nada. Cualquier lectura que el 265 haga del card sigue funcionando; si el 265 arma cards por su cuenta,
debe copiar las dos claves nuevas (forma uniforme).

**Sin dependencia de orden:** el 263 **no** necesita que 260/264/265 estén implementados, ni al revés.
Los 4 pueden implementarse en cualquier orden respetando las reglas de arriba.

---

## 10. Registro de implementación

*(Lo completa quien implemente el plan: salida real de los comandos, los números medidos por §1.1, el
conteo de cards del smoke visual en las dos densidades, y todo desvío respecto de este documento.)*
