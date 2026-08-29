import { useId, useMemo } from "react";

interface Props {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  strokeWidth?: number;
  /** Draws the line in on mount instead of appearing fully-formed. */
  animate?: boolean;
}

/** Minimal inline trend line — no axes, no tooltip, just shape (with an
 *  optional draw-in and a soft glow matching the trend direction). */
export default function SparkLine({
  values,
  width = 96,
  height = 32,
  className,
  strokeWidth = 1.6,
  animate = false,
}: Props) {
  const gradientId = useId();
  const glowId = useId();

  const { path, areaPath, positive, endPoint } = useMemo(() => {
    if (!values || values.length < 2) {
      return { path: "", areaPath: "", positive: true, endPoint: null as [number, number] | null };
    }

    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const stepX = width / (values.length - 1);
    const pad = strokeWidth;

    const points = values.map((v, i) => {
      const x = i * stepX;
      const y = pad + (1 - (v - min) / range) * (height - pad * 2);
      return [x, y] as const;
    });

    const line = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
    const area = `${line} L${width},${height} L0,${height} Z`;
    const last = points[points.length - 1];

    return { path: line, areaPath: area, positive: values[values.length - 1] >= values[0], endPoint: last };
  }, [values, width, height, strokeWidth]);

  if (!path) {
    return <div className={className} style={{ width, height }} />;
  }

  const color = positive ? "#3dd68c" : "#f2637a";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      preserveAspectRatio="none"
      aria-hidden
      style={{ overflow: "visible" }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
        <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow dx="0" dy="0" stdDeviation="1.4" floodColor={color} floodOpacity="0.55" />
        </filter>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        filter={`url(#${glowId})`}
        pathLength={animate ? 1 : undefined}
        className={animate ? "spark-draw" : undefined}
      />
      {endPoint && (
        <circle cx={endPoint[0]} cy={endPoint[1]} r={strokeWidth * 1.1} fill={color} className={animate ? "spark-dot" : undefined} />
      )}
    </svg>
  );
}
