"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { Core, ElementDefinition } from "cytoscape";
import { useStore } from "@/lib/store";

export interface CanvasEdge {
  source: string;
  target: string;
  type: string;
  aid: string;
  kind: "normal" | "disputed" | "stale" | "added" | "removed";
  label?: string;
  id?: string;
}

export interface GraphHandle {
  fit: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  relayout: () => void;
  center: (id: string) => void;
  /** Ease back to the focused path (the recenter button). */
  focusPath: () => void;
}

const FOCUS_PAD = 120;
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Node encoding (DESIGN.md §3.2): shape by type, a restrained neutral/accent ramp, one legend. */
// Phosphor entity colours, as theme tokens: systems and projects teal, teams and people violet, records grey
export const NODE_STYLE: Record<string, { colour: string; shape: string; size: number }> = {
  Team: { colour: "--entity-person", shape: "round-rectangle", size: 26 },
  System: { colour: "--entity-system", shape: "diamond", size: 20 },
  Project: { colour: "--entity-system", shape: "round-rectangle", size: 18 },
  Person: { colour: "--entity-person", shape: "ellipse", size: 14 },
  Decision: { colour: "--entity-record", shape: "triangle", size: 18 },
  Ticket: { colour: "--entity-record", shape: "ellipse", size: 10 },
};

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

const GraphCanvas = forwardRef<GraphHandle, {
  nodes: { id: string; name: string; labels: string[] }[];
  edges: CanvasEdge[];
  selected?: string[];
  onNode?: (id: string, additive: boolean) => void;
  onEdge?: (e: CanvasEdge) => void;
  onBackground?: () => void;
  layout?: "cose" | "concentric" | "breadthfirst";
  onReady?: () => void;
  /** a small neighbourhood (Explore) shouldn't zoom in until labels fill the canvas */
  maxZoom?: number;
  /** Path focus ("Open in Graph" from evidence): the path's node ids in step order. The rest dims. */
  focus?: string[] | null;
  /** The path left the view or the zoom drifted from the focus zoom (shows the recenter button). */
  onDrift?: (drifted: boolean) => void;
  /** Pixels on the left that an overlay (the path card) covers: the path fits beside it. */
  focusInset?: number;
  /** The relation of each step to the one before (OWNS, LEADS…): only that edge between a pair is the path's. */
  focusRels?: string[];
}>(function GraphCanvas({ nodes, edges, selected = [], onNode, onEdge, onBackground, layout = "cose", onReady, maxZoom = 3, focus = null, onDrift, focusInset = 0, focusRels = [] }, ref) {
  const { theme } = useStore();   // colours come from theme tokens, so a theme switch redraws
  const el = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const handlers = useRef({ onNode, onEdge, onBackground, onReady, onDrift });
  handlers.current = { onNode, onEdge, onBackground, onReady, onDrift };
  const focusRef = useRef(focus);
  focusRef.current = focus;
  const focusZoom = useRef(0);
  const inset = useRef(focusInset);
  inset.current = focusInset;
  const rels = useRef(focusRels);
  rels.current = focusRels;
  const moved = useRef(false);   // the user panned or zoomed since the last focus
  const positions = useRef<Map<string, { x: number; y: number }>>(new Map());

  useImperativeHandle(ref, () => ({
    fit: () => cyRef.current?.animate({ fit: { eles: cyRef.current.elements(), padding: 40 }, duration: 200 }),
    zoomIn: () => cyRef.current?.zoom({ level: cyRef.current.zoom() * 1.25, renderedPosition: { x: (el.current?.clientWidth || 0) / 2, y: (el.current?.clientHeight || 0) / 2 } }),
    zoomOut: () => cyRef.current?.zoom({ level: cyRef.current.zoom() / 1.25, renderedPosition: { x: (el.current?.clientWidth || 0) / 2, y: (el.current?.clientHeight || 0) / 2 } }),
    relayout: () => {
      const cy = cyRef.current;
      if (!cy) return;
      positions.current.clear();
      cy.one("layoutstop", () => focusOn(cy, focusRef.current, focusZoom, inset.current, rels.current, moved));   // the layout first, then the focus
      cy.layout(layoutOptions(layout)).run();
    },
    center: (id: string) => { const n = cyRef.current?.getElementById(id); if (n && n.length) cyRef.current?.animate({ center: { eles: n }, zoom: Math.max(cyRef.current.zoom(), 1.2), duration: 200 }); },
    focusPath: () => { if (cyRef.current) focusOn(cyRef.current, focusRef.current, focusZoom, inset.current, rels.current, moved); },
  }));

  // build or rebuild when the data changes; keep positions of nodes that stay (the time slider redraws in place)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const cytoscape = (await import("cytoscape")).default;
      if (cancelled || !el.current) return;
      const ids = new Set(nodes.map((n) => n.id));
      const els: ElementDefinition[] = [
        ...nodes.map((n) => {
          const lab = n.labels.find((l) => l !== "Entity") || "Entity";
          const st = NODE_STYLE[lab] || NODE_STYLE.Person;
          const pos = positions.current.get(n.id);
          return {
            data: { id: n.id, label: n.name, colour: cssVar(st.colour, "#888"), shape: st.shape, size: st.size, type: lab },
            ...(pos ? { position: { ...pos } } : {}),
          };
        }),
        ...edges
          .filter((e) => ids.has(e.source) && ids.has(e.target))
          .map((e, i) => ({
            data: { id: e.id || `${e.kind}-${e.aid || i}-${e.source}-${e.target}-${e.type}`, source: e.source, target: e.target, label: e.label || e.type.toLowerCase().replace(/_/g, " "), raw: e },
            classes: e.kind,
          })),
      ];
      const fg = cssVar("--text", "#0f172a");
      const muted = cssVar("--text-3", "#64748b");
      const line = cssVar("--border-strong", "#cbd5e1");
      const bg = cssVar("--surface", "#fff");
      const disputed = cssVar("--error-600", "#dc2626");
      const stale = cssVar("--warning-600", "#d97706");
      const added = cssVar("--success-600", "#16a34a");
      const accent = cssVar("--accent-600", "#4f46e5");
      const lime = cssVar("--primary-text", "#C4F25A");
      cyRef.current?.destroy();
      const allPositioned = nodes.length > 0 && nodes.every((n) => positions.current.has(n.id));
      const cy = cytoscape({
        container: el.current,
        elements: els,
        wheelSensitivity: 0.25,
        minZoom: 0.15,
        maxZoom,
        style: [
          {
            selector: "node",
            style: {
              "background-color": "data(colour)", shape: "data(shape)" as "ellipse", width: "data(size)", height: "data(size)",
              label: "data(label)", color: fg, "font-size": 10, "font-family": cssVar("--font", "Geist, system-ui"),
              "text-valign": "bottom", "text-margin-y": 4, "text-outline-color": bg, "text-outline-width": 2,
              "border-width": 1.5, "border-color": bg,
              // m9: labels drop out when zoomed far out instead of piling up, and long names are cut short
              "min-zoomed-font-size": 8, "text-wrap": "ellipsis", "text-max-width": "110px",
            },
          },
          { selector: "node[type = 'Ticket']", style: { "font-size": 8, color: muted } },
          { selector: "node.hov", style: { "font-size": 14, "z-index": 20, "text-max-width": "240px", "min-zoomed-font-size": 0, "text-outline-width": 3 } },
          { selector: "node.sel", style: { "border-width": 3, "border-color": accent, "overlay-color": accent, "overlay-opacity": 0.12, "overlay-padding": 6 } },
          {
            selector: "edge",
            style: {
              width: 1.2, "line-color": line, "target-arrow-color": line, "target-arrow-shape": "triangle", "arrow-scale": 0.6,
              "curve-style": "bezier", label: "data(label)", "font-size": 7, color: muted, "text-rotation": "autorotate",
              "text-outline-color": bg, "text-outline-width": 2, "text-opacity": 0,
            },
          },
          { selector: "edge:selected, edge.hl", style: { "text-opacity": 1 } },
          { selector: "edge.disputed", style: { "line-color": disputed, "target-arrow-color": disputed, width: 2.2, color: disputed, "text-opacity": 1, "line-style": "solid" } },
          { selector: "edge.stale", style: { "line-color": stale, "target-arrow-color": stale, width: 1.8, "line-style": "dashed", color: stale, "text-opacity": 1 } },
          { selector: "edge.added", style: { "line-color": added, "target-arrow-color": added, width: 2.6, "text-opacity": 1, color: added } },
          { selector: "edge.removed", style: { "line-style": "dashed", opacity: 0.35, width: 1.6 } },
          { selector: "edge:selected", style: { width: 3, "line-color": accent, "target-arrow-color": accent } },
          { selector: "node:selected", style: { "border-width": 3, "border-color": accent } },
          // path focus: the path at full strength, everything else faint and unlabelled until hovered or zoomed out
          { selector: ".dim", style: { opacity: 0.15, "text-opacity": 0 } },
          { selector: ".dim.wide", style: { opacity: 0.45 } },
          { selector: "edge.dim.near", style: { opacity: 0.6 } },
          { selector: "node.dim.hov", style: { "text-opacity": 1, opacity: 0.8 } },
          { selector: "node.path", style: { "border-width": 2, "border-color": lime, "z-index": 30, "font-size": 12, "min-zoomed-font-size": 0 } },
          { selector: "edge.path", style: { width: 2.5, "line-color": lime, "target-arrow-color": lime, "line-style": "dashed", "line-dash-pattern": [7, 4], color: lime, "text-opacity": 1, "font-size": 9, "z-index": 30 } },
        ],
        layout: allPositioned ? { name: "preset" } : layoutOptions(layout),
      });
      cy.on("tap", "node", (ev) => {
        const oe = ev.originalEvent as MouseEvent | undefined;
        handlers.current.onNode?.(ev.target.id(), !!(oe && (oe.shiftKey || oe.metaKey || oe.ctrlKey)));
      });
      cy.on("tap", "edge", (ev) => handlers.current.onEdge?.(ev.target.data("raw") as CanvasEdge));
      cy.on("tap", (ev) => { if (ev.target === cy) handlers.current.onBackground?.(); });
      cy.on("mouseover", "edge", (ev) => ev.target.addClass("hl"));
      cy.on("mouseover", "node", (ev) => ev.target.addClass("hov"));
      cy.on("mouseout", "node", (ev) => ev.target.removeClass("hov"));
      cy.on("mouseout", "edge", (ev) => ev.target.removeClass("hl"));
      cy.on("position", "node", (ev) => { positions.current.set(ev.target.id(), { ...ev.target.position() }); });
      cy.nodes().forEach((n) => { positions.current.set(n.id(), { ...n.position() }); });
      let drifted = false;
      cy.on("scrollzoom tapstart", () => { moved.current = true; });
      cy.on("viewport", () => {
        const f = focusRef.current;
        if (!f?.length || !focusZoom.current) return;
        const ratio = cy.zoom() / focusZoom.current;
        cy.batch(() => cy.elements(".dim").toggleClass("wide", ratio < 0.6));
        const box = cy.nodes(".path").renderedBoundingBox();
        const off = box.x1 < 0 || box.y1 < 0 || box.x2 > cy.width() || box.y2 > cy.height() || ratio < 0.6 || ratio > 1.6;
        if (off !== drifted) { drifted = off; handlers.current.onDrift?.(off); }
      });
      cyRef.current = cy;
      applySelection(cy, selected);
      focusOn(cy, focusRef.current, focusZoom, inset.current, rels.current, moved);
      handlers.current.onReady?.();
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, layout, theme, maxZoom]);

  useEffect(() => { if (cyRef.current) applySelection(cyRef.current, selected); }, [selected]);
  useEffect(() => { if (cyRef.current) focusOn(cyRef.current, focus, focusZoom, inset.current, rels.current, moved); }, [focus]);
  // the path's flowing dash (design system), off with reduced motion
  useEffect(() => {
    if (!focus?.length || reducedMotion()) return;
    let raf = 0;
    let off = 0;
    const tick = () => {
      off = (off + 0.4) % 11;
      cyRef.current?.edges(".path").style("line-dash-offset", -off);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [focus]);
  useEffect(() => () => cyRef.current?.destroy(), []);
  // the canvas changes size after the first fit (the rail collapses on entering the graph): refit the path
  // unless the user has moved the view since
  useEffect(() => {
    if (!el.current) return;
    const ro = new ResizeObserver(() => {
      const cy = cyRef.current;
      if (!cy) return;
      cy.resize();
      if (focusRef.current?.length && !moved.current) focusOn(cy, focusRef.current, focusZoom, inset.current, rels.current, moved);
    });
    ro.observe(el.current);
    return () => ro.disconnect();
  }, []);

  return <div ref={el} className="cy" />;
});

export default GraphCanvas;

function layoutOptions(layout: "cose" | "concentric" | "breadthfirst"): cytoscape.LayoutOptions {
  if (layout === "cose") return { name: "cose", animate: false, nodeRepulsion: () => 12000, idealEdgeLength: () => 80, randomize: false, padding: 40 } as cytoscape.LayoutOptions;
  return { name: layout, padding: 40 } as cytoscape.LayoutOptions;
}

/** Mark the path (its nodes, and the edges between consecutive steps) and dim the rest, then ease to fit the
 * path alone. No path clears the focus and leaves the view where it is. */
function focusOn(cy: Core, path: string[] | null | undefined, zoomAt: { current: number }, insetLeft = 0,
  rels: string[] = [], moved?: { current: boolean }) {
  if (moved) moved.current = false;
  cy.batch(() => {
    cy.elements().removeClass("dim wide near path");
    if (!path?.length) return;
    const ids = new Set(path);
    const nodes = cy.nodes().filter((n) => ids.has(n.id()));
    const pairs = new Map(path.slice(1).map((b, i) => [[path[i], b].sort().join("|"), rels[i] || ""]));
    const onPath = cy.edges().filter((e) => {
      const rel = pairs.get([e.source().id(), e.target().id()].sort().join("|"));
      return rel !== undefined && !e.hasClass("disputed") && !e.hasClass("stale") && (!rel || (e.data("raw") as CanvasEdge).type === rel);
    });
    cy.elements().not(nodes).not(onPath).addClass("dim");
    nodes.addClass("path");
    onPath.addClass("path");
    nodes.connectedEdges(".disputed, .stale").addClass("near");
  });
  if (!path?.length) { zoomAt.current = 0; return; }
  spreadPath(cy, path);
  const eles = cy.nodes(".path");
  if (!eles.length) return;
  // fit the path into the area beside the overlay (at most 40% of the width is given up to it)
  const left = Math.min(insetLeft, cy.width() * 0.4);
  const bb = eles.boundingBox();
  const w = Math.max(cy.width() - left - 2 * FOCUS_PAD, 80);
  const h = Math.max(cy.height() - 2 * FOCUS_PAD, 80);
  const zoom = Math.min(cy.maxZoom(), Math.max(cy.minZoom(), Math.min(w / Math.max(bb.w, 1), h / Math.max(bb.h, 1))));
  const pan = { x: left + FOCUS_PAD + w / 2 - zoom * (bb.x1 + bb.w / 2), y: FOCUS_PAD + h / 2 - zoom * (bb.y1 + bb.h / 2) };
  const done = () => { zoomAt.current = cy.zoom(); cy.emit("viewport"); };
  cy.stop();   // a refit replaces a fit still running
  if (reducedMotion()) { cy.viewport({ zoom, pan }); done(); return; }
  cy.animate({ zoom, pan, duration: 500, easing: "ease-out-cubic", complete: done });
}

/** Path nodes the layout left on top of each other move apart (later from earlier along their line), so every
 * step and its label reads; nothing off the path moves. */
function spreadPath(cy: Core, path: string[]) {
  const MIN = 70;
  const nodes = path.map((id) => cy.getElementById(id)).filter((n) => n.length);
  nodes.forEach((n, i) => nodes.slice(0, i).forEach((m) => {
    const a = m.position();
    const b = n.position();
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.hypot(dx, dy);
    if (d >= MIN) return;
    const [ux, uy] = d ? [dx / d, dy / d] : [1, 0];
    n.position({ x: a.x + ux * MIN, y: a.y + uy * MIN });
  }));
}

function applySelection(cy: Core, selected: string[]) {
  cy.nodes().removeClass("sel");
  selected.forEach((id) => cy.getElementById(id).addClass("sel"));
}
