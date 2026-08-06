import { useState } from 'react';
import type { ReactNode } from 'react';

export function CurrencyBadge({ currency }: { currency: string }) {
  const colors: Record<string, string> = {
    USD: 'bg-blue-50 text-blue-700',
    BYN: 'bg-green-50 text-green-700',
    EUR: 'bg-purple-50 text-purple-700',
    XAU: 'bg-amber-50 text-amber-700',
    XAG: 'bg-slate-50 text-slate-700',
    XPT: 'bg-slate-50 text-slate-600',
    CNY: 'bg-rose-50 text-rose-700',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[currency] || 'bg-[#f8fafb] text-[#516c79]'}`}>
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
        className="rounded-full object-cover bg-[#f8fafb] ring-1 ring-[#d6e2e6] shrink-0"
        onError={() => setErrored(true)}
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

export function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return null;
  const colors: Record<string, string> = {
    S: 'bg-[#004b65] text-white',
    A: 'bg-[#387387] text-white',
    B: 'bg-[#759eac] text-[#001d25]',
    C: 'bg-amber-100 text-amber-800',
    D: 'bg-red-100 text-red-800',
  };
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[tier] || 'bg-[#f8fafb] text-[#516c79]'}`}>{tier}</span>;
}

const DECISION_STYLES: Record<string, { label: string; cls: string; dot: string }> = {
  buy: { label: 'Покупать', cls: 'bg-green-50 text-green-700 border-green-200', dot: 'bg-green-600' },
  hold: { label: 'Держать', cls: 'bg-blue-50 text-blue-700 border-blue-200', dot: 'bg-blue-600' },
  wait: { label: 'Подождать', cls: 'bg-amber-50 text-amber-700 border-amber-200', dot: 'bg-amber-600' },
  avoid: { label: 'Избегать', cls: 'bg-red-50 text-red-700 border-red-200', dot: 'bg-red-600' },
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
          <div key={i} className="bg-[#eef3f5] rounded-xl h-24" />
        ))}
      </div>
      <div className="bg-[#eef3f5] rounded-xl h-64" />
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
      <span className="text-red-500 shrink-0">⚠</span>
      <p className="text-sm text-red-700">{message}</p>
    </div>
  );
}

export function EmptyState({ message, className = '' }: { message: string; className?: string }) {
  return <p className={`text-[#a4a7ae] text-sm text-center py-8 ${className}`}>{message}</p>;
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
