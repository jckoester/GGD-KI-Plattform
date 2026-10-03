import tailwindcss from "@tailwindcss/vite";
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";
import { execSync } from "child_process";
import { readFileSync } from "fs";
import path from "path";

// Die Plattformversion hat **eine** Quelle: `backend/VERSION` (0.13, P4). Das Backend
// meldet sie in `/health`; hier landet sie in `__APP_VERSION__` (Über-Seite, Feedback).
// `package.json` trägt bewusst keine Version mehr — sonst gäbe es zwei Zahlen.
const version = readFileSync(
  new URL("../backend/VERSION", import.meta.url),
  "utf-8",
).trim();

const gitCommit = (() => {
  try {
    return execSync("git rev-parse --short HEAD").toString().trim();
  } catch {
    return "unknown";
  }
})();

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  envDir: "..",
  envPrefix: ["VITE_", "PUBLIC_"],
  resolve: {
    alias: {
      $docs: path.resolve("./../docs/user"),
    },
  },
  define: {
    __GIT_COMMIT__: JSON.stringify(gitCommit),
    __APP_VERSION__: JSON.stringify(version),
  },
  server: {
    fs: {
      allow: [".."],
    },
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
