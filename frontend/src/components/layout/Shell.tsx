import type { ReactNode } from "react";

interface Props {
  header: ReactNode;
  controls: ReactNode;
  clock: ReactNode;
  orb: ReactNode;
  conversation: ReactNode;
  rating: ReactNode;
  input: ReactNode;
  /** Post-task survey or arch-complete notice. When set it takes over the orb's space and
   * the rating/input row is dropped entirely — the participant can't send anything until
   * the survey is answered, which is the same gate the rating prompt applies per response. */
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

      {overlay ? null : (
        <div className="mx-auto w-full max-w-2xl pt-4">
          {rating}
          {input}
        </div>
      )}
    </div>
  );
}
