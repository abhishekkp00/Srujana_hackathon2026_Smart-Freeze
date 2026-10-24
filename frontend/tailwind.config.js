/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          900: '#0B132B',
          800: '#1C2541',
          700: '#3A506B',
        },
        teal: {
          500: '#00A896',
          600: '#028090',
        },
        accent: {
          blue: '#1E6091',
          light: '#F4F7FB',
        }
      }
    },
  },
  plugins: [],
}
