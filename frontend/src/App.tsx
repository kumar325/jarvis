import { useAccentColor } from "./hooks/useAccentColor";
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
import { PrimaryDirective } from "./components/center/PrimaryDirective";
import {
  MOCK_VITALS,
  MOCK_DIRECTIVES,
  MOCK_DOCUMENTS,
  COMMAND_ACTIONS,
  MOCK_WIRE,
  MOCK_TOOL_CARDS,
} from "./lib/mockData";

function App() {
  const { accent, setAccent } = useAccentColor();

  return (
    <div className="h-screen w-screen bg-[var(--bg)]">
      <div className="hud-grid-overlay" />
      <div className="hud-scanlines" />
      <div className="hud-vignette" />

      <Shell
        header={<Header />}
        clock={<ClockStatus accent={accent} onAccentChange={setAccent} />}
        leftPanels={
          <>
            <SystemVitals vitals={MOCK_VITALS} />
            <Directives directives={MOCK_DIRECTIVES} />
            <Documents documents={MOCK_DOCUMENTS} />
          </>
        }
        rightPanels={
          <>
            <CommandDeck actions={COMMAND_ACTIONS} />
            <AudioIO />
            <AIWire events={MOCK_WIRE} />
          </>
        }
        center={<OrbVisualization />}
        toolCards={<ToolCallCards cards={MOCK_TOOL_CARDS} />}
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
