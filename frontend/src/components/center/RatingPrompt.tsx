import type { Rating } from "../../lib/types";

interface Props {
  onRate: (rating: Rating) => void;
}

function ThumbIcon({ down }: { down?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`h-4 w-4 ${down ? "rotate-180" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M7 22V11l5-9a2.5 2.5 0 0 1 2.4 3.2L13.5 9h4.8a2.2 2.2 0 0 1 2.1 2.8l-1.9 8A2.2 2.2 0 0 1 16.4 22H7Z" />
      <path d="M7 11H4.5A1.5 1.5 0 0 0 3 12.5v8A1.5 1.5 0 0 0 4.5 22H7" />
    </svg>
  );
}

/* Gold ring + breathing glow, matching the orb. Both read --accent rather than the literal,
   so retuning the token moves the orb and these together. The glow needs no conditional:
   RatingPrompt mounts only while awaitingRating is true, so it arrives and leaves with the
   prompt itself. */
const RATING_BUTTON =
  "rating-glow flex h-8 w-8 items-center justify-center rounded-full border " +
  "border-[var(--accent)] bg-[var(--surface)] text-[var(--accent)] transition-colors " +
  "hover:bg-[var(--surface-raised)] hover:text-[var(--text)]";

/** Shown after every model response. Input stays disabled until one of these is clicked,
 * so each exchange in the study carries a rating. */
export function RatingPrompt({ onRate }: Props) {
  return (
    <div className="flex items-center justify-center gap-3 py-1">
      <span className="text-xs text-[var(--text-muted)]">Was this response helpful?</span>
      <button
        onClick={() => onRate("up")}
        aria-label="Rate this response helpful"
        className={RATING_BUTTON}
      >
        <ThumbIcon />
      </button>
      <button
        onClick={() => onRate("down")}
        aria-label="Rate this response unhelpful"
        className={RATING_BUTTON}
      >
        <ThumbIcon down />
      </button>
    </div>
  );
}
