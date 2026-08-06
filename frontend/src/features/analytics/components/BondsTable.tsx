import { Star, Download } from 'lucide-react';
import type { Bond } from '../../../lib/api';
import { BondIcon, CurrencyBadge, ScoreTierBadge, StatusBadge } from './badges';

export type SortDir = 'asc' | 'desc';

export function fmtDate(d: string | null | undefined): string {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

interface SortHeaderProps {
  k: string;
  label: string;
  sortKey: string;
  sortDir: SortDir;
  onSort: (key: string) => void;
  align?: 'left' | 'right';
}

function SortHeader({ k, label, sortKey, sortDir, onSort, align = 'left' }: SortHeaderProps) {
  const active = sortKey === k;
  return (
    <th
      onClick={() => onSort(k)}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      className={`px-3 py-3 text-xs font-semibold text-aigenis-placeholder uppercase tracking-wider border-b border-aigenis-border font-aigenis-heading whitespace-nowrap cursor-pointer select-none ${
        align === 'right' ? 'text-right' : 'text-left'
      } ${active ? 'text-aigenis-500' : ''}`}
    >
      {label}
      {active && <span className="ml-1">{sortDir === 'asc' ? '▲' : '▼'}</span>}
    </th>
  );
}

interface Props {
  loading: boolean;
  bonds: Bond[];
  scoreMap: Record<string, number>;
  favorites: Set<string>;
  sortKey: string;
  sortDir: SortDir;
  onSort: (key: string) => void;
  onToggleFav: (id: string) => void;
  onExportCsv: () => void;
}

export function BondsTable({ loading, bonds, scoreMap, favorites, sortKey, sortDir, onSort, onToggleFav, onExportCsv }: Props) {
  if (loading) {
    return <div className="py-10 text-center text-aigenis-placeholder">Загрузка данных…</div>;
  }

  return (
    <>
      <div className="bg-white rounded-xl border border-aigenis-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="bg-aigenis-surface">
                <th className="px-3 py-3 w-9 text-center" aria-label="Выбрать все">
                  <input type="checkbox" className="accent-aigenis-500" aria-label="Выбрать все" />
                </th>
                <th className="px-3 py-3 w-9"></th>
                <SortHeader k="name" label="Наименование" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                <SortHeader k="internal_id" label="ID" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                <SortHeader k="currency" label="Вал" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                <SortHeader k="yield_to_maturity" label="Доходность" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <SortHeader k="price" label="Цена" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <SortHeader k="coupon_rate" label="Купон" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <SortHeader k="score" label="Скор" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <SortHeader k="maturity_date" label="Погашение" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                <SortHeader k="status" label="Статус" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              </tr>
            </thead>
            <tbody>
              {bonds.map((b) => {
                const fav = favorites.has(b.internal_id);
                return (
                  <tr key={b.internal_id} className="border-b border-aigenis-row-border hover:bg-aigenis-hover">
                    <td className="px-3 py-3 text-center">
                      <input type="checkbox" className="accent-aigenis-500" aria-label={`Выбрать ${b.name}`} />
                    </td>
                    <td className="px-3 py-3">
                      <button
                        onClick={() => onToggleFav(b.internal_id)}
                        aria-label={fav ? `Убрать из избранного: ${b.name}` : `В избранное: ${b.name}`}
                        aria-pressed={fav}
                        className="bg-transparent border-none cursor-pointer p-0"
                      >
                        <Star size={16} fill={fav ? '#004b65' : 'none'} color={fav ? '#004b65' : '#d6e2e6'} />
                      </button>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2.5">
                        <BondIcon name={b.name} size={28} />
                        <div>
                          <div className="font-medium text-[13px]">{b.name}</div>
                          {b.issuer && <div className="text-[11px] text-aigenis-placeholder mt-0.5">{b.issuer}</div>}
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 font-mono text-[11px] text-aigenis-text-muted">{b.internal_id}</td>
                    <td className="px-3 py-3"><CurrencyBadge currency={b.currency} /></td>
                    <td className="px-3 py-3 text-right font-mono font-medium">
                      {b.yield_to_maturity != null ? `${b.yield_to_maturity.toFixed(2)}%` : '—'}
                    </td>
                    <td className="px-3 py-3 text-right font-mono">{b.price?.toFixed(2) ?? '—'}</td>
                    <td className="px-3 py-3 text-right font-mono text-aigenis-text-muted">{b.coupon_rate?.toFixed(2)}%</td>
                    <td className="px-3 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <span className="font-mono font-semibold text-aigenis-500">{scoreMap[b.internal_id]?.toFixed(1) ?? '—'}</span>
                        <ScoreTierBadge score={scoreMap[b.internal_id]} />
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs text-aigenis-text-muted">{fmtDate(b.maturity_date)}</td>
                    <td className="px-3 py-3"><StatusBadge status={b.status} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {bonds.length === 0 && (
          <div className="py-10 text-center text-aigenis-placeholder">Ничего не найдено. Попробуйте изменить фильтры.</div>
        )}
      </div>

      {bonds.length > 0 && (
        <div className="mt-3.5">
          <button
            onClick={onExportCsv}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-full border border-aigenis-border bg-white text-aigenis-text text-[13px] font-medium cursor-pointer font-aigenis-body"
          >
            <Download size={15} /> Экспорт CSV
          </button>
        </div>
      )}
    </>
  );
}
