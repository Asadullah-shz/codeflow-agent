"use client";

import React from "react";
import { Code2 } from "lucide-react";

export interface CodeEditorProps {
  code: string;
  onChange?: (code: string) => void;
  label?: string;
  readOnly?: boolean;
}

export const CodeEditor: React.FC<CodeEditorProps> = ({
  code,
  onChange,
  label = "Code Editor",
  readOnly = false,
}) => {
  return (
    <div className="flex flex-col h-full bg-surface border border-surface-border rounded-xl overflow-hidden shadow-2xl">
      {/* Editor Top Bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-slate-900/80 border-b border-surface-border">
        <div className="flex items-center gap-2 text-xs text-slate-300 font-medium">
          <Code2 className="w-4 h-4 text-indigo-400" />
          <span>{label}</span>
        </div>
      </div>

      {/* Editor Main Content */}
      <div className="p-3 flex-1 flex flex-col min-h-0">
        <textarea
          value={code}
          readOnly={readOnly}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange?.(e.target.value)}
          placeholder={readOnly ? "Output will appear here..." : "# Type or paste code here..."}
          className={`w-full flex-1 p-3 rounded-lg bg-background border border-surface-border font-mono text-xs focus:outline-none focus:border-indigo-500 resize-none transition-colors ${
            readOnly ? "text-emerald-400 bg-slate-950/50" : "text-slate-200"
          }`}
        />
      </div>
    </div>
  );
};

export default CodeEditor;
