import { test, expect } from '@playwright/test';
import { mockLiveDemoApi } from './live-demo';

interface PerfState {
  lcp: number;
  cls: number;
  fcp: number;
  dcl: number;
  load: number;
  transfer: number;
  errors: string[];
}

const pages = [
  { path: '/demo/trading', name: 'trading' },
  { path: '/demo/analytics?market=BCSE', name: 'analytics' },
  { path: '/demo/portfolio-impact/demo-bond-001?market=BCSE', name: 'impact' },
  { path: '/demo/desk?market=BCSE', name: 'desk' },
  { path: '/demo/stress?market=BCSE', name: 'stress' },
  { path: '/demo/optimizer?market=BCSE', name: 'optimizer' },
  { path: '/demo/search?q=Минфин', name: 'search' },
  { path: '/demo/portfolio-lab?market=BCSE', name: 'portfolio-lab' },
];

const BUDGETS = {
  lcp: 3000,
  fcp: 2500,
  cls: 0.3,
  load: 5000,
  dcl: 4000,
};

test.describe('demo perf (6.5)', () => {
  for (const { path, name } of pages) {
    test(name, async ({ page }, testInfo) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
      page.on('console', (m) => {
        if (m.type() === 'error') errors.push(`console.error: ${m.text()}`);
      });

      await page.addInitScript(() => {
        const state = { lcp: 0, cls: 0, fcp: 0 };
        (window as any).__perf = state;
        const obsLcp = new PerformanceObserver((list) => {
          for (const e of list.getEntries()) state.lcp = e.startTime;
        });
        obsLcp.observe({ type: 'largest-contentful-paint', buffered: true });
        const obsCls = new PerformanceObserver((list) => {
          for (const e of list.getEntries()) {
            if (!(e as any).hadRecentInput) state.cls += (e as any).value;
          }
        });
        obsCls.observe({ type: 'layout-shift', buffered: true });
        const obsPaint = new PerformanceObserver((list) => {
          for (const e of list.getEntries()) {
            if (e.entryType === 'paint' && e.name === 'first-contentful-paint') state.fcp = e.startTime;
          }
        });
        obsPaint.observe({ type: 'paint', buffered: true });
      });

      await mockLiveDemoApi(page);
      await page.goto(path, { waitUntil: 'load' });
      await page.waitForTimeout(500);

      const metrics = await page.evaluate(() => {
        const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
        const transfer = performance
          .getEntriesByType('resource')
          .reduce((acc, e) => acc + (e as PerformanceResourceTiming).transferSize, 0);
        const state = (window as any).__perf;
        return {
          lcp: state.lcp,
          cls: state.cls,
          fcp: state.fcp,
          dcl: nav?.domContentLoadedEventEnd ?? 0,
          load: nav?.loadEventEnd ?? 0,
          transfer,
        } as PerfState;
      });
      metrics.errors = errors;

      testInfo.attach('metrics', {
        body: JSON.stringify(metrics, null, 2),
        contentType: 'application/json',
      });

      console.log(
        `PERF ${name}: lcp=${Math.round(metrics.lcp)}ms fcp=${Math.round(metrics.fcp)}ms ` +
          `cls=${metrics.cls.toFixed(3)} dcl=${Math.round(metrics.dcl)}ms load=${Math.round(metrics.load)}ms ` +
          `transfer=${(metrics.transfer / 1024).toFixed(0)}KB errors=${metrics.errors.length}`,
      );

      expect(metrics.errors, `console/page errors on ${name}`).toEqual([]);
      expect(metrics.lcp, `${name} LCP ${Math.round(metrics.lcp)}ms`).toBeLessThan(BUDGETS.lcp);
      expect(metrics.fcp, `${name} FCP ${Math.round(metrics.fcp)}ms`).toBeLessThan(BUDGETS.fcp);
      expect(metrics.cls, `${name} CLS ${metrics.cls.toFixed(3)}`).toBeLessThan(BUDGETS.cls);
      expect(metrics.load, `${name} load ${Math.round(metrics.load)}ms`).toBeLessThan(BUDGETS.load);
      expect(metrics.dcl, `${name} DCL ${Math.round(metrics.dcl)}ms`).toBeLessThan(BUDGETS.dcl);
    });
  }
});
