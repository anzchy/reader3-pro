// Vitest host (013 WI-9 A9.8). The alias comes from the same module Vite uses;
// never write a second alias map here. No passWithNoTests: an empty run must fail.
import { defineConfig } from "vitest/config";

import { alias, FRONTEND_ROOT } from "./aliases.ts";

export default defineConfig({
  root: FRONTEND_ROOT,
  resolve: { alias },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.ts"],
    watch: false,
  },
});
