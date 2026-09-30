"use client";

import { useState } from "react";
import Header from "@/components/Header";
import CodeEditor from "@/components/CodeEditor";
import AgentTerminal from "@/components/AgentTerminal";
import DiffViewer from "@/components/DiffViewer";
import AgentTrace from "@/components/AgentTrace";
import MetricsPanel from "@/components/MetricsPanel";
import PipelineGraph from "@/components/PipelineGraph";
import { useWebSocket } from "@/hooks/useWebSocket";

const SAMPLE_LEGACY_CODE = `def calc(a,b,c):
    if c=="+":
        return a+b
    elif c=="-":
        return a-b
    elif c=="*":
        return a*b
    elif c=="/":
        if b==0:
            return "err"
        return a/b
    else:
        return "nope"`;

export default function Home() {
  const [inputCode, setInputCode] = useState(SAMPLE_LEGACY_CODE);
  const [activeTab, setActiveTab] = useState<"diff" | "tests" | "metrics" | "trace">("diff");

  const { messages, isRunning, connect, sendMessage } = useWebSocket("ws://localhost:8000/ws/refactor");

  const latestTrace = [...messages].reverse().find((m) => m.llm_messages)?.llm_messages;
  const metricsMsg = [...messages].reverse().find((m) => m.metrics_before || m.metrics_after);
  const reportMsg = [...messages].reverse().find((m) => m.report);

  // NOTE: "success" no longer fires in v3 — the pipeline ends at
  // awaiting_approval -> shipped / rejected. We look for all of them.
  const lastSuccess = [...messages]
    .reverse()
    .find((m) => ["awaiting_approval", "shipped", "success", "exhausted"].includes(m.step));
  const displayCode = lastSuccess?.code || "";
  const displayTest = lastSuccess?.test_code || "";

  const latestMessage = messages.length > 0 ? messages[messages.length - 1] : null;
  const isAwaitingApproval = latestMessage?.step === "awaiting_approval";
  const isShipped = latestMessage?.step === "shipped";
  const isRejected = latestMessage?.step === "rejected";

  const handleRefactor = () => {
    if (!inputCode.trim() || isRunning) return;
    connect(inputCode);
  };

  const tabs = [
    { id: "diff", label: "✨ Code Diff" },
    { id: "tests", label: "🧪 Pytest Suite" },
    { id: "metrics", label: "📊 Quality Metrics" },
    { id: "trace", label: "🔍 LLM Trace" },
  ] as const;

  return (
    <div className="h-screen flex flex-col">
      <Header isRunning={isRunning} />

      <div className="flex-1 grid grid-cols-2 gap-4 p-4 overflow-hidden">
        {/* Left Column */}
        <div className="flex flex-col gap-4 overflow-hidden">
          <div className="flex-1 min-h-0">
            <CodeEditor code={inputCode} onChange={setInputCode} label="📥 Legacy Code (Input)" />
          </div>

          {/* 🛑 HUMAN-IN-THE-LOOP GATE */}
          {isAwaitingApproval ? (
            <div className="flex gap-4">
              <button
                onClick={() => sendMessage({ action: "approve" })}
                className="flex-1 py-3 rounded-lg font-semibold text-sm transition-all
                  bg-green-600 hover:bg-green-500 text-white shadow-lg"
              >
                ✅ Accept & Commit to Git
              </button>
              <button
                onClick={() => sendMessage({ action: "reject" })}
                className="flex-1 py-3 rounded-lg font-semibold text-sm transition-all
                  bg-red-600 hover:bg-red-500 text-white shadow-lg"
              >
                ❌ Discard Refactor
              </button>
            </div>
          ) : (
            <button
              onClick={handleRefactor}
              disabled={isRunning || !inputCode.trim()}
              className="w-full py-3 rounded-lg font-semibold text-sm transition-all
                bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500
                disabled:opacity-40 disabled:cursor-not-allowed text-white shadow-lg"
            >
              {isRunning ? "⏳ Multi-Agent Pipeline Running..." : "🚀 Run Multi-Agent Refactor"}
            </button>
          )}

          {/* Final status banner */}
          {isShipped && (
            <div className="text-xs font-mono text-terminal-green bg-green-950/40 border border-green-900 rounded-lg px-3 py-2">
              🚀 {latestMessage?.message}
            </div>
          )}
          {isRejected && (
            <div className="text-xs font-mono text-terminal-red bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
              ❌ {latestMessage?.message}
            </div>
          )}

          <div className="flex-1 min-h-0 flex flex-col bg-terminal-bg rounded-lg border border-gray-800 overflow-hidden">
            <div className="flex border-b border-gray-800">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`px-3 py-2 text-xs font-mono transition-colors ${
                    activeTab === t.id
                      ? "bg-gray-800 text-white border-b-2 border-blue-500"
                      : "text-gray-500 hover:text-gray-300"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-auto">
              {activeTab === "diff" ? (
                <DiffViewer oldCode={inputCode} newCode={displayCode} />
              ) : activeTab === "tests" ? (
                <CodeEditor code={displayTest} label="🧪 Generated Pytest Suite" readOnly />
              ) : activeTab === "metrics" ? (
                <MetricsPanel
                  before={metricsMsg?.metrics_before}
                  after={metricsMsg?.metrics_after}
                  report={reportMsg?.report}
                />
              ) : (
                <AgentTrace messages={latestTrace} />
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Pipeline + Terminal */}
        <div className="h-full flex flex-col gap-4">
          <PipelineGraph messages={messages} />
          <div className="flex-1 min-h-0">
            <AgentTerminal messages={messages} />
          </div>
        </div>
      </div>
    </div>
  );
}