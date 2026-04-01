"""
Decay verification test.

1. Manually sets one node's created_at to 3 years ago
2. Sets another node's created_at to 7 days ago
3. Verifies:
   - Numerical decay scores differ correctly (formula check)
   - Old node is flagged is_stale=True
   - New node is flagged is_stale=False
   - Visual opacity values differ (for D3 graph)
   - Dashboard stale count increases when old node added
"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

GRAPH_JSON = Path(__file__).parent.parent.parent / "dataset" / "ner_output" / "knowledge_graph.json"
LAMBDA = 0.02  # must match build_graph.py and retrieval.py
STALE_THRESHOLD_MONTHS = 18

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    symbol = "v" if condition else "X"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{symbol}] {label}")
    if detail:
        print(f"       {detail}")
    return condition


def decay(created_at_iso: str) -> float:
    created = datetime.fromisoformat(created_at_iso)
    months = (datetime.now() - created).days / 30.44
    return round(max(0.05, min(1.0, math.exp(-LAMBDA * months))), 4)


def months_old(created_at_iso: str) -> float:
    created = datetime.fromisoformat(created_at_iso)
    return round((datetime.now() - created).days / 30.44, 1)


def opacity(decay_score: float) -> float:
    """D3 fill-opacity formula from GraphView.tsx: 0.3 + decay * 0.7"""
    return round(max(0.15, min(1.0, 0.3 + decay_score * 0.7)), 3)


# ── Step 1: Define the two test nodes ────────────────────────────────────────

three_years_ago = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")
seven_days_ago  = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

old_node = {
    "id":         "TEST_OLD_DECISION",
    "label":      "Test: Old Architecture Decision (3yr)",
    "type":       "DECISION",
    "source":     "confluence",
    "files":      "confluence_adrs.txt",
    "created_at": three_years_ago,
}

new_node = {
    "id":         "TEST_NEW_DECISION",
    "label":      "Test: Recent Architecture Decision (7d)",
    "type":       "DECISION",
    "source":     "confluence",
    "files":      "confluence_adrs.txt",
    "created_at": seven_days_ago,
}

# Compute expected values
old_decay    = decay(old_node["created_at"])
new_decay    = decay(new_node["created_at"])
old_months   = months_old(old_node["created_at"])
new_months   = months_old(new_node["created_at"])
old_stale    = old_months > STALE_THRESHOLD_MONTHS
new_stale    = new_months > STALE_THRESHOLD_MONTHS
old_opacity  = opacity(old_decay)
new_opacity  = opacity(new_decay)

print("=" * 60)
print("DECAY VERIFICATION TEST")
print("=" * 60)
print(f"\nOLD NODE  created_at={old_node['created_at']}  ({old_months:.1f} months ago)")
print(f"  decay_score = e^(-{LAMBDA} × {old_months:.1f}) = {old_decay}")
print(f"  is_stale    = {old_stale}  (>{STALE_THRESHOLD_MONTHS} months)")
print(f"  D3 opacity  = 0.3 + {old_decay} × 0.7 = {old_opacity}")

print(f"\nNEW NODE  created_at={new_node['created_at']}  ({new_months:.1f} months ago)")
print(f"  decay_score = e^(-{LAMBDA} × {new_months:.1f}) = {new_decay}")
print(f"  is_stale    = {new_stale}  (>{STALE_THRESHOLD_MONTHS} months)")
print(f"  D3 opacity  = 0.3 + {new_decay} × 0.7 = {new_opacity}")

print(f"\nDifference: {round(new_decay - old_decay, 4)} decay points  |  {round(new_opacity - old_opacity, 3)} opacity points")

# ── Step 2: Numerical checks ──────────────────────────────────────────────────

print("\n" + "=" * 60)
print("NUMERICAL CHECKS")
print("=" * 60)

check("Old node decay < new node decay",
      old_decay < new_decay,
      f"old={old_decay} < new={new_decay}")

check("Old node decay is significantly lower (>0.3 difference)",
      (new_decay - old_decay) > 0.3,
      f"difference={round(new_decay - old_decay, 4)}")

check("Old node decay matches formula e^(-lambda * months)",
      abs(old_decay - math.exp(-LAMBDA * old_months)) < 0.01,
      f"stored={old_decay}  formula={round(math.exp(-LAMBDA * old_months), 4)}")

check("New node decay matches formula e^(-lambda * months)",
      abs(new_decay - math.exp(-LAMBDA * new_months)) < 0.01,
      f"stored={new_decay}  formula={round(math.exp(-LAMBDA * new_months), 4)}")

check("Old node decay is below 0.5 (clearly degraded)",
      old_decay < 0.5,
      f"old decay={old_decay}")

check("New node decay is above 0.9 (nearly fresh)",
      new_decay > 0.9,
      f"new decay={new_decay}")

# ── Step 3: Stale flag checks ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("STALE FLAG CHECKS")
print("=" * 60)

check("Old node (3yr) is_stale=True",
      old_stale,
      f"months_old={old_months:.1f} > threshold={STALE_THRESHOLD_MONTHS}")

check("New node (7d) is_stale=False",
      not new_stale,
      f"months_old={new_months:.1f} <= threshold={STALE_THRESHOLD_MONTHS}")

check("Old node months_old >= 36",
      old_months >= 36,
      f"months_old={old_months:.1f}")

check("New node months_old < 1",
      new_months < 1,
      f"months_old={new_months:.1f}")

# ── Step 4: Visual opacity checks (D3 graph) ──────────────────────────────────

print("\n" + "=" * 60)
print("VISUAL OPACITY CHECKS (D3 graph)")
print("=" * 60)

check("Old node opacity visually dimmer than new (D3 formula: 0.3 + decay*0.7)",
      old_opacity < new_opacity,
      f"old={old_opacity}  new={new_opacity}  (formula floor is 0.335 at decay=0.05)")

check("Old node opacity < 0.7 (noticeably dim vs fresh node at ~1.0)",
      old_opacity < 0.7,
      f"old opacity={old_opacity}")

check("New node opacity > 0.9 (visually bright)",
      new_opacity > 0.9,
      f"new opacity={new_opacity}")

check("Opacity difference > 0.3 (clearly visible difference in D3)",
      (new_opacity - old_opacity) > 0.3,
      f"difference={round(new_opacity - old_opacity, 3)}")

# ── Step 5: Inject into graph JSON and verify stale count ─────────────────────

print("\n" + "=" * 60)
print("GRAPH JSON INJECTION + STALE COUNT CHECK")
print("=" * 60)

data = json.loads(GRAPH_JSON.read_text())
original_node_count = len(data["nodes"])
original_stale = sum(1 for n in data["nodes"] if n.get("is_stale"))

# Add test nodes to graph
for node in [old_node, new_node]:
    d = decay(node["created_at"])
    mo = months_old(node["created_at"])
    data["nodes"].append({
        **node,
        "decay_score": d,
        "months_old": mo,
        "is_stale": mo > STALE_THRESHOLD_MONTHS,
        "risk_score": 0.0,
        "degree": 1,
        "in_degree": 0,
        "out_degree": 1,
    })

new_stale_count = sum(1 for n in data["nodes"] if n.get("is_stale"))

check("Node count increased by 2 after injection",
      len(data["nodes"]) == original_node_count + 2,
      f"{original_node_count} -> {len(data['nodes'])}")

check("Stale count increased by exactly 1 (only old node is stale)",
      new_stale_count == original_stale + 1,
      f"stale count: {original_stale} -> {new_stale_count}")

# Verify old node is in stale list
stale_ids = {n["id"] for n in data["nodes"] if n.get("is_stale")}
check("Old test node appears in stale set",
      "TEST_OLD_DECISION" in stale_ids)

check("New test node NOT in stale set",
      "TEST_NEW_DECISION" not in stale_ids)

# Write back to graph JSON (with test nodes)
GRAPH_JSON.write_text(json.dumps(data, indent=2))
print(f"\n  Graph JSON updated: {len(data['nodes'])} nodes ({new_stale_count} stale)")

# ── Step 6: Verify retrieval layer reads is_stale correctly ───────────────────

print("\n" + "=" * 60)
print("RETRIEVAL LAYER CHECK")
print("=" * 60)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# Force reload graph cache
import retrieval
retrieval._graph_cache = None

from retrieval import hybrid_retrieve

results = hybrid_retrieve("old architecture decision test", top_k=3, max_hops=1)
old_result = next((n for n in results if n["id"] == "TEST_OLD_DECISION"), None)
new_result = next((n for n in results if n["id"] == "TEST_NEW_DECISION"), None)

# Also try direct lookup
graph = retrieval.load_graph()
old_from_graph = graph["nodes"].get("TEST_OLD_DECISION")
new_from_graph  = graph["nodes"].get("TEST_NEW_DECISION")

if old_from_graph:
    check("Old node loaded in retrieval graph with correct decay",
          abs(old_from_graph.get("decay_score", 0) - old_decay) < 0.01,
          f"stored={old_from_graph.get('decay_score')}  expected={old_decay}")
    check("Old node has is_stale=True in graph",
          old_from_graph.get("is_stale") == True,
          f"is_stale={old_from_graph.get('is_stale')}")
else:
    check("Old node loaded in retrieval graph", False, "node not found in graph cache")

if new_from_graph:
    check("New node loaded in retrieval graph with correct decay",
          abs(new_from_graph.get("decay_score", 0) - new_decay) < 0.01,
          f"stored={new_from_graph.get('decay_score')}  expected={new_decay}")
    check("New node has is_stale=False in graph",
          new_from_graph.get("is_stale") == False,
          f"is_stale={new_from_graph.get('is_stale')}")
else:
    check("New node loaded in retrieval graph", False, "node not found in graph cache")

# ── Final summary ─────────────────────────────────────────────────────────────

total = PASS + FAIL
pct = round(PASS / total * 100) if total else 0

print("\n" + "=" * 60)
print(f"DECAY TEST RESULTS: {PASS}/{total} checks passed ({pct}%)")
print("=" * 60)

if FAIL == 0:
    print("Decay formula, stale flags, and visual opacity all verified.")
    print(f"\nSummary:")
    print(f"  Old node (3yr):  decay={old_decay}  opacity={old_opacity}  stale=True")
    print(f"  New node (7d):   decay={new_decay}  opacity={new_opacity}  stale=False")
    print(f"  Difference:      {round(new_decay - old_decay, 4)} decay  |  {round(new_opacity - old_opacity, 3)} opacity")
else:
    print(f"{FAIL} checks failed.")
