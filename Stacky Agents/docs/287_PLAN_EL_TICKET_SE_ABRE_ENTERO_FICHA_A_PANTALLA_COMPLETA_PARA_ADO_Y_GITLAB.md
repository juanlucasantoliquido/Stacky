# Plan 287 — El ticket se abre entero: una ficha a pantalla completa, la misma para Azure DevOps y para GitLab

**Estado:** MEJORADO (v1 → **v2**) — reescrito por el juez adversarial el 2026-08-02
**Veredicto de la crítica v1:** **RECHAZADO** (6 bloqueantes). La v2 los salda; el veredicto de la v2 queda para su propio juez.
**Fecha:** 2026-08-02
**Rama al escribir:** `docs/plan-279`
**Alcance:** frontend (una ficha nueva) + backend (dos lecturas que ya existen en el puerto y nadie expuso). Cero migraciones de datos. Cero caminos de escritura nuevos. Cero tabs nuevos.
**Antecesores directos que se reusan, no se re-implementan:** 164 (primitiva `Dialog`), 165 (router tipado), 218 (puerto `TrackerProvider` + matriz de capacidades), 265 (precedente de pantalla completa), 277 (jerarquía y `motivo_huerfano`), 281/286 (ruteo por proyecto, nunca por la columna).

> **Los anclajes `archivo:línea` se re-verificaron abriendo los archivos el 2026-08-02, DESPUÉS de los 6 commits del plan 286 de la sesión paralela.** De 116 anclajes: **99 correctos, 16 desplazados** (corregidos en esta v2) y **1 inexistente heredado del repo** (§C9). Los conteos se midieron ejecutando `grep -c` / `pytest` / `vitest`, no se estimaron. Donde un número puede correrse, el documento da además la instrucción por **símbolo** (§4.3).

---

## CHANGELOG v1 → v2

| # | Severidad | Qué se corrigió |
|---|---|---|
| **C1** | BLOQUEANTE | `_normalizar_update` era inimplementable: **los dos adaptadores devuelven formas sin una sola clave en común** y el plan no daba el mapeo, así que las 5 claves salían `None` en ADO **y** en GitLab. La v2 trae la **tabla de mapeo por tracker**, la firma `_normalizar_update(u, tracker)`, fixtures capturadas de las formas reales y el centinela **[ADICIÓN ARQUITECTO] F1.5** |
| **C2** | BLOQUEANTE | F0.1 declaraba **verdes** `uiDebtRatchet.test.ts` y `adhocModalRatchet.test.ts`. **Los dos están ROJOS DE FÁBRICA** (medido). Sus criterios en K7/K8/F6/F7/DoD eran insatisfacibles. Ahora están en §4.2 con la lista exacta de ofensores y los criterios son **delta** |
| **C3** | BLOQUEANTE | §3.1 afirmaba que la allowlist estaba "llena y sana"; está **rota** (2 detectados fuera + 1 stale). Y el import obligatorio `import Dialog from "../ui/Dialog"` **no satisface** `UI_DIALOG_IMPORT_RE`. Ahora se manda `import { Dialog } from "../ui"` y el gate usa la regex del detector |
| **C4** | BLOQUEANTE | El enlace directo `?ticket=` **no llegaba a la ficha**: `App.tsx:412` monta `<TicketBoard />` **sin props**. F7 suma `App.tsx` como 4º archivo, igual que el precedente `?exec=` (`App.tsx:421`) |
| **C5** | BLOQUEANTE | F4 **no compilaba**: `TicketNode` no declara `motivo_huerfano` y `types.ts` no estaba en ninguna fase. F4 lo agrega |
| **C6** | BLOQUEANTE | No se decía **cuál** árbol recibe la ficha, y el que está a mano (`displayHierarchy`) está **filtrado por "mías"**: navegar a un hermano ajeno daba ficha muda. Se congela `hierarchy` crudo y se agrega la regla del foco fuera del árbol |
| **C7** | IMPORTANTE | Dos tests de F2 pasaban **antes** del cambio. Salen del conteo de aceptación |
| **C8** | IMPORTANTE | El criterio delta de `test_harness_flags_help.py` no detectaba un `PLAIN_HELP` faltante (ya falla con 92 keys). Ahora el criterio va sobre el **cuerpo** del mensaje |
| **C9** | IMPORTANTE | La pérdida que la ficha le iba a mostrar al operador en GitLab **es falsa** y su anclaje apunta a otra función. F2 la corrige y la asserta por texto |
| **C10** | IMPORTANTE | `CreateChildTaskButton` es un popover de la allowlist montado dentro de un `Dialog` con trampa de foco: riesgo R13 + paso de humo |
| **C11/C12** | IMPORTANTE | 16 anclajes desplazados corregidos (incluidos los 3 de `api/tickets.py` sobre los que se pega el código) y la contradicción `:95` vs `:97` del glosario |
| **C13-C16** | MENOR | `TrackerDeepLink` es export nombrado · el gate `-riE` de F8.3 se acota a `src/` · huella de regresión · alcance de etiquetas/relaciones declarado |

---

## 1. Objetivo y KPI

### 1.1 Objetivo

Hoy **Stacky no tiene vista de detalle de ticket**. El click sobre un ticket solo despliega la misma tarjeta hacia abajo (`Stacky Agents/frontend/src/pages/TicketBoard.tsx:498-501` y `Stacky Agents/frontend/src/components/TicketGraphView.jsx:398`). Para leer un ticket entero — descripción, comentarios, adjuntos, historial, hijos — el operador tiene que abandonar Stacky e irse a Azure DevOps o a GitLab.

Este plan construye **una sola ficha de ticket a pantalla completa**, idéntica para los dos trackers, que:

1. se abre con **un click** desde donde el ticket ya se ve (tablero de tarjetas y grafo),
2. muestra **toda** la información útil en tres columnas de densidad alta, sin ruido,
3. permite **navegar la jerarquía** (padre, hijos, hermanos) **sin cerrarse ni perder el contexto**,
4. **dice cuándo no puede mostrar algo y por qué** — que es exactamente lo que ni la vista de work item de Azure DevOps ni la de issue de GitLab hacen,
5. reúne ahí mismo las acciones que **ya existen**, cada una conservando su confirmación explícita.

### 1.2 La tesis, medida

**La información ya está del lado del servidor. Lo que falta es la pantalla que la junte.** Cinco mediciones del 2026-08-02:

| Lo que existe | Dónde | Quién lo consume en la interfaz |
|---|---|---|
| `GET /tickets/<id>` (detalle + `executions[]`) | `backend/api/tickets.py` — decorador `@bp.get("/<int:ticket_id>")` **`:1291`**, `def get_ticket` **`:1292`** | **1 sitio**, y es un auto-relleno: `Stacky Agents/frontend/src/hooks/useAutoFillBlocks.ts:22` |
| `GET /tickets/<id>/comments`, **ya ruteado por provider** | `backend/api/tickets.py` — `def get_comments` **`:1568`** | **1 sitio**: `Stacky Agents/frontend/src/components/AgentLaunchModal.tsx:168` |
| `GET /tickets/<id>/attachments`, **ya ruteado por provider** | `backend/api/tickets.py` — `def get_attachments` **`:1605`** | **3 sitios**, los tres selectores de archivo |
| `fetch_item_updates` (historial de cambios), en el puerto y en **los dos** adaptadores | `Stacky Agents/backend/services/tracker_provider.py:96`, `services/ado_provider.py:137`, `services/gitlab_provider.py:606` | **0** — no tiene ruta HTTP. `grep -rn "fetch_item_updates" api/*.py` → **0 hits** |
| Matriz de capacidades por proveedor, con la pérdida escrita capacidad por capacidad | `CAPABILITY_MATRIX`, `Stacky Agents/backend/services/provider_capabilities.py:95` | **0** — `grep -rn "provider_capabilities\|capability_status\|capability_loss" api/*.py` → **0 hits** |
| `motivo_huerfano` (por qué un ticket no cuelga de su épica), calculado en cada respuesta de jerarquía | `Stacky Agents/backend/api/tickets.py:718`, emitido en `:810` | **0** — `grep -rn "motivo_huerfano" frontend/src/` → **0 hits**. El propio docstring lo admite: *"nadie la lee todavía"* (`api/tickets.py:754`) |

### 1.3 KPI — todos binarios, todos con comando

| # | KPI | HOY (medido 2026-08-02) | Meta del 287 | Comando que lo mide |
|---|---|---|---|---|
| **K0** | Fichas de detalle de ticket a pantalla completa | **0** | **1** | `ls "Stacky Agents/frontend/src/components/ticket/TicketFullView.tsx"` |
| **K1** | Clicks para ver, sin salir de Stacky, descripción + comentarios + adjuntos + hijos + padre de un ticket | **imposible: no existe la pantalla** | **1** | smoke §9.2 |
| **K2** | Sitios que consumen `Tickets.byId` fuera de `api/endpoints.ts` | **1** | **≥ 2** | `grep -rn "Tickets.byId(" frontend/src \| grep -v api/endpoints.ts \| wc -l` |
| **K3** | Sitios que consumen `Tickets.comments` fuera de `api/endpoints.ts` | **1** | **≥ 2** | `grep -rn "Tickets.comments(" frontend/src \| grep -v api/endpoints.ts \| wc -l` |
| **K4** | Métodos de lectura de detalle del puerto `TrackerProvider` con ruta HTTP viva, de 3 (`fetch_comments`, `fetch_attachments`, `fetch_item_updates`) | **2 de 3** | **3 de 3** | `grep -c "fetch_item_updates" "Stacky Agents/backend/api/tickets.py"` ≥ 1 |
| **K5** | Consumidores de la matriz de capacidades desde la interfaz | **0** | **≥ 1** | `grep -rn "capacidades" frontend/src/api/endpoints.ts \| wc -l` ≥ 1 |
| **K6** | Consumidores de `motivo_huerfano` en la interfaz | **0** | **≥ 1** | `grep -rn "motivo_huerfano" frontend/src \| wc -l` ≥ 1 |
| **K7** | Colores hex nuevos en el CSS que agrega este plan | — | **0** | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` — **DELTA**: mismas 5 regresiones de §4.2, ni una más (el archivo está **rojo de fábrica**, §4.2/C2) |
| **K8** | Entradas nuevas en `adhocModalAllowlist.json` | 11 de `FROZEN_MAX = 11`, pero **el ratchet ya está ROJO**: 2 detectados fuera + 1 stale | **0** (queda en 11) | `npx vitest run src/__tests__/adhocModalRatchet.test.ts` — **DELTA**: mismos 3 ofensores de §4.2, ni uno más |
| **K9** | Sitios nuevos ADO-only en el servidor | `violaciones_count: 0` (`backend/tests/ado_only_baseline.json`) | **0** | `pytest tests/test_plan281_ratchet_ado_only.py` |
| **K10** | Gates de pantalla en `App.tsx` (`useState<GateState>("unknown")`) | **8** | **8** — este plan **no agrega ninguno** | `grep -c 'useState<GateState>("unknown")' "Stacky Agents/frontend/src/App.tsx"` |
| **K11** | Saltos de jerarquía posibles desde la vista de un ticket | **0** | padre + N hijos + N hermanos, con tope 50 | `npx vitest run src/services/__tests__/ticketDetailModel.test.ts` |

---

## 2. Por qué ahora, y qué gap cierra respecto de los planes recientes

- El **276** trajo GitLab self-hosted de punta a punta, el **277** unificó la jerarquía, el **281** y el **286** erradicaron el ruteo por la columna que miente, y el **282** hizo que la pantalla hable el idioma del tracker. Después de esa serie **el dato ya llega bien**: hay tickets de los dos trackers, con padre, con estado, con comentarios y con adjuntos.
- Lo que quedó sin cerrar es el último tramo: **no hay dónde mirarlo junto**. El tablero es una lista de tarjetas; el grafo es un mapa. Ninguno de los dos es una ficha.
- El **265** ya resolvió, para la consola, el problema técnico de "pantalla completa sobre la misma sesión" y dejó el patrón probado (`Stacky Agents/frontend/src/components/CodexConsoleFull.tsx`, 494 líneas, con toda la lógica extraída a nueve módulos `.ts` puros en `frontend/src/services/console*.ts`). Este plan **copia ese patrón**, no lo reinventa.
- El **218** dejó construida la matriz de capacidades con la pérdida escrita capacidad por capacidad, y nunca se expuso. Esa matriz es, literalmente, la diferencia entre "el panel está vacío" y "el panel está vacío **porque en GitLab los adjuntos se extraen por expresión sobre la descripción del issue**". Es la funcionalidad que ni ADO ni GitLab dan.

---

## 3. Principios y guardarraíles (obligatorios, se verifican en el DoD)

1. **Human-in-the-loop innegociable.** Este plan **no agrega ni un solo camino de escritura nuevo** al tracker. Las acciones que aparecen en la ficha son las que ya existen y **conservan su propia confirmación** (§6.F7). Cualquier acción de escritura nueva está **fuera de scope** (§8).
2. **Mono-operador, sin auth real.** No hay roles ni permisos. En este plan, `403` significa **flag apagada**, nunca permiso, y el cuerpo lo dice: `{"error": "feature_disabled"}`.
3. **Toda configuración del operador va por interfaz.** Las 3 flags de este plan son `env_only=False` y aparecen en el panel del arnés.
4. **Cross-tracker por construcción, nunca por bifurcación.** Prohibido leer `ticket.tracker_type` para decidir a quién preguntarle. El ruteo va por `get_tracker_provider(project)` (`Stacky Agents/backend/services/tracker_provider.py:125`), que es uno de los dos `PROVIDER_SEAMS` reconocidos por el auditor (`Stacky Agents/backend/services/provider_coupling_audit.py:130-132`). El ratchet `test_ningun_sitio_nuevo_lee_tracker_type_para_rutear` exige `vivos == []`: no hay tolerancia.
5. **Cero trabajo extra para el operador.** Las 3 flags nacen **ON** (§5). Ninguna cae en las dos categorías de excepción: **(A)** ninguna enciende loop, daemon, barrido, sondeo, prefetch ni llamada a modelo — todo es bajo demanda, disparado por el operador al abrir la ficha o un panel; **(B)** ninguna escribe en un sistema real, ninguna borra datos, ninguna decide por él.
6. **No degradar.** La ficha no monta ningún sondeo periódico. Las consultas son bajo demanda y se cachean con la clave de React Query correspondiente. El panel de historial **solo consulta al tracker cuando el operador lo abre** (`enabled:` de la query atado al panel visible).
7. **Español** en documento, nombres de símbolos nuevos del dominio, y todo texto visible al operador.
8. **`services/` no importa de `api/`.** El módulo nuevo de capacidades vive en `services/` y la ruta HTTP lo importa, nunca al revés.

### 3.1 La decisión arquitectónica central: **la ficha NO es un tab**

Esto no es una preferencia estética; está medido.

| Evidencia | Consecuencia |
|---|---|
| Un tab nuevo toca **10 archivos**: `services/routes.ts` (union `Tab` `:6-9` + `TAB_PATHS` `:15`), `components/shell/shellNav.ts` (`ShellTab` `:5`, `TAB_META` `:16`, `SHELL_NAV_GROUPS` `:44`, `VisibilityInput` `:52`, `ALWAYS_VISIBLE` `:66`, `computeVisibleTabs` `:70`), `components/shell/shellIcons.ts:9`, `App.tsx` (gate, sonda, redirección, render, botón de la barra v1), `components/commandPaletteData.ts:84`, `components/CommandPalette.tsx:122`, `lib/tabsPorTracker.ts:14` | 10 puntos de edición para una pantalla que **no tiene sentido sin un ticket elegido** |
| `components/shell/__tests__/shellNav.test.ts:19` congela *"TAB_META cubre exactamente los 19 tabs"* | Un tab nuevo obliga a tocar una suite ajena |
| `services/__tests__/plan273GateState.test.ts:86` espera **7** declaraciones `useState<GateState>("unknown")` y el conteo real en `App.tsx` es **8** (verificado: `grep -c 'useState<GateState>("unknown")' App.tsx` → `8`). Lo mismo en `:110` para `isGateResolving(` → real **8** | **Esas dos aserciones ya están ROJAS hoy**, antes de este plan. Un gate nuevo las deja en 9 y hace parecer que el rojo lo trajo el 287 |
| Los gates de `App.tsx` se resuelven **después** del primer pintado, vía `probeFlagHealth` (`App.tsx:183-209`) | Toda pantalla gateada arrastra el problema de orden de inicialización |

**Por eso la ficha es un recubrimiento a pantalla completa montado sobre el tablero**, con la primitiva `Dialog` en modo `bare` (`Stacky Agents/frontend/src/components/ui/Dialog.tsx:42-44`), que aporta portal + `role="dialog"` + Escape + trampa de foco + restauración de foco + bloqueo de scroll (`Dialog.tsx:52`, `:203`) sin imponer chrome visual.

**Y usar `Dialog` es lo que evita empeorar el ratchet de modales ad-hoc.** Su detector (`src/__tests__/adhocModalRatchet.test.ts:37`) marca todo `.tsx` que contenga `role="dialog"`, `aria-modal` o `createPortal(`, y lo perdona **solo** si matchea `UI_DIALOG_IMPORT_RE` (`:38-39`):

```js
const DETECT_RE = /role="dialog"|aria-modal|createPortal\(/;
const UI_DIALOG_IMPORT_RE = /import\s+\{[^}]*\bDialog\b[^}]*\}\s+from\s+["'][^"']*ui["']/;
```

> **C3 — dos correcciones duras de la v1, medidas el 2026-08-02:**
>
> 1. **La allowlist NO está "llena y sana": el ratchet ya está ROJO.** `FROZEN_MAX = 11` (`:35`) y hay 11 entradas, pero **2 modales ad-hoc detectados quedaron fuera** (`components/contextmenu/ContextMenu.tsx`, `components/peek/PeekCard.tsx`) y **1 entrada quedó stale** (`components/ShortcutsCheatsheet.tsx`, que ya no se detecta). Ver §4.2. La conclusión de la v1 (usar `Dialog`, no hacer un recubrimiento a mano) **sigue siendo la correcta**; la premisa "está verde y llena" no lo era.
> 2. **El import que la v1 mandaba NO satisface el escape del detector.** `import Dialog from "../ui/Dialog"` es un import **por defecto** desde una ruta que **termina en `Dialog`**; `UI_DIALOG_IMPORT_RE` exige **llaves** y una ruta que **termina en `ui`**. Hoy no rompe solo por accidente — `TicketFullView.tsx` no contendrá `role="dialog"` ni `createPortal(` propios, así que `DETECT_RE` no dispara —, pero el gate que la v1 congelaba (`grep -c 'from "../ui/Dialog"'` → 1) **no probaba nada** y cementaba la forma equivocada: el día que alguien agregue un `aria-modal="true"` a una ficha a pantalla completa, el archivo se detecta y **no hay lugar en la allowlist**.
>
> **Forma obligatoria (única aceptada en F6):**
> ```tsx
> import { Dialog } from "../ui";
> ```
> El barril lo exporta como nombrado en `src/components/ui/index.ts:38` (`export { default as Dialog } from "./Dialog";`). Verificado.

### 3.2 El enlace directo no puede morir

El operador tiene que poder pegar `…/?ticket=1234` y aterrizar en la ficha. Eso es exactamente lo que rompió el bug histórico de "los gates nacen en `false`" (documentado en `Stacky Agents/frontend/src/services/gateState.ts:3-11`). Acá **no puede pasar**, y hay dos razones independientes:

1. `parseRoute` corre **síncrono** en el `useState` inicial de `App.tsx:83-85`, antes de cualquier sonda de flag.
2. El interruptor de la ficha se lee con `readCachedBoolFlag` (`Stacky Agents/frontend/src/services/flagGate.ts:70`), que es **sincrónico** y **fail-open a ON** cuando no hay caché. No hay un tercer estado "todavía no sé".

Y el molde ya existe: `RouteState` **ya tiene** `exec?: number` para abrir el cajón de una ejecución (`services/routes.ts:29`), con su expresión estricta `/^\d+$/` (`:74`), su normalización de tab (`normalizeInitial`, `:88`) y su serialización (`:121`). El campo `ticket?: number` es su espejo exacto.

### 3.3 Paridad en los 3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro)

| Ítem | Codex CLI | Claude Code CLI | GitHub Copilot Pro | Fallback |
|---|---|---|---|---|
| Ficha, jerarquía, comentarios, adjuntos, historial, capacidades | Idéntico | Idéntico | Idéntico | **No aplica bifurcación**: la ficha lee del *tracker* y de la base local, no del motor que ejecuta agentes. Ningún símbolo de este plan nombra un runtime |
| Panel de ejecuciones del ticket (`executions[]` de `GET /tickets/<id>`) | Idéntico | Idéntico | Idéntico | La forma de `AgentExecution` (`frontend/src/types.ts:138-166`) es una sola para los tres; el motor concreto viaja dentro de `metadata` y la ficha **no ramifica por él**, solo lo muestra si está |
| Acciones reusadas (`FinishWorkButton`, `CreateChildTaskButton`, `JerarquiaLocalControl`, `TicketLocalInsightButton`) | Ya funcionan hoy en los 3 | Ídem | Ídem | Este plan **las mueve de lugar, no las modifica**: el comportamiento por runtime es el que ya tienen |

**Gate binario de esta sección (F8.3):** `grep -riE "codex|claude|copilot" ` sobre los 4 archivos nuevos del plan debe dar **0 hits**.

---

## 4. Glosario y reglas de lectura

### 4.1 Glosario

| Término | Qué es en este repositorio |
|---|---|
| **Tracker** | El sistema donde viven los tickets del proyecto: Azure DevOps o GitLab. Se resuelve **del proyecto**, nunca de la columna del ticket |
| **Puerto `TrackerProvider`** | El `Protocol` de `services/tracker_provider.py:76-96`. Define los métodos que los dos adaptadores implementan |
| **Seam / costura de proveedor** | `get_tracker_provider` y `_provider_for_ticket`. Son los dos nombres que el auditor de acoplamiento acepta como "esta función ya rutea bien" (`services/provider_coupling_audit.py:130-132`) |
| **Matriz de capacidades** | `CAPABILITY_MATRIX` en `services/provider_capabilities.py:95` (v1 decía `:97` acá y `:95` en §1.2; **manda `:95`**, verificado): por proveedor y por capacidad, un estado (`full` / `partial` / `absent` / `n/a`) y, si es `partial`, el texto de **qué se pierde** |
| **Ratchet** | Prueba que congela un número y solo lo deja bajar. Este plan cruza 4: deuda visual, modales ad-hoc, ADO-only y paridad de los dos scripts del arnés |
| **Ficha** | La pantalla nueva de este plan: el detalle completo de **un** ticket, a pantalla completa |
| **Foco** | El ticket que la ficha está mostrando en este momento. Cambia al navegar la jerarquía, sin cerrar la ficha |
| **Rojo de fábrica** | Prueba que ya falla en `main` antes de que este plan toque nada. Se declara para que nadie lo confunda con una regresión propia |

### 4.2 Rojos de fábrica declarados (medidos 2026-08-02, ANTES de tocar nada)

**Los 5 rojos de fábrica, todos EJECUTADOS el 2026-08-02 (no citados de otro plan):**

| Archivo | Salida real medida | Ofensores exactos (congelados: si aparece uno más, es de este plan) |
|---|---|---|
| `frontend/src/services/__tests__/plan273GateState.test.ts` | `2 failed \| 12 passed (14)` | `:86` espera 7 `useState<GateState>("unknown")`, real **8**; `:110` espera 7 `isGateResolving(`, real **8** (el 283 sumó `reuniones`). Deuda del 283 |
| **`frontend/src/__tests__/uiDebtRatchet.test.ts`** ⚠️ **la v1 lo declaraba VERDE** | `1 failed \| ... ` con **5 regresiones** | `hexByFile`: `components/ExecutionDetailDrawer.module.css` 23>21 · `components/RunReconciliationCard.module.css` 1>0. `inlineStyleByFile`: `components/docs/DocumenterButton.tsx` 3>1 · `components/docs/DocumenterResultPanel.tsx` 41>20 · `pages/DocsPage.tsx` 4>1 |
| **`frontend/src/__tests__/adhocModalRatchet.test.ts`** ⚠️ **la v1 lo declaraba VERDE** | `2 failed \| 2 passed (4)` | *ad-hoc fuera de la allowlist*: `components/contextmenu/ContextMenu.tsx`, `components/peek/PeekCard.tsx`. *entrada stale*: `components/ShortcutsCheatsheet.tsx` |
| `backend/tests/test_harness_flags_help.py` | `4 failed` de la suite (`4 failed, 72 passed` corriendo las 3 suites de flags juntas) | `test_plain_help_covers_all_registry_keys` (**92 flags sin ayuda llana**), `test_plain_help_fields_non_empty_and_bounded`, `test_plain_help_on_off_start_with_si`, `test_plain_help_avoids_jargon_denylist` |
| `backend/tests/test_error_fingerprints_catalog.py` | `3 failed, 5 passed` | `test_campos_obligatorios`, `test_status_enum`, `test_self_test_coherente` |

**Verdes de fábrica confirmados por ejecución** (estos SÍ tienen que seguir verdes): `test_plan281_ratchet_ado_only.py` + `test_plan259_ratchet_script_parity.py` + `test_harness_ratchet_meta.py` → **`27 passed`**; `test_harness_flags.py` y `test_harness_flags_requires.py` → verdes dentro del `72 passed`; `themeContrast.test.ts` → `4 passed`; `a11yCss.test.ts` → `3 passed`; `routes.test.ts` → **`17 passed`**; `routesDeepLink.test.ts` → **`6 passed`**; `npx tsc --noEmit` → **exit 0**.

**Regla de aceptación de este plan (C2 — DELTA, nunca absoluto):** ninguna prueba que hoy esté **verde** puede quedar roja, y **ningún rojo de fábrica puede sumar un ofensor nuevo**. El criterio NO es "el archivo pasa a verde" — eso es insatisfacible para los 5 de arriba y bloquearía el cierre del plan. El criterio es: **la lista de ofensores de cada rojo es exactamente la de esta tabla**. Un "todo pasa" no es evidencia; se pega la salida.

### 4.3 Cómo se leen los `archivo:línea` de este documento

Hay una sesión paralela viva en este árbol. Los números pueden correrse entre que se escribe y se implementa. **Regla:** cada vez que este documento da un número de línea para un punto de inserción, da también el **símbolo**. Si el número no coincide, **manda el símbolo**. F0.0 es un barrido que revalida los 12 anclajes críticos en 10 segundos antes de tocar nada.

---

## 5. Las 3 flags — nombre, default y las SEIS patas

### 5.1 Las flags

| Key | Default | Categoría | Qué protege | Justificación del default |
|---|---|---|---|---|
| `STACKY_TICKET_FULLVIEW_ENABLED` | **ON** (`default=True`) | `interfaz_ui` | La ficha a pantalla completa, su botón de apertura y el enlace directo `?ticket=` | Solo lectura y presentación. No cae en (A) — nada corre en reposo — ni en (B) — no escribe en ningún sistema |
| `STACKY_TICKET_HISTORY_API_ENABLED` | **ON** (`default=True`) | `paridad_proveedores` | La ruta `GET /api/tickets/<id>/historial` y su panel | Lectura **bajo demanda**: solo consulta al tracker cuando el operador abre el panel (§6.F5, `enabled:`). No es loop, daemon, barrido ni sondeo ⇒ no cae en (A). No escribe ⇒ no cae en (B) |
| `STACKY_TRACKER_CAPABILITIES_API_ENABLED` | **ON** (`default=True`) | `paridad_proveedores` | La ruta `GET /api/tickets/capacidades` y los avisos de pérdida en los paneles | Lee un `dict` en memoria del propio proceso (`CAPABILITY_MATRIX`), sin red y sin base. Es el caso canónico de "solo lectura ⇒ va ON" |

**Ninguna declara `requires=`.** No es un olvido: `test_requires_map_is_frozen` (`backend/tests/test_harness_flags_requires.py:397`) compara por **igualdad exacta de diccionarios** contra `_REQUIRES_MAP_FROZEN` (`:120`), y es el séptimo guardián que se olvida siempre. La dependencia real (los paneles solo existen dentro de la ficha) se hace cumplir en **un solo punto de código**: los paneles se renderizan dentro de `TicketFullView.tsx`, que solo se monta si `STACKY_TICKET_FULLVIEW_ENABLED` está ON (§6.F6). No hace falta declararla.

### 5.2 Las SEIS patas, con ruta y ancla verificadas el 2026-08-02

| # | Archivo | Estructura | Ancla | Instrucción por símbolo |
|---|---|---|---|---|
| 1 | `Stacky Agents/backend/config.py` | 3 atributos de la clase de config | final del bloque de flags | Buscar la última línea `STACKY_*: bool = os.getenv(` y agregar debajo |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | 3 `FlagSpec` en `FLAG_REGISTRY` | abre en **`:610`**, cierra en **`:7183`** | Agregar antes del `)` final del archivo |
| 3 | `Stacky Agents/backend/services/harness_flags.py` | `_CATEGORY_KEYS`: 1 key en `"interfaz_ui"`, 2 en `"paridad_proveedores"` | `"interfaz_ui"` abre en **`:556`** y cierra en **`:580`**; `"paridad_proveedores"` abre en **`:581`** | `Select-String -Path "...harness_flags.py" -Pattern '"interfaz_ui": \(\|"paridad_proveedores": \('` — pegar al final de cada tupla, **después de la última entrada que encuentres, sea cual sea** |
| 4 | **`Stacky Agents/backend/tests/test_harness_flags.py`** | `_CURATED_DEFAULTS_ON` (es un `set`, vive en el **test**, no en el servicio) | abre en **`:467`** | Agregar las **3** keys al final del set |
| 5 | **`Stacky Agents/backend/tests/test_harness_flags_requires.py`** | `_REQUIRES_MAP_FROZEN` (dict) | abre en **`:120`** | **NO SE TOCA.** Ninguna flag de este plan declara `requires=` |
| 6 | `Stacky Agents/backend/services/harness_flags_help.py` | `PLAIN_HELP` (dict) | abre en **`:25`**, cierra en **`:2455`** (el `}`; la última entrada cierra con `),` en `:2454` y `def plain_help_for` está en `:2458`) | Agregar 3 entradas al final del dict |

### 5.3 Texto literal de las 3 `FlagSpec`

Van al final de `FLAG_REGISTRY`, antes del `)` de `services/harness_flags.py:7183`:

```python
    # ── Plan 287 — la ficha del ticket a pantalla completa ────────────────────
    FlagSpec(
        key="STACKY_TICKET_FULLVIEW_ENABLED",
        type="bool",
        label="Ficha del ticket a pantalla completa",
        description=(
            "Plan 287 — Habilita abrir un ticket en una ficha a pantalla completa "
            "con descripcion, comentarios, adjuntos, historial e hijos, y navegar "
            "padre/hijos/hermanos sin cerrarla. Solo lectura y presentacion."
        ),
        group="global",
        env_only=False,
        default=True,
        # SIN requires= a proposito: ver Plan 287 seccion 5.1.
    ),
    FlagSpec(
        key="STACKY_TICKET_HISTORY_API_ENABLED",
        type="bool",
        label="Historial de cambios del ticket",
        description=(
            "Plan 287 — Expone el historial de cambios del ticket leyendolo del "
            "puerto TrackerProvider (fetch_item_updates), igual para Azure DevOps "
            "y GitLab. Se consulta solo cuando el operador abre el panel."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_TRACKER_CAPABILITIES_API_ENABLED",
        type="bool",
        label="Avisar que un panel viene incompleto",
        description=(
            "Plan 287 — Publica el estado declarado de cada capacidad del tracker "
            "activo para que cada panel de la ficha avise cuando su informacion "
            "viene parcial, y con que perdida. Lee un diccionario en memoria."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
```

> **Regla dura verificada:** en todo `harness_flags.py` hay **cero** `default=False` reales. Una flag OFF se declara **omitiendo** el kwarg, porque `default_is_known(spec)` es `spec.default is not None` y `False is not None`. Las 3 de este plan son ON, así que las 3 declaran `default=True` **y** entran a `_CURATED_DEFAULTS_ON`. Las dos cosas, siempre juntas.

### 5.4 Texto literal de `_CURATED_DEFAULTS_ON` (pata 4)

Al final del `set` que abre en `backend/tests/test_harness_flags.py:467`:

```python
    # ── Plan 287 — la ficha del ticket a pantalla completa ────────────────────
    # Las 3 nacen ON. Ninguna cae en (A): no enciende loop, daemon, barrido,
    # sondeo ni llamada a modelo — todo es bajo demanda del operador. Ninguna
    # cae en (B): no escribe en ningun sistema, no borra nada y no decide nada.
    "STACKY_TICKET_FULLVIEW_ENABLED",
    "STACKY_TICKET_HISTORY_API_ENABLED",
    "STACKY_TRACKER_CAPABILITIES_API_ENABLED",
```

### 5.5 Texto literal de `PLAIN_HELP` (pata 6)

Las 10 reglas, leídas del test real (`backend/tests/test_harness_flags_help.py`, no de otro plan): `JARGON_DENYLIST` en `:17-20`, `_KEY_RE` en `:22`, `_PHASE_RE` en `:23`, las cotas en `:47-51`, el prefijo en `:59-60` y la jerga en `:64-77`.

`what` entre 10 y 200 caracteres · `on_effect` y `off_effect` ≤ 240 · `example` ≤ 300 · los 4 no vacíos · `on_effect` y `off_effect` **empiezan con `"Si "`** (con espacio) · sin jerga de `JARGON_DENYLIST` = `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime`, **case-insensitive y con el plural incluido** (`\b{term}s?\b`) · sin claves en mayúsculas con guión bajo · sin referencias a fase (`\bF\d`).

> **Los 3 textos de abajo se validaron EJECUTANDO las 10 reglas** contra las mismas expresiones del test, el 2026-08-02. Resultado: **0 violaciones**. Longitudes medidas — `FULLVIEW`: what 116 / on 152 / off 99 / ejemplo 105 · `HISTORY_API`: 102 / 111 / 77 / 86 · `CAPABILITIES_API`: 91 / 129 / 85 / 135. **Copiarlos literales.** Si se reescriben "para que suenen mejor", hay que volver a correr `pytest tests/test_harness_flags_help.py` y comparar contra el baseline de F0.1: las palabras prohibidas más fáciles de meter sin querer en este dominio son *"endpoint"*, *"runtime"* y *"gate"*.

```python
    "STACKY_TICKET_FULLVIEW_ENABLED": PlainHelp(
        what="Permite abrir la ficha completa de un ticket a pantalla completa, con su descripcion, comentarios, adjuntos e hijos.",
        on_effect="Si la activas: cada ticket suma un boton que abre su ficha a pantalla completa y te deja saltar al padre, a los hijos y a los hermanos sin volver atras.",
        off_effect="Si la apagas: el tablero queda como hasta ahora y el ticket solo se despliega dentro de su tarjeta.",
        example="Abris una epica, ves sus ocho hijos en una lista y saltas al tercero sin perder de vista de donde venias.",
    ),
    "STACKY_TICKET_HISTORY_API_ENABLED": PlainHelp(
        what="Trae el historial de cambios del ticket desde el sistema donde vive para mostrarlo dentro de la ficha.",
        on_effect="Si la activas: la ficha suma un panel con quien cambio que y cuando, y solo se consulta cuando abris ese panel.",
        off_effect="Si la apagas: la ficha se ve igual pero sin el panel de historial de cambios.",
        example="Ves que el estado paso a En curso hace dos dias y quien lo movio, sin salir de Stacky.",
    ),
    "STACKY_TRACKER_CAPABILITIES_API_ENABLED": PlainHelp(
        what="Publica que cosas soporta el sistema de tickets del proyecto activo y con que limitaciones.",
        on_effect="Si la activas: cada panel de la ficha avisa cuando su informacion viene incompleta y explica que falta en ese sistema de tickets.",
        off_effect="Si la apagas: los paneles que no pueden traer todo aparecen vacios sin decir por que.",
        example="En un proyecto de GitLab el listado de adjuntos sale de la descripcion del issue: la ficha lo aclara en vez de mostrar una lista vacia.",
    ),
```

---

## 6. Fases

> **Comandos canónicos.** Servidor: desde `Stacky Agents/backend`, `.venv/Scripts/python.exe -m pytest tests/<UN_ARCHIVO>.py -q --no-header -p no:cacheprovider` (`backend/.venv` es Python 3.13.5; `backend/venv` es 3.11.9 — **usar `.venv`**). Interfaz: desde `Stacky Agents/frontend`, `npx vitest run src/<ruta>/<archivo>.test.ts` (**por archivo, nunca la suite entera**: hay contaminación por orden) y `npx tsc --noEmit`.

---

### F0.0 — Barrido de anclajes, ANTES de tocar nada

**Objetivo:** revalidar en 10 segundos los 12 anclajes críticos, porque hay una sesión paralela viva en este árbol.
**Archivos:** ninguno (solo lectura).
**Trabajo del operador:** ninguno.
**Flag:** ninguna.

Correr desde `Stacky Agents`:

```powershell
Select-String -Path "backend\services\harness_flags.py"        -Pattern 'FLAG_REGISTRY: tuple|"interfaz_ui": \(|"paridad_proveedores": \('
Select-String -Path "backend\tests\test_harness_flags.py"      -Pattern '_CURATED_DEFAULTS_ON = \{'
Select-String -Path "backend\services\harness_flags_help.py"   -Pattern 'PLAIN_HELP: dict|def plain_help_for'
Select-String -Path "backend\api\tickets.py"                   -Pattern 'def get_ticket\b|def get_comments|def get_attachments|def get_hierarchy|def _padre_efectivo'
Select-String -Path "backend\services\tracker_provider.py"     -Pattern 'def get_tracker_provider'
Select-String -Path "backend\services\provider_capabilities.py" -Pattern 'def capability_status|def capability_loss|def supports'
Select-String -Path "backend\scripts\run_harness_tests.sh"     -Pattern 'HARNESS_TEST_FILES=\('
Select-String -Path "backend\scripts\run_harness_tests.ps1"    -Pattern '\$HarnessTestFiles = @\('
Select-String -Path "frontend\src\services\routes.ts"          -Pattern 'export interface RouteState|export function parseRoute|export function serializeRoute|function normalizeInitial|const EXEC_KEYS|sp\.forEach'
Select-String -Path "frontend\src\components\ui\Dialog.tsx"    -Pattern 'bare\?: boolean|panelClassName\?: string'
Select-String -Path "frontend\src\components\ui\index.ts"      -Pattern 'export \{ default as Dialog \}'
Select-String -Path "frontend\src\pages\TicketBoard.tsx"       -Pattern 'function TicketCard|data-card-header|export default function TicketBoard'
Select-String -Path "frontend\src\components\TicketGraphView.jsx" -Pattern 'function TicketNodeCard'
Select-String -Path "frontend\src\App.tsx"                     -Pattern '<TicketBoard'
Select-String -Path "frontend\src\types.ts"                    -Pattern 'export interface TicketNode|export interface TicketHierarchy'
```

**Criterio binario:** los 15 patrones imprimen **al menos una línea cada uno**. Si alguno no imprime nada, **parar** y avisar: el símbolo se renombró y el plan necesita una pasada de actualización.

> **C11 — por qué la v2 sumó `routes.ts` con más granularidad, `App.tsx`, `types.ts` y el barril `ui`.** Los 6 commits del plan 286 de la sesión paralela corrieron 16 anclajes de la v1 entre que se escribió y se criticó: `api/tickets.py` **+6/+7** (`get_ticket` `:1285`→**`:1292`**, `get_comments` `:1561`→**`:1568`**, `get_attachments` `:1598`→**`:1605`**), los dos scripts del arnés **+3**, y `routes.ts` **−1 a −4** (`RouteState` `:26`→**`:25`**, `exec?: number` `:29`→**`:28`**, regex `:74`→**`:71`**, volcado de `query` `:80-81`→**`:76-77`**, `normalizeInitial` `:88`→**`:85`**). Ninguno rompe el plan porque manda el símbolo — **pero el barrido tiene que cubrir los símbolos que las fases realmente tocan**, y la v1 no cubría ni `App.tsx` ni `types.ts`, que son justamente los dos archivos que la v2 tuvo que agregar (C4, C5).

---

### F0.1 — Línea base medida de los 6 gates que este plan cruza

**Objetivo:** dejar por escrito el número de **hoy** de cada gate, para que el criterio de aceptación sea un **delta** y no un absoluto.
**Archivos:** ninguno (solo lectura).
**Trabajo del operador:** ninguno.

Correr y **anotar la salida literal** en el registro de implementación:

**Los valores de la columna "Medido" ya están tomados (2026-08-02, tras los 6 commits del plan 286). El implementador los vuelve a correr y confirma que coinciden; si NO coinciden, la sesión paralela volvió a moverse y hay que reanclar antes de seguir.**

| # | Comando (cwd) | **Medido 2026-08-02** |
|---|---|---|
| 1 | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` (`frontend`) | **ROJO DE FÁBRICA — 1 failed, 5 regresiones** (§4.2). *La v1 decía "verde": era falso* |
| 2 | `npx vitest run src/__tests__/adhocModalRatchet.test.ts` (`frontend`) | **ROJO DE FÁBRICA — `2 failed \| 2 passed (4)`**, 2 ad-hoc fuera + 1 stale (§4.2). *La v1 decía "verde": era falso* |
| 3 | `npx vitest run src/services/__tests__/routes.test.ts` (`frontend`) | **`17 passed`** |
| 4 | `npx vitest run src/services/__tests__/routesDeepLink.test.ts` (`frontend`) | **`6 passed`** |
| 5 | `npx vitest run src/services/__tests__/plan273GateState.test.ts` (`frontend`) | **`2 failed \| 12 passed (14)`** (`:86` y `:110`) — rojo de fábrica §4.2 |
| 6 | `.venv/Scripts/python.exe -m pytest tests/test_plan281_ratchet_ado_only.py tests/test_plan259_ratchet_script_parity.py tests/test_harness_ratchet_meta.py -q --no-header -p no:cacheprovider` (`backend`) | **`27 passed`** |
| 7 | `npx tsc --noEmit` (`frontend`) | **exit 0, 0 errores** |
| 8 | `.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_help.py tests/test_harness_flags_requires.py -q --no-header -p no:cacheprovider` (`backend`) | **`4 failed, 72 passed`** — las 4 son de `test_harness_flags_help.py` (§4.2) |
| 9 | `npx vitest run src/__tests__/themeContrast.test.ts` y `src/__tests__/a11yCss.test.ts` (`frontend`) | **`4 passed`** y **`3 passed`** |

**Criterio binario:** los 9 números quedan escritos. Al cerrar el plan (F8.4) se vuelven a correr los 9 y se compara **contra estos números**:
- Los verdes (3, 4, 6, 7, 9) siguen verdes, con **+4 / +2** en 3 y 4 respectivamente ⇒ **`21 passed`** y **`8 passed`**.
- Los rojos de fábrica (1, 2, 5, 8) mantienen **exactamente la misma lista de ofensores de §4.2**. Un ofensor nuevo = regresión de este plan.

---

### F0.2 — Las 3 flags: las seis patas, en un solo commit

**Objetivo:** registrar las flags completas para que ninguna suite del arnés salga roja.
**Archivos:** los 5 de §5.2 (la pata 5 **no se toca**).
**Tests primero:** no aplica — esta fase **es** la que hace pasar tests ajenos ya existentes.
**Flag:** son las flags.
**Trabajo del operador:** ninguno (las 3 nacen ON).
**Runtimes:** neutro — el registro de flags es único.

**Criterio binario (los 4 comandos, desde `Stacky Agents/backend`):**

```bash
.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py::test_requires_map_is_frozen -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_flags_env_read_meta.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_harness_flags_help.py -q --no-header -p no:cacheprovider
```

- Los 3 primeros: **verdes**.
- El cuarto: es rojo de fábrica. **C8 — el criterio NO es "las mismas 4 fallidas con los mismos nombres": eso NO discrimina.** `test_plain_help_covers_all_registry_keys` ya falla hoy con **92 flags sin ayuda llana**; si este plan registra las 3 `FlagSpec` y se olvida una entrada de `PLAIN_HELP`, la suite sigue dando **las mismas 4 fallidas con los mismos nombres** y el olvido pasa. El criterio va sobre el **CUERPO** del mensaje:

  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_harness_flags_help.py -q --no-header -p no:cacheprovider 2>&1 \
    | grep -cE "STACKY_TICKET_FULLVIEW_ENABLED|STACKY_TICKET_HISTORY_API_ENABLED|STACKY_TRACKER_CAPABILITIES_API_ENABLED"
  ```
  **Tiene que dar `0`.** Ninguna key de este plan puede aparecer en la lista `missing` de `test_plain_help_covers_all_registry_keys` ni en la lista `violations` de `test_plain_help_avoids_jargon_denylist`.

> **Los 3 textos de `PLAIN_HELP` de §5.5 se validaron EJECUTANDO las 10 reglas del test real el 2026-08-02: 0 violaciones**, con longitudes `what/on/off/ejemplo` = `116/152/99/105`, `102/111/77/86`, `91/129/85/135` — idénticas a las declaradas. **Copiarlos literales.** Si se reescriben, volver a correr el `grep -c` de arriba.
- Además: `grep -c "STACKY_TICKET_FULLVIEW_ENABLED\|STACKY_TICKET_HISTORY_API_ENABLED\|STACKY_TRACKER_CAPABILITIES_API_ENABLED"` sobre los 5 archivos de §5.2 debe dar **3, 3+3, 3, 3, 3** respectivamente (registro, dos categorías, curadas, ayuda, config).

---

### F1 — Servidor: el historial del ticket, por la costura, para los dos trackers

**Objetivo:** exponer por HTTP el `fetch_item_updates` que ya existe en el puerto y en los dos adaptadores, y que hoy nadie puede ver.
**Valor:** cierra K4 (2 de 3 → 3 de 3). Es la pieza de "paridad conceptual con la vista de work item" que hoy falta entera.
**Flag:** `STACKY_TICKET_HISTORY_API_ENABLED` (ON).
**Trabajo del operador:** ninguno.
**Runtimes:** neutro (el símbolo no nombra ningún runtime).

**Archivo a editar:** `Stacky Agents/backend/api/tickets.py`. La ruta va **inmediatamente después** de `get_attachments` (buscar `def get_attachments`, hoy en **`:1605`**, y pegarla después de su `return`).

---

#### C1 — LO MÁS IMPORTANTE DE ESTA FASE: los dos adaptadores devuelven formas SIN UNA SOLA CLAVE EN COMÚN

La v1 decía: *"`_normalizar_update(u)` es un helper **puro** que devuelve exactamente estas 5 claves, tolerando ausencias: `{fecha, autor, campo, de, a}`. No inventa datos: lo que no venga, va `None`."*

**Eso, escrito literal, produce un panel MUDO en LOS DOS trackers.** Medido abriendo los dos adaptadores el 2026-08-02:

| | ADO — `ado_provider.py:137` → `ado_client.fetch_work_item_updates` (`ado_client.py:957-972`, devuelve `data["value"]` crudo de `/_apis/wit/workitems/<id>/updates`) | GitLab — `gitlab_provider.py:606-666` (dict **ya armado por el adaptador**) |
|---|---|---|
| **Claves reales** | `id`, `rev`, `revisedBy{displayName}`, `revisedDate`, `fields{"<campo>": {oldValue, newValue}}` | `kind` (`label_event`\|`state_event`\|`system_note`), `created_at`, `user` (ya es el `username`, string), `label{name}`, `action`, `state`, `body`, `raw` |
| **Fixtures reales que YA existen en el repo** | `backend/tests/test_ado_provider.py:75-78` → `{"revisedDate": "2026-01-01", "rev": 1}` | `backend/tests/test_gitlab_provider.py:394-398` → `{"created_at": "...", "action": "add", "label": {"name": "bug"}, "user": {"username": "dev"}}` y `{"created_at": "...", "state": "closed", "user": {"username": "dev"}}` |
| `u.get("fecha")` | `None` | `None` |
| `u.get("autor")` | `None` | `None` |
| `u.get("campo") / ("de") / ("a")` | `None` | `None` |

**Intersección de claves entre los dos: vacía.** Un `_normalizar_update(u)` de una sola forma devuelve `{fecha: None, autor: None, campo: None, de: None, a: None}` para **toda** entrada de **ambos** trackers. Y el test que debería atraparlo (`test_historial_devuelve_los_updates_del_provider`, "doble con `fetch_item_updates` devolviendo 2 entradas") **deja que el implementador elija la forma del doble**, así que sale verde con una forma inventada. Falso verde de manual.

**Firma corregida y TABLA DE MAPEO OBLIGATORIA (copiar, no inferir):**

```python
# ── Plan 287 F1 (v2/C1) — normalizador POR TRACKER. La forma de fetch_item_updates
# NO es común a los dos adaptadores: no comparten ni una clave. Mapeo explícito o
# el panel sale mudo. Fixtures reales: tests/test_ado_provider.py:75-78 y
# tests/test_gitlab_provider.py:394-398.

def _normalizar_update(u: dict, tracker: str) -> list[dict]:
    """Devuelve 0..N filas {fecha, autor, campo, de, a} (str|None). NUNCA lanza.

    ADO emite UNA entrada con N campos cambiados -> se expande a N filas.
    GitLab emite UNA entrada por evento -> devuelve 0 o 1 fila.
    """
    if tracker == "gitlab":
        kind = u.get("kind") or ""
        autor = u.get("user") or None                     # ya es el username, string
        fecha = u.get("created_at") or None
        if kind == "state_event":
            return [{"fecha": fecha, "autor": autor, "campo": "Estado",
                     "de": None, "a": u.get("state") or None}]
        if kind == "label_event":
            etiqueta = (u.get("label") or {}).get("name") or None
            agrega = (u.get("action") or "") == "add"
            return [{"fecha": fecha, "autor": autor, "campo": "Etiqueta",
                     "de": None if agrega else etiqueta,
                     "a": etiqueta if agrega else None}]
        if kind == "system_note":
            return [{"fecha": fecha, "autor": autor, "campo": "Nota del sistema",
                     "de": None, "a": (u.get("body") or None)}]
        return []                                          # kind desconocido: se descarta

    # azure_devops (y cualquier otro que hable el dialecto de ADO)
    fecha = u.get("revisedDate") or None
    autor = ((u.get("revisedBy") or {}).get("displayName")) or None
    campos = u.get("fields") or {}
    filas = [
        {"fecha": fecha, "autor": autor, "campo": _nombre_llano(nombre),
         "de": _txt(cambio.get("oldValue")), "a": _txt(cambio.get("newValue"))}
        for nombre, cambio in campos.items()
        if isinstance(cambio, dict) and nombre in _CAMPOS_ADO_VISIBLES
    ]
    # Una revision sin ningun campo visible NO se descarta en silencio: se emite
    # una fila de presencia, para que el operador vea que hubo una revision.
    return filas or [{"fecha": fecha, "autor": autor, "campo": None, "de": None, "a": None}]


_CAMPOS_ADO_VISIBLES = frozenset({
    "System.State", "System.AssignedTo", "System.Title", "System.IterationPath",
    "System.AreaPath", "System.Tags", "Microsoft.VSTS.Common.Priority",
})
_NOMBRES_LLANOS = {
    "System.State": "Estado", "System.AssignedTo": "Asignado",
    "System.Title": "Titulo", "System.IterationPath": "Iteracion",
    "System.AreaPath": "Area", "System.Tags": "Etiquetas",
    "Microsoft.VSTS.Common.Priority": "Prioridad",
}
def _nombre_llano(k: str) -> str: return _NOMBRES_LLANOS.get(k, k)
def _txt(v) -> str | None:
    if v is None: return None
    if isinstance(v, dict): return v.get("displayName") or v.get("name") or str(v)
    return str(v)
```

Como `_normalizar_update` ahora devuelve **una lista**, la ruta hace `for u in crudos for fila in _normalizar_update(u, tracker)`.

**Imports — verificado el 2026-08-02, para que nadie duplique ni se olvide:**
- `resolve_project_context` **ya está importado** (`api/tickets.py:35`). No re-importar.
- `get_tracker_provider` y `TrackerConfigError` **ya están importados** (`api/tickets.py:39`). No re-importar.
- `capability_status`, `capability_loss` y `supports` **NO están importados**: `grep -c "provider_capabilities" api/tickets.py` → **0**. Hay que agregar, junto a los otros imports de `services`:
  ```python
  from services.provider_capabilities import capability_status, capability_loss, supports  # Plan 287
  ```
  Es un import de `api/` hacia `services/`, que es la dirección permitida (el guardarraíl prohíbe la inversa).

**Tests PRIMERO.** Archivo nuevo: `Stacky Agents/backend/tests/test_plan287_ficha_ticket.py`.

Casos (nombres exactos):

| Test | Qué prueba | Cómo |
|---|---|---|
| `test_historial_devuelve_403_con_la_flag_apagada` | 403 = flag apagada, **nunca** permiso; el cuerpo dice `feature_disabled` | `monkeypatch.setattr(config.config, "STACKY_TICKET_HISTORY_API_ENABLED", False)` |
| `test_historial_404_si_el_ticket_no_existe` | id inexistente → 404 con motivo | — |
| `test_historial_usa_el_provider_y_no_la_columna_tracker_type` | El caso central. Un ticket con `tracker_type="azure_devops"` **en un proyecto GitLab** debe consultar al provider de **GitLab** | `monkeypatch` de `get_tracker_provider` por un doble que registra la llamada; el ticket se crea con la columna mintiendo |
| `test_historial_devuelve_los_updates_del_provider` | Pasa por el puerto y normaliza | doble con `fetch_item_updates` devolviendo 2 entradas |
| `test_historial_degrada_sin_romper_si_la_capacidad_esta_ausente` | Si `supports(tracker, "tracker.updates.history")` es False → **200** con `historial: []` y `capacidad.estado == "absent"`, no 500 | `monkeypatch` de `capability_status` |
| `test_historial_informa_la_perdida_cuando_la_capacidad_es_parcial` | En GitLab la capacidad es `partial` con pérdida escrita (`provider_capabilities.py:244-248`) → el cuerpo trae `capacidad.perdida` no vacía | — |
| `test_historial_503_si_el_tracker_no_esta_configurado` | `TrackerConfigError` (p. ej. GitLab con su interruptor apagado) → 503 tipado, no traza cruda | — |
| `test_historial_no_llama_al_tracker_dos_veces` | Una sola llamada por pedido | contador en el doble |
| **`test_normaliza_la_forma_REAL_de_ado`** *(v2/C1)* | La fixture **copiada de `tests/test_ado_provider.py:75-78` + la forma completa del endpoint** (`{"revisedDate","rev","revisedBy":{"displayName":"Ana"},"fields":{"System.State":{"oldValue":"New","newValue":"Active"}}}`) sale con `fecha`, `autor` y `campo="Estado"`, `de="New"`, `a="Active"` | llamada directa a `_normalizar_update(u, "azure_devops")` |
| **`test_normaliza_la_forma_REAL_de_gitlab`** *(v2/C1)* | Las 2 fixtures **copiadas de `tests/test_gitlab_provider.py:394-398`** salen con `fecha`, `autor="dev"`, y `campo` en `{"Estado","Etiqueta"}` | llamada directa a `_normalizar_update(u, "gitlab")` |
| **`test_ninguna_fila_sale_toda_en_None`** *(v2/C1 — el centinela anti-panel-mudo)* | Para **cada** fixture real de los dos trackers, **al menos una** de las 5 claves no es `None`. Es el test que la v1 no tenía y que habría atrapado el defecto | parametrizado sobre las fixtures de F1.5 |
| **`test_normalizador_no_lanza_ante_basura`** *(v2/C1)* | `{}`, `{"kind": "inventado"}`, `{"fields": "no es dict"}` → devuelve lista (vacía o de presencia), **nunca** excepción | — |

**Antes de implementar, `test_ninguna_fila_sale_toda_en_None` tiene que FALLAR con la implementación ingenua de la v1** (`u.get("fecha")` etc.). Ese es el gate corrido **contra el defecto**: si no falla con la v1, no prueba nada. Anotar la salida de esa corrida.

Comando: desde `Stacky Agents/backend`

```bash
.venv/Scripts/python.exe -m pytest tests/test_plan287_ficha_ticket.py -q --no-header -p no:cacheprovider
```

**Antes de implementar, los 8 tienen que FALLAR** (7 por `404` de ruta inexistente, y `test_historial_devuelve_403_con_la_flag_apagada` por `AttributeError` de la flag si F0.2 aún no corrió). Anotar la salida.

**Implementación (pseudocódigo, `api/tickets.py`):**

```python
# ── Plan 287 F1 — historial de cambios del ticket, por la costura de proveedor ──
# PROHIBIDO leer ticket.tracker_type para rutear: la columna miente (Plan 281/286).
# El ruteo va por get_tracker_provider(project), que es PROVIDER_SEAM reconocido
# por services/provider_coupling_audit.py:130-132.

_CAPACIDAD_HISTORIAL = "tracker.updates.history"

@bp.get("/<int:ticket_id>/historial")
def get_ticket_historial(ticket_id: int):
    if not bool(getattr(config.config, "STACKY_TICKET_HISTORY_API_ENABLED", True)):
        return jsonify({"error": "feature_disabled",
                        "detalle": "El historial del ticket esta apagado en el arnes."}), 403

    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            return jsonify({"error": "not_found",
                            "detalle": f"No existe el ticket {ticket_id}."}), 404
        proyecto = ticket.stacky_project_name
        item_id = str(ticket.external_id or ticket.ado_id)

    ctx = resolve_project_context(project_name=proyecto)      # TRACKER_GUARD reconocido
    tracker = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()

    estado = capability_status(tracker, _CAPACIDAD_HISTORIAL)
    perdida = capability_loss(tracker, _CAPACIDAD_HISTORIAL)
    capacidad = {"clave": _CAPACIDAD_HISTORIAL, "estado": estado, "perdida": perdida}

    if not supports(tracker, _CAPACIDAD_HISTORIAL):
        # Degrada, NO rompe: 200 con lista vacia y el motivo escrito.
        return jsonify({"historial": [], "tracker": tracker, "capacidad": capacidad}), 200

    try:
        provider = get_tracker_provider(proyecto)
        crudos = provider.fetch_item_updates(item_id) or []
    except TrackerConfigError as e:
        return jsonify({"error": "tracker_no_configurado", "detalle": str(e),
                        "tracker": tracker}), 503

    historial = [fila for u in crudos for fila in _normalizar_update(u, tracker)]
    return jsonify({"historial": historial,
                    "tracker": tracker, "capacidad": capacidad}), 200
```

`_normalizar_update(u, tracker)` es el helper **puro** de la tabla de mapeo de arriba (C1). Devuelve una **lista** de 0..N filas `{"fecha", "autor", "campo", "de", "a"}` (`str | None` cada una). No inventa datos, pero **tampoco emite filas todas en `None`**: una revisión de ADO sin campos visibles emite una fila de presencia con fecha y autor.

**Criterio binario:** los **12** tests de F1 en verde **y** `pytest tests/test_plan281_ratchet_ado_only.py` sigue en verde (`violaciones_count` sin subir, hoy `0` en `backend/tests/ado_only_baseline.json`).

---

### F1.5 — [ADICIÓN ARQUITECTO] El centinela de forma del puerto: `test_paridad_forma_updates`

**El problema que resuelve, en una línea:** el puerto `TrackerProvider` declara la **firma** (`-> list[dict]`) pero **no declara la forma del `dict`**, así que dos adaptadores pueden cumplir el `Protocol` y devolver universos distintos — y nadie se entera hasta que un operador mira un panel vacío. Es exactamente el defecto C1, y **no es propio de este plan**: `fetch_comments` y `fetch_attachments` tienen el mismo agujero, solo que ya fueron domados a mano por sus consumidores.

**Por qué es barato:** las formas reales **ya están capturadas** en los tests que los propios adaptadores escribieron (`test_ado_provider.py:75-78`, `test_gitlab_provider.py:394-398`). No hace falta red, ni credenciales, ni tocar los adaptadores.

**Archivo nuevo:** `Stacky Agents/backend/tests/fixtures/plan287_updates.py` — un módulo de datos, sin lógica:

```python
"""Plan 287 F1.5 — formas REALES de fetch_item_updates, copiadas de los tests que
los propios adaptadores ya tienen. Sirven de contrato: si un adaptador cambia su
forma, este archivo tiene que cambiar en el mismo commit y el cambio se ve en el diff."""

UPDATES_ADO = [
    {"rev": 2, "revisedDate": "2026-06-01T10:00:00Z",
     "revisedBy": {"displayName": "Ana Perez"},
     "fields": {"System.State": {"oldValue": "New", "newValue": "Active"}}},
    {"rev": 3, "revisedDate": "2026-06-02T11:00:00Z",
     "revisedBy": {"displayName": "Ana Perez"},
     "fields": {"Microsoft.VSTS.Common.Priority": {"oldValue": 3, "newValue": 1}}},
    {"rev": 4, "revisedDate": "2026-06-03T12:00:00Z",
     "revisedBy": {"displayName": "Ana Perez"}, "fields": {}},   # revision sin campos visibles
]

UPDATES_GITLAB = [
    {"kind": "state_event", "created_at": "2026-06-14T09:00:00",
     "state": "closed", "user": "dev", "raw": {}},
    {"kind": "label_event", "created_at": "2026-06-15T10:00:00",
     "action": "add", "label": {"name": "bug"}, "user": "dev", "raw": {}},
    {"kind": "system_note", "created_at": "2026-06-16T08:00:00",
     "body": "changed the description", "user": "dev", "raw": {}},
]
```

**Los 3 tests del centinela** (van en `tests/test_plan287_ficha_ticket.py`, con `@pytest.mark.parametrize` sobre los dos trackers):

| Test | Qué congela |
|---|---|
| `test_paridad_forma_updates_las_cinco_claves` | Para **cada** fixture de **cada** tracker, la fila normalizada tiene **exactamente** `{fecha, autor, campo, de, a}` — ni una clave más, ni una menos. Congela el contrato de la ficha |
| `test_paridad_forma_updates_ninguna_fila_muda` | Para **cada** fixture de **cada** tracker, **al menos una** de las 5 no es `None`. **Este es el test que habría matado a C1 en la v1** |
| `test_paridad_forma_updates_el_fixture_refleja_al_adaptador` | `UPDATES_GITLAB[0].keys() ⊇ {"kind","created_at","user"}` y `UPDATES_ADO[0].keys() ⊇ {"revisedDate","revisedBy","fields"}`. Si un adaptador renombra una clave, este test **no** lo detecta solo — pero deja escrito en un archivo de 20 líneas cuál era la forma esperada, que es la mitad del costo de diagnosticarlo |

**Por qué respeta los guardarraíles:** es solo lectura, no toca ningún adaptador, no agrega flags, no agrega trabajo al operador, no llama a la red ni a un modelo, y es neutro a los 3 runtimes (el módulo de fixtures no nombra ninguno). **No es scope creep:** sin él, F1 es un panel que puede nacer muerto y salir verde.

**Criterio binario:** los 3 en verde, y **el segundo tiene que FALLAR** si se le pasa la implementación ingenua de la v1. Se corre esa comprobación una vez y se pega la salida.

---

### F2 — Servidor: la matriz de capacidades, publicada

**Objetivo:** que la interfaz pueda saber, antes de pintar un panel, si va a poder llenarlo y qué se pierde si no.
**Valor:** cierra K5. Es la funcionalidad que ni Azure DevOps ni GitLab ofrecen: **decir qué no se puede mostrar y por qué**.
**Flag:** `STACKY_TRACKER_CAPABILITIES_API_ENABLED` (ON).
**Trabajo del operador:** ninguno.
**Runtimes:** neutro.

**Archivo a editar:** `Stacky Agents/backend/api/tickets.py` (misma ruta base, **cero blueprints nuevos** — un blueprint nuevo es una pata más de registro en `app.py` que este plan no necesita).

> **Trampa a evitar (verificada):** la ruta es `GET /tickets/capacidades`, un segmento **literal**. Flask la resuelve antes que `/<int:ticket_id>` porque el conversor `int` no matchea `"capacidades"`. Aun así, la ruta se declara **antes** de `get_ticket` (`api/tickets.py:1285`) para que quede explícito.

**Contrato de respuesta (congelado por este plan):**

```json
{
  "tracker": "gitlab",
  "capacidades": {
    "tracker.comments.list":   {"estado": "full",    "perdida": ""},
    "tracker.attachments.list":{"estado": "partial", "perdida": "GitLab no tiene modelo de relaciones: los adjuntos se extraen por regex sobre la descripción del issue"},
    "tracker.updates.history": {"estado": "partial", "perdida": "las tres sub-consultas (etiquetas, estados y notas del sistema) atrapan su error con un except mudo: si una falla, el historial sale incompleto y no hay forma de distinguirlo de un ticket sin actividad"},
    "tracker.items.url":       {"estado": "partial", "perdida": "devuelve None con los deep links apagados, violando la firma '-> str' del puerto"}
  }
}
```

Las 4 claves son una **lista congelada** en el módulo, `_CAPACIDADES_DE_LA_FICHA`, no la matriz entera: la ficha solo necesita esas cuatro y publicar de más es superficie inútil.

> #### C9 — el texto de `tracker.updates.history` de GitLab que la v1 iba a mostrarle al operador **es FALSO**
>
> `CAPABILITY_MATRIX["gitlab"]["tracker.updates.history"]` (`services/provider_capabilities.py:244-248`) dice **hoy**:
> > *"las sub-consultas de resource_state_events / resource_label_events están silenciadas: sin historial de estado ni de etiquetas"* — anclado en `services/gitlab_provider.py:413`.
>
> **Las dos mitades están mal, verificado abriendo el archivo el 2026-08-02:**
> 1. `gitlab_provider.py:413` es el armado de etiquetas de `update_item_state`; **no** es `fetch_item_updates`, que vive en **`:606`**. Anclaje **inexistente**.
> 2. `fetch_item_updates` **SÍ** consulta `resource_label_events` (`:613`) y `resource_state_events` (`:630`). Lo silenciado son los **errores** de esas sub-consultas (`except Exception: pass` en `:625`, `:641`, `:656`), no las consultas.
>
> La v1 copiaba ese texto **verbatim** al contrato congelado y su test lo asertaba solo por *"no vacía"*, así que la mentira pasaba los dos gates. El operador leería **"sin historial de estado ni de etiquetas"** justo mientras la ficha le muestra eventos de estado. **Corregirlo es parte de esta fase** (edición de 3 líneas en `provider_capabilities.py`, con el anclaje a `:606`), y el test lo asserta **por texto**.

**Tests (mismo archivo `tests/test_plan287_ficha_ticket.py`):**

| Test | Qué prueba |
|---|---|
| `test_capacidades_403_con_la_flag_apagada` | 403 + `feature_disabled` |
| `test_capacidades_devuelve_las_cuatro_claves_de_la_ficha` | exactamente 4 claves, las de `_CAPACIDADES_DE_LA_FICHA`, ni una más |
| `test_capacidades_de_gitlab_traen_la_perdida_escrita` | con proyecto GitLab, `tracker.attachments.list.perdida` **no vacía** y `estado == "partial"` |
| `test_capacidades_de_ado_marcan_full_donde_corresponde` | con proyecto ADO, `tracker.comments.list.estado == "full"` y `perdida == ""` |
| **`test_la_perdida_de_historial_de_gitlab_dice_la_verdad`** *(v2/C9)* | El texto de `tracker.updates.history` para GitLab **contiene** `"except mudo"` y **NO contiene** `"silenciadas"` ni `"sin historial de estado"`. Corre **contra el defecto**: con el texto de hoy, **falla** |

**Los 2 tests de la v1 que salen del conteo de aceptación (C7 — pasaban ANTES del cambio):**

| Test | Por qué no discrimina | Qué se hace |
|---|---|---|
| `test_capacidades_no_importa_nada_de_api_desde_services` | `services/provider_capabilities.py` ya no importa de `api/` **hoy**: verde sin tocar una línea | Se **conserva** como centinela heredado, pero **fuera** del conteo de aceptación de la fase |
| `test_capacidades_lo_desconocido_es_absent_no_explota` | La ruta publica solo las 4 claves congeladas de `_CAPACIDADES_DE_LA_FICHA` y **no acepta clave por parámetro**, así que el test solo puede llamar a `capability_status` directo — que ya se comporta así (`provider_capabilities.py:340`, verificado) | Ídem |

**Criterio binario de F2:** los 4 tests que discriminan, en verde; los 2 centinelas heredados, en verde; y el archivo completo da **`21 passed`** (F1: 12 · F1.5: 3 · F2: 6). El número vale como criterio porque **cambia** respecto de los 15 de F1+F1.5 y se compara contra ese número, no contra el vacío.

---

### F3 — Servidor: registrar el archivo de tests en los DOS ratchets, en el MISMO commit

**Objetivo:** que el arnés corra la suite nueva sin romper los dos guardianes que auditan la lista.
**Archivos:** `Stacky Agents/backend/scripts/run_harness_tests.sh` y `Stacky Agents/backend/scripts/run_harness_tests.ps1`.
**Flag:** ninguna.
**Trabajo del operador:** ninguno.

> **Por qué en el mismo commit que crea el archivo, y no antes:** `tests/test_harness_ratchet_meta.py::test_ratchet_no_referencia_archivos_inexistentes` y `tests/test_plan259_ratchet_script_parity.py::test_ninguna_ruta_apunta_a_un_archivo_inexistente` ponen **rojas dos suites hoy verdes** si la lista nombra un archivo que todavía no existe. Registrar antes de crear es el error del plan 286 §C2.

- `run_harness_tests.sh`: la lista abre en **`:20`** (`HARNESS_TEST_FILES=(`) y cierra en **`:1064`** (el archivo tiene 1106 líneas). Última entrada hoy: `tests/test_plan283_e2e.py` (**`:1063`**). *(v2/C11: la v1 decía `:1060/:1061`; los 6 commits del 286 corrieron la lista **+3**. El `:20` de apertura sí era correcto — quedó zanjada la contradicción `:12` vs `:20` de los dos censos del proponente.)* Es un array de bash: **sin comas**. Agregar como línea nueva antes del `)`:
  ```bash
  tests/test_plan287_ficha_ticket.py
  ```
- `run_harness_tests.ps1`: la lista abre en **`:13`** (`$HarnessTestFiles = @(`) y cierra en **`:980`** (el archivo tiene 1015 líneas). Última entrada hoy: `"tests/test_plan283_e2e.py"` (**`:979`**), **sin coma final** — verificado. *(v2/C11: la v1 decía `:976/:977`; **+3** por el 286.)* Es un array de PowerShell: **hay que agregarle la coma a la línea que hoy es la última** y después la entrada nueva:
  ```powershell
    "tests/test_plan283_e2e.py",
    "tests/test_plan287_ficha_ticket.py"
  ```
- **Sin rutas con espacios** y **misma ruta relativa exacta** en los dos archivos: la paridad se compara textualmente.

**Criterio binario:**

```bash
.venv/Scripts/python.exe -m pytest tests/test_plan259_ratchet_script_parity.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py -q --no-header -p no:cacheprovider
```
Los dos **verdes**, y `grep -c "test_plan287_ficha_ticket" scripts/run_harness_tests.sh scripts/run_harness_tests.ps1` da **1 y 1**.

---

### F4 — Interfaz: la lógica pura de la jerarquía, con sus tests

**Objetivo:** derivar padre, cadena de ancestros, hijos y hermanos a partir del árbol que el tablero **ya tiene cacheado**, sin una sola llamada nueva al servidor.
**Valor:** cierra K11 y K6. Es la navegación que pide el operador, a costo cero de red.
**Flag:** ninguna (es lógica pura; el interruptor está en quien la usa).
**Trabajo del operador:** ninguno.
**Runtimes:** neutro.

> **Por qué en un módulo `.ts` puro y no en el componente:** en este repositorio **no están instalados** `@testing-library/react` ni `jsdom` (`frontend/package.json` no los lista). No se puede montar un componente en una prueba. Toda la lógica testeable vive en `.ts` puro y el `.tsx` queda tonto. Es el mismo reparto que usó el plan 265 con sus nueve `services/console*.ts`.

**Archivos (v2 — son DOS, no uno):**
1. **`Stacky Agents/frontend/src/types.ts`** — **C5, sin esto la fase NO COMPILA.** `TicketNode` (`:129-131`) declara hoy solo `children: TicketNode[]`; **`motivo_huerfano` no existe en `Ticket`, ni en `TicketNode`, ni en `TicketHierarchy`** (verificado). La regla 5 lo lee del nodo y `NavegacionJerarquia.motivoHuerfano` lo expone, así que con `tsc --noEmit` (hoy **exit 0**, medido) eso es error de compilación — y "0 errores" es criterio binario de F6, F7 y del DoD. La v1 no listaba `types.ts` en ninguna fase. Edición **aditiva y de una línea**, dentro de `TicketNode`:
   ```ts
   export interface TicketNode extends Ticket {
     children: TicketNode[];
     /** Plan 287 — solo viaja en `orphans` (backend: api/tickets.py:810). Opcional a proposito. */
     motivo_huerfano?: string | null;
   }
   ```
   Es aditiva y opcional ⇒ **no rompe ningún consumidor** (`TicketBoard.tsx:5` y `TicketGraphView.jsx` ya importan el tipo).
2. **`Stacky Agents/frontend/src/services/ticketDetailModel.ts`** — el módulo puro.

> #### C6 — CUÁL árbol recibe la ficha: `hierarchy`, **nunca** `displayHierarchy`
>
> `TicketBoard.tsx` tiene **dos** árboles en scope:
> - `hierarchy` (`:1001-1003`) — el crudo del `useQuery` `["tickets-hierarchy", activeProjectName]`.
> - `displayHierarchy` (`:1029-1031`) — **filtrado por "mías"** (`if (showAll || !myUniqueName) return hierarchy;` … si no, filtra).
>
> La v1 decía `jerarquia: TicketHierarchy | undefined` sin decir cuál, y el que está más a mano en el render es el filtrado. Si el implementador toma `displayHierarchy`, un hijo o un hermano asignado a otra persona **no está en el árbol**: la regla 6 devuelve `foco: null` y todo vacío, **sin lanzar y sin explicar**. Es exactamente el *"panel vacío mudo"* que F6 regla 3 prohíbe, y rompe el KPI **K11** (la navegación de jerarquía) justo en el caso más común de un tablero compartido.
>
> **Regla dura:** la ficha recibe **`hierarchy`** (el crudo). El filtro "mías" es del tablero, no de la ficha: una ficha que oculta la mitad del árbol miente.
>
> **Regla 9 nueva (C6), con su test:** si `construirNavegacion` devuelve `foco: null` **y** la jerarquía **no** era `undefined/null`, `NavegacionJerarquia` expone `focoFueraDelArbol: true`, y la columna de jerarquía escribe *"Este ticket no está en el árbol cargado del proyecto activo."* en vez de tres listas vacías.

**Contrato exacto:**

```ts
import type { Ticket, TicketNode, TicketHierarchy } from "../types";

/** Espejo del tope del servidor (api/tickets.py:827) para no colgarse ante un ciclo. */
export const MAX_SALTOS_JERARQUIA = 50;

export interface NavegacionJerarquia {
  /** Del ancestro más lejano al padre directo. Vacío si el foco no tiene padre. */
  cadenaAncestros: TicketNode[];
  /** Hijos directos del foco, en el orden en que vienen del servidor. */
  hijos: TicketNode[];
  /** Otros hijos del mismo padre, EXCLUYENDO al foco. Vacío si no tiene padre. */
  hermanos: TicketNode[];
  /** El nodo del foco dentro del árbol, o null si el árbol no lo contiene. */
  foco: TicketNode | null;
  /** Motivo textual que el servidor ya calcula cuando el ticket quedó suelto. */
  motivoHuerfano: string | null;
  /** v2/C6 — true si el árbol vino cargado pero NO contiene al foco. Distingue
   *  "todavía no cargó" de "cargó y este ticket no está": la ficha tiene que
   *  DECIRLO, no mostrar tres listas vacías. */
  focoFueraDelArbol: boolean;
}

/** Deriva la navegación del foco desde el árbol cacheado. NO hace red. NO muta. */
export function construirNavegacion(
  jerarquia: TicketHierarchy | undefined | null,
  ticketId: number,
): NavegacionJerarquia;

/** Todos los nodos del árbol, aplanados, sin repetir, con tope de saltos. */
export function aplanarJerarquia(jerarquia: TicketHierarchy | undefined | null): TicketNode[];

/** Etiqueta corta para un salto de navegación: "1234 · Historia · En curso". */
export function etiquetaDeSalto(t: Pick<Ticket, "ado_id" | "work_item_type" | "ado_state">): string;
```

**Reglas de comportamiento (cada una es un test):**

1. `jerarquia` `undefined`/`null` → todo vacío, `foco: null`, `motivoHuerfano: null`. **Nunca lanza.**
2. El foco es una épica → `cadenaAncestros: []`, `hijos` = sus hijos, `hermanos: []`.
3. El foco es hijo directo de una épica → `cadenaAncestros: [epica]`, `hermanos` = los otros hijos de esa épica **sin el foco**.
4. El foco es nieto → `cadenaAncestros: [epica, padre]`, en ese orden (raíz primero).
5. El foco está en `orphans` → `cadenaAncestros: []`, `hermanos: []`, `motivoHuerfano` = el `motivo_huerfano` que vino en el nodo (o `null` si no vino).
6. El foco no está en el árbol → `foco: null` y todo lo demás vacío. **Nunca lanza.**
7. Un árbol con un ciclo artificial (nodo que se declara hijo de sí mismo en un fixture) **no cuelga**: `aplanarJerarquia` corta a `MAX_SALTOS_JERARQUIA` y devuelve lo recorrido.
8. `etiquetaDeSalto` con campos ausentes no imprime `undefined`: omite el segmento.
9. **(v2/C6)** Árbol **presente** pero sin el foco → `focoFueraDelArbol: true`. Árbol `undefined`/`null` → `focoFueraDelArbol: **false**` (todavía no sé, no es lo mismo). Foco presente → `false`.

**Archivo de test nuevo:** `Stacky Agents/frontend/src/services/__tests__/ticketDetailModel.test.ts`, con **9 tests**, uno por regla, nombrados `navegacion_arbol_vacio`, `navegacion_foco_epica`, `navegacion_foco_hijo_directo`, `navegacion_foco_nieto`, `navegacion_foco_huerfano_expone_motivo`, `navegacion_foco_ausente_no_lanza`, `aplanar_corta_ante_ciclo`, `etiqueta_omite_campos_ausentes`, **`navegacion_distingue_arbol_sin_cargar_de_foco_ausente`**.

> **Nota de forma del árbol, verificada en el servidor (`api/tickets.py:760-818`):** la anidación **es de profundidad arbitraria** — `ado_id_to_ticket[clave_padre]["children"].append(d)` cuelga dicts compartidos, así que un nieto queda dentro de su padre y el padre dentro de la épica. La regla 4 (`cadenaAncestros: [epica, padre]`) es implementable. **Dos límites reales que la ficha debe respetar:** (a) un ticket con `work_item_type == "epic"` **siempre** queda en el nivel superior (`:788-790`), aunque declare padre ⇒ para una épica hija, `cadenaAncestros` sale `[]` y eso es correcto respecto del dato; (b) `motivo_huerfano` **solo** viaja en `orphans` (`:810`), nunca en un nodo colgado.

**Comando (desde `Stacky Agents/frontend`):**

```bash
npx vitest run src/services/__tests__/ticketDetailModel.test.ts
```

**Criterio binario:** `9 passed`, y `npx tsc --noEmit` sigue en **exit 0** (es lo que prueba que la pata de `types.ts` se hizo). Los 9 fallan antes de escribir el módulo (por `Cannot find module`) y pasan después. **No hay ratchet de lista para vitest** — los ratchets de la interfaz son pruebas de barrido, ninguna registra archivos —, así que este archivo **no requiere registro** en ningún script.

---

### F5 — Interfaz: el enlace directo `?ticket=`, espejo exacto de `?exec=`

**Objetivo:** que `…/?ticket=1234` abra la ficha del ticket 1234, y que ese enlace sobreviva a copiar/pegar.
**Valor:** el operador puede compartirse a sí mismo el enlace de un ticket, igual que hoy con una ejecución.
**Flag:** `STACKY_TICKET_FULLVIEW_ENABLED` gobierna si el recubrimiento se **monta**; el router **siempre** parsea el parámetro (mantenerlo fuera de la flag es lo que hace que el enlace no se pierda al apagar/prender).
**Trabajo del operador:** ninguno.
**Runtimes:** neutro.

**Archivo a editar:** `Stacky Agents/frontend/src/services/routes.ts` (4 puntos, todos con símbolo):

*(v2/C11 — los 4 anclajes se re-midieron el 2026-08-02; los de la v1 estaban corridos entre −1 y −4. Manda el símbolo.)*

1. `export interface RouteState` (**`:25`**, la v1 decía `:26-31`; `exec?: number` está en **`:28`**, no en `:29`): agregar `ticket?: number;` con el comentario `// ?ticket=<id> — ficha del ticket (Plan 287)`.
2. `parseRoute` (**`:52`**, exacto): tras el bloque `for (const k of EXEC_KEYS)` (**`:65-75`**, la v1 decía `:67-79`), leer `ticket` con **la misma expresión estricta** `/^\d+$/` (la de `exec` está en **`:71`**, no en `:74`). Un `?ticket=` vacío, `?ticket=0x10` o `?ticket=1.5` dejan `ticket` en `undefined`.
3. El volcado de `query` es **una sola línea, `:77`** (la v1 decía `:80-81`), hoy:
   ```ts
   sp.forEach((v, k) => { if (!EXEC_KEYS.includes(k as typeof EXEC_KEYS[number])) query[k] = v; });
   ```
   Excluir también `"ticket"`. **Si esto falta, el round-trip duplica el parámetro.**
4. `serializeRoute` (**`:111`**, exacto): tras la línea de `exec` (**`:121`**, exacto), emitir `if (s.ticket != null) sp.set("ticket", String(s.ticket));`.
5. `normalizeInitial` está en **`:85`** (la v1 decía `:88`). **No se toca**, ver el recuadro de abajo.

> **`normalizeInitial` (`:88`) NO se toca.** Su regla de `exec` (normalizar el tab a `history`) no aplica: `ticket` es válido en la raíz `"/"`, que ya **es** el tablero (`TAB_PATHS.tickets === "/"`, `:16`). Agregarle una rama sería inventar un requisito que no existe. Si `?ticket=` viene con otro tab (p. ej. `/devops?ticket=9`), el parámetro **se conserva y se ignora**: la ficha vive en el tablero.

**Tests: se agregan a los DOS archivos que ya existen** (así no nacen archivos nuevos y se reusa el `split()` que ya tienen):

`Stacky Agents/frontend/src/services/__tests__/routes.test.ts` — 4 tests nuevos:
- `parse_ticket_canonico` — `parseRoute("/", "?ticket=1234").ticket === 1234`
- `parse_ticket_no_numerico` — `?ticket=abc` → `undefined`, y `query` **no** contiene `ticket`
- `parse_ticket_vacio_y_formas_raras` — `?ticket=`, `?ticket=0x10`, `?ticket=1.5`, `?ticket=-3` → los 4 `undefined`
- `serialize_ticket_roundtrip` — `serializeRoute(parseRoute(...split("/?ticket=7")))` devuelve exactamente `"/?ticket=7"`

`Stacky Agents/frontend/src/services/__tests__/routesDeepLink.test.ts` — 2 tests nuevos:
- `deeplink_ticket_en_raiz` — `/?ticket=88` → `{tab: "tickets", ticket: 88}`
- `deeplink_ticket_convive_con_exec` — `/?exec=5&ticket=9` → `tab` se normaliza a `history` por la regla vigente de `exec`, **y `ticket` sobrevive en el estado** (no se pierde ni pasa a `query`)

**Comandos:**

```bash
npx vitest run src/services/__tests__/routes.test.ts
npx vitest run src/services/__tests__/routesDeepLink.test.ts
```

**Criterio binario:** los dos archivos verdes, con **+4 y +2** tests respecto de los baselines **medidos** en F0.1: `routes.test.ts` **17 → 21 passed**, `routesDeepLink.test.ts` **6 → 8 passed**. El conteo absoluto solo vale porque el delta está anclado a un número medido, no supuesto.

> **C14 — límite honesto del `deeplink_ticket_convive_con_exec`.** `normalizeInitial` (`:85-88`) fuerza `tab: "history"` cuando hay `exec`, y la ficha vive en el tablero (`tab: "tickets"`). Entonces `/?exec=5&ticket=9` deja `ticket: 9` **en el estado** pero **no abre la ficha**, porque `TicketBoard` ni siquiera se monta. El test verifica **la supervivencia del parámetro**, no la apertura de la ficha — y su nombre y su comentario tienen que decirlo, o el próximo lector va a creer que el caso combinado funciona. El caso soportado de punta a punta es `?ticket=` **en la raíz**.

---

### F6 — Interfaz: la ficha

**Objetivo:** la pantalla.
**Flag:** `STACKY_TICKET_FULLVIEW_ENABLED` (ON), leída con `readCachedBoolFlag` (síncrona, fail-open).
**Trabajo del operador:** ninguno.
**Runtimes:** neutro — **gate F8.3: cero menciones de `codex`/`claude`/`copilot` en los archivos de esta fase.**

**Archivos nuevos (2):**
- `Stacky Agents/frontend/src/components/ticket/TicketFullView.tsx`
- `Stacky Agents/frontend/src/components/ticket/TicketFullView.module.css`

**Esqueleto obligatorio del componente:**

```tsx
// v2/C3 — FORMA OBLIGATORIA: import CON LLAVES desde el BARRIL `../ui`.
// `import Dialog from "../ui/Dialog"` (lo que decía la v1) NO matchea
// UI_DIALOG_IMPORT_RE del ratchet: exige llaves y ruta terminada en `ui`.
import { Dialog } from "../ui";
import styles from "./TicketFullView.module.css";

export interface TicketFullViewProps {
  ticketId: number;
  jerarquia: TicketHierarchy | undefined;    // el árbol YA cacheado por el tablero
  onCerrar: () => void;
  onCambiarFoco: (id: number) => void;       // navegación sin cerrar
}

export default function TicketFullView({ ticketId, jerarquia, onCerrar, onCambiarFoco }: TicketFullViewProps) {
  const nav = construirNavegacion(jerarquia, ticketId);   // ← F4, puro
  // ... 5 useQuery: byId, comments, attachments, historial, capacidades
  return (
    <Dialog open bare panelClassName={styles.ficha}
            onClose={onCerrar} ariaLabel={`Ficha del ticket ${ticketId}`}>
      {/* cabecera + 3 columnas */}
    </Dialog>
  );
}
```

**Restricciones de estilo — verificadas por ratchet, no negociables:**

| Regla | Por qué | Cómo se verifica |
|---|---|---|
| **Cero** colores hex (`#rrggbb`) en `TicketFullView.module.css` | Archivo nuevo ⇒ **no está en `uiDebtBaseline.json`** ⇒ `allowedBase = 0` (`src/__tests__/uiDebtRatchet.test.ts:97` en adelante, la línea `?? 0`); cualquier hex es `count > allowed` y rompe | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` |
| **Cero** `style={{` en `TicketFullView.tsx` | Misma regla, dimensión `inlineStyleByFile` | idem |
| **Cero** `confirm(` / `alert(` / `prompt(` nativos | `nativeDialogByFile` es **forzado a 0 absoluto** para todo archivo, y el propio comentario dice que ni un `UI_DEBT_REGEN` futuro puede resubirlo (`uiDebtRatchet.test.ts:109-113`) | idem |
| Importar `Dialog` **con llaves, del barril**: `import { Dialog } from "../ui";` | **v2/C3.** El detector marca todo `.tsx` con `role="dialog"`\|`aria-modal`\|`createPortal(` y solo perdona si matchea `UI_DIALOG_IMPORT_RE` = `/import\s+\{[^}]*\bDialog\b[^}]*\}\s+from\s+["'][^"']*ui["']/`, que exige **llaves** y ruta **terminada en `ui`**. El `import Dialog from "../ui/Dialog"` de la v1 **no matchea**. Y la allowlist **no tiene lugar**: ya está rota con 2 detectados fuera + 1 stale (§4.2) | `npx vitest run src/__tests__/adhocModalRatchet.test.ts` — **delta**: los ofensores tienen que seguir siendo exactamente `ContextMenu.tsx` + `PeekCard.tsx` (fuera) y `ShortcutsCheatsheet.tsx` (stale) |
| **Nunca escribir `aria-modal`, `role="dialog"` ni `createPortal(` a mano en `TicketFullView.tsx`** | Los aporta `Dialog` (`Dialog.tsx:192`, `:203`). Si el archivo los trae por su cuenta, `DETECT_RE` dispara y hay que depender del import — que solo funciona en la forma de arriba | idem |
| **No usar `--text-faint`** para texto informativo | Está fuera de contraste accesible (auditoría 2026-07-29). Usar `--text-muted` | revisión + `npx vitest run src/__tests__/themeContrast.test.ts` sigue verde |

**Tokens disponibles y verificados en `frontend/src/theme.css`** (no inventar): superficies `--bg-base --bg-panel --bg-elev --border --border-muted`; texto `--text-primary --text-muted`; estado `--status-{success,warning,danger,info}-{text,solid,bg,border}` y `--status-neutral-{text,bg,border}`; acento `--accent --accent-hot --success --warn --danger`; tipografía `--font-sans --font-mono --text-2xs … --text-2xl --weight-*`; espaciado `--space-1 … --space-9`; geometría `--radius --radius-sm --radius-md --radius-lg --radius-full`; sombras `--shadow-1 --shadow-2 --shadow-3 --shadow-overlay`; foco `--focus-ring`; capa `--z-dialog` (= 9700).
**No existe ningún token `--color-*`** salvo `--color-scheme` (`theme.css:163`). Escribir `var(--color-primary)` **degrada en silencio**, no rompe: el color simplemente no se aplica.

**Layout — 3 columnas, densidad alta:**

```
┌───────────────────────────────────────────────────────────────────────┐
│ #1234 · Historia · En curso     Titulo del ticket        [Abrir en ▸] [✕]│
├──────────────┬────────────────────────────────┬───────────────────────┤
│ JERARQUIA    │ CONTENIDO                      │ FICHA Y ACCIONES      │
│              │                                │                       │
│ Ancestros ▸  │ Descripcion                    │ Asignado a            │
│  #10 Epica   │ Comentarios (N)                │ Prioridad             │
│  #42 Feature │ Historial de cambios (N)       │ Estado / Ultima sync  │
│              │                                │ Progreso del pipeline │
│ Hijos (N)    │                                │ Adjuntos (N)          │
│  #77 …       │                                │ ─────────────         │
│  #78 …       │                                │ Acciones (F7)         │
│ Hermanos (N) │                                │ Ejecuciones (N)       │
└──────────────┴────────────────────────────────┴───────────────────────┘
```

**Comportamiento obligatorio:**

1. **Escape cierra.** Lo aporta `Dialog`; **no** registrar un atajo global propio (el precedente `CodexConsoleFull.tsx:132-134` lo advierte: el Escape lo maneja el contenedor, nunca el registro global).
2. **Navegar no cierra.** Un click en un ancestro / hijo / hermano llama a `onCambiarFoco(id)`; la ficha **sigue abierta** y el contenido se recarga. El tablero de fondo no se remonta.
3. **Cada panel declara su estado.** Si `capacidades[clave].estado === "partial"`, el panel muestra un aviso corto con `capacidades[clave].perdida`. Si es `absent`, muestra "Este sistema de tickets no ofrece este dato" en lugar de una lista vacía. **Nunca un panel vacío mudo.**
4. **El huérfano dice por qué.** Si `nav.motivoHuerfano` no es `null`, la columna de jerarquía lo muestra en vez de "sin padre". (Esto cierra K6.)
5. **El historial se consulta solo al abrirse.** `useQuery({ ..., enabled: panelHistorialAbierto })`. Sin esto, abrir una ficha dispara una llamada al tracker que el operador no pidió.
6. **Errores legibles.** Los 5 `useQuery` usan `formatLoadErrorMessage` (`frontend/src/utils/loadError.ts`, ya usado por `CodexConsoleFull.tsx:24`). Si hace falta leer el cuerpo de una respuesta no-2xx, usar `rawGet` de `api/client.ts:100` — el wrapper `api.*` **lanza** en non-2xx y se pierde el cuerpo.
7. **Un solo montaje.** Si la flag está OFF, `TicketFullView` **no se monta** y el botón de apertura no se pinta.

**Endpoints nuevos en `frontend/src/api/endpoints.ts`,** dentro del objeto `Tickets` que abre en `:188`, pegados después de `attachments` (`:453`):

```ts
  historial: (id: number) =>
    api.get<{ historial: { fecha: string|null; autor: string|null; campo: string|null; de: string|null; a: string|null }[];
              tracker: string;
              capacidad: { clave: string; estado: string; perdida: string } }>(
      `/api/tickets/${id}/historial`),
  capacidades: () =>
    api.get<{ tracker: string; capacidades: Record<string, { estado: string; perdida: string }> }>(
      `/api/tickets/capacidades`),
```

**Criterio binario de F6:**

```bash
npx tsc --noEmit                                              # exit 0 (baseline F0.1 #7)
npx vitest run src/__tests__/themeContrast.test.ts            # 4 passed
npx vitest run src/__tests__/a11yCss.test.ts                  # 3 passed
npx vitest run src/__tests__/uiDebtRatchet.test.ts            # ROJO DE FABRICA: MISMAS 5 regresiones de §4.2, NI UNA MAS
npx vitest run src/__tests__/adhocModalRatchet.test.ts        # ROJO DE FABRICA: MISMOS 3 ofensores de §4.2, NI UNO MAS
```

> **v2/C2 — los dos últimos NO pueden dar "verde" y exigirlo bloquearía el cierre del plan.** El criterio es **delta**: la salida tiene que nombrar **exactamente** los ofensores de §4.2. Si aparece `components/ticket/TicketFullView.tsx` o `.module.css` en cualquiera de las dos listas, **es regresión de este plan**.

Más tres conteos que se corren y tienen que dar exactamente eso:
- `grep -c 'style={{' "…/components/ticket/TicketFullView.tsx"` → **0**
- `grep -cE '#[0-9a-fA-F]{3,8}\b' "…/components/ticket/TicketFullView.module.css"` → **0**
- `grep -cE 'import \{[^}]*Dialog[^}]*\} from "\.\./ui"' "…/components/ticket/TicketFullView.tsx"` → **1** *(v2/C3: la v1 congelaba `grep -c 'from "../ui/Dialog"'` → 1, que **no prueba nada** contra el ratchet y cementa la forma que el detector no perdona)*
- `grep -cE 'aria-modal|role="dialog"|createPortal\(' "…/components/ticket/TicketFullView.tsx"` → **0**

---

### F7 — Interfaz: cableado desde el tablero y desde el grafo, y las acciones in-situ

**Objetivo:** que la ficha se abra desde los dos lugares donde el ticket ya se ve, sin robarle el click al despliegue actual.
**Flag:** `STACKY_TICKET_FULLVIEW_ENABLED` (ON).
**Trabajo del operador:** ninguno — el gesto que ya conoce (click = desplegar) **no cambia**; se **suma** un botón.
**Runtimes:** neutro.

**Archivos a editar (4 — la v1 decía 3 y le faltaba el que hace vivir al enlace directo):**

> #### C4 — BLOQUEANTE de la v1: `?ticket=` **nunca llegaba a la ficha**
>
> La v1 decía que `fichaTicketId` se inicializa *"desde `?ticket=` (la ruta ya lo parsea, F5)"*. Pero, verificado el 2026-08-02:
> - `App.tsx:412` monta **`{tab === "tickets" && <TicketBoard />}`** — **sin una sola prop**.
> - `TicketBoard` es `export default function TicketBoard()` (`:923`) — **sin parámetros**.
> - `App.tsx` **no estaba en la lista de archivos de ninguna fase**.
>
> **`TicketBoard` no tenía forma de leer la ruta.** Y el precedente que el propio plan invoca hace exactamente lo que la v1 omitía: `App.tsx:421` → `<ExecutionHistoryPage exec={route.exec ?? null} />`. La v1 copiaba la mitad del espejo (el router) y dejaba la otra mitad (el cableado de la prop) sin escribir: F5 quedaba **construido y jamás cableado**, §3.2 entera sin cumplir, el paso 6 del humo imposible y el DoD falso.

0. **`Stacky Agents/frontend/src/App.tsx`** — **la pata que faltaba (C4).** Una sola línea, espejo exacto de `:421`:
   ```tsx
   {tab === "tickets"  && <TicketBoard ticket={route.ticket ?? null} />}
   ```
   **No agrega ningún gate** (`grep -c 'useState<GateState>("unknown")' App.tsx` sigue dando **8**, y por eso `plan273GateState.test.ts` sigue con sus mismas 2 fallidas de §4.2). No toca `probeFlagHealth` (`:183-208`). Es aditivo y no cambia el orden de inicialización: `parseRoute` ya corre síncrono en el `useState` de **`:83-85`** (verificado).

1. **`Stacky Agents/frontend/src/pages/TicketBoard.tsx`** — el dueño del estado. Aquí se monta la ficha una sola vez para toda la pantalla.
   - **Firma nueva (C4):** `export default function TicketBoard({ ticket = null }: { ticket?: number | null })` (`:923`). El default `null` mantiene la compatibilidad con cualquier otro montaje.
   - En `TicketBoard()`: `const [fichaTicketId, setFichaTicketId] = useState<number | null>(ticket)`.
   - **Sincronización con `popstate` (C4):** `useEffect(() => { setFichaTicketId(ticket); }, [ticket])`. Sin esto, el botón Atrás del navegador cambia `route.ticket` en `App` y la ficha se queda mostrando el ticket anterior. `route` **es estado vivo** en `App` (`:81-85` lo dice: *"la ruta es ESTADO (no un ref congelado): popstate y la navegación in-app la actualizan"*), así que la prop sí llega.
   - En `TicketCard` (`:304`): un botón nuevo **"Abrir ficha"** (`IconButton` — **ya importado** en `:61` — con el ícono `Maximize2` de `lucide-react`, el mismo que ya usa `CodexConsoleDock.tsx:2`).
     **Dónde exactamente:** dentro del `<div className={styles.cardActions} …>` que abre en **`:527`**, como **hermano** del `.map(...)` de `quickActions` (`:531`), inmediatamente **antes** de él.
     **Por qué ahí y no dentro de `quickActions`:** ese contenedor **ya trae `onClick={(e) => e.stopPropagation()}` en su propia línea `:527`** (verificado), así que el botón queda protegido del `onClick` que despliega la tarjeta (`:498-501`) **sin agregar un `stopPropagation` nuevo**. Y meterlo *dentro* de `quickActions` sería otra cosa: esa lista sale del catálogo de acciones filtrado con doble cerrojo (comentario en `:528-530`), lo que obligaría a dar de alta la acción en el catálogo y arrastraría el ratchet del catálogo de acciones. **No se hace.**
   - Al final del render de `TicketBoard` (después del `<RunModal>` de **`:745`**, en el ámbito de la página, no de la tarjeta): montar `{fullViewOn && fichaTicketId != null && <TicketFullView ticketId={fichaTicketId} jerarquia={hierarchy} … />}`, donde `fullViewOn = readCachedBoolFlag("STACKY_TICKET_FULLVIEW_ENABLED")` (`services/flagGate.ts:70`, síncrono y fail-open a ON — verificado).
   - **`jerarquia={hierarchy}`, el crudo de `:1001-1003`. NUNCA `displayHierarchy` (`:1029`), que está filtrado por "mías" — ver C6 en F4.**
   - `onCambiarFoco` hace `setFichaTicketId(id)` **y** actualiza la URL con `history.replaceState` usando `serializeRoute` (no `pushState`: no queremos una entrada de historial por cada salto de jerarquía).
   - `onCerrar` hace `setFichaTicketId(null)` **y** quita `?ticket=` de la URL.

2. **`Stacky Agents/frontend/src/components/TicketGraphView.jsx`** — una prop nueva `onAbrirFicha` en `TicketNodeCard` (`:324`) y un botón en el `<div className={styles.nodeTopRow}>` que abre en **`:412`**.
   **Acá SÍ hace falta `stopPropagation` propio, y es asimétrico respecto del tablero:** `nodeTopRow` **no** tiene contenedor que frene la propagación (verificado: los `stopPropagation` de este archivo están en `:126, :441, :460, :470, :485, :497, :512, :526`, ninguno envuelve la cabecera), y la tarjeta entera lleva el `onClick` que expande en **`:398`**. El botón se escribe exactamente con la forma que ya usa `:441`:
   ```jsx
   onClick={e => { e.stopPropagation(); onAbrirFicha(ticket.id); }}
   ```
   > **Decisión consciente sobre este archivo:** `TicketGraphView.jsx` es `.jsx` y `tsconfig.json` **no tiene `allowJs`** ⇒ `npx tsc --noEmit` **no lo cubre**. Este plan **no lo migra a `.tsx`** — esa migración son 756 líneas con `STATE_COLORS` (`:49`), `COLORES_GITLAB` (`:63`) y `EPIC_COLORS` (`:88`) en hex crudo, y es una fase con costo propio, no un efecto colateral. El cambio de este plan sobre ese archivo es **una prop y un botón**, y su corrección se verifica a mano en el smoke §9.2, no por compilador. **Está declarado como riesgo R3.**

3. **`Stacky Agents/frontend/src/api/endpoints.ts`** — las 2 funciones de F6, dentro del objeto `Tickets` que abre en **`:188`**, pegadas después de `attachments` (**`:453-454`**). Ambos anclajes verificados.

**Las acciones in-situ: se REUSAN, no se reescriben.** Dentro de la columna derecha de la ficha se montan los componentes que ya existen, con las mismas props que hoy reciben en `TicketBoard.tsx`:

| Componente | Ruta | Qué hace | Confirmación |
|---|---|---|---|
| `FinishWorkButton` | `components/FinishWorkButton.tsx:37` | cierra el trabajo del ticket | la suya, ya existente |
| `CreateChildTaskButton` | `components/CreateChildTaskButton.tsx:53` | crea tareas hijas (**solo si el foco es épica**) | su propio diálogo con motivo y ensayo en seco (`:213-235`) |
| `JerarquiaLocalControl` | `components/JerarquiaLocalControl.tsx:31` | tipo y padre local de GitLab | la suya |
| `TicketLocalInsightButton` | `components/TicketLocalInsightButton.tsx:26` | análisis local del ticket | la suya |
| `TicketFingerprint` | `components/TicketFingerprint.tsx:40` | señales del ticket | solo lectura |
| `TrackerDeepLink` | `components/TrackerDeepLink.tsx:19` — **export NOMBRADO** (`export function TrackerDeepLink`), no default, a diferencia de los otros 5 | abrir en Azure DevOps / GitLab | solo lectura |

**Las 6 rutas y líneas se verificaron abriendo los archivos el 2026-08-02: 6 de 6 exactas.**

> #### C10 — un popover de la allowlist adentro de un `Dialog` con trampa de foco
>
> `CreateChildTaskButton.tsx` está **en `adhocModalAllowlist.json`** con la razón *"popover anclado al botón, no es un diálogo modal"*. La ficha lo monta **dentro** de un `Dialog` con portal, trampa de foco, restauración de foco y `--z-dialog: 9700`. La v1 no dice qué pasa con ninguna de las tres cosas.
>
> **Riesgo real:** un popover que renderiza fuera del subárbol del diálogo queda **inalcanzable por teclado** dentro de la trampa de foco, y un Escape puede cerrar la ficha entera en vez del popover.
>
> **Mitigación (R13):** el componente **no se modifica** (sigue fuera de scope tocarlo). Se agrega el **paso 8 del humo**: abrir "crear tarea hija" desde la ficha en una épica, confirmar con teclado que (a) el popover recibe foco, (b) el primer Escape cierra el popover y **no** la ficha, (c) el segundo Escape cierra la ficha. Si alguna de las tres falla, la acción se **omite de la ficha** en esta entrega y se deja anotada como deuda — la ficha sigue siendo valiosa sin ella.

**Ni una acción de escritura nueva.** Este plan no agrega un solo camino que escriba al tracker. Es lo que lo mantiene barato y compatible con el lazo humano.

**Criterio binario de F7:**

```bash
npx tsc --noEmit                                       # 0 errores
npx vitest run src/__tests__/uiDebtRatchet.test.ts     # verde (TicketBoard.tsx no sube su deuda)
```

Más tres conteos, **asimétricos a propósito** (los valores de hoy están medidos, así que el criterio es exacto y no "≥"):

| Conteo | Hoy (2026-08-02) | Después de F7 | Por qué |
|---|---|---|---|
| `grep -c "stopPropagation" "…/pages/TicketBoard.tsx"` | **12** | **12** — sin cambio | El botón entra en un contenedor que ya lo trae (`:527`). **Si este número sube, el botón se puso en el lugar equivocado.** |
| `grep -c "stopPropagation" "…/components/TicketGraphView.jsx"` | **8** | **9** | La cabecera del nodo no tiene contenedor protegido: el botón trae el suyo |
| `grep -c 'style={{' "…/pages/TicketBoard.tsx"` | **15** | **15** — sin cambio | El botón nuevo usa clases, no estilo en línea. `TicketBoard.tsx` ya tiene 15 de deuda en el baseline del ratchet: **puede bajar, nunca subir** |

---

### F8 — Cierre: documentación, paridad y el barrido final

**Objetivo:** dejar el sistema consistente y demostrar que nada verde se puso rojo.
**Flag:** ninguna.
**Trabajo del operador:** ninguno.

**F8.1 — Documentación del sistema.** Actualizar, con el cambio **mínimo** (los tres archivos son cortos: 95, 37 y 78 líneas):
- `Stacky Agents/docs/sistema/04-api.md`: **2 filas nuevas** en la tabla que abre en `:56` (`## tickets (/api/tickets) — endpoints clave`), con el mismo formato de las filas `:59-79`, e incluyendo la flag que las gatea como hace la fila `:79`:
  ```
  | GET `/<id>/historial` | historial de cambios del ticket, por el puerto TrackerProvider (gated `STACKY_TICKET_HISTORY_API_ENABLED`) |
  | GET `/capacidades` | qué soporta el tracker activo y con qué pérdida (gated `STACKY_TRACKER_CAPABILITIES_API_ENABLED`) |
  ```
- `Stacky Agents/docs/sistema/07-frontend.md`: agregar la ficha a la lista de pantallas, **aclarando que NO es un tab** sino un recubrimiento montado sobre el tablero, para que ningún censo futuro la cuente como el tab número 20.
- `Stacky Agents/docs/sistema/08-configuracion-flags.md`: las 3 flags nuevas con su default ON.

**F8.2 — Estado del plan.** Escribir al final de **este** documento una sección `## Estado de implementación` con: fase, commit, y la **salida literal** de cada comando de aceptación. Sin salida pegada, la fase no está cerrada.

**F8.3 — Gate de neutralidad de runtime.** Desde `Stacky Agents`, sobre los **6** archivos nuevos del plan (v2 sumó `plan287_updates.py`; y `types.ts`/`App.tsx`/`TicketBoard.tsx` **no entran**: son archivos preexistentes que ya nombran runtimes por otras razones):
```bash
grep -riE "codex|claude|copilot" \
  "frontend/src/components/ticket/TicketFullView.tsx" \
  "frontend/src/components/ticket/TicketFullView.module.css" \
  "frontend/src/services/ticketDetailModel.ts" \
  "frontend/src/services/__tests__/ticketDetailModel.test.ts" \
  "backend/tests/test_plan287_ficha_ticket.py" \
  "backend/tests/fixtures/plan287_updates.py"
```
**Criterio binario: 0 hits.**

> **(v2/C15) Ojo con el `-i`:** el patrón es amplio y `claude` aparece en rutas del entorno del operador. Correr el `grep` con **rutas relativas desde `Stacky Agents`** (como está escrito), nunca con rutas absolutas, para que ningún directorio del árbol de trabajo contamine el resultado. Si un día da un falso positivo, se acota a `\bcodex\b|\bcopilot\b|claude[ _-]?code`.

**F8.4 — Segundo barrido: los 9 gates de F0.1, otra vez.** Se vuelven a correr los 9 comandos de F0.1 y se compara **contra los números medidos en esa tabla**:
- Los verdes (3, 4, 6, 7, 9): **siguen verdes**, con `routes.test.ts` en **21** y `routesDeepLink.test.ts` en **8**.
- **Los 4 rojos de fábrica (1, 2, 5, 8) mantienen EXACTAMENTE la lista de ofensores de §4.2.** Ni "pasan a verde" (insatisfacible) ni suman uno. En particular: `plan273GateState.test.ts` = `2 failed | 12 passed (14)`; `uiDebtRatchet` = las 5 regresiones ajenas; `adhocModalRatchet` = `ContextMenu.tsx` + `PeekCard.tsx` fuera y `ShortcutsCheatsheet.tsx` stale; `test_harness_flags_help.py` = las mismas 4, con `grep -c` de las 3 keys del plan = **`0`**.
- Más las suites nuevas/extendidas: `test_plan287_ficha_ticket.py` (**21**), `ticketDetailModel.test.ts` (**9**), `routes.test.ts` (**+4**), `routesDeepLink.test.ts` (**+2**).
- Más los dos conteos de cableado que prueban que nada quedó construido-y-sin-conectar: `grep -c '<TicketBoard ticket=' frontend/src/App.tsx` → **1**, y `grep -c 'motivo_huerfano' frontend/src/types.ts` → **1**.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta, en el plan) |
|---|---|---|---|
| **R1** | Los anclajes `archivo:línea` se corren por la sesión paralela | **Alta** | **F0.0**: barrido por símbolo antes de tocar nada, y toda instrucción de inserción está dada también por símbolo |
| **R2** | El recubrimiento nuevo rompe un ratchet de deuda visual | Media | F6 fija las 5 reglas de estilo como criterio binario y nombra el comando de cada una. Un archivo nuevo tiene base **0**: no hay margen, y por eso está escrito |
| **R3** | `TicketGraphView.jsx` no lo cubre `tsc` y el cableado rompe en tiempo de ejecución | Media | Declarado explícitamente en F7. El cambio es **una prop y un botón**; se verifica en el smoke manual §9.2. La migración a `.tsx` está **fuera de scope** y dicho por qué |
| **R4** | El botón nuevo se come el click de desplegar la tarjeta | **Alta si no se dice** | F7 lo resuelve **asimétricamente y con evidencia**: en `TicketBoard.tsx` el botón va dentro de `styles.cardActions` (`:527`), que **ya** trae `stopPropagation`, y el conteo del archivo debe quedar en **12 sin cambio**; en `TicketGraphView.jsx` la cabecera (`:412`) **no** tiene contenedor protegido y el botón trae el suyo, llevando el conteo de **8 a 9**. Los dos `onClick` conflictivos están citados (`TicketBoard.tsx:498-501`, `TicketGraphView.jsx:398`) |
| **R5** | El panel de historial dispara una llamada al tracker por cada ficha abierta | Media | F6 regla 5: `enabled:` atado al panel visible. Es también lo que mantiene la flag fuera de la categoría (A) |
| **R6** | El `?ticket=` se duplica en la URL al serializar | Media | F5 punto 3 lo nombra: excluir `"ticket"` del volcado verbatim de `query`, con el test `serialize_ticket_roundtrip` que lo prueba |
| **R7** | Registrar el archivo de tests en los ratchets antes de crearlo pone rojas dos suites ajenas | Media | F3: registro **en el mismo commit** que crea el archivo, con los dos guardianes nombrados |
| **R8** | La entrada nueva en `run_harness_tests.ps1` rompe el array por falta de coma | **Alta** | F3 lo dice literal: la última entrada de hoy **no tiene coma** y hay que agregársela |
| **R9** | Alguien "arregla" `plan273GateState.test.ts` creyendo que lo rompió este plan | Media | §4.2 lo declara rojo de fábrica con el `grep -c` que lo prueba, y F8.4 exige que quede **igual** |
| **R10** | Un token CSS inventado (`--color-*`) no rompe: degrada en silencio | Media | F6 lista los tokens que **existen** y avisa que `--color-*` no existe salvo `--color-scheme` |
| **R11** | El nuevo endpoint termina siendo ADO-only sin que nadie lo note | Baja | F1 rutea por `get_tracker_provider` (seam reconocido) y el criterio incluye correr `test_plan281_ratchet_ado_only.py`, cuyo `test_ningun_sitio_nuevo_lee_tracker_type_para_rutear` exige `vivos == []` |
| **R12** | Colisión de número de plan con la sesión paralela | Media | `ls "Stacky Agents/docs" \| grep -E "^28[0-9]_"` **justo antes de commitear**. Ya pasó el 2026-08-01 con el 280 duplicado |
| **R13** *(v2/C10)* | El popover de `CreateChildTaskButton` queda inalcanzable o roba el Escape dentro del `Dialog` | Media | Paso 8 del humo §9.2, con la salida documentada: si falla, la acción se omite de la ficha y queda como deuda |
| **R14** *(v2/C1)* | **El panel de historial nace MUDO**: los dos adaptadores no comparten ni una clave y un normalizador único devuelve las 5 en `None` | **Alta — era el defecto real de la v1** | Tabla de mapeo por tracker en F1 + fixtures reales en F1.5 + `test_ninguna_fila_sale_toda_en_None`, que **tiene que fallar** con la implementación de la v1 |
| **R15** *(v2/C2)* | Alguien "arregla" `uiDebtRatchet` o `adhocModalRatchet` creyendo que este plan los rompió, y toca deuda ajena (`DocumenterResultPanel.tsx`, `ContextMenu.tsx`, …) | **Alta** | §4.2 los declara con la lista **exacta** de ofensores y el criterio es delta. **Arreglarlos NO es de este plan** (§8.10) |
| **R16** *(v2/C6)* | La ficha recibe el árbol filtrado y la navegación a un hermano ajeno muere en silencio | Media | Regla dura en F4/F7 (`hierarchy`, nunca `displayHierarchy`) + `focoFueraDelArbol` con mensaje visible |

---

## 8. Fuera de scope (explícito, para que nadie lo agregue de contrabando)

1. **Editar el ticket desde la ficha** (cambiar título, descripción, estado o asignado escribiendo al tracker). Es un camino de escritura nuevo: exige su propia flag OFF por categoría (B) y su propio plan.
2. **Publicar un comentario desde la ficha.** Ídem. El puerto ya tiene `post_comment` (`tracker_provider.py:88`), pero exponerlo es escritura.
3. **Migrar `TicketGraphView.jsx` a `.tsx`.** 756 líneas y tres tablas de color en hex crudo. Fase con costo propio (R3).
4. **Convertir la ficha en un tab con ruta propia.** Medido y descartado en §3.1.
5. **Unificar `TicketCard` (`TicketBoard.tsx:304`) con `TicketNodeCard` (`TicketGraphView.jsx:324`).** Son dos gemelos divergentes y consolidarlos es deuda real, pero es otra pelea: este plan **agrega** la ficha, no refactoriza las tarjetas.
6. **Migrar los dos `RunModal` hechos a mano** (`TicketBoard.tsx:127`, `TicketGraphView.jsx:111`) a la primitiva `Dialog`. Deuda conocida, no de este plan.
7. **Publicar la matriz de capacidades entera.** F2 publica **4 claves congeladas**, las que la ficha necesita.
8. **Cachear el historial en base local.** La consulta es bajo demanda y vive en la caché de la sesión.
9. **Arreglar los rojos de fábrica de §4.2.** Son deuda de los planes 283 y 284/285.
10. **(v2/C2) Sanear `uiDebtRatchet` y `adhocModalRatchet`.** Los dos están rojos por trabajo **ajeno** (`DocumenterResultPanel.tsx`, `DocsPage.tsx`, `DocumenterButton.tsx`, `ExecutionDetailDrawer.module.css`, `RunReconciliationCard.module.css`, `ContextMenu.tsx`, `PeekCard.tsx`, `ShortcutsCheatsheet.tsx`). Tocarlos acá sería robarle el diff a otro plan y hacer imposible atribuir una regresión. **Se declaran y se congelan, no se arreglan.**
11. **(v2/C13) Etiquetas, hitos, relaciones y ramas/PR vinculados en la ficha.** Es la omisión más grande frente a la vista nativa: ADO muestra *tags*, *area/iteration path*, *effort* y *links* (related / blocked-by / duplicate); GitLab muestra *labels*, *milestone*, *time tracking* y *MRs vinculadas*. **Nada de eso entra en esta entrega** — el layout de 3 columnas no le reserva lugar y traerlo exige tocar `get_item`/`fetch_*` en los dos adaptadores. La ficha v1 igual supera a las dos vistas nativas en lo que sí trae (jerarquía navegable sin salir + el aviso de pérdida), pero **el plan no puede decir "toda la información útil" hasta que esto exista**: queda como el candidato natural al plan siguiente.

---

## 9. Orden de implementación, humo y Definición de Hecho

### 9.1 Orden (estricto: cada paso depende del anterior)

1. **F0.0** — barrido de **15** patrones. Si algo no imprime, parar.
2. **F0.1** — correr los **9** gates y confirmar que coinciden con los números **medidos** de la tabla.
3. **F0.2** — las 3 flags, las 6 patas, un commit. Verificar el `grep -c` = `0` de C8.
4. **F1** — fixtures + tabla de mapeo por tracker → los **12** tests (rojos) → ruta `/historial` → verdes.
5. **F1.5** *(v2, [ADICIÓN ARQUITECTO])* — `tests/fixtures/plan287_updates.py` + los **3** del centinela de forma. **Correr `test_paridad_forma_updates_ninguna_fila_muda` contra la implementación ingenua de la v1 y confirmar que FALLA** antes de dar la fase por buena.
6. **F2** — corregir el texto de C9 en `provider_capabilities.py` → tests de capacidades (rojos) → ruta `/capacidades` → verdes (**21** en el archivo).
7. **F3** — registrar `test_plan287_ficha_ticket.py` en los DOS scripts, mismo commit conceptual que F1/F1.5/F2.
8. **F4** — **primero `types.ts`** (C5, o no compila), después `ticketDetailModel.ts` con sus **9** tests (rojos primero).
9. **F5** — `?ticket=` en el router: 17→21 y 6→8.
10. **F6** — `TicketFullView.tsx` (con `import { Dialog } from "../ui"`, C3) + `.module.css` + las 2 funciones de `endpoints.ts`.
11. **F7** — **`App.tsx` primero** (C4, la prop `ticket`), después el cableado desde `TicketBoard.tsx` (con `hierarchy`, C6) y `TicketGraphView.jsx` + acciones reusadas.
12. **F8** — documentación, gate de neutralidad de runtime, segundo barrido.

### 9.2 Humo manual (10 pasos, se hace una vez al final)

1. Levantar la aplicación en un proyecto **Azure DevOps**. Abrir el tablero.
2. Click en **"Abrir ficha"** de una épica → se abre a pantalla completa; **la tarjeta de atrás NO se desplegó** (R4).
3. En la columna izquierda, click en un **hijo** → el contenido cambia, **la ficha sigue abierta**, la URL muestra `?ticket=<hijo>`.
4. Abrir el panel de **historial** → aparecen entradas; con las herramientas de red se ve **una sola** llamada, y **recién al abrir el panel** (R5).
5. **Escape** cierra; el foco vuelve al botón que la abrió; el `?ticket=` desapareció de la URL.
6. Copiar `…/?ticket=<id>`, abrirlo en una pestaña nueva → **aterriza directo en la ficha** (§3.2).
7. Repetir 1-6 en un proyecto **GitLab**. En el panel de adjuntos y en el de historial tiene que aparecer el **aviso de pérdida** con el texto de la matriz, no un panel vacío mudo.
8. **(v2/C10)** Con el foco en una **épica**, abrir "crear tarea hija" **desde la ficha**, solo con teclado: (a) el popover recibe foco, (b) el **primer** Escape cierra el popover y **no** la ficha, (c) el **segundo** Escape cierra la ficha. Si alguna falla, **omitir esa acción de la ficha** en esta entrega y anotarlo (R13).
9. **(v2/C1 — el paso que la v1 no tenía y que es el único que prueba que el historial NO nació mudo)** En los **dos** trackers, abrir el panel de historial de un ticket que **sí tuvo cambios** y verificar que **cada fila muestra al menos un dato real** (fecha, autor o campo). Una tabla de N filas con las 5 celdas vacías es el fallo de C1 y significa que el mapeo por tracker no se aplicó. **Pegar una captura o el JSON de la respuesta.**
10. **(v2/C6)** Con el filtro **"mías"** activo en el tablero, abrir la ficha de una épica que tenga **hijos de otra persona**: los hijos **tienen que aparecer igual** en la columna de jerarquía. Si aparecen vacíos, se pasó `displayHierarchy` en vez de `hierarchy`.

### 9.3 Definición de Hecho (DoD) — 16 ítems, todos binarios

1. `ls "Stacky Agents/docs/287_PLAN_*.md"` existe y este documento tiene su §Estado de implementación con las salidas pegadas.
2. Las 3 flags están en las **5** patas que corresponden (la 6ª, `_REQUIRES_MAP_FROZEN`, **no se toca**) — verificado con `grep -c`.
3. `pytest tests/test_harness_flags.py` — **verde**.
4. `pytest tests/test_harness_flags_requires.py::test_requires_map_is_frozen` — **verde**.
5. `pytest tests/test_harness_flags_help.py` — mismas 4 fallidas que en F0.1 **y** el `grep -c` de F0.2 sobre las 3 keys del plan da **`0`** (C8: el conteo de fallidas solo no discrimina).
6. `pytest tests/test_plan287_ficha_ticket.py` — **`21 passed`** (F1: 12 · F1.5: 3 · F2: 6).
7. `pytest tests/test_plan281_ratchet_ado_only.py` — **verde** (`violaciones_count` sigue en `0`).
8. `pytest tests/test_plan259_ratchet_script_parity.py` y `tests/test_harness_ratchet_meta.py` — **verdes** (juntos con el 7: **`27 passed`**, el baseline de F0.1 #6).
9. `npx tsc --noEmit` — **exit 0**. *(Es lo que prueba que la pata `types.ts` de C5 y la firma con props de `TicketBoard` de C4 se hicieron.)*
10. `npx vitest run src/services/__tests__/ticketDetailModel.test.ts` — **`9 passed`**.
11. `npx vitest run src/services/__tests__/routes.test.ts` → **`21 passed`** y `routesDeepLink.test.ts` → **`8 passed`** (+4 y +2 sobre los 17 y 6 medidos).
12. **(C2)** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` y `adhocModalRatchet.test.ts` — **siguen rojos de fábrica con EXACTAMENTE los ofensores de §4.2**, ni uno más. Ningún archivo del 287 aparece en ninguna de las dos listas. *(Exigirles "verde" era insatisfacible: es el error que la v1 cometía.)*
13. `npx vitest run src/services/__tests__/plan273GateState.test.ts` — **`2 failed | 12 passed (14)`**, las mismas de F0.1, y `grep -c 'useState<GateState>("unknown")' App.tsx` sigue dando **8** (la prop nueva de C4 **no** agrega gate).
14. **(C4)** `grep -c '<TicketBoard ticket=' "frontend/src/App.tsx"` → **1**. Sin esto, F5 quedó construido y jamás cableado.
15. **(C1)** El paso 9 del humo, con la evidencia pegada: **ninguna fila del historial sale con las 5 celdas vacías**, en los dos trackers.
16. Los **10** pasos del humo §9.2, hechos en **los dos** trackers, con el aviso de pérdida visible en GitLab.

**Ninguna fase se da por cerrada con un "pasó todo". Se pega la salida.**
