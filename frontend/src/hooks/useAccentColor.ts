import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "jarvis:accent";
const DEFAULT_ACCENT = "#D4A244";

export const ACCENT_PRESETS = [
  { name: "gold", value: "#D4A244" },
  { name: "cyan", value: "#00E5FF" },
  { name: "green", value: "#39FF14" },
  { name: "red", value: "#FF3131" },
  { name: "purple", value: "#BF5FFF" },
];

function applyAccent(hex: string) {
  document.documentElement.style.setProperty("--accent", hex);
}

export function useAccentColor() {
  const [accent, setAccentState] = useState<string>(() => {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_ACCENT;
  });

  useEffect(() => {
    applyAccent(accent);
  }, [accent]);

  const setAccent = useCallback((hex: string) => {
    setAccentState(hex);
    localStorage.setItem(STORAGE_KEY, hex);
  }, []);

  return { accent, setAccent };
}
