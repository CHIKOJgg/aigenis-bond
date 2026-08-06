import { useState } from 'react';
import { Search } from 'lucide-react';
import type { BondScore } from '../../../lib/api';
import { ScoreTierBadge } from './badges';

interface Props {
  loading: boolean;
  scores: BondScore[];
}

export function ScoresTable({ loading, scores }: Props) {
  const [q, setQ] = useState('');
  const rows = q
    ? scores.filter((s) => s.internal_id.toLowerCase().includes(q.toLowerCase()))
    : scores.slice(0, 200);

  if (loading) {
    return <div className="py-10 text-center text-aigenis-placeholder">Загрузка данных…</div>;
  }

  return (
    <>
      <div className="flex items-center gap-2.5 border border-aigenis-border rounded-[10px] px-4 py-2.5 bg-white mb-3.5 max-w-[400px]">
        <Search size={18} className="text-aigenis-placeholder shrink-0" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по ID"
          aria-label="Поиск по ID"
          className="border-none outline-none flex-1 text-sm text-aigenis-text bg-transparent font-aigenis-body"
        />
      </div>
      <div className="bg-white rounded-xl border border-aigenis-border overflow-hidden">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="bg-aigenis-surface">
              <th className="px-3 py-3 text-xs font-semibold text-aigenis-placeholder uppercase tracking-wider border-b border-aigenis-border font-aigenis-heading">#</th>
              <th className="px-3 py-3 text-xs font-semibold text-aigenis-placeholder uppercase tracking-wider border-b border-aigenis-border font-aigenis-heading">Bond ID</th>
              <th className="px-3 py-3 text-xs font-semibold text-aigenis-placeholder uppercase tracking-wider border-b border-aigenis-border font-aigenis-heading text-right">Score</th>
              <th className="px-3 py-3 text-xs font-semibold text-aigenis-placeholder uppercase tracking-wider border-b border-aigenis-border font-aigenis-heading">Tier</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => (
              <tr key={s.internal_id} className="border-b border-aigenis-row-border">
                <td className="px-3 py-3 text-aigenis-placeholder text-xs">{i + 1}</td>
                <td className="px-3 py-3 font-mono text-xs text-aigenis-text-secondary">{s.internal_id}</td>
                <td className="px-3 py-3 text-right font-mono font-semibold text-aigenis-500">{s.score.toFixed(2)}</td>
                <td className="px-3 py-3"><ScoreTierBadge score={s.score} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="py-10 text-center text-aigenis-placeholder">Ничего не найдено</div>}
      </div>
    </>
  );
}
