import { useNavigate, useLocation } from 'react-router-dom';
import { BarChart3, TrendingUp } from 'lucide-react';
import { DEMO_PERSONA } from '../demo-config';

const NAV_ITEMS = [
  { path: '/demo/trading', label: 'Торги', icon: <TrendingUp size={18} /> },
  { path: '/demo/analytics', label: 'Аналитика', icon: <BarChart3 size={18} /> },
];

export default function DemoSidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside
      style={{
        width: 210,
        minWidth: 210,
        backgroundColor: 'var(--demo-sidebar-bg, #0B526B)',
        color: '#ffffff',
        display: 'flex',
        flexDirection: 'column',
        padding: '20px 0',
      }}
    >
      <div style={{ padding: '0 20px 24px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
        <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-0.5px' }}>
          Aigenis Invest
        </span>
        <span style={{ display: 'block', fontSize: 10, color: 'rgba(255,255,255,0.5)', marginTop: 2 }}>
          Analytics Preview
        </span>
      </div>

      <nav style={{ flex: 1, padding: '12px 0' }}>
        {NAV_ITEMS.map((item) => {
          const isActive = location.pathname.startsWith(item.path);
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                width: '100%',
                padding: '10px 20px',
                border: 'none',
                background: isActive ? 'rgba(255,255,255,0.12)' : 'transparent',
                color: isActive ? '#ffffff' : 'rgba(255,255,255,0.7)',
                fontSize: 14,
                fontWeight: isActive ? 600 : 400,
                cursor: 'pointer',
                transition: 'background 0.15s',
                borderLeft: isActive ? '3px solid #ffffff' : '3px solid transparent',
              }}
            >
              {item.icon}
              {item.label}
            </button>
          );
        })}
      </nav>

      <div
        style={{
          margin: '12px 16px',
          padding: '12px',
          background: 'rgba(255,255,255,0.08)',
          borderRadius: 8,
          fontSize: 12,
          color: 'rgba(255,255,255,0.6)',
        }}
      >
        <div style={{ fontWeight: 600, color: 'rgba(255,255,255,0.9)', marginBottom: 4 }}>
          {DEMO_PERSONA.name}
        </div>
        <div>{DEMO_PERSONA.label}</div>
        <div>{DEMO_PERSONA.portfolio_byn.toLocaleString('ru-RU')} BYN</div>
      </div>
    </aside>
  );
}
