# Plan 256 — Intake sin pérdida: ningún artefacto rechazado sin razón

**Estado:** CRITICADO v2
**Versión:** v1 -> v2 (juez adversarial + arquitecto; toda la evidencia del v1 re-medida contra el repo y los logs reales)
**Serie:** Robustez desde los logs (253-258). Plan **#4 por retorno**.
**Fuente:** auditoría de ~16 MB de logs reales de `Stacky Agents/backend/data/logs/` (14 archivos, `2026-07-12` .. `2026-07-26`).

> **El v1 apuntaba al lugar equivocado.** Decía que el watcher rechaza artefactos *sin decir por qué* y que el mensaje termina en dos puntos y nada. **Se midió y es falso: 0 de 26 mensajes tienen la razón vacía.** La razón está completa, es accionable y es siempre la misma. El bug real es otro y es peor: la razón existe hace **11 días**, dice exactamente qué hacer, y **nadie la vio nunca** porque solo vive en un log de 4 MB y en un dict de RAM que se borra en cada arranque. Este plan v2 ataca **eso**.

---

## 0. CHANGELOG v1 -> v2

- **C1 (BLOQUEANTE, premisa falsa)** — el KPI "9 de 9 artefactos en cuarentena con razón **vacía**" está **desmentido por medición**: son **0 de 26**. El extracto del v1 salió de una firma agregada **truncada** (la misma que normaliza `epic-28`→`epic-N` y corta con `...`). Se reemplazó por el extracto crudo íntegro y se rehízo la tabla de KPI. **F1 del v1 (garantizar razón no vacía) se eliminó: corregía un bug que no existe.**
- **C2 (BLOQUEANTE)** — `result.code` **no existe**. La dataclass es `IntakeResult` y el campo es `reason_code` (`artifact_intake.py:42`). El v1 escribía `result.code or "UNKNOWN"` → `AttributeError` en el camino caliente del intake. Corregido a `result.reason_code`.
- **C3 (BLOQUEANTE)** — el v1 mezclaba **dos vocabularios** de códigos (`reason_code` del intake vs `_TERMINAL_CREATE_ERRORS` del watcher). Se define **un solo enum `cause_code`** con tabla de origen explícita (§4.1).
- **C4 (BLOQUEANTE)** — la clave compuesta `f"{path}|{cause_code}"` **no resuelve** el caso que dice resolver, y con la evidencia real es **cero-efecto** (la causa nunca cambia: 25/25 son la misma). Eliminada; reemplazada por el sidecar en disco + `retry` explícito.
- **C5 (BLOQUEANTE, duplicación)** — el endpoint `GET /api/diag/intake-quarantine` **ya existe** (`api/diag.py:193`, plan 149 F7) y `quarantine_retry` **ya existe** como `clear_quarantine` (`output_watcher.py:880`, plan 149 F5, consumido por `api/tickets.py:4058`). El v1 los reinventaba con otro nombre. F3/F4 ahora **extienden** lo existente.
- **C6 (BLOQUEANTE)** — `discard` escribía `status='discarded_by_operator'` **dentro del JSON del agente**: contradice "nunca perder el original", cambia el mtime (re-dispara el watcher) y **es imposible** en el caso real (el archivo está vacío: no hay JSON que parsear). Movido al sidecar.
- **C7 (IMPORTANTE)** — la cuarentena en RAM se evapora en cada arranque (los 26 relogueos **son** eso). Resuelto por **[ADICIÓN ARQUITECTO]** §4.2.
- **C8 (IMPORTANTE, trabajo fantasma)** — "el watcher debe ignorar los `*.orig` o se genera un loop": **falso, medido**. El glob es literal (`output_watcher.py:405-406`) y `all_files` solo suma `analisis-funcional.md`/`plan-de-pruebas.md` (`:413-418`). Degradado a test de regresión, ya no es trabajo.
- **C9 (MENOR)** — el riesgo de `with_suffix` se midió en py3.13.5: **funciona**. Igual se usa la forma explícita `Path(str(p) + ".orig")` por legibilidad, no por miedo.
- **C10 (IMPORTANTE)** — el v1 decía "3 flags nuevas" e introducía **4**, y ninguna fase daba de alta la flag en la UI. Ahora son **3 exactas**, con **F5 dedicada** al alta en los 3 lugares obligatorios.
- **C11 (IMPORTANTE)** — path traversal sin símbolo. Fijado: `AdoOutputWatcher.outputs_dir` (`output_watcher.py:154`, property lazy con override) / `_outputs_dir()` (`:101`), con `resolve()` + comparación case-insensitive Windows.
- **C12 (IMPORTANTE)** — `test_ninguna_accion_es_automatica` por grep del módulo era gameable y frágil (un comentario lo rompe). Reemplazado por un test **de comportamiento** (§F4).
- **C13 (MENOR)** — el KPI `no such table: tickets` es del plan 253. Movido a "Dependencias", ya no es meta propia.
- **C14 (MENOR)** — `confirm_token` tiene **0 implementaciones** hoy. Declarado como **dependencia dura del plan 253 F5**; este plan **no** lo reimplementa.
- **C15 (MENOR)** — falta la huella de regresión. F1 agrega la firma a `docs/sistema/error_fingerprints.json`.
- **C16 (MENOR, deuda ajena detectada)** — `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` está declarada `env_only=True` (`harness_flags.py:952`) pero **sí** es atributo de Config (`config.py:1813`) y se lee como tal (`api/diag.py:201`). No se toca (es del 149), pero las flags nuevas de este plan declaran `env_only=False` **porque son atributos de Config**.
- **C17 (hallazgo nuevo del juez)** — el artefacto `epic-28/rf-028-filtros-cp-fecha-compromiso-pago-agenda/pending-task.json` está **vacío y atascado desde el 2026-07-16**: 11 días, 25 relogueos, cero visibilidad. Es el caso de prueba real del plan y ahora es un KPI.
- **[ADICIÓN ARQUITECTO]** — sidecar de cuarentena en disco (§4.2): sobrevive al reinicio, da el marcador de descarte **sin tocar** el artefacto, y aporta la señal de invalidación que el mtime del JSON no puede dar.

---

## 1. Objetivo y KPI

Que ningún artefacto de agente quede atascado **invisible**. La razón ya existe: hay que **persistirla, mostrarla y darle un botón**.

| KPI | Hoy (**medido 2026-07-26**) | Meta |
|---|---|---|
| Artefactos en cuarentena con razón vacía | **0 de 26** (el v1 decía 9 de 9: **era un artefacto de la firma truncada**) | 0 (mantener; test de invariante) |
| **Días que un artefacto puede estar atascado sin que el operador se entere** | **11** (`epic-28/rf-028`, 07-16 → 07-26) | **0** — visible en la UI en el primer scan |
| Entradas de cuarentena que **sobreviven** a un reinicio del backend | **0** (dict en RAM) | **100 %** (sidecar en disco) |
| Relogueos del mismo artefacto atascado | **25** en 11 días (≈1 por arranque) | **1** por causa, con contador en el sidecar |
| Cuarentena visible en la UI | **No** (`GET /api/diag/intake-quarantine` existe desde el plan 149 **sin un solo consumidor de frontend**) | **Sí**, con razón, antigüedad y acción |
| Originales destruidos por la reparación automática in place | Indeterminado (no hay copia) | **0** (`.orig` obligatorio, o se aborta) |
| Artefactos en cuarentena sin forma de reintentar desde la UI | **Todos** | **0** |

**Dependencias (KPI ajenos, no son meta de este plan):** `no such table: tickets` durante el scan y los rounds perdidos por lock → **plan 253**. Acá solo se verifica que no reaparezcan.

---

## 2. Evidencia real (anclaje anti-alucinación) — **re-medida**

### E1 — El mensaje, crudo y completo

Comando exacto de la medición (Git Bash, sobre `Stacky Agents/backend/data/logs/`):

```
grep -h "pending-task con fallo terminal" *.log | wc -l         -> 26
grep -h "intake rechaz" *.log | wc -l                           -> 25
grep -hE "artefacto: *$" *.log | wc -l                          ->  0   <-- razón vacía: NINGUNA
grep -ho "intake rechaz.* el artefacto: .*" *.log | sed 's/.*artefacto: //' | sort | uniq -c
   -> 25  el archivo está vacío o solo tiene espacios; el agente no llegó a escribir el
          contenido. Reescribí el pending-task.json completo.
```

Línea cruda íntegra (no truncada):

```
2026-07-16 13:34:24 ERROR [stacky.output_watcher] output_watcher mode_a: pending-task con
fallo terminal (se omite hasta corregir el archivo/carpeta) en
C:\desarrollo\GIT\RS\RSPACIFICO\Agentes\outputs\epic-28\rf-028-filtros-cp-fecha-compromiso-
pago-agenda\pending-task.json: intake rechazó el artefacto: el archivo está vacío o solo
tiene espacios; el agente no llegó a escribir el contenido. Reescribí el pending-task.json
completo.
```

**La razón está, es completa y dice exactamente qué hacer.** El v1 leyó una firma agregada que corta la línea (la misma que convierte `epic-28` en `epic-N`) y concluyó que el mensaje estaba vacío. **Lección para el implementador: nunca derives un bug de una firma normalizada; abrí el log crudo.**

Serie temporal (del v1, **confirmada exacta** con `grep -c` por archivo):

| Log | Ocurrencias |
|---|---|
| `stacky-2026-07-16.log` | 3 |
| `stacky-2026-07-17.log` | 8 |
| `stacky-2026-07-18.log` | 2 |
| `stacky-2026-07-19.log` | 1 |
| `stacky-2026-07-20.log` | 1 |
| `stacky-2026-07-21.log` | 1 |
| `stacky-2026-07-23.log` | 1 |
| `stacky-2026-07-25.log` | 5 |
| `stacky-2026-07-26.log` | 4 |
| **Total** | **26** |

Y también **1 vez** en `Stacky Agents/DeployStackyAgents/data/logs/stacky-2026-07-20.log`: pasa en el binario del operador.

Desglose de las 26 por causa: **25** `intake rechazó el artefacto: ...vacío...` + **1** `HTTP 400: TASK_GATE_BLOCKED`.

### E2 — El bug REAL: el invariante ya se cumple, la visibilidad no existe

El contrato que el v1 quería agregar **ya está garantizado por construcción**. Todos los retornos `ok=False` de `artifact_intake.py` pueblan `errors`:

| Línea | Camino | `errors` |
|---|---|---|
| `artifact_intake.py:86-89` | `comment_html` vacío | `["comment.html vacío"]` |
| `artifact_intake.py:151-154` | `JSONDecodeError` | `[hint]` (siempre no vacío; `hint` sale de un dict con 3 claves cubiertas) |
| `artifact_intake.py:156-161` | raíz no-dict | `["el JSON raíz debe ser un objeto, ..."]` |
| `artifact_intake.py:169-176` | schema / anti-ordinal | `errors` (el `if errors:` garantiza ≥ 1) |

No existe ningún camino `ok=False, errors=[]`. **Los 6 casos de F0 del v1 que decían "hoy falla" hoy pasan**: habrían sido 6 verdes vacíos, el peor resultado posible de un TDD.

Lo que sí es cierto, y es el plan:

1. El artefacto lleva **11 días** atascado. `2026-07-16 13:34:24` → `2026-07-26`.
2. La única superficie es un log de 4 MB. `GET /api/diag/intake-quarantine` (`api/diag.py:193`) devuelve el dato desde el plan 149 y **no tiene ni un consumidor de frontend** (`grep -rn "intake-quarantine" frontend/src` → 0 hits).
3. Se reloguea ~1 vez por arranque porque `_SEEN_TERMINAL_PENDING` (`output_watcher.py:826`) es un `dict` de módulo: **el reinicio borra la cuarentena**.

### E3 — La cuarentena, tal cual está hoy

`Stacky Agents/backend/services/output_watcher.py:850-877` (verificado literal):

```python
def _quarantine_pending_once(pt_file: Path, reason: str) -> bool:
    key = str(pt_file)
    try:
        mtime_ns = pt_file.stat().st_mtime_ns
    except OSError:
        mtime_ns = -1
    if _SEEN_TERMINAL_PENDING.get(key) == mtime_ns:
        return False  # ya logueado para este contenido
    _SEEN_TERMINAL_PENDING[key] = mtime_ns
    _QUARANTINE_REASON[key] = reason
    logger.error(
        "output_watcher mode_a: pending-task con fallo terminal (se omite hasta "
        "corregir el archivo/carpeta) en %s: %s",
        pt_file, reason,
    )
    return True


def quarantine_snapshot() -> dict[str, dict]:
    """Plan 149 F4/F7 — Snapshot read-only de la cuarentena para diag/board.
    path -> {reason, mtime_ns}."""
    return {
        k: {"reason": _QUARANTINE_REASON.get(k, ""), "mtime_ns": v}
        for k, v in _SEEN_TERMINAL_PENDING.items()
    }
```

El diseño `path + mtime` es correcto **para fallos de contenido**. No cubre dos casos:
- **Corregir la carpeta no cambia el mtime del JSON** (el mensaje mismo dice "archivo/carpeta"). Lo confirma otra firma, 25 ocurrencias: `corrigiendo epic dir mal nombrado source_epic=N effective_ado=N`.
- **Reiniciar el backend borra el registro**, así que el "una sola vez" dura lo que dura el proceso.

**La clave compuesta `path|cause_code` que proponía el v1 no arregla ninguno de los dos**: si el operador renombra la carpeta, el `cause_code` sigue siendo el mismo (`INTAKE_EMPTY`) y el path también ⇒ clave idéntica ⇒ sigue en cuarentena. Y en los datos reales la causa es **siempre la misma** (25/25), así que la clave compuesta sería literalmente cero-efecto. Lo que hace falta es un **estado en disco** y un **retry explícito**, no una clave más larga.

### E4 — Lo que ya existe y hay que REUSAR (no reinventar)

| Símbolo / endpoint | Ubicación | Estado |
|---|---|---|
| `quarantine_snapshot()` | `output_watcher.py:871` | Existe. Consumido por `api/diag.py:204`. |
| `clear_quarantine(pt_file)` | `output_watcher.py:880` | **Existe** (plan 149 F5). Es el `quarantine_retry` del v1. Consumido por `api/tickets.py:4058`. Su docstring documenta el gotcha de la clave en Windows. |
| `_pending_is_quarantined(pt_file)` | `output_watcher.py:893` | Existe. Es el gate del scan (`:1004`). |
| `GET /api/diag/intake-quarantine` | `api/diag.py:193` | **Existe** (plan 149 F7). Devuelve `{enabled, count, items:[{path, reason, mtime_ns}]}`. **Sin consumidor de frontend.** |
| `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` | `config.py:1813` + `harness_flags.py:948` | Existe, default ON, categoría `fiabilidad_ciclo_vida`. **Gobierna F3/F4-retry: no hace falta flag nueva para eso.** |
| `_outputs_dir()` / `AdoOutputWatcher.outputs_dir` | `output_watcher.py:101` / `:154` | Existe. Property lazy con override (`self._outputs_dir_override`). Es el símbolo para la validación anti-traversal. |

### E5 — Otros caminos por los que el trabajo se pierde

```
4 WARNING [stacky_agents.api.tickets] pending-task: no se pudo parsear
  C:\desarrollo\GIT\RS\RSPACIFICO\Agentes\outputs\epic-N\rf-N-filtro...
5 WARNING [stacky_agents.api.tickets] artifact_rescue falló (no crítico)
2 ERROR [stacky.output_watcher] output_watcher: error procesando ...: (sqlite3.OperationalError) no such table: tickets
```

- El mismo artefacto falla **por dos rutas distintas**: el watcher lo pone en cuarentena y `api/tickets.py` no lo puede parsear. Dos módulos, un solo artefacto perdido.
- `artifact_rescue falló (no crítico)` — el rescate, que es la última red de seguridad, falla y se etiqueta "no crítico". **Es del plan 255**; acá solo se cita.
- `no such table: tickets` es del **plan 253** (carrera de arranque). Se menciona porque su efecto es perder el artefacto de ese round.

---

## 3. Principios y guardarraíles (obligatorios)

- **Human-in-the-loop, en el corazón del plan:** Stacky **no** decide descartar el trabajo de un agente. Lo pone en cuarentena, explica por qué, y el operador reintenta o descarta. F4 agrega el descarte y es la **única** pieza con efecto irreversible, detrás de flag OFF + `confirm_token`.
- **Nunca perder el original.** Ningún artefacto se borra ni se sobreescribe sin copia. La reparación (`output_watcher.py:1041-1054`) hoy **reescribe el archivo del operador in place**: F2 le agrega copia previa y **aborta** si no puede hacerla. **El descarte no toca el artefacto: escribe en el sidecar.**
- **Mono-operador sin auth.** No hay roles ni 403 real; `current_user` es un header sin validar. Los endpoints nuevos **no** implementan RBAC (sería teatro). El único candado real es `confirm_token` + la flag OFF.
- **Paridad de 3 runtimes, con fallback:** el `output_watcher` consume artefactos de **disco**, y los 3 runtimes (Codex CLI, Claude Code CLI, Copilot Pro) escriben el mismo `pending-task.json` en `Agentes/outputs/`. Un solo cambio cubre a los 3; **no hay código por runtime en este plan**. Fallback: con las 3 flags en OFF el comportamiento es **byte-idéntico** al de hoy (§F5).
- **Cero trabajo extra al operador:** hoy tiene que leer un log de 4 MB para enterarse de que algo está atascado hace 11 días. Después lo ve en una tarjeta. Es **menos** trabajo.
- **No degradar:** ninguna fase cambia el criterio de aceptación de un artefacto. Un artefacto que hoy entra, sigue entrando.
- **Backward-compatible:** el formato de `pending-task.json` no cambia. El endpoint existente **conserva** sus claves actuales y solo **agrega** campos.
- **Reusar lo existente:** `clear_quarantine`, `quarantine_snapshot`, `GET /api/diag/intake-quarantine`, `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED`, `confirm_token` (del 253 F5). Prohibido crear un gemelo de cualquiera de estos.
- **Flags default ON** salvo la de descarte (excepción dura: acción irreversible desde la UI).

---

## 4. Contratos congelados

### 4.1 — `cause_code`: **un solo** enum, con origen explícito

El v1 mezclaba dos vocabularios. Este es el único válido. **Fuente de verdad: `backend/services/output_watcher.py`, constante nueva `_CAUSE_CODES`.**

| `cause_code` | De dónde sale exactamente | `retryable` |
|---|---|---|
| `INTAKE_EMPTY` | `IntakeResult.reason_code == "empty"` (`artifact_intake.py:136` vía `classify_json_failure`) | `True` |
| `INTAKE_TRUNCATED` | `reason_code == "truncated"` | `True` |
| `INTAKE_MALFORMED` | `reason_code == "malformed"` (`:136` y `:160`) | `True` |
| `INTAKE_SCHEMA` | `reason_code == "schema"` (`:172`) | `True` |
| `INTAKE_ANTI_ORDINAL` | `reason_code == "anti_ordinal"` (`:172`) | `True` |
| `WATCHER_UNREADABLE` | `OSError` al leer el archivo (`output_watcher.py:1016-1017`) | `True` |
| `WATCHER_HTTP_TERMINAL` | HTTP en `_TERMINAL_CREATE_HTTP` o error en `_TERMINAL_CREATE_ERRORS` (`output_watcher.py:837-847`) | `True` |
| `ORIG_BACKUP_FAILED` | F2: no se pudo escribir el `.orig` | **`False`** (hay que arreglar el disco primero) |
| `UNKNOWN` | Cualquier otro `_quarantine_pending_once` sin `cause_code` explícito | `True` |

**Regla dura:** `_TERMINAL_CREATE_ERRORS` (`PENDING_TASK_SCHEMA_INVALID`, etc.) es el vocabulario del **endpoint de creación**, NO del intake. Nunca lo uses como `cause_code` de un rechazo del intake — colapsan todos en `WATCHER_HTTP_TERMINAL` y el detalle va en `reason`.

**Función de mapeo exacta** (nueva, en `output_watcher.py`, junto a `_TERMINAL_CREATE_ERRORS`):

```python
# Plan 256 F1 — mapeo ÚNICO reason_code(artifact_intake) -> cause_code(cuarentena).
_INTAKE_REASON_TO_CAUSE: dict[str, str] = {
    "empty": "INTAKE_EMPTY",
    "truncated": "INTAKE_TRUNCATED",
    "malformed": "INTAKE_MALFORMED",
    "schema": "INTAKE_SCHEMA",
    "anti_ordinal": "INTAKE_ANTI_ORDINAL",
}
_NON_RETRYABLE_CAUSES: frozenset[str] = frozenset({"ORIG_BACKUP_FAILED"})


def _cause_from_intake(result) -> str:
    """reason_code -> cause_code. OJO: el campo es `reason_code`, NO `code`."""
    return _INTAKE_REASON_TO_CAUSE.get(getattr(result, "reason_code", None) or "", "UNKNOWN")
```

### 4.2 — [ADICIÓN ARQUITECTO] Sidecar de cuarentena en disco

**Problema que resuelve (tres de una):**
1. La cuarentena vive en RAM y se borra en cada arranque ⇒ 25 relogueos y una tarjeta de UI que se vacía sola (C7).
2. El descarte necesitaba escribir dentro del JSON del agente, lo que viola "nunca perder el original" y es **imposible** cuando el JSON está vacío (C6).
3. El mtime del JSON no puede señalar "el operador arregló la carpeta" (C4).

**Contrato congelado.** Archivo `<mismo_dir>/<nombre>.quarantine.json`, junto al artefacto. Para `pending-task.json` ⇒ `pending-task.json.quarantine.json`.

```json
{
  "schema": 1,
  "artifact": "pending-task.json",
  "cause_code": "INTAKE_EMPTY",
  "reason": "intake rechazó el artefacto: el archivo está vacío o solo tiene espacios; el agente no llegó a escribir el contenido. Reescribí el pending-task.json completo.",
  "first_seen": "2026-07-16T13:34:24Z",
  "last_seen": "2026-07-26T20:52:11Z",
  "occurrences": 25,
  "artifact_mtime_ns": 1785000000000000000,
  "discarded_at": null,
  "discarded_by": null
}
```

**Reglas duras del sidecar (todas con test):**
- **Nunca** toca el artefacto. Es un archivo aparte. Si el sidecar no se puede escribir, se loguea `warning` y **la cuarentena sigue funcionando en RAM** (degradación limpia, nunca se pierde el gate anti-loop).
- `first_seen` se preserva entre arranques; `occurrences` se incrementa; `last_seen` se pisa.
- El sidecar **no** cuenta como artefacto: el glob del scan es literal `pending-task.json` (`output_watcher.py:405-406`), medido — `fnmatch("pending-task.json.quarantine.json", "pending-task.json")` = `False`.
- El sidecar **no** entra en `all_files` para el `max_mtime` del epic dir: esa lista solo suma `analisis-funcional.md` y `plan-de-pruebas.md` (`output_watcher.py:413-418`), medido. **Escribirlo no re-dispara el scan.**
- `discarded_at != null` ⇒ el watcher **omite** el artefacto sin reloguear y sin contarlo como error. Es el marcador de descarte, fuera del JSON del agente.
- Al arrancar, la cuarentena **se rehidrata** desde los sidecars encontrados bajo `outputs_dir` (lazy, en el primer `scan_once`, no en el import del módulo).
- Si el `artifact_mtime_ns` del sidecar **no coincide** con el mtime real del artefacto ⇒ el operador lo editó ⇒ **se sale de cuarentena solo** (mismo criterio que hoy, pero ahora persistente).

---

## 5. Fases

> **Orden no negociable:** F1 (persistencia + `cause_code`) → F2 (`.orig`) → F3 (visible) → F4 (acciones) → F5 (flags en la UI). F3 sin F1 muestra una tarjeta que se vacía en cada arranque.

### F0 — Tests: congelar lo que ya funciona, reproducir lo que sí está roto

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan256_intake_razon.py`
**Registrar en:** `HARNESS_TEST_FILES` de `Stacky Agents/backend/scripts/run_harness_tests.sh` (**es el único archivo con esa lista**; lo exigen `tests/test_harness_ratchet_meta.py` y `tests/test_plan76_ratchet_byteidentical.py:83`).

**Casos exactos, con su estado esperado HOY:**

| # | Test | Hoy | Qué prueba |
|---|---|---|---|
| 1 | `test_ok_false_siempre_trae_errors` | **VERDE** (caracterización) | Recorre los 4 caminos `ok=False` de `artifact_intake` (`""`, `"{"`, `"[]"`, `'{"foo":1}'`) y asserta `len(result.errors) >= 1`. **Congela el invariante que el v1 creía roto.** Si algún día se rompe, este test lo caza. |
| 2 | `test_reason_code_es_el_nombre_del_campo` | **VERDE** (anti-regresión de C2) | `assert hasattr(IntakeResult, "__dataclass_fields__") and "reason_code" in IntakeResult.__dataclass_fields__ and "code" not in IntakeResult.__dataclass_fields__`. Impide que alguien vuelva a escribir `result.code`. |
| 3 | `test_cause_from_intake_mapea_los_5_reason_codes` | **ROJO** (no existe `_cause_from_intake`) | Los 5 valores de `reason_code` mapean a los 5 `INTAKE_*`; `None` y un valor desconocido mapean a `"UNKNOWN"`. |
| 4 | `test_cuarentena_sobrevive_al_reinicio` | **ROJO** | Cuarentena un artefacto, **limpia los dos dicts de módulo** (`_SEEN_TERMINAL_PENDING.clear()`, `_QUARANTINE_REASON.clear()`) simulando el reinicio, rehidrata, y `quarantine_snapshot()` **vuelve a tener** la entrada con su `reason` y su `first_seen` original. |
| 5 | `test_sidecar_no_toca_el_artefacto` | **ROJO** | Hash SHA-256 y `st_mtime_ns` del artefacto **idénticos** antes y después de cuarentenarlo. |
| 6 | `test_sidecar_no_es_recogido_por_el_glob` | **ROJO** hasta F1, luego regresión | En un epic dir con `pending-task.json` + su sidecar, `list(epic_dir.glob("*/" + PENDING_TASK_FILENAME))` devuelve **exactamente 1** ruta. |
| 7 | `test_occurrences_incrementa_y_first_seen_se_preserva` | **ROJO** | Dos ciclos de cuarentena con reinicio simulado en el medio: `occurrences == 2`, `first_seen` inalterado, `last_seen` mayor. |
| 8 | `test_quarantine_snapshot_nunca_devuelve_reason_vacia` | **VERDE** (invariante) | Sobre todo lo que entre por `_quarantine_pending_once`, `reason.strip() != ""`. |

**Comando exacto (PowerShell o Git Bash, ruta absoluta):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan256_intake_razon.py -v
```
El intérprete es **`backend\.venv`** (py **3.13.5**, verificado). Correr **por archivo**: la suite completa del backend tiene contaminación cross-file conocida.

**Criterio binario de F0:** los 8 tests existen; **3, 4, 5, 6, 7 fallan** (5 rojos) y **1, 2, 8 pasan** (3 verdes). Si el 1, el 2 o el 8 fallan, **parar**: el diagnóstico de este plan cambió y hay que re-criticarlo.

**Flag:** ninguna. **Trabajo del operador: ninguno.**

---

### F1 — Cuarentena persistente + `cause_code` unificado

**Objetivo:** que la cuarentena sobreviva al reinicio y que cada entrada tenga un código de causa del enum único.

**Archivo a editar:** `Stacky Agents/backend/services/output_watcher.py`.
**Símbolos nuevos:** `_INTAKE_REASON_TO_CAUSE`, `_NON_RETRYABLE_CAUSES`, `_cause_from_intake`, `_sidecar_path`, `_write_sidecar`, `_read_sidecar`, `_rehydrate_quarantine`.
**Imports a agregar arriba del módulo (explícitos, nada de import local salvo el `json as _json` que ya existe dentro de la función):** `from datetime import datetime, timezone`.

**1) Nueva firma de `_quarantine_pending_once` (`output_watcher.py:850`), backward-compatible:**

```python
def _quarantine_pending_once(pt_file: Path, reason: str, *,
                             cause_code: str = "UNKNOWN") -> bool:
    """Loguea UNA vez (por path+mtime) un pending-task.json con fallo terminal y
    lo registra en la cuarentena. Devuelve True si logueó (primera vez para este
    contenido), False si ya estaba en cuarentena.

    Plan 256 F1 — `cause_code` es un valor del enum único (§4.1) y se persiste en
    un sidecar `<artefacto>.quarantine.json` para que la cuarentena sobreviva al
    reinicio del backend. La CLAVE en memoria sigue siendo `str(pt_file)`: NO se
    compone con el cause_code (ver plan 256 C4 — no resolvía nada y rompía
    `clear_quarantine`).
    """
    key = str(pt_file)                      # SIN CAMBIOS — clear_quarantine depende de esto
    try:
        mtime_ns = pt_file.stat().st_mtime_ns
    except OSError:
        mtime_ns = -1
    if _SEEN_TERMINAL_PENDING.get(key) == mtime_ns:
        return False
    _SEEN_TERMINAL_PENDING[key] = mtime_ns
    _QUARANTINE_REASON[key] = reason
    _QUARANTINE_CAUSE[key] = cause_code     # dict nuevo, mismo key que los otros dos
    if _sidecar_enabled():
        _write_sidecar(pt_file, reason=reason, cause_code=cause_code, mtime_ns=mtime_ns)
    logger.error(
        "output_watcher mode_a: pending-task con fallo terminal (se omite hasta "
        "corregir el archivo/carpeta) en %s: %s",
        pt_file, reason,
    )
    return True
```

> **La clave NO cambia.** `clear_quarantine` (`:880`) documenta explícitamente que deriva la clave igual que `_quarantine_pending_once` y que divergir deja el `pop` en un no-op silencioso en Windows. Cambiarla habría roto `api/tickets.py:4058` en silencio.

**2) Call-site del intake (`output_watcher.py:1034-1040`) — el fix de C2:**

```python
            if not result.ok:
                _quarantine_pending_once(
                    pt_file,
                    "intake rechazó el artefacto: " + "; ".join(result.errors),
                    cause_code=_cause_from_intake(result),   # <-- reason_code, NO .code
                )
                skipped += 1
                continue
```

**3) El otro call-site del intake (`output_watcher.py:1017`):**
```python
                _quarantine_pending_once(pt_file, f"no legible: {exc}",
                                         cause_code="WATCHER_UNREADABLE")
```

**4) `quarantine_snapshot()` (`:871`) — aditivo, sin romper consumidores:**

```python
def quarantine_snapshot() -> dict[str, dict]:
    """Plan 149 F4/F7 — Snapshot read-only de la cuarentena para diag/board.
    path -> {reason, mtime_ns}. Plan 256 F1 — agrega cause_code / retryable /
    first_seen / occurrences / has_original_backup (aditivo: las claves viejas
    NO cambian de nombre ni de tipo)."""
```

**5) Rehidratación.** `_rehydrate_quarantine(outputs_dir)` se llama **una sola vez**, dentro del primer `scan_once` de la instancia (guard `self._quarantine_rehydrated: bool`), **nunca en el import del módulo** (importar `output_watcher` no debe tocar disco; hay tests que lo importan). Recorre `outputs_dir.glob("*/*/" + PENDING_TASK_FILENAME + ".quarantine.json")` y repuebla los 3 dicts. Un sidecar ilegible o con `schema != 1` se ignora con `logger.warning` y **no** aborta el scan.

**6) Huella de regresión (C15).** Agregar a `Stacky Agents/docs/sistema/error_fingerprints.json` la firma `output_watcher mode_a: pending-task con fallo terminal` con su causa conocida y el puntero a este plan. Consumidor: `backend/services/error_fingerprints.py`.

**Tests:** casos 3, 4, 5, 6, 7 de F0 a verde; 1, 2, 8 **siguen** verdes.
**Criterio binario:** `pytest tests/test_plan256_intake_razon.py -v` ⇒ **8 verdes**. Y, por archivo, siguen verdes: `tests/test_plan149_intake_quarantine_surface.py` (usa `_quarantine_pending_once` con la firma vieja en `:33` y `:197` — **la firma nueva es keyword-only con default, así que no se toca ese test**).

**Flag:** `STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED`, **default ON**. OFF ⇒ `_sidecar_enabled()` es `False` ⇒ comportamiento **byte-idéntico** al de hoy (solo RAM). Alta en la UI: **F5**.
**Impacto por runtime:** los 3 igual (el watcher es común a Codex / Claude Code / Copilot Pro).
**Trabajo del operador: ninguno.**

---

### F2 — Nunca perder el original

**Objetivo:** que la reparación automática no destruya el artefacto del agente.

**Archivo a editar:** `Stacky Agents/backend/services/output_watcher.py:1041-1054`.

Hoy reescribe el archivo del operador in place, y si falla solo loguea un `warning`:

```python
1041            if result.repaired and isinstance(result.normalized, dict):
1044                try:
1045                    pt_file.write_text(
1046                        _json.dumps(result.normalized, ensure_ascii=False, indent=2),
1047                        encoding="utf-8",
1048                    )
...
1053                except OSError:
1054                    logger.warning("intake: no se pudo reescribir %s", pt_file, exc_info=True)
```

**Cambio exacto:**

```python
            if result.repaired and isinstance(result.normalized, dict):
                # Plan 256 F2 — el original del agente se preserva ANTES de
                # reescribir. Idempotente: si el .orig ya existe, NO se pisa
                # (si no, el segundo pase guardaría como "original" la versión
                # ya reparada).
                if _preserve_original_enabled():
                    orig = Path(str(pt_file) + ".orig")   # explícito; ver plan 256 C9
                    try:
                        if not orig.exists():
                            orig.write_text(raw_text, encoding="utf-8")
                    except OSError:
                        logger.error(
                            "intake: NO se pudo preservar el original de %s — se ABORTA "
                            "la reparación para no destruir el artefacto",
                            pt_file, exc_info=True)
                        _quarantine_pending_once(
                            pt_file,
                            "reparación abortada: no se pudo escribir la copia .orig",
                            cause_code="ORIG_BACKUP_FAILED")
                        skipped += 1
                        continue
                # ... el write_text existente, sin cambios ...
```

**Regla dura:** si la copia falla, **se aborta la reparación**. Es preferible un artefacto en cuarentena con razón clara a un artefacto del agente destruido.

**Lo que NO hay que hacer (corrección del v1):** el v1 declaraba obligatorio "filtrar los `*.orig` del glob del scan o se genera un loop". **Se midió y el riesgo no existe**: el glob es literal `PENDING_TASK_FILENAME` (`:405-406`), y `all_files` para el `max_mtime` solo suma `analisis-funcional.md` y `plan-de-pruebas.md` (`:413-418`). Un `.orig` **no** se recoge y **no** mueve el mtime del epic dir. Se conserva el test como **regresión** (barato), pero **no se toca el glob**.

**Nombre del archivo, medido en py3.13.5:** tanto `p.with_suffix(p.suffix + ".orig")` como `Path(str(p) + ".orig")` dan `pending-task.json.orig`. Se usa la segunda por ser inmune a nombres con puntos internos.

**Tests** (en `test_plan256_intake_razon.py`):
- `test_reparacion_preserva_el_original` — el `.orig` tiene **el `raw_text` crudo**, byte a byte.
- `test_reparacion_no_pisa_el_orig_en_el_segundo_pase`.
- `test_reparacion_abortada_si_falla_el_orig` — `monkeypatch` de `Path.write_text` para que tire `OSError` **solo** para el `.orig`; el artefacto original queda **intacto** (hash idéntico) y entra en cuarentena con `cause_code == "ORIG_BACKUP_FAILED"`.
- `test_orig_backup_failed_no_es_retryable` — `retryable is False` para esa causa.
- `test_glob_del_scan_ignora_los_orig` (regresión, verde de entrada).

**Criterio binario:** 5 verdes ⇒ el archivo va de 8 a **13 verdes**.

**Flag:** `STACKY_INTAKE_PRESERVE_ORIGINAL_ENABLED`, **default ON**. No es excepción dura: escribir una copia de respaldo no es destructivo, no bypasea revisión humana, no tiene prerequisito no garantizado y no reduce la seguridad. OFF ⇒ camino actual exacto.
**Impacto por runtime:** los 3 igual.
**Trabajo del operador: ninguno.**

---

### F3 — La cuarentena, visible (**extender**, no duplicar)

**Objetivo:** que el operador vea en la UI que hay algo atascado, con la razón que **ya existe** y **hace cuánto**.

**Archivos a editar:**
1. `Stacky Agents/backend/api/diag.py:193-207` — **el endpoint `GET /api/diag/intake-quarantine` que YA EXISTE.** Prohibido crear `GET /api/diag/intake/quarantine`.
2. Frontend, panel de diagnóstico existente — tarjeta **"Artefactos en cuarentena"**.

**Contrato del endpoint (aditivo; las 3 claves viejas `path`/`reason`/`mtime_ns` **se conservan** tal cual):**

```json
{
  "enabled": true,
  "count": 1,
  "items": [{
    "path": "C:\\desarrollo\\GIT\\RS\\RSPACIFICO\\Agentes\\outputs\\epic-28\\rf-028-filtros-cp-fecha-compromiso-pago-agenda\\pending-task.json",
    "reason": "intake rechazó el artefacto: el archivo está vacío o solo tiene espacios; el agente no llegó a escribir el contenido. Reescribí el pending-task.json completo.",
    "mtime_ns": 1785000000000000000,

    "file_name": "pending-task.json",
    "cause_code": "INTAKE_EMPTY",
    "first_seen": "2026-07-16T13:34:24Z",
    "age_days": 10,
    "occurrences": 25,
    "has_original_backup": false,
    "discarded": false,
    "retryable": true
  }]
}
```

- `retryable` = `cause_code not in _NON_RETRYABLE_CAUSES` (hoy: `False` solo para `ORIG_BACKUP_FAILED`).
- `age_days` = días enteros desde `first_seen`. **Es el campo que hace visible el hallazgo C17.**
- Ítems con `discarded: true` **no** se listan por default; se listan con `?include_discarded=1`.

**Tarjeta en la UI:** título, contador, y por ítem: nombre de archivo, `age_days` destacado si ≥ 1 (*"atascado hace 10 días"*), la razón **completa en texto plano** (no truncada — es literalmente el bug que originó este plan), y los dos botones de F4. Si `count == 0` la tarjeta **no se renderiza**.

**Tests backend:** `Stacky Agents/backend/tests/test_plan256_quarantine_api.py` (registrar en `HARNESS_TEST_FILES`):
- `test_endpoint_vacio_devuelve_count_cero`.
- `test_endpoint_conserva_las_claves_del_plan_149` — `path`, `reason`, `mtime_ns` presentes con el mismo tipo. **Anti-regresión de contrato.**
- `test_endpoint_expone_cause_code_y_age_days`.
- `test_endpoint_nunca_devuelve_reason_vacia`.
- `test_retryable_false_solo_para_orig_backup_failed`.
- `test_descartados_ocultos_salvo_include_discarded`.
- `test_flag_surface_off_devuelve_enabled_false` — con `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` en OFF (la flag del 149, **no** una nueva).

**Tests frontend:** `Stacky Agents/frontend/src/pages/__tests__/plan256Quarantine.test.ts`.
**Restricción dura de la casa:** `@testing-library/react` y `jsdom` **no están instalados** ⇒ **prohibido testear el componente React**. Los tests son de un **módulo puro `.ts`** — extraer la lógica a `frontend/src/incidents/quarantineModel.ts` con funciones puras: `shouldRenderCard(count)`, `formatAge(firstSeenIso, nowIso)`, `sortByAgeDesc(items)`.
- `test_no_renderiza_si_count_cero`.
- `test_formatea_la_antiguedad_en_dias`.
- `test_ordena_por_antiguedad_descendente`.

**Criterio binario:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan256_quarantine_api.py -v
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/pages/__tests__/plan256Quarantine.test.ts
```
7 backend + 3 frontend verdes. **Vitest por archivo y con ruta concreta** (contaminación cross-file conocida; un glob `src/**/...` puede no expandirse en PowerShell).

**Flag:** **ninguna nueva.** Reusa `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` (`config.py:1813`, default ON, categoría `fiabilidad_ciclo_vida`).
**Impacto por runtime:** la UI es común; los artefactos de los 3 runtimes caen en la misma cuarentena.
**Trabajo del operador: ninguno** — información nueva donde ya mira.

---

### F4 — Reintentar o descartar, con el operador decidiendo

**Objetivo:** cerrar el ciclo desde la UI, sin que Stacky decida nada por su cuenta.

**Archivos a editar:**
1. `Stacky Agents/backend/api/diag.py` — `POST /api/diag/intake-quarantine/retry` y `POST /api/diag/intake-quarantine/discard` (mismo prefijo que el `GET` existente).
2. `Stacky Agents/backend/services/output_watcher.py` — **una** función nueva.

**Reuso obligatorio:** el `retry` **NO** crea un símbolo nuevo. `clear_quarantine(pt_file)` (`output_watcher.py:880`) ya hace exactamente eso y ya documenta el gotcha de la clave en Windows. Lo único que se agrega es el borrado del sidecar:

```python
def quarantine_discard(pt_file: Path, *, operator: str) -> dict:
    """Plan 256 F4 — marca el artefacto como descartado por el operador.

    NO borra ni modifica el artefacto: escribe `discarded_at`/`discarded_by` en el
    SIDECAR (`<artefacto>.quarantine.json`). El trabajo del agente queda intacto en
    disco. El watcher omite los artefactos con `discarded_at != null`.
    Devuelve {'ok', 'path', 'sidecar'}.
    """
```

**Contrato HITL, no negociable:**
- `retry` es **no destructivo** (solo saca la entrada de la cuarentena para que el próximo scan reintente) → un clic, sin confirmación, sin token.
- `discard` **no borra ni modifica el artefacto**. Aun así exige `confirm_token`, y la UI dice literal: *"El artefacto queda intacto en disco. Solo se marca como descartado y el watcher deja de reintentarlo."*
- **`confirm_token` es del plan 253 F5** (`backend/services/confirm_token.py`, `issue_token(action, payload, ttl_s=120)` / `consume_token(action, token)`). Hoy tiene **0 implementaciones** en el repo. **Prohibido reimplementarlo acá.** Si el 253 F5 no está mergeado al implementar esta fase: **F4-discard se posterga**; F4-retry se puede hacer igual (no usa token).
- **Prohibido cualquier automatismo.** Stacky nunca reintenta ni descarta por su cuenta.

**Validación anti-traversal (símbolo exacto, C11).** El `path` viene del cliente:

```python
def _assert_under_outputs(raw_path: str) -> Path:
    """400 si el path no cae bajo el outputs_dir del watcher vivo."""
    from services.output_watcher import get_watcher   # instancia viva: respeta el override
    base = get_watcher().outputs_dir.resolve()        # property lazy, output_watcher.py:154
    p = Path(raw_path).resolve()
    # Windows: case-insensitive y con el separador normalizado por resolve().
    if os.path.normcase(str(p)) != os.path.normcase(str(base)) and \
       not os.path.normcase(str(p)).startswith(os.path.normcase(str(base)) + os.sep):
        abort(400, "path fuera de outputs_dir")
    return p
```
- Se usa la **property de la instancia viva** (`outputs_dir`, `:154`), no `_outputs_dir()` a secas: la property respeta `self._outputs_dir_override`, que es lo que usan los tests y un proyecto con override.
- `resolve()` colapsa `..`, symlinks y `8.3`; `os.path.normcase` cubre el case-insensitive de Windows; el `+ os.sep` evita que `C:\outputs-evil` pase como hijo de `C:\outputs`.

**Casos borde:**
- `retry` de un path que ya no existe en disco: `ok=True, was_quarantined=<bool>`; se limpian entrada y sidecar.
- `retry` es **idempotente**: reintentar algo que no está en cuarentena devuelve `ok=True`.
- `discard` sobre un directorio de solo lectura (no se puede escribir el sidecar): falla con mensaje claro y la entrada **queda** en cuarentena (no se pierde el ítem).
- `retry` cuando la causa es de carpeta: el reintento va a fallar otra vez. La UI lo dice en el tooltip: *"reintenta la validación; no corrige el artefacto"*.
- `discard` de un artefacto ya descartado: idempotente, `discarded_at` no se pisa.

**Tests** (en `test_plan256_quarantine_api.py`):
- `test_retry_reusa_clear_quarantine` — `monkeypatch` de `output_watcher.clear_quarantine`; el endpoint **lo llama**. Prueba el reuso, no una copia.
- `test_retry_no_modifica_el_archivo` — hash SHA-256 idéntico antes y después.
- `test_retry_es_idempotente`.
- `test_discard_sin_token_devuelve_409`.
- `test_discard_no_toca_el_artefacto` — hash **y** `st_mtime_ns` idénticos; el marcador está en el sidecar.
- `test_discard_marca_el_sidecar_y_el_watcher_lo_omite`.
- `test_discard_con_sidecar_no_escribible_mantiene_la_entrada`.
- `test_path_fuera_de_outputs_dir_devuelve_400` — probar `..\\..\\Windows\\win.ini`, un path absoluto ajeno, y `<outputs_dir>-evil\\x.json`.
- `test_ninguna_accion_es_automatica` — **reemplaza al grep del v1 (C12), que era gameable y lo rompía un comentario.** Test **de comportamiento**: `monkeypatch` de `clear_quarantine` y `quarantine_discard` con espías que registran llamadas; se corre un `scan_once()` completo sobre un epic dir con un artefacto en cuarentena; **assert: 0 llamadas a ambos espías**.

**Criterio binario:** 9 verdes ⇒ `test_plan256_quarantine_api.py` cierra en **16 verdes** (7 de F3 + 9 de F4).

**Flags:**
- `retry`: **ninguna nueva**; va bajo `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` (la del 149).
- `discard`: `STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED`, **default OFF**, **excepción dura: acción irreversible desde la UI** (el marcador de descarte no se revierte por UI; hay que borrar el sidecar a mano).

**Impacto por runtime:** los 3 igual.
**Trabajo del operador:** opt-in explícito solo para el descarte; el reintento es un clic disponible por default.

---

### F5 — Alta de las flags en la UI (fase obligatoria, no un paso suelto)

> El v1 dejaba esto como el ítem 7 de una lista al final. **Un atributo en `config.py` NO alcanza para que la flag aparezca en la UI**: el panel se alimenta de `FLAG_REGISTRY` en `services/harness_flags.py`.

**Son 3 flags, exactamente** (el v1 decía 3 y listaba 4 — C10). Todas con el prefijo de la casa `STACKY_`:

| Flag | Fase | Default | Excepción dura |
|---|---|---|---|
| `STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED` | F1 | **ON** | no |
| `STACKY_INTAKE_PRESERVE_ORIGINAL_ENABLED` | F2 | **ON** | no |
| `STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED` | F4 | **OFF** | **sí — acción irreversible desde la UI** |

**Los 4 lugares obligatorios, en este orden. Saltear cualquiera deja la flag invisible o el harness rojo:**

1. **`Stacky Agents/backend/config.py`** — atributo, con el idioma **exacto** de la casa (**no existe ningún `_env_bool` en este repo**):
   ```python
   STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED: bool = os.getenv(
       "STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED", "true"
   ).lower() in ("1", "true", "yes")
   STACKY_INTAKE_PRESERVE_ORIGINAL_ENABLED: bool = os.getenv(
       "STACKY_INTAKE_PRESERVE_ORIGINAL_ENABLED", "true"
   ).lower() in ("1", "true", "yes")
   STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED: bool = os.getenv(
       "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED", "false"
   ).lower() in ("1", "true", "yes")
   ```
   El **default efectivo** es el segundo argumento de `os.getenv`, no el `default=` del `FlagSpec`. Tienen que coincidir.
   Los consumidores leen la **instancia**: `from config import config` y después `config.STACKY_...` (o `getattr(config.config, "...", True)` como hace `api/diag.py:201`). **Leer el módulo en vez de la instancia devuelve el default y mata el branch OFF.**

2. **`Stacky Agents/backend/services/harness_flags.py`** — un `FlagSpec` por flag en `FLAG_REGISTRY`, modelado sobre el hermano del plan 149 (`:948`):
   ```python
   FlagSpec(
       key="STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED",
       type="bool",
       label="Cuarentena de intake persistente en disco",
       description=(
           "Plan 256 — Si ON, cada artefacto en cuarentena deja un sidecar "
           "<artefacto>.quarantine.json con la causa y la antigüedad, y la cuarentena "
           "sobrevive al reinicio del backend. Nunca modifica el artefacto. "
           "OFF = solo en memoria (comportamiento legacy)."
       ),
       group="global",
       env_only=False,   # SÍ es atributo de Config (ver plan 256 C16)
       default=True,
   ),
   ```
   **`env_only=False` es obligatorio** porque las tres son atributos de `Config`. (`env_only=True` significa "no existe como atributo de Config"; la flag del 149 lo tiene mal declarado — es deuda ajena, no se toca.)

3. **`_CATEGORY_KEYS` en `services/harness_flags.py:120`** — agregar las 3 keys a **`"fiabilidad_ciclo_vida"`**, que es la categoría **ya existente** donde vive `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` (verificado con `categorize()`). **Prohibido crear una categoría nueva.** Sin esto, `test_every_registry_flag_is_categorized` se pone rojo a propósito (plan 63).

4. **`_CURATED_DEFAULTS_ON` en `Stacky Agents/backend/tests/test_harness_flags.py:467`** — agregar las **2** flags con `default=True` (sidecar y preserve-original). **No** agregar la de discard (`default=False`). Sin esto, `test_default_known_only_for_curated` se pone rojo.

**No tocar `deployment/harness_defaults.env` a mano** — se regenera con `deployment/export_harness_defaults.py`. Si el ratchet de ese archivo ya estaba rojo por deuda ajena, **no lo arregles en este plan**.

**Tests:** `Stacky Agents/backend/tests/test_plan256_flags.py` (registrar en `HARNESS_TEST_FILES`), modelado sobre `tests/test_plan149_flags.py`:
- `test_las_3_flags_estan_en_el_registry` — por `key`, en `FLAG_REGISTRY`.
- `test_las_3_flags_estan_categorizadas` — `categorize(k) == "fiabilidad_ciclo_vida"` para las 3.
- `test_defaults_declarados_coinciden_con_config` — el `default=` del `FlagSpec` coincide con el default de `os.getenv` en `config.py`.
- `test_solo_discard_nace_off`.

**Criterio binario:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan256_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -v
```
4 verdes en el archivo nuevo, y **`test_harness_flags.py` sin regresiones**.
**Nota anti-falso-rojo:** `tests/test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes**. No son de este plan. Validá tu entrada aparte y no lo uses como gate.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cambiar la clave de cuarentena rompe `clear_quarantine` y `api/tickets.py:4058` en silencio | **La clave NO cambia** (sigue `str(pt_file)`). El v1 la componía con el `cause_code`; se descartó (C4). |
| El sidecar se procesa como artefacto y genera un loop | **Medido: imposible.** El glob es literal (`:405-406`) y el sidecar no entra en `all_files` del `max_mtime` (`:413-418`). Test de regresión igual (F0 caso 6). |
| Escribir el sidecar cambia el mtime del **directorio** y re-dispara el scan del epic | El watcher cachea por `max_mtime` de **archivos** (`pending-task.json` + los 2 hermanos `.md`), no del directorio. Verificado en `:409-418`. |
| El `.orig` del segundo pase guarda la versión ya reparada como "original" | Guard `if not orig.exists()`, con test dedicado. |
| Los `.orig` y los sidecars acumulan basura en la carpeta del operador | Uno por artefacto. Se documenta en el README operativo. **No se agrega purga automática**: borrar cosas del operador sin pedir es exactamente lo que este plan evita. |
| El sidecar no se puede escribir (permisos, disco lleno) | Degradación limpia: `logger.warning` + la cuarentena sigue en RAM. **Nunca** se pierde el gate anti-loop. |
| Sidecar corrupto o de un `schema` futuro | Se ignora con `warning`, no aborta el scan. `schema: 1` es obligatorio. |
| `confirm_token` no está implementado (plan 253 F5) | Dependencia declarada. Si no está al implementar: **F4-discard se posterga**, F4-retry sigue. |
| `retry` da falsa esperanza cuando la causa es de carpeta | La razón ya dice qué corregir. Tooltip: *"reintenta la validación; no corrige el artefacto"*. |
| Path traversal en los endpoints nuevos | `_assert_under_outputs` con `resolve()` + `normcase` + `+ os.sep`, sobre la property de la instancia viva. 3 casos de test. |
| **Volver a diagnosticar desde una firma agregada** | El error que produjo el v1. Regla para el implementador: **abrí el log crudo con `grep -h ... | cat`** antes de afirmar que un mensaje está incompleto. |

---

## 7. Fuera de scope

- Reescribir `artifact_intake.validate_and_normalize`. Su contrato ya informa la causa (medido). Mejorar sus **reglas de validación** es otro trabajo.
- **Averiguar por qué el agente dejó un `pending-task.json` vacío.** Este plan hace visible el síntoma; la causa raíz del agente que no escribe es otro eje.
- La barrera de esquema al principio de `scan_once` → **plan 253 F2** (mismo archivo `output_watcher.py`: **no duplicar ni tocar**).
- El `no such table: tickets` y los locks que hacen perder rounds → **plan 253**.
- El `artifact_rescue falló (no crítico)` y los `except` mudos de `api/tickets.py` → **plan 255** (tarjeta *"Fallos silenciados"*).
- El throttle del volumen de `corrigiendo epic dir mal nombrado` → **plan 257** (tarjeta *"Firmas de log más repetidas"*).
- Salud de ledgers → **plan 258**.
- Cambiar el formato de `pending-task.json`. Backward-compatible o nada.

---

## 8. Glosario

| Término | Significado |
|---|---|
| **`output_watcher`** | Daemon que vigila `Agentes/outputs/` y convierte los artefactos de los agentes en tickets/tasks. `backend/services/output_watcher.py`. |
| **`pending-task.json`** | Artefacto que un agente deja en disco pidiendo que Stacky cree una task. La forma principal en que el trabajo del agente entra al sistema. |
| **Intake** | La validación/normalización que decide si un artefacto entra. `backend/services/artifact_intake.py`. |
| **Cuarentena** | Registro de artefactos con fallo terminal que el watcher omite hasta que algo cambie. Hoy: `_SEEN_TERMINAL_PENDING` + `_QUARANTINE_REASON` (RAM). Con F1: **+ sidecar en disco**. |
| **`reason_code`** | Campo **real** de `IntakeResult` (`artifact_intake.py:42`). Valores: `empty`, `truncated`, `malformed`, `schema`, `anti_ordinal`. **No existe un campo `code`.** |
| **`cause_code`** | Enum **único** de la cuarentena (§4.1). Se deriva de `reason_code` vía `_INTAKE_REASON_TO_CAUSE`. No confundir con `_TERMINAL_CREATE_ERRORS`, que es el vocabulario del endpoint de creación. |
| **Sidecar** | `<artefacto>.quarantine.json`. Estado de cuarentena en disco. **Nunca** modifica el artefacto. |
| **`.orig`** | Copia del artefacto crudo del agente, escrita antes de cualquier reparación automática. |
| **Firma agregada** | Log normalizado (`epic-28`→`epic-N`) y **truncado** que se usa para contar ocurrencias. **Sirve para contar, no para diagnosticar.** Origen del error del v1. |
| **Excepción dura** | Una de las 4 razones para que una flag nazca OFF: bypasea revisión humana, destructiva/irreversible, prerequisito no garantizado, reduce seguridad. |

---

## 9. Orden de implementación

1. **F0** — 8 tests. Verificar el reparto **5 rojos / 3 verdes**. Si el 1, el 2 o el 8 no están verdes, **parar y re-criticar**.
2. **F1** — `cause_code` unificado + sidecar + rehidratación + huella en `error_fingerprints.json`. Verificar que `tests/test_plan149_intake_quarantine_surface.py` siga verde.
3. **Verificación en vivo:** reiniciar el backend y confirmar que `GET /api/diag/intake-quarantine` **sigue mostrando** `epic-28/rf-028` con su `first_seen` de `2026-07-16` y su `occurrences`. Ese es el momento en que el plan demuestra su valor.
4. **F2** — `.orig` + abortar la reparación si la copia falla. **No tocar el glob.**
5. **F3** — extender el endpoint **existente** + tarjeta en el panel de diagnóstico + módulo puro `quarantineModel.ts`.
6. **F4** — `retry` (reusa `clear_quarantine`) y `discard` (sidecar, token del 253, flag OFF).
7. **F5** — alta de las 3 flags en los 4 lugares.
8. Registrar los **3** archivos de test backend nuevos en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh`.

---

## 10. Definición de Hecho (DoD)

- [ ] **F0 arrancó con 5 rojos y 3 verdes**, y los 3 verdes iniciales siguen verdes al final.
- [ ] Ningún `_quarantine_pending_once` puede registrar una `reason` vacía (invariante con test) — y se documentó que **ya se cumplía**: este plan lo **congela**, no lo arregla.
- [ ] `cause_code` sale **siempre** del enum de §4.1, derivado de `result.reason_code`. **`grep -rn "result\.code" backend/` = 0 hits.**
- [ ] La clave de cuarentena **sigue siendo** `str(pt_file)`; `clear_quarantine` y `api/tickets.py:4058` siguen funcionando.
- [ ] La cuarentena **sobrevive a un reinicio** del backend (sidecar), con `first_seen` y `occurrences` preservados.
- [ ] El sidecar **nunca** modifica el artefacto (hash + `st_mtime_ns` idénticos, con test).
- [ ] La reparación automática preserva el `.orig` y **aborta** si no puede.
- [ ] `GET /api/diag/intake-quarantine` **conserva** `path`/`reason`/`mtime_ns` y **agrega** `cause_code`, `age_days`, `occurrences`, `retryable`, `discarded`.
- [ ] **No se creó ningún endpoint ni símbolo gemelo**: `grep -rn "intake/quarantine\|quarantine_retry" backend/` = **0 hits**.
- [ ] La tarjeta de cuarentena se ve en la UI, muestra la razón **completa** y la antigüedad, y **no** se renderiza si `count == 0`.
- [ ] `retry` **reusa** `clear_quarantine`, es idempotente y **no** modifica el archivo (verificado por hash).
- [ ] `discard` exige `confirm_token` (del plan 253 F5), **no toca el artefacto**, escribe solo en el sidecar, y está detrás de una flag default OFF.
- [ ] Los endpoints rechazan paths fuera de `outputs_dir` con `400` (3 casos: `..`, absoluto ajeno, prefijo `-evil`).
- [ ] Ni `retry` ni `discard` se invocan desde `scan_once` — verificado **por comportamiento** (espías + un scan real), no por grep.
- [ ] Las **3** flags están en `config.py` + `FLAG_REGISTRY` + `_CATEGORY_KEYS["fiabilidad_ciclo_vida"]`, y las **2** default-ON en `_CURATED_DEFAULTS_ON`.
- [ ] Con las 3 flags en OFF, el comportamiento es **byte-idéntico** al de hoy (test de fallback).
- [ ] Los **3** archivos de test backend nuevos están en `HARNESS_TEST_FILES`.
- [ ] La firma de cuarentena está en `docs/sistema/error_fingerprints.json`.
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**; `test_harness_flags_help.py` tiene 4 rojos ajenos preexistentes que no cuentan).
- [ ] **Cierre real del caso testigo:** `epic-28/rf-028-filtros-cp-fecha-compromiso-pago-agenda/pending-task.json` aparece en la UI con *"atascado hace N días"* y el operador puede reintentarlo o descartarlo sin tocar un log.
