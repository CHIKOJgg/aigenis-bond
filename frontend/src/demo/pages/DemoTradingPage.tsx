import { useSearchParams, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import MarketTable from '../components/MarketTable';
import { fetchLiveMarket } from '../live-demo-api';
import { getAllBonds, getBonds } from '../demo-api';
import { bondDrawerStore } from '../drawer-store';
import type { DemoBond } from '../types';

const API_MARKET: Record<string, 'bcse' | 'moex'> = { BCSE: 'bcse', MOEX: 'moex' };

export default function DemoTradingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const market = searchParams.get('market') || 'ALL';
  const [bonds, setBonds] = useState<DemoBond[]>([]);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState<{ name: string; asOf: string | null } | null>(null);

  const handleMarketChange = (m: string) => {
    setSearchParams({ market: m });
  };

  const handleSelect = (internalId: string) => {
    bondDrawerStore.open(internalId);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSource(null);
    setBonds([]);

    if (market === 'ALL') {
      Promise.all([
        fetchLiveMarket('bcse').catch(() => null),
        fetchLiveMarket('moex').catch(() => null),
      ]).then((snaps) => {
        if (cancelled) return;
        const live = snaps.filter((s): s is NonNullable<typeof s> => s !== null);
        const merged = live.flatMap((s) => s.bonds);
        if (live.length) {
          setBonds(merged);
          setSource({ name: live[0]?.source ?? 'Aigenis', asOf: live[0]?.as_of ?? null });
        } else {
          setBonds(getAllBonds());
          setSource({ name: 'Aigenis (демо-копия)', asOf: null });
        }
        setLoading(false);
      });
    } else {
      fetchLiveMarket(API_MARKET[market] ?? 'bcse')
        .then((snap) => {
          if (cancelled) return;
          setBonds(snap.bonds);
          setSource({ name: snap.source, asOf: snap.as_of });
          setLoading(false);
        })
        .catch(() => {
          if (cancelled) return;
          setBonds(getBonds(market.toUpperCase()));
          setSource({ name: 'Aigenis (демо-копия)', asOf: null });
          setLoading(false);
        });
    }
    return () => { cancelled = true; };
  }, [market]);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px' }}>Торги</h1>
        <p style={{ color: '#516c79', fontSize: 14, margin: 0 }}>
          {market === 'ALL' ? 'Все рынки' : market}
          {bonds.length > 0 ? ` · ${bonds.length} облигаций` : ''}
        </p>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        {['ALL', 'BCSE', 'MOEX'].map((m) => (
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
            {m === 'ALL' ? 'Все рынки' : m}
          </button>
        ))}
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: '#516c79', padding: '4px 12px', background: '#f5f5f5', borderRadius: 6 }}>
            Облигации
          </span>
          <span
            onClick={() => navigate(`/demo/analytics?market=${market}`)}
            style={{
              fontSize: 13, color: '#0B526B', padding: '4px 12px',
              background: '#eef3f5', borderRadius: 6, fontWeight: 600,
              cursor: 'pointer', textDecoration: 'underline',
            }}
          >
            Аналитика
          </span>
          <span
            onClick={() => navigate(`/demo/search?market=${market}`)}
            style={{
              fontSize: 13, color: '#0B526B', padding: '4px 12px',
              background: '#eef3f5', borderRadius: 6, fontWeight: 600,
              cursor: 'pointer', textDecoration: 'underline',
            }}
          >
            Поиск
          </span>
        </div>
      </div>

      {source && (
        <div style={{ color: '#516c79', fontSize: 12, marginBottom: 12 }}>
          Источник: {source.name}
          {source.asOf ? ` · актуально на ${new Date(source.asOf).toLocaleString('ru-RU')}` : ''}
        </div>
      )}
      <MarketTable
        market={market}
        bonds={loading ? undefined : bonds}
        loading={loading}
        onSelect={handleSelect}
      />
    </div>
  );
}
