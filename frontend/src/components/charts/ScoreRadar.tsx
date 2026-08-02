interface ScoreRadarProps {
  scores: { label: string; value: number; max: number }[];
  size?: number;
}

export default function ScoreRadar({ scores, size = 220 }: ScoreRadarProps) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = size * 0.35;
  const levels = [0.25, 0.5, 0.75, 1];
  const n = scores.length;
  const angleStep = (2 * Math.PI) / n;

  const polyPoints = scores
    .map((s, i) => {
      const angle = angleStep * i - Math.PI / 2;
      const r = (s.value / s.max) * radius;
      return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
    })
    .join(' ');

  return (
    <svg width={size} height={size} className="mx-auto">
      {/* Grid levels */}
      {levels.map((lv) => (
        <polygon
          key={lv}
          points={scores
            .map((_, i) => {
              const angle = angleStep * i - Math.PI / 2;
              const r = lv * radius;
              return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
            })
            .join(' ')}
          fill="none"
          stroke="#374151"
          strokeWidth={1}
        />
      ))}

      {/* Axes */}
      {scores.map((_, i) => {
        const angle = angleStep * i - Math.PI / 2;
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={cx + radius * Math.cos(angle)}
            y2={cy + radius * Math.sin(angle)}
            stroke="#374151"
            strokeWidth={1}
          />
        );
      })}

      {/* Data polygon */}
      <polygon points={polyPoints} fill="rgba(52, 211, 153, 0.2)" stroke="#34d399" strokeWidth={2} />

      {/* Labels */}
      {scores.map((s, i) => {
        const angle = angleStep * i - Math.PI / 2;
        const labelR = radius + 22;
        const x = cx + labelR * Math.cos(angle);
        const y = cy + labelR * Math.sin(angle);
        return (
          <g key={i}>
            <text x={x} y={y} textAnchor="middle" dominantBaseline="middle" fill="#9ca3af" fontSize={9}>
              {s.label}
            </text>
            <text x={x} y={y + 11} textAnchor="middle" dominantBaseline="middle" fill="#34d399" fontSize={8} fontWeight="bold">
              {s.value}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
