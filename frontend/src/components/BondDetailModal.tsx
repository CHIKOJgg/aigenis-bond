import { useState, useRef, useEffect } from 'react';
import { Star, X, TrendingUp, BarChart3, Search, Newspaper, ExternalLink } from 'lucide-react';
import { Modal } from '../lib/Modal';
import { useI18n } from '../i18n';
import { LoadingSkeleton } from './common';
import type { Bond, BondAnalysisResult, Cashflow, NewsItem } from '../lib/api';
import { api, ApiError } from '../lib/api';

interface BondDetailModalProps {
  bond: Bond;
  isFavorite?: boolean;
  onToggleFavorite?: () => void;
  onClose: () => void;
  onSubscribe?: () => void;
  onOpenCompany?: (issuer: string) => void;
  onOpenBond?: (id: string) => void;
}

interface BondDetailContentProps {
  bond: Bond;
  onSubscribe?: () => void;
  onOpenCompany?: (issuer: string) => void;
  onOpenBond?: (id: string) => void;
  headerAction?: React.ReactNode;
}

type Tab = 'overview' | 'analytics' | 'similar' | 'news';

export default function BondDetailModal({ bond, isFavorite, onToggleFavorite, onClose, onSubscribe, onOpenCompany, onOpenBond }: BondDetailModalProps) {
  return (
    <Modal onClose={onClose} className="max-w-2xl w-full max-h-[90vh] overflow-y-auto">
      <div className="p-6">
        <BondDetailContent
          bond={bond}
          onSubscribe={onSubscribe}
          onOpenCompany={onOpenCompany}
          onOpenBond={onOpenBond}
          headerAction={
            <>
              {onToggleFavorite && (
                <button onClick={onToggleFavorite} className="text-[#a4a7ae] hover:text-[#004b65] p-1">
                  <Star size={18} className={isFavorite ? 'fill-[#004b65] text-[#004b65]' : ''} />
                </button>
              )}
              <button onClick={onClose} className="text-[#a4a7ae] hover:text-[#01121a] p-1"><X size={18} /></button>
            </>
          }
        />
      </div>
    </Modal>
  );
}

export function BondDetailContent({ bond, onSubscribe, onOpenCompany, onOpenBond, headerAction }: BondDetailContentProps) {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>('overview');
  const [analysis, setAnalysis] = useState<BondAnalysisResult | null>(null);
  const [analysisLocked, setAnalysisLocked] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [cashflow, setCashflow] = useState<Cashflow | null>(null);
  const [cashflowLocked, setCashflowLocked] = useState(false);
  const [cashflowLoading, setCashflowLoading] = useState(false);
  const cfAmount = '1000';
  const [similarBonds, setSimilarBonds] = useState<Bond[]>([]);
  const [similarLoading, setSimilarLoading] = useState(false);
  const [similarLoaded, setSimilarLoaded] = useState(false);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsLoaded, setNewsLoaded] = useState(false);

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
    if (similarLoaded) return;
    setSimilarLoading(true);
    try {
      const all = await api.bonds.list({ limit: 100 });
      setSimilarBonds(all.filter((b) => b.internal_id !== bond.internal_id && b.currency === bond.currency).slice(0, 6));
      setSimilarLoaded(true);
    } catch { /* ignore */ }
    finally { setSimilarLoading(false); }
  };

  const loadNews = async () => {
    if (newsLoaded) return;
    setNewsLoading(true);
    try {
      const items = await api.analytics.news({ bondId: bond.internal_id, limit: 10 });
      setNews(items);
      setNewsLoaded(true);
    } catch { /* ignore */ }
    finally { setNewsLoading(false); }
  };

  const prevTab = useRef(tab);
  useEffect(() => {
    if (tab === 'similar' && prevTab.current !== 'similar') {
      loadSimilar();
    }
    if (tab === 'news' && prevTab.current !== 'news') {
      loadNews();
    }
    prevTab.current = tab;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: t('detail.tabOverview'), icon: <TrendingUp size={14} /> },
    { id: 'analytics', label: t('detail.tabAnalytics'), icon: <BarChart3 size={14} /> },
    { id: 'similar', label: t('detail.tabSimilar'), icon: <Search size={14} /> },
    { id: 'news', label: t('detail.tabNews'), icon: <Newspaper size={14} /> },
  ];

  const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString() : '—';

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-[#01121a]">{bond.internal_id}</h3>
        <div className="flex items-center gap-2">{headerAction}</div>
      </div>

        <div className="flex gap-1 border-b border-[#d6e2e6] mb-4 overflow-x-auto">
          {tabs.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                tab === t.id ? 'border-[#004b65] text-[#004b65]' : 'border-transparent text-[#717680] hover:text-[#01121a]'
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
              {onOpenCompany && bond.issuer ? (
                <div className="flex flex-col">
                  <span className="text-xs text-[#717680]">{t('common.issuer')}</span>
                  <button onClick={() => onOpenCompany(bond.issuer!)} className="text-[#004b65] hover:text-[#387387] font-medium truncate text-left">{bond.issuer}</button>
                </div>
              ) : (
                <DetailRow label={t('common.issuer')} value={bond.issuer || '-'} />
              )}
              <DetailRow label={t('common.price')} value={bond.price != null ? bond.price.toFixed(2) : '-'} />
              <DetailRow label={t('common.ytm')} value={bond.yield_to_maturity != null ? `${bond.yield_to_maturity.toFixed(2)}%` : '-'} />
              <DetailRow label={t('detail.couponRate')} value={bond.coupon_rate != null ? `${bond.coupon_rate.toFixed(2)}%` : '-'} />
              <DetailRow label={t('common.frequency')} value={bond.coupon_frequency != null ? `${bond.coupon_frequency}x/year` : '-'} />
              <DetailRow label={t('common.maturity')} value={fmtDate(bond.maturity_date)} />
              <DetailRow label={t('common.status')} value={bond.status} />
              <DetailRow label={t('common.lastUpdated')} value={bond.fetched_at ? new Date(bond.fetched_at).toLocaleString() : '-'} />
            </dl>

            <div className="mt-4 flex flex-wrap gap-2">
              <button onClick={showAnalysis} className="bg-[#f8fafb] hover:bg-[#eef3f5] text-sm text-[#01121a] px-3 py-2 rounded-lg transition-colors border border-[#d6e2e6]">{t('detail.analyze')}</button>
              <button onClick={showCashflow} className="bg-[#f8fafb] hover:bg-[#eef3f5] text-sm text-[#01121a] px-3 py-2 rounded-lg transition-colors border border-[#d6e2e6]">{t('detail.income')}</button>
            </div>

            {analysisLoading && <LoadingSkeleton />}
            {analysisLocked && <UpgradePrompt onSubscribe={onSubscribe} />}
            {analysis && !analysisLocked && (
              <div className="mt-4 bg-[#f5f9fb] rounded-xl p-4 space-y-3 border border-[#d6e2e6]">
                <h4 className="font-semibold text-[#01121a]">{analysis.analysis.verdict}</h4>
                {Array.isArray(analysis.analysis.reasons) && analysis.analysis.reasons.length > 0 && (
                  <ul className="list-disc pl-5 text-sm text-[#516c79] space-y-1">
                    {analysis.analysis.reasons.map((r, i) => <li key={i}>{String(r)}</li>)}
                  </ul>
                )}
                {analysis.ml_prediction && (
                  <div className="text-sm text-[#516c79] space-y-1 border-t border-[#d6e2e6] pt-2">
                    <div>ML: <b className="capitalize text-[#01121a]">{analysis.ml_prediction.decision}</b> (conf {analysis.ml_prediction.confidence.toFixed(2)})</div>
                  </div>
                )}
              </div>
            )}

            {cashflowLoading && <LoadingSkeleton />}
            {cashflowLocked && <UpgradePrompt onSubscribe={onSubscribe} />}
            {cashflow && !cashflowLocked && (
              <div className="mt-3 bg-[#f5f9fb] rounded-xl p-4 text-sm space-y-2 border border-[#d6e2e6]">
                <div className="flex justify-between"><span className="text-[#516c79]">{t('detail.annualIncome')}</span><span className="font-mono text-[#004b65]">{cashflow.annual_income.toFixed(2)}</span></div>
                <div className="flex justify-between"><span className="text-[#516c79]">{t('detail.yieldOnCost')}</span><span className="font-mono">{cashflow.yield_on_cost.toFixed(2)}%</span></div>
              </div>
            )}
          </div>
        )}

        {tab === 'analytics' && (
          <div className="text-center py-8">
            <BarChart3 size={48} className="mx-auto mb-4 text-[#a4a7ae]" />
            <p className="text-[#516c79] mb-4">{t('detail.analyticsDesc')}</p>
            <button onClick={showAnalysis} className="bg-[#004b65] hover:bg-[#003545] text-white px-4 py-2 rounded-lg text-sm">{t('detail.loadAnalytics')}</button>
          </div>
        )}

        {tab === 'similar' && (
          <div>
            {similarBonds.length === 0 && !similarLoading && (
              <div className="text-center py-8">
                <Search size={48} className="mx-auto mb-4 text-[#a4a7ae]" />
                <p className="text-[#516c79] mb-4">{t('detail.similarPrompt')}</p>
                <button onClick={loadSimilar} className="bg-[#004b65] hover:bg-[#003545] text-white px-4 py-2 rounded-lg text-sm">{t('detail.loadSimilar')}</button>
              </div>
            )}
            {similarLoading && <LoadingSkeleton />}
            {similarBonds.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {similarBonds.map((b) => (
                  <button key={b.internal_id} onClick={() => onOpenBond?.(b.internal_id)} className="text-left bg-[#f8fafb] rounded-xl p-3 border border-[#d6e2e6] hover:border-[#004b65] transition-colors">
                    <p className="font-medium text-sm text-[#01121a] truncate">{b.name}</p>
                    <div className="flex flex-wrap gap-x-3 text-xs text-[#717680] mt-1">
                      <span>YTM: {b.yield_to_maturity?.toFixed(2)}%</span>
                      <span>{b.currency}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'news' && (
          <div>
            {newsLoading && <LoadingSkeleton />}
            {!newsLoading && news.length === 0 && (
              <div className="text-center py-8">
                <Newspaper size={48} className="mx-auto mb-4 text-[#a4a7ae]" />
                <p className="text-[#516c79] mb-2">{t('detail.newsEmpty')}</p>
                <button onClick={loadNews} className="text-sm text-[#004b65] hover:text-[#387387]">{t('detail.loadNews')}</button>
              </div>
            )}
            {!newsLoading && news.length > 0 && (
              <div className="space-y-3">
                {news.map((n) => (
                  <a
                    key={n.id ?? n.url}
                    href={n.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block bg-[#f8fafb] rounded-xl border border-[#d6e2e6] p-4 hover:border-[#004b65] transition-colors"
                  >
                    <p className="text-sm text-[#01121a] leading-snug">{n.title}</p>
                    <div className="flex items-center gap-2 mt-2 text-xs text-[#717680]">
                      <span>{n.published_at ? new Date(n.published_at.replace(' ', 'T')).toLocaleString() : ''}</span>
                      <ExternalLink size={12} className="text-[#004b65]" />
                    </div>
                  </a>
                ))}
              </div>
            )}
          </div>
        )}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-[#717680]">{label}</span>
      <span className="text-[#01121a] font-medium truncate">{value}</span>
    </div>
  );
}

function UpgradePrompt({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="mt-4 bg-amber-50 border border-amber-200 rounded-xl p-4 text-center">
      <p className="text-sm text-amber-700 mb-2">{t('detail.upgradePrompt')}</p>
      <button onClick={onSubscribe} className="bg-[#004b65] hover:bg-[#003545] text-white px-4 py-2 rounded-lg text-sm">{t('detail.upgradeCta')}</button>
    </div>
  );
}
