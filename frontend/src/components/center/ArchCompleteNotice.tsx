interface Props {
  /** Which arm just finished ("arch1" / "arch2"), straight from the server's session_info. */
  condition: string | null;
  onDismiss: () => void;
}

/** Shown instead of the chat view after the last task's survey, so the moderator sees that
 * this arm is done rather than being dropped back at an input box that looks identical to
 * the one from thirty seconds ago.
 *
 * Dismissable rather than terminal: the session isn't over — the moderator still has to
 * reset state and relabel the backend, and may need the input box back in the meantime
 * (a fourth task still logs honestly as task 4 rather than being silently blocked). */
export function ArchCompleteNotice({ condition, onDismiss }: Props) {
  return (
    <div className="flex h-full items-center justify-center py-4">
      <div className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-7 text-center">
        <span className="text-[0.7rem] uppercase tracking-[0.15em] text-[var(--text-muted)]">
          {condition ?? "Session"}
        </span>
        <h2 className="mt-2 text-base font-medium text-[var(--text)]">
          Arch complete — ready for next phase
        </h2>
        <p className="mt-3 text-xs leading-relaxed text-[var(--text-muted)]">
          All three task surveys are recorded. Reset participant state and relabel the
          backend before starting the next arm.
        </p>
        <button
          onClick={onDismiss}
          className="mt-6 h-8 rounded-lg border border-[var(--border)] px-4 text-xs text-[var(--text-muted)] transition-colors hover:border-[var(--text-muted)] hover:text-[var(--text)]"
        >
          Return to session
        </button>
      </div>
    </div>
  );
}
