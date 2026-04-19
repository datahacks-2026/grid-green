// Person B — suggest + scorecard shapes (keep in sync with CONTRACT.md).

export interface Suggestion {
  line: number;
  original_snippet: string;
  alternative_snippet: string;
  carbon_saved_pct: number;
  performance_retained_pct: number;
  citation: string;
  reasoning: string;
}

export interface SuggestResponse {
  suggestions: Suggestion[];
}

export interface Scorecard {
  co2_saved_grams: number;
  runs_deferred: number;
  suggestions_accepted: number;
}

export type ScorecardEvent =
  | { session_id: string; event: "suggestion_accepted"; co2_saved_grams: number }
  | { session_id: string; event: "run_deferred"; co2_saved_grams: number };
