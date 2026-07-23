import { useState, useRef, useEffect } from 'react';
import { X, Send, Brain, Trash2 } from 'lucide-react';
import { api, ApiError } from '../lib/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  bondId?: string;
}

export default function AIChatModal({ isOpen, onClose, bondId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen && messages.length === 0) {
      setMessages([{
        role: 'assistant',
        content: bondId
          ? `Здравствуйте! Я AI-ассистент по облигациям. Задайте вопрос по облигации ${bondId}.`
          : 'Здравствуйте! Я AI-ассистент по облигациям. Спросите меня о любой облигации, рейтинге, рекомендациях.',
      }]);
    }
  }, [isOpen, bondId, messages.length]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setLoading(true);
    setError(null);

    try {
      const res = await api.chat.send(text, bondId ? { internal_id: bondId } : undefined);
      setMessages((prev) => [...prev, { role: 'assistant', content: res.reply }]);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) {
        setError('AI-ассистент доступен в подписке Pro/Enterprise.');
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось получить ответ.');
      }
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([{
      role: 'assistant',
      content: 'Диалог очищен. Задайте новый вопрос.',
    }]);
    setError(null);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-[420px] h-[520px] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <Brain size={18} className="text-emerald-400" />
            <h3 className="font-semibold text-sm">AI-ассистент</h3>
            {bondId && <span className="text-xs text-gray-500 font-mono">{bondId}</span>}
          </div>
          <div className="flex items-center gap-1">
            <button onClick={clearChat} className="text-gray-400 hover:text-white p-1" title="Очистить">
              <Trash2 size={14} />
            </button>
            <button onClick={onClose} className="text-gray-400 hover:text-white p-1" title="Закрыть">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-emerald-600/30 text-emerald-100'
                  : 'bg-gray-800 text-gray-200'
              }`}>
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-800 rounded-lg px-3 py-2 text-sm text-gray-400 animate-pulse">
                Думаю…
              </div>
            </div>
          )}
          {error && (
            <div className="bg-red-900/30 border border-red-800 rounded-lg px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="px-4 py-3 border-t border-gray-700">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
              placeholder="Задайте вопрос об облигациях…"
              disabled={loading}
              className="flex-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
            />
            <button
              onClick={send}
              disabled={loading || !input.trim()}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white px-3 py-2 rounded-lg transition-colors"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
