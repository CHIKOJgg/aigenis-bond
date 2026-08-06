import { useLocation, useNavigate } from 'react-router-dom';
import { Brain, TrendingUp, PieChart, Clock, Bell, Calculator } from 'lucide-react';

export type AnalyticsTab = 'bonds' | 'scores' | 'companies';

export const TAB_LABELS: Record<AnalyticsTab, string> = {
  bonds: 'Облигации',
  scores: 'Скоры',
  companies: 'Компании',
};

const SUB_NAV: { id: string; label: string; icon: React.ReactNode; path: string }[] = [
  { id: 'recommendations', label: 'Рекомендации', icon: <Brain size={16} />, path: '/recommendations' },
  { id: 'desk', label: 'Desk', icon: <TrendingUp size={16} />, path: '/desk' },
  { id: 'portfolio', label: 'Портфель', icon: <PieChart size={16} />, path: '/portfolio' },
  { id: 'forecast', label: 'Прогноз', icon: <Clock size={16} />, path: '/forecast' },
  { id: 'alerts', label: 'Алерты', icon: <Bell size={16} />, path: '/alerts' },
  { id: 'calculator', label: 'Калькулятор', icon: <Calculator size={16} />, path: '/calculator' },
];

export function AnalyticsTabs({ tab, onChange }: { tab: AnalyticsTab; onChange: (tab: AnalyticsTab) => void }) {
  return (
    <div role="tablist" aria-label="Разделы аналитики" className="flex gap-0 mt-5 border-b border-aigenis-border">
      {(['bonds', 'scores', 'companies'] as AnalyticsTab[]).map((t) => {
        const active = tab === t;
        return (
          <button
            key={t}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t)}
            className={`px-5 py-2.5 border-none bg-transparent text-[15px] font-medium cursor-pointer relative font-aigenis-body ${
              active ? 'text-aigenis-text' : 'text-aigenis-text-muted'
            }`}
          >
            {TAB_LABELS[t]}
            {active && (
              <span
                className="absolute -bottom-px left-0 right-0 h-0.5 bg-aigenis-500 rounded"
                aria-hidden="true"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

export function AnalyticsSubNav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return (
    <nav className="flex gap-1 mt-4 flex-wrap" aria-label="Разделы аналитики">
      {SUB_NAV.map((item) => {
        const active = pathname.startsWith(item.path);
        return (
          <button
            key={item.id}
            onClick={() => navigate(item.path)}
            aria-pressed={active}
            className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border-none cursor-pointer text-[13px] font-medium font-aigenis-body ${
              active ? 'bg-aigenis-50 text-aigenis-500' : 'bg-white text-aigenis-text-secondary'
            }`}
          >
            {item.icon} {item.label}
          </button>
        );
      })}
    </nav>
  );
}
