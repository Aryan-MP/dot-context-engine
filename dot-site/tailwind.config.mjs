/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,ts,jsx,tsx,md,mdx}'],
  theme: {
    extend: {
      colors: {
        // "Field Notes" palette — warm paper + ink, violet accent.
        paper: '#f4efe4',
        'paper-2': '#faf6ec',
        'paper-edge': '#e7dfcd',
        ink: '#1f1b16',
        'ink-2': '#6b6357',
        'ink-3': '#9a9384',
        rule: 'rgba(31,27,22,0.1)',
        violet: '#6a4ff0',
        'violet-ink': '#5238d6',
        terra: '#c8612f',
        green: '#3f7d4f',
      },
      fontFamily: {
        serif: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
        hand: ['Caveat', 'cursive'],
      },
      maxWidth: {
        content: '1080px',
      },
    },
  },
  plugins: [],
};
