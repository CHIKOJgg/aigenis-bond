import { useState, useEffect } from 'react';
import { Plus, ArrowUpRight, ArrowDownRight, Trash2 } from 'lucide-react';
import { api } from '../lib/api';

interface Transaction {
  id: number;
  internal_id: string;
  side: 'buy' | 'sell';
  amount: number;
  price: number;
  currency: string;
  executed_at: string | null;
  note: string | null;
}

export default function TransactionLog() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    internal_id: '',
    side: 'buy' as 'buy' | 'sell',
    amount: '',
    price: '',
    currency: 'BYN',
    note: '',
  });

  useEffect(() => {
    loadTransactions();
  }, []);

  async function loadTransactions() {
    setLoading(true);
    try {
      const data = await api.request('/api/v1/transactions?limit=100');
      setTransactions(data);
    } catch {
      console.error('Failed to load transactions');
    }
    setLoading(false);
  }

  async function addTransaction() {
    if (!form.internal_id || !form.amount || !form.price) return;
    try {
      await api.request('/api/v1/transactions', {
        method: 'POST',
        body: JSON.stringify({
          internal_id: form.internal_id,
          side: form.side,
          amount: parseFloat(form.amount),
          price: parseFloat(form.price),
          currency: form.currency,
          note: form.note || undefined,
        }),
      });
      setForm({ internal_id: '', side: 'buy', amount: '', price: '', currency: 'BYN', note: '' });
      setShowAdd(false);
      loadTransactions();
    } catch {
      console.error('Failed to add transaction');
    }
  }

  async function deleteTransaction(id: number) {
    try {
      await api.request(`/api/v1/transactions/${id}`, { method: 'DELETE' });
      loadTransactions();
    } catch {
      console.error('Failed to delete transaction');
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Журнал транзакций</h2>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
        >
          <Plus size={14} />
          Добавить
        </button>
      </div>

      {showAdd && (
        <div className="rounded-xl bg-slate-800/80 border border-slate-600/50 p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input
              type="text"
              placeholder="Bond ID"
              value={form.internal_id}
              onChange={(e) => setForm({ ...form, internal_id: e.target.value })}
              className="rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-400"
            />
            <select
              value={form.side}
              onChange={(e) => setForm({ ...form, side: e.target.value as 'buy' | 'sell' })}
              className="rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white"
            >
              <option value="buy">Покупка</option>
              <option value="sell">Продажа</option>
            </select>
            <input
              type="number"
              placeholder="Сумма"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
              className="rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-400"
            />
            <input
              type="number"
              placeholder="Цена"
              value={form.price}
              onChange={(e) => setForm({ ...form, price: e.target.value })}
              className="rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-400"
            />
          </div>
          <input
            type="text"
            placeholder="Заметка (необязательно)"
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
            className="w-full rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white placeholder-slate-400"
          />
          <div className="flex gap-2">
            <button
              onClick={addTransaction}
              className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm font-medium transition-colors"
            >
              Сохранить
            </button>
            <button
              onClick={() => setShowAdd(false)}
              className="px-4 py-2 rounded-lg bg-slate-600 hover:bg-slate-500 text-white text-sm font-medium transition-colors"
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-slate-400 text-sm py-8 text-center">Загрузка...</div>
      ) : transactions.length === 0 ? (
        <div className="text-slate-400 text-sm py-8 text-center">Нет транзакций</div>
      ) : (
        <div className="space-y-2">
          {transactions.map((tx) => (
            <div
              key={tx.id}
              className="flex items-center justify-between rounded-xl bg-slate-800/60 border border-slate-600/30 px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    tx.side === 'buy' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                  }`}
                >
                  {tx.side === 'buy' ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
                </div>
                <div>
                  <div className="text-sm text-white font-medium">
                    {tx.side === 'buy' ? 'Покупка' : 'Продажа'} {tx.internal_id}
                  </div>
                  <div className="text-xs text-slate-400">
                    {tx.amount.toFixed(2)} × {tx.price.toFixed(2)} {tx.currency}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-sm text-white font-mono">
                  {(tx.amount * tx.price).toFixed(2)}
                </div>
                <div className="text-xs text-slate-500">
                  {tx.executed_at ? new Date(tx.executed_at).toLocaleDateString() : ''}
                </div>
                <button
                  onClick={() => deleteTransaction(tx.id)}
                  className="text-slate-500 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
