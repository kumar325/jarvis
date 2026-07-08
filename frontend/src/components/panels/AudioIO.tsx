import { PanelFrame } from "./PanelFrame";

interface Props {
  recording: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function AudioIO({ recording, onToggle, disabled }: Props) {
  return (
    <PanelFrame title="AUDIO I/O">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs text-slate-300">
          <span className={`w-1.5 h-1.5 rounded-full ${recording ? "bg-accent animate-pulse" : "bg-slate-600"}`} />
          MIC {recording ? "LIVE" : "STANDBY"}
        </div>
        <button
          onClick={onToggle}
          disabled={disabled}
          className={`rounded-full w-10 h-10 border flex items-center justify-center transition-all disabled:opacity-40 ${
            recording
              ? "border-accent shadow-glow bg-accent/10 animate-pulse"
              : "border-slate-600 hover:border-accent"
          }`}
          aria-label={recording ? "stop recording" : "start recording"}
        >
          <div className={`w-3 h-3 rounded-sm ${recording ? "bg-accent" : "bg-slate-500"}`} />
        </button>
      </div>
      <p className="text-[0.6rem] text-slate-500 font-mono">{recording ? "TAP TO STOP" : "TAP TO TALK"}</p>
    </PanelFrame>
  );
}
