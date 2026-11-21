"""Fetch SFMTA's monthly share of scheduled Muni service hours delivered (DataSF kc49-udxn, measure 441) into data/muni-ewt/service_delivered.csv.

The Controller's scorecard dataset carries every month SFMTA has reported, from 2001, with the actual and the target
("target", 0.985 in earlier years, 0.99 from July 2025 to June 2026 and 0.985 again from July 2026). It also carries the
current fiscal year's months before their actuals are in, with the target alone: the target in force for the first
of those months goes to data/muni-ewt/service_delivered_target.json ({"target", "from"}), so the pages use the current
target, not the last reported month's (pre-send gate round 6, R6-1: SFMTA's page reads "Achieve 98.5% service delivery
in accordance with City Charter"). --update first asks DataSF's metadata for rowsUpdatedAt and
re-reads when it moved since the last good read, or when the local file no longer holds the months that read wrote (kept in data/pipeline-state/, gitignored). A read that fails is
retried after 5, 20 and 60 seconds (lib/fetch.py); one that still fails on a 5xx or a timeout keeps the last good
file, records socrata:kc49-udxn-441 failed in data/pipeline-state/sources.json and exits 0, so the builds run on the
last good file; any other read error, or a short read, exits 2 or 1.

Checks, before the file is replaced: at least 200 months; months unique; every actual between 0.2 and 1 (April to August 2020 ran 31% to 45%) and target between 0.5 and 1;
no month later than the dataset's own data_as_of; the row count no lower than the previous file's. A failure keeps
the old file and exits 1. Idempotent: rows sorted by month, no run date in the file.
Usage: python3 tools/muni/muni-ewt/fetch_service_delivered.py [--update]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, json, os, sys

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "data", "muni-ewt", "service_delivered.csv")
OUT_T = os.path.join(ROOT, "data", "muni-ewt", "service_delivered_target.json")
STATE = os.path.join(ROOT, "data", "pipeline-state", "muni-service-delivered.json")
API = "https://data.sf.gov"
MARKER = "socrata:kc49-udxn-441"
sys.path.insert(0, paths.LIB)
from lib import pipeline_state  # noqa: E402
from lib.fetch import read, upstream_failed  # noqa: E402
get = lambda url: json.loads(read(url, headers={"User-Agent": "sf-works"}, timeout=60))

state = json.load(open(STATE)) if os.path.exists(STATE) else {}
try:
    meta = get(f"{API}/api/views/kc49-udxn.json")
    marker = meta.get("rowsUpdatedAt")
except Exception as e:
    upstream_failed(MARKER, e, step="muni-service-delivered")
held = [l.split(",")[0] for l in open(OUT).read().splitlines()[1:]] if os.path.exists(OUT) else []
# the marker says nothing moved at the source, and the local copy still holds every month the last good read wrote
if "--update" in sys.argv and held and state.get("rowsUpdatedAt") == marker and state.get("months") == len(held) \
        and state.get("newest") == held[-1]:
    print("unchanged at source:", marker)
    pipeline_state.record(MARKER, "unchanged", version=marker)
    sys.exit(0)
try:
    rows = get(f"{API}/resource/kc49-udxn.json?$select=calendar_month,actual,target,data_as_of&$where=measure_code='441'&$order=calendar_month&$limit=5000")
except Exception as e:
    upstream_failed(MARKER, e, step="muni-service-delivered")

out, errors, ahead = {}, [], {}
for r in rows:
    if r.get("actual") in (None, "", "-9999"):
        if r.get("target"):
            ahead[r["calendar_month"][:7]] = float(r["target"])
        continue
    m = r["calendar_month"][:7]
    if m in out:
        errors.append(f"{m} twice")
    out[m] = (float(r["actual"]), float(r["target"]) if r.get("target") else None, r.get("data_as_of", "")[:10])
asof = max((v[2] for v in out.values()), default="")
for m, (a, t, _) in out.items():
    if not 0.2 <= a <= 1 or (t is not None and not 0.5 <= t <= 1):
        errors.append(f"{m}: actual {a} or target {t} out of range")
    if asof and m > asof[:7]:
        errors.append(f"{m} is after the dataset's data_as_of {asof}")
prev = sum(1 for _ in open(OUT)) - 1 if os.path.exists(OUT) else 0
if len(out) < 200 or len(out) < prev:
    errors.append(f"{len(out)} months, previous file had {prev}")
nxt = sorted(m for m in ahead if not out or m > max(out))
cur = {"target": ahead[nxt[0]], "from": nxt[0]} if nxt else None
if cur and not 0.5 <= cur["target"] <= 1:
    errors.append(f"current target {cur} out of range")
if errors:
    for e in errors:
        print("check failed:", e, file=sys.stderr)
    sys.exit(1)
text = "month,actual,target\n" + "".join(f"{m},{a},{'' if t is None else t}\n" for m, (a, t, _) in sorted(out.items()))
moved = not os.path.exists(OUT) or open(OUT).read() != text
if moved:
    open(OUT, "w").write(text)
    print("wrote", OUT, len(out), "months,", min(out), "to", max(out))
else:
    print("unchanged", OUT)
if cur:
    t_text = json.dumps(cur, sort_keys=True) + "\n"
    if not os.path.exists(OUT_T) or open(OUT_T).read() != t_text:
        open(OUT_T, "w").write(t_text)
        print("wrote", OUT_T, cur)
elif os.path.exists(OUT_T):
    # no month past the newest actual carries a target any more, so a kept file would show last year's target;
    #   site_data.py falls back to the newest year's own value (Codex review, 2026-11-19)
    os.remove(OUT_T)
    moved = True
    print("removed", OUT_T, "(no target listed past the newest actual)")
pipeline_state.record(MARKER, "changed" if moved else "unchanged", version=marker)
os.makedirs(os.path.dirname(STATE), exist_ok=True)
json.dump({"rowsUpdatedAt": marker, "months": len(out), "newest": max(out)}, open(STATE, "w"))
