import type { StatCardData } from "../../lib/types";
import { Sparkline } from "./Sparkline";

export function StatCard({ label, value, unit, delta, sparkline }: StatCardData) {
  const deltaUp = delta > 0;
  const deltaFlat = delta === 0;

  return (
    <div className="hud-panel hud-corner-brackets rounded px-3 py-2 flex items-center justify-between gap-2">
      <div>
        <div className="text-[0.6rem] tracking-wider text-slate-400 font-mono">{label}</div>
        <div className="font-condensed text-2xl font-semibold hud-glow-text leading-tight">
          {value}
          {unit && <span className="text-sm text-slate-400 ml-0.5">{unit}</span>}
        </div>
        <div
          className={`text-[0.6rem] font-mono mt-0.5 ${
            deltaFlat ? "text-slate-500" : deltaUp ? "text-emerald-400" : "text-red-400"
          }`}
        >
          {deltaFlat ? "–" : deltaUp ? `▲ +${delta}` : `▼ ${delta}`}
        </div>
      </div>
      <Sparkline values={sparkline} />
    </div>
  );
}
