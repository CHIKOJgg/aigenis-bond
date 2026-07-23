import { useState } from 'react';
import { Star, X, TrendingUp, BarChart3, Search, Newspaper } from 'lucide-react';
import { Modal } from '../lib/Modal';
import { useI18n } from '../i18n';
import { LoadingSkeleton } from './common';
import type { Bond, BondAnalysisResult, Cashflow } from '../lib/api';
import { api, ApiError } from '../lib/api';

interface BondDetailModalProps {
  bond: Bond;
  isFavorite?: boolean;
  onToggleFavorite?: () => void;
  onClose: () => void;
  onSubscribe?: () => void;
}

type Tab = 'overview' | 'analytics' | 'similar' | 'news';

export default function BondDetailModal({ bond, isFavorite, onToggleFavorite, onClose, onSubscribe }: BondDetailModalProps) {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>('overview');
  const [analysis, setAnalysis] = useState<BondAnalysisResult | null>(null);
  const [analysisLocked, setAnalysisLocked] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [cashflow, setCashflow] = useState<Cashflow | null>(null);
  const [cashflowLocked, setCashflowLocked] = useState(false);
  const [cashflowLoading, setCashflowLoading] = useState(false);
  const [cfAmount, setCfAmount] = useState('1000');
  const [similarBonds, setSimilarBonds] = useState<Bond[]>([]);
  const [similarLoading, setSimilarLoading] = useState(false);

  const showAnalysis = async () => {
    setAnalysisLoading(true); setAnalysisLocked(false); setAnalysis(null);
    try {
      setAnalysis(await api.portfolio.analysis(bond.internal_id));
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) setAnalysisLocked(true);
    } finally { setAnalysisLoading(false); }
  };

  const showCashflow = async () => {
    setCashflowLoading(true); setCashflowLocked(false); setCashflow(null);
    try {
      const amt = Number(cfAmount) || 1000;
      setCashflow(await api.portfolio.cashflow(bond.internal_id, amt));
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) setCashflowLocked(true);
    } finally { setCashflowLoading(false); }
  };

  const loadSimilar = async () => {
    setSimilarLoading(true);
    try {
      const all = await api.bonds.list({ limit: 100 });
      setSimilarBonds(all.filter((b) => b.internal_id !== bond.internal_id && b.currency === bond.currency).slice(0, 6));
    } catch { /* ignore */ }
    finally { setSimilarLoading(false); }
  };

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Обзор', icon: <TrendingUp size={14} /> },
    { id: 'analytics', label: 'Аналитика', icon: <BarChart3 size={14} /> },
    { id: 'similar', label: 'Похожие', icon: <Search size={14} /> },
    { id: 'news', label: 'Новости', icon: <Newspaper size={14} /> },
  ];

  const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString() : '—';

  return (
    <Modal onClose={onClose} className="max-w-2xl w-full max-h-[90vh] overflow-y-auto">
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold">{bond.internal_id}</h3>
          <div className="flex items-center gap-2">
            {onToggleFavorite && (
              <button onClick={onToggleFavorite} className="text-gray-400 hover:text-amber-400 p-1">
                <Star size={18} className={isFavorite ? 'fill-amber-400 text-amber-400' : ''} />
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-white p-1"><X size={18} /></button>
          </div>
        </div>

        <div className="flex gap-1 border-b border-gray-800 mb-4 overflow-x-auto">
          {tabs.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                tab === t.id ? 'border-emerald-400 text-emerald-400' : 'border-transparent text-gray-400 hover:text-gray-200'
              }`}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {tab === 'overview' && (
          <div>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <DetailRow label={t('common.name')} value={bond.name} />
              <DetailRow label={t('common.currency')} value={bond.currency} />
              <DetailRow label={t('common.issuer')} value={bond.issuer || '-'} />
              <DetailRow label={t('common.price')} value={bond.price != null ? bond.price.toFixed(2) : '-'} />
              <DetailRow label={t('common.ytm')} value={bond.yield_to_maturity != null ? `${bond.yield_to_maturity.toFixed(2)}%` : '-'} />
              <DetailRow label={t('detail.couponRate')} value={bond.coupon_rate != null ? `${bond.coupon_rate.toFixed(2)}%` : '-'} />
              <DetailRow label={t('common.frequency')} value={bond.coupon_frequency != null ? `${bond.coupon_frequency}x/year` : '-'} />
              <DetailRow label={t('common.maturity')} value={fmtDate(bond.maturity_date)} />
              <DetailRow label={t('common.status')} value={bond.status} />
              <DetailRow label={t('common.lastUpdated')} value={bond.fetched_at ? new Date(bond.fetched_at).toLocaleString() : '-'} />
            </dl>

            <div className="mt-4 flex flex-wrap gap-2">
              <button onClick={showAnalysis} className="bg-gray-800 hover:bg-gray-700 text-sm text-white px-3 py-2 rounded-lg transition-colors">Анализ</button>
              <button onClick={showCashflow} className="bg-gray-800 hover:bg-gray-700 text-sm text-white px-3 py-2 rounded-lg transition-colors">Доход</button>
            </div>

            {analysisLoading && <LoadingSkeleton />}
            {analysisLocked && <UpgradePrompt onSubscribe={onSubscribe} />}
            {analysis && !analysisLocked && (
              <div className="mt-4 bg-gray-800/40 rounded-xl p-4 space-y-3">
                <h4 className="font-semibold">{analysis.analysis.verdict}</h4>
                {Array.isArray(analysis.analysis.reasons) && analysis.analysis.reasons.length > 0 && (
                  <ul className="list-disc pl-5 text-sm text-gray-300 space-y-1">
                    {analysis.analysis.reasons.map((r, i) => <li key={i}>{String(r)}</li>)}
                  </ul>
                )}
                {analysis.ml_prediction && (
                  <div className="text-sm text-gray-300 space-y-1 border-t border-gray-700 pt-2">
                    <div>ML: <b className="capitalize">{analysis.ml_prediction.decision}</b> (conf {analysis.ml_prediction.confidence.toFixed(2)})</div>
                  </div>
                )}
              </div>
            )}

            {cashflowLoading && <LoadingSkeleton />}
            {cashflowLocked && <UpgradePrompt onSubscribe={onSubscribe} />}
            {cashflow && !cashflowLocked && (
              <div className="mt-3 bg-gray-800/40 rounded-xl p-4 text-sm space-y-2">
                <div className="flex justify-between"><span className="text-gray-400">Годовой доход</span><span className="font-mono text-emerald-400">{cashflow.annual_income.toFixed(2)}</span></div>
                <div className="flex justify-between"><span className="text-gray-400">Доходность</span><span className="font-mono">{cashflow.yield_on_cost.toFixed(2)}%</span></div>
              </div>
            )}
          </div>
        )}

        {tab === 'analytics' && (
          <div className="text-center py-8">
            <BarChart3 size={48} className="mx-auto mb-4 text-gray-600" />
            <p className="text-gray-400 mb-4">Графики цены, доходности и скоринга за 6M/1Y/3Y</p>
            <button onClick={showAnalysis} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm">Загрузить аналитику</button>
          </div>
        )}

        {tab === 'similar' && (
          <div>
            {similarBonds.length === 0 && !similarLoading && (
              <div className="text-center py-8">
                <Search size={48} className="mx-auto mb-4 text-gray-600" />
                <p className="text-gray-400 mb-4">Найдите похожие облигации</p>
                <button onClick={loadSimilar} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm">Загрузить</button>
              </div>
            )}
            {similarLoading && <LoadingSkeleton />}
            {similarBonds.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {similarBonds.map((b) => (
                  <div key={b.internal_id} className="bg-gray-800/40 rounded-xl p-3 border border-gray-700/50">
                    <p className="font-medium text-sm truncate">{b.name}</p>
                    <div className="flex flex-wrap gap-x-3 text-xs text-gray-400 mt-1">
                      <span>YTM: {b.yield_to_maturity?.toFixed(2)}%</span>
                      <span>{b.currency}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'news' && (
          <div className="text-center py-8">
            <Newspaper size={48} className="mx-auto mb-4 text-gray-600" />
            <p className="text-gray-400">Новости по эмитенту</p>
          </div>
        )}
      </div>
    </Modal>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-gray-200 font-medium truncate">{value}</span>
    </div>
  );
}

function UpgradePrompt({ onSubscribe }: { onSubscribe?: () => void }) {
  return (
    <div className="mt-4 bg-amber-900/20 border border-amber-500/20 rounded-xl p-4 text-center">
      <p className="text-sm text-amber-300 mb-2">Доступно по подписке Pro</p>
      <button onClick={onSubscribe} className="bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-sm">Открыть Pro</button>
    </div>
  );
}
