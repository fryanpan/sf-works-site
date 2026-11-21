# Street arrangements, pedestrian-violation crashes

A fixed snapshot, not a refreshed dataset: the people killed or severely injured in San Francisco from 2022 to 2024 in crashes police blamed on a pedestrian violation, sorted into seven street arrangements, with one sketch each. Crash data read 2026-11-20 from DataSF ([crash victims](https://data.sfgov.org/d/nwes-mmgh), [crash parties](https://data.sfgov.org/d/8gtc-pjc6), [street centerlines](https://data.sfgov.org/d/3psu-pn9h)). The daylighting verdicts are our inference.

`manifest.json` and the seven SVGs were copied by hand from the output of a generator that still lives in the gitignored scratch folder (`scratch/runs/hin-figures/daylight_arrangements.py`), because it reads other scratch scripts and caches and so can't run from tracked inputs. Nothing rebuilds these files. The Street Safety map's carousel (`site/src/safety-map/arrangements.mjs`) reads them at build time.
