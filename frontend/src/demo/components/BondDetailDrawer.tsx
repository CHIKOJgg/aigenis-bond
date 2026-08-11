import { X, TrendingUp, AlertTriangle, ThumbsUp, ThumbsDown } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { getScore, getExplanation, getAllBonds } from '../demo-api';
import { SCORE_STATUS_LABEL, SCORE_STATUS_DESC } from '../demo-config';
import {
  formatYtm,
  formatYears,
  formatDurationYears,
  formatPrice,
  formatPoints,
} from '../demo-format';
import ScoreExplanation from './ScoreExplanation';
import type {
  DemoBond,
  DemoScore,
  BondExplanation,
  LiveBondDetail,
  LiveExplanation,
  ExplanationFactor,
} from '../types';

interface Props {
  bondId: string;
  onClose: () => void;
  onPortfolioImpact: () => void;
  bond?: DemoBond;
  score?: DemoScore;
  detail?: LiveBondDetail;
}

function normalizeFactors(
  explanation: (BondExplanation | LiveExplanation) | undefined,
): ExplanationFactor[] {
  if (!explanation || !('factors' in explanation) || !explanation.factors) return [];
  return explanation.factors.map((f): ExplanationFactor => {
    if ('impact' in f) {
      return {
        label: f.label,
        direction: f.impact,
        plainText: f.detail,
        importance: Math.abs(f.points) >= 10 ? 'high' : 'medium',
      };
    }
    return f;
  });
}

export default function BondDetailDrawer({
  bondId,
  bond: liveBond,
  score: liveScore,
  detail,
  onClose,
  onPortfolioImpact,
}: Props) {
  const bond = liveBond ?? getAllBonds().find((b) => b.internal_id === bondId);
  const score = liveScore ?? getScore(bondId);
  const fixtureExplanation = getExplanation(bondId);
  const liveExplanation: LiveExplanation | null =
    (liveBond ?? detail)?.explanation ?? null;
  const explanation: (BondExplanation | LiveExplanation) | undefined =
    liveExplanation ?? fixtureExplanation;
  const factors = normalizeFactors(explanation);
  const history = detail?.history ?? [];
  const couponSchedule = detail?.coupon_schedule ?? null;
  const strengthsRaw = liveExplanation?.strengths.length ? liveExplanation.strengths :
    (explanation as BondExplanation)?.strengths ?? [];
  const weaknessesRaw = liveExplanation?.weaknesses.length ? liveExplanation.weaknesses :
    (explanation as BondExplanation)?.weaknesses ?? [];
  const derivedStrengths = factors.filter((f) => f.direction === 'positive').map((f) => f.plainText);
  const derivedWeaknesses = factors.filter((f) => f.direction === 'negative').map((f) => f.plainText);
  const finalStrengths = strengthsRaw.length ? strengthsRaw : derivedStrengths;
  const finalWeaknesses = weaknessesRaw.length ? weaknessesRaw : derivedWeaknesses;
  const verdict = liveExplanation?.verdict ?? (explanation as BondExplanation | undefined)?.verdict ?? null;
  const summary = liveExplanation?.summary ?? (explanation as BondExplanation | undefined)?.summary ?? null;
  const panelRef = useRef<HTMLElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeBtnRef.current?.focus();
    const panel = panelRef.current;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !panel) return;
      const focusables = panel.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  if (!bond) return null;

  return (
    <>
      <div
        onClick={onClose}
        aria-hidden="true"
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.25)',
          zIndex: 100,
        }}
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={bond.name}
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: 520,
          maxWidth: '92vw',
          background: '#ffffff',
          zIndex: 101,
          boxShadow: '-4px 0 24px rgba(0,0,0,0.1)',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '20px 24px', borderBottom: '1px solid #eef3f5',
        }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{bond.name}</h2>
          <button ref={closeBtnRef} onClick={onClose} aria-label="Закрыть" style={iconBtnStyle}>
            <X size={20} />
          </button>
        </div>

        <div style={{ padding: '24px', flex: 1 }}>
          <div style={{ fontSize: 13, color: '#717680', marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
            {bond.isin && <span>ISIN: {bond.isin}</span>}
            <span>Эмитент: {bond.issuer}</span>
            <span>Валюта: {bond.currency}</span>
            <span>Рынок: {bond.market?.toUpperCase()}</span>
          </div>

          {bond.distressed && (
            <div style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              padding: '12px 16px',
              background: '#e0340012',
              border: '1px solid #e0340026',
              borderRadius: 10,
              marginBottom: 16,
            }}>
              <AlertTriangle size={16} style={{ color: '#e03400', flexShrink: 0, marginTop: 1 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#b42318' }}>
                  Дистрибуция / высокая вероятность дефолта
                </div>
                <div style={{ fontSize: 12, color: '#7a2e16', lineHeight: 1.45, marginTop: 2 }}>
                  Цена ниже 80% от номинала при доходности выше 30% — рынок закладывает
                  неисполнение обязательств. Расчётная доходность к погашению недостижима
                  без полных выплат по графику.
                </div>
              </div>
            </div>
          )}

          {score ? (
            <div style={{
              padding: '20px',
              background: '#f5f9fb',
              borderRadius: 12,
              marginBottom: 20,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div style={{
                  width: 64, height: 64, borderRadius: 16,
                  background: scoreStatusColor(score.status) + '15',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 28, fontWeight: 700,
                  color: scoreStatusColor(score.status),
                }}>
                  {Math.round(score.score)}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: '#717680', fontWeight: 500 }}>Score</div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: scoreStatusColor(score.status) }}>
                    {SCORE_STATUS_LABEL[score.status]}
                    {verdict && <span style={{ fontSize: 13, color: '#516c79', fontWeight: 500, marginLeft: 8 }}>{verdict}</span>}
                  </div>
                  <div style={{ fontSize: 13, color: '#516c79' }}>
                    {SCORE_STATUS_DESC[score.status]}
                  </div>
                </div>
              </div>
              {summary && (
                <div style={{ marginTop: 12, fontSize: 13, color: '#516c79', lineHeight: 1.5 }}>
                  {summary}
                </div>
              )}
            </div>
          ) : (
            <div style={{
              padding: 20, background: '#f5f5f5', borderRadius: 12, marginBottom: 20,
              textAlign: 'center', color: '#717680',
            }}>
              <AlertTriangle size={24} style={{ marginBottom: 8 }} />
              <div style={{ fontSize: 14 }}>Недостаточно данных для расчёта Score</div>
            </div>
          )}

          {bond.issuer_risk && (
            <div style={{
              padding: '14px 16px',
              background: '#f5f9fb',
              border: '1px solid #d6e2e6',
              borderRadius: 10,
              marginBottom: 20,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>Риск эмитента</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: issuerRiskColor(bond.issuer_risk.level) }}>
                  {bond.issuer_risk.level} · {bond.issuer_risk.score}/100
                </div>
              </div>
              <div style={{ fontSize: 12, color: '#516c79', lineHeight: 1.45, marginTop: 6 }}>
                {bond.issuer_risk.basis}
              </div>
              <div style={{ fontSize: 11, color: '#717680', marginTop: 6, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <span>credit_component: <strong>{bond.issuer_risk.credit_component.toFixed(2)}</strong></span>
                <span>·</span>
                <span>{bond.issuer_risk.method}</span>
              </div>
              <div style={{ fontSize: 11, color: '#717680', marginTop: 6 }}>
                Показатель движка, не внешний кредитный рейтинг.
              </div>
            </div>
          )}

          {(finalStrengths.length > 0 || finalWeaknesses.length > 0) && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
                Плюсы и минусы
              </div>
              {finalStrengths.length > 0 && (
                <ul style={{ margin: '0 0 10px', padding: 0, listStyle: 'none' }}>
                  {finalStrengths.map((s, i) => (
                    <li key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '6px 0' }}>
                      <ThumbsUp size={16} style={{ color: '#06b663', flexShrink: 0, marginTop: 2 }} />
                      <span style={{ fontSize: 13, color: '#2d3a45', lineHeight: 1.45 }}>{s}</span>
                    </li>
                  ))}
                </ul>
              )}
              {finalWeaknesses.length > 0 && (
                <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                  {finalWeaknesses.map((w, i) => (
                    <li key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '6px 0' }}>
                      <ThumbsDown size={16} style={{ color: '#e03400', flexShrink: 0, marginTop: 2 }} />
                      <span style={{ fontSize: 13, color: '#2d3a45', lineHeight: 1.45 }}>{w}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {score?.breakdown && <ScoreBreakdownBars breakdown={score.breakdown} />}

          {factors.length > 0 && (
            <ScoreExplanation factors={factors} />
          )}

          <div style={{
            padding: '16px',
            background: '#fafafa',
            borderRadius: 10,
            marginBottom: 20,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Ключевые показатели</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px', fontSize: 13 }}>
              {bond.yield_to_maturity != null && (
                <KeyValue
                  label="YTM"
                  value={formatYtm(bond.yield_to_maturity) + (bond.computed_ytm ? ' · оценка' : '')}
                />
              )}
              {bond.coupon_rate != null && (
                <KeyValue label="Купон" value={formatYtm(bond.coupon_rate)} />
              )}
              {bond.coupon_frequency != null && (
                <KeyValue label="Выплаты" value={`${bond.coupon_frequency} раза в год`} />
              )}
              {bond.price != null && (
                <KeyValue label="Цена" value={formatPrice(bond.price)} />
              )}
              {bond.nominal != null && (
                <KeyValue label="Номинал" value={`${Number(bond.nominal.toFixed(0)).toLocaleString('ru-RU')} ${bond.currency}`} />
              )}
              {(bond.term_days != null || bond.duration_years != null) && (
                <KeyValue label="Дюрация" value={bond.duration_years != null ? formatYears(bond.duration_years) : formatDurationYears(bond.term_days)} />
              )}
              {bond.maturity_date && (
                <KeyValue label="Погашение" value={bond.maturity_date} />
              )}
              <KeyValue label="Статус" value={bond.status === 'active' ? 'Активна' : bond.status} />
            </div>
          </div>

          {history.some((h) => h.price != null) && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
                История цены
              </div>
              <BondHistoryChart history={history.filter((h) => h.price != null)} />
            </div>
          )}

          {couponSchedule && (
            <CouponScheduleTable schedule={couponSchedule} />
          )}
        </div>

        <div style={{ padding: '16px 24px', borderTop: '1px solid #eef3f5' }}>
          <button onClick={onPortfolioImpact} style={actionBtnStyle}>
            <TrendingUp size={16} />
            Влияние на портфель
          </button>
        </div>
      </aside>
    </>
  );
}

const BREAKDOWN_LABELS: Array<[keyof import('../types').ScoreBreakdown, string]> = [
  ['yield_component', 'Доходность'],
  ['currency_component', 'Валюта'],
  ['duration_component', 'Срок / дюрация'],
  ['liquidity_component', 'Ликвидность'],
  ['credit_risk_component', 'Кредитный риск'],
  ['inflation_component', 'Инфляция'],
  ['coupon_component', 'Купонный доход'],
  ['volatility_component', 'Волатильность'],
  ['historical_volatility_component', 'Истор. волатильность'],
  ['peer_relative_component', 'vs аналоги'],
  ['metal_component', 'Драгметалл'],
];

function ScoreBreakdownBars({ breakdown }: { breakdown: import('../types').ScoreBreakdown }) {
  const rows = BREAKDOWN_LABELS.map(([key, label]) => ({ key, label, value: breakdown[key] }));
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.value)), 0.0001);
  return (
    <div style={{
      padding: '16px',
      background: '#fafafa',
      borderRadius: 10,
      marginBottom: 20,
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
        Состав оценки
      </div>
      {rows.map((r) => (
        <div key={r.key} style={{ marginBottom: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
            <span style={{ color: '#516c79' }}>{r.label}</span>
            <span style={{ fontWeight: 600, color: r.value > 0 ? '#06b663' : r.value < 0 ? '#e03400' : '#717680' }}>
              {formatPoints(r.value)}
            </span>
          </div>
          <div style={{ height: 6, background: '#eef3f5', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              width: `${Math.min(Math.abs(r.value) / maxAbs * 100, 100)}%`,
              height: '100%',
              borderRadius: 3,
              background: r.value > 0 ? '#06b663' : r.value < 0 ? '#e03400' : '#b7c4cb',
              transition: 'width 0.2s',
            }} />
          </div>
        </div>
      ))}
      {breakdown.efficiency_ratio != null && (
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 12,
          paddingTop: 10,
          borderTop: '1px solid #eef3f5',
          marginTop: 2,
        }}>
          <span style={{ color: '#516c79' }}>Эффективность доходность/риск</span>
          <span style={{ fontWeight: 600, color: '#0B526B' }}>
            {Number(breakdown.efficiency_ratio.toFixed(2))}
          </span>
        </div>
      )}
    </div>
  );
}

function BondHistoryChart({ history }: { history: Array<{ date: string; price: number | null; yield: number | null }> }) {
  const W = 440;
  const H = 150;
  const PAD = 8;
  const prices = history.map((h) => h.price).filter((p): p is number => p != null);
  const yields = history.map((h) => h.yield).filter((y): y is number => y != null);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const spanP = maxP - minP || 1;
  const minY = yields.length ? Math.min(...yields) : 0;
  const maxY = yields.length ? Math.max(...yields) : 0;
  const spanY = maxY - minY || 1;
  const x = (i: number) => PAD + (i / (history.length - 1 || 1)) * (W - PAD * 2);
  const yP = (p: number) => PAD + (1 - (p - minP) / spanP) * (H - PAD * 2);
  const yY = (v: number) => PAD + (1 - (v - minY) / spanY) * (H - PAD * 2);
  const line = (values: number[], scale: (v: number) => number) =>
    values.map((v, i) => `${x(i)},${scale(v)}`).join(' ');
  const lastPrice = prices[prices.length - 1];
  const lastYield = yields.length ? yields[yields.length - 1] : null;

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="График цены и доходности">
        <polyline
          points={line(prices, yP)}
          fill="none"
          stroke="#0B526B"
          strokeWidth={2}
        />
        {yields.length > 1 && (
          <polyline
            points={line(yields, yY)}
            fill="none"
            stroke="#35aaac"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        )}
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#516c79', marginTop: 8 }}>
        <span>
          <span style={{ color: '#0B526B', fontWeight: 600 }}>Цена</span> {lastPrice != null ? Number(lastPrice.toFixed(2)) : '—'}%
          <span style={{ color: '#717680', marginLeft: 8 }}>({Number(minP.toFixed(2))}–{Number(maxP.toFixed(2))})</span>
        </span>
        {lastYield != null && (
          <span>
            <span style={{ color: '#35aaac', fontWeight: 600 }}>YTM</span> {Number(lastYield.toFixed(2))}%
            <span style={{ color: '#717680', marginLeft: 8 }}>({Number(minY.toFixed(2))}–{Number(maxY.toFixed(2))})</span>
          </span>
        )}
      </div>
      <div style={{ fontSize: 12, color: '#717680', marginTop: 4 }}>
        {history[0]?.date} — {history[history.length - 1]?.date}
      </div>
    </div>
  );
}

function CouponScheduleTable({ schedule }: { schedule: Record<string, unknown> }) {
  const years = Object.keys(schedule).sort();
  return (
    <div style={{
      padding: '16px',
      background: '#fafafa',
      borderRadius: 10,
      marginBottom: 20,
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
        Купонные выплаты
      </div>
      {years.length === 0 ? (
        <div style={{ fontSize: 13, color: '#717680' }}>График не предоставлен</div>
      ) : (
        years.map((year) => {
          const list = (Array.isArray(schedule[year]) ? schedule[year] : []) as string[];
          return (
            <div key={year} style={{ display: 'flex', gap: 12, padding: '5px 0', fontSize: 13, borderBottom: '1px solid #f0f4f6' }}>
              <span style={{ fontWeight: 600, color: '#0B526B', width: 48, flexShrink: 0 }}>{year}</span>
              <span style={{ color: '#2d3a45' }}>
                {list.map((d) => d.slice(8, 10) + '.' + d.slice(5, 7) + '.' + d.slice(0, 4)).join(' · ')}
              </span>
            </div>
          );
        })
      )}
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span style={{ color: '#717680' }}>{label}: </span>
      <span style={{ fontWeight: 500 }}>{value}</span>
    </div>
  );
}

export function scoreStatusColor(status: string): string {
  const colors: Record<string, string> = {
    attractive: '#06b663',
    neutral: '#35aaac',
    review: '#dc6803',
    high_risk: '#e03400',
    no_data: '#717680',
  };
  return colors[status] || '#717680';
}

function issuerRiskColor(level: string): string {
  if (level === 'Очень низкий' || level === 'Низкий') return '#06b663';
  if (level === 'Критический' || level === 'Высокий') return '#e03400';
  return '#dc6803';
}

const iconBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer', color: '#516c79',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  padding: 4, borderRadius: 6,
};

const actionBtnStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8,
  padding: '10px 18px', borderRadius: 8,
  border: 'none', background: '#0B526B', color: '#ffffff',
  fontSize: 13, fontWeight: 600, cursor: 'pointer',
};
