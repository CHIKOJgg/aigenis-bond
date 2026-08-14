import { useState, useMemo, useEffect } from 'react';
import {
  TrendingUp,
  Calendar,
  DollarSign,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  Sparkles,
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';

interface PortfolioForecastCalculatorProps {
  initialCapital: number;
  initialYtm: number;
  currency: string;
}

export default function PortfolioForecastCalculator({
  initialCapital,
  initialYtm,
  currency,
}: PortfolioForecastCalculatorProps) {
  const [capital, setCapital] = useState(initialCapital || 50000);
  const [years, setYears] = useState(5);
  const [reinvest, setReinvest] = useState(true);
  const [customYtm, setCustomYtm] = useState<number | null>(null);
  const [inflationRate, setInflationRate] = useState(
    currency === 'USD' ? 2.5 : currency === 'RUB' ? 7.0 : 6.0
  );
  const [monthlyContribution, setMonthlyContribution] = useState(0);
  const [taxRate, setTaxRate] = useState(0); // 0% для льготных гос/корп облигаций, 13% для НДФЛ
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    if (initialCapital > 0) {
      setCapital(initialCapital);
    }
  }, [initialCapital]);

  useEffect(() => {
    setInflationRate(currency === 'USD' ? 2.5 : currency === 'RUB' ? 7.0 : 6.0);
  }, [currency]);

  // Синхронизируем базовый капитал при изменении входного пропа, если пользователь не менял вручную
  const effectiveCapital = capital > 0 ? capital : 1000;
  const effectiveYtm = customYtm !== null ? customYtm : (initialYtm > 0 ? initialYtm : 13.5);
  const netYtm = effectiveYtm * (1 - taxRate / 100);

  // Расчёт по годам
  const simulation = useMemo(() => {
    const data: Array<{
      year: number;
      invested: number;
      nominalBalance: number;
      realBalance: number;
      annualCoupons: number;
      cumulativeCoupons: number;
    }> = [];

    const monthlyRate = netYtm / 100 / 12;
    let currentNominal = effectiveCapital;
    let totalInvested = effectiveCapital;
    let totalCouponsPaidOut = 0;

    data.push({
      year: 0,
      invested: effectiveCapital,
      nominalBalance: effectiveCapital,
      realBalance: effectiveCapital,
      annualCoupons: 0,
      cumulativeCoupons: 0,
    });

    for (let y = 1; y <= years; y++) {
      let annualCouponSum = 0;

      for (let m = 1; m <= 12; m++) {
        // Довнесение в начале месяца
        if (monthlyContribution > 0) {
          totalInvested += monthlyContribution;
          if (reinvest) {
            currentNominal += monthlyContribution;
          }
        }

        const couponMonth = (reinvest ? currentNominal : totalInvested) * monthlyRate;
        annualCouponSum += couponMonth;

        if (reinvest) {
          currentNominal += couponMonth;
        } else {
          totalCouponsPaidOut += couponMonth;
        }
      }

      const nominalAtYearEnd = reinvest
        ? currentNominal
        : totalInvested + totalCouponsPaidOut;

      const inflationFactor = Math.pow(1 + inflationRate / 100, y);
      const realAtYearEnd = nominalAtYearEnd / inflationFactor;

      data.push({
        year: y,
        invested: Math.round(totalInvested),
        nominalBalance: Math.round(nominalAtYearEnd),
        realBalance: Math.round(realAtYearEnd),
        annualCoupons: Math.round(annualCouponSum),
        cumulativeCoupons: Math.round(reinvest ? nominalAtYearEnd - totalInvested : totalCouponsPaidOut),
      });
    }

    const final = data[data.length - 1];
    const simpleInterestNominal =
      totalInvested + (totalInvested * (netYtm / 100) * years);
    const compoundBonus = reinvest
      ? Math.max(final.nominalBalance - Math.round(simpleInterestNominal), 0)
      : 0;

    const realProfit = final.realBalance - final.invested;
    const realAnnualizedReturn = (Math.pow(final.realBalance / final.invested, 1 / years) - 1) * 100;

    return {
      yearlyData: data,
      finalNominal: final.nominalBalance,
      finalReal: final.realBalance,
      finalInvested: final.invested,
      totalProfit: final.nominalBalance - final.invested,
      realProfit,
      realAnnualizedReturn: Number.isFinite(realAnnualizedReturn) ? realAnnualizedReturn : 0,
      compoundBonus,
      monthlyPassiveIncome: Math.round((final.nominalBalance * (netYtm / 100)) / 12),
    };
  }, [effectiveCapital, years, reinvest, netYtm, inflationRate, monthlyContribution]);

  return (
    <div
      style={{
        background: '#ffffff',
        borderRadius: 12,
        border: '1px solid #d6e2e6',
        padding: 24,
        marginTop: 32,
        boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
      }}
    >
      {/* Заголовок */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 20,
          borderBottom: '1px solid #eef3f5',
          paddingBottom: 16,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <TrendingUp size={22} color="#0B526B" />
            <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: '#01121a' }}>
              Калькулятор Капитала & Доходности Портфеля
            </h2>
          </div>
          <p style={{ margin: '4px 0 0', color: '#516c79', fontSize: 13 }}>
            Прогноз сложного процента, реинвестирования купонов и реальной покупательной способности с учётом инфляции.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: '#717680', fontWeight: 500 }}>Налог (НДФЛ):</span>
          <button
            onClick={() => setTaxRate(0)}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: 'none',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              background: taxRate === 0 ? '#0B526B' : '#f0f4f8',
              color: taxRate === 0 ? '#fff' : '#516c79',
            }}
          >
            0% (Льгота)
          </button>
          <button
            onClick={() => setTaxRate(13)}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: 'none',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              background: taxRate === 13 ? '#0B526B' : '#f0f4f8',
              color: taxRate === 13 ? '#fff' : '#516c79',
            }}
          >
            13% (НДФЛ)
          </button>
        </div>
      </div>

      {/* Панель Управления и Ввода Параметров */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 16,
          background: '#f8fafc',
          padding: 16,
          borderRadius: 10,
          border: '1px solid #e1e9ed',
          marginBottom: 24,
        }}
      >
        {/* Сумма инвестиций */}
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#516c79', marginBottom: 6 }}>
            Стартовый капитал ({currency})
          </label>
          <div style={{ display: 'flex', alignItems: 'center', background: '#fff', border: '1px solid #d6e2e6', borderRadius: 6, padding: '6px 10px' }}>
            <DollarSign size={16} color="#717680" />
            <input
              type="number"
              min={100}
              step={1000}
              value={capital}
              onChange={(e) => setCapital(Math.max(0, Number(e.target.value)))}
              style={{ width: '100%', border: 'none', outline: 'none', fontSize: 14, fontWeight: 700, color: '#01121a', marginLeft: 4 }}
            />
          </div>
        </div>

        {/* Срок инвестирования */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#516c79' }}>
              Срок инвестирования
            </label>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#0B526B' }}>
              {years} {years === 1 ? 'год' : years < 5 ? 'года' : 'лет'}
            </span>
          </div>
          <input
            type="range"
            min={1}
            max={20}
            step={1}
            value={years}
            onChange={(e) => setYears(Number(e.target.value))}
            style={{ width: '100%', accentColor: '#0B526B', cursor: 'pointer' }}
          />
        </div>

        {/* Доходность (YTM) */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#516c79' }}>
              Доходность портфеля (% годовых)
            </label>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#06b663' }}>
              {effectiveYtm.toFixed(1)}% {taxRate > 0 && `(чистыми ${netYtm.toFixed(1)}%)`}
            </span>
          </div>
          <input
            type="range"
            min={3}
            max={35}
            step={0.5}
            value={effectiveYtm}
            onChange={(e) => setCustomYtm(Number(e.target.value))}
            style={{ width: '100%', accentColor: '#06b663', cursor: 'pointer' }}
          />
        </div>

        {/* Инфляция */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#516c79' }}>
              Ожидаемая инфляция (% в год)
            </label>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#dc6803' }}>
              {inflationRate.toFixed(1)}%
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={25}
            step={0.5}
            value={inflationRate}
            onChange={(e) => setInflationRate(Number(e.target.value))}
            style={{ width: '100%', accentColor: '#dc6803', cursor: 'pointer' }}
          />
        </div>

        {/* Ежемесячное пополнение */}
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#516c79', marginBottom: 6 }}>
            Ежемесячное пополнение ({currency})
          </label>
          <div style={{ display: 'flex', alignItems: 'center', background: '#fff', border: '1px solid #d6e2e6', borderRadius: 6, padding: '6px 10px' }}>
            <Calendar size={16} color="#717680" />
            <input
              type="number"
              min={0}
              step={100}
              value={monthlyContribution}
              onChange={(e) => setMonthlyContribution(Math.max(0, Number(e.target.value)))}
              placeholder="0"
              style={{ width: '100%', border: 'none', outline: 'none', fontSize: 14, fontWeight: 700, color: '#01121a', marginLeft: 4 }}
            />
          </div>
        </div>

        {/* Реинвестирование купонов (Toggle) */}
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#516c79', marginBottom: 6 }}>
            Режим купонов
          </label>
          <div style={{ display: 'flex', background: '#fff', border: '1px solid #d6e2e6', borderRadius: 6, padding: 2 }}>
            <button
              onClick={() => setReinvest(true)}
              style={{
                flex: 1,
                padding: '6px 8px',
                borderRadius: 4,
                border: 'none',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: reinvest ? '#0B526B' : 'transparent',
                color: reinvest ? '#fff' : '#516c79',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 4,
              }}
            >
              <Sparkles size={13} />
              Реинвестировать
            </button>
            <button
              onClick={() => setReinvest(false)}
              style={{
                flex: 1,
                padding: '6px 8px',
                borderRadius: 4,
                border: 'none',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: !reinvest ? '#717680' : 'transparent',
                color: !reinvest ? '#fff' : '#516c79',
              }}
            >
              Снимать
            </button>
          </div>
        </div>
      </div>

      {/* KPI Карточки Результатов */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        {/* Номинальный Капитал */}
        <div style={{ background: '#f5fbf8', border: '1px solid #b7ebcf', borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#0e8345' }}>
            Итоговый капитал ({years} {years === 1 ? 'год' : years < 5 ? 'года' : 'лет'})
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#0e8345', marginTop: 6 }}>
            {simulation.finalNominal.toLocaleString('ru-RU')} {currency}
          </div>
          <div style={{ fontSize: 12, color: '#516c79', marginTop: 4 }}>
            Чистая прибыль: <strong>+{simulation.totalProfit.toLocaleString('ru-RU')} {currency}</strong> (
            {((simulation.totalProfit / simulation.finalInvested) * 100).toFixed(1)}%)
          </div>
        </div>

        {/* Реальная Покупательная Способность */}
        <div style={{ background: '#fff9f2', border: '1px solid #f9d8b3', borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#b54708' }}>
            Реальная ценность (с инфляцией {inflationRate}%)
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#b54708', marginTop: 6 }}>
            {simulation.finalReal.toLocaleString('ru-RU')} {currency}
          </div>
          <div style={{ fontSize: 12, color: '#516c79', marginTop: 4 }}>
            Реальный прирост: <strong>{simulation.realProfit >= 0 ? '+' : ''}{simulation.realProfit.toLocaleString('ru-RU')} {currency}</strong> ({simulation.realAnnualizedReturn.toFixed(1)}% в год)
          </div>
        </div>

        {/* Пассивный Поток / Купоны */}
        <div style={{ background: '#f0f7fa', border: '1px solid #c5e0eb', borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#0B526B' }}>
            {reinvest ? 'Пассивный доход на конец срока' : 'Купонный доход в месяц'}
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#0B526B', marginTop: 6 }}>
            ~{simulation.monthlyPassiveIncome.toLocaleString('ru-RU')} {currency} / мес
          </div>
          <div style={{ fontSize: 12, color: '#516c79', marginTop: 4 }}>
            Годовой поток: <strong>{(simulation.monthlyPassiveIncome * 12).toLocaleString('ru-RU')} {currency}</strong>
          </div>
        </div>

        {/* Эффект сложного процента */}
        <div style={{ background: '#f8fafc', border: '1px solid #d6e2e6', borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#516c79' }}>
            Бонус сложного процента
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#01121a', marginTop: 6 }}>
            {reinvest ? `+${simulation.compoundBonus.toLocaleString('ru-RU')} ${currency}` : 'Выключен'}
          </div>
          <div style={{ fontSize: 12, color: '#717680', marginTop: 4 }}>
            {reinvest
              ? 'Дополнительный доход от реинвестирования купонов'
              : 'Включите реинвестирование для максимизации капитала'}
          </div>
        </div>
      </div>

      {/* График Динамики Капитала */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#01121a', margin: 0 }}>
            Динамика Капитала: Номинальный vs Реальный (с учётом инфляции {inflationRate}%)
          </h3>
          <span style={{ fontSize: 12, color: '#8fa0a8' }}>Суммы указаны в {currency}</span>
        </div>

        <div style={{ width: '100%', height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={simulation.yearlyData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="nominalGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b663" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#06b663" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="realGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#dc6803" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#dc6803" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="investedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0B526B" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#0B526B" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f4f8" vertical={false} />
              <XAxis dataKey="year" tickFormatter={(v) => `Год ${v}`} tick={{ fontSize: 12, fill: '#717680' }} />
              <YAxis
                tickFormatter={(v) => (v >= 1000000 ? `${(v / 1000000).toFixed(1)}M` : `${Math.round(v / 1000)}k`)}
                tick={{ fontSize: 12, fill: '#717680' }}
              />
              <Tooltip
                formatter={(val: any, name: string) => {
                  const num = Number(val) || 0;
                  const label =
                    name === 'nominalBalance'
                      ? 'Номинальный капитал'
                      : name === 'realBalance'
                      ? 'Реальная ценность (с инфляцией)'
                      : 'Вложено средств';
                  return [`${num.toLocaleString('ru-RU')} ${currency}`, label];
                }}
                labelFormatter={(l) => `Год ${l}`}
                contentStyle={{ background: '#fff', borderRadius: 8, border: '1px solid #d6e2e6', fontSize: 12 }}
              />
              <Legend
                formatter={(v) =>
                  v === 'nominalBalance'
                    ? 'Номинальный баланс'
                    : v === 'realBalance'
                    ? 'Реальная покупательная способность'
                    : 'Собственные вложения'
                }
              />
              <Area
                type="monotone"
                dataKey="nominalBalance"
                stroke="#06b663"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#nominalGrad)"
              />
              <Area
                type="monotone"
                dataKey="realBalance"
                stroke="#dc6803"
                strokeWidth={2}
                strokeDasharray="4 4"
                fillOpacity={1}
                fill="url(#realGrad)"
              />
              <Area
                type="monotone"
                dataKey="invested"
                stroke="#0B526B"
                strokeWidth={1.5}
                fillOpacity={1}
                fill="url(#investedGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Переключатель разворота подробной таблицы */}
      <div>
        <button
          onClick={() => setShowTable(!showTable)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'transparent',
            border: 'none',
            color: '#0B526B',
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer',
            padding: 0,
            marginBottom: 12,
          }}
        >
          {showTable ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          {showTable ? 'Скрыть разбивку по годам' : 'Показать подробную разбивку по годам'}
        </button>

        {showTable && (
          <div style={{ overflowX: 'auto', border: '1px solid #e1e9ed', borderRadius: 8 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e1e9ed', textAlign: 'left', color: '#5a6e78' }}>
                  <th style={{ padding: '8px 12px' }}>Год</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Вложено средств</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Купоны за год</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Накопленный доход</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Номинальный баланс</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Реальная ценность</th>
                </tr>
              </thead>
              <tbody>
                {simulation.yearlyData.map((row) => (
                  <tr key={row.year} style={{ borderBottom: '1px solid #f0f4f8' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 600, color: '#01121a' }}>
                      {row.year === 0 ? 'Старт (0)' : `Год ${row.year}`}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: '#516c79' }}>
                      {row.invested.toLocaleString('ru-RU')} {currency}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: '#06b663', fontWeight: 600 }}>
                      {row.annualCoupons > 0 ? `+${row.annualCoupons.toLocaleString('ru-RU')}` : '—'} {row.annualCoupons > 0 ? currency : ''}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: '#0B526B', fontWeight: 600 }}>
                      +{row.cumulativeCoupons.toLocaleString('ru-RU')} {currency}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: '#0e8345', fontWeight: 700 }}>
                      {row.nominalBalance.toLocaleString('ru-RU')} {currency}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: '#b54708', fontWeight: 700 }}>
                      {row.realBalance.toLocaleString('ru-RU')} {currency}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Поясняющая справка */}
      <div
        style={{
          marginTop: 16,
          padding: 12,
          background: '#f8fafc',
          borderRadius: 8,
          border: '1px solid #e1e9ed',
          fontSize: 12,
          color: '#516c79',
          display: 'flex',
          alignItems: 'flex-start',
          gap: 8,
        }}
      >
        <HelpCircle size={16} color="#717680" style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <strong>Как рассчитывается реальная ценность (эффект Фишера):</strong> Номинальная сумма дисконтируется по формуле Real = Nominal / (1 + Inflation)^T. При реинвестировании купонов сложный процент экспоненциально обгоняет инфляцию, сохраняя и преумножая реальную покупательную способность капитала.
        </div>
      </div>
    </div>
  );
}
