# Atmospheric App

Atmospheric app is the SvelteKit-based app scaffold for the Atmospheric project. It provides the starting point for the dashboard and UI components used to view environmental sensor data. The app is under active development and currently functions as a scaffold — most features and integrations are not yet implemented.

Quick start (using Bun)

- Install dependencies: bun install
- Run in development: bun run dev
- Build for production: bun run build
- Preview a production build: bun run preview
- Typecheck: bun run check
- Lint: bun run lint
- Format: bun run format

Using Bun via mise

The repository pins Bun in the global mise.toml (bun = "1.3"). To ensure you run the exact pinned Bun version, prefer invoking Bun commands through mise from the repository root so the pinned runtime is used. For example, run mise to execute Bun commands (install/start/build) from the repo root — this avoids mismatched Bun versions across developer machines or CI.

Environment

- Copy app/.env.example to app/.env and update values before running the app.

Database & auth helpers

- Database helpers (Drizzle) are available via npm scripts (invoke via Bun):
  - bun run db:push
  - bun run db:generate
  - bun run db:migrate
  - bun run db:studio
- To generate the auth schema: bun run auth:schema

Notes

- This directory is a scaffold only. See the repository root README.md for project-level goals and status.
- Files and configs included: package.json, svelte.config.js, drizzle.config.ts, and basic Tailwind + Prettier + ESLint setup.

