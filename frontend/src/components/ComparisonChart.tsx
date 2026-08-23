import { useMemo, useState } from "react";
import {
  ResponsiveContainer,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ComposedChart,
} from "recharts";
import type { SeriesPoint } from "@/lib/api";
import { fmtDateShort } from "@/lib/utils";

interface Props {
  fundSeries: SeriesPoint[];
  benchmarkSeries: SeriesPoint[];
  categoryLabel: string;
}

const RANGES: { label: string; days: number }[] = [
  { label: "6M", days: 182 },
  { label: "1Y", days: 365 },
  { label: "3Y", days: 1095 },
  { label: "All", days: 100000 },
];

export default function ComparisonChart({ fundSeries, benchmarkSeries, categoryLabel }: Props) {
  const [rangeDays, setRangeDays] = useState(365);

  const merged = useMemo(() => {
    const benchByDate = new Map(benchmarkSeries.map((p) => [p.date, p.value]));
    const cutoff = fundSeries.length
      ? new Date(new Date(fundSeries[fundSeries.length - 1].date).getTime() - rangeDays * 86400000)
      : null;

    const sliced = cutoff ? fundSeries.filter((p) => new Date(p.date) >= cutoff) : fundSeries;
    if (sliced.length < 2) return [];

    const base = sliced[0].value;
    const benchBaseEntry = benchmarkSeries.find((p) => p.date >= sliced[0].date);
    const benchBase = benchBaseEntry?.value;

    return sliced.map((p) => {
      const bench = benchByDate.get(p.date);
      return {
        date: p.date,
        fund: (p.value / base) * 100,
        benchmark: bench != null && benchBase ? (bench / benchBase) * 100 : null,
      };
    });
  }, [fundSeries, benchmarkSeries, rangeDays]);

  if (merged.length < 2) {
    return <div className="h-64 grid place-items-center text-xs text-ink-faint">Not enough history to chart.</div>;
  }

  const hasBenchmark = merged.some((p) => p.benchmark != null);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-2xs text-ink-faint">
          <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-brand" /> Fund</span>
          {hasBenchmark && (
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-ink-faint" /> {categoryLabel} peer median</span>
          )}
        </div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => setRangeDays(r.days)}
              className={rangeDays === r.days ? "chip" : "chip"}
              data-active={rangeDays === r.days}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={merged} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="fundFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6d7bff" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#6d7bff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 6" stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtDateShort}
            tick={{ fill: "#686e7d", fontSize: 11 }}
            axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis
            tick={{ fill: "#686e7d", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={40}
            domain={["auto", "auto"]}
          />
          <Tooltip content={<ChartTooltip />} />
          {hasBenchmark && (
            <Line
              type="monotone"
              dataKey="benchmark"
              stroke="#686e7d"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
            />
          )}
          <Area
            type="monotone"
            dataKey="fund"
            stroke="#6d7bff"
            strokeWidth={2}
            fill="url(#fundFill)"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const fund = payload.find((p: any) => p.dataKey === "fund")?.value;
  const bench = payload.find((p: any) => p.dataKey === "benchmark")?.value;
  return (
    <div className="surface-card px-3 py-2 text-2xs shadow-raised">
      <div className="text-ink-faint mb-1">{fmtDateShort(label)}</div>
      {fund != null && (
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-brand" />
          <span className="num text-ink">{fund.toFixed(1)}</span>
        </div>
      )}
      {bench != null && (
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-ink-faint" />
          <span className="num text-ink-dim">{bench.toFixed(1)}</span>
        </div>
      )}
    </div>
  );
}
