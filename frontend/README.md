# GridGreen — Frontend (Person A slice)

Next.js 15 (app router) + Tailwind + Monaco editor + Recharts.

Person A owns:
- Monaco editor with inline impact decorations (`gg-impact-*` line classes).
- Region selector + small grid-status badge in the header.
- "Run analysis" pre-run modal with a 48h gCO₂/kWh chart and "wait vs now" stats.

Person B layers on top of this shell with the suggestion sidebar, stats card,
`/mcp` page, and Gemini-powered NL reasoning inside the modal.

---

## Quick start

```bash
cd frontend
npm install
cp .env.example .env.local   # set BACKEND_URL if the API is not on localhost:8000
npm run dev
```

Open http://localhost:3000.

> The dev server proxies `/api/*` to `BACKEND_URL` (default `http://localhost:8000`)
> via a Next rewrite (`next.config.mjs`), so the browser can call `/api/...`
> without CORS issues.

### `npm audit` and Next.js

This app pins **Next `15.5.15`** so all current npm-reported **Next 14 / 15.5.x**
advisories (including **GHSA-q4gf-8mx6-v5v3**, fixed at `>=15.5.15`) are
addressed. **`package.json` `overrides`** bump **DOMPurify** (Monaco) and
**glob** (ESLint plugin) to patched minors.

Avoid **`npm audit fix --force`** here — it tends to jump to **Next 16** with
unreviewed breaking changes.

## Layout

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx          # Monaco + header + modal + suggestion sidebar
│   │   ├── globals.css       # Tailwind + .gg-impact-* line classes
│   │   └── mcp/page.tsx
│   ├── components/
│   │   ├── CodeEditor.tsx
│   │   ├── RunAnalysisModal.tsx
│   │   ├── SuggestionSidebar.tsx
│   │   └── …
│   └── lib/
│       ├── api.ts            # grid + suggest + scorecard client
│       └── sample.ts
├── next.config.mjs           # /api/* → BACKEND_URL rewrite
├── tailwind.config.ts
├── tsconfig.json
├── .env.example
└── package.json
```

## Wiring contract

Reads (typed in `lib/api.ts`):
- `POST /api/estimate_carbon` → fills the modal stats + line decorations.
- `GET  /api/check_grid?region=…` → header badge.
- `GET  /api/find_clean_window?region=…&hours_needed=4` → modal chart + optimal time line.

Stays in lockstep with [`../CONTRACT.md`](../CONTRACT.md).

## Person B components (drop-in)

| Component | Where Person A inserts it |
|---|---|
| `<SuggestionSidebar code={code} onApplySuggestion={...} />` | Right column of the main page. |
| `<StatsCard refreshKey={n} />` | Top of the right column. |
| `<GeminiReasoning suggestions={...} />` | Inside Person A's pre-run modal, below the 48h chart. |
| `/mcp` page | Already routed — link from header (already wired). |

Each component is fully self-contained: it manages its own loading / error
state. Prefer the **`/api/*` rewrite** to the backend; `NEXT_PUBLIC_API_BASE_URL`
is only needed if something calls the API host directly.

## Contract types

`src/types/api.ts` mirrors the backend Pydantic models. **Keep them in sync**
with [`../CONTRACT.md`](../CONTRACT.md).
