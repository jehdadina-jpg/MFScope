import { ResponsiveContainer, LineChart, Line, Tooltip } from "recharts";
import type { NAVPoint } from "@/lib/api";
import { fmtNav } from "@/lib/utils";

interface SparkLineProps {
  data: NAVPoint[];
  /** Width in px; height is always 40px for card use */
  width?: number;
  className?: string;
}

function trendColor(data: NAVPoint[]): string {
  if (data.length < 2) return "#6B7280";
  const first = data[0].nav;
  const last  = data[data.length - 1].nav;
  return last >= first ? "#10B981" : "#EF4444";
}

export default function SparkLine({ data, width = 96, className }: SparkLineProps) {
  if (!data || data.length === 0) {
    return (
      <div
        className={`flex items-center justify-center text-text-muted text-2xs ${className ?? ""}`}
        style={{ width, height: 40 }}
      >
        no data
      </div>
    );
  }

  const color = trendColor(data);

  return (
    <div style={{ width, height: 40 }} className={className}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 2, bottom: 4, left: 2 }}>
          <Line
            type="monotone"
            dataKey="nav"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          <Tooltip
            contentStyle={{
              background: "#111318",
              border: "1px solid #1E2028",
              borderRadius: "6px",
              padding: "4px 8px",
              fontSize: "11px",
              color: "#E8EAF0",
            }}
            itemStyle={{ color }}
            formatter={(v: number) => [fmtNav(v), "NAV"]}
            labelFormatter={(label: string) => label}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
