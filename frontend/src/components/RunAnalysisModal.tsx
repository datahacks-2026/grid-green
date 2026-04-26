"use client";

import { useEffect, useMemo, useState } from "react";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  formatRegionLabel,
  type CampusHeatContext,
  type EstimateCarbonResponse,
  type FindCleanWindowResponse,
  type Region,
  type WeatherContext,
} from "@/lib/api";
import type { Suggestion } from "@/types/api";

import { ContextStrip } from "./ContextStrip";
import { GeminiReasoning } from "./GeminiReasoning";

type Props = {
  open: boolean;
  onClose: () => void;
  onDeferRun?: (co2SavedGrams: number) => Promise<void> | void;
  region: Region;
  loading: boolean;
  error?: string | null;
  estimate?: EstimateCarbonResponse | null;
  cleanWindow?: FindCleanWindowResponse | null;
  cleanWindowsByLookahead?: Partial<Record<4 | 12 | 24 | 48, FindCleanWindowResponse>>;
  /** Top RAG suggestion (optional) — shown below the chart with NL reasoning. */
  suggestions?: Suggestion[];
  /** Optional NOAA narrative for the selected region. Hidden if upstream is flaky. */
  weather?: WeatherContext | null;
  /** Optional Scripps heat-map aggregate. Hidden if CSV is missing. */
  campusHeat?: CampusHeatContext | null;
};

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtGrams(g: number): string {
  if (g >= 1000) return `${(g / 1000).toFixed(2)} kg`;
  return `${Math.round(g)} g`;
}

export default function RunAnalysisModal({
  open,
  onClose,
  onDeferRun,
  region,
  loading,
  error,
  estimate,
  cleanWindow,
  cleanWindowsByLookahead = {},
  suggestions = [],
  weather = null,
  campusHeat = null,
}: Props) {
  const [selectedLookahead, setSelectedLookahead] = useState<4 | 12 | 24 | 48>(48);
  const activeWindow = cleanWindowsByLookahead[selectedLookahead] ?? cleanWindow ?? null;
  const activeOptimalStart = activeWindow?.optimal_start ?? cleanWindow?.optimal_start ?? "";

  const savings =
    estimate && estimate.co2_grams_now > 0
      ? Math.round(
          ((estimate.co2_grams_now - estimate.co2_grams_optimal) /
            estimate.co2_grams_now) *
            100,
        )
      : 0;
  const waitIsBetter = useMemo(() => {
    if (!estimate || !activeWindow) return false;
    const gramsAtActiveWindow =
      estimate.kwh_estimated * activeWindow.expected_gco2_kwh;
    return gramsAtActiveWindow < estimate.co2_grams_now;
  }, [estimate, activeWindow]);

  const lookaheadRows = useMemo(
    () =>
      ([4, 12, 24, 48] as const).map((hours) => ({
        hours,
        window: cleanWindowsByLookahead[hours] ?? null,
      })),
    [cleanWindowsByLookahead],
  );

  const activeWindowGrams = useMemo(() => {
    if (!estimate || !activeWindow) return null;
    return estimate.kwh_estimated * activeWindow.expected_gco2_kwh;
  }, [estimate, activeWindow]);

  const lookaheadComparison = useMemo(() => {
    if (!estimate) return new Map<number, "better" | "worse" | "same" | "na">();
    const out = new Map<number, "better" | "worse" | "same" | "na">();
    for (const { hours, window } of lookaheadRows) {
      if (!window) {
        out.set(hours, "na");
        continue;
      }
      const grams = estimate.kwh_estimated * window.expected_gco2_kwh;
      if (grams < estimate.co2_grams_now) out.set(hours, "better");
      else if (grams > estimate.co2_grams_now) out.set(hours, "worse");
      else out.set(hours, "same");
    }
    return out;
  }, [estimate, lookaheadRows]);

  const activeSavingsPct = useMemo(() => {
    if (!estimate || !activeWindowGrams || estimate.co2_grams_now <= 0) return 0;
    return Math.max(
      0,
      Math.round(
        ((estimate.co2_grams_now - activeWindowGrams) / estimate.co2_grams_now) *
          100,
      ),
    );
  }, [estimate, activeWindowGrams]);

  const deferSavedGrams =
    estimate && activeWindowGrams
      ? Math.max(0, Math.round(estimate.co2_grams_now - activeWindowGrams))
      : 0;

  useEffect(() => {
    const available = ([4, 12, 24, 48] as const).find(
      (h) => cleanWindowsByLookahead[h],
    );
    if (available) setSelectedLookahead(available);
  }, [cleanWindowsByLookahead]);

  async function handleDeferRun() {
    if (!onDeferRun || deferSavedGrams <= 0) return;
    await onDeferRun(deferSavedGrams);
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <div className="w-full max-w-3xl rounded-lg border border-gg-border bg-gg-panel shadow-xl">
        <div className="flex items-center justify-between border-b border-gg-border px-5 py-3">
          <div>
            <h2 className="text-lg font-semibold">Run analysis</h2>
            <p className="text-xs text-gg-muted">
              Grid region:{" "}
              <span className="text-gg-text">{formatRegionLabel(region)}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-gg-muted hover:bg-gg-border hover:text-gg-text"
          >
            ✕
          </button>
        </div>

        <div className="space-y-5 px-5 py-4">
          {loading && (
            <p className="text-sm text-gg-muted">Crunching grid + carbon…</p>
          )}
          {error && <p className="text-sm text-gg-danger">{error}</p>}

          {estimate && cleanWindow && (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="If you run now" value={fmtGrams(estimate.co2_grams_now)} tone="warn" />
                <Stat
                  label={
                    waitIsBetter
                      ? `If you wait until ${fmtTime(activeOptimalStart)}`
                      : `Best future ${selectedLookahead}h window`
                  }
                  value={fmtGrams(activeWindowGrams ?? estimate.co2_grams_optimal)}
                  tone={waitIsBetter ? "ok" : "warn"}
                />
                <Stat label="Estimated GPU-hours" value={`${estimate.gpu_hours}`} />
                <Stat label="Confidence" value={estimate.confidence} />
              </div>

              <div className="rounded border border-gg-border bg-black/30 p-3">
                {waitIsBetter ? (
                  <p className="text-sm">
                    Waiting saves about{" "}
                    <strong className="text-gg-accent">{activeSavingsPct}%</strong>{" "}
                    CO₂ for this run on the {formatRegionLabel(region)} grid.
                  </p>
                ) : (
                  <p className="text-sm">
                    Waiting does not improve CO₂ in the next 48h forecast.{" "}
                    <strong className="text-gg-accent">Recommendation: run now.</strong>
                  </p>
                )}
              </div>

              <div className="rounded border border-gg-border bg-black/30 p-3">
                <p className="mb-2 text-xs uppercase tracking-wider text-gg-muted">
                  Best start by lookahead
                </p>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {lookaheadRows.map(({ hours, window }) => (
                    <button
                      key={hours}
                      type="button"
                      onClick={() => setSelectedLookahead(hours)}
                      disabled={!window}
                      className={`rounded border px-2 py-1.5 text-left ${
                        selectedLookahead === hours
                          ? "border-gg-accent bg-gg-accent/10"
                          : "border-white/10"
                      } disabled:cursor-not-allowed disabled:opacity-60`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[11px] text-gg-muted">Within {hours}h</p>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                            lookaheadComparison.get(hours) === "better"
                              ? "bg-emerald-500/20 text-emerald-300"
                              : lookaheadComparison.get(hours) === "worse"
                                ? "bg-amber-500/20 text-amber-300"
                                : lookaheadComparison.get(hours) === "same"
                                  ? "bg-slate-500/20 text-slate-300"
                                  : "bg-slate-700/30 text-slate-400"
                          }`}
                        >
                          {lookaheadComparison.get(hours) === "better"
                            ? "better"
                            : lookaheadComparison.get(hours) === "worse"
                              ? "worse"
                              : lookaheadComparison.get(hours) === "same"
                                ? "same"
                                : "n/a"}
                        </span>
                      </div>
                      <p className="text-sm font-medium">
                        {window ? fmtTime(window.optimal_start) : "Unavailable"}
                      </p>
                      {window && (
                        <p className="text-xs text-gg-muted">
                          {window.expected_gco2_kwh.toFixed(2)} gCO₂/kWh
                        </p>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p className="mb-2 text-xs uppercase tracking-wider text-gg-muted">
                  Next 48 hours — gCO₂/kWh
                </p>
                <div className="h-56 w-full">
                  <ResponsiveContainer>
                    <LineChart
                      data={cleanWindow.forecast_48h.map((p) => ({
                        ts: new Date(p.hour).getTime(),
                        v: p.gco2_kwh,
                      }))}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
                    >
                      <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="ts"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        stroke="#94a3b8"
                        tick={{ fontSize: 11 }}
                        tickFormatter={(t) =>
                          new Date(t).toLocaleString(undefined, {
                            month: "numeric",
                            day: "numeric",
                            hour: "2-digit",
                          })
                        }
                      />
                      <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} width={40} />
                      <Tooltip
                        contentStyle={{
                          background: "#0f172a",
                          border: "1px solid #1f2937",
                          color: "#e2e8f0",
                        }}
                        labelFormatter={(t) =>
                          new Date(Number(t)).toLocaleString()
                        }
                        formatter={(v: number) => [`${v} gCO₂/kWh`, "Intensity"]}
                      />
                      <ReferenceLine
                        x={new Date(activeOptimalStart).getTime()}
                        stroke="#22c55e"
                        strokeDasharray="4 4"
                        label={{
                          value: `Optimal (${selectedLookahead}h)`,
                          fill: "#22c55e",
                          fontSize: 11,
                          position: "top",
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="v"
                        stroke="#22c55e"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <ContextStrip weather={weather} campusHeat={campusHeat} />

              <GeminiReasoning suggestions={suggestions} />

              {estimate.detected_patterns.length > 0 && (
                <div>
                  <p className="mb-2 text-xs uppercase tracking-wider text-gg-muted">
                    Detected in your code
                  </p>
                  <ul className="space-y-1 text-sm">
                    {estimate.detected_patterns.map((p, i) => (
                      <li key={`${p.line}-${p.pattern}-${i}`} className="flex gap-3">
                        <span className="font-mono text-gg-muted">
                          line {p.line}
                        </span>
                        <span className="font-mono">{p.pattern}</span>
                        <span
                          className={
                            p.impact === "high"
                              ? "text-gg-danger"
                              : p.impact === "medium"
                                ? "text-gg-warn"
                                : "text-gg-accent"
                          }
                        >
                          {p.impact}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {(estimate.workload_practices ?? []).length > 0 && (
                <div className="mt-4">
                  <p className="mb-2 text-xs uppercase tracking-wider text-gg-muted">
                    Training &amp; infra practices
                  </p>
                  <p className="mb-2 text-[11px] leading-snug text-gg-muted">
                    High-scope signals (not yet folded into the gCO₂ number) — where ideal
                    tooling would look beyond model swaps.
                  </p>
                  <ul className="space-y-2 text-sm">
                    {(estimate.workload_practices ?? []).map((w) => (
                      <li
                        key={`${w.id}-${w.line}`}
                        className="rounded border border-white/5 bg-black/25 p-2"
                      >
                        <div className="flex flex-wrap items-baseline gap-2">
                          <span className="font-mono text-xs text-gg-muted">line {w.line}</span>
                          <span className="font-mono text-xs text-gg-accent">{w.label}</span>
                          <span
                            className={
                              w.impact === "high"
                                ? "text-xs text-gg-danger"
                                : w.impact === "medium"
                                  ? "text-xs text-gg-warn"
                                  : "text-xs text-gg-accent"
                            }
                          >
                            {w.impact}
                          </span>
                        </div>
                        <p className="mt-1 text-xs leading-snug text-slate-200">{w.rationale}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-gg-border px-5 py-3">
          <button
            type="button"
            onClick={handleDeferRun}
            disabled={!onDeferRun || deferSavedGrams <= 0}
            title={
              deferSavedGrams <= 0
                ? "No projected CO₂ savings from deferring in this selected window."
                : undefined
            }
            className="rounded border border-gg-accent/40 px-3 py-1.5 text-sm text-gg-accent hover:bg-gg-accent/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Defer run (+{fmtGrams(deferSavedGrams)})
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-gg-border px-3 py-1.5 text-sm hover:bg-gg-border"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn";
}) {
  const toneClass =
    tone === "ok"
      ? "text-gg-accent"
      : tone === "warn"
        ? "text-gg-warn"
        : "text-gg-text";
  return (
    <div className="rounded border border-gg-border bg-black/30 p-3">
      <p className="text-[10px] uppercase tracking-wider text-gg-muted">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}
