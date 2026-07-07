import { useCallback, useRef, useState } from "react";
import { readLevel } from "../lib/audio-level";

export function useAudioPlayback() {
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const ensureGraph = useCallback(() => {
    const ctx = ctxRef.current ?? new AudioContext();
    ctxRef.current = ctx;

    if (!analyserRef.current) {
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.connect(ctx.destination);
      analyserRef.current = analyser;
      dataRef.current = new Uint8Array(analyser.fftSize);
    }

    return { ctx, analyser: analyserRef.current };
  }, []);

  const play = useCallback(
    async (bytes: ArrayBuffer) => {
      const { ctx, analyser } = ensureGraph();
      if (ctx.state === "suspended") await ctx.resume();

      const audioBuffer = await ctx.decodeAudioData(bytes.slice(0));
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(analyser);
      source.onended = () => setIsPlaying(false);
      setIsPlaying(true);
      source.start();
    },
    [ensureGraph]
  );

  const getLevel = useCallback(() => {
    const analyser = analyserRef.current;
    const data = dataRef.current;
    if (!analyser || !data) return 0;
    return readLevel(analyser, data);
  }, []);

  return { play, isPlaying, getLevel };
}
