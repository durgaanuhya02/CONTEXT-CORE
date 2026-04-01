"""
Hybrid Retrieval Engine
-----------------------
1. Semantic search — finds top-K nodes via ChromaDB cosine similarity
2. Graph traversal — expands to connected nodes (reasoning chain)
3. LangChain + OpenAI — generates answer citing nodes with provenance
4. Confidence decay — exponential decay applied to every cited node
"""

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if ANTHROPIC_API_KEY and any(x in ANTHROPIC_API_KEY for x in ("your_", "your-", "here", "placeholder")):
    ANTHROPIC_API_KEY = None
if ANTHROPIC_API_KEY and len(ANTHROPIC_API_KEY) < 20:
    ANTHROPIC_API_KEY = None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("GRAPHRAG_API_KEY")
if OPENAI_API_KEY and any(x in OPENAI_API_KEY for x in ("your_", "your-", "here", "placeholder")):
    OPENAI_API_KEY = None
if OPENAI_API_KEY and len(OPENAI_API_KEY) < 20:
    OPENAI_API_KEY = None

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if GROQ_API_KEY and len(GROQ_API_KEY) < 20:
    GROQ_API_KEY = None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY and len(GEMINI_API_KEY) < 20:
    GEMINI_API_KEY = None

# Effective key availability — Groq fills the "Claude" slot, Gemini fills "GPT-4o" slot
_HAS_CLAUDE  = bool(ANTHROPIC_API_KEY)
_HAS_GPT4O   = bool(OPENAI_API_KEY)
_HAS_GROQ    = bool(GROQ_API_KEY)
_HAS_GEMINI  = bool(GEMINI_API_KEY)
CHROMA_DIR = Path(__file__).parent.parent.parent / "dataset" / "chroma_db"
GRAPH_JSON = Path(__file__).parent.parent.parent / "dataset" / "ner_output" / "knowledge_graph.json"

LAMBDA = 0.02  # decay rate — tuned for 2-4 year old enterprise data


# ── Decay formula ─────────────────────────────────────────────────────────────

def exponential_decay(created_at_iso: str) -> float:
    """confidence = e^(−λ × months_since_created)"""
    try:
        created = datetime.fromisoformat(created_at_iso)
    except Exception:
        created = datetime(2022, 3, 14)
    months = (datetime.now() - created).days / 30.44
    return round(max(0.05, min(1.0, math.exp(-LAMBDA * months))), 4)


def months_since(created_at_iso: str) -> float:
    try:
        created = datetime.fromisoformat(created_at_iso)
    except Exception:
        created = datetime(2022, 3, 14)
    return round((datetime.now() - created).days / 30.44, 1)


# ── Graph loader (cached) ─────────────────────────────────────────────────────

_graph_cache: dict | None = None


def load_graph() -> dict:
    global _graph_cache
    if _graph_cache is None and GRAPH_JSON.exists():
        data = json.loads(GRAPH_JSON.read_text())
        # Build adjacency: node_id → list of (neighbor_id, edge_type, rationale)
        adj: dict[str, list[dict]] = {}
        for edge in data["edges"]:
            src, tgt = edge["source"], edge["target"]
            adj.setdefault(src, []).append({
                "id": tgt,
                "edge_type": edge.get("type", "RELATED"),
                "rationale": edge.get("rationale", ""),
                "weight": edge.get("weight", 1.0),
            })
            # Undirected traversal
            adj.setdefault(tgt, []).append({
                "id": src,
                "edge_type": edge.get("type", "RELATED"),
                "rationale": edge.get("rationale", ""),
                "weight": edge.get("weight", 1.0),
            })
        node_map = {n["id"]: n for n in data["nodes"]}
        _graph_cache = {"nodes": node_map, "adj": adj, "edges": data["edges"]}
    return _graph_cache or {"nodes": {}, "adj": {}, "edges": []}


# ── Semantic search ───────────────────────────────────────────────────────────

def semantic_search(query: str, top_k: int = 5) -> list[dict]:
    """
    Semantic search via ChromaDB cloud, falls back to keyword matching.
    """
    try:
        import chroma_store
        if chroma_store.is_enabled():
            results = chroma_store.semantic_search(query, top_k)
            if results:
                # Enrich with full node data from graph
                graph = load_graph()
                node_map = graph["nodes"]
                for r in results:
                    full = node_map.get(r["id"], {})
                    r["months_old"] = months_since(full.get("created_at", r.get("created_at", "2022-01-01")))
                    r["files"] = full.get("files", "")
                return results
    except Exception as e:
        print(f"[Chroma] semantic_search error: {e}")
    return _keyword_fallback(query, top_k)


def _embed_query(query: str) -> list[float]:
    """Embed a query string using OpenAI or pseudo-embedding fallback."""
    if OPENAI_API_KEY:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=[query],
        )
        return response.data[0].embedding

    # Pseudo-embedding fallback
    import hashlib, random
    seed = int(hashlib.md5(query.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(1536)]
    norm = sum(x**2 for x in vec) ** 0.5
    return [x / norm for x in vec]


def _keyword_fallback(query: str, top_k: int) -> list[dict]:
    """Keyword-based node matching when ChromaDB is unavailable."""
    graph = load_graph()
    q = query.lower()

    # Extract meaningful search terms (3+ chars, skip stopwords)
    stopwords = {"what", "who", "why", "how", "did", "does", "the", "for",
                 "about", "with", "from", "that", "this", "have", "has",
                 "are", "was", "were", "will", "over", "before", "after",
                 "most", "more", "than", "and", "but", "not", "can", "its"}
    terms = [w.strip("?.,!") for w in q.split()
             if len(w.strip("?.,!")) >= 3 and w.strip("?.,!") not in stopwords]

    scored = []
    for nid, node in graph["nodes"].items():
        label = node.get("label", nid).lower()
        node_type = node.get("type", "").lower()
        # Score: label match + type match + id match
        score = 0
        for term in terms:
            if term in label:
                score += 2
            if term in nid.lower():
                score += 1
            if term in node_type:
                score += 0.5
        # Boost exact phrase matches
        for phrase in [q, q.replace("?", "").strip()]:
            if any(word in label for word in phrase.split() if len(word) > 4):
                score += 0.5

        if score > 0:
            decay = exponential_decay(node.get("created_at", "2022-01-01"))
            scored.append({
                "id": nid,
                "label": node.get("label", nid),
                "type": node.get("type", "OTHER"),
                "source": node.get("source", "unknown"),
                "files": node.get("files", ""),
                "similarity": round(min(1.0, score / 10), 4),
                "decay_score": decay,
                "created_at": node.get("created_at", "2022-01-01"),
                "months_old": months_since(node.get("created_at", "2022-01-01")),
                "risk_score": node.get("risk_score", 0.0),
                "retrieval_method": "keyword",
            })
    return sorted(scored, key=lambda x: -x["similarity"])[:top_k]


# ── Graph traversal ───────────────────────────────────────────────────────────

def graph_traversal(seed_node_ids: list[str], max_hops: int = 2, max_nodes: int = 15) -> list[dict]:
    """
    BFS from seed nodes, expanding to connected neighbors.
    Returns the reasoning chain — all nodes reachable within max_hops.
    """
    graph = load_graph()
    adj = graph["adj"]
    node_map = graph["nodes"]

    visited: dict[str, dict] = {}
    queue = [(nid, 0, "seed", "") for nid in seed_node_ids]

    while queue and len(visited) < max_nodes:
        nid, hop, edge_type, rationale = queue.pop(0)
        if nid in visited:
            continue

        node = node_map.get(nid, {"id": nid, "label": nid, "type": "UNKNOWN"})
        decay = exponential_decay(node.get("created_at", "2022-01-01"))

        visited[nid] = {
            "id": nid,
            "label": node.get("label", nid),
            "type": node.get("type", "OTHER"),
            "source": node.get("source", "unknown"),
            "files": node.get("files", ""),
            "decay_score": decay,
            "created_at": node.get("created_at", "2022-01-01"),
            "months_old": months_since(node.get("created_at", "2022-01-01")),
            "hop": hop,
            "edge_type": edge_type,
            "rationale": rationale,
            "retrieval_method": "graph_traversal" if hop > 0 else "semantic",
        }

        if hop < max_hops:
            for neighbor in adj.get(nid, []):
                if neighbor["id"] not in visited:
                    queue.append((
                        neighbor["id"],
                        hop + 1,
                        neighbor["edge_type"],
                        neighbor["rationale"],
                    ))

    return list(visited.values())


# ── Hybrid retrieval ──────────────────────────────────────────────────────────

def hybrid_retrieve(query: str, top_k: int = 5, max_hops: int = 2) -> list[dict]:
    """
    Full hybrid retrieval:
    1. Semantic search → top-K seed nodes
    2. Domain intent boost → inject known relevant nodes for common query patterns
    3. Graph traversal → expand reasoning chain
    Returns deduplicated, decay-weighted node list.
    """
    # Step 1: semantic search
    seed_nodes = semantic_search(query, top_k=top_k)
    seed_ids = [n["id"] for n in seed_nodes]

    # Step 2: domain intent boost — inject known anchors for common query patterns
    boosted_ids = _intent_boost(query)
    for bid in boosted_ids:
        if bid not in seed_ids:
            seed_ids.insert(0, bid)

    # Step 3: graph traversal from seeds
    chain_nodes = graph_traversal(seed_ids, max_hops=max_hops)

    # Merge: seed nodes take priority, graph nodes fill in
    merged: dict[str, dict] = {n["id"]: n for n in chain_nodes}
    for n in seed_nodes:
        merged[n["id"]] = {**merged.get(n["id"], {}), **n}

    # Sort: semantic seeds first, then by decay score
    result = sorted(
        merged.values(),
        key=lambda x: (x.get("hop", 99), -x.get("decay_score", 0))
    )
    return result


# Query intent → anchor node IDs built dynamically from the real graph
# These are populated at first use from actual node IDs in knowledge_graph.json

def _intent_boost(query: str) -> list[str]:
    """
    Dynamically boost query with relevant node IDs from the real graph.
    Matches query terms against actual node labels and IDs.
    """
    q = query.lower()
    graph = load_graph()
    node_map = graph["nodes"]

    boosted = []
    for nid, node in node_map.items():
        label = node.get("label", "").lower()
        # Match query words against node labels
        words = [w.strip("?.,!") for w in q.split() if len(w) > 3]
        if any(w in label or w in nid.lower() for w in words):
            boosted.append(nid)
        if len(boosted) >= 5:
            break
    return boosted


# ── Per-model system prompts ──────────────────────────────────────────────────

# Claude: analytical, reasoning-heavy, cites tradeoffs and decision history
SYSTEM_PROMPT_CLAUDE = """You are ContextCore, an institutional memory assistant.
Analyze the provided knowledge graph context and give a detailed, reasoning-focused answer that explains the decision rationale, who was involved, and what tradeoffs were considered.
Be analytical and cite specific sources. Write 4-6 sentences minimum. Explore the "why" behind decisions."""

# GPT-4o: concise, direct, lead with the key finding
SYSTEM_PROMPT_GPT4O = """You are ContextCore, an institutional memory assistant.
Give a concise, direct answer using the provided knowledge graph context.
Lead with the key finding, then briefly explain supporting evidence in 1-2 sentences.
Be clear and actionable. Do not over-explain."""

# Routing keywords — presence of any of these triggers Claude in Auto mode
_CLAUDE_KEYWORDS = [
    "why", "decision", "reasoning", "rationale", "chose", "choose", "tradeoff",
    "trade-off", "explain", "how did", "what led", "impact", "risk", "should we",
    "recommend", "strategy", "architecture", "design", "compare",
]


def _route_model(query: str, model: str) -> tuple[str, str]:
    """
    Determine effective model and routing label.
    Claude slot: Anthropic → Groq (llama-3.3-70b) as free fallback
    GPT-4o slot: OpenAI   → Gemini (gemini-1.5-flash) as free fallback
    Returns (effective_model, display_label).
    """
    def _best_claude_provider():
        if _HAS_CLAUDE:  return ("claude",  "claude-sonnet-4-20250514")
        if _HAS_GROQ:    return ("groq",    "llama-3.3-70b (Groq)")
        if _HAS_GEMINI:  return ("gemini",  "gemini-2.0-flash (Gemini)")
        return ("template", "Local Template (API unavailable)")

    def _best_gpt4o_provider():
        if _HAS_GPT4O:   return ("gpt4o",   "gpt-4o")
        if _HAS_GROQ:    return ("groq",    "llama-3.3-70b (Groq)")
        if _HAS_GEMINI:  return ("gemini",  "gemini-2.0-flash (Gemini)")
        return ("template", "Local Template (API unavailable)")

    if model == "claude":
        eff, label = _best_claude_provider()
        print(f"[ContextCore] Calling Claude API with model: {label}")
        return eff, label

    if model == "gpt4o":
        eff, label = _best_gpt4o_provider()
        print(f"[ContextCore] Calling GPT-4o API with model: {label}")
        return eff, label

    if model == "auto":
        q = query.lower()
        is_reasoning = any(kw in q for kw in _CLAUDE_KEYWORDS)
        reason = "reasoning keywords detected" if is_reasoning else "simple query detected"
        if is_reasoning:
            eff, label = _best_claude_provider()
            if eff != "template":
                print(f"[ContextCore] Auto mode: routed to Claude because {reason} → {label}")
                return eff, f"Auto → Claude ({label})"
        else:
            eff, label = _best_gpt4o_provider()
            if eff != "template":
                print(f"[ContextCore] Auto mode: routed to GPT-4o because {reason} → {label}")
                return eff, f"Auto → GPT-4o ({label})"
        # Both unavailable
        print(f"[ContextCore] Auto mode: no API keys — using local template")
        return "template", "Local Template (API unavailable)"

    # model == "local"
    print(f"[ContextCore] Local template mode — no API call")
    return "template", "Local Template"


def generate_answer(query: str, context_nodes: list[dict], model: str = "auto") -> dict[str, Any]:
    """
    Generate a cited answer. model: 'auto' | 'claude' | 'gpt4o' | 'local'
    """
    if not context_nodes:
        return {
            "answer": "No relevant knowledge nodes found for this query.",
            "cited_nodes": [],
            "overall_confidence": 0.0,
            "model_used": "none",
        }

    # Build context string from nodes
    context_parts = []
    for node in context_nodes[:10]:
        months = node.get("months_old", 0)
        decay = node.get("decay_score", 0.75)
        stale_flag = " ⚠️ POTENTIALLY STALE (>18 months)" if months > 18 else ""
        context_parts.append(
            f"- [{node['label']}] type={node['type']} "
            f"source={node['source']} "
            f"confidence={round(decay * 100)}%{stale_flag}"
            + (f" | {node['rationale']}" if node.get('rationale') else "")
        )
    context_str = "\n".join(context_parts)

    effective_model, display_label = _route_model(query, model)

    if effective_model == "claude":
        answer = _generate_with_claude(query, context_str)
        if answer is None:
            answer = _generate_template_answer(query, context_nodes)
            display_label = "Local Template (API unavailable)"
    elif effective_model == "gpt4o":
        answer = _generate_with_openai(query, context_str)
        if answer is None:
            answer = _generate_template_answer(query, context_nodes)
            display_label = "Local Template (API unavailable)"
    elif effective_model == "groq":
        # Groq fills the Claude slot — use analytical prompt for reasoning queries
        prompt = SYSTEM_PROMPT_CLAUDE if "claude" in display_label.lower() or "auto → claude" in display_label.lower() else SYSTEM_PROMPT_GPT4O
        answer = _generate_with_groq(query, context_str, prompt)
        if answer is None:
            answer = _generate_template_answer(query, context_nodes)
            display_label = "Local Template (API unavailable)"
    elif effective_model == "gemini":
        prompt = SYSTEM_PROMPT_GPT4O if "gpt" in display_label.lower() or "auto → gpt" in display_label.lower() else SYSTEM_PROMPT_CLAUDE
        answer = _generate_with_gemini(query, context_str, prompt)
        if answer is None:
            answer = _generate_template_answer(query, context_nodes)
            display_label = "Local Template (API unavailable)"
    else:
        answer = _generate_template_answer(query, context_nodes)

    # Dynamic confidence — weighted average of retrieved node decay scores
    seed_nodes = [n for n in context_nodes if n.get("hop", 99) == 0]
    graph_nodes = [n for n in context_nodes if n.get("hop", 99) > 0]

    if seed_nodes:
        seed_scores = [n["decay_score"] for n in seed_nodes]
        graph_scores = [n["decay_score"] for n in graph_nodes]
        all_weighted = seed_scores * 2 + graph_scores
        base_confidence = sum(all_weighted) / len(all_weighted) if all_weighted else 0.4
        corroboration = min(0.10, len(graph_nodes) * 0.012)
        sources = {n.get("source", "unknown") for n in context_nodes}
        diversity = min(0.06, (len(sources) - 1) * 0.025)
        q_lower = query.lower()
        known_terms = [
            "vscode", "react", "next.js", "typescript", "javascript",
            "contributor", "release", "pr", "issue", "dependency",
            "kubernetes", "istio", "python", "rust", "css",
        ]
        has_intent = any(t in q_lower for t in known_terms)
        intent_adj = 0.04 if has_intent else -0.06
        overall_confidence = round(min(0.92, max(0.22, base_confidence + corroboration + diversity + intent_adj)), 3)
    else:
        scores = [n["decay_score"] for n in context_nodes[:8]]
        overall_confidence = round(min(0.92, max(0.22, sum(scores) / max(len(scores), 1))), 3)

    return {
        "answer": answer,
        "model_used": display_label,
        "cited_nodes": [
            {
                "id": n["id"],
                "label": n["label"],
                "type": n["type"],
                "source": n["source"],
                "files": n.get("files", ""),
                "decay_score": n["decay_score"],
                "months_old": n.get("months_old", 0),
                "is_stale": n.get("months_old", 0) > 18,
                "retrieval_method": n.get("retrieval_method", "unknown"),
                "edge_type": n.get("edge_type", ""),
                "rationale": n.get("rationale", ""),
            }
            for n in context_nodes[:10]
        ],
        "overall_confidence": overall_confidence,
    }


def _generate_with_claude(query: str, context: str) -> str | None:
    """Generate answer using Anthropic Claude — analytical, reasoning-focused."""
    import anthropic
    print(f"[ContextCore] Calling Claude API with model: claude-sonnet-4-20250514")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=SYSTEM_PROMPT_CLAUDE,
            messages=[{"role": "user", "content": f"Context nodes:\n{context}\n\nQuestion: {query}"}],
        )
        return message.content[0].text
    except Exception as e:
        print(f"[ContextCore] Claude API error: {e} — falling back to template")
        return None


def _generate_with_openai(query: str, context: str) -> str | None:
    """Generate answer using GPT-4o — concise, direct, lead with key finding."""
    from openai import OpenAI
    print(f"[ContextCore] Calling GPT-4o API with model: gpt-4o")
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_GPT4O},
                {"role": "user", "content": f"Context nodes:\n{context}\n\nQuestion: {query}"},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ContextCore] GPT-4o API error: {e} — falling back to template")
        return None


def _generate_with_groq(query: str, context: str, prompt: str) -> str | None:
    """Generate answer using Groq (llama-3.3-70b) — free tier."""
    from groq import Groq
    print(f"[ContextCore] Calling Groq API with model: llama-3.3-70b-versatile")
    client = Groq(api_key=GROQ_API_KEY)
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Context nodes:\n{context}\n\nQuestion: {query}"},
            ],
            temperature=0.2,
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ContextCore] Groq API error: {e} — falling back to template")
        return None


def _generate_with_gemini(query: str, context: str, prompt: str) -> str | None:
    """Generate answer using Gemini 1.5 Flash — free tier."""
    print(f"[ContextCore] Calling Gemini API with model: gemini-2.0-flash")
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        full_prompt = f"{prompt}\n\nContext nodes:\n{context}\n\nQuestion: {query}"
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt,
        )
        return response.text
    except Exception as e:
        print(f"[ContextCore] Gemini API error: {e} — falling back to template")
        return None


def _generate_template_answer(query: str, nodes: list[dict]) -> str:
    """
    Template answer built from real graph nodes — no hardcoded AcmeCorp content.
    Summarizes the actual retrieved nodes with their labels, types, and rationale.
    """
    def cite(n: dict) -> str:
        decay = n.get("decay_score", 0.5)
        stale = " [stale]" if n.get("months_old", 0) > 18 else ""
        return f"[{n['label']} · {n.get('source','github')} · {round(decay*100)}% confidence{stale}]"

    if not nodes:
        return "No relevant knowledge nodes found for this query."

    top = nodes[:3]
    inline = ", ".join(cite(n) for n in top)

    # Build a natural language summary from the actual retrieved nodes
    node_summaries = []
    for n in nodes[:5]:
        label = n.get("label", n["id"])
        ntype = n.get("type", "")
        rationale = (n.get("rationale") or "")[:150]
        decay = round(n.get("decay_score", 0.5) * 100)
        stale = " ⚠ stale" if n.get("months_old", 0) > 18 else ""
        if rationale:
            node_summaries.append(f"- {label} ({ntype}): {rationale}{stale}")
        else:
            node_summaries.append(f"- {label} ({ntype}, {decay}% confidence{stale})")

    summary = "\n".join(node_summaries)

    # Identify the most relevant node for a lead sentence
    lead = nodes[0]
    lead_label = lead.get("label", lead["id"])
    lead_type = lead.get("type", "")
    lead_rationale = (lead.get("rationale") or "")[:200]

    if lead_rationale:
        intro = f"Based on the knowledge graph, the most relevant finding is **{lead_label}** ({lead_type}): {lead_rationale}"
    else:
        intro = f"Based on the knowledge graph, here are the most relevant nodes for your query:"

    return f"{intro}\n\n{summary}\n\nSources: {inline}"


# ── Main entry point ──────────────────────────────────────────────────────────

def answer_query(query: str, top_k: int = 5, max_hops: int = 2, model: str = "auto") -> dict[str, Any]:
    """
    Full pipeline: hybrid retrieval → answer generation with citations.
    This is called by the /query FastAPI endpoint.
    model: 'auto' | 'claude' | 'gpt4o' | 'local'
    """
    context_nodes = hybrid_retrieve(query, top_k=top_k, max_hops=max_hops)
    return generate_answer(query, context_nodes, model=model)
