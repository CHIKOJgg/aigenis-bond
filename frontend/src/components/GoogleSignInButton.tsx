import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { useAuth } from '../lib/AuthContext';
import { useI18n } from '../i18n';

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }) => void;
          renderButton: (
            element: HTMLElement,
            options: { theme?: string; size?: string; text?: string; width?: number; shape?: string; logo_alignment?: string },
          ) => void;
        };
      };
    };
  }
}

const GOOGLE_CLIENT_ID = '780703079643-d2acg5sasj38cbn7q9k5epumgbnus13t.apps.googleusercontent.com';

export function GoogleSignInButton() {
  const { refreshUser } = useAuth();
  const { t } = useI18n();
  const btnRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const handleCredential = async (response: { credential: string }) => {
      try {
        const res = await api.auth.google(response.credential);
        localStorage.setItem('access_token', res.access_token);
        localStorage.setItem('refresh_token', res.refresh_token);
        await refreshUser();
      } catch (e: unknown) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : 'Google login failed';
          setError(msg === 'Failed to fetch' ? t('auth.fetchError') : msg);
        }
      }
    };

    const init = () => {
      if (!window.google?.accounts?.id) return;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: handleCredential,
      });
      if (btnRef.current) {
        window.google.accounts.id.renderButton(btnRef.current, {
          theme: 'filled_black',
          size: 'large',
          text: 'continue_with',
          shape: 'rectangular',
          width: 320,
        });
      }
    };

    if (window.google?.accounts?.id) {
      init();
      return () => { cancelled = true; };
    }

    const existing = document.querySelector<HTMLScriptElement>('script[data-gsi-client]');
    if (existing) {
      existing.addEventListener('load', init);
      return () => { cancelled = true; existing.removeEventListener('load', init); };
    }

    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.dataset.gsiClient = '1';
    script.onload = init;
    document.head.appendChild(script);

    return () => {
      cancelled = true;
      script.removeEventListener('load', init);
    };
  }, [refreshUser]);

  return (
    <div className="flex flex-col items-center">
      <div ref={btnRef} className="min-h-[40px]" />
      {error && <div className="text-red-400 text-sm mt-2">{error}</div>}
    </div>
  );
}
