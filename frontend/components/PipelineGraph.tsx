"use client";

import { AgentMessage } from "@/hooks/useWebSocket";

const STEPS = ["Analyze", "Refactor", "Test", "Critic", "Security", "Mutants", "Ship"];

export default function PipelineGraph({ messages }: { messages: AgentMessage[] }) {
  const doneFlags = [
    messages.some((m) => m.step === "metrics"),
    messages.some((m) => m.step === "coding"),
    messages.some((m) => m.step === "failed" || m.step === "success"),
    messages.some((m) => m.step === "critic"),
    messages.some((m) => m.step === "security" && m.security_after),
    messages.some((m) => m.step === "mutation" && m.mutation_score_pct != null),
    messages.some((m) => m.step === "shipped" || m.step === "success"),
  ];
  const activeIdx = messages.length === 0 ? -1 : doneFlags.findIndex((d) => !d);

  return (
    <div className="flex items-start px-4 py-3 bg-terminal-bg rounded-lg border border-gray-800">
      {STEPS.map((label, i) => {
        const done = doneFlags[i];
        const active = i === activeIdx;
        return (
          <div key={label} className="flex items-start flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5 w-14">
              <div
                className={`w-3 h-3 rounded-full border-2 ${
                  done
                    ? "bg-terminal-green border-terminal-green"
                    : active
                    ? "bg-terminal-blue border-terminal-blue animate-pulse"
                    : "bg-transparent border-gray-600"
                }`}
              />
              <span
                className={`text-[8px] font-mono text-center ${
                  done ? "text-terminal-green" : active ? "text-terminal-blue" : "text-gray-600"
                }`}
              >
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-0.5 mt-1 ${done ? "bg-terminal-green" : "bg-gray-700"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}