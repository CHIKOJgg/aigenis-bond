import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { LineChart, ArrowUpRight, ArrowDownRight, ShieldCheck, Activity, ExternalLink } from 'lucide-react';
import { formatPrice, formatBondDisplayName } from '../demo-format';
import { fetchLiveDeskCurve, fetchLiveDeskRv } from '../live-demo-api';
import { bondDrawerStore } from '../drawer-store';

interface CurvePoint {
  tenor: string;
  years: number;
  rate_pct: number;
}

interface RVSignal {
  internal_id: string;
  name?: string | null;
  issuer?: string | null;
  isin?: string | null;
  price?: number | null;
  nominal?: number | null;
  accrued_interest?: number | null;
  peer_currency: string;
  z_score: number;
  spread_pct: number;
  fair_spread_pct: number;
  side: 'buy' | 'sell' | 'hold';
  rationale: string;
}

export default function DemoDeskPage() {
  const [searchParams] = useSearchParams();
  const routeMarket = (searchParams.get('market') ?? 'BCSE').toUpperCase();
  const market = routeMarket === 'MOEX' ? 'MOEX' : 'BCSE';
  const [currency, setCurrency] = useState<'BYN' | 'USD' | 'RUB'>(market === 'MOEX' ? 'RUB' : 'BYN');
  const [curvePoints, setCurvePoints] = useState<CurvePoint[]>([]);
  const [signals, setSignals] = useState<RVSignal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (market === 'MOEX' && currency === 'BYN') {
      setCurrency('RUB');
    } else if (market === 'BCSE' && currency === 'RUB') {
      setCurrency('BYN');
    }
  }, [market]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    
    Promise.all([
      fetchLiveDeskCurve(currency, market.toLowerCase()).catch(() => ({ points: [] })),
      fetchLiveDeskRv(currency, market.toLowerCase()).catch(() => []),
    ]).then(([curveRes, rvRes]) => {
      if (!active) return;
      setCurvePoints(curveRes.points || []);
      setSignals(Array.isArray(rvRes) ? rvRes : []);
      setLoading(false);
    });

    return () => {
      active = false;
    };
  }, [currency, market]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#ffffff',
          padding: '20px 24px',
          borderRadius: 12,
          boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: '#01121a' }}>
              Институциональный Desk & Relative Value
            </h1>
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                padding: '3px 10px',
                borderRadius: 6,
                background: market === 'BCSE' ? '#eef3f5' : '#fff3e0',
                color: market === 'BCSE' ? '#0B526B' : '#a85a00',
                border: market === 'BCSE' ? '1px solid #bce0fd' : '1px solid #ffe0b2',
              }}
            >
              {market}
            </span>
          </div>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#5a6e78' }}>
            Кривые доходности Nelson-Siegel и фильтрация аномалий для рынка {market}
          </p>
        </div>

        {/* Currency Switcher */}
        <div style={{ display: 'flex', gap: 8, background: '#f0f4f8', padding: 4, borderRadius: 8 }}>
          {(['BYN', 'USD', 'RUB'] as const).map((cur) => (
            <button
              key={cur}
              onClick={() => setCurrency(cur)}
              style={{
                padding: '6px 16px',
                border: 'none',
                borderRadius: 6,
                fontSize: 13,
                fontWeight: currency === cur ? 600 : 400,
                background: currency === cur ? '#0B526B' : 'transparent',
                color: currency === cur ? '#ffffff' : '#5a6e78',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {cur}
            </button>
          ))}
        </div>
      </div>

      {/* Yield Curve Visualizer */}
      <div
        style={{
          backgroundColor: '#ffffff',
          padding: 24,
          borderRadius: 12,
          boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <LineChart size={20} color="#0B526B" />
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
            Кривая доходности {currency} (Nelson-Siegel Fit)
          </h2>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#8fa0a8' }}>Загрузка кривой...</div>
        ) : curvePoints.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#8fa0a8' }}>
            Недостаточно рыночных точек для построения кривой {currency}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Visual Bar Spectrum */}
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${curvePoints.length}, 1fr)`, gap: 12, alignItems: 'end', height: 180, padding: '20px 0 10px' }}>
              {curvePoints.map((pt) => {
                const maxRate = Math.max(...curvePoints.map((p) => p.rate_pct), 1);
                const heightPct = Math.max(15, (pt.rate_pct / maxRate) * 100);
                return (
                  <div key={pt.tenor} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, height: '100%', justifyContent: 'flex-end' }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: '#0B526B' }}>
                      {pt.rate_pct.toFixed(2)}%
                    </span>
                    <div
                      style={{
                        width: '100%',
                        maxWidth: 48,
                        height: `${heightPct}%`,
                        background: 'linear-gradient(180deg, #0B526B 0%, #1582A5 100%)',
                        borderRadius: '6px 6px 0 0',
                        transition: 'height 0.3s ease',
                      }}
                    />
                    <span style={{ fontSize: 11, color: '#5a6e78', fontWeight: 500 }}>{pt.tenor}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Relative Value Anomalies (Z-Score Arbitrage Table) */}
      <div
        style={{
          backgroundColor: '#ffffff',
          padding: 24,
          borderRadius: 12,
          boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Activity size={20} color="#0B526B" />
            <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
              Оценка аномалий цен & Z-Score ({currency})
            </h2>
          </div>
          <span style={{ fontSize: 12, color: '#8fa0a8' }}>Сигналы переоценки / недооценки</span>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#8fa0a8' }}>Расчёт сигналов...</div>
        ) : signals.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#8fa0a8' }}>
            Все выпуски торгуются в пределах справедливых спредов
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e1e9ed', textAlign: 'left', color: '#5a6e78' }}>
                  <th style={{ padding: '10px 12px' }}>Выпуск / Название облигации</th>
                  <th style={{ padding: '10px 12px' }}>Сигнал</th>
                  <th style={{ padding: '10px 12px' }}>Цена & Спред</th>
                  <th style={{ padding: '10px 12px' }}>Z-Score</th>
                  <th style={{ padding: '10px 12px' }}>Аналитическое объяснение</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig) => {
                  const isBuy = sig.side === 'buy';
                  const isSell = sig.side === 'sell';
                  const displayName = formatBondDisplayName(sig.name, sig.internal_id, sig.isin);
                  const displayId = sig.isin ? `${sig.isin} · ${sig.internal_id}` : sig.internal_id;
                  return (
                    <tr
                      key={sig.internal_id}
                      onClick={() => bondDrawerStore.open(sig.internal_id)}
                      style={{
                        borderBottom: '1px solid #f0f4f8',
                        cursor: 'pointer',
                        transition: 'background 0.15s ease',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = '#f4f8fa'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                      title="Нажмите, чтобы открыть полную карточку облигации"
                    >
                      <td style={{ padding: '12px', color: '#01121a' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 13, color: '#0B526B' }}>
                          <span>{displayName}</span>
                          <ExternalLink size={12} color="#8fa0a8" />
                        </div>
                        <div style={{ fontSize: 11, color: '#717680', marginTop: 2 }}>{displayId}</div>
                      </td>
                      <td style={{ padding: '12px' }}>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4,
                            padding: '4px 10px',
                            borderRadius: 6,
                            fontSize: 12,
                            fontWeight: 600,
                            background: isBuy ? '#e6f7ed' : isSell ? '#fde8e8' : '#f0f4f8',
                            color: isBuy ? '#0e8345' : isSell ? '#c5221f' : '#5a6e78',
                          }}
                        >
                          {isBuy && <ArrowUpRight size={14} />}
                          {isSell && <ArrowDownRight size={14} />}
                          {!isBuy && !isSell && <ShieldCheck size={14} />}
                          {isBuy ? 'Недооценена (BUY)' : isSell ? 'Переоценена (SELL)' : 'Fair Value'}
                        </span>
                      </td>
                      <td style={{ padding: '12px', color: '#5a6e78' }}>
                        <div style={{ fontWeight: 600, color: '#01121a' }}>
                          {formatPrice(sig.price, sig.peer_currency, sig.nominal, sig.accrued_interest)}
                        </div>
                        <div style={{ fontSize: 11, color: '#717680' }}>
                          Спред: {sig.spread_pct > 0 ? `+${sig.spread_pct.toFixed(1)}%` : `${sig.spread_pct.toFixed(1)}%`}
                        </div>
                      </td>
                      <td style={{ padding: '12px', fontWeight: 600, color: isBuy ? '#0e8345' : isSell ? '#c5221f' : '#01121a' }}>
                        {sig.z_score > 0 ? `+${sig.z_score.toFixed(2)}` : sig.z_score.toFixed(2)}
                      </td>
                      <td style={{ padding: '12px', color: '#334155', lineHeight: 1.4 }}>
                        {sig.rationale}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
