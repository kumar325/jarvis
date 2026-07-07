import type { ReactNode } from "react";

interface Props {
  header: ReactNode;
  clock: ReactNode;
  leftPanels: ReactNode;
  rightPanels: ReactNode;
  center: ReactNode;
  toolCards: ReactNode;
  commandInput: ReactNode;
  primaryDirective: ReactNode;
}

export function Shell({
  header,
  clock,
  leftPanels,
  rightPanels,
  center,
  toolCards,
  commandInput,
  primaryDirective,
}: Props) {
  return (
    <div className="relative z-10 h-full w-full grid grid-cols-[300px_1fr_300px] grid-rows-[auto_1fr_auto] gap-4 p-5">
      <div className="col-start-1 row-start-1">{header}</div>
      <div className="col-start-3 row-start-1 flex justify-end">{clock}</div>

      <div className="col-start-1 row-start-2 flex flex-col gap-4 overflow-y-auto min-h-0">
        {leftPanels}
      </div>

      <div className="col-start-2 row-start-2 flex flex-col min-h-0">
        <div className="flex-1 min-h-0">{center}</div>
        <div className="pb-2">{toolCards}</div>
      </div>

      <div className="col-start-3 row-start-2 flex flex-col gap-4 overflow-y-auto min-h-0">
        {rightPanels}
      </div>

      <div className="col-start-2 row-start-3 flex flex-col items-center gap-3 pb-2">
        {commandInput}
        {primaryDirective}
      </div>
    </div>
  );
}
