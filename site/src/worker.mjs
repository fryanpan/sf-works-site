// Serve the static build, and give each tool its own hostname on staging.
//
// Production is one site: sf-works.org/transportation, /housing, /permits, so the three
// pages share a navigation and can link into each other. Staging needs the tools
// separable — one of them can be mid-rewrite while another is being shown to
// somebody — so <tool>.staging.sf-works.org serves the same build with that
// tool's page at the root. One build, several front doors, no drift between them.

const TOOLS = ["transportation", "housing", "permits"];

// Who may frame /embed/*: sf-works.org's own pages (a published board doc
// frames its figures from /embed/figures/), fryanpan.com, which runs the same
// bike post, the workspace board that reviews it, and local development. A
// private review server is added from the Worker's REVIEW_FRAME_ANCESTORS
// setting (space-separated origins), set once per deploy target with
// `npx wrangler secret put REVIEW_FRAME_ANCESTORS` so its address stays out of
// the repo; unset, nothing is added.
const FRAME_ANCESTORS = [
  "'self'",
  "https://fryanpan.com",
  "https://*.fryanpan.com",
  "http://localhost:*",
  "http://127.0.0.1:*",
  "https://workspaces.fryanpan.com",
];
const frameAncestors = (env) =>
  [...FRAME_ANCESTORS, ...String(env.REVIEW_FRAME_ANCESTORS || "").split(/\s+/).filter(Boolean)].join(" ");

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const tool = TOOLS.find((t) => url.hostname.startsWith(`${t}.`));

    // The transportation tool lived at /streets until 2026-09-22 and links to
    // it exist. Send them to the new address, permanently.
    if (url.pathname === "/streets" || url.pathname.startsWith("/streets/")) {
      url.pathname = "/transportation" + url.pathname.slice("/streets".length);
      return Response.redirect(url.toString(), 301);
    }

    // /transportation was the bike network overview until 2026-09-29, when it
    // moved to /transportation/bike, and a redirect to it until 2026-11-19, when
    // it became the Transportation front page Mobility lands on.

    // Every bike page moved under /transportation/bike on 2026-09-29: the
    // overview from /transportation/bike-network, and Better Coordination,
    // Current Projects (with each project's page) and About the Data from
    // /transportation/<page>. The build also leaves a redirect page at each old
    // address; this catches any the build does not know.
    const moved = url.pathname.match(/^\/transportation\/(bike-network|departments|projects|about)(\/.*)?$/);
    if (moved) {
      const to = { "bike-network": "", departments: "/departments", projects: "/projects", about: "/about" }[moved[1]];
      url.pathname = "/transportation/bike" + to + (moved[2] && moved[2] !== "/" ? moved[2] : "");
      return Response.redirect(url.toString(), 301);
    }

    // Safer School Trips, at /transportation/school-trips since 2026-10-12 and
    // /transportation/bike/schools/trips before, was archived on 2026-11-19
    // (src/features.mjs ARCHIVED_PAGES). Every address under either lands on
    // the Transportation front page. The build also leaves a redirect page at
    // each page's address.
    if (/^\/transportation\/(school-trips|bike\/schools\/trips)(\/.*)?$/.test(url.pathname)) {
      url.pathname = "/transportation";
      url.hash = "";
      return Response.redirect(url.toString(), 301);
    }

    // The plan's progress page became /transportation/future on 2026-09-22
    // and a section of the overview on 2026-09-23. That section has no anchor
    // of its own on the overview, so the reader lands at the top, as the
    // build's redirect pages at those addresses send them.
    if (/^\/transportation\/(progress|future)\/?$/.test(url.pathname)) {
      url.pathname = "/transportation/bike";
      url.hash = "";
      return Response.redirect(url.toString(), 301);
    }

    // "Two maps disagree" became a section of About the Data on 2026-09-22 and
    // left the site on 2026-09-30; its old address lands on About the Data.
    if (url.pathname === "/transportation/osm" || url.pathname === "/transportation/osm/") {
      url.pathname = "/transportation/bike/about";
      url.hash = "";
      return Response.redirect(url.toString(), 301);
    }

    if (tool && url.pathname === "/") {
      url.pathname = `/${tool}`;
      return env.ASSETS.fetch(new Request(url, request));
    }

    let response = await env.ASSETS.fetch(request);

    // The bike figures at /embed/* are framed by fryanpan.com, which carries
    // the same post, and by the workspace board that reviews it, and by
    // nothing else. wrangler.toml routes these paths through this Worker
    // (run_worker_first); without that, static assets skip it and the header
    // never gets sent. Nothing here sends X-Frame-Options, which would
    // override this in older browsers.
    if (url.pathname.startsWith("/embed/")) {
      const headers = new Headers(response.headers);
      headers.delete("X-Frame-Options");
      headers.set("Content-Security-Policy", `frame-ancestors ${frameAncestors(env)}`);
      response = new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }

    // The Street Safety map's data, public figures read by the map wherever it is mounted: fryanpan.com, and a board's
    // sandboxed frame, whose origin is "null", so only a wildcard lets it fetch (src/safety-map/map.js).
    if (url.pathname.startsWith("/transportation/street-safety/data/")) {
      const headers = new Headers(response.headers);
      headers.set("Access-Control-Allow-Origin", "*");
      response = new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }

    // The post's canonical text, which fryanpan.com reads as it is.
    if (url.pathname.startsWith("/content/posts/") && url.pathname.endsWith(".md")) {
      const headers = new Headers(response.headers);
      headers.set("Content-Type", "text/markdown; charset=utf-8");
      response = new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }

    // Staging is a working copy. Keeping it out of search results costs nothing
    // and stops a half-finished figure being the one a search turns up.
    if (env.ENVIRONMENT === "staging") {
      const headers = new Headers(response.headers);
      headers.set("X-Robots-Tag", "noindex, nofollow");
      // A Response's status is a getter on its prototype, so spreading the
      // response would copy nothing and every page, 404s included, would
      // answer 200.
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }

    return response;
  },
};
