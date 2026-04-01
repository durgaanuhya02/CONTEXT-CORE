"""
Standalone DB seeder — reads knowledge_graph.json directly (no GraphRAG needed).
Populates: knowledge_nodes, knowledge_owners, risk_scores

Run:
    python seed_db.py
"""

import json
import math
import os
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://contextcore:contextcore@localhost:5432/contextcore")
GRAPH_JSON = Path(__file__).parent.parent.parent / "dataset" / "ner_output" / "knowledge_graph.json"

LAMBDA = 0.02

SOURCE_DATES = {
    "slack":            "2022-03-14",
    "confluence":       "2022-03-15",
    "github":           "2023-04-08",
    "zoom":             "2022-07-20",
    "domain_knowledge": "2022-01-01",
    "inferred":         "2022-01-01",
    "unknown":          "2022-01-01",
}

ENTITY_AUTHOR_MAP = {
    "alice.chen": "alice.chen",
    "bob.martinez": "bob.martinez",
    "carol.singh": "carol.singh",
    "david.kim": "david.kim",
    "priya.nair": "priya.nair",
    "billing-service": "alice.chen",
    "billing_service": "alice.chen",
    "pgbouncer": "alice.chen",
    "postgresql": "alice.chen",
    "postgres": "alice.chen",
    "acid_compliance": "alice.chen",
    "connection_pooling": "alice.chen",
    "circuit_breaker": "alice.chen",
    "adr-001": "alice.chen",
    "adr-002": "alice.chen",
    "adr-004": "alice.chen",
    "strangler_fig": "alice.chen",
    "notifications-service": "carol.singh",
    "notifications_service": "carol.singh",
    "adr-003": "carol.singh",
    "redis": "bob.martinez",
    "recommendations-engine": "bob.martinez",
    "recommendations_engine": "bob.martinez",
    "adr-007": "bob.martinez",
    "kubernetes": "david.kim",
    "istio": "david.kim",
    "sqs": "david.kim",
    "pr_#142": "david.kim",
    "pr_#178": "carol.singh",
    "pr_#289": "alice.chen",
}

SOURCE_FILE_MAP = {
    "slack": "slack_architecture_decisions.txt",
    "confluence": "confluence_adrs.txt",
    "github": "github_prs.txt",
    "zoom": "zoom_transcripts.txt",
    "domain_knowledge": "onboarding_docs.txt",
    "inferred": "onboarding_docs.txt",
    "unknown": "onboarding_docs.txt",
}


def exponential_decay(created_at_iso: str) -> float:
    try:
        created = datetime.fromisoformat(created_at_iso)
    except Exception:
        created = datetime(2022, 3, 14)
    months = (datetime.now() - created).days / 30.44
    return round(max(0.05, min(1.0, math.exp(-LAMBDA * months))), 4)


def resolve_author(node_id: str) -> str:
    nid = node_id.lower()
    for key, author in ENTITY_AUTHOR_MAP.items():
        if key in nid or nid == key:
            return author
    return "unknown"


def seed():
    if not GRAPH_JSON.exists():
        print(f"ERROR: {GRAPH_JSON} not found. Run build_graph.py first.")
        return

    print(f"Loading knowledge graph from {GRAPH_JSON}...")
    graph = json.loads(GRAPH_JSON.read_text())
    nodes = graph["nodes"]
    print(f"  {len(nodes)} nodes found")

    engine = sa.create_engine(DATABASE_URL)

    node_rows = []
    for node in nodes:
        nid = node["id"]
        source = node.get("source", "unknown")
        created_at_str = SOURCE_DATES.get(source, "2022-01-01")
        decay = node.get("decay_score") or exponential_decay(created_at_str)
        author = resolve_author(nid)

        node_rows.append({
            "id": nid,
            "title": node.get("label", nid),
            "description": node.get("rationale", None),
            "source_system": source,
            "source_file": SOURCE_FILE_MAP.get(source, "onboarding_docs.txt"),
            "author_id": author,
            "created_at": datetime.fromisoformat(created_at_str),
            "last_validated": datetime.now(),
            "decay_score": decay,
            "community_id": node.get("type", None),
            "inserted_at": datetime.now(),
        })

    with engine.begin() as conn:
        # Clear and re-seed
        conn.execute(sa.text("DELETE FROM regulatory_tags"))
        conn.execute(sa.text("DELETE FROM coverage_gaps"))
        conn.execute(sa.text("DELETE FROM risk_scores"))
        conn.execute(sa.text("DELETE FROM knowledge_owners"))
        conn.execute(sa.text("DELETE FROM knowledge_nodes"))

        for row in node_rows:
            conn.execute(sa.text(
                "INSERT INTO knowledge_nodes "
                "(id, title, description, source_system, source_file, author_id, "
                "created_at, last_validated, decay_score, community_id, tags, inserted_at) "
                "VALUES (:id, :title, :description, :source_system, :source_file, :author_id, "
                ":created_at, :last_validated, :decay_score, :community_id, '{}', :inserted_at)"
            ), row)
        print(f"  Inserted {len(node_rows)} knowledge nodes")

        # Build owner stats
        from collections import Counter
        author_counts = Counter(r["author_id"] for r in node_rows)
        total = len(node_rows)

        owner_data = [
            ("alice.chen",   "alice.chen@acmecorp.com",   "Senior Engineer",          0.85),
            ("bob.martinez", "bob.martinez@acmecorp.com", "Engineer",                 0.45),
            ("carol.singh",  "carol.singh@acmecorp.com",  "Engineer",                 0.20),
            ("david.kim",    "david.kim@acmecorp.com",    "Infrastructure Engineer",  0.95),
            ("priya.nair",   "priya.nair@acmecorp.com",   "CTO",                      0.30),
        ]
        for author_id, email, role, risk_score in owner_data:
            conn.execute(sa.text(
                "INSERT INTO knowledge_owners (author_id, email, role, node_count, risk_score, is_active, updated_at) "
                "VALUES (:a, :e, :r, :nc, :rs, TRUE, NOW())"
            ), {"a": author_id, "e": email, "r": role,
                "nc": author_counts.get(author_id, 0), "rs": risk_score})
        print(f"  Inserted {len(owner_data)} knowledge owners")

        # Seed risk scores
        risk_data = [
            ("billing-service",       "alice.chen",   "HIGH",     0.85,
             "Alice Chen owns 70% of billing-service institutional knowledge. Transitioned to platform team Oct 2023.",
             author_counts.get("alice.chen", 34), True),
            ("istio-service-mesh",    "david.kim",    "CRITICAL", 0.95,
             "David Kim is the sole Istio expert. Secondary contractor leaving June 2024. No documented succession.",
             author_counts.get("david.kim", 18), True),
            ("recommendations-engine","bob.martinez", "MEDIUM",   0.45,
             "Bob Martinez recently onboarded. Redis/recommendations knowledge concentrated.",
             author_counts.get("bob.martinez", 21), False),
            ("notifications-service", "carol.singh",  "LOW",      0.20,
             "Well documented. Multiple engineers familiar with the service.",
             author_counts.get("carol.singh", 14), False),
        ]
        for domain, owner, level, score, reason, nc, sole in risk_data:
            conn.execute(sa.text(
                "INSERT INTO risk_scores (domain, owner_id, risk_level, risk_score, reason, node_count, sole_owner, updated_at) "
                "VALUES (:d, :o, :l, :s, :r, :nc, :so, NOW())"
            ), {"d": domain, "o": owner, "l": level, "s": score,
                "r": reason, "nc": nc, "so": sole})
        print(f"  Inserted {len(risk_data)} risk scores")

    print("DB seeding complete.")


if __name__ == "__main__":
    seed()
