import type { WireEvent } from "../../lib/types";
import { PanelFrame } from "./PanelFrame";

interface Props {
  events: WireEvent[];
}

export function AIWire({ events }: Props) {
  return (
    <PanelFrame title="AI WIRE" className="flex-1 min-h-0">
      <ul className="flex flex-col gap-2 overflow-y-auto">
        {events.length === 0 && (
          <li className="text-xs text-slate-600 font-mono">no activity yet this session</li>
        )}
        {events.map((event) => (
          <li key={event.id} className="text-xs">
            <span className="text-slate-500 font-mono text-[0.6rem]">{event.timestamp}</span>
            <p className="text-slate-300 leading-snug">▸ {event.text}</p>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
