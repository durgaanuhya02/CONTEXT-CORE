"""
Neon PostgreSQL integration via HTTP API.
Uses Neon's serverless HTTP endpoint (port 443) instead of TCP port 5432,
which works even when firewalls block outbound PostgreSQL connections.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Parse connection string to extract host and credentials for HTTP API
def _parse_db_url(url: str) -> dict:
    """Extract host, user, password, dbname from a postgres:// URL."""
    try:
        # postgresql://user:pass@host/dbname?params
        url = url.replace("postgresql://", "").replace("postgres://", "")
        creds, rest = url.split("@", 1)
        user, password = creds.split(":", 1)
        host_part = rest.split("?")[0]
        host, dbname = host_part.split("/", 1) if "/" in host_part else (host_part, "neondb")
        return {"user": user, "password": password, "host": host, "dbname": dbname}
    except Exception:
        return {}

_DB = _parse_db_url(DATABASE_URL)
_HTTP_URL = f"https://{_DB.get('host', '')}/sql" if _DB.get("host") else None
_HEADERS = {
    "Content-Type": "application/json",
    "Neon-Connection-String": DATABASE_URL,
} if DATABASE_URL else {}

_enabled = bool(_HTTP_URL and DATABASE_URL)


def is_enabled() -> bool:
    return _enabled


def execute(query: str, params: list = None) -> list[dict]:
    """Execute a SQL query via Neon HTTP API. Returns list of row dicts."""
    if not _enabled:
        return []
    try:
        body = {"query": query}
        if params:
            body["params"] = [str(p) if p is not None else None for p in params]
        data = json.dumps(body).encode()
        req = urllib.request.Request(_HTTP_URL, data=data, headers=_HEADERS, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
        fields = [f["name"] for f in result.get("fields", [])]
        rows = result.get("rows", [])
        # Neon HTTP returns rows as dicts already when rowAsArray=false
        if rows and isinstance(rows[0], dict):
            return rows
        # Fallback: zip fields with array rows
        return [dict(zip(fields, row)) for row in rows]
    except Exception as e:
        print(f"[DB] Query error: {e}")
        return []


def execute_many(query: str, params_list: list[list]) -> bool:
    """Execute multiple inserts."""
    for params in params_list:
        execute(query, params)
    return True


def init_schema():
    """Create tables if they don't exist."""
    if not _enabled:
        return False
    queries = [
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            query_text TEXT NOT NULL,
            answer TEXT,
            source_nodes TEXT[],
            source_files TEXT[],
            confidence FLOAT,
            query_method VARCHAR(50),
            model_used VARCHAR(100),
            user_id VARCHAR(100),
            queried_at TIMESTAMP DEFAULT NOW(),
            entry_hash VARCHAR(64),
            prev_hash VARCHAR(64)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge_nodes (
            id VARCHAR(200) PRIMARY KEY,
            label TEXT,
            node_type VARCHAR(50),
            source VARCHAR(50),
            created_at DATE,
            decay_score FLOAT,
            risk_score FLOAT,
            rationale TEXT,
            url TEXT,
            ingested_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge_edges (
            id SERIAL PRIMARY KEY,
            source_id VARCHAR(200),
            target_id VARCHAR(200),
            edge_type VARCHAR(50),
            weight FLOAT,
            rationale TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ingest_runs (
            id SERIAL PRIMARY KEY,
            repos TEXT[],
            node_count INT,
            edge_count INT,
            ran_at TIMESTAMP DEFAULT NOW(),
            status VARCHAR(20)
        )
        """,
    ]
    for q in queries:
        execute(q)
    print("[DB] Schema initialized")
    return True


def save_audit_entry(entry: dict) -> int:
    """Persist an audit log entry to PostgreSQL."""
    if not _enabled:
        return 0
    rows = execute(
        """
        INSERT INTO audit_log
            (query_text, answer, source_nodes, source_files, confidence,
             query_method, model_used, user_id, queried_at, entry_hash, prev_hash)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        RETURNING id
        """,
        [
            entry.get("query_text", ""),
            (entry.get("answer") or "")[:2000],
            "{" + ",".join(f'"{s}"' for s in entry.get("source_nodes", [])) + "}",
            "{" + ",".join(f'"{s}"' for s in entry.get("source_files", [])) + "}",
            entry.get("confidence"),
            entry.get("query_method", "local"),
            entry.get("model_used", "template"),
            entry.get("user_id", "demo_user"),
            entry.get("queried_at", datetime.now().isoformat()),
            entry.get("entry_hash", ""),
            entry.get("prev_hash", "GENESIS"),
        ],
    )
    return rows[0]["id"] if rows else 0


def get_audit_log(limit: int = 20) -> list[dict]:
    """Fetch audit log from PostgreSQL."""
    if not _enabled:
        return []
    return execute(
        "SELECT * FROM audit_log ORDER BY queried_at DESC LIMIT $1",
        [limit]
    )


def save_graph(nodes: list[dict], edges: list[dict], repos: list[str]):
    """Persist graph nodes and edges to PostgreSQL."""
    if not _enabled:
        return
    # Clear existing
    execute("DELETE FROM knowledge_edges")
    execute("DELETE FROM knowledge_nodes")

    for n in nodes:
        execute(
            """
            INSERT INTO knowledge_nodes
                (id, label, node_type, source, created_at, decay_score, risk_score, rationale, url)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (id) DO UPDATE SET
                label=EXCLUDED.label, decay_score=EXCLUDED.decay_score,
                ingested_at=NOW()
            """,
            [
                n.get("id"), n.get("label"), n.get("type"), n.get("source"),
                n.get("created_at"), n.get("decay_score"), n.get("risk_score"),
                (n.get("rationale") or "")[:500], n.get("files", "")[:500],
            ]
        )

    for e in edges:
        execute(
            """
            INSERT INTO knowledge_edges (source_id, target_id, edge_type, weight, rationale)
            VALUES ($1,$2,$3,$4,$5)
            """,
            [e.get("source"), e.get("target"), e.get("type"),
             e.get("weight"), (e.get("rationale") or "")[:300]]
        )

    execute(
        "INSERT INTO ingest_runs (repos, node_count, edge_count, status) VALUES ($1,$2,$3,$4)",
        ["{" + ",".join(f'"{r}"' for r in repos) + "}", len(nodes), len(edges), "success"]
    )
    print(f"[DB] Saved {len(nodes)} nodes, {len(edges)} edges to PostgreSQL")


def get_audit_stats() -> dict:
    """Get aggregate stats from PostgreSQL audit log."""
    if not _enabled:
        return {}
    rows = execute("SELECT COUNT(*) as total, AVG(confidence) as avg_conf FROM audit_log")
    return rows[0] if rows else {}
