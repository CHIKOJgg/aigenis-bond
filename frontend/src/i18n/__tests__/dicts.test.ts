import { describe, expect, it } from 'vitest';
import { ru, en, by } from '../index';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';

describe('i18n dictionary merge', () => {
  it('en/by содержат все ключи ru (fallback не молчит)', () => {
    const missingEn = Object.keys(ru).filter((k) => !(k in en));
    const missingBy = Object.keys(ru).filter((k) => !(k in by));
    expect(missingEn).toEqual([]);
    expect(missingBy).toEqual([]);
  });

  it('словари непустые и содержат ожидаемые ключи', () => {
    expect(Object.keys(ru).length).toBeGreaterThan(600);
    expect(ru['common.loading']).toBe('Загрузка…');
    expect(ru['meta.analytics']).toBe('Аналитика биржи');
  });

  it('namespace-файлы существуют для каждого домена', () => {
    const files = readdirSync(join(__dirname, '..', 'dicts')).filter((f) => f.endsWith('.ts'));
    expect(files.length).toBeGreaterThanOrEqual(15);
    for (const f of ['common', 'auth', 'bonds', 'stocks', 'landing', 'legal', 'widget', 'dashboard']) {
      expect(files).toContain(`${f}.ts`);
    }
  });
});
