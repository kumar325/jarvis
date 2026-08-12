import { useState } from "react";
import type { AccuracyAnswer, SurveyAnswers, SurveyScale } from "../../lib/types";

interface Props {
  /** 1-based, shown to the participant as "Task N of TOTAL". */
  taskNumber: number;
  totalTasks: number;
  onSubmit: (answers: SurveyAnswers) => void;
  /** Waiting on the server to confirm the write — Submit stays locked until it answers. */
  submitting: boolean;
  /** The write failed. Shown on the card (moderator-facing), never in the transcript. */
  error: string | null;
  /** Back out of the card without recording anything — for a mis-clicked Finish Task. */
  onClose: () => void;
}

const SCALE: SurveyScale[] = [1, 2, 3, 4, 5];

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

const ACCURACY_OPTIONS: { value: AccuracyAnswer; label: string }[] = [
  { value: "yes", label: "Yes" },
  { value: "partially", label: "Partially" },
  { value: "no", label: "No" },
];

/** One question's label plus its answer row. Every question is mandatory, so there is no
 * "prefer not to say" option and no visual distinction between answered and unanswered
 * beyond the selection itself. */
function Question({ prompt, children }: { prompt: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[0.8rem] leading-snug text-[var(--text)]">{prompt}</p>
      {children}
    </div>
  );
}

/** 1-5 selector rendered as discrete buttons with anchor labels underneath. Buttons rather
 * than a slider: a slider has a default position, which biases the answer before the
 * participant has touched it, and would make "unanswered" indistinguishable from "3". */
function ScaleRow({
  name,
  value,
  onChange,
  lowLabel,
  highLabel,
}: {
  name: string;
  value: SurveyScale | null;
  onChange: (v: SurveyScale) => void;
  lowLabel: string;
  highLabel: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div role="radiogroup" aria-label={name} className="flex gap-1.5">
        {SCALE.map((n) => (
          <button
            key={n}
            role="radio"
            aria-checked={value === n}
            onClick={() => onChange(n)}
            className={`h-7 flex-1 rounded-lg border text-xs transition-colors ${
              value === n
                ? "border-[var(--text-muted)] bg-[var(--surface-raised)] text-[var(--text)]"
                : "border-[var(--border)] bg-transparent text-[var(--text-muted)] hover:border-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="flex justify-between text-[0.62rem] text-[var(--text-muted)]">
        <span>{lowLabel}</span>
        <span>{highLabel}</span>
      </div>
    </div>
  );
}

function ChoiceRow({
  name,
  value,
  onChange,
}: {
  name: string;
  value: AccuracyAnswer | null;
  onChange: (v: AccuracyAnswer) => void;
}) {
  return (
    <div role="radiogroup" aria-label={name} className="flex gap-1.5">
      {ACCURACY_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          role="radio"
          aria-checked={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={`h-7 flex-1 rounded-lg border text-xs transition-colors ${
            value === opt.value
              ? "border-[var(--text-muted)] bg-[var(--surface-raised)] text-[var(--text)]"
              : "border-[var(--border)] bg-transparent text-[var(--text-muted)] hover:border-[var(--text-muted)] hover:text-[var(--text)]"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/** Post-task evaluation, shown once per task after the moderator marks it finished.
 *
 * Same disable-until-answered contract as RatingPrompt: Submit stays locked until all
 * three questions carry an answer, and there is no skip or back — a partial row would be
 * unusable in the analysis. Unlike the thumbs up/down, submission is confirmed by the
 * server before the card clears, since these three answers are the task-level measure and
 * are not recoverable from anywhere else.
 *
 * Closable, but only backwards: the X dismisses the card without writing a row, so a
 * mis-clicked Finish Task doesn't strand the participant in a survey for a task they
 * haven't finished. Reopening starts blank — the component unmounts and its answers go
 * with it, which is the intended behaviour. A half-filled card resumed later would be
 * answering about a task that has since continued.
 */
export function TaskSurvey({ taskNumber, totalTasks, onSubmit, submitting, error, onClose }: Props) {
  const [personalized, setPersonalized] = useState<SurveyScale | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracyAnswer | null>(null);
  const [trust, setTrust] = useState<SurveyScale | null>(null);

  const complete = personalized !== null && accuracy !== null && trust !== null;

  const submit = () => {
    if (!complete || submitting) return;
    onSubmit({
      personalized_rating: personalized,
      accuracy_rating: accuracy,
      trust_rating: trust,
    });
  };

  return (
    <div className="flex h-full items-center justify-center overflow-y-auto py-2">
      <div className="relative w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
        {/* Locked while a write is in flight: the card clears itself on `survey_recorded`,
            so closing mid-submit would hide a result the moderator still needs to see. */}
        <button
          onClick={onClose}
          disabled={submitting}
          aria-label="Close without submitting"
          title="Close without submitting"
          className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-raised)] hover:text-[var(--text)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <CloseIcon />
        </button>

        <div className="mb-4 flex flex-col gap-0.5">
          <span className="text-[0.62rem] uppercase tracking-[0.15em] text-[var(--text-muted)]">
            {/* Drops the "of N" past the planned count rather than printing "Task 4 of 3" —
                an extra task still logs honestly, it just isn't part of the protocol. */}
            {taskNumber > totalTasks ? `Task ${taskNumber}` : `Task ${taskNumber} of ${totalTasks}`}
          </span>
          <h2 className="text-sm font-medium text-[var(--text)]">Post-task evaluation</h2>
        </div>

        <div className="flex flex-col gap-4">
          <Question prompt="Did this feel personalized to you?">
            <ScaleRow
              name="Did this feel personalized to you?"
              value={personalized}
              onChange={setPersonalized}
              lowLabel="Not at all"
              highLabel="Very much"
            />
          </Question>

          <Question prompt="Do the recommendations seem accurate?">
            <ChoiceRow
              name="Do the recommendations seem accurate?"
              value={accuracy}
              onChange={setAccuracy}
            />
          </Question>

          <Question prompt="Would you trust this suggestion?">
            <ScaleRow
              name="Would you trust this suggestion?"
              value={trust}
              onChange={setTrust}
              lowLabel="Not at all"
              highLabel="Completely"
            />
          </Question>
        </div>

        {error ? <p className="mt-3 text-[0.7rem] text-[var(--danger)]">{error}</p> : null}

        <button
          onClick={submit}
          disabled={!complete || submitting}
          className="mt-4 h-8 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] text-xs text-[var(--text)] transition-colors hover:border-[var(--text-muted)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-[var(--border)]"
        >
          {submitting ? "Saving…" : "Submit"}
        </button>

        {!complete ? (
          <p className="mt-2 text-center text-[0.62rem] text-[var(--text-muted)]">
            Answer all three to continue
          </p>
        ) : null}
      </div>
    </div>
  );
}
