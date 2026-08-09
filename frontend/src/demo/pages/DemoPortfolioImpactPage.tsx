import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, useParams } from 'react-router-dom';
import { getAllBonds, getScore, scoreFromLiveBond } from '../demo-api';
import { DEMO_PERSONA } from '../demo-config';
import PortfolioImpactCard from '../components/PortfolioImpactCard';
import PositionSizeControl from '../components/PositionSizeControl';
import { fetchLiveMarket } from '../live-demo-api';
import type { DemoBond } from '../types';

export default function DemoPortfolioImpactPage() {
  const [searchParams] = useSearchParams();
  const { internalId } = useParams<{ internalId?: string }>();
  const navigate = useNavigate();
  const market = searchParams.get('market') || 'BCSE';

  const [bonds, setBonds] = useState<DemoBond[]>(getAllBonds());
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const markets = market === 'ALL' ? ['bcse', 'moex'] : [market.toLowerCase()];
    Promise.all(
      markets.map((m) => fetchLiveMarket(m, 'ALL').catch(() => null)),
    ).then((snaps) => {
      if (cancelled) return;
      const live = snaps.filter((s): s is NonNullable<typeof s> => s !== null);
      if (live.length) {
        const merged = live.flatMap((s) => s.bonds);
        setBonds((prev) => (merged.length ? merged : prev));
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [market]);
  const [bondId, setBondId] = useState(internalId ?? searchParams.get('bond') ?? '');
  const [allocation, setAllocation] = useState(10);
  const [sizeLabel, setSizeLabel] = useState('10%');

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
                const sc = scoreFromLiveBond(b) ?? getScore(b.internal_id);
                const distMark = b.distressed ? ' ⚠ дистрибуция' : '';
                return (
                  <option key={b.internal_id} value={b.internal_id}>
                    {b.name} ({b.currency}) — Score {sc?.score ?? '?'} — YTM {b.yield_to_maturity}%{distMark}
                  </option>
                );
              })}
            </select>
            {loading && (
              <div style={{ fontSize: 12, color: '#717680', marginTop: 8 }}>
                Загрузка актуальных котировок…
              </div>
            )}
          </div>

          <div style={{
            padding: 20, background: '#ffffff', border: '1px solid #eef3f5',
            borderRadius: 10, marginBottom: 16,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Размер позиции</div>
            <PositionSizeControl
              bond={bond}
              allocationPct={allocation}
              onChange={setAllocation}
              onLabelChange={setSizeLabel}
            />
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 300 }}>
          {bond && (
            <PortfolioImpactCard bondId={bond.internal_id} allocationPct={allocation} allocationLabel={sizeLabel} bond={bond} />
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
          onClick={() => navigate(`/demo/analytics?market=${market === 'ALL' ? 'BCSE' : market}`)}
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
