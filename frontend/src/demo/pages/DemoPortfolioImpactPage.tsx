import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, useParams } from 'react-router-dom';
import { getAllBonds, getScore } from '../demo-api';
import { DEMO_PERSONA, ALLOCATION_OPTIONS } from '../demo-config';
import PortfolioImpactCard from '../components/PortfolioImpactCard';
import { fetchLiveMarket } from '../live-demo-api';
import type { DemoBond } from '../types';

export default function DemoPortfolioImpactPage() {
  const [searchParams] = useSearchParams();
  const { internalId } = useParams<{ internalId?: string }>();
  const navigate = useNavigate();
  const market = searchParams.get('market') || 'BCSE';

  const [bonds, setBonds] = useState<DemoBond[]>(getAllBonds());
  useEffect(() => {
    if (market === 'BCSE') fetchLiveMarket('bcse').then((s) => setBonds(s.bonds)).catch(() => {});
  }, [market]);
  const [bondId, setBondId] = useState(internalId ?? searchParams.get('bond') ?? '');
  const [allocation, setAllocation] = useState(10);

  const bond = bonds.find((b) => b.internal_id === bondId);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px' }}>Влияние на портфель</h1>
        <p style={{ color: '#516c79', fontSize: 14, margin: 0 }}>
          Оценка эффекта от добавления позиции в портфель {DEMO_PERSONA.name}
        </p>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 300 }}>
          <div style={{
            padding: 20, background: '#ffffff', border: '1px solid #eef3f5',
            borderRadius: 10, marginBottom: 16,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Выберите бумагу</div>
            <select
              value={bondId}
              onChange={(e) => setBondId(e.target.value)}
              style={{
                width: '100%', padding: '10px 14px', borderRadius: 8,
                border: '1px solid #d6e2e6', fontSize: 14, color: '#01121a',
              }}
            >
              <option value="">— Выберите облигацию —</option>
              {bonds.map((b) => {
                const sc = getScore(b.internal_id);
                return (
                  <option key={b.internal_id} value={b.internal_id}>
                    {b.name} ({b.currency}) — Score {sc?.score ?? '?'} — YTM {b.yield_to_maturity}%
                  </option>
                );
              })}
            </select>
          </div>

          <div style={{
            padding: 20, background: '#ffffff', border: '1px solid #eef3f5',
            borderRadius: 10, marginBottom: 16,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Размер позиции</div>
            <div style={{ display: 'flex', gap: 8 }}>
              {ALLOCATION_OPTIONS.map((pct) => (
                <button
                  key={pct}
                  onClick={() => setAllocation(pct)}
                  style={{
                    padding: '8px 20px',
                    borderRadius: 8,
                    border: allocation === pct ? '2px solid #0B526B' : '1px solid #d6e2e6',
                    background: allocation === pct ? '#eef3f5' : '#ffffff',
                    color: allocation === pct ? '#0B526B' : '#516c79',
                    fontWeight: allocation === pct ? 600 : 400,
                    fontSize: 14,
                    cursor: 'pointer',
                  }}
                >
                  {pct}% ({(DEMO_PERSONA.portfolio_byn * pct / 100).toLocaleString('ru-RU')} BYN)
                </button>
              ))}
            </div>
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 300 }}>
          {bond && (
            <PortfolioImpactCard bondId={bond.internal_id} allocationPct={allocation} bond={bond} />
          )}
          {!bond && (
            <div style={{
              padding: 40, textAlign: 'center', color: '#717680',
              background: '#fafafa', borderRadius: 10,
            }}>
              Выберите облигацию для оценки портфельного эффекта
            </div>
          )}
        </div>
      </div>

      <div style={{ marginTop: 24 }}>
        <button
          onClick={() => navigate(`/demo/analytics?market=${market}`)}
          style={{
            padding: '8px 20px', borderRadius: 8,
            border: '1px solid #d6e2e6', background: '#ffffff',
            color: '#0B526B', fontSize: 14, cursor: 'pointer',
          }}
        >
          ← Назад к аналитике
        </button>
      </div>
    </div>
  );
}
