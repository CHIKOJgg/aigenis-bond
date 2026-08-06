import { useI18n } from '../../i18n';
import {
  BondIcon as CommonBondIcon,
  DecisionBadge,
  TierBadge,
} from '../../components/common';
import { BondIcon, CurrencyBadge, ScoreTierBadge, StatusBadge } from '../analytics/components/badges';
import YieldCurveChart from '../../components/charts/YieldCurveChart';
import RVHeatmap from '../../components/charts/RVHeatmap';
import StressWaterfall from '../../components/charts/StressWaterfall';
import CarryBarChart from '../../components/charts/CarryBarChart';

const PALETTE: { token: string; hex: string; usage: string }[] = [
  { token: 'aigenis-50', hex: '#eef3f5', usage: 'surface / subtle fills' },
  { token: 'aigenis-100', hex: '#d9e4e8', usage: 'section backgrounds' },
  { token: 'aigenis-200', hex: '#b2c9d1', usage: 'borders (strong)' },
  { token: 'aigenis-300', hex: '#759eac', usage: 'tertiary accents' },
  { token: 'aigenis-400', hex: '#387387', usage: 'hover / secondary accents' },
  { token: 'aigenis-500', hex: '#004b65', usage: 'brand primary' },
  { token: 'aigenis-600', hex: '#004055', usage: 'pressed states' },
  { token: 'aigenis-700', hex: '#003545', usage: 'deep brand' },
  { token: 'aigenis-800', hex: '#002935', usage: 'headers' },
  { token: 'aigenis-900', hex: '#001d25', usage: 'dark text' },
  { token: 'aigenis-950', hex: '#001115', usage: 'darkest' },
  { token: 'aigenis-text', hex: '#01121a', usage: 'body text' },
  { token: 'aigenis-text-secondary', hex: '#516c79', usage: 'secondary text' },
  { token: 'aigenis-text-muted', hex: '#717680', usage: 'muted text' },
  { token: 'aigenis-placeholder', hex: '#a4a7ae', usage: 'placeholders' },
  { token: 'aigenis-border', hex: '#d6e2e6', usage: 'default borders' },
  { token: 'aigenis-border-strong', hex: '#b2c9d1', usage: 'strong borders' },
  { token: 'aigenis-card', hex: '#ffffff', usage: 'cards' },
  { token: 'aigenis-bg', hex: '#f5f9fb', usage: 'page background' },
  { token: 'aigenis-input', hex: '#f8fafb', usage: 'inputs' },
  { token: 'aigenis-surface', hex: '#fafafa', usage: 'surfaces' },
  { token: 'aigenis-surface-subtle', hex: '#f5f5f5', usage: 'subtle surfaces' },
  { token: 'aigenis-hover', hex: '#f8fafb', usage: 'hover fills' },
  { token: 'aigenis-row-border', hex: '#f2f2f2', usage: 'row borders' },
  { token: 'aigenis-success-600', hex: '#06b663', usage: 'success' },
  { token: 'aigenis-success-50', hex: '#ebfff2', usage: 'success fill' },
  { token: 'aigenis-warning-600', hex: '#dc6803', usage: 'warning' },
  { token: 'aigenis-warning-500', hex: '#f79009', usage: 'warning accent' },
  { token: 'aigenis-warning-50', hex: '#fffaeb', usage: 'warning fill' },
  { token: 'aigenis-error-600', hex: '#e03400', usage: 'error' },
  { token: 'aigenis-error-50', hex: '#fff4ef', usage: 'error fill' },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-14">
      <h2 className="text-xl font-bold font-aigenis-heading mb-6 pb-2 border-b border-aigenis-border">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Swatch({ hex, token, usage }: { hex: string; token: string; usage: string }) {
  return (
    <div className="rounded-xl border border-aigenis-border overflow-hidden">
      <div className="h-14" style={{ backgroundColor: hex }} />
      <div className="p-2.5 text-xs">
        <p className="font-mono font-semibold">{token}</p>
        <p className="text-aigenis-text-muted">{hex}</p>
        <p className="text-aigenis-text-muted mt-0.5">{usage}</p>
      </div>
    </div>
  );
}

export function CatalogPage() {
  const { t } = useI18n();

  return (
    <div className="min-h-screen bg-aigenis-bg text-aigenis-text p-6 md:p-10">
      <div className="max-w-6xl mx-auto">
        <header className="mb-12">
          <h1 className="text-3xl font-bold font-aigenis-heading mb-2">Design Catalog</h1>
          <p className="text-aigenis-text-secondary">
            Aigenis theme review surface — tokens and components in one screen
            (dev builds only, reachable at /catalog).
          </p>
        </header>

        <Section title="Color tokens">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {PALETTE.map((s) => (
              <Swatch key={s.token} {...s} />
            ))}
          </div>
        </Section>

        <Section title="Typography">
          <div className="grid md:grid-cols-2 gap-6">
            <div className="rounded-xl border border-aigenis-border p-5 bg-aigenis-card">
              <p className="text-xs text-aigenis-text-muted mb-2 uppercase tracking-wide">
                font-aigenis-heading
              </p>
              <p className="font-aigenis-heading text-4xl font-bold mb-1">Analytics 40</p>
              <p className="font-aigenis-heading text-xl font-semibold mb-1">Analytics 20</p>
              <p className="font-aigenis-heading text-sm font-medium">Analytics 14</p>
            </div>
            <div className="rounded-xl border border-aigenis-border p-5 bg-aigenis-card">
              <p className="text-xs text-aigenis-text-muted mb-2 uppercase tracking-wide">
                font-aigenis-body
              </p>
              <p className="text-4xl mb-1">Body 40</p>
              <p className="text-xl mb-1">Body 20</p>
              <p className="text-sm">Body 14 · {t('common.allRights')}</p>
            </div>
          </div>
        </Section>

        <Section title="Badges & identity">
          <div className="flex flex-wrap items-center gap-4 p-5 rounded-xl border border-aigenis-border bg-aigenis-card">
            <ScoreTierBadge score={92} />
            <ScoreTierBadge score={75} />
            <ScoreTierBadge score={55} />
            <ScoreTierBadge score={30} />
            <ScoreTierBadge score={null} />
            <StatusBadge status="active" />
            <StatusBadge status="matured" />
            <StatusBadge status={null} />
            <CurrencyBadge currency="USD" />
            <CurrencyBadge currency={null} />
            <TierBadge tier="pro" />
            <TierBadge tier={null} />
            <DecisionBadge decision="buy" />
            <DecisionBadge decision="hold" />
            <DecisionBadge decision="sell" />
            <CommonBondIcon issuer="Министерство финансов" size={36} />
            <BondIcon name="Правительство РФ" size={36} />
          </div>
        </Section>

        <Section title="Interactive primitives">
          <div className="flex flex-wrap items-center gap-4 p-5 rounded-xl border border-aigenis-border bg-aigenis-card">
            <button className="bg-aigenis-500 hover:bg-aigenis-400 text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors">
              Primary
            </button>
            <button className="border border-aigenis-border-strong hover:border-aigenis-400 text-aigenis-text-secondary hover:text-aigenis-text px-5 py-2.5 rounded-xl text-sm font-medium transition-colors">
              Secondary
            </button>
            <button className="bg-aigenis-500 hover:bg-aigenis-400 text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors inline-flex items-center gap-2">
              With icon →
            </button>
            <div className="inline-flex items-center bg-white rounded-xl p-1 border border-aigenis-border">
              <button className="px-5 py-2 rounded-lg text-sm font-medium bg-aigenis-500 text-white shadow-lg shadow-aigenis-500/20">
                Active tab
              </button>
              <button className="px-5 py-2 rounded-lg text-sm font-medium text-aigenis-text-secondary hover:text-aigenis-text">
                Inactive tab
              </button>
            </div>
          </div>
        </Section>

        <Section title="Charts">
          <div className="grid md:grid-cols-2 gap-6">
            <div className="rounded-xl border border-aigenis-border p-4 bg-aigenis-card">
              <p className="text-sm font-semibold mb-3">Yield curve</p>
              <YieldCurveChart
                currencies={[
                  {
                    currency: 'USD',
                    points: [
                      { tenor: '1Y', years: 1, rate_pct: 4.2 },
                      { tenor: '2Y', years: 2, rate_pct: 4.6 },
                      { tenor: '5Y', years: 5, rate_pct: 5.1 },
                    ],
                  },
                  {
                    currency: 'BYN',
                    points: [
                      { tenor: '1Y', years: 1, rate_pct: 9.8 },
                      { tenor: '2Y', years: 2, rate_pct: 10.4 },
                      { tenor: '5Y', years: 5, rate_pct: 11.2 },
                    ],
                  },
                ]}
              />
            </div>
            <div className="rounded-xl border border-aigenis-border p-4 bg-aigenis-card">
              <p className="text-sm font-semibold mb-3">RV signals</p>
              <RVHeatmap
                signals={[
                  { internal_id: 'BY-1', z_score: 2.1, currency: 'BYN', issuer: 'MinFin' },
                  { internal_id: 'BY-2', z_score: -1.8, currency: 'BYN', issuer: 'Bank' },
                  { internal_id: 'BY-3', z_score: 0.2, currency: 'USD', issuer: 'Gov' },
                ]}
              />
            </div>
            <div className="rounded-xl border border-aigenis-border p-4 bg-aigenis-card">
              <p className="text-sm font-semibold mb-3">Stress waterfall</p>
              <StressWaterfall
                runs={[
                  { scenario_name: 'Rate +200', pnl_pct: -2.4 },
                  { scenario_name: 'Rate -100', pnl_pct: 1.2 },
                  { scenario_name: 'Credit spread', pnl_pct: -0.8 },
                ]}
              />
            </div>
            <div className="rounded-xl border border-aigenis-border p-4 bg-aigenis-card">
              <p className="text-sm font-semibold mb-3">Carry ranking</p>
              <CarryBarChart
                trades={[
                  { internal_id: 'BY-1', coupon_pct: 12.4, expected_pnl_pct: 2.1 },
                  { internal_id: 'BY-2', coupon_pct: 9.8, expected_pnl_pct: 1.4 },
                  { internal_id: 'BY-3', coupon_pct: 6.5, expected_pnl_pct: 0.9 },
                ]}
              />
            </div>
          </div>
        </Section>
      </div>
    </div>
  );
}
