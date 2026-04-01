const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SourceNode {
  id: string;
  title: string;
  source_system: string;
  source_file: string;
  author_id: string;
  decay_score: number;
  months_old: number;
  is_stale: boolean;
  retrieval_method: string;
  edge_type: string;
  rationale: string;
}

export interface QueryResponse {
  answer: string;
  confidence: number;
  method: string;
  model_used: string;
  sources: SourceNode[];
  query_id: number;
  duration_ms: number;
}

export interface DomainRisk {
  domain: string;
  owner_id: string;
  risk_level: string;
  risk_score: number;
  reason: string;
  node_count: number;
  sole_owner: boolean;
}

export interface OwnerRisk {
  author_id: string;
  email: string | null;
  node_count: number;
  risk_score: number;
  risk_level: string;
  domains: string[];
  is_active: boolean;
}

export interface HealthScore {
  overall_score: number;
  total_nodes: number;
  avg_decay: number;
  high_risk_domains: number;
  sole_owner_domains: number;
  stale_nodes: number;
  owners: OwnerRisk[];
  domains: DomainRisk[];
}

export interface GraphNode {
  id: string;
  title: string;
  description: string | null;
  source_system: string;
  author_id: string;
  decay_score: number;
  community_id: string | null;
  color: string;
  size: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string | null;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface AuditEntry {
  id: number;
  query_text: string;
  answer: string | null;
  source_nodes: string[];
  source_files: string[];
  confidence: number | null;
  query_method: string;
  user_id: string;
  queried_at: string;
}

export interface AuditSummary {
  total_queries: number;
  avg_confidence: number;
  top_sources: { file: string; count: number }[];
  entries: AuditEntry[];
  source?: string;
}

export interface DepartureAlert {
  owner_id: string;
  email: string | null;
  risk_level: string;
  risk_score: number;
  node_count: number;
  domains: string[];
  critical_nodes: {
    title: string;
    decay_score: number;
    source_system: string;
    months_old: number;
  }[];
  recommended_actions: string[];
  estimated_knowledge_loss_pct: number;
}

export async function getDepartureAlert(ownerId: string): Promise<DepartureAlert> {
  const res = await fetch(`${BASE}/risk/departure/${ownerId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function queryKnowledge(question: string, method = "local", model = "auto"): Promise<QueryResponse> {
  const res = await fetch(`${BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, method, model }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getHealthScore(): Promise<HealthScore> {
  const res = await fetch(`${BASE}/risk/health`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getGraphData(): Promise<GraphData> {
  const res = await fetch(`${BASE}/graph`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAuditLog(): Promise<AuditSummary> {
  const res = await fetch(`${BASE}/audit-log`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getTransferChecklist(ownerId: string) {
  const res = await fetch(`${BASE}/risk/transfer/${ownerId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface CopilotResponse {
  answer: string;
  disclaimer: string;
}

export async function askRiskCopilot(question: string): Promise<CopilotResponse> {
  const res = await fetch(`${BASE}/risk/copilot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
