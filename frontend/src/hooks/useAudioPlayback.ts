import { useCallback, useEffect, useRef, useState } from "react";
import { readLevel } from "../lib/audio-level";

export function useAudioPlayback(enabled: boolean) {
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  // A ref (not a `play` dependency) so toggling TTS never changes play's identity —
  // useJarvisSocket's socket-setup effect depends on `play`, and we don't want a mute
  // toggle to tear down and reconnect the websocket.
  const enabledRef = useRef(enabled);
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

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

  const stop = useCallback(() => {
    const source = sourceRef.current;
    sourceRef.current = null;
    if (source) {
      try {
        source.stop();
      } catch {
        // already stopped/ended — nothing to do
      }
      source.disconnect();
    }
    setIsPlaying(false);
  }, []);

  const play = useCallback(
    async (bytes: ArrayBuffer) => {
      if (!enabledRef.current) return;

      // Never let two replies play at once — cut off whatever's currently speaking.
      stop();

      const { ctx, analyser } = ensureGraph();
      if (ctx.state === "suspended") await ctx.resume();

      const audioBuffer = await ctx.decodeAudioData(bytes.slice(0));
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(analyser);
      source.onended = () => {
        setIsPlaying(false);
        if (sourceRef.current === source) sourceRef.current = null;
      };
      sourceRef.current = source;
      setIsPlaying(true);
      source.start();
    },
    [ensureGraph, stop]
  );

  const getLevel = useCallback(() => {
    const analyser = analyserRef.current;
    const data = dataRef.current;
    if (!analyser || !data) return 0;
    return readLevel(analyser, data);
  }, []);

  return { play, stop, isPlaying, getLevel };
}
