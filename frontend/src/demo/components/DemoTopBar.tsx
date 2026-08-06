import { Bell, Settings } from 'lucide-react';
import { DEMO_PERSONA } from '../demo-config';

interface Props {
  market?: string;
  onMarketChange?: (market: string) => void;
}

export default function DemoTopBar({ market = 'BCSE', onMarketChange }: Props) {

  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 32px',
        borderBottom: '1px solid var(--demo-border, #d6e2e6)',
        backgroundColor: 'var(--demo-card, #ffffff)',
        minHeight: 56,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ display: 'flex', background: '#eef3f5', borderRadius: 8, padding: 2 }}>
          {['BCSE', 'MOEX'].map((m) => (
            <button
              key={m}
              onClick={() => onMarketChange?.(m)}
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

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
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
          style={{
            fontSize: 13,
            color: '#01121a',
            fontWeight: 500,
            marginRight: 8,
          }}
        >
          {DEMO_PERSONA.name} · {DEMO_PERSONA.portfolio_byn.toLocaleString('ru-RU')} BYN
        </div>
        <button
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
    </header>
  );
}
