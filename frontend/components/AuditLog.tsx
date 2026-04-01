"use client";
import { useEffect, useState } from "react";
import { getAuditLog, AuditSummary } from "@/lib/api";

export default function AuditLog() {
  const [data, setData] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    getAuditLog()
      .then(setData)
      .catch(() => setData(getMockAudit()))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-slate-500 text-sm">Loading audit log...</div>;
  if (!data) return null;

  return (
    <div className="p-6 overflow-y-auto h-full max-h-full space-y-6">
      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          <p className="text-xs text-slate-500">Total Queries</p>
          <p className="text-2xl font-bold text-white mt-1">{data.total_queries}</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          <p className="text-xs text-slate-500">Avg Confidence</p>
          <p className="text-2xl font-bold text-green-400 mt-1">{Math.round(data.avg_confidence * 100)}%</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          <p className="text-xs text-slate-500">Top Source</p>
          <p className="text-sm font-medium text-white mt-1 truncate">{data.top_sources[0]?.file || "—"}</p>
        </div>
      </div>

      {/* Query log */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-300">Query History</h2>
          <p className="text-xs text-slate-500 mt-0.5">Every AI-assisted query with full source provenance</p>
        </div>
        <div className="divide-y divide-slate-700">
          {data.entries.length === 0 && (
            <p className="p-4 text-sm text-slate-500">No queries yet. Ask something in the Knowledge Chat tab.</p>
          )}
          {data.entries.map((entry) => (
            <div key={entry.id} className="p-4">
              <div
                className="flex items-start justify-between cursor-pointer"
                onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white font-medium truncate">{entry.query_text}</p>
                  <div className="flex gap-3 mt-1 text-xs text-slate-500">
                    <span>{new Date(entry.queried_at).toLocaleString()}</span>
                    <span>·</span>
                    <span className="capitalize">{entry.query_method}</span>
                    <span>·</span>
                    <span className={entry.confidence && entry.confidence > 0.7 ? "text-green-400" : "text-yellow-400"}>
                      {entry.confidence ? `${Math.round(entry.confidence * 100)}% confidence` : "—"}
                    </span>
                  </div>
                </div>
                <span className="text-slate-500 ml-4">{expanded === entry.id ? "▲" : "▼"}</span>
              </div>

              {expanded === entry.id && (
                <div className="mt-3 space-y-3">
                  {entry.answer && (
                    <div className="bg-slate-900 rounded-lg p-3">
                      <p className="text-xs text-slate-500 mb-1">Answer</p>
                      <p className="text-xs text-slate-300 leading-relaxed">{entry.answer.slice(0, 400)}{entry.answer.length > 400 ? "…" : ""}</p>
                    </div>
                  )}
                  {entry.source_files.length > 0 && (
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Source Files</p>
                      <div className="flex flex-wrap gap-1">
                        {entry.source_files.map((f, i) => (
                          <span key={i} className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded">{f}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {entry.source_nodes.length > 0 && (
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Referenced Entities</p>
                      <div className="flex flex-wrap gap-1">
                        {entry.source_nodes.map((n, i) => (
                          <span key={i} className="text-xs bg-blue-900/40 text-blue-300 border border-blue-800 px-2 py-0.5 rounded">{n}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function getMockAudit(): AuditSummary {
  return {
    total_queries: 0,
    avg_confidence: 0,
    top_sources: [],
    entries: [],
  };
}
