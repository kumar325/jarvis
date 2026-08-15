import type { ReactNode } from "react";

interface Props {
  header: ReactNode;
  controls: ReactNode;
  clock: ReactNode;
  orb: ReactNode;
  conversation: ReactNode;
  rating: ReactNode;
  input: ReactNode;
  /** The arch-complete notice. When set it takes over the orb's space and the rating/input
   * row is dropped entirely — the participant can't send anything until it's dismissed,
   * which is the same gate the rating prompt applies per response. */
  overlay?: ReactNode;
}

/** Title top-left, mute + time top-right, orb centered, conversation / rating / input below. */
export function Shell({ header, controls, clock, orb, conversation, rating, input, overlay }: Props) {
  return (
    <div className="flex h-full w-full flex-col px-6 py-5">
      <div className="flex items-start justify-between">
        {header}
        <div className="flex items-center gap-3">
          {controls}
          {clock}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col items-center">
        <div className="min-h-0 w-full flex-1">{overlay ?? orb}</div>
        <div className="w-full max-w-2xl">{conversation}</div>
      </div>

      {/* pb-12 lifts the rating + input row ~0.5in off the bottom edge. Padding rather than
          a fixed height or absolute position: this is a full-height flex column, so the
          orb/conversation area above absorbs the offset instead of the input sliding under
          the viewport edge on a short screen. */}
      {overlay ? null : (
        <div className="mx-auto w-full max-w-2xl pt-4 pb-12">
          {rating}
          {input}
        </div>
      )}
    </div>
  );
}
