import { useState, useEffect } from 'react';
import { Upload, FileText, AlertTriangle } from 'lucide-react';
import { api, ApiError } from '../lib/api';

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
          <FileText size={22} className="text-emerald-400" />
          Документы
        </h2>
        <label className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm cursor-pointer transition-colors">
          <Upload size={16} />
          {uploading ? 'Загрузка…' : 'Загрузить проспект'}
          <input type="file" accept=".pdf" onChange={handleUpload} className="hidden" disabled={uploading} />
        </label>
      </div>

      {error && (
        <div className="flex items-center gap-3 bg-red-900/30 border border-red-800 rounded-xl p-4">
          <AlertTriangle size={20} className="text-red-400 shrink-0" />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1 space-y-2">
          {loading && <div className="animate-pulse bg-gray-800 rounded-xl h-20" />}
          {!loading && documents.length === 0 && (
            <p className="text-gray-500 text-sm text-center py-8">
              Загрузите PDF-проспект облигации для анализа
            </p>
          )}
          {documents.map((doc) => (
            <button
              key={doc.id}
              onClick={() => setSelected(doc)}
              className={`w-full text-left bg-gray-900 border rounded-xl p-3 transition-colors ${
                selected?.id === doc.id ? 'border-emerald-500' : 'border-gray-800 hover:border-gray-600'
              }`}
            >
              <div className="flex items-center gap-2">
                <FileText size={14} className="text-gray-400 shrink-0" />
                <span className="text-sm font-medium truncate">{doc.filename}</span>
              </div>
              <p className="text-xs text-gray-500 mt-1 line-clamp-2">{doc.summary}</p>
            </button>
          ))}
        </div>

        <div className="lg:col-span-2">
          {selected ? (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
              <h3 className="font-semibold">{selected.filename}</h3>
              <div>
                <h4 className="text-sm font-medium text-gray-300 mb-2">Резюме</h4>
                <p className="text-sm text-gray-400 whitespace-pre-wrap">{selected.summary}</p>
              </div>
              {Object.keys(selected.extracted).length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-300 mb-2">Извлечённые параметры</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(selected.extracted).map(([key, val]) => (
                      <div key={key} className="bg-gray-800/50 rounded-lg px-3 py-2">
                        <p className="text-xs text-gray-500">{key}</p>
                        <p className="text-sm text-white font-mono">{String(val)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {selected.risk_flags.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-300 mb-2">Риски</h4>
                  <div className="flex flex-wrap gap-2">
                    {selected.risk_flags.map((flag, i) => (
                      <span key={i} className="bg-red-900/30 border border-red-800 text-red-300 text-xs px-2 py-1 rounded">
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center text-gray-500 text-sm">
              Выберите документ для просмотра
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
