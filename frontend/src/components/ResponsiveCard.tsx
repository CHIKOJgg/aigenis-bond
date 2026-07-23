import { useState, useRef } from 'react';

interface ResponsiveCardProps {
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
  swipeLeft?: () => void;
  swipeRight?: () => void;
}

export default function ResponsiveCard({
  children,
  onClick,
  className = '',
  swipeLeft,
  swipeRight,
}: ResponsiveCardProps) {
  const [touchStart, setTouchStart] = useState<number | null>(null);
  const [touchDelta, setTouchDelta] = useState(0);
  const [isSwiping, setIsSwiping] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const handleTouchStart = (e: React.TouchEvent) => {
    setTouchStart(e.touches[0].clientX);
    setIsSwiping(false);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStart === null) return;
    const delta = e.touches[0].clientX - touchStart;
    if (Math.abs(delta) > 10) {
      setIsSwiping(true);
      setTouchDelta(delta);
    }
  };

  const handleTouchEnd = () => {
    if (isSwiping) {
      if (touchDelta < -80 && swipeLeft) {
        swipeLeft();
      } else if (touchDelta > 80 && swipeRight) {
        swipeRight();
      }
    }
    setTouchStart(null);
    setTouchDelta(0);
    setIsSwiping(false);
  };

  const handleClick = () => {
    if (!isSwiping && onClick) {
      onClick();
    }
  };

  return (
    <div
      ref={cardRef}
      onClick={handleClick}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      className={`rounded-xl bg-slate-800/60 border border-slate-600/30 transition-all active:scale-[0.98] ${
        onClick ? 'cursor-pointer hover:bg-slate-800/80' : ''
      } ${className}`}
      style={{
        transform: isSwiping ? `translateX(${touchDelta * 0.3}px)` : undefined,
      }}
    >
      {children}
    </div>
  );
}
