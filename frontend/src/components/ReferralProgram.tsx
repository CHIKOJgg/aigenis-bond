import { useState } from 'react';
import { Gift, Copy, Check, Share2 } from 'lucide-react';
import { api } from '../lib/api';

interface ReferralStats {
  referral_code: string | null;
  total_referrals: number;
  conversions: number;
  pending_payouts: number;
  paid_payouts: number;
  total_commission: number;
}

export default function ReferralProgram() {
  const [referralCode, setReferralCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [noCode, setNoCode] = useState(false);
  const [stats, setStats] = useState<{ referrals: number; rewards: number } | null>(null);

  async function loadReferral() {
    setLoading(true);
    try {
      const data = await api.request<ReferralStats>('/api/v1/partner/referrals');
      setReferralCode(data.referral_code);
      setNoCode(!data.referral_code);
      setStats({ referrals: data.total_referrals, rewards: data.total_commission });
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
    <div className="rounded-xl bg-white border border-[#d6e2e6] p-5 space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#fce7f3] to-[#ede9fe] flex items-center justify-center">
          <Gift size={20} className="text-[#be185d]" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-[#01121a]">Пригласи друга</h3>
          <p className="text-xs text-[#516c79]">Получи комиссию с подписок за каждого приглашённого</p>
        </div>
      </div>

      {!referralCode && !loading && !noCode && (
        <button
          onClick={loadReferral}
          className="w-full py-2.5 rounded-lg bg-[#fce7f3] border border-[#f9a8d4] text-[#be185d] text-sm font-medium hover:bg-[#fbcfe8] transition-colors"
        >
          Получить реферальный код
        </button>
      )}

      {noCode && !loading && (
        <p className="text-xs text-[#516c79] leading-relaxed">
          Реферальная программа привязана к Partner-ключу. Создайте ключ в разделе
          «Для бизнеса» (доступно в Pro/Enterprise), и реферальный код появится здесь.
        </p>
      )}

      {loading && (
        <div className="text-[#516c79] text-xs text-center py-2">Загрузка...</div>
      )}

      {referralCode && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 bg-[#f5f9fb] rounded-lg px-3 py-2">
            <code className="flex-1 text-sm text-[#01121a] font-mono">{referralCode}</code>
            <button
              onClick={copyCode}
              className="p-1.5 text-[#516c79] hover:text-[#004b65] rounded-md hover:bg-[#eef3f5] transition-colors"
            >
              {copied ? <Check size={14} className="text-[#008f5e]" /> : <Copy size={14} />}
            </button>
          </div>

          {stats && (
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-[#f5f9fb] rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-[#01121a]">{stats.referrals}</div>
                <div className="text-[10px] text-[#717680]">Приглашено</div>
              </div>
              <div className="bg-[#f5f9fb] rounded-lg p-2 text-center">
                <div className="text-lg font-bold text-[#008f5e]">+{stats.rewards.toFixed(2)}</div>
                <div className="text-[10px] text-[#717680]">Комиссия BYN</div>
              </div>
            </div>
          )}

          <button
            onClick={share}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-[#004b65] hover:bg-[#387387] text-white text-sm font-medium transition-colors"
          >
            <Share2 size={14} />
            Поделиться ссылкой
          </button>
        </div>
      )}
    </div>
  );
}
