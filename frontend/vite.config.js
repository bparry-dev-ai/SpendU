import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run dev` serves the app on http://localhost:5173 and forwards /api
// calls to Flask on port 5000 (start it with `python app.py`).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:5000' },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
