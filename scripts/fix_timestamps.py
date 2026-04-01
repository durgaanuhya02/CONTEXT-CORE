"""Update node timestamps so ~15 nodes show healthy decay scores."""
import json
import math
from datetime import datetime
from pathlib import Path

GRAPH_JSON = Path(__file__).parent.parent.parent / "dataset" / "ner_output" / "knowledge_graph.json"
LAMBDA = 0.02

# Nodes that should be RECENT — actively maintained, recently validated
RECENT_DATES = {
    "redis":                   "2025-01-15",
    "recommendations-engine":  "2025-02-01",
    "kubernetes":              "2024-11-20",
    "linkerd":                 "2025-01-10",
    "single_point_of_failure": "2025-03-01",
    "knowledge_transfer":      "2025-02-15",
    "platform_team":           "2025-01-20",
    "ADR-007":                 "2024-12-01",
    "PR_#267":                 "2024-10-15",
    "PR_#289":                 "2024-09-01",
    "PR_#178":                 "2024-08-20",
    "launchdarkly":            "2024-11-01",
    "memcached":               "2024-07-01",
    "jwt":                     "2024-10-01",
    "oauth2":                  "2024-10-01",
}

g = json.loads(GRAPH_JSON.read_text())
now = datetime.now()
updated = 0

for node in g["nodes"]:
    nid = node["id"]
    if nid in RECENT_DATES:
        node["created_at"] = RECENT_DATES[nid]
        updated += 1
    # Recalculate decay_score from created_at
    try:
        created = datetime.fromisoformat(node["created_at"])
        months = (now - created).days / 30.44
        node["decay_score"] = round(max(0.05, min(1.0, math.exp(-LAMBDA * months))), 4)
        node["months_old"] = round(months, 1)
        node["is_stale"] = months > 18
    except Exception:
        pass

GRAPH_JSON.write_text(json.dumps(g, indent=2))
print(f"Updated {updated} timestamps, recalculated all decay scores")
print()

# Show distribution
fresh = sum(1 for n in g["nodes"] if not n.get("is_stale", True))
stale = sum(1 for n in g["nodes"] if n.get("is_stale", True))
print(f"Fresh nodes (<=18mo): {fresh}")
print(f"Stale nodes (>18mo):  {stale}")
print()
print("Top 10 freshest nodes:")
for n in sorted(g["nodes"], key=lambda x: x.get("decay_score", 0), reverse=True)[:10]:
    print(f"  {n['id']:<35} decay={n['decay_score']}  created={n['created_at']}")
print()
print("Bottom 5 stalest nodes:")
for n in sorted(g["nodes"], key=lambda x: x.get("decay_score", 1))[:5]:
    print(f"  {n['id']:<35} decay={n['decay_score']}  created={n['created_at']}")
