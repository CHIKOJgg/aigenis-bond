import { BrowserRouter, useNavigate } from 'react-router-dom';
import { AuthProvider } from './lib/AuthContext';
import { PaywallProvider } from './lib/PaywallContext';
import { ToastProvider } from './lib/ToastContext';
import { I18nProvider } from './i18n';
import { ExchangeProvider } from './lib/ExchangeContext';
import { PaywallModal } from './PaywallModal';
import { ErrorBoundary } from './app/ErrorBoundary';
import { ScrollToTop } from './app/ScrollToTop';
import AppRoutes from './app/router';
import { ROUTES } from './app/paths';

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <PaywallProvider>
          <ToastProvider>
            <BrowserRouter>
              <ExchangeProvider>
                <ErrorBoundary>
                  <ScrollToTop />
                  <AppRoutes />
                </ErrorBoundary>
                <AppModals />
              </ExchangeProvider>
            </BrowserRouter>
          </ToastProvider>
        </PaywallProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

function AppModals() {
  const navigate = useNavigate();
  return <PaywallModal onSubscribe={() => navigate(ROUTES.subscribe)} />;
}
