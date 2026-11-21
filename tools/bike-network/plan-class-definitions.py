#!/usr/bin/env python3
"""Pull the Biking and Rolling Plan's own words for each facility class.

    tools/bike-network/plan-class-definitions.py [--pdf <plan.pdf>] [--out <path.json>]

Registered as the plan-class-definitions build step in
pipeline/transportation-update.py, which copies its output to
site/data/class-definitions.json (NORTH_STAR_COPY).

The streets page sorts 111 segments into Separated, Shared, Shared L3 and
Undecided and then says which ones the city fell short on. Bryan, 2026-09-19:
"the 'traffic calming' class of bike segment is vague unless specified more
clearly in writing." So the page has to carry the plan's definition of each
class, in the plan's words, with a page a reader can turn to.

The PDF is sfmta.com/media/41810/download, 92 MB, 48 PDF pages. It is not
committed — it is 92 MB and it is the city's to publish. It is kept in
.cache/north-star-plan/plan.pdf (gitignored) and fetched from sfmta.com when
missing; --pdf points at another copy.

THREE WAYS A QUOTE FROM THIS PDF COMES OUT WRONG, each of which produces a
plausible sentence rather than a visible failure.

1. The printed page numbers are not the PDF's. PDF page 35 is printed 68-69,
   38 is 74-75, 39 is 76-77. A reader sent to "page 38" turns to the wrong
   page, so every citation here carries the PRINTED number.

2. The pages are laid out in columns, and the reading-order text runs the
   legend into the prose. Reading the map page that way attaches the wavy-line
   sentence to the Undecided swatch, which is a sentence about something else.
   So each quote is cut at an anchor and then checked for legend contamination.

3. Words break across lines with a hyphen, and dropping that hyphen gives
   "mostlevel" and "AllAges-and-Abilities". The hyphens are real: the same
   page prints "lower-speed" and "All-Ages-and-Abilities" whole elsewhere. The
   repairs are read off the -layout rendering rather than typed here, so a
   break this script has never seen still gets fixed.

WHAT THE PLAN DOES NOT SAY is recorded too. There is no prose definition of
Undecided anywhere in the plan — it is a legend swatch and a grey stroke on
the map, nothing more. That is written into the output as a gap, because the
alternative is a sentence somebody wrote to fill the hole.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = paths.ROOT

# Each PDF page is a two-page spread, so PDF page n prints pages 2n-2 and
# 2n-1. Typed by hand this went wrong twice in six on the first attempt, so it
# is derived and then checked against the number in the page's own footer.
def printed(page):
    return f"{2 * page - 2}\u2013{2 * page - 1}"


def footer_page(text):
    """The printed number in the page footer, or None."""
    nums = re.findall(r"(?<![\w>])(\d{1,3})(?![\w])", text)
    return int(nums[-1]) if nums else None


PLAN_URL = "https://www.sfmta.com/media/41810/download"
PLAN_PDF = os.path.join(ROOT, ".cache", "north-star-plan", "plan.pdf")


def fetch_plan(path):
    """Download the plan to `path`; exit rather than keep a body that is not a PDF."""
    import urllib.request
    req = urllib.request.Request(PLAN_URL, headers={"User-Agent": "Mozilla/5.0 (sf-works; +https://sf-works.org)"})
    with urllib.request.urlopen(req, timeout=300) as fh:
        body = fh.read()
    if not body.startswith(b"%PDF"):
        sys.exit("%s did not return a PDF" % PLAN_URL)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(body)
PLAN_PAGE = "https://www.sfmta.com/projects/biking-and-rolling-plan"

# sfmta.com serves both PDFs with `Content-Disposition: attachment`, checked
# with curl -sI on 2026-09-20. A browser downloads the file and throws the
# fragment away, so a `#page=` link does not open anyone to a page — it starts
# a 92 MB download, which on a phone is not a document a reader reaches. So
# nothing here emits a deep link, and anything that cites a page has to carry
# the quoted words itself.
DEEP_LINKS_WORK = False

# The map legend's swatch labels. Two or more of these inside one quote means
# the legend column has run into the prose — see trap 2.
LEGEND_LABELS = [
    "Community Action Plans", "Undecided", "Car-free",
    "Destination (school, park, etc.)", "Shared-use Path",
    "Future Connection", "Separated", "Future Plan / Study",
    "Shared - Level 3 Traffic Calming",
]

# start anchor, stop anchor. The stop is the first thing the column after it
# prints, so the cut lands at the end of the description and not mid-sentence.
CUTS = {
    "separated.statement": (38, "Separated facilities are those", "CATEGORY"),
    "separated.car-free": (38, "These facilities do not have cars", "Path or Cycle tracks"),
    "separated.protected": (38, "Protected facilities are on", " Class IV"),
    "separated.separated": (38, "Separated facilities are best exemplified", " Quick builds"),
    "shared.statement": (39, "Shared facilities allow all roadway users", " CATEGORY"),
    "shared.level-i": (39, "Slow Streets that meet low motor", "\u201cNeighborways\u201d"),
    "shared.level-ii": (39, "\u201cNeighborways\u201d and \u201cBicycle", "Traffic-calmed streets"),
    "shared.level-iii": (39, "Traffic-calmed streets that manage", "Making Slow Streets better"),
    "shared.bike-lanes": (39, "While painted bike lanes are a key tool", "Washington Boulevard"),
    # The prose says "three main categories" and then bullets FOUR facilities.
    # An earlier cut started at the second bullet and produced a quotation of
    # three, which read as the plan listing three.
    "map.what-it-draws": (35, "\u00bb Car-free streets like", "\u00bb Lighter-shaded"),
    "map.shared-l3-ceiling": (35, "\u00bb Lighter-shaded shared facilities", "\u00bb Wavy lines"),
    "map.wavy-lines": (35, "\u00bb Wavy lines indicate", "Community Action Plans"),
    "network.definition": (33, "This North Star network is defined as", "Policy 8."),
    # The map that carries the Shared - Level 3 class is itself introduced as a
    # network of All-Ages-and-Abilities bikeways. Without this, the typology's
    # silence on Level III reads as the plan excluding it from that standard.
    "network.is-aaa": (35, "we developed this draft of the North Star Network", 1),
    # And the plan does not claim pp. 74-77 are definitions: adopting them is
    # an action it has yet to carry out. This is the answer to "what does
    # traffic calming mean" — the plan has not said yet, and knows it.
    "network.definitions-pending": (33, "Adopt definitions and operating characteristics",
                                    "Provide flexibility"),
    "network.aaa-today": (13, "As of 2024, 8% of streets", "All-ages and abilities network"),
    # A per-street score does exist, which is why the page must not say the
    # index cannot be checked — only that the published bins straddle 80.
    "bci.all-streets": (18, "The Bicycle Conditions Index", " As an example"),
}

# Cuts that are a bullet list rather than prose. The plan does not end its
# last bullet with a full stop, so the mid-sentence check would fire on a
# clean read; these are split on the bullet character instead.
BULLETS = {"map.what-it-draws"}

# Cuts that are a map legend: no sentence punctuation at all, and the entries
# are split where a new one starts rather than on every "Class", because the
# first entry is itself "Class I, Class IV, and Slow Streets".
LEGENDS = {"network.aaa-today"}
LEGEND_SPLIT = re.compile(r"(?=Class II with|Class III with)")

# Cuts where a check is wrong for this passage, named one by one so that
# relaxing a guard is a decision about one quote rather than about the guard.
#   legend  — the passage legitimately lists facility names ("Car-free,
#             Protected, Separated, Shared Level I, II, III"), which is what
#             the column-bleed check looks for.
#   period  — the passage genuinely has no closing full stop. An action item
#             in this plan is a phrase, not a sentence.
#   caps    — the passage legitimately prints Roman numerals ("Shared Level
#             I, II, III"), which is what the map-label check looks for.
EXEMPT = {"network.definitions-pending": {"legend", "period", "caps"}}

# Which cut defines each class the streets page uses.
CLASS_OF = {
    "Separated": "separated.statement",
    "Shared": "shared.statement",
    "Shared L3": "shared.level-iii",
}


def page_text(pdf, page, layout=False):
    cmd = ["pdftotext"] + (["-layout"] if layout else []) + [
        "-f", str(page), "-l", str(page), pdf, "-"]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def runs(line):
    """[(start column, text)] for each column of text on a laid-out line.

    Two or more spaces is the column gap pdftotext leaves between columns, so
    it is what separates one run from the next.
    """
    out, col = [], 0
    for piece in re.split(r"( {2,})", line):
        if piece and not piece.isspace():
            out.append((col, piece))
        col += len(piece)
    return out


def hyphen_repairs(layout):
    """{"onstreet": "on-street"} for every word this page breaks over a line.

    Read off the laid-out rendering rather than listed by hand, so a break
    this script has never seen still gets repaired.

    The continuation has to be found in the SAME COLUMN. Taking the next
    non-empty line instead reads the neighbouring column and produces
    "on-Class" for "on-street" — a repair that looks like it worked. These
    pages are three and four columns wide, so that is the common case, not
    the edge one.
    """
    out = {}
    lines = layout.splitlines()
    table = [runs(ln) for ln in lines]
    for i, row in enumerate(table):
        for col, text in row:
            if not text.endswith("-") or len(text) < 2 or not text[-2].isalpha():
                continue
            head = text.split()[-1].rstrip("-")
            for below in table[i + 1:]:
                near = [t for c, t in below if abs(c - col) <= 3]
                if not near:
                    continue
                tail = near[0].split()[0]
                if head and tail and tail[0].isalpha():
                    out[head + tail] = f"{head}-{tail}"
                break
    return out


def bullets(layout, first, last):
    """The bullet list running from `first` to `last`, read column-wise.

    The reading-order text cannot be used here. These bullets sit beside a
    city map, and the first one starts on the same output line as a paragraph
    two columns away, so a flowed cut from it runs straight through street
    labels ("JFK Promenade S D IN RR GEN Add traffic ..."). Reading the run at
    a fixed column skips the map entirely.
    """
    items, col, buf = [], None, []
    for line in layout.splitlines():
        for c, text in runs(line):
            if text.startswith("\u00bb") and (col is None or abs(c - col) <= 3):
                if first in text and col is None:
                    col = c
                elif col is None:
                    continue
                if last in text:
                    if buf:
                        items.append(" ".join(buf))
                    return items
                if buf:
                    items.append(" ".join(buf))
                buf = [text.lstrip("\u00bb ").strip()]
            # A wrapped line is indented past its bullet — 68 for the bullet,
            # 77 for the rest of it on this page — so the continuation window
            # runs forward from the bullet column, not around it.
            elif col is not None and buf and col <= c <= col + 12:
                buf.append(text.strip())
    return items or None


def grab(text, start, stop):
    """The span from `start` to `stop`.

    `stop` is normally the first words of the next column, so the cut lands at
    the end of the passage. Where what follows is map labels rather than prose
    — they move between renderings and cannot be anchored on — `stop` is an
    int instead, meaning "take this many sentences".
    """
    i = text.find(start)
    if i < 0:
        return None
    if isinstance(stop, int):
        out, rest = [], text[i:]
        for _ in range(stop):
            m = re.search(r"\.(?:\s|$)", rest)
            if not m:
                return None
            out.append(rest[:m.end()])
            rest = rest[m.end():]
        return "".join(out).strip()
    j = text.find(stop, i + len(start))
    return text[i:j].strip() if j > 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=PLAN_PDF,
                    help="the plan PDF (fetched from sfmta.com when missing)")
    ap.add_argument("--out", default=os.path.join(
        ROOT, "out", "north-star", "class-definitions.json"))
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        fetch_plan(args.pdf)
    # pdftotext reads the PDF in a subprocess, which the pipeline's read trace
    # (lib/trace_io) cannot see. Reading it here once records it as an
    # input, so a new copy of the plan reruns this step.
    with open(args.pdf, "rb") as fh:
        print("plan sha256", hashlib.sha256(fh.read()).hexdigest()[:16])

    wanted = sorted({page for page, _, _ in CUTS.values()})
    flow, repairs, problems = {}, {}, []
    for n in wanted:
        flow[n] = re.sub(r"\s+", " ", page_text(args.pdf, n))
        repairs.update(hyphen_repairs(page_text(args.pdf, n, layout=True)))
        stamped = footer_page(flow[n])
        if stamped != 2 * n - 1:
            problems.append(
                f"PDF page {n}: footer reads {stamped}, expected {2 * n - 1} — "
                "the spread assumption is wrong for this PDF")

    layout = {n: page_text(args.pdf, n, layout=True) for n in wanted}
    cuts = {}
    for key, (page, start, stop) in CUTS.items():
        raw = (" \u00bb ".join(bullets(layout[page], start, stop) or [])
               if key in BULLETS else grab(flow[page], start, stop))
        if not raw:
            problems.append(f"{key}: anchor not found on PDF page {page}")
            continue
        q = re.sub(r"\s+", " ", raw)
        # pdftotext dehyphenates a line break inconsistently: the same PDF
        # gives "onstreet" on one page and "slow- moving" on another. Repair
        # both — the joined form from the layout pass, then any hyphen still
        # sitting against a space.
        for bad, good in repairs.items():
            q = q.replace(bad, good)
        q = re.sub(r"(\w)-\s+(\w)", r"\1-\2", q)
        q = re.sub(r"^»\s*", "", q).strip()

        skip = EXEMPT.get(key, set())
        hits = [l for l in LEGEND_LABELS if l in q]
        if len(hits) > 1 and "legend" not in skip:
            problems.append(f"{key}: legend ran into the prose — {hits}")
        checks = (
            ("hyphen", r"[a-z]{3,}[A-Z][a-z]{2,}", "unrepaired line break"),
            ("hyphen", r"\w-\s", "unrepaired line break"),
            # Street labels read off the map, e.g. "S D IN RR GEN".
            ("caps", r"(?:\b[A-Z]{1,3}\b[ ,]+){3,}", "map labels in the quote"),
        )
        for name, bad, why in checks:
            hit = name not in skip and re.search(bad, q)
            if hit:
                problems.append(f"{key}: {why} near {hit.group(0)!r}")
        if (key not in BULLETS | LEGENDS and "period" not in skip
                and not q.endswith((".", "”"))):
            problems.append(f"{key}: cut mid-sentence, ends {q[-40:]!r}")

        if key in BULLETS:
            cuts[key] = {"items": [b.strip() for b in q.split("»") if b.strip()]}
        elif key in LEGENDS:
            head, _, rest = q.partition("Class ")
            cuts[key] = {
                "caption": head.strip(),
                "items": [e.strip() for e in LEGEND_SPLIT.split("Class " + rest) if e.strip()],
            }
        else:
            cuts[key] = {"quote": q}
        cuts[key].update({
            "printedPage": printed(page),
            "pdfPage": page,
            "url": PLAN_URL,
        })

    if problems:
        # Refuse to write rather than publish words the plan did not print. A
        # missing definition is visible on the page; a mangled one is not.
        sys.exit("not written:\n  " + "\n  ".join(problems))

    out = {
        "source": {
            "title": "San Francisco Biking and Rolling Plan",
            "adopted": "2025-03-04",
            "url": PLAN_URL,
            "projectPage": PLAN_PAGE,
            "note": "Page numbers are the plan's own printed numbers, not the "
                    "PDF's. The PDF is not committed — 92 MB, and the city's "
                    "to publish.",
        },
        "classes": {
            name: dict(cuts[key], definitionOf=key) for name, key in CLASS_OF.items()
        },
        "detail": cuts,
        "deepLinks": {
            "work": DEEP_LINKS_WORK,
            "why": "sfmta.com serves the plan and the appendix with "
                   "Content-Disposition: attachment (curl -sI, 2026-09-20), so "
                   "a browser drops a #page= fragment and starts a 92 MB "
                   "download instead. Citing a page means carrying its words.",
        },
        # The direct answer to "what does the traffic-calming class mean": the
        # plan has not said yet, and has an action item to say later. Pages
        # 74-77 are descriptions, and the plan does not call them definitions.
        "definitionsArePending": {
            "finding": "The plan does not claim to have defined these classes. "
                       "Action 2.7.1 commits the SFMTA to adopting definitions "
                       "and operating characteristics for Car-free, Protected, "
                       "Separated, Shared Level I, II and III, and Bike lanes.",
            "quote": "network.definitions-pending",
            "printedPage": "64\u201365",
            "tag": "[primary \u2014 read 2026-09-20]",
        },
        # Two numbering schemes run through this plan and they are not the
        # same. Conflating them is the specific error this block exists to
        # prevent: an earlier draft of the page read the existing-conditions
        # legend's "Class III with traffic calming" as the typology's "Shared
        # Level III" and concluded the plan contradicted itself.
        "twoVocabularies": {
            "caltrans": "Class I, II, III and IV are the Caltrans bikeway "
                        "classes: path, bike lane, signed shared roadway, "
                        "separated bikeway. The plan uses them for what "
                        "exists, and pairs them with its own separated types "
                        "on printed pages 74\u201375.",
            "plan": "Shared Level I, II and III are the plan's own tiers for "
                    "shared streets, on printed pages 76\u201377.",
            "warning": "The plan never equates a Caltrans class with a Shared "
                       "Level. Do not read 'Class III with traffic calming' as "
                       "'Shared Level III'.",
            "tag": "[primary \u2014 read 2026-09-20]",
        },
        "allAgesAndAbilities": {
            "question": "Is a Shared Level III street an all-ages-and-abilities "
                        "facility? The plan's network is defined as "
                        "all-ages-and-abilities bikeways, so this decides "
                        "whether calming such a street counts as building it.",
            "textualObservation":
                "The Shared Level I and Level II descriptions each end by "
                "calling the facility all-ages-and-abilities. The Level III "
                "description does not, and neither does the Bike Lanes row.",
            "observationPage": "76\u201377",
            "butTheMapDoes":
                "The North Star map carries a 'Shared - Level 3 Traffic "
                "Calming' class, and the plan introduces that map as conveying "
                "'a future connected network of All-Ages-and-Abilities "
                "bikeways'. So the plan does draw Level III streets on a "
                "network it calls all-ages-and-abilities.",
            "mapPage": "68\u201369",
            "reading": "The missing sentence is a gap in the description, not "
                       "the plan excluding Level III from its own standard. "
                       "Read with Action 2.7.1, the simplest account is that "
                       "the plan has not finished defining these classes.",
            "readingTag": "[inference \u2014 mine]",
            "tag": "[primary \u2014 read 2026-09-20]",
        },
        "bicycleConditionsIndex": {
            "whatIsPublished": "The plan says the index 'was updated for all "
                               "streets in San Francisco' and maps it citywide "
                               "in five bands: 0\u201330, 31\u201360, 61\u201390, 91\u2013120, "
                               "121\u2013150.",
            "printedPage": "34\u201335",
            "limit": "The existing-network legend's test is a score above 80, "
                     "and the published band 61\u201390 straddles it. So the map "
                     "cannot settle whether a given street clears the test, "
                     "though a per-street score exists.",
            "tag": "[primary \u2014 read 2026-09-20]",
        },
        "gaps": [
            {
                "class": "Undecided",
                "what": "No sentence in the plan defines Undecided. The word "
                        "appears three times, on two pages, every one of them "
                        "a map legend label: once on the North Star map "
                        "(printed 68\u201369) and twice on printed 80\u201381, in the "
                        "legends of the map with fire stations and the map "
                        "with Muni routes. It is also absent from the list of "
                        "facilities Action 2.7.1 promises to define.",
                "checked": "Searched every page of the plan PDF for the word.",
                "tag": "[primary \u2014 read 2026-09-20]",
                "butAlso": "Appendix L uses Undecided as a facility value on "
                           "32 of its 393 rows, 19 flagged Upgrade and 4 New. "
                           "Existing facility on those rows: Class III 15, "
                           "Lanes 8, None 4, a mixture of two 3, Path 1, and "
                           "one row with the cell left blank.",
                "butAlsoTag": "[primary \u2014 Appendix L via out/north-star/index.csv, "
                              "counted 2026-09-20]",
                "careful": "An Upgrade flag is not a commitment in the plan's "
                           "words. The plan calls the index 'a long-term "
                           "outlook'.",
            },
            {
                "class": "Shared L3",
                "what": "Appendix L never uses a Level 3 value; where it names "
                        "these streets at all it calls them Shared. The class "
                        "exists only as a lighter shade on the map, and the "
                        "index tells the reader to defer to the map where the "
                        "two differ.",
                "checked": "All 393 Appendix L rows in out/north-star/index.csv; "
                           "no north_star value contains Level or L3. Of the "
                           "three segments this repo labels Shared L3, Leese "
                           "St and Richland Ave have rows reading Shared; 29th "
                           "St has no Appendix L row at all.",
                "tag": "[primary \u2014 Appendix L via out/north-star/index.csv, "
                       "counted 2026-09-20]",
            },
        ],
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"wrote {args.out}")
    print(f"  {len(repairs)} line-break repairs read off the layout")
    for key, d in cuts.items():
        shown = d.get("quote") or " / ".join(d["items"])
        print(f"  {key:<24} p{d['printedPage']:<8} {shown[:62]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
