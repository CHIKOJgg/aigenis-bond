import { useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, exportCsv } from './lib/api';
import type {
  Bond, BondScore, Stats, SubscribeInfo, WatchlistItem,
  AnalyticsCurve, AnalyticsRV, AnalyticsCarry, AnalyticsStress, AnalyticsRepo,
  AnalyticsPortfolio, AnalyticsForecast, AnalyticsRecommendation, AnalyticsAlert,
} from './lib/api';
import { AuthProvider, useAuth } from './lib/AuthContext';
import { PaywallProvider, usePaywall } from './lib/PaywallContext';
import { I18nProvider, LanguageToggle, useI18n, type Lang } from './i18n';
import { Modal } from './lib/Modal';
import { PaywallModal } from './PaywallModal';
import { tierLimits } from './lib/tiers';
import { LandingPage } from './LandingPage';
import { LegalPages } from './LegalPages';
import { OnboardingTour, isOnboardingNeeded } from './OnboardingTour';
import { BondFilters, defaultFilters, type BondFiltersState } from './BondFilters';
import { BarChart3, Shield, Banknote, Activity, TrendingUp, Search, Menu, X, AlertTriangle, LineChart, PieChart, Zap, Brain, Bell, Clock, User, LogOut, Lock, Star, ExternalLink, FileText, ShieldCheck, CreditCard, Globe2, Download, GitCompare, Calculator, Check } from 'lucide-react';

const PREMIUM_PAGES = new Set<Page>(['desk', 'portfolio', 'forecast', 'ml', 'alerts']);

type Page = 'dashboard' | 'bonds' | 'scores' | 'desk' | 'forecast' | 'portfolio' | 'ml' | 'alerts' | 'calculator' | 'settings' | 'subscribe';

function trialDaysWord(n: number, lang: Lang): string {
  if (lang === 'en') return n === 1 ? 'day' : 'days';
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'день';
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return 'дня';
  return 'дней';
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <PaywallProvider>
          <AppInner />
        </PaywallProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

function AppInner() {
  const { t, lang } = useI18n();
  const { user, loading, refreshUser } = useAuth();
  const { openPaywall } = usePaywall();
  const [page, setPage] = useState<Page>('dashboard');
  const [mobileMenu, setMobileMenu] = useState(false);
  const [authPage, setAuthPage] = useState<'login' | 'register' | null>(null);
  const [legalPage, setLegalPage] = useState<'terms' | 'privacy' | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(isOnboardingNeeded());
  const [toast, setToast] = useState<string | null>(null);

  // Detect successful YooKassa payment redirect (?success=1) and refresh tier.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('success') === '1') {
      setToast(t('toast.paymentSuccess'));
      window.history.replaceState({}, '', window.location.pathname);
      refreshUser().catch(() => {});
      setTimeout(() => setToast(null), 6000);
    }
  }, [refreshUser]);

  const trialDaysLeft =
    user?.trial_end && new Date(user.trial_end).getTime() > Date.now()
      ? Math.ceil((new Date(user.trial_end).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
      : null;
  const trialExpiring = trialDaysLeft != null && trialDaysLeft <= 3;

  if (showOnboarding) {
    return <OnboardingTour onDone={() => setShowOnboarding(false)} />;
  }

  if (legalPage) {
    return <LegalPages page={legalPage} onBack={() => setLegalPage(null)} />;
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="animate-pulse text-gray-400">{t('common.loading')}</div>
      </div>
    );
  }

  if (!user) {
    if (authPage === 'login') return <LoginPage onRegister={() => setAuthPage('register')} />;
    if (authPage === 'register') return <RegisterPage onSwitch={() => setAuthPage('login')} />;
    return <LandingPage onLogin={() => setAuthPage('login')} onRegister={() => setAuthPage('register')} onTerms={() => setLegalPage('terms')} onPrivacy={() => setLegalPage('privacy')} />;
  }

  const navItems: { id: Page; label: string; icon: React.ReactNode; premium?: boolean }[] = [
    { id: 'dashboard', label: t('nav.dashboard'), icon: <BarChart3 size={16} /> },
    { id: 'bonds', label: t('nav.bonds'), icon: <Banknote size={16} /> },
    { id: 'scores', label: t('nav.scores'), icon: <Shield size={16} /> },
    { id: 'desk', label: t('nav.desk'), icon: <LineChart size={16} />, premium: true },
    { id: 'portfolio', label: t('nav.portfolio'), icon: <PieChart size={16} />, premium: true },
    { id: 'forecast', label: t('nav.forecast'), icon: <TrendingUp size={16} />, premium: true },
    { id: 'ml', label: t('nav.ml'), icon: <Brain size={16} />, premium: true },
    { id: 'alerts', label: t('nav.alerts'), icon: <Bell size={16} />, premium: true },
    { id: 'calculator', label: t('nav.calculator'), icon: <Calculator size={16} /> },
  ];

  const goToPage = (id: Page) => {
    if (PREMIUM_PAGES.has(id) && user?.subscription_tier === 'free') {
      openPaywall(id);
      return;
    }
    setPage(id);
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 bg-gray-900 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-bold flex items-center gap-2">
            <TrendingUp className="text-emerald-400" size={22} />
            <span className="hidden sm:inline">Aigenis Bonds</span>
          </h1>
          <GlobalSearch />
          <nav className="hidden md:flex gap-1 overflow-x-auto">
            {navItems.map(({ id, label, icon, premium }) => {
              const locked = premium && user?.subscription_tier === 'free';
              return (
                <button key={id} onClick={() => goToPage(id)}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm whitespace-nowrap ${page === id ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}>
                  {icon}{label}
                  {locked && <Lock size={12} className="text-amber-400" />}
                </button>
              );
            })}
            {user.subscription_tier === 'free' && (
              <button onClick={() => setPage('subscribe')}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm whitespace-nowrap ${page === 'subscribe' ? 'bg-amber-600 text-white' : 'text-amber-400 hover:text-white hover:bg-amber-600/30'}`}>
                <Star size={16} />{t('nav.subscribe')}
              </button>
            )}
            <button onClick={() => setPage('settings')}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm whitespace-nowrap ${page === 'settings' ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}>
              <User size={16} />{(user.name || '').split(' ')[0]}
            </button>
          </nav>
          <LanguageToggle />
          <button className="md:hidden p-2 text-gray-400" onClick={() => setMobileMenu(!mobileMenu)} aria-label={mobileMenu ? t('nav.menuClose') : t('nav.menuOpen')}>
            {mobileMenu ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {mobileMenu && (
          <div className="md:hidden border-t border-gray-800 px-4 py-2 bg-gray-900">
            {navItems.map(({ id, label, icon, premium }) => {
              const locked = premium && user?.subscription_tier === 'free';
              return (
                <button key={id} onClick={() => { goToPage(id); setMobileMenu(false); }}
                  className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm ${page === id ? 'bg-emerald-600 text-white' : 'text-gray-400'}`}>
                  {icon}{label}
                  {locked && <Lock size={12} className="text-amber-400" />}
                </button>
              );
            })}
          </div>
        )}
      </header>
      <main className="max-w-7xl mx-auto p-4">
        {trialExpiring && (
          <div className="mb-4 flex items-center gap-3 bg-amber-900/30 border border-amber-800 text-amber-200 rounded-xl px-4 py-3 text-sm">
            <Clock size={16} className="shrink-0" />
            <span>
              {t('trial.expiring', { days: trialDaysLeft, daysWord: trialDaysWord(trialDaysLeft, lang) })}
            </span>
            <button onClick={() => setPage('subscribe')} className="ml-auto bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors">
              {t('trial.cta')}
            </button>
          </div>
        )}
        {page === 'dashboard' && <Dashboard onPickCurrency={(cur) => { sessionStorage.setItem('bonds_currency', cur); setPage('bonds'); }} />}
        {page === 'bonds' && <BondsPage />}
        {page === 'scores' && <ScoresPage />}
        {page === 'desk' && <DeskPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'portfolio' && <PortfolioPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'forecast' && <ForecastPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'ml' && <MLPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'alerts' && <AlertsPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'calculator' && <BondCalculator />}
        {page === 'settings' && <SettingsPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'subscribe' && <SubscribePage />}
      </main>
      <PaywallModal onSubscribe={() => setPage('subscribe')} />
      <footer className="border-t border-gray-800 bg-gray-900 mt-8">
        <div className="max-w-7xl mx-auto px-4 py-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-gray-500">
          <span>&copy; {new Date().getFullYear()} Aigenis Parser. {t('common.allRights')}</span>
          <div className="flex items-center gap-4">
            <button onClick={() => setLegalPage('terms')} className="hover:text-gray-300 transition-colors flex items-center gap-1">
              <FileText size={12} /> {t('footer.terms')}
            </button>
            <button onClick={() => setLegalPage('privacy')} className="hover:text-gray-300 transition-colors flex items-center gap-1">
              <ShieldCheck size={12} /> {t('footer.privacy')}
            </button>
          </div>
        </div>
      </footer>
      {toast && (
        <div role="status" aria-live="polite" className="fixed bottom-4 right-4 z-[110] bg-emerald-600 text-white px-4 py-3 rounded-xl shadow-lg text-sm flex items-center gap-2 animate-fadeIn">
          <Check size={16} /> {toast}
        </div>
      )}
    </div>
  );
}

function GlobalSearch() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [all, setAll] = useState<Bond[] | null>(null);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Bond | null>(null);
  const [loadingBond, setLoadingBond] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user || all) return;
    let alive = true;
    const timer = setTimeout(() => {
      api.bonds
        .list({ limit: 1000 })
        .then((b) => { if (alive) setAll(b); })
        .catch(() => { if (alive) setAll(null); });
    }, 1000);
    return () => { alive = false; clearTimeout(timer); };
  }, [user, all]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const results = useMemo(() => {
    if (!all || q.trim().length < 1) return [];
    const n = q.trim().toLowerCase();
    return all
      .filter((b) => b.name.toLowerCase().includes(n) || b.internal_id.toLowerCase().includes(n))
      .slice(0, 8);
  }, [all, q]);

  const openBond = async (id: string) => {
    setLoadingBond(true);
    try {
      const b = await api.bonds.get(id);
      setSelected(b);
    } catch {
      setSelected(null);
    } finally {
      setLoadingBond(false);
      setOpen(false);
      setQ('');
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && results.length > 0) {
      e.preventDefault();
      openBond(results[0].internal_id);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  if (!user) return null;

  return (
    <div className="relative" ref={boxRef}>
      <div className="flex items-center gap-2 bg-gray-800 rounded-lg pl-3 pr-2 py-2 w-full">
        {loadingBond ? (
          <span className="w-4 h-4 border-2 border-gray-600 border-t-emerald-400 rounded-full animate-spin shrink-0" />
        ) : (
          <Search size={16} className="text-gray-500 shrink-0" />
        )}
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={t('search.placeholder')}
          className="bg-transparent outline-none text-sm text-white w-36 md:w-56 placeholder-gray-500"
          aria-label={t('search.aria')}
        />
      </div>
      {open && results.length > 0 && (
        <div className="absolute z-50 mt-1 w-72 md:w-96 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden max-h-[60vh] overflow-y-auto">
          {results.map((b) => (
            <button
              key={b.internal_id}
              onClick={() => openBond(b.internal_id)}
              className="w-full text-left px-4 py-2.5 hover:bg-gray-800 flex items-center justify-between gap-3 border-b border-gray-800 last:border-0"
            >
              <span className="min-w-0">
                <span className="block text-sm text-white truncate">{b.name}</span>
                <span className="block text-xs text-gray-500 font-mono">{b.internal_id}</span>
              </span>
              <span className="shrink-0"><CurrencyBadge currency={b.currency} /></span>
            </button>
          ))}
        </div>
      )}
      {selected && <BondDetailModal bond={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function LoginPage({ onRegister }: { onRegister: () => void }) {
  const { t } = useI18n();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center p-4">
      <div className="absolute top-3 right-3">
        <LanguageToggle />
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 w-full max-w-md">
        <div className="flex items-center gap-2 mb-6">
          <TrendingUp className="text-emerald-400" size={24} />
          <h1 className="text-xl font-bold">Aigenis Bonds</h1>
        </div>
        <h2 className="text-lg font-semibold mb-4">{t('auth.signInTitle')}</h2>
        {error && <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">{t('auth.email')}</label>
            <input value={email} onChange={e => setEmail(e.target.value)} type="email" required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">{t('auth.password')}</label>
            <input value={password} onChange={e => setPassword(e.target.value)} type="password" required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <button type="submit" disabled={submitting}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white py-2 rounded-lg text-sm font-medium transition-colors">
            {submitting ? t('auth.signingIn') : t('auth.signIn')}
          </button>
        </form>
        <p className="text-sm text-gray-400 mt-4 text-center">
          {t('auth.noAccount')}{' '}
          <button onClick={onRegister} className="text-emerald-400 hover:underline">{t('auth.signUp')}</button>
        </p>
      </div>
    </div>
  );
}

function RegisterPage({ onSwitch }: { onSwitch: () => void }) {
  const { t } = useI18n();
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 6) { setError(t('auth.pwMin')); return; }
    setSubmitting(true);
    try {
      await register(email, password, name);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center p-4">
      <div className="absolute top-3 right-3">
        <LanguageToggle />
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 w-full max-w-md">
        <div className="flex items-center gap-2 mb-6">
          <TrendingUp className="text-emerald-400" size={24} />
          <h1 className="text-xl font-bold">Aigenis Bonds</h1>
        </div>
        <h2 className="text-lg font-semibold mb-4">{t('auth.createAccount')}</h2>
        {error && <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">{t('auth.name')}</label>
            <input value={name} onChange={e => setName(e.target.value)} required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">{t('auth.email')}</label>
            <input value={email} onChange={e => setEmail(e.target.value)} type="email" required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">{t('auth.password')}</label>
            <input value={password} onChange={e => setPassword(e.target.value)} type="password" required minLength={6}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <button type="submit" disabled={submitting}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white py-2 rounded-lg text-sm font-medium transition-colors">
            {submitting ? t('auth.creating') : t('auth.createAccount')}
          </button>
        </form>
        <p className="text-sm text-gray-400 mt-4 text-center">
          {t('auth.hasAccount')}{' '}
          <button onClick={onSwitch} className="text-emerald-400 hover:underline">{t('auth.signIn')}</button>
        </p>
      </div>
    </div>
  );
}

function SettingsPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t, lang } = useI18n();
  const { user, logout } = useAuth();
  const isOnTrial = user?.trial_end && new Date(user.trial_end) > new Date();
  const trialDaysLeft = isOnTrial && user?.trial_end ? Math.ceil((new Date(user.trial_end).getTime() - Date.now()) / (1000 * 60 * 60 * 24)) : 0;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">{t('settings.title')}</h2>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 max-w-lg">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><User size={16} className="text-emerald-400" /> {t('settings.profile')}</h3>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between py-1.5 border-b border-gray-800">
            <span className="text-gray-400">{t('settings.name')}</span>
            <span className="text-white font-medium">{user?.name}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-gray-800">
            <span className="text-gray-400">{t('settings.email')}</span>
            <span className="text-white font-medium">{user?.email}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-gray-800">
            <span className="text-gray-400">{t('settings.plan')}</span>
            <span className="text-emerald-400 font-medium capitalize">{user?.subscription_tier}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-gray-800">
            <span className="text-gray-400">{t('settings.role')}</span>
            <span className="text-white font-medium capitalize">{user?.role}</span>
          </div>
          {isOnTrial && (
            <div className="flex justify-between py-1.5 border-b border-gray-800">
              <span className="text-gray-400">{t('settings.trial')}</span>
              <span className="text-amber-400 font-medium">{t('trial.daysLeftShort', { days: trialDaysLeft, daysWord: trialDaysWord(trialDaysLeft, lang) })}</span>
            </div>
          )}
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          {user?.subscription_tier === 'free' && (
            <button onClick={onSubscribe}
              className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              <Star size={16} /> {t('settings.subscribe')}
            </button>
          )}
          <button onClick={logout}
            className="flex items-center gap-2 bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded-lg text-sm transition-colors">
            <LogOut size={16} /> {t('settings.signOut')}
          </button>
        </div>
      </div>
    </div>
  );
}

function Dashboard({ onPickCurrency }: { onPickCurrency?: (cur: string) => void }) {
  const { t } = useI18n();
  const [stats, setStats] = useState<Stats | null>(null);
  const [bonds, setBonds] = useState<Bond[]>([]);
  const [scores, setScores] = useState<BondScore[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.stats().catch(() => null),
      api.bonds.list({ limit: 5 }).catch(() => []),
      api.scores({ limit: 5 }).catch(() => []),
      api.health().catch(() => null),
    ]).then(([s, b, sc, h]) => {
      setStats(s);
      setBonds(b);
      setScores(sc);
      setHealth(h);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">{t('dash.title')}</h2>
        {health && (
          <div className="flex items-center gap-2 text-xs">
            <span className={`w-2 h-2 rounded-full ${health.status === 'ok' ? 'bg-emerald-400' : 'bg-red-400'}`} />
            <span className="text-gray-400">{health.status}</span>
            <span className="text-gray-600">|</span>
            <span className="text-gray-400">{t('dash.db')}: {health.db}</span>
            <Clock size={12} className="text-gray-500" />
            <span className="text-gray-500">{Math.floor(health.uptime_seconds || 0)}s</span>
          </div>
        )}
      </div>

      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Banknote} label={t('dash.totalBonds')} value={stats.total_bonds} color="from-emerald-500 to-emerald-700" />
          <StatCard icon={Activity} label={t('dash.activeBonds')} value={stats.active_bonds} color="from-blue-500 to-blue-700" />
          <StatCard icon={Shield} label={t('dash.topScore')} value={scores[0]?.score?.toFixed(1) || '-'} color="from-purple-500 to-purple-700" />
          {Object.entries(stats.by_currency).slice(0, 1).map(([cur, count]) => (
            <StatCard key={cur} icon={BarChart3} label={t('dash.currencyBonds', { cur })} value={count as number} color="from-amber-500 to-amber-700" />
          ))}
        </div>
      )}

      <CurrencyTracker />

      <MarketsOverview onPick={onPickCurrency} />

      <AlertsWidget />

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2"><Banknote size={16} className="text-emerald-400" /> {t('dash.recent')}</h3>
          <div className="space-y-1">
            {bonds.map(b => <BondRow key={b.internal_id} bond={b} />)}
          </div>
          {bonds.length === 0 && <EmptyState message={t('dash.noBonds')} />}
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2"><Shield size={16} className="text-purple-400" /> {t('dash.topScores')}</h3>
          <div className="space-y-1">
            {scores.map(s => (
              <div key={s.internal_id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                <span className="text-sm text-gray-300 font-mono text-xs">{s.internal_id}</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono text-emerald-400">{s.score.toFixed(2)}</span>
                  {s.tier && <TierBadge tier={s.tier} />}
                </div>
              </div>
            ))}
          </div>
        </div>
        <WatchlistCard />
      </div>
    </div>
  );
}

function CurrencyTracker() {
  const { t } = useI18n();
  const { user } = useAuth();
  const { openPaywall } = usePaywall();
  const limits = tierLimits(user?.subscription_tier);
  const isFree = user?.subscription_tier === 'free';

  const [available, setAvailable] = useState<string[]>(['USD', 'BYN', 'EUR', 'XAU', 'XAG', 'XPT']);
  const [selected, setSelected] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);

  const storageKey = `watched_currencies_${user?.id ?? 'anon'}`;

  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as string[];
        setSelected(parsed.slice(0, Math.max(limits.maxCurrencies, parsed.length)));
      } catch {
        setSelected(limits.maxCurrencies >= 1 ? ['USD'] : []);
      }
    } else {
      setSelected(limits.maxCurrencies >= 1 ? ['USD'] : []);
    }
    setLoaded(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, limits.maxCurrencies]);

  useEffect(() => {
    api.stats()
      .then((s) => {
        const curs = Object.keys(s.by_currency);
        if (curs.length) setAvailable(curs);
      })
      .catch(() => {});
  }, []);

  const persist = (next: string[]) => {
    setSelected(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  };

  const toggle = (cur: string) => {
    if (selected.includes(cur)) {
      persist(selected.filter((c) => c !== cur));
      return;
    }
    if (isFree && selected.length >= limits.maxCurrencies) {
      openPaywall('currencies');
      return;
    }
    persist([...selected, cur]);
  };

  const atLimit = isFree && selected.length >= limits.maxCurrencies;

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Globe2 size={16} className="text-emerald-400" /> {t('tracker.title')}
        </h3>
        {isFree && (
          <span className={`text-xs px-2 py-0.5 rounded border ${atLimit ? 'text-amber-400 bg-amber-900/30 border-amber-800' : 'text-gray-400 bg-gray-800 border-gray-700'}`}>
            {selected.length}/{limits.maxCurrencies}
          </span>
        )}
      </div>
      <p className="text-xs text-gray-500 mb-3">
        {isFree
          ? t('tracker.freeHint')
          : t('tracker.hint')}
      </p>
      <div className="flex flex-wrap gap-2">
        {available.map((cur) => {
          const active = selected.includes(cur);
          const blocked = isFree && !active && atLimit;
          return (
            <button
              key={cur}
              onClick={() => toggle(cur)}
              disabled={loaded && blocked}
              className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${active
                ? 'bg-emerald-600 text-white border-emerald-500'
                : 'bg-gray-800 text-gray-300 border-gray-700 hover:border-gray-600'
                } ${blocked ? 'opacity-40 cursor-not-allowed' : ''}`}
            >
              {cur}
            </button>
          );
        })}
      </div>
      {isFree && atLimit && (
        <button
          onClick={() => openPaywall('currencies')}
          className="mt-3 inline-flex items-center gap-1.5 text-sm text-amber-400 hover:text-amber-300 transition-colors"
        >
          <Lock size={14} /> {t('tracker.unlock')}
        </button>
      )}
    </div>
  );
}

function WatchlistCard() {
  const { t } = useI18n();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.bonds.watchlist()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;
  if (items.length === 0) return null;

  const exportNow = () => {
    exportCsv(
      'watchlist.csv',
      ['Bond ID', 'Name', 'Score'],
      items.map((it) => [it.internal_id, it.name, it.score != null ? it.score.toFixed(2) : '']),
    );
  };

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Star size={16} className="text-amber-400" /> {t('watchlist.title')}
          <span className="text-xs text-gray-500 font-normal">{items.length}</span>
        </h3>
        <button onClick={exportNow}
          className="flex items-center gap-1 text-gray-400 hover:text-white" title={t('action.exportCsv')}>
          <Download size={14} />
        </button>
      </div>
      <div className="space-y-1">
        {items.slice(0, 8).map((it) => (
          <div key={it.internal_id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
            <span className="text-sm text-gray-300 font-mono text-xs truncate">{it.internal_id}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono text-emerald-400">{it.score != null ? it.score.toFixed(1) : '-'}</span>
              {it.score != null && <TierBadge tier={it.score >= 80 ? 'A' : it.score >= 60 ? 'B' : it.score >= 40 ? 'C' : 'D'} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MarketsOverview({ onPick }: { onPick?: (cur: string) => void }) {
  const { t } = useI18n();
  const [tiles, setTiles] = useState<{ currency: string; count: number; avg: number | null }[]>([]);

  useEffect(() => {
    Promise.all([
      api.stats().then((s) => s.by_currency).catch(() => ({}) as Record<string, number>),
      api.bonds.list({ limit: 1000 }).catch(() => [] as Bond[]),
      api.scores({ limit: 1000 }).catch(() => [] as BondScore[]),
    ])
      .then(([byCur, bonds, sc]) => {
        const scoreMap: Record<string, number> = {};
        sc.forEach((s) => { scoreMap[s.internal_id] = s.score; });
        const sums: Record<string, { n: number; sum: number }> = {};
        bonds.forEach((b) => {
          const s = scoreMap[b.internal_id];
          if (s == null) return;
          if (!sums[b.currency]) sums[b.currency] = { n: 0, sum: 0 };
          sums[b.currency].n += 1;
          sums[b.currency].sum += s;
        });
        const rows = Object.entries(byCur as Record<string, number>).map(([cur, count]) => ({
          currency: cur,
          count,
          avg: sums[cur] ? sums[cur].sum / sums[cur].n : null,
        })).sort((a, b) => b.count - a.count);
        setTiles(rows);
      })
      .catch(() => {});
  }, []);

  if (tiles.length === 0) return null;

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <Globe2 size={16} className="text-emerald-400" /> {t('markets.title')}
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {tiles.map((tile) => {
          const avg = tile.avg;
          const tint = avg == null
            ? 'bg-gray-800 border-gray-700'
            : avg >= 70
              ? 'bg-emerald-900/40 border-emerald-800'
              : avg >= 50
                ? 'bg-amber-900/30 border-amber-800'
                : 'bg-red-900/30 border-red-800';
          return (
            <button key={tile.currency} onClick={() => onPick?.(tile.currency)}
              className={`rounded-lg border p-3 text-left transition-colors hover:border-emerald-600 ${tint}`}>
              <div className="flex items-center justify-between">
                <CurrencyBadge currency={tile.currency} />
                <span className="text-xs text-gray-400">{tile.count}</span>
              </div>
              <p className="mt-1 text-sm font-mono">{avg != null ? avg.toFixed(1) : '—'}</p>
              <p className="text-[10px] text-gray-500">{t('dash.avgScore')}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AlertsWidget() {
  const { t } = useI18n();
  const { user } = useAuth();
  const storageKey = `alerts_${user?.id ?? 'anon'}`;

  interface AlertRule {
    id: string;
    scope: 'bond' | 'currency';
    target: string;
    metric: 'ytm' | 'score' | 'price';
    op: '>' | '<';
    value: number;
    enabled: boolean;
  }

  const [rules, setRules] = useState<AlertRule[]>([]);
  const [triggered, setTriggered] = useState<{ rule: AlertRule; bond: Bond; value: number }[]>([]);
  const [form, setForm] = useState<{ scope: 'bond' | 'currency'; target: string; metric: 'ytm' | 'score' | 'price'; op: '>' | '<'; value: string }>({
    scope: 'currency', target: '', metric: 'ytm', op: '>', value: '',
  });

  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) setRules(JSON.parse(saved));
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  const persist = (next: AlertRule[]) => {
    setRules(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  };

  const evaluate = async (rs: AlertRule[]) => {
    if (rs.length === 0) { setTriggered([]); return; }
    try {
      const [bonds, sc] = await Promise.all([
        api.bonds.list({ limit: 1000 }),
        api.scores({ limit: 1000 }).catch(() => [] as BondScore[]),
      ]);
      const scoreMap: Record<string, number> = {};
      sc.forEach((s) => { scoreMap[s.internal_id] = s.score; });
      const out: { rule: AlertRule; bond: Bond; value: number }[] = [];
      for (const r of rs.filter((x) => x.enabled)) {
        const matched = bonds.filter((b) => (r.scope === 'bond' ? b.internal_id === r.target : b.currency === r.target));
        for (const b of matched) {
          const val = r.metric === 'score'
            ? scoreMap[b.internal_id]
            : r.metric === 'ytm'
              ? (b.yield_to_maturity != null ? b.yield_to_maturity * 100 : null)
              : b.price;
          if (val == null) continue;
          const hit = r.op === '>' ? val > r.value : val < r.value;
          if (hit) out.push({ rule: r, bond: b, value: val });
        }
      }
      setTriggered(out);
    } catch {
      setTriggered([]);
    }
  };

  const addRule = () => {
    const v = Number(form.value);
    if (!form.target.trim() || isNaN(v)) return;
    const rule: AlertRule = {
      id: Math.random().toString(36).slice(2),
      scope: form.scope,
      target: form.target.trim().toUpperCase(),
      metric: form.metric,
      op: form.op,
      value: v,
      enabled: true,
    };
    const next = [...rules, rule];
    persist(next);
    setForm((f) => ({ ...f, target: '', value: '' }));
    evaluate(next);
  };

  const removeRule = (id: string) => {
    const next = rules.filter((r) => r.id !== id);
    persist(next);
    evaluate(next);
  };

  useEffect(() => { evaluate(rules); /* eslint-disable-next-line */ }, [rules]);

  const metricLabel: Record<AlertRule['metric'], string> = { ytm: t('alerts.metricYtm'), score: t('alerts.metricScore'), price: t('alerts.metricPrice') };

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <Bell size={16} className="text-emerald-400" /> {t('alerts.title')}
        {triggered.length > 0 && (
          <span className="text-xs bg-red-900 text-red-300 px-2 py-0.5 rounded ml-auto">{t('alerts.triggered', { n: triggered.length })}</span>
        )}
      </h3>

      {triggered.length > 0 && (
        <div className="mb-3 space-y-1">
          {triggered.slice(0, 6).map((tr, i) => (
            <div key={i} className="flex items-center gap-2 text-sm bg-red-900/20 border border-red-800 rounded-lg px-3 py-1.5">
              <span className="font-mono text-xs text-gray-300">{tr.bond.internal_id}</span>
               <span className="text-gray-400">
                 {metricLabel[tr.rule.metric]} {tr.rule.op === '>' ? t('alerts.above') : t('alerts.below')} {tr.rule.value}
               </span>
              <span className="ml-auto font-mono text-red-300">
                {tr.value != null ? tr.value.toFixed(2) : '—'}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-3">
        <select value={form.scope} onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value as 'bond' | 'currency' }))}
          className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-white text-xs">
          <option value="currency">{t('alerts.scopeCurrency')}</option>
          <option value="bond">{t('alerts.scopeBond')}</option>
        </select>
        <input value={form.target} onChange={(e) => setForm((f) => ({ ...f, target: e.target.value }))} placeholder={form.scope === 'bond' ? 'ID' : 'USD'}
          className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-white text-xs" />
        <select value={form.metric} onChange={(e) => setForm((f) => ({ ...f, metric: e.target.value as 'ytm' | 'score' | 'price' }))}
          className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-white text-xs">
          <option value="ytm">YTM %</option>
          <option value="score">{t('alerts.metricScore')}</option>
          <option value="price">{t('alerts.metricPrice')}</option>
        </select>
        <div className="flex gap-1">
          <select value={form.op} onChange={(e) => setForm((f) => ({ ...f, op: e.target.value as '>' | '<' }))}
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-white text-xs">
            <option value=">">&gt;</option>
            <option value="<">&lt;</option>
          </select>
          <input value={form.value} onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))} type="number" step="0.1" placeholder={t('alerts.value')}
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-white text-xs w-full" />
        </div>
          <button onClick={addRule}
            className="bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-2 py-1.5 text-xs transition-colors">{t('alerts.add')}</button>
      </div>

      {rules.length > 0 && (
        <div className="space-y-1">
          {rules.map((r) => (
            <div key={r.id} className="flex items-center justify-between text-sm py-1 border-b border-gray-800 last:border-0">
              <span className="text-gray-300">
                 {r.scope === 'bond' ? t('alerts.scopeBond') : t('alerts.scopeCurrency')} <b className="font-mono">{r.target}</b>: {metricLabel[r.metric]} {r.op === '>' ? '>' : '<'} {r.value}
               </span>
               <button onClick={() => removeRule(r.id)} className="text-gray-500 hover:text-red-400" aria-label={t('alerts.remove')}>
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {rules.length === 0 && <p className="text-xs text-gray-500">{t('alerts.noRules')}</p>}
    </div>
  );
}

function maturityBucket(b: Bond): string | null {
  if (!b.maturity_date) return null;
  const yrs = (new Date(b.maturity_date).getTime() - Date.now()) / (365.25 * 24 * 3600 * 1000);
  if (yrs < 0) return 'expired';
  if (yrs < 1) return '<1y';
  if (yrs < 3) return '1-3y';
  if (yrs < 5) return '3-5y';
  if (yrs < 10) return '5-10y';
  return '>10y';
}

function defaultForPreset(id: string): Partial<BondFiltersState> {
  switch (id) {
    case 'ytm10':
      return { ytm: [null, null] };
    case 'score70':
      return { score: [null, null] };
    case 'active':
      return { statuses: [] };
    case 'short':
      return { maturities: [] };
    case 'fav':
      return { favoritesOnly: false };
    default:
      return {};
  }
}

function BondsPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [allBonds, setAllBonds] = useState<Bond[]>([]);
  const [scoreMap, setScoreMap] = useState<Record<string, number>>({});
  const [filters, setFilters] = useState<BondFiltersState>({ ...defaultFilters });
  const [activePresets, setActivePresets] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<{ key: 'yield_to_maturity' | 'price' | 'coupon_rate' | 'score' | 'name'; dir: 'asc' | 'desc' }>({ key: 'yield_to_maturity', dir: 'desc' });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Bond | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [compareOpen, setCompareOpen] = useState(false);
  const MAX_COMPARE = 4;
  const PAGE_SIZE = 25;

  useEffect(() => {
    const savedCurrency = sessionStorage.getItem('bonds_currency');
    sessionStorage.removeItem('bonds_currency');
    setLoading(true);
    setError(null);
    setPage(1);
    if (savedCurrency) {
      setFilters((f) => ({
        ...f,
        currencies: f.currencies.includes(savedCurrency) ? f.currencies : [...f.currencies, savedCurrency],
      }));
    }
    Promise.all([
      api.bonds.list({ limit: 1000 }),
      api.scores({ limit: 1000 }).catch(() => [] as BondScore[]),
    ])
      .then(([bs, sc]) => {
        setAllBonds(bs);
        const m: Record<string, number> = {};
        sc.forEach((s) => { m[s.internal_id] = s.score; });
        setScoreMap(m);
      })
      .catch(() => setError('Failed to load bonds'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    api.bonds.watchlist()
      .then((items) => setFavorites(new Set(items.map((i) => i.internal_id))))
      .catch(() => {});
  }, [user]);

  const toggleFav = async (id: string) => {
    try {
      if (favorites.has(id)) {
        const r = await api.bonds.removeFromWatchlist(id);
        setFavorites(new Set(r.watchlist));
      } else {
        const r = await api.bonds.addToWatchlist(id);
        setFavorites(new Set(r.watchlist));
      }
    } catch {
      /* ignore */
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < MAX_COMPARE) {
        next.add(id);
      }
      return next;
    });
  };

  const filtered = useMemo(() => {
    const f = filters;
    const q = f.search.trim().toLowerCase();
    const ytmLo = f.ytm[0] != null ? f.ytm[0] / 100 : null;
    const ytmHi = f.ytm[1] != null ? f.ytm[1] / 100 : null;
    const couponLo = f.coupon[0] != null ? f.coupon[0] / 100 : null;
    const couponHi = f.coupon[1] != null ? f.coupon[1] / 100 : null;

    let rows = allBonds.filter((b) => {
      if (q && !(b.name.toLowerCase().includes(q) || b.internal_id.toLowerCase().includes(q))) return false;
      if (f.currencies.length && !f.currencies.includes(b.currency)) return false;
      if (f.statuses.length && !f.statuses.includes(b.status)) return false;
      if (f.favoritesOnly && !favorites.has(b.internal_id)) return false;

      if (b.yield_to_maturity != null) {
        if (ytmLo != null && b.yield_to_maturity < ytmLo) return false;
        if (ytmHi != null && b.yield_to_maturity > ytmHi) return false;
      } else if (ytmLo != null || ytmHi != null) {
        return false;
      }

      if (b.price != null) {
        if (f.price[0] != null && b.price < f.price[0]) return false;
        if (f.price[1] != null && b.price > f.price[1]) return false;
      } else if (f.price[0] != null || f.price[1] != null) {
        return false;
      }

      if (b.coupon_rate != null) {
        if (couponLo != null && b.coupon_rate < couponLo) return false;
        if (couponHi != null && b.coupon_rate > couponHi) return false;
      } else if (couponLo != null || couponHi != null) {
        return false;
      }

      const sc = scoreMap[b.internal_id];
      if (sc != null) {
        if (f.score[0] != null && sc < f.score[0]) return false;
        if (f.score[1] != null && sc > f.score[1]) return false;
      } else if (f.score[0] != null || f.score[1] != null) {
        return false;
      }

      if (f.maturities.length) {
        const bucket = maturityBucket(b);
        if (!bucket || !f.maturities.includes(bucket)) return false;
      }

      return true;
    });

    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      let av: number | string | null;
      let bv: number | string | null;
      if (sort.key === 'score') {
        av = scoreMap[a.internal_id] ?? -Infinity;
        bv = scoreMap[b.internal_id] ?? -Infinity;
      } else if (sort.key === 'name') {
        av = a.name.toLowerCase();
        bv = b.name.toLowerCase();
      } else {
        av = (a as unknown as Record<string, number | null>)[sort.key];
        bv = (b as unknown as Record<string, number | null>)[sort.key];
      }
      if (av == null) av = -Infinity;
      if (bv == null) bv = -Infinity;
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }, [allBonds, filters, sort, scoreMap, favorites]);

  // Presets toggle a single filter dimension on/off (composable — activating
  // one never wipes the rest of the user's filters).
  const togglePreset = (p: { id: string; apply: Partial<BondFiltersState> }) => {
    setActivePresets((prev) => {
      const next = new Set(prev);
      if (next.has(p.id)) {
        next.delete(p.id);
        setFilters((f) => ({ ...f, ...defaultForPreset(p.id) }));
      } else {
        next.add(p.id);
        setFilters((f) => ({ ...f, ...p.apply }));
      }
      return next;
    });
  };

  const presets: { id: string; label: string; apply: Partial<BondFiltersState> }[] = [
    { id: 'ytm10', label: t('bonds.presetYtm'), apply: { ytm: [10, null] } },
    { id: 'score70', label: t('bonds.presetScore'), apply: { score: [70, null] } },
    { id: 'active', label: t('bonds.presetActive'), apply: { statuses: ['active'] } },
    { id: 'short', label: t('bonds.presetShort'), apply: { maturities: ['<1y', '1-3y'] } },
    { id: 'fav', label: t('common.favorites'), apply: { favoritesOnly: true } },
  ];

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const statusOptions = Array.from(new Set(allBonds.map((b) => b.status))).sort();
  const currencyOptions = Array.from(new Set(allBonds.map((b) => b.currency))).sort();

  const pageIds = pageRows.map((b) => b.internal_id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        pageIds.forEach((id) => next.delete(id));
      } else {
        pageIds.forEach((id) => { if (next.size < MAX_COMPARE) next.add(id); });
      }
      return next;
    });
  };

  const exportNow = () => {
    const headers = ['Name', 'ID', 'Currency', 'Price', 'YTM %', 'Coupon %', 'Maturity', 'Status', 'Score'];
    const rows = filtered.map((b) => [
      b.name,
      b.internal_id,
      b.currency,
      b.price != null ? b.price.toFixed(2) : '',
      b.yield_to_maturity != null ? (b.yield_to_maturity * 100).toFixed(2) : '',
      b.coupon_rate != null ? (b.coupon_rate * 100).toFixed(2) : '',
      b.maturity_date ? new Date(b.maturity_date).toLocaleDateString() : '',
      b.status,
      scoreMap[b.internal_id] != null ? scoreMap[b.internal_id].toFixed(2) : '',
    ]);
    exportCsv('bonds.csv', headers, rows);
  };

  const setSortKey = (key: typeof sort.key) => {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  };

  const SortHeader = ({ label, k, className = '' }: { label: string; k: typeof sort.key; className?: string }) => (
    <th
      className={`text-left p-3 cursor-pointer select-none hover:text-white ${className} ${sort.key === k ? 'text-emerald-400' : 'text-gray-400'}`}
      onClick={() => setSortKey(k)}
    >
      {label} {sort.key === k ? (sort.dir === 'asc' ? '▲' : '▼') : ''}
    </th>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">{t('bonds.title')}</h2>
        <button onClick={exportNow} disabled={filtered.length === 0}
          className="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200 px-3 py-2 rounded-lg text-sm transition-colors">
          <Download size={15} /> {t('bonds.csv')}
        </button>
      </div>

      {/* Screener */}
      <BondFilters
        filters={filters}
        onChange={(next) => { setFilters(next); setPage(1); }}
        currencyOptions={currencyOptions}
        statusOptions={statusOptions}
        resultCount={filtered.length}
        totalCount={allBonds.length}
      />

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-gray-500">{t('common.quickFilters')}</span>
        {presets.map((p) => {
          const active = activePresets.has(p.id);
          return (
            <button key={p.id} onClick={() => togglePreset(p)}
              className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                active
                  ? 'bg-emerald-600 border-emerald-500 text-white'
                  : 'bg-gray-800 hover:bg-gray-700 text-gray-200 border-gray-700'
              }`}>
              {p.label}
            </button>
          );
        })}
      </div>

      {loading && <LoadingSkeleton />}
      {error && <ErrorBanner message={error} />}
      {!loading && !error && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left p-3 w-8">
                  <input type="checkbox" checked={allPageSelected} onChange={toggleSelectAll} className="accent-emerald-500" aria-label={t('common.selectAll')} />
                </th>
                 <th className="text-left p-3 w-8 hidden sm:table-cell"></th>
                 <SortHeader label={t('common.name')} k="name" />
                 <th className="text-left p-3 w-8 hidden sm:table-cell">{t('common.id')}</th>
                 <th className="text-left p-3">{t('common.currencyShort')}</th>
                 <SortHeader label={t('common.price')} k="price" className="text-right" />
                 <SortHeader label={t('common.ytm')} k="yield_to_maturity" className="text-right hidden md:table-cell" />
                 <SortHeader label={t('common.coupon')} k="coupon_rate" className="text-right hidden lg:table-cell" />
                 <SortHeader label={t('common.score')} k="score" className="text-right" />
                 <th className="text-left p-3 hidden lg:table-cell">{t('common.maturity')}</th>
                 <th className="text-left p-3">{t('common.status')}</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((b) => (
                <tr key={b.internal_id} onClick={() => setSelected(selected?.internal_id === b.internal_id ? null : b)}
                  className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer transition-colors">
                  <td className="p-3" onClick={(e) => e.stopPropagation()}>
                     <input type="checkbox" checked={selectedIds.has(b.internal_id)} onChange={() => toggleSelect(b.internal_id)} className="accent-emerald-500" aria-label={t('bonds.selectOne', { id: b.internal_id })} />
                  </td>
                  <td className="p-3" onClick={(e) => e.stopPropagation()}>
                     <button onClick={() => toggleFav(b.internal_id)} className="text-gray-500 hover:text-amber-400" title={t('common.addToFavorites')}>
                      <Star size={15} className={favorites.has(b.internal_id) ? 'fill-amber-400 text-amber-400' : ''} />
                    </button>
                  </td>
                  <td className="p-3 text-white font-medium max-w-[200px] truncate">{b.name}</td>
                  <td className="p-3 text-gray-400 font-mono text-xs hidden sm:table-cell">{b.internal_id}</td>
                  <td className="p-3"><CurrencyBadge currency={b.currency} /></td>
                  <td className="p-3 text-right font-mono">{b.price?.toFixed(2) ?? '-'}</td>
                  <td className="p-3 text-right font-mono hidden md:table-cell">{b.yield_to_maturity != null ? `${(b.yield_to_maturity * 100).toFixed(2)}%` : '-'}</td>
                  <td className="p-3 text-right font-mono hidden lg:table-cell">{b.coupon_rate != null ? `${(b.coupon_rate * 100).toFixed(2)}%` : '-'}</td>
                  <td className="p-3 text-right font-mono text-emerald-400">{scoreMap[b.internal_id] != null ? scoreMap[b.internal_id].toFixed(1) : '-'}</td>
                  <td className="p-3 text-gray-400 text-xs hidden lg:table-cell">{b.maturity_date ? new Date(b.maturity_date).toLocaleDateString() : '-'}</td>
                  <td className="p-3">{b.status === 'active' ? <span className="px-2 py-0.5 rounded text-xs bg-green-900 text-green-300">active</span> : <span className="px-2 py-0.5 rounded text-xs bg-gray-800 text-gray-400">{b.status}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && <EmptyState message={t('bonds.empty')} />}
        </div>
      )}

      {/* Pagination */}
      {!loading && !error && totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 text-sm">
           <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
            className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200">{t('common.back')}</button>
           <span className="text-gray-400">{page} / {totalPages}</span>
           <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200">{t('common.next')}</button>
        </div>
      )}

      {selected && (
        <BondDetailModal
          bond={selected}
          isFavorite={favorites.has(selected.internal_id)}
          onToggleFavorite={() => toggleFav(selected.internal_id)}
          onClose={() => setSelected(null)}
        />
      )}

      {selectedIds.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 bg-gray-800 border border-gray-700 rounded-full px-4 py-2 shadow-lg">
           <span className="text-sm text-gray-300">{t('bonds.selected', { n: selectedIds.size, max: MAX_COMPARE })}</span>
           <button onClick={() => setCompareOpen(true)} disabled={selectedIds.size < 2}
             className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white px-3 py-1.5 rounded-full text-sm transition-colors">
             <GitCompare size={15} /> {t('common.compare')}
           </button>
           <button onClick={() => setSelectedIds(new Set())} className="text-gray-400 hover:text-white text-sm px-2">{t('common.clear')}</button>
        </div>
      )}

      {compareOpen && (
        <ComparisonModal
          bonds={allBonds.filter((b) => selectedIds.has(b.internal_id))}
          scoreMap={scoreMap}
          onClose={() => setCompareOpen(false)}
        />
      )}
    </div>
  );
}

function ComparisonModal({ bonds, scoreMap, onClose }: { bonds: Bond[]; scoreMap: Record<string, number>; onClose: () => void }) {
  const { t } = useI18n();
  const metrics: { label: string; get: (b: Bond) => string }[] = [
    { label: t('common.currency'), get: (b) => b.currency },
    { label: t('common.price'), get: (b) => (b.price != null ? b.price.toFixed(2) : '-') },
    { label: t('common.ytm'), get: (b) => (b.yield_to_maturity != null ? `${(b.yield_to_maturity * 100).toFixed(2)}%` : '-') },
    { label: t('common.coupon'), get: (b) => (b.coupon_rate != null ? `${(b.coupon_rate * 100).toFixed(2)}%` : '-') },
    { label: t('common.frequency'), get: (b) => (b.coupon_frequency != null ? `${b.coupon_frequency}x/${t('calc.freqYear')}` : '-') },
    { label: t('common.maturity'), get: (b) => (b.maturity_date ? new Date(b.maturity_date).toLocaleDateString() : '-') },
    { label: t('common.status'), get: (b) => b.status },
    { label: t('common.score'), get: (b) => (scoreMap[b.internal_id] != null ? scoreMap[b.internal_id].toFixed(1) : '-') },
  ];

  return (
    <Modal onClose={onClose} className="max-w-4xl w-full max-h-[85vh] overflow-auto">
      <div className="flex items-center justify-between p-6 pb-2">
        <h3 className="text-lg font-bold" id="comparison-title">{t('bonds.compareTitle', { n: bonds.length })}</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-white p-1" aria-label={t('action.close')}><X size={18} /></button>
      </div>
      <div className="px-6 pb-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3 sticky left-0 bg-gray-900">{t('bonds.metric')}</th>
              {bonds.map((b) => (
                <th key={b.internal_id} className="text-left p-3 min-w-[150px]">
                  <div className="font-semibold text-white">{b.name}</div>
                  <div className="text-xs text-gray-500 font-mono">{b.internal_id}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.label} className="border-b border-gray-800">
                <td className="p-3 text-gray-400 sticky left-0 bg-gray-900">{m.label}</td>
                {bonds.map((b) => (
                  <td key={b.internal_id} className="p-3 font-mono">{m.get(b)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

function BondDetailModal({ bond, isFavorite, onToggleFavorite, onClose }: { bond: Bond; isFavorite?: boolean; onToggleFavorite?: () => void; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <Modal onClose={onClose} className="max-w-lg w-full max-h-[80vh] overflow-y-auto">
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold" id="detail-title">{bond.internal_id}</h3>
          <div className="flex items-center gap-2">
            {onToggleFavorite && (
              <button onClick={onToggleFavorite} className="text-gray-400 hover:text-amber-400 p-1" title={t('common.addToFavorites')} aria-label={t('common.addToFavorites')}>
                <Star size={18} className={isFavorite ? 'fill-amber-400 text-amber-400' : ''} />
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-white p-1" aria-label={t('action.close')}><X size={18} /></button>
          </div>
        </div>
        <dl className="space-y-3 text-sm">
          <DetailRow label={t('common.name')} value={bond.name} />
          <DetailRow label={t('common.currency')} value={bond.currency} />
          <DetailRow label={t('common.issuer')} value={bond.issuer || '-'} />
          <DetailRow label={t('common.price')} value={bond.price != null ? bond.price.toFixed(2) : '-'} />
          <DetailRow label={t('common.ytm')} value={bond.yield_to_maturity != null ? `${(bond.yield_to_maturity * 100).toFixed(2)}%` : '-'} />
          <DetailRow label={t('detail.couponRate')} value={bond.coupon_rate != null ? `${(bond.coupon_rate * 100).toFixed(2)}%` : '-'} />
          <DetailRow label={t('common.frequency')} value={bond.coupon_frequency != null ? `${bond.coupon_frequency}x/year` : '-'} />
          <DetailRow label={t('common.maturity')} value={bond.maturity_date ? new Date(bond.maturity_date).toLocaleDateString() : '-'} />
          <DetailRow label={t('common.status')} value={bond.status} />
          <DetailRow label={t('common.lastUpdated')} value={bond.fetched_at ? new Date(bond.fetched_at).toLocaleString() : '-'} />
        </dl>
      </div>
    </Modal>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1.5 border-b border-gray-800 last:border-0">
      <span className="text-gray-400">{label}</span>
      <span className="text-white font-medium text-right max-w-[60%] truncate">{value}</span>
    </div>
  );
}

function ScoresPage() {
  const { t } = useI18n();
  const [scores, setScores] = useState<BondScore[]>([]);
  const [minScore, setMinScore] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<Bond | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.scores({ min_score: minScore ? Number(minScore) : undefined, limit: 100 })
      .then(setScores)
      .catch(() => setError('Failed to load scores'))
      .finally(() => setLoading(false));
  }, [minScore]);

  const openDetail = async (id: string) => {
    try {
      const b = await api.bonds.get(id);
      setDetail(b);
    } catch {
      /* ignore */
    }
  };

  const exportNow = () => {
    exportCsv(
      'scores.csv',
      ['Bond ID', 'Score', 'Tier'],
      scores.map((s) => [s.internal_id, s.score.toFixed(2), s.tier ?? '']),
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">{t('scores.title')}</h2>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <input value={minScore} onChange={e => setMinScore(e.target.value)} placeholder={t('common.minScore')} type="number" step="0.1"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full sm:w-32" />
            <button onClick={exportNow} disabled={scores.length === 0}
              className="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200 px-3 py-2 rounded-lg text-sm transition-colors">
              <Download size={15} /> {t('bonds.csv')}
            </button>
        </div>
      </div>
      {loading && <LoadingSkeleton />}
      {error && <ErrorBanner message={error} />}
      {!loading && !error && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400">
                <th className="text-left p-3">#</th>
                <th className="text-left p-3">Bond ID</th>
                <th className="text-right p-3">Score</th>
                <th className="text-left p-3">Tier</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s, i) => (
                <tr key={s.internal_id} onClick={() => openDetail(s.internal_id)}
                  className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer transition-colors">
                  <td className="p-3 text-gray-500 text-xs">{i + 1}</td>
                  <td className="p-3 font-mono text-xs text-gray-300">{s.internal_id}</td>
                  <td className="p-3 text-right font-mono text-emerald-400">{s.score.toFixed(2)}</td>
                  <td className="p-3"><TierBadge tier={s.tier} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {scores.length === 0 && <EmptyState message={t('scores.empty')} />}
        </div>
      )}
      {detail && <BondDetailModal bond={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function DeskPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<'curve' | 'rv' | 'carry' | 'repo' | 'stress'>('curve');

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">{t('desk.title')}</h2>
      <div className="flex gap-2 flex-wrap">
        {(['curve', 'rv', 'carry', 'repo', 'stress'] as const).map(tt => (
          <button key={tt} onClick={() => setTab(tt)}
            className={`px-4 py-2 rounded-lg text-sm capitalize ${tab === tt ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            {tt === 'curve' ? t('desk.tabCurve') : tt === 'rv' ? t('desk.tabRv') : tt === 'carry' ? t('desk.tabCarry') : tt === 'repo' ? t('desk.tabRepo') : t('desk.tabStress')}
          </button>
        ))}
      </div>
      {tab === 'curve' && <DeskCurve onSubscribe={onSubscribe} />}
      {tab === 'rv' && <DeskRV onSubscribe={onSubscribe} />}
      {tab === 'carry' && <DeskCarry onSubscribe={onSubscribe} />}
      {tab === 'repo' && <DeskRepo onSubscribe={onSubscribe} />}
      {tab === 'stress' && <DeskStress onSubscribe={onSubscribe} />}
    </div>
  );
}

function YieldCurveChart({ points, color = '#34d399' }: { points: { tenor: string; years: number; rate_pct: number }[]; color?: string }) {
  const { t } = useI18n();
  const data = points
    .filter((p) => p.years > 0 && p.rate_pct != null)
    .slice()
    .sort((a, b) => a.years - b.years);
  if (data.length < 2) {
    return <p className="text-xs text-gray-500">{t('desk.emptyYtm')}</p>;
  }
  const W = 320, H = 160, pad = 30;
  const xs = data.map((d) => d.years);
  const ys = data.map((d) => d.rate_pct);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  const sx = (x: number) => pad + ((x - xMin) / xRange) * (W - pad * 2);
  const sy = (y: number) => H - pad - ((y - yMin) / yRange) * (H - pad * 2);
  const path = data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${sx(d.years).toFixed(1)} ${sy(d.rate_pct).toFixed(1)}`).join(' ');
  const area = `${path} L ${sx(xMax).toFixed(1)} ${H - pad} L ${sx(xMin).toFixed(1)} ${H - pad} Z`;
  const yTicks = [yMin, (yMin + yMax) / 2, yMax];
  const xTicks = [xMin, (xMin + xMax) / 2, xMax];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-40" role="img" aria-label={t('chart.yieldCurve')}>
      {yTicks.map((t, i) => (
        <g key={`y${i}`}>
          <line x1={pad} y1={sy(t)} x2={W - pad} y2={sy(t)} stroke="#1f2937" strokeWidth={1} />
          <text x={4} y={sy(t) + 3} fill="#6b7280" fontSize={9}>{t.toFixed(1)}%</text>
        </g>
      ))}
      {xTicks.map((t, i) => (
        <text key={`x${i}`} x={sx(t)} y={H - 8} fill="#6b7280" fontSize={9} textAnchor="middle">{t.toFixed(1)}y</text>
      ))}
      <path d={area} fill={color} fillOpacity={0.12} />
      <path d={path} fill="none" stroke={color} strokeWidth={2} />
      {data.map((d, i) => (
        <circle key={i} cx={sx(d.years)} cy={sy(d.rate_pct)} r={2.5} fill={color} />
      ))}
    </svg>
  );
}

function MiniBarChart({ data, formatValue }: { data: { label: string; value: number }[]; formatValue?: (v: number) => string }) {
  if (data.length === 0) return null;
  const max = Math.max(...data.map((d) => Math.abs(d.value)), 0.0001);
  return (
    <div className="space-y-1.5">
      {data.map((d, i) => {
        const pct = Math.min(100, (Math.abs(d.value) / max) * 100);
        const positive = d.value >= 0;
        return (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="w-28 shrink-0 truncate text-gray-400 font-mono">{d.label}</span>
            <div className="flex-1 bg-gray-800 rounded h-3 relative overflow-hidden">
              <div className={`h-3 rounded ${positive ? 'bg-emerald-500' : 'bg-red-500'}`} style={{ width: `${pct}%` }} />
            </div>
            <span className="w-16 shrink-0 text-right font-mono">{formatValue ? formatValue(d.value) : d.value.toFixed(2)}</span>
          </div>
        );
      })}
    </div>
  );
}

function DeskCurve({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data: curves, loading, error, locked } = useGated<AnalyticsCurve[]>(() => api.analytics.curve());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {(curves ?? []).map(c => (
        <div key={c.currency} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <LineChart size={16} className="text-emerald-400" /> {c.currency} Curve
            <span className="text-xs text-gray-500 font-normal ml-auto">{t('desk.slope')} {c.slope.toFixed(2)}</span>
          </h3>
          <YieldCurveChart points={c.points} />
          <div className="space-y-1 mt-2">
            {c.points.filter(p => p.years > 0).slice(0, 15).map((p, i) => (
              <div key={i} className="flex justify-between text-sm py-1 border-b border-gray-800/50">
                <span className="text-gray-400 font-mono text-xs">{p.tenor}</span>
                <span className="text-emerald-400 font-mono">{p.rate_pct.toFixed(2)}%</span>
              </div>
            ))}
          </div>
        </div>
      ))}
      {(curves ?? []).length === 0 && <EmptyState message={t('desk.curveEmpty')} className="col-span-full" />}
    </div>
  );
}

function DeskRV({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data: signals, loading, error, locked } = useGated<AnalyticsRV[]>(() => api.analytics.rv());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = signals ?? [];
  const chart = rows
    .filter((s) => s.z_score != null)
    .slice()
    .sort((a, b) => Math.abs(b.z_score!) - Math.abs(a.z_score!))
    .slice(0, 12)
    .map((s) => ({ label: s.internal_id, value: s.z_score! }));
  return (
    <div className="space-y-4">
      {chart.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-sm font-semibold mb-3 text-gray-300">{t('desk.rvTitle')}</h3>
          <MiniBarChart data={chart} />
        </div>
      )}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">{t('common.id')}</th>
              <th className="text-right p-3">{t('desk.rvSpread')}</th>
              <th className="text-right p-3">{t('desk.rvZscore')}</th>
              <th className="text-left p-3">{t('desk.rvSignal')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 40).map((s, i) => (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="p-3 font-mono text-xs text-gray-300">{s.internal_id}</td>
                <td className="p-3 text-right font-mono">{s.spread_pct != null ? `${s.spread_pct.toFixed(2)}%` : '-'}</td>
                <td className="p-3 text-right font-mono">{s.z_score != null ? s.z_score.toFixed(2) : '-'}</td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${s.side === 'buy' ? 'bg-green-900 text-green-300' : s.side === 'sell' ? 'bg-red-900 text-red-300' : 'bg-gray-800 text-gray-400'}`}>
                    {s.side.toUpperCase()}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState message={t('desk.rvEmpty')} />}
      </div>
    </div>
  );
}

function DeskCarry({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const [funding, setFunding] = useState('5.0');
  const { data: trades, loading, error, locked } = useGated<AnalyticsCarry[]>(
    () => api.analytics.carry(parseFloat(funding) || 5), [funding]
  );

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = trades ?? [];
  const chart = rows
    .slice()
    .sort((a, b) => Math.abs(b.expected_pnl_pct) - Math.abs(a.expected_pnl_pct))
    .slice(0, 12)
    .map((t) => ({ label: t.internal_id, value: t.expected_pnl_pct }));
  return (
    <div className="space-y-4">
      {chart.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-sm font-semibold mb-3 text-gray-300">{t('desk.carryTitle')}</h3>
          <MiniBarChart data={chart} formatValue={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}%`} />
        </div>
      )}
      <div className="flex items-center gap-3">
        <label className="text-sm text-gray-400">{t('desk.fundingRate')}</label>
        <input value={funding} onChange={e => setFunding(e.target.value)} type="number" step="0.1" className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-sm w-24" />
        <span className="text-sm text-gray-500">%</span>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">{t('common.id')}</th>
              <th className="text-right p-3">{t('common.coupon')}</th>
              <th className="text-right p-3">{t('desk.carryRolldown')}</th>
              <th className="text-right p-3">{t('desk.carryPnl')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 30).map((t, i) => (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="p-3 font-mono text-xs text-gray-300">{t.internal_id}</td>
                <td className="p-3 text-right font-mono">{t.coupon_pct.toFixed(2)}%</td>
                <td className="p-3 text-right font-mono">{t.rolldown_bps.toFixed(1)}bp</td>
                <td className={`p-3 text-right font-mono ${t.expected_pnl_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>{t.expected_pnl_pct > 0 ? '+' : ''}{t.expected_pnl_pct.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState message={t('desk.carryEmpty')} />}
      </div>
    </div>
  );
}

function DeskRepo({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const [bondId, setBondId] = useState('');
  const [notional, setNotional] = useState('1000');
  const [tenor, setTenor] = useState('30');
  const [result, setResult] = useState<AnalyticsRepo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);

  const calculate = async () => {
    if (!bondId) return;
    setBusy(true); setError(null); setLocked(false);
    try {
      const r = await api.analytics.repo({ bond_id: bondId, notional: parseFloat(notional), tenor_days: parseInt(tenor) });
      setResult(r);
    } catch (e: unknown) {
      setResult(null);
      if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
      else setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setBusy(false);
    }
  };

  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;

  return (
    <div className="space-y-4">
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 max-w-md">
        <h3 className="text-lg font-semibold mb-4">{t('desk.repoCalc')}</h3>
        <div className="space-y-3">
          <InputField label={t('desk.repoBondId')} value={bondId} onChange={setBondId} placeholder="OP-51" />
          <InputField label={t('desk.repoNotional')} value={notional} onChange={setNotional} type="number" />
          <InputField label={t('desk.repoTenor')} value={tenor} onChange={setTenor} type="number" />
          <button onClick={calculate} disabled={busy} className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white py-2 rounded-lg text-sm font-medium transition-colors">{busy ? t('desk.repoCalculating') : t('desk.repoCalculate')}</button>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      {result && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 max-w-md">
          <h3 className="text-lg font-semibold mb-3">{t('desk.repoResults')}</h3>
          <div className="space-y-2 text-sm">
            <DetailRow label={t('common.bond')} value={result.internal_id} />
            <DetailRow label={t('desk.repoHaircut')} value={`${result.haircut_pct.toFixed(2)}%`} />
            <DetailRow label={t('desk.repoRate')} value={`${result.repo_rate_pct.toFixed(2)}%`} />
            <DetailRow label={t('desk.repoTenorShort')} value={`${result.tenor_days}d`} />
            <DetailRow label={t('desk.repoCashLent')} value={result.cash_lent.toFixed(2)} />
            <DetailRow label={t('desk.repoCollateral')} value={result.collateral_value.toFixed(2)} />
            <DetailRow label={t('desk.repoAccrued')} value={result.accrued_interest.toFixed(4)} />
          </div>
        </div>
      )}
    </div>
  );
}

function InputField({ label, value, onChange, placeholder, type = 'text' }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <div>
      <label className="text-sm text-gray-400 block mb-1">{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} type={type}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
    </div>
  );
}

function DeskStress({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data, loading, error, locked } = useGated<AnalyticsStress[]>(() => api.analytics.stress());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const results = data ?? [];
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold flex items-center gap-2"><Zap size={16} className="text-amber-400" /> {t('desk.stressTitle')}</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {results.map(r => (
          <div key={r.scenario} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
            <h4 className="font-semibold mb-2 capitalize">{r.scenario.replace(/_/g, ' ')}</h4>
            <div className="space-y-1 text-sm">
              <p className={`text-2xl font-bold ${r.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{r.pnl_pct >= 0 ? '+' : ''}{r.pnl_pct.toFixed(2)}%</p>
              <p className="text-gray-400">{t('desk.stressPnl')} {r.pnl >= 0 ? '+' : ''}{r.pnl.toFixed(0)}</p>
              <p className="text-gray-500 text-xs">{r.kind}</p>
            </div>
          </div>
        ))}
      </div>
      {results.length === 0 && <EmptyState message={t('desk.stressEmpty')} />}
    </div>
  );
}

function PortfolioPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data: alloc, loading, error, locked } = useGated<AnalyticsPortfolio>(() => api.analytics.portfolio());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;
  if (!alloc) return <EmptyState message={t('portfolio.empty')} />;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">{t('nav.portfolio')}</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3">{t('portfolio.metrics')}</h3>
          <div className="space-y-3">
            <MetricRow label={t('portfolio.strategy')} value={alloc.strategy} />
            <MetricRow label={t('portfolio.expReturn')} value={`${alloc.expected_return.toFixed(2)}%`} color="text-emerald-400" />
            <MetricRow label={t('portfolio.sharpe')} value={alloc.sharpe.toFixed(2)} color="text-blue-400" />
            <MetricRow label={t('portfolio.sortino')} value={alloc.sortino.toFixed(2)} color="text-blue-400" />
            <MetricRow label={t('portfolio.maxDrawdown')} value={`${alloc.max_drawdown.toFixed(1)}%`} color="text-red-400" />
            <MetricRow label={t('portfolio.var')} value={`${alloc.var_95.toFixed(1)}%`} color="text-red-400" />
          </div>
        </div>
        <div className="lg:col-span-2 bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <h3 className="text-lg font-semibold p-4 pb-2">{t('portfolio.forecast')}</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400">
                <th className="text-left p-3">{t('portfolio.horizon')}</th>
                <th className="text-right p-3">{t('portfolio.pessimistic')}</th>
                <th className="text-right p-3">{t('portfolio.expected')}</th>
                <th className="text-right p-3">{t('portfolio.optimistic')}</th>
              </tr>
            </thead>
            <tbody>
              {alloc.forecast.map((f, i) => (
                <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                  <td className="p-3 font-semibold">{f.horizon_years}Y</td>
                  <td className="p-3 text-right text-red-400 font-mono">{Math.round(f.pessimistic_capital).toLocaleString()}</td>
                  <td className="p-3 text-right text-emerald-400 font-mono font-semibold">{Math.round(f.expected_capital).toLocaleString()}</td>
                  <td className="p-3 text-right text-blue-400 font-mono">{Math.round(f.optimistic_capital).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function MetricRow({ label, value, color = 'text-white' }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={`text-sm font-semibold ${color}`}>{value}</span>
    </div>
  );
}

function ForecastPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data: horizons, loading, error, locked } = useGated<AnalyticsForecast[]>(() => api.analytics.forecast());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = horizons ?? [];
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">{t('portfolio.forecast')}</h2>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">{t('portfolio.horizon')}</th>
              <th className="text-right p-3">{t('portfolio.pessimistic')}</th>
              <th className="text-right p-3">{t('portfolio.expected')}</th>
              <th className="text-right p-3">{t('portfolio.optimistic')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h, i) => (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="p-3 font-semibold">{h.horizon_years} Year{h.horizon_years > 1 ? 's' : ''}</td>
                <td className="p-3 text-right text-red-400 font-mono">{Math.round(h.pessimistic_capital).toLocaleString()}</td>
                <td className="p-3 text-right text-emerald-400 font-mono font-semibold">{Math.round(h.expected_capital).toLocaleString()}</td>
                <td className="p-3 text-right text-blue-400 font-mono">{Math.round(h.optimistic_capital).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState message={t('forecast.empty')} />}
      </div>
    </div>
  );
}

function MLPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data, loading, error, locked } = useGated<AnalyticsRecommendation[]>(() => api.analytics.recommendations(20));

  const decisionColor = (d: string) => {
    switch (d) {
      case 'buy': return 'bg-emerald-900 text-emerald-300';
      case 'hold': return 'bg-blue-900 text-blue-300';
      case 'wait': return 'bg-amber-900 text-amber-300';
      case 'avoid': return 'bg-red-900 text-red-300';
      default: return 'bg-gray-800 text-gray-400';
    }
  };

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const predictions = data ?? [];
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">{t('ml.title')}</h2>
      <p className="text-sm text-gray-400">{t('ml.subtitle')}</p>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">#</th>
              <th className="text-left p-3">{t('common.bond')}</th>
              <th className="text-left p-3">{t('ml.decision')}</th>
              <th className="text-right p-3">{t('common.score')}</th>
              <th className="text-right p-3">{t('ml.predReturn')}</th>
              <th className="text-right p-3">{t('ml.confidence')}</th>
            </tr>
          </thead>
          <tbody>
            {predictions.map((p) => (
              <tr key={p.rank} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="p-3 text-gray-500 text-xs">{p.rank}</td>
                <td className="p-3"><span className="text-white text-sm">{p.name}</span><span className="block text-xs text-gray-500 font-mono">{p.internal_id}</span></td>
                <td className="p-3"><span className={`px-2 py-0.5 rounded text-xs font-medium ${decisionColor(p.decision)}`}>{p.decision.toUpperCase()}</span></td>
                <td className="p-3 text-right font-mono text-emerald-400">{p.score != null ? p.score.toFixed(1) : '-'}</td>
                <td className="p-3 text-right font-mono">{p.predicted_return_pct != null ? `${p.predicted_return_pct.toFixed(2)}%` : '-'}</td>
                <td className="p-3 text-right font-mono">{(p.confidence * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {predictions.length === 0 && <EmptyState message={t('ml.empty')} />}
      </div>
    </div>
  );
}

function AlertsPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data, loading, error, locked } = useGated<AnalyticsAlert[]>(() => api.analytics.alerts(20));

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const alerts = data ?? [];
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">{t('nav.alerts')}</h2>
      {alerts.length > 0 ? (
        <div className="space-y-3">
          {alerts.map((a, i) => (
            <div key={i} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-start gap-3">
                <Bell size={16} className="text-amber-400 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-sm">{a.title}</h4>
                  <p className="text-sm text-gray-400 mt-1">{a.message}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : <EmptyState message={t('alerts.pageEmpty')} />}
    </div>
  );
}

function useGated<T>(fetcher: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  // The dependency array is supplied by the caller via `deps`; `fetcher` is
  // intentionally excluded so callers control re-fetch behaviour.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setLoading(true); setError(null); setLocked(false);
    fetcher()
      .then(d => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (!alive || controller.signal.aborted) return;
        if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
        else setError(e instanceof Error ? e.message : 'Failed to load');
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; controller.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, loading, error, locked };
}

function UpgradePrompt({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="bg-gradient-to-br from-amber-900/30 to-gray-900 border border-amber-800/50 rounded-xl p-8 text-center max-w-lg mx-auto">
      <div className="w-14 h-14 bg-amber-600/20 rounded-full flex items-center justify-center mx-auto mb-4">
        <Lock size={26} className="text-amber-400" />
      </div>
      <h3 className="text-lg font-bold mb-2">{t('upgrade.title')}</h3>
      <p className="text-sm text-gray-400 mb-5">
        {t('upgrade.desc')}
      </p>
      {onSubscribe && (
        <button onClick={onSubscribe}
          className="inline-flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors">
          <Star size={16} /> {t('upgrade.cta')}
        </button>
      )}
    </div>
  );
}

function SubscribePage() {
  const { t, lang } = useI18n();
  const [info, setInfo] = useState<SubscribeInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  useEffect(() => {
    api.subscribeInfo().then(setInfo).catch(() => setInfo(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;

  const isPaid = user && user.subscription_tier !== 'free';
  const isOnTrial = user?.trial_end && new Date(user.trial_end) > new Date();
  const trialDaysLeft = isOnTrial && user?.trial_end ? Math.ceil((new Date(user.trial_end).getTime() - Date.now()) / (1000 * 60 * 60 * 24)) : 0;

  const [payError, setPayError] = useState<string | null>(null);

  const handleYooKassaPayment = async (plan: string) => {
    try {
      setPayError(null);
      const base = window.location.origin;
      const result = await api.billing.createPayment(plan, `${base}/subscribe?success=1`, `${base}/subscribe`);
      if (result.confirmation_url) window.location.href = result.confirmation_url;
    } catch (e: unknown) {
      setPayError(e instanceof Error ? e.message : t('payment.error'));
    }
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="text-center">
        <div className="w-14 h-14 bg-amber-600/20 rounded-full flex items-center justify-center mx-auto mb-3">
          <Star size={26} className="text-amber-400" />
        </div>
        <h2 className="text-2xl font-bold">{t('subscribe.title')}</h2>
        <p className="text-sm text-gray-400 mt-2">
          {t('subscribe.desc')}
        </p>
        {isOnTrial && (
          <p className="mt-3 inline-block bg-blue-900/40 border border-blue-800 text-blue-300 text-sm px-3 py-1.5 rounded-lg">
            {t('trial.daysLeftFull', { days: trialDaysLeft, daysWord: trialDaysWord(trialDaysLeft, lang) })}
          </p>
        )}
        {payError && <ErrorBanner message={payError} />}
        {isPaid && !isOnTrial && (
          <p className="mt-3 inline-block bg-emerald-900/40 border border-emerald-800 text-emerald-300 text-sm px-3 py-1.5 rounded-lg">
            {t('subscribe.currentTier', { tier: user!.subscription_tier })}
          </p>
        )}
      </div>

      {/* YooKassa — карты, СБП, Apple Pay, Google Pay */}
      {info?.yookassa_configured && info.yookassa_plans.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <CreditCard size={18} className="text-blue-400" /> {t('subscribe.cardTitle')}
          </h3>
          <p className="text-sm text-gray-500 mb-3">{t('subscribe.cardHint')}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {info.yookassa_plans.map(p => (
              <div key={p.tier} className="bg-gray-900 rounded-xl border border-gray-800 p-5 flex flex-col">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-lg font-bold">{p.name}</h3>
                  <span className="text-emerald-400 font-semibold">{p.price} {p.currency}/{p.interval}</span>
                </div>
                <p className="text-sm text-gray-400 flex-1">
                  {p.tier === 'pro' ? t('subscribe.proDesc') : t('subscribe.entDesc')}
                </p>
                <button onClick={() => handleYooKassaPayment(p.tier)}
                  className="mt-4 w-full bg-blue-600 hover:bg-blue-500 text-white py-2 rounded-lg text-sm font-medium transition-colors">
                  {t('subscribe.payCard')}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Telegram Stars Plans */}
      <div>
        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Star size={18} className="text-amber-400" /> Telegram Stars
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {(info?.plans ?? []).map(p => (
            <div key={p.tier} className="bg-gray-900 rounded-xl border border-gray-800 p-5 flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-lg font-bold">{p.name}</h3>
                <span className="flex items-center gap-1 text-amber-400 font-semibold"><Star size={15} />{p.stars}</span>
              </div>
              <p className="text-sm text-gray-400 flex-1">{p.blurb}</p>
              <p className="text-xs text-gray-500 mt-3">{t('subscribe.duration', { days: p.duration_days })}</p>
            </div>
          ))}
        </div>

        {info?.deep_link ? (
          <a href={info.deep_link} target="_blank" rel="noopener noreferrer"
            className="mt-4 flex items-center justify-center gap-2 bg-amber-600 hover:bg-amber-500 text-white py-3 rounded-xl text-sm font-medium transition-colors">
            <ExternalLink size={16} /> {t('subscribe.inBot')}
          </a>
        ) : (
          <p className="mt-4 text-center text-sm text-gray-500">
            {t('subscribe.openBot')}
          </p>
        )}
      </div>
    </div>
  );
}

function BondCalculator() {
  const { t } = useI18n();
  const [face, setFace] = useState('100');
  const [coupon, setCoupon] = useState('8');
  const [freq, setFreq] = useState(2);
  const [ytm, setYtm] = useState('9');
  const [years, setYears] = useState('5');
  const [accruedDays, setAccruedDays] = useState('0');
  const [periodDays, setPeriodDays] = useState('182');

  const result = useMemo(() => {
    const F = Number(face);
    const c = Number(coupon) / 100;
    const y = Number(ytm) / 100;
    const n = Number(years);
    const f = freq;
    if (!F || isNaN(c) || isNaN(y) || !n || !f) return null;
    const periods = Math.round(n * f);
    if (periods <= 0) return null;
    const perY = y / f;
    const cf = (F * c) / f;
    let clean = 0;
    for (let k = 1; k <= periods; k++) {
      const flow = k === periods ? cf + F : cf;
      clean += flow / Math.pow(1 + perY, k);
    }
    const pd = Number(periodDays) || 1;
    const accrued = (F * c) / f * (Number(accruedDays) / pd);
    const dirty = clean + accrued;
    const currentYield = cf * f / clean;
    return { clean, dirty, accrued, currentYield };
  }, [face, coupon, freq, ytm, years, accruedDays, periodDays]);

  const numField = (label: string, value: string, onChange: (v: string) => void, step = '1', type = 'number') => (
    <div>
      <label className="text-xs text-gray-400 block mb-1">{label}</label>
      <input value={value} onChange={(e) => onChange(e.target.value)} type={type} step={step}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
    </div>
  );

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center gap-2">
        <Calculator size={22} className="text-emerald-400" />
        <h2 className="text-2xl font-bold">{t('calc.title')}</h2>
      </div>
      <p className="text-sm text-gray-400">{t('calc.desc')}</p>

      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 grid grid-cols-2 lg:grid-cols-3 gap-4">
        {numField(t('calc.face'), face, setFace)}
        {numField(t('calc.coupon'), coupon, setCoupon, '0.1')}
        <div>
          <label className="text-xs text-gray-400 block mb-1">{t('calc.payments')}</label>
          <select value={freq} onChange={(e) => setFreq(Number(e.target.value))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
            <option value={1}>1 ({t('calc.freqYear')})</option>
            <option value={2}>2 ({t('calc.freqHalf')})</option>
            <option value={4}>4 ({t('calc.freqQuarter')})</option>
            <option value={12}>12 ({t('calc.freqMonth')})</option>
          </select>
        </div>
        {numField(t('calc.ytm'), ytm, setYtm, '0.1')}
        {numField(t('calc.years'), years, setYears, '0.5')}
        {numField(t('calc.accruedDays'), accruedDays, setAccruedDays)}
        {numField(t('calc.periodDays'), periodDays, setPeriodDays)}
      </div>

      {result && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-400">{t('calc.cleanPrice')}</p>
            <p className="text-xl font-bold text-emerald-400">{result.clean.toFixed(2)}</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-400">{t('calc.accrued')}</p>
            <p className="text-xl font-bold text-amber-400">{result.accrued.toFixed(2)}</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-400">{t('calc.dirtyPrice')}</p>
            <p className="text-xl font-bold text-white">{result.dirty.toFixed(2)}</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-xs text-gray-400">{t('calc.currentYield')}</p>
            <p className="text-xl font-bold text-blue-400">{(result.currentYield * 100).toFixed(2)}%</p>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: { icon: any; label: string; value: string | number; color: string }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className={`w-10 h-10 bg-gradient-to-br ${color} rounded-lg flex items-center justify-center mb-3`}>
        <Icon size={20} className="text-white" />
      </div>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-sm text-gray-400">{label}</p>
    </div>
  );
}

function BondRow({ bond }: { bond: Bond }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-white truncate">{bond.name}</p>
        <p className="text-xs text-gray-500">{bond.internal_id} · {bond.currency}</p>
      </div>
      <div className="text-right ml-4">
        <p className="text-sm font-mono">{bond.price != null ? bond.price.toFixed(2) : '-'}</p>
        <p className="text-xs text-gray-400">{bond.status}</p>
      </div>
    </div>
  );
}

function CurrencyBadge({ currency }: { currency: string }) {
  const colors: Record<string, string> = { USD: 'bg-blue-900 text-blue-300', BYN: 'bg-green-900 text-green-300', EUR: 'bg-purple-900 text-purple-300', XAU: 'bg-amber-900 text-amber-300', XAG: 'bg-gray-700 text-gray-300', XPT: 'bg-slate-700 text-slate-300' };
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[currency] || 'bg-gray-800 text-gray-400'}`}>{currency}</span>;
}

function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return null;
  const colors: Record<string, string> = { A: 'bg-emerald-900 text-emerald-300', B: 'bg-blue-900 text-blue-300', C: 'bg-amber-900 text-amber-300', D: 'bg-red-900 text-red-300' };
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[tier] || 'bg-gray-800 text-gray-400'}`}>{tier}</span>;
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => <div key={i} className="bg-gray-800 rounded-xl h-24" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-800 rounded-xl h-64" />
        <div className="bg-gray-800 rounded-xl h-64" />
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 bg-red-900/30 border border-red-800 rounded-xl p-4">
      <AlertTriangle size={20} className="text-red-400 shrink-0" />
      <p className="text-sm text-red-300">{message}</p>
    </div>
  );
}

function EmptyState({ message, className = '' }: { message: string; className?: string }) {
  return <p className={`text-gray-500 text-sm text-center py-8 ${className}`}>{message}</p>;
}
