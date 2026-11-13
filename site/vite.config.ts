// SPDX-License-Identifier: AGPL-3.0-or-later
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as {
  version: string;
};

function gitCommit(): string {
  if (process.env.PRICELIGHT_COMMIT) return process.env.PRICELIGHT_COMMIT;
  if (process.env.GITHUB_SHA) return process.env.GITHUB_SHA;
  try {
    return execSync('git rev-parse HEAD', { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim();
  } catch {
    return '';
  }
}

const build = {
  version: process.env.PRICELIGHT_VERSION ?? pkg.version,
  buildNumber: process.env.PRICELIGHT_BUILD_NUMBER ?? process.env.GITHUB_RUN_NUMBER ?? 'dev',
  commit: gitCommit().slice(0, 7),
  date: new Date().toISOString().slice(0, 10),
};

export default defineConfig({
  // Relative base: the same build works at a domain root, under /Pricelight/
  // on GitHub Pages, or from any static file server.
  base: './',
  plugins: [svelte()],
  define: {
    __BUILD__: JSON.stringify(build),
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    chunkSizeWarningLimit: 900,
    assetsInlineLimit: 0,
  },
  worker: {
    format: 'es',
  },
  optimizeDeps: {
    exclude: ['@duckdb/duckdb-wasm'],
  },
  test: {
    include: ['tests/**/*.test.ts'],
    environment: 'node',
  },
});
