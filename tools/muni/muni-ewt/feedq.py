"""Feed-quality markers per month from the diag JSON files."""
import json, glob, os, sys
d = sys.argv[1]
print("month src obs_rows ooo_drop% dedupe% outage_days(>=57bins) partial_outage_bins line_days_dropped stops_obs secform routes")
for f in sorted(glob.glob(f"{d}/*.json")):
    j = json.load(open(f))
    if "after_dedupe" not in j: continue
    od = sum(1 for x in j["outage_bins"] if x[3] >= 57); pb = sum(x[3] for x in j["outage_bins"] if x[3] < 57)
    ooo = 100 * (j["after_dedupe"] - j["after_out_of_order"]) / max(j["after_dedupe"], 1)
    dd = 100 * (j["after_first_stop_and_nulls"] - j["after_dedupe"]) / max(j["after_first_stop_and_nulls"], 1)
    print(j["month"], j.get("schedule_source", "")[:9], j["obs_rows"], f"{ooo:.2f}", f"{dd:.2f}", od, pb, len(j["line_days_dropped"]), j["stops_obs"], j.get("obs_time_seconds_form", "?"), len(j["routes"]))
