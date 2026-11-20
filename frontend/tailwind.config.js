/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 900: '#0a0f1e', 800: '#0d1526', 700: '#111c35', 600: '#162040' },
        green: { 950: '#051a0a', 900: '#0a2e14', 800: '#0f4020', 700: '#145228', 600: '#1a6632', 500: '#22c55e', 400: '#4ade80', 300: '#86efac' },
        lime: { 400: '#a3e635', 300: '#bef264', 200: '#d9f99d', 500: '#84cc16' },
        surface: { DEFAULT: '#111c35', card: '#162040', border: '#1e3a5f' }
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] }
    }
  },
  plugins: []
}
