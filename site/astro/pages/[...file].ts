// Every page the src/pages modules render, published at the path each one
// names (scripts/site-files.mjs). A real Astro page beside this file takes
// precedence for its own address.
//
// `astro build` lists every file up front (getStaticPaths) and writes each.
// `astro dev` does not prerender this route (astro.config.mjs, devServer), so
// each request renders only the page it names (scripts/dev-render.mjs).
import type { APIRoute, GetStaticPaths } from "astro";

declare const __SITE_FILES__: string;

type SiteFile = { file: string; body: string | Uint8Array };
const load = async (): Promise<SiteFile[]> =>
  (await import(/* @vite-ignore */ __SITE_FILES__)).siteFiles();

export const getStaticPaths: GetStaticPaths = async () =>
  (await load()).map(({ file, body }) => ({ params: { file }, props: { body } }));

// In dev the renderer is loaded through Vite rather than Node, so an edit
// drops it and the next request loads it afresh.
const DEV_RENDER = "/scripts/dev-render.mjs";

export const GET: APIRoute = async ({ props, request }) => {
  if (import.meta.env.DEV) return (await import(/* @vite-ignore */ DEV_RENDER)).respond(request);
  return new Response(props.body as BodyInit);
};
