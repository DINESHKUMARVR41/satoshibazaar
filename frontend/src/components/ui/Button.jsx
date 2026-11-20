import { Loader2 } from 'lucide-react';

const variants = {
  primary: 'bg-lime-400 text-[#0a0f1e] hover:bg-lime-300',
  secondary: 'bg-transparent border border-[#1e3a5f] text-slate-300 hover:border-slate-400',
  danger: 'bg-red-700 text-white hover:bg-red-600',
  ghost: 'bg-transparent text-slate-400 hover:text-slate-100',
};

const sizes = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
};

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  className = '',
  onClick,
  type = 'button',
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-all duration-150
        ${variants[variant]} ${sizes[size]}
        ${disabled || loading ? 'opacity-50 cursor-not-allowed' : ''}
        ${className}`}
    >
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  );
}
