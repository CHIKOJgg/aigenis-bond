import { useState } from 'react';
import { X, Send, Building2, Check } from 'lucide-react';
import { Modal } from '../lib/Modal';

interface EnterpriseFormProps {
  open: boolean;
  onClose: () => void;
}

export default function EnterpriseForm({ open, onClose }: EnterpriseFormProps) {
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [needs, setNeeds] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    // Simulate sending
    await new Promise((r) => setTimeout(r, 1000));
    setSent(true);
    setBusy(false);
  };

  if (sent) {
    return (
      <Modal onClose={onClose} className="max-w-md w-full">
        <div className="p-8 text-center">
          <div className="w-14 h-14 bg-emerald-600/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <Check size={28} className="text-emerald-400" />
          </div>
          <h3 className="text-lg font-bold mb-2">Заявка отправлена!</h3>
          <p className="text-sm text-gray-400 mb-6">Мы свяжемся с вами в ближайшее время</p>
          <button onClick={onClose} className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2 rounded-lg text-sm">
            Закрыть
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal onClose={onClose} className="max-w-md w-full">
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-emerald-600/20 rounded-xl flex items-center justify-center">
              <Building2 size={20} className="text-emerald-400" />
            </div>
            <div>
              <h3 className="text-lg font-bold">Enterprise</h3>
              <p className="text-sm text-gray-400">Индивидуальное решение для бизнеса</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white p-1"><X size={18} /></button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Email *</label>
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm"
              placeholder="you@company.com"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Компания *</label>
            <input
              required
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm"
              placeholder="ООО «Ваша компания»"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Потребности</label>
            <textarea
              value={needs}
              onChange={(e) => setNeeds(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm resize-none"
              rows={3}
              placeholder="Какие функции нужны? Сколько пользователей?"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white py-3 rounded-xl text-sm font-medium flex items-center justify-center gap-2"
          >
            <Send size={16} /> {busy ? 'Отправка...' : 'Отправить заявку'}
          </button>
        </form>

        <div className="mt-6 space-y-2">
          <p className="text-xs text-gray-500 font-medium mb-2">Для бизнеса:</p>
          {['White-label решение под ваш бренд', 'API-доступ с расширенными лимитами', 'Выделенный менеджер и поддержка'].map((item) => (
            <div key={item} className="flex items-center gap-2 text-xs text-gray-400">
              <Check size={12} className="text-emerald-400 shrink-0" /> {item}
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
}
