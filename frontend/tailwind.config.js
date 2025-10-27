/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: '#0ea5e9', // sky-500
          primaryDark: '#0284c7', // sky-600
          accent: '#06b6d4', // cyan-500
        },
      },
      boxShadow: {
        soft: '0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.10)',
      },
    },
  },
  plugins: [],
};
