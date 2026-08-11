import { useState, useEffect, useMemo } from 'react';
import { useSearchParams, useNavigate, useParams } from 'react-router-dom';
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

  const [bonds, setBonds] = useState<DemoBond[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    const markets = market === 'ALL' ? ['bcse', 'moex'] : [market.toLowerCase()];
    Promise.all(
      markets.map((m) => fetchLiveMarket(m, 'ALL')),
    ).then((snaps) => {
      if (cancelled) return;
      const merged = snaps.flatMap((s) => s.bonds);
      setBonds(merged);
      setLoading(false);
      if (!merged.length) setError('Live-источник не вернул облигации');
    }).catch(() => {
      if (cancelled) return;
      setBonds([]);
      setError('Не удалось загрузить live-данные портфеля');
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [market]);
  const [bondId, setBondId] = useState(internalId ?? searchParams.get('bond') ?? '');
  const [allocation, setAllocation] = useState(10);
  const [sizeLabel, setSizeLabel] = useState('10%');
  const [bondQuery, setBondQuery] = useState('');
  const [bondMenuOpen, setBondMenuOpen] = useState(false);
  const [orderOpen, setOrderOpen] = useState(false);

  const selectedBondId = bonds.some((b) => b.internal_id === bondId) ? bondId : bonds[0]?.internal_id ?? '';
  const bond = bonds.find((b) => b.internal_id === selectedBondId);
  const filteredBonds = useMemo(() => {
    const query = bondQuery.trim().toLowerCase();
    if (!query) return bonds;
    return bonds.filter((item) => [item.name, item.issuer, item.isin, item.internal_id]
      .some((value) => String(value ?? '').toLowerCase().includes(query)));
  }, [bonds, bondQuery]);

  const chooseBond = (id: string) => {
    setBondId(id);
    setBondQuery('');
    setBondMenuOpen(false);
    setOrderOpen(false);
  };

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
            <div style={{ position: 'relative' }}>
              <input
                type="search"
                role="combobox"
                aria-label="Поиск облигации"
                aria-expanded={bondMenuOpen}
                value={bondQuery}
                onFocus={() => setBondMenuOpen(true)}
                onChange={(e) => { setBondQuery(e.target.value); setBondMenuOpen(true); }}
                placeholder={bond ? `${bond.name} · ${bond.isin ?? bond.internal_id}` : 'Поиск по названию, эмитенту или ISIN'}
                style={{
                  width: '100%', padding: '10px 14px', borderRadius: 8,
                  border: '1px solid #d6e2e6', fontSize: 14, color: '#01121a',
                  boxSizing: 'border-box',
                }}
              />
              {bondMenuOpen && (
                <div
                  role="listbox"
                  style={{
                    position: 'absolute', left: 0, right: 0, top: 'calc(100% + 4px)', zIndex: 20,
                    maxHeight: 320, overflowY: 'auto', background: '#fff',
                    border: '1px solid #d6e2e6', borderRadius: 10,
                    boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                  }}
                >
                  {filteredBonds.length === 0 ? (
                    <div style={{ padding: 16, color: '#717680', fontSize: 13 }}>Ничего не найдено в live-данных</div>
                  ) : filteredBonds.slice(0, 50).map((item) => (
                    <button
                      key={item.internal_id}
                      type="button"
                      role="option"
                      aria-selected={item.internal_id === selectedBondId}
                      onClick={() => chooseBond(item.internal_id)}
                      style={{
                        display: 'block', width: '100%', padding: '10px 12px', textAlign: 'left',
                        border: 'none', borderBottom: '1px solid #f0f4f6', background: item.internal_id === selectedBondId ? '#eef3f5' : '#fff',
                        cursor: 'pointer', color: '#01121a',
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{item.name}</div>
                      <div style={{ fontSize: 11, color: '#516c79', marginTop: 3 }}>
                        {item.issuer ?? 'Эмитент не указан'} · {item.isin ?? item.internal_id}
                      </div>
                      <div style={{ fontSize: 11, color: '#0B526B', marginTop: 3 }}>
                        {item.market.toUpperCase()} · {item.currency} · Score {item.score?.toFixed(1) ?? '—'} · YTM {item.yield_to_maturity ?? '—'}%
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div style={{ fontSize: 12, color: '#516c79', marginTop: 8 }}>
              Live-данные источника Aigenis · расчёт Score и YTM выполнен движком.
            </div>
            {loading && (
              <div style={{ fontSize: 12, color: '#717680', marginTop: 8 }}>
                Загрузка актуальных котировок…
              </div>
            )}
            {error && <div style={{ color: '#b42318', fontSize: 13, marginTop: 8 }}>{error}</div>}
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
            <>
              <PortfolioImpactCard bondId={bond.internal_id} allocationPct={allocation} allocationLabel={sizeLabel} bond={bond} />
              <button
                type="button"
                onClick={() => setOrderOpen(true)}
                style={{
                  width: '100%', marginTop: 14, padding: '12px 18px', border: 'none', borderRadius: 8,
                  background: '#0B526B', color: '#fff', fontSize: 14, fontWeight: 700, cursor: 'pointer',
                }}
              >
                Купить {allocation}% позиции
              </button>
            </>
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

      {orderOpen && bond && (
        <div style={{
          marginTop: 16, padding: 20, background: '#fffaf0', border: '1px solid #f0c36d', borderRadius: 12,
        }} role="dialog" aria-label="Подготовка заявки на покупку">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'start' }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>Заявка на покупку подготовлена</div>
              <div style={{ marginTop: 6, fontSize: 13, color: '#6b4d18', lineHeight: 1.5 }}>
                {bond.name} · {bond.market.toUpperCase()} · {bond.currency} · {Math.round(DEMO_PERSONA.portfolio_byn * allocation / 100).toLocaleString('ru-RU')} BYN
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: '#80652c' }}>
                Demo read-only: заявка не отправляется. В рабочей интеграции эта кнопка передаёт `internal_id`, рынок, валюту и размер позиции в торговый терминал Aigenis.
              </div>
            </div>
            <button type="button" onClick={() => setOrderOpen(false)} aria-label="Закрыть заявку" style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#80652c', fontSize: 20 }}>×</button>
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
            <button type="button" disabled style={{ padding: '9px 14px', border: 'none', borderRadius: 7, background: '#d6e2e6', color: '#516c79', fontWeight: 600, cursor: 'not-allowed' }}>
              Перейти к выставлению заявки
            </button>
            <button type="button" onClick={() => setOrderOpen(false)} style={{ padding: '9px 14px', border: '1px solid #d6e2e6', borderRadius: 7, background: '#fff', color: '#0B526B', cursor: 'pointer' }}>
              Вернуться к расчёту
            </button>
          </div>
        </div>
      )}

      <div style={{
        marginTop: 24,
        padding: 20,
        background: '#0B526B',
        color: '#fff',
        borderRadius: 12,
      }}>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>
          Следующий шаг для Aigenis
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.5, color: 'rgba(255,255,255,0.82)', maxWidth: 760 }}>
          Подключить ваш источник данных к готовому аналитическому слою и проверить пилот из трёх экранов: каталог, карточка облигации и Portfolio Impact.
        </div>
        <a
          href="mailto:licensing@aigenis.by?subject=Aigenis%20Analytics%20Pilot"
          style={{
            display: 'inline-block',
            marginTop: 14,
            padding: '9px 16px',
            borderRadius: 7,
            background: '#fff',
            color: '#0B526B',
            fontSize: 13,
            fontWeight: 700,
            textDecoration: 'none',
          }}
        >
          Обсудить пилот
        </a>
      </div>

      <div style={{ marginTop: 16 }}>
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
