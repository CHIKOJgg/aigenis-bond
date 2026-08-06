import type { Bond } from '../lib/api';

export function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1.5 border-b border-[#d6e2e6] last:border-0">
      <span className="text-[#516c79]">{label}</span>
      <span className="text-[#01121a] font-medium text-right max-w-[60%] truncate">{value}</span>
    </div>
  );
}

export function InputField({ label, value, onChange, placeholder, type = 'text' }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <div>
      <label className="text-sm text-[#516c79] block mb-1">{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} type={type}
        className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
    </div>
  );
}

export function MetricRow({ label, value, color = 'text-[#01121a]' }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-[#516c79]">{label}</span>
      <span className={`text-sm font-semibold ${color}`}>{value}</span>
    </div>
  );
}

export function StatCard({ icon: Icon, label, value, color }: { icon: any; label: string; value: string | number; color: string }) {
  return (
    <div className="bg-white rounded-xl p-4 border border-[#d6e2e6]">
      <div className={`w-10 h-10 bg-gradient-to-br ${color} rounded-lg flex items-center justify-center mb-3`}>
        <Icon size={20} className="text-white" />
      </div>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-sm text-[#516c79]">{label}</p>
    </div>
  );
}

export function BondRow({ bond }: { bond: Bond }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[#d6e2e6] last:border-0">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <BondIcon issuer={bond.issuer} logo={bond.issuer_logo} />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-[#01121a] truncate">{bond.name}</p>
          <p className="text-xs text-[#717680]">{bond.internal_id} · {bond.currency}</p>
        </div>
      </div>
      <div className="text-right ml-4">
        <p className="text-sm font-mono">{bond.price != null ? bond.price.toFixed(2) : '-'}</p>
        <p className="text-xs text-[#516c79]">{bond.status}</p>
      </div>
    </div>
  );
}

export function BondIcon({ issuer, logo, size = 20 }: { issuer?: string | null; logo?: string | null; size?: number }) {
  const initial = (issuer || '?').trim().charAt(0).toUpperCase() || '?';
  const dim = { width: size, height: size };
  if (logo) {
    return (
      <img
        src={logo}
        alt={issuer || ''}
        width={size}
        height={size}
        style={dim}
        className="rounded-full object-cover bg-[#f8fafb] ring-1 ring-[#d6e2e6] shrink-0"
        loading="lazy"
      />
    );
  }
  return (
    <span
      style={dim}
      className="rounded-full bg-gradient-to-br from-[#004b65] to-[#387387] text-white flex items-center justify-center text-[10px] font-bold shrink-0 ring-1 ring-[#d6e2e6]"
    >
      {initial}
    </span>
  );
}

export function maturityBucket(b: Bond): string | null {
  if (!b.maturity_date) return null;
  const yrs = (new Date(b.maturity_date).getTime() - Date.now()) / (365.25 * 24 * 3600 * 1000);
  if (yrs < 0) return 'expired';
  if (yrs < 1) return '<1y';
  if (yrs < 3) return '1-3y';
  if (yrs < 5) return '3-5y';
  if (yrs < 10) return '5-10y';
  return '>10y';
}

export function defaultForPreset(id: string): Record<string, unknown> {
  switch (id) {
    case 'ytm10': return { ytm: [null, null] };
    case 'score70': return { score: [null, null] };
    case 'active': return { statuses: [] };
    case 'short': return { maturities: [] };
    case 'fav': return { favoritesOnly: false };
    default: return {};
  }
}
