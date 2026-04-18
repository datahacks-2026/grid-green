"use client";

import { motion } from "framer-motion";
import type { Suggestion } from "@/types/api";

interface Props {
  suggestions: Suggestion[];
}

/**
 * Drop this directly inside Person A's pre-run modal, below the 48h chart.
 * It only renders when there's at least one Gemini-generated reasoning blurb.
 */
export function GeminiReasoning({ suggestions }: Props) {
  if (suggestions.length === 0) return null;
  const top = suggestions[0];

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className="mt-6 rounded-xl border border-leaf/30 bg-leaf/5 p-4"
    >
      <header className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-leaf">
        <span className="inline-block h-2 w-2 rounded-full bg-leaf" />
        Why this swap is worth it
      </header>
      <p className="mt-2 text-sm leading-relaxed text-slate-100">
        {top.reasoning}
      </p>
      <p className="mt-2 text-xs text-ash">{top.citation}</p>
    </motion.section>
  );
}
