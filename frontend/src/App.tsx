import { useEffect, useState } from "react";
import { useAccentColor } from "./hooks/useAccentColor";
import { useJarvisSocket } from "./hooks/useJarvisSocket";
import { useAudioCapture } from "./hooks/useAudioCapture";
import { useOrbAmplitude } from "./hooks/useOrbAmplitude";
import { Header } from "./components/layout/Header";
import { ClockStatus } from "./components/layout/ClockStatus";
import { Shell } from "./components/layout/Shell";
import { SystemVitals } from "./components/panels/SystemVitals";
import { Directives } from "./components/panels/Directives";
import { Documents } from "./components/panels/Documents";
import { CommandDeck } from "./components/panels/CommandDeck";
import { AudioIO } from "./components/panels/AudioIO";
import { AIWire } from "./components/panels/AIWire";
import { OrbVisualization } from "./components/center/OrbVisualization";
import { ToolCallCards } from "./components/center/ToolCallCards";
import { CommandInput } from "./components/center/CommandInput";
import { PrimaryDirective } from "./components/center/PrimaryDirective";
import { COMMAND_ACTIONS } from "./lib/mockData";

const TTS_ENABLED_STORAGE_KEY = "jarvis-tts-enabled";

function App() {
  const { accent, setAccent } = useAccentColor();
  const [ttsEnabled, setTtsEnabled] = useState(() => {
    const stored = localStorage.getItem(TTS_ENABLED_STORAGE_KEY);
    return stored === null ? true : stored === "true";
  });
  useEffect(() => {
    localStorage.setItem(TTS_ENABLED_STORAGE_KEY, String(ttsEnabled));
  }, [ttsEnabled]);
  const {
    connected,
    vitals,
    directives,
    documents,
    toolCards,
    wireEvents,
    agentBusy,
    sendText,
    sendAudio,
    isPlaying,
    getPlaybackLevel,
    stopPlayback,
  } = useJarvisSocket(ttsEnabled, setTtsEnabled);
  const { recording, toggle: toggleRecording, getLevel: getMicLevel } = useAudioCapture(sendAudio);

  const handleMicToggle = () => {
    if (!recording && (agentBusy || !connected)) return;
    toggleRecording(() => {
      if (isPlaying) stopPlayback();
    });
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
      <div className="hud-grid-overlay" />
      <div className="hud-scanlines" />
      <div className="hud-vignette" />

      <Shell
        header={<Header />}
        clock={
          <ClockStatus
            accent={accent}
            onAccentChange={setAccent}
            linkStatus={connected ? "ONLINE" : "OFFLINE"}
          />
        }
        leftPanels={
          <>
            <SystemVitals vitals={vitals} />
            <Directives directives={directives} />
            <Documents documents={documents} />
          </>
        }
        rightPanels={
          <>
            <CommandDeck actions={COMMAND_ACTIONS} />
            <AudioIO
              recording={recording}
              onToggle={handleMicToggle}
              disabled={!recording && (agentBusy || !connected)}
              ttsEnabled={ttsEnabled}
            />
            <AIWire events={wireEvents} />
          </>
        }
        center={<OrbVisualization active={agentBusy} amplitude={amplitude} />}
        toolCards={<ToolCallCards cards={toolCards} />}
        commandInput={<CommandInput onSubmit={sendText} disabled={agentBusy || !connected} />}
        primaryDirective={
          <PrimaryDirective
            directive="MAXIMIZE PERSONALIZATION SIGNAL"
            metricLabel="sessions logged"
            metricValue={41}
          />
        }
      />
    </div>
  );
}

export default App;
