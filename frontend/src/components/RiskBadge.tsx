import { RISK_BG, RISK_COLOR, RISK_ORDER, cn } from "@/lib/utils";

interface Props {
  riskLevel: string | null;
  riskScore?: number | null;
  size?: "sm" | "md";
  showLabel?: boolean;
  className?: string;
}

const SIZE = {
  sm: "text-2xs px-2 py-0.5",
  md: "text-xs px-2.5 py-1",
};

/** SEBI riskometer tier as a compact pill with a 6-step position dial. */
export default function RiskBadge({ riskLevel, riskScore, size = "sm", showLabel = true, className }: Props) {
  if (!riskLevel) return null;
  const idx = RISK_ORDER.indexOf(riskLevel as (typeof RISK_ORDER)[number]);

  return (
    <span
      title={riskScore != null ? `Risk score ${riskScore.toFixed(0)}/100` : undefined}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill font-medium whitespace-nowrap",
        RISK_BG[riskLevel],
        RISK_COLOR[riskLevel],
        SIZE[size],
        className
      )}
    >
      <span className="flex items-center gap-[2px]">
        {RISK_ORDER.map((_, i) => (
          <span
            key={i}
            className={cn("w-[3px] h-2.5 rounded-full", i <= idx ? "bg-current" : "bg-current/20")}
          />
        ))}
      </span>
      {showLabel && riskLevel}
    </span>
  );
}
