import { Suspense, lazy, useEffect, useState, type ReactNode } from 'react';
import { Routes, Route, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../lib/AuthContext';
import { useI18n } from '../i18n';
import { useToast } from '../lib/ToastContext';
import { WidgetPage } from '../WidgetPage';
import { LandingPage } from '../features/landing/LandingPage';
import { CatalogPage } from '../features/catalog/CatalogPage';
import { LegalPages } from '../LegalPages';
import { OnboardingFlow, isOnboardingNeeded } from '../OnboardingFlow';
import AppLayout from '../layouts/AppLayout';
import { PageFallback } from './PageFallback';
import { RequirePremium, PublicOnly } from './guards';
import { ROUTES } from './paths';

const DashboardPage = lazy(() => import('../pages/DashboardPage'));
const BondsPage = lazy(() => import('../pages/BondsPage'));
const StocksPage = lazy(() => import('../pages/StocksPage'));
const StockPage = lazy(() => import('../pages/StockPage'));
const NewsPage = lazy(() => import('../pages/NewsPage'));
const ChatPage = lazy(() => import('../pages/ChatPage'));
const ScoresPage = lazy(() => import('../pages/ScoresPage'));
const AnalyticsPage = lazy(() => import('../features/analytics/AnalyticsPage'));
const DeskPage = lazy(() => import('../pages/DeskPage'));
const PortfolioPage = lazy(() => import('../pages/PortfolioPage'));
const PortfolioAdvancedPage = lazy(() => import('../pages/PortfolioAdvancedPage'));
const ForecastPage = lazy(() => import('../pages/ForecastPage'));
const AlertsPage = lazy(() => import('../pages/AlertsPage'));
const CalculatorPage = lazy(() => import('../pages/CalculatorPage'));
const AccountPage = lazy(() => import('../pages/AccountPage'));
const SubscribePage = lazy(() => import('../pages/SubscribePage'));
const DocumentAnalysisPage = lazy(() => import('../pages/DocumentAnalysis'));
const NotFoundPage = lazy(() => import('../pages/NotFoundPage'));
const LoginPage = lazy(() => import('../pages/AuthPages').then((m) => ({ default: m.LoginPage })));
const RegisterPage = lazy(() => import('../pages/AuthPages').then((m) => ({ default: m.RegisterPage })));
const CompanyPage = lazy(() => import('../pages/CompanyPage').then((m) => ({ default: m.CompanyPage })));
const RecommendationsPage = lazy(() => import('../pages/RecommendationsPage').then((m) => ({ default: m.RecommendationsPage })));
const DemoApp = lazy(() => import('../demo/DemoApp'));

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageFallback />}>{children}</Suspense>;
}

export default function AppRoutes() {
  const { user, loading } = useAuth();
  const [showOnboarding, setShowOnboarding] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();
  const { showToast } = useToast();

  useEffect(() => {
    if (user && isOnboardingNeeded()) {
      setShowOnboarding(true);
    }
  }, [user]);

  const finishOnboarding = () => setShowOnboarding(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('success') === '1') {
      showToast(t('toast.paymentSuccess'));
      const cleanPath = window.location.pathname + window.location.search.replace(/[?&]success=1/, '');
      window.history.replaceState({}, '', cleanPath || window.location.pathname);
    }
  }, [t, showToast]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f5f9fb] text-[#01121a] flex items-center justify-center">
        <div className="animate-pulse text-[#516c79]">{t('common.loading')}</div>
      </div>
    );
  }

  if (showOnboarding) {
    return <Navigate to={ROUTES.onboarding} replace />;
  }

  const goSubscribe = () => navigate(ROUTES.subscribe);

  return (
    <Routes>
      <Route path={ROUTES.widget} element={<WidgetPage />} />
      <Route path="/demo/*" element={<Page><DemoApp /></Page>} />
      {import.meta.env.DEV && (
        <Route path="/catalog" element={<CatalogPage />} />
      )}

      {!user ? (
        <>
          <Route path={ROUTES.login} element={<PublicOnly><Page><LoginPage onRegister={() => navigate(ROUTES.register)} /></Page></PublicOnly>} />
          <Route path={ROUTES.register} element={<PublicOnly><Page><RegisterRoute /></Page></PublicOnly>} />
          <Route path={ROUTES.terms} element={<LegalPages page="terms" onBack={() => navigate(ROUTES.home)} />} />
          <Route path={ROUTES.privacy} element={<LegalPages page="privacy" onBack={() => navigate(ROUTES.home)} />} />
          <Route path="*" element={<LandingPage onLogin={() => navigate(ROUTES.login)} onRegister={() => navigate(ROUTES.register)} onTerms={() => navigate(ROUTES.terms)} onPrivacy={() => navigate(ROUTES.privacy)} />} />
        </>
      ) : (
        <>
          <Route
            path={ROUTES.onboarding}
            element={
              <OnboardingFlow
                onDone={() => { finishOnboarding(); navigate(ROUTES.home); }}
                onNavigate={(p) => {
                  finishOnboarding();
                  if (p === 'profile') navigate(ROUTES.account);
                  else if (p === 'companies') navigate(ROUTES.scores);
                  else if (p === 'recommendations') navigate(ROUTES.recommendations);
                  else navigate(ROUTES.bonds);
                }}
              />
            }
          />
          <Route element={<AppLayout />}>
            <Route path={ROUTES.home} element={<Page><DashboardPage onPickCurrency={(cur) => navigate(`${ROUTES.bonds}?currency=${encodeURIComponent(cur)}`)} onOpenCompany={(issuer) => navigate(ROUTES.companyDetail(issuer))} onSubscribe={goSubscribe} /></Page>} />
            <Route path={ROUTES.bonds} element={<Page><BondsPage /></Page>} />
            <Route path={ROUTES.bondDetailPattern} element={<Page><BondsPage /></Page>} />
            <Route path={ROUTES.stocks} element={<Page><StocksPage /></Page>} />
            <Route path={ROUTES.stockDetailPattern} element={<Page><StockPage /></Page>} />
            <Route path={ROUTES.news} element={<Page><NewsPage /></Page>} />
            <Route path={ROUTES.chat} element={<Page><RequirePremium><ChatPage /></RequirePremium></Page>} />
            <Route path={ROUTES.scores} element={<Page><ScoresPage /></Page>} />
            <Route path={ROUTES.analytics} element={<Page><AnalyticsPage /></Page>} />
            <Route path={ROUTES.calculator} element={<Page><CalculatorPage /></Page>} />
            <Route path={ROUTES.subscribe} element={<Page><SubscribePage /></Page>} />
            <Route path={ROUTES.account} element={<Page><AccountPage onSubscribe={goSubscribe} /></Page>} />
            <Route path={ROUTES.companyDetailPattern} element={<Page><CompanyRoute /></Page>} />
            <Route path={ROUTES.desk} element={<Page><RequirePremium><DeskPage onSubscribe={goSubscribe} /></RequirePremium></Page>} />
            <Route path={ROUTES.portfolio} element={<Page><RequirePremium><PortfolioPage onSubscribe={goSubscribe} /></RequirePremium></Page>} />
            <Route path={ROUTES.portfolioAdvanced} element={<Page><RequirePremium><PortfolioAdvancedPage /></RequirePremium></Page>} />
            <Route path={ROUTES.forecast} element={<Page><RequirePremium><ForecastPage onSubscribe={goSubscribe} /></RequirePremium></Page>} />
            <Route path={ROUTES.alerts} element={<Page><RequirePremium><AlertsPage onSubscribe={goSubscribe} /></RequirePremium></Page>} />
            <Route path={ROUTES.documents} element={<Page><RequirePremium><DocumentAnalysisPage /></RequirePremium></Page>} />
            <Route path={ROUTES.recommendations} element={<Page><RecommendationsPage onSubscribe={goSubscribe} onOpenBond={(id: string) => navigate(ROUTES.bondDetail(id))} /></Page>} />
            <Route path="*" element={<Page><NotFoundPage /></Page>} />
          </Route>
        </>
      )}
    </Routes>
  );
}

function RegisterRoute() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  return (
    <RegisterPage
      onSwitch={() => navigate(ROUTES.login)}
      defaultRefCode={params.get('ref') ?? undefined}
    />
  );
}

function CompanyRoute() {
  const { issuer } = useParams<'issuer'>();
  const navigate = useNavigate();
  if (!issuer) return <Navigate to={ROUTES.home} replace />;
  return (
    <CompanyPage
      issuer={issuer}
      onBack={() => navigate(ROUTES.scores)}
      onOpenBond={(id: string) => navigate(ROUTES.bondDetail(id))}
    />
  );
}
