/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: [
          'Inter var',
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        // Brand — aligned to cBioPortal's signature blue for a familiar feel.
        primary: {
          50: '#eef6fd',
          100: '#d5e9fb',
          200: '#b0d4f6',
          300: '#7eb8ef',
          400: '#4f9ae8',
          500: '#2986e2',
          600: '#1f6fc4',
          700: '#1d5aa0',
          800: '#1d4c84',
          900: '#1c416d',
          950: '#132a49',
        },
        // Accent — teal, used sparingly for highlights.
        accent: {
          50: '#edfcf6',
          100: '#d3f8e9',
          200: '#aaefd6',
          300: '#73e0bd',
          400: '#3bc89e',
          500: '#17ad84',
          600: '#0b8b6c',
          700: '#0a6f58',
          800: '#0c5847',
          900: '#0b483b',
        },
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
      },
      boxShadow: {
        soft: '0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.06)',
        card: '0 1px 3px 0 rgb(15 23 42 / 0.05), 0 12px 32px -16px rgb(15 23 42 / 0.18)',
        pop: '0 12px 40px -12px rgb(15 23 42 / 0.28)',
        glow: '0 0 0 1px rgb(59 102 245 / 0.12), 0 12px 40px -12px rgb(59 102 245 / 0.35)',
      },
      backgroundImage: {
        'grid-slate':
          'linear-gradient(to right, rgb(15 23 42 / 0.035) 1px, transparent 1px), linear-gradient(to bottom, rgb(15 23 42 / 0.035) 1px, transparent 1px)',
        'mesh-primary':
          'radial-gradient(at 20% 20%, rgb(41 134 226 / 0.12) 0px, transparent 50%), radial-gradient(at 80% 0%, rgb(23 173 132 / 0.08) 0px, transparent 50%), radial-gradient(at 80% 100%, rgb(31 111 196 / 0.10) 0px, transparent 50%)',
      },
      backgroundSize: {
        grid: '28px 28px',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in-fast': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
        'pop-in': {
          from: { opacity: '0', transform: 'translateY(8px) scale(0.97)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'slide-in-x': {
          from: { opacity: '0', transform: 'translateX(12px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out both',
        'fade-in-fast': 'fade-in-fast 0.2s ease-out both',
        float: 'float 6s ease-in-out infinite',
        'pop-in': 'pop-in 0.2s ease-out both',
        'slide-in-x': 'slide-in-x 0.18s ease-out both',
      },
    },
  },
  plugins: [],
};
