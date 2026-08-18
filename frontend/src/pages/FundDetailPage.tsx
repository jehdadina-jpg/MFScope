import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ExternalLink, TrendingUp, TrendingDown } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  AreaChart, Area, CartesianGrid,
} from "recharts";
import { format } from "date-fns";
import { useFundDetail } from "@/hooks/useFundDetail";
import ScoreBadge from "@/components/ScoreBadge";
import RiskBadge from "@/components/RiskBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { cn, fmtPct, fmtNav, fmtAum, returnColor } from "@/lib/utils";
import type { FundFeatures, FundScore } from "@/lib/api";

export default function FundDetailPage() {
  const { schemeCode } = useParams<{ schemeCode: string }>();
  const { data, loading, error } = useFundDetail(schemeCode);

  if (loading) return <LoadingSpinner label="Loading fund details…" />;
  if (error)   return <ErrorMessage message={error} className="mt-6" />;
  if (!data)   return null;

  const { scheme, latest_score, metadata, features, nav_history, score_history, recent_news } = data;

  return (
    <div className="flex flex-col gap-8 animate-fade-in pb-12">

      {/* ── Breadcrumb ─────────────────────────────────────────────────── */}
      <Link
        to="/"
        className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-accent transition-colors w-fit"
      >
        <ArrowLeft size={14} aria-hidden />
        All Funds
      </Link>

      {/* ── Hero header ────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-lg sm:text-xl font-semibold text-text-primary leading-snug">
            {scheme.scheme_name}
          </h1>
          <p className="text-sm text-text-secondary mt-1">{scheme.amc_name}</p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className="text-xs px-2 py-0.5 rounded bg-background-muted border border-border text-text-secondary">
              {scheme.category}
            </span>
            {scheme.plan_type && (
              <span className="text-xs px-2 py-0.5 rounded bg-background-muted border border-border text-text-secondary">
                {scheme.plan_type}
              </span>
            )}
            <span className="text-xs font-mono text-text-muted">
              #{scheme.scheme_code}
            </span>
          </div>
        </div>

        {latest_score && (
          <div className="flex flex-col gap-2 items-end">
            <ScoreBadge
              conviction={latest_score.conviction}
              score={latest_score.composite_score}
              size="lg"
              animated
            />
            {latest_score.risk_level && (
              <RiskBadge
                riskLevel={latest_score.risk_level}
                riskScore={latest_score.risk_score}
                size="md"
              />
            )}
          </div>
        )}
      </div>

      {/* ── Quick stats row ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="1Y Return"  value={fmtPct(features?.return_1y)}  valueClass={returnColor(features?.return_1y)} />
        <StatCard label="3Y Return"  value={fmtPct(features?.return_3y)}  valueClass={returnColor(features?.return_3y)} />
        <StatCard label="Sharpe"     value={features?.sharpe_1y?.toFixed(2) ?? "—"} valueClass="text-text-primary" />
        <StatCard label="AUM"        value={fmtAum(metadata?.aum_crore)}  valueClass="text-text-primary" />
        <StatCard label="Expense"    value={features?.expense_ratio ? `${features.expense_ratio.toFixed(2)}%` : "—"} valueClass="text-text-primary" />
        <StatCard label="Sortino"    value={features?.sortino_1y?.toFixed(2) ?? "—"} valueClass="text-text-primary" />
        <StatCard label="Max DD"     value={fmtPct(features?.max_drawdown_1y)} valueClass={returnColor(features?.max_drawdown_1y)} />
        <StatCard label="Volatility" value={features?.volatility_1y ? `${features.volatility_1y.toFixed(2)}%` : "—"} valueClass="text-text-primary" />
      </div>

      {/* ── NAV Chart ──────────────────────────────────────────────────── */}
      <Section title="NAV — 1 Year">
        <NavChart data={nav_history} />
      </Section>

      {/* ── Score breakdown ────────────────────────────────────────────── */}
      {latest_score && (
        <Section title="Score Breakdown">
          <ScoreBreakdown score={latest_score} />
        </Section>
      )}

      {/* ── Trailing returns ───────────────────────────────────────────── */}
      {features && (
        <Section title="Trailing Returns">
          <TrailingReturns features={features} />
        </Section>
      )}

      {/* ── Score history chart ────────────────────────────────────────── */}
      {score_history.length > 1 && (
        <Section title="Score History">
          <ScoreHistoryChart data={score_history} />
        </Section>
      )}

      {/* ── Fund manager / metadata ────────────────────────────────────── */}
      {metadata && (
        <Section title="Fund Details">
          <FundMeta meta={metadata} />
        </Section>
      )}

      {/* ── Recent news ────────────────────────────────────────────────── */}
      {recent_news.length > 0 && (
        <Section title="Recent News">
          <NewsList news={recent_news} />
        </Section>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <h2 className="section-label">{title}</h2>
      {children}
    </div>
  );
}

function StatCard({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass: string;
}) {
  return (
    <div className="card px-4 py-3 flex flex-col gap-1">
      <span className="section-label text-2xs">{label}</span>
      <span className={cn("text-base font-mono font-semibold tabular-nums", valueClass)}>
        {value}
      </span>
    </div>
  );
}

function NavChart({ data }: { data: Array<{ nav_date: string; nav: number }> }) {
  if (!data.length) return <p className="text-text-muted text-sm">No NAV data available.</p>;

  const first = data[0].nav;
  const last  = data[data.length - 1].nav;
  const color = last >= first ? "#10B981" : "#EF4444";

  return (
    <div className="card p-4" style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="navGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={color} stopOpacity={0.18} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1E2028" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="nav_date"
            tick={{ fill: "#555870", fontSize: 10 }}
            tickFormatter={(d: string) => format(new Date(d), "MMM yy")}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: "#555870", fontSize: 10 }}
            tickFormatter={(v: number) => `₹${v.toFixed(0)}`}
            tickLine={false}
            axisLine={false}
            width={52}
          />
          <Tooltip
            contentStyle={{
              background: "#111318",
              border: "1px solid #1E2028",
              borderRadius: "8px",
              fontSize: "12px",
              color: "#E8EAF0",
            }}
            formatter={(v: number) => [fmtNav(v), "NAV"]}
            labelFormatter={(l: string) => format(new Date(l), "dd MMM yyyy")}
          />
          <Area
            type="monotone"
            dataKey="nav"
            stroke={color}
            strokeWidth={1.5}
            fill="url(#navGrad)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

const COMPONENT_META: Array<{
  key: keyof FundScore;
  label: string;
  weight: number;
}> = [
  { key: "score_returns",     label: "Risk-adj. Returns", weight: 40 },
  { key: "score_consistency", label: "Consistency",       weight: 20 },
  { key: "score_cost",        label: "Cost Efficiency",   weight: 15 },
  { key: "score_sentiment",   label: "News Sentiment",    weight: 15 },
  { key: "score_stability",   label: "Stability",         weight: 10 },
];

function ScoreBreakdown({ score }: { score: FundScore }) {
  return (
    <div className="card p-5 flex flex-col gap-3">
      {/* Composite display */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-text-secondary">Composite Score</span>
        <span className="font-mono font-semibold text-lg text-text-primary tabular-nums">
          {score.composite_score.toFixed(1)}<span className="text-text-muted text-sm font-normal"> / 100</span>
        </span>
      </div>

      <div className="h-px bg-border" />

      {/* Component bars */}
      {COMPONENT_META.map(({ key, label, weight }) => {
        const val = score[key] as number | null | undefined;
        if (val == null) return null;
        const barColor =
          val >= 70 ? "#F59E0B" : val >= 45 ? "#6B7280" : "#EF4444";
        return (
          <div key={key} className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-secondary">
                {label}
                <span className="text-text-muted ml-1">({weight}%)</span>
              </span>
              <span className="text-xs font-mono tabular-nums" style={{ color: barColor }}>
                {val.toFixed(1)}
              </span>
            </div>
            <div className="h-1 bg-border rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${Math.min(100, val)}%`, background: barColor }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TrailingReturns({ features }: { features: FundFeatures }) {
  const periods: Array<{ label: string; value: number | null }> = [
    { label: "1M",  value: features.return_1m },
    { label: "3M",  value: features.return_3m },
    { label: "6M",  value: features.return_6m },
    { label: "1Y",  value: features.return_1y },
    { label: "3Y",  value: features.return_3y },
    { label: "5Y",  value: features.return_5y },
  ];

  return (
    <div className="card p-4 grid grid-cols-3 sm:grid-cols-6 divide-x divide-border">
      {periods.map(({ label, value }) => (
        <div key={label} className="flex flex-col items-center gap-1 px-3 py-2">
          <span className="section-label text-2xs">{label}</span>
          <span
            className={cn(
              "font-mono font-semibold tabular-nums text-sm",
              returnColor(value)
            )}
          >
            {fmtPct(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function ScoreHistoryChart({
  data,
}: {
  data: Array<{ score_date: string; composite_score: number; conviction: string }>;
}) {
  return (
    <div className="card p-4" style={{ height: 160 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1E2028" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="score_date"
            tick={{ fill: "#555870", fontSize: 10 }}
            tickFormatter={(d: string) => format(new Date(d), "MMM")}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: "#555870", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={28}
          />
          <Tooltip
            contentStyle={{
              background: "#111318",
              border: "1px solid #1E2028",
              borderRadius: "8px",
              fontSize: "12px",
              color: "#E8EAF0",
            }}
            formatter={(v: number, _: string, p: { payload: { conviction: string } }) => [
              `${v.toFixed(1)} — ${p.payload.conviction}`,
              "Score",
            ]}
            labelFormatter={(l: string) => format(new Date(l), "dd MMM yyyy")}
          />
          <Line
            type="monotone"
            dataKey="composite_score"
            stroke="#F59E0B"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function FundMeta({ meta }: { meta: import("@/lib/api").FundMeta }) {
  const rows: Array<{ label: string; value: string }> = [
    { label: "Fund Manager",    value: meta.fund_manager ?? "—" },
    { label: "Manager Tenure",  value: meta.manager_tenure_years ? `${meta.manager_tenure_years.toFixed(1)} yrs` : "—" },
    { label: "Expense Ratio",   value: meta.expense_ratio ? `${meta.expense_ratio.toFixed(2)}%` : "—" },
    { label: "AUM",             value: fmtAum(meta.aum_crore) },
    { label: "Portfolio Turnover", value: meta.portfolio_turnover ? `${meta.portfolio_turnover.toFixed(1)}%` : "—" },
    { label: "Benchmark",       value: meta.benchmark_index ?? "—" },
    { label: "Category Rank",   value: (meta.category_rank && meta.category_total) ? `${meta.category_rank} / ${meta.category_total}` : "—" },
    { label: "As of",           value: format(new Date(meta.as_of_date), "dd MMM yyyy") },
  ];

  return (
    <div className="card p-4 grid grid-cols-2 sm:grid-cols-4 gap-y-4 gap-x-6">
      {rows.map(({ label, value }) => (
        <div key={label} className="flex flex-col gap-0.5">
          <span className="section-label text-2xs">{label}</span>
          <span className="text-sm text-text-primary font-medium">{value}</span>
        </div>
      ))}
    </div>
  );
}

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "text-positive",
  negative: "text-negative",
  neutral:  "text-text-muted",
};

function NewsList({ news }: { news: import("@/lib/api").NewsSnippet[] }) {
  return (
    <div className="flex flex-col gap-2">
      {news.map((item, idx) => (
        <article
          key={idx}
          className="card px-4 py-3 flex items-start gap-3 hover:border-border-strong transition-colors"
        >
          {/* Sentiment indicator */}
          <div className="mt-0.5 shrink-0">
            {item.sentiment_label === "positive" && (
              <TrendingUp size={14} className="text-positive" aria-label="Positive" />
            )}
            {item.sentiment_label === "negative" && (
              <TrendingDown size={14} className="text-negative" aria-label="Negative" />
            )}
            {(!item.sentiment_label || item.sentiment_label === "neutral") && (
              <div className="w-3.5 h-3.5 rounded-full border border-border-strong" aria-label="Neutral" />
            )}
          </div>

          <div className="min-w-0 flex-1">
            <p className="text-sm text-text-primary leading-snug line-clamp-2">
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-accent transition-colors"
                >
                  {item.title}
                </a>
              ) : (
                item.title
              )}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-2xs text-text-muted capitalize">{item.source.replace("_", " ")}</span>
              {item.published_at && (
                <span className="text-2xs text-text-muted">
                  {format(new Date(item.published_at), "dd MMM, HH:mm")}
                </span>
              )}
              {item.compound_score != null && (
                <span
                  className={cn(
                    "text-2xs font-mono tabular-nums",
                    SENTIMENT_COLOR[item.sentiment_label ?? "neutral"]
                  )}
                >
                  {item.compound_score >= 0 ? "+" : ""}
                  {item.compound_score.toFixed(2)}
                </span>
              )}
              {item.url && (
                <ExternalLink size={10} className="text-text-muted" aria-hidden />
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
