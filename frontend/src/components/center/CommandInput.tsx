import { useEffect, useState } from "react";
import type { InputMode } from "../../lib/types";

interface Props {
  onSubmit: (text: string) => void;
  /** Input is gated: agent busy, socket down, or a rating is owed. */
  disabled?: boolean;
  connected: boolean;
  awaitingRating: boolean;
  mode: InputMode;
  onModeChange: (mode: InputMode) => void;
  recording: boolean;
  onMicToggle: () => void;
  /** Stop the mic and discard the audio, rather than submitting it. */
  onMicCancel: () => void;
  /** Actionable capture failure (permission, no device, unsupported), or null. */
  micError: string | null;
}

function MicIcon({ active }: { active: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`h-5 w-5 ${active ? "text-[var(--bg)]" : "text-[var(--text-muted)]"}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

const MODES: { value: InputMode; label: string }[] = [
  { value: "text", label: "Type" },
  { value: "voice", label: "Speak" },
];

export function CommandInput({
  onSubmit,
  disabled,
  connected,
  awaitingRating,
  mode,
  onModeChange,
  recording,
  onMicToggle,
  onMicCancel,
  micError,
}: Props) {
  const [value, setValue] = useState("");

  // Leaving voice mode with the mic live would otherwise keep the stream open. Cancel
  // rather than stop: a plain stop submits whatever was captured, and switching modes
  // is not the participant saying "send this".
  useEffect(() => {
    if (mode === "text" && recording) onMicCancel();
  }, [mode, recording, onMicCancel]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
  };

  const placeholder = awaitingRating
    ? "Rate the response above to continue"
    : connected
      ? "Type a message"
      : "Connecting…";

  const voiceHint = awaitingRating
    ? "Rate the response above to continue"
    : recording
      ? "Listening — tap to stop and send"
      : connected
        ? "Tap the microphone to speak"
        : "Connecting…";

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        role="radiogroup"
        aria-label="Input mode"
        className="flex gap-1 rounded-full border border-[var(--border)] bg-[var(--surface)] p-0.5"
      >
        {MODES.map((m) => (
          <button
            key={m.value}
            role="radio"
            aria-checked={mode === m.value}
            onClick={() => onModeChange(m.value)}
            className={`rounded-full px-3 py-1 text-xs transition-colors ${
              mode === m.value
                ? "bg-[var(--surface-raised)] text-[var(--text)]"
                : "text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === "text" ? (
        <div className="flex w-full items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            disabled={disabled}
            placeholder={placeholder}
            className="flex-1 bg-transparent px-1 text-[0.95rem] text-[var(--text)] outline-none placeholder:text-[var(--text-muted)] disabled:cursor-not-allowed"
          />
          <button
            onClick={submit}
            disabled={disabled || value.trim() === ""}
            aria-label="Send message"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--surface-raised)] text-[var(--text-muted)] transition-colors hover:bg-[var(--border)] hover:text-[var(--text)] disabled:opacity-40 disabled:hover:bg-[var(--surface-raised)]"
          >
            <SendIcon />
          </button>
        </div>
      ) : (
        <div className="flex w-full items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
          <button
            onClick={onMicToggle}
            disabled={disabled && !recording}
            aria-label={recording ? "Stop recording and send" : "Start recording"}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-40 ${
              recording
                ? "bg-[var(--accent)]"
                : "bg-[var(--surface-raised)] hover:bg-[var(--border)]"
            }`}
          >
            <MicIcon active={recording} />
          </button>
          {/* A capture failure outranks the hint: "Tap the microphone to speak" next to a
              button that can't work is what made this look like a dead button. */}
          <span
            className={`text-[0.9rem] ${
              micError ? "text-[var(--danger)]" : "text-[var(--text-muted)]"
            }`}
          >
            {micError ?? voiceHint}
          </span>
        </div>
      )}
    </div>
  );
}
