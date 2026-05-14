# MAG10 Monitor Dashboard

Real-time trading signal dashboard powered by Plotly Dash and BigQuery.

## Quick Start (Local)

### 1. Set up environment

```bash
cd dashboard

# Create .env file with your config
cp .env.example .env

# Edit .env with your GCP project ID
export GCP_PROJECT_ID=data-engineering-hs
export BQ_DATASET=signals
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

**Alternatively, use UV (recommended):**
```bash
uv sync
uv run python app.py
```

### 3. Authenticate with GCP

**Option A: Local development (gcloud ADC)**
```bash
gcloud auth application-default login
```

This opens a browser to authenticate. Your credentials are saved locally and used by the BigQuery client.

**Option B: Service account JSON (for CI/CD)**
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### 4. Run the dashboard

```bash
python app.py
```

Open your browser: **http://localhost:8050**

---

## Dashboard Overview

### 5 Tabs

| Tab | What It Shows |
|-----|---------------|
| **Live Signals 🔴** | Real-time alerts from the last 10 minutes + confirmation rate |
| **Volume Analysis 📊** | Hourly signal distribution + signal strength by spike magnitude |
| **Momentum & Correlation 🔗** | Multi-signal confirmation (volume + momentum together) + top correlated pairs |
| **Volatility & Sector 📈** | Daily volatility z-score trend + hourly sector rotation |
| **Analytics 📉** | 30-day historical win rate of volume spike signals |

### Controls

- **Date Picker**: Choose which day to analyze (filters all tables by partition)
- **Symbol Filter**: Select which of the 10 stocks to monitor (default: all)
- **Refresh Interval**: Auto-poll BigQuery every 15s / 30s / 60s / 120s

### Auto-Refresh

The dashboard re-queries BigQuery automatically every N seconds (default: 30s). Watch the "Last updated" timestamp in the top-right.

---

## Data Source

All charts query the `signals` dataset in BigQuery (`data-engineering-hs` project):

| Table | Rows Per Day (Est.) |
|-------|---------------------|
| `volume_spikes` | 100-500 |
| `momentum_signals` | 50-200 |
| `volatility_spikes` | 50-300 |
| `sector_snapshots` | 240 (one per minute × 10 symbols) |

Queries use **partition pruning** (all `WHERE` clauses filter by date) to minimize BigQuery costs.

---

## Files

```
dashboard/
  app.py              Entry point (Dash init + gunicorn server)
  layout.py           Dash layout (tabs, filters, containers)
  callbacks.py        Chart generation (Plotly figures)
  queries.py          BigQuery queries (returns DataFrames)
  requirements.txt    Python dependencies
  .env.example        Environment variable template
  README.md           This file
```

---

## Troubleshooting

### `google.auth.exceptions.DefaultCredentialsError`

You haven't authenticated with GCP. Run:
```bash
gcloud auth application-default login
```

### `google.cloud.exceptions.NotFound: 404 Dataset ... not found`

Check:
- `GCP_PROJECT_ID` is correct in `.env`
- `BQ_DATASET` is correct (default: `signals`)
- Dataset exists in BigQuery

### Slow queries / timeout

- Reduce the refresh interval or increase `QUERY_TIMEOUT` in `queries.py`
- Check BigQuery for slow queries: Cloud Console → BigQuery → Query History
- Partition pruning must work: all queries should have `WHERE DATE(...) = ...`

### Charts are empty

- Check the browser's Network tab for query errors
- Date picker must match data in BigQuery (default: today)
- Try selecting more symbols or adjusting the date range

---

## Next Steps

Once you verify this runs locally:
1. Update `infra/main.tf` to add a `google_cloud_run_v2_service` resource
2. Create a Dockerfile (template provided in plan)
3. Push to Artifact Registry
4. Deploy to Cloud Run with `terraform apply`

---

## Architecture Diagram

```
Browser (localhost:8050)
    ↕ HTTP / WebSocket
Dash App (Flask + Plotly)
    ├── dcc.Interval (auto-refresh every N seconds)
    ├── dcc.DatePickerSingle, dcc.Dropdown (filters)
    └── 5 Tabs with Plotly figures
    ↕ BigQuery Client (google-cloud-bigquery)
BigQuery
    └── signals dataset (4 tables, 100K+ rows)
```

---

## Performance Notes

- **Latency**: Charts update 1-2 seconds after BigQuery query completes
- **Cost**: ~$0.01 per refresh (5 queries × 2KB each, scan ~100MB partitions)
- **Refresh interval**: 30s balances freshness with cost (costs ~$2.88/day at this rate)
- **Browser**: Works best on Chrome, Firefox; Safari may have rendering issues with complex Plotly

---

Generated for MAG10 Monitor project. Questions? Check the spec files in `spec/dashboard/`.
