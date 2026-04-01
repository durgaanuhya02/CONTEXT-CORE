"""Ingest router — trigger real-time GitHub data fetch and graph rebuild."""

import os
import sys
import subprocess
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

import store

router = APIRouter()

SCRIPT = Path(__file__).parent.parent.parent.parent / "contextcore" / "scripts" / "fetch_github.py"
ENV_FILE = Path(__file__).parent.parent / ".env"

_ingest_status = {"running": False, "last_run": None, "last_result": None, "error": None}


class IngestRequest(BaseModel):
    repos: list[str] | None = None  # override GITHUB_REPOS if provided
    github_token: str | None = None  # override GITHUB_TOKEN if provided


class IngestStatus(BaseModel):
    running: bool
    last_run: str | None
    last_result: dict | None
    error: str | None


def _run_fetch(repos: list[str] | None, token: str | None):
    _ingest_status["running"] = True
    _ingest_status["error"] = None
    try:
        env = os.environ.copy()
        if repos:
            env["GITHUB_REPOS"] = ",".join(repos)
        if token:
            env["GITHUB_TOKEN"] = token

        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if result.returncode == 0:
            # Reload graph into memory
            graph = store.reload_graph()
            from datetime import datetime
            _ingest_status["last_run"] = datetime.now().isoformat()
            _ingest_status["last_result"] = {
                "nodes": len(graph.get("nodes", [])),
                "edges": len(graph.get("edges", [])),
                "repos": graph.get("stats", {}).get("repos", []),
            }
            # Persist graph to PostgreSQL
            import db as database
            if database.is_enabled():
                database.save_graph(
                    graph.get("nodes", []),
                    graph.get("edges", []),
                    graph.get("stats", {}).get("repos", []),
                )
            # Index nodes in ChromaDB cloud for semantic search
            try:
                import chroma_store
                if chroma_store.is_enabled():
                    chroma_store.index_nodes(graph.get("nodes", []))
            except Exception as e:
                print(f"[Ingest] ChromaDB indexing error: {e}")
            print(f"[Ingest] ✓ Graph rebuilt: {_ingest_status['last_result']}")
        else:
            _ingest_status["error"] = result.stderr[-500:] if result.stderr else "Unknown error"
            print(f"[Ingest] ✗ Fetch failed: {_ingest_status['error']}")
    except subprocess.TimeoutExpired:
        _ingest_status["error"] = "Fetch timed out after 120s"
    except Exception as e:
        _ingest_status["error"] = str(e)
    finally:
        _ingest_status["running"] = False


@router.post("/github")
async def ingest_github(req: IngestRequest, background_tasks: BackgroundTasks):
    """Trigger a background GitHub data fetch and graph rebuild."""
    if _ingest_status["running"]:
        return {"status": "already_running", "message": "Ingestion already in progress"}
    background_tasks.add_task(_run_fetch, req.repos, req.github_token)
    return {"status": "started", "message": "GitHub ingestion started in background"}


@router.get("/status", response_model=IngestStatus)
def ingest_status():
    return IngestStatus(**_ingest_status)


@router.post("/github/sync")
def ingest_github_sync(req: IngestRequest):
    """Synchronous fetch — waits for completion (use for testing)."""
    if _ingest_status["running"]:
        return {"status": "already_running"}
    _run_fetch(req.repos, req.github_token)
    return {"status": "done", **(_ingest_status["last_result"] or {}), "error": _ingest_status["error"]}
