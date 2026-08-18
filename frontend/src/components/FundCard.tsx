import { useNavigate } from "react-router-dom";
import { TrendingUp, TrendingDown, ArrowRight } from "lucide-react";
import type { FundCard as FundCardType } from "@/lib/api";
import { cn, fmtPct, fmtAum, returnColor } from "@/lib/utils";
import ScoreBadge from "./ScoreBadge";
import RiskBadge from "./RiskBadge";
import SparkLine from "./SparkLine";

interface FundCardProps {
  fund: FundCardType;
  className?: string;
}

export default function FundCard({ fund, className }: FundCardProps) {
  const navigate = useNavigate();

  return (
    <article
      className={cn(
        "group relative overflow-hidden rounded-xl cursor-pointer animate-fade-in",
        "bg-gradient-to-br from-background-subtle/80 to-background-muted/60",
        "backdrop-blur-md border border-border/50",
        "hover:border-accent/50 hover:shadow-xl",
        "transition-all duration-300 hover:scale-[1.02] hover:-translate-y-1",
        "spotlight",
        className
      )}
      onClick={() => navigate(`/fund/${fund.scheme_code}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && navigate(`/fund/${fund.scheme_code}`)}
      aria-label={`View details for ${fund.scheme_name}`}
    >
      {/* Gradient overlay on hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-accent/0 via-accent/0 to-accent/0 
                      group-hover:from-accent/5 group-hover:via-accent/3 group-hover:to-transparent 
                      transition-all duration-500 pointer-events-none" />
      
      {/* Content wrapper */}
      <div className="relative p-5 flex flex-col gap-4">
        
        {/* ── Header row ─────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-text-primary leading-snug mb-1.5 line-clamp-2 
                           group-hover:text-accent transition-colors duration-300">
              {fund.scheme_name}
            </h3>
            <p className="text-xs text-text-secondary line-clamp-1 group-hover:text-text-primary 
                          transition-colors duration-300">
              {fund.amc_name}
            </p>
          </div>
          
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <RiskBadge 
              riskLevel={fund.risk_level} 
              riskScore={fund.risk_score} 
              size="sm" 
              showLabel={false} 
            />
            <ScoreBadge conviction={fund.conviction} animated />
          </div>
        </div>

        {/* ── Category tag ───────────────────────────────────────────────── */}
        <span className="w-fit text-2xs px-2.5 py-1 rounded-lg font-medium
                         bg-background-elevated/50 text-text-secondary border border-border/50
                         backdrop-blur-sm group-hover:border-accent/30 group-hover:text-accent 
                         transition-all duration-300">
          {fund.category}
        </span>

        {/* ── Metrics grid ────────────────────────────────────────────────── */}
        <div className="grid grid-cols-3 gap-3">
          <Metric
            label="1Y"
            value={fmtPct(fund.return_1y)}
            valueClass={returnColor(fund.return_1y)}
            icon={getReturnIcon(fund.return_1y)}
          />
          <Metric
            label="3Y"
            value={fmtPct(fund.return_3y)}
            valueClass={returnColor(fund.return_3y)}
            icon={getReturnIcon(fund.return_3y)}
          />
          <Metric
            label="AUM"
            value={fmtAum(fund.aum_crore)}
            valueClass="text-text-primary"
          />
        </div>

        {/* ── Sparkline & Score ─────────────────────────────────────────── */}
        <div className="flex items-end justify-between gap-4 pt-3 border-t border-border/30">
          <div className="flex-1">
            {fund.nav_sparkline.length > 0 && (
              <SparkLine data={fund.nav_sparkline} width={120} />
            )}
          </div>
          
          {fund.composite_score != null && (
            <div className="flex items-center gap-2">
              <span className="text-2xs text-text-muted uppercase tracking-wider">Score</span>
              <span className="text-base font-bold font-mono text-accent">
                {fund.composite_score.toFixed(0)}
              </span>
            </div>
          )}
        </div>

        {/* ── Score bar ──────────────────────────────────────────────────── */}
        {fund.composite_score != null && (
          <ScoreBar score={fund.composite_score} conviction={fund.conviction} />
        )}

        {/* ── Hover arrow ────────────────────────────────────────────────── */}
        <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 
                        translate-x-2 group-hover:translate-x-0 transition-all duration-300">
          <div className="p-1.5 rounded-lg bg-accent/10 backdrop-blur-sm border border-accent/30">
            <ArrowRight className="w-4 h-4 text-accent" />
          </div>
        </div>
      </div>

      {/* Shine effect on hover */}
      <div className="absolute inset-0 bg-gradient-shine opacity-0 group-hover:opacity-100 
                      transition-opacity duration-500 pointer-events-none" />
    </article>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Metric({
  label,
  value,
  valueClass,
  icon,
}: {
  label: string;
  value: string;
  valueClass: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 p-2.5 rounded-lg bg-background-elevated/30 
                    border border-border/30 backdrop-blur-sm group-hover:border-border-accent/50
                    transition-all duration-300">
      <span className="text-2xs text-text-muted uppercase tracking-wider font-medium">
        {label}
      </span>
      <div className="flex items-center gap-1">
        {icon}
        <span className={cn("text-sm font-mono font-bold tabular-nums", valueClass)}>
          {value}
        </span>
      </div>
    </div>
  );
}

const BAR_COLORS: Record<string, string> = {
  "Strong Buy":  "from-conviction-strong-buy to-conviction-buy",
  "Buy":         "from-conviction-buy to-conviction-buy/80",
  "Hold":        "from-neutral/80 to-neutral/60",
  "Sell":        "from-conviction-sell/80 to-conviction-sell/60",
  "Strong Sell": "from-conviction-strong-sell to-conviction-sell",
};

function ScoreBar({
  score,
  conviction,
}: {
  score: number;
  conviction: string | null;
}) {
  const gradient = BAR_COLORS[conviction ?? "Hold"] ?? BAR_COLORS["Hold"];
  const width = Math.min(100, Math.max(0, score));
  
  return (
    <div className="relative h-1.5 w-full bg-border/30 rounded-full overflow-hidden">
      <div
        className={cn(
          "h-full rounded-full bg-gradient-to-r transition-all duration-700 ease-out",
          gradient,
          "shadow-sm"
        )}
        style={{ 
          width: `${width}%`,
          transition: "width 1s cubic-bezier(0.4, 0, 0.2, 1)"
        }}
        role="meter"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Score: ${score.toFixed(1)}`}
      />
      {/* Glow effect */}
      <div
        className={cn(
          "absolute top-0 left-0 h-full rounded-full bg-gradient-to-r blur-sm opacity-50",
          gradient
        )}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

// ── Helper functions ──────────────────────────────────────────────────────────

function getReturnIcon(returnValue: number | null) {
  if (returnValue === null) return null;
  if (returnValue >= 0) {
    return <TrendingUp className="w-3 h-3 text-success" />;
  }
  return <TrendingDown className="w-3 h-3 text-danger" />;
}
