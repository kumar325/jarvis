import type { ReactNode } from "react";

interface Props {
  header: ReactNode;
  controls: ReactNode;
  clock: ReactNode;
  orb: ReactNode;
  conversation: ReactNode;
  rating: ReactNode;
  input: ReactNode;
}

/** Title top-left, mute + time top-right, orb centered, conversation / rating / input below. */
export function Shell({ header, controls, clock, orb, conversation, rating, input }: Props) {
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
        <div className="min-h-0 w-full flex-1">{orb}</div>
        <div className="w-full max-w-2xl">{conversation}</div>
      </div>

      <div className="mx-auto w-full max-w-2xl pt-4">
        {rating}
        {input}
      </div>
    </div>
  );
}
