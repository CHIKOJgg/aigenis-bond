export default function DemoStatusBanner() {
  return (
    <div
      style={{
        padding: '6px 32px',
        fontSize: 12,
        fontWeight: 500,
        color: '#0B526B',
        backgroundColor: '#eef3f5',
        borderBottom: '1px solid #d6e2e6',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
        <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', backgroundColor: '#0B526B' }} />
         Демонстрационная среда · актуальные рыночные данные и скоринг движка Aigenis · только чтение
       </div>
  );
}
