import { useCallback, useRef, useState } from "react";
import { blobToWav16kMono } from "../lib/wav-encode";

export function useAudioCapture(onRecorded: (wav: ArrayBuffer) => void) {
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const cleanup = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
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

  return { recording, start, stop };
}
