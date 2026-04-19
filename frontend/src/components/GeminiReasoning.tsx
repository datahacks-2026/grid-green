"use client";

import { motion } from "framer-motion";
import type { Suggestion } from "@/types/api";

interface Props {
  suggestions: Suggestion[];
}

/**
 * Renders the top suggestion's NL reasoning paragraph (Gemini-polished
 * when `GEMINI_API_KEY` is set on the backend; corpus reasoning otherwise).
 *
 * Lives inside `RunAnalysisModal` *below* the 48h chart so the judge sees:
 *
 *   "When to run"   (chart)
 *   "Why this swap" (this component — the model-intelligence story)
 *
 * Renders nothing when there are no suggestions, so it's safe to mount
 * unconditionally in the modal.
 */
export function GeminiReasoning({ suggestions }: Props) {
  if (suggestions.length === 0) return null;
  const top = suggestions[0];

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: 0.05 }}
      className="rounded border border-gg-accent/40 bg-gg-accent/5 p-4"
    >
      <header className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-gg-accent">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-gg-accent" />
        Why this swap is worth it
      </header>

      <div className="mt-2 grid gap-2 text-sm">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 font-mono text-xs">
          <span className="text-gg-muted">line {top.line}</span>
          <span className="text-gg-danger line-through">
            {top.original_snippet}
          </span>
          <span className="text-gg-muted">→</span>
          <span className="text-gg-accent">{top.alternative_snippet}</span>
        </div>
        <p className="leading-relaxed text-gg-text">{top.reasoning}</p>
        <p className="text-xs text-gg-muted">
          <span className="font-semibold">−{top.carbon_saved_pct}% CO₂</span>
          <span className="mx-2">·</span>
          <span>{top.performance_retained_pct}% performance retained</span>
          <span className="mx-2">·</span>
          <span>{top.citation}</span>
        </p>
      </div>
    </motion.section>
  );
}
