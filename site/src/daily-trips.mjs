// What the Daily Trips map and its About page share: the data file, the
// labels for each destination and way of travelling, the three bands, and the
// sources list.
//
// The data is site/data/daily-trips.json, written by
// tools/travel/daily-trips-site.py from out/full-map/ (tools/travel/full-map.py), whose
// checks make every count here equal the published summary.json's.

import fs from "node:fs";
import nodePath from "node:path";

export const D = JSON.parse(fs.readFileSync(nodePath.join(import.meta.dirname, "..", "data", "daily-trips.json"), "utf8"));

// The destinations in the order a parent thinks of them: school first, then
// daily errands, then Muni. "muni" is not a destination type in the data: it
// is the block's Muni service, which has no mode.
export const PLACES = [
  ["elementary", "Elementary school"],
  ["middle", "Middle school"],
  ["high", "High school"],
  ["grocery", "Grocery store"],
  ["library", "Library"],
  ["park", "Park"],
  ["major_park", "Large park (10+ acres)"],
  ["commercial", "Commercial district"],
  ["muni", "Frequent Muni stop"],
];
export const MODES = [
  ["walk", "Walk"],
  ["bike", "Low-stress bike"],
  ["transit", "Muni or walk"],
  ["car", "Car"],
];
// The phrase each mode takes in a sentence: "within 15 minutes of a library by low-stress bike".
// The mode is named as its button names it; the note under the buttons says what it means, once.
export const MODE_PHRASE = { walk: "on foot", bike: "by low-stress bike", transit: "by Muni or walk", car: "by car" };
export const PLACE_PHRASE = {
  elementary: "an elementary school", middle: "a middle school", high: "a high school", grocery: "a grocery store",
  library: "a library", park: "a park", major_park: "a park of 10 acres or more", commercial: "a commercial district",
};

// Three ordered bands, darkest best, from the site's one sequential scale (layout.mjs).
export const BANDS = {
  time: ["15 minutes or less (ideal)", "16 to 30 minutes (at most)", "Over 30 minutes"],
  car: ["15 minutes or less", "16 to 30 minutes", "Over 30 minutes"],
  muni: ["Every 5 minutes (goal)", "Every 10 minutes", "Less often, or no stop within a quarter mile"],
};
export const BAND_COLOURS = ["--seq-3", "--seq-2", "--seq-1"];

// The opening view: high school by low-stress bike, a trip a teenager makes alone, and the one where the
// low-stress routes add most over walking (55% of residents within 15 minutes on foot, 69% by bike).
export const DEFAULT = { to: "high", by: "bike", t3: false };

export const sig2 = (n) => {
  if (!n) return "0";
  const p = Math.pow(10, Math.max(0, Math.floor(Math.log10(Math.abs(n))) - 1));
  return (Math.round(n / p) * p).toLocaleString("en-US");
};
export const pct = (n, of) => {
  const v = (100 * n) / of;
  return v >= 99.5 && n < of ? ">99%" : v < 1 && n > 0 ? "<1%" : `${Math.round(v)}%`;
};

// Residents within `t` minutes of `to` by `by`. For "muni", residents with Muni every 5 minutes whatever `t`,
// as the page counts them.
export function within(to, by, t3, t) {
  const pop = D.pop;
  let n = 0;
  if (to === "muni") {
    for (let i = 0; i < pop.length; i++) if (D.muni[i] === 5) n += pop[i];
    return n;
  }
  const v = by === "transit" && t3 && D.tthird ? D.tthird[to] : D.min[to][by];
  for (let i = 0; i < pop.length; i++) if (v[i] != null && v[i] <= t) n += pop[i];
  return n;
}

const longDate = (iso) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });
export const SERVICE_DAY = longDate(D.asof.service_date);

export const SOURCES = [
  { label: "DataSF, Census 2020: Blocks for San Francisco (residents per block)", href: "https://data.sfgov.org/d/p2fw-hsrv", read: "2026-09-22" },
  { label: "U.S. Census Bureau, TIGERweb 2020 census block outlines", href: "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer/10", read: "2026-09-29" },
  { label: "SFMTA, GTFS Transit Data (the Muni schedule)", href: "https://www.sfmta.com/reports/gtfs-transit-data", read: "2026-10-23", through: "2026-08-28" },
  { label: "SFMTA, bikeway network layer", href: "https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0", read: "2026-09-22" },
  { label: "SFCTA, INRIX speeds on Congestion Management Program segments, September 2026, 8 to 9 AM", href: "https://api.sfcta.org/api/inrix_rt_hourly_exp?date=eq.2026-09&period=eq.8", read: "2026-10-08" },
  { label: "DataSF, Slow Streets", href: "https://data.sfgov.org/d/hkz3-itiu", read: "2026-09-28" },
  { label: "DataSF, Recreation and Parks Properties", href: "https://data.sfgov.org/d/gtr9-ntp6", read: "2026-10-23" },
  { label: "DataSF, Zoning Map – Zoning Districts", href: "https://data.sfgov.org/d/3i4a-hu95", read: "2026-10-23" },
  { label: "California Department of Education, Public Schools and Districts data file", href: "https://www.cde.ca.gov/ds/si/ds/pubschls.asp", read: "2026-09-22" },
  { label: "DataSF, Schools (private schools)", href: "https://data.sfgov.org/d/7e7j-59qk", read: "2026-09-30" },
  { label: "DataSF, City Facilities (library branches)", href: "https://data.sfgov.org/d/nc68-ngbr", read: "2026-09-22" },
  { label: "OpenStreetMap contributors: grocery stores, streets and paths", href: "https://www.openstreetmap.org/copyright", read: "2026-10-20" },
];
