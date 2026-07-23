import { useEffect } from 'react';
import { X } from 'lucide-react';

interface MobileBottomSheetProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  maxHeight?: string;
}

export default function MobileBottomSheet({
  isOpen,
  onClose,
  title,
  children,
  maxHeight = '70vh',
}: MobileBottomSheetProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm md:hidden"
        onClick={onClose}
      />
      <div
        className="fixed bottom-0 left-0 right-0 z-[61] md:hidden bg-gray-900 rounded-t-2xl animate-slideUp"
        style={{ maxHeight }}
      >
        <div className="sticky top-0 bg-gray-900 px-4 pt-4 pb-2 border-b border-gray-800">
          <div className="flex items-center justify-between">
            {title && <h3 className="text-sm font-semibold text-white">{title}</h3>}
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors ml-auto"
            >
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="overflow-y-auto" style={{ maxHeight: `calc(${maxHeight} - 60px)` }}>
          {children}
        </div>
      </div>
    </>
  );
}
