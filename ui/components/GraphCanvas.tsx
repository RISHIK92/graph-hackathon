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
}

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
}>(function GraphCanvas({ nodes, edges, selected = [], onNode, onEdge, onBackground, layout = "cose", onReady }, ref) {
  const { theme } = useStore();   // colours come from theme tokens, so a theme switch redraws
  const el = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const handlers = useRef({ onNode, onEdge, onBackground, onReady });
  handlers.current = { onNode, onEdge, onBackground, onReady };
  const positions = useRef<Map<string, { x: number; y: number }>>(new Map());

  useImperativeHandle(ref, () => ({
    fit: () => cyRef.current?.animate({ fit: { eles: cyRef.current.elements(), padding: 40 }, duration: 200 }),
    zoomIn: () => cyRef.current?.zoom({ level: cyRef.current.zoom() * 1.25, renderedPosition: { x: (el.current?.clientWidth || 0) / 2, y: (el.current?.clientHeight || 0) / 2 } }),
    zoomOut: () => cyRef.current?.zoom({ level: cyRef.current.zoom() / 1.25, renderedPosition: { x: (el.current?.clientWidth || 0) / 2, y: (el.current?.clientHeight || 0) / 2 } }),
    relayout: () => { positions.current.clear(); cyRef.current?.layout(layoutOptions(layout)).run(); },
    center: (id: string) => { const n = cyRef.current?.getElementById(id); if (n && n.length) cyRef.current?.animate({ center: { eles: n }, zoom: Math.max(cyRef.current.zoom(), 1.2), duration: 200 }); },
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
      cyRef.current?.destroy();
      const allPositioned = nodes.length > 0 && nodes.every((n) => positions.current.has(n.id));
      const cy = cytoscape({
        container: el.current,
        elements: els,
        wheelSensitivity: 0.25,
        minZoom: 0.15,
        maxZoom: 3,
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
      cyRef.current = cy;
      applySelection(cy, selected);
      handlers.current.onReady?.();
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, layout, theme]);

  useEffect(() => { if (cyRef.current) applySelection(cyRef.current, selected); }, [selected]);
  useEffect(() => () => cyRef.current?.destroy(), []);

  return <div ref={el} className="cy" />;
});

export default GraphCanvas;

function layoutOptions(layout: "cose" | "concentric" | "breadthfirst"): cytoscape.LayoutOptions {
  if (layout === "cose") return { name: "cose", animate: false, nodeRepulsion: () => 12000, idealEdgeLength: () => 80, randomize: false, padding: 40 } as cytoscape.LayoutOptions;
  return { name: layout, padding: 40 } as cytoscape.LayoutOptions;
}

function applySelection(cy: Core, selected: string[]) {
  cy.nodes().removeClass("sel");
  selected.forEach((id) => cy.getElementById(id).addClass("sel"));
}
