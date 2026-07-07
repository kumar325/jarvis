import type { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
  className?: string;
}

export function PanelFrame({ title, children, className = "" }: Props) {
  return (
    <div className={`hud-panel rounded p-3 flex flex-col gap-2 ${className}`}>
      <div className="hud-panel-title border-b border-panel-border pb-1.5">{title}</div>
      {children}
    </div>
  );
}
