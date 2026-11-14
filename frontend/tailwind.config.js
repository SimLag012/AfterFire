/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          950: 'color-mix(in srgb, var(--color-paper) calc(<alpha-value> * 100%), transparent)',
          900: 'color-mix(in srgb, var(--color-paper-2) calc(<alpha-value> * 100%), transparent)',
          850: 'color-mix(in srgb, var(--color-hover) calc(<alpha-value> * 100%), transparent)',
          800: 'color-mix(in srgb, var(--color-hover) calc(<alpha-value> * 100%), transparent)',
          700: 'color-mix(in srgb, var(--color-rule) calc(<alpha-value> * 100%), transparent)',
          600: 'color-mix(in srgb, var(--color-rule-strong) calc(<alpha-value> * 100%), transparent)',
        },
        accent: {
          fire: 'color-mix(in srgb, var(--color-accent) calc(<alpha-value> * 100%), transparent)',
          amber: 'var(--color-warning)',
          smoke: 'var(--color-muted)',
          recovery: 'var(--color-positive)',
          canopy: 'var(--color-positive)',
          water: 'var(--color-accent-2)',
        }
      },
      fontFamily: {
        sans: ['var(--font-body)'],
        mono: ['var(--font-data)'],
      }
    },
  },
  plugins: [],
}

