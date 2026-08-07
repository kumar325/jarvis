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
export function FinishTaskButton({ onClick, disabled, disabledReason }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={disabled ? (disabledReason ?? undefined) : "Mark this task finished and open the survey"}
      className="h-8 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-[var(--text-muted)]"
    >
      Finish Task
    </button>
  );
}
