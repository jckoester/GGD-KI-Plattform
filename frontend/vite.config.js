import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { execSync } from 'child_process';
import { readFileSync } from 'fs';

const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'));

const gitCommit = (() => {
    try { return execSync('git rev-parse --short HEAD').toString().trim() }
    catch { return 'unknown' }
})()

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  envDir: '../config',
  envPrefix: ['VITE_', 'PUBLIC_'],
  define: {
    __GIT_COMMIT__: JSON.stringify(gitCommit),
    __APP_VERSION__: JSON.stringify(version),
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
});
