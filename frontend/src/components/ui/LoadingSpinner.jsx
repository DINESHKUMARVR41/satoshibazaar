import { Loader2 } from 'lucide-react';

export default function LoadingSpinner({ size = 8, className = '' }) {
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <Loader2 className={`w-${size} h-${size} animate-spin text-lime-400`} />
    </div>
  );
}
