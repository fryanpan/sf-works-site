"""The rows added on 2026-10-23 (lane removal, 25 more tools, the Muni group), one dict per tool, from that
day's research lanes. tools_src.py imports NEW from here and OVER from tools_over.py."""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
from tools_src import *  # noqa: F401,F403  (constants and the P/U helpers)

# Constants from the 2026-10-23 research lanes
# Research B, read 2026-10-23
CC_REPORT = "https://www.sfmta.com/media/45219/download"   # SFMTA Board staff report, Community Corners Program, cal. item 13, 2026-06-16
CC_RES = "https://www.sfmta.com/media/45291/download"      # SFMTAB Resolution 260616-054 (adopted 2026-06-16) + staff report copy
NYC_DAYLIGHT = "https://www.nyc.gov/assets/ddc/downloads/town-and-gown/ROTR8/1_Viola_Daylighting%20Study%20Summary%20Presentation%20to%20ROTR%20Nov%202025.pdf"
NYC_HD_COST = "https://citymeetings.nyc/meetings/new-york-city-council/2025-04-21-1000-am-committee-on-transportation-and-infrastructure/chapter/council-member-julie-won-questions-dot-on-daylighting-implementation-costs"
SB_HARD = "https://sf.streetsblog.org/2026/02/04/commentary-hardened-daylighting-works-paint-alone-not-so-much"
LT_PAGE = "https://www.sfmta.com/getting-around/walk/pedestrian-improvements-toolkit/left-turn-safety"
LT_EVAL = "https://www.sfmta.com/media/43301/download"     # SFMTA one-page evaluation, Left Turn Traffic Calming, 14 treated / 6 control, Oct 2024-Mar 2025
PROPL_LT = "https://www.sfcta.org/sites/default/files/2024-02/SFCTA_CAC_PropLAllocationsPRESENTATION_2024-02-28.pdf"
NYC_TURN = "https://www.nyc.gov/html/dot/html/pedestrians/turn-calming.shtml"
NTOR_EVAL = "https://www.sfmta.com/media/31093/download"   # SFMTA Tenderloin No Turn on Red Evaluation summary
NTOR_DT = "https://www.sfmta.com/index%2Ephp/projects/no-turn-red-downtown-expansion-project"
SFSTD_NTOR = "https://sfstandard.com/2024/04/02/right-on-red-banned-san-francisco/"
CMF_RTOR = "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=4579"
CMF_RTOR_PREUSSER = "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=371"
PEDSAFE_RTOR = "https://mail.walkinginfo.org/pedsafe/pedsafe_curb1_CM_NUM_41/"
SCRAMBLE = "https://www.sfmta.com/node/25507"              # SFMTA Pedestrian Improvements Toolkit: Pedestrian Scramble
CMF_SCRAMBLE = "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=4117"
CMF_SCRAMBLE_MV = "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=4118"
PEDSAFE_SIG = "https://pedbikesafe.org/PEDSAFE/countermeasures_detail.cfm?CM_NUM=47"
TOWNSEND = "https://www.sfmta.com/projects/townsend-corridor-improvement-project"
BIKESIG_EVAL = "https://sfmta.com/media/17331/download"    # SFMTA, Bike Signals and Mixing Zones evaluation, 2018 data
FELL_SIG = "https://sfmta.com/media/1265/download"         # SFMTA FAQ, Fell-Masonic, first bicycle signal
SB_POLK = "https://sf.streetsblog.org/2015/03/20/four-protected-bike-signals-coming-to-polk-street-by-may"
VZRT = "https://sfmta.com/en/node/29748"  # Vision Zero Signal Retiming project page
PEDSIG = "https://www.sfmta.com/pedestrian-signal-improvements"
GREENWAVE = "https://archives.sfmta.com/cms/apress/GreenWaveImprovesCyclingonValenciaStreetSFMTAmodifiessignaltimingreducesspeedtobetterac.htm"
FRANKLIN = "https://www.sfmta.com/project-updates/august-2024-franklin-street-quick-build-project-update-signal-retiming-results"
MOCAC = "https://sfplanning.org/sites/default/files/documents/cac/MOCAC-Presentation02-SFMTA-111422.pdf"
C35 = "https://www.sfmta.com/projects/contract-35-traffic-signal-modifications-0"
C35_PWC = "https://sfpublicworks.org/sites/default/files/Commissions/April%2030%2C%202026/Resolutions/PWC%20Resolution%202026-0036%20No.%2035%20Traffic%20Signal%20Upgrades%20award%202026-4-30.pdf"
C65 = "https://www.sfmta.com/node/29743"
C65_PWC = "https://sfpublicworks.org/sites/default/files/Item%204e_PWC%20No.%2065%20New%20Traffic%20Signals%20mod%202023-10-6%20v104.pdf"
C66 = "https://www.sfcta.org/sites/default/files/2025-09/SFCTA_CAC_Item5_PropLAllocationsandNextGenSanchezAmendmentPRESENTATION_2025-09-03.pdf"
WA1 = "https://www.sfmta.com/projects/western-addition-traffic-signal-upgrades-phase-1"
CONT = "https://www.sfmta.com/continental-crosswalks"
CONT_LAYER = "https://services.sfmta.com/arcgis/rest/services/DataSF/master/MapServer/53"
RRFB_WF = "https://www.sfmta.com/projects/walkfirst-rectangular-rapid-flashing-beacons-project"
G38 = "https://www.sfcta.org/sites/default/files/2023-03/D1%2038th%20and%20Geary.pdf"
PBIC = "https://web.archive.org/web/2024/https://www.pedbikeinfo.org/cms/downloads/Countermeasure%20Costs_Report_Nov2013.pdf"
RADAR04 = "https://sfbos.archive.sf.gov/ftp/uploadedfiles/bdsupvrs/resolutions04/r0548-04.pdf"
CMF418 = "https://cmfclearinghouse.fhwa.dot.gov/study_detail.php?stid=418"
CMF1409 = "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=1409"
TL_LIGHT = "https://tlcbd.org/blog/lighting-project-tenderloin"
TL_LIGHT17 = "https://tlcbd.org/blog/2017/09/11/2017-9-11-plan-to-improve-tenderloin-streetlights-on-hold-amid-pge-watchdog-dispute-sf-chronicle/"
REDLIGHT = "https://www.sfmta.com/RedLight"
RLC_2018 = "https://sfmta.com/media/14188/download"          # SFMTA Board Res. 180821-112
FHWA_RLC = "https://www.fhwa.dot.gov/publications/research/safety/05048/12.cfm"
IIHS_RLC = "https://www.iihs.org/topics/bibliography/ref/2121"
GUARD_PAGE = "https://www.sfmta.com/getting-around/walk/adult-school-crossing-guard-program"
KALW_GUARDS = "https://www.kalw.org/bay-area-news/2026-01-06/crossing-guard-program-misses-staffing-goal-despite-gains"
ROTHMAN = "https://pmc.ncbi.nlm.nih.gov/articles/PMC4520271"
SCHOOLS_DATA = "https://data.sfgov.org/d/7e7j-59qk"
FMCSA_SG = "https://trid.trb.org/View/1497971"
VZN_LARGE = "https://visionzeronetwork.org/case-study-how-can-cities-increase-the-safety-of-large-vehicles-in-urban-areas/"
SB_TRUCKS = "https://sf.streetsblog.org/2016/10/26/how-american-cities-can-protect-cyclists-from-deadly-trucks"
VOLPE_SF = "https://rosap.ntl.bts.gov/view/dot/12367"
SFPD_TVR = "https://www.sanfranciscopolice.org/stay-safe/crime-data/traffic-violation-reports"
RIPA = "https://data.sfgov.org/d/ubqf-aqzw"
CITE_NOTE = None
ENF_NOTE = "https://doi.org/10.1257/pol.6.2.231"
TOI_PATROL = "https://www.tshandbok.no/del-2/8-kontroll-og-sanksjoner/doc731/"
FLISS = "https://pmc.ncbi.nlm.nih.gov/articles/PMC6970293"
AB645 = "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240AB645"
AB645_WB = "https://web.archive.org/web/20260206135943/https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240AB645"
SPEEDMGMT = "https://www.sfmta.com/getting-around/walk/speed-management"
CAL_SAFETY = "https://www.sfmta.com/californiasafety"
GG_ARF = "https://SFCTA.org/sites/default/files/2019-03/ARF%20Golden_Gate_Avenue_Buffered_Bike_Lane__NTIP_Capital.pdf"
SFCTA_14TH = "https://www.sfcta.org/sites/default/files/2021-09/Item%206%20-%20Grouped%20Prop%20K%20Allocations%20MEMO.pdf"
NYC_STE = "https://nyc.gov/html/dot/downloads/pdf/safety-treatment-evaluation-2005-2018.pdf"
SB_DIETS = "https://sf.streetsblog.org/2010/03/31/san-francisco-planners-proud-of-long-list-of-road-diets"
# low-traffic-neighborhoods
# car-free-streets
# leading-pedestrian-interval (stays "in"; better source and count)
# speed-humps (stays "in"; count from the device data)
# transit-only-lanes (stays "in")
SLOW_EVAL = "https://www.sfmta.com/sites/default/files/reports-and-documents/2023/12/2023_slow_streets_evaluation_report_accessible.pdf"
SLOW_TOOLKIT = "https://www.sfmta.com/media/35181/download?inline"
SLOW_S24 = "https://www.sfmta.com/project-updates/spring-2024-slow-streets-program-update"
SLOW_W25 = "https://www.sfmta.com/project-updates/winter-2025-slow-streets-program-update"
NOE_SB = "https://sf.streetsblog.org/2024/08/20/traffic-diverter-removed-from-plan-for-slow-noe-street"
PBOT_NG = "https://www.portland.gov/transportation/pbot-projects/neighborhood-greenways/documents/neighborhood-greenway-assessment-0/download"
PBIC_COST = "https://web.archive.org/web/2024/https://www.pedbikeinfo.org/cms/downloads/Countermeasure%20Costs_Report_Nov2013.pdf"

NEW = [
# ---- from research-A.md
dict(
  id="traffic-circles", name="Traffic circles and mini roundabouts", short_name="Traffic circles", group="spot",
  one_line="A small round island in the middle of a residential intersection, so drivers have to slow down and steer around it.",
  cost=dict(text="No SF unit cost found. Seattle prices a neighborhood circle at $20,000 to $25,000; the US median is $27,190 for circles and roundabouts together (non-SF)", short="$20K-$25K a circle (Seattle)",
            value_low=20000, value_high=25000, unit="per intersection",
            source_url="https://www.seattle.gov/transportation/projects-and-programs/programs/home-zone-program/traffic-calming/traffic-circles",
            source_title="Seattle DOT, Traffic Circles, undated [primary — read 2026-10-23, non-SF]; Bushell et al. 2013, Table 9, p. 16 [primary — read 2026-10-23, non-SF]"),
  effect=dict(text="61% fewer fatal and injury crashes when a two-way stop becomes a mini roundabout. But crashes went up when the intersection had been an all-way stop. FHWA's 78% to 82% is for full roundabouts, not neighborhood circles", short="-61% injury crashes (from two-way stop)", pct=-61,
              outcome="crashes", design="not stated", where="US",
              source_url="https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=11241",
              source_title="CMF Clearinghouse 11241, Mishra et al. 2022, CMF 0.39 for fatal and injury crashes, 105 rating points; all-way stop to mini roundabout is CMF 1.74 (facid 11244) [primary — read 2026-10-23]"),
  opposition=dict(grade="Medium",
    reason="SFMTA removed one circle after six months when neighbors complained, and the fire department's review rules keep circles off narrow streets.",
    examples=[{"text": "McAllister and Steiner circle removed in 2018 'Due to the safety and noise concerns observed and documented by neighbors' (Streetsblog) [secondary — verify]", "url": "https://sf.streetsblog.org/2018/08/20/sfmta-launches-muni-backward-program/"},
              {"text": "SFFD manual p. 32: 'Distance from curb to face of Traffic Circle: 20' minimum'; circles need a one-month review (p. 22)", "url": "https://www.sfmta.com/media/45260/download"}]),
  programs=P(ssc=("in", SSC, "Physical infrastructure toolkit, biking and rolling: 'Traffic circles'"),
             mta=("limits", "https://www.sfmta.com/media/45260/download", "SFMTA/SFFD Street Design Review Manual p. 32: 'Distance from curb to face of Traffic Circle: 20' minimum'; one-month Battalion Chief review (p. 22)")),
  sf_example=dict(name="Euclid and Parker avenues, Laurel Heights/Jordan Park Traffic Calming Project (a second circle went in at Euclid and Collins)", year=2018,
                  lat=37.784030, lon=-122.454618, geometry_hint="point", source_url="https://www.sfmta.com/fr/node/15989"),
  by_user=U(
    ("Slower cars through the crossing.", "Drivers watch the circle, not the crosswalk; SFMTA weighed extra crosswalk islands at Euclid.", "https://www.sfmta.com/fr/node/15989", "SFMTA said it was 'Considering concrete islands to separate the travel lane from the crosswalks' after the Euclid circles went in."),
    ("Calmer crossing on bike routes without a stop.", "Drivers can squeeze bikes on the way round.", None, "[inference — mine]"),
    ("None measured.", "Buses and trucks need a mountable apron.", "https://www.sfmta.com/media/45260/download", "SFFD manual p. 32 requires a 2-inch mountable apron for the short review."),
    ("Fewer crashes than a two-way stop.", "More crashes than an all-way stop, in the one study that measured it.", "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=11244", "Mishra et al. 2022: CMF 1.74 for fatal and injury crashes when an all-way stop became a mini roundabout."),
    ("Named in the school biking toolkit.", "No SF school example found.", SSC, "Safe School Connections lists traffic circles under biking and rolling infrastructure."))),
# ---- from research-A.md
dict(
  id="raised-crossings", name="Raised crosswalks and raised intersections", short_name="Raised crossings", group="spot",
  one_line="A crosswalk built up to about sidewalk height, so drivers have to slow down to cross it and people walking are easier to see.",
  cost=dict(text="$15,000 an asphalt raised crosswalk, construction only (SFMTA engineer's estimate); about $28,600 a device all-in across SF's FY21 calming cycle. A whole raised intersection is a US median of $59,160 (non-SF)", short="$15K-$29K a crossing",
            value_low=15000, value_high=28592, unit="per crosswalk",
            source_url="https://www.sfcta.org/sites/default/files/2021-03/Item%207%20-%20Grouped%20Allocations%20ENCLOSURE.pdf",
            source_title="SFCTA March 2021 enclosure, Vision Zero Proactive Traffic Calming allocation request, 'Asphalt Raised Crosswalks $15,000.00', 'Engineer's estimate based on prior work' (enclosure p. E7-27) [primary — read 2026-10-23, cached .cache/calming]; all-in figure from SFCTA R26-06 as in the speed-humps row"),
  effect=dict(text="30% fewer injury crashes on two-lane local streets", short="-30% injury crashes", pct=-30,
              outcome="crashes", design="meta-analysis", where="international",
              source_url="https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=137",
              source_title="CMF Clearinghouse 137, Elvik and Vaa 2004 Handbook of Road Safety Measures, CMF 0.7, severity A/B/C, 75 rating points [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="Residents request them through the calming program; the friction is the fire department, which objects to raising both crosswalks at one intersection.",
    examples=[{"text": "SFFD manual p. 29: 'Significant Concerns' about intersections 'that would require apparatuses to slow down or stop twice'", "url": "https://www.sfmta.com/media/45260/download"},
              {"text": "Four raised crosswalks on Silver Ave, FY21 cycle: 'Working with SFFD on approval' (SFCTA R26-06)", "url": R2606}]),
  programs=P(ssc=("in", SSC, "Traffic calming and safety upgrades for people walking: 'Raised crosswalks'"),
             srts=("in", SRTS, "Section X, p. 44: walk audits can 'add speed tables, raised crosswalks'"),
             mta=("in", "https://www.sfmta.com/raised-crosswalks", "Residential Traffic Calming Program installs asphalt raised crosswalks (SFFD manual p. 29); 7-day fire review (p. 22). Limits: one leg per intersection until SFFD agrees otherwise (p. 46)")),
  sf_example=dict(name="Yerba Buena Avenue at Brentwood Avenue, south leg, application-based traffic calming FY21 cycle", year=2024,
                  lat=37.733645, lon=-122.459064, geometry_hint="point", source_url=R2606),
  by_user=U(
    ("Drivers yield more and slow at the crossing.", "Only one leg of an intersection, under the fire rule.", "https://www.sfmta.com/raised-crosswalks", "SFMTA: at two Golden Gate Park crosswalks 'vehicles yielding to pedestrians increased by an average of 21%'."),
    ("Slower cars at bike-route crossings.", "A bump for people biking on the cross street.", "https://www.sfmta.com/raised-crosswalks", "SFMTA installed raised crosswalks on the Wiggle 'to lower vehicle speeds through intersections'."),
    ("None measured.", "Buses slow at each one.", None, "[inference — mine]"),
    ("Clear place to slow and look.", "Slower trips; noise.", "https://www.sfmta.com/raised-crosswalks", "John Muir Boulevard: after three raised crosswalks, 85th percentile speeds 'fell from 43 mph to 29 mph'."),
    ("The walk-audit list for schools includes them.", "Each one needs fire review.", SRTS, "Safe Routes 2024-25, p. 44."))),
# ---- from research-A.md
dict(
  id="refuge-islands", name="Pedestrian refuge islands and medians", short_name="Refuge islands", group="spot",
  one_line="A raised island in the middle of a wide street, so people can cross one direction of traffic at a time.",
  cost=dict(text="$10,000 a traffic island in an SF calming estimate; $10,460 the US median for a median island, up to $41,170 (non-SF). No SF figure for an arterial refuge", short="$10K-$41K an island",
            value_low=10000, value_high=41170, unit="per island",
            source_url="https://www.sfcta.org/sites/default/files/2021-03/Item%207%20-%20Grouped%20Allocations%20ENCLOSURE.pdf",
            source_title="SFCTA March 2021 enclosure, 'Traffic Islands $10,000.00', engineer's estimate (p. E7-27) [primary — read 2026-10-23]; Bushell et al. 2013, Table 6, p. 15 [primary — read 2026-10-23, non-SF]"),
  effect=dict(text="56% fewer pedestrian crashes with a refuge island; 46% with a raised median at a marked crosswalk", short="-56% pedestrian crashes", pct=-56,
              outcome="pedestrian crashes", design="not stated", where="FHWA",
              source_url=WB + "medians-and-pedestrian-refuge-islands-urban-and-suburban-areas",
              source_title="FHWA Proven Safety Countermeasures, Medians and Pedestrian Refuge Islands, 2026 snapshot (cached .cache/vz-cities/psc) [primary — read 2026-10-23]; the 46% is CMF 175, Zegeer et al. 2002, a cross-section comparison on 3- to 8-lane arterials (CMF Clearinghouse, read 2026-10-23)"),
  opposition=dict(grade="Low",
    reason="No fights over a refuge island were found; the fire department's manual limits tall islands on streets narrower than 20 to 26 feet of clear width.",
    examples=[{"text": "SFFD manual p. 41: a 6-8\" refuge where '20/26' roadway emergency clear width is not maintained' goes to extended review", "url": "https://www.sfmta.com/media/45260/download"}]),
  programs=P(mta=("in", "https://www.sfmta.com/getting-around/walk/pedestrian-improvements-toolkit/pedestrian-refuges", "SFMTA pedestrian toolkit; built on Upper Market and Geary. Limits: SFFD manual p. 41 on height where clear width is short"),
             ssi=("considered", SSA, "Street Safety Act 4(a): Public Works to build 'curb extensions, speed humps, islands, turn calming' when repaving HIN and arterial streets")),
  sf_example=dict(name="Geary Boulevard at Laguna Street, median pedestrian refuge, Geary Rapid Project", year=2021,
                  lat=37.784954, lon=-122.427989, geometry_hint="point", source_url="https://www.sfmta.com/node/23165"),
  by_user=U(
    ("Cross one direction at a time; a place to wait halfway.", "Only helps on wide streets.", WB + "medians-and-pedestrian-refuge-islands-urban-and-suburban-areas", "FHWA: 56% fewer pedestrian crashes; it advises refuges on multilane streets with over 9,000 vehicles a day and speeds of 35 mph or more."),
    ("None measured.", "Can pinch the lane beside a bike lane.", None, "[inference — mine]"),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("Fewer left-turn and crossing conflicts.", "Narrower lanes; lost left turns at some medians.", None, "[inference — mine]"),
    ("Helps the slowest crossers most.", "Not in any school program.", "https://www.sfmta.com/getting-around/walk/pedestrian-improvements-toolkit/pedestrian-refuges", "SFMTA: refuges help 'children and others who may struggle to cross in one stage'."))),
# ---- from research-A.md
dict(
  id="bulb-outs", name="Bulb-outs (curb extensions)", short_name="Bulb-outs", group="spot",
  one_line="The sidewalk is built out into the parking lane at a corner, so the crossing is shorter and people waiting to cross are easier to see.",
  cost=dict(text="Up to about $185,000 a bulb-out in SF: Bayview's $2.77M construction allocation buys 15 bulb-outs and two flashing beacons. The US median is $10,150 (2013, non-SF)", short="Up to $185K a bulb-out",
            value_low=None, value_high=184500, unit="per bulb-out (one corner)",
            source_url="https://www.sfcta.org/sites/default/files/2023-02/SFCTA_CAC_PropKGroupedAllocationsMEMO_2023-02-22.pdf",
            source_title="SFCTA Prop K grouped allocations memo, 2023-02-16, Bayview CBTP Implementation, construction, $2,767,500 for RRFBs at two intersections 'and 15 bulbouts' (PDF p. 8) [primary — read 2026-10-23]; per bulb-out is $2,767,500 / 15, an upper bound because the beacons are in it [inference — mine]"),
  effect=dict(text="16.5% fewer pedestrian injuries and 44.7% fewer pedestrians killed or seriously injured at 266 NYC curb extensions. A 2026 Philadelphia study found 11% fewer crashes, not statistically clear", short="-17% pedestrian injuries", pct=-16.5,
              outcome="pedestrian injuries", design="before-after", where="New York",
              source_url="https://nyc.gov/html/dot/downloads/pdf/safety-treatment-evaluation-2005-2018.pdf",
              source_title="NYC DOT, Safety Treatment Evaluation (2005-2018), 2022, p. 2, simple before-after, 266 treatments [primary — read 2026-10-23]; CMF Clearinghouse 12197, Guerra et al. 2026, CMF 0.89 (SE 0.168) [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="No reversal found. The limits are cost and drainage, and the fire department reviews mid-block neckdowns for a month and is still testing them.",
    examples=[{"text": "SFFD manual p. 46: 'Neckdown Treatments ... Testing on Kirkham St beginning Fall 2024'", "url": "https://www.sfmta.com/media/45260/download"},
              {"text": "269 bulb-outs installed 2017-2020 (SFMTA)", "url": "https://sfmta.com/media/28271/download"}]),
  programs=P(ssc=("in", SSC, "Traffic calming and safety upgrades for people walking: 'Corner bulbouts'"),
             mta=("in", "https://sfmta.com/media/28271/download", "SFMTA Bayview Bulb-Outs flyer, 2021: '269 bulb-outs installed in SF between 2017 and 2020'"),
             ssi=("considered", SSA, "Street Safety Act 4(a): Public Works to build 'curb extensions' when repaving HIN and arterial streets")),
  sf_example=dict(name="Mission Street and Geneva Avenue Infrastructure Improvement Project, 34 corner bulb-outs", year=2026,
                  lat=37.716460, lon=-122.441020, geometry_hint="point at Mission and Geneva; the project runs Geneva from Prague to Mission and Mission from Geneva to Trumbull",
                  source_url="https://www.sfcta.org/blogs/celebrating-delivery-mission-street-and-geneva-avenue-infrastructure-improvements"),
  by_user=U(
    ("Shorter crossing; people waiting are visible past parked cars.", "None measured.", "https://nyc.gov/html/dot/downloads/pdf/safety-treatment-evaluation-2005-2018.pdf", "NYC DOT: pedestrian KSI fell 44.7% at curb and sidewalk extensions."),
    ("None measured.", "Can squeeze people biking toward the travel lane at the corner.", None, "[inference — mine]"),
    ("Transit bulbs let buses stop in lane.", "A corner bulb can slow a turning bus.", None, "[inference — mine]"),
    ("Slower turns.", "Loses parking at the corner; the fire department wants wide clearances.", "https://sfmta.com/media/28272/download", "SFMTA: bulb-outs 'increase cars stopping for pedestrians by 25%' and 'slow turning vehicle speeds by 55%' (no study named)."),
    ("Bayview's bulb-outs were placed for school access.", "Expensive, so few per school.", "https://sfmta.com/media/28272/download", "The Bayview flyer names the Leola Havard Early Education School on Oakdale Ave."))),
# ---- from research-A.md
dict(
  id="protected-intersections", name="Protected intersections", group="spot",
  one_line="Concrete corner islands keep people biking separate from turning cars right up to the crosswalk, and make drivers turn slowly and square.",
  cost=dict(text="About $350,000 for 9th and Division, the city's first, which Streetsblog called 'half a protected intersection'", short="About $350K an intersection",
            value_low=350000, value_high=None, unit="per intersection",
            source_url="https://cal.streetsblog.org/2019/11/01/protected-intersection-update-whats-next",
            source_title="Streetsblog California, Protected Intersection Update: What's Next?, 2019-11-01 [secondary — verify]"),
  effect=dict(text="No crash reduction factor found. The federal NCHRP 15-73 study found protected intersections 'perform better (in terms of crash rates and high-severity conflicts)' than conventional bike lanes", short="Fewer conflicts; no crash figure", pct=None,
              outcome="conflicts", design="cross-section", where="US",
              source_url="https://www.nationalacademies.org/read/28289/chapter/2",
              source_title="NCHRP 15-73, Design Options to Reduce Conflicts Between Turning Motor Vehicles and Bicycles: Conduct of Research Report, 2024, summary [primary — read 2026-10-23]"),
  opposition=dict(grade="Medium",
    reason="Few have been built, SFMTA does not make them the default with protected bike lanes, and separated bikeways get case-by-case fire review.",
    examples=[{"text": "'SFMTA doesn't seem to use them as the default' (Streetsblog, 2026-04-17) [secondary — verify]", "url": "https://sf.streetsblog.org/2026/04/17/mercedes-driver-runs-red-hits-cyclist-speeds-off"},
              {"text": "SFFD manual p. 36: separated bikeways, 'Extended Review: Case-by-case basis'", "url": "https://www.sfmta.com/media/45260/download"}]),
  programs=P(mta=("in", "https://www.sfmta.com/press-releases/press-release-san-francisco-breaks-ground-folsom-streetscape-project", "Folsom Streetscape (ground broken 2024-05-13) lists 'Protected corners at intersections'; Mid-Valencia proposal (Nov 2024) would 'Include protected intersections'")),
  sf_example=dict(name="9th and Division streets, San Francisco's first protected intersection", year=2016,
                  lat=37.769463, lon=-122.406213, geometry_hint="point", source_url="https://www.sfmta.com/node/13725"),
  by_user=U(
    ("Turning drivers slower and squarer at the crosswalk.", "None measured.", "https://www.sfmta.com/node/13725", "SFMTA: 'concrete islands placed at the corners slow turning cars'."),
    ("Protection carried through the corner, where most right-hook crashes happen.", "Riders wait in a corner queue at signals.", "https://cal.streetsblog.org/2019/11/01/protected-intersection-update-whats-next", "Streetsblog cites an SFMTA study at 9th and Division: '96 percent of drivers approaching a bicyclist yielded where they were supposed to' [secondary — verify]."),
    ("None measured.", "Tighter corners for buses unless the islands are mountable.", None, "[inference — mine]"),
    ("Predictable turns.", "Slower right turns; fewer free right turns.", None, "[inference — mine]"),
    ("Useful where a school route meets a protected bike lane.", "Not in any school program.", None, "[inference — mine]"))),
# ---- from research-B.md
dict(
  id="hardened-daylighting", name="Hardened daylighting", group="spot",
  one_line="Posts, planters, concrete islands or bike corrals in the 20 feet beside a crosswalk, so the daylit corner stays clear without relying on paint.",
  cost=dict(text="No SF unit cost found. New York's DOT estimates $10,000 per hardened daylight location for labor and materials, which it calls 'a very round number rule of thumb' (not SF)", short="About $10K a corner (NYC)",
            value_low=10000, value_high=None, unit="per location (corner) [not SF]",
            source_url=NYC_HD_COST, source_title="NYC Council Transportation Committee hearing 2025-04-21, DOT estimate relayed by CM Julie Won; DOT's Eric Beaton: 'a very round number rule of thumb estimate' [secondary — verify]"),
  effect=dict(text="In New York, corners with hardened daylighting averaged a pedestrian injury every 3.4 years against 2.3 years expected without it, about 32% fewer [inference — mine, from NYC's intervals]; sign-only daylighting showed no significant effect, and neither showed 'a significant relationship with an increase or decrease in overall injuries'", short="-32% pedestrian injuries; no clear change in all injuries", pct=-32,
              outcome="pedestrian casualties, all severities", design="controlled", where="New York",
              source_url=NYC_DAYLIGHT, source_title="NYC DOT, NYC Daylighting Study, 2025, pp. 22-26, difference-in-differences against nearby non-daylit intersections, 2017-2023 crash data [primary — read 2026-10-23]; percent is 1/3.4 vs 1/2.3 [inference — mine]"),
  opposition=dict(grade="Low",
    reason="The parking is already gone under state law, so hardening takes nothing new; SFMTA's Board adopted the Community Corners pilot in June 2026 [inference — mine on the parking point].",
    examples=[{"text": "Street Safety Act 1(d) asks SFMTA for a plan for 'hardened daylighting' on the High-Injury Network by December 2026", "url": SSA},
              {"text": "SFMTA Board adopted Resolution 260616-054 creating the two-year Community Corners pilot, 2026-06-16", "url": CC_RES}]),
  programs=P(mta=("in", CC_REPORT, "Safety Zone Program: staff-led 'concrete islands, bike corrals, turn safety treatments' plus the Community Corners pilot, adopted 2026-06-16; no count of hardened corners"),
             ssi=("considered", SSA, "Street Safety Act 1(d): plan for citywide daylighting 'including hardened daylighting on the High-Injury Network by December 2026'; 4(a) asks Public Works to build hardened daylighting when repaving HIN and arterial streets; SSI Action 18 (prototypes for community-installed protection) led to Community Corners")),
  sf_example=None,
  nearest_example=dict(city="New York", name="NYC DOT hardened daylighting (turn calming, neckdowns, bike corrals, Citi Bike stations at the corner), 2019 to 2021 installs", url=NYC_DAYLIGHT),
  by_user=U(
    ("Corners stay clear even where paint is ignored; NYC found fewer pedestrian injuries.", "None measured.", NYC_DAYLIGHT, "NYC DOT: hardened daylighting 'is associated with a decrease in pedestrian injuries'; neckdowns did best (one injury every 4.7 years vs 1.4 expected)."),
    ("Bike corrals at the corner add parking and keep the sight line.", "None measured.", CC_REPORT, "SFMTA lists bike corrals among its Safety Zone Program tools."),
    ("None measured.", "Posts can tighten a bus's turn at the corner.", None, "[inference — mine]"),
    ("Clear view of people at the corner.", "Nothing new lost; the space is already no-parking under AB 413.", CC_REPORT, "Staff report p. 2: AB 413 bans parking within 20 feet of the approach to any crosswalk."),
    ("Keeps school corners clear without daily enforcement.", "The community version is limited to quiet stop-sign corners, not the busy ones.", CC_REPORT, "Staff report p. 4: eligible locations envisioned as streets under 2,000 vehicles a day at stop-controlled intersections."))),
# ---- from research-B.md
dict(
  id="turn-calming", name="Hardened centerlines and turn calming", short_name="Turn calming", group="spot",
  one_line="Posts, rubber curbs and small speed bumps on the centerline and corner, so drivers turning left take the corner slowly and squarely.",
  cost=dict(text="About $3,700 a location: SFCTA's $100,000 Prop L allocation for 27 left-turn calming locations, covering paint, posts, rubber speed bumps, outreach and evaluation [inference — mine on the division]", short="About $3.7K an intersection",
            value_low=3704, value_high=None, unit="per intersection",
            source_url=PROPL_LT, source_title="SFCTA CAC Prop L allocations presentation 2024-02-28, slide 4, Vision Zero Left Turn Traffic Calming [primary — read 2026-10-23]"),
  effect=dict(text="In New York, pedestrian injuries fell 18% at turn-calmed intersections, but car occupant injuries rose, so all injuries were about flat (+0.3%) while killed or seriously injured fell 16%; in SF, treated corners had a 99% safe-turn rate against 84% untreated", short="All injuries +0.3%; pedestrians -18%", pct=0.3,
              outcome="all injuries", design="before-after", where="New York",
              source_url="https://nyc.gov/html/dot/downloads/pdf/safety-treatment-evaluation-2005-2018.pdf", source_title="NYC DOT, Safety Treatment Evaluation (2005-2018), 2022: turn calming all road users +0.3% injuries, -16.2% KSI; pedestrians -17.5%; motor vehicle occupants +13.6% [primary — read 2026-10-23]; NYC DOT Turn Calming Program page (" + NYC_TURN + "), 1,236 intersections as of 2025-12-31, 1,236 intersections as of 2025-12-31; method not described beyond comparison locations [primary — read 2026-10-23]; SF: " + LT_EVAL + " [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="Posts and bumps inside the intersection take no parking or lane, and SFMTA has done 220 intersections with no reported reversal [inference — mine on opposition].",
    examples=[{"text": "Turn Safety Treatments at 220 intersections completed (SFMTA Board, Jan 2026)", "url": DECK},
              {"text": "SFCTA allocated Prop L for 27 more locations, Feb 2024", "url": PROPL_LT}]),
  programs=P(mta=("in", LT_PAGE, "Left Turn Safety program in the Pedestrian Improvements Toolkit; Vision Zero action: 'left-turn traffic calming at 35 new high priority locations on the HIN' by 2024"),
             ssi=("in", DECK, "Street Safety Commitments deck, Jan 2026: Turn Safety Treatments at 220 intersections, next 18 months 'a subset of the 2025 HIN'; Street Safety Act 1(a), 1(b) and 4(a) ask for more turn calming")),
  sf_example=dict(name="Polk Street at Turk Street, one of SFMTA's Left Turn Safety intersections", year=None,
                  lat=37.782169, lon=-122.418993, geometry_hint="point", source_url=DECK),
  by_user=U(
    ("Slower left turns into the crosswalk; NYC saw 18% fewer pedestrian injuries.", "None measured.", LT_EVAL, "SFMTA: every treated intersection averaged a left-turn speed below the 15 mph safe-turn threshold."),
    ("Slower turning cars across the bike lane.", "Centerline posts narrow the space beside a left-turning car.", None, "[inference — mine]"),
    ("None measured.", "Can slow a bus's left turn.", None, "[inference — mine]"),
    ("Clear guidance on where to turn.", "Slower turns; the posts need replacing when hit.", LT_PAGE, "SFMTA: treatments encourage 'slower, wider left turns'."),
    ("Left turns are where seniors and children crossing are hit most.", "None measured for children.", LT_PAGE, "SFMTA: 'In 2019, 40% of traffic deaths in San Francisco were caused when drivers made left turns.'"))),
# ---- from research-B.md
dict(
  id="no-turn-on-red", name="No turn on red", group="spot",
  one_line="Signs ban turning while the light is red, so drivers stop blocking the crosswalk while they look left for a gap.",
  cost=dict(text="No SF cost found. FHWA's PEDSAFE puts a sign at $30 to $150 plus $200 to install; SF uses about eight signs an intersection, so about $1,800 to $2,800 [inference — mine]", short="About $2K an intersection",
            value_low=1840, value_high=2800, unit="per intersection [not SF]",
            source_url=PEDSAFE_RTOR, source_title="FHWA PEDSAFE, Right-Turn-on-Red Restrictions [primary — read 2026-10-23]; eight signs an intersection from SF Standard 2024-04-02 [secondary — verify]"),
  effect=dict(text="Allowing turns on red where they were banned raised pedestrian and bike crashes 69% (Highway Safety Manual); a ban is our reading of the reverse, about 41% fewer [inference — mine]. SF's Tenderloin study measured behavior only: crosswalk blocking down more than 70%, 92% compliance", short="-41% pedestrian and bike crashes", pct=-41,
              outcome="crashes", design="before-after", where="US (HSM)",
              source_url=CMF_RTOR, source_title="CMF Clearinghouse ID 4579, Permit right-turn-on-red, HSM 1st ed., CMF 1.69, vehicle/pedestrian and vehicle/bicycle, empirical Bayes [primary — read 2026-10-23]; reversal 1/1.69 = 0.59 [inference — mine]; SF: " + NTOR_EVAL + " [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="No organized opposition reported; the limit is SFMTA's: it declined a citywide ban, citing sign crews.",
    examples=[{"text": "Tumlin: 'We do not have enough crews to be putting up thousands of metal signs all over the city' [secondary — verify]", "url": SFSTD_NTOR},
              {"text": "About 200 downtown intersections approved by the City Traffic Engineer, 2024", "url": NTOR_DT}]),
  programs=P(mta=("in", NTOR_DT, "About 50 Tenderloin intersections since fall 2021; about 200 downtown legislated, construction listed April 2024 to September 2027, 'Pending'"),
             ssi=None),
  sf_example=dict(name="Larkin Street at Turk Street, one of the Tenderloin No Turn on Red study intersections", year=2021,
                  lat=37.782379, lon=-122.417339, geometry_hint="point", source_url=NTOR_EVAL),
  by_user=U(
    ("Crosswalks stay clear on red; close calls fell from 5 to 1.", "No change in drivers yielding on green.", NTOR_EVAL, "SFMTA Tenderloin evaluation, 3 treated intersections and Hyde/Turk as control."),
    ("Fewer drivers nosing into the crosswalk and bike lane on red.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "None measured.", None, None),
    ("Simple rule, high compliance (92%).", "Longer waits to turn.", NTOR_EVAL, None),
    ("Turns on red cause 20% of turning-driver injury crashes with people walking or biking at SF signals.", "Only at signals.", NTOR_EVAL, "SFMTA: turn-on-red crashes are under 1% of all injury crashes but 20% of pedestrian or bicycle injury crashes with turning drivers at signals."))),
# ---- from research-B.md
dict(
  id="pedestrian-scrambles", name="Pedestrian scrambles", group="spot",
  one_line="An all-way red for cars, with no turns, while people cross in every direction including diagonally.",
  cost=dict(text="No SF cost found. At an existing signal it is mostly a timing change, 'a few hours of staff time'; new signal equipment runs $8,000 to $150,000 (FHWA PEDSAFE, not SF)", short="Timing change to $150K",
            value_low=8000, value_high=150000, unit="per intersection [not SF]",
            source_url=PEDSAFE_SIG, source_title="FHWA PEDSAFE, Pedestrian Signal Timing [primary — read 2026-10-23]"),
  effect=dict(text="51% fewer pedestrian-vehicle crashes in New York (97 before, 19 after; comparison sites fell 9%), but 10% more crashes between vehicles", short="-51% pedestrian crashes", pct=-51,
              outcome="crashes", design="before-after", where="New York",
              source_url=CMF_SCRAMBLE, source_title="CMF Clearinghouse ID 4117 (and 4118 for multi-vehicle, CMF 1.1), Chen, Chen and Ewing 2012, simple before/after, 1998-2008 [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="No opposition found to SF's scrambles; the cost is a longer wait for everyone at the signal [inference — mine].",
    examples=[{"text": "Eleven Tenderloin intersections converted to scrambles (SFMTA)", "url": SCRAMBLE}]),
  programs=P(mta=("in", SCRAMBLE, "SFMTA Pedestrian Improvements Toolkit; Chinatown and Financial District scrambles plus eleven in the Tenderloin")),
  sf_example=dict(name="Stockton and Sacramento streets, Chinatown pedestrian scramble", year=None,
                  lat=37.793178, lon=-122.407727, geometry_hint="point", source_url=SCRAMBLE),
  by_user=U(
    ("No turning cars during the walk phase; NYC saw 51% fewer pedestrian crashes.", "Longer wait for the walk signal.", CMF_SCRAMBLE, "SFMTA: scrambles 'eliminate all potential conflicts between pedestrians and vehicles'."),
    ("None measured.", "Longer red for bikes too.", None, "[inference — mine]"),
    ("None measured.", "Adds a phase, so buses wait longer.", None, "[inference — mine]"),
    ("No pedestrians in the crosswalk while turning.", "Longer cycle; crashes between vehicles rose 10% in NYC.", CMF_SCRAMBLE_MV, "CMF 1.1 for multi-vehicle crashes, same study."),
    ("A protected crossing for children in busy districts.", "Only fits busy signals with many people walking.", None, "[inference — mine]"))),
# ---- from research-B.md
dict(
  id="bike-signals", name="Bicycle signals and separate turn phases", short_name="Bike signals", group="spot",
  one_line="A bike-only signal gives people on bikes their own green while turning drivers wait, so a right hook can't happen.",
  cost=dict(text="$50,000 to $250,000, Vision Zero's third band (national data; per intersection is our reading [inference — mine])", short="$50K-$250K a signal",
            value_low=50000, value_high=250000, unit="per intersection [inference — mine]",
            source_url=VZ, source_title=VZ_TAB + " (Bicycle Traffic Signals, $$$, ++)"),
  effect=dict(text="No crash study found. At two SF bike signals, the share of right-turning drivers who met a bike fell from 41% (at mixing zones) to 2%, and close calls from 17 to 1", short="Conflicts 41% to 2%", pct=None,
              outcome=None, design=None, where="San Francisco",
              source_url=BIKESIG_EVAL, source_title="SFMTA, Bike Signals and Mixing Zones evaluation, Folsom/8th and 8th/Brannan vs 6 mixing zones, peak-hour video, 2018 [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="No opposition found; the cost is green time taken from turning traffic [inference — mine].",
    examples=[{"text": "Townsend Street: 'new bicycle signals at 4th and Townsend' (SFMTA, complete 2020)", "url": TOWNSEND}]),
  programs=P(mta=("in", VZ, "Vision Zero tool table p. 26: Bicycle Traffic Signals ($$$, ++); SFMTA said in 2018 it would roll out 'more separated bike signals in 2019'")),
  sf_example=dict(name="4th and Townsend streets, bicycle signals on the Townsend Corridor project", year=2020,
                  lat=37.777089, lon=-122.394981, geometry_hint="point", source_url=TOWNSEND),
  by_user=U(
    ("None measured.", "A further phase can lengthen the pedestrian wait.", None, "[inference — mine]"),
    ("Own green with turning cars held; right-hook conflicts fell from 41% to 2%.", "People on bikes complied 86% of the time.", BIKESIG_EVAL, "SFMTA 2018: driver compliance 95%."),
    ("None measured.", "Less green for the street the bus is on.", None, "[inference — mine]"),
    ("No bike to watch for while turning.", "Turning drivers wait for their own phase.", BIKESIG_EVAL, None),
    ("Separates children on bikes from turning trucks and cars.", "Only on the few corridors with protected lanes.", None, "[inference — mine]"))),
# ---- from research-C.md
dict(
  id="signal-progression", name="Signals timed for slower speeds", short_name="Slower signal timing", group="spot",
  one_line="Traffic lights timed so a driver going 20 to 25 mph meets green after green, and a faster driver meets red.",
  cost=dict(text="No SF unit cost found; Vision Zero's lowest band, under $10,000 (national data; per intersection is our reading [inference — mine])", short="Under $10K a signal",
            value_low=None, value_high=10000, unit="per intersection [inference — mine]", source_url=VZ, source_title=VZ_TAB + " ($)" + F),
  effect=dict(text="No injury study found. On Franklin Street, typical 85th percentile speeds fell to 25 mph after SFMTA adjusted the signal timing in 2024, from 27 mph mid-block in the 2023 evaluation", short="No injury study; Franklin 27 to 25 mph", pct=None,
              outcome="speeds", design="before-after", where="Franklin St, SF",
              source_url=FRANKLIN, source_title="SFMTA, Franklin Street Quick-Build update, August 2024 [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="A timing change takes no lane or parking, and SFMTA has retimed corridors without a public fight on record [inference — mine].",
    examples=[{"text": "Valencia Street 'Green Wave': progression cut 'from 25 to 13 mph', 16th to 25th streets (SFMTA, Jan 2011)", "url": GREENWAVE},
              {"text": "Oak/Fell retiming, Octavia to Stanyan, with a '20mph vehicle progression speed' (SFMTA to the Market Octavia CAC, Nov 2022)", "url": MOCAC}]),
  programs=P(mta=("in", VZ, "Vision Zero tool table p. 26: Signal Progression Speeds, $ ++; the speed management action names 'traffic signal re-timing'"),
             ssi=("considered", SSI, "Action 22, in progress: 2025 HIN plan with 'signal timing optimization'; Street Safety Act 1(a), due December 2026. Neither says the speed the signals are timed to")),
  sf_example=dict(name="Valencia Street from 16th to 25th Street, the 'Green Wave' timed at 13 mph", year=2011,
                  lat=37.757712, lon=-122.421197, geometry_hint="lat/lon is the straight-line midpoint; street segment: Valencia St, 16th St (37.764917,-122.421886) to 25th St (37.750506,-122.420507)",
                  source_url=GREENWAVE),
  by_user=U(
    ("Slower cars between signals.", "None measured.", FRANKLIN, "Franklin St: 85th percentile 25 mph after retiming."),
    ("A green wave at bike speed on Valencia.", "Only where the progression is set for bikes.", GREENWAVE, "SFMTA set Valencia for 'bicyclists and motorists traveling at 13 mph'."),
    ("None measured.", "Buses can fall out of step with a slow wave.", None, "[inference — mine]"),
    ("Fewer stops for drivers at the set speed.", "Speeding gets a red, so peak trips may slow.", None, "[inference — mine]"),
    ("Calmer arterials near schools.", "Only on signal corridors; most school blocks have stop signs.", None, "[inference — mine]"))),
# ---- from research-C.md
dict(
  id="signal-upgrades", name="Signal visibility upgrades", short_name="Bigger, brighter signals", group="spot",
  one_line="Larger 12-inch signal heads on mast arms over the lanes, reflective borders around the lights, and yellow times set to the street's speed, so drivers see the signal sooner.",
  cost=dict(text="About $424,000 a signalized intersection: Public Works awarded Contract 35, larger signal heads, poles and mast arms, countdown and accessible signals and curb ramps at 17 locations, for $7.2M (estimate $9.18M, about $540,000 each)", short="$424K an intersection",
            value_low=423529, value_high=539928, unit="per signalized intersection, construction contract only",
            source_url=C35_PWC, source_title="Public Works Commission resolution awarding Contract No. 35 Traffic Signal Upgrades, 2026-04-30 [primary — read 2026-10-23]; " + VZ_TAB + " (New Signal Mast Arms & Signal Heads $$$; New Traffic Signals $$$$)" + F),
  effect=dict(text="15% fewer total crashes with reflective signal backplates; 8% to 14% fewer total crashes and 12% fewer injury crashes when yellow times are set properly", short="-15% crashes (backplates)", pct=-15,
              outcome="crashes", design="not stated", where="FHWA",
              source_url=WB + "backplates-retroreflective-borders", source_title="FHWA Proven Safety Countermeasures, Backplates with Retroreflective Borders (CMF 1410, Sayed et al. 2005) and Yellow Change Intervals (CMFs 380, 384, NCHRP Report 731, 2011) [primary — read 2026-10-23, cached 2026 snapshot]"),
  opposition=dict(grade="Low",
    reason="Work at the corner that takes no lane or parking; the limits are cost and construction time [inference — mine].",
    examples=[{"text": "Contract 35: 17 intersections, 9 on the High Injury Network, construction started at two in August 2026 (SFMTA)", "url": C35},
              {"text": "Western Addition: 'larger 12- inch signals and mast arms to enhance signal visibility' at 16 locations (SFMTA)", "url": WA1}]),
  programs=P(mta=("in", VZ, "Vision Zero tool table p. 26: New Signal Mast Arms & Signal Heads $$$ +++; New Traffic Signals $$$$ +++")),
  sf_example=dict(name="39th Avenue, Skyline and Sloat boulevards, new signal with mast arms and 12-inch heads, activated 2025-02-28", year=2025,
                  lat=37.733771, lon=-122.496636, geometry_hint="point", source_url=C65),
  by_user=U(
    ("New signals come with countdown and accessible signals and curb ramps.", "Years from design to switch-on.", C65, "Contract 65: design 2019, activations 2023 to 2025."),
    ("Drivers see the light sooner, so fewer red-light crashes [inference — mine].", "None measured.", None, "[inference — mine]"),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("A clearer signal, and a yellow matched to the street's speed.", "None measured.", WB + "yellow-change-intervals", "FHWA: 36% to 50% less red-light running with proper yellow times."),
    ("A new signal can make a hard crossing near a school possible.", "Costs hundreds of thousands per corner.", None, "[inference — mine]"))),
# ---- from research-C.md
dict(
  id="walk-speed", name="Longer crossing time (Walk Speed 3.0)", short_name="Longer crossing time", group="spot",
  one_line="Signals give enough walk and countdown time for someone walking 3 feet a second, not 3.5, so slower walkers finish crossing before cars move.",
  cost=dict(text="$10,000 to $50,000, Vision Zero's second band (national data; per intersection is our reading [inference — mine])", short="$10K-$50K a signal",
            value_low=10000, value_high=50000, unit="per intersection [inference — mine]", source_url=VZ, source_title=VZ_TAB + " (Walk Speed 3.0, $$)" + F),
  effect=dict(text="No injury study of longer clearance times found. SF's 2001 countdown-signal pilot saw 25% fewer pedestrian injury crashes (27 before, 13 after, a simple before-after)", short="No study; countdowns -25%", pct=None,
              outcome="crashes", design="before-after", where="San Francisco",
              source_url=CMF1409, source_title="CMF Clearinghouse CMF 1409, Markowitz et al. 2006, countdown signals, San Francisco 1999-2002, not in the Highway Safety Manual [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="A timing change that takes no lane or parking; SFMTA adopted it as the city standard in 2018.",
    examples=[{"text": "SFMTA 'committed to increasing the crossing time ... from 3.5 ft/second to 3.0 ft/second' in 2018", "url": PEDSIG},
              {"text": "Vision Zero action: 'Modify all eligible signals on the HIN for slower walking speeds' by 2024", "url": VZ}]),
  programs=P(mta=("in", VZ, "Vision Zero tool table p. 26: Walk Speed 3.0, $$ +++; action 'Modify all eligible signals on the HIN for slower walking speeds and leading pedestrian intervals', 2024"),
             ssi=("considered", DECK, "Street Safety Commitments deck, Jan 2026: signal changes at 1,500 intersections; it does not say how many changed walk speed")),
  sf_example=dict(name="Fell Street from Octavia to Stanyan, retimed with 'revised minimum walk times (for slower pedestrians)'", year=2024,
                  lat=37.773842, lon=-122.439204, geometry_hint="lat/lon is the straight-line midpoint; street segment: Fell St, Octavia St (37.775754,-122.424325) to Stanyan St (37.771930,-122.454083); Oak St was retimed in the same project",
                  source_url=VZRT),
  by_user=U(
    ("Older and disabled people finish crossing on time.", "Longer cycles mean longer waits.", PEDSIG, "SFMTA: nearly all of its 1,200+ signals have countdown signals."),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "A little less green time on wide streets.", None, "[inference — mine]"),
    ("Fewer people still in the crosswalk when the light changes [inference — mine].", "A little less green time.", None, "[inference — mine]"),
    ("Small children walk slowly too.", "Only at signals.", None, "[inference — mine]"))),
# ---- from research-C.md
dict(
  id="high-visibility-crosswalks", name="High-visibility crosswalks", short_name="Zebra crosswalks", group="spot",
  one_line="Wide 'continental' stripes along the line of travel instead of two thin lines, so drivers see the crossing from farther away.",
  cost=dict(text="No SF unit cost found; Vision Zero's lowest band, under $10,000; a US median of about $3,070 a crosswalk (PBIC 2013, non-SF), about $12,000 for four legs [inference — mine]", short="About $3K a crosswalk (US)",
            value_low=3070, value_high=12280, unit="per crosswalk (low) to per four-leg intersection (high) [inference — mine]",
            source_url=PBIC, source_title="Bushell et al., Costs for Pedestrian and Bicyclist Infrastructure Improvements, UNC HSRC for FHWA, 2013, Appendix D p. 42, non-SF [primary — read 2026-10-23]; " + VZ_TAB + " ($)" + F),
  effect=dict(text="Up to 40% fewer pedestrian injury crashes", short="-40% pedestrian injury crashes", pct=-40,
              outcome="pedestrian injuries", design="before-after", where="FHWA (NYC study)",
              source_url=WB + "crosswalk-visibility-enhancements", source_title="FHWA Proven Safety Countermeasures, Crosswalk Visibility Enhancements; the 40% is CMF 4123, Chen, Chen and Ewing 2012, a New York City study [primary — read 2026-10-23, cached 2026 snapshot]"),
  opposition=dict(grade="Low",
    reason="Paint that takes no lane or parking, and SFMTA has striped them at 3,869 intersections.",
    examples=[{"text": "3,869 intersections marked as having continental crosswalks in SFMTA's layer (queried 2026-10-23)", "url": CONT_LAYER},
              {"text": "'By 2024, all crosswalks on the Vision Zero High Injury Network will be upgraded to continental crosswalks' (SFMTA)", "url": CONT}]),
  programs=P(mta=("in", VZ, "Vision Zero tool table p. 26: Continental Crosswalks, $ ++; action 'Ensure all intersections on the HIN have high visibility crosswalks by 2024'")),
  sf_example=dict(name="Polk Street and Golden Gate Avenue, continental crosswalk installed 2019", year=2019,
                  lat=37.781236, lon=-122.418808, geometry_hint="point", source_url=CONT_LAYER),
  by_user=U(
    ("Drivers see the crossing sooner and yield more.", "Paint wears and needs restriping.", CONT, "SFMTA: wide stripes 'have been shown to increase yielding behavior among drivers' (no study cited)."),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("A clearer cue where to stop.", "None measured.", None, "[inference — mine]"),
    ("Marks the walking route to school.", "Paint alone does not slow cars.", None, "[inference — mine]"))),
# ---- from research-C.md
dict(
  id="flashing-beacons", name="Flashing beacons at crosswalks", short_name="Flashing beacons", group="spot",
  one_line="Push-button yellow lights (RRFBs) or red-signal beacons (pedestrian hybrid beacons) at a crosswalk with no traffic light, so drivers stop for the person waiting.",
  cost=dict(text="About $250,000 for one SF intersection ($75,000 design, $175,000 construction, SFCTA estimate for 38th Avenue and Geary); US medians are $14,160 an RRFB unit and $51,460 a hybrid beacon (PBIC 2013)", short="$250K an intersection",
            value_low=175000, value_high=250000, unit="per intersection (construction only to all-in)",
            source_url=G38, source_title="SFCTA Allocation Request Form, 38th and Geary Rectangular Rapid Flashing Beacons, FY2022/23, pp. 4 and 6 [primary — read 2026-10-23]; PBIC 2013 Appendix D p. 42 [primary — read 2026-10-23]"),
  effect=dict(text="RRFBs: up to 47% fewer pedestrian crashes; pedestrian hybrid beacons: 55% fewer pedestrian crashes", short="-47% to -55% pedestrian crashes", pct=-47,
              outcome="pedestrian crashes", design="not stated", where="FHWA",
              source_url=WB + "rectangular-rapid-flashing-beacons-rrfb", source_title="FHWA Proven Safety Countermeasures, RRFB (CMF 9024, NCHRP 841, 2017) and Pedestrian Hybrid Beacons (CMF 9020, NCHRP 841; 29% total and 15% serious-and-fatal from Fitzpatrick and Park 2010) [primary — read 2026-10-23, cached 2026 snapshot]"),
  opposition=dict(grade="Low",
    reason="No public fight found; the limit is federal rules, which bar RRFBs at stop signs and signals, and the cost of about $250,000 a corner.",
    examples=[{"text": "55 locations done, 10 more planned in 18 months (SFMTA Board, Jan 2026)", "url": DECK},
              {"text": "WalkFirst: 10 RRFBs with accessible signals, activated 2022 to 2025 (SFMTA)", "url": RRFB_WF}]),
  programs=P(ssc=("in", SSC, "Traffic calming and safety upgrades for people walking: 'Rectangular rapid flashing beacons'"),
             mta=("in", VZ, "Vision Zero tool table p. 26: Rapid Flashing Beacons, $$$ ++"),
             ssi=("in", DECK, "Safer Crossings draft plan: 55 locations done, 10 in the next 18 months")),
  sf_example=dict(name="Clay Street and Gough Street, RRFB activated 2025-10-15 (WalkFirst)", year=2025,
                  lat=37.791757, lon=-122.425980, geometry_hint="point", source_url=RRFB_WF),
  by_user=U(
    ("Drivers stop far more often for people waiting.", "Only where the person presses the button.", WB + "rectangular-rapid-flashing-beacons-rrfb", "FHWA: yielding up to 98% with an RRFB, varying by speed, lanes and crossing distance."),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "A stop at each activation.", None, "[inference — mine]"),
    ("A clear signal of when to stop.", "Brief stops on through streets.", None, "[inference — mine]"),
    ("SSC lists RRFBs for school connector streets.", "Not allowed at stop-sign corners, where most school crossings are.", WB + "rectangular-rapid-flashing-beacons-rrfb", "MUTCD via FHWA: no RRFBs on approaches with STOP or YIELD signs or signals."))),
# ---- from research-C.md
dict(
  id="speed-radar-signs", name="Speed radar signs", short_name="Radar speed signs", group="spot",
  one_line="Signs that flash each driver's speed back at them as they approach.",
  cost=dict(text="About $7,500 a sign bought and installed, $11,150 with city engineering (two signs for 19th Avenue, 2004 dollars); Vision Zero's band is $50,000 to $250,000", short="About $11K a sign (2004)",
            value_low=7500, value_high=11150, unit="per sign, 2004 dollars",
            source_url=RADAR04, source_title="Board of Supervisors Resolution, File 041239, 2004-09-07, CSAA gift of two radar speed signs for 19th Avenue, $15,001 purchase and install plus $7,300 DPT costs [primary — read 2026-10-23, OCR]; " + VZ_TAB + " ($$$)" + F),
  effect=dict(text="5% to 7% fewer crashes at rural curves (no urban or pedestrian study found); Vision Zero SF rates radar signs 'Minimal'", short="-5% to -7% crashes (rural)", pct=-7,
              outcome="crashes", design="before-after", where="22 rural curves, 7 states",
              source_url=CMF418, source_title="CMF Clearinghouse study 418, Hallmark et al., FHWA-HRT-14-020, 2015, CMFs 0.93 to 0.95 [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="No fight found; Vision Zero SF rates the tool's crash effect 'Minimal', the lowest on its table.",
    examples=[{"text": "Vision Zero tool table: Speed Radar Signs, $$$ cost, '+' effect ('Minimal')", "url": VZ},
              {"text": "Radar speed signs at Buchanan and Turk and Buchanan and Fulton in Western Addition Phase 1, construction to Fall 2026 (SFMTA)", "url": WA1}]),
  programs=P(mta=("in", VZ, "Vision Zero tool table p. 26: Speed Radar Signs, $$$ +")),
  sf_example=dict(name="Buchanan Street and Turk Street, radar speed signs in Western Addition Phase 1 (construction pending, not confirmed installed)", year=2026,
                  lat=37.780916, lon=-122.428853, geometry_hint="point", source_url=WA1),
  by_user=U(
    ("Slightly slower drivers near the sign [inference — mine].", "Effect measured on rural curves, not city streets.", CMF418, "Mean speeds fell up to 10.9 mph at some curve sites."),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("A reminder with no ticket.", "None measured.", None, "[inference — mine]"),
    ("Can sit on a school approach.", "No enforcement behind it.", None, "[inference — mine]"))),
# ---- from research-C.md
dict(
  id="street-lighting", name="Street lighting at crossings", short_name="Crossing lighting", group="spot",
  one_line="Brighter lights over crosswalks and corners, so drivers see people crossing at night.",
  cost=dict(text="About $43,800 a pole: $4.25M paid for 97 new street-and-sidewalk lights in the Tenderloin [inference — mine]; US median $3,600 a streetlight (PBIC 2013, non-SF)", short="About $44K a pole (SF)",
            value_low=3600, value_high=43800, unit="per light pole",
            source_url=TL_LIGHT, source_title="Tenderloin CBD, 97 newly installed street lights, 2019-01-10 [secondary — verify]; PBIC 2013 Appendix D p. 43 [primary — read 2026-10-23]"),
  effect=dict(text="Up to 42% fewer nighttime pedestrian injury crashes at intersections", short="-42% night pedestrian injuries", pct=-42,
              outcome="pedestrian injuries", design="not stated", where="FHWA",
              source_url=WB + "lighting", source_title="FHWA Proven Safety Countermeasures, Lighting; the 42% is from Elvik and Vaa, Handbook of Road Safety Measures, 2004 (CMFs 436, 433, 192) [primary — read 2026-10-23, cached 2026 snapshot]"),
  opposition=dict(grade="Low",
    reason="No objection to the lights themselves; the Tenderloin project stalled on a PG&E connection-fee dispute.",
    examples=[{"text": "PG&E sought $107,000 for the connection, a 'fourfold increase' per the SFPUC (Tenderloin CBD, citing the Chronicle, Sept 2017) [secondary — verify]", "url": TL_LIGHT17},
              {"text": "97 lights on Larkin, Hyde, Leavenworth and Jones between McAllister and O'Farrell, unveiled January 2019 [secondary — verify]", "url": TL_LIGHT}]),
  programs=P(),
  sf_example=dict(name="Tenderloin, 97 new street and sidewalk lights between McAllister and O'Farrell (point is Hyde and Eddy)", year=2019,
                  lat=37.783516, lon=-122.415883, geometry_hint="area: Larkin, Hyde, Leavenworth and Jones streets from McAllister to O'Farrell, and Eddy from Larkin to Mason; point is Hyde St and Eddy St",
                  source_url=TL_LIGHT),
  by_user=U(
    ("People crossing at night are easier to see.", "None measured.", WB + "lighting", "FHWA: up to 42% fewer nighttime pedestrian injury crashes at intersections."),
    ("Easier to see at night.", "None measured.", None, "[inference — mine]"),
    ("Brighter stops for people waiting.", "None measured.", None, "[inference — mine]"),
    ("Better night view of the crossing.", "None measured.", None, "[inference — mine]"),
    ("Helps winter-evening trips home.", "Most school trips are in daylight.", None, "[inference — mine]"))),
# ---- from research-D.md
dict(
  id="red-light-cameras", name="Red light cameras", group="programs",
  one_line="Cameras at a signal that mail a ticket to drivers who enter the intersection after the light has turned red.",
  cost=dict(text="SFMTA's 2018 contract to run 19 approaches at 13 intersections was capped at $5M for up to 3.75 years, about $263,000 an approach over the term (about $70,000 a year) [inference — mine]; Vision Zero's top band is $250,000 or more (national data)", short="About $70K an approach a year",
            value_low=70000, value_high=263000, unit="per enforced approach (low: a year; high: the whole contract term) [inference — mine]",
            source_url=RLC_2018, source_title="SFMTA Board Resolution 180821-112, 2018-08-21, Contract SFMTA-2016-49 with American Traffic Solutions, not to exceed $5,000,000, 1 year 9 months plus up to 2 years [primary — read 2026-10-23]; " + VZ_TAB + " ($$$$)"),
  effect=dict(text="For injury crashes, 15.7% fewer right-angle but 24.0% more rear-end at camera sites (25% fewer and 15% more for all crashes), with a net crash-cost benefit (FHWA, 132 sites, empirical Bayes). IIHS: 14% fewer fatal crashes at signals citywide in large cities with cameras", short="-16% right-angle, +24% rear-end injury crashes", pct=-16,
              outcome="injury crashes", design="before-after", where="FHWA",
              source_url=FHWA_RLC, source_title="FHWA-HRT-05-048, Council et al. 2005, Safety Evaluation of Red-Light Cameras, Executive Summary [primary — read 2026-10-23]; Hu and Cicchino 2017, IIHS bibliography ref 2121 [primary — read 2026-10-23, abstract]"),
  opposition=dict(grade="Low",
    reason="SF has run cameras since 1996 and is adding six, with no reported fight; SFMTA's own rule makes cameras the last resort at an intersection.",
    examples=[{"text": "Six new cameras under construction, activation expected Summer 2026 (Street Safety Initiative, Action 8)", "url": SSI},
              {"text": "10,385 red light camera citations in 2025 (DataSF uzmr-g2uc, repo note)", "url": "https://data.sfgov.org/d/uzmr-g2uc"}]),
  programs=P(mta=("in", REDLIGHT, "Red Light Camera program since 1996: 19 approaches at 13 intersections; Vision Zero tool table p. 26 ($$$$, ++) and action pp. 32-33 'Expand red light camera program with eight new locations'"),
             ssi=("in", SSI, "Action 8: 'The red light camera program is expanding, with 6 in construction and on track to be completed in Summer 2026'; Street Safety Act 1(c)")),
  limits=[{"text": "\"The SFMTA tries to implement all other traffic safety measures first before considering a red light camera installation at an intersection.\"", "url": REDLIGHT}],
  sf_example=dict(name="Fell Street at Masonic Avenue (westbound approach; northbound Masonic approach under construction)", year=2019,
                  lat=37.772995, lon=-122.445902, geometry_hint="point: Fell St and Masonic Ave (DataSF 3psu-pn9h node 26347000)",
                  source_url=REDLIGHT),
  by_user=U(
    ("Fewer drivers run the red into a crosswalk.", "Works only at 13 of about 1,300 signals.", FHWA_RLC, "FHWA: right-angle injury crashes 15.7% fewer. The study does not report a pedestrian figure."),
    ("Same as walking for crossing traffic.", "None measured.", None, "[inference — mine]"),
    ("Fewer side-impact crashes in bus paths.", "More rear-end crashes for vehicles that stop short.", FHWA_RLC, "FHWA: total rear-end crashes 14.9% more."),
    ("Fewer right-angle crashes.", "Tickets, and 15% more rear-end crashes.", FHWA_RLC, "FHWA found a net crash-cost benefit of $39,000 to $50,000 a site a year."),
    ("None measured.", "Sites are picked by crash totals, not by school.", REDLIGHT, "SFMTA: 'priority going to the intersections in San Francisco with the highest collision totals'."))),
# ---- from research-D.md
dict(
  id="crossing-guards", name="School crossing guards", short_name="Crossing guards", group="programs",
  one_line="Paid adult guards who walk children across a busy corner near school at arrival and dismissal.",
  cost=dict(text="SFMTA's roughly $4M program paid for 155 guards at 91 schools, about $44,000 a school a year, $26,000 a guard, or about $56 a coverage hour over 180 school days [inference — mine]", short="$44K a school a year",
            value_low=25800, value_high=44000, unit="per guard a year (low) or per school a year (high) [inference — mine]",
            source_url=GUARDS, source_title="SFMTA blog, Prioritizing Safety at Schools Citywide: An Update on Our Crossing Guard Program, 2025 [primary — read 2026-10-23]; 180 school days assumed [inference — mine]"),
  effect=dict(text="No change in pedestrian crashes where Toronto added 58 guards (rate ratio 1.02), while more children walked; most child crashes happened away from guards or outside school hours", short="No crash change; more walking", pct=None,
              outcome="pedestrian crashes", design="before-after", where="Toronto",
              source_url=ROTHMAN, source_title="Rothman et al., BMC Public Health 2015;15:732, quasi-experimental pre-post, IRR 1.02 (95% CI 0.74 to 1.39) [primary — read 2026-10-23, abstract]"),
  opposition=dict(grade="Low",
    reason="Everyone wants more guards; the fight is over staffing and money, not the guards.",
    examples=[{"text": "SFMTA: 'Crossing guards are beloved by students, parents, caregivers and neighbors'", "url": GUARDS},
              {"text": "21 schools were missing a guard; SFMTA missed its end-of-2025 hiring goal (KALW, 2026-01-06) [secondary — verify]", "url": KALW_GUARDS}]),
  programs=P(ssc=("in", SSC, "School Crossing Guard Program is one of the school programs the draft coordinates"),
             srts=("in", SRTS, "Section X: the Crossing Guard Program is one of the SFMTA teams working with schools"),
             mta=("in", GUARD_PAGE, "174 guards on duty at 98 public and private schools, about 400 hours of coverage a day")),
  limits=[{"text": "\"The School Crossing Guard Program is not accepting requests for evaluations for new school crossing guard locations at this time due to limited staffing capacity.\"", "url": GUARD_PAGE}],
  sf_example=dict(name="John Yehall Chin Elementary, 350 Broadway (KALW photo of a guard stationed near the school)", year=2026,
                  lat=37.798310, lon=-122.403175, geometry_hint="point: school address from DataSF Schools 7e7j-59qk; the guard's exact corner is not stated",
                  source_url=KALW_GUARDS),
  by_user=U(
    ("An adult stops traffic at the busiest corner at the bell.", "Only at bell times and only at one corner.", ROTHMAN, "Toronto: no change in crashes at guard sites. 62% of child pedestrian crashes were outside school travel times."),
    ("None measured.", "None measured.", None, None),
    ("None measured.", "None measured.", None, None),
    ("A clear signal of when to stop.", "Short waits at bell times.", None, "[inference — mine]"),
    ("Parents let children walk when a guard is on the corner.", "98 schools have one; new requests are closed.", GUARD_PAGE, "Rothman et al. call guards a way 'to increase walking to school'."))),
# ---- from research-D.md
dict(
  id="fleet-safety", name="Truck side guards and city fleet rules", short_name="Fleet safety", group="programs",
  one_line="Rails along the side of a truck that keep a person who is hit from going under the rear wheels, plus driver training and telematics on city vehicles.",
  cost=dict(text="About $1,800 a truck in Boston; US DOT estimated about $900 (non-SF; no SF cost found)", short="About $900-$1,800 a truck",
            value_low=900, value_high=1800, unit="per truck",
            source_url=SB_TRUCKS, source_title="Streetsblog, How American Cities Can Protect Cyclists From Deadly Trucks, 2016-10-26 [secondary — verify]"),
  effect=dict(text="After the UK required side guards, cyclist deaths in side-impact crashes with trucks fell 61% and pedestrian deaths 20%", short="-61% cyclist, -20% pedestrian side-impact deaths", pct=-20,
              outcome="deaths", design="before-after", where="UK",
              source_url=FMCSA_SG, source_title="FMCSA/Volpe, Study of Truck Side Guards to Reduce Pedestrian Fatalities, TRID record 1497971 [primary — read 2026-10-23]; the underlying UK study was not opened [unretrieved — verify]"),
  opposition=dict(grade="Untested",
    reason="Untested in SF: no side guard mandate was found; driver training for city truck drivers began in 2015 without a reported fight.",
    examples=[{"text": "SF requires city-employed truck and bus drivers to take a large-vehicle safety course (Vision Zero Network) [secondary — verify]", "url": VZN_LARGE},
              {"text": "Volpe's 2016 side guard assessment for SFMTA", "url": VOLPE_SF}]),
  programs=P(mta=("considered", VZ, "Vision Zero pp. 40-41, Safe Vehicles: 'Explore additional collision avoidance technologies for MTA city fleet once next vehicle procurement cycle begins' (SFMTA, 2024); annual public report on city fleet driving behaviour (City Admin)"),
             ssi=("considered", SSI, "Action 21: 'The City Administrator's office is updating vehicle driver training for city employees and focusing on consistent telematics installation on city vehicles'")),
  limits=[],
  sf_example=None,
  nearest_example=dict(city="Boston", name="2014 ordinance: side guards on city-owned and city-contracted trucks", url=VZN_LARGE),
  by_user=U(
    ("A person hit from the side is less likely to go under the wheels.", "Does not prevent the crash.", FMCSA_SG, "UK: pedestrian side-impact deaths 20% fewer."),
    ("The biggest gain: cyclists are most often hit by a truck's side.", "Covers only fitted trucks.", FMCSA_SG, "UK: cyclist side-impact deaths 61% fewer."),
    ("None measured.", "None measured.", None, None),
    ("None measured.", "Fitting cost per truck.", SB_TRUCKS, "US DOT says guards can be cost-neutral through fuel economy if designed well [secondary — verify]."),
    ("None measured.", "None measured.", None, None))),
# ---- from research-D.md
dict(
  id="traffic-enforcement", name="Police traffic enforcement", short_name="Police enforcement", group="programs",
  one_line="Officers stop and ticket drivers for the moves that most often kill or maim, aimed at the High Injury Network.",
  cost=dict(text="No SF cost per officer or per operation found; Oregon's trooper layoffs imply about $309,000 of state police spending per highway death prevented (non-SF)", short="No SF cost found",
            value_low=None, value_high=None, unit=None,
            source_url=ENF_NOTE, source_title="DeAngelo and Hansen 2014, AEJ: Economic Policy 6(2):231, abstract [primary — read 2026-10-22, repo note]"),
  effect=dict(text="More patrol cuts fatal crashes about 18% but injury crashes only about 2% (meta-analysis of seven studies); effects fade within days once patrols leave", short="-18% deaths, -2% injury crashes", pct=-18,
              outcome="deaths", design="meta-analysis", where="TØI handbook (mostly US studies)",
              source_url=TOI_PATROL, source_title="Elvik and Høye, TØI Handbook of Road Safety Measures 8.4, revised 2020 [primary — read 2026-10-22, machine translated, repo note]; Fliss et al. 2020, Fayetteville [primary — read 2026-10-22, repo note]"),
  opposition=dict(grade="Medium",
    reason="Wanted by the Board and the Grand Jury, but city plans limit it over racial disparities in stops, and SFPD restricted pretext stops in 2024.",
    examples=[{"text": "Citations fell from 127,861 in 2014 to 4,006 in 2022, then rose to 20,393 in 2025 (SFPD reports, repo note)", "url": SFPD_TVR},
              {"text": "Street Safety Act 2(a)-(c): plan to increase enforcement, monthly HVE, citation statistics", "url": SSA}]),
  programs=P(mta=("in", VZ, "Vision Zero pp. 38-39: 'Issue 50% of traffic citations for top five causes of collisions (Focus on the Five)' and monthly HVE on the HIN (SFPD); p. 42 metric 'At least 50% of traffic citations'"),
             ssi=("in", SSI, "Action 9: 'SFPD has implemented monthly High Visibility Enforcement operations focused on High Injury Network corridors'; Action 20 Traffic Enforcement Strategy; Action 27 enforcement plan scheduled for 2027")),
  limits=[{"text": "\"Safety projects and programs should not exacerbate existing inequities, including through interactions with law enforcement and issues of racial profiling.\" (Vision Zero SF Action Strategy, p. 10)", "url": VZ},
          {"text": "\"People of color are disproportionately stopped for traffic stops in SF. Vision Zero SF is working to identify alternatives to and reduce harm from enforcement.\" (p. 12)", "url": VZ}],
  sf_example=dict(name="Cabrillo Street and Funston Avenue, the city's top spot for traffic citations in 2025 (958 people cited, 936 for unsafe speed)", year=2025,
                  lat=37.775028, lon=-122.471373, geometry_hint="point: Cabrillo St and Funston Ave (DataSF 3psu-pn9h node 27268000)",
                  source_url=RIPA),
  by_user=U(
    ("Drivers who fail to yield can be cited anywhere, not only at 33 camera sites.", "Effect fades within days of patrols leaving.", TOI_PATROL, "TØI 8.1: police speed checks cut killed-or-seriously-injured crashes 12%."),
    ("Same reach as for walking.", "None measured.", None, "[inference — mine]"),
    ("None measured.", "None measured.", None, None),
    ("Covers drunk driving, red lights and failure to yield.", "Stops fall unevenly: Black people were 14.8% to 18.9% of people stopped, 2019 to 2026.", RIPA, "RIPA stop data, repo note [DataSF ubqf-aqzw — queried 2026-10-22]."),
    ("Speed checks near schools are possible.", "No school-zone enforcement figure found.", None, "[inference — mine]"))),
# ---- from research-E.md
dict(
  id="lane-removal", name="Removing a car lane", group="spot",
  one_line="A four-lane street becomes three (one lane each way plus a turn lane), or a wider street loses a lane to a bike lane, buffer or parking, mostly with paint.",
  cost=dict(text="$200,000 for Golden Gate Avenue, Polk to Market (three lanes to two plus a buffered bike lane, 0.47 miles), about $425,000 a mile; 14th Street's lane removal, Castro to Sanchez, was $60,700 to build over 0.24 miles", short="$0.25M-$0.43M a mile",
            value_low=250000, value_high=425000, unit="per mile (paint)",
            source_url=GG_ARF, source_title="SFCTA Prop K allocation request, Golden Gate Avenue Buffered Bike Lane, pp. 1 and 3; SFCTA Board memo Sept 2021 (14th Street Road Diet, $60,700 construction); lengths from DataSF 3psu-pn9h [primary — read 2026-10-23]; per mile [inference — mine]"),
  effect=dict(text="19% to 47% fewer crashes, converting four lanes to three; NYC's 28 road diets cut killed-or-seriously-injured 30%", short="-19% to -47% crashes", pct=-19,
              outcome="crashes", design="before-after", where="FHWA",
              source_url=WB + "road-diets-roadway-reconfiguration", source_title="FHWA Proven Safety Countermeasures, Road Diets, Wayback snapshot [primary — read 2026-10-22]; removed from FHWA's list in 2026 without a safety reason. NYC DOT Safety Treatment Evaluation 2005-2018, p. 2 [primary — read 2026-10-23]"),
  opposition=dict(grade="Medium",
    reason="Projects are fought one street at a time, and the Mayor's directive limits quick-builds to places 'where data shows they are necessary'.",
    examples=[{"text": "Executive Directive 25-06, Action 6: quick-builds 'in areas where data shows they are necessary'; principle: 'Safer streets are not anti-driving streets'", "url": MAYOR_ED},
              {"text": "Civil Grand Jury: open-ended outreach causes 'wild swings on high profile projects' (p. 28)", "url": CGJ}]),
  programs=P(mta=("pilot", SB_DIETS, "Done street by street: 34 road diets from 1973 to 2010 on an SFMTA list (about 20 miles, our measurement), and a handful since, such as California Street in 2020 and 14th Street in 2022"),
             ssi=("considered", SSI, "Action 6 names a priority quick-build list; 8 projects 'through approval process' in the Jan 2026 deck. No source names lane removal")),
  sf_example=dict(name="California Street, Arguello Boulevard to Park Presidio Boulevard, 'reconfigured from four lanes to three'", year=2020,
                  lat=37.785066, lon=-122.465883, geometry_hint="lat/lon is the straight-line midpoint; street segment: California St, Arguello Blvd (37.785682,-122.459179) to Park Presidio Blvd (37.784449,-122.472586)",
                  source_url=CAL_SAFETY),
  by_user=U(
    ("Fewer lanes to cross and slower cars.", "Paint doesn't widen the sidewalk.", NYC_STE, "NYC DOT, 28 road diets: pedestrian injuries -12.5%, pedestrians killed or seriously injured -31.7% (before-after, no comparison group)."),
    ("Room for a bike lane or buffer.", "Only if the freed space goes to bikes.", GG_ARF, "Golden Gate Avenue's lane went to an eastbound buffered bike lane."),
    ("Fewer lane changes in front of buses.", "Buses can slow behind a single lane of cars.", None, "[inference — mine]"),
    ("Fewer crashes and less weaving.", "Slower peak trips on that street.", WB + "road-diets-roadway-reconfiguration", "FHWA: 19% to 47% fewer total crashes, four lanes to three. NYC: motor vehicle occupant injuries -19.3%."),
    ("Arterials near schools get calmer.", "Helps only on the street treated.", None, "[inference — mine]"))),
# ---- from research-F.md
dict(
  id="muni-frequency", name="More frequent Muni service", short_name="More frequent Muni", group="muni",
  one_line="Shorter waits on the bus lines through a neighborhood, so more trips go by Muni instead of by car.",
  cost=dict(text="About $16M to $18M a year per square mile to halve waits on every bus line (10 to 5 minutes): doubling Muni's 2.50M bus revenue hours at its FY2025 cost of $305 an hour [inference — mine]", short="$16M-$18M a year a sq mi",
            value_low=16200000, value_high=18200000, unit="per square mile a year",
            source_url="https://data.transportation.gov/d/ekg5-frzt", source_title="FTA National Transit Database, SFMTA (90015) FY2025 metrics: bus operating cost over revenue hours [primary — queried 2026-10-23]; arithmetic [inference — mine]"),
  effect=dict(text="Doubling bus service in a square mile adds about 0.6M to 1.7M trips a year. The 10% to 50% of new riders who leave a car remove that risk, but twice the buses means up to twice the crashes involving a Muni vehicle, 1.6% of SF's injury crashes. Net, the area's injuries change by 3.9% fewer to 1.3% more, about 0.7% fewer at the central case [inference — mine]", short="About -0.7% injuries (-3.9% to +1.3%)", pct=-0.7,
              outcome="all injuries", design="model", where="SF (model)",
              source_url="https://ww2.arb.ca.gov/sites/default/files/2020-06/Impacts_of_Transit_Service_Strategies_on_Passenger_Vehicle_Use_and_Greenhouse_Gas_Emissions_Technical_Background_Document.pdf",
              source_title="CARB / Handy et al. 2013, frequency elasticity +0.5 (cluster +0.3 to +1.0) and 10% to 50% of new rides from cars, from TCRP 95 [primary — read 2026-10-23]; Morency et al. 2018, Montreal, per passenger km car vs bus: occupants 3.7, pedestrians struck 4.1, cyclists 5.3 (https://pmc.ncbi.nlm.nih.gov/articles/PMC5906382/) [primary — read 2026-10-23]; DataSF 8gtc-pjc6 transit-vehicle parties [DataSF 8gtc-pjc6 — queried 2026-10-23]; NTD SFMTA FY2025 unlinked trips [primary — queried 2026-10-23]; SFMTA TDS 2019, p. 5, car and TNC trips [primary — read 2026-10-20, repo note]; arithmetic in muni_model.py [inference — mine]"),
  opposition=dict(grade="Medium",
    reason="Little organized opposition to service itself. The barrier is money: SFMTA says it cannot add service while it closes a $307M gap, and keeping today's service depends on two November 2026 measures.",
    examples=[{"text": "'Due to the SFMTA's budget gap, we cannot increase overall Muni service'; Aug 2026 changes are cost-neutral", "url": "https://www.sfmta.com/servicechanges"},
              {"text": "FY26-27 budget closes a $307M shortfall; if the measures fail, 'elimination of up to 20 Muni routes' (SFMTA, 2026-04-21)", "url": "https://www.sfmta.com/index%2Ephp/press-releases/press-release-facing-fiscal-cliff-sfmta-board-approves-balanced-two-year-budget-preserve-muni-service-and-keep-san-francisco-moving"},
              {"text": "April 2020: service cut to a 'Core Service Network' of Muni's 17 most-used lines, restored in stages to 2022", "url": "https://www.sfmta.com/project-updates/covid-19-related-service-changes"},
              {"text": "Prop H Muni parcel tax, about $160M a year, simple majority; SPUR says both it and Prop RTM must pass [secondary — verify]", "url": "https://www.spur.org/voter-guide/2026-11/sf-prop-h-muni-parcel-tax"}]),
  programs=P(ssc=("in", SSC, "'School Peak Service and School Tripper Service' is one of the Muni Support programs the draft coordinates (extra service at bell times, not a frequency program)"),
             mta=("pilot", "https://www.sfmta.com/servicechanges", "Frequency moves only within a fixed budget: Aug 2026 changes bring the 1 California to every 4 to 5 minutes from Presidio to downtown and the N Judah to 9 minutes at peak, cost-neutral")),
  sf_example=dict(name="1 California, every 4 to 5 minutes between Presidio Avenue and downtown (Aug 29, 2026 service change)", year=2026,
                  lat=37.787262, lon=-122.446793, geometry_hint="lat/lon is California St at Presidio Ave, where the 1 meets the stretch; route east to downtown terminal near Clay St at Drumm St (37.795466,-122.396772), via Sacramento/Clay per Muni Simple Routes",
                  source_url="https://www.sfmta.com/servicechanges"),
  by_user=U(
    ("Fewer cars if drivers switch.", "Each trip adds a walk to and from the stop; 44 pedestrians were hurt and 3 killed in crashes involving a transit vehicle in five years.", None, "SF police data, Sep 2021 to Aug 2026, my query [inference — mine]"),
    ("Fewer cars if drivers switch.", "More bus miles; 21 bicyclists were hurt in crashes involving a transit vehicle in five years.", None, "SF police data, my query [inference — mine]"),
    ("Shorter waits; out-of-vehicle time matters more to riders than in-vehicle time.", "On-board falls rise with ridership: NTD counts about 127 Muni riders hurt a year.", "https://ww2.arb.ca.gov/sites/default/files/2020-06/Impacts_of_Transit_Service_Strategies_on_Passenger_Vehicle_Use_and_Greenhouse_Gas_Emissions_Technical_Background_Document.pdf", "CARB: strategies that cut out-of-vehicle time 'seem to have more impact' (Evans 2004)."),
    ("Fewer cars if some drivers switch.", "More buses in the lane.", None, "[inference — mine]"),
    ("Shorter waits for the students who already ride.", "Citywide frequency reaches few students per dollar; bell-time trippers reach more.", None, "Our school-trips model: about 243 students out of cars for $174M a year [repo note, read 2026-10-23]"))),
# ---- from research-F.md
dict(
  id="transit-signal-priority", name="Transit signal priority", short_name="Signal priority for Muni", group="muni",
  one_line="Traffic signals that hold or bring up a green light for an approaching Muni bus or train, so it spends less time at red lights. Red transit-only lanes are their own row.",
  cost=dict(text="$2,500 to $40,000 an intersection for detection equipment (US, TCRP Synthesis 83, 2013, non-SF). SF's 2021 Prop K request of $1.35M covered repairs plus 5 to 20 new intersections, so it gives no clean unit cost", short="$2.5K-$40K an intersection (US)",
            value_low=2500, value_high=40000, unit="per intersection",
            source_url="https://www.itskrs.its.dot.gov/2013-sc00286", source_title="USDOT ITS JPO cost database, TCRP Synthesis 83, 2013, non-SF [primary — read 2026-10-23, Wayback copy]; SFCTA Prop K Grouped Allocations memo, Oct 2021, p. 4 [primary — read 2026-10-23]"),
  effect=dict(text="8% faster Muni trips on Lombard and Richardson after TSP (SFMTA). In Portland, all crashes fell 4.5% on TSP streets against a control, but fatal and injury crashes didn't change and pedestrian and bike crashes rose. Its ridership gain is small, and by the per-mile rule in the rows above it can add or remove injuries [inference — mine]", short="No clear injury effect", pct=None,
              outcome="crashes", design="controlled", where="Portland; SF travel time",
              source_url="https://arxiv.org/abs/1812.01788", source_title="Song and Noyce, Effects of Transit Signal Priority on Traffic Safety, Portland 1995-2010, interrupted time series with control (Accident Analysis & Prevention 2019; arXiv preprint) [primary — read 2026-10-23, abstract]; SFMTA TSP map, Jan 2023 [primary — read 2026-10-23]"),
  opposition=dict(grade="Low",
    reason="An equipment and timing change with no reported fight; SFMTA has installed it at about 450 intersections since 2012. No opposition record found.",
    examples=[{"text": "'TSP is implemented at about 450 intersections' (SFMTA Board workshop, 2023-02-07)", "url": "https://sfmta.com/media/34264/download"},
              {"text": "SFCTA Prop K allocation of $1,350,883 for bus TSP, Oct 2021", "url": "https://www.sfcta.org/sites/default/files/2021-10/Item%206%20-%20Grouped%20Allocations%20BD%20MEMO.pdf"}]),
  programs=P(mta=("in", MF, "Transit signal priority is in the Muni Forward Transit Priority Toolbox (Muni Forward Update, 2024-11-06, p. 5); about 450 intersections"),
             ssi=("considered", DECK, "Draft plan: 15 more miles of Muni Forward toolkit (Jan 2026 deck, p. 28)")),
  sf_example=dict(name="Lombard Street at Richardson Avenue, TSP added July 2022 (28 and 43 lines)", year=2022,
                  lat=37.798840, lon=-122.444828, geometry_hint="point; Lombard St at Richardson Ave from DataSF 3psu-pn9h; Lombard continues east past Divisadero (37.799000,-122.442648)",
                  source_url="https://sfmta.com/media/34264/download"),
  by_user=U(
    ("None measured.", "Pedestrian and bike-involved crashes rose after TSP in Portland.", "https://arxiv.org/abs/1812.01788", "Song and Noyce: 'Pedestrian and bike-involved crashes were found to increase in the post-intervention period with TSP'."),
    ("None measured.", "Pedestrian and bike-involved crashes rose after TSP in Portland.", "https://arxiv.org/abs/1812.01788", "Same study; not broken out for bikes alone in the abstract."),
    ("Faster, more reliable buses.", "None measured.", "https://sfmta.com/media/34264/download", "Lombard and Richardson, July 2022: travel times down 8%, variability down 16%."),
    ("Fewer property-damage crashes.", "Shorter greens on cross streets.", "https://arxiv.org/abs/1812.01788", "Portland: property-damage-only crashes down 10%. The cross-street effect is [inference — mine]."),
    ("Faster Muni for students who ride.", "None measured.", None, "[inference — mine]"))),
# ---- from research-F.md
dict(
  id="lower-fares", name="Lower or free fares", short_name="Lower fares", group="muni",
  one_line="Cheaper or free Muni rides, so cost doesn't push people into a car. San Francisco already lets everyone 18 and under ride free.",
  cost=dict(text="Free fares for everyone would give up about $2.3M a year per square mile ($110M of Muni fare revenue in FY2025). Free Muni for Youth cost an estimated $2.9M a year as a 2014 pilot and $6.8M if open to all youth, about $62K to $144K per square mile [inference — mine]", short="$2.3M a year a sq mi (all riders)",
            value_low=62000, value_high=2340000, unit="per square mile a year",
            source_url="https://data.transportation.gov/d/ekg5-frzt", source_title="NTD SFMTA (90015) FY2025 fare revenues earned, fixed route [primary — queried 2026-10-23]; Budget and Legislative Analyst, Free Muni for Youth policy analysis, 2014-02-18, pp. 2-3 [primary — read 2026-10-23]"),
  effect=dict(text="A 1% fare cut adds about 0.4% bus riders in the short run, so free fares add about 40%, close to the 41% rise in youth Clipper tags under SF's free youth fares, which showed 'no discernible change in the use of private vehicles to and from school' in the first months. Each new rider carries Muni's injury risk, about 26% of a car's a mile, so the area's injuries change by 2.0% fewer to 1.5% more as 50% to 10% of new riders leave cars, about 0.3% fewer at the central case, and SF's youth evidence points to the worse end [inference — mine]", short="About -0.3% injuries (-2.0% to +1.5%)", pct=-0.3,
              outcome="all injuries", design="model", where="SF (model)",
              source_url="https://sfbos.archive.sf.gov/sites/default/files/FileCenter/Documents/47980-BLA%20FMFY%20021814.pdf",
              source_title="Budget and Legislative Analyst, Free Muni for Youth policy analysis, 2014-02-18, pp. 4-5 [primary — read 2026-10-23]; CARB / Handy et al. 2013, bus fare elasticity -0.4 from TCRP 95 ch. 12 [primary — read 2026-10-23]; Morency et al. 2018, Montreal, per passenger km car vs bus: occupants 3.7, pedestrians struck 4.1, cyclists 5.3 (https://pmc.ncbi.nlm.nih.gov/articles/PMC5906382/) [primary — read 2026-10-23]; DataSF 8gtc-pjc6 transit-vehicle parties [DataSF 8gtc-pjc6 — queried 2026-10-23]; NTD SFMTA FY2025 unlinked trips [primary — queried 2026-10-23]; arithmetic in muni_model.py [inference — mine]"),
  opposition=dict(grade="Medium",
    reason="The cost falls on a Muni budget already short $307M a year. The FY26-27 budget raised some fares while adding a daily cap.",
    examples=[{"text": "FY26-27 budget 'eliminates the 15-cent Clipper card discount' and raises the cable car fare from $9 to $12, while 'after a customer pays for two Muni rides on the same day, any additional rides are free' (SFMTA, 2026-04-21)", "url": "https://www.sfmta.com/index%2Ephp/press-releases/press-release-facing-fiscal-cliff-sfmta-board-approves-balanced-two-year-budget-preserve-muni-service-and-keep-san-francisco-moving"},
              {"text": "Free Muni for all youth from 2021-08-15, with $2 million from the City budget", "url": "https://www.sfmta.com/blog/young-people-ride-muni-free"},
              {"text": "Controller: forgone fare revenue from all Free Muni programs 'approximately $13.3 million' (2022)", "url": "https://www.sf.gov/sites/default/files/2023-03/SFMTA%20Free%20Fare%20Audit%20Memo%2003.30.23.pdf"}]),
  programs=P(ssc=("in", SSC, "'Free Muni for Youth' is one of the Muni Support programs the draft coordinates"),
             srts=("in", SRTS, "'Free Muni for All Youth Outreach spreads the word about the program so youth ages 18 and under know they can ride for free'"),
             mta=("in", "https://www.sfmta.com/fares/free-muni-all-youth-18-years-and-younger", "Free Muni for all youth 18 and under, citywide, no application; free fares for adults are not in place")),
  sf_example=dict(name="Free Muni for All Youth, citywide, every rider 18 and under from August 15, 2021", year=2021,
                  lat=None, lon=None, geometry_hint="citywide; no single place",
                  source_url="https://www.sfmta.com/blog/young-people-ride-muni-free"),
  by_user=U(
    ("Fewer cars if drivers switch.", "In Tallinn, new riders came mostly from walking [secondary — verify].", "https://www.weforum.org/agenda/2018/06/estonia-is-making-public-transport-free", "Not opened; from search results only [web search — verify]."),
    ("None measured.", "None measured.", None, "[inference — mine]"),
    ("Free or cheaper rides.", "More crowding on full lines; on-board injuries rise with riders.", None, "[inference — mine]"),
    ("Fewer cars if some drivers switch.", "None measured.", None, "[inference — mine]"),
    ("Youth ride free today; youth Clipper tags rose 41.1% in May 2013 against May 2012.", "No discernible change in private-vehicle trips to school in the first three months.", "https://sfbos.archive.sf.gov/sites/default/files/FileCenter/Documents/47980-BLA%20FMFY%20021814.pdf", "BLA 2014, pp. 4-5; SFUSD survey of high-school students."))),
# ---- from research-G.md
dict(
  id="bike-slow-streets", name="Bike priority slow streets (Fahrradstraße, fietsstraat)", short_name="Bike priority slow streets", group="network",
  one_line="A residential street where bikes have legal priority and diverters stop through traffic. Germany's Fahrradstraße lets cars in only where a sign allows, at 30 km/h, and riders may go side by side; in a Dutch-language fietsstraat cars are guests ('auto te gast'), and Belgian law bars them from passing cyclists. SF's Slow Streets, Page Street among them, are a partial version: diverters on some, and no legal bike priority on any.",
  cost=dict(text="$200,000 a mile for a Slow Street, mostly signs, posts and calming (SFMTA Board, 2022-12-06, p. 13); about $0.8M a mile on Page Street, dividing CIP ST071's $1,405,000 by 1.74 miles [inference — mine]. A diverter alone: $22,790 median in US data (PBIC 2013, non-SF)", short="$0.2M-$0.8M a mile",
            value_low=200000, value_high=807000, unit="per mile",
            source_url=SLOW_SR, source_title="SFMTA Board staff report 2022-12-06, PDF p. 13 [primary — read 2026-10-23]; CIP ST071 total $1,405,000 (" + PAGE_CIP + ") [primary — read 2026-10-23]; PBIC Costs for Pedestrian and Bicyclist Infrastructure Improvements, 2013, Table 5, PDF p. 16 [primary — read 2026-10-23, non-SF]"),
  effect=dict(text="We found no injury study of Fahrradstraßen. SF's partial version: 48% fewer reported collisions of all severities per mile on Slow Streets after designation, against 14% fewer citywide, so about 40% net of the trend", short="-40% collisions net of trend (SF Slow Streets)", pct=-40,
              outcome="collisions, all severities", design="before-after with citywide comparison", where="SF Slow Streets",
              source_url=SLOW_EVAL, source_title="SFMTA 2023 Slow Streets Evaluation, PDF pp. 7, 17 (monthly collisions per mile, 2017-2020 vs 2022, all modes) [primary — read 2026-10-23]"),
  opposition=dict(grade="Medium",
    reason="Staff kept 15 of 31 pandemic Slow Streets and the Board kept 16; SFMTA paused the Noe Street diverter for lack of consensus, and Lake Street's diverters stalled the same way.",
    examples=[{"text": "Staff recommended 15 of 31 pandemic Slow Streets; materials on the rest 'will be removed in the Winter 2023' (Dec 2022)", "url": SLOW_SR},
              {"text": "Board added Lake Street and struck the rule that every diversion citywide needs Board approval (minutes, 2022-12-06)", "url": SLOW_MIN},
              {"text": "Noe and 15th diverter paused: 'We don't yet have consensus' (SFMTA to Streetsblog, Aug 2024) [secondary — verify]", "url": NOE_SB},
              {"text": "Cayuga diverter at Geneva cut traffic from about 2,100 to 1,200 cars a day (SFMTA, 2024)", "url": SLOW_S24}]),
  programs=P(ssc=("in", SSC, "All Ages and Abilities Network includes Slow Streets; the physical toolkit lists traffic diverters"),
             mta=("in", SLOW, "Slow Streets Program (Transportation Code §207): 19 corridors; treatments listed include turn restrictions and traffic diverters"),
             ssi=("considered", DECK, "Street Safety Commitments draft plan, Jan 2026: 'Upgrades to 3 of the 19 to meet speed/volume standards'")),
  sf_example=dict(name="Page Street at Webster Street, a partial version only: turn restrictions and a diverter by John Muir Elementary, but no legal bike priority and few diverters, so through traffic still uses most of it", year=2020,
                  lat=37.773248, lon=-122.428990, geometry_hint="point (CNN node 25901000, Page St at Webster St); corridor Stanyan St (37.770098, -122.453726, node 26440000) to Octavia Blvd (37.773889, -122.423947, node 25909000)",
                  source_url=PAGE),
  by_user=U(
    ("Fewer cars; collisions per mile fell 48% on Slow Streets.", "Only 3 of 16 met both SFMTA targets in 2023.", SLOW_EVAL, "2023 evaluation, PDF pp. 17-18 [primary — read 2026-10-23]."),
    ("A low-traffic route with no lane to build; local streets signed as bike routes carried about half the injury risk of busy streets.", "The street stays shared; on 12 of 16 the median speed was over 15 mph in 2023.", TESCHKE, "Teschke et al. 2012, local street designated bike route, adjusted OR 0.49 (0.26-0.90) against major streets with parked cars. With traffic calming including diverters, OR 0.66 (0.35-1.26), not significant [primary — read 2026-10-23]."),
    ("None measured.", "Muni routes can't run on them.", SLOW, "SFMTA: 'MUNI routes and emergency response corridors do not work as Slow Streets' [primary — read 2026-10-23]."),
    ("Every address stays reachable.", "Through trips turn off at the diverter; a minority drive around soft ones.", PAGE, "Page item, Jan 2023, PDF p. 12: 'a minority of people illegally drive around the traffic diverters' [primary — read 2026-10-23]."),
    ("SFMTA put the Webster diverter by John Muir Elementary to keep traffic low there.", "None measured.", PAGE, "Page item, PDF p. 7: restrictions 'intended to maintain low vehicle volumes on Page Street near John Muir Elementary School to improve traffic safety for students' [primary — read 2026-10-23]."))),
]
