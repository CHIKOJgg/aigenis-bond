import { Component, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { useI18n } from '../i18n';

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <ErrorFallback onReset={() => this.setState({ error: null })} />;
    }
    return this.props.children;
  }
}

function ErrorFallback({ onReset }: { onReset: () => void }) {
  const { t } = useI18n();
  return (
    <div className="min-h-screen bg-[#f5f9fb] flex items-center justify-center p-6">
      <div className="bg-white border border-[#d6e2e6] rounded-2xl p-8 max-w-md w-full text-center">
        <div className="w-14 h-14 bg-[#e03400]/10 rounded-full flex items-center justify-center mx-auto mb-4">
          <AlertTriangle size={26} className="text-[#e03400]" />
        </div>
        <h1 className="text-lg font-bold mb-2">{t('error.title')}</h1>
        <p className="text-sm text-[#516c79] mb-6">{t('error.desc')}</p>
        <button
          onClick={onReset}
          className="inline-flex items-center gap-2 bg-[#004b65] hover:bg-[#387387] text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
        >
          <RotateCcw size={15} /> {t('error.retry')}
        </button>
      </div>
    </div>
  );
}
