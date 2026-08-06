import { User, Star, LogOut } from 'lucide-react';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useAuth } from '../lib/AuthContext';
import ReferralProgram from '../components/ReferralProgram';

export default function AccountPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  usePageMeta(t('meta.account'));
  const { user, logout } = useAuth();
  const isOnTrial = user?.trial_end && new Date(user.trial_end) > new Date();
  const trialDaysLeft = isOnTrial && user?.trial_end ? Math.ceil((new Date(user.trial_end).getTime() - Date.now()) / (1000 * 60 * 60 * 24)) : 0;

  const trialDaysWord = (n: number) => {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return 'день';
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return 'дня';
    return 'дней';
  };

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('settings.title')}</h2>
      <div className="bg-white rounded-xl border border-[#d6e2e6] p-6 max-w-lg">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><User size={16} className="text-[#004b65]" /> {t('settings.profile')}</h3>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between py-1.5 border-b border-[#d6e2e6]">
            <span className="text-[#516c79]">{t('settings.name')}</span>
            <span className="text-[#01121a] font-medium">{user?.name}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-[#d6e2e6]">
            <span className="text-[#516c79]">{t('settings.email')}</span>
            <span className="text-[#01121a] font-medium">{user?.email}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-[#d6e2e6]">
            <span className="text-[#516c79]">{t('settings.plan')}</span>
            <span className="text-[#004b65] font-medium capitalize">{user?.subscription_tier}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-[#d6e2e6]">
            <span className="text-[#516c79]">{t('settings.role')}</span>
            <span className="text-[#01121a] font-medium capitalize">{user?.role}</span>
          </div>
          {isOnTrial && (
            <div className="flex justify-between py-1.5 border-b border-[#d6e2e6]">
              <span className="text-[#516c79]">{t('settings.trial')}</span>
              <span className="text-[#004b65] font-medium">{t('trial.daysLeftShort', { days: trialDaysLeft, daysWord: trialDaysWord(trialDaysLeft) })}</span>
            </div>
          )}
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          {user?.subscription_tier === 'free' && (
            <button onClick={onSubscribe}
              className="flex items-center gap-2 bg-[#004b65] hover:bg-[#387387] text-white px-4 py-2 rounded-lg text-sm transition-colors">
              <Star size={16} /> {t('settings.subscribe')}
            </button>
          )}
          <button onClick={logout}
            className="flex items-center gap-2 bg-[#e03400] hover:bg-[#c02e00] text-white px-4 py-2 rounded-lg text-sm transition-colors">
            <LogOut size={16} /> {t('settings.signOut')}
          </button>
        </div>
      </div>
      <ReferralProgram />
    </div>
  );
}
