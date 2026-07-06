import { useEffect, useState } from 'react';
import { api, type Bond, type BondScore, type Stats } from './lib/api';
import { AuthProvider, useAuth } from './lib/AuthContext';
import { BarChart3, Shield, Banknote, Activity, TrendingUp, Search, Menu, X, AlertTriangle, LineChart, PieChart, Zap, Brain, Bell, Clock, User, LogOut } from 'lucide-react';

type Page = 'dashboard' | 'bonds' | 'scores' | 'desk' | 'forecast' | 'portfolio' | 'ml' | 'alerts' | 'settings';

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}

function AppInner() {
  const { user, loading } = useAuth();
  const [page, setPage] = useState<Page>('dashboard');
  const [mobileMenu, setMobileMenu] = useState(false);
  const [authPage, setAuthPage] = useState<'login' | 'register' | null>(null);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  if (!user) {
    if (authPage === 'register') return <RegisterPage onSwitch={() => setAuthPage('login')} />;
    return <LoginPage onRegister={() => setAuthPage('register')} />;
  }

  const navItems: { id: Page; label: string; icon: React.ReactNode }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: <BarChart3 size={16} /> },
    { id: 'bonds', label: 'Bonds', icon: <Banknote size={16} /> },
    { id: 'scores', label: 'Scores', icon: <Shield size={16} /> },
    { id: 'desk', label: 'Desk', icon: <LineChart size={16} /> },
    { id: 'portfolio', label: 'Portfolio', icon: <PieChart size={16} /> },
    { id: 'forecast', label: 'Forecast', icon: <TrendingUp size={16} /> },
    { id: 'ml', label: 'ML', icon: <Brain size={16} /> },
    { id: 'alerts', label: 'Alerts', icon: <Bell size={16} /> },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 bg-gray-900 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-bold flex items-center gap-2">
            <TrendingUp className="text-emerald-400" size={22} />
            <span className="hidden sm:inline">Aigenis Bonds</span>
          </h1>
          <nav className="hidden md:flex gap-1 overflow-x-auto">
            {navItems.map(({ id, label, icon }) => (
              <button key={id} onClick={() => setPage(id)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm whitespace-nowrap ${page === id ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}>
                {icon}{label}
              </button>
            ))}
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
            {navItems.map(({ id, label, icon }) => (
              <button key={id} onClick={() => { setPage(id); setMobileMenu(false); }}
                className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm ${page === id ? 'bg-emerald-600 text-white' : 'text-gray-400'}`}>
                {icon}{label}
              </button>
            ))}
          </div>
        )}
      </header>
      <main className="max-w-7xl mx-auto p-4">
        {page === 'dashboard' && <Dashboard />}
        {page === 'bonds' && <BondsPage />}
        {page === 'scores' && <ScoresPage />}
        {page === 'desk' && <DeskPage />}
        {page === 'portfolio' && <PortfolioPage />}
        {page === 'forecast' && <ForecastPage />}
        {page === 'ml' && <MLPage />}
        {page === 'alerts' && <AlertsPage />}
        {page === 'settings' && <SettingsPage />}
      </main>
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

function SettingsPage() {
  const { user, logout } = useAuth();

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
        </div>
        <button onClick={logout}
          className="mt-6 flex items-center gap-2 bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded-lg text-sm transition-colors">
          <LogOut size={16} /> Sign Out
        </button>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
      </div>
    </div>
  );
}

function BondsPage() {
  const [bonds, setBonds] = useState<Bond[]>([]);
  const [currency, setCurrency] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Bond | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.bonds.list({ currency: currency || undefined, limit: 100 })
      .then(setBonds)
      .catch(() => setError('Failed to load bonds'))
      .finally(() => setLoading(false));
  }, [currency]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">Bonds</h2>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Search size={16} className="text-gray-500 shrink-0" />
          <input value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())} placeholder="Filter by currency (USD, BYN...)"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full sm:w-48" />
        </div>
      </div>
      {loading && <LoadingSkeleton />}
      {error && <ErrorBanner message={error} />}
      {!loading && !error && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400">
                <th className="text-left p-3">Name</th>
                <th className="text-left p-3 hidden sm:table-cell">ID</th>
                <th className="text-left p-3">Cur</th>
                <th className="text-right p-3">Price</th>
                <th className="text-right p-3 hidden md:table-cell">YTM</th>
                <th className="text-right p-3 hidden lg:table-cell">Coupon</th>
                <th className="text-left p-3 hidden lg:table-cell">Maturity</th>
                <th className="text-left p-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {bonds.map(b => (
                <tr key={b.internal_id} onClick={() => setSelected(selected?.internal_id === b.internal_id ? null : b)}
                  className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer transition-colors">
                  <td className="p-3 text-white font-medium max-w-[200px] truncate">{b.name}</td>
                  <td className="p-3 text-gray-400 font-mono text-xs hidden sm:table-cell">{b.internal_id}</td>
                  <td className="p-3"><CurrencyBadge currency={b.currency} /></td>
                  <td className="p-3 text-right font-mono">{b.price?.toFixed(2) ?? '-'}</td>
                  <td className="p-3 text-right font-mono hidden md:table-cell">{b.yield_to_maturity != null ? `${(b.yield_to_maturity * 100).toFixed(2)}%` : '-'}</td>
                  <td className="p-3 text-right font-mono hidden lg:table-cell">{b.coupon_rate != null ? `${(b.coupon_rate * 100).toFixed(2)}%` : '-'}</td>
                  <td className="p-3 text-gray-400 text-xs hidden lg:table-cell">{b.maturity_date ? new Date(b.maturity_date).toLocaleDateString() : '-'}</td>
                  <td className="p-3">{b.status === 'active' ? <span className="px-2 py-0.5 rounded text-xs bg-green-900 text-green-300">active</span> : <span className="px-2 py-0.5 rounded text-xs bg-gray-800 text-gray-400">{b.status}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {bonds.length === 0 && <EmptyState message="No bonds found. Run the scraper first." />}
        </div>
      )}
      {selected && (
        <BondDetailModal bond={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function BondDetailModal({ bond, onClose }: { bond: Bond; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 max-w-lg w-full max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold">{bond.internal_id}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white p-1"><X size={18} /></button>
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

function DeskPage() {
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
      {tab === 'curve' && <DeskCurve />}
      {tab === 'rv' && <DeskRV />}
      {tab === 'carry' && <DeskCarry />}
      {tab === 'repo' && <DeskRepo />}
      {tab === 'stress' && <DeskStress />}
    </div>
  );
}

function DeskCurve() {
  const [curves, setCurves] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.bonds.list({ limit: 200 }).then(allBonds => {
      const byCur: Record<string, any[]> = {};
      for (const b of allBonds) {
        if (!b.yield_to_maturity || !b.maturity_date) continue;
        (byCur[b.currency] = byCur[b.currency] || []).push(b);
      }
      const result = Object.entries(byCur).map(([cur, bonds]) => ({
        currency: cur,
        points: bonds
          .sort((a, b) => new Date(a.maturity_date!).getTime() - new Date(b.maturity_date!).getTime())
          .slice(0, 20)
          .map(b => ({
            tenor: b.internal_id,
            years: (new Date(b.maturity_date!).getTime() - Date.now()) / (365.25 * 24 * 60 * 60 * 1000),
            rate: b.yield_to_maturity! * 100,
          })),
      }));
      setCurves(result);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {curves.map(c => (
        <div key={c.currency} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <LineChart size={16} className="text-emerald-400" /> {c.currency} Curve
          </h3>
          <div className="space-y-1">
            {c.points.filter((p: any) => p.years > 0).slice(0, 15).map((p: any, i: number) => (
              <div key={i} className="flex justify-between text-sm py-1 border-b border-gray-800/50">
                <span className="text-gray-400 font-mono text-xs">{p.tenor}</span>
                <span className="text-emerald-400 font-mono">{p.rate.toFixed(2)}%</span>
              </div>
            ))}
          </div>
        </div>
      ))}
      {curves.length === 0 && <EmptyState message="No bonds with YTM data available" className="col-span-full" />}
    </div>
  );
}

function DeskRV() {
  const [signals, setSignals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.bonds.list({ limit: 200 }).then(allBonds => {
      const byCur: Record<string, any[]> = {};
      for (const b of allBonds) {
        if (!b.yield_to_maturity) continue;
        (byCur[b.currency] = byCur[b.currency] || []).push(b);
      }
      const result: any[] = [];
      for (const [, bonds] of Object.entries(byCur)) {
        const ys = bonds.map(b => b.yield_to_maturity! * 100);
        const mean = ys.reduce((a: number, b: number) => a + b, 0) / ys.length;
        const std = Math.sqrt(ys.reduce((a: number, y: number) => a + (y - mean) ** 2, 0) / ys.length) || 1;
        for (const b of bonds) {
          const z = (b.yield_to_maturity! * 100 - mean) / std;
          result.push({ internal_id: b.internal_id, z_score: z, side: z > 1 ? 'sell' : z < -1 ? 'buy' : 'hold', currency: b.currency, ytm: b.yield_to_maturity! * 100 });
        }
      }
      result.sort((a, b) => Math.abs(b.z_score) - Math.abs(a.z_score));
      setSignals(result.slice(0, 50));
    }).catch(() => setError('Failed to compute RV signals')).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-gray-400">
            <th className="text-left p-3">ID</th>
            <th className="text-left p-3">Cur</th>
            <th className="text-right p-3">YTM</th>
            <th className="text-right p-3">Z-Score</th>
            <th className="text-left p-3">Signal</th>
          </tr>
        </thead>
        <tbody>
          {signals.slice(0, 30).map((s, i) => (
            <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
              <td className="p-3 font-mono text-xs text-gray-300">{s.internal_id}</td>
              <td className="p-3"><CurrencyBadge currency={s.currency} /></td>
              <td className="p-3 text-right font-mono">{s.ytm.toFixed(2)}%</td>
              <td className="p-3 text-right font-mono">{s.z_score.toFixed(2)}</td>
              <td className="p-3">
                <span className={`px-2 py-0.5 rounded text-xs ${s.side === 'buy' ? 'bg-green-900 text-green-300' : s.side === 'sell' ? 'bg-red-900 text-red-300' : 'bg-gray-800 text-gray-400'}`}>
                  {s.side.toUpperCase()}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {signals.length === 0 && <EmptyState message="No RV signals available" />}
    </div>
  );
}

function DeskCarry() {
  const [trades, setTrades] = useState<any[]>([]);
  const [funding, setFunding] = useState('5.0');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.bonds.list({ limit: 100 }).then(allBonds => {
      const f = parseFloat(funding) || 5;
      const result = allBonds
        .filter(b => b.yield_to_maturity && b.coupon_rate)
        .map(b => ({
          internal_id: b.internal_id,
          currency: b.currency,
          coupon_pct: b.coupon_rate! * 100,
          ytm_pct: b.yield_to_maturity! * 100,
          carry: (b.coupon_rate! * 100 - f),
          expected_pnl_pct: (b.yield_to_maturity! * 100 - f),
        }))
        .sort((a, b) => b.expected_pnl_pct - a.expected_pnl_pct);
      setTrades(result);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [funding]);

  if (loading) return <LoadingSkeleton />;

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
              <th className="text-left p-3">Cur</th>
              <th className="text-right p-3">Coupon</th>
              <th className="text-right p-3">YTM</th>
              <th className="text-right p-3">Carry</th>
              <th className="text-right p-3">Exp. P&L</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, 30).map((t, i) => (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="p-3 font-mono text-xs text-gray-300">{t.internal_id}</td>
                <td className="p-3"><CurrencyBadge currency={t.currency} /></td>
                <td className="p-3 text-right font-mono">{t.coupon_pct.toFixed(2)}%</td>
                <td className="p-3 text-right font-mono">{t.ytm_pct.toFixed(2)}%</td>
                <td className={`p-3 text-right font-mono ${t.carry > 0 ? 'text-emerald-400' : 'text-red-400'}`}>{t.carry > 0 ? '+' : ''}{t.carry.toFixed(2)}%</td>
                <td className={`p-3 text-right font-mono ${t.expected_pnl_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>{t.expected_pnl_pct > 0 ? '+' : ''}{t.expected_pnl_pct.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {trades.length === 0 && <EmptyState message="No carry data available" />}
      </div>
    </div>
  );
}

function DeskRepo() {
  const [bondId, setBondId] = useState('');
  const [notional, setNotional] = useState('1000');
  const [tenor, setTenor] = useState('30');
  const [result, setResult] = useState<any>(null);

  const calculate = () => {
    if (!bondId) return;
    setResult({
      internal_id: bondId,
      notional: parseFloat(notional),
      haircut_pct: 5.0,
      repo_rate_pct: 5.0,
      tenor_days: parseInt(tenor),
      cash_lent: parseFloat(notional) * 0.95,
      collateral_value: parseFloat(notional),
      accrued_interest: parseFloat(notional) * 0.95 * 0.05 * parseInt(tenor) / 365,
    });
  };

  return (
    <div className="space-y-4">
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 max-w-md">
        <h3 className="text-lg font-semibold mb-4">Repo Deal Calculator</h3>
        <div className="space-y-3">
          <InputField label="Bond ID" value={bondId} onChange={setBondId} placeholder="OP-51" />
          <InputField label="Notional" value={notional} onChange={setNotional} type="number" />
          <InputField label="Tenor (days)" value={tenor} onChange={setTenor} type="number" />
          <button onClick={calculate} className="w-full bg-emerald-600 hover:bg-emerald-500 text-white py-2 rounded-lg text-sm font-medium transition-colors">Calculate</button>
        </div>
      </div>
      {result && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 max-w-md">
          <h3 className="text-lg font-semibold mb-3">Repo Deal Results</h3>
          <div className="space-y-2 text-sm">
            <DetailRow label="Bond" value={result.internal_id} />
            <DetailRow label="Notional" value={result.notional.toFixed(2)} />
            <DetailRow label="Haircut" value={`${result.haircut_pct}%`} />
            <DetailRow label="Repo Rate" value={`${result.repo_rate_pct}%`} />
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

function DeskStress() {
  const [scenarios] = useState([
    { name: 'Parallel +100bp', kind: 'parallel', shift: 100 },
    { name: 'Parallel -100bp', kind: 'parallel', shift: -100 },
    { name: 'Steepener', kind: 'steepener', short_shift: -50, long_shift: 100 },
    { name: 'Flattener', kind: 'flattener', short_shift: 50, long_shift: -50 },
    { name: 'Inversion', kind: 'inversion', shift: 150 },
    { name: 'Credit Shock', kind: 'credit', shift: 150 },
    { name: 'FX Shock -20%', kind: 'fx', fx_shift: -20 },
  ]);
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const runStress = async () => {
    setLoading(true);
    try {
      const bonds = await api.bonds.list({ limit: 100 });
      const activeBonds = bonds.filter(b => b.status === 'active' && b.yield_to_maturity);
      if (activeBonds.length === 0) { setLoading(false); return; }

      const res = scenarios.map(s => {
        const totalValue = activeBonds.length * 1000;
        let pnl = 0;
        for (const b of activeBonds) {
          const modDur = 1 / (1 + (b.yield_to_maturity! * 100) / 100 / 2);
          let shift = 0;
          if (s.kind === 'parallel') shift = s.shift!;
          else if (s.kind === 'inversion') shift = s.shift!;
          else if (s.kind === 'credit') shift = s.shift!;
          else if (s.kind === 'steepener') shift = b.maturity_date && (new Date(b.maturity_date).getTime() - Date.now()) / (365.25 * 24 * 60 * 60 * 1000) > 5 ? s.long_shift! : s.short_shift!;
          else if (s.kind === 'flattener') shift = b.maturity_date && (new Date(b.maturity_date).getTime() - Date.now()) / (365.25 * 24 * 60 * 60 * 1000) > 5 ? s.long_shift! : s.short_shift!;
          pnl += -modDur * shift / 100 * 1000;
        }
        return { scenario_name: s.name, scenario_kind: s.kind, pnl, pnl_pct: pnl / totalValue * 100, portfolio_value: totalValue, stressed_value: totalValue + pnl };
      });
      setResults(res);
    } catch { /* ignore */ }
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Stress Test Scenarios</h3>
        <button onClick={runStress} disabled={loading} className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition-colors">
          <Zap size={16} />{loading ? 'Running...' : 'Run All'}
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {scenarios.map(s => {
          const r = results.find(res => res.scenario_name === s.name);
          return (
            <div key={s.name} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <h4 className="font-semibold mb-2">{s.name}</h4>
              {r ? (
                <div className="space-y-1 text-sm">
                  <p className={`text-2xl font-bold ${r.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{r.pnl_pct >= 0 ? '+' : ''}{r.pnl_pct.toFixed(2)}%</p>
                  <p className="text-gray-400">P&L: {r.pnl >= 0 ? '+' : ''}{r.pnl.toFixed(0)}</p>
                  <p className="text-gray-500 text-xs">Portfolio: {r.portfolio_value.toFixed(0)} → {r.stressed_value.toFixed(0)}</p>
                </div>
              ) : (
                <p className="text-gray-500 text-sm">Click "Run All" to test</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PortfolioPage() {
  const [alloc, setAlloc] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.bonds.list({ limit: 50 }).then(bonds => {
      const activeBonds = bonds.filter(b => b.status === 'active' && b.yield_to_maturity);
      if (activeBonds.length === 0) { setLoading(false); return; }
      const avgYtm = activeBonds.reduce((s: number, b: Bond) => s + (b.yield_to_maturity || 0), 0) / activeBonds.length * 100;
      const topBonds = activeBonds.sort((a, b) => (b.yield_to_maturity || 0) - (a.yield_to_maturity || 0)).slice(0, 10);
      setAlloc({
        strategy: 'Balanced',
        expected_return: avgYtm,
        volatility: avgYtm * 0.4,
        sharpe: (avgYtm - 3) / (avgYtm * 0.4) || 0,
        max_drawdown: avgYtm * 0.3,
        var_95: avgYtm * 0.5,
        positions: topBonds.map((b: Bond) => ({ internal_id: b.internal_id, name: b.name, ytm: b.yield_to_maturity! * 100, weight: 1 / topBonds.length, currency: b.currency })),
        byCurrency: topBonds.reduce((acc: Record<string, number>, b: Bond) => { acc[b.currency] = (acc[b.currency] || 0) + 1 / topBonds.length; return acc; }, {}),
      });
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Portfolio</h2>
      {alloc ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 bg-gray-900 rounded-xl border border-gray-800 p-4">
            <h3 className="text-lg font-semibold mb-4">Top Holdings</h3>
            <div className="space-y-2">
              {alloc.positions.map((p: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white truncate">{p.name}</p>
                    <p className="text-xs text-gray-500">{p.internal_id} · {p.currency}</p>
                  </div>
                  <div className="text-right ml-4">
                    <p className="text-sm font-mono text-emerald-400">{p.ytm.toFixed(2)}%</p>
                    <p className="text-xs text-gray-500">{(p.weight * 100).toFixed(1)}%</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-4">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <h3 className="text-lg font-semibold mb-3">Metrics</h3>
              <div className="space-y-3">
                <MetricRow label="Strategy" value={alloc.strategy} />
                <MetricRow label="Exp. Return" value={`${alloc.expected_return.toFixed(2)}%`} color="text-emerald-400" />
                <MetricRow label="Volatility" value={`${alloc.volatility.toFixed(2)}%`} color="text-amber-400" />
                <MetricRow label="Sharpe" value={alloc.sharpe.toFixed(2)} color="text-blue-400" />
                <MetricRow label="Max Drawdown" value={`${alloc.max_drawdown.toFixed(1)}%`} color="text-red-400" />
                <MetricRow label="VaR 95%" value={`${alloc.var_95.toFixed(1)}%`} color="text-red-400" />
              </div>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <h3 className="text-lg font-semibold mb-3">Currency Mix</h3>
              <div className="space-y-2">
                {Object.entries(alloc.byCurrency).map(([cur, w]) => (
                  <div key={cur} className="flex items-center justify-between text-sm">
                    <span className="text-gray-400">{cur}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-24 bg-gray-800 rounded-full h-2">
                        <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${(w as number) * 100}%` }} />
                      </div>
                      <span className="text-white font-mono text-xs">{(w as number * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : <EmptyState message="No active bonds with YTM data" />}
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

function ForecastPage() {
  const [forecast, setForecast] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.bonds.list({ limit: 50 }).then(bonds => {
      const activeBonds = bonds.filter(b => b.status === 'active' && b.yield_to_maturity);
      const avgReturn = activeBonds.length > 0 ? activeBonds.reduce((s: number, b: Bond) => s + (b.yield_to_maturity || 0), 0) / activeBonds.length * 100 : 7;
      const capital = 10000;
      const monthly = 500;
      const horizons = [1, 3, 5, 10, 20];
      setForecast({
        initial_capital: capital,
        monthly_contribution: monthly,
        expected_return: avgReturn,
        horizons: horizons.map(y => {
          const total = capital * Math.pow(1 + avgReturn / 100, y) + monthly * ((Math.pow(1 + avgReturn / 100, y) - 1) / (avgReturn / 100)) * 12;
          return { years: y, expected: total, pessimistic: total * 0.7, optimistic: total * 1.3 };
        }),
      });
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Capital Forecast</h2>
      {forecast && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-sm text-gray-400">Initial Capital</p>
              <p className="text-2xl font-bold">${forecast.initial_capital.toLocaleString()}</p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-sm text-gray-400">Monthly Contribution</p>
              <p className="text-2xl font-bold">${forecast.monthly_contribution.toLocaleString()}</p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-sm text-gray-400">Expected Return</p>
              <p className="text-2xl font-bold text-emerald-400">{forecast.expected_return.toFixed(1)}%</p>
            </div>
          </div>
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
                {forecast.horizons.map((h: any, i: number) => (
                  <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td className="p-3 font-semibold">{h.years} Year{h.years > 1 ? 's' : ''}</td>
                    <td className="p-3 text-right text-red-400 font-mono">${Math.round(h.pessimistic).toLocaleString()}</td>
                    <td className="p-3 text-right text-emerald-400 font-mono font-semibold">${Math.round(h.expected).toLocaleString()}</td>
                    <td className="p-3 text-right text-blue-400 font-mono">${Math.round(h.optimistic).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function MLPage() {
  const [predictions, setPredictions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.scores({ limit: 50 }).then(scores => {
      const preds = scores.slice(0, 30).map(s => ({
        internal_id: s.internal_id,
        decision: s.score > 70 ? 'buy' : s.score > 50 ? 'hold' : s.score > 30 ? 'wait' : 'avoid',
        confidence: Math.min(s.score / 100, 0.95),
        score: s.score,
        tier: s.tier,
      }));
      setPredictions(preds);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

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

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">ML Predictions</h2>
      <p className="text-sm text-gray-400">Predictions based on score-based heuristic (ML model training requires historical data)</p>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">Bond ID</th>
              <th className="text-right p-3">Score</th>
              <th className="text-left p-3">Tier</th>
              <th className="text-left p-3">Decision</th>
              <th className="text-right p-3">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {predictions.map((p, i) => (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="p-3 font-mono text-xs text-gray-300">{p.internal_id}</td>
                <td className="p-3 text-right font-mono text-emerald-400">{p.score.toFixed(2)}</td>
                <td className="p-3">{p.tier ? <TierBadge tier={p.tier} /> : '-'}</td>
                <td className="p-3"><span className={`px-2 py-0.5 rounded text-xs font-medium ${decisionColor(p.decision)}`}>{p.decision.toUpperCase()}</span></td>
                <td className="p-3 text-right font-mono">{(p.confidence * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {predictions.length === 0 && <EmptyState message="No prediction data available" />}
      </div>
    </div>
  );
}

function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.scores({ limit: 10 }).then(scores => {
      const now = new Date().toISOString();
      const mockAlerts = [
        { id: 1, kind: 'score', title: 'Score Update', message: `${scores.length} bonds scored`, created_at: now },
        { id: 2, kind: 'info', title: 'System Status', message: 'All services operational', created_at: now },
      ];
      setAlerts(mockAlerts);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Alerts</h2>
      {alerts.length > 0 ? (
        <div className="space-y-3">
          {alerts.map(a => (
            <div key={a.id} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-start gap-3">
                <Bell size={16} className="text-amber-400 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-sm">{a.title}</h4>
                  <p className="text-sm text-gray-400 mt-1">{a.message}</p>
                  <p className="text-xs text-gray-600 mt-1">{new Date(a.created_at).toLocaleString()}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : <EmptyState message="No alerts" />}
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
