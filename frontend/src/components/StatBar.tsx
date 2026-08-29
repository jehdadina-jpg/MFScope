import type { UniverseStats } from "@/lib/api";
import { useCountUp } from "@/hooks/useCountUp";
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

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <StatCard label="Funds scored" raw={stats.investable_schemes} format={(v) => Math.round(v).toLocaleString("en-IN")} />
      <StatCard label="Fund houses" raw={stats.amc_count} format={(v) => String(Math.round(v))} />
      <StatCard
        label="Median 1Y return"
        raw={stats.median_return_1y}
        format={(v) => fmtPct(v)}
        valueClass={returnColor(stats.median_return_1y)}
      />
      <StatCard label="NAV records" raw={stats.nav_records} format={(v) => fmtCompact(Math.round(v))} />

      <div className="col-span-2 sm:col-span-4 text-2xs text-ink-faint -mt-1">
        NAV as of {fmtDateShort(stats.latest_nav_date)} · scores as of {fmtDateShort(stats.latest_score_date)}
      </div>
    </div>
  );
}

function StatCard({
  label,
  raw,
  format,
  valueClass,
}: {
  label: string;
  raw: number | null;
  format: (v: number) => string;
  valueClass?: string;
}) {
  const animated = useCountUp(raw ?? undefined);
  return (
    <div className="surface-card p-4 group">
      <div className="text-2xs text-ink-faint mb-1">{label}</div>
      <div className={`num text-xl font-semibold tabular-nums ${valueClass ?? "text-ink"}`}>
        {animated != null ? format(animated) : "—"}
      </div>
    </div>
  );
}
