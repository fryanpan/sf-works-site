// The site's build: `npm run build` (astro build) writes every page into dist/,
// which the Worker in src/worker.mjs serves (wrangler.toml).
//
// The pages are still the modules in src/pages, each rendering its own HTML.
// One catch-all endpoint, astro/pages/[...file].ts, publishes exactly the
// files scripts/site-files.mjs lists, byte for byte, so moving to Astro changed
// no page. New pages can be written as .astro or .md files under astro/pages/;
// Astro's own src/pages would collide with the page modules, so srcDir is
// astro/ and src/ is left as it is.
//
// Before anything is written, the geometry and mile-basis checks run and a
// failure stops the build (scripts/site-files.mjs, checkSite).
//
// `astro dev` (scripts/dev.mjs) renders a page only when it is asked for, so
// an edit shows on the next request rather than after a whole build. The dev
// half is scripts/dev-reload.mjs and scripts/dev-render.mjs.
import { defineConfig } from "astro/config";
import { devServer } from "./scripts/dev-reload.mjs";
import { fileURLToPath, pathToFileURL } from "node:url";

const SITE = fileURLToPath(new URL(".", import.meta.url));
const SITE_FILES = pathToFileURL(`${SITE}scripts/site-files.mjs`).href;

const siteChecks = {
  name: "sf-works-site-checks",
  hooks: {
    "astro:build:start": async ({ logger }) => {
      const { checkSite } = await import(SITE_FILES);
      const errors = await checkSite();
      if (errors.length) {
        for (const e of errors) logger.error(`build: ${e}`);
        throw new Error(`build: ${errors.length} geometry or mile-basis error(s)`);
      }
    },
  },
};

// The same prefix the pages put on their own URLs (scripts/site-files.mjs,
// withBase). Astro's own output carries none of them, so setting it changes
// no built byte; in dev it puts the server under that path.
const BASE = (process.env.SITE_BASE_PATH || "").replace(/\/+$/, "");

export default defineConfig({
  output: "static",
  ...(BASE ? { base: BASE } : {}),
  srcDir: "./astro",
  publicDir: "./astro/public",
  outDir: "./dist",
  devToolbar: { enabled: false },
  integrations: [siteChecks, devServer()],
  vite: {
    // The endpoint loads the page renderer through Node rather than Vite's
    // bundle, so the page modules run exactly as they did before.
    define: { __SITE_FILES__: JSON.stringify(SITE_FILES) },
    // Reviewers may reach the dev server through a private hostname (e.g.
    // `tailscale serve`): DEV_ALLOWED_HOSTS, comma-separated, adds it; unset,
    // only localhost is served. A taken port is an error, not a quiet move to
    // the next one: whatever proxies the dev server expects the port it gave.
    server: {
      strictPort: true,
      allowedHosts: (process.env.DEV_ALLOWED_HOSTS || "").split(",").map((h) => h.trim()).filter(Boolean),
    },
  },
});
