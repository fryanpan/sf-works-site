// The dev server's answer to one request (scripts/dev.mjs, `astro dev`).
//
// In dev the catch-all endpoint, astro/pages/[...file].ts, renders on request
// rather than from a list made up front: it hands the address here, and only
// the page asked for is rendered (scripts/site-files.mjs, renderFile). Vite
// loads this file and everything it imports, so an edit to a page module,
// src/, content/ or data/ is picked up on the next request (astro.config.mjs,
// devServer, drops the loaded modules on every such edit).
//
// The geometry and mile-basis checks run once per edit. A failure stops
// `astro build`; here it is shown on the page instead, so the server stays up
// and the page comes back when the data is fixed.
import { BASE, checkSite, renderFile } from "./site-files.mjs";
import { RELOAD } from "./dev-reload.mjs";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".json": "application/json",
  ".geojson": "application/geo+json",
  ".xml": "application/xml",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
};
const typeOf = (file) => TYPES[(file.match(/\.[^./]+$/) || [""])[0]] || "application/octet-stream";

let checked = null;

const escape = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);

// `request` is the one the catch-all was given; the address comes from its URL.
export async function respond(request) {
  const url = new URL(request.url);
  const reload = !url.searchParams.has("noreload");
  const html = (status, body) =>
    new Response(reload ? body.replace(/<\/body>/i, RELOAD + "</body>") : body, {
      status,
      headers: { "Content-Type": TYPES[".html"], "Cache-Control": "no-store" },
    });

  checked ??= checkSite();
  const errors = await checked;
  if (errors.length) {
    return html(
      500,
      `<!doctype html><meta charset="utf-8"><title>Site check failed</title><body style="font:15px/1.4 system-ui,sans-serif;margin:24px">` +
        `<h1>The geometry or mile-basis check failed</h1><p>${errors.length} error(s). <code>astro build</code> stops on these; fix the data and this page updates.</p>` +
        `<pre style="white-space:pre-wrap">${errors.map(escape).join("\n")}</pre></body>`,
    );
  }

  // The address as asked, slash and all (the parameter drops a trailing
  // slash), less the base path.
  let tail = decodeURI(url.pathname);
  if (BASE && (tail === BASE || tail.startsWith(BASE + "/"))) tail = tail.slice(BASE.length);
  tail = tail.replace(/^\/+/, "");
  let hit = null;
  if (tail === "" || tail.endsWith("/")) hit = await renderFile(`${tail}index.html`);
  else {
    hit = await renderFile(tail);
    // A directory's page asked for without its slash goes to the slash, as
    // the Worker and the old dev server both did, so relative links resolve.
    if (!hit && (await renderFile(`${tail}/index.html`))) {
      return new Response(null, { status: 302, headers: { Location: `${BASE}/${tail}/${url.search}` } });
    }
  }
  if (!hit) {
    const notFound = await renderFile("404.html");
    return html(404, notFound.body);
  }
  if (typeOf(hit.file).startsWith("text/html")) return html(200, hit.body);
  return new Response(hit.body, { headers: { "Content-Type": typeOf(hit.file), "Cache-Control": "no-store" } });
}
