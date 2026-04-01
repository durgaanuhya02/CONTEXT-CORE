"""Compliance router — regulatory tagging, coverage gaps, audit chain. No DB."""

from fastapi import APIRouter
from pydantic import BaseModel

import store

router = APIRouter()


class RegulatoryTag(BaseModel):
    node_id: str
    node_title: str
    framework: str
    rationale: str
    tagged_at: str


class CoverageGap(BaseModel):
    topic: str
    query_count: int
    node_count: int
    gap_score: float
    last_queried: str


class AuditChainEntry(BaseModel):
    id: int
    query_text: str
    queried_at: str
    entry_hash: str | None
    prev_hash: str | None
    chain_valid: bool


@router.post("/tag/auto")
def auto_tag_nodes():
    tags = store.get_regulatory_tags()
    return {"tagged": len(tags), "message": "Regulatory auto-tagging complete (derived from graph)"}


@router.get("/tags", response_model=list[RegulatoryTag])
def get_regulatory_tags(framework: str | None = None):
    return [RegulatoryTag(**t) for t in store.get_regulatory_tags(framework)]


@router.get("/tags/summary")
def get_tags_summary():
    return store.get_tag_summary()


@router.get("/gaps", response_model=list[CoverageGap])
def get_coverage_gaps():
    return [CoverageGap(**g) for g in store.get_coverage_gaps()]


@router.get("/audit-chain", response_model=list[AuditChainEntry])
def verify_audit_chain():
    return [
        AuditChainEntry(
            id=e["id"],
            query_text=e["query_text"],
            queried_at=e.get("queried_at", ""),
            entry_hash=e.get("entry_hash"),
            prev_hash=e.get("prev_hash"),
            chain_valid=e.get("chain_valid", False),
        )
        for e in store.verify_audit_chain()
    ]


@router.get("/audit-chain/status")
def audit_chain_status():
    chain = store.verify_audit_chain()
    total = len(chain)
    broken = sum(1 for e in chain if not e.get("chain_valid", True))
    return {
        "total_entries": total,
        "valid_entries": total - broken,
        "broken_entries": broken,
        "chain_intact": broken == 0,
        "compliance_status": "PASS" if broken == 0 else "FAIL — potential tampering detected",
    }
