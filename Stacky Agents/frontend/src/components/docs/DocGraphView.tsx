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
import { useEffect, useMemo, useRef, useState } from "react";
import type { DocGraphResponse } from "../../docs/docGraphModel";
import { filterNodeIds } from "../../docs/docGraphModel";
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
  type Viewport,
  type LabelCandidate,
} from "../../docs/graphViewport";
import styles from "./DocGraphView.module.css";

interface DocGraphViewProps {
  graph: DocGraphResponse;
  onOpenNoteById: (nodeId: string) => void;
  selectedNodeId?: string | null;
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
}

function readPalette(el: HTMLElement): Palette {
  const cs = getComputedStyle(el);
  const v = (name: string, fallback: string) => {
    const raw = cs.getPropertyValue(name).trim();
    return raw || fallback;
  };
  return {
    note: v("--color-accent", "#4a9eff"),
    code: v("--color-success", "#3fb950"),
    missing: v("--color-danger", "#f85149"),
    edge: v("--color-border", "#3a3a3a"),
    stale: v("--color-danger", "#f85149"),
    label: v("--color-text", "#d0d4da"),
    labelBg: v("--color-surface", "#141414"),
    halo: v("--color-accent", "#4a9eff"),
    ring: v("--color-text", "#e6e6e6"),
  };
}

function colorForGroup(group: string, pal: Palette): string {
  if (group === "code") return pal.code;
  if (group === "missing") return pal.missing;
  return pal.note; // note:<source>
}

const LABEL_FONT_PX = 11;
const LABEL_HEIGHT_PX = 15;

export default function DocGraphView({
  graph,
  onOpenNoteById,
  selectedNodeId,
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

  const [query, setQuery] = useState("");

  // índices auxiliares del grafo
  const kindById = useMemo(() => {
    const m = new Map<string, "note" | "code" | "missing">();
    for (const n of graph.nodes) m.set(n.id, n.kind);
    return m;
  }, [graph]);

  const orphanSet = useMemo(() => new Set(graph.orphans ?? []), [graph]);

  const nodeCount = graph.nodes.length;

  // Recalcular el set de filtro cuando cambia la query (sin reiniciar el layout).
  useEffect(() => {
    filterRef.current = filterNodeIds(graph, query);
    // en modo estático hay que forzar un redibujo
    if (stateRef.current && !stateRef.current.animated) drawRef.current();
  }, [query, graph]);

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
      return { w, h };
    }

    let { w, h } = sizeCanvas();
    stateRef.current = initLayout(graph, w, h, Boolean(reducedMotion));
    viewportRef.current = IDENTITY;

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
        const isHub = node.r >= 9;
        if (!isHover && !isSelected && !isNeighbor && !isHub && !zoomedIn && !hasFilter)
          continue;
        if (hover !== null && !isHover && !isNeighbor && !isSelected) continue;
        const g = graph.nodes[i];
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
          priority: isHover ? 1000 : isSelected ? 900 : isNeighbor ? 500 : node.r,
        });
      }
      const visible = pickVisibleLabels(candidates, 60);
      ctx.font = `${LABEL_FONT_PX}px system-ui, sans-serif`;
      ctx.textBaseline = "middle";
      for (const c of candidates) {
        if (!visible.has(c.id)) continue;
        const idx = graph.nodes.findIndex((n) => n.id === c.id);
        const text = idx >= 0 ? graph.nodes[idx].label : c.id;
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

    resetViewRef.current = () => {
      viewportRef.current = IDENTITY;
      draw();
    };

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
        viewportRef.current = panBy(vp, x - downPos.x, y - downPos.y);
        downPos = { x, y };
        draw();
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
      if (kindById.get(id) === "note") onOpenNoteById(id);
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
      const next = zoomAt(viewportRef.current, factor, x, y);
      if (next === viewportRef.current) return;
      viewportRef.current = next;
      const state = stateRef.current;
      if (state && !state.animated) draw();
      else draw(); // feedback inmediato también en modo animado
    }

    function onDblClick() {
      resetViewRef.current();
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
      stateRef.current = initLayout(graph, w, h, Boolean(reducedMotion));
      viewportRef.current = IDENTITY;
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
      ro.disconnect();
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("dblclick", onDblClick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, selectedNodeId]);

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <input
          type="search"
          className={styles.search}
          placeholder="Buscar nodo..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Buscar nodo en el grafo"
        />
        <div className={styles.legend} aria-hidden="false">
          <span className={styles.legendItem}>
            <span className={styles.swatch} style={{ background: "var(--color-accent, #4a9eff)" }} />
            Nota
          </span>
          <span className={styles.legendItem}>
            <span className={styles.swatch} style={{ background: "var(--color-success, #3fb950)" }} />
            Código
          </span>
          <span className={styles.legendItem}>
            <span className={styles.swatch} style={{ background: "var(--color-danger, #f85149)" }} />
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
      <div className={styles.canvasBox} ref={boxRef}>
        {nodeCount === 0 ? (
          <div className={styles.empty}>
            El grafo no tiene nodos todavía. Verificá que haya documentación en la
            fuente seleccionada.
          </div>
        ) : (
          <>
            <canvas ref={canvasRef} className={styles.canvas} />
            <div className={styles.hint} aria-hidden="true">
              Rueda: zoom · Arrastrá el fondo: mover · Click en una nota: abrirla
            </div>
          </>
        )}
      </div>
    </div>
  );
}
