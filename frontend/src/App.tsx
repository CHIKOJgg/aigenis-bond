import { useEffect, useState } from 'react';
import { api } from './lib/api';
import { BarChart3, Shield, Banknote, Activity, TrendingUp, Search } from 'lucide-react';

type Page = 'dashboard' | 'bonds' | 'scores';

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-bold flex items-center gap-2">
            <TrendingUp className="text-emerald-400" size={22} />
            Aigenis Bonds
          </h1>
          <nav className="flex gap-1">
            {(['dashboard', 'bonds', 'scores'] as Page[]).map(p => (
              <button key={p} onClick={() => setPage(p)}
                className={`px-4 py-2 rounded-lg text-sm capitalize ${page === p ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}>
                {p === 'dashboard' ? 'Dashboard' : p === 'bonds' ? 'Bonds' : 'Scores'}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="max-w-7xl mx-auto p-4">
        {page === 'dashboard' && <Dashboard />}
        {page === 'bonds' && <BondsPage />}
        {page === 'scores' && <ScoresPage />}
      </main>
    </div>
  );
}

function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [bonds, setBonds] = useState<any[]>([]);
  const [scores, setScores] = useState<any[]>([]);

  useEffect(() => {
    api.stats().then(setStats).catch(() => {});
    api.bonds.list({ limit: 5 }).then(setBonds).catch(() => {});
    api.scores({ limit: 5 }).then(setScores).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Banknote} label="Total Bonds" value={stats.total_bonds} color="bg-emerald-500" />
          <StatCard icon={Activity} label="Active Bonds" value={stats.active_bonds} color="bg-blue-500" />
          <StatCard icon={Shield} label="Top Score" value={scores[0]?.score?.toFixed(1) || '-'} color="bg-purple-500" />
          {Object.entries(stats.by_currency).slice(0, 1).map(([cur, count]) => (
            <StatCard key={cur} icon={BarChart3} label={`${cur} Bonds`} value={count as number} color="bg-amber-500" />
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3">Recent Bonds</h3>
          {bonds.map(b => <BondRow key={b.internal_id} bond={b} />)}
          {bonds.length === 0 && <p className="text-gray-500 text-sm">No data</p>}
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h3 className="text-lg font-semibold mb-3">Top Scores</h3>
          {scores.map((s: any) => (
            <div key={s.internal_id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
              <span className="text-sm text-gray-300">{s.internal_id}</span>
              <div className="flex items-center gap-2">
                <span className="text-sm font-mono text-emerald-400">{s.score.toFixed(2)}</span>
                {s.tier && <span className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400">{s.tier}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: { icon: any; label: string; value: string | number; color: string }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className={`w-10 h-10 ${color} rounded-lg flex items-center justify-center mb-3`}>
        <Icon size={20} className="text-white" />
      </div>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-sm text-gray-400">{label}</p>
    </div>
  );
}

function BondRow({ bond }: { bond: any }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
      <div>
        <p className="text-sm text-white">{bond.name}</p>
        <p className="text-xs text-gray-500">{bond.internal_id} · {bond.currency}</p>
      </div>
      <div className="text-right">
        <p className="text-sm font-mono">{bond.price != null ? bond.price.toFixed(2) : '-'}</p>
        <p className="text-xs text-gray-400">{bond.status}</p>
      </div>
    </div>
  );
}

function BondsPage() {
  const [bonds, setBonds] = useState<any[]>([]);
  const [currency, setCurrency] = useState('');

  useEffect(() => {
    api.bonds.list({ currency: currency || undefined, limit: 50 }).then(setBonds).catch(() => {});
  }, [currency]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Bonds</h2>
        <div className="flex items-center gap-2">
          <Search size={16} className="text-gray-500" />
          <input value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())} placeholder="Filter by currency (USD, BYN...)"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-48" />
        </div>
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">ID</th>
              <th className="text-left p-3">Currency</th>
              <th className="text-right p-3">Price</th>
              <th className="text-right p-3">YTM</th>
              <th className="text-right p-3">Coupon</th>
              <th className="text-left p-3">Maturity</th>
              <th className="text-left p-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {bonds.map(b => (
              <tr key={b.internal_id} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="p-3 text-white">{b.name}</td>
                <td className="p-3 text-gray-400 font-mono text-xs">{b.internal_id}</td>
                <td className="p-3">{b.currency}</td>
                <td className="p-3 text-right font-mono">{b.price?.toFixed(2) ?? '-'}</td>
                <td className="p-3 text-right font-mono">{b.yield_to_maturity != null ? `${(b.yield_to_maturity * 100).toFixed(2)}%` : '-'}</td>
                <td className="p-3 text-right font-mono">{b.coupon_rate != null ? `${(b.coupon_rate * 100).toFixed(2)}%` : '-'}</td>
                <td className="p-3 text-gray-400 text-xs">{b.maturity_date ? new Date(b.maturity_date).toLocaleDateString() : '-'}</td>
                <td className="p-3"><span className={`px-2 py-0.5 rounded text-xs ${b.status === 'active' ? 'bg-green-900 text-green-300' : 'bg-gray-800 text-gray-400'}`}>{b.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {bonds.length === 0 && <p className="text-gray-500 text-sm text-center py-8">No bonds found.</p>}
      </div>
    </div>
  );
}

function ScoresPage() {
  const [scores, setScores] = useState<any[]>([]);
  const [minScore, setMinScore] = useState('');

  useEffect(() => {
    api.scores({ min_score: minScore ? Number(minScore) : undefined, limit: 100 }).then(setScores).catch(() => {});
  }, [minScore]);

  const tierColor = (t: string) =>
    t === 'A' ? 'text-emerald-400' : t === 'B' ? 'text-blue-400' : t === 'C' ? 'text-amber-400' : 'text-gray-400';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Bond Scores</h2>
        <input value={minScore} onChange={e => setMinScore(e.target.value)} placeholder="Min score" type="number" step="0.1"
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-32" />
      </div>
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">Bond ID</th>
              <th className="text-right p-3">Score</th>
              <th className="text-left p-3">Tier</th>
            </tr>
          </thead>
          <tbody>
            {scores.map((s: any) => (
              <tr key={s.internal_id} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="p-3 font-mono text-xs text-gray-300">{s.internal_id}</td>
                <td className="p-3 text-right font-mono text-emerald-400">{s.score.toFixed(2)}</td>
                <td className="p-3"><span className={`font-medium ${tierColor(s.tier)}`}>{s.tier || '-'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {scores.length === 0 && <p className="text-gray-500 text-sm text-center py-8">No scores found.</p>}
      </div>
    </div>
  );
}
