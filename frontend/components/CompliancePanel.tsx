"use client";
import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FRAMEWORK_COLORS: Record<string, string> = {
  SOX: "bg-yellow-900/40 text-yellow-300 border-yellow-800",
  GDPR: "bg-blue-900/40 text-blue-300 border-blue-800",
  HIPAA: "bg-green-900/40 text-green-300 border-green-800",
  EU_AI_ACT: "bg-purple-900/40 text-purple-300 border-purple-800",
  ISO_42001: "bg-pink-900/40 text-pink-300 border-pink-800",
};

export default function CompliancePanel() {
  const [tagSummary, setTagSummary] = useState<any[]>([]);
  const [tags, setTags] = useState<any[]>([]);
  const [gaps, setGaps] = useState<any[]>([]);
  const [chainStatus, setChainStatus] = useState<any>(null);
  const [chain, setChain] = useState<any[]>([]);
  const [activeFramework, setActiveFramework] = useState<string | null>(null);
  const [tagging, setTagging] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`${BASE}/compliance/tags/summary`).then(r => r.json()).catch(() => []),
      fetch(`${BASE}/compliance/gaps`).then(r => r.json()).catch(() => []),
      fetch(`${BASE}/compliance/audit-chain/status`).then(r => r.json()).catch(() => null),
    ]).then(([summary, gapsData, status]) => {
      setTagSummary(summary);
      setGaps(gapsData);
      setChainStatus(status);
    });
  }, []);

  async function runAutoTag() {
    setTagging(true);
    try {
      await fetch(`${BASE}/compliance/tag/auto`, { method: "POST" });
      const summary = await fetch(`${BASE}/compliance/tags/summary`).then(r => r.json());
      setTagSummary(summary);
    } finally {
      setTagging(false);
    }
  }

  async function loadFrameworkTags(fw: string) {
    setActiveFramework(fw);
    const data = await fetch(`${BASE}/compliance/tags?framework=${fw}`).then(r => r.json()).catch(() => []);
    setTags(data);
  }

  async function loadChain() {
    const data = await fetch(`${BASE}/compliance/audit-chain`).then(r => r.json()).catch(() => []);
    setChain(data);
  }

  return (
    <div className="p-6 overflow-y-auto h-full max-h-full space-y-6">

      {/* Regulatory Tagging */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-300">Regulatory Coverage</h2>
            <p className="text-xs text-slate-500 mt-0.5">Auto-tagged knowledge nodes by compliance framework</p>
          </div>
          <button
            onClick={runAutoTag}
            disabled={tagging}
            className="text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white px-3 py-1.5 rounded-lg transition-colors"
          >
            {tagging ? "Tagging…" : "Run Auto-Tag"}
          </button>
        </div>

        <div className="flex flex-wrap gap-3">
          {tagSummary.length === 0 && (
            <p className="text-xs text-slate-500">No tags yet. Click "Run Auto-Tag" to scan knowledge nodes.</p>
          )}
          {tagSummary.map((t) => (
            <button
              key={t.framework}
              onClick={() => loadFrameworkTags(t.framework)}
              className={`px-3 py-2 rounded-lg border text-xs font-medium transition-opacity ${FRAMEWORK_COLORS[t.framework] || "bg-slate-700 text-slate-300 border-slate-600"} ${activeFramework === t.framework ? "opacity-100 ring-2 ring-white/20" : "opacity-80 hover:opacity-100"}`}
            >
              {t.framework} · {t.node_count} nodes
            </button>
          ))}
        </div>

        {activeFramework && tags.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-slate-500">{activeFramework} tagged nodes</p>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {tags.map((t, i) => (
                <div key={i} className="flex items-center justify-between bg-slate-900 rounded-lg px-3 py-2">
                  <span className="text-xs text-slate-200">{t.node_title}</span>
                  <span className="text-xs text-slate-500">{t.rationale}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Coverage Gap Analysis */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-1">Coverage Gap Analysis</h2>
        <p className="text-xs text-slate-500 mb-4">Topics frequently queried but poorly documented — blind spots before they become crises</p>

        {gaps.length === 0 ? (
          <p className="text-xs text-slate-500">No gaps detected yet. Gaps are identified as users ask questions. Start querying in the Knowledge Chat tab.</p>
        ) : (
          <div className="space-y-2">
            {gaps.map((g, i) => (
              <div key={i} className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-white font-medium">{g.topic}</span>
                  <span className={`text-xs font-bold ${g.gap_score > 0.7 ? "text-red-400" : g.gap_score > 0.4 ? "text-yellow-400" : "text-green-400"}`}>
                    {Math.round(g.gap_score * 100)}% gap
                  </span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-1.5 mb-2">
                  <div
                    className={`h-1.5 rounded-full ${g.gap_score > 0.7 ? "bg-red-500" : g.gap_score > 0.4 ? "bg-yellow-500" : "bg-green-500"}`}
                    style={{ width: `${g.gap_score * 100}%` }}
                  />
                </div>
                <div className="flex gap-4 text-xs text-slate-500">
                  <span>{g.query_count} queries</span>
                  <span>·</span>
                  <span>{g.node_count} documented nodes</span>
                  <span>·</span>
                  <span>Last queried: {new Date(g.last_queried).toLocaleDateString()}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Audit Chain Integrity */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-300">Audit Chain Integrity</h2>
            <p className="text-xs text-slate-500 mt-0.5">Cryptographic hash chain — tamper-evident compliance log</p>
          </div>
          <button
            onClick={loadChain}
            className="text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 px-3 py-1.5 rounded-lg transition-colors"
          >
            Verify Chain
          </button>
        </div>

        {chainStatus && (
          <div className={`rounded-lg p-3 border mb-4 ${chainStatus.chain_intact ? "bg-green-900/30 border-green-800" : "bg-red-900/30 border-red-800"}`}>
            <div className="flex items-center gap-2">
              <span className={`text-lg ${chainStatus.chain_intact ? "text-green-400" : "text-red-400"}`}>
                {chainStatus.chain_intact ? "✓" : "✗"}
              </span>
              <div>
                <p className={`text-sm font-medium ${chainStatus.chain_intact ? "text-green-300" : "text-red-300"}`}>
                  {chainStatus.compliance_status}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {chainStatus.valid_entries} / {chainStatus.total_entries} entries verified
                </p>
              </div>
            </div>
          </div>
        )}

        {chain.length > 0 && (
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {chain.map((entry) => (
              <div key={entry.id} className={`rounded-lg px-3 py-2 border text-xs ${entry.chain_valid ? "bg-slate-900 border-slate-700" : "bg-red-900/20 border-red-800"}`}>
                <div className="flex items-center justify-between">
                  <span className="text-slate-300 truncate max-w-xs">{entry.query_text}</span>
                  <span className={entry.chain_valid ? "text-green-400" : "text-red-400"}>
                    {entry.chain_valid ? "✓ valid" : "✗ tampered"}
                  </span>
                </div>
                {entry.entry_hash && (
                  <p className="text-slate-600 mt-0.5 font-mono">{entry.entry_hash.slice(0, 32)}…</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
