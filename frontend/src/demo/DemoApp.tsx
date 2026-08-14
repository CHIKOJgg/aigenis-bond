import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import DemoShell from './DemoShell';
import { PageFallback } from '../app/PageFallback';

const DemoTradingPage = lazy(() => import('./pages/DemoTradingPage'));
const DemoAnalyticsPage = lazy(() => import('./pages/DemoAnalyticsPage'));
const DemoDeskPage = lazy(() => import('./pages/DemoDeskPage'));
const DemoStressPage = lazy(() => import('./pages/DemoStressPage'));
const DemoOptimizerPage = lazy(() => import('./pages/DemoOptimizerPage'));
const DemoPortfolioImpactPage = lazy(() => import('./pages/DemoPortfolioImpactPage'));
const DemoSearchPage = lazy(() => import('./pages/DemoSearchPage'));

function Page({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<PageFallback />}>{children}</Suspense>;
}

export default function DemoApp() {
  return (
    <Routes>
      <Route element={<DemoShell />}>
        <Route index element={<Navigate to="/demo/trading" replace />} />
        <Route path="trading" element={<Page><DemoTradingPage /></Page>} />
        <Route path="analytics" element={<Page><DemoAnalyticsPage /></Page>} />
        <Route path="analytics/bonds/:internalId" element={<Page><DemoAnalyticsPage /></Page>} />
        <Route path="desk" element={<Page><DemoDeskPage /></Page>} />
        <Route path="stress" element={<Page><DemoStressPage /></Page>} />
        <Route path="optimizer" element={<Page><DemoOptimizerPage /></Page>} />
        <Route path="search" element={<Page><DemoSearchPage /></Page>} />
        <Route path="portfolio-impact/:internalId" element={<Page><DemoPortfolioImpactPage /></Page>} />
      </Route>
    </Routes>
  );
}
