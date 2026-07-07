import type { CommandAction } from "../../lib/types";
import { PanelFrame } from "./PanelFrame";

interface Props {
  actions: CommandAction[];
  onTrigger?: (id: string) => void;
}

export function CommandDeck({ actions, onTrigger }: Props) {
  return (
    <PanelFrame title="COMMAND DECK">
      <div className="grid grid-cols-2 gap-1.5">
        {actions.map((action) => (
          <button
            key={action.id}
            onClick={() => onTrigger?.(action.id)}
            className="hud-panel rounded px-2 py-2 text-[0.62rem] font-condensed font-semibold tracking-wider text-slate-300 hover:text-accent hover:shadow-glow transition-all"
          >
            {action.label}
          </button>
        ))}
      </div>
    </PanelFrame>
  );
}
