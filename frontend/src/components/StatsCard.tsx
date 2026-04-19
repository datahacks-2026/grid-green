"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getSessionId } from "@/lib/session";
import type { Scorecard } from "@/types/api";

interface Props {
  /** Bump this number to force a refetch (e.g. after Apply / Defer). */
  refreshKey?: number;
}

export function StatsCard({ refreshKey = 0 }: Props) {
  const [card, setCard] = useState<Scorecard>({
    co2_saved_grams: 0,
    runs_deferred: 0,
    suggestions_accepted: 0,
  });

  useEffect(() => {
    let cancelled = false;
    api
      .getScorecard(getSessionId())
      .then((c) => !cancelled && setCard(c))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return (
    <section className="rounded-2xl border border-white/10 bg-cardBg p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-ash">
        Your session impact
      </h3>
      <dl className="mt-3 grid grid-cols-3 gap-3 text-center">
        <Stat
          label="CO₂ saved"
          value={formatGrams(card.co2_saved_grams)}
          accent
        />
        <Stat label="Runs deferred" value={String(card.runs_deferred)} />
        <Stat
          label="Swaps applied"
          value={String(card.suggestions_accepted)}
        />
      </dl>
    </section>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-ash">{label}</dt>
      <dd
        className={
          "mt-1 text-xl font-semibold " + (accent ? "text-leaf" : "text-slate-100")
        }
      >
        {value}
      </dd>
    </div>
  );
}

function formatGrams(g: number): string {
  if (g >= 1000) return `${(g / 1000).toFixed(1)} kg`;
  return `${g} g`;
}
