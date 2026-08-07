export interface StatCardData {
  id: string;
  label: string;
  value: number;
  unit?: string;
  delta: number;
  sparkline: number[];
}

export interface Directive {
  id: string;
  label: string;
  done: boolean;
}

export interface DocumentEntry {
  id: string;
  name: string;
  accessedAt: string;
}

export interface CommandAction {
  id: string;
  label: string;
}

export interface ToolCallCard {
  id: string;
  toolName: string;
  preview: string;
  timestamp: string;
}

export interface WireEvent {
  id: string;
  speaker: "USER" | "JARVIS";
  text: string;
  timestamp: string;
}

export type SystemStatus = "IDLE" | "ONLINE" | "ALIVE" | "BUSY" | "OFFLINE";

/** How the participant is entering their next message. Switchable at any point. */
export type InputMode = "text" | "voice";

export type Rating = "up" | "down";

/** 1-5 selectors on the post-task survey. Not a slider — discrete points only. */
export type SurveyScale = 1 | 2 | 3 | 4 | 5;

export type AccuracyAnswer = "yes" | "partially" | "no";

/** One post-task evaluation. Carries no task number or participant id — the server
 * derives both, so a refreshed browser can't restart the task count at 1. */
export interface SurveyAnswers {
  personalized_rating: SurveyScale;
  accuracy_rating: AccuracyAnswer;
  trust_rating: SurveyScale;
}

/** How far through the current arm the participant is, per the server's survey log. */
export interface TaskState {
  completedTasks: number;
  nextTask: number;
  archComplete: boolean;
}
