# Plan 263 — Tablero de planes denso y ningún plan sin estado: fallback único, migración con evidencia y guardia anti-regresión

**Estado:** PROPUESTO v1 (2026-07-27) · **Autor:** pipeline `proponer-plan-stacky` · **Juez:** pendiente (`criticar-y-mejorar-plan`)

---

## 1. Objetivo y KPI

El Tablero de Planes muestra hoy **78 de 212 planes (36,8 %) con estado `SIN_ESTADO`**, y para esos 78 la
UI no ofrece **ninguna** acción: `allowedActionsForCard("SIN_ESTADO", null)` devuelve `[]`
(`frontend/src/plansBoard/__tests__/actions.test.ts:18-19`). Son planes invisibles al pipeline: no se
pueden criticar, ni implementar, ni supervisar desde el tablero. Además, el tablero es **sordo al
sistema de densidad global** del Plan 150: **31 de 46** declaraciones de espaciado de
`PlansBoardPage.module.css` están hardcodeadas en `rem`/`px` y no responden al toggle
cómodo/compacto, por lo que en pantallas chicas el tablero desperdicia altura y muestra menos cards.

Este plan cierra las dos cosas con un solo criterio: **un plan nunca tiene estado nulo**. Se aplica
`IMPLEMENTADO` como fallback determinista, se marca explícitamente cuando el estado fue **inferido**
(para no mentir), se ofrece una migración a disco con evidencia y confirmación humana, y se instala un
ratchet que impide que un plan nuevo nazca sin estado.

| KPI | Antes (medido 2026-07-27) | Después (criterio binario) |
|---|---|---|
| **KPI-1** Planes sin acción disponible en el tablero | **78** | **0** |
| **KPI-2** Declaraciones de espaciado sordas a la densidad en `PlansBoardPage.module.css` | **31** | **0** |
| **KPI-3** `estado_efectivo` con valor `SIN_ESTADO` en la respuesta de `/api/plans-board/list` | **78** | **0** |
| **KPI-4** Planes nuevos que pueden guardarse sin `**Estado:**` sin que nada avise | ilimitado | **0** (ratchet rojo) |
| **KPI-5** Cards visibles sin scroll en el tablero a 1080 px de alto, densidad `compacto` | ~7 | **≥ 11** |

Comandos que miden KPI-1..KPI-4: ver §8 (DoD).

---

## 2. Por qué ahora / gap que cierra

Los últimos planes leídos (255 fallas mudas, 256 intake sin pérdida, 257 observabilidad antirruido,
258 telemetría veraz, 259 alta de proyecto GitLab) comparten una misma tesis: **ningún artefacto puede
quedar en un limbo silencioso**. El 256 lo dice para los artefactos de intake, el 258 para los ledgers.
El Tablero de Planes es el último lugar donde ese limbo sigue vivo: 78 documentos catalogados,
parseados y mostrados, pero clasificados en un estado que la propia UI trata como "no hacer nada".

El Plan 237 construyó el triage y el Plan 196 (IMPLEMENTADO F0..F6, 2026-07-26) le puso los botones de
acción. Ambos asumieron que el estado del documento era confiable. No lo es: el 36,8 % de los planes
nunca escribió su línea `**Estado:**`. Este plan cierra ese supuesto sin tocar el diseño de 237/196.

**El fallback elegido no es arbitrario y no rompe el pipeline.** Con `IMPLEMENTADO`, un plan huérfano
cae en el bucket `SIN_SUPERVISAR` (`services/plans_board.py:58`) y su acción sugerida pasa a ser
**"Supervisar"** (`services/plans_board.py:525-534`). El supervisor
(`/supervisar-implementaciones-planes`) es exactamente la herramienta que **audita el código y
determina el estado real**. Es decir: el fallback no inventa una verdad, **rutea el plan hacia la
auditoría que la resuelve**. Ese es el argumento arquitectónico central de este plan.

> **Riesgo declarado por escrito (R1, §6):** el fallback muestra como "Implementado (inferido)" planes
> que verificablemente **no** están implementados — p. ej. `243`, `247`..`252`. Por eso el fallback
> **nunca** se aplica en silencio: viaja siempre acompañado de `estado_inferido: true`, la UI lo
> rotula "inferido" y la acción sugerida dice explícitamente que el estado no está declarado. La
> verdad se escribe a disco sólo por la migración con evidencia de F3, que es opt-in y confirmada.

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad.** Todo lo de este plan es backend Python + frontend TS + CSS: **no invoca
   ningún modelo**. Corre idéntico bajo Codex CLI, Claude Code CLI y GitHub Copilot Pro. El único punto
   que dispara una corrida es el botón "Supervisar" **ya existente** del Plan 196, que ya tiene su
   propia paridad. Fallback por runtime: ninguno necesario (no hay dependencia de runtime).
2. **Cero trabajo extra para el operador.** F1, F2, F4 y F5 son automáticos e invisibles. F3 (escritura
   a disco) es opt-in con flag **OFF** citando la categoría **(B)**.
3. **Human-in-the-loop innegociable.** La migración de F3 **nunca** corre sola: requiere flag encendida
   + click + confirmación con el diff a la vista. No hay barrido, ni daemon, ni autocorrección.
4. **Mono-operador sin auth.** Nada de RBAC ni multiusuario.
5. **Backward-compatible.** `SIN_ESTADO` sigue existiendo en el tipo `EstadoPlan` y en
   `_ESTADO_A_BUCKET` como defensa: un deploy viejo del frontend contra un backend nuevo (o al revés)
   no rompe. Las firmas públicas de `services/plans_board.py` no cambian de forma incompatible: los
   parámetros nuevos son *keyword-only con default*.
6. **Reusar lo existente.** Densidad: tokens `--space-*` del Plan 150 (`frontend/src/theme.css:100-108`
   y `:250-259`). Ratchet: patrón de baseline JSON ya usado por `silence_ratchet_baseline.json` y
   `uiDebtBaseline.json`. Flags: patrón triple `config.py` + `FlagSpec` + `_CURATED_DEFAULTS_ON`.
7. **No degradar.** F1 es aritmética pura sobre datos ya parseados: **cero I/O nuevo**, cero llamadas de
   red, cero costo de tokens. El cache TTL de 15 s (`services/plans_board.py:698`) no se toca.

---

## 4. Glosario

| Término | Significado en este plan |
|---|---|
| **estado normalizado** | Salida de `normalize_estado()` (`services/plans_board.py:73-86`): uno de `PROPUESTO`, `CRITICADO`, `IMPLEMENTADO`, `IMPLEMENTADO_PARCIAL`, `SIN_ESTADO`. |
| **estado resuelto** | **NUEVO**: el normalizado, salvo que sea `SIN_ESTADO` → entonces `IMPLEMENTADO`. Lo calcula `resolve_estado()`. |
| **estado efectivo** | Ya existe (`services/plans_board.py:568`): el resuelto, salvo que el ledger lo apruebe sin drift → entonces `APROBADO`. Es lo que consume la UI. |
| **estado inferido** | **NUEVO**: `True` cuando el documento no declaraba estado y se aplicó el fallback. |
| **ledger** | `Stacky Agents/docs/_supervision/ledger.json`: qué planes aprobó el supervisor, con el sha256 del doc. |
| **drift del doc** | El sha256 actual del `.md` ≠ el que registró el supervisor ⇒ el doc cambió después de aprobarse. |
| **bucket de triage** | Etapa del Plan 237: `SIN_IMPLEMENTAR`, `SIN_CRITICAR`, `SIN_DOCUMENTO`, `SIN_SUPERVISAR`, `COMPLETADO`. |
| **ratchet** | Test que congela una deuda conocida en un baseline JSON y **falla si crece**. Sólo se puede achicar. |
| **densidad** | Sistema del Plan 150: `<html data-density="compacto">` re-apunta los tokens `--space-*`. |

---

## 5. Fases

### F0 — Flags (patrón triple, exacto)

**Objetivo.** Dar de alta las 3 flags del plan sin romper los meta-tests del arnés.

**Archivos a editar (3, exactos):**

1. `Stacky Agents/backend/config.py` — insertar **después** de la línea 1922 (fin del bloque
   `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED`, ver `config.py:1918-1922`):

```python
    # Plan 263 — el tablero nunca muestra un plan con estado nulo.
    STACKY_PLANS_ESTADO_FALLBACK_ENABLED: bool = os.getenv(
        "STACKY_PLANS_ESTADO_FALLBACK_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED: bool = os.getenv(
        "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_PLANS_NORMALIZE_APPLY_ENABLED: bool = os.getenv(
        "STACKY_PLANS_NORMALIZE_APPLY_ENABLED", "false"
    ).strip().lower() in ("1", "true", "yes")
```

> **Nota literal para el implementador:** copiá el sufijo `.strip().lower() in (...)` EXACTAMENTE como
> lo escriben las líneas 1911-1922 del archivo real. Si el patrón vigente ahí difiere, gana el del
> archivo, no el de este documento.

2. `Stacky Agents/backend/services/harness_flags.py` — agregar 3 `FlagSpec` inmediatamente después del
   bloque `STACKY_PLANS_PIPELINE_ACTIONS_ENABLED` (`harness_flags.py:4545-4558`):

```python
    # ── Plan 263 — ningún plan sin estado + migración con evidencia ──
    FlagSpec(
        key="STACKY_PLANS_ESTADO_FALLBACK_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON.
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
        default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="Vista previa de normalizacion de estados",
        description=(
            "Plan 263 — Calcula, SOLO EN MEMORIA, que linea **Estado:** habria que "
            "escribir en cada plan sin estado, con la evidencia que la respalda "
            "(ledger, commits, fase del doc). No escribe nada."
        ),
        group="global",
        requires="STACKY_PLANS_BOARD_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PLANS_NORMALIZE_APPLY_ENABLED",
        type="bool",
        # OFF por CATEGORIA (B): escribe en un sistema REAL del operador. Edita los
        # .md de "Stacky Agents"/docs/ en su working tree — los mismos archivos que
        # el operador tiene sin commitear. La escritura vive en
        # services/plans_estado_migration.py::apply_estado_migration.
        default=False,
        label="Aplicar la normalizacion de estados a los .md",
        description=(
            "Plan 263 — Escribe la linea **Estado:** en los planes que no la tienen, "
            "uno por uno, con confirmacion y diff a la vista. Nunca corre sola. "
            "El commit y el push siguen siendo manuales."
        ),
        group="global",
        requires="STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED",
    ),
```

3. `Stacky Agents/backend/services/harness_flags.py` — agregar **sólo las dos ON** a la tupla
   `_CURATED_DEFAULTS_ON`, junto a `"STACKY_PLANS_PIPELINE_ACTIONS_ENABLED"` (`harness_flags.py:350`):

```python
        "STACKY_PLANS_ESTADO_FALLBACK_ENABLED",     # Plan 263
        "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED",   # Plan 263
```

> `STACKY_PLANS_NORMALIZE_APPLY_ENABLED` **NO** va en `_CURATED_DEFAULTS_ON` (nace OFF).

**Tests (correr, no escribir nuevos):**

```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
```

**Criterio binario.** Los dos comandos salen con exit code 0 y `test_default_known_only_for_curated`
pasa. Si falla, es porque una flag `default=True` quedó fuera de `_CURATED_DEFAULTS_ON`.

**Flag que la protege:** las tres son las flags del plan. Defaults declarados arriba: 2 ON, 1 OFF con
justificación categoría (B) escrita en el propio código.

**Impacto por runtime:** ninguno — son flags de configuración, sin llamada a modelo.
**Trabajo del operador: ninguno.**

---

### F1 — Backend: `resolve_estado()` y el fallback único (núcleo puro, TDD)

**Objetivo.** Que ningún card salga de `build_board()` con `estado_efectivo == "SIN_ESTADO"`, y que
todo card diga si su estado fue inferido.

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
| 9 | `build_board(tmp_docs, None)` con un `.md` **sin** `**Estado:**` | el card tiene `estado_efectivo == "IMPLEMENTADO"`, `estado_inferido is True`, `triage_bucket == "SIN_SUPERVISAR"` |
| 10 | idem 9 | `card["suggested_action"]["kind"] == "supervisar"` |
| 11 | idem 9 | `"no declara" in card["suggested_action"]["natural_language"]` (la sugerencia AVISA que fue inferido) |
| 12 | `build_board` con un `.md` **con** `**Estado:** PROPUESTO v1` | `estado_inferido is False` y `estado_efectivo == "PROPUESTO"` |
| 13 | `build_board` sobre un doc sin estado **pero aprobado en el ledger sin drift** | `estado_efectivo == "APROBADO"` (el ledger sigue ganando) y `estado_inferido is True` |
| 14 | `build_board(tmp_docs, None)` sobre 3 docs sin estado | `"SIN_ESTADO" not in board["totals"]` y `board["totals"]["inferidos"] == 3` |
| 15 | flag OFF (`monkeypatch` de `config.config.STACKY_PLANS_ESTADO_FALLBACK_ENABLED = False`) | el card vuelve a `estado_efectivo == "IMPLEMENTADO"`… **NO**: vuelve a `"SIN_ESTADO"` y `estado_inferido is False` (comportamiento pre-260 byte-idéntico) |

> **Aviso al implementador (memoria del repo, gotcha conocido):** para leer la flag usá
> **`config.config.STACKY_PLANS_ESTADO_FALLBACK_ENABLED`** (la *instancia*), no `config.STACKY_...`
> (el *módulo*). El módulo devuelve el default y mata la rama OFF, dejando el test 15 en falso verde.

**Cambios (diff ilustrativo).**

(a) Constantes nuevas, junto a las de §4.1 (después de `plans_board.py:34`):

```python
# ── Plan 263 — el fallback de estado, en UN solo literal ────────────────────
ESTADO_FALLBACK = "IMPLEMENTADO"
ESTADOS_VALIDOS: tuple[str, ...] = (
    "PROPUESTO", "CRITICADO", "IMPLEMENTADO", "IMPLEMENTADO_PARCIAL",
)
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
    (comportamiento pre-Plan-260).
    """
    valor = (estado_normalizado or "").strip().upper()
    if valor in ESTADOS_VALIDOS:
        return valor, False
    if not _fallback_activo():
        return (valor or "SIN_ESTADO"), False
    return ESTADO_FALLBACK, True
```

(c) `suggest_next_action()` (`plans_board.py:471-543`) — agregar un parámetro **keyword-only con
default** (no rompe llamadores existentes) y hacer que la sugerencia avise:

```python
 def suggest_next_action(
     estado: str, ledger_info: dict | None, unpushed: bool | None, number_str: str,
+    *, estado_inferido: bool = False,
 ) -> dict:
```

y, justo antes del `return` de la rama `IMPLEMENTADO/IMPLEMENTADO_PARCIAL`
(`plans_board.py:525-534`), reemplazar el texto por:

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
> con la flag OFF sigue siendo alcanzable, y con la flag ON queda como defensa muerta. No la borres.

(d) `build_board()` (`plans_board.py:561-591`) — resolver antes de aplicar el ledger:

```python
-        estado_efectivo = "APROBADO" if (ledger_ok and doc_drift is not True) else c["estado"]
-        action = suggest_next_action(c["estado"], ledger_info, unpushed, c["number_str"])
+        estado_resuelto, estado_inferido = resolve_estado(c["estado"])
+        estado_efectivo = "APROBADO" if (ledger_ok and doc_drift is not True) else estado_resuelto
+        action = suggest_next_action(
+            estado_resuelto, ledger_info, unpushed, c["number_str"],
+            estado_inferido=estado_inferido,
+        )
```

y en el dict `card` agregar **una** clave (después de `"estado_efectivo": estado_efectivo,`,
`plans_board.py:581`):

```python
            "estado_inferido": estado_inferido,
```

(e) Totales (`plans_board.py:610-612`) — agregar el contador para las estadísticas:

```python
    totals["inferidos"] = sum(1 for c in plans if c.get("estado_inferido"))
```

> **Cuidado:** las cards `SIN_DOCUMENTO` que arma `build_planned_cards()` (`plans_board.py:397-422`)
> **no** pasan por `resolve_estado` y no tienen la clave. Por eso arriba se usa `.get(...)`. Además,
> en `build_planned_cards` agregá `"estado_inferido": False,` al dict del card
> (`plans_board.py:409`) para que **todas** las cards tengan la misma forma — el frontend no debe
> discriminar.

**Comando de test:**

```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan263_estado_fallback.py" -q
```

> **Gotcha del repo (SQLITE_LOCKED bajo pytest):** este archivo **no toca la DB**, así que no es
> flaky. Si aun así aparece un `SQLITE_LOCKED`, corré el archivo solo, nunca la suite completa.

**Criterio binario.** 15 passed, 0 failed. Y:

```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.plans_board import get_board_cached; b=get_board_cached(refresh=True); print(sum(1 for p in b['plans'] if p['estado_efectivo']=='SIN_ESTADO'))"
```
debe imprimir **`0`** (KPI-3).

**Flag:** `STACKY_PLANS_ESTADO_FALLBACK_ENABLED`, default **ON** (cálculo puro de solo lectura; no cae
en ninguna categoría de excepción).
**Impacto por runtime:** idéntico en los 3 — no invoca modelos. Sin fallback necesario.
**Trabajo del operador: ninguno.**

---

### F2 — Backend: registrar el test y cerrar el ratchet anti-regresión

**Objetivo.** Que un plan **nuevo** no pueda nacer sin `**Estado:**` sin que el arnés se ponga rojo.

**Archivos a crear/editar (3):**

1. **Crear** `Stacky Agents/backend/tests/plans_estado_baseline.json` — la deuda histórica congelada.
   Generalo con este comando (no lo escribas a mano):

```bash
cd "Stacky Agents/docs" && \
for f in [0-9]*_PLAN_*.md; do \
  head -c 4000 "$f" | grep -qE '^\s*(>\s*)?\*\*Estado:\*\*' || echo "$f"; \
done | sort | python -c "import sys,json; print(json.dumps({'_comment':'Plan 263 — planes historicos sin **Estado:**. RATCHET: esta lista SOLO puede achicarse. Un plan nuevo sin estado NO se agrega aca: se le escribe el estado.','sin_estado':[l.strip() for l in sys.stdin if l.strip()]}, indent=2, ensure_ascii=False))" > "../backend/tests/plans_estado_baseline.json"
```

Al momento de escribir este plan la lista tiene **78** entradas.

2. **Crear** `Stacky Agents/backend/tests/test_plan263_estado_guard.py`:

| # | Test | Qué asegura |
|---|---|---|
| 1 | `test_baseline_existe_y_es_json` | El baseline carga y `sin_estado` es una lista de str. |
| 2 | `test_ningun_plan_nuevo_sin_estado` | Recorre `docs/*_PLAN_*.md`; junta los que no tienen `**Estado:**` en los primeros 4000 chars; **falla** si alguno **no** está en el baseline. Mensaje: `"El plan <archivo> no declara **Estado:**. Agregale la linea o corré la normalización del Plan 263."` |
| 3 | `test_el_ratchet_solo_se_achica` | **Falla** si el baseline tiene entradas que ya **no** existen en disco o que **sí** tienen estado ⇒ obliga a achicar el baseline cuando se normaliza un plan. Mensaje: `"El baseline quedó stale: sacá <archivo> de plans_estado_baseline.json."` |
| 4 | `test_baseline_sin_duplicados` | `len(sin_estado) == len(set(sin_estado))`. |

3. **Editar** `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar a la tupla
   `HARNESS_TEST_FILES` (empieza en `run_harness_tests.sh:20`) las dos líneas, respetando el orden
   alfabético del bloque vecino:

```
    tests/test_plan263_estado_fallback.py
    tests/test_plan263_estado_guard.py
```

Y lo mismo en `Stacky Agents/backend/scripts/run_harness_tests.ps1` (el .ps1 mantiene su propia copia
de la lista; verificá con `grep -n "test_plan25" run_harness_tests.ps1` cómo se declara ahí y seguí
ese formato literal).

> **Por qué es obligatorio:** `tests/test_harness_ratchet_meta.py:3` falla si un `test_*.py` nuevo no
> está clasificado. Saltarse este paso deja el arnés rojo.

**Comando de test:**

```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan263_estado_guard.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
```

**Criterio binario.** Ambos exit 0. Prueba negativa manual obligatoria: creá
`Stacky Agents/docs/999_PLAN_PRUEBA_RATCHET.md` con una sola línea `# hola`, corré el primer comando,
verificá que **falla** nombrando `999_PLAN_PRUEBA_RATCHET.md`, y **borrá el archivo**.

**Flag:** ninguna nueva — es un test del arnés, siempre activo.
**Impacto por runtime:** ninguno (test determinista, sin modelo).
**Trabajo del operador: ninguno.**

---

### F3 — Backend: normalización con evidencia (preview ON, escritura OFF)

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
      }
    NUNCA lanza. NUNCA escribe.
    """
```

**Reglas de inferencia (en este orden exacto; la primera que matchea gana):**

| Orden | Condición (verificable, sin LLM) | `estado_propuesto` | `confianza` | Evidencia que se agrega |
|---|---|---|---|---|
| 1 | El ledger (`load_ledger`) tiene entrada con `veredicto` en `("APROBADO","TERMINADO-POR-SUPERVISOR")` | `IMPLEMENTADO` | `alta` | `"El supervisor lo aprobó el <fecha> (ledger.json)."` |
| 2 | El doc contiene la subcadena `"Registro de implementación"` o `"IMPLEMENTADA"` en los primeros 8000 chars | `IMPLEMENTADO` | `alta` | `"El propio documento registra fases IMPLEMENTADAS."` |
| 3 | El doc contiene `"veredicto"` y (`"APROBADO"` o `"RECHAZADO"`) en los primeros 8000 chars | `CRITICADO` | `media` | `"El documento trae un veredicto del juez, pero no registro de implementación."` |
| 4 | Ninguna de las anteriores **y** el número del plan `> max(ledger) - 20` (plan reciente) | `PROPUESTO` | `baja` | `"Plan reciente sin rastro de crítica ni implementación."` |
| 5 | Ninguna de las anteriores | `IMPLEMENTADO` | `baja` | `"Sin evidencia; se aplica el fallback del Plan 263."` |

> **Por qué la regla 4 existe:** sin ella, planes recientes y realmente pendientes (`243`, `247`..`252`)
> quedarían escritos en disco como `IMPLEMENTADO`, que es exactamente la mentira que R1 advierte. La
> regla 4 los deja en `PROPUESTO` y `confianza: baja`, para que el operador los revise.

```python
def preview_estado_migration(docs_dir: Path) -> dict:
    """{"ok": True, "total": int, "propuestas": [<dict de infer_estado_con_evidencia>, ...],
        "por_confianza": {"alta": int, "media": int, "baja": int}}
    SOLO LECTURA. Nunca escribe. Nunca lanza."""


def apply_estado_migration(docs_dir: Path, filenames: list[str], *, dry_run: bool = True) -> dict:
    """Escribe la línea **Estado:** en los planes pedidos, UNO POR UNO.

    - `filenames` es una lista EXPLÍCITA: no existe "aplicar a todos" implícito.
    - Rechaza cualquier filename que no matchee `_PLAN_FILE_RE` o que escape de
      docs_dir (guardia de path traversal: `(docs_dir / name).resolve()` debe
      tener `docs_dir.resolve()` como parent).
    - Rechaza un plan que YA tiene **Estado:** (idempotencia: no duplica la línea).
    - Escritura atómica: escribe a `<archivo>.tmp` y hace os.replace().
    - dry_run=True devuelve el diff sin tocar el disco.
    Devuelve {"ok": bool, "aplicados": [str], "omitidos": [{"filename","razon"}], "diffs": {filename: str}}
    """
```

**Casos de test (mínimo 12):**

1. `infer_estado_con_evidencia` con ledger APROBADO → `IMPLEMENTADO`/`alta`.
2. …con doc que dice `"Registro de implementación"` → `IMPLEMENTADO`/`alta`.
3. …con doc que trae `veredicto ... APROBADO` → `CRITICADO`/`media`.
4. …plan reciente sin nada → `PROPUESTO`/`baja`.
5. …plan viejo sin nada → `IMPLEMENTADO`/`baja`.
6. `linea_a_insertar` empieza con `**Estado:** ` y contiene el string `Plan 263`.
7. `insert_after_line` apunta a la línea del `# ` título (el estado va justo debajo del H1).
8. `preview_estado_migration` sobre un tmp_path con 3 docs sin estado → `total == 3`, no escribe (mtime de los 3 archivos idéntico antes/después).
9. `apply_estado_migration(dry_run=True)` → `aplicados == []`, `diffs` no vacío, archivos intactos.
10. `apply_estado_migration(dry_run=False, filenames=["01_PLAN_X.md"])` → el archivo ahora tiene `**Estado:**` y `parse_plan_header` lo reconoce.
11. Idempotencia: correr 10 dos veces → la segunda devuelve `omitidos` con razón `"ya declara estado"` y el archivo **no** cambia (sha256 idéntico).
12. Seguridad: `apply_estado_migration(docs_dir, ["../../.env"])` → `omitidos`, `ok` sigue True, y `.env` **no** se toca.

**Endpoints (editar `Stacky Agents/backend/api/plans_board.py`):**

```python
@bp.get("/normalize/preview")          # ruta: /api/plans-board/normalize/preview
def plans_normalize_preview():
    # Gate: config.config.STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED
    # 200 -> preview_estado_migration(docs_dir_default())
    # deshabilitada -> reusar el patrón de _disabled_resp() (plans_board.py:19)

@bp.post("/normalize/apply")           # ruta: /api/plans-board/normalize/apply
def plans_normalize_apply():
    # Gate: config.config.STACKY_PLANS_NORMALIZE_APPLY_ENABLED
    # Body: {"filenames": ["...", ...], "dry_run": true|false, "confirm": true}
    # 400 si falta `confirm: true` o si `filenames` está vacío/ausente.
    # -> apply_estado_migration(...)
```

> **HITL, explícito:** `confirm: true` es obligatorio y `filenames` nunca puede ser `"*"`. El backend
> no expone ninguna forma de aplicar a todos de una. Si el operador quiere los 78, la UI manda los 78
> nombres tras mostrarlos.

**Comando de test:**

```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan263_migration.py" -q
```
(y registrar `tests/test_plan263_migration.py` en las dos listas `HARNESS_TEST_FILES`, igual que F2).

**Criterio binario.** 12 passed, 0 failed. Con `STACKY_PLANS_NORMALIZE_APPLY_ENABLED=false`,
`POST /api/plans-board/normalize/apply` responde el envelope de deshabilitado y **no** modifica ningún
archivo (verificable comparando `git status --porcelain "Stacky Agents/docs"` antes y después).

**Flags:** `STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED` **ON** (solo lectura, calcula y muestra) ·
`STACKY_PLANS_NORMALIZE_APPLY_ENABLED` **OFF** — **categoría (B)**: escribe en un sistema real del
operador, editando los `.md` de su working tree en `Stacky Agents/docs/` desde
`services/plans_estado_migration.py::apply_estado_migration`.
**Impacto por runtime:** ninguno — inferencia determinista por reglas, **sin LLM**. Idéntico en los 3.
**Trabajo del operador:** opt-in explícito para la escritura (flag + click + confirmación). El preview
es automático y no pide nada.

---

### F4 — Frontend: el modelo puro, coherente con el backend

**Objetivo.** Que las dos superficies del tablero (tab "Planes" y Centro de Evolución) apliquen el mismo
fallback y muestren el rótulo "inferido".

**Archivos a editar (2) + tests (2).**

1. `Stacky Agents/frontend/src/plansBoard/model.ts`:

```diff
 export interface PlanCardDto {
   ...
   estado_efectivo: EstadoPlan;
+  /** Plan 263 — el backend infirió el estado porque el doc no lo declara.
+      Opcional: un deploy viejo del backend no manda la clave. */
+  estado_inferido?: boolean;
   ...
 }
```

```diff
+/** Plan 263 — literal único del fallback en el frontend. Debe coincidir con
+    services/plans_board.py::ESTADO_FALLBACK. */
+export const ESTADO_FALLBACK: EstadoPlan = "IMPLEMENTADO";
+
 export function estadoChip(card: PlanCardDto): { label: string; color: string } {
-  return ESTADO_CHIP[card.estado_efectivo] ?? ESTADO_CHIP.SIN_ESTADO;
+  const chip = ESTADO_CHIP[card.estado_efectivo] ?? ESTADO_CHIP[ESTADO_FALLBACK];
+  return card.estado_inferido ? { ...chip, label: `${chip.label} (inferido)` } : chip;
 }
```

> `ESTADO_CHIP.SIN_ESTADO` (`model.ts:57`) y el miembro `"SIN_ESTADO"` del tipo `EstadoPlan`
> (`model.ts:8`) **se conservan**: con la flag OFF, o contra un backend viejo, siguen llegando.

2. `Stacky Agents/frontend/src/plansBoard/actions.ts` — la función `allowedActionsForCard`. Hoy
   `allowedActionsForCard("SIN_ESTADO", null)` devuelve `[]`
   (`plansBoard/__tests__/actions.test.ts:18-19`). **Ese test se conserva tal cual** (es el
   comportamiento con flag OFF). Lo que se agrega es que `"IMPLEMENTADO"` ya habilita "Supervisar", que
   es lo que reciben ahora los 78 planes — verificalo leyendo la función antes de tocarla; si
   `allowedActionsForCard("IMPLEMENTADO", null)` ya incluye `"supervisar"`, **no hay cambio de código
   en este archivo**, sólo el test 3 de abajo.

**Tests (vitest):** editar `Stacky Agents/frontend/src/plansBoard/model.test.ts` agregando:

| # | Caso | Aserción |
|---|---|---|
| 1 | `estadoChip(card({estado_efectivo:"ALGO_RARO"}))` | `.label === "Implementado"` (antes era `"Sin estado"` — **este test 55-57 existente hay que ACTUALIZARLO**, no duplicarlo) |
| 2 | `estadoChip(card({estado_efectivo:"IMPLEMENTADO", estado_inferido:true}))` | `.label === "Implementado (inferido)"` |
| 3 | `estadoChip(card({estado_efectivo:"IMPLEMENTADO"}))` (sin la clave) | `.label === "Implementado"` (deploy viejo del backend no rompe) |
| 4 | `filterPlans([...], {estado:"IMPLEMENTADO", ...})` con un card inferido | lo incluye (filtro consistente con el fallback) |
| 5 | `allowedActionsForCard("IMPLEMENTADO", null)` | incluye `"supervisar"` |

**Comando de test (por archivo — nunca la suite completa, por contaminación cross-file conocida):**

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/model.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/__tests__/actions.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** Los tres comandos exit 0. `tsc --noEmit` sin errores.

**Flag:** protegido por `STACKY_PLANS_BOARD_ENABLED` (ya existente, ON). El fallback lo decide el
backend; el frontend sólo lo refleja — **no hay lógica de fallback duplicada en TS** más allá del
literal `ESTADO_FALLBACK`, que existe únicamente para el chip de un backend viejo.
**Impacto por runtime:** ninguno (UI pura).
**Trabajo del operador: ninguno.**

---

### F5 — Frontend: densidad real (0 espaciados sordos)

**Objetivo.** Que el tablero obedezca el toggle cómodo/compacto del Plan 150 y muestre ≥ 11 cards sin
scroll a 1080 px en `compacto`.

**Archivo a editar (1):** `Stacky Agents/frontend/src/pages/PlansBoardPage.module.css`.

**Cambio.** Reemplazar las **31** declaraciones de `padding`/`margin`/`gap` hardcodeadas en `rem`/`px`
por tokens `var(--space-N)`. Tabla de conversión **exacta** (los tokens están en
`frontend/src/theme.css:100-108`; en `compacto` se re-apuntan en `:250-259`):

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

Aplicar a las 31 líneas listadas por el comando de verificación de abajo. Ejemplo de las 4 que más
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
  congelados en `frontend/src/__tests__/uiDebtBaseline.json`. Criterio: **no aumentar** (quedan 3).
  No intentes bajarlos a 0 en este plan.

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
> `ls "Stacky Agents/frontend/src/__tests__/" | grep -i ratchet` y corré ese.

**Criterio binario.** Primer grep = **0** (KPI-2), segundo grep **≥ 46**, ratchet de UI verde,
`npx tsc --noEmit` exit 0.

**Smoke visual (manual, 2 minutos — NO automatizable):** el repo **no tiene RTL ni jsdom instalados**,
así que la verificación visual es a ojo y va documentada, no scripteada. Pasos: abrir `/plans`, poner
la ventana en 1080 px de alto, activar densidad `compacto` con el `DensityToggle`, contar las cards
visibles sin scroll ⇒ **≥ 11** (KPI-5). Anotar el número en el registro de implementación del plan.

**Flag:** ninguna nueva — protegido por `STACKY_PLANS_BOARD_ENABLED` (ON) y por el sistema de densidad
del Plan 150, ya existente y ya ON.
**Impacto por runtime:** ninguno (CSS puro).
**Trabajo del operador: ninguno** (el toggle de densidad ya existía; el tablero simplemente empieza a
obedecerlo).

---

### F6 — Frontend: panel de normalización en el tablero (HITL)

**Objetivo.** Darle al operador la vista previa y el botón de aplicar, con la evidencia y el diff.

**Archivos a editar (2):**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — agregar al objeto `PlansBoard` existente (ubicalo
   con `grep -n "PlansBoard" endpoints.ts`):

```ts
  normalizePreview: () => api.get<NormalizePreviewDto>("/plans-board/normalize/preview"),
  normalizeApply: (filenames: string[], dryRun: boolean) =>
    rawPost("/plans-board/normalize/apply", { filenames, dry_run: dryRun, confirm: true }),
```

> **Gotcha del repo:** usá **`rawPost`**, no `api.post`. El wrapper `api.*` **lanza excepción** ante
> cualquier non-2xx, así que con la flag OFF (que responde el envelope de deshabilitado) el componente
> explota en vez de mostrar el hint. Confirmá el nombre exacto del helper crudo con
> `grep -n "rawPost\|rawGet" "Stacky Agents/frontend/src/api/endpoints.ts"`.

2. `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` — un panel plegable "Planes sin estado
   declarado (N)", visible sólo si `preview.total > 0`, con:
   - una fila por propuesta: número, título, `estado_propuesto`, chip de `confianza`, y la evidencia;
   - checkbox por fila, **desmarcado por default** (nada se aplica sin marcarlo);
   - botón "Ver diff" → llama `normalizeApply(seleccionados, true)` (dry-run);
   - botón "Escribir estado en los .md seleccionados" → **deshabilitado** si
     `STACKY_PLANS_NORMALIZE_APPLY_ENABLED` está OFF, con hint: *"Activá 'Aplicar la normalizacion de
     estados a los .md' en Configuración del arnés para habilitarlo."*;
   - al hacer click, `confirm()` mostrando cuántos archivos se van a modificar. Usá el **Dialog
     canónico del Plan 164** si está disponible (`grep -rn "ConfirmDialog\|useConfirm" frontend/src`),
     no un `window.confirm` nuevo.

> **Cómo sabe el frontend si la flag está OFF:** las flags de UI se exponen en **`/api/diag/health`**
> (patrón ya usado por el resto del cockpit). Leé de ahí, no inventes un endpoint nuevo.

**Test (vitest, lógica pura — la UI no se testea sin RTL):** crear
`Stacky Agents/frontend/src/plansBoard/normalize.test.ts` sobre helpers puros que **debés poner en**
`Stacky Agents/frontend/src/plansBoard/normalize.ts`:

| # | Función | Caso |
|---|---|---|
| 1 | `seleccionablesPorDefecto(propuestas)` | devuelve `[]` (nada preseleccionado) |
| 2 | `resumenConfianza(propuestas)` | `{alta: n, media: n, baja: n}` correcto |
| 3 | `puedeAplicar(flagOn, seleccionados)` | `false` si `flagOn === false`; `false` si `seleccionados.length === 0`; `true` si ambos ok |
| 4 | `textoConfirmacion(seleccionados)` | contiene la cantidad y la palabra `"archivos"` |

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/normalize.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** 4 passed, `tsc --noEmit` exit 0, y `grep -c "style={{" PlansBoardPage.tsx`
sigue devolviendo **3** (no aumentar).

**Flags:** `STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED` (ON) para el panel;
`STACKY_PLANS_NORMALIZE_APPLY_ENABLED` (OFF, categoría B) para el botón de escritura.
**Impacto por runtime:** ninguno (UI + endpoint determinista).
**Trabajo del operador:** ninguno para ver; opt-in explícito para escribir.

---

### F7 — Cierre: verificación consolidada

**Objetivo.** Dejar constancia verificable de que los 5 KPI se cumplen.

**Sin archivos nuevos.** Correr, en este orden, y pegar la salida en el "Registro de implementación"
que se agrega al final de **este** documento:

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
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/model.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/__tests__/actions.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/plansBoard/normalize.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

> **Regresión obligatoria:** los tests `test_plan128_*`, `test_plan237_*` y `test_plan196_*` son de
> planes ya cerrados. Si alguno se pone rojo, el fallback rompió un contrato existente ⇒ **arreglalo
> antes de cerrar**, no lo pongas en una allowlist.

**Criterio binario.** Los 13 comandos exit 0, más los 3 greps de KPI (§1).
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación |
|---|---|---|---|
| **R1** | El fallback muestra "Implementado" en planes que **no** lo están (243, 247-252) y el operador les cree. | **Alta** (es el diseño pedido) | `estado_inferido: true` viaja siempre; el chip dice **"(inferido)"**; la acción sugerida dice literalmente *"no declara **Estado:**"*. La escritura a disco (F3) usa la **regla 4** que deja los planes recientes en `PROPUESTO`, no en `IMPLEMENTADO`. |
| **R2** | Con el fallback, el bucket `SIN_SUPERVISAR` salta de ~N a ~N+78 y el triage se vuelve inútil por volumen. | Alta | El panel de F6 separa visualmente los inferidos, y `totals["inferidos"]` permite filtrarlos. El filtro por bucket del Plan 237 sigue funcionando. Medir tras F1: si `SIN_SUPERVISAR > 100`, priorizar F3 sobre F5. |
| **R3** | `suggest_next_action` cambia de firma y rompe `test_plan128_plans_board_parser.py`. | Media | El parámetro nuevo es **keyword-only con default** (`*, estado_inferido: bool = False`) ⇒ los llamadores viejos compilan igual. F7 corre ese test explícitamente. |
| **R4** | La escritura de F3 corrompe un `.md` del operador (que además tiene cambios sin commitear). | Media | Escritura atómica (`.tmp` + `os.replace`), idempotente, con guardia de path traversal, `dry_run` por default, lista explícita de archivos, y la flag nace **OFF**. El operador ve el diff antes. |
| **R5** | El baseline del ratchet queda stale y el arnés se pone rojo por un archivo borrado. | Media | El test 3 de F2 (`test_el_ratchet_solo_se_achica`) da el mensaje exacto de qué sacar del JSON. |
| **R6** | La tokenización del CSS rompe el layout en `cómodo` (los tokens dan menos px que el hardcode). | Media | La tabla de conversión de F5 mapea cada valor a su token más cercano **hacia arriba** en cómodo (p.ej. `1.5rem`=24px → `--space-7`=24px exacto). Smoke visual obligatorio en las 2 densidades. |
| **R7** | Un deploy congelado (PyInstaller) sin `.git` rompe algo. | Baja | `repo_root()` ya devuelve `None` sin `.git` y `collect_unpushed_docs` degrada a `None` (`plans_board.py:647-652`, `:660-663`). Nada de este plan agrega dependencia de git. |
| **R8** | `test_harness_flags_help` sale rojo. | Media | **Ese archivo tiene 4 fallos ajenos preexistentes.** Validá TU entrada aparte (que las 3 flags nuevas tengan `label` y `description` no vacíos) y no adoptes los rojos ajenos. |

---

## 7. Fuera de scope

- **No** se cambia el diseño del triage del Plan 237 ni el orden de `TRIAGE_BUCKETS`.
- **No** se tocan los botones de acción del Plan 196 (proponer/criticar/implementar/supervisar).
- **No** se hace `git commit` ni `git push` de los `.md` normalizados: eso queda 100 % manual.
- **No** se corre el supervisor automáticamente sobre los 78 planes (sería categoría A: quema tokens).
- **No** se agrega RBAC, ni multiusuario, ni auth.
- **No** se refactoriza `PlansBoardPage.tsx` más allá del panel de F6 y los 3 inline styles congelados.
- **No** se toca `evolution/PlansSection.tsx` salvo que `tsc` lo exija por el tipo nuevo.

---

## 8. Orden de implementación y DoD

**Orden (estricto, por dependencia):**

1. **F0** — flags (todo lo demás las lee).
2. **F1** — `resolve_estado()` + `build_board` (el núcleo; sin esto no hay KPI-1 ni KPI-3).
3. **F2** — ratchet anti-regresión (protege lo de F1 hacia adelante).
4. **F4** — frontend modelo (consume lo de F1; sin esto la UI muestra un chip incoherente).
5. **F5** — densidad CSS (independiente de F1-F4; se puede hacer en paralelo si hay dos manos).
6. **F3** — migración backend (necesita F1 para saber qué normalizar).
7. **F6** — panel de normalización (necesita F3 y F4).
8. **F7** — cierre y verificación.

**Definición de Hecho (DoD) — global, binaria:**

- [ ] Los 13 comandos de F7 salen **exit 0**, cero rojos.
- [ ] `sum(1 for p in board['plans'] if p['estado_efectivo']=='SIN_ESTADO')` ⇒ **0** (KPI-3).
- [ ] `grep -cE '^\s*(padding|margin|gap)[^:]*:\s*[^;]*(rem|px)' PlansBoardPage.module.css` ⇒ **0** (KPI-2).
- [ ] `grep -c "style={{" PlansBoardPage.tsx` ⇒ **3** (no aumentó).
- [ ] Ningún literal hex nuevo en `PlansBoardPage.module.css` (ratchet `hexByFile` sin subir).
- [ ] Las 3 flags declaran default explícito; la OFF cita la categoría **(B)** por escrito en el código.
- [ ] `tests/test_plan263_*.py` (3 archivos) registrados en **ambas** listas `HARNESS_TEST_FILES`
      (`.sh` y `.ps1`), y `test_harness_ratchet_meta.py` verde.
- [ ] Prueba negativa del ratchet ejecutada y el archivo `999_PLAN_PRUEBA_RATCHET.md` **borrado**.
- [ ] Smoke visual hecho en las **dos** densidades, con el conteo de cards anotado (KPI-5 ≥ 11).
- [ ] Con `STACKY_PLANS_NORMALIZE_APPLY_ENABLED=false`, `git status --porcelain "Stacky Agents/docs"`
      **no cambia** tras llamar al endpoint de apply.
- [ ] El "Registro de implementación" se agrega al final de **este** documento con la salida real de
      los comandos y los desvíos encontrados.
- [ ] `git commit` del trabajo hecho **con pathspec explícito** (`git commit -- "<ruta>" ...`): el
      working tree tiene cambios de otras sesiones y un commit de índice compartido se los roba.
      **Prohibido** `git add -A`, `reset`, `amend` y `--no-verify`. El `push` es manual.
