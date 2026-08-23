/**
 * MFScope API client — thin typed fetch wrappers, same-origin via the Vite proxy.
 */

const BASE = "/api/v1";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ── Shared ──────────────────────────────────────────────────────────────────

export interface DataQuality {
  nav_days_available: number;
  history_years: number | null;
  first_nav_date: string | null;
  latest_nav_date: string | null;
  returns_valid: boolean;
  risk_metrics_valid: boolean;
  inception_date: string | null;
  nav_adjustments: number;
}

export interface NAVPoint {
  nav_date: string;
  nav: number;
}

export interface SeriesPoint {
  date: string;
  value: number;
}

export interface Page<T> {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: T[];
}

// ── Fund card ─────────────────────────────────────────────────────────────────

export interface FundCard {
  id: number;
  scheme_code: string;
  scheme_name: string;
  amc_name: string;
  category: string;
  asset_class: string | null;
  plan_type: string | null;

  composite_score: number | null;
  conviction: string | null;
  data_confidence: number | null;
  peer_rank: number | null;
  peer_count: number | null;

  risk_score: number | null;
  risk_level: string | null;

  return_1y: number | null;
  return_3y: number | null;
  return_5y: number | null;
  volatility_1y: number | null;
  sharpe_1y: number | null;
  max_drawdown_1y: number | null;
  expense_ratio: number | null;
  aum_crore: number | null;

  nav: number | null;
  nav_date: string | null;
  nav_sparkline: number[];
  data_quality: DataQuality | null;
}

// ── Fund detail ───────────────────────────────────────────────────────────────

export interface ComponentBreakdown {
  components: Record<string, number>;
  weights: Record<string, number>;
  nominal_weights: Record<string, number>;
  missing: string[];
  data_confidence: number | null;
  peer_group: string | null;
  peer_count: number | null;
  model_version: string | null;
}

export interface RiskBreakdown {
  model_version: string | null;
  components: Record<string, number | null>;
  weights: Record<string, number>;
  inputs: Record<string, number | null>;
  confidence: number | null;
}

export interface FundScore {
  score_date: string;
  composite_score: number;
  conviction: string;
  model_version: string;
  score_returns: number | null;
  score_consistency: number | null;
  score_momentum: number | null;
  score_cost: number | null;
  score_sentiment: number | null;
  score_stability: number | null;
  data_confidence: number | null;
  peer_group: string | null;
  peer_count: number | null;
  peer_rank: number | null;
  risk_score: number | null;
  risk_level: string | null;
  breakdown: ComponentBreakdown | null;
  risk_breakdown: RiskBreakdown | null;
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
  return_ytd: number | null;
  return_1y: number | null;
  return_2y: number | null;
  return_3y: number | null;
  return_5y: number | null;
  return_10y: number | null;
  return_since_inception: number | null;
  volatility_1y: number | null;
  volatility_3y: number | null;
  downside_deviation_1y: number | null;
  sharpe_1y: number | null;
  sortino_1y: number | null;
  calmar_1y: number | null;
  var_95_1y: number | null;
  alpha_1y: number | null;
  beta_1y: number | null;
  r_squared_1y: number | null;
  tracking_error_1y: number | null;
  information_ratio_1y: number | null;
  up_capture_1y: number | null;
  down_capture_1y: number | null;
  max_drawdown_1y: number | null;
  max_drawdown_3y: number | null;
  drawdown_recovery_days: number | null;
  rolling_1y_mean: number | null;
  rolling_1y_std: number | null;
  rolling_1y_best: number | null;
  rolling_1y_worst: number | null;
  rolling_1y_positive_pct: number | null;
  momentum_roc_1m: number | null;
  momentum_roc_3m: number | null;
  momentum_roc_6m: number | null;
  ma_50d: number | null;
  ma_200d: number | null;
  ma_crossover: number | null;
  expense_ratio: number | null;
  aum_crore: number | null;
  sentiment_7d: number | null;
  sentiment_30d: number | null;
  news_volume_7d: number | null;
  history_years: number | null;
  nav_days: number | null;
  data_quality: DataQuality | null;
}

export interface PeerStat {
  metric: string;
  value: number | null;
  peer_median: number | null;
  peer_best: number | null;
  peer_worst: number | null;
  percentile: number | null;
  higher_is_better: boolean;
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
  asset_class: string | null;
  plan_type: string | null;
  option_type: string | null;
  inception_date: string | null;
  is_active: boolean;
  is_investable: boolean | null;
  nav_latest: number | null;
  nav_latest_date: string | null;
}

export interface FundDetail {
  scheme: SchemeDetail;
  latest_score: FundScore | null;
  metadata: FundMeta | null;
  features: FundFeatures | null;
  nav_history: NAVPoint[];
  fund_series: SeriesPoint[];
  benchmark_series: SeriesPoint[];
  score_history: ScoreHistoryPoint[];
  peer_stats: PeerStat[];
  recent_news: NewsSnippet[];
  similar_funds: FundCard[];
}

// ── Aggregates ────────────────────────────────────────────────────────────────

export interface CategorySummary {
  category: string;
  asset_class: string | null;
  fund_count: number;
  avg_score: number | null;
  median_return_1y: number | null;
  avg_risk_score: number | null;
  top_fund_code: string | null;
  top_fund_name: string | null;
  top_fund_score: number | null;
}

export interface AMCSummary {
  amc_name: string;
  fund_count: number;
  avg_score: number | null;
  top_fund_name: string | null;
  top_fund_score: number | null;
}

export interface UniverseStats {
  total_schemes: number;
  investable_schemes: number;
  scored_schemes: number;
  nav_records: number;
  amc_count: number;
  category_count: number;
  latest_nav_date: string | null;
  latest_score_date: string | null;
  median_return_1y: number | null;
  conviction_breakdown: Record<string, number>;
  risk_breakdown: Record<string, number>;
  asset_class_breakdown: Record<string, number>;
  mean_data_confidence: number | null;
}

export interface FilterOptions {
  categories: CategorySummary[];
  asset_classes: string[];
  amcs: string[];
  convictions: string[];
  risk_levels: string[];
  plan_types: string[];
}

// ── Query shapes ──────────────────────────────────────────────────────────────

export interface FundsQuery {
  category?: string;
  asset_class?: string;
  amc?: string;
  conviction?: string;
  risk_level?: string;
  plan_type?: string;
  search?: string;
  min_score?: number;
  min_return_1y?: number;
  max_expense_ratio?: number;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
  with_sparkline?: boolean;
}

function toParams(q: object): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(q)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  return params;
}

export const api = {
  funds: {
    list: (q: FundsQuery = {}): Promise<Page<FundCard>> => {
      const qs = toParams(q).toString();
      return req<Page<FundCard>>(`/funds${qs ? `?${qs}` : ""}`);
    },
    detail: (schemeCode: string, days = 1095): Promise<FundDetail> =>
      req<FundDetail>(`/funds/${schemeCode}?days=${days}`),
    nav: (schemeCode: string, days = 365): Promise<NAVPoint[]> =>
      req<NAVPoint[]>(`/funds/${schemeCode}/nav?days=${days}`),
    compare: (codes: string[]): Promise<FundCard[]> =>
      req<FundCard[]>(`/funds/compare?codes=${codes.join(",")}`),
  },

  scores: {
    top: (params: { category?: string; asset_class?: string; conviction?: string; limit?: number } = {}): Promise<FundCard[]> => {
      const qs = toParams(params).toString();
      return req<FundCard[]>(`/scores/top${qs ? `?${qs}` : ""}`);
    },
  },

  categories: {
    list: (): Promise<CategorySummary[]> => req<CategorySummary[]>("/categories"),
  },

  amcs: {
    list: (limit = 60): Promise<AMCSummary[]> => req<AMCSummary[]>(`/amcs?limit=${limit}`),
  },

  meta: {
    stats: (): Promise<UniverseStats> => req<UniverseStats>("/stats"),
    filters: (): Promise<FilterOptions> => req<FilterOptions>("/filters"),
  },

  admin: {
    refresh: (): Promise<{ status: string }> => req<{ status: string }>("/admin/refresh", { method: "POST" }),
    refreshStatus: (): Promise<{ status: string; error: string | null }> =>
      req("/admin/refresh/status"),
  },
};
