"use client";

import { motion } from "framer-motion";
import type { Suggestion } from "@/types/api";

interface Props {
  suggestion: Suggestion;
  onApply: (s: Suggestion) => void;
}

export function SuggestionCard({ suggestion, onApply }: Props) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="rounded-xl border border-white/10 bg-cardBg p-4 shadow-lg"
    >
      <header className="mb-2 flex items-center justify-between">
        <span className="rounded-full bg-leaf/15 px-2 py-0.5 text-xs font-medium text-leaf">
          line {suggestion.line}
        </span>
        <span className="text-xs text-ash">
          −{suggestion.carbon_saved_pct}% compute · {suggestion.performance_retained_pct}% perf
        </span>
      </header>

      <pre className="overflow-x-auto rounded-md bg-black/40 p-2 font-mono text-xs text-rose-300">
        - {suggestion.original_snippet}
      </pre>
      <pre className="mt-1 overflow-x-auto rounded-md bg-black/40 p-2 font-mono text-xs text-emerald-300">
        + {suggestion.alternative_snippet}
      </pre>

      <p className="mt-3 text-sm leading-relaxed text-slate-200">
        {suggestion.reasoning}
      </p>

      <footer className="mt-3 flex items-center justify-between text-xs text-ash">
        <cite className="not-italic">{suggestion.citation}</cite>
        <button
          type="button"
          onClick={() => onApply(suggestion)}
          className="rounded-md bg-leaf px-3 py-1.5 text-xs font-semibold text-ink transition hover:bg-leafDeep hover:text-white"
        >
          Apply
        </button>
      </footer>
    </motion.article>
  );
}
