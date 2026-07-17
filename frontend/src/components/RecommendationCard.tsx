import { useState } from 'react';
import { CheckCircle2, AlertTriangle, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import type { AnalyticsRecommendation, CompanyRecommendation } from '../lib/api';
import { DecisionBadge, CurrencyBadge } from './common';

interface Props {
  rec: AnalyticsRecommendation | CompanyRecommendation;
  title: string;
  subtitle?: string;
  currency?: string;
  rank?: number;
  onOpen?: () => void;
}

export function RecommendationCard({ rec, title, subtitle, currency, rank, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const hasDetails = (rec.reasons && rec.reasons.length > 0) || (rec.risks && rec.risks.length > 0);

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {rank != null && (
              <span className="text-xs font-bold text-gray-500 bg-gray-800 rounded px-1.5 py-0.5">#{rank}</span>
            )}
            <h3 className="font-semibold text-white truncate">{title}</h3>
            {currency && <CurrencyBadge currency={currency} />}
          </div>
          {subtitle && <p className="text-xs text-gray-500 mt-0.5 truncate">{subtitle}</p>}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <DecisionBadge decision={rec.decision} />
          {rec.confidence != null && (
            <span className="text-xs text-gray-400">уверенность {Math.round(rec.confidence * 100)}%</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
        {rec.score != null && <span>Score: <span className="text-white font-medium">{rec.score.toFixed(1)}</span></span>}
        {rec.predicted_return_pct != null && (
          <span>
            прогноз доходности:{' '}
            <span className={rec.predicted_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              {rec.predicted_return_pct >= 0 ? '+' : ''}{rec.predicted_return_pct.toFixed(2)}%
            </span>
          </span>
        )}
      </div>

      {hasDetails && (
        <>
          <button
            onClick={() => setOpen((o) => !o)}
            className="mt-3 flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {open ? 'Скрыть детали' : 'Почему такой вердикт?'}
          </button>

          {open && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="bg-emerald-950/30 border border-emerald-900 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-emerald-300 text-xs font-semibold mb-2">
                  <CheckCircle2 size={14} /> Почему стоит брать
                </div>
                {rec.reasons && rec.reasons.length > 0 ? (
                  <ul className="space-y-1.5 text-xs text-emerald-200/90 list-disc list-inside">
                    {rec.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-gray-500">Нет явных аргументов «за».</p>
                )}
              </div>
              <div className="bg-red-950/30 border border-red-900 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-red-300 text-xs font-semibold mb-2">
                  <AlertTriangle size={14} /> Риски и причины избегать
                </div>
                {rec.risks && rec.risks.length > 0 ? (
                  <ul className="space-y-1.5 text-xs text-red-200/90 list-disc list-inside">
                    {rec.risks.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-gray-500">Существенных рисков не выявлено.</p>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {onOpen && (
        <button
          onClick={onOpen}
          className="mt-3 flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors"
        >
          <ExternalLink size={14} /> Открыть детали
        </button>
      )}
    </div>
  );
}
