import { useState } from "react";
import type { ToolCallCard } from "../../lib/types";

interface Props {
  cards: ToolCallCard[];
}

export function ToolCallCards({ cards }: Props) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const visible = cards.filter((c) => !dismissed.has(c.id));
  if (visible.length === 0) return null;

  return (
    <div className="flex gap-2 flex-wrap justify-center px-4">
      {visible.map((card) => (
        <div
          key={card.id}
          className="hud-panel rounded px-3 py-1.5 flex items-center gap-2 text-[0.65rem] font-mono"
        >
          <span className="hud-glow-text font-semibold">{card.toolName}</span>
          <span className="text-slate-400 truncate max-w-[220px]">{card.preview}</span>
          <span className="text-slate-600">{card.timestamp}</span>
          <button
            onClick={() => setDismissed((prev) => new Set(prev).add(card.id))}
            className="text-slate-500 hover:text-accent ml-1"
            aria-label="dismiss"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
