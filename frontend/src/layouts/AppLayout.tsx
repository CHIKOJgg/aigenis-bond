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
        className={`flex items-center gap-3 px-3.5 py-2.5 rounded-[10px] border-none cursor-pointer text-sm font-medium text-left w-full font-aigenis-body transition-all duration-[120ms] ${
          active ? 'bg-white/15 text-white' : 'bg-transparent text-aigenis-300'
        }`}
      >
        {item.icon}
        <span className="flex-1 text-left">{item.label}</span>
        {locked && <span className="text-[10px] text-aigenis-300">PRO</span>}
      </button>
    );
  };

  return (
    <div className="font-aigenis-body bg-aigenis-bg text-aigenis-text min-h-screen flex">
      {/* ──── Desktop sidebar (dark teal) ──── */}
      <aside className="hidden md:flex w-[210px] bg-aigenis-500 flex-col shrink-0 z-10 h-screen fixed">
        <div className="px-4 pb-3.5 pt-4.5 flex items-center justify-between">
          <button onClick={() => navigate('/')} className="bg-transparent border-none cursor-pointer flex items-baseline p-0">
            <span className="font-aigenis-heading text-lg font-extrabold text-white tracking-tight">aigenis</span>
            <span className="text-[13px] font-normal text-aigenis-300 ml-1">invest</span>
          </button>
        </div>

        <nav className="flex-1 px-1.5 flex flex-col gap-0.5 overflow-y-auto">
          {SIDEBAR_MAIN.map(renderNavItem)}
          <div className="mx-3.5 mt-3 mb-1.5 text-[10px] tracking-widest text-aigenis-300 uppercase font-semibold">
            Сервисы
          </div>
          {SIDEBAR_EXTRA.map(renderNavItem)}
        </nav>

        <button
          className="px-3.5 py-3 mx-1.5 mb-2.5 bg-white/10 rounded-xl cursor-pointer flex items-center gap-2.5 text-left"
          onClick={() => navigate('/account')}
        >
          <div className="w-9 h-9 rounded-[10px] bg-white/10 flex items-center justify-center text-aigenis-300 text-sm font-aigenis-heading font-bold">
            {(user?.name || 'П').charAt(0).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-white whitespace-nowrap overflow-hidden text-ellipsis">
              {user?.name || 'Гость'}
            </div>
            <div className="text-[11px] text-aigenis-300">A0418012025</div>
          </div>
        </button>

        <div className="px-3.5 pb-3.5 flex gap-2">
          <div className="bg-aigenis-900 rounded-lg px-2.5 py-1.5 flex items-center gap-1 text-[9px] text-white leading-none">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M3.609 1.814L13.792 12 3.61 22.186a.996.996 0 01-.61-.92V2.734a1 1 0 01.609-.92zm10.89 10.893l2.302 2.302-10.937 6.333 8.635-8.635zm3.199-1.4l2.807 1.626a1 1 0 010 1.734l-2.808 1.626-2.53-2.53 2.53-2.456zM5.864 2.658L16.8 8.99l-2.302 2.302-8.634-8.634z"/></svg>
            <div>
              <div className="text-[7px] opacity-70">GET IT ON</div>
              <div className="text-[10px] font-semibold">Google Play</div>
            </div>
          </div>
          <div className="bg-aigenis-900 rounded-lg px-2.5 py-1.5 flex items-center gap-1 text-[9px] text-white leading-none">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg>
            <div>
              <div className="text-[7px] opacity-70">Download on the</div>
              <div className="text-[10px] font-semibold">App Store</div>
            </div>
          </div>
        </div>
      </aside>

      {/* ──── Mobile top bar ──── */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-4 h-14 bg-aigenis-500 text-white">
        <button onClick={() => setMobileOpen(true)} className="bg-transparent border-none text-white cursor-pointer p-1" aria-label="Открыть меню">
          <Menu size={22} />
        </button>
        <span className="font-aigenis-heading font-extrabold text-base">aigenis invest</span>
        <button onClick={() => navigate('/alerts')} className="bg-transparent border-none text-white cursor-pointer p-1 relative" aria-label="Алерты">
          <Bell size={20} />
          <span className="absolute top-0 right-0 w-2 h-2 rounded-full bg-aigenis-error-600 border-[1.5px] border-aigenis-500" aria-hidden="true" />
        </button>
      </div>

      {/* Mobile menu sheet */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-[60]">
          <div className="fixed inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <div className="fixed left-0 top-0 bottom-0 w-[280px] bg-aigenis-500 p-4 flex flex-col animate-slideInLeft font-aigenis-body">
            <div className="flex items-center justify-between mb-4">
              <span className="font-aigenis-heading font-extrabold text-white text-lg">aigenis invest</span>
              <button onClick={() => setMobileOpen(false)} className="bg-white/10 border-none w-7.5 h-7.5 rounded-lg text-white cursor-pointer flex items-center justify-center" aria-label="Закрыть меню">
                <X size={16} />
              </button>
            </div>
            <nav className="flex-1 flex flex-col gap-0.5 overflow-y-auto">
              {[...SIDEBAR_MAIN, ...SIDEBAR_EXTRA].map((item) => {
                const locked = item.premium && tier === 'free';
                return (
                  <button
                    key={item.path}
                    onClick={() => { handleNav(item); setMobileOpen(false); }}
                    className="flex items-center gap-3 py-3 px-3.5 rounded-[10px] border-none cursor-pointer text-sm font-medium text-left w-full bg-transparent text-aigenis-300"
                  >
                    {item.icon}
                    <span className="flex-1 text-left">{item.label}</span>
                    {locked && <span className="text-[10px] text-aigenis-300">PRO</span>}
                  </button>
                );
              })}
            </nav>
            <button
              onClick={() => { navigate('/account'); setMobileOpen(false); }}
              className="py-3 px-3.5 bg-white/10 rounded-xl text-white border-none cursor-pointer flex items-center gap-2.5"
            >
              <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center font-bold font-aigenis-heading">
                {(user?.name || 'П').charAt(0).toUpperCase()}
              </div>
              <span className="text-[13px] font-semibold">{user?.name || 'Гость'}</span>
            </button>
          </div>
        </div>
      )}

      {/* ──── Main content ──── */}
      <div className="flex-1 flex flex-col md:ml-[210px] min-h-screen w-full">
        <header className="hidden md:flex h-14 bg-white border-b border-aigenis-50 items-center justify-between px-6 sticky top-0 z-5">
          <div className="flex gap-1">
            {(['BCSE', 'MOEX'] as Exchange[]).map((ex) => {
              const active = exchange === ex;
              return (
                <button
                  key={ex}
                  onClick={() => setExchange(ex)}
                  aria-pressed={active}
                  className={`px-5 py-2 rounded-full text-sm font-semibold cursor-pointer font-aigenis-body flex items-center gap-2 transition-all duration-150 ${
                    active
                      ? 'border-2 border-aigenis-500 bg-aigenis-500 text-white'
                      : 'border-2 border-aigenis-border bg-white text-aigenis-text-secondary'
                  }`}
                >
                  {ex === 'BCSE' && (
                    <span className={`w-5 h-5 rounded-[4px] flex items-center justify-center ${active ? 'bg-white' : 'bg-aigenis-500'}`}>
                      <Globe2 size={12} color={active ? '#004b65' : '#ffffff'} />
                    </span>
                  )}
                  {ex === 'MOEX' && (
                    <span className="w-5 h-5 rounded-[4px] bg-[#ff0000] flex items-center justify-center text-[8px] font-extrabold text-white font-aigenis-heading">
                      MOEX
                    </span>
                  )}
                  {ex === 'BCSE' ? 'Белорусская биржа (BCSE)' : 'Московская биржа (MOEX)'}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2">
            <LanguageToggle />
            <button onClick={() => navigate(ROUTES.chat)} className="bg-transparent border-none cursor-pointer text-aigenis-text-secondary p-1.5" title="AI-ассистент" aria-label="AI-ассистент">
              <Brain size={20} />
            </button>
            {tier === 'free' && (
              <button
                onClick={() => navigate('/subscribe')}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-full border border-aigenis-500 bg-white text-aigenis-500 text-[13px] font-semibold cursor-pointer"
              >
                <Star size={14} /> {t('nav.subscribe')}
              </button>
            )}
            <button onClick={() => navigate('/alerts')} className="bg-transparent border-none cursor-pointer text-aigenis-text-secondary p-1.5 relative" aria-label="Алерты">
              <Bell size={22} />
              <span className="absolute top-0.5 right-0.5 w-2.5 h-2.5 rounded-full bg-aigenis-error-600 border-2 border-white" aria-hidden="true" />
            </button>
          </div>
        </header>

        <main className="md:pt-0 pt-14 flex-1 overflow-y-auto pb-12">
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
    <div className="hidden md:flex mb-4 gap-3 items-center bg-aigenis-warning-50 border border-aigenis-warning-500 rounded-[10px] px-3.5 py-2.5 text-[13px] text-aigenis-warning-600">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#dc6803" strokeWidth="2"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
      <span>Расписание торгов на БВФБ: 10:30–12:20, 13:45–15:45</span>
      <span className="ml-auto text-xs text-aigenis-warning-600 cursor-pointer">Подробнее</span>
    </div>
  );
}
