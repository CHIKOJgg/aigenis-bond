import { BarChart3, Banknote, Shield, PieChart, Menu } from 'lucide-react';

interface BottomNavProps {
  activePage: string;
  onNavigate: (page: string) => void;
  onOpenMenu: () => void;
}

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Главная', icon: BarChart3 },
  { id: 'bonds', label: 'Облигации', icon: Banknote },
  { id: 'scores', label: 'Оценки', icon: Shield },
  { id: 'portfolio', label: 'Портфель', icon: PieChart },
] as const;

export default function BottomNav({ activePage, onNavigate, onOpenMenu }: BottomNavProps) {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 md:hidden bg-gray-900/95 backdrop-blur-lg border-t border-gray-800 safe-area-inset">
      <div className="flex items-center justify-around px-2 py-1">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const isActive = activePage === id;
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className={`flex flex-col items-center gap-0.5 px-3 py-2 rounded-xl transition-all ${
                isActive
                  ? 'text-emerald-400 bg-emerald-400/10'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              <Icon size={20} strokeWidth={isActive ? 2.5 : 1.5} />
              <span className="text-[10px] font-medium">{label}</span>
            </button>
          );
        })}
        <button
          onClick={onOpenMenu}
          className="flex flex-col items-center gap-0.5 px-3 py-2 rounded-xl text-gray-500 hover:text-gray-300 transition-all"
        >
          <Menu size={20} strokeWidth={1.5} />
          <span className="text-[10px] font-medium">Ещё</span>
        </button>
      </div>
    </nav>
  );
}
