import { useState, useEffect } from 'react';
import { Upload, FileText, AlertTriangle } from 'lucide-react';
import { api, ApiError } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';

interface Document {
  id: number;
  filename: string;
  internal_id: string | null;
  summary: string;
  extracted: Record<string, unknown>;
  risk_flags: string[];
  created_at: string;
}

export default function DocumentAnalysisPage() {
  const { t } = useI18n();
  usePageMeta(t('meta.documents'));
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState<Document | null>(null);

  const loadDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await api.documents.list();
      setDocuments(docs);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) {
        setError('Анализ документов доступен в подписке Pro/Enterprise.');
      } else {
        setError(e instanceof Error ? e.message : 'Failed to load');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadDocuments(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const result = await api.documents.upload(file);
      setDocuments((prev) => [{ ...result, internal_id: null, created_at: new Date().toISOString() }, ...prev]);
      setSelected(result as unknown as Document);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) {
        setError('Анализ документов доступен в подписке Pro/Enterprise.');
      } else {
        setError(e instanceof Error ? e.message : 'Upload failed');
      }
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <FileText size={22} className="text-[#004b65]" />
          Документы
        </h2>
        <label className="flex items-center gap-2 bg-[#004b65] hover:bg-[#387387] disabled:bg-[#d6e2e6] text-white px-4 py-2 rounded-lg text-sm cursor-pointer transition-colors">
          <Upload size={16} />
          {uploading ? 'Загрузка…' : 'Загрузить проспект'}
          <input type="file" accept=".pdf" onChange={handleUpload} className="hidden" disabled={uploading} />
        </label>
      </div>

      {error && (
        <div className="flex items-center gap-3 bg-[#fef2f2] border border-[#fecaca] rounded-xl p-4">
          <AlertTriangle size={20} className="text-[#b91c1c] shrink-0" />
          <p className="text-sm text-[#b91c1c]">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1 space-y-2">
          {loading && <div className="animate-pulse bg-[#d6e2e6] rounded-xl h-20" />}
          {!loading && documents.length === 0 && (
            <p className="text-[#717680] text-sm text-center py-8">
              Загрузите PDF-проспект облигации для анализа
            </p>
          )}
          {documents.map((doc) => (
            <button
              key={doc.id}
              onClick={() => setSelected(doc)}
              className={`w-full text-left bg-white border rounded-xl p-3 transition-colors ${
                selected?.id === doc.id ? 'border-[#004b65]' : 'border-[#d6e2e6] hover:border-[#b2c9d1]'
              }`}
            >
              <div className="flex items-center gap-2">
                <FileText size={14} className="text-[#516c79] shrink-0" />
                <span className="text-sm font-medium truncate">{doc.filename}</span>
              </div>
              <p className="text-xs text-[#717680] mt-1 line-clamp-2">{doc.summary}</p>
            </button>
          ))}
        </div>

        <div className="lg:col-span-2">
          {selected ? (
            <div className="bg-white rounded-xl border border-[#d6e2e6] p-5 space-y-4">
              <h3 className="font-semibold">{selected.filename}</h3>
              <div>
                <h4 className="text-sm font-medium text-[#516c79] mb-2">Резюме</h4>
                <p className="text-sm text-[#516c79] whitespace-pre-wrap">{selected.summary}</p>
              </div>
              {Object.keys(selected.extracted).length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-[#516c79] mb-2">Извлечённые параметры</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(selected.extracted).map(([key, val]) => (
                      <div key={key} className="bg-[#f8fafb] rounded-lg px-3 py-2">
                        <p className="text-xs text-[#717680]">{key}</p>
                        <p className="text-sm text-[#01121a] font-mono">{String(val)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {selected.risk_flags.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-[#516c79] mb-2">Риски</h4>
                  <div className="flex flex-wrap gap-2">
                    {selected.risk_flags.map((flag, i) => (
                      <span key={i} className="bg-[#fef2f2] border border-[#fecaca] text-[#b91c1c] text-xs px-2 py-1 rounded">
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-[#d6e2e6] p-8 text-center text-[#717680] text-sm">
              Выберите документ для просмотра
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
