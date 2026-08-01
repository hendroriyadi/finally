interface SparklineProps {
  points: { t: number; p: number }[];
  width?: number;
  height?: number;
  positive?: boolean;
}

export function Sparkline({
  points,
  width = 72,
  height = 20,
  positive = true,
}: SparklineProps) {
  if (points.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="sparkline pending"
        className="opacity-40"
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="var(--color-edge)"
          strokeWidth={1}
          strokeDasharray="2 3"
        />
      </svg>
    );
  }

  const values = points.map((pt) => pt.p);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const stroke = positive ? "var(--color-up)" : "var(--color-down)";

  const path = values
    .map((value, index) => {
      const x = index * step;
      const y = height - ((value - min) / span) * (height - 2) - 1;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={width} height={height} role="img" aria-label="sparkline">
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.25} />
    </svg>
  );
}
