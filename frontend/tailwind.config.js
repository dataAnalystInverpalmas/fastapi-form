/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"SF Pro Display"', '"SF Pro Text"', 'Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        slate: {
          950: '#020617',
        },
      },
      boxShadow: {
        panel: '0 10px 30px rgba(15, 23, 42, 0.08)',
      },
    },
  },
  plugins: [],
}

