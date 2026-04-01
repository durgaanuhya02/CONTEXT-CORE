"use client";
import { useEffect, useRef, useState } from "react";
import { getHealthScore, getTransferChecklist, askRiskCopilot, HealthScore } from "@/lib/api";

const RISK_COLORS: Record<string, string> = {
  CRITICAL: "text-red-400 bg-red-900/30 border-red-800",
  HIGH: "text-orange-400 bg-orange-900/30 border-orange-800",
  MEDIUM: "text-yellow-400 bg-yellow-900/30 border-yellow-800",
  LOW: "text-green-400 bg-green-900/30 border-green-800",
};

const RISK_BAR: Record<string, string> = {
  CRITICAL: "bg-red-500",
  HIGH: "bg-orange-500",
  MEDIUM: "bg-yellow-500",
  LOW: "bg-green-500",
};

const COPILOT_STARTERS = [
  "Who is safe to remove?",
  "Simulate David Kim departure",
  "Reduce Alice Chen risk",
];

interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

export default function RiskDashboard() {
  const [health, setHealth] = useState<HealthScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [checklist, setChecklist] = useState<any>(null);
  const [checklistOwner, setChecklistOwner] = useState<string | null>(null);

  // Copilot state
  const [copilotMessages, setCopilotMessages] = useState<CopilotMessage[]>([]);
  const [copilotInput, setCopilotInput] = useState("");
  const [copilotLoading, setCopilotLoading] = useState(false);
  const copilotBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getHealthScore()
      .then(setHealth)
      .catch(() => setHealth(getMockHealth()))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    copilotBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [copilotMessages]);

  async function showChecklist(ownerId: string) {
    setChecklistOwner(ownerId);
    try {
      const data = await getTransferChecklist(ownerId);
      setChecklist(data);
    } catch {
      setChecklist(getMockChecklist(ownerId));
    }
  }

  async function sendCopilot(question?: string) {
    const q = question || copilotInput.trim();
    if (!q) return;
    setCopilotInput("");
    setCopilotMessages((m) => [...m, { role: "user", content: q }]);
    setCopilotLoading(true);
    try {
      const res = await askRiskCopilot(q);
      setCopilotMessages((m) => [...m, { role: "assistant", content: res.answer }]);
    } catch {
      setCopilotMessages((m) => [...m, {
        role: "assistant",
        content: "Could not reach the Risk Copilot. Is the backend running?",
      }]);
    } finally {
      setCopilotLoading(false);
    }
  }

  if (loading) return <div className="p-8 text-slate-500 text-sm">Loading risk data...</div>;
  if (!health) return null;

  const scoreColor = health.overall_score >= 70 ? "text-green-400" : health.overall_score >= 50 ? "text-yellow-400" : "text-red-400";

  return (
    <div className="flex h-full max-h-full overflow-hidden">
      {/* Left: main risk panels */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 min-w-0">
        {/* Health Score Banner */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="col-span-2 md:col-span-1 bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col items-center justify-center">
            <p className="text-xs text-slate-500 mb-1">Knowledge Health</p>
            <p className={`text-4xl font-bold ${scoreColor}`}>{health.overall_score}</p>
            <p className="text-xs text-slate-500 mt-1">/ 100</p>
          </div>
          {[
            { label: "Total Nodes", value: health.total_nodes },
            { label: "High Risk Domains", value: health.high_risk_domains, warn: health.high_risk_domains > 0 },
            { label: "Single-Owner Domains", value: health.sole_owner_domains, warn: health.sole_owner_domains > 0 },
            { label: "Stale Nodes", value: health.stale_nodes, warn: health.stale_nodes > 5 },
          ].map((stat) => (
            <div key={stat.label} className="bg-slate-800 border border-slate-700 rounded-xl p-4">
              <p className="text-xs text-slate-500">{stat.label}</p>
              <p className={`text-2xl font-bold mt-1 ${stat.warn ? "text-orange-400" : "text-white"}`}>{stat.value}</p>
            </div>
          ))}
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          {/* Domain Risks */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
            <h2 className="text-sm font-semibold text-slate-300 mb-4">Domain Risk</h2>
            <div className="space-y-3">
              {health.domains.map((d) => (
                <div key={d.domain} className={`rounded-lg border p-3 ${RISK_COLORS[d.risk_level]}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium">{d.domain}</span>
                    <span className="text-xs font-bold">{d.risk_level}</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-1.5 mb-2">
                    <div className={`h-1.5 rounded-full ${RISK_BAR[d.risk_level]}`} style={{ width: `${d.risk_score * 100}%` }} />
                  </div>
                  <p className="text-xs opacity-80">{d.reason}</p>
                  <div className="flex gap-3 mt-2 text-xs opacity-70">
                    <span>Owner: {d.owner_id}</span>
                    <span>·</span>
                    <span>{d.node_count} nodes</span>
                    {d.sole_owner && <span className="text-red-400 font-medium">⚠ Single point of failure</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Owner Risks */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
            <h2 className="text-sm font-semibold text-slate-300 mb-4">Knowledge Owners</h2>
            <div className="space-y-3">
              {health.owners.filter(o => o.author_id !== "unknown").map((o) => (
                <div key={o.author_id} className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <p className="text-sm font-medium text-white">{o.author_id}</p>
                      <p className="text-xs text-slate-500">{o.email}</p>
                    </div>
                    <span className={`text-xs font-bold px-2 py-1 rounded ${RISK_COLORS[o.risk_level]}`}>{o.risk_level}</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-1.5 mb-2">
                    <div className={`h-1.5 rounded-full ${RISK_BAR[o.risk_level]}`} style={{ width: `${o.risk_score * 100}%` }} />
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>{o.node_count} knowledge nodes</span>
                    <button
                      onClick={() => showChecklist(o.author_id)}
                      className="text-blue-400 hover:text-blue-300 transition-colors"
                    >
                      Generate Transfer Checklist →
                    </button>
                  </div>
                  {o.domains.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {o.domains.map(d => (
                        <span key={d} className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded">{d}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Right: Risk Copilot */}
      <div className="w-80 xl:w-96 border-l border-slate-800 flex flex-col bg-slate-900 shrink-0">
        <div className="p-4 border-b border-slate-800">
          <p className="text-sm font-semibold text-white">Risk Copilot</p>
          <p className="text-xs text-slate-500 mt-0.5">Ask workforce decision questions</p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
          {copilotMessages.length === 0 && (
            <div className="space-y-2 mt-2">
              <p className="text-xs text-slate-600">Try asking:</p>
              {COPILOT_STARTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => sendCopilot(s)}
                  className="w-full text-left text-xs px-3 py-2 rounded-lg border border-slate-700 text-slate-400 hover:border-blue-500 hover:text-blue-400 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {copilotMessages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              {msg.role === "user" ? (
                <div className="bg-blue-600 text-white rounded-2xl rounded-tr-sm px-3 py-2 max-w-[85%]">
                  <p className="text-xs">{msg.content}</p>
                </div>
              ) : (
                <div className="bg-slate-800 border border-slate-700 rounded-xl p-3 w-full">
                  <p className="text-xs text-slate-200 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  <p className="text-xs text-slate-600 mt-2 italic">Based on knowledge graph analysis. Use alongside HR judgment.</p>
                </div>
              )}
            </div>
          ))}

          {copilotLoading && (
            <div className="flex justify-start">
              <div className="bg-slate-800 rounded-xl px-3 py-2 border border-slate-700">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}
          <div ref={copilotBottomRef} />
        </div>

        <div className="p-3 border-t border-slate-800">
          <div className="flex gap-2">
            <input
              value={copilotInput}
              onChange={(e) => setCopilotInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendCopilot()}
              placeholder="Ask about workforce risk..."
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => sendCopilot()}
              disabled={copilotLoading || !copilotInput.trim()}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white px-3 py-2 rounded-lg text-xs font-medium transition-colors"
            >
              Ask
            </button>
          </div>
        </div>
      </div>

      {/* Transfer Checklist Modal */}
      {checklist && checklistOwner && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <h3 className="font-semibold text-white">Knowledge Transfer Checklist — {checklistOwner}</h3>
              <button onClick={() => setChecklist(null)} className="text-slate-400 hover:text-white text-xl">×</button>
            </div>
            <div className="p-4 space-y-2">
              {checklist.checklist?.map((item: any, i: number) => (
                <div key={i} className={`rounded-lg p-3 border ${RISK_COLORS[item.priority] || "border-slate-700"}`}>
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">{item.title}</p>
                    <span className="text-xs font-bold">{item.priority}</span>
                  </div>
                  <p className="text-xs opacity-70 mt-1">{item.description}</p>
                  <p className="text-xs mt-1 opacity-80">→ {item.action}</p>
                  <p className="text-xs text-slate-500 mt-1">Source: {item.source} · {item.file}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Empty state fallback when API is unreachable
function getMockHealth(): HealthScore {
  return {
    overall_score: 0,
    total_nodes: 0,
    avg_decay: 0,
    high_risk_domains: 0,
    sole_owner_domains: 0,
    stale_nodes: 0,
    owners: [],
    domains: [],
  };
}

function getMockChecklist(ownerId: string) {
  return { owner_id: ownerId, total_nodes: 0, checklist: [] };
}
