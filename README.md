# GridGreen 

> **Project**: GridGreen (Ghost Grid Copilot)
> **Team Size**: 2 people
> **Tracks**: AI/ML + Cloud
> **Theme**: Environment, Climate, & Energy Sciences
> **Per-person budget**: 18-19 productive hours + 1-2 hours buffer for debugging & demo prep

---

## 1. The Time Reality

Out of 36 calendar hours, each person realistically has:

| Allocation | Hours |
|---|---|
| Productive build time | **18-19h** |
| Debugging & demo buffer | **1-2h** |
| Sleep | 6-7h |
| Food / breaks / workshops | 4-5h |
| Integration & context switches | 2-3h |
| **Total** | **~36h** |

**Ship less, ship well.** The plan below is sized to fit this budget with buffer protected.

---

## 2. Project in One Paragraph

GridGreen is a carbon-aware copilot for ML engineers. It analyzes any ML training script, estimates its compute cost, pairs that with real-time and forecasted grid carbon intensity, and tells the developer **when** to run, **where** to run, and **what cheaper model** to use — before a single GPU-hour is burned. Built as a web-based copilot plus an MCP server so any AI agent (Claude Desktop, Cursor, Claude Code) gets the same intelligence for free.

**Pitch line:** *"Every `model.fit()` is a climate decision. GridGreen makes that decision visible — at the exact moment developers make it."*

---

## 3. Prize Targets

| Target | Prize | Why We Win |
|---|---|---|
| AI/ML Track (main) | Track prize | Custom estimator + forecaster + RAG + MCP agent |
| Cloud Track (main) | Track prize | Streaming pipeline + multi-service architecture |
| Best Use of NVIDIA Brev.dev | $500 | Real GPU workload for embeddings + training |
| Best Use of Databricks | $1000 | Delta Live Tables + MLflow |
| Best Use of Snowflake API | Raspberry Pi | Cortex vector search + hybrid analytics |
| Most Innovative Build with AI (Google) | $1000 | Gemini powers NL reasoning |
| Best Use of Gemini API | Swag | Free from Google integration |
| Most Innovative Idea | $200 | Submit for free |

**Potential upside: ~$2,500+ in sponsor prizes plus main track wins.**

---

## 4. Final Architecture

```
┌─────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js on Vercel                           │
│  Monaco editor, inline hints, pre-run modal, stats card │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS
┌────────────────────▼────────────────────────────────────┐
│  BACKEND — FastAPI on Render (single service)           │
│  MCP server + HTTP API                                  │
│  Tools: estimate_carbon, suggest_greener, check_grid,   │
│         find_clean_window, get_scorecard                │
└──┬──────────┬──────────┬──────────┬────────────────────┘
   │          │          │          │
┌──▼────┐  ┌─▼──────┐  ┌▼──────┐  ┌▼──────┐
│ Grid  │  │Carbon  │  │Suggest│  │Score  │
│ Fcstr │  │Est.    │  │RAG +  │  │Store  │
│ (GBM) │  │(Rules) │  │Gemini │  │       │
└──┬────┘  └─┬──────┘  └┬──────┘  └┬──────┘
   │         │          │          │
   └─────────┼──────────┼──────────┘
             │          │
┌────────────▼──────────▼─────────────────┐
│  DATABRICKS (Delta Live Tables)          │
│  EIA streaming ingestion + features      │
└────────────┬─────────────────────────────┘
             ▼
┌──────────────────────────────────────────┐
│  SNOWFLAKE + CORTEX                       │
│  Grid history, benchmarks, vector index   │
└──────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────┐
│  NVIDIA BREV.DEV GPU                      │
│  Embedding generation + model training    │
└──────────────────────────────────────────┘

Supporting: Hugging Face, W&B, Gemini API,
Cursor (dev speed), Figma, Notion
```

---

## 5. The API Contract (Source of Truth)

**Locked at hour 1. Both people code against this.**

### POST /api/estimate_carbon
```json
// Request
{ "code": "string", "region": "CISO | ERCO | PJM | MISO | NYIS" }

// Response
{
  "co2_grams_now": 1840,
  "co2_grams_optimal": 340,
  "gpu_hours": 2.5,
  "kwh_estimated": 1.8,
  "confidence": "medium",
  "detected_patterns": [{ "line": 12, "pattern": "model.fit", "impact": "high" }]
}
```

### POST /api/suggest_greener
```json
// Request
{ "code": "string" }

// Response
{
  "suggestions": [{
    "line": 5,
    "original_snippet": "AutoModel.from_pretrained('flan-t5-xxl')",
    "alternative_snippet": "AutoModel.from_pretrained('flan-t5-large')",
    "carbon_saved_pct": 85,
    "performance_retained_pct": 94,
    "citation": "Chung et al., 2022.",
    "reasoning": "flan-t5-large retains 94% of xxl's performance..."
  }]
}
```

### GET /api/check_grid?region=CISO
```json
{ "region": "CISO", "current_gco2_kwh": 450, "trend": "rising", "last_updated": "..." }
```

### GET /api/find_clean_window?hours_needed=4&max_delay_hours=48&region=CISO
```json
{
  "optimal_start": "2026-04-20T03:00:00Z",
  "expected_gco2_kwh": 180,
  "current_gco2_kwh": 450,
  "co2_savings_pct": 62,
  "forecast_48h": [{ "hour": "...", "gco2_kwh": 440 }]
}
```

### GET /api/scorecard?session_id=abc
```json
{ "co2_saved_grams": 1200, "runs_deferred": 3, "suggestions_accepted": 2 }
```

---

## 6. Clean Work Split (Zero Overlap)

### 👤 Person A — ML / Backend / Data

**Budget:** 18h build + 1.5h buffer = 19.5h total

**Owns:**
1. EIA data pipeline → Snowflake
2. Databricks Delta Live Tables pipeline
3. Grid forecasting model (Prophet/XGBoost)
4. Rules-based code-to-carbon estimator
5. RAG index via Snowflake Cortex
6. Gemini API integration
7. FastAPI backend with 5 API + MCP tools
8. Render deployment
9. MCP config for Claude Desktop

**Stack:** Python, FastAPI, Snowflake, Databricks, scikit-learn, XGBoost, Prophet, Gemini SDK

---

### 👤 Person B — Product / Frontend / Demo

**Budget:** 18h build + 1.5h buffer = 19.5h total

**Owns:**
1. Next.js + Tailwind skeleton
2. Monaco editor integration
3. Inline hint rendering
4. Pre-run modal with 48h chart
5. RAG suggestion side panel
6. Stats card
7. "/mcp" config page
8. Vercel deployment
9. Architecture diagram (Figma)
10. 3-min demo video
11. Devpost copy + submission

**Stack:** TypeScript, Next.js, Tailwind, Monaco, Recharts, Framer Motion

---

## 7. Hour-by-Hour Schedule

> Saturday 9 AM start assumed. Adjust to actual kickoff.

### 🟢 Phase 1: Setup (Hours 0–2) — 2h each

**Person A:**
- [ ] Submit team + track form (AI/ML + Cloud)
- [ ] Create GitHub repo: `gridgreen` with `backend/` + `frontend/`
- [ ] Register EIA API key (instant)
- [ ] **Request Brev.dev GPU NOW** (async, takes 1-3h)
- [ ] Create Snowflake + Databricks + Gemini + W&B accounts
- [ ] Write `CONTRACT.md` (paste from §5)

**Person B:**
- [ ] Scaffold Next.js + Tailwind, deploy empty page to Vercel
- [ ] Install Monaco, verify Python syntax loads
- [ ] Figma: wireframe main screen
- [ ] Set up Notion status board (Doing/Blocked/Done)

**Checkpoint:** Repo exists, URLs live, contract locked.

---

### 🟡 Phase 2: Foundation (Hours 2–8) — 6h each

**Person A (6h):**
- [ ] FastAPI with 5 endpoints returning hardcoded contract-valid JSON (2h)
- [ ] Deploy to Render → public URL (1h)
- [ ] Pull 30 days EIA hourly data for 5 balancing authorities (1.5h)
- [ ] Load into Snowflake via script (1.5h)

**Person B (6h):**
- [ ] Main page layout: Monaco editor, sidebar, stats card (2.5h)
- [ ] Sample ML script as default content (15 min)
- [ ] Wire "Run Analysis" → POST → show JSON (1h)
- [ ] Design system: typography, colors, spacing (2h)

**Checkpoint:** Dummy data flows end-to-end. Polished shell.

---

### 🟠 Phase 3: Core Intelligence (Hours 8–14) — 6h each

**Person A (6h):**
- [ ] Grid forecasting model — Prophet on EIA data, 48h horizon (1.5h)
- [ ] Replace `check_grid` + `find_clean_window` with real predictions (1h)
- [ ] Rules-based carbon estimator: HF model lookup table + multipliers (2.5h)
- [ ] Wire `estimate_carbon` to real estimator (1h)

**Person B (6h):**
- [ ] Monaco inline decorations for detected ML patterns (2h)
- [ ] Pre-run modal: layout + 48h Recharts line graph + numbers (2.5h)
- [ ] Framer Motion modal transitions (30 min)
- [ ] Polish: hover states, loading spinners (1h)

**Checkpoint @ hour 14:** Real estimates inline. Real forecast chart. Both sleep.

---

### 🔵 Phase 4: Sleep Window (Hours 14–22)

**Both sleep 6-7 hours.** Staggered: Person A sleeps 14–20, Person B sleeps 15–22 (someone always awake for service outages).

**Low-intensity work only** if awake: writing Devpost copy, polishing CSS, fixing small visual bugs. **No risky integrations. No new features.**

---

### 🟣 Phase 5: Intelligence Layer (Hours 22–28) — 6h each

**Person A (6h):**
- [ ] RAG via Snowflake Cortex: scrape 30 HF model card pairs, embed, store as VECTOR (2.5h)
- [ ] Wire `suggest_greener`: model name extraction → Cortex similarity → alternatives (1h)
- [ ] Gemini API: reads retrieved context, writes NL reasoning paragraph (1.5h)
- [ ] Run reference workload profiling on Brev.dev GPU, screenshot (1h)

**Person B (6h):**
- [ ] Render RAG suggestions in sidebar: citation card + "apply" button (2h)
- [ ] Render Gemini reasoning in modal (1h)
- [ ] Stats card with live session numbers (1h)
- [ ] "/mcp" page: Claude Desktop config + copy button (1h)
- [ ] Architecture diagram in Figma (1h)

**Checkpoint:** Every feature works. Every sponsor tech visibly used.

---

### 🔴 Phase 6: Polish + Demo Prep (Hours 28–32) — 4h each

**Person A (4h):**
- [ ] Configure Databricks DLT pipeline for EIA stream (1.5h)
- [ ] Log W&B experiment + screenshot (30 min)
- [ ] Test MCP in Claude Desktop — paste config, verify tools, run query (1h)
- [ ] Write technical Devpost description (1h)

**Person B (4h):**
- [ ] **Record 3-min demo video** — see §9 (1.5h including retakes)
- [ ] Write user-facing Devpost description (1h)
- [ ] Devpost header image (30 min)
- [ ] Submit on Devpost, select ALL prize categories (1h)

**Checkpoint @ hour 32:** Submitted. Video live. Forms filled.

---

### 🟢 Phase 7: Buffer + Rehearsal (Hours 32–36) — 1.5h each + rest

**Both (1.5h each):**
- [ ] Rehearse pitch out loud × 3 (30 min)
- [ ] Test live demo on clean incognito browser (30 min)
- [ ] Confirm backup video plays in browser tab (15 min)
- [ ] Fix critical bugs only — strict 15 min cap (15 min)

**Remaining time:** Rest. Eat. Be fresh for judging.

---

## 8. Per-Person Hour Summary

### Person A (ML/Backend)

| Phase | Hours | Cumulative |
|---|---|---|
| Phase 1 — Setup | 2 | 2 |
| Phase 2 — Foundation | 6 | 8 |
| Phase 3 — Core | 6 | 14 |
| Phase 4 — Sleep | 0 | 14 |
| Phase 5 — Intelligence | 6 | 20 |
| Phase 6 — Polish | 4 | 24 |
| Phase 7 — Buffer | 1.5 | 25.5 |

**Productive build: 18h • Buffer: 1.5h • Total: 19.5h**

### Person B (Product/Frontend)

| Phase | Hours | Cumulative |
|---|---|---|
| Phase 1 — Setup | 2 | 2 |
| Phase 2 — Foundation | 6 | 8 |
| Phase 3 — Core | 6 | 14 |
| Phase 4 — Sleep | 0 | 14 |
| Phase 5 — Intelligence | 6 | 20 |
| Phase 6 — Polish + Demo | 4 | 24 |
| Phase 7 — Buffer | 1.5 | 25.5 |

**Productive build: 18h • Buffer: 1.5h (+1.5h embedded in Phase 6 for video retakes) • Total: 19.5h**

---

## 9. Demo Video Script (3 Minutes, Memorize)

**[0:00–0:15] Hook**
> "Every ML engineer types `model.fit(epochs=500)` without thinking. Depending on when and where that code runs, it could emit 200g of CO₂ or 2kg. Nobody sees that. We made it visible."

**[0:15–0:45] Product in action**
Paste training script → carbon annotations appear inline → hover for breakdown → click "Run Analysis."

**[0:45–1:30] The intelligence**
Modal: 48h grid forecast, "1.84kg now vs 340g at 3am." RAG suggestion: "flan-t5-large saves 85% carbon, retains 94% performance. Chung et al. 2022."

**[1:30–2:00] Architecture (20s)**
Diagram flash. Call out Databricks streaming, Snowflake Cortex, NVIDIA GPU, Gemini, MCP.

**[2:00–2:30] MCP moment**
Claude Desktop with GridGreen tools loaded. Ask: "Should I train this now?" Claude answers with real data.

**[2:30–3:00] Close**
> "AI's carbon footprint grows 10x every two years. The infrastructure to make it climate-aware doesn't exist. We built it this weekend. GridGreen — the missing layer between your code and the planet."

---

## 10. The "Stuck" Protocol

**Declare blocks in the Notion board within 30 minutes. No silent suffering.**

### Escalation
- 5 min: obvious fixes
- 15 min: read error, search docs
- 30 min: ask Cursor/Codex with full context
- 45 min: rubber-duck with teammate
- **60 min: PIVOT — mock it, move on, return if time allows**

### Contingencies

| If... | Then... |
|---|---|
| Brev.dev doesn't provision | Use CPU. Run profiling when it arrives. Screenshots = prize entry. |
| Snowflake auth fails | Dump to local SQLite. Fix later. |
| Databricks flaky | Run as local Python. Screenshot any working notebook. |
| Gemini fails | Hardcode NL responses. Note fallback honestly. |
| Monaco breaks | Fall back to `<textarea>` + sidebar hints. |
| Live demo fails on stage | Switch to pre-recorded video. Don't apologize. |

---

## 11. Scope Cuts (Baked In — Don't Relitigate)

| Cut | Replaced With | Saved |
|---|---|---|
| Neural-net carbon estimator | Rules-based w/ HF lookup | 8-10h |
| Fine-tuned Chronos | Prophet/XGBoost | 3-4h |
| Microservices | Single FastAPI | 3-5h |
| Separate dashboard page | Stats card inline | 3h |
| VS Code extension | Web + "/mcp" page | 8-10h |
| DigitalOcean | Render | 1h |

**Total saved: ~30h.** That's what makes 18h per person fit.

---

## 12. Communication Rules

- **3-hour sync rhythm:** 5-min standup every 3 hours
- **Notion board:** 3 columns (Doing/Blocked/Done), updated each sync
- **Git discipline:** Commit often; pull teammate's work after each commit
- **No heroics past hour 30:** Polish and fix only
- **Contract immutable after hour 4:** Changes require explicit sync

---

## 13. Success Definitions

### 🟢 Minimum (must ship by hour 32)
- Main page with Monaco editor
- Paste code → ≥1 real carbon annotation
- "Run Analysis" modal with real 48h forecast
- ≥1 RAG suggestion working
- 3-min demo video
- Public URLs
- Devpost submitted

### 🟡 Target (aim here)
- All 5 API tools real
- Gemini NL explanations
- MCP live in Claude Desktop
- Databricks pipeline visible
- Snowflake Cortex live
- Brev.dev screenshots captured
- All prize categories submitted

### 🔵 Stretch (only if ahead by hour 28)
- Multi-region forecasting
- Extra RAG domain (batch-size efficiency)
- Viral social share image

---

## 14. Devpost Submission Checklist

- [ ] Project name: **GridGreen**
- [ ] Tagline: *"Carbon-aware scheduling for ML workloads."*
- [ ] Tracks: **AI/ML** + **Cloud**
- [ ] Prize categories:
  - [ ] Best Use of NVIDIA Brev.dev
  - [ ] Best Use of Databricks
  - [ ] Best Use of Snowflake API
  - [ ] Most Innovative Build with AI (Google)
  - [ ] Best Use of Gemini API
  - [ ] Most Innovative Idea
  - [ ] Most Viral Idea
- [ ] 3-min demo video uploaded
- [ ] GitHub repo linked
- [ ] Live URL added
- [ ] Screenshots (≥4: main UI, modal, architecture, MCP in Claude)
- [ ] Tech stack listed
- [ ] Team members added

---

## 15. The One Rule That Matters

**By hour 24 the demo path must work end-to-end, even if the intelligence behind it is imperfect.**

A beautiful demo with some hardcoded values beats a "real" system that doesn't render.

**Protect the demo path above all else.**

---

*Ship it.*
