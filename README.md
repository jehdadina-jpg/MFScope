# MFScope — India Mutual Fund Intelligence Engine

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
