import { useEffect, useState } from "react";

/** Plain time + date. No system/backend status is surfaced to the participant. */
export function Clock() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const time = now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const date = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  return (
    <div className="select-none text-right leading-tight">
      <div className="text-base font-medium tabular-nums text-[var(--text)]">{time}</div>
      <div className="text-xs text-[var(--text-muted)]">{date}</div>
    </div>
  );
}
