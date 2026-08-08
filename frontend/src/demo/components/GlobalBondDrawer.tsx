import { useEffect, useState } from 'react';
import { fetchLiveBond } from '../live-demo-api';
import { bondDrawerStore, useOpenBond } from '../drawer-store';
import {
  getAllBonds,
  scoreFromLiveBond,
} from '../demo-api';
import BondDetailDrawer from './BondDetailDrawer';
import type { LiveBondDetail, DemoBond, DemoScore } from '../types';

interface State {
  bond: DemoBond | null;
  score: DemoScore | undefined;
  detail: LiveBondDetail | null;
  loading: boolean;
  error: boolean;
}

const EMPTY: State = { bond: null, score: undefined, detail: null, loading: false, error: false };

export default function GlobalBondDrawer() {
  const bondId = useOpenBond();
  const [state, setState] = useState<State>(EMPTY);

  useEffect(() => {
    if (!bondId) {
      setState(EMPTY);
      return;
    }
    let cancelled = false;
    setState({ ...EMPTY, loading: true });
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    (async () => {
      try {
        const detail = await fetchLiveBond(bondId, controller.signal);
        if (cancelled) return;
        const score = scoreFromLiveBond(detail);
        setState({ bond: detail, score, detail, loading: false, error: false });
      } catch {
        if (cancelled) return;
        const fixture = getAllBonds().find((b) => b.internal_id === bondId);
        if (!fixture) {
          setState({ bond: null, score: undefined, detail: null, loading: false, error: true });
          return;
        }
        setState({ bond: fixture, score: undefined, detail: null, loading: false, error: false });
      } finally {
        if (!cancelled) clearTimeout(timeout);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bondId]);

  if (!bondId) return null;

  if (state.loading) {
    return (
      <Overlay>
        <div
          role="dialog"
          aria-modal="true"
          aria-busy="true"
          aria-label="Загрузка облигации"
          style={drawerStyle}
        >
          <div style={{ padding: '24px', color: '#516c79', fontSize: 14 }}>Загрузка данных…</div>
        </div>
      </Overlay>
    );
  }

  if (state.error || !state.bond) {
    return (
      <Overlay>
        <div role="dialog" aria-modal="true" aria-label="Облигация не найдена" style={drawerStyle}>
          <div style={{ padding: '24px', color: '#516c79', fontSize: 14 }}>
            Облигация не найдена
          </div>
          <div style={{ padding: '0 24px 24px' }}>
            <button onClick={() => bondDrawerStore.close()} style={closeBtn}>Закрыть</button>
          </div>
        </div>
      </Overlay>
    );
  }

  return (
    <BondDetailDrawer
      bondId={bondId}
      bond={state.bond}
      score={state.score}
      detail={state.detail ?? undefined}
      onClose={() => bondDrawerStore.close()}
      onPortfolioImpact={() => {
        const id = bondId;
        bondDrawerStore.close();
        const next = window.location.pathname.replace(/\/bonds\/[^/]+$/, '');
        window.location.href = `${next}/portfolio-impact/${encodeURIComponent(id)}?market=ALL`;
      }}
    />
  );
}

function Overlay({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div
        aria-hidden="true"
        onClick={() => bondDrawerStore.close()}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.25)',
          zIndex: 100,
        }}
      />
      {children}
    </>
  );
}

const drawerStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  right: 0,
  bottom: 0,
  width: 520,
  maxWidth: '92vw',
  background: '#ffffff',
  zIndex: 101,
  boxShadow: '-4px 0 24px rgba(0,0,0,0.1)',
  display: 'flex',
  flexDirection: 'column',
};

const closeBtn: React.CSSProperties = {
  padding: '8px 18px',
  borderRadius: 8,
  border: '1px solid #d6e2e6',
  background: '#ffffff',
  color: '#0B526B',
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
};