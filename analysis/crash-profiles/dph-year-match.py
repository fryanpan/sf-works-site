#!/usr/bin/env python3
"""Year-by-year match of police-reported severe injuries and deaths (DataSF nwes-mmgh) against SFDPH's published hospital counts (ZSFG trauma registry) and OME-verified deaths, 2015-2024, by mode where SFDPH gives it.

    python3 analysis/crash-profiles/dph-year-match.py      # writes out/crash-augment/profiles/dph-year-match.json

Standard library only. Reads out/crash-augment/tables/victims.csv (pipeline/crash-augment). SFDPH's figures are typed
in below from the documents named beside them, each opened and read on 2026-11-25; nothing is fetched at run time,
so a second run writes the same bytes.

WHAT IS COMPARED
  police severe   victims rows with victim_degree_of_injury "Severe Injury", by year of collision_datetime. Mode from
                  victim_role (Pedestrian, Bicyclist) and, for drivers and passengers, the body type of the vehicle
                  they were in or on. Fatal victims are counted separately.
  DPH police      SFDPH's own count of the same police severe injuries (Severe Injury Trends 2015-2022, Table 5). Our
                  count is checked against it: it is the published total this comparison has to reproduce.
  ZSFG severe     SFDPH's hospital count: every traffic injury admitted to ZSFG, critical (ISS over 15) included,
                  deaths left out, freeways, the Presidio and off-street rail included (same report, Table 3).
  OME deaths      Vision Zero traffic deaths, DataSF dau3-4s8f (OME records meeting the Vision Zero Fatality Protocol;
                  freeways left out), queried 2026-11-25.
  The ratio police / ZSFG is a ratio of two counts, not a linkage rate: some police severe injuries are not severe in
  the hospital record and some hospital patients have no police report. SFDPH's linkage (HIN 2022 methodology,
  Tables 3 and 6) is published only pooled over 2017-2021, so no year-by-year linked share exists to compare.
  SFDPH's police mode split appears to put motor-driven cycles with motorcycles before 2019 and with motor vehicle
  occupants from 2019 [inference — mine: our motorcycle plus motor-driven cycle count matches Table 5's motorcyclists
  in 2015-2018 and motorcycles alone match in 2019-2021], so motorcyclists, vehicle occupants and other are compared as
  one group ("everyone else").
  SFDPH counts e-scooter riders inside its hospital pedestrian category ("E-scooter injuries are presently included
  within the pedestrian category of injury surveillance", Severe Injury Trends 2015-2022, p. 16). Police code them as
  role Other (or a driver) on body type "Go-ped, ZIP Electric Scooter, Motorboard", so they sit in "everyone else".
  pedestrian_with_police_scooter_riders adds them to police pedestrians for a like-for-like pedestrian ratio.
  ZSFG severe includes freeways, the Presidio and off-street rail; police and OME exclude highways. So every ratio
  here is a lower bound on the police share of the same population, most for "everyone else".
  our_police_ksi_per_linked_total divides police KSI as the officer coded it by SFDPH's linked total after
  reclassification, in which 406 police severe injuries were downgraded and 973 police lesser injuries upgraded.

ZSFG figures for 2023 and 2024 were not found in any published SFDPH source (see MISSING); those years carry police
counts only.
"""

import collections
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VICTIMS = os.path.join(ROOT, "out", "crash-augment", "tables", "victims.csv")
OUT = os.path.join(ROOT, "out", "crash-augment", "profiles", "dph-year-match.json")
csv.field_size_limit(1 << 24)

YEARS = list(range(2015, 2025))
MODES = ("pedestrian", "bicyclist", "everyone else")

TRENDS_2015_2022 = ("SFDPH, San Francisco Severe Traffic Injury Trends: 2015-2022 (December 2024), "
                    "https://visionzerosf.org/wp-content/uploads/2024/12/Severe-Injury-Trends_2015-2022.pdf "
                    "[primary — read 2026-11-25]")
TRENDS_2011_2020 = ("SFDPH, Severe Injury Trends 2011-2020, Tables 1 and A, "
                    "https://media.api.sf.gov/documents/Severe-Injury-Trends_2011-2020_final_report.cleaned_GmPU6Ay.pdf "
                    "[primary — read 2026-11-25]; same 2015-2020 figures as the 2015-2022 report")
HIN_2022_METHOD = ("SFDPH and SFMTA, Vision Zero High Injury Network: 2022 Update, methodology, Tables 3, 4 and 6, "
                   "https://www.visionzerosf.org/wp-content/uploads/2023/03/2022_Vision_Zero_Network_Update_Methodology.pdf "
                   "[primary — read 2026-11-25]")
OME_DEATHS = "DataSF dau3-4s8f, Traffic Crashes Resulting in Fatality, https://data.sfgov.org/d/dau3-4s8f [DataSF dau3-4s8f — queried 2026-11-25]"

# Table 3, severe injuries by travel mode, hospital data: pedestrian, cyclist, motorcyclist, motor vehicle occupant,
# other/unknown, total. Critical injuries are included in these counts.
ZSFG_SEVERE = {
    2015: (187, 110, 110, 156, 15, 578),
    2016: (190, 114, 110, 142, 14, 570),
    2017: (178, 102, 99, 189, 6, 574),
    2018: (183, 116, 130, 160, 3, 592),
    2019: (186, 76, 111, 156, 4, 533),
    2020: (137, 115, 117, 137, 6, 512),
    2021: (151, 102, 162, 157, 5, 577),
    2022: (146, 89, 141, 151, 8, 535),
}
# Table 4, critical injuries (ISS over 15), a subset of ZSFG_SEVERE, total only.
ZSFG_CRITICAL = {2015: 109, 2016: 125, 2017: 110, 2018: 130, 2019: 114, 2020: 121, 2021: 136, 2022: 137}
# Table 5, severe injuries by travel mode, police data, same column order.
DPH_POLICE_SEVERE = {
    2015: (87, 51, 45, 47, 0, 230),
    2016: (118, 40, 56, 64, 0, 278),
    2017: (112, 46, 48, 53, 2, 261),
    2018: (110, 55, 45, 69, 4, 283),
    2019: (117, 53, 46, 77, 14, 307),
    2020: (92, 34, 35, 53, 12, 226),
    2021: (85, 49, 40, 77, 20, 271),
    2022: (93, 54, 28, 84, 23, 282),
}
# dau3-4s8f, people killed by collision_year and deceased: (pedestrian, bicyclist, everyone else, total).
OME = {
    2015: (20, 4, 7, 31), 2016: (15, 3, 11, 29), 2017: (14, 2, 4, 20), 2018: (15, 3, 5, 23), 2019: (17, 1, 11, 29),
    2020: (12, 2, 16, 30), 2021: (13, 2, 12, 27), 2022: (20, 1, 18, 39), 2023: (18, 0, 8, 26), 2024: (24, 3, 15, 42),
}
# HIN 2022 methodology, Table 6 (2017-2021 pooled, N=2,627 severe and fatal after linkage and reclassification).
HIN_2022_TABLE6 = {
    "zsfg_not_matched_to_police": 596, "matched": 1724, "police_not_matched_to_zsfg": 178, "ome_fatalities": 129,
    "total": 2627,
    "by_mode_total": {"cyclist": 169 + 239 + 44 + 10, "pedestrian": 120 + 675 + 47 + 71,
                      "vehicle": 306 + 766 + 73 + 43, "other": 1 + 44 + 14 + 5},
}
# Table 3 there: of 1,165 police severe injuries with a linked ZSFG record, 406 (34.8%) were not severe per ZSFG, and
# 973 police Other Visible or Complaint of Pain injuries were severe per ZSFG.
HIN_2022_RECLASS = {"police_severe_linked": 1165, "downgraded": 406, "upgraded_other_visible": 469,
                    "upgraded_complaint_of_pain": 504, "severe_after_reclassification": 1732}

MISSING = [
    {"what": "ZSFG severe injuries for 2023 and 2024",
     "looked_at": [
         "SFDPH Severe Injury Trends 2015-2022 (Dec 2024), the latest severe injury report found; it covers 2015-2022",
         "SFDPH Health Commission deck on the 2024 High Injury Network (2026-08-17), "
         "https://media.api.sf.gov/documents/PHD-PPT-High_Injury_Network_Health_Commission_v5_2026-08-17_FINAL.pdf: "
         "says severe and fatal injuries rose 10% and injuries fell 8% from the 2022 HIN to the 2024 HIN; its counts "
         "are in chart images with no extractable figures",
         "sf.gov 2024 High Injury Network page, https://www.sf.gov/2024-high-injury-network-hin-map: no counts",
         "DataSF enwt-3u8m (2024 HIN, 2020-2024 linked SFPD, ZSFG and ambulance data): corridors only, no counts",
         "DataSF 3z93-mft8 (Vision Zero Benchmarking): SWITRS injuries and fatalities, no severe-injury metric",
         "SFCTA Board 2024-07-23 item 15 presentation (SFDPH): ZSFG and SFPD severe through 2022 only",
     ]},
    {"what": "a year-by-year linked (police and ZSFG matched) KSI count",
     "looked_at": ["HIN 2022 methodology gives linkage pooled over 2017-2021 only (Tables 3-6)",
                   "Severe Injury Trends 2015-2022 says a 2020-2022 linkage was due in 2025; not found published"]},
]


def mode(role, body):
    if role == "Pedestrian":
        return "pedestrian"
    if role == "Bicyclist":
        return "bicyclist"
    return "everyone else"


SCOOTER_BODY = "Go-ped, ZIP Electric Scooter, Motorboard"


def police_counts():
    sev = collections.defaultdict(collections.Counter)
    fat = collections.defaultdict(collections.Counter)
    with open(VICTIMS, newline="") as f:
        for r in csv.DictReader(f):
            y = int(r["collision_datetime"][:4] or 0)
            if y not in YEARS:
                continue
            m = mode(r["victim_role"], r["vehicle_body_type_clean"])
            if r["victim_degree_of_injury"] == "Severe Injury":
                sev[y][m] += 1
                if m != "pedestrian" and r["vehicle_body_type_clean"] == SCOOTER_BODY:
                    sev[y]["scooter"] += 1
            elif r["victim_degree_of_injury"] == "Fatal Injury":
                fat[y][m] += 1
    return sev, fat


def group3(row):
    """(pedestrian, cyclist, motorcyclist, MV occupant, other, total) to {mode: n} with total."""
    d = {"pedestrian": row[0], "bicyclist": row[1], "everyone else": row[2] + row[3] + row[4]}
    d["total"] = row[5]
    return d


def ratio(a, b):
    return round(a / b, 3) if b else None


def main():
    sev, fat = police_counts()
    rows, repro = [], []
    for y in YEARS:
        ps = {m: sev[y][m] for m in MODES}
        ps["total"] = sum(sev[y][m] for m in MODES)
        scoot = sev[y]["scooter"]
        pf = {m: fat[y][m] for m in MODES}
        pf["total"] = sum(fat[y].values())
        row = {"year": y, "police_severe": ps, "police_severe_scooter_riders": scoot, "police_fatal": pf,
               "police_ksi": {k: ps[k] + pf[k] for k in ps}}
        if y in OME:
            o = OME[y]
            row["ome_deaths"] = {"pedestrian": o[0], "bicyclist": o[1], "everyone else": o[2], "total": o[3]}
        if y in ZSFG_SEVERE:
            z = group3(ZSFG_SEVERE[y])
            row["zsfg_severe"] = z
            row["zsfg_critical_total"] = ZSFG_CRITICAL[y]
            row["police_severe_per_zsfg_severe"] = {k: ratio(ps[k], z[k]) for k in z}
            row["police_severe_per_zsfg_severe"]["pedestrian_with_police_scooter_riders"] = ratio(
                ps["pedestrian"] + scoot, z["pedestrian"])
            dk = {k: z[k] + row["ome_deaths"][k] for k in z}
            row["dph_ksi_zsfg_plus_ome"] = dk
            row["police_ksi_per_dph_ksi"] = {k: ratio(row["police_ksi"][k], dk[k]) for k in dk}
            d = group3(DPH_POLICE_SEVERE[y])
            repro.append({"year": y, "ours": ps, "dph_table5": d,
                          "difference": {k: ps[k] - d[k] for k in d}})
        else:
            row["zsfg_severe"] = None
            row["police_severe_per_zsfg_severe"] = None
            row["dph_ksi_zsfg_plus_ome"] = None
            row["police_ksi_per_dph_ksi"] = None
        rows.append(row)

    def pooled(ys):
        p = {k: sum(r["police_severe"][k] for r in rows if r["year"] in ys) for k in MODES + ("total",)}
        z = {k: sum(r["zsfg_severe"][k] for r in rows if r["year"] in ys) for k in MODES + ("total",)}
        pk = {k: sum(r["police_ksi"][k] for r in rows if r["year"] in ys) for k in MODES + ("total",)}
        dk = {k: sum(r["dph_ksi_zsfg_plus_ome"][k] for r in rows if r["year"] in ys) for k in MODES + ("total",)}
        return {"years": [min(ys), max(ys)], "police_severe": p, "zsfg_severe": z,
                "police_severe_per_zsfg_severe": {k: ratio(p[k], z[k]) for k in p},
                "police_ksi": pk, "dph_ksi_zsfg_plus_ome": dk,
                "police_ksi_per_dph_ksi": {k: ratio(pk[k], dk[k]) for k in pk}}

    windows = [pooled(range(2015, 2020)), pooled(range(2017, 2020)), pooled(range(2020, 2023)),
               pooled(range(2017, 2022))]
    p1721 = windows[3]["police_ksi"]["total"]
    out = {
        "about": __doc__.split("\n")[0],
        "caveats": [
            "A ratio of two counts, not a linkage rate.",
            "ZSFG severe includes freeways, the Presidio and off-street rail; police and OME exclude highways, so each "
            "ratio understates the police share of the same population, most for 'everyone else'.",
            "SFDPH counts e-scooter riders as pedestrians; see pedestrian_with_police_scooter_riders.",
            "ZSFG severe leaves out deaths; dph_ksi_zsfg_plus_ome adds OME deaths to it.",
            "our_police_ksi_per_linked_total compares police KSI before reclassification with SFDPH's linked total after it.",
        ],
        "sources": {"zsfg_and_dph_police": TRENDS_2015_2022, "zsfg_earlier_edition": TRENDS_2011_2020,
                    "linkage": HIN_2022_METHOD, "deaths": OME_DEATHS},
        "inputs": {"victims": "out/crash-augment/tables/victims.csv (DataSF nwes-mmgh, crash-augment build)"},
        "reproduces_dph_police_table5": repro,
        "by_year": rows,
        "pooled": windows,
        "hin_2022_linkage_2017_2021": {
            "table6": HIN_2022_TABLE6, "table3_reclassification": HIN_2022_RECLASS,
            "our_police_ksi_2017_2021": p1721,
            "our_police_ksi_per_linked_total": ratio(p1721, HIN_2022_TABLE6["total"]),
        },
        "missing": MISSING,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, sort_keys=False, ensure_ascii=False)
        f.write("\n")
    for r in rows:
        z = r["police_severe_per_zsfg_severe"]
        print(r["year"], "police severe", r["police_severe"]["total"], "fatal", r["police_fatal"]["total"],
              "ZSFG", (r["zsfg_severe"] or {}).get("total"), "ratio", z and z["total"],
              "ped", z and z["pedestrian"], "bike", z and z["bicyclist"], "rest", z and z["everyone else"])
    print("2017-2021 police KSI", p1721, "of linked", HIN_2022_TABLE6["total"])


if __name__ == "__main__":
    main()
