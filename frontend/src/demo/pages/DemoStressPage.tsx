import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AlertTriangle, TrendingDown, ShieldAlert, Loader2, ExternalLink } from 'lucide-react';
import { runStressTest } from '../demo-api';
import type { StressTestResponse } from '../demo-api';
import { fetchLiveStress } from '../live-demo-api';
import { formatBondDisplayName } from '../demo-format';
import { bondDrawerStore } from '../drawer-store';

export default function DemoStressPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const routeMarket = (searchParams.get('market') ?? 'BCSE').toUpperCase();
  const market = routeMarket === 'MOEX' ? 'MOEX' : 'BCSE';
  const currency = market === 'MOEX' ? 'RUB' : 'BYN';

  const [scenarioKey, setScenarioKey] = useState('parallel_+100bp');
  const [capital, setCapital] = useState(50000);
  const [capitalError, setCapitalError] = useState<string | null>(null);
  const [data, setData] = useState<StressTestResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const setMarket = (nextMarket: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('market', nextMarket);
    setSearchParams(next);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchLiveStress({
        scenario: scenarioKey,
        market,
        capital,
      });
      setData({
        ...result,
        available_scenarios: result.available_scenarios,
      } as StressTestResponse);
    } catch {
      const fallback = runStressTest(scenarioKey, market, capital);
      setData(fallback);
    } finally {
      setLoading(false);
    }
  }, [scenarioKey, market, capital]);

  useEffect(() => {
    const timer = setTimeout(loadData, 300);
    return () => clearTimeout(timer);
  }, [loadData]);

  const res = data ?? runStressTest(scenarioKey, market, capital);
  const positionsCount = Math.max(Object.keys(res.by_position).length, 1);
  const pnlColor = (v: number) => (v >= 0 ? '#0a7d3b' : '#e03400');

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, color: '#01121a' }}>
          Институциональное Стресс-Тестирование
        </h1>
        <p style={{ color: '#516c79', fontSize: 14, marginTop: 4, margin: 0 }}>
          Оценка P&L (прибыль/убыток), Value-at-Risk (стоимость под риском) и сдвига дюрации при шоках ставок, спредов и девальвации BYN.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', background: '#eef3f5', padding: 3, borderRadius: 8 }}>
          <button
            onClick={() => setMarket('BCSE')}
            style={{
              padding: '8px 16px', borderRadius: 6, border: 'none',
              background: market === 'BCSE' ? '#0B526B' : 'transparent',
              color: market === 'BCSE' ? '#fff' : '#516c79',
              fontWeight: 600, cursor: 'pointer', fontSize: 13,
            }}
          >
            BCSE (Беларусь)
          </button>
          <button
            onClick={() => setMarket('MOEX')}
            style={{
              padding: '8px 16px', borderRadius: 6, border: 'none',
              background: market === 'MOEX' ? '#0B526B' : 'transparent',
              color: market === 'MOEX' ? '#fff' : '#516c79',
              fontWeight: 600, cursor: 'pointer', fontSize: 13,
            }}
          >
            MOEX (Россия)
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#fff', padding: '6px 12px', borderRadius: 8, border: '1px solid #d6e2e6' }}>
          <span style={{ fontSize: 13, color: '#717680', fontWeight: 500 }}>Капитал портфеля:</span>
          <input
            type="number"
            aria-label="Капитал портфеля"
            min={1}
            step={1000}
            value={capital}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw.trim() === '') { setCapitalError(null); return; }
              const v = Number(raw);
              if (!Number.isFinite(v) || v <= 0) {
                setCapitalError('Сумма инвестиций должна быть больше 0');
                return;
              }
              setCapitalError(null);
              setCapital(v);
            }}
            style={{ width: 110, border: 'none', fontWeight: 700, fontSize: 14, color: '#01121a', outline: 'none' }}
          />
          <span style={{ fontSize: 13, color: '#717680' }}>{market === 'MOEX' ? 'RUB' : 'BYN'}</span>
          {capitalError && (
            <div style={{ color: '#e03400', fontSize: 12, marginTop: 4, width: '100%', flexBasis: '100%' }}>{capitalError}</div>
          )}
        </div>
      </div>

      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: '#516c79', display: 'block', marginBottom: 10 }}>
          Выберите макроэкономический сценарий шока:
        </label>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {res.available_scenarios.map((sc) => {
            const isActive = sc.key === scenarioKey;
            return (
              <button
                key={sc.key}
                onClick={() => setScenarioKey(sc.key)}
                style={{
                  padding: '14px 16px',
                  borderRadius: 10,
                  border: isActive ? '2px solid #0B526B' : '1px solid #d6e2e6',
                  background: isActive ? '#f5f9fb' : '#ffffff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  boxShadow: isActive ? '0 4px 12px rgba(11,82,107,0.12)' : 'none',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 14, color: isActive ? '#0B526B' : '#01121a' }}>
                    <AlertTriangle size={16} color={isActive ? '#0B526B' : '#717680'} />
                    {sc.name}
                  </div>
                  <div style={{ fontSize: 12, color: '#516c79', marginTop: 6, lineHeight: 1.4 }}>
                    {sc.description}
                  </div>
                </div>
                {sc.simple_description && (
                  <div
                    style={{
                      fontSize: 11,
                      color: '#0B526B',
                      background: isActive ? '#e3eff3' : '#f0f7fa',
                      padding: '6px 8px',
                      borderRadius: 6,
                      marginTop: 8,
                      lineHeight: 1.35,
                      fontWeight: 500,
                    }}
                  >
                    💡 <strong>По-простому:</strong> {sc.simple_description}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#717680', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <Loader2 size={18} className="animate-spin" />
          Загрузка данных...
        </div>
      )}

      {!loading && (
        <>
          {/* Информационная плашка активного сценария */}
          <div style={{ background: '#f5f9fb', border: '1px solid #c5e0eb', borderRadius: 10, padding: '14px 18px', marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 14, color: '#0B526B' }}>
              <AlertTriangle size={18} color="#0B526B" />
              <span>Активный сценарий: {res.scenario.name}</span>
            </div>
            <div style={{ fontSize: 13, color: '#516c79', marginTop: 4 }}>
              <strong>Макроэкономический механизм:</strong> {res.scenario.description}
            </div>
            {res.scenario.simple_description && (
              <div style={{ fontSize: 12, color: '#01121a', marginTop: 6, background: '#ffffff', padding: '8px 12px', borderRadius: 6, border: '1px solid #d6e2e6' }}>
                💡 <strong>Что это значит для инвестора:</strong> {res.scenario.simple_description}
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
            <div style={{ background: '#fff', padding: 20, borderRadius: 12, border: '1px solid #d6e2e6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#717680', fontSize: 13, fontWeight: 500 }}>
                <TrendingDown size={18} color={pnlColor(res.pnl_amount)} />
                Ожидаемый P&L (убыток/прибыль)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: pnlColor(res.pnl_amount), marginTop: 8 }}>
                {res.pnl_amount.toLocaleString('ru-RU')} {currency}
              </div>
              <div style={{ fontSize: 13, color: pnlColor(res.pnl_amount), fontWeight: 600, marginTop: 2 }}>
                {res.pnl_pct}% от капитала
              </div>
            </div>

            <div style={{ background: '#fff', padding: 20, borderRadius: 12, border: '1px solid #d6e2e6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#717680', fontSize: 13, fontWeight: 500 }}>
                <ShieldAlert size={18} color="#dc6803" />
                Value-at-Risk (VaR 95%)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#01121a', marginTop: 8 }}>
                {typeof res.var_95 === 'number' ? `${res.var_95}%` : '2.10%'}
              </div>
              <div style={{ fontSize: 12, color: '#717680', marginTop: 2 }}>
                Максимальный ожидаемый убыток с вероятностью 95% за один торговый день
              </div>
            </div>

            <div style={{ background: '#fff', padding: 20, borderRadius: 12, border: '1px solid #d6e2e6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#717680', fontSize: 13, fontWeight: 500 }}>
                <AlertTriangle size={18} color="#0B526B" />
                Сдвиг дюрации (чувствительность к ставкам)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#01121a', marginTop: 8 }}>
                {res.duration_before} г. → {res.duration_after} г.
              </div>
              <div style={{ fontSize: 12, color: '#717680', marginTop: 2 }}>
                Насколько сильнее портфель реагирует на изменение процентных ставок
              </div>
            </div>
          </div>

          <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #d6e2e6', padding: 24 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 16px 0', color: '#01121a' }}>
              Детализация P&L по бумагам ({market})
            </h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #eef3f5', textAlign: 'left', color: '#717680' }}>
                  <th style={{ padding: '10px 12px' }}>Облигация</th>
                  <th style={{ padding: '10px 12px', textAlign: 'right' }}>Кол-во</th>
                  <th style={{ padding: '10px 12px', textAlign: 'right' }}>Инвестиции ({currency})</th>
                  <th style={{ padding: '10px 12px', textAlign: 'right' }}>Прогнозируемый P&L</th>
                </tr>
              </thead>
              <tbody>
                {(() => {
                  const positions = (res as StressTestResponse & { positions?: Array<{ internal_id: string; name: string; lots: number; invested: number; pnl: number }> }).positions;
                  if (positions && positions.length > 0) {
                    return positions.map((pos, idx) => (
                      <tr
                        key={idx}
                        onClick={() => pos.internal_id && bondDrawerStore.open(pos.internal_id)}
                        style={{
                          borderBottom: '1px solid #f5f9fb',
                          cursor: 'pointer',
                          transition: 'background 0.15s ease',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = '#f4f8fa'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                        title="Нажмите, чтобы открыть полную аналитику облигации"
                      >
                        <td style={{ padding: '12px', fontWeight: 600, color: '#0B526B' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span>{formatBondDisplayName(pos.name, pos.internal_id)}</span>
                            <ExternalLink size={12} color="#64747c" />
                          </div>
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: '#516c79' }}>
                          {pos.lots} шт.
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', color: '#516c79' }}>
                          {pos.invested.toLocaleString('ru-RU')} {currency}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: pnlColor(pos.pnl) }}>
                          {pos.pnl.toLocaleString('ru-RU')} {currency}
                        </td>
                      </tr>
                    ));
                  }
                  const entries = Object.entries(res.by_position);
                  if (entries.length === 0) {
                    return (
                      <tr>
                        <td colSpan={4} style={{ padding: '24px 12px', textAlign: 'center', color: '#717680' }}>
                          Нет позиций для расчёта — подберите рыночные параметры стресс-сценария
                        </td>
                      </tr>
                    );
                  }
                  return entries.map(([name, pnl], idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #f5f9fb' }}>
                      <td style={{ padding: '12px', fontWeight: 600, color: '#01121a' }}>
                        {formatBondDisplayName(name, name)}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', color: '#516c79' }}>—</td>
                      <td style={{ padding: '12px', textAlign: 'right', color: '#516c79' }}>
                        {(capital / positionsCount).toLocaleString('ru-RU')} {currency}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: pnlColor(pnl) }}>
                        {pnl.toLocaleString('ru-RU')} {currency}
                      </td>
                    </tr>
                  ));
                })()}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}