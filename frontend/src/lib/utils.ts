import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes safely. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Percentage with sign, "—" for missing. */
export function fmtPct(val: number | null | undefined, decimals = 1): string {
  if (val == null || !Number.isFinite(val)) return "—";
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(decimals)}%`;
}

/** Plain percentage, no sign — for ratios like allocation or percentile. */
export function fmtPctPlain(val: number | null | undefined, decimals = 0): string {
  if (val == null || !Number.isFinite(val)) return "—";
  return `${val.toFixed(decimals)}%`;
}

export function fmtNav(val: number | null | undefined): string {
  if (val == null) return "—";
  return `₹${val.toFixed(4)}`;
}

export function fmtAum(crore: number | null | undefined): string {
  if (crore == null) return "—";
  if (crore >= 1_00_000) return `₹${(crore / 1_00_000).toFixed(2)} L Cr`;
  if (crore >= 1_000) return `₹${(crore / 1_000).toFixed(2)}K Cr`;
  return `₹${crore.toFixed(0)} Cr`;
}

export function fmtCompact(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function fmtNumber(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-IN").format(n);
}

export function fmtScore(score: number | null | undefined): string {
  if (score == null) return "—";
  return score.toFixed(1);
}

export function fmtRatio(val: number | null | undefined, decimals = 2): string {
  if (val == null || !Number.isFinite(val)) return "—";
  return val.toFixed(decimals);
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return "—";
  const diffMs = Date.now() - d;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return fmtDateShort(iso);
}

export function returnColor(val: number | null | undefined): string {
  if (val == null) return "text-ink-faint";
  return val >= 0 ? "text-up" : "text-down";
}

export const CONVICTION_ORDER = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"] as const;

export const CONVICTION_COLOR: Record<string, string> = {
  "Strong Buy": "text-conviction-strong-buy",
  Buy: "text-conviction-buy",
  Hold: "text-conviction-hold",
  Sell: "text-conviction-sell",
  "Strong Sell": "text-conviction-strong-sell",
};

export const CONVICTION_BG: Record<string, string> = {
  "Strong Buy": "bg-conviction-strong-buy-soft",
  Buy: "bg-conviction-buy-soft",
  Hold: "bg-conviction-hold-soft",
  Sell: "bg-conviction-sell-soft",
  "Strong Sell": "bg-conviction-strong-sell-soft",
};

export const RISK_ORDER = [
  "Low",
  "Low to Moderate",
  "Moderate",
  "Moderately High",
  "High",
  "Very High",
] as const;

export const RISK_COLOR: Record<string, string> = {
  Low: "text-risk-low",
  "Low to Moderate": "text-risk-low-moderate",
  Moderate: "text-risk-moderate",
  "Moderately High": "text-risk-moderately-high",
  High: "text-risk-high",
  "Very High": "text-risk-very-high",
};

export const RISK_BG: Record<string, string> = {
  Low: "bg-risk-low-soft",
  "Low to Moderate": "bg-risk-low-moderate-soft",
  Moderate: "bg-risk-moderate-soft",
  "Moderately High": "bg-risk-moderately-high-soft",
  High: "bg-risk-high-soft",
  "Very High": "bg-risk-very-high-soft",
};

/** Component key -> human label, shared between score breakdown UI. */
export const COMPONENT_LABELS: Record<string, string> = {
  returns: "Risk-Adj. Returns",
  consistency: "Consistency",
  momentum: "Momentum",
  cost: "Cost Efficiency",
  sentiment: "News Sentiment",
  stability: "Stability",
};

export function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}

export function debounce<Args extends unknown[]>(
  fn: (...args: Args) => void,
  ms: number
): (...args: Args) => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return (...args: Args) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
