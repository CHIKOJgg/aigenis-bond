import { ArrowRight, Check, X } from 'lucide-react';
import { useI18n } from '../../../i18n';

export function ComparisonSection({ onRegister }: { onRegister: () => void }) {
  const { t } = useI18n();

  return (
    <section className="max-w-5xl mx-auto px-4 py-20">
      <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">{t('compare.title')}</h2>
      <p className="text-[#516c79] text-center mb-12 max-w-2xl mx-auto">{t('compare.sub')}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#d6e2e6]">
              <th className="p-3 md:p-4 text-left text-[#516c79] font-medium">{t('compare.col1')}</th>
              <th className="p-3 md:p-4 text-center text-[#004b65] font-semibold">{t('compare.col2')}</th>
              <th className="p-3 md:p-4 text-center text-[#717680] font-medium">{t('compare.col3')}</th>
            </tr>
          </thead>
          <tbody>
            {[
              { label: t('compare.feature1'), yes: true, other: true },
              { label: t('compare.feature2'), yes: true, other: false },
              { label: t('compare.feature3'), yes: true, other: false },
              { label: t('compare.feature4'), yes: true, other: false },
              { label: t('compare.feature5'), yes: true, other: true },
            ].map((r) => (
              <tr key={r.label} className="border-b border-[#d6e2e6]/60 hover:bg-[#eef3f5]/60 transition-colors">
                <td className="p-3 md:p-4 text-[#01121a]">{r.label}</td>
                <td className="p-3 md:p-4 text-center"><Check className="inline text-[#004b65]" size={18} /></td>
                <td className="p-3 md:p-4 text-center">
                  {r.other ? <Check className="inline text-[#a4a7ae]" size={18} /> : <X className="inline text-[#a4a7ae]" size={18} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-center mt-10">
        <button onClick={onRegister} className="inline-flex items-center gap-2 bg-[#004b65] hover:bg-[#387387] text-white px-6 py-3 rounded-xl text-sm font-medium transition-colors">
          {t('cta.seeResults')} <ArrowRight size={16} />
        </button>
      </div>
    </section>
  );
}
