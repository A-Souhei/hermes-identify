import type { Config } from 'tailwindcss'

const inkVar = (name: string) => `rgb(var(--${name}) / <alpha-value>)`

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: {
          50:  inkVar('ink-50'),
          100: inkVar('ink-100'),
          200: inkVar('ink-200'),
          300: inkVar('ink-300'),
          400: inkVar('ink-400'),
          500: inkVar('ink-500'),
          600: inkVar('ink-600'),
          700: inkVar('ink-700'),
          800: inkVar('ink-800'),
          900: inkVar('ink-900'),
          950: inkVar('ink-950'),
          975: inkVar('ink-975'),
        },
        parchment: {
          50:  '#fcfaf6',
          100: '#f7f2e8',
          200: '#ede4d0',
          300: '#dfd1ad',
        },
        amber: {
          50:  '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
        },
        iris: {
          50:  '#eef2ff',
          100: '#e0e7ff',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        'glow-amber': '0 0 0 1px rgba(251,191,36,0.18), 0 8px 24px -8px rgba(251,191,36,0.25)',
        'card': '0 1px 2px rgba(0,0,0,0.04), 0 4px 16px -8px rgba(15,23,41,0.08)',
        'card-dark': '0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 32px -16px rgba(0,0,0,0.6)',
      },
      keyframes: {
        'fade-in': { '0%': { opacity: '0', transform: 'translateY(4px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'slide-in-right': { '0%': { opacity: '0', transform: 'translateX(12px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        'pulse-soft': { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.55' } },
      },
      animation: {
        'fade-in': 'fade-in 180ms ease-out',
        'slide-in-right': 'slide-in-right 200ms ease-out',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}

export default config
