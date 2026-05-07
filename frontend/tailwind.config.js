/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          900: 'var(--bg-surface-900)',
          800: 'var(--bg-surface-800)',
          700: 'var(--bg-surface-700)',
          600: 'var(--bg-surface-600)',
          500: 'var(--bg-surface-500)',
        },
        accent: {
          500: 'var(--accent)',
          400: 'var(--accent-hover)',
          300: 'var(--accent-hover)',
        },
        success: '#22c55e',
        warning: '#f59e0b',
        danger:  '#ef4444',
        muted:   'var(--text-muted)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
