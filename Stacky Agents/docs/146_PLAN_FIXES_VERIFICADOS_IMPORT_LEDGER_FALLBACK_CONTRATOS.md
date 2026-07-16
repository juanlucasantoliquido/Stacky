# Plan 146 — Fixes verificados de bajo esfuerzo: import `AgentExecution`, `mkdir` del ledger SQLite, contrato de `Config` fallback

- **Estado:** IMPLEMENTADO F0..F4 (2026-07-16, commits 743f8c84/4e68db61) · CRITICADO v1→v2 previo: **APROBADO-CON-CAMBIOS**
- **Fecha:** 2026-07-15
- **Autor:** StackyArchitectaUltraEficientCode (perfil: normal, heredado de Opus 4.8)
- **Crítica v2 (juez adversarial):** StackyArchitectaUltraEficientCode (perfil: normal, heredado de Opus 4.8) — 2026-07-15
- **Serie:** 144–149 (derivada de `docs/reportes/2026-07-15_AUDITORIA_LOGS_deploy_vs_dev.md`)
- **Cluster de este plan:** "Fixes verificados de bajo esfuerzo + blindaje de contratos de Config/imports con tests"
- **Hallazgos que cierra:** **V1** (import `Execution`→`AgentExecution`), **V5** (`mkdir` del SQLite ledger + dedup de warning), **V4** (contrato `Config.CLAUDE_CODE_CLI_MODEL_FALLBACK` + re-deploy)

### CHANGELOG v1 → v2 (crítica adversarial)
Todas las citas `[V]` del v1 se **re-verificaron contra el código real** y son correctas (`ado_edit_learning.py:259` import roto; `db.py:302` `session_scope`; `models.py:207/219` `AgentExecution`/`metadata_json`; `config.py:216-217` `CLAUDE_CODE_CLI_MODEL_FALLBACK`; 4 call-sites SQLite sin `mkdir`; `_append_jsonl:79` sí lo hace; meta-test parsea solo el `.sh`). Cambios de v2:

- **C1 (MEDIO-ALTO) — Cambio de comportamiento subestimado.** `app.py:444-446`: el daemon del sweep está **gated por `STACKY_ADO_EDIT_LEARNING_ENABLED`, default ON** (promovido 2026-07-15). Hoy el sweep **crashea en el `ImportError` ANTES de llegar al loop de ADO** → 0 llamadas ADO. Tras el fix, cada ciclo consulta `AgentExecution` y llama `fetch_work_item_updates` + `save_observation` + `mark_learned` en **~todas** las instalaciones. La afirmación v1 "sin cambio de comportamiento observable salvo la desaparición del error" era **inexacta**: se **revive trabajo real de fondo**. Corregido en §1/§3.2 + nuevo riesgo R8.
- **C2 (MEDIO) — Reuso.** El fix reimplementaba el decode de metadata en vez de usar el accessor canónico `AgentExecution.metadata_dict` (`models.py:259-261`). Cambio B reescrito para preferir `metadata_dict`.
- **C3 (MEDIO) — [ADICIÓN ARQUITECTO] Dedup robusto.** El guard `_sqlite_warned` de un solo booleano **silenciaba para siempre** cualquier fallo SQLite **nuevo/distinto** posterior. Reemplazado por dedup **por firma `(tipo+mensaje de la excepción)` con re-emisión temporal** (`_SQLITE_WARN_STATE` + `_SQLITE_WARN_INTERVAL_S`; el mismo error desde 4 call-sites colapsa a 1 warning, pero una causa distinta aflora). Semántica idéntica a `log_throttle.log_throttled` de 145 → migración trivial. Preserva observabilidad de fallos persistentes.
- **C4 (MEDIO-BAJO) — Fidelidad de test.** `_RealShapedRun` no tenía `metadata_dict`; ahora lo expone para ejercitar el path canónico (blinda C2).
- **C5 (BAJO) — Orden.** Se suavizó la afirmación "146 antes que 145" (no verificable y en tensión con lo que declara 145); 146 es autónomo en cualquier orden.
- **C6 (BAJO) — Re-deploy.** Reencuadrado como paso de **release del plan** (ships V1+V5+V4), no acción específica de V4; DEV toma el fix al reiniciar sin re-deploy.
- **C7 (BAJO) — Allowlist.** Nota: `tests/harness_ratchet_allowlist.txt` puede no existir hoy (el meta-test lo trata como vacío); no crearlo.

---

## 1. Título, objetivo e impacto esperado

Este plan corrige tres defectos **verificados contra el código real del working tree** que hoy generan ruido masivo y dejan funcionalidad muerta, y añade **tests de contrato** que impiden su regresión. Los tres son de bajo esfuerzo e invisibles al operador. **Advertencia de comportamiento (C1):** V5 y V4 no cambian comportamiento observable salvo la desaparición del error; **V1 sí revive trabajo de fondo real** — hoy el sweep crashea en el `ImportError` **antes** de llamar a ADO (0 llamadas), y tras el fix pasará a hacer polling de ADO + escritura de lecciones/memoria en cada ciclo. Ese daemon está **gated por `STACKY_ADO_EDIT_LEARNING_ENABLED` (default ON desde 2026-07-15, `app.py:446`)**, así que la revivificación se activa en ~todas las instalaciones; el ledger de idempotencia acota el trabajo repetido (ver R8):

1. **V1 (ALTO, `[V]`)** — `services/ado_edit_learning.py:259` hace `from models import Execution, session_scope`; en `models.py` la clase es `AgentExecution` (línea 207) y **`session_scope` no vive en `models` sino en `db.py:302`**. Cada barrido de `sweep_recent_runs` con DB viva explota con `ImportError` (capturado como `sweep_recent_runs: error general`), **318 veces** en los logs de DEV. Además, tras arreglar el import aparece un **segundo bug verificado no listado en el reporte**: la función lee `run.metadata` (el objeto `MetaData` de SQLAlchemy) en vez de `run.metadata_json` (la columna real), por lo que el sweep degradaría a **no-op silencioso** (nunca aprende) aun con el import corregido.
2. **V5 (MEDIO, `[INF]`)** — `services/ado_edit_ledger.py` abre `sqlite3.connect(_get_db_path())` en 4 funciones **sin garantizar el directorio padre**; si `data_dir()` no existe, falla con `unable to open database file` (**42 veces**: 30 en `_create_table_if_needed`, 12 en `mark_learned`) y lo advierte en cada ciclo.
3. **V4 (MEDIO, `[V]`)** — el atributo `Config.CLAUDE_CODE_CLI_MODEL_FALLBACK` **ya está presente en el working tree** (`config.py:216-217`), pero el DEPLOY v1.0.76 (commit `7df192a8`) es anterior al fix y es vulnerable a `'Config' object has no attribute 'CLAUDE_CODE_CLI_MODEL_FALLBACK'` si se dispara el fallback. Falta un **test de contrato** que bloquee la regresión y **re-publicar el deploy**.

**KPI / impacto esperado:**
- `sweep_recent_runs: error general: cannot import name 'Execution'`: **318 → 0** warnings.
- `ado_edit_ledger ... unable to open database file`: **42 → ≤1** (una advertencia, o cero cuando el dir se crea).
- ADO edit learning deja de ser **dead code**: el sweep vuelve a poder leer metadata de runs reales y producir lecciones.
- Un test de contrato de `Config` protege contra que una futura edición vuelva a borrar `CLAUDE_CODE_CLI_MODEL_FALLBACK` (u otro atributo que el runner de Claude lee).

---

## 2. Por qué ahora / gap que cierra

- **V1** es un bug `[V]` con fix trivial que hoy dispara 318 warnings/día en DEV y **está latente en DEPLOY** (mismo código base; el deploy simplemente no ejercita ese path con la frecuencia del server local). Peor: el reporte lo describe como "renombrar `Execution`", pero la verificación real muestra que **el import también arrastra `session_scope` desde el módulo equivocado** y que **el uso de `metadata` está roto** — un modelo menor que aplique la instrucción literal del reporte dejaría el import a medio arreglar y el feature muerto. Este plan lo cierra **completo y sin fragilidad**.
- **V5** es la contraparte defensiva/local de la causa raíz de rutas que ataca el **Plan 147** (resolución de `data_dir()`/`repo_root()`). Aquí no arreglamos la resolución de rutas (eso es 147): garantizamos que el ledger **cree su directorio padre** y **no floodee** aunque la ruta llegue mal. Es backward-compatible y no interfiere con 147.
- **V4** es un bug ya corregido en código; el gap es de **release** (el binario desplegado no lo tiene) y de **contrato** (nada impide que una futura regresión de `config.py` vuelva a quitar el atributo). El test de contrato es el blindaje barato que faltaba.

Este es el plan de **quick wins verificados**: junto con el 144 (bloqueo crítico de producción) es lo primero del orden global de la serie.

---

## 3. Principios y guardarraíles (rieles duros de Stacky, codificados por fase)

1. **Paridad de 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):** V1 y V5 son **runtime-agnósticos** — el sweep de ADO edit learning y el ledger SQLite corren igual sin importar qué runtime ejecutó el run; el fix aplica **idéntico** a los 3, sin ramas por runtime. V4 es específico del runner de **Claude Code CLI** (`CLAUDE_CODE_CLI_MODEL_FALLBACK`); el test de contrato guarda los atributos que lee `claude_code_cli_runner.py`. Codex (`codex_cli_runner.py`) y Copilot no tienen ese atributo y **no lo necesitan**: su ausencia no los afecta (degradación = n/a). Se detalla el impacto por runtime en cada fase.
2. **Cero trabajo extra al operador:** F1/F2/F3 son invisibles y automáticas. La única acción de operador es RE-PUBLICAR el deploy — es una **acción de release del plan** (ships V1+V5+V4 juntos, **no** específica de V4; **C6**), one-time, de fixes ya commiteados, **no** config nueva ni paso recurrente. En **DEV** el fix surte efecto con solo reiniciar el proceso (corre de fuente, sin re-deploy); solo el **binario del DEPLOY** necesita re-publish. No dispara ninguna de las 4 excepciones duras (no bypasea revisión humana, no es destructiva, no requiere prerequisito nuevo en instalación default, no reduce seguridad). Se marca explícitamente como "Trabajo del operador".
3. **Human-in-the-loop:** ningún cambio agrega autonomía proactiva. El ledger ya era automático. El sweep de learning también estaba cableado como daemon (`app.py:446`, flag default ON), pero **crasheaba en cada ciclo** (V1) → estaba muerto. El fix lo **revive** a su comportamiento diseñado (Plan 60): aprender de ediciones humanas sobre work items. No es autonomía nueva (no toma decisiones por el operador; solo observa ediciones y guarda lecciones), pero **sí es trabajo de fondo real que hoy no ocurre** — clasificado honestamente en R8. No agrega ninguna superficie de acción para el operador.
4. **Mono-operador sin auth real:** no se toca ninguna superficie de auth/RBAC.
5. **No degradar performance/seguridad/estabilidad/DX; backward-compatible; reusar lo existente:** se reusa el patrón de fixtures de `test_ado_edit_sweep.py`, el ledger JSONL de fallback ya presente, y el ratchet `HARNESS_TEST_FILES`. Los cambios son quirúrgicos y compatibles hacia atrás (el `_FakeRun` de los tests existentes sigue funcionando por diseño del fix).

### 3.1 Flags: por qué este plan NO introduce ninguna

Los tres son **fixes de bug verificados** (corrigen código roto; no agregan comportamiento opt-in ni superficie nueva). Según el patrón duro del repo, un fix de bug verificado **no necesita flag**. Justificación por caso:

- **V1** — antes fallaba SIEMPRE (ImportError en cada sweep con DB viva). No hay "comportamiento viejo" que preservar detrás de una flag: el comportamiento viejo es "crashea y no aprende". Poner una flag sería preservar el bug.
- **V5** — `mkdir(parents=True, exist_ok=True)` y dedup de warning son **defensivos**: garantizan una precondición (el dir existe) que siempre debió cumplirse. No cambian comportamiento observable salvo eliminar el error. El guard de dedup es interno (no configurable por el operador).
- **V4** — sólo se AGREGA un test de contrato; el código (`config.py`) ya tiene el fix y no se toca. Nada que flaggear.

Ninguna de estas correcciones expone umbrales/endpoints/backoff que el operador deba configurar, así que **no aplica** la regla "todo valor configurable por el operador va por UI".

---

## 4. Fases F0..F4

> **Entorno de tests (verificado, no asumido):**
> - Venv real: `Stacky Agents/backend/.venv/Scripts/python.exe` (py3.13). Confirmado: `backend/.venv/pyvenv.cfg` existe.
> - Los tests corren con **cwd = `backend/`** e imports top-level (`from models import ...`, `from config import config`, `from db import ...`). El script `backend/scripts/run_harness_tests.sh` hace `cd "$(dirname "$0")/.."` (→ `backend/`) y luego `python -m pytest <archivo> -q`. `python -m pytest` inserta el cwd en `sys.path`, por eso resuelven los imports top-level.
> - **Correr SIEMPRE por archivo** (la suite completa contamina cross-file). No hay `conftest.py` ni `pytest.ini` en `backend/`.
> - **Comando canónico (PowerShell, desde la raíz del repo con espacios):**
>   ```powershell
>   cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
>   .\.venv\Scripts\python.exe -m pytest tests\test_plan146_verified_fixes.py -q
>   ```

---

### F0 — Scaffolding del archivo de test + registro en el ratchet de cobertura

- **Objetivo (1 frase):** crear el archivo de test del plan y registrarlo en el ratchet `HARNESS_TEST_FILES` para que el meta-test no falle, dejando la base sobre la que F1–F3 agregan sus casos.
- **Valor:** sin esto, `test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests` falla en cuanto exista el archivo nuevo (todo `tests/test_*.py` debe estar clasificado).

**Archivos a crear/editar (rutas exactas):**
1. **CREAR** `Stacky Agents/backend/tests/test_plan146_verified_fixes.py` con este contenido inicial (docstring + un test scaffold trivial que garantiza que pytest colecciona al menos 1 caso):
   ```python
   """Plan 146 — Fixes verificados de bajo esfuerzo (V1, V5, V4).

   Un solo archivo con los tests de contrato/comportamiento de las 3 correcciones.
   Correr aislado:  .venv/Scripts/python.exe -m pytest tests/test_plan146_verified_fixes.py -q
   """
   from __future__ import annotations

   import logging
   import json as _json
   from contextlib import contextmanager

   import pytest


   def test_plan146_scaffold():
       """Placeholder para que el archivo exista y el ratchet lo clasifique (F0)."""
       assert True
   ```
2. **EDITAR** `Stacky Agents/backend/scripts/run_harness_tests.sh` — dentro del array `HARNESS_TEST_FILES=( ... )` (empieza en línea 20), agregar UNA línea **sin comillas**, respetando el sangrado de 2 espacios de las entradas existentes (p. ej. junto a `tests/test_ado_edit_sweep.py` en la línea 107):
   ```
     tests/test_plan146_verified_fixes.py
   ```
3. **EDITAR** `Stacky Agents/backend/scripts/run_harness_tests.ps1` — dentro de su array (la entrada análoga está en la línea 100: `  "tests/test_ado_edit_sweep.py",`), agregar UNA línea **con comillas y coma final**:
   ```
     "tests/test_plan146_verified_fixes.py",
   ```
   > El meta-test `test_harness_ratchet_meta.py` sólo parsea el `.sh` (paso 2 es el obligatorio); el `.ps1` (paso 3) se actualiza por **paridad** para el operador Windows. Hacé ambos.

**Casos borde:**
- El array `HARNESS_TEST_FILES` del `.sh` es un **ratchet: sólo crece**. No borres ni reordenes entradas existentes; sólo agregá la tuya.
- No pongas la entrada en `tests/harness_ratchet_allowlist.txt` (esa lista es para tests excluidos con motivo; solaparía y rompería `test_allowlist_no_se_solapa_con_ratchet`). **Nota (C7):** ese archivo hoy **puede no existir** — el meta-test lo trata como vacío (`_allowlist()` retorna `set()` si falta). **No lo crees**; tu test va al `.sh`.

**Criterio de aceptación BINARIO + comando:**
- El meta-test del ratchet pasa (clasifica el archivo nuevo y no referencia inexistentes):
  ```powershell
  cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
  .\.venv\Scripts\python.exe -m pytest tests\test_harness_ratchet_meta.py -q
  ```
  → **PASA** (3 tests verdes). Y `pytest tests\test_plan146_verified_fixes.py -q` → 1 test verde (`test_plan146_scaffold`).

**Flag que la protege:** ninguna (scaffolding). **Default:** n/a.
**Impacto por runtime:** ninguno (infra de tests). **Fallback:** n/a.
**Trabajo del operador:** ninguno.

---

### F1 — V1: corregir el import y el uso de `metadata` en `sweep_recent_runs`

- **Objetivo (1 frase):** que `sweep_recent_runs` importe `AgentExecution` (y `session_scope` desde `db`) y lea la metadata desde la columna real `metadata_json`, eliminando el `ImportError` (318×) y el no-op silencioso.
- **Valor:** elimina 318 warnings/día y revive la funcionalidad de ADO edit learning (que hoy nunca aprende de runs reales).

**TESTS PRIMERO (TDD).** Agregar a `tests/test_plan146_verified_fixes.py` estos dos casos (fallan antes del fix, pasan después):

```python
# ---------- V1: import real de AgentExecution + session_scope ----------

def test_sweep_recent_runs_real_import_path_no_import_error(monkeypatch, caplog):
    """V1: con _db_runs=None se ejecuta el IMPORT REAL del módulo models/db.

    Antes del fix, 'from models import Execution, session_scope' lanzaba
    ImportError ('cannot import name Execution') capturado y logueado como
    'sweep_recent_runs: error general'. El import NO se mockea: solo se
    inyecta una sesión falsa vía monkeypatch de db.session_scope para no
    tocar la DB real.
    """
    import db as db_mod

    class _FakeQuery:
        def order_by(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return []

    class _FakeSession:
        def query(self, *a, **k):
            return _FakeQuery()

    @contextmanager
    def _fake_scope():
        yield _FakeSession()

    # El fix hace 'from db import session_scope' DENTRO de la función:
    # parchear db.session_scope basta (se resuelve en tiempo de llamada).
    monkeypatch.setattr(db_mod, "session_scope", _fake_scope)

    from services.ado_edit_learning import sweep_recent_runs

    with caplog.at_level(logging.WARNING):
        result = sweep_recent_runs(_db_runs=None, _learn_fn=lambda **k: None)

    assert result == 0
    assert "cannot import name" not in caplog.text
    assert "error general" not in caplog.text


def test_sweep_reads_metadata_json_from_real_shaped_run(monkeypatch):
    """V1 (2º bug) + C2/C4: un run 'real' refleja EXACTAMENTE la forma de
    AgentExecution (models.py:207): expone la columna `.metadata_json` (str JSON),
    la property canónica `.metadata_dict` (dict parseado) y `.metadata` = el
    registro MetaData de SQLAlchemy (NO dict). El sweep debe leer el dict correcto
    (vía `metadata_dict` canónico) y extraer epic_ado_id — nunca el objeto MetaData.
    """
    from services.ado_edit_learning import sweep_recent_runs, LearnResult

    class _RealShapedRun:
        id = 7
        metadata_json = _json.dumps({"epic_ado_id": 999, "project_name": "P"})
        metadata = object()  # NO es dict: emula MetaData de SQLAlchemy

        @property
        def metadata_dict(self) -> dict:
            # Espejo fiel de AgentExecution.metadata_dict (models.py:259-261).
            return _json.loads(self.metadata_json)

    seen = {}

    def fake_learn(**kw):
        seen.update(kw)
        return LearnResult(
            learned=True, lesson_written=True, golden_written=False,
            rev=2, reason="ok",
        )

    result = sweep_recent_runs(
        _db_runs=[_RealShapedRun()],
        _ado_client_factory=lambda p: object(),
        _learn_fn=fake_learn,
    )

    assert seen.get("ado_id") == 999
    assert result == 1
```

> **Nota TDD:** antes del fix, el 1er test falla porque `from models import Execution` lanza ImportError → se captura → se loguea "error general" (assert falla). El 2º falla porque el código v1 lee `run.metadata` (= `object()`) → `json.loads(object())` lanza TypeError → `meta={}` → `epic_ado_id` None → `continue` → `result==0` y `seen` vacío. Tras el fix (Cambio B), el sweep lee `run.metadata_dict` (accessor canónico) → `{"epic_ado_id":999,...}` → `seen["ado_id"]==999`, `result==1`.

**Correr (debe estar en ROJO antes de tocar el código):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan146_verified_fixes.py -q
```

**IMPLEMENTACIÓN — editar `Stacky Agents/backend/services/ado_edit_learning.py`:**

Cambio A (import, líneas actuales 258-266):
```diff
         if _db_runs is None:
-            from models import Execution, session_scope
+            from models import AgentExecution
+            from db import session_scope
             with session_scope() as db:
                 raw_runs = (
-                    db.query(Execution)
-                    .order_by(Execution.id.desc())
+                    db.query(AgentExecution)
+                    .order_by(AgentExecution.id.desc())
                     .limit(_SWEEP_RUN_LIMIT)
                     .all()
                 )
```

Cambio B (lectura de metadata, líneas actuales 270-278) — **C2: reusa el accessor canónico `AgentExecution.metadata_dict` (`models.py:259-261`) en vez de reimplementar el decode JSON**:
```diff
         for run in raw_runs:
             try:
-                meta = (
-                    run.metadata
-                    if isinstance(run.metadata, dict)
-                    else json.loads(run.metadata or "{}")
-                )
+                # Accessor CANÓNICO de AgentExecution: la property .metadata_dict
+                # (models.py:259-261) hace _json_loads(self.metadata_json) or {}.
+                # Preferirla evita reimplementar el decode y nunca toca el objeto
+                # MetaData de SQLAlchemy expuesto en .metadata.
+                meta = getattr(run, "metadata_dict", None)
+                if not isinstance(meta, dict):
+                    # Fallback para el _FakeRun de test_ado_edit_sweep.py (expone
+                    # .metadata dict, sin la property canónica) y para formas que
+                    # solo traen la columna cruda metadata_json.
+                    raw_meta = getattr(run, "metadata_json", None)
+                    if not isinstance(raw_meta, (str, bytes)):
+                        _m = getattr(run, "metadata", None)
+                        raw_meta = _m if isinstance(_m, (str, dict)) else None
+                    meta = raw_meta if isinstance(raw_meta, dict) else json.loads(raw_meta or "{}")
             except Exception:
                 meta = {}
```

**Casos borde cubiertos por el fix:**
- `AgentExecution` real con `metadata_json` poblado: `run.metadata_dict` → dict parseado. Path canónico, sin fallback.
- `AgentExecution` real con `metadata_json=None` (columna nullable): `run.metadata_dict` → `_json_loads(None) or {}` → `{}`. No crashea, sin fallback.
- `_FakeRun` de los tests existentes (`.metadata` dict, **sin** `metadata_dict` ni `metadata_json`): `getattr(run,"metadata_dict",None) → None` → no dict → `metadata_json` None → `.metadata` es dict → `raw_meta=dict` → `meta=dict`. **Sigue funcionando** (backward-compatible).
- Forma que solo trae `metadata_json` cruda (sin la property): `metadata_dict` None → `metadata_json` str → `json.loads(str)`. No crashea.
- `metadata_json` con JSON inválido: cualquier `json.loads` lanza → `except` externo → `meta={}`. No crashea.

> **Por qué `metadata_dict` y no leer `metadata_json` crudo:** la property centraliza el contrato de serialización del modelo (`models.py:259-261`). Si mañana la metadata se cifra/comprime, el sweep sigue correcto sin tocarlo. Reusa lo existente (riel duro), no lo duplica.

**Criterio de aceptación BINARIO + comando:**
- Los dos tests nuevos de F1 pasan **y** los tests preexistentes de sweep siguen verdes (no-regresión del `_FakeRun`):
  ```powershell
  cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
  .\.venv\Scripts\python.exe -m pytest tests\test_plan146_verified_fixes.py -q
  .\.venv\Scripts\python.exe -m pytest tests\test_ado_edit_sweep.py -q
  ```
  → ambos **PASAN** (0 fallos). Verificación de que ya no queda referencia al símbolo roto:
  ```powershell
  cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents"
  Select-String -Path "backend\services\ado_edit_learning.py" -Pattern "import Execution\b|db\.query\(Execution\)|Execution\.id"
  ```
  → **sin coincidencias**.

**Flag que la protege:** ninguna (fix de bug verificado; ver §3.1). **Default:** n/a.
**Impacto por runtime:** idéntico en Codex / Claude Code / Copilot (el sweep lee `AgentExecution` de la DB sin importar el runtime que originó el run). **Fallback:** el `try/except` externo ya degrada a warning si algo falla; el fix solo elimina el error sistemático.
**Trabajo del operador:** ninguno.

---

### F2 — V5: garantizar el directorio del SQLite del ledger + dedup del warning

- **Objetivo (1 frase):** que `ado_edit_ledger` cree el directorio padre de su DB SQLite antes de abrirla y, si aun así no es escribible, degrade a JSONL con **una sola** advertencia por proceso.
- **Valor:** elimina 42 warnings/día (`unable to open database file`) y hace que el ledger persista en lugar de caer siempre al fallback.

**TESTS PRIMERO (TDD).** Agregar a `tests/test_plan146_verified_fixes.py`:

```python
# ---------- V5: mkdir del SQLite ledger + dedup del warning ----------

def test_ledger_creates_parent_dir_when_missing(monkeypatch, tmp_path):
    """V5: si el directorio padre de la DB no existe, el ledger lo crea y
    persiste en SQLite (el archivo .db queda en disco). Antes del fix,
    sqlite3.connect fallaba con 'unable to open database file' y NO se creaba
    el archivo (caía a JSONL)."""
    import services.ado_edit_ledger as lm

    nested_db = tmp_path / "no" / "existe" / "aun" / "ledger.db"
    monkeypatch.setattr(lm, "_get_db_path", lambda: str(nested_db))
    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "ledger.jsonl")
    monkeypatch.setattr(lm, "_SQLITE_WARN_STATE", {})

    lm.mark_learned(111, 3, "run-x")

    assert nested_db.exists(), "el fix debe crear el dir padre y la DB SQLite"
    assert lm.already_learned(111, 3) is True


def test_ledger_warns_once_per_signature_when_sqlite_unavailable(monkeypatch, tmp_path, caplog):
    """V5: ante el MISMO fallo repetido, se emite UNA sola advertencia (dedup por
    firma). El resto degrada silencioso a JSONL. Todas las operaciones lanzan la
    misma OperationalError → una firma → un warning."""
    import sqlite3
    import services.ado_edit_ledger as lm

    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "ledger.jsonl")
    monkeypatch.setattr(lm, "_SQLITE_WARN_STATE", {})

    def _boom(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")

    # _connect es el único punto de apertura tras el fix.
    monkeypatch.setattr(lm, "_connect", _boom)

    with caplog.at_level(logging.WARNING):
        lm.mark_learned(1, 1, "r1")
        lm.mark_learned(2, 2, "r2")
        lm.already_learned(3, 3)

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "SQLite no disponible" in r.getMessage()
    ]
    assert len(warnings) == 1, f"esperaba 1 warning dedup por firma, hubo {len(warnings)}"


def test_ledger_rewarns_on_distinct_sqlite_failure(monkeypatch, tmp_path, caplog):
    """C3: un fallo con firma DISTINTA vuelve a advertir. Un booleano global de un
    solo disparo lo habría silenciado para siempre; el dedup por firma NO oculta un
    fallo nuevo/persistente."""
    import sqlite3
    import services.ado_edit_ledger as lm

    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "ledger.jsonl")
    monkeypatch.setattr(lm, "_SQLITE_WARN_STATE", {})
    # No consumir el iterador con _create_table_if_needed intermedio:
    monkeypatch.setattr(lm, "_create_table_if_needed", lambda: None)

    errs = iter([
        sqlite3.OperationalError("unable to open database file"),
        sqlite3.OperationalError("database disk image is malformed"),  # firma distinta
    ])

    def _boom_seq(*a, **k):
        raise next(errs)

    monkeypatch.setattr(lm, "_connect", _boom_seq)

    with caplog.at_level(logging.WARNING):
        lm.already_learned(1, 1)   # 1ª firma → warning
        lm.already_learned(2, 2)   # 2ª firma distinta → warning

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "SQLite no disponible" in r.getMessage()
    ]
    assert len(warnings) == 2, f"cada firma distinta debe advertir una vez, hubo {len(warnings)}"
```

> **Nota TDD:** `test_ledger_creates_parent_dir_when_missing` falla antes del fix porque, sin `mkdir`, `sqlite3.connect(nested_db)` lanza y no crea el archivo → `nested_db.exists()` es `False`. Los dos tests de warning referencian los símbolos nuevos `_connect` y `_SQLITE_WARN_STATE` (no existen aún) → fallan hasta implementarlos. El 3º (`rewarns_on_distinct`) además fija el contrato de **no silenciar fallos nuevos** (fallaría con un guard de booleano único, que produciría 1 warning en vez de 2).

**IMPLEMENTACIÓN — editar `Stacky Agents/backend/services/ado_edit_ledger.py`:**

0. En el bloque de imports (línea 9-15), agregar `import time` (para el throttle temporal por firma).

1. Bajo la constante `_TABLE` (línea 19), agregar el estado y los helpers nuevos:
   ```python
   # C3 — dedup de warnings de SQLite POR FIRMA (no un booleano global de un solo
   # disparo). Un booleano único silenciaría PARA SIEMPRE cualquier fallo nuevo o
   # persistente posterior; el dedup por firma re-emite ante un error distinto y
   # a lo sumo una vez por intervalo. Semántica idéntica a
   # services/log_throttle.log_throttled (Plan 145): cuando 145 aterrice, migrar
   # es reemplazar este helper por una llamada (ver cross-ref al final de F2).
   _SQLITE_WARN_STATE: dict[str, float] = {}   # firma -> ts monotónico del último warning
   _SQLITE_WARN_INTERVAL_S = 300.0             # re-emite una firma a lo sumo cada 5 min


   def _connect() -> "sqlite3.Connection":
       """Abre la DB SQLite del ledger garantizando el directorio padre.

       Centraliza TODA apertura de conexión: crea el dir padre (mkdir -p) antes
       de conectar para evitar 'unable to open database file' cuando data_dir()
       aún no existe. (Causa raíz de la resolución de rutas: ver Plan 147.)
       """
       db_path = _get_db_path()
       try:
           Path(db_path).parent.mkdir(parents=True, exist_ok=True)
       except Exception:
           pass  # si el mkdir falla, la connect de abajo reporta el error real
       return sqlite3.connect(db_path)


   def _warn_sqlite_unavailable(where: str, exc: Exception) -> None:
       """Loguea con dedup POR FIRMA (tipo + mensaje de la excepción) y throttle.

       - Firma nueva (fallo distinto)  -> WARNING una vez.
       - Misma firma dentro del intervalo -> DEBUG (silenciado, no oculto).
       - Misma firma tras _SQLITE_WARN_INTERVAL_S -> vuelve a WARNING (heartbeat),
         para que un fallo PERSISTENTE no desaparezca de los logs para siempre.
       La firma NO incluye `where` a propósito: el mismo error desde 4 call-sites
       colapsa a 1 warning (cumple el KPI 42 -> <=1), pero un error de otra causa
       (p. ej. 'disk image is malformed') sí aflora.
       """
       sig = f"{type(exc).__name__}:{exc}"
       now = time.monotonic()
       last = _SQLITE_WARN_STATE.get(sig)
       if last is None or (now - last) >= _SQLITE_WARN_INTERVAL_S:
           _SQLITE_WARN_STATE[sig] = now
           logger.warning(
               "ado_edit_ledger: SQLite no disponible (%s): %s — degradando a "
               "JSONL. Repeticiones de esta firma se omiten por %ss.",
               where, exc, int(_SQLITE_WARN_INTERVAL_S),
           )
       else:
           logger.debug("ado_edit_ledger: SQLite falló (%s): %s", where, exc)
   ```

2. Reemplazar en las **4 funciones** `sqlite3.connect(_get_db_path())` por `_connect()`, y reemplazar sus `logger.warning("ado_edit_ledger: ... : %s", exc)` de SQLite por `_warn_sqlite_unavailable("<nombre>", exc)`:

   - `_create_table_if_needed` (líneas 34-50): `con = _connect()`; en el `except` (línea 50): `_warn_sqlite_unavailable("create_table", exc)`.
   - `already_learned` (líneas 92-112): `con = _connect()` (línea 100); en el `except` (línea 107): `_warn_sqlite_unavailable("already_learned", exc)` (mantener el fallback JSONL de las líneas 108-112 tal cual).
   - `mark_learned` (líneas 115-136): `con = _connect()` (línea 121); en el `except` (línea 130): `_warn_sqlite_unavailable("mark_learned", exc)` (mantener el `_append_jsonl` best-effort de la línea 133 y el `logger.info` de fallback de la línea 136).
   - `processed_revs_for` (líneas 139-152): `con = _connect()` (línea 143); en el `except` (línea 150): `_warn_sqlite_unavailable("processed_revs_for", exc)` (mantener el fallback JSONL de la línea 152).

**Casos borde cubiertos:**
- `data_dir()` inexistente pero creable → `mkdir` lo crea → SQLite persiste (ya no cae a JSONL). Es el caso de los 42 warnings.
- `data_dir()` verdaderamente no escribible (permisos) → `mkdir` no puede → `sqlite3.connect` lanza → **una advertencia por firma** + JSONL (idempotencia preservada por `_append_jsonl`, que ya hace su propio `mkdir` en la línea 79). Si más tarde surge un fallo de **otra** causa (corrupción, disco lleno), su firma distinta **sí** aflora (C3).
- `_append_jsonl` **no se toca** (ya crea su dir padre).

**Criterio de aceptación BINARIO + comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan146_verified_fixes.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_ado_edit_ledger.py -q
```
→ ambos **PASAN**. No debe quedar `sqlite3.connect(_get_db_path())` fuera de `_connect`:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents"
Select-String -Path "backend\services\ado_edit_ledger.py" -Pattern "sqlite3\.connect\(_get_db_path\(\)\)"
```
→ **una única coincidencia**, dentro de `def _connect(`.

**Cross-ref y no-dependencia (C5):** el Plan **145** provee `services/log_throttle.log_throttled(key, logger, level, msg, *args, min_interval_s=60.0)` — dedup/rate-limit temporal por `key` — que **145 declara para 147/148** (no lista a 146 como consumidor). **Independiente del orden de aterrizaje**, 146 es **autónomo**: usa su guard local `_warn_sqlite_unavailable` + `_SQLITE_WARN_STATE`, cuya semántica (throttle por firma) es **idéntica** a `log_throttled`, de modo que migrar es trivial (reemplazar el helper por `log_throttled(sig, logger, logging.WARNING, msg, where, exc, min_interval_s=_SQLITE_WARN_INTERVAL_S)`) **si y cuando** 145 ya esté disponible. Migrar es opcional y queda **fuera de scope**. La causa raíz de la ruta mal resuelta la ataca **147**; 146 sólo aplica el `mkdir` defensivo local.

**Flag que la protege:** ninguna (fix defensivo; ver §3.1). **Default:** n/a.
**Impacto por runtime:** idéntico en los 3 (persistencia SQLite/JSONL, sin lógica por runtime). **Fallback:** JSONL append-only (ya existente).
**Trabajo del operador:** ninguno.

---

### F3 — V4: test de contrato de `Config` + nota de re-deploy

- **Objetivo (1 frase):** añadir un test que verifique la presencia de `CLAUDE_CODE_CLI_MODEL_FALLBACK` y demás atributos que el runner de Claude lee de `Config`, blindando contra regresiones; y documentar el re-deploy como acción de operador.
- **Valor:** convierte el crash `'Config' object has no attribute 'CLAUDE_CODE_CLI_MODEL_FALLBACK'` en imposible de regresar sin romper CI, y deja claro el paso de release pendiente.

**Contexto verificado:** el runner `services/claude_code_cli_runner.py` hace `from config import config` (línea 49) y lee, entre otros: `CLAUDE_CODE_CLI_MODEL` (líneas 805/814/966/1356/1966), `CLAUDE_CODE_CLI_MODEL_FALLBACK` (línea 874), `CLAUDE_CODE_CLI_BIN` (línea 2026), `CLAUDE_CODE_CLI_TIMEOUT` (línea 866), `CLAUDE_CODE_CLI_EFFORT` (`config.py:221`), `CLAUDE_CODE_CLI_SKIP_PERMISSIONS` (línea 1999), `CLAUDE_CODE_CLI_PERMISSION_MODE` (línea 2002), `CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE` (línea 623), `CLAUDE_CODE_CLI_HOOKS_ENABLED` (línea 725), `CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED` (línea 958), `CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES` (línea 963), `CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED` (línea 2145). `config = Config()` está en `config.py:1110`.

**TESTS PRIMERO (TDD).** Agregar a `tests/test_plan146_verified_fixes.py`:

```python
# ---------- V4: contrato de atributos de Config que el runner de Claude lee ----------

# Atributos que services/claude_code_cli_runner.py lee de `config`.
# Si una regresión de config.py borra cualquiera, el runner crashea en runtime
# ('Config' object has no attribute ...). Este contrato lo bloquea en CI.
_CLAUDE_RUNNER_CONFIG_ATTRS = [
    "CLAUDE_CODE_CLI_MODEL",
    "CLAUDE_CODE_CLI_MODEL_FALLBACK",   # V4: el que faltaba en deploy v1.0.76
    "CLAUDE_CODE_CLI_BIN",
    "CLAUDE_CODE_CLI_TIMEOUT",
    "CLAUDE_CODE_CLI_EFFORT",
    "CLAUDE_CODE_CLI_SKIP_PERMISSIONS",
    "CLAUDE_CODE_CLI_PERMISSION_MODE",
    "CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE",
    "CLAUDE_CODE_CLI_HOOKS_ENABLED",
    "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
    "CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES",
    "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED",
]


@pytest.mark.parametrize("attr", _CLAUDE_RUNNER_CONFIG_ATTRS)
def test_config_exposes_claude_runner_attribute(attr):
    """V4: la instancia `config` expone cada atributo crítico del runner de Claude."""
    from config import config
    assert hasattr(config, attr), (
        f"Config no expone {attr}: el runner de Claude crasheará en runtime. "
        f"Regresión de config.py (ver Plan 146 / hallazgo V4)."
    )


def test_config_model_fallback_is_nonempty_str():
    """V4: el fallback tiene un default usable (no None/vacío)."""
    from config import config
    val = config.CLAUDE_CODE_CLI_MODEL_FALLBACK
    assert isinstance(val, str) and val.strip(), "fallback debe ser un modelo no vacío"
```

> **Nota:** con el working tree actual estos tests **pasan** (el fix ya está en `config.py:216-217`). Su valor es de **regresión**: en el binario del deploy v1.0.76 habrían fallado. No se edita `config.py` en este plan.

**IMPLEMENTACIÓN:** ninguna en código de producción (el atributo ya existe). Sólo se agregan los tests de arriba.

**Criterio de aceptación BINARIO + comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan146_verified_fixes.py -q
```
→ **PASA** (todos los `test_config_exposes_claude_runner_attribute[...]` verdes + `test_config_model_fallback_is_nonempty_str`).

**Flag que la protege:** ninguna (sólo se agrega un test; el código ya está). **Default:** n/a.
**Impacto por runtime:**
- **Claude Code CLI:** directo — el contrato guarda los atributos que su runner lee.
- **Codex CLI / GitHub Copilot Pro:** no leen `CLAUDE_CODE_CLI_MODEL_FALLBACK`; su ausencia no los afecta. El contrato no los obliga (degradación = n/a). Si en el futuro se quiere el mismo blindaje para el runner de Codex, se extiende la lista con los atributos que lee `codex_cli_runner.py` — **fuera de scope** de este plan.
- **Fallback:** el propio `_spawn_claude_with_fallback` (runner, líneas 313-392) ya reintenta con `CLAUDE_CODE_CLI_MODEL_FALLBACK`; el test sólo garantiza que el atributo exista para que ese fallback no crashee.

**Trabajo del operador (ACCIÓN DE RELEASE del plan, one-time — C6):** RE-PUBLICAR el deploy para que la versión desplegada (v1.0.77+) incluya los fixes ya commiteados en el working tree. **Ojo:** el re-deploy **no es específico de V4** — un único re-publish lleva V1 + V5 + V4 al binario. En **DEV** los tres fixes surten efecto con solo reiniciar el proceso (corre de fuente), **sin** re-deploy; el re-publish solo hace falta para el **binario del DEPLOY** (donde V4 es además un crash latente en v1.0.76). Es una publicación normal (`deployment/Prepare-Publication.ps1` → `deployment/build_release.ps1`), **no** config nueva ni paso recurrente. Este plan **no** ejecuta el release (no toca código de build); sólo lo deja documentado como pendiente de operador. No dispara ninguna de las 4 excepciones duras.

---

### F4 — Verificación integral y no-regresión

- **Objetivo (1 frase):** confirmar que los tres fixes están verdes en conjunto, que el ratchet sigue consistente y que no se rompieron los tests vecinos.
- **Valor:** cierre binario del plan sin falsos verdes.

**Comandos (todos deben PASAR):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan146_verified_fixes.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_ado_edit_sweep.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_ado_edit_ledger.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_ado_edit_learning.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_harness_ratchet_meta.py -q
```

**Criterio de aceptación BINARIO:** los 5 comandos terminan con **0 fallos** (correr por archivo; NO correr la suite completa — contamina cross-file). Verificación estática final:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents"
Select-String -Path "backend\services\ado_edit_learning.py" -Pattern "import Execution\b"   # → sin coincidencias
Select-String -Path "backend\scripts\run_harness_tests.sh" -Pattern "test_plan146_verified_fixes" # → 1 coincidencia
```

**Flag:** ninguna. **Impacto por runtime:** n/a (verificación). **Trabajo del operador:** ninguno (salvo el re-deploy de F3).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Un modelo menor "arregla" sólo `Execution→AgentExecution` y deja `session_scope` importándose de `models` → nuevo `ImportError: cannot import name 'session_scope' from 'models'`. | Media | Alto | El diff de F1 (Cambio A) es explícito: **dos** líneas de import (`from models import AgentExecution` + `from db import session_scope`). El test `test_sweep_recent_runs_real_import_path_no_import_error` lo detecta (fallaría igual). |
| R2 | El fix de metadata rompe `test_ado_edit_sweep.py` (que usa `_FakeRun.metadata` dict). | Baja | Medio | El fix es backward-compatible por diseño (`getattr` prefiere `metadata_json`, cae a `.metadata` si es dict). F1 exige correr `test_ado_edit_sweep.py` verde. |
| R3 | El estado `_SQLITE_WARN_STATE` contamina entre tests (dict de módulo global). | Media | Bajo | Los tres tests de F2 hacen `monkeypatch.setattr(lm, "_SQLITE_WARN_STATE", {})` (auto-revertido por monkeypatch). |
| R4 | Olvidar registrar el test nuevo en `run_harness_tests.sh` → `test_harness_ratchet_meta.py` falla. | Media | Bajo | F0 lo hace primero y F4 lo re-verifica. |
| R5 | `sweep_recent_runs` sin `_db_runs` toca la DB real en el test. | Baja | Medio | El test **no** mockea el import pero **sí** inyecta `db.session_scope` falso (monkeypatch) → cero acceso a DB real; hermético. |
| R6 | El re-deploy (V4) se olvida y el binario sigue vulnerable. | Media | Medio | Marcado explícito como "Trabajo del operador" en F3; el test de contrato garantiza que el código a publicar es correcto. |
| R7 | `metadata_json` de runs reales no contiene `epic_ado_id` (se guarda en otra columna). | Baja | Bajo | El fix es correcto respecto a la columna real (`models.py:219`); si el dato no estuviera ahí, el sweep degrada a no-op **sin** warning (comportamiento seguro), y sería un hallazgo separado fuera de V1. |
| **R8** | **Revivir el sweep (V1) enciende trabajo de fondo real** (polling ADO `fetch_work_item_updates` + `save_observation` + `mark_learned`) que hoy NO ocurre — el daemon está gated por `STACKY_ADO_EDIT_LEARNING_ENABLED` **default ON** (`app.py:446`), así que se activa en ~todas las instalaciones. | Media | Medio | **Es el comportamiento diseñado** (Plan 60), hoy muerto por V1. Acotado por: (a) el **ledger de idempotencia** evita re-aprender `(ado_id, rev)` ya vistos → tras la 1ª pasada el trabajo por run cae a ~0; (b) solo procesa runs con `epic_ado_id`/`issue_ado_id` en metadata (la mayoría no lo tiene → `continue` sin tocar ADO, R7); (c) el `try/except` por run aísla fallos de ADO (no propaga). Si el operador quisiera mantenerlo apagado, **la flag ya existe** (`STACKY_ADO_EDIT_LEARNING_ENABLED=false`) y es la vía por UI/config; este plan **no** cambia su default. Documentado en §1/§3.3. |

---

## 6. Fuera de scope (explícito)

- **D1/D2 (trust de workspace, stall watchdog):** Plan **144**. No se tocan `claude_code_cli_runner.py`/`codex_cli_runner.py` salvo lectura para el contrato de Config.
- **D3 (reaper 120 min → cierre rápido) y D4 (enum de estados `needs_review`):** Plan **144**. Este plan **no** unifica el vocabulario de estados ni toca `agent_completion.py`.
- **404 de `/api/v1/pipeline/status`, strip ANSI, aislar pytest del logging, helper de dedup común:** Plan **145**.
- **Causa raíz de resolución de `outputs_dir`/`repo_root`/`data_dir` (V2/D8):** Plan **147**. 146 sólo aplica el `mkdir` defensivo local del ledger.
- **PAT ADO expirado, Jira sin credenciales, 502 LLM local, api-version `connectionData` (V3/V8/D6/D9):** Plan **148**.
- **`pending-task.json` inválido y excepciones tipadas en endpoints (D5/V6):** Plan **149**.
- **Refactor del reader de metadata a un helper compartido, migrar el dedup al helper de 145, extender el contrato de Config al runner de Codex:** mejoras futuras, no en este plan.

---

## 7. Glosario, Orden de implementación y DoD

### 7.1 Glosario (términos Stacky usados)
- **`sweep_recent_runs`:** barrido periódico (background) que lee `AgentExecution` recientes y aprende de ediciones humanas sobre work items de ADO (ADO edit learning, Plan 60).
- **`AgentExecution`:** modelo ORM de una ejecución de agente (`models.py:207`); su metadata operativa vive en la columna `metadata_json` (`models.py:219`) y se lee con el **accessor canónico `metadata_dict`** (property, `models.py:259-261`), **no** con `.metadata` (que es el registro `MetaData` de SQLAlchemy). El fix de F1 usa `metadata_dict` (C2).
- **`session_scope`:** context manager de sesión SQLAlchemy (`db.py:302`), **no** exportado por `models`.
- **`ado_edit_ledger`:** ledger de idempotencia (SQLite + fallback JSONL) que garantiza que cada `(ado_id, rev)` se aprende una sola vez (`services/ado_edit_ledger.py`, Plan 60 F3).
- **`config` / `Config`:** `Config` es la clase (`config.py:54`); `config = Config()` (`config.py:1110`) es la instancia que importan los runners.
- **Ratchet `HARNESS_TEST_FILES`:** lista sólo-crece en `scripts/run_harness_tests.sh` (+ paridad `.ps1`) que el meta-test `test_harness_ratchet_meta.py` verifica; todo `tests/test_*.py` debe estar ahí o en la allowlist.
- **`_FakeRun`:** dataclass de test (`test_ado_edit_sweep.py`) que simula un run con `.metadata` dict; el fix de F1 se mantiene compatible con él.

### 7.2 Orden de implementación (numerado)
1. **F0** — crear `tests/test_plan146_verified_fixes.py` (scaffold) + registrarlo en `run_harness_tests.sh` y `.ps1`; verificar `test_harness_ratchet_meta.py` verde.
2. **F1** — escribir los 2 tests de V1 (rojo) → aplicar Cambios A y B en `ado_edit_learning.py` → verde + no-regresión de `test_ado_edit_sweep.py`.
3. **F2** — escribir los 3 tests de V5 (rojo: mkdir + dedup-por-firma + rewarns-distinto) → agregar `import time`, `_connect`, `_warn_sqlite_unavailable`, `_SQLITE_WARN_STATE`/`_SQLITE_WARN_INTERVAL_S` y reemplazar los 4 call-sites en `ado_edit_ledger.py` → verde + no-regresión de `test_ado_edit_ledger.py`.
4. **F3** — escribir los tests de contrato de V4 (verdes con el working tree actual) → documentar el re-deploy como acción de operador.
5. **F4** — verificación integral (5 comandos) + checks estáticos.

> Las tres correcciones son independientes entre sí; F1/F2/F3 pueden hacerse en cualquier orden tras F0. F0 es prerequisito (ratchet).

### 7.3 Definición de Hecho (DoD global)
- [ ] `tests/test_plan146_verified_fixes.py` existe, está en `HARNESS_TEST_FILES` (`.sh` + `.ps1`) y `test_harness_ratchet_meta.py` pasa.
- [ ] `ado_edit_learning.py` importa `AgentExecution` (models) + `session_scope` (db) y lee la metadata vía el accessor canónico `metadata_dict` (`models.py:259-261`); sin referencias a `Execution` ni a `db.query(Execution)`.
- [ ] `ado_edit_ledger.py` abre SQLite sólo vía `_connect()` (con `mkdir parents=True, exist_ok=True`) y advierte con **dedup por firma + throttle** vía `_warn_sqlite_unavailable` (`_SQLITE_WARN_STATE`); un fallo de firma distinta vuelve a aflorar (test `rewarns_on_distinct`).
- [ ] `Config` expone los 12 atributos del contrato del runner de Claude (test parametrizado verde).
- [ ] Los 5 comandos de F4 terminan con 0 fallos (corridos **por archivo** con `backend/.venv/Scripts/python.exe`).
- [ ] Sin flags nuevas (justificado en §3.1). Sin trabajo recurrente de operador. Backward-compatible.
- [ ] Comportamiento de V1 documentado honestamente (R8): revive trabajo de fondo real (sweep ADO), gated por `STACKY_ADO_EDIT_LEARNING_ENABLED` default ON; el plan **no** cambia ese default.
- [ ] **Pendiente de operador (fuera del código):** re-publicar el deploy (v1.0.77+) — es el **paso de release del plan** que lleva V1+V5+V4 al binario. **DEV** ya toma los fixes al reiniciar el proceso (corre de fuente), **sin** re-deploy.

---

### Anexo — Discrepancias de anchor detectadas contra el código real (2026-07-15)
- **V1 / anchor del reporte:** el reporte dice "corregir el import al nombre real (`AgentExecution`)". Verificación real: `session_scope` **no** existe en `models.py` (está en `db.py:302`); el fix correcto requiere **dos** imports, no un simple rename. Además, el reporte no lista el segundo bug `[V]`: `ado_edit_learning.py:272-276` lee `run.metadata` (objeto `MetaData` de SQLAlchemy) en vez de la metadata real; sin arreglarlo, el sweep queda como no-op silencioso. El accessor **canónico** es la property `AgentExecution.metadata_dict` (`models.py:259-261`), que el fix reusa en vez de reimplementar el decode (C2). Ambos cubiertos en F1.
- **V1 / comportamiento (C1):** el daemon del sweep está gated por `STACKY_ADO_EDIT_LEARNING_ENABLED` **default ON** (`app.py:446`, promovido 2026-07-15) y hoy crashea en el `ImportError` **antes** de tocar ADO. El fix no es "silencioso": **revive trabajo de fondo real** (polling ADO + escritura de lecciones) en ~todas las instalaciones. Documentado en §1/§3.3 y R8.
- **V5:** confirmado `services/ado_edit_ledger.py`; los 4 call-sites `sqlite3.connect(_get_db_path())` (`_create_table_if_needed`, `already_learned`, `mark_learned`, `processed_revs_for`) carecen de `mkdir`; `_append_jsonl` (línea 79) ya lo hace.
- **V4:** confirmado `config.py:216-217` con el fix presente; `config = Config()` en `config.py:1110`; el runner lo consume vía `from config import config` (`claude_code_cli_runner.py:49`).
- **Anchors D4 / 404 / D1-D2 provistos como contexto:** pertenecen a los Planes 144/145 y quedan **fuera de scope** aquí (no son discrepancias, sólo delimitación de alcance).
