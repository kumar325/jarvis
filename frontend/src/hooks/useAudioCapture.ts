import { useCallback, useRef, useState } from "react";
import { blobToWav16kMono } from "../lib/wav-encode";
import { readLevel } from "../lib/audio-level";

/** Turn a getUserMedia rejection into something a participant can act on.
 *
 * These all used to dead-end in console.error, so a blocked mic looked identical to a
 * dead button — the participant taps, nothing happens, and the session runner has no way
 * to tell permission from missing hardware without opening DevTools. */
function micErrorMessage(err: unknown): string {
  switch ((err as { name?: string })?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone blocked. Allow it via the icon in the address bar, then reload.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No microphone found. Connect one and try again.";
    case "NotReadableError":
      return "The microphone is in use by another app. Close it and try again.";
    default:
      return "Couldn't start the microphone. Check your browser's audio settings.";
  }
}

export function useAudioCapture(onRecorded: (wav: ArrayBuffer) => void) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const levelCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  // Set by cancel() so the recorder's onstop tears down without sending what it captured.
  // MediaRecorder has no "stop without emitting" of its own.
  const discardRef = useRef(false);

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
    setError(null);

    // Absent outside a secure context — http:// on anything but localhost. Reading
    // .getUserMedia off undefined would throw a TypeError that reads like a bug.
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Recording needs a secure connection — use localhost or https.");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      console.error("microphone access failed", err);
      setError(micErrorMessage(err));
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];
    discardRef.current = false;

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
      setError("Recording isn't supported in this browser.");
      cleanup();
      return;
    }

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onerror = (event) => {
      console.error("recording error", event);
      setError("Recording stopped unexpectedly. Try again.");
      cleanup();
    };

    recorder.onstop = async () => {
      const chunks = chunksRef.current;
      const discard = discardRef.current;
      discardRef.current = false;
      cleanup();

      if (discard) return;
      if (chunks.length === 0) {
        setError("Didn't capture any audio — try holding the button a moment longer.");
        return;
      }
      try {
        const blob = new Blob(chunks, { type: recorder.mimeType });
        const wav = await blobToWav16kMono(blob);
        onRecorded(await wav.arrayBuffer());
      } catch (err) {
        console.error("failed to encode recorded audio", err);
        setError("Couldn't process that recording. Try again.");
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

  // Stop the mic and throw the recording away — used when the participant leaves voice
  // mode mid-recording, where a plain stop() would submit a turn they didn't mean to send.
  const cancel = useCallback(() => {
    if (!mediaRecorderRef.current) return;
    discardRef.current = true;
    stop();
  }, [stop]);

  const getLevel = useCallback(() => {
    const analyser = analyserRef.current;
    const data = dataRef.current;
    if (!analyser || !data) return 0;
    return readLevel(analyser, data);
  }, []);

  return { recording, error, start, stop, cancel, toggle, getLevel };
}
