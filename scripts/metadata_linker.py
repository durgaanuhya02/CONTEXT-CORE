"""
Metadata Linker — reads GraphRAG parquet output + metadata JSON files,
enriches entities with provenance, writes to PostgreSQL.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://contextcore:contextcore@localhost:5432/contextcore")
GRAPHRAG_ROOT = Path(os.getenv("GRAPHRAG_ROOT", "../../dataset"))
METADATA_DIR = GRAPHRAG_ROOT / "metadata"
OUTPUT_DIR = GRAPHRAG_ROOT / "output"

# Source keyword mapping: which metadata file covers which entities
SOURCE_KEYWORDS = {
    "slack_architecture_decisions_meta.json": {
        "source_system": "slack",
        "keywords": ["postgres", "mongodb", "strangler", "redis", "memcached", "pgbouncer",
                     "circuit breaker", "connection pool", "v1 api", "notifications"],
        "author_default": "alice.chen",
        "date_default": "2022-03-14",
    },
    "confluence_adrs_meta.json": {
        "source_system": "confluence",
        "keywords": ["adr", "acid", "kubernetes", "istio", "oauth", "jwt", "rds proxy",
                     "transaction pooling", "session pooling"],
        "author_default": "alice.chen",
        "date_default": "2022-03-15",
    },
    "github_prs_meta.json": {
        "source_system": "github",
        "keywords": ["pr", "pull request", "sidecar", "launchdarkly", "feature flag",
                     "deprecation header", "pub/sub"],
        "author_default": "david.kim",
        "date_default": "2023-04-08",
    },
    "zoom_transcripts_meta.json": {
        "source_system": "zoom",
        "keywords": ["postmortem", "all-hands", "architecture review", "tech stack review",
                     "outage", "migration planning"],
        "author_default": "priya.nair",
        "date_default": "2022-07-20",
    },
    "onboarding_docs_meta.json": {
        "source_system": "confluence",
        "keywords": ["onboarding", "runbook", "gotcha", "billing service", "single point of failure",
                     "utc bug", "prepared statement"],
        "author_default": "carol.singh",
        "date_default": "2024-01-08",
    },
}

# Known entity → author mapping (from our dataset narrative)
ENTITY_AUTHOR_MAP = {
    "alice chen": "alice.chen",
    "bob martinez": "bob.martinez",
    "carol singh": "carol.singh",
    "david kim": "david.kim",
    "priya nair": "priya.nair",
    "billing-service": "alice.chen",
    "billing service": "alice.chen",
    "pgbouncer": "alice.chen",
    "postgresql": "alice.chen",
    "postgres": "alice.chen",
    "notifications-service": "carol.singh",
    "notifications service": "carol.singh",
    "redis": "bob.martinez",
    "recommendations engine": "bob.martinez",
    "kubernetes": "david.kim",
    "istio": "david.kim",
    "adr-001": "alice.chen",
    "adr-002": "alice.chen",
    "adr-003": "carol.singh",
    "adr-004": "alice.chen",
    "adr-007": "bob.martinez",
}


def resolve_author(entity_title: str) -> str:
    title_lower = entity_title.lower()
    for key, author in ENTITY_AUTHOR_MAP.items():
        if key in title_lower:
            return author
    return "unknown"


def resolve_source(entity_title: str, description: str) -> tuple[str, str]:
    """Return (source_system, source_file) based on entity content."""
    combined = (entity_title + " " + (description or "")).lower()
    best_match = ("confluence", "confluence_adrs.txt")
    best_count = 0
    for meta_file, info in SOURCE_KEYWORDS.items():
        count = sum(1 for kw in info["keywords"] if kw in combined)
        if count > best_count:
            best_count = count
            source_file = meta_file.replace("_meta.json", ".txt")
            best_match = (info["source_system"], source_file)
    return best_match


def compute_decay_score(created_at_str: str) -> float:
    """Simple linear decay: 1.0 at creation, -0.1 per year, floor at 0.1"""
    try:
        created = datetime.fromisoformat(created_at_str)
        years_old = (datetime.now() - created).days / 365.0
        score = max(0.1, 1.0 - (years_old * 0.15))
        return round(score, 3)
    except Exception:
        return 0.8


def load_metadata_files() -> dict:
    """Load all metadata JSON files."""
    meta = {}
    for fname in METADATA_DIR.glob("*_meta.json"):
        with open(fname) as f:
            meta[fname.name] = json.load(f)
    return meta


def link_metadata():
    print("Starting metadata linking...")

    # Load GraphRAG entities
    entities_path = OUTPUT_DIR / "entities.parquet"
    if not entities_path.exists():
        print(f"ERROR: {entities_path} not found. Run 'graphrag index' first.")
        return

    entities_df = pd.read_parquet(entities_path)
    print(f"Loaded {len(entities_df)} entities from GraphRAG output")

    # Load communities if available
    communities_path = OUTPUT_DIR / "communities.parquet"
    community_map = {}
    if communities_path.exists():
        communities_df = pd.read_parquet(communities_path)
        # Map entity id → community id
        for _, row in communities_df.iterrows():
            for eid in (row.get("entity_ids") or []):
                community_map[eid] = str(row["id"])

    # Connect to DB
    engine = sa.create_engine(DATABASE_URL)

    rows = []
    for _, entity in entities_df.iterrows():
        title = str(entity.get("title", ""))
        description = str(entity.get("description", ""))
        entity_id = str(entity.get("id", ""))

        author = resolve_author(title)
        source_system, source_file = resolve_source(title, description)

        # Estimate creation date from source
        date_str = "2022-03-14"
        for meta_file, info in SOURCE_KEYWORDS.items():
            if info["source_system"] == source_system:
                date_str = info["date_default"]
                break

        decay = compute_decay_score(date_str)
        community_id = community_map.get(entity_id, None)

        rows.append({
            "id": entity_id,
            "title": title,
            "description": description[:1000] if description else None,
            "source_system": source_system,
            "source_file": source_file,
            "author_id": author,
            "created_at": datetime.fromisoformat(date_str),
            "last_validated": datetime.now(),
            "decay_score": decay,
            "community_id": community_id,
            "tags": [],  # empty list — stored as TEXT[] in postgres
            "inserted_at": datetime.now(),
        })

    if not rows:
        print("No entities to insert.")
        return

    nodes_df = pd.DataFrame(rows)

    with engine.begin() as conn:
        # Upsert knowledge_nodes — write row by row to handle TEXT[] properly
        conn.execute(sa.text("DELETE FROM knowledge_nodes"))
        for row in rows:
            conn.execute(sa.text(
                "INSERT INTO knowledge_nodes "
                "(id, title, description, source_system, source_file, author_id, "
                "created_at, last_validated, decay_score, community_id, tags, inserted_at) "
                "VALUES (:id, :title, :description, :source_system, :source_file, :author_id, "
                ":created_at, :last_validated, :decay_score, :community_id, :tags, :inserted_at)"
            ), {**row, "tags": "{}"})  # empty postgres array literal
        print(f"Inserted {len(rows)} knowledge nodes")

        # Build knowledge_owners from node data
        owner_counts = nodes_df.groupby("author_id").size().reset_index(name="node_count")
        total = len(rows)

        owner_rows = []
        for _, row in owner_counts.iterrows():
            author = row["author_id"]
            count = int(row["node_count"])
            ownership_pct = count / total
            # Risk score: higher ownership % = higher risk if person leaves
            risk = round(min(1.0, ownership_pct * 2.5), 3)
            owner_rows.append({
                "author_id": author,
                "email": f"{author}@acmecorp.com" if author != "unknown" else None,
                "role": "Engineer",
                "node_count": count,
                "risk_score": risk,
                "is_active": author != "unknown",
                "updated_at": datetime.now(),
            })

        conn.execute(sa.text("DELETE FROM knowledge_owners"))
        pd.DataFrame(owner_rows).to_sql("knowledge_owners", conn, if_exists="append", index=False)
        print(f"Inserted {len(owner_rows)} knowledge owners")

        # Build risk_scores
        risk_rows = [
            {
                "domain": "billing-service",
                "owner_id": "alice.chen",
                "risk_level": "HIGH",
                "risk_score": 0.85,
                "reason": "Alice Chen owns 70% of billing-service institutional knowledge. Transitioned to platform team Oct 2023.",
                "node_count": nodes_df[nodes_df["author_id"] == "alice.chen"].shape[0],
                "sole_owner": True,
                "updated_at": datetime.now(),
            },
            {
                "domain": "istio-service-mesh",
                "owner_id": "david.kim",
                "risk_level": "CRITICAL",
                "risk_score": 0.95,
                "reason": "David Kim is the sole Istio expert. Secondary contractor leaving June 2024. No documented succession.",
                "node_count": nodes_df[nodes_df["author_id"] == "david.kim"].shape[0],
                "sole_owner": True,
                "updated_at": datetime.now(),
            },
            {
                "domain": "notifications-service",
                "owner_id": "carol.singh",
                "risk_level": "LOW",
                "risk_score": 0.2,
                "reason": "Well documented. Multiple engineers familiar with the service.",
                "node_count": nodes_df[nodes_df["author_id"] == "carol.singh"].shape[0],
                "sole_owner": False,
                "updated_at": datetime.now(),
            },
            {
                "domain": "recommendations-engine",
                "owner_id": "bob.martinez",
                "risk_level": "MEDIUM",
                "risk_score": 0.45,
                "reason": "Bob Martinez recently onboarded to billing-service ownership. Redis/recommendations knowledge concentrated.",
                "node_count": nodes_df[nodes_df["author_id"] == "bob.martinez"].shape[0],
                "sole_owner": False,
                "updated_at": datetime.now(),
            },
        ]

        conn.execute(sa.text("DELETE FROM risk_scores"))
        pd.DataFrame(risk_rows).to_sql("risk_scores", conn, if_exists="append", index=False)
        print(f"Inserted {len(risk_rows)} risk scores")

    print("Metadata linking complete.")


if __name__ == "__main__":
    link_metadata()
