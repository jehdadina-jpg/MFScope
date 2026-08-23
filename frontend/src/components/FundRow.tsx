import { useNavigate } from "react-router-dom";
import type { FundCard } from "@/lib/api";
import { cn, fmtPct, fmtAum, fmtRatio, returnColor } from "@/lib/utils";
import ConvictionPill from "./ConvictionPill";
import RiskBadge from "./RiskBadge";
import SparkLine from "./SparkLine";

/** Dense table row — the alternative to the card grid for scanning many funds. */
export default function FundRow({ fund }: { fund: FundCard }) {
  const navigate = useNavigate();
  return (
    <tr
      className="border-b border-stroke last:border-0 hover:bg-surface-raised cursor-pointer transition-colors duration-150"
      onClick={() => navigate(`/fund/${fund.scheme_code}`)}
    >
      <td className="py-2.5 pl-4 pr-3 max-w-[280px]">
        <div className="text-[13px] font-medium text-ink truncate">{fund.scheme_name}</div>
        <div className="text-2xs text-ink-faint truncate">{fund.amc_name} · {fund.category}</div>
      </td>
      <td className="py-2.5 px-3 hidden lg:table-cell">
        <SparkLine values={fund.nav_sparkline} width={72} height={24} />
      </td>
      <td className={cn("py-2.5 px-3 num text-[13px] text-right", returnColor(fund.return_1y))}>{fmtPct(fund.return_1y)}</td>
      <td className={cn("py-2.5 px-3 num text-[13px] text-right hidden sm:table-cell", returnColor(fund.return_3y))}>{fmtPct(fund.return_3y)}</td>
      <td className="py-2.5 px-3 num text-[13px] text-right hidden md:table-cell text-ink-dim">{fmtRatio(fund.sharpe_1y)}</td>
      <td className="py-2.5 px-3 num text-[13px] text-right hidden md:table-cell text-ink-dim">{fund.expense_ratio != null ? `${fund.expense_ratio.toFixed(2)}%` : "—"}</td>
      <td className="py-2.5 px-3 num text-[13px] text-right hidden lg:table-cell text-ink-dim">{fmtAum(fund.aum_crore)}</td>
      <td className="py-2.5 px-3 hidden sm:table-cell">
        <RiskBadge riskLevel={fund.risk_level} size="sm" showLabel={false} />
      </td>
      <td className="py-2.5 pl-3 pr-4">
        <ConvictionPill conviction={fund.conviction} score={fund.composite_score} size="sm" />
      </td>
    </tr>
  );
}
