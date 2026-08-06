import { useState } from 'react';
import { useI18n } from './i18n';
import { Search, SlidersHorizontal, X, Star, RotateCcw, ChevronDown } from 'lucide-react';

export type RangeValue = [number | null, number | null];

export interface BondFiltersState {
  search: string;
  currencies: string[];
  statuses: string[];
  ytm: RangeValue;
  score: RangeValue;
  price: RangeValue;
  coupon: RangeValue;
  maturities: string[];
  favoritesOnly: boolean;
}

export const MATURITY_BUCKETS: { id: string; label: string }[] = [
  { id: '<1y', label: 'maturity.<1y' },
  { id: '1-3y', label: 'maturity.1-3y' },
  { id: '3-5y', label: 'maturity.3-5y' },
  { id: '5-10y', label: 'maturity.5-10y' },
  { id: '>10y', label: 'maturity.>10y' },
  { id: 'expired', label: 'maturity.expired' },
];

export const defaultFilters: BondFiltersState = {
  search: '',
  currencies: [],
  statuses: [],
  ytm: [null, null],
  score: [null, null],
  price: [null, null],
  coupon: [null, null],
  maturities: [],
  favoritesOnly: false,
};

export function activeFilterGroups(f: BondFiltersState): number {
  let n = 0;
  if (f.search.trim()) n++;
  if (f.currencies.length) n++;
  if (f.statuses.length) n++;
  if (f.ytm[0] != null || f.ytm[1] != null) n++;
  if (f.score[0] != null || f.score[1] != null) n++;
  if (f.price[0] != null || f.price[1] != null) n++;
  if (f.coupon[0] != null || f.coupon[1] != null) n++;
  if (f.maturities.length) n++;
  if (f.favoritesOnly) n++;
  return n;
}

interface RangeFilterProps {
  label: string;
  unit?: string;
  min: number;
  max: number;
  step?: number;
  value: RangeValue;
  onChange: (v: RangeValue) => void;
}

function RangeFilter({ label, unit = '', min, max, step = 1, value, onChange }: RangeFilterProps) {
  const lo = value[0] ?? min;
  const hi = value[1] ?? max;
  const loPct = ((lo - min) / (max - min)) * 100;
  const hiPct = ((hi - min) / (max - min)) * 100;

  const setLo = (v: number) => onChange([Math.min(v, hi), value[1]]);
  const setHi = (v: number) => onChange([value[0], Math.max(v, lo)]);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-[#516c79]">{label}</span>
        <div className="flex items-center gap-1 text-xs text-[#717680]">
          <input
            type="number"
            value={value[0] ?? ''}
            placeholder={String(min)}
            step={step}
            onChange={(e) => onChange([e.target.value === '' ? null : Number(e.target.value), value[1]])}
            className="w-16 bg-white border border-[#d6e2e6] rounded-md px-1.5 py-1 text-[#01121a] text-right"
          />
          <span>—</span>
          <input
            type="number"
            value={value[1] ?? ''}
            placeholder={String(max)}
            step={step}
            onChange={(e) => onChange([value[0], e.target.value === '' ? null : Number(e.target.value)])}
            className="w-16 bg-white border border-[#d6e2e6] rounded-md px-1.5 py-1 text-[#01121a] text-right"
          />
          {unit && <span className="w-5">{unit}</span>}
        </div>
      </div>
      <div className="range-dual">
        <div className="range-track" />
        <div className="range-fill" style={{ left: `${loPct}%`, width: `${hiPct - loPct}%` }} />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={lo}
          onChange={(e) => setLo(Number(e.target.value))}
          aria-label={`${label} min`}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={hi}
          onChange={(e) => setHi(Number(e.target.value))}
          aria-label={`${label} max`}
        />
      </div>
    </div>
  );
}

interface ChipToggleGroupProps {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
}

function ChipToggleGroup({ label, options, selected, onToggle }: ChipToggleGroupProps) {
  if (options.length === 0) return null;
  return (
    <div>
      <div className="text-xs font-medium text-[#516c79] mb-2">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((opt) => {
          const active = selected.includes(opt);
          return (
            <button
              key={opt}
              type="button"
              onClick={() => onToggle(opt)}
              className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                active
                  ? 'bg-[#004b65] border-[#004b65] text-white'
                  : 'bg-white border-[#d6e2e6] text-[#516c79] hover:border-[#b2c9d1]'
              }`}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </div>
  );
}

interface BondFiltersProps {
  filters: BondFiltersState;
  onChange: (next: BondFiltersState) => void;
  currencyOptions: string[];
  statusOptions: string[];
  resultCount: number;
  totalCount: number;
}

export function BondFilters({
  filters,
  onChange,
  currencyOptions,
  statusOptions,
  resultCount,
  totalCount,
}: BondFiltersProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const groups = activeFilterGroups(filters);

  const update = (patch: Partial<BondFiltersState>) => onChange({ ...filters, ...patch });

  const toggleInArray = (key: 'currencies' | 'statuses' | 'maturities', v: string) => {
    const arr = filters[key];
    update({ [key]: arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v] } as Partial<BondFiltersState>);
  };

  const resetAll = () => {
    onChange({ ...defaultFilters });
  };

  const chips: { id: string; label: string; onRemove: () => void }[] = [];
  if (filters.search.trim())
    chips.push({ id: 'search', label: `${t('filters.search')}: «${filters.search.trim()}»`, onRemove: () => update({ search: '' }) });
  filters.currencies.forEach((c) =>
    chips.push({ id: `cur-${c}`, label: `${t('common.currency')}: ${c}`, onRemove: () => toggleInArray('currencies', c) }),
  );
  filters.statuses.forEach((s) =>
    chips.push({ id: `st-${s}`, label: `${t('common.status')}: ${s}`, onRemove: () => toggleInArray('statuses', s) }),
  );
  if (filters.ytm[0] != null || filters.ytm[1] != null)
    chips.push({
      id: 'ytm',
      label: `${t('filters.ytm')}: ${filters.ytm[0] != null ? `${t('filters.from')} ${filters.ytm[0]}%` : t('filters.any')} – ${filters.ytm[1] != null ? `${t('filters.to')} ${filters.ytm[1]}%` : '∞'}`,
      onRemove: () => update({ ytm: [null, null] }),
    });
  if (filters.score[0] != null || filters.score[1] != null)
    chips.push({
      id: 'score',
      label: `${t('common.score')}: ${filters.score[0] != null ? `${t('filters.from')} ${filters.score[0]}` : t('filters.any')} – ${filters.score[1] != null ? `${t('filters.to')} ${filters.score[1]}` : '∞'}`,
      onRemove: () => update({ score: [null, null] }),
    });
  if (filters.price[0] != null || filters.price[1] != null)
    chips.push({
      id: 'price',
      label: `${t('common.price')}: ${filters.price[0] != null ? `${t('filters.from')} ${filters.price[0]}` : t('filters.any')} – ${filters.price[1] != null ? `${t('filters.to')} ${filters.price[1]}` : '∞'}`,
      onRemove: () => update({ price: [null, null] }),
    });
  if (filters.coupon[0] != null || filters.coupon[1] != null)
    chips.push({
      id: 'coupon',
      label: `${t('common.coupon')}: ${filters.coupon[0] != null ? `${t('filters.from')} ${filters.coupon[0]}%` : t('filters.any')} – ${filters.coupon[1] != null ? `${t('filters.to')} ${filters.coupon[1]}%` : '∞'}`,
      onRemove: () => update({ coupon: [null, null] }),
    });
  filters.maturities.forEach((m) => {
    chips.push({ id: `mat-${m}`, label: `${t('filters.maturity')}: ${t(`maturity.${m}`)}`, onRemove: () => toggleInArray('maturities', m) });
  });
  if (filters.favoritesOnly)
    chips.push({ id: 'fav', label: t('filters.favoritesOnly'), onRemove: () => update({ favoritesOnly: false }) });

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="flex items-center gap-2 flex-1 bg-white border border-[#d6e2e6] rounded-xl px-3">
          <Search size={16} className="text-[#a4a7ae] shrink-0" />
          <input
            value={filters.search}
            onChange={(e) => update({ search: e.target.value })}
            placeholder={t('bonds.searchPlaceholder')}
            className="bg-transparent py-2.5 text-[#01121a] text-sm w-full outline-none placeholder:text-[#a4a7ae]"
          />
          {filters.search && (
            <button onClick={() => update({ search: '' })} className="text-[#a4a7ae] hover:text-[#01121a]" aria-label={t('bonds.clearSearch')}>
              <X size={15} />
            </button>
          )}
        </div>
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center justify-center gap-2 bg-white hover:bg-[#f5f9fb] border border-[#d6e2e6] rounded-xl px-4 py-2.5 text-sm text-[#01121a] transition-colors"
        >
          <SlidersHorizontal size={16} />
          {t('bonds.filters')}
          {groups > 0 && (
            <span className="bg-[#004b65] text-white text-xs rounded-full px-1.5 py-0.5 min-w-[1.25rem] text-center">
              {groups}
            </span>
          )}
          <ChevronDown size={15} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {open && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4 grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-5 animate-fadeIn shadow-sm">
          <ChipToggleGroup
            label={t('filters.currencyLabel')}
            options={currencyOptions}
            selected={filters.currencies}
            onToggle={(v) => toggleInArray('currencies', v)}
          />
          <ChipToggleGroup
            label={t('filters.statusLabel')}
            options={statusOptions}
            selected={filters.statuses}
            onToggle={(v) => toggleInArray('statuses', v)}
          />
          <div>
            <div className="text-xs font-medium text-[#516c79] mb-2">{t('filters.maturityLabel')}</div>
            <div className="flex flex-wrap gap-1.5">
              {MATURITY_BUCKETS.map((b) => {
                const active = filters.maturities.includes(b.id);
                return (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => toggleInArray('maturities', b.id)}
                    className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                      active
                        ? 'bg-[#004b65] border-[#004b65] text-white'
                        : 'bg-white border-[#d6e2e6] text-[#516c79] hover:border-[#b2c9d1]'
                    }`}
                  >
                    {t(`maturity.${b.id}`)}
                  </button>
                );
              })}
            </div>
          </div>

          <RangeFilter label={t('filters.ytmLabel')} unit="%" min={0} max={30} step={0.5} value={filters.ytm} onChange={(v) => update({ ytm: v })} />
          <RangeFilter label={t('common.score')} min={0} max={100} step={1} value={filters.score} onChange={(v) => update({ score: v })} />
          <RangeFilter label={t('common.price')} min={0} max={200} step={1} value={filters.price} onChange={(v) => update({ price: v })} />
          <RangeFilter label={t('common.coupon')} unit="%" min={0} max={30} step={0.5} value={filters.coupon} onChange={(v) => update({ coupon: v })} />

          <div className="lg:col-span-2 xl:col-span-3 flex items-center justify-between border-t border-[#d6e2e6] pt-3">
            <label className="flex items-center gap-2 text-sm text-[#516c79] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={filters.favoritesOnly}
                onChange={(e) => update({ favoritesOnly: e.target.checked })}
                className="accent-[#004b65] w-4 h-4"
              />
              <Star size={15} className={filters.favoritesOnly ? 'fill-[#004b65] text-[#004b65]' : 'text-[#a4a7ae]'} />
              {t('filters.favoritesOnly')}
            </label>
            <button
              onClick={resetAll}
              disabled={groups === 0}
              className="flex items-center gap-1.5 text-sm text-[#717680] hover:text-[#01121a] disabled:opacity-40"
            >
              <RotateCcw size={14} /> {t('common.resetAll')}
            </button>
          </div>
        </div>
      )}

      {(chips.length > 0 || open) && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-[#717680]">
            {t('common.found')}: <b className="text-[#01121a]">{resultCount}</b> {t('common.of')} {totalCount}
          </span>
          {chips.map((c) => (
            <span
              key={c.id}
              className="inline-flex items-center gap-1 bg-white border border-[#d6e2e6] rounded-full px-2.5 py-1 text-xs text-[#01121a]"
            >
              {c.label}
              <button onClick={c.onRemove} className="text-[#a4a7ae] hover:text-red-500" aria-label={t('common.removeFilter')}>
                <X size={12} />
              </button>
            </span>
          ))}
          {chips.length > 0 && (
            <button onClick={resetAll} className="text-xs text-[#717680] hover:text-[#01121a] underline">
              {t('common.reset')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
