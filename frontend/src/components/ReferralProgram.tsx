import { useState } from 'react';
import { Gift, Copy, Check, Share2 } from 'lucide-react';
import { api } from '../lib/api';

export default function ReferralProgram() {
  const [referralCode, setReferralCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<{ referrals: number; rewards: number } | null>(null);

  async function loadReferral() {
    setLoading(true);
    try {
      const data = await api.request('/api/v1/referral/code');
      setReferralCode(data.code);
      setStats({ referrals: data.referral_count || 0, rewards: data.reward_days || 0 });
    } catch {
      console.error('Failed to load referral');
    }
    setLoading(false);
  }

  function copyCode() {
    if (!referralCode) return;
    navigator.clipboard.writeText(referralCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function share() {
    if (!referralCode) return;
    const url = `https://t.me/AigenisBondsBot?start=ref_${referralCode}`;
    const text = 'Присоединяйся к Aigenis Bonds — лучший аналитический инструмент для облигаций!';
    if (navigator.share) {
      navigator.share({ title: 'Aigenis Bonds', text, url });
    } else {
      window.open(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`, '_blank');
    }
  }

  return (
    <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-5 space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-pink-500/30 to-purple-500/30 flex items-center justify-center">
          <Gift size={20} className="text-pink-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">Пригласи друга</h3>
          <p className="text-xs text-slate-400">Получи 7 дней Pro за каждого приглашённого</p>
        </div>
      </div>

      {!referralCode && !loading && (
        <button
          onClick={loadReferral}
          className="w-full py-2.5 rounded-lg bg-pink-600/20 border border-pink-500/30 text-pink-300 text-sm font-medium hover:bg-pink-600/30 transition-colors"
        >
          Получить реферальный код
        </button>
      )}

      {loading && (
        <div className="text-slate-400 text-xs text-center py-2">Загрузка...</div>
      )}

      {referralCode && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 bg-slate-700/50 rounded-lg px-3 py-2">
            <code className="flex-1 text-sm text-white font-mono">{referralCode}</code>
            <button
              onClick={copyCode}
              className="p-1.5 text-slate-400 hover:text-white rounded-md hover:bg-slate-600/50 transition-colors"
            >
              {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
            </button>
          </div>

          {stats && (
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-slate-700/30 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-white">{stats.referrals}</div>
                <div className="text-[10px] text-slate-400">Приглашено</div>
              </div>
              <div className="bg-slate-700/30 rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-emerald-400">+{stats.rewards}</div>
                <div className="text-[10px] text-slate-400">Дней Pro</div>
              </div>
            </div>
          )}

          <button
            onClick={share}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
          >
            <Share2 size={14} />
            Поделиться ссылкой
          </button>
        </div>
      )}
    </div>
  );
}
