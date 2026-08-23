# MFScope — Indian Mutual Fund Intelligence Engine

Scrape → score → visualize. A research tool that ranks ~3,900 investable
Indian mutual funds against real peers, with every number traceable to the
math that produced it.

## What it does

- **Ingestion** — pulls AMFI's daily NAV file (which carries the fund's own
  SEBI category and AMC), plus years of per-scheme history from `mfapi.in`.
- **Universe hygiene** — filters ~37,000 raw scheme rows down to the ~3,900
  that are actually investable today: live, open-ended, Growth-option,
  enough history to measure. Matured FMPs, IDCW payout share classes, and
  dormant plans are excluded so they can't distort a peer ranking.
- **Analytics** — corporate-action-adjusted NAV series, CAGR vs. absolute
  returns depending on horizon, Sharpe/Sortino/alpha/beta/drawdown, rolling
  consistency, and a synthesized market benchmark from index-fund NAV.
- **Scoring** — a peer-percentile composite score (not a raw blend — see
  `backend/scoring/rule_based.py` for why), with missing inputs dropped and
  reported rather than imputed into a fake number.
- **Risk** — a transparent, calibrated mapping onto SEBI's six-tier
  riskometer (Low → Very High), not a black-box model trained on its own
  labels.
- **API** — FastAPI over the scored universe, with peer stats, benchmark
  comparison series, and full score/risk explainability on every fund.
- **Frontend** — React + TypeScript + Vite dashboard: browse, filter, sort,
  compare, and drill into exactly how a fund's score was built.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy (async), SQLite (WAL) |
| Analytics | pandas, numpy — pure functions, no ML in the risk/score path |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Recharts |
| Scheduling | APScheduler (optional; disabled by default, see below) |

## Project layout

```
backend/
  analytics/         # pure functions: NAV hygiene, metrics, taxonomy
  api/                # FastAPI app, routes, response schemas
  db/                 # SQLAlchemy models, session, schema reconciliation
  features/           # feature_builder.py — orchestrates analytics → DB
  ingestion/           # AMFI client, universe refresh, scheduler, news
  nlp/                 # sentiment pipeline (FinBERT / VADER)
  scoring/            # rule_based.py (composite score), risk_model.py
frontend/
  src/
    components/        # FundCard, FilterBar, ComparisonChart, breakdowns…
    pages/              # HomePage, FundDetailPage
    hooks/              # data-fetching hooks
    lib/                # typed API client, formatters
scripts/
  pipeline.py         # run the full nav → universe → features → scores pipeline
  backfill_history.py # pull years of NAV history for the investable universe
tests/                # pytest suite
alembic/              # Postgres migration path (SQLite dev DB uses db/migrate.py)
```

## Quick start

### Backend

```bash
# from the project root
pip install -e ".[dev]"
cp .env.example .env          # defaults work for local SQLite

# one-time: pull history and score the universe
python -m scripts.pipeline

# serve the API
uvicorn backend.api.main:app --reload --port 8000
```

The scheduler that re-runs the pipeline automatically is **off by default**
(a stray import used to start it on every `--reload` restart). Set
`MFSCOPE_ENABLE_SCHEDULER=1` to enable the nightly job, or re-run
`python -m scripts.pipeline` manually / via cron.

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

## Data pipeline stages

Run all of them, or one at a time with `python -m scripts.pipeline --stage <name>`:

1. **nav** — download `NAVAll.txt`, sync scheme master + today's NAV.
2. **universe** — reclassify schemes AMFI didn't classify, refresh NAV
   summaries, recompute the investable-universe flag.
3. **features** — rebuild the point-in-time metric vector for every
   investable scheme (returns, risk, momentum, sentiment).
4. **scores** — composite score + peer rank, then the riskometer.

`python -m scripts.backfill_history` pulls multi-year NAV history for
schemes that only have AMFI's daily print so far — needed once after a fresh
clone, since AMFI's file only carries the current day.

## Notes on accuracy

- Sub-1-year returns are absolute; 1-year-and-longer returns are CAGR.
  Mixing the two (annualizing a 1-month move) was the source of the
  multi-million-percent "returns" the old pipeline produced.
- The composite score is a **peer percentile**, disclosed alongside the peer
  group and count it was computed from. A fund is never scored against a
  peer group of fewer than a handful of comparable funds.
- Corporate actions (IDCW payouts, splits) are detected relative to a fund's
  own trailing volatility, not a single global threshold — a 20% single-day
  move in a silver fund is normal; the same move in a liquid fund is not.

## License

MIT — for personal/educational use. Verify data source ToS before commercial use.
