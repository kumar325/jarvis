interface Props {
  directive: string;
  metricLabel: string;
  metricValue: number;
}

export function PrimaryDirective({ directive, metricLabel, metricValue }: Props) {
  return (
    <div className="flex flex-col items-center text-center gap-1">
      <span className="font-mono text-[0.6rem] tracking-[0.2em] text-slate-500">
        PRIMARY DIRECTIVE
      </span>
      <span className="font-condensed text-3xl font-bold hud-glow-text">{directive}</span>
      <span className="font-mono text-[0.65rem] text-slate-400">
        {metricValue.toLocaleString()} {metricLabel}
      </span>
    </div>
  );
}
