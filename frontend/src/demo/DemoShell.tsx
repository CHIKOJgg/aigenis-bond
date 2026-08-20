import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import DemoSidebar from './components/DemoSidebar';
import DemoTopBar from './components/DemoTopBar';
import DemoWatermark from './components/DemoWatermark';
import DemoDisclaimer from './components/DemoDisclaimer';
import DemoStatusBanner from './components/DemoStatusBanner';
import GlobalBondDrawer from './components/GlobalBondDrawer';

export default function DemoShell() {
  const [navOpen, setNavOpen] = useState(false);
  return (
    <div
      style={{
        display: 'flex',
        minHeight: '100vh',
        backgroundColor: 'var(--demo-bg, #f5f9fb)',
        color: 'var(--demo-text, #01121a)',
        fontFamily: 'var(--demo-font-body, "Onest Variable", sans-serif)',
      }}
    >
      <a
        href="#demo-main"
        style={{
          position: 'absolute',
          left: -9999,
          top: 'auto',
          width: 1,
          height: 1,
          overflow: 'hidden',
          background: '#0B526B',
          color: '#fff',
          padding: '10px 16px',
          borderRadius: 8,
          fontSize: 14,
          fontWeight: 600,
          zIndex: 200,
        }}
        onFocus={(e) => {
          e.currentTarget.style.left = '16px';
          e.currentTarget.style.top = '16px';
          e.currentTarget.style.width = 'auto';
          e.currentTarget.style.height = 'auto';
        }}
        onBlur={(e) => {
          e.currentTarget.style.left = '-9999px';
          e.currentTarget.style.top = 'auto';
          e.currentTarget.style.width = '1px';
          e.currentTarget.style.height = '1px';
        }}
      >
        Перейти к содержимому
      </a>
      <DemoSidebar open={navOpen} onClose={() => setNavOpen(false)} />
      {navOpen && (
        <div
          className="demo-nav-backdrop"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <DemoTopBar onMenuClick={() => setNavOpen((o) => !o)} />
        <DemoStatusBanner />
        <main id="demo-main" tabIndex={-1} style={{ flex: 1, padding: '24px 32px', overflowY: 'auto', overflowX: 'hidden' }}>
          <Outlet />
        </main>
        <DemoDisclaimer />
      </div>
      <DemoWatermark />
      <GlobalBondDrawer />
    </div>
  );
}
