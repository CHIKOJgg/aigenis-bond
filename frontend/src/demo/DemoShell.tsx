import { Outlet } from 'react-router-dom';
import DemoSidebar from './components/DemoSidebar';
import DemoTopBar from './components/DemoTopBar';
import DemoWatermark from './components/DemoWatermark';
import DemoDisclaimer from './components/DemoDisclaimer';
import DemoStatusBanner from './components/DemoStatusBanner';
import GlobalBondDrawer from './components/GlobalBondDrawer';

export default function DemoShell() {
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
      <DemoSidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <DemoTopBar />
        <DemoStatusBanner />
        <main style={{ flex: 1, padding: '24px 32px', overflowY: 'auto' }}>
          <Outlet />
        </main>
        <DemoDisclaimer />
      </div>
      <DemoWatermark />
      <GlobalBondDrawer />
    </div>
  );
}
