const WIDTH = 60;
const HEIGHT = 20;

interface SparklineProps {
  points: number[];
}

/**
 * Pure presentational inline-SVG sparkline. Holds no state and never resets
 * anything — accumulation lives entirely in `useSseStream`'s ref; this
 * component only ever reads the array it's given.
 *
 * Fewer than two points (a ticker with zero SSE ticks received yet — either
 * just added, or before the first stream event) renders a flat baseline
 * placeholder line. Empty and loading share this exact rendering per the
 * UI-SPEC: there is nothing to distinguish them.
 */
export function Sparkline({ points }: SparklineProps) {
  if (points.length < 2) {
    return (
      <svg width={WIDTH} height={HEIGHT} className="opacity-40" aria-hidden="true">
        <line
          x1={0}
          y1={HEIGHT / 2}
          x2={WIDTH}
          y2={HEIGHT / 2}
          stroke="currentColor"
          strokeWidth={1}
        />
      </svg>
    );
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  // Guard a zero range (a perfectly flat series) so we never divide by zero.
  const range = max - min || 1;

  const coords = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * WIDTH;
      const y = HEIGHT - ((point - min) / range) * HEIGHT;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width={WIDTH} height={HEIGHT} aria-hidden="true">
      <polyline points={coords} fill="none" stroke="#209dd7" strokeWidth={1.5} />
    </svg>
  );
}
