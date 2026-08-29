import type { RiskBreakdown } from "@/lib/api";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  volatility: "Volatility",
  drawdown: "Max Drawdown",
  beta: "Market Sensitivity (Beta)",
};

const INPUT_LABELS: Record<string, { label: string; format: (v: number) => string }> = {
  volatility_pct: { label: "Annualised volatility", format: (v) => `${v.toFixed(1)}%` },
  max_drawdown_pct: { label: "Worst drawdown", format: (v) => `${v.toFixed(1)}%` },
  beta: { label: "Beta vs. market", format: (v) => v.toFixed(2) },
};

/** Shows exactly how the realised-risk score was assembled — no black box. */
export default function RiskBreakdownCard({ breakdown }: { breakdown: RiskBreakdown }) {
  const entries = Object.entries(breakdown.components).filter(([, v]) => v != null) as [string, number][];

  return (
    <div className="flex flex-col gap-3">
      <p className="text-2xs text-ink-faint -mt-1">
        Computed from this fund's own trailing volatility, drawdown and beta — not the fund's
        official SEBI riskometer, which is based on portfolio holdings.
      </p>
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center gap-3">
          <span className="text-xs text-ink-dim w-40 shrink-0">{LABELS[key] ?? key}</span>
          <div className="flex-1 h-2 rounded-full bg-surface-raised overflow-hidden">
            <div className={cn("h-full rounded-full", riskColor(value))} style={{ width: `${Math.max(2, value)}%` }} />
          </div>
          <span className="num text-xs text-ink-dim w-9 text-right">{value.toFixed(0)}</span>
        </div>
      ))}

      <div className="flex flex-wrap gap-x-5 gap-y-1 pt-1 text-2xs text-ink-faint">
        {Object.entries(breakdown.inputs)
          .filter(([, v]) => v != null)
          .map(([key, value]) => {
            const meta = INPUT_LABELS[key];
            return (
              <span key={key}>
                {meta?.label ?? key}: <span className="num text-ink-dim">{meta ? meta.format(value as number) : value}</span>
              </span>
            );
          })}
      </div>
    </div>
  );
}

function riskColor(value: number): string {
  if (value >= 65) return "bg-risk-high";
  if (value >= 35) return "bg-risk-moderate";
  return "bg-risk-low";
}
