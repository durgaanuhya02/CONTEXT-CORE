"""Audit log router — in-memory + PostgreSQL persistent query history."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

import store
import db as database

router = APIRouter()


class AuditEntry(BaseModel):
    id: int
    query_text: str
    answer: str | None
    source_nodes: list[str]
    source_files: list[str]
    confidence: float | None
    query_method: str
    user_id: str
    queried_at: str


class AuditSummary(BaseModel):
    total_queries: int
    avg_confidence: float
    top_sources: list[dict]
    entries: list[AuditEntry]
    source: str  # "memory" or "postgresql"


@router.get("", response_model=AuditSummary)
def get_audit_log(limit: int = Query(default=20, le=100)):
    # Prefer PostgreSQL if available — it persists across restarts
    if database.is_enabled():
        db_entries = database.get_audit_log(limit)
        if db_entries:
            entries = [
                AuditEntry(
                    id=int(e.get("id", 0)),
                    query_text=e.get("query_text", ""),
                    answer=e.get("answer"),
                    source_nodes=e.get("source_nodes") or [],
                    source_files=e.get("source_files") or [],
                    confidence=float(e["confidence"]) if e.get("confidence") else None,
                    query_method=e.get("query_method", "local"),
                    user_id=e.get("user_id", "demo_user"),
                    queried_at=str(e.get("queried_at", "")),
                )
                for e in db_entries
            ]
            stats = database.get_audit_stats()
            return AuditSummary(
                total_queries=int(stats.get("total", 0)) if stats else len(entries),
                avg_confidence=float(stats.get("avg_conf", 0) or 0) if stats else 0.0,
                top_sources=[],
                entries=entries,
                source="postgresql",
            )

    # Fallback to in-memory
    entries_raw = store.get_audit_log(limit)
    entries = [
        AuditEntry(
            id=e["id"],
            query_text=e["query_text"],
            answer=e.get("answer"),
            source_nodes=e.get("source_nodes", []),
            source_files=e.get("source_files", []),
            confidence=e.get("confidence"),
            query_method=e.get("query_method", "local"),
            user_id=e.get("user_id", "demo_user"),
            queried_at=e.get("queried_at", ""),
        )
        for e in entries_raw
    ]
    all_entries = store.get_audit_log(1000)
    confs = [e["confidence"] for e in all_entries if e.get("confidence") is not None]
    avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.0
    file_counts: dict[str, int] = {}
    for e in all_entries:
        for f in e.get("source_files", []):
            file_counts[f] = file_counts.get(f, 0) + 1
    top_sources = sorted(
        [{"file": k, "count": v} for k, v in file_counts.items()],
        key=lambda x: -x["count"]
    )[:5]
    return AuditSummary(
        total_queries=len(all_entries),
        avg_confidence=avg_conf,
        top_sources=top_sources,
        entries=entries,
        source="memory",
    )
