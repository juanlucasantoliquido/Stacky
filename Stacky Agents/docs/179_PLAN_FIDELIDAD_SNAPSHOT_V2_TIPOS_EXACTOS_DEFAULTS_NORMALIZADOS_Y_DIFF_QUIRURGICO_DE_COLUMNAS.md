# Plan 179 — Fidelidad Snapshot v2: tipos exactos, defaults normalizados y diff quirúrgico de columnas

**Estado:** PROPUESTO (v1, 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`).

**Serie:** Comparador de BD — núcleo v2 (fidelidad del motor). Mejora DIRECTA de la capa 1 implementada en main (planes 122-126). Relación con las capas en papel 157 (config UX), 176 (triage/gates/cierre) y 178 (radar/vigía): **cero colisión de archivos** (sección 2bis) — ninguno de los tres toca `dbcompare_snapshot.py` ni `dbcompare_diff.py`.

---

## 1. Título, objetivo y KPIs

### 1.1 Objetivo (1 frase)

Que el snapshot capture la identidad EXACTA de cada columna como datos estructurados (precision, scale, length, collation, identity, computed — cuando el dialecto los reporta) y que el diff de columnas compare esa estructura de forma quirúrgica y normalizada, matando falsos negativos (subcampos que hoy viajan aplastados dentro de un string) y falsos positivos (diferencias cosméticas de render o de mayúsculas en defaults), con compatibilidad TOTAL hacia los snapshots v1 ya persistidos.

### 1.2 Qué es hoy y cuál es el gap (con evidencia)

Hoy la captura por columna es SOLO esto (`services/dbcompare_snapshot.py:63-71`):

```python
columns.append({
    "name": col["name"],
    "type": str(col["type"]).upper(),   # string plano del tipo SQLAlchemy
    "nullable": bool(col.get("nullable", True)),
    "default": (str(default) if default is not None else None),
    "autoincrement": bool(col.get("autoincrement") or False),
})
```

y el diff de tipo es un compare de strings (`services/dbcompare_diff.py:122`):

```python
if str(sc.get("type")) != str(tc.get("type")):
```

Consecuencias verificadas:

1. **Sin estructura**: precision/scale/length viajan (cuando viajan) embebidos en el string (`NUMERIC(10, 2)`); collation, identity y computed NO se capturan en absoluto — `insp.get_columns()` de SQLAlchemy los expone (claves opcionales `identity`/`computed` del dict de columna y atributos `precision`/`scale`/`length`/`collation` del objeto de tipo) y hoy se descartan.
2. **Falsos negativos**: un cambio que el dialecto reporta solo por fuera del `str()` del tipo (identity agregada, columna convertida a computed, collation cambiada cuando el render del dialecto no la incluye) es INVISIBLE para el diff actual.
3. **Falsos positivos**: dos servers que renderizan el mismo tipo con cosmética distinta (espaciado, sinónimos de render entre versiones de SQLAlchemy/driver) disparan `column_type_changed` sin cambio real. En defaults, `_normalize_default` (`dbcompare_diff.py:78-86`) YA mata el caso `((0))` vs `(0)` (fix C1 del plan 123) — ese falso positivo NO existe en main — pero NO hace case-folding ni colapso de espacios internos: `GETDATE()` vs `getdate()` o `CONVERT(bit,0)` vs `CONVERT(BIT, 0)` son falsos positivos HOY.
4. **Sin cirugía**: cuando el tipo cambia, el `detail` dice solo `{column, source, target}` (`dbcompare_diff.py:123`) — no dice QUÉ subcampo cambió (¿precision? ¿scale? ¿collation?), que es lo que el operador necesita para decidir rápido.

Este es el diferido explícito del 176 §6 ("Snapshot v2 con precision/scale/max_length como subcampos — eventual serie v2 del comparador", prior art #6) y es el ÚNICO gap que mejora el núcleo YA implementado sin depender de los planes en papel.

### 1.3 KPIs binarios

| KPI | Criterio binario | Cómo se verifica |
|---|---|---|
| KPI-1 | Con `STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED=false`, el snapshot producido es estructuralmente idéntico a main: `version == 1` y cada columna tiene EXACTAMENTE las 5 claves v1 (`name,type,nullable,default,autoincrement`); el diff no cambia en nada. | `tests/test_plan179_snapshot_v2.py::test_off_byte_identico_a_v1` |
| KPI-2 | Con la flag ON, un cambio `NUMERIC(10,2)` → `NUMERIC(12,4)` entre dos snapshots v2 emite `column_type_changed` con `detail.changed_fields == ["precision", "scale"]`. | `tests/test_plan179_diff_v2.py::test_precision_scale_quirurgico` |
| KPI-3 | Mezcla v1/v2 (un lado con `type_detail`, el otro sin) NO produce ningún item por la mera presencia/ausencia del campo: el diff cae al comportamiento v1 idéntico a main. Test BLOQUEANTE. | `tests/test_plan179_diff_v2.py::test_mezcla_v1_v2_sin_falsos_diffs` |
| KPI-4 | En modo v2, defaults `GETDATE()` vs `getdate()` y `CONVERT(bit,0)` vs `CONVERT(BIT, 0)` NO emiten `column_default_changed` (falsos positivos muertos); `0` vs `1` SÍ lo emite. | `tests/test_plan179_diff_v2.py::test_defaults_normalizados_v2` |
| KPI-5 | En modo v2, dos strings de tipo con render cosmético distinto pero `type_detail` estructuralmente igual NO emiten `column_type_changed` (el criterio pasa a ser estructural). | `tests/test_plan179_diff_v2.py::test_render_cosmetico_no_emite` |
| KPI-6 | Un diff generado en modo v2 pasa entera la generación de scripts existente sin `ValueError` (cero kinds nuevos: `dbcompare_scripts.py:317` lanza ante kind desconocido — verificado). | `tests/test_plan179_diff_v2.py::test_scripts_no_rompen_con_detail_v2` |
| KPI-7 | La suite dbcompare preexistente (los 13 archivos `test_plan122/123/125/126_dbcompare_*.py` que tocan snapshot/diff/scripts) queda verde POR ARCHIVO sin editar NINGUNO. | comandos de F4 |

---

## 2. Por qué ahora / gap

1. **Es el único frente del comparador que mejora main hoy**: 157/176/178 están en papel; este plan endurece el motor que TODOS ellos van a consumir (el triage del 176 curará diffs más fieles; el vigía del 178 re-comparará con menos ruido y más señal — cada falso positivo que matamos acá es un falso aviso de drift que el radar no va a dar).
2. **El costo del falso negativo es real**: una columna que pasa de `DECIMAL(10,2)` a `DECIMAL(12,4)` en DEV y no en PROD es exactamente el tipo de drift que muerde en un pase (overflow, redondeo). Si el render del dialecto los aplana o los omite, hoy nadie lo ve.
3. **El costo del falso positivo también**: cada `column_default_changed` cosmético entrena al operador a ignorar la lista — el peor destino de una herramienta de diff.
4. **Onboarding literalmente nulo**: es una mejora invisible del motor. El próximo compare (del wizard o de cualquier consumidor) ya sale más fiel; el operador no configura nada, no aprende nada nuevo, no ve UI nueva.
5. **Prior art declarado**: 176 §6 lo difirió con nombre y apellido ("Snapshot v2 con precision/scale/max_length como subcampos"); este plan lo cierra sin esperar a esa serie.

---

## 2bis. Relación con 157 / 176 / 178 (intersección de archivos = vacía)

Los tres planes previos del comparador están SIN implementar al 2026-07-18. Tabla de archivos que cada uno declara tocar vs los de este plan:

| Plan | Archivos que toca (según su doc) | ¿Intersección con 179? |
|---|---|---|
| 157 (config UX) | `EnvSetupWizard.tsx`, `CredentialWarningBanner.tsx`, `dbcompare_config_import.py` (nuevo), `MigrationPanel.tsx` | NINGUNA |
| 176 (triage/gates/cierre) | `api/db_compare.py`, servicios nuevos de triage/gates/tableprefs/closure, `DbComparePage.tsx`, `SummaryHero.tsx`, `endpoints.ts` | NINGUNA |
| 178 (radar/vigía) | `services/dbcompare_watch.py` (nuevo), `services/dbcompare_baseline.py` (nuevo), `api/db_compare_watch.py` (nuevo), `app.py`, `services/dbcompare_runs.py` (kwarg aditivo), `endpoints.ts`, `DbComparePage.tsx` | NINGUNA |
| **179 (este)** | `services/dbcompare_snapshot.py`, `services/dbcompare_diff.py`, `services/harness_flags.py`, `config.py`, `tests/test_harness_flags_requires.py`, runners de tests | — |

- Los únicos archivos compartidos con los otros planes son los de REGISTRO (`harness_flags.py`, `config.py`, `test_harness_flags_requires.py`, `run_harness_tests.sh/.ps1`): todos los planes agregan bloques aditivos separados. Gotcha conocido del repo: en merges paralelos git puede duplicar una línea de cierre sin marcar conflicto — tras cualquier merge que involucre estos archivos, correr `python -m compileall` del backend y grep de cada key nueva esperando exactamente 1 declaración.
- **Este plan NO toca frontend** (cero archivos `.tsx`/`.ts`): la UI existente ya muestra el string `type` y el side-by-side compara una lista CERRADA de campos (`COMPARABLE_FIELDS = ["type", "nullable", "default", "autoincrement"]`, `frontend/src/components/dbcompare/sideBySide.ts:12`), así que el campo aditivo `type_detail` es invisible para la UI actual por construcción — sin falsos "changed" en el drill-down con mezcla v1/v2. `ColumnInfo` en TS (`dbcompareTypes.ts:149-155`) es una interface estructural: claves runtime extra no rompen nada.
- **Interacción con el 178 (cuando exista)**: el `content_hash` de un snapshot v2 difiere del de un snapshot v1 del MISMO esquema (el hash cubre el body completo, `dbcompare_snapshot.py:205-207`, y el body v2 trae más datos). Efecto sobre el chequeo de baseline del 178: su short-circuit "hash igual ⇒ sin violación" no se activará entre un baseline v1 y un snapshot v2, pero el paso siguiente es `diff_snapshots`, que en mezcla v1/v2 se comporta idéntico a main (KPI-3) y solo emite violación si hay items reales — resultado correcto, sin falsos avisos. Declarado acá para que el implementador del 178 no lo reporte como bug.

---

## 3. Principios y guardarraíles

### 3.1 Contratos

- **Snapshot v1 NO se rompe**: v2 es un SUPERSET aditivo versionado. Los snapshots v1 en disco siguen cargando (`load_snapshot`, `dbcompare_snapshot.py:261`), listando (`list_snapshots:246`) y comparando idéntico a main. Ningún snapshot persistido se migra ni se re-escribe: los v1 viejos conviven con los v2 nuevos hasta que el prune natural los recicle (`_MAX_SNAPSHOTS_PER_ALIAS = 20`, `dbcompare_snapshot.py:31`).
- **SchemaDiff v1 intacto**: el shape del diff (`{version, engine, source, target, items, summary}`, `dbcompare_diff.py:316-331`) no cambia; la tabla `_KIND_SEVERITY` (`:28-52`) no gana ni pierde entradas; los `detail` de los changes solo GANAN claves opcionales (`changed_fields`, y los dicts de columna embebidos ganan `type_detail`). `DiffChange.detail` es `Record<string, unknown>` en el frontend (`dbcompareTypes.ts:76-80`) y `kind` es `string` abierto — claves nuevas son gratis.
- **CERO kinds nuevos — decisión sellada con evidencia**: `dbcompare_scripts.py:317` hace `raise ValueError(f"kind de diff no soportado por los emitters ...")` ante cualquier kind desconocido, y el generador de scripts consume `detail["column"]`/`detail.get("source")`/`detail.get("target")` de los kinds existentes (`:199-315`). Por lo tanto v2 ENRIQUECE el detail de kinds EXISTENTES: cambios de collation/identity/computed se emiten como `column_type_changed` (semánticamente correcto: la identidad del tipo de la columna cambió; severidad `danger` apropiada; además `column_type_changed` ya está en `_DATA_BACKUP_KINDS` (`dbcompare_scripts.py:325-329`), así que el backup pareado de datos se conserva para estos cambios).
- **La regla central de compatibilidad (literal)**: el campo nuevo por columna se llama `type_detail`, es ADITIVO y opcional; el diff usa `type_detail` y las reglas v2 SOLO si AMBOS snapshots son v2 (`version == 2` en los dos); la mezcla v1 vs v2 NO produce diffs por la mera ausencia del campo y se comporta byte-idéntico a main (test BLOQUEANTE, KPI-3); los snapshots v1 en disco siguen cargando y comparando idéntico a main.

### 3.2 Flags y excepciones

- `STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED`, bool, **default ON**: es una mejora invisible read-only sin prerequisitos — **NINGUNA de las 4 excepciones duras aplica** (no conecta a nada nuevo, no publica nada afuera, no escribe en ninguna BD, no depende de credenciales/conectividad no garantizadas ni agrega costo). `requires="STACKY_DB_COMPARE_ENABLED"` (plano, profundidad 1 — jamás encadenar a flag hija), grupo `global`, categoría `comparador_bd`, alta en `_CURATED_DEFAULTS_ON` (única vía para default ON, `harness_flags.py:310` y gotcha `:3143-3147`), arista en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`, junto a las DB_COMPARE existentes `:183-185`), y `harness_defaults.env` regenerado por `scripts/export_harness_defaults.py` (PROHIBIDO editarlo a mano).
- **El gate actúa en la CAPTURA**: con ON, el snapshot nuevo sale `version: 2` con `type_detail` por columna; con OFF, la captura es byte-idéntica a main (`version: 1`, 5 claves por columna). El diff NO tiene flag propia: es PASIVO por versión de ambos inputs (usa lo nuevo sii ambos lados lo traen) — así OFF ⇒ idéntico y la mezcla es inocua POR DISEÑO, no por chequeos dispersos.
- En `api/*.py` la instancia de flags es `config.config`, NO el módulo (`api/db_compare.py:27-29`) — este plan no toca la API, pero el gate de captura en `dbcompare_snapshot.py` lee la flag con el mismo idioma de servicios: `getattr(_config.config, "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED", False)` importando `import config as _config`.

### 3.3 Diseño y calidad

- **CERO archivos nuevos de runtime** (preferencia confirmada con evidencia): todo el código vive en `dbcompare_snapshot.py` y `dbcompare_diff.py` existentes — son el lugar natural (captura y comparación), se evita el gotcha de PyInstaller collect-submodules (un submódulo nuevo que falla en el freeze aparece como `ModuleNotFoundError` tardío) y se reduce superficie. Archivos nuevos SOLO de tests (`tests/test_plan179_*.py`).
- **Determinismo**: la derivación de `type_detail` y la normalización v2 de defaults son funciones PURAS (mismo input ⇒ mismo output, sin reloj, sin red, sin disco), testeables sin BD.
- **No prometer lo que el dialecto no da**: collation/identity/computed se capturan "si el dialecto los reporta"; si no, quedan `null` y el diff degrada limpio al criterio v1 para ese subcampo. Nunca se inventa un valor.
- **Human-in-the-loop**: este plan no agrega ninguna acción automática — mejora la FIDELIDAD de lo que el operador ve; comparar, generar scripts y migrar siguen siendo decisiones humanas.
- **Mono-operador sin auth real**: nada de RBAC.
- **3 runtimes**: feature de motor backend puro (sin LLM, sin UI): idéntica en Codex CLI, Claude Code CLI y GitHub Copilot Pro; fallback N/A salvo la degradación preexistente por drivers de BD faltantes, que no cambia.
- **Tests backend por archivo** con `./venv/Scripts/python.exe` (fallback `./.venv/Scripts/python.exe`) desde `Stacky Agents/backend`; los `test_plan179_*.py` se registran en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh:20` + espejo `run_harness_tests.ps1`) o el meta-test del ratchet queda rojo.
- **Fixtures sqlite**: el registry acepta engine `sqlite` SOLO para alias `test-*` (`services/dbcompare_registry.py:80-89`) — los golden E2E usan ese carril, igual que `tests/test_plan122_dbcompare_snapshot.py`. Nota de fidelidad sqlite: SQLAlchemy parsea el tipo DECLARADO de la DDL (`NUMERIC(10,2)` refleja `precision=10, scale=2`; `VARCHAR(50)` refleja `length=50`), así que los golden de precision/scale/length son reales; collation/identity/computed en sqlite quedan `null` (degradación documentada, cubierta por unit tests con dicts armados a mano).

---

## 4. Contrato nuevo: `type_detail` v1 (subobjeto por columna, dentro de Snapshot v2)

Cada columna de un snapshot `version: 2` agrega UNA clave:

```json
{
  "name": "importe",
  "type": "NUMERIC(10, 2)",
  "nullable": false,
  "default": "((0))",
  "autoincrement": false,
  "type_detail": {
    "base": "NUMERIC",
    "precision": 10,
    "scale": 2,
    "length": null,
    "collation": null,
    "timezone": null,
    "identity": null,
    "computed": null
  }
}
```

Reglas EXACTAS de derivación (función pura, F1):

- `base`: el string `type` v1 cortado en el primer `(`: `str(col_type).upper().split("(")[0].strip()`. Nunca `null`.
- `precision`: `getattr(col_type, "precision", None)` pasado por `int()` si no es `None`; si el atributo existe pero no es convertible, `null`.
- `scale`: ídem con `getattr(col_type, "scale", None)`.
- `length`: ídem con `getattr(col_type, "length", None)`.
- `collation`: `getattr(col_type, "collation", None)` como string o `null`.
- `timezone`: `bool(getattr(col_type, "timezone", None))` si el atributo existe y no es `None`; si no, `null` (distingue "False explícito" de "el tipo no tiene noción de timezone").
- `identity`: si `col.get("identity")` (clave opcional del Inspector) es un dict no vacío ⇒ `{"start": int_o_null, "increment": int_o_null}` (con conversión defensiva); si no ⇒ `null`. `autoincrement` v1 se mantiene intacto al lado (compat).
- `computed`: si `col.get("computed")` es un dict no vacío ⇒ `{"persisted": bool(d.get("persisted") or False), "sqltext_sha256": sha256(sqltext_normalizado) | null}` donde `sqltext_normalizado` = colapsar whitespace a un espacio + strip + upper (el sqltext puede ser enorme y con formato variable: se hashea, no se persiste crudo); si no ⇒ `null`.
- Los 8 subcampos SIEMPRE presentes en un snapshot v2 (con `null` donde el dialecto no reporta): shape estable, hash estable, diff simple.

El `content_hash` sigue calculándose igual (`json.dumps(body, sort_keys=True)`, `dbcompare_snapshot.py:205-207`): al cambiar el body, un snapshot v2 tiene hash distinto de un v1 del mismo esquema — correcto (el contenido ES distinto) y con la interacción 178 ya declarada en §2bis.

---

## 5. Fases

Orden estricto: F0 → F1 → F2 → F3 → F4 → F5. Cada fase es verificable sola y deja el sistema funcional.

---

### F0 — Flag, config y arista requires

**Objetivo:** registrar `STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED` (default ON) sin ningún comportamiento nuevo.
**Valor:** kill-switch visible en el panel del arnés (categoría "Comparador de BD entre ambientes") desde el día 0.

**Archivos a editar (exactos):**

1. `Stacky Agents/backend/services/harness_flags.py`:
   - En `_CURATED_DEFAULTS_ON` (hoy contiene `"STACKY_DB_COMPARE_ENABLED"` en `:310`), agregar:
     ```python
     "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED",  # Plan 179 — fidelidad snapshot v2 (mejora invisible read-only, ninguna excepción dura aplica)
     ```
   - En `_CATEGORY_KEYS["comparador_bd"]` (`:320-324`), agregar:
     ```python
     "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED",  # Plan 179
     ```
   - En `FLAG_REGISTRY`, inmediatamente después de la FlagSpec de `STACKY_DB_COMPARE_DATA_MAX_ROWS` (`:3162-3175`), agregar copiando el idioma de las vecinas:
     ```python
     # ── Plan 179 — Fidelidad Snapshot v2 (tipos exactos + defaults normalizados) ──
     FlagSpec(
         key="STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED",
         type="bool",
         default=True,  # ON: mejora invisible read-only del motor; los snapshots nuevos capturan type_detail. OFF: captura byte-idéntica a v1. El diff es pasivo por versión (usa v2 sii ambos snapshots lo traen).
         label="Comparador BD: snapshot v2 (fidelidad de tipos)",
         description="Captura estructurada por columna (precision, scale, length, collation, identity, computed cuando el dialecto los reporta) y diff quirúrgico con defaults normalizados. OFF = snapshots v1 idénticos a antes.",
         group="global",
         requires="STACKY_DB_COMPARE_ENABLED",
     ),
     ```
2. `Stacky Agents/backend/config.py` — después del bloque del Plan 126 (`:127-133`), copiando el idioma literal de `:119-121`:
   ```python
   # ── Plan 179 — Fidelidad Snapshot v2 (mejora invisible del motor) ────────
   STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED: bool = os.getenv(
       "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED", "true"
   ).strip().lower() == "true"
   ```
3. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — en `_REQUIRES_MAP_FROZEN` (`:120`), junto a `:183-185`:
   ```python
   "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 179
   ```
4. `Stacky Agents/backend/scripts/run_harness_tests.sh` (`HARNESS_TEST_FILES`, `:20`) + espejo `run_harness_tests.ps1`: registrar `tests/test_plan179_snapshot_v2.py` y `tests/test_plan179_diff_v2.py`.
5. Regenerar `harness_defaults.env`: `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" scripts/export_harness_defaults.py`.

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan179_snapshot_v2.py` (primer bloque):**
- `test_flag_registrada_bool_default_on_requires_master`: la FlagSpec existe, `type == "bool"`, `spec.default is True`, `requires == "STACKY_DB_COMPARE_ENABLED"`.
- `test_flag_en_categoria_comparador_bd`: la key está en `_CATEGORY_KEYS["comparador_bd"]`.
- `test_config_default_on`: `config.config.STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED is True` con env limpio.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan179_snapshot_v2.py -q`
**También verdes:** `tests/test_harness_flags.py` y `tests/test_harness_flags_requires.py` (por archivo, mismo intérprete).
**Criterio de aceptación (binario):** los 3 tests nuevos + los 2 preexistentes pasan; `harness_defaults.env` regenerado por script.
**Flag:** la propia (aún sin efecto). **Runtimes:** idéntico en los 3 (motor backend). **Trabajo del operador:** ninguno.

---

### F1 — Derivación pura de `type_detail` y normalización v2 de defaults

**Objetivo:** dos funciones puras nuevas, sin tocar todavía ni la captura ni el diff.
**Valor:** el corazón determinista del plan, testeable sin BD.

**Archivos a editar:**

1. `Stacky Agents/backend/services/dbcompare_snapshot.py` — agregar (antes de `_reflect_table`):

```python
TYPE_DETAIL_KEYS = ("base", "precision", "scale", "length", "collation", "timezone", "identity", "computed")


def _int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_sqltext_for_hash(sqltext: str) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", (sqltext or "")).strip().upper()


def derive_type_detail(col: dict) -> dict:
    """Plan 179 F1 — deriva el subobjeto type_detail v1 (doc 179 §4) desde el dict
    de columna que devuelve insp.get_columns(). Función PURA: sin red, sin disco.
    Los subcampos que el dialecto no reporta quedan None — NUNCA se inventan."""
    col_type = col.get("type")
    type_str = str(col_type).upper() if col_type is not None else ""
    base = type_str.split("(")[0].strip()

    tz_attr = getattr(col_type, "timezone", None)
    identity_raw = col.get("identity")
    identity = None
    if isinstance(identity_raw, dict) and identity_raw:
        identity = {
            "start": _int_or_none(identity_raw.get("start")),
            "increment": _int_or_none(identity_raw.get("increment")),
        }
    computed_raw = col.get("computed")
    computed = None
    if isinstance(computed_raw, dict) and computed_raw:
        sqltext = computed_raw.get("sqltext")
        computed = {
            "persisted": bool(computed_raw.get("persisted") or False),
            "sqltext_sha256": (
                hashlib.sha256(_normalize_sqltext_for_hash(str(sqltext)).encode("utf-8")).hexdigest()
                if sqltext else None
            ),
        }
    return {
        "base": base,
        "precision": _int_or_none(getattr(col_type, "precision", None)),
        "scale": _int_or_none(getattr(col_type, "scale", None)),
        "length": _int_or_none(getattr(col_type, "length", None)),
        "collation": (str(getattr(col_type, "collation")) if getattr(col_type, "collation", None) else None),
        "timezone": (bool(tz_attr) if tz_attr is not None else None),
        "identity": identity,
        "computed": computed,
    }
```

2. `Stacky Agents/backend/services/dbcompare_diff.py` — agregar (después de `_normalize_default`, `:78-86`, SIN modificarla):

```python
def _normalize_default_v2(s):
    """Plan 179 F1 — normalización ENDURECIDA de defaults para modo v2 (doc 179 §5 F1).
    Reglas EXACTAS, en orden:
      1. None -> None.
      2. Strip de capas de paréntesis externos balanceados (reusa _normalize_default,
         que ya mata `((0))` vs `(0)` — fix C1 del plan 123, intacto).
      3. Colapsar todo whitespace a UN espacio + strip.
      4. Eliminar espacios adyacentes a '(' , ')' y ',' — `CONVERT(bit, 0)` == `CONVERT(bit,0)`.
      5. Si el resultado NO contiene comilla simple ('), comparar case-insensitive:
         se retorna .upper(). Si contiene comilla simple hay un literal de string y
         el case puede ser semántico: se retorna sin cambio de case (solo pasos 1-4).
    """
    s = _normalize_default(s)
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*([(),])\s*", r"\1", s)
    if "'" not in s:
        s = s.upper()
    return s
```

**Tests PRIMERO — agregar a `tests/test_plan179_snapshot_v2.py` (derivación) y crear `tests/test_plan179_diff_v2.py` (normalización):**

Derivación (`test_plan179_snapshot_v2.py`), todos con dicts/objetos fake (clase mínima con atributos, sin SQLAlchemy real):
- `test_derive_numeric_precision_scale`: type fake con `precision=10, scale=2`, str "NUMERIC(10, 2)" → `{"base": "NUMERIC", "precision": 10, "scale": 2, "length": None, ...}`.
- `test_derive_varchar_length_collation`: `length=50`, `collation="Modern_Spanish_CI_AS"` → base "VARCHAR", length 50, collation capturada.
- `test_derive_identity_dict`: `col["identity"] = {"start": 1, "increment": 1}` → `identity == {"start": 1, "increment": 1}`.
- `test_derive_computed_hashea_sqltext_normalizado`: dos sqltext con distinto whitespace/case → mismo `sqltext_sha256`; `persisted` respetado.
- `test_derive_sin_atributos_todo_null`: tipo opaco sin atributos → los 7 subcampos opcionales `None`, `base` del str.
- `test_derive_keys_estables`: `set(result.keys()) == set(TYPE_DETAIL_KEYS)` siempre.

Normalización (`test_plan179_diff_v2.py`):
- `test_norm_v2_parens_heredado`: `"((0))"` y `"(0)"` → ambos `"0"` (la conducta v1 se conserva).
- `test_norm_v2_case_funciones`: `"GETDATE()"` == `"getdate()"`.
- `test_norm_v2_espacios_comas`: `"CONVERT(bit, 0)"` == `"CONVERT(BIT,0)"`.
- `test_norm_v2_literal_string_preserva_case`: `"('Abc')"` vs `"('ABC')"` → DISTINTOS (comilla simple presente).
- `test_norm_v2_distintos_reales`: `"0"` vs `"1"` → distintos; `None` vs `"0"` → distintos.

**Comandos:**
```bash
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan179_snapshot_v2.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan179_diff_v2.py -q
```
**Criterio de aceptación:** los 11 tests de F1 verdes; `_normalize_default` original SIN diff (`git diff` no la toca); ningún caller nuevo todavía.
**Flag:** sin efecto aún (funciones sin llamadores). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — Captura v2 gated en `_reflect_table` (OFF ⇒ byte-idéntico)

**Objetivo:** que `take_snapshot` produzca `version: 2` + `type_detail` por columna con la flag ON, y byte-idéntico a main con OFF.
**Valor:** los snapshots nuevos llevan la fidelidad completa sin re-capturar nada viejo.

**Archivo a editar:** `Stacky Agents/backend/services/dbcompare_snapshot.py`:

1. Reemplazar la constante de versión única por:
   ```python
   SNAPSHOT_VERSION = 1          # shape v1 (compat: NO tocar — referencia histórica)
   SNAPSHOT_VERSION_V2 = 2       # Plan 179 — superset aditivo con type_detail por columna
   ```
2. Agregar el helper de gate (idioma de servicios, §3.2):
   ```python
   def _snapshot_v2_enabled() -> bool:
       import config as _config
       return bool(getattr(_config.config, "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED", False))
   ```
3. `_reflect_table` (`:61-71`): cambiar la firma a `def _reflect_table(insp, tname: str, schema: str, *, v2: bool = False) -> dict:` y el bucle de columnas a:
   ```python
   for col in insp.get_columns(tname, schema=schema):
       default = col.get("default")
       entry = {
           "name": col["name"],
           "type": str(col["type"]).upper(),
           "nullable": bool(col.get("nullable", True)),
           "default": (str(default) if default is not None else None),
           "autoincrement": bool(col.get("autoincrement") or False),
       }
       if v2:
           entry["type_detail"] = derive_type_detail(col)
       columns.append(entry)
   ```
   El resto de `_reflect_table` (pk/fks/indexes/uniques/checks, `:73-123`) queda INTACTO.
4. `take_snapshot` (`:144-227`): al inicio del `try`, computar `v2 = _snapshot_v2_enabled()`; pasar `v2=v2` en la llamada `_reflect_table(insp, tname, schema, v2=v2)` (`:167`); y en `body` (`:198-204`) y `result` (`:210-220`) usar `"version": (SNAPSHOT_VERSION_V2 if v2 else SNAPSHOT_VERSION)`. NADA más cambia (hash, id, persistencia, prune: intactos).

**Tests PRIMERO — agregar a `tests/test_plan179_snapshot_v2.py`** (fixtures sqlite con alias `test-*`, mismo patrón que `tests/test_plan122_dbcompare_snapshot.py`: monkeypatch de `data_dir` a `tmp_path`, registro de ambiente sqlite y DDL sembrada en un archivo sqlite temporal):
- `test_off_byte_identico_a_v1` (KPI-1): con la flag en OFF (`monkeypatch.setattr(config.config, "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED", False, raising=False)`), `take_snapshot` sobre una tabla `NUMERIC(10,2)` + `VARCHAR(50)` produce `version == 1` y CADA columna tiene EXACTAMENTE `{"name", "type", "nullable", "default", "autoincrement"}` como set de claves.
- `test_on_version_2_y_type_detail`: con ON, `version == 2` y cada columna tiene además `type_detail` con `set(keys) == set(TYPE_DETAIL_KEYS)`; para la columna `NUMERIC(10,2)`: `precision == 10 and scale == 2`; para `VARCHAR(50)`: `length == 50`.
- `test_on_content_hash_determinista`: dos `take_snapshot` seguidos del mismo esquema con ON tienen el mismo `content_hash` (el determinismo v1 se conserva en v2).
- `test_v1_persistidos_siguen_cargando`: sembrar a mano un JSON snapshot v1 en `tmp_path` y verificar `load_snapshot`/`list_snapshots`/`latest_snapshot` lo devuelven intacto con ON activo.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan179_snapshot_v2.py -q`
**También verde sin editarlo:** `tests/test_plan122_dbcompare_snapshot.py` (sus asserts son puntuales — pk/fk/index/view en `:87-90` — y no fijan el set de claves de columna; si al correrlo apareciera un assert de shape estricto que este campo rompa, es un HALLAZGO BLOQUEANTE de diseño: se reporta y se resuelve re-evaluando el gate de captura — PROHIBIDO editar el test preexistente).
**Criterio de aceptación:** 4 tests nuevos + `test_plan122_dbcompare_snapshot.py` verdes.
**Flag:** `STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED` gobierna la captura. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — Diff v2 pasivo: criterio estructural quirúrgico + defaults endurecidos

**Objetivo:** que `diff_snapshots` use las reglas v2 SOLO cuando AMBOS snapshots son v2, con `changed_fields` en el detail; en cualquier otro caso, byte-idéntico a main.
**Valor:** mata los falsos negativos y positivos de columnas, y le dice al operador exactamente QUÉ subcampo cambió.

**Archivo a editar:** `Stacky Agents/backend/services/dbcompare_diff.py`:

1. Plumbing del modo (funciones privadas, no contrato): `diff_snapshots` (`:283`) computa
   ```python
   v2_mode = int(source.get("version") or 1) >= 2 and int(target.get("version") or 1) >= 2
   ```
   y lo propaga: `_walk_object_type(..., diff_fn)` recibe en el caso "table" un `diff_fn` que cierra sobre `v2_mode` (cambiar la llamada de `:301` a `lambda s, t: _diff_table(s, t, v2_mode=v2_mode)`); `_diff_table` (`:197`) gana el kwarg `v2_mode: bool = False` y lo pasa SOLO a `_diff_columns` (pk/fk/index/unique/check quedan intactos); `_diff_view` y sequences no cambian.
2. `_diff_columns` (`:109-133`) gana el kwarg `v2_mode: bool = False` y reemplaza los dos criterios afectados:
   - **Tipo** (reemplaza `:122-123`):
     ```python
     s_td, t_td = sc.get("type_detail"), tc.get("type_detail")
     if v2_mode and isinstance(s_td, dict) and isinstance(t_td, dict):
         changed_fields = [k for k in ("base", "precision", "scale", "length", "collation", "timezone", "identity", "computed") if s_td.get(k) != t_td.get(k)]
         if not changed_fields and _all_optional_null(s_td) and _all_optional_null(t_td) and str(sc.get("type")) != str(tc.get("type")):
             # Red de seguridad: tipo opaco sin atributos en ambos lados -> cae al criterio v1.
             changed_fields = ["type"]
         if changed_fields:
             changes.append(_change("column_type_changed", {
                 "column": name, "source": sc, "target": tc, "changed_fields": changed_fields,
             }))
     elif str(sc.get("type")) != str(tc.get("type")):
         changes.append(_change("column_type_changed", {"column": name, "source": sc, "target": tc}))
     ```
     con el helper:
     ```python
     def _all_optional_null(td: dict) -> bool:
         return all(td.get(k) is None for k in ("precision", "scale", "length", "collation", "timezone", "identity", "computed"))
     ```
   - **Default** (reemplaza `:129-130`):
     ```python
     norm = _normalize_default_v2 if v2_mode else _normalize_default
     if norm(sc.get("default")) != norm(tc.get("default")):
         changes.append(_change("column_default_changed", {"column": name, "source": sc, "target": tc}))
     ```
   - Nullable (`:124-128`) y autoincrement (`:131-132`) quedan INTACTOS (ya son estructurales).
3. Semántica de `changed_fields` (documentarla como comentario junto al código): lista ordenada y cerrada de subcampos de `type_detail` que difieren; `["type"]` es el valor especial de la red de seguridad (tipo opaco). Es una clave ADITIVA del detail de `column_type_changed`: el frontend la ignora hoy (`DiffChange.detail` abierto, `dbcompareTypes.ts:79`; `ObjectDrilldown` no lee `change.detail`), el export markdown la ignora (`_change_label` solo usa `kind` + `detail.column`, `dbcompare_runs.py:255-262`) y los emitters de scripts siguen leyendo `detail["column"]`/`source`/`target` que no cambian (`dbcompare_scripts.py:229-237`).

**Tests PRIMERO — agregar a `tests/test_plan179_diff_v2.py`** (todos con snapshots dict armados a mano — sin BD; helper local `snap(version, cols_source)` que construye el shape mínimo `{version, engine, alias, id, content_hash, schemas: {"s": {"tables": {"t": {...}}, "views": {}, "sequences": []}}}`):
- `test_precision_scale_quirurgico` (KPI-2): ambos v2, `NUMERIC(10,2)` → `NUMERIC(12,4)` → 1 item con 1 change `column_type_changed` y `detail["changed_fields"] == ["precision", "scale"]`.
- `test_mezcla_v1_v2_sin_falsos_diffs` (KPI-3, BLOQUEANTE): source v1 (columnas sin `type_detail`) vs target v2 (mismas columnas con `type_detail`) con `type` strings iguales → `items == []` y `summary.parity_score == 100.0`; y el mismo par comparado en ambos órdenes.
- `test_v1_vs_v1_identico_a_main`: dos v1 con un cambio de tipo real → mismo resultado que produce main (1 `column_type_changed` sin `changed_fields` en el detail).
- `test_render_cosmetico_no_emite` (KPI-5): ambos v2, `type` strings distintos (`"NUMERIC(10, 2)"` vs `"NUMERIC(10,2)"`) pero `type_detail` idéntico → 0 changes de tipo.
- `test_tipo_opaco_red_de_seguridad`: ambos v2, subcampos todos `None` en ambos lados y `type` strings distintos → 1 `column_type_changed` con `changed_fields == ["type"]`.
- `test_identity_detectada_quirurgica`: ambos v2, mismo `type` string, `identity` `null` → `{"start":1,"increment":1}` → `changed_fields == ["identity"]` (el falso negativo v1 muerto).
- `test_collation_detectada`: ídem con `collation` `null` → `"Latin1_General_CI_AS"` → `changed_fields == ["collation"]`.
- `test_defaults_normalizados_v2` (KPI-4): ambos v2, defaults `"GETDATE()"` vs `"getdate()"` → 0 changes; `"CONVERT(bit, 0)"` vs `"CONVERT(BIT,0)"` → 0 changes; `"0"` vs `"1"` → 1 `column_default_changed`. Y en modo v1 (ambos snapshots v1) `"GETDATE()"` vs `"getdate()"` SÍ emite (conducta main intacta, documenta el antes/después).
- `test_scripts_no_rompen_con_detail_v2` (KPI-6): construir un diff v2 con `changed_fields` y pasarlo por `dbcompare_scripts.generate_parity_bundle_from_diff` (o por la función de flatten+emitters que consume items — usar el mismo entrypoint que usan los tests `test_plan125_dbcompare_flatten.py`) → no lanza `ValueError`, y la pieza generada para `column_type_changed` es la misma que con un diff v1 equivalente.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan179_diff_v2.py -q`
**Criterio de aceptación:** los 9 tests (más los 5 de F1 en el mismo archivo) verdes; `_KIND_SEVERITY` sin diff; `_normalize_default` sin diff.
**Flag:** sin lectura de flag en el diff (pasivo por versión — §3.2). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F4 — Golden E2E sqlite + suite preexistente intacta

**Objetivo:** probar el ciclo completo real (DDL → `take_snapshot` ON → cambio de DDL → segundo snapshot → `diff_snapshots`) y demostrar KPI-7.
**Valor:** evidencia end-to-end de que la fidelidad funciona con el motor real, no solo con dicts.

**Tests PRIMERO — agregar a `tests/test_plan179_snapshot_v2.py`** (carril sqlite `test-*`, `dbcompare_registry.py:80-89`):
- `test_golden_e2e_precision_change`: crear BD sqlite con `CREATE TABLE t (importe NUMERIC(10,2))`, snapshot A (ON); recrear con `NUMERIC(12,4)`, snapshot B; `diff_snapshots(A, B)` → exactamente 1 item `table/changed` con `column_type_changed` y `changed_fields == ["precision", "scale"]`.
- `test_golden_e2e_sin_cambios_parity_100`: mismo DDL dos veces → `items == []`, `parity_score == 100.0` (el ruido no aparece con v2 ON).
- `test_golden_e2e_varchar_length`: `VARCHAR(50)` → `VARCHAR(80)` → `changed_fields == ["length"]`.
- `test_golden_e2e_mezcla_con_snapshot_v1_persistido`: snapshot A tomado con flag OFF (v1), snapshot B del MISMO esquema con ON (v2) → `diff_snapshots(A, B)` da `items == []` (KPI-3 con snapshots reales, no fixtures).

**Verificación de no-regresión (KPI-7) — correr POR ARCHIVO, SIN editar ninguno:**
```bash
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan122_dbcompare_snapshot.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan122_dbcompare_api.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan122_dbcompare_registry.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan122_dbcompare_engine.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan122_dbcompare_flags.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan123_dbcompare_diff.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan123_dbcompare_runs.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan123_dbcompare_export.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan123_dbcompare_api.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan125_dbcompare_flatten.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan125_dbcompare_emitters_sqlserver.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan125_dbcompare_emitters_oracle.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan126_dbcompare_data_diff.py -q
```
**Criterio de aceptación (binario):** 4 golden nuevos verdes + los 13 archivos preexistentes verdes sin ningún diff en `tests/` fuera de los 2 archivos `test_plan179_*.py`. Si alguno de los 13 se pone rojo, es HALLAZGO BLOQUEANTE: se reporta la línea del assert y se corrige el DISEÑO de la captura/diff (el gate por flag y el modo pasivo existen exactamente para esto) — PROHIBIDO tocar el test.
**Flag:** cubierta por F2/F3. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F5 — Cierre: registro, defaults y DoD

**Objetivo:** dejar el plan auditable y el arnés coherente.
**Valor:** cero deuda administrativa; el supervisor puede verificar todo con comandos.

**Acciones:**
1. Confirmar que `tests/test_plan179_snapshot_v2.py` y `tests/test_plan179_diff_v2.py` están en `HARNESS_TEST_FILES` (`run_harness_tests.sh:20`) Y en el espejo `run_harness_tests.ps1` (hecho en F0; acá se verifica con grep).
2. Confirmar `harness_defaults.env` regenerado (contiene `STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED=true`) vía `scripts/export_harness_defaults.py` — nunca a mano.
3. `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m compileall services/dbcompare_snapshot.py services/dbcompare_diff.py` limpio.
4. Smoke manual documentado en el PR (requiere una BD real registrada; no automatizable):
   - Con la flag ON (default), tomar un snapshot de un ambiente sqlserver real → el JSON en `data\db_compare\snapshots\<alias>\` trae `"version": 2` y `type_detail` por columna con collation/identity donde el server los reporta.
   - Correr un compare del wizard entre ese ambiente y otro → el run termina `done` y la UI existente se ve idéntica a antes (el campo nuevo es invisible para la UI actual — esperado y correcto).
   - Apagar la flag por UI y tomar otro snapshot → `"version": 1` sin el campo (hot-apply del gate de captura, sin reinicio).

**Criterio de aceptación:** puntos 1-3 binarios verdes; punto 4 documentado con resultados en el PR.
**Trabajo del operador:** ninguno (el smoke lo hace quien implementa).

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | Un test preexistente asserta el shape v1 estricto de columnas y el campo aditivo lo rompe | Suite roja | Verificado ANTES de proponer: `test_plan122_dbcompare_snapshot.py` solo asserta claves puntuales (`:87-90`), y los tests de diff/scripts usan fixtures v1 armados a mano (que el modo pasivo trata idéntico a main). Si igual aparece un rojo: HALLAZGO BLOQUEANTE, se corrige el diseño (gate de captura), JAMÁS el test (F2/F4) |
| R2 | Los emitters de scripts rompen con lo nuevo | Generación de scripts caída | Sellado por diseño: CERO kinds nuevos (evidencia: `ValueError` en `dbcompare_scripts.py:317`); el detail solo GANA claves; KPI-6 lo prueba pasando un diff v2 por el generador real |
| R3 | Frontend muestra "changed" falso en el drill-down con mezcla v1/v2 | Ruido visual | Imposible por construcción: `COMPARABLE_FIELDS` es lista cerrada (`sideBySide.ts:12`) y no incluye `type_detail`; `ColumnInfo` TS ignora claves extra (`dbcompareTypes.ts:149-155`). Este plan no toca frontend |
| R4 | Oracle sin permisos de catálogo para algún subcampo (collation u otro) | Subcampo no reportado | `derive_type_detail` usa `getattr`/`col.get` defensivos → `null`; el diff con `null` en ambos lados no emite; con `null` vs valor emite `changed_fields` con ese subcampo — que ES un cambio reportado por el dialecto. Nunca se inventa un valor (§3.3) |
| R5 | sqlite sin precision "real" (afinidad de tipos) | Golden tests débiles | SQLAlchemy refleja el tipo DECLARADO en la DDL (`NUMERIC(10,2)` → `precision=10, scale=2`) — los golden de F4 son reales; collation/identity/computed en sqlite quedan `null` y se cubren con unit tests de dicts (F3) |
| R6 | Snapshots viejos v1 gigantes conviviendo con v2 | Confusión o re-captura masiva | No hay migración ni re-captura: v1 persistidos siguen cargando y comparando idéntico (KPI-3); el prune natural (`_MAX_SNAPSHOTS_PER_ALIAS = 20`, `dbcompare_snapshot.py:31`) los recicla solo |
| R7 | `content_hash` distinto entre v1 y v2 del mismo esquema confunde a consumers de hash | Short-circuits por hash no se activan | Único consumer de igualdad de hash previsto: el chequeo de baseline del 178 (en papel) — declarado inocuo en §2bis (la violación exige items>0, y la mezcla da items==0). El motor actual no compara hashes entre snapshots |
| R8 | Drift de versión de SQLAlchemy cambia el render de `str(type)` | Falsos positivos v1 reaparecen | Exactamente lo que v2 inmuniza: en modo v2 el criterio es estructural (`type_detail`), no el render (KPI-5) |
| R9 | Sesión paralela ocupa el número 179 antes del commit | Colisión de numeración (ya pasó con 171) | Número recalculado listando `docs/` inmediatamente antes del Write; si al commitear existe otro 179, renumerar el archivo completo al primer libre ANTES de commitear |
| R10 | La normalización v2 de defaults es demasiado agresiva y tapa un cambio real | Falso negativo nuevo | Reglas cerradas y conservadoras (§F1): el case-folding se SUSPENDE ante literales de string (comilla simple); solo se colapsa whitespace sintáctico. Test explícito `test_norm_v2_literal_string_preserva_case` |

---

## 7. Fuera de scope (diferidos explícitos de este plan)

- **Emitters/ALTERs enriquecidos** (usar `type_detail` para generar `ALTER ... COLLATE`, identity DDL, computed columns): diferido — colisiona con el terreno del 176 F3 y merece su propia serie de scripts v2. Limitación conocida y aceptada: un `column_type_changed` cuyo único `changed_fields` sea `["collation"]` genera hoy el mismo ALTER de tipo base que antes (el operador ve el subcampo exacto en el diff y decide).
- **Export markdown enriquecido** (imprimir `changed_fields` en el .md): el formato está congelado por el doc 123 §F4 (`export_markdown`, `dbcompare_runs.py:265-321`) y `_change_label` no imprime detail (verificado `:255-262`) — NO se toca el exporter en este plan.
- **UI nueva para `type_detail`** (mostrar subcampos en el drill-down): diferido a la serie UX del comparador; este plan es de motor y no toca frontend.
- **Snapshot v3** (comments de columnas, particiones, triggers, grants): diferido.
- **Migración/re-captura de snapshots v1 persistidos**: prohibida por diseño (conviven).
- **Masking PII y comparación de datos**: sin cambios — el data-diff del 126 no se toca.
- **Mapeo a scripts ticketeados del repo del producto (trunk/BD)**: sigue diferido como en 176 §6.

---

## 8. Glosario, orden de implementación y DoD global

### Glosario

- **Snapshot v2**: snapshot con `version: 2` cuyo único agregado es `type_detail` por columna (superset aditivo de v1).
- **`type_detail`**: subobjeto estructurado de 8 claves fijas (`base, precision, scale, length, collation, timezone, identity, computed`) derivado de la reflexión SQLAlchemy ya existente — sin queries nuevas.
- **Modo v2 (del diff)**: rama de comparación que se activa sii AMBOS snapshots son `version >= 2`; en cualquier otro caso el diff es byte-idéntico a main (pasivo).
- **`changed_fields`**: clave aditiva del detail de `column_type_changed` en modo v2 — lista exacta de subcampos que difieren; `["type"]` es la red de seguridad para tipos opacos.
- **Normalización v2 de defaults**: `_normalize_default_v2`, superset de `_normalize_default` (que queda intacta para el modo v1).
- **Golden E2E**: test que ejecuta DDL sqlite real + `take_snapshot` + `diff_snapshots` de punta a punta por el carril `test-*`.

### Orden de implementación (estricto)

F0 (flag) → F1 (funciones puras) → F2 (captura gated) → F3 (diff pasivo) → F4 (golden + no-regresión) → F5 (cierre). Nada es permutable. Cada fase termina con sus tests verdes ANTES de la siguiente (TDD: escribir los tests primero, verlos fallar por la razón correcta, implementar, verlos pasar).

### Definition of Done global

1. Los 7 KPIs de §1.3 verificados con sus tests/comandos.
2. `tests/test_plan179_snapshot_v2.py` y `tests/test_plan179_diff_v2.py` verdes POR ARCHIVO y registrados en ambos runners.
3. Los 13 archivos preexistentes de la serie dbcompare (F4) verdes SIN ediciones en `tests/` fuera de los 2 archivos nuevos.
4. `tests/test_harness_flags.py` y `tests/test_harness_flags_requires.py` verdes.
5. `harness_defaults.env` regenerado por script (contiene la flag nueva en `true`).
6. `git diff --stat` solo lista: `services/dbcompare_snapshot.py`, `services/dbcompare_diff.py`, `services/harness_flags.py`, `config.py`, `tests/test_harness_flags_requires.py`, `scripts/run_harness_tests.sh`, `scripts/run_harness_tests.ps1`, `harness_defaults.env` y los 2 tests nuevos — NADA de frontend, NADA de `api/`, NADA de `dbcompare_runs.py`/`dbcompare_scripts.py`/`dbcompare_registry.py`.
7. Con la flag OFF: captura byte-idéntica a v1 (KPI-1) y conducta global idéntica a main.
8. Smoke manual de F5 documentado en el PR.
