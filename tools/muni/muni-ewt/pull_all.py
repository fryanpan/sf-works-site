"""Pull every month of 511 historic stop observations (YYYY-MM-so) from 2022-01 to 2026-10, extract Muni rows, delete each zip.

For each month, in order: skip it if history/regional-<m>-so-sf/DONE exists; else download the zip (unless already on
disk) with fetch_hist.py, run extract_sf.py on it in the background, and on success write DONE and delete the zip.
Rate limit: 511 allows 60 requests per rolling hour per token and the realtime archive (tools/muni/rt-archive/) uses 50,
so this script keeps its own request log (history/requests.log, one epoch second per line) and never makes more than
MAXH requests in any 3,600 s window, nor two within GAP seconds. HTTP 429 waits 30 minutes and retries; other failures retry twice, then
the month is logged as failed and the run moves on. At most two extractions run at once, and the downloader waits
while three zips are waiting on disk. Never prints the token or a URL (fetch_hist.py doesn't either).
Usage (on the VM, from ~/muni-511): nice -n 10 ionice -c3 python3 pull_all.py [2022-01 2026-10]
"""
import os, sys, time, subprocess, glob

H = os.path.expanduser("~/muni-511/history")
HERE = os.path.dirname(os.path.abspath(__file__))
REQLOG = os.path.join(H, "requests.log")
MAXH, GAP = 8, 190


def months(a, b):
    y, m = map(int, a.split("-")); y2, m2 = map(int, b.split("-"))
    while (y, m) <= (y2, m2):
        yield "%04d-%02d" % (y, m)
        m += 1
        if m == 13: y, m = y + 1, 1


def log(*a):
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), *a, flush=True)


def wait_for_slot():
    while True:
        now = time.time()
        ts = [float(x) for x in open(REQLOG).read().split()] if os.path.exists(REQLOG) else []
        recent = [t for t in ts if now - t < 3600]
        if len(recent) < MAXH and (not ts or now - max(ts) >= GAP):
            with open(REQLOG, "a") as f: f.write("%d\n" % now)
            return
        time.sleep(15)


running = {}  # month -> Popen


def reap(block=False):
    for m, p in list(running.items()):
        if block: p.wait()
        if p.poll() is None: continue
        del running[m]
        zp = os.path.join(H, "regional-%s-so.zip" % m); d = zp[:-4] + "-sf"
        ok = p.returncode == 0 and os.path.getsize(os.path.join(d, "stop_observations.csv.gz")) > 100
        if ok:
            open(os.path.join(d, "DONE"), "w").write(time.strftime("%Y-%m-%dT%H:%M:%S\n"))
            os.remove(zp); log(m, "extracted, zip deleted")
        else:
            log(m, "EXTRACT FAILED rc", p.returncode, "- zip kept")


def extract(m):
    zp = os.path.join(H, "regional-%s-so.zip" % m)
    lf = open(os.path.join(H, "extract-%s.log" % m), "w")
    running[m] = subprocess.Popen([sys.executable, os.path.join(HERE, "extract_sf.py"), zp], stdout=lf, stderr=subprocess.STDOUT)
    log(m, "extract started")


a, b = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("2022-01", "2026-10")
for m in months(a, b):
    d = os.path.join(H, "regional-%s-so-sf" % m); zp = os.path.join(H, "regional-%s-so.zip" % m)
    if os.path.exists(os.path.join(d, "DONE")): continue
    if not os.path.exists(zp):
        while len(running) >= 2 or len(glob.glob(os.path.join(H, "regional-*-so.zip"))) >= 3:
            reap(); time.sleep(10)
        for attempt in range(3):
            wait_for_slot()
            r = subprocess.run([sys.executable, os.path.join(HERE, "fetch_hist.py"), m + "-so"], capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip().splitlines()
            log(m, "fetch:", out[-1][:200] if out else "(no output)")
            if os.path.exists(zp): break
            if out and out[-1].startswith("http 429"):
                log("rate limited, waiting 30 min"); time.sleep(1800)
        if not os.path.exists(zp):
            log(m, "FETCH FAILED, moving on"); continue
    while len(running) >= 2:
        reap(); time.sleep(10)
    extract(m)
reap(block=True)
log("all done")
