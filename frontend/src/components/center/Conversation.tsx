import { useEffect, useRef } from "react";
import type { WireEvent } from "../../lib/types";

interface Props {
  events: WireEvent[];
  thinking: boolean;
}

export function Conversation({ events, thinking }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  // The socket keeps events newest-first; a transcript reads oldest-first.
  const ordered = [...events].reverse();

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length, thinking]);

  if (ordered.length === 0 && !thinking) return null;

  return (
    <div className="max-h-[38vh] w-full overflow-y-auto">
      <div className="flex flex-col gap-3 py-2 pr-1">
        {ordered.map((event) =>
          event.speaker === "USER" ? (
            <div
              key={event.id}
              className="max-w-[85%] self-end rounded-2xl bg-[var(--surface-raised)] px-4 py-2 text-[0.95rem] leading-relaxed"
            >
              {event.text}
            </div>
          ) : (
            <div
              key={event.id}
              className="max-w-[85%] self-start px-1 text-[0.95rem] leading-relaxed text-[var(--text)]"
            >
              {event.text}
            </div>
          )
        )}

        {thinking && (
          <div className="flex items-center gap-1.5 self-start px-1 py-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="thinking-dot h-1.5 w-1.5 rounded-full bg-[var(--text-muted)]"
                style={{ animationDelay: `${i * 0.18}s` }}
              />
            ))}
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
}
