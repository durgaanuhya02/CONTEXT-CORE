"""Risk router — departure risk, knowledge health, staleness. No DB."""

from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

import store

router = APIRouter()


class OwnerRisk(BaseModel):
    author_id: str
    email: str | None
    node_count: int
    risk_score: float
    risk_level: str
    domains: list[str]
    is_active: bool


class DomainRisk(BaseModel):
    domain: str
    owner_id: str
    risk_level: str
    risk_score: float
    reason: str
    node_count: int
    sole_owner: bool


class HealthScore(BaseModel):
    overall_score: float
    total_nodes: int
    avg_decay: float
    high_risk_domains: int
    sole_owner_domains: int
    stale_nodes: int
    owners: list[OwnerRisk]
    domains: list[DomainRisk]


class KnowledgeTransferChecklist(BaseModel):
    owner_id: str
    total_nodes: int
    checklist: list[dict]


class DepartureAlert(BaseModel):
    owner_id: str
    email: str | None
    risk_level: str
    risk_score: float
    node_count: int
    domains: list[str]
    critical_nodes: list[dict]
    recommended_actions: list[str]
    estimated_knowledge_loss_pct: float


@router.get("/health", response_model=HealthScore)
def get_health_score():
    h = store.get_health_score()
    return HealthScore(
        overall_score=h["overall_score"],
        total_nodes=h["total_nodes"],
        avg_decay=h["avg_decay"],
        high_risk_domains=h["high_risk_domains"],
        sole_owner_domains=h["sole_owner_domains"],
        stale_nodes=h["stale_nodes"],
        owners=[OwnerRisk(**o) for o in h["owners"]],
        domains=[DomainRisk(**d) for d in h["domains"]],
    )


@router.get("/owners", response_model=list[OwnerRisk])
def get_owner_risks():
    return [OwnerRisk(**o) for o in store.get_owner_risks()]


@router.get("/domains", response_model=list[DomainRisk])
def get_domain_risks():
    return [DomainRisk(**d) for d in store.get_domain_risks()]


@router.get("/transfer/{owner_id}", response_model=KnowledgeTransferChecklist)
def get_transfer_checklist(owner_id: str):
    nodes = store.get_nodes_by_owner(owner_id)
    checklist = [
        {
            "title": n.get("label", n["id"]),
            "description": (n.get("rationale") or "")[:200],
            "source": n.get("source", "unknown"),
            "file": {
                "slack": "slack_architecture_decisions.txt",
                "confluence": "confluence_adrs.txt",
                "github": "github_prs.txt",
                "zoom": "zoom_transcripts.txt",
            }.get(n.get("source", ""), "onboarding_docs.txt"),
            "decay_score": n.get("decay_score", 0.75),
            "action": (
                "Document immediately — high decay risk" if n.get("decay_score", 1) < 0.6
                else "Schedule knowledge transfer session" if n.get("decay_score", 1) < 0.8
                else "Review and validate still accurate"
            ),
            "priority": (
                "HIGH" if n.get("decay_score", 1) < 0.6
                else "MEDIUM" if n.get("decay_score", 1) < 0.8
                else "LOW"
            ),
        }
        for n in nodes[:20]
    ]
    return KnowledgeTransferChecklist(
        owner_id=owner_id,
        total_nodes=len(checklist),
        checklist=checklist,
    )


@router.get("/departure/{owner_id}", response_model=DepartureAlert)
def get_departure_alert(owner_id: str):
    nodes = store.get_nodes_by_owner(owner_id)
    all_nodes = store.get_nodes()
    total = max(len(all_nodes), 1)

    owner_node = store.get_node_map().get(owner_id, {})
    risk_score = float(owner_node.get("risk_score", 0.5))
    risk_level = "CRITICAL" if risk_score >= 0.9 else "HIGH" if risk_score >= 0.7 else "MEDIUM" if risk_score >= 0.4 else "LOW"
    email = f"{owner_id.replace('gh_', '')}@github.com"

    domains = [d["domain"] for d in store.get_domain_risks() if d["owner_id"] == owner_id]
    sole_domains = [d["domain"] for d in store.get_domain_risks() if d["owner_id"] == owner_id and d["sole_owner"]]

    critical_nodes = [
        {
            "title": n.get("label", n["id"]),
            "decay_score": n.get("decay_score", 0.75),
            "source_system": n.get("source", "unknown"),
            "months_old": n.get("months_old", 0.0),
        }
        for n in nodes[:8]
    ]

    knowledge_loss_pct = round(min(100.0, len(nodes) / total * 100), 1)

    actions = []
    if risk_level in ("CRITICAL", "HIGH"):
        actions.append(f"🚨 Initiate immediate knowledge transfer sessions with {owner_id}")
    for d in sole_domains[:2]:
        actions.append(f"📋 Document all architectural decisions for {d} before departure")
    stale_count = sum(1 for n in nodes if n.get("decay_score", 1) < 0.6)
    if stale_count:
        actions.append(f"⚠️ {stale_count} nodes have decay <60% — prioritize documentation now")
    actions += [
        "🎥 Record walkthrough videos for critical system components",
        "👥 Identify and onboard a backup owner for each sole-owner domain",
        "📝 Update runbooks and GOTCHAS.md with tribal knowledge",
    ]

    return DepartureAlert(
        owner_id=owner_id,
        email=email,
        risk_level=risk_level,
        risk_score=risk_score,
        node_count=len(nodes),
        domains=domains,
        critical_nodes=critical_nodes,
        recommended_actions=actions[:6],
        estimated_knowledge_loss_pct=knowledge_loss_pct,
    )


# ── Risk Copilot ──────────────────────────────────────────────────────────────

import os

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if ANTHROPIC_API_KEY and any(x in ANTHROPIC_API_KEY for x in ("your_", "your-", "here", "placeholder")):
    ANTHROPIC_API_KEY = None
if ANTHROPIC_API_KEY and len(ANTHROPIC_API_KEY) < 20:
    ANTHROPIC_API_KEY = None


class CopilotRequest(BaseModel):
    question: str


class CopilotResponse(BaseModel):
    answer: str
    disclaimer: str = "Based on knowledge graph analysis. Use alongside HR judgment."


def _build_graph_context() -> str:
    """Build a concise text summary of the knowledge graph for the copilot."""
    nodes = store.get_nodes()
    owner_risks = store.get_owner_risks()
    domain_risks = store.get_domain_risks()

    lines = ["=== Knowledge Graph Summary ==="]
    lines.append(f"Total nodes: {len(nodes)}")

    lines.append("\n--- Owner Risk Profiles ---")
    for o in owner_risks:
        if o["author_id"] == "unknown":
            continue
        lines.append(
            f"{o['author_id']} | risk={o['risk_level']} ({o['risk_score']:.2f}) | "
            f"nodes={o['node_count']} | domains={', '.join(o['domains'])}"
        )

    lines.append("\n--- Domain Risk Profiles ---")
    for d in domain_risks:
        lines.append(
            f"{d['domain']} | risk={d['risk_level']} | owner={d['owner_id']} | "
            f"sole_owner={d['sole_owner']} | nodes={d['node_count']} | reason: {d['reason']}"
        )

    lines.append("\n--- Critical Nodes (decay < 0.5) ---")
    critical = [n for n in nodes if n.get("decay_score", 1) < 0.5]
    for n in critical[:20]:
        owner = store.resolve_author(n["id"])
        lines.append(
            f"{n.get('label', n['id'])} | owner={owner} | "
            f"decay={n.get('decay_score', 0):.2f} | source={n.get('source', '?')}"
        )

    return "\n".join(lines)


_COPILOT_SYSTEM = """You are a Risk Copilot for ContextCore, an institutional memory intelligence platform.
You help engineering managers make workforce decisions using knowledge graph data.

Answer questions about:
- Departure impact (nodes at risk, domains affected, recovery time, recommended actions)
- Safe-to-remove rankings (LOW/MEDIUM/HIGH/CRITICAL risk per person with one-line reasoning)
- Knowledge transfer plans (which nodes to transfer, who to assign as backup, timeline)
- Revenue impact estimates (use $50K per critical node as baseline cost)

Be concise and structured. Use bullet points for lists. Always ground answers in the graph data provided.
Do not invent data not present in the context.
"""

_COPILOT_TEMPLATE_ANSWERS = {
    "safe": None,
    "departure": None,
    "transfer": None,
}


def _copilot_template(question: str) -> str:
    """Generate template answer from real graph data."""
    owner_risks = store.get_owner_risks()
    q = question.lower()

    if "safe" in q or ("remove" in q and "who" in q):
        lines = ["Based on the knowledge graph, here is the departure risk ranking:\n"]
        for o in sorted(owner_risks, key=lambda x: x["risk_score"]):
            if o["author_id"] == "unknown":
                continue
            domains = ", ".join(o["domains"][:2]) or "general"
            lines.append(f"• {o['author_id']} — {o['risk_level']} risk. Owns {o['node_count']} nodes across {domains}.")
        lines.append("\nRecommendation: Do not remove CRITICAL or HIGH risk contributors without a knowledge transfer plan.")
        return "\n".join(lines)

    lines = ["Based on the knowledge graph analysis:\n"]
    for o in owner_risks[:5]:
        if o["author_id"] == "unknown":
            continue
        lines.append(f"• {o['author_id']}: {o['risk_level']} risk ({o['node_count']} nodes, domains: {', '.join(o['domains'][:2])})")
    return "\n".join(lines)


@router.post("/copilot", response_model=CopilotResponse)
def risk_copilot(req: CopilotRequest):
    graph_context = _build_graph_context()

    # Use Groq for copilot responses
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key and len(groq_key) > 20:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "system", "content": _COPILOT_SYSTEM,
                }, {
                    "role": "user",
                    "content": f"Knowledge Graph Data:\n{graph_context}\n\nQuestion: {req.question}",
                }],
                max_tokens=800,
                temperature=0.2,
            )
            answer = response.choices[0].message.content
        except Exception as e:
            print(f"[Copilot] Groq error: {e}")
            answer = _copilot_template(req.question)
    else:
        answer = _copilot_template(req.question)

    return CopilotResponse(answer=answer)
