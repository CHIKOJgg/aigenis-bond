import type { DemoScore } from '../types';

interface Props {
  score: DemoScore | undefined;
}

export default function BondScoreBadge({ score }: Props) {
  if (!score) {
    return (
      <span style={{ color: '#717680', fontSize: 13 }}>
        —
      </span>
    );
  }

  const colors: Record<string, string> = {
    attractive: '#06b663',
    neutral: '#35aaac',
    review: '#dc6803',
    high_risk: '#e03400',
    no_data: '#717680',
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 40,
        height: 40,
        borderRadius: 10,
        background: `${colors[score.status]}15`,
        color: colors[score.status],
        fontWeight: 700,
        fontSize: 16,
      }}>
        {Math.round(score.score)}
      </span>
      <span style={{ fontSize: 11, color: '#516c79', fontWeight: 600 }}>
        / 100
      </span>
    </div>
  );
}
