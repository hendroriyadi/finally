// Source: this repo's own bundled Next.js 16.2.12 testing guide,
// node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md.
// Per frontend/AGENTS.md the bundled docs win over remembered patterns — look
// there first when this config needs to change.
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  // tsconfigPaths before react: alias resolution (@/components/..., @/lib/...)
  // has to happen ahead of the JSX transform.
  plugins: [tsconfigPaths(), react()],
  resolve: {
    alias: {
      // Explicit, and NOT redundant with tsconfigPaths above. tsconfig.json's
      // `exclude` lists the test globs so `next build` does not type-check
      // them — and vite-tsconfig-paths honours that same `exclude`, so it
      // refuses to map `@/` inside the very files that need it. Without this
      // alias every test fails at import with "Failed to resolve @/...".
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    // No implicit globals — describe/it/expect are imported explicitly, so a
    // reader can tell where every identifier comes from.
  },
});
