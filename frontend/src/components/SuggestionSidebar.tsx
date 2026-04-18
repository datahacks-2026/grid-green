"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getSessionId } from "@/lib/session";
import type { Suggestion } from "@/types/api";
import { SuggestionCard } from "./SuggestionCard";

interface Props {
  /**
   * Current editor source. The sidebar refetches whenever this changes
   * (debounced) — Person A's Monaco component just needs to keep this prop
   * up to date.
   */
  code: string;
  /** Called when user clicks Apply on a card; the editor should swap the snippet. */
  onApplySuggestion: (s: Suggestion) => void;
  /** Optional callback so the parent can refresh the stats card. */
  onScorecardChange?: () => void;
}

export function SuggestionSidebar({
  code,
  onApplySuggestion,
  onScorecardChange,
}: Props) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!code.trim()) {
      setSuggestions([]);
      return;
    }
    const handle = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.suggestGreener(code);
        setSuggestions(res.suggestions);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }, 600);
    return () => clearTimeout(handle);
  }, [code]);

  async function handleApply(s: Suggestion) {
    onApplySuggestion(s);
    try {
      await api.recordEvent({
        session_id: getSessionId(),
        event: "suggestion_accepted",
        co2_saved_grams: Math.round((s.carbon_saved_pct / 100) * 1000),
      });
      onScorecardChange?.();
    } catch {
      /* fail silently — the swap already happened in the editor */
    }
  }

  return (
    <aside className="flex h-full w-full flex-col gap-3 overflow-y-auto p-4">
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ash">
          Greener alternatives
        </h2>
        {loading && <span className="text-xs text-ash">analyzing…</span>}
      </header>

      {error && (
        <p className="rounded-md bg-rose-500/10 p-2 text-xs text-rose-300">
          {error}
        </p>
      )}

      {!loading && suggestions.length === 0 && !error && (
        <p className="rounded-md border border-dashed border-white/10 p-4 text-xs text-ash">
          No swap suggestions yet — try pasting a script that uses
          <code className="mx-1 font-mono text-leaf">from_pretrained(...)</code>.
        </p>
      )}

      {suggestions.map((s) => (
        <SuggestionCard
          key={`${s.line}-${s.alternative_snippet}`}
          suggestion={s}
          onApply={handleApply}
        />
      ))}
    </aside>
  );
}
