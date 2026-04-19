"use client";

import { useState } from "react";

const CONFIG = {
  mcpServers: {
    gridgreen: {
      command: "python",
      args: ["/absolute/path/to/gridgreen/backend/mcp_server.py"],
      cwd: "/absolute/path/to/gridgreen/backend",
      env: {
        EIA_API_KEY: "<your_eia_key>",
        GEMINI_API_KEY: "<your_gemini_key>",
        SQLITE_PATH: "/absolute/path/to/gridgreen/backend/data/gridgreen.sqlite",
      },
    },
  },
};

const CONFIG_TEXT = JSON.stringify(CONFIG, null, 2);

export default function McpConfigPage() {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(CONFIG_TEXT);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-3xl font-semibold">Use GridGreen inside your AI agent</h1>
      <p className="mt-3 text-slate-300">
        GridGreen ships an MCP server. Drop the config below into Claude Desktop,
        Cursor, or Claude Code, restart the host, and the carbon-aware tools
        light up automatically.
      </p>

      <section className="mt-8 rounded-2xl border border-white/10 bg-cardBg p-5">
        <header className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ash">
            Claude Desktop / Cursor config
          </h2>
          <button
            type="button"
            onClick={copy}
            className="rounded-md bg-leaf px-3 py-1.5 text-xs font-semibold text-ink transition hover:bg-leafDeep hover:text-white"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </header>
        <pre className="overflow-x-auto rounded-lg bg-black/50 p-4 font-mono text-xs leading-relaxed text-emerald-200">
{CONFIG_TEXT}
        </pre>
        <p className="mt-3 text-xs text-ash">
          Path:{" "}
          <code className="font-mono text-slate-300">
            ~/Library/Application Support/Claude/claude_desktop_config.json
          </code>{" "}
          (macOS) or{" "}
          <code className="font-mono text-slate-300">
            %APPDATA%\Claude\claude_desktop_config.json
          </code>{" "}
          (Windows).
        </p>
      </section>

      <section className="mt-8 grid gap-4 sm:grid-cols-2">
        <Tool name="estimate_carbon" desc="CO₂ now vs optimal for a script." />
        <Tool name="suggest_greener" desc="Greener model swaps + Gemini reasoning." />
        <Tool name="check_grid" desc="Live gCO₂/kWh for a region." />
        <Tool name="find_clean_window" desc="Lowest-carbon window in next 48h." />
        <Tool name="get_scorecard" desc="Cumulative session savings." />
      </section>

      <section className="mt-10 text-sm text-slate-300">
        <h3 className="text-base font-semibold text-slate-100">Try it</h3>
        <p className="mt-1">
          Restart your host, then ask Claude:{" "}
          <em className="text-leaf">
            “I’m about to train flan-t5-xxl on CISO. Should I run now?”
          </em>
        </p>
      </section>
    </main>
  );
}

function Tool({ name, desc }: { name: string; desc: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-cardBg p-4">
      <div className="font-mono text-sm text-leaf">{name}</div>
      <div className="mt-1 text-xs text-ash">{desc}</div>
    </div>
  );
}
