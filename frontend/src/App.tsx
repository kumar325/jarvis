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

function App() {
  const { accent, setAccent } = useAccentColor();
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
  } = useJarvisSocket();
  const { recording, start, stop, getLevel: getMicLevel } = useAudioCapture(sendAudio);
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
              onStart={start}
              onStop={stop}
              disabled={agentBusy || !connected}
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
