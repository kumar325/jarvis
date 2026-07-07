import { useState } from "react";
import { ACCENT_PRESETS } from "../../hooks/useAccentColor";

interface Props {
  accent: string;
  onChange: (hex: string) => void;
}

export function ColorPicker({ accent, onChange }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-6 h-6 rounded-full border border-accent shadow-glow"
        style={{ background: accent }}
        aria-label="Change accent color"
      />
      {open && (
        <div className="hud-panel absolute right-0 mt-2 p-3 flex gap-2 z-50 rounded">
          {ACCENT_PRESETS.map((preset) => (
            <button
              key={preset.name}
              onClick={() => {
                onChange(preset.value);
                setOpen(false);
              }}
              title={preset.name}
              className="w-5 h-5 rounded-full border border-white/20 hover:scale-110 transition-transform"
              style={{ background: preset.value }}
            />
          ))}
          <input
            type="color"
            value={accent}
            onChange={(e) => onChange(e.target.value)}
            className="w-5 h-5 bg-transparent border-none cursor-pointer"
            title="custom"
          />
        </div>
      )}
    </div>
  );
}
