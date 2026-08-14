import { useMemo, useState } from 'react';
import { Calculator } from 'lucide-react';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';

export default function BondCalculator() {
  const { t } = useI18n();
  usePageMeta(t('meta.calculator'));
  const [face, setFace] = useState('100');
  const [coupon, setCoupon] = useState('8');
  const [freq, setFreq] = useState(2);
  const [ytm, setYtm] = useState('9');
  const [years, setYears] = useState('5');
  const [accruedDays, setAccruedDays] = useState('0');
  const [periodDays, setPeriodDays] = useState('182');

  const result = useMemo(() => {
    const F = Number(face);
    const c = Number(coupon) / 100;
    const y = Number(ytm) / 100;
    const n = Number(years);
    const f = freq;
    if (!F || isNaN(c) || isNaN(y) || !n || !f) return null;
    const periods = Math.round(n * f);
    if (periods <= 0) return null;
    const perY = y / f;
    const cf = (F * c) / f;
    let clean = 0;
    for (let k = 1; k <= periods; k++) {
      const flow = k === periods ? cf + F : cf;
      clean += flow / Math.pow(1 + perY, k);
    }
    const pd = Number(periodDays) || 1;
    const accrued = (F * c) / f * (Number(accruedDays) / pd);
    const dirty = clean + accrued;
    const currentYield = clean > 0 ? (cf * f) / clean : 0;
    return { clean, dirty, accrued, currentYield };
  }, [face, coupon, freq, ytm, years, accruedDays, periodDays]);

  const numField = (label: string, value: string, onChange: (v: string) => void, step = '1', type = 'number') => (
    <div>
      <label className="text-xs text-[#516c79] block mb-1">{label}</label>
      <input value={value} onChange={(e) => onChange(e.target.value)} type={type} step={step}
        className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
    </div>
  );

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center gap-2">
        <Calculator size={22} className="text-[#004b65]" />
        <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('calc.title')}</h2>
      </div>
      <p className="text-sm text-[#516c79]">{t('calc.desc')}</p>

      <div className="bg-white rounded-xl border border-[#d6e2e6] p-5 grid grid-cols-2 lg:grid-cols-3 gap-4">
        {numField(t('calc.face'), face, setFace)}
        {numField(t('calc.coupon'), coupon, setCoupon, '0.1')}
        <div>
          <label className="text-xs text-[#516c79] block mb-1">{t('calc.payments')}</label>
          <select value={freq} onChange={(e) => setFreq(Number(e.target.value))}
            className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm">
            <option value={1}>1 ({t('calc.freqYear')})</option>
            <option value={2}>2 ({t('calc.freqHalf')})</option>
            <option value={4}>4 ({t('calc.freqQuarter')})</option>
            <option value={12}>12 ({t('calc.freqMonth')})</option>
          </select>
        </div>
        {numField(t('calc.ytm'), ytm, setYtm, '0.1')}
        {numField(t('calc.years'), years, setYears, '0.5')}
        {numField(t('calc.accruedDays'), accruedDays, setAccruedDays)}
        {numField(t('calc.periodDays'), periodDays, setPeriodDays)}
      </div>

      {result && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-5 grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-[#f8fafb]/50 rounded-lg p-3">
            <p className="text-xs text-[#516c79]">{t('calc.cleanPrice')}</p>
            <p className="text-xl font-bold text-[#004b65]">{result.clean.toFixed(2)} {t('calc.currency')}</p>
          </div>
          <div className="bg-[#f8fafb]/50 rounded-lg p-3">
            <p className="text-xs text-[#516c79]">{t('calc.accrued')}</p>
            <p className="text-xl font-bold text-[#004b65]">{result.accrued.toFixed(2)} {t('calc.currency')}</p>
          </div>
          <div className="bg-[#f8fafb]/50 rounded-lg p-3">
            <p className="text-xs text-[#516c79]">{t('calc.dirtyPrice')}</p>
            <p className="text-xl font-bold text-[#01121a]">{result.dirty.toFixed(2)} {t('calc.currency')}</p>
          </div>
          <div className="bg-[#f8fafb]/50 rounded-lg p-3">
            <p className="text-xs text-[#516c79]">{t('calc.currentYield')}</p>
            <p className="text-xl font-bold text-[#004b65]">{(result.currentYield * 100).toFixed(2)}%</p>
          </div>
        </div>
      )}
    </div>
  );
}
