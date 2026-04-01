"""Graph router — serves knowledge graph for D3 visualization. No DB."""

from fastapi import APIRouter
from pydantic import BaseModel

import store

router = APIRouter()

AUTHOR_COLORS = {
    "alice.chen":   "#EF4444",
    "bob.martinez": "#3B82F6",
    "carol.singh":  "#10B981",
    "david.kim":    "#F59E0B",
    "priya.nair":   "#8B5CF6",
    "unknown":      "#6B7280",
}


class GraphNode(BaseModel):
    id: str
    title: str
    description: str | None
    source_system: str
    author_id: str
    decay_score: float
    community_id: str | None
    color: str
    size: int


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str | None
    weight: float


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_nodes: int
    total_edges: int


@router.get("", response_model=GraphData)
def get_graph(limit: int = 80):
    raw_nodes = sorted(store.get_nodes(), key=lambda n: n.get("degree", 0), reverse=True)[:limit]
    node_ids = {n["id"] for n in raw_nodes}

    nodes = []
    for n in raw_nodes:
        author = n.get("author") or store.resolve_author(n["id"])
        nodes.append(GraphNode(
            id=n["id"],
            title=n.get("label", n["id"]),
            description=n.get("rationale"),
            source_system=n.get("source", "unknown"),
            author_id=author,
            decay_score=n.get("decay_score", 0.75),
            community_id=n.get("type"),
            color=AUTHOR_COLORS.get(author, "#6B7280"),
            size=max(8, min(30, n.get("degree", 1) * 3)),
        ))

    seen: set[tuple] = set()
    edges = []
    for e in store.get_edges():
        src, tgt = e["source"], e["target"]
        if src not in node_ids or tgt not in node_ids:
            continue
        key = (min(src, tgt), max(src, tgt))
        if key in seen:
            continue
        seen.add(key)
        edges.append(GraphEdge(
            source=src,
            target=tgt,
            label=e.get("type"),
            weight=e.get("weight", 1.0),
        ))

    return GraphData(nodes=nodes, edges=edges, total_nodes=len(nodes), total_edges=len(edges))
