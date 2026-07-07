import { useEffect, useState } from "react";
import { ColorPicker } from "../common/ColorPicker";
import type { SystemStatus } from "../../lib/types";

interface StatusChip {
  label: string;
  status: SystemStatus;
}

function statusColor(status: SystemStatus) {
  switch (status) {
    case "ONLINE":
    case "ALIVE":
      return "bg-emerald-400";
    case "BUSY":
      return "bg-accent";
    case "OFFLINE":
      return "bg-red-400";
    default:
      return "bg-slate-500";
  }
}

interface Props {
  accent: string;
  onAccentChange: (hex: string) => void;
  linkStatus?: SystemStatus;
}

export function ClockStatus({ accent, onAccentChange, linkStatus = "ONLINE" }: Props) {
  const [now, setNow] = useState(new Date());

  const statusChips: StatusChip[] = [
    { label: "CORE", status: "IDLE" },
    { label: "LINK", status: linkStatus },
    { label: "RUNNER", status: "ALIVE" },
  ];

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const time = now.toLocaleTimeString("en-US", { hour12: false });
  const date = now.toLocaleDateString("en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "2-digit",
  });

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-3">
        <div className="text-right">
          <div className="font-condensed text-xl font-semibold hud-glow-text tabular-nums">
            {time}
          </div>
          <div className="font-mono text-[0.6rem] text-slate-400 tracking-wider">{date}</div>
        </div>
        <ColorPicker accent={accent} onChange={onAccentChange} />
      </div>
      <div className="flex gap-2">
        {statusChips.map((chip) => (
          <div
            key={chip.label}
            className="hud-panel flex items-center gap-1.5 px-2 py-1 rounded text-[0.6rem] tracking-wider"
          >
            <span className={`w-1.5 h-1.5 rounded-full ${statusColor(chip.status)}`} />
            {chip.label} - {chip.status}
          </div>
        ))}
      </div>
    </div>
  );
}
