"""
Step 3 — NetworkX Knowledge Graph Builder

Reads spaCy NER output (entities_combined.json) and builds a typed
knowledge graph with edges: MADE_BY, SUPPORTS, CONTRADICTS, SUPERSEDES,
USES, OWNS, DOCUMENTED_BY, PARTICIPATED_IN.

Outputs:
  - dataset/ner_output/knowledge_graph.graphml  (for D3 / Gephi)
  - dataset/ner_output/knowledge_graph.json     (for API / frontend)
  - Prints graph stats

Install:
    pip install networkx
"""

import json
import math
from datetime import datetime
from pathlib import Path

import networkx as nx

LAMBDA = 0.02  # decay rate: e^(-lambda * months) — tuned for 2-4 year old enterprise data


def compute_decay(created_at: str) -> float:
    """confidence = e^(-lambda * months_since_created), floor 0.05"""
    try:
        created = datetime.fromisoformat(created_at)
        months = (datetime.now() - created).days / 30.44
        return round(max(0.05, min(1.0, math.exp(-LAMBDA * months))), 4)
    except Exception:
        return 0.75


# Source → fallback created_at when NODE_META has no entry
SOURCE_DATE_DEFAULTS = {
    "slack":            "2022-03-14",
    "confluence":       "2022-03-15",
    "github":           "2023-04-08",
    "zoom":             "2022-07-20",
    "domain_knowledge": "2022-01-01",
    "inferred":         "2022-01-01",
    "unknown":          "2022-01-01",
}

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
NER_OUTPUT = SCRIPT_DIR.parent.parent / "dataset" / "ner_output"
ENTITIES_FILE = NER_OUTPUT / "entities_combined.json"

# ── Typed edge definitions ────────────────────────────────────────────────────
# Format: (source_id, target_id, edge_type, weight, rationale)

EXPLICIT_EDGES = [
    # MADE_BY — who authored each decision
    ("ADR-001",         "alice.chen",   "MADE_BY",       1.0, "Alice Chen authored ADR-001 (Postgres over MongoDB)"),
    ("ADR-002",         "alice.chen",   "MADE_BY",       1.0, "Alice Chen authored ADR-002 (Strangler Fig migration)"),
    ("ADR-003",         "carol.singh",  "MADE_BY",       1.0, "Carol Singh authored ADR-003 (v1 API deprecation)"),
    ("ADR-004",         "alice.chen",   "MADE_BY",       1.0, "Alice Chen authored ADR-004 (pgBouncer over RDS Proxy)"),
    ("ADR-007",         "bob.martinez", "MADE_BY",       1.0, "Bob Martinez authored ADR-007 (Redis over Memcached)"),
    ("PR_#142",         "david.kim",    "MADE_BY",       1.0, "David Kim opened PR #142 (pgBouncer sidecar)"),
    ("PR_#178",         "carol.singh",  "MADE_BY",       1.0, "Carol Singh opened PR #178 (notifications extraction)"),
    ("PR_#289",         "alice.chen",   "MADE_BY",       1.0, "Alice Chen opened PR #289 (knowledge transfer docs)"),

    # OWNS — who is responsible for each system
    ("alice.chen",      "billing-service",              "OWNS", 0.9, "Alice Chen primary owner until Oct 2023"),
    ("alice.chen",      "postgresql",                   "OWNS", 0.9, "Alice Chen is the institutional PostgreSQL expert"),
    ("alice.chen",      "pgbouncer",                    "OWNS", 1.0, "Alice Chen designed and owns the pgBouncer configuration"),
    ("alice.chen",      "circuit_breaker",              "OWNS", 1.0, "Alice Chen defined the 50% circuit breaker threshold"),
    ("alice.chen",      "connection_pooling",           "OWNS", 0.9, "Alice Chen owns connection pooling knowledge"),
    ("alice.chen",      "acid_compliance",              "OWNS", 0.9, "Alice Chen owns ACID compliance rationale for billing"),
    ("bob.martinez",    "billing-service",              "OWNS", 0.7, "Bob Martinez took ownership Oct 2023"),
    ("carol.singh",     "notifications-service",        "OWNS", 1.0, "Carol Singh owns notifications-service"),
    ("bob.martinez",    "recommendations-engine",       "OWNS", 1.0, "Bob Martinez owns recommendations engine"),
    ("david.kim",       "kubernetes",                   "OWNS", 1.0, "David Kim owns Kubernetes infrastructure"),
    ("david.kim",       "istio",                        "OWNS", 1.0, "David Kim sole Istio expert"),

    # USES — system dependencies
    ("billing-service", "postgresql",                   "USES", 1.0, "billing-service uses PostgreSQL as primary DB"),
    ("billing-service", "pgbouncer",                    "USES", 1.0, "billing-service uses pgBouncer connection pooler"),
    ("billing-service", "circuit_breaker",              "USES", 1.0, "billing-service has circuit breaker at 50% threshold"),
    ("billing-service", "sqs",                          "USES", 0.8, "billing-service uses SQS for event messaging"),
    ("notifications-service", "sqs",                   "USES", 1.0, "notifications-service is event-driven via SQS"),
    ("recommendations-engine", "redis",                "USES", 1.0, "recommendations engine uses Redis for caching"),
    ("kubernetes",      "istio",                        "USES", 1.0, "Kubernetes cluster uses Istio service mesh"),

    # SUPPORTS — decisions that support other decisions or systems
    ("ADR-001",         "billing-service",              "SUPPORTS", 1.0, "ADR-001 establishes Postgres as billing DB"),
    ("ADR-002",         "notifications-service",        "SUPPORTS", 1.0, "ADR-002 strangler fig produced notifications extraction"),
    ("ADR-004",         "billing-service",              "SUPPORTS", 1.0, "ADR-004 pgBouncer config supports billing reliability"),
    ("ADR-007",         "recommendations-engine",       "SUPPORTS", 1.0, "ADR-007 Redis supports recommendations caching"),
    ("PR_#142",         "ADR-004",                      "SUPPORTS", 1.0, "PR #142 implements ADR-004 pgBouncer decision"),
    ("PR_#178",         "ADR-002",                      "SUPPORTS", 1.0, "PR #178 implements ADR-002 strangler fig extraction"),

    # CONTRADICTS — rejected alternatives
    ("ADR-001",         "mongodb",                      "CONTRADICTS", 1.0, "ADR-001 rejected MongoDB due to lack of ACID compliance"),
    ("ADR-004",         "rds_proxy",                    "CONTRADICTS", 1.0, "ADR-004 rejected RDS Proxy: session pooling only, 5ms latency"),
    ("ADR-007",         "memcached",                    "CONTRADICTS", 1.0, "ADR-007 rejected Memcached: no pub/sub, no persistence"),

    # SUPERSEDES — newer decisions replacing older ones
    ("ADR-003",         "ADR-001",                      "SUPERSEDES", 0.3, "ADR-003 v2 API supersedes v1 patterns (partial)"),

    # DOCUMENTED_BY — knowledge captured in docs
    ("billing-service", "PR_#289",                      "DOCUMENTED_BY", 1.0, "PR #289 is the knowledge transfer doc for billing-service"),
    ("ADR-004",         "PR_#142",                      "DOCUMENTED_BY", 1.0, "PR #142 review documents pgBouncer rationale"),
    ("circuit_breaker", "PR_#289",                      "DOCUMENTED_BY", 1.0, "GOTCHAS.md in PR #289 documents 50% threshold rationale"),

    # PARTICIPATED_IN — who was in key decisions
    ("bob.martinez",    "ADR-001",                      "PARTICIPATED_IN", 0.8, "Bob Martinez recommended Postgres in Slack thread"),
    ("david.kim",       "ADR-001",                      "PARTICIPATED_IN", 0.7, "David Kim noted infra team only supports Postgres"),
    ("carol.singh",     "ADR-002",                      "PARTICIPATED_IN", 0.8, "Carol Singh raised service discovery concerns"),
    ("priya.nair",      "ADR-002",                      "PARTICIPATED_IN", 1.0, "Priya Nair approved strangler fig migration"),
    ("alice.chen",      "ADR-004",                      "PARTICIPATED_IN", 1.0, "Alice Chen led pgBouncer decision post-outage"),
    ("alice.chen",      "ADR-003",                      "PARTICIPATED_IN", 0.8, "Alice Chen reviewed and approved ADR-003 API deprecation"),
    ("alice.chen",      "ADR-007",                      "PARTICIPATED_IN", 0.5, "Alice Chen participated in Redis caching discussion"),
    ("david.kim",       "ADR-004",                      "PARTICIPATED_IN", 0.9, "David Kim deployed pgBouncer sidecar"),
    ("priya.nair",      "ADR-004",                      "PARTICIPATED_IN", 0.8, "Priya Nair asked why not RDS Proxy in postmortem"),
    ("bob.martinez",    "ADR-007",                      "PARTICIPATED_IN", 0.9, "Bob Martinez proposed Redis for recommendations"),
    ("carol.singh",     "ADR-007",                      "PARTICIPATED_IN", 0.7, "Carol Singh confirmed Redis pub/sub requirement"),

    # RELATED_TO — connect orphan concept/tech nodes to relevant decisions/projects
    ("strangler_fig",           "ADR-002",              "RELATED_TO", 1.0, "Strangler fig is the pattern described in ADR-002"),
    ("monolith",                "ADR-002",              "RELATED_TO", 1.0, "ADR-002 strangler fig migration targets the monolith"),
    ("notifications-service",   "monolith",             "RELATED_TO", 1.0, "notifications-service was extracted from the monolith"),
    ("acid_compliance",         "ADR-001",              "RELATED_TO", 1.0, "ACID compliance is the core rationale for ADR-001"),
    ("connection_pooling",      "ADR-004",              "RELATED_TO", 1.0, "Connection pooling is the subject of ADR-004"),
    ("transaction_pooling",     "pgbouncer",            "RELATED_TO", 1.0, "pgBouncer uses transaction pooling mode"),
    ("session_pooling",         "rds_proxy",            "RELATED_TO", 1.0, "RDS Proxy only supports session pooling"),
    ("service_mesh",            "istio",                "RELATED_TO", 1.0, "Istio is the service mesh implementation"),
    ("knowledge_transfer",      "PR_#289",              "RELATED_TO", 1.0, "PR #289 is the knowledge transfer document"),
    ("single_point_of_failure", "david.kim",            "RELATED_TO", 0.9, "David Kim is a single point of failure for Istio"),
    ("single_point_of_failure", "alice.chen",           "RELATED_TO", 0.9, "Alice Chen was a single point of failure for billing-service"),
    ("microservices",           "ADR-002",              "RELATED_TO", 0.8, "Microservices is the target architecture of ADR-002"),
    ("api_versioning",          "ADR-003",              "RELATED_TO", 1.0, "API versioning is the subject of ADR-003"),
    ("launchdarkly",            "notifications-service","RELATED_TO", 0.8, "LaunchDarkly feature flags used in notifications extraction"),
    ("linkerd",                 "istio",                "RELATED_TO", 0.8, "Linkerd is the alternative being evaluated to replace Istio"),
    ("postgres",                "postgresql",           "RELATED_TO", 1.0, "postgres is the informal name for postgresql"),
    ("oauth2",                  "ADR-003",              "RELATED_TO", 1.0, "OAuth2 is the auth standard mandated in ADR-003"),
    ("jwt",                     "ADR-003",              "RELATED_TO", 1.0, "JWT tokens are mandated in ADR-003 v2 API"),
    ("aws",                     "billing-service",      "RELATED_TO", 0.7, "AWS RDS hosts the billing-service database"),
    ("rds",                     "postgresql",           "RELATED_TO", 1.0, "RDS is the managed PostgreSQL service used"),
    ("acmecorp",                "billing-service",      "RELATED_TO", 1.0, "AcmeCorp owns billing-service"),
    ("platform_team",           "alice.chen",           "RELATED_TO", 1.0, "Alice Chen moved to the platform team"),
    ("PR_#203",                 "ADR-003",              "RELATED_TO", 1.0, "PR #203 implements v1 API deprecation from ADR-003"),
    ("PR_#267",                 "ADR-007",              "RELATED_TO", 1.0, "PR #267 adds Redis caching per ADR-007"),
]

# Node metadata — includes created_at (ISO date) derived from dataset narrative
# decay_score is computed from created_at using e^(-lambda * months), not hardcoded
NODE_META: dict[str, dict] = {
    # People — joined AcmeCorp before dataset start
    "alice.chen":               {"type": "PERSON",     "label": "Alice Chen",              "risk": 0.85, "created_at": "2021-01-01"},
    "bob.martinez":             {"type": "PERSON",     "label": "Bob Martinez",             "risk": 0.45, "created_at": "2021-06-01"},
    "carol.singh":              {"type": "PERSON",     "label": "Carol Singh",              "risk": 0.20, "created_at": "2021-03-01"},
    "david.kim":                {"type": "PERSON",     "label": "David Kim",                "risk": 0.95, "created_at": "2021-09-01"},
    "priya.nair":               {"type": "PERSON",     "label": "Priya Nair",               "risk": 0.10, "created_at": "2020-01-01"},
    # Decisions — dated from ADR/PR creation dates in the dataset
    "ADR-001":                  {"type": "DECISION",   "label": "ADR-001: Postgres",        "created_at": "2022-03-15"},
    "ADR-002":                  {"type": "DECISION",   "label": "ADR-002: Strangler Fig",   "created_at": "2022-07-10"},
    "ADR-003":                  {"type": "DECISION",   "label": "ADR-003: API Deprecation", "created_at": "2022-11-22"},
    "ADR-004":                  {"type": "DECISION",   "label": "ADR-004: pgBouncer",       "created_at": "2023-04-10"},
    "ADR-007":                  {"type": "DECISION",   "label": "ADR-007: Redis",           "created_at": "2024-01-16"},
    "PR_#142":                  {"type": "DECISION",   "label": "PR #142: pgBouncer impl",  "created_at": "2023-04-08"},
    "PR_#178":                  {"type": "DECISION",   "label": "PR #178: Notifications",   "created_at": "2023-11-14"},
    "PR_#203":                  {"type": "DECISION",   "label": "PR #203: v1 Deprecation",  "created_at": "2023-01-10"},
    "PR_#267":                  {"type": "DECISION",   "label": "PR #267: Redis Caching",   "created_at": "2024-01-22"},
    "PR_#289":                  {"type": "DECISION",   "label": "PR #289: Knowledge Xfer",  "created_at": "2023-10-05"},
    # Projects — created when first mentioned in dataset
    "billing-service":          {"type": "PROJECT",    "label": "billing-service",          "created_at": "2022-03-14"},
    "notifications-service":    {"type": "PROJECT",    "label": "notifications-service",    "created_at": "2022-07-08"},
    "recommendations-engine":   {"type": "PROJECT",    "label": "recommendations-engine",   "created_at": "2024-01-15"},
    "monolith":                 {"type": "PROJECT",    "label": "Monolith",                 "created_at": "2021-01-01"},
    "platform_team":            {"type": "PROJECT",    "label": "Platform Team",            "created_at": "2023-09-12"},
    "acmecorp":                 {"type": "PROJECT",    "label": "AcmeCorp",                 "created_at": "2020-01-01"},
    # Technologies — dated from first ADR/decision that introduced them
    "postgresql":               {"type": "TECHNOLOGY", "label": "PostgreSQL",               "created_at": "2022-03-15"},
    "pgbouncer":                {"type": "TECHNOLOGY", "label": "pgBouncer",                "created_at": "2023-04-08"},
    "redis":                    {"type": "TECHNOLOGY", "label": "Redis",                    "created_at": "2024-01-16"},
    "mongodb":                  {"type": "TECHNOLOGY", "label": "MongoDB (rejected)",       "created_at": "2022-03-14"},
    "rds_proxy":                {"type": "TECHNOLOGY", "label": "RDS Proxy (rejected)",     "created_at": "2023-04-05"},
    "memcached":                {"type": "TECHNOLOGY", "label": "Memcached (rejected)",     "created_at": "2024-01-15"},
    "kubernetes":               {"type": "TECHNOLOGY", "label": "Kubernetes",               "created_at": "2022-07-09"},
    "istio":                    {"type": "TECHNOLOGY", "label": "Istio",                    "created_at": "2022-07-09"},
    "sqs":                      {"type": "TECHNOLOGY", "label": "AWS SQS",                  "created_at": "2022-07-10"},
    "launchdarkly":             {"type": "TECHNOLOGY", "label": "LaunchDarkly",             "created_at": "2023-11-14"},
    "linkerd":                  {"type": "TECHNOLOGY", "label": "Linkerd (candidate)",      "created_at": "2024-03-10"},
    "oauth2":                   {"type": "TECHNOLOGY", "label": "OAuth2",                   "created_at": "2022-11-22"},
    "jwt":                      {"type": "TECHNOLOGY", "label": "JWT",                      "created_at": "2022-11-22"},
    "aws":                      {"type": "TECHNOLOGY", "label": "AWS",                      "created_at": "2022-03-15"},
    "rds":                      {"type": "TECHNOLOGY", "label": "AWS RDS",                  "created_at": "2022-03-15"},
    "postgres":                 {"type": "TECHNOLOGY", "label": "Postgres (alias)",         "created_at": "2022-03-14"},
    # Concepts — dated from first document that introduced them
    "circuit_breaker":          {"type": "CONCEPT",    "label": "Circuit Breaker (50%)",    "created_at": "2023-04-03"},
    "strangler_fig":            {"type": "CONCEPT",    "label": "Strangler Fig Pattern",    "created_at": "2022-07-08"},
    "acid_compliance":          {"type": "CONCEPT",    "label": "ACID Compliance",          "created_at": "2022-03-14"},
    "connection_pooling":       {"type": "CONCEPT",    "label": "Connection Pooling",       "created_at": "2023-04-03"},
    "api_versioning":           {"type": "CONCEPT",    "label": "API Versioning (v2)",      "created_at": "2022-11-21"},
    "transaction_pooling":      {"type": "CONCEPT",    "label": "Transaction Pooling",      "created_at": "2023-04-08"},
    "session_pooling":          {"type": "CONCEPT",    "label": "Session Pooling",          "created_at": "2023-04-05"},
    "service_mesh":             {"type": "CONCEPT",    "label": "Service Mesh",             "created_at": "2022-07-09"},
    "knowledge_transfer":       {"type": "CONCEPT",    "label": "Knowledge Transfer",       "created_at": "2023-09-12"},
    "single_point_of_failure":  {"type": "CONCEPT",    "label": "Single Point of Failure",  "created_at": "2024-03-10"},
    "microservices":            {"type": "CONCEPT",    "label": "Microservices",            "created_at": "2022-07-08"},
}


def build_graph(entities_data: dict) -> nx.DiGraph:
    G = nx.DiGraph()

    # Alias map: NER-extracted IDs that are duplicates of canonical node IDs.
    # Any entity whose id is in this map gets merged into the canonical node.
    ALIAS_TO_CANONICAL = {
        # Project aliases
        "billing_service":          "billing-service",
        "billing_service_":         "billing-service",
        "notifications_service":    "notifications-service",
        "notifications_service_":   "notifications-service",
        "notifications_module":     "notifications-service",
        "recommendations_engine":   "recommendations-engine",
        "monolith":                 "monolith",
        # Decision aliases
        "PR_289":                   "PR_#289",
        "PR__289":                  "PR_#289",
        # Concept aliases — merge into the canonical concept node
        "connection_pool":          "connection_pooling",
        "acid":                     "acid_compliance",
        "v2":                       "api_versioning",
        "v2_api":                   "api_versioning",
        "versioning":               "api_versioning",
        "semantic_versioning":      "api_versioning",
        "url_path_versioning":      "api_versioning",
        # Technology aliases
        "postgres":                 "postgresql",
        "rds":                      "postgresql",
    }

    # Add nodes from NER output — skip aliases (they map to canonical nodes)
    for ent in entities_data.get("entities", []):
        nid = ent["id"]
        canonical = ALIAS_TO_CANONICAL.get(nid, nid)  # resolve alias
        if canonical in G:
            # Already exists — just enrich files list
            existing_files = G.nodes[canonical].get("files", "")
            new_files = ",".join(ent.get("files", [ent.get("file", "")]))
            if new_files and new_files not in existing_files:
                G.nodes[canonical]["files"] = f"{existing_files},{new_files}".strip(",")
            continue
        meta = NODE_META.get(canonical, {})
        created_at = meta.get("created_at") or SOURCE_DATE_DEFAULTS.get(ent.get("source", "unknown"), "2022-01-01")
        G.add_node(canonical,
            label=meta.get("label", ent.get("text", canonical)),
            type=meta.get("type", ent.get("type", "OTHER")),
            source=ent.get("source", "unknown"),
            files=",".join(ent.get("files", [ent.get("file", "")])),
            created_at=created_at,
            decay_score=compute_decay(created_at),
            risk_score=meta.get("risk", 0.0),
        )

    # Add any nodes from NODE_META not in NER output
    for nid, meta in NODE_META.items():
        if nid not in G:
            created_at = meta.get("created_at", "2022-01-01")
            G.add_node(nid,
                label=meta["label"],
                type=meta["type"],
                source="domain_knowledge",
                files="",
                created_at=created_at,
                decay_score=compute_decay(created_at),
                risk_score=meta.get("risk", 0.0),
            )

    # Add typed edges — ensure both nodes exist with created_at
    for src, tgt, etype, weight, rationale in EXPLICIT_EDGES:
        for nid in (src, tgt):
            if nid not in G:
                meta = NODE_META.get(nid, {})
                created_at = meta.get("created_at", "2022-01-01")
                G.add_node(nid,
                    label=meta.get("label", nid),
                    type=meta.get("type", "UNKNOWN"),
                    source="inferred",
                    files="",
                    created_at=created_at,
                    decay_score=compute_decay(created_at),
                    risk_score=meta.get("risk", 0.0),
                )
        G.add_edge(src, tgt,
            type=etype,
            weight=weight,
            rationale=rationale,
        )

    return G


def graph_to_json(G: nx.DiGraph) -> dict:
    """Convert NetworkX graph to JSON format compatible with D3 and the frontend."""
    now = datetime.now()
    nodes = []
    for nid, data in G.nodes(data=True):
        created_at = data.get("created_at", "2022-01-01")
        try:
            months_old = round((now - datetime.fromisoformat(created_at)).days / 30.44, 1)
        except Exception:
            months_old = 36.0
        nodes.append({
            "id": nid,
            "label": data.get("label", nid),
            "type": data.get("type", "OTHER"),
            "source": data.get("source", "unknown"),
            "files": data.get("files", ""),
            "created_at": created_at,
            "months_old": months_old,
            "is_stale": months_old > 18,
            "decay_score": data.get("decay_score", compute_decay(created_at)),
            "risk_score": data.get("risk_score", 0.0),
            "degree": G.degree(nid),
            "in_degree": G.in_degree(nid),
            "out_degree": G.out_degree(nid),
        })

    edges = []
    for src, tgt, data in G.edges(data=True):
        edges.append({
            "source": src,
            "target": tgt,
            "type": data.get("type", "RELATED"),
            "weight": data.get("weight", 1.0),
            "rationale": data.get("rationale", ""),
        })

    # Compute graph stats
    edge_types: dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        t = d.get("type", "UNKNOWN")
        edge_types[t] = edge_types.get(t, 0) + 1

    node_types: dict[str, int] = {}
    for _, d in G.nodes(data=True):
        t = d.get("type", "OTHER")
        node_types[t] = node_types.get(t, 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
            "density": round(nx.density(G), 4),
            "is_dag": nx.is_directed_acyclic_graph(G),
        },
        "generated_at": datetime.now().isoformat(),
    }


def print_stats(G: nx.DiGraph):
    print(f"\n── Graph Statistics ──────────────────────────")
    print(f"  Nodes:  {G.number_of_nodes()}")
    print(f"  Edges:  {G.number_of_edges()}")
    print(f"  Density: {nx.density(G):.4f}")

    print(f"\n── Top nodes by degree ───────────────────────")
    top = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:10]
    for nid, deg in top:
        label = G.nodes[nid].get("label", nid)
        ntype = G.nodes[nid].get("type", "?")
        print(f"  {label:<35} [{ntype}]  degree={deg}")

    print(f"\n── Edge types ────────────────────────────────")
    edge_types: dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        t = d.get("type", "UNKNOWN")
        edge_types[t] = edge_types.get(t, 0) + 1
    for etype, count in sorted(edge_types.items(), key=lambda x: -x[1]):
        print(f"  {etype:<20} {count}")

    print(f"\n── High-risk single owners ───────────────────")
    for nid, data in G.nodes(data=True):
        if data.get("risk_score", 0) >= 0.8:
            owned = [tgt for _, tgt, d in G.out_edges(nid, data=True) if d.get("type") == "OWNS"]
            print(f"  {data.get('label', nid):<20} risk={data['risk_score']}  owns={owned}")


def run():
    if not ENTITIES_FILE.exists():
        print(f"ERROR: {ENTITIES_FILE} not found.")
        print("Run preprocess.py first: python preprocess.py")
        return

    print("Loading NER entities...")
    entities_data = json.loads(ENTITIES_FILE.read_text())
    print(f"  {entities_data['total_entities']} entities loaded")

    print("Building knowledge graph...")
    G = build_graph(entities_data)

    print_stats(G)

    # Export GraphML (for Gephi, D3, external tools)
    graphml_path = NER_OUTPUT / "knowledge_graph.graphml"
    nx.write_graphml(G, str(graphml_path))
    print(f"\nGraphML saved: {graphml_path}")

    # Export JSON (for API and frontend)
    graph_json = graph_to_json(G)
    json_path = NER_OUTPUT / "knowledge_graph.json"
    json_path.write_text(json.dumps(graph_json, indent=2))
    print(f"JSON saved:    {json_path}")

    print(f"\nDone. Graph has {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")


if __name__ == "__main__":
    run()
