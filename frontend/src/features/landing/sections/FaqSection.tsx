import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useI18n } from '../../../i18n';

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-5 text-left hover:bg-[#f5f9fb] transition-colors"
      >
        <span className="text-sm font-medium text-[#01121a] pr-4">{question}</span>
        <ChevronDown
          size={18}
          className={`text-[#516c79] shrink-0 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="px-5 pb-5 text-sm text-[#516c79] leading-relaxed animate-fadeIn">
          {answer}
        </div>
      )}
    </div>
  );
}

export function FaqSection() {
  const { t } = useI18n();

  return (
    <section id="faq" className="bg-white border-y border-[#d6e2e6]">
      <div className="max-w-3xl mx-auto px-4 py-20">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-12">{t('faq.title')}</h2>
        <div className="space-y-4">
          <FaqItem question={t('faq.q1')} answer={t('faq.a1')} />
          <FaqItem question={t('faq.q2')} answer={t('faq.a2')} />
          <FaqItem question={t('faq.q3')} answer={t('faq.a3')} />
          <FaqItem question={t('faq.q4')} answer={t('faq.a4')} />
        </div>
      </div>
    </section>
  );
}
