import { ResponsiveContainer } from 'recharts';

interface ResponsiveChartProps {
  children: React.ReactNode;
  height?: number;
  minHeight?: number;
  className?: string;
}

export default function ResponsiveChart({
  children,
  height = 300,
  minHeight = 200,
  className = '',
}: ResponsiveChartProps) {
  return (
    <div className={`w-full ${className}`}>
      <div
        style={{ minHeight: `${minHeight}px` }}
        className="w-full"
      >
        <ResponsiveContainer width="100%" height={height}>
          {children as React.ReactElement}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
