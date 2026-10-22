/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: { 950: '#070d1a', 900: '#0b1324', 850: '#0f1a30', 800: '#13203b', 700: '#1c2b4a', 600: '#2a3b5f', 500: '#3d5078' },
        accent: { DEFAULT: '#f97316', soft: '#fb923c', dim: '#9a3412' },
        sev: { low: '#22c55e', medium: '#f59e0b', high: '#ef4444', repaired: '#64748b' },
      },
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
    },
  },
  plugins: [],
}
