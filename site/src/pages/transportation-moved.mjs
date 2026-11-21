// The bike pages' addresses before 2026-09-29, when they moved under
// /transportation/bike (Bryan: "All of the pages should nest under
// /transportation/bike"). Each old address keeps answering with a redirect
// page, project pages included, so no published link stops working. The
// worker sends the same addresses on with a 301 as well.
import { redirectPage } from "../redirect.mjs";
import { pages as projectPages } from "./transportation-projects.mjs";

export const path = "/transportation/bike-network";
export const file = "transportation/bike-network/index.html";
export const redirect = "/transportation/bike";
export const render = () => redirectPage(redirect, "Improving The Bike Network");

const ROOTS = [
  ["departments", "Better Coordination"],
  ["projects", "Current Repaving Projects"],
  ["about", "About the Data"],
];

export function pages() {
  const roots = ROOTS.map(([slug, name]) => ({
    path: `/transportation/${slug}/`,
    file: `transportation/${slug}/index.html`,
    sitemap: false,
    html: redirectPage(`/transportation/bike/${slug}/`, name),
  }));
  const projects = projectPages().map((p) => ({
    path: p.path.replace("/transportation/bike/projects/", "/transportation/projects/"),
    file: p.file.replace("transportation/bike/projects/", "transportation/projects/"),
    sitemap: false,
    html: redirectPage(p.path, "this project's page"),
  }));
  return roots.concat(projects);
}
