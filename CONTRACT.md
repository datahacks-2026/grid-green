# GridGreen API Contract

> Locked source of truth. Mirrors `README.md` §5. Do not change shapes silently.
> Any change requires explicit sync between Person A and Person B.

All endpoints are mounted under `/api`.

---

## POST /api/estimate_carbon

### Request
```json
{
  "code": "string",
  "region": "CISO | ERCO | PJM | MISO | NYIS"
}
```

### Response
```json
{
  "co2_grams_now": 1840,
  "co2_grams_optimal": 340,
  "compute_hours": 2.5,
  "compute_device": "gpu | cpu | api",
  "gpu_hours": 2.5,
  "kwh_estimated": 1.8,
  "confidence": "low | medium | high",
  "detected_patterns": [
    { "line": 12, "pattern": "model.fit", "impact": "low | medium | high" }
  ],
  "workload_practices": [
    {
      "id": "autocast",
      "line": 4,
      "label": "torch.autocast",
      "impact": "low | medium | high",
      "rationale": "One-sentence why this practice matters for energy / throughput."
    }
  ]
}
```

`workload_practices` may be empty. Each entry is the **first** matching line in the
script for that practice id (deduped). These are **advisory** signals separate from
`detected_patterns` (model-load / trainer heuristics).

`gpu_hours` is retained for backward compatibility. Prefer `compute_hours` +
`compute_device` for display; classical ML estimates use CPU energy, and API-model
estimates use a prompt-volume proxy.

---

## POST /api/suggest_greener  (Person B owns)

### Request
```json
{
  "code": "string",
  "region": "CISO | ERCO | PJM | MISO | NYIS",
  "co2_grams_now": 1840,
  "co2_grams_optimal": 340,
  "current_gco2_kwh": 450,
  "optimal_window_start": "2026-04-20T03:00:00Z",
  "co2_savings_pct_window": 62,
  "impact_focus_lines": [12, 44]
}
```

All fields except **`code`** are optional. When supplied (typically from
`estimate_carbon`, `check_grid`, and `find_clean_window` after the user clicks
**Run analysis**), the service ranks high-impact lines first and appends
grid + script CO₂ context to each suggestion's `reasoning`.

### Response
```json
{
  "suggestions": [
    {
      "line": 5,
      "original_snippet": "AutoModel.from_pretrained('flan-t5-xxl')",
      "alternative_snippet": "AutoModel.from_pretrained('flan-t5-large')",
      "carbon_saved_pct": 85,
      "performance_retained_pct": 94,
      "citation": "Chung et al., 2022.",
      "reasoning": "flan-t5-large retains 94% of xxl's performance..."
    }
  ]
}
```

---

## GET /api/check_grid?region=CISO

### Response
```json
{
  "region": "CISO",
  "current_gco2_kwh": 450,
  "trend": "rising | falling | flat",
  "last_updated": "2026-04-18T12:00:00Z"
}
```

---

## GET /api/find_clean_window?hours_needed=4&max_delay_hours=48&region=CISO

### Response
```json
{
  "optimal_start": "2026-04-20T03:00:00Z",
  "expected_gco2_kwh": 180,
  "current_gco2_kwh": 450,
  "co2_savings_pct": 62,
  "forecast_48h": [
    { "hour": "2026-04-18T12:00:00Z", "gco2_kwh": 440 }
  ]
}
```

---

## GET /api/scorecard?session_id=abc  (Person B owns)

### Response
```json
{
  "co2_saved_grams": 1200,
  "runs_deferred": 3,
  "suggestions_accepted": 2
}
```

---

## POST /api/scorecard/event  (Person B owns)

### Request
```json
{
  "session_id": "abc",
  "event": "suggestion_accepted | run_deferred",
  "co2_saved_grams": 420
}
```

### Response
Same shape as `GET /api/scorecard`.

---

## POST /api/analyze_repo

Fetch a public GitHub repository zipball, scan `.py` / `.ipynb` files for model
loads, and return per-file greener suggestions plus aggregated code for
`estimate_carbon`.

### Request
```json
{
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",
  "region": "CISO",
  "top_k_per_file": 2,
  "max_files_with_hits": 25
}
```

`ref`, `region`, `top_k_per_file`, and `max_files_with_hits` are optional.

### Response
```json
{
  "repo_url": "https://github.com/owner/repo",
  "owner": "owner",
  "repo": "repo",
  "files_scanned": 42,
  "files_with_hits": 3,
  "total_suggestions": 5,
  "files": [
    {
      "path": "train.py",
      "suggestions": [
        {
          "line": 5,
          "original_snippet": "…",
          "alternative_snippet": "…",
          "carbon_saved_pct": 85,
          "performance_retained_pct": 94,
          "citation": "…",
          "reasoning": "…"
        }
      ]
    }
  ],
  "aggregated_code_for_estimate": "# --- repo:train.py ---\n…",
  "aggregate_file_count": 12,
  "aggregate_truncated": false
}
```

---

## GET /api/context/weather?region=CISO

Optional narrative context (not the primary carbon signal).

### Response
```json
{
  "region": "CISO",
  "location_label": "San Francisco, CA",
  "temperature_f": 62.0,
  "high_24h_f": 68.0,
  "short_forecast": "Partly cloudy",
  "fetched_at": "2026-04-18T12:00:00Z"
}
```

---

## GET /api/context/campus_heat

Summary of bundled UCSD mobile weather CSV (demo heatmap data).

### Response
```json
{
  "source": "scripps_ucsd_mobile_weather",
  "n_points": 1200,
  "n_stations": 4,
  "earliest": "2026-03-01T00:00:00Z",
  "latest": "2026-03-15T23:00:00Z",
  "mean_temperature_c": 18.2,
  "mean_relative_humidity": 72.5
}
```

---

## Conventions

- All timestamps are **ISO-8601 UTC** with trailing `Z`.
- All grid intensity values are **gCO₂/kWh**.
- All emission values are **grams CO₂** (not kilograms).
- `confidence` is a string enum: `low | medium | high`.
- `impact` is a string enum: `low | medium | high`.
- `region` codes are EIA balancing authority codes: `CISO | ERCO | PJM | MISO | NYIS`.
- Errors return HTTP status + `{"detail": "..."}`.
