"""Quick status check of all 5 priorities."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

print("=" * 55)
print("CONTEXTCORE — BUILD STATUS")
print("=" * 55)

# 1. Dataset
files = list(Path("dataset/input").glob("*.txt"))
print(f"\n1. DATASET")
print(f"   Files: {len(files)}/5")
for f in files:
    print(f"   {f.name}: {len(f.read_text().splitlines())} lines")

# 2. Graph
g = json.loads(Path("dataset/ner_output/knowledge_graph.json").read_text())
nodes = g["nodes"]
edges = g["edges"]
orphans = [n for n in nodes if n.get("degree", 0) == 0]
has_ts = sum(1 for n in nodes if n.get("created_at"))
has_decay = sum(1 for n in nodes if n.get("decay_score") is not None)
has_stale = sum(1 for n in nodes if n.get("is_stale") is not None)
print(f"\n2. GRAPH CONSTRUCTION")
print(f"   Nodes: {len(nodes)}  Edges: {len(edges)}")
print(f"   Orphans: {len(orphans)}")
print(f"   Has created_at: {has_ts}/{len(nodes)}")
print(f"   Has decay_score: {has_decay}/{len(nodes)}")
print(f"   Has is_stale: {has_stale}/{len(nodes)}")
print(f"   Edge types: {list(g['stats']['edge_types'].keys())}")

# 3. Retrieval
from retrieval import hybrid_retrieve, generate_answer, OPENAI_API_KEY
result = generate_answer("test", hybrid_retrieve("pgbouncer", top_k=3))
print(f"\n3. HYBRID RETRIEVAL")
print(f"   OpenAI key: {'real' if OPENAI_API_KEY else 'missing (template fallback active)'}")
print(f"   Cited nodes on test query: {len(result['cited_nodes'])}")
print(f"   Confidence: {result['overall_confidence']}")
print(f"   Graph traversal working: {any(n.get('retrieval_method') == 'graph_traversal' for n in result['cited_nodes'])}")

# 4. Decay in UI
frontend_files = {
    "ChatPanel.tsx": "contextcore/frontend/components/ChatPanel.tsx",
    "GraphView.tsx": "contextcore/frontend/components/GraphView.tsx",
    "RiskDashboard.tsx": "contextcore/frontend/components/RiskDashboard.tsx",
}
print(f"\n4. CONFIDENCE DECAY IN UI")
for name, path in frontend_files.items():
    text = Path(path).read_text()
    has_decay_ui = "decay_score" in text
    has_stale_ui = "is_stale" in text or "stale" in text.lower()
    has_opacity = "opacity" in text or "fill-opacity" in text
    print(f"   {name}: decay={has_decay_ui} stale={has_stale_ui} opacity={has_opacity}")

# 5. Risk dashboard
risk_text = Path("contextcore/frontend/components/RiskDashboard.tsx").read_text()
print(f"\n5. RISK DASHBOARD")
print(f"   Health score: {'overall_score' in risk_text}")
print(f"   Owner risk cards: {'risk_score' in risk_text}")
print(f"   Transfer checklist: {'checklist' in risk_text}")
print(f"   Departure alert: {'departure' in risk_text.lower() or 'transfer' in risk_text.lower()}")
print(f"   Sole owner flag: {'sole_owner' in risk_text}")

# 6. Graph visualizer
graph_text = Path("contextcore/frontend/components/GraphView.tsx").read_text()
print(f"\n6. GRAPH VISUALIZER")
print(f"   D3 force graph: {'forceSimulation' in graph_text}")
print(f"   Node color by owner: {'author_id' in graph_text and 'color' in graph_text}")
print(f"   Decay opacity: {'decay_score' in graph_text and 'opacity' in graph_text}")
print(f"   Stale dashed border: {'stroke-dasharray' in graph_text}")
print(f"   Click detail panel: {'setSelected' in graph_text}")
print(f"   Filter by owner: {'setFilter' in graph_text}")

# Backend endpoints
print(f"\n7. BACKEND ENDPOINTS")
main_text = Path("contextcore/backend/main.py").read_text()
for ep in ["/query", "/risk", "/graph", "/audit-log", "/compliance"]:
    print(f"   {ep}: {'prefix=\"' + ep + '\"' in main_text or ep.strip('/') in main_text}")

print("\n" + "=" * 55)
