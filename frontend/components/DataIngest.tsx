"use client";
import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const DEFAULT_REPOS = [
  "microsoft/vscode",
  "facebook/react",
  "vercel/next.js",
  "torvalds/linux",
  "golang/go",
];

interface IngestResult {
  nodes?: number;
  edges?: number;
  repos?: string[];
  error?: string;
}

interface IngestStatus {
  running: boolean;
  last_run: string | null;
  last_result: IngestResult | null;
  error: string | null;
}

export default function DataIngest() {
  const [repos, setRepos] = useState("microsoft/vscode,facebook/react,vercel/next.js");
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<IngestStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  async function fetchStatus() {
    try {
      const r = await fetch(`${BASE}/ingest/status`);
      const data = await r.json();
      setStatus(data);
    } catch {}
  }

  async function triggerIngest() {
    setLoading(true);
    const repoList = repos.split(",").map(r => r.trim()).filter(Boolean);
    addLog(`Starting ingestion for: ${repoList.join(", ")}`);
    try {
      const r = await fetch(`${BASE}/ingest/github`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repos: repoList, github_token: token || null }),
      });
      const data = await r.json();
      addLog(`Status: ${data.status} — ${data.message}`);
      addLog("Polling for completion...");
    } catch (e) {
      addLog(`Error: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  function addLog(msg: string) {
    const ts = new Date().toLocaleTimeString();
    setLog(prev => [`[${ts}] ${msg}`, ...prev].slice(0, 30));
  }

  // Watch for completion
  useEffect(() => {
    if (status?.last_result && !status.running) {
      const r = status.last_result;
      if (r.nodes) addLog(`✓ Graph rebuilt: ${r.nodes} nodes, ${r.edges} edges from ${r.repos?.join(", ")}`);
    }
    if (status?.error) addLog(`✗ Error: ${status.error}`);
  }, [status?.running, status?.last_run]);

  return (
    <div className="p-6 overflow-y-auto h-full space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Live GitHub Data Ingestion</h2>
          <p className="text-xs text-slate-500 mt-1">
            Fetch real contributors, PRs, issues, releases and dependencies from GitHub repos
          </p>
        </div>
        {status?.running && (
          <div className="flex items-center gap-2 text-sm text-blue-400">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse inline-block" />
            Fetching data...
          </div>
        )}
        {status?.last_result && !status.running && (
          <div className="flex items-center gap-2 text-sm text-green-400">
            <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
            {status.last_result.nodes} nodes · {status.last_result.edges} edges
          </div>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Config panel */}
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-slate-300">Configuration</h3>

          <div>
            <label className="text-xs text-slate-400 mb-1 block">
              GitHub Repos <span className="text-slate-600">(comma-separated owner/repo)</span>
            </label>
            <textarea
              value={repos}
              onChange={e => setRepos(e.target.value)}
              rows={3}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500 resize-none"
              placeholder="microsoft/vscode,facebook/react"
            />
          </div>

          <div>
            <label className="text-xs text-slate-400 mb-1 block">
              GitHub Token <span className="text-slate-600">(optional — raises limit to 5000 req/hr)</span>
            </label>
            <input
              type="password"
              value={token}
              onChange={e => setToken(e.target.value)}
              placeholder="ghp_xxxxxxxxxxxx"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500"
            />
            <p className="text-xs text-slate-600 mt-1">
              Get a free token at github.com/settings/tokens (no scopes needed for public repos)
            </p>
          </div>

          <button
            onClick={triggerIngest}
            disabled={loading || status?.running}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            {status?.running ? "Fetching GitHub Data..." : "🔄 Fetch & Rebuild Graph"}
          </button>

          <p className="text-xs text-slate-600">
            Fetches: contributors · PRs · issues · releases · languages · dependencies
          </p>
        </div>

        {/* Quick presets */}
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-slate-300">Quick Presets</h3>
          <p className="text-xs text-slate-500">Click to load a preset, then hit Fetch</p>
          {[
            { label: "🌐 Top Open Source", repos: "microsoft/vscode,facebook/react,vercel/next.js" },
            { label: "🐍 Python Ecosystem", repos: "python/cpython,django/django,pallets/flask" },
            { label: "☁️ Cloud Native", repos: "kubernetes/kubernetes,istio/istio,helm/helm" },
            { label: "🤖 AI / ML", repos: "openai/openai-python,huggingface/transformers,langchain-ai/langchain" },
            { label: "🛠️ DevTools", repos: "microsoft/typescript,vitejs/vite,prettier/prettier" },
          ].map(preset => (
            <button
              key={preset.label}
              onClick={() => setRepos(preset.repos)}
              className="w-full text-left text-xs px-3 py-2 rounded-lg border border-slate-700 text-slate-400 hover:border-blue-500 hover:text-blue-400 transition-colors"
            >
              {preset.label}
              <span className="block text-slate-600 mt-0.5">{preset.repos}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Last result */}
      {status?.last_result && (
        <div className="bg-slate-800 border border-green-800 rounded-xl p-4">
          <p className="text-xs font-semibold text-green-400 mb-2">Last Ingestion Result</p>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-slate-500">Nodes</p>
              <p className="text-2xl font-bold text-white">{status.last_result.nodes}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Edges</p>
              <p className="text-2xl font-bold text-white">{status.last_result.edges}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Repos</p>
              <p className="text-sm font-medium text-white">{status.last_result.repos?.length}</p>
            </div>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Completed: {status.last_run ? new Date(status.last_run).toLocaleString() : "—"}
          </p>
          <p className="text-xs text-slate-600 mt-1">
            Repos: {status.last_result.repos?.join(", ")}
          </p>
        </div>
      )}

      {/* Activity log */}
      {log.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <p className="text-xs font-semibold text-slate-400 mb-2">Activity Log</p>
          <div className="space-y-1 font-mono">
            {log.map((l, i) => (
              <p key={i} className={`text-xs ${l.includes("✓") ? "text-green-400" : l.includes("✗") ? "text-red-400" : "text-slate-500"}`}>
                {l}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
