import { useCallback, useEffect, useState } from "react";
import { useJarvisSocket } from "./hooks/useJarvisSocket";
import { useAudioCapture } from "./hooks/useAudioCapture";
import { useOrbAmplitude } from "./hooks/useOrbAmplitude";
import { Header } from "./components/layout/Header";
import { Clock } from "./components/layout/Clock";
import { MuteButton } from "./components/layout/MuteButton";
import { Shell } from "./components/layout/Shell";
import { OrbVisualization } from "./components/center/OrbVisualization";
import { CommandInput } from "./components/center/CommandInput";
import { Conversation } from "./components/center/Conversation";
import { RatingPrompt } from "./components/center/RatingPrompt";
import type { InputMode } from "./lib/types";

const TTS_ENABLED_STORAGE_KEY = "jarvis-tts-enabled";

function App() {
  const [ttsEnabled, setTtsEnabled] = useState(() => {
    const stored = localStorage.getItem(TTS_ENABLED_STORAGE_KEY);
    return stored === null ? true : stored === "true";
  });
  useEffect(() => {
    localStorage.setItem(TTS_ENABLED_STORAGE_KEY, String(ttsEnabled));
  }, [ttsEnabled]);

  const [inputMode, setInputMode] = useState<InputMode>("text");

  // vitals/directives/documents/toolCards still arrive over the socket but are
  // deliberately not rendered — participants must not see internal state.
  const {
    connected,
    wireEvents,
    agentBusy,
    pendingRatingId,
    sendText,
    sendAudio,
    sendRating,
    sendTtsState,
    isPlaying,
    getPlaybackLevel,
    stopPlayback,
  } = useJarvisSocket(ttsEnabled, setTtsEnabled);
  const {
    recording,
    toggle: toggleRecording,
    cancel: cancelRecording,
    getLevel: getMicLevel,
  } = useAudioCapture(sendAudio);

  const awaitingRating = pendingRatingId !== null;
  const inputDisabled = agentBusy || !connected || awaitingRating;
  const micDisabled = !recording && inputDisabled;

  const handleMicToggle = useCallback(() => {
    if (micDisabled) return;
    toggleRecording(() => {
      if (isPlaying) stopPlayback();
    });
  }, [micDisabled, toggleRecording, isPlaying, stopPlayback]);

  const handleTtsToggle = () => {
    const next = !ttsEnabled;
    setTtsEnabled(next);
    // Also told to the server so a muted session skips synthesis entirely rather than
    // sending audio the browser throws away.
    sendTtsState(next);
    if (!next) stopPlayback();
  };

  const amplitude = useOrbAmplitude({
    recording,
    getMicLevel,
    isPlaying,
    getPlaybackLevel,
    agentBusy,
  });

  return (
    <div className="h-screen w-screen bg-[var(--bg)]">
      <Shell
        header={<Header />}
        controls={<MuteButton ttsEnabled={ttsEnabled} onToggle={handleTtsToggle} />}
        clock={<Clock />}
        orb={<OrbVisualization active={agentBusy} amplitude={amplitude} />}
        conversation={<Conversation events={wireEvents} thinking={agentBusy} />}
        rating={awaitingRating ? <RatingPrompt onRate={sendRating} /> : null}
        input={
          <CommandInput
            onSubmit={sendText}
            disabled={inputDisabled}
            connected={connected}
            awaitingRating={awaitingRating}
            mode={inputMode}
            onModeChange={setInputMode}
            recording={recording}
            onMicToggle={handleMicToggle}
            onMicCancel={cancelRecording}
          />
        }
      />
    </div>
  );
}

export default App;
