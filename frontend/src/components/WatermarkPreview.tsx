import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

interface WatermarkPreviewProps {
  children: React.ReactNode;
  height?: string;
}

export default function WatermarkPreview({ children, height = '200px' }: WatermarkPreviewProps) {
  const [showPreview, setShowPreview] = useState(false);

  return (
    <div className="relative overflow-hidden rounded-xl" style={{ height }}>
      <div className={`${showPreview ? '' : 'blur-sm select-none'} transition-all duration-200 h-full`}>
        {children}
      </div>

      {!showPreview && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="absolute inset-0 flex items-center justify-center overflow-hidden">
            <div className="text-gray-600/20 text-2xl font-bold rotate-[-30deg] whitespace-nowrap select-none pointer-events-none">
              AIGENIS BONDS — TEST MODE
            </div>
          </div>
        </div>
      )}

      <button
        onClick={() => setShowPreview(!showPreview)}
        className="absolute bottom-2 right-2 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-900/90 border border-gray-700 text-xs text-gray-300 hover:text-white transition-colors backdrop-blur-sm"
      >
        {showPreview ? <EyeOff size={14} /> : <Eye size={14} />}
        {showPreview ? 'Скрыть' : 'Показать preview'}
      </button>
    </div>
  );
}
