import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Bell, Search, Settings, X, Menu } from 'lucide-react';
import { DEMO_PERSONA } from '../demo-config';
import { fetchLiveSearch } from '../live-demo-api';
import { scoreFromLiveBond } from '../demo-api';
import { bondDrawerStore } from '../drawer-store';
import { formatYtm } from '../demo-format';
import { scoreStatusColor } from './BondDetailDrawer';
import { SCORE_STATUS_LABEL } from '../demo-config';
import type { DemoBond } from '../types';

interface Props {
  market?: string;
  onMarketChange?: (market: string) => void;
  onMenuClick?: () => void;
}

const SUGGESTION_DEBOUNCE = 220;
const SUGGESTION_LIMIT = 8;

export default function DemoTopBar({ market: marketProp, onMarketChange, onMenuClick }: Props) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // The header market switch is global: it reads/writes the ?market= query
  // param so it works on every demo page, not just the one that owns the
  // market state. The prop override stays for embedded/explicit usage.
  const routeMarket = (searchParams.get('market') ?? 'BCSE').toUpperCase();
  const market = (marketProp ?? (routeMarket === 'BCSE' || routeMarket === 'MOEX' ? routeMarket : 'BCSE'));
  const [q, setQ] = useState('');
  const [suggestions, setSuggestions] = useState<DemoBond[]>([]);
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const noticeTimer = useRef<number | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const showNotice = (text: string) => {
    setNotice(text);
    if (noticeTimer.current !== null) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 2600);
  };

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setSuggestions([]);
      return;
    }
    const t = window.setTimeout(async () => {
      try {
        const data = await fetchLiveSearch(term, market);
        setSuggestions(data.bonds.slice(0, SUGGESTION_LIMIT));
      } catch {
        setSuggestions([]);
      }
    }, SUGGESTION_DEBOUNCE);
    return () => window.clearTimeout(t);
  }, [q, market]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const submit = () => {
    const term = q.trim();
    if (!term) return;
    setOpen(false);
    navigate(`/demo/search?q=${encodeURIComponent(term)}&market=${market}`);
  };

  const pick = (bond: DemoBond) => {
    setOpen(false);
    setQ('');
    inputRef.current?.blur();
    bondDrawerStore.open(bond.internal_id);
  };

  const changeMarket = (m: string) => {
    if (onMarketChange) {
      onMarketChange(m);
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set('market', m);
    setSearchParams(next, { replace: true });
  };

  return (
    <header
      className="demo-header"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 32px',
        borderBottom: '1px solid var(--demo-border, #d6e2e6)',
        backgroundColor: 'var(--demo-card, #ffffff)',
        minHeight: 56,
        gap: 16,
        flexWrap: 'wrap',
      }}
    >
      <button
        className="demo-menu-btn"
        onClick={onMenuClick}
        aria-label="Открыть меню"
        style={{
          display: 'none',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 6,
          color: '#0B526B',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Menu size={20} />
      </button>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
        <div style={{ display: 'flex', background: '#eef3f5', borderRadius: 8, padding: 2 }}>
          {['BCSE', 'MOEX'].map((m) => (
            <button
              key={m}
              onClick={() => changeMarket(m)}
              style={{
                padding: '6px 16px',
                border: 'none',
                borderRadius: 6,
                background: market === m ? '#ffffff' : 'transparent',
                color: market === m ? '#0B526B' : '#516c79',
                fontWeight: market === m ? 600 : 400,
                fontSize: 13,
                cursor: 'pointer',
                boxShadow: market === m ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div ref={wrapRef} className="demo-search" style={{ flex: 1, maxWidth: 480, minWidth: 0, flexShrink: 1, position: 'relative' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          background: '#f5f9fb',
          border: '1px solid #d6e2e6',
          borderRadius: 8,
        }}>
          <Search size={16} style={{ color: '#516c79', flexShrink: 0 }} />
          <input
            ref={inputRef}
            type="search"
            name="q"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setOpen(false);
                inputRef.current?.blur();
              } else if (e.key === 'Enter') {
                submit();
              }
            }}
            placeholder="Поиск по облигациям…"
            aria-label="Поиск облигаций"
            style={{
              flex: 1,
              border: 'none',
              outline: 'none',
              background: 'transparent',
              fontSize: 14,
              color: '#01121a',
            }}
          />
          {q && (
            <button
              onClick={() => { setQ(''); setSuggestions([]); inputRef.current?.focus(); }}
              aria-label="Очистить"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 2, color: '#516c79', display: 'flex',
              }}
            >
              <X size={14} />
            </button>
          )}
        </div>
        {open && suggestions.length > 0 && (
          <div
            role="listbox"
            style={{
              position: 'absolute',
              top: 'calc(100% + 4px)',
              left: 0,
              right: 0,
              maxHeight: 380,
              overflowY: 'auto',
              background: '#ffffff',
              border: '1px solid #d6e2e6',
              borderRadius: 10,
              boxShadow: '0 8px 24px rgba(0,0,0,0.08)',
              zIndex: 50,
            }}
          >
            {suggestions.map((bond) => {
              const score = scoreFromLiveBond(bond);
              const status = score?.status ?? 'no_data';
              return (
                <button
                  key={bond.internal_id}
                  role="option"
                  onClick={() => pick(bond)}
                  style={{
                    display: 'flex',
                    width: '100%',
                    textAlign: 'left',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    padding: '10px 12px',
                    borderBottom: '1px solid #f0f4f6',
                    alignItems: 'center',
                    gap: 10,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#f5f9fb'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                >
                  <span style={{
                    display: 'inline-block',
                    padding: '2px 6px',
                    background: bond.market.toUpperCase() === 'BCSE' ? '#eef3f5' : '#fff3e0',
                    color: bond.market.toUpperCase() === 'BCSE' ? '#0B526B' : '#a85a00',
                    borderRadius: 4,
                    fontSize: 11,
                    fontWeight: 600,
                    flexShrink: 0,
                  }}>
                    {bond.market.toUpperCase()}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: '#01121a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {bond.name}
                    </div>
                    <div style={{ fontSize: 11, color: '#717680', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {bond.issuer} · {bond.isin ?? bond.internal_id}
                    </div>
                  </div>
                  <div style={{ flexShrink: 0, textAlign: 'right' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#0B526B' }}>
                      {formatYtm(bond.yield_to_maturity)}
                    </div>
                    <div style={{ fontSize: 11, color: scoreStatusColor(status) }}>
                      {SCORE_STATUS_LABEL[status]}
                      {bond.distressed && <span style={{ color: '#e03400', fontWeight: 600 }}> · дистрибуция</span>}
                    </div>
                  </div>
                </button>
              );
            })}
            <button
              onClick={submit}
              style={{
                width: '100%',
                textAlign: 'center',
                background: '#f5f9fb',
                border: 'none',
                borderTop: '1px solid #d6e2e6',
                padding: '8px 12px',
                cursor: 'pointer',
                color: '#0B526B',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              Показать все результаты →
            </button>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        <button
          aria-label="Уведомления"
          onClick={() => showNotice('Уведомления недоступны в демо-режиме')}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 6,
            color: '#516c79',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Bell size={18} />
        </button>
        <div
          className="demo-persona"
          style={{
            fontSize: 13,
            color: '#01121a',
            fontWeight: 500,
            marginRight: 8,
            maxWidth: 160,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {DEMO_PERSONA.name} · {DEMO_PERSONA.portfolio_byn.toLocaleString('ru-RU')} BYN
        </div>
        <button
          aria-label="Настройки"
          onClick={() => showNotice('Настройки недоступны в демо-режиме')}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 6,
            color: '#516c79',
          }}
        >
          <Settings size={18} />
        </button>
      </div>
      {notice && (
        <div
          role="status"
          style={{
            position: 'fixed',
            left: '50%',
            bottom: 24,
            transform: 'translateX(-50%)',
            background: '#0B526B',
            color: '#ffffff',
            padding: '10px 18px',
            borderRadius: 10,
            fontSize: 14,
            fontWeight: 500,
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
            zIndex: 200,
          }}
        >
          {notice}
        </div>
      )}
    </header>
  );
}
