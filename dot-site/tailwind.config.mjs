/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,ts,jsx,tsx,md,mdx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0c0c0e',
        surface: '#111116',
        elevated: '#18181f',
        border: 'rgba(255,255,255,0.07)',
        primary: '#f0f0f5',
        secondary: '#8b8b9e',
        muted: '#4a4a5e',
        accent: '#7c6af7',
        'accent-glow': 'rgba(124,106,247,0.15)',
        green: '#4ade80',
        amber: '#fbbf24',
        red: '#f87171',
      },
      fontFamily: {
        serif: ['"Instrument Serif"', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      maxWidth: {
        content: '1100px',
      },
      animation: {
        'fade-up': 'fadeUp 0.6s cubic-bezier(0.16,1,0.3,1) forwards',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        flow: 'flow 3s linear infinite',
        blink: 'blink 1s step-end infinite',
        'spin-slow': 'spin 20s linear infinite',
        'spin-slower': 'spin 32s linear infinite',
        breathe: 'breathe 4s ease-in-out infinite',
        float: 'float 6s ease-in-out infinite',
      },
      keyframes: {
        fadeUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%,100%': { boxShadow: '0 0 20px rgba(124,106,247,0.3)' },
          '50%': { boxShadow: '0 0 40px rgba(124,106,247,0.6)' },
        },
        flow: {
          from: { strokeDashoffset: '100' },
          to: { strokeDashoffset: '0' },
        },
        blink: {
          '0%,100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        breathe: {
          '0%,100%': { transform: 'scale(1)', opacity: '0.9' },
          '50%': { transform: 'scale(1.04)', opacity: '1' },
        },
        float: {
          '0%,100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
      },
    },
  },
  plugins: [],
};
