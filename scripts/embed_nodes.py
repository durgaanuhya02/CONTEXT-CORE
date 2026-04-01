"""
Embed all knowledge nodes using OpenAI text-embedding-3-small
and store in ChromaDB (local, zero setup).

Install:
    pip install chromadb openai

Run:
    python embed_nodes.py
"""

import json
import math
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("GRAPHRAG_API_KEY")
# Treat placeholder values as no key
if OPENAI_API_KEY and any(x in OPENAI_API_KEY for x in ("your_", "your-", "here", "placeholder", "example")):
    OPENAI_API_KEY = None
if OPENAI_API_KEY and len(OPENAI_API_KEY) < 20:
    OPENAI_API_KEY = None
NER_OUTPUT = Path(__file__).parent.parent.parent / "dataset" / "ner_output"
CHROMA_DIR = Path(__file__).parent.parent.parent / "dataset" / "chroma_db"
GRAPH_JSON = NER_OUTPUT / "knowledge_graph.json"

LAMBDA = 0.02  # decay rate — tuned for 2-4 year old enterprise data


def exponential_decay(created_at_iso: str) -> float:
    """
    confidence = e^(−λ × months_since_created)
    Returns value between 0.0 and 1.0.
    """
    try:
        created = datetime.fromisoformat(created_at_iso)
    except Exception:
        created = datetime(2022, 3, 14)  # default to dataset start

    months = (datetime.now() - created).days / 30.44
    score = math.exp(-LAMBDA * months)
    return round(max(0.05, min(1.0, score)), 4)


def build_node_text(node: dict) -> str:
    """Build a rich text representation of a node for embedding."""
    parts = [
        f"Entity: {node.get('label', node['id'])}",
        f"Type: {node.get('type', 'UNKNOWN')}",
        f"Source: {node.get('source', 'unknown')}",
    ]
    if node.get("files"):
        parts.append(f"Found in: {node['files']}")
    return " | ".join(parts)


def embed_with_openai(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


def embed_with_fallback(texts: list[str]) -> list[list[float]]:
    """
    Try OpenAI first. If no API key, generate deterministic
    pseudo-embeddings for local testing (not for production).
    """
    if OPENAI_API_KEY:
        print("  Using OpenAI text-embedding-3-small")
        return embed_with_openai(texts)

    print("  No API key found — using hash-based pseudo-embeddings (demo only)")
    import hashlib
    embeddings = []
    for text in texts:
        # 1536-dim pseudo-embedding from hash (same dim as text-embedding-3-small)
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
        import random
        rng = random.Random(seed)
        vec = [rng.gauss(0, 1) for _ in range(1536)]
        # Normalize
        norm = sum(x**2 for x in vec) ** 0.5
        vec = [x / norm for x in vec]
        embeddings.append(vec)
    return embeddings


def run():
    import chromadb

    if not GRAPH_JSON.exists():
        print(f"ERROR: {GRAPH_JSON} not found. Run build_graph.py first.")
        return

    print("Loading knowledge graph nodes...")
    graph = json.loads(GRAPH_JSON.read_text())
    nodes = graph["nodes"]
    print(f"  {len(nodes)} nodes to embed")

    # Build texts and metadata for each node
    texts = []
    metadatas = []
    ids = []

    # Source → approximate creation date mapping
    SOURCE_DATES = {
        "slack": "2022-03-14",
        "confluence": "2022-03-15",
        "github": "2023-04-08",
        "zoom": "2022-07-20",
        "domain_knowledge": "2022-01-01",
        "inferred": "2022-01-01",
        "unknown": "2022-01-01",
    }

    for node in nodes:
        nid = node["id"]
        source = node.get("source", "unknown")
        # Use node's own created_at if present, fall back to source default
        created_at = node.get("created_at") or SOURCE_DATES.get(source, "2022-01-01")
        decay = exponential_decay(created_at)

        text = build_node_text(node)
        texts.append(text)
        ids.append(nid)
        metadatas.append({
            "id": nid,
            "label": node.get("label", nid),
            "type": node.get("type", "OTHER"),
            "source": source,
            "files": node.get("files", ""),
            "decay_score": decay,
            "created_at": created_at,
            "risk_score": node.get("risk_score", 0.0),
            "degree": node.get("degree", 0),
        })

    print("Generating embeddings...")
    # Embed in batches of 50
    all_embeddings = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"  Batch {i // batch_size + 1}/{math.ceil(len(texts) / batch_size)} ({len(batch)} items)")
        embeddings = embed_with_fallback(batch)
        all_embeddings.extend(embeddings)

    print(f"Storing {len(all_embeddings)} embeddings in ChromaDB...")
    CHROMA_DIR.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Delete existing collection if present
    try:
        client.delete_collection("knowledge_nodes")
    except Exception:
        pass

    collection = client.create_collection(
        name="knowledge_nodes",
        metadata={"hnsw:space": "cosine"},
    )

    collection.add(
        ids=ids,
        embeddings=all_embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    print(f"ChromaDB collection 'knowledge_nodes': {collection.count()} items")
    print(f"Stored at: {CHROMA_DIR}")

    # Write decay scores back — use the computed value (from node's own created_at)
    decay_map = {m["id"]: m["decay_score"] for m in metadatas}
    for node in nodes:
        node["decay_score"] = decay_map.get(node["id"], node.get("decay_score", 0.75))
    GRAPH_JSON.write_text(json.dumps(graph, indent=2))
    print("Updated decay scores in knowledge_graph.json")

    print("\nSample decay scores (freshest first):")
    for m in sorted(metadatas, key=lambda x: -x["decay_score"])[:8]:
        print(f"  {m['label']:<35} decay={m['decay_score']}  created={m['created_at']}")


if __name__ == "__main__":
    run()
