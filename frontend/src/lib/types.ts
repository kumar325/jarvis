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
  text: string;
  timestamp: string;
}

export type SystemStatus = "IDLE" | "ONLINE" | "ALIVE" | "BUSY";
