# Plan 128 — Tablero de Evolución de Planes (pipeline proponer→criticar→implementar→supervisar, solo lectura)

**Estado:** IMPLEMENTADO — 2026-07-14 (F0..F6 vía implementar-plan-stacky; ver crítica v2 CRITICADO/APROBADO-CON-CAMBIOS del mismo día. Renumerado de 127→128 el 2026-07-12: el número 127 colisionó con el plan ajeno "reuso IA local" `e922b78f` propuesto en paralelo por otra sesión. La colisión es EXACTAMENTE el bug que este plan elimina con `next_free_number`.)
**Dependencias:** ninguna dura. Reusa el ledger de supervisión existente (`docs/_supervision/ledger.json`) y el patrón de tab gateado por flag de los Planes 74/87. NO depende de los planes 120-127.
**Ortogonal a:** Planes 119/120/121/122-126/127 (no toca DevOps, ni despliegues, ni comparador de BD, ni la IA local).

> ### Changelog v1 → v2 (crítica adversarial 2026-07-14, juez `StackyArchitectaUltraEficientCode`)
> Veredicto: **APROBADO-CON-CAMBIOS** (0 bloqueantes, 2 importantes, 1 menor, 1 adición de arquitecto). Cambios aplicados in place:
> - **C1 (IMPORTANTE)** — F0 test #3 citaba `STACKY_GITLAB_DEEP_LINKS_ENABLED` como ejemplo de flag bool "sin default", pero esa flag fue promovida a `default=True` el 2026-07-10 (`services/harness_flags.py:2497`, curada en `_CURATED_DEFAULTS_ON`) — el ejemplo estaba roto desde la redacción de v1. Reemplazado por un ejemplo verificado (`CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED`) y la aserción se simplificó para no depender de comparar contra otra flag.
> - **C2 (IMPORTANTE)** — la cita `config.py:494-497` como "patrón EXACTO" ya estaba desactualizada (ubicación real verificada: `config.py:484-487`) — evidencia viva de que los números de línea rotan rápido en este repo por sesiones concurrentes. Se agregó guardarraíl §3.9 aplicable a TODAS las citas `archivo:línea` del doc (ubicar por contenido/comentario, nunca solo por número).
> - **C4 (MENOR)** — `_MAX_FILE_BYTES` hacía desaparecer silenciosamente un doc de plan sin ninguna card, contradiciendo el principio R1 ("el board muestra el gap, no lo esconde"). Documentado explícitamente como limitación aceptada (probabilidad ~0: ningún doc real supera los 2MB) en vez de complejizar el contrato.
> - **[ADICIÓN ARQUITECTO]** — `GET /api/plans-board/health` ahora incluye `next_free_number` SIEMPRE (sin gate de flag, cómputo barato de un solo `iterdir()`), para que la garantía anti-colisión (KPI-2, el problema que este plan documenta 3 veces materializado) exista incluso con el tablero visual apagado — cero trabajo nuevo del operador, reusa `next_free_number` de F1 sin tocar su contrato.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Los regex, contratos JSON, tablas de
> decisión y nombres son LITERALES: prohibido desviarse de los nombres exactos,
> prohibido "mejorar" el alcance. Todo lo ambiguo ya fue decidido acá.

---

## 1. Objetivo + KPI

Stacky evoluciona por un pipeline de planes (`proponer-plan-stacky` → `criticar-y-mejorar-plan`
→ `implementar-plan-stacky` → `supervisar-implementaciones-planes`), pero ese pipeline —
el corazón del proyecto — **no tiene ninguna superficie en la app**. Hoy el estado de cada
plan vive desparramado en 4 lugares que solo se cruzan a mano:

1. El encabezado `**Estado:**` de cada `docs/NN_PLAN_*.md`.
2. El ledger de supervisión `docs/_supervision/ledger.json` (veredictos APROBADO + sha del doc).
3. Git (commits de planes que quedan SIN pushear durante días — "push manual pendiente" crónico).
4. La memoria del asistente (frágil, externa a la app).

Este plan agrega un **tab "Planes" de SOLO LECTURA** que parsea esas 4 fuentes y muestra,
por plan: estado del pipeline, veredicto del juez, aprobación del supervisor (con detección
de drift doc-vs-aprobación por sha256), commits sin push, colisiones de numeración, el
**próximo número libre** (mata el bug recurrente de colisiones: el 110 fue tomado dos veces,
el 118 obligó a renumerar el 119, y el 127 colisionó DURANTE la escritura de este mismo doc),
y una **acción sugerida copiable al portapapeles** (el comando de skill para Claude Code +
su equivalente en lenguaje natural para Codex CLI / Copilot). La página **jamás ejecuta
nada**: amplifica al operador, no lo reemplaza.

**KPIs (binarios):**

- **KPI-1 (utilidad día uno):** la pregunta "¿en qué estado está el plan NN y qué sigue?"
  se responde en un solo lugar. Proxy verificable: sobre un directorio fixture con los 5
  formatos reales de encabezado, `build_board` clasifica el 100% de los planes con el
  estado y la acción sugerida EXACTOS de la tabla §4.3 (tests F1).
- **KPI-2 (anti-colisión):** `next_free_number` correcto contando TODOS los archivos `NN_`
  (planes, checklists, incidentes) y las colisiones marcadas con `duplicate: true`
  (tests F1, casos 6-7).
- **KPI-3 (cero regresión):** con la flag OFF, los endpoints devuelven 404, el tab no se
  renderiza, y `tests/test_harness_flags.py` sigue verde (tests F0/F3).

## 2. Por qué ahora / gap que cierra (evidencia)

- `docs/sistema/11-estado-planes.md` es el intento manual de esto: una tabla estática que
  cubre SOLO los docs 19-46, ya vencida, y cuyas propias notas admiten el problema
  ("Donde el header dice 'propuesto' pero MEMORY/git indican que se implementó, se marca
  el conflicto"). Automatizarla con las fuentes vivas es estrictamente mejor.
- El ledger `docs/_supervision/ledger.json` ya existe, ya guarda `veredicto`, `fecha`,
  `tests`, `evidencia` y `doc_sha256` por plan (schema real verificado) — pero es
  invisible: nadie lo ve salvo el agente supervisor.
- Colisiones de numeración REALES y recurrentes: plan 110 tomado por dos planes distintos;
  118 colisionó con winrm-1click y obligó a renumerar el 119; y el 2026-07-12 DOS sesiones
  propusieron "127" en paralelo (este doc nació 127 y tuvo que renumerarse a 128). Tres
  colisiones documentadas. Un "próximo número libre" visible las elimina.
- "Push manual pendiente" es el estado crónico del repo (regla del pipeline: los commits
  de planes NUNCA se pushean solos). Hoy no hay forma de ver cuántos planes están en esa
  condición sin correr git a mano.
- La app ya tiene el patrón exacto para esto: tab gateado por flag vía endpoint `/health`
  (Plan 74 `migrador`, Plan 87 `devops` — `frontend/src/App.tsx:82-95`), gating 404 de
  endpoints por flag (Plan 109 — `backend/api/docs.py:219-221`), y blueprints Flask
  registrados en `backend/api/__init__.py`. Este plan solo replica patrones probados.

## 3. Principios y guardarraíles (NO negociables)

1. **Solo lectura absoluta:** el backend lee archivos y corre UN comando git de solo
   lectura (`git log`). Prohibido: escribir archivos, `git push`, `git add`, tocar el
   ledger, editar docs. El frontend solo copia texto al portapapeles.
2. **Human-in-the-loop:** la "acción sugerida" es TEXTO copiable. La página no dispara
   skills, no lanza agentes, no ejecuta git. El operador decide y ejecuta en su terminal.
3. **Paridad 3 runtimes:** la feature es un panel (backend Flask + frontend React):
   idéntica bajo Codex CLI, Claude Code CLI y Copilot Pro. El único punto runtime-sensible
   es el comando sugerido (las skills `/...` son de Claude Code): por eso CADA acción trae
   TAMBIÉN `natural_language` (instrucción en castellano pegable en cualquier runtime).
   Degradación explícita: sin git disponible → columna Push muestra "—"; sin ledger →
   columna Supervisión muestra "—"; nunca se rompe.
4. **Cero trabajo del operador:** opt-in con `STACKY_PLANS_BOARD_ENABLED` default OFF,
   activable desde el HarnessFlagsPanel (registry dinámico — sin pasos manuales nuevos,
   sin editar archivos). Con OFF, comportamiento byte-idéntico al actual.
5. **Mono-operador, sin auth:** cero RBAC, cero multiusuario.
6. **No degradar performance:** listado = escaneo NO recursivo de `docs/` leyendo los
   primeros 4000 chars por archivo + UNA llamada git batcheada + sha256 SOLO de los docs
   presentes en el ledger; cache TTL 15 s con `?refresh=1`.
7. **Gotchas de flags (obligatorio):** la FlagSpec bool va SIN `default=False` explícito
   (gotcha Plan 63: rompería `test_default_known_only_for_curated`); SIN `requires` (no
   tiene master); SIN `env_only` (queda UI-editable); NO tocar `_CURATED_DEFAULTS_ON`;
   categoría EXISTENTE `observabilidad_notif` (crear categoría nueva rompería la paridad
   16==N con `CATEGORY_VISUALS` del frontend, Plan 78).
8. **Al implementar:** `config.py` y `harness_flags.py` suelen tener WIP ajeno de sesiones
   concurrentes → staging quirúrgico por hunk (`git add -p` o pathspec); PROHIBIDO
   `git stash`/`reset`/`checkout` de limpieza.
9. **[v2] Citas `archivo:línea` son APROXIMADAS, no literales:** este repo tiene planes
   escribiéndose en paralelo constantemente (evidencia real: la propia cita `config.py:494-497`
   de este doc ya rotó a `config.py:484-487` entre la redacción de v1 y la crítica v2). TODA
   cita de línea en este documento (config.py, harness_flags_help.py, App.tsx, etc.) debe
   tratarse como orientativa: ubicar el punto de edición por el CONTENIDO/comentario citado
   (ej. el comentario `# ── Plan 109`, el nombre del símbolo, el bloque de código mostrado),
   nunca confiar en que el número de línea siga siendo exacto.

## 4. Contratos congelados

### 4.1 Regex y normalización (LITERALES — van tal cual al código)

```python
_PLAN_FILE_RE   = re.compile(r"^(\d{2,3})_PLAN_(.+)\.md$")      # solo planes
_SEQ_PREFIX_RE  = re.compile(r"^(\d{2,3})_")                    # secuencia compartida (planes+checklists+incidentes)
_ESTADO_RE      = re.compile(r"^\s*(?:>\s*)?\*\*Estado:\*\*\s*(.+?)\s*$", re.MULTILINE)
_VEREDICTO_RE   = re.compile(r"APROBADO-CON-CAMBIOS|RECHAZADO|APROBADO")   # orden importa
_VERSION_RE     = re.compile(r"\bv(\d+(?:\.\d+)*)", re.IGNORECASE)
_FECHA_RE       = re.compile(r"20\d{2}-\d{2}-\d{2}")
```

Reglas duras:
- `_ESTADO_RE` se aplica a los **primeros 4000 caracteres** del archivo y se toma el
  **primer** match. El literal `\*\*Estado:\*\*` NO matchea `**Estado previo:**` ni
  `**Estado del arte (verificado):**` (variantes reales en docs 111/100) — hay tests
  trampa para ambos.
- El escaneo de `docs/` es **no recursivo** (`iterdir()`, solo archivos): `_legacy/`,
  `sistema/`, `specs/`, `_supervision/`, `_roadmap/`, `_evals/` quedan fuera solos.

```python
def normalize_estado(raw: str | None) -> str:
    # Devuelve UNO de: "PROPUESTO" | "CRITICADO" | "IMPLEMENTADO" |
    #                  "IMPLEMENTADO_PARCIAL" | "SIN_ESTADO"
    if not raw:
        return "SIN_ESTADO"
    u = raw.upper()
    if "IMPLEMENTADO-PARCIAL" in u:          # antes que startswith IMPLEMENTADO
        return "IMPLEMENTADO_PARCIAL"
    if u.startswith("IMPLEMENTADO"):
        return "IMPLEMENTADO"
    if u.startswith("CRITICADO"):
        return "CRITICADO"
    if u.startswith(("PROPUESTO", "PROPUESTA")):
        return "PROPUESTO"
    return "SIN_ESTADO"
```

Variantes reales que los tests fixtures cubren (copiadas de docs vivos):
- `**Estado:** PROPUESTO (v1)` → PROPUESTO, version "1"
- `**Estado:** PROPUESTO (v1.1, 2026-07-12 — integra prior art…)` → PROPUESTO, "1.1", fecha 2026-07-12
- `> **Estado:** IMPLEMENTADO — 2026-07-09 (F0..F6 vía implementar-plan-stacky…)` → IMPLEMENTADO
- `> **Estado:** CRITICADO v2 (APROBADO-CON-CAMBIOS) — 2026-07-10` → CRITICADO, veredicto APROBADO-CON-CAMBIOS, version "2"
- `> **Estado:** IMPLEMENTADO-PARCIAL — 2026-07-10 (F0-F3…)` → IMPLEMENTADO_PARCIAL

### 4.2 Ledger (lectura tolerante)

Ruta: `<docs_dir>/_supervision/ledger.json`. Schema real: `{"version": 1, "planes": {"51": {...}}}`.
- Claves de `planes` = número SIN ceros a la izquierda: lookup con `planes.get(str(number))`.
- Campos usados: `veredicto` (valores reales: `"APROBADO"`, `"TERMINADO-POR-SUPERVISOR"`),
  `fecha`, `doc_sha256` (OPCIONAL — entradas 81-85 no lo tienen).
- `doc_drift`: si la entrada tiene `doc_sha256` → `hashlib.sha256(path.read_bytes()).hexdigest() != doc_sha256.lower()`;
  si NO tiene `doc_sha256` → `doc_drift = None` (desconocido, NO se asume drift).
- Encoding: intentar `utf-8`; ante `UnicodeDecodeError` reintentar `utf-16` (el ledger fue
  escrito por PowerShell en algún momento). Cualquier otra excepción (archivo ausente,
  JSON roto) → devolver `{}` sin loggear error (es un estado válido).
- `ledger_ok(entry)` = `entry` existe y `entry.get("veredicto") in ("APROBADO", "TERMINADO-POR-SUPERVISOR")`.

### 4.3 Tabla de acción sugerida (congelada — evaluar EN ESTE ORDEN, gana la primera)

| # | Condición | kind | label | command | natural_language |
|---|-----------|------|-------|---------|------------------|
| 1 | `ledger_ok` y `doc_drift is not True` y `unpushed is True` | `push` | `Push pendiente` | `git push` | `El plan <NN> está aprobado pero sus commits siguen sin pushear: corré git push manualmente cuando quieras publicarlos.` |
| 2 | `ledger_ok` y `doc_drift is not True` | `ok` | `Al día` | `null` | `Plan <NN> al día: implementado, supervisado y aprobado.` |
| 3 | entrada de ledger presente y `doc_drift is True` | `supervisar` | `Re-supervisar (drift)` | `/supervisar-implementaciones-planes <NN>` | `El doc del plan <NN> cambió después de la aprobación del supervisor: pedile al agente re-supervisar el plan <NN>.` |
| 4 | estado `PROPUESTO` | `criticar` | `Criticar plan` | `/criticar-y-mejorar-plan <NN>` | `Pedile al agente criticar y mejorar el plan <NN> con el juez adversarial antes de implementarlo.` |
| 5 | estado `CRITICADO` | `implementar` | `Implementar plan` | `/implementar-plan-stacky <NN>` | `Pedile al agente implementar el plan <NN> fase por fase con TDD, sin falsos verdes.` |
| 6 | estado `IMPLEMENTADO` o `IMPLEMENTADO_PARCIAL` | `supervisar` | `Supervisar` | `/supervisar-implementaciones-planes <NN>` | `Pedile al agente supervisar la implementación del plan <NN> contra su documento y cerrar lo que falte.` |
| 7 | resto (`SIN_ESTADO`) | `revisar` | `Sin estado` | `null` | `El doc del plan <NN> no tiene línea **Estado:** — agregásela para que el tablero lo clasifique.` |

`<NN>` = `number_str` (ej. "128"). `estado_efectivo` (para chips y totales) = `"APROBADO"`
si aplica fila 1 o 2; si no, el estado normalizado del doc.

### 4.4 Contratos HTTP (congelados)

`GET /api/plans-board/health` → **siempre 200** (sin gate, patrón Plan 87):
```json
{"ok": true, "flag_enabled": false, "next_free_number": 129}
```
**[v2 ADICIÓN ARQUITECTO]** `next_free_number` va SIEMPRE en `/health`, INDEPENDIENTE del
flag (`null` solo si `docs_dir_default()` no existe — deploy sin carpeta `docs/`). Motivo:
el problema que este plan documenta materializado 3 veces (colisión de número de plan) debe
quedar resuelto incluso para operadores/agentes que nunca activaron el tablero visual; el
cómputo es un solo `iterdir()` + regex (sin ledger, sin git, sin cache) — costo despreciable,
cero trabajo nuevo del operador, reusa `next_free_number` de F1 tal cual.

`GET /api/plans-board/list` (query opcional `refresh=1` invalida cache):
- Flag OFF → **404** `{"ok": false, "error": "plans_board_disabled", "message": "El tablero de planes está deshabilitado (STACKY_PLANS_BOARD_ENABLED)."}`
- Flag ON → **200**:
```json
{
  "ok": true,
  "generated_at": "2026-07-12T15:00:00+00:00",
  "docs_dir_found": true,
  "git_available": true,
  "next_free_number": 129,
  "totals": {"PROPUESTO": 9, "CRITICADO": 2, "IMPLEMENTADO": 3, "IMPLEMENTADO_PARCIAL": 1,
             "APROBADO": 40, "SIN_ESTADO": 2, "unpushed": 6, "duplicados": 0, "total": 57},
  "plans": [ { "...": "PlanCard, ver abajo, orden number DESC" } ]
}
```
PlanCard (todas las claves SIEMPRE presentes; `null` cuando no aplica):
```json
{
  "number": 126, "number_str": "126",
  "slug": "DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO",
  "filename": "126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md",
  "path_rel": "Stacky Agents/docs/126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md",
  "title": "Plan 126 — Comparador de BD entre ambientes (…)",
  "estado": "PROPUESTO", "estado_raw": "PROPUESTO (v1.1, 2026-07-12 — …)",
  "estado_efectivo": "PROPUESTO",
  "veredicto": null, "version": "1.1", "fecha": "2026-07-12",
  "duplicate": false,
  "ledger": null,
  "unpushed": true,
  "suggested_action": {"kind": "criticar", "label": "Criticar plan",
                        "command": "/criticar-y-mejorar-plan 126",
                        "natural_language": "Pedile al agente criticar y mejorar el plan 126 con el juez adversarial antes de implementarlo."}
}
```
Cuando hay entrada de ledger: `"ledger": {"veredicto": "APROBADO", "fecha": "2026-06-20", "doc_drift": false}`.
`unpushed`: `true`/`false` con git disponible; `null` si `git_available=false`.
`path_rel` SIEMPRE con `/` (posix), relativo a la raíz del repo.

`GET /api/plans-board/detail/<int:number>`:
- Flag OFF → 404 `plans_board_disabled` (mismo shape).
- Número inexistente → 404 `{"ok": false, "error": "plan_not_found"}`.
- OK → 200 `{"ok": true, "plan": PlanCard, "duplicates": [PlanCard…], "head_excerpt": "<primeras 60 líneas del md, crudas>"}`.
  (`duplicates` = las OTRAS cards con el mismo número; lista vacía si no hay colisión.)

---

## 5. Fases

### F0 — Flag + config + help + defaults

**Objetivo:** declarar `STACKY_PLANS_BOARD_ENABLED` (bool, default OFF, UI-editable) sin romper la suite de flags.
**Valor:** kill-switch y opt-in del feature completo.

**Archivos a editar (4):**
1. `Stacky Agents/backend/services/harness_flags.py`:
   - Agregar al `FLAG_REGISTRY` (al final, junto a las flags de planes recientes):
   ```python
   FlagSpec(
       key="STACKY_PLANS_BOARD_ENABLED",
       type="bool",
       label="Tablero de evolución de planes",
       description=(
           "Tab 'Planes' de solo lectura: estado del pipeline "
           "proponer→criticar→implementar→supervisar por cada plan de docs/, "
           "aprobación del supervisor, commits sin push y acción sugerida copiable."
       ),
       group="global",
   ),
   ```
   SIN `default=`, SIN `requires=`, SIN `env_only=` (guardarraíl §3.7).
   - Agregar `"STACKY_PLANS_BOARD_ENABLED"` a la tupla EXISTENTE
     `_CATEGORY_KEYS["observabilidad_notif"]` (el dict arranca en `harness_flags.py:111`;
     buscá la clave por nombre, no por número de línea).
2. `Stacky Agents/backend/config.py` — patrón EXACTO del Plan 109 (ubicar por el comentario
   `# ── Plan 109 — Grafo documental READ-ONLY`, hoy en `~config.py:484-487`; ver guardarraíl §3.9):
   ```python
   # ── Plan 128 — Tablero de evolución de planes (default OFF, editable por UI) ──
   STACKY_PLANS_BOARD_ENABLED: bool = os.getenv(
       "STACKY_PLANS_BOARD_ENABLED", "false"
   ).strip().lower() == "true"
   ```
3. `Stacky Agents/backend/services/harness_flags_help.py` — entrada `PlainHelp` (formato
   exacto del dict, ver `STACKY_DOCS_GRAPH_ENABLED` en `harness_flags_help.py:268`):
   ```python
   "STACKY_PLANS_BOARD_ENABLED": PlainHelp(
       what="Muestra un tablero de solo lectura con todos los planes NN_PLAN de docs/ y en qué paso del pipeline está cada uno (propuesto, criticado, implementado, supervisado), más si sus commits ya se pushearon.",
       on_effect="Si la activás: aparece el tab 'Planes' con el tablero, el próximo número libre y una acción sugerida copiable por plan. No ejecuta nada por sí solo.",
       off_effect="Si la apagás: el tab desaparece y /api/plans-board devuelve 404. Todo lo demás sigue exactamente igual.",
       example="Como un tablero kanban de la evolución de Stacky, pero automático: lee los docs, el ledger de supervisión y git, y te dice qué sigue.",
   ),
   ```
4. `Stacky Agents/backend/harness_defaults.env` — insertar `STACKY_PLANS_BOARD_ENABLED=false`
   respetando el ORDEN ALFABÉTICO del archivo.

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan128_plans_board_flag.py`
(espejo de `tests/test_plan93_preflight_flag.py`; 6 casos):
1. `test_flag_declarada_en_registry` — existe FlagSpec con esa key, `type == "bool"`.
2. `test_flag_ui_editable` — `env_only` es False/ausente en la spec.
3. `test_flag_sin_default_explicito` — `spec.default is None` (confirmado: el campo `default`
   de `FlagSpec` tiene default `None` en el dataclass — `services/harness_flags.py:29` —, así
   que basta con esta aserción directa, SIN comparar contra otra flag. Si se quiere un ejemplo
   cruzado de referencia, usar `CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED`, que es bool y no pasa
   `default=` — `services/harness_flags.py:288-293`. **NO usar `STACKY_GITLAB_DEEP_LINKS_ENABLED`
   como ejemplo de "sin default": esa flag SÍ tiene `default=True` explícito desde 2026-07-10,
   curada en `_CURATED_DEFAULTS_ON` — `services/harness_flags.py:2497`.**).
4. `test_config_default_off` — con env limpio, `config.STACKY_PLANS_BOARD_ENABLED is False`.
5. `test_categoria_observabilidad` — la key está en `_CATEGORY_KEYS["observabilidad_notif"]`.
6. `test_defaults_env_y_help` — `harness_defaults.env` contiene la línea `STACKY_PLANS_BOARD_ENABLED=false` y el dict de help contiene la key.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan128_plans_board_flag.py tests/test_harness_flags.py -q`
**Criterio binario:** 6/6 nuevos verdes Y `test_harness_flags.py` sin regresión (los fallos preexistentes documentados de `test_default_known_only_for_curated` no cuentan como regresión SOLO si ya fallaban en HEAD antes de tocar nada — verificarlo corriéndolo ANTES de F0).
**Flag:** `STACKY_PLANS_BOARD_ENABLED` default OFF. **Runtimes:** N/A (declaración). **Operador:** ninguno.

### F1 — Servicio parser puro: `services/plans_board.py`

**Objetivo:** escanear `docs/`, parsear encabezados, mergear ledger y producir el board como dict puro (sin git, sin Flask, sin cache).
**Valor:** toda la lógica testeable con `tmp_path`, sin tocar el repo real.

**Archivo a crear:** `Stacky Agents/backend/services/plans_board.py`

**Símbolos EXACTOS (además de los regex/normalizadores de §4.1):**
```python
from dataclasses import dataclass, field, asdict
from pathlib import Path

_HEADER_READ_CHARS = 4000
_MAX_FILE_BYTES = 2_000_000          # archivos más grandes se saltean (defensa)

def parse_plan_header(text: str) -> dict
    # text = primeros _HEADER_READ_CHARS chars. Devuelve SIEMPRE las claves:
    # {"title": str|None, "estado_raw": str|None, "estado": str,
    #  "veredicto": str|None, "version": str|None, "fecha": str|None}
    # title = primera línea que empieza con "# " (strip del "# "); None si no hay.
    # estado_raw = primer match de _ESTADO_RE; estado = normalize_estado(estado_raw).
    # veredicto/version/fecha = regex de §4.1 sobre estado_raw (None si estado_raw es None).

def scan_plan_files(docs_dir: Path) -> list[dict]
    # iterdir() NO recursivo, solo archivos que matchean _PLAN_FILE_RE y
    # pesan <= _MAX_FILE_BYTES. Lee con read_text(encoding="utf-8", errors="replace").
    # Devuelve dicts: {"number": int, "number_str": str, "slug": str, "filename": str,
    #                  "path": Path, **parse_plan_header(...)}
    # (title None → fallback al stem del filename). Si docs_dir no existe → [].

def next_free_number(docs_dir: Path) -> int
    # max de int(m.group(1)) sobre TODOS los archivos no recursivos que matchean
    # _SEQ_PREFIX_RE (planes + checklists + incidentes) + 1. Sin archivos → 1.

def load_ledger(docs_dir: Path) -> dict
    # §4.2. Devuelve el dict "planes" (o {} ante cualquier problema).

def ledger_info_for(number: int, path: Path, ledger: dict) -> dict | None
    # entry = ledger.get(str(number)); None si no hay.
    # Devuelve {"veredicto": ..., "fecha": ..., "doc_drift": bool|None} (§4.2).

def suggest_next_action(estado: str, ledger_info: dict | None, unpushed: bool | None,
                        number_str: str) -> dict
    # Tabla §4.3 LITERAL. Devuelve {"kind","label","command","natural_language"}.

def build_board(docs_dir: Path, unpushed_paths: set[str] | None,
                repo_rel_prefix: str = "Stacky Agents/docs") -> dict
    # Ensambla el contrato §4.4 COMPLETO menos "ok"/"git_available" (los pone la API):
    # - path_rel = f"{repo_rel_prefix}/{filename}" (posix).
    # - unpushed por card: None si unpushed_paths is None; si no, path_rel in unpushed_paths.
    # - duplicate: True para TODAS las cards cuyo number aparece más de una vez.
    # - totals por estado_efectivo + "unpushed" (cards con True) + "duplicados"
    #   (cantidad de NÚMEROS repetidos, no de archivos) + "total".
    # - plans ordenado por (number DESC, filename ASC). generated_at = datetime.now(timezone.utc).isoformat().
    # - docs_dir_found = docs_dir.exists().
```

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan128_plans_board_parser.py`
(todo con `tmp_path`; NUNCA contra el docs/ real; 14 casos):
1. `test_plan_file_re` — acepta `95_PLAN_X.md` y `126_PLAN_Y.md`; rechaza `TOP5_FOO.md`, `25_CHECKLIST_NUEVO_RUNTIME.md` (como plan), `9_PLAN_X.md` (1 dígito).
2. `test_scan_no_recursivo` — un `120_PLAN_A.md` dentro de `tmp/docs/_legacy/` NO aparece.
3. `test_estado_variantes` — los 5 fixtures de §4.1 producen exactamente (estado, veredicto, version, fecha) esperados (parametrizado).
4. `test_estado_trampas` — doc solo con `**Estado del arte (verificado):** X` → SIN_ESTADO; doc solo con `**Estado previo:** CRITICADO v2` → SIN_ESTADO.
5. `test_estado_y_previo_juntos` — doc con `**Estado:** IMPLEMENTADO — …` en línea 3 y `**Estado previo:** CRITICADO…` en línea 4 → IMPLEMENTADO.
6. `test_next_free_number_secuencia_compartida` — con `25_CHECKLIST_X.md` + `126_PLAN_Y.md` → 127; con solo `20_INCIDENTE_Z.md` → 21; dir vacío → 1.
7. `test_duplicados` — dos archivos `110_PLAN_A.md` y `110_PLAN_B.md` → ambos `duplicate=True`, `totals["duplicados"] == 1`.
8. `test_ledger_ok_sin_drift` — entrada APROBADO con `doc_sha256` == sha real → `doc_drift False`; acción = `push` si unpushed True, `ok` si False.
9. `test_ledger_drift` — sha distinto → `doc_drift True` → acción `supervisar` AUNQUE el doc diga IMPLEMENTADO.
10. `test_ledger_sin_sha` — entrada sin `doc_sha256` (real: planes 81-85) → `doc_drift None`, sigue contando como aprobado (fila 1/2).
11. `test_ledger_ausente_o_roto` — sin archivo → `{}`; JSON inválido → `{}`; y `load_ledger` re-lee OK un ledger escrito en UTF-16.
12. `test_acciones_tabla` — parametrizado con las 7 filas de §4.3 (entrada → kind/command exactos).
13. `test_unpushed_none` — `unpushed_paths=None` → cards con `unpushed None` y totals["unpushed"]==0; ledger aprobado cae en fila 2 (`ok`), no en `push`.
14. `test_build_board_orden_y_totales` — 3 planes → orden DESC, totals consistentes, `docs_dir_found`, `generated_at` ISO.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan128_plans_board_parser.py -q`
**Criterio binario:** 14/14 verdes.
**Flag:** no aplica (módulo puro, nadie lo importa aún). **Runtimes:** N/A. **Operador:** ninguno.

### F2 — Enriquecimiento git de solo lectura: `collect_unpushed_docs`

**Objetivo:** saber qué docs de planes tienen commits locales sin pushear, con UNA llamada git batcheada, sin romper jamás.
**Valor:** visibiliza el "push manual pendiente" crónico.

**Archivo a editar:** `Stacky Agents/backend/services/plans_board.py` (mismo módulo).

**Símbolos EXACTOS:**
```python
_GIT_TIMEOUT_SEC = 5

def repo_root() -> Path | None
    # Path(__file__).resolve().parents[3]  (services→backend→"Stacky Agents"→raíz repo).
    # Si (root / ".git") no existe (deploy congelado PyInstaller) → None.

def docs_dir_default() -> Path
    # Path(__file__).resolve().parents[2] / "docs"   ("Stacky Agents"/docs)

def collect_unpushed_docs(root: Path | None) -> set[str] | None
    # None si root es None.
    # subprocess.run(["git", "log", "--name-only", "--pretty=format:",
    #                 "origin/main..HEAD", "--", "Stacky Agents/docs"],
    #                cwd=str(root), capture_output=True, text=True,
    #                encoding="utf-8", errors="replace", timeout=_GIT_TIMEOUT_SEC)
    # returncode != 0 → None. TimeoutExpired / FileNotFoundError / OSError → None.
    # Parse: por línea, line = line.strip(); si empieza y termina con '"' →
    # line = line[1:-1] (git puede C-quotear paths con espacios). Ignorar vacías.
    # Devuelve set de paths tal como los da git (posix, ej. "Stacky Agents/docs/X.md").
```
PROHIBIDO cualquier otro subcomando git. PROHIBIDO `shell=True`.

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan128_plans_board_git.py`
(monkeypatch de `subprocess.run`; 6 casos):
1. salida normal (2 paths, uno repetido en 2 commits) → set de 2.
2. salida con path C-quoteado `"Stacky Agents/docs/X.md"` → set lo contiene SIN comillas.
3. returncode 1 (sin remoto / sin upstream) → None.
4. raise `subprocess.TimeoutExpired` → None; raise `FileNotFoundError` (sin git) → None.
5. `collect_unpushed_docs(None) is None` (root None = deploy congelado sin `.git`).
6. verificación del comando: capturar args del mock y assert de la lista EXACTA de argv (congela el contrato read-only).

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan128_plans_board_git.py -q`
**Criterio binario:** 6/6 verdes.
**Flag:** no aplica aún. **Runtimes:** N/A. **Operador:** ninguno.

### F3 — API Flask: `api/plans_board.py` + cache TTL + registro

**Objetivo:** exponer `/api/plans-board/{health,list,detail/<n>}` gateados por flag, con cache TTL de 15 s.
**Valor:** contrato §4.4 servido; el frontend ya puede montarse encima.

**Archivo a crear:** `Stacky Agents/backend/api/plans_board.py`
```python
from flask import Blueprint, jsonify, request
from config import config

bp = Blueprint("plans_board", __name__, url_prefix="/plans-board")

def _enabled() -> bool:
    return bool(getattr(config, "STACKY_PLANS_BOARD_ENABLED", False))

def _disabled_resp():
    return jsonify({"ok": False, "error": "plans_board_disabled",
                    "message": "El tablero de planes está deshabilitado (STACKY_PLANS_BOARD_ENABLED)."}), 404

@bp.get("/health")
def plans_board_health():
    # [v2 ADICIÓN ARQUITECTO] next_free_number va SIEMPRE, sin gate de flag: cómputo barato
    # (un iterdir(), sin ledger/git) que cierra el anti-colisión aunque el tablero esté OFF.
    from services import plans_board  # import lazy (patrón Plan 109, api/docs.py:224)
    docs_dir = plans_board.docs_dir_default()
    next_n = plans_board.next_free_number(docs_dir) if docs_dir.exists() else None
    return jsonify({"ok": True, "flag_enabled": _enabled(), "next_free_number": next_n})

@bp.get("/list")
def plans_board_list():
    if not _enabled():
        return _disabled_resp()
    from services import plans_board  # import lazy (patrón Plan 109, api/docs.py:224)
    refresh = request.args.get("refresh", "").strip() == "1"
    return jsonify(plans_board.get_board_cached(refresh=refresh))

@bp.get("/detail/<int:number>")
def plans_board_detail(number: int):
    if not _enabled():
        return _disabled_resp()
    from services import plans_board
    payload = plans_board.get_detail(number)
    if payload is None:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404
    return jsonify(payload)
```

**Agregar a `services/plans_board.py` (cache + orquestación):**
```python
_BOARD_TTL_SEC = 15
_BOARD_CACHE: tuple[float, dict] | None = None   # (monotonic_ts, board)

def get_board_cached(refresh: bool = False) -> dict
    # Si no refresh y cache viva (time.monotonic() - ts < _BOARD_TTL_SEC) → copia cacheada.
    # Si no: root = repo_root(); unpushed = collect_unpushed_docs(root);
    #        board = build_board(docs_dir_default(), unpushed)
    #        board["ok"] = True; board["git_available"] = unpushed is not None
    #        guardar en cache y devolver.

def get_detail(number: int) -> dict | None
    # Sobre get_board_cached(): cards con ese number. [] → None.
    # plan = primera card; duplicates = resto; head_excerpt = primeras 60 líneas del
    # archivo (read_text utf-8 errors="replace", splitlines()[:60] unidas con "\n";
    # archivo desaparecido → head_excerpt = "").
```

**Registro (2 líneas en `Stacky Agents/backend/api/__init__.py`, espejo de las de Plan 110):**
```python
from .plans_board import bp as plans_board_bp  # Plan 128 — tablero de evolución de planes
...
api_bp.register_blueprint(plans_board_bp)
```

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan128_plans_board_endpoints.py`
(fixtures `app_flag_off`/`app_flag_on` COPIADAS del patrón real `tests/test_plan87_devops_endpoints.py:6-29`,
cambiando el attr a `STACKY_PLANS_BOARD_ENABLED`; 8 casos):
1. `test_health_200_flag_off` — `/api/plans-board/health` → 200, `flag_enabled False`.
2. `test_health_200_flag_on` — 200, `flag_enabled True`.
3. `test_list_404_flag_off` — 404 + `error == "plans_board_disabled"`.
4. `test_list_200_flag_on` — 200 y el JSON contiene TODAS las claves top-level de §4.4 (`ok`, `generated_at`, `docs_dir_found`, `git_available`, `next_free_number`, `totals`, `plans`).
5. `test_detail_404_not_found` — flag ON + número 99999 → 404 `plan_not_found`.
6. `test_refresh_invalida_cache` — monkeypatch `services.plans_board.build_board` con contador; 2 GET seguidos → 1 build; tercer GET con `?refresh=1` → 2 builds.
7. `test_rutas_sin_doble_prefijo` — sentinela (patrón `test_plan74_routes_registered.py`): el url_map contiene `/api/plans-board/list` y NO contiene `/api/api/plans-board/list`.
8. **[v2]** `test_health_next_free_number_sin_gate` — con flag OFF, `/health` igual trae
   `next_free_number` numérico y correcto (monkeypatch `docs_dir_default` a un `tmp_path`
   fixture con 2-3 archivos `NN_*`); con `docs_dir_default` apuntando a un directorio
   inexistente → `next_free_number is None`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan128_plans_board_endpoints.py -q`
**Criterio binario:** 8/8 verdes.
**Flag:** gating 404 verificado. **Runtimes:** N/A. **Operador:** ninguno.

### F4 — Modelo puro frontend: `src/plansBoard/model.ts`

**Objetivo:** tipos + lógica de filtrado/chips/copiado como funciones puras testeables con vitest (SIN React Testing Library — no está instalada, gotcha Plan 119: tests puros).
**Valor:** la UI de F5 queda sin lógica, solo render.

**Archivo a crear:** `Stacky Agents/frontend/src/plansBoard/model.ts`
```typescript
export type EstadoPlan = "PROPUESTO" | "CRITICADO" | "IMPLEMENTADO"
  | "IMPLEMENTADO_PARCIAL" | "APROBADO" | "SIN_ESTADO";

export interface SuggestedAction { kind: string; label: string;
  command: string | null; natural_language: string; }

export interface PlanCardDto { number: number; number_str: string; slug: string;
  filename: string; path_rel: string; title: string; estado: string;
  estado_raw: string | null; estado_efectivo: EstadoPlan; veredicto: string | null;
  version: string | null; fecha: string | null; duplicate: boolean;
  ledger: { veredicto: string; fecha: string | null; doc_drift: boolean | null } | null;
  unpushed: boolean | null; suggested_action: SuggestedAction; }

export interface BoardDto { ok: boolean; generated_at: string; docs_dir_found: boolean;
  git_available: boolean; next_free_number: number;
  totals: Record<string, number>; plans: PlanCardDto[]; }

export const ESTADO_CHIP: Record<EstadoPlan, { label: string; color: string }> = {
  PROPUESTO:            { label: "Propuesto",     color: "#8b5cf6" },
  CRITICADO:            { label: "Criticado",     color: "#f59e0b" },
  IMPLEMENTADO:         { label: "Implementado",  color: "#3b82f6" },
  IMPLEMENTADO_PARCIAL: { label: "Impl. parcial", color: "#f97316" },
  APROBADO:             { label: "Aprobado",      color: "#22c55e" },
  SIN_ESTADO:           { label: "Sin estado",    color: "#6b7280" },
};

export interface BoardFilters { texto: string; estado: EstadoPlan | "TODOS";
  soloPendientesPush: boolean; soloSinSupervisar: boolean; }

export function estadoChip(card: PlanCardDto): { label: string; color: string }
  // ESTADO_CHIP[card.estado_efectivo] con fallback a SIN_ESTADO si la clave no existe.

export function sinSupervisar(card: PlanCardDto): boolean
  // (estado_efectivo === "IMPLEMENTADO" || === "IMPLEMENTADO_PARCIAL")  — aprobados quedan fuera
  // porque su estado_efectivo ya es "APROBADO".

export function filterPlans(plans: PlanCardDto[], f: BoardFilters): PlanCardDto[]
  // texto: lowercase incluido en number_str, title o slug (los 3 en lowercase).
  // estado: "TODOS" no filtra; si no, igualdad con estado_efectivo.
  // soloPendientesPush: unpushed === true. soloSinSupervisar: sinSupervisar(card).
  // Los filtros se AND-ean. No muta el array.

export function buildCopyPayload(a: SuggestedAction): string
  // a.command ?? a.natural_language  (el botón principal copia esto).
```

**Tests PRIMERO:** `Stacky Agents/frontend/src/plansBoard/model.test.ts` (vitest puro; 9 casos):
1-2. `estadoChip` mapea APROBADO→verde y clave desconocida→SIN_ESTADO.
3. `sinSupervisar` true para IMPLEMENTADO e IMPLEMENTADO_PARCIAL, false para APROBADO/PROPUESTO.
4-7. `filterPlans`: por texto (case-insensitive sobre número/título/slug), por estado, por pendientes push, AND de filtros combinados.
8. `filterPlans` no muta el input (assert deep-equal antes/después).
9. `buildCopyPayload`: con command → command; con command null → natural_language.

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/plansBoard/model.test.ts`
**Criterio binario:** 9/9 verdes.
**Flag:** N/A (módulo puro no importado aún). **Runtimes:** N/A. **Operador:** ninguno.

### F5 — Página + tab gateado: `PlansBoardPage` + wiring App.tsx + endpoints.ts

**Objetivo:** el tab "🧭 Planes" visible SOLO con flag ON, con tabla, hero de contadores, filtros, drawer de detalle y copiado al portapapeles.
**Valor:** la feature completa usable el día uno.

**Archivos a crear (2):**
1. `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx`
2. `Stacky Agents/frontend/src/pages/PlansBoardPage.module.css`

**Archivos a editar (2):**
1. `Stacky Agents/frontend/src/api/endpoints.ts` — agregar namespace (replicando el ESTILO
   de los namespaces existentes en ese archivo, ej. el de DevOps):
   ```typescript
   export const PlansBoard = {
     health: () => fetch("/api/plans-board/health").then((r) => r.json()),
     list: (refresh = false) =>
       fetch(`/api/plans-board/list${refresh ? "?refresh=1" : ""}`).then((r) => {
         if (!r.ok) throw new Error(`plans-board list ${r.status}`);
         return r.json();
       }),
     detail: (n: number) =>
       fetch(`/api/plans-board/detail/${n}`).then((r) => {
         if (!r.ok) throw new Error(`plans-board detail ${r.status}`);
         return r.json();
       }),
   };
   ```
2. `Stacky Agents/frontend/src/App.tsx` — 6 toques quirúrgicos, espejo EXACTO del patrón
   DevOps/Migrador (buscar por contenido, las líneas citadas son de HEAD actual):
   - Union `Tab` (línea ~30): agregar `| "planes"`.
   - `TAB_PATHS` (líneas ~31-46): agregar `planes: "/planes",`.
   - Estado (tras línea ~62): `// Plan 128: tab Planes visible solo si el flag está ON en el backend` + `const [planesEnabled, setPlanesEnabled] = useState(false);`
   - Effect de montaje (tras el fetch de `/api/devops/health`, líneas ~90-94):
     ```typescript
     // Plan 128: comprobar si el tablero de planes está habilitado (flag backend)
     fetch("/api/plans-board/health")
       .then((r) => r.json())
       .then((d: { flag_enabled?: boolean }) => setPlanesEnabled(d.flag_enabled === true))
       .catch(() => setPlanesEnabled(false));
     ```
   - Effect de fallback (líneas ~132-139): agregar rama `else if (tab === "planes" && !planesEnabled) selectTab("team");` y `planesEnabled` al array de deps.
   - Nav + render (líneas ~223-253): bloque de botón espejo del de devops con `🧭 Planes`,
     y `{tab === "planes" && planesEnabled && <PlansBoardPage />} {/* Plan 128 */}` + import arriba.

**Contenido EXACTO de `PlansBoardPage.tsx` (estructura; estilos en el .module.css):**
- Carga: `useEffect` → `PlansBoard.list()`; estados `loading` (spinner de texto "Cargando planes…"), `error` (banner con mensaje y botón "Reintentar" que llama `PlansBoard.list(true)`), `data`.
- **Hero** (fila de tarjetas): "Próximo Nº libre: {next_free_number}" (destacado, es el
  anti-colisión), un chip por estado con su total (colores de `ESTADO_CHIP`), "⬆️ Sin push:
  {totals.unpushed}" (solo si `git_available`), "⚠️ Duplicados: {totals.duplicados}" (solo si > 0),
  y botón "↻ Refrescar" → `PlansBoard.list(true)`.
- **Filtros**: input de texto (placeholder "Buscar por número, título o slug…"), select de
  estado (TODOS + los 6), checkbox "Solo pendientes de push" (deshabilitado con tooltip
  "sin datos de git" si `!git_available`), checkbox "Solo sin supervisar". Todo aplicado
  con `filterPlans` de F4 en un `useMemo`.
- **Tabla** (orden ya viene DESC del backend): columnas `Nº` (badge rojo "DUP" si
  `duplicate`), `Título` (title, con `version`/`fecha` en subtexto gris), `Estado` (chip
  `estadoChip`), `Juez` (veredicto o "—"), `Supervisión` (`ledger` null → "—"; `doc_drift
  true` → "⚠️ drift"; si no → "✅ {ledger.veredicto}"), `Push` (`unpushed null` → "—";
  true → "⬆️ pendiente"; false → "✓"), `Acción sugerida` (label + botón 📋 que copia
  `buildCopyPayload(...)` y botón 💬 que copia SIEMPRE `natural_language`).
- **Copiado**: `navigator.clipboard.writeText(texto)` dentro de try/catch; éxito → estado
  local "Copiado ✓" 1500 ms sobre el botón; fallo → "No se pudo copiar" (sin romper).
- **Drawer de detalle** (click en fila): `PlansBoard.detail(number)`; muestra metadata
  completa, cards duplicadas si las hay, `head_excerpt` en `<pre>` con scroll, y los dos
  botones de copiado grandes. Cierre con ✕ y con Escape.
- **Empty state** (flag ON, `plans` vacío o `!docs_dir_found`): texto "No se encontraron
  docs de planes en este deploy" (pasa en el build congelado sin docs/ — degradación §3.3).
- La página NO tiene ningún botón que ejecute acciones. Solo lectura + copiar.

**Tests:** los de F4 cubren la lógica; el componente NO se testea con render (sin RTL).
**Verificación de fase (binaria):**
- `cd "Stacky Agents/frontend" && npx tsc --noEmit` → exit 0.
- `cd "Stacky Agents/frontend" && npx vitest run src/plansBoard/model.test.ts` → verde.
- Greps de wiring (los 2 devuelven ≥1 match):
  `grep -n "planes" "Stacky Agents/frontend/src/App.tsx"` (union, paths, state, health, fallback, nav, render);
  `grep -n "PlansBoard" "Stacky Agents/frontend/src/api/endpoints.ts"`.
- Verificación manual del operador (flag ON, backend corriendo) queda declarada como
  pendiente-de-operador, patrón disclosure Plan 111 (los tests de componente están
  bloqueados por falta de RTL/jsdom en el repo).
**Flag:** tab invisible y sin fetchs extra con OFF (`/health` responde `flag_enabled false` y no se monta nada más). **Runtimes:** idéntico en los 3; el botón 💬 es el fallback de paridad (§3.3). **Operador:** opt-in (default off).

### F6 — Cierre: ratchet + no-regresión + estado del doc

**Objetivo:** registrar los tests nuevos en el ratchet y dejar el plan auditable.

**Archivos a editar:**
1. `Stacky Agents/backend/scripts/run_harness_tests.ps1` y `.sh` — agregar los 4 archivos
   `test_plan128_*.py` como bloque nuevo, espejo del bloque de cualquier plan reciente
   (un `pytest` por archivo, mismo estilo de las líneas de Plan 80).
2. Este doc (`128_PLAN_TABLERO_EVOLUCION_PLANES.md`): al terminar, actualizar la línea
   `**Estado:**` a `IMPLEMENTADO — <fecha> (F0..F6 …)` (regla de la casa: estado sincronizado en el doc).

**Comandos de cierre (todos deben quedar verdes, corridos por archivo):**
```
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan128_plans_board_flag.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan128_plans_board_parser.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan128_plans_board_git.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan128_plans_board_endpoints.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
cd "Stacky Agents/frontend" && npx vitest run src/plansBoard/model.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio binario:** los 7 comandos verdes (con la única excepción documentada del
centinela `test_default_known_only_for_curated` SI YA fallaba en HEAD — anotarlo en el
reporte con el conteo antes/después idéntico).
**Runtimes:** N/A. **Operador:** ninguno.

---

## 6. Riesgos y mitigaciones

- **R1 — Encabezados heterogéneos** (docs viejos sin `**Estado:**`): el parser NO adivina;
  clasifica `SIN_ESTADO` (gris) y la acción sugerida lo dice explícito (fila 7). El board
  muestra el gap en vez de esconderlo.
  - **[v2] Excepción documentada:** un archivo `NN_PLAN_*.md` que pese más de
    `_MAX_FILE_BYTES` (2MB) es la ÚNICA condición donde el board SÍ esconde el gap — el
    archivo no genera card. Se acepta esta excepción tal cual porque ningún doc real del
    repo se acerca a ese tamaño (los más grandes rondan decenas de KB) y complejizar el
    contrato para un caso con probabilidad ~0 no vale la pena; si algún día ocurre, el
    síntoma es "un plan no aparece en el tablero" y se resuelve partiendo el doc.
- **R2 — Git ausente o lento** (deploy congelado, repo sin remoto): timeout 5 s y
  `None` → columna Push "—", `git_available false`, checkbox deshabilitado. Jamás 500.
- **R3 — Ledger con encoding/schema variable** (UTF-16 posible, entradas sin `doc_sha256`):
  lectura tolerante §4.2 con tests dedicados (F1 casos 10-11).
- **R4 — WIP ajeno en `config.py`/`harness_flags.py`/`App.tsx` al implementar** (sesiones
  concurrentes son la norma en este repo): staging quirúrgico por hunk, prohibido
  stash/reset/checkout (guardarraíl §3.8); `git status` al final para verificar que el WIP
  ajeno sigue intacto.
- **R5 — Colisión de número (YA MATERIALIZADA):** este doc nació como 127 y otra sesión
  propuso SU 127 (`e922b78f`, reuso IA local) el mismo día → renumerado a 128. Quien
  implemente debe re-verificar que `128_PLAN_TABLERO_EVOLUCION_PLANES.md` sigue siendo el
  único `128_*`. El board resuelve esta clase de bug para siempre (hero "Próximo Nº libre"
  + badge DUP).
- **R6 — Performance con ~140 docs**: solo se leen 4000 chars por archivo + sha256 solo de
  docs en ledger + 1 git call + TTL 15 s. Si `docs/` creciera 10×, el diseño aguanta sin
  cambios (escaneo sigue O(archivos), no O(bytes)).
- **R7 — Falso "Al día"**: `unpushed` compara contra `origin/main`; si el operador trabaja
  contra otro remoto/rama, el dato podría ser optimista. Mitigación: el comando git está
  congelado y testeado (F2 caso 6) y la columna es informativa, nunca dispara nada.

## 7. Fuera de scope (explícito)

- Ejecutar el pipeline desde la UI (lanzar skills/agentes/git) — violaría HITL.
- Editar docs o el ledger desde la UI.
- Kanban drag & drop, agrupación por series (122-126), notificaciones, historial temporal.
- Enriquecer el ledger con campos nuevos o escribir memoria.
- Integración con DocsPage/grafo documental (posible plan futuro: abrir el doc en el tab
  Docs; hoy el drawer con `head_excerpt` cubre la necesidad sin acoplarse).
- Auth/RBAC/multiusuario.

## 8. Glosario (para modelos menores)

- **Pipeline de planes**: ciclo de evolución de Stacky: `proponer-plan-stacky` (crea el doc
  `NN_PLAN_*.md`) → `criticar-y-mejorar-plan` (juez adversarial, reescribe a v2) →
  `implementar-plan-stacky` (TDD fase por fase) → `supervisar-implementaciones-planes`
  (audita contra el código y marca APROBADO en el ledger). Son skills de Claude Code.
- **Ledger de supervisión**: `docs/_supervision/ledger.json` — registro versionado de
  planes auditados, con veredicto y sha256 del doc al momento de aprobar.
- **Drift**: el doc del plan cambió DESPUÉS de que el supervisor lo aprobó (sha actual ≠
  `doc_sha256` del ledger) → la aprobación ya no cubre lo que dice el doc.
- **Push manual pendiente**: regla de la casa — el pipeline commitea localmente pero NUNCA
  pushea; el operador pushea a mano cuando decide.
- **Flag del arnés**: toggle declarado en `harness_flags.py` (FlagSpec), leído desde
  `config.py`, editable desde el HarnessFlagsPanel de la UI (registry dinámico).
- **3 runtimes**: Codex CLI, Claude Code CLI y GitHub Copilot Pro — los motores que
  ejecutan agentes de Stacky. Este plan es un panel: se ve igual con cualquiera.
- **HITL (human-in-the-loop)**: el operador decide y ejecuta; Stacky informa y prepara.
- **Staging quirúrgico**: commitear SOLO los hunks/archivos propios cuando el working tree
  tiene WIP de otras sesiones.
- **venv del repo**: `Stacky Agents/backend/.venv` (Python 3.13) — los tests backend se
  corren con `.venv\Scripts\python.exe -m pytest`, por archivo.
- **Ratchet**: `scripts/run_harness_tests.ps1/.sh` — lista acumulativa de suites que deben
  quedar verdes; cada plan registra ahí sus tests.

## 9. Orden de implementación

1. F0 (flag + config + help + defaults) — correr también `test_harness_flags.py` ANTES para fotografiar fallos preexistentes.
2. F1 (parser puro + 14 tests).
3. F2 (git read-only + 6 tests).
4. F3 (API + cache + registro + 7 tests).
5. F4 (modelo TS puro + 9 tests).
6. F5 (página + wiring App.tsx/endpoints.ts + tsc).
7. F6 (ratchet + estado del doc + corrida completa de cierre).

## 10. Definición de Hecho (DoD)

- [x] `STACKY_PLANS_BOARD_ENABLED` declarada (bool, UI-editable, sin default explícito,
      categoría `observabilidad_notif`), en `config.py`, help y `harness_defaults.env`.
- [x] Los 4 archivos de test backend (`flag`, `parser`, `git`, `endpoints`) verdes con los
      comandos EXACTOS de §5 (34 casos en total: 6+14+6+8 — 6/25/6/8 ejecuciones reales con parametrize).
- [x] `model.test.ts` verde (9 casos, 10 ejecuciones con sub-asserts) y `npx tsc --noEmit` exit 0.
- [x] Con flag OFF: `/api/plans-board/list` y `/detail` → 404 `plans_board_disabled`;
      `/health` → 200 `flag_enabled false` Y `next_free_number` numérico (v2, sin gate);
      tab "Planes" ausente del nav; `test_harness_flags.py` sin regresión vs. la foto previa a F0 (53/53 ambas veces).
- [x] Con flag ON sobre fixtures: estados, veredictos, drift, duplicados, `next_free_number`
      y las 7 acciones de §4.3 EXACTOS (KPI-1/KPI-2) — cubierto por F1 (25 ejecuciones).
- [x] El backend del feature no escribe NADA: único subprocess = el `git log` congelado de
      F2 (verificado: `grep -n "subprocess" "Stacky Agents/backend/services/plans_board.py"`
      solo matchea `collect_unpushed_docs`, y `grep -n "subprocess\|open(.*w" "Stacky Agents/backend/api/plans_board.py"` → 0 matches).
- [x] Ratchet ps1/sh actualizados con los 4 archivos `test_plan128_*`.
- [x] Encabezado `**Estado:**` de este doc actualizado al cerrar.
- [x] `git status` final: WIP ajeno intacto (staging quirúrgico verificado; el worktree
      `wt-plan-128` arrancó 100% limpio y cada fase se staged con pathspec explícito, nunca
      `git add -A`).
