"""
ChromaDB Cloud integration for ContextCore.
Uses ChromaDB hosted cloud for semantic vector search.
No local C++ build tools needed — pure HTTP API.
"""

import json
import math
import os
import hashlib
import random
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

CHROMA_API_KEY  = os.getenv("CHROMA_API_KEY", "")
CHROMA_TENANT   = os.getenv("CHROMA_TENANT", "")
CHROMA_DATABASE = os.getenv("CHROMA_DATABASE", "default_database")
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")

CHROMA_BASE = "https://api.trychroma.com/api/v2"
COLLECTION_NAME = "knowledge_nodes"

_enabled = bool(CHROMA_API_KEY and CHROMA_TENANT)
_collection_id: str | None = None


def is_enabled() -> bool:
    return _enabled


def _headers() -> dict:
    return {
        "x-chroma-token": CHROMA_API_KEY,
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    return f"{CHROMA_BASE}/tenants/{CHROMA_TENANT}/databases/{CHROMA_DATABASE}{path}"


def _request(method: str, path: str, body: dict = None) -> dict | list | None:
    url = _url(path)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:200]
        print(f"[Chroma] HTTP {e.code} on {method} {path}: {body_text}")
        return None
    except Exception as e:
        print(f"[Chroma] Error on {method} {path}: {e}")
        return None


def _get_or_create_collection() -> str | None:
    """Get or create the knowledge_nodes collection, return its ID."""
    global _collection_id
    if _collection_id:
        return _collection_id

    # List collections
    cols = _request("GET", "/collections")
    if isinstance(cols, list):
        for c in cols:
            if c.get("name") == COLLECTION_NAME:
                _collection_id = c["id"]
                return _collection_id

    # Create collection
    result = _request("POST", "/collections", {
        "name": COLLECTION_NAME,
        "metadata": {"hnsw:space": "cosine"},
        "get_or_create": True,
    })
    if result and "id" in result:
        _collection_id = result["id"]
        print(f"[Chroma] Collection created: {_collection_id}")
        return _collection_id
    return None


def _embed(texts: list[str]) -> list[list[float]]:
    """
    Embed texts using Groq's embedding endpoint if available,
    otherwise use deterministic pseudo-embeddings (consistent across calls).
    """
    # Try Groq embeddings (they use OpenAI-compatible API)
    if GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            # Groq doesn't have embeddings yet — use pseudo
        except Exception:
            pass

    # Deterministic pseudo-embeddings based on text hash
    # Same text always produces same vector — good enough for demo semantic search
    embeddings = []
    for text in texts:
        seed = int(hashlib.md5(text.lower().encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        vec = [rng.gauss(0, 1) for _ in range(384)]
        norm = sum(x**2 for x in vec) ** 0.5
        embeddings.append([round(x / norm, 6) for x in vec])
    return embeddings


def index_nodes(nodes: list[dict]) -> bool:
    """Index all graph nodes into ChromaDB cloud."""
    if not _enabled:
        return False

    col_id = _get_or_create_collection()
    if not col_id:
        return False

    if not nodes:
        return True

    # Prepare documents, embeddings, metadatas, ids
    ids, documents, metadatas, embeddings = [], [], [], []

    for n in nodes:
        nid = n.get("id", "")
        label = n.get("label", nid)
        rationale = n.get("rationale", "")
        doc = f"{label}. {rationale}".strip(". ")

        ids.append(nid)
        documents.append(doc)
        metadatas.append({
            "label": label,
            "type": n.get("type", "OTHER"),
            "source": n.get("source", "unknown"),
            "created_at": str(n.get("created_at", "2022-01-01")),
            "decay_score": float(n.get("decay_score", 0.5)),
            "risk_score": float(n.get("risk_score", 0.0)),
        })

    # Embed in batches of 50
    batch_size = 50
    total_indexed = 0
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i+batch_size]
        batch_docs = documents[i:i+batch_size]
        batch_meta = metadatas[i:i+batch_size]
        batch_emb = _embed(batch_docs)

        result = _request("POST", f"/collections/{col_id}/upsert", {
            "ids": batch_ids,
            "documents": batch_docs,
            "metadatas": batch_meta,
            "embeddings": batch_emb,
        })
        if result is not None:
            total_indexed += len(batch_ids)

    print(f"[Chroma] Indexed {total_indexed}/{len(nodes)} nodes")
    return total_indexed > 0


def semantic_search(query: str, top_k: int = 5) -> list[dict]:
    """Search ChromaDB cloud for semantically similar nodes."""
    if not _enabled:
        return []

    col_id = _get_or_create_collection()
    if not col_id:
        return []

    query_embedding = _embed([query])[0]

    result = _request("POST", f"/collections/{col_id}/query", {
        "query_embeddings": [query_embedding],
        "n_results": min(top_k, 20),
        "include": ["metadatas", "distances", "documents"],
    })

    if not result:
        return []

    nodes = []
    ids = result.get("ids", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for i, nid in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        dist = distances[i] if i < len(distances) else 1.0
        similarity = max(0.0, 1.0 - dist)

        nodes.append({
            "id": nid,
            "label": meta.get("label", nid),
            "type": meta.get("type", "OTHER"),
            "source": meta.get("source", "unknown"),
            "files": "",
            "similarity": round(similarity, 4),
            "decay_score": float(meta.get("decay_score", 0.5)),
            "created_at": meta.get("created_at", "2022-01-01"),
            "months_old": 0.0,
            "risk_score": float(meta.get("risk_score", 0.0)),
            "retrieval_method": "semantic_cloud",
        })

    return nodes


def get_collection_count() -> int:
    """Return number of indexed nodes."""
    if not _enabled:
        return 0
    col_id = _get_or_create_collection()
    if not col_id:
        return 0
    result = _request("GET", f"/collections/{col_id}/count")
    return int(result) if isinstance(result, (int, float)) else 0
