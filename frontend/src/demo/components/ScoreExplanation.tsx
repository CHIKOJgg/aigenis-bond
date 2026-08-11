import type { ExplanationFactor } from '../types';

interface Props {
  factors: ExplanationFactor[];
}

const directionIcon: Record<string, string> = {
  positive: '+',
  negative: '−',
  neutral: '·',
};

const directionColor: Record<string, string> = {
  positive: '#06b663',
  negative: '#e03400',
  neutral: '#516c79',
};

export default function ScoreExplanation({ factors }: Props) {
  return (
    <div style={{ marginBottom: 20 }}>
      <details style={{ marginBottom: 16, padding: '12px 14px', background: '#f5f9fb', border: '1px solid #d6e2e6', borderRadius: 8 }}>
        <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 700, color: '#0B526B' }}>
          Как считается Score
        </summary>
        <div style={{ marginTop: 10, fontSize: 12, color: '#516c79', lineHeight: 1.55 }}>
          Score — это сумма 11 объяснимых факторов, а не прогноз цены. Положительные
          факторы формируют reward, отрицательные — risk. Итог дополнительно
          проверяется через efficiency ratio: reward / (reward + risk + 1).
          Если данных недостаточно, фактор получает нейтральный вклад и это видно
          в breakdown.
          <div style={{ marginTop: 8, display: 'grid', gap: 4 }}>
            <span><strong>Reward:</strong> доходность, валюта, срок, ликвидность, купон, инфляция, аналоги.</span>
            <span><strong>Risk:</strong> кредитный риск, волатильность, историческая волатильность, distressed-сигнал.</span>
            <span><strong>Уровни:</strong> S ≥ 85 · A ≥ 75 · B ≥ 60 · C ≥ 45 · D &lt; 45.</span>
          </div>
        </div>
      </details>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
        Почему такой рейтинг
      </div>
      {factors.map((f, i) => (
        <div
          key={i}
          style={{
            display: 'flex',
            gap: 12,
            padding: '10px 0',
            borderBottom: i < factors.length - 1 ? '1px solid #f5f5f5' : 'none',
          }}
        >
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 24,
            height: 24,
            borderRadius: '50%',
            background: directionColor[f.direction] + '15',
            color: directionColor[f.direction],
            fontWeight: 700,
            fontSize: 16,
            flexShrink: 0,
          }}>
            {directionIcon[f.direction]}
          </span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#01121a', marginBottom: 2 }}>
              {f.label}
              {f.importance === 'high' && (
                <span style={{ fontSize: 10, color: '#717680', marginLeft: 6, fontWeight: 400 }}>
                  значимый фактор
                </span>
              )}
            </div>
            <div style={{ fontSize: 13, color: '#516c79', lineHeight: 1.5 }}>
              {f.plainText}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
