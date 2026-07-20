# Plan 187 — Selección múltiple y acciones en lote: checkboxes por fila, rango con Shift, barra flotante contextual y resultado agregado

> **Estado:** IMPLEMENTADO F0-F5 (2026-07-18) · rama `impl/ux` · flag `STACKY_BULK_ACTIONS_ENABLED` default ON · KPIs K1-K9 verdes con output real (K1 4 passed, K2 56 passed, K3 .sh+.ps1=1, K4 selectionModel 17, K5 bulkModel 17, K6 bulkFlags 5, K7 tsc exit 0, K8 style={{}}=0, K9 role="toolbar"=1); wiring F4 ReviewInboxPage + F5 ExecutionHistoryPage (checkbox meta-columna PRIMERA + barra flotante). Deltas 197 §8.7 aplicados: `copySelectedLinks` usa `copyText` de `copyService` (sin writeText inline) y clave canónica `exec`. uiDebt/formDebt ratchets rojos = deuda ajena preexistente (mis 4 archivos en 0 regresión). Smoke manual de navegador (F4/F5 §687/§773) pendiente fuera de banda. · **Veredicto v1: APROBADO-CON-CAMBIOS** (0 bloqueantes, 5 importantes) · **Autor:** StackyArchitectaUltraEficientCode · juez: crítica adversarial inline en sesión principal (el subagente juez cayó por session-limit tras verificar OK las anclas de ReviewInboxPage).
> **Serie UX/UI:** continúa 150/161/162/164/165/172-175/185 SIN duplicarlos. Deslindes explícitos: 173 = presets de filtros y preferencias de tabla (NO selección); 175 = peek + menú contextual + acciones POR FILA (NO lote); 172 = atajos/foco roving (NO selección); 185 = undo con gracia (COMPLEMENTO de este plan, integración diferida en §4.7).
> **Toda la evidencia archivo:línea de este doc fue verificada en frío contra el checkout real `N:\GIT\RS\STACKY\Stacky\Stacky Agents` el 2026-07-18.** Los números de línea son referencia de ese día; **toda edición se ancla por TEXTO/símbolo citado, no por número de línea** (hay una sesión paralela conocida commiteando en este mismo árbol — hoy mismo creó los planes 176-184 y 186).

---

## CHANGELOG v1 → v2 (crítica adversarial C1..C7)

- **C1 (IMPORTANTE, resuelto):** la retención de fallidos usaba `sel.setSelection(retainOnly(sel.selection, …))` con snapshot STALE de la selección (cerrado al invocar el lote; el refetch de 30 s puede podar en el medio y el snapshot resucitaría ids ya podados, violando la invariante §3.6). Fix: el hook expone `retainFailed(ids)` con actualización FUNCIONAL (`setSelection((s) => retainOnly(s, ids))`) y `setSelection` crudo SALE del contrato público (F3/F4/F5).
- **C2 (IMPORTANTE, resuelto):** «OFF ⇒ UI byte-idéntica» era falso durante el primer paint (el hook arranca optimista en `true` y corrige tras el fetch: con flag OFF la columna aparece ~100-300 ms y desaparece). Fix: cache de módulo `_last` (mounts posteriores de la sesión sin flash) + la garantía se re-redacta como «desde el primer resolve de la flag en la sesión» (§1, §3.2, §3.9) — staleness documentada, sin prometer lo imposible.
- **C3 (IMPORTANTE, resuelto):** el worker de «Relanzar» duplicaba el payload de `Agents.run` inline (drift silencioso si el handler por fila cambia mañana). Fix: F4 paso 3a extrae `relaunchRow(row)` del handler existente y AMBOS caminos (botón por fila y lote) llaman LA MISMA función.
- **C4 (IMPORTANTE, resuelto):** `copySelectedLinks` hardcodeaba la ruta `/history` al armar deep-links (link roto si la ruta/base difiere). Fix: construir con `new URL(window.location.href)` + `searchParams.set("execution", String(id))`.
- **C5 (IMPORTANTE, resuelto) [ADICIÓN ARQUITECTO]:** faltaba freno de costo para lotes que DISPARAN ejecuciones: «¿Relanzar 200? Confirmar» lanzaría 200 runs con costo real tras un solo click. Fix: `BULK_EXECUTION_ACTION_MAX = 25` + helper puro `capExecutionBatch` (F2, con tests) aplicado SOLO a «Relanzar» (F4); las acciones locales (descartar/borrar/copiar) no llevan cap.
- **C6 (MENOR, resuelto):** K3/K9 exigían `grep -c` == `1` EXACTO (frágil: un comentario que mencione el string lo rompe). Ahora `≥1`.
- **C7 (MENOR, resuelto):** el gate del DoD contaba `confirm(` en TODO el diff (líneas de contexto incluidas ⇒ falso positivo posible). Ahora solo líneas AGREGADAS: `grep -cE '^\+.*(confirm|alert|prompt)\('` → `0`.

---

## 1. Objetivo + KPIs binarios

**Objetivo (1 párrafo):** hoy TODA acción del dashboard es 1×1: descartar 20 ejecuciones revisadas en la Bandeja de revisión son 20 clicks con 20 esperas (`ReviewInboxPage.tsx:115` — un botón «Descartar» por fila), y limpiar ejecuciones viejas del Historial exige abrir el drawer una por una (`ExecutionHistoryPage.tsx:187` — el click de fila solo abre detalle; no existe NINGÚN checkbox de selección en ninguna página). Este plan instala el patrón universal **selección múltiple + acciones en lote**, con onboarding NULO porque es el patrón que todo operador ya conoce de Gmail/Explorer: **(a)** una columna de checkboxes reales (primitiva `Checkbox` del plan 162) con click plano = toggle, **Shift+click = rango desde el ancla**, **Ctrl/Cmd+click = toggle**, y un checkbox de cabecera tri-estado «seleccionar todo lo visible»; **(b)** una **barra flotante contextual** («N seleccionadas · [acciones] · Deseleccionar») que aparece sola al haber selección y desaparece al no haberla; **(c)** ejecución del lote **reutilizando los endpoints por ítem ya existentes** (cero endpoints nuevos), secuencial, con progreso visible y **resultado agregado** (éxitos/fallos por ítem) en el `Toast` de la casa — los ítems fallidos QUEDAN seleccionados para reintentar; **(d)** **Escape deselecciona todo** (con guard de foco). Human-in-the-loop reforzado: toda acción de lote con efecto exige **confirmación armada de dos pasos** dentro de la barra (primer click arma «¿Descartar 12? Confirmar», segundo click ejecuta) — cero `confirm()` nativo nuevo (compatible con el ratchet del plan 185), cero autonomía. Pilotos: **Bandeja de revisión** (descartar/relanzar en lote) e **Historial de ejecuciones** (borrar/copiar links en lote). Todo detrás de la flag `STACKY_BULK_ACTIONS_ENABLED` (default ON); OFF ⇒ UI idéntica a hoy desde el primer resolve de la flag en la sesión (C2).

**KPIs binarios (comandos exactos):**

| # | Qué verifica | Comando (cwd y shell indicados) | Esperado |
|---|---|---|---|
| K1 | Flag registrada (bool, global, default ON) + curada + config default efectivo | PowerShell, `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` → `venv\Scripts\python.exe -m pytest tests/test_bulk_actions_flag.py -q` | exit 0 |
| K2 | El gate de flags del arnés sigue verde (curado `_CURATED_DEFAULTS_ON` + categorización) | mismo cwd → `venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` | exit 0 |
| K3 | Test backend nuevo registrado en el ratchet de cobertura | Git Bash, `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"` → `grep -c "test_bulk_actions_flag.py" scripts/run_harness_tests.sh` | `≥1` (C6) |
| K4 | Modelo puro de selección (toggle, rango, ancla, selectAll, prune, tri-estado) | PowerShell o Git Bash, `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"` → `npx vitest run src/services/__tests__/selectionModel.test.ts` | exit 0 |
| K5 | Modelo puro del lote (runner secuencial, guard doble-submit, resumen agregado, armado 2 pasos, guard Escape, cap de ejecución C5) | mismo cwd → `npx vitest run src/services/__tests__/bulkModel.test.ts` | exit 0 |
| K6 | Parser puro de la flag (OFF ⇔ `value === false` literal; ausente/error ⇒ ON) | mismo cwd → `npx vitest run src/services/__tests__/bulkFlags.test.ts` | exit 0 |
| K7 | Tipos verdes en todo el frontend | mismo cwd → `npx tsc --noEmit` | exit 0 |
| K8 | uiDebtRatchet: el `.tsx` nuevo nace con CERO inline-style | Git Bash, `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"` → `grep -c "style={{" src/components/bulk/BulkActionsBar.tsx` | `0` |
| K9 | Accesibilidad de la barra: `role="toolbar"` presente | mismo cwd Git Bash → `grep -c 'role="toolbar"' src/components/bulk/BulkActionsBar.tsx` | `≥1` (C6) |

**KPIs de impacto (proyectados, verificables por observación manual):**

| Métrica | Hoy (recuento en frío 2026-07-18) | Con el plan |
|---|---|---|
| Páginas con selección múltiple + lote | **0** (no hay checkboxes de selección en `frontend/src/pages/`) | **2** (Bandeja de revisión, Historial) |
| Interacciones para descartar 20 ejecuciones revisadas | 20 clicks + 20 esperas secuenciales manuales | 4 (checkbox 1 + Shift+click 20 + acción + confirmar) |
| Reporte de resultado de una limpieza masiva | inexistente (cada acción es muda o refresca sola) | 1 Toast agregado «X de N descartadas · fallaron: #a, #b» |
| Endpoints backend nuevos requeridos | — | **0** (reusa `Executions.discard/deleteOne`, `Agents.run`) |

---

## 2. Por qué ahora / gap que cierra (evidencia verificada)

**Gap (el porqué en 8 líneas):** Stacky es mono-operador y sus bandejas son de **triage masivo**: la Bandeja de revisión carga hasta **200** ejecuciones (`frontend/src/services/reviewInbox.ts:13-18`, `Executions.list({ status: ["needs_review","error"], limit: 200, days: 30 })`) y el Historial pagina de a **50** (`ExecutionHistoryPage.tsx:41`). Los planes 175 (acciones por fila) y 164 (confirmación canónica) optimizan el caso **1 ítem**; nadie optimiza el caso real del operador que vuelve de 3 días de runs y tiene 40 ejecuciones para descartar o 30 para borrar: hoy eso es O(N) clicks con O(N) esperas. La demanda de lote ya existe en la API — `Executions.deleteByTicket` es un bulk ad-hoc (`endpoints.ts:1297-1300`) — pero **no existe NINGUNA superficie de selección** en la UI (cero checkboxes de selección en `pages/`). La selección múltiple es el multiplicador que convierte las acciones por ítem existentes en operaciones de decenas, sin backend nuevo, sin curva de aprendizaje (patrón Gmail/Explorer) y sin quitarle al operador ninguna decisión: él selecciona, él confirma, él ve el resultado ítem por ítem.

**Pilotos elegidos (leyendo el código, no por intuición):**

| Página | Evidencia de lista con ids + acciones por ítem | Acciones de lote (reusan endpoint existente) |
|---|---|---|
| **Bandeja de revisión** — `frontend/src/pages/ReviewInboxPage.tsx` | tabla `<tr key={row.id}>` (`:104`); acciones por fila «Relanzar» (`:112-114` → `relaunch` `:49-66` → `Agents.run`, `endpoints.ts:1049`) y «Descartar» (`:115-117` → `discard` `:68-76` → `Executions.discard`, `endpoints.ts:1269`) | Descartar seleccionadas; Relanzar seleccionadas |
| **Historial de ejecuciones** — `frontend/src/pages/ExecutionHistoryPage.tsx` | tabla `<tr key={item.id}>` con `onClick` que abre el drawer (`:183-189`); acciones por ítem vía endpoints reales: `Executions.deleteOne` (`endpoints.ts:1295-1296`), receptor de deep-link `?execution=<id>` (`:58-65`) | Borrar seleccionadas; Copiar links seleccionados |

**Por qué NO las otras dos páginas ancla:** `TicketBoard.tsx` es archivo CALIENTE (lo tocan los planes 164/173/175 y la sesión paralela; además su vista es cards/grafo, no tabla) — queda como candidata futura en §6. `TeamScreen.tsx` renderiza cards de agentes fijados por `filename` (`TeamScreen.tsx:153` `pinned.map((filename) => …)`), no una bandeja de volumen — sin caso de lote real.

**Sustrato que se REUSA (verificado, no se reinventa):**

- **Primitiva `Checkbox`** (plan 162): `frontend/src/components/ui/Checkbox.tsx:4-24` — `label: ReactNode` obligatoria, extiende `InputHTMLAttributes<HTMLInputElement>` (pasa `checked`/`onClick`/`onChange`/`aria-label` al `<input>` real); exportada por el barrel `frontend/src/components/ui/index.ts:33`. **Gotcha codificado:** NO tiene `forwardRef` — el tri-estado de cabecera se resuelve con wrapper + `querySelector` (§4.4), sin tocar la primitiva.
- **`Button`** y **`Spinner`** del barrel (`ui/index.ts:7,21`) para la barra (formDebtRatchet del 162: cero tags crudos en `.tsx` nuevos).
- **`Toast` de la casa** (plan 135 F5): `frontend/src/components/Toast.tsx:11-17` — `ToastState { variant: "success"|"warning"|"error"; title?: string; body: string; correlationId?: string }`, controlado por el caller (no singleton), `role="alert"` + `aria-live="assertive"` (`:30-31`). El resultado agregado del lote se muestra por acá.
- **Arnés de flags:** `FlagSpec` (`backend/services/harness_flags.py:21-41`), categoría `interfaz_ui` (`:109-111`), `_CATEGORY_KEYS` (`:117`, tupla `interfaz_ui` en `:325-327`), `categorize()` (`:3377`); set curado `_CURATED_DEFAULTS_ON` importable como `from tests.test_harness_flags import _CURATED_DEFAULTS_ON` (patrón real en `backend/tests/test_context_contract_flags.py:68`); default efectivo en `config.py` con el patrón exacto de `STACKY_COST_CENTER_ENABLED` (`config.py:543-545`); ratchet de registro `HARNESS_TEST_FILES` en `backend/scripts/run_harness_tests.sh:20` (comentario `:8`: solo crece; lo vigila `tests/test_harness_ratchet_meta.py`).
- **Lectura de la flag por el frontend:** `HarnessFlags.list()` (`frontend/src/api/endpoints.ts:909-910`, `GET /api/harness-flags`) con `HarnessFlagView { key: string; …; value: boolean|number|string; … }` (`endpoints.ts:703-716`; `key` en `:704`, `value` en `:711`). Lookup literal y semántica OFF ⇔ `value === false` (mismo mecanismo que el plan 185 C1).

---

## 3. Principios y guardarraíles (NO negociables, codificados acá)

1. **Human-in-the-loop innegociable.** El lote lo dispara SIEMPRE el operador (seleccionar es manual; no hay auto-selección ni acciones proactivas). Toda acción de lote **con efecto** (descartar, relanzar, borrar) exige confirmación explícita: **armado de dos pasos dentro de la barra** (primer click arma y cambia el label a «¿<Acción> N? Confirmar»; segundo click dentro de 5 s ejecuta; cambio de selección, Escape o timeout desarman). Si al momento de implementar el diálogo canónico del plan 164 ya existe (verificable: `grep -r "ConfirmDialog\|useConfirm" frontend/src/components/ui/index.ts` con ≥1 hit), puede usarse EN SU LUGAR; si no, el armado de dos pasos es la vía (misma degradación declarada que el plan 175 §F3). **PROHIBIDO agregar llamadas nuevas a la familia de diálogos nativos del navegador** — el plan 185 F5 congela un baseline (`confirmCallCount`) que este plan no puede hacer crecer, y el gate del 164 F2 caza ese identificador.
2. **Cero trabajo extra para el operador.** Flag `STACKY_BULK_ACTIONS_ENABLED` default **ON**; la feature es invisible hasta que el operador toca un checkbox; no usarla deja todo como hoy. Sin pasos manuales nuevos, sin config nueva, sin migraciones. **Ninguna de las 4 excepciones duras aplica**, revisadas una por una: (1) *bypass de revisión humana* — NO: cada lote pasa por confirmación armada y las acciones son las MISMAS ya expuestas por ítem; (2) *destructiva/irreversible* — las acciones destructivas ya existen por ítem con la misma semántica; el lote agrega confirmación explícita donde hoy el botón por fila ejecuta directo (MÁS protección, no menos); (3) *prerequisito no garantizado* — solo endpoints y primitivas ya presentes en toda instalación; (4) *reduce seguridad* — OFF ⇒ idéntico a hoy desde el primer resolve de la flag en la sesión (C2: el primer paint de la primera carga puede mostrar la columna un instante; mounts posteriores usan el cache `_last`).
3. **Paridad de 3 runtimes: N/A-por-diseño, declarada por fase.** Feature 100% frontend (+1 flag backend de arnés): no toca el camino de ejecución/publicación de ningún runtime. «Relanzar en lote» reusa `Agents.run` tal cual lo llama hoy el botón por fila (`ReviewInboxPage.tsx:54-59`) — el runtime lo decide la config vigente del sistema, igual que hoy. Cada fase lo declara con 1 línea.
4. **Cero endpoints nuevos.** El lote es N llamadas cliente a los endpoints por ítem existentes, secuenciales. Si una acción de lote requiriera un endpoint bulk nuevo, queda FUERA DE SCOPE (§6) — explícitamente: no se crea `POST /api/executions/bulk-*` ni nada análogo.
5. **Mono-operador sin auth.** Sin RBAC, sin `user_id`, sin permisos por acción: la visibilidad de una acción depende solo de haber selección (`current_user` es un header sin validar; no protege nada y no se usa acá).
6. **Selección efímera y solo sobre lo cargado.** La selección vive en memoria de la página (ni URL, ni localStorage, ni backend), muere al desmontar, y SOLO puede contener ids presentes en la lista actualmente cargada: todo refetch/cambio de página/filtro la **poda** (`pruneToKnown`). «Seleccionar todo lo visible» = todas las filas HOY renderizadas (los `items`/`sortedRows` en memoria), NUNCA «todo lo que matchea el filtro en el servidor».
7. **Ratchets del repo se respetan, no se gamean.** (a) uiDebtRatchet (plan 138): `.tsx` NUEVOS con presupuesto CERO de `style={{}}` — todo estilo en `*.module.css`; el único valor dinámico necesario (tri-estado `indeterminate`) es una PROPIEDAD del input, no un estilo, y se setea por ref+effect. (b) formDebtRatchet (plan 162): cero tags crudos `<input>/<select>/<label>/<button>` en `.tsx` nuevos — primitivas `Checkbox`/`Button` del barrel. (c) Test backend nuevo registrado en `HARNESS_TEST_FILES`. (d) Colores solo con tokens `var(--…)` de `theme.css` (referencia de tokens reales: `Toast.module.css`), nunca hex.
8. **Tests sin DOM.** `@testing-library/react` y `jsdom` NO están en `frontend/package.json` (gap estructural conocido): TODA la lógica (selección, rango, ancla, runner, resumen, armado, guard de Escape, parser de flag) vive en módulos `.ts` PUROS con tests vitest POR ARCHIVO; los `.tsx` son cáscaras finas verificadas con `tsc --noEmit` + smoke manual documentado.
9. **Backward-compatible.** Ningún handler existente cambia de semántica: el click de fila del Historial sigue abriendo el drawer (el checkbox hace `stopPropagation`); los botones por fila de la Bandeja siguen intactos. Flag OFF ⇒ ni columna de checkboxes ni barra (UI idéntica desde el primer resolve; C2).
10. **No degradar performance.** Estado de selección = un `Set` en memoria; cero polling nuevo; la flag se lee UNA vez por sesión (promesa cacheada a nivel módulo; toggle del operador aplica al próximo reload — misma staleness aceptada que el plan 185 C6); el lote es secuencial contra el Flask local (sin ráfagas paralelas que saturen el backend).
11. **Sesión paralela viva en este árbol.** Pre-flight OBLIGATORIO por archivo antes de editar: `git status -- "<ruta>"`; si hay WIP ajeno en ese archivo ⇒ STOP y reportar al orquestador. `backend/harness_defaults.env` tiene WIP ajeno HOY: **PROHIBIDO tocarlo a mano** (se genera; si algún test de drift preexistente lo reclama, reportar el drift — es conocido — sin «arreglarlo»). El implementador NO commitea (lo hace el orquestador), staging quirúrgico por path explícito.

---

## 4. Fases

> **Convenciones de comandos.** Backend (PowerShell): `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` → `venv\Scripts\python.exe -m pytest tests/<archivo>.py -q` — SIEMPRE por archivo, NUNCA la suite entera (contaminación cross-file conocida). Frontend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"` → `npx vitest run src/<ruta>` por archivo; `npx tsc --noEmit` al cerrar cada fase que toque `.ts/.tsx`. Gates `grep`: Git Bash desde el cwd indicado en cada KPI.
> **Orden:** F0 → F1 → F2 → F3 → F4 → F5. Cada fase es autocontenida y verificable sola; F3 consume F1+F2; F4/F5 consumen F0+F3.
> **Sanity de imports backend:** NUNCA validar imports ejecutando `create_app()` fuera de pytest (dispara daemons y sync ADO reales — gotcha documentado del repo); siempre vía `pytest`.

---

### F0 — Flag `STACKY_BULK_ACTIONS_ENABLED` (default ON) + lectura frontend por `HarnessFlags.list()`

**Objetivo (1 frase):** registrar la flag con el patrón triple canónico (FlagSpec + default efectivo en `config.py` + alta en `_CURATED_DEFAULTS_ON`) y darle al frontend un parser puro + hook de lectura vía `GET /api/harness-flags`. **Valor:** un interruptor visible/toggleable en Settings→Arnés (panel registry-driven: registrar el FlagSpec la hace aparecer sola) gobierna todo el plan.

**Archivos a editar (4), crear (3):**

1. **`backend/services/harness_flags.py`** — agregar al `FLAG_REGISTRY` (ancla: el FlagSpec de `STACKY_UI_SHELL_V2_ENABLED`; insertarlo cerca, mismo formato):

```python
    # ── Plan 187 — Selección múltiple y acciones en lote ──────────────────────
    FlagSpec(
        key="STACKY_BULK_ACTIONS_ENABLED",
        type="bool",
        label="Selección múltiple y acciones en lote",
        description=(
            "Plan 187 — Checkboxes por fila, rango con Shift, barra flotante de "
            "acciones en lote y resultado agregado en Bandeja de revisión e "
            "Historial. OFF = interfaz idéntica a la actual."
        ),
        group="global",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
    ),
```

2. **`backend/services/harness_flags.py`** — en `_CATEGORY_KEYS` (`:117`), agregar `"STACKY_BULK_ACTIONS_ENABLED"` a la tupla existente `"interfaz_ui"` (ancla por texto: la tupla que hoy contiene `"STACKY_UI_SHELL_V2_ENABLED"`, `:325-327`). NO crear categoría nueva. NOTA de coexistencia: los planes 173/175 (no implementados) planean agregar sus propias keys a la MISMA tupla; si ya están cuando esto aterrice, simplemente sumar la nuestra al final.
3. **`backend/config.py`** — atributo con default efectivo ON, patrón EXACTO de `STACKY_COST_CENTER_ENABLED` (`config.py:543-545`):

```python
    # ── Plan 187 — Selección múltiple y acciones en lote (UI) ──────────────────
    # Default ON: no publica nada solo, no destruye (agrega confirmación),
    # sin prerequisitos, no reduce seguridad (OFF = UI idéntica).
    STACKY_BULK_ACTIONS_ENABLED: bool = os.getenv(
        "STACKY_BULK_ACTIONS_ENABLED", "true"
    ).strip().lower() == "true"
```

4. **`backend/tests/test_harness_flags.py`** — agregar `"STACKY_BULK_ACTIONS_ENABLED"` al set `_CURATED_DEFAULTS_ON` con comentario `# Plan 187`. Sin este paso `test_default_known_only_for_curated` rompe — es el gate, no un opcional.
5. **NUEVO `backend/tests/test_bulk_actions_flag.py`** — TESTS PRIMERO (correr ROJO por la razón correcta antes de tocar los 4 archivos de arriba):

```python
"""Plan 187 F0 — flag STACKY_BULK_ACTIONS_ENABLED (seleccion multiple y lote)."""
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_KEY = "STACKY_BULK_ACTIONS_ENABLED"


def test_flag_registrada_bool_global_default_on():
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert _KEY in by_key, f"{_KEY} no esta en FLAG_REGISTRY"
    spec = by_key[_KEY]
    assert spec.type == "bool"
    assert spec.group == "global"
    assert spec.default is True


def test_flag_categorizada_interfaz_ui():
    from services.harness_flags import categorize
    assert categorize(_KEY) == "interfaz_ui"


def test_flag_curada_default_on():
    # Patron real del repo: tests/test_context_contract_flags.py:68
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    assert _KEY in _CURATED_DEFAULTS_ON


def test_config_default_efectivo_true():
    # Chequeo a nivel FUENTE para no importar config con side effects
    # (gotcha create_app/daemons; mismo patron que el plan 175 F0).
    src = (_BACKEND / "config.py").read_text(encoding="utf-8")
    m = re.search(rf'{_KEY}: bool = os\.getenv\(\s*"{_KEY}", "(\w+)"', src)
    assert m is not None, "config.py no define la flag con el patron canonico"
    assert m.group(1) == "true"
```

6. **`backend/scripts/run_harness_tests.sh`** — agregar la línea `tests/test_bulk_actions_flag.py` al array `HARNESS_TEST_FILES` (`:20`; ratchet solo-crece, `:8`). Pre-flight `git status -- "Stacky Agents/backend/scripts/run_harness_tests.sh"`: si hay WIP ajeno, agregar la línea igual (array aditivo, una línea propia) y declarar la coexistencia en el resumen.
7. **NUEVO `frontend/src/services/bulkFlags.ts`** — parser puro + hook (TESTS PRIMERO: crear antes `frontend/src/services/__tests__/bulkFlags.test.ts`, correrlo rojo):

```ts
// Plan 187 F0 — lectura de STACKY_BULK_ACTIONS_ENABLED via GET /api/harness-flags.
// Mecanismo idéntico al plan 185 C1: lookup literal por key; OFF ⇔ value === false;
// flag ausente, backend caído o error de red ⇒ ON (default de la flag es ON).
// Staleness aceptada: se lee UNA vez por sesión; un toggle del operador aplica
// al próximo reload del dashboard (mismo contrato que las flags restart_required).
import { useEffect, useState } from "react";
import { HarnessFlags } from "../api/endpoints";

export function resolveBulkActionsEnabled(
  flags: Array<{ key: string; value: unknown }> | null | undefined,
): boolean {
  if (!Array.isArray(flags)) return true;
  const f = flags.find((x) => x.key === "STACKY_BULK_ACTIONS_ENABLED");
  return !(f && f.value === false);
}

let _cached: Promise<boolean> | null = null;
let _last: boolean | null = null;   // C2: último valor resuelto en esta sesión (mounts posteriores sin flash)
function fetchEnabledOnce(): Promise<boolean> {
  if (!_cached) {
    _cached = HarnessFlags.list()
      .then((res) => { const v = resolveBulkActionsEnabled(res.flags); _last = v; return v; })
      .catch(() => { _last = true; return true; });
  }
  return _cached;
}

/** Hook de página: primer mount de la sesión arranca optimista en true (default ON) y
 *  corrige si el backend dice false (C2: flash único aceptado y documentado);
 *  mounts posteriores arrancan directo en el valor resuelto (_last) — sin flash. */
export function useBulkActionsEnabled(): boolean {
  const [enabled, setEnabled] = useState(() => _last ?? true);
  useEffect(() => {
    let alive = true;
    void fetchEnabledOnce().then((v) => { if (alive) setEnabled(v); });
    return () => { alive = false; };
  }, []);
  return enabled;
}
```

**Tests de `bulkFlags.test.ts` (solo el parser puro, exactos):** `off_cuando_value_false_literal` (`[{key:"STACKY_BULK_ACTIONS_ENABLED", value:false}]` → `false`); `on_cuando_value_true` (→ `true`); `on_cuando_key_ausente` (array con otras keys → `true`); `on_cuando_flags_undefined_o_null` (→ `true`); `on_cuando_value_string_false` (`value:"false"` → `true`, SOLO el booleano literal apaga).

**Criterio de aceptación BINARIO:** K1 + K2 + K3 + K6 verdes (comandos en §1).

**Flag:** `STACKY_BULK_ACTIONS_ENABLED`, default ON, configurable desde Settings→Arnés automáticamente (panel registry-driven de los planes 82/86). **Runtimes:** N/A-por-diseño — flag de arnés consumida solo por el dashboard; no toca ejecución de agentes. **Trabajo del operador: ninguno.**

---

### F1 — Núcleo puro de selección: `frontend/src/services/selectionModel.ts`

**Objetivo (1 frase):** TODA la semántica de selección (toggle, rango con ancla para Shift, Ctrl-toggle, seleccionar todo lo visible, tri-estado de cabecera, poda ante ids desaparecidos, retención de fallidos) como funciones puras inmutables testeables sin DOM. **Valor:** el comportamiento queda fijado por tests ANTES de tocar ninguna página; F3-F5 son cáscaras.

**Archivos NUEVOS (2):** `frontend/src/services/selectionModel.ts` + `frontend/src/services/__tests__/selectionModel.test.ts` (TESTS PRIMERO).

**API exacta (exports nombrados; TODAS las funciones devuelven estado NUEVO, jamás mutan; `selected` es siempre un `Set` nuevo):**

```ts
// Plan 187 F1 — modelo puro de selección múltiple. Ids numéricos (los dos
// pilotos usan ids de ejecución number). Sin window, sin React, sin fetch.
export type ItemId = number;

export interface SelectionState {
  selected: ReadonlySet<ItemId>;
  /** Ancla del rango Shift+click: el último id sobre el que se hizo click plano/ctrl. */
  anchor: ItemId | null;
}

export const EMPTY_SELECTION: SelectionState = { selected: new Set(), anchor: null };

export function isSelected(s: SelectionState, id: ItemId): boolean;
export function selectedCount(s: SelectionState): number;

/** Ids seleccionados EN EL ORDEN de visibleIds (determinismo del lote). Ignora
 *  duplicados de visibleIds (el primero gana) y seleccionados no visibles. */
export function selectedIdsInOrder(s: SelectionState, visibleIds: ItemId[]): ItemId[];

/** Click plano o Ctrl/Cmd+click sobre el checkbox: toggle del id y el ancla pasa a ese id
 *  (tanto al seleccionar como al deseleccionar). */
export function toggleOne(s: SelectionState, id: ItemId): SelectionState;

/** Shift+click: UNIÓN de selected con el rango cerrado [anchor..id] según el orden
 *  de visibleIds. Si anchor es null o no está en visibleIds ⇒ equivale a toggleOne.
 *  El ancla NO cambia (comportamiento estándar de Shift+click). El rango funciona
 *  igual con id antes o después del ancla (min/max de índices). */
export function rangeSelect(s: SelectionState, id: ItemId, visibleIds: ItemId[]): SelectionState;

/** Punto de entrada ÚNICO para el click de un checkbox de fila:
 *  shift ⇒ rangeSelect (ctrl se ignora si vienen ambos); si no ⇒ toggleOne. */
export function clickSelect(
  s: SelectionState, id: ItemId, visibleIds: ItemId[],
  mods: { shift: boolean; ctrl: boolean },
): SelectionState;

/** Unión con todos los visibles; el ancla no cambia. */
export function selectAllVisible(s: SelectionState, visibleIds: ItemId[]): SelectionState;

/** Estado del checkbox de cabecera: visibleIds vacío ⇒ "none"; todos los visibles
 *  seleccionados ⇒ "all"; alguno pero no todos ⇒ "some". Los seleccionados NO
 *  visibles no cuentan para este cálculo. */
export function headerState(s: SelectionState, visibleIds: ItemId[]): "none" | "some" | "all";

/** Click en la cabecera: headerState === "all" ⇒ quita los visibles del set
 *  (los no visibles, si los hubiera, se conservan); si no ⇒ selectAllVisible. */
export function toggleAllVisible(s: SelectionState, visibleIds: ItemId[]): SelectionState;

/** Escape / botón Deseleccionar. */
export function clearSelection(): SelectionState;   // devuelve un estado nuevo equivalente a EMPTY_SELECTION

/** Invariante ante refetch/cambio de página/filtro: selected ∩ knownIds;
 *  el ancla se conserva SOLO si sigue en knownIds (si no ⇒ null). */
export function pruneToKnown(s: SelectionState, knownIds: ItemId[]): SelectionState;

/** Tras un lote: conservar seleccionados SOLO los ids dados (los fallidos,
 *  para reintentar). Ancla: misma regla que pruneToKnown. */
export function retainOnly(s: SelectionState, ids: ItemId[]): SelectionState;
```

**Tests EXACTOS de `selectionModel.test.ts`** (con `visibleIds = [10, 20, 30, 40, 50]` salvo indicación):

| Test | Qué afirma |
|---|---|
| `toggle_selecciona_y_pone_ancla` | `toggleOne(EMPTY, 30)` → selected `{30}`, anchor `30`. |
| `toggle_deselecciona_y_mueve_ancla` | toggle 30 dos veces → selected vacío, anchor `30` (el ancla queda igual). |
| `rango_desde_ancla_hacia_abajo` | toggle 20, luego `rangeSelect(s, 40, vis)` → `{20,30,40}`, anchor sigue `20`. |
| `rango_invertido` | toggle 40, `rangeSelect(s, 20, vis)` → `{20,30,40}` (min/max de índices). |
| `rango_sin_ancla_equivale_a_toggle` | `rangeSelect(EMPTY, 30, vis)` → `{30}`, anchor `30`. |
| `rango_con_ancla_no_visible_equivale_a_toggle` | toggle 20; `rangeSelect` con `visibleIds=[30,40,50]` (el 20 ya no está) → toggle de ese id. |
| `rango_es_union_no_reemplazo` | toggle 10, toggle 50, luego toggle 20 y `rangeSelect(s, 30, vis)` → `{10,20,30,50}`. |
| `clickSelect_prioriza_shift_sobre_ctrl` | `mods {shift:true, ctrl:true}` invoca la semántica de rango. |
| `clickSelect_ctrl_es_toggle` | `mods {shift:false, ctrl:true}` = toggleOne. |
| `selectAll_es_union_y_preserva_ancla` | con `{20}` anchor 20 → `selectAllVisible` → los 5 + anchor 20. |
| `headerState_none_some_all` | vacío→"none"; `{20}`→"some"; los 5→"all"; `visibleIds=[]`→"none". |
| `toggleAll_desde_all_quita_solo_visibles` | seleccionados los 5 + un 99 no visible → `toggleAllVisible` → queda `{99}`. |
| `prune_elimina_ids_desaparecidos` | `{20,30}` y `knownIds=[30,40]` → `{30}`; anchor 20 → null. |
| `retainOnly_conserva_fallidos` | `{10,20,30}` y `retainOnly(s,[20])` → `{20}`. |
| `visibleIds_con_duplicados_no_rompen` | `visibleIds=[10,10,20]`: `selectedIdsInOrder` sin duplicados; `rangeSelect` no explota. |
| `inmutabilidad` | toda función devuelve un objeto distinto y NO muta el `Set` de entrada (comparar referencia y contenido del original). |

**Criterio de aceptación BINARIO:** K4 verde + `npx tsc --noEmit` exit 0.

**Flag:** N/A directo (módulo puro sin consumo aún; el consumo queda detrás de la flag en F3-F5). **Runtimes:** N/A-por-diseño — lógica pura del dashboard. **Trabajo del operador: ninguno.**

---

### F2 — Núcleo puro del lote: `frontend/src/services/bulkModel.ts`

**Objetivo (1 frase):** runner secuencial con guard anti doble-submit y progreso, resumen agregado éxitos/fallos → shape de Toast, armado de confirmación de dos pasos y guard de Escape — todo puro y testeable. **Valor:** el lote es imposible de duplicar por doble click, un fallo por ítem NUNCA corta el lote y el resultado siempre se reporta ítem por ítem.

**Archivos NUEVOS (2):** `frontend/src/services/bulkModel.ts` + `frontend/src/services/__tests__/bulkModel.test.ts` (TESTS PRIMERO).

**API exacta:**

```ts
// Plan 187 F2 — modelo puro del lote. Sin React, sin fetch, sin window.
export const BULK_MAX_LISTED_FAILURES = 5;
export const ARM_AUTO_DISARM_MS = 5000;
/** [ADICIÓN ARQUITECTO] C5 — cap de lote SOLO para acciones que DISPARAN EJECUCIONES (costo real). */
export const BULK_EXECUTION_ACTION_MAX = 25;

export interface BulkItemFailure { id: number; error: string }
export interface BulkResult { total: number; ok: number[]; failed: BulkItemFailure[] }
export type BulkWorker = (id: number) => Promise<void>;

/** Shape estructuralmente compatible con ToastState de components/Toast.tsx
 *  (se declara local para que este módulo siga siendo puro, sin imports de UI). */
export interface BulkToast { variant: "success" | "warning" | "error"; title?: string; body: string }

export interface BulkRunner {
  isRunning(): boolean;
  /** null ⇔ ya hay un lote corriendo (guard anti doble-submit). Ejecuta los ids
   *  DEDUPLICADOS, EN ORDEN, SECUENCIALMENTE (await por ítem). Un throw/reject del
   *  worker se captura POR ÍTEM (try/catch), se registra en failed con
   *  String((e as {message?:unknown})?.message ?? e).slice(0,200) y el lote SIGUE.
   *  onProgress(done, total) se invoca tras CADA ítem (éxito o fallo).
   *  Al resolver, isRunning() vuelve a false (finally). */
  run(
    ids: number[],
    worker: BulkWorker,
    onProgress?: (done: number, total: number) => void,
  ): Promise<BulkResult> | null;
}
export function createBulkRunner(): BulkRunner;

/** Resumen agregado. Reglas EXACTAS:
 *  - total 0                 ⇒ { variant:"warning", body:"Sin elementos seleccionados" }
 *  - failed 0                ⇒ { variant:"success", body:`${ok.length} ${ok.length===1?doneSingular:donePlural}` }
 *  - ok 0 (todo falló)       ⇒ { variant:"error", title:"Falló el lote",
 *                                body:`0 de ${total} — fallaron: ${listados}${sufijo} · primer error: ${failed[0].error}` }
 *  - parcial                 ⇒ { variant:"warning", title:"Resultado parcial",
 *                                body:`${ok.length} de ${total} ${donePlural} · fallaron: ${listados}${sufijo}` }
 *  donde listados = failed.slice(0, BULK_MAX_LISTED_FAILURES).map(f => `#${f.id}`).join(", ")
 *  y sufijo = failed.length > BULK_MAX_LISTED_FAILURES ? "…" : "".
 *  Ejemplo de params: doneSingular="ejecución descartada", donePlural="ejecuciones descartadas". */
export function summarizeBulk(r: BulkResult, doneSingular: string, donePlural: string): BulkToast;

/** [ADICIÓN ARQUITECTO] C5 — freno de costo para acciones de ejecución.
 *  ids.length <= max ⇒ { ok: true }.
 *  Si no ⇒ { ok: false, toast: { variant: "warning", title: "Lote demasiado grande",
 *    body: `Máximo ${max} relanzamientos por lote (seleccionadas: ${ids.length}). Repetí en tandas.` } }.
 *  Solo la página lo invoca para acciones que lanzan runs (F4 "relaunch");
 *  las acciones locales (descartar/borrar/copiar) NO llevan cap. */
export function capExecutionBatch(
  ids: number[], max = BULK_EXECUTION_ACTION_MAX,
): { ok: true } | { ok: false; toast: BulkToast };

/** Armado de dos pasos: click sobre una acción destructiva.
 *  current === clicked ⇒ { armed: null, execute: true }   (segundo click: ejecutar)
 *  distinto            ⇒ { armed: clicked, execute: false } (primer click: armar) */
export function nextArmed(current: string | null, clicked: string): { armed: string | null; execute: boolean };

/** Guard del Escape global: true ⇔ key === "Escape" Y el foco NO está en un campo
 *  de entrada de texto. Un <input type="checkbox"> (nuestros checkboxes de fila)
 *  NO bloquea el guard. active === null ⇒ true. */
export function shouldClearSelectionOnEscape(
  ev: { key: string },
  active: { tagName: string; isContentEditable: boolean; type?: string } | null,
): boolean;
// Reglas: tagName TEXTAREA o SELECT ⇒ false; tagName INPUT con type !== "checkbox" ⇒ false;
// isContentEditable ⇒ false; el resto ⇒ true.
```

**Tests EXACTOS de `bulkModel.test.ts`** (workers = funciones async fake; SIN fake timers, el runner no usa timers):

| Test | Qué afirma |
|---|---|
| `runner_secuencial_en_orden` | worker que empuja su id a un array `order` con un `await Promise.resolve()` en el medio → `order` igual a los ids de entrada; result `{total:3, ok:[…3], failed:[]}`. |
| `runner_fallo_no_corta_el_lote` | worker que rechaza en el 2º de 3 → `ok=[a,c]`, `failed=[{id:b,error:…}]`, y el 3º SÍ se ejecutó. |
| `runner_captura_throw_sincronico` | worker que hace `throw new Error("boom")` → failed con `error:"boom"`. |
| `runner_error_truncado_200` | mensaje de 500 chars → `failed[0].error.length === 200`. |
| `runner_progreso_por_item` | espía `onProgress` llamado N veces con `(1,N)…(N,N)` incluso con fallos. |
| `runner_guard_doble_submit` | con el primer `run` aún pendiente (worker con promesa manual), el segundo `run` devuelve `null`; tras resolver el primero, un tercer `run` devuelve promesa (no null). |
| `runner_dedup_ids` | `ids=[7,7,8]` → worker llamado 2 veces, `total===2`. |
| `runner_ids_vacios` | `run([],…)` → resuelve `{total:0, ok:[], failed:[]}` sin invocar worker. |
| `cap_dentro_del_limite` | `capExecutionBatch` con 25 ids → `{ ok: true }`; con 1 id → `{ ok: true }`. |
| `cap_excedido_devuelve_toast` | 26 ids → `{ ok: false, toast }` con variant `"warning"` y body que contiene `"25"` y `"26"`; `max` custom (p. ej. 2) respeta el override. |
| `summarize_todo_ok_singular_y_plural` | 1 ok → body `"1 ejecución descartada"`; 3 ok → `"3 ejecuciones descartadas"`, variant success. |
| `summarize_parcial_lista_fallidos` | 2 ok + 2 failed (#4,#9) de 4 → variant warning, title `"Resultado parcial"`, body contiene `"2 de 4 ejecuciones descartadas"` y `"#4, #9"`. |
| `summarize_mas_de_5_fallidos_trunca` | 7 failed → body lista 5 ids y termina la lista con `"…"`. |
| `summarize_todo_fallo` | 0 ok → variant error, title `"Falló el lote"`, body contiene `"primer error:"`. |
| `nextArmed_arma_y_ejecuta` | `(null,"discard")`→`{armed:"discard",execute:false}`; `("discard","discard")`→`{armed:null,execute:true}`; `("discard","delete")`→`{armed:"delete",execute:false}`. |
| `escape_guard_true_fuera_de_inputs` | active null, o `{tagName:"TD"}`, o `{tagName:"INPUT", type:"checkbox"}` → true (con key Escape). |
| `escape_guard_false_en_campos_de_texto` | INPUT type "text"/"search"/sin type, TEXTAREA, SELECT, contentEditable → false; key ≠ Escape → false. |

**Criterio de aceptación BINARIO:** K5 verde + `npx tsc --noEmit` exit 0.

**Flag:** N/A directo (módulo puro). **Runtimes:** N/A-por-diseño — lógica pura del dashboard. **Trabajo del operador: ninguno.**

---

### F3 — Cáscaras UI: `BulkActionsBar` + hook `useRowSelection`

**Objetivo (1 frase):** la barra flotante contextual (contador + acciones con armado + Deseleccionar + progreso) y el hook que cablea selección/poda/Escape a cualquier página con lista. **Valor:** F4/F5 agregan lote a una página con ~30 líneas de wiring cada una; futuras páginas reutilizan esto tal cual.

**Archivos NUEVOS (3):**
- `frontend/src/components/bulk/BulkActionsBar.tsx`
- `frontend/src/components/bulk/BulkActionsBar.module.css`
- `frontend/src/components/bulk/useRowSelection.ts`

**Contrato de `BulkActionsBar` (props exactas):**

```ts
import type { ReactElement } from "react";

export interface BulkAction {
  id: string;                          // estable kebab-case, ej. "discard-selected"
  label: (n: number) => string;        // ej. (n) => `Descartar ${n}`
  /** Solo para destructive: label del estado armado. ej. (n) => `¿Descartar ${n}? Confirmar` */
  armedLabel?: (n: number) => string;
  destructive: boolean;                // true ⇒ requiere armado de dos pasos (HITL)
  run: () => void;                     // la página cierra sobre su selección/worker
}

export interface BulkActionsBarProps {
  count: number;                                    // N seleccionados
  actions: BulkAction[];
  running: boolean;                                 // lote en curso
  progress: { done: number; total: number } | null; // texto "Ejecutando… d/t"
  onClear: () => void;                              // botón "Deseleccionar"
}
```

**Comportamiento EXACTO del componente:**
1. `if (count === 0 && !running) return null;` — la barra solo existe con selección o lote en curso.
2. Contenedor: `<div className={styles.bar} role="toolbar" aria-label="Acciones en lote">`. Posición: `position: fixed`, centrada abajo (`left: 50%; transform: translateX(-50%); bottom: …`), TODO en `BulkActionsBar.module.css` — **cero `style={{}}`** (K8). Colores/sombra/borde SOLO con tokens `var(--…)` de `theme.css` (copiar los tokens que ya usa `Toast.module.css` como referencia); sin hex.
3. Contador como TEXTO REAL: `<span className={styles.count} aria-live="polite">{count} seleccionadas</span>` (con `running && progress`: `Ejecutando… {progress.done}/{progress.total}` y un `<Spinner size="sm" />` del barrel `ui`).
4. Estado interno `const [armed, setArmed] = useState<string | null>(null);` con:
   - `useEffect` que hace `setArmed(null)` cuando cambia `count` (cambió la selección ⇒ desarmar).
   - `useEffect` de auto-desarme: cuando `armed !== null`, `setTimeout(() => setArmed(null), ARM_AUTO_DISARM_MS)` con cleanup.
5. Cada acción se renderiza con la primitiva `Button` del barrel (`components/ui`) — **cero `<button>` crudo** (formDebtRatchet). `disabled={running}`. El label:
   - no destructiva ⇒ `action.label(count)`; onClick ⇒ `action.run()` directo.
   - destructiva ⇒ si `armed === action.id` muestra `action.armedLabel?.(count) ?? action.label(count)`; onClick ⇒ `const r = nextArmed(armed, action.id); setArmed(r.armed); if (r.execute) action.run();`. El estado armado se comunica por el TEXTO del label (sin depender de variantes de estilo; si `Button` expone una variante de peligro en su tipo real, puede usarse — verificar en `components/ui/Button.tsx` al implementar, NO asumir nombres).
6. Botón final `Deseleccionar` (primitiva `Button`) ⇒ `onClear()`; `disabled={running}`.
7. Sin portal, sin z-index heroico: un `z-index` razonable en el module.css por encima del contenido de página (referencia: el que use `Toast.module.css`).

**Contrato del hook `useRowSelection` (archivo `useRowSelection.ts`):**

```ts
import { useEffect, useMemo, useState } from "react";
import {
  EMPTY_SELECTION, type SelectionState, clickSelect, clearSelection, headerState,
  isSelected, pruneToKnown, retainOnly, selectedCount, selectedIdsInOrder, toggleAllVisible,
} from "../../services/selectionModel";
import { shouldClearSelectionOnEscape } from "../../services/bulkModel";

export interface UseRowSelectionOptions {
  visibleIds: number[];        // ids en orden visual — el caller los MEMOIZA (useMemo)
  enabled: boolean;            // flag ON; false ⇒ el hook es inerte (count 0, no-ops)
  escapeDisabled?: boolean;    // true mientras un drawer propio está abierto o corre un lote
}

export interface UseRowSelectionResult {
  selection: SelectionState;
  /** C1 — retención post-lote: aplica retainOnly de forma FUNCIONAL (sin snapshot stale).
   *  setSelection crudo NO se expone (footgun de closure stale eliminado del contrato). */
  retainFailed: (failedIds: number[]) => void;
  count: number;
  header: "none" | "some" | "all";
  isRowSelected: (id: number) => boolean;
  orderedSelectedIds: number[];
  onRowCheckboxClick: (
    id: number,
    ev: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; stopPropagation(): void },
  ) => void;
  onToggleAll: () => void;
  clear: () => void;
}
```

**Comportamiento EXACTO del hook:**
1. Estado `useState<SelectionState>(EMPTY_SELECTION)`.
2. **Poda (invariante §3.6):** `useEffect(() => { setSelection((s) => pruneToKnown(s, visibleIds)); }, [visibleIds.join(",")])` — clave de dependencia barata sobre el array memoizado del caller (anotar el eslint-disable de deps si el linter lo pide).
3. **Escape global:** `useEffect` activo SOLO cuando `enabled && count > 0 && !escapeDisabled`; registra `document.addEventListener("keydown", onKey)` donde `onKey` arma `active = document.activeElement` como `{ tagName, isContentEditable, type }` (cast a `HTMLInputElement` para `type`) y si `shouldClearSelectionOnEscape(ev, active)` ⇒ `setSelection(clearSelection())`. SIN `stopPropagation` (no interfiere con otros handlers de Escape; el caso drawer-abierto se cubre con `escapeDisabled`). Cleanup del listener.
4. `onRowCheckboxClick(id, ev)`: `ev.stopPropagation();` (crítico en el Historial: la fila tiene `onClick` que abre el drawer, `ExecutionHistoryPage.tsx:187`); si `ev.shiftKey` ⇒ `window.getSelection()?.removeAllRanges();` (mata la selección de texto nativa del Shift+click); luego `setSelection((s) => clickSelect(s, id, visibleIds, { shift: ev.shiftKey, ctrl: ev.ctrlKey || ev.metaKey }))`.
5. `onToggleAll()`: `setSelection((s) => toggleAllVisible(s, visibleIds))`.
6. `retainFailed(failedIds)`: `setSelection((s) => retainOnly(s, failedIds))` — SIEMPRE funcional (C1): opera sobre el estado FRESCO aunque el lote haya tardado y el polling haya podado en el medio.
7. Si `enabled === false`: devolver `count: 0`, `header: "none"` y handlers no-op (las páginas además NO renderizan la columna, ver F4/F5).

**Tests:** la lógica está fijada en F1/F2 (K4/K5). Esta fase se verifica con `npx tsc --noEmit` exit 0 + K8 + K9 (greps).

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` exit 0 **y** K8 = `0` **y** K9 = `1`.

**Flag:** los consumidores pasan `enabled` desde `useBulkActionsEnabled()` (F0). **Runtimes:** N/A-por-diseño — componentes del dashboard. **Trabajo del operador: ninguno.**

---

### F4 — Piloto 1: Bandeja de revisión (descartar / relanzar en lote)

**Objetivo (1 frase):** cablear selección + barra en `ReviewInboxPage.tsx` con dos acciones de lote que reusan `Executions.discard` y `Agents.run` por ítem. **Valor:** el flujo de mayor dolor real (triage de decenas de `needs_review`/`error`) pasa de O(N) interacciones a 4.

**Archivos a EDITAR (2):** `frontend/src/pages/ReviewInboxPage.tsx` + `frontend/src/pages/ReviewInboxPage.module.css`. **Pre-flight:** `git status -- "Stacky Agents/frontend/src/pages/ReviewInboxPage.tsx"` (STOP si hay WIP ajeno).

**Paso 1 — imports y estado (ancla: tras los `useState` existentes, `ReviewInboxPage.tsx:30-31`):**

```tsx
import { useRef } from "react";                    // sumar a los imports de react existentes
import Toast, { type ToastState } from "../components/Toast";
import { Checkbox } from "../components/ui";
import { useBulkActionsEnabled } from "../services/bulkFlags";
import { capExecutionBatch, createBulkRunner, summarizeBulk, type BulkWorker } from "../services/bulkModel";
import BulkActionsBar, { type BulkAction } from "../components/bulk/BulkActionsBar";
import { useRowSelection } from "../components/bulk/useRowSelection";

// dentro del componente:
const bulkEnabled = useBulkActionsEnabled();
const [bulkToast, setBulkToast] = useState<ToastState | null>(null);
const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
const runnerRef = useRef(createBulkRunner());
const bulkRunning = bulkProgress !== null;
const visibleIds = useMemo(() => sortedRows.map((r) => r.id), [sortedRows]);
const sel = useRowSelection({
  visibleIds,
  enabled: bulkEnabled,
  escapeDisabled: detailExecutionId !== null || bulkRunning,
});
```

**Paso 2 — auto-ocultado del toast (8 s, con cleanup):**

```tsx
useEffect(() => {
  if (!bulkToast) return;
  const t = setTimeout(() => setBulkToast(null), 8000);
  return () => clearTimeout(t);
}, [bulkToast]);
```

**Paso 3a (C3) — refactor mínimo previo, cero cambio de semántica:** extraer el CUERPO del handler por fila `relaunch` existente (`ReviewInboxPage.tsx:49-66`) a una función `async function relaunchRow(row): Promise<void>` dentro del componente (mismo payload de `Agents.run` que hoy, sin tocar una coma), y hacer que el botón por fila la llame. El lote llama LA MISMA función: si mañana cambia el payload del relanzamiento por fila, el lote hereda el cambio — cero drift entre caminos.

**Paso 3 — el ejecutor del lote (función dentro del componente; EXACTA):**

```tsx
async function runBulkAction(kind: "discard" | "relaunch") {
  const ids = sel.orderedSelectedIds;
  if (kind === "relaunch") {
    const cap = capExecutionBatch(ids);             // [ADICIÓN ARQUITECTO] C5: freno de costo
    if (!cap.ok) { setBulkToast(cap.toast); return; }
  }
  const worker: BulkWorker =
    kind === "discard"
      ? async (id) => { await Executions.discard(id); }
      : async (id) => {
          const row = rows.find((x) => x.id === id);
          if (!row) throw new Error("la fila ya no está en la bandeja");
          await relaunchRow(row);                    // C3: MISMA función que el botón por fila (paso 3a)
        };
  const p = runnerRef.current.run(ids, worker, (done, total) => setBulkProgress({ done, total }));
  if (!p) return;                                   // guard: ya hay un lote corriendo
  setBulkProgress({ done: 0, total: ids.length });
  const result = await p;
  setBulkProgress(null);
  setBulkToast(
    kind === "discard"
      ? summarizeBulk(result, "ejecución descartada", "ejecuciones descartadas")
      : summarizeBulk(result, "ejecución relanzada", "ejecuciones relanzadas"),
  );
  sel.retainFailed(result.failed.map((f) => f.id)); // C1: retención FUNCIONAL, sin snapshot stale
  await qc.invalidateQueries({ queryKey: ["review-inbox", activeProjectName] });
  if (kind === "relaunch") {
    await qc.invalidateQueries({ queryKey: ["tickets", activeProjectName] });
    await qc.invalidateQueries({ queryKey: ["executions"] });
  }
}
```

(Las queryKeys invalidadas son EXACTAMENTE las que ya usan los handlers por ítem: `ReviewInboxPage.tsx:60-62` y `:72`.)

**Paso 4 — columna de checkboxes.** En el `<thead>` (ancla: `<tr>` con `<th>Ticket</th>`, `:93-100`), AGREGAR como PRIMER `<th>` (solo si `bulkEnabled`):

```tsx
{bulkEnabled && (
  <th className={styles.selectCell}>
    <span ref={headerWrapRef}>
      <Checkbox
        label=""
        aria-label="Seleccionar todo lo visible"
        checked={sel.header === "all"}
        onChange={() => {}}
        onClick={(e) => { e.stopPropagation(); sel.onToggleAll(); }}
      />
    </span>
  </th>
)}
```

con `const headerWrapRef = useRef<HTMLSpanElement>(null);` y el efecto del **tri-estado** (propiedad del DOM, NO estilo — la primitiva `Checkbox` no tiene forwardRef, gotcha §2):

```tsx
useEffect(() => {
  const el = headerWrapRef.current?.querySelector("input");
  if (el) el.indeterminate = sel.header === "some";
}, [sel.header]);
```

En el `<tbody>` (ancla: `<tr key={row.id}>`, `:104`), AGREGAR como PRIMER `<td>`:

```tsx
{bulkEnabled && (
  <td className={styles.selectCell}>
    <Checkbox
      label=""
      aria-label={`Seleccionar ejecución #${row.id}`}
      checked={sel.isRowSelected(row.id)}
      onChange={() => {}}
      onClick={(e) => sel.onRowCheckboxClick(row.id, e)}
    />
  </td>
)}
```

(El estado checked/mixed lo expone el `<input type="checkbox">` NATIVO — no agregar `aria-checked` redundante sobre un input nativo; `aria-checked` es solo para `role="checkbox"` custom, que acá no existe.)

**Paso 5 — barra + toast (ancla: inmediatamente ANTES de `<ExecutionDetailDrawer`, `:125`):**

```tsx
{bulkEnabled && (
  <BulkActionsBar
    count={sel.count}
    running={bulkRunning}
    progress={bulkProgress}
    onClear={sel.clear}
    actions={[
      { id: "discard-selected", destructive: true,
        label: (n) => `Descartar ${n}`, armedLabel: (n) => `¿Descartar ${n}? Confirmar`,
        run: () => void runBulkAction("discard") },
      { id: "relaunch-selected", destructive: true,
        label: (n) => `Relanzar ${n}`, armedLabel: (n) => `¿Relanzar ${n}? Confirmar`,
        run: () => void runBulkAction("relaunch") },
    ]}
  />
)}
{bulkToast && <Toast toast={bulkToast} onClose={() => setBulkToast(null)} />}
```

(«Relanzar» es `destructive: true` a propósito: dispara N ejecuciones de agentes con costo real ⇒ confirmación armada obligatoria. Ambas acciones reusan endpoints por ítem — regla §3.4.)

**Paso 6 — CSS (agregar a `ReviewInboxPage.module.css`):**

```css
/* Plan 187 — celda de selección: sin selección de texto (colisión Shift+click) */
.selectCell {
  width: 2.25rem;
  user-select: none;
}
```

**Casos borde codificados:** fila desaparecida entre selección y ejecución del relanzamiento ⇒ el worker lanza y se reporta como fallo por ítem (el lote sigue); refetch de 30 s de la query (`:36`) mientras hay selección ⇒ la poda del hook mantiene la selección consistente; doble click en «Confirmar» ⇒ el segundo `run` devuelve `null` (guard) y no pasa nada.

**TDD/validación:** la lógica ya está fijada por K4/K5/K6. Esta fase: `npx tsc --noEmit` exit 0 + **smoke manual documentado** (anotar en el resumen de implementación): (1) seleccionar 3 con click; (2) Shift+click selecciona rango; (3) checkbox de cabecera selecciona todo lo visible y queda `indeterminate` con selección parcial; (4) Escape deselecciona (y NO deselecciona si el drawer está abierto); (5) «Descartar N» pide Confirmar y al confirmar muestra el Toast agregado y la bandeja refetchea; (6) con flag OFF (togglearla en Settings→Arnés + reload) la página es idéntica a hoy.

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` exit 0 + smoke completado y anotado.

**Flag:** `STACKY_BULK_ACTIONS_ENABLED` — OFF ⇒ ni columna ni barra (byte-idéntico). **Runtimes:** N/A-por-diseño — el relanzamiento usa `Agents.run` idéntico al botón por fila existente; el runtime lo decide la config vigente, igual que hoy. **Trabajo del operador: ninguno.**

---

### F5 — Piloto 2: Historial de ejecuciones (borrar / copiar links en lote)

**Objetivo (1 frase):** cablear selección + barra en `ExecutionHistoryPage.tsx` con «Borrar seleccionadas» (`Executions.deleteOne` por ítem, confirmación armada) y «Copiar N links» (deep-links `/history?execution=<id>`, acción segura instantánea). **Valor:** limpieza masiva del historial + compartir referencias de N runs en un click.

**Archivos a EDITAR (2):** `frontend/src/pages/ExecutionHistoryPage.tsx` + `frontend/src/pages/ExecutionHistoryPage.module.css`. **Pre-flight:** `git status -- "Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx"` (los planes 173/174/175 también planean tocarlo; si hay WIP ajeno ⇒ STOP y reportar).

**Paso 1 — mismos imports/estado que F4 Paso 1-2, con estas diferencias EXACTAS:**
- `visibleIds = useMemo(() => items.map((i) => i.id), [items]);` (los `items` de `:82`).
- `escapeDisabled: detailId !== null || bulkRunning` (el drawer usa `detailId`, `:55`).
- La página no importa `Agents`; importa `Toast`, `Checkbox`, `BulkActionsBar`, `useRowSelection`, `useBulkActionsEnabled`, `createBulkRunner`, `summarizeBulk` igual que F4 (sin `retainOnly` ni `capExecutionBatch`: la retención va por `sel.retainFailed` —C1— y acá ninguna acción dispara ejecuciones —C5 no aplica—). Ya importa `useEffect`/`useState` (`:8`) y `Executions` (`:10`).

**Paso 2 — acciones:**

```tsx
async function runBulkDelete() {
  const ids = sel.orderedSelectedIds;
  const p = runnerRef.current.run(ids, async (id) => { await Executions.deleteOne(id); },
    (done, total) => setBulkProgress({ done, total }));
  if (!p) return;
  setBulkProgress({ done: 0, total: ids.length });
  const result = await p;
  setBulkProgress(null);
  setBulkToast(summarizeBulk(result, "ejecución borrada", "ejecuciones borradas"));
  sel.retainFailed(result.failed.map((f) => f.id));                  // C1: retención funcional
  await qc.invalidateQueries({ queryKey: ["execution-history"] });   // match parcial de ["execution-history", filters, project] (:68)
}

async function copySelectedLinks() {
  // Deep-link con receptor REAL ya implementado: ?execution=<id> abre el drawer
  // (ExecutionHistoryPage.tsx:58-65, plan 129). Si el plan 175 ya aterrizó su
  // services/clipboard.ts, usarlo en lugar de este try/catch local.
  // C4: construir sobre la URL REAL de la página actual (ruta y base incluidas) —
  // nunca hardcodear "/history": si la ruta cambiara, el link seguiría siendo válido.
  const text = sel.orderedSelectedIds
    .map((id) => {
      const u = new URL(window.location.href);
      u.searchParams.set("execution", String(id));
      return u.toString();
    })
    .join("\n");
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch { ok = false; }
  setBulkToast(ok
    ? { variant: "success", body: `${sel.count} links copiados` }
    : { variant: "error", title: "No se pudo copiar", body: "El portapapeles no está disponible en este contexto." });
}
```

Nota: la página hoy NO usa `useQueryClient` — agregar `const qc = useQueryClient();` con su import desde `@tanstack/react-query` (junto al `useQuery` existente, `:9`).

**Paso 3 — columna de checkboxes:** idéntico a F4 Paso 4, con anclas de ESTA página: header en el `<tr>` de `<th>Inicio</th>` (`:169-180`; el `<th>` nuevo va PRIMERO) y celda en el `<tr key={item.id}>` (`:183-189`; el `<td>` nuevo va PRIMERO, antes de `dateCell`). `aria-label` de fila: `` `Seleccionar ejecución #${item.id}` ``. **CRÍTICO:** el `onClick` del checkbox DEBE ejecutar `stopPropagation` (lo hace `onRowCheckboxClick`) porque la fila entera abre el drawer (`:187`) — sin eso, cada click de selección abriría el detalle.

**Paso 4 — barra + toast (ancla: antes de `<ExecutionDetailDrawer`, `:258`):**

```tsx
{bulkEnabled && (
  <BulkActionsBar
    count={sel.count}
    running={bulkRunning}
    progress={bulkProgress}
    onClear={sel.clear}
    actions={[
      { id: "copy-links", destructive: false,
        label: (n) => `Copiar ${n} links`,
        run: () => void copySelectedLinks() },
      { id: "delete-selected", destructive: true,
        label: (n) => `Borrar ${n}`, armedLabel: (n) => `¿Borrar ${n}? Confirmar`,
        run: () => void runBulkDelete() },
    ]}
  />
)}
{bulkToast && <Toast toast={bulkToast} onClose={() => setBulkToast(null)} />}
```

**Paso 5 — CSS:** misma clase `.selectCell` de F4 Paso 6, agregada a `ExecutionHistoryPage.module.css`.

**Casos borde codificados:** borrar una ejecución `running` ⇒ si el backend lo rechaza, aparece como fallo por ítem en el Toast agregado y la fila queda seleccionada para decidir (NO se pre-filtra client-side: no adivinamos la política del backend); selección + «Siguiente» de paginación ⇒ los ids de la página anterior desaparecen de `items` ⇒ poda automática (la barra refleja el nuevo count); portapapeles bloqueado (contexto no-seguro) ⇒ Toast de error, sin crash.

**TDD/validación:** `npx tsc --noEmit` exit 0 + smoke manual documentado: seleccionar 2 filas SIN que se abra el drawer; Shift+click de rango; borrar 2 con confirmación armada y ver el Toast; copiar 3 links y pegarlos (3 URLs válidas que abren el drawer correcto); cambiar de página y verificar que la selección se poda; flag OFF ⇒ página idéntica a hoy.

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` exit 0 + smoke completado y anotado.

**Flag:** `STACKY_BULK_ACTIONS_ENABLED`. **Runtimes:** N/A-por-diseño — borrar/copiar operan sobre registros de ejecución ya terminados, agnósticos del runtime que los produjo. **Trabajo del operador: ninguno.**

---

### 4.7 — Integración DIFERIDA con el plan 185 (undo universal) — SOLO documentación, cero código ahora

El plan 185 (CRITICADO v2, **no implementado** al 2026-07-18) introduce `scheduleUndoable` en `frontend/src/services/undoManager.ts`. Contrato de integración congelado acá:

- **Regla de decisión (heredada del 185 §3.2):** una acción de lote solo puede migrar de «confirmación armada» a «undo con gracia» si TODOS sus ítems tienen **inversa natural** (endpoint inverso existente). **Hoy NINGUNA de las 3 acciones piloto califica:** `discard` no tiene endpoint inverso verificado, `deleteOne` es irreversible, `relaunch` no tiene inversa. ⇒ la confirmación armada se mantiene INCLUSO con el 185 implementado.
- **El switch exacto (para futuras acciones reversibles):** cuando (a) exista `frontend/src/services/undoManager.ts` en el checkout Y (b) la acción declare inversa, el wiring de la página reemplaza la llamada directa `runnerRef.current.run(...)` por `scheduleUndoable({ id: "bulk:<actionId>:" + Date.now(), label: "<N> <acción>", commit: () => <el mismo run(...)>, onUndo: <revertir la mutación optimista local> })`, y esa acción deja de marcar `destructive: true` (el toast de undo del 185 reemplaza a la confirmación previa). Es un cambio LOCAL al wiring de la acción: `BulkActionsBar`, `useRowSelection`, `selectionModel` y `bulkModel` NO cambian.
- Mientras tanto (estado actual): el lote ejecuta directo tras la confirmación armada — exactamente lo especificado en F4/F5.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación (codificada en fase) |
|---|---|---|
| R1 | **Ids desaparecidos tras refresh** (refetch de 30 s de la Bandeja, invalidaciones, borrados): el lote actuaría sobre ítems que ya no existen | Invariante §3.6 + `pruneToKnown` en el hook (F3 paso 2, tests F1); el worker de relanzamiento revalida la fila y falla por ítem si no está (F4 paso 3) |
| R2 | **Selección sobre lista filtrada/paginada**: el operador cree que seleccionó "todo" cuando solo ve una página | «Seleccionar todo lo visible» opera SOLO sobre las filas cargadas (§3.6); el contador dice el número exacto; cambiar página/filtro poda la selección (test `prune_elimina_ids_desaparecidos`) |
| R3 | **Doble submit del lote** (doble click en Confirmar, click en dos acciones) | Guard `createBulkRunner` (`run` ⇒ `null` si hay lote en curso, test `runner_guard_doble_submit`) + botones `disabled={running}` (F3 paso 5) |
| R4 | **Resultado parcial** (algunos ítems fallan): éxito silencioso o fallo total serían mentira | Runner captura por ítem sin cortar el lote; `summarizeBulk` reporta «X de N · fallaron: #a, #b» en el Toast de la casa; los fallidos QUEDAN seleccionados para reintentar (`retainOnly`, F4/F5) |
| R5 | **Colisión con la selección nativa de texto** en Shift+click | `user-select: none` SOLO en la celda del checkbox (`.selectCell`, no en toda la fila — se puede seguir copiando texto de otras celdas) + `getSelection().removeAllRanges()` en el handler (F3 paso 4) |
| R6 | **Colisión con el onClick de fila del Historial** (abriría el drawer al seleccionar) | `stopPropagation()` SIEMPRE en `onRowCheckboxClick` (F3 paso 4; smoke F5) |
| R7 | **Escape ambiguo** con drawer abierto (cerraría drawer Y deseleccionaría) | `escapeDisabled: detailId !== null || bulkRunning` — con drawer abierto o lote corriendo, Escape no toca la selección (F4/F5 paso 1) + guard de foco `shouldClearSelectionOnEscape` (checkbox propio NO bloquea; campos de texto SÍ, tests F2) |
| R8 | **Ratchet de confirmaciones del plan 185 / gate del 164**: sumar `confirm()` nativos rompería sus gates | Cero diálogos nativos nuevos: confirmación armada de dos pasos en la barra (§3.1, F3 paso 5) |
| R9 | **Acciones por fila durante un lote** (p. ej. descartar a mano un id que el lote está procesando) | El fallo del ítem duplicado se reporta como fallo por ítem (R4); documentado como límite aceptado — no se deshabilitan los botones por fila (cambiaría semántica existente, §3.9) |
| R10 | **Sesión paralela** editando las mismas páginas (173/174/175 también tocan `ExecutionHistoryPage.tsx`) | Pre-flight `git status` por archivo (§3.11); anclas por TEXTO, no por línea; STOP y reporte si hay WIP ajeno |
| R11 | **Checkbox primitiva sin forwardRef** (tri-estado de cabecera imposible por ref directa) | Wrapper `<span ref>` + `querySelector("input")` + propiedad `indeterminate` en effect (F4 paso 4) — sin tocar la primitiva del 162 |
| R12 | **Relanzar en lote dispara N ejecuciones con costo real** | `destructive: true` ⇒ confirmación armada con el N visible en el label («¿Relanzar 12? Confirmar») + progreso visible + resultado agregado (F4) + cap duro `BULK_EXECUTION_ACTION_MAX = 25` por lote SOLO para acciones de ejecución ([ADICIÓN ARQUITECTO] C5, F2/F4) |

---

## 6. Fuera de scope (explícito)

1. **Endpoints bulk nuevos en el backend** (`POST /api/executions/bulk-*` o similares): el lote es N llamadas cliente a endpoints por ítem existentes. Si alguna acción futura lo necesitara, es OTRO plan.
2. **Drag-select con mouse** (arrastrar para seleccionar): solo click/Shift/Ctrl.
3. **Persistencia de la selección** entre sesiones, navegaciones o páginas de datos: la selección es efímera por diseño (§3.6).
4. **«Seleccionar todos los que matchean el filtro» server-side** (seleccionar más allá de lo cargado): requeriría contrato backend de conteo/ids que hoy no existe (el historial ni siquiera expone `total`; backlog del plan 173 F5).
5. **TicketBoard y TeamScreen**: TicketBoard es archivo caliente con vista cards/grafo (candidata natural una vez que 164/175 aterricen); TeamScreen no tiene bandeja de volumen.
6. **Undo real del lote**: integración diferida documentada en §4.7; depende del plan 185 y de inversas que hoy no existen.
7. **Cancelar un lote en curso**: el lote es secuencial y corto (decenas de ítems contra Flask local); un botón «Detener» agregaría estados intermedios (parcial-por-abandono) sin dolor real que lo justifique hoy.
8. **Atajos de teclado de selección** (Ctrl+A, navegación con flechas + Space): pertenecen al registro de atajos del plan 172; cuando exista, registrar ahí `Ctrl+A = seleccionar todo lo visible` es una extensión de 5 líneas sobre `useRowSelection`.

---

## 7. Glosario + Orden de implementación + DoD

### 7.1 Glosario (para el modelo menor)

- **Arnés de flags:** registry central de configuración (`backend/services/harness_flags.py`, `FLAG_REGISTRY` de `FlagSpec`) servido por `GET/PUT /api/harness-flags` y renderizado automáticamente en Settings→Arnés. Registrar un `FlagSpec` = la flag aparece sola en la UI.
- **Patrón triple de una flag bool default ON:** (1) `FlagSpec(default=True)` en `FLAG_REGISTRY` + alta en `_CATEGORY_KEYS`; (2) default EFECTIVO en `backend/config.py` (`os.getenv(KEY, "true")…`); (3) alta en `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py`). Faltar cualquiera rompe K2.
- **`config` vs `config.config` (gotcha):** en módulos backend, `config` es el MÓDULO python; la instancia con los atributos de flags es `config.config`. Este plan no necesita leer la flag en backend (la consume solo el frontend), pero el test F0 verifica el default a nivel FUENTE justamente para esquivar los side effects del import.
- **Ratchet:** test que congela un baseline de deuda y solo permite que baje. Relevantes acá: uiDebtRatchet (inline styles, plan 138), formDebtRatchet (tags crudos, plan 162), `HARNESS_TEST_FILES` (registro de tests backend, `run_harness_tests.sh` + `test_harness_ratchet_meta.py`), baseline `confirmCallCount` (plan 185, si ya aterrizó).
- **Primitivas `ui/`:** componentes canónicos del barrel `frontend/src/components/ui/index.ts` (plan 138/162): `Button`, `Checkbox`, `Spinner` y el resto de exports del barrel (lista completa en ese index.ts). En `.tsx` nuevos son OBLIGATORIAS (no tags crudos).
- **Toast de la casa:** `frontend/src/components/Toast.tsx`, canal para resultados de ACCIONES, controlado por el caller (la página tiene el estado y lo renderiza).
- **Ancla (de selección):** el id del último click plano/ctrl; Shift+click selecciona el rango entre el ancla y el id clickeado.
- **Confirmación armada (two-step):** primer click cambia el label del botón a «¿…? Confirmar»; segundo click dentro de 5 s ejecuta; Escape/cambio de selección/timeout desarman. Patrón heredado del plan 175 §F3, sin diálogos nativos.
- **Poda (`pruneToKnown`):** intersección de la selección con los ids actualmente cargados; corre en cada cambio de la lista.
- **Runtime:** motor de ejecución de agentes (Codex CLI / Claude Code CLI / GitHub Copilot Pro). Este plan no toca ninguno: es UI del dashboard + 1 flag.
- **HITL (human-in-the-loop):** principio innegociable de Stacky — el operador decide; acá: él selecciona, él confirma, él ve el resultado.

### 7.2 Orden de implementación (numerado, sin ambigüedad)

1. **F0** — flag backend (tests primero, rojos → implementación → K1/K2/K3 verdes) + `bulkFlags.ts` (test primero → K6 verde).
2. **F1** — `selectionModel.test.ts` (rojo) → `selectionModel.ts` → K4 verde.
3. **F2** — `bulkModel.test.ts` (rojo) → `bulkModel.ts` → K5 verde.
4. **F3** — `BulkActionsBar.tsx` + `.module.css` + `useRowSelection.ts` → `tsc` + K8/K9 verdes.
5. **F4** — wiring Bandeja de revisión → `tsc` verde + smoke manual anotado.
6. **F5** — wiring Historial → `tsc` verde + smoke manual anotado.
7. Cierre: correr TODOS los KPIs de §1 en orden K1→K9 y pegar el output real en el resumen (cero falsos verdes: la verificación final la hace el agente principal leyendo output, no un reporte de subagente).

### 7.3 DoD global (todos obligatorios)

- [ ] K1..K9 de §1 verdes con output pegado (comandos y shells exactos de la tabla).
- [ ] Smokes manuales de F4 y F5 completados y anotados (incluye el smoke de flag OFF ⇒ UI idéntica).
- [ ] `git status` final revisado: SOLO los archivos listados en F0-F5 tocados; `backend/harness_defaults.env` NO tocado a mano; sin `stash`/`reset`/`checkout` (repo compartido con sesión paralela).
- [ ] Cero `confirm(`/`alert(`/`prompt(` nuevos en el diff — solo líneas AGREGADAS cuentan (C7; Git Bash desde `frontend`): `git diff -- src | grep -cE '^\+.*(confirm|alert|prompt)\('` → `0`.
- [ ] Encabezado de estado de ESTE doc actualizado (PROPUESTO → IMPLEMENTADO con fecha) al cerrar.

---

*Fin del plan 187 v2 (CRITICADO, veredicto v1: APROBADO-CON-CAMBIOS, C1..C7 aplicados). Siguiente paso del pipeline: `implementar-plan-stacky`.*
