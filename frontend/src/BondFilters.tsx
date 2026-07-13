import { useState } from 'react';
import { Search, SlidersHorizontal, X, Star, RotateCcw, ChevronDown } from 'lucide-react';

export type RangeValue = [number | null, number | null];

export interface BondFiltersState {
  search: string;
  currencies: string[];
  statuses: string[];
  ytm: RangeValue; // percent
  score: RangeValue; // 0..100
  price: RangeValue;
  coupon: RangeValue; // percent
  maturities: string[]; // bucket ids
  favoritesOnly: boolean;
}

export const MATURITY_BUCKETS: { id: string; label: string }[] = [
  { id: '<1y', label: 'до 1 г' },
  { id: '1-3y', label: '1–3 г' },
  { id: '3-5y', label: '3–5 л' },
  { id: '5-10y', label: '5–10 л' },
  { id: '>10y', label: 'более 10 л' },
  { id: 'expired', label: 'погашена' },
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

// Count of distinct filter *dimensions* that are active (used for the badge).
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
        <span className="text-xs font-medium text-gray-300">{label}</span>
        <div className="flex items-center gap-1 text-xs text-gray-400">
          <input
            type="number"
            value={value[0] ?? ''}
            placeholder={String(min)}
            step={step}
            onChange={(e) => onChange([e.target.value === '' ? null : Number(e.target.value), value[1]])}
            className="w-16 bg-gray-800 border border-gray-700 rounded-md px-1.5 py-1 text-white text-right"
          />
          <span>—</span>
          <input
            type="number"
            value={value[1] ?? ''}
            placeholder={String(max)}
            step={step}
            onChange={(e) => onChange([value[0], e.target.value === '' ? null : Number(e.target.value)])}
            className="w-16 bg-gray-800 border border-gray-700 rounded-md px-1.5 py-1 text-white text-right"
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
          aria-label={`${label}: минимум`}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={hi}
          onChange={(e) => setHi(Number(e.target.value))}
          aria-label={`${label}: максимум`}
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
      <div className="text-xs font-medium text-gray-300 mb-2">{label}</div>
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
                  ? 'bg-emerald-600 border-emerald-500 text-white'
                  : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
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

  // Build removable active-filter chips.
  const chips: { id: string; label: string; onRemove: () => void }[] = [];
  if (filters.search.trim())
    chips.push({ id: 'search', label: `Поиск: «${filters.search.trim()}»`, onRemove: () => update({ search: '' }) });
  filters.currencies.forEach((c) =>
    chips.push({ id: `cur-${c}`, label: `Валюта: ${c}`, onRemove: () => toggleInArray('currencies', c) }),
  );
  filters.statuses.forEach((s) =>
    chips.push({ id: `st-${s}`, label: `Статус: ${s}`, onRemove: () => toggleInArray('statuses', s) }),
  );
  if (filters.ytm[0] != null || filters.ytm[1] != null)
    chips.push({
      id: 'ytm',
      label: `YTM: ${filters.ytm[0] != null ? `от ${filters.ytm[0]}%` : 'любой'} – ${filters.ytm[1] != null ? `до ${filters.ytm[1]}%` : '∞'}`,
      onRemove: () => update({ ytm: [null, null] }),
    });
  if (filters.score[0] != null || filters.score[1] != null)
    chips.push({
      id: 'score',
      label: `Скор: ${filters.score[0] != null ? `от ${filters.score[0]}` : 'любой'} – ${filters.score[1] != null ? `до ${filters.score[1]}` : '∞'}`,
      onRemove: () => update({ score: [null, null] }),
    });
  if (filters.price[0] != null || filters.price[1] != null)
    chips.push({
      id: 'price',
      label: `Цена: ${filters.price[0] != null ? `от ${filters.price[0]}` : 'любая'} – ${filters.price[1] != null ? `до ${filters.price[1]}` : '∞'}`,
      onRemove: () => update({ price: [null, null] }),
    });
  if (filters.coupon[0] != null || filters.coupon[1] != null)
    chips.push({
      id: 'coupon',
      label: `Купон: ${filters.coupon[0] != null ? `от ${filters.coupon[0]}%` : 'любой'} – ${filters.coupon[1] != null ? `до ${filters.coupon[1]}%` : '∞'}`,
      onRemove: () => update({ coupon: [null, null] }),
    });
  filters.maturities.forEach((m) => {
    const b = MATURITY_BUCKETS.find((x) => x.id === m);
    chips.push({ id: `mat-${m}`, label: `Срок: ${b?.label ?? m}`, onRemove: () => toggleInArray('maturities', m) });
  });
  if (filters.favoritesOnly)
    chips.push({ id: 'fav', label: 'Только избранное', onRemove: () => update({ favoritesOnly: false }) });

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="flex items-center gap-2 flex-1 bg-gray-900 border border-gray-800 rounded-xl px-3">
          <Search size={16} className="text-gray-500 shrink-0" />
          <input
            value={filters.search}
            onChange={(e) => update({ search: e.target.value })}
            placeholder="Поиск по названию или ID"
            className="bg-transparent py-2.5 text-white text-sm w-full outline-none placeholder:text-gray-600"
          />
          {filters.search && (
            <button onClick={() => update({ search: '' })} className="text-gray-500 hover:text-white" aria-label="Очистить поиск">
              <X size={15} />
            </button>
          )}
        </div>
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center justify-center gap-2 bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-gray-200 transition-colors"
        >
          <SlidersHorizontal size={16} />
          Фильтры
          {groups > 0 && (
            <span className="bg-emerald-600 text-white text-xs rounded-full px-1.5 py-0.5 min-w-[1.25rem] text-center">
              {groups}
            </span>
          )}
          <ChevronDown size={15} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {open && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-5 animate-fadeIn">
          <ChipToggleGroup
            label="Валюта"
            options={currencyOptions}
            selected={filters.currencies}
            onToggle={(v) => toggleInArray('currencies', v)}
          />
          <ChipToggleGroup
            label="Статус"
            options={statusOptions}
            selected={filters.statuses}
            onToggle={(v) => toggleInArray('statuses', v)}
          />
          <div>
            <div className="text-xs font-medium text-gray-300 mb-2">Срок до погашения</div>
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
                        ? 'bg-emerald-600 border-emerald-500 text-white'
                        : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
                    }`}
                  >
                    {b.label}
                  </button>
                );
              })}
            </div>
          </div>

          <RangeFilter label="Доходность (YTM)" unit="%" min={0} max={30} step={0.5} value={filters.ytm} onChange={(v) => update({ ytm: v })} />
          <RangeFilter label="Скор" min={0} max={100} step={1} value={filters.score} onChange={(v) => update({ score: v })} />
          <RangeFilter label="Цена" min={0} max={200} step={1} value={filters.price} onChange={(v) => update({ price: v })} />
          <RangeFilter label="Купон" unit="%" min={0} max={30} step={0.5} value={filters.coupon} onChange={(v) => update({ coupon: v })} />

          <div className="lg:col-span-2 xl:col-span-3 flex items-center justify-between border-t border-gray-800 pt-3">
            <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={filters.favoritesOnly}
                onChange={(e) => update({ favoritesOnly: e.target.checked })}
                className="accent-amber-400 w-4 h-4"
              />
              <Star size={15} className={filters.favoritesOnly ? 'fill-amber-400 text-amber-400' : 'text-gray-500'} />
              Только избранное
            </label>
            <button
              onClick={resetAll}
              disabled={groups === 0}
              className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white disabled:opacity-40"
            >
              <RotateCcw size={14} /> Сбросить всё
            </button>
          </div>
        </div>
      )}

      {(chips.length > 0 || open) && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-500">
            Найдено: <b className="text-gray-300">{resultCount}</b> из {totalCount}
          </span>
          {chips.map((c) => (
            <span
              key={c.id}
              className="inline-flex items-center gap-1 bg-gray-800 border border-gray-700 rounded-full px-2.5 py-1 text-xs text-gray-200"
            >
              {c.label}
              <button onClick={c.onRemove} className="text-gray-500 hover:text-red-400" aria-label="Убрать фильтр">
                <X size={12} />
              </button>
            </span>
          ))}
          {chips.length > 0 && (
            <button onClick={resetAll} className="text-xs text-gray-500 hover:text-white underline">
              сбросить
            </button>
          )}
        </div>
      )}
    </div>
  );
}
