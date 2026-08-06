import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import DemoShell from './DemoShell';
import { PageFallback } from '../app/PageFallback';

const DemoTradingPage = lazy(() => import('./pages/DemoTradingPage'));
const DemoAnalyticsPage = lazy(() => import('./pages/DemoAnalyticsPage'));
const DemoPortfolioImpactPage = lazy(() => import('./pages/DemoPortfolioImpactPage'));

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
        <Route path="portfolio-impact/:internalId" element={<Page><DemoPortfolioImpactPage /></Page>} />
      </Route>
    </Routes>
  );
}
