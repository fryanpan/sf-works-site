// Live reload for `astro dev` (scripts/dev.mjs), the one piece Astro and Vite
// cannot do for this site.
//
// The pages read content/ and data/ with fs, so Vite never sees those files
// change, and a page module's edit reaches no browser module either: the
// pages are rendered on the server and ship no Vite client. So this watches
// the folders the pages are built from, drops every module Vite has loaded on
// any edit there (the next request renders afresh), and tells each open page.
//
// The message goes over a plain event stream at <base>/__reload, not Vite's
// HMR websocket, because the board's app door relays requests with fetch and
// drops `Upgrade`: a websocket never reaches this port through it, and an
// event stream does. The page shows a bar rather than reloading itself (the
// reasons are in the script below).
import path from "node:path";
import { spawn } from "node:child_process";

const BASE = (process.env.SITE_BASE_PATH || "").replace(/\/+$/, "");
const WATCHED = ["src", "content", "data", "scripts", "astro"];

export const RELOAD = `<script>
(function () {
  var es = new EventSource("${BASE}/__reload");
  // A rebuild reloads the page. The board keeps a comment draft through the
  // reload since its PR 1142 (Bryan, 2026-09-24: "Looks right"), which
  // answers the lost-comment problem ("every time you update in a live
  // reload, I lose my comment", 2026-09-23) that the reload button replaced.
  // A rebuild no longer reloads by itself: a reload in the middle of voice
  // feedback dropped the board's widget and the note being recorded (Bryan,
  // 2026-09-28: "I was in the middle of leaving voice feedback ... the
  // feedback widgets all disappeared"). The page shows a small bar instead,
  // and the reader reloads when they are done.
  es.onmessage = function (e) {
    if (e.data !== "reload" || document.getElementById("sfw-updated")) return;
    var bar = document.createElement("div");
    bar.id = "sfw-updated";
    bar.setAttribute("role", "status");
    bar.style.cssText = "position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:2147483000;" +
      "background:#1f2328;color:#fff;font:14px/1.3 system-ui,sans-serif;padding:8px 10px 8px 14px;" +
      "border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);display:flex;gap:10px;align-items:center";
    bar.innerHTML = 'This page has been updated. <button type="button" style="font:inherit;font-weight:600;' +
      'padding:6px 12px;border:0;border-radius:6px;background:#fff;color:#1f2328;cursor:pointer">Reload</button>' +
      '<button type="button" aria-label="Dismiss" style="font:inherit;border:0;background:none;color:#fff;cursor:pointer;padding:6px">×</button>';
    var b = bar.querySelectorAll("button");
    b[0].onclick = function () { location.reload(); };
    b[1].onclick = function () { bar.remove(); };
    document.body.appendChild(bar);
  };
  // A proxy that cannot carry the event stream fails this at once; reloading
  // on that error reloaded the page every 1.5s through the board door and
  // tore down its comment controls each time (Bryan, 2026-09-23, twice:
  // "What happened to my comment controls again?"). So an error ends live
  // reload for this page and the reader refreshes by hand.
  es.onerror = function () { es.close(); };
})();
</script>`;

// The Astro integration: dev only, it does nothing to `astro build`.
export function devServer() {
  let dev = false;
  return {
    name: "sf-works-dev-server",
    hooks: {
      "astro:config:setup": ({ command, updateConfig }) => {
        if (command !== "dev") return;
        dev = true;
        updateConfig({ vite: { plugins: [reloadPlugin()] } });
      },
      // Render on request: in dev the catch-all is not prerendered, so Astro
      // never asks it for the whole list of paths (getStaticPaths) and each
      // request renders only its own page.
      "astro:route:setup": ({ route }) => {
        if (dev && route.component.endsWith("[...file].ts")) route.prerender = false;
      },
    },
  };
}

function reloadPlugin() {
  return {
    name: "sf-works-reload",
    configureServer(server) {
      const root = server.config.root;
      const dirs = WATCHED.map((d) => path.join(root, d) + path.sep);
      const clients = new Set();

      // The board's door strips the base path before forwarding and a browser
      // on this port directly keeps it, so a request without it gets it put
      // back, and Astro (whose `base` is the same prefix) sees one tree. It
      // goes first in the stack, ahead of Astro's own base handling, which
      // Astro puts at the front once every plugin is configured; this
      // plugin's post hook runs after Astro's.
      const front = () => server.middlewares.stack.unshift({ route: "", handle: (req, res, next) => {
        if (BASE && req.url !== BASE && !req.url.startsWith(BASE + "/") && !req.url.startsWith(BASE + "?")) {
          req.url = BASE + (req.url.startsWith("/") ? "" : "/") + req.url;
        }
        // The home page is the catch-all with no parameter, which Astro
        // refuses for an endpoint that also lists paths; asking for its file
        // by name is the same page.
        const [p, q] = req.url.split(/\?(.*)/s);
        if (p === `${BASE}/` || p === BASE) req.url = `${BASE}/index.html${q !== undefined ? "?" + q : ""}`;
        if (p === `${BASE}/__reload`) {
          res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
          res.write("data: hello\n\n");
          clients.add(res);
          req.on("close", () => clients.delete(res));
          return;
        }
        next();
      } });

      // A post Bryan edits on the board (content/posts/<post>.md) also feeds
      // its export bundle, which fryanpan.com's preview watches, so the
      // bundle is rewritten on each edit, one run at a time per post.
      const posts = path.join(root, "content", "posts") + path.sep;
      const exporting = new Map();
      const exportPost = (file) => {
        const slug = path.basename(file, ".md");
        if (exporting.get(slug)) { exporting.set(slug, "again"); return; }
        exporting.set(slug, "running");
        const p = spawn(process.execPath, [path.join(root, "scripts", "export-post.mjs"), slug], { cwd: root, stdio: ["ignore", "ignore", "pipe"] });
        let err = "";
        p.stderr.on("data", (d) => { err += d; });
        p.on("close", (code) => {
          if (code) console.error(`export-post ${slug} failed:\n${err}`);
          const again = exporting.get(slug) === "again";
          exporting.delete(slug);
          if (again) exportPost(file);
        });
      };

      let timer;
      const changed = (file) => {
        if (!dirs.some((d) => file.startsWith(d))) return;
        if (file.startsWith(posts) && file.endsWith(".md")) exportPost(file);
        clearTimeout(timer);
        timer = setTimeout(() => {
          for (const env of Object.values(server.environments ?? {})) env.moduleGraph?.invalidateAll();
          server.moduleGraph?.invalidateAll?.();
          const stamp = new Date().toTimeString().slice(0, 8);
          console.log(`${stamp} changed ${path.relative(root, file)}; ${clients.size} page(s) told`);
          for (const res of clients) res.write("data: reload\n\n");
        }, 50);
      };
      for (const d of dirs) server.watcher.add(d);
      server.watcher.on("change", changed);
      server.watcher.on("add", changed);
      server.watcher.on("unlink", changed);
      return front;
    },
  };
}
