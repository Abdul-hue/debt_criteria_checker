/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Merriweather"', 'Georgia', 'serif'],
      },
      colors: {
        'brand-navy': '#0F172A',
        'brand-slate': '#1E293B',
        'brand-gold': '#A87C1F',
        'brand-red': '#8B1538',
        'block-red': '#FEF2F2',
        'block-red-border': '#EF4444',
        'flag-amber': '#FFFBEB',
        'flag-amber-border': '#F59E0B',
        'pass-green': '#F0FDF4',
        'pass-green-border': '#22C55E',
        'info-blue': '#EFF6FF',
        'info-blue-border': '#3B82F6',
        blocked: {
          DEFAULT: '#dc2626',
          light: '#fef2f2',
          border: '#fca5a5',
        },
        flagged: {
          DEFAULT: '#f59e0b',
          light: '#fffbeb',
          border: '#fcd34d',
        },
        passed: {
          DEFAULT: '#16a34a',
          light: '#f0fdf4',
          border: '#86efac',
        },
        info: {
          DEFAULT: '#3b82f6',
          light: '#eff6ff',
          border: '#93c5fd',
        },
      },
    },
  },
  plugins: [],
}
