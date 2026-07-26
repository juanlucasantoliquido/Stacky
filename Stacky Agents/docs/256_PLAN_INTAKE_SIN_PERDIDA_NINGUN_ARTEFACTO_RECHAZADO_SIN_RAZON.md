# Plan 256 — Intake sin pérdida: ningún artefacto rechazado sin razón

**Estado:** PROPUESTO v1
**Serie:** Robustez desde los logs (253-258). Plan **#4 por retorno**.
**Fuente:** auditoría de ~16 MB de logs reales de `Stacky Agents/backend/data/logs/`.

> El `output_watcher` es la puerta por donde el trabajo de los agentes entra a Stacky. La auditoría encontró que esa puerta **rechaza artefactos sin decir por qué**: el mensaje de cuarentena termina literalmente en dos puntos y nada. El operador ve *"se omite hasta corregir el archivo/carpeta"* y no tiene forma de saber qué corregir.

---

## 1. Objetivo y KPI

Que ningún artefacto de agente se pierda en silencio ni quede en cuarentena sin una razón **legible y accionable**: razón siempre presente, cuarentena visible en la UI, y un botón para reintentar o descartar con criterio.

| KPI | Hoy (medido) | Meta |
|---|---|---|
| Artefactos en cuarentena con razón **vacía** | **9 de 9** en 07-25/07-26 | **0** |
| `pending-task con fallo terminal` | **26** en 8 días, vivo (07-25=5, 07-26=4) | **0 sin razón**; los que queden, accionables |
| Artefactos en cuarentena permanente por problema de **carpeta** (el mtime del JSON no cambia al corregir) | Indeterminado, estructuralmente posible | **0** (clave de cuarentena incluye la causa) |
| Cuarentena visible en la UI | No (existe `quarantine_snapshot()` sin consumidor visual) | **Sí**, con razón y acción |
| `no such table: tickets` durante el scan | 6 (`07-16`) | **0** (lo cubre el plan 253; acá se verifica) |
| Artefactos que se reprocesan en loop tras fallo | Todos los que fallan por lock | **0** |

---

## 2. Evidencia real (anclaje anti-alucinación)

### E1 — La razón vacía, literal

Firma agregada sobre los 14 logs:

```
26 ERROR [stacky.output_watcher] output_watcher mode_a: pending-task con fallo terminal
   (se omite hasta corregir el archivo/carpeta) en C:\desarrollo\GIT\RS\RS...
```

Serie temporal — **vivo**:

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

Y también **1 vez** en `Stacky Agents/DeployStackyAgents/data/logs/stacky-2026-07-20.log`: pasa en el binario del operador.

Ahora el detalle que importa. Agregando el mensaje **con su razón** sobre los logs de 07-25 y 07-26:

```
9  pending-task con fallo terminal (se omite hasta corregir el archivo/carpeta) en
   C:\desarrollo\GIT\RS\RSPACIFICO\Agentes\outputs\epic-N\rf-N-filtros-cp-fecha-compromiso-pago-agenda\pending-task.json:
   intake rechazó el artefacto:
```

**El mensaje termina en `intake rechazó el artefacto:` y nada más.** Nueve ocurrencias, mismo artefacto, cero información. El operador no puede corregir lo que no sabe que está mal.

### E2 — Por qué la razón sale vacía

`Stacky Agents/backend/services/output_watcher.py:1031-1040`:

```python
1031            result = artifact_intake.validate_and_normalize(
1032                raw=raw_text, kind="pending_task_json", ticket_context=ctx,
1033            )
1034            if not result.ok:
1035                _quarantine_pending_once(
1036                    pt_file,
1037                    "intake rechazó el artefacto: " + "; ".join(result.errors),
1038                )
1039                skipped += 1
1040                continue
```

Cuando `result.ok is False` pero `result.errors` es una **lista vacía**, `"; ".join([])` devuelve `""` y el mensaje queda truncado. **No hay ninguna aserción de que un rechazo traiga al menos un error.** El contrato de `validate_and_normalize` permite `ok=False` con `errors=[]`, y eso es el bug: un rechazo sin motivo es indistinguible de un bug del validador.

El logueo se hace en `output_watcher.py:863-867` (dentro de `_quarantine_pending_once`, def en `output_watcher.py:850`):

```python
863    logger.error(
864        "output_watcher mode_a: pending-task con fallo terminal (se omite hasta "
865        "corregir el archivo/carpeta) en %s: %s",
866        pt_file, reason,
867    )
```

El `logger.error` está bien elegido. El problema es que `reason` viene vacío.

### E3 — La cuarentena por `path + mtime` puede ser permanente

`Stacky Agents/backend/services/output_watcher.py:854-862`:

```python
854    key = str(pt_file)
855    try:
856        mtime_ns = pt_file.stat().st_mtime_ns
857    except OSError:
858        mtime_ns = -1
859    if _SEEN_TERMINAL_PENDING.get(key) == mtime_ns:
860        return False  # ya logueado para este contenido
861    _SEEN_TERMINAL_PENDING[key] = mtime_ns
862    _QUARANTINE_REASON[key] = reason
```

El diseño es correcto **para fallos de contenido**: si el operador edita el JSON, el `mtime` cambia y el artefacto se reintenta. Pero el propio mensaje dice *"corregir el archivo **o la carpeta**"*, y **corregir la carpeta no cambia el mtime del JSON**. Un artefacto rechazado por un problema de nombre de carpeta o de contexto de épica queda en cuarentena **hasta reiniciar el backend**, sin que nada lo indique.

Lo confirma otra firma de los logs, 25 ocurrencias:

```
25 WARNING [stacky.output_watcher] output_watcher mode_a: corrigiendo epic dir mal nombrado
   source_epic=N effective_ado=N reason=ticket_ti...
```

Los nombres de carpeta de épica **sí** son una fuente real de problemas, y son exactamente el caso que la clave por mtime no cubre.

### E4 — La cuarentena ya está expuesta, pero nadie la mira

`Stacky Agents/backend/services/output_watcher.py:871-874`:

```python
871 def quarantine_snapshot() -> dict[str, dict]:
872     """Plan 149 F4/F7 — Snapshot read-only de la cuarentena para diag/board.
873     path -> {reason, mtime_ns}."""
```

La función existe desde el plan 149 y devuelve la razón. **Con razones vacías, un panel que la muestre no sirve de nada.** Primero hay que garantizar la razón (F1) y después hacerla visible (F3). Ese orden no es negociable.

### E5 — Otros caminos por los que el trabajo se pierde

```
4 WARNING [stacky_agents.api.tickets] pending-task: no se pudo parsear
  C:\desarrollo\GIT\RS\RSPACIFICO\Agentes\outputs\epic-N\rf-N-filtro...
5 WARNING [stacky_agents.api.tickets] artifact_rescue falló (no crítico)
2 ERROR [stacky.output_watcher] output_watcher: error procesando ...: (sqlite3.OperationalError) no such table: tickets
```

- El mismo artefacto (`epic-N\rf-N-filtro...`) falla **por dos rutas distintas**: el watcher lo pone en cuarentena y `api/tickets.py` no lo puede parsear. Dos mensajes, dos módulos, un solo artefacto perdido, y ninguno de los dos le dice al operador qué pasa.
- `artifact_rescue falló (no crítico)` — el **rescate** de artefactos, que es la última red de seguridad, falla y se etiqueta como "no crítico". Si el rescate no es crítico, no es una red de seguridad.
- `no such table: tickets` es del plan 253 (carrera de arranque). Se menciona acá porque su efecto es **perder el artefacto de ese round**.

---

## 3. Principios y guardarraíles (obligatorios)

- **Human-in-the-loop, en el corazón del plan:** Stacky **no** decide descartar el trabajo de un agente. Lo pone en cuarentena, explica por qué, y el operador reintenta o descarta. F4 agrega el botón de descarte y es la **única** pieza destructiva, con confirmación.
- **Nunca perder el original.** Ningún artefacto en cuarentena se borra ni se sobreescribe sin copia. La reparación (`result.repaired`, `output_watcher.py:1041-1054`) hoy **reescribe el archivo del operador in place**: F2 le agrega copia previa.
- **Mono-operador sin auth.**
- **Paridad de 3 runtimes:** el `output_watcher` consume artefactos de disco, y los 3 runtimes (Codex CLI, Claude Code CLI, Copilot Pro) escriben en el mismo formato en `Agentes/outputs/`. Un solo cambio los cubre a los 3. No hay código por runtime en este plan.
- **Cero trabajo extra al operador:** hoy el operador ya tiene que adivinar; después va a leer una razón. Es **menos** trabajo, no más.
- **No degradar:** F1 solo agrega información al mensaje. Ningún artefacto que hoy entra bien deja de entrar.
- **Flags default ON** salvo la de descarte destructivo (excepción dura #2).
- **Toda flag configurable desde la UI.**

---

## 4. Fases

### F0 — Test que reproduce la razón vacía

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan256_intake_razon.py`
**Registrar en:** `HARNESS_TEST_FILES` de `Stacky Agents/backend/scripts/run_harness_tests.sh`.

**Casos exactos:**

1. `test_rechazo_sin_errors_produce_razon_no_vacia` — mockear `artifact_intake.validate_and_normalize` para devolver `ok=False, errors=[]`; asserta que la razón de cuarentena **no** es `""` ni termina en `": "`. **Hoy falla.**
2. `test_rechazo_sin_errors_se_loguea_como_bug_del_validador` — el mismo caso deja un log de nivel `error` que dice explícitamente que el validador rechazó sin motivo. Un rechazo sin causa **es un bug**, no un dato. **Hoy falla.**
3. `test_razon_incluye_el_kind_y_el_path` — la razón siempre nombra el `kind` (`pending_task_json`) y el nombre del archivo.
4. `test_quarantine_key_incluye_la_causa` — dos rechazos del mismo path con causas distintas producen **dos** entradas de cuarentena, no una. **Hoy falla** (la clave es solo `path`).
5. `test_quarantine_snapshot_nunca_devuelve_reason_vacia` — invariante global sobre `quarantine_snapshot()`. **Hoy falla.**
6. `test_validate_and_normalize_ok_false_exige_errors` — aserción defensiva sobre el contrato de `artifact_intake`: si devuelve `ok=False`, `errors` tiene ≥ 1 elemento.

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan256_intake_razon.py -v
```

**Criterio binario:** 6 tests existen; 1, 2, 4, 5, 6 **fallan** antes de F1.

**Flag:** ninguna. **Trabajo del operador: ninguno.**

---

### F1 — Razón obligatoria, siempre

**Objetivo:** que sea **imposible** poner un artefacto en cuarentena sin decir por qué.

**Archivos a editar:**
1. `Stacky Agents/backend/services/output_watcher.py` — `_quarantine_pending_once` (`:850`) y el call-site (`:1034-1040`).
2. `Stacky Agents/backend/services/artifact_intake.py` — invariante del contrato.

**Cambio exacto en el call-site (`output_watcher.py:1034-1040`):**

```python
            if not result.ok:
                # Plan 256 F1 — un rechazo SIN errores es un bug del validador,
                # no un artefacto malo. Se dice así, con todas las letras.
                if result.errors:
                    reason = ("intake rechazó el artefacto (%s): %s"
                              % ("pending_task_json", "; ".join(result.errors)))
                else:
                    reason = (
                        "intake rechazó el artefacto (pending_task_json) SIN informar "
                        "ninguna causa — esto es un defecto del validador, no del "
                        "artefacto. Revisar artifact_intake.validate_and_normalize."
                    )
                    logger.error(
                        "output_watcher: BUG del validador — validate_and_normalize "
                        "devolvió ok=False con errors=[] para %s", pt_file)
                _quarantine_pending_once(pt_file, reason, cause_code=result.code or "UNKNOWN")
                skipped += 1
                continue
```

**Cambio exacto en `_quarantine_pending_once` (`output_watcher.py:850`):** nueva firma y guard.

```python
def _quarantine_pending_once(pt_file: Path, reason: str, *,
                             cause_code: str = "UNKNOWN") -> bool:
    """... (docstring existente) ...

    Plan 256 F1 — `reason` no puede ser vacío ni terminar en ':'. La clave de
    cuarentena incluye `cause_code` para que corregir la CARPETA (que no cambia
    el mtime del JSON) permita reintentar.
    """
    reason = (reason or "").strip()
    if not reason or reason.endswith(":"):
        reason = (f"rechazo sin causa informada (cause_code={cause_code}) — "
                  f"defecto del validador; ver logs de artifact_intake")
    key = f"{pt_file}|{cause_code}"          # antes: str(pt_file)
    ...
```

**Símbolo nuevo en `services/artifact_intake.py`:** el resultado gana un campo `code: str | None` con un valor del conjunto ya existente en `output_watcher.py:845-847` (`PENDING_TASK_SCHEMA_INVALID`, `PENDING_TASK_STATUS_INVALID`, …). Y un guard al final de `validate_and_normalize`:

```python
    # Plan 256 F1 — invariante del contrato: ok=False ⟹ hay al menos un error.
    if not ok and not errors:
        errors = ["UNSPECIFIED_REJECTION: el validador rechazó sin registrar causa"]
        code = code or "UNSPECIFIED_REJECTION"
```

**Casos borde:**
- `reason` con solo espacios: el `.strip()` lo detecta.
- `cause_code=None`: se normaliza a `"UNKNOWN"`.
- **Migración de la clave de cuarentena:** al cambiar de `str(path)` a `f"{path}|{code}"`, las entradas viejas en memoria quedan huérfanas. Como `_SEEN_TERMINAL_PENDING` es un dict en memoria (se vacía al reiniciar), el impacto es nulo. **Verificar que no esté persistido en disco** antes de cambiar; si lo estuviera, hay que migrar las claves.
- `quarantine_snapshot()` (`output_watcher.py:871`) devuelve `path -> {...}`: con la clave compuesta hay que **separar** path y code en el retorno para no romper a sus consumidores. Mantener `path` como clave del dict y agregar `cause_code` al valor.

**Tests:** casos 1, 2, 3, 4, 5, 6 de F0 a verde.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan256_intake_razon.py -v
```
6 verdes, y `grep -c "intake rechazó el artefacto: *$"` sobre el log del día siguiente = **0**.

**Flag:** ninguna. Es la corrección de un mensaje defectuoso; ponerla detrás de una flag dejaría el defecto vivo por default.
**Impacto por runtime:** los 3 igual (el watcher es común).
**Trabajo del operador: ninguno** — y a partir de acá tiene la razón que hoy le falta.

---

### F2 — Nunca perder el original

**Objetivo:** que la reparación automática y la cuarentena no destruyan el artefacto del agente.

**Archivo a editar:** `Stacky Agents/backend/services/output_watcher.py:1041-1054`.

El código actual **reescribe el archivo del operador in place**:

```python
1041            if result.repaired and isinstance(result.normalized, dict):
1044                try:
1045                    pt_file.write_text(
1046                        _json.dumps(result.normalized, ensure_ascii=False, indent=2),
1047                        encoding="utf-8",
1048                    )
```

**Cambio exacto:** copia previa con sufijo, y **una sola** copia por contenido.

```python
            if result.repaired and isinstance(result.normalized, dict):
                # Plan 256 F2 — el original del agente se preserva ANTES de
                # reescribir. Idempotente: si el .orig ya existe para este
                # contenido, no se sobreescribe.
                orig = pt_file.with_suffix(pt_file.suffix + ".orig")
                try:
                    if not orig.exists():
                        orig.write_text(raw_text, encoding="utf-8")
                except OSError:
                    logger.error(
                        "intake: NO se pudo preservar el original de %s — "
                        "se ABORTA la reparación para no destruir el artefacto",
                        pt_file, exc_info=True)
                    _quarantine_pending_once(
                        pt_file,
                        "reparación abortada: no se pudo escribir la copia .orig",
                        cause_code="ORIG_BACKUP_FAILED")
                    skipped += 1
                    continue
                # ... recién ahora el write_text existente ...
```

**Regla dura:** si la copia falla, **se aborta la reparación**. Es preferible un artefacto en cuarentena con razón clara a un artefacto del agente destruido.

**Además:** `.orig` debe estar en el `.gitignore` de la carpeta de outputs si esa carpeta estuviera versionada, y el escaneo del watcher debe **ignorar** los `*.json.orig` para no intentar procesarlos como artefactos. Ese segundo punto es obligatorio o se genera un loop.

**Casos borde:**
- Segundo pase de reparación sobre el mismo archivo: `orig.exists()` evita pisar la copia buena con la ya reparada. **Esto es crítico**: sin el guard, el segundo pase guardaría como "original" la versión ya modificada.
- Disco lleno: la copia falla → se aborta y se pone en cuarentena con `ORIG_BACKUP_FAILED`.
- El watcher levanta el `.orig` como artefacto nuevo: se filtra por extensión en el glob del scan.

**Tests:** en `test_plan256_intake_razon.py`:
- `test_reparacion_preserva_el_original` — el `.orig` tiene el contenido crudo original.
- `test_reparacion_no_pisa_el_orig_en_el_segundo_pase`
- `test_reparacion_abortada_si_falla_el_orig` — mock de `OSError`; el archivo original queda **intacto** y va a cuarentena.
- `test_watcher_ignora_archivos_orig` — un `pending-task.json.orig` no se procesa como artefacto.

**Criterio binario:** 4 verdes.

**Flag:** `INTAKE_PRESERVE_ORIGINAL_ENABLED`, **default ON**. Sin excepción dura: escribir una copia de respaldo no es destructivo, no bypasea revisión, no requiere prerequisito, no reduce seguridad.
**Impacto por runtime:** los 3 igual.
**Trabajo del operador: ninguno.**

---

### F3 — La cuarentena, visible

**Objetivo:** sacar `quarantine_snapshot()` de la oscuridad. Ahora que la razón existe (F1), mostrarla vale la pena.

**Archivos a editar:**
1. `Stacky Agents/backend/api/diag.py` — endpoint `GET /api/diag/intake/quarantine`.
2. Frontend, panel de diagnóstico existente — tarjeta *"Artefactos en cuarentena"*.

**Contrato del endpoint (exacto):**

```json
{
  "count": 1,
  "items": [{
    "path": "C:\\desarrollo\\...\\epic-402\\rf-...\\pending-task.json",
    "file_name": "pending-task.json",
    "reason": "intake rechazó el artefacto (pending_task_json): PENDING_TASK_SCHEMA_INVALID: falta 'title'",
    "cause_code": "PENDING_TASK_SCHEMA_INVALID",
    "mtime_ns": 1785000000000000000,
    "first_seen": "2026-07-25T18:12:03Z",
    "has_original_backup": true,
    "retryable": true
  }]
}
```

`retryable` es `False` solo para `cause_code == "ORIG_BACKUP_FAILED"` (hay que arreglar el disco antes) y `True` en el resto.

**Tarjeta en la UI:** título, contador, y por ítem el nombre de archivo + la razón en texto plano + dos botones (F4). Si `count == 0`, la tarjeta **no se renderiza** (no agregar ruido visual cuando todo está bien).

**Tests:** `Stacky Agents/backend/tests/test_plan256_quarantine_api.py` (agregar al ratchet):
- `test_endpoint_vacio_devuelve_count_cero`
- `test_endpoint_expone_reason_y_cause_code`
- `test_endpoint_nunca_devuelve_reason_vacia` — invariante, otra vez, en la frontera HTTP.
- `test_retryable_false_solo_para_orig_backup_failed`

Frontend: `Stacky Agents/frontend/src/**/__tests__/planN256Quarantine.test.ts`
- `test_no_renderiza_si_count_cero`
- `test_muestra_razon_completa`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan256_quarantine_api.py -v
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx vitest run src/**/__tests__/planN256Quarantine.test.ts
```
4 + 2 verdes. (Vitest **por archivo**: contaminación cross-file conocida.)

**Flag:** `UI_INTAKE_QUARANTINE_CARD_ENABLED`, **default ON**. Sin excepción dura.
**Impacto por runtime:** la UI es común; los artefactos de los 3 runtimes caen en la misma cuarentena.
**Trabajo del operador: ninguno** — información nueva donde ya mira.

---

### F4 — Reintentar o descartar, con el operador decidiendo

**Objetivo:** cerrar el ciclo. Hoy un artefacto en cuarentena queda ahí hasta reiniciar el backend.

**Archivos a editar:**
1. `Stacky Agents/backend/api/diag.py` — `POST /api/diag/intake/quarantine/retry` y `POST /api/diag/intake/quarantine/discard`.
2. `Stacky Agents/backend/services/output_watcher.py` — dos funciones nuevas.

**Símbolos nuevos exactos en `output_watcher.py`:**

```python
def quarantine_retry(path: str) -> dict:
    """Plan 256 F4 — saca `path` de la cuarentena para que el próximo scan lo
    reintente. NO modifica el archivo. Devuelve {'ok', 'path', 'was_quarantined'}.
    Idempotente: reintentar algo que no está en cuarentena devuelve ok=True.
    """

def quarantine_discard(path: str, *, confirm_token: str) -> dict:
    """Plan 256 F4 — marca el artefacto como descartado por el operador.

    NO borra el archivo: le pone `status='discarded_by_operator'` y un
    `discarded_at`, para que el watcher lo ignore y quede la evidencia en disco.
    Exige confirm_token válido.
    """
```

**Contrato HITL, no negociable:**
- `retry` es **no destructivo** → un clic, sin confirmación.
- `discard` **no borra nada**: escribe un marcador en el propio JSON. El trabajo del agente queda en disco para siempre. Aun así exige `confirm_token` (TTL 120 s, emitido por el `GET`) y la UI muestra *"El artefacto queda en disco marcado como descartado. No se borra."*
- **Prohibido** cualquier acción automática: Stacky nunca reintenta ni descarta por su cuenta. La cuarentena es un pedido de decisión al operador.

**Casos borde:**
- `retry` de un path que ya no existe en disco: `ok=True, was_quarantined=False`, se limpia la entrada.
- `discard` sobre un archivo read-only: falla con mensaje claro, la entrada **queda** en cuarentena (no se pierde el ítem).
- `retry` cuando la causa es de carpeta y no de archivo: el reintento va a fallar otra vez, pero con la razón de F1 el operador ya sabe qué carpeta arreglar. Documentar que `retry` no arregla nada por sí solo.
- Path traversal: validar que el `path` recibido esté **bajo** el `outputs_dir` resuelto. Rechazar con `400` si no. Esto es obligatorio: el endpoint recibe una ruta del cliente.

**Tests:** en `test_plan256_quarantine_api.py`:
- `test_retry_saca_de_cuarentena_y_es_idempotente`
- `test_retry_no_modifica_el_archivo` — hash del contenido antes y después.
- `test_discard_sin_token_devuelve_409`
- `test_discard_no_borra_el_archivo` — el archivo existe y tiene `status='discarded_by_operator'`.
- `test_discard_archivo_readonly_mantiene_la_entrada`
- `test_path_fuera_de_outputs_dir_devuelve_400` — seguridad.
- `test_ninguna_accion_es_automatica` — asserta que ni `quarantine_retry` ni `quarantine_discard` se llaman desde `scan_once` (grep del módulo: 0 call-sites internos).

**Criterio binario:** 7 verdes + los 4 de F3 = 11 verdes en el archivo.

**Flag:** `INTAKE_QUARANTINE_ACTIONS_ENABLED`, **default ON** para `retry`; el `discard` va detrás de `INTAKE_QUARANTINE_DISCARD_ENABLED` **default OFF**, citando la **excepción dura #2 (destructiva/irreversible)** — aunque no borre el archivo, marca el artefacto como descartado de forma no revertible desde la UI.
**Impacto por runtime:** los 3 igual.
**Trabajo del operador:** opt-in explícito para el descarte; el reintento es un clic disponible por default.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cambiar la clave de cuarentena rompe consumidores de `quarantine_snapshot()` | El retorno **mantiene** `path` como clave y agrega `cause_code` al valor. Verificar los consumidores del plan 149 antes de cerrar F1. |
| El `.orig` se procesa como artefacto y genera un loop | Filtro explícito por extensión en el glob del scan, con test dedicado (`test_watcher_ignora_archivos_orig`). |
| El `.orig` del segundo pase guarda la versión ya reparada como "original" | Guard `if not orig.exists()`, con test dedicado. |
| Los `.orig` acumulan basura en la carpeta del operador | Uno por artefacto reparado, mismo tamaño que el original. Documentar en el README operativo; no se agrega purga automática (borrar cosas del operador sin pedir es exactamente lo que este plan evita). |
| `retry` da falsa esperanza cuando la causa es de carpeta | La razón de F1 dice qué corregir. Documentar en el tooltip: *"reintenta la validación; no corrige el artefacto"*. |
| Path traversal en los endpoints nuevos | Validación obligatoria de que el path esté bajo `outputs_dir`, con test. |
| El invariante "ok=False ⟹ errors≥1" enmascara el bug real del validador | No lo enmascara: además de rellenar el error, se loguea a **`error`** que el validador tiene un defecto (caso 2 de F0). |

---

## 6. Fuera de scope

- Reescribir `artifact_intake.validate_and_normalize`. Este plan garantiza que **informe** su causa; mejorar sus reglas de validación es otro trabajo.
- El `no such table: tickets` y los locks que hacen perder rounds → **plan 253**.
- El `artifact_rescue falló (no crítico)` de `api/tickets.py`: se **nombra** como evidencia (E5) pero su arreglo es del eje de fallas mudas → **plan 255**.
- El ruido de las 25 ocurrencias de `corrigiendo epic dir mal nombrado`: acá se usa como evidencia de que los nombres de carpeta fallan; el throttle del volumen es del **plan 257**.
- Cambiar el formato de `pending-task.json`. Backward-compatible o nada.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **`output_watcher`** | Daemon que vigila `Agentes/outputs/` y convierte los artefactos que dejan los agentes en tickets/tasks de Stacky. `backend/services/output_watcher.py`. |
| **`pending-task.json`** | Artefacto que un agente deja en disco pidiendo que Stacky cree una task. La forma principal en que el trabajo del agente entra al sistema. |
| **Intake** | La validación/normalización que decide si un artefacto entra. `backend/services/artifact_intake.py`. |
| **Cuarentena** | Registro en memoria de artefactos con fallo terminal que el watcher omite hasta que algo cambie. `_SEEN_TERMINAL_PENDING` + `_QUARANTINE_REASON`. |
| **`cause_code`** | Código estable de la causa del rechazo (p. ej. `PENDING_TASK_SCHEMA_INVALID`). Nuevo en F1; permite reintentar cuando cambia la causa y no el archivo. |
| **Modo A / Modo B** | Los dos modos de descubrimiento del watcher (por carpeta de épica y por ticket directo). El fallo terminal de los logs es de **modo A**. |
| **`.orig`** | Copia del artefacto crudo del agente, escrita antes de cualquier reparación automática. |
| **Excepción dura** | Una de las 4 razones para que una flag nazca OFF: bypasea revisión humana, destructiva, prerequisito no garantizado, reduce seguridad. |

---

## 8. Orden de implementación

1. **F0** — 6 tests, rojos. Registrar en `HARNESS_TEST_FILES`.
2. **F1** — razón obligatoria + `cause_code` en la clave + invariante en `artifact_intake`. **Esta fase sola ya elimina el hallazgo principal.** Verificar consumidores de `quarantine_snapshot()`.
3. Verificar en vivo: el log del día siguiente no tiene ningún `intake rechazó el artefacto:` terminado en dos puntos.
4. **F2** — copia `.orig` + abortar la reparación si la copia falla + filtrar `.orig` del scan.
5. **F3** — endpoint `GET` + tarjeta en el panel de diagnóstico (que ahora muestra razones útiles).
6. **F4** — `retry` (default ON) y `discard` (default OFF, con token, sin borrar).
7. Exponer las 3 flags nuevas en el panel de flags y en `api/global_config.py`.
8. Registrar los 2 archivos de test backend nuevos en `HARNESS_TEST_FILES`.

---

## 9. Definición de Hecho (DoD)

- [ ] Ningún mensaje de cuarentena termina en `:` o queda vacío; `grep -c "intake rechazó el artefacto: *$"` = **0**.
- [ ] Un `ok=False` con `errors=[]` produce razón explícita **y** un `logger.error` que lo señala como bug del validador.
- [ ] La clave de cuarentena incluye `cause_code`; dos causas distintas sobre el mismo path son dos entradas.
- [ ] `quarantine_snapshot()` nunca devuelve `reason` vacía (invariante con test).
- [ ] La reparación automática preserva el `.orig` y **aborta** si no puede.
- [ ] El watcher **ignora** los `*.orig`.
- [ ] `GET /api/diag/intake/quarantine` expone razón, `cause_code` y `retryable`.
- [ ] La tarjeta de cuarentena se ve en la UI y **no** se renderiza si `count == 0`.
- [ ] `retry` es idempotente y **no** modifica el archivo (verificado por hash).
- [ ] `discard` exige token, **no borra** el archivo, y está detrás de una flag default OFF.
- [ ] Los endpoints rechazan paths fuera de `outputs_dir` con `400`.
- [ ] Ni `retry` ni `discard` se invocan desde `scan_once` (cero automatismo).
- [ ] Los 2 archivos de test backend nuevos están en `HARNESS_TEST_FILES`.
- [ ] Las 3 flags nuevas se cambian **desde la UI**.
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**).
