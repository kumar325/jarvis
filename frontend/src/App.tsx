import { useCallback, useEffect, useState } from "react";
import { useJarvisSocket } from "./hooks/useJarvisSocket";
import { useAudioCapture } from "./hooks/useAudioCapture";
import { useOrbAmplitude } from "./hooks/useOrbAmplitude";
import { Header } from "./components/layout/Header";
import { Clock } from "./components/layout/Clock";
import { MuteButton } from "./components/layout/MuteButton";
import { FinishTaskButton } from "./components/layout/FinishTaskButton";
import { Shell } from "./components/layout/Shell";
import { OrbVisualization } from "./components/center/OrbVisualization";
import { CommandInput } from "./components/center/CommandInput";
import { Conversation } from "./components/center/Conversation";
import { RatingPrompt } from "./components/center/RatingPrompt";
import { TaskSurvey } from "./components/center/TaskSurvey";
import { ArchCompleteNotice } from "./components/center/ArchCompleteNotice";
import type { InputMode } from "./lib/types";

const TTS_ENABLED_STORAGE_KEY = "jarvis-tts-enabled";

/** Matches backend/surveys.py's TASKS_PER_ARCH — used for the "Task N of 3" label only;
 * whether the arm is actually complete is decided server-side from the survey log. */
const TASKS_PER_ARCH = 3;

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
    condition,
    wireEvents,
    agentBusy,
    pendingRatingId,
    taskState,
    surveySubmitting,
    surveyError,
    surveyRecorded,
    sendText,
    sendAudio,
    sendRating,
    sendSurvey,
    acknowledgeSurveyRecorded,
    sendTtsState,
    isPlaying,
    getPlaybackLevel,
    stopPlayback,
  } = useJarvisSocket(ttsEnabled, setTtsEnabled);
  const {
    recording,
    error: micError,
    toggle: toggleRecording,
    cancel: cancelRecording,
    getLevel: getMicLevel,
  } = useAudioCapture(sendAudio);

  const awaitingRating = pendingRatingId !== null;
  const inputDisabled = agentBusy || !connected || awaitingRating;
  const micDisabled = !recording && inputDisabled;

  // The moderator has marked a task finished; the survey card is up.
  const [surveyOpen, setSurveyOpen] = useState(false);
  // The last task of this arm has been surveyed — shown instead of dropping straight back
  // to an input box that looks no different from before.
  const [archCompleteShown, setArchCompleteShown] = useState(false);

  // The server confirmed the survey reached disk. Only then does the card come down; a
  // failed write leaves it up with the answers intact (see useJarvisSocket's survey_error).
  useEffect(() => {
    if (!surveyRecorded) return;
    setSurveyOpen(false);
    if (surveyRecorded.archComplete) setArchCompleteShown(true);
    acknowledgeSurveyRecorded();
  }, [surveyRecorded, acknowledgeSurveyRecorded]);

  // A live mic behind the survey card would keep recording something nobody can send, and
  // would still be running when the chat view comes back.
  const handleFinishTask = useCallback(() => {
    if (recording) cancelRecording();
    if (isPlaying) stopPlayback();
    setSurveyOpen(true);
  }, [recording, cancelRecording, isPlaying, stopPlayback]);

  // Gated on the same conditions as the input, minus the survey itself: finishing a task
  // mid-reply would survey a task whose last answer hasn't landed, and finishing while a
  // response is owed a thumbs up/down would drop that rating — the per-response rating
  // stays mandatory regardless of this feature.
  const finishTaskBlockedReason = !connected
    ? "Not connected"
    : agentBusy
      ? "Wait for the current response"
      : awaitingRating
        ? "Rate the last response first"
        : null;

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
        controls={
          <>
            <FinishTaskButton
              onClick={handleFinishTask}
              disabled={surveyOpen || archCompleteShown || finishTaskBlockedReason !== null}
              disabledReason={finishTaskBlockedReason}
            />
            <MuteButton ttsEnabled={ttsEnabled} onToggle={handleTtsToggle} />
          </>
        }
        clock={<Clock />}
        orb={<OrbVisualization active={agentBusy} amplitude={amplitude} speaking={isPlaying} />}
        conversation={<Conversation events={wireEvents} thinking={agentBusy} />}
        rating={awaitingRating ? <RatingPrompt onRate={sendRating} /> : null}
        overlay={
          surveyOpen ? (
            <TaskSurvey
              taskNumber={taskState.nextTask}
              totalTasks={TASKS_PER_ARCH}
              onSubmit={sendSurvey}
              submitting={surveySubmitting}
              error={surveyError}
              onClose={() => setSurveyOpen(false)}
            />
          ) : archCompleteShown ? (
            <ArchCompleteNotice
              condition={condition}
              onDismiss={() => setArchCompleteShown(false)}
            />
          ) : null
        }
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
            micError={micError}
          />
        }
      />
    </div>
  );
}

export default App;
