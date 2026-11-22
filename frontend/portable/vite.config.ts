import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath} from 'node:url';

// In development every path that production serves from Django (behind nginx) is proxied to the
// Django dev server, so the site behaves the same on http://127.0.0.1:5173 as on the live domain.
const backend = process.env.FLOWLY_BACKEND || 'http://127.0.0.1:3000';
const djangoPaths = ['/api', '/health', '/account', '/accounts', '/static', '/media', '/admin', '/robots.txt', '/sitemap.xml'];

export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  publicDir: '../public',
  plugins: [react()],
  server: {proxy: Object.fromEntries(djangoPaths.map(p => [p, {target: backend, changeOrigin: false}]))},
  build: {outDir: '../ec2-dist/public', emptyOutDir: true, sourcemap: false},
});
