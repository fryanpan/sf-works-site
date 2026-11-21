"""City Survey (DataSF nufj-bfbw) transportation needs and satisfaction by supervisor district (2023) and neighborhood (2023, 2026).

One-off exploratory pull for research/notes/whitepaper-2026-11/2026-11-12-needs-satisfaction-by-district.mdx; not a scheduled updater.

Fetch (one call, about 5,000 rows) into scratch/runs/needs-by-district/raw/:
  python3 tools/travel/city-survey-by-district.py fetch
Analyse:
  python3 tools/travel/city-survey-by-district.py

Definitions follow the Controller's: grades are coded 5 = A ... 1 = F and averaged with the
`weight` column, blanks left out; "feels safe" is a 4 or 5 on both safe_day and safe_night
(2023 Summary Report p. 11). Margins use Kish's effective sample size, n_eff = (sum w)^2 / sum w^2.
2026 has no bosdistrict values at all, so districts are 2023 only.

Checks before writing: row counts match the Controller's 2,530 (2023) and 2,505 (2026)
interviews; citywide 2023 grades reproduce the Summary Report's results table (p. 21) to 0.01;
the 2023 neighborhood range of "safe day and night" reproduces its 20% to 54% (p. 11).
Also prints the 2023 reasons for feeling unsafe (safe_open1, safe_open3).
Writes data/needs-by-district/district_2023.csv and nhood.csv.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, json, math, os, subprocess, sys, collections

ROOT = paths.ROOT
RAW = os.path.join(ROOT, 'scratch', 'runs', 'needs-by-district', 'raw', 'nufj-bfbw-2023-2026.json')
OUT = os.path.join(ROOT, 'data', 'needs-by-district')

GRADES = ['muni_rate', 'inf_stcond', 'inf_sidecond', 'safe_day', 'safe_night', 'inf_light', 'inf_clean']
ISSUES = ['issue_1', 'issue_2', 'issue_3', 'issue_4']
TRANSPORT_ISSUES = {'transit', 'traffic_safety_congestion', 'car_parking_restrictions', 'car_free_advocacy'}
FREQ = ['trans_drive_freq', 'trans_muni_freq', 'trans_bike_freq', 'trans_walk_freq']
OFTEN = {'Daily', '3-6 Days/week'}
WEEKLY = OFTEN | {'1-2 Days/week'}

# Controller, City Survey 2023 Summary Report, results overview p. 21.
PUBLISHED_2023 = {'muni_rate': 3.35, 'inf_stcond': 3.13, 'inf_sidecond': 3.14, 'safe_day': 3.68, 'safe_night': 2.96}


def fetch():
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    cols = ['year', 'weight', 'mode', 'bosdistrict', 'nhood', 'muni_user_yes', 'muni_nonuser1', 'safe_open1', 'safe_open3'] + GRADES + ISSUES + FREQ
    subprocess.run(['curl', '-sG', 'https://data.sf.gov/resource/nufj-bfbw.json',
                    '--data-urlencode', '$select=' + ','.join(cols),
                    '--data-urlencode', "$where=year in ('2023','2026')",
                    '--data-urlencode', '$limit=50000', '-o', RAW], check=True)


def grade(r, c):
    v = r.get(c)
    if v in (None, ''):
        return None
    v = int(float(v))
    return v if 1 <= v <= 5 else None


def wmean(pairs):
    """Weighted mean and 95% margin from (value, weight) pairs."""
    pairs = [(v, w) for v, w in pairs if v is not None]
    if not pairs:
        return None, None, 0
    W = sum(w for _, w in pairs)
    m = sum(v * w for v, w in pairs) / W
    neff = W * W / sum(w * w for _, w in pairs)
    var = sum(w * (v - m) ** 2 for v, w in pairs) / W
    return m, 1.96 * math.sqrt(var / neff), len(pairs)


def summarise(rs):
    o = {'n': len(rs)}
    for c in GRADES:
        m, moe, n = wmean([(grade(r, c), float(r['weight'])) for r in rs])
        o[c] = round(m, 3) if m is not None else None
        o[c + '_moe'] = round(moe, 3) if moe is not None else None
    def share(test, keep=lambda r: True):
        m, moe, n = wmean([(1.0 if test(r) else 0.0, float(r['weight'])) for r in rs if keep(r)])
        return (round(100 * m, 1), round(100 * moe, 1), n) if m is not None else (None, None, 0)
    both = lambda r: grade(r, 'safe_day') is not None and grade(r, 'safe_night') is not None
    o['safe_both_pct'], o['safe_both_moe'], _ = share(lambda r: grade(r, 'safe_day') >= 4 and grade(r, 'safe_night') >= 4, both)
    o['unsafe_night_pct'], o['unsafe_night_moe'], _ = share(lambda r: grade(r, 'safe_night') <= 2, lambda r: grade(r, 'safe_night') is not None)
    o['muni_used_pct'], o['muni_used_moe'], _ = share(lambda r: r.get('muni_user_yes') == '1', lambda r: r.get('muni_user_yes') in ('0', '1'))
    o['drive_often_pct'], o['drive_often_moe'], _ = share(lambda r: r.get('trans_drive_freq') in OFTEN, lambda r: r.get('trans_drive_freq'))
    o['transit_often_pct'], o['transit_often_moe'], _ = share(lambda r: r.get('trans_muni_freq') in OFTEN, lambda r: r.get('trans_muni_freq'))
    o['bike_weekly_pct'], o['bike_weekly_moe'], _ = share(lambda r: r.get('trans_bike_freq') in WEEKLY, lambda r: r.get('trans_bike_freq'))
    o['issue_transport_pct'], o['issue_transport_moe'], _ = share(lambda r: bool({r.get(c) for c in ISSUES} & TRANSPORT_ISSUES))
    o['issue_transport_n'] = sum(1 for r in rs if {r.get(c) for c in ISSUES} & TRANSPORT_ISSUES)
    return o


def main():
    rows = json.load(open(RAW))
    years = collections.Counter(r['year'] for r in rows)
    print('rows', dict(years))
    if years.get('2023') != 2530 or years.get('2026') != 2505:
        sys.exit('row counts %s differ from the Controller\'s 2,530 and 2,505: truncated or changed' % dict(years))
    y23 = [r for r in rows if r['year'] == '2023']
    y26 = [r for r in rows if r['year'] == '2026']
    if any(r.get('bosdistrict') for r in y26):
        print('NOTE: 2026 now carries bosdistrict values; the page says it has none')

    city23 = summarise(y23)
    for c, pub in PUBLISHED_2023.items():
        print('reproduce %s: ours %.2f, Controller %.2f' % (c, city23[c], pub))
        if abs(round(city23[c], 2) - pub) > 0.011:
            sys.exit('citywide %s does not reproduce the published %.2f' % (c, pub))
    city26 = summarise(y26)
    print('muni used 2023 %.1f (Controller 83%%), 2026 %.1f (Controller 88%%)' % (city23['muni_used_pct'], city26['muni_used_pct']))

    os.makedirs(OUT, exist_ok=True)
    out = [dict(district='Citywide', **city23)]
    for d in sorted({r['bosdistrict'] for r in y23 if r.get('bosdistrict')}, key=int):
        out.append(dict(district='D' + d, **summarise([r for r in y23 if r.get('bosdistrict') == d])))
    keys = list(out[0].keys())
    with open(os.path.join(OUT, 'district_2023.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(out)
    for o in out:
        print({k: o[k] for k in ['district', 'n', 'muni_rate', 'inf_stcond', 'inf_sidecond', 'safe_night', 'safe_both_pct',
                                 'unsafe_night_pct', 'muni_used_pct', 'drive_often_pct', 'transit_often_pct', 'bike_weekly_pct',
                                 'issue_transport_pct', 'issue_transport_n']})

    nh = []
    for year, rs in (('2023', y23), ('2026', y26)):
        for name in sorted({r['nhood'] for r in rs if r.get('nhood')}):
            sub = [r for r in rs if r.get('nhood') == name]
            nh.append(dict(year=year, nhood=name, **summarise(sub)))
    with open(os.path.join(OUT, 'nhood.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, ['year', 'nhood'] + keys); w.writeheader(); w.writerows(nh)
    big23 = [o for o in nh if o['year'] == '2023' and o['n'] >= 30]
    lo = min(big23, key=lambda o: o['safe_both_pct']); hi = max(big23, key=lambda o: o['safe_both_pct'])
    print('2023 safe day and night, neighborhoods n>=30: min %s %.1f, max %s %.1f (Controller 20%% to 54%%)'
          % (lo['nhood'], lo['safe_both_pct'], hi['nhood'], hi['safe_both_pct']))
    if round(lo['safe_both_pct']) != 20 or round(hi['safe_both_pct']) != 54:
        sys.exit('2023 neighborhood range does not reproduce the Controller\'s 20% to 54%')

    # 2023 first reason for feeling unsafe (safe_open1; safe_open2 repeats it, second mentions are in safe_open3), unweighted.
    first = collections.Counter(r['safe_open1'] for r in y23 if r.get('safe_open1'))
    second = collections.Counter(r['safe_open3'] for r in y23 if r.get('safe_open3'))
    print('unsafe first reasons, %d people:' % sum(first.values()), first.most_common())
    print('unsafe second reasons (safe_open3), %d people:' % sum(second.values()), second.most_common(6))

    # 2023 non-riders' first reason, by district (444 answered).
    reasons = collections.defaultdict(collections.Counter)
    for r in y23:
        if r.get('muni_nonuser1'):
            reasons['Citywide'][r['muni_nonuser1']] += 1
    print('non-rider first reason 2023', reasons['Citywide'].most_common())


if __name__ == '__main__':
    if sys.argv[1:] == ['fetch']:
        fetch()
    else:
        main()
