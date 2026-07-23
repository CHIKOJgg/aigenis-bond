import { X, Star, User, Lock } from 'lucide-react';

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  premium?: boolean;
}

interface MobileMenuProps {
  isOpen: boolean;
  onClose: () => void;
  navItems: NavItem[];
  activePage: string;
  onNavigate: (page: string) => void;
  userTier: string;
  userName: string;
  onSubscribe: () => void;
  onSettings: () => void;
}

export default function MobileMenu({
  isOpen,
  onClose,
  navItems,
  activePage,
  onNavigate,
  userTier,
  userName,
  onSubscribe,
  onSettings,
}: MobileMenuProps) {
  if (!isOpen) return null;

  const mainPages = ['dashboard', 'bonds', 'scores', 'portfolio'];
  const extraItems = navItems.filter((item) => !mainPages.includes(item.id));

  return (
    <>
      <div
        className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm md:hidden"
        onClick={onClose}
      />
      <div className="fixed bottom-0 left-0 right-0 z-[61] md:hidden bg-gray-900 rounded-t-2xl max-h-[70vh] overflow-y-auto animate-slideUp">
        <div className="sticky top-0 bg-gray-900 px-4 pt-4 pb-2 border-b border-gray-800">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Навигация</h3>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="p-4 space-y-1">
          {extraItems.map(({ id, label, icon, premium }) => {
            const locked = premium && userTier === 'free';
            const isActive = activePage === id;
            return (
              <button
                key={id}
                onClick={() => {
                  onNavigate(id);
                  onClose();
                }}
                className={`flex items-center gap-3 w-full px-4 py-3 rounded-xl text-sm transition-colors ${
                  isActive
                    ? 'bg-emerald-600 text-white'
                    : 'text-gray-300 hover:bg-gray-800'
                }`}
              >
                {icon}
                <span className="flex-1 text-left">{label}</span>
                {locked && <Lock size={14} className="text-amber-400" />}
              </button>
            );
          })}

          <div className="my-3 border-t border-gray-800" />

          {userTier === 'free' && (
            <button
              onClick={() => {
                onSubscribe();
                onClose();
              }}
              className="flex items-center gap-3 w-full px-4 py-3 rounded-xl text-sm text-amber-400 hover:bg-amber-600/20 transition-colors"
            >
              <Star size={18} />
              <span className="flex-1 text-left">Подписка</span>
            </button>
          )}

          <button
            onClick={() => {
              onSettings();
              onClose();
            }}
            className="flex items-center gap-3 w-full px-4 py-3 rounded-xl text-sm text-gray-300 hover:bg-gray-800 transition-colors"
          >
            <User size={18} />
            <span className="flex-1 text-left">{userName || 'Настройки'}</span>
          </button>
        </div>
      </div>
    </>
  );
}
