// Typed client mirroring backend/app/models/schemas.py.
// Routes live behind Next.js rewrites (next.config.mjs) so the browser
// always talks to /api/* and the rewrite forwards to BACKEND_URL.

export type Region = "CISO" | "ERCO" | "PJM" | "MISO" | "NYIS";
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
