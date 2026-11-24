"""Extract Muni (agency SF) rows from a 511 historic -so zip into a small working set for DuckDB.

Writes, next to the zip, a directory <zip-stem>-sf/ holding:
  stop_observations.csv.gz  every row whose trip_id starts with 'SF:'
  stop_times.csv.gz, trips.csv.gz, calendar_dates.csv.gz, routes.csv  filtered to SF the same way
Streams each member once; memory stays small. A member absent from the zip is listed in <dir>/MISSING. Usage: python3 extract_sf.py <zip>
"""
import zipfile, gzip, io, os, sys
zp = sys.argv[1]
out = zp[:-4] + "-sf"; os.makedirs(out, exist_ok=True)
z = zipfile.ZipFile(zp)
names = set(z.namelist())
def filt(member, dest, test):
    n = k = 0
    if member not in names:  # some months' archives lack Muni schedule files; make_sched.py stands in
        open(os.path.join(out, "MISSING"), "a").write(member + "\n")
        print(member, "MISSING from archive", flush=True); return
    with z.open(member) as f, gzip.open(os.path.join(out, dest), "wt", compresslevel=3) as g:
        t = io.TextIOWrapper(f, "utf-8-sig")
        g.write(next(t))
        for line in t:
            n += 1
            if test(line): g.write(line); k += 1
    print(member, n, "->", k, flush=True)
sf = lambda l: l.startswith("SF:")
filt("stop_observations.txt", "stop_observations.csv.gz", sf)
filt("trips.txt", "trips.csv.gz", sf)          # route_id first column, 'SF:..'
filt("stop_times.txt", "stop_times.csv.gz", sf)  # trip_id first column
filt("calendar_dates.txt", "calendar_dates.csv.gz", sf)  # service_id = hashed trip id
filt("routes.txt", "routes.csv.gz", sf)
