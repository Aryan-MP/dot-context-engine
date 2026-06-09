import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphEdge, GraphNode } from "../api";

interface Position {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

const COLORS: Record<string, string> = {
  python: "#60a5fa",
  typescript: "#34d399",
  javascript: "#fbbf24",
  tsx: "#34d399",
  markdown: "#a78bfa",
};

/**
 * Small self-contained force-directed layout (repulsion + spring + center
 * gravity), animated with rAF. Good to a few hundred nodes, zero deps.
 */
export default function ForceGraph({
  nodes,
  edges,
  width = 900,
  height = 600,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  width?: number;
  height?: number;
}) {
  const internalEdges = useMemo(() => edges.filter((edge) => edge.internal), [edges]);
  const [positions, setPositions] = useState<Map<string, Position>>(new Map());
  const [hovered, setHovered] = useState<string | null>(null);
  const frame = useRef(0);

  useEffect(() => {
    const layout = new Map<string, Position>();
    nodes.forEach((node, index) => {
      const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
      layout.set(node.id, {
        x: width / 2 + Math.cos(angle) * width * 0.3,
        y: height / 2 + Math.sin(angle) * height * 0.3,
        vx: 0,
        vy: 0,
      });
    });

    let ticks = 0;
    const tick = () => {
      ticks += 1;
      const entries = [...layout.entries()];
      // pairwise repulsion
      for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
          const [, a] = entries[i];
          const [, b] = entries[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distSq = Math.max(dx * dx + dy * dy, 25);
          const force = 2500 / distSq;
          const dist = Math.sqrt(distSq);
          a.vx += (dx / dist) * force;
          a.vy += (dy / dist) * force;
          b.vx -= (dx / dist) * force;
          b.vy -= (dy / dist) * force;
        }
      }
      // springs along edges
      for (const edge of internalEdges) {
        const a = layout.get(edge.source);
        const b = layout.get(edge.target);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const force = (dist - 120) * 0.01;
        a.vx += (dx / dist) * force;
        a.vy += (dy / dist) * force;
        b.vx -= (dx / dist) * force;
        b.vy -= (dy / dist) * force;
      }
      // gravity toward center + integrate
      for (const [, p] of entries) {
        p.vx += (width / 2 - p.x) * 0.002;
        p.vy += (height / 2 - p.y) * 0.002;
        p.vx *= 0.85;
        p.vy *= 0.85;
        p.x = Math.min(width - 20, Math.max(20, p.x + p.vx));
        p.y = Math.min(height - 20, Math.max(20, p.y + p.vy));
      }
      setPositions(new Map([...layout.entries()].map(([k, v]) => [k, { ...v }])));
      if (ticks < 150) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [nodes, internalEdges, width, height]);

  const radius = (node: GraphNode) => Math.min(14, 4 + Math.log1p(node.edit_count) * 3);

  return (
    <svg width={width} height={height} className="rounded-xl border border-zinc-800 bg-zinc-900/40">
      {internalEdges.map((edge, index) => {
        const a = positions.get(edge.source);
        const b = positions.get(edge.target);
        if (!a || !b) return null;
        const active = hovered === edge.source || hovered === edge.target;
        return (
          <line
            key={index}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={active ? "#34d399" : "#3f3f46"}
            strokeWidth={active ? 1.5 : 0.7}
          />
        );
      })}
      {nodes.map((node) => {
        const p = positions.get(node.id);
        if (!p) return null;
        return (
          <g
            key={node.id}
            onMouseEnter={() => setHovered(node.id)}
            onMouseLeave={() => setHovered(null)}
          >
            <circle
              cx={p.x}
              cy={p.y}
              r={radius(node)}
              fill={COLORS[node.language] ?? "#71717a"}
              opacity={hovered && hovered !== node.id ? 0.4 : 0.9}
            />
            {(hovered === node.id || nodes.length <= 30) && (
              <text x={p.x + radius(node) + 4} y={p.y + 4} fontSize="10" fill="#d4d4d8">
                {node.id}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
