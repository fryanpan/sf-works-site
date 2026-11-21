# Transportation audit inputs

Hand-kept inputs to `pipeline/transportation-audit.py`, which checks the data
behind the biking pages against `pipeline/transportation-data-audit-criteria.md`
and writes `out/transportation-audit/report.md`. Everything here is tracked, so a
grade or an explanation is reviewed like code.

## grades/d2-dates.csv (criterion D2)

A seeded random sample of 60 listed projects, four rows each for construction
start, construction end, public consultation start and public consultation end,
plus up to two other dates the project page shows. The audit wrote the rows; a
person fills three columns.

| Column | Meaning |
| --- | --- |
| `slug` | the project page, `/transportation/projects/<slug>` |
| `project`, `department` | as the list shows them |
| `field` | the milestone graded; `other: <label>` for any other date shown |
| `shown` | what our page shows, or `not published` |
| `department_page` | the department's own page: the one the list links, or one the department publishes under nearly the same name. `none found` when the department publishes no page for the project; a DataSF row is never used here, since it is where the shown date came from |
| `source_row` | the row the shown date was read from (a DataSF feed row, or the record's own address), for reference only |
| `department_says` | **fill in**: the date the department gives for that milestone, or `not published` |
| `grade` | **fill in**: `correct`, `wrong`, `sources disagree` (the page gives a different date and the page itself or another source supports ours; counts as not correct), `not on page` (the page exists but gives no date for this milestone) or `no page` (the department publishes no page). A correct `not published` is `correct`. A season on the page matches a date within a month of that season. City-body records are graded against the meeting the record comes from. The last two grades are left out of the shares and counted beside them |
| `note` | anything the next grader needs |

D2 reports NOT GRADED until every row has a grade. It also prints, per
department, how many sampled projects have no department page to grade against.

A sampled project that leaves the list shows no dates, so its rows stay in
the file with their grades and D2 leaves them out. The audit then tops the
sample up to 60 listed projects with ones drawn from the rest of the list
(seed `D2_TOPUP_SEED` in `pipeline/transportation-audit.py`), their rows added
blank for grading. Six left on 2026-09-29 and six were drawn in their place.

When a fix changes a date the list shows, the row's `shown` is updated to the
new value and the row is graded again against the page; the `note` says so.

Until anyone fills a grade, the audit rewrites both sample files from the
current list on every run (the samples are seeded, so they move only when the
list does). Once one row carries a grade, the file is left alone.

## grades/c3-links.csv (criterion C3, the hand-checked sample)

A seeded random sample of 40 records shown under "City decisions naming this
project" that a city body published. Items from a project's own page are left
out: whether they belong under City decisions is C3a's question, and the
sample is there to test the name matcher.

| Column | Meaning |
| --- | --- |
| `slug`, `project` | the project the record is attached to |
| `record_date`, `record_label`, `relation`, `record_title`, `record_url` | the record as the page shows it |
| `route` | how `tools/projects/project-record.py` attached it: full name, head of the name, contract number (in the name, or from the feed's scope), place-named project, a named program's instance on its street, or a contract award on its streets. A match on the street alone is shown as "same street" and is never counted, so it is not sampled. Each route gets up to four links; the rest of the 40 are drawn at random |
| `seed` | the random seed that drew the sample (`C3_SEED` in `pipeline/transportation-audit.py`); a new sample takes a new seed |
| `about_project` | **fill in**: `yes` when the record is about this project, `no` otherwise |
| `label_correct` | **fill in**: `yes` when the label (SFMTA Board, Engineering hearing…) says what the record is |
| `note` | why, for any `no` |

## explanations.csv

For pass lines that say "every miss explained". One row per explained miss.

| Column | Meaning |
| --- | --- |
| `check` | the check id as the report prints it: `A1-PW`, `A2`, `C2`… |
| `key` | the row's key as the report prints it, usually the project or job name (case does not matter) |
| `explanation` | why it is missing or short, in a sentence a reader can check |

An explained row still counts in the measured number. The check passes only
when the number is within its line and every counted row is explained.

## typed-figures.csv (criterion F4)

Every figure typed into the page prose (`site/content/`) rather than filled
from data. The audit lists them; a person classifies each one.

| Column | Meaning |
| --- | --- |
| `file` | the content file |
| `figure` | the figure as the audit prints it |
| `context` | a few words next to it, enough to tell two `80%` apart |
| `verdict` | `external`: a quote of a source the data does not hold, which may stay typed. `data`: the data could supply it, so it fails until the page fills it from data |
| `note` | the source, or what data field could supply it |

## cache/

Network reads the audit keeps between runs. `pipeline/transportation-audit.py
--refresh` rewrites them: `sfmta-sitemap.json` (every `/projects/` page in
SFMTA's sitemap), `link-status.json` (the HTTP status of every department link
on the list) and `metadata.json` (DataSF's own last-updated dates). Without
them the audit seeds the sitemap from `data/extract/sfmta-pages/sitemap.json`
and B1 reports NOT MEASURED, since no link is counted live unless this cache
holds a 200 for it. `link-status.json` and `sfmta-sitemap.json` are tracked so
a checkout measures B1 as of the last refresh, whose date they carry;
`metadata.json` is not.
