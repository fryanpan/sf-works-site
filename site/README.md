# site

The website at [sf-works.org](https://sf-works.org): Astro pages in `src/pages/`, markdown pages in `content/`, the data they read in `data/`, and the build's checks in `scripts/`. `tests/` holds the site's tests and their fixtures. `src/plot-chart/` is the one copy of the shared chart code (`plot-spec.mjs`).

    cd site && npm ci
    npm run build      # pages land in site/dist/
    npm run check      # every check and test
    npm run dev        # build, then serve locally
