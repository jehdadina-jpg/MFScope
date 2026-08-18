import { useEffect, useState } from "react";
import { TrendingUp, Award, Sparkles, ChevronRight, Crown } from "lucide-react";
import { api, type FundCard } from "@/lib/api";
import { useNavigate } from "react-router-dom";
import { cn, fmtPct } from "@/lib/utils";
import ScoreBadge from "./ScoreBadge";
import RiskBadge from "./RiskBadge";
import LoadingSpinner from "./LoadingSpinner";

export default function TopFundsSection() {
  const [topFunds, setTopFunds] = useState<FundCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.funds
      .top(undefined, 10)
      .then((funds) => {
        const buyFunds = funds.filter(
          (f) => f.conviction === "Buy" || f.conviction === "Strong Buy"
        );
        setTopFunds(buyFunds.slice(0, 10));
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <section className="card-premium p-8">
        <LoadingSpinner label="Loading top funds..." />
      </section>
    );
  }

  if (error || topFunds.length === 0) {
    return null;
  }

  return (
    <section className="relative overflow-hidden rounded-2xl animate-fade-in">
      {/* Premium gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-accent/10 via-accent-bright/5 to-transparent" />
      <div className="absolute inset-0 bg-gradient-to-t from-background/95 via-background/60 to-transparent" />
      
      {/* Glow effects */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-accent/20 rounded-full blur-3xl opacity-20 animate-pulse-soft" />
      <div className="absolute bottom-0 left-0 w-96 h-96 bg-gradient-via/20 rounded-full blur-3xl opacity-20 animate-pulse-soft" style={{ animationDelay: "1s" }} />

      <div className="relative backdrop-blur-xl border border-border-accent/50 rounded-2xl p-8">
        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-start gap-4">
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-br from-accent to-accent-bright blur-xl opacity-50 animate-pulse-soft" />
              <div className="relative p-3 rounded-2xl bg-gradient-to-br from-accent/20 to-accent-bright/20 border border-accent/30">
                <Crown className="w-7 h-7 text-accent animate-float" />
              </div>
            </div>
            <div>
              <h2 className="text-2xl font-bold text-text-primary flex items-center gap-2 mb-1">
                Top 10 Funds to Buy
                <Sparkles className="w-5 h-5 text-accent animate-pulse-soft" />
              </h2>
              <p className="text-sm text-text-secondary">
                Premium selections with <span className="text-conviction-buy font-semibold">Buy</span> conviction
              </p>
            </div>
          </div>
          
          <button
            onClick={() => navigate("/?conviction=Buy")}
            className="group px-4 py-2 rounded-xl bg-accent/10 hover:bg-accent/20 border border-accent/30 
                       hover:border-accent/50 transition-all duration-300 flex items-center gap-2 hover:scale-105"
          >
            <span className="text-sm font-medium text-accent">View All</span>
            <ChevronRight className="w-4 h-4 text-accent group-hover:translate-x-1 transition-transform" />
          </button>
        </div>

        {/* Top 3 Spotlight */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {topFunds.slice(0, 3).map((fund, idx) => (
            <TopFundCard key={fund.scheme_code} fund={fund} rank={idx + 1} navigate={navigate} />
          ))}
        </div>

        {/* Remaining 7 funds */}
        <div className="space-y-2">
          {topFunds.slice(3).map((fund, idx) => (
            <CompactFundCard 
              key={fund.scheme_code} 
              fund={fund} 
              rank={idx + 4} 
              navigate={navigate} 
            />
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Top 3 Featured Cards ──────────────────────────────────────────────────────

function TopFundCard({ fund, rank, navigate }: { fund: FundCard; rank: number; navigate: any }) {
  const [isHovered, setIsHovered] = useState(false);
  
  const rankColors = {
    1: {
      bg: "from-yellow-500/20 to-orange-500/20",
      border: "border-yellow-500/50",
      icon: "text-yellow-400",
      glow: "shadow-glow-gold",
    },
    2: {
      bg: "from-gray-400/20 to-gray-500/20",
      border: "border-gray-400/50",
      icon: "text-gray-300",
      glow: "shadow-md",
    },
    3: {
      bg: "from-orange-600/20 to-orange-700/20",
      border: "border-orange-500/50",
      icon: "text-orange-400",
      glow: "shadow-md",
    },
  };

  const colors = rankColors[rank as keyof typeof rankColors];

  return (
    <article
      className={cn(
        "relative group cursor-pointer rounded-xl p-5 transition-all duration-300",
        "bg-gradient-to-br backdrop-blur-sm border",
        colors.bg,
        colors.border,
        isHovered && colors.glow,
        "hover:scale-105 hover:-translate-y-1"
      )}
      onClick={() => navigate(`/fund/${fund.scheme_code}`)}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Rank badge */}
      <div className={cn(
        "absolute -top-3 -right-3 w-10 h-10 rounded-full flex items-center justify-center",
        "font-bold text-lg border-2 backdrop-blur-sm",
        colors.border,
        colors.bg,
        colors.icon
      )}>
        {rank}
      </div>

      {/* Content */}
      <div className="space-y-3">
        <div>
          <p className="text-sm font-semibold text-text-primary leading-tight mb-1 line-clamp-2 group-hover:text-accent transition-colors">
            {fund.scheme_name}
          </p>
          <p className="text-xs text-text-secondary line-clamp-1">
            {fund.amc_name}
          </p>
        </div>

        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-2xs text-text-muted uppercase tracking-wide">Score</p>
            <p className={cn("text-lg font-bold font-mono", colors.icon)}>
              {fund.composite_score?.toFixed(1) ?? "—"}
            </p>
          </div>
          <div>
            <p className="text-2xs text-text-muted uppercase tracking-wide">1Y Return</p>
            <p className={cn(
              "text-lg font-bold font-mono",
              (fund.return_1y ?? 0) >= 15 ? "text-success" : "text-warning"
            )}>
              {fmtPct(fund.return_1y)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 pt-2 border-t border-border/50">
          <RiskBadge riskLevel={fund.risk_level} riskScore={fund.risk_score} size="sm" />
          <ScoreBadge conviction={fund.conviction} size="sm" animated />
        </div>
      </div>

      {/* Hover shine effect */}
      <div className="absolute inset-0 rounded-xl bg-gradient-shine opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
    </article>
  );
}

// ── Compact List Items ────────────────────────────────────────────────────────

function CompactFundCard({ fund, rank, navigate }: { fund: FundCard; rank: number; navigate: any }) {
  return (
    <article
      className={cn(
        "group flex items-center gap-4 p-4 rounded-xl cursor-pointer",
        "bg-background-subtle/40 backdrop-blur-sm border border-border/50",
        "hover:bg-background-muted/60 hover:border-accent/30 hover:shadow-lg",
        "transition-all duration-300 spotlight"
      )}
      onClick={() => navigate(`/fund/${fund.scheme_code}`)}
    >
      {/* Rank */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-background-elevated border border-border-accent 
                      flex items-center justify-center font-bold text-sm text-text-secondary group-hover:text-accent
                      transition-colors">
        {rank}
      </div>

      {/* Fund info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary truncate group-hover:text-accent transition-colors">
          {fund.scheme_name}
        </p>
        <p className="text-xs text-text-secondary truncate mt-0.5">
          {fund.amc_name}
        </p>
      </div>

      {/* Metrics */}
      <div className="hidden sm:flex items-center gap-6">
        <div className="text-right">
          <p className="text-2xs text-text-muted uppercase">Score</p>
          <p className="text-sm font-mono font-bold text-accent tabular-nums">
            {fund.composite_score?.toFixed(1) ?? "—"}
          </p>
        </div>
        <div className="text-right">
          <p className="text-2xs text-text-muted uppercase">1Y</p>
          <p className={cn(
            "text-sm font-mono font-bold tabular-nums",
            (fund.return_1y ?? 0) >= 15 ? "text-success" : 
            (fund.return_1y ?? 0) >= 8 ? "text-warning" : "text-text-secondary"
          )}>
            {fmtPct(fund.return_1y)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RiskBadge riskLevel={fund.risk_level} size="sm" showLabel={false} />
          <ScoreBadge conviction={fund.conviction} size="sm" />
        </div>
      </div>

      {/* Arrow */}
      <ChevronRight className="w-5 h-5 text-text-muted group-hover:text-accent group-hover:translate-x-1 transition-all flex-shrink-0" />
    </article>
  );
}
