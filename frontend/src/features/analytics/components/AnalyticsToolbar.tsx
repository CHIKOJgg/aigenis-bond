import { RotateCcw, Search, Star, X } from 'lucide-react';

export interface PresetDef {
  id: string;
  label: string;
}

export const PRESET_DEFS: PresetDef[] = [
  { id: 'ytm10', label: 'YTM ≥ 10%' },
  { id: 'score70', label: 'Скор ≥ 70' },
  { id: 'active', label: 'Только active' },
  { id: 'short', label: 'Короткие (<3 г)' },
  { id: 'fav', label: 'Избранное' },
];

interface Props {
  search: string;
  onSearch: (value: string) => void;
  activePresets: Set<string>;
  onTogglePreset: (id: string) => void;
  onReset: () => void;
  found: number;
  total: number;
}

export function AnalyticsToolbar({ search, onSearch, activePresets, onTogglePreset, onReset, found, total }: Props) {
  return (
    <>
      <div className="flex items-center gap-2.5 border border-aigenis-border rounded-[10px] px-4 py-2.5 bg-white mb-3.5 max-w-[400px]">
        <Search size={18} className="text-aigenis-placeholder shrink-0" />
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Поиск по названию"
          aria-label="Поиск по названию"
          className="border-none outline-none flex-1 text-sm text-aigenis-text bg-transparent font-aigenis-body"
        />
        {search && (
          <button
            onClick={() => onSearch('')}
            aria-label="Очистить поиск"
            className="bg-transparent border-none cursor-pointer text-aigenis-placeholder p-0"
          >
            <X size={16} />
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {PRESET_DEFS.map((p) => {
          const active = activePresets.has(p.id);
          return (
            <button
              key={p.id}
              onClick={() => onTogglePreset(p.id)}
              aria-pressed={active}
              className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-[13px] font-medium cursor-pointer font-aigenis-body ${
                active
                  ? 'border-[1.5px] border-aigenis-500 bg-aigenis-50 text-aigenis-500'
                  : 'border border-aigenis-border bg-white text-aigenis-text-secondary'
              }`}
            >
              {p.id === 'fav' && <Star size={14} fill={active ? 'currentColor' : 'none'} />}
              {p.label}
            </button>
          );
        })}
        {activePresets.size > 0 && (
          <button
            onClick={onReset}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border-none bg-transparent text-aigenis-text-muted text-xs cursor-pointer font-aigenis-body"
          >
            <RotateCcw size={13} /> Сбросить
          </button>
        )}
        <span className="text-xs text-aigenis-placeholder flex items-center ml-2">
          Найдено: <b className="text-aigenis-text mx-1">{found}</b> из {total}
        </span>
      </div>
    </>
  );
}
