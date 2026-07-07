import { useCallback, useEffect, useRef, useState } from "react";
import type { StatCardData, ToolCallCard, WireEvent } from "../lib/types";
import { MOCK_VITALS } from "../lib/mockData";

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) || "ws://localhost:8001/ws";

type ServerMessage =
  | { type: "vitals_update"; vitals: StatCardData[] }
  | { type: "assistant_text"; text: string }
  | { type: "tool_call"; id: string; tool_name: string; args: Record<string, unknown> }
  | { type: "tool_result"; id: string; tool_name: string; preview: string }
  | { type: "error"; message: string };

function timestamp() {
  return new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" });
}

export function useJarvisSocket() {
  const [connected, setConnected] = useState(false);
  const [vitals, setVitals] = useState<StatCardData[]>(MOCK_VITALS);
  const [toolCards, setToolCards] = useState<ToolCallCard[]>([]);
  const [wireEvents, setWireEvents] = useState<WireEvent[]>([]);
  const [agentBusy, setAgentBusy] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const wireIdRef = useRef(0);

  const pushWireEvent = useCallback((text: string) => {
    wireIdRef.current += 1;
    setWireEvents((prev) => [{ id: `w${wireIdRef.current}`, text, timestamp: timestamp() }, ...prev].slice(0, 20));
  }, []);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data);
      switch (msg.type) {
        case "vitals_update":
          setVitals(msg.vitals);
          break;
        case "tool_call":
          setAgentBusy(true);
          setToolCards((prev) => [
            ...prev.filter((c) => c.id !== msg.id),
            { id: msg.id, toolName: msg.tool_name, preview: "running…", timestamp: timestamp() },
          ]);
          break;
        case "tool_result":
          setToolCards((prev) =>
            prev.map((c) => (c.id === msg.id ? { ...c, preview: msg.preview } : c))
          );
          pushWireEvent(`${msg.tool_name} → ${msg.preview}`);
          break;
        case "assistant_text":
          setAgentBusy(false);
          pushWireEvent(`Jarvis: ${msg.text}`);
          break;
        case "error":
          setAgentBusy(false);
          pushWireEvent(`error: ${msg.message}`);
          break;
      }
    };

    return () => ws.close();
  }, [pushWireEvent]);

  const sendText = useCallback((text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    setAgentBusy(true);
    ws.send(JSON.stringify({ type: "user_text", text }));
  }, []);

  return { connected, vitals, toolCards, wireEvents, agentBusy, sendText };
}
