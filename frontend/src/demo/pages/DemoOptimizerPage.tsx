import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { TrendingUp, Sliders, AlertCircle, PieChart, Activity, ExternalLink, Loader2 } from 'lucide-react';
import { runPortfolioOptimizer, STRATEGY_LABELS } from '../demo-api';
import type { PortfolioOptimizationResponse } from '../demo-api';
import { fetchLiveOptimize } from '../live-demo-api';
import { formatBondDisplayName, formatYtm } from '../demo-format';
import { bondDrawerStore } from '../drawer-store';
import PortfolioForecastCalculator from '../components/PortfolioForecastCalculator';

const AVAILABLE_STRATEGIES = [
  'Conservative',
  'Balanced',
  'Aggressive',
  'Carry Trade',
  'Dollarization',
  'Maximum Reward/Risk',
  'Metals++',
];

export default function DemoOptimizerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const routeMarket = (searchParams.get('market') ?? 'BCSE').toUpperCase();
  const market = routeMarket === 'MOEX' ? 'MOEX' : 'BCSE';

  const [capital, setCapital] = useState(50000);
  const [capitalError, setCapitalError] = useState<string | null>(null);
  const [currency, setCurrency] = useState(market === 'MOEX' ? 'RUB' : 'BYN');
  const [strategy, setStrategy] = useState('Balanced');
  const [data, setData] = useState<PortfolioOptimizationResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const setMarket = (nextMarket: 'BCSE' | 'MOEX') => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('market', nextMarket);
    setSearchParams(nextParams);
    if (nextMarket === 'MOEX' && currency === 'BYN') {
      setCurrency('RUB');
    } else if (nextMarket === 'BCSE' && currency === 'RUB') {
      setCurrency('BYN');
    }
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchLiveOptimize({
        capital,
        strategy,
        currency,
        top_n: 8,
        market: market.toLowerCase(),
      });
      setData({
        ...result,
        order_tickets: result.order_tickets.map((t) => ({ ...t, action: t.action as 'BUY' | 'SELL' })),
        available_strategies: AVAILABLE_STRATEGIES,
      });
    } catch {
      const fallback = runPortfolioOptimizer(capital, strategy, currency, 8, market);
      setData(fallback);
    } finally {
      setLoading(false);
    }
  }, [capital, strategy, currency, market]);

  useEffect(() => {
    const timer = setTimeout(loadData, 300);
    return () => clearTimeout(timer);
  }, [loadData]);

  const res = data ?? runPortfolioOptimizer(capital, strategy, currency, 8, market);

  const localCurrency = market === 'MOEX' ? 'RUB' : 'BYN';

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, color: '#01121a' }}>
          Институциональный Оптимизатор Портфеля & Робо-Эдвайзинг
        </h1>
        <p style={{ color: '#516c79', fontSize: 14, marginTop: 4, margin: 0 }}>
          Оптимизация по Марковицу и Risk-Parity, расчёт коэффициентов Шарпа/Сортино и генерация биржевых ордеров.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
        {/* Market Switcher */}
        <div style={{ display: 'flex', background: '#eef3f5', padding: 3, borderRadius: 8 }}>
          <button
            onClick={() => setMarket('BCSE')}
            style={{
              padding: '8px 16px',
              borderRadius: 6,
              border: 'none',
              background: market === 'BCSE' ? '#0B526B' : 'transparent',
              color: market === 'BCSE' ? '#fff' : '#516c79',
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            BCSE (Беларусь)
          </button>
          <button
            onClick={() => setMarket('MOEX')}
            style={{
              padding: '8px 16px',
              borderRadius: 6,
              border: 'none',
              background: market === 'MOEX' ? '#0B526B' : 'transparent',
              color: market === 'MOEX' ? '#fff' : '#516c79',
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            MOEX (Россия)
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#fff', padding: '8px 14px', borderRadius: 8, border: '1px solid #d6e2e6' }}>
          <span style={{ fontSize: 13, color: '#717680', fontWeight: 500 }}>Сумма инвестиций:</span>
          <input
            type="number"
            aria-label="Сумма инвестиций"
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
            style={{ width: 120, border: 'none', fontWeight: 700, fontSize: 15, color: '#01121a', outline: 'none' }}
          />
          <span style={{ fontSize: 13, color: '#717680', fontWeight: 600 }}>{currency}</span>
          {capitalError && (
            <div style={{ color: '#e03400', fontSize: 12, marginTop: 4, width: '100%', flexBasis: '100%' }}>{capitalError}</div>
          )}
        </div>

        <div style={{ display: 'flex', background: '#eef3f5', padding: 3, borderRadius: 8 }}>
          <button
            onClick={() => setCurrency(localCurrency)}
            style={{
              padding: '8px 16px',
              borderRadius: 6,
              border: 'none',
              background: currency === localCurrency ? '#0B526B' : 'transparent',
              color: currency === localCurrency ? '#fff' : '#516c79',
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {localCurrency} (Рубли)
          </button>
          <button
            onClick={() => setCurrency('USD')}
            style={{
              padding: '8px 16px',
              borderRadius: 6,
              border: 'none',
              background: currency === 'USD' ? '#0B526B' : 'transparent',
              color: currency === 'USD' ? '#fff' : '#516c79',
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            USD (Валюта)
          </button>
        </div>
      </div>

      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: '#516c79', display: 'block', marginBottom: 10 }}>
          Выберите целевую инвестиционную стратегию:
        </label>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
          {AVAILABLE_STRATEGIES.map((st) => {
            const isActive = st === strategy;
            return (
              <button
                key={st}
                onClick={() => setStrategy(st)}
                style={{
                  padding: '14px',
                  borderRadius: 10,
                  border: isActive ? '2px solid #0B526B' : '1px solid #d6e2e6',
                  background: isActive ? '#f5f9fb' : '#ffffff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: 14,
                  color: isActive ? '#0B526B' : '#01121a',
                  boxShadow: isActive ? '0 4px 12px rgba(11,82,107,0.12)' : 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Sliders size={16} color={isActive ? '#0B526B' : '#717680'} />
                  {STRATEGY_LABELS[st] || st}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#717680' }}>
          <Loader2 size={22} className="animate-spin" />
          <div style={{ marginTop: 8 }}>Загрузка данных...</div>
        </div>
      )}

      {!loading && res.allocations.length === 0 && (
        <div style={{ background: '#fff8f0', border: '1px solid #f0c76a', borderRadius: 12, padding: 24, marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12 }}>
          <AlertCircle size={20} color="#dc6803" />
          <div>
            <div style={{ fontWeight: 700, color: '#01121a' }}>Недостаточно средств или нет доступных бумаг</div>
            <div style={{ fontSize: 13, color: '#516c79', marginTop: 4 }}>
              {res.warning || `В валюте ${currency} нет активных облигаций для формирования портфеля под сумму ${capital.toLocaleString('ru-RU')} ${currency}. Попробуйте увеличить сумму или выбрать другую валюту.`}
            </div>
          </div>
        </div>
      )}

      {!loading && res.allocations.length > 0 && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
            <div style={{ background: '#fff', padding: 20, borderRadius: 12, border: '1px solid #d6e2e6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#717680', fontSize: 13, fontWeight: 500 }}>
                <TrendingUp size={18} color="#06b663" />
                Ожидаемая Доходность (YTM)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#06b663', marginTop: 8 }}>
                {res.metrics.expected_return}% годовых
              </div>
            </div>

            <div style={{ background: '#fff', padding: 20, borderRadius: 12, border: '1px solid #d6e2e6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#717680', fontSize: 13, fontWeight: 500 }}>
                <Sliders size={18} color="#0B526B" />
                Коэффициент Шарпа (Sharpe)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#01121a', marginTop: 8 }}>
                {res.metrics.sharpe}
              </div>
            </div>

            <div style={{ background: '#fff', padding: 20, borderRadius: 12, border: '1px solid #d6e2e6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#717680', fontSize: 13, fontWeight: 500 }}>
                <Sliders size={18} color="#0B526B" />
                Коэффициент Сортино (Sortino)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#01121a', marginTop: 8 }}>
                {res.metrics.sortino}
              </div>
            </div>

            <div style={{ background: '#fff', padding: 20, borderRadius: 12, border: '1px solid #d6e2e6' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#717680', fontSize: 13, fontWeight: 500 }}>
                <AlertCircle size={18} color="#dc6803" />
                Макс. просадка (MDD)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#dc6803', marginTop: 8 }}>
                {res.metrics.max_drawdown}%
              </div>
            </div>
          </div>

          {res.notes && res.notes.length > 0 && (
            <div style={{ background: '#fff8f0', border: '1px solid #f0c76a', borderRadius: 12, padding: 16, marginBottom: 24, display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <AlertCircle size={18} color="#dc6803" style={{ marginTop: 2, flexShrink: 0 }} />
              <div style={{ fontSize: 13, color: '#516c79', lineHeight: 1.5 }}>
                {res.notes.map((note, idx) => (
                  <div key={idx}>{note}</div>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #d6e2e6', padding: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 16 }}>
                  <PieChart size={20} color="#0B526B" />
                  Целевая Аллокация Портфеля
                </div>
                <span style={{ fontSize: 11, color: '#64747c' }}>Нажмите на бумагу для аналитики</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e1e9ed', textAlign: 'left', color: '#5a6e78' }}>
                      <th style={{ padding: 8 }}>Облигация</th>
                      <th style={{ padding: 8 }}>Доля</th>
                      <th style={{ padding: 8 }}>Сумма</th>
                      <th style={{ padding: 8 }}>YTM</th>
                    </tr>
                  </thead>
                  <tbody>
                    {res.allocations.map((a) => (
                      <tr
                        key={a.internal_id}
                        onClick={() => bondDrawerStore.open(a.internal_id)}
                        style={{
                          borderBottom: '1px solid #f0f4f8',
                          cursor: 'pointer',
                          transition: 'background 0.15s ease',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = '#f4f8fa'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                        title="Нажмите, чтобы открыть полную карточку и скоринг облигации"
                      >
                        <td style={{ padding: 10, fontWeight: 600, color: '#0B526B' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span>{formatBondDisplayName(a.name, a.internal_id, a.isin)}</span>
                            <ExternalLink size={12} color="#64747c" />
                          </div>
                        </td>
                        <td style={{ padding: 10, color: '#0B526B', fontWeight: 600 }}>
                          {a.weight_pct.toFixed(1)}%
                        </td>
                        <td style={{ padding: 10, color: '#516c79' }}>
                          {Math.round(a.amount).toLocaleString('ru-RU')} {a.currency ?? currency}
                        </td>
                        <td style={{ padding: 10, color: '#06b663', fontWeight: 600 }}>
                          {formatYtm(a.ytm)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #d6e2e6', padding: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 16 }}>
                  <Activity size={20} color="#0B526B" />
                  Сгенерированные Биржевые Ордера
                </div>
                <span style={{ fontSize: 11, color: '#64747c' }}>Клик для детального анализа</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {res.order_tickets.map((ticket, idx) => (
                  <div
                    key={idx}
                    onClick={() => bondDrawerStore.open(ticket.internal_id)}
                    style={{
                      padding: 14,
                      background: '#f5f9fb',
                      borderRadius: 8,
                      border: '1px solid #d6e2e6',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = '#eef6f9';
                      e.currentTarget.style.borderColor = '#0B526B';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = '#f5f9fb';
                      e.currentTarget.style.borderColor = '#d6e2e6';
                    }}
                    title="Нажмите, чтобы открыть подробную карточку инструмента"
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 13, color: '#01121a' }}>
                        <span style={{ background: '#06b663', color: '#fff', padding: '2px 8px', borderRadius: 4, fontSize: 11 }}>{ticket.action}</span>
                        <span>{formatBondDisplayName(ticket.name, ticket.internal_id)}</span>
                        <ExternalLink size={12} color="#64747c" />
                      </div>
                      <div style={{ fontSize: 12, color: '#717680', marginTop: 4 }}>
                        {ticket.rationale}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontWeight: 700, fontSize: 14, color: '#0B526B' }}>
                        {ticket.lots} шт.
                      </div>
                      <div style={{ fontSize: 12, color: '#516c79' }}>
                        ~{(ticket.est_cost ?? 0).toLocaleString('ru-RU')} {ticket.currency ?? currency}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <PortfolioForecastCalculator
            initialCapital={capital}
            initialYtm={res.metrics.expected_return}
            currency={currency}
          />
        </>
      )}
    </div>
  );
}
