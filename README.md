# MFScope — India Mutual Fund Intelligence Engine

> Scrape · Score · Visualise — a full-stack research tool for Indian mutual funds.

---

## What it does

- **Data Pipeline** — pulls daily NAV from AMFI, secondary metadata from aggregators, and financial news via RSS
- **ML Scoring Engine** — engineers 30+ features (returns, risk-adjusted metrics, sentiment, fundamentals) and produces a 5-tier conviction label per fund: `Strong Buy → Buy → Hold → Sell → Strong Sell`
- **Dark-Mode Dashboard** — React + TypeScript minimal fintech UI; browse by category, drill into a fund, see the score + why

---

## Stack

| Layer | Choice |
|---|---|
| Backend language | Python 3.11+ |
| Scraping | httpx, BeautifulSoup4, Playwright, feedparser |
| Database | PostgreSQL (SQLite for MVP) via SQLAlchemy async |
| ML | XGBoost / LightGBM + SHAP |
| NLP | FinBERT (ProsusAI/finbert) or VADER |
| API | FastAPI + Uvicorn |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| Charts | Recharts |
| Deployment | Backend → Railway/Render · Frontend → Vercel · DB → Supabase/Neon |

---

## Quick Start

### Backend

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Install Playwright browsers (only needed if using JS scraping)
playwright install chromium

# 4. Configure environment
cp .env.example .env
# edit .env with your DATABASE_URL etc.

# 5. Run DB migrations
alembic upgrade head

# 6. Start the API server
uvicorn backend.api.main:app --reload --port 8000

# 7. (Optional) Run the scheduler as a standalone process
python -m backend.ingestion.scheduler
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # starts Vite dev server at http://localhost:5173
```

---

## Project Structure

```
mfscope/
├── backend/
│   ├── ingestion/
│   │   ├── amfi_client.py       # AMFI NAV + scheme master
│   │   ├── news_scraper.py      # RSS news ingestion
│   │   └── scheduler.py        # APScheduler jobs
│   ├── nlp/
│   │   └── sentiment.py        # FinBERT / VADER sentiment
│   ├── features/
│   │   └── feature_builder.py  # 30+ engineered features
│   ├── scoring/
│   │   ├── rule_based.py       # Weighted composite scorer (v1)
│   │   └── ml_model.py         # XGBoost learned model (v2)
│   ├── api/
│   │   └── main.py             # FastAPI routes
│   └── db/
│       └── models.py           # SQLAlchemy ORM models
├── frontend/
│   └── src/
│       ├── components/         # ScoreBadge, FundCard, SparkLine, CategoryFilter
│       ├── pages/              # Home, FundDetail
│       └── lib/                # API client, hooks
├── notebooks/
│   └── model_exploration.ipynb
├── tests/
├── alembic/
├── models/                     # Saved ML model artifacts (.gitkeep)
├── pyproject.toml
└── .env.example
```

---

## Data Sources

| Source | What we use | Notes |
|---|---|---|
| AMFI (`amfiindia.com`) | Daily NAV, scheme master | Primary, ToS-safe, always free |
| mfapi.in | Historical NAV per scheme | Free community API |
| Moneycontrol | AUM, expense ratio, fund manager | Scrape carefully, respect robots.txt |
| Value Research Online | Category rank, portfolio composition | Factual data only |
| ET Markets / LiveMint / BS | News headlines + summaries | RSS feeds only |

---

## Scoring Model (v1 — Rule-Based)

Each fund scored 0–100 within its category peer group:

| Component | Weight | Features |
|---|---|---|
| Risk-adjusted returns | 40% | Sharpe, Sortino, alpha |
| Consistency | 20% | Rolling return std dev, max drawdown |
| Cost efficiency | 15% | Expense ratio (inverted) |
| News sentiment | 15% | FinBERT 7-day + 30-day rolling |
| Stability | 10% | AUM trend, manager tenure |

Score → Label mapping: 80–100 Strong Buy · 60–79 Buy · 40–59 Hold · 20–39 Sell · 0–19 Strong Sell

---

## License

MIT — for personal/educational use. Always check data source ToS before any commercial use.
