import { useState } from 'react';
import { Menu, TrendingUp, X } from 'lucide-react';
import { useI18n, LanguageToggle } from '../../../i18n';

interface LandingHeaderProps {
  onLogin: () => void;
  onRegister: () => void;
  scrollTo: (id: string) => void;
}

export function LandingHeader({ onLogin, onRegister, scrollTo }: LandingHeaderProps) {
  const { t } = useI18n();
  const [mobileMenu, setMobileMenu] = useState(false);

  const closeAndScroll = (id: string) => {
    setMobileMenu(false);
    scrollTo(id);
  };

  return (
    <header className="border-b border-[#d6e2e6] bg-white/90 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="text-[#004b65]" size={24} />
          <span className="text-lg font-bold">Aigenis Bonds</span>
        </div>
        <nav className="hidden md:flex items-center gap-6 text-sm">
          <button onClick={() => closeAndScroll('pain-points')} className="text-[#516c79] hover:text-[#01121a] transition-colors">{t('pain.title')}</button>
          <button onClick={() => closeAndScroll('features')} className="text-[#516c79] hover:text-[#01121a] transition-colors">{t('landing.features')}</button>
          <button onClick={() => closeAndScroll('pricing')} className="text-[#516c79] hover:text-[#01121a] transition-colors">{t('landing.pricing')}</button>
          <button onClick={() => closeAndScroll('faq')} className="text-[#516c79] hover:text-[#01121a] transition-colors">FAQ</button>
          <a href="/partners" className="text-[#004b65] hover:text-[#387387] transition-colors">{t('landing.forBusiness')}</a>
          <LanguageToggle />
          <button onClick={onLogin} className="text-[#516c79] hover:text-[#01121a] transition-colors">{t('auth.signIn')}</button>
          <button onClick={onRegister}
            className="bg-[#004b65] hover:bg-[#387387] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
            {t('landing.getStarted')}
          </button>
        </nav>
        <button className="md:hidden p-2 text-[#516c79]" onClick={() => setMobileMenu(!mobileMenu)}>
          {mobileMenu ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
      {mobileMenu && (
        <div className="md:hidden border-t border-[#d6e2e6] px-4 py-3 bg-white space-y-2">
          <button onClick={() => closeAndScroll('pain-points')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">{t('pain.title')}</button>
          <button onClick={() => closeAndScroll('features')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">{t('landing.features')}</button>
          <button onClick={() => closeAndScroll('pricing')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">{t('landing.pricing')}</button>
          <button onClick={() => closeAndScroll('faq')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">FAQ</button>
          <a href="/partners" className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#004b65] hover:bg-[#f5f9fb]">{t('landing.forBusiness')}</a>
          <button onClick={onLogin} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">{t('auth.signIn')}</button>
          <LanguageToggle />
          <button onClick={onRegister} className="w-full bg-[#004b65] text-white py-2 rounded-lg text-sm font-medium">{t('landing.getStarted')}</button>
        </div>
      )}
    </header>
  );
}
