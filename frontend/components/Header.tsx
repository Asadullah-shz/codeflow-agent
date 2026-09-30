"use client";

export default function Header({ isRunning }: { isRunning: boolean }) {
  return (
    <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center text-sm font-bold">
          CF
        </div>
        <div>
          <h1 className="text-lg font-bold text-white">CodeFlow Agent</h1>
          <p className="text-xs text-gray-500">Autonomous Self-Correcting Refactoring Engine</p>
        </div>
      </div>
      {isRunning && (
        <div className="flex items-center gap-2 text-sm text-terminal-yellow">
          <span className="w-2 h-2 bg-terminal-yellow rounded-full animate-pulse" />
          Agent is working...
        </div>
      )}
    </header>
  );
}