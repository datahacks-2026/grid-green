"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import CodeEditor from "@/components/CodeEditor";
import { RepoAnalyzer } from "@/components/RepoAnalyzer";
import RunAnalysisModal from "@/components/RunAnalysisModal";
import { StatsCard } from "@/components/StatsCard";
import { SuggestionSidebar } from "@/components/SuggestionSidebar";
import {
  checkGrid,
  type CheckGridResponse,
  type DetectedPattern,
  estimateCarbon,
  type EstimateCarbonResponse,
  findCleanWindow,
  type FindCleanWindowResponse,
  formatRegionLabel,
  type Region,
} from "@/lib/api";
import { SAMPLE_CODE } from "@/lib/sample";
import type { CarbonAnalysisContext } from "@/components/SuggestionSidebar";
import type { Suggestion } from "@/types/api";

const REGIONS: Region[] = ["CISO", "ERCO", "PJM", "MISO", "NYIS"];
type Mode = "code" | "repo";

export default function Home() {
  const [mode, setMode] = useState<Mode>("code");
  const [code, setCode] = useState(SAMPLE_CODE);
  /** Source blob returned from POST /api/analyze_repo for grid + timing in repo mode. */
  const [repoCarbonCode, setRepoCarbonCode] = useState<string | null>(null);
  const [region, setRegion] = useState<Region>("CISO");
  const [grid, setGrid] = useState<CheckGridResponse | null>(null);
  const [patterns, setPatterns] = useState<DetectedPattern[]>([]);
  const [estimate, setEstimate] = useState<EstimateCarbonResponse | null>(null);
  const [cleanWindow, setCleanWindow] = useState<FindCleanWindowResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scoreRefresh, setScoreRefresh] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    checkGrid(region, ctrl.signal)
      .then(setGrid)
      .catch((e) => console.warn("check_grid failed", e));
    return () => ctrl.abort();
  }, [region]);

  useEffect(() => {
    setEstimate(null);
    setCleanWindow(null);
    setPatterns([]);
    setError(null);
    if (mode === "code") {
      setRepoCarbonCode(null);
    }
  }, [mode]);

  const analysisPayload = mode === "repo" ? (repoCarbonCode ?? "") : code;

  const runAnalysis = useCallback(async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    setEstimate(null);
    setCleanWindow(null);
    if (!analysisPayload.trim()) {
      setError(
        mode === "repo"
          ? "Scan the repo first — then we can estimate training CO₂ and the best time window from grid forecasts."
          : "Paste or write some code to analyze.",
      );
      setLoading(false);
      return;
    }
    try {
      const [est, win] = await Promise.all([
        estimateCarbon(analysisPayload, region),
        findCleanWindow(region, 4),
      ]);
      setEstimate(est);
      setCleanWindow(win);
      setPatterns(est.detected_patterns);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [analysisPayload, mode, region]);

  function handleApplySuggestion(s: Suggestion) {
    setCode((prev) => prev.split(s.original_snippet).join(s.alternative_snippet));
  }

  const carbonContext = useMemo<CarbonAnalysisContext>(
    () => ({
      estimate,
      grid,
      cleanWindow,
    }),
    [estimate, grid, cleanWindow],
  );

  return (
    <main className="flex h-screen flex-col">
      <header className="flex flex-wrap items-center gap-4 border-b border-gg-border px-5 py-3">
        <div>
          <h1 className="text-base font-semibold">
            GridGreen <span className="text-gg-muted">— carbon-aware ML copilot</span>
          </h1>
          <p className="text-xs text-gg-muted">
            Code: edit + run analysis for grid timing and greener swaps. Repo URL: scan GitHub,
            then run analysis for the same timing + CO₂ view on aggregated source.
          </p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-3">
          <div
            role="tablist"
            aria-label="Input mode"
            className="flex overflow-hidden rounded border border-gg-border bg-black/30 text-xs"
          >
            <button
              role="tab"
              aria-selected={mode === "code"}
              type="button"
              onClick={() => setMode("code")}
              className={`px-3 py-1.5 transition ${
                mode === "code"
                  ? "bg-gg-accent text-black"
                  : "text-gg-muted hover:text-gg-text"
              }`}
            >
              Code
            </button>
            <button
              role="tab"
              aria-selected={mode === "repo"}
              type="button"
              onClick={() => setMode("repo")}
              className={`px-3 py-1.5 transition ${
                mode === "repo"
                  ? "bg-gg-accent text-black"
                  : "text-gg-muted hover:text-gg-text"
              }`}
            >
              Repo URL
            </button>
          </div>
          <a
            href="/mcp"
            className="text-xs text-gg-muted underline-offset-2 hover:text-gg-accent hover:underline"
          >
            MCP setup →
          </a>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-gg-muted">Region</span>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value as Region)}
              className="rounded border border-gg-border bg-gg-bg px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-gg-accent"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>
                  {formatRegionLabel(r)}
                </option>
              ))}
            </select>
          </label>

          {grid && (
            <div className="hidden items-center gap-2 rounded border border-gg-border bg-black/30 px-3 py-1 text-xs sm:flex">
              <span className="text-gg-muted">Grid now</span>
              <span className="font-mono">
                {grid.current_gco2_kwh.toFixed(0)} gCO₂/kWh
              </span>
              <span
                className={
                  grid.trend === "rising"
                    ? "text-gg-warn"
                    : grid.trend === "falling"
                      ? "text-gg-accent"
                      : "text-gg-muted"
                }
              >
                {grid.trend}
              </span>
            </div>
          )}

          <button
            type="button"
            onClick={runAnalysis}
            disabled={mode === "repo" && !repoCarbonCode?.trim()}
            title={
              mode === "repo" && !repoCarbonCode?.trim()
                ? "Scan a repo first to load source for timing + CO₂ estimate"
                : undefined
            }
            className="rounded bg-gg-accent px-3 py-1.5 text-sm font-semibold text-black hover:bg-gg-accentDim disabled:cursor-not-allowed disabled:opacity-40"
          >
            Run analysis
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <section className="min-w-0 flex-1">
          {mode === "code" ? (
            <CodeEditor value={code} onChange={setCode} patterns={patterns} />
          ) : (
            <RepoAnalyzer
              region={region}
              onAggregatedCode={(agg) => setRepoCarbonCode(agg)}
              estimate={estimate}
              cleanWindow={cleanWindow}
            />
          )}
        </section>
        {mode === "code" && (
          <aside className="flex w-80 shrink-0 flex-col gap-3 overflow-y-auto border-l border-gg-border bg-gg-panel p-3">
            <StatsCard refreshKey={scoreRefresh} />
            <SuggestionSidebar
              code={code}
              region={region}
              carbonContext={carbonContext}
              onApplySuggestion={handleApplySuggestion}
              onScorecardChange={() => setScoreRefresh((n) => n + 1)}
            />
          </aside>
        )}
      </div>

      <RunAnalysisModal
        open={open}
        onClose={() => setOpen(false)}
        region={region}
        loading={loading}
        error={error}
        estimate={estimate}
        cleanWindow={cleanWindow}
      />
    </main>
  );
}
