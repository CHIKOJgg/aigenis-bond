import type { CompanySummary } from '../../../lib/api';
import { BondIcon } from './badges';

interface Props {
  loading: boolean;
  companies: CompanySummary[];
}

export function CompaniesGrid({ loading, companies }: Props) {
  if (loading) {
    return <div className="py-10 text-center text-aigenis-placeholder">Загрузка данных…</div>;
  }

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
      {companies.map((c) => (
        <div key={c.issuer} className="bg-white rounded-xl border border-aigenis-border p-4">
          <div className="flex items-center gap-2.5">
            <BondIcon name={c.name} size={36} />
            <div className="min-w-0">
              <div className="font-semibold text-sm whitespace-nowrap overflow-hidden text-ellipsis">{c.name}</div>
              <div className="text-[11px] text-aigenis-placeholder mt-0.5">{c.issuer}</div>
            </div>
          </div>
          <div className="flex gap-3 mt-3 text-xs text-aigenis-text-secondary">
            {c.sector && (
              <span className="px-2 py-0.5 rounded-[6px] bg-aigenis-surface-subtle text-aigenis-text-secondary font-medium">
                {c.sector}
              </span>
            )}
            <span><b className="text-aigenis-text">{c.bond_count}</b> выпусков</span>
            {c.avg_yield_to_maturity != null && (
              <span>YTM <b className="text-aigenis-500">{c.avg_yield_to_maturity}%</b></span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
