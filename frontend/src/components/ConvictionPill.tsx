import { CONVICTION_BG, CONVICTION_COLOR, cn, fmtScore } from "@/lib/utils";

interface Props {
  conviction: string | null;
  score?: number | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE = {
  sm: "text-2xs px-2 py-0.5 gap-1",
  md: "text-xs px-2.5 py-1 gap-1.5",
  lg: "text-sm px-3 py-1.5 gap-2",
};

/** Compact conviction + score pill. One dot, one label — no gradients, no glow. */
export default function ConvictionPill({ conviction, score, size = "md", className }: Props) {
  if (!conviction) {
    return (
      <span className={cn("inline-flex items-center rounded-pill bg-surface-raised text-ink-faint border border-stroke", SIZE[size], className)}>
        Unscored
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-pill font-medium whitespace-nowrap",
        CONVICTION_BG[conviction],
        CONVICTION_COLOR[conviction],
        SIZE[size],
        className
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
      {conviction}
      {score != null && <span className="num opacity-70">{fmtScore(score)}</span>}
    </span>
  );
}
