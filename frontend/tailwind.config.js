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
        slate: Object.fromEntries(Object.entries({950:'--color-paper-3',900:'--color-paper-2',800:'--color-hover',700:'--color-rule',600:'--color-rule-strong',500:'--color-muted',400:'--color-muted',300:'--color-ink-2',200:'--color-ink-2',100:'--color-ink',50:'--color-ink'}).map(([shade,token])=>[shade,`color-mix(in srgb, var(${token}) calc(<alpha-value> * 100%), transparent)`])),
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

