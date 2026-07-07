import { useState } from "react";

interface Props {
  onSubmit: (text: string) => void;
  disabled?: boolean;
}

export function CommandInput({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState("");

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
  };

  return (
    <div className="hud-panel rounded px-3 py-1.5 flex items-center gap-2 w-full max-w-xl">
      <span className="hud-glow-text font-mono text-sm">{">"}</span>
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        disabled={disabled}
        placeholder={disabled ? "AWAITING RESPONSE..." : "ISSUE A DIRECTIVE..."}
        className="flex-1 bg-transparent outline-none font-mono text-sm text-slate-200 placeholder:text-slate-600 tracking-wide"
      />
    </div>
  );
}
