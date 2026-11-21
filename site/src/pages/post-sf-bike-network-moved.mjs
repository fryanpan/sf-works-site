// /posts/sf-bike-network carried the bike post from its release on 2026-10-08
// until the post became the bike section's front page the same day. Links to
// the old address exist, so it sends the reader on.
import { redirectPage } from "../redirect.mjs";

export const path = "/posts/sf-bike-network";
export const file = "posts/sf-bike-network/index.html";
export const redirect = "/transportation/bike";

export const render = () => redirectPage(redirect, "Improving The Bike Network");
