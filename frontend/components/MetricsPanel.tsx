"use client";

interface Metrics {
  avg_complexity?: number;
  lint_issues?: number;
  functions?: number;
  docstring_coverage?: number;
  lines?: number;
}

interface Report {
  security_before?: { issues?: number; high?: number };
  security_after?: { issues?: number; high?: number };
  mutation_score_pct?: number;
  mutants_killed?: number;
  mutants_total?: number;
  tokens?: { prompt?: number; completion?: number };
  est_cost_usd?: number;
  attempts?: number;
}

export default function MetricsPanel({
  before,
  after,
  report,
}: {
  before?: Metrics;
  after?: Metrics;
  report?: Report;
}) {
  if (!before && !after && !report) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500 text-sm font-mono p-4">
        Quality, security & mutation metrics will appear here after analysis...
      </div>
    );
  }

  const rows = [
    { label: "Cyclomatic Complexity", key: "avg_complexity", lowerBetter: true },
    { label: "Lint Issues (pyflakes)", key: "lint_issues", lowerBetter: true },
    { label: "Docstring Coverage %", key: "docstring_coverage", lowerBetter: false },
    { label: "Lines of Code", key: "lines", lowerBetter: true },
  ] as const;

  return (
    <div className="p-4 space-y-1 font-mono text-xs">
      <div className="grid grid-cols-3 text-gray-500 text-[10px] uppercase pb-2 border-b border-gray-700">
        <span>Quality Metric</span>
        <span className="text-center">Before</span>
        <span className="text-right">After</span>
      </div>
      {rows.map((r) => {
        const b = before?.[r.key];
        const a = after?.[r.key];
        let delta = "";
        let color = "text-gray-400";
        if (b != null && a != null && b !== a) {
          const improved = r.lowerBetter ? a < b : a > b;
          delta = improved ? "▼ improved" : "▲ worse";
          color = improved ? "text-terminal-green" : "text-terminal-red";
        }
        return (
          <div key={r.label} className="grid grid-cols-3 items-center py-2 border-b border-gray-800/60">
            <span className="text-gray-300">{r.label}</span>
            <span className="text-center text-gray-400">{b ?? "–"}</span>
            <span className="text-right">
              <span className="text-gray-100">{a ?? "–"}</span>
              {delta && <span className={`ml-2 ${color}`}>{delta}</span>}
            </span>
          </div>
        );
      })}

      {report && (
        <>
          <div className="pt-3 pb-1 text-gray-500 text-[10px] uppercase">Security & Test Strength</div>
          <div className="grid grid-cols-3 items-center py-2 border-b border-gray-800/60">
            <span className="text-gray-300">Security Issues (bandit)</span>
            <span className="text-center text-gray-400">{report.security_before?.issues ?? "–"}</span>
            <span className="text-right text-gray-100">{report.security_after?.issues ?? "–"}</span>
          </div>
          <div className="grid grid-cols-3 items-center py-2 border-b border-gray-800/60">
            <span className="text-gray-300">Mutation Score (test strength)</span>
            <span className="text-center text-gray-400">–</span>
            <span className={`text-right ${ (report.mutation_score_pct ?? 0) >= 70 ? "text-terminal-green" : "text-terminal-yellow" }`}>
              {report.mutation_score_pct ?? "–"}% ({report.mutants_killed}/{report.mutants_total} killed)
            </span>
          </div>
          <div className="pt-3 pb-1 text-gray-500 text-[10px] uppercase">Run Economics</div>
          <div className="grid grid-cols-3 items-center py-2 border-b border-gray-800/60">
            <span className="text-gray-300">LLM Tokens (in/out)</span>
            <span className="text-center text-gray-400">–</span>
            <span className="text-right text-gray-100">
              {report.tokens?.prompt ?? 0} / {report.tokens?.completion ?? 0}
            </span>
          </div>
          <div className="grid grid-cols-3 items-center py-2 border-b border-gray-800/60">
            <span className="text-gray-300">Estimated Cost</span>
            <span className="text-center text-gray-400">–</span>
            <span className="text-right text-terminal-green">${report.est_cost_usd ?? 0}</span>
          </div>
          <div className="grid grid-cols-3 items-center py-2">
            <span className="text-gray-300">Attempts Needed</span>
            <span className="text-center text-gray-400">–</span>
            <span className="text-right text-gray-100">{report.attempts ?? "–"}</span>
          </div>
        </>
      )}
    </div>
  );
}