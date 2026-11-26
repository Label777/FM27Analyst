// Типы данных ядра (зеркало fm27_analyst/models.py)

export type Fatigue = "fresh" | "ok" | "tired" | "exhausted" | "unknown";
export type Severity = "info" | "warning" | "critical";

export interface TeamStats {
  possession: number | null;
  shots: number | null;
  shots_on_target: number | null;
  xg: number | null;
  passes: number | null;
  pass_accuracy: number | null;
  tackles_won: number | null;
  tackles: number | null;
  yellow_cards: number | null;
  red_cards: number | null;
}

export interface PlayerState {
  name: string;
  position: string | null;
  role: string | null;
  rating: number | null;
  fatigue: Fatigue;
  yellow_card: boolean;
  injured: boolean;
  on_pitch: boolean;
  attributes: Record<string, number>;
}

export interface TeamState {
  name: string;
  formation_in_possession: string | null;
  formation_out_of_possession: string | null;
  stats: TeamStats;
  players: PlayerState[];
  bench: PlayerState[];
}

export interface Snapshot {
  minute: number;
  home_goals: number;
  away_goals: number;
  our_side: "home" | "away";
  home: TeamState;
  away: TeamState;
  dugout_messages: string[];
  source: string;
  confidence: number;
}

export interface Fact {
  id: string;
  text: string;
  minute: number;
  source: string;
  confidence: number;
}

export interface Signal {
  rule_id: string;
  severity: Severity;
  title: string;
  minute: number;
  fact_ids: string[];
  player: string | null;
}

export interface Action {
  text: string;
  kind: "tactical_tweak" | "role" | "instruction" | "substitution" | "shout" | "other";
  setting: string | null;
}

export interface Recommendation {
  id: string;
  minute: number;
  mode: "quick" | "live" | "head_coach";
  problem: string;
  evidence_fact_ids: string[];
  actions: Action[];
  expected_effect: string;
  risks: string;
  confidence: "low" | "medium" | "high";
  missing_data: string[];
  status: "new" | "accepted" | "rejected";
  generated_by: "llm" | "rules";
}

export interface Change {
  kind: string;
  text: string;
  minute: number;
  fact_id: string;
}

export interface Tick {
  snapshot: Snapshot;
  changes: Change[];
  facts: Fact[];
  signals: Signal[];
  recommendations: Recommendation[];
}

export interface Answer {
  question: string;
  short: string;
  detail: string;
  evidence_fact_ids: string[];
  missing_data: string[];
  generated_by: string;
}

export interface Health {
  ok: boolean;
  version: string;
  llm: boolean;
  save: string | null;
  match_id: number | null;
}

export interface CaptureResult {
  ok: boolean;
  message: string;
  screen?: string;
  saved_to?: string;
}

export interface MatchRow {
  id: number;
  opponent: string;
  our_side: string;
  started_at: number;
  finished: number;
  final_score: string | null;
}

export interface HistoryItem {
  match_id: number;
  rule_ids: string[];
  recommendation: Recommendation;
  outcome: { window: number; xg_us: number; xg_them: number; goals: string; note: string } | null;
}

// --- мост с игрой ---
export interface BridgeTableSummary {
  id: string;
  received_at: number;
  screen: string;
  headers: string[];
  row_count: number;
  expected_rows: number | null;
  paginated: boolean;
  hidden_columns: number;
  missing_rows: number;
  notes: string[];
  game_date: string | null;
  suggested_scope: "own" | "market" | null;
  imported: { scope: string; added: number; updated: number } | null;
  preview: string[][];
}

export interface BridgeStatus {
  online: boolean;
  last_seen: number | null;
  plugin: { plugin_version?: string; game_version?: string; unity_version?: string; product?: string } | null;
  auto_screen: boolean;
  auto_interval: number;
  game_date: string | null;
  game_date_text: string | null;
  queued: number;
  last_table: BridgeTableSummary | null;
  last_screen: { received_at: number; auto: boolean; screen: string; text_count: number; truncated: boolean } | null;
  tables_on_screen: { index: number; screen: string; name: string; columns: number; rows: number | null }[];
}
