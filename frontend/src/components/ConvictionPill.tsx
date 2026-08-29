import { CONVICTION_BG, CONVICTION_COLOR, cn, fmtScore } from "@/lib/utils";

interface Props {
  conviction: string | null;
  score?: number | null;
  size?: "sm" | "md" | "lg";
  /** Adds a soft ambient glow for Strong Buy / Strong Sell. Reserve for the
   *  one or two hero placements per screen — a badge on every card in a grid
   *  of 24 would turn "emphasis" into "wallpaper". */
  emphasize?: boolean;
  className?: string;
}

const SIZE = {
  sm: "text-2xs px-2 py-0.5 gap-1",
  md: "text-xs px-2.5 py-1 gap-1.5",
  lg: "text-sm px-3 py-1.5 gap-2",
};

const GLOW: Record<string, string> = {
  "Strong Buy": "shadow-[0_0_0_1px_rgba(47,191,130,0.25),0_0_20px_-4px_rgba(47,191,130,0.55)]",
  "Strong Sell": "shadow-[0_0_0_1px_rgba(226,89,110,0.25),0_0_20px_-4px_rgba(226,89,110,0.55)]",
};

/** Conviction + score pill. A restrained dot and label everywhere, with an
 *  optional ambient glow on the two extreme verdicts when `emphasize` is set —
 *  the one place strong color earns its keep. */
export default function ConvictionPill({ conviction, score, size = "md", emphasize, className }: Props) {
  if (!conviction) {
    return (
      <span className={cn("inline-flex items-center rounded-pill bg-surface-raised text-ink-faint border border-stroke", SIZE[size], className)}>
        Unscored
      </span>
    );
  }

  const glow = emphasize ? GLOW[conviction] : undefined;

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-pill font-medium whitespace-nowrap transition-shadow duration-300",
        CONVICTION_BG[conviction],
        CONVICTION_COLOR[conviction],
        SIZE[size],
        glow,
        className
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full bg-current shrink-0", glow && "animate-pulse-glow")} />
      {conviction}
      {score != null && <span className="num opacity-70">{fmtScore(score)}</span>}
    </span>
  );
}
