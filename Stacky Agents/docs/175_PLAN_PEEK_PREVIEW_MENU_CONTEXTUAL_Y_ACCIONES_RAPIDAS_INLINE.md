# Plan 175 — Peek de entidades, menú contextual unificado y acciones rápidas inline

Serie UX Cockpit del Operador (172-175) — plan 4/4 — **v2 CRITICADO (APROBADO-CON-CAMBIOS)** — 2026-07-18

> ### Changelog v1 → v2 (crítica adversarial, evidencia verificada en frío 2026-07-18)
> - **C1 (IMPORTANTE):** `routes.ts` **YA existe** en `frontend/src/services/routes.ts` (plan 165
>   IMPLEMENTADO, no "NO existe" como afirmaba v1). El grep de v1 miró la ruta equivocada
>   (`frontend/src/routes.ts`, top-level). Corregida la evidencia de §2.5 y §4. `peekLinks.ts`
>   ahora **DELEGA en `serializeRoute`** (reuso, no reinvención) y usa la clave **canónica `?exec=`**
>   — no el alias legacy `?execution=`. La dependencia con 165 pasa de "blanda futura" a
>   **satisfecha hoy**.
> - **C2 (IMPORTANTE):** colisión con el plan **194** (copyService/copyFormats + ratchet `writeText`),
>   hermano de la serie no declarado en v1. `clipboard.ts` **delega en `copyService` cuando existe**
>   y solo cae al wrapper local si 194 aún no está mergeado — así no reinventa ni viola el ratchet
>   `writeText`. Nueva fila 194 en §4.
> - **C3 (IMPORTANTE) + [ADICIÓN ARQUITECTO]:** el camino de teclado de v1 quedaba **inerte sin el
>   172** (filas no enfocables). Ahora 175 pone su propio `tabIndex={0}` (gated por flag) en las
>   filas/cards cableadas ⇒ menú y peek accesibles por teclado **standalone**; el 172 los promueve
>   a foco roving cuando aterrice. Cierra la exigencia "100% accesible por teclado".
> - **C4 (MENOR):** limpiada la prosa de razonamiento a medias del gating de F4 (quedaba
>   `"se usa STACKY_UI_PEEK_ENABLED… NO: decisión…"`, ambigua para un modelo menor).
> - **C5 (MENOR):** los cuerpos de `buildExecutionPeek`/`buildTicketPeek`/`menuKeydown`/`armTransition`
>   estaban como comentarios-prosa; se dejan **fijados por los tests** (nota explícita) y con la
>   lista de campos literal.
> - **C6 (MENOR):** corregida la afirmación falsa "shell v2 es opt-in" — su default efectivo en
>   `config.py` es `"true"` (ON), igual que estas flags.
> - **C7 (MENOR):** F0 agrega las 2 entradas en `harness_flags_help.py` (`PLAIN_HELP`), paridad con
>   el patrón del plan 139 (texto de ayuda para el operador en Settings).
> - **C8 (MENOR):** las queryKeys `["execution-detail"/"ticket-detail", id]` se declaran "propuestas
>   a congelar con 174" — el implementador debe verificar contra el 174 antes de fijarlas.

> **Autor:** StackyArchitectaUltraEficientCode · **Cierra la serie** Cockpit del Operador.
> **Hermanos:** 172 (teclado primero: registro de atajos + overlay "?" + foco roving), 173 (vistas
> guardadas + preferencias de tabla), 174 (rendimiento percibido: virtualización + prefetch +
> cache react-query). Este plan **consume** lo de sus hermanos como **dependencia blanda**: si un
> hermano no está implementado, la feature degrada de forma explícita y declarada — nunca rompe.
> **Toda la evidencia archivo:línea de este doc fue verificada en frío el 2026-07-18.** Los números
> de línea son referencia de ese día: **toda edición se ancla por TEXTO/símbolo citado, no por
> número de línea** (hay sesiones paralelas conocidas en este repo).

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** hoy, ver el detalle de una ejecución exige clickear la fila y abrir el
drawer completo (`frontend/src/pages/ExecutionHistoryPage.tsx:187` `onClick={() => setDetailId(item.id)}`
→ `ExecutionDetailDrawer` en `:258-261`), y ver el detalle de un ticket exige expandir la card
(`frontend/src/pages/TicketBoard.tsx:422` `cardHeader onClick={() => setExpanded(...)}`). No existe
hover-card, no existe menú contextual (grep `onContextMenu|contextmenu` en `frontend/src` →
**0 archivos**, verificado 2026-07-18) y no existen acciones rápidas por fila. Este plan agrega
tres capacidades del cockpit, todas invisibles hasta que el operador las usa: **(a)** un
componente **PeekCard** reutilizable — hover sostenido ≥400 ms sobre una fila muestra una tarjeta
flotante con el resumen de la entidad (ejecución y ticket), alimentada del cache de react-query
(contrato de queryKeys compartido con el plan 174; sin 174, degrada a fetch on-demand con Spinner
chico); **(b)** un **menú contextual clic-derecho unificado** (UN solo componente para toda la
app) con acciones por tipo de entidad, sobre un **registro tipado de acciones por `kind`** que
extiende el `CommandKind` de la paleta (plan 129); **(c)** **acciones rápidas inline** en filas
(iconos al hover) restringidas por construcción a acciones **seguras** (copiar link, abrir).
**TODA acción con efecto (cancelar run, borrar ejecución, publicar a ADO) pasa por el diálogo
canónico del plan 164 con confirmación explícita — human-in-the-loop innegociable**: ninguna
acción destructiva o de publicación se ejecuta sin que el operador confirme.

**KPIs binarios (comandos exactos):**

Frontend — correr desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` (POSIX:
`cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"`). vitest SIEMPRE por archivo
(contaminación cross-file conocida):

- **KPI-1:** `npx vitest run src/services/uiCockpitFlags.test.ts` → exit 0 (parser de flags del health).
- **KPI-2:** `npx vitest run src/services/entityActions.test.ts` → exit 0 (registro tipado; invariante "quick ⇒ safe").
- **KPI-3:** `npx vitest run src/services/peekLinks.test.ts` → exit 0 (deep-links puros).
- **KPI-4:** `npx vitest run src/services/peekModel.test.ts` → exit 0 (reducer del peek + builders con format.ts).
- **KPI-5:** `npx vitest run src/services/contextMenuModel.test.ts` → exit 0 (clamp de posición + teclado + armado de confirmación).
- **KPI-6:** `npx tsc --noEmit` → exit 0.
- **KPI-7 (ratchet UI):** `grep -c "style={{" src/components/peek/PeekCard.tsx` → `0`; ídem para
  `src/components/contextmenu/ContextMenu.tsx` → `0` (archivos `.tsx` nuevos nacen con alcance
  CERO de inline-style — uiDebtRatchet, plan 138).

Backend — correr desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` (venv py3.13):

- **KPI-8:** `venv/Scripts/python.exe -m pytest tests/test_ui_cockpit_flags.py -q` → exit 0.
- **KPI-9:** `venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q` → exit 0 (las 2
  flags nuevas quedan curadas y categorizadas; si falta el alta en `_CURATED_DEFAULTS_ON` o en
  `_CATEGORY_KEYS`, este archivo rompe SOLO — es el gate).
- **KPI-10:** `grep -c "test_ui_cockpit_flags.py" scripts/run_harness_tests.sh` → `1` (registro en
  `HARNESS_TEST_FILES`; sin esto el meta-test del ratchet de tests rompe).

**Impacto esperado (observación manual):** inspeccionar 10 ejecuciones pasa de 10 aperturas de
drawer (10 clics + 10 cierres) a pasar el mouse por las filas; copiar el link de una ejecución
pasa de "abrir drawer → mirar URL → armarla a mano" a 1 clic en el icono de la fila; las acciones
frecuentes (cancelar, borrar, abrir en ADO) quedan a un clic-derecho de distancia — siempre con
confirmación de marca cuando tienen efecto.

---

## 2. Por qué ahora / gap que cierra (evidencia verificada)

1. **No hay menú contextual en TODO el frontend:** grep `onContextMenu|contextmenu` en
   `frontend/src` → **0 archivos** (verificado 2026-07-18). El clic-derecho hoy muestra el menú
   del navegador, que no sabe nada de Stacky.
2. **El detalle exige navegación pesada:** `ExecutionHistoryPage.tsx:183-227` renderiza `<tr>` con
   `onClick={() => setDetailId(item.id)}` (`:187`) como ÚNICA interacción; el drawer
   `ExecutionDetailDrawer` (`:258-261`) es la única vista de detalle. En `TicketBoard.tsx`, la
   card (`function TicketCard` en `:249`, `styles.cardHeader` con `onClick` en `:422`) solo
   expande/colapsa.
3. **Los datos del resumen YA están en memoria:** `ExecutionHistoryItem`
   (`frontend/src/api/endpoints.ts:1212-1233`) trae id, ticket_id, ticket_title, agent_type,
   agent_name, runtime, model, status, started_at, finished_at, duration_ms, cost_usd, tokens_in,
   tokens_out, produced_files_count, error_message y local_insight — **todo lo que una hover-card
   necesita, sin fetch adicional**. Ídem `Ticket` (`frontend/src/types.ts:87-110`: ado_id, title,
   ado_state, ado_url, priority, work_item_type, assigned_to_ado, stacky_status, last_synced_at,
   pipeline_summary). El gap es de PRESENTACIÓN, no de datos.
4. **Las acciones ya existen como endpoints, dispersas en la UI:** `Executions.cancel`
   (`endpoints.ts:1279-1280`), `Executions.deleteOne` (`:1295-1296`), `Executions.publish`
   (`:1272-1273`), `Executions.byId` (`:1267`), `Tickets.byId` (`endpoints.ts:143`), link ADO por
   ticket (`TicketBoard.tsx:585-588` usa `ticket.ado_url`; helper `adoUrl` en
   `frontend/src/utils/trackerUrls.ts:10-11`). Hoy llegar a cada una exige superficies distintas.
5. **El deep-link de ejecución tiene builder + receptor canónicos YA implementados (plan 165):**
   `frontend/src/services/routes.ts` **existe** (plan 165 IMPLEMENTADO F1-F3). `serializeRoute({tab:"history", exec:<id>})`
   produce la clave **canónica `?exec=<id>`** (`routes.ts:95`); `ExecutionHistoryPage` la recibe vía
   la prop `exec` parseada por `parseRoute` (`ExecutionHistoryPage.tsx:58-76`), que **reemplazó** al
   receptor viejo `?execution=` (comentado como "roto" en `:67`). `parseRoute` acepta `execution`
   SOLO como **alias legacy** (`EXEC_KEYS = ["exec","execution"]`, `routes.ts:27`). Por eso
   "Copiar link" **DELEGA en `serializeRoute`** (reuso, clave canónica `?exec=`) en vez de construir
   un literal con el alias legacy. (Corrección **C1**: v1 afirmaba que `routes.ts` "no existía" por
   grepear `frontend/src/routes.ts` top-level en vez de `frontend/src/services/routes.ts`.)
6. **La infraestructura de tipos por entidad ya existe:** `CommandKind` en
   `frontend/src/components/commandPaletteData.ts:10-19` (incluye `"execution"` y `"ticket"`).
   Este plan lo REUSA vía `Extract<>` en vez de inventar otro enum.
7. **El sustrato de flags está maduro:** `FlagSpec` (`backend/services/harness_flags.py:21-41`),
   categoría `"interfaz_ui"` ya existente (`harness_flags.py:325-327`, hoy solo con
   `STACKY_UI_SHELL_V2_ENABLED`), exposición al frontend por `/api/diag/health`
   (`backend/api/diag.py:410-411`) y lectura en el frontend con el patrón del plan 139
   (`App.tsx:152-163`).

**Entidades elegidas (leyendo el código): ejecución y ticket.** Son las 2 entidades con listados
reales de alto tráfico (`ExecutionHistoryPage.tsx` tabla de filas; `TicketBoard.tsx` cards) y con
shape de resumen ya cargado en el cliente (evidencia en el punto 3). Docs/planes quedan fuera de
scope (§7): su listado vive en otra página con su propio visor y no tiene shape de resumen
uniforme cargado.

---

## 3. Principios y guardarraíles (restricciones NO negociables)

1. **Human-in-the-loop innegociable.** Ninguna acción destructiva (cancelar run, borrar
   ejecución) ni de publicación (publicar a ADO) se ejecuta sin confirmación explícita del
   operador. El camino canónico es el diálogo del plan 164 (`useConfirm()` promise-based); como el
   164 aún no está implementado, la degradación declarada es una confirmación de dos pasos DENTRO
   del propio menú (§5 F3), jamás un diálogo nativo del navegador y jamás ejecución directa.
   Amplificar al operador, nunca reemplazarlo.
2. **Cero trabajo extra para el operador.** Las dos flags nuevas nacen con **default ON**
   (invisible/automático): el peek aparece solo al hover sostenido, el menú solo al clic-derecho,
   las acciones rápidas solo al hover de fila. Sin pasos manuales nuevos, sin config nueva, sin
   migraciones. **Ninguna de las 4 excepciones duras aplica:** no hay bypass de revisión humana
   (todo efecto pasa por confirmación, punto 1); no hay acción destructiva/irreversible nueva
   (solo se re-exponen acciones existentes CON confirmación); no hay prerequisito no garantizado
   (todo corre sobre endpoints y datos ya existentes); no se reduce seguridad (con flag OFF la UI
   es byte-idéntica a hoy).
3. **Paridad de 3 runtimes por construcción.** Todo este plan es dashboard (frontend React +
   lectura de flags por Flask). Es **agnóstico del runtime de agentes** (Codex CLI, Claude Code
   CLI, GitHub Copilot Pro): ninguna fase toca el camino de ejecución. Las acciones del menú
   disparan endpoints que ya son runtime-agnósticos (`/api/executions/<id>/cancel`, `delete`,
   `publish-to-ado`). Se declara igual fase por fase.
4. **Mono-operador sin auth real.** Nada de RBAC ni "permisos por usuario" en el registro de
   acciones: la visibilidad de una acción depende SOLO del estado de la entidad (p. ej. "cancelar"
   solo si `status === "running"`).
5. **Reusar, no reinventar.** Tipos: `CommandKind` (plan 129). Formato: SIEMPRE los 11 exports de
   `frontend/src/services/format.ts` (plan 161; hay ratchet anti-Intl — prohibido formatear a
   mano). Primitivas: `IconButton`, `Spinner`, `StatusChip` del barrel `components/ui` (planes
   138/140). Motion: tokens `--duration-*`/presets del plan 143 en los CSS modules. Cache:
   react-query ya montado (`@tanstack/react-query ^5.59.0`, `frontend/package.json:13`;
   `QueryClientProvider` en `main.tsx`). Deep-link: **builder canónico `serializeRoute` del plan 165
ya implementado** (`services/routes.ts`), no construir URLs a mano. Copiado: **`copyService` del
plan 194** cuando esté mergeado (C2), nunca `navigator.clipboard.writeText` crudo nuevo.
6. **Lógica pura, no `render()`.** `@testing-library/react` y `jsdom` NO están en
   `frontend/package.json` (gap estructural conocido). TODA la lógica de este plan (parser de
   flags, registro de acciones, reducer del peek, clamp/teclado/armado del menú, builders de
   campos, deep-links) vive en módulos `.ts` PUROS con tests de vitest sin DOM, como
   `commandPaletteData.test.ts`. Los componentes `.tsx` son cáscaras finas; su comportamiento DOM
   se valida con `tsc --noEmit` + smoke manual (§5 F5).
7. **Ratchets del repo se respetan, no se gamean.** (a) `.tsx` nuevos: CERO `style={{}}` — el
   posicionamiento dinámico del peek y del menú va por `ref` + efecto imperativo
   (`el.style.left = ...` dentro de `useLayoutEffect`), patrón bendecido por el gotcha del
   uiDebtRatchet. (b) CSS modules nuevos: colores SOLO por tokens `var(--...)` de `theme.css`,
   nunca hex. (c) Tests backend nuevos se registran en `HARNESS_TEST_FILES`. (d) Nombres de
   variables: el resultado de cualquier hook de confirmación se llama `askConfirm`/`ask`, JAMÁS el
   identificador de la familia de diálogos nativos del navegador (el gate del plan 164 F2 caza ese
   identificador en minúsculas seguido de paréntesis; regla heredada textualmente del 164 §5 F2).
8. **Dependencias blandas, degradación explícita.** Tabla completa en §5.0. Regla: este plan
   compila y funciona con CERO hermanos implementados; cada hermano que aterrice lo mejora sin
   tocar este código (contratos de integración congelados acá).
9. **Backward-compatible.** Flag OFF ⇒ comportamiento byte-idéntico al actual (clic-derecho
   nativo del navegador incluido). Ningún handler existente se elimina ni cambia de semántica.
10. **No degradar performance.** El peek no hace fetch en el camino feliz (usa datos ya en
    memoria); los listeners de hover son por fila, pasivos y sin trabajo hasta cumplirse el delay;
    el menú se monta solo mientras está abierto (render condicional, no display:none permanente).

---

## 4. Contratos de integración con los hermanos (dependencias blandas)

| Hermano | Qué consume 175 | Contrato congelado | Degradación SIN el hermano |
|---|---|---|---|
| **172 Teclado primero** | Combos `Shift+F10` / tecla `ContextMenu` para abrir el menú desde el teclado; tecla `p` para fijar el peek; filas enfocables (foco roving). | 175 deja cableado el handler `onKeyDown` EN la fila/card (§5 F3 paso 4). 172 aporta: (a) filas enfocables (roving) y (b) el alta de los combos en su registro central + overlay "?". | Sin 172 las filas no son enfocables ⇒ el menú por teclado y el peek por tecla quedan **inactivos** (el handler existe pero nunca recibe foco). El menú por mouse y el peek por hover funcionan al 100%. Nada rompe. |
| **173 Vistas guardadas** | Nada. | Sin interacción: 173 persiste filtros/columnas; 175 no toca ni lee esas preferencias. | N/A. |
| **174 Rendimiento percibido** | Cache/prefetch de react-query para el enriquecimiento del peek. | **queryKeys compartidas (propuestas: `["execution-detail", id]` → `Executions.byId(id)` y `["ticket-detail", id]` → `Tickets.byId(id)`). C8: el implementador VERIFICA contra el 174 antes de fijarlas — si 174 ya congeló otras claves, 175 adopta las del 174 (174 es el dueño del cache).** 174 debe poblarlas con su prefetch on-hover; 175 las lee con `queryClient.getQueryData(...)`. | Sin 174 el cache está frío ⇒ el peek muestra los campos de la fila (que NO requieren fetch) al instante, y el bloque de enriquecimiento hace `queryClient.fetchQuery(...)` on-demand mostrando `<Spinner size="sm">` — explícito y acotado a ese bloque. |
| **164 Diálogo canónico** | `useConfirm()` promise-based para las acciones con efecto. | Punto ÚNICO de migración: `frontend/src/services/confirmGateway.ts` (§5 F1 paso 3). Cuando 164 aterrice, se cambia SOLO la implementación de ese módulo a `useConfirm()` (contrato del 164 §F0: `(opts) => Promise<boolean>` con `tone: "danger"`). | Sin 164 (estado actual: PROPUESTO, `components/ui/Dialog.tsx` no existe), `confirmGateway` v1 = confirmación de dos pasos DENTRO del menú (máquina `armTransition`, §5 F3): primer clic arma el ítem ("¿Borrar? Clic de nuevo"), segundo clic ejecuta; Escape/cerrar desarma. HITL intacto, cero diálogos nativos. |
| **165 Contrato de URL — YA SATISFECHA (C1)** | Builder canónico de deep-links (`serializeRoute` de `frontend/src/services/routes.ts`, ya implementado). | `frontend/src/services/peekLinks.ts` es el único módulo que arma URLs y **delega HOY** en `serializeRoute({tab:"history", exec:id})` → clave canónica `?exec=<id>` (`routes.ts:95`). | N/A — 165 está implementado. (Contingencia sólo si `routes.ts` fuera removido: fallback al literal `/history?exec=<id>` con la clave canónica, que `parseRoute` recibe; nunca el alias legacy `?execution=`.) |
| **194 Portapapeles universal — COLISIÓN (C2)** | `copyService` (copiado con feedback + formatos) del plan 194. | `frontend/src/services/clipboard.ts` **delega en `copyService` si está presente**; toda copia de 175 pasa por ahí para no reinventar ni violar el ratchet `writeText` que introduce 194. | Sin 194 mergeado (estado actual: `copyService.ts` vive en la rama `impl/ux`, no en este árbol), `clipboard.ts` usa un wrapper local `navigator.clipboard.writeText` con fallback `execCommand`. Cuando 194 aterrice, se reemplaza SOLO el cuerpo de `clipboard.ts` por `copyService`. |

---

## 5. Fases

> **Pre-flight OBLIGATORIO por fase y por archivo tocado:** `git status -- "<ruta>"`. Si hay WIP
> ajeno sin commitear, STOP y avisar al orquestador (sesiones paralelas en el mismo árbol son un
> escenario real conocido; el plan 164 toca `TicketBoard.tsx` y las mismas superficies). Staging
> quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos:** frontend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`
> (`npx vitest run src/<archivo>` POR ARCHIVO; `npx tsc --noEmit` al cerrar cada fase). Backend
> desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`
> (`venv/Scripts/python.exe -m pytest tests/<archivo> -q` POR ARCHIVO, nunca la suite entera).
>
> **Anclas por TEXTO:** todo "editar en :NNN" de este doc se localiza por el símbolo/cadena
> citada, no por el número de línea.

---

### F0 — Flags backend + exposición en health + lectura frontend

**Objetivo (1 frase):** crear `STACKY_UI_PEEK_ENABLED` y `STACKY_UI_CONTEXT_MENU_ENABLED`
(default **ON**, configurables desde la UI de Settings), exponerlas por `/api/diag/health` y darle
al frontend un hook de lectura con parser puro testeable. **Valor:** kill-switch de marca por
feature sin trabajo del operador; el resto del plan se cablea detrás de estas flags.

**Archivos:**
- MODIFICADO `backend/services/harness_flags.py` — 2 `FlagSpec` nuevas en `FLAG_REGISTRY` + 2 keys
  en `_CATEGORY_KEYS["interfaz_ui"]` (hoy `harness_flags.py:325-327`, tupla con solo
  `STACKY_UI_SHELL_V2_ENABLED`).
- MODIFICADO `backend/config.py` — 2 atributos con default efectivo `"true"` (el default EFECTIVO
  vive en config.py; el de FlagSpec es hint de UI — gotcha conocido).
- MODIFICADO `backend/api/diag.py` — 2 campos aditivos en el dict de retorno de `health()`, junto
  a `"shell_v2_enabled"` (`diag.py:415`, mismo patrón `getattr`).
- MODIFICADO `backend/services/harness_flags_help.py` — 2 entradas `PlainHelp` en `PLAIN_HELP` (C7),
  ancla por TEXTO `"STACKY_UI_SHELL_V2_ENABLED"` (`harness_flags_help.py:1330`). Da el texto de
  ayuda que ve el operador en Settings; paridad con el patrón del plan 139
  (`test_plan139_shell_flag.py:32` verifica que su flag esté en `PLAIN_HELP`).
- MODIFICADO `backend/tests/test_harness_flags.py` — agregar las 2 keys al set
  `_CURATED_DEFAULTS_ON` (definido en `test_harness_flags.py:467`). Sin esto,
  `test_default_known_only_for_curated` (`:749`) rompe: es el gate, no se gamea.
- NUEVO `backend/tests/test_ui_cockpit_flags.py`.
- MODIFICADO `backend/scripts/run_harness_tests.sh` — agregar `"tests/test_ui_cockpit_flags.py"`
  al array `HARNESS_TEST_FILES` (`run_harness_tests.sh:20`; la lista es ratchet: solo crece, `:8`).
- NUEVO `frontend/src/services/uiCockpitFlags.ts` (parser PURO).
- NUEVO `frontend/src/services/uiCockpitFlags.test.ts`.
- NUEVO `frontend/src/hooks/useUiFlags.ts` (wrapper react-query, sin lógica).

**Paso 1 — TESTS PRIMERO (backend), `backend/tests/test_ui_cockpit_flags.py`:**

```python
"""Plan 175 F0 — flags del cockpit (peek + menu contextual)."""
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_KEYS = ("STACKY_UI_PEEK_ENABLED", "STACKY_UI_CONTEXT_MENU_ENABLED")


def test_flags_registered_bool_global_default_on():
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _KEYS:
        assert key in by_key, f"{key} no esta en FLAG_REGISTRY"
        spec = by_key[key]
        assert spec.type == "bool"
        assert spec.group == "global"
        assert spec.default is True, f"{key} debe declarar default=True (default ON)"


def test_flags_categorized_interfaz_ui():
    from services.harness_flags import categorize
    for key in _KEYS:
        assert categorize(key) == "interfaz_ui"


def test_config_effective_default_is_true_literal():
    # El default EFECTIVO vive en config.py (FlagSpec es cosmetico). Se verifica
    # a nivel fuente para no recargar el modulo config (side effects conocidos).
    src = (_BACKEND / "config.py").read_text(encoding="utf-8")
    for key in _KEYS:
        m = re.search(rf'{key}: bool = os\.getenv\(\s*"{key}", "(\w+)"', src)
        assert m is not None, f"config.py no define {key} con el patron canonico"
        assert m.group(1) == "true", f"{key}: default efectivo debe ser \"true\""


def test_health_exposes_both_ui_flags():
    src = (_BACKEND / "api" / "diag.py").read_text(encoding="utf-8")
    assert '"ui_peek_enabled"' in src
    assert '"ui_context_menu_enabled"' in src
    assert "STACKY_UI_PEEK_ENABLED" in src
    assert "STACKY_UI_CONTEXT_MENU_ENABLED" in src
```

Correr y ver ROJO por la razón correcta (keys ausentes):
`venv/Scripts/python.exe -m pytest tests/test_ui_cockpit_flags.py -q`

**Paso 2 — `harness_flags.py`.** En `FLAG_REGISTRY` (mismo formato que el FlagSpec de
`STACKY_UI_SHELL_V2_ENABLED`, `harness_flags.py:3180-3192`, pero con `default=True`):

```python
    # ── Plan 175 — Cockpit: peek + menu contextual ────────────────────────────
    FlagSpec(
        key="STACKY_UI_PEEK_ENABLED",
        type="bool",
        default=True,  # default ON (directiva flags nuevas ON; curada en _CURATED_DEFAULTS_ON)
        label="Peek: tarjeta flotante al hover",
        description=(
            "Plan 175 — Hover sostenido sobre una fila de Historial o una card de "
            "Tickets muestra una tarjeta con el resumen de la entidad, sin abrir el "
            "detalle. OFF = comportamiento identico al actual."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_UI_CONTEXT_MENU_ENABLED",
        type="bool",
        default=True,  # default ON (directiva flags nuevas ON; curada en _CURATED_DEFAULTS_ON)
        label="Menu contextual en filas",
        description=(
            "Plan 175 — Clic-derecho sobre una fila de Historial o una card de Tickets "
            "abre un menu de acciones de Stacky; toda accion con efecto pide "
            "confirmacion. OFF = clic-derecho nativo del navegador, como hoy."
        ),
        group="global",
    ),
```

Y en `_CATEGORY_KEYS`, la tupla `"interfaz_ui"` (ancla: comentario
`# Plan 139 — shell v2`) queda:

```python
    "interfaz_ui": (
        "STACKY_UI_SHELL_V2_ENABLED",  # Plan 139 — shell v2 (sidebar agrupada + TopBar + iconografía)
        "STACKY_UI_PEEK_ENABLED",          # Plan 175 — peek al hover
        "STACKY_UI_CONTEXT_MENU_ENABLED",  # Plan 175 — menú contextual
    ),
```

**Paso 3 — `config.py`** (ancla por TEXTO: bloque de `STACKY_UI_SHELL_V2_ENABLED`, hoy en
`config.py:1345-1346`; mismo patrón `os.getenv(..., "true").strip().lower() == "true"`. Nota C6:
el shell v2 también tiene default efectivo `"true"` en config.py — su comentario "opt-in" está
desactualizado; estas 2 flags nuevas siguen el mismo default ON):

```python
    # Plan 175 — Cockpit del operador: peek + menu contextual (default ON; con OFF
    # la interfaz es byte-identica a la actual).
    STACKY_UI_PEEK_ENABLED: bool = os.getenv(
        "STACKY_UI_PEEK_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_UI_CONTEXT_MENU_ENABLED: bool = os.getenv(
        "STACKY_UI_CONTEXT_MENU_ENABLED", "true"
    ).strip().lower() == "true"
```

**Paso 4 — `api/diag.py`**, en el dict de retorno de `health()` (ancla: línea
`"shell_v2_enabled"`, `diag.py:411`), agregar DEBAJO, aditivo puro:

```python
        "ui_peek_enabled": bool(getattr(_config.config, "STACKY_UI_PEEK_ENABLED", True)),  # Plan 175
        "ui_context_menu_enabled": bool(getattr(_config.config, "STACKY_UI_CONTEXT_MENU_ENABLED", True)),  # Plan 175
```

**Paso 5 — `tests/test_harness_flags.py`:** agregar las 2 keys al set `_CURATED_DEFAULTS_ON`
(`:467`), con comentario `# Plan 175`. **Paso 6 — `scripts/run_harness_tests.sh`:** alta de
`"tests/test_ui_cockpit_flags.py"` en `HARNESS_TEST_FILES`.

**Paso 7 — TESTS PRIMERO (frontend), `frontend/src/services/uiCockpitFlags.test.ts`:**

| Test | Qué afirma |
|---|---|
| `parse con payload completo` | `parseUiCockpitFlags({ui_peek_enabled:true, ui_context_menu_enabled:true})` → `{peek:true, contextMenu:true}`. |
| `parse con payload parcial` | `parseUiCockpitFlags({ui_peek_enabled:true})` → `{peek:true, contextMenu:false}`. |
| `parse tolera null/undefined/basura` | `parseUiCockpitFlags(null)`, `(undefined)`, `("x")`, `({ui_peek_enabled:"true"})` → `{peek:false, contextMenu:false}` (fail-closed: sin health, UI idéntica a hoy). |

**Paso 8 — implementación frontend:**

```ts
// frontend/src/services/uiCockpitFlags.ts  (PURO)
export interface UiCockpitFlags { peek: boolean; contextMenu: boolean }
export function parseUiCockpitFlags(data: unknown): UiCockpitFlags {
  const d = (typeof data === "object" && data !== null ? data : {}) as Record<string, unknown>;
  return {
    peek: d["ui_peek_enabled"] === true,
    contextMenu: d["ui_context_menu_enabled"] === true,
  };
}
```

```ts
// frontend/src/hooks/useUiFlags.ts  (mecanismo del plan 139: leer /api/diag/health,
// mismo endpoint que App.tsx:152-163; aca via react-query para dedupe de requests)
import { useQuery } from "@tanstack/react-query";
import { parseUiCockpitFlags, type UiCockpitFlags } from "../services/uiCockpitFlags";

export function useUiFlags(): UiCockpitFlags {
  const q = useQuery({
    queryKey: ["diag-health-ui-cockpit"],
    queryFn: async () => (await fetch("/api/diag/health")).json(),
    staleTime: 5 * 60_000,
    retry: false,
  });
  return parseUiCockpitFlags(q.data);
}
```

**Configurable desde la UI de Settings (regla dura del pipeline):** el alta en `FLAG_REGISTRY`
con `group="global"` hace que ambas flags aparezcan AUTOMÁTICAMENTE en el panel de flags de
Settings (panel registry-driven de los planes 82/86; categoría "interfaz_ui" ya renderizada). No
hay trabajo de UI adicional: el toggle del operador persiste y `health()` refleja el nuevo valor
al recargar la página (mismo modelo que el shell v2: sin re-montaje en caliente,
`App.tsx:152-153`).

**Criterio de aceptación BINARIO:** KPI-8, KPI-9, KPI-10 y KPI-1 verdes (comandos en §1); además
`venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q` exit 0.

**Flags:** `STACKY_UI_PEEK_ENABLED`, `STACKY_UI_CONTEXT_MENU_ENABLED` (ambas default ON).
**Runtimes:** feature de dashboard, agnóstica del runtime de agentes (Codex CLI / Claude Code CLI
/ Copilot); paridad por construcción, sin fallback por runtime.
**Trabajo del operador: ninguno.**

---

### F1 — Registro tipado de acciones por entidad + gateway de confirmación + deep-links

**Objetivo (1 frase):** crear el registro PURO de acciones por `kind` (extendiendo `CommandKind`
del plan 129) con el invariante estructural "acción rápida ⇒ acción segura", el gateway único de
confirmación (punto de integración con el 164) y los builders puros de deep-links (punto de
integración con el 165). **Valor:** una sola fuente de verdad de acciones que consumen el menú
contextual (F3) y las acciones inline (F4); imposible por construcción que una acción con efecto
quede sin confirmación.

**Archivos:**
- NUEVO `frontend/src/services/peekLinks.ts` + NUEVO `frontend/src/services/peekLinks.test.ts`
- NUEVO `frontend/src/services/confirmGateway.ts` (solo tipos + implementación v1 trivial; la
  máquina de armado vive en F3)
- NUEVO `frontend/src/services/clipboard.ts` (wrapper fino, sin test — sin lógica)
- NUEVO `frontend/src/services/entityActions.ts` + NUEVO `frontend/src/services/entityActions.test.ts`

**Paso 1 — TESTS PRIMERO, `peekLinks.test.ts`:**

| Test | Qué afirma |
|---|---|
| `executionDeepLink delega en serializeRoute (clave canónica ?exec=)` | `executionDeepLink(42, "http://localhost:5173")` → `"http://localhost:5173/history?exec=42"` (clave canónica de `serializeRoute`, `routes.ts:95`; NO el alias legacy `?execution=`). |
| `ticketExternalLink prefiere ado_url del backend` | con `{ado_url:"https://x/wi/9", ado_id:9}` → `"https://x/wi/9"`. |
| `ticketExternalLink fallback a adoUrl por ado_id` | con `{ado_id: 9}` (sin ado_url) → el string que devuelve `adoUrl("9")` de `utils/trackerUrls.ts`. |
| `ticketExternalLink sin datos` | con `{ado_id: 0}` → `null`. |

**Paso 2 — `peekLinks.ts`:**

```ts
// Plan 175 F1 — deep-links puros. C1: el plan 165 YA está implementado
// (frontend/src/services/routes.ts). Este modulo DELEGA en su builder canonico
// serializeRoute (clave canonica ?exec=), NO reinventa ni usa el alias legacy
// ?execution=. Reuso, no reinvencion (guardarrail §3.5).
import { adoUrl } from "../utils/trackerUrls";
import { serializeRoute } from "./routes";

export function executionDeepLink(id: number, origin: string): string {
  // serializeRoute -> "/history?exec=<id>" (routes.ts:95). OJO: RouteState.query
  // es OBLIGATORIO (routes.ts:19-24) — pasar `query: {}` o tsc rompe.
  return `${origin}${serializeRoute({ tab: "history", exec: id, query: {} })}`;
}

export function ticketExternalLink(t: { ado_url?: string; ado_id: number }): string | null {
  if (t.ado_url) return t.ado_url;
  if (t.ado_id > 0) return adoUrl(String(t.ado_id));
  return null;
}
```

**Paso 3 — `confirmGateway.ts`** (punto ÚNICO de migración al 164):

```ts
// Plan 175 F1 — gateway de confirmacion. HITL innegociable: toda accion con
// efecto pasa por aca. v1 (plan 164 aun no implementado): la confirmacion la
// resuelve el menu contextual con armado de dos pasos (F3, armTransition).
// v2 (cuando el 164 aterrice): reemplazar SOLO este modulo para delegar en
// useConfirm() del DialogHost (contrato 164 §F0). PROHIBIDO usar los dialogos
// nativos del navegador en cualquier version.
export interface ConfirmRequest {
  title: string;
  message: string;
  confirmLabel: string;
  tone: "default" | "danger";
}
export type ConfirmFn = (req: ConfirmRequest) => Promise<boolean>;
```

**Paso 4 — `clipboard.ts` (C2 — colisión con plan 194):** este módulo es el ÚNICO punto de copiado
de 175. **Regla dura:** si el plan 194 ya está mergeado (existe `frontend/src/services/copyService.ts`),
`copyText` debe **delegar en `copyService`** — NO reimplementar el copiado ni llamar
`navigator.clipboard.writeText` directo (el plan 194 introduce un **ratchet `writeText`** que
prohíbe nuevas llamadas crudas; una llamada directa nueva rompería ese trinquete). En el estado
actual de este árbol `copyService.ts` NO existe (vive en la rama `impl/ux`), así que el wrapper
local de abajo es el fallback declarado; cuando 194 aterrice se reemplaza SOLO el cuerpo por
`return copyService.copy(text)`. Pre-flight del implementador: `ls frontend/src/services/copyService.ts`
— si existe, delegar; si no, usar el wrapper local:

```ts
// FALLBACK LOCAL (solo si copyService del plan 194 aun no esta mergeado).
// Cuando 194 aterrice: reemplazar el cuerpo por `return copyService.copy(text)`.
export async function copyText(text: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(text); return true; } catch { /* sigue */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy"); ta.remove(); return ok;
  } catch { return false; }
}
```

**Paso 5 — TESTS PRIMERO, `entityActions.test.ts`** (casos EXACTOS):

| Test | Qué afirma |
|---|---|
| `execution running incluye cancelar y excluye borrar/publicar` | `actionsForExecution({...status:"running"...}, origin)` contiene id `"exec-cancel"` con `effect:"confirm"`; NO contiene `"exec-delete"` ni `"exec-publish"`. |
| `execution completed incluye publicar y borrar, excluye cancelar` | con `status:"completed"`: contiene `"exec-publish"` y `"exec-delete"` (ambas `effect:"confirm"`); no contiene `"exec-cancel"`. |
| `execution siempre ofrece abrir y copiar link` | para todo status: contiene `"exec-open"` y `"exec-copy-link"`, ambas `effect:"safe"`, ambas `quick:true`. |
| `ticket con ado_url ofrece abrir/copiar ADO` | `actionsForTicket({...ado_url:"https://x"...})` contiene `"ticket-open-ado"` y `"ticket-copy-ado-link"` (`effect:"safe"`, `quick:true`) y `"ticket-copy-ref"` (`quick:false`). |
| `ticket sin link externo no ofrece abrir ADO` | con `ado_id:0` y sin `ado_url`: no contiene `"ticket-open-ado"` ni `"ticket-copy-ado-link"`. |
| `INVARIANTE quick ⇒ safe` | para una matriz de entidades (running/completed/error × ticket con/sin ado_url): `quickActions(actionsFor*(...))` devuelve SOLO acciones con `effect === "safe"`; y NINGUNA acción con `effect === "confirm"` tiene `quick === true` en el catálogo completo. |
| `toda accion con efecto pide confirmacion antes de llamar la API` | con un `ctx` fake donde `askConfirm` resuelve `false`: `run()` de `"exec-delete"`/`"exec-cancel"`/`"exec-publish"` NO invoca `ctx.api.*` (spies llamados 0 veces). Con `askConfirm` → `true`: el spy correspondiente se llama exactamente 1 vez. |

**Paso 6 — `entityActions.ts`:**

```ts
import type { CommandKind } from "../components/commandPaletteData";
import type { ExecutionHistoryItem } from "../api/endpoints";
import type { Ticket } from "../types";
import { executionDeepLink, ticketExternalLink } from "./peekLinks";
import { serializeRoute } from "./routes";  // C1: builder canonico de URL (plan 165)
import type { ConfirmFn } from "./confirmGateway";

/** Reusa el vocabulario de la paleta (plan 129) en vez de inventar otro enum. */
export type EntityKind = Extract<CommandKind, "execution" | "ticket">;

export interface EntityActionContext {
  copyText: (text: string) => Promise<boolean>;
  openExternal: (url: string) => void;              // window.open(url, "_blank") en runtime real
  openDetail?: (id: number) => void;                // la pagina lo mapea a su drawer/expand local
  navigate: (path: string) => void;
  askConfirm: ConfirmFn;                            // HITL: gateway de confirmacion (F1 paso 3)
  api: {
    cancelExecution: (id: number) => Promise<unknown>;   // Executions.cancel  (endpoints.ts)
    deleteExecution: (id: number) => Promise<unknown>;   // Executions.deleteOne
    publishExecution: (id: number) => Promise<unknown>;  // Executions.publish
  };
  onDone?: (actionId: string, ok: boolean) => void;
}

export interface EntityAction {
  id: string;               // estable, kebab-case, prefijado por entidad
  label: string;
  icon: string;             // emoji, como la paleta (commandPaletteData.ts DEEP_ICONS)
  effect: "safe" | "confirm";
  quick: boolean;           // candidata a accion rapida inline (SOLO safe puede ser quick)
  run: (ctx: EntityActionContext) => Promise<void>;
}

export function quickActions(actions: EntityAction[]): EntityAction[] {
  // Doble cerrojo: filtra quick Y safe (el invariante ademas se testea).
  return actions.filter((a) => a.quick && a.effect === "safe");
}

export function actionsForExecution(item: ExecutionHistoryItem, origin: string): EntityAction[] {
  const out: EntityAction[] = [
    { id: "exec-open", label: "Abrir detalle", icon: "👁", effect: "safe", quick: true,
      run: async (ctx) => { if (ctx.openDetail) ctx.openDetail(item.id); else ctx.navigate(serializeRoute({ tab: "history", exec: item.id, query: {} })); } },  // C1: clave canonica ?exec= (query:{} obligatorio)
    { id: "exec-copy-link", label: "Copiar link", icon: "🔗", effect: "safe", quick: true,
      run: async (ctx) => { const ok = await ctx.copyText(executionDeepLink(item.id, window.location.origin)); ctx.onDone?.("exec-copy-link", ok); } },
    { id: "exec-copy-id", label: `Copiar id #${item.id}`, icon: "🆔", effect: "safe", quick: false,
      run: async (ctx) => { const ok = await ctx.copyText(String(item.id)); ctx.onDone?.("exec-copy-id", ok); } },
  ];
  if (item.status === "running") {
    out.push({ id: "exec-cancel", label: "Cancelar run…", icon: "⛔", effect: "confirm", quick: false,
      run: async (ctx) => {
        const ok = await ctx.askConfirm({ title: "Cancelar run", message: `Cancelar la ejecución #${item.id} en curso.`, confirmLabel: "Cancelar run", tone: "danger" });
        if (!ok) return;
        await ctx.api.cancelExecution(item.id); ctx.onDone?.("exec-cancel", true);
      } });
  } else {
    if (item.status === "completed") {
      out.push({ id: "exec-publish", label: "Publicar a ADO…", icon: "📤", effect: "confirm", quick: false,
        run: async (ctx) => {
          const ok = await ctx.askConfirm({ title: "Publicar a ADO", message: `Publicar el resultado de la ejecución #${item.id} como comentario en ADO.`, confirmLabel: "Publicar", tone: "default" });
          if (!ok) return;
          await ctx.api.publishExecution(item.id); ctx.onDone?.("exec-publish", true);
        } });
    }
    out.push({ id: "exec-delete", label: "Borrar ejecución…", icon: "🗑", effect: "confirm", quick: false,
      run: async (ctx) => {
        const ok = await ctx.askConfirm({ title: "Borrar ejecución", message: `Borrar la ejecución #${item.id}. Esta acción no se puede deshacer.`, confirmLabel: "Borrar", tone: "danger" });
        if (!ok) return;
        await ctx.api.deleteExecution(item.id); ctx.onDone?.("exec-delete", true);
      } });
  }
  return out;
}

export function actionsForTicket(t: Ticket): EntityAction[] {
  const out: EntityAction[] = [];
  const ext = ticketExternalLink(t);
  if (ext) {
    out.push({ id: "ticket-open-ado", label: "Abrir en ADO", icon: "↗", effect: "safe", quick: true,
      run: async (ctx) => ctx.openExternal(ext) });
    out.push({ id: "ticket-copy-ado-link", label: "Copiar link ADO", icon: "🔗", effect: "safe", quick: true,
      run: async (ctx) => { const ok = await ctx.copyText(ext); ctx.onDone?.("ticket-copy-ado-link", ok); } });
  }
  out.push({ id: "ticket-copy-ref", label: `Copiar ref ADO-${t.ado_id}`, icon: "🆔", effect: "safe", quick: false,
    run: async (ctx) => { const ok = await ctx.copyText(`ADO-${t.ado_id} — ${t.title}`); ctx.onDone?.("ticket-copy-ref", ok); } });
  return out;
}
```

**Casos borde codificados:** ticket sin `ado_url` y `ado_id<=0` (no hay acciones externas);
ejecución `running` (sin borrar/publicar: el backend lo rechazaría — no se ofrece lo que no se
puede); `askConfirm` que resuelve `false` corta ANTES de tocar la API (test con spies).

**Nota de nombres (gate del 164):** el campo se llama `askConfirm` y las variables locales
`ask`/`askConfirm` — NUNCA el identificador nativo en minúsculas (regla §3.7d).

**Criterio de aceptación BINARIO:** KPI-2 y KPI-3 verdes; `npx tsc --noEmit` exit 0.

**Flag:** N/A directo (módulos puros sin consumo aún; el consumo queda detrás de
`STACKY_UI_PEEK_ENABLED` / `STACKY_UI_CONTEXT_MENU_ENABLED` en F2-F4).
**Runtimes:** dashboard puro, agnóstico del runtime de agentes; los 3 endpoints consumidos ya son
runtime-agnósticos. Paridad por construcción.
**Trabajo del operador: ninguno.**

---

### F2 — PeekCard: tarjeta flotante al hover sostenido (ejecución y ticket)

**Objetivo (1 frase):** crear el componente reutilizable `PeekCard` con su máquina de estados PURA
(hover ≥400 ms abre; salir cierra con tolerancia de 150 ms; Escape cierra sin robar foco) y
cablearlo en las filas del Historial y las cards del tablero de Tickets. **Valor:** inspeccionar N
entidades pasa de N aperturas de drawer a deslizar el mouse; cero fetch en el camino feliz.

**Archivos:**
- NUEVO `frontend/src/services/peekModel.ts` (reducer + builders PUROS)
- NUEVO `frontend/src/services/peekModel.test.ts`
- NUEVO `frontend/src/components/peek/PeekCard.tsx`
- NUEVO `frontend/src/components/peek/PeekCard.module.css`
- MODIFICADO `frontend/src/pages/ExecutionHistoryPage.tsx` (wiring en `<tr>`, ancla:
  `className={styles.row}` en `:186`)
- MODIFICADO `frontend/src/pages/TicketBoard.tsx` (wiring en el header de `TicketCard`, ancla:
  `styles.cardHeader` en `:422`)
- MODIFICADO `frontend/src/pages/ExecutionHistoryPage.module.css` y el module css del TicketBoard
  SOLO si necesitan la clase contenedora `position: relative` (tokens, sin hex).

**Paso 1 — TESTS PRIMERO, `peekModel.test.ts`:**

| Test | Qué afirma |
|---|---|
| `idle + hover-start → arming` | target queda seteado; `phase === "arming"`. |
| `arming + hover-end → idle` | mover el mouse antes de 400 ms nunca abre. |
| `arming + open-timer → open` | el timer solo abre desde arming (desde idle es no-op). |
| `open + hover-end → closing; closing + close-timer → idle` | cierre en dos tiempos. |
| `closing + card-hover → open` | entrar a la tarjeta cancela el cierre (se puede leer/copiar de la card). |
| `open + hover-start(otro target) → arming(nuevo)` | pasar a otra fila re-arma para la nueva entidad. |
| `escape/force-close → idle desde cualquier fase` | tabla de 4 fases × 2 eventos. |
| `constantes congeladas` | `PEEK_OPEN_DELAY_MS === 400` y `PEEK_CLOSE_DELAY_MS === 150`. |
| `buildExecutionPeek formatea SOLO via format.ts` | con un item fixture (`duration_ms: 65000, cost_usd: 0.005, tokens_in: 1500, tokens_out: 250, produced_files_count: 3`): los values contienen exactamente `formatDuration(65000)` (= `"1m 5s"`), `formatCostUsd(0.005)` (= `"$0.0050"`), `formatTokens(1500)` (= `"1.5k"`), `formatInt(3)` (= `"3"`). |
| `buildExecutionPeek con nulls` | `duration_ms: null, cost_usd: null` → values `"—"` (contrato format.ts); `error_message` largo se trunca a 120 chars + `"…"`. |
| `buildTicketPeek campos` | con fixture Ticket completo: título `ADO-<ado_id> — <title>` (title truncado a 80); fields incluyen Tipo, Estado ADO, Estado Stacky, Asignado, `formatRelativeTime(last_synced_at)`; con `pipeline_summary` presente: `"<done_stages.length> etapas · próx: <next_suggested>"`; sin él, el field Pipeline no aparece. |

**Paso 2 — `peekModel.ts`:**

```ts
import { formatDateTime, formatDuration, formatCostUsd, formatTokens, formatInt, formatRelativeTime } from "./format";
import type { ExecutionHistoryItem } from "../api/endpoints";
import type { Ticket } from "../types";
import type { EntityKind } from "./entityActions";

export const PEEK_OPEN_DELAY_MS = 400;
export const PEEK_CLOSE_DELAY_MS = 150;

export type PeekTarget = { kind: EntityKind; id: number };
export type PeekPhase = "idle" | "arming" | "open" | "closing";
export interface PeekState { phase: PeekPhase; target: PeekTarget | null }
export type PeekEvent =
  | { type: "hover-start"; target: PeekTarget }
  | { type: "open-timer" }
  | { type: "hover-end" }
  | { type: "card-hover" }
  | { type: "close-timer" }
  | { type: "escape" }
  | { type: "force-close" };

export const PEEK_IDLE: PeekState = { phase: "idle", target: null };

export function peekReducer(s: PeekState, e: PeekEvent): PeekState {
  switch (e.type) {
    case "hover-start": return { phase: "arming", target: e.target };
    case "open-timer": return s.phase === "arming" ? { ...s, phase: "open" } : s;
    case "hover-end":
      if (s.phase === "arming") return PEEK_IDLE;
      if (s.phase === "open") return { ...s, phase: "closing" };
      return s;
    case "card-hover": return s.phase === "closing" ? { ...s, phase: "open" } : s;
    case "close-timer": return s.phase === "closing" ? PEEK_IDLE : s;
    case "escape":
    case "force-close": return PEEK_IDLE;
  }
}

export interface PeekField { label: string; value: string; mono?: boolean }
export interface PeekContent { title: string; fields: PeekField[] }

export function buildExecutionPeek(it: ExecutionHistoryItem): PeekContent { /* campos EXACTOS: Estado (it.status), Inicio formatDateTime(it.started_at), Duración formatDuration(it.duration_ms), Costo formatCostUsd(it.cost_usd), Tokens `${formatTokens(it.tokens_in)} in · ${formatTokens(it.tokens_out)} out`, Runtime it.runtime ?? "—" (mono), Modelo it.model ?? "—" (mono), Archivos formatInt(it.produced_files_count), Ticket it.ticket_title ?? `#${it.ticket_id}`; si it.error_message: field Error truncado a 120. Título: `Ejecución #${it.id} — ${it.agent_name ?? it.agent_type}` */ }

export function buildTicketPeek(t: Ticket): PeekContent { /* título `ADO-${t.ado_id} — ${title80}`; fields: Tipo (work_item_type ?? "—"), Estado ADO (ado_state ?? "—"), Estado Stacky (stacky_status ?? "—"), Prioridad (t.priority != null ? formatInt(t.priority) : "—"), Asignado (assigned_to_ado ?? "—"), Sync formatRelativeTime(t.last_synced_at), y si t.pipeline_summary: Pipeline `${done_stages.length} etapas · próx: ${next_suggested ?? "—"}` */ }
```

(El implementador materializa los cuerpos comentados EXACTAMENTE como se describen; los tests del
Paso 1 los fijan.)

**Paso 3 — `PeekCard.tsx`** (cáscara fina; el ÚNICO lugar con DOM):
- Props: `{ state: PeekState; content: PeekContent | null; anchorRect: DOMRect | null; loading?: boolean; onCardHover: () => void; onCardLeave: () => void }`.
- Render `null` salvo `state.phase === "open" || "closing"`.
- Portal a `document.body` (patrón `createPortal` ya usado en el repo).
- **Posicionamiento SIN inline-style:** `ref` + `useLayoutEffect` que setea
  `el.style.left/top` imperativamente a partir de `anchorRect` (debajo de la fila; si no entra en
  el viewport, arriba — reusar `clampMenuPosition` de F3 cuando exista; hasta F3, clamp local
  equivalente). PROHIBIDO `style={{}}` (uiDebtRatchet).
- `role="tooltip"` + `aria-hidden={false}`; la card **NUNCA toma foco** (no roba foco por diseño);
  `onMouseEnter={onCardHover}` / `onMouseLeave={onCardLeave}` para la tolerancia de cierre.
- `PeekCard.module.css`: tokens de `theme.css` para colores/sombra; transición de entrada con los
  tokens de motion del plan 143 (`transition: opacity var(--duration-fast) ...`); sin hex, sin ms
  literales.
- Si `loading` (enriquecimiento sin cache): render `<Spinner size="sm">` del barrel `ui` junto a
  los fields ya disponibles.

**Paso 4 — hook de wiring `usePeek()`** (dentro de `PeekCard.tsx` o
`frontend/src/components/peek/usePeek.ts`, a criterio del implementador PERO exportado): maneja
`useReducer(peekReducer, PEEK_IDLE)`, los dos timers (`setTimeout` de `PEEK_OPEN_DELAY_MS` al
despachar `hover-start`, y de `PEEK_CLOSE_DELAY_MS` al despachar `hover-end` en open; limpiar
timers en cleanup), el listener de `keydown` a nivel `document` **agregado SOLO mientras
`phase !== "idle"`** que ante `Escape` despacha `escape` y hace `stopPropagation()` (para no
cerrar drawers/paleta de rebote) pero **jamás mueve el foco**. Devuelve
`{ state, rowProps(target, rect): {onMouseEnter, onMouseLeave}, cardProps }`.

**Paso 5 — datos del peek (contrato con 174):**
- **Camino feliz (sin fetch):** en Historial, `content = buildExecutionPeek(item)` con el item de
  la fila (ya en memoria vía la query `["execution-history", ...]`,
  `ExecutionHistoryPage.tsx:67-80`). En Tickets, `content = buildTicketPeek(ticket)` con el
  ticket de la card.
- **Enriquecimiento (opcional, solo ticket):** ejecuciones del ticket vía
  `queryClient.getQueryData(["ticket-detail", t.id])`; si `undefined` (cache frío = plan 174
  ausente), `queryClient.fetchQuery({ queryKey: ["ticket-detail", t.id], queryFn: () => Tickets.byId(t.id), staleTime: 30_000 })`
  con `loading=true` mientras tanto (**degradación explícita: fetch on-demand con spinner
  chico**). Al llegar, agregar field `Ejecuciones: formatInt(executions.length)` + último estado.
- queryKeys CONGELADAS (§4): `["execution-detail", id]`, `["ticket-detail", id]`.

**Paso 6 — wiring gated por flag:** en ambas páginas, `const { peek } = useUiFlags();` y los
handlers de hover se pasan SOLO si `peek === true` (`{...(peek ? rowProps(...) : {})}`); con OFF
no se agrega ni un listener (byte-idéntico a hoy).

**Dependencia blanda 172 (peek por teclado):** el hook expone además
`rowKeyProps: { onKeyDown }` que ante tecla `p` (sin modificadores, fuera de inputs) despacha
`hover-start` + `open-timer` inmediato (peek fijado). Se cablea en la fila; queda inerte hasta que
el 172 haga las filas enfocables (§4). Sin 172: peek solo por hover — declarado.

**Criterio de aceptación BINARIO:** KPI-4 verde; `npx tsc --noEmit` exit 0;
`grep -c "style={{" src/components/peek/PeekCard.tsx` → `0`.

**Flag:** `STACKY_UI_PEEK_ENABLED` (default ON). **Runtimes:** dashboard puro, agnóstico del
runtime de agentes; los datos del peek salen de endpoints de lectura existentes. Paridad por
construcción. **Trabajo del operador: ninguno** (hover natural; sin hover, nada cambia).

---

### F3 — Menú contextual clic-derecho unificado (UN componente, accesible por teclado)

**Objetivo (1 frase):** crear el componente ÚNICO `ContextMenu` (posicionado sin inline-style,
navegable por teclado, cierre con Escape sin robar foco) que renderiza las acciones del registro
de F1 para la entidad bajo el cursor, con confirmación de dos pasos en línea para las acciones con
efecto (v1 pre-164). **Valor:** las acciones frecuentes quedan a un clic-derecho, con HITL
intacto y sin diálogos nativos.

**Archivos:**
- NUEVO `frontend/src/services/contextMenuModel.ts` + NUEVO `frontend/src/services/contextMenuModel.test.ts`
- NUEVO `frontend/src/components/contextmenu/ContextMenu.tsx`
- NUEVO `frontend/src/components/contextmenu/ContextMenu.module.css`
- NUEVO `frontend/src/components/contextmenu/useEntityContextMenu.ts` (hook de instanciación por página)
- MODIFICADO `frontend/src/pages/ExecutionHistoryPage.tsx` (onContextMenu + onKeyDown en `<tr>`)
- MODIFICADO `frontend/src/pages/TicketBoard.tsx` (ídem en la card, ancla `styles.card` en `:401`)

**Paso 1 — TESTS PRIMERO, `contextMenuModel.test.ts`:**

| Test | Qué afirma |
|---|---|
| `clamp: entra tal cual` | `clampMenuPosition(100, 100, 200, 150, 1920, 1080)` → `{left:100, top:100}`. |
| `clamp: desborda derecha → flip` | `clampMenuPosition(1900, 100, 200, 150, 1920, 1080)` → `left === 1700` (x − menuW). |
| `clamp: desborda abajo → flip` | `clampMenuPosition(100, 1050, 200, 150, 1920, 1080)` → `top === 900`. |
| `clamp: viewport enano → margen mínimo 8` | nunca devuelve left/top < 8. |
| `teclado: ArrowDown/ArrowUp con wrap` | `menuKeydown("ArrowDown", 2, 3)` → `{kind:"move", index:0}`; `("ArrowUp", 0, 3)` → `{kind:"move", index:2}`. |
| `teclado: Home/End/Enter/Espacio/Escape` | Home→0, End→count−1, Enter y `" "`→select, Escape→close, otra tecla→none. |
| `teclado: menú vacío` | con `count === 0`: solo Escape cierra, el resto es none. |
| `armado: safe dispara directo` | `armTransition({armedId:null}, {type:"activate", id:"a", effect:"safe"})` → `{state:{armedId:null}, fire:"a"}`. |
| `armado: confirm requiere dos pasos` | primer activate de `"d"` (confirm) → `{armedId:"d", fire:null}`; segundo activate de `"d"` → `{armedId:null, fire:"d"}`. |
| `armado: activar otro item re-arma` | armado `"d"`, activate `"x"` (confirm) → `{armedId:"x", fire:null}`. |
| `armado: escape/close desarman sin disparar` | armado `"d"`, `{type:"escape"}` → `{armedId:null, fire:null}`; ídem `close`. |

**Paso 2 — `contextMenuModel.ts`:**

```ts
export interface MenuPosition { left: number; top: number }
export function clampMenuPosition(x: number, y: number, menuW: number, menuH: number, vw: number, vh: number, margin = 8): MenuPosition {
  let left = x, top = y;
  if (x + menuW > vw - margin) left = x - menuW;
  if (y + menuH > vh - margin) top = y - menuH;
  return { left: Math.max(margin, left), top: Math.max(margin, top) };
}

export type MenuKeyResult = { kind: "move"; index: number } | { kind: "select" } | { kind: "close" } | { kind: "none" };
export function menuKeydown(key: string, index: number, count: number): MenuKeyResult { /* segun tabla de tests */ }

export interface ArmState { armedId: string | null }
export type ArmEvent = { type: "activate"; id: string; effect: "safe" | "confirm" } | { type: "escape" } | { type: "close" };
export function armTransition(s: ArmState, e: ArmEvent): { state: ArmState; fire: string | null } { /* segun tabla de tests */ }
```

**Paso 3 — `ContextMenu.tsx` (el componente ÚNICO):**
- Props: `{ open: boolean; x: number; y: number; actions: EntityAction[]; ctx: EntityActionContext; openedByKeyboard: boolean; onClose: () => void }`.
- Portal a `document.body`. Render condicional (`null` si `!open`).
- **Posicionamiento SIN inline-style:** `ref` + `useLayoutEffect`: medir
  `ref.current.getBoundingClientRect()`, calcular `clampMenuPosition(x, y, w, h, innerWidth, innerHeight)` y asignar `el.style.left/top` imperativamente.
- Semántica: contenedor `role="menu"` con `aria-label="Acciones"`; cada ítem `role="menuitem"`,
  `tabIndex={-1}`; ítem activo trackeado por índice en estado + clase de módulo `.active`.
- **Foco:** si `openedByKeyboard`, al montar foco al contenedor con
  `focus({ preventScroll: true })` e índice 0 activo; si se abrió por mouse, foco al contenedor
  igualmente (para capturar el teclado) pero SIN marcar ítem activo hasta la primera flecha. Al
  cerrar: si `openedByKeyboard`, devolver el foco al elemento capturado al abrir
  (`openerEl = document.activeElement` guardado por el hook); si fue por mouse, **no enfocar nada**
  (cerrar con Escape no roba el foco — requisito textual).
- **Teclado:** `onKeyDown` del contenedor delega en `menuKeydown`; `select` ejecuta
  `armTransition` sobre el ítem activo; `close` cierra (+ restore-focus según regla anterior).
  `stopPropagation()` SIEMPRE que el menú esté abierto (que Escape no cierre además el drawer).
- **Confirmación v1 (HITL, dependencia blanda 164):** ítems `effect:"confirm"` pasan por
  `armTransition`: armado ⇒ el label muta a `¿${label.replace("…","")}? Clic de nuevo` con clase
  `.danger` (tokens de color de peligro del tema). `fire` ⇒ `action.run(ctx)` con un
  `ctx.askConfirm` que resuelve `true` (la confirmación YA ocurrió en el menú — el gateway se
  satisface; cuando el 164 aterrice, `askConfirm` pasa a abrir el `ConfirmDialog` canónico y el
  armado in-menu se elimina, cambio acotado a `confirmGateway.ts` + este componente).
- **Cierre por click-afuera:** listener `pointerdown` en `document` mientras open (en cleanup se
  remueve); click dentro no cierra (el menú maneja sus ítems).
- CSS module con tokens (`--color-*`, sombra, `var(--duration-fast)` del 143); sin hex, sin ms
  literales, sin `style={{}}`.

**Paso 4 — `useEntityContextMenu.ts` (hook por página; el componente sigue siendo UNO):**

```ts
// Devuelve { menuElement, openFromMouse(e, actions, ctx), openFromKeyboard(el, actions, ctx) }.
// openFromMouse: e.preventDefault(); guarda {x: e.clientX, y: e.clientY, openedByKeyboard: false}.
// openFromKeyboard: usa el.getBoundingClientRect() → {x: rect.left + 8, y: rect.bottom - 4, openedByKeyboard: true}.
```

**Paso 5 — wiring (gated por flag):** `const { contextMenu } = useUiFlags();` En ambas superficies,
además de `onContextMenu`/`onKeyDown`, agregar `tabIndex={contextMenu ? 0 : undefined}` en la
`<tr>`/card ([ADICIÓN ARQUITECTO] C3: enfocabilidad standalone, sin esperar al 172).
- `ExecutionHistoryPage.tsx`, en el `<tr>` (ancla `styles.row`):
  `onContextMenu={contextMenu ? (e) => openFromMouse(e, actionsForExecution(item, window.location.origin), ctx) : undefined}` y
  `onKeyDown={contextMenu ? (e) => { if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) { e.preventDefault(); openFromKeyboard(e.currentTarget, ...); } } : undefined}`.
  El `ctx` de la página mapea: `openDetail: setDetailId`, `navigate` (router), `copyText`
  (clipboard.ts), `openExternal: (u) => window.open(u, "_blank", "noopener")`, `api` con
  `Executions.cancel/deleteOne/publish`, y `onDone` que invalida la query
  `["execution-history", ...]` tras cancel/delete/publish (refresco inmediato de la tabla).
- `TicketBoard.tsx`, en el `<div className={styles.card}>` (ancla `:401`): ídem con
  `actionsForTicket(ticket)`.
- Flag OFF ⇒ `onContextMenu` es `undefined` ⇒ **menú nativo del navegador, como hoy** (binario).

**[ADICIÓN ARQUITECTO] — Accesibilidad por teclado STANDALONE (C3).** v1 dejaba el camino de
teclado **inerte sin el 172** (filas no enfocables ⇒ `onKeyDown` nunca recibía foco), lo que
incumple el requisito "menú 100% accesible por teclado". Fix: **175 pone su propio `tabIndex={0}`**
en la `<tr>`/card cableada, **gated por `STACKY_UI_CONTEXT_MENU_ENABLED`** (`tabIndex={contextMenu ? 0 : undefined}`),
más `role` y `aria-label` mínimos. Así, con la flag ON:
- El operador tabula hasta la fila y abre el menú con `Shift+F10` / tecla `ContextMenu` **sin
  esperar al 172** (menú navegable por flechas, cierre con Escape sin robar foco — ya en F3 Paso 3).
- La tecla `p` para fijar el peek (F2) también funciona, porque la fila ya es enfocable.
- Las acciones rápidas inline quedan alcanzables vía `:focus-within` (F4).
Esto **no colisiona con el 172**: cuando 172 aterrice, promueve estas filas de `tabIndex={0}`
estático a **foco roving** (`tabIndex` gestionado por el roving group) y agrega j/k — un cambio de
1 línea por página, sin tocar los handlers de 175. Contrato congelado acá: 175 aporta enfocabilidad
básica; 172 aporta roving + alta de combos en el registro central + overlay "?". Con la flag OFF no
se agrega `tabIndex` (byte-idéntico a hoy). **Sin trabajo del operador; HITL intacto; los 3 runtimes
no se tocan.**

**Dependencia blanda 172 (declarada):** los combos `Shift+F10`/`ContextMenu` quedan cableados EN
la fila; con el `tabIndex={0}` propio de 175 (adición de arriba) el camino de teclado funciona
standalone. Cuando 172 aterrice, además debe dar de alta ambos combos en su registro central
de atajos para que aparezcan en el overlay "?" (obligación del 172, citada acá como contrato) y
promover el `tabIndex` a foco roving.

**Criterio de aceptación BINARIO:** KPI-5 verde; `npx tsc --noEmit` exit 0;
`grep -c "style={{" src/components/contextmenu/ContextMenu.tsx` → `0`; grep del contador de
diálogos nativos del plan 164 §5 F2 sobre los archivos NUEVOS de este plan → `0` apariciones.

**Flag:** `STACKY_UI_CONTEXT_MENU_ENABLED` (default ON). **Runtimes:** dashboard puro, agnóstico
del runtime de agentes; paridad por construcción (las 3 acciones con efecto llaman endpoints ya
runtime-agnósticos). **Trabajo del operador: ninguno** (el clic-derecho es opcional; sin él, nada
cambia).

---

### F4 — Acciones rápidas inline en filas (iconos al hover; SOLO acciones seguras)

**Objetivo (1 frase):** mostrar al hover de cada fila/card los iconos de las acciones `quick` del
registro (subset seguro por construcción e invariante testeado: copiar link, abrir), con feedback
visual de copiado. **Valor:** las 2 acciones más frecuentes a 1 clic sin abrir nada; imposible
que una acción con efecto aparezca inline.

**Archivos:**
- MODIFICADO `frontend/src/pages/ExecutionHistoryPage.tsx` + `ExecutionHistoryPage.module.css`
- MODIFICADO `frontend/src/pages/TicketBoard.tsx` (zona `styles.cardActions`, ancla `:437`, que ya
  hace `stopPropagation`)
- (Sin módulos nuevos: consume `quickActions()` de F1 — el invariante "quick ⇒ safe" ya quedó
  testeado en KPI-2.)

**Paso 1 — Historial:** agregar una última columna:
- `<th>` con `aria-label="Acciones rápidas"` y texto vacío (ancla: después del `<th>Ticket</th>`).
- En cada `<tr>`, último `<td className={styles.actionsCell}>` con
  `<span className={styles.rowActions} onClick={(e) => e.stopPropagation()}>` (para no abrir el
  drawer al clickear un icono) y adentro, por cada `a` de
  `quickActions(actionsForExecution(item, window.location.origin))`:
  `<IconButton size="sm" aria-label={a.label} title={a.label} onClick={() => a.run(ctx)}>{copiedId === a.id + item.id ? "✓" : a.icon}</IconButton>`
  (`IconButton` del barrel `components/ui`, plan 138).
- Feedback de copiado SIN Toast: estado local `copiedId: string | null`; `ctx.onDone` de la página
  setea `copiedId = actionId + item.id` y un `setTimeout` de 1200 ms lo limpia (icono ✓ transitorio).
- CSS module (`ExecutionHistoryPage.module.css`): `.rowActions { opacity: 0; transition: opacity var(--duration-fast) var(--ease-out, ease); }`
  y `.row:hover .rowActions, .row:focus-within .rowActions { opacity: 1; }` — tokens del 143/138,
  sin hex ni ms literales. `:focus-within` deja las acciones alcanzables por teclado cuando el 172
  haga las filas enfocables (dependencia blanda declarada).
- Gate por flag (decisión ÚNICA, sin ambigüedad — C4): las acciones rápidas inline van detrás de
  **`STACKY_UI_CONTEXT_MENU_ENABLED`** (misma familia "acciones"; NO se usa la flag del peek). Con
  la flag OFF no se agrega ni la columna ni los handlers (tabla byte-idéntica a hoy).

**Paso 2 — Tickets:** dentro de `styles.cardActions` (`TicketBoard.tsx:437`), prepend de los
IconButtons de `quickActions(actionsForTicket(ticket))` con el mismo patrón de feedback ✓. Los
botones existentes de la card no se tocan.

**Paso 3 — verificación del invariante en runtime de tipos:** el array que renderizan ambas
superficies proviene EXCLUSIVAMENTE de `quickActions(...)` (nunca del catálogo completo). Ese
helper filtra `quick && effect === "safe"` (doble cerrojo) y su test (KPI-2) fija que
cancelar/borrar/publicar jamás califican. **Las acciones con efecto solo existen en el menú
contextual (F3) y siempre detrás de confirmación — human-in-the-loop innegociable.**

**Casos borde:** ticket sin link externo ⇒ `quickActions` devuelve solo lo aplicable (puede ser
lista vacía ⇒ no se renderiza el contenedor); fila en `running` ⇒ quick actions iguales (abrir y
copiar link son seguras siempre); doble clic rápido en copiar ⇒ el `setTimeout` se resetea
(guardar el handle y limpiarlo antes de resetear).

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` exit 0; re-correr KPI-2 (el invariante
sigue verde); `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 (los archivos tocados no
suman deuda inline-style; regla del ratchet por archivo).

**Flag:** `STACKY_UI_CONTEXT_MENU_ENABLED` (default ON). **Runtimes:** dashboard puro, agnóstico
del runtime de agentes; paridad por construcción. **Trabajo del operador: ninguno.**

---

### F5 — Verificación transversal + smoke manual (cierre de la serie)

**Objetivo (1 frase):** correr TODOS los gates binarios del plan de una pasada y ejecutar el
checklist de smoke manual que valida el comportamiento DOM que los tests puros no cubren
(gap jsdom estructural). **Valor:** cero falsos verdes; el plan queda auditable por el supervisor.

**Procedimiento EXACTO (en orden):**
1. Frontend: KPI-1..KPI-5 (`npx vitest run <archivo>` uno por uno — NUNCA la suite entera),
   KPI-6 (`npx tsc --noEmit`), KPI-7 (los 2 greps de inline-style),
   `npx vitest run src/__tests__/uiDebtRatchet.test.ts`.
2. Backend: KPI-8, KPI-9, KPI-10 (comandos de §1).
3. Smoke manual (lo corre el implementador/orquestador con el dashboard levantado — NO es trabajo
   del operador):
   - Historial: hover 400 ms sobre una fila ⇒ PeekCard con Estado/Inicio/Duración/Costo/Tokens
     formateados (formato del plan 161); mover el mouse a la card ⇒ no se cierra; Escape ⇒ se
     cierra y el foco NO se mueve.
   - Historial: clic-derecho en fila ⇒ menú Stacky (no el del navegador); flechas navegan;
     "Borrar ejecución…" ⇒ primer clic arma ("¿Borrar? Clic de nuevo"), Escape desarma y cierra,
     nada se borró; segundo clic ⇒ borra y la tabla se refresca.
   - Historial (teclado standalone, C3, SIN 172): `Tab` hasta una fila (foco visible por el
     `tabIndex={0}` de 175) ⇒ `Shift+F10`/tecla `ContextMenu` abre el menú ⇒ flechas + Enter
     ejecutan ⇒ Escape cierra y **el foco vuelve a la fila** (no se pierde ni salta al body).
   - Historial (copiar link, C1): pegar en un editor ⇒ `http://<host>/history?exec=<id>` (clave
     canónica `exec`, NO `execution`); abrir esa URL ⇒ el drawer se abre (receptor `parseRoute`).
   - Historial: hover fila ⇒ iconos 🔗/👁 aparecen; 🔗 ⇒ icono ✓ 1.2 s (feedback de copiado del
     link canónico `?exec=`, ver bullet anterior).
   - Tickets: ídem peek en card, menú con "Abrir en ADO"/"Copiar link ADO", quick actions en
     `cardActions`.
   - Settings: apagar `STACKY_UI_CONTEXT_MENU_ENABLED` desde el panel de flags, recargar ⇒
     clic-derecho vuelve a ser el nativo del navegador y no hay columna de acciones; apagar
     `STACKY_UI_PEEK_ENABLED`, recargar ⇒ no hay peek. Volver a encender ambas.
   - Tema claro Y oscuro: peek y menú respetan tokens (sin colores rotos).
4. `git status` final: SOLO los archivos declarados en F0-F4 modificados/creados; nada más.

**Criterio de aceptación BINARIO:** los 10 KPIs de §1 verdes + checklist de smoke completado y
declarado punto por punto en el resumen de implementación (honesto: lo no corrido se reporta como
NO corrido).

**Flag:** ambas. **Runtimes:** N/A (verificación). **Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Colisión con sesiones paralelas / plan 164** (toca `TicketBoard.tsx` y las mismas superficies cuando se implemente). | Pre-flight `git status -- "<ruta>"` por archivo; anclas por TEXTO; el punto de contacto con 164 está aislado en `confirmGateway.ts` + el armado in-menu de F3 (migración acotada y documentada en el propio código). |
| R2 | **Peek molesto/parpadeante** para el operador. | Delay de apertura 400 ms + tolerancia de cierre 150 ms (constantes congeladas y testeadas); card `role="tooltip"` que jamás toma foco; flag `STACKY_UI_PEEK_ENABLED` apagable desde Settings en 2 clics. |
| R3 | **Perder el menú nativo del navegador** donde el operador lo quiere (copiar texto seleccionado, inspeccionar). | El `onContextMenu` se cablea SOLO en filas/cards (no global); flag OFF lo restaura al 100%; dentro de inputs/textarea no hay filas, así que el nativo sigue intacto donde más se usa. |
| R4 | **Acción destructiva a un clic de distancia** (menú acerca el peligro). | Invariante testeado "quick ⇒ safe" (doble cerrojo función + test); acciones con efecto SOLO en el menú y SIEMPRE tras confirmación (armado v1 / diálogo canónico v2); tono `danger` visual; Escape desarma. |
| R5 | **Ratchets del repo** (inline-style, anti-Intl, registro de tests, gate anti-nativos del 164). | Posicionamiento imperativo por ref (KPI-7); todo formato vía `services/format.ts` (tests lo fijan); alta en `HARNESS_TEST_FILES` (KPI-10); naming `askConfirm` y prosa perifrástica (§3.7). |
| R6 | **Deep-link se rompa si cambia el contrato de URL.** | El link se construye en UN solo módulo (`peekLinks.ts`) **delegando en `serializeRoute` del plan 165 ya implementado** (`services/routes.ts`, clave canónica `?exec=`); si 165 evoluciona el contrato, `peekLinks` lo hereda automáticamente. Test `peekLinks.test.ts` fija el resultado esperado. |
| R7 | **fetchQuery on-demand del enriquecimiento suma requests** si 174 no está. | Solo se dispara con el peek YA abierto (≥400 ms de intención), `staleTime: 30_000`, y es UN endpoint de lectura existente (`Tickets.byId`); el camino feliz (fields de la fila) no fetchea nunca. |
| R8 | **`stopPropagation` del Escape del menú/peek interfiera con paleta/drawers.** | El listener global se agrega SOLO mientras el menú/peek está abierto y se remueve al cerrar (cleanup); tests puros fijan las transiciones; smoke manual del punto 3 de F5 lo verifica con la paleta abierta. |

---

## 7. Fuera de scope (y qué hermano lo cubre)

- **Virtualización de listas largas, prefetch on-hover global, presupuesto de perf,** y cualquier
  política de cache más allá de las 2 queryKeys congeladas en §4 → **plan 174**.
- **Registro central tipado de atajos, overlay de ayuda "?", foco roving (j/k/flechas) en tablas,
  hints de atajos en tooltips/paleta** → **plan 172** (este plan solo deja handlers locales
  cableados que se activan cuando 172 haga las filas enfocables).
- **Vistas guardadas, presets de filtros, preferencias de tabla persistentes (columnas/sort/anchos),
  restauración de última vista** → **plan 173**.
- **Primitiva `Dialog`, `useConfirm`/`useAlert`, migración de modales y eliminación de los 32
  diálogos nativos existentes** → **plan 164** (este plan solo consume su contrato vía
  `confirmGateway.ts` y NO introduce ningún diálogo nativo nuevo).
- **`routes.ts` y el contrato global de URL/deep-links** → **plan 165**.
- **Peek para docs/planes/servidores**, menú contextual en árboles jerárquicos (`TicketNode`),
  acciones masivas multi-selección → fuera de la serie; candidatos a plan futuro sobre el registro
  de F1 (extensible por `EntityKind` sin tocar lo existente).

---

## 8. Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **peek / hover-card** | Tarjeta flotante de solo lectura que aparece al sostener el mouse ≥400 ms sobre una fila y resume la entidad sin navegar ni abrir el drawer. Nunca toma el foco. |
| **menú contextual** | Menú que se abre con clic-derecho (o Shift+F10/tecla Menu desde teclado) sobre una fila, con acciones específicas de esa entidad. |
| **acción rápida inline** | Icono-botón que aparece al hover de la fila para acciones seguras de 1 clic (copiar link, abrir). |
| **acción segura vs. con efecto** | Segura: no muta nada (copiar, abrir, navegar). Con efecto: muta estado o publica (cancelar, borrar, publicar a ADO) — SIEMPRE requiere confirmación (HITL). |
| **registro tipado de acciones** | Módulo puro (`entityActions.ts`) que declara, por tipo de entidad (`EntityKind`, subconjunto de `CommandKind` del plan 129), la lista de acciones con id/label/efecto/visibilidad. Menú y acciones inline lo consumen; nadie define acciones a mano en la UI. |
| **dependencia blanda** | El plan compila y funciona sin el otro plan; si el otro existe, la feature mejora sola vía un contrato congelado (queryKey, módulo gateway); si no, degrada de forma declarada. |
| **HITL (human-in-the-loop)** | El operador confirma toda acción con efecto. Innegociable: este plan jamás ejecuta algo destructivo o de publicación sin confirmación explícita. |
| **queryKey / cache react-query** | Clave del cache de datos del cliente. Si el plan 174 pre-carga `["ticket-detail", id]`, el peek la lee gratis; si no, la puebla on-demand. |
| **deep-link** | URL que abre directamente una vista/entidad (p. ej. `/history?exec=42` — clave canónica de `serializeRoute` del plan 165 — abre el drawer de esa ejecución vía `parseRoute`). |
| **ratchet / trinquete** | Test que congela un contador de deuda y falla si sube (inline-style, formateo fuera de format.ts, tests sin registrar). Solo puede bajar. |
| **flag curada** | Flag con default ON declarado: exige `default=True` en su `FlagSpec`, alta en `_CURATED_DEFAULTS_ON` (tests) y default efectivo `"true"` en `config.py`. Las tres patas o el arnés rompe. |
| **foco roving** | Patrón de teclado (plan 172) donde las filas de una tabla son enfocables y j/k/flechas mueven el foco. Este plan lo consume, no lo define. |

---

## 9. Orden de implementación

1. **F0** — flags backend + health + hook frontend (todo lo demás se cablea detrás).
2. **F1** — registro de acciones + gateway + deep-links (F3 y F4 lo consumen; F2 usa `EntityKind`).
3. **F2** — peekModel + PeekCard + wiring (independiente de F3/F4; primero porque no muta nada).
4. **F3** — contextMenuModel + ContextMenu + wiring (consume F1; trae el armado de confirmación).
5. **F4** — acciones rápidas inline (consume F1 y el patrón de wiring de F3).
6. **F5** — verificación transversal + smoke manual.

---

## 10. Definición de Hecho (DoD) global

- [ ] KPI-1..KPI-10 de §1 verdes, con los comandos EXACTOS listados (salida real leída, no
      reportada por terceros).
- [ ] `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 tras F4.
- [ ] Ambas flags visibles y toggleables en el panel de flags de Settings (categoría
      "interfaz_ui"), default ON; smoke de apagado/encendido de F5.3 ejecutado.
- [ ] Checklist de smoke manual de F5 completado y reportado punto por punto (lo no corrido se
      declara NO corrido — cero falsos verdes).
- [ ] Ningún archivo fuera de los declarados en F0-F4 modificado (`git status` limpio de
      sorpresas); el implementador NO commitea.
- [ ] Contratos de integración de §4 citados en el código (comentarios en `confirmGateway.ts`,
      `peekLinks.ts` y las queryKeys) para que 164/165/172/174 sepan dónde enchufarse.
- [ ] Resumen de implementación con: qué cambió, por qué, cómo se validó, y desvíos del plan (si
      los hubo) justificados.
