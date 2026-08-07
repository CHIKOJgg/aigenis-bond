import { useSearchParams, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import MarketTable from '../components/MarketTable';
import { fetchLiveMarket } from '../live-demo-api';
import type { DemoBond } from '../types';

export default function DemoTradingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const market = searchParams.get('market') || 'BCSE';
  const [bonds, setBonds] = useState<DemoBond[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (market !== 'BCSE') return;
    fetchLiveMarket('bcse').then((s) => setBonds(s.bonds)).catch(() => setError('Не удалось получить актуальные данные BCSE'));
  }, [market]);

  const handleMarketChange = (m: string) => {
    setSearchParams({ market: m });
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px' }}>Торги</h1>
        <p style={{ color: '#516c79', fontSize: 14, margin: 0 }}>
          Текущие котировки и итоги торгов на {market}
        </p>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        {['BCSE', 'MOEX'].map((m) => (
          <button
            key={m}
            onClick={() => handleMarketChange(m)}
            style={{
              padding: '8px 24px',
              border: market === m ? '2px solid #0B526B' : '1px solid #d6e2e6',
              borderRadius: 8,
              background: market === m ? '#eef3f5' : '#ffffff',
              color: market === m ? '#0B526B' : '#516c79',
              fontWeight: market === m ? 600 : 400,
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            {m}
          </button>
        ))}
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: '#516c79', padding: '4px 12px', background: '#f5f5f5', borderRadius: 6 }}>
            Акции / Облигации
          </span>
          <span
            onClick={() => navigate(`/demo/analytics?market=${market}`)}
            style={{
              fontSize: 13,
              color: '#0B526B',
              padding: '4px 12px',
              background: '#eef3f5',
              borderRadius: 6,
              fontWeight: 600,
              cursor: 'pointer',
              textDecoration: 'underline',
            }}
          >
            Аналитика · Новое
          </span>
          <span style={{ fontSize: 13, color: '#516c79', padding: '4px 12px', background: '#f5f5f5', borderRadius: 6 }}>
            Результаты завершённых торгов
          </span>
        </div>
      </div>

      {error && <div style={{ color: '#b42318', marginBottom: 12 }}>{error}</div>}
      <MarketTable market={market} bonds={market === 'BCSE' ? bonds : undefined} />
    </div>
  );
}
