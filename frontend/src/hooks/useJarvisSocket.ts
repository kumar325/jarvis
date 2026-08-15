import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Directive,
  DocumentEntry,
  Rating,
  StatCardData,
  TaskState,
  ToolCallCard,
  WireEvent,
} from "../lib/types";
import { MOCK_VITALS, MOCK_DIRECTIVES, MOCK_DOCUMENTS } from "../lib/mockData";
import { parseTtsCommand } from "../lib/ttsCommand";
import { useAudioPlayback } from "./useAudioPlayback";

// frontend/.env is gitignored, so a fresh clone has no VITE_WS_URL and falls through to
// this default — it must match the port backend/server.py actually documents (8000), or
// a new machine silently fails to connect with no error beyond "Connecting…".
const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) || "ws://localhost:8000/ws";
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
  | { type: "assistant_text"; text: string; id: string; ratable: boolean }
  | { type: "transcript"; text: string }
  | { type: "session_info"; session_id: string; condition: string }
  | { type: "tool_call"; id: string; tool_name: string; args: Record<string, unknown> }
  | { type: "tool_result"; id: string; tool_name: string; preview: string }
  | { type: "tts_state"; enabled: boolean }
  | { type: "task_state"; completed_tasks: number; next_task: number; arch_complete: boolean }
  | { type: "task_recorded"; task_number: number; next_task: number; arch_complete: boolean }
  | { type: "task_error"; message: string }
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
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [condition, setCondition] = useState<string | null>(null);
  // Task progress through the current arm. Server-owned and re-sent on every connect, so a
  // refreshed browser resumes at the right task rather than restarting the count.
  const [taskState, setTaskState] = useState<TaskState>({
    completedTasks: 0,
    nextTask: 1,
    archComplete: false,
  });
  const [taskSubmitting, setTaskSubmitting] = useState(false);
  const [taskError, setTaskError] = useState<string | null>(null);
  // Set when the server confirms a task boundary reached disk; App consumes it and clears
  // it via acknowledgeTaskRecorded(). Unlike a rating this is NOT acknowledged
  // optimistically — a dropped boundary shifts the numbering of every task after it, and
  // with the survey answers now on paper this row is the only digital record that the
  // task ended at all.
  const [taskRecorded, setTaskRecorded] = useState<{
    taskNumber: number;
    archComplete: boolean;
  } | null>(null);
  // The id of the response currently awaiting a thumbs up/down. Non-null means input is
  // gated: the participant must rate before sending anything else.
  const [pendingRatingId, setPendingRatingId] = useState<string | null>(null);
  // Mirrored in a ref so the send callbacks can check the gate without being re-created
  // (and tearing down the socket effect) every time a rating lands.
  const pendingRatingIdRef = useRef<string | null>(null);
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

  const updatePendingRating = useCallback((id: string | null) => {
    pendingRatingIdRef.current = id;
    setPendingRatingId(id);
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
        // A reconnect starts a fresh server-side session, so the old pending response no
        // longer exists to be rated — holding the gate would lock the participant out.
        updatePendingRating(null);
        // No task_recorded/task_error is coming over a closed socket, so drop the pending
        // state — the button becomes clickable again and the moderator can resend once the
        // socket is back. Nothing is lost by retrying: the server assigns the task number.
        setTaskSubmitting(false);
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
            // Tool trace is tracked but not rendered — never a chat message.
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
          case "session_info":
            setSessionId(msg.session_id);
            setCondition(msg.condition);
            break;
          case "task_state":
            setTaskState({
              completedTasks: msg.completed_tasks,
              nextTask: msg.next_task,
              archComplete: msg.arch_complete,
            });
            break;
          case "task_recorded":
            setTaskSubmitting(false);
            setTaskError(null);
            setTaskState({
              completedTasks: msg.task_number,
              nextTask: msg.next_task,
              archComplete: msg.arch_complete,
            });
            setTaskRecorded({ taskNumber: msg.task_number, archComplete: msg.arch_complete });
            break;
          case "task_error":
            // Deliberately not pushed to the wire log — a disk problem is the operator's,
            // and the participant's transcript must not carry it. Re-enables the button so
            // the moderator can retry.
            setTaskSubmitting(false);
            setTaskError(msg.message);
            break;
          case "assistant_text":
            setBusy(false, "assistant_text");
            pushWireEvent("JARVIS", msg.text);
            // Mute/unmute confirmations arrive as assistant_text too, but the server marks
            // them ratable:false — gating on those would put junk in the ratings log.
            if (msg.ratable && msg.id) updatePendingRating(msg.id);
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
  }, [pushWireEvent, play, setBusy, onTtsStateChange, updatePendingRating]);

  const sendText = useCallback(
    (text: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || agentBusyRef.current) return;
      if (pendingRatingIdRef.current) return;
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
      if (pendingRatingIdRef.current) return;
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

  const sendRating = useCallback(
    (rating: Rating) => {
      const messageId = pendingRatingIdRef.current;
      if (!messageId) return;

      // Cleared optimistically. A dropped frame or a disk error on the server must never
      // strand a participant behind the gate mid-session — a failed write comes back as an
      // error message for the session runner instead.
      updatePendingRating(null);

      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      try {
        ws.send(JSON.stringify({ type: "rating", message_id: messageId, rating }));
      } catch (err) {
        console.error("failed to send rating", err);
      }
    },
    [updatePendingRating]
  );

  const sendTaskComplete = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setTaskError("not connected — reconnecting, then try again");
      return;
    }
    setTaskError(null);
    setTaskSubmitting(true);
    try {
      // No task number or participant id in the payload: the server assigns both from the
      // task log, so a refreshed browser can't restart the count at 1 and log two
      // different tasks as task 1.
      ws.send(JSON.stringify({ type: "task_complete" }));
    } catch (err) {
      console.error("failed to send task complete", err);
      setTaskSubmitting(false);
      setTaskError("could not record the task — try again");
    }
  }, []);

  const acknowledgeTaskRecorded = useCallback(() => setTaskRecorded(null), []);

  const sendTtsState = useCallback((enabled: boolean) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      // Server-side mute means it also stops synthesizing, rather than sending audio the
      // client would only discard.
      ws.send(JSON.stringify({ type: "set_tts", enabled }));
    } catch (err) {
      console.error("failed to send tts state", err);
    }
  }, []);

  return {
    connected,
    sessionId,
    condition,
    taskState,
    taskSubmitting,
    taskError,
    taskRecorded,
    sendTaskComplete,
    acknowledgeTaskRecorded,
    vitals,
    directives,
    documents,
    toolCards,
    wireEvents,
    agentBusy,
    pendingRatingId,
    sendText,
    sendAudio,
    sendRating,
    sendTtsState,
    isPlaying,
    getPlaybackLevel,
    stopPlayback,
  };
}
