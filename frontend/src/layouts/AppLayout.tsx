import { useState, type ReactNode } from 'react';
import { useLocation, useNavigate, Outlet } from 'react-router-dom';
import {
  ArrowLeft, Bell, BookOpen, Briefcase, BarChart3, User, Menu, X,
  Star, PieChart, Globe2, Brain, Clock, Calculator, FileText, TrendingUp, Newspaper, LineChart,
} from 'lucide-react';
import { useAuth } from '../lib/AuthContext';
import { useI18n, LanguageToggle } from '../i18n';
import { useExchange, type Exchange } from '../lib/ExchangeContext';
import { ROUTES } from '../app/paths';

interface NavItem {
  path: string;
  label: string;
  icon: ReactNode;
  premium?: boolean;
}

const SIDEBAR_MAIN: NavItem[] = [
  { path: ROUTES.bonds, label: 'Торги', icon: <ArrowLeft size={18} style={{ transform: 'rotate(45deg)' }} /> },
  { path: ROUTES.stocks, label: 'Акции', icon: <TrendingUp size={18} /> },
  { path: ROUTES.desk, label: 'Менеджер заявок', icon: <Briefcase size={18} />, premium: true },
  { path: ROUTES.portfolio, label: 'Портфель', icon: <PieChart size={18} />, premium: true },
  { path: ROUTES.analytics, label: 'Аналитика', icon: <BarChart3 size={18} /> },
  { path: ROUTES.scores, label: 'Справочник', icon: <BookOpen size={18} /> },
  { path: ROUTES.account, label: 'Профиль', icon: <User size={18} /> },
];

const SIDEBAR_EXTRA: NavItem[] = [
  { path: ROUTES.recommendations, label: 'Рекомендации', icon: <Brain size={18} /> },
  { path: ROUTES.forecast, label: 'Прогноз', icon: <Clock size={18} />, premium: true },
  { path: ROUTES.alerts, label: 'Алерты', icon: <Bell size={18} />, premium: true },
  { path: ROUTES.portfolioAdvanced, label: 'Портфель Pro', icon: <LineChart size={18} />, premium: true },
  { path: ROUTES.chat, label: 'AI-чат', icon: <Brain size={18} />, premium: true },
  { path: ROUTES.news, label: 'Новости', icon: <Newspaper size={18} /> },
  { path: ROUTES.calculator, label: 'Калькулятор', icon: <Calculator size={18} /> },
  { path: ROUTES.documents, label: 'Документы', icon: <FileText size={18} />, premium: true },
];

export default function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user } = useAuth();
  const { exchange, setExchange } = useExchange();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useI18n();

  const tier = user?.subscription_tier || 'free';

  const handleNav = (item: NavItem) => {
    if (item.premium && tier === 'free') return;
    navigate(item.path);
  };

  const renderNavItem = (item: NavItem) => {
    const active = location.pathname.startsWith(item.path);
    const locked = item.premium && tier === 'free';
    return (
      <button
        key={item.path}
        onClick={() => handleNav(item)}
        style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '11px 14px',
          borderRadius: 10, border: 'none', cursor: 'pointer',
          fontSize: 14, fontWeight: 500, textAlign: 'left', width: '100%',
          background: active ? 'rgba(255,255,255,.14)' : 'transparent',
          color: active ? '#ffffff' : '#b2c9d1',
          transition: 'all .12s',
        }}
      >
        {item.icon}
        <span className="flex-1 text-left">{item.label}</span>
        {locked && <span style={{ fontSize: 10, color: '#759eac' }}>PRO</span>}
      </button>
    );
  };

  return (
    <div style={{
      fontFamily: "'Onest Variable', 'Onest', -apple-system, sans-serif",
      backgroundColor: '#f5f9fb',
      color: '#01121a',
      minHeight: '100vh',
      display: 'flex',
    }}>
      {/* ──── Desktop sidebar (dark teal) ──── */}
      <aside style={{
        width: 210,
        backgroundColor: '#004b65',
        display: 'none',
        flexDirection: 'column',
        flexShrink: 0,
        zIndex: 10,
        height: '100vh',
        position: 'fixed',
      }} className="md:flex">
        <div style={{ padding: '18px 16px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button onClick={() => navigate('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'baseline', padding: 0 }}>
            <span style={{
              fontFamily: "'Montserrat Variable', Montserrat, sans-serif",
              fontSize: 18, fontWeight: 800, color: '#ffffff', letterSpacing: '-0.5px',
            }}>aigenis</span>
            <span style={{ fontSize: 13, fontWeight: 400, color: '#b2c9d1', marginLeft: 4 }}>invest</span>
          </button>
        </div>

        <nav style={{ flex: 1, padding: '0 6px', display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto' }}>
          {SIDEBAR_MAIN.map(renderNavItem)}
          <div style={{ margin: '12px 14px 6px', fontSize: 10, letterSpacing: '1px', color: '#759eac', textTransform: 'uppercase', fontWeight: 600 }}>
            Сервисы
          </div>
          {SIDEBAR_EXTRA.map(renderNavItem)}
        </nav>

        <div style={{ padding: '12px 14px', margin: '8px 6px 10px', background: 'rgba(255,255,255,.08)', borderRadius: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10 }} onClick={() => navigate('/account')}>
            <div style={{
              width: 36, height: 36, borderRadius: 10, background: 'rgba(255,255,255,.12)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#b2c9d1',
              fontSize: 14, fontFamily: "'Montserrat Variable', sans-serif", fontWeight: 700,
            }}>
              {(user?.name || 'П').charAt(0).toUpperCase()}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#ffffff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user?.name || 'Гость'}
              </div>
              <div style={{ fontSize: 11, color: '#759eac' }}>A0418012025</div>
            </div>
          </div>

        <div style={{ padding: '0 14px 14px', display: 'flex', gap: 8 }}>
          <div style={{ background: '#01121a', borderRadius: 8, padding: '5px 10px', display: 'flex', alignItems: 'center', gap: 5, fontSize: 9, color: '#ffffff', lineHeight: 1 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M3.609 1.814L13.792 12 3.61 22.186a.996.996 0 01-.61-.92V2.734a1 1 0 01.609-.92zm10.89 10.893l2.302 2.302-10.937 6.333 8.635-8.635zm3.199-1.4l2.807 1.626a1 1 0 010 1.734l-2.808 1.626-2.53-2.53 2.53-2.456zM5.864 2.658L16.8 8.99l-2.302 2.302-8.634-8.634z"/></svg>
            <div>
              <div style={{ fontSize: 7, opacity: .7 }}>GET IT ON</div>
              <div style={{ fontSize: 10, fontWeight: 600 }}>Google Play</div>
            </div>
          </div>
          <div style={{ background: '#01121a', borderRadius: 8, padding: '5px 10px', display: 'flex', alignItems: 'center', gap: 5, fontSize: 9, color: '#ffffff', lineHeight: 1 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg>
            <div>
              <div style={{ fontSize: 7, opacity: .7 }}>Download on the</div>
              <div style={{ fontSize: 10, fontWeight: 600 }}>App Store</div>
            </div>
          </div>
        </div>
      </aside>

      {/* ──── Mobile top bar ──── */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-4 h-14"
        style={{ background: '#004b65', color: '#ffffff' }}>
        <button onClick={() => setMobileOpen(true)} style={{ background: 'none', border: 'none', color: '#ffffff', cursor: 'pointer', padding: 4 }}>
          <Menu size={22} />
        </button>
        <span style={{ fontFamily: "'Montserrat Variable', sans-serif", fontWeight: 800, fontSize: 16 }}>aigenis invest</span>
        <button onClick={() => navigate('/alerts')} style={{ background: 'none', border: 'none', color: '#ffffff', cursor: 'pointer', padding: 4, position: 'relative' }}>
          <Bell size={20} />
          <span style={{ position: 'absolute', top: 0, right: 0, width: 8, height: 8, borderRadius: 10, background: '#e03400', border: '1.5px solid #004b65' }} />
        </button>
      </div>

      {/* Mobile menu sheet */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-[60]">
          <div className="fixed inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <div className="fixed left-0 top-0 bottom-0 w-[280px] bg-[#004b65] p-4 flex flex-col animate-slideInLeft" style={{ fontFamily: "'Onest Variable', sans-serif" }}>
            <div className="flex items-center justify-between mb-4">
              <span style={{ fontFamily: "'Montserrat Variable', sans-serif", fontWeight: 800, color: '#ffffff', fontSize: 18 }}>aigenis invest</span>
              <button onClick={() => setMobileOpen(false)} style={{ background: 'rgba(255,255,255,.12)', border: 'none', width: 30, height: 30, borderRadius: 8, color: '#ffffff', cursor: 'pointer' }}>
                <X size={16} />
              </button>
            </div>
            <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto' }}>
              {[...SIDEBAR_MAIN, ...SIDEBAR_EXTRA].map((item) => {
                const locked = item.premium && tier === 'free';
                return (
                  <button
                    key={item.path}
                    onClick={() => { handleNav(item); setMobileOpen(false); }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
                      borderRadius: 10, border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 500,
                      textAlign: 'left', width: '100%', background: 'transparent', color: '#b2c9d1',
                    }}
                  >
                    {item.icon}
                    <span className="flex-1 text-left">{item.label}</span>
                    {locked && <span style={{ fontSize: 10, color: '#759eac' }}>PRO</span>}
                  </button>
                );
              })}
            </nav>
            <button onClick={() => { navigate('/account'); setMobileOpen(false); }}
              style={{ padding: '12px 14px', background: 'rgba(255,255,255,.08)', borderRadius: 12, color: '#ffffff', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 32, height: 32, borderRadius: 9, background: 'rgba(255,255,255,.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontFamily: "'Montserrat Variable', sans-serif" }}>
                {(user?.name || 'П').charAt(0).toUpperCase()}
              </div>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{user?.name || 'Гость'}</span>
            </button>
          </div>
        </div>
      )}

      {/* ──── Main content ──── */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        marginLeft: 0, minHeight: '100vh', width: '100%',
      }} className="md:ml-[210px]">
        <header style={{
          height: 56, background: '#ffffff', borderBottom: '1px solid #eef3f5',
          display: 'none', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 24px', position: 'sticky', top: 0, zIndex: 5,
        }} className="md:flex">
          <div style={{ display: 'flex', gap: 4 }}>
            {(['BCSE', 'MOEX'] as Exchange[]).map((ex) => (
              <button
                key={ex}
                onClick={() => setExchange(ex)}
                style={{
                  padding: '8px 20px', borderRadius: 9999,
                  border: exchange === ex ? '2px solid #004b65' : '2px solid #d6e2e6',
                  background: exchange === ex ? '#004b65' : '#ffffff',
                  color: exchange === ex ? '#ffffff' : '#516c79',
                  fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  fontFamily: "'Onest Variable', Onest, sans-serif",
                  display: 'flex', alignItems: 'center', gap: 8, transition: 'all .15s',
                }}
              >
                {ex === 'BCSE' && (
                  <span style={{
                    width: 20, height: 20, borderRadius: 4,
                    background: exchange === 'BCSE' ? '#ffffff' : '#004b65',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Globe2 size={12} color={exchange === 'BCSE' ? '#004b65' : '#ffffff'} />
                  </span>
                )}
                {ex === 'MOEX' && (
                  <span style={{
                    width: 20, height: 20, borderRadius: 4, background: '#ff0000',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 8, fontWeight: 800, color: '#ffffff',
                    fontFamily: "'Montserrat Variable', sans-serif",
                  }}>MOEX</span>
                )}
                {ex === 'BCSE' ? 'Белорусская биржа (BCSE)' : 'Московская биржа (MOEX)'}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <LanguageToggle />
            <button onClick={() => navigate(ROUTES.chat)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#516c79', padding: 6 }} title="AI-ассистент">
              <Brain size={20} />
            </button>
            {tier === 'free' && (
              <button
                onClick={() => navigate('/subscribe')}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px',
                  borderRadius: 9999, border: '1px solid #004b65', background: '#ffffff',
                  color: '#004b65', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                }}
              >
                <Star size={14} /> {t('nav.subscribe')}
              </button>
            )}
            <button onClick={() => navigate('/alerts')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#516c79', padding: 6, position: 'relative' }}>
              <Bell size={22} />
              <span style={{ position: 'absolute', top: 2, right: 2, width: 10, height: 10, borderRadius: 10, background: '#e03400', border: '2px solid #ffffff' }} />
            </button>
          </div>
        </header>

        <main className="md:pt-0 pt-14" style={{ flex: 1, overflowY: 'auto', paddingBottom: 48 }}>
          <div className="md:px-6 px-4 pb-8">
            <ExchangeHint />
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

function ExchangeHint() {
  const { exchange } = useExchange();
  if (exchange !== 'BCSE') return null;
  return (
    <div style={{
      display: 'none',
      marginBottom: 16,
      gap: 12, alignItems: 'center', background: '#fffaeb', border: '1px solid #fedf89',
      borderRadius: 10, padding: '10px 14px', fontSize: 13, color: '#b54708',
    }} className="md:flex">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#dc6803" strokeWidth="2"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
      <span>Расписание торгов на БВФБ: 10:30–12:20, 13:45–15:45</span>
      <span style={{ marginLeft: 'auto', fontSize: 12, color: '#dc6803', cursor: 'pointer' }}>Подробнее</span>
    </div>
  );
}
