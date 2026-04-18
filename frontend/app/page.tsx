"use client";

import { useCallback, useEffect, useState } from "react";

import CodeEditor from "@/components/CodeEditor";
import RunAnalysisModal from "@/components/RunAnalysisModal";
import {
  checkGrid,
  type CheckGridResponse,
  type DetectedPattern,
  estimateCarbon,
  type EstimateCarbonResponse,
  findCleanWindow,
  type FindCleanWindowResponse,
  type Region,
} from "@/lib/api";
import { SAMPLE_CODE } from "@/lib/sample";

const REGIONS: Region[] = ["CISO", "ERCO", "PJM", "MISO", "NYIS"];

export default function Home() {
  const [code, setCode] = useState(SAMPLE_CODE);
  const [region, setRegion] = useState<Region>("CISO");
  const [grid, setGrid] = useState<CheckGridResponse | null>(null);
  const [patterns, setPatterns] = useState<DetectedPattern[]>([]);
  const [estimate, setEstimate] = useState<EstimateCarbonResponse | null>(null);
  const [cleanWindow, setCleanWindow] = useState<FindCleanWindowResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lightweight grid status in the header — refreshed on region change.
  useEffect(() => {
    const ctrl = new AbortController();
    checkGrid(region, ctrl.signal)
      .then(setGrid)
      .catch((e) => console.warn("check_grid failed", e));
    return () => ctrl.abort();
  }, [region]);

  const runAnalysis = useCallback(async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    setEstimate(null);
    setCleanWindow(null);
    try {
      const [est, win] = await Promise.all([
        estimateCarbon(code, region),
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
  }, [code, region]);

  return (
    <main className="flex h-screen flex-col">
      <header className="flex flex-wrap items-center gap-4 border-b border-gg-border px-5 py-3">
        <div>
          <h1 className="text-base font-semibold">
            GridGreen <span className="text-gg-muted">— carbon-aware ML copilot</span>
          </h1>
          <p className="text-xs text-gg-muted">
            Person A slice: grid + estimator. Paste a training script, pick a region, run analysis.
          </p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-gg-muted">Region</span>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value as Region)}
              className="rounded border border-gg-border bg-gg-bg px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-gg-accent"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
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
            className="rounded bg-gg-accent px-3 py-1.5 text-sm font-semibold text-black hover:bg-gg-accentDim"
          >
            Run analysis
          </button>
        </div>
      </header>

      <section className="min-h-0 flex-1">
        <CodeEditor value={code} onChange={setCode} patterns={patterns} />
      </section>

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
