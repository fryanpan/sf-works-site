# pipeline

The refresh runner and what keeps it honest. `transportation-update.py` runs every step that fetches a source or builds an output, in order, and skips a step whose inputs have not changed. `transportation-quality.py` holds the checks each step must pass, `transportation-audit.py` the data audit against `transportation-data-audit-criteria.md`, and `refresh-freshness.py` the check that each source is current. `site-refresh/` is the scheduled run on the cloud server: `run.sh`, which its systemd timer starts daily, `refresh.py`, `vm-setup.sh`, which installs both, and `move-refresh.sh`, which moves a VM's scheduled refresh into this clone from another clone, caches included. `refresh.py` opens its alerts and records its heartbeat in the repo the `ALERT_REPO` setting names, or this one when it is unset. `requirements-geo.txt` and `requirements-refresh.txt` pin the analysis virtualenv `venv-step.py` runs steps in. `sources/` fetches the city base data the tools share: streets, block lengths, addresses, districts, census blocks and equity areas. `check-large-files.py` fails on a file of 1 MB or more that is not in Git LFS, and `check-public-repo.mjs` on anything private anywhere in the repo.

    python3 pipeline/transportation-update.py --dry-run          # print the plan, run nothing
    python3 pipeline/transportation-update.py                    # run every step that is due
    python3 pipeline/transportation-update.py --only <step,...>  # run named steps
    python3 pipeline/transportation-update-test.py               # the runner's tests
    python3 pipeline/check-large-files.py
    node pipeline/check-public-repo.mjs

## Rules every scheduled step meets

A fetch that a page, report or other build reads on a schedule is an updater, and meets all six:

1. **Incremental.** It asks the source whether anything changed, by the source's own marker (DataSF `rowsUpdatedAt`, an ArcGIS row count and newest edit, a sitemap's `lastmod`), and re-reads only what moved. A source with no marker gets a bounded re-read, named in the script's docstring. A failed re-read keeps the last good copy.
2. **Checked.** Quality checks run right after every fetch: row counts against a floor or the previous count, required fields present, dates in range, keys unique, joins that neither drop nor duplicate rows. A failing check keeps the previous data and stops the steps that read it.
3. **Idempotent.** A run with no new data changes no tracked file. Run stamps are never the only change in a file (`lib/stable.py`), output order is sorted, and a date a figure is computed from is the date its data was read, not the wall clock.
4. **Stable identifiers.** A published id never changes or disappears (`data/project-ids.json`, `lib/project_ids.py`).
5. **Registered.** The step is in `STEPS` in `transportation-update.py`, and each check is recorded in `data/pipeline-state/sources.json`.
6. **Proven.** Run twice with no change in `git status`; remove the newest item and see only it fetched again; see a quality check fail on bad input.

Each step also names its update interval, at most weekly, and the freshness check fails when its newest data is older than that. Each page whose data updates says near its top when the data was last read.
