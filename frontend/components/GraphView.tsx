"use client";
import { useEffect, useRef, useState } from "react";
import { getGraphData, GraphData, GraphNode } from "@/lib/api";

const AUTHOR_LABELS: Record<string, string> = {
  "alice.chen": "Alice Chen",
  "bob.martinez": "Bob Martinez",
  "carol.singh": "Carol Singh",
  "david.kim": "David Kim",
  "priya.nair": "Priya Nair",
  "unknown": "Unknown",
};

export default function GraphView() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [data, setData] = useState<GraphData | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    getGraphData()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!data || !svgRef.current) return;
    renderGraph(data, svgRef.current, filter, setSelected);
  }, [data, filter]);

  const authors = data ? [...new Set(data.nodes.map(n => n.author_id))] : [];

  return (
    <div className="flex h-full">
      <div className="flex-1 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
            Loading knowledge graph...
          </div>
        )}

        {/* Filter bar */}
        <div className="absolute top-4 left-4 z-10 flex gap-2 flex-wrap">
          <button
            onClick={() => setFilter("all")}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${filter === "all" ? "bg-white text-black border-white" : "border-slate-600 text-slate-400 hover:border-slate-400"}`}
          >
            All
          </button>
          {authors.map(a => (
            <button
              key={a}
              onClick={() => setFilter(a)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${filter === a ? "bg-white text-black border-white" : "border-slate-600 text-slate-400 hover:border-slate-400"}`}
            >
              {AUTHOR_LABELS[a] || a}
            </button>
          ))}
        </div>

        <svg ref={svgRef} className="w-full h-full" style={{ minHeight: "500px" }} />
      </div>

      {/* Node detail panel */}
      {selected && (
        <div className="w-72 border-l border-slate-800 p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-white text-sm">{selected.title}</h3>
            <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-white">×</button>
          </div>
          <div className="space-y-3 text-xs">
            <div>
              <p className="text-slate-500">Owner</p>
              <p className="text-slate-200">{selected.author_id}</p>
            </div>
            <div>
              <p className="text-slate-500">Source</p>
              <p className="text-slate-200">{selected.source_system}</p>
            </div>
            <div>
              <p className="text-slate-500">Knowledge Freshness</p>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 bg-slate-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${selected.decay_score > 0.7 ? "bg-green-500" : selected.decay_score > 0.4 ? "bg-yellow-500" : "bg-red-500"}`}
                    style={{ width: `${selected.decay_score * 100}%` }}
                  />
                </div>
                <span className={selected.decay_score > 0.7 ? "text-green-400" : selected.decay_score > 0.4 ? "text-yellow-400" : "text-red-400"}>
                  {Math.round(selected.decay_score * 100)}%
                </span>
              </div>
              {selected.decay_score < 0.4 && (
                <p className="text-orange-400 mt-1">⚠ Older than 18 months — verify accuracy</p>
              )}
            </div>
            {selected.description && (
              <div>
                <p className="text-slate-500">Description</p>
                <p className="text-slate-300 leading-relaxed">{selected.description}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function renderGraph(
  data: GraphData,
  svg: SVGSVGElement,
  filter: string,
  onSelect: (n: GraphNode) => void
) {
  // Dynamic import D3 to avoid SSR issues
  import("d3").then((d3) => {
    const width = svg.clientWidth || svg.getBoundingClientRect().width || 900;
    const height = svg.clientHeight || svg.getBoundingClientRect().height || 600;

    d3.select(svg).selectAll("*").remove();

    const filteredNodes = filter === "all" ? data.nodes : data.nodes.filter(n => n.author_id === filter);
    const filteredIds = new Set(filteredNodes.map(n => n.id));
    const filteredEdges = data.edges.filter(e => {
      const src = typeof e.source === "object" ? (e.source as any).id : e.source;
      const tgt = typeof e.target === "object" ? (e.target as any).id : e.target;
      return filteredIds.has(src) && filteredIds.has(tgt);
    });

    const svgEl = d3.select(svg)
      .attr("width", width)
      .attr("height", height);

    const g = svgEl.append("g");

    // Zoom
    svgEl.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on("zoom", (event) => g.attr("transform", event.transform))
    );

    const simulation = d3.forceSimulation(filteredNodes as any)
      .force("link", d3.forceLink(filteredEdges as any).id((d: any) => d.id).distance(80))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius((d: any) => d.size + 4));

    // Edges
    const link = g.append("g")
      .selectAll("line")
      .data(filteredEdges)
      .join("line")
      .attr("stroke", "#334155")
      .attr("stroke-width", 1)
      .attr("stroke-opacity", 0.6);

    // Nodes — opacity dims for stale nodes (decay < 0.4 = older than ~18 months)
    const node = g.append("g")
      .selectAll<SVGCircleElement, typeof filteredNodes[0]>("circle")
      .data(filteredNodes)
      .join("circle")
      .attr("r", (d) => d.size)
      .attr("fill", (d) => d.color)
      .attr("fill-opacity", (d) => {
        // Exponential decay: nodes with decay < 0.4 are visually dimmed
        const base = 0.3 + d.decay_score * 0.7;
        return Math.max(0.15, Math.min(1.0, base));
      })
      .attr("stroke", (d) => d.color)
      .attr("stroke-width", (d) => d.decay_score < 0.4 ? 0.5 : 1.5)
      .attr("stroke-dasharray", (d) => d.decay_score < 0.4 ? "3,2" : "none")
      .attr("cursor", "pointer")
      .on("click", (_, d) => onSelect(d))
      .call(
        d3.drag<SVGCircleElement, (typeof filteredNodes)[0]>()
          .on("start", (event, d: any) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag", (event, d: any) => { d.fx = event.x; d.fy = event.y; })
          .on("end", (event, d: any) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    // Labels
    const label = g.append("g")
      .selectAll("text")
      .data(filteredNodes)
      .join("text")
      .text((d) => d.title.length > 18 ? d.title.slice(0, 16) + "…" : d.title)
      .attr("font-size", "10px")
      .attr("fill", "#94a3b8")
      .attr("text-anchor", "middle")
      .attr("dy", (d) => d.size + 12)
      .attr("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
    });
  });
}
