import { Info } from "lucide-react";
import type { DataQuality } from "@/lib/api";

/**
 * Tells the user exactly what horizon the numbers on this page are trustworthy
 * for, instead of quietly showing a "1Y return" computed from eight months.
 */
export default function DataQualityNote({ quality }: { quality: DataQuality }) {
  if (quality.returns_valid && quality.risk_metrics_valid) return null;

  return (
    <div className="flex items-start gap-2 text-2xs text-warn bg-warn/10 border border-warn/20 rounded-lg px-3 py-2">
      <Info size={13} className="shrink-0 mt-0.5" />
      <span>
        Only {quality.history_years?.toFixed(1) ?? "a few"} years of NAV history available — 1-year risk metrics and
        returns needing a full year are shown as unavailable rather than estimated from a shorter window.
      </span>
    </div>
  );
}
