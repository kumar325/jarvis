interface Props {
  ttsEnabled: boolean;
  onToggle: () => void;
}

function SpeakerIcon({ muted }: { muted: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      {muted ? (
        <>
          <path d="m16 9 5 6" />
          <path d="m21 9-5 6" />
        </>
      ) : (
        <>
          <path d="M15.5 8.5a5 5 0 0 1 0 7" />
          <path d="M18.5 5.5a9 9 0 0 1 0 13" />
        </>
      )}
    </svg>
  );
}

/** Session-scoped mute for Jarvis's voice. Muting is applied server-side too, so a muted
 * session doesn't spend time synthesizing audio the browser would discard. */
export function MuteButton({ ttsEnabled, onToggle }: Props) {
  return (
    <button
      onClick={onToggle}
      aria-label={ttsEnabled ? "Mute voice output" : "Unmute voice output"}
      aria-pressed={!ttsEnabled}
      className={`flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border)] transition-colors ${
        ttsEnabled
          ? "bg-[var(--surface)] text-[var(--text-muted)] hover:text-[var(--text)]"
          : "bg-[var(--surface-raised)] text-[var(--text)]"
      }`}
    >
      <SpeakerIcon muted={!ttsEnabled} />
    </button>
  );
}
