"""
ContextCore in-memory store — no database required.

Loads everything from dataset/ner_output/knowledge_graph.json at startup.
"""

import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

GRAPH_JSON = Path(__file__).parent.parent.parent / "dataset" / "ner_output" / "knowledge_graph.json"
LAMBDA = 0.02

# ── In-process state (no DB) ──────────────────────────────────────────────────
_audit_log: list[dict] = []          # query history
_coverage_gaps: dict[str, dict] = {} # topic → gap record

# ── Graph data (loaded once) ──────────────────────────────────────────────────
_graph: dict | None = None


def _load() -> dict:
    global _graph
    if _graph is None:
        if not GRAPH_JSON.exists():
            _graph = {"nodes": [], "edges": [], "stats": {}}
        else:
            _graph = json.loads(GRAPH_JSON.read_text())
    return _graph


def reload_graph() -> dict:
    """Force reload the graph from disk (called after GitHub ingestion)."""
    global _graph
    _graph = None
    return _load()


def get_nodes() -> list[dict]:
    return _load()["nodes"]


def get_edges() -> list[dict]:
    return _load()["edges"]


def get_node_map() -> dict[str, dict]:
    return {n["id"]: n for n in get_nodes()}


# ── Ownership index (legacy synthetic data — kept for backward compat) ────────
# These are only used as fallback when no OWNS edges exist in the graph.
# With real GitHub data, get_owner_risks() and get_domain_risks() use OWNS edges directly.

_AUTHOR_MAP: dict[str, str] = {}  # cleared — dynamic resolution via OWNS edges

_OWNER_META: dict[str, dict] = {}  # cleared — dynamic from PERSON nodes

_DOMAIN_RISKS: list[dict] = []  # cleared — dynamic from PROJECT nodes + OWNS edges


def resolve_author(node_id: str) -> str:
    """Resolve a node ID to its owner. Works for both synthetic and GitHub data."""
    nid = node_id.lower()
    # Static map for synthetic data
    for key, author in _AUTHOR_MAP.items():
        if key.lower() == nid or key.lower() in nid:
            return author
    # Dynamic: for GitHub nodes, find OWNS edges pointing to this node
    for e in get_edges():
        if e.get("type") == "OWNS" and e.get("target", "").lower() == nid:
            return e["source"]
    return "unknown"


def get_nodes_by_owner(owner_id: str) -> list[dict]:
    """Return all nodes owned by a given author, sorted by decay ascending."""
    nodes = []
    owned_ids = {e["target"] for e in get_edges()
                 if e.get("type") == "OWNS" and e.get("source") == owner_id}
    node_map = get_node_map()
    for nid in owned_ids:
        if nid in node_map:
            nodes.append(node_map[nid])
    # Also check static map
    for n in get_nodes():
        author = n.get("author") or _AUTHOR_MAP.get(n["id"], "unknown")
        if author == owner_id and n not in nodes:
            nodes.append(n)
    return sorted(nodes, key=lambda x: x.get("decay_score", 0.5))


def get_owner_node_counts() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    # Count via OWNS edges (works for GitHub data)
    for e in get_edges():
        if e.get("type") == "OWNS":
            counts[e["source"]] += 1
    # Fallback: static map for synthetic data
    if not counts:
        for n in get_nodes():
            author = n.get("author") or resolve_author(n["id"])
            counts[author] += 1
    return dict(counts)


def get_domain_risks() -> list[dict]:
    """Build domain risks dynamically from graph data."""
    counts = get_owner_node_counts()
    node_map = get_node_map()

    # Find all PROJECT nodes and their owners via OWNS edges
    project_owners: dict[str, list[str]] = defaultdict(list)
    for e in get_edges():
        if e.get("type") == "OWNS":
            tgt = e["target"]
            if tgt in node_map and node_map[tgt].get("type") == "PROJECT":
                project_owners[tgt].append(e["source"])

    # If no GitHub data, fall back to static
    if not project_owners:
        result = []
        for d in _DOMAIN_RISKS:
            result.append({**d, "node_count": counts.get(d["owner_id"], 0)})
        return result

    result = []
    for proj_id, owners in project_owners.items():
        proj = node_map[proj_id]
        primary_owner = owners[0] if owners else "unknown"
        owner_node = node_map.get(primary_owner, {})
        risk_score = owner_node.get("risk_score", 0.5)
        sole = len(owners) == 1
        result.append({
            "domain": proj.get("label", proj_id),
            "owner_id": primary_owner,
            "risk_level": "CRITICAL" if risk_score >= 0.9 else "HIGH" if risk_score >= 0.7 else "MEDIUM" if risk_score >= 0.4 else "LOW",
            "risk_score": risk_score,
            "reason": f"{owner_node.get('label', primary_owner)} owns {proj.get('label', proj_id)}. {'Sole owner — single point of failure.' if sole else f'{len(owners)} contributors.'}",
            "node_count": counts.get(primary_owner, 0),
            "sole_owner": sole,
        })
    return sorted(result, key=lambda x: -x["risk_score"])[:6]


def get_owner_risks() -> list[dict]:
    """Build owner risks dynamically from graph data."""
    counts = get_owner_node_counts()
    node_map = get_node_map()

    # Find all PERSON nodes
    persons = [n for n in get_nodes() if n.get("type") == "PERSON"]

    # If no GitHub persons, fall back to static
    if not persons:
        result = []
        for author_id, meta in _OWNER_META.items():
            rs = meta["risk_score"]
            result.append({
                "author_id": author_id,
                "email": meta["email"],
                "role": meta.get("role", ""),
                "node_count": counts.get(author_id, 0),
                "risk_score": rs,
                "risk_level": "CRITICAL" if rs >= 0.9 else "HIGH" if rs >= 0.7 else "MEDIUM" if rs >= 0.4 else "LOW",
                "domains": [d["domain"] for d in _DOMAIN_RISKS if d["owner_id"] == author_id],
                "is_active": True,
            })
        return sorted(result, key=lambda x: -x["risk_score"])

    result = []
    for person in persons:
        pid = person["id"]
        rs = person.get("risk_score", 0.3)
        owned = [e["target"] for e in get_edges()
                 if e.get("type") == "OWNS" and e["source"] == pid]
        domains = [node_map[t].get("label", t) for t in owned
                   if t in node_map and node_map[t].get("type") == "PROJECT"]
        result.append({
            "author_id": pid,
            "email": person.get("extra", {}).get("github_login", pid) + "@github.com"
                     if isinstance(person.get("extra"), dict) else f"{pid}@github.com",
            "role": "Contributor",
            "node_count": counts.get(pid, 0),
            "risk_score": rs,
            "risk_level": "CRITICAL" if rs >= 0.9 else "HIGH" if rs >= 0.7 else "MEDIUM" if rs >= 0.4 else "LOW",
            "domains": domains[:3],
            "is_active": True,
        })
    return sorted(result, key=lambda x: -x["risk_score"])[:8]


def get_health_score() -> dict:
    nodes = get_nodes()
    total = len(nodes)
    stale = sum(1 for n in nodes if n.get("decay_score", 1.0) < 0.5)
    avg_decay = round(sum(n.get("decay_score", 0.75) for n in nodes) / max(total, 1), 3)
    domains = get_domain_risks()
    high_risk = sum(1 for d in domains if d["risk_level"] in ("HIGH", "CRITICAL"))
    sole_owner = sum(1 for d in domains if d["sole_owner"])
    # Penalty: high-risk domains and sole-owner domains matter most; stale nodes capped
    penalty = (high_risk * 10) + (sole_owner * 8) + min(stale, 10) * 1
    overall = max(0, min(100, round(100 - penalty, 1)))
    return {
        "overall_score": overall,
        "total_nodes": total,
        "avg_decay": avg_decay,
        "high_risk_domains": high_risk,
        "sole_owner_domains": sole_owner,
        "stale_nodes": stale,
        "owners": get_owner_risks(),
        "domains": domains,
    }


# ── Audit log (in-memory) ─────────────────────────────────────────────────────

def append_audit(entry: dict) -> int:
    entry_id = len(_audit_log) + 1
    prev_hash = _audit_log[-1]["entry_hash"] if _audit_log else "GENESIS"
    payload = json.dumps({
        "id": entry_id,
        "query": entry["query_text"],
        "answer": (entry.get("answer") or "")[:500],
        "at": entry.get("queried_at", ""),
        "prev": prev_hash,
    }, sort_keys=True)
    entry_hash = hashlib.sha256(payload.encode()).hexdigest()
    _audit_log.append({
        **entry,
        "id": entry_id,
        "entry_hash": entry_hash,
        "prev_hash": prev_hash,
        "queried_at": entry.get("queried_at", datetime.now().isoformat()),
    })
    return entry_id


def get_audit_log(limit: int = 20) -> list[dict]:
    return list(reversed(_audit_log))[:limit]


def verify_audit_chain() -> list[dict]:
    result = []
    for entry in _audit_log:
        prev_hash = entry.get("prev_hash", "GENESIS")
        payload = json.dumps({
            "id": entry["id"],
            "query": entry["query_text"],
            "answer": (entry.get("answer") or "")[:500],
            "at": entry.get("queried_at", ""),
            "prev": prev_hash,
        }, sort_keys=True)
        expected = hashlib.sha256(payload.encode()).hexdigest()
        result.append({
            **entry,
            "chain_valid": expected == entry.get("entry_hash"),
        })
    return result


# ── Coverage gaps (in-memory) ─────────────────────────────────────────────────

_KNOWN_TOPICS = [
    "typescript", "javascript", "python", "rust", "react", "vscode",
    "contributor", "release", "dependency", "security", "performance",
    "api", "testing", "documentation", "deployment", "ci", "cd",
    "kubernetes", "docker", "github", "open source", "license",
]


def record_gap(query_text: str, source_count: int):
    q = query_text.lower()
    topics = [t for t in _KNOWN_TOPICS if t in q]
    if not topics:
        words = [w.strip("?.,!") for w in q.split() if len(w) > 4]
        topics = [" ".join(words[:2])] if words else ["general"]

    node_map = get_node_map()
    for topic in topics[:3]:
        node_count = sum(1 for n in node_map.values()
                         if topic in (n.get("label") or "").lower()
                         or topic in (n.get("id") or "").lower())
        gap_score = round(max(0.0, 1.0 - node_count * 0.15), 3)
        if topic in _coverage_gaps:
            _coverage_gaps[topic]["query_count"] += 1
            _coverage_gaps[topic]["gap_score"] = gap_score
            _coverage_gaps[topic]["last_queried"] = datetime.now().isoformat()
        else:
            _coverage_gaps[topic] = {
                "topic": topic,
                "query_count": 1,
                "node_count": node_count,
                "gap_score": gap_score,
                "first_queried": datetime.now().isoformat(),
                "last_queried": datetime.now().isoformat(),
            }


def get_coverage_gaps() -> list[dict]:
    return sorted(_coverage_gaps.values(), key=lambda x: -x["gap_score"])[:20]


# ── Regulatory tagging (derived from graph, no DB) ────────────────────────────

_REG_KEYWORDS = {
    "SOX":       ["financial", "audit", "transaction", "revenue", "reporting", "release", "versioning"],
    "GDPR":      ["personal data", "user data", "email", "privacy", "consent", "data retention", "pii", "telemetry"],
    "HIPAA":     ["health", "medical", "patient", "clinical", "phi", "healthcare"],
    "EU_AI_ACT": ["ai", "ml", "model", "recommendation", "automated", "algorithm", "prediction", "llm", "copilot"],
    "ISO_42001": ["ai governance", "responsible ai", "explainability", "transparency", "ai audit", "open source", "license"],
}


def get_regulatory_tags(framework: str | None = None) -> list[dict]:
    tags = []
    for node in get_nodes():
        combined = f"{node.get('label', '')} {node.get('id', '')}".lower()
        for fw, keywords in _REG_KEYWORDS.items():
            if framework and fw != framework:
                continue
            matched = [kw for kw in keywords if kw in combined]
            if matched:
                tags.append({
                    "node_id": node["id"],
                    "node_title": node.get("label", node["id"]),
                    "framework": fw,
                    "rationale": f"Matched: {', '.join(matched[:3])}",
                    "tagged_at": datetime.now().isoformat(),
                })
    return tags


def get_tag_summary() -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    for tag in get_regulatory_tags():
        counts[tag["framework"]] += 1
    return [{"framework": fw, "node_count": c} for fw, c in sorted(counts.items(), key=lambda x: -x[1])]
