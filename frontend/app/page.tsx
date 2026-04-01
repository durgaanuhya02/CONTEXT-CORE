"use client";
import { useState } from "react";
import ChatPanel from "@/components/ChatPanel";
import RiskDashboard from "@/components/RiskDashboard";
import GraphView from "@/components/GraphView";
import AuditLog from "@/components/AuditLog";
import CompliancePanel from "@/components/CompliancePanel";
import DataIngest from "@/components/DataIngest";

type Tab = "chat" | "risk" | "graph" | "audit" | "compliance" | "ingest";

export default function Home() {
  const [tab, setTab] = useState<Tab>("chat");

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: "chat",       label: "Knowledge Chat",  icon: "💬" },
    { id: "risk",       label: "Risk Dashboard",  icon: "⚠️" },
    { id: "graph",      label: "Knowledge Graph", icon: "🕸️" },
    { id: "audit",      label: "Audit Log",       icon: "📋" },
    { id: "compliance", label: "Compliance",      icon: "🔒" },
    { id: "ingest",     label: "Live Data",       icon: "🔄" },
  ];

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-200 flex flex-col h-screen">
      <header className="border-b border-slate-800 px-6 py-4 flex items-center gap-4">
        <div>
          <h1 className="text-xl font-bold text-white">
            ContextCore<span className="text-blue-400">™</span>
          </h1>
          <p className="text-xs text-slate-500">Institutional Memory Intelligence Platform</p>
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
          <span className="w-2 h-2 rounded-full bg-green-400 inline-block"></span>
          Live GitHub Knowledge Base · GraphRAG v3
        </div>
      </header>

      <nav className="border-b border-slate-800 px-6 flex gap-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t.id
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </nav>

      <main className="flex-1 overflow-hidden">
        {tab === "chat"       && <ChatPanel />}
        {tab === "risk"       && <RiskDashboard />}
        {tab === "graph"      && <GraphView />}
        {tab === "audit"      && <AuditLog />}
        {tab === "compliance" && <CompliancePanel />}
        {tab === "ingest"     && <DataIngest />}
      </main>
    </div>
  );
}
