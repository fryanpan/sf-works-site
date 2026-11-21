"""Source data for the broader-toolkit table: one dict per tool. Read by build.py,
which writes data/toolkit/tools.json and the two PlotChart MDX files."""

VZ = "https://visionzerosf.org/wp-content/uploads/2021/11/VZSF_AS_111021_spreads-FINAL.pdf"
VZ_T = "Vision Zero SF Action Strategy 2021-2024, pp. 25-26"
# The tool table with its cost bands is printed on pp. 26-27; the bands carry no unit and are "based on national data".
VZ_TAB = "Vision Zero SF Action Strategy 2021-2024, tool table pp. 26-27 (bands based on national data, no unit printed)"
SIXTH_2019 = "https://www.sfmta.com/node/20133"
# Provenance for facts the Fable data review of 2026-10-23 opened and corrected.
F = " [primary — read 2026-10-23, Fable review]"
TFW_2025 = "https://tfw.wales/national-monitoring-report-july-2025"
EXAMINER_D4 = "https://www.sfexaminer.com/news/politics/great-highway-ballot-measure-district-4-alan-wong/article_d4e08c58-79c5-4efd-96ec-e5625151bc13.html"
MISSION_OK = "https://www.sfmta.com/project-updates/mission-street-changes-approved-sfmta-board"
SSC = "https://www.sfmta.com/safe-school-connections-draft-approach-september-2026"
SRTS = "https://www.sfsaferoutes.org/documents/2026/SFSRTS_Report_final_spreads_low_res.pdf"
SSI = "https://www.sf.gov/street-safety-initiative"
SSA = "https://sfgov.legistar.com/View.ashx?M=F&ID=14821038&GUID=E014E308-33EC-4EEF-B09B-CB0EEC48A3C2"
DECK = "https://www.sfmta.com/media/44242/download"
CAMDECK = "https://www.sfmta.com/media/44957/download?inline"
WB = "https://web.archive.org/web/2026/https://highways.dot.gov/safety/proven-safety-countermeasures/"
QB = "https://sfmta.com/media/41107/download"
SLOW = "https://www.sfmta.com/projects/slow-streets-program"
SLOW_SR = "https://www.sfmta.com/media/33575/download?inline"
SLOW_MIN = "https://www.sfmta.com/media/33981/download?inline"
R2606 = "https://www.sfcta.org/sites/default/files/2025-07/R26-06%20TNC%20Allocations.pdf"
CGJ = "https://media.api.sf.gov/documents/2025_CGJ_Report_Failed_Vision.pdf"
KQED_CALM = "https://www.kqed.org/news/12045959/sf-ends-program-allowing-residents-to-request-street-safety-improvements"
CALM141 = "https://www.sfmta.com/blog/making-your-streets-safer-traffic-calming-coming-141-locations-across-san-francisco"
GROWSF = "https://growsf.org/pulse/growsf-pulse-may-2024/"
MAYOR_ED = "https://media.api.sf.gov/documents/Street_Safety_ED.pdf"
MF = "https://sfmta.com/media/41027/download"
REDLANES = "https://www.sfmta.com/blog/red-transit-only-lanes-work-two-new-studies-show-their-benefits"
GRUNDY = "https://pubmed.ncbi.nlm.nih.gov/20007666/"
FURLONG = "https://pubmed.ncbi.nlm.nih.gov/40623802/"
TESTER = "https://doi.org/10.2105/ajph.94.4.646"
KOKKA = "https://pmc.ncbi.nlm.nih.gov/articles/PMC11187370/"
DFT = "https://assets.publishing.service.gov.uk/media/5bf2ba08ed915d1830158998/20mph-technical-report.pdf"
GREEN = "https://www.lancaster.ac.uk/media/lancaster-university/content-assets/documents/lums/economics/working-papers/LondonCongestionCharge.pdf"
GHENT = "https://stad.gent/sites/default/files/onepager/cta/Evaluatierapport%20Circulatieplan%20Gent%202019%20finaal.pdf"
VRT = "https://www.vrt.be/vrtnws/en/2017/03/31/death_threats_oneveofbigmobilityplaninghent-1-2938418/"
DGT = "https://www.dgt.es/.galleries/downloads/conoce_la_dgt/que-hacemos/estrategias-y-planes/Experiencias-urbanas/pdf/84000-Pontevedra.pdf"
OSLO = "https://www.oslo.kommune.no/byutvikling/bilfritt-byliv-2016-2023/"
TFL_OSLO = "https://content.tfl.gov.uk/vision-zero-case-study-oslo.pdf"
HOBOKEN = "https://hobokennj.gov/news/hoboken-to-reduce-speed-limit-to-20-mph-citywide"
HANTS = "https://democracy.hants.gov.uk/documents/s116625/School%20Streets.pdf"
CONTROLLER_VAL = "https://www.sf.gov/sites/default/files/2024-06/Valencia%20Economic%20Context%20final.pdf"
ELECTIONS = "https://www.sfelections.org/results/20241105/"
ML_RECALL = "https://missionlocal.org/2025/09/sf-district-4-joel-engardio-election-results/"
JFK_SFMTA = "https://www.sfmta.com/projects/golden-gate-park-access-and-safety-program"
PROPJ = "https://www.sfpublicpress.org/proposition-j-recreational-use-of-jfk-drive-in-golden-gate-park/"
STREETSBLOG_MKT = "https://sf.streetsblog.org/2020/10/28/city-betrays-advocates-with-bummer-market-street"
STREETSBLOG_MISSION = "https://sf.streetsblog.org/2016/08/10/sfmta-readies-limited-roll-back-on-mission-transit-project/"
SB_CAMPOS = "https://sf.streetsblog.org/2016/04/18/mission-businesses-tussle-with-transit-advocates-over-bus-lanes"
LPI_BLOG = "https://www.sfmta.com/about-sfmta/blog/giving-pedestrians-head-start"
DAYLIGHT_BLOG = "https://www.sfmta.com/blog/making-trips-school-safer-across-city-new-daylighting-program"
SFCTA_DAYLIGHT = "https://www.sfcta.org/blogs/hands-learning-about-californias-daylighting-law-new-traditions-elementary"
CAMS = "https://www.sfmta.com/reports/approved-automated-speed-enforcement-camera-locations"
TL20 = "https://www.sfmta.com/blog/speed-and-turn-limits-boost-safety-tenderloin-streets-0"
SIXTH = "https://www.sfmta.com/blog/creating-sustainable-change-downtown-san-francisco"
SIXTH_EVAL = "https://www.sfmta.com/media/42943/download"
VALENCIA = "https://sfmta.com/projects/valencia-bikeway-improvements"
PAGE = "https://sfmta.com/media/33975/download"
HUMPS_DATA = "https://data.sfgov.org/d/abhw-ffzx"
SAMPLE14 = "https://www.sfmta.com/14rapid"
SCHOOL_ZONE_2012 = "https://archives.sfmta.com/cms/apress/MayorLeeSFMTAandWalkSFAnnounceNewSaferSpeedZonesCompletedaround181SanFranciscoSchools.htm"
GUARDS = "https://www.sfmta.com/blog/prioritizing-safety-schools-citywide-update-our-crossing-guard-program"
WALKSF_SZ = "https://walksf.org/2026/07/23/sfmta-expanded-school-zones-and-lower-speed-limits-are-a-win-for-kids-and-neighborhoods/"
TRB269 = "https://www.nationalacademies.org/read/10409/chapter/2"
TESCHKE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC3519333/"
MORENCY = "https://pmc.ncbi.nlm.nih.gov/articles/PMC5906382/"
PROPL_SLOW = "https://www.sfcta.org/sites/default/files/2025-08/SFCTA_CAC_Item5_PropLAllocationsandNextGenSanchezAmendmentMEMO_2025-09-03.pdf"
PAGE_CIP = "https://www.sfmta.com/media/39080/download"
ELIASSON = "https://www.transportportal.se/swopec/CTS2014-1.pdf"
SFCTA_PRICING = "https://www.sfcta.org/downtown"

CENSUS_GAZ = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_counties_national.zip"
CENTERLINES = "https://data.sfgov.org/d/3psu-pn9h"
OSM_SIGNALS = "https://wiki.openstreetmap.org/wiki/Tag:highway%3Dtraffic_signals"
FHWA_LIST = "https://web.archive.org/web/20260627183202/https://highways.dot.gov/safety/proven-safety-countermeasures"

# A typical SF square mile. Land area 46.914 sq mi (Census 2020 Gazetteer, county 06075) [primary — read 2026-10-23].
# Street counts from DataSF centerlines 3psu-pn9h, active segments on the STREETS layers, freeways, ramps and
# paper streets left out [DataSF 3psu-pn9h — queried 2026-10-23]: 1,060 street miles (18 class 2, 117 class 3,
# 161 class 4, 763 class 5), 6,956 intersections (nodes where 3+ segments meet), 2,768 touching a class 2-4
# street, 1,109 touching a class 2-3 street, 4,188 on residential streets only, 10,414 residential segments.
# Signals: 2,285 OpenStreetMap traffic_signals nodes snapped to 1,294 intersections (Overpass, 2026-10-23).
SQ = dict(street_mi=22.6, arterial_mi=2.9, collector_mi=3.4, main_mi=6.3, residential_mi=16.3,
          intersections=148, main_x=59, arterial_x=24, residential_x=89, residential_blocks=222, signals=28)
SQUARE_MILE = dict(
    text=("SF has 46.9 square miles of land and 1,060 miles of city streets, so a typical square mile holds about "
          "22.6 street miles (6.3 on main streets, meaning arterials and collectors, and 16.3 residential), 148 intersections "
          "(59 on a main street, 89 on residential streets only), about 220 residential blocks and about 28 traffic signals. "
          "Each tool is counted only where it goes: main-street tools on main-street corners or miles, residential tools "
          "on residential blocks, signal tools at signals, and area tools at the edges of the area. Signals are OpenStreetMap's count, "
          "not SFMTA's inventory, which DataSF doesn't publish."),
    counts=SQ,
    sources=[{"title": "Census 2020 land area", "url": CENSUS_GAZ},
             {"title": "DataSF street centerlines", "url": CENTERLINES},
             {"title": "OpenStreetMap signals", "url": OSM_SIGNALS}])
SFMTA_RULE = ("SFMTA today is filled only when SFMTA uses the tool widely: a standing citywide practice at hundreds of "
              "places or many miles, or at a quarter or more of the places it suits. A pilot, a state-capped program "
              "or a handful of sites gets the hollow dot.")

def P(ssc=None, srts=None, mta=None, ssi=None):
    """Program marks. Each is (status, url, note) or (status, url, note, quote) or None."""
    def one(v):
        if v is None:
            return None
        s, u, n, *q = v
        out = {"status": s, "source_url": u, "note": n}
        if q:
            out["quote"] = q[0]
        return out
    return {"safe_school_connections": one(ssc), "safe_routes": one(srts),
            "other_sfmta": one(mta), "street_safety_initiative": one(ssi)}

def U(walking, biking, transit, driving, kids):
    out = {}
    for k, v in zip(["walking", "biking", "transit", "driving", "kids_school_trip"], [walking, biking, transit, driving, kids]):
        pros, cons, url, note = v
        out[k] = {"pros": pros, "cons": cons, "evidence_url": url, "evidence_note": note}
    return out

TOOLS = [
# ---------------------------------------------------------------- spot fixes
dict(
  id="daylighting", name="Daylighting", group="spot",
  one_line="Red curbs that keep parked cars 20 feet back from a crosswalk, so people driving and crossing can see each other.",
  cost=dict(text="SFCTA's $1.1M paid for about 300 intersections, about $3,700 each; Vision Zero's lowest band is under $10,000 (national data, per intersection is our reading [inference — mine])", short="About $3.7K an intersection",
            value_low=3667, value_high=10000, unit="per intersection",
            source_url=SFCTA_DAYLIGHT, source_title="SFCTA, Hands-On Learning About California's Daylighting Law, 2025-05-16 [primary — read 2026-09-29, repo note]; " + VZ_TAB + F),
  effect=dict(text="14% fewer collisions after daylighting across the Tenderloin", short="-14% collisions", pct=-14,
              outcome="crashes", design="before-after", where="Tenderloin",
              source_url=VZ, source_title=VZ_T + " [primary — read 2026-10-22]"),
  opposition=dict(grade="Low",
    reason="State law (AB 413) requires it, and SFMTA has done 65% of the city's intersections with no reported reversal.",
    examples=[{"text": "65% of citywide intersections daylit as of May 2026 (Street Safety Initiative, Action 7)", "url": SSI},
              {"text": "71% of voters rate daylighting important (GrowSF poll, May 2024) [secondary — verify]", "url": GROWSF}]),
  programs=P(ssc=("in", SSC, "Daylighting and Safety Zone Program is one of the school programs the draft coordinates"),
             srts=("in", SRTS, "Section X: almost 2,000 crosswalks near schools daylit by September 2025"),
             mta=("in", VZ, "Vision Zero tool table p. 26; Daylighting and Safety Zone Program"),
             ssi=("in", SSI, "Action 7, 65% of intersections done; Street Safety Act 1(d) adds hardened daylighting on the HIN")),
  sf_example=dict(name="New Traditions Elementary, 2049 Grove Street (launch of the School Daylighting Program)", year=2025,
                  lat=37.774271, lon=-122.450187, geometry_hint="point", source_url=DAYLIGHT_BLOG),
  by_user=U(
    ("Drivers see people at the corner sooner; children are no longer hidden by parked cars.", "Paint alone does not stop illegal parking in the red zone.", DAYLIGHT_BLOG, "SFMTA says children 'often can't see past a parked car'. The crash effect is the Tenderloin's 14%, a before-after count."),
    ("Clearer sight lines at corners.", "None measured.", None, "[inference — mine]"),
    ("Clear corners help buses turn.", "None measured.", None, "[inference — mine]"),
    ("Better view of crossing traffic and people.", "Loses about one parking space per corner approach.", DAYLIGHT_BLOG, "The state law bans parking within 20 feet of the approach side of a crosswalk."),
    ("Corners within 600 feet of public schools, the rollout's second stage after the High Injury Network.", "Does not slow cars or shorten the crossing.", DAYLIGHT_BLOG, "Schools were stage two of SFMTA's rollout, due by the end of 2025."))),
dict(
  id="leading-pedestrian-interval", name="Leading pedestrian intervals", group="spot",
  one_line="The walk signal turns on at least three seconds before the green light, so people are already in the crosswalk when drivers start to turn.",
  cost=dict(text="$10,000 to $50,000, Vision Zero's second band (national data; per intersection is our reading [inference — mine])", short="$10K-$50K a signal",
            value_low=10000, value_high=50000, unit="per intersection [inference — mine]", source_url=VZ, source_title=VZ_TAB + " ($$)" + F),
  effect=dict(text="13% fewer pedestrian-vehicle crashes at intersections", short="-13% pedestrian crashes", pct=-13,
              outcome="crashes", design="before-after", where="FHWA",
              source_url=WB + "leading-pedestrian-interval", source_title="FHWA Proven Safety Countermeasures, Leading Pedestrian Interval, Wayback snapshot [primary — read 2026-10-22]; the 13% is CMF 9918, Goughnour et al. 2018, an empirical Bayes before-after study" + F),
  opposition=dict(grade="Low",
    reason="A signal timing change that takes no parking or lane, and SFMTA has changed signals at about 1,500 intersections.",
    examples=[{"text": "60 intersections got LPIs in 2015 alone (SFMTA)", "url": LPI_BLOG},
              {"text": "Signal changes at 1,500 intersections so far (SFMTA Board, Jan 2026)", "url": DECK}]),
  programs=P(mta=("in", VZ, "Vision Zero tool table p. 26; SFMTA has installed LPIs since 1999"),
             ssi=("considered", DECK, "Street Safety Commitments deck, Jan 2026: signal changes at 1,500 intersections; the deck does not say how many are LPIs")),
  sf_example=dict(name="Eddy and Mason streets, the city's worst corner for left-turn pedestrian injuries before its LPI", year=2015,
                  lat=37.784349, lon=-122.409309, geometry_hint="point", source_url=LPI_BLOG),
  by_user=U(
    ("A head start into the crosswalk before turning cars move.", "Adds a few seconds of waiting for the whole cycle.", WB + "leading-pedestrian-interval", "FHWA: 13% fewer pedestrian-vehicle crashes. At Eddy and Mason, SFMTA reported no left-turn pedestrian injuries in eight months after the LPI, against eight in 2012 to 2015."),
    ("People on bikes can use the head start too where signals allow.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "A small loss of green time.", None, "[inference — mine]"),
    ("Turning drivers meet people already in plain view.", "About three seconds less green for turns.", LPI_BLOG, "SFMTA: walk shows 'at least three seconds' before the green."),
    ("Helps the slowest crossers most.", "Only at signals, and most school corners near homes have stop signs.", None, "[inference — mine]"))),
dict(
  id="speed-humps", name="Speed humps, cushions and tables", short_name="Speed humps", group="spot",
  one_line="Raised bumps across a block that slow drivers to about 15 to 20 mph where they sit.",
  cost=dict(text="About $28,600 a device all-in; $0.33M to $1.3M a mile at SFMTA's 150 to 250 ft spacing [inference — mine]", short="$29K a hump",
            value_low=15517, value_high=37169, unit="per device",
            source_url=R2606, source_title="SFCTA Resolution 26-06 (FY21 to FY23 traffic calming cycles) and SFCTA 2021 enclosure [primary — read 2026-10-22, repo note]"),
  effect=dict(text="40% fewer injury crashes on local streets with speed humps (Elvik and Vaa meta-analysis); for children, 53% lower odds of being hit near home where humps were present (Tester et al. 2004, case-control)", short="-40% injury crashes", pct=-40,
              outcome="all injuries", design="meta-analysis", where="Elvik and Vaa 2004",
              source_url="https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=132", source_title="CMF Clearinghouse 132, Install speed humps, Elvik and Vaa 2004, CMF 0.60 (SE 0.16), injury crashes A-C, local two-lane urban and suburban streets [primary — read 2026-10-23]; Tester et al., AJPH 2004, adjusted OR 0.47 (" + TESTER + ") [primary — read 2026-10-23, abstract]"),
  opposition=dict(grade="Low",
    reason="Residents ask for them: demand outran the program, and SFMTA paused new requests in July 2025 with a backlog.",
    examples=[{"text": "Over 1,200 devices since 2018, more than 500 requested by residents; program paused (KQED) [secondary — verify]", "url": KQED_CALM},
              {"text": "'An unprecedented number of applications'; 141 approved locations being built (SFMTA, Nov 2025)", "url": CALM141}]),
  programs=P(ssc=("in", SSC, "Physical infrastructure toolkit: speed humps/tables"),
             srts=("in", SRTS, "Section X: walk audits add speed tables and raised crosswalks"),
             mta=("in", CALM141, "Residential Traffic Calming Program (new applications paused); Vision Zero tool table"),
             ssi=("considered", SSI, "Action 23, updated program in progress; Street Safety Act 1(g) asks for a proactive plan by December 2026; deck plans 300 treatments")),
  sf_example=dict(name="Hugo Street from 6th to 7th Avenue, resident-requested speed hump", year=2026,
                  lat=37.765090, lon=-122.463702, geometry_hint="lat/lon is the straight-line midpoint; street segment: Hugo St, 6th Ave (37.765114,-122.463167) to 7th Ave (37.765067,-122.464237)",
                  source_url=HUMPS_DATA),
  by_user=U(
    ("Slower cars on the block; children hit near home far less often.", "Only covers the blocks that asked.", TESTER, "Matched case-control: adjusted OR 0.47 for injury within the neighbourhood, 0.40 in front of the home."),
    ("Calmer mixed traffic on residential streets.", "Bumpy unless built with bike gaps.", None, "[inference — mine]"),
    ("Speed cushions let buses pass more easily.", "Humps slow buses where cushions aren't used.", CALM141, "SFMTA: cushions have 'wheel slots to help emergency vehicles and buses pass'."),
    ("Predictable, and no parking lost.", "Slower trips on the block; noise.", None, "[inference — mine]"),
    ("Best-measured child benefit of any spot fix.", "Requests come from organized blocks.", CALM141, "The program is 'resident driven'; the Street Safety Act asks for a proactive, data-driven replacement."))),
dict(
  id="quick-build-road-diet", name="Quick-build road diets", group="spot",
  one_line="Paint and posts that take a travel lane away and turn it into turn pockets, loading or a buffer, installed in months.",
  cost=dict(text="$0.9M to $1.6M a mile, using five SFMTA bikeway quick-build budgets as a proxy", short="$0.9M-$1.6M a mile",
            value_low=890000, value_high=1610000, unit="per mile",
            source_url=QB, source_title="SFMTA protected-bikeway quick-build budgets at Board approval (17th St, Mid-Valencia, Winston, Frida Kahlo, Beach), used as a proxy for road diets [primary — read 2026-09-29, repo note]"),
  effect=dict(text="19% to 47% fewer crashes, converting four lanes to three", short="-19% to -47% crashes", pct=-19,
              outcome="crashes", design="before-after", where="FHWA",
              source_url=WB + "road-diets-roadway-reconfiguration", source_title="FHWA Proven Safety Countermeasures, Road Diets, Wayback snapshot [primary — read 2026-10-22]; removed from FHWA's list in 2026 without a safety reason"),
  opposition=dict(grade="Medium",
    reason="Projects are fought one street at a time, and the Mayor's directive limits quick-builds to places 'where data shows they are necessary'.",
    examples=[{"text": "Street Safety Initiative Action 6 wording", "url": SSI},
              {"text": "Civil Grand Jury: open-ended outreach causes 'wild swings on high profile projects' (p. 28)", "url": CGJ}]),
  programs=P(mta=("in", VZ, "Vision Zero tool table p. 26; Quick-Build Program, 40 projects over six years"),
             ssi=("considered", SSI, "Action 6 names a priority quick-build list; 8 projects 'through approval process' in the Jan 2026 deck. No source names lane removal")),
  sf_example=dict(name="6th Street quick-build, one southbound travel lane removed (the four-to-three change came with the 2024 capital project)", year=2019,
                  lat=37.780985, lon=-122.408726, geometry_hint="lat/lon is the straight-line midpoint; street segment: 6th St, Market St (37.782231,-122.410292) to Howard St (37.779739,-122.407159)",
                  source_url=SIXTH_2019),
  by_user=U(
    ("Fewer lanes to cross and slower cars.", "Paint and posts don't widen the sidewalk.", SIXTH, "SFMTA reported a 21% drop in average speeds on 6th Street after its quick-build. Its later capital-project evaluation found the 85th percentile speed fell from 25 to 24 mph."),
    ("Room for a bike lane or buffer.", "Only if the freed lane goes to bikes.", None, "[inference — mine]"),
    ("Fewer lane changes in front of buses.", "Buses can slow behind a single lane of cars.", None, "[inference — mine]"),
    ("Fewer crashes and less weaving.", "Slower peak trips on that street.", WB + "road-diets-roadway-reconfiguration", "FHWA: 19% to 47% fewer total crashes, four lanes to three."),
    ("Arterials near schools get calmer.", "Helps only on the street treated.", None, "[inference — mine]"))),
dict(
  id="speed-cameras", name="Speed cameras", group="spot",
  one_line="Fixed cameras that mail a ticket to drivers speeding past them, without a police stop.",
  cost=dict(text="Gross: about $4.2M all-in for the first year for 33 cameras, about $127,000 a camera; the vendor contract is about $1.5M a year. Net: SFMTA projected about $7.2M of fines in year one, so the program raises about $3M more than it costs at first, falling as drivers slow down [inference — mine on the decline]", short="$127K a camera, year one",
            value_low=127000, value_high=None, unit="per camera, first year all-in",
            source_url=CAMDECK, source_title="SFMTA, Speed Safety Camera Program update to the Vision Zero Committee, 2026-05-06 [primary — read 2026-10-23]"),
  effect=dict(text="20% fewer fatal and injury crashes on urban arterials with mobile cameras (FHWA, citing Li et al. 2015). FHWA's 47% is a fixed-camera freeway study (Shin 2009, Arizona SR 101)", short="-20% injury crashes", pct=-20,
              outcome="crashes", design="not stated", where="FHWA",
              source_url=WB + "speed-safety-cameras", source_title="FHWA Proven Safety Countermeasures, Speed Safety Cameras, Wayback snapshot [primary — read 2026-10-22]; removed from FHWA's list in 2026" + F),
  opposition=dict(grade="Low",
    reason="Popular with voters; the limit is state law, which caps SF at 33 cameras.",
    examples=[{"text": "71% of voters rate speed cameras important (GrowSF, May 2024) [secondary — verify]", "url": GROWSF},
              {"text": "SFMTA Board approved the 33 locations unanimously (SF Examiner, Apr 2024); list of sites", "url": CAMS}]),
  programs=P(ssc=("in", SSC, "Speed Management Strategies: speed safety cameras, listed among school programs"),
             srts=("in", SRTS, "Section X: 33 camera locations near schools and busy streets, citations from 2025-08-05"),
             mta=("in", CAMDECK, "Speed Safety Camera Program"),
             ssi=("in", SSI, "Action 8; Street Safety Act 1(c)")),
  sf_example=dict(name="Geary Boulevard from 7th to 8th Avenue, site 3 on the approved-locations list", year=2025,
                  lat=37.780945, lon=-122.465890, geometry_hint="lat/lon is the straight-line midpoint; street segment: Geary Blvd, 7th Ave (37.780965,-122.465353) to 8th Ave (37.780925,-122.466427)",
                  source_url=CAMS),
  by_user=U(
    ("Fewer fast drivers on the busiest streets.", "33 sites only.", CAMDECK, "SFMTA camera program update, pp. 21-22: drivers going 10 mph or more over are down nearly 80% across camera sites."),
    ("Slower traffic beside bike lanes.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "None measured.", None, "No transit effect studied."),
    ("Even, automatic enforcement without a stop.", "Tickets.", CAMDECK, "Net revenue goes to traffic calming, about $3M a year."),
    ("Several sites are in school zones.", "Few cameras on the small streets near most schools.", SRTS, "SRTS: cameras placed 'near schools and along busy streets'."))),
dict(
  id="lower-speed-limits", name="Lower speed limits on corridors (signs)", short_name="Lower limits, signs only", group="spot",
  one_line="New 20 or 25 mph signs on a named corridor or school zone, with no change to the street.",
  cost=dict(text="$10,000 to $50,000, Vision Zero's second band (national data; per corridor is our reading [inference — mine])", short="$10K-$50K a corridor",
            value_low=10000, value_high=50000, unit="per corridor [inference — mine]", source_url=VZ, source_title=VZ_TAB + " ($$)" + F),
  effect=dict(text="20% fewer crashes after Seattle's sign change, a figure Vision Zero SF prints with no reference or study design; a UK study found no clear change from signs alone", short="-20% crashes; UK: no clear change", pct=-20,
              outcome="crashes", design="not stated", where="Seattle (unreferenced)",
              source_url=VZ, source_title="Vision Zero SF Action Strategy 2021-2024, p. 27, citing Seattle, unreferenced [secondary — verify]; DfT 20mph research, 2018 [primary — read 2026-10-22, repo note]"),
  opposition=dict(grade="Low",
    reason="86 corridors have been cut with little fight; advocates ask for more, and state law sets where SF may lower limits.",
    examples=[{"text": "86 corridors with reduced limits, 35 more planned (SFMTA Board, Jan 2026)", "url": DECK},
              {"text": "Walk SF asked for lower limits 'in all school zones as much as the new law allows'", "url": WALKSF_SZ}]),
  programs=P(ssc=("in", SSC, "Speed Management Strategies: speed limit signs"),
             mta=("in", "https://www.sfmta.com/sfmta-school-safety-programs", "Over 100 miles of lower limits; new 20 mph default school limit under AB 382"),
             ssi=("considered", DECK, "Draft 18-month plan: 35 new corridors")),
  sf_example=dict(name="Tenderloin, 20 mph on 17 corridors (centre point Eddy and Leavenworth)", year=2021,
                  lat=37.783724, lon=-122.414242, geometry_hint="area: Tenderloin, 17 corridors; point is Eddy St and Leavenworth St",
                  source_url=TL20),
  by_user=U(
    ("Slower cars where drivers obey.", "Signs alone move speeds little.", DFT, "DfT 2018: 'insufficient evidence' of a casualty change after signed residential 20 mph limits in the short term."),
    ("Calmer mixed traffic.", "Same caveat.", None, "[inference — mine]"),
    ("None measured.", "Slightly slower buses on fast corridors.", None, "[inference — mine]"),
    ("Cheap and quick.", "More tickets once cameras enforce them.", None, "[inference — mine]"),
    ("AB 382 lets SF set 15 and 20 mph school zones.", "Only near the school.", "https://www.sfmta.com/sfmta-school-safety-programs", "SFMTA's school speed program sets a new default school limit of 20 mph."))),
# ---------------------------------------------------------------- network tools
dict(
  id="protected-bike-lanes", name="Protected bike lanes", group="network",
  one_line="Bike lanes separated from cars by posts, parked cars or concrete, forming a connected network.",
  cost=dict(text="$0.9M to $1.6M a mile as a quick-build; $16M to $24M a mile in concrete", short="$0.9M-$1.6M a mile",
            value_low=890000, value_high=1610000, unit="per mile (quick-build)",
            source_url=QB, source_title="SFMTA quick-build budgets at Board approval; Central Embarcadero memo for concrete [primary — read 2026-09-29, repo note]"),
  effect=dict(text="53% fewer bike-car crashes where posts separate a painted lane, from a cross-sectional study with propensity weights (Dixon 2023, FHWA-HRT-23-025)", short="-53% bike crashes", pct=-53,
              outcome="crashes", design="cross-sectional", where="FHWA",
              source_url=WB + "bicycle-lanes", source_title="FHWA Proven Safety Countermeasures, Bicycle Lanes, Wayback snapshot [primary — read 2026-10-22], citing Dixon 2023, FHWA-HRT-23-025; removed from FHWA's list in 2026" + F),
  opposition=dict(grade="Medium",
    reason="Merchant backlash forced Valencia's redesign, from the 2023 centre-running pilot to a side-running lane, and the lane survived.",
    examples=[{"text": "The 2023 centre-running pilot was 'a compromise with merchants' (SFMTA staff report, Nov 2024, p. 5)", "url": QB},
              {"text": "Side-running lane approved 2024-11-19, built from 2025-02-10", "url": VALENCIA},
              {"text": "Controller: Valencia business troubles 'pre-date the construction' with 'no statistical basis' linking them", "url": CONTROLLER_VAL},
              {"text": "Market Street's protected lane was cut in 2020 in 'the pandemic budget crunch' (Streetsblog, 2020-10-28)", "url": STREETSBLOG_MKT}]),
  programs=P(ssc=("in", SSC, "Physical infrastructure toolkit: separated bike lanes"),
             mta=("in", DECK, "51 miles of protected bike lanes built (Jan 2026 deck)"),
             ssi=("considered", SSI, "Action 22, HIN plan 'providing separation', in progress; deck plans 3 miles in 18 months")),
  sf_example=dict(name="Valencia Street side-running protected bikeway, 15th to 23rd Street", year=2025,
                  lat=37.760101, lon=-122.421425, geometry_hint="lat/lon is Valencia St at 19th St; street segment: Valencia St, 15th St (37.76654,-122.422044) to 23rd St (37.753703,-122.420812)",
                  source_url=VALENCIA),
  by_user=U(
    ("Bikes off the sidewalk; shorter crossings where islands are added.", "Floating bus and parking islands add a lane to cross.", None, "[inference — mine]"),
    ("Physical separation; the biggest single safety gain for people on bikes.", "Driveways and turns remain conflict points.", TESCHKE, "Teschke et al. 2012 (case-crossover, Toronto and Vancouver): cycle tracks adjusted OR 0.11 against major streets with parked cars [primary — read 2026-10-09, repo note]."),
    ("None measured.", "Can compete with bus lanes for space.", None, "[inference — mine]"),
    ("Fewer bike-car conflicts.", "Parking and loading lost: Valencia went from 225 to 146 spaces.", QB, "SFMTA staff report, Nov 2024, pp. 10 to 13."),
    ("The tool SFMTA's school plan is built around.", "A child riding still carries more risk per mile than in a car.", "https://www.canada.ca/en/public-health/services/reports-publications/health-promotion-chronic-disease-prevention-canada-research-policy-practice/vol-34-no-4-2014/active-safe-transportation-elementary-school-students.html", "Montreal, ages 5 to 12: cycling 22 times a car's injury risk per km [primary — read 2026-10-13, repo note]."))),
dict(
  id="low-traffic-neighborhoods", name="Low traffic neighborhoods and diverters", short_name="Low traffic neighborhoods", group="network",
  one_line="Planters or posts at a few corners stop through traffic on residential streets, while every home stays reachable by car.",
  cost=dict(text="$19,000 to $40,000 a diverter: the concrete islands on the Sanchez Slow Street (SFCTA Prop L allocation, Sept 2025)", short="$19K-$40K a diverter",
            value_low=19000, value_high=40000, unit="per diverter",
            source_url="https://www.sfcta.org/sites/default/files/2025-08/SFCTA_CAC_Item5_PropLAllocationsandNextGenSanchezAmendmentMEMO_2025-09-03.pdf", source_title="SFCTA CAC Prop L allocations memo, 2025-09-03 [primary — read 2026-10-23, earlier session; not reopened, the site blocks scripted reads]"),
  effect=dict(text="37% fewer people killed or seriously hurt inside London's LTNs, with no rise on boundary roads", short="-37% killed or seriously hurt", pct=-37,
              outcome="deaths+serious", design="controlled", where="London",
              source_url=FURLONG, source_title="Furlong et al., Injury Prevention 2025, controlled before-after [primary — read 2026-10-22]"),
  opposition=dict(grade="Medium",
    reason="Staff cut the pandemic Slow Streets from 31 to 15; the Board kept 16, the list is now 19, and the Page Street diverter was made permanent 6-0.",
    examples=[{"text": "Staff recommended 15 of 31 Slow Streets and removal of the rest (Dec 2022)", "url": SLOW_SR},
              {"text": "Board added Lake Street and kept 16 (minutes, 2022-12-06)", "url": SLOW_MIN},
              {"text": "19 Slow Streets corridors today", "url": SLOW},
              {"text": "Page Street diverter made permanent, 6-0", "url": PAGE}]),
  programs=P(ssc=("in", SSC, "Physical infrastructure toolkit: traffic diverters"),
             mta=("in", SLOW, "Slow Streets program lists traffic diverters among its treatments; 19 corridors"),
             ssi=("considered", DECK, "Draft plan: upgrade 3 of 19 Slow Streets to meet speed and volume standards")),
  sf_example=dict(name="Page Street at Webster Street diverter, beside John Muir Elementary", year=2020,
                  lat=37.773248, lon=-122.42899, geometry_hint="point", source_url=PAGE),
  by_user=U(
    ("Quiet streets; injuries fall inside the area.", "None measured.", FURLONG, "All injuries fell 35% and killed or seriously injured 37% inside LTNs; injuries returned where LTNs were removed."),
    ("Low-traffic routes without building a bike lane.", "Only as good as the volume it holds down: 3 of 16 Slow Streets met SFMTA's targets in 2023.", "https://www.sfmta.com/sites/default/files/reports-and-documents/2023/12/2023_slow_streets_evaluation_report_accessible.pdf", "SFMTA 2023 Slow Streets evaluation, p. 18 [primary — read 2026-10-05, repo note]."),
    ("None measured.", "Muni routes can't run on them.", SLOW, "SFMTA: 'MUNI routes and emergency response corridors do not work as Slow Streets'."),
    ("Every address stays reachable.", "Longer routes through the area; Furlong found no rise in boundary-road injuries.", FURLONG, None),
    ("SFMTA used one to keep traffic low by John Muir Elementary.", "None measured.", PAGE, "Page Street item, Jan 2023: restrictions 'intended to maintain low vehicle volumes on Page Street near John Muir Elementary School'."))),
dict(
  id="calmed-20mph-zones", name="Calmed 20 mph zones", group="network",
  one_line="A whole neighborhood at 20 mph, with a hump, table or chicane every 150 to 250 feet so the limit holds.",
  cost=dict(text="$0.33M to $1.3M a mile: SF's device costs at SFMTA's 150 to 250 ft spacing [inference — mine]", short="$0.33M-$1.3M a mile",
            value_low=330000, value_high=1300000, unit="per mile",
            source_url=R2606, source_title="SFCTA R26-06 and 2021 enclosure, device costs times SFMTA spacing of 150 to 250 ft [inference — mine, from primary costs read 2026-10-22]"),
  effect=dict(text="42% fewer casualties in London's zones, more for serious injuries and young children", short="-42% injuries", pct=-42,
              outcome="all injuries", design="controlled", where="London",
              source_url=GRUNDY, source_title="Grundy et al., BMJ 2009, controlled interrupted time series [primary — read 2026-10-22]"),
  opposition=dict(grade="Medium",
    reason="No SF zone has been tried. Humps are popular when residents ask, but a zone puts them on every block at once [inference — mine].",
    examples=[{"text": "Street Safety Act asks for a proactive hump program 'across neighborhoods' by Dec 2026", "url": SSA},
              {"text": "Resident requests far exceeded the program, which paused in 2025", "url": CALM141}]),
  programs=P(),
  sf_example=None,
  nearest_example=dict(city="London", name="20 mph zones in London boroughs, 1986 to 2006", url=GRUNDY),
  by_user=U(
    ("Slower cars on every street in the zone.", "None measured.", GRUNDY, "Casualties fell 41.9% after adjusting for the trend, with no rise in adjacent areas."),
    ("Mixed traffic slow enough to share.", "Humps without bike gaps are uncomfortable.", None, "[inference — mine]"),
    ("Zones skip the main bus streets.", "Buses slow if routes run through.", None, "[inference — mine]"),
    ("Neighbors' streets calmed too, so less cut-through.", "Slower last mile.", None, "[inference — mine]"),
    ("The reduction 'was greatest in younger children'.", "None measured.", GRUNDY, None))),
dict(
  id="20mph-default", name="20 mph as the citywide default", short_name="20 mph citywide default", group="network",
  one_line="Every street is 20 mph unless signed otherwise, as in Hoboken since 2022.",
  cost=dict(text="Signs only; SF paid about $450 a sign for school zones in 2012. No citywide estimate found", short="Signs only",
            value_low=450, value_high=None, unit="per sign",
            source_url=SCHOOL_ZONE_2012, source_title="SFMTA press release 2012-05-14, $361,700 for about 803 signs [primary — read 2026-10-13, repo note]"),
  effect=dict(text="10% fewer casualties on Edinburgh's changed streets than on unchanged ones (95% CI −19% to 0%); Wales saw 26% in year one, with no control", short="-10% injuries", pct=-10,
              outcome="all injuries", design="controlled", where="Edinburgh",
              source_url=KOKKA, source_title="Kokka et al., J Epidemiol Community Health 2024 [primary — read 2026-10-13, repo note]; Wales: Transport for Wales, National Monitoring Report, July 2025, " + TFW_2025 + F),
  opposition=dict(grade="Untested",
    reason="Untested in SF; the block is legal: state law only lets SF lower limits on certain streets.",
    examples=[{"text": "Mayor, 2021: 'We need to urgently work to change speed limits in the city'", "url": VZ},
              {"text": "86 corridors cut so far (Jan 2026)", "url": DECK}]),
  programs=P(),
  sf_example=None,
  nearest_example=dict(city="Hoboken, NJ", name="20 mph citywide, adopted unanimously in July 2022", url=HOBOKEN),
  by_user=U(
    ("SFMTA: a pedestrian struck at 20 mph has double the chance of survival of one struck at 25.", "Signs alone change speeds by 1 to 2 mph: Edinburgh's mean fell 1.3 mph.", TL20, "Edinburgh speed change from Kokka et al. 2024 [primary — read 2026-10-13, repo note]."),
    ("Calmer mixed traffic everywhere.", "Same caveat.", None, "[inference — mine]"),
    ("None measured.", "Slightly slower buses if arterials are included.", None, "[inference — mine]"),
    ("One rule everywhere.", "Slower trips; tickets where cameras enforce.", None, "[inference — mine]"),
    ("Covers the whole walk to school, not 500 feet of it.", "None measured.", None, "[inference — mine]"))),
dict(
  id="school-streets", name="School Streets", group="network",
  one_line="The block in front of a school closes to cars at drop-off and pick-up, staffed by people with barriers.",
  cost=dict(text="About $30,000 a school a year for staff, plus set-up: our estimate from SFMTA's crossing guard cost of about $56 an hour over 180 school days", short="$30K a school a year",
            value_low=13500, value_high=60000, unit="per school per year",
            source_url=GUARDS, source_title="Our estimate from SFMTA crossing guard costs (about $56 an hour, 180 school days assumed) [inference — mine]; Hampshire Cabinet 2024-02-06 para 18 [primary — read 2026-10-13, repo note]"),
  effect=dict(text="No injury study found; studies measure travel mode only", short="No injury study", pct=None,
              outcome=None, design=None, where="",
              source_url=HANTS, source_title="No casualty study found [repo note 2026-10-13]"),
  opposition=dict(grade="Untested",
    reason="Untested: SF has only run demonstration days.",
    examples=[{"text": "Up to six School Street events planned for 2026-27 in SFMTA's draft", "url": SSC}]),
  programs=P(ssc=("considered", SSC, "Draft plan's physical infrastructure toolkit: up to six School Street activations in 2026-27")),
  sf_example=None,
  nearest_example=dict(city="Hampshire, England", name="School Streets programme (Harrison School and others)", url=HANTS),
  by_user=U(
    ("No cars on the school's own block at the bell.", "Only one block, only at bell times.", None, "[inference — mine]"),
    ("Car-free arrival on the last block.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "None measured.", None, None),
    ("Less crush at the gate.", "Drop-off moves a block away.", None, "[inference — mine]"),
    ("Children arrive in a calm block.", "Needs staff every day: Harrison School needed 'eight volunteers every day'.", HANTS, "Hampshire Cabinet paper, para 16 [primary — read 2026-10-13, repo note]."))),
dict(
  id="circulation-plan", name="Circulation plan", group="network",
  one_line="The center is split into sectors that cars can enter and leave but not drive between, so through traffic goes around.",
  cost=dict(text="No cost found", short="Not found", value_low=None, value_high=None, unit=None,
            source_url=GHENT, source_title="Ghent 2019 evaluation reports no total cost [unretrieved — verify]"),
  effect=dict(text="No clear injury effect: Ghent's own evaluation says the link cannot be firmly shown (our translation from Dutch), and its pedestrian casualties fell no faster than Belgium's [inference — mine]", short="No clear effect", pct=None,
              outcome="pedestrian casualties, all severities", design="before-after", where="Ghent",
              source_url=GHENT, source_title="Stad Gent, Evaluatierapport Circulatieplan 2019 [primary — read 2026-10-22, repo note]"),
  opposition=dict(grade="High",
    reason="SF has never proposed one; its nearest moves, Slow Street diversions and car-free Market Street, were cut back [inference — mine].",
    examples=[{"text": "Ghent's mobility alderman got death threats days before launch (VRT, 2017)", "url": VRT},
              {"text": "Slow Streets cut from 31 to 16 corridors", "url": SLOW_SR}]),
  programs=P(),
  sf_example=None,
  nearest_example=dict(city="Ghent, Belgium", name="Circulation plan, six sectors around a car-free core, from 3 April 2017", url=GHENT),
  by_user=U(
    ("Much less traffic in the center.", "None measured.", GHENT, "Peak traffic into and out of the center fell 17% [primary — read 2026-10-22, repo note]."),
    ("Through routes for bikes, not cars.", "None measured.", None, "[inference — mine]"),
    ("Buses can keep through routes.", "None measured.", None, "[inference — mine]"),
    ("Every address reachable.", "Longer trips between sectors; victims rose on Ghent's R40 ring.", GHENT, None),
    ("None measured.", "None measured.", None, None))),
dict(
  id="congestion-charge", name="Congestion charge", group="network",
  one_line="A daily fee to drive into the downtown core at busy hours, with the money going to transit.",
  cost=dict(text="Raises money rather than costing it; SF needs state authority", short="Raises money",
            value_low=None, value_high=None, unit=None,
            source_url=VZ, source_title="Vision Zero SF Action Strategy 2021-2024, p. 19, 'SF needs state authority' [primary — read 2026-10-23]"),
  effect=dict(text="38% to 40% fewer crashes in London's zone and hours, against comparison cities; serious and fatal crashes fell too (an unrefereed working paper)", short="-38% crashes", pct=-38,
              outcome="crashes", design="controlled", where="London",
              source_url=GREEN, source_title="Green, Heywood and Navarro, Traffic Accidents and the London Congestion Charge, unrefereed working paper [primary — read 2026-10-23]"),
  opposition=dict(grade="High",
    reason="SFCTA's downtown pricing study is paused and the business lobby opposes a local cordon; the state has not granted authority.",
    examples=[{"text": "SFCTA downtown congestion pricing study, paused (SFCTA page, 2022-11-30)", "url": SFCTA_PRICING},
              {"text": "Stockholm's support rose from 34% to about two thirds once people lived with the charge (Eliasson 2014) [primary — read 2026-10-22, repo note]", "url": ELIASSON}]),
  programs=P(mta=("considered", VZ, "Named on Vision Zero p. 19 as needing state authority; no commitment")),
  sf_example=None,
  nearest_example=dict(city="London", name="Congestion Charge zone, from February 2003", url=GREEN),
  by_user=U(
    ("Fewer cars downtown.", "None measured.", GREEN, "Fewer crashes in the zone, in adjacent areas and for uncharged vehicles."),
    ("Fewer cars downtown.", "None measured.", None, "[inference — mine]"),
    ("Faster buses and money for service.", "None measured.", None, "[inference — mine]"),
    ("Faster trips for those who pay.", "A daily fee.", None, "[inference — mine]"),
    ("None measured.", "Most school trips are not downtown.", None, "[inference — mine]"))),
dict(
  id="car-free-streets", name="Car-free streets", group="network",
  one_line="A street or district closed to private cars full-time, open to people walking, biking, transit and deliveries.",
  cost=dict(text="No SF cost found for a closure itself", short="Not found", value_low=None, value_high=None, unit=None,
            source_url=JFK_SFMTA, source_title="Golden Gate Park Access and Safety Program page gives no cost [primary — read 2026-10-23]"),
  effect=dict(text="Citywide serious injuries in Pontevedra (pop. 84,000) fell from 129 in 1999 to 4 to 20 a year in 2005 to 2020, with no comparison city; the figures are for the whole city, not only the car-free center", short="-84% serious injuries", pct=-84,
              outcome="deaths+serious", design="before-after", where="Pontevedra (city)",
              source_url=DGT, source_title="DGT, Pontevedra urban experience sheet [primary — read 2026-10-22, repo note]" + F),
  opposition=dict(grade="High",
    reason="Car-free parks win citywide votes and lose locally: District 4 voted 63.7% against Prop K, then recalled its supervisor.",
    examples=[{"text": "Prop K (Upper Great Highway) passed with 54.7% in November 2024", "url": ELECTIONS},
              {"text": "District 4 voted 63.7% against Prop K (SF Examiner, 2025-12-19)", "url": EXAMINER_D4},
              {"text": "District 4 recalled Supervisor Engardio with 62.7% [secondary — verify]", "url": ML_RECALL},
              {"text": "2022: Prop J kept JFK Drive car-free with 62%; Prop I to reopen it lost with 64% (Streetsblog, 2022-11-14) [unretrieved — verify]", "url": PROPJ}]),
  programs=P(mta=("in", JFK_SFMTA, "Golden Gate Park program made a 3-mile stretch of park streets car-free"),
             ssi=None),
  sf_example=dict(name="JFK Promenade, John F. Kennedy Drive from Kezar Drive to Transverse Drive", year=2022,
                  lat=37.772524, lon=-122.468086, geometry_hint="lat/lon is JFK Dr at 10th Ave; street segment: JFK Dr, Kezar Dr (37.77093,-122.45529) to Transverse Dr (37.770496,-122.479895)",
                  source_url=JFK_SFMTA),
  by_user=U(
    ("No cars at all.", "None measured.", DGT, "Pontevedra also cut traffic in the historic center by 92%."),
    ("A car-free route.", "Short unless it links to a network.", None, "[inference — mine]"),
    ("Transit can be kept, as on Market Street.", "Detours where routes are removed.", None, "[inference — mine]"),
    ("None measured.", "Detours and lost parking; disabled access needs shuttles and parking.", JFK_SFMTA, "The JFK program added a park shuttle and ADA parking."),
    ("Car-free routes for family rides.", "Mostly park roads, not routes to school.", None, "[inference — mine]"))),
dict(
  id="transit-only-lanes", name="Transit-only lanes", group="network",
  one_line="Red lanes reserved for buses, often with turn limits and boarding islands, so Muni isn't stuck in car traffic.",
  cost=dict(text="Less than $0.5M a mile as a quick-build (19 Polk, a ceiling, not a floor); about $5M a mile on Mission", short="Under $0.5M-$5M a mile",
            value_low=500000, value_high=5000000, unit="per mile",
            source_url=MF, source_title="SFMTA Board, Muni Forward Update, 2024-11-06, p. 7 [primary — read 2026-10-23]"),
  effect=dict(text="24% fewer injury collisions after red lanes on 3rd, Geary and O'Farrell, when citywide injuries didn't change", short="-24% injury collisions", pct=-24,
              outcome="all injuries", design="before-after", where="3 SF streets",
              source_url=REDLANES, source_title="SFMTA, Red Transit-Only Lanes Work, 2017-04-07 [primary — read 2026-10-23]"),
  opposition=dict(grade="Medium",
    reason="Merchant and supervisor backlash forced a redesign of Mission Street's 2016 red lanes, and the lanes survived.",
    examples=[{"text": "Supervisor Campos called for 'a radical shift' (Apr 2016) [secondary — verify]", "url": SB_CAMPOS},
              {"text": "Board removed two forced turns, kept the red lanes (Aug 2016) [secondary — verify]", "url": STREETSBLOG_MISSION},
              {"text": "SFMTA Board approves the Mission Street changes", "url": MISSION_OK}]),
  programs=P(mta=("in", DECK, "Muni Forward toolkit on 110 miles"),
             ssi=("considered", DECK, "Draft plan: 15 more miles of Muni Forward toolkit")),
  sf_example=dict(name="Mission Street red transit lanes, 14th to Randall Street (14 Mission Rapid)", year=2016,
                  lat=37.755437, lon=-122.418748, geometry_hint="lat/lon is Mission St at 22nd St; street segment: Mission St, 14th St (37.768274,-122.419982) to Randall St (37.739884,-122.42358)",
                  source_url=MISSION_OK),
  by_user=U(
    ("Fewer injury collisions on the street.", "None measured.", SAMPLE14, "SFMTA says Mission's safety features cut pedestrian collisions 59% (daylighting, a lane reduction, head-start signals, turn limits)."),
    ("None measured.", "Bikes share or cross the lane.", None, "[inference — mine]"),
    ("Faster, more reliable buses.", "None measured.", SAMPLE14, "Up to 31% faster in SoMa; 25% less variable travel times in the Mission."),
    ("Fewer lane changes and less speeding.", "One less lane; forced turns.", REDLANES, "Zendrive found a 36% reduction in speeding on Mission after the project (vendor study, reported by SFMTA)."),
    ("Faster Muni for students who ride.", "None measured.", MORENCY, "A bus trip carries far less injury risk than a car trip per passenger km (Montreal) [primary — read 2026-10-13, repo note]."))),
dict(
  id="parking-removal", name="Parking removal at scale", short_name="Parking removal", group="network",
  one_line="Taking out street parking across a district and giving the curb to people, bikes, loading and transit.",
  cost=dict(text="Little capital; costs lost meter and permit revenue. No SF figure found", short="Lost meter revenue",
            value_low=None, value_high=None, unit=None, source_url=OSLO, source_title="No SF estimate found"),
  effect=dict(text="No injury study found. Oslo removed about 760 central spaces; its page reports no injury figures", short="No injury study", pct=None,
              outcome=None, design=None, where="Oslo",
              source_url=OSLO, source_title="Oslo kommune, Bilfritt byliv 2016-2023 [primary — read 2026-10-22, repo note]" + F),
  opposition=dict(grade="High",
    reason="Parking is the objection that wins in SF, even when the data contradict it, as on Valencia.",
    examples=[{"text": "Controller found 'no statistical basis' linking Valencia business losses to the bike lane", "url": CONTROLLER_VAL},
              {"text": "Oslo's parking removal drew 'local opposition' (TfL case study) [secondary — verify]", "url": TFL_OSLO}]),
  programs=P(),
  sf_example=None,
  nearest_example=dict(city="Oslo", name="Car-free city life, about 760 spaces removed inside Ring 1, 2016 to 2023", url=OSLO),
  by_user=U(
    ("Wider space and clear corners.", "None measured.", None, "[inference — mine]"),
    ("Room for bike lanes.", "None measured.", None, "[inference — mine]"),
    ("Room for bus lanes and stops.", "None measured.", None, "[inference — mine]"),
    ("Less cruising if the rest is priced.", "Fewer places to park.", None, "[inference — mine]"),
    ("None measured.", "Harder drop-off for families who still drive.", None, "[inference — mine]"))),
]

# ---------------------------------------------------------------- 2026-10-23 additions and overlay
# tools_more.py holds the 26 rows added from the FHWA, Vision Zero and NYC lists; tools_over.py holds each row's
# square-mile cost, area effect, coverage and the plan text that limits it. tools_more imports from this
# module, so the import sits after TOOLS.
from tools_more import NEW  # noqa: E402
from tools_over import OVER, ORDER, LIMITS, BANDS, LISTS, SKIPPED, SHARES_NOTE  # noqa: E402,F401

TOOLS = [t for t in TOOLS if t["id"] != "quick-build-road-diet"] + NEW
_by = {t["id"]: t for t in TOOLS}
assert len(_by) == len(TOOLS), "duplicate tool id"
_ordered = [i for ids in ORDER.values() for i in ids]
assert sorted(_ordered) == sorted(_by), f"ORDER and TOOLS differ: {sorted(set(_by) ^ set(_ordered))}"
assert sorted(OVER) == sorted(_by), f"OVER and TOOLS differ: {sorted(set(_by) ^ set(OVER))}"

# The LTN row no longer carries Page Street: that diverter sits on a Slow Street, which is its own row now.
_ltn = _by["low-traffic-neighborhoods"]
_ltn["sf_example"] = None
_ltn["nearest_example"] = dict(city="London", name="The low traffic neighbourhoods Furlong et al. 2025 studied", url=FURLONG)
_ltn["opposition"]["reason"] = ("None has been proposed in SF. The nearest fights are over single Slow Streets, which staff "
                                "cut from 31 to 15 in 2022 before the Board kept 16.")
_ltn["opposition"]["examples"] = [e for e in _ltn["opposition"]["examples"] if "Page Street" not in e["text"]]
_ltn["by_user"]["kids_school_trip"] = {"pros": "Quiet residential streets on the walk to school.", "cons": "None measured.",
                                       "evidence_url": None, "evidence_note": "[inference — mine]"}

_ltn["programs"]["street_safety_initiative"] = None  # the Jan 2026 draft-plan line is about Slow Streets, now its own row

# The square mile is the median grid cell (tools_over.GRID), replacing the citywide average above.
from tools_over import SQUARE_MILE, GRID as SQ  # noqa: E402,F811

# Fable review, 2026-10-23: headline figures that were the wrong study or mislabelled.
_by["lower-speed-limits"]["effect"].update(
    text="10% fewer casualties on Edinburgh's streets where signed limits fell from 30 to 20 mph, against unchanged streets (95% CI −19% to 0%). Vision Zero SF's 20% for Seattle has no reference",
    short="-10% injuries", pct=-10, outcome="all injuries", design="controlled", where="Edinburgh",
    source_url=KOKKA, source_title="Kokka et al. 2024, controlled before-after [primary — read 2026-10-22]")
_by["speed-humps"]["effect"].update(outcome="child pedestrian injuries (odds)", design="case-control",
    text="53% lower odds of a child pedestrian being hit near home where humps were present (Tester et al. 2004, a case-control study of children treated after a crash)")
_by["congestion-charge"]["effect"].update(
    text="38% to 40% fewer crashes in London's zone during charging hours, against comparison cities; serious and fatal crashes fell too",
    source_url="https://doi.org/10.1016/j.jpubeco.2015.10.005",
    source_title="Green, Heywood and Navarro, Traffic accidents and the London congestion charge, Journal of Public Economics 133 (2016) 11-22 [primary — read 2026-10-23]")
_by["speed-radar-signs"]["sf_example"] = dict(
    name="Upper Market Street near Twin Peaks, one of five completed speed radar signs on Market in SFMTA's calming data", year=None,
    lat=37.754150, lon=-122.442053, geometry_hint="point (DataSF 3psu-pn9h segment 8776104, Market St)", source_url="https://data.sfgov.org/d/abhw-ffzx")
_by["bike-slow-streets"]["nearest_example"] = dict(
    city="Berlin", name="Tucholskystraße Fahrradstraße, with bollards closing it to through traffic at Auguststraße (December 2023)",
    url="https://www.berlin.de/ba-mitte/politik-und-verwaltung/aemter/strassen-und-gruenflaechenamt/planung-entwurf-neubau/tucholskystrasse-fahrradstrasse-1312267.php",
    rules_title="German road code, sign 244.1: other vehicles only where a sign allows, 30 km/h, riders may go side by side, and cyclists 'may neither be endangered nor obstructed'",
    rules_url="https://www.gesetze-im-internet.de/stvo_2013/anlage_2.html",
    rules2_title="Belgian road code, art. 22novies (the fietsstraat, called a fietszone since 2023): motor vehicles may enter but 'mogen de fietsers evenwel niet inhalen' (may not pass cyclists), at 30 km/h or less",
    rules2_url="https://www.wegcode.be/nl/regelgeving/1975120109~hra8v386pu",
    rules3_title="The Dutch 'Fietsstraat, auto te gast' sign, which has no legal standing in the Netherlands (Dutch Wikipedia, secondary source)",
    rules3_url="https://nl.wikipedia.org/wiki/Fietsstraat")

# The school plan's Slow Streets are the partial version, so they count as hollow for the full bike street.
_by["bike-slow-streets"]["programs"]["safe_school_connections"]["status"] = "considered"
_by["bike-slow-streets"]["programs"]["safe_school_connections"]["note"] += " (Slow Streets, the partial version: no legal bike priority)"

for _g, _ids in ORDER.items():
    for _i in _ids:
        _by[_i]["group"] = _g
TOOLS = [_by[i] for i in _ordered]

for t in TOOLS:
    o = OVER[t["id"]]
    t["cost"]["per_sq_mi"] = o["sq"]
    t["effect"]["area"] = o["area"]
    t["coverage"] = o["cov"]
    if o.get("net"):
        t["cost"]["per_sq_mi"]["net"] = o["net"]
    if o.get("legal"):
        t["legal"] = {"text": o["legal"][0], "sources": [{"title": a, "url": b} for a, b in o["legal"][1]], "cell": o["legal"][2] if len(o["legal"]) > 2 else "capped by state law"}
    _mta = t["programs"].pop("other_sfmta", None)
    t["sfmta_use"] = {"text": _mta["note"], "url": _mta["source_url"]} if _mta else None
    t.pop("limits", None)
    if t["id"] in LIMITS:
        _key, _url, _where, _quote = LIMITS[t["id"]]
        t["programs"][_key] = {"status": "limits", "source_url": _url, "note": _where, "quote": _quote}
    for _p in t["programs"].values():
        if _p and _p["status"] == "pilot":
            _p["status"] = "considered"
