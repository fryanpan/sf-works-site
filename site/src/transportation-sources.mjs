// What the streets tool drew on, shared by its four pages so a source cannot
// be listed on one and missing from another.

import { data, records } from "./transportation.mjs";

export const SOURCES = [
  {
    label:
      "Public Works Order 187,005 — Regulations for Excavating and Restoring Streets, for what a utility must put back after opening a street",
    href: "https://sfpublicworks.org/sites/default/files/PW-Order-187005-Signed.pdf",
    group: "Street work and repaving", read: "2026-09-22",
  },
  {
    label:
      "Utility Excavation Moratorium Streets (5wbp-dwzt) — what was repaved and when",
    href: "https://data.sf.gov/d/5wbp-dwzt",
    group: "Street work and repaving", read: data.queriedAt,
  },
  {
    label:
      "Public Works Internal & External Projects (btxj-k9uh) — what each project was scoped to do",
    href: "https://data.sf.gov/d/btxj-k9uh",
    group: "Projects and city records", read: data.queriedAt,
  },
  {
    label: "SFMTA engineering public hearings — the Streets Division directive orders, which is where most bikeways are legislated",
    href: "https://www.sfmta.com/past-meetings-and-events/2617",
    group: "Projects and city records", read: `${records.generated} (orders published since ${records.since})`,
  },
  {
    label: "SFMTA Board of Directors — agendas and minutes, for the items the City Traffic Engineer cannot approve alone",
    href: "https://sanfrancisco.granicus.com/ViewPublisher.php?view_id=55",
    group: "Projects and city records", read: `${records.generated} (meetings since ${records.since})`,
  },
  {
    label:
      "Slow Streets (hkz3-itiu) — which streets carry the designation Shared asks for",
    href: "https://data.sf.gov/d/hkz3-itiu",
    group: "The bike network", read: data.queriedAt,
  },
  {
    label:
      "Mid-Block Traffic Calming Areas (abhw-ffzx) and Intersection-Level Traffic Calming Devices (bp3t-bd4t)",
    href: "https://data.sf.gov/d/abhw-ffzx",
    group: "The bike network", read: data.queriedAt,
  },
  {
    label: "MTA Bike Network Linear Features (ygmz-vaxd) — what is on the ground",
    href: "https://data.sf.gov/d/ygmz-vaxd",
    group: "The bike network", read: `${data.queriedAt} (the layer itself was last refreshed ${data.bikewayLayerAsOf})`,
  },
  {
    label:
      "SFMTA Biking and Rolling Plan (March 2025) — the facility descriptions on printed pp. 74–77, the North Star map and its legend on pp. 68–69, the network definition and Action 2.7.1 on pp. 64–65, and the 2024 all-ages-and-abilities map on pp. 24–25",
    href: "https://www.sfmta.com/projects/biking-and-rolling-plan",
    group: "The Biking and Rolling Plan", read: "2026-09-19",
  },
  {
    label:
      "SFMTA Biking and Rolling Plan, North Star Map — the planned network, traced to GIS because the city publishes none",
    href: "https://www.sfmta.com/projects/biking-and-rolling-plan",
    group: "The Biking and Rolling Plan", read: "2025 edition, traced 2026-09-29",
  },
  {
    label: "Public Works Code §2.4.13",
    href: "https://codelibrary.amlegal.com/codes/san_francisco/latest/sf_publicworks/0-0-0-4453",
    group: "Street work and repaving", read: "2026-09-18",
  },
];
