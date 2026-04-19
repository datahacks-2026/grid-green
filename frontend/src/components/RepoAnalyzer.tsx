"use client";

import { useState } from "react";

import {
  api,
  type AnalyzeRepoResponse,
  type EstimateCarbonResponse,
  type FindCleanWindowResponse,
  formatRegionLabel,
  type Region,
} from "@/lib/api";

type Props = {
  region: Region;
  /** Filled after a successful scan — parent uses this for `estimate_carbon` + clean window. */
  onAggregatedCode?: (
    code: string,
    meta: { fileCount: number; truncated: boolean },
  ) => void;
  estimate?: EstimateCarbonResponse | null;
  cleanWindow?: FindCleanWindowResponse | null;
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

export function RepoAnalyzer({
  region,
  onAggregatedCode,
  estimate,
  cleanWindow,
}: Props) {
  const [url, setUrl] = useState("https://github.com/huggingface/transformers");
  const [ref, setRef] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeRepoResponse | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.analyzeRepo({
        repo_url: url.trim(),
        ref: ref.trim() || undefined,
        region,
        top_k_per_file: 2,
        max_files_with_hits: 25,
      });
      setResult(res);
      onAggregatedCode?.(res.aggregated_code_for_estimate, {
        fileCount: res.aggregate_file_count,
        truncated: res.aggregate_truncated,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex flex-col gap-2 rounded-lg border border-gg-border bg-black/20 p-3">
        <label className="text-xs font-semibold uppercase tracking-wider text-gg-muted">
          GitHub repo URL
        </label>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://github.com/owner/repo"
          className="rounded border border-gg-border bg-gg-bg px-2 py-1.5 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-gg-accent"
        />

        <label className="mt-1 text-xs font-semibold uppercase tracking-wider text-gg-muted">
          Branch / tag / sha (optional)
        </label>
        <input
          type="text"
          value={ref}
          onChange={(e) => setRef(e.target.value)}
          placeholder="main"
          className="rounded border border-gg-border bg-gg-bg px-2 py-1.5 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-gg-accent"
        />

        <button
          type="button"
          onClick={run}
          disabled={loading || !url.trim()}
          className="mt-2 w-fit rounded bg-gg-accent px-3 py-1.5 text-sm font-semibold text-black hover:bg-gg-accentDim disabled:opacity-50"
        >
          {loading ? "Scanning…" : "Scan repo"}
        </button>

        <p className="text-[11px] leading-snug text-gg-muted">
          Public repos work without credentials. Set <code>GITHUB_TOKEN</code> on the
          backend to raise the rate limit or scan private repos. Caps: 200 files,
          50 MB compressed, 1 MB per file.
        </p>
        <p className="text-[11px] leading-snug text-gg-accent/90">
          After <strong className="text-gg-text">Scan repo</strong>, click{" "}
          <strong className="text-gg-text">Run analysis</strong> in the header for the same
          grid CO₂ estimate + <em>when to train</em> (48h forecast / cleaner window) as in
          code mode — it uses the scanned source files (byte-capped like pasted code).
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-rose-500/10 p-2 text-xs text-rose-300">{error}</p>
      )}

      {estimate && cleanWindow && (
        <div className="rounded-lg border border-gg-accent/40 bg-gg-accent/10 p-3 text-xs leading-relaxed text-gg-text">
          <p className="font-semibold text-gg-accent">
            When to run — {formatRegionLabel(region)}
          </p>
          <p className="mt-1 text-gg-muted">
            Cleaner window starts around{" "}
            <span className="font-mono text-gg-text">{fmtTime(cleanWindow.optimal_start)}</span>
            — grid intensity ~{cleanWindow.expected_gco2_kwh.toFixed(0)} gCO₂/kWh vs{" "}
            {cleanWindow.current_gco2_kwh.toFixed(0)} now (
            <span className="text-gg-accent">~{cleanWindow.co2_savings_pct.toFixed(0)}% lower</span>
            ).
          </p>
          <p className="mt-1 text-gg-muted">
            Script estimate (aggregated repo): ~{estimate.co2_grams_now.toFixed(0)} g CO₂ if you run
            now vs ~{estimate.co2_grams_optimal.toFixed(0)} g aligned with that window (same code,
            different timing).
          </p>
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <header className="flex flex-wrap items-baseline justify-between gap-2 rounded border border-gg-border bg-black/30 px-3 py-2 text-xs">
            <div>
              <span className="font-semibold text-gg-text">
                {result.owner}/{result.repo}
              </span>{" "}
              <span className="text-gg-muted">
                — {result.files_scanned} files scanned, {result.files_with_hits} with greener
                suggestions
              </span>
            </div>
            <span className="font-mono text-gg-accent">
              {result.total_suggestions} suggestion{result.total_suggestions === 1 ? "" : "s"}
            </span>
          </header>
          <p className="text-[11px] text-gg-muted">
            <strong className="text-gg-text">Run analysis</strong> uses{" "}
            <span className="font-mono text-gg-accent">{result.aggregate_file_count}</span> source
            file(s) merged for <code className="font-mono text-gg-text">estimate_carbon</code>
            {result.aggregate_truncated ? " (byte-truncated to the API limit)." : "."}
          </p>

          {result.files_with_hits === 0 && (
            <p className="rounded-md border border-dashed border-gg-border p-3 text-xs text-gg-muted">
              No supported model ids were detected (or none matched our swap corpus). Works
              best with Hugging Face{" "}
              <code className="text-gg-text">from_pretrained</code> /{" "}
              <code className="text-gg-text">SentenceTransformer</code>, OpenAI / Anthropic
              SDK calls, or explicit{" "}
              <code className="text-gg-text">namespace/model</code> hub strings. Pure pandas /
              API-only repos often have nothing to swap.
            </p>
          )}

          {result.files.map((f) => (
            <article
              key={f.path}
              className="rounded-lg border border-gg-border bg-gg-panel p-3"
            >
              <h3 className="mb-2 font-mono text-xs text-gg-accent">{f.path}</h3>
              <ul className="space-y-2">
                {f.suggestions.map((s, i) => (
                  <li key={`${f.path}-${i}`} className="rounded border border-white/5 bg-black/30 p-2">
                    <div className="flex items-center justify-between text-[11px] text-gg-muted">
                      <span>line {s.line}</span>
                      <span>
                        −{s.carbon_saved_pct}% CO₂ · {s.performance_retained_pct}% perf
                      </span>
                    </div>
                    <pre className="mt-1 overflow-x-auto rounded bg-black/50 p-1.5 font-mono text-[11px] text-rose-300">
                      − {s.original_snippet}
                    </pre>
                    <pre className="mt-0.5 overflow-x-auto rounded bg-black/50 p-1.5 font-mono text-[11px] text-emerald-300">
                      + {s.alternative_snippet}
                    </pre>
                    <p className="mt-1.5 text-xs leading-snug text-slate-200">
                      {s.reasoning}
                    </p>
                    <p className="mt-1 text-[10px] italic text-gg-muted">{s.citation}</p>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
