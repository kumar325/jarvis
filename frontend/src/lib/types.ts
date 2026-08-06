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
