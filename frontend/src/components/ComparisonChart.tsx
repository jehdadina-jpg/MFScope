import { useId, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ComposedChart,
  ReferenceLine,
} from "recharts";
import { motion, AnimatePresence } from "framer-motion";
import type { SeriesPoint } from "@/lib/api";
import { useCountUp } from "@/hooks/useCountUp";
import { fmtDateShort, cn } from "@/lib/utils";

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

const EASE_OUT: [number, number, number, number] = [0.23, 1, 0.32, 1];

export default function ComparisonChart({ fundSeries, benchmarkSeries, categoryLabel }: Props) {
  const [rangeDays, setRangeDays] = useState(365);
  const fundGradientId = useId();
  const glowId = useId();

  const { merged, totalReturn, benchTotalReturn } = useMemo(() => {
    const benchByDate = new Map(benchmarkSeries.map((p) => [p.date, p.value]));
    const cutoff = fundSeries.length
      ? new Date(new Date(fundSeries[fundSeries.length - 1].date).getTime() - rangeDays * 86400000)
      : null;

    const sliced = cutoff ? fundSeries.filter((p) => new Date(p.date) >= cutoff) : fundSeries;
    if (sliced.length < 2) return { merged: [], totalReturn: null, benchTotalReturn: null };

    const base = sliced[0].value;
    const benchBaseEntry = benchmarkSeries.find((p) => p.date >= sliced[0].date);
    const benchBase = benchBaseEntry?.value;

    const points = sliced.map((p) => {
      const bench = benchByDate.get(p.date);
      return {
        date: p.date,
        fund: (p.value / base) * 100,
        benchmark: bench != null && benchBase ? (bench / benchBase) * 100 : null,
      };
    });

    const lastFund = points[points.length - 1].fund;
    const lastBench = [...points].reverse().find((p) => p.benchmark != null)?.benchmark ?? null;

    return {
      merged: points,
      totalReturn: lastFund - 100,
      benchTotalReturn: lastBench != null ? lastBench - 100 : null,
    };
  }, [fundSeries, benchmarkSeries, rangeDays]);

  const animatedReturn = useCountUp(totalReturn ?? undefined, 700);

  if (merged.length < 2) {
    return <div className="h-64 grid place-items-center text-xs text-ink-faint">Not enough history to chart.</div>;
  }

  const hasBenchmark = merged.some((p) => p.benchmark != null);
  const positive = (totalReturn ?? 0) >= 0;
  const relative = totalReturn != null && benchTotalReturn != null ? totalReturn - benchTotalReturn : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-4 text-2xs text-ink-faint">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-brand shadow-[0_0_6px_1px_rgba(109,123,255,0.6)]" /> Fund
          </span>
          {hasBenchmark && (
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-ink-faint" /> {categoryLabel} peer median
            </span>
          )}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={rangeDays}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.18, ease: EASE_OUT }}
            className="flex items-baseline gap-2"
          >
            <span className={cn("num text-lg font-semibold tabular-nums", positive ? "text-up" : "text-down")}>
              {animatedReturn != null ? `${animatedReturn >= 0 ? "+" : ""}${animatedReturn.toFixed(1)}%` : "—"}
            </span>
            {relative != null && (
              <span className={cn("num text-2xs", relative >= 0 ? "text-up" : "text-down")}>
                {relative >= 0 ? "+" : ""}
                {relative.toFixed(1)}pp vs peers
              </span>
            )}
          </motion.div>
        </AnimatePresence>

        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => setRangeDays(r.days)}
              className="chip"
              data-active={rangeDays === r.days}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={rangeDays}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25, ease: EASE_OUT }}
        >
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={merged} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={fundGradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={positive ? "#3dd68c" : "#f2637a"} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={positive ? "#3dd68c" : "#f2637a"} stopOpacity={0} />
                </linearGradient>
                <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
                  <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor={positive ? "#3dd68c" : "#f2637a"} floodOpacity="0.45" />
                </filter>
              </defs>
              <CartesianGrid strokeDasharray="3 6" stroke="rgba(255,255,255,0.06)" vertical={false} />
              <ReferenceLine y={100} stroke="rgba(255,255,255,0.12)" strokeDasharray="2 4" />
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
              <Tooltip
                content={<ChartTooltip />}
                cursor={{ stroke: "rgba(255,255,255,0.18)", strokeWidth: 1, strokeDasharray: "3 3" }}
              />
              {hasBenchmark && (
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  stroke="#686e7d"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  dot={false}
                  activeDot={{ r: 3, fill: "#686e7d", stroke: "#0a0b0d", strokeWidth: 2 }}
                  isAnimationActive
                  animationDuration={900}
                  animationEasing="ease-out"
                />
              )}
              <Area
                type="monotone"
                dataKey="fund"
                stroke={positive ? "#3dd68c" : "#f2637a"}
                strokeWidth={2}
                fill={`url(#${fundGradientId})`}
                filter={`url(#${glowId})`}
                dot={false}
                activeDot={{
                  r: 4.5,
                  fill: positive ? "#3dd68c" : "#f2637a",
                  stroke: "#0a0b0d",
                  strokeWidth: 2,
                }}
                isAnimationActive
                animationDuration={900}
                animationEasing="ease-out"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const fund = payload.find((p: any) => p.dataKey === "fund")?.value;
  const bench = payload.find((p: any) => p.dataKey === "benchmark")?.value;
  return (
    <div className="surface-card px-3 py-2 text-2xs shadow-raised backdrop-blur-sm">
      <div className="text-ink-faint mb-1">{fmtDateShort(label)}</div>
      {fund != null && (
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-brand" />
          <span className="num text-ink">{fund.toFixed(1)}</span>
          <span className={cn("num", fund >= 100 ? "text-up" : "text-down")}>
            ({fund >= 100 ? "+" : ""}
            {(fund - 100).toFixed(1)}%)
          </span>
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
