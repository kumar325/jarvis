import type { WireEvent } from "../../lib/types";
import { PanelFrame } from "./PanelFrame";

interface Props {
  events: WireEvent[];
}

export function AIWire({ events }: Props) {
  return (
    <PanelFrame title="AI WIRE" className="flex-1 min-h-0">
      <ul className="flex flex-col gap-2.5 overflow-y-auto">
        {events.length === 0 && (
          <li className="text-xs text-slate-600 font-mono">no conversation yet this session</li>
        )}
        {events.map((event) => (
          <li key={event.id} className="text-xs">
            <div className="flex items-center gap-2">
              <span
                className={`font-condensed font-semibold tracking-wider text-[0.65rem] ${
                  event.speaker === "USER" ? "text-slate-400" : "hud-glow-text"
                }`}
              >
                {event.speaker}
              </span>
              <span className="text-slate-600 font-mono text-[0.6rem]">{event.timestamp}</span>
            </div>
            <p className="text-slate-300 leading-snug">{event.text}</p>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
