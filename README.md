# SF Works

The source of [sf-works.org](https://sf-works.org): pages that use San Francisco's own data to show how the city works, the scripts and data that build them, and the research notes the pages cite.

## What's here

| Path | Holds |
| --- | --- |
| `site/` | The website. Astro, with charts drawn by Observable Plot at build time, plus its checks and tests. |
| `pipeline/` | The refresh runner that fetches each source and rebuilds what changed, its quality checks, audit and freshness check, and `pipeline/sources/` for the city base data every tool shares. |
| `tools/` | One folder per tool on the site (street safety, school trips, bike network, Muni, travel, projects, meetings, toolkit, grand juries): the scripts that write its data. |
| `lib/` | Python modules two or more folders import, and `paths.py`, which finds the repo root and any script by file name. |
| `data/`, `out/` | Fetched source data and generated outputs, one folder per source or tool. Most come from DataSF, SFMTA and other public sources; each script's docstring names its source. Files of 1 MB or more are in Git LFS. |
| `research/` | The research notes and source descriptions that published pages cite, one folder per thread. |

Each folder's README says what it holds and which command runs it.

Pull requests are welcome. Each one runs the checks in `.github/workflows/checks.yml`, and a merge to `main` deploys the site.

## Getting started

1. Clone, with [Git LFS](https://git-lfs.com) installed for the large data files: `git clone https://github.com/fryanpan/sf-works-site.git`
2. Install: `cd site && npm ci`
3. Build: `npm run build` (the pages land in `site/dist/`)

Maps fall back to OpenFreeMap tiles when no `GOOGLE_MAPS_KEY` is set.

Refreshing the data runs `python3 pipeline/transportation-update.py` (`--dry-run` prints the plan). Most steps need only Python 3; the steps that use numpy, GeoPandas or GrowBikeNet run in a virtualenv built from the pinned requirements:

    python3.13 -m venv ~/.venvs/sf-works-geo
    ~/.venvs/sf-works-geo/bin/pip install -r pipeline/requirements-geo.txt -r pipeline/requirements-refresh.txt

Settings that name private infrastructure (a cloud bucket, a review board) are optional and kept out of the repo, in environment variables or a gitignored `local-settings.json`; `lib/settings.py` lists them.

## License

MIT; see [LICENSE](LICENSE). Data from public agencies keeps its source's terms.
