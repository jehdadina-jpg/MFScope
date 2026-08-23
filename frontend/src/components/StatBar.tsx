import type { UniverseStats } from "@/lib/api";
import { fmtCompact, fmtDateShort, fmtPct, returnColor } from "@/lib/utils";

export default function StatBar({ stats }: { stats: UniverseStats | null }) {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="surface-card p-4">
            <div className="skeleton h-3 w-16 mb-2" />
            <div className="skeleton h-6 w-20" />
          </div>
        ))}
      </div>
    );
  }

  const items = [
    { label: "Funds scored", value: stats.investable_schemes.toLocaleString("en-IN") },
    { label: "Fund houses", value: String(stats.amc_count) },
    {
      label: "Median 1Y return",
      value: fmtPct(stats.median_return_1y),
      valueClass: returnColor(stats.median_return_1y),
    },
    { label: "NAV records", value: fmtCompact(stats.nav_records) },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {items.map((item) => (
        <div key={item.label} className="surface-card p-4">
          <div className="text-2xs text-ink-faint mb-1">{item.label}</div>
          <div className={`num text-xl font-semibold ${item.valueClass ?? "text-ink"}`}>{item.value}</div>
        </div>
      ))}
      <div className="col-span-2 sm:col-span-4 text-2xs text-ink-faint -mt-1">
        NAV as of {fmtDateShort(stats.latest_nav_date)} · scores as of {fmtDateShort(stats.latest_score_date)}
      </div>
    </div>
  );
}
