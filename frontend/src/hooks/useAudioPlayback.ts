import { useCallback, useRef } from "react";

export function useAudioPlayback() {
  const ctxRef = useRef<AudioContext | null>(null);

  const play = useCallback(async (bytes: ArrayBuffer) => {
    const ctx = ctxRef.current ?? new AudioContext();
    ctxRef.current = ctx;
    if (ctx.state === "suspended") await ctx.resume();

    const audioBuffer = await ctx.decodeAudioData(bytes.slice(0));
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    source.start();
  }, []);

  return { play };
}
