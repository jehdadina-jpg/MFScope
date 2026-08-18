/**
 * MFScope API client
 * Thin typed wrappers around fetch — no external HTTP library needed for a
 * same-origin SPA proxied by Vite.
 */

const BASE = "/api/v1";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface NAVPoint {
  nav_date: string;
  nav: number;
}

export interface FundCard {
  id: number;
  scheme_code: string;
  scheme_name: string;
  amc_name: string;
  category: string;
  composite_score: number | null;
  conviction: string | null;
  return_1y: number | null;
  return_3y: number | null;
  expense_ratio: number | null;
  aum_crore: number | null;
  risk_score: number | null;
  risk_level: string | null;
  nav_sparkline: NAVPoint[];
}

export interface Page<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface FundScore {
  composite_score: number;
  conviction: string;
  model_version: string;
  score_date: string;
  score_returns: number | null;
  score_consistency: number | null;
  score_cost: number | null;
  score_sentiment: number | null;
  score_stability: number | null;
  shap_json: string | null;
  risk_score: number | null;
  risk_level: string | null;
  risk_shap_json: string | null;
}

export interface FundMeta {
  as_of_date: string;
  aum_crore: number | null;
  expense_ratio: number | null;
  fund_manager: string | null;
  manager_tenure_years: number | null;
  portfolio_turnover: number | null;
  category_rank: number | null;
  category_total: number | null;
  benchmark_index: string | null;
}

export interface FundFeatures {
  feature_date: string;
  return_1m: number | null;
  return_3m: number | null;
  return_6m: number | null;
  return_1y: number | null;
  return_3y: number | null;
  return_5y: number | null;
  volatility_1y: number | null;
  sharpe_1y: number | null;
  sortino_1y: number | null;
  alpha_1y: number | null;
  beta_1y: number | null;
  max_drawdown_1y: number | null;
  sentiment_7d: number | null;
  sentiment_30d: number | null;
  news_volume_7d: number | null;
}

export interface NewsSnippet {
  title: string;
  url: string | null;
  published_at: string | null;
  sentiment_label: string | null;
  compound_score: number | null;
  source: string;
}

export interface ScoreHistoryPoint {
  score_date: string;
  composite_score: number;
  conviction: string;
}

export interface SchemeDetail {
  id: number;
  scheme_code: string;
  scheme_name: string;
  amc_name: string;
  category: string;
  plan_type: string | null;
  option_type: string | null;
  is_active: boolean;
}

export interface FundDetail {
  scheme: SchemeDetail;
  latest_score: FundScore | null;
  metadata: FundMeta | null;
  features: FundFeatures | null;
  nav_history: NAVPoint[];
  score_history: ScoreHistoryPoint[];
  recent_news: NewsSnippet[];
}

export interface CategorySummary {
  category: string;
  fund_count: number;
  avg_score: number | null;
  top_fund_name: string | null;
  top_fund_score: number | null;
}

// ── API calls ─────────────────────────────────────────────────────────────────

export interface FundsQuery {
  category?: string;
  conviction?: string;
  search?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export const api = {
  funds: {
    list: (q: FundsQuery = {}): Promise<Page<FundCard>> => {
      const params = new URLSearchParams();
      if (q.category)   params.set("category",  q.category);
      if (q.conviction) params.set("conviction", q.conviction);
      if (q.search)     params.set("search",     q.search);
      if (q.sort_by)    params.set("sort_by",    q.sort_by);
      if (q.sort_dir)   params.set("sort_dir",   q.sort_dir);
      if (q.page)       params.set("page",       String(q.page));
      if (q.page_size)  params.set("page_size",  String(q.page_size));
      const qs = params.toString();
      return req<Page<FundCard>>(`/funds${qs ? `?${qs}` : ""}`);
    },

    detail: (schemeCode: string): Promise<FundDetail> =>
      req<FundDetail>(`/funds/${schemeCode}`),

    nav: (schemeCode: string, days = 365): Promise<NAVPoint[]> =>
      req<NAVPoint[]>(`/funds/${schemeCode}/nav?days=${days}`),

    top: (category?: string, limit = 10): Promise<FundCard[]> => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (category) params.set("category", category);
      return req<FundCard[]>(`/scores/top?${params}`);
    },
  },

  categories: {
    list: (): Promise<CategorySummary[]> => req<CategorySummary[]>("/categories"),
  },

  admin: {
    refresh: (): Promise<{ message: string }> =>
      req<{ message: string }>("/admin/refresh", { method: "POST" }),
  },
};
