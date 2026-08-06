import { useState, useEffect } from 'react';
import {
  TrendingUp, Shield, LineChart, PieChart, Brain, Bell, Star,
  BarChart3, Zap, CreditCard, ArrowRight, Check, Menu, X,
  AlertTriangle, Clock, Eye, Target, TrendingDown, ShieldAlert,
  Sparkles, ChevronDown,
} from 'lucide-react';
import { useI18n, LanguageToggle } from './i18n';
import { api, type Bond, type BondScore } from './lib/api';

interface LandingPageProps {
  onLogin: () => void;
  onRegister: () => void;
  onTerms?: () => void;
  onPrivacy?: () => void;
}

export function LandingPage({ onLogin, onRegister, onTerms, onPrivacy }: LandingPageProps) {
  const { t } = useI18n();
  const [mobileMenu, setMobileMenu] = useState(false);
  const [billing, setBilling] = useState<'month' | 'year'>('month');
  const [plans, setPlans] = useState<Record<string, { id: string; name: string; price: number; currency: string; features: string[] }>>({});
  const [starsPlans, setStarsPlans] = useState<Record<string, number>>({});
  const discount = 0.8;

  useEffect(() => {
    api.billing.plans()
      .then((data) => {
        const byId: Record<string, { id: string; name: string; price: number; currency: string; features: string[] }> = {};
        for (const p of data) byId[p.id] = p;
        setPlans(byId);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    api.subscribeInfo()
      .then((info) => {
        const byTier: Record<string, number> = {};
        for (const p of info.plans ?? []) byTier[p.tier] = p.stars;
        setStarsPlans(byTier);
      })
      .catch(() => {});
  }, []);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    setMobileMenu(false);
  };

  return (
    <div className="min-h-screen bg-[#f5f9fb] text-[#01121a] pb-20 md:pb-0">
      {/* Navigation */}
      <header className="border-b border-[#d6e2e6] bg-white/90 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="text-[#004b65]" size={24} />
            <span className="text-lg font-bold">Aigenis Bonds</span>
          </div>
          <nav className="hidden md:flex items-center gap-6 text-sm">
            <button onClick={() => scrollTo('pain-points')} className="text-[#516c79] hover:text-[#01121a] transition-colors">{t('pain.title')}</button>
            <button onClick={() => scrollTo('features')} className="text-[#516c79] hover:text-[#01121a] transition-colors">{t('landing.features')}</button>
            <button onClick={() => scrollTo('pricing')} className="text-[#516c79] hover:text-[#01121a] transition-colors">{t('landing.pricing')}</button>
            <button onClick={() => scrollTo('faq')} className="text-[#516c79] hover:text-[#01121a] transition-colors">FAQ</button>
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
            <button onClick={() => scrollTo('pain-points')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">{t('pain.title')}</button>
            <button onClick={() => scrollTo('features')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">{t('landing.features')}</button>
            <button onClick={() => scrollTo('pricing')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">{t('landing.pricing')}</button>
            <button onClick={() => scrollTo('faq')} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">FAQ</button>
            <a href="/partners" className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#004b65] hover:bg-[#f5f9fb]">{t('landing.forBusiness')}</a>
            <button onClick={onLogin} className="block w-full text-left px-3 py-2 rounded-lg text-sm text-[#516c79] hover:bg-[#f5f9fb]">{t('auth.signIn')}</button>
            <LanguageToggle />
            <button onClick={onRegister} className="w-full bg-[#004b65] text-white py-2 rounded-lg text-sm font-medium">{t('landing.getStarted')}</button>
          </div>
        )}
      </header>

      {/* Hero — Problem → Solution */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[#d9e4e8] via-[#f5f9fb] to-[#e7f0f4] animate-gradient" />
        <div className="relative max-w-7xl mx-auto px-4 py-20 md:py-32 text-center">
          <div className="inline-flex items-center gap-2 bg-[#eef3f5] border border-[#b2c9d1] rounded-full px-4 py-1.5 text-sm text-[#004b65] mb-8">
            <Zap size={14} /> {t('landing.badge')}
          </div>
          <h1 className="text-4xl md:text-6xl font-bold mb-6 leading-tight">
            {t('landing.hero1')}<br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#004b65] to-[#387387]">
              {t('landing.hero2')}
            </span>
          </h1>
          <p className="text-lg md:text-xl text-[#516c79] max-w-2xl mx-auto mb-10">
            {t('landing.heroDesc')}
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button onClick={onRegister}
              className="bg-[#004b65] hover:bg-[#387387] text-white px-8 py-3 rounded-xl text-base font-medium transition-colors flex items-center gap-2 animate-pulseGlow">
              {t('landing.startTrial')} <ArrowRight size={18} />
            </button>
            <button onClick={() => scrollTo('features')}
              className="border border-[#b2c9d1] hover:border-[#387387] text-[#516c79] hover:text-[#01121a] px-8 py-3 rounded-xl text-base font-medium transition-colors">
              {t('landing.explore')}
            </button>
          </div>
          <p className="text-sm text-[#717680] mt-4">{t('landing.trialNote')}</p>
        </div>
      </section>

      {/* Live Widget — Real data is the best proof */}
      <BestBondsWidget onOpen={onRegister} />

      {/* Pain Points — Why user needs this */}
      <section id="pain-points" className="max-w-7xl mx-auto px-4 py-20">
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 bg-red-900/20 border border-red-800/30 rounded-full px-4 py-1.5 text-sm text-red-300 mb-6">
            <AlertTriangle size={14} /> {t('pain.noTools')}
          </div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('pain.title')}</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <PainCard
            icon={<Eye size={24} />}
            title={t('pain.p1Title')}
            description={t('pain.p1Desc')}
          />
          <PainCard
            icon={<ShieldAlert size={24} />}
            title={t('pain.p2Title')}
            description={t('pain.p2Desc')}
          />
          <PainCard
            icon={<TrendingDown size={24} />}
            title={t('pain.p3Title')}
            description={t('pain.p3Desc')}
          />
          <PainCard
            icon={<Clock size={24} />}
            title={t('pain.p4Title')}
            description={t('pain.p4Desc')}
          />
          <PainCard
            icon={<Target size={24} />}
            title={t('pain.p5Title')}
            description={t('pain.p5Desc')}
          />
        </div>
      </section>

      {/* Stats Bar */}
      <section className="border-y border-[#d6e2e6] bg-white">
        <div className="max-w-5xl mx-auto px-4 py-10 grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
          <div>
            <p className="text-3xl font-bold text-[#004b65]">1500+</p>
            <p className="text-sm text-[#516c79] mt-1">{t('trust.stat1')}</p>
          </div>
          <div>
            <p className="text-3xl font-bold text-[#004b65]">6</p>
            <p className="text-sm text-[#516c79] mt-1">{t('trust.stat2')}</p>
          </div>
          <div>
            <p className="text-3xl font-bold text-[#004b65]">5</p>
            <p className="text-sm text-[#516c79] mt-1">{t('trust.stat3')}</p>
          </div>
          <div>
            <p className="text-3xl font-bold text-[#004b65]">24/7</p>
            <p className="text-sm text-[#516c79] mt-1">{t('trust.stat4')}</p>
          </div>
        </div>
      </section>

      {/* Features — Result-focused */}
      <section id="features" className="max-w-7xl mx-auto px-4 py-20">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('landing.featuresTitle')}</h2>
          <p className="text-[#516c79] max-w-2xl mx-auto">{t('landing.featuresSub')}</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <FeatureCard
            icon={<BarChart3 size={24} />}
            title={t('feat.result1')}
            description={t('feat.result1Desc')}
            color="from-[#004b65] to-[#003545]"
          />
          <FeatureCard
            icon={<Shield size={24} />}
            title={t('feat.result2')}
            description={t('feat.result2Desc')}
            color="from-purple-500 to-purple-700"
          />
          <FeatureCard
            icon={<LineChart size={24} />}
            title={t('feat.result3')}
            description={t('feat.result3Desc')}
            color="from-blue-500 to-blue-700"
          />
          <FeatureCard
            icon={<PieChart size={24} />}
            title={t('feat.result4')}
            description={t('feat.result4Desc')}
            color="from-amber-500 to-amber-700"
          />
          <FeatureCard
            icon={<Brain size={24} />}
            title={t('feat.result5')}
            description={t('feat.result5Desc')}
            color="from-pink-500 to-pink-700"
          />
          <FeatureCard
            icon={<Bell size={24} />}
            title={t('feat.result6')}
            description={t('feat.result6Desc')}
            color="from-red-500 to-red-700"
          />
        </div>
      </section>

      {/* Comparison Table */}
      <section className="max-w-5xl mx-auto px-4 py-20">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">{t('compare.title')}</h2>
        <p className="text-[#516c79] text-center mb-12 max-w-2xl mx-auto">{t('compare.sub')}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#d6e2e6]">
                <th className="p-3 md:p-4 text-left text-[#516c79] font-medium">{t('compare.col1')}</th>
                <th className="p-3 md:p-4 text-center text-[#004b65] font-semibold">{t('compare.col2')}</th>
                <th className="p-3 md:p-4 text-center text-[#717680] font-medium">{t('compare.col3')}</th>
              </tr>
            </thead>
            <tbody>
              {[
                { label: t('compare.feature1'), yes: true, other: true },
                { label: t('compare.feature2'), yes: true, other: false },
                { label: t('compare.feature3'), yes: true, other: false },
                { label: t('compare.feature4'), yes: true, other: false },
                { label: t('compare.feature5'), yes: true, other: true },
              ].map((r) => (
                <tr key={r.label} className="border-b border-[#d6e2e6]/60 hover:bg-[#eef3f5]/60 transition-colors">
                  <td className="p-3 md:p-4 text-[#01121a]">{r.label}</td>
                  <td className="p-3 md:p-4 text-center"><Check className="inline text-[#004b65]" size={18} /></td>
                  <td className="p-3 md:p-4 text-center">
                    {r.other ? <Check className="inline text-[#a4a7ae]" size={18} /> : <X className="inline text-[#a4a7ae]" size={18} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text-center mt-10">
          <button onClick={onRegister} className="inline-flex items-center gap-2 bg-[#004b65] hover:bg-[#387387] text-white px-6 py-3 rounded-xl text-sm font-medium transition-colors">
            {t('cta.seeResults')} <ArrowRight size={16} />
          </button>
        </div>
      </section>

      {/* How It Works — Simple 3 steps */}
      <section className="bg-white border-y border-[#d6e2e6]">
        <div className="max-w-5xl mx-auto px-4 py-20">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-16">{t('how.resultTitle')}</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="w-14 h-14 bg-[#eef3f5] rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-[#004b65]">1</span>
              </div>
              <h3 className="text-lg font-semibold mb-2">{t('how.step1Title')}</h3>
              <p className="text-sm text-[#516c79]">{t('how.step1Desc')}</p>
            </div>
            <div className="text-center">
              <div className="w-14 h-14 bg-[#eef3f5] rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-[#387387]">2</span>
              </div>
              <h3 className="text-lg font-semibold mb-2">{t('how.step2Title')}</h3>
              <p className="text-sm text-[#516c79]">{t('how.step2Desc')}</p>
            </div>
            <div className="text-center">
              <div className="w-14 h-14 bg-[#fef3c7] rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl font-bold text-[#b45309]">3</span>
              </div>
              <h3 className="text-lg font-semibold mb-2">{t('how.step3Title')}</h3>
              <p className="text-sm text-[#516c79]">{t('how.step3Desc')}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ROI / Value — Concrete numbers */}
      <section className="max-w-5xl mx-auto px-4 py-20">
        <div className="bg-gradient-to-br from-[#eef3f5] to-[#d9e4e8] rounded-2xl border border-[#b2c9d1] p-8 md:p-12">
          <div className="text-center">
            <Sparkles className="text-[#004b65] mx-auto mb-4" size={32} />
            <h2 className="text-3xl md:text-4xl font-bold mb-6">{t('roi.title')}</h2>
            <p className="text-lg text-[#01121a] max-w-2xl mx-auto mb-8">
              {t('roi.calc', { diff: '1 200' })}
            </p>
            <p className="text-sm text-[#516c79] max-w-xl mx-auto">
              {t('roi.subNote')}
            </p>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="max-w-5xl mx-auto px-4 py-20">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-12">
          {t('testimonials.title')}
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {[0, 1, 2].map(i => (
            <div key={i} className="bg-white rounded-2xl border border-[#d6e2e6] p-6 hover:border-[#b2c9d1] transition-colors">
              <div className="flex items-center gap-1 mb-4">
                {[...Array(5)].map((_, si) => (
                  <Star key={si} size={14} className="fill-amber-400 text-amber-400" />
                ))}
              </div>
              <p className="text-sm text-[#01121a] mb-4 leading-relaxed">{t(`testimonials.q${i}`)}</p>
              <p className="text-xs text-[#717680]">{t(`testimonials.author${i}`)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="max-w-5xl mx-auto px-4 py-20">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('pricing.highlight')}</h2>
          <p className="text-[#516c79] mb-8">{t('pricing.startFree')}</p>
          <div className="inline-flex items-center bg-white rounded-xl p-1 border border-[#d6e2e6]">
            <button onClick={() => setBilling('month')}
              className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${billing === 'month' ? 'bg-[#004b65] text-white shadow-lg shadow-[#004b65]/20' : 'text-[#516c79] hover:text-[#01121a]'}`}>
              {t('billing.monthly')}
            </button>
            <button onClick={() => setBilling('year')}
              className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${billing === 'year' ? 'bg-[#004b65] text-white shadow-lg shadow-[#004b65]/20' : 'text-[#516c79] hover:text-[#01121a]'}`}>
              {t('billing.yearly')}
            </button>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Free */}
          <div className="bg-white rounded-2xl border border-[#d6e2e6] p-6 flex flex-col">
            <h3 className="text-lg font-bold mb-1">{t('landing.planFree')}</h3>
            <p className="text-sm text-[#516c79] mb-4">{t('landing.planFreeDesc')}</p>
            <p className="text-3xl font-bold mb-6">0 BYN</p>
            <ul className="space-y-3 text-sm mb-8 flex-1">
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatBondDetails')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatScoring')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatStats')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeat10Api')}</li>
            </ul>
            <button onClick={onRegister}
              className="w-full border border-[#b2c9d1] hover:border-[#387387] text-[#004b65] py-2.5 rounded-xl text-sm font-medium transition-colors">
              {t('landing.getStarted')}
            </button>
          </div>

          {/* Pro */}
          <div className="bg-gradient-to-b from-[#eef3f5] to-white rounded-2xl border border-[#004b65] p-6 flex flex-col relative">
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[#004b65] text-white text-xs font-semibold px-4 py-1 rounded-full">
              {t('landing.mostPopular')}
            </div>
            <div className="flex items-start justify-between mb-1">
              <h3 className="text-lg font-bold">Pro</h3>
              {billing === 'year' && (
                <span className="text-xs bg-[#eef3f5] text-[#004b65] border border-[#b2c9d1] rounded-full px-2.5 py-0.5 font-medium">{t('billing.save')}</span>
              )}
            </div>
            <p className="text-sm text-[#516c79] mb-4">{t('pricing.upgradeNote')}</p>
            <p className="text-3xl font-bold mb-2">
              {billing === 'year' ? (
                <>{Math.round((plans.pro?.price ?? 2900) * discount)} <span className="text-base line-through text-[#a4a7ae]">{plans.pro?.price ?? 2900}</span></>
              ) : plans.pro?.price ?? 2900}
              <span className="text-base text-[#717680] font-normal"> {billing === 'year' ? '/мес при оплате за год' : t('landing.planPerMonth')}</span>
            </p>
            <p className="text-sm text-[#717680] mb-6">{t('landing.or')} {starsPlans.pro ?? 150} Stars</p>
            <ul className="space-y-3 text-sm mb-8 flex-1">
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatFree')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatDesk')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatOptimizer')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatMl')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatAlerts')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeat60Api')}</li>
            </ul>
            <button onClick={onRegister}
              className="w-full bg-[#004b65] hover:bg-[#387387] text-white py-2.5 rounded-xl text-sm font-medium transition-colors">
              {t('landing.startTrial')}
            </button>
          </div>

          {/* Enterprise */}
          <div className="bg-white rounded-2xl border border-[#d6e2e6] p-6 flex flex-col">
            <h3 className="text-lg font-bold mb-1">Enterprise</h3>
            <p className="text-sm text-[#516c79] mb-4">{t('landing.planEntDesc')}</p>
            <p className="text-3xl font-bold mb-2">
              {billing === 'year' ? (
                <>{Math.round((plans.enterprise?.price ?? 9900) * discount)} <span className="text-base line-through text-[#a4a7ae]">{plans.enterprise?.price ?? 9900}</span></>
              ) : plans.enterprise?.price ?? 9900}
              <span className="text-base text-[#717680] font-normal"> {billing === 'year' ? '/мес при оплате за год' : t('landing.planPerMonth')}</span>
            </p>
            <p className="text-sm text-[#717680] mb-6">{t('landing.or')} {starsPlans.enterprise ?? 500} Stars</p>
            <ul className="space-y-3 text-sm mb-8 flex-1">
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatFree')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeat300Api')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatPriority')}</li>
              <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatCustom')}</li>
            </ul>
            <button onClick={onRegister}
              className="w-full border border-[#b2c9d1] hover:border-[#387387] text-[#004b65] py-2.5 rounded-xl text-sm font-medium transition-colors">
              {t('landing.planContact')}
            </button>
          </div>
        </div>

        <p className="text-center text-sm text-[#717680] mt-8">
          {t('landing.trialNoteRu')}
        </p>
      </section>

      {/* FAQ */}
      <section id="faq" className="bg-white border-y border-[#d6e2e6]">
        <div className="max-w-3xl mx-auto px-4 py-20">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-12">{t('faq.title')}</h2>
          <div className="space-y-4">
            <FaqItem question={t('faq.q1')} answer={t('faq.a1')} />
            <FaqItem question={t('faq.q2')} answer={t('faq.a2')} />
            <FaqItem question={t('faq.q3')} answer={t('faq.a3')} />
            <FaqItem question={t('faq.q4')} answer={t('faq.a4')} />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-gradient-to-r from-[#eef3f5] to-[#d9e4e8] border-y border-[#d6e2e6]">
        <div className="max-w-4xl mx-auto px-4 py-20 text-center">
          <p className="text-sm text-[#b45309] mb-4">{t('cta.urgency')}</p>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('landing.ctaTitle')}</h2>
          <p className="text-lg text-[#516c79] mb-8 max-w-xl mx-auto">
            {t('landing.ctaSub')}
          </p>
          <button onClick={onRegister}
            className="bg-[#004b65] hover:bg-[#387387] text-white px-8 py-3 rounded-xl text-base font-medium transition-colors inline-flex items-center gap-2">
            {t('cta.tryNow')} <ArrowRight size={18} />
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#d6e2e6] bg-white">
        <div className="max-w-7xl mx-auto px-4 py-10">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="text-[#004b65]" size={20} />
                <span className="font-bold">Aigenis Bonds</span>
              </div>
              <p className="text-sm text-[#717680]">{t('landing.badge')}</p>
            </div>
            <div>
              <h4 className="text-sm font-semibold mb-3">{t('landing.footerProduct')}</h4>
              <div className="space-y-2 text-sm text-[#516c79]">
                <button onClick={() => scrollTo('pain-points')} className="block hover:text-[#01121a] transition-colors">{t('pain.title')}</button>
                <button onClick={() => scrollTo('features')} className="block hover:text-[#01121a] transition-colors">{t('landing.features')}</button>
                <button onClick={() => scrollTo('pricing')} className="block hover:text-[#01121a] transition-colors">{t('landing.pricing')}</button>
                <button onClick={() => scrollTo('faq')} className="block hover:text-[#01121a] transition-colors">FAQ</button>
              </div>
            </div>
            <div>
              <h4 className="text-sm font-semibold mb-3">{t('landing.footerLegal')}</h4>
              <div className="space-y-2 text-sm text-[#516c79]">
                <button onClick={onTerms} className="block hover:text-[#01121a] transition-colors text-left">{t('footer.terms')}</button>
                <button onClick={onPrivacy} className="block hover:text-[#01121a] transition-colors text-left">{t('footer.privacy')}</button>
              </div>
            </div>
            <div>
              <h4 className="text-sm font-semibold mb-3">{t('landing.footerPayMethods')}</h4>
              <div className="space-y-2 text-sm text-[#516c79]">
                <p className="flex items-center gap-2"><Star size={14} /> Telegram Stars</p>
                <p className="flex items-center gap-2"><CreditCard size={14} /> {t('landing.footerBankCard')}</p>
              </div>
            </div>
          </div>
          <div className="border-t border-[#d6e2e6] pt-6 text-center text-sm text-[#717680]">
            &copy; {new Date().getFullYear()} Aigenis Parser. {t('common.allRights')}
          </div>
        </div>
      </footer>

      {/* Sticky mobile CTA bar */}
      <div className="fixed bottom-0 inset-x-0 z-50 md:hidden bg-white/95 backdrop-blur border-t border-[#d6e2e6] px-4 py-3">
        <button
          onClick={onRegister}
          className="w-full bg-[#004b65] hover:bg-[#387387] text-white py-3 rounded-xl text-sm font-semibold transition-colors flex items-center justify-center gap-2 animate-pulseGlow"
        >
          {t('landing.startTrial')} <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}

function PainCard({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <div className="bg-white rounded-2xl border border-[#d6e2e6] p-6 hover:border-[#b91c1c]/40 transition-colors group">
      <div className="w-12 h-12 bg-[#fee2e2] rounded-xl flex items-center justify-center mb-4 text-[#b91c1c] group-hover:bg-[#fecaca] transition-colors">
        {icon}
      </div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-sm text-[#516c79] leading-relaxed">{description}</p>
    </div>
  );
}

function FeatureCard({ icon, title, description, color }: { icon: React.ReactNode; title: string; description: string; color: string }) {
  return (
    <div className="bg-white rounded-2xl border border-[#d6e2e6] p-6 hover:border-[#b2c9d1] transition-colors">
      <div className={`w-12 h-12 bg-gradient-to-br ${color} rounded-xl flex items-center justify-center mb-4`}>
        {icon}
      </div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-sm text-[#516c79] leading-relaxed">{description}</p>
    </div>
  );
}

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-5 text-left hover:bg-[#f5f9fb] transition-colors"
      >
        <span className="text-sm font-medium text-[#01121a] pr-4">{question}</span>
        <ChevronDown
          size={18}
          className={`text-[#516c79] shrink-0 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="px-5 pb-5 text-sm text-[#516c79] leading-relaxed animate-fadeIn">
          {answer}
        </div>
      )}
    </div>
  );
}

function CurrencyButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-5 py-3 rounded-xl text-sm font-medium transition-colors border ${
        active
          ? 'bg-[#004b65] border-[#004b65] text-white'
          : 'bg-white border-[#d6e2e6] text-[#01121a] hover:border-[#004b65]'
      }`}
    >
      {label}
    </button>
  );
}

function BestBondsWidget({ onOpen }: { onOpen: () => void }) {
  const { t } = useI18n();
  const [currency, setCurrency] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<{ bond: Bond; score: number | null }[]>([]);

  const load = async (cur: string) => {
    setCurrency(cur);
    setLoading(true);
    setError(null);
    setRows([]);
    try {
      const [bonds, scores] = await Promise.all([
        api.bonds.list({ currency: cur, limit: 300 }),
        api.scores({ limit: 1000 }).catch(() => [] as BondScore[]),
      ]);
      const scoreMap: Record<string, number> = {};
      scores.forEach((s) => { scoreMap[s.internal_id] = s.score; });
      const merged = bonds
        .map((b) => ({ bond: b, score: scoreMap[b.internal_id] ?? null }))
        .sort((a, b) => {
          if (a.score != null && b.score != null) return b.score - a.score;
          if (a.score != null) return -1;
          if (b.score != null) return 1;
          return (b.bond.yield_to_maturity ?? -1) - (a.bond.yield_to_maturity ?? -1);
        });
      setRows(merged.slice(0, 8));
    } catch {
      setError(t('bestBonds.error'));
    } finally {
      setLoading(false);
    }
  };

  const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleDateString() : '—');

  return (
    <section className="max-w-5xl mx-auto px-4 -mt-6 relative z-10">
      <div className="bg-white backdrop-blur border border-[#d6e2e6] rounded-2xl p-6 shadow-xl">
        <div className="flex items-start gap-3 mb-1">
          <TrendingUp className="text-[#004b65] mt-1 shrink-0" size={22} />
          <div>
            <h2 className="text-xl md:text-2xl font-bold">{t('bestBonds.title')}</h2>
            <p className="text-sm text-[#516c79] mt-1">{t('bestBonds.sub')}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 my-4">
          <CurrencyButton label={t('bestBonds.rub')} active={currency === 'RUB'} onClick={() => load('RUB')} />
          <CurrencyButton label={t('bestBonds.usd')} active={currency === 'USD'} onClick={() => load('USD')} />
          <CurrencyButton label={t('bestBonds.byn')} active={currency === 'BYN'} onClick={() => load('BYN')} />
          <CurrencyButton label={t('bestBonds.eur')} active={currency === 'EUR'} onClick={() => load('EUR')} />
        </div>

        {loading && <p className="text-sm text-[#516c79] py-6 text-center">{t('bestBonds.loading')}</p>}
        {error && <p className="text-sm text-[#b91c1c] py-6 text-center">{error}</p>}

        {!loading && !error && rows.length > 0 && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
              {rows.map(({ bond, score }) => (
                <div key={bond.internal_id} className="bg-[#f8fafb] border border-[#d6e2e6] rounded-xl p-4 flex flex-col">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-sm truncate">{bond.name}</p>
                      <p className="text-xs text-[#717680] font-mono">{bond.internal_id} · {bond.currency}</p>
                    </div>
                    {score != null && (
                      <span className="shrink-0 text-xs bg-[#eef3f5] text-[#004b65] border border-[#b2c9d1] rounded-full px-2 py-0.5">
                        {t('bestBonds.score')}: {score.toFixed(0)}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm">
                    <span className="text-[#516c79]">{t('bestBonds.ytm')}: <b className="text-[#01121a] font-mono">{bond.yield_to_maturity != null ? `${bond.yield_to_maturity.toFixed(2)}%` : '—'}</b></span>
                    <span className="text-[#516c79]">{t('bestBonds.coupon')}: <b className="text-[#01121a] font-mono">{bond.coupon_rate != null ? `${bond.coupon_rate.toFixed(2)}%` : '—'}</b></span>
                    <span className="text-[#516c79]">{t('bestBonds.maturity')}: <b className="text-[#01121a] font-mono">{fmtDate(bond.maturity_date)}</b></span>
                  </div>
                </div>
              ))}
            </div>
            <button
              onClick={onOpen}
              className="mt-5 w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-[#004b65] hover:bg-[#387387] text-white px-6 py-2.5 rounded-xl text-sm font-medium transition-colors"
            >
              {t('bestBonds.cta')} <ArrowRight size={16} />
            </button>
          </>
        )}

        {!loading && !error && currency && rows.length === 0 && (
          <p className="text-sm text-[#516c79] py-6 text-center">{t('bestBonds.empty')}</p>
        )}
      </div>
    </section>
  );
}
