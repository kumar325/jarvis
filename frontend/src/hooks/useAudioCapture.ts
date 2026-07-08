import { useCallback, useRef, useState } from "react";
import { blobToWav16kMono } from "../lib/wav-encode";
import { readLevel } from "../lib/audio-level";

export function useAudioCapture(onRecorded: (wav: ArrayBuffer) => void) {
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const levelCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);

  const cleanup = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
    analyserRef.current = null;
    dataRef.current = null;
    levelCtxRef.current?.close().catch(() => {});
    levelCtxRef.current = null;
    setRecording(false);
  }, []);

  const start = useCallback(async () => {
    if (mediaRecorderRef.current) return;

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      console.error("microphone access failed", err);
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];

    // Tap the mic stream for a live amplitude reading (orb reactivity) without playing
    // it back — route through a muted gain so the analyser stays active cross-browser,
    // but nothing is audible.
    try {
      const levelCtx = new AudioContext();
      const source = levelCtx.createMediaStreamSource(stream);
      const analyser = levelCtx.createAnalyser();
      analyser.fftSize = 256;
      const silentGain = levelCtx.createGain();
      silentGain.gain.value = 0;
      source.connect(analyser);
      analyser.connect(silentGain);
      silentGain.connect(levelCtx.destination);

      levelCtxRef.current = levelCtx;
      analyserRef.current = analyser;
      dataRef.current = new Uint8Array(analyser.fftSize);
    } catch (err) {
      console.error("mic level metering unavailable", err);
    }

    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream);
    } catch (err) {
      console.error("MediaRecorder unavailable", err);
      cleanup();
      return;
    }

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onerror = (event) => {
      console.error("recording error", event);
      cleanup();
    };

    recorder.onstop = async () => {
      const chunks = chunksRef.current;
      cleanup();

      if (chunks.length === 0) return;
      try {
        const blob = new Blob(chunks, { type: recorder.mimeType });
        const wav = await blobToWav16kMono(blob);
        onRecorded(await wav.arrayBuffer());
      } catch (err) {
        console.error("failed to encode recorded audio", err);
      }
    };

    mediaRecorderRef.current = recorder;
    recorder.start();
    setRecording(true);
  }, [cleanup, onRecorded]);

  const stop = useCallback(() => {
    try {
      mediaRecorderRef.current?.stop();
    } catch (err) {
      console.error("failed to stop recording", err);
      cleanup();
    }
  }, [cleanup]);

  // Toggle for a press-to-start / press-to-stop mic button. onBeforeStart lets the
  // caller interrupt anything else in progress (e.g. TTS playback) right as a new
  // recording begins, not just once the recording is stopped and sent.
  const toggle = useCallback(
    (onBeforeStart?: () => void) => {
      if (mediaRecorderRef.current) {
        stop();
      } else {
        onBeforeStart?.();
        start();
      }
    },
    [start, stop]
  );

  const getLevel = useCallback(() => {
    const analyser = analyserRef.current;
    const data = dataRef.current;
    if (!analyser || !data) return 0;
    return readLevel(analyser, data);
  }, []);

  return { recording, start, stop, toggle, getLevel };
}
