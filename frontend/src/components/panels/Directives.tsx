import { useState } from "react";
import type { Directive } from "../../lib/types";
import { PanelFrame } from "./PanelFrame";

interface Props {
  directives: Directive[];
}

export function Directives({ directives: initial }: Props) {
  const [directives, setDirectives] = useState(initial);

  const toggle = (id: string) => {
    setDirectives((prev) =>
      prev.map((d) => (d.id === id ? { ...d, done: !d.done } : d))
    );
  };

  return (
    <PanelFrame title="DIRECTIVES">
      <ul className="flex flex-col gap-1.5">
        {directives.map((d) => (
          <li key={d.id} className="flex items-start gap-2 text-xs">
            <button
              onClick={() => toggle(d.id)}
              className={`mt-0.5 w-3.5 h-3.5 shrink-0 border rounded-sm ${
                d.done ? "bg-accent border-accent" : "border-slate-500"
              }`}
              aria-label={d.done ? "mark incomplete" : "mark complete"}
            />
            <span className={d.done ? "text-slate-500 line-through" : "text-slate-300"}>
              {d.label}
            </span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
