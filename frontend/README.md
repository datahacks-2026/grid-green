# GridGreen — Frontend (Person A slice)

Next.js 14 (app router) + Tailwind + Monaco editor + Recharts.

Person A owns:
- Monaco editor with inline impact decorations (`gg-impact-*` line classes).
- Region selector + small grid-status badge in the header.
- "Run analysis" pre-run modal with a 48h gCO₂/kWh chart and "wait vs now" stats.

Person B layers on top of this shell with the suggestion sidebar, stats card,
`/mcp` page, and Gemini-powered NL reasoning inside the modal.

---

## Quick start
# GridGreen Frontend — Person B slice

## Local run

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000.

> The dev server proxies `/api/*` to `BACKEND_URL` (default `http://localhost:8000`)
> via a Next rewrite (`next.config.mjs`), so the backend can stay on a different
> port without CORS pain.

## Layout

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx              # editor + header + modal wiring
│   └── globals.css           # Tailwind + .gg-impact-* line classes
├── components/
│   ├── CodeEditor.tsx        # Monaco + deltaDecorations for inline hints
│   └── RunAnalysisModal.tsx  # 48h chart + stats
├── lib/
│   ├── api.ts                # typed client mirroring CONTRACT.md
│   └── sample.ts             # default training script in the editor
├── next.config.mjs           # /api/* → BACKEND_URL rewrite
├── tailwind.config.ts
├── postcss.config.mjs
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
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_BASE_URL at the backend
npm run dev
```

Open http://localhost:3000 — paste a script with `from_pretrained(...)` and
suggestion cards stream in from `/api/suggest_greener`.

## Person B components (drop-in)

| Component | Where Person A inserts it |
|---|---|
| `<SuggestionSidebar code={code} onApplySuggestion={...} />` | Right column of the main page. |
| `<StatsCard refreshKey={n} />` | Top of the right column. |
| `<GeminiReasoning suggestions={...} />` | Inside Person A's pre-run modal, below the 48h chart. |
| `/mcp` page | Already routed — link from header (already wired). |

Each component is fully self-contained: it manages its own loading / error
state and reads `NEXT_PUBLIC_API_BASE_URL` from the env. No props from
Person A's data layer are required.

## Contract types

`src/types/api.ts` mirrors `backend/app/schemas.py`. **Both files must change
together** — this is the source of truth from README §5.
