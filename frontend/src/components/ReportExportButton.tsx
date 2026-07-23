import { useState } from 'react';
import { Download, FileText } from 'lucide-react';
import { api } from '../lib/api';

export default function ReportExportButton() {
  const [exporting, setExporting] = useState(false);

  async function exportReport() {
    setExporting(true);
    try {
      await api.request('/api/v1/reports/portfolio');
    } catch {
      console.error('Failed to export report');
    }
    setExporting(false);
  }

  return (
    <button
      onClick={exportReport}
      disabled={exporting}
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-700/50 border border-slate-600/30 text-sm text-slate-300 hover:text-white hover:bg-slate-700 disabled:opacity-50 transition-colors"
    >
      {exporting ? (
        <FileText size={14} className="animate-pulse" />
      ) : (
        <Download size={14} />
      )}
      Экспорт отчёта
    </button>
  );
}
