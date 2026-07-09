// Client-side mirror of backend/server.py's parse_tts_command — used only to decide
// whether to set agentBusy, since the actual mute/unmute toggle is always applied
// server-side (the backend intercepts the same phrases before calling ask_jarvis()).
// Keep these patterns in sync with server.py's _UNMUTE_PATTERNS / _MUTE_PATTERNS.
const UNMUTE_PATTERNS = [
  /\btalk on\b/, /\bstart talking\b/, /\bunmute\b/, /\bspeak up\b/,
  /\bvoice on\b/, /\bturn on (the )?voice\b/,
];
const MUTE_PATTERNS = [
  /\btalk off\b/, /\bstop talking\b/, /\bmute\b/, /\bbe quiet\b/, /\bgo silent\b/,
  /\bvoice off\b/, /\bturn off (the )?voice\b/,
];

/** True for an unmute command, false for a mute command, null if not a TTS toggle. */
export function parseTtsCommand(text: string): boolean | null {
  const normalized = text.trim().toLowerCase().replace(/[.!?]+$/, "");
  if (UNMUTE_PATTERNS.some((p) => p.test(normalized))) return true;
  if (MUTE_PATTERNS.some((p) => p.test(normalized))) return false;
  return null;
}
