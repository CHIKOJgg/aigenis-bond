import { useId } from 'react';
import type { ScoreStatus, TermFilter } from '../types';
import { CURRENCY_LABEL } from '../demo-config';

interface Props {
  market: string;
  onMarketChange: (m: string) => void;
  currency: string;
  currencies: string[];
  onCurrencyChange: (c: string) => void;
  term: TermFilter;
  onTermChange: (t: TermFilter) => void;
  status: ScoreStatus | 'all';
  onStatusChange: (s: ScoreStatus | 'all') => void;
  liquidity: string;
  onLiquidityChange: (l: string) => void;
  sortKey: string;
  sortDir: string;
  onSortChange: (key: 'score' | 'ytm', dir: 'asc' | 'desc') => void;
}

const STATUS_OPTIONS: { value: ScoreStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Все статусы' },
  { value: 'attractive', label: 'Привлекательна' },
  { value: 'neutral', label: 'Нейтральна' },
  { value: 'review', label: 'Требует проверки' },
  { value: 'high_risk', label: 'Повышенный риск' },
];

const LIQUIDITY_OPTIONS = [
  { value: 'all', label: 'Вся ликвидность' },
  { value: 'high', label: 'Высокая' },
  { value: 'medium', label: 'Средняя' },
  { value: 'low', label: 'Низкая' },
];

const TERM_OPTIONS: { value: TermFilter; label: string }[] = [
  { value: 'all', label: 'Все сроки' },
  { value: 'up_to_1', label: 'До 1 года' },
  { value: '1_3', label: '1–3 года' },
  { value: '3_5', label: '3–5 лет' },
  { value: '5_plus', label: 'Более 5 лет' },
];

export default function AnalyticsFilters({
  market, onMarketChange,
  currency, currencies, onCurrencyChange,
  term, onTermChange,
  status, onStatusChange,
  liquidity, onLiquidityChange,
  sortKey, sortDir, onSortChange,
}: Props) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <Select label="Рынок" value={market} onChange={onMarketChange} options={[{ value: 'ALL', label: 'Все рынки' }, { value: 'BCSE', label: 'BCSE' }, { value: 'MOEX', label: 'MOEX' }]} />
        <Select label="Валюта" value={currency} onChange={onCurrencyChange} options={currencies.map((c) => ({ value: c, label: CURRENCY_LABEL[c] || c }))} />
        <Select label="Срок" value={term} onChange={(v) => onTermChange(v as TermFilter)} options={TERM_OPTIONS} />
        <Select label="Статус" value={status} onChange={(v) => onStatusChange(v as ScoreStatus | 'all')} options={STATUS_OPTIONS} />
        <Select label="Ликвидность" value={liquidity} onChange={onLiquidityChange} options={LIQUIDITY_OPTIONS} />

        <button
          onClick={() => { onStatusChange('all'); onTermChange('all'); onCurrencyChange('ALL'); onLiquidityChange('all'); }}
          style={{
            padding: '6px 14px',
            borderRadius: 6,
            border: '1px solid #d6e2e6',
            background: '#ffffff',
            color: '#516c79',
            fontSize: 13,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
            marginTop: 16,
          }}
        >
          Сбросить
        </button>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4, marginTop: 16 }}>
          {(['score', 'ytm'] as const).map((k) => (
            <button
              key={k}
              onClick={() => onSortChange(k, sortKey === k && sortDir === 'desc' ? 'asc' : 'desc')}
              style={{
                padding: '6px 14px',
                borderRadius: 6,
                border: sortKey === k ? '1.5px solid #0B526B' : '1px solid #d6e2e6',
                background: sortKey === k ? '#eef3f5' : '#ffffff',
                color: sortKey === k ? '#0B526B' : '#516c79',
                fontSize: 13,
                fontWeight: sortKey === k ? 600 : 400,
                cursor: 'pointer',
              }}
            >
              {k === 'score' ? 'Score' : 'YTM'} {sortKey === k ? (sortDir === 'asc' ? '↑' : '↓') : ''}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Select({ label, value, onChange, options }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  const id = useId();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 120 }}>
      <label htmlFor={id} style={{ fontSize: 11, color: '#717680', fontWeight: 500, textTransform: 'uppercase' }}>{label}</label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: '6px 12px',
          borderRadius: 6,
          border: '1px solid #d6e2e6',
          background: '#ffffff',
          fontSize: 13,
          color: '#01121a',
          cursor: 'pointer',
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}
