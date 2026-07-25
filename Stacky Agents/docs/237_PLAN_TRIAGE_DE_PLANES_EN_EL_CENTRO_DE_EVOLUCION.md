# Plan 237 — Triage de planes en el Centro de Evolución: qué falta primero, sin abrir un solo `.md`

**Estado:** PROPUESTO v1 — 2026-07-25
**Tipo:** plan de superficie + censo honesto (backend read-only + una sección nueva del Centro de Evolución)
**Depende de:** Plan 128 (tablero de planes, ya implementado), Plan 167 (Centro de Evolución, ya implementado)
**No depende de:** la serie 218/219..236 (verificado: cero colisión de propiedad de archivos, §3.1)

---

## 1. Objetivo y KPI

**Objetivo (1 párrafo).** Hoy el operador tiene **192** documentos de plan en `Stacky Agents/docs/` (contados
2026-07-25: archivos que matchean `^[0-9]{2,3}_PLAN_.*\.md$` en el directorio raíz) y **ninguna
superficie encendida por defecto** que le diga cuáles faltan. El tablero del Plan 128 existe pero su flag
nace apagada, vive en otro tab, ordena por número descendente (el plan recién propuesto tapa al plan criticado
que espera implementación) y descarta en silencio todo lo que no sea un `NN_PLAN_*.md` del directorio raíz.
Este plan lleva el inventario **al Centro de Evolución** (la vista que el operador ya abre, flag ON de fábrica),
lo **ordena por triage** — primero lo que **no está implementado**, después lo que **no está criticado**,
después lo que ya está **completado** — y convierte el censo en **honesto**: nada se descarta sin contador y
motivo, incluidos los 18 subplanes catalogados en `docs/_roadmap/serie_paridad_218.json` que todavía no tienen
documento. De yapa corrige el `next_free_number`, que hoy propone **219** — un número **reservado** — y haría
colisionar el próximo plan con la serie multi-proveedor.

**KPI / impacto esperado (medible, binario):**

| ID | Métrica | Hoy (medido 2026-07-25) | Meta | Cómo se verifica |
|----|---------|--------------------------|------|------------------|
| K1 | Planes visibles al operador sin tocar ninguna flag | **0** (`STACKY_PLANS_BOARD_ENABLED` default `"false"`, `backend/config.py:1544`) | **192** (todos los `NN_PLAN_*.md` del raíz) | `test_plan237_flag_default_on` + `GET /api/evolution/plans` con config de fábrica |
| K2 | Clicks para responder "¿qué plan implemento ahora?" | indefinido (hay que abrir docs a mano) | **0** — el primer grupo de la sección es "Sin implementar" | `test_orden_de_buckets_es_el_contratado` |
| K3 | `next_free_number` correcto | **219** (número RESERVADO por el catálogo del 218) | **237** | `test_next_free_number_effective_saltea_reservados` |
| K4 | Planes descartados en silencio por el censo | **3+** (`docs/_legacy/`) + 18 catalogados sin doc, sin contador | **0 silenciosos**: todos con contador y motivo en `census` | `test_censo_declara_todos_los_excluidos` |
| K5 | Superficies que muestran el mismo orden | 1 (tab Planes, apagado) | 2 (tab Planes + Centro de Evolución), mismo servicio puro | `test_plan237_plans_triage_endpoint.py` |

---

## 2. Por qué ahora / gap que cierra (evidencia real, `archivo:línea`)

### 2.1 Los 4 defectos medidos

1. **El tablero nace apagado.** `backend/config.py:1544-1546` define
   `STACKY_PLANS_BOARD_ENABLED = os.getenv("STACKY_PLANS_BOARD_ENABLED", "false")` y la `FlagSpec` de
   `backend/services/harness_flags.py:3642-3654` **no declara `default=`** (comentario literal en `:3652`:
   *"SIN default= (queda None: opt-in...)"*). Consecuencia probada: `App.tsx:145` consulta
   `/api/plans-board/health`, recibe `flag_enabled:false` y **el tab "Planes" nunca se pinta**
   (`App.tsx:301`). El operador tiene el inventario construido y no lo ve.
   Esto contradice la directiva vigente del operador ("toda flag nueva default ON salvo las 4 excepciones
   duras"); acá **no aplica ninguna**: es lectura de archivos locales, sin egreso, sin escritura, sin
   credenciales, sin tokens ociosos.

2. **El orden es inútil para decidir.** `backend/services/plans_board.py:304`:
   `plans.sort(key=lambda c: (-c["number"], c["filename"]))`. El plan 237 recién propuesto aparece **arriba**
   del 216, que ya está criticado y espera implementación. Para saber qué falta hay que leer 192 filas.

3. **El censo pierde datos en silencio.** `scan_plan_files` (`plans_board.py:82-115`) itera **no recursivo**
   (`docs_dir.iterdir()`), matchea solo `^(\d{2,3})_PLAN_(.+)\.md$` (`:22`) y descarta sin contador:
   `docs/_legacy/10_PLAN_*.md`, `16_PLAN_*.md`, `17_PLAN_*.md` (3 archivos), cualquier archivo > 2 MB
   (`_MAX_FILE_BYTES`, `:30`) y cualquier `OSError` de lectura (`:96-101`). El operador ve un total que
   **no dice de qué universo salió**.

4. **`next_free_number` propone un número reservado.** `plans_board.py:118-131` devuelve `max(NN_)+1 = 219`.
   Pero `docs/_roadmap/serie_paridad_218.json` (generado y validado por el Plan 218 F7) declara **19 subplans**
   ocupando **218..236**. Proponer el 219 hoy rompe `test_plan218_serie_integridad.py` y duplica numeración —
   el mismo accidente que ya ocurrió y quedó documentado como incidente de colisión de numeración.

### 2.2 Lo que SÍ existe y hay que reusar (no reinventar nada)

| Pieza | Dónde | Cómo se reusa |
|-------|-------|----------------|
| Parser de estado de planes | `backend/services/plans_board.py:35-79` (`normalize_estado`, `parse_plan_header`) | **Sin tocar.** Ya devuelve `PROPUESTO / CRITICADO / IMPLEMENTADO / IMPLEMENTADO_PARCIAL / SIN_ESTADO`. |
| Ledger del supervisor | `plans_board.py:134-177` (`load_ledger`, `ledger_info_for`) + `docs/_supervision/ledger.json` | **Sin tocar.** Ya calcula `doc_drift` por SHA-256 y `estado_efectivo = "APROBADO"`. |
| Acción sugerida copiable | `plans_board.py:180-252` (`suggest_next_action`) | **Sin tocar** salvo un caso nuevo (`SIN_DOCUMENTO`, F3). Ya trae `command` (slash de Claude Code CLI) **y** `natural_language` (fallback Codex/Copilot). |
| Cache TTL 15 s | `plans_board.py:374-392` (`get_board_cached`) | La sección nueva consume el **mismo** cache: cero costo extra de I/O. |
| Catálogo de subplanes | `docs/_roadmap/serie_paridad_218.json` (`subplans[].number/title/slug/priority/milestone`) | Fuente de los planes **previstos sin documento** y de los números reservados. |
| Patrón de sección del Centro de Evolución | `frontend/src/evolution/KnowledgeSection.tsx:66-83` (estado `loading/hidden/error/ready` + `health()` → `flag_enabled`) | Se copia literal para `PlansSection.tsx`. |
| Punto de montaje | `frontend/src/pages/EvolutionCenterPage.tsx:483-491` | Se inserta `<PlansSection />` **antes** de `<FitnessSection />`. |

---

## 3. Principios y guardarraíles (no negociables — se codifican en los tests)

- **G1 — Cero trabajo extra para el operador.** Todo default **ON**. No se pide configurar nada, no aparece un
  paso manual nuevo, no hay wizard. La sección se ve sola al abrir el tab "Evolución" que ya existe.
  **Ninguna de las 4 excepciones duras aplica** (no hay bypass de revisión humana, no hay acción destructiva ni
  irreversible, no hay prerequisito externo — lee archivos del propio repo y degrada a vacío si no están —, y no
  reduce la seguridad: es solo lectura y no expone contenido nuevo, solo el encabezado que ya expone el Plan 128).
- **G2 — Human-in-the-loop innegociable.** La sección **nunca ejecuta** un plan, ni critica, ni supervisa, ni
  commitea. Ofrece **texto copiable** que el operador pega y corre él. Cero botones que disparen agentes.
  Verificado por `test_plan237_seccion_no_expone_endpoints_de_escritura`.
- **G3 — Paridad de 3 runtimes.** Nada de este plan depende del runtime: es un lector de archivos + una tabla.
  La única superficie sensible al runtime es la **acción copiable**, que ya trae dos variantes
  (`command` = slash de Claude Code CLI; `natural_language` = frase para pegar en Codex CLI o GitHub Copilot Pro).
  **F5 obliga a renderizar las dos**, y el test lo verifica.
- **G4 — Aditivo y backward-compatible.** Ninguna clave del contrato `§4.4` del Plan 128 se renombra ni se borra.
  Solo se **agregan** claves. Las funciones existentes conservan su firma; lo nuevo va en funciones nuevas.
- **G5 — Cero pollers.** Carga on-mount + botón "Refrescar". Igual que el resto del Centro de Evolución.
- **G6 — Cero deuda visual nueva.** El `.tsx` nuevo va con **cero** literales de color hexadecimal, **cero**
  atributos de estilo en línea y **cero** diálogos modales nativos del navegador. Todo el color vive en el
  `.module.css`. (El ratchet `src/__tests__/uiDebtRatchet.test.ts` arranca en 0 para archivos nuevos.)
- **G7 — Nada se descarta en silencio.** Todo archivo que el censo saltea suma a un contador con motivo.
- **G8 — No degrada performance.** Se reusa el cache TTL de 15 s. El único I/O nuevo es leer los `*.json` de
  `docs/_roadmap/` (5 archivos, < 50 KB) **dentro** del mismo `build_board` ya cacheado.

### 3.1 Verificación de colisiones con la serie 218 (hecha, no prometida)

Ninguno de los 9 archivos que toca este plan aparece en `owns_files` de ningún subplan de
`docs/_roadmap/serie_paridad_218.json` (comprobado 2026-07-25 recorriendo las 19 entradas).
Los archivos de este plan son: `backend/config.py`, `backend/services/harness_flags.py`,
`backend/services/harness_flags_help.py`, `backend/services/plans_board.py`, `backend/api/plans_board.py`,
`backend/api/evolution.py`, `frontend/src/api/endpoints.ts`, `frontend/src/pages/EvolutionCenterPage.tsx`,
`frontend/src/pages/PlansBoardPage.tsx`, `frontend/src/plansBoard/model.ts`, más 4 archivos **nuevos**.

---

## 4. Comandos de test (usar EXACTAMENTE estos)

> **Backend** — desde `Stacky Agents/backend`, PowerShell:
> `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q`
> **SIEMPRE por archivo**, nunca la suite completa (contaminación cross-run conocida: `importlib.reload(config)`
> de `test_harness_flags.py` ensucia la corrida).
>
> **Frontend** — desde `Stacky Agents/frontend`:
> `npx vitest run <ruta/al/archivo.test.ts>` y `npx tsc --noEmit`.
> **SIEMPRE por archivo** (contaminación de orden conocida en vitest).

---

## 5. Fases

---

### F0 — Encender el inventario: `STACKY_PLANS_BOARD_ENABLED` pasa a default ON

**Objetivo (1 frase):** que el operador vea sus planes sin prender nada a mano.
**Valor:** desbloquea K1 (0 → 192 planes visibles) con 4 líneas de cambio.

**Archivos a editar (rutas exactas):**
1. `Stacky Agents/backend/config.py`
2. `Stacky Agents/backend/services/harness_flags.py`
3. `Stacky Agents/backend/services/harness_flags_help.py`
4. `Stacky Agents/backend/tests/test_harness_flags.py`

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

**Cambio 2 — `backend/services/harness_flags.py:3642-3654`** (dentro de la `FlagSpec` cuya `key` es
`STACKY_PLANS_BOARD_ENABLED`): reemplazar las dos líneas de comentario que empiezan con `# SIN default=` y
`# SIN requires=` por `default=True,` (y dejar el resto igual):
```diff
         group="global",
-        # SIN default= (queda None: opt-in, no curada en _CURATED_DEFAULTS_ON).
-        # SIN requires= (no tiene master). SIN env_only= (queda UI-editable).
+        default=True,   # Plan 237: promovido a ON (lectura local, sin egreso). Curado en _CURATED_DEFAULTS_ON.
+        # SIN requires= (no tiene master). SIN env_only= (queda UI-editable).
     ),
```

**Cambio 3 — `backend/tests/test_harness_flags.py`**, set `_CURATED_DEFAULTS_ON` (empieza en `:467`):
agregar, al final del set y antes de la llave de cierre, exactamente estas **dos líneas** (una sola key: la
segunda key del plan se cura en F4, cuando su `FlagSpec` exista — ver la nota al final de la fase):
```python
    # ── Plan 237 — inventario de planes visible de fábrica ──
    "STACKY_PLANS_BOARD_ENABLED",
```
> **Por qué es obligatorio:** `test_default_known_only_for_curated` (mismo archivo, `:816-826`) exige
> `spec.default is True ⇔ key ∈ _CURATED_DEFAULTS_ON`. Poner `default=True` sin tocar el set deja el test en rojo.

**Cambio 4 — `backend/services/harness_flags_help.py:1361-1366`**, entrada `"STACKY_PLANS_BOARD_ENABLED"`:
reemplazar el campo `on_effect` por (≤ 240 chars, empieza con `"Si "` — lo exige
`test_plain_help_on_off_start_with_si`):
```python
        on_effect="Si la activás (viene así de fábrica): aparece el tab 'Planes' y la sección 'Planes' del Centro de Evolución, con el próximo número libre y una acción copiable por plan. No ejecuta nada por sí solo.",
```

**Tests PRIMERO (TDD).** Archivo nuevo: `Stacky Agents/backend/tests/test_plan237_plans_triage.py`
(el mismo archivo crece en F1/F2/F3; en F0 solo lleva estos 2 casos):
```python
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
    import pathlib, re
    src = pathlib.Path(__file__).resolve().parents[1] / "config.py"
    texto = src.read_text(encoding="utf-8")
    m = re.search(r'os\.getenv\(\s*\n?\s*"STACKY_PLANS_BOARD_ENABLED",\s*"(\w+)"', texto)
    assert m is not None, "no se encontró el getenv de STACKY_PLANS_BOARD_ENABLED en config.py"
    assert m.group(1) == "true"
```
> **CORRECCIÓN al cambio 3 — `_CURATED_DEFAULTS_ON` se edita en DOS TIEMPOS.** Curar una key que todavía
> no existe en `FLAG_REGISTRY` rompe **dos** tests del mismo archivo: `test_declared_default_true_set`
> (`:806-814`) hace `by_key[key]` y levanta **KeyError**, y `test_default_known_only_for_curated`
> (`:816-826`) asserta igualdad exacta contra el registry. Como
> `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED` recién nace en F4:
> **en F0 se agrega SOLO `"STACKY_PLANS_BOARD_ENABLED"`**, y **en F4 —cuando la `FlagSpec` ya existe— se
> agrega `"STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED"`**.
> O sea, el bloque del cambio 3 en F0 es únicamente
> ```python
>     # ── Plan 237 — inventario de planes visible de fábrica ──
>     "STACKY_PLANS_BOARD_ENABLED",
> ```
> y en F4 agregá debajo `"STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED",`.

**Comandos de verificación (los 3 tienen que quedar verdes):**
```
& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_harness_flags_help.py -q
```

**Criterio de aceptación BINARIO:** los 3 comandos anteriores terminan con `0 failed`.

**Flag que la protege:** `STACKY_PLANS_BOARD_ENABLED`, **default ON**. Ninguna de las 4 excepciones duras aplica
(lectura local, sin egreso, sin escritura, sin credenciales, sin tokens ociosos).
**Impacto por runtime:** ninguno — es configuración del backend, idéntica en Codex CLI, Claude Code CLI y
GitHub Copilot Pro. **Fallback:** si `docs/` no existe (deploy congelado), `docs_dir_found:false` y la UI muestra
el estado vacío que ya existe (`PlansBoardPage.tsx:212-213`).
**Trabajo del operador: ninguno.**

---

### F1 — Buckets de triage: el orden que responde "¿qué falta?"

**Objetivo (1 frase):** clasificar cada plan en un bucket y ordenar por bucket antes que por número.
**Valor:** K2 — el primer grupo de la lista es, siempre, lo que falta implementar.

**Archivos a editar:**
1. `Stacky Agents/backend/services/plans_board.py`
2. `Stacky Agents/backend/tests/test_plan128_plans_board_parser.py` (un assert; ver abajo)

**Contrato de buckets (LITERAL — el orden es el contrato, no una sugerencia).**
Agregar después de `_LEDGER_OK_VEREDICTOS` (`:32`):
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

# estado_efectivo -> bucket. Cualquier estado desconocido cae en SIN_CRITICAR
# (se prefiere pedir revisión humana antes que esconder un plan al fondo).
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

**Cambio en `build_board`** (`:270-316`). Dentro del `for c in cards_raw:`, después de calcular
`estado_efectivo` (`:277`), agregar `bucket = triage_bucket(estado_efectivo)` y **agregar la clave al card**
(aditivo, nada se borra):
```diff
             "estado_efectivo": estado_efectivo,
+            "triage_bucket": bucket,
```
Y reemplazar el `sort` de `:304` por:
```diff
-    plans.sort(key=lambda c: (-c["number"], c["filename"]))
+    # Plan 237: primero el triage, y DENTRO de cada bucket el número descendente
+    # (lo más nuevo primero), con el filename como desempate estable.
+    plans.sort(key=lambda c: (triage_rank(c["triage_bucket"]), -c["number"], c["filename"]))
```
Y después de `totals["total"] = len(plans)` (`:308`) agregar el resumen por bucket:
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

**Tests PRIMERO.** En `Stacky Agents/backend/tests/test_plan237_plans_triage.py` agregar:
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

**Cambio OBLIGATORIO en el test del Plan 128 (medido: es el único que se pone en rojo).**
`Stacky Agents/backend/tests/test_plan128_plans_board_parser.py:253` — `test_build_board_orden_y_totales`
arma 3 planes: `10_PLAN_A` (`PROPUESTO`), `30_PLAN_B` (`CRITICADO v1`), `20_PLAN_C` (`IMPLEMENTADO`), y
asserta `numbers == [30, 20, 10]`. Con el triage, 30 cae en `SIN_IMPLEMENTAR` (rank 0), 10 en `SIN_CRITICAR`
(rank 1) y 20 en `SIN_SUPERVISAR` (rank 3). Editar así (el orden nuevo **es** el contrato del Plan 237):
```diff
-    assert numbers == [30, 20, 10]
+    # Plan 237: el orden es por bucket de triage, no por número.
+    # 30=CRITICADO -> SIN_IMPLEMENTAR; 10=PROPUESTO -> SIN_CRITICAR; 20=IMPLEMENTADO -> SIN_SUPERVISAR.
+    assert numbers == [30, 10, 20]
```
Ningún otro test del Plan 128 asume orden (verificado 2026-07-25 sobre los 4 archivos `test_plan128_*`).

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q`
**+ no-regresión:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan128_plans_board_parser.py -q`

**Criterio BINARIO:** ambos comandos `0 failed`.
**Flag:** `STACKY_PLANS_BOARD_ENABLED` (default ON, F0). No hace falta flag propia: el orden es una mejora del
mismo payload y la flag maestra ya lo apaga entero.
**Impacto por runtime:** ninguno (lógica pura de Python). **Fallback:** N/A.
**Trabajo del operador: ninguno.**

---

### F2 — Censo honesto: nada se descarta sin contador y motivo

**Objetivo (1 frase):** que el total del tablero declare de qué universo salió y qué dejó afuera y por qué.
**Valor:** K4 — el operador deja de preguntarse si los 192 que ve son todos los que tiene.

**Archivo a editar:** `Stacky Agents/backend/services/plans_board.py`

**Cambio.** Agregar una función nueva **sin tocar la firma de `scan_plan_files`** (que sigue devolviendo
`list[dict]` para no romper los tests del Plan 128), y hacer que la vieja delegue en la nueva:
```python
def scan_plan_files_with_census(docs_dir: Path) -> tuple[list[dict], dict]:
    """Igual que scan_plan_files, pero devolviendo (planes, censo).

    census = {
      "files_seen": int,          # entradas de archivo en el directorio raíz
      "plans_parsed": int,        # NN_PLAN_*.md efectivamente parseados
      "skipped_not_a_plan": int,  # NN_ que no son _PLAN_, y todo lo demás
      "skipped_oversize": int,    # > _MAX_FILE_BYTES
      "skipped_unreadable": int,  # OSError al leer o al stat
      "skipped_subdirs": int,     # planes NN_PLAN_*.md en subdirectorios (p.ej. _legacy/)
      "subdir_examples": list[str],  # hasta 5 rutas relativas, para que el operador sepa cuáles
    }
    NUNCA lanza: cualquier problema suma a un contador.
    """
```
Pseudocódigo (entradas, salidas, casos borde):
```
census = {todas las claves en 0, subdir_examples: []}
si no docs_dir.exists(): devolver ([], census)
para entry en sorted(docs_dir.iterdir(), key=name):
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
    try: full_text = entry.read_text(utf-8, errors="replace")
    except OSError: census["skipped_unreadable"] += 1; continuar
    ... (idéntico al cuerpo actual de scan_plan_files, líneas :102-114) ...
    census["plans_parsed"] += 1
devolver (results, census)


def scan_plan_files(docs_dir: Path) -> list[dict]:      # firma INTACTA (G4)
    return scan_plan_files_with_census(docs_dir)[0]
```
En `build_board`, reemplazar `cards_raw = scan_plan_files(docs_dir)` (`:259`) por
`cards_raw, census = scan_plan_files_with_census(docs_dir)` y agregar `"census": census,` al `return`.

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

def test_scan_plan_files_conserva_su_firma(tmp_path):
    """G4: el Plan 128 sigue llamando scan_plan_files(dir) -> list."""
    from services.plans_board import scan_plan_files
    (tmp_path / "01_PLAN_OK.md").write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    out = scan_plan_files(tmp_path)
    assert isinstance(out, list) and len(out) == 1 and out[0]["number"] == 1

def test_censo_de_docs_reales_no_pierde_nada():
    """Sobre el docs/ real: parseados + no-planes + oversize + ilegibles == vistos."""
    from services.plans_board import docs_dir_default, build_board
    c = build_board(docs_dir_default(), unpushed_paths=None)["census"]
    assert (c["plans_parsed"] + c["skipped_not_a_plan"]
            + c["skipped_oversize"] + c["skipped_unreadable"]) == c["files_seen"]
    assert c["skipped_subdirs"] >= 3    # docs/_legacy/ tiene 3 planes archivados
```

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q`
**Criterio BINARIO:** `0 failed` y, además,
`& ".venv\Scripts\python.exe" -m pytest tests\test_plan128_plans_board_parser.py tests\test_plan128_plans_board_endpoints.py -q` → `0 failed`.
**Flag:** `STACKY_PLANS_BOARD_ENABLED` (default ON). **Impacto por runtime:** ninguno.
**Trabajo del operador: ninguno.**

---

### F3 — Planes previstos sin documento + `next_free_number` que respeta reservas

**Objetivo (1 frase):** mostrar los planes que un roadmap ya comprometió pero que todavía no tienen `.md`, y
dejar de proponer números reservados.
**Valor:** K3 (219 → 237) y el bucket `SIN_DOCUMENTO` con los 18 subplanes pendientes de la serie 218.

**Archivo a editar:** `Stacky Agents/backend/services/plans_board.py`

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
Pseudocódigo:
```
root = docs_dir / _ROADMAP_DIRNAME
si no root.exists() o no root.is_dir(): devolver []
out, vistos = [], set()
para f en sorted(root.glob("*.json")):
    try: data = json.loads(f.read_text(utf-8, errors="replace"))
    except (OSError, ValueError): continuar          # nunca lanza
    si no es dict: continuar
    subplans = data.get("subplans");  si no es list: continuar
    para e en subplans:
        si no es dict: continuar
        n = e.get("number");  si no es int: continuar
        si n en vistos: continuar                     # primer roadmap gana
        vistos.add(n)
        out.append({"number": n,
                    "title": str(e.get("title") or f"Plan {n}"),
                    "slug": str(e.get("slug") or ""),
                    "priority": e.get("priority"),
                    "milestone": e.get("milestone"),
                    "source": f.name})
devolver out ordenado por number


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
En `build_board`: después del `for` que arma `plans`, y **antes** del `sort`:
```python
    numeros_con_doc = {c["number"] for c in cards_raw}
    planned = build_planned_cards(docs_dir, numeros_con_doc)
    for card in planned:
        plans.append(card)
        totals["SIN_DOCUMENTO"] = totals.get("SIN_DOCUMENTO", 0) + 1
```
y cambiar `"next_free_number": next_free_number(docs_dir),` (`:313`) por
`"next_free_number": next_free_number_effective(docs_dir),` agregando además
`"next_free_number_raw": next_free_number(docs_dir),` y
`"reserved_count": len(reserved_numbers(docs_dir)),`.

En `Stacky Agents/backend/api/plans_board.py:39`, cambiar
`next_n = plans_board.next_free_number(docs_dir) if docs_dir.exists() else None` por
`next_n = plans_board.next_free_number_effective(docs_dir) if docs_dir.exists() else None`.

> **Ojo (caso borde real):** el número 218 **sí** tiene documento, así que **no** aparece como
> `SIN_DOCUMENTO`; sí aparecen los 18 subplanes 219..236. `numeros_con_doc` se calcula sobre `cards_raw`
> (planes parseados), no sobre `plans`, para no auto-excluir las cards que se están agregando.

**Tests PRIMERO.** En `test_plan237_plans_triage.py`:
```python
def test_next_free_number_effective_saltea_reservados(tmp_path):
    import json
    from services.plans_board import next_free_number, next_free_number_effective
    (tmp_path / "18_PLAN_ORQ.md").write_text("# Orq\n\n**Estado:** IMPLEMENTADO\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps(
        {"subplans": [{"number": 19, "title": "A"}, {"number": 20, "title": "B"}]}), encoding="utf-8")
    assert next_free_number(tmp_path) == 19          # el crudo colisiona
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
    assert load_roadmap_entries(tmp_path) == []
    assert build_board(tmp_path, unpushed_paths=None)["plans"] == []

def test_planes_catalogados_sin_doc_entran_como_SIN_DOCUMENTO(tmp_path):
    import json
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

def test_docs_reales_proponen_237_y_listan_los_18_subplanes():
    """Sobre el docs/ real, con el catálogo del Plan 218 vivo."""
    from services.plans_board import docs_dir_default, build_board
    board = build_board(docs_dir_default(), unpushed_paths=None)
    assert board["next_free_number"] >= 237
    assert board["next_free_number"] not in {e for e in range(219, 237)}
    sd = [p["number"] for p in board["plans"] if p["triage_bucket"] == "SIN_DOCUMENTO"]
    assert 219 in sd and 236 in sd and 218 not in sd
```

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage.py -q`
**+ no-regresión obligatoria** (el catálogo del 218 tiene su propio guardián):
`& ".venv\Scripts\python.exe" -m pytest tests\test_plan218_serie_integridad.py -q`

**Criterio BINARIO:** ambos `0 failed`, y
`& ".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'.'); from services.plans_board import docs_dir_default, next_free_number_effective as f; print(f(docs_dir_default()))"`
imprime **237**.
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
- editar `Stacky Agents/backend/services/harness_flags.py`
- editar `Stacky Agents/backend/services/harness_flags_help.py`
- editar `Stacky Agents/backend/tests/test_harness_flags.py` (curar la key nueva — ver abajo)
- editar `Stacky Agents/backend/scripts/run_harness_tests.sh` (ratchet)
- crear `Stacky Agents/backend/tests/test_plan237_plans_triage_endpoint.py`

**Flag nueva:** `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED`, **default ON**, `group="global"`,
`requires="STACKY_EVOLUTION_CENTER_ENABLED"`.

**Curado obligatorio (el segundo tiempo del cambio 3 de F0).** En `backend/tests/test_harness_flags.py`,
dentro de `_CURATED_DEFAULTS_ON` (`:467`), debajo de la línea que agregó F0:
```diff
     # ── Plan 237 — inventario de planes visible de fábrica ──
     "STACKY_PLANS_BOARD_ENABLED",
+    "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED",
```
Y agregar a `test_plan237_plans_triage_endpoint.py`:
```python
def test_flag_de_la_seccion_default_on():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED")
    assert spec.default is True
    assert spec.requires == "STACKY_EVOLUTION_CENTER_ENABLED"
```

`backend/config.py` — junto al bloque del Plan 167 (después de `STACKY_EVOLUTION_CYCLE_ENABLED`, `:1557-1560`):
```python
    # ── Plan 237 — Sección "Planes" del Centro de Evolución (solo lectura) ──
    STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED: bool = os.getenv(
        "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

`backend/services/harness_flags.py` — inmediatamente después de la `FlagSpec` de
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

`backend/services/harness_flags_help.py` — entrada nueva en `PLAIN_HELP` (obligatoria:
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

`backend/api/evolution.py` — agregar el gate y el handler (import de `services` **lazy**, como el resto del
archivo; el blueprint ya tiene `url_prefix="/evolution"`, así que la ruta final es `/api/evolution/plans`):
```python
def _plans_triage_enabled() -> bool:
    return _enabled() and bool(getattr(_cfg, "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED", False))


@bp.get("/plans/health")
def plans_health():
    # Siempre 200 (patrón del /health de este mismo módulo): la UI lo usa para gatear la sección.
    return jsonify({"ok": True, "flag_enabled": _plans_triage_enabled()})


@bp.get("/plans")
def plans_triage():
    if not _plans_triage_enabled():
        return _disabled_resp()
    from services import plans_board  # lazy

    refresh = request.args.get("refresh", "").strip() == "1"
    board = plans_board.get_board_cached(refresh=refresh)
    return jsonify(board)
```

> **Por qué reusa `get_board_cached` y no arma nada propio:** el cache TTL de 15 s ya existe
> (`plans_board.py:374-392`); dos superficies pegándole al mismo cache no agregan I/O (G8).

**Tests PRIMERO.** Archivo nuevo `Stacky Agents/backend/tests/test_plan237_plans_triage_endpoint.py`
(copiar el patrón de fixtures de `tests/test_plan128_plans_board_endpoints.py`, que ya arma la app):
```python
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
    assert "triage_totals" in body and "census" in body
    assert all("triage_bucket" in p for p in body["plans"])

def test_plans_404_con_su_flag_off(client, monkeypatch):
    from config import config as cfg
    monkeypatch.setattr(cfg, "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED", False)
    assert client.get("/api/evolution/plans").status_code == 404
    assert client.get("/api/evolution/plans/health").get_json()["flag_enabled"] is False

def test_plans_404_con_la_flag_maestra_off(client, monkeypatch):
    from config import config as cfg
    monkeypatch.setattr(cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)
    assert client.get("/api/evolution/plans").status_code == 404

def test_plans_no_depende_del_flag_del_tab_planes(client, monkeypatch):
    """La sección de Evolución vive aunque el tab 'Planes' esté apagado."""
    from config import config as cfg
    monkeypatch.setattr(cfg, "STACKY_PLANS_BOARD_ENABLED", False)
    assert client.get("/api/evolution/plans").status_code == 200

def test_plan237_seccion_no_expone_endpoints_de_escritura():
    """G2: el blueprint de evolution no gana ningún POST/PUT/DELETE por este plan."""
    import re, pathlib
    src = pathlib.Path("api/evolution.py").read_text(encoding="utf-8")
    bloque = src[src.index("def _plans_triage_enabled"):]
    assert not re.search(r"@bp\.(post|put|delete|patch)", bloque)
```

> **Nota para quien implemente:** `monkeypatch.setattr(cfg, ...)` sobre la **instancia** `config.config`
> es lo que funciona; leer/parchear el **módulo** `config` devuelve el default y no cambia nada
> (`getattr(_cfg, ...)` en `api/evolution.py:19` usa `from config import config as _cfg`, o sea la instancia).

**Registro obligatorio en el ratchet.** Editar `Stacky Agents/backend/scripts/run_harness_tests.sh` y agregar,
junto a las 4 líneas `tests/test_plan128_plans_board_*.py` (`:245-248`), dos líneas nuevas:
```
  tests/test_plan237_plans_triage.py
  tests/test_plan237_plans_triage_endpoint.py
```
> Sin esto, `test_harness_ratchet_meta.py` queda **rojo** ("Tests no clasificados").

**Comandos:**
```
& ".venv\Scripts\python.exe" -m pytest tests\test_plan237_plans_triage_endpoint.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_harness_ratchet_meta.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_flag_wiring.py -q
& ".venv\Scripts\python.exe" -m pytest tests\test_evolution_endpoints.py -q
```
**Criterio BINARIO:** los 4 con `0 failed`.
**Flag:** `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED`, **default ON** (ninguna excepción dura aplica: solo lectura
local, sin egreso, sin escritura, sin credenciales, sin costo de tokens).
**Impacto por runtime:** ninguno — es un endpoint Flask de lectura, idéntico bajo Codex CLI, Claude Code CLI y
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

export interface PlansTriageDto {
  ok: boolean; docs_dir_found: boolean; git_available: boolean;
  next_free_number: number; next_free_number_raw?: number; reserved_count?: number;
  triage_order: string[]; triage_totals: Record<string, number>;
  totals: Record<string, number>;
  census: { files_seen: number; plans_parsed: number; skipped_not_a_plan: number;
            skipped_oversize: number; skipped_unreadable: number;
            skipped_subdirs: number; subdir_examples: string[] };
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
  const fuera = c.skipped_subdirs + c.skipped_oversize + c.skipped_unreadable;
  if (fuera === 0) return null;
  const partes: string[] = [];
  if (c.skipped_subdirs) partes.push(`${c.skipped_subdirs} archivados en subcarpetas`);
  if (c.skipped_oversize) partes.push(`${c.skipped_oversize} demasiado grandes`);
  if (c.skipped_unreadable) partes.push(`${c.skipped_unreadable} ilegibles`);
  return `${c.plans_parsed} planes leídos · fuera del listado: ${partes.join(", ")}.`;
}
```

**`PlansSection.tsx`** — componente, copiando el patrón de `KnowledgeSection.tsx:66-83`:
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
  <SectionHeader title="Planes" actions={<Button variant="ghost" size="sm" onClick={refrescar}>↻ Refrescar</Button>} />
  <Card>  fila de resumen:
     "Próximo Nº libre: {next_free_number}"  (+ si next_free_number_raw !== next_free_number:
        texto "…{reserved_count} números reservados por el roadmap")
     un chip por bucket: {BUCKET_META[b].label} {triage_totals[b]}   -> className={styles[BUCKET_META[b].tone]}
     si censusSummary(census) !== null -> <p className={styles.census}>{censusSummary(census)}</p>
  <Input> filtro de texto (value=texto, onChange=setTexto)
  para cada grupo de groupByBucket(filterByText(plans, texto)):
     si cards.length === 0 -> saltear el grupo (no ensuciar)
     <h4 className={styles[BUCKET_META[bucket].tone]}>{label} ({cards.length})</h4>
     <p className={styles.hint}>{hint}</p>
     <table>: Nº | Título | Estado | Supervisión | Push | Acción sugerida
        Nº: {number_str} + si duplicate, badge "DUP"
        Título: {title} + subtítulo con version/fecha
        Supervisión: ledger===null ? "—" : ledger.doc_drift===true ? "drift" : `OK ${ledger.veredicto}`
        Push: unpushed===null ? "—" : unpushed ? "pendiente" : "ok"
        Acción: {suggested_action.label} + DOS botones de copiar (G3):
           "Copiar comando"  -> suggested_action.command ?? suggested_action.natural_language
           "Copiar en texto" -> suggested_action.natural_language
        (copiar = navigator.clipboard.writeText dentro de try/catch; si falla, Toast de error)
render (status==="hidden") -> null
render (status==="loading") -> <SkeletonList />
render (status==="error")   -> <EmptyState variant="generic" title="No se pudieron leer los planes" message={errorMsg} />
```

**Restricciones DURAS del `.tsx` nuevo (las verifica el ratchet, G6):**
- **cero** literales de color hexadecimal (todos los colores viven en `PlansSection.module.css`),
- **cero** atributos de estilo en línea (nada de objetos de estilo pasados por prop),
- **cero** diálogos modales nativos del navegador,
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
> Va **antes** de `<FitnessSection />` (o sea, primera de las secciones montadas en `:483-491`) porque es la
> respuesta a "¿qué hago ahora?", que es lo que el operador busca al entrar.

**Tests PRIMERO.** `Stacky Agents/frontend/src/evolution/plansTriageModel.test.ts`:
```ts
describe("plansTriageModel", () => {
  it("BUCKET_ORDER es el contrato: sin implementar primero, completado último", () => {
    expect(BUCKET_ORDER).toEqual(["SIN_IMPLEMENTAR","SIN_CRITICAR","SIN_DOCUMENTO","SIN_SUPERVISAR","COMPLETADO"]);
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
  it("censusSummary nombra cada motivo de exclusión", () => { /* subcarpetas + grandes + ilegibles */ });
});
```

**Comandos:**
```
npx vitest run src/evolution/plansTriageModel.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx tsc --noEmit
```
**Criterio BINARIO:** los 3 verdes. Además, verificación manual de una línea desde `Stacky Agents/frontend`:
```
npx vitest run src/__tests__/uiDebtRatchet.test.ts
```
debe pasar **sin regenerar el baseline** — o sea, `PlansSection.tsx` aporta 0 a los tres contadores.

**Flag:** `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED` (default ON). Con la flag OFF el componente devuelve `null`
y el Centro de Evolución queda **exactamente** como hoy.
**Impacto por runtime:**
- *Claude Code CLI*: el botón "Copiar comando" copia el slash listo (`/implementar-plan-stacky 216`).
- *Codex CLI*: no hay slash commands ⇒ el operador usa "Copiar en texto" (frase natural). **Los dos botones se
  renderizan siempre**, así que no hay detección de runtime ni configuración.
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
   dependencias del `useMemo` de `:117`), y una columna nueva **"Etapa"** en la tabla que muestra
   `card.triage_bucket`. **No** se toca el orden en el cliente: viene del backend.

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

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta, en el plan) |
|---|--------|--------------|------------------------------------|
| R1 | Poner `default=True` sin curar la key deja `test_default_known_only_for_curated` en rojo | **Alta** (ya pasó antes) | F0 cambio 3 agrega **las dos** keys a `_CURATED_DEFAULTS_ON` en la misma edición |
| R2 | Los tests nuevos no registrados rompen `test_harness_ratchet_meta` | **Alta** (ya pasó antes) | F4 obliga a agregar las 2 líneas a `run_harness_tests.sh:245-248` |
| R3 | Cambiar el `sort` rompe un test del Plan 128 que asume orden por número | **Confirmado** (medido, no estimado) | Es exactamente **un** test y ya está identificado: `backend/tests/test_plan128_plans_board_parser.py:253` `test_build_board_orden_y_totales`. F1 lo actualiza en la misma edición (ver "Cambio obligatorio en el test del Plan 128"). Ningún otro test del 128 asume orden |
| R4 | `docs/_roadmap/` con un JSON de otra forma (`PARIDAD_ADO_GITLAB.md`, `estado_real_serie_gitlab.json`) hace explotar el lector | Media | `load_roadmap_entries` filtra por `glob("*.json")` + `isinstance` en cada nivel y devuelve `[]` ante cualquier problema; `test_roadmap_corrupto_no_rompe` lo prueba |
| R5 | Archivo nuevo `.tsx` con estilos en línea rompe el ratchet de deuda visual | Media (patrón recurrente) | G6 lo declara como restricción dura y F5 lo verifica con `uiDebtRatchet.test.ts` **sin regenerar baseline** |
| R6 | Sesión paralela sobre el mismo árbol se lleva cambios ajenos al commitear | Media (el árbol es compartido) | Commitear **siempre** con pathspec explícito (`git commit -- "<ruta>" ...`); prohibido `reset`, `amend` y `rebase` |
| R7 | El operador tenía `STACKY_PLANS_BOARD_ENABLED=false` en su `.env` y no ve el cambio | Baja | El default solo aplica cuando la variable **no** está seteada; la ayuda llana actualizada (F0 cambio 4) dice "viene así de fábrica" y el panel de flags muestra el valor efectivo |
| R8 | El bucket `SIN_DOCUMENTO` mete 18 filas de ruido para quien no usa la serie 218 | Baja | Es un grupo **colapsable por posición** (3.º de 5, después de lo accionable) y el filtro "Etapa" de F6 lo excluye en un click; con `docs/_roadmap/` vacío el bucket queda vacío y F5 **no renderiza grupos vacíos** |

---

## 7. Fuera de scope (explícito)

- **Ejecutar** planes, críticas o supervisiones desde la UI. La sección es de solo lectura + copiar (G2).
- Editar el `**Estado:**` de un doc desde la UI (sería escritura sobre el repo).
- Inferir el estado real leyendo el código (eso es `/supervisar-implementaciones-planes`, ya existe).
- Recorrer `docs/_legacy/` como planes vivos: se **cuentan** (F2) pero no se listan.
- Unificar los dos tabs en uno solo, borrar `PlansBoardPage` o mover el tab de lugar.
- Cambiar el contrato de `docs/_roadmap/serie_paridad_218.json` o tocar la serie 219..236.
- Notificaciones, badges en la barra superior o cualquier superficie fuera del tab "Evolución" y el tab "Planes".

---

## 8. Glosario (para quien implemente sin conocer el dominio)

| Término | Qué significa acá |
|---------|-------------------|
| **Plan** | Un documento `Stacky Agents/docs/NN_PLAN_<SLUG>.md`. `NN` es un número de 2 o 3 dígitos de una secuencia **compartida** con checklists e incidentes. |
| **Pipeline de planes** | `proponer` → `criticar` → `implementar` → `supervisar`. Cuatro skills distintas; cada una deja rastro (el encabezado `**Estado:**` del doc y/o el ledger). |
| **`**Estado:**`** | Línea del encabezado del doc, parseada por `parse_plan_header`. Valores normalizados: `PROPUESTO`, `CRITICADO`, `IMPLEMENTADO`, `IMPLEMENTADO_PARCIAL`, `SIN_ESTADO`. |
| **Ledger de supervisión** | `docs/_supervision/ledger.json`. El supervisor marca ahí `veredicto: APROBADO` con el `doc_sha256` del momento. |
| **`doc_drift`** | El doc cambió **después** de que el supervisor lo aprobó (SHA-256 actual ≠ el del ledger) ⇒ la aprobación ya no vale. |
| **`estado_efectivo`** | `"APROBADO"` si el ledger aprobó y no hay drift; si no, el estado del doc. Lo calcula `build_board`. |
| **Bucket de triage** | Los 5 grupos que crea este plan. El orden ES el contrato. |
| **Flag del arnés** | Interruptor declarado en `FLAG_REGISTRY` (`services/harness_flags.py`), reflejado en `config.py` y editable desde el panel de flags de la UI. |
| **Excepción dura** | Las 4 únicas razones para que una flag nazca OFF: bypass de revisión humana, acción destructiva/irreversible, prerequisito no garantizado, o menos seguridad. **Ninguna aplica a este plan.** |
| **Ratchet** | Test que congela una métrica para que solo pueda mejorar (deuda visual, cobertura del arnés). |
| **Runtime** | El motor que ejecuta a los agentes: Codex CLI, Claude Code CLI o GitHub Copilot Pro. |
| **`SIN_DOCUMENTO`** | Plan comprometido en un roadmap de `docs/_roadmap/` que todavía no tiene su `.md`. |

---

## 9. Orden de implementación (numerado, en este orden exacto)

1. **F0** — flags a default ON (`config.py`, `harness_flags.py`, `harness_flags_help.py`, `_CURATED_DEFAULTS_ON`) + los 2 tests de F0. Verificar `test_harness_flags.py` y `test_harness_flags_help.py`.
2. **F1** — `TRIAGE_BUCKETS`, `triage_bucket`, `triage_rank`, nuevo `sort`, `triage_order`/`triage_totals`. Verificar + no-regresión del Plan 128.
3. **F2** — `scan_plan_files_with_census` + `census` en el board. Verificar + no-regresión del Plan 128.
4. **F3** — `load_roadmap_entries`, `reserved_numbers`, `next_free_number_effective`, `build_planned_cards`, swap en `api/plans_board.py:39`. Verificar + `test_plan218_serie_integridad.py`.
5. **F4** — flag nueva + `/api/evolution/plans` + `/api/evolution/plans/health` + archivo de tests de endpoint + **registro en `run_harness_tests.sh`**. Verificar los 4 comandos.
6. **F5** — `plansTriageModel.ts` (+ su test), `PlansSection.tsx`, `PlansSection.module.css`, `endpoints.ts`, montaje en `EvolutionCenterPage.tsx`. Verificar vitest + `tsc --noEmit` + ratchet de deuda visual.
7. **F6** — filtro y columna "Etapa" en el tab "Planes". Verificar vitest + `tsc --noEmit`.
8. **Cierre** — actualizar el `**Estado:**` de este doc a `IMPLEMENTADO` con fecha y agregar una sección
   "§10 Reporte de implementación" con los desvíos reales y los comandos corridos.

---

## 10. Definición de Hecho (DoD) — todo binario

- [ ] Con la configuración de fábrica (sin ninguna variable de entorno seteada), abrir el tab **Evolución**
      muestra la sección **Planes** con los 5 grupos, y el primer grupo no vacío es **"Sin implementar"**.
- [ ] `GET /api/evolution/plans` responde **200** con `triage_order`, `triage_totals`, `census` y
      `triage_bucket` en **todos** los elementos de `plans`.
- [ ] `GET /api/evolution/plans` responde **404** con `STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED=false`,
      y también con `STACKY_EVOLUTION_CENTER_ENABLED=false`.
- [ ] El tab **Planes** aparece sin tocar ninguna flag, y su tabla llega ordenada por triage.
- [ ] `next_free_number` del board devuelve **237** sobre el `docs/` real (no 219).
- [ ] Los 18 subplanes 219..236 aparecen en el bucket **`SIN_DOCUMENTO`**; el 218 **no**.
- [ ] `census` cierra la cuenta: `plans_parsed + skipped_not_a_plan + skipped_oversize + skipped_unreadable == files_seen`, y `skipped_subdirs >= 3`.
- [ ] Estos comandos terminan con `0 failed` (desde `Stacky Agents/backend`, uno por uno):
      `tests\test_plan237_plans_triage.py`, `tests\test_plan237_plans_triage_endpoint.py`,
      `tests\test_harness_flags.py`, `tests\test_harness_flags_help.py`, `tests\test_flag_wiring.py`,
      `tests\test_harness_ratchet_meta.py`, `tests\test_evolution_endpoints.py`,
      `tests\test_plan128_plans_board_parser.py`, `tests\test_plan128_plans_board_endpoints.py`,
      `tests\test_plan128_plans_board_flag.py`, `tests\test_plan128_plans_board_git.py`,
      `tests\test_plan218_serie_integridad.py`.
- [ ] Estos comandos terminan verdes (desde `Stacky Agents/frontend`, uno por uno):
      `npx vitest run src/evolution/plansTriageModel.test.ts`,
      `npx vitest run src/plansBoard/model.test.ts`,
      `npx vitest run src/__tests__/uiDebtRatchet.test.ts` (**sin** regenerar baseline),
      `npx tsc --noEmit`.
- [ ] `PlansSection.tsx` no contiene colores hexadecimales, ni estilos en línea, ni diálogos nativos.
- [ ] Ningún endpoint de escritura nuevo; la sección solo lee y copia al portapapeles.
- [ ] Las dos variantes de copiado (comando y frase natural) se renderizan siempre, en todos los buckets.
- [ ] Commit con pathspec explícito de los archivos de este plan; **sin `git push`** salvo pedido del operador.
