/** @type {import('tailwindcss').Config} */
export default {
  // Scan the HTML shell and every frontend module so utilities are not dropped.
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Outfit', 'Segoe UI', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
