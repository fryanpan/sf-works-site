// What "How Residents Travel: One City, Many Neighborhoods" and its About page
// share: the tract data, each measure's label, format, colour range and
// one-line source, and the sources list.
//
// The data is site/data/neighborhood-travel.json, written by
// tools/travel/neighborhood-travel.py, which documents every measure's definition
// and runs the checks.

import fs from "node:fs";
import nodePath from "node:path";

export const D = JSON.parse(fs.readFileSync(nodePath.join(import.meta.dirname, "..", "data", "neighborhood-travel.json"), "utf8"));

const MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const month = (ym) => `${MON[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;
const a = (href, text) => `<a href="${href}">${text}</a>`;
const ACS = (t) => a(`https://data.census.gov/table?q=${t}&g=050XX00US06075$1400000`, `Census ACS 2020 to 2024, table ${t}`);
const MODE_SRC = `${ACS("B08301")}, workers 16 and over.`;
const GAP_SRC = "Distance of the best bike route off the all-ages network. We did the routing.";

// [key, panel title, format, group, one-line source, button label]. Formats: pct (a 0 to 1 share), dec (one decimal), min (minutes), ft (feet).
export const MEASURES = [
  ["mode_car", "Drive to work", "pct", "work", MODE_SRC, "Drive to work"],
  ["mode_transit", "Take transit to work", "pct", "work", MODE_SRC, "Transit to work"],
  ["mode_bike", "Bike to work", "pct", "work", MODE_SRC, "Bike to work"],
  ["mode_walk", "Walk to work", "pct", "work", MODE_SRC, "Walk to work"],
  ["mode_wfh", "Work from home", "pct", "work", MODE_SRC, "Work from home"],
  ["zero_car", "Households without a car", "pct", "cars", `${ACS("B25044")}.`, "No car at home"],
  ["vmt", "Car miles per resident a weekday", "dec", "cars", `${a("https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/mtc_vmt_home_work_pba2050p/FeatureServer/0", "MTC's 2023 travel model")}, trips that start or end at home.`, "Car miles a day"],
  ["hurt", "People hurt in traffic a year, per 1,000 residents", "dec", "safety", `${a("https://data.sfgov.org/d/nwes-mmgh", "Police crash reports")}, ${month(D.asof.injuries.from)} to ${month(D.asof.injuries.to)}.`, "People hurt"],
  ["hin", "Streets on the High Injury Network", "pct", "safety", `${a("https://www.sfmta.com/en/node/45244", "SFMTA and SFDPH's 2024 network")}.`, "High Injury Network streets"],
  ["night", "Feel unsafe walking alone at night", "pctw", "safety", `${a("https://data.sfgov.org/d/nufj-bfbw", "City Survey")} 2023, by neighborhood.`, "Unsafe at night"],
  ["ewt", "Extra wait for Muni at the nearest frequent stop", "min1", "muni", `${a("https://511.org/open-data/transit", "511's Muni arrival records")}, ${month(D.asof.muni_wait[0])} to ${month(D.asof.muni_wait[1])}.`, "Extra Muni wait"],
  ["cityhall_muni", "Minutes to City Hall by Muni", "min", "muni", `${a("https://www.sfmta.com/reports/gtfs-transit-data", "SFMTA's schedule")}, leaving 8 to 9 AM.`, "City Hall by Muni"],
  ["cityhall_walk", "Minutes to City Hall on foot", "min", "muni", "Walking at 2 mph on OpenStreetMap's streets.", "City Hall on foot"],
  ["grocery", "Minutes on foot to the nearest grocery store", "min", "errands", `${a("https://www.openstreetmap.org/copyright", "OpenStreetMap")} stores, walking at 2 mph.`, "Walk to a grocery"],
  ["gap_ggp", "Bike gap to Golden Gate Park", "ft", "gaps", GAP_SRC, "Bike gap: Golden Gate Park"],
  ["gap_ferry", "Bike gap to the Ferry Building", "ft", "gaps", GAP_SRC, "Bike gap: Ferry Building"],
  ["gap_bart", "Bike gap to the nearest BART station", "ft", "gaps", GAP_SRC, "Bike gap: nearest BART"],
  ["gap_caltrain", "Bike gap to the nearest Caltrain station", "ft", "gaps", GAP_SRC, "Bike gap: nearest Caltrain"],
  ["gap_lungfung", "Bike gap to Lung Fung Bakery", "ft", "gaps", GAP_SRC, "Bike gap: Lung Fung Bakery"],
].filter(([k]) => D.metrics[k]);

// What each panel's number counts, under its name.
export const UNITS = {
  mode_car: "share of workers, carpools included", mode_transit: "share of workers", mode_bike: "share of workers", mode_walk: "share of workers",
  mode_wfh: "share of workers", zero_car: "share of households", vmt: "per resident, trips from or to home, modeled", hurt: "a year per 1,000 residents",
  hin: "share of street length", night: "share of residents, by neighborhood", ewt: "beyond the schedule, nearest frequent stop",
  cityhall_muni: "minutes, leaving 8 to 9 AM", cityhall_walk: "minutes at 2 mph", grocery: "minutes at 2 mph",
  gap_ggp: "bike route off the network", gap_ferry: "bike route off the network", gap_bart: "bike route off the network",
  gap_caltrain: "bike route off the network", gap_lungfung: "bike route off the network, 1823 Clement St",
};

export const GROUPS = [
  ["work", "How Workers Get to Work"],
  ["cars", "Cars"],
  ["safety", "Safety"],
  ["muni", "Muni and Walking"],
  ["errands", "Errands"],
  ["gaps", "Gaps in the All-Ages Bike Network"],
];

// The one categorical view: a map per way to work, on one shared scale.
export const MODES = MEASURES.filter((m) => m[3] === "work").map((m) => m[0]);
export const MAX_SHOWN = 4;
export const DEFAULT = { view: "modes", show: [] };

// Each measure's colour range: 0 to its 95th percentile across tracts, rounded up to two figures, so one
// outlier tract doesn't wash out the rest. The mode maps share the highest of their five.
const nice = (v) => {
  if (!(v > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)) - 1);
  return Math.ceil(v / p) * p;
};
const p95 = (vals) => {
  const s = vals.filter((v) => v != null).sort((x, y) => x - y);
  return s[Math.min(s.length - 1, Math.floor(0.95 * s.length))];
};
export const RANGE = Object.fromEntries(MEASURES.map(([k]) => [k, nice(p95(D.metrics[k]))]));
const modeHi = Math.max(...MODES.map((k) => RANGE[k]));
for (const k of MODES) RANGE[k] = modeHi;

// Citywide: the published county figure where the data carries one, else the resident-weighted mean of tracts.
export const CITY = Object.fromEntries(MEASURES.map(([k]) => {
  if (D.city[k] != null) return [k, D.city[k]];
  let n = 0, s = 0;
  D.metrics[k].forEach((v, i) => { if (v != null) { n += D.pop[i]; s += v * D.pop[i]; } });
  return [k, n ? s / n : null];
}));

// One calm sequential ramp, light to dark with the value (Observable's blues, as the whitepaper's maps used).
export const RAMP = ["#eef3fb", "#c6dbef", "#9ecae1", "#6baed6", "#3a87c0", "#1f5fa3"];
export const NONE = "#e4e7eb";

const lastDay = (ym) => new Date(Date.UTC(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)), 0)).toISOString().slice(0, 10);
// The oldest read among the live sources (crashes, High Injury Network, street centerlines), so the page's
// "Data updated" line never claims newer data than one of its maps holds.
export const READ = [D.asof.injuries.read, D.asof.hin_read, D.asof.centerlines_read].filter(Boolean).map((d) => String(d).slice(0, 10)).sort().slice(0, 1);

export const SOURCES = [
  { label: "U.S. Census Bureau, American Community Survey 2020-2024 5-year, tables B01003, B08301 and B25044, by tract (via Census Reporter)", href: "https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B01003,B08301,B25044&geo_ids=140|05000US06075", read: "2026-11-17" },
  { label: "DataSF, Census 2020: Census Tracts for San Francisco", href: "https://data.sfgov.org/d/sevw-6tgi", read: D.asof.tracts_read },
  { label: "Metropolitan Transportation Commission, home-based vehicle miles traveled per resident, 2023 base year", href: "https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/mtc_vmt_home_work_pba2050p/FeatureServer/0", read: "2026-11-06" },
  { label: "DataSF, Traffic Crashes Resulting in Injury: Victims Involved", href: "https://data.sfgov.org/d/nwes-mmgh", read: D.asof.injuries.read, through: lastDay(D.asof.injuries.to) },
  { label: "SFMTA and SFDPH, 2024 High Injury Network", href: "https://services.arcgis.com/Zs2aNLFN00jrS4gG/arcgis/rest/services/HIN/FeatureServer/0", read: D.asof.hin_read },
  { label: "DataSF, Streets: Active and Retired (street centerlines)", href: "https://data.sfgov.org/d/3psu-pn9h", read: D.asof.centerlines_read },
  { label: "City Controller's Office, City Survey 2023 (DataSF)", href: "https://data.sfgov.org/d/nufj-bfbw", read: "2026-11-17" },
  { label: "511 SF Bay historic stop observations and SFMTA's GTFS (Muni excess wait)", href: "https://511.org/open-data/transit", read: "2026-11-10" },
  { label: "SFMTA, GTFS Transit Data (the Muni schedule)", href: "https://www.sfmta.com/reports/gtfs-transit-data", read: "2026-11-17" },
  { label: "BART, GTFS schedule (station locations)", href: "https://www.bart.gov/schedules/developers/gtfs", read: "2026-11-17" },
  { label: "Caltrain, GTFS schedule (station locations)", href: "https://data.trilliumtransit.com/gtfs/caltrain-ca-us/caltrain-ca-us.zip", read: "2026-11-17" },
  { label: "SFMTA, bikeway network layer", href: "https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0", read: "2026-09-22" },
  { label: "DataSF, Slow Streets", href: "https://data.sfgov.org/d/hkz3-itiu", read: "2026-09-28" },
  { label: "DataSF, Recreation and Parks Properties", href: "https://data.sfgov.org/d/gtr9-ntp6", read: "2026-11-11" },
  { label: "U.S. Census Bureau, Geocoder (Lung Fung Bakery, City Hall)", href: "https://geocoding.geo.census.gov/geocoder/", read: "2026-11-17" },
  { label: "OpenStreetMap contributors: streets, paths, grocery stores and the Ferry Building", href: "https://www.openstreetmap.org/copyright", read: "2026-11-17" },
];
