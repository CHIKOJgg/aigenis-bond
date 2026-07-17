import { useState } from 'react';
import type { ReactNode } from 'react';

export function CurrencyBadge({ currency }: { currency: string }) {
  const colors: Record<string, string> = {
    USD: 'bg-blue-900 text-blue-300',
    BYN: 'bg-green-900 text-green-300',
    EUR: 'bg-purple-900 text-green-300',
    XAU: 'bg-amber-900 text-amber-300',
    XAG: 'bg-gray-700 text-gray-300',
    XPT: 'bg-slate-700 text-slate-300',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[currency] || 'bg-gray-800 text-gray-400'}`}>
      {currency}
    </span>
  );
}

export function BondIcon({ issuer, logo, size = 20 }: { issuer?: string | null; logo?: string | null; size?: number }) {
  const [errored, setErrored] = useState(false);
  const initial = (issuer || '?').trim().charAt(0).toUpperCase() || '?';
  const dim = { width: size, height: size };
  if (logo && !errored) {
    return (
      <img
        src={logo}
        alt={issuer || ''}
        width={size}
        height={size}
        style={dim}
        className="rounded-full object-cover bg-gray-800 ring-1 ring-gray-700 shrink-0"
        onError={() => setErrored(true)}
        loading="lazy"
      />
    );
  }
  return (
    <span
      style={dim}
      className="rounded-full bg-gradient-to-br from-emerald-700 to-emerald-900 text-emerald-200 flex items-center justify-center text-[10px] font-bold shrink-0 ring-1 ring-gray-700"
    >
      {initial}
    </span>
  );
}

export function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return null;
  const colors: Record<string, string> = {
    A: 'bg-emerald-900 text-emerald-300',
    B: 'bg-blue-900 text-blue-300',
    C: 'bg-amber-900 text-amber-300',
    D: 'bg-red-900 text-red-300',
  };
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[tier] || 'bg-gray-800 text-gray-400'}`}>{tier}</span>;
}

const DECISION_STYLES: Record<string, { label: string; cls: string; dot: string }> = {
  buy: { label: 'Покупать', cls: 'bg-emerald-900/40 text-emerald-300 border-emerald-700', dot: 'bg-emerald-400' },
  hold: { label: 'Держать', cls: 'bg-blue-900/40 text-blue-300 border-blue-700', dot: 'bg-blue-400' },
  wait: { label: 'Подождать', cls: 'bg-amber-900/40 text-amber-300 border-amber-700', dot: 'bg-amber-400' },
  avoid: { label: 'Избегать', cls: 'bg-red-900/40 text-red-300 border-red-700', dot: 'bg-red-400' },
};

export function DecisionBadge({ decision, size = 'sm' }: { decision: string; size?: 'sm' | 'lg' }) {
  const d = DECISION_STYLES[decision] || DECISION_STYLES.wait;
  const pad = size === 'lg' ? 'px-3 py-1.5 text-sm' : 'px-2 py-0.5 text-xs';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${d.cls} ${pad}`}>
      <span className={`w-2 h-2 rounded-full ${d.dot}`} />
      {d.label}
    </span>
  );
}

export function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-gray-800 rounded-xl h-24" />
        ))}
      </div>
      <div className="bg-gray-800 rounded-xl h-64" />
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 bg-red-900/30 border border-red-800 rounded-xl p-4">
      <span className="text-red-400 shrink-0">⚠</span>
      <p className="text-sm text-red-300">{message}</p>
    </div>
  );
}

export function EmptyState({ message, className = '' }: { message: string; className?: string }) {
  return <p className={`text-gray-500 text-sm text-center py-8 ${className}`}>{message}</p>;
}

export function SectionTitle({ icon, title, action }: { icon?: ReactNode; title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="text-xl font-bold flex items-center gap-2">
        {icon}
        {title}
      </h2>
      {action}
    </div>
  );
}
