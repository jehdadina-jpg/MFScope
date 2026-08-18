import { cn } from "@/lib/utils";

type Conviction =
  | "Strong Buy"
  | "Buy"
  | "Hold"
  | "Sell"
  | "Strong Sell"
  | string
  | null
  | undefined;

interface ScoreBadgeProps {
  conviction: Conviction;
  score?: number | null;
  /** "sm" = compact pill (card grid), "lg" = large display (detail view) */
  size?: "sm" | "lg";
  /** Animate with a soft pulse on strong conviction signals */
  animated?: boolean;
  className?: string;
}

const STYLES: Record<string, string> = {
  "Strong Buy":  "bg-conviction-strong-buy/15 text-conviction-strong-buy  border-conviction-strong-buy/40",
  "Buy":         "bg-conviction-buy/10        text-conviction-buy          border-conviction-buy/30",
  "Hold":        "bg-conviction-hold/10       text-conviction-hold         border-conviction-hold/30",
  "Sell":        "bg-conviction-sell/10       text-conviction-sell         border-conviction-sell/30",
  "Strong Sell": "bg-conviction-strong-sell/10 text-conviction-strong-sell border-conviction-strong-sell/30",
};

const GLOW: Record<string, string> = {
  "Strong Buy":  "shadow-glow",
  "Strong Sell": "shadow-[0_0_12px_2px_rgb(185_28_28/0.25)]",
};

export default function ScoreBadge({
  conviction,
  score,
  size = "sm",
  animated = false,
  className,
}: ScoreBadgeProps) {
  const key = conviction ?? "Hold";
  const styles = STYLES[key] ?? STYLES["Hold"];
  const glow   = GLOW[key] ?? "";
  const shouldPulse = animated && (key === "Strong Buy" || key === "Strong Sell");

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-badge border font-medium leading-none",
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm",
        styles,
        shouldPulse && "animate-pulse-soft",
        glow,
        className
      )}
      aria-label={`Conviction: ${key}${score != null ? `, score ${score.toFixed(1)}` : ""}`}
    >
      {size === "lg" && score != null && (
        <span className="font-mono tabular-nums text-base font-semibold">
          {score.toFixed(1)}
        </span>
      )}
      {key}
    </span>
  );
}
