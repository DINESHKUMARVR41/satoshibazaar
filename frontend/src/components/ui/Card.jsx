export default function Card({ children, className = '', hover = false }) {
  return (
    <div
      className={`bg-[#111c35] border border-[#1e3a5f] rounded-xl p-4 ${
        hover ? 'transition-colors duration-200 hover:border-green-500 cursor-pointer' : ''
      } ${className}`}
    >
      {children}
    </div>
  );
}
