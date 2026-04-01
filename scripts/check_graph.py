"""
Graph verification — checks all nodes are created and edges are correctly typed.
Queries the NetworkX JSON output directly (no Neo4j needed).
"""

import json
from pathlib import Path

GRAPH_JSON = Path(__file__).parent.parent.parent / "dataset" / "ner_output" / "knowledge_graph.json"

# ── Expected nodes ────────────────────────────────────────────────────────────

EXPECTED_NODES = {
    # People
    "alice.chen":               "PERSON",
    "bob.martinez":             "PERSON",
    "carol.singh":              "PERSON",
    "david.kim":                "PERSON",
    "priya.nair":               "PERSON",
    # Decisions
    "ADR-001":                  "DECISION",
    "ADR-002":                  "DECISION",
    "ADR-003":                  "DECISION",
    "ADR-004":                  "DECISION",
    "ADR-007":                  "DECISION",
    "PR_#142":                  "DECISION",
    "PR_#178":                  "DECISION",
    "PR_#289":                  "DECISION",
    # Projects
    "billing-service":          "PROJECT",
    "notifications-service":    "PROJECT",
    "recommendations-engine":   "PROJECT",
    "monolith":                 "PROJECT",
    # Technologies
    "postgresql":               "TECHNOLOGY",
    "pgbouncer":                "TECHNOLOGY",
    "redis":                    "TECHNOLOGY",
    "mongodb":                  "TECHNOLOGY",
    "rds_proxy":                "TECHNOLOGY",
    "memcached":                "TECHNOLOGY",
    "kubernetes":               "TECHNOLOGY",
    "istio":                    "TECHNOLOGY",
    "sqs":                      "TECHNOLOGY",
    # Concepts
    "circuit_breaker":          "CONCEPT",
    "strangler_fig":            "CONCEPT",
    "acid_compliance":          "CONCEPT",
}

# ── Expected edges (src, tgt, type) ──────────────────────────────────────────

EXPECTED_EDGES = [
    # MADE_BY
    ("ADR-001",       "alice.chen",    "MADE_BY"),
    ("ADR-002",       "alice.chen",    "MADE_BY"),
    ("ADR-003",       "carol.singh",   "MADE_BY"),
    ("ADR-004",       "alice.chen",    "MADE_BY"),
    ("ADR-007",       "bob.martinez",  "MADE_BY"),
    ("PR_#142",       "david.kim",     "MADE_BY"),
    ("PR_#178",       "carol.singh",   "MADE_BY"),
    ("PR_#289",       "alice.chen",    "MADE_BY"),
    # OWNS
    ("alice.chen",    "billing-service",           "OWNS"),
    ("bob.martinez",  "billing-service",           "OWNS"),
    ("carol.singh",   "notifications-service",     "OWNS"),
    ("bob.martinez",  "recommendations-engine",    "OWNS"),
    ("david.kim",     "kubernetes",                "OWNS"),
    ("david.kim",     "istio",                     "OWNS"),
    # USES
    ("billing-service",         "postgresql",      "USES"),
    ("billing-service",         "pgbouncer",       "USES"),
    ("billing-service",         "circuit_breaker", "USES"),
    ("notifications-service",   "sqs",             "USES"),
    ("recommendations-engine",  "redis",           "USES"),
    ("kubernetes",              "istio",           "USES"),
    # SUPPORTS
    ("ADR-001",  "billing-service",           "SUPPORTS"),
    ("ADR-002",  "notifications-service",     "SUPPORTS"),
    ("ADR-004",  "billing-service",           "SUPPORTS"),
    ("ADR-007",  "recommendations-engine",    "SUPPORTS"),
    ("PR_#142",  "ADR-004",                   "SUPPORTS"),
    ("PR_#178",  "ADR-002",                   "SUPPORTS"),
    # CONTRADICTS
    ("ADR-001",  "mongodb",    "CONTRADICTS"),
    ("ADR-004",  "rds_proxy",  "CONTRADICTS"),
    ("ADR-007",  "memcached",  "CONTRADICTS"),
    # SUPERSEDES
    ("ADR-003",  "ADR-001",   "SUPERSEDES"),
    # DOCUMENTED_BY
    ("billing-service",  "PR_#289",  "DOCUMENTED_BY"),
    ("ADR-004",          "PR_#142",  "DOCUMENTED_BY"),
    ("circuit_breaker",  "PR_#289",  "DOCUMENTED_BY"),
    # PARTICIPATED_IN
    ("bob.martinez",  "ADR-001",  "PARTICIPATED_IN"),
    ("david.kim",     "ADR-001",  "PARTICIPATED_IN"),
    ("carol.singh",   "ADR-002",  "PARTICIPATED_IN"),
    ("priya.nair",    "ADR-002",  "PARTICIPATED_IN"),
    ("alice.chen",    "ADR-004",  "PARTICIPATED_IN"),
    ("david.kim",     "ADR-004",  "PARTICIPATED_IN"),
    ("priya.nair",    "ADR-004",  "PARTICIPATED_IN"),
    ("bob.martinez",  "ADR-007",  "PARTICIPATED_IN"),
    ("carol.singh",   "ADR-007",  "PARTICIPATED_IN"),
]

VALID_EDGE_TYPES = {
    "MADE_BY", "OWNS", "USES", "SUPPORTS",
    "CONTRADICTS", "SUPERSEDES", "DOCUMENTED_BY", "PARTICIPATED_IN",
    "RELATED_TO",
}


def run():
    if not GRAPH_JSON.exists():
        print(f"ERROR: {GRAPH_JSON} not found. Run build_graph.py first.")
        return

    data = json.loads(GRAPH_JSON.read_text())
    nodes = {n["id"]: n for n in data["nodes"]}
    edges = data["edges"]
    stats = data["stats"]

    pass_count = 0
    fail_count = 0
    failures = []

    # ── 1. Node existence check ───────────────────────────────────────────────
    print("=" * 60)
    print("1. NODE EXISTENCE CHECK")
    print("=" * 60)

    for node_id, expected_type in EXPECTED_NODES.items():
        if node_id in nodes:
            actual_type = nodes[node_id].get("type", "UNKNOWN")
            if actual_type == expected_type:
                pass_count += 1
                print(f"  [v] {node_id:<35} type={actual_type}")
            else:
                fail_count += 1
                msg = f"{node_id} — type mismatch: expected={expected_type} actual={actual_type}"
                failures.append(msg)
                print(f"  [!] {msg}")
        else:
            fail_count += 1
            msg = f"{node_id} — NODE MISSING"
            failures.append(msg)
            print(f"  [X] {msg}")

    # ── 2. Edge existence + type check ───────────────────────────────────────
    print()
    print("=" * 60)
    print("2. EDGE EXISTENCE + TYPE CHECK")
    print("=" * 60)

    # Build edge lookup: (src, tgt) → edge_type (directed only, no reverse)
    edge_lookup: dict[tuple[str, str], str] = {}
    for e in edges:
        edge_lookup[(e["source"], e["target"])] = e.get("type", "UNKNOWN")

    for src, tgt, expected_type in EXPECTED_EDGES:
        key = (src, tgt)
        if key in edge_lookup:
            actual_type = edge_lookup[key]
            if actual_type == expected_type:
                pass_count += 1
                print(f"  [v] {src:<20} --{expected_type}--> {tgt}")
            else:
                fail_count += 1
                msg = f"{src} --?--> {tgt}: expected={expected_type} actual={actual_type}"
                failures.append(msg)
                print(f"  [!] {msg}")
        else:
            fail_count += 1
            msg = f"MISSING EDGE: {src} --{expected_type}--> {tgt}"
            failures.append(msg)
            print(f"  [X] {msg}")

    # ── 3. Edge type validity check ───────────────────────────────────────────
    print()
    print("=" * 60)
    print("3. EDGE TYPE VALIDITY (no unknown types)")
    print("=" * 60)

    invalid_types = set()
    for e in edges:
        etype = e.get("type", "UNKNOWN")
        if etype not in VALID_EDGE_TYPES:
            invalid_types.add(etype)

    if invalid_types:
        fail_count += len(invalid_types)
        for t in invalid_types:
            msg = f"Invalid edge type: {t}"
            failures.append(msg)
            print(f"  [X] {msg}")
    else:
        pass_count += 1
        print(f"  [v] All {len(edges)} edges use valid types: {sorted(VALID_EDGE_TYPES)}")

    # ── 4. Graph integrity checks ─────────────────────────────────────────────
    print()
    print("=" * 60)
    print("4. GRAPH INTEGRITY")
    print("=" * 60)

    # Check for orphan nodes (no edges)
    connected = set()
    for e in edges:
        connected.add(e["source"])
        connected.add(e["target"])
    orphans = [nid for nid in nodes if nid not in connected]

    if orphans:
        print(f"  [!] Orphan nodes (no edges): {orphans}")
    else:
        pass_count += 1
        print(f"  [v] No orphan nodes — all {len(nodes)} nodes are connected")

    # Check for self-loops
    self_loops = [(e["source"], e["target"]) for e in edges if e["source"] == e["target"]]
    if self_loops:
        fail_count += len(self_loops)
        for sl in self_loops:
            failures.append(f"Self-loop: {sl[0]}")
            print(f"  [X] Self-loop: {sl[0]}")
    else:
        pass_count += 1
        print(f"  [v] No self-loops")

    # Check all edge endpoints exist as nodes
    broken = [(e["source"], e["target"]) for e in edges
              if e["source"] not in nodes or e["target"] not in nodes]
    if broken:
        fail_count += len(broken)
        for b in broken:
            failures.append(f"Broken edge endpoint: {b}")
            print(f"  [X] Broken edge: {b[0]} --> {b[1]}")
    else:
        pass_count += 1
        print(f"  [v] All edge endpoints exist as nodes")

    # ── 5. Summary ────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("5. GRAPH STATS")
    print("=" * 60)
    print(f"  Total nodes:  {stats['total_nodes']}")
    print(f"  Total edges:  {stats['total_edges']}")
    print(f"  Node types:   {stats['node_types']}")
    print(f"  Edge types:   {stats['edge_types']}")
    print(f"  Density:      {stats['density']}")
    print(f"  Is DAG:       {stats['is_dag']}")

    # Top 5 nodes by degree
    top = sorted(data["nodes"], key=lambda n: n.get("degree", 0), reverse=True)[:5]
    print(f"\n  Top 5 by degree:")
    for n in top:
        print(f"    {n['label']:<35} degree={n['degree']}  type={n['type']}")

    # ── Final result ──────────────────────────────────────────────────────────
    total = pass_count + fail_count
    pct = round(pass_count / total * 100) if total else 0
    print()
    print("=" * 60)
    print(f"RESULT: {pass_count}/{total} checks passed ({pct}%)")
    if failures:
        print(f"\nFailed checks ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
    else:
        print("All checks passed.")
    print("=" * 60)


if __name__ == "__main__":
    run()
