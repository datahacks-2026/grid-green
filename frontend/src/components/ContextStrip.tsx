"use client";

import type { CampusHeatContext, WeatherContext } from "@/lib/api";

type Props = {
  weather: WeatherContext | null;
  campusHeat: CampusHeatContext | null;
};

/**
 * Optional narrative layer below the 48h chart in `RunAnalysisModal`.
 *
 * - NOAA weather (`/api/context/weather`) explains *why* the grid might
 *   be dirty right now (e.g. heat → AC load).
 * - Scripps-style heat-map aggregate (`/api/context/campus_heat`)
 *   surfaces the hyperlocal dataset and keeps the Scripps prize claim
 *   visible in the demo.
 *
 * Both calls are best-effort. If either returns null (NOAA 502, CSV
 * missing, fetch aborted) we hide that side gracefully — the strip
 * itself only renders when at least one source has data.
 */
export function ContextStrip({ weather, campusHeat }: Props) {
  if (!weather && !campusHeat) return null;

  return (
    <div>
      <p className="mb-2 text-xs uppercase tracking-wider text-gg-muted">
        Context · why the grid looks like this
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {weather && <WeatherCard w={weather} />}
        {campusHeat && <HeatCard h={campusHeat} />}
      </div>
    </div>
  );
}

function WeatherCard({ w }: { w: WeatherContext }) {
  const temp =
    w.temperature_f !== null ? `${Math.round(w.temperature_f)}°F now` : "—";
  const high =
    w.high_24h_f !== null ? `${Math.round(w.high_24h_f)}°F next 24h` : null;

  return (
    <div className="rounded border border-gg-border bg-black/30 p-3">
      <p className="text-[10px] uppercase tracking-wider text-gg-muted">
        NOAA · {w.location_label}
      </p>
      <p className="mt-1 text-sm">
        <span className="font-semibold text-gg-text">{temp}</span>
        {high && <span className="text-gg-muted"> · {high}</span>}
      </p>
      {w.short_forecast && (
        <p className="mt-1 line-clamp-2 text-xs text-gg-muted">
          {w.short_forecast}
        </p>
      )}
    </div>
  );
}

function HeatCard({ h }: { h: CampusHeatContext }) {
  const tC =
    h.mean_temperature_c !== null ? `${h.mean_temperature_c.toFixed(1)}°C` : "—";
  const rh =
    h.mean_relative_humidity !== null
      ? `${Math.round(h.mean_relative_humidity * 100)}% RH`
      : null;
  return (
    <div className="rounded border border-gg-border bg-black/30 p-3">
      <p className="text-[10px] uppercase tracking-wider text-gg-muted">
        Scripps heat map · {h.n_stations} stations · {h.n_points} obs
      </p>
      <p className="mt-1 text-sm">
        <span className="font-semibold text-gg-text">{tC}</span>
        {rh && <span className="text-gg-muted"> · {rh}</span>}
      </p>
      <p className="mt-1 text-xs text-gg-muted">
        Hyperlocal cooling-load proxy (UCSD mobile sensors).
      </p>
    </div>
  );
}
