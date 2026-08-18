import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes safely — shadcn/ui convention. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a number as a percentage string with sign. */
export function fmtPct(val: number | null | undefined, decimals = 2): string {
  if (val == null) return "—";
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(decimals)}%`;
}

/** Format NAV / price with 4 decimal places. */
export function fmtNav(val: number | null | undefined): string {
  if (val == null) return "—";
  return `₹${val.toFixed(4)}`;
}

/** Format AUM in crores with abbreviation. */
export function fmtAum(crore: number | null | undefined): string {
  if (crore == null) return "—";
  if (crore >= 10_000) return `₹${(crore / 10_000).toFixed(2)}L Cr`;
  if (crore >= 1_000)  return `₹${(crore / 1_000).toFixed(2)}K Cr`;
  return `₹${crore.toFixed(0)} Cr`;
}

/** Format a score 0–100 to one decimal. */
export function fmtScore(score: number | null | undefined): string {
  if (score == null) return "—";
  return score.toFixed(1);
}

/** Return Tailwind text colour class for a return value. */
export function returnColor(val: number | null | undefined): string {
  if (val == null) return "text-text-muted";
  return val >= 0 ? "text-positive" : "text-negative";
}

/** Conviction → display label. */
export const CONVICTION_LABELS: Record<string, string> = {
  "Strong Buy":  "Strong Buy",
  "Buy":         "Buy",
  "Hold":        "Hold",
  "Sell":        "Sell",
  "Strong Sell": "Strong Sell",
};
