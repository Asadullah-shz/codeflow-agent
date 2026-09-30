"use client";

import { useState, useRef, useCallback } from "react";

export interface AgentMessage {
  step:
    | "thinking" | "coding" | "failed" | "success" | "error" | "exhausted"
    | "metrics" | "critic" | "security" | "mutation" | "memory" | "report"
    | "awaiting_approval" | "shipped" | "rejected"; // <--- THE NEW STEPS ADDED HERE
  attempt?: number;
  message: string;
  code?: string;
  test_code?: string;
  output?: string;
  llm_messages?: Array<{ role: string; content: string }>;
  metrics_before?: Record<string, number>;
  metrics_after?: Record<string, number>;
  security_before?: Record<string, number>;
  security_after?: Record<string, number>;
  mutation_score_pct?: number;
  critic_feedback?: string;
  approved?: boolean;
  report?: Record<string, any>;
}

export function useWebSocket(url: string) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(
    (code: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      setMessages([]);
      setIsRunning(true);

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        ws.send(JSON.stringify({ code }));
      };

      ws.onmessage = (event) => {
        const data: AgentMessage = JSON.parse(event.data);
        setMessages((prev) => [...prev, data]);
        
        // Unfreeze the UI when we hit a terminal state OR the approval gate
        if (["success", "error", "exhausted", "awaiting_approval", "shipped", "rejected"].includes(data.step)) {
          setIsRunning(false);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        setIsRunning(false);
      };

      ws.onerror = () => {
        setMessages((prev) => [
          ...prev,
          { step: "error", message: "❌ WebSocket connection failed. Is the backend running?" },
        ]);
        setIsRunning(false);
      };
    },
    [url]
  );

  const sendMessage = useCallback((payload: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
  }, []);

  return { messages, isConnected, isRunning, connect, disconnect, sendMessage };
}