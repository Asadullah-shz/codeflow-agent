"use client";

import React from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';

interface DiffViewerProps {
  oldCode: string;
  newCode: string;
}

export default function DiffViewer({ oldCode, newCode }: DiffViewerProps) {
  if (!newCode) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500 text-sm font-mono bg-terminal-bg">
        Refactored code will appear here after the agent finishes...
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-terminal-bg">
      <ReactDiffViewer
        oldValue={oldCode}
        newValue={newCode}
        splitView={true}
        leftTitle="📥 Legacy Code (Before)"
        rightTitle="✨ Refactored Code (After)"
        useDarkTheme={true}
        compareMethod={DiffMethod.WORDS}
        showDiffOnly={false}
      />
    </div>
  );
}