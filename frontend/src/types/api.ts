// Mirrors backend/app/schemas.py — keep in sync with README §5.

export type Region = "CISO" | "ERCO" | "PJM" | "MISO" | "NYIS";

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

// Person A's contracts — defined here so the UI can render them
// the moment A's endpoints go live, without another typing pass.
export interface DetectedPattern {
  line: number;
  pattern: string;
  impact: "low" | "medium" | "high";
}

export interface EstimateCarbonResponse {
  co2_grams_now: number;
  co2_grams_optimal: number;
  gpu_hours: number;
  kwh_estimated: number;
  confidence: "low" | "medium" | "high";
  detected_patterns: DetectedPattern[];
}
