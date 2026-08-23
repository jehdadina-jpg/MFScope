import type { PeerStat } from "@/lib/api";
import { cn } from "@/lib/utils";

const METRIC_LABELS: Record<string, string> = {
  return_1y: "1Y Return",
  return_3y: "3Y CAGR",
  return_5y: "5Y CAGR",
  sharpe_1y: "Sharpe",
  sortino_1y: "Sortino",
  alpha_1y: "Alpha",
  volatility_1y: "Volatility",
  max_drawdown_1y: "Max Drawdown",
  expense_ratio: "Expense Ratio",
  rolling_1y_std: "Return Dispersion",
};

const PCT_METRICS = new Set(["return_1y", "return_3y", "return_5y", "alpha_1y", "volatility_1y", "max_drawdown_1y", "expense_ratio", "rolling_1y_std"]);

function fmt(metric: string, value: number | null): string {
  if (value == null) return "—";
  if (PCT_METRICS.has(metric)) return `${value >= 0 && metric.startsWith("return") ? "+" : ""}${value.toFixed(2)}%`;
  return value.toFixed(2);
}

/** Where this fund sits against its peers — the numbers behind the score. */
export default function PeerStatsTable({ stats }: { stats: PeerStat[] }) {
  if (stats.length === 0) {
    return <p className="text-xs text-ink-faint">Not enough peers with data yet to compare.</p>;
  }

  return (
    <div className="flex flex-col divide-y divide-stroke">
      {stats.map((s) => (
        <div key={s.metric} className="py-2.5 flex items-center gap-3">
          <span className="text-xs text-ink-dim w-32 shrink-0">{METRIC_LABELS[s.metric] ?? s.metric}</span>
          <span className="num text-[13px] text-ink w-20 shrink-0">{fmt(s.metric, s.value)}</span>
          <div className="flex-1 relative h-1.5 rounded-full bg-surface-raised">
            {s.percentile != null && (
              <span
                className={cn(
                  "absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full border-2 border-canvas",
                  s.percentile >= 50 ? "bg-up" : "bg-down"
                )}
                style={{ left: `${s.percentile}%` }}
              />
            )}
          </div>
          <span className="num text-2xs text-ink-faint w-16 text-right shrink-0">
            {s.percentile != null ? `${s.percentile.toFixed(0)}th pctile` : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
