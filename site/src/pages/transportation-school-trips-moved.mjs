// School Trips' addresses before 2026-10-12, when it moved from
// /transportation/bike/schools/trips to /transportation/school-trips (Bryan:
// "Replace Schools at the top level with 'Safer School Trips' and make the url
// school-trips"). The tool and its About page keep answering at the old
// addresses with a redirect page, which carries the tool's #hash state on, and
// the worker sends the same addresses on with a 301.
import { redirectPage } from "../redirect.mjs";

export const path = "/transportation/bike/schools/trips";
export const file = "transportation/bike/schools/trips/index.html";
export const redirect = "/transportation/school-trips";
export const render = () => redirectPage(redirect, "Safer School Trips");

export const pages = () => [{
  path: "/transportation/bike/schools/trips/about/",
  file: "transportation/bike/schools/trips/about/index.html",
  sitemap: false,
  html: redirectPage("/transportation/school-trips/about/", "About School Trips"),
}];
