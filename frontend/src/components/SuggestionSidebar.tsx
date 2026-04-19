"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  CheckGridResponse,
  EstimateCarbonResponse,
  FindCleanWindowResponse,
  Region,
  SuggestGreenerPayload,
} from "@/lib/api";
import { getSessionId } from "@/lib/session";
import type { Suggestion } from "@/types/api";
import { SuggestionCard } from "./SuggestionCard";

export interface CarbonAnalysisContext {
  estimate: EstimateCarbonResponse | null;
  grid: CheckGridResponse | null;
  cleanWindow: FindCleanWindowResponse | null;
}

interface Props {
  code: string;
  region: Region;
  /** After "Run analysis", pass estimate + clean window so swaps cite Part A numbers. */
  carbonContext?: CarbonAnalysisContext | null;
  onApplySuggestion: (s: Suggestion) => void;
  onScorecardChange?: () => void;
}

function buildSuggestPayload(
  code: string,
  region: Region,
  ctx: CarbonAnalysisContext | null | undefined,
): SuggestGreenerPayload {
  const base: SuggestGreenerPayload = { code, region };
  if (!ctx?.estimate) {
    return base;
  }
  const focusLines = ctx.estimate.detected_patterns
    .filter((p) => p.impact === "high")
    .map((p) => p.line);
  return {
    ...base,
    co2_grams_now: ctx.estimate.co2_grams_now,
    co2_grams_optimal: ctx.estimate.co2_grams_optimal,
    current_gco2_kwh: ctx.grid?.current_gco2_kwh ?? undefined,
    optimal_window_start: ctx.cleanWindow?.optimal_start ?? undefined,
    co2_savings_pct_window: ctx.cleanWindow?.co2_savings_pct ?? undefined,
    impact_focus_lines: focusLines.length ? focusLines : undefined,
  };
}

export function SuggestionSidebar({
  code,
  region,
  carbonContext,
  onApplySuggestion,
  onScorecardChange,
}: Props) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const payload = useMemo(
    () => buildSuggestPayload(code, region, carbonContext ?? null),
    [code, region, carbonContext],
  );

  useEffect(() => {
    if (!code.trim() || !carbonContext?.estimate) {
      setSuggestions([]);
      setLoading(false);
      setError(null);
      return;
    }
    const handle = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.suggestGreener(payload);
        setSuggestions(res.suggestions);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }, 600);
    return () => clearTimeout(handle);
  }, [payload, carbonContext?.estimate]);

  async function handleApply(s: Suggestion) {
    onApplySuggestion(s);
    try {
      await api.recordEvent({
        session_id: getSessionId(),
        event: "suggestion_accepted",
        co2_saved_grams: Math.round((s.carbon_saved_pct / 100) * 1000),
      });
      onScorecardChange?.();
    } catch {
      /* swap already applied */
    }
  }

  const hasAnalysis = Boolean(carbonContext?.estimate);

  return (
    <aside className="flex h-full w-full flex-col gap-3 overflow-y-auto p-2">
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gg-muted">
          Greener alternatives
        </h2>
        {hasAnalysis && loading && (
          <span className="text-xs text-gg-muted">analyzing…</span>
        )}
      </header>

      {!hasAnalysis && (
        <div className="space-y-2 rounded-md border border-gg-border bg-black/20 p-3 text-xs leading-relaxed text-gg-text">
          <p>
            <span className="font-semibold text-gg-accent">Step 1 — same model.</span> Click{" "}
            <strong>Run analysis</strong> first: grid intensity, a cleaner time window, and estimated
            CO₂ for <em>this</em> script (no model change).
          </p>
          <p className="text-gg-muted">
            <span className="font-semibold text-gg-text">Step 2 — other models.</span> Alternative
            model swaps load here after Step 1 so they can use those numbers in the explanations.
          </p>
        </div>
      )}

      {hasAnalysis && (
        <p className="rounded-md border border-gg-accent/30 bg-gg-accent/10 px-2 py-1.5 text-[10px] leading-snug text-gg-text">
          Using your last <strong>Run analysis</strong> (grid + script CO₂) to rank and explain swaps.
          If you change the script a lot, run analysis again before trusting swaps.
        </p>
      )}

      {error && (
        <p className="rounded-md bg-rose-500/10 p-2 text-xs text-rose-300">{error}</p>
      )}

      {hasAnalysis && !loading && suggestions.length === 0 && !error && (
        <p className="rounded-md border border-dashed border-gg-border p-3 text-xs text-gg-muted">
          No swap suggestions — use <code className="font-mono text-gg-accent">from_pretrained(&quot;…&quot;)</code>{" "}
          with a model in the corpus, then click <strong>Run analysis</strong> for grid-aware reasoning.
        </p>
      )}

      {suggestions.map((s) => (
        <SuggestionCard
          key={`${s.line}-${s.alternative_snippet}`}
          suggestion={s}
          onApply={handleApply}
        />
      ))}
    </aside>
  );
}
