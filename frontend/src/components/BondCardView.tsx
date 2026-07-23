import { Star, TrendingUp, Lock } from 'lucide-react';
import type { Bond } from '../lib/api';

interface BondCardViewProps {
  bonds: Bond[];
  favorites: Set<string>;
  onToggleFav: (id: string) => void;
  onSelect: (bond: Bond) => void;
  onSubscribe?: () => void;
  scores?: Record<string, number>;
}

export default function BondCardView({ bonds, favorites, onToggleFav, onSelect, onSubscribe, scores }: BondCardViewProps) {
  if (bonds.length === 0) {
    return <div className="text-center py-8 text-gray-500 text-sm">Нет облигаций</div>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 sm:hidden">
      {bonds.map((bond) => (
        <div key={bond.internal_id} onClick={() => onSelect(bond)}
          className="bg-gray-900 border border-gray-800 rounded-xl p-4 cursor-pointer hover:border-gray-700 transition-colors active:scale-[0.98]">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-sm truncate">{bond.name}</p>
              <p className="text-xs text-gray-500 font-mono">{bond.internal_id}</p>
            </div>
            <button onClick={(e) => { e.stopPropagation(); onToggleFav(bond.internal_id); }}
              className="shrink-0 p-1 text-gray-500 hover:text-amber-400">
              <Star size={14} className={favorites.has(bond.internal_id) ? 'fill-amber-400 text-amber-400' : ''} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div><span className="text-gray-500">YTM</span><p className="text-white font-mono">{bond.yield_to_maturity != null ? `${bond.yield_to_maturity.toFixed(2)}%` : '—'}</p></div>
            <div><span className="text-gray-500">Купон</span><p className="text-white font-mono">{bond.coupon_rate != null ? `${bond.coupon_rate.toFixed(2)}%` : '—'}</p></div>
            <div><span className="text-gray-500">Цена</span><p className="text-white font-mono">{bond.price != null ? bond.price.toFixed(2) : '—'}</p></div>
            <div><span className="text-gray-500">Валюта</span><p className="text-white">{bond.currency}</p></div>
          </div>
          {scores && scores[bond.internal_id] != null && (
            <div className="mt-2 flex items-center gap-1">
              <TrendingUp size={12} className="text-emerald-400" />
              <span className="text-xs text-emerald-400 font-medium">Скор: {scores[bond.internal_id].toFixed(0)}</span>
            </div>
          )}
        </div>
      ))}
      {onSubscribe && (
        <button onClick={onSubscribe}
          className="flex items-center justify-center gap-2 bg-amber-600/20 border border-dashed border-amber-700/50 rounded-xl p-4 text-amber-400 text-sm hover:bg-amber-600/30 transition-colors">
          <Lock size={14} /> Открыть все облигации в Pro
        </button>
      )}
    </div>
  );
}
