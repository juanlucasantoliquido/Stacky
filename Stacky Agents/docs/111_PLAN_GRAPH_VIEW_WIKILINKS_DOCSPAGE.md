# Plan 111 — Graph View (canvas) + wikilinks clickeables + backlinks en DocsPage

> **Estado:** CRITICADO v2 — 2026-07-09 (v1 → v2 por `criticar-y-mejorar-plan`)
> **Veredicto del juez:** APROBADO-CON-CAMBIOS (C1-C4 IMPORTANTES resueltos en esta v2; sin bloqueantes)
>
> **CHANGELOG v1 → v2:**
> - **C1 (IMPORTANTE):** contradicción interna resuelta — la query del grafo estaba `enabled` solo para las vistas `coverage`/`graph`, pero los wikilinks y backlinks del LECTOR también la necesitan: con la v1, en la vista `reader` todos los `[[wikilinks]]` se pintaban rotos. Ahora `enabled: graphEnabled` (todas las vistas, F4).
> - **C2 (IMPORTANTE):** navegación cross-source de `onOpenNoteById` especificada literal (la nota destino puede vivir en OTRA fuente: hay que cambiar `selectedSourceId` y esperar el `indexData` async). Algoritmo con estado `pendingOpenPath` + `useEffect` en F4.
> - **C3 (IMPORTANTE):** `stepLayout_keeps_nodes_in_bounds` exigía un clamp que las reglas cerradas de F2 no especificaban → un modelo menor no podía poner el test en verde. Clamp literal agregado a las reglas.
> - **C4 (IMPORTANTE):** el import de tipos `mdast`/`unified` es transitivo y puede no resolver según config de TS: fallback literal en F0 (tipos estructurales mínimos locales, sin tocar `package.json`).
> - **C5 (MENOR):** `LayoutEdge.stale` no existe en el payload del 109 (recién lo produce el plan 114): `initLayout` lo defaultea `false`.
> - **C6 (MENOR):** radio de pick del hover fijado: `max(12, r + 4)` px.
> - **C7 (MENOR):** `frac()` de la siembra definido: `frac(v) = v - Math.floor(v)`.
> - **[ADICIÓN ARQUITECTO]:** búsqueda en la pestaña Grafo — input que resalta los nodos cuyo label matchea (helper puro `filterNodeIds(graph, query)` en `docGraphModel.ts`, 3 tests vitest). Cero dependencias, read-only.
> **Serie:** Documentación agéntica Obsidian (109 → **111** → 112; alimenta al Documentador del plan 113). El número 110 quedó tomado por un plan ajeno (Revisor de PRs), por eso la serie salta de 109 a 111.
> **Pipeline:** este documento pasó `proponer` (este estado). Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Depende de:** Plan 109 (endpoint `GET /api/docs/graph`, contrato §4.1, flag `STACKY_DOCS_GRAPH_ENABLED`, tipos `DocGraphResponse`/`DocGraphNode`/`DocGraphEdge` en `frontend/src/docs/docGraphModel.ts`, cliente `Docs.getGraph`, estado `docsView` y pestaña "Cobertura" en `DocsPage`). **Este plan NO parsea markdown ni computa aristas: consume el payload de 109.**

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El plan 109 construye el grafo documental y lo expone por HTTP, pero el operador todavía no lo *ve* como red ni puede *navegarlo*. Este plan agrega la capa perceptible estilo Obsidian: (a) una pestaña **"Grafo"** en `DocsPage` con un **graph view force-directed dibujado en un `<canvas>` propio, SIN dependencias nuevas** (decisión de arquitectura ya tomada: nada de mermaid, d3, cytoscape ni react-force-graph); (b) un **remark plugin propio** `remarkWikilinks` que convierte `[[nombre]]` / `[[nombre|alias]]` en links clickeables dentro del visor markdown, resolviendo el destino contra el índice del grafo; (c) un **panel de backlinks** debajo del documento abierto que lista las notas que lo referencian. Todo gateado por la MISMA flag `STACKY_DOCS_GRAPH_ENABLED` del plan 109 (sin flag nueva). Cero backend nuevo: es 100% frontend sobre el contrato §4.1.

**KPI / impacto esperado.**
- **Navegación en red:** desde cualquier nota, el operador llega a sus vecinas en 1 clic (wikilink, backlink o nodo del grafo). Meta: click en un nodo del grafo abre la nota correspondiente en el visor en < 150 ms (sin fetch nuevo si el contenido ya está en cache de react-query).
- **Render fluido sin librerías:** el graph view dibuja hasta **300 nodos** a ≥ 30 fps en la simulación y **degrada a layout estático precomputado** por encima de ese umbral (sin colgar el hilo). Meta binaria: con 301+ nodos NO se corre el bucle de animación (se verifica en el módulo puro de layout).
- **Wikilinks reales:** un `[[nombre]]` que resuelve navega; uno que no resuelve se pinta atenuado (clase `wikilink-broken`) y NO rompe el render. Meta: 0 excepciones en el visor ante wikilinks rotos.
- **Cero regresión:** con la flag OFF (default), `DocsPage`, `DocViewer` y el resto son **byte-idénticos** a hoy (la pestaña "Grafo", el plugin y el panel de backlinks solo se montan con la flag ON).

---

## 2. Por qué ahora / gap que cierra

1. El plan 109 ya entrega el grafo por `GET /api/docs/graph` (nodos, aristas, backlinks, huérfanas, `doc_health`) pero la única superficie visible es la pestaña "Cobertura" (una tabla). **Falta la vista de red — el corazón de la metáfora Obsidian que el operador aprobó.**
2. `frontend/src/components/DocViewer.tsx` renderiza markdown con `react-markdown@9` + `remark-gfm` + `rehype-highlight`, con un `LinkRenderer` propio que ya intercepta links (DocViewer.tsx:33-69). **No entiende `[[wikilinks]]`** (no hay remark plugin). Es el punto de extensión natural.
3. `frontend/package.json` **no tiene** ninguna librería de graph view, y la casa ya decidió **no** agregarla (coherente con `MermaidDiagram` para diagramas estáticos, pero un graph view interactivo necesita force-layout que mermaid no da). Canvas propio = ~250 líneas, cero superficie de dependencia nueva, cero riesgo de supply chain.
4. El plan 109 dejó el estado `docsView: 'reader' | 'coverage'` en `DocsPage`; este plan agrega el tercer valor `'graph'` reutilizando esa maquinaria (sin re-arquitectura).

---

## 3. Principios y guardarraíles (NO negociables — codificados en las fases)

- **3 runtimes con paridad total.** Plan **100% frontend** (React + canvas 2D). No hay ninguna llamada a runtime LLM (Codex / Claude Code / Copilot). Paridad trivial; no hay fallback de runtime que definir.
- **Cero trabajo extra al operador.** Todo cuelga de la flag del plan 109 (`STACKY_DOCS_GRAPH_ENABLED`, default OFF, editable por UI). Sin flag nueva, sin config nueva, backward-compatible.
- **Sin dependencias nuevas.** Prohibido agregar paquetes a `package.json`. El graph view es canvas 2D nativo; el remark plugin es una función pura sobre el AST de `mdast` (react-markdown ya trae `unified`/`mdast` transitivamente, pero el plugin NO importa paquetes nuevos: opera sobre el árbol que react-markdown le pasa).
- **Human-in-the-loop / read-only.** Nada se escribe. El grafo y los wikilinks solo navegan/visualizan.
- **Mono-operador sin auth.** No se agrega nada de identidad.
- **No degradar performance.** El bucle de animación se apaga solo cuando la pestaña no está visible (`docsView !== 'graph'`) y respeta `prefers-reduced-motion` (layout estático precomputado). Límite duro de 300 nodos para el modo animado.
- **Reusar lo existente.** Consume `Docs.getGraph` (109), los tipos de `docGraphModel.ts` (109), el `LinkRenderer` de `DocViewer` (extendido, no reemplazado) y el patrón de pestañas de `DocsPage` (109).
- **Theme-aware.** Colores del canvas y del panel leídos de CSS custom properties (light/dark), nunca hardcodeados.
- **Sin ambigüedad para modelos menores.** Cada fase: archivo exacto, símbolo exacto, pseudocódigo con casos borde, test nombrado + comando con el runner del repo, criterio binario.

---

## 4. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto |
|---|---|
| Flag (reusada de 109) | `STACKY_DOCS_GRAPH_ENABLED` (sin flag nueva) |
| Remark plugin | `remarkWikilinks` en `frontend/src/docs/remarkWikilinks.ts` |
| Resolutor de nombres | `buildNameIndex(graph: DocGraphResponse): Map<string, string>` en `frontend/src/docs/docGraphModel.ts` (se agrega a 109) |
| Módulo de layout puro | `frontend/src/docs/forceLayout.ts` (funciones `initLayout`, `stepLayout`, `staticLayout`) |
| Componente graph view | `DocGraphView` en `frontend/src/components/docs/DocGraphView.tsx` |
| Panel de backlinks | `DocBacklinksPanel` en `frontend/src/components/docs/DocBacklinksPanel.tsx` |
| Estado de vista (extiende 109) | `docsView: 'reader' \| 'coverage' \| 'graph'` |
| Umbral de nodos para animar | `MAX_ANIMATED_NODES = 300` (const en `forceLayout.ts`) |
| Clase CSS wikilink OK | `wikilink` |
| Clase CSS wikilink roto | `wikilink-broken` |
| Callback abrir nota | `onOpenNoteById(nodeId: string): void` |

### 4.1 Contrato de datos que se consume (del plan 109, §4.1)

Este plan **no define contrato nuevo**: usa `DocGraphResponse` (nodes/edges/orphans/stats/doc_health) tal como lo entrega `GET /api/docs/graph`. La resolución de wikilinks usa el mismo criterio de identidad de nodos del 109 (`note:<source_id>:<path>`, `code:<path>`, `missing:<nombre_lower>`).

---

## 5. Fases

### F0 — `remarkWikilinks`: plugin puro que transforma `[[...]]` en links del AST

**Objetivo (1 frase).** Un remark plugin que recorre el `mdast` y reemplaza los `[[nombre]]` / `[[nombre|alias]]` que aparezcan dentro de nodos `text` por nodos `link` con una URL marcadora `wikilink:<nombre>`, sin tocar código, links normales ni bloques de código. **Valor:** núcleo determinístico y testeable sin DOM.

**Archivo a crear:** `Stacky Agents/frontend/src/docs/remarkWikilinks.ts`.

**Pseudocódigo EXACTO:**
```ts
import type { Root, Text, Link, PhrasingContent } from "mdast";
import type { Plugin } from "unified";
// (mdast/unified ya vienen transitivamente con react-markdown@9; NO se agregan a package.json)
// (C4) FALLBACK LITERAL si `tsc --noEmit` NO resuelve "mdast"/"unified" en este checkout:
// borrar los dos imports de arriba y declarar tipos estructurales mínimos locales —
//   type Text = { type: "text"; value: string };
//   type Link = { type: "link"; url: string; children: Text[] };
//   type PhrasingContent = Text | Link | { type: string; [k: string]: unknown };
//   type Root = { type: "root"; children: any[] };
//   type Plugin<A extends any[], T> = () => (tree: T) => void;
// react-markdown consume el plugin en runtime por duck-typing; los tipos locales
// solo tienen que tipar ESTE archivo. PROHIBIDO agregar paquetes a package.json.

const WIKILINK_RE = /\[\[([^\]|\n]+?)(?:\|([^\]\n]*))?\]\]/g;

/**
 * remarkWikilinks — transforma [[nombre]] y [[nombre|alias]] en nodos link con
 * url "wikilink:<nombre-trim>". El texto visible es el alias si existe, si no el nombre.
 * NO transforma dentro de `inlineCode`/`code` (remark no baja a esos nodos como text con [[).
 * Determinístico. Nunca lanza.
 */
export const remarkWikilinks: Plugin<[], Root> = () => (tree) => {
  visitTextNodes(tree, (node, index, parent) => {
    const value = node.value;
    if (!value.includes("[[")) return;            // fast path
    const parts: PhrasingContent[] = [];
    let last = 0;
    WIKILINK_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = WIKILINK_RE.exec(value)) !== null) {
      const name = m[1].trim();
      if (!name) continue;                         // [[]] o [[  ]] → se ignora, queda como texto
      if (m.index > last) parts.push({ type: "text", value: value.slice(last, m.index) } as Text);
      const label = (m[2] ?? "").trim() || name;
      const link: Link = {
        type: "link",
        url: "wikilink:" + name,
        children: [{ type: "text", value: label } as Text],
      };
      parts.push(link);
      last = m.index + m[0].length;
    }
    if (parts.length === 0) return;                // no hubo match real
    if (last < value.length) parts.push({ type: "text", value: value.slice(last) } as Text);
    parent.children.splice(index, 1, ...parts);   // reemplaza el text node por [text?, link, text?, ...]
    return index + parts.length;                  // continuar después de lo insertado
  });
};

// visitTextNodes: recorrido propio (sin unist-util-visit para no depender de su API);
// recorre recursivo, saltea nodos type "code"/"inlineCode", y llama al callback sobre "text".
function visitTextNodes(tree: Root, cb: (n: Text, i: number, parent: any) => number | void) { /* ... */ }
```

**Casos borde que cierra (y los tests verifican):**
- `[[Nota Motor]]` → link `wikilink:Nota Motor`, label `Nota Motor`.
- `[[Nota|el motor]]` → link `wikilink:Nota`, label `el motor`.
- `texto [[A]] medio [[B|b]] fin` → `text("texto ") link(A) text(" medio ") link(B,label b) text(" fin")`.
- `[[]]` y `[[   ]]` → NO se transforman (quedan como texto literal).
- Wikilink dentro de `` `código [[X]]` `` (inlineCode) → NO se transforma (el visitor saltea `inlineCode`).
- Texto sin `[[` → intacto (fast path, sin asignaciones).

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/docs/remarkWikilinks.test.ts` (vitest, sin DOM: construir un `Root` mdast a mano o parsear con la utilidad que ya use el repo; preferido: construir el árbol a mano para no depender de un parser). Casos con los nombres: `transforms_simple_wikilink`, `transforms_wikilink_with_alias`, `splits_mixed_text_and_wikilinks`, `ignores_empty_wikilink`, `skips_inline_code`, `leaves_plain_text_untouched`.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/docs/remarkWikilinks.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** 6/6 vitest verdes + `tsc --noEmit` 0 errores.

**Flag/default:** el plugin no lee flags (se cablea en F1 solo con flag ON). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F1 — Resolución de wikilinks + wiring en `DocViewer` (flag ON)

**Objetivo (1 frase).** Que `DocViewer` use `remarkWikilinks` y resuelva las URLs `wikilink:<nombre>` contra el índice del grafo, navegando a la nota si existe o marcándola rota si no. **Valor:** wikilinks vivos en el visor, estilo Obsidian.

**Archivos a editar:**

1. **`Stacky Agents/frontend/src/docs/docGraphModel.ts`** (creado en 109) — agregar el índice de nombres:
   ```ts
   /** Índice nombre-lower-sin-extensión → nodeId, para resolver wikilinks. Mismo
    *  criterio de colisión que el backend (109): gana el path lexicográficamente menor. */
   export function buildNameIndex(graph: DocGraphResponse): Map<string, string> {
     const idx = new Map<string, string>();
     const notes = graph.nodes
       .filter((n) => n.kind === "note")
       .sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : a.source_id < b.source_id ? -1 : 1));
     for (const n of notes) {
       const base = n.label.replace(/\.md$/i, "").toLowerCase();
       if (!idx.has(base)) idx.set(base, n.id);   // primera (menor) gana
     }
     return idx;
   }
   /** Resuelve "wikilink:<nombre>" a un nodeId o null. */
   export function resolveWikilink(url: string, nameIndex: Map<string, string>): string | null {
     if (!url.startsWith("wikilink:")) return null;
     const name = url.slice("wikilink:".length).trim().toLowerCase();
     return nameIndex.get(name) ?? null;
   }
   ```

2. **`Stacky Agents/frontend/src/components/DocViewer.tsx`** — extender (NO reemplazar) el render:
   - Nuevas props opcionales (backward-compatible; hoy DocViewer se usa sin ellas):
     ```ts
     interface DocViewerProps {
       node: DocNode; content: string; isLoading?: boolean; error?: string | null;
       wikilinksEnabled?: boolean;                 // true solo con flag ON
       nameIndex?: Map<string, string>;            // del grafo (109)
       onOpenNoteById?: (nodeId: string) => void;  // navegar a nota resuelta
     }
     ```
   - `remarkPlugins`: `wikilinksEnabled ? [remarkGfm, remarkWikilinks] : [remarkGfm]` (con flag OFF el plugin NI se carga en el pipeline → comportamiento byte-idéntico a hoy).
   - `LinkRenderer`: al inicio, si `href?.startsWith("wikilink:")`:
     ```tsx
     const target = nameIndex ? resolveWikilink(href, nameIndex) : null;
     if (target && onOpenNoteById) {
       return <a href="#" className="wikilink"
         onClick={(e) => { e.preventDefault(); onOpenNoteById(target); }}>{children}</a>;
     }
     return <span className="wikilink-broken" title="Nota no encontrada">{children}</span>;
     ```
   - Clases `wikilink` / `wikilink-broken` en `DocViewer.module.css` (theme-aware: `wikilink` usa `var(--accent)`, `wikilink-broken` gris atenuado con `text-decoration: underline dotted`).

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/docs/docGraphModel.test.ts` (extender el de 109 o crear `docGraphModel.wikilinks.test.ts`; **modelo puro, sin DOM**):
- `buildNameIndex_maps_basename_lowercase`.
- `buildNameIndex_collision_lower_path_wins`.
- `resolveWikilink_hits_and_misses` (nombre existente → id; inexistente → null; url sin prefijo → null).

> **Disclosure de entorno (plan 107):** los `.test.tsx` con `@testing-library/react` están BLOQUEADOS en este checkout. El criterio de F1 es el test del **modelo puro** (`.test.ts`) + `tsc --noEmit`. El wiring de `DocViewer` se valida por tipos (tsc) y por la verificación manual de F5, no por un test de componente.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/docs/docGraphModel.test.ts src/docs/docGraphModel.wikilinks.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** tests del modelo verdes + `tsc --noEmit` 0 errores. Con `wikilinksEnabled` ausente/false, `DocViewer` no incluye `remarkWikilinks` (verificable por lectura: el array de plugins no lo contiene).

**Flag/default:** `wikilinksEnabled` lo pasa `DocsPage` solo cuando `graph_enabled === true`. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F2 — `forceLayout.ts`: simulación force-directed PURA (sin canvas, sin React)

**Objetivo (1 frase).** Aislar toda la matemática del layout en un módulo puro y testeable: inicialización de posiciones, un `stepLayout` de repulsión+resortes+centrado, y un `staticLayout` determinístico para el modo degradado / reduced-motion. **Valor:** el 80% del riesgo del graph view (la física) queda cubierto por tests sin DOM.

**Archivo a crear:** `Stacky Agents/frontend/src/docs/forceLayout.ts`.

**Diseño EXACTO:**
```ts
export const MAX_ANIMATED_NODES = 300;

export interface LayoutNode { id: string; x: number; y: number; vx: number; vy: number; r: number; group: string; }
export interface LayoutEdge { source: number; target: number; stale: boolean; }  // índices en el array de nodos
export interface LayoutState { nodes: LayoutNode[]; edges: LayoutEdge[]; width: number; height: number; animated: boolean; }

/** Construye el estado inicial desde el grafo (109). radio = f(in_degree). Posiciones
 *  sembradas deterministas (sin Math.random: usa un hash del id) para reproducibilidad.
 *  animated = nodes.length <= MAX_ANIMATED_NODES && !reducedMotion. */
export function initLayout(graph: DocGraphResponse, width: number, height: number, reducedMotion: boolean): LayoutState { /* ... */ }

/** Un paso de simulación in-place: repulsión O(n²) acotada, resortes por arista,
 *  atracción al centro, damping. Devuelve la energía (para detectar convergencia). */
export function stepLayout(state: LayoutState): number { /* ... */ }

/** Layout determinístico sin animación: distribuye por grupo en columnas + jitter por hash.
 *  Se usa si !state.animated (>300 nodos o reduced-motion). */
export function staticLayout(state: LayoutState): void { /* ... */ }

/** Radio de nodo a partir del in_degree (backlinks): 4 + min(11, inDeg*1.15). */
export function nodeRadius(inDegree: number): number { return 4 + Math.min(11, inDegree * 1.15); }
```

**Reglas cerradas:**
- Siembra determinista: `seed(id)` = suma de char codes; `frac(v) = v - Math.floor(v)` (C7); `x = width*(0.15+0.7*frac(seed*0.618))`, `y = height*(0.15+0.7*frac(seed*0.377))`. **Sin `Math.random`** (tests reproducibles).
- `stepLayout`: repulsión solo entre pares a distancia² < 40000 (acota el O(n²) real); resorte a longitud natural 78; centro con factor 0.0016; damping 0.86.
- **(C3) Clamp de bordes (literal, al final de cada paso, tras integrar velocidad):** para cada nodo, `x = Math.min(Math.max(x, r), width - r)` y `y = Math.min(Math.max(y, r), height - r)`; si se clampeó en un eje, la velocidad de ese eje se pone en 0. Sin este clamp el test `stepLayout_keeps_nodes_in_bounds` no puede pasar.
- **(C5)** `initLayout` construye `LayoutEdge.stale` como `Boolean((edge as any).stale)` — el payload del 109 NO trae ese campo (lo produce el plan 114): ausente ⇒ `false`.
- `animated=false` cuando `nodes.length > MAX_ANIMATED_NODES` **o** `reducedMotion` → el componente NO llama `stepLayout`, usa `staticLayout` una vez.

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/docs/forceLayout.test.ts` (vitest puro):
- `nodeRadius_scales_and_caps` (inDeg 0 → 4; inDeg grande → 15 tope).
- `initLayout_seeds_are_deterministic` (dos `initLayout` del mismo grafo dan posiciones idénticas).
- `initLayout_disables_animation_over_threshold` (301 nodos → `animated===false`).
- `initLayout_disables_animation_when_reduced_motion` (`reducedMotion=true` → `animated===false` aún con pocos nodos).
- `stepLayout_reduces_energy_over_iterations` (energía tras 100 pasos < energía inicial).
- `stepLayout_keeps_nodes_in_bounds` (tras N pasos, todo x∈[0,width], y∈[0,height]).
- `staticLayout_is_deterministic_and_groups_columns`.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/docs/forceLayout.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** 7/7 vitest verdes + tsc 0 errores.

**Flag/default:** módulo puro, no lee flags. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F3 — `DocGraphView.tsx`: render canvas + interacción

**Objetivo (1 frase).** Componente que dibuja el `LayoutState` en un `<canvas>`, corre el bucle de animación solo cuando corresponde, y maneja hover (resalta vecinos), click (abre nota) y drag de nodos. **Valor:** la vista de red navegable — la cara Obsidian.

**Archivo a crear:** `Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`.

**Diseño EXACTO (comportamiento, no copiar literal):**
- Props: `{ graph: DocGraphResponse; onOpenNoteById: (nodeId: string) => void; selectedNodeId?: string | null }`.
- `useRef` al canvas; `useRef` al `LayoutState` (no estado React, para no re-renderizar en cada frame).
- En mount / cuando cambia `graph` o el tamaño: `initLayout(...)` leyendo `prefers-reduced-motion` vía `matchMedia`. Colores por grupo (`note` según `source_id` kind, `code`, `missing`, huérfana) leídos de CSS custom properties con `getComputedStyle` (theme-aware).
- Bucle: `requestAnimationFrame`; si `state.animated`, `stepLayout` + `draw`; si no, `staticLayout` una vez + `draw` estático. **Cancelar el rAF** cuando el componente se desmonta o cuando su contenedor no está visible (el padre solo lo monta con `docsView === 'graph'`, así que desmontar al cambiar de pestaña ya apaga el bucle).
- `draw`: aristas primero (stale = punteada roja `var(--stale)`, tolerando el campo ausente → sólida normal), luego nodos (radio de `nodeRadius`, color por grupo, halo en el `selectedNodeId`), labels solo en hubs (r grande), nodo hovered y huérfanas.
- Hover: `pointermove` → nodo más cercano dentro de un radio de pick de `Math.max(12, r + 4)` px (C6) → resalta él + vecinos (atenúa el resto a alpha 0.22).
- **[ADICIÓN ARQUITECTO]** Búsqueda: un `<input type="search">` sobre el canvas (placeholder "Buscar nodo..."); con texto no vacío, los nodos cuyo id está en `filterNodeIds(graph, query)` se dibujan resaltados y el resto atenuado a alpha 0.15 (misma mecánica del hover). El helper es puro y vive en `docGraphModel.ts`:
  ```ts
  /** Ids de nodos cuyo label matchea query (substring case-insensitive, trim). Query vacía → Set vacío. */
  export function filterNodeIds(graph: DocGraphResponse, query: string): Set<string> { /* ... */ }
  ```
- Click: `pointerup` sin drag → `onOpenNoteById(node.id)` **solo si `kind === 'note'`** (los nodos `code`/`missing` no abren visor; se ignoran o muestran tooltip).
- Drag: `pointerdown` sobre nodo fija su posición al puntero mientras se arrastra.
- Accesibilidad: leyenda de colores en HTML al lado del canvas (no solo color); `prefers-reduced-motion` respetado por el flag `animated`.
- **NO** disparar `alert`/`confirm`.

**Tests:** por la limitación de entorno (`.test.tsx` bloqueado), **no** hay test de componente. La lógica testeable ya vive en `forceLayout.ts` (F2). Criterio de F3 = `tsc --noEmit` 0 errores + verificación manual de F5.

**Comando (desde `Stacky Agents/frontend`):**
```
npx tsc --noEmit
```

**Criterio BINARIO:** `tsc --noEmit` 0 errores; lectura del código confirma: rAF cancelado en cleanup del `useEffect`; `stepLayout` NO se llama si `!state.animated`; click abre solo nodos `note`.

**Flag/default:** el componente solo se monta con flag ON (F4). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F4 — `DocBacklinksPanel` + pestaña "Grafo" en `DocsPage`

**Objetivo (1 frase).** Integrar todo: tercer valor `'graph'` en `docsView`, el panel de backlinks bajo el visor, y el pasaje de `wikilinksEnabled`/`nameIndex`/`onOpenNoteById` a `DocViewer`. **Valor:** la experiencia completa cableada, solo visible con flag ON.

**Archivos:**

1. **Crear** `Stacky Agents/frontend/src/components/docs/DocBacklinksPanel.tsx`:
   - Props: `{ graph: DocGraphResponse | undefined; currentNodeId: string | null; onOpenNoteById: (id: string) => void }`.
   - Deriva los backlinks: aristas cuyo `target === currentNodeId`; mapea `source` → nodo; lista clickeable (máx 50). Vacío → "Ninguna nota enlaza a este documento todavía." Si `currentNodeId` no resuelve a un nodo del grafo (p.ej. doc de Stacky no mapeado), oculta el panel.

2. **Editar** `Stacky Agents/frontend/src/pages/DocsPage.tsx`:
   - `docsView` pasa a `'reader' | 'coverage' | 'graph'` (extiende 109).
   - **(C1)** La query `graphData` de 109 cambia su gate a `enabled: graphEnabled` (SIN condición de vista): los wikilinks y el panel de backlinks de la vista `reader` también la necesitan — con el gate v1 (`coverage || graph`) todos los wikilinks del lector se pintaban rotos por `nameIndex === undefined`. El costo es 1 fetch cacheado (staleTime 60 s) solo cuando la flag está ON.
   - `const nameIndex = useMemo(() => graphData ? buildNameIndex(graphData) : undefined, [graphData]);`
   - Resolver el `currentNodeId` de la nota abierta: helper `noteIdFor(selectedDocNode, graphData)` que matchea por `path`/`source_id` contra `graphData.nodes` (best-effort; null si no mapea).
   - **(C2) Callback `onOpenNoteById(nodeId)` — algoritmo literal (la nota destino puede vivir en OTRA fuente):**
     1. Buscar `target = graphData.nodes.find(n => n.id === nodeId)`. Si no existe o `target.kind !== 'note'`, no hacer nada y retornar.
     2. `setDocsView('reader')`.
     3. Si `target.source_id === selectedSourceId`: buscar el `DocNode` en `indexData.roots` con un helper recursivo `findDocNodeByPath(roots, target.path)` (DFS que compara `node.path === target.path` en nodos `kind !== 'folder'`); si lo encuentra, `setSelectedNode(docNode)` y retornar.
     4. Si es OTRA fuente: `setSelectedSourceId(target.source_id)` **y** `setPendingOpenPath(target.path)` (estado nuevo `const [pendingOpenPath, setPendingOpenPath] = useState<string | null>(null)`). El `indexData` de la fuente nueva llega async.
     5. `useEffect` sobre `[indexData, pendingOpenPath]`: si hay `pendingOpenPath` y el `indexData` actual corresponde a la fuente pedida, `findDocNodeByPath` → `setSelectedNode(...)` + `setPendingOpenPath(null)`. Si no se encuentra el path (grafo stale), limpiar `pendingOpenPath` sin lanzar.
     Nota: el reset por cambio de proyecto (useEffect existente de DocsPage) también debe limpiar `pendingOpenPath`.
   - Barra de pestañas (solo con `graphEnabled`): agregar botón "Grafo" junto a "Lector"/"Cobertura" (`aria-pressed`).
   - Cuando `docsView === 'graph'`: el panel principal renderiza `<DocGraphView graph={graphData} onOpenNoteById={...} selectedNodeId={currentNodeId} />` (con loading/empty si `graphData` no llegó).
   - Cuando `docsView === 'reader'` y `graphEnabled`: pasar a `DocViewer` las props `wikilinksEnabled`, `nameIndex`, `onOpenNoteById`; y montar `<DocBacklinksPanel .../>` debajo del `DocViewer`.
   - **Con `graphEnabled === false`:** NADA de esto se monta (ni pestaña "Grafo", ni backlinks, ni wikilinks) → DocsPage byte-idéntica a hoy.

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/docs/backlinks.test.ts` (extraer la derivación pura de backlinks a una función `backlinksOf(graph, nodeId): DocGraphNode[]` en `docGraphModel.ts` y testearla sin DOM):
- `backlinksOf_returns_sources_targeting_node`.
- `backlinksOf_empty_when_no_incoming`.
- `backlinksOf_null_node_returns_empty`.
- **[ADICIÓN ARQUITECTO]** `filterNodeIds_matches_substring_case_insensitive`.
- **[ADICIÓN ARQUITECTO]** `filterNodeIds_empty_query_returns_empty_set`.
- **[ADICIÓN ARQUITECTO]** `filterNodeIds_no_match_returns_empty_set`.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/docs/backlinks.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** 6/6 vitest verdes + `tsc --noEmit` 0 errores.

**Flag/default:** `STACKY_DOCS_GRAPH_ENABLED` OFF → cero elementos nuevos, cero fetch (la query respeta `enabled`). **Impacto por runtime:** ninguno. **Fallback:** DocsPage idéntica a hoy. **Trabajo del operador:** ninguno (opt-in default off).

---

### F5 — Cierre: verificación manual, no-regresión y DoD

**Objetivo (1 frase).** Sellar el plan con la verificación end-to-end que los tests de componente no pueden cubrir en este entorno.

**Acciones:**
1. Confirmar que NO se agregó ninguna dependencia: `git diff -- "Stacky Agents/frontend/package.json"` vacío.
2. Suite frontend pura (desde `Stacky Agents/frontend`):
   ```
   npx vitest run src/docs/remarkWikilinks.test.ts src/docs/forceLayout.test.ts src/docs/docGraphModel.test.ts src/docs/backlinks.test.ts
   npx tsc --noEmit
   ```
3. **Verificación manual (flag ON)** con el backend levantado y `STACKY_DOCS_GRAPH_ENABLED=true`: abrir DocsPage → aparecen 3 pestañas; "Grafo" dibuja la red y el drag/hover/click funcionan; la búsqueda resalta nodos por nombre; abrir una nota con `[[wikilink]]` válido navega (incluso si la nota destino está en OTRA fuente — C2); uno inválido se ve atenuado; los wikilinks resuelven en la vista Lector SIN pasar antes por Grafo/Cobertura (C1); el panel de backlinks lista las notas entrantes.
4. **Verificación manual (flag OFF, default):** DocsPage muestra solo el visor de siempre, sin pestañas nuevas, sin panel de backlinks, sin request a `/api/docs/graph`.

**Criterio BINARIO global (DoD):**
- [ ] `remarkWikilinks.test.ts` (6), `forceLayout.test.ts` (7), tests del modelo (buildNameIndex/resolveWikilink/backlinksOf) verdes; `tsc --noEmit` 0 errores.
- [ ] `package.json` sin cambios (cero dependencias nuevas).
- [ ] Con flag OFF: DocsPage/DocViewer byte-idénticos a hoy; sin fetch a `/api/docs/graph`.
- [ ] Con flag ON: pestaña "Grafo" renderiza; wikilinks resuelven o se marcan rotos sin excepción; backlinks listan.
- [ ] `stepLayout` no corre con >300 nodos o reduced-motion (modo estático); rAF cancelado al desmontar.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Canvas force-layout que traba el hilo con muchos nodos. | Umbral `MAX_ANIMATED_NODES=300` → layout estático; repulsión acotada a distancia²<40000; rAF cancelado fuera de la pestaña. |
| Tests de componente bloqueados en el entorno. | Toda la lógica dura (plugin, layout, resolución, backlinks) vive en módulos PUROS con tests vitest; el componente queda cubierto por tsc + verificación manual (F5). Disclosure explícito. |
| Wikilink roto rompe el render del visor. | Rotos → `<span class="wikilink-broken">`, nunca navegación ni throw; `resolveWikilink` devuelve null de forma segura. |
| Agregar una dependencia "para ir más rápido". | Guardarraíl duro: `package.json` sin cambios es criterio de DoD; canvas 2D nativo alcanza. |
| Colores hardcodeados rompen dark mode. | Colores leídos de CSS custom properties con `getComputedStyle`; leyenda en HTML (no solo color). |
| Colisión de nombres de wikilink (dos notas igual basename). | Mismo criterio determinista que el backend 109 (path lexicográfico menor gana), implementado en `buildNameIndex`. |
| Drift del contrato del 109. | Este plan solo lee el payload; si 109 cambia el shape, `tsc` sobre los tipos de `docGraphModel.ts` lo detecta. |

---

## 7. Fuera de scope

- Backend / parsing de aristas (es del plan 109; acá se consume).
- Retrieval híbrido con el grafo (plan 112).
- Escribir/crear/corregir documentación o wikilinks (plan 113, Documentador).
- Producir el campo de aristas "stale" (plan 114; acá solo se pinta si viene en el payload).
- Zoom/pan avanzado, minimap, clustering por comunidades (no necesarios para el valor central; se pueden proponer luego).
- Persistir posiciones de nodos entre sesiones.

---

## 8. Glosario (términos para modelos menores)

- **Graph view:** vista de la documentación como red de nodos (notas/código) y aristas (links), estilo Obsidian.
- **Force-directed layout:** algoritmo que posiciona nodos simulando repulsión entre todos y resortes en las aristas hasta un equilibrio.
- **Remark plugin:** función que transforma el árbol `mdast` (markdown) antes de renderizar; se pasa en `remarkPlugins` de react-markdown.
- **mdast:** Markdown Abstract Syntax Tree — la representación en árbol del markdown que usa remark/react-markdown.
- **Wikilink:** sintaxis Obsidian `[[nombre]]` / `[[nombre|alias]]`; resuelve por basename sin extensión, case-insensitive.
- **Backlink:** nota que enlaza a la nota actual (arista entrante).
- **`prefers-reduced-motion`:** preferencia del SO para minimizar animaciones; acá fuerza el layout estático.
- **Nodo puro / módulo puro:** función sin efectos secundarios ni DOM, testeable con vitest sin navegador.
- **Runner de tests frontend:** `vitest` (instalado desde plan 87); correr por archivo. `tsc --noEmit` valida tipos.

---

## 9. Orden de implementación (secuencial)

1. **F0** — `remarkWikilinks.ts` + 6 tests.
2. **F1** — `buildNameIndex`/`resolveWikilink` + wiring `DocViewer` + tests del modelo.
3. **F2** — `forceLayout.ts` + 7 tests.
4. **F3** — `DocGraphView.tsx` (tsc + lectura).
5. **F4** — `DocBacklinksPanel.tsx` + pestaña "Grafo" en `DocsPage` + `backlinksOf` + `filterNodeIds` + 6 tests.
6. **F5** — cierre, no-regresión, verificación manual, DoD.

---

## 10. Definición de Hecho (DoD) — resumen binario

Hecho cuando: (a) los 4 archivos de test puros (remarkWikilinks, forceLayout, modelo, backlinks) están verdes y `tsc --noEmit` da 0 errores; (b) `package.json` no cambió (cero dependencias nuevas); (c) con la flag OFF DocsPage/DocViewer son byte-idénticos a hoy y no hay request a `/api/docs/graph`; (d) con la flag ON la pestaña "Grafo" renderiza la red navegable (hover/click/drag), los wikilinks resuelven o se marcan rotos sin romper el visor, y el panel de backlinks lista las notas entrantes; (e) el modo animado se apaga con >300 nodos o `prefers-reduced-motion` y el rAF se cancela al desmontar.
