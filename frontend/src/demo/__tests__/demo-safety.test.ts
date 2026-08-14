import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { DEMO_CONFIG, DEMO_PERSONA, ALLOCATION_OPTIONS } from '../demo-config';

describe('feature flags (DEMO_CONFIG)', () => {
  it('демо работает на live-данных с отключёнными side effects', () => {
    expect(DEMO_CONFIG.useFixtures).toBe(false);
    expect(DEMO_CONFIG.enableLiveRefresh).toBe(true);
  });

  it('в демо отключены все реальные side effects', () => {
    expect(DEMO_CONFIG.enableRequestCreation).toBe(false);
    expect(DEMO_CONFIG.enableExternalLinks).toBe(false);
  });

  it('concept-режим: без брендовых логотипов', () => {
    expect(DEMO_CONFIG.mode).toBe('concept');
    expect(DEMO_CONFIG.showBrandMark).toBe(false);
  });

  it('демо-водяной знак включён', () => {
    expect(DEMO_CONFIG.showDemoWatermark).toBe(true);
  });

  it('аллокация ограничена 5/10/15%', () => {
    expect(ALLOCATION_OPTIONS).toEqual([5, 10, 15]);
  });

  it('персона демо — Марина К. с 50 000 BYN', () => {
    expect(DEMO_PERSONA.name).toBe('Марина К.');
    expect(DEMO_PERSONA.portfolio_byn).toBe(50000);
  });
});

describe('demo side-effect guard', () => {
  const demoDir = join(__dirname, '..');
  const files = readdirSync(demoDir, { recursive: true })
    .map(String)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .filter((f) => !f.includes('__tests__'))
    .filter((f) => !f.endsWith('.test.ts') && !f.endsWith('.test.tsx'));

  // The only sanctioned network calls in the demo are read-only routes under
  // /api/v1/demo (the nginx demo gate fails closed for every other API family).
  const SANCTIONED = 'live-demo-api.ts';

  it('демо-модуль не содержит сетевых вызовов и платежей', () => {
    const offenders: string[] = [];
    for (const file of files) {
      if (file === SANCTIONED) continue;
      const source = readFileSync(join(demoDir, file), 'utf8');
      if (/\b(fetch|axios|XMLHttpRequest|WebSocket)\s*\(/.test(source)) {
        offenders.push(`${file}: fetch/axios/XHR/WS`);
      }
      if (/\b(localStorage|sessionStorage)\b/.test(source)) {
        offenders.push(`${file}: storage`);
      }
      if (/payment|checkout|yookassa|stripe/i.test(source)) {
        offenders.push(`${file}: payment`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('демо-модуль обращается только к read-only demo API', () => {
    const offenders: string[] = [];
    for (const file of files) {
      if (file === SANCTIONED) continue;
      const source = readFileSync(join(demoDir, file), 'utf8');
      if (/\/api\//.test(source) || /\bfetch\b/.test(source)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('live-demo-api обращается только к read-only demo-endpoint', () => {
    const source = readFileSync(join(demoDir, SANCTIONED), 'utf8');
    const fetchUrls = Array.from(source.matchAll(/fetch\([^)]*\)/g)).map((m) => m[0]);
    expect(fetchUrls.length).toBeGreaterThan(0);
    for (const url of fetchUrls) {
      expect(url).toMatch(/\/api\/v1\/demo\/(market-data|search|bond\/|desk\/|portfolio\/)/);
    }
    expect(source).not.toMatch(/localStorage|sessionStorage/);
    expect(source).not.toMatch(/payment|checkout|yookassa|stripe/i);
  });
});
