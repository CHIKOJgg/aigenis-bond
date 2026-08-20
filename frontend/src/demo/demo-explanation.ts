import type {
  ScoreBreakdown,
  ScoreStatus,
  LiveExplanation,
} from './types';
import { SCORE_STATUS_LABEL, SCORE_STATUS_DESC } from './demo-config';

const BREAKDOWN_LABELS: Array<[keyof ScoreBreakdown, string]> = [
  ['yield_component', 'Доходность к погашению'],
  ['coupon_component', 'Купонный доход'],
  ['currency_component', 'Валютный профиль'],
  ['inflation_component', 'Инфляционная защита'],
  ['liquidity_component', 'Ликвидность'],
  ['duration_component', 'Дюрация и срок'],
  ['credit_risk_component', 'Кредитный риск'],
  ['volatility_component', 'Волатильность'],
  ['historical_volatility_component', 'Историческая волатильность'],
  ['peer_relative_component', 'Позиция среди аналогов'],
  ['metal_component', 'Металлическая составляющая'],
];

/** Полностью синтезированное объяснение из breakdown, когда готового нет.
 * Используется, когда у облигации нет explanation от движка (большинство
 * live-бумаг), чтобы раздел «Почему такой рейтинг» был заполнен осмысленно,
 * а не пустым. Знак компонента определяет направление (reward / risk). */
export function synthesizeExplanation(
  b: ScoreBreakdown | null | undefined,
  status: ScoreStatus | null | undefined,
  score: number | null | undefined,
): LiveExplanation | undefined {
  if (!b) return undefined;
  const statusKey = (status ?? 'no_data') as ScoreStatus;
  const factors = BREAKDOWN_LABELS.filter(
    ([k]) => typeof b[k] === 'number' && (b[k] as number) !== 0,
  ).map(([k, label]) => {
    const v = b[k] as number;
    return {
      component: k,
      label,
      points: v,
      impact: (v > 0 ? 'positive' : 'negative') as 'positive' | 'negative',
      detail: `${label}: ${v > 0 ? 'улучшает' : 'ухудшает'} рейтинг на ${Math.abs(v).toFixed(1)} п.`,
    };
  });
  const scoreText = score != null ? `Итоговый балл ${score.toFixed(1)} из 100. ` : '';
  return {
    verdict: SCORE_STATUS_LABEL[statusKey] ?? 'Оценка движка',
    summary: `${scoreText}${SCORE_STATUS_DESC[statusKey] ?? ''}`.trim(),
    strengths: [],
    weaknesses: [],
    factors,
    source: 'синтезировано (движок Aigenis)',
    metadata: {
      generated_by: 'движок Aigenis (синтез из breakdown)',
      synthesized: 'true',
    },
  };
}
