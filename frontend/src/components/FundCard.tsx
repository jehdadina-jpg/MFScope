import { useNavigate } from "react-router-dom";
import { useRef, useState } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import type { FundCard as FundCardType } from "@/lib/api";
import { cn, fmtPct, fmtAum, fmtRatio, returnColor } from "@/lib/utils";
import ConvictionPill from "./ConvictionPill";
import RiskBadge from "./RiskBadge";
import SparkLine from "./SparkLine";

interface Props {
  fund: FundCardType;
  className?: string;
  style?: React.CSSProperties;
}

// A light spring: enough to feel alive, not enough to feel loose. Tuned to
// settle in well under 300ms so it never lags behind a fast mouse.
const TILT_SPRING = { stiffness: 340, damping: 28, mass: 0.4 };

export default function FundCard({ fund, className, style }: Props) {
  const navigate = useNavigate();
  const thin = (fund.peer_count ?? 0) < 8;
  const ref = useRef<HTMLElement>(null);
  const [hovered, setHovered] = useState(false);

  // Motion values update the DOM directly on rAF — no React re-render per
  // pixel of mouse movement, which is what keeps a grid of 24 of these smooth.
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const rotateX = useSpring(useTransform(py, [0, 1], [5, -5]), TILT_SPRING);
  const rotateY = useSpring(useTransform(px, [0, 1], [-5, 5]), TILT_SPRING);
  const spotlight = useTransform([px, py], ([x, y]: number[]) =>
    `radial-gradient(240px circle at ${x * 100}% ${y * 100}%, rgba(109,123,255,0.14), transparent 72%)`
  );

  function handleMouseMove(e: React.MouseEvent<HTMLElement>) {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    px.set((e.clientX - rect.left) / rect.width);
    py.set((e.clientY - rect.top) / rect.height);
  }

  function handleMouseLeave() {
    setHovered(false);
    px.set(0.5);
    py.set(0.5);
  }

  return (
    <motion.article
      ref={ref}
      className={cn(
        "interactive-card cursor-pointer p-4 flex flex-col gap-3 relative overflow-hidden [transform-style:preserve-3d]",
        className
      )}
      style={{ ...style, rotateX, rotateY, transformPerspective: 700 }}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={handleMouseLeave}
      onClick={() => navigate(`/fund/${fund.scheme_code}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && navigate(`/fund/${fund.scheme_code}`)}
      aria-label={`View details for ${fund.scheme_name}`}
    >
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 transition-opacity duration-300 z-0"
        style={{ opacity: hovered ? 1 : 0, background: spotlight }}
      />

      <div className="relative z-10 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-[13px] font-medium text-ink leading-snug line-clamp-2">{fund.scheme_name}</h3>
            <p className="text-2xs text-ink-faint mt-1 truncate">{fund.amc_name}</p>
          </div>
          <SparkLine values={fund.nav_sparkline} width={72} height={28} className="shrink-0 mt-0.5" animate />
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-2xs px-2 py-0.5 rounded-md bg-surface-raised text-ink-dim border border-stroke">
            {fund.category}
          </span>
          {fund.plan_type === "Direct" && (
            <span className="text-2xs px-2 py-0.5 rounded-md bg-brand-soft text-brand-bright">Direct</span>
          )}
        </div>

        <div className="grid grid-cols-3 gap-2 pt-1">
          <Metric label="1Y" value={fmtPct(fund.return_1y)} valueClass={returnColor(fund.return_1y)} />
          <Metric label="3Y CAGR" value={fmtPct(fund.return_3y)} valueClass={returnColor(fund.return_3y)} />
          <Metric label="Sharpe" value={fmtRatio(fund.sharpe_1y)} />
        </div>

        <div className="flex items-center justify-between gap-2 pt-2 border-t border-stroke">
          <div className="flex items-center gap-1.5">
            <ConvictionPill conviction={fund.conviction} score={fund.composite_score} size="sm" />
            {thin && (
              <span className="text-2xs text-ink-faint" title={`Ranked against only ${fund.peer_count} peers`}>
                thin peer set
              </span>
            )}
          </div>
          <RiskBadge riskLevel={fund.risk_level} riskScore={fund.risk_score} size="sm" showLabel={false} />
        </div>

        <div className="flex items-center justify-between text-2xs text-ink-faint">
          <span>Expense {fund.expense_ratio != null ? `${fund.expense_ratio.toFixed(2)}%` : "—"}</span>
          <span>AUM {fmtAum(fund.aum_crore)}</span>
        </div>
      </div>
    </motion.article>
  );
}

function Metric({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-2xs text-ink-faint">{label}</span>
      <span className={cn("num text-[13px] font-medium", valueClass ?? "text-ink")}>{value}</span>
    </div>
  );
}
