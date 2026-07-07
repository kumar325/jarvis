import { useAudioCapture } from "../../hooks/useAudioCapture";
import { PanelFrame } from "./PanelFrame";

interface Props {
  onRecorded: (wav: ArrayBuffer) => void;
  disabled?: boolean;
}

export function AudioIO({ onRecorded, disabled }: Props) {
  const { recording, start, stop } = useAudioCapture(onRecorded);

  return (
    <PanelFrame title="AUDIO I/O">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs text-slate-300">
          <span className={`w-1.5 h-1.5 rounded-full ${recording ? "bg-accent" : "bg-slate-600"}`} />
          MIC {recording ? "LIVE" : "STANDBY"}
        </div>
        <button
          onMouseDown={() => !disabled && start()}
          onMouseUp={() => recording && stop()}
          onMouseLeave={() => recording && stop()}
          disabled={disabled}
          className={`rounded-full w-10 h-10 border flex items-center justify-center transition-all disabled:opacity-40 ${
            recording
              ? "border-accent shadow-glow bg-accent/10"
              : "border-slate-600 hover:border-accent"
          }`}
          aria-label="hold to talk"
        >
          <div className={`w-3 h-3 rounded-sm ${recording ? "bg-accent" : "bg-slate-500"}`} />
        </button>
      </div>
      <p className="text-[0.6rem] text-slate-500 font-mono">HOLD TO TALK</p>
    </PanelFrame>
  );
}
