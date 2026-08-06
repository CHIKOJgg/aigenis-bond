import { Navigate, useNavigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from '../lib/AuthContext';
import { UpgradePrompt } from '../lib/gate';
import { ROUTES } from './paths';

export function RequirePremium({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  if (user?.subscription_tier === 'free') {
    return <UpgradePrompt onSubscribe={() => navigate(ROUTES.subscribe)} />;
  }
  return <>{children}</>;
}

export function PublicOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user) return <Navigate to={ROUTES.home} replace />;
  return <>{children}</>;
}
