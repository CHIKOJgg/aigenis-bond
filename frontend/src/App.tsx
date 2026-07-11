import { useEffect, useMemo, useState } from 'react';
import { api, ApiError, exportCsv } from './lib/api';
import type {
  Bond, BondScore, Stats, SubscribeInfo, WatchlistItem,
  AnalyticsCurve, AnalyticsRV, AnalyticsCarry, AnalyticsStress, AnalyticsRepo,
  AnalyticsPortfolio, AnalyticsForecast, AnalyticsRecommendation, AnalyticsAlert,
} from './lib/api';
import { AuthProvider, useAuth } from './lib/AuthContext';
import { PaywallProvider, usePaywall } from './lib/PaywallContext';
import { PaywallModal } from './PaywallModal';
import { tierLimits } from './lib/tiers';
import { LandingPage } from './LandingPage';
import { LegalPages } from './LegalPages';
import { OnboardingTour, isOnboardingNeeded } from './OnboardingTour';
import { BarChart3, Shield, Banknote, Activity, TrendingUp, Search, Menu, X, AlertTriangle, LineChart, PieChart, Zap, Brain, Bell, Clock, User, LogOut, Lock, Star, ExternalLink, FileText, ShieldCheck, CreditCard, Globe2, Download } from 'lucide-react';

const PREMIUM_PAGES = new Set<Page>(['desk', 'portfolio', 'forecast', 'ml', 'alerts']);

type Page = 'dashboard' | 'bonds' | 'scores' | 'desk' | 'forecast' | 'portfolio' | 'ml' | 'alerts' | 'settings' | 'subscribe';

export default function App() {
  return (
    <AuthProvider>
      <PaywallProvider>
        <AppInner />
      </PaywallProvider>
    </AuthProvider>
  );
}

function AppInner() {
  const { user, loading } = useAuth();
  const { openPaywall } = usePaywall();
  const [page, setPage] = useState<Page>('dashboard');
  const [mobileMenu, setMobileMenu] = useState(false);
  const [authPage, setAuthPage] = useState<'login' | 'register' | null>(null);
  const [legalPage, setLegalPage] = useState<'terms' | 'privacy' | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(isOnboardingNeeded());

  if (showOnboarding) {
    return <OnboardingTour onDone={() => setShowOnboarding(false)} />;
  }

  if (legalPage) {
    return <LegalPages page={legalPage} onBack={() => setLegalPage(null)} />;
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  if (!user) {
    if (authPage === 'login') return <LoginPage onRegister={() => setAuthPage('register')} />;
    if (authPage === 'register') return <RegisterPage onSwitch={() => setAuthPage('login')} />;
    return <LandingPage onLogin={() => setAuthPage('login')} onRegister={() => setAuthPage('register')} />;
  }

  const navItems: { id: Page; label: string; icon: React.ReactNode; premium?: boolean }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: <BarChart3 size={16} /> },
    { id: 'bonds', label: 'Bonds', icon: <Banknote size={16} /> },
    { id: 'scores', label: 'Scores', icon: <Shield size={16} /> },
    { id: 'desk', label: 'Desk', icon: <LineChart size={16} />, premium: true },
    { id: 'portfolio', label: 'Portfolio', icon: <PieChart size={16} />, premium: true },
    { id: 'forecast', label: 'Forecast', icon: <TrendingUp size={16} />, premium: true },
    { id: 'ml', label: 'ML', icon: <Brain size={16} />, premium: true },
    { id: 'alerts', label: 'Alerts', icon: <Bell size={16} />, premium: true },
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
                <Star size={16} />Subscribe
              </button>
            )}
            <button onClick={() => setPage('settings')}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm whitespace-nowrap ${page === 'settings' ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}>
              <User size={16} />{user.name.split(' ')[0]}
            </button>
          </nav>
          <button className="md:hidden p-2 text-gray-400" onClick={() => setMobileMenu(!mobileMenu)}>
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
        {page === 'dashboard' && <Dashboard />}
        {page === 'bonds' && <BondsPage />}
        {page === 'scores' && <ScoresPage />}
        {page === 'desk' && <DeskPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'portfolio' && <PortfolioPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'forecast' && <ForecastPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'ml' && <MLPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'alerts' && <AlertsPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'settings' && <SettingsPage onSubscribe={() => setPage('subscribe')} />}
        {page === 'subscribe' && <SubscribePage />}
      </main>
      <PaywallModal onSubscribe={() => setPage('subscribe')} />
      <footer className="border-t border-gray-800 bg-gray-900 mt-8">
        <div className="max-w-7xl mx-auto px-4 py-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-gray-500">
          <span>&copy; {new Date().getFullYear()} Aigenis Parser. All rights reserved.</span>
          <div className="flex items-center gap-4">
            <button onClick={() => setLegalPage('terms')} className="hover:text-gray-300 transition-colors flex items-center gap-1">
              <FileText size={12} /> Terms of Service
            </button>
            <button onClick={() => setLegalPage('privacy')} className="hover:text-gray-300 transition-colors flex items-center gap-1">
              <ShieldCheck size={12} /> Privacy Policy
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}

function LoginPage({ onRegister }: { onRegister: () => void }) {
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
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 w-full max-w-md">
        <div className="flex items-center gap-2 mb-6">
          <TrendingUp className="text-emerald-400" size={24} />
          <h1 className="text-xl font-bold">Aigenis Bonds</h1>
        </div>
        <h2 className="text-lg font-semibold mb-4">Sign In</h2>
        {error && <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">Email</label>
            <input value={email} onChange={e => setEmail(e.target.value)} type="email" required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">Password</label>
            <input value={password} onChange={e => setPassword(e.target.value)} type="password" required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <button type="submit" disabled={submitting}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white py-2 rounded-lg text-sm font-medium transition-colors">
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
        <p className="text-sm text-gray-400 mt-4 text-center">
          Don't have an account?{' '}
          <button onClick={onRegister} className="text-emerald-400 hover:underline">Sign up</button>
        </p>
      </div>
    </div>
  );
}

function RegisterPage({ onSwitch }: { onSwitch: () => void }) {
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 6) { setError('Password must be at least 6 characters'); return; }
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
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 w-full max-w-md">
        <div className="flex items-center gap-2 mb-6">
          <TrendingUp className="text-emerald-400" size={24} />
          <h1 className="text-xl font-bold">Aigenis Bonds</h1>
        </div>
        <h2 className="text-lg font-semibold mb-4">Create Account</h2>
        {error && <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">Name</label>
            <input value={name} onChange={e => setName(e.target.value)} required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">Email</label>
            <input value={email} onChange={e => setEmail(e.target.value)} type="email" required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">Password</label>
            <input value={password} onChange={e => setPassword(e.target.value)} type="password" required minLength={6}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
          </div>
          <button type="submit" disabled={submitting}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white py-2 rounded-lg text-sm font-medium transition-colors">
            {submitting ? 'Creating account...' : 'Create Account'}
          </button>
        </form>
        <p className="text-sm text-gray-400 mt-4 text-center">
          Already have an account?{' '}
          <button onClick={onSwitch} className="text-emerald-400 hover:underline">Sign in</button>
        </p>
      </div>
    </div>
  );
}

function SettingsPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { user, logout } = useAuth();
  const isOnTrial = user?.trial_end && new Date(user.trial_end) > new Date();
  const trialDaysLeft = isOnTrial ? Math.ceil((new Date(user!.trial_end!).getTime() - Date.now()) / (1000 * 60 * 60 * 24)) : 0;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Settings</h2>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 max-w-lg">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><User size={16} className="text-emerald-400" /> Profile</h3>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between py-1.5 border-b border-gray-800">
            <span className="text-gray-400">Name</span>
            <span className="text-white font-medium">{user?.name}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-gray-800">
            <span className="text-gray-400">Email</span>
            <span className="text-white font-medium">{user?.email}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-gray-800">
            <span className="text-gray-400">Plan</span>
            <span className="text-emerald-400 font-medium capitalize">{user?.subscription_tier}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-gray-800">
            <span className="text-gray-400">Role</span>
            <span className="text-white font-medium capitalize">{user?.role}</span>
          </div>
          {isOnTrial && (
            <div className="flex justify-between py-1.5 border-b border-gray-800">
              <span className="text-gray-400">Trial</span>
              <span className="text-amber-400 font-medium">{trialDaysLeft} day{trialDaysLeft > 1 ? 's' : ''} left</span>
            </div>
          )}
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          {user?.subscription_tier === 'free' && (
            <button onClick={onSubscribe}
              className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-sm transition-colors">
              <Star size={16} /> Оформить подписку
            </button>
          )}
          <button onClick={logout}
            className="flex items-center gap-2 bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded-lg text-sm transition-colors">
            <LogOut size={16} /> Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}

function Dashboard() {
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
    }).catch(() => setError('Failed to load dashboard')).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        {health && (
          <div className="flex items-center gap-2 text-xs">
            <span className={`w-2 h-2 rounded-full ${health.status === 'ok' ? 'bg-emerald-400' : 'bg-red-400'}`} />
            <span className="text-gray-400">{health.status}</span>
            <span className="text-gray-600">|</span>
            <span className="text-gray-400">DB: {health.db}</span>
            <Clock size={12} className="text-gray-500" />
            <span className="text-gray-500">{Math.floor(health.uptime_seconds || 0)}s</span>
          </div>
        )}
      </div>

      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Banknote} label="Total Bonds" value={stats.total_bonds} color="from-emerald-500 to-emerald-700" />
          <StatCard icon={Activity} label="Active Bonds" value={stats.active_bonds} color="from-blue-500 to-blue-700" />
          <StatCard icon={Shield} label="Top Score" value={scores[0]?.score?.toFixed(1) || '-'} color="from-purple-500 to-purple-700" />
          {Object.entries(stats.by_currency).slice(0, 1).map(([cur, count]) => (
            <StatCard key={cur} icon={BarChart3} label={`${cur} Bonds`} value={count as number} color="from-amber-500 to-amber-700" />
          ))}
        </div>
      )}

      <CurrencyTracker />

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2"><Banknote size={16} className="text-emerald-400" /> Recent Bonds</h3>
          <div className="space-y-1">
            {bonds.map(b => <BondRow key={b.internal_id} bond={b} />)}
          </div>
          {bonds.length === 0 && <EmptyState message="No bonds found" />}
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2"><Shield size={16} className="text-purple-400" /> Top Scores</h3>
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
          <Globe2 size={16} className="text-emerald-400" /> Трекер валют (бирж)
        </h3>
        {isFree && (
          <span className={`text-xs px-2 py-0.5 rounded border ${atLimit ? 'text-amber-400 bg-amber-900/30 border-amber-800' : 'text-gray-400 bg-gray-800 border-gray-700'}`}>
            {selected.length}/{limits.maxCurrencies}
          </span>
        )}
      </div>
      <p className="text-xs text-gray-500 mb-3">
        {isFree
          ? 'Бесплатный тариф — только 1 валюта. Pro / Enterprise — все биржи и валюты сразу.'
          : 'Отслеживаемые валюты (биржи).'}
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
          <Lock size={14} /> Разблокировать все валюты
        </button>
      )}
    </div>
  );
}

function WatchlistCard() {
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

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <Star size={16} className="text-amber-400" /> Избранное
        <span className="text-xs text-gray-500 font-normal ml-auto">{items.length}</span>
      </h3>
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

function BondsPage() {
  const { user } = useAuth();
  const [allBonds, setAllBonds] = useState<Bond[]>([]);
  const [scoreMap, setScoreMap] = useState<Record<string, number>>({});
  const [currency, setCurrency] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [minYtm, setMinYtm] = useState('');
  const [minScore, setMinScore] = useState('');
  const [sort, setSort] = useState<{ key: 'yield_to_maturity' | 'price' | 'coupon_rate' | 'score' | 'name'; dir: 'asc' | 'desc' }>({ key: 'yield_to_maturity', dir: 'desc' });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Bond | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const PAGE_SIZE = 25;

  useEffect(() => {
    setLoading(true);
    setError(null);
    setPage(1);
    Promise.all([
      api.bonds.list({ currency: currency || undefined, limit: 1000 }),
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
  }, [currency]);

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

  const filtered = useMemo(() => {
    let rows = allBonds;
    const q = search.trim().toLowerCase();
    if (q) rows = rows.filter((b) => b.name.toLowerCase().includes(q) || b.internal_id.toLowerCase().includes(q));
    if (status) rows = rows.filter((b) => b.status === status);
    if (minYtm !== '') {
      const v = Number(minYtm);
      rows = rows.filter((b) => b.yield_to_maturity != null && b.yield_to_maturity * 100 >= v);
    }
    if (minScore !== '') {
      const v = Number(minScore);
      rows = rows.filter((b) => (scoreMap[b.internal_id] ?? -1) >= v);
    }
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
  }, [allBonds, search, status, minYtm, minScore, sort, scoreMap]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const statuses = Array.from(new Set(allBonds.map((b) => b.status))).sort();

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
        <h2 className="text-2xl font-bold">Bonds</h2>
        <button onClick={exportNow} disabled={filtered.length === 0}
          className="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200 px-3 py-2 rounded-lg text-sm transition-colors">
          <Download size={15} /> CSV
        </button>
      </div>

      {/* Screener */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="flex items-center gap-2">
          <Search size={16} className="text-gray-500 shrink-0" />
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Поиск по названию / ID"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full" />
        </div>
        <input value={currency} onChange={(e) => { setCurrency(e.target.value.toUpperCase()); setPage(1); }} placeholder="Валюта (USD, BYN...)"
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full" />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full">
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input value={minYtm} onChange={(e) => { setMinYtm(e.target.value); setPage(1); }} type="number" step="0.1" placeholder="Мин. YTM, %"
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full" />
        <input value={minScore} onChange={(e) => { setMinScore(e.target.value); setPage(1); }} type="number" step="0.1" placeholder="Мин. скор"
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full" />
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>Найдено: {filtered.length}</span>
          {(search || status || minYtm || minScore || currency) && (
            <button onClick={() => { setSearch(''); setStatus(''); setMinYtm(''); setMinScore(''); setCurrency(''); setPage(1); }}
              className="text-gray-400 hover:text-white">Сбросить</button>
          )}
        </div>
      </div>

      {loading && <LoadingSkeleton />}
      {error && <ErrorBanner message={error} />}
      {!loading && !error && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left p-3 w-8"></th>
                <SortHeader label="Name" k="name" />
                <th className="text-left p-3 hidden sm:table-cell">ID</th>
                <th className="text-left p-3">Cur</th>
                <SortHeader label="Price" k="price" className="text-right" />
                <SortHeader label="YTM" k="yield_to_maturity" className="text-right hidden md:table-cell" />
                <SortHeader label="Coupon" k="coupon_rate" className="text-right hidden lg:table-cell" />
                <SortHeader label="Score" k="score" className="text-right" />
                <th className="text-left p-3 hidden lg:table-cell">Maturity</th>
                <th className="text-left p-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((b) => (
                <tr key={b.internal_id} onClick={() => setSelected(selected?.internal_id === b.internal_id ? null : b)}
                  className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer transition-colors">
                  <td className="p-3" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => toggleFav(b.internal_id)} className="text-gray-500 hover:text-amber-400" title="В избранное">
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
          {filtered.length === 0 && <EmptyState message="Ничего не найдено. Измените фильтры." />}
        </div>
      )}

      {/* Pagination */}
      {!loading && !error && totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 text-sm">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
            className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200">Назад</button>
          <span className="text-gray-400">{page} / {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200">Вперёд</button>
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
    </div>
  );
}

function BondDetailModal({ bond, isFavorite, onToggleFavorite, onClose }: { bond: Bond; isFavorite?: boolean; onToggleFavorite?: () => void; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 max-w-lg w-full max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold">{bond.internal_id}</h3>
          <div className="flex items-center gap-2">
            {onToggleFavorite && (
              <button onClick={onToggleFavorite} className="text-gray-400 hover:text-amber-400 p-1" title="В избранное">
                <Star size={18} className={isFavorite ? 'fill-amber-400 text-amber-400' : ''} />
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-white p-1"><X size={18} /></button>
          </div>
        </div>
        <div className="space-y-3 text-sm">
          <DetailRow label="Name" value={bond.name} />
          <DetailRow label="Currency" value={bond.currency} />
          <DetailRow label="Issuer" value={bond.issuer || '-'} />
          <DetailRow label="Price" value={bond.price != null ? bond.price.toFixed(2) : '-'} />
          <DetailRow label="YTM" value={bond.yield_to_maturity != null ? `${(bond.yield_to_maturity * 100).toFixed(2)}%` : '-'} />
          <DetailRow label="Coupon Rate" value={bond.coupon_rate != null ? `${(bond.coupon_rate * 100).toFixed(2)}%` : '-'} />
          <DetailRow label="Frequency" value={bond.coupon_frequency != null ? `${bond.coupon_frequency}x/year` : '-'} />
          <DetailRow label="Maturity" value={bond.maturity_date ? new Date(bond.maturity_date).toLocaleDateString() : '-'} />
          <DetailRow label="Status" value={bond.status} />
          <DetailRow label="Last Updated" value={bond.fetched_at ? new Date(bond.fetched_at).toLocaleString() : '-'} />
        </div>
      </div>
    </div>
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
  const [scores, setScores] = useState<BondScore[]>([]);
  const [minScore, setMinScore] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.scores({ min_score: minScore ? Number(minScore) : undefined, limit: 100 })
      .then(setScores)
      .catch(() => setError('Failed to load scores'))
      .finally(() => setLoading(false));
  }, [minScore]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">Bond Scores</h2>
        <input value={minScore} onChange={e => setMinScore(e.target.value)} placeholder="Min score" type="number" step="0.1"
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full sm:w-32" />
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
                <tr key={s.internal_id} className="border-b border-gray-800 hover:bg-gray-800/50">
                  <td className="p-3 text-gray-500 text-xs">{i + 1}</td>
                  <td className="p-3 font-mono text-xs text-gray-300">{s.internal_id}</td>
                  <td className="p-3 text-right font-mono text-emerald-400">{s.score.toFixed(2)}</td>
                  <td className="p-3"><TierBadge tier={s.tier} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {scores.length === 0 && <EmptyState message="No scores found" />}
        </div>
      )}
    </div>
  );
}

function DeskPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const [tab, setTab] = useState<'curve' | 'rv' | 'carry' | 'repo' | 'stress'>('curve');

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Fixed Income Desk</h2>
      <div className="flex gap-2 flex-wrap">
        {(['curve', 'rv', 'carry', 'repo', 'stress'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm capitalize ${tab === t ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
            {t === 'curve' ? 'Yield Curve' : t === 'rv' ? 'Relative Value' : t === 'carry' ? 'Carry' : t === 'repo' ? 'Repo' : 'Stress'}
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

function DeskCurve({ onSubscribe }: { onSubscribe?: () => void }) {
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
            <span className="text-xs text-gray-500 font-normal ml-auto">slope {c.slope.toFixed(2)}</span>
          </h3>
          <div className="space-y-1">
            {c.points.filter(p => p.years > 0).slice(0, 15).map((p, i) => (
              <div key={i} className="flex justify-between text-sm py-1 border-b border-gray-800/50">
                <span className="text-gray-400 font-mono text-xs">{p.tenor}</span>
                <span className="text-emerald-400 font-mono">{p.rate_pct.toFixed(2)}%</span>
              </div>
            ))}
          </div>
        </div>
      ))}
      {(curves ?? []).length === 0 && <EmptyState message="No bonds with YTM data available" className="col-span-full" />}
    </div>
  );
}

function DeskRV({ onSubscribe }: { onSubscribe?: () => void }) {
  const { data: signals, loading, error, locked } = useGated<AnalyticsRV[]>(() => api.analytics.rv());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = signals ?? [];
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-gray-400">
            <th className="text-left p-3">ID</th>
            <th className="text-right p-3">Spread</th>
            <th className="text-right p-3">Z-Score</th>
            <th className="text-left p-3">Signal</th>
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
      {rows.length === 0 && <EmptyState message="No RV signals available" />}
    </div>
  );
}

function DeskCarry({ onSubscribe }: { onSubscribe?: () => void }) {
  const [funding, setFunding] = useState('5.0');
  const { data: trades, loading, error, locked } = useGated<AnalyticsCarry[]>(
    () => api.analytics.carry(parseFloat(funding) || 5), [funding]
  );

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = trades ?? [];
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm text-gray-400">Funding Rate:</label>
        <input value={funding} onChange={e => setFunding(e.target.value)} type="number" step="0.1" className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-sm w-24" />
        <span className="text-sm text-gray-500">%</span>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">ID</th>
              <th className="text-right p-3">Coupon</th>
              <th className="text-right p-3">Rolldown</th>
              <th className="text-right p-3">Exp. P&L</th>
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
        {rows.length === 0 && <EmptyState message="No carry data available" />}
      </div>
    </div>
  );
}

function DeskRepo({ onSubscribe }: { onSubscribe?: () => void }) {
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
        <h3 className="text-lg font-semibold mb-4">Repo Deal Calculator</h3>
        <div className="space-y-3">
          <InputField label="Bond ID" value={bondId} onChange={setBondId} placeholder="OP-51" />
          <InputField label="Notional" value={notional} onChange={setNotional} type="number" />
          <InputField label="Tenor (days)" value={tenor} onChange={setTenor} type="number" />
          <button onClick={calculate} disabled={busy} className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white py-2 rounded-lg text-sm font-medium transition-colors">{busy ? 'Calculating...' : 'Calculate'}</button>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      {result && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 max-w-md">
          <h3 className="text-lg font-semibold mb-3">Repo Deal Results</h3>
          <div className="space-y-2 text-sm">
            <DetailRow label="Bond" value={result.internal_id} />
            <DetailRow label="Haircut" value={`${result.haircut_pct.toFixed(2)}%`} />
            <DetailRow label="Repo Rate" value={`${result.repo_rate_pct.toFixed(2)}%`} />
            <DetailRow label="Tenor" value={`${result.tenor_days}d`} />
            <DetailRow label="Cash Lent" value={result.cash_lent.toFixed(2)} />
            <DetailRow label="Collateral" value={result.collateral_value.toFixed(2)} />
            <DetailRow label="Accrued Interest" value={result.accrued_interest.toFixed(4)} />
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
  const { data, loading, error, locked } = useGated<AnalyticsStress[]>(() => api.analytics.stress());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const results = data ?? [];
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold flex items-center gap-2"><Zap size={16} className="text-amber-400" /> Stress Test Scenarios</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {results.map(r => (
          <div key={r.scenario} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
            <h4 className="font-semibold mb-2 capitalize">{r.scenario.replace(/_/g, ' ')}</h4>
            <div className="space-y-1 text-sm">
              <p className={`text-2xl font-bold ${r.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{r.pnl_pct >= 0 ? '+' : ''}{r.pnl_pct.toFixed(2)}%</p>
              <p className="text-gray-400">P&L: {r.pnl >= 0 ? '+' : ''}{r.pnl.toFixed(0)}</p>
              <p className="text-gray-500 text-xs">{r.kind}</p>
            </div>
          </div>
        ))}
      </div>
      {results.length === 0 && <EmptyState message="No stress data available" />}
    </div>
  );
}

function PortfolioPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { data: alloc, loading, error, locked } = useGated<AnalyticsPortfolio>(() => api.analytics.portfolio());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;
  if (!alloc) return <EmptyState message="No portfolio data" />;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Portfolio</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3">Metrics</h3>
          <div className="space-y-3">
            <MetricRow label="Strategy" value={alloc.strategy} />
            <MetricRow label="Exp. Return" value={`${alloc.expected_return.toFixed(2)}%`} color="text-emerald-400" />
            <MetricRow label="Sharpe" value={alloc.sharpe.toFixed(2)} color="text-blue-400" />
            <MetricRow label="Sortino" value={alloc.sortino.toFixed(2)} color="text-blue-400" />
            <MetricRow label="Max Drawdown" value={`${alloc.max_drawdown.toFixed(1)}%`} color="text-red-400" />
            <MetricRow label="VaR 95%" value={`${alloc.var_95.toFixed(1)}%`} color="text-red-400" />
          </div>
        </div>
        <div className="lg:col-span-2 bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
          <h3 className="text-lg font-semibold p-4 pb-2">Capital Forecast</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400">
                <th className="text-left p-3">Horizon</th>
                <th className="text-right p-3">Pessimistic</th>
                <th className="text-right p-3">Expected</th>
                <th className="text-right p-3">Optimistic</th>
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
  const { data: horizons, loading, error, locked } = useGated<AnalyticsForecast[]>(() => api.analytics.forecast());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = horizons ?? [];
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Capital Forecast</h2>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">Horizon</th>
              <th className="text-right p-3">Pessimistic</th>
              <th className="text-right p-3">Expected</th>
              <th className="text-right p-3">Optimistic</th>
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
        {rows.length === 0 && <EmptyState message="No forecast data" />}
      </div>
    </div>
  );
}

function MLPage({ onSubscribe }: { onSubscribe?: () => void }) {
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
      <h2 className="text-2xl font-bold">ML Recommendations</h2>
      <p className="text-sm text-gray-400">Explainable buy/hold/wait/avoid recommendations from the ML pipeline.</p>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">#</th>
              <th className="text-left p-3">Bond</th>
              <th className="text-left p-3">Decision</th>
              <th className="text-right p-3">Score</th>
              <th className="text-right p-3">Pred. Return</th>
              <th className="text-right p-3">Confidence</th>
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
        {predictions.length === 0 && <EmptyState message="No recommendations available" />}
      </div>
    </div>
  );
}

function AlertsPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { data, loading, error, locked } = useGated<AnalyticsAlert[]>(() => api.analytics.alerts(20));

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const alerts = data ?? [];
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Alerts</h2>
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
      ) : <EmptyState message="No alerts" />}
    </div>
  );
}

function useGated<T>(fetcher: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(null); setLocked(false);
    fetcher()
      .then(d => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
        else setError(e instanceof Error ? e.message : 'Failed to load');
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, loading, error, locked };
}

function UpgradePrompt({ onSubscribe }: { onSubscribe?: () => void }) {
  return (
    <div className="bg-gradient-to-br from-amber-900/30 to-gray-900 border border-amber-800/50 rounded-xl p-8 text-center max-w-lg mx-auto">
      <div className="w-14 h-14 bg-amber-600/20 rounded-full flex items-center justify-center mx-auto mb-4">
        <Lock size={26} className="text-amber-400" />
      </div>
      <h3 className="text-lg font-bold mb-2">Функция Pro / Enterprise</h3>
      <p className="text-sm text-gray-400 mb-5">
        Эта аналитика доступна по подписке. Оформите её через Telegram Stars в боте —
        доступ откроется здесь и в боте одновременно.
      </p>
      {onSubscribe && (
        <button onClick={onSubscribe}
          className="inline-flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors">
          <Star size={16} /> Оформить подписку
        </button>
      )}
    </div>
  );
}

function SubscribePage() {
  const [info, setInfo] = useState<SubscribeInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  useEffect(() => {
    api.subscribeInfo().then(setInfo).catch(() => setInfo(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;

  const isPaid = user && user.subscription_tier !== 'free';
  const isOnTrial = user?.trial_end && new Date(user.trial_end) > new Date();
  const trialDaysLeft = isOnTrial ? Math.ceil((new Date(user!.trial_end!).getTime() - Date.now()) / (1000 * 60 * 60 * 24)) : 0;

  const handleYooKassaPayment = async (plan: string) => {
    try {
      const base = window.location.origin;
      const result = await api.billing.createPayment(plan, `${base}/subscribe?success=1`, `${base}/subscribe`);
      if (result.confirmation_url) window.location.href = result.confirmation_url;
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Ошибка оплаты');
    }
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="text-center">
        <div className="w-14 h-14 bg-amber-600/20 rounded-full flex items-center justify-center mx-auto mb-3">
          <Star size={26} className="text-amber-400" />
        </div>
        <h2 className="text-2xl font-bold">Подписка</h2>
        <p className="text-sm text-gray-400 mt-2">
          Подписка открывает Desk-аналитику (RV, duration, carry, РЕПО, стресс-тесты),
          рекомендации, портфель, ML-прогнозы и алерты — одинаково в боте и на сайте.
        </p>
        {isOnTrial && (
          <p className="mt-3 inline-block bg-blue-900/40 border border-blue-800 text-blue-300 text-sm px-3 py-1.5 rounded-lg">
            Пробный период: <b>{trialDaysLeft} {trialDaysLeft > 1 ? 'дней' : 'день'}</b> осталось
          </p>
        )}
        {isPaid && !isOnTrial && (
          <p className="mt-3 inline-block bg-emerald-900/40 border border-emerald-800 text-emerald-300 text-sm px-3 py-1.5 rounded-lg">
            Ваш текущий тариф: <b className="capitalize">{user!.subscription_tier}</b>
          </p>
        )}
      </div>

      {/* YooKassa — карты, СБП, Apple Pay, Google Pay */}
      {info?.yookassa_configured && info.yookassa_plans.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <CreditCard size={18} className="text-blue-400" /> Банковская карта (ЮKassa)
          </h3>
          <p className="text-sm text-gray-500 mb-3">Принимаем Visa, Mastercard, Мир, СБП, Apple Pay, Google Pay</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {info.yookassa_plans.map(p => (
              <div key={p.tier} className="bg-gray-900 rounded-xl border border-gray-800 p-5 flex flex-col">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-lg font-bold">{p.name}</h3>
                  <span className="text-emerald-400 font-semibold">{p.price} {p.currency}/{p.interval}</span>
                </div>
                <p className="text-sm text-gray-400 flex-1">
                  {p.tier === 'pro' ? 'Полный Fixed Income Desk, ML, портфель, алерты.' : 'Всё из Pro + макс. лимиты, приоритетная поддержка.'}
                </p>
                <button onClick={() => handleYooKassaPayment(p.tier)}
                  className="mt-4 w-full bg-blue-600 hover:bg-blue-500 text-white py-2 rounded-lg text-sm font-medium transition-colors">
                  Оплатить картой
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
              <p className="text-xs text-gray-500 mt-3">{p.duration_days} дней · разовая оплата</p>
            </div>
          ))}
        </div>

        {info?.deep_link ? (
          <a href={info.deep_link} target="_blank" rel="noopener noreferrer"
            className="mt-4 flex items-center justify-center gap-2 bg-amber-600 hover:bg-amber-500 text-white py-3 rounded-xl text-sm font-medium transition-colors">
            <ExternalLink size={16} /> Оформить в Telegram-боте
          </a>
        ) : (
          <p className="mt-4 text-center text-sm text-gray-500">
            Откройте бота и отправьте /subscribe
          </p>
        )}
      </div>
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
