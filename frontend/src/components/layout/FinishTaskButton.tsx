interface Props {
  onClick: () => void;
  /** Blocked mid-turn or while a response is still owed a thumbs up/down. */
  disabled: boolean;
  /** Why it's blocked, surfaced as the tooltip so a dead-looking button explains itself. */
  disabledReason: string | null;
}

/** Moderator control, not a participant one — it lives up in the header row with the mute
 * toggle rather than beside the input, where a participant reaching for Send could hit it.
 *
 * Deliberately text rather than an icon: this is the one control in the UI whose meaning
 * has to be unambiguous to whoever is running the session. */
const BASE =
  "h-8 rounded-full bg-[var(--surface)] px-3 text-xs transition-colors " +
  "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-[var(--text-muted)]";

/* Gold only while actionable. Keyed on `disabled` rather than on mounting — unlike the
   rating thumbs this button is always in the header, so enablement is the only signal that
   it's live. Static ring, no pulse: it's a moderator control, and a breathing glow would
   draw the participant's eye to it through every idle moment of a task. */
const ENABLED = "border border-[var(--accent)] text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)] hover:text-[var(--text)]";
const DISABLED = "border border-[var(--border)] text-[var(--text-muted)]";

export function FinishTaskButton({ onClick, disabled, disabledReason }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={disabled ? (disabledReason ?? undefined) : "Mark this task finished and open the survey"}
      className={`${BASE} ${disabled ? DISABLED : ENABLED}`}
    >
      Finish Task
    </button>
  );
}
