import { useState, useRef, useEffect } from 'react';
import { Search, X, TrendingUp, Building2, FileText } from 'lucide-react';

interface SearchResult {
  type: 'bond' | 'company' | 'news';
  id: string;
  label: string;
  sublabel?: string;
}

interface SmartSearchProps {
  onSelect: (result: SearchResult) => void;
  placeholder?: string;
}

const MOCK_BONDS = [
  { id: 'BYN_001', label: 'ОАО "АСБ Беларусбанк" Обл 1', sublabel: 'BYN · 12.5%' },
  { id: 'USD_002', label: 'ЗАО "МТБанк" Обл 2', sublabel: 'USD · 8.5%' },
  { id: 'RUB_003', label: 'ООО "Развитие" Обл 3', sublabel: 'RUB · 15%' },
];

export default function SmartSearch({ onSelect, placeholder = 'Поиск облигаций, эмитентов...' }: SmartSearchProps) {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setFocused(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const results: SearchResult[] = query.length > 0
    ? [
        ...MOCK_BONDS
          .filter((b) => b.label.toLowerCase().includes(query.toLowerCase()) || b.id.toLowerCase().includes(query.toLowerCase()))
          .map((b) => ({ type: 'bond' as const, id: b.id, label: b.label, sublabel: b.sublabel })),
      ]
    : [];

  const handleSelect = (r: SearchResult) => {
    onSelect(r);
    setQuery('');
    setFocused(false);
  };

  return (
    <div ref={ref} className="relative max-w-md w-full">
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          placeholder={placeholder}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-8 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 transition-colors"
        />
        {query && (
          <button onClick={() => setQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white">
            <X size={14} />
          </button>
        )}
      </div>

      {focused && results.length > 0 && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-gray-900 border border-gray-800 rounded-xl shadow-2xl overflow-hidden z-50 animate-fadeIn">
          {results.map((r) => (
            <button
              key={`${r.type}-${r.id}`}
              onClick={() => handleSelect(r)}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-800 transition-colors text-left"
            >
              <span className="w-8 h-8 rounded-lg bg-gray-800 flex items-center justify-center text-gray-400 shrink-0">
                {r.type === 'bond' ? <TrendingUp size={14} /> : r.type === 'company' ? <Building2 size={14} /> : <FileText size={14} />}
              </span>
              <div className="min-w-0">
                <p className="text-sm text-white truncate">{r.label}</p>
                {r.sublabel && <p className="text-xs text-gray-500 truncate">{r.sublabel}</p>}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
