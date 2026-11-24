#!/bin/bash
# Aggregate and summarise an ewt directory on the VM: the main extract (TfL weights), the frequent-line extract the site reads, the 95%-tracked, no-guard and
# scheduled-bus-weighted (--eb) sensitivity extracts, the summaries ewt_analyze.py writes for each, and feed-quality
# markers, then speed and excess trip time (trip_analyze.py) and each line's miles and hours by month and by month and hour (speed_line_month.py), then each month's stop-level excess wait (ewt_stops.py) and the same by clock hour (ewt_stop_hours.py) and each line's figures by date (ewt_daily.py), on-time at timepoints in the less frequent hours (ontime_month.py), and stop-to-stop times (stop_pair_time.py, the input of speed_along_line.py and the lever study). Scripts are read from this file's directory. Usage (on the VM): bash post_all.sh [ewt dir, default ewt] [root]
set -e
S=$(cd "$(dirname "$0")" && pwd); H=${2:-$HOME/muni-511}; cd "$H"; export PYTHONPATH=$H/pylib PYTHONHASHSEED=0; E=${1:-ewt}
mkdir -p $E/.stamps
# Stop-to-stop times (stop_pair_time.py), run at the end of every call, after the summaries or in place of them when
# the skip below finds nothing changed, so a missing or stale month is rebuilt even when nothing else moved. A month
# is rebuilt when pairs/<m>.parquet is missing, its stamp (pairs/<m>.stamp, the script's hash, written only after the
# month succeeds and removed before it starts, so a run killed mid-write rebuilds it) differs, or it is older than its
# hourly blocks, its stop observations or the distance table (ref/stamp, dist_table.py). A month whose stop
# observations are gone is left as it is and named. One month at a time (it holds up to 12 GB), nice 10. A failing
# month exits 1 after the summaries are done, so the next run retries only the pairs.
pairs() {
  mkdir -p $E/pairs; local h=$(sha256sum "$S/stop_pair_time.py" | cut -c1-16) f m p o r
  for f in $E/hourly/202*.parquet; do m=$(basename $f .parquet); p=$E/pairs/$m.parquet; o=$H/history/regional-$m-so-sf/stop_observations.csv.gz
    if [ ! -f $o ]; then echo "pairs $m: no stop observations; left as it is"; continue; fi
    if [ ! -f $p ] || [ "$(cat $E/pairs/$m.stamp 2>/dev/null)" != "$h" ] || [ $p -ot $f ] || [ $p -ot $o ] || [ $p -ot $E/ref/stamp ]; then
      rm -f $E/pairs/$m.stamp
      r=$(nice -n 10 python3 $S/stop_pair_time.py $H/history/regional-$m-so-sf $E $m --tables $E/ref 2>&1) || { echo "pairs $m failed:"; echo "$r" | tail -5; exit 1; }
      echo $h > $E/pairs/$m.stamp
      echo "pairs $m: $(echo "$r" | tail -1 | cut -c1-200)"; fi; done
}
# Skip everything when no month's blocks and no script changed since the last complete run: DuckDB's parallel sums
# move the last digits of the summaries from run to run, so a rerun on the same inputs would not write the same bytes.
# The signature is every month's hourly and seg stamp (rerun_all.py, which cover the scripts that build them) plus the
# scripts this file runs, so an edit to an analysis script beside them reruns nothing. FORCE=1 reruns.
SIG=$( (cat $E/hourly/*.stamp $E/seg/*.stamp 2>/dev/null; cd $S && sha256sum post_all.sh ewt_aggregate.py ewt_analyze.py feedq.py \
  trip_analyze.py speed_line_month.py ewt_stops.py ewt_stop_hours.py ewt_daily.py ontime_month.py freq_rule.py) | sha256sum | cut -c1-16)
if [ "${FORCE:-}" != 1 ] && [ "$(cat $E/.stamps/post 2>/dev/null)" = "$SIG" ]; then echo "post: no month or script changed; nothing rebuilt"; pairs; exit 0; fi
python3 $S/ewt_aggregate.py $E $E/extract.csv
python3 $S/ewt_aggregate.py $E $E/extract_cov95.csv 0.95
python3 $S/ewt_aggregate.py $E $E/extract_noguard.csv --no-guard
python3 $S/ewt_aggregate.py $E $E/extract_eb.csv --eb
# frequent lines only (every line but SFMTA's Connector and Owl lines, freq_rule.py), the site's excess-wait rule
python3 $S/ewt_aggregate.py $E $E/extract_freq.csv --frequent
python3 $S/ewt_analyze.py $E/extract.csv $E/diag intake $E/summary > $E/analyze.log
python3 $S/ewt_analyze.py $E/extract_cov95.csv $E/diag intake $E/summary_cov95 > /dev/null
python3 $S/ewt_analyze.py $E/extract_noguard.csv $E/diag intake $E/summary_noguard > /dev/null
python3 $S/ewt_analyze.py $E/extract_eb.csv $E/diag intake $E/summary_eb --eb > /dev/null
python3 $S/feedq.py $E/diag > $E/feed_quality.txt
python3 $S/trip_analyze.py $E $E/extract_months.csv $E/summary_trip > $E/trip_analyze.log
python3 $S/speed_line_month.py $E $E/summary_trip/speed_line_month.csv
python3 $S/speed_line_month.py $E $E/summary_trip/speed_line_hour.csv --by-hour
# A month's CSV below is rebuilt when its Parquet is newer, and every month is when the script that writes it changed:
# fresh <dir> <script> clears <dir>'s month CSVs if the hash of the script and freq_rule.py differs from the one $E/.stamps/<dir> holds, and
# stamp <dir> <script> records it once the loop has finished without error (set -e stops the run before that).
fresh() { h=$(cat "$S/$2" "$S/freq_rule.py" | sha256sum | cut -c1-16); [ "$(cat $E/.stamps/$1 2>/dev/null)" = "$h" ] || rm -f $E/$1/202*.csv; }
stamp() { cat "$S/$2" "$S/freq_rule.py" | sha256sum | cut -c1-16 > $E/.stamps/$1; }
# stop-level excess wait, frequent hours, for each month from 2022 on whose hourly blocks are newer than its CSV
mkdir -p $E/stops; fresh stops ewt_stops.py
for f in $E/hourly/202*.parquet; do m=$(basename $f .parquet); [ $E/stops/$m.csv -nt $f ] || python3 $S/ewt_stops.py $f $E/stops/$m.csv; done
stamp stops ewt_stops.py
# the same stops by clock hour (ewt_stop_hours.py), for the line pages' heat maps; each month's hours must add up to its
# stops file above, or the run stops here
# (fresh clears *.csv only, so the gzipped months are cleared here when the script or freq_rule.py changed)
mkdir -p $E/stophours
[ "$(cat $E/.stamps/stophours 2>/dev/null)" = "$(cat "$S/ewt_stop_hours.py" "$S/freq_rule.py" | sha256sum | cut -c1-16)" ] || rm -f $E/stophours/202*.csv.gz
for f in $E/hourly/202*.parquet; do m=$(basename $f .parquet); [ $E/stophours/$m.csv.gz -nt $E/stops/$m.csv ] || python3 $S/ewt_stop_hours.py $f $E/stophours/$m.csv.gz $E/stops/$m.csv; done
stamp stophours ewt_stop_hours.py
# each line's excess wait and speed by service date (ewt_daily.py), same months
mkdir -p $E/daily; fresh daily ewt_daily.py
for f in $E/hourly/202*.parquet; do m=$(basename $f .parquet); [ -f $E/seg/$m.parquet ] || continue; [ $E/daily/$m.csv -nt $f ] && [ $E/daily/$m.csv -nt $E/seg/$m.parquet ] || python3 $S/ewt_daily.py $f $E/seg/$m.parquet $E/daily/$m.csv; done
stamp daily ewt_daily.py
# by week over every month at once (the 5-year and Max views)
python3 $S/ewt_daily.py "$E/hourly/202*.parquet" "$E/seg/20*.parquet" $E/daily/weekly.csv --by-week
# and by hour for the newest three months only, for the 30- and 90-day views (the page groups 90 days into 6-hour blocks)
rm -f $E/daily/hourly-*.csv $E/daily/6h-*.csv
for f in $(ls $E/hourly/202*.parquet | tail -3); do m=$(basename $f .parquet); python3 $S/ewt_daily.py $f $E/seg/$m.parquet $E/daily/hourly-$m.csv --by-hour; python3 $S/ewt_daily.py $f $E/seg/$m.parquet $E/daily/6h-$m.csv --by-6h; done
# on time and left early at timepoints in the hours that are not frequent (ontime_month.py), each month whose hourly
# blocks are newer than its CSV
mkdir -p $E/ontime; fresh ontime ontime_month.py
for f in $E/hourly/202*.parquet; do m=$(basename $f .parquet); [ $E/ontime/$m-days.csv -nt $f ] || python3 $S/ontime_month.py $H/history/regional-$m-so-sf $E $m; done
stamp ontime ontime_month.py
echo $SIG > $E/.stamps/post
pairs
echo post done
