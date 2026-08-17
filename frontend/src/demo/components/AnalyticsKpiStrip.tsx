interface Props {
  attractive: number;
  review: number;
  distressed: number;
  bestYield: number;
  asOf: string;
}

export default function AnalyticsKpiStrip({ attractive, review, distressed, bestYield, asOf }: Props) {
  const time = asOf ? new Date(asOf).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '';
  return (
    <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
      <KpiCard
        value={attractive}
        label="привлекательных идей"
        color="#06b663"
      />
      <KpiCard
        value={review}
        label="требуют проверки"
        color="#dc6803"
      />
      <KpiCard
        value={distressed}
        label="дистрибуция / риск"
        color="#e03400"
      />
      <KpiCard
        value={`${bestYield.toFixed(2)}%`}
        label="макс. доходность (без дистрибуций)"
        color="#0B526B"
      />
      <KpiCard
        value={time}
        label="обновлено"
        color="#516c79"
      />
    </div>
  );
}

function KpiCard({ value, label, color }: { value: string | number; label: string; color: string }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 160,
        padding: '16px 20px',
        background: '#ffffff',
        border: '1px solid #eef3f5',
        borderRadius: 10,
      }}
    >
      <div style={{ fontSize: 28, fontWeight: 700, color, lineHeight: 1.2 }}>
        {value}
      </div>
      <div style={{ fontSize: 13, color: '#516c79', marginTop: 4 }}>
        {label}
      </div>
    </div>
  );
}
