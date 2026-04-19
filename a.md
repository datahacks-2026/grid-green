# GridGreen — Person A playbook (revised split)

**Role:** Grid intelligence — *“When should I run?”*  
**Time budget:** ~18–19h build + ~1.5h buffer (per README).  
**Execution source of truth:** `split.md` (full-stack slice). Use `README.md` §5 for API shapes and §10–§15 for process, prizes, and contingencies.


---

## 0. Required only (submission + sponsors)

Everything else in this doc is **detail or stretch**. Do not miss §0.

### README §13 — minimum you must ship (team)

- Main page with **Monaco** editor  
- Paste code → **≥1 real** carbon-related annotation  
- **“Run analysis”** modal with **real 48h forecast**  
- **≥1** working **RAG** suggestion  
- **Public URLs** (frontend + backend)  
- **Devpost** submitted  
- **3‑minute demo video**

### Core stack required to deliver the minimum (per README plan)

- **Next.js** on **Vercel** (frontend)  
- **FastAPI** on **Render** (HTTP + MCP)  
- **EIA** as the primary approved **dataset** + ingest/store enough to drive a **real** forecast (Snowflake in plan; SQLite only as README contingency)  
- **Forecast** (e.g. **Prophet**) backing `check_grid` / `find_clean_window`  
- **RAG** path for at least one suggestion (**Snowflake Cortex** + small HF corpus in plan)  
- **Gemini API** for NL reasoning on suggestions (team)  
- **MCP** working in **Claude Desktop** for the demo story (README target)

### Hackathon dataset rule (verify wording with organizers)

- **≥1** dataset from the official **Scripps or non‑Scripps** list → **EIA** (non‑Scripps → Energy) satisfies the general software-project requirement.  
- **Scripps $1,500 challenge:** requires **≥1 Scripps** dataset (e.g. heat map) — **not** covered by EIA alone.

### Sponsor must-use (your school / hackathon list)

- **Brev.dev (NVIDIA)** — required touch for **NVIDIA** challenge (embeddings and/or reference GPU run + evidence).  
- **$200 AWS credits** — required touch for **AWS** challenge (pick **one** clear AWS component; set billing alarms).  
- **$5 Google Cloud credits (non‑.edu account)** — required touch for **GDG** challenge (minimal footprint; rules said do **not** use `.edu` for this).

### Explicitly not required for §13 minimum (still in target / prizes)

- **Databricks DLT**, **W&B**, **NOAA**, **heat map**, **EPA**, repo mode, model dropdown, SSE — **only if time** or a specific prize needs them.

---

## 1. What you’re shipping (your slice)

| Layer | You own |
|--------|--------|
| **API** | `POST /api/estimate_carbon`, `GET /api/check_grid`, `GET /api/find_clean_window` |
| **UI** | Monaco editor area, inline decorations, pre-run modal + 48h chart *(align modal shell vs chart with Person B — §4)* |
| **Data / ML** | EIA → Snowflake; Prophet/XGBoost-style **48h grid forecast**; **rules-based** carbon estimator (HF-style lookup + multipliers) |
| **Phase 5 (split.md)** | RAG index (HF pairs → embed on Brev → **Snowflake Cortex**); wire **`/api/suggest_greener`** (model extraction → similarity → alternatives); **Databricks DLT** for EIA stream; Brev reference workload + **W&B** screenshot |
| **Deploy / verify** | FastAPI on **Render**; **MCP** verified in **Claude Desktop** (coordinate with B on who wires server vs config page); technical **Devpost** section |

**Note:** `README.md` §6 still says “A = backend only.” **`split.md` moves Monaco + pre-run modal to you.** Follow **`split.md`** unless the team explicitly reverts.

---

## 2. API contract (do not drift silently)

- Lock request/response shapes to **`README.md` §5** (`estimate_carbon`, `suggest_greener`, `check_grid`, `find_clean_window`, `scorecard`).
- After the team’s “contract freeze,” changes only with **explicit sync** with Person B.
- Start with **hardcoded but valid JSON**; swap in real logic file-by-file.
- **Paths:** Implement under `/api/...` prefix consistently so Next.js and MCP map to the same handlers (adjust if repo uses a different convention, but document it once).

---

## 3. Phase-by-phase checklist

### Phase 1 — Setup (hours 0–2) — independent

- [ ] Repo `gridgreen/` with `backend/` + `frontend/`; share access with Person B.
- [ ] **EIA** API key (`eia.gov/opendata`).
- [ ] Request **Brev.dev** GPU immediately (async).
- [ ] **Snowflake** + **Databricks** accounts; credentials in `.env` (team convention).
- [ ] FastAPI scaffold: `main.py`, uvicorn `:8000`, **`GET /ping`** → `{"ok": true}`.
- [ ] Ensure **`CONTRACT.md`** (README §5) exists in repo (Person B may commit it — don’t block on ownership).

**Checkpoint:** Local backend runs; data cloud accounts exist; GPU request in flight.

---

### Phase 2 — Foundation (hours 2–8) — independent

**Backend**

- [ ] `POST /api/estimate_carbon` — stub, **contract-valid** JSON.
- [ ] `GET /api/check_grid` — stub.
- [ ] `GET /api/find_clean_window` — stub.
- [ ] Deploy to **Render**; share public base URL with B.

**Data**

- [ ] Pull ~**30 days** EIA hourly for **CISO, ERCO, PJM, MISO, NYIS**; load into **Snowflake** (script you can rerun).

**Frontend (your slice)**

- [ ] Main layout: **Monaco** + default sample ML script.
- [ ] **“Run analysis”** → `POST /api/estimate_carbon`; show response (JSON OK at first).
- [ ] Keep UI functional; B may own global **design system** in parallel.

**Checkpoint:** Three routes live on Render; EIA data in Snowflake; Monaco + one wired call demos your vertical slice.

---

### Phase 3 — Integration + real intelligence (hours 8–14) — first merge

- [ ] **Merge** with Person B; resolve layout (editor / sidebar / modal).
- [ ] Train / use **grid forecaster** (e.g. **Prophet**) on Snowflake data, **48h horizon**.
- [ ] Replace stubs: **`check_grid`** + **`find_clean_window`** use real forecasts + current-ish intensity.
- [ ] **Rules-based carbon estimator:** HF model hints + GPU multipliers; wire **`estimate_carbon`**.
- [ ] **Monaco inline decorations:** `model.fit`, `AutoModel`, `Trainer`, etc.; align with contract field **`detected_patterns`** (line, pattern, impact).

**Rule of thumb (README §15):** By end of Phase 3, *“paste code → see when to run”* should work end-to-end, even if imperfect.

**Checkpoint:** Real estimates + real clean-window logic + inline annotations.

---

### Phase 4 — Sleep (hours 14–22)

- [ ] Stagger sleep with B; if awake, **low-risk only** (copy, tiny CSS, docs). No risky integrations.

---

### Phase 5 — Intelligence layer (hours 22–28)

Per **`split.md`:**

- [ ] **RAG:** ~30 HF model-card pairs → **embed on Brev** → store **VECTOR** in **Snowflake Cortex**.
- [ ] **`POST /api/suggest_greener`:** extract model names from code → **Cortex similarity** → alternatives *(Person B adds **Gemini** NL on top)*.
- [ ] **Databricks DLT** pipeline for EIA stream (screenshot / story for judges).
- [ ] **Brev:** reference workload; **W&B** screenshot.

**Checkpoint:** Sponsor-visible path: Cortex + DLT + Brev; greener suggestions flow from your backend path.

---

### Phase 6 — Polish + demo (hours 28–32)

- [ ] **MCP:** end-to-end test in **Claude Desktop** (coordinate with B on server wiring vs `/mcp` config page).
- [ ] **W&B** logging/screenshot if not done.
- [ ] **Technical Devpost** description.
- [ ] Fix backend issues found in demo dry-runs.

---

### Phase 7 — Buffer + rehearsal (hours 32–36)

- [ ] Rehearse pitch with teammate.
- [ ] Live demo in **incognito**; backup video plays.
- [ ] **Critical bugs only** — strict **15 min** cap.

---

## 4. Coordination you must not skip

- **~Hour 8 / Phase 3:** One shared main page composition (Monaco, modal, sidebar).
- **Contract:** Stay on README §5 unless you **version** it together.
- **Modal ownership:** `split.md` Phase 2 puts **Monaco + Run analysis** on you; Phase 3 puts **pre-run modal + chart wiring** partly on B — **agree who owns modal shell vs chart** so nothing is dropped or duplicated.
- **MCP:** Agree who implements **MCP server exposure** vs **`/mcp` copy-paste page** vs **Claude testing** so nothing is orphaned.

---

## 5. Optional product ideas (stretch only)

- **Model dropdown + custom model + region:** Thin UI on the same estimator; optional API fields — sync with B if you extend the contract (see §8.6).
- **Repo / zip mode:** New behavior (scan + merge); **not** in core README path — see §8.5.

Do **not** let stretch work threaten README **§13 minimum** or **§15 demo path**.

---

## 6. If you fall behind (README §10)

Prefer **stub / mock** over blocking: local SQLite if Snowflake fails, CPU if Brev is late, hardcoded NL on B’s side if Gemini fails — **keep the demo path working**.

---

## 7. Success you’re aiming for

- **Minimum (README §13):** Monaco, real annotation(s), modal with real 48h forecast, ≥1 RAG suggestion working, public URLs, Devpost, video (team).
- **Target:** All five tools real; MCP live; Databricks + Cortex + Brev visible; prizes submitted.

---

## 8. Implementation details (full)

### 8.1 Product semantics (what the code must reflect)

- **Dev-time copilot:** Targets **ML engineers before/during training**, not live inference for end users of their product. GridGreen is **not** on the customer request path unless you explicitly integrate it later.
- **“When / where / what model”:** **When** = time window from forecast; **where** = **grid / balancing-authority region** (CISO, ERCO, …), **not** a full “pick AWS region + instance type” optimizer unless you add mapping docs.
- **Reducing impact:** (1) **Schedule** — same job, cleaner grid time → lower emissions per kWh (does not shorten GPU hours by itself). (2) **Smaller/cheaper models** — can reduce **compute** and often wall time. **Epochs/batch tuning** is stretch (README mentions batch RAG as stretch only).
- **Static vs dynamic:** Responses are **dynamic** per request, region, and time for grid endpoints; **rules + lookup tables** are **static until you ship new code**. Early stubs are **static JSON** until replaced.
- **Latency:** End users of **their** ML app: **unaffected** (GridGreen not in prod path). **Developer** waits **seconds to tens of seconds** for a full analysis if you chain Snowflake + RAG + Gemini — set **timeouts** and **loading UI**. Optional **defer training** hours are **product advice**, not UI lag.

### 8.2 Input limits (enforce in FastAPI + Monaco)

- **Max pasted code size:** e.g. **256KB–1MB** or **~2k–10k lines** — reject or truncate with a clear error (`413` / JSON error) and message: “Paste a training script, not a whole monorepo.”
- **Request timeout:** e.g. **30–60s** on Render for heavy paths; return partial/degraded response if you implement tiered calls.
- **Rate limit:** simple per-IP or per-session cap for demo stability.
- **Custom model / unknown HF id:** return **`confidence: "low"`** and a **default size bucket**; do not claim tight CO₂ without data.

### 8.3 EIA pipeline (primary data)

**What EIA is:** U.S. government **energy statistics** (electricity, fuels, prices, emissions-related series — **you choose which series** map to `current_gco2_kwh` / trend for the demo). Document the mapping in Devpost.

**Snowflake landing (suggested columns):**

- `ts_utc` (TIMESTAMP_NTZ or TZ-aware), `region_code` (TEXT), `series_id` or `metric` (TEXT), `value` (FLOAT), `ingested_at` (TIMESTAMP), optional `raw` (VARIANT) for debugging.

**Step-by-step ingest (initial):**

1. Register EIA API key; store in env `EIA_API_KEY`.
2. **Pick one metric story** (one paragraph) and the **EIA series IDs** that implement it — review EIA Open Data docs for the exact route (`/v2/...` etc.).
3. Pull **one region** (e.g. CISO) for **30 days** hourly; validate row count and gaps.
4. Generalize to **five regions:** CISO, ERCO, PJM, MISO, NYIS.
5. **Load** into Snowflake table (idempotent: delete+insert window or merge on `ts_utc`+`region_code`).
6. **Wire** `check_grid` from **latest** row (or latest complete hour); `find_clean_window` from **Prophet** (or XGBoost) fit on historical + **48h future** horizon, output aligned to contract `forecast_48h` shape.

**Forecasting:** Train **per region** or one model with region feature — keep first version **per region Prophet** for simplicity.

### 8.4 Optional datasets (NOAA + Scripps heat map)

| Source | Role | Implementation sketch |
|--------|------|-------------------------|
| **NOAA** (approved non-Scripps) | **Regional weather** → narrative / demand context (heat → **AC load** on grid). | Pick **one** NOAA product (e.g. station or grid point near demo region). Cache responses in Snowflake or Redis; optional `GET /api/context/weather?region=...` **or** optional fields inside `check_grid` response. **Do not** claim NOAA replaces EIA for carbon math. |
| **Scripps heat map** | **Hyperlocal** measured **T + RH** on UCSD campus; **Scripps prize** eligibility. | Ingest **small CSV slice** from hackathon assets; optional `GET /api/context/campus_heat` **or** extra fields on a “context” object in UI only. **Measured** trajectories, not a substitute for ISO carbon. |

**AC load (terminology):** **Air conditioning** = space cooling; high **T/RH** → more cooling **electricity demand** → often **higher grid stress**. Use as **explainability**, not as a second carbon oracle unless you model it honestly.

**Order:** **EIA first** → if Scripps prize: **heat map** → if time: **NOAA**. Devpost one-liner: *“Core scheduling uses **EIA**; optional layers add **local (Scripps heat map)** and/or **regional weather (NOAA)** for context.”*

### 8.5 Repo / multi-file mode (stretch — not default)

**Today:** one tool argument = **one `code` string** (README §5).

**Repo mode** = folder or repo → **aggregate** suggestions/estimates across files. **Not automatic** via Claude unless you orchestrate.

| Approach | Mechanism | Notes |
|----------|-----------|--------|
| **A — Client-side** | Claude reads files; calls `suggest_greener` / `estimate_carbon` **per file**; merges in chat. | No backend change; token/context limits. |
| **B — `repo_root` / paths (local MCP)** | MCP **stdio** process on user machine reads **allowlisted** directory under `REPO_ROOT`; walk `*.py` (optional `*.ipynb`); merge; add **`file`** to each suggestion. | **Remote Render** cannot read user `C:\...` without upload. |
| **C — Git clone / URL** | Backend clones to **temp dir**, scan, delete; **max bytes/files**; **public repos first**. | Needs git, cleanup, abuse controls. |
| **D — IDE** | Cursor/VS Code extension sends workspace — **most work**. | Post-hackathon. |

**Security:** Never `open()` arbitrary user paths on server. **Single approved root**, skip `.git`, `venv`, `node_modules`, cap **file count** and **total bytes**, **timeout** clone/walk.

**Contract:** Either **new** fields (`paths[]`, `repo_url`) or **repeat calls** + merge client-side — **sync with B** if you extend README §5.

### 8.6 Optional model dropdown + region (stretch)

- **UI:** Preset models from your **lookup table** + **Custom** (HF id string) + **region** (grid BA codes matching API).
- **Backend:** If `model_id` present, use table row for **FLOPs/kWh proxy**; else parse `code` as today. **Custom unknown** → `confidence: low`.
- **“Cloud region”:** If you add it, **document a simple mapping** (e.g. `us-east-1` → approximate BA) or keep **grid BA only** to avoid false precision.

### 8.7 Carbon estimator (rules-based)

- **Detect patterns:** regex/AST-lite for `model.fit`, `Trainer`, `from_pretrained`, etc. → `detected_patterns[]` with **line**, **pattern**, **impact**.
- **Lookup:** HF model name → **parameters class** / default GPU hours / kWh heuristic; apply **multipliers** (GPU type, epochs if parsed else default).
- **Combine with grid:** `co2_grams_now ≈ kwh * grid_intensity_now` (use consistent units g vs kg across contract — README uses mixed examples; **normalize once** with B).

### 8.8 RAG + Cortex + Brev (Phase 5)

- **Corpus:** ~30 curated HF model pairs (name, size, citation snippet).
- **Embed:** on **Brev** GPU; store **VECTOR** in **Snowflake Cortex**.
- **`suggest_greener`:** parse model strings from code → **similarity search** → return `suggestions[]` per contract; **dedupe** if same model appears twice.
- **Gemini:** **In-app** only — B calls Gemini API with **retrieved context**; not “Gemini Desktop plugin.” For **Gemini CLI + MCP**, separate optional story — see §8.9.

### 8.9 MCP + Claude Desktop

- **What it is:** **MCP server** exposes tools (`estimate_carbon`, `suggest_greener`, `check_grid`, `find_clean_window`, `get_scorecard`); **Claude Desktop** is the **MCP client**.
- **Not an app-store “plugin”:** User adds **JSON config** (command + args or URL per transport), **restarts** Claude — your **`/mcp` page** is **copy-paste** helper text.
- **Transports:** **stdio** (local subprocess — can read local disk for repo mode B), **SSE** / **streamable HTTP** (remote). **Render-hosted HTTP MCP** cannot read arbitrary local paths — use **A** or **B local** or **upload/zip** for server-side repo.
- **Tools must mirror** HTTP handlers or call same service layer to avoid drift.

### 8.10 Databricks DLT

- **Purpose:** **EIA streaming / incremental** ingestion + **features** for judges (“Cloud track”).
- **Minimum viable:** One pipeline that **appends** new hours; **screenshot** in Devpost if flaky; README allows **local Python fallback** + screenshot.

### 8.11 Deploy + env

- **Render:** `WEB_CONCURRENCY`, start command `uvicorn ... --host 0.0.0.0 --port $PORT`, env vars for Snowflake, EIA, Gemini (if server-side), CORS origin = Vercel URL.
- **Secrets:** never commit `.env`; document required keys in `README` or `.env.example` without values.

### 8.12 Hackathon dataset compliance (verify wording with organizers)

- **Software projects:** must use **≥1** dataset from the official **Scripps or non-Scripps** list (minimum **one**; more allowed).
- **$1,500 Scripps Challenge:** must use **≥1** dataset from the **Scripps** list (e.g. **heat map**) **in addition** if the rest is non-Scripps.
- **EIA** appears on the **non-Scripps → Energy** list — good **primary** for GridGreen.
- **Devpost:** bullet **each** dataset used with **name + link** + **how** it appears in the product (screenshot).

### 8.13 Current repo state

- `backend/` is implemented: FastAPI app with all five contract routes
  (`estimate_carbon`, `suggest_greener`, `check_grid`,
  `find_clean_window`, `scorecard`), the optional `/api/context/*`
  endpoints, repo-mode scanner, MCP server (`backend/mcp_server.py`),
  EIA → SQLite ingest with optional Snowflake mirror, and a 41-test
  pytest suite. `frontend/` runs end-to-end against it locally.
  Deployment to Render + Vercel is the remaining work.

### 8.14 Near–real-time vs “static dataset”

- **API-backed sources count** as using the dataset; you are **not** limited to a one-time CSV download.
- **Pattern:** cache upstream responses with a **TTL** (e.g. 5–15 min for grid-ish data); return **`last_updated`** in `check_grid` (README §5); UI shows **“as of …”**.
- **Heavier:** scheduled job (cron / DLT) every **15–60 min** → Snowflake → API reads **latest row** (fast, stable demo).
- **Stretch:** **SSE** from FastAPI for live chart updates; only if core path is done.
- **Honesty:** match refresh rate to **what EIA/upstream actually publishes**; do not imply sub-second grid truth.

### 8.15 Optional datasets to strengthen (beyond EIA + NOAA + heat map)

**On your hackathon non-Scripps list (use if time / story needs):**

| Source | Use |
|--------|-----|
| **US EPA** | Air quality / pollution **context** next to schedule (environment + health narrative). |
| **DNV Energy Transition Outlook 2025** | **Macro** charts (2024–2060) for pitch / one Devpost figure — not hourly scheduling. |
| **Solar Power Data (ZenPower)** | **Distributed solar** angle for time-of-day / regional story — simple heuristic only. |

**Scripps (extra beyond heat map):** Spray, CalCOFI, EasyOneArgo, CCE mooring — **climate/ocean context** for Devpost; keep **thin** (one viz + caption), not core grid math.

**Off-list (only if rules allow extra open data):** marginal CO₂ APIs (e.g. WattTime-style), ISO/RTO public feeds — **high credibility** for intensity; confirm eligibility before relying on them for judging.

---

## 9. Master checklist (single list)

Use this as a **printable** backlog; details live in §3 and §8.

### Accounts & keys

- [ ] EIA API key
- [ ] Snowflake + Databricks accounts; `.env` pattern with B
- [ ] Brev GPU requested early
- [ ] Gemini / W&B (as per team split — B may own Gemini keys for NL)
- [ ] Render + Vercel URLs documented

### Backend

- [ ] FastAPI: `/ping`, stubs for `estimate_carbon`, `check_grid`, `find_clean_window`
- [ ] Same business logic shared by **HTTP** and **MCP** tools
- [ ] Deploy Render; CORS for Vercel origin
- [ ] Replace stubs with EIA-backed grid + Prophet 48h
- [ ] Rules-based `estimate_carbon` + `detected_patterns`
- [ ] Phase 5: Cortex RAG + `suggest_greener` wiring; DLT screenshot path; Brev + W&B screenshot
- [ ] Input limits, timeouts, rate limits (§8.2)
- [ ] Optional: cache/TTL + `last_updated` for near–real-time (§8.14)

### Data

- [ ] EIA → Snowflake table (`ts_utc`, `region_code`, `metric`/`series_id`, `value`, `ingested_at`)
- [ ] Document **one** EIA series → intensity mapping for judges
- [ ] Optional: NOAA context endpoint or fields (§8.4)
- [ ] Optional: Scripps heat map CSV slice for Scripps prize (§8.4)
- [ ] Optional: EPA / DNV / ZenPower (§8.15)

### Frontend (Person A slice per split.md)

- [ ] Monaco + default script + Run analysis → `estimate_carbon`
- [ ] Inline decorations for high-impact patterns
- [ ] Pre-run modal + 48h chart — **split ownership with B** (§4)
- [ ] Loading / error states for API calls

### Integration & demo

- [ ] Merge with B by ~hour 8; one page layout
- [ ] `CONTRACT.md` / README §5 unchanged without sync
- [ ] MCP config snippet on `/mcp`; Claude Desktop end-to-end test
- [ ] Devpost: datasets section (name, link, how used, screenshots) — §8.12
- [ ] Technical Devpost + incognito rehearsal + backup video

### Stretch (only if ahead)

- [ ] Model dropdown + custom model + optional contract fields (§8.6)
- [ ] Repo / zip / local MCP scan (§8.5)
- [ ] SSE live updates

---

## 10. Closing rule

**Ship the demo path first** (README §15): paste → analyze → modal with real forecast → at least one real suggestion path → public URLs → Devpost. Everything else supports that.

*Ship it.*