import { useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { api } from '../lib/api';
import { useI18n, LanguageToggle } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useAuth } from '../lib/AuthContext';
import { GoogleSignInButton } from '../components/GoogleSignInButton';

function AuthShell({ children, onSwitch, footerText, linkText }: { children: React.ReactNode; onSwitch: () => void; footerText: string; linkText: string }) {
  const { t } = useI18n();
  return (
    <div className="min-h-screen bg-[#f5f9fb] text-[#01121a] flex items-center justify-center p-4">
      <div className="absolute top-3 right-3">
        <LanguageToggle />
      </div>
      <div className="bg-white rounded-xl border border-[#d6e2e6] p-8 w-full max-w-md">
        <div className="flex items-center gap-2 mb-6">
          <TrendingUp className="text-[#004b65]" size={24} />
          <h1 className="text-xl font-bold font-[Montserrat,sans-serif]">Aigenis Bonds</h1>
        </div>
        {children}
        <div className="flex items-center gap-3 my-4">
          <div className="flex-1 h-px bg-[#f8fafb]" />
          <span className="text-xs text-[#717680]">{t('auth.or') || 'или'}</span>
          <div className="flex-1 h-px bg-[#f8fafb]" />
        </div>
        <GoogleSignInButton />
        <p className="text-sm text-[#516c79] mt-4 text-center">
          {footerText}{' '}
          <button onClick={onSwitch} className="text-[#004b65] hover:underline">{linkText}</button>
        </p>
      </div>
    </div>
  );
}

export function LoginPage({ onRegister }: { onRegister: () => void }) {
  const { t } = useI18n();
  usePageMeta(t('meta.login'));
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [resetSent, setResetSent] = useState(false);
  const [resetting, setResetting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message === 'Failed to fetch' ? t('auth.fetchError') : err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = async () => {
    setError('');
    setResetting(true);
    try {
      if (!email.trim()) {
        setError(t('auth.enterEmail') || 'Введите email, чтобы восстановить пароль');
        return;
      }
      await api.auth.forgotPassword(email.trim());
      setResetSent(true);
      setTimeout(() => setResetSent(false), 8000);
    } catch (err: any) {
      setError(err.message === 'Failed to fetch' ? t('auth.fetchError') : err.message);
    } finally {
      setResetting(false);
    }
  };

  return (
    <AuthShell onSwitch={onRegister} footerText={t('auth.noAccount')} linkText={t('auth.signUp')}>
      <h2 className="text-lg font-semibold mb-4">{t('auth.signInTitle')}</h2>
      {error && <div className="bg-[#fff1ee] border border-[#e03400] rounded-lg p-3 mb-4 text-sm text-[#e03400]">{error}</div>}
      {resetSent && <div className="bg-[#ebfff2] border border-[#06b663] rounded-lg p-3 mb-4 text-sm text-[#06b663]">Если аккаунт существует, ссылка для сброса пароля отправлена на email</div>}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="text-sm text-[#516c79] block mb-1">{t('auth.email')}</label>
          <input value={email} onChange={e => setEmail(e.target.value)} type="email" required
            className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
        </div>
        <div>
          <label className="text-sm text-[#516c79] block mb-1">{t('auth.password')}</label>
          <input value={password} onChange={e => setPassword(e.target.value)} type="password" required
            className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
        </div>
        <button type="submit" disabled={submitting}
          className="w-full bg-[#004b65] hover:bg-[#387387] disabled:bg-[#d9e4e8] text-white py-2 rounded-lg text-sm font-medium transition-colors">
          {submitting ? t('auth.signingIn') : t('auth.signIn')}
        </button>
        <div className="text-center">
          <button type="button" onClick={handleReset} disabled={resetting} className="text-sm text-[#717680] hover:text-[#004b65] disabled:opacity-50 transition-colors">
            {resetting ? 'Отправка...' : 'Забыли пароль?'}
          </button>
        </div>
      </form>
    </AuthShell>
  );
}

export function RegisterPage({ onSwitch, defaultRefCode }: { onSwitch: () => void; defaultRefCode?: string | null }) {
  const { t } = useI18n();
  usePageMeta(t('meta.register'));
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [refCode, setRefCode] = useState(defaultRefCode ?? '');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    // Match backend rules: min 8 chars + uppercase + digit.
    if (password.length < 8) { setError(t('auth.pwMin')); return; }
    if (!/[A-ZА-Я]/.test(password)) { setError(t('auth.pwUpper')); return; }
    if (!/\d/.test(password)) { setError(t('auth.pwDigit')); return; }
    setSubmitting(true);
    try {
      await register(email, password, name, refCode.trim() || null);
    } catch (err: any) {
      setError(err.message === 'Failed to fetch' ? t('auth.fetchError') : err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell onSwitch={onSwitch} footerText={t('auth.hasAccount')} linkText={t('auth.signIn')}>
      <h2 className="text-lg font-semibold mb-4">{t('auth.createAccount')}</h2>
      {error && <div className="bg-[#fff1ee] border border-[#e03400] rounded-lg p-3 mb-4 text-sm text-[#e03400]">{error}</div>}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="text-sm text-[#516c79] block mb-1">{t('auth.name')}</label>
          <input value={name} onChange={e => setName(e.target.value)} required
            className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
        </div>
        <div>
          <label className="text-sm text-[#516c79] block mb-1">{t('auth.email')}</label>
          <input value={email} onChange={e => setEmail(e.target.value)} type="email" required
            className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
        </div>
        <div>
          <label className="text-sm text-[#516c79] block mb-1">{t('auth.password')}</label>
          <input value={password} onChange={e => setPassword(e.target.value)} type="password" required minLength={8}
            className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
        </div>
        <div>
          <label className="text-sm text-[#516c79] block mb-1">{t('auth.referralCode') || 'Реферальный код (необязательно)'}</label>
          <input value={refCode} onChange={e => setRefCode(e.target.value)} placeholder="ref_..."
            className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
        </div>
        <button type="submit" disabled={submitting}
          className="w-full bg-[#004b65] hover:bg-[#387387] disabled:bg-[#d9e4e8] text-white py-2 rounded-lg text-sm font-medium transition-colors">
          {submitting ? t('auth.creating') : t('auth.createAccount')}
        </button>
      </form>
    </AuthShell>
  );
}
