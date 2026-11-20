export default function Badge({ children, variant = 'info' }) {
  const variants = {
    demo: 'bg-lime-400 text-[#0a0f1e]',
    success: 'bg-green-900 text-green-400',
    warning: 'bg-yellow-900 text-yellow-400',
    error: 'bg-red-900 text-red-400',
    info: 'bg-blue-900 text-blue-400',
    pending: 'bg-orange-900 text-orange-400',
    lightning: 'bg-blue-900 text-blue-300',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${variants[variant] || variants.info}`}>
      {children}
    </span>
  );
}
