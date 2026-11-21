// Local dev server with live reload: `astro dev`, which renders a page when it
// is asked for, so an edit shows on the next request instead of after a build
// of every page. Needs `npm ci` in site/ first.
//
//   node scripts/dev.mjs [--port 8765] [--staging]
//
// The pieces Astro does not do itself are in scripts/dev-reload.mjs (watching
// content/ and data/, which the pages read with fs, and telling open pages)
// and scripts/dev-render.mjs (one page per request; a failing geometry or
// mile-basis check shown on the page instead of stopping the server).
//
// --staging serves the staging variant, with the workspace comment widget,
// using the same variables the staging deploy job sets. Reviewers reach the
// server through Tailscale (see `tailscale serve status`), so it binds to
// 127.0.0.1 and the Tailscale proxy does the HTTPS.
//
// SITE_BASE_PATH=/some/prefix serves the whole tree under that prefix, with
// the reload stream at <prefix>/__reload, for a host that proxies this port
// at that path (the board's app resource: /workspaces/<ws>/apps/<id>/). The
// pages read the same variable and prefix every root-relative URL, and
// astro.config.mjs sets it as Astro's `base`.
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const port = args.includes("--port") ? Number(args[args.indexOf("--port") + 1]) : 8765;
const staging = args.includes("--staging");
const BASE = (process.env.SITE_BASE_PATH || "").replace(/\/+$/, "");

// Under a base path the pages are served through the board's app door, which
// injects its own comment widget bound to the app resource and relays it
// through the host page; the frame's opaque origin cannot reach our widget
// server anyway (Workspaces, 2026-09-23). So the site's own tag is emitted
// only for the direct Tailscale page.
// The dev server always shows tools that are hidden on production
// (src/features.mjs), since that is where they are being finished.
process.env.ASTRO_TELEMETRY_DISABLED = "1";
process.env.SITE_SHOW_HIDDEN = "1";
// The widget's board doc, board and server come from the environment
// (WIDGET_DOC_ID, WIDGET_WORKSPACE_ID, WIDGET_SERVER), never from the repo;
// without them the staging variant runs with no widget.
if (staging && !BASE && !process.env.WIDGET_DOC_ID) {
  console.log("dev: WIDGET_DOC_ID is not set, so the staging variant has no comment widget");
}
if (!staging || BASE) {
  delete process.env.WIDGET_DOC_ID;
}

// Imported after the variables are set: the page modules read them when they load.
const { dev } = await import("astro");
await dev({ root: SITE, server: { port, host: "127.0.0.1" }, logLevel: "warn" });
console.log(
  `dev server on http://127.0.0.1:${port}${BASE}/ (${staging ? (BASE ? "staging variant, widget left to the board door" : "staging variant, with widget") : "production variant"}); astro dev, one page rendered per request`,
);
