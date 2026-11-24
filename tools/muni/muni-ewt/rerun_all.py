"""Rebuild the Muni excess-wait months on the VM, rebuilding only what changed.

For every month from 2022-01 to the newest one pull_all.py has finished (and the 2019-09 baseline), a month is rebuilt when its hourly/<m>.parquet is
missing or its stamp (hourly/<m>.stamp) no longer matches: the SHA-256 of ewt_month.py (ewt_2019.py for 2019-09),
plus, for a stand-in month, of make_sched.py and the name of the SFMTA GTFS capture it uses, plus the size and
modification time of the month's stop_observations.csv.gz. So editing a script reruns every month it touches, and a
rerun with nothing changed rebuilds nothing. Stand-in schedules (make_sched.py) are rebuilt the same way, keyed on
make_sched.py's hash and the capture name (SCHEDULE_STAMP in the extract directory). Then trip_time.py (speed and
excess trip time; trip_time_2019.py for 2019-09) reruns for a month when its own hash or the month's excess-wait
stamp changed (seg/<m>.stamp), with 511's 2023-01 timetable for stop positions and 2022-07's (2022-01's for 2019)
for timepoint flags where a month lacks them. Three months run at a time.
Scripts are read from this file's directory; data live under the root (default ~/muni-511: history/, pylib/).
Usage (on the VM): nice -n 10 python3 rerun_all.py <ewt dir name, e.g. ewt> [root]
"""
import os, sys, glob, hashlib, subprocess, time
from concurrent.futures import ThreadPoolExecutor
S = os.path.dirname(os.path.abspath(__file__))
H = os.path.expanduser(sys.argv[2] if len(sys.argv) > 2 else "~/muni-511")
env = dict(os.environ, PYTHONPATH=os.path.join(H, "pylib"), PYTHONHASHSEED="0")
out = os.path.join(H, sys.argv[1]); os.makedirs(out + "/hourly", exist_ok=True)
sha = lambda *ps: hashlib.sha256(b"".join(open(p, "rb").read() for p in ps)).hexdigest()[:16]
# every month from 2022-01 through the newest one pull_all.py has finished (history/regional-<m>-so-sf/DONE)
done = sorted(os.path.basename(os.path.dirname(p))[9:16] for p in glob.glob(f"{H}/history/regional-20??-??-so-sf/DONE"))
last = done[-1] if done else "2026-10"
ms = ["%04d-%02d" % (y, m) for y in range(2022, int(last[:4]) + 1) for m in range(1, 13) if "%04d-%02d" % (y, m) <= last]
src = lambda m: f"{H}/history/regional-{m}-so-sf"

def standin(m):
    f = src(m) + "/SCHEDULE_SOURCE"
    return open(f).read().strip() if os.path.exists(f) else None
for m in ms:
    z = standin(m)
    if not z: continue
    stamp = sha(f"{S}/make_sched.py") + " " + z
    sf = src(m) + "/SCHEDULE_STAMP"
    if os.path.exists(sf) and open(sf).read().strip() == stamp: continue
    r = subprocess.run([sys.executable, f"{S}/make_sched.py", os.path.expanduser("~/faster-muni-hist/zips/" + z), m, src(m)], capture_output=True, text=True)
    print(m, "make_sched rc", r.returncode, (r.stdout + r.stderr)[-300:], flush=True)
    if r.returncode == 0: open(sf, "w").write(stamp + "\n")

FAILED = []
def stamp(m):
    if m == "2019-09": return sha(f"{S}/ewt_2019.py")
    o = src(m) + "/stop_observations.csv.gz"; st = os.stat(o)
    z = standin(m)
    return " ".join(x for x in (sha(f"{S}/ewt_month.py"), z and sha(f"{S}/make_sched.py"), z, f"{st.st_size}:{int(st.st_mtime)}") if x)
def run(m):
    p, sf = f"{out}/hourly/{m}.parquet", f"{out}/hourly/{m}.stamp"
    want = stamp(m)
    if os.path.exists(p) and os.path.exists(sf) and open(sf).read().strip() == want: return
    t0 = time.time()
    cmd = [sys.executable, f"{S}/ewt_2019.py", out] if m == "2019-09" else [sys.executable, f"{S}/ewt_month.py", src(m), out, m]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    print(time.strftime("%H:%M:%S"), m, "rc", r.returncode, round(time.time() - t0), "s", (r.stdout + r.stderr)[-400:] if r.returncode else "", flush=True)
    if r.returncode == 0: open(sf, "w").write(want + "\n")
    else: FAILED.append(f"{m} ewt_month")
REF, TABLES = src("2023-01"), f"{out}/ref"
def dist_stamp():
    xs = sorted(glob.glob(f"{H}/history/regional-20??-??-so-sf/stop_times.csv.gz"))
    return sha(f"{S}/dist_table.py") + " " + str(len(xs)) + " " + hashlib.sha256(" ".join(f"{x}:{os.stat(x).st_size}" for x in xs).encode()).hexdigest()[:12]
DSTAMP = dist_stamp()
if not (os.path.exists(f"{TABLES}/stop_pairs.parquet") and os.path.exists(f"{TABLES}/stamp") and open(f"{TABLES}/stamp").read().strip() == DSTAMP):
    r = subprocess.run([sys.executable, f"{S}/dist_table.py", f"{H}/history", TABLES], capture_output=True, text=True, env=env)
    print(time.strftime("%H:%M:%S"), "dist_table rc", r.returncode, (r.stdout + r.stderr)[-400:], flush=True)
    if r.returncode: sys.exit(1)
    open(f"{TABLES}/stamp", "w").write(DSTAMP + "\n")
def run_trip(m):
    sf = f"{out}/seg/{m}.stamp"; os.makedirs(f"{out}/seg", exist_ok=True)
    s19 = m == "2019-09"
    if not os.path.exists(f"{out}/hourly/{m}.stamp"): return
    want = sha(f"{S}/trip_time_2019.py" if s19 else f"{S}/trip_time.py") + " " + DSTAMP + " " + open(f"{out}/hourly/{m}.stamp").read().strip()
    if os.path.exists(f"{out}/seg/{m}.parquet") and os.path.exists(sf) and open(sf).read().strip() == want: return
    t0 = time.time()
    cmd = ([sys.executable, f"{S}/trip_time_2019.py", out, "--ref", REF, "--tables", TABLES] if s19 else
           [sys.executable, f"{S}/trip_time.py", src(m), out, m, "--tables", TABLES])
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    print(time.strftime("%H:%M:%S"), m, "trip_time rc", r.returncode, round(time.time() - t0), "s", (r.stdout + r.stderr)[-400:] if r.returncode else "", flush=True)
    if r.returncode == 0: open(sf, "w").write(want + "\n")
    else: FAILED.append(f"{m} trip_time")
def both(m): run(m); run_trip(m)
with ThreadPoolExecutor(3) as ex: list(ex.map(both, ms))
run("2019-09"); run_trip("2019-09")
if FAILED:  # vm_local.sh then stops before copying anything, so the last good data/muni-ewt/ stays
    print("failed:", ", ".join(sorted(FAILED)), flush=True); sys.exit(1)
print("finished", flush=True)
