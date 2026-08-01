# Plan 282 — GitLab deja de ser un ADO disfrazado: paridad que se ve y cierre que no miente

**Estado:** MEJORADO v2 (v1 → v2 tras crítica adversarial con verificación de anclajes contra el código real)
**Veredicto de la crítica v1:** **RECHAZADO** (7 bloqueantes). Esta v2 los resuelve.
**Fecha:** 2026-08-01 (v1) · 2026-08-01 (v2)
**Rama:** `docs/plan-279` (rama de trabajo vigente; **no** se abre rama nueva — el worktree es único y
hay sesiones paralelas escribiendo el 280 y el 281 en este mismo árbol)
**Depende de:** 276 (TLS + sync + grafo), 277 (jerarquía), 278 (publicador de épica), 270/271 (cierre y
estado), **280 (dependencia DURA de F1, ver abajo)**

### Frontera con los planes hermanos (escritos en paralelo, LEER ANTES DE IMPLEMENTAR)

Los tres planes atacan el mismo incidente de campo —la corrida de RIPLEY/GitLab del 2026-08-01, execs
211/212— desde tres capas distintas. **Las fronteras se verificaron leyendo los dos documentos, no
asumiendo.**

| Plan | Su capa | Qué NO hace |
|---|---|---|
| **280** — El desenlace mira el trabajo entregado | **Decidir** el estado terminal: `has_delivered_work`, `classify_outcome_reason`, 4 motores → 1 | No toca a qué tracker se publica |
| **281** — El ruteo por tracker deja de mentir | **Enrutar** el cliente: erradicar los 8 sitios ADO-only, gate por AST, la firma `no usa Azure DevOps` | No toca `ado_publisher.py` (verificado: `grep ado_publisher\|post_comment` en el 281 → **0 hits**) |
| **282** — este | **Entregar y mostrar**: que el resultado llegue al issue de GitLab y que la pantalla hable el idioma del tracker | No decide estados ni erradica sitios ADO-only |

**Cesión explícita al plan 280.** La versión inicial de este plan tenía una fase F1 que agregaba un guard
de idempotencia a `_mark_terminal` (`claude_code_cli_runner.py:3105`, `codex_cli_runner.py:1975`) para que
el runner no pisara el `completed` del `output_watcher`. **Se retiró.** El plan 280 resuelve el mismo
síntoma más arriba y con más evidencia (44 ejecuciones y 93.447 caracteres de trabajo bajo estado `error`,
contra las 2 corridas que medía este plan): al hacer que la regla 8 mire el trabajo entregado, la
ejecución nunca llega a `_mark_terminal("error")`. Dos planes tocando los mismos dos runners para el mismo
síntoma es trabajo duplicado y conflicto de merge garantizado. **F1 de este plan (publicación) declara al
280 como dependencia dura:** sin el 280, la ejecución queda en `error` y el gate
`agent_completion_internal.py:233-234` (`final_status != "completed"` → `skipped`) impide publicar. Este
plan **no** vuelve a implementar esa lógica ni la parchea por su cuenta.

**Pase entrante del plan 281 §7 — aceptado en parte, y lo rechazado se dice.** El 281 deriva a este plan:
- *"Deep links de GitLab, `base_url` con namespace pegado, y demás features a medio portar"* →
  **ACEPTADO como diagnóstico, DIFERIDO como trabajo** (§6.8): la normalización silenciosa y la
  validación del backend ya contienen el caso; falta solo el hint en la UI.
- *"Construir el equivalente GitLab de los 7 sitios que F7 degrada a valor neutro"* (criterios de
  aceptación, self-review, similar tickets, auto-assign, business preflight, enriquecimiento de contexto,
  estado equivalente de tarea) → **RECHAZADO por priorización, ver §6.14.** Son 7 features nuevas, no
  arreglos de paridad. Aceptarlas volvería este plan inimplementable y contradice el encargo explícito de
  acotar el alcance a lo que se cierra bien.
- *"El breaker `ado_sync` con key de proyecto GitLab"* y *"la cadencia de polling"* → **RECHAZADO**, §6.15.

---

## 0. CHANGELOG v1 → v2

Todos los anclajes `archivo:línea` de v1 se **abrieron y verificaron**. Los censos de F0 se **ejecutaron**.

| # | Severidad | Qué estaba mal en v1 | Cómo lo resuelve v2 |
|---|---|---|---|
| C1 | **BLOQUEANTE** | El censo K2 de F0 **no reproduce 96**: ejecutado con el algoritmo textual de v1 da **118**. Peor: su regex exige comilla o `>` en la misma línea, así que **no ve `App.tsx:455`** (`📋 Tickets ADO`) — el ofensor **#1 del ranking del propio plan** — ni `TicketBoard.tsx:175`. §8 ordenaba "no avanzar sin ver 4 / 96": F0 era un rojo garantizado que mandaba al implementador a "arreglar" un censo correcto | F0 reescrito: baseline **118 medido**, regex que también captura **texto JSX suelto**, y guarda que exige ver `App.tsx` en el detalle. Ver §4/F0 |
| C2 | **BLOQUEANTE** | El techo `K2 ≤ 20` es **aritméticamente inalcanzable** con los 25 sitios de F4: los 17 archivos que F4 toca suman **40** de los 118. 118 − 40 = **78** aun eliminando el 100%. F0 y F4 se contradecían | K2 pasa a **censo particionado** (allowlist justificada vs. ruteables) con meta **0 en el conjunto ruteable** + sentinela anti-crecimiento de la allowlist. **[ADICIÓN ARQUITECTO A2]** |
| C3 | **BLOQUEANTE** | `resolve_comment_publisher(tracker_type: str)` **no puede construir el provider**: `get_tracker_provider(project)` (`tracker_provider.py:125`) y `GitLabTrackerProvider(project=, base_url=, group=, auth_path=, ca_bundle=)` exigen el **proyecto**. Con sólo el tipo, un modelo menor inventa un global y **escribe en el proyecto GitLab equivocado**. Y "espeja `tracker_write_router.py:56-80`" era falso: ese router recibe **el ticket** y devuelve un `StateWriter`, no un `Callable` | Firma nueva `resolve_comment_publisher(ticket) -> CommentPublisher \| None`, espejo real de `resolve_state_writer(ticket)` (**`tracker_write_router.py:55`**) |
| C4 | **BLOQUEANTE** | **Arity mismatch no detectado**: `ado_publisher.py:469` llama `client.post_comment(ado_id, html, "html")` — **3 posicionales**. `GitLabTrackerProvider.post_comment(item_id, body_html)` acepta **2** ⇒ `TypeError` en producción | El router devuelve un **adaptador con la forma del cliente ADO**, y un test de contrato por `inspect.signature` congela la llamada de `:469`. **[ADICIÓN ARQUITECTO A1]** |
| C5 | **BLOQUEANTE** | `PublishResult` **no tiene `error_kind`** (`ado_publisher.py:190-202`, `@dataclass(frozen=True)`, 10 campos). Los casos 4 y 5 de F1 asertaban `error_kind=...` sobre un campo inexistente | v2 declara el campo nuevo `error_kind: str \| None = None` **con default** (aditivo, no toca la tabla `agent_html_publish`) y lo lista como archivo a editar |
| C6 | **BLOQUEANTE** | F4 rompe **4 suites** que v1 no nombra: `TAB_META` está congelado por `shellNav.test.ts:19,36-37`, `shellIcons.test.ts:7-8`, `shellIconsCoverage.test.ts:11` y consumido por `App.tsx:310`. Y la única suite que v1 sí nombraba tenía **la ruta mal**: `commandPaletteDevopsActions.test.ts` vive en `frontend/src/components/__tests__/`, no en `services/__tests__/` | `TAB_META` **no se toca**. Se agrega `labelDeTab(tab, trackerType)`. Ruta del test corregida. **[ADICIÓN ARQUITECTO A3]** |
| C7 | **BLOQUEANTE** | F4/F7 exigen `trackerType` en `App.tsx`, que **no lo tiene en ninguna línea**, y v1 nunca decía de dónde sacarlo ("reusar esa misma fuente" ≠ instrucción) | v2 pinea la fuente exacta: `useWorkbench((s) => s.activeProject?.tracker_type ?? null)` (`store/workbench.ts:26`; patrón vivo en `TicketBoard.tsx:957,960`) |
| C8 | IMPORTANTE | La idempotencia que v1 declaraba "innegociable" **ya existe y es genérica**: `ado_publisher.py:438-449` hace `getattr(client, "comment_exists", None)`. Un segundo chequeo duplicaría un `fetch_all_comments` (paginado) por cierre | Se **reusa** el bloque existente; F1 prohíbe explícitamente agregar un segundo chequeo |
| C9 | IMPORTANTE | `_resolve_assignee_id` está en **`:162-169`**, no en `:519`. Y tiene **2 llamadores más** (`gitlab_provider.py:396`, `tools/migrar_mantis_gitlab/destination_writer.py:381`) + un test (`test_gitlab_provider.py:260-264`). El caso 4 de F3 exigía "propagar", lo que obliga a tocar el `except: pass` de `:168-169` y cambia el comportamiento de los otros dos | F3 declara el radio de impacto y **acota el cambio a `update_item_assignee`** con un helper `_resolve_assignee_id_strict`; los otros 2 llamadores quedan byte-idénticos y con test que lo congela |
| C10 | IMPORTANTE | F1 caso 5 citaba `api/tickets.py:7519` y `:7829` — que son el publicador de **ÉPICA**, no el de comentarios. Además `api/tickets.py` está **VEDADO por el plan 280 §G7** y tiene cambios sin commitear de otra sesión | El caso 5 se reancla en el `except` real del publicador de comentarios: `ado_publisher.py:494-500`. `api/tickets.py` queda en la lista de archivos prohibidos del DoD |
| C11 | IMPORTANTE | F6 anclaba el filtro en `:1159`, que es el `<input type="checkbox">`. Los consumidores reales de `CLOSED_STATES` son **`:354`, `:438`, `:795`, `:1078`, `:1094`** y `ADO_STATE_COLORS` se consume en **`:110`**. Y `:438` lo pasa como `closedStates:` a `canResolveWithAgent` (`incidents/devResolverModel.ts`), contrato que v1 ignoraba. "donde se consuma" era una frase vaga | Los 6 call sites listados uno por uno, con el contrato de `devResolverModel` declarado |
| C12 | IMPORTANTE | F5 rompe `frontend/src/services/__tests__/copyFormats.test.ts:94`, que asserta el fallback `adoUrl`, y v1 no lo nombraba. Además los consumidores son **3**, no 4 (`StructuredOutput.tsx:78` es el regex `CITATION_RE`, no una llamada) | Los 3 consumidores reales listados + el test ajeno declarado como parte del cambio |
| C13 | IMPORTANTE | F7 derivaba `TABS_SOLO_ADO` de `api/pm.py:71` y `:1171`. **`:1171` no es un guard**: es el mensaje "No hay sprint activo". Los guards reales son **10** (`:105, 291, 340, 380, 542, 926, 999, 1052, 1143` + el helper de respuesta `:68-73`) | Anclajes corregidos y la derivación se hace **por censo AST del guard**, no por dos líneas a mano |
| C14 | IMPORTANTE | Costura no declarada: 280, 281 y 282 escriben **a la vez** en `backend/config.py`, `services/harness_flags.py` (3 puntos) y `deployment/harness_defaults.env`. R9 sólo cubría el commit con pathspec | §4/F8.1 predeclara los 7 nombres y ancla la inserción **por SÍMBOLO** (después de `STACKY_GITLAB_DEEP_LINKS_ENABLED`), nunca por número de línea |
| C15 | IMPORTANTE | **Sin huella de regresión**, mientras el plan hermano 280 sí tiene su F6 | Nueva **F8.4** con el schema REAL verificado (`{schema_version, description, fingerprints[]}`; requeridos `id,title,class,status,log_pattern,log_guarded,killed_by,guard_test,self_test`; `_STATUS_ENUM = {"resolved","open","by_design"}`) y criterio **delta cero** porque el catálogo ya está rojo (1 entrada con `status:"guarded"`, fuera del enum) |
| C16 | MENOR | 8 anclajes con desfase de 1-3 líneas | Corregidos en el cuerpo: `project_context.py:340-343` · `update_item_assignee` `:506-520` · `ADO_STATE_COLORS` `:87-96` · `TicketGraphView.jsx` `STATE_COLORS` **`:47-57`** (v1 decía `48-55` y dejaba `"Removed"` colgando) · `<datalist>` `:241-246`, opciones **`:242-245`** (v1 decía `242-244` y se comía `Active`, que su propio test 4 espera) · `resolve_state_writer` `:55` · `harness_flags` categoría `:453` / `FlagSpec` `:4266` |
| C17 | MENOR | "extender el existente si lo hay; si no, crearlo" (F4) | Verificado: `frontend/src/lib/__tests__/` existe con 2 archivos y **`trackerLabels.test.ts` NO existe**. Se crea |

**Lo que la crítica CONFIRMÓ como correcto** (no se tocó): los 4 constructores de F2 (`gitlab_ci_logs.py:11`, `gitlab_ci_provider.py:31`, `gitlab_preflight.py:38`, `gitlab_variables.py:14`) — el censo AST **ejecutado da exactamente 4**; `tracker_provider.py:144-148` y `:153-156`; `agent_completion_internal.py:233-234` y `:247`; `gitlab_provider.py:152-160`, `:440`, `:450`, `:248`; `ado_provider.py:95`; `trackerUrls.ts:11`; los **19 de 25** sitios de F4 muestreados; y la frontera con 280/281 (`grep ado_publisher|post_comment|agent_completion_internal` sobre el 281 → **0 hits**, verificado en v2).

### [ADICIÓN ARQUITECTO] — lo que v2 aporta y v1 no tenía

- **A1 — El adaptador con forma de cliente ADO** (§4/F1). En vez de bifurcar la lógica del publicador, el router devuelve un objeto que **habla el dialecto del `client` que `ado_publisher` ya usa**. Consecuencia: la única línea que cambia en `ado_publisher.py` es *qué fábrica construye `client`*, y **todo lo de abajo funciona gratis para GitLab**: el dedupe por sha (`:386-408`), el dedupe por marcador (`:438-449`), la inyección del marcador (`:468`), la persistencia (`:506+`) y `_emit_and_persist`. Hace **imposible por construcción** el bug C4 y elimina la duplicación de idempotencia de C8.
- **A2 — Censo particionado con allowlist justificada** (§4/F0). Reemplaza un techo global inalcanzable por un criterio **binario, alcanzable y no degradable**: 0 rótulos ADO en el conjunto ruteable + sentinela que impide que la allowlist crezca sin justificación escrita (mismo patrón de "puerta trasera del gate" que el 281 F0).
- **A3 — `labelDeTab(tab, trackerType)`** (§4/F4). Rutea el rótulo del tab **sin tocar `TAB_META`**: 4 suites y `App.tsx:310` sobreviven intactos.

---

## 1. Objetivo

Stacky nació ADO-first. GitLab se agregó después y quedó a mitad de camino: **el trabajo se produce, pero
no llega al tracker y la pantalla habla un idioma que no es el del operador.** Este plan cierra la brecha
de FLUIDEZ en dos frentes medidos en vivo sobre RIPLEY/GitLab (53 issues abiertos / 1009 totales):

1. **El trabajo no llega al tracker.** El análisis técnico se generó, se validó y **no se publicó**:
   el publicador de comentarios (`services/ado_publisher.py`) es ADO-only y muere en
   `services/project_context.py:340-343`, aunque `services/gitlab_provider.py:440` ya implementa
   `post_comment`. Evidencia dura: tabla `agent_html_publish`, filas 56 y 57, `status='failed'`, con el
   `comment.html` válido en disco (12.163 y 22.448 bytes). Contraste en la misma tabla: filas 50-55,
   proyecto RSPACIFICO (ADO), `status='ok'`.
2. **La UI habla ADO.** La pestaña dice "Tickets ADO" mientras el título de la propia página dice
   "Tickets GitLab"; cada tarjeta rotula `ADO-1234`; el filtro "Solo abiertos" es **ciego** en GitLab; y
   "Copiar link ADO" pega una URL a `dev.azure.com/UbimiaPacifico/Strategist_Pacifico` — **la organización
   de otro cliente**.

Y por debajo de los dos, tres silencios que rompen la confianza sin decir nada: cuatro servicios GitLab
que **pierden el CA bundle** y mueren contra el certificado interno del operador; un `update_item_assignee`
que **borra al asignado** cuando el username no resuelve; y tres tabs ADO-only ofrecidos en el menú de un
proyecto GitLab que terminan en un cartel de "solo disponible para Azure DevOps".

Al terminar este plan, un operador GitLab ve su vocabulario, sus links funcionan, sus filtros filtran, y
cuando el agente termina el trabajo **el resultado aparece en su issue**.

### KPI / impacto esperado (todos binarios y medibles)

| # | KPI | Hoy (medido) | Meta |
|---|-----|--------------|------|
| K1 | Filas `agent_html_publish.status='failed'` con causa "no usa Azure DevOps" en un proyecto GitLab | 2 (ids 56, 57) | **0** |
| K2 | Rótulos con "ADO"/"Azure DevOps" en el conjunto **RUTEABLE** de `frontend/src` (total 118 medido − allowlist justificada; ver F0) | **40** ruteables de **118** totales | **0 ruteables**, y la allowlist **no crece** |
| K3 | Constructores de `GitLabTrackerProvider` que **bypassean la fábrica** y quedan sin `ca_bundle` | 4 (censo AST **ejecutado**, no estimado) | **0** |
| K4 | Sitios que construyen una URL de tracker con org/proyecto ADO hardcodeados | 1 (`utils/trackerUrls.ts:11`), con **3** consumidores de producción | **0** |
| K5 | Tabs ADO-only alcanzables desde un proyecto GitLab que terminan en callejón sin salida | 3 (PM, Sprint Board, User Stats) | **0** |
| K6 | Caminos de escritura a GitLab que **destruyen datos en silencio** ante un fallo de resolución | 1 (`update_item_assignee` vacía `assignee_ids`) | **0** |

**Nota sobre K1:** su medición exige que la ejecución llegue a `completed`, cosa que hoy depende del plan
280. Por eso el gate de F1 mide el **publicador aislado** (con el estado forzado en el test) y el smoke
manual mide la cadena completa. Un KPI que no se puede medir sin otro plan **no se declara verde**: sale
`exit 5`.

**Nota sobre K2 (corregida en v2 — C1/C2).** El censo de v1 declaraba 96 y un techo de ≤20. Ejecutado con
su propio algoritmo da **118**, y los 17 archivos que F4 toca suman **40**: aun eliminando el 100% de lo
que F4 alcanza quedan **78**. El techo era inalcanzable por 58 y ninguna fase lo cerraba. v2 reemplaza el
techo global por una **partición**: `RUTEABLES` (los que deben hablar el idioma del tracker → meta **0**) y
`LEGÍTIMOS` (allowlist con motivo escrito por archivo → congelada, no crece). Un techo global que ninguna
fase alcanza no es un KPI: es una promesa que el gate va a incumplir.

---

## 2. Por qué ahora / gap que cierra

Los planes 270-278 construyeron las piezas correctas y **declararon explícitamente fuera de alcance la
capa que las hace usables**:

- **276 §7** dejó fuera, textual, los rótulos de navegación global (`App.tsx:455`, `shellNav.ts:18`,
  `commandPaletteData.ts:74`) como "decisión de producto pendiente". Y creó `lib/trackerLabels.ts` —
  el helper correcto — pero **solo lo consumen 2 archivos** de toda la app.
- **270 §fuera-de-alcance** delegó a un "plan 272" la unificación de escritores y el vocabulario GitLab.
  **El plan 272 no existe** (número reservado sin archivo). Esas brechas están huérfanas.
- **271** dejó escrito que `_state_map_for_gitlab` entiende solo 4 claves lógicas y que "como la UI
  enseña vocabulario ADO, el caso común cae en `transition_failed`". Ese diagnóstico sigue vigente:
  `services/gitlab_provider.py:152-160`.
- **278** unificó los 3 RUNTIMES del publicador de épica, no los TRACKERS. Y el camino de **comentarios**
  (que es el que usa el operador todos los días al cerrar trabajo) nunca se tocó.

La decisión de producto que el 276 dejó pendiente **ya la tomó el operador**: usa GitLab de verdad, en
producción, y el requerimiento textual es "necesito que el uso de la herramienta sea muy fluido".

### Lo que este plan NO re-planifica (ya está hecho o en vuelo)

- **La idempotencia de `POST /api/tickets/epics/from-brief` YA ESTÁ IMPLEMENTADA** en el working tree
  (sin commitear): `api/tickets.py:8052` (`sealed_work_item_id`), `:8058` (`claim_publication`),
  `:8067` (409 `publish_in_progress`). No la toques.
- **El guard `typeof === "number"` de la épica duplicada YA ESTÁ PARCHEADO** en el working tree:
  `frontend/src/services/uiGuards.ts:78` (`sealedWorkItemId`) consumido desde
  `frontend/src/components/EpicFromBriefModal.tsx:223`. No lo toques.
- **El publicador de ÉPICA sí rutea** por provider desde `api/tickets.py:7176`. El que NO rutea es el de
  **comentarios**, que es otro módulo (F1).

---

## 3. Principios y guardarraíles (obligatorios en cada fase)

- **3 runtimes con paridad.** Todo lo de este plan vive en el chokepoint de cierre, en el publicador o en
  el frontend — capas **runtime-agnósticas**. **Ningún ítem de este plan toca un runner específico**: la
  decisión del estado terminal quedó cedida al plan 280. Cada fase declara igual su impacto por runtime.
- **Cero trabajo extra para el operador.** Las 7 flags nacen **default ON**. Ninguna cae en la categoría
  (A) —no enciende loops, daemons, polling ni prefetch—. Sobre la (B):
  - **F1 es la única que merece discusión seria**, porque hoy en GitLab **no se escribe nada** y encenderla
    hace que empiecen a aparecer comentarios en el tracker del operador. La justificación de v1 ("no agrega
    una escritura nueva") era **un atajo**. La justificación completa, de tres patas verificadas en el
    código, está escrita en F1 y **se sostiene o la flag pasa a OFF**: (1) la dispara el operador por
    corrida con el checkbox (`FinishWorkButton.tsx:225` → gate `agent_completion_internal.py:243-245`),
    (2) es idempotente por dos barreras que ya existen (`ado_publisher.py:386-408` y `:438-449`), (3) su
    modo de fallo es inerte (`publisher_unavailable`), no destructivo.
  - **F3 reduce** la escritura: deja de emitir un PUT que **borra** el asignado. Una flag que quita una
    escritura destructiva no puede nacer OFF sin dejar el destrozo encendido de fábrica.
  - **F2** cambia de dónde sale un objeto de configuración. **F4, F5, F6, F7** son lectura y presentación.
  Justificación escrita por flag en cada fase; ninguna se apoya en "default seguro" ni en "prerequisito no
  garantizado", que **no son categorías válidas**.
- **Human-in-the-loop.** Nada se publica ni se cierra solo que no se publicara o cerrara ya hoy. F7
  **oculta** entradas que llevan a callejones sin salida; no decide nada por el operador.
- **Mono-operador, sin auth.** Ningún ítem introduce roles ni permisos.
- **No degradar.** Todos los cambios son aditivos y con fallback al comportamiento actual. Los helpers
  nuevos del frontend son **funciones puras en `.ts`** (RTL/jsdom no están instalados en este repo).
- **Backward-compatible.** Un proyecto ADO debe comportarse EXACTAMENTE igual que hoy. Cada fase tiene al
  menos un caso de test que congela el comportamiento ADO.

---

## 4. Fases

### F0 — Medir el defecto antes de tocarlo (el gate que hoy está ROJO)

**Objetivo:** dejar por escrito y ejecutable el estado de hoy, para que las fases siguientes se verifiquen
contra el defecto y no contra sí mismas.

**Valor:** sin esto, cada fase siguiente puede pasar por accidente. Este repo tiene precedentes de tests
que pasan con el bug vivo.

**Archivos a crear:**
- `Stacky Agents/backend/tests/test_plan282_censo_paridad.py`
- `Stacky Agents/frontend/src/services/__tests__/plan282Censo.test.ts`

**Contenido exacto del test backend** (`test_plan282_censo_paridad.py`):

```python
"""Plan 282 F0 — censos ejecutables del estado ANTES del arreglo.

REGLA DE LA CASA: un censo por subcadena da por cubierta la ruta larga y un censo
circular grepea su propia lista. Acá se BARRE EL DIRECTORIO y se cuenta por AST /
por referencia, nunca por `grep -c` sobre un closure.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

def test_f0_censo_constructores_gitlab_que_bypassean_la_fabrica():
    """K3: cuenta los módulos que llaman GitLabTrackerProvider(...) DIRECTO en vez
    de pasar por get_tracker_provider(). Esos nacen sin ca_bundle y mueren contra
    un GitLab con CA interna.

    ANTES del arreglo: exactamente 4 (gitlab_ci_logs:11, gitlab_ci_provider:31,
    gitlab_preflight:38, gitlab_variables:14). DESPUÉS de F2: 0.
    VERIFICADO ejecutando este mismo censo en la crítica v2: da 4. Es el unico
    numero de este plan que reprodujo a la primera.

    Se excluye services/tracker_provider.py — ESE es el que tiene derecho
    (:144-148 per-project, :153-156 legacy; ambos pasan ca_bundle).

    ALCANCE DECLARADO (v2): el glob es NO recursivo sobre services/. Fuera del
    censo, a proposito: tools/migrar_mantis_gitlab/destination_writer.py:267
    (el migrador tiene su propio eje, §6.10) y los 8 constructores de tests.
    Un censo que barriera todo el backend daria 15 y mezclaria deuda ajena.
    """
    ofensores = []
    for py in (BACKEND / "services").glob("*.py"):
        if py.name == "tracker_provider.py":
            continue
        arbol = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) \
               and nodo.func.id == "GitLabTrackerProvider":
                ofensores.append(f"{py.name}:{nodo.lineno}")
    # F0 (rojo esperado): assert len(ofensores) == 4
    # F2 (verde):
    assert ofensores == [], f"bypassean la fabrica: {ofensores}"


def test_f0_el_publicador_de_comentarios_es_ado_only():
    """K1: hoy services/ado_publisher.py resuelve el cliente sin preguntar el
    tracker, y por eso muere en project_context.py:340-343 en todo proyecto GitLab.

    GUARDA ANTI-FALSO-VERDE: el detector se prueba PRIMERO contra un fuente
    sintetico que si tiene el ruteo, y contra otro que no. Un assert de ausencia
    que nunca vio un positivo no prueba nada.
    """
    con_ruteo = "def p():\n    pub = resolve_comment_publisher(tracker_type)\n"
    sin_ruteo = "def p():\n    client = _client_for_ticket_project(x)\n"
    assert _rutea_por_tracker(con_ruteo), "el detector da falso negativo: test invalido"
    assert not _rutea_por_tracker(sin_ruteo), "el detector no detecta: test invalido"

    texto = (BACKEND / "services" / "ado_publisher.py").read_text(encoding="utf-8")
    # F0 (rojo esperado): assert not _rutea_por_tracker(texto)
    # F1 (verde):
    assert _rutea_por_tracker(texto), "ado_publisher no consulta el router de tracker"


def _rutea_por_tracker(fuente: str) -> bool:
    """True si el fuente REFERENCIA resolve_comment_publisher.

    Se censa por REFERENCIA (ast.Name/ast.Attribute), no por ast.Call con
    func.id: si manana la llamada se hace por alias o por atributo de modulo,
    un censo de llamadas daria CERO y premiaria el bug.
    """
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name) and nodo.id == "resolve_comment_publisher":
            return True
        if isinstance(nodo, ast.Attribute) and nodo.attr == "resolve_comment_publisher":
            return True
    return False
```

**Contenido exacto del test frontend** (`plan282Censo.test.ts`) — **REESCRITO EN v2 (C1, C2, [A2])**:

> **Dos defectos del censo v1, medidos, no supuestos.** (1) El total real es **118**, no 96. (2) Su regex
> exigía comilla o `>` en la misma línea, así que **no veía `App.tsx:455`** (`📋 Tickets ADO` es texto JSX
> suelto) — el ofensor que el propio plan rankea **#1** — ni `TicketBoard.tsx:175`. Un censo que no ve al
> ofensor principal no puede ser el gate de la fase que lo arregla.
>
> **Por qué partición y no techo.** F4 alcanza 17 archivos que suman **40** de los 118. El resto son
> superficies que **deben** decir ADO (selector de tracker, migrador ADO→GitLab, preview de pipeline ADO)
> o pantallas ADO-only por diseño (PM, Sprint Board, User Stats). Un techo global mezcla las dos cosas y
> obliga a elegir entre incumplir el gate o hacer trabajo fuera de alcance. La partición hace el criterio
> **binario y alcanzable**, y la sentinela impide que la allowlist se use como escape.

```ts
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const SRC = join(__dirname, "..", "..");   // desde src/services/__tests__/ → src/

/** ALLOWLIST — superficies donde decir "ADO" es CORRECTO. Cada entrada lleva su
 *  motivo escrito: esta lista es la puerta trasera del gate y no se toca sin
 *  justificar en el PR. Rutas relativas a src/, con separador POSIX. */
const LEGITIMOS: Record<string, string> = {
  // Selección/configuración de tracker: el operador elige ENTRE trackers.
  "components/NewProjectModal.tsx":        "selector de tracker en el alta de proyecto",
  "components/EditProjectModal.tsx":       "selector de tracker en la config del proyecto",
  "pages/SettingsPage.tsx":                "config global del tracker",
  // Migrador ADO→GitLab: ADO es literalmente el origen.
  "pages/MigratorPage.tsx":                "migrador ADO→GitLab: ADO es el origen",
  "components/MigratorWizard.tsx":         "idem migrador",
  "components/MigratorMappingTable.tsx":   "idem migrador",
  // Pipelines: el preview YAML de Azure Pipelines es un artefacto ADO.
  "components/devops/PipelineYamlPreview.tsx":   "YAML de Azure Pipelines",
  "components/devops/PipelineBuilderSection.tsx": "builder de Azure Pipelines",
  "components/devops/BlockProperties.tsx":       "bloques de Azure Pipelines",
  "components/devops/CommitPipelineModal.tsx":   "commit de azure-pipelines.yml",
  "components/devops/OneClickPublishModal.tsx":  "publicación de pipeline ADO",
  "components/devops/PipelineEnvMatrixPanel.tsx":"matriz de entornos ADO",
  "components/devops/ProductionFlow.tsx":        "flujo de release ADO",
  "components/devops/PublicationsSection.tsx":   "publicaciones ADO",
  "components/devops/TriggerPipelineSection.tsx":"trigger de pipeline ADO",
  "components/devops/VariablesSection.tsx":      "variables de pipeline ADO",
  "pages/DevOpsPage.tsx":                        "cockpit DevOps ADO",
  "components/PipelineGeneratorPanel.tsx":       "generador de azure-pipelines.yml",
  "hooks/useAutoFillBlocks.ts":                  "autofill de bloques ADO",
  // Pantallas ADO-only por diseño (F7 las gatea, no las traduce).
  "pages/PMCommandCenter.tsx":  "PM Suite v1 es ADO-only (api/pm.py)",
  "pages/SprintBoardPage.tsx":  "Sprint Board es ADO-only (api/pm.py)",
  "pages/UserStatsPage.tsx":    "User Stats es ADO-only (api/pm.py)",
  // El diccionario de rótulos: "ADO" es su DATO, no su bug.
  "lib/trackerLabels.ts":       "el mapa NOMBRES contiene la cadena por definición",
};

function archivosFuente(dir: string): string[] {
  const salida: string[] = [];
  for (const entrada of readdirSync(dir)) {
    if (entrada === "node_modules" || entrada === "__tests__") continue;
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) salida.push(...archivosFuente(ruta));
    else if (/\.(tsx?|jsx)$/.test(entrada) && !/\.test\.tsx?$/.test(entrada)) salida.push(ruta);
  }
  return salida;
}

/** Cuenta rótulos ADO visibles. Descarta líneas de comentario (el código está en
 *  español: contarlas da 100% de falsos positivos) Y **captura texto JSX suelto**
 *  — el defecto de v1, que dejaba fuera `App.tsx:455` y `TicketBoard.tsx:175`. */
export function rotulosAdo(texto: string): number {
  return texto
    .split("\n")
    .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
    .filter((l) => /\b(ADO|Azure DevOps)\b/.test(l)).length;
}

function rel(f: string): string { return relative(SRC, f).split(sep).join("/"); }

describe("Plan 282 F0 — censo particionado de rótulos ADO (K2)", () => {
  it("guarda anti-falso-verde: el detector detecta y descarta comentarios", () => {
    expect(rotulosAdo(`const x = "Tickets ADO";`)).toBe(1);
    expect(rotulosAdo(`              📋 Tickets ADO`)).toBe(1);   // ← texto JSX suelto (el bug de v1)
    expect(rotulosAdo(`// comentario sobre ADO`)).toBe(0);
    expect(rotulosAdo(`const x = "GitLab";`)).toBe(0);
  });

  it("guarda: el censo VE App.tsx (el ofensor #1 del plan)", () => {
    // Si esto da 0, el regex volvió a estar mal: App.tsx:455 dice "📋 Tickets ADO".
    expect(rotulosAdo(readFileSync(join(SRC, "App.tsx"), "utf-8"))).toBeGreaterThan(0);
  });

  it("K2: CERO rótulos ADO en el conjunto RUTEABLE", () => {
    const ruteables: Record<string, number> = {};
    for (const f of archivosFuente(SRC)) {
      const r = rel(f);
      if (r in LEGITIMOS) continue;
      const n = rotulosAdo(readFileSync(f, "utf-8"));
      if (n > 0) ruteables[r] = n;
    }
    // F0 (rojo esperado, MEDIDO en la crítica v2):
    //   expect(Object.values(ruteables).reduce((a,b)=>a+b,0)).toBe(40);
    // F4..F7 (verde):
    expect(ruteables).toEqual({});
  });

  it("sentinela: la allowlist no crece sin justificación", () => {
    expect(Object.keys(LEGITIMOS).length).toBe(23);
    // Toda entrada debe traer motivo NO vacío: sin esto la allowlist es un agujero.
    for (const [k, v] of Object.entries(LEGITIMOS)) expect(v.trim().length, k).toBeGreaterThan(0);
  });
});
```

**Nota de calibración (obligatoria, primer paso de F0).** Los números `40` y `23` son los **medidos en la
crítica v2 con este mismo algoritmo**. Corré el test **antes de tocar nada**: si `ruteables` no suma 40, es
porque otra sesión movió código — **actualizá el número con el medido y anotá el delta en este doc**, no
"arregles" el censo. Lo que **no** se negocia es que `App.tsx` aparezca en `ruteables`: si no aparece, el
regex está mal. Comando de calibración, que imprime el detalle por archivo:

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/services/__tests__/plan282Censo.test.ts --testTimeout=60000 --reporter=verbose
```

**Comando exacto:**
```bash
# backend (venv del repo — el que ANDA es backend/venv)
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan282_censo_paridad.py -v
# frontend (POR ARCHIVO: vitest contamina por orden)
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/services/__tests__/plan282Censo.test.ts --testTimeout=60000
```

**Criterio de aceptación BINARIO de F0:** los 2 archivos existen y, con los asserts en su versión
"rojo esperado" (las líneas comentadas), **ambos PASAN** reproduciendo **4** (backend) y **40 ruteables /
23 legítimos** (frontend), con `App.tsx` presente en el detalle, y detectando que `ado_publisher` **no**
rutea. Eso prueba que el censo ve el defecto. Recién entonces se activan los asserts "verde" y las fases
siguientes los llevan a **0 / {} / con guard**.

**Flag:** ninguna (son tests).
**Runtimes:** N/A (no toca runtime).
**Trabajo del operador:** ninguno.

**Registro obligatorio en los DOS ratchets** (sintaxis distinta — v2 la escribe, v1 la dejaba inferir):
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — bloque de `tests/test_plan277_*.py`, hoy en
  **:250-256**. Sintaxis: **dos espacios de sangría + la ruta, SIN comillas ni coma**:
  ```
    tests/test_plan282_censo_paridad.py
  ```
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — mismo bloque, hoy en **:243-249**. Sintaxis:
  **dos espacios + la ruta ENTRE COMILLAS DOBLES + coma final**:
  ```
    "tests/test_plan282_censo_paridad.py",
  ```
- **El ratchet no admite rutas con espacios**: la ruta es relativa a `backend/`, sin espacios.
- **Los dos archivos están modificados por otra sesión** (plan 279): agregá tus líneas **al final del
  bloque 277**, sin tocar las suyas, y verificá con `git diff --stat -- backend/scripts/` que sólo crecen.
- Los **4** archivos de test backend de este plan se registran en **ambos**: `test_plan282_censo_paridad.py`,
  `test_plan282_publicacion_comentario.py`, `test_plan282_fabrica_unica.py`,
  `test_plan282_assignee_no_borra.py`.

---

### F1 — El comentario del agente se publica en GitLab

**Objetivo:** que el HTML que el agente ya generó y validó llegue al issue de GitLab, igual que llega al
work item de ADO.

**Valor:** cierra K1. Hoy el operador GitLab **nunca** recibe el resultado en su tracker: queda un
`comment.html` en disco y una fila `failed` en la bitácora. Es el "produce el trabajo pero reporta mal"
en su forma más cara.

**Diagnóstico exacto (anclajes verificados en v2):**
```
agent_completion_internal.py:233-234  if final_status != "completed": skipped        [OK]
agent_completion_internal.py:243-245  if not _should_auto_publish(...): skipped      [OK]
agent_completion_internal.py:247      _attempt_publish()                             [OK]
ado_publisher.py:410-418              # ── 5. Resolver el cliente ADO ──             [OK]
                                      client = _client_for_ticket_project(...)
project_context.py:340-343            if ctx.tracker_type != _DEFAULT_TRACKER_TYPE:
                                          raise AdoConfigError("... no usa Azure DevOps ...")
```
Y del otro lado, listo y sin usar: `services/gitlab_provider.py:440` `post_comment(item_id, body_html)`,
que renderiza a markdown vía `_render_note` (`:248`), y `comment_exists` en `:450`.

---

#### [ADICIÓN ARQUITECTO A1] — El adaptador con forma de cliente, no una bifurcación

v1 proponía bifurcar la lógica del publicador ("si el tracker no es ADO y hay publicador, usarlo"). Eso
tiene **dos defectos que la crítica midió**:

1. **`ado_publisher.py:469` llama `client.post_comment(ado_id, html_to_publish, "html")` — TRES
   posicionales.** `GitLabTrackerProvider.post_comment(self, item_id, body_html)` acepta **dos**. La
   bifurcación de v1 explota con `TypeError` en la primera corrida real. (C4)
2. **La idempotencia que v1 declaraba "innegociable" ya existe y es genérica**: `ado_publisher.py:438-449`
   hace `comment_exists_fn = getattr(client, "comment_exists", None)` y, si es llamable, la usa. Agregar
   un segundo chequeo duplicaría un `fetch_all_comments` paginado por cada cierre. (C8)

**El diseño correcto se cae de maduro leyendo el publicador:** todo lo que hay entre `:410` y `:520`
trabaja contra una variable llamada `client` y **sólo le pide tres cosas** — `post_comment(id, html,
"html")`, `comment_exists(id, marker)` y (opcional) los métodos de adjuntos que consume
`_prepare_html_attachments`. Entonces el router no devuelve "un publicador": devuelve **un objeto con la
forma del cliente ADO**. Consecuencia directa, y es el valor de esta adición:

> La **única** línea de lógica que cambia en `ado_publisher.py` es **qué fábrica construye `client`**.
> El dedupe por sha (`:386-408`), el dedupe por marcador (`:438-449`), la inyección del marcador (`:468`),
> la exigencia de `comment_id` en la respuesta (`:473-482`), la persistencia (`:506+`) y `_emit_and_persist`
> **pasan a funcionar para GitLab sin tocarlos**. El bug C4 se vuelve **imposible por construcción**
> porque la firma la define el adaptador, y C8 desaparece porque no hay segundo chequeo que escribir.

**Archivo a crear:** `Stacky Agents/backend/services/comment_publish_router.py`

Módulo **puro de ruteo**, sin Flask ni sesión. Espeja la forma REAL de
`services/tracker_write_router.py:55` — que **recibe el ticket** y devuelve un handle, no un `Callable`
suelto. (v1 decía `:56-80` y una firma `(tracker_type: str)`; con sólo el tipo **es imposible construir el
provider**, porque `get_tracker_provider(project)` y `GitLabTrackerProvider(project=, base_url=, group=,
auth_path=, ca_bundle=)` necesitan el PROYECTO — C3.)

```python
@dataclass(frozen=True)
class CommentPublisher:
    tracker_type: str          # "azure_devops" | "gitlab"
    kind: str                  # "ado_client" | "gitlab_adapter"
    handle: object             # SIEMPRE con la forma del cliente ADO (ver abajo)


def resolve_comment_publisher(ticket) -> CommentPublisher:
    """Devuelve el publicador de comentarios del tracker del TICKET.

    Espejo exacto de services/tracker_write_router.py:55 `resolve_state_writer`.
    Recibe el TICKET (no el tipo) porque el provider GitLab se construye POR
    PROYECTO: services/tracker_provider.py:125 `get_tracker_provider(project)`.

    - tracker_type ausente / "azure_devops"
        -> CommentPublisher(kind="ado_client",
                            handle=_client_for_ticket_project(...))   # camino de HOY, sin cambios
    - tracker_type == "gitlab"
        -> CommentPublisher(kind="gitlab_adapter",
                            handle=GitLabCommentClient(get_tracker_provider(stacky_project_name)))
           Si esa fabrica levanta TrackerConfigError (p.ej. STACKY_GITLAB_ENABLED=false),
           se RE-LEVANTA como CapabilityUnavailable. NUNCA se cae a ADO.
    - cualquier otro tracker
        -> levanta CapabilityUnavailable  (el llamador lo traduce a
           PublishResult(ok=False, error_kind="publisher_unavailable"), NO revienta).

    REGLA DURA, copiada literal del write router: nunca devuelve kind="ado_client"
    cuando el tracker_type normalizado no es "azure_devops" (ni vacio/None).
    """


class GitLabCommentClient:
    """Adaptador: habla el dialecto que `ado_publisher` ya usa.

    Existe por UNA razon medible: ado_publisher.py:469 llama
    `client.post_comment(ado_id, html, "html")` con TRES posicionales, y
    GitLabTrackerProvider.post_comment (gitlab_provider.py:440) acepta DOS.
    """

    def __init__(self, provider): self._p = provider

    def post_comment(self, item_id, body_html, content_format="html") -> dict:
        """content_format se ACEPTA y se IGNORA: el provider ya convierte a
        markdown en _render_note (gitlab_provider.py:248). Se acepta para que la
        llamada de ado_publisher.py:469 no cambie.

        DEBE devolver un dict con clave "id": ado_publisher.py:473-482 exige
        `comment_id` en la respuesta o levanta RuntimeError. La API de notas de
        GitLab devuelve {"id": ...} y post_comment lo pasa tal cual (:448).
        """
        return self._p.post_comment(str(item_id), body_html)

    def comment_exists(self, item_id, marker) -> bool:
        """gitlab_provider.py:450. La consume ado_publisher.py:438-449 por
        getattr: NO se escribe un segundo chequeo de idempotencia."""
        return self._p.comment_exists(str(item_id), marker)
```

**Sobre adjuntos (declarado, no inferido):** `_prepare_html_attachments` (`ado_publisher.py:458`) recibe
`client=client`. Si el adaptador no expone lo que esa función usa, **debe degradar sin romper**: el
adaptador implementa `upload_attachment` / `link_attachment` delegando a `gitlab_provider.py:456` y `:468`
si existen, y si `_prepare_html_attachments` levanta, el camino ya está cubierto por
`except AttachmentPublishError` (`:483-493`). **Antes de escribir el adaptador, abrí
`_prepare_html_attachments` y anotá acá qué métodos exige.** Es la única incógnita declarada de F1.

**Archivos a editar (los 2, exactos):**
1. `Stacky Agents/backend/services/ado_publisher.py`
   - **`:190-202`** — agregar al `@dataclass(frozen=True) class PublishResult` el campo
     **`error_kind: str | None = None`**. Va **con default**, al final, después de `marker`: es aditivo,
     no rompe ninguna construcción existente y **no toca la tabla `agent_html_publish`**. (v1 asertaba
     sobre este campo sin declararlo: no existía — C5.)
   - **`:410-418`** — sustituir la construcción de `client` por el router. El `client_factory` explícito
     (`:412-413`) **sigue ganando** (lo usan los tests de hoy: no lo toques). Sólo la rama `else` cambia:
     ```python
     else:
         pub = resolve_comment_publisher(ticket)   # levanta CapabilityUnavailable si no hay
         client = pub.handle
     ```
     y el `except` de `:419-429` suma una rama previa para `CapabilityUnavailable` que devuelve
     `PublishResult(ok=False, status="failed", error_kind="publisher_unavailable", ...)` **sin** dejar que
     `AdoConfigError` escape.
2. `Stacky Agents/backend/services/comment_publish_router.py` (nuevo, arriba).

**PROHIBIDO en F1** (cada uno cierra un defecto medido):
- Escribir un segundo chequeo de `comment_exists`: ya está en `:438-449` (C8).
- Cambiar la llamada de `:469`: el adaptador se adapta a ella, no al revés (C4).
- Tocar `api/tickets.py`: es el publicador de **ÉPICA**, otro módulo, **vedado por el plan 280 §G7** y con
  cambios sin commitear de otra sesión (C10).

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan282_publicacion_comentario.py`

Casos exactos (**7** en v2; el 7 es nuevo y cierra C4):
1. `test_ado_sigue_publicando_igual_que_hoy` — congela el camino ADO byte a byte. **Primero este.**
2. `test_gitlab_publica_por_post_comment` — provider fake, asserta que se llamó `post_comment` con el
   `item_id` correcto y que el `PublishResult.ok is True`.
3. `test_gitlab_no_duplica_si_el_marcador_ya_existe` — `comment_exists` devuelve True → el resultado sale
   `status="idempotent_replay"` con `reason="ado_marker_exists"` (es el camino de `ado_publisher.py:444-449`,
   **no** un `skipped` nuevo) y `post_comment` **no** se llamó.
4. `test_tracker_sin_publicador_no_revienta` — `tracker_type="mantis"` → `ok=False`,
   `error_kind="publisher_unavailable"`, y **no** escapa `AdoConfigError` ni `CapabilityUnavailable`.
5. `test_el_fallo_del_tracker_se_clasifica_y_no_cae_en_exception_generica` — el adaptador lanza
   `TrackerApiError`; asserta `error_kind="tracker_error"`. **Reanclado en v2 (C10):** el `except` que hoy
   se traga esto es **`ado_publisher.py:494-500`** (`except Exception` → `reason="ADO post_comment failed:
   ..."`), no `api/tickets.py:7519/:7829` — esos dos son el publicador de **ÉPICA**, otro módulo y archivo
   vedado. El test congela que un fallo **tipado** de GitLab sale como `error_kind="tracker_error"` y no
   disfrazado de "ADO post_comment failed".
   > `TrackerApiError` exige `status` **posicional** en su constructor: `TrackerApiError("msg", 500)`.
   > Instanciarlo con sólo el mensaje falla y deja el test rojo por la razón equivocada.
6. `test_reproduce_el_fallo_de_hoy_con_la_flag_off` — con `STACKY_COMMENT_PUBLISH_ROUTED_ENABLED=False`,
   el proyecto GitLab vuelve a fallar con la firma `no usa Azure DevOps`. **El gate se corre CONTRA el
   defecto.**
7. **`test_el_adaptador_acepta_la_llamada_EXACTA_de_ado_publisher`** — *(nuevo en v2, [A1])*. Gate de
   contrato por `inspect.signature`: construye el adaptador con un provider fake y lo invoca **igual que
   `ado_publisher.py:469`**, con tres posicionales:
   ```python
   adaptador.post_comment(1115, "<p>x</p>", "html")   # 3 posicionales, como :469
   ```
   y asserta que el dict devuelto **tiene clave `"id"`** (lo exige `:473-482`). Guarda anti-falso-verde:
   antes, el test comprueba que un objeto con la firma de DOS argumentos **sí** levanta `TypeError` al
   recibir tres — probando que el detector detecta. **Este es el test que v1 no tenía y que habría
   atrapado el `TypeError` de producción.**

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan282_publicacion_comentario.py -v
./venv/Scripts/python.exe -m pytest tests/test_plan282_publicacion_comentario.py --collect-only -q | tail -3
```
**Criterio BINARIO:** los 7 casos pasan y `--collect-only -q` reporta **exactamente 7 seleccionados**
(`pytest -k` sin match sale **exit 0**: el conteo es el único gate honesto).
**Aislamiento de BD obligatorio:** estos tests tocan `session_scope`. Corrélos con `DATABASE_URL` apuntando
a la base de test del repo. **Un pytest suelto sin `DATABASE_URL` escribe en la base VIVA del operador.**

**Flag:** `STACKY_COMMENT_PUBLISH_ROUTED_ENABLED`, **default ON**.

**Justificación del ON — reescrita en v2, porque la de v1 era un atajo.** v1 se limitaba a decir "no agrega
una escritura nueva". Eso es discutible: **hoy, en GitLab, no se escribe nada**, así que encender esto sí
hace que empiecen a aparecer comentarios en el GitLab del operador. El argumento honesto es **de tres patas,
todas verificadas en el código**, y sólo si las tres se sostienen el ON es legítimo:

1. **La escritura la dispara el operador, por corrida, a mano.** El checkbox "Publicar comentario"
   (`FinishWorkButton.tsx:225`) alimenta `auto_publish`, y `agent_completion_internal.py:243-245` saltea la
   publicación si está apagado (`reason="auto_publish_disabled"`). Además `:233-234` exige
   `final_status == "completed"`. No hay camino autónomo: **sin acción del operador no se escribe nada**.
2. **Es idempotente por construcción, con dos barreras que ya existen**: dedupe por sha (`:386-408`, se
   aplica **incluso con `force=True`**) y dedupe por marcador contra el propio tracker (`:438-449`). El
   precedente de la épica duplicada de esta semana nació justo de publicar sin ninguna de las dos.
3. **El modo de fallo es inerte, no destructivo**: si no hay publicador, sale
   `error_kind="publisher_unavailable"` y se registra; no borra, no cierra, no transiciona.

Con esas tres, **no es categoría (B)**: no hay escritura autónoma, no hay pérdida de datos y no se le saca
ninguna decisión al operador — se repara una acción que él ya pide y que **hoy falla en silencio**. Nacer
OFF obligaría al operador a encender una flag para que una función que ya autorizó deje de estar rota:
exactamente el "trabajo extra" que el riel prohíbe. **Si alguna de las tres patas no se sostiene al
implementar (p. ej. si el adaptador termina publicando fuera del gate de `auto_publish`), la flag pasa a
OFF y se declara la categoría.** No se resuelve con una nota: se cambia el default.

**Impacto por runtime:** el publicador vive en `agent_completion_internal`, chokepoint runtime-agnóstico.
Los 3 runtimes lo atraviesan igual. Sin fallback por runtime porque no hay divergencia por runtime.

**Trabajo del operador:** ninguno.

---

### F2 — Los servicios GitLab dejan de bypassear la fábrica (y de perder el CA bundle)

**Objetivo:** que ningún módulo construya `GitLabTrackerProvider` a mano.

**Valor:** cierra K3. Contra un GitLab self-hosted con CA interna —**el caso del operador**— estos 4
servicios mueren con `CERTIFICATE_VERIFY_FAILED` mientras la sonda y el listado de tickets funcionan. Es
la peor forma de "no fluido": una parte del producto anda y otra no, sin explicación visible.

**Evidencia (los 4 ofensores):**
```
services/gitlab_ci_logs.py:11      GitLabTrackerProvider(project=project)   ← sin ca_bundle
services/gitlab_ci_provider.py:31  GitLabTrackerProvider(project=project)   ← sin ca_bundle
services/gitlab_preflight.py:38    GitLabTrackerProvider(project=project)   ← sin ca_bundle
services/gitlab_variables.py:14    GitLabTrackerProvider(project=project)   ← sin ca_bundle
```
La fábrica correcta ya resuelve el bundle en **ambas** ramas: `services/tracker_provider.py:144-148`
(per-project) y `:153-156` (legacy). El plan 276 F8.1 ya arregló la rama legacy y dejó escrito que era
"el único camino del repo que construía este provider sin certificado". **Faltaban estos 4.**

**Cambio exacto en los 4 archivos:** reemplazar la construcción directa por
`services.tracker_provider.get_tracker_provider(project)`, y validar que lo devuelto sea un
`GitLabTrackerProvider` (si el proyecto no es GitLab, estos servicios no aplican: devolver el error
tipado del módulo, no un `AttributeError`).

**Cuidado con el import circular:** `tracker_provider.py` importa `gitlab_provider`. Los 4 servicios
deben importar `get_tracker_provider` **dentro de la función**, no a nivel de módulo — es el patrón que
`tracker_provider.py:141` ya usa para `project_context`.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan282_fabrica_unica.py`
1. El censo AST de F0 da **0** ofensores (reusar la función, no reescribirla).
2. Para cada uno de los 4 servicios: con un proyecto GitLab que tiene `ca_bundle` configurado, el cliente
   resultante **tiene** ese bundle. Monkeypatchear `get_tracker_provider` y assertar el paso del valor.
3. `test_servicio_en_proyecto_ado_devuelve_error_tipado` — no `AttributeError`.
4. Guarda: con la flag OFF, el camino viejo sigue disponible (reversibilidad).

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan282_fabrica_unica.py -v
```
**Criterio BINARIO:** los **4** casos verdes, `--collect-only -q` reporta **exactamente 4 seleccionados**,
y el censo F0 de constructores en **0**.

**ADVERTENCIA:** `services/gitlab_client.py:143-145` documenta que **no** hay que ensuciar
`REQUESTS_CA_BUNDLE` global (rompe la verificación de ADO/Jira/Mantis/LLM en el mismo backend). El único
sitio que lo hace hoy es `tools/migrar_mantis_gitlab/destination_writer.py:238`, que está **fuera de
alcance** de este plan (§6). No "arregles" los 4 servicios exportando esa variable.

**Flag:** `STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED`, **default ON**. No agrega escrituras ni loops:
cambia de dónde sale un objeto de configuración.
**Impacto por runtime:** ninguno (capa de servicios).
**Trabajo del operador:** ninguno.

---

### F3 — El asignado deja de borrarse en silencio

**Objetivo:** que un username GitLab que no resuelve **falle diciéndolo**, en vez de vaciar el campo.

**Valor:** cierra K6. Es el silencio más caro de la matriz de paridad. Hoy `update_item_assignee`
(`services/gitlab_provider.py:506-520`) hace:
```python
assignee_id = self._resolve_assignee_id(assignee) if assignee else None
update_body: dict = {}
if assignee_id: update_body["assignee_ids"] = [assignee_id]
else:           update_body["assignee_ids"] = []   # ← BORRA al asignado actual
```
`_resolve_assignee_id` está en **`gitlab_provider.py:162-169`** (v1 decía `:519-...`, que es
`json_body=update_body,` — anclaje muerto, C9) y devuelve `None` ante cualquier fallo porque su cuerpo es
un `try/except: pass`. Resultado: un typo en el username, o un fallo transitorio de `/users`,
**desasigna el issue del operador sin avisar**. En ADO el camino equivalente propaga el error.

**RADIO DE IMPACTO — declarado en v2, ausente en v1 (C9).** `_resolve_assignee_id` tiene **3 llamadores**:

| Llamador | ¿Lo toca F3? | Por qué |
|---|---|---|
| `gitlab_provider.py:509` (`update_item_assignee`) | **SÍ** — es el defecto | Es el único que manda `[]` destructivo |
| `gitlab_provider.py:396` | **NO** | Camino de creación/actualización de item; su semántica de "sin asignado" es legítima |
| `tools/migrar_mantis_gitlab/destination_writer.py:381` | **NO** | El migrador tiene su propio eje (§6.10) y corre en batch: hacerlo estricto abortaría migraciones enteras por un usuario faltante |
| `tests/test_gitlab_provider.py:260-264` | **NO se rompe** | Testea `_resolve_assignee_id` devolviendo el id; sigue igual |

**Por eso el cambio NO va en `_resolve_assignee_id`.** Cambiar su `except: pass` para que propague
alteraría los otros dos llamadores en silencio — el mismo error de "arreglar arriba y romper al lado" que
este plan denuncia.

**Cambio exacto (v2):** agregar un helper hermano y usarlo **sólo** en `update_item_assignee`.
```python
def _resolve_assignee_id_strict(self, username: str) -> int:
    """Como _resolve_assignee_id (:162) pero DICE por qué falló.
    Es un metodo NUEVO: _resolve_assignee_id (:162-169) queda BYTE-IDENTICO
    porque lo consumen :396 y el migrador (destination_writer.py:381)."""
    uid = self._resolve_assignee_id(username)          # reusa, no duplica
    if uid is None:
        raise TrackerApiError(f"usuario GitLab no resuelto: '{username}'", 404)
    return uid
```
y en `update_item_assignee` distinguir los dos casos que hoy están colapsados:
- `assignee` vacío/`None` → intención explícita de desasignar → `assignee_ids: []`. **Se conserva.**
- `assignee` con valor **que no resuelve** → `_resolve_assignee_id_strict` lanza **antes** de armar
  `update_body`. Nunca se manda `[]`.

Actualizar el docstring de `:507`: hoy dice "Si no se encuentra, limpia assignees", que documenta el bug
como si fuera la feature.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan282_assignee_no_borra.py`
1. `test_username_valido_asigna` — camino feliz.
2. `test_username_vacio_desasigna_a_proposito` — `assignee=""` → `assignee_ids: []`. **Congela la
   intención legítima.**
3. `test_username_que_no_resuelve_lanza_y_no_manda_body` — asserta que se lanzó `TrackerApiError` **y**
   que `_request` **no fue llamado en absoluto**. Las dos cosas: sin el segundo assert, el test pasa
   aunque el borrado siga ocurriendo antes de lanzar.
   > `TrackerApiError(mensaje, status)` — el `status` es **posicional obligatorio**.
4. `test_fallo_transitorio_de_users_no_desasigna` — `/users` lanza dentro de `_resolve_assignee_id` (que
   lo traga y devuelve `None`) → el **strict** lo convierte en `TrackerApiError`, y `_request` de update
   no se llama. **Ojo:** no esperes que se propague la excepción original; `:168-169` la traga y eso **no
   se cambia** (ver radio de impacto).
5. `test_ado_no_cambia` — congela el camino ADO.
6. **`test_los_otros_dos_llamadores_no_cambian`** *(nuevo en v2)* — `_resolve_assignee_id` con un username
   que no existe sigue devolviendo **`None`** (no lanza). Es el gate que prueba que el radio de impacto se
   respetó: si alguien "arregla" `:162` en vez de agregar el strict, este test se pone rojo.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan282_assignee_no_borra.py -v
./venv/Scripts/python.exe -m pytest tests/test_plan282_assignee_no_borra.py --collect-only -q | tail -3
```
**Criterio BINARIO:** 6 verdes y `--collect-only -q` reporta **exactamente 6 seleccionados**. Además
`tests/test_gitlab_provider.py` mantiene su conteo de fallos previo (delta cero).

**Flag:** `STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED`, **default ON**.
Justificación del ON: **reduce** la escritura al sistema del operador (deja de emitir un PUT destructivo).
Una flag que quita una escritura destructiva no puede nacer OFF sin dejar el destrozo encendido de fábrica.

**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno. Cambio de comportamiento visible: donde antes el issue quedaba
silenciosamente sin asignar, ahora aparece un error con el username que no se pudo resolver.

---

### F4 — Un solo diccionario de rótulos, consumido por toda la app

**Objetivo:** que ningún rótulo visible diga "ADO" cuando el tracker del proyecto no es ADO.

**Valor:** cierra K2. Es el frente de fluidez más grande en superficie: **118 rótulos medidos, 40 de ellos
ruteables**, y el #1 del ranking —`shellNav.ts:18` (vía `AppSidebar.tsx:33`) + `App.tsx:455`— está en
pantalla el 100% del tiempo **contradiciendo el título de la propia página**, que desde el 276 ya dice
"Tickets GitLab" (`TicketBoard.tsx:1103`).

**Archivo a editar:** `Stacky Agents/frontend/src/lib/trackerLabels.ts`
Ya existe y ya exporta `nombreDeTracker`, `tituloDeTickets`, `accionSincronizar`. **Extenderlo, no crear
otro helper.** Símbolos exactos a agregar:

```ts
/** Prefijo de referencia de un item. ADO usa "ADO-123"; GitLab usa "#123"
 *  (la notacion que el propio GitLab muestra); el resto cae a "<Nombre>-123". */
export function refDeTicket(tipo: string | null | undefined, id: number | string): string

/** "Abrir en Azure DevOps ↗" | "Abrir en GitLab ↗" | "Abrir en el tracker ↗" */
export function accionAbrirEn(tipo: string | null | undefined): string

/** "Publicar comentario en ADO" | "... en GitLab" — usado por FinishWorkButton. */
export function accionPublicarComentario(tipo: string | null | undefined): string

/** "Estado destino en ADO (opcional)" | "Estado destino en GitLab (opcional)" */
export function etiquetaEstadoDestino(tipo: string | null | undefined): string

/** Sugerencias de estado de cierre POR TRACKER. ADO: Done/Closed/Resolved/Active.
 *  GitLab: las 4 claves logicas reales de services/gitlab_provider.py:152-160
 *  (functional/accepted/rejected/in_progress). Nunca sugerir estados que el
 *  tracker del operador no tiene. */
export function sugerenciasDeEstadoFinal(tipo: string | null | undefined): string[]

/** [ADICION ARQUITECTO A3] Rotulo del tab, ruteado por tracker, SIN tocar TAB_META.
 *
 *  Por que existe: TAB_META (components/shell/shellNav.ts:16) es un
 *  `Record<ShellTab, ShellTabMeta>` congelado por CUATRO suites
 *  (shellNav.test.ts:19 `Object.keys(TAB_META)`, :36-37 `TAB_META[t].label`,
 *  shellIcons.test.ts:7-8, shellIconsCoverage.test.ts:11) y consumido por
 *  App.tsx:310 (`TAB_META[t]?.label`). Convertirlo en funcion rompe las cuatro.
 *
 *  Contrato: para "tickets" devuelve tituloDeTickets(tracker); para cualquier
 *  otro tab devuelve el label estatico que reciba. NUNCA lee TAB_META por su
 *  cuenta (funcion pura, sin imports de shell). */
export function labelDeTab(
  tab: string,
  labelEstatico: string,
  tracker: string | null | undefined,
): string
```

**Nota de fidelidad obligatoria:** `sugerenciasDeEstadoFinal("gitlab")` DEBE devolver exactamente las 4
claves lógicas de `_state_map_for_gitlab` (`services/gitlab_provider.py:152-160`), no una lista inventada.
El test 3 de abajo lo congela contra el backend.

**Archivos a editar (cablear el helper) — lista EXACTA, en este orden:**

| # | archivo:línea | qué reemplaza |
|---|---|---|
| 1 | `frontend/src/components/shell/AppSidebar.tsx:33` (**NO `shellNav.ts:18`** — C6) | `const meta = TAB_META[t]` → sigue igual, pero el render usa `labelDeTab(t, meta.label, trackerType)`. **`TAB_META` no se toca:** lo congelan 4 suites y lo consume `App.tsx:310` |
| 2 | `frontend/src/App.tsx:455` | `📋 Tickets ADO` → `📋 {tituloDeTickets(trackerType)}` (shell v1) |
| 3 | `frontend/src/components/commandPaletteData.ts:74` | `"Ir a Tickets ADO"` → `` `Ir a ${tituloDeTickets(t)}` `` |
| 4 | `frontend/src/pages/TicketBoard.tsx:499` | `ADO-{ticket.ado_id}` → `refDeTicket(tt, ticket.ado_id)` |
| 5 | `frontend/src/pages/TicketBoard.tsx:844` | ídem (chip de épica) |
| 6 | `frontend/src/pages/TicketBoard.tsx:1245` | ídem (banner en ejecución) |
| 7 | `frontend/src/pages/TicketBoard.tsx:175` | ídem (subtítulo modal Run) |
| 8 | `frontend/src/pages/TicketBoard.tsx:732` | `Abrir en Azure DevOps ↗` → `accionAbrirEn(tt)` |
| 9 | `frontend/src/pages/TicketBoard.tsx:1270` | placeholder `"…o ADO-ID…"` → ruteado |
| 10 | `frontend/src/components/SyncStatusBar.tsx:58` | `Sincronizando con ADO…` → `` `Sincronizando con ${nombreDeTracker(tt)}…` `` |
| 11 | `frontend/src/components/FinishWorkButton.tsx:225` | `Publicar comentario en ADO` → `accionPublicarComentario(tt)` |
| 12 | `frontend/src/components/FinishWorkButton.tsx:229` | `Estado destino en ADO (opcional)` → `etiquetaEstadoDestino(tt)` |
| 13 | `frontend/src/components/FinishWorkButton.tsx:236` + `<datalist>` **`:241-246`**, opciones **`:242-245`** | placeholder + las **4** `<option>` (`Done`/`Closed`/`Resolved`/`Active`) → `sugerenciasDeEstadoFinal(tt).map(...)`. **v1 decía `242-244` y dejaba `Active` (`:245`) colgando**, contradiciendo su propio test 4 (C16) |
| 14 | `frontend/src/components/FinishWorkButton.tsx:139` | `ADO-{ticket.ado_id}` → `refDeTicket(...)` |
| 15 | `frontend/src/components/TicketSelector.tsx:59,107` | tooltip + ref |
| 16 | `frontend/src/components/TicketGraphView.jsx:99,380,443` | ref + `Abrir en ADO ↗` |
| 17 | `frontend/src/components/CreateChildTaskButton.tsx:167,200,204,219,299` | "en ADO" → ruteado |
| 18 | `frontend/src/components/AgentHistoryModal.tsx:142,166,168` | ref + tooltip + link |
| 19 | `frontend/src/components/ExecutionDetailDrawer.tsx:336,337,339` | `ADO ID:` + ref + link |
| 20 | `frontend/src/components/EmptyState.tsx:46` | lista de trackers: **agregar GitLab, que hoy falta** |
| 21 | `frontend/src/services/peekModel.ts:106,121` | `"Estado ADO"` + título |
| 22 | `frontend/src/services/entityActions.ts:114,120,121,161,169,182,187` | menú contextual |
| 23 | `frontend/src/services/copyFormats.ts:75` | `- Estado ADO:` en el markdown copiado |
| 24 | `frontend/src/components/EmployeeCard.tsx:76` | ref |
| 25 | `frontend/src/components/AgentLaunchModal.tsx:385` | ref |

**De dónde sale `trackerType` — PINEADO en v2 (C7).** v1 decía "reusar esa misma fuente", que no es una
instrucción: **`App.tsx` no tiene `trackerType` en ninguna de sus líneas**. La fuente exacta, y la única
que se usa:

```ts
// Patrón vivo en TicketBoard.tsx:957 y :960 (Plan 276 F7). Tipo: Project | null
// declarado en frontend/src/store/workbench.ts:26.
const trackerType = useWorkbench((s) => s.activeProject?.tracker_type ?? null);
```

- **`App.tsx`**: agregar exactamente esa línea junto a `const sections = useUiSectionsStore(...)`
  (**`:93`**). Sirve para F4 ítem 2 y para F7.
- **`AppSidebar.tsx`**: misma línea; el componente ya es React.
- **`commandPaletteData.ts`** es un módulo de datos sin contexto React: **cambiar la constante exportada
  por una función que reciba el tracker** y que el consumidor (`CommandPalette.tsx`) le pase el valor
  leyéndolo del mismo selector. **No** introducir un store global nuevo.
- **`shellNav.ts` NO se toca** (ver ítem 1 de la tabla y [A3]).

**Test PRIMERO:** `Stacky Agents/frontend/src/lib/__tests__/trackerLabels.test.ts`.
**Verificado en v2:** el directorio `src/lib/__tests__/` **existe** (contiene `costCenter.logic.test.ts` y
`costCharts.logic.test.ts`) y **`trackerLabels.test.ts` NO existe** ⇒ **crearlo** (v1 dejaba la duda —
C17). Casos:
1. `refDeTicket("azure_devops", 1234) === "ADO-1234"` — **congela ADO primero**.
2. `refDeTicket("gitlab", 1115) === "#1115"`.
3. `sugerenciasDeEstadoFinal("gitlab")` es exactamente `["functional","accepted","rejected","in_progress"]`.
4. `sugerenciasDeEstadoFinal("azure_devops")` es exactamente `["Done","Closed","Resolved","Active"]`
   (las 4 `<option>` reales de `:242-245`).
5. Tracker desconocido / `null` / `undefined` → nunca devuelve "ADO". Cae a "Tracker".
6. `accionAbrirEn("gitlab") === "Abrir en GitLab ↗"`.
7. **`labelDeTab("tickets", "Tickets ADO", "gitlab") === "Tickets GitLab"`** *(nuevo, [A3])*.
8. **`labelDeTab("devops", "DevOps", "gitlab") === "DevOps"`** — un tab no-tickets pasa el label estático
   sin tocarlo. Sin este caso, `labelDeTab` podría reescribir todo y el test 7 igual pasaría.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/lib/__tests__/trackerLabels.test.ts --testTimeout=60000
npx vitest run src/components/shell/__tests__/shellNav.test.ts --testTimeout=60000
npx vitest run src/components/__tests__/commandPaletteDevopsActions.test.ts --testTimeout=60000
npx tsc --noEmit
```
**Criterio BINARIO:** los **8** casos pasan, `tsc --noEmit` sale **0**, `shellNav.test.ts` sigue **verde
sin editarlo** (es el gate de que `TAB_META` no se rompió), y el censo de F0 deja `ruteables` **vacío**.

**ADVERTENCIA para el implementador — cuatro trampas reales de este repo (v1 nombraba una, y mal):**
- **`TAB_META` es intocable.** Lo congelan `shellNav.test.ts:19` (`Object.keys(TAB_META).sort()`),
  `:36-37` (`TAB_META[t].label` / `.iconName` no vacíos), `shellIcons.test.ts:7-8` y
  `shellIconsCoverage.test.ts:11`; y lo consume `App.tsx:310` como `TAB_META[t as keyof typeof TAB_META]?.label`.
  Convertirlo en función pone **4 suites en rojo** y viola el DoD de delta cero. Por eso [A3].
- **La ruta del test del command palette que v1 daba NO EXISTE.** Es
  `frontend/src/components/__tests__/commandPaletteDevopsActions.test.ts` (v1 decía
  `frontend/src/services/__tests__/`). Un modelo menor buscaría ahí, no lo encontraría, y dejaría el rojo.
  Ese test **se actualiza en el mismo commit**. Verificá también
  `frontend/src/components/__tests__/commandPaletteData.test.ts`, que vive al lado.
- `TicketGraphView.jsx` es **`.jsx`, no `.tsx`**: `tsc --noEmit` **NO lo cubre**. Su única verificación es
  el smoke manual. Tocalo con cuidado y anotalo en el smoke de F8.
- Un rojo de vitest puede ser **sólo timeout**: por eso `--testTimeout=60000`, y **por archivo** (vitest
  contamina por orden de ejecución en este repo).

**Flag:** `STACKY_TRACKER_LABELS_GLOBAL_ENABLED`, **default ON**. Solo lectura y presentación: jamás es
excepción.
**Impacto por runtime:** ninguno (frontend puro, agnóstico).
**Trabajo del operador:** ninguno.

---

### F5 — El link deja de apuntar al tracker de otro cliente

**Objetivo:** eliminar la URL de ADO con org y proyecto hardcodeados.

**Valor:** cierra K4. Esto **no es cosmética**: "Abrir en ADO" y "Copiar link ADO" del menú contextual, en
un proyecto GitLab, mandan al operador a `dev.azure.com/UbimiaPacifico/Strategist_Pacifico` — la
organización de **otro cliente**. Es un link roto que además filtra el nombre de un tercero.

**Evidencia:** `frontend/src/utils/trackerUrls.ts:11` (verificado en v2 — la línea es exacta)
```ts
return `https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/${adoId}`;
```
**Consumidores REALES: 3, no 4 (C12).** `grep -rn "adoUrl" frontend/src` da:
| archivo:línea | qué hace |
|---|---|
| `services/peekLinks.ts:20` | `if (t.ado_id > 0) return adoUrl(String(t.ado_id));` |
| `services/copyFormats.ts:79` | `` `- Enlace: ${t.ado_url ?? adoUrl(String(t.ado_id))}` `` |
| `components/StructuredOutput.tsx:103` | `url={adoUrl(adoId)}` |
| ~~`StructuredOutput.tsx:78`~~ | **NO es un consumidor**: es `const CITATION_RE = ...` (el regex que detecta `ADO-XXXX` en texto). Se deja como está; linkificar `ADO-1234` sólo tiene sentido en proyectos ADO y `:103` ya se protege con el `null` |

**TEST AJENO QUE ESTE CAMBIO ROMPE — v1 no lo nombraba (C12):**
`frontend/src/services/__tests__/copyFormats.test.ts:94` —
*"13 — ticketToMarkdown: ado_url gana; fallback adoUrl; sin description sin cuerpo"*. Asserta justamente
el fallback que F5 elimina. **Se actualiza en el mismo commit**, igual que el del command palette en F4.

**Cambio exacto:** `adoUrl(adoId)` pasa a devolver `string | null` y **solo** construye la URL si recibe
la org y el proyecto reales. Firma nueva:
```ts
export function urlDeTicket(
  tracker: { type: string; ado_url?: string | null; organization?: string; project?: string },
  id: string | number,
): string | null
```
Regla de resolución, en este orden: (1) si el ticket trae `ado_url` del backend, **usarlo tal cual** — el
backend ya construye las URLs GitLab vía `gitlab_deep_links.py`; (2) si el tracker es ADO y hay `organization`
y `project` en la config del proyecto, construirla; (3) si no, **devolver `null`**.

Los **3** consumidores deben manejar `null` **ocultando la acción**, no renderizando un link muerto:
- `peekLinks.ts:20` → si `null`, no ofrecer la entrada "Abrir".
- `copyFormats.ts:79` → si `null`, omitir la línea `- Enlace:` del markdown.
- `StructuredOutput.tsx:103` → si `null`, dejar el texto **sin linkificar** (no un `<a href="null">`).

**Backward-compat de la firma:** `adoUrl(adoId: string): string` se **conserva exportada** y pasa a
delegar en `urlDeTicket`, para no romper importadores que aparezcan en las ramas paralelas 280/281. Se
marca `@deprecated` con una línea que apunta a `urlDeTicket`. Borrarla es trabajo de un barrido posterior,
no de este plan.

**Test PRIMERO:** `Stacky Agents/frontend/src/utils/__tests__/trackerUrls.test.ts`
1. Ticket GitLab con `ado_url` del backend → devuelve ese mismo string.
2. Ticket GitLab **sin** `ado_url` → `null`. **Nunca** una URL `dev.azure.com`.
3. Ticket ADO con org+project → la URL correcta con ESA org, no la hardcodeada.
4. Ticket ADO **sin** org configurada → `null`.
5. Guarda anti-regresión: `readFileSync` de `trackerUrls.ts` **no contiene** la subcadena
   `"UbimiaPacifico"`. Assert de ausencia **precedido** por un assert positivo sobre un string sintético
   que sí la contiene, para probar que el detector detecta.

**Comando:** `npx vitest run src/utils/__tests__/trackerUrls.test.ts --testTimeout=60000` + `npx tsc --noEmit`
**Criterio BINARIO:** 5 casos verdes, `tsc` 0, y `grep -c UbimiaPacifico frontend/src/utils/trackerUrls.ts` = **0**.

**Flag:** `STACKY_TRACKER_URLS_ROUTED_ENABLED`, **default ON**. Solo lectura.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno. **Nota:** si un proyecto ADO no tiene `organization` en su config, la
acción "Abrir en ADO" desaparece en vez de mandar a una org ajena. Es una mejora, y F8 lo verifica.

---

### F6 — El filtro "Solo abiertos" deja de ser ciego en GitLab

**Objetivo:** que el filtro y el color de estado funcionen con el vocabulario del tracker activo.

**Valor:** fricción **funcional**, no cosmética. Hoy `CLOSED_STATES` (`TicketBoard.tsx:98`) es
`["Done","Closed","Resolved","Removed","Completed"]` y `ADO_STATE_COLORS` (**`:87-96`**; v1 decía `87-97`
y `:97` está en blanco) solo conoce estados ADO. En GitLab (`opened`/`closed`) el filtro no filtra nada y
**todos los badges caen al gris**.

**Archivo a crear:** `Stacky Agents/frontend/src/lib/trackerEstados.ts` (lógica pura, sin React).

```ts
/** True si el estado es terminal EN ESE TRACKER. ADO: Done/Closed/Resolved/
 *  Removed/Completed. GitLab: 'closed' (y las claves stacky::accepted/rejected,
 *  que services/gitlab_provider.py:152-160 marca con closed:true).
 *  Comparacion CASE-INSENSITIVE: GitLab devuelve minusculas. */
export function esEstadoCerrado(estado: string | null | undefined, tracker: string | null | undefined): boolean

/** Color del badge por estado y tracker. Nunca devuelve undefined. */
export function colorDeEstado(estado: string | null | undefined, tracker: string | null | undefined): string
```

**Archivos a editar — LOS CALL SITES, UNO POR UNO (v2; v1 daba un anclaje equivocado y una frase vaga, C11):**

`frontend/src/pages/TicketBoard.tsx` — borrar las dos constantes locales (`:87-96` y `:98`) e importar del
helper. Los consumidores reales, obtenidos con `grep -n "CLOSED_STATES\|ADO_STATE_COLORS"`:

| línea | qué es | cómo queda |
|---|---|---|
| `:110` | `return ADO_STATE_COLORS[state] ?? "#6b7280";` | `return colorDeEstado(state, trackerType);` — la función que lo contiene debe recibir el tracker |
| `:354` | `const isClosed = CLOSED_STATES.includes(ticket.ado_state ?? "")` | `esEstadoCerrado(ticket.ado_state, trackerType)` |
| `:438` | `closedStates: CLOSED_STATES` → se pasa a **`canResolveWithAgent`** (`incidents/devResolverModel.ts`) | **Contrato ajeno que v1 ignoraba.** Ese modelo espera una **lista**, no un predicado. Pasarle `sugerenciasDeEstadoCerrado(trackerType)` (lista por tracker) y **no** cambiar la firma de `canResolveWithAgent` |
| `:795` | `const isClosed = CLOSED_STATES.includes(epic.ado_state ?? "")` | `esEstadoCerrado(epic.ado_state, trackerType)` |
| `:1078` | `if (onlyPending && CLOSED_STATES.includes(node.ado_state ?? "")) return false;` | **ESTE es el filtro "Solo abiertos" del árbol** (v1 anclaba en `:1159`, que es el `<input type="checkbox">`) |
| `:1094` | `.filter((t) => !CLOSED_STATES.includes(t.ado_state ?? ""))` | **ESTE es el filtro de la lista plana** |

`frontend/src/components/TicketGraphView.jsx`:
- **`:47-57`** `STATE_COLORS` (v1 decía `48-55`, que **parte el objeto al medio y deja `"Removed"` colgando**
  ⇒ error de sintaxis silencioso en un `.jsx` que `tsc` no cubre).
- **`:322`** `const isClosed = ["Done","Closed","Resolved","Removed","Completed"].includes(ticket.ado_state);`
  — el array literal duplicado.
Ambos al helper.

**Nota de alcance:** `colorDeEstado` y `esEstadoCerrado` necesitan el tracker en funciones que hoy no lo
reciben (`:110`). Propagarlo por **parámetro explícito**, nunca por variable de módulo: `TicketBoard.tsx`
tiene el valor en `:960` y esas funciones viven en el mismo archivo.

**Test PRIMERO:** `Stacky Agents/frontend/src/lib/__tests__/trackerEstados.test.ts`
1. `esEstadoCerrado("Done","azure_devops")` → true. **ADO primero.**
2. `esEstadoCerrado("Active","azure_devops")` → false.
3. `esEstadoCerrado("closed","gitlab")` → true.
4. `esEstadoCerrado("Closed","gitlab")` → true (case-insensitive).
5. `esEstadoCerrado("opened","gitlab")` → false.
6. `esEstadoCerrado("Done","gitlab")` → **false**. Un estado ADO no cierra un ticket GitLab.
7. `esEstadoCerrado(null, "gitlab")` → false, no lanza.
8. `colorDeEstado("opened","gitlab")` !== `colorDeEstado("closed","gitlab")` — prueba que GitLab dejó de
   caer todo al mismo gris. **Este es el assert que prueba el arreglo, no la ausencia de error.**

**Comando:** `npx vitest run src/lib/__tests__/trackerEstados.test.ts --testTimeout=60000` + `tsc --noEmit`
**Criterio BINARIO:** 8 casos verdes, `tsc` 0.

**Flag:** `STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED`, **default ON**. Solo lectura/presentación.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno.

---

### F7 — Las pantallas ADO-only dejan de ser callejones sin salida

**Objetivo:** que un proyecto GitLab no vea entradas de menú que, al abrirlas, dicen "solo disponible
para proyectos Azure DevOps".

**Valor:** cierra K5. Hoy el tab **PM** se muestra por `sections.pm` (`App.tsx:382`) sin mirar el tracker,
se presenta como *"Fase 1 MVP · sin IA · azure_devops únicamente"* (`PMCommandCenter.tsx:995`), ofrece
**"↻ Sync ADO"** (`:1004`), y al pulsarlo el backend responde *"PM Intelligence Suite v1 solo está
disponible para proyectos Azure DevOps"* (`backend/api/pm.py:71`). Es un callejón sin salida ofrecido en
el menú. Igual: **Sprint Board** (`SprintBoardPage.tsx:144-146`) y **User Stats**
(`UserStatsPage.tsx:104,139`).

**Corrección de anclaje (C13).** v1 derivaba la lista de "`api/pm.py:71` y `api/pm.py:1171`".
**`:1171` NO es un guard**: es `"message": "No hay sprint activo en el proyecto. Configurá iteraciones en
ADO."`. El guard real de todo `api/pm.py` es el patrón
`if tracker.get("type", "azure_devops") != "azure_devops":` y aparece **10 veces** —
`:105, 291, 340, 380, 542, 926, 999, 1052, 1143` (`:1143` es el del sprint) — más el helper que arma la
respuesta 400 en `:68-73`. **El blueprint entero es ADO-only**, no dos endpoints sueltos.

**Archivo a crear:** `Stacky Agents/frontend/src/lib/tabsPorTracker.ts` (lógica pura).
```ts
/** Tabs que HOY solo funcionan con Azure DevOps. La lista NO se inventa: se
 *  deriva del guard del backend `tracker.get("type","azure_devops") != "azure_devops"`,
 *  que en api/pm.py aparece 10 veces (:105,291,340,380,542,926,999,1052,1143)
 *  y devuelve TRACKER_NOT_SUPPORTED via el helper de :68-73.
 *  Los 3 tabs del frontend que consumen ESE blueprint son estos. */
export const TABS_SOLO_ADO = ["pm", "sprint", "userstats"] as const;

/** True si el tab debe ofrecerse para ese tracker. */
export function tabDisponible(tab: string, tracker: string | null | undefined): boolean

/** Motivo legible para el tooltip cuando NO esta disponible. Nunca vacio. */
export function motivoNoDisponible(tab: string, tracker: string | null | undefined): string
```

**Comportamiento exacto (importa, no lo cambies):** el tab **no se borra de la navegación**, se muestra
**deshabilitado con tooltip explicativo** (*"El Command Center de PM requiere Azure DevOps; este proyecto
usa GitLab"*). Razón: **los gates de tab que nacen `false` matan el deep link** — es un defecto conocido y
documentado de este repo. Deshabilitar-con-motivo preserva la ruta y explica; ocultar rompe el enlace
directo y no explica nada.

**Archivos a editar:**
- `frontend/src/App.tsx:382` — la decisión de render del tab PM consulta `tabDisponible`.
- `frontend/src/components/shell/shellNav.ts` — los 3 tabs llevan el estado deshabilitado + tooltip.
- `frontend/src/pages/PMCommandCenter.tsx:995` — el subtítulo `"azure_devops únicamente"` pasa a ser el
  motivo ruteado; si el proyecto ES ADO, el texto no cambia.

**Test PRIMERO:** `Stacky Agents/frontend/src/lib/__tests__/tabsPorTracker.test.ts`
1. `tabDisponible("pm","azure_devops")` → true. **ADO primero.**
2. `tabDisponible("pm","gitlab")` → false.
3. `tabDisponible("tickets","gitlab")` → true (no rompas los tabs normales).
4. `tabDisponible("pm", null)` → **true** (sin proyecto no se esconde nada; falla abierto).
5. `motivoNoDisponible("pm","gitlab")` menciona "GitLab" y no está vacío.
6. Sentinela de contrato: `TABS_SOLO_ADO` tiene exactamente 3 entradas. Si alguien agrega un tab
   ADO-only, este test lo obliga a declararlo acá.
7. **`tabDisponible("pm","azure_devops") === true` con `TABS_SOLO_ADO` vacío daría `true` también** ⇒
   guarda anti-falso-verde: `tabDisponible("pm","gitlab")` **debe** ser `false` **y** el test 6 fija el
   tamaño de la lista. Sin las dos, un `TABS_SOLO_ADO = []` pasaría el 1, el 3 y el 4.

**Comando:** `npx vitest run src/lib/__tests__/tabsPorTracker.test.ts --testTimeout=60000` + `tsc --noEmit`
**Criterio BINARIO:** **7** verdes, `tsc` 0, y en el smoke de F8 los 3 tabs aparecen deshabilitados con
tooltip en un proyecto GitLab.

**Flag:** `STACKY_ADO_ONLY_TABS_GATED_ENABLED`, **default ON**. Presentación pura.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno; deja de perder tiempo entrando a pantallas que no le sirven.

---

### F8 — Gate de cierre, registro de flags y smoke manual

**Objetivo:** dejar el plan verificable de una sola corrida y las **7 flags nuevas** visibles en la UI del arnés.

**F8.1 — Registro de las 7 flags nuevas.** Cada flag es un **bloque atómico**; si falta una pata, la flag
queda registrada pero muerta y **el gate igual pasa**. Los lugares, con el patrón exacto que ya usa
`STACKY_GITLAB_DEEP_LINKS_ENABLED`:

| # | archivo | qué agregar |
|---|---|---|
| 1 | `backend/config.py` | **la forma REAL, verificada en `:1979-1981`** — no es `= os.getenv(...)` a secas: `NOMBRE: bool = os.getenv("NOMBRE", "true").lower() in ("1", "true", "yes")`. Sin el `.lower() in (...)` la flag queda siendo el **string** `"true"` y `bool("false")` es `True`. **El default EFECTIVO es este**, no el del registry |
| 2 | `backend/services/harness_flags.py` — bloque de categoría, hoy en **`:453`** | la clave en la lista de categoría |
| 3 | `backend/services/harness_flags.py` — bloque de specs, hoy en **`:4266`** | el `FlagSpec(key=..., default=True, type="bool", ...)` |
| 4 | `backend/services/harness_flags.py` | `_CATEGORY_KEYS` — sin esto el panel no la muestra |
| 5 | `deployment/harness_defaults.env` — hoy `:206` | la línea `NOMBRE=true` |
| 6 | el consumidor real | `config.config.NOMBRE` en el código de la fase — **`config.config`, la INSTANCIA**, no el módulo (patrón vivo en `tracker_provider.py:133,141`) |

**Los 6 números de arriba son referencias, no destinos.** Anclá **por SÍMBOLO**: en los tres puntos de
`harness_flags.py` y en `config.py`, insertá **inmediatamente después del bloque de
`STACKY_GITLAB_DEEP_LINKS_ENABLED`**, que es el patrón que este plan copia. Los números de línea van a
haber corrido cuando implementes.

**COSTURA COMPARTIDA CON 280 Y 281 — declarada en v2 (C14).** Los tres planes escriben **a la vez** en
`backend/config.py`, `backend/services/harness_flags.py` (3 puntos) y `deployment/harness_defaults.env`.
Es la frontera de merge más caliente del árbol. Reglas:
- **Predeclaración de nombres.** Este plan reserva exactamente estos 7 y **ningún otro**:
  `STACKY_COMMENT_PUBLISH_ROUTED_ENABLED`, `STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED`,
  `STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED`, `STACKY_TRACKER_LABELS_GLOBAL_ENABLED`,
  `STACKY_TRACKER_URLS_ROUTED_ENABLED`, `STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED`,
  `STACKY_ADO_ONLY_TABS_GATED_ENABLED`. Antes de escribir: `grep -n "<NOMBRE>" backend/services/harness_flags.py`
  para confirmar que otra sesión no lo tomó.
- **Bloque contiguo.** Las 7 van juntas, en un solo bloque por punto de inserción, con un comentario
  `# Plan 282 — paridad GitLab` arriba. Un bloque contiguo se resuelve como un conflicto; 7 inserciones
  dispersas se resuelven como 7.
- **Verificación post-merge obligatoria**: `git 3-way NO marca conflicto si dos ramas agregan la misma
  línea de cierre a un objeto ya existente`. Después de cualquier merge con 280/281, correr
  `python -m compileall backend/config.py backend/services/harness_flags.py` y
  `grep -c "STACKY_COMMENT_PUBLISH_ROUTED_ENABLED" backend/services/harness_flags.py` esperando **2**
  (categoría + spec). Un 3 o un 4 es un duplicado silencioso.

**Trampa conocida:** el gate de ayuda de flags exige la cadena **`"Si "` SIN TILDE** en el texto de ayuda.
Y `test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes**: el criterio de aceptación es
**delta cero**, no "verde absoluto" — contá los fallos antes y después y exigí el mismo número.
Idem `test_harness_env_read_meta` (1 rojo ajeno). **Medí los rojos ANTES de tocar nada** y anotá los dos
números en este doc; sin la foto previa no hay delta.

**F8.2 — Gate ejecutable con exit code.** Crear
`Stacky Agents/backend/scripts/gate_plan282.py`, que corre y devuelve:
- `exit 0` — los 6 KPI en meta.
- `exit 2` — algún KPI fuera de meta (imprime cuál y su valor).
- `exit 5` — **no se pudo medir** (falta backend levantado, o no hay proyecto GitLab configurado). Un
  gate que no puede medir **no debe reportar verde**.

**F8.3 — Smoke manual (requiere backend levantado + token GitLab del operador).** Pasos numerados, con el
resultado esperado de cada uno. Esto **no** se automatiza: requiere credenciales reales.
1. Abrir un proyecto GitLab. La pestaña dice **"Tickets GitLab"** en las dos shells (v1 y v2).
2. Las tarjetas rotulan **`#1115`**, no `ADO-1115`.
3. Marcar "Solo abiertos": la lista **cambia** (hoy no cambia).
4. Menú contextual → "Copiar link": pega una URL de **GitLab**, no de `dev.azure.com`.
5. Cerrar trabajo: el checkbox dice **"Publicar comentario en GitLab"** y el `<datalist>` sugiere las 4
   claves lógicas, no `Done/Closed/Resolved`.
6. Correr un agente hasta el final: la ejecución queda **`completed`** (no `error`) y el comentario
   **aparece en el issue de GitLab**.
7. Reintentar la publicación: **no** aparece un segundo comentario (idempotencia de F1).
8. Los tabs PM / Sprint Board / User Stats están **deshabilitados con tooltip**, y su deep link directo
   sigue aterrizando.
9. Abrir el mismo flujo en un proyecto **ADO**: todo se comporta **exactamente como antes**.

**F8.4 — Huella de regresión (NUEVA en v2 — C15).** El plan hermano 280 tiene su F6 de huella; v1 de este
plan no tenía ninguna. Agregar **una** entrada a `Stacky Agents/docs/sistema/error_fingerprints.json`.

**Schema REAL, verificado abriendo el archivo y su schema-test** (no el que dictan otros planes):
- El archivo es un **dict** `{schema_version, description, fingerprints: [...]}` — **no** una lista suelta.
- Claves **requeridas** de cada huella (`tests/test_error_fingerprints_catalog.py:18`):
  `id`, `title`, `class`, `status`, `log_pattern`, `log_guarded`, `killed_by`, `guard_test`, `self_test`.
  Opcionales en uso: `killed_commit`, `date_resolved`, `evidence`, `note`.
- **`_STATUS_ENUM = {"resolved", "open", "by_design"}`** (`:17`). **`"guarded"` NO está en el enum**:
  usarlo pone el schema-test en rojo.
- `self_test` es `{matches: [...], clean: [...]}`. `guarded_fingerprints()`
  (`services/error_fingerprints.py:26-29`) sólo alarma con `status=="resolved" and log_guarded is True`.

Entrada a agregar:
```json
{
  "id": "plan282-comentario-no-llega-al-tracker-gitlab",
  "title": "El comentario del agente se genero y quedo en disco: el publicador es ADO-only",
  "class": "silent-write-loss",
  "status": "resolved",
  "log_pattern": "ADO client build failed.*no usa Azure DevOps",
  "log_guarded": true,
  "killed_by": "plan 282 F1",
  "killed_commit": null,
  "date_resolved": "2026-08-01",
  "guard_test": "tests/test_plan282_publicacion_comentario.py",
  "self_test": {
    "matches": ["ERROR ado_publisher ADO client build failed: AdoConfigError: El proyecto 'RIPLEY' no usa Azure DevOps (tracker_type=gitlab)."],
    "clean": ["INFO ado_publisher publish ok tracker=gitlab item=1115 comment_id=99"]
  }
}
```

**Criterio BINARIO de F8.4 — delta cero, no verde absoluto.** El catálogo **ya está ROJO DE FÁBRICA**:
tiene **57** huellas y **1 con `status:"guarded"`**, fuera del enum. Corré
`./venv/Scripts/python.exe -m pytest tests/test_error_fingerprints_catalog.py -v` **antes** de agregar la
entrada, anotá el número de fallos, y exigí **el mismo número después**. Y correr
`tests/test_error_fingerprints_scan.py`, que verifica que cada huella `resolved+guarded` **matchea sus
`matches` y NO matchea sus `clean`**: si el `log_pattern` de arriba no distingue, el test lo dice.
**No "arregles" la huella ajena con `guarded`**: es deuda de otro plan.

---

**Criterio BINARIO de F8:** `gate_plan282.py` sale **0** (o **5** documentado); `run_harness_tests` con los
**4** archivos backend nuevos registrados en **ambos** ratchets no introduce ningún rojo nuevo (delta cero
contra el commit base, contado antes y después); `tsc --noEmit` sale 0; el catálogo de huellas mantiene su
conteo de fallos previo; y los 9 pasos del smoke se marcan uno por uno en el propio doc del plan.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **F1 depende del plan 280.** Sin él la ejecución queda `error`, el gate `agent_completion_internal.py:233-234` saltea el publish, y K1 **no se puede medir en vivo** | El test de F1 fuerza `final_status="completed"` y prueba el publicador **aislado**: el router se verifica sin depender del 280. El KPI en vivo se mide en el smoke (F8.3 paso 6) y, si el 280 no está, `gate_plan282.py` sale **exit 5** (no medible), nunca 0. **Un gate que no puede medir no reporta verde** |
| R2 | **F1 duplica comentarios** en el issue del operador | `comment_exists(item_id, marker)` obligatorio antes de publicar; F1 caso 3 lo congela. Precedente directo: la épica duplicada de esta semana nació de publicar sin chequear |
| R3 | **F4 y F5 rompen tests ajenos** — `components/__tests__/commandPaletteDevopsActions.test.ts:109-110` congela los rótulos viejos, y `services/__tests__/copyFormats.test.ts:94` congela el fallback `adoUrl` que F5 elimina | Los dos están declarados en su fase: se actualizan **en el mismo commit**. No son rojos ajenos, son parte del cambio. **La ruta del primero la corrigió v2**: v1 lo ubicaba en `services/__tests__/`, donde no existe |
| R4 | **F4 toca 25 sitios**: riesgo de romper el render | Los helpers son funciones puras testeadas antes de cablearse; `tsc --noEmit` cubre todo salvo `TicketGraphView.jsx` (`.jsx`, no tipado) — por eso está en el smoke manual paso 2 |
| R5 | **F2 import circular** `tracker_provider` ↔ `gitlab_provider` | Import **dentro de la función**, patrón ya usado en `tracker_provider.py:141` |
| R6 | **F3 rompe un flujo que dependía del borrado silencioso** | F3 caso 2 conserva el desasignar explícito (`assignee=""`). Solo cambia el caso "no resuelve", que hoy es un bug |
| R7 | **F7 mata deep links** (defecto conocido: los gates de tab nacen `false`) | Por eso **deshabilitar con tooltip**, no ocultar. Caso 4: sin proyecto, falla **abierto**. Smoke paso 8 verifica que el deep link aterriza |
| R8 | **El working tree tiene archivos sin commitear** de otras sesiones, varios del dominio de este plan (`api/tickets.py`, `uiGuards.ts`, `EpicFromBriefModal.tsx`, y **los dos ratchets** `run_harness_tests.sh`/`.ps1`) | F0 se corre **antes** de tocar nada y anota el `git status` de partida en el doc. **PROHIBIDO** `git stash`, `reset`, `checkout --`, `amend`, `rebase`: ese diff es el fix vivo de la épica duplicada. Los ratchets ya están modificados por otra sesión — agregá tus líneas **sin** revertir las suyas |
| R9 | **Tres sesiones paralelas** sobre el MISMO worktree (`N:` ↔ `C:\desarrollo` son el mismo dir por junction) escribiendo 280, 281 y este | **No abrir rama nueva** (mueve el HEAD de las otras sesiones). Commitear con `git commit -m "..." -- "<ruta>"` para no barrer ajenos. Antes de commitear: `git worktree list` + `git log`. **Colisión detectada:** existen DOS archivos `280_*` (ver §6.16) |
| R10 | **Todo test de DB es flaky** por `SQLITE_LOCKED` | Los tests de F1 usan la sesión de test del repo, no la DB viva. **Nunca** correr pytest sin `DATABASE_URL`: un pytest suelto escribe en la base real del operador (193 MB) |
| R11 | **El censo de F0 cuenta comentarios** y da falsos positivos (el código está en español) | El filtro descarta líneas de comentario **y** el test tiene una guarda que prueba que el detector detecta antes de assertar ausencia |
| R12 | **El censo de F0 por AST da CERO si la llamada va por alias** y premia el bug | `_rutea_por_tracker` censa por **REFERENCIA** (`ast.Name` y `ast.Attribute`), no por `ast.Call`. Y el criterio de F0 exige **reproducir primero la foto vieja** (4 backend / 40 ruteables frontend) antes de activar los asserts verdes |
| R13 | **F1 explota con `TypeError` en la primera corrida real**: `ado_publisher.py:469` pasa 3 posicionales y el provider GitLab acepta 2 | El router devuelve un **adaptador** que define la firma ([A1]), y el caso 7 de F1 la congela por `inspect.signature` con guarda anti-falso-verde. Riesgo **cerrado por construcción**, no por disciplina |
| R14 | **F4 pone 4 suites en rojo** al convertir `TAB_META` en función, violando el DoD de delta cero | `TAB_META` **no se toca**; se agrega `labelDeTab` ([A3]) y el criterio de F4 exige que `shellNav.test.ts` quede **verde sin editarlo** |
| R15 | **F3 rompe a los otros 2 llamadores de `_resolve_assignee_id`** (`gitlab_provider.py:396`, `tools/migrar_mantis_gitlab/destination_writer.py:381`) — el migrador abortaría corridas enteras por un usuario faltante | El cambio va en un helper **nuevo** (`_resolve_assignee_id_strict`) usado sólo por `update_item_assignee`; el caso 6 de F3 congela que `_resolve_assignee_id` **sigue devolviendo `None`** |
| R16 | **Colisión de costura con 280 y 281** en `config.py`, `harness_flags.py` y `harness_defaults.env`; y `git` 3-way **no marca conflicto** si dos ramas agregan la misma línea de cierre | F8.1: 7 nombres predeclarados, bloque **contiguo**, anclaje **por símbolo** (tras `STACKY_GITLAB_DEEP_LINKS_ENABLED`) y verificación post-merge con `compileall` + `grep -c` esperando exactamente 2 por flag |
| R17 | **El KPI K2 se declara verde midiendo un universo distinto al que arregla** (el defecto de v1: techo 96→≤20 inalcanzable por 58) | K2 pasa a censo **particionado** con meta `{}` en el conjunto ruteable + sentinela de tamaño de la allowlist. Y F0 exige **calibrar contra el número medido**, no contra el número escrito |

---

## 6. Fuera de scope (declarado, para no perderlo)

**Cubierto por el plan 281 (sesión paralela):** el error literal `no usa Azure DevOps` en ticket-grafo, su
intermitencia, el censo por AST de sitios ADO-only con esa firma, y el contrato de ruteo de esos sitios.
**Dependencia blanda:** si el 281 unifica `project_context.py:340-343`, F1 se simplifica pero no cambia de
contrato.

**FRONTERA RE-VERIFICADA EN v2 (no heredada del v1):**
- `grep -n "ado_publisher\|post_comment\|agent_completion_internal\|comment_publish"` sobre
  `281_PLAN_EL_RUTEO_POR_TRACKER_DEJA_DE_MENTIR.md` → **0 hits**. El 281 **no toca el publicador**. ✔
- Los 8 sitios de la F7 del 281 son: `api/agents.py:1798`, `api/tickets.py:4912`, **`api/tickets.py:7564`**,
  `services/acceptance_criteria.py:25`, `business_preflight.py:37`, `self_review.py:43`,
  `similar_tickets.py:91`, `ticket_assigner.py:356`. Los **7** que §6.14 rechaza son esos menos
  `api/tickets.py:7564` (que es el autopublicador de épica, dominio del 278/280). **No queda trabajo
  huérfano ni duplicado.** ✔
- El plan **280 §G7** declara vedados, para sí mismo: `services/epic_autopublish.py`, `api/tickets.py`,
  `frontend/src/services/uiGuards.ts`, `frontend/src/components/EpicFromBriefModal.tsx`,
  `tests/test_epic_from_brief_idempotencia.py`, `tests/test_plan276_gitlab_sync.py`,
  **`scripts/run_harness_tests.sh`**, **`.ps1`**, `frontend/src/api/endpoints.ts`, `docs/281_*`, `docs/282_*`.
  Este plan **sí** debe escribir en los dos ratchets (F0): son crecimiento aditivo al final de un bloque,
  no edición de líneas ajenas. `api/tickets.py` queda **vedado también para este plan** (C10). ✔
- El 280 tiene **F6 — Huella de regresión**; este plan la agrega en **F8.4** (C15). Sin solape: distinta
  `class`, distinto `log_pattern`, distinto `guard_test`. ✔

**Ya implementado, no re-planificar:** la idempotencia de `epics/from-brief` (working tree,
`api/tickets.py:8052-8070`) y el guard `sealedWorkItemId` (`frontend/src/services/uiGuards.ts:78`).

**Deliberadamente fuera de este plan:**

1. **El debounce del `output_watcher`** (`output_watcher.py:66-67`: 2 s / 30 s, hardcodeados y ausentes de
   `harness_defaults.env`). Tocarlo cambia el timing de TODAS las corridas, ADO incluidas. El defecto
   medido es el **pisado**, no el debounce. Candidato natural al plan siguiente, junto con el
   `.stacky-done.json` (el bypass determinista que existe en `:62` y que los agentes no escriben).
2. **El bug del stall watchdog de Codex**: `_codex_on_runaway_with_stall` (`codex_cli_runner.py:704-706`)
   **nunca se cablea**, así que el "watchdog de inactividad" es en realidad un reloj de pared duro de
   600 s desde el arranque. Es un defecto real, propio y aislable — merece su propio plan.
3. **`fetch_epics` en GitLab**: es la **única** operación que existe en ADO (`ado_provider.py:487`) y no en
   GitLab. Requiere épicas nativas de grupo (GitLab **Premium**), que el operador no tiene. Ya declarado
   fuera por 276 §7 y 277 §6.
4. **Los silencios de lectura de GitLab**: `fetch_item_updates` (`gitlab_provider.py:556-606`, tres
   `except: pass` ⇒ historial vacío mudo), `fetch_attachments` (`:486-495`, regex sobre la descripción +
   `except: return []`), `fetch_all_comments` (`:436`, idéntico a `fetch_comments`, no pagina), y
   `find_child_by_marker` (`:524-552`, devuelve el PADRE como proxy). Son degradaciones **de lectura**:
   molestan menos que el cierre y la publicación, y son 4 fases más. Van al plan siguiente.
5. **La `CAPABILITY_MATRIX` está STALE**: `services/provider_capabilities.py:94` declara verificación al
   2026-07-25 y `gitlab_provider.py` cambió el 07-31; toda la columna GitLab tiene las líneas corridas
   ~115. Re-verificarla es un trabajo de censo propio, no un subproducto de este plan.
6. **La asimetría `auth_file` vs `ca_bundle`** (`project_manager.py:663-677`): vaciar `auth_file`
   **conserva**, vaciar `ca_bundle` **borra**. **No es un bug ciego** — el docstring en `:655-661` lo
   documenta como decisión deliberada. Lo que falta es el hint en la UI. Es un ítem de una línea que no
   justifica una fase; anotado para el barrido de config.
7. **`initialize_gitlab_project` es constructor, no merge** (`project_manager.py:668-677`): pisa cualquier
   clave de `issue_tracker` que no esté en su lista fija. Es la **misma clase de trampa** que
   `_rebuild_tickets_table_if_needed` en `db.py`, que el 277 parcheó y declaró viva. Merecen un plan
   conjunto de "listas hardcodeadas que se comen los campos nuevos".
8. **La advertencia de `base_url` con namespace pegado**: el anclaje heredado `EditProjectModal.tsx:722`
   está **muerto** (hoy es el bloque de Mantis). El campo vive en `:736`, sin nota de ayuda. La
   normalización silenciosa (`:239` → `newProjectGitlabModel.ts:37-41`) y la validación dura del backend
   (`gitlab_client.py:95-99`) ya lo contienen: el operador no se rompe, solo no se entera temprano.
   Prioridad baja.
9. **Los 2 motores de probe** (`api/global_config.py:349-405` global vs
   `services/local_diagnostics.py:217` por proyecto): divergen a propósito (uno prueba el `.env`, el otro
   el proyecto). `connection_doctor.py:253` **ya consolidó** la parte por proyecto. Lo que falta es que la
   UI diga cuál de los dos corrió. Ítem de UI, no de arquitectura.
10. **`REQUESTS_CA_BUNDLE` global** en `tools/migrar_mantis_gitlab/destination_writer.py:238` — ensucia el
    entorno del proceso entero, justo lo que `gitlab_client.py:143-145` advierte. El migrador tiene su
    propio eje.
11. **Renombrar `ado_id` / `ado_state` / `ado_url`** — migración de esquema, fuera por 276 §7 **y** 277 §6.
    Este plan los deja intactos y solo cambia **cómo se rotulan**.
12. **Sync automático, webhooks, techo de 4.000 issues, Jira y Mantis** — fuera por los planes previos.
13. **El plan 272 nunca escrito**: 270 y 271 le delegaron la unificación de los 6 escritores de estado, el
    `_origin_guard` del motor B y el vocabulario GitLab de `_state_map_for_gitlab`. Sigue huérfano. Este
    plan **consume** las 4 claves lógicas (F4), no las amplía.
14. **RECHAZO EXPLÍCITO del pase del plan 281 §7** — *"construir el equivalente GitLab de los 7 sitios que
    F7 degrada a valor neutro"*: criterios de aceptación (`services/acceptance_criteria.py:25`),
    self-review (`services/self_review.py:43`), similar tickets (`services/similar_tickets.py:91`),
    auto-assign (`services/ticket_assigner.py:356`), business preflight
    (`services/business_preflight.py:37`), enriquecimiento de contexto (`api/agents.py:1798`) y estado
    equivalente de tarea (`api/tickets.py:4912`). **Razón del rechazo:** son **7 features nuevas de
    GitLab**, no arreglos de paridad de algo que ya existe. Sumadas al alcance actual, este plan pasaría
    de 9 fases quirúrgicas a ~16 y dejaría de ser implementable por un modelo menor — que es exactamente
    lo que el encargo prohíbe. Además, el propio 281 las degrada a un valor neutro **honesto**: hoy esos
    7 sitios ya devuelven ese mismo valor por su `except`, así que el 281 no empeora nada y este plan no
    tiene urgencia que justifique tomarlas. **Candidatos naturales al plan siguiente**, en orden de valor:
    similar tickets y auto-assign (los dos que el operador nota) antes que los cinco restantes.
15. **RECHAZO del pase del 281 §7 sobre `ado_sync` y polling** — el breaker `"ado_sync"` usado con key de
    proyecto GitLab (`api/tickets.py:6430`) y la cadencia de `GET /api/tickets` que late a ~8 s por
    colisión de `queryKey` entre `TicketBoard.tsx:987-993` y `useRunningStatus.ts:51-61`. Son problemas
    de **performance y naming**, no de paridad ni de fluidez percibida. Van a un plan de rendimiento.
16. **COLISIÓN DE NUMERACIÓN DETECTADA — no la resuelve este plan, pero queda anotada.** Al momento de
    escribir existen **dos archivos con el número 280**:
    `docs/280_PLAN_EL_DESENLACE_MIRA_EL_TRABAJO_ENTREGADO_UN_SOLO_VEREDICTO.md` (tracked, modificado) y
    `docs/280_PLAN_CALENDARIO_DE_REUNIONES_TEAMS_MINUTAS_Y_PENDIENTES_ACCIONABLES.md` (untracked). Son dos
    planes distintos de dos sesiones distintas. **Requiere decisión del operador**: uno de los dos debe
    renumerarse. Este plan tomó el 282 pinneado y **no renumera nada por su cuenta**.

---

## 7. Glosario

- **Tracker** — sistema de tickets externo. Stacky soporta `azure_devops`, `gitlab`, `jira`, `mantis`.
- **Provider** — adaptador que traduce el puerto `TrackerProvider` (`services/tracker_provider.py:76-118`,
  18 métodos) a la API de un tracker concreto.
- **`ado_id`** — nombre histórico del identificador del item **en cualquier tracker**. En GitLab guarda el
  `iid` (el número que ve el operador), no el `id` global. El nombre es legado; renombrarlo está fuera.
- **`output_watcher`** — daemon que vigila los archivos de salida del agente y cierra la ejecución cuando
  se estabilizan (Modo A: `pending-task.json`, 30 s; Modo B: `comment.html`, 2 s).
- **`_mark_terminal`** — función de cada runner CLI que escribe el estado final de la ejecución.
- **Chokepoint** — punto único por el que pasan los 3 runtimes; acá es
  `services/agent_completion_internal.py`.
- **Estado terminal** — `completed`, `error`, `cancelled`, `needs_review`. Lo opuesto a `ACTIVE_STATUSES`
  (`preparing`, `running`, `queued`).
- **Ratchet** — script que congela un censo para que no empeore. Hay uno `.sh` y uno `.ps1`, **con
  sintaxis distinta**, y todo test nuevo va en los **dos** — o dentro de un archivo ya registrado.
- **Flag del arnés** — interruptor en `services/harness_flags.py` cuyo default **efectivo** vive en
  `config.py`. El comentario del registry puede mentir; leé el `os.getenv`.

---

## 8. Orden de implementación

Las fases ya están escritas en el orden en que se implementan. Bloque backend primero (F1-F3), bloque
frontend después (F4-F7), cierre al final (F8).

1. **F0** — los dos censos, en su versión "rojo esperado". **No avanzar sin ver: 4 constructores
   (backend), `App.tsx` presente en el detalle del censo frontend, y el detector de `ado_publisher`
   reportando "no rutea".** El baseline de ruteables (**40**) y el tamaño de la allowlist (**23**) son
   números **medidos**: si no reproducen, **recalibralos con lo medido y anotá el delta acá** — v1 mandaba
   a "arreglar" el censo contra un número (96) que era el equivocado y frenaba la implementación entera.
   Lo que **no** se recalibra es la presencia de `App.tsx`: si no aparece, el regex está mal.
2. **F1** — router de publicación de comentarios. **Es el de mayor valor del plan.** Se puede implementar
   y testear sin el plan 280; solo su KPI en vivo lo necesita (R1).
3. **F2** — fábrica única. Backend, independiente de todo lo demás.
4. **F3** — assignee estricto. Backend, independiente.
5. **F4** — rótulos. El más largo (25 sitios): entrar con el helper **ya testeado**, no tocar `TAB_META`
   ([A3]), y actualizar `components/__tests__/commandPaletteDevopsActions.test.ts:109-110` en el mismo
   commit (**`components/`**, no `services/`).
6. **F5** — URLs. Depende de F4 (comparte consumidores en `entityActions` y `copyFormats`).
7. **F6** — estados y filtros.
8. **F7** — tabs gateados.
9. **F8** — flags, gate y smoke.

**Corte válido si hay que parar antes de terminar:** F0 → F1 → F8.1/F8.2 entrega el frente de mayor valor
(el trabajo llega al issue de GitLab) de forma cerrada y verificable. F2-F7 son aditivas e independientes
entre sí; ninguna deja el sistema a medio camino si no se hace.

## 9. Definición de Hecho (DoD)

- [ ] Los 6 KPI (K1-K6) en meta, medidos por `backend/scripts/gate_plan282.py` con **exit 0** — o
      **exit 5** documentado si K1 no se puede medir en vivo por falta del plan 280 (R1). Nunca exit 0
      con un KPI sin medir.
- [ ] **K2 medido como partición**, no como techo: `ruteables === {}` y `LEGITIMOS` con 23 entradas, todas
      con motivo no vacío. El baseline (40) fue **recalibrado contra la medición real** antes de arrancar
      y el delta quedó anotado en este doc.
- [ ] Los **9 archivos de test** nuevos (4 backend + 5 frontend) existen, pasan, y el conteo exacto de
      casos de cada uno está **escrito en este doc** (no "todos verdes"): F0 backend 2 · **F1 7** ·
      F2 4 · **F3 6** · F0 frontend 4 · **F4 8** · F5 5 · F6 8 · **F7 7**. `--collect-only -q` confirma el
      número de seleccionados en los 4 de backend.
- [ ] Los tests backend nuevos están registrados en **`run_harness_tests.sh` Y `run_harness_tests.ps1`**.
- [ ] `run_harness_tests` no introduce ningún rojo nuevo: **delta cero** contra el commit base, contado
      antes y después (el repo tiene rojos ajenos preexistentes; "verde absoluto" no es el criterio).
- [ ] `npx tsc --noEmit` sale **0**.
- [ ] Las **7 flags nuevas** (`STACKY_COMMENT_PUBLISH_ROUTED_ENABLED`,
      `STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED`, `STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED`,
      `STACKY_TRACKER_LABELS_GLOBAL_ENABLED`, `STACKY_TRACKER_URLS_ROUTED_ENABLED`,
      `STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED`, `STACKY_ADO_ONLY_TABS_GATED_ENABLED`) tienen sus
      **6 patas**, **todas nacen ON**, y aparecen en el panel de Configuración → Arnés.
- [ ] `test_harness_flags_help.py` (4 rojos ajenos) y `test_harness_env_read_meta` (1) mantienen su conteo
      de fallos **preexistente**, sin sumar ninguno. La foto previa está anotada en este doc.
- [ ] **F8.4**: la huella `plan282-comentario-no-llega-al-tracker-gitlab` existe con el schema REAL
      (`status="resolved"`, **nunca `"guarded"`**), y `test_error_fingerprints_catalog.py` +
      `test_error_fingerprints_scan.py` mantienen su conteo de fallos previo (el catálogo ya está rojo).
- [ ] **`TAB_META` no fue modificado**: `shellNav.test.ts`, `shellIcons.test.ts` y
      `shellIconsCoverage.test.ts` pasan **sin haber sido editados** (`git diff --stat` sobre ellos = vacío).
- [ ] Los **3 tests ajenos que este plan SÍ actualiza** están en el mismo commit y verdes:
      `components/__tests__/commandPaletteDevopsActions.test.ts` (F4),
      `components/__tests__/commandPaletteData.test.ts` si aplica (F4), y
      `services/__tests__/copyFormats.test.ts` (F5).
- [ ] **`api/tickets.py` NO fue tocado** (vedado por el plan 280 §G7 y con cambios sin commitear de otra
      sesión): `git diff --stat -- "Stacky Agents/backend/api/tickets.py"` no muestra líneas de este plan.
- [ ] `PublishResult` ganó **sólo** el campo `error_kind: str | None = None`, con default, al final del
      dataclass, y **la tabla `agent_html_publish` no cambió de esquema**.
- [ ] Los 9 pasos del smoke manual (F8.3) marcados uno por uno, incluido el **paso 9** (un proyecto ADO se
      comporta exactamente como antes).
- [ ] Ningún archivo de `Stacky Agents/docs/280_*` ni `281_*` fue tocado.
- [ ] Los archivos modificados por otras sesiones al inicio siguen intactos o fueron commiteados por su
      dueño: **no** se ejecutó `git stash`, `reset`, `checkout --`, `amend` ni `rebase`. En particular,
      las líneas que otra sesión ya agregó a `run_harness_tests.sh` y `.ps1` **siguen ahí**.
- [ ] Ninguna fase de este plan modificó `services/claude_code_cli_runner.py`, `codex_cli_runner.py` ni
      `services/run_outcome.py`: **esa capa es del plan 280** y tocarla es un conflicto de merge.
- [ ] Sin `git push` (el push es siempre manual).
