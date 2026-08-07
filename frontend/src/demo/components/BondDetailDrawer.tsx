import { X, TrendingUp, AlertTriangle } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { getScore, getExplanation, getAllBonds } from '../demo-api';
import { SCORE_STATUS_LABEL, SCORE_STATUS_DESC } from '../demo-config';
import { formatYtm, formatDurationYears, formatPrice } from '../demo-format';
import ScoreExplanation from './ScoreExplanation';
import type { DemoBond } from '../types';

interface Props {
  bondId: string;
  onClose: () => void;
  onPortfolioImpact: () => void;
  onAlert: () => void;
  onOrder: () => void;
  bond?: DemoBond;
}

export default function BondDetailDrawer({ bondId, bond: liveBond, onClose, onPortfolioImpact, onAlert, onOrder }: Props) {
  const bond = liveBond ?? getAllBonds().find((b) => b.internal_id === bondId);
  const score = getScore(bondId);
  const explanation = getExplanation(bondId);
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
          width: 480,
          maxWidth: '90vw',
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
            {bond.maturity_date && <span>Погашение: {bond.maturity_date}</span>}
          </div>

          {score && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 16,
              padding: '20px', background: '#f5f9fb', borderRadius: 12, marginBottom: 20,
            }}>
              <div style={{
                width: 64, height: 64, borderRadius: 16,
                background: scoreStatusColor(score.status) + '15',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 28, fontWeight: 700,
                color: scoreStatusColor(score.status),
              }}>
                {Math.round(score.score)}
              </div>
              <div>
                <div style={{ fontSize: 11, color: '#717680', fontWeight: 500 }}>Score</div>
                <div style={{ fontSize: 16, fontWeight: 600, color: scoreStatusColor(score.status) }}>
                  {SCORE_STATUS_LABEL[score.status]}
                </div>
                <div style={{ fontSize: 13, color: '#516c79' }}>
                  {SCORE_STATUS_DESC[score.status]}
                </div>
              </div>
            </div>
          )}

          {explanation && (
            <ScoreExplanation factors={explanation.factors} />
          )}

          {!score && (
            <div style={{
              padding: 20, background: '#f5f5f5', borderRadius: 12, marginBottom: 20,
              textAlign: 'center', color: '#717680',
            }}>
              <AlertTriangle size={24} style={{ marginBottom: 8 }} />
              <div style={{ fontSize: 14 }}>Недостаточно данных для расчёта Score</div>
            </div>
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
                <KeyValue label="YTM" value={formatYtm(bond.yield_to_maturity)} />
              )}
              {bond.coupon_rate != null && (
                <KeyValue label="Купон" value={formatYtm(bond.coupon_rate)} />
              )}
              {bond.price != null && (
                <KeyValue label="Цена" value={formatPrice(bond.price, bond.currency)} />
              )}
              {bond.term_days != null && (
                <KeyValue label="Дюрация" value={formatDurationYears(bond.term_days)} />
              )}
              {bond.maturity_date && (
                <KeyValue label="Погашение" value={bond.maturity_date} />
              )}
            </div>
          </div>
        </div>

        <div style={{ padding: '16px 24px', borderTop: '1px solid #eef3f5', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button onClick={onPortfolioImpact} style={actionBtnStyle}>
            <TrendingUp size={16} />
            Влияние на портфель
          </button>
          <button onClick={onAlert} style={actionBtnOutlineStyle}>
            Создать алерт
          </button>
          <button onClick={onOrder} style={actionBtnOutlineStyle}>
            К заявке
          </button>
        </div>
      </aside>
    </>
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

function scoreStatusColor(status: string): string {
  const colors: Record<string, string> = {
    attractive: '#06b663',
    neutral: '#35aaac',
    review: '#dc6803',
    high_risk: '#e03400',
    no_data: '#717680',
  };
  return colors[status] || '#717680';
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

const actionBtnOutlineStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8,
  padding: '10px 18px', borderRadius: 8,
  border: '1px solid #d6e2e6', background: '#ffffff', color: '#0B526B',
  fontSize: 13, fontWeight: 500, cursor: 'pointer',
};
