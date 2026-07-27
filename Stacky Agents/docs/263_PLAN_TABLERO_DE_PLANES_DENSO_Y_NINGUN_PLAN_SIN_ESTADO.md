# Plan 263 — Tablero de planes denso y ningún plan sin estado: fallback único, migración con evidencia y guardia anti-regresión

**Estado:** CRITICADO v2 (2026-07-27) · **Autor:** pipeline `proponer-plan-stacky` · **Juez:** `criticar-y-mejorar-plan` — **v1 RECHAZADO** (6 BLOQUEANTES), reescrito a v2 in place

---

## 0. CHANGELOG v1 → v2

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

El Tablero de Planes muestra hoy **79 de 216 planes (36,6 %) con estado `SIN_ESTADO`**, y para esos 79 la
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

> **v2 / C8 — los KPI son valores MEDIDOS, no constantes de fe.** El 79 y el 216 se midieron el
> 2026-07-27 con la regla EXACTA del parser (`_ESTADO_RE` + `_HEADER_READ_CHARS=4000` de
> `services/plans_board.py:25,30`), no con un grep aproximado. El v1 decía 78/212 y **ese número no
> es reproducible con su propio comando**. El implementador **vuelve a medir al arrancar** con el
> comando de §1.1 y usa **su** número como línea base; el criterio binario es el **0** final, no el 79.

### 1.1 Comando de medición (correr ANTES de F0 y anotar el resultado)

```powershell
& "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); import pathlib, re; from services.plans_board import _ESTADO_RE, _HEADER_READ_CHARS; d=pathlib.Path('Stacky Agents/docs'); fs=sorted(p for p in d.iterdir() if re.match(r'^[0-9]+_PLAN_.*\.md$', p.name)); sin=[p.name for p in fs if not _ESTADO_RE.search(p.open('r',encoding='utf-8',errors='replace').read(_HEADER_READ_CHARS))]; print('total', len(fs), '| sin estado', len(sin))"
```

Salida de referencia el 2026-07-27: `total 216 | sin estado 79`.

| KPI | Antes (medido 2026-07-27) | Después (criterio binario) |
|---|---|---|
| **KPI-1** Planes sin acción disponible en el tablero | **79** | **0** |
| **KPI-2** Declaraciones de espaciado sordas a la densidad en `PlansBoardPage.module.css` | **31** | **0** |
| **KPI-3** `estado_efectivo` con valor `SIN_ESTADO` en la respuesta de `/api/plans-board/list` | **79** | **0** |
| **KPI-4** Planes nuevos que pueden guardarse sin `**Estado:**` sin que nada avise | ilimitado | **0** (ratchet rojo) |
| **KPI-5** Cards visibles sin scroll en el tablero a 1080 px de alto, densidad `compacto` | ~7 | **≥ 11** |
| **KPI-6** *(v2/C6)* Planes aprobados por el supervisor que la normalización des-aprueba | n/a | **0** |

Comandos que miden KPI-1..KPI-4 y KPI-6: ver §8 (DoD).

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
> que verificablemente **no** están implementados — p. ej. `243`, `247`..`252`. Por eso el fallback
> **nunca** se aplica en silencio: viaja siempre acompañado de `estado_inferido: true` y
> `estado_origen: "inferido"`, la UI lo rotula "inferido" y la acción sugerida dice explícitamente que
> el estado no está declarado. La verdad se escribe a disco sólo por la migración con evidencia de F3,
> que es opt-in y confirmada.

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
   `uiDebtBaseline.json`. Regla de estado: **se importa** de `services/plans_board.py`, no se
   reimplementa. Parser, tablero, triage y acciones de 128/237/196: **no se reescriben**.
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
| **estado inferido** | **NUEVO**: `True` cuando el documento no declaraba estado y se aplicó el fallback. |
| **estado origen** | **NUEVO (v2, ADICIÓN ARQUITECTO 2)**: `"declarado"` \| `"inferido"` \| `"ledger"`. Explica *por qué* el card muestra lo que muestra. `estado_inferido` se conserva como azúcar de `estado_origen == "inferido"`. |
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
| 3 | `backend/services/harness_flags.py` (`_CATEGORY_KEYS`, cat. `"observabilidad_notif"`, abre en `:305`) | las **3** keys | `test_every_registry_flag_is_categorized` (`tests/test_harness_flags.py:902`) |
| 4 | **`backend/tests/test_harness_flags.py`** (`_CURATED_DEFAULTS_ON`, abre en **`:467`**) | **sólo las 2 ON** | `test_default_known_only_for_curated` (`tests/test_harness_flags.py:974`) |
| 5 | `backend/services/harness_flags_help.py` (`PLAIN_HELP`, abre en `:25`) | las **3** entradas | `test_plain_help_covers_all_registry_keys` (`tests/test_harness_flags_help.py:32`) |
| 6 | `backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`) | las **3** aristas | `test_requires_map_is_frozen` (`tests/test_harness_flags_requires.py:312`) |

---

#### F0.1 — `backend/config.py`

Insertar **después de la línea 1920** (fin del bloque `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED`, que va
de `:1918` a `:1920`; **`:1922` ya es el comentario del Plan 167** y meterse ahí parte ese comentario
de su flag):

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

> **v2 / C15:** el patrón real vigente en ese bloque es `.strip().lower() == "true"` (ver
> `config.py:1911-1920`), **no** `in ("1", "true", "yes")` como decía el v1. Copiá el de arriba tal cual.
> Si el archivo real difiere del snippet, **gana el archivo**.

#### F0.2 — `backend/services/harness_flags.py` · las 3 `FlagSpec`

Agregar **inmediatamente después** del bloque `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED`
(`harness_flags.py:4544-4558`):

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
        # STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED (harness_flags.py:3166-3173, Plan 250).
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

Agregar las **3** keys en la categoría `"observabilidad_notif"` (abre en `harness_flags.py:305`),
junto a `"STACKY_PLANS_PIPELINE_ACTIONS_ENABLED"` (`harness_flags.py:350`):

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

**Criterio binario (v2 / C5 — dice la verdad sobre cada modo de fallo).**
Los tres comandos exit 0. Si alguno falla, la causa es **una de estas cinco y sólo estas cinco**:

| Test rojo | Causa exacta | Pata que falta |
|---|---|---|
| `test_default_known_only_for_curated` → **"Extras (no curadas)"** | una flag `default=True` (o `default=False`, que también cuenta como *conocido*) no está en el conjunto | F0.4 — o le sobra el `default=` a la flag OFF |
| `test_default_known_only_for_curated` → **"Faltantes"** | una key está en el conjunto curado pero su `FlagSpec` no declara `default=` | F0.2 / F0.4 desalineados |
| `test_every_registry_flag_is_categorized` | falta una de las 3 keys en `_CATEGORY_KEYS` | F0.3 |
| `test_plain_help_covers_all_registry_keys` | falta una de las 3 entradas de ayuda llana | F0.5 |
| `test_requires_map_is_frozen` → **"Extras"** | la `FlagSpec` declara `requires=` y la arista no está congelada | F0.6 |

> **Ojo, rojo ajeno conocido:** `test_harness_flags_help.py` puede traer fallos **preexistentes** de
> otros planes. Antes de tocar nada, corré ese archivo **en un worktree del commit base** y anotá
> cuáles ya estaban rojos. Los tuyos son sólo los que nombran una de tus 3 keys. **No adoptes deuda
> ajena y no la escondas en una allowlist.**

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
| 13 | `build_board` sobre un doc **sin** estado **pero aprobado en el ledger sin drift** | `estado_efectivo == "APROBADO"` (el ledger sigue ganando), `estado_inferido is True` y `estado_origen == "ledger"` |
| 14 | `build_board(tmp_docs, None)` sobre 3 docs sin estado | `"SIN_ESTADO" not in board["totals"]` y `board["totals"]["inferidos"] == 3` |
| 15 | **flag OFF** (`monkeypatch.setattr(config.config, "STACKY_PLANS_ESTADO_FALLBACK_ENABLED", False)`) sobre el mismo doc del caso 9 | **una sola aserción:** `card["estado_efectivo"] == "SIN_ESTADO"`, `card["estado_inferido"] is False`, `card["estado_origen"] == "declarado"`, `card["suggested_action"]["kind"] == "revisar"` — es decir, el comportamiento **byte-idéntico al de antes de este plan (263)** |
| 16 | *(v2)* `build_planned_cards` (bucket `SIN_DOCUMENTO`) | cada card trae `estado_inferido is False` y `estado_origen == "declarado"` — **todas** las cards tienen la misma forma |
| 17 | *(v2)* `suggest_next_action("IMPLEMENTADO", None, None, "07")` llamado **posicionalmente con 4 args** | no lanza `TypeError` y devuelve `kind == "supervisar"` (prueba de que el parámetro nuevo es keyword-only con default) |

> **v2 / C12:** el v1 escribía el caso 15 con una corrección tachada adentro ("vuelve a
> `"IMPLEMENTADO"`… **NO**: vuelve a `"SIN_ESTADO"`"). Un modelo menor no puede saber cuál gana. La
> aserción correcta es `"SIN_ESTADO"`. Y el comportamiento de referencia es el **pre-263** (el Plan 260
> es de pipelines y no toca nada de esto).

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
    """(estado_resuelto, inferido).

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
+        estado_resuelto, estado_inferido = resolve_estado(c["estado"])
+        aprobado = bool(ledger_ok and doc_drift is not True)
+        estado_efectivo = "APROBADO" if aprobado else estado_resuelto
+        if aprobado:
+            estado_origen = ORIGEN_LEDGER
+        elif estado_inferido:
+            estado_origen = ORIGEN_INFERIDO
+        else:
+            estado_origen = ORIGEN_DECLARADO
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

**Criterio binario.** 17 passed, 0 failed. Y:

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
distinguen por un booleano que además es ambiguo en el caso 13: un plan **sin estado declarado** pero
**aprobado por el supervisor** llega con `estado_efectivo="APROBADO"` y `estado_inferido=True`, y la UI
no tiene forma de saber que ahí el ledger ya dijo la verdad y **no hace falta normalizar nada**. Sin
este campo, el panel de F6 le propone al operador reescribir un `.md` que ya está resuelto.

**Contrato (aditivo, backward-compatible).** `estado_origen: "declarado" | "inferido" | "ledger"`.
Se computa en `build_board` (ver F1(d)). `estado_inferido` **se conserva** como azúcar
(`estado_origen == "inferido"`), para no romper ningún consumidor.

**Consumidores en este plan:**
- F3 `preview_estado_migration` **excluye por default** los planes con `estado_origen == "ledger"` y
  los reporta aparte en `ya_resueltos_por_ledger` (no hay nada que escribir: el supervisor ya cerró).
- F4 muestra el sufijo `(inferido)` sólo cuando `estado_origen === "inferido"`.

**Tests:** casos 9, 12, 13 y 16 de F1 ya lo cubren. Sin archivo nuevo, sin flag nueva.
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

La regla de "tiene estado" NO se reimplementa acá: se importa de
services.plans_board (_ESTADO_RE + _HEADER_READ_CHARS), que es la misma que usa
el tablero. Ver [ADICIÓN ARQUITECTO 3]: test_regla_unica_de_estado lo prueba.
"""
import json
import pathlib
import re
import sys

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services.plans_board import _ESTADO_RE, _HEADER_READ_CHARS  # noqa: E402

DOCS_DIR = _BACKEND.parent / "docs"
BASELINE_PATH = _BACKEND / "tests" / "plans_estado_baseline.json"
_PLAN_FILE_RE = re.compile(r"^[0-9]+_PLAN_.*\.md$")


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

   Y estos tests:

| # | Test | Qué asegura |
|---|---|---|
| 1 | `test_baseline_existe_y_es_json` | El baseline carga y `sin_estado` es una lista de `str`. |
| 2 | `test_ningun_plan_nuevo_sin_estado` | `set(planes_sin_estado(DOCS_DIR)) - set(baseline) == set()`. Mensaje: `"El plan <archivo> no declara **Estado:**. Agregale la linea o corré la normalización del Plan 263."` |
| 3 | `test_el_ratchet_solo_se_achica` | `set(baseline) - set(planes_sin_estado(DOCS_DIR)) == set()` ⇒ obliga a achicar el baseline cuando un plan se normaliza o se borra. Mensaje: `"El baseline quedó stale: sacá <archivo> de plans_estado_baseline.json (o dejá que la normalización del Plan 263 lo pode sola)."` |
| 4 | `test_baseline_sin_duplicados` | `len(sin_estado) == len(set(sin_estado))`. |
| 5 | **`test_regla_unica_de_estado`** **[ADICIÓN ARQUITECTO 3]** | Escribe en `tmp_path` un `.md` sintético con ~3.900 caracteres **acentuados** de relleno (p. ej. `"á" * 3900`) y la línea `**Estado:** PROPUESTO v1` justo después, de modo que caiga **dentro** de los 4000 *caracteres* pero **fuera** de los 4000 *bytes*. Asserta las tres cosas: (a) `tiene_estado(p) is True`; (b) `parse_plan_header(_texto_encabezado(p))["estado"] == "PROPUESTO"` (la función pública real es **`parse_plan_header(text: str)`**, `plans_board.py:89` — recibe **texto**, no un `Path`); (c) el equivalente por bytes **NO** lo ve: `_ESTADO_RE.search(p.read_bytes()[:4000].decode("utf-8", "replace")) is None`. Es decir: ratchet y tablero coinciden, y el atajo shell habría mentido. Este test impide que alguien "optimice" el ratchet a shell y reintroduzca C9. |
| 6 | `test_baseline_solo_nombres_de_plan` | Toda entrada del baseline matchea `_PLAN_FILE_RE` (nada de rutas ni `..`). |

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

**Criterio binario.** Ambos exit 0 (6 passed en el primero). **Prueba negativa manual obligatoria:**
creá `Stacky Agents/docs/999_PLAN_PRUEBA_RATCHET.md` con una sola línea `# hola`, corré el primer
comando, verificá que **falla** nombrando `999_PLAN_PRUEBA_RATCHET.md`, y **borrá el archivo**
(`Remove-Item "Stacky Agents\docs\999_PLAN_PRUEBA_RATCHET.md"`). Volvé a correr: verde.

**Flag:** ninguna nueva — es un test del arnés, siempre activo.
**Impacto por runtime:** ninguno (test determinista, sin modelo).
**Trabajo del operador: ninguno.**

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

**Rollback.** Las patas 2 y 3 se escriben con el mismo patrón atómico (`.tmp` + `os.replace`). Si la
pata 2 o la 3 fallan (p. ej. el JSON del ledger está corrupto), la función **restaura el `.md`** desde
el contenido original que guardó en memoria antes de la pata 1 y devuelve ese archivo en `omitidos`
con `razon="rollback: no se pudo actualizar el ledger o el baseline"`. **Ningún archivo queda a medias.**

**Por qué re-sellar el ledger no es hacer trampa.** El re-sellado se aplica **sólo** a un cambio que
esta misma función acaba de hacer y que es **puramente aditivo en el encabezado**: inserta una línea
`**Estado:**` y no toca ni una palabra del cuerpo. Se registra en el propio ledger con
`normalizado_por: "plan-263"` y la fecha, así que queda auditable. Cualquier otra edición del `.md`
sigue produciendo drift normal.

**Tests (van en `test_plan263_migration.py`, F3):** casos 13-18 de esa lista.

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
        "estado_propuesto": str,        # "IMPLEMENTADO" | "PROPUESTO" | "CRITICADO" | "IMPLEMENTADO-PARCIAL"
        "confianza": str,               # "alta" | "media" | "baja"
        "evidencia": list[str],         # frases cortas, verificables, en español
        "linea_a_insertar": str,        # p.ej. "**Estado:** IMPLEMENTADO (normalizado 2026-07-27, Plan 263) — sin veredicto de supervisor"
        "insert_after_line": int,       # índice 0-based de la línea tras la cual insertar
        "sha256_visto": str,            # v2/C7 — sha256 del archivo COMPLETO al momento del preview
        "resella_ledger": bool,         # v2/C6 — el ledger tiene doc_sha256 para este plan
      }
    NUNCA lanza. NUNCA escribe.
    """
```

**Reglas de inferencia (en este orden exacto; la primera que matchea gana):**

| Orden | Condición (verificable, sin modelo) | `estado_propuesto` | `confianza` | Evidencia que se agrega |
|---|---|---|---|---|
| 1 | El ledger (`load_ledger`) tiene entrada con `veredicto` en `("APROBADO","TERMINADO-POR-SUPERVISOR")` | `IMPLEMENTADO` | `alta` | `"El supervisor lo aprobó el <fecha> (ledger.json)."` |
| 2 | El doc contiene la subcadena `"Registro de implementación"` o `"IMPLEMENTADA"` en los primeros 8000 chars | `IMPLEMENTADO` | `alta` | `"El propio documento registra fases IMPLEMENTADAS."` |
| 3 | El doc contiene `"veredicto"` y (`"APROBADO"` o `"RECHAZADO"`) en los primeros 8000 chars | `CRITICADO` | `media` | `"El documento trae un veredicto del juez, pero no registro de implementación."` |
| 4 | Ninguna de las anteriores **y** `number > _umbral_reciente(docs_dir)` | `PROPUESTO` | `baja` | `"Plan reciente sin rastro de crítica ni implementación."` |
| 5 | Ninguna de las anteriores | `IMPLEMENTADO` | `baja` | `"Sin evidencia; se aplica el fallback del Plan 263."` |

```python
def _umbral_reciente(docs_dir: Path) -> int:
    """v2/C19 — determinista y sin excepciones.

    El v1 usaba `max(ledger) - 20`: `load_ledger` devuelve un dict con claves
    STRING (ver plans_board.py:451 `ledger.get(str(number))`), así que `max()`
    ordenaba lexicográficamente ("99" > "265") y encima lanzaba ValueError con el
    ledger vacío, contra el contrato "NUNCA lanza".
    """
    numeros = [c["number"] for c in scan_plan_files_with_census(docs_dir)[0]]
    return max(numeros, default=0) - 20
```

> **Por qué la regla 4 existe:** sin ella, planes recientes y realmente pendientes (`243`, `247`..`252`)
> quedarían escritos en disco como `IMPLEMENTADO`, que es exactamente la mentira que R1 advierte. La
> regla 4 los deja en `PROPUESTO` y `confianza: baja`, para que el operador los revise.

```python
def preview_estado_migration(docs_dir: Path) -> dict:
    """{"ok": True, "total": int, "propuestas": [<dict de infer_estado_con_evidencia>, ...],
        "por_confianza": {"alta": int, "media": int, "baja": int},
        "ya_resueltos_por_ledger": [str]}   # v2/F1.5: estado_origen == "ledger", NO se proponen
    SOLO LECTURA. Nunca escribe. Nunca lanza."""


def apply_estado_migration(
    docs_dir: Path, items: list[dict], *, dry_run: bool = True
) -> dict:
    """Escribe la línea **Estado:** en los planes pedidos, UNO POR UNO (transacción F2.5).

    - `items` es una lista EXPLÍCITA de {"filename": str, "sha256_visto": str}:
      no existe "aplicar a todos" implícito y no se acepta el comodín "*".
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

**Casos de test (mínimo 18):**

1. `infer_estado_con_evidencia` con ledger APROBADO → `IMPLEMENTADO`/`alta`.
2. …con doc que dice `"Registro de implementación"` → `IMPLEMENTADO`/`alta`.
3. …con doc que trae `veredicto ... APROBADO` → `CRITICADO`/`media`.
4. …plan reciente sin nada → `PROPUESTO`/`baja`.
5. …plan viejo sin nada → `IMPLEMENTADO`/`baja`.
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

**Endpoints (editar `Stacky Agents/backend/api/plans_board.py`):**

```python
@bp.get("/normalize/preview")          # ruta final: /api/plans-board/normalize/preview
def plans_normalize_preview():
    # Candado 0 (patrón Plan 250): chequear las flags acá, NO confiar en `requires`.
    #   config.config.STACKY_PLANS_BOARD_ENABLED  AND
    #   config.config.STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED
    # deshabilitada -> reusar _disabled_resp() (api/plans_board.py:19-29) -> 404
    # 200 -> preview_estado_migration(plans_board.docs_dir_default())

@bp.post("/normalize/apply")           # ruta final: /api/plans-board/normalize/apply
def plans_normalize_apply():
    # Candado 0: las TRES flags — BOARD AND PREVIEW AND APPLY. Con cualquiera OFF -> 404
    # (_disabled_resp). Esto materializa "APPLY exige PREVIEW" que `requires` NO evalúa.
    # Body: {"items": [{"filename": "...", "sha256_visto": "..."}], "dry_run": true|false,
    #        "confirm": true}
    # 400 si falta `confirm: true`, si `items` está vacío/ausente, o si algún item no
    # trae `sha256_visto`.
    # -> apply_estado_migration(...)
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

**Criterio binario.** 18 passed, 0 failed. Además, con `STACKY_PLANS_NORMALIZE_APPLY_ENABLED=false`,
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
+  return card.estado_origen === "inferido" || card.estado_inferido
+    ? { ...chip, label: `${chip.label} (inferido)` }
+    : chip;
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
| 4 | `estadoChip(card({estado_efectivo:"APROBADO", estado_origen:"ledger"}))` | `.label === ESTADO_CHIP.APROBADO.label` (sin sufijo: el ledger **no** es inferencia) |
| 5 | `filterPlans([...], {estado:"IMPLEMENTADO", ...})` con un card inferido | lo incluye (filtro consistente con el fallback) |
| 6 | el test existente `"cae a SIN_ESTADO ante una clave desconocida"` | **sigue verde sin tocarlo** |

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
así que la verificación visual es a ojo y va documentada, no scripteada. Pasos: abrir `/plans`, poner
la ventana en 1080 px de alto, activar densidad `compacto` con el `DensityToggle`, contar las cards
visibles sin scroll ⇒ **≥ 11** (KPI-5). Repetir en `cómodo` y confirmar que **no** se rompió el layout.
Anotar los dos números en el registro de implementación del plan.

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

2. `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` — un panel plegable "Planes sin estado
   declarado (N)", visible sólo si `preview.total > 0`, con:
   - una fila por propuesta: número, título, `estado_propuesto`, chip de `confianza`, y la evidencia;
   - checkbox por fila, **desmarcado por default** (nada se aplica sin marcarlo);
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

> **Cómo sabe la app si la flag está OFF:** las flags de UI se exponen en **`/api/diag/health`**
> (patrón ya usado por el resto del cockpit). Leé de ahí, no inventes un endpoint nuevo.

**`sha256_visto` en el cliente:** la app **no calcula** ningún hash. Toma el `sha256_visto` que vino en
cada propuesta del preview y lo devuelve tal cual en el item del apply. Si el operador deja el panel
abierto un rato y el archivo cambió, el servidor lo omite con su razón y la UI la muestra (C7).

**Test (vitest, lógica pura — la UI no se testea sin RTL):** crear
`Stacky Agents/frontend/src/plansBoard/normalize.test.ts` sobre helpers puros que **deben vivir en**
`Stacky Agents/frontend/src/plansBoard/normalize.ts` (`.ts` puro, **no** `.tsx`):

| # | Función | Caso |
|---|---|---|
| 1 | `seleccionablesPorDefecto(propuestas)` | devuelve `[]` (nada preseleccionado) |
| 2 | `resumenConfianza(propuestas)` | `{alta: n, media: n, baja: n}` correcto |
| 3 | `puedeAplicar(flagOn, seleccionados)` | `false` si `flagOn === false`; `false` si `seleccionados.length === 0`; `true` si ambos ok |
| 4 | `textoConfirmacion(seleccionados)` | contiene la cantidad y la palabra `"archivos"` |
| 5 | `itemsParaApply(propuestas, seleccionados)` | devuelve `[{filename, sha256_visto}]` — **nunca** pierde el `sha256_visto` ni manda claves de más |
| 6 | `itemsParaApply` con una propuesta sin `sha256_visto` | la **excluye** (no manda un item inválido que el servidor rechazaría con 400) |

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/normalize.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** 6 passed, `tsc --noEmit` exit 0, y
`Select-String -Path "Stacky Agents\frontend\src\pages\PlansBoardPage.tsx" -Pattern "style=\{\{" | Measure-Object`
devuelve el **mismo** número que antes de empezar (ver §9 si el 264 ya se mergeó).

**Flags:** `STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED` (ON) para el panel;
`STACKY_PLANS_NORMALIZE_APPLY_ENABLED` (OFF, categoría B) para el botón de escritura.
**Impacto por runtime:** ninguno (UI + handler determinista).
**Trabajo del operador:** ninguno para ver; opt-in explícito para escribir.

---

### F7 — Cierre: verificación consolidada y huella de regresión

**Objetivo.** Dejar constancia verificable de que los 6 KPI se cumplen.

**Un archivo a editar (v2 / C17):** `Stacky Agents/docs/sistema/error_fingerprints.json` — registrar la
huella de esta clase de regresión, siguiendo el formato que ya usan las entradas vecinas (leelo antes y
copiá su forma exacta):

- **síntoma:** un plan aparece en el tablero sin ninguna acción disponible / el chip dice "Sin estado".
- **causa raíz:** el `.md` no declara la línea `**Estado:**`, o
  `STACKY_PLANS_ESTADO_FALLBACK_ENABLED` está apagada.
- **detección:** el comando de §1.1 devuelve un número > 0 para `sin estado`.
- **fix:** normalizar el estado desde el panel del tablero, o encender la flag.

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
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_help.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
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

**Criterio binario.** Los 16 comandos exit 0, más los comandos de KPI de §8.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación |
|---|---|---|---|
| **R1** | El fallback muestra "Implementado" en planes que **no** lo están (243, 247-252) y el operador les cree. | **Alta** (es el diseño pedido) | `estado_inferido: true` + `estado_origen: "inferido"` viajan siempre; el chip dice **"(inferido)"**; la acción sugerida dice literalmente *"no declara **Estado:**"*. La escritura a disco (F3) usa la **regla 4** que deja los planes recientes en `PROPUESTO`, no en `IMPLEMENTADO`. |
| **R2** | Con el fallback, el bucket `SIN_SUPERVISAR` salta de ~N a ~N+79 y el triage se vuelve inútil por volumen. | Alta | El panel de F6 separa visualmente los inferidos, y `totals["inferidos"]` permite filtrarlos. El filtro por bucket del Plan 237 sigue funcionando. Medir tras F1: si `SIN_SUPERVISAR > 100`, priorizar F3 sobre F5. |
| **R3** | `suggest_next_action` cambia de firma y rompe `test_plan128_plans_board_parser.py`. | Media | El parámetro nuevo es **keyword-only con default** (`*, estado_inferido: bool = False`) ⇒ los llamadores viejos compilan igual. El caso 17 de F1 lo prueba explícitamente y F7 corre ese test. |
| **R4** | La escritura de F3 corrompe un `.md` del operador (que además tiene cambios sin commitear). | Media | Escritura atómica (`.tmp` + `os.replace`), idempotente, guardia de path traversal, guardia TOCTOU por `sha256_visto`, `dry_run` por default, lista explícita de archivos, rollback de 3 patas, y la flag nace **OFF**. El operador ve el diff antes. Y el `.md` sigue versionado en git: el `git diff` es el backup. |
| **R5** | El baseline del ratchet queda stale y el arnés se pone rojo por un archivo borrado o normalizado. | Media | La pata 3 de F2.5 lo poda sola en el mismo apply. Para el borrado manual, el test 3 de F2 da el mensaje exacto de qué sacar del JSON. |
| **R6** | La tokenización del CSS rompe el layout en `cómodo` (los tokens dan menos px que el hardcode). | Media | La tabla de conversión de F5 mapea cada valor a su token exacto o inmediatamente superior en cómodo (`1.5rem`=24px → `--space-7`=24px exacto). Smoke visual obligatorio en las **2** densidades. |
| **R7** | Un deploy congelado (PyInstaller) sin `.git` rompe algo. | Baja | `repo_root()` ya devuelve `None` sin `.git` y `collect_unpushed_docs` degrada a `None` (`plans_board.py:647-652`, `:660-663`). Nada de este plan agrega dependencia de git. En congelado, `docs/` puede ser read-only: `apply_estado_migration` captura el `OSError` y devuelve `omitidos` con razón, sin lanzar. |
| **R8** | `test_harness_flags_help` sale rojo. | Media | Ese archivo puede traer fallos **ajenos preexistentes**. *(v2/C3: el v1 decía que bastaba con `label`/`description` no vacíos — falso.)* Lo que el gate mide es: **cobertura 100 % de `PLAIN_HELP`**, `on/off` empezando con `"Si "`, largos ≤200/240/240/300, y cero palabras de `JARGON_DENYLIST` / cero MAYÚSCULAS_CON_GUION / cero `F`+dígito. Las 3 entradas de F0.5 ya cumplen. Aislá tus rojos de los ajenos con un worktree del commit base. |
| **R9** | *(v2)* Normalizar un plan aprobado lo des-aprueba y dispara una re-supervisión cara. | **Alta si no se mitiga** | F2.5 pata 2 (re-sellado del ledger) + F1.5 (`ya_resueltos_por_ledger` ni siquiera se proponen). Caso 14 de F3 lo prueba (**KPI-6 = 0**). |
| **R10** | *(v2)* Una sesión paralela sobre este mismo árbol edita un `.md` entre el preview y el apply. | Media (hay sesiones paralelas vivas) | Guardia TOCTOU: `sha256_visto` por archivo; el offset se re-deriva del archivo recién leído. Caso 13 de F3. |
| **R11** | *(v2)* El plan colisiona con 260/264/265 en los archivos compartidos de flags y en `PlansBoardPage.tsx`. | **Alta** (los 4 tocan los mismos 5 archivos) | §9: bloques comentados por plan, orden por número, y frontera explícita con el 264 dentro de `PlansBoardPage.tsx`. |

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
- **No** se reescribe el parser de encabezados (`_ESTADO_RE`, `parse_plan_header`, `_read_header_cached`):
  se **importa**. Tampoco se corrige la docstring de `_read_header_cached` que dice "bytes" donde el
  código lee caracteres (fuera de scope; archivo compartido con el 265).

---

## 8. Orden de implementación y DoD

**Orden (estricto, por dependencia):**

1. **Medición inicial** — correr §1.1 y anotar `total` y `sin estado`.
2. **F0** — flags, las 6 patas (todo lo demás las lee).
3. **F1 + F1.5** — `resolve_estado()` + `estado_origen` + `build_board` (el núcleo; sin esto no hay KPI-1 ni KPI-3).
4. **F2** — ratchet anti-regresión + registro en las dos listas del arnés (protege lo de F1 hacia adelante).
5. **F4** — modelo de la app (consume lo de F1; sin esto la UI muestra un chip incoherente).
6. **F5** — densidad CSS (independiente de F1-F4; se puede hacer en paralelo si hay dos manos).
7. **F3 + F2.5** — migración con evidencia y transacción de 3 patas (necesita F1 para saber qué normalizar y F2 para tener baseline que podar).
8. **F6** — panel de normalización (necesita F3 y F4).
9. **F7** — cierre, huella de regresión y verificación.

**Definición de Hecho (DoD) — global, binaria:**

- [ ] Los 16 comandos de F7 salen **exit 0**, cero rojos propios (los ajenos, documentados con worktree del commit base).
- [ ] `sum(1 for p in board['plans'] if p['estado_efectivo']=='SIN_ESTADO')` ⇒ **0** (KPI-3).
- [ ] `grep -cE '^\s*(padding|margin|gap)[^:]*:\s*[^;]*(rem|px)' PlansBoardPage.module.css` ⇒ **0** (KPI-2).
- [ ] El conteo de `style={{` en `PlansBoardPage.tsx` **no aumentó** respecto de la medición inicial.
- [ ] Ningún literal hex nuevo en `PlansBoardPage.module.css` (ratchet `hexByFile` sin subir).
- [ ] **Las 6 patas de F0 hechas**, en los **5** archivos correctos: `config.py`, `services/harness_flags.py` (registry **y** `_CATEGORY_KEYS`), `services/harness_flags_help.py`, `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`.
- [ ] La flag OFF **no** declara `default=` y **no** está en el conjunto curado; las 2 ON declaran `default=True` y **sí** están.
- [ ] Las 3 aristas `requires` son de **profundidad 1** (todas a `STACKY_PLANS_BOARD_ENABLED`) y están congeladas en `_REQUIRES_MAP_FROZEN`.
- [ ] `tests/test_plan263_*.py` (3 archivos) registrados en **ambas** listas `HARNESS_TEST_FILES` (`.sh` y `.ps1`), y `test_harness_ratchet_meta.py` verde.
- [ ] Prueba negativa del ratchet ejecutada y el archivo `999_PLAN_PRUEBA_RATCHET.md` **borrado**.
- [ ] `test_regla_unica_de_estado` verde (ratchet y tablero comparten la regla, borde multibyte incluido).
- [ ] **KPI-6:** tras un apply sobre un plan aprobado en el ledger, su card sigue en `estado_efectivo == "APROBADO"` y `doc_drift is False`.
- [ ] Tras un apply, `plans_estado_baseline.json` quedó podado solo y `test_plan263_estado_guard.py` sigue verde **sin edición manual**.
- [ ] Smoke visual hecho en las **dos** densidades, con los dos conteos de cards anotados (KPI-5 ≥ 11 en compacto).
- [ ] Con `STACKY_PLANS_NORMALIZE_APPLY_ENABLED=false`, `git status --porcelain "Stacky Agents/docs"` es **idéntico** antes y después de llamar al endpoint de apply.
- [ ] Huella registrada en `docs/sistema/error_fingerprints.json`.
- [ ] El "Registro de implementación" se agrega al final de **este** documento con la salida real de los comandos, los números medidos y los desvíos encontrados.
- [ ] `git commit` del trabajo hecho **con pathspec explícito** (`git commit -- "<ruta>" ...`): el working tree tiene cambios de otras sesiones y un commit de índice compartido se los roba. **Prohibido** `git add -A`, `reset`, `amend`, `stash`, `checkout` y `--no-verify`. El `push` es manual.

---

## 9. Convivencia con los planes hermanos 260 / 264 / 265 (v2 / C18)

Los cuatro planes de esta tanda editan **los mismos 5 archivos compartidos**. El riesgo real y ya
documentado del repo: **git hace 3-way merge SIN marcar conflicto cuando dos ramas agregan la misma
línea de cierre a una estructura existente**, dejando un duplicado silencioso que ni los marcadores ni
el compilador atrapan.

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
