# GridGreen — Frontend

Next.js 15 (app router) + Tailwind + Monaco editor + Recharts.

Features: Monaco editor with inline impact hints, region selector, run-analysis
modal with a 48h grid chart, suggestion sidebar, session scorecard, repo
analyzer, and an `/mcp` setup page.

---

## Quick start

```bash
cd frontend
npm install
cp .env.example .env.local   # set BACKEND_URL if the API is not on localhost:8000
npm run dev
```

Open http://localhost:3000.

> The dev server proxies `/api/*` to `BACKEND_URL` (default `http://127.0.0.1:8000`)
> via a Next rewrite (`next.config.mjs`), so the browser can call `/api/...`
> without CORS issues.

## Scripts

```bash
npm run dev      # development server
npm run build    # production build
npm run lint     # ESLint
```

## Layout

```
frontend/
├── src/
│   ├── app/           # Next.js pages (home, /mcp)
│   ├── components/    # Editor, modals, suggestion UI
│   ├── lib/           # API client, session helpers
│   └── types/         # TypeScript API types (mirrors CONTRACT.md)
├── .env.example
└── next.config.mjs
```
