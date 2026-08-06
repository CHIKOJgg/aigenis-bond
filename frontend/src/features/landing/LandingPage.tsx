import { LandingHeader } from './sections/LandingHeader';
import { HeroSection } from './sections/HeroSection';
import { BestBondsWidget } from './sections/BestBondsWidget';
import { PainPointsSection } from './sections/PainPointsSection';
import { StatsSection } from './sections/StatsSection';
import { FeaturesSection } from './sections/FeaturesSection';
import { ComparisonSection } from './sections/ComparisonSection';
import { HowItWorksSection } from './sections/HowItWorksSection';
import { RoiSection } from './sections/RoiSection';
import { TestimonialsSection } from './sections/TestimonialsSection';
import { PricingSection } from './sections/PricingSection';
import { FaqSection } from './sections/FaqSection';
import { CtaSection } from './sections/CtaSection';
import { LandingFooter } from './sections/LandingFooter';
import { StickyMobileCta } from './sections/StickyMobileCta';

interface LandingPageProps {
  onLogin: () => void;
  onRegister: () => void;
  onTerms?: () => void;
  onPrivacy?: () => void;
}

export function LandingPage({ onLogin, onRegister, onTerms, onPrivacy }: LandingPageProps) {
  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-[#f5f9fb] text-[#01121a] pb-20 md:pb-0">
      <LandingHeader onLogin={onLogin} onRegister={onRegister} scrollTo={scrollTo} />

      {/* Hero — Problem → Solution */}
      <HeroSection onRegister={onRegister} scrollTo={scrollTo} />

      {/* Live Widget — Real data is the best proof */}
      <BestBondsWidget onOpen={onRegister} />

      {/* Pain Points — Why user needs this */}
      <PainPointsSection />

      {/* Stats Bar */}
      <StatsSection />

      {/* Features — Result-focused */}
      <FeaturesSection />

      {/* Comparison Table */}
      <ComparisonSection onRegister={onRegister} />

      {/* How It Works — Simple 3 steps */}
      <HowItWorksSection />

      {/* ROI / Value — Concrete numbers */}
      <RoiSection />

      {/* Testimonials */}
      <TestimonialsSection />

      {/* Pricing */}
      <PricingSection onRegister={onRegister} />

      {/* FAQ */}
      <FaqSection />

      {/* CTA */}
      <CtaSection onRegister={onRegister} />

      {/* Footer */}
      <LandingFooter onTerms={onTerms} onPrivacy={onPrivacy} scrollTo={scrollTo} />

      {/* Sticky mobile CTA bar */}
      <StickyMobileCta onRegister={onRegister} />
    </div>
  );
}
