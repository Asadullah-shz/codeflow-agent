"use client";

export default function AgentTrace({ messages }: { messages?: Array<{role: string, content: string}> }) {
  if (!messages || messages.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500 text-sm font-mono bg-terminal-bg p-4">
        The LLM conversation trace will appear here after the agent runs...
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-terminal-bg p-4 space-y-4 font-mono text-xs">
      {messages.map((msg, i) => (
        <div key={i} className="flex flex-col gap-1">
          <div className={`font-bold uppercase text-[10px] ${
            msg.role === "system" ? "text-gray-500" : 
            msg.role === "user" ? "text-blue-400" : 
            "text-green-400"
          }`}>
            {msg.role}
          </div>
          <div className={`p-3 rounded-lg border ${
            msg.role === "system" ? "bg-gray-900 border-gray-800 text-gray-400" : 
            msg.role === "user" ? "bg-blue-950 border-blue-900 text-blue-100" : 
            "bg-green-950 border-green-900 text-green-100"
          }`}>
            <pre className="whitespace-pre-wrap break-words">{msg.content}</pre>
          </div>
        </div>
      ))}
    </div>
  );
}