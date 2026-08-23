/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        medintel: {
          dark: '#0B0E17',
          panel: '#121829',
          panelAlt: '#161F36',
          border: '#1E293B',
          primary: '#3B82F6',
          cyan: '#06B6D4',
          critical: '#EF4444',
          moderate: '#F97316',
          low: '#10B981',
          purple: '#8B5CF6',
        }
      }
    },
  },
  plugins: [],
}
