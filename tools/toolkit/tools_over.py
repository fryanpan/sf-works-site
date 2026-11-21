"""Per-tool square-mile figures, 2026-10-23: cost.per_sq_mi (what goes where in a typical SF square mile, times SF's
unit cost), effect.area (the study's local effect scaled to all injury crashes across that square mile) and coverage
(how much of what the city needs SF has built today). tools_src.py merges these into TOOLS. Every derived number here
is [inference — mine]; the inputs carry their own tags.

The typical square mile is the average of the 42 cells of a 1-mile grid over SF's land left after cells that are mostly
park, open space or water are dropped (geo/grid.py, read from geo/grid.json below). The Q() totals are overwritten by the
CALC arithmetic further down. Inputs:
DataSF Analysis Neighborhoods j2bu-swwd as the land mask, DataSF Recreation and Parks Properties gtr9-ntp6 plus the
Presidio as open space, DataSF centerlines 3psu-pn9h, OpenStreetMap signals, SFMTA's 2022 High Injury Network, and
DataSF injury crashes ubvf-ztfx 2022-2025. The same counts drive cost and effect."""

from muni_model import FREQ_FX, FARE_FX, FREQ, FARE_NEW, CAR_TRIPS  # noqa: E402
FREQ_SHARE = (round(FREQ["low"] / CAR_TRIPS * 100, 1), round(FREQ["high"] / CAR_TRIPS * 100, 1))
FARE_SHARE = round(FARE_NEW / CAR_TRIPS * 100, 1)
CRASHES = "https://data.sfgov.org/d/ubvf-ztfx"
CENTERLINES = "https://data.sfgov.org/d/3psu-pn9h"
NHOODS = "https://data.sfgov.org/d/j2bu-swwd"
RPD = "https://data.sfgov.org/d/gtr9-ntp6"
HIN = "https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/hin2022/FeatureServer/0"
OSM_SIGNALS = "https://wiki.openstreetmap.org/wiki/Tag:highway%3Dtraffic_signals"
HUMPS = "https://data.sfgov.org/d/abhw-ffzx"
SSI = "https://www.sf.gov/street-safety-initiative"
SSA = "https://sfgov.legistar.com/View.ashx?M=F&ID=14821038&GUID=E014E308-33EC-4EEF-B09B-CB0EEC48A3C2"
DECK = "https://www.sfmta.com/media/44242/download"
CAMDECK = "https://www.sfmta.com/media/44957/download?inline"
SDRM = "https://www.sfmta.com/media/45260/download"
MAYOR_ED = "https://media.api.sf.gov/documents/Street_Safety_ED.pdf"
VEH_22425 = "https://california.public.law/codes/vehicle_code_section_22425"
VEH_22426 = "https://california.public.law/codes/vehicle_code_section_22426"
VZ = "https://visionzerosf.org/wp-content/uploads/2021/11/VZSF_AS_111021_spreads-FINAL.pdf"
R2606 = "https://www.sfcta.org/sites/default/files/2025-07/R26-06%20TNC%20Allocations.pdf"
QBQ = "https://sfmta.com/media/41107/download"
PBIC = "https://web.archive.org/web/2024/https://www.pedbikeinfo.org/cms/downloads/Countermeasure%20Costs_Report_Nov2013.pdf"
NYC_DAYLIGHT = "https://www.nyc.gov/html/dot/downloads/pdf/daylighting-study-2025.pdf"

# ---- the typical square mile: the AVERAGE of the 42 kept cells (geo/grid.py, its grid.json) [inference — mine]. The
# crash shares are pooled over the same cells' crashes, so building a tool at every such place in the 42 cells, divided by
# 42, is exactly the study's effect × the pooled share: cost quantities and shares describe the same square mile.
import json as _json, os as _os
_GJ = _json.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "geo", "grid.json")))
_M = _GJ["mean"]
GRID = dict(
    cells=_GJ["cells"], kept=_GJ["kept"], land_sq_mi=_GJ["land_sq_mi"],
    street_mi=_M["mi_all"], arterial_mi=_M["mi_arterial"], collector_mi=_M["mi_4"], main_mi=_M["mi_main"],
    residential_mi=_M["mi_5"], hin_mi=_M["hin_mi"], intersections=round(_M["x_all"]), main_x=round(_M["x_main"]),
    arterial_x=round(_M["x_arterial"]), residential_x=round(_M["x_res_only"]), main_unsig_x=round(_M["x_main_unsig"]),
    arterial_unsig_x=round(_M["x_arterial_unsig"]), residential_blocks=round(_M["res_blocks"]), signals=round(_M["signals"]),
    arterial_signals=round(_M["signals_arterial"]))
GRID["collector_x"] = GRID["main_x"] - GRID["arterial_x"]
N_SQ = GRID["kept"]  # "citywide need" for coverage = the square mile's quantity × the 42 kept cells
_COV = _GJ["coverage"]
# Short names for the counts the rows use.
IX, MX, AX, CX, RX = GRID["intersections"], GRID["main_x"], GRID["arterial_x"], GRID["collector_x"], GRID["residential_x"]
MU, AU, RB, SG, SGA = GRID["main_unsig_x"], GRID["arterial_unsig_x"], GRID["residential_blocks"], GRID["signals"], GRID["arterial_signals"]
AMI, MMI, RMI, HMI = GRID["arterial_mi"], GRID["main_mi"], GRID["residential_mi"], GRID["hin_mi"]
HALF_ART = AMI / 2                     # the four-lane (or frequent-bus) half of the arterial miles
_r = lambda v: int(v + 0.5)
RAISED, CIRCLES, FILTERS = _r(RX / 2), _r(RX / 4), _r(RX / 5)
HUMPS_N = round(1.7 * RB)
CALM_LO, CALM_HI = round(RMI * 5280 / 250), round(RMI * 5280 / 150)
RADAR = round(AMI * 4)                 # one each way every half mile
SIGNS = round(8 * MMI)                 # about eight speed-limit signs a main-street mile
CAMS = round(HMI / 0.5)                # one camera per half mile of High Injury Network
TSP_N = round(SG * 0.46)
BULBS = 4 * AX + 2 * CX
SQUARE_MILE = dict(
    text=(f"We laid a 1-mile grid over SF's {GRID['land_sq_mi']:.1f} square miles of land and dropped the cells that are under half land or over "
          f"half park, open space or water (Rec and Park property or the Presidio), which leaves {GRID['kept']} of {GRID['cells']}, and leaves out "
          f"Golden Gate Park, the Presidio, Lake Merced, McLaren Park and Treasure Island. The typical square mile is the "
          f"average of those {GRID['kept']}, the same cells whose crashes give each tool's share: {GRID['street_mi']:.1f} street miles "
          f"({AMI:.1f} arterial, {GRID['collector_mi']:.1f} collector, {RMI:.1f} residential), {HMI:.1f} miles of the High Injury Network, "
          f"{IX} intersections ({MX} on a main street, {AX} of them on an arterial, {RX} on residential streets only), {RB} "
          f"residential blocks and {SG} traffic signals ({SGA} on arterials). A main street is one DataSF's centerlines class as "
          f"arterial or collector, or one OpenStreetMap tags trunk, primary, secondary or tertiary. That is OpenStreetMap's judgement: Polk and Valencia count as main streets, Eddy, Irving and Clement stay residential. Each tool is counted only where it goes: "
          f"main-street tools on main-street corners or miles, residential tools on residential blocks, signal tools at signals. "
          f"Signals are OpenStreetMap's, since DataSF doesn't publish SFMTA's inventory. Built today compares SF's count with "
          f"the square mile's quantity times {GRID['kept']}, or with the citywide count where one exists."),
    counts=GRID,
    sources=[{"title": "DataSF neighborhoods (land)", "url": NHOODS}, {"title": "Rec and Park properties", "url": RPD},
             {"title": "DataSF street centerlines", "url": CENTERLINES}, {"title": "OpenStreetMap signals", "url": OSM_SIGNALS},
             {"title": "OpenStreetMap road classes", "url": "https://wiki.openstreetmap.org/wiki/Key:highway"},
             {"title": "SFMTA High Injury Network 2022", "url": HIN}])

# Where the typical square mile's injury crashes happen: DataSF ubvf-ztfx 2022-2025, the 11,095 crashes inside the 42
# kept cells (of 11,781), joined to centerlines by node or segment key and to OSM signals [DataSF ubvf-ztfx — queried
# 2026-10-23]. Percent of those 11,095, copied from geo/grid.json. "Main street" = class 2-4; "arterial" = class 2-3.
S = _json.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "geo", "grid.json")))["shares"]
S = dict(S, all=100.0, signal_nonped=round(S["signal"] - S["signal_ped"], 1))
_LBL = dict(all_x="crashes at intersections", signal="crashes at signals", signal_ped="pedestrian crashes at signals",
            signal_nonped="crashes at signals that involve no pedestrian",
            main_x_ped="pedestrian crashes at main-street corners", main_unsig_x_ped="pedestrian crashes at main-street corners with no signal",
            main_x_night_ped="pedestrian crashes after dark at main-street corners", res_unsig_x="crashes at residential corners with no signal",
            res_ped="pedestrian crashes on residential streets", arterial="crashes on arterials", art_mid="crashes on arterials away from corners",
            main="crashes on main streets", residential="crashes on residential streets", nonarterial="crashes off the arterials",
            main_bike="bike crashes on main streets", main_bikecar="crashes between a bike and a vehicle on main streets",
            res_mid="crashes on residential streets away from corners", day="crashes in daylight",
            signal_right_pedbike="right-turn crashes with a pedestrian or bike at signals",
            sig_broadside="broadside crashes at signals", sig_rearend="rear-end crashes at signals",
            unlit="crashes on streets with no working street lights",
            unlit_x_ped="pedestrian crashes at corners with no working street lights, after dark",
            all="every injury crash in the area")
SHARES_NOTE = ("Effect is the change in all injury crashes across a typical square mile once the tool is built everywhere "
               "the cost column puts it, the same places the cost column prices. It is the study's effect where the tool goes, "
               "times the share of the square mile's injury crashes that happen at that kind of place (DataSF crashes 2022-2025 "
               "inside the same 42 cells the square mile averages, 11,095 of them), times the share of those places the cost column treats. "
               "Built today is a separate column and does not change the effect. Where the study counted only pedestrians, "
               "only pedestrian crashes are counted, so the figure leaves other road users unchanged. Each info box shows the arithmetic.")


def _p(v, d=None):
    """A percent for the working: one decimal from 1% up, two below, so a small product never prints as 0.0."""
    v = abs(v)
    if d == 0:
        return f"{v:g}"
    return f"{v:.1f}" if v >= 1 else f"{v:.2f}"


def _w(v):
    return "fewer" if v < 0 else "more"


def T(n, of, words):
    """The share of places treated, read from the cost column's quantity: n of the `of` places, in words."""
    return (n / of, words)


def ALL(words):
    return (1.0, words)


def E(local, share, treat, lead=None):
    """One term of the effect: the study's percent change where the tool goes (negative = fewer), the share of the
    square mile's injury crashes at those places (an S key, or (value, label) for a figure from elsewhere), and the
    share of those places treated. `lead` is a sentence to put first, for a scenario."""
    val, lbl = (S[share], _LBL[share]) if isinstance(share, str) else share
    return dict(local=local, share=val, label=lbl, key=share if isinstance(share, str) else None,
                treat=treat[0], treat_words=treat[1], value=local * val / 100 * treat[0], lead=lead)


def _term_words(t, last=True):
    who = t["label"][0].upper() + t["label"][1:]
    tw = "every one of them" if t["treat"] >= 0.999 else f"{t['treat']:.0%} of them"
    return ((t["lead"] + " " if t.get("lead") else "") + f"{who} are {_p(t['share'])}% of a typical square mile's injury crashes. The cost column builds it at "
            f"{t['treat_words']}, so it reaches {tw}. {_p(t['local'], 0)}% {_w(t['local'])} × {_p(t['share'])}% × "
            f"{t['treat']:.0%} = {_p(t['value'])}% {_w(t['value'])}")


def working(terms, unit="injury crashes across the square mile"):
    """The effect's arithmetic in plain sentences, generated from the numbers so it cannot drift from the cell."""
    if len(terms) == 1:
        return _term_words(terms[0]) + f" {unit}."
    parts = [_term_words(t) + "." for t in terms]
    tot = sum(t["value"] for t in terms)
    sums = " and ".join(f"{_p(t['value'])}% {_w(t['value'])}" for t in terms)
    return " ".join(parts) + f" Together, {sums} net out to {_p(tot)}% {_w(tot)} {unit}."


def A(note, *terms, cell=None, pct=None, work=None):
    """note: what the study found and how it applies, in plain sentences. terms: E(...) terms whose sum is the
    square-mile effect. cell: what the table prints when there is no single figure (then work, if given, is a
    side calculation). pct/work: a figure from a model (the Muni rows), with its working written from the model's numbers."""
    out = dict(pct=None, local_pct=None, share=None, share_key=None, treat=None, cell=cell, note=note)
    if terms:
        tot = sum(t["value"] for t in terms)
        out.update(local_pct=terms[0]["local"], share=terms[0]["share"], share_key=terms[0]["key"],
                   treat=round(terms[0]["treat"], 3), terms=[{k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items()} for t in terms])
        work = work or working(terms)
        if cell is None:
            out["pct"] = round(tot, 1) if abs(tot) >= 1 else round(tot, 2)  # the same decimals the working prints
    if pct is not None:
        out["pct"] = pct
    if cell is not None and not terms and not work:
        work = "So we give no square-mile figure."
    out["working"] = work
    out["text"] = f"{note} {work}".strip()
    for s in (note, work):
        assert ";" not in (s or "") and "—" not in (s or "") and "–" not in (s or ""), f"semicolon or dash in: {s}"
    return out


def _usd(v, exact=False):
    if exact or v < 1e4:
        return f"${v:,.0f}"
    if v >= 1e6:
        return f"${v / 1e6:.2f}".rstrip("0").rstrip(".") + "M"
    return f"${round(v, -3):,.0f}"


def _rng(lo, hi, f=_usd):
    return f(lo) if hi in (None, lo) else f"{f(lo)} to {f(hi)}"


def K(n, what, each, n_hi=None, each_hi=None, per="each"):
    """One cost term: n (to n_hi) of `what` at `each` (to each_hi) dollars, `per` unit ("each", "a mile")."""
    return dict(n=n, n_hi=n_hi if n_hi is not None else n, what=what, each=each, each_hi=each_hi if each_hi is not None else each, per=per)


def cost_working(terms, lo, hi, per_year):
    """quantity × unit cost = total, from the numbers, checked against the row's total."""
    lo_c = sum(t["n"] * t["each"] for t in terms)
    hi_c = sum(t["n_hi"] * t["each_hi"] for t in terms)
    for got, want in ((lo_c, lo), (hi_c, hi)):
        assert abs(got - want) <= 0.03 * want, f"cost working {got} does not match total {want}"
    yr = " a year" if per_year else ""
    num = lambda v: f"{v:.3g}"
    bits = [f"{_rng(t['n'], t['n_hi'], num)} {t['what']} × {_rng(t['each'], t['each_hi'], lambda v: _usd(v, True))} {t['per']}" for t in terms]
    s = " plus ".join(bits) + f" = {_rng(lo_c, hi_c)}{yr}."
    if per_year:
        s += f" The band counts ten years, {_rng(lo_c * 10, hi_c * 10)}."
    return s


from muni_model import S as _MS, B as _MB, R as _MR  # noqa: E402
_sg = lambda v: f"{'−' if v < 0 else '+'}{abs(v):.1f}%"
_fm = FREQ["mid"] / CAR_TRIPS * 100
FREQ_WORK = (f"Doubling bus service at an elasticity of 0.3 to 0.7 (CARB: frequency +0.5, service hours +0.7 to +0.8) adds "
             f"{FREQ_SHARE[0]}% to {FREQ_SHARE[1]}% as many trips as the area makes by car. Each new rider who leaves a car removes "
             f"that car trip's risk, and {_MS['low']:.0%} to {_MS['high']:.0%} of new riders do. Muni is not injury-free. A transit vehicle "
             f"was a party in 1.6% of SF's injury crashes in 2022 to 2025 (189 of 11,781, DataSF 8gtc-pjc6), so twice the buses add "
             f"{_MB['low']}% to {_MB['high']}% more. Central case: {_fm:.1f}% × {_MS['mid']:.0%} from cars = {_fm * _MS['mid']:.1f}% fewer, "
             f"plus {_MB['mid']}% more from the added buses, = {abs(FREQ_FX[1]):.1f}% {_w(FREQ_FX[1])} injury crashes. Across the range, "
             f"{_sg(FREQ_FX[0])} to {_sg(FREQ_FX[2])}. Trips are compared one for one, and NTD counts boardings, so transfers make "
             f"this lean toward too much benefit.")
FARE_WORK = (f"Free fares at the short-run fare elasticity of 0.4 add 40% more bus, light rail and streetcar trips, {FARE_SHARE}% as "
             f"many as the area makes by car (the long-run elasticity is higher). Each new rider who leaves a car removes a car trip's "
             f"risk, and every new rider adds a Muni trip's risk, about {_MR['mid']:.0%} of a car trip's risk a mile (Morency 2018's ratios of car "
             f"to bus risk for occupants, pedestrians and cyclists, weighted by SF's crash mix). Central case: {FARE_SHARE}% × "
             f"({_MS['mid']:.0%} from cars minus {_MR['mid']:.0%}) = {abs(FARE_FX[1]):.1f}% {_w(FARE_FX[1])} injury crashes. Across the range, "
             f"{_sg(FARE_FX[0])} to {_sg(FARE_FX[2])}. SF's youth program saw 'no discernible change' in car trips to school, "
             f"which points to the worse end. Free fares add riders but no buses, so charging each new rider a Muni trip's "
             f"average risk is a cautious choice. With no added risk per rider, the central case would be {FARE_SHARE * _MS['mid']:.1f}% fewer.")


def Q(quantity, unit_cost, lo, hi=None, per_year=False, assume=None, *srcs):
    return dict(quantity_text=quantity, unit_cost=unit_cost, total_low=lo, total_high=hi if hi is not None else lo,
                per_year=per_year, band="auto", assumptions=assume,
                sources=[{"title": a, "url": b} for a, b in srcs])


def C(pct, text, url=None, label=None):
    return dict(pct=pct, label=label if label else (None if pct is None else (f"{pct:.0f}%" if pct >= 1 else "<1%")), text=text, url=url)


G = GRID
OVER = {
# ------------------------------------------------------------------ spot
"daylighting": dict(
    sq=Q(f"All {IX} intersections", "$3,667 an intersection", 550000, None, False, None,
         ("SFCTA, $1.1M for about 300 intersections", "https://www.sfcta.org/blogs/hands-learning-about-californias-daylighting-law-new-traditions-elementary")),
    area=A("The studies disagree. Vision Zero SF reports 14% fewer collisions after neighborhood-wide daylighting in the "
             "Tenderloin, with no study behind it (p. 26). New York's 2025 daylighting study found no significant change in "
             "total injuries at corners daylit with paint or signs, and a 30% higher pedestrian injury rate at daylit "
             "hydrant-zone corners. With no agreed figure, we give no square-mile figure.", cell="No clear effect"),
    cov=C(65, "SFMTA has daylit 65% of the city's intersections, more than 4,000, as of May 2026.", SSI)),
"hardened-daylighting": dict(
    sq=Q(f"About {2 * AX} to {2 * MX} corners: the two near-side corners at each of the {AX} arterial or {MX} main-street intersections",
         "$10,000 a corner (New York, not SF)", 400000, 980000, False, None,
         ("NYC DOT estimate, Council hearing 2025-04-21", "https://citymeetings.nyc/meetings/new-york-city-council/2025-04-21-1000-am-committee-on-transportation-and-infrastructure/chapter/council-member-julie-won-questions-dot-on-daylighting-implementation-costs")),
    area=A("New York: corners with hardened daylighting had about 32% fewer pedestrian injuries than expected (NYC DOT 2025), "
             "but the same study found 'No significant relationship between daylighting and total (all mode) injuries', hardened or "
             "sign-only. So the table prints no figure for all injuries. For pedestrians alone, the arithmetic would be:",
             E(-32, "main_x_ped", T(2, 4, "two of the four corners at each main-street intersection")), cell="No clear effect on all injuries"),
    cov=C(0.5, "No count of hardened corners exists; SFMTA's Community Corners pilot was adopted in June 2026, limited to quiet stop-sign corners.", "https://www.sfmta.com/media/45219/download", "<1%")),
"high-visibility-crosswalks": dict(
    sq=Q(f"About {4 * MX} crosswalks: four at each of the {MX} main-street intersections", "$3,070 a crosswalk (US, 2013)", 602000, None, False, None,
         ("PBIC 2013 cost report", PBIC)),
    area=A("FHWA: up to 40% fewer pedestrian injury crashes where high-visibility crosswalks are painted. "
             "That is an 'up to' figure, so this is a ceiling.",
             E(-40, "main_x_ped", ALL(f"all four crosswalks at each of the {MX} main-street intersections"))),
    cov=C(round(100 * _COV["x_main_continental"] / _COV["x_main"]), f"SFMTA's crosswalk layer marks continental crosswalks at about {_COV['x_main_continental']:,} of SF's {_COV['x_main']:,} main-street intersections ({100 * _COV['x_res_continental'] / _COV['x_res_only']:.0f}% of residential-only ones). The layer marks an intersection once if any crosswalk at it is continental, and the cost column buys all four, so this overstates how many of the crosswalks are done [DataSF crosswalk layer — queried 2026-10-23, joined to centerline nodes, inference — mine].", "https://services.sfmta.com/arcgis/rest/services/DataSF/master/MapServer/53", f"≤{round(100 * _COV['x_main_continental'] / _COV['x_main'])}%")),
"leading-pedestrian-interval": dict(
    sq=Q(f"All {SG} signals", "$10,000 to $50,000 a signal (Vision Zero band, national data)", 170000, 850000, False,
         "FHWA says the cost is 'very low' where only the timing changes, so this is a ceiling.", ("Vision Zero SF tool table, p. 26", VZ)),
    area=A("FHWA: 13% fewer pedestrian crashes at intersections with a leading pedestrian interval.",
             E(-13, "signal_ped", ALL(f"all {SG} signals"))),
    cov=C(81, "81% of SF's 1,292 signals have an LPI on at least one crosswalk or no turn conflict (SFMTA, 2024); SFMTA gives no LPI-only count, so this is a ceiling.",
          "https://sfmta.com/accessibility-strategy-needs-assessment-2024/streets-capital-projects/12-accessible-pedestrian-signals", "≤81%")),
"walk-speed": dict(
    sq=Q(f"All {SG} signals", "$10,000 to $50,000 a signal (Vision Zero band)", 170000, 850000, False, None, ("Vision Zero SF tool table, p. 26", VZ)),
    area=A("We found no injury study of longer crossing times, so we give no square-mile figure.", cell="No injury study"),
    cov=C(None, "SFMTA's standard since 2018 at its 1,200+ signals; how many run it is not published.", "https://www.sfmta.com/pedestrian-signal-improvements", "no count")),
"pedestrian-scrambles": dict(
    sq=Q(f"About 2 of the {SG} signals, the busiest walking corners", "a timing change to $150,000 a signal (FHWA PEDSAFE, not SF)", 16000, 300000, False, None,
         ("FHWA PEDSAFE, pedestrian signal timing", "https://pedbikesafe.org/PEDSAFE/countermeasures_detail.cfm?CM_NUM=47")),
    area=A("New York: 51% fewer pedestrian crashes at scrambles (Chen et al. 2012), but 10% more crashes between vehicles. "
             "So the two changes are counted separately. Scrambles go at the busiest walking corners, which have more pedestrian "
             "crashes than the average signal, so this figure is a floor.",
             E(-51, "signal_ped", T(2, SG, f"about 2 of the {SG} signals, the busiest walking corners")),
             E(10, "signal_nonped", T(2, SG, "the same 2 signals"))),
    cov=C(19, "About 16 named scrambles (Chinatown, the Financial District, 11 in the Tenderloin) against about 84 that 2 a square mile would mean.", "https://www.sfmta.com/node/25507", "~19%")),
"no-turn-on-red": dict(
    sq=Q(f"All {SG} signals, about eight signs each", "about $1,900 to $2,800 an intersection (FHWA PEDSAFE sign costs, not SF)", 32000, 48000, False, None,
         ("FHWA PEDSAFE, right-turn-on-red restrictions", "https://mail.walkinginfo.org/pedsafe/pedsafe_curb1_CM_NUM_41/")),
    area=A("The Highway Safety Manual finds 69% more of these crashes where turns on red are allowed, so a ban means about 41% "
             "fewer of them (1 ÷ 1.69 is 0.59, our reading of the reverse). SFMTA's own Tenderloin evaluation found 'turn on red crashes "
             "account for less than 1% of all injury crashes', so we use 1% as the most these crashes can be, and the result is an upper bound.",
             E(-41, (1.0, "turn-on-red crashes, at most (SFMTA's count)"), ALL(f"all {SG} signals"))),
    cov=C(4, "About 50 Tenderloin intersections since 2021 of SF's 1,294 signals; about 200 downtown are approved, construction pending to 2027.", "https://www.sfmta.com/index%2Ephp/projects/no-turn-red-downtown-expansion-project")),
"turn-calming": dict(
    sq=Q(f"All {SG} signals", "about $3,700 an intersection (SFCTA Prop L, $100,000 for 27 locations)", 63000, None, False, None,
         ("SFCTA CAC Prop L allocations, 2024-02-28, slide 4", "https://www.sfcta.org/sites/default/files/2024-02/SFCTA_CAC_PropLAllocationsPRESENTATION_2024-02-28.pdf")),
    area=A("New York's own before-after evaluation (NYC DOT 2022): pedestrian injuries fell 17.5% at turn-calmed corners, but injuries "
             "to people in vehicles rose 13.6%, so all injuries changed by +0.3% (killed or seriously injured fell 16.2%). For all "
             "injuries the tool is about even.",
             E(0.3, "signal", ALL(f"all {SG} signals"))),
    cov=C(17, "Turn safety treatments at 220 intersections (SFMTA Board, Jan 2026), against about 1,300 signals.", DECK)),
"bulb-outs": dict(
    sq=Q(f"About {BULBS} corners: four at each of the {AX} arterial intersections and two at each of the {CX} collector-only ones",
         "$10,000 (US median, 2013) to $184,500 (SF, Bayview, an upper bound) a corner", 1380000, 25460000, False,
         "The SF figure includes two flashing beacons, so the true SF cost is lower.",
         ("SFCTA Prop K memo 2023-02, Bayview bulb-outs", "https://www.sfcta.org/sites/default/files/2023-02/SFCTA_CAC_PropKGroupedAllocationsMEMO_2023-02-22.pdf")),
    area=A("New York: 16.5% fewer pedestrian injuries at 266 curb extensions (before-after).",
             E(-16.5, "main_x_ped", T(BULBS, 4 * MX, f"{BULBS} of the {4 * MX} corners at the {MX} main-street intersections (all four at arterial "
                                     "intersections, two at collector-only ones)"))),
    cov=C(round(100 * 269 / (BULBS * N_SQ)), f"269 bulb-outs built 2017-2020 (SFMTA), no citywide total, against about {round(BULBS * N_SQ, -2):,} corners at {BULBS} a square mile, so at least {100 * 269 / (BULBS * N_SQ):.0f}%.", "https://sfmta.com/media/28271/download", f"{100 * 269 / (BULBS * N_SQ):.0f}%+")),
"refuge-islands": dict(
    sq=Q(f"One at each of the about {AU} arterial intersections with no signal (the effect is for crossings with no signal)",
         "$10,000 (SF calming island) to $41,000 (US high) an island", 100000, 410000, False, None,
         ("SFCTA March 2021 enclosure, p. E7-27", "https://www.sfcta.org/sites/default/files/2021-03/Item%207%20-%20Grouped%20Allocations%20ENCLOSURE.pdf")),
    area=A("FHWA: 56% fewer pedestrian crashes with a refuge island, measured at crossings with no signal. Placing them at the "
             "arterial crossings with no signal is our reading.",
             E(-56, "main_unsig_x_ped", T(AU, MU, f"{AU} of the {MU} main-street corners with no signal, the ones on arterials"))),
    cov=C(None, "No SFMTA count of refuge islands found; built on Geary, Upper Market and a few others.", "https://www.sfmta.com/getting-around/walk/pedestrian-improvements-toolkit/pedestrian-refuges", "no count")),
"raised-crossings": dict(
    sq=Q(f"About {RAISED}: one raised leg at every other residential-only intersection (the fire department objects to two)",
         "$15,000 (SF engineer's estimate, asphalt) to $28,600 (SF all-in calming device)", 645000, 1230000, False, None,
         ("SFCTA March 2021 enclosure, p. E7-27", "https://www.sfcta.org/sites/default/files/2021-03/Item%207%20-%20Grouped%20Allocations%20ENCLOSURE.pdf"),
         ("SFCTA R26-06", R2606)),
    area=A("Elvik and Vaa meta-analysis (CMF Clearinghouse 137, a raised crosswalk): 30% fewer injury crashes where one is built. "
             "One raised leg at every other residential corner puts one at half the corners, and at each it slows one of the two "
             "crossing streets, so we count a quarter of the corners as treated.",
             E(-30, "res_unsig_x", T(1, 4, f"one leg at {RAISED} of the {RX} residential corners, which slows one of the two streets at each"))),
    cov=C(2, f"Tens: 18 mid-block raised crosswalks in SFMTA's calming data, 13 in Golden Gate Park and a few others, against about {round(RAISED * N_SQ, -2):,} at {RAISED} a square mile.", HUMPS, "~2%")),
"flashing-beacons": dict(
    sq=Q("About 5, at main-street crossings with no signal or stop sign (federal rules bar them elsewhere)",
         "$175,000 to $250,000 an intersection (SFCTA estimate, 38th and Geary)", 875000, 1250000, False, None,
         ("SFCTA allocation request, 38th and Geary RRFB", "https://www.sfcta.org/sites/default/files/2023-03/D1%2038th%20and%20Geary.pdf")),
    area=A("FHWA: up to 47% fewer pedestrian crashes with rectangular rapid flashing beacons (55% with hybrid beacons). That is an "
             "'up to' figure, so this is a ceiling.",
             E(-47, "main_unsig_x_ped", T(5, MU, f"about 5 of the {MU} main-street corners with no signal"))),
    cov=C(26, "55 locations (SFMTA Board, Jan 2026) against about 210 at 5 a square mile.", DECK)),
"street-lighting": dict(
    sq=Q(f"About {2 * MX} poles: two at each of the {MX} main-street intersections", "$3,600 (US median) to $43,800 (SF Tenderloin, derived) a pole", 353000, 4290000, False,
         "No data says which corners lack crossing-level light, so this is an upper bound.",
         ("Tenderloin CBD, 97 new lights (secondary)", "https://tlcbd.org/blog/lighting-project-tenderloin")),
    area=A("FHWA: up to 42% fewer nighttime pedestrian injury crashes, comparing lit intersections with unlit ones. So the "
             "study reaches only pedestrian crashes after dark at corners with no working street lights. SF's main-street "
             "corners are mostly lit already, so few crashes are left for new poles to prevent.",
             E(-42, "unlit_x_ped", ALL("the corners that lack working lights"))),
    cov=C(None, "No SF program or count for lighting at crossings; one-off projects such as the Tenderloin's 97 lights.", None, "no count")),
"signal-upgrades": dict(
    sq=Q(f"All {SG} signals", "$424,000 to $540,000 a signal (Public Works Contract 35, 17 sites)", 7210000, 9180000, False,
         "The contract buys new poles, mast arms, 12-inch heads, accessible signals and curb ramps.",
         ("Public Works Commission, Contract 35 award, 2026-04-30", "https://sfpublicworks.org/sites/default/files/Commissions/April%2030%2C%202026/Resolutions/PWC%20Resolution%202026-0036%20No.%2035%20Traffic%20Signal%20Upgrades%20award%202026-4-30.pdf")),
    area=A("FHWA's 15% fewer crashes is for reflective backplates, a very low-cost add-on, not the mast arms and heads this cost "
             "buys. We found no injury study of the full upgrade, so we give no square-mile figure.", cell="No figure for this hardware"),
    cov=C(None, "Upgrades go in numbered contracts of 7 to 17 signals; no citywide count of upgraded signals, and no SF backplate program found.", "https://www.sfmta.com/projects/contract-35-traffic-signal-modifications-0", "no count")),
"signal-progression": dict(
    sq=Q(f"All {SG} signals, timed as corridors", "under $10,000 a signal (Vision Zero band, national data)", 170000, None, False, "A ceiling: no SF unit cost found.",
         ("Vision Zero SF tool table, p. 26", VZ)),
    area=A("We found no injury study. Franklin Street's 85th percentile speed fell from 27 to 25 mph. So we give no square-mile "
             "figure.", cell="No injury study"),
    cov=C(None, "Corridor by corridor: Valencia at 13 mph (2011), Oak and Fell at 20 mph (2024); the 175-signal retiming does not state a speed.", "https://sfmta.com/en/node/29748", "no count")),
"speed-humps": dict(
    sq=Q(f"About {HUMPS_N} devices: 1.7 a block on all {RB} residential blocks", "$15,500 to $37,200 a device all-in (SFCTA R26-06)", 5900000, 14100000, False, None,
         ("SFCTA R26-06", R2606)),
    area=A("Elvik and Vaa meta-analysis (CMF Clearinghouse 132): 40% fewer injury crashes of all types on local two-lane streets "
             "with speed humps. We apply it to crashes away from corners on residential streets, where the devices sit. Tester et "
             "al. 2004 found 53% lower odds of a child pedestrian injury near home, but child pedestrians are under 1% of SF's "
             "injury crashes.",
             E(-40, "res_mid", ALL(f"every one of the {RB} residential blocks"))),
    cov=C(round(100 * _COV["res_blocks_calmed"] / _COV["res_blocks"]), f"{_COV['res_blocks_calmed']:,} of SF's {_COV['res_blocks']:,} residential blocks have a completed hump, cushion, table or bump in SFMTA's data (queried 2026-10-23).", HUMPS)),
"traffic-circles": dict(
    sq=Q(f"About {CIRCLES}: one in four of the {RX} residential-only intersections, those wide enough for the fire department's 20 ft rule",
         "$20,000 to $25,000 a circle (Seattle, not SF)", 420000, 525000, False, None,
         ("Seattle DOT, traffic circles", "https://www.seattle.gov/transportation/projects-and-programs/programs/home-zone-program/traffic-calming/traffic-circles")),
    area=A("Mishra et al. 2022: 61% fewer fatal and injury crashes when a two-way stop becomes a mini roundabout, but 74% more "
             "when it was an all-way stop, and SF keeps the all-way stops at its circles on Euclid. The study's intersections were "
             "suburban collectors in eight states (3,700 to 4,900 cars a day on the minor road), not SF residential corners. So the "
             "table prints both ends.",
             cell="−2% to +2% injuries",
             work=working([E(-61, "res_unsig_x", T(1, 4, f"one in four of the {RX} residential corners, about {CIRCLES}, those wide enough for the fire department"), lead="Where a circle replaces a two-way stop.")])
                  + " " + working([E(74, "res_unsig_x", T(1, 4, f"the same {CIRCLES} corners"), lead="Where it replaces an all-way stop.")])),
    cov=C(0.2, "Two circles on Euclid Avenue (2018); one at McAllister and Steiner was removed after six months.", "https://www.sfmta.com/fr/node/15989", "<1%")),
"speed-radar-signs": dict(
    sq=Q(f"About {RADAR}: one each way every half mile on the {AMI:.1f} arterial miles", "$7,500 to $11,150 a sign (SF, 2004 dollars, not inflated)", 75000, 112000, False, None,
         ("Board of Supervisors Res. 548-04", "https://sfbos.archive.sf.gov/ftp/uploadedfiles/bdsupvrs/resolutions04/r0548-04.pdf")),
    area=A("Hallmark et al. 2015: 5% to 7% fewer crashes, measured on rural curves only. We use the 7%.",
             E(-7, "art_mid", ALL(f"one sign each way every half mile on all {AMI:.1f} arterial miles"))),
    cov=C(round(100 * 12 / (RADAR * N_SQ)), f"12 completed speed radar signs in SFMTA's calming data (queried 2026-10-23), five of them on Upper Market, against about {round(RADAR * N_SQ, -1)} at {RADAR} a square mile.", HUMPS, f"~{100 * 12 / (RADAR * N_SQ):.0f}%")),
"lane-removal": dict(
    sq=Q(f"About {HALF_ART:.2g} miles: the four-lane half of the {AMI:.1f} arterial miles", "$250,000 to $425,000 a mile in paint (14th Street and Golden Gate Avenue)", 325000, 553000, False, None,
         ("SFCTA Prop K request, Golden Gate Avenue", "https://SFCTA.org/sites/default/files/2019-03/ARF%20Golden_Gate_Avenue_Buffered_Bike_Lane__NTIP_Capital.pdf"),
         ("SFCTA Board memo, Sept 2021 (14th Street)", "https://www.sfcta.org/sites/default/files/2021-09/Item%206%20-%20Grouped%20Prop%20K%20Allocations%20MEMO.pdf")),
    area=A("FHWA: 19% to 47% fewer crashes when four lanes become three. We use the low end, 19%.",
             E(-19, "arterial", T(1, 2, f"the four-lane half of the {AMI:.1f} arterial miles"))),
    cov=C(round(100 * 20 / (HALF_ART * N_SQ)), f"34 road diets from 1973 to 2010 (about 20 miles) plus a handful since, against about {HALF_ART * N_SQ:.0f} miles at {HALF_ART:.2g} a square mile.", "https://sf.streetsblog.org/2010/03/31/san-francisco-planners-proud-of-long-list-of-road-diets", f"~{100 * 20 / (HALF_ART * N_SQ):.0f}%")),
"lower-speed-limits": dict(
    sq=Q(f"About {SIGNS} signs on the {MMI:.1f} main-street miles", "about $450 a sign (SF, 2012)", 22000, None, False, None,
         ("SFMTA press release 2012-05-14", "https://archives.sfmta.com/cms/apress/MayorLeeSFMTAandWalkSFAnnounceNewSaferSpeedZonesCompletedaround181SanFranciscoSchools.htm")),
    area=A("Edinburgh, a controlled study of signed 20 mph limits: 10% fewer casualties on changed streets (95% CI −19% to 0%), "
             "where limits fell from 30 mph. SF's corridors go from 25 to 20 mph, so the effect may be smaller. The paper's estimate "
             "against paired control zones is 20%, and we use the street-level 10%. State law (AB 43) limits where SF may lower "
             "limits, so building it on every main-street mile is a ceiling.",
             E(-10, "main", ALL(f"all {MMI:.1f} main-street miles"))),
    cov=C(round(100 * 108 / _COV["mi_main"]), f"AB 43 lower limits on 112 corridors, about 108 miles (79 business-district corridors and 33 safety corridors), of SF's {_COV['mi_main']:.0f} main-street miles.", "https://www.sfmta.com/getting-around/walk/speed-management")),
"protected-intersections": dict(
    sq=Q("About 4: the arterial signals where a protected bike lane crosses", "about $350,000 an intersection (9th and Division, secondary)", 1400000, None, False, None,
         ("Streetsblog California, 2019-11-01", "https://cal.streetsblog.org/2019/11/01/protected-intersection-update-whats-next")),
    area=A("We found no crash reduction factor. NCHRP 15‑73 found they perform better than conventional bike lanes. So we give "
             "no square-mile figure.", cell="No crash figure"),
    cov=C(1, "9th and Division (2016) and a few more, against about 170 at 4 a square mile; Folsom's are under construction.", "https://www.sfmta.com/node/13725", "~1%")),
"bike-signals": dict(
    sq=Q("About 4, at signals where a protected bike lane meets heavy turns", "$50,000 to $250,000 a signal (Vision Zero band)", 200000, 1000000, False, None,
         ("Vision Zero SF tool table, p. 26", VZ)),
    area=A("We found no crash study. At two SF bike signals, right-turning drivers meeting a bike fell from 41% to 2%. So we give "
             "no square-mile figure.", cell="No crash study"),
    cov=C(2, "A handful: Fell and Masonic, Folsom and 8th, 8th and Brannan, 4th and Townsend, against about 170 at 4 a square mile.", "https://sfmta.com/media/17331/download", "~2%")),
# ------------------------------------------------------------------ network
"protected-bike-lanes": dict(
    sq=Q("About 2 miles: a half-mile grid on the main streets", "$0.89M to $1.61M a mile as a quick-build (SFMTA)", 1780000, 3220000, False, None,
         ("SFMTA quick-build budgets", QBQ)),
    area=A("FHWA, citing Dixon 2023: 53% fewer crashes between bikes and vehicles where posts separate the lane.",
             E(-53, "main_bikecar", T(2, MMI, f"about 2 of the {MMI:.1f} main-street miles, a half-mile grid"))),
    cov=C(61, "51 miles of protected bike lanes (SFMTA Board, Jan 2026), against about 84 at 2 a square mile.", DECK)),
"bike-slow-streets": dict(
    sq=Q("About 4 miles of residential street (a half-mile grid) and 12 diverters where they cross main streets",
         "$200,000 a mile (SFMTA) plus $22,790 a diverter (US), or $807,000 a mile on Page Street", 1070000, 3230000, False, None,
         ("SFMTA Board staff report 2022-12-06, p. 13", "https://www.sfmta.com/media/33575/download?inline"),
         ("PBIC 2013 cost report", PBIC)),
    area=A("We found no injury study of Fahrradstraßen. SF's partial version: SFMTA 2023 found reported collisions of all "
             "severities per mile fell 48% on Slow Streets against 14% citywide, so 40% net of the citywide trend (0.52 ÷ 0.86 is "
             "0.60). It is a weak before-after across the pandemic, on streets chosen because they were already quiet, so it may "
             "overstate. Legal priority and full diverters would cut more car traffic but draw more riders.",
             E(-40, "residential", T(4, RMI, f"about 4 of the {RMI:.1f} residential miles, a half-mile grid"))),
    cov=C(0, "None with legal bike priority, of about 168 miles a half-mile grid would need citywide (4 miles × 42 square miles): the California Vehicle Code has no such street type [inference — mine]. SF's 19 Slow Streets (about 15.7 miles, DataSF hkz3-itiu) are a partial version, with turn limits or diverters but no bike priority; 5 of the 19 have hard diverters. Counted as partial, they would be 9%.", "https://data.sfgov.org/d/hkz3-itiu", "0%")),
"low-traffic-neighborhoods": dict(
    sq=Q(f"About {FILTERS} filters at the edges of the cells the main streets make (one in five residential-only intersections)",
         "$19,000 to $40,000 a diverter (Sanchez Slow Street concrete islands, Prop L)", 323000, 680000, False, None,
         ("SFCTA CAC Prop L memo, Sept 2025", "https://www.sfcta.org/sites/default/files/2025-08/SFCTA_CAC_Item5_PropLAllocationsandNextGenSanchezAmendmentMEMO_2025-09-03.pdf")),
    area=A("Furlong et al. 2025, London: all injuries fell 35% inside low traffic neighborhoods (37% for killed or seriously "
             "injured), with no rise on boundary roads.",
             E(-35, "residential", ALL("every residential street, with filters at the edges of each cell the main streets make"))),
    cov=C(0, "None in SF: every Slow Street is a single corridor, and the Duboce Triangle circulation study is 'not a project that will lead to changes on the street'.", "https://www.sfmta.com/project-updates/winter-2025-slow-streets-program-update", "0%")),
"calmed-20mph-zones": dict(
    sq=Q(f"About {CALM_LO} to {CALM_HI} humps, tables or chicanes on the {RMI:.1f} residential miles (SFMTA's 150 to 250 ft spacing), and gateway signs where they meet the arterials",
         "$15,500 to $37,200 a device (SFCTA R26-06)", 5600000, 22300000, False, "The same devices as the speed hump row, plus a 20 mph limit and gateways.", ("SFCTA R26-06", R2606)),
    area=A("Grundy et al. 2009, London: 42% fewer casualties in 20 mph zones, against other roads. London's 1990s baseline had "
             "30 mph limits and more casualties than SF's residential streets today, so SF may see less.",
             E(-42, "residential", ALL(f"all {RMI:.1f} residential miles"))),
    cov=C(0, "SFMTA has no zone where devices hold a 20 mph limit; the Tenderloin's 20 mph is signs only.", "https://www.sfmta.com/blog/speed-and-turn-limits-boost-safety-tenderloin-streets-0", "0%")),
"20mph-default": dict(
    sq=Q("Gateway and repeater signs, about 25 to 60", "about $450 a sign (SF, 2012)", 11000, 27000, False, None,
         ("SFMTA press release 2012-05-14", "https://archives.sfmta.com/cms/apress/MayorLeeSFMTAandWalkSFAnnounceNewSaferSpeedZonesCompletedaround181SanFranciscoSchools.htm")),
    area=A("Edinburgh: 10% fewer casualties on the streets that changed against streets that stayed at 30 mph (Kokka et al. "
             "2024). The same paper finds about 20% fewer across the changed zones against control zones. We use the street-level "
             "10%, since SF would step down from 25 mph, less than Edinburgh's 30 to 20.",
             E(-10, "nonarterial", ALL("every street off the arterials"))),
    cov=C(0, "Not used; state law sets where SF may lower limits.", None, "0%")),
"school-streets": dict(
    sq=Q("About 4 schools (182 elementary, middle and K-12 schools, DataSF)", "$13,500 to $60,000 a school a year for staff (our estimate)", 54000, 240000, True, None,
         ("DataSF schools", "https://data.sfgov.org/d/7e7j-59qk"),
         ("SFMTA crossing guard costs", "https://www.sfmta.com/blog/prioritizing-safety-schools-citywide-update-our-crossing-guard-program")),
    area=A("We found no injury study. Studies measure how children travel, not injuries. So we give no square-mile figure.", cell="No injury study"),
    cov=C(0, "Only advocate-run event days, with SFMTA staff attending.", "https://www.sfmta.com/safe-school-connections-draft-approach-september-2026", "0%")),
"circulation-plan": dict(
    sq=Q("About 6 to 12 filters on the main streets at sector edges", "$19,000 to $40,000 a diverter (Sanchez, Prop L)", 114000, 480000, False, None,
         ("SFCTA CAC Prop L memo, Sept 2025", "https://www.sfcta.org/sites/default/files/2025-08/SFCTA_CAC_Item5_PropLAllocationsandNextGenSanchezAmendmentMEMO_2025-09-03.pdf")),
    area=A("Ghent's own evaluation says the injury link cannot be firmly shown (our translation from Dutch). So we give no "
             "square-mile figure.", cell="No clear effect"),
    cov=C(0, "Never proposed in SF.", None, "0%")),
"congestion-charge": dict(
    sq=dict(quantity_text="A cordon and its cameras around downtown", unit_cost="SFCTA's 2010 study: $60M to $100M up front for a downtown cordon, $65M a year to run, $145M a year in fares",
            total_low=80000000, total_high=80000000, per_year=True, band="revenue",
            assumptions=None,
            sources=[{"title": "SFCTA, Mobility, Access and Pricing Study, 2010, p. 53", "url": "https://www.sfcta.org/sites/default/files/2019-11/MAPS_study_final_lo_res.pdf"}]),
    area=A("Green, Heywood and Navarro, Journal of Public Economics 2016: 38% to 40% fewer crashes in London's zone during "
             "charging hours. A cordon works downtown, inside it, not across a typical square mile, so we give no square-mile figure.",
             cell="−38% inside the cordon"),
    cov=C(0, "Not used; SFCTA's downtown study is paused and state authority is needed.", "https://www.sfcta.org/downtown", "0%")),
"car-free-streets": dict(
    sq=Q("About half a mile of commercial street", "about $1.8M a mile (Market Street quick-build, $3.5M over 1.9 miles)", 900000, None, False, None,
         ("SFMTA blog 2020-01-23", "https://www.sfmta.com/node/21169")),
    area=A("Pontevedra's serious injuries fell from 129 in 1999 to 4 to 20 a year, citywide, over 20 years with no comparison "
             "city, and they are serious injuries only. That can't be scaled to all injury crashes on half a mile, so we give no "
             "square-mile figure.", cell="No clear figure"),
    cov=C(9, "Market Street, about 1.9 miles closed to private cars since 2020, against about 21 miles at half a mile a square mile. JFK Drive and the Upper Great Highway are car-free park roads, not commercial streets, so they aren't counted.", "https://www.sfmta.com/node/21169", "~9%")),
"transit-only-lanes": dict(
    sq=Q(f"About {HALF_ART:.2g} miles, the frequent-bus half of the {AMI:.1f} arterial miles", "under $0.5M a mile as a quick-build to about $5M a mile on Mission (SFMTA)", 650000, 6500000, False, None,
         ("SFMTA Board, Muni Forward Update, 2024-11-06, p. 7", "https://sfmta.com/media/41027/download")),
    area=A("SFMTA: 24% fewer injury collisions after red lanes on 3rd, Geary and O'Farrell. Muni-involved collisions there rose "
             "23%, 'though it increased at the same rate citywide at a time when Muni service and car traffic also increased'.",
             E(-24, "arterial", T(1, 2, f"the frequent-bus half of the {AMI:.1f} arterial miles"))),
    cov=C(round(100 * 38 / (HALF_ART * N_SQ)), f"About 75 lane miles of transit lanes, about 38 street miles counting both directions [inference — mine], against about {HALF_ART * N_SQ:.0f} at {HALF_ART:.2g} a square mile.", "https://www.sfmta.com/index%2Ephp/blog/decade-rolling-out-red-carpet-riders", f"~{100 * 38 / (HALF_ART * N_SQ):.0f}%")),
"parking-removal": dict(
    sq=dict(quantity_text="Curb space across a district", unit_cost="little capital, since the cost is lost meter and permit revenue", total_low=None, total_high=None,
            per_year=False, band="unknown", assumptions="No SF figure found.", sources=[]),
    area=A("We found no injury study, so we give no square-mile figure.", cell="No injury study"),
    cov=C(0, "Only as a side effect of single projects.", None, "0%")),
# ------------------------------------------------------------------ programs
"speed-cameras": dict(
    sq=Q(f"About {CAMS} cameras: one per half mile of the {HMI:.1f} miles of High Injury Network",
         "about $127,000 a camera in year one, then about $45,000 a camera a year for the vendor ($4.2M first-year spending and a ~$1.5M a year contract for 33 cameras, SFMTA)",
         3200000, None, False,
         f"That is gross. Year one is start-up heavy, since SFMTA's $4.2M includes $2.5M of staff time from Nov 2023 to June 2026. Net of fines: SFMTA projected $7.2M of revenue against $4.2M of spending in year one, about $218,000 against $127,000 a camera, so {CAMS} cameras raise about ${CAMS * 91:,}K net in year one. Fines should fall as drivers slow down [inference — mine]. SFMTA lists 'improved long term financial feasibility' as a next step. State law sends the rest to streets: 'Any excess revenue shall be used for traffic-calming measures' (Vehicle Code §22426(g)(2)).",
         ("SFMTA camera program update, 2026-05-06, p. 27", CAMDECK), ("Vehicle Code §22426(g)", VEH_22426)),
    area=A("FHWA, citing Li et al. 2015: 20% fewer fatal and injury crashes on urban arterials. We assume each camera reaches "
             f"about half a mile, so {CAMS} cameras cover the {HMI:.1f} miles of High Injury Network and the {AMI:.1f} arterial miles it mostly runs on. "
             f"Built in every square mile, that would take about {round(CAMS * N_SQ, -1)} cameras, against the 33 state law allows.",
             E(-20, "arterial", ALL(f"all {AMI:.1f} arterial miles, with {CAMS} cameras at half a mile each"))),
    cov=C(10, "33 cameras, the most state law allows a city SF's size (Vehicle Code §22425(b)(2)(B): 'no more than 33 systems'), reach about 16.5 miles at half a mile each, of SFMTA's 160-mile 2022 High Injury Network [inference — mine on the half-mile reach]. The pilot ends by January 1, 2032.", VEH_22425, "~10%"),
    net=f"year-one fines top cost by ${CAMS * 91}K",
    legal=("Blocked at 33 by AB 645, the state speed camera pilot: Vehicle Code §22425(b)(2)(B) allows a city of 800,000 to 3,000,000 people 'no more than 33 systems', and SF runs 33. Each may run 'for five years, or until January 1, 2032, whichever date is sooner' (§22426(i)). SFMTA's next steps include 'exploring expansion of number of locations'.",
           [("Vehicle Code §22425(b)(2)(B)", VEH_22425), ("§22426(i)", VEH_22426), ("SFMTA camera program update, 2026-05-06, pp. 27-28", CAMDECK)],
           "blocked at 33 by state law")),
"red-light-cameras": dict(
    sq=Q(f"About 2 to 3 of the {SGA} arterial signals, the highest-crash ones", "about $385,000 an intersection over a 3.75-year contract (SFMTA 2018), about $103,000 a year", 205000, 308000, True, None,
         ("SFMTA Board Res. 180821-112", "https://sfmta.com/media/14188/download")),
    area=A("FHWA 2005, injury crashes at camera signals: 15.7% fewer right-angle (broadside) crashes and 24.0% more rear-end "
             "crashes. SFMTA picks the highest-crash signals, so the average signal understates the gain somewhat.",
             E(-15.7, "sig_broadside", T(2.5, SG, f"about 2 or 3 of the {SG} signals, the highest-crash ones")),
             E(24.0, "sig_rearend", T(2.5, SG, "the same signals"))),
    cov=C(12, "13 intersections (19 approaches), six more due in 2026, against about 105 at 2.5 a square mile.", "https://www.sfmta.com/RedLight")),
"traffic-enforcement": dict(
    sq=dict(quantity_text="Officer-hours on the main streets", unit_cost="no SF cost per officer or operation found", total_low=None, total_high=None,
            per_year=True, band="unknown", assumptions="No source ties officer-hours to an effect.", sources=[]),
    area=A("TØI meta-analysis: more patrol cuts injury crashes about 2% (deaths about 18%), and the effect fades within days.",
             E(-2, "all", ALL("the whole square mile"))),
    cov=C(None, "Not a count of places. SFPD wrote 20,393 traffic citations in 2025, 16% of 2014's 127,861.", "https://www.sanfranciscopolice.org/stay-safe/crime-data/traffic-violation-reports", "no count")),
"crossing-guards": dict(
    sq=Q("About 7 guards at about 4 schools", "about $44,000 a school a year (SFMTA's $4M program)", 176000, None, True, None,
         ("SFMTA crossing guard update", "https://www.sfmta.com/blog/prioritizing-safety-schools-citywide-update-our-crossing-guard-program")),
    area=A("Toronto: no change in pedestrian crashes where guards were added (rate ratio 1.02), while more children walked. So "
             "we give no square-mile figure.", cell="No crash change"),
    cov=C(54, "174 guards at 98 of SF's 182 elementary, middle and K-12 schools; new requests are closed for lack of staff.", "https://www.sfmta.com/getting-around/walk/adult-school-crossing-guard-program")),
"fleet-safety": dict(
    sq=dict(quantity_text="Fitted on trucks, not streets", unit_cost="$900 to $1,800 a truck (US DOT, Boston, not SF)", total_low=None, total_high=None,
            per_year=False, band="unknown", assumptions="The city's truck fleet size was not found, so there is no per-square-mile figure.", sources=[]),
    area=A("UK: after side guards were required, cyclist deaths in side-impact truck crashes fell 61% and pedestrian deaths 20%. "
             "Those are deaths only, a tiny share of injury crashes, so we give no square-mile figure.", cell="Deaths only"),
    cov=C(0, "No SF side guard mandate found; driver training since 2015, telematics in progress.", None, "0%")),
# ------------------------------------------------------------------ muni
"muni-frequency": dict(
    sq=Q("Every bus line through the area, waits halved (10 to 5 minutes)", "$305 a bus hour (NTD FY2025)", 16200000, 18200000, True,
         None,
         ("NTD, SFMTA FY2025", "https://data.transportation.gov/d/ekg5-frzt")),
    area=A("Our model: fewer car trips times their injury risk, minus the crashes the added buses cause.", pct=FREQ_FX[1], work=FREQ_WORK),
    cov=C(None, "SFMTA 'cannot increase overall Muni service' within its budget; August 2026 changes are cost-neutral.", "https://www.sfmta.com/servicechanges", "no count")),
"transit-signal-priority": dict(
    sq=Q(f"About {TSP_N} signals on bus routes ({SG} signals × the 46% of SF's signals on Muni routes)", "$2,500 to $40,000 a signal (US, TCRP Synthesis 83)", 20000, 320000, False, None,
         ("USDOT ITS cost database", "https://www.itskrs.its.dot.gov/2013-sc00286")),
    area=A("We found no clear injury effect. Portland found no change in fatal and injury crashes, and more pedestrian and bike "
             "crashes. Faster buses win some riders, and those few can add or remove injuries, but we found no ridership study to "
             "size it. So we give no square-mile figure.", cell="No clear effect"),
    cov=C(75, "About 450 of about 600 signals on Muni bus routes (SFCTA, 2021; SFMTA, 2023).", "https://www.sfcta.org/sites/default/files/2021-10/Item%206%20-%20Grouped%20Allocations%20BD%20MEMO.pdf")),
"lower-fares": dict(
    sq=Q("Every fare paid in the area (the citywide average)", "$110M of Muni fare revenue a year (NTD FY2025)", 2340000, None, True,
         "Free Muni for all youth costs far less, about $62,000 to $144,000 a square mile a year.",
         ("NTD, SFMTA FY2025", "https://data.transportation.gov/d/ekg5-frzt")),
    area=A("Our model: car trips that switch to Muni, times the risk a car trip carries, minus the smaller risk each new Muni trip carries.",
             pct=FARE_FX[1], work=FARE_WORK),
    cov=C(None, "Free for everyone 18 and under since 2021; no fare cut for adults outside the income, senior and disability programs.", "https://www.sfmta.com/fares/free-muni-all-youth-18-years-and-younger", "youth only")),
}


# The cost arithmetic for each row, quantity × unit cost = total, checked against the row's total (cost_working).
CALC = {
    "daylighting": [K(IX, "intersections", 3667)],
    "hardened-daylighting": [K(2 * AX, "corners", 10000, n_hi=2 * MX)],
    "high-visibility-crosswalks": [K(4 * MX, "crosswalks", 3070)],
    "leading-pedestrian-interval": [K(SG, "signals", 10000, each_hi=50000)],
    "walk-speed": [K(SG, "signals", 10000, each_hi=50000)],
    "pedestrian-scrambles": [K(2, "signals", 8000, each_hi=150000)],
    "no-turn-on-red": [K(SG, "signals", 1900, each_hi=2800)],
    "turn-calming": [K(SG, "signals", 3700)],
    "bulb-outs": [K(BULBS, "corners", 10000, each_hi=184500)],
    "refuge-islands": [K(AU, "islands", 10000, each_hi=41000)],
    "raised-crossings": [K(RAISED, "raised crossings", 15000, each_hi=28600)],
    "flashing-beacons": [K(5, "crossings", 175000, each_hi=250000)],
    "street-lighting": [K(2 * MX, "poles", 3600, each_hi=43800)],
    "signal-upgrades": [K(SG, "signals", 424000, each_hi=540000)],
    "signal-progression": [K(SG, "signals", 10000)],
    "speed-humps": [K(HUMPS_N, "devices", 15500, each_hi=37200)],
    "traffic-circles": [K(CIRCLES, "circles", 20000, each_hi=25000)],
    "speed-radar-signs": [K(RADAR, "signs", 7500, each_hi=11150)],
    "lane-removal": [K(HALF_ART, "miles", 250000, each_hi=425000, per="a mile")],
    "lower-speed-limits": [K(SIGNS, "signs", 450)],
    "protected-intersections": [K(4, "intersections", 350000)],
    "bike-signals": [K(4, "signals", 50000, each_hi=250000)],
    "protected-bike-lanes": [K(2, "miles", 890000, each_hi=1610000, per="a mile")],
    "low-traffic-neighborhoods": [K(FILTERS, "filters", 19000, each_hi=40000)],
    "calmed-20mph-zones": [K(CALM_LO, "devices", 15500, n_hi=CALM_HI, each_hi=37200)],
    "20mph-default": [K(25, "signs", 450, n_hi=60)],
    "school-streets": [K(4, "schools", 13500, each_hi=60000, per="a year each")],
    "circulation-plan": [K(6, "filters", 19000, n_hi=12, each_hi=40000)],
    "car-free-streets": [K(0.5, "miles", 1800000, per="a mile")],
    "transit-only-lanes": [K(HALF_ART, "miles", 500000, each_hi=5000000, per="a mile")],
    "speed-cameras": [K(CAMS, "cameras in year one", 127000), K(9 * CAMS, f"camera years after that ({CAMS} cameras for 9 years)", 45000)],
    "red-light-cameras": [K(2, "camera intersections", 102667, n_hi=3, per="a year each")],
    "crossing-guards": [K(4, "schools", 44000, per="a year each")],
    "transit-signal-priority": [K(TSP_N, "signals", 2500, each_hi=40000)],
}
COST_WORK = {
    "bike-slow-streets": (f"Low: 4 miles × $200,000 a mile plus 12 diverters × $22,790 each = {_usd(4 * 200000 + 12 * 22790)}. "
                          f"High, at Page Street's cost: 4 miles × $807,000 a mile = {_usd(4 * 807000)}."),
    "congestion-charge": ("SFCTA's 2010 study: $145M a year in fares minus $65M a year to run = $80M a year net, for the whole downtown "
                          "cordon, after $60M to $100M up front. The study does not state the cordon's area, so there is no "
                          "figure for one square mile."),
    "muni-frequency": (f"Doubling Muni's 2.50 million bus revenue hours at $305 an hour costs about {_usd(2.5e6 * 305)} a year citywide. "
                       f"{_usd(2.5e6 * 305)} ÷ {GRID['land_sq_mi']:.1f} square miles of land = {_usd(2.5e6 * 305 / GRID['land_sq_mi'])} a square mile a year. "
                       f"Spread over only the {GRID['kept']} typical cells, it is {_usd(2.5e6 * 305 / GRID['kept'])}. The band counts ten years."),
    "lower-fares": ("Muni collects about $110M a year in fares. $110M ÷ 47.1 square miles of land = about $2.3M a square mile a year. The band "
                    "counts ten years."),
    "parking-removal": "We found no SF figure, so there is no total.",
    "traffic-enforcement": "We found no SF cost per officer or operation, so there is no total.",
    "fleet-safety": "The city's truck fleet size was not found, so there is no total for a square mile.",
}
for _k, _o in OVER.items():
    _q = _o["sq"]
    if _k in CALC:
        _lo = sum(t["n"] * t["each"] for t in CALC[_k]); _hi = sum(t["n_hi"] * t["each_hi"] for t in CALC[_k])
        _q["total_low"], _q["total_high"] = int(round(_lo, -3)), int(round(_hi, -3))
        _q["working"] = cost_working(CALC[_k], _q["total_low"], _q["total_high"], _q["per_year"]) + (" That covers ten years." if _k == "speed-cameras" else "")
    else:
        _q["working"] = COST_WORK[_k]
    assert ";" not in _q["working"] and "—" not in _q["working"], _k

# The figure under the effect cell when it is not the row's headline study figure.
SUB = {
    "low-traffic-neighborhoods": "London study: −35% injuries",
    "no-turn-on-red": "SFMTA: turn-on-red crashes under 1%",
    "red-light-cameras": "study: −16% right-angle, +24% rear-end injury crashes",
    "muni-frequency": f"our model, {FREQ_FX[0]:+.1f}% to {FREQ_FX[2]:+.1f}%".replace("-", "−"),
    "lower-fares": f"our model, {FARE_FX[0]:+.1f}% to {FARE_FX[2]:+.1f}%".replace("-", "−"),
    "high-visibility-crosswalks": "FHWA: up to −40% pedestrian",
    "flashing-beacons": "FHWA: up to −47% pedestrian",
    "street-lighting": "study: lit vs. unlit corners",
    "speed-humps": "study: −40% injury crashes",
    "daylighting": "Tenderloin −14%; NYC none",
    "hardened-daylighting": "NYC: −32% pedestrian, none for all",
    "turn-calming": "NYC: pedestrians −18%, all users +0.3%",
    "pedestrian-scrambles": "study: −51% pedestrian, +10% between vehicles",
    "traffic-circles": "depends on the stop signs",
    "congestion-charge": "London study",
    "car-free-streets": "Pontevedra −84% serious, no control",
    "signal-upgrades": "backplates −15%, not this cost",
}
for _k, _v in SUB.items():
    OVER[_k]["area"]["sub"] = _v

ORDER = {
    "spot": ["daylighting", "hardened-daylighting", "high-visibility-crosswalks", "leading-pedestrian-interval", "walk-speed",
             "pedestrian-scrambles", "no-turn-on-red", "turn-calming", "bulb-outs", "refuge-islands", "raised-crossings",
             "flashing-beacons", "street-lighting", "signal-upgrades", "signal-progression", "speed-humps", "traffic-circles",
             "speed-radar-signs", "lane-removal", "lower-speed-limits", "protected-intersections", "bike-signals"],
    "network": ["protected-bike-lanes", "bike-slow-streets", "low-traffic-neighborhoods", "calmed-20mph-zones", "20mph-default",
                "school-streets", "circulation-plan", "congestion-charge", "car-free-streets", "transit-only-lanes", "parking-removal"],
    "programs": ["speed-cameras", "red-light-cameras", "traffic-enforcement", "crossing-guards", "fleet-safety"],
    "muni": ["muni-frequency", "transit-signal-priority", "lower-fares"],
}

# Plan text that opposes or severely limits a tool, verbatim from the source opened on 2026-10-23.
# Street Safety Initiative column only. ED 25-06's principle is applied to car-free streets, which it plainly covers;
# whether it also limits LTNs and circulation plans is a question for Bryan, so those rows carry no mark.
ED_QUOTE = "Safety interventions aim to reduce injuries, not limit how or where people can travel."
LIMITS = {
    "traffic-circles": ("street_safety_initiative", SDRM, "SFMTA and SFFD Street Design Review Manual (SSI Action 17), p. 32: circles are allowed, but this clear width keeps them off most narrow residential corners, so it severely limits where",
                        "Distance from curb to face of Traffic Circle: 20’ minimum"),
    "raised-crossings": ("street_safety_initiative", SDRM, "SFMTA and SFFD Street Design Review Manual (SSI Action 17), p. 29",
                         "SFFD Has Highlighted Significant Concerns Regarding: Installation on intersections that would require apparatuses to slow down or stop twice for both raised crosswalks at the intersection"),
    "car-free-streets": ("street_safety_initiative", MAYOR_ED, "Mayor's Executive Directive 25-06, p. 2, Core Safety Principles", ED_QUOTE),
}

BANDS = {
    "cutoffs": {"$": {"max": 250000, "label": "under $250K"},
                "$$": {"max": 2500000, "label": "$250K to $2.5M"},
                "$$$": {"max": None, "label": "over $2.5M"}},
    "note": "A yearly cost counts ten years. The figure under each band is the range for one typical square mile.",
}
LISTS = [
    {"title": "FHWA's Proven Safety Countermeasures (all 28, June 2026)", "url": "https://web.archive.org/web/20260627183202/https://highways.dot.gov/safety/proven-safety-countermeasures"},
    {"title": "Vision Zero SF's tool table (pp. 26-27)", "url": VZ},
    {"title": "NYC's Street Design Manual", "url": "https://www.nycstreetdesign.info/geometry"},
]
SKIPPED = ("Left out as rural or freeway tools: rumble strips, median barriers, SafetyEdge, wider edge lines, curve "
           "delineation, roadside design at curves and variable speed limits. Left out as suburban designs: reduced "
           "left-turn conflict intersections and corridor access management. Left out as planning processes: road safety "
           "audits and local road safety plans. Folded in: turn lanes into Removing a car lane, stop-sign sight-line work "
           "into Daylighting, chicanes into Calmed 20 mph zones, plazas and shared streets into Car-free streets, busways "
           "into Transit-only lanes, AB 43 limits into Lower speed limits, Vision Zero's painted safety zones into Bulb-outs, its new traffic signals and quick-build program into Bigger, brighter signals, and NYC's mid-block narrowing and gateways into Calmed 20 mph zones, its greenways into Bike priority slow streets, and its conventional and two-way bike lanes into Protected bike lanes. Left out as transit or sidewalk design rather than safety tools: NYC's bus bulbs and boarding islands and sidewalk expansion. Also left out: walkways, since SF streets "
           "nearly all have sidewalks, and pavement friction, which FHWA aims at curves, ramps and fast approaches (our judgement).")
