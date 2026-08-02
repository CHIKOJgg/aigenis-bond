import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type Theme = 'dark' | 'dim' | 'light';

const STORAGE_KEY = 'aigenis_theme';

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'dim' || saved === 'light') return saved;
    return 'dark';
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, theme);
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const setTheme = (t: Theme) => setThemeState(t);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const themes: { key: Theme; label: string }[] = [
    { key: 'dark', label: '🌙' },
    { key: 'dim', label: '🌓' },
    { key: 'light', label: '☀️' },
  ];

  return (
    <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-0.5">
      {themes.map((t) => (
        <button
          key={t.key}
          onClick={() => setTheme(t.key)}
          className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
            theme === t.key ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white'
          }`}
          title={t.key}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
