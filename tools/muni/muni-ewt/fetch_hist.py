"""Download one month of 511's historic Regional GTFS with stop observations (historic=YYYY-MM-so) to ~/muni-511/history/.

Reads the token from ~/.511token and never prints it or the URL. One request per run. Usage: python3 fetch_hist.py 2026-10-so
"""
import os, sys, time, urllib.request, urllib.error
m = sys.argv[1]
tok = open(os.path.expanduser("~/.511token")).read().strip()
url = "https://api.511.org/transit/datafeeds?operator_id=RG&historic=%s&api_key=%s" % (m, tok)
out = os.path.expanduser("~/muni-511/history/regional-%s.zip" % m)
t0 = time.time()
try:
    with urllib.request.urlopen(url, timeout=1800) as r, open(out + ".part", "wb") as f:
        print("status", r.status, "type", r.headers.get("Content-Type"), "len", r.headers.get("Content-Length"), flush=True)
        n = 0
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b); n += len(b)
    os.rename(out + ".part", out)
    print("ok", m, n, "bytes", round(time.time() - t0), "s", flush=True)
except urllib.error.HTTPError as e:
    print("http", e.code, e.read()[:300].decode("utf-8", "replace"), flush=True)
