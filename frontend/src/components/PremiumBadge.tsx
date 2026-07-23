import { Lock, Star } from 'lucide-react';

interface PremiumBadgeProps {
  tier: 'pro' | 'enterprise';
  size?: 'sm' | 'md';
}

export default function PremiumBadge({ tier, size = 'sm' }: PremiumBadgeProps) {
  const isEnterprise = tier === 'enterprise';
  const sizeClasses = size === 'sm' ? 'text-[9px] px-1.5 py-0.5' : 'text-[10px] px-2 py-0.5';

  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-full font-semibold uppercase tracking-wider ${sizeClasses} ${
        isEnterprise
          ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
          : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
      }`}
    >
      {isEnterprise ? <Lock size={8} /> : <Star size={8} />}
      {tier}
    </span>
  );
}
