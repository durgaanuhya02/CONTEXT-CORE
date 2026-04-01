"use client";
import { useState, useRef, useEffect } from "react";
import { queryKnowledge, QueryResponse } from "@/lib/api";

const SOURCE_COLORS: Record<string, string> = {
  slack: "bg-purple-900 text-purple-300",
  confluence: "bg-blue-900 text-blue-300",
  github: "bg-gray-700 text-gray-300",
  zoom: "bg-sky-900 text-sky-300",
};

const MODEL_BADGE: Record<string, { label: string; cls: string }> = {};

function getModelBadge(modelUsed: string): { label: string; cls: string } {
  if (!modelUsed || modelUsed === "none") return { label: "—", cls: "bg-slate-700 text-slate-400" };
  const m = modelUsed.toLowerCase();
  if (m.includes("api unavailable")) {
    return { label: modelUsed, cls: "bg-red-900 text-red-400 border border-red-700" };
  }
  if (m.includes("local template")) {
    return { label: "Local Template", cls: "bg-slate-700 text-slate-300" };
  }
  // Claude slot: Anthropic Claude or Groq Llama (analytical)
  if (m.includes("claude") || m.includes("llama") || m.includes("groq")) {
    return { label: modelUsed, cls: "bg-purple-900 text-purple-300 border border-purple-700" };
  }
  // GPT-4o slot: OpenAI GPT-4o or Gemini (concise)
  if (m.includes("gpt") || m.includes("gemini")) {
    return { label: modelUsed, cls: "bg-green-900 text-green-300 border border-green-700" };
  }
  return { label: modelUsed, cls: "bg-slate-700 text-slate-300" };
}

const SUGGESTED = [
  "Who are the top contributors to vscode?",
  "What technologies does react use?",
  "Which repos have the most knowledge concentration risk?",
  "What are the latest releases in next.js?",
  "Who owns the most critical knowledge?",
];

interface Message {
  role: "user" | "assistant";
  content: string;
  response?: QueryResponse;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [method, setMethod] = useState("local");
  const [model, setModel] = useState("auto");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(question?: string) {
    const q = question || input.trim();
    if (!q) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      // Log routing intent before the call
      if (model === "auto") {
        const reasoningKws = ["why", "decision", "reasoning", "rationale", "chose", "choose",
          "tradeoff", "trade-off", "explain", "how did", "what led", "impact", "risk",
          "should we", "recommend", "strategy", "architecture", "design", "compare"];
        const isReasoning = reasoningKws.some(kw => q.toLowerCase().includes(kw));
        if (isReasoning) {
          console.log(`[ContextCore] Auto mode: routed to Claude because reasoning keywords detected — "${q}"`);
        } else {
          console.log(`[ContextCore] Auto mode: routed to GPT-4o because simple query detected — "${q}"`);
        }
      } else if (model === "claude") {
        console.log(`[ContextCore] Calling Claude API with model: claude-sonnet-4-20250514`);
      } else if (model === "gpt4o") {
        console.log(`[ContextCore] Calling GPT-4o API with model: gpt-4o`);
      } else {
        console.log(`[ContextCore] Local template mode — no API call`);
      }

      const res = await queryKnowledge(q, method, model);
      console.log(`[ContextCore] Response — model_used: "${res.model_used}", confidence: ${Math.round(res.confidence * 100)}%, duration: ${res.duration_ms}ms`);
      setMessages((m) => [...m, { role: "assistant", content: res.answer, response: res }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: "Error connecting to ContextCore API. Is the backend running?" }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full max-h-full">
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 && (
            <div className="text-center mt-16">
              <p className="text-slate-500 text-sm mb-6">Ask anything about your GitHub knowledge base</p>
              <div className="flex flex-wrap gap-2 justify-center max-w-2xl mx-auto">
                {SUGGESTED.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="text-xs px-3 py-2 rounded-lg border border-slate-700 text-slate-400 hover:border-blue-500 hover:text-blue-400 transition-colors text-left"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-3xl ${msg.role === "user" ? "bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3" : "w-full"}`}>
                {msg.role === "user" ? (
                  <p className="text-sm">{msg.content}</p>
                ) : (
                  <div className="space-y-3">
                    {/* Answer */}
                    <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
                      <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                    </div>

                    {/* Metadata bar */}
                    {msg.response && (
                      <div className="flex items-center gap-2 text-xs text-slate-500 px-1 flex-wrap">
                        {/* Model badge — most prominent */}
                        {(() => {
                          const badge = getModelBadge(msg.response.model_used);
                          return (
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.cls}`}>
                              {badge.label}
                            </span>
                          );
                        })()}
                        <span>·</span>
                        <span>Confidence: <span className={`font-medium ${msg.response.confidence > 0.6 ? "text-green-400" : msg.response.confidence > 0.4 ? "text-yellow-400" : "text-red-400"}`}>{Math.round(msg.response.confidence * 100)}%</span></span>
                        <span>·</span>
                        <span>{msg.response.duration_ms}ms</span>
                        <span>·</span>
                        <span>method: {msg.response.method}</span>
                      </div>
                    )}

                    {/* Sources */}
                    {msg.response?.sources && msg.response.sources.length > 0 && (
                      <div className="px-1">
                        <p className="text-xs text-slate-500 mb-2">Sources</p>
                        <div className="flex flex-wrap gap-2">
                          {msg.response.sources.map((s, j) => (
                            <div key={j} className={`flex flex-col gap-0.5 border rounded-lg px-2 py-1.5 ${s.is_stale ? "border-orange-700 bg-orange-900/20" : "border-slate-700 bg-slate-800"}`}>
                              <div className="flex items-center gap-1.5">
                                <span className={`text-xs px-1.5 py-0.5 rounded ${SOURCE_COLORS[s.source_system] || "bg-slate-700 text-slate-300"}`}>
                                  {s.source_system}
                                </span>
                                <span className="text-xs text-slate-300 font-medium">{s.title}</span>
                                {s.is_stale && <span className="text-xs text-orange-400">⚠ stale</span>}
                              </div>
                              <div className="flex items-center gap-2 text-xs text-slate-500">
                                <span>by {s.author_id}</span>
                                {s.edge_type && <span className="text-slate-600">· {s.edge_type}</span>}
                                <span className={`ml-auto font-medium ${s.decay_score > 0.6 ? "text-green-400" : s.decay_score > 0.4 ? "text-yellow-400" : "text-red-400"}`}>
                                  {Math.round(s.decay_score * 100)}% confidence
                                </span>
                              </div>
                              {s.rationale && (
                                <p className="text-xs text-slate-600 italic truncate max-w-xs">{s.rationale}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-slate-800 rounded-xl px-4 py-3 border border-slate-700">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-800 p-4">
          <div className="flex gap-2 max-w-4xl mx-auto">
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded-lg px-2 py-2"
            >
              <option value="local">Local</option>
              <option value="global">Global</option>
              <option value="drift">DRIFT</option>
            </select>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded-lg px-2 py-2"
            >
              <option value="auto">Auto</option>
              <option value="claude">Claude</option>
              <option value="gpt4o">GPT-4o</option>
              <option value="local">Template</option>
            </select>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              placeholder="Ask about any engineering decision, system, or person..."
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => send()}
              disabled={loading || !input.trim()}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              Ask
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
