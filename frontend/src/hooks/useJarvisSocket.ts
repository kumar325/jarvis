import { useCallback, useEffect, useRef, useState } from "react";
import type { Directive, DocumentEntry, StatCardData, ToolCallCard, WireEvent } from "../lib/types";
import { MOCK_VITALS, MOCK_DIRECTIVES, MOCK_DOCUMENTS } from "../lib/mockData";
import { useAudioPlayback } from "./useAudioPlayback";

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) || "ws://localhost:8001/ws";
const RECONNECT_DELAY_MS = 2000;

type ServerMessage =
  | { type: "vitals_update"; vitals: StatCardData[] }
  | { type: "directives_update"; directives: Directive[] }
  | { type: "documents_update"; documents: DocumentEntry[] }
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
  const [directives, setDirectives] = useState<Directive[]>(MOCK_DIRECTIVES);
  const [documents, setDocuments] = useState<DocumentEntry[]>(MOCK_DOCUMENTS);
  const [toolCards, setToolCards] = useState<ToolCallCard[]>([]);
  const [wireEvents, setWireEvents] = useState<WireEvent[]>([]);
  const [agentBusy, setAgentBusy] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const agentBusyRef = useRef(false);
  const wireIdRef = useRef(0);
  const { play, isPlaying, getLevel: getPlaybackLevel } = useAudioPlayback();

  const setBusy = useCallback((busy: boolean) => {
    agentBusyRef.current = busy;
    setAgentBusy(busy);
  }, []);

  const pushWireEvent = useCallback((text: string) => {
    wireIdRef.current += 1;
    setWireEvents((prev) => [{ id: `w${wireIdRef.current}`, text, timestamp: timestamp() }, ...prev].slice(0, 20));
  }, []);

  useEffect(() => {
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);

      ws.onclose = () => {
        setConnected(false);
        // A dropped connection can't still be "processing" anything — otherwise a mic
        // or network hiccup permanently disables both input paths.
        setBusy(false);
        if (!cancelled) {
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };

      ws.onerror = () => {
        // The browser fires close right after error for connection failures; onclose
        // handles the busy reset + reconnect, this is just for closing it promptly.
        ws.close();
      };

      ws.onmessage = (event) => {
        if (event.data instanceof Blob) {
          event.data.arrayBuffer().then(play).catch((err) => console.error("playback failed", err));
          return;
        }

        let msg: ServerMessage;
        try {
          msg = JSON.parse(event.data);
        } catch (err) {
          console.error("failed to parse server message", err);
          return;
        }

        switch (msg.type) {
          case "vitals_update":
            setVitals(msg.vitals);
            break;
          case "directives_update":
            setDirectives(msg.directives);
            break;
          case "documents_update":
            setDocuments(msg.documents);
            break;
          case "tool_call":
            setBusy(true);
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
            setBusy(false);
            pushWireEvent(`Jarvis: ${msg.text}`);
            break;
          case "error":
            setBusy(false);
            pushWireEvent(`error: ${msg.message}`);
            break;
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [pushWireEvent, play, setBusy]);

  const sendText = useCallback(
    (text: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || agentBusyRef.current) return;
      try {
        setBusy(true);
        ws.send(JSON.stringify({ type: "user_text", text }));
      } catch (err) {
        console.error("failed to send text", err);
        setBusy(false);
      }
    },
    [setBusy]
  );

  const sendAudio = useCallback(
    (wav: ArrayBuffer) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || agentBusyRef.current) return;
      try {
        setBusy(true);
        ws.send(wav);
      } catch (err) {
        console.error("failed to send audio", err);
        setBusy(false);
      }
    },
    [setBusy]
  );

  return {
    connected,
    vitals,
    directives,
    documents,
    toolCards,
    wireEvents,
    agentBusy,
    sendText,
    sendAudio,
    isPlaying,
    getPlaybackLevel,
  };
}
