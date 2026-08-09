import { useEffect, useState } from 'react';
import { ALLOCATION_OPTIONS, DEMO_PERSONA } from '../demo-config';
import type { DemoBond } from '../types';

type Mode = 'pct' | 'byn' | 'qty';

interface Props {
  bond?: DemoBond;
  allocationPct: number;
  onChange: (allocationPct: number) => void;
  onLabelChange?: (label: string) => void;
}

const PORTFOLIO = DEMO_PERSONA.portfolio_byn;

const MODE_TABS: { value: Mode; label: string }[] = [
  { value: 'pct', label: '% портфеля' },
  { value: 'byn', label: 'Сумма (BYN)' },
  { value: 'qty', label: 'Кол-во (шт)' },
];

function clampPct(pct: number): number {
  if (!Number.isFinite(pct)) return 0;
  return Math.min(100, Math.max(0, pct));
}

function fmt(n: number): string {
  return Number.isFinite(n) ? Math.round(n).toLocaleString('ru-RU') : '0';
}

export default function PositionSizeControl({ bond, allocationPct, onChange, onLabelChange }: Props) {
  const [mode, setMode] = useState<Mode>('pct');
  const [bynDraft, setBynDraft] = useState('');
  const [qtyDraft, setQtyDraft] = useState('');

  // Amount per bond in portfolio currency: nominal (face value) x price
  // (percent of face). The demo treats face values as BYN-equivalent.
  const unitAmount = bond?.nominal != null && bond.price
    ? bond.nominal * bond.price / 100
    : null;

  // Keep the derived position in sync when the selected bond changes (its
  // price/nominal define the quantity -> amount conversion).
  useEffect(() => {
    if (mode !== 'qty') return;
    const qty = Number(qtyDraft.replace(/\s/g, '').replace(',', '.'));
    if (qty > 0 && unitAmount) {
      onChange(clampPct(qty * unitAmount / PORTFOLIO * 100));
      onLabelChange?.(`${fmt(qty)} шт`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bond?.internal_id]);

  const switchMode = (next: Mode) => {
    setMode(next);
    if (next === 'pct') {
      setBynDraft(fmt(allocationPct * PORTFOLIO / 100));
      setQtyDraft(unitAmount ? fmt(allocationPct / 100 * PORTFOLIO / unitAmount) : '');
    } else if (next === 'byn') {
      setBynDraft(fmt(allocationPct / 100 * PORTFOLIO));
      setQtyDraft(unitAmount ? fmt(allocationPct / 100 * PORTFOLIO / unitAmount) : '');
    } else {
      setBynDraft(fmt(allocationPct / 100 * PORTFOLIO));
      setQtyDraft(unitAmount ? fmt(allocationPct / 100 * PORTFOLIO / unitAmount) : '');
    }
  };

  const setFromByn = (raw: string) => {
    setBynDraft(raw);
    const byn = Number(raw.replace(/\s/g, '').replace(',', '.'));
    if (!Number.isFinite(byn) || byn < 0) return;
    onChange(clampPct(byn / PORTFOLIO * 100));
    onLabelChange?.(`${fmt(byn)} BYN`);
    setQtyDraft(unitAmount ? fmt(byn / unitAmount) : '');
  };

  const setFromQty = (raw: string) => {
    setQtyDraft(raw);
    const qty = Number(raw.replace(/\s/g, '').replace(',', '.'));
    if (!Number.isFinite(qty) || qty < 0 || !unitAmount) return;
    const byn = qty * unitAmount;
    onChange(clampPct(byn / PORTFOLIO * 100));
    onLabelChange?.(`${fmt(qty)} шт`);
    setBynDraft(fmt(byn));
  };

  const setFromPct = (pct: number) => {
    const clamped = clampPct(pct);
    onChange(clamped);
    onLabelChange?.(`${Math.round(clamped * 10) / 10}%`);
    setBynDraft(fmt(clamped / 100 * PORTFOLIO));
    setQtyDraft(unitAmount ? fmt(clamped / 100 * PORTFOLIO / unitAmount) : '');
  };

  const bynAmount = allocationPct / 100 * PORTFOLIO;
  const qtyEstimate = unitAmount ? bynAmount / unitAmount : null;
  const exceedsPortfolio = allocationPct >= 100;

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid #d6e2e6',
    fontSize: 14,
    color: '#01121a',
    boxSizing: 'border-box',
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {MODE_TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => switchMode(t.value)}
            style={{
              padding: '6px 12px',
              borderRadius: 6,
              border: mode === t.value ? '1px solid #0B526B' : '1px solid #d6e2e6',
              background: mode === t.value ? '#eef3f5' : '#ffffff',
              color: mode === t.value ? '#0B526B' : '#516c79',
              fontWeight: mode === t.value ? 600 : 400,
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {mode === 'pct' && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {ALLOCATION_OPTIONS.map((pct) => (
            <button
              key={pct}
              onClick={() => setFromPct(pct)}
              style={{
                padding: '8px 20px',
                borderRadius: 8,
                border: allocationPct === pct ? '2px solid #0B526B' : '1px solid #d6e2e6',
                background: allocationPct === pct ? '#eef3f5' : '#ffffff',
                color: allocationPct === pct ? '#0B526B' : '#516c79',
                fontWeight: allocationPct === pct ? 600 : 400,
                fontSize: 14,
                cursor: 'pointer',
              }}
            >
              {pct}% ({(PORTFOLIO * pct / 100).toLocaleString('ru-RU')} BYN)
            </button>
          ))}
          <div style={{ position: 'relative', flex: 1, minWidth: 120 }}>
            <input
              type="text"
              inputMode="decimal"
              aria-label="Свой процент портфеля"
              placeholder="Свой %"
              value={allocationPct}
              onChange={(e) => {
                const v = e.target.value.replace(/\s/g, '').replace(',', '.');
                if (!/^\d*\.?\d*$/.test(v)) return;
                setFromPct(Number(v));
              }}
              style={inputStyle}
            />
            <span style={{ position: 'absolute', right: 12, top: 11, fontSize: 13, color: '#717680' }}>
              %
            </span>
          </div>
        </div>
      )}

      {mode === 'byn' && (
        <div style={{ position: 'relative' }}>
          <input
            type="text"
            inputMode="numeric"
            aria-label="Сумма позиции в BYN"
            placeholder="Например, 12 500"
            value={bynDraft}
            onChange={(e) => setFromByn(e.target.value.replace(/[^\d\s,.]/g, ''))}
            style={inputStyle}
          />
          <span style={{ position: 'absolute', right: 12, top: 11, fontSize: 13, color: '#717680' }}>
            BYN
          </span>
        </div>
      )}

      {mode === 'qty' && (
        <div>
          <div style={{ position: 'relative' }}>
            <input
              type="text"
              inputMode="numeric"
              aria-label="Количество облигаций"
              placeholder={unitAmount ? 'Например, 25' : 'Выберите бумагу сначала'}
              value={qtyDraft}
              disabled={!unitAmount}
              onChange={(e) => setFromQty(e.target.value.replace(/[^\d]/g, ''))}
              style={{ ...inputStyle, opacity: unitAmount ? 1 : 0.6 }}
            />
            <span style={{ position: 'absolute', right: 12, top: 11, fontSize: 13, color: '#717680' }}>
              шт
            </span>
          </div>
          {unitAmount && (
            <div style={{ fontSize: 12, color: '#717680', marginTop: 6 }}>
              ≈ {fmt(unitAmount)} {bond?.currency ?? 'BYN'} за штуку (номинал {fmt(bond?.nominal ?? 0)} × цена {bond?.price}%)
            </div>
          )}
          {!unitAmount && (
            <div style={{ fontSize: 12, color: '#dc6803', marginTop: 6 }}>
              Для расчёта количества нужен номинал и цена бумаги — выберите облигацию
            </div>
          )}
        </div>
      )}

      <div style={{
        marginTop: 12,
        padding: '10px 14px',
        background: '#f5f9fb',
        borderRadius: 8,
        fontSize: 13,
        color: '#516c79',
        lineHeight: 1.5,
      }}>
        {mode === 'pct' && <span>{allocationPct}% · {fmt(bynAmount)} BYN{qtyEstimate ? ` · ≈ ${fmt(qtyEstimate)} шт` : ''}</span>}
        {mode === 'byn' && <span>{fmt(bynAmount)} BYN · {allocationPct.toLocaleString('ru-RU')}%{qtyEstimate ? ` · ≈ ${fmt(qtyEstimate)} шт` : ''}</span>}
        {mode === 'qty' && <span>{qtyDraft || '0'} шт · {bynDraft || fmt(0)} BYN · {allocationPct.toLocaleString('ru-RU')}%</span>}
        {exceedsPortfolio && (
          <span style={{ display: 'block', color: '#dc6803', fontWeight: 500 }}>
            Позиция превышает портфель {PORTFOLIO.toLocaleString('ru-RU')} BYN — эффект рассчитан на 100%
          </span>
        )}
      </div>
    </div>
  );
}
