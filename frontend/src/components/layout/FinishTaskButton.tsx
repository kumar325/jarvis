import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  onConfirm: () => void;
  /** Blocked mid-turn or while a response is still owed a thumbs up/down. */
  disabled: boolean;
  /** Why it's blocked, surfaced as the tooltip so a dead-looking button explains itself. */
  disabledReason: string | null;
  /** Sent, waiting on the server to confirm the row reached disk. */
  pending: boolean;
  /** Set when the write failed. The button stays clickable so the boundary can be retried. */
  error: string | null;
}

/** How long an armed button stays armed before returning to rest. Long enough for a
 * deliberate second click, short enough that a stray first click can't sit armed until the
 * moderator happens to press it again later in the task. */
const ARM_TIMEOUT_MS = 4000;

/** Moderator control, not a participant one — it lives up in the header row with the mute
 * toggle rather than beside the input, where a participant reaching for Send could hit it.
 *
 * Deliberately text rather than an icon: this is the one control in the UI whose meaning
 * has to be unambiguous to whoever is running the session.
 *
 * Two-step by design. The survey card used to be the escape hatch for a misclick — you
 * could close it without submitting. With the questions on paper there is no card, so a
 * single click would write a boundary immediately, and a phantom boundary shifts the
 * number of every task after it (the server counts existing rows to assign the next one).
 * Same shape as the two-step delete in tools/files.py, for the same reason. */
const BASE =
  "h-8 rounded-full bg-[var(--surface)] px-3 text-xs transition-colors " +
  "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-[var(--text-muted)]";

/* Gold only while actionable. Keyed on `disabled` rather than on mounting — unlike the
   rating thumbs this button is always in the header, so enablement is the only signal that
   it's live. Static ring, no pulse: it's a moderator control, and a breathing glow would
   draw the participant's eye to it through every idle moment of a task. */
const ENABLED = "border border-[var(--accent)] text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)] hover:text-[var(--text)]";
const DISABLED = "border border-[var(--border)] text-[var(--text-muted)]";
/* Armed and awaiting the confirming click. Brighter than ENABLED so the state change is
   unmistakable at a glance — the moderator is mid-session and not studying the header. */
const ARMED = "border border-[var(--accent)] bg-[var(--accent)] text-[var(--bg)] shadow-[0_0_16px_var(--accent-glow)]";

export function FinishTaskButton({ onConfirm, disabled, disabledReason, pending, error }: Props) {
  const [armed, setArmed] = useState(false);
  const armTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const disarm = useCallback(() => {
    if (armTimerRef.current) {
      clearTimeout(armTimerRef.current);
      armTimerRef.current = null;
    }
    setArmed(false);
  }, []);

  // Losing the gate mid-arm (a reply starts, the socket drops) must not leave a primed
  // button that fires on the next click for a task the moderator has moved on from.
  useEffect(() => {
    if (disabled || pending) disarm();
  }, [disabled, pending, disarm]);

  useEffect(() => () => {
    if (armTimerRef.current) clearTimeout(armTimerRef.current);
  }, []);

  const handleClick = () => {
    if (armed) {
      disarm();
      onConfirm();
      return;
    }
    setArmed(true);
    armTimerRef.current = setTimeout(() => {
      armTimerRef.current = null;
      setArmed(false);
    }, ARM_TIMEOUT_MS);
  };

  const label = pending ? "Saving…" : armed ? "Confirm?" : error ? "Retry" : "Finish Task";

  const title = disabled
    ? (disabledReason ?? undefined)
    : pending
      ? "Waiting for the server to confirm the task was recorded"
      : error
        ? `${error} — click to try again`
        : armed
          ? "Click again to record this task as finished"
          : "Mark this task finished (asks to confirm)";

  return (
    <button
      onClick={handleClick}
      onBlur={disarm}
      disabled={disabled || pending}
      title={title}
      // The label changes without the button moving or remounting, so a moderator watching
      // the header is told what happened without anything else on screen shifting.
      aria-live="polite"
      className={`${BASE} ${disabled || pending ? DISABLED : armed ? ARMED : ENABLED}`}
    >
      {label}
    </button>
  );
}
