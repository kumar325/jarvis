import { useCallback, useEffect, useRef, useState } from "react";
import type { Directive, DocumentEntry, StatCardData, ToolCallCard, WireEvent } from "../lib/types";
import { MOCK_VITALS, MOCK_DIRECTIVES, MOCK_DOCUMENTS } from "../lib/mockData";
import { parseTtsCommand } from "../lib/ttsCommand";
import { useAudioPlayback } from "./useAudioPlayback";

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) || "ws://localhost:8001/ws";
const RECONNECT_DELAY_MS = 2000;
const BUSY_TIMEOUT_MS = 10000;

function logTimestamp() {
  const d = new Date();
  return d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0");
}

type ServerMessage =
  | { type: "vitals_update"; vitals: StatCardData[] }
  | { type: "directives_update"; directives: Directive[] }
  | { type: "documents_update"; documents: DocumentEntry[] }
  | { type: "assistant_text"; text: string }
  | { type: "transcript"; text: string }
  | { type: "tool_call"; id: string; tool_name: string; args: Record<string, unknown> }
  | { type: "tool_result"; id: string; tool_name: string; preview: string }
  | { type: "tts_state"; enabled: boolean }
  | { type: "error"; message: string };

function timestamp() {
  return new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" });
}

export function useJarvisSocket(ttsEnabled: boolean, onTtsStateChange: (enabled: boolean) => void) {
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
  const busyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { play, stop: stopPlayback, isPlaying, getLevel: getPlaybackLevel } = useAudioPlayback(ttsEnabled);

  // `reason` identifies which call site flipped the flag, so a stuck-busy report can be
  // diagnosed from the browser console. Every call logs an explicit timestamp (not relying
  // on devtools' optional timestamp column) so the ordering/gaps between calls are visible
  // even if the console log is copy-pasted out of devtools.
  const setBusy = useCallback((busy: boolean, reason: string) => {
    console.log(`[useJarvisSocket ${logTimestamp()}] setBusy(${busy}) — ${reason}`);
    agentBusyRef.current = busy;
    setAgentBusy(busy);

    if (busyTimeoutRef.current) {
      clearTimeout(busyTimeoutRef.current);
      busyTimeoutRef.current = null;
    }

    if (busy) {
      // Safety net: if nothing ever clears agentBusy (a swallowed error, a message we
      // didn't anticipate, a dropped assistant_text), don't leave the UI locked forever.
      busyTimeoutRef.current = setTimeout(() => {
        console.warn(
          `[useJarvisSocket ${logTimestamp()}] agentBusy stuck true for ${BUSY_TIMEOUT_MS}ms with no ` +
            `assistant_text/error — forcing reset`
        );
        agentBusyRef.current = false;
        setAgentBusy(false);
        busyTimeoutRef.current = null;
      }, BUSY_TIMEOUT_MS);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (busyTimeoutRef.current) clearTimeout(busyTimeoutRef.current);
    };
  }, []);

  const pushWireEvent = useCallback((speaker: "USER" | "JARVIS", text: string) => {
    wireIdRef.current += 1;
    setWireEvents((prev) =>
      [{ id: `w${wireIdRef.current}`, speaker, text, timestamp: timestamp() }, ...prev].slice(0, 20)
    );
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
        setBusy(false, "ws:onclose");
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
            setBusy(true, `tool_call:${msg.tool_name}`);
            setToolCards((prev) => [
              ...prev.filter((c) => c.id !== msg.id),
              { id: msg.id, toolName: msg.tool_name, preview: "running…", timestamp: timestamp() },
            ]);
            break;
          case "tool_result":
            // Tool trace stays in the floating ToolCallCards only — not a chat message.
            setToolCards((prev) =>
              prev.map((c) => (c.id === msg.id ? { ...c, preview: msg.preview } : c))
            );
            break;
          case "transcript":
            // What a voice recording was transcribed to — the user's turn in the log.
            pushWireEvent("USER", msg.text);
            // A mute/unmute phrase is intercepted server-side before ask_jarvis() — it
            // was never a real LLM query, so don't leave the mic/input frozen waiting
            // on a reply that (aside from the tts_state + confirmation) won't come.
            if (parseTtsCommand(msg.text) !== null) setBusy(false, "transcript:tts-command");
            break;
          case "assistant_text":
            setBusy(false, "assistant_text");
            pushWireEvent("JARVIS", msg.text);
            break;
          case "tts_state":
            onTtsStateChange(msg.enabled);
            break;
          case "error":
            setBusy(false, "error");
            pushWireEvent("JARVIS", msg.message);
            break;
          default:
            // A message type the frontend doesn't recognize (server/client type drift).
            // Without this, the switch would just silently do nothing — and if agentBusy
            // was true waiting on a reply, this message wouldn't clear it, leaving only
            // the BUSY_TIMEOUT_MS safety net to eventually recover.
            console.warn(
              `[useJarvisSocket ${logTimestamp()}] unhandled server message type — this will not clear agentBusy`,
              msg
            );
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
  }, [pushWireEvent, play, setBusy, onTtsStateChange]);

  const sendText = useCallback(
    (text: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || agentBusyRef.current) return;
      try {
        // A new request always interrupts whatever Jarvis is currently speaking —
        // never let two replies play at once.
        stopPlayback();
        // A mute/unmute command is intercepted server-side before ask_jarvis() — it's
        // never a real LLM query, so don't flip agentBusy (and freeze mic/input) for it.
        if (parseTtsCommand(text) === null) setBusy(true, "sendText");
        pushWireEvent("USER", text);
        ws.send(JSON.stringify({ type: "user_text", text }));
      } catch (err) {
        console.error("failed to send text", err);
        setBusy(false, "sendText:catch");
      }
    },
    [setBusy, pushWireEvent, stopPlayback]
  );

  const sendAudio = useCallback(
    (wav: ArrayBuffer) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || agentBusyRef.current) return;
      try {
        stopPlayback();
        setBusy(true, "sendAudio");
        ws.send(wav);
      } catch (err) {
        console.error("failed to send audio", err);
        setBusy(false, "sendAudio:catch");
      }
    },
    [setBusy, stopPlayback]
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
    stopPlayback,
  };
}
