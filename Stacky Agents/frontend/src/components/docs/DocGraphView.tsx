/**
 * DocGraphView.tsx — Plan 111 F3 (+ mejora visual/navegación).
 *
 * Dibuja el grafo documental (109) en un <canvas> 2D nativo (SIN dependencias nuevas).
 * Corre el bucle de animación solo cuando corresponde (<=300 nodos y sin
 * prefers-reduced-motion), y maneja hover (resalta vecinos), click (abre nota en el
 * Lector), drag de nodos, PAN (arrastrando el fondo) y ZOOM (rueda, anclado al cursor;
 * matemática pura en docs/graphViewport). Labels sin solapamiento con fondo tipo pill
 * (pickVisibleLabels). La búsqueda resalta nodos por label (filterNodeIds).
 * Colores leídos de CSS custom properties (theme-aware). Read-only, nunca escribe.
 */
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import type { DocGraphResponse } from "../../docs/docGraphModel";
import { filterNodeIds, nodeIndexById } from "../../docs/docGraphModel";
import { GRAPH_PALETTE_TOKENS, GROUP_SLOT_TOKENS } from "../../docs/graphPalette";
import { graphExplorerReducer, INITIAL_EXPLORER_STATE } from "../../docs/graphExplorerState";
import { applyGraphFilters, availableFilterOptions } from "../../docs/graphFilters";
import { searchGraphNodes, matchAt, matchIdSet } from "../../docs/graphSearch";
import { focusSubgraph, rankedNeighbors, resolveFocusId } from "../../docs/graphNeighborhood";
import {
  collapseGroups,
  groupKeyFromNodeId,
  isGroupNodeId,
  groupLabelOf,
} from "../../docs/graphGrouping";
import DocGraphFilterBar from "./DocGraphFilterBar";
import DocGraphZoomControls from "./DocGraphZoomControls";
import {
  initLayout,
  stepLayout,
  staticLayout,
  type LayoutState,
} from "../../docs/forceLayout";
import {
  IDENTITY,
  zoomAt,
  panBy,
  toWorld,
  toScreen,
  pickVisibleLabels,
  estimateLabelWidth,
  centerOn,
  zoomAtCenter,
  fitViewport,
  ZOOM_STEP,
  MIN_SCALE,
  MAX_SCALE,
  type Viewport,
  type LabelCandidate,
} from "../../docs/graphViewport";
import styles from "./DocGraphView.module.css";
import ex from "./DocGraphExplorer.module.css";

interface DocGraphViewProps {
  graph: DocGraphResponse;
  onOpenNoteById: (nodeId: string) => void;
  selectedNodeId?: string | null;
  /** Plan 268 — si false/undefined, el componente se comporta EXACTAMENTE como en el 111. */
  explorerEnabled?: boolean;
  /** Plan 268 F6 — necesario para el peek. */
  projectName?: string;
}

interface Palette {
  note: string;
  code: string;
  missing: string;
  edge: string;
  stale: string;
  label: string;
  labelBg: string;
  halo: string;
  ring: string;
  /** Plan 268 F0.6 — un color por SLOT de grupo (F5). Orden = GROUP_SLOT_TOKENS. */
  groups: string[];
}

function readPalette(el: HTMLElement): Palette {
  const cs = getComputedStyle(el);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  const t = GRAPH_PALETTE_TOKENS;
  return {
    note: v(t.note.token, t.note.fallback),
    code: v(t.code.token, t.code.fallback),
    missing: v(t.missing.token, t.missing.fallback),
    edge: v(t.edge.token, t.edge.fallback),
    stale: v(t.stale.token, t.stale.fallback),
    label: v(t.label.token, t.label.fallback),
    labelBg: v(t.labelBg.token, t.labelBg.fallback),
    halo: v(t.halo.token, t.halo.fallback),
    ring: v(t.ring.token, t.ring.fallback),
    groups: GROUP_SLOT_TOKENS.map((g) => v(g.token, g.fallback)), // Plan 268 F5
  };
}

function colorForGroup(group: string, pal: Palette): string {
  if (group === "code") return pal.code;
  if (group === "missing") return pal.missing;
  return pal.note; // note:<source>
}

const LABEL_FONT_PX = 11;
const LABEL_HEIGHT_PX = 15;

/** Plan 268 F1 (B4) — Map vacío como CONSTANTE de módulo: si se creara uno nuevo por
 *  render, el efecto de sincronización de I2 se dispararía en cada render. */
const EMPTY_GROUP_SLOTS: Map<string, number> = new Map();

export default function DocGraphView({
  graph,
  onOpenNoteById,
  selectedNodeId,
  explorerEnabled,
  projectName,
}: DocGraphViewProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const stateRef = useRef<LayoutState | null>(null);
  const rafRef = useRef<number | null>(null);
  const hoverRef = useRef<number | null>(null);
  const dragRef = useRef<number | null>(null);
  const filterRef = useRef<Set<string>>(new Set());
  const paletteRef = useRef<Palette | null>(null);
  const drawRef = useRef<() => void>(() => {});
  const viewportRef = useRef<Viewport>(IDENTITY);
  const resetViewRef = useRef<() => void>(() => {});

  // ── Plan 268 F1 — refs que lee draw() (invariante I2 / guardarraíl G12) ─────
  // draw() vive DENTRO del efecto de layout (deps [visibleGraph, selectedNodeId]):
  // cualquier valor de React que lea directamente queda congelado en el closure.
  // Se declaran TODOS acá aunque los llenen fases posteriores, para no volver a
  // tocar la firma del efecto ni este bloque nunca más.
  const activeMatchIdRef = useRef<string | null>(null); // F2 — resultado de búsqueda activo
  const groupSlotsRef = useRef<Map<string, number>>(EMPTY_GROUP_SLOTS); // F5 — slot de color por grupo
  const explorerEnabledRef = useRef<boolean>(false); // F7 — gatea el LOD y el minimapa
  const canvasSizeRef = useRef<{ w: number; h: number }>({ w: 0, h: 0 }); // F2/F3 — encuadre

  // ── refs de COMANDO (B5): funciones definidas DENTRO del efecto de layout y
  //    llamadas desde AFUERA (JSX u otros efectos). Un efecto no puede ver el
  //    closure de otro, así que este es el único puente legítimo. Mismo patrón
  //    que resetViewRef / drawRef.
  const setViewportRef = useRef<(next: Viewport) => void>(() => {});
  const zoomInRef = useRef<() => void>(() => {});
  const zoomOutRef = useRef<() => void>(() => {});
  const fitRef = useRef<() => void>(() => {});

  const [query, setQuery] = useState("");
  const [viewScale, setViewScale] = useState(1);

  // ── Plan 268 F1 — estado del explorador (puro, en docs/graphExplorerState.ts)
  const [ui, dispatch] = useReducer(graphExplorerReducer, INITIAL_EXPLORER_STATE);

  /** Opciones de la barra: derivadas del grafo COMPLETO a propósito (la barra no
   *  debe cambiar de forma cuando el operador filtra). Es una de las DOS únicas
   *  referencias legítimas a `graph` fuera del efecto. */
  const filterOptions = useMemo(() => availableFilterOptions(graph), [graph]);

  /**
   * El subgrafo que realmente se dibuja. Con la flag OFF es el MISMO objeto que
   * `graph` (identidad referencial ⇒ el layout no se re-inicializa, R2).
   *
   * ORDEN FIJO Y OBLIGATORIO: filtros → agrupación → RESOLUCIÓN del foco → foco.
   * Filtrar después de enfocar daría vecindarios rotos; agrupar después de enfocar
   * generaría super-nodos parciales; y sin el paso de resolución, colapsar el grupo
   * del nodo enfocado (o filtrarlo) dejaría la pantalla EN BLANCO (C3 / G13).
   */
  const { visibleGraph, effectiveFocusId } = useMemo(() => {
    if (!explorerEnabled) {
      return { visibleGraph: graph, effectiveFocusId: null as string | null };
    }
    const filtered = applyGraphFilters(graph, ui.filters);
    const grouped = collapseGroups(filtered, ui.collapsedGroups);
    const focusId = resolveFocusId(grouped, graph, ui.focusRootId);
    return {
      visibleGraph: focusId ? focusSubgraph(grouped, focusId, ui.focusDepth) : grouped,
      effectiveFocusId: focusId,
    };
  }, [
    explorerEnabled,
    graph,
    ui.filters,
    ui.collapsedGroups,
    ui.focusRootId,
    ui.focusDepth,
  ]);

  // índices auxiliares del grafo VISIBLE (C5: si apuntaran a `graph` mientras el
  // layout indexa `visibleGraph`, los labels saldrían del nodo equivocado — R1).
  const kindById = useMemo(() => {
    const m = new Map<string, "note" | "code" | "missing">();
    for (const n of visibleGraph.nodes) m.set(n.id, n.kind);
    return m;
  }, [visibleGraph]);

  const orphanSet = useMemo(() => new Set(visibleGraph.orphans ?? []), [visibleGraph]);

  /** Plan 268 F0.3 — id → posición. Reemplaza el findIndex O(n) por label/frame (K8). */
  const indexById = useMemo(() => nodeIndexById(visibleGraph), [visibleGraph]);

  const nodeCount = visibleGraph.nodes.length;

  /** Denominador del contador "N de TOTAL". Es la SEGUNDA (y última) referencia
   *  legítima a `graph` fuera del efecto; se extrae a una constante para que el
   *  grep-gate de la invariante I1 siga dando exactamente un hit. */
  const totalNodes = graph.nodes.length;

  // ── Plan 268 F2 — búsqueda navegable sobre el grafo VISIBLE.
  const matches = useMemo(
    () => (explorerEnabled ? searchGraphNodes(visibleGraph, ui.query) : []),
    [explorerEnabled, visibleGraph, ui.query]
  );

  // Costura F1→F2 resuelta: el placeholder tipado pasa a ser el valor real, SIN
  // tocar el efecto de sincronización ni la lista de refs (contrato de F1.3-3).
  const activeMatchId: string | null = matchAt(matches, ui.matchIndex);
  const groupSlots: Map<string, number> = EMPTY_GROUP_SLOTS; // F5 lo reemplaza

  /** (C3) La búsqueda corre sobre lo VISIBLE. Si hay filtros o foco activos, el
   *  contador lo dice para que nadie interprete que una nota "no está" cuando en
   *  realidad está filtrada. */
  const searchScopeIsPartial =
    ui.focusRootId !== null ||
    ui.collapsedGroups.length > 0 ||
    visibleGraph.nodes.length !== totalNodes;

  /** Nodo efectivamente enfocado, resuelto contra el grafo compuesto. `ui.focusRootId`
   *  es lo que el operador PIDIÓ; `effectiveFocusId` es lo que se puede mostrar. */
  const focusNode = useMemo(
    () =>
      effectiveFocusId ? (visibleGraph.nodes.find((n) => n.id === effectiveFocusId) ?? null) : null,
    [visibleGraph, effectiveFocusId]
  );

  /** Vecinos directos del foco, para la lista "Relaciones" del peek (F6). */
  const focusNeighbors = useMemo(
    () => (effectiveFocusId ? rankedNeighbors(visibleGraph, effectiveFocusId) : []),
    [visibleGraph, effectiveFocusId]
  );

  /** (C3) El operador pidió un foco que la vista actual no puede mostrar. NUNCA se
   *  limpia solo: se le avisa y él decide (G4). */
  const focusUnavailable = ui.focusRootId !== null && effectiveFocusId === null;
  const focusRemapped =
    effectiveFocusId !== null && effectiveFocusId !== ui.focusRootId && isGroupNodeId(effectiveFocusId);

  /** Plan 268 F3 — atajos de teclado del canvas. Se registran sobre el `.canvasBox`
   *  (NO sobre `window`: no deben dispararse mientras el operador escribe en otra
   *  parte de la app) y llaman a los refs de comando que llena el efecto de layout. */
  function onCanvasKeyDown(evt: ReactKeyboardEvent<HTMLDivElement>) {
    // Guardia obligatoria: un atajo sin modificador jamás se dispara con el foco
    // dentro de un campo editable.
    const t = evt.target as HTMLElement | null;
    const tag = (t?.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || t?.isContentEditable) return;
    const PAN_PX = 40;
    switch (evt.key) {
      case "+":
      case "=":
        evt.preventDefault();
        zoomInRef.current();
        break;
      case "-":
        evt.preventDefault();
        zoomOutRef.current();
        break;
      case "0":
        evt.preventDefault();
        resetViewRef.current();
        break;
      case "f":
      case "F":
        evt.preventDefault();
        fitRef.current();
        break;
      case "Escape":
        evt.preventDefault();
        dispatch({ type: "CLEAR_FOCUS" });
        dispatch({ type: "SET_PEEK", nodeId: null });
        break;
      case "ArrowLeft":
        evt.preventDefault();
        setViewportRef.current(panBy(viewportRef.current, PAN_PX, 0));
        break;
      case "ArrowRight":
        evt.preventDefault();
        setViewportRef.current(panBy(viewportRef.current, -PAN_PX, 0));
        break;
      case "ArrowUp":
        evt.preventDefault();
        setViewportRef.current(panBy(viewportRef.current, 0, PAN_PX));
        break;
      case "ArrowDown":
        evt.preventDefault();
        setViewportRef.current(panBy(viewportRef.current, 0, -PAN_PX));
        break;
      default:
        break;
    }
  }

  // UN solo efecto de sincronización de refs (no cuatro), que además fuerza el
  // redibujo en modo estático. Regla de oro: dentro de draw() se lee xxxRef.current,
  // NUNCA la variable del render.
  useEffect(() => {
    activeMatchIdRef.current = activeMatchId;
    groupSlotsRef.current = groupSlots;
    explorerEnabledRef.current = Boolean(explorerEnabled);
    if (stateRef.current && !stateRef.current.animated) drawRef.current();
  }, [activeMatchId, groupSlots, explorerEnabled]);

  // Recalcular el set de resaltado cuando cambia la búsqueda (sin reiniciar el
  // layout). Con la flag ON la fuente de verdad es ui.query (vía `matches`); con
  // la flag OFF sigue siendo el useState `query`, exactamente como en el 111.
  useEffect(() => {
    filterRef.current = explorerEnabled ? matchIdSet(matches) : filterNodeIds(graph, query);
    // en modo estático hay que forzar un redibujo
    if (stateRef.current && !stateRef.current.animated) drawRef.current();
  }, [explorerEnabled, matches, query, graph]);

  // Plan 268 F2.2-4 — encuadrar el resultado ACTIVO de la búsqueda. El findIndex
  // corre una vez por salto (no por frame). No puede llamar a `setViewport` a
  // secas: esa función vive dentro de OTRO efecto (B5) ⇒ se usa el ref de comando,
  // que F3 llena. Antes de F3 es el no-op inicial: la fase compila y no hace nada.
  useEffect(() => {
    if (!explorerEnabled || !activeMatchId) return;
    const st = stateRef.current;
    if (!st) return;
    const idx = st.nodes.findIndex((n) => n.id === activeMatchId);
    if (idx < 0) return;
    const n = st.nodes[idx];
    const { w: cw, h: ch } = canvasSizeRef.current;
    setViewportRef.current(centerOn(viewportRef.current, n.x, n.y, cw, ch));
  }, [explorerEnabled, activeMatchId]);

  // Plan 268 F4.2-4 — encuadre automático al enfocar / cambiar de profundidad. No es
  // autonomía (G4): es la consecuencia visual directa de un click del operador. El
  // rAF espera a que el layout ya tenga posiciones.
  useEffect(() => {
    if (!explorerEnabled || !ui.focusRootId) return;
    const raf = requestAnimationFrame(() => fitRef.current());
    return () => cancelAnimationFrame(raf);
  }, [explorerEnabled, ui.focusRootId, ui.focusDepth]);

  // Redibujar cuando cambia la selección (modo estático).
  useEffect(() => {
    if (stateRef.current && !stateRef.current.animated) drawRef.current();
  }, [selectedNodeId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const box = boxRef.current;
    if (!canvas || !box) return;

    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const pal = readPalette(canvas);
    paletteRef.current = pal;

    function sizeCanvas(): { w: number; h: number } {
      const rect = box!.getBoundingClientRect();
      const w = Math.max(50, Math.floor(rect.width));
      const h = Math.max(50, Math.floor(rect.height));
      const dpr = window.devicePixelRatio || 1;
      canvas!.width = Math.floor(w * dpr);
      canvas!.height = Math.floor(h * dpr);
      const ctx = canvas!.getContext("2d");
      if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      canvasSizeRef.current = { w, h }; // Plan 268 I2 — sin esto el encuadre usa 0×0
      return { w, h };
    }

    /** Plan 268 F3 (C7) — re-init del viewport SIN dibujar. Se usa solo en los dos
     *  caminos que re-inicializan el layout y dibujan inmediatamente después (evita
     *  el doble draw). Lo importante es que `viewScale` NUNCA queda desincronizado:
     *  ese era el bug de C7 (el indicador decía 195% con el grafo al 100%). */
    function initViewport() {
      viewportRef.current = IDENTITY;
      setViewScale(IDENTITY.scale);
    }

    let fitRaf: number | null = null;

    let { w, h } = sizeCanvas();
    stateRef.current = initLayout(visibleGraph, w, h, Boolean(reducedMotion));
    initViewport();

    function neighborsOf(idx: number, state: LayoutState): Set<number> {
      const set = new Set<number>();
      for (const e of state.edges) {
        if (e.source === idx) set.add(e.target);
        else if (e.target === idx) set.add(e.source);
      }
      return set;
    }

    function draw() {
      const state = stateRef.current;
      const ctx = canvas!.getContext("2d");
      if (!state || !ctx) return;
      const palette = paletteRef.current!;
      const vp = viewportRef.current;
      ctx.clearRect(0, 0, w, h);

      const filter = filterRef.current;
      const hasFilter = filter.size > 0;
      const hover = hoverRef.current;
      const hoverNeighbors =
        hover !== null ? neighborsOf(hover, state) : null;

      const nodeAlpha = (i: number): number => {
        const id = state.nodes[i].id;
        if (hasFilter) return filter.has(id) ? 1 : 0.12;
        if (hover !== null)
          return i === hover || hoverNeighbors!.has(i) ? 1 : 0.14;
        return orphanSet.has(id) ? 0.6 : 1;
      };

      ctx.save();
      ctx.translate(vp.tx, vp.ty);
      ctx.scale(vp.scale, vp.scale);

      // aristas primero
      for (const e of state.edges) {
        const a = state.nodes[e.source];
        const b = state.nodes[e.target];
        const hoverEdge =
          hover !== null && (e.source === hover || e.target === hover);
        const al = Math.min(nodeAlpha(e.source), nodeAlpha(e.target));
        ctx.globalAlpha = al * (hoverEdge ? 0.95 : 0.55);
        ctx.strokeStyle = e.stale ? palette.stale : hoverEdge ? palette.halo : palette.edge;
        ctx.lineWidth = (hoverEdge ? 1.6 : 1) / vp.scale;
        if (e.stale) ctx.setLineDash([4 / vp.scale, 3 / vp.scale]);
        else ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // nodos
      for (let i = 0; i < state.nodes.length; i++) {
        const node = state.nodes[i];
        const al = nodeAlpha(i);
        ctx.globalAlpha = al;
        // halo del seleccionado
        if (selectedNodeId && node.id === selectedNodeId) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.r + 4 / vp.scale, 0, Math.PI * 2);
          ctx.strokeStyle = palette.halo;
          ctx.lineWidth = 2 / vp.scale;
          ctx.stroke();
        }
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
        ctx.fillStyle = colorForGroup(node.group, palette);
        ctx.fill();
        // anillo del hovered (feedback de "clickeable")
        if (i === hover) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.r + 2 / vp.scale, 0, Math.PI * 2);
          ctx.strokeStyle = palette.ring;
          ctx.lineWidth = 1.5 / vp.scale;
          ctx.stroke();
        }
        // Plan 268 F2.2-5 — anillo del resultado ACTIVO de la búsqueda. Se lee el
        // REF (I2): con la variable del render, el anillo quedaría clavado en el
        // primer resultado y apretar Enter movería el contador pero no el dibujo.
        if (activeMatchIdRef.current && node.id === activeMatchIdRef.current) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.r + 3 / vp.scale, 0, Math.PI * 2);
          ctx.strokeStyle = palette.halo;
          ctx.lineWidth = 2 / vp.scale;
          ctx.stroke();
        }
      }
      ctx.restore();

      // ── Labels en espacio de PANTALLA (tamaño constante, sin solaparse) ────
      const candidates: LabelCandidate[] = [];
      const zoomedIn = vp.scale >= 1.4;
      for (let i = 0; i < state.nodes.length; i++) {
        const node = state.nodes[i];
        const id = node.id;
        if (hasFilter && !filter.has(id)) continue;
        const isHover = i === hover;
        const isSelected = Boolean(selectedNodeId && id === selectedNodeId);
        const isNeighbor = hover !== null && hoverNeighbors!.has(i);
        const isActiveMatch = activeMatchIdRef.current === id; // I2: el ref, no el render
        const isHub = node.r >= 9;
        if (
          !isHover &&
          !isSelected &&
          !isNeighbor &&
          !isActiveMatch &&
          !isHub &&
          !zoomedIn &&
          !hasFilter
        )
          continue;
        if (hover !== null && !isHover && !isNeighbor && !isSelected && !isActiveMatch) continue;
        const g = visibleGraph.nodes[i];
        const text = g ? g.label : id;
        const p = toScreen(vp, node.x, node.y);
        // fuera de pantalla: no compite por espacio
        if (p.x < -150 || p.x > w + 30 || p.y < -20 || p.y > h + 20) continue;
        candidates.push({
          id,
          x: p.x + node.r * vp.scale + 4,
          y: p.y,
          width: estimateLabelWidth(text, LABEL_FONT_PX),
          height: LABEL_HEIGHT_PX,
          priority: isHover
            ? 1000
            : isActiveMatch
              ? 950 // Plan 268 F2.2-5 — entre hover (1000) y seleccionado (900)
              : isSelected
                ? 900
                : isNeighbor
                  ? 500
                  : node.r,
        });
      }
      const visible = pickVisibleLabels(candidates, 60);
      ctx.font = `${LABEL_FONT_PX}px system-ui, sans-serif`;
      ctx.textBaseline = "middle";
      for (const c of candidates) {
        if (!visible.has(c.id)) continue;
        const idx = indexById.get(c.id);
        const text = idx !== undefined ? visibleGraph.nodes[idx].label : c.id;
        // pill de fondo para legibilidad sobre aristas
        ctx.globalAlpha = 0.82;
        ctx.fillStyle = pal.labelBg;
        const rw = c.width;
        const rh = c.height;
        ctx.beginPath();
        if (typeof (ctx as any).roundRect === "function") {
          (ctx as any).roundRect(c.x - 2, c.y - rh / 2, rw, rh, 4);
        } else {
          ctx.rect(c.x - 2, c.y - rh / 2, rw, rh);
        }
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.fillStyle = pal.label;
        ctx.fillText(text, c.x + 2, c.y);
      }
      ctx.globalAlpha = 1;
    }
    drawRef.current = draw;

    /**
     * Plan 268 F3 (C7) — ÚNICO lugar del componente donde se escribe
     * viewportRef.current en respuesta a un gesto. Mantiene el % de zoom
     * sincronizado y redibuja. Vive DENTRO del efecto de layout; los llamadores
     * externos (JSX y otros efectos) pasan por setViewportRef (B5).
     */
    function setViewport(next: Viewport) {
      if (next === viewportRef.current) return; // zoomAt devuelve el MISMO objeto si clampeó
      viewportRef.current = next;
      setViewScale(next.scale);
      draw();
    }

    // Los 4 refs de comando ya están DECLARADOS en el cuerpo del componente (F1);
    // acá solo se LLENAN. Esta es la línea que cierra las costuras F2→F3 y F7→F3:
    // sin ella el encuadre al resultado de búsqueda y el click del minimapa quedan
    // como no-ops SILENCIOSOS (no fallan: simplemente no hacen nada).
    setViewportRef.current = setViewport;
    zoomInRef.current = () => setViewport(zoomAtCenter(viewportRef.current, ZOOM_STEP, w, h));
    zoomOutRef.current = () => setViewport(zoomAtCenter(viewportRef.current, 1 / ZOOM_STEP, w, h));
    fitRef.current = () => {
      const st = stateRef.current;
      if (!st || !st.nodes.length) return;
      setViewport(fitViewport(st.nodes.map((n) => ({ x: n.x, y: n.y, r: n.r })), w, h, 40));
    };

    function tick() {
      const state = stateRef.current;
      if (!state) return;
      if (state.animated) {
        stepLayout(state);
        draw();
        rafRef.current = requestAnimationFrame(tick);
      }
    }

    if (stateRef.current.animated) {
      rafRef.current = requestAnimationFrame(tick);
    } else {
      staticLayout(stateRef.current);
      draw();
    }

    resetViewRef.current = () => setViewport(IDENTITY);

    // Plan 268 F3 (C7) — re-encuadre tras cada re-init, SOLO en modo explorador.
    // Cuando el operador toca un filtro el subgrafo aparece encuadrado en vez de
    // aparecer a escala 1 con la mitad afuera. No es autonomía (G4): es la
    // consecuencia visual directa de su click. El rAF espera a que staticLayout /
    // el primer stepLayout ya hayan puesto posiciones.
    if (explorerEnabledRef.current && visibleGraph.nodes.length > 0) {
      fitRaf = requestAnimationFrame(() => {
        fitRaf = null;
        fitRef.current();
      });
    }

    // ── Interacción ──────────────────────────────────────────────────────────
    function toLocal(ev: PointerEvent | WheelEvent): { x: number; y: number } {
      const rect = canvas!.getBoundingClientRect();
      return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
    }

    function nearestNode(sx: number, sy: number): number | null {
      const state = stateRef.current;
      if (!state) return null;
      const vp = viewportRef.current;
      const { x, y } = toWorld(vp, sx, sy);
      let best: number | null = null;
      let bestD = Infinity;
      const pickBase = 12 / vp.scale; // 12px de pantalla, en unidades de mundo
      for (let i = 0; i < state.nodes.length; i++) {
        const n = state.nodes[i];
        const dx = n.x - x;
        const dy = n.y - y;
        const d = Math.sqrt(dx * dx + dy * dy);
        const pick = Math.max(pickBase, n.r + 4 / vp.scale); // (C6)
        if (d <= pick && d < bestD) {
          bestD = d;
          best = i;
        }
      }
      return best;
    }

    function syncCursor() {
      const hover = hoverRef.current;
      if (panActive) {
        canvas!.style.cursor = "grabbing";
        return;
      }
      if (hover !== null) {
        const id = stateRef.current?.nodes[hover]?.id;
        canvas!.style.cursor =
          id && kindById.get(id) === "note" ? "pointer" : "default";
        return;
      }
      canvas!.style.cursor = "grab";
    }

    let downPos: { x: number; y: number } | null = null;
    let movedFar = false;
    let panActive = false;

    function onPointerDown(ev: PointerEvent) {
      // (C9) SIN ESTO LOS ATAJOS DE TECLADO ESTÁN MUERTOS: el click cae en el
      // <canvas> hijo y `pointerdown` NO enfoca a un ancestro con tabIndex, así que
      // el keydown se iría al <body>. Primera instrucción, a propósito.
      boxRef.current?.focus({ preventScroll: true });
      const { x, y } = toLocal(ev);
      downPos = { x, y };
      movedFar = false;
      const idx = nearestNode(x, y);
      if (idx !== null) {
        dragRef.current = idx;
      } else {
        panActive = true; // arrastrar el fondo = pan
      }
      canvas!.setPointerCapture?.(ev.pointerId);
      syncCursor();
    }

    function onPointerMove(ev: PointerEvent) {
      const { x, y } = toLocal(ev);
      const state = stateRef.current;
      if (!state) return;
      const vp = viewportRef.current;
      if (downPos) {
        const dx = x - downPos.x;
        const dy = y - downPos.y;
        if (dx * dx + dy * dy > 9) movedFar = true;
      }
      if (panActive && downPos) {
        setViewport(panBy(vp, x - downPos.x, y - downPos.y)); // C7: escritor único
        downPos = { x, y };
        return;
      }
      const drag = dragRef.current;
      if (drag !== null) {
        const n = state.nodes[drag];
        const wpt = toWorld(vp, x, y);
        n.x = Math.min(Math.max(wpt.x, n.r), state.width - n.r);
        n.y = Math.min(Math.max(wpt.y, n.r), state.height - n.r);
        n.vx = 0;
        n.vy = 0;
        if (!state.animated) draw();
        return;
      }
      const idx = nearestNode(x, y);
      if (idx !== hoverRef.current) {
        hoverRef.current = idx;
        syncCursor();
        if (!state.animated) draw();
      }
    }

    function onPointerUp(ev: PointerEvent) {
      const { x, y } = toLocal(ev);
      const wasDrag = dragRef.current;
      const wasPan = panActive;
      dragRef.current = null;
      panActive = false;
      canvas!.releasePointerCapture?.(ev.pointerId);
      downPos = null;
      syncCursor();
      if (wasPan) return; // fue un pan (o un click al vacío)
      if (wasDrag !== null && movedFar) return; // fue un drag real de nodo
      const idx = nearestNode(x, y);
      if (idx === null) return;
      const state = stateRef.current;
      if (!state) return;
      const id = state.nodes[idx].id;
      // TABLA ÚNICA DE GESTOS (F4.2-1). Se lee explorerEnabledRef, NO la prop: con
      // filtros vacíos `visibleGraph === graph`, así que este efecto NO se re-crea
      // cuando la flag llega del backend y la prop del closure quedaría en false.
      if (!explorerEnabledRef.current) {
        if (kindById.get(id) === "note") onOpenNoteById(id); // comportamiento del 111
        return;
      }
      if (isGroupNodeId(id)) {
        const key = groupKeyFromNodeId(id);
        if (key) dispatch({ type: "TOGGLE_GROUP_COLLAPSED", groupKey: key }); // des-colapsa
        return;
      }
      dispatch({ type: "FOCUS_NODE", nodeId: id }); // enfoca y abre el peek
    }

    function onPointerLeave() {
      if (hoverRef.current !== null) {
        hoverRef.current = null;
        syncCursor();
        const state = stateRef.current;
        if (state && !state.animated) draw();
      }
    }

    function onWheel(ev: WheelEvent) {
      ev.preventDefault();
      const { x, y } = toLocal(ev);
      const factor = Math.exp(-ev.deltaY * 0.0015);
      setViewport(zoomAt(viewportRef.current, factor, x, y)); // C7: escritor único
    }

    function onDblClick(ev: MouseEvent) {
      // TABLA ÚNICA DE GESTOS (F4.2-1). En modo 111 el doble click SIEMPRE resetea.
      if (!explorerEnabledRef.current) {
        resetViewRef.current();
        return;
      }
      const rect = canvas!.getBoundingClientRect();
      const idx = nearestNode(ev.clientX - rect.left, ev.clientY - rect.top);
      if (idx === null) {
        resetViewRef.current(); // doble click al vacío: el reset del 111 sigue vivo
        return;
      }
      const state = stateRef.current;
      if (!state) return;
      const id = state.nodes[idx].id;
      // note → abre en el Lector; code / missing / super-nodo → nada (no hay doc).
      if (!isGroupNodeId(id) && kindById.get(id) === "note") onOpenNoteById(id);
    }

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerLeave);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("dblclick", onDblClick);
    syncCursor();

    // Resize → re-inicializar layout.
    const ro = new ResizeObserver(() => {
      const size = sizeCanvas();
      w = size.w;
      h = size.h;
      stateRef.current = initLayout(visibleGraph, w, h, Boolean(reducedMotion));
      initViewport(); // C7: el % de zoom no puede quedar mintiendo tras un resize
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      if (stateRef.current.animated) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        staticLayout(stateRef.current);
        draw();
      }
    });
    ro.observe(box);

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      if (fitRaf !== null) {
        cancelAnimationFrame(fitRaf);
        fitRaf = null;
      }
      ro.disconnect();
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("dblclick", onDblClick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleGraph, selectedNodeId]);

  return (
    <div className={styles.wrap}>
      {explorerEnabled ? (
        <DocGraphFilterBar
          options={filterOptions}
          filters={ui.filters}
          onToggleSource={(id) => dispatch({ type: "TOGGLE_SOURCE", sourceId: id })}
          onToggleKind={(kind) => dispatch({ type: "TOGGLE_KIND", kind })}
          onToggleEdgeKind={(edgeKind) => dispatch({ type: "TOGGLE_EDGE_KIND", edgeKind })}
          onSetMinDegree={(n) => dispatch({ type: "SET_MIN_DEGREE", minDegree: n })}
          onToggleHideOrphans={() => dispatch({ type: "TOGGLE_HIDE_ORPHANS" })}
          onToggleOnlyStale={() => dispatch({ type: "TOGGLE_ONLY_STALE" })}
          onReset={() => dispatch({ type: "RESET_FILTERS" })}
          visibleNodes={visibleGraph.nodes.length}
          totalNodes={totalNodes}
        />
      ) : null}
      <div className={styles.toolbar}>
        <input
          type="search"
          className={styles.search}
          placeholder="Buscar nodo..."
          value={explorerEnabled ? ui.query : query}
          onChange={(e) =>
            explorerEnabled
              ? dispatch({ type: "SET_QUERY", query: e.target.value })
              : setQuery(e.target.value)
          }
          onKeyDown={(ev) => {
            if (!explorerEnabled) return;
            if (ev.key === "Enter") {
              ev.preventDefault();
              dispatch({
                type: ev.shiftKey ? "PREV_MATCH" : "NEXT_MATCH",
                total: matches.length,
              });
            } else if (ev.key === "Escape") {
              ev.preventDefault();
              dispatch({ type: "SET_QUERY", query: "" });
            }
          }}
          aria-label="Buscar nodo en el grafo"
        />
        {explorerEnabled ? (
          <span className={ex.searchRow}>
            <span className={ex.matchCount}>
              {matches.length ? ui.matchIndex + 1 : 0} de {matches.length}
              {searchScopeIsPartial ? " (en lo visible)" : ""}
            </span>
            <button
              type="button"
              className={ex.navBtn}
              title="Coincidencia anterior"
              aria-label="Coincidencia anterior"
              disabled={!matches.length}
              onClick={() => dispatch({ type: "PREV_MATCH", total: matches.length })}
            >
              &#9650;
            </button>
            <button
              type="button"
              className={ex.navBtn}
              title="Coincidencia siguiente"
              aria-label="Coincidencia siguiente"
              disabled={!matches.length}
              onClick={() => dispatch({ type: "NEXT_MATCH", total: matches.length })}
            >
              &#9660;
            </button>
          </span>
        ) : null}
        <div className={styles.legend} aria-hidden="false">
          <span className={styles.legendItem}>
            <span className={styles.swatch} style={{ background: "var(--accent, #388bfd)" }} />
            Nota
          </span>
          <span className={styles.legendItem}>
            <span className={styles.swatch} style={{ background: "var(--success, #3fb950)" }} />
            Código
          </span>
          <span className={styles.legendItem}>
            <span className={styles.swatch} style={{ background: "var(--danger, #f85149)" }} />
            Faltante
          </span>
        </div>
        <button
          type="button"
          className={styles.resetBtn}
          onClick={() => resetViewRef.current()}
          title="Restablecer zoom y posición"
        >
          Centrar
        </button>
      </div>
      {explorerEnabled && ui.focusRootId ? (
        <div className={ex.breadcrumbs}>
          <button
            type="button"
            className={ex.navBtn}
            onClick={() => dispatch({ type: "FOCUS_BACK" })}
            disabled={ui.focusHistory.length === 0 && !ui.focusRootId}
            title="Volver al nodo anterior"
          >
            &#8592; Volver
          </button>
          {focusUnavailable ? (
            <span className={ex.focusWarn}>
              El nodo enfocado no está en la vista actual (lo ocultó un filtro o un grupo
              colapsado).
            </span>
          ) : (
            <span className={ex.focusLabel}>
              Foco: {focusNode?.label ?? effectiveFocusId}
              {focusRemapped
                ? ` (${groupLabelOf(groupKeyFromNodeId(effectiveFocusId!) ?? "")} colapsado)`
                : ""}
            </span>
          )}
          <span className={ex.depthGroup}>
            {[1, 2, 3].map((d) => (
              <button
                key={d}
                type="button"
                className={ex.navBtn}
                aria-pressed={ui.focusDepth === d}
                onClick={() => dispatch({ type: "SET_FOCUS_DEPTH", depth: d })}
                title={`Mostrar vecinos a ${d} salto${d > 1 ? "s" : ""}`}
              >
                {d}
              </button>
            ))}
          </span>
          <button
            type="button"
            className={ex.navBtn}
            onClick={() => dispatch({ type: "CLEAR_FOCUS" })}
            title="Volver a ver el grafo completo"
          >
            Ver todo
          </button>
          <span className={ex.counter}>
            {nodeCount} de {totalNodes} nodos
          </span>
        </div>
      ) : null}
      {/* Plan 268 — con la flag OFF este contenedor es `display: contents`, así que
          el canvas sigue siendo hijo directo del flex de .wrap (layout del 111). */}
      <div className={explorerEnabled ? ex.body : ex.bodyPlain}>
        <div
          className={styles.canvasBox}
          ref={boxRef}
          tabIndex={explorerEnabled ? 0 : undefined}
          onKeyDown={explorerEnabled ? onCanvasKeyDown : undefined}
        >
          {nodeCount === 0 ? (
            <div className={styles.empty}>
              {explorerEnabled && totalNodes > 0
                ? "Ningún nodo pasa los filtros actuales. Usá «Limpiar filtros» para volver a ver el grafo completo."
                : "El grafo no tiene nodos todavía. Verificá que haya documentación en la fuente seleccionada."}
            </div>
          ) : (
            <>
              <canvas ref={canvasRef} className={styles.canvas} />
              {explorerEnabled ? (
                <DocGraphZoomControls
                  scale={viewScale}
                  onZoomIn={() => zoomInRef.current()}
                  onZoomOut={() => zoomOutRef.current()}
                  onFit={() => fitRef.current()}
                  onReset={() => resetViewRef.current()}
                  canZoomIn={viewScale < MAX_SCALE}
                  canZoomOut={viewScale > MIN_SCALE}
                />
              ) : null}
              <div className={styles.hint} aria-hidden="true">
                {explorerEnabled
                  ? "Rueda o + / −: zoom · F: ajustar · 0: restablecer · Arrastrá el fondo: mover · Click: enfocar · Doble click: abrir · Click en el grafo para usar el teclado"
                  : "Rueda: zoom · Arrastrá el fondo: mover · Click en una nota: abrirla"}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
