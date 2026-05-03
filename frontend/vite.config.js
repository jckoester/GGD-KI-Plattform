import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { execSync } from 'child_process';
import { readFileSync } from 'fs';
import path from 'path';

const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'));

const gitCommit = (() => {
    try { return execSync('git rev-parse --short HEAD').toString().trim() }
    catch { return 'unknown' }
})()

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  envDir: '../config',
  envPrefix: ['VITE_', 'PUBLIC_'],
  resolve: {
    alias: {
      $docs: path.resolve('./../docs/user'),
    },
  },
  define: {
    __GIT_COMMIT__: JSON.stringify(gitCommit),
    __APP_VERSION__: JSON.stringify(version),
  },
  server: {
    fs: {
      allow: ['..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
});
