"use client";

import { useEffect, useRef } from "react";
import { AgentMessage } from "@/hooks/useWebSocket";

const stepColors: Record<string, string> = {
  thinking: "text-terminal-blue",
  coding: "text-terminal-purple",
  failed: "text-terminal-red",
  success: "text-terminal-green",
  error: "text-terminal-red",
  exhausted: "text-terminal-yellow",
  metrics: "text-cyan-400",
  critic: "text-pink-400",
  security: "text-orange-400",
  mutation: "text-amber-300",
  memory: "text-fuchsia-400",
  report: "text-terminal-green",
    awaiting_approval: "text-terminal-yellow",
  shipped: "text-terminal-green",
  rejected: "text-terminal-red",
};

export default function AgentTerminal({ messages }: { messages: AgentMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="h-full flex flex-col bg-terminal-bg rounded-lg border border-gray-800">
      <div className="px-4 py-2 border-b border-gray-800 flex items-center gap-2">
        <div className="w-3 h-3 rounded-full bg-red-500" />
        <div className="w-3 h-3 rounded-full bg-yellow-500" />
        <div className="w-3 h-3 rounded-full bg-green-500" />
        <span className="ml-2 text-xs text-gray-500 font-mono">agent-terminal</span>
      </div>
      <div className="flex-1 overflow-y-auto p-4 font-mono text-sm terminal-scroll space-y-2">
        {messages.length === 0 && (
          <p className="text-gray-600 italic">Waiting for input... Paste code and click Refactor.</p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`${stepColors[msg.step] || "text-terminal-text"}`}>
            <span className="text-gray-600 mr-2">[{String(i + 1).padStart(2, "0")}]</span>
            {msg.message}
            {msg.output && (
              <pre className="mt-1 text-xs text-gray-500 bg-black/30 p-2 rounded overflow-x-auto whitespace-pre-wrap">
                {msg.output}
              </pre>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}