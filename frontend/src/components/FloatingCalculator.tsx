import { useState } from 'react';
import { Calculator, X } from 'lucide-react';

export default function FloatingCalculator() {
  const [open, setOpen] = useState(false);
  const [face, setFace] = useState('1000');
  const [coupon, setCoupon] = useState('10');
  const [ytm, setYtm] = useState('12');
  const [years, setYears] = useState('3');
  const [result, setResult] = useState<string | null>(null);

  const calculate = () => {
    const f = Number(face) || 1000;
    const c = (Number(coupon) || 0) / 100;
    const y = (Number(ytm) || 0) / 100;
    const n = Number(years) || 1;
    const annualIncome = f * c;
    const price = (annualIncome / y) * (1 - 1 / Math.pow(1 + y, n)) + f / Math.pow(1 + y, n);
    setResult(`Цена: ${price.toFixed(2)} / Доход: ${annualIncome.toFixed(2)} / год`);
  };

  return (
    <div className="fixed bottom-20 right-4 z-40 md:bottom-4">
      {open && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 shadow-2xl mb-3 w-72 animate-fadeInUp">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold">Калькулятор</span>
            <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-white"><X size={14} /></button>
          </div>
          <div className="space-y-2 text-sm">
            <input value={face} onChange={(e) => setFace(e.target.value)} placeholder="Номинал" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-xs" />
            <input value={coupon} onChange={(e) => setCoupon(e.target.value)} placeholder="Купон %" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-xs" />
            <input value={ytm} onChange={(e) => setYtm(e.target.value)} placeholder="YTM %" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-xs" />
            <input value={years} onChange={(e) => setYears(e.target.value)} placeholder="Лет" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-xs" />
            <button onClick={calculate} className="w-full bg-emerald-600 hover:bg-emerald-500 text-white py-1.5 rounded-lg text-xs font-medium">
              Рассчитать
            </button>
            {result && <p className="text-xs text-emerald-300">{result}</p>}
          </div>
        </div>
      )}
      <button
        onClick={() => setOpen(!open)}
        className="w-12 h-12 bg-emerald-600 hover:bg-emerald-500 rounded-full shadow-lg shadow-emerald-600/20 flex items-center justify-center text-white transition-all active:scale-95"
      >
        <Calculator size={20} />
      </button>
    </div>
  );
}
