"use client";

import { useState } from "react";
import { SuggestionSidebar } from "@/components/SuggestionSidebar";
import { StatsCard } from "@/components/StatsCard";
import type { Suggestion } from "@/types/api";

const SAMPLE = `from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-xxl")
model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-xxl")

# ... training loop ...
`;

export default function Home() {
  const [code, setCode] = useState(SAMPLE);
  const [refresh, setRefresh] = useState(0);

  function handleApply(s: Suggestion) {
    setCode((prev) => prev.split(s.original_snippet).join(s.alternative_snippet));
  }

  return (
    <main className="grid h-screen grid-cols-12 gap-0">
      {/* LEFT: Person A's Monaco editor will replace this textarea. */}
      <section className="col-span-7 flex flex-col border-r border-white/5">
        <header className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <h1 className="text-sm font-semibold uppercase tracking-wider text-leaf">
            GridGreen
          </h1>
          <a href="/mcp" className="text-xs text-ash hover:text-leaf">
            Use in Claude / Cursor →
          </a>
        </header>
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          spellCheck={false}
          className="flex-1 resize-none bg-black/40 p-5 font-mono text-sm text-slate-100 outline-none"
        />
      </section>

      {/* RIGHT: Person B's panels. */}
      <section className="col-span-5 flex flex-col gap-4 overflow-y-auto bg-ink/95 p-4">
        <StatsCard refreshKey={refresh} />
        <SuggestionSidebar
          code={code}
          onApplySuggestion={handleApply}
          onScorecardChange={() => setRefresh((n) => n + 1)}
        />
      </section>
    </main>
  );
}
