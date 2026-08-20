import { DEMO_DISCLAIMER } from '../demo-config';

export default function DemoDisclaimer() {
  return (
    <footer
      style={{
        padding: '10px 32px',
        borderTop: '1px solid var(--demo-border, #d6e2e6)',
        fontSize: 12,
        color: '#5c666f',
        textAlign: 'center',
        backgroundColor: '#fafafa',
      }}
    >
      {DEMO_DISCLAIMER}
    </footer>
  );
}
