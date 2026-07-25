# Plan 237 — Triage de planes en el Centro de Evolución: qué falta primero, sin abrir un solo `.md`

**Estado:** IMPLEMENTADO — F0..F7 (2026-07-25)
**Implementación:** F0, F1, F2, F3, F7, F4, F5, F6 completas. Ver §11.
**Estado previo:** CRITICADO v2 — RECHAZADO(v1) → corregido — 2026-07-25
**Versión:** v1 → **v2** (juez adversarial: `StackyArchitectaUltraEficientCode`)
**Tipo:** plan de superficie + censo honesto + guardia de numeración (backend read-only + una sección nueva del Centro de Evolución)
**Depende de:** Plan 128 (tablero de planes, implementado), Plan 167 (Centro de Evolución, implementado)
**Numeración:** este plan CONSERVA el **237**. El plan hermano del mismo día pasó a **238**
(`238_PLAN_BANDEJA_DE_INCIDENCIAS_ABIERTAS_EN_TICKETS_ADO.md`). Los números **219..236** siguen
RESERVADOS por `docs/_roadmap/serie_paridad_218.json`.

---

## 0. CHANGELOG v1 → v2 (qué se rompió y qué se arregló)

El v1 fue **RECHAZADO** por 6 bloqueantes. Todos verificados corriendo comandos, no por lectura.

| # | Corrección | Resuelve |
|---|------------|----------|
| 1 | F0 ahora edita **también** `tests/test_plan128_plans_board_flag.py`: el flip a `default=True` rompe `test_flag_sin_default_explicito` (`assert spec.default is None`) y `test_config_default_off` (`assert ... is False`). El v1 afirmaba que se rompía **un solo** test (el de orden) — falso. | **C1** |
| 2 | F0 repara además `test_defaults_env_y_help`, que **YA ESTABA ROJO antes de este plan** (evidencia: `1 failed, 5 passed` — `harness_defaults.env` es un snapshot PARCIAL que no contiene la key). Se arregla el test, **no** se toca ni se regenera el `.env` generado. | **C3** |
| 3 | F4 agrega la key nueva a `_CATEGORY_KEYS` (`harness_flags.py:279`). Sin eso, `test_flag_categories_cover_registry` y `test_read_current_includes_category_and_default` quedan rojos. | **C2** |
| 4 | K3, el criterio binario de F3 y el DoD ya no exigen "**237**": el `next_free_number` real de hoy es **239** (`max` de prefijos `NN_` en `docs/` = 238). Los criterios pasan a ser **relativos y auto-verificables**. | **C4** |
| 5 | F4 fija el **punto de inserción literal** (final de `api/evolution.py`) y reescribe el test anti-escritura con centinela: `api/evolution.py` tiene `@bp.post` en `:104`, `:134`, `:171`, así que el test del v1 estaba diseñado para fallar. | **C5** |
| 6 | G6 corregido: el ratchet cuenta **hex en `*.module.css`** (`uiDebtRatchet.test.ts`, `HEX_RE` sobre `.module.css`). El v1 ordenaba "todo el color al `.module.css`" ⇒ ratchet rojo garantizado. Ahora: **cero hex también en el CSS**, solo `var(--token)`. | **C6** |
| 7 | §3.1 reescrita: la colisión con el plan **238** es REAL (comparten `config.py`, `harness_flags.py`, `test_harness_flags.py`, `run_harness_tests.sh`, `endpoints.ts`) + protocolo de merge anti-duplicado silencioso. | **C7** |
| 8 | **[ADICIÓN ARQUITECTO] F7 — Guardia de numeración anti-colisión**: universo completo de números, detección de duplicados, `claim_plan_path()` con creación **exclusiva** (mata el read-then-write de dos sesiones paralelas), guard test y huella de regresión. El v1 no prevenía la recurrencia: solo saltaba reservados, y hoy ese salto es **inerte**. | **C11**, **C16** |
| 9 | **[ADICIÓN ARQUITECTO]** F2 gana **memo por `(mtime, size)`**, lectura acotada a 4000 bytes (hoy se hace `read_text()` COMPLETO de 193 archivos) y cota dura `_MAX_PLAN_FILES`. G8 pasa de afirmación a hecho medible. | **C8** |
| 10 | F5 trae el **bloque de imports literal** (`SkeletonList`, `Toast`, `EmptyState` NO viven en `components/ui`) y grupos `<details>` reales con `COMPLETADO` colapsado. | **C9**, **C13** |
| 11 | KPIs relativos, no congelados (el v1 clavaba "192 planes"; hoy son 193). | **C10** |
| 12 | `get_board_cached` devuelve copia profunda del board (dos superficies comparten el mismo dict cacheado). | **C12** |
| 13 | Rutas de test con `Path(__file__).resolve().parents[1]` en todos lados; cita `:806-814` corregida a `:805-813`. | **C14**, **C15** |

---

## 1. Objetivo y KPI

**Objetivo.** Hoy el operador tiene **193** documentos de plan en `Stacky Agents/docs/` (contados 2026-07-25:
archivos que matchean `^[0-9]{2,3}_PLAN_.*\.md$` en el directorio raíz) y **ninguna superficie encendida por
defecto** que le diga cuáles faltan. El tablero del Plan 128 existe pero su flag nace apagada, vive en otro tab,
ordena por número descendente (el plan recién propuesto tapa al plan criticado que espera implementación) y
descarta en silencio todo lo que no sea un `NN_PLAN_*.md` del directorio raíz. Este plan lleva el inventario
**al Centro de Evolución** (la vista que el operador ya abre, flag ON de fábrica), lo **ordena por triage**
— primero lo que **no está implementado**, después lo que **no está criticado**, después lo que ya está
**completado** —, convierte el censo en **honesto** (nada se descarta sin contador y motivo) y agrega una
**guardia de numeración** que detecta y previene la colisión de números que acaba de ocurrir de verdad
(dos planes nacieron como 237 el mismo día).

**KPI / impacto esperado — todos RELATIVOS y auto-verificables (nada de números congelados que caducan
al día siguiente):**

| ID | Métrica | Hoy (medido 2026-07-25) | Meta | Cómo se verifica |
|----|---------|--------------------------|------|------------------|
| K1 | Planes visibles al operador sin tocar ninguna flag | **0** (`STACKY_PLANS_BOARD_ENABLED` default `"false"`, `config.py:1544-1546`) | **todos** los `NN_PLAN_*.md` del raíz (hoy 193; el test compara contra el conteo real, no contra 193) | `test_plan237_flag_default_on` + `test_censo_de_docs_reales_cierra_la_cuenta` |
| K2 | Clicks para responder "¿qué plan implemento ahora?" | indefinido (hay que abrir docs a mano) | **0** — el primer grupo no vacío es "Sin implementar" | `test_orden_de_buckets_es_el_contratado` |
| K3 | `next_free_number` **nunca** propone un número ocupado ni reservado | **falla**: propone `max(NN_)+1` a secas, ignora los reservados `219..236` del catálogo del 218 | el número propuesto **no** está en `reserved_numbers()` **ni** en los números con documento, y es **> max existente**. (Hoy eso da **239**; el test NO hardcodea 239) | `test_next_free_number_effective_saltea_reservados` + `test_docs_reales_proponen_un_numero_libre_de_verdad` |
| K4 | Planes descartados en silencio por el censo | **3** (`docs/_legacy/`) + 18 catalogados sin doc, sin contador | **0 silenciosos**: todos con contador y motivo en `census` | `test_censo_declara_todos_los_excluidos` |
| K5 | Superficies que muestran el mismo orden | 1 (tab Planes, apagado) | 2 (tab Planes + Centro de Evolución), mismo servicio puro | `test_plan237_plans_triage_endpoint.py` |
| K6 | **[ADICIÓN]** Números de plan duplicados detectados automáticamente | **0 detección** (la colisión 237/237 la encontró un humano) | duplicados listados en `numbering.duplicates` + guard test rojo si reaparecen | `test_docs_reales_sin_numeros_duplicados` |
| K7 | **[ADICIÓN]** Bytes leídos de disco por rebuild del board | **archivo completo** × 193 (`read_text()` en `plans_board.py:99`) usando solo 4000 chars | ≤ 4000 bytes por archivo **y** 0 bytes por archivo sin cambios (memo `mtime`+`size`) | `test_memo_no_relee_archivos_sin_cambios` |

---

## 2. Evidencia real (`archivo:línea` — VERIFICADO 2026-07-25 leyendo el código)

### 2.1 Los 4 defectos medidos

1. **El tablero nace apagado.** `backend/config.py:1544-1546` define
   `STACKY_PLANS_BOARD_ENABLED = os.getenv("STACKY_PLANS_BOARD_ENABLED", "false").strip().lower() == "true"`
   y la `FlagSpec` de `backend/services/harness_flags.py:3642-3654` **no declara `default=`**
   (comentario literal en `:3652`: *"SIN default= (queda None: opt-in…)"*). Consecuencia probada:
   `App.tsx:145` consulta `/api/plans-board/health`, recibe `flag_enabled:false` y el tab "Planes" nunca se
   pinta (`App.tsx:301`). Esto contradice la directiva vigente ("toda flag nueva default ON salvo las 4
   excepciones duras"); acá **no aplica ninguna**: es lectura de archivos locales, sin egreso, sin escritura,
   sin credenciales, sin tokens ociosos.

2. **El orden es inútil para decidir.** `backend/services/plans_board.py:304`:
   `plans.sort(key=lambda c: (-c["number"], c["filename"]))`. El plan 238 recién propuesto aparece **arriba**
   del 216, que ya está criticado y espera implementación. Para saber qué falta hay que leer 193 filas.

3. **El censo pierde datos en silencio.** `scan_plan_files` (`plans_board.py:82-115`) itera **no recursivo**
   (`docs_dir.iterdir()`, `:87`), matchea solo `^(\d{2,3})_PLAN_(.+)\.md$` (`_PLAN_FILE_RE`, `:22`) y descarta
   sin contador: los 3 `docs/_legacy/*_PLAN_*.md`, cualquier archivo > 2 MB (`_MAX_FILE_BYTES`, `:30`) y
   cualquier `OSError` (`:96-97` en el `stat`, `:100-101` en el `read_text`).

4. **`next_free_number` propone un número ocupado o reservado.** `plans_board.py:118-131` devuelve
   `max(prefijo NN_ de los archivos del raíz) + 1`, ignorando por completo `docs/_roadmap/`.
   `docs/_roadmap/serie_paridad_218.json` declara **19 subplanes** ocupando **218..236** (verificado: la lista
   `subplans[].number` es exactamente `[218..236]`). **Y la colisión ya ocurrió**: dos planes distintos
   nacieron como 237 el mismo día. Ver §2.3.

### 2.2 Lo que SÍ existe y hay que reusar (no reinventar nada)

| Pieza | Dónde (verificado) | Cómo se reusa |
|-------|--------------------|----------------|
| Parser de estado | `plans_board.py:35-49` (`normalize_estado`) + `:52-79` (`parse_plan_header`) | **Sin tocar.** Devuelve EXACTAMENTE 5 valores: `PROPUESTO / CRITICADO / IMPLEMENTADO / IMPLEMENTADO_PARCIAL / SIN_ESTADO` (verificado leyendo el cuerpo: no hay otros returns). |
| Ledger del supervisor | `plans_board.py:134-177` + `docs/_supervision/ledger.json` | **Sin tocar.** `_LEDGER_OK_VEREDICTOS = ("APROBADO", "TERMINADO-POR-SUPERVISOR")` (`:32`); ambos colapsan a `estado_efectivo == "APROBADO"` (`:277`). |
| Acción sugerida copiable | `plans_board.py:180-252` (`suggest_next_action`) | **Sin tocar** salvo el caso nuevo `SIN_DOCUMENTO` (F3). Ya trae `command` (slash de Claude Code CLI) **y** `natural_language` (fallback Codex/Copilot). |
| Cache TTL 15 s | `plans_board.py:374-392` (`get_board_cached`) | La sección nueva consume el **mismo** cache. Se corrige la copia superficial (F2). |
| Catálogo de subplanes | `docs/_roadmap/serie_paridad_218.json` | Fuente de los planes previstos sin documento y de los números reservados. |
| Patrón de sección | `frontend/src/evolution/KnowledgeSection.tsx:66-80` (`load` con `loading/hidden/error/ready`) + `:82-84` (`useEffect`) | Se copia literal para `PlansSection.tsx`. |
| Punto de montaje | `frontend/src/pages/EvolutionCenterPage.tsx:483-491` | Se inserta `<PlansSection />` **antes** de `<FitnessSection />` (`:485`). |
| `next_free_number` sin gate de flag | `backend/api/plans_board.py:32-40` (el `/health` ya lo expone SIEMPRE) | F7 lo enriquece con el bloque `numbering`. |

### 2.3 [ADICIÓN ARQUITECTO] La colisión ya pasó: evidencia y causa raíz

**Hecho:** el 2026-07-25 dos sesiones escribieron `237_PLAN_*.md` distintos. Se resolvió a mano renumerando
uno a **238**.

**Causa raíz — y por qué el fix del v1 NO alcanza:**
- `next_free_number` es un **read** puro; entre ese read y el `write` del `.md` hay una ventana en la que otra
  sesión lee el mismo valor. Saltear reservados **no cierra esa ventana**.
- Peor: hoy el salto de reservados es **inerte**. `max(NN_) = 238` ⇒ crudo `= 239`, que ya está fuera de
  `219..236`. O sea, el v1 se vendía como "el fix de la colisión" con una lógica que en el estado actual
  **no cambia ni un número**. Sigue siendo correcta como guardia futura (si se borra un doc, el crudo vuelve a
  caer en la banda reservada), pero no es el fix.
- El fix real, y **read-only-compatible**, es de tres partes: (a) el universo de números tiene que incluir
  raíz + subdirectorios + roadmaps + ledger; (b) la creación del `.md` debe ser **exclusiva** (`open(..., "x")`),
  que es atómica en el filesystem y hace que la segunda sesión falle en vez de pisar; (c) los duplicados que
  igual se cuelen deben ser **ruidosos** (banner + guard test), no descubrirse a ojo. Eso es **F7**.

---

## 3. Principios y guardarraíles (no negociables — se codifican en los tests)

- **G1 — Cero trabajo extra para el operador.** Todo default **ON**. No se pide configurar nada, no aparece un
  paso manual nuevo, no hay wizard. **Ninguna de las 4 excepciones duras aplica**: (1) no hay bypass de revisión
  humana — la sección no dispara nada; (2) no hay acción destructiva ni irreversible — es solo lectura; (3) no
  hay prerequisito no garantizado — lee archivos del propio repo y degrada a vacío si no están; (4) no reduce la
  seguridad — no expone contenido nuevo, solo el encabezado que ya expone el Plan 128.
- **G2 — Human-in-the-loop innegociable.** La sección **nunca ejecuta** un plan, ni critica, ni supervisa, ni
  commitea. Ofrece **texto copiable** que el operador pega y corre él. Cero botones que disparen agentes.
  Cero endpoints de escritura. Verificado por `test_plan237_seccion_no_expone_endpoints_de_escritura`.
  *(La única función que escribe, `claim_plan_path` de F7, NO tiene endpoint: es una utilidad importable que
  hace atómica una escritura que la skill de proponer ya hacía. No agrega autonomía ni saca al operador del lazo.)*
- **G3 — Paridad de 3 runtimes.** Nada de este plan depende del runtime: es un lector de archivos + una tabla.
  La única superficie sensible es la **acción copiable**, que trae dos variantes (`command` = slash de Claude
  Code CLI; `natural_language` = frase para Codex CLI o GitHub Copilot Pro). **F5 obliga a renderizar las dos
  siempre**, sin detección de runtime, y el test lo verifica.
- **G4 — Aditivo y backward-compatible.** Ninguna clave del contrato §4.4 del Plan 128 se renombra ni se borra.
  Solo se **agregan** claves. Las funciones existentes conservan su firma; lo nuevo va en funciones nuevas.
- **G5 — Cero pollers.** Carga on-mount + botón "Refrescar". Igual que el resto del Centro de Evolución.
- **G6 — Cero deuda visual nueva (CORREGIDO en v2).** El ratchet `src/__tests__/uiDebtRatchet.test.ts` cuenta,
  **por archivo**: hex `(/#[0-9a-fA-F]{3,8}\b/g)` en **`*.module.css`**, `style={{` en `*.tsx`, y
  `confirm|alert|prompt(` en ambos. Por lo tanto: **cero hex en `PlansSection.module.css`** (todos los colores
  por `var(--token)` existentes), **cero `style={{` en `PlansSection.tsx`**, **cero diálogos nativos**.
  *(El v1 decía "todo el color vive en el `.module.css`" — eso rompía el ratchet.)*
- **G7 — Nada se descarta en silencio.** Todo archivo que el censo saltea suma a un contador con motivo.
- **G8 — No degrada performance (ahora medible, no declarativo).** Se reusa el cache TTL de 15 s **y** se
  agrega memo por `(mtime, size)` + lectura acotada a `_HEADER_READ_CHARS` bytes + cota `_MAX_PLAN_FILES` +
  piso de 2 s para `?refresh=1`. El I/O por rebuild **baja** respecto de hoy, no sube (K7).
- **G9 — [ADICIÓN] Ningún número de plan se propone dos veces.** El universo de números es completo y los
  duplicados son ruidosos (F7).

### 3.1 Colisión de propiedad de archivos — REESCRITA (el v1 afirmaba "cero colisión": era FALSO)

**Con la serie 218 (`docs/_roadmap/serie_paridad_218.json`): cero colisión.** Ninguno de los archivos de este
plan aparece en `owns_files` de ningún subplan (recorridas las 19 entradas).

**Con el plan 238 (hermano del mismo día): COLISIÓN REAL en 5 archivos compartidos.** El 238
(`STACKY_INCIDENT_INBOX_ENABLED`) edita exactamente los mismos registros globales:

| Archivo compartido | 237 escribe | 238 escribe | Riesgo |
|---|---|---|---|
| `backend/config.py` | flip de `STACKY_PLANS_BOARD_ENABLED` (`:1544-1546`) + campo nuevo tras `:1560` | campo nuevo tras `:1523` | Anclajes distintos ⇒ git mergea sin conflicto. OK. |
| `backend/services/harness_flags.py` | `_CATEGORY_KEYS` tras `:279` + `FlagSpec` tras la del Plan 167 + `default=True` en `:3652` | `_CATEGORY_KEYS` tras `:375` + `FlagSpec` nueva | **Merge duplicado silencioso**: dos ramas agregando líneas a la misma estructura no dan conflicto. |
| `backend/services/harness_flags_help.py` | 1 entrada nueva + reescribe `on_effect` de `:1363` | 1 entrada nueva | Igual que arriba. |
| `backend/tests/test_harness_flags.py` | 2 keys en `_CURATED_DEFAULTS_ON` (`:467`) | 1 key en el mismo set | Igual que arriba. |
| `backend/scripts/run_harness_tests.sh` | 2 líneas tras `:248` | 3 líneas antes del cierre de la lista | Igual que arriba. |
| `frontend/src/api/endpoints.ts` | 2 métodos en `Evolution` (`:2769`) | namespace `IncidentInbox` nuevo | Bloques distintos. OK. |

**Protocolo obligatorio (gotcha conocido: el merge 3-way NO marca conflicto cuando dos ramas agregan la misma
línea de cierre a una estructura ya existente):** después de mergear 237 y 238, correr **siempre**:
```
& ".venv\Scripts\python.exe" -m compileall -q services config.py
& ".venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -q
```
y verificar que cada key aparezca **exactamente una vez** por estructura:
```
Select-String -Path "services\harness_flags.py" -Pattern "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED"   # esperado: 2 (categoría + FlagSpec)
Select-String -Path "tests\test_harness_flags.py" -Pattern "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED" # esperado: 1
```

> **Aviso de namespace (no es scope de este plan, pero hay que saberlo):** el plan 238 todavía nombra sus
> archivos de test `test_plan237_inbox_*.py` y su título dice "Plan 237". Este plan usa
> `test_plan237_plans_triage*.py`. **No colisionan como nombre de archivo**, pero cualquier verificación por
> `grep "plan237"` va a traer archivos de los dos planes. Quien implemente el 237 **no** debe renombrar nada
> del 238.

---

## 4. Comandos de test (usar EXACTAMENTE estos)

> **Backend** — desde `Stacky Agents/backend`, PowerShell:
> `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q`
> **SIEMPRE por archivo**, nunca la suite completa (contaminación cross-run conocida: el
> `importlib.reload(config)` de varios tests ensucia la corrida).
>
> **Frontend** — desde `Stacky Agents/frontend`:
> `npx vitest run <ruta/al/archivo.test.ts>` y `npx tsc --noEmit`.
> **SIEMPRE por archivo** (contaminación de orden conocida en vitest).

---

## 5. Fases

---

### F0 — Encender el inventario: `STACKY_PLANS_BOARD_ENABLED` pasa a default ON

**Objetivo (1 frase):** que el operador vea sus planes sin prender nada a mano.
**Valor:** desbloquea K1 (0 → todos los planes visibles).

**Archivos a editar (rutas exactas — son 5, no 4: el v1 se olvidaba del quinto y por eso quedaba rojo):**
1. `Stacky Agents/backend/config.py`
2. `Stacky Agents/backend/services/harness_flags.py`
3. `Stacky Agents/backend/services/harness_flags_help.py`
4. `Stacky Agents/backend/tests/test_harness_flags.py`
5. `Stacky Agents/backend/tests/test_plan128_plans_board_flag.py`  ← **NUEVO en v2 (C1 + C3)**

**Cambio 1 — `backend/config.py:1543-1546`:**
```diff
-    # ── Plan 128 — Tablero de evolución de planes (default OFF, editable por UI) ──
+    # ── Plan 128 — Tablero de evolución de planes (default ON desde el Plan 237:
+    #    solo lectura de docs/ locales, sin egreso ni escritura) ──
     STACKY_PLANS_BOARD_ENABLED: bool = os.getenv(
-        "STACKY_PLANS_BOARD_ENABLED", "false"
+        "STACKY_PLANS_BOARD_ENABLED", "true"
     ).strip().lower() == "true"
```

**Cambio 2 — `backend/services/harness_flags.py:3651-3653`** (dentro de la `FlagSpec` cuya `key` es
`STACKY_PLANS_BOARD_ENABLED`, que ocupa `:3642-3654`):
```diff
         group="global",
-        # SIN default= (queda None: opt-in, no curada en _CURATED_DEFAULTS_ON).
-        # SIN requires= (no tiene master). SIN env_only= (queda UI-editable).
+        default=True,   # Plan 237: promovido a ON (lectura local, sin egreso). Curado en _CURATED_DEFAULTS_ON.
+        # SIN requires= (no tiene master). SIN env_only= (queda UI-editable).
     ),
```
> **No hace falta tocar `_CATEGORY_KEYS` para ESTA key**: ya está clasificada en `"observabilidad_notif"`
> (verificado: `test_categoria_observabilidad` de `test_plan128_plans_board_flag.py:45-46` pasa hoy).
> La key **nueva** de F4 sí la necesita.

**Cambio 3 — `backend/tests/test_harness_flags.py`**, set `_CURATED_DEFAULTS_ON` (empieza en `:467`):
agregar al final del set, antes de la llave de cierre, **exactamente** estas dos líneas
(**una sola key**: la segunda se cura en F4, cuando su `FlagSpec` ya exista):
```python
    # ── Plan 237 — inventario de planes visible de fábrica ──
    "STACKY_PLANS_BOARD_ENABLED",
```
> **Por qué es obligatorio:** `test_default_known_only_for_curated` (mismo archivo, `:816-826`) exige
> `default_is_known(spec) ⇔ key ∈ _CURATED_DEFAULTS_ON`. Poner `default=True` sin curar deja ese test rojo.
> **Y por qué en DOS TIEMPOS:** `test_declared_default_true_set` (`:805-813`) hace `by_key[key]` y levanta
> **KeyError** si se cura una key que todavía no existe en `FLAG_REGISTRY`. Como
> `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED` recién nace en F4, en F0 va **solo** la key de arriba.

**Cambio 4 — `backend/services/harness_flags_help.py:1363`**, entrada `"STACKY_PLANS_BOARD_ENABLED"`
(el bloque `PlainHelp` ocupa `:1361-1366`): reemplazar el campo `on_effect` por (≤ 240 chars, empieza con
`"Si "` — lo exige `test_plain_help_on_off_start_with_si`):
```python
        on_effect="Si la activás (viene así de fábrica): aparece el tab 'Planes' y la sección 'Planes' del Centro de Evolución, con el próximo número libre y una acción copiable por plan. No ejecuta nada por sí solo.",
```

**Cambio 5 — `backend/tests/test_plan128_plans_board_flag.py` (NUEVO en v2, tres ediciones).**
Medido con `pytest tests/test_plan128_plans_board_flag.py -q` ⇒ hoy `1 failed, 5 passed`.
Tras el flip, sin estas ediciones, quedaría `3 failed`.

*(a)* `:32-34` — `test_flag_sin_default_explicito` afirma lo contrario de lo que este plan hace:
```diff
-def test_flag_sin_default_explicito():
+def test_flag_default_on_desde_plan237():
     spec = _spec()
-    assert spec.default is None
+    # Plan 237: promovida a default ON (lectura local, sin egreso). Curada en _CURATED_DEFAULTS_ON.
+    assert spec.default is True
```
*(b)* `:37-42` — `test_config_default_off`:
```diff
-def test_config_default_off(monkeypatch):
+def test_config_default_on(monkeypatch):
     monkeypatch.delenv(_KEY, raising=False)
     import importlib
     import config
     importlib.reload(config)
-    assert config.config.STACKY_PLANS_BOARD_ENABLED is False
+    # Plan 237: sin variable de entorno, el tablero viene ENCENDIDO.
+    assert config.config.STACKY_PLANS_BOARD_ENABLED is True
```
*(c)* `:49-55` — `test_defaults_env_y_help`. **Este test YA ESTABA ROJO antes de este plan** (evidencia:
`AssertionError: assert 'STACKY_PLANS_BOARD_ENABLED=false' in '...'` — el archivo generado
`backend/harness_defaults.env` es un snapshot **parcial** de 67 líneas que **no contiene** esta key).
Se repara **sin tocar el `.env`** (está generado por `deployment/export_harness_defaults.py`; editarlo a mano
está prohibido y regenerarlo entero arrastra drift de otras features):
```diff
 def test_defaults_env_y_help():
     backend_root = Path(__file__).parent.parent
     defaults_path = backend_root / "harness_defaults.env"
     assert defaults_path.exists()
     content = defaults_path.read_text(encoding="utf-8")
-    assert "STACKY_PLANS_BOARD_ENABLED=false" in content
+    # harness_defaults.env es un snapshot PARCIAL generado por
+    # deployment/export_harness_defaults.py: esta key puede no estar. Lo que NO puede
+    # pasar (Plan 237) es que esté con el valor viejo "false".
+    assert "STACKY_PLANS_BOARD_ENABLED=false" not in content
     assert _KEY in PLAIN_HELP
```

**Tests PRIMERO (TDD).** Archivo nuevo: `Stacky Agents/backend/tests/test_plan237_plans_triage.py`
(el mismo archivo crece en F1/F2/F3/F7; en F0 lleva estos 2 casos):
```python
"""tests/test_plan237_plans_triage.py — Plan 237: triage, censo y numeración."""
import json
import pathlib
import re


def test_plan237_flag_default_on():
    """La FlagSpec del tablero declara default=True."""
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_PLANS_BOARD_ENABLED")
    assert spec.default is True


def test_plan237_config_default_on_sin_env():
    """config.py declara "true" como default de la variable de entorno.

    Se verifica sobre el SOURCE y NO con importlib.reload(config): recargar el
    módulo config dentro de una corrida contamina otros tests del arnés (gotcha
    conocido). El source es la única fuente del default y basta para el gate.
    """
    src = pathlib.Path(__file__).resolve().parents[1] / "config.py"
    texto = src.read_text(encoding="utf-8")
    m = re.search(r'os\.getenv\(\s*"STACKY_PLANS_BOARD_ENABLED",\s*"(\w+)"', texto, re.S)
    assert m is not None, "no se encontró el getenv de STACKY_PLANS_BOARD_ENABLED en config.py"
    assert m.group(1) == "true"
```

**Comandos de verificación (los 4 tienen que quedar verdes):**
```
& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_harness_flags_help.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_plan128_plans_board_flag.py -q
```
**Criterio de aceptación BINARIO:** los 4 comandos terminan con `0 failed`.
*(El cuarto es el que el v1 omitía y el que hoy está en rojo: F0 lo deja verde por primera vez.)*

**Flag que la protege:** `STACKY_PLANS_BOARD_ENABLED`, **default ON**. Ninguna de las 4 excepciones duras
aplica (lectura local, sin egreso, sin escritura, sin credenciales, sin tokens ociosos).
**Impacto por runtime:** ninguno — configuración de backend, idéntica en Codex CLI, Claude Code CLI y
GitHub Copilot Pro. **Fallback:** si `docs/` no existe (deploy congelado), `docs_dir_found:false` y la UI
muestra el estado vacío que ya existe. **Trabajo del operador: ninguno.**

---

### F1 — Buckets de triage: el orden que responde "¿qué falta?"

**Objetivo (1 frase):** clasificar cada plan en un bucket y ordenar por bucket antes que por número.
**Valor:** K2 — el primer grupo de la lista es, siempre, lo que falta implementar.

**Archivos a editar:**
1. `Stacky Agents/backend/services/plans_board.py`
2. `Stacky Agents/backend/tests/test_plan128_plans_board_parser.py` (un assert; ver abajo)

**Contrato de buckets (LITERAL — el orden ES el contrato).** Agregar después de `_LEDGER_OK_VEREDICTOS` (`:32`):
```python
# ── Plan 237 — Triage: el ORDEN de esta tupla ES el orden de presentación. ──
# Responde, de arriba a abajo: qué NO está implementado, qué NO está criticado,
# qué ni siquiera tiene documento, qué falta cerrar, y qué ya está completo.
TRIAGE_BUCKETS: tuple[tuple[str, str], ...] = (
    ("SIN_IMPLEMENTAR", "Sin implementar"),      # pasó el juez (o quedó a medias): toca construir
    ("SIN_CRITICAR",    "Sin criticar"),         # escrito pero sin juez adversarial
    ("SIN_DOCUMENTO",   "Sin documento"),        # catalogado en un roadmap, todavía sin .md (F3)
    ("SIN_SUPERVISAR",  "Sin supervisar"),       # construido, falta el cierre del supervisor
    ("COMPLETADO",      "Completado"),           # ledger APROBADO y sin drift del doc
)
_TRIAGE_RANK: dict[str, int] = {key: i for i, (key, _label) in enumerate(TRIAGE_BUCKETS)}

# estado_efectivo -> bucket. COBERTURA COMPLETA: normalize_estado (:35-49) devuelve
# exactamente PROPUESTO/CRITICADO/IMPLEMENTADO/IMPLEMENTADO_PARCIAL/SIN_ESTADO, y
# build_board (:277) puede sustituirlo por "APROBADO". No hay un sexto valor posible.
# Un estado desconocido cae en SIN_CRITICAR (se prefiere pedir revisión humana antes
# que esconder un plan al fondo).
_ESTADO_A_BUCKET: dict[str, str] = {
    "CRITICADO":            "SIN_IMPLEMENTAR",
    "IMPLEMENTADO_PARCIAL": "SIN_IMPLEMENTAR",
    "PROPUESTO":            "SIN_CRITICAR",
    "SIN_ESTADO":           "SIN_CRITICAR",
    "IMPLEMENTADO":         "SIN_SUPERVISAR",
    "APROBADO":             "COMPLETADO",
}


def triage_bucket(estado_efectivo: str) -> str:
    """Bucket de triage de un plan CON documento. Nunca lanza."""
    return _ESTADO_A_BUCKET.get(estado_efectivo or "", "SIN_CRITICAR")


def triage_rank(bucket: str) -> int:
    """Posición del bucket. Un bucket desconocido va al final (nunca oculto)."""
    return _TRIAGE_RANK.get(bucket, len(TRIAGE_BUCKETS))
```

**Cambio en `build_board`** (`:255-316`). Dentro del `for c in cards_raw:` (`:270`), después de calcular
`estado_efectivo` (`:277`), agregar `bucket = triage_bucket(estado_efectivo)` y **agregar la clave al card**
(aditivo, nada se borra) justo debajo de la línea `"estado_efectivo": estado_efectivo,` (`:290`):
```diff
             "estado_efectivo": estado_efectivo,
+            "triage_bucket": bucket,
```
Reemplazar el `sort` de `:304`:
```diff
-    plans.sort(key=lambda c: (-c["number"], c["filename"]))
+    # Plan 237: primero el triage, y DENTRO de cada bucket el número descendente
+    # (lo más nuevo primero), con el filename como desempate estable.
+    # `filename` puede ser None en las cards SIN_DOCUMENTO (F3) -> se normaliza a "".
+    plans.sort(key=lambda c: (triage_rank(c["triage_bucket"]), -c["number"], c["filename"] or ""))
```
Después de `totals["total"] = len(plans)` (`:308`) agregar el resumen por bucket:
```diff
+    triage_totals = {key: 0 for key, _ in TRIAGE_BUCKETS}
+    for card in plans:
+        triage_totals[card["triage_bucket"]] = triage_totals.get(card["triage_bucket"], 0) + 1
```
y en el `return` (`:310-316`) agregar dos claves:
```diff
         "totals": totals,
+        "triage_order": [key for key, _ in TRIAGE_BUCKETS],
+        "triage_totals": triage_totals,
         "plans": plans,
```

**Tests PRIMERO.** En `test_plan237_plans_triage.py` agregar:
```python
def test_orden_de_buckets_es_el_contratado():
    from services.plans_board import TRIAGE_BUCKETS
    assert [k for k, _ in TRIAGE_BUCKETS] == [
        "SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO", "SIN_SUPERVISAR", "COMPLETADO",
    ]


def test_mapeo_estado_a_bucket_completo():
    from services.plans_board import triage_bucket
    assert triage_bucket("CRITICADO") == "SIN_IMPLEMENTAR"
    assert triage_bucket("IMPLEMENTADO_PARCIAL") == "SIN_IMPLEMENTAR"
    assert triage_bucket("PROPUESTO") == "SIN_CRITICAR"
    assert triage_bucket("SIN_ESTADO") == "SIN_CRITICAR"
    assert triage_bucket("IMPLEMENTADO") == "SIN_SUPERVISAR"
    assert triage_bucket("APROBADO") == "COMPLETADO"
    assert triage_bucket("MARCIANO") == "SIN_CRITICAR"   # desconocido -> pide revisión
    assert triage_bucket("") == "SIN_CRITICAR"


def test_cobertura_total_de_normalize_estado():
    """Ningún valor que normalize_estado pueda producir queda sin bucket explícito."""
    from services.plans_board import _ESTADO_A_BUCKET
    posibles = {"PROPUESTO", "CRITICADO", "IMPLEMENTADO", "IMPLEMENTADO_PARCIAL",
                "SIN_ESTADO", "APROBADO"}
    assert posibles <= set(_ESTADO_A_BUCKET)


def test_build_board_ordena_por_bucket_y_luego_por_numero(tmp_path):
    """Un plan CRITICADO viejo va ARRIBA de un PROPUESTO nuevo."""
    from services.plans_board import build_board
    (tmp_path / "10_PLAN_VIEJO_CRITICADO.md").write_text(
        "# Viejo\n\n**Estado:** CRITICADO v2 APROBADO 2026-01-01\n", encoding="utf-8")
    (tmp_path / "90_PLAN_NUEVO_PROPUESTO.md").write_text(
        "# Nuevo\n\n**Estado:** PROPUESTO v1 2026-07-25\n", encoding="utf-8")
    (tmp_path / "50_PLAN_MEDIO_IMPLEMENTADO.md").write_text(
        "# Medio\n\n**Estado:** IMPLEMENTADO 2026-05-05\n", encoding="utf-8")
    board = build_board(tmp_path, unpushed_paths=None)
    assert [p["number"] for p in board["plans"]] == [10, 90, 50]
    assert board["triage_order"][0] == "SIN_IMPLEMENTAR"
    assert board["triage_totals"]["SIN_IMPLEMENTAR"] == 1


def test_desempate_dentro_del_bucket_es_numero_descendente(tmp_path):
    from services.plans_board import build_board
    for n in ("11", "22", "33"):
        (tmp_path / f"{n}_PLAN_X{n}.md").write_text(
            f"# X{n}\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    board = build_board(tmp_path, unpushed_paths=None)
    assert [p["number"] for p in board["plans"]] == [33, 22, 11]


def test_claves_legacy_del_plan128_siguen_presentes(tmp_path):
    """G4: aditivo. Ninguna clave del contrato del Plan 128 desaparece."""
    from services.plans_board import build_board
    (tmp_path / "07_PLAN_Z.md").write_text("# Z\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    card = build_board(tmp_path, unpushed_paths=None)["plans"][0]
    for k in ("number", "number_str", "slug", "filename", "path_rel", "title", "estado",
              "estado_raw", "estado_efectivo", "veredicto", "version", "fecha",
              "duplicate", "ledger", "unpushed", "suggested_action"):
        assert k in card, f"clave legacy perdida: {k}"
    assert card["triage_bucket"] == "SIN_CRITICAR"
```

**Cambio OBLIGATORIO en el test del Plan 128 (medido: es el único de orden que se pone en rojo).**
`Stacky Agents/backend/tests/test_plan128_plans_board_parser.py:253` — `test_build_board_orden_y_totales`
arma `10_PLAN_A` (`PROPUESTO`), `30_PLAN_B` (`CRITICADO v1`), `20_PLAN_C` (`IMPLEMENTADO`) y asserta
`numbers == [30, 20, 10]` (`:262`). Con el triage: 30→`SIN_IMPLEMENTAR` (rank 0), 10→`SIN_CRITICAR` (rank 1),
20→`SIN_SUPERVISAR` (rank 3):
```diff
-    assert numbers == [30, 20, 10]
+    # Plan 237: el orden es por bucket de triage, no por número.
+    # 30=CRITICADO -> SIN_IMPLEMENTAR; 10=PROPUESTO -> SIN_CRITICAR; 20=IMPLEMENTADO -> SIN_SUPERVISAR.
+    assert numbers == [30, 10, 20]
```
Ningún otro test del Plan 128 asume orden (verificado sobre los 4 archivos `test_plan128_*`).

**Comandos:**
```
& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_plan128_plans_board_parser.py -q
```
**Criterio BINARIO:** ambos `0 failed`.
**Flag:** `STACKY_PLANS_BOARD_ENABLED` (default ON, F0). No hace falta flag propia: el orden es una mejora del
mismo payload y la flag maestra ya lo apaga entero.
**Impacto por runtime:** ninguno (lógica pura de Python). **Fallback:** N/A. **Trabajo del operador: ninguno.**

---

### F2 — Censo honesto + escáner acotado y memoizado

**Objetivo (1 frase):** que el total declare de qué universo salió y qué dejó afuera y por qué, **y** que leer
193 archivos cueste menos que hoy, no más.
**Valor:** K4 + K7.

**Archivo a editar:** `Stacky Agents/backend/services/plans_board.py`

**Cambio A — cota dura (junto a `_MAX_FILE_BYTES`, `:30`):**
```python
_MAX_PLAN_FILES = 500          # Plan 237: cota de I/O. Más allá de esto se cuenta y no se parsea.
```

**Cambio B — [ADICIÓN ARQUITECTO] memo por (mtime, size).** Hoy `scan_plan_files:99` hace
`entry.read_text()` — el archivo **entero** — para usar solo los primeros `_HEADER_READ_CHARS` (4000) chars.
Con 193 planes eso son megabytes por rebuild. Se corrige con lectura acotada + memo:
```python
# Plan 237 — memo de encabezados: clave = (str(path), mtime_ns, size) -> dict header.
# Un archivo que no cambió NO se vuelve a leer ni a parsear. Cota: se limpia si supera
# 4 * _MAX_PLAN_FILES entradas (evita crecer sin techo en procesos largos).
_HEADER_MEMO: dict[tuple[str, int, int], dict] = {}


def _read_header_cached(entry: Path, size: int) -> dict | None:
    """Encabezado parseado de `entry`, leyendo COMO MUCHO _HEADER_READ_CHARS bytes.

    Devuelve None si el archivo no se pudo leer (el llamador lo cuenta como ilegible).
    """
    try:
        key = (str(entry), entry.stat().st_mtime_ns, size)
    except OSError:
        return None
    hit = _HEADER_MEMO.get(key)
    if hit is not None:
        return dict(hit)
    try:
        with entry.open("r", encoding="utf-8", errors="replace") as fh:
            texto = fh.read(_HEADER_READ_CHARS)
    except OSError:
        return None
    header = parse_plan_header(texto)
    if not header["title"]:
        header["title"] = entry.stem
    if len(_HEADER_MEMO) > 4 * _MAX_PLAN_FILES:
        _HEADER_MEMO.clear()
    _HEADER_MEMO[key] = dict(header)
    return header
```

**Cambio C — censo.** Función nueva **sin tocar la firma de `scan_plan_files`** (que sigue devolviendo
`list[dict]` para no romper los tests del Plan 128); la vieja delega en la nueva:
```python
def scan_plan_files_with_census(docs_dir: Path) -> tuple[list[dict], dict]:
    """Igual que scan_plan_files, pero devolviendo (planes, censo).

    census = {
      "files_seen": int,            # entradas de archivo en el directorio raíz
      "plans_parsed": int,          # NN_PLAN_*.md efectivamente parseados
      "skipped_not_a_plan": int,    # NN_ que no son _PLAN_, y todo lo demás
      "skipped_oversize": int,      # > _MAX_FILE_BYTES
      "skipped_unreadable": int,    # OSError al leer o al stat
      "skipped_over_cap": int,      # planes más allá de _MAX_PLAN_FILES (cota de I/O)
      "skipped_subdirs": int,       # planes NN_PLAN_*.md en subdirectorios (p.ej. _legacy/)
      "subdir_examples": list[str], # hasta 5 rutas relativas, para que el operador sepa cuáles
    }
    NUNCA lanza: cualquier problema suma a un contador.
    Invariante testeada: plans_parsed + skipped_not_a_plan + skipped_oversize
                       + skipped_unreadable + skipped_over_cap == files_seen
    """
```
Pseudocódigo LITERAL (entradas, salidas, casos borde). El cuerpo del `results.append(...)` es el mismo de
`scan_plan_files:105-114` (claves `number`, `number_str`, `slug`, `filename`, `path`, `**header`):
```
census = {los 6 contadores en 0, subdir_examples: []}
si no docs_dir.exists(): devolver ([], census)
results = []
para entry en sorted(docs_dir.iterdir(), key=nombre):
    si no entry.is_file():
        # subdirectorio: contar los planes que quedan afuera, SIN parsearlos
        try: hijos = sorted(entry.glob("*_PLAN_*.md"))
        except OSError: hijos = []
        census["skipped_subdirs"] += len(hijos)
        para h en hijos[: 5 - len(census["subdir_examples"])]:
            census["subdir_examples"].append(f"{entry.name}/{h.name}")
        continuar
    census["files_seen"] += 1
    m = _PLAN_FILE_RE.match(entry.name)
    si no m: census["skipped_not_a_plan"] += 1; continuar
    try: size = entry.stat().st_size
    except OSError: census["skipped_unreadable"] += 1; continuar
    si size > _MAX_FILE_BYTES: census["skipped_oversize"] += 1; continuar
    si len(results) >= _MAX_PLAN_FILES: census["skipped_over_cap"] += 1; continuar
    header = _read_header_cached(entry, size)
    si header es None: census["skipped_unreadable"] += 1; continuar
    results.append({"number": int(m.group(1)), "number_str": m.group(1),
                    "slug": m.group(2), "filename": entry.name, "path": entry, **header})
    census["plans_parsed"] += 1
devolver (results, census)


def scan_plan_files(docs_dir: Path) -> list[dict]:      # firma INTACTA (G4)
    return scan_plan_files_with_census(docs_dir)[0]
```
En `build_board`, reemplazar `cards_raw = scan_plan_files(docs_dir)` (`:259`) por
`cards_raw, census = scan_plan_files_with_census(docs_dir)` y agregar `"census": census,` al `return`.

**Cambio D — copia profunda del board cacheado (C12).** `get_board_cached` (`:378-392`) devuelve `dict(board)`,
una copia **superficial**: `census`, `triage_totals`, `totals` y `plans` quedan compartidos entre las dos
superficies, y una mutación de un consumidor envenena el cache. Reemplazar los dos `return dict(board)` por
`return copy.deepcopy(board)` (agregando `import copy` arriba). Además, piso anti-abuso del `refresh`:
```python
_BOARD_MIN_REFRESH_SEC = 2.0   # Plan 237: ?refresh=1 no puede forzar rebuilds en ráfaga.
```
y en `get_board_cached`, si `refresh` es True pero el cache tiene menos de `_BOARD_MIN_REFRESH_SEC`, se
devuelve el cache igual (el botón "Refrescar" no puede martillar el disco).

**Tests PRIMERO.** En `test_plan237_plans_triage.py`:
```python
def test_censo_declara_todos_los_excluidos(tmp_path):
    from services.plans_board import build_board
    (tmp_path / "01_PLAN_OK.md").write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    (tmp_path / "02_CHECKLIST_NO_ES_PLAN.md").write_text("# No\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    legacy = tmp_path / "_legacy"; legacy.mkdir()
    (legacy / "03_PLAN_ARCHIVADO.md").write_text("# Arch\n", encoding="utf-8")
    c = build_board(tmp_path, unpushed_paths=None)["census"]
    assert c["files_seen"] == 3
    assert c["plans_parsed"] == 1
    assert c["skipped_not_a_plan"] == 2
    assert c["skipped_subdirs"] == 1
    assert c["subdir_examples"] == ["_legacy/03_PLAN_ARCHIVADO.md"]
    assert c["skipped_oversize"] == 0 and c["skipped_unreadable"] == 0
    assert c["skipped_over_cap"] == 0


def test_scan_plan_files_conserva_su_firma(tmp_path):
    """G4: el Plan 128 sigue llamando scan_plan_files(dir) -> list."""
    from services.plans_board import scan_plan_files
    (tmp_path / "01_PLAN_OK.md").write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    out = scan_plan_files(tmp_path)
    assert isinstance(out, list) and len(out) == 1 and out[0]["number"] == 1


def test_memo_no_relee_archivos_sin_cambios(tmp_path, monkeypatch):
    """K7: el segundo escaneo del MISMO archivo sin cambios no vuelve a abrir el disco."""
    from services import plans_board as pb
    pb._HEADER_MEMO.clear()
    f = tmp_path / "01_PLAN_OK.md"
    f.write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    aperturas = {"n": 0}
    real_open = pb.Path.open

    def contando(self, *a, **k):
        if self.name.endswith("_PLAN_OK.md"):
            aperturas["n"] += 1
        return real_open(self, *a, **k)

    monkeypatch.setattr(pb.Path, "open", contando)
    pb.scan_plan_files(tmp_path)
    pb.scan_plan_files(tmp_path)
    assert aperturas["n"] == 1, "el memo debe evitar la segunda lectura"


def test_memo_reparsea_cuando_el_archivo_cambia(tmp_path):
    from services import plans_board as pb
    pb._HEADER_MEMO.clear()
    f = tmp_path / "01_PLAN_OK.md"
    f.write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    assert pb.scan_plan_files(tmp_path)[0]["estado"] == "PROPUESTO"
    f.write_text("# Ok\n\n**Estado:** CRITICADO v2\n\n<!-- relleno -->\n", encoding="utf-8")
    assert pb.scan_plan_files(tmp_path)[0]["estado"] == "CRITICADO"


def test_cota_de_archivos_se_declara(tmp_path):
    from services import plans_board as pb
    monkey = pb._MAX_PLAN_FILES
    try:
        pb._MAX_PLAN_FILES = 2
        for n in ("01", "02", "03", "04"):
            (tmp_path / f"{n}_PLAN_X.md").write_text("# X\n", encoding="utf-8")
        c = pb.build_board(tmp_path, unpushed_paths=None)["census"]
        assert c["plans_parsed"] == 2 and c["skipped_over_cap"] == 2
        assert c["plans_parsed"] + c["skipped_over_cap"] == c["files_seen"]
    finally:
        pb._MAX_PLAN_FILES = monkey


def test_censo_de_docs_reales_cierra_la_cuenta():
    """Sobre el docs/ real: la invariante del censo se cumple y hay al menos 3 archivados."""
    from services.plans_board import docs_dir_default, build_board
    c = build_board(docs_dir_default(), unpushed_paths=None)["census"]
    assert (c["plans_parsed"] + c["skipped_not_a_plan"] + c["skipped_oversize"]
            + c["skipped_unreadable"] + c["skipped_over_cap"]) == c["files_seen"]
    assert c["skipped_subdirs"] >= 3    # docs/_legacy/ tiene 3 planes archivados


def test_board_cacheado_no_comparte_estructuras_mutables():
    """C12: mutar el board devuelto NO envenena el cache."""
    from services.plans_board import get_board_cached
    a = get_board_cached()
    a["census"]["files_seen"] = -999
    b = get_board_cached()
    assert b["census"]["files_seen"] != -999
```

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q`
**Criterio BINARIO:** `0 failed`, y además
`& ".venv\Scripts\python.exe" -m pytest tests\test_plan128_plans_board_parser.py tests\test_plan128_plans_board_endpoints.py -q` → `0 failed`.
**Flag:** `STACKY_PLANS_BOARD_ENABLED` (default ON). **Impacto por runtime:** ninguno.
**Trabajo del operador: ninguno.**

---

### F3 — Planes previstos sin documento + `next_free_number` que respeta reservas

**Objetivo (1 frase):** mostrar los planes que un roadmap ya comprometió pero que todavía no tienen `.md`, y
dejar de proponer números reservados.
**Valor:** K3 y el bucket `SIN_DOCUMENTO` con los 18 subplanes pendientes de la serie 218.

**Archivos a editar:** `Stacky Agents/backend/services/plans_board.py`, `Stacky Agents/backend/api/plans_board.py`

**Cambio.** Lector **genérico** de roadmaps (no hardcodea `serie_paridad_218.json`: cualquier `*.json` de
`docs/_roadmap/` con una lista `subplans` de objetos con `number` entra solo):
```python
_ROADMAP_DIRNAME = "_roadmap"


def load_roadmap_entries(docs_dir: Path) -> list[dict]:
    """Lee docs/_roadmap/*.json y devuelve las entradas de plan catalogadas.

    Formato aceptado (el del Plan 218 F7): dict con "subplans": [ {..}, .. ],
    donde cada entrada tiene al menos "number" (int). "title", "slug",
    "priority" y "milestone" son opcionales.
    Devuelve [] ante CUALQUIER problema (no existe, no es JSON, es otra forma).
    Cada entrada devuelta: {"number", "title", "slug", "priority", "milestone", "source"}.
    """
```
Pseudocódigo LITERAL:
```
root = docs_dir / _ROADMAP_DIRNAME
si no root.exists() o no root.is_dir(): devolver []
out, vistos = [], set()
para f en sorted(root.glob("*.json")):
    try: data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError): continuar          # nunca lanza
    si no isinstance(data, dict): continuar
    subplans = data.get("subplans")
    si no isinstance(subplans, list): continuar
    para e en subplans:
        si no isinstance(e, dict): continuar
        n = e.get("number")
        si no isinstance(n, int) o isinstance(n, bool): continuar
        si n en vistos: continuar                     # primer roadmap gana
        vistos.add(n)
        out.append({"number": n,
                    "title": str(e.get("title") or f"Plan {n}"),
                    "slug": str(e.get("slug") or ""),
                    "priority": e.get("priority"),
                    "milestone": e.get("milestone"),
                    "source": f.name})
devolver sorted(out, key=lambda e: e["number"])


def reserved_numbers(docs_dir: Path) -> set[int]:
    """Números comprometidos por algún roadmap (tengan o no documento)."""
    return {e["number"] for e in load_roadmap_entries(docs_dir)}


def next_free_number_effective(docs_dir: Path) -> int:
    """next_free_number, pero saltando los números reservados por roadmaps.
    Sin docs/_roadmap/ devuelve EXACTAMENTE lo mismo que next_free_number."""
    n = next_free_number(docs_dir)
    reservados = reserved_numbers(docs_dir)
    while n in reservados:
        n += 1
    return n


def build_planned_cards(docs_dir: Path, numeros_con_doc: set[int]) -> list[dict]:
    """Cards del bucket SIN_DOCUMENTO: catalogados en un roadmap y sin .md.
    Mismas claves que un card normal (para que la UI no discrimine)."""
```
Pseudocódigo de `build_planned_cards`:
```
cards = []
para e en load_roadmap_entries(docs_dir):
    si e["number"] en numeros_con_doc: continuar
    ns = f"{e['number']:02d}"
    cards.append({
      "number": e["number"], "number_str": ns, "slug": e["slug"],
      "filename": None, "path_rel": f"docs/_roadmap/{e['source']}",
      "title": e["title"], "estado": "SIN_DOCUMENTO", "estado_raw": None,
      "estado_efectivo": "SIN_DOCUMENTO", "triage_bucket": "SIN_DOCUMENTO",
      "veredicto": None, "version": None, "fecha": None, "duplicate": False,
      "ledger": None, "unpushed": None,
      "priority": e["priority"], "milestone": e["milestone"],
      "suggested_action": {
        "kind": "proponer",
        "label": "Escribir el plan",
        "command": f"/proponer-plan-stacky {e['title']}",
        "natural_language": (f"El plan {ns} está comprometido en el roadmap "
                             f"({e['source']}) pero todavía no tiene documento: "
                             f"pedile al agente proponer el plan {ns} — {e['title']}."),
      },
    })
devolver cards
```
En `build_board`: después del `for` que arma `plans` (o sea después de `:302`) y **antes** del `sort` (`:304`):
```python
    numeros_con_doc = {c["number"] for c in cards_raw}
    planned = build_planned_cards(docs_dir, numeros_con_doc)
    for card in planned:
        plans.append(card)
        totals["SIN_DOCUMENTO"] = totals.get("SIN_DOCUMENTO", 0) + 1
```
y en el `return`, cambiar `"next_free_number": next_free_number(docs_dir),` (`:313`) por
`"next_free_number": next_free_number_effective(docs_dir),` agregando además
`"next_free_number_raw": next_free_number(docs_dir),` y
`"reserved_count": len(reserved_numbers(docs_dir)),`.

En `Stacky Agents/backend/api/plans_board.py:39`, cambiar
`next_n = plans_board.next_free_number(docs_dir) if docs_dir.exists() else None` por
`next_n = plans_board.next_free_number_effective(docs_dir) if docs_dir.exists() else None`.

> **Ojo (caso borde real):** el número 218 **sí** tiene documento, así que **no** aparece como
> `SIN_DOCUMENTO`; sí aparecen los 18 subplanes 219..236. `numeros_con_doc` se calcula sobre `cards_raw`
> (planes parseados), no sobre `plans`, para no auto-excluir las cards que se están agregando.
> **Y `totals["total"]` ya se calculó en `:308` sobre `len(plans)`**, o sea que las cards `SIN_DOCUMENTO`
> quedan incluidas en el total: es lo correcto (el total es "todo lo que la sección muestra").

**Tests PRIMERO.** En `test_plan237_plans_triage.py`:
```python
def test_next_free_number_effective_saltea_reservados(tmp_path):
    from services.plans_board import next_free_number, next_free_number_effective
    (tmp_path / "18_PLAN_ORQ.md").write_text("# Orq\n\n**Estado:** IMPLEMENTADO\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps(
        {"subplans": [{"number": 19, "title": "A"}, {"number": 20, "title": "B"}]}), encoding="utf-8")
    assert next_free_number(tmp_path) == 19            # el crudo colisiona
    assert next_free_number_effective(tmp_path) == 21  # el efectivo saltea 19 y 20


def test_sin_roadmap_effective_es_igual_al_crudo(tmp_path):
    from services.plans_board import next_free_number, next_free_number_effective
    (tmp_path / "05_PLAN_A.md").write_text("# A\n", encoding="utf-8")
    assert next_free_number_effective(tmp_path) == next_free_number(tmp_path) == 6


def test_roadmap_corrupto_no_rompe(tmp_path):
    from services.plans_board import load_roadmap_entries, build_board
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "roto.json").write_text("{ esto no es json", encoding="utf-8")
    (rm / "otra_forma.json").write_text('{"cosas": [1,2,3]}', encoding="utf-8")
    (rm / "lista_pelada.json").write_text('[1,2,3]', encoding="utf-8")
    assert load_roadmap_entries(tmp_path) == []
    assert build_board(tmp_path, unpushed_paths=None)["plans"] == []


def test_planes_catalogados_sin_doc_entran_como_SIN_DOCUMENTO(tmp_path):
    from services.plans_board import build_board
    (tmp_path / "18_PLAN_ORQ.md").write_text("# Orq\n\n**Estado:** IMPLEMENTADO\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps({"subplans": [
        {"number": 18, "title": "Ya tiene doc"},
        {"number": 19, "title": "Onboarding GitLab", "priority": "P0", "milestone": "M1"},
    ]}), encoding="utf-8")
    board = build_board(tmp_path, unpushed_paths=None)
    sd = [p for p in board["plans"] if p["triage_bucket"] == "SIN_DOCUMENTO"]
    assert [p["number"] for p in sd] == [19]
    assert sd[0]["suggested_action"]["kind"] == "proponer"
    assert sd[0]["suggested_action"]["command"].startswith("/proponer-plan-stacky ")
    assert sd[0]["suggested_action"]["natural_language"]
    assert board["triage_totals"]["SIN_DOCUMENTO"] == 1


def test_docs_reales_proponen_un_numero_libre_de_verdad():
    """Sobre el docs/ real. RELATIVO: no hardcodea 237 ni 239 (caducan al día siguiente)."""
    from services.plans_board import (docs_dir_default, build_board, reserved_numbers)
    docs = docs_dir_default()
    board = build_board(docs, unpushed_paths=None)
    n = board["next_free_number"]
    con_doc = {p["number"] for p in board["plans"] if p["filename"]}
    assert n not in reserved_numbers(docs), "propuso un número RESERVADO por un roadmap"
    assert n not in con_doc, "propuso un número que YA tiene documento"
    assert n > max(con_doc), "el número propuesto debe ser mayor que todos los existentes"


def test_docs_reales_listan_los_subplanes_218_sin_doc():
    from services.plans_board import docs_dir_default, build_board
    board = build_board(docs_dir_default(), unpushed_paths=None)
    sd = {p["number"] for p in board["plans"] if p["triage_bucket"] == "SIN_DOCUMENTO"}
    assert 219 in sd and 236 in sd, "faltan subplanes reservados de la serie 218"
    assert 218 not in sd, "el 218 tiene documento: no puede figurar como SIN_DOCUMENTO"
```

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q`
**+ no-regresión obligatoria** (el catálogo del 218 tiene su propio guardián):
`& ".venv\Scripts\python.exe" -m pytest tests\test_plan218_serie_integridad.py -q`

**Criterio BINARIO (CORREGIDO en v2 — el v1 exigía imprimir `237`, imposible: hoy el valor real es `239`):**
ambos comandos `0 failed`, y
```
& ".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'.'); from services.plans_board import docs_dir_default as d, next_free_number_effective as f, reserved_numbers as r; n=f(d()); print(n); assert n not in r(d())"
```
imprime un número **> 238** (hoy: **239**) y no lanza `AssertionError`.
**Flag:** `STACKY_PLANS_BOARD_ENABLED` (default ON). **Impacto por runtime:** ninguno.
**Trabajo del operador: ninguno.**

---

### F4 — Endpoint propio del Centro de Evolución (no depende del tab "Planes")

**Objetivo (1 frase):** exponer el board triado bajo `/api/evolution/plans`, gateado por la flag del Centro de
Evolución, para que la sección funcione aunque el operador apague el tab "Planes".
**Valor:** K5 — dos superficies, un solo servicio puro, sin acoplar flags entre features.

**Archivos:**
- editar `Stacky Agents/backend/api/evolution.py`
- editar `Stacky Agents/backend/config.py`
- editar `Stacky Agents/backend/services/harness_flags.py` (**dos** ediciones: `_CATEGORY_KEYS` + `FlagSpec`)
- editar `Stacky Agents/backend/services/harness_flags_help.py`
- editar `Stacky Agents/backend/tests/test_harness_flags.py` (curar la key nueva)
- editar `Stacky Agents/backend/scripts/run_harness_tests.sh` (ratchet)
- crear `Stacky Agents/backend/tests/test_plan237_plans_triage_endpoint.py`

**Flag nueva:** `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED`, **default ON**, `group="global"`,
`requires="STACKY_EVOLUTION_CENTER_ENABLED"` (profundidad 1: el master es una flag raíz, no encadena).

**Edición 1 (NUEVA en v2 — C2) — `harness_flags.py`, `_CATEGORY_KEYS`.** El dict empieza en `:120`.
Insertar **inmediatamente después** de la línea `:279`
(`"STACKY_EVOLUTION_CENTER_ENABLED",              # Plan 167 — Centro de Evolución (panel)`),
**dentro de la misma tupla**:
```python
        "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED",        # Plan 237 — triage de planes en el Centro de Evolución
```
> **Por qué es obligatorio:** `test_flag_categories_cover_registry` (`test_harness_flags.py:745`) exige
> biyección completa registry ↔ `_CATEGORY_KEYS`, y `test_read_current_includes_category_and_default`
> (`:789-802`) exige que cada dict de `read_current()` tenga una `category` válida. Una `FlagSpec` sin entrada
> en `_CATEGORY_KEYS` pone **los dos** en rojo. El comentario de `harness_flags.py:386` lo dice literal.

**Edición 2 — `harness_flags.py`, `FLAG_REGISTRY`.** Inmediatamente después de la `FlagSpec` de
`STACKY_EVOLUTION_CYCLE_ENABLED`:
```python
    # ── Plan 237 — Triage de planes dentro del Centro de Evolución ──
    FlagSpec(
        key="STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED",
        type="bool", default=True,
        label="Planes en el Centro de Evolución",
        description="Sección de solo lectura que lista TODOS los planes de docs/ agrupados por triage: primero los que faltan implementar, después los que faltan criticar, después los completados.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
```

**Curado obligatorio (segundo tiempo del cambio 3 de F0).** En `tests/test_harness_flags.py`, dentro de
`_CURATED_DEFAULTS_ON` (`:467`), debajo de la línea que agregó F0:
```diff
     # ── Plan 237 — inventario de planes visible de fábrica ──
     "STACKY_PLANS_BOARD_ENABLED",
+    "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED",
```

**`backend/config.py`** — junto al bloque del Plan 167, **inmediatamente después** del campo
`STACKY_EVOLUTION_CYCLE_ENABLED` (`:1557-1560`):
```python
    # ── Plan 237 — Sección "Planes" del Centro de Evolución (solo lectura) ──
    STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED: bool = os.getenv(
        "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

**`backend/services/harness_flags_help.py`** — entrada nueva en `PLAIN_HELP` (obligatoria:
`test_plain_help_covers_all_registry_keys` la exige; `on_effect`/`off_effect` **deben** empezar con `"Si "`,
`what` ≤ 200 chars, `on_effect`/`off_effect` ≤ 240, `example` ≤ 300):
```python
    # ── Plan 237 — Planes en el Centro de Evolución ──────────────────────────
    "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED": PlainHelp(
        what="Lista todos tus planes dentro del Centro de Evolución, agrupados por lo que falta: sin implementar, sin criticar, sin documento, sin supervisar y completados.",
        on_effect="Si la activás (viene así de fábrica): al abrir Evolución ves arriba de todo qué planes faltan construir, con el próximo número libre y una acción copiable. No ejecuta nada.",
        off_effect="Si la apagás: la sección desaparece del Centro de Evolución y /api/evolution/plans devuelve 404. El tab 'Planes' sigue funcionando aparte.",
        example="Abrís Evolución y en dos segundos sabés que el 216 está criticado esperando implementación y que 18 subplanes del roadmap ni siquiera tienen documento.",
    ),
```

**`backend/api/evolution.py` — PUNTO DE INSERCIÓN LITERAL (CORREGIDO en v2 — C5).**
El archivo tiene rutas de escritura en `@bp.post("/proposals")` (`:104`), `@bp.post("/proposals/<pid>/transition")`
(`:134`) y `@bp.post("/cycle/run")` (`:171`). Por eso **todo el bloque nuevo va AL FINAL DEL ARCHIVO**,
después de la última ruta existente, precedido por el centinela EXACTO de la primera línea (el test lo busca
por texto):
```python


# ── Plan 237 — Triage de planes (bloque appendeado al FINAL del archivo) ──
# Solo lectura. Debajo de este centinela NO puede haber ninguna ruta de escritura.
def _plans_triage_enabled() -> bool:
    return _enabled() and bool(getattr(_cfg, "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED", False))


@bp.get("/plans/health")
def plans_health():
    # Siempre 200 (patrón del /health de este mismo módulo, :46): la UI lo usa para gatear la sección.
    return jsonify({"ok": True, "flag_enabled": _plans_triage_enabled()})


@bp.get("/plans")
def plans_triage():
    if not _plans_triage_enabled():
        return _disabled_resp()
    from services import plans_board  # lazy (patrón del módulo)

    refresh = request.args.get("refresh", "").strip() == "1"
    board = plans_board.get_board_cached(refresh=refresh)
    return jsonify(board)
```
> `request`, `jsonify` y `_cfg` YA están importados en `api/evolution.py:9-11`. El blueprint tiene
> `url_prefix="/evolution"` (`:13`) y la app lo monta bajo `/api`, así que la ruta final es
> `/api/evolution/plans`. **No agregar imports nuevos.**
> **Por qué reusa `get_board_cached` y no arma nada propio:** el cache TTL de 15 s ya existe
> (`plans_board.py:374-392`); dos superficies pegándole al mismo cache no agregan I/O (G8).

**Tests PRIMERO.** Archivo nuevo `Stacky Agents/backend/tests/test_plan237_plans_triage_endpoint.py`.
Las fixtures se copian del patrón real de `tests/test_plan128_plans_board_endpoints.py:7-29` (setean
`cfg.config.<KEY>` **antes** de `create_app()` y restauran al final):
```python
"""tests/test_plan237_plans_triage_endpoint.py — Plan 237 F4: /api/evolution/plans."""
import pathlib
import re

import pytest


@pytest.fixture
def client():
    import config as cfg
    prev_center = getattr(cfg.config, "STACKY_EVOLUTION_CENTER_ENABLED", True)
    prev_triage = getattr(cfg.config, "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED", True)
    cfg.config.STACKY_EVOLUTION_CENTER_ENABLED = True
    cfg.config.STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    cfg.config.STACKY_EVOLUTION_CENTER_ENABLED = prev_center
    cfg.config.STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED = prev_triage


def test_flag_de_la_seccion_default_on():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED")
    assert spec.default is True
    assert spec.requires == "STACKY_EVOLUTION_CENTER_ENABLED"


def test_flag_de_la_seccion_esta_categorizada():
    """C2: sin entrada en _CATEGORY_KEYS, dos meta-tests del arnés se ponen rojos."""
    from services.harness_flags import _CATEGORY_KEYS
    todas = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    assert "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED" in todas


def test_plans_health_siempre_200_con_flag_on(client):
    r = client.get("/api/evolution/plans/health")
    assert r.status_code == 200
    assert r.get_json()["flag_enabled"] is True


def test_plans_devuelve_board_con_triage(client):
    r = client.get("/api/evolution/plans")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["triage_order"] == ["SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO",
                                    "SIN_SUPERVISAR", "COMPLETADO"]
    assert "triage_totals" in body and "census" in body and "numbering" in body
    assert all("triage_bucket" in p for p in body["plans"])


def test_plans_404_con_su_flag_off(client):
    from config import config as cfg
    cfg.STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED = False
    try:
        assert client.get("/api/evolution/plans").status_code == 404
        assert client.get("/api/evolution/plans/health").get_json()["flag_enabled"] is False
    finally:
        cfg.STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED = True


def test_plans_404_con_la_flag_maestra_off(client):
    from config import config as cfg
    cfg.STACKY_EVOLUTION_CENTER_ENABLED = False
    try:
        assert client.get("/api/evolution/plans").status_code == 404
    finally:
        cfg.STACKY_EVOLUTION_CENTER_ENABLED = True


def test_plans_no_depende_del_flag_del_tab_planes(client):
    """La sección de Evolución vive aunque el tab 'Planes' esté apagado."""
    from config import config as cfg
    prev = cfg.STACKY_PLANS_BOARD_ENABLED
    cfg.STACKY_PLANS_BOARD_ENABLED = False
    try:
        assert client.get("/api/evolution/plans").status_code == 200
    finally:
        cfg.STACKY_PLANS_BOARD_ENABLED = prev


def test_plan237_seccion_no_expone_endpoints_de_escritura():
    """G2: debajo del centinela del Plan 237 no puede haber NINGUNA ruta de escritura."""
    src_path = pathlib.Path(__file__).resolve().parents[1] / "api" / "evolution.py"
    src = src_path.read_text(encoding="utf-8")
    centinela = "# ── Plan 237 — Triage de planes (bloque appendeado al FINAL del archivo) ──"
    assert centinela in src, "el bloque del Plan 237 debe ir al final de api/evolution.py"
    bloque = src[src.index(centinela):]
    assert not re.search(r"@bp\.(post|put|delete|patch)", bloque), (
        "el bloque del Plan 237 quedó ANTES de rutas de escritura: moverlo al final del archivo"
    )
```
> **Nota para quien implemente:** se parchea la **instancia** `config.config`; leer/parchear el **módulo**
> `config` pelado devuelve el default y no cambia nada (`api/evolution.py:11` usa
> `from config import config as _cfg`, o sea la instancia).

**Registro obligatorio en el ratchet.** Editar `Stacky Agents/backend/scripts/run_harness_tests.sh` y agregar,
inmediatamente **después** de la línea `:248` (`tests/test_plan128_plans_board_endpoints.py`), estas tres líneas:
```
  # — Plan 237 · Triage de planes en el Centro de Evolución —
  tests/test_plan237_plans_triage.py
  tests/test_plan237_plans_triage_endpoint.py
```
> Sin esto, `test_harness_ratchet_meta.py` queda **rojo** ("Tests no clasificados").
> **Ojo merge (§3.1):** el plan 238 agrega sus líneas al final de la misma lista. Después de mergear, verificar
> que no haya duplicados: `Select-String -Path "scripts\run_harness_tests.sh" -Pattern "test_plan237"`.

**Comandos:**
```
& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage_endpoint.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_harness_ratchet_meta.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_flag_wiring.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_evolution_endpoints.py -q
```
**Criterio BINARIO:** los 5 con `0 failed`.
**Flag:** `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED`, **default ON** (ninguna excepción dura aplica: solo lectura
local, sin egreso, sin escritura, sin credenciales, sin costo de tokens).
**Impacto por runtime:** ninguno — endpoint Flask de lectura, idéntico bajo Codex CLI, Claude Code CLI y
GitHub Copilot Pro. **Fallback:** con `docs/` ausente devuelve `docs_dir_found:false` + `plans: []`.
**Trabajo del operador: ninguno.**

---

### F5 — La sección en el Centro de Evolución (lo que el operador pidió)

**Objetivo (1 frase):** que al abrir el tab "Evolución" lo primero que se vea sean los planes agrupados
por triage, con lo que falta implementar arriba de todo.
**Valor:** K1 + K2. Es el entregable visible del plan.

**Archivos:**
- crear `Stacky Agents/frontend/src/evolution/plansTriageModel.ts`
- crear `Stacky Agents/frontend/src/evolution/plansTriageModel.test.ts`
- crear `Stacky Agents/frontend/src/evolution/PlansSection.tsx`
- crear `Stacky Agents/frontend/src/evolution/PlansSection.module.css`
- editar `Stacky Agents/frontend/src/api/endpoints.ts`
- editar `Stacky Agents/frontend/src/pages/EvolutionCenterPage.tsx`

**`endpoints.ts`** — dentro del objeto `export const Evolution = {` (`:2769`), agregar dos métodos
(mismo estilo `fetch` crudo que el resto del objeto; **no** usar el wrapper `api.get`, que lanza en non-2xx):
```ts
  plansHealth: () => fetch("/api/evolution/plans/health").then((r) => r.json()),
  plans: (refresh = false) =>
    fetch(`/api/evolution/plans${refresh ? "?refresh=1" : ""}`).then((r) =>
      r.json().then((d) => ({ ok: r.ok, status: r.status, data: d })),
    ),
```

**`plansTriageModel.ts`** — lógica pura, sin React, sin fetch:
```ts
// Plan 237 — Triage de planes: tipos + lógica pura (sin React).
export type TriageBucket =
  | "SIN_IMPLEMENTAR" | "SIN_CRITICAR" | "SIN_DOCUMENTO" | "SIN_SUPERVISAR" | "COMPLETADO";

export const BUCKET_ORDER: TriageBucket[] = [
  "SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO", "SIN_SUPERVISAR", "COMPLETADO",
];

// Buckets que arrancan ABIERTOS. COMPLETADO arranca cerrado: es el más numeroso
// y el menos accionable (mata el ruido sin esconder nada).
export const BUCKETS_ABIERTOS_POR_DEFECTO: TriageBucket[] = [
  "SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO", "SIN_SUPERVISAR",
];

// `tone` es un NOMBRE DE CLASE del .module.css. Cero colores literales acá (G6).
export const BUCKET_META: Record<TriageBucket, { label: string; hint: string; tone: string }> = {
  SIN_IMPLEMENTAR: { label: "Sin implementar", hint: "Ya pasaron el juez (o quedaron a medias): toca construirlos.", tone: "toneUrgent" },
  SIN_CRITICAR:    { label: "Sin criticar",    hint: "Escritos, pero todavía sin juez adversarial.",               tone: "toneWarn" },
  SIN_DOCUMENTO:   { label: "Sin documento",   hint: "Comprometidos en un roadmap; falta escribir el .md.",        tone: "toneInfo" },
  SIN_SUPERVISAR:  { label: "Sin supervisar",  hint: "Construidos; falta el cierre del supervisor.",               tone: "tonePending" },
  COMPLETADO:      { label: "Completado",      hint: "Implementados, supervisados y aprobados.",                   tone: "toneDone" },
};

export interface PlanTriageCard {
  number: number; number_str: string; title: string; slug: string;
  filename: string | null; estado: string; estado_efectivo: string;
  triage_bucket: TriageBucket; version: string | null; fecha: string | null;
  duplicate: boolean; unpushed: boolean | null;
  ledger: { veredicto: string; fecha: string | null; doc_drift: boolean | null } | null;
  suggested_action: { kind: string; label: string; command: string | null; natural_language: string };
}

export interface NumberingDto {
  max_number: number; next_free_number: number; next_free_number_raw: number;
  reserved_count: number; duplicates: { number: number; filenames: string[] }[];
}

export interface PlansTriageDto {
  ok: boolean; docs_dir_found: boolean; git_available: boolean;
  next_free_number: number; next_free_number_raw?: number; reserved_count?: number;
  triage_order: string[]; triage_totals: Record<string, number>;
  totals: Record<string, number>;
  census: { files_seen: number; plans_parsed: number; skipped_not_a_plan: number;
            skipped_oversize: number; skipped_unreadable: number; skipped_over_cap: number;
            skipped_subdirs: number; subdir_examples: string[] };
  numbering?: NumberingDto;
  plans: PlanTriageCard[];
}

export function bucketRank(b: string): number {
  const i = BUCKET_ORDER.indexOf(b as TriageBucket);
  return i === -1 ? BUCKET_ORDER.length : i;   // desconocido al final, nunca oculto
}

/** Agrupa respetando BUCKET_ORDER. Devuelve TODOS los grupos, incluso vacíos. */
export function groupByBucket(plans: PlanTriageCard[]): { bucket: TriageBucket; cards: PlanTriageCard[] }[] {
  return BUCKET_ORDER.map((bucket) => ({
    bucket,
    cards: plans.filter((p) => p.triage_bucket === bucket)
                .slice()
                .sort((a, b) => b.number - a.number),
  }));
}

/** Filtro de texto: número, título o slug. Vacío = todo. */
export function filterByText(plans: PlanTriageCard[], texto: string): PlanTriageCard[] {
  const q = texto.trim().toLowerCase();
  if (!q) return plans;
  return plans.filter((p) => `${p.number_str} ${p.title} ${p.slug}`.toLowerCase().includes(q));
}

/** Frase del censo. Devuelve null si no se excluyó nada (nada que declarar). */
export function censusSummary(c: PlansTriageDto["census"]): string | null {
  const fuera = c.skipped_subdirs + c.skipped_oversize + c.skipped_unreadable + c.skipped_over_cap;
  if (fuera === 0) return null;
  const partes: string[] = [];
  if (c.skipped_subdirs) partes.push(`${c.skipped_subdirs} archivados en subcarpetas`);
  if (c.skipped_oversize) partes.push(`${c.skipped_oversize} demasiado grandes`);
  if (c.skipped_unreadable) partes.push(`${c.skipped_unreadable} ilegibles`);
  if (c.skipped_over_cap) partes.push(`${c.skipped_over_cap} más allá del tope de lectura`);
  return `${c.plans_parsed} planes leídos · fuera del listado: ${partes.join(", ")}.`;
}

/** [ADICIÓN] Aviso de colisión de numeración. null si no hay duplicados. */
export function numberingAlert(n: NumberingDto | undefined): string | null {
  if (!n || !n.duplicates.length) return null;
  const lista = n.duplicates
    .map((d) => `${d.number} (${d.filenames.join(", ")})`)
    .join(" · ");
  return `Números de plan duplicados: ${lista}. Renumerá uno antes de seguir.`;
}
```

**`PlansSection.tsx`** — bloque de imports **LITERAL** (v2: el v1 nombraba componentes sin decir de dónde
salen; `SkeletonList`, `Toast` y `EmptyState` **no** viven en `components/ui`):
```ts
import { useCallback, useEffect, useMemo, useState } from "react";
import { Evolution } from "../api/endpoints";
import { Button, Card, SectionHeader, Input } from "../components/ui";
import SkeletonList from "../components/SkeletonList";
import EmptyState from "../components/EmptyState";
import Toast, { type ToastState } from "../components/Toast";
import {
  BUCKET_ORDER, BUCKET_META, BUCKETS_ABIERTOS_POR_DEFECTO,
  groupByBucket, filterByText, censusSummary, numberingAlert,
  type PlansTriageDto, type PlanTriageCard,
} from "./plansTriageModel";
import styles from "./PlansSection.module.css";
```
Estructura (copiando el patrón de `KnowledgeSection.tsx:66-84`):
```
estado: "loading" | "hidden" | "error" | "ready"
load():
  h = await Evolution.plansHealth()
  si !h.flag_enabled -> setStatus("hidden"); return        // con la flag OFF NO renderiza nada
  r = await Evolution.plans()
  si !r.ok -> setStatus("error"); setErrorMsg(...)
  si no -> setData(r.data as PlansTriageDto); setStatus("ready")
useEffect(() => { void load() }, [load])                   // G5: on-mount, CERO pollers

render (status==="ready"):
  <SectionHeader title="Planes" actions={<Button variant="ghost" size="sm" onClick={refrescar}>Refrescar</Button>} />
  <Card>  fila de resumen:
     "Próximo Nº libre: {next_free_number}"  (+ si next_free_number_raw !== next_free_number:
        texto "…{reserved_count} números reservados por el roadmap")
     un chip por bucket: {BUCKET_META[b].label} {triage_totals[b]}  -> className={styles[BUCKET_META[b].tone]}
     si numberingAlert(numbering) !== null -> <p className={styles.alerta} role="status">{numberingAlert(numbering)}</p>
     si censusSummary(census) !== null -> <p className={styles.census}>{censusSummary(census)}</p>
  <Input> filtro de texto (value=texto, onChange=setTexto)
  para cada grupo de groupByBucket(filterByText(plans, texto)):
     si cards.length === 0 -> saltear el grupo (no ensuciar)
     <details open={BUCKETS_ABIERTOS_POR_DEFECTO.includes(bucket)} className={styles.grupo}>
       <summary className={styles[BUCKET_META[bucket].tone]}>{label} ({cards.length})</summary>
       <p className={styles.hint}>{hint}</p>
       <table>: Nº | Título | Estado | Supervisión | Push | Acción sugerida
          Nº: {number_str} + si duplicate, badge "DUP" (className={styles.badgeDup})
          Título: {title} + subtítulo con version/fecha
          Supervisión: ledger===null ? "—" : ledger.doc_drift===true ? "drift" : `OK ${ledger.veredicto}`
          Push: unpushed===null ? "—" : unpushed ? "pendiente" : "ok"
          Acción: {suggested_action.label} + DOS botones de copiar (G3):
             "Copiar comando"  -> suggested_action.command ?? suggested_action.natural_language
             "Copiar en texto" -> suggested_action.natural_language
          (copiar = navigator.clipboard.writeText dentro de try/catch; si falla, Toast de error)
     </details>
render (status==="hidden") -> null
render (status==="loading") -> <SkeletonList />
render (status==="error")   -> <EmptyState variant="generic" title="No se pudieron leer los planes" message={errorMsg} />
```

**Restricciones DURAS de los archivos nuevos (las verifica el ratchet `uiDebtRatchet.test.ts`, G6):**
- **`PlansSection.module.css`: CERO literales hexadecimales.** El ratchet cuenta `/#[0-9a-fA-F]{3,8}\b/g`
  **en los `*.module.css`**. Todos los colores por `var(--…)` de los tokens que ya existen (mirar
  `src/evolution/KnowledgeSection.module.css` y usar las mismas variables).
- **`PlansSection.tsx`: cero `style={{`** (ratchet sobre `*.tsx`).
- **cero `confirm(` / `alert(` / `prompt(`** en ambos archivos.
- todo texto en español, sin emojis en los nombres de clase.

**`EvolutionCenterPage.tsx`** — dos ediciones:
```diff
 import KnowledgeSection from "../evolution/KnowledgeSection";
+import PlansSection from "../evolution/PlansSection"; // Plan 237
```
```diff
+          {/* Plan 237 — sección "Planes" (no renderiza con su flag OFF) */}
+          <PlansSection />
+
           {/* Plan 168 — sección Fitness (no renderiza con la flag del arnés OFF) */}
           <FitnessSection />
```
> Va **antes** de `<FitnessSection />` (`:485`) porque es la respuesta a "¿qué hago ahora?", que es lo que el
> operador busca al entrar.

**Tests PRIMERO.** `Stacky Agents/frontend/src/evolution/plansTriageModel.test.ts`:
```ts
describe("plansTriageModel", () => {
  it("BUCKET_ORDER es el contrato: sin implementar primero, completado último", () => {
    expect(BUCKET_ORDER).toEqual(["SIN_IMPLEMENTAR","SIN_CRITICAR","SIN_DOCUMENTO","SIN_SUPERVISAR","COMPLETADO"]);
  });
  it("COMPLETADO es el único bucket cerrado por defecto", () => {
    expect(BUCKETS_ABIERTOS_POR_DEFECTO).not.toContain("COMPLETADO");
    expect(BUCKETS_ABIERTOS_POR_DEFECTO).toHaveLength(4);
  });
  it("BUCKET_META cubre todos los buckets y ninguno trae color literal", () => {
    for (const b of BUCKET_ORDER) {
      expect(BUCKET_META[b].label.length).toBeGreaterThan(0);
      expect(BUCKET_META[b].tone).not.toMatch(/#[0-9a-fA-F]{3}/);
    }
  });
  it("groupByBucket devuelve los 5 grupos en orden, aun vacíos", () => { /* 5 grupos, keys en orden */ });
  it("groupByBucket ordena por número descendente dentro del grupo", () => { /* [90,50,10] */ });
  it("bucketRank manda lo desconocido al final", () => {
    expect(bucketRank("MARCIANO")).toBe(BUCKET_ORDER.length);
    expect(bucketRank("SIN_IMPLEMENTAR")).toBe(0);
  });
  it("filterByText matchea número, título y slug, y respeta el vacío", () => { /* 3 casos + vacío */ });
  it("censusSummary devuelve null cuando no se excluyó nada", () => { /* ceros -> null */ });
  it("censusSummary nombra cada motivo de exclusión", () => { /* subcarpetas + grandes + ilegibles + tope */ });
  it("numberingAlert es null sin duplicados y nombra los archivos con duplicados", () => {
    expect(numberingAlert(undefined)).toBeNull();
    expect(numberingAlert({ max_number: 238, next_free_number: 239, next_free_number_raw: 239,
                            reserved_count: 19, duplicates: [] })).toBeNull();
    const s = numberingAlert({ max_number: 238, next_free_number: 239, next_free_number_raw: 239,
      reserved_count: 19, duplicates: [{ number: 237, filenames: ["237_PLAN_A.md", "237_PLAN_B.md"] }] });
    expect(s).toContain("237");
    expect(s).toContain("237_PLAN_B.md");
  });
});
```

**Comandos:**
```
npx vitest run src/evolution/plansTriageModel.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx tsc --noEmit
```
**Criterio BINARIO:** los 3 verdes, y el ratchet pasa **sin regenerar baseline** (`PlansSection.tsx` y
`PlansSection.module.css` aportan **0** a los tres contadores).
**Flag:** `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED` (default ON). Con la flag OFF el componente devuelve `null`
y el Centro de Evolución queda **exactamente** como hoy.
**Impacto por runtime:**
- *Claude Code CLI*: "Copiar comando" copia el slash listo (`/implementar-plan-stacky 216`).
- *Codex CLI*: no hay slash commands ⇒ el operador usa "Copiar en texto". **Los dos botones se renderizan
  siempre**, así que no hay detección de runtime ni configuración.
- *GitHub Copilot Pro*: idéntico a Codex — la frase natural se pega en el chat.
**Fallback declarado:** si `suggested_action.command` es `null` (casos "ok" y "revisar" del Plan 128), el botón
"Copiar comando" copia la frase natural — nunca copia vacío.
**Trabajo del operador: ninguno.**

---

### F6 — El tab "Planes" hereda el mismo orden (coherencia entre las dos superficies)

**Objetivo (1 frase):** que el tab "Planes" del Plan 128 muestre el mismo triage, sin dos verdades distintas.
**Valor:** K5 — una sola definición de "qué falta", en dos lugares.

**Archivos:**
- editar `Stacky Agents/frontend/src/plansBoard/model.ts`
- editar `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx`
- editar `Stacky Agents/frontend/src/plansBoard/model.test.ts`

**Cambios (mínimos — el backend ya devuelve el orden correcto, así que la tabla lo hereda gratis):**
1. En `model.ts`, extender `PlanCardDto` con `triage_bucket: string;` y `BoardDto` con
   `triage_order?: string[]; triage_totals?: Record<string, number>;` (opcionales, para no romper si un deploy
   viejo responde sin ellas).
2. Agregar un filtro nuevo a `BoardFilters`: `bucket: string | "TODOS";`, y en `filterPlans` (`:70-82`), antes
   del `return true` final:
   ```ts
   if (f.bucket !== "TODOS" && card.triage_bucket !== f.bucket) return false;
   ```
3. En `PlansBoardPage.tsx`: un `<select>` nuevo "Etapa" con las 5 opciones + "TODOS" (estado
   `const [bucket, setBucket] = useState<string>("TODOS")`, incluido en el objeto `filters` de `:116` y en las
   dependencias del `useMemo` de `:117`), y una columna nueva **"Etapa"** que muestra `card.triage_bucket`.
   **No** se toca el orden en el cliente: viene del backend.

**Tests PRIMERO.** En `frontend/src/plansBoard/model.test.ts` agregar:
```ts
it("filtra por etapa de triage", () => {
  const plans = [mk({ number: 1, triage_bucket: "SIN_IMPLEMENTAR" }),
                 mk({ number: 2, triage_bucket: "COMPLETADO" })];
  const base = { texto: "", estado: "TODOS", soloPendientesPush: false, soloSinSupervisar: false } as const;
  expect(filterPlans(plans, { ...base, bucket: "SIN_IMPLEMENTAR" }).map(p => p.number)).toEqual([1]);
  expect(filterPlans(plans, { ...base, bucket: "TODOS" }).length).toBe(2);
});
```

**Comandos:**
```
npx vitest run src/plansBoard/model.test.ts
npx tsc --noEmit
npx vitest run src/__tests__/uiDebtRatchet.test.ts
```
**Criterio BINARIO:** los 3 verdes.
**Flag:** `STACKY_PLANS_BOARD_ENABLED` (default ON desde F0). **Impacto por runtime:** ninguno.
**Trabajo del operador: ninguno.**

---

### F7 — [ADICIÓN ARQUITECTO] Guardia de numeración anti-colisión

**Por qué existe.** El 2026-07-25 dos planes nacieron como **237**. El v1 se vendía como el fix y no lo era
(§2.3): saltear reservados no cierra la ventana read-then-write, y hoy ese salto es **inerte**. Esta fase ataca
la causa raíz con tres piezas, sin romper ningún riel (sigue sin haber endpoints de escritura, sin autonomía
proactiva y sin trabajo del operador).

**Archivos:**
- editar `Stacky Agents/backend/services/plans_board.py`
- editar `Stacky Agents/backend/api/plans_board.py`
- editar `Stacky Agents/docs/sistema/error_fingerprints.json`
- (tests en `tests/test_plan237_plans_triage.py`, ya registrado en el ratchet en F4)

**Pieza 1 — universo COMPLETO de números.** Hoy `next_free_number` (`:118-131`) solo mira archivos del
directorio raíz. Un número puede estar comprometido en cuatro lugares:
```python
def all_claimed_numbers(docs_dir: Path) -> dict[str, set[int]]:
    """Números comprometidos, por fuente. NUNCA lanza.

    - "root":    prefijo NN_ de archivos del directorio raíz (planes, checklists, incidentes)
    - "subdirs": prefijo NN_ de archivos de subdirectorios de PRIMER nivel (_legacy/, etc.)
    - "roadmap": reserved_numbers(docs_dir)
    - "ledger":  claves numéricas de docs/_supervision/ledger.json (load_ledger)
    """
```
Pseudocódigo:
```
fuentes = {"root": set(), "subdirs": set(), "roadmap": set(), "ledger": set()}
si no docs_dir.exists(): devolver fuentes
para entry en docs_dir.iterdir():
    si entry.is_file():
        m = _SEQ_PREFIX_RE.match(entry.name);  si m: fuentes["root"].add(int(m.group(1)))
    si no:
        try: hijos = list(entry.iterdir())
        except OSError: hijos = []
        para h en hijos:
            si h.is_file():
                m = _SEQ_PREFIX_RE.match(h.name);  si m: fuentes["subdirs"].add(int(m.group(1)))
fuentes["roadmap"] = reserved_numbers(docs_dir)
para k en load_ledger(docs_dir):        # las claves del ledger son "NN" o "NN_slug"
    m = re.match(r"^(\d{2,3})", str(k))
    si m: fuentes["ledger"].add(int(m.group(1)))
devolver fuentes


def next_free_number_effective(docs_dir: Path) -> int:   # F3, AMPLIADA en F7
    """Primer número > max(TODAS las fuentes) que no esté comprometido en ninguna.
    Sin docs/_roadmap/ ni subdirectorios devuelve lo mismo que next_free_number."""
    fuentes = all_claimed_numbers(docs_dir)
    tomados = set().union(*fuentes.values()) or {0}
    n = max(tomados) + 1
    while n in tomados:
        n += 1
    return n
```
> **Compatibilidad:** `test_sin_roadmap_effective_es_igual_al_crudo` (F3) sigue verde porque, sin roadmap ni
> subdirectorios ni ledger, `max(root)+1` es exactamente `next_free_number`.

**Pieza 2 — duplicados ruidosos.**
```python
def plan_number_duplicates(docs_dir: Path) -> list[dict]:
    """[{"number": int, "filenames": [str, ...]}] para todo NN con >1 documento en el raíz.
    Ordenado por number. Lista vacía = todo sano."""
```
y el bloque nuevo del board, agregado al `return` de `build_board`:
```python
        "numbering": {
            "max_number": max(todos_los_tomados, default=0),
            "next_free_number": next_free_number_effective(docs_dir),
            "next_free_number_raw": next_free_number(docs_dir),
            "reserved_count": len(reserved_numbers(docs_dir)),
            "duplicates": plan_number_duplicates(docs_dir),
        },
```
En `Stacky Agents/backend/api/plans_board.py`, el `/health` (`:32-40`) ya expone `next_free_number` **sin gate
de flag**. Agregar ahí también `"duplicates": plans_board.plan_number_duplicates(docs_dir) if docs_dir.exists() else []`,
para que el aviso llegue **aunque el tablero esté apagado**.

**Pieza 3 — la escritura del `.md` deja de ser una carrera.**
```python
def claim_plan_path(docs_dir: Path, number: int, filename: str) -> Path:
    """Crea el archivo del plan de forma ATÓMICA y devuelve su ruta.

    Usa creación EXCLUSIVA (open(..., "x")): si otra sesión ganó la carrera entre el
    cálculo del número y la escritura, esto levanta FileExistsError en vez de pisar.
    NO tiene endpoint HTTP: es una utilidad importable por la skill que ya escribía el
    archivo. No agrega autonomía: hace atómica una escritura que ya existía (G2).
    """
    docs_dir.mkdir(parents=True, exist_ok=True)
    destino = docs_dir / filename
    with destino.open("x", encoding="utf-8") as fh:   # falla si ya existe
        fh.write(f"# Plan {number} — (borrador)\n\n**Estado:** PROPUESTO v1\n")
    return destino
```

**Pieza 4 — huella de regresión.** Agregar a `Stacky Agents/docs/sistema/error_fingerprints.json`, dentro de la
lista `fingerprints`, una entrada nueva:
```json
{
  "id": "plan-number-collision-2026-07-25",
  "patron": "Dos documentos distintos NN_PLAN_*.md con el mismo NN en Stacky Agents/docs/",
  "causa_raiz": "next_free_number solo miraba el directorio raíz y era un read puro: entre el cálculo del número y la escritura del .md, una sesión paralela podía tomar el mismo número.",
  "plan": "237",
  "fecha": "2026-07-25",
  "guard_test": "backend/tests/test_plan237_plans_triage.py::test_docs_reales_sin_numeros_duplicados"
}
```

**Tests PRIMERO.** En `test_plan237_plans_triage.py`:
```python
def test_universo_de_numeros_cubre_las_cuatro_fuentes(tmp_path):
    from services.plans_board import all_claimed_numbers
    (tmp_path / "05_PLAN_A.md").write_text("# A\n", encoding="utf-8")
    leg = tmp_path / "_legacy"; leg.mkdir()
    (leg / "07_PLAN_VIEJO.md").write_text("# V\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps({"subplans": [{"number": 9, "title": "X"}]}), encoding="utf-8")
    f = all_claimed_numbers(tmp_path)
    assert 5 in f["root"] and 7 in f["subdirs"] and 9 in f["roadmap"]


def test_next_free_salta_por_encima_de_todas_las_fuentes(tmp_path):
    from services.plans_board import next_free_number_effective
    (tmp_path / "05_PLAN_A.md").write_text("# A\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps({"subplans": [{"number": 9, "title": "X"}]}), encoding="utf-8")
    assert next_free_number_effective(tmp_path) == 10   # no 6: el 9 está comprometido


def test_duplicados_se_detectan_con_nombres(tmp_path):
    from services.plans_board import plan_number_duplicates, build_board
    (tmp_path / "37_PLAN_UNO.md").write_text("# Uno\n", encoding="utf-8")
    (tmp_path / "37_PLAN_DOS.md").write_text("# Dos\n", encoding="utf-8")
    (tmp_path / "38_PLAN_SOLO.md").write_text("# Solo\n", encoding="utf-8")
    dups = plan_number_duplicates(tmp_path)
    assert [d["number"] for d in dups] == [37]
    assert dups[0]["filenames"] == ["37_PLAN_DOS.md", "37_PLAN_UNO.md"]
    assert build_board(tmp_path, unpushed_paths=None)["numbering"]["duplicates"] == dups


def test_sin_duplicados_la_lista_esta_vacia(tmp_path):
    from services.plans_board import plan_number_duplicates
    (tmp_path / "37_PLAN_UNO.md").write_text("# Uno\n", encoding="utf-8")
    assert plan_number_duplicates(tmp_path) == []


def test_claim_plan_path_es_exclusivo(tmp_path):
    import pytest as _pytest
    from services.plans_board import claim_plan_path
    p = claim_plan_path(tmp_path, 40, "40_PLAN_X.md")
    assert p.exists()
    with _pytest.raises(FileExistsError):
        claim_plan_path(tmp_path, 40, "40_PLAN_X.md")   # la segunda sesión NO pisa


def test_docs_reales_sin_numeros_duplicados():
    """GUARD (huella plan-number-collision-2026-07-25). Hoy VERDE: la colisión 237/238
    ya se resolvió renumerando. Si vuelve a aparecer un NN repetido, este test se pone
    rojo y nombra los archivos."""
    from services.plans_board import docs_dir_default, plan_number_duplicates
    dups = plan_number_duplicates(docs_dir_default())
    assert dups == [], f"números de plan duplicados en docs/: {dups}"
```

**Comandos:**
```
& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_plan128_plans_board_endpoints.py -q
```
**Criterio BINARIO:** ambos `0 failed`, y
```
& ".venv\Scripts\python.exe" -c "import sys,json; sys.path.insert(0,'.'); from services.plans_board import docs_dir_default as d, plan_number_duplicates as p; print(json.dumps(p(d())))"
```
imprime `[]`.
**Flag:** `STACKY_PLANS_BOARD_ENABLED` para el bloque `numbering` del board;
el `/health` de `api/plans_board.py` queda **sin gate** (ya era así: cómputo barato que cierra el
anti-colisión aunque el tablero esté apagado). **Impacto por runtime:** ninguno (Python puro).
**Human-in-the-loop:** intacto — `claim_plan_path` no tiene endpoint, no decide números por su cuenta y no
escribe contenido: crea el archivo vacío que el operador/agente ya iba a crear.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta, en el plan) |
|---|--------|--------------|------------------------------------|
| R1 | `default=True` sin curar la key deja `test_default_known_only_for_curated` en rojo | **Alta** (ya pasó) | F0 cambio 3 (+ F4 el segundo tiempo). Curar una key inexistente da **KeyError** en `test_declared_default_true_set:805-813`: por eso son dos tiempos |
| R2 | Los tests nuevos no registrados rompen `test_harness_ratchet_meta` | **Alta** (ya pasó) | F4 obliga a agregar las 3 líneas tras `run_harness_tests.sh:248` |
| R3 | El flip de la flag rompe tests del Plan 128 que asumen `default is None` / `is False` | **Confirmado, medido** | F0 cambio 5 edita los 3 tests de `test_plan128_plans_board_flag.py` (uno de ellos ya estaba rojo antes de este plan) |
| R4 | Cambiar el `sort` rompe un test de orden del Plan 128 | **Confirmado, medido** | Es exactamente **uno**: `test_plan128_plans_board_parser.py:253`. F1 lo actualiza en la misma edición |
| R5 | Flag nueva sin entrada en `_CATEGORY_KEYS` ⇒ 2 meta-tests rojos | **Alta** (gotcha recurrente) | F4 edición 1, con test propio `test_flag_de_la_seccion_esta_categorizada` |
| R6 | El bloque nuevo de `api/evolution.py` insertado antes de los `@bp.post` de `:104/:134/:171` deja rojo el test anti-escritura | **Alta** (el v1 lo garantizaba) | F4 fija el punto de inserción (**final del archivo**) + centinela textual buscado por el test |
| R7 | `docs/_roadmap/` con JSON de otra forma (`estado_real_serie_gitlab.json` no tiene `subplans`) hace explotar el lector | Media | `load_roadmap_entries` filtra por `glob("*.json")` + `isinstance` en cada nivel y devuelve `[]` ante cualquier problema; `test_roadmap_corrupto_no_rompe` lo prueba con 3 formas rotas |
| R8 | Archivo `.tsx`/`.module.css` nuevo rompe el ratchet de deuda visual | **Alta** (el v1 lo pedía explícitamente) | G6 corregido: **cero hex también en el CSS** (`var(--token)`), cero `style={{`, cero diálogos nativos. Verificado sin regenerar baseline |
| R9 | Merge con el plan 238 duplica líneas en las 5 estructuras compartidas, **sin conflicto de git** | **Alta** | §3.1: protocolo de verificación post-merge con `compileall` + `pytest test_harness_flags.py` + conteo por `Select-String` |
| R10 | Sesión paralela sobre el mismo árbol se lleva cambios ajenos al commitear | Media | Commitear **siempre** con pathspec explícito (`git commit -- "<ruta>" …`); prohibido `reset`, `amend` y `rebase` |
| R11 | El operador tenía `STACKY_PLANS_BOARD_ENABLED=false` en su `.env` y no ve el cambio | Baja | El default solo aplica cuando la variable **no** está seteada; la ayuda llana actualizada dice "viene así de fábrica" y el panel de flags muestra el valor efectivo |
| R12 | El bucket `SIN_DOCUMENTO` mete 18 filas de ruido para quien no usa la serie 218 | Baja | Grupo `<details>` real (F5), tercero de cinco, y el filtro "Etapa" de F6 lo excluye en un click; con `docs/_roadmap/` vacío el bucket queda vacío y F5 no renderiza grupos vacíos |
| R13 | El memo de encabezados sirve datos viejos si el archivo cambia sin cambiar `mtime` | Muy baja | La clave incluye `size` además de `mtime_ns`; y el TTL de 15 s del board acota la ventana. `test_memo_reparsea_cuando_el_archivo_cambia` cubre el caso normal |
| R14 | `test_docs_reales_sin_numeros_duplicados` se pone rojo por una colisión futura y frena trabajo ajeno | Media | **Es el objetivo** (K6): la colisión debe doler en CI, no descubrirse a ojo. El mensaje nombra los archivos y renumerar es una operación de 1 minuto |

---

## 7. Fuera de scope (explícito)

- **Ejecutar** planes, críticas o supervisiones desde la UI. La sección es de solo lectura + copiar (G2).
- Editar el `**Estado:**` de un doc desde la UI (sería escritura sobre el repo).
- Inferir el estado real leyendo el código (eso es `/supervisar-implementaciones-planes`, ya existe).
- Recorrer `docs/_legacy/` como planes vivos: se **cuentan** (F2) pero no se listan.
- Unificar los dos tabs en uno solo, borrar `PlansBoardPage` o mover el tab de lugar.
- Cambiar el contrato de `docs/_roadmap/serie_paridad_218.json` o tocar la serie 219..236.
- Renumerar, renombrar o tocar cualquier archivo del **plan 238** (incluidos sus `test_plan237_inbox_*.py`).
- Regenerar `backend/harness_defaults.env` (snapshot parcial generado por
  `deployment/export_harness_defaults.py`; regenerarlo arrastra drift de otras features).
- Notificaciones, badges en la barra superior o cualquier superficie fuera del tab "Evolución" y el tab "Planes".
- Cambiar las skills del pipeline de planes para que llamen a `claim_plan_path` (F7 la deja disponible y
  testeada; adoptarla en las skills es un plan aparte).

---

## 8. Glosario (para quien implemente sin conocer el dominio)

| Término | Qué significa acá |
|---------|-------------------|
| **Plan** | Un documento `Stacky Agents/docs/NN_PLAN_<SLUG>.md`. `NN` es un número de 2 o 3 dígitos de una secuencia **compartida** con checklists e incidentes. |
| **Pipeline de planes** | `proponer` → `criticar` → `implementar` → `supervisar`. Cuatro skills; cada una deja rastro (el encabezado `**Estado:**` del doc y/o el ledger). |
| **`**Estado:**`** | Línea del encabezado, parseada por `parse_plan_header`. Normalizada a: `PROPUESTO`, `CRITICADO`, `IMPLEMENTADO`, `IMPLEMENTADO_PARCIAL`, `SIN_ESTADO`. |
| **Ledger de supervisión** | `docs/_supervision/ledger.json`. El supervisor marca `veredicto: APROBADO` con el `doc_sha256` del momento. |
| **`doc_drift`** | El doc cambió **después** de que el supervisor lo aprobó (SHA-256 actual ≠ el del ledger) ⇒ la aprobación ya no vale. |
| **`estado_efectivo`** | `"APROBADO"` si el ledger aprobó y no hay drift; si no, el estado del doc. Lo calcula `build_board:277`. |
| **Bucket de triage** | Los 5 grupos que crea este plan. El orden ES el contrato. |
| **Flag del arnés** | Interruptor declarado en `FLAG_REGISTRY` (`services/harness_flags.py`), clasificado en `_CATEGORY_KEYS`, reflejado en `config.py` y editable desde el panel de flags de la UI. |
| **Excepción dura** | Las 4 únicas razones para que una flag nazca OFF: (1) acción automática que bypasea revisión humana, (2) destructiva/irreversible, (3) prerequisito no garantizado en instalación default, (4) reduce seguridad por default. **Ninguna aplica a este plan.** |
| **Ratchet** | Test que congela una métrica para que solo pueda mejorar (deuda visual, cobertura del arnés). |
| **Runtime** | El motor que ejecuta a los agentes: Codex CLI, Claude Code CLI o GitHub Copilot Pro. |
| **`SIN_DOCUMENTO`** | Plan comprometido en un roadmap de `docs/_roadmap/` que todavía no tiene su `.md`. |
| **Creación exclusiva** | `open(path, "x")`: crea el archivo o falla con `FileExistsError`. Es atómica en el filesystem, así que dos procesos no pueden ganar los dos. |

---

## 9. Orden de implementación (numerado, en este orden exacto)

1. **F0** — flags a default ON (`config.py`, `harness_flags.py`, `harness_flags_help.py`,
   `_CURATED_DEFAULTS_ON`) **+ las 3 ediciones de `test_plan128_plans_board_flag.py`** + los 2 tests nuevos.
   Verificar los 4 comandos de F0.
2. **F1** — `TRIAGE_BUCKETS`, `triage_bucket`, `triage_rank`, nuevo `sort`, `triage_order`/`triage_totals`.
   Verificar + no-regresión de `test_plan128_plans_board_parser.py`.
3. **F2** — `_MAX_PLAN_FILES`, `_read_header_cached` (memo), `scan_plan_files_with_census`, `census`,
   `deepcopy` en `get_board_cached`, piso de `refresh`. Verificar + no-regresión del Plan 128.
4. **F3** — `load_roadmap_entries`, `reserved_numbers`, `next_free_number_effective`, `build_planned_cards`,
   swap en `api/plans_board.py:39`. Verificar + `test_plan218_serie_integridad.py`.
5. **F7** — guardia de numeración (`all_claimed_numbers`, `plan_number_duplicates`, `claim_plan_path`, bloque
   `numbering`, huella en `error_fingerprints.json`). **Va ANTES de F4** porque el endpoint de F4 asserta
   `"numbering" in body`.
6. **F4** — `_CATEGORY_KEYS` + flag nueva + `/api/evolution/plans` **appendeado al final** de `api/evolution.py`
   + archivo de tests de endpoint + **registro en `run_harness_tests.sh`**. Verificar los 5 comandos.
7. **F5** — `plansTriageModel.ts` (+ su test), `PlansSection.tsx`, `PlansSection.module.css`, `endpoints.ts`,
   montaje en `EvolutionCenterPage.tsx`. Verificar vitest + `tsc --noEmit` + ratchet de deuda visual.
8. **F6** — filtro y columna "Etapa" en el tab "Planes". Verificar vitest + `tsc --noEmit`.
9. **Cierre** — actualizar el `**Estado:**` de este doc a `IMPLEMENTADO` con fecha y agregar una sección
   "§11 Reporte de implementación" con los desvíos reales y los comandos corridos.

---

## 10. Definición de Hecho (DoD) — todo binario

- [ ] Con la configuración de fábrica (sin ninguna variable de entorno seteada), abrir el tab **Evolución**
      muestra la sección **Planes** con sus grupos, y el primer grupo no vacío es **"Sin implementar"**.
- [ ] `GET /api/evolution/plans` responde **200** con `triage_order`, `triage_totals`, `census`, `numbering`
      y `triage_bucket` en **todos** los elementos de `plans`.
- [ ] `GET /api/evolution/plans` responde **404** con `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED=false`,
      y también con `STACKY_EVOLUTION_CENTER_ENABLED=false`.
- [ ] El tab **Planes** aparece sin tocar ninguna flag, y su tabla llega ordenada por triage.
- [ ] `next_free_number` del board **no** está en `reserved_numbers()`, **no** pertenece a ningún plan con
      documento y es **> max existente** (hoy eso da **239**; el criterio es relativo, no el literal 239).
- [ ] Los 18 subplanes 219..236 aparecen en el bucket **`SIN_DOCUMENTO`**; el 218 **no**.
- [ ] `numbering.duplicates == []` sobre el `docs/` real.
- [ ] `census` cierra la cuenta:
      `plans_parsed + skipped_not_a_plan + skipped_oversize + skipped_unreadable + skipped_over_cap == files_seen`,
      y `skipped_subdirs >= 3`.
- [ ] Un segundo escaneo sin cambios en disco **no** vuelve a abrir los archivos (`test_memo_no_relee_...`).
- [ ] Estos comandos terminan con `0 failed` (desde `Stacky Agents/backend`, uno por uno):
      `tests\test_plan237_plans_triage.py`, `tests\test_plan237_plans_triage_endpoint.py`,
      `tests\test_harness_flags.py`, `tests\test_harness_flags_help.py`, `tests\test_flag_wiring.py`,
      `tests\test_harness_ratchet_meta.py`, `tests\test_evolution_endpoints.py`,
      `tests\test_plan128_plans_board_parser.py`, `tests\test_plan128_plans_board_endpoints.py`,
      `tests\test_plan128_plans_board_flag.py`, `tests\test_plan128_plans_board_git.py`,
      `tests\test_plan218_serie_integridad.py`.
      *(`test_plan128_plans_board_flag.py` estaba en **rojo antes** de este plan: F0 lo deja verde.)*
- [ ] Estos comandos terminan verdes (desde `Stacky Agents/frontend`, uno por uno):
      `npx vitest run src/evolution/plansTriageModel.test.ts`,
      `npx vitest run src/plansBoard/model.test.ts`,
      `npx vitest run src/__tests__/uiDebtRatchet.test.ts` (**sin** regenerar baseline),
      `npx tsc --noEmit`.
- [ ] `PlansSection.tsx` no contiene `style={{` ni diálogos nativos; `PlansSection.module.css` **no contiene
      ningún literal hexadecimal** (solo `var(--…)`).
- [ ] Ningún endpoint de escritura nuevo; la sección solo lee y copia al portapapeles.
- [ ] Las dos variantes de copiado (comando y frase natural) se renderizan siempre, en todos los buckets.
- [ ] La huella `plan-number-collision-2026-07-25` está registrada en `docs/sistema/error_fingerprints.json`
      con su `guard_test`, y ese guard test corre verde.
- [ ] Post-merge con el plan 238: cada key nueva aparece **exactamente una vez** por estructura compartida
      (§3.1) y `pytest tests\test_harness_flags.py -q` da `0 failed`.
- [ ] Commit con pathspec explícito de los archivos de este plan; **sin `git push`** salvo pedido del operador.

---

## 11. Reporte de implementación (2026-07-25)

**Rama:** `feat/plan-217-migrador-mantis-gitlab` (rama de trabajo activa; no se creó una nueva).

| Fase | Estado | Comando corrido | Resultado real |
|------|--------|-----------------|----------------|
| F0 | IMPLEMENTADA | `pytest tests\test_plan237_plans_triage.py -q` | 27 passed |
| F0 | IMPLEMENTADA | `pytest tests\test_plan128_plans_board_flag.py -q` | **6 passed** (antes: 1 failed, 5 passed) |
| F1 | IMPLEMENTADA | `pytest tests\test_plan128_plans_board_parser.py -q` | 25 passed |
| F2 | IMPLEMENTADA | `pytest tests\test_plan128_plans_board_endpoints.py -q` | 8 passed |
| F3 | IMPLEMENTADA | `pytest tests\test_plan218_serie_integridad.py -q` | 10 passed |
| F7 | IMPLEMENTADA | `plan_number_duplicates(docs/)` | `[]`; `next_free_number_effective` = **239** |
| F4 | IMPLEMENTADA | `pytest tests\test_plan237_plans_triage_endpoint.py -q` | 8 passed |
| F4 | IMPLEMENTADA | `pytest tests\test_harness_flags.py -q` / `test_flag_wiring.py` / `test_harness_ratchet_meta.py` / `test_evolution_endpoints.py` | 56 / 5 / 4 / 11 passed |
| F5 | IMPLEMENTADA | `npx vitest run src/evolution/plansTriageModel.test.ts` | 10 passed |
| F6 | IMPLEMENTADA | `npx vitest run src/plansBoard/model.test.ts` | 11 passed |
| F5+F6 | IMPLEMENTADA | `npx tsc --noEmit` + `uiDebtRatchet` + `copyDebtRatchet` | 0 errores; 3 + 3 passed **sin regenerar baseline** |

**Flags (ambas default ON, ninguna de las 4 excepciones duras aplica):**
`STACKY_PLANS_BOARD_ENABLED` (promovida de opt-in a ON) y `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED` (nueva,
`requires=STACKY_EVOLUTION_CENTER_ENABLED`). Ambas UI-editables desde el panel de flags del arnés, con
categoría y ayuda llana registradas.

### Desvíos respecto del plan (declarados, no maquillados)

1. **`test_harness_flags_help.py` NO puede quedar en `0 failed`** (criterio 3 de F0). Estaba **rojo antes**
   de este plan con **3 tests fallando** por deuda ajena masiva: 44 flags sin ayuda llana (no solo la del
   192), `STACKY_EGRESS_SENTINEL_MAX_CHARS` con `off_effect` que no empieza con `"Si "`, y 15 violaciones de
   jerga. **Verificado que este plan no agrega ni una**: `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED` no aparece
   en ninguna de las tres listas de faltantes. La violación preexistente
   `STACKY_PLANS_BOARD_ENABLED: cita una key SCREAMING_SNAKE` vive en su campo `what` (la cadena `NN_PLAN`),
   que este plan **no** toca; arreglarla queda fuera de alcance.
2. **F2 rompió un segundo test del Plan 128 que el plan no enumeró** (§6 R4 afirmaba "es exactamente uno").
   El piso anti-ráfaga `_BOARD_MIN_REFRESH_SEC` contradice `test_refresh_invalida_cache`
   (`test_plan128_plans_board_endpoints.py`), que exige que `?refresh=1` reconstruya de inmediato. Se
   **conservó el piso** (instrucción literal de F2 + G8) y se adaptó ese test para que pruebe las dos mitades
   del contrato nuevo: dentro del piso devuelve cache, pasado el piso reconstruye.
3. **F5 usa `copyText` (services/copyService), no `navigator.clipboard.writeText`.** El plan pedía
   `navigator.clipboard` en un `try/catch`, pero eso viola `copyDebtRatchet.test.ts` (Plan 194), que congela
   las escrituras directas al portapapeles fuera del servicio canónico. Con `copyText` el ratchet queda
   verde y el comportamiento (incluido el fallback) es el de la casa.
4. **Tokens de CSS corregidos.** El plan mandaba copiar las variables de `KnowledgeSection.module.css`, pero
   ese archivo usa `var(--text)` y `var(--surface-2)`, que **no existen** en `theme.css` (bug preexistente
   del Plan 170: esos colores caen a herencia). `PlansSection.module.css` usa los tokens reales
   (`--text-primary`, `--bg-elev`, `--warn` en vez del inexistente `--warning`). Cero hex igualmente.
5. **La huella de regresión usa el esquema real de `error_fingerprints.json`**
   (`id`/`title`/`class`/`status`/`log_pattern`/`log_guarded`/`killed_by`/`guard_test`/`self_test`), no el
   shape aproximado del plan (`patron`/`causa_raiz`/`plan`/`fecha`), que habría puesto rojo
   `test_error_fingerprints_catalog.py`. Verificado: 8 passed.

### Pendiente

- **Smoke manual** del DoD (abrir el tab Evolución con configuración de fábrica y confirmar que el primer
  grupo no vacío es "Sin implementar"). No se ejecutó: requiere levantar backend + frontend.
- Adoptar `claim_plan_path` en las skills del pipeline (explícitamente fuera de alcance, §7).
