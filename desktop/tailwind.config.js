/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        korgan: {
          blue: '#0066FF',
          'blue-dim': '#0044AA',
          'blue-bright': '#3399FF',
          orange: '#FF8800',
          red: '#FF3333',
        },
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
