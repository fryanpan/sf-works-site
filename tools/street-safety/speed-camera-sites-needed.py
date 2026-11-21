#!/usr/bin/env python3
"""How many speed camera locations each trial design needs for 80% power to detect a 13%, 15%, 20% or 30% injury drop against matched controls.

    uv run --no-project --with numpy --with scipy python tools/street-safety/speed-camera-sites-needed.py

Prints markdown tables; writes no file. The write-up is
research/speed-cameras-2026-10/2026-11-01-sites-needed.md.

INPUTS, all already in the repo, nothing fetched:
  data/extract/speed-cameras/camera-injuries.json  per-location injury counts (site plus two blocks, and the
      "ring" of blocks 3 to 8 hops out) before and after each of the 33 camera locations started, built by
      scratch/hin-map/hin_split.py from DataSF nwes-mmgh (victims fetched 2026-10-20, data to 2026-08-31).
  The cached nwes-mmgh query hin_split.py uses (data/socrata-cache/, read only; the script stops if it is missing).
  data/extract/access/hin-2022.json  SFMTA's 2022 High Injury Network centerline.
  site/data/school-sim/index.json  the 113 school points the School Trips tool draws.

COUNTING. A location is one system under Vehicle Code §22425, the way SFMTA counts its 56 cameras at 33
locations as 33 systems. A corridor is 4 locations, a
school zone 3, and one mobile system serves 4 locations.

METHOD.
 1. Site-to-site overdispersion. For each location, y = log((after+0.5)/(before+0.5)), with variance
    v = phi * (1/(after+0.5) + 1/(before+0.5)), where phi = sum(n^2)/sum(n) over crashes is the inflation from
    several victims in one crash. tau^2, the variance of the true change from one location to the next beyond that,
    is estimated two ways, DerSimonian-Laird and REML, with a Q-profile 95% upper bound, for the two-block counts and
    the ring counts, by group. Only the all-injury group has counts enough to show tau^2 above zero under DL, and REML
    puts it at zero; no check in this data can choose between them, so every result is shown at both and at the upper
    bound. The all-injury value is used for every group, treated and control alike.
    CV^2 of the true per-place rates enters because the pooled ratio weights big units more: tau^2 counts (1 + CV^2)
    times. It is computed separately for each pool (camera locations, HIN blocks, schools) from the 660 ft radius
    counts, all injuries: (variance - phi * mean) / mean^2.
 2. Injury rate per unit. Today's two-block rate per location-year is the deduplicated count averaged over the
    window before the cameras and the one before that (646/682 all, 57/53 KSI, 102/115 pedestrians, from
    notes/speed-cameras-2026-10/2026-10-31-severe-injuries.md), which takes some of the bad-stretch bump out. A new
    design's rate is that times the ratio of its candidate places' mean 660 ft radius count to the 33 locations',
    over 2021-09-01 to 2025-03-31, which ends before the first camera started. Candidate places: every HIN block
    midpoint more than 660 ft from a current camera (corridors, mobile), or every school point (school zones). The
    upper half of each pool is a sensitivity.
 3. Units and clustering. A unit is whatever shares one random change: a corridor (4 locations, catchment 2.0x one
    location's two blocks; 3 and 2 locations, catchment (n + 2) / 3, as a sensitivity because HIN streets are short), a school zone (3 locations, catchment 1.5x), or a mobile location (one system rotates over
    4 locations, each its own unit). A fixed single location like today's is shown for reference. Mobile is run at the
    full drop and at half of it, the UK ratio of mobile to fixed (28% against 51% for KSI).
 4. Sample size. Each treated unit gets k matched control units (k = 1, and 3 as a sensitivity) with the same
    expected count and tau^2. Windows: 18 months each side, 3 years each side, and 3 years before with 18 months
    after. The estimate is the log ratio of ratios. With mb, ma the expected counts before and after,
    Var per treated unit = (1+CV^2) tau^2 + phi (1/mb + 1/(ma (1-d))); per control (1+CV^2) tau^2 + phi (1/mb + 1/ma).
    Units N = (z_.975 + z_.80)^2 (V_t + V_c/k) / log(1-d)^2. Systems = N x locations per unit (mobile: N / 4).
    School zones draw treated and control schools from one pool of 113 (57 for the worse half); a cell where
    N (1 + k) exceeds the pool is marked. With k = 3, school zones take the most controls the pool allows.
 5. Checks: the sample-size formula against a Monte Carlo simulation under the same model, with a cluster-robust
    standard error; and the model's standard error for today's 33 locations against the published pedestrian
    interval, which tests the Poisson/phi term only, since that interval is a bootstrap over crashes.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import datetime, json, math, os, sys

import numpy as np
from scipy import stats, optimize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata

GROUPS = ("all", "severe", "ped")
NAMES = {"all": "All injuries", "severe": "Killed or severely injured", "ped": "Pedestrians, all severities"}
# Deduplicated two-block counts at the 33 locations: (window before the before window, before window).
# From notes/speed-cameras-2026-10/2026-10-31-severe-injuries.md, section 1, placebo column.
PRE_BEFORE = {"all": (646, 682), "severe": (57, 53), "ped": (102, 115)}
RADIUS_FT = 660
WIN = (datetime.date(2021, 9, 1), datetime.date(2025, 3, 31))   # ends before the first camera (2025-03-20 go-live, data from 04-01)
EFFECTS = (0.13, 0.15, 0.20, 0.30)   # 0.13 is SF's own all-injury result, 0.87 (0.75-1.00); the rest are assumed
WINDOWS = ((1.5, 1.5, "18 mo each side"), (3.0, 3.0, "3 y each side"), (3.0, 1.5, "3 y before, 18 mo after"))
K = 1                      # matched controls per treated unit
Z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
SCHOOL_POOL = 113
FT_LAT = 364000.0
FT_LON = FT_LAT * math.cos(math.radians(37.76))
MOBILE_SHARE = 0.5         # half-effect row: UK mobile 28% vs fixed 51% KSI drop (PA Consulting and UCL 2004)
# design: (locations per unit, catchment as a multiple of one location's two blocks, units per system, rate pool,
#          share of the fixed-camera drop the design gets)
DESIGNS = {
    "Corridor (4 locations, ~10 blocks)": (4, 2.0, 1, "hin", 1.0),
    "School zone (3 locations round one school)": (3, 1.5, 1, "school", 1.0),
    "Mobile, full drop (1 system over 4 locations)": (1, 1.0, 4, "hin", 1.0),
    "Mobile, half drop (1 system over 4 locations)": (1, 1.0, 4, "hin", MOBILE_SHARE),
    "Reference: one fixed location like today's": (1, 1.0, 1, "camera", 1.0),
    # shorter corridors: catchment (n + 2) / 3, so 4 locations two blocks apart = 2.0, 3 = 1.67, 2 = 1.33
    "Corridor (3 locations, ~8 blocks)": (3, 5 / 3, 1, "hin", 1.0),
    "Corridor (2 locations, ~7 blocks)": (2, 4 / 3, 1, "hin", 1.0),
}
CORR, SCH, MOB_FULL, MOB_HALF, REF, CORR3, CORR2 = DESIGNS


def dl(y, v):
    w = 1 / v
    mu = (w * y).sum() / w.sum()
    q = (w * (y - mu) ** 2).sum()
    df = len(y) - 1
    tau2 = max(0.0, (q - df) / (w.sum() - (w ** 2).sum() / w.sum()))

    def qgen(t):
        ww = 1 / (v + t)
        m = (ww * y).sum() / ww.sum()
        return (ww * (y - m) ** 2).sum()
    crit = stats.chi2.ppf(0.025, df)     # upper bound of tau^2: Q_gen(tau^2) = lower chi-square quantile
    hi = 0.0 if qgen(0) < crit else optimize.brentq(lambda t: qgen(t) - crit, 0, 50)
    return tau2, hi, q, df


def reml(y, v):
    def nll(t):
        w = 1 / (v + t)
        m = (w * y).sum() / w.sum()
        return 0.5 * (np.log(v + t).sum() + math.log(w.sum()) + (w * (y - m) ** 2).sum())
    r = optimize.minimize_scalar(nll, bounds=(0.0, 10.0), method="bounded", options={"xatol": 1e-8})
    t = float(r.x)
    return 0.0 if nll(0.0) <= nll(t) or t < 1e-6 else t


def overdispersion(rows, phi):
    out = {}
    for place in ("near", "ring"):
        for g in GROUPS:
            b = np.array([r[place]["groups"][g]["before"] for r in rows], float)
            a = np.array([r[place]["groups"][g]["after"] for r in rows], float)
            y = np.log((a + 0.5) / (b + 0.5))
            v = phi[g] * (1 / (a + 0.5) + 1 / (b + 0.5))
            t2, hi, q, df = dl(y, v)
            out[place, g] = (t2, reml(y, v), hi, q, df, b.sum(), a.sum())
    return out


def victims():
    sel = ("case_id_pkey,victim_id,victim_age,victim_degree_of_injury,victim_role,collision_datetime,"
           "collision_time,tb_latitude,tb_longitude,primary_rd,secondary_rd,intersection,distance,ped_action,"
           "street_of_travel,move_pre_acc,party_type,party_number_ckey,type_of_collision,vz_pcf_code")
    path = sfdata.CACHE_ROOT / ("%s.json" % sfdata._key("nwes-mmgh", {"$select": sel, "$order": ":id"}))
    if not path.exists():
        sys.exit("cached nwes-mmgh query missing (%s); run scratch/hin-map/hin_split.py first" % path)
    V = sfdata.fetch("nwes-mmgh", select=sel, floor=80000)
    pts = {g: [] for g in GROUPS}
    per_crash = {g: {} for g in GROUPS}
    for v in V.rows:
        deg = v.get("victim_degree_of_injury")
        if deg in (None, "No Injury"):
            continue
        try:
            la, lo = float(v["tb_latitude"]), float(v["tb_longitude"])
            d = datetime.date.fromisoformat((v.get("collision_datetime") or "")[:10])
        except (KeyError, TypeError, ValueError):
            continue
        if not (37.6 < la < 37.85 and -122.53 < lo < -122.35) or not WIN[0] <= d <= WIN[1]:
            continue
        case = v.get("case_id_pkey")
        for g, keep in (("all", True), ("severe", deg in ("Severe Injury", "Fatal Injury")),
                        ("ped", v.get("victim_role") == "Pedestrian")):
            if keep:
                pts[g].append((lo, la))
                per_crash[g][case] = per_crash[g].get(case, 0) + 1
    # victims per crash inflate the variance of a victim count by phi = sum(n^2) / sum(n) over crashes
    phi = {g: sum(n * n for n in c.values()) / sum(c.values()) for g, c in per_crash.items()}
    return {g: np.array(p) for g, p in pts.items()}, phi, V.fetched_on


def sq_dist(c, p):
    dx = (c[:, None, 0] - p[None, :, 0]) * FT_LON
    dy = (c[:, None, 1] - p[None, :, 1]) * FT_LAT
    return dx * dx + dy * dy


def radius_counts(centres, p):
    c = np.asarray(centres)
    out = np.zeros(len(c))
    for i in range(0, len(c), 200):
        out[i:i + 200] = (sq_dist(c[i:i + 200], p) <= RADIUS_FT ** 2).sum(1)
    return out


def n_units(rate, tb, ta, tau2, d, phi, cv2, k=K):
    # the pooled ratio weights units by size, so tau^2 counts (1 + cv2) times
    mb, ma = rate * tb, rate * ta
    vt = (1 + cv2) * tau2 + phi * (1 / mb + 1 / (ma * (1 - d)))
    vc = (1 + cv2) * tau2 + phi * (1 / mb + 1 / ma)
    return Z ** 2 * (vt + vc / k) / math.log(1 - d) ** 2


def school_constrained(rate, tb, ta, tau2, d, phi, cv2, k, pool_n):
    """Smallest N treated schools, with min(k, (pool - N) / N) controls each, that reaches 80% power; None if none."""
    for n in range(1, pool_n):
        ke = min(k, (pool_n - n) / n)
        if n_units(rate, tb, ta, tau2, d, phi, cv2, ke) <= n:
            return n, ke
    return None


def simulate(n, mu, tau2, d, phi, cv2, k=K, reps=4000, seed=1):
    rng = np.random.default_rng(seed)
    n = int(math.ceil(n))
    nc = n * k
    hits = 0
    for _ in range(reps):
        # site rates vary (gamma with CV^2 cv2) and cancel within site; the change carries tau^2;
        # counts come in lumps of phi victims so their variance is phi times the mean
        sh = 1 / cv2 if cv2 > 0 else 1e6
        lam_t = mu * rng.gamma(sh, 1 / sh, n)
        lam_c = mu * rng.gamma(sh, 1 / sh, nc)
        pois = lambda lam: phi * rng.poisson(lam / phi)
        bt = pois(lam_t)
        at = pois(lam_t * (1 - d) * np.exp(rng.normal(-tau2 / 2, math.sqrt(tau2), n)))
        bc = pois(lam_c)
        ac = pois(lam_c * np.exp(rng.normal(-tau2 / 2, math.sqrt(tau2), nc)))
        A, B, C, D_ = at.sum(), bt.sum(), ac.sum(), bc.sum()
        if min(A, B, C, D_) == 0:
            continue
        est = math.log(A / B) - math.log(C / D_)
        vt = ((at / A - bt / B) ** 2).sum() * n / (n - 1)
        vc = ((ac / C - bc / D_) ** 2).sum() * nc / (nc - 1)
        hits += abs(est) / math.sqrt(vt + vc) > 1.96
    return hits / reps


def main():
    data = json.load(open(os.path.join(ROOT, "data", "extract", "speed-cameras", "camera-injuries.json")))
    rows = data["rows"]
    assert len(rows) == 33, len(rows)
    P, phi, fetched = victims()
    assert all(len(P[g]) > 100 for g in GROUPS)
    print("Victims per crash, phi = sum(n^2)/sum(n), %s to %s: %s\n"
          % (WIN[0], WIN[1], ", ".join("%s %.2f" % (g, phi[g]) for g in GROUPS)))
    od = overdispersion(rows, phi)
    print("## Overdispersion: tau^2 of the log change across the 33 locations (Poisson variance x phi)\n")
    print("| Group | Area | Before → after (summed) | Q (df 32) | tau^2 DL | tau^2 REML | 95% upper (Q-profile) |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for (place, g), (t2, t2r, hi, q, df, b, a) in od.items():
        print("| %s | %s | %d → %d | %.1f | %.3f | %.3f | %.3f |" % (NAMES[g], "two blocks" if place == "near" else "ring (3-8 hops)",
                                                               b, a, q, t2, t2r, hi))

    years = float(np.mean([r["years"] for r in rows]))
    rate_cam = {g: (sum(PRE_BEFORE[g]) / 2) / 33 / years for g in GROUPS}
    print("\nMean window %.2f years. Two-block injuries per location-year (avg of two pre-camera windows): %s\n"
          % (years, ", ".join("%s %.2f" % (g, rate_cam[g]) for g in GROUPS)))

    cams = [(r["lon"], r["lat"]) for r in rows]
    hin = json.load(open(os.path.join(ROOT, "data", "extract", "access", "hin-2022.json")))["records"]
    hin_all = np.array([tuple(np.mean(np.array(h["pts"]), 0)) for h in hin if len(h.get("pts") or []) >= 2])
    near_cam = (sq_dist(hin_all, np.array(cams)) <= RADIUS_FT ** 2).any(1)
    hin_mid = hin_all[~near_cam]
    sch = json.load(open(os.path.join(ROOT, "site", "data", "school-sim", "index.json")))["schools"]
    sch_pts = [(s["lon"], s["lat"]) for s in sch]
    assert len(sch_pts) == SCHOOL_POOL, len(sch_pts)
    pools = {"camera": cams, "hin": hin_mid, "school": sch_pts}
    counts = {(k, g): np.sort(radius_counts(c, P[g])) for k, c in pools.items() for g in GROUPS}
    factor, upf = {g: {} for g in GROUPS}, {g: {} for g in GROUPS}
    print("## Rate factor: 660 ft radius counts, %s to %s (victims fetched %s)\n" % (WIN[0], WIN[1], fetched))
    print("HIN blocks: %d midpoints, %d within 660 ft of a current camera dropped, %d left.\n"
          % (len(hin_all), near_cam.sum(), len(hin_mid)))
    print("| Group | 33 camera locations | HIN blocks, all (n=%d) | HIN blocks, upper half | Schools, all (n=%d) | Schools, upper half | HIN factor (all) | School factor (all) |"
          % (len(hin_mid), len(sch_pts)))
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for g in GROUPS:
        m, up = {}, {}
        for k in pools:
            x = counts[k, g]
            m[k], up[k] = x.mean(), x[len(x) // 2:].mean()
        factor[g] = {k: m[k] / m["camera"] for k in m}
        upf[g] = {k: up[k] / m["camera"] for k in m}
        print("| %s | %.1f | %.1f | %.1f | %.1f | %.1f | %.2f | %.2f |" % (NAMES[g], m["camera"], m["hin"], up["hin"], m["school"], up["school"],
                                                                factor[g]["hin"], factor[g]["school"]))
    pool_n = {"whole pool": SCHOOL_POOL, "worse half": SCHOOL_POOL - SCHOOL_POOL // 2}

    # CV^2 of true per-place rates, per pool, from the all-injury radius counts net of the phi-inflated count noise
    cv2 = {}
    for k in pools:
        x = counts[k, "all"]
        cv2[k] = max(0.0, (x.var(ddof=1) - phi["all"] * x.mean()) / x.mean() ** 2)
    print("\nCV^2 of true per-place rates, all injuries, 660 ft radius: %s"
          % ", ".join("%s %.2f" % (k, cv2[k]) for k in pools))

    # one place-level tau^2 for every group: the all-injury estimate, the only group with counts enough to see it
    t = od["near", "all"]
    tau = {"REML": t[1], "DL": t[0], "upper": t[2]}
    print("\n## Locations needed, 80%% power, two-sided alpha 0.05, %d matched control unit(s) per treated unit" % K)
    print("phi per group as above; tau^2 REML %.3f, DL %.3f, upper %.3f, for treated and control units alike.\n"
          "† = school zones: treated plus controls exceed the %d-school pool.\n" % (tau["REML"], tau["DL"], tau["upper"], SCHOOL_POOL))
    results = {}
    for tau_case, t2 in tau.items():
        if tau_case != "upper":
            print("\n### tau^2 = %s (%.3f)\n" % (tau_case, t2))
            print("| Design | Group | Windows | Injuries per unit, before / after window | "
                  + " | ".join("%d%% drop: units | %d%%: locations" % (d * 100, d * 100) for d in EFFECTS) + " |")
            print("| --- " * (4 + 2 * len(EFFECTS)) + "|")
        for name, (m, catch, per_sys, pool, share) in DESIGNS.items():
            for g in GROUPS:
                for tb, ta, wl in WINDOWS:
                    rate = rate_cam[g] * factor[g][pool] * catch
                    cells = []
                    for d in EFFECTS:
                        n = math.ceil(n_units(rate, tb, ta, t2, d * share, phi[g], cv2[pool]))
                        sysn = math.ceil(n * m / per_sys)
                        over = pool == "school" and n * (1 + K) > SCHOOL_POOL
                        results[tau_case, name, g, (tb, ta), d] = (n, sysn, rate, over)
                        cells += [str(n) + ("†" if over else ""), str(sysn)]
                    if tau_case != "upper":
                        print("| %s | %s | %s | %.1f / %.1f | %s |" % (name, NAMES[g], wl, rate * tb, rate * ta, " | ".join(cells)))

    print("\n## Implied cap: corridors + school zones + mobile, plus today's 33\n")
    print("Each cell: total with mobile at the full drop – total with mobile at half the drop. † = school zones exceed the pool.\n")
    print("| Outcome | Windows | tau^2 | " + " | ".join("%d%% drop" % (d * 100) for d in EFFECTS) + " |")
    print("| --- " * (3 + len(EFFECTS)) + "|")
    for g in GROUPS:
        for tb, ta, wl in WINDOWS:
            for tau_case in tau:
                cells = []
                for d in EFFECTS:
                    r = lambda nm: results[tau_case, nm, g, (tb, ta), d]
                    base = 33 + r(CORR)[1] + r(SCH)[1]
                    cells.append("%d–%d%s" % (base + r(MOB_FULL)[1], base + r(MOB_HALF)[1], "†" if r(SCH)[3] else ""))
                print("| %s | %s | %s | %s |" % (NAMES[g], wl, tau_case, " | ".join(cells)))

    print("\n## Corridor size: cap with 4, 3 or 2 locations per corridor (school zones held to the pool)\n")
    print("Each cell: lowest (REML, mobile full drop) – highest (DL, mobile half drop) total, school zones capped at %d"
          " locations.\n" % (3 * (SCHOOL_POOL // 2)))
    print("| Outcome | Windows | Locations per corridor | Corridor units (REML–DL), %d%% drop | " % (EFFECTS[0] * 100)
          + " | ".join("%d%% drop" % (d * 100) for d in EFFECTS) + " |")
    print("| --- " * (4 + len(EFFECTS)) + "|")
    for g in ("all", "ped"):
        for tb, ta, wl in WINDOWS:
            for cname, nloc in ((CORR, 4), (CORR3, 3), (CORR2, 2)):
                cells = []
                for d in EFFECTS:
                    tots = []
                    for tau_case, mob in (("REML", MOB_FULL), ("DL", MOB_HALF)):
                        r = lambda nm: results[tau_case, nm, g, (tb, ta), d]
                        tots.append(33 + r(cname)[1] + min(r(SCH)[1], 3 * (SCHOOL_POOL // 2)) + r(mob)[1])
                    cells.append("%d–%d" % tuple(tots))
                cu = "%d–%d" % (results["REML", cname, g, (tb, ta), EFFECTS[0]][0], results["DL", cname, g, (tb, ta), EFFECTS[0]][0])
                print("| %s | %s | %d | %s | %s |" % (NAMES[g], wl, nloc, cu, " | ".join(cells)))

    n_sch = SCHOOL_POOL // 2
    print("\n## School zones held to the pool: %d treated schools, %d controls\n" % (n_sch, SCHOOL_POOL - n_sch))
    print("Power of a school-zone trial using every school, and the cap with school zones held to %d locations"
          " (mobile at full drop – half drop).\n" % (3 * n_sch))
    print("| Outcome | Windows | tau^2 | " + " | ".join("%d%%: power | %d%%: cap" % (d * 100, d * 100) for d in EFFECTS) + " |")
    print("| --- " * (3 + 2 * len(EFFECTS)) + "|")
    held = {}
    for g in GROUPS:
        for tb, ta, wl in WINDOWS:
            for tau_case in ("REML", "DL"):
                cells = []
                for d in EFFECTS:
                    rate = results[tau_case, SCH, g, (tb, ta), d][2]
                    req = n_units(rate, tb, ta, tau[tau_case], d, phi[g], cv2["school"], (SCHOOL_POOL - n_sch) / n_sch)
                    pw = stats.norm.cdf(math.sqrt(n_sch / req) * Z - stats.norm.ppf(0.975))
                    r = lambda nm: results[tau_case, nm, g, (tb, ta), d]
                    base = 33 + r(CORR)[1] + min(r(SCH)[1], 3 * n_sch)
                    held[g, (tb, ta), tau_case, d] = (pw, base + r(MOB_FULL)[1], base + r(MOB_HALF)[1])
                    cells += ["%.2f" % pw, "%d–%d" % held[g, (tb, ta), tau_case, d][1:]]
                print("| %s | %s | %s | %s |" % (NAMES[g], wl, tau_case, " | ".join(cells)))

    print("\n## Cap sensitivity: controls per site and where sites go (mobile at full drop – half drop)\n")
    print("Controls cost no cameras, so k can rise for corridors and mobile. School zones share one pool of 113 schools")
    print("(57 in the worse half), so with k = 3 they take min(3, (pool - N) / N) controls; 'no fit' means no N in the pool")
    print("reaches 80% power. 'Worse half' puts corridors, mobile locations and schools in the upper half of their pool by")
    print("radius count. † = with k = 1, school treated plus controls exceed the pool.\n")
    print("| Outcome | Windows | tau^2 | Sites from | Controls per unit | " + " | ".join("%d%% drop" % (d * 100) for d in EFFECTS) + " |")
    print("| --- " * (5 + len(EFFECTS)) + "|")
    for g in GROUPS:
        for tb, ta, wl in WINDOWS:
            for tau_case in ("REML", "DL"):
                t2 = tau[tau_case]
                for where, fac in (("whole pool", factor), ("worse half", upf)):
                    for k in (1, 3):
                        cells = []
                        for d in EFFECTS:
                            tot = 33
                            flag = ""
                            for name in (CORR, SCH):
                                m, catch, per_sys, pool, share = DESIGNS[name]
                                rate = rate_cam[g] * fac[g][pool] * catch
                                if pool == "school":
                                    if k == 1:
                                        n = math.ceil(n_units(rate, tb, ta, t2, d, phi[g], cv2[pool], 1))
                                        flag = "†" if n * 2 > pool_n[where] else ""
                                    else:
                                        fit = school_constrained(rate, tb, ta, t2, d, phi[g], cv2[pool], k, pool_n[where])
                                        if fit is None:
                                            flag, n = "no fit", 0
                                        else:
                                            n = fit[0]
                                else:
                                    n = math.ceil(n_units(rate, tb, ta, t2, d, phi[g], cv2[pool], k))
                                tot += math.ceil(n * m / per_sys)
                            mob = []
                            for name in (MOB_FULL, MOB_HALF):
                                m, catch, per_sys, pool, share = DESIGNS[name]
                                rate = rate_cam[g] * fac[g][pool] * catch
                                mob.append(math.ceil(math.ceil(n_units(rate, tb, ta, t2, d * share, phi[g], cv2[pool], k)) * m / per_sys))
                            cells.append("no fit" if flag == "no fit" else "%d–%d%s" % (tot + mob[0], tot + mob[1], flag))
                        print("| %s | %s | %s | %s | %d | %s |" % (NAMES[g], wl, tau_case, where, k, " | ".join(cells)))

    print("\n## Formula against simulation under the same model (DL tau^2, equal windows, 4,000 reps each)\n")
    for name in (CORR, SCH, MOB_FULL):
        m, catch, per_sys, pool, share = DESIGNS[name]
        for g, T, d in (("all", 1.5, 0.13), ("ped", 1.5, 0.2), ("severe", 3.0, 0.3)):
            n, sysn, rate, over = results["DL", name, g, (T, T), d]
            print("- %s, %s, %.1f y, %d%% drop: N=%d units, simulated power %.2f"
                  % (name, g, T, d * 100, n, simulate(n, rate * T, tau["DL"], d * share, phi[g], cv2[pool])))

    print("\n## Model check: today's 33 locations, pedestrians, city as control (tests the Poisson/phi term only)\n")
    b, a = od["near", "ped"][5], od["near", "ped"][6]
    pub = (math.log(0.88) - math.log(0.47)) / 3.92
    for tau_case in ("REML", "DL"):
        se = math.sqrt((1 + cv2["camera"]) * tau[tau_case] / 33 + phi["ped"] * (1 / a + 1 / b))
        print("- Model SE of the log ratio, tau^2 %s: %.3f." % (tau_case, se))
    print("- The published 0.66 (0.47-0.88), a bootstrap over crashes, implies %.3f." % pub)

    zb = stats.norm.ppf(1 - 0.05 / 6) + stats.norm.ppf(0.80)
    print("\n## Multiple testing\n")
    print("Testing 3 designs on one outcome each at 0.05 gives a %.0f%% chance of at least one false positive if none works;"
          " holding that to 5%% (Bonferroni, 0.05/3 two-sided) multiplies every N by %.2f."
          % (100 * (1 - 0.95 ** 3), zb ** 2 / Z ** 2))


if __name__ == "__main__":
    main()
