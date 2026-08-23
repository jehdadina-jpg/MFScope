import { useId, useMemo } from "react";

interface Props {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  strokeWidth?: number;
}

/** Minimal inline trend line — no axes, no tooltip, just shape. */
export default function SparkLine({ values, width = 96, height = 32, className, strokeWidth = 1.6 }: Props) {
  const gradientId = useId();

  const { path, areaPath, positive } = useMemo(() => {
    if (!values || values.length < 2) return { path: "", areaPath: "", positive: true };

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

    return { path: line, areaPath: area, positive: values[values.length - 1] >= values[0] };
  }, [values, width, height, strokeWidth]);

  if (!path) {
    return <div className={className} style={{ width, height }} />;
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      preserveAspectRatio="none"
      aria-hidden
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positive ? "#3dd68c" : "#f2637a"} stopOpacity="0.22" />
          <stop offset="100%" stopColor={positive ? "#3dd68c" : "#f2637a"} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
      <path
        d={path}
        fill="none"
        stroke={positive ? "#3dd68c" : "#f2637a"}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
