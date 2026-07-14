import { useState } from 'react';
import {
  TrendingUp, Shield, LineChart, PieChart, Brain, Bell, Star,
  BarChart3, Zap, CreditCard, ArrowRight, Check, Menu, X,
} from 'lucide-react';
import { useI18n, LanguageToggle } from './i18n';

interface LandingPageProps {
  onLogin: () => void;
  onRegister: () => void;
  onTerms?: () => void;
  onPrivacy?: () => void;
}

export function LandingPage({ onLogin, onRegister, onTerms, onPrivacy }: LandingPageProps) {
  const { t } = useI18n();
  const [mobileMenu, setMobileMenu] = useState(false);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    setMobileMenu(false);
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Navigation */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="text-emerald-400" size={24} />
            <span className="text-lg font-bold">Aigenis Bonds</span>
          </div>
          <nav className="hidden md:flex items-center gap-6 text-sm">
            <button onClick={() => scrollTo('features')} className="text-gray-400 hover:text-white transition-colors">{t('landing.features')}</button>
            <button onClick={() => scrollTo('pricing')} className="text-gray-400 hover:text-white transition-colors">{t('landing.pricing')}</button>
            <LanguageToggle />
            <button onClick={onLogin} className="text-gray-300 hover:text-white transition-colors">{t('auth.signIn')}</button>
            <button onClick={onRegister}
              className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
              {t('landing.getStarted')}
            </button>
          </nav>
          <button className="md:hidden p-2 text-gray-400" onClick={() => setMobileMenu(!mobileMenu)}>
            {mobileMenu ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        {mobileMenu && (
          <div className="md:hidden border-t border-gray-800 px-4 py-3 bg-gray-900 space-y-2">
            <button onClick={() => scrollTo('features')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800">{t('landing.features')}</button>
            <button onClick={() => scrollTo('pricing')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800">{t('landing.pricing')}</button>
            <button onClick={onLogin} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800">{t('auth.signIn')}</button>
            <LanguageToggle />
            <button onClick={onRegister} className="w-full bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium">{t('landing.getStarted')}</button>
          </div>
        )}
      </header>

      {/* Hero */}
      <section className="max-w-7xl mx-auto px-4 py-20 md:py-32 text-center">
        <div className="inline-flex items-center gap-2 bg-emerald-900/30 border border-emerald-800/50 rounded-full px-4 py-1.5 text-sm text-emerald-300 mb-8">
          <Zap size={14} /> {t('landing.badge')}
        </div>
        <h1 className="text-4xl md:text-6xl font-bold mb-6 leading-tight">
          {t('landing.hero1')}<br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-blue-400">
            {t('landing.hero2')}
          </span>
        </h1>
        <p className="text-lg md:text-xl text-gray-400 max-w-2xl mx-auto mb-10">
          {t('landing.heroDesc')}
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <button onClick={onRegister}
            className="bg-emerald-600 hover:bg-emerald-500 text-white px-8 py-3 rounded-xl text-base font-medium transition-colors flex items-center gap-2">
            {t('landing.startTrial')} <ArrowRight size={18} />
          </button>
          <button onClick={() => scrollTo('features')}
            className="border border-gray-700 hover:border-gray-600 text-gray-300 px-8 py-3 rounded-xl text-base font-medium transition-colors">
            {t('landing.explore')}
          </button>
        </div>
        <p className="text-sm text-gray-500 mt-4">{t('landing.trialNote')}</p>
      </section>

      {/* Stats Bar */}
      <section className="border-y border-gray-800 bg-gray-900/50">
        <div className="max-w-5xl mx-auto px-4 py-10 grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
          <div>
          <p className="text-3xl font-bold text-emerald-400">6</p>
          <p className="text-sm text-gray-400 mt-1">{t('landing.statCurrencies')}</p>
        </div>
        <div>
          <p className="text-3xl font-bold text-emerald-400">100+</p>
          <p className="text-sm text-gray-400 mt-1">{t('landing.statBonds')}</p>
        </div>
        <div>
          <p className="text-3xl font-bold text-emerald-400">5</p>
          <p className="text-sm text-gray-400 mt-1">{t('landing.statModules')}</p>
        </div>
        <div>
          <p className="text-3xl font-bold text-emerald-400">24/7</p>
          <p className="text-sm text-gray-400 mt-1">{t('landing.statMonitoring')}</p>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="max-w-7xl mx-auto px-4 py-20">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('landing.featuresTitle')}</h2>
          <p className="text-gray-400 max-w-2xl mx-auto">{t('landing.featuresSub')}</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <FeatureCard
            icon={<BarChart3 size={24} />}
            title={t('landing.f1Title')}
            description={t('landing.f1Desc')}
            color="from-emerald-500 to-emerald-700"
          />
          <FeatureCard
            icon={<Shield size={24} />}
            title={t('landing.f2Title')}
            description={t('landing.f2Desc')}
            color="from-purple-500 to-purple-700"
          />
          <FeatureCard
            icon={<LineChart size={24} />}
            title={t('landing.f3Title')}
            description={t('landing.f3Desc')}
            color="from-blue-500 to-blue-700"
          />
          <FeatureCard
            icon={<PieChart size={24} />}
            title={t('landing.f4Title')}
            description={t('landing.f4Desc')}
            color="from-amber-500 to-amber-700"
          />
          <FeatureCard
            icon={<Brain size={24} />}
            title={t('landing.f5Title')}
            description={t('landing.f5Desc')}
            color="from-pink-500 to-pink-700"
          />
          <FeatureCard
            icon={<Bell size={24} />}
            title={t('landing.f6Title')}
            description={t('landing.f6Desc')}
            color="from-red-500 to-red-700"
          />
        </div>
      </section>

      {/* How it works */}
      <section className="bg-gray-900/50 border-y border-gray-800">
        <div className="max-w-5xl mx-auto px-4 py-20">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-16">{t('landing.how')}</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="w-14 h-14 bg-emerald-600/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-emerald-400">1</span>
              </div>
              <h3 className="text-lg font-semibold mb-2">{t('landing.how1Title')}</h3>
              <p className="text-sm text-gray-400">{t('landing.how1Desc')}</p>
            </div>
            <div className="text-center">
              <div className="w-14 h-14 bg-blue-600/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-blue-400">2</span>
              </div>
              <h3 className="text-lg font-semibold mb-2">{t('landing.how2Title')}</h3>
              <p className="text-sm text-gray-400">{t('landing.how2Desc')}</p>
            </div>
            <div className="text-center">
              <div className="w-14 h-14 bg-amber-600/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-amber-400">3</span>
              </div>
              <h3 className="text-lg font-semibold mb-2">{t('landing.how3Title')}</h3>
              <p className="text-sm text-gray-400">{t('landing.how3Desc')}</p>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="max-w-5xl mx-auto px-4 py-20">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('landing.pricingTitle')}</h2>
          <p className="text-gray-400">{t('landing.pricingSub')}</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Free */}
          <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 flex flex-col">
            <h3 className="text-lg font-bold mb-1">{t('landing.planFree')}</h3>
            <p className="text-sm text-gray-400 mb-4">{t('landing.planFreeDesc')}</p>
            <p className="text-3xl font-bold mb-6">$0</p>
            <ul className="space-y-3 text-sm mb-8 flex-1">
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatBondDetails')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatScoring')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatStats')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeat10Api')}</li>
            </ul>
            <button onClick={onRegister}
              className="w-full border border-gray-700 hover:border-gray-600 text-gray-300 py-2.5 rounded-xl text-sm font-medium transition-colors">
              {t('landing.getStarted')}
            </button>
          </div>

          {/* Pro */}
          <div className="bg-gradient-to-b from-emerald-900/30 to-gray-900 rounded-2xl border border-emerald-800/50 p-6 flex flex-col relative">
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-emerald-600 text-white text-xs font-semibold px-4 py-1 rounded-full">
              {t('landing.mostPopular')}
            </div>
            <h3 className="text-lg font-bold mb-1">Pro</h3>
            <p className="text-sm text-gray-400 mb-4">{t('landing.planProDesc')}</p>
            <p className="text-3xl font-bold mb-2">29 <span className="text-base text-gray-500 font-normal">{t('landing.planPerMonth')}</span></p>
            <p className="text-sm text-gray-500 mb-6">{t('landing.or')} 150 Stars</p>
            <ul className="space-y-3 text-sm mb-8 flex-1">
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatFree')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatDesk')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatOptimizer')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatMl')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatAlerts')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeat60Api')}</li>
            </ul>
            <button onClick={onRegister}
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white py-2.5 rounded-xl text-sm font-medium transition-colors">
              {t('landing.startTrial')}
            </button>
          </div>

          {/* Enterprise */}
          <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 flex flex-col">
            <h3 className="text-lg font-bold mb-1">Enterprise</h3>
            <p className="text-sm text-gray-400 mb-4">{t('landing.planEntDesc')}</p>
            <p className="text-3xl font-bold mb-2">99 <span className="text-base text-gray-500 font-normal">{t('landing.planPerMonth')}</span></p>
            <p className="text-sm text-gray-500 mb-6">{t('landing.or')} 500 Stars</p>
            <ul className="space-y-3 text-sm mb-8 flex-1">
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatFree')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeat300Api')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatPriority')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-emerald-400 shrink-0 mt-0.5" /> {t('landing.planFeatCustom')}</li>
            </ul>
            <button onClick={onRegister}
              className="w-full border border-gray-700 hover:border-gray-600 text-gray-300 py-2.5 rounded-xl text-sm font-medium transition-colors">
              {t('landing.planContact')}
            </button>
          </div>
        </div>

        <p className="text-center text-sm text-gray-500 mt-8">
          {t('landing.trialNoteRu')}
        </p>
      </section>

      {/* CTA */}
      <section className="bg-gradient-to-r from-emerald-900/30 to-blue-900/30 border-y border-gray-800">
        <div className="max-w-4xl mx-auto px-4 py-20 text-center">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('landing.ctaTitle')}</h2>
          <p className="text-lg text-gray-400 mb-8 max-w-xl mx-auto">
            {t('landing.ctaSub')}
          </p>
          <button onClick={onRegister}
            className="bg-emerald-600 hover:bg-emerald-500 text-white px-8 py-3 rounded-xl text-base font-medium transition-colors inline-flex items-center gap-2">
            {t('landing.createAccount')} <ArrowRight size={18} />
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 py-10">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="text-emerald-400" size={20} />
                <span className="font-bold">Aigenis Bonds</span>
              </div>
              <p className="text-sm text-gray-500">{t('landing.badge')}</p>
            </div>
            <div>
              <h4 className="text-sm font-semibold mb-3">{t('landing.footerProduct')}</h4>
              <div className="space-y-2 text-sm text-gray-400">
                <button onClick={() => scrollTo('features')} className="block hover:text-white transition-colors">{t('landing.features')}</button>
                <button onClick={() => scrollTo('pricing')} className="block hover:text-white transition-colors">{t('landing.pricing')}</button>
              </div>
            </div>
            <div>
              <h4 className="text-sm font-semibold mb-3">{t('landing.footerLegal')}</h4>
              <div className="space-y-2 text-sm text-gray-400">
                <button onClick={onTerms} className="block hover:text-white transition-colors text-left">{t('footer.terms')}</button>
                <button onClick={onPrivacy} className="block hover:text-white transition-colors text-left">{t('footer.privacy')}</button>
              </div>
            </div>
            <div>
              <h4 className="text-sm font-semibold mb-3">{t('landing.footerPayMethods')}</h4>
              <div className="space-y-2 text-sm text-gray-400">
                <p className="flex items-center gap-2"><Star size={14} /> Telegram Stars</p>
                <p className="flex items-center gap-2"><CreditCard size={14} /> {t('landing.footerBankCard')}</p>
              </div>
            </div>
          </div>
          <div className="border-t border-gray-800 pt-6 text-center text-sm text-gray-600">
            &copy; {new Date().getFullYear()} Aigenis Parser. {t('common.allRights')}
          </div>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({ icon, title, description, color }: { icon: React.ReactNode; title: string; description: string; color: string }) {
  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 hover:border-gray-700 transition-colors">
      <div className={`w-12 h-12 bg-gradient-to-br ${color} rounded-xl flex items-center justify-center mb-4`}>
        {icon}
      </div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-sm text-gray-400 leading-relaxed">{description}</p>
    </div>
  );
}
