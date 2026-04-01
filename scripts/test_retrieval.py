"""
5 retrieval test queries — verifies answers are coherent and sourced.
Runs directly against the retrieval.py pipeline (no server needed).
"""

import sys
from pathlib import Path

# Add backend to path so retrieval.py imports work
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from retrieval import hybrid_retrieve, generate_answer, answer_query

PASS = 0
FAIL = 0
RESULTS = []


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    symbol = "v" if condition else "X"
    status = "PASS" if condition else "FAIL"
    print(f"    [{symbol}] {label}")
    if detail:
        print(f"         {detail}")
    if condition:
        PASS += 1
    else:
        FAIL += 1
    return condition


def run_query(question: str, top_k: int = 5, max_hops: int = 2) -> dict:
    result = answer_query(question, top_k=top_k, max_hops=max_hops)
    return result


def print_result(result: dict):
    print(f"    Answer ({len(result['answer'])} chars):")
    # Print first 300 chars of answer
    preview = result["answer"][:300].replace("\n", " ")
    print(f"      \"{preview}...\"" if len(result["answer"]) > 300 else f"      \"{preview}\"")
    print(f"    Confidence: {round(result['overall_confidence'] * 100)}%")
    print(f"    Cited nodes ({len(result['cited_nodes'])}):")
    for n in result["cited_nodes"][:6]:
        stale = " [STALE]" if n.get("is_stale") else ""
        method = n.get("retrieval_method", "?")
        edge = f" via {n['edge_type']}" if n.get("edge_type") else ""
        print(f"      - {n['label']:<35} decay={n['decay_score']:.3f}{stale}  [{method}{edge}]")


# ─────────────────────────────────────────────────────────────────────────────
# Q1: Technology comparison — should reconstruct decision thread
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("Q1: Why did we choose pgBouncer over RDS Proxy?")
print("=" * 65)
print("  Expected: decision thread across ADR-004, Slack, PR #142, postmortem")

r1 = run_query("Why did we choose pgBouncer over RDS Proxy?")
print_result(r1)

cited_ids = {n["id"] for n in r1["cited_nodes"]}
cited_labels = {n["label"].lower() for n in r1["cited_nodes"]}

check("Answer mentions pgBouncer",
      any("pgbouncer" in l for l in cited_labels) or "pgbouncer" in r1["answer"].lower())
check("Answer mentions RDS Proxy",
      any("rds" in l for l in cited_labels) or "rds" in r1["answer"].lower())
check("ADR-004 cited",
      "ADR-004" in cited_ids or "adr-004" in r1["answer"].lower())
check("Multiple sources cited (decision thread)",
      len(r1["cited_nodes"]) >= 3,
      f"got {len(r1['cited_nodes'])} cited nodes")
check("Answer has rationale (not just one doc)",
      len(r1["answer"]) > 150,
      f"answer length: {len(r1['answer'])} chars")
check("Confidence score present",
      r1["overall_confidence"] > 0)


# ─────────────────────────────────────────────────────────────────────────────
# Q2: Person + project context — should return person with decision nodes
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("Q2: Who has the most context about billing-service?")
print("=" * 65)
print("  Expected: Alice Chen with connected ADR/PR decision nodes")

r2 = run_query("Who has the most context about billing-service?")
print_result(r2)

cited_ids2 = {n["id"] for n in r2["cited_nodes"]}
cited_labels2 = {n["label"].lower() for n in r2["cited_nodes"]}

check("Alice Chen cited",
      "alice.chen" in cited_ids2 or "alice" in r2["answer"].lower())
check("billing-service cited",
      "billing-service" in cited_ids2 or "billing" in r2["answer"].lower())
check("At least one decision node cited (ADR or PR)",
      any(n["type"] == "DECISION" for n in r2["cited_nodes"]),
      f"decision nodes: {[n['id'] for n in r2['cited_nodes'] if n['type'] == 'DECISION']}")
check("Graph traversal expanded beyond seed nodes",
      any(n.get("retrieval_method") == "graph_traversal" for n in r2["cited_nodes"]),
      "at least one node found via graph traversal")
check("Answer mentions ownership or context",
      any(w in r2["answer"].lower() for w in ["own", "context", "knowledge", "author", "created"]))


# ─────────────────────────────────────────────────────────────────────────────
# Q3: Knowledge decay — should return low-confidence nodes
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("Q3: What decisions are at risk because of knowledge decay?")
print("=" * 65)
print("  Expected: nodes with low decay scores, stale flags")

r3 = run_query("What decisions are at risk because of knowledge decay?")
print_result(r3)

stale_nodes = [n for n in r3["cited_nodes"] if n.get("is_stale")]
low_decay = [n for n in r3["cited_nodes"] if n.get("decay_score", 1.0) < 0.5]

check("At least one stale node cited",
      len(stale_nodes) > 0,
      f"stale nodes: {[n['id'] for n in stale_nodes]}")
check("At least one low-decay node (< 0.5)",
      len(low_decay) > 0,
      f"low decay: {[(n['id'], n['decay_score']) for n in low_decay]}")
check("Answer mentions decay or risk or stale",
      any(w in r3["answer"].lower() for w in ["decay", "stale", "risk", "old", "confidence", "outdated"]))
check("Confidence score reflects stale sources",
      r3["overall_confidence"] < 0.7,
      f"confidence={r3['overall_confidence']:.3f} (should be < 0.7 for stale content)")


# ─────────────────────────────────────────────────────────────────────────────
# Q4: Current status — should surface superseding node, not original
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("Q4: What is the current status of the v1 API?")
print("=" * 65)
print("  Expected: ADR-003 (supersedes v1), not just the original v1 API docs")

r4 = run_query("What is the current status of the v1 API?")
print_result(r4)

cited_ids4 = {n["id"] for n in r4["cited_nodes"]}
cited_labels4 = {n["label"].lower() for n in r4["cited_nodes"]}

check("ADR-003 cited (the superseding decision)",
      "ADR-003" in cited_ids4 or "adr-003" in r4["answer"].lower())
check("Answer mentions deprecation or sunset",
      any(w in r4["answer"].lower() for w in ["deprecat", "sunset", "v2", "supersed", "dead", "retired"]))
check("Answer is not just about v1 (mentions v2 or replacement)",
      any(w in r4["answer"].lower() for w in ["v2", "oauth", "jwt", "replacement", "new api"]))
check("api_versioning or ADR-003 in cited nodes",
      any(n["id"] in ("ADR-003", "api_versioning") for n in r4["cited_nodes"]))


# ─────────────────────────────────────────────────────────────────────────────
# Q5: Departure risk — tests knowledge transfer simulation
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("Q5: What did Alice Chen contribute before she left billing-service?")
print("=" * 65)
print("  Expected: Alice's decisions (ADR-001, ADR-002, ADR-004, PR #289) + risk flag")

r5 = run_query("What did Alice Chen contribute before she left billing-service?")
print_result(r5)

cited_ids5 = {n["id"] for n in r5["cited_nodes"]}
alice_decisions = [n for n in r5["cited_nodes"]
                   if n.get("edge_type") in ("MADE_BY", "OWNS", "PARTICIPATED_IN")
                   or n["id"] in ("ADR-001", "ADR-002", "ADR-004", "PR_#289")]

check("Alice Chen cited",
      "alice.chen" in cited_ids5 or "alice" in r5["answer"].lower())
check("At least 2 of Alice's decisions cited",
      len(alice_decisions) >= 2,
      f"Alice's decisions found: {[n['id'] for n in alice_decisions]}")
check("billing-service cited",
      "billing-service" in cited_ids5 or "billing" in r5["answer"].lower())
check("Answer mentions knowledge transfer or departure",
      any(w in r5["answer"].lower() for w in ["transfer", "left", "transition", "owner", "platform", "departure"]))
check("MADE_BY or OWNS edge traversed",
      any(n.get("edge_type") in ("MADE_BY", "OWNS", "PARTICIPATED_IN") for n in r5["cited_nodes"]),
      f"edge types: {list(set(n.get('edge_type','') for n in r5['cited_nodes']))}")


# ─────────────────────────────────────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────────────────────────────────────
total = PASS + FAIL
pct = round(PASS / total * 100) if total else 0

print("\n" + "=" * 65)
print(f"RETRIEVAL TEST RESULTS: {PASS}/{total} checks passed ({pct}%)")
print("=" * 65)

if FAIL == 0:
    print("All 5 queries: coherent answers with proper sourcing.")
else:
    print(f"{FAIL} checks failed — see details above.")
