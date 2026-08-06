import { useState, useRef, useEffect } from 'react';
import { Send, Brain, Trash2 } from 'lucide-react';
import { api, ApiError } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatPage() {
  const { t } = useI18n();
  usePageMeta(t('meta.chat'));
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length === 0) {
      setMessages([{ role: 'assistant', content: t('chat.greeting') }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      const res = await api.chat.send(text);
      setMessages((prev) => [...prev, { role: 'assistant', content: res.reply }]);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) {
        setError(t('chat.errorPremium'));
      } else {
        setError(e instanceof Error ? e.message : t('chat.errorGeneric'));
      }
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([{ role: 'assistant', content: t('chat.cleared') }]);
    setError(null);
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('chat.title')}</h2>
        <p className="text-sm text-[#516c79] mt-1">{t('chat.subtitle')}</p>
      </div>

      <div className="bg-white border border-[#d6e2e6] rounded-xl shadow-sm w-full max-w-3xl h-[70vh] min-h-[420px] flex flex-col mx-auto">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#d6e2e6]">
          <div className="flex items-center gap-2">
            <Brain size={18} className="text-[#004b65]" />
            <h3 className="font-semibold text-sm text-[#01121a]">AI-ассистент</h3>
          </div>
          <button onClick={clearChat} className="text-[#a4a7ae] hover:text-[#01121a] p-1" title={t('chat.clear')}>
            <Trash2 size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 bg-[#f5f9fb]">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-[#004b65] text-white'
                  : 'bg-white text-[#01121a] border border-[#d6e2e6]'
              }`}>
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-white rounded-lg px-3 py-2 text-sm text-[#a4a7ae] animate-pulse border border-[#d6e2e6]">
                {t('chat.thinking')}
              </div>
            </div>
          )}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="px-4 py-3 border-t border-[#d6e2e6]">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
              placeholder={t('chat.placeholder')}
              disabled={loading}
              className="flex-1 bg-[#f8fafb] border border-[#d6e2e6] rounded-lg px-3 py-2 text-sm text-[#01121a] placeholder-[#a4a7ae] focus:outline-none focus:border-[#004b65]"
            />
            <button
              onClick={send}
              disabled={loading || !input.trim()}
              className="bg-[#004b65] hover:bg-[#003545] disabled:bg-[#d9e4e8] text-white px-3 py-2 rounded-lg transition-colors"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
