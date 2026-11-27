import { defineConfig } from "drizzle-kit";

// Paths are relative to frontend/ (where `pnpm db:generate` runs), not to this folder.
export default defineConfig({
  out: "./legacy/drizzle",
  schema: "./legacy/db/schema.ts",
  dialect: "sqlite",
});
