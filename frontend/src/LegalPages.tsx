import { TrendingUp, X } from 'lucide-react';

type LegalPage = 'terms' | 'privacy';

export function LegalPages({ page, onBack }: { page: LegalPage; onBack: () => void }) {
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
            <X size={14} /> Back to App
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
  return (
    <div className="max-w-none">
      <h1 className="text-3xl font-bold mb-6">Terms of Service</h1>
      <p className="text-sm text-gray-400 mb-8">Last updated: July 2026</p>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">1. Acceptance of Terms</h2>
        <p className="text-gray-300 mb-2">
          By accessing or using the Aigenis Bonds platform ("Service"), you agree to be bound by
          these Terms of Service. If you do not agree, do not use the Service.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">2. Description of Service</h2>
        <p className="text-gray-300 mb-2">
          Aigenis Bonds provides bond market data, analytics, scoring, portfolio optimization,
          and fixed income desk tools for informational purposes. The Service scrapes data from
          public sources and applies analytical models.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">3. Not Financial Advice</h2>
        <p className="text-gray-300 mb-2">
          All content, analytics, scores, recommendations, and data provided by the Service are
          for informational and educational purposes only. They do not constitute financial advice,
          investment advice, or a recommendation to buy or sell any security.
        </p>
        <p className="text-gray-300 mb-2">
          You are solely responsible for your investment decisions. Past performance is not
          indicative of future results.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">4. Subscriptions and Payments</h2>
        <p className="text-gray-300 mb-2">4.1. The Service offers free and paid subscription tiers (Pro, Enterprise).</p>
        <p className="text-gray-300 mb-2">
          4.2. Payments are processed through Telegram Stars or other designated payment providers.
          All payments are final except as required by applicable law.
        </p>
        <p className="text-gray-300 mb-2">
          4.3. Subscriptions are for a fixed duration as specified at the time of purchase.
          Auto-renewal is not supported; users must manually renew.
        </p>
        <p className="text-gray-300 mb-2">
          4.4. Refunds for Telegram Stars are handled through Telegram's refund system.
          For other payment methods, contact support@aigenis.by.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">5. User Responsibilities</h2>
        <p className="text-gray-300 mb-2">You agree not to:</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>Use the Service for any illegal purpose</li>
          <li>Attempt to bypass subscription gating or access restrictions</li>
          <li>Scrape, crawl, or extract data from the Service programmatically without authorization</li>
          <li>Share your account credentials with others</li>
          <li>Use the Service in a way that exceeds reasonable rate limits</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">6. Limitation of Liability</h2>
        <p className="text-gray-300 mb-2">
          To the maximum extent permitted by law, Aigenis Parser shall not be liable for any
          indirect, incidental, special, consequential, or punitive damages arising from your
          use of the Service.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">7. Termination</h2>
        <p className="text-gray-300 mb-2">
          We reserve the right to suspend or terminate your access to the Service at any time
          for violation of these terms.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">8. Changes to Terms</h2>
        <p className="text-gray-300 mb-2">
          We may modify these terms at any time. Continued use of the Service after changes
          constitutes acceptance of the new terms.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">9. Contact</h2>
        <p className="text-gray-300 mb-2">
          For questions about these terms, contact: support@aigenis.by
        </p>
      </section>
    </div>
  );
}

function PrivacyContent() {
  return (
    <div className="max-w-none">
      <h1 className="text-3xl font-bold mb-6">Privacy Policy</h1>
      <p className="text-sm text-gray-400 mb-8">Last updated: July 2026</p>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">1. Information We Collect</h2>
        <p className="text-gray-300 mb-2">We collect the following information:</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li><strong>Account data:</strong> email address, name, Telegram ID (if using bot)</li>
          <li><strong>Subscription data:</strong> tier, payment charge IDs, subscription dates</li>
          <li><strong>Portfolio data:</strong> bonds you track, portfolio allocations, preferences</li>
          <li><strong>Usage data:</strong> API requests, pages visited, features used</li>
          <li><strong>Technical data:</strong> IP address, browser type, device information</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">2. How We Use Your Data</h2>
        <p className="text-gray-300 mb-2">We use your data to:</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>Provide and maintain the Service</li>
          <li>Process subscriptions and payments</li>
          <li>Send service-related communications</li>
          <li>Improve and analyze usage of the Service</li>
          <li>Detect and prevent abuse or unauthorized access</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">3. Data Sharing</h2>
        <p className="text-gray-300 mb-2">
          We do not sell your personal data. We may share data with:
        </p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>Payment processors (Telegram, Stripe) for subscription processing</li>
          <li>Cloud infrastructure providers for hosting</li>
          <li>Legal authorities if required by law</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">4. Data Retention</h2>
        <p className="text-gray-300 mb-2">
          We retain your data for as long as your account is active. After account deletion,
          data is deleted within 30 days. Aggregated, anonymized data may be retained for
          analytics purposes.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">5. Your Rights</h2>
        <p className="text-gray-300 mb-2">You have the right to:</p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>Access your personal data</li>
          <li>Correct inaccurate data</li>
          <li>Delete your account and associated data</li>
          <li>Export your data in machine-readable format</li>
          <li>Withdraw consent for data processing</li>
        </ul>
        <p className="text-gray-300 mt-2">
          To exercise these rights, contact: support@aigenis.by
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">6. Data Security</h2>
        <p className="text-gray-300 mb-2">
          We implement appropriate technical and organizational measures to protect your data,
          including encryption at rest and in transit, access controls, and regular security audits.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">7. Cookies</h2>
        <p className="text-gray-300 mb-2">
          The Service uses essential cookies for authentication and session management. We do not
          use tracking cookies or third-party advertising cookies. You can disable cookies in your
          browser settings, but this may affect Service functionality.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">8. Third-Party Services</h2>
        <p className="text-gray-300 mb-2">
          The Service integrates with:
        </p>
        <ul className="list-disc pl-6 text-gray-300 space-y-1 mb-2">
          <li>Telegram (messaging bot and Stars payments)</li>
          <li>Stripe (optional credit card payments)</li>
          <li>Sentry (error tracking, optional)</li>
        </ul>
        <p className="text-gray-300 mt-2">
          These services have their own privacy policies governing data handling.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">9. International Data Transfers</h2>
        <p className="text-gray-300 mb-2">
          Your data may be processed in any country where we or our service providers operate.
          We ensure appropriate safeguards are in place for international data transfers.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">10. Contact</h2>
        <p className="text-gray-300 mb-2">
          For privacy inquiries: support@aigenis.by
        </p>
      </section>
    </div>
  );
}
