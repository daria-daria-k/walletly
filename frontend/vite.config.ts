import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // В разработке фронт и API тоже живут на одном адресе — как за nginx на сервере
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000' },
  },
});
