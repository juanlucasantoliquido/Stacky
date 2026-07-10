/**
 * DocGraphView.tsx — Plan 111 F3.
 *
 * Dibuja el grafo documental (109) en un <canvas> 2D nativo (SIN dependencias nuevas).
 * Corre el bucle de animación solo cuando corresponde (<=300 nodos y sin
 * prefers-reduced-motion), y maneja hover (resalta vecinos), click (abre nota) y drag.
 * La búsqueda resalta nodos por label (helper puro filterNodeIds en docGraphModel).
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
  halo: string;
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
    label: v("--color-text-muted", "#9aa0a6"),
    halo: v("--color-accent", "#4a9eff"),
  };
}

function colorForGroup(group: string, pal: Palette): string {
  if (group === "code") return pal.code;
  if (group === "missing") return pal.missing;
  return pal.note; // note:<source>
}

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
      ctx.clearRect(0, 0, w, h);

      const filter = filterRef.current;
      const hasFilter = filter.size > 0;
      const hover = hoverRef.current;
      const hoverNeighbors =
        hover !== null ? neighborsOf(hover, state) : null;

      const nodeAlpha = (i: number): number => {
        const id = state.nodes[i].id;
        if (hasFilter) return filter.has(id) ? 1 : 0.15;
        if (hover !== null)
          return i === hover || hoverNeighbors!.has(i) ? 1 : 0.22;
        return orphanSet.has(id) ? 0.6 : 1;
      };

      // aristas primero
      for (const e of state.edges) {
        const a = state.nodes[e.source];
        const b = state.nodes[e.target];
        const al = Math.min(nodeAlpha(e.source), nodeAlpha(e.target));
        ctx.globalAlpha = al * 0.6;
        ctx.strokeStyle = e.stale ? palette.stale : palette.edge;
        ctx.lineWidth = 1;
        if (e.stale) ctx.setLineDash([4, 3]);
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
          ctx.arc(node.x, node.y, node.r + 4, 0, Math.PI * 2);
          ctx.strokeStyle = palette.halo;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
        ctx.fillStyle = colorForGroup(node.group, palette);
        ctx.fill();
      }

      // labels solo en hubs (r grande) o en el hovered
      ctx.globalAlpha = 1;
      ctx.fillStyle = palette.label;
      ctx.font = "11px sans-serif";
      for (let i = 0; i < state.nodes.length; i++) {
        const node = state.nodes[i];
        const isHub = node.r >= 10;
        if (!isHub && i !== hover) continue;
        if (hasFilter && !filter.has(node.id)) continue;
        const g = graph.nodes[i];
        const text = g ? g.label : node.id;
        ctx.fillText(text, node.x + node.r + 3, node.y + 3);
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

    // ── Interacción ──────────────────────────────────────────────────────────
    function toLocal(ev: PointerEvent): { x: number; y: number } {
      const rect = canvas!.getBoundingClientRect();
      return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
    }

    function nearestNode(x: number, y: number): number | null {
      const state = stateRef.current;
      if (!state) return null;
      let best: number | null = null;
      let bestD = Infinity;
      for (let i = 0; i < state.nodes.length; i++) {
        const n = state.nodes[i];
        const dx = n.x - x;
        const dy = n.y - y;
        const d = Math.sqrt(dx * dx + dy * dy);
        const pick = Math.max(12, n.r + 4); // (C6)
        if (d <= pick && d < bestD) {
          bestD = d;
          best = i;
        }
      }
      return best;
    }

    let downPos: { x: number; y: number } | null = null;
    let movedFar = false;

    function onPointerDown(ev: PointerEvent) {
      const { x, y } = toLocal(ev);
      downPos = { x, y };
      movedFar = false;
      const idx = nearestNode(x, y);
      if (idx !== null) {
        dragRef.current = idx;
        canvas!.setPointerCapture?.(ev.pointerId);
      }
    }

    function onPointerMove(ev: PointerEvent) {
      const { x, y } = toLocal(ev);
      const state = stateRef.current;
      if (!state) return;
      if (downPos) {
        const dx = x - downPos.x;
        const dy = y - downPos.y;
        if (dx * dx + dy * dy > 9) movedFar = true;
      }
      const drag = dragRef.current;
      if (drag !== null) {
        const n = state.nodes[drag];
        n.x = Math.min(Math.max(x, n.r), state.width - n.r);
        n.y = Math.min(Math.max(y, n.r), state.height - n.r);
        n.vx = 0;
        n.vy = 0;
        if (!state.animated) draw();
        return;
      }
      const idx = nearestNode(x, y);
      if (idx !== hoverRef.current) {
        hoverRef.current = idx;
        if (!state.animated) draw();
      }
    }

    function onPointerUp(ev: PointerEvent) {
      const { x, y } = toLocal(ev);
      const wasDrag = dragRef.current;
      dragRef.current = null;
      canvas!.releasePointerCapture?.(ev.pointerId);
      downPos = null;
      if (wasDrag !== null && movedFar) return; // fue un drag real
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
        const state = stateRef.current;
        if (state && !state.animated) draw();
      }
    }

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerLeave);

    // Resize → re-inicializar layout.
    const ro = new ResizeObserver(() => {
      const size = sizeCanvas();
      w = size.w;
      h = size.h;
      stateRef.current = initLayout(graph, w, h, Boolean(reducedMotion));
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
      </div>
      <div className={styles.canvasBox} ref={boxRef}>
        {nodeCount === 0 ? (
          <div className={styles.empty}>
            El grafo no tiene nodos todavía. Verificá que haya documentación en la
            fuente seleccionada.
          </div>
        ) : (
          <canvas ref={canvasRef} className={styles.canvas} />
        )}
      </div>
    </div>
  );
}
