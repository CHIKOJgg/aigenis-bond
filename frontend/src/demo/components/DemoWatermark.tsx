export default function DemoWatermark() {
  return (
    <div
      style={{
        position: 'fixed',
        bottom: 36,
        left: 0,
        right: 0,
        textAlign: 'center',
        pointerEvents: 'none',
        zIndex: 9999,
      }}
    >
      <span
        style={{
          fontSize: 11,
          color: 'rgba(0,75,101,0.85)',
          fontWeight: 600,
          letterSpacing: 1,
          textTransform: 'uppercase',
        }}
      >
        Demo · Aigenis Analytics Preview
      </span>
    </div>
  );
}
