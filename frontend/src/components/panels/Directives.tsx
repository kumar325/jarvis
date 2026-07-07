import { useState } from "react";
import type { Directive } from "../../lib/types";
import { PanelFrame } from "./PanelFrame";

interface Props {
  directives: Directive[];
}

export function Directives({ directives }: Props) {
  const [overrides, setOverrides] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setOverrides((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <PanelFrame title="DIRECTIVES">
      <ul className="flex flex-col gap-1.5">
        {directives.map((d) => {
          const done = overrides.has(d.id) ? !d.done : d.done;
          return (
            <li key={d.id} className="flex items-start gap-2 text-xs">
              <button
                onClick={() => toggle(d.id)}
                className={`mt-0.5 w-3.5 h-3.5 shrink-0 border rounded-sm ${
                  done ? "bg-accent border-accent" : "border-slate-500"
                }`}
                aria-label={done ? "mark incomplete" : "mark complete"}
              />
              <span className={done ? "text-slate-500 line-through" : "text-slate-300"}>
                {d.label}
              </span>
            </li>
          );
        })}
      </ul>
    </PanelFrame>
  );
}
