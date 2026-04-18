import type {
  Scorecard,
  ScorecardEvent,
  SuggestResponse,
} from "@/types/api";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} on ${path}`);
  }
  return (await res.json()) as T;
}

export const api = {
  suggestGreener: (code: string) =>
    jsonFetch<SuggestResponse>("/api/suggest_greener", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

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
