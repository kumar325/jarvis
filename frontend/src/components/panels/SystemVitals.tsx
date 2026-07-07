import type { StatCardData } from "../../lib/types";
import { PanelFrame } from "./PanelFrame";
import { StatCard } from "./StatCard";

interface Props {
  vitals: StatCardData[];
}

export function SystemVitals({ vitals }: Props) {
  return (
    <PanelFrame title="SYSTEM VITALS">
      <div className="flex flex-col gap-2">
        {vitals.map((stat) => (
          <StatCard key={stat.id} {...stat} />
        ))}
      </div>
    </PanelFrame>
  );
}
