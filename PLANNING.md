# GridGreen — Internal Hackathon Planning

> This file contains the original DataHacks 2026 planning docs: schedules,
> work splits, demo scripts, contingencies, and checklists. For the project
> overview, see [`README.md`](README.md).

> **Project**: GridGreen (Ghost Grid Copilot)
> **Team Size**: 2 people
> **Tracks**: AI/ML + Cloud
> **Theme**: Environment, Climate, & Energy Sciences
> **Per-person budget**: 18-19 productive hours + 1-2 hours buffer for debugging & demo prep

---

## 0. Canonical build docs (read first)

| Doc | Use it for |
|-----|------------|
| **`split.md`** | **Authoritative work split** — each person owns a **full-stack vertical slice**; first big merge **~hour 8–14**. Overrides older **§7 / §8** ownership lines when they disagree. |
| **`a.md`** | **Person A** — §0 minimum ship + sponsor must-use (**Brev**, **AWS**, **GCP**), hackathon **dataset** notes (EIA, optional Scripps/NOAA), implementation details, MCP. |
| **This file §6** | **API contract** — request/response JSON; still the source of truth for both people. |
| **This file §8+** | **Timing** and checkpoints — still useful; **reassign tasks** per `split.md` when a line item conflicts (e.g. Monaco / `suggest_greener` / MCP wiring). |

Hackathon **dataset eligibility**, optional **NOAA / heat map**, and **$200 AWS / $5 GCP (non-.edu) / Brev** requirements are documented in **`a.md`** (not duplicated here).

---

## DataHacks 2026 compliance (judge cheat-sheet)

- **Theme — Environment, Climate, & Energy Sciences:** every endpoint
  serves a carbon-aware-compute workflow; the user-facing pitch is
  literally "every `model.fit()` is a climate decision."
- **Required dataset (ML/AI + Cloud tracks):** **EIA — US Energy
  Information Administration** is on the official Non-Scripps Energy
  list. Wired end-to-end via `backend/app/services/eia_client.py`
  (ingest) → `storage.insert_eia_rows` (SQLite + Snowflake mirror) →
  `forecaster.find_clean_window` / `check_grid` (HTTP + MCP tools).
  **Verify locally:** after `python -m scripts.ingest_eia` (from `backend/`),
  call **`GET /api/diagnostics`** and check **`storage.eia_hourly.row_count`**
  (and `ts_min_utc` / `ts_max_utc`). Same numbers appear if you query SQLite
  directly — see **`HOW_TO_RUN.md`**.
- **Optional Scripps dataset (status: code-ready, data pending):**
  `GET /api/context/campus_heat`
  (`backend/app/routes/context.py`) ingests
  `backend/data/sample_heatmap.csv` and exposes a small aggregate
  surfaced inside the pre-run modal next to the 48h grid chart. The
  bundled CSV is **synthetic** so the demo path works without
  credentials; **drop the real Scripps mobile-weather CSV in place
  (same columns) before claiming the Scripps $1,500 prize.**
- **Tracks targeted (max 2):** AI/ML + Cloud.
- **Sponsor integrations shipped (re-runnable scripts):**
  - **AWS** — `python -m scripts.sagemaker_processing` launches a
    SageMaker Processing Job on `ml.t3.medium`. *Capture the job
    ARN/console screenshot for Devpost.*
  - **Snowflake** — `python -m scripts.build_rag_index --target
    snowflake` populates `RAG_HF_CORPUS` with `VECTOR(FLOAT, 384)` via
    `PARSE_JSON`; EIA is mirrored to `EIA_HOURLY` on every ingest. The
    runtime RAG path uses `VECTOR_COSINE_SIMILARITY` when
    `GRIDGREEN_RAG_BACKEND=auto|snowflake` and SBERT is loaded.
  - **NVIDIA Brev / W&B** — `python -m scripts.brev_embed` runs the
    embedding workload on a Brev GPU and optionally logs to W&B when
    `WANDB_API_KEY` is set. *Sponsor proof requires actually executing
    this on a Brev instance and capturing the run.*
  - **Databricks** — `python -m scripts.dlt_pipeline` is dual-mode: it
    registers `@dlt.table` stages inside Databricks and falls back to a
    local pandas+SQLite runner so the same script demos offline. *DLT
    prize requires an actual pipeline run inside a Databricks
    workspace; the local fallback alone is not sponsor evidence.*
  - **Google / Gemini** — `app/services/gemini_service.py` polishes
    `suggest_greener` reasoning when `GEMINI_API_KEY` is set; the
    polished paragraph is rendered inside the pre-run modal via
    `GeminiReasoning`.
  - **MCP / Claude Desktop** — `backend/mcp_server.py` exposes the five
    contract tools plus `get_scorecard`; copy-paste config at `/mcp` in
    the frontend.

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

GridGreen is a carbon-aware copilot for ML engineers. It analyzes any ML training script, estimates its compute footprint using published scaling laws (Patterson et al. 2022, Kaplan et al. 2020, Strubell et al. 2019), pairs that with real-time and forecasted grid carbon intensity from the EIA, and tells the developer **when** to run and **what smaller model** to consider — before a single GPU-hour is burned. Built as a web-based copilot plus an MCP server so any AI agent (Claude Desktop, Cursor, Claude Code) gets the same intelligence for free.

**Important:** CO₂ and GPU-hours are **rules-based directional estimates** from static code analysis — not metered datacenter power or a full lifecycle assessment. For ground-truth, pair with runtime telemetry (CodeCarbon, RAPL, DCGM). The `carbon_saved_pct` in model-swap suggestions reflects the **parameter-ratio compute reduction** (1 − params_to/params_from), and `performance_retained_pct` references published benchmark comparisons where available.

**Pitch line:** *"Every `model.fit()` is a climate decision. GridGreen makes that decision visible — at the exact moment developers make it."*

---

## 3. Prize Targets

| Target | Prize | Why We Win |
|---|---|---|
| AI/ML Track (main) | Track prize | Custom estimator + forecaster + RAG + MCP agent |
| Cloud Track (main) | Track prize | Streaming pipeline + multi-service architecture |
| Best Use of NVIDIA Brev.dev | $500 | Real GPU workload for embeddings + training |
| Best Use of Databricks | $1000 | Delta Live Tables EIA pipeline (`backend/scripts/dlt_pipeline.py`) |
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

## 5. Evaluation Results

We maintain a self-evaluation harness (`evaluation/`) that runs 12 workloads
across 4 scenarios: S1 (baseline), S2 (model swap only), S3 (time shift only),
S4 (combined). Full methodology in `evaluation/README.md`; latest report in
`evaluation/runs/`.

| Metric | Value |
|---|---|
| Success rate | **100%** (12/12 workloads) |
| Mean analysis latency | **<20ms** (in-process benchmark) |
| Suggestion coverage | **66.7%** of workloads receive ≥1 swap |
| S2 model-swap reduction (LLMs) | **54.9%** estimated CO₂ |
| S2 model-swap reduction (Vision/Audio) | **57.1%** estimated CO₂ |
| S2 model-swap reduction (overall) | **37.0%** estimated CO₂ |
| Avg claimed compute reduction | **77.6%** (parameter-ratio proxy) |

**Honest caveats:**
- S3 time-shift numbers depend on the grid snapshot at benchmark time;
  negative values mean the forecast window was dirtier than "now" — expected
  and documented.
- Classical ML and unknown-model workloads correctly receive 0 suggestions
  (no corpus entry = no overclaim).
- Table 3 (accuracy vs ground-truth) is N/A — we have no metered runtime
  measurements. Populate `observed_co2_grams` via CodeCarbon to generate
  MAE / MAPE.

---

## 6. The API Contract (Source of Truth)

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
  "detected_patterns": [{ "line": 12, "pattern": "model.fit", "impact": "high" }],
  "workload_practices": [
    {
      "id": "autocast",
      "line": 4,
      "label": "torch.autocast",
      "impact": "high",
      "rationale": "…"
    }
  ],
  "methodology": {
    "approach": "rules-based-static-analysis",
    "gpu_assumed": "A100-80GB @ 400W TDP",
    "scaling_refs": [
      "Patterson et al., 2022. https://arxiv.org/abs/2104.10350",
      "Kaplan et al., 2020. https://arxiv.org/abs/2001.08361",
      "Strubell et al., 2019. https://arxiv.org/abs/1906.02243"
    ],
    "limitations": "No dataset-size awareness; batch-size heuristic; …"
  }
}
```

### POST /api/suggest_greener
```json
// Request — only `code` is required. Other fields (typically supplied
// by the UI right after `estimate_carbon` + `find_clean_window`) let the
// service rank high-impact lines first and surface grid context inside
// each suggestion's `reasoning`. Full schema in CONTRACT.md §POST /api/suggest_greener.
{
  "code": "string",
  "region": "CISO",
  "co2_grams_now": 1840,
  "co2_grams_optimal": 340,
  "current_gco2_kwh": 450,
  "optimal_window_start": "2026-04-20T03:00:00Z",
  "co2_savings_pct_window": 62,
  "impact_focus_lines": [12, 44]
}

// Response — carbon_saved_pct is the parameter-ratio compute reduction
// (1 − params_to/params_from), not a metered energy delta.
{
  "suggestions": [{
    "line": 5,
    "original_snippet": "AutoModel.from_pretrained('flan-t5-xxl')",
    "alternative_snippet": "AutoModel.from_pretrained('flan-t5-large')",
    "carbon_saved_pct": 85,
    "performance_retained_pct": 94,
    "citation": "Chung et al., 2022. https://arxiv.org/abs/2210.11416",
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

## 7. Work split

> **Status note:** the GridGreen codebase as committed was built end-to-end
> by a single contributor. §7 + §8 below — and `split.md` / `a.md` more
> broadly — are the **original two-person planning artifacts** kept in the
> repo for context (and because the API contract in §6 was locked against
> them). Do not read them as a description of who actually wrote which
> file; read them as the design bible the implementation aimed at.

**Authoritative roles and per-phase tasks:** **`split.md`**. **Person A execution + required ship + sponsors:** **`a.md`**.

The table below matches **`split.md`**. The **hour-by-hour in §8** was written for an older **A = all backend / B = all frontend** model — use §8 for **timing**, but **reassign line items** when they conflict with **`split.md`**.

| Person | Slice | FastAPI routes | UI |
|--------|--------|----------------|-----|
| **A** — Grid intelligence *("When should I run?")* | Forecast + carbon estimate from code | `estimate_carbon`, `check_grid`, `find_clean_window` | Monaco, inline decorations, pre-run modal + 48h chart *(agree modal shell vs chart with B)* |
| **B** — Model intelligence *("What should I run?")* | Greener models + session stats | `suggest_greener`, `scorecard` | Suggestion sidebar, stats card, `/mcp`, Gemini reasoning (incl. in modal per `split.md` Phase 5) |

**Stacks — A:** Python, FastAPI, Snowflake, Databricks, scikit-learn, XGBoost, Prophet, Hugging Face tooling as needed. **B:** TypeScript, Next.js, Tailwind, Monaco, Recharts, Framer Motion, Gemini SDK.

**Phase 5 note (`split.md`):** Person **A** owns **RAG index + `suggest_greener` wiring** (Cortex); Person **B** owns **Gemini NL**, **`/mcp` page**, and **MCP server wiring** in Claude Desktop — differs from some §8 bullets; **follow `split.md`**.

### Legacy reference — original “zero overlap” split

<details>
<summary>Older A = backend only / B = frontend only (click to expand)</summary>

**Person A — ML / Backend / Data:** EIA → Snowflake, DLT, Prophet/XGBoost forecaster, rules estimator, RAG + Cortex, Gemini API, all five FastAPI routes + MCP, Render, MCP config for Claude.

**Person B — Product / Frontend:** Next.js, Monaco, inline hints, pre-run modal + chart, RAG sidebar, stats card, `/mcp`, Vercel, Figma, video, Devpost.

Use this only if the team **explicitly reverts** to the old split; otherwise **`split.md`** wins.

</details>

---

## 8. Hour-by-Hour Schedule

> Saturday 9 AM start assumed. Adjust to actual kickoff.

**Ownership:** Checkboxes below follow the **original** split. Where they disagree with **`split.md`** (e.g. who builds Monaco, `suggest_greener`, MCP wiring), use **`split.md`** and **`a.md`**.

### 🟢 Phase 1: Setup (Hours 0–2) — 2h each

**Person A:**
- [ ] Submit team + track form (AI/ML + Cloud)
- [ ] Create GitHub repo: `gridgreen` with `backend/` + `frontend/`
- [ ] Register EIA API key (instant)
- [ ] **Request Brev.dev GPU NOW** (async, takes 1-3h)
- [ ] Create Snowflake + Databricks + Gemini + W&B accounts
- [ ] Write `CONTRACT.md` (paste from §6)

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
- [ ] **Record 3-min demo video** — see §10 (1.5h including retakes)
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

## 9. Per-Person Hour Summary

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

## 10. Demo Video Script (3 Minutes, Memorize)

**[0:00–0:15] Hook**
> "Every ML engineer types `model.fit(epochs=500)` without thinking. Depending on when and where that code runs, it could emit 200g of CO₂ or 2kg. Nobody sees that. We made it visible."

**[0:15–0:45] Product in action**
Paste training script → carbon annotations appear inline → hover for breakdown → click "Run Analysis."

**[0:45–1:30] The intelligence**
Modal: 48h grid forecast, "1.84kg estimated now vs 340g at 3am." RAG suggestion: "flan-t5-large cuts compute 85%, retains 94% benchmark perf. Chung et al. 2022." Show the `methodology` block — transparent provenance with three published scaling-law references.

**[1:30–2:00] Architecture (20s)**
Diagram flash. Call out Databricks streaming, Snowflake Cortex, NVIDIA GPU, Gemini, MCP.

**[2:00–2:30] MCP moment**
Claude Desktop with GridGreen tools loaded. Ask: "Should I train this now?" Claude answers with real data.

**[2:30–3:00] Close**
> "AI's carbon footprint grows 10x every two years. The infrastructure to make it climate-aware doesn't exist. We built it this weekend — with honest methodology, published citations, and transparent limitations. GridGreen — the missing layer between your code and the planet."

---

## 11. The "Stuck" Protocol

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

## 12. Scope Cuts (Baked In — Don't Relitigate)

| Cut | Replaced With | Saved |
|---|---|---|
| Neural-net carbon estimator | Rules-based w/ published scaling laws (Patterson, Kaplan, Strubell) | 8-10h |
| Fine-tuned Chronos | Prophet/XGBoost | 3-4h |
| Microservices | Single FastAPI | 3-5h |
| Separate dashboard page | Stats card inline | 3h |
| VS Code extension | Web + "/mcp" page | 8-10h |
| DigitalOcean | Render | 1h |

**Total saved: ~30h.** That's what makes 18h per person fit.

---

## 13. Communication Rules

- **3-hour sync rhythm:** 5-min standup every 3 hours
- **Notion board:** 3 columns (Doing/Blocked/Done), updated each sync
- **Git discipline:** Commit often; pull teammate's work after each commit
- **No heroics past hour 30:** Polish and fix only
- **Contract immutable after hour 4:** Changes require explicit sync

---

## 14. Success Definitions

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

## 15. Devpost Submission Checklist

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
- [ ] **EIA proof:** `storage.eia_hourly` in `/api/diagnostics` (or `sqlite3`
  per `HOW_TO_RUN.md`) after ingest — sponsor/judge “show the dataset” moment
- [ ] **`./scripts/verify_demo_readiness.sh` passes** (backend tests +
  frontend build + lint) before recording video
- [ ] Tech stack listed
- [ ] Team members added

---

## 16. The One Rule That Matters

**By hour 24 the demo path must work end-to-end, even if the intelligence behind it is imperfect.**

A beautiful demo with some hardcoded values beats a "real" system that doesn't render.

**Protect the demo path above all else.**

---

*Ship it.*
