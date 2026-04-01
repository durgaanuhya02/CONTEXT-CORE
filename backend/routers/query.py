"""Query router — hybrid retrieval + answer generation with provenance."""

import time
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import store
import db as database
from retrieval import answer_query

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    method: Literal["local", "global", "drift"] = "local"
    model: Literal["auto", "claude", "gpt4o", "local"] = "auto"
    top_k: int = 5
    max_hops: int = 2


class SourceNode(BaseModel):
    id: str
    title: str
    source_system: str
    source_file: str
    author_id: str
    decay_score: float
    months_old: float
    is_stale: bool
    retrieval_method: str
    edge_type: str
    rationale: str


class QueryResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    answer: str
    confidence: float
    method: str
    model_used: str
    sources: list[SourceNode]
    query_id: int
    duration_ms: int


@router.post("", response_model=QueryResponse)
async def query_knowledge(req: QueryRequest):
    start = time.time()

    result = await run_in_threadpool(
        answer_query, req.question, req.top_k, req.max_hops, req.model
    )

    answer = result["answer"]
    cited_nodes = result["cited_nodes"]
    overall_confidence = result["overall_confidence"]
    model_used = result.get("model_used", "template")

    sources = [
        SourceNode(
            id=n["id"],
            title=n["label"],
            source_system=n.get("source", "unknown"),
            source_file=_source_file(n.get("source", "")),
            author_id=store.resolve_author(n["id"]),
            decay_score=n["decay_score"],
            months_old=n.get("months_old", 0.0),
            is_stale=n.get("is_stale", False),
            retrieval_method=n.get("retrieval_method", "hybrid"),
            edge_type=n.get("edge_type", ""),
            rationale=n.get("rationale", ""),
        )
        for n in cited_nodes
    ]

    duration_ms = int((time.time() - start) * 1000)

    # Append to in-memory audit log
    query_id = store.append_audit({
        "query_text": req.question,
        "answer": answer[:2000],
        "source_nodes": [s.title for s in sources],
        "source_files": list({s.source_file for s in sources}),
        "confidence": overall_confidence,
        "query_method": req.method,
        "model_used": model_used,
        "user_id": "demo_user",
        "queried_at": datetime.now().isoformat(),
    })

    # Also persist to PostgreSQL if available
    if database.is_enabled():
        audit_entry = store.get_audit_log(1)
        if audit_entry:
            database.save_audit_entry(audit_entry[0])

    # Track coverage gaps
    store.record_gap(req.question, len(sources))

    return QueryResponse(
        answer=answer,
        confidence=overall_confidence,
        method=req.method,
        model_used=model_used,
        sources=sources,
        query_id=query_id,
        duration_ms=duration_ms,
    )


def _source_file(source: str) -> str:
    return {
        "slack": "slack_architecture_decisions.txt",
        "confluence": "confluence_adrs.txt",
        "github": "github_prs.txt",
        "zoom": "zoom_transcripts.txt",
    }.get(source, "onboarding_docs.txt")
