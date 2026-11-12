/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  // dark: classes follow <html data-theme="dark">, the same switch styles.css uses.
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        cyber: {
          void: '#060814',
          emerald: '#00f59b',
          cyan: '#00e5ff',
          violet: '#8b5cf6',
          coral: '#ff3366',
        }
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      }
    },
  },
  plugins: [],
}
