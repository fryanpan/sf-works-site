// School Trips' City figures: each change's effect, cost and injuries, by the
// rules Bryan set for the SSC comment on 2026-10-11, so the tool and the comment
// give the same numbers.
//
// Reads city.json (tools/school-trips/school-sim.py, city_view), whose sets hold every
// change at full strength, and rules.json (tools/school-trips/school-sim-rules.py). Each
// change has a low, central and high value, central used for the figures, from
// the study review behind the About page, whose ranges Bryan approved on
// 2026-10-13 ("Your updated ranges look okay"):
//   - The network's bike shift: three cases, Low, Central and High (city.json's
//     cases), year 10 of the ten-year horizon (Bryan, 2026-10-18: "Rebuild the
//     model", and "10 years is more reasonable"). Each set holds the students by
//     mode under each case, so a new street's low, central and high are the
//     sim's three cases, read straight from the sets. The central is the
//     headline and the low to high its range (Bryan, 2026-10-18: "Use middle end
//     and show low to high range"). No control moves it.
//   - School Street: 2.7 points fewer car trips, 0 to 5.3. The set is the
//     study's 5.3, and 2.68 of its 5.40 were park-and-stride, which SF's tally
//     counts as driven, so the central blends the set at 2.7 / 5.3.
//   - Safer crossings: the set's 3.3 points more walking and biking, 0 to 6.3,
//     plus calmed residential streets within 660 ft of the schools the $10M
//     reaches, which count as safe to bike (city.json's calming).
//   - Walking school bus: 0.37 car points of TK-5 students, 0 to 1.
//   - Free Muni for caregivers: Muni's share rises 0, 1 or 3 points among TK-8
//     students over half a mile from school (rules.muniFar), and CAR_FRAC of the
//     new riders leave a family car.
//   - Yellow bus: 1,520 riders, every seat, 44% previously driven, about 670
//     fewer driven kids, range 0.16 to 4.3 tally points at 479 kids a point.
//   - Carpool: 0.5% of driven students, 0.2% to 1%.
//   - Assignment: the model's own shift, range 0.1 to 2.2 tally points, in points over its own central.
//   - Speed limit signs take no one out of a car and don't make a street safe
//     to bike, so they cut injuries only.
//   - School Connectors are counted with School Streets on, and priced block by
//     block by street type (rules.connector).
//   - E-bike help: inside the sets. With the e-bike bit on, every student at a
//     school passing the sim's e-bike gate on the set's network takes the PCT's
//     e-bike term on the bike choice (tools/school-trips/school-sim.py, CHANGES["ebike"]).
//     The sim writes that set at full strength and has no take-up share, so the
//     page reads it at full strength too: every family at the gate's schools
//     gets a voucher, $1,000 to $2,000, central $1,500, whether or not they stop
//     driving, as the old voucher rule paid every eligible family. Our reading,
//     the closest to the sim, with no new parameter. The old 3%, 10% or 25%
//     stop-driving rate is gone, since the PCT term now says who switches.
//   Four more changes aren't in city.json's sets, so they are applied on top of a
//   set's result (Bryan, 2026-10-14, "Can we add these options to the tool?"):
//   each takes its points off what's left of its students' car share at its
//   schools, several at one school multiply on what's left, never below 0, and
//   the switchers walk or bike so the injury model prices them.
//   - Travel tracker: a daily classroom tally, Living Streets' WOW kind, at TK-5
//     schools. TK-5 car share down 0, 1.8 or 3.5 points: Scotland's 2.5 and 5
//     points after three years, times the 71% of schools that keep it up, and
//     every TK-5 school running it daily. Switchers walk. $2,000 to
//     $15,000 a school a year, central $5,000.
//   - E-cargo bike month: 12 families a school a year, 73% of them driving, at
//     the e-bike gate's schools; 3%, 10% or 20% of the driving ones are out of
//     the car a year later, one year's cohort. Switchers bike. $190 to $900 a
//     trial, central $400, plus $150,000 a year of staff ($100,000 to $200,000).
//   - Curb restriction: no stopping at the bells at TK-5 schools. TK-5 car share
//     down 0, 0 or 1 point, since the one before and after (Dundee) moved
//     drivers to park and stride, which the tally counts as driven. Switchers walk. $2,000 to $20,000 a school once,
//     central $5,000.
//   - Bike bus: one route a school at the e-bike gate's schools (most students
//     within 2 miles have a bike route that passes the gap test), car share down
//     0, 0.3 or 3 points, paired with its program: a volunteer route at $0, a
//     weekly paid chaperone pair at $4,500 or a daily paid route at $23,000 a
//     year. Switchers bike. 72% of bike bus kids ride with their own parent, so
//     none of these changes frees a parent.
//   Their kids hurt are the fewest and most of every pairing of car level and
//   risk level, around the central, so a change whose switchers carry more risk
//   than the car trip still reads low to high (as is E-bike's).
//   - Business districts at 20 mph, speed humps and speed cameras cut kids hurt only, on their own blocks or camera
//     corridor (SPEED, below).
//   - Kids who wouldn't need their parent: switchers onto a trip another adult
//     runs only, as city.json's sets count them.
//   - Injuries: the school-zone model, each change alone, effects multiplied.
//     Fewer school cars cut only bell-hour injuries, the own-risk base counts
//     the modelled students' share of driven kids, and walking or biking on
//     ordinary streets carries more risk than the car trip it replaces. A
//     protected bikeway carries less.
//
// makeCityModel is written without imports or outside names so its source can be
// copied into the page as it is, and run under node to check it against the comment.
// The module's imports are for ebikeGate's file reader, which runs at build time only.

import fs from "node:fs";
import nodePath from "node:path";

export function makeCityModel(CJ, P) {
  const BITS = CJ.programs, NB = CJ.bands.length, SETS = CJ.sets, COST = P.cost, RULES = P.rules || {};
  // P.assume: central values to use in place of the ones below, keyed by the param names in
  // site/data/school-trips-assumptions.json, so site/scripts/check-assumptions.mjs can rerun the headline at each
  // input's low and high without the simulation. one() swaps a single value, at1() the central of a low, central, high
  // triple, leaving its low and high. With no P.assume every value is the one written here.
  const OV = P.assume || {}, ASSUMED = Object.keys(OV).length > 0;
  const one = (name, v) => (name in OV ? OV[name] : v);
  const at1 = (name, arr) => (name in OV ? arr.map((x, i) => (i === 1 ? OV[name] : x)) : arr);
  const MI = BITS.indexOf("caregiver_muni"), BI = BITS.indexOf("yellow_bus");
  const SI = BITS.indexOf("school_street"), PI = BITS.indexOf("carpool"), WI = BITS.indexOf("walking_bus");
  // The sim's three cases, in its order, and each set's layout: per case, students by mode x6, family-car students per
  // tally band, total trip minutes (NS values), then the students whose trip needs no parent, the same in every case.
  // CEN is the central case, the headline; a figure's low and high are the cases at either side of it.
  const CASES = CJ.cases || ["low", "central", "high"], NC = CASES.length, CEN = CASES.indexOf(CJ.mapCase || "central");
  const NS = 6 + NB + 1, SOLO = NC * NS;
  if (NC !== 3 || CEN !== 1) throw new Error(`school trips: city.json's cases are ${CASES}, not low, central and high`);
  const MUNI_PTS = at1("muni_pts", [0, 1, 3]);
  // Share of new Muni riders who leave a family car: family cars, carpools and bikes in proportion among far TK-8 students.
  const CAR_FRAC = one("muni_car_frac", 0.8845);
  // The shuttle loops carry 640 riders at Denver's loop take-up, 580 to 700 (Bryan, 2026-10-15: "Use loop take-up"), 48%
  // of them previously driven; low and high scale with the riders. BUS_CARS is the sim's own count, 48% of the 640
  // riders (307.2), not a rounded 310: the full-strength set takes exactly that many, and a target above it would ask
  // the blend for more than the set holds.
  const BUS_RIDERS = 640, BUS_CARS = one("bus_car_frac", 0.48) * BUS_RIDERS, BUS_PTS = [580 / 640, 1, 700 / 640], BUS_SEATS = 640;
  const SS_C = one("ss_pts", 2.7), SS = [0, 1, 5.3 / Math.max(SS_C, 1e-9)], SS_SET = SS_C / 5.3;          // School Street: low, central, high over the central; central over the set
  const XING_C = one("xing_pts", 3.3), XING = [0, 1, 6.3 / Math.max(XING_C, 1e-9)];                             // safer crossings' mode gain
  const POOL_SHARE = one("pool_share", 0.005), POOL = [0.4, 1, 2];               // carpool: 0.5% of driven students, 0.2% to 1%
  const WB_PTS = one("wb_pts", 0.37), WB = [0, 1, 1 / Math.max(WB_PTS, 1e-9)];                 // walking school bus: car points of TK-5 students, 0 to 1
  // Assignment's range is 0.1 to 2.2 tally points (the study review behind the About page), in
  // points, not a ratio: low and high are those points over the option's own central at full effect, its tally drop
  // from today as fig() counts it, so a phased option takes the same ratios. ASSIGN_R(id) is set after fig() below.
  const ASSIGN_PTS = [0.1, 2.2];
  const EI = BITS.indexOf("ebike");
  // The changes applied on top of a set's result: their population ("k5", the TK-5 students at every school with
  // them, or "gate", every student at the e-bike gate's schools), car points off at low, central and high, and the
  // mode their switchers take. The e-cargo month counts families, not points: ECARGO_FAM driving families a school a
  // year, ECARGO of them out of the car a year later. The bike bus's yearly cost is paired with its effect, BB_COST.
  const POST = {
    travel_tracker: { pop: "k5", pts: at1("tracker_pts", [0, 1.8, 3.5]), to: "walk" },
    ecargo_month: { pop: "gate", to: "bike" },
    curb_restriction: { pop: "k5", pts: at1("curb_pts", [0, 0, 1]), to: "walk" },
    bike_bus: { pop: "gate", pts: at1("bikebus_pts", [0, 0.3, 3]), to: "bike" },
  };
  const POST_IDS = Object.keys(POST);
  const ECARGO_FAM = 12 * 0.73, ECARGO = at1("ecargo_rate", [0.03, 0.1, 0.2]), BB_COST = [0, 1, 23000 / 4500];
  // Injuries: kids 5 to 18 hurt on SF weekdays, 6 am to 6 pm, August to May, 2021-22 to 2024-25, from site/data/school-kids-hurt.json's
  // model block (tools/school-trips/school-kids-hurt.py), passed in as P.rules.injury. Every distance runs to the nearest school's
  // grounds, measured from their edge as California's school-zone law measures it.
  // - Traffic: fewer cars cut injuries within a quarter mile with the square root of traffic (Elvik 2015), school cars
  //   0, 5 or 25% of bell traffic on residential streets and a tenth of that on main streets, and only at the bells: BELL is the share of child walking and biking crashes within
  //   600 ft on school days that fell at bell hours.
  // - Own risk: a kid leaving a car changes their own risk by GAIN, 1 minus the new mode's risk against the car trip it
  //   replaces. PAX counts every K-12 kid, so it is scaled by the modelled students' share of all K-12 (city.json's students,
  //   SFUSD, charter and private, of 80,919). Walking and biking are riskier per km than a car (Lavoie et al. 2014): walk -0.5 (-1 to 0), bike -2 (-4 to
  //   -1), half that excess for an e-bike voucher rider. Muni 0.15 (0 to 0.25), the bus 0.75 (0.65 to 0.80, TRB 2002).
  //   A rider on a new protected bikeway or a calmed street takes Teschke et al. 2012's route risks against a major
  //   street with parked cars and no bike lane (Bryan, 2026-10-18: "Use Teschke's cuts"): cycle tracks 0.11 (0.02 to
  //   0.54), local streets 0.51 (0.31 to 0.84). The ordinary-street bike risk stands in for that major street, our
  //   inference. Low pairs the riskiest bike with the highest ratio, high the safest with the lowest. A bikeway set's
  //   riders split as its miles do between protected lanes and calmed or shared streets (city.json's separatedShare,
  //   0% to 13%). A School Connector's riders take the calmed street's, since most connectors run on residential
  //   streets and we have no split, our judgment.
  // - Bikeway calming: a bikeway set's calmed blocks cut the kids hurt on them, where both streets are residential, by
  //   calming's 40% (20% to 55%), as safety upgrades' calmed streets do (school-kids-hurt.json's bikeways). Kids hurt
  //   within 660 ft of a school or on speed hump blocks are left out there, so no kid is cut twice.
  // - Safer crossings: 40% (20% to 55%) fewer of the walking and biking kids hurt within 350 ft of the grounds
  //   (Barcelona, NYC, CDC).
  // - Calming: 40% (20% to 55%) of the kids hurt where both streets are residential within 660 ft of the calmed schools,
  //   from city.json's calming (Grundy et al. 2009's 20 mph zones).
  // - Speed limit signs: 10% (5% to 25%) of the kids hurt inside the 500 ft zone in the hours the limit applies
  //   (Kokka et al., Edinburgh).
  // - Assignment: 0.4 (0 to 1), car miles cut 13.6% net of new walkers' risk, our estimate.
  const INJ = RULES.injury;
  if (!INJ || !(INJ.base > 0)) throw new Error("school trips: no injury shares; pass site/data/school-kids-hurt.json's model as rules.injury");
  const HB = INJ.base / INJ.years, NEAR = INJ.near / INJ.base;
  // The modelled students: city.json's per-school counts, or, when the page splits the school list into its own file
  // (city-schools.json, fetched after the model is built), the total the build writes beside it as schoolStudents.
  const NSCH = CJ.schools ? CJ.schools.students.reduce((t, n) => t + n, 0) : CJ.schoolStudents;
  if (!(NSCH > 0)) throw new Error("school trips: city.json has neither schools nor schoolStudents");
  const PAX = 21.75 * Math.min(1, NSCH / 80919), BELL = INJ.bellN / INJ.bellD;
  const GAIN = { bus: at1("gain_bus", [0.65, 0.75, 0.8]), muni: at1("gain_muni", [0, 0.15, 0.25]), walk: at1("gain_walk", [-1, -0.5, 0]),
    bike: at1("gain_bike", [-4, -2, -1]), sepbike: at1("gain_sepbike", [-2, -1, -0.5]), wb: at1("gain_wb", [-0.5, 0, 0.3]), pool: [0, 0, 0], none: [0, 0, 0] };
  const onRoute = (or) => [0, 1, 2].map((k) => 1 - (1 - GAIN.bike[k]) * or[2 - k]);
  GAIN.track = onRoute(at1("or_track", [0.02, 0.11, 0.54]));
  GAIN.calmbike = onRoute(at1("or_local", [0.31, 0.51, 0.84]));
  // School cars' share of the bell-time traffic near a school, low, central and high. Our check of DataSF's crashes
  // (tools/school-trips/school-hour-crashes.py, out/school-hour-crashes/summary.json): injury crashes within 600 ft of a school at
  // its bells were 290 against 288 expected at the city's clock, a ratio of 1.01 (0.89 to 1.12), so no excess at the
  // bells. The low is 0, and the high of 25% is the most that check allows, our inference.
  const TRAFFIC = at1("traffic_share", [0, 0.05, 0.25]), CALM = at1("calm_effect", [0.2, 0.4, 0.55]);
  // School cars are a much smaller share of a main street's traffic than a residential street's, so on main streets the
  // traffic cut takes MAIN_TRAFFIC of the share, our judgment. Kids hurt where the street wasn't matched take the main and
  // residential mix of the matched ones.
  const MAIN_TRAFFIC = one("main_traffic", 0.1);
  const NBS = INJ.nearByStreet || [0, INJ.near, 0], NM = NBS[0] + NBS[1];
  const NEAR_W = NM > 0 ? [[NBS[0] + NBS[2] * NBS[0] / NM, MAIN_TRAFFIC], [NBS[1] + NBS[2] * NBS[1] / NM, 1]].map(([n, w]) => [n / INJ.base, w]) : [[NEAR, 1]];
  // Safety upgrades reach one block (350 ft), two blocks (660 ft) or a quarter mile (1,320 ft) from a school's grounds
  // (Bryan, 2026-10-13: "Offer three levels. One block from school, two blocks from school and quarter mile. And model
  // injuries prevented on bikes, walking and cars"). Each cuts the kids hurt within its reach by how they travelled,
  // low, central and high. Walking from Barcelona, New York City and NYC DOT's curb extensions. Biking is our judgment
  // from the pooled walking-and-biking figures (18 states 0.77, Texas 0.86), with no study of these treatments for
  // bikes alone. In a car is our judgment from leading pedestrian intervals' 0.86 on injury crashes (FHWA CMF 9911),
  // NYC DOT's 10% to 13.5% fewer occupants hurt, and beacons that may add rear-end crashes, so a real low of 0.
  // Scooters and other take biking's. Barcelona's 200 m buffer, about two blocks, is the only reach a study states.
  const XEFF = { Walking: at1("xeff_walk", [0.2, 0.4, 0.55]), Biking: at1("xeff_bike", [0, 0.25, 0.4]), "In a car": at1("xeff_car", [0, 0.12, 0.25]),
    "Scooter or other": at1("xeff_bike", [0, 0.25, 0.4]) };
  // The studies measured school-travel hours. Outside them (the rest of the 6 am to 6 pm school day) the
  // upgrades still stand, so they cut injuries by this share of the measured effect, our judgment.
  const XOFF = one("xoff", 0.5);
  const REACH = INJ.reach, XFT = [350, 660, 1320];
  if (!REACH || !XFT.every((f) => REACH[f])) throw new Error("school trips: no reach block in the injury shares; rerun tools/school-trips/school-kids-hurt.py");
  // Each reach treats only the intersections where at least one street is a main street (Bryan, 2026-10-15: "Keep all
  // intersections on big enough roads to be a problem"), and its cost scales with them. The $200,000 a school buys one
  // block's every named crossing at the average TK-8 school (intersectionsAll, k8OneBlockAll), so a reach costs its
  // main street intersections over that count: citywide each intersection once, and in the school view the school's
  // own. An intersection near two schools is paid for at both.
  const XBASE = REACH[350].intersectionsAll || REACH[350].intersections;
  const XCOST = Object.fromEntries(XFT.map((f) => [f, REACH[f] ? REACH[f].intersections / XBASE : 1]));
  const K8N = INJ.k8Counts || {}, K8N_350 = INJ.k8OneBlockAll || Object.values(K8N).reduce((t, n) => t + n[0], 0) / Math.max(1, Object.keys(K8N).length);
  const xcostAt = (cds, f) => (!K8N[cds] || !K8N_350 ? XCOST[f] : (INJ.k8OneBlockAll ? K8N[cds][XFT.indexOf(f)] : Math.max(1, K8N[cds][XFT.indexOf(f)])) / K8N_350);
  // Kids hurt within a reach that the upgrades spare, at low, central or high, by how they travelled.
  const xSpared = (f, k) => Object.fromEntries(Object.entries(REACH[f].modes).map(([m, n]) => {
    const h = (REACH[f].hours || {})[m] ?? n;
    return [m, (XEFF[m] || XEFF["Scooter or other"])[k] * (h + XOFF * (n - h))];
  }));
  const SIGNS = at1("signs_effect", [0.05, 0.1, 0.25]).map((x) => x * INJ.zoneKidsYear * INJ.zoneHours), ASSIGN_HURT = at1("assign_hurt", [0, 0.4, 1]);
  // Three speed changes on the streets near schools (Bryan, 2026-10-15: "BAD with lower speed limit, humps separately,
  // and cameras with raised limit separately too"), placed by tools/school-trips/school-speed-levers.py and counted by
  // tools/school-trips/school-kids-hurt.py (its speed block): the kids hurt on each change's own blocks or camera corridor, by the
  // school it belongs to and how they travelled. Each cuts those kids by its effect, low, central and high. None takes
  // anyone out of a car, so none changes how students get to school.
  // - Business districts: 20 mph on main street blocks with shops within a quarter mile (Vehicle Code 22358.9, AB 43).
  //   Edinburgh's 20 mph signs cut casualties 10% (95% CI 0% to 19%) on changed streets (Kokka et al. 2024), with no
  //   split by mode, so every mode takes it.
  // - Speed humps: residential blocks within a block of the grounds. FHWA's CMF 134 is 0.5 for injury crashes, standard
  //   error 0.13, so 25% to 75% at two errors. Kids walking take Oakland's odds ratio of 0.47 for children struck near
  //   home (Tester et al. 2004) as the central, and its 95% CI, 0.24 to 0.95, as the range.
  // - Speed cameras, if the state raises AB 645's cap of 33: NYC's 2022 school-zone cameras against same-corridor
  //   controls, 2021 to 2023, by mode (NYC DOT 2024 report, p. 20): pedestrians 0.874, cyclists 0.789, vehicle
  //   occupants 0.862, other motorized 1.033, so 13%, 21% and 14%, and none for scooters. No interval was published, so
  //   the low is 0 and the high is our judgment.
  const SPEED = {
    bad_district: { key: "bad", eff: { Walking: [0, 0.1, 0.19], Biking: [0, 0.1, 0.19], "In a car": [0, 0.1, 0.19], "Scooter or other": [0, 0.1, 0.19] } },
    speed_humps: { key: "humps", eff: { Walking: [0.05, 0.53, 0.76], Biking: [0.25, 0.5, 0.75], "In a car": [0.25, 0.5, 0.75], "Scooter or other": [0.25, 0.5, 0.75] } },
    speed_cameras: { key: "cameras", eff: { Walking: [0, 0.13, 0.25], Biking: [0, 0.21, 0.3], "In a car": [0, 0.14, 0.25], "Scooter or other": [0, 0, 0.1] } },
  };
  const SPEED_IDS = Object.keys(SPEED), SP = INJ.speed || {};
  // Humps overlap the calming that comes with safety upgrades, which humps and diverts the residential streets within
  // 660 ft of the schools its budget reaches. So with safety upgrades on, humps go only to the schools calming doesn't
  // reach, priced and credited there alone, and nothing is counted twice ("speed_humps_rest").
  const CALMED = new Set((P.schools || []).filter((s) => s.calmed).map((s) => s.cds));
  const spKids = (id, k, cds) => {
    const L = SPEED[id === "speed_humps_rest" ? "speed_humps" : id], kids = ((SP[L.key] || {}).kids) || {};
    const one = (m) => Object.entries(m).reduce((t, [md, n]) => t + (L.eff[md] || L.eff["Scooter or other"])[k] * n, 0) / INJ.years;
    if (cds) return kids[cds] ? one(kids[cds]) : 0;
    return Object.entries(kids).reduce((t, [c, m]) => t + (id === "speed_humps_rest" && CALMED.has(c) ? 0 : one(m)), 0);
  };
  // How many of each a school gets: business district corridors, humps, and new cameras.
  const spUnits = (id, cds) => {
    const S2 = id === "bad_district" ? (SP.bad || {}).corridors : id === "speed_cameras" ? (SP.cameras || {}).sites : (SP.humps || {}).humps;
    if (cds) return (S2 || {})[cds] || 0;
    return Object.entries(S2 || {}).reduce((t, [c, n]) => t + (id === "speed_humps_rest" && CALMED.has(c) ? 0 : n), 0);
  };
  // An assignment option part way through its rollout: the sim's set at full effect blended with today's, at the
  // share of TK-5 students under the new rules. SFUSD's new rules cover families entering TK or K, and families new to
  // the district, from 2028-29, and don't move students already enrolled (Study Session #1 deck, scope slide). Adding a
  // grade a year, weighted by grade enrollment, puts 52% of TK-5 under them in 2030-31 and all of it in 2033-34
  // (our reading of the phase-in). The sim's options only shorten TK-5 trips, so
  // blending a school's whole mix at the TK-5 share blends its TK-5 students and leaves the rest as they are.
  const ASSIGN_PHASE = { assign_ncp52: ["assign_ncp", 0.52], assign_nas52: ["assign_nas", 0.52] };
  const phaseOf = (a) => ASSIGN_PHASE[a] || [a, 1];

  const bits = (c) => BITS.map((p) => (c[p] ? 1 : 0)).join("");
  // Safer crossings bring the calmed streets, so their network is calm, or both with School Connectors.
  // c.seg is the new bikeways' budget in $M (5, 10, 20, 40 or 80), or 0 for none.
  const variant = (c) => (c.safer_crossings ? (c.connector ? "both" : "calm") : c.connector ? "connector" : "today") + (c.seg ? `_b${c.seg}` : "");
  const keyOf = (c) => `${variant(c)}|${c.assign || "today"}|${bits(c)}`;
  const TODAY = `today|today|${BITS.map(() => 0).join("")}`;
  const flip = (k, i, v) => { const [n, a, b] = k.split("|"); return `${n}|${a}|${b.slice(0, i)}${v}${b.slice(i + 1)}`; };
  if (!SETS[TODAY] || SETS[TODAY].length !== SOLO + 1) throw new Error(`school trips: city.json's sets aren't ${NC} cases of ${NS} figures and a no-parent count; rerun tools/school-trips/school-sim.py`);
  const CAR0 = SETS[TODAY][CEN * NS];
  // Each scaled change's share of its full-strength set: the central's fewer driven kids over the set's. These sets are
  // on today's network, where the three cases are the same.
  const setCars = (i) => CAR0 - SETS[flip(TODAY, i, 1)][CEN * NS];
  const T_MUNI = ((RULES.muniFar || 0) * MUNI_PTS[1] / 100 * CAR_FRAC) / setCars(MI);
  const T_BUS = BUS_CARS / setCars(BI);
  const T_POOL = POOL_SHARE * CAR0 / setCars(PI);
  const T_WB = WB_PTS / 100 * CJ.bandN[0] / setCars(WI);
  const WEIGHT = { [MI]: T_MUNI, [BI]: T_BUS, [SI]: SS_SET, [PI]: T_POOL, [WI]: T_WB };
  // Safer crossings' set is the study's 3.3 points; an assumed central blends it the same way.
  if ("xing_pts" in OV) WEIGHT[BITS.indexOf("safer_crossings")] = XING_C / 3.3;
  // A share past 1 would need more than the full-strength set, which a blend can't give.
  // A share of exactly 1 (the bus fills every seat the set holds) can come out a hair over in floating point.
  // Under P.assume a share may run from 0 past 1, extrapolating the blend in a straight line: a sensitivity run, not a figure.
  for (const [i, w] of Object.entries(WEIGHT)) {
    if (ASSUMED ? !(w >= 0) : !(w > 0 && w <= 1 + 1e-9)) throw new Error(`school trips: ${BITS[i]}'s share of its set is ${w}, outside 0 to 1`);
    WEIGHT[i] = w <= 1 + 1e-9 ? Math.min(w, 1) : w;
  }
  const W = (p) => WEIGHT[BITS.indexOf(p)] ?? 1;
  // A key with a scaled change on is a blend of the sets with it off and at full strength, weighted by its share.
  function corners(k) {
    const [n, a, b] = k.split("|"), [full, share] = phaseOf(a);
    let out = share < 1 ? [[`${n}|today|${b}`, 1 - share], [`${n}|${full}|${b}`, share]] : [[k, 1]];
    for (const [i, w] of Object.entries(WEIGHT)) {
      if (k.split("|")[2][i] !== "1") continue;
      out = out.flatMap(([kk, x]) => [[flip(kk, +i, 0), x * (1 - w)], [kk, x * w]]);
    }
    return out.filter(([, x]) => x !== 0);
  }
  const blend = (k, get) => corners(k).reduce((acc, [kk, w]) => { const v = get(kk); return acc == null ? v.map((x) => w * x) : acc.map((x, i) => x + w * v[i]); }, null);
  const row = (k) => blend(k, (kk) => SETS[kk]);
  // A set's figures under case q (0 low, 1 central, 2 high). The tally's car share moves by each band's change from
  // today, weighted as the tally weights its grades.
  function fig(k, q = CEN) {
    const x = row(k), T = SETS[TODAY], o = q * NS;
    const modes = x.slice(o, o + 6), bandCar = x.slice(o + 6, o + 6 + NB);
    let tally = CJ.tallyCar;
    CJ.bands.forEach((b, j) => { tally += CJ.tallyBandWeights[b] * 100 * (bandCar[j] - T[o + 6 + j]) / CJ.bandN[j]; });
    return { modes, tally, solo: x[SOLO], min: x[o + 6 + NB], bandCar };
  }

  const ASSIGN_R = (id) => {
    const full = phaseOf(id)[0], pts = fig(TODAY).tally - fig(`today|${full}|${BITS.map(() => 0).join("")}`).tally;
    if (!(pts > 0)) throw new Error(`school trips: ${full} moves ${pts} tally points, so its range has no central`);
    return [ASSIGN_PTS[0] / pts, 1, ASSIGN_PTS[1] / pts];
  };

  // The e-bike gate's schools, where the e-cargo month and the bike bus run, and where e-bike help reaches on today's
  // network: the schools whose bike students rise with the e-bike bit on, with their students, TK-5 students and car
  // students today. byVariant holds the same for every network (the gate passes more schools as the network grows), as
  // a bit per school in order's order with the students they hold, for e-bike help's vouchers. Built from the schools'
  // own files by ebikeGate below, since city.json doesn't list the gate's schools, and passed in as rules.gate.
  const GATE = RULES.gate;
  if (!GATE || !GATE.cds || !GATE.cds.length || !GATE.byVariant) throw new Error("school trips: no e-bike gate schools; pass rules.gate from ebikeGate (site/src/school-trips-model.mjs)");
  const IN_GATE = new Set(GATE.cds);
  // The gate on one network: its students, and whether a school is in it.
  const gateOf = (v) => GATE.byVariant[v] || { n: 0, bits: "" };
  const inGateOn = (v, cds) => { const j = GATE.order.indexOf(cds); return j >= 0 && gateOf(v).bits[j] === "1"; };
  // The cars each change applied on top of a set takes out, at low, central or high (k), given a population's car
  // students left after the set. Segments are the car students a group of these changes reaches together: each
  // change's share off its population's car share, multiplied on what's left, split back to the changes by their
  // own shares. on: the changes switched on; k5: TK-5 car students and students; gate: the gate's car students and
  // students; gk5: of the gate's car students, the TK-5 ones; schools: how many schools the gate holds.
  function postOut(on, k, k5, gate, gk5, schools) {
    const out = Object.fromEntries(on.map((id) => [id, 0]));
    if (!on.length) return out;
    const share = (id) => {
      const L = POST[id], [car, n] = L.pop === "k5" ? k5 : gate;
      if (!(car > 0)) return 0;
      return Math.min(1, id === "ecargo_month" ? schools * ECARGO_FAM * ECARGO[k] / car : L.pts[k] / 100 * n / car);
    };
    const f = Object.fromEntries(on.map((id) => [id, share(id)]));
    const seg = (car, ids) => {
      const sum = ids.reduce((t, id) => t + f[id], 0);
      if (!(car > 0) || !(sum > 0)) return;
      const gone = car * (1 - ids.reduce((t, id) => t * (1 - f[id]), 1));
      ids.forEach((id) => (out[id] += gone * f[id] / sum));
    };
    const K5 = on.filter((id) => POST[id].pop === "k5"), G = on.filter((id) => POST[id].pop === "gate");
    const g5 = Math.min(gk5, k5[0]);
    seg(k5[0] - (G.length ? g5 : 0), K5);
    if (G.length) { seg(g5, K5.concat(G)); seg(gate[0] - g5, G); }
    return out;
  }
  // A set's figures with the changes applied on top of it. Switchers walk or bike, and none is freed from their own
  // parent: 72% of bike bus kids ride with their own parent (the global survey of bike bus organizers).
  // Trip minutes aren't changed, since the set's minutes come from routed trips these changes don't have.
  function addPost(X, out, k5Out) {
    const modes = X.modes.slice();
    let tally = X.tally;
    for (const [id, n] of Object.entries(out)) { modes[0] -= n; modes[POST[id].to === "walk" ? 2 : 3] += n; }
    // The tally counts TK-5's share by its band, the rest across the older bands by their students.
    const gone = Object.values(out).reduce((t, x) => t + x, 0), rest = gone - k5Out, nOld = CJ.bandN.slice(1).reduce((t, x) => t + x, 0);
    CJ.bands.forEach((b, j) => { tally -= CJ.tallyBandWeights[b] * 100 * (j === 0 ? k5Out : rest * CJ.bandN[j] / nOld) / CJ.bandN[j]; });
    return { ...X, modes, tally, post: out };
  }
  // The City's figures for a set of changes c, under case q, with the changes on top at level k (both central by
  // default). The gate's car students left after the set are today's share of them, scaled by the set's citywide car
  // students.
  function figC(c, q = CEN, k = CEN) {
    const X = fig(keyOf(c), q), on = POST_IDS.filter((id) => c[id]);
    if (!on.length) return X;
    const gcar = GATE.car * X.modes[0] / CAR0, gk5 = GATE.n > 0 ? gcar * GATE.k5 / GATE.n : 0;
    const out = postOut(on, k, [X.bandCar[0], CJ.bandN[0]], [gcar, GATE.n], gk5, GATE.cds.length);
    // The TK-5 part: every k5 change's cars, and the gate changes' share of the TK-5 segment.
    const k5Out = on.reduce((t, id) => t + (POST[id].pop === "k5" ? out[id] : out[id] * Math.min(1, gk5 / Math.max(1e-9, gcar))), 0);
    return addPost(X, out, k5Out);
  }

  // Costs. School Street and the walking school bus go to every school with TK-5 students, safety upgrades to every TK-8
  // school with the calming budget beside them, speed limit signs to every school, connectors to the schools
  // rules.connector prices.
  const S = P.schools, hasK5 = (s) => !!(s.ranges && s.ranges["K-5"]);
  const N_K5 = S.filter(hasK5).length, N_K8 = S.filter((s) => hasK5(s) || !!(s.ranges && s.ranges["6-8"])).length;
  const N_SIGNS = S.length, K5_N = S.reduce((t, s) => t + (hasK5(s) ? s.ranges["K-5"].n || 0 : 0), 0), N_GATE = GATE.cds.length;
  for (const k of ["travelTracker", "curbRestriction", "bikeBus", "ecargoTrial", "ecargoProgram", "badCorridor", "speedHump", "speedCamera"]) if (!(COST[k] >= 0)) throw new Error(`school trips: no cost ${k}`);
  // Free Muni's fare goes to every caregiver who rides, so today's TK-5 Muni riders count too (city.json's muniK5Today,
  // from the simulation's TK-5 mode shares).
  const MUNI_K5_TODAY = CJ.muniK5Today;
  const CONN = RULES.connector || {};
  const connCost = (c, cds) => { const x = CONN[cds]; return x ? (c.school_street ? x.ss : x.full) : 0; };
  const connTotal = (c) => Object.keys(CONN).reduce((t, cds) => t + connCost(c, cds), 0);
  const muniRiders = (c) => { const k = keyOf(c), m = CEN * NS + 4; return c.caregiver_muni ? Math.max(0, row(k)[m] - row(flip(k, MI, 0))[m]) / CAR_FRAC + MUNI_K5_TODAY : 0; };
  // E-bike vouchers go to every family at the gate's schools on the set's network, the students the sim gives the
  // e-bike term at full strength, whether or not they switch (our reading; see the header).
  const ebikeFamilies = (c) => (c.ebike ? gateOf(variant(c)).n : 0);
  function cost(c) {
    const segM = c.seg ? ((CJ.segments || []).find((m) => m.budgetM === c.seg) || {}).costM || 0 : 0;
    const riders = c.yellow_bus ? BUS_RIDERS : 0, muni = muniRiders(c), eb = ebikeFamilies(c);
    const once = segM * 1e6 + (c.calm ? N_SIGNS * COST.calmPerSchool : 0) + (c.connector ? connTotal(c) : 0)
      + (c.safer_crossings ? N_K8 * COST.saferCrossings * XCOST[c.xreach || 350] + COST.calmStreets * 1e6 : 0) + (c.school_street ? N_K5 * COST.ssSetup : 0) + eb * COST.ebike
      + (c.curb_restriction ? N_K5 * COST.curbRestriction : 0)
      + (c.bad_district ? spUnits("bad_district") * COST.badCorridor : 0)
      + (c.speed_humps ? spUnits(c.safer_crossings ? "speed_humps_rest" : "speed_humps") * COST.speedHump : 0);
    const year = (c.school_street ? N_K5 * COST.schoolStreet : 0) + (c.walking_bus ? N_K5 * COST.walkingBus : 0) + riders * COST.busPerRider
      + muni * COST.muniPerRider + (c.carpool ? COST.carpool : 0) + (c.ebike ? COST.ebikeProgram : 0)
      + (c.travel_tracker ? N_K5 * COST.travelTracker : 0) + (c.bike_bus ? N_GATE * COST.bikeBus : 0)
      + (c.ecargo_month ? N_GATE * 12 * COST.ecargoTrial + COST.ecargoProgram : 0)
      + (c.speed_cameras ? spUnits("speed_cameras") * 12 * COST.speedCamera : 0);
    const st = { ss: c.school_street ? N_K5 * COST.ssStaff : 0, drv: riders / COST.busRiders, pool: c.carpool ? 0.5 : 0 };
    return { once: once / 1e6, year: year / 1e6, st, people: st.ss + st.drv + st.pool, riders, muni, eb };
  }

  // Students with a safe trip of 15 minutes. With a School Street on, its block counts as safe street.
  const svar = (c) => { const v = variant(c); return c.school_street && CJ.blocks.safe15Pct[v + "_ss"] ? v + "_ss" : v; };
  function safeN(v) {
    const B = CJ.blocks;
    return { n: B.students.reduce((t, x, i) => t + x * B.safe15Pct[v][i] / 100, 0), of: B.students.reduce((t, x) => t + x, 0) };
  }

  // Fewer kids hurt a year for one change alone, at low, central or high (k = 0, 1, 2).
  // The kids calming reaches: city.json's calming, each budget's residential-street kids a year, at the low, central and
  // high budget and effect.
  const CB = (CJ.calming || {}).budgets || {};
  const CALM_KIDS = ["5", "10", "20"].map((b, k) => ((CB[b] || {}).residentialKidsPerYear || 0) * CALM[k]);
  const segCalm = (m) => {
    const kids = (INJ.bikeways || {})[String(m)];
    if (!kids) throw new Error(`school trips: no bikeways kids for $${m}M in the injury shares; rerun tools/school-trips/school-kids-hurt.py`);
    const n = Object.values(kids).reduce((t, x) => t + x, 0) / INJ.years;
    return CALM.map((e) => e * n);
  };
  // Carpools are TK-8 only for injuries: teen-driven cars carry 4.7 times the risk per trip (TRB 2002).
  const BC0 = SETS[TODAY].slice(CEN * NS + 6, CEN * NS + 6 + NB), K8_CARS = (BC0[0] + BC0[1]) / BC0.reduce((t, x) => t + x, 0);
  // gain is one GAIN key, or { key: share } for a change whose switchers split between walking and biking.
  function hurtOne(cars, gain, k, opt = {}) {
    const f = cars / CAR0 * (gain === "pool" ? 0.5 : 1);
    const traffic = NEAR_W.reduce((t, [sh, w]) => t + (1 - Math.sqrt(Math.max(0, 1 - f * TRAFFIC[k] * w))) * sh, 0) * BELL;
    const g = typeof gain === "string" ? GAIN[gain][k] : Object.entries(gain).reduce((t, [m, w]) => t + w * GAIN[m][k], 0);
    const pax = PAX * (cars / CAR0) * g / HB;
    const sep = opt.sep ? Object.values(xSpared(opt.reach, k)).reduce((t, x) => t + x, 0) / INJ.base : 0;
    const calm = opt.sep ? CALM_KIDS[k] / HB : 0;
    const fixed = opt.fixed ? opt.fixed[k] / HB : 0;
    return HB * (1 - (1 - traffic - pax) * (1 - sep) * (1 - calm) * (1 - fixed));
  }
  const OFF = { ...Object.fromEntries(BITS.map((p) => [p, 0])), ...Object.fromEntries(POST_IDS.map((p) => [p, 0])), ...Object.fromEntries(SPEED_IDS.map((p) => [p, 0])), calm: 0, connector: 0, assign: "today", seg: 0, xreach: 350 };
  const GAIN_OF = { yellow_bus: "bus", caregiver_muni: "muni", carpool: "pool", walking_bus: "wb", ebike: "sepbike", connector: "calmbike" };
  // One change alone against today. A School Connector is counted on top of School Streets, since the plan builds both.
  // Safety upgrades at two blocks or a quarter mile are xing660 and xing1320; safer_crossings is one block.
  // Kids hurt low, central and high as the fewest and most over every pairing of car level kc and risk level kr, with
  // the central at both central, so the central always sits between.
  const hurtSpan = (h) => { const all = [0, 1, 2].flatMap((kc) => [0, 1, 2].map((kr) => h(kc, kr))); return [Math.min(...all), h(1, 1), Math.max(...all)]; };
  function alone(id) {
    if (SPEED[id] || id === "speed_humps_rest") {
      // Kids hurt only: each school's own kids on the change's blocks or corridor, at its effect.
      const rest = id === "speed_humps_rest", lever = rest ? "speed_humps" : id, L = SPEED[lever];
      const hurt = [0, 1, 2].map((k) => spKids(id, k)), base = rest ? { ...OFF, safer_crossings: 1 } : OFF;
      const kb = cost(base), kx = cost({ ...base, [lever]: 1 }), year = kx.year - kb.year;
      // Kids hurt it spares, central, by how they travelled.
      const byMode = Object.fromEntries(Object.keys(L.eff).map((m) => [m, Object.entries(((SP[L.key] || {}).kids) || {})
        .reduce((t, [c, x]) => t + (rest && CALMED.has(c) ? 0 : L.eff[m][1] * (x[m] || 0)), 0) / INJ.years]));
      return { id, cars: [0, 0, 0], free: [0, 0, 0], byMode, carHurt: [0, 0, 0], hurt, safe: 0, once: kx.once - kb.once, year, yearK: [year, year, year] };
    }
    if (POST[id]) {
      // A change applied on top of the set: its cars at each level, priced by the injury model by its switchers' mode.
      const c = { ...OFF, [id]: 1 }, cars = [0, 1, 2].map((k) => figC(c, CEN, k).post[id]);
      const kb = cost(OFF), kx = cost(c), year = kx.year - kb.year;
      const carHurt = [0, 1, 2].map((k) => hurtOne(cars[k], POST[id].to, k, {}));
      return { id, cars, free: [0, 0, 0], byMode: null, carHurt, hurt: hurtSpan((kc, kr) => hurtOne(cars[kc], POST[id].to, kr, {})), safe: 0,
        once: kx.once - kb.once, year, yearK: id === "bike_bus" ? BB_COST.map((m) => year * m) : [year, year, year] };
    }
    const base = id === "connector" ? { ...OFF, school_street: 1 } : { ...OFF };
    const c = { ...base };
    if (id.startsWith("xing")) { c.safer_crossings = 1; c.xreach = Number(id.slice(4)); id = "safer_crossings"; }
    if (id.startsWith("assign")) c.assign = id; else if (id.startsWith("seg")) c.seg = Number(id.slice(3)); else c[id] = 1;
    const T = fig(keyOf(base)), X = fig(keyOf(c));
    const mid = T.modes[0] - X.modes[0], free = (X.solo || 0) - (T.solo || 0);
    // The cars a change takes out under each case, low, central and high, read from the sim's sets.
    const byCase = (k0, k1) => [0, 1, 2].map((q) => fig(k0, q).modes[0] - fig(k1, q).modes[0]);
    let cars = [mid, mid, mid], fr = [free, free, free];
    const scale = (xs) => { cars = xs.map((x) => mid * x); fr = xs.map((x) => free * x); };
    // A street change, and e-bike help, whose term the sim puts on the bike choice: the three cases.
    if (id === "connector" || id.startsWith("seg") || id === "ebike") cars = byCase(keyOf(base), keyOf(c));
    else if (id === "safer_crossings") {
      // The study's walking and biking gain, read on today's network (the same set with the calmed streets left out,
      // where the cases agree) and scaled to its low and high, plus the kids who bike once the calmed streets count as
      // safe, under each case. The calmed streets free no parent, so the freed parents scale with the study's gain.
      const kG = `${variant({ ...c, safer_crossings: 0 })}|${c.assign || "today"}|${bits(c)}`, net = byCase(kG, keyOf(c));
      const gainOnly = T.modes[0] - fig(kG).modes[0];
      cars = XING.map((x, k) => gainOnly * x + net[k]);
      fr = XING.map((x) => free * x);
    } else if (id === "school_street") scale(SS);
    else if (id === "caregiver_muni") { cars = MUNI_PTS.map((p) => (RULES.muniFar || 0) * p / 100 * CAR_FRAC); fr = MUNI_PTS.map((p) => free * p / MUNI_PTS[1]); }
    else if (id === "yellow_bus") {
      // The blend is weighted to the 310 fewer driven kids, so it may seat fewer than 640. Every rider needs no parent,
      // so the freed parents are scaled up to the 640 riders.
      scale(BUS_PTS);
      fr = fr.map((x) => x * BUS_RIDERS / (T_BUS * BUS_SEATS));
    }
    else if (id === "carpool") scale(POOL);
    else if (id === "walking_bus") scale(WB);
    else if (id.startsWith("assign")) scale(ASSIGN_R(id));
    else if (id === "calm") cars = [0, 0, 0];
    // School Streets and safer crossings move kids to walking and biking, split as the set's own walking and biking
    // rise. The bikers ride ordinary streets past a School Street and calmed streets with safer crossings.
    const dW = Math.max(0, X.modes[2] - T.modes[2]), dB = Math.max(0, X.modes[3] - T.modes[3]);
    const segSep = id.startsWith("seg") ? ((CJ.segments || []).find((m) => m.budgetM === Number(id.slice(3))) || {}).separatedShare : null;
    if (id.startsWith("seg") && segSep == null) throw new Error(`school trips: no separatedShare for ${id} in city.json's segments`);
    const gain = GAIN_OF[id] || (id.startsWith("seg") ? { track: segSep, calmbike: 1 - segSep }
      : ["school_street", "safer_crossings"].includes(id) && dW + dB > 0
        ? { walk: dW / (dW + dB), [id === "safer_crossings" ? "calmbike" : "bike"]: dB / (dW + dB) } : "none");
    const opt = { sep: id === "safer_crossings", reach: c.xreach || 350, fixed: id === "calm" ? SIGNS : id.startsWith("assign") ? ASSIGN_HURT.map((x) => x * phaseOf(id)[1])
      : id.startsWith("seg") ? segCalm(Number(id.slice(3))) : null };
    // Assignment's injury figure is its own estimate, so its cars add nothing on top; carpools count TK-8 only.
    const hurtCars = (k) => (id.startsWith("assign") ? 0 : id === "carpool" ? cars[k] * K8_CARS : cars[k]);
    const kb = cost(base), kx = cost(c), year = kx.year - kb.year;
    // A yearly cost that scales with riders (free Muni's new riders, the shuttle loops) moves with them.
    const fixedYear = id === "caregiver_muni" ? MUNI_K5_TODAY * COST.muniPerRider / 1e6 : 0;
    const yearK = ["caregiver_muni", "yellow_bus"].includes(id) && cars[1] > 0 ? cars.map((x) => fixedYear + (year - fixedYear) * x / cars[1]) : [year, year, year];
    // Kids hurt the upgrades' own cut spares, central, by how they travelled.
    const byMode = opt.sep ? Object.fromEntries(Object.entries(xSpared(opt.reach, 1)).map(([m, x]) => [m, x / INJ.years])) : null;
    // The injury cut that comes from fewer cars alone, so a plan can credit a school with its own cars' share.
    const carHurt = [0, 1, 2].map((k) => hurtOne(hurtCars(k), gain, k, {}));
    return { id, cars, free: fr, byMode, carHurt, hurt: id === "ebike" || id === "connector" || id.startsWith("seg") ? hurtSpan((kc, kr) => hurtOne(hurtCars(kc), gain, kr, opt)) : [0, 1, 2].map((k) => hurtOne(hurtCars(k), gain, k, opt)),
      safe: safeN(svar(c)).n - safeN(svar(base)).n, once: kx.once - kb.once, year, yearK };
  }
  // The changes switched on in a set, each as alone() names it.
  const onIds = (c) => BITS.filter((p) => c[p]).map((p) => (p === "safer_crossings" && c.xreach && c.xreach !== 350 ? `xing${c.xreach}` : p)).concat(c.calm ? ["calm"] : [], c.connector ? ["connector"] : [],
    c.seg ? [`seg${c.seg}`] : [], c.assign && c.assign !== "today" ? [c.assign] : [], POST_IDS.filter((id) => c[id]),
    SPEED_IDS.filter((id) => c[id]).map((id) => (id === "speed_humps" && c.safer_crossings ? "speed_humps_rest" : id)));
  // Fewer kids hurt a year with a set of changes: each change's own central cut, multiplied together.
  const hurt = (c) => HB * (1 - onIds(c).reduce((t, id) => t * (1 - alone(id).hurt[1] / HB), 1));

  // Low and high for a set of changes: the central total plus each change's own move to its low or high, and the
  // injury cut multiplied from each change's low or high, as the comment does for all ten together.
  function range(c) {
    const T = fig(TODAY), X = figC(c), k = cost(c), mid = T.modes[0] - X.modes[0];
    const out = { cars: [mid, mid], year: [k.year, k.year], hurt: [1, 1] };
    for (const id of onIds(c)) {
      const a = alone(id);
      [0, 2].forEach((q, j) => {
        out.cars[j] += a.cars[q] - a.cars[1];
        out.year[j] += a.yearK[q] - a.yearK[1];
        out.hurt[j] *= 1 - a.hurt[q] / HB;
      });
    }
    return { cars: [Math.max(0, out.cars[0]), Math.min(CAR0, out.cars[1])], year: out.year.map((x) => Math.max(0, x)), hurt: out.hurt.map((x) => HB * (1 - x)) };
  }
  // One school's figures for a set of changes under case q, from its own file's city block (tools/school-trips/school-sim.py,
  // school_city): its mix on today's network per assignment|programs key, and per full key its family-car and bike
  // students and total trip minutes under each case, and the students whose trip needs no parent. Key orders are
  // city.json's, sorted.
  let KIX = null;
  function keyIx() {
    if (!KIX) {
      const full = Object.keys(SETS).sort(), ab = [...new Set(full.map((k) => k.slice(k.indexOf("|") + 1)))].sort();
      KIX = { full: Object.fromEntries(full.map((k, i) => [k, i])), ab: Object.fromEntries(ab.map((k, i) => [k, i])) };
    }
    return KIX;
  }
  function schoolFig(C, cds, key, q = CEN, v) {
    const K = keyIx(), ab = (k) => K.ab[k.slice(k.indexOf("|") + 1)], cs = corners(key);
    // Free Muni and the shuttle loops blend the sets at full strength and without, as the City's totals do.
    const at = (a) => cs.reduce((t, [kk, w]) => t + w * a[K.full[kk]][q], 0), at1 = (a) => cs.reduce((t, [kk, w]) => t + w * a[K.full[kk]], 0);
    const m = cs.reduce((acc, [kk, w]) => acc.map((x, i) => x + w * C.mix[ab(kk)][i]), C.mix[ab(cs[0][0])].map(() => 0));
    const N = m.reduce((t, x) => t + x, 0);
    // The car and bike students are the file's own for this network and case. The other modes are the mix on today's
    // network scaled to the students left, as the sim's bike shift scales every other mode in proportion: close, not
    // exact, where a school's cells move by different amounts.
    const car = at(C.car), bike = at(C.bike), rest0 = N - m[0] - m[3], f = rest0 > 1e-9 ? Math.max(0, N - car - bike) / rest0 : 1;
    const modes = m.map((x, i) => (i === 0 ? car : i === 3 ? bike : x * f));
    const SJ = CJ.schools, j = SJ && SJ.cds ? SJ.cds.indexOf(cds) : -1;
    return { modes, min: C.min ? at(C.min) : null, alone: at1(C.solo), safe: j >= 0 && v && SJ.safe15Pct[v] ? N * SJ.safe15Pct[v][j] / 100 : null, N };
  }
  // One school's figures for a set of changes c, with the changes applied on top of the set. Its TK-5 car students
  // are its car students in proportion to its TK-5 students, since a school's file doesn't split its mix by grade.
  const BY_CDS = Object.fromEntries(S.filter((s) => s.cds).map((s) => [s.cds, s]));
  function schoolFigC(C, cds, c, q = CEN, k = CEN) {
    const X = schoolFig(C, cds, keyOf(c), q, svar(c)), s = BY_CDS[cds] || {}, gate = IN_GATE.has(cds);
    const on = POST_IDS.filter((id) => c[id] && (POST[id].pop === "k5" ? hasK5(s) : gate));
    if (!on.length) return X;
    const car = Math.max(0, X.modes[0]), N = X.N, n5 = hasK5(s) ? Math.min(N, s.ranges["K-5"].n || 0) : 0, car5 = N > 0 ? car * n5 / N : 0;
    const out = postOut(on, k, [car5, n5], gate ? [car, N] : [0, 0], gate ? car5 : 0, 1);
    return addPost(X, out, 0);
  }
  // What one school's share of a set of changes costs, as the City prices it. New bikeways, carpool matching and the
  // e-bike program's yearly cost are citywide and not split by school. fig is schoolFig's with the set on, without(p)
  // its figure with change p off.
  function schoolCost(s, c, X, without) {
    const k5 = hasK5(s), k8 = k5 || !!(s.ranges && s.ranges["6-8"]);
    // New Muni riders, counting the ones who left a carpool or a bike as well as a single-family car.
    const muni = c.caregiver_muni ? Math.max(0, X.modes[4] - without("caregiver_muni").modes[4]) / CAR_FRAC : 0;
    // Vouchers go to every family at the school when it passes the e-bike gate on the set's network, as cost() counts.
    const ebk = c.ebike && inGateOn(variant(c), s.cds) ? X.N : 0;
    const gate = IN_GATE.has(s.cds), bb = c.bike_bus && gate, ec = c.ecargo_month && gate;
    // The bus blend is weighted to its fewer driven kids, so it seats fewer than it pays for; riders are scaled up to
    // the seats paid for, as cost() pays for all 1,520.
    // Riders are the loop's own, over the school's share of today's riders, which the mode chart carries too.
    const riders = c.yellow_bus ? Math.max(0, X.modes[5] - without("yellow_bus").modes[5]) * BUS_RIDERS / (T_BUS * BUS_SEATS) : 0;
    const conn = c.connector ? connCost(c, s.cds) / 1e6 : 0;
    // Calming is citywide, so a school's share is its own calmed miles at the calming rate.
    const calmM = c.safer_crossings ? (s.calmFt || 0) / 5280 * COST.connectorCalm : 0;
    const xing = c.safer_crossings && k8 ? COST.saferCrossings * xcostAt(s.cds, c.xreach || 350) / 1e6 : 0;
    // The speed changes: the school's own corridors and humps (none where calming already reaches, with safety
    // upgrades on), and its new camera's monthly fee.
    const badN = c.bad_district ? spUnits("bad_district", s.cds) : 0;
    const humpN = c.speed_humps && !(c.safer_crossings && s.calmed) ? spUnits("speed_humps", s.cds) : 0;
    const camN = c.speed_cameras ? spUnits("speed_cameras", s.cds) : 0;
    const once = (c.calm ? COST.calmPerSchool / 1e6 : 0) + conn + xing + calmM + (c.school_street && k5 ? COST.ssSetup / 1e6 : 0) + ebk * COST.ebike / 1e6
      + (c.curb_restriction && k5 ? COST.curbRestriction / 1e6 : 0) + (badN * COST.badCorridor + humpN * COST.speedHump) / 1e6;
    // Free Muni's fare also goes to the school's share of today's TK-5 riders, as the City's cost counts them.
    const muniToday = c.caregiver_muni && k5 && K5_N ? MUNI_K5_TODAY * s.ranges["K-5"].n / K5_N : 0;
    // The e-cargo month's trials are the school's; its staff are citywide, as the e-bike program's are.
    const year = ((c.school_street && k5 ? COST.schoolStreet : 0) + (c.walking_bus && k5 ? COST.walkingBus : 0) + riders * COST.busPerRider + (muni + muniToday) * COST.muniPerRider
      + (c.travel_tracker && k5 ? COST.travelTracker : 0) + (bb ? COST.bikeBus : 0) + (ec ? 12 * COST.ecargoTrial : 0) + camN * 12 * COST.speedCamera) / 1e6;
    const people = (c.school_street && k5 ? COST.ssStaff : 0) + riders / COST.busRiders;
    return { once, year, people, muni, muniToday, ebk, riders, conn, calmM, xing, k5, k8, bb, ec, gate, badN, humpN, camN };
  }
  // One school's kids hurt a year that its own safety upgrades, calmed streets and speed limit signs spare, at low,
  // central or high (k = 0, 1, 2), from site/data/school-kids-hurt.json's schoolKids: the upgrades at its reach on the
  // kids hurt nearest it, the calming on its share of the calmed miles, the signs on the kids hurt in its own zone.
  const SK = INJ.schoolKids || {};
  const CALM_FT = S.reduce((t, s) => t + (s.calmed ? s.calmFt || 0 : 0), 0);
  function schoolSafety(s, c, k) {
    const x = SK[s.cds] || {}, out = { xing: 0, calmed: 0, signs: 0, bad: 0, humps: 0, cameras: 0 };
    if (c.bad_district) out.bad = spKids("bad_district", k, s.cds);
    if (c.speed_humps && !(c.safer_crossings && s.calmed)) out.humps = spKids("speed_humps", k, s.cds);
    if (c.speed_cameras) out.cameras = spKids("speed_cameras", k, s.cds);
    if (c.safer_crossings && x.reach) {
      for (const [m, [h, n]] of Object.entries(x.reach[c.xreach || 350] || {})) out.xing += (XEFF[m] || XEFF["Scooter or other"])[k] * (h + XOFF * (n - h)) / INJ.years;
      out.calmed = s.calmed && CALM_FT ? CALM_KIDS[k] * (s.calmFt || 0) / CALM_FT : 0;
    }
    // SIGNS is the citywide cut, its kids in the zone hours spread by each school's own count.
    if (c.calm && INJ.zone) out.signs = SIGNS[k] * (x.zone || 0) / (INJ.zone * INJ.zoneHours);
    return out;
  }
  return { CASES, CEN, gateOf, inGateOn, segCalm, ASSIGN_PHASE, phaseOf, range, keyOf, schoolFig, schoolFigC, figC, POST_IDS, GATE, IN_GATE, N_GATE, schoolCost, schoolSafety, CALM_KIDS, SIGNS, ASSIGN_HURT, variant, svar, corners, row, fig, cost, safeN, alone, hurt, onIds, TODAY, CAR0, HB, T_MUNI, T_BUS, W, CAR_FRAC,
    N_K5, N_K8, N_SIGNS, BUS_RIDERS, MUNI_K5_TODAY, connCost, OFF, XCOST, XEFF, XOFF, REACH, xcostAt, SPEED, SPEED_IDS, spUnits, spKids };
}

// The e-bike gate's schools, for makeCityModel's rules.gate, from city.json and each school's own file's city block
// (files: cds -> that block). A school is in the gate on a network when its bike students rise, in the central case,
// with only the e-bike bit switched on, at today's assignment: the sim gives the e-bike term only at schools passing
// its gate on that network (tools/school-trips/school-sim.py, ebike_gate), so the rise marks the gate. schools: the page's
// school list, for TK-5 students. Run at build time, never in the browser.
export function ebikeGate(CJ, files, schools) {
  const SJ = CJ.schools, full = Object.keys(CJ.sets).sort(), ix = Object.fromEntries(full.map((k, i) => [k, i]));
  const cen = (CJ.cases || ["low", "central", "high"]).indexOf(CJ.mapCase || "central"), EI = CJ.programs.indexOf("ebike");
  const off = CJ.programs.map(() => "0").join(""), on = CJ.programs.map((p, i) => (i === EI ? "1" : "0")).join("");
  const k5 = Object.fromEntries((schools || []).map((s) => [s.cds, ((s.ranges || {})["K-5"] || {}).n || 0]));
  const byVariant = {};
  for (const v of CJ.variants) {
    const i0 = ix[`${v}|today|${off}`], i1 = ix[`${v}|today|${on}`];
    const js = SJ.cds.map((c, j) => j).filter((j) => { const C = files[SJ.cds[j]]; return C && C.bike[i1][cen] - C.bike[i0][cen] > 1e-6; });
    const inj = new Set(js);
    byVariant[v] = { n: Math.round(js.reduce((t, j) => t + SJ.students[j], 0) * 10) / 10, bits: SJ.cds.map((c, j) => (inj.has(j) ? "1" : "0")).join("") };
  }
  const t = byVariant.today, js = SJ.cds.map((c, j) => j).filter((j) => t.bits[j] === "1"), car = SJ.car[`today|${off}`];
  return { order: SJ.cds, cds: js.map((j) => SJ.cds[j]), n: t.n, k5: js.reduce((s, j) => s + (k5[SJ.cds[j]] || 0), 0),
    car: js.reduce((s, j) => s + car[j], 0), byVariant };
}

// ebikeGate over the school files beside city.json in dir (site/data/school-sim), read once per process.
const GATE_MEMO = new Map();
export function readEbikeGate(dir, CJ, schools) {
  if (GATE_MEMO.has(dir)) return GATE_MEMO.get(dir);
  const files = {};
  for (const cds of CJ.schools.cds) {
    const f = nodePath.join(dir, `${cds}.json`);
    if (fs.existsSync(f)) files[cds] = JSON.parse(fs.readFileSync(f, "utf8")).city;
  }
  const g = ebikeGate(CJ, files, schools);
  GATE_MEMO.set(dir, g);
  return g;
}
