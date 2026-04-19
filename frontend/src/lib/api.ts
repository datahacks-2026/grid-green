// Typed client — routes use Next.js `/api/*` rewrites → BACKEND_URL.

import type {
  Scorecard,
  ScorecardEvent,
  SuggestResponse,
} from "@/types/api";

export type Region = "CISO" | "ERCO" | "PJM" | "MISO" | "NYIS";

/** EIA balancing-authority names — same grid areas as `backend/app/services/regions.py`. */
export const REGION_FULL_NAMES: Record<Region, string> = {
  CISO: "California ISO",
  ERCO: "ERCOT (Texas)",
  PJM: "PJM Interconnection",
  MISO: "Midcontinent ISO",
  NYIS: "New York ISO",
};

/** e.g. "California ISO (CISO)" — for selects and headings. */
export function formatRegionLabel(code: Region): string {
  return `${REGION_FULL_NAMES[code]} (${code})`;
}

export type Confidence = "low" | "medium" | "high";
export type Impact = "low" | "medium" | "high";
export type Trend = "rising" | "falling" | "flat";

export interface DetectedPattern {
  line: number;
  pattern: string;
  impact: Impact;
}

export interface EstimateCarbonResponse {
  co2_grams_now: number;
  co2_grams_optimal: number;
  gpu_hours: number;
  kwh_estimated: number;
  confidence: Confidence;
  detected_patterns: DetectedPattern[];
}

export interface CheckGridResponse {
  region: Region;
  current_gco2_kwh: number;
  trend: Trend;
  last_updated: string;
}

export interface ForecastPoint {
  hour: string;
  gco2_kwh: number;
}

export interface FindCleanWindowResponse {
  optimal_start: string;
  expected_gco2_kwh: number;
  current_gco2_kwh: number;
  co2_savings_pct: number;
  forecast_48h: ForecastPoint[];
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${detail || res.statusText}`);
  }
  return (await res.json()) as T;
}

export async function estimateCarbon(
  code: string,
  region: Region,
  signal?: AbortSignal,
): Promise<EstimateCarbonResponse> {
  const res = await fetch("/api/estimate_carbon", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, region }),
    signal,
  });
  return jsonOrThrow(res);
}

export async function checkGrid(
  region: Region,
  signal?: AbortSignal,
): Promise<CheckGridResponse> {
  const res = await fetch(`/api/check_grid?region=${region}`, { signal });
  return jsonOrThrow(res);
}

export async function findCleanWindow(
  region: Region,
  hoursNeeded = 4,
  signal?: AbortSignal,
): Promise<FindCleanWindowResponse> {
  const res = await fetch(
    `/api/find_clean_window?region=${region}&hours_needed=${hoursNeeded}`,
    { signal },
  );
  return jsonOrThrow(res);
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  return jsonOrThrow(res);
}

/** Optional Part A fields — backend merges these into RAG reasoning when present. */
export type SuggestGreenerPayload = {
  code: string;
  region?: Region;
  co2_grams_now?: number | null;
  co2_grams_optimal?: number | null;
  current_gco2_kwh?: number | null;
  optimal_window_start?: string | null;
  co2_savings_pct_window?: number | null;
  impact_focus_lines?: number[];
};

export type AnalyzeRepoRequest = {
  repo_url: string;
  ref?: string;
  region?: Region;
  top_k_per_file?: number;
  max_files_with_hits?: number;
};

export type AnalyzeRepoResponse = {
  repo_url: string;
  owner: string;
  repo: string;
  files_scanned: number;
  files_with_hits: number;
  total_suggestions: number;
  files: Array<{
    path: string;
    suggestions: import("@/types/api").Suggestion[];
  }>;
  /** Joined source (byte-capped) — POST to `/api/estimate_carbon` for grid + timing. */
  aggregated_code_for_estimate: string;
  aggregate_file_count: number;
  aggregate_truncated: boolean;
};

export type Diagnostics = {
  time: string;
  env: string;
  integrations: Record<string, Record<string, unknown>>;
  storage: { sqlite_path: string; sqlite_exists: boolean; sqlite_size_bytes: number };
  rag_corpus: { path: string; entries: number };
};

export const api = {
  suggestGreener: (payload: SuggestGreenerPayload) =>
    jsonFetch<SuggestResponse>("/api/suggest_greener", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  analyzeRepo: (payload: AnalyzeRepoRequest) =>
    jsonFetch<AnalyzeRepoResponse>("/api/analyze_repo", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  diagnostics: () => jsonFetch<Diagnostics>("/api/diagnostics"),

  getScorecard: (sessionId: string) =>
    jsonFetch<Scorecard>(
      `/api/scorecard?session_id=${encodeURIComponent(sessionId)}`,
    ),

  recordEvent: (event: ScorecardEvent) =>
    jsonFetch<Scorecard>("/api/scorecard/event", {
      method: "POST",
      body: JSON.stringify(event),
    }),
};
