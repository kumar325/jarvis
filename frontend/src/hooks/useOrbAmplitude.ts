import { useEffect, useRef, useState } from "react";

interface Sources {
  recording: boolean;
  getMicLevel: () => number;
  isPlaying: boolean;
  getPlaybackLevel: () => number;
  agentBusy: boolean;
}

const IDLE_THINKING_LEVEL = 0.3;
const SMOOTHING = 0.3;

/** Live 0-1 amplitude for the orb: real mic level while recording, real TTS playback
 * level while speaking, a modest synthetic "thinking" pulse while awaiting a reply,
 * else idle. Smoothed so the orb doesn't jitter frame to frame. */
export function useOrbAmplitude({
  recording,
  getMicLevel,
  isPlaying,
  getPlaybackLevel,
  agentBusy,
}: Sources): number {
  const [amplitude, setAmplitude] = useState(0);
  const frameRef = useRef<number>();

  useEffect(() => {
    const tick = () => {
      let target = 0;
      if (recording) {
        target = getMicLevel();
      } else if (isPlaying) {
        target = getPlaybackLevel();
      } else if (agentBusy) {
        target = IDLE_THINKING_LEVEL;
      }

      setAmplitude((prev) => prev + (target - prev) * SMOOTHING);
      frameRef.current = requestAnimationFrame(tick);
    };

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [recording, getMicLevel, isPlaying, getPlaybackLevel, agentBusy]);

  return amplitude;
}
