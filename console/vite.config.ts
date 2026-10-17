import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: path.join(here, "web"),
  base: "./",
  build: { outDir: path.join(here, "dist", "web"), emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
