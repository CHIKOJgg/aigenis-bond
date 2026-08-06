import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { common } from './dicts/common';
import { auth } from './dicts/auth';
import { landing } from './dicts/landing';
import { bonds } from './dicts/bonds';
import { stocks } from './dicts/stocks';
import { news } from './dicts/news';
import { chat } from './dicts/chat';
import { dashboard } from './dicts/dashboard';
import { desk } from './dicts/desk';
import { portfolio } from './dicts/portfolio';
import { forecast } from './dicts/forecast';
import { alerts } from './dicts/alerts';
import { calc } from './dicts/calc';
import { onboarding } from './dicts/onboarding';
import { widget } from './dicts/widget';
import { legal } from './dicts/legal';
import { app } from './dicts/app';
import { subscribe } from './dicts/subscribe';

export type Lang = 'ru' | 'en' | 'by';

type Dict = Record<string, string>;

// Russian is the source language (the app was originally Russian).
// English mirrors every key. t() falls back to Russian, then to the key
// itself, so missing translations never render blank.
const ru: Dict = { ...common.ru, ...auth.ru, ...landing.ru, ...bonds.ru, ...stocks.ru, ...news.ru, ...chat.ru, ...dashboard.ru, ...desk.ru, ...portfolio.ru, ...forecast.ru, ...alerts.ru, ...calc.ru, ...onboarding.ru, ...widget.ru, ...legal.ru, ...app.ru, ...subscribe.ru };
const en: Dict = { ...common.en, ...auth.en, ...landing.en, ...bonds.en, ...stocks.en, ...news.en, ...chat.en, ...dashboard.en, ...desk.en, ...portfolio.en, ...forecast.en, ...alerts.en, ...calc.en, ...onboarding.en, ...widget.en, ...legal.en, ...app.en, ...subscribe.en };
const by: Dict = { ...common.by, ...auth.by, ...landing.by, ...bonds.by, ...stocks.by, ...news.by, ...chat.by, ...dashboard.by, ...desk.by, ...portfolio.by, ...forecast.by, ...alerts.by, ...calc.by, ...onboarding.by, ...widget.by, ...legal.by, ...app.by, ...subscribe.by };

const dictionaries: Record<Lang, Dict> = { ru, en, by };

export { ru, en, by };

interface I18nValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem('lang') : null;
    if (saved === 'en' || saved === 'ru') return saved;
    const nav = typeof navigator !== 'undefined' && navigator.language ? navigator.language.toLowerCase() : '';
    return nav.startsWith('ru') ? 'ru' : 'en';
  });

  useEffect(() => {
    localStorage.setItem('lang', lang);
    document.documentElement.lang = lang;
  }, [lang]);

  const t = (key: string, vars?: Record<string, string | number>): string => {
    const dict = dictionaries[lang] ?? ru;
    let s: string = dict[key] ?? ru[key] ?? key;
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        s = s.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
      }
    }
    return s;
  };

  const setLang = (l: Lang) => setLangState(l);

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}

export function LanguageToggle() {
  const { lang, setLang } = useI18n();
  const cycle = () => {
    if (lang === 'ru') setLang('en');
    else if (lang === 'en') setLang('by');
    else setLang('ru');
  };
  const label = lang === 'ru' ? 'Switch to English' : lang === 'en' ? 'Switch to Belarusian' : 'Переключить на русский';
  return (
    <button
      onClick={cycle}
      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm text-aigenis-text-secondary hover:text-aigenis-text hover:bg-aigenis-50 whitespace-nowrap"
      aria-label={label}
      title={label}
    >
      <span className={lang === 'ru' ? 'font-semibold text-aigenis-text' : ''}>RU</span>
      <span className="text-aigenis-placeholder">/</span>
      <span className={lang === 'en' ? 'font-semibold text-aigenis-text' : ''}>EN</span>
      <span className="text-aigenis-placeholder">/</span>
      <span className={lang === 'by' ? 'font-semibold text-aigenis-text' : ''}>BY</span>
    </button>
  );
}
