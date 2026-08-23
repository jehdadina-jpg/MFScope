import { useParams, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useFundDetail } from "@/hooks/useFundDetail";
import ConvictionPill from "@/components/ConvictionPill";
import RiskBadge from "@/components/RiskBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import ComparisonChart from "@/components/ComparisonChart";
import ScoreBreakdown from "@/components/ScoreBreakdown";
import RiskBreakdownCard from "@/components/RiskBreakdownCard";
import PeerStatsTable from "@/components/PeerStatsTable";
import NewsList from "@/components/NewsList";
import DataQualityNote from "@/components/DataQualityNote";
import FundCard from "@/components/FundCard";
import { cn, fmtPct, fmtNav, fmtAum, fmtRatio, fmtDate, returnColor, ordinal } from "@/lib/utils";

export default function FundDetailPage() {
  const { schemeCode } = useParams<{ schemeCode: string }>();
  const { data, loading, error } = useFundDetail(schemeCode);

  if (loading) return <LoadingSpinner label="Loading fund details…" />;
  if (error) return <ErrorMessage message={error} className="mt-6" />;
  if (!data) return null;

  const { scheme, latest_score, features, fund_series, benchmark_series, peer_stats, recent_news, similar_funds } = data;

  return (
    <div className="flex flex-col gap-8 pb-16 animate-fade-in">
      <Link to="/" className="flex items-center gap-1.5 text-xs text-ink-faint hover:text-ink transition-colors w-fit">
        <ArrowLeft size={13} /> All funds
      </Link>

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-lg sm:text-xl font-semibold text-ink leading-snug">{scheme.scheme_name}</h1>
          <p className="text-sm text-ink-faint mt-1">{scheme.amc_name}</p>
          <div className="flex items-center gap-2 mt-2.5 flex-wrap">
            <Tag>{scheme.category}</Tag>
            {scheme.plan_type && <Tag>{scheme.plan_type}</Tag>}
            <span className="text-2xs font-mono text-ink-faint">#{scheme.scheme_code}</span>
          </div>
        </div>

        {latest_score && (
          <div className="flex flex-col gap-2 items-start sm:items-end shrink-0">
            <ConvictionPill conviction={latest_score.conviction} score={latest_score.composite_score} size="lg" />
            {latest_score.risk_level && (
              <RiskBadge riskLevel={latest_score.risk_level} riskScore={latest_score.risk_score} size="md" />
            )}
          </div>
        )}
      </div>

      {features?.data_quality && <DataQualityNote quality={features.data_quality} />}

      {/* ── Quick stats ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="NAV" value={fmtNav(scheme.nav_latest)} sub={fmtDate(scheme.nav_latest_date)} />
        <Stat label="1Y Return" value={fmtPct(features?.return_1y)} valueClass={returnColor(features?.return_1y)} />
        <Stat label="3Y CAGR" value={fmtPct(features?.return_3y)} valueClass={returnColor(features?.return_3y)} />
        <Stat label="Expense Ratio" value={features?.expense_ratio != null ? `${features.expense_ratio.toFixed(2)}%` : "—"} />
      </div>

      {/* ── Chart ──────────────────────────────────────────────────────── */}
      <section className="surface-card p-5">
        <h2 className="text-sm font-semibold text-ink mb-4">Performance vs. category peers</h2>
        <ComparisonChart fundSeries={fund_series} benchmarkSeries={benchmark_series} categoryLabel={scheme.category} />
      </section>

      {/* ── Score + Risk breakdown ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {latest_score?.breakdown && (
          <section className="surface-card p-5">
            <h2 className="text-sm font-semibold text-ink mb-4">How the score was built</h2>
            <ScoreBreakdown breakdown={latest_score.breakdown} />
          </section>
        )}
        {latest_score?.risk_breakdown && (
          <section className="surface-card p-5">
            <h2 className="text-sm font-semibold text-ink mb-4">Riskometer breakdown</h2>
            <RiskBreakdownCard breakdown={latest_score.risk_breakdown} />
          </section>
        )}
      </div>

      {/* ── Peer comparison ────────────────────────────────────────────── */}
      {peer_stats.length > 0 && (
        <section className="surface-card p-5">
          <div className="flex items-baseline justify-between mb-2">
            <h2 className="text-sm font-semibold text-ink">Fund vs. peer group</h2>
            {latest_score?.peer_rank && latest_score?.peer_count && (
              <span className="text-2xs text-ink-faint">
                Ranked <span className="num text-ink-dim">{ordinal(latest_score.peer_rank)}</span> of{" "}
                <span className="num text-ink-dim">{latest_score.peer_count}</span> in {latest_score.peer_group}
              </span>
            )}
          </div>
          <PeerStatsTable stats={peer_stats} />
        </section>
      )}

      {/* ── Full metrics table ─────────────────────────────────────────── */}
      {features && (
        <section className="surface-card p-5">
          <h2 className="text-sm font-semibold text-ink mb-4">All metrics</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-4 gap-y-3">
            <Metric label="1M" value={fmtPct(features.return_1m)} valueClass={returnColor(features.return_1m)} />
            <Metric label="3M" value={fmtPct(features.return_3m)} valueClass={returnColor(features.return_3m)} />
            <Metric label="6M" value={fmtPct(features.return_6m)} valueClass={returnColor(features.return_6m)} />
            <Metric label="YTD" value={fmtPct(features.return_ytd)} valueClass={returnColor(features.return_ytd)} />
            <Metric label="1Y" value={fmtPct(features.return_1y)} valueClass={returnColor(features.return_1y)} />
            <Metric label="3Y CAGR" value={fmtPct(features.return_3y)} valueClass={returnColor(features.return_3y)} />
            <Metric label="5Y CAGR" value={fmtPct(features.return_5y)} valueClass={returnColor(features.return_5y)} />
            <Metric label="Since inception" value={fmtPct(features.return_since_inception)} valueClass={returnColor(features.return_since_inception)} />
            <Metric label="Volatility (1Y)" value={features.volatility_1y != null ? `${features.volatility_1y.toFixed(1)}%` : "—"} />
            <Metric label="Sharpe" value={fmtRatio(features.sharpe_1y)} />
            <Metric label="Sortino" value={fmtRatio(features.sortino_1y)} />
            <Metric label="Calmar" value={fmtRatio(features.calmar_1y)} />
            <Metric label="Alpha (1Y)" value={fmtPct(features.alpha_1y)} valueClass={returnColor(features.alpha_1y)} />
            <Metric label="Beta" value={fmtRatio(features.beta_1y)} />
            <Metric label="R²" value={fmtRatio(features.r_squared_1y)} />
            <Metric label="Max Drawdown (1Y)" value={features.max_drawdown_1y != null ? `${features.max_drawdown_1y.toFixed(1)}%` : "—"} valueClass="text-down" />
            <Metric label="Max Drawdown (3Y)" value={features.max_drawdown_3y != null ? `${features.max_drawdown_3y.toFixed(1)}%` : "—"} valueClass="text-down" />
            <Metric label="Up Capture" value={features.up_capture_1y != null ? `${features.up_capture_1y.toFixed(0)}%` : "—"} />
            <Metric label="Down Capture" value={features.down_capture_1y != null ? `${features.down_capture_1y.toFixed(0)}%` : "—"} />
            <Metric label="Rolling 1Y Best" value={fmtPct(features.rolling_1y_best)} valueClass={returnColor(features.rolling_1y_best)} />
            <Metric label="Rolling 1Y Worst" value={fmtPct(features.rolling_1y_worst)} valueClass={returnColor(features.rolling_1y_worst)} />
            <Metric label="% Rolling Periods Positive" value={features.rolling_1y_positive_pct != null ? `${features.rolling_1y_positive_pct.toFixed(0)}%` : "—"} />
            <Metric label="AUM" value={fmtAum(features.aum_crore)} />
            <Metric label="History" value={features.history_years != null ? `${features.history_years.toFixed(1)}y` : "—"} />
          </div>
        </section>
      )}

      {/* ── News + Similar funds ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="surface-card p-5">
          <h2 className="text-sm font-semibold text-ink mb-3">Related news</h2>
          <NewsList items={recent_news} />
        </section>

        {similar_funds.length > 0 && (
          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-ink">Other funds in {scheme.category}</h2>
            <div className="grid grid-cols-1 gap-3">
              {similar_funds.map((f) => (
                <FundCard key={f.id} fund={f} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="text-2xs px-2 py-0.5 rounded-md bg-surface-raised text-ink-dim border border-stroke">{children}</span>;
}

function Stat({ label, value, sub, valueClass }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="surface-card p-4">
      <div className="text-2xs text-ink-faint mb-1">{label}</div>
      <div className={cn("num text-lg font-semibold", valueClass ?? "text-ink")}>{value}</div>
      {sub && <div className="text-2xs text-ink-faint mt-0.5">{sub}</div>}
    </div>
  );
}

function Metric({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-2xs text-ink-faint">{label}</span>
      <span className={cn("num text-sm font-medium", valueClass ?? "text-ink")}>{value}</span>
    </div>
  );
}
