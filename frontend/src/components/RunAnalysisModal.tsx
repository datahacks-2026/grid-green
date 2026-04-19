"use client";

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
  region: Region;
  loading: boolean;
  error?: string | null;
  estimate?: EstimateCarbonResponse | null;
  cleanWindow?: FindCleanWindowResponse | null;
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
  region,
  loading,
  error,
  estimate,
  cleanWindow,
  suggestions = [],
  weather = null,
  campusHeat = null,
}: Props) {
  if (!open) return null;

  const savings =
    estimate && estimate.co2_grams_now > 0
      ? Math.round(
          ((estimate.co2_grams_now - estimate.co2_grams_optimal) /
            estimate.co2_grams_now) *
            100,
        )
      : 0;

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
                  label={`If you wait until ${fmtTime(cleanWindow.optimal_start)}`}
                  value={fmtGrams(estimate.co2_grams_optimal)}
                  tone="ok"
                />
                <Stat label="Estimated GPU-hours" value={`${estimate.gpu_hours}`} />
                <Stat label="Confidence" value={estimate.confidence} />
              </div>

              <div className="rounded border border-gg-border bg-black/30 p-3">
                <p className="text-sm">
                  Waiting saves about <strong className="text-gg-accent">{savings}%</strong>{" "}
                  CO₂ for this run on the {formatRegionLabel(region)} grid.
                </p>
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
                        x={new Date(cleanWindow.optimal_start).getTime()}
                        stroke="#22c55e"
                        strokeDasharray="4 4"
                        label={{
                          value: "Optimal",
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
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-gg-border px-5 py-3">
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
