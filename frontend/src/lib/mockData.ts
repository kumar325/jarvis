import type {
  CommandAction,
  DocumentEntry,
  Directive,
  StatCardData,
  ToolCallCard,
  WireEvent,
} from "./types";

export const MOCK_VITALS: StatCardData[] = [
  {
    id: "prefs",
    label: "PREFERENCE EXAMPLES",
    value: 34,
    delta: 3,
    sparkline: [4, 6, 5, 8, 9, 11, 14, 18, 22, 26, 30, 34],
  },
  {
    id: "facts",
    label: "REMEMBERED FACTS",
    value: 12,
    delta: 1,
    sparkline: [2, 2, 3, 4, 4, 5, 6, 7, 8, 9, 11, 12],
  },
  {
    id: "layers",
    label: "PERSONALIZATION LAYERS",
    value: 5,
    unit: "/5",
    delta: 0,
    sparkline: [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5],
  },
  {
    id: "turns",
    label: "AGENT TURNS (SESSION)",
    value: 7,
    delta: 2,
    sparkline: [0, 1, 1, 2, 3, 3, 4, 5, 5, 6, 6, 7],
  },
];

export const MOCK_DIRECTIVES: Directive[] = [
  { id: "d1", label: "Tune preference retrieval threshold (k, sim cutoff)", done: false },
  { id: "d2", label: "Fuzzy-dedup user_profile.json facts", done: false },
  { id: "d3", label: "Draft NeurIPS workshop abstract", done: false },
  { id: "d4", label: "Run full ablation eval before Thursday sync", done: true },
];

export const MOCK_DOCUMENTS: DocumentEntry[] = [
  { id: "doc1", name: "eval_scores_20260707_002245.csv", accessedAt: "09:14" },
  { id: "doc2", name: "system_prompt.py", accessedAt: "08:52" },
  { id: "doc3", name: "test_queries.json", accessedAt: "08:40" },
  { id: "doc4", name: "ablations.py", accessedAt: "08:21" },
];

export const COMMAND_ACTIONS: CommandAction[] = [
  { id: "metrics_pull", label: "METRICS PULL" },
  { id: "inbox_brief", label: "INBOX BRIEF" },
  { id: "trend_scan", label: "TREND SCAN" },
  { id: "plan_today", label: "PLAN TODAY" },
  { id: "wk_review", label: "WK REVIEW" },
  { id: "am_report", label: "AM REPORT" },
  { id: "gh_trending", label: "GH TRENDING" },
  { id: "yt_week", label: "YT WEEK" },
  { id: "plan_tmrw", label: "PLAN TMRW" },
  { id: "vault_clean", label: "VAULT CLEAN" },
];

export const MOCK_WIRE: WireEvent[] = [
  { id: "w1", text: "no_web_search ablation zeroed context_relevance (0.182 -> 0.0)", timestamp: "09:12" },
  { id: "w2", text: "style_tracker re-analyzed after 5 utterances", timestamp: "08:58" },
  { id: "w3", text: "new preference pair saved: rating=up", timestamp: "08:45" },
  { id: "w4", text: "Tavily credit balance: 1,240 remaining", timestamp: "08:30" },
];

export const MOCK_TOOL_CARDS: ToolCallCard[] = [
  { id: "t1", toolName: "web_search", preview: "query: 'NeurIPS 2026 workshop deadlines'", timestamp: "09:15" },
  { id: "t2", toolName: "remember", preview: "fact: 'prefers concise answers'", timestamp: "09:10" },
];
