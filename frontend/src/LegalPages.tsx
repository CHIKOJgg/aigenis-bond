import { TrendingUp, X } from 'lucide-react';
import { useI18n } from './i18n';

type LegalPage = 'terms' | 'privacy';

export function LegalPages({ page, onBack }: { page: LegalPage; onBack: () => void }) {
  const { t } = useI18n();
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 bg-gray-900 sticky top-0 z-40">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-bold flex items-center gap-2">
            <TrendingUp className="text-emerald-400" size={22} />
            <span>Aigenis Bonds</span>
          </h1>
          <button onClick={onBack}
            className="text-gray-400 hover:text-white px-3 py-2 rounded-lg text-sm bg-gray-800 hover:bg-gray-700 transition-colors flex items-center gap-1.5">
            <X size={14} /> {t('legal.back')}
          </button>
        </div>
      </header>
      <main className="max-w-4xl mx-auto p-4 sm:p-8">
        {page === 'terms' && <TermsContent />}
        {page === 'privacy' && <PrivacyContent />}
      </main>
      <footer className="border-t border-gray-800 bg-gray-900 mt-8">
        <div className="max-w-4xl mx-auto px-4 py-4 text-center text-xs text-gray-500">
          &copy; {new Date().getFullYear()} Aigenis Parser. All rights reserved.
        </div>
      </footer>
    </div>
  );
}

function TermsContent() {
  const { t } = useI18n();
  return (
    <div className="max-w-none">
      <h1 className="text-3xl font-bold mb-6">{t('legal.termsTitle')}</h1>
      <p className="text-sm text-gray-400 mb-8">{t('legal.updated')}</p>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h1')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t1')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h2')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t2')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h3')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t3a')}</p>
        <p className="text-gray-300 mb-2">{t('legal.t3b')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h4')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t4_1')}</p>
        <p className="text-gray-300 mb-2">{t('legal.t4_2')}</p>
        <p className="text-gray-300 mb-2">{t('legal.t4_3')}</p>
        <p className="text-gray-300 mb-2">{t('legal.t4_4')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h5')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t5intro')}</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>{t('legal.t5a')}</li>
          <li>{t('legal.t5b')}</li>
          <li>{t('legal.t5c')}</li>
          <li>{t('legal.t5d')}</li>
          <li>{t('legal.t5e')}</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h6')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t6')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h7')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t7')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h8')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t8')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.h9')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.t9')}</p>
      </section>
    </div>
  );
}

function PrivacyContent() {
  const { t } = useI18n();
  return (
    <div className="max-w-none">
      <h1 className="text-3xl font-bold mb-6">{t('legal.privacyTitle')}</h1>
      <p className="text-sm text-gray-400 mb-8">{t('legal.updated')}</p>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p1')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p1intro')}</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>{t('legal.p1a')}</li>
          <li>{t('legal.p1b')}</li>
          <li>{t('legal.p1c')}</li>
          <li>{t('legal.p1d')}</li>
          <li>{t('legal.p1e')}</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p2')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p2intro')}</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>{t('legal.p2a')}</li>
          <li>{t('legal.p2b')}</li>
          <li>{t('legal.p2c')}</li>
          <li>{t('legal.p2d')}</li>
          <li>{t('legal.p2e')}</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p3')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p3intro')}</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>{t('legal.p3a')}</li>
          <li>{t('legal.p3b')}</li>
          <li>{t('legal.p3c')}</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p4')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p4text')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p5')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p5intro')}</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>{t('legal.p5a')}</li>
          <li>{t('legal.p5b')}</li>
          <li>{t('legal.p5c')}</li>
          <li>{t('legal.p5d')}</li>
          <li>{t('legal.p5e')}</li>
        </ul>
        <p className="text-gray-300 mt-2">{t('legal.p5contact')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p6')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p6text')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p7')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p7text')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p8')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p8intro')}</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>{t('legal.p8a')}</li>
          <li>{t('legal.p8b')}</li>
          <li>{t('legal.p8c')}</li>
        </ul>
        <p className="text-gray-300 mt-2">{t('legal.p8text')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p9')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p9text')}</p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">{t('legal.p10')}</h2>
        <p className="text-gray-300 mb-2">{t('legal.p10text')}</p>
      </section>
    </div>
  );
}
