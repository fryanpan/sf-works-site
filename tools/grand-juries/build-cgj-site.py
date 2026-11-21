#!/usr/bin/env python3
"""Turn the Civil Grand Jury topic page into site/data/cgj.json for the site's Grand Juries page.

The topic file is where the research is written and reviewed, one section per
report with four parts (gaps found, key recommendations, response, followed
through) and a summary table of counts. The site may not read outside site/
(site/scripts/check-public.mjs), so this copies the published facts across:
every report's four parts as markdown, its inline notes split out, the
summary table's counts, each term's opening paragraph, and the two method
sections for the About page. Links into this repo (the archived report text)
are dropped, because the site cannot link them; each note keeps its link to
the city's own copy.

The report ids come from data/cgj/reports.json, matched by the report's URL,
so the site's ids are the archive's ids, and each release date in the topic
is checked against the archive's.

    python3 tools/grand-juries/build-cgj-site.py          # write site/data/cgj.json
    python3 tools/grand-juries/build-cgj-site.py --check  # exit 1 if it is out of date

It stops, writing nothing, if a report has a part missing, the table and the
sections disagree on the reports or their order, a count is impossible
(more refused or done than asked), or a repo-relative link survives.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json
import re
import sys
from pathlib import Path

ROOT = Path(paths.ROOT)
TOPIC = ROOT / "research" / "topics" / "sf-civil-grand-jury.md"
ARCHIVE = ROOT / "data" / "cgj" / "reports.json"
OUT = ROOT / "site" / "data" / "cgj.json"

PARTS = [
    ("gaps", "**Gaps found**"),
    ("asks", "**Key recommendations**"),
    ("response", "**Response**"),
    ("followed", "**Followed through?**"),
]
VERDICTS = ("Yes", "Partly", "No", "Unknown")


def fail(msg):
    sys.exit(f"build-cgj-site: {msg}")


def split_notes(text, notes):
    """Replace each Pandoc inline note ^[...] with a {{fn:N}} token, N counting from 1 within the report."""
    out, i = [], 0
    while True:
        j = text.find("^[", i)
        if j == -1:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:j])
        depth, k = 0, j + 1
        while k < len(text):
            if text[k] == "[":
                depth += 1
            elif text[k] == "]":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if depth != 0:
            fail(f"unbalanced note near: {text[j:j + 80]!r}")
        notes.append(clean_note(text[j + 2:k]))
        out.append("{{fn:%d}}" % len(notes))
        i = k + 1


def clean_note(note):
    # The archived text lives in this repo, which the site cannot link.
    note = re.sub(r",?\s*\[archived text\]\(\.\./[^)]*\)", "", note)
    note = note.replace(
        "The responses archived in [`data/cgj/reports.json`](../../data/cgj/reports.json), each citing",
        "The city's posted responses, each citing",
    )
    return note.strip()


def table_counts(lines):
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in ("Report",) or set(cells[0]) <= set("- "):
            continue
        m = re.fullmatch(r"(\d+) of (\d+) \((\d+)\)", cells[4])
        if not m:
            fail(f"unreadable count cell {cells[4]!r}")
        evidence, n2, says = map(int, m.groups())
        n, refused = int(cells[2]), int(cells[3])
        if n2 != n:
            fail(f"{cells[0]}: {n2} in the done column but {n} recommendations")
        if evidence > says or refused + says > n:
            fail(f"{cells[0]}: counts do not fit inside {n} recommendations")
        rows.append({"short": cells[0], "term": cells[1], "n": n, "refused": refused, "evidence": evidence, "citySays": says})
    return rows


def bullets_and_lead(block):
    """A part's lead text (after its bold label) and its bullet items."""
    lead, items = [], []
    for line in block:
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif line.strip():
            if items:
                items[-1] += " " + line.strip()
            else:
                lead.append(line.strip())
    return " ".join(lead).strip(), items


def parse_report(head, body, archive_by_url):
    m = re.fullmatch(r"### \[(.+?)\]\((\S+?)\), (\d{4}-\d{2}-\d{2})", head)
    if not m:
        fail(f"unreadable report heading {head!r}")
    title, url, released = m.groups()
    rec = archive_by_url.get(url)
    if not rec:
        fail(f"{title}: no archived report with URL {url}")
    if rec.get("released") != released:
        fail(f"{title}: released {released} in the topic but {rec.get('released')} in the archive")
    notes = []
    starts = []
    for idx, line in enumerate(body):
        for key, label in PARTS:
            if line.startswith(label):
                starts.append((idx, key, label))
    if [k for _, k, _ in starts] != [k for k, _ in PARTS]:
        fail(f"{title}: parts found {[k for _, k, _ in starts]}")
    intro = " ".join(l.strip() for l in body[: starts[0][0]] if l.strip())
    parts = {}
    for n, (idx, key, label) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(body)
        first = body[idx][len(label):]
        lead, items = bullets_and_lead([first] + body[idx + 1:end])
        lead = split_notes(lead, notes)
        items = [split_notes(x, notes) for x in items]
        part = {"items": items}
        if key == "followed":
            verdict = re.match(r"(\w+)", lead)
            if not verdict or verdict.group(1) not in VERDICTS:
                fail(f"{title}: followed-through verdict unreadable: {lead[:40]!r}")
            part["verdict"] = verdict.group(1)
        if lead:
            part["lead"] = lead
        parts[key] = part
    return {
        "id": rec["id"],
        "title": title,
        "url": url,
        "released": released,
        "intro": split_notes(intro, notes) if intro else "",
        **parts,
        "notes": notes,
    }


def build():
    text = TOPIC.read_text()
    archive = json.loads(ARCHIVE.read_text())
    archive_by_url = {r["url"]: r for r in archive["reports"]}
    lines = text.split("\n")

    # Lede: the paragraphs between the H1 and the table; the table; the paragraph under it.
    t0 = next(i for i, l in enumerate(lines) if l.startswith("| Report"))
    t1 = next(i for i in range(t0, len(lines)) if not lines[i].startswith("|"))
    counts = table_counts(lines[t0:t1])
    lede_notes = []
    lede = [split_notes(l.strip(), lede_notes) for l in lines[1:t0] if l.strip()]
    under_table = []
    i = t1
    while i < len(lines) and not lines[i].startswith("## "):
        if lines[i].strip():
            under_table.append(lines[i].strip())
        i += 1

    terms, reports, method = [], [], {}
    sections = re.split(r"^(## .+)$", "\n".join(lines[i:]), flags=re.M)
    for k in range(1, len(sections), 2):
        head, body = sections[k], sections[k + 1]
        tm = re.fullmatch(r"## (\d{4}-\d{2}) term", head)
        if tm:
            pieces = re.split(r"^(### .+)$", body, flags=re.M)
            term_notes = []
            terms.append({"term": tm.group(1), "intro": split_notes(" ".join(l.strip() for l in pieces[0].split("\n") if l.strip()), term_notes), "notes": term_notes})
            for j in range(1, len(pieces), 2):
                r = parse_report(pieces[j], pieces[j + 1].split("\n"), archive_by_url)
                r["term"] = tm.group(1)
                reports.append(r)
        elif head in ("## How reports get answered", "## What we have not verified"):
            notes = []
            _, items = bullets_and_lead(body.strip().split("\n"))
            method[head[3:]] = {"items": [split_notes(x, notes) for x in items], "notes": notes}

    if len(counts) != len(reports):
        fail(f"{len(counts)} table rows but {len(reports)} report sections")
    for c, r in zip(counts, reports):
        if c["term"] != r["term"] or c["short"].split()[0] != r["title"].split()[0]:
            fail(f"table row {c['short']!r} does not match section {r['title']!r}")
        r["short"] = c["short"]
        r["counts"] = {k: c[k] for k in ("n", "refused", "evidence", "citySays")}
    if len(method) != 2:
        fail(f"method sections found: {sorted(method)}")

    out = {
        "source": "San Francisco Civil Grand Jury reports and the city's responses, 2021-22 to 2025-26",
        "read": "2026-10-22",
        "lede": {"paragraphs": lede, "notes": lede_notes},
        "countsNote": under_table,
        "terms": terms,
        "reports": reports,
        "method": method,
    }
    body = json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    for bad in ("](../", "topics/", "notes/", "data/cgj/text"):
        if bad in body:
            fail(f"a repo-relative reference survived: {bad}")
    return body


def main():
    body = build()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != body:
            fail(f"{OUT.relative_to(ROOT)} is out of date; run tools/grand-juries/build-cgj-site.py")
        print("build-cgj-site: up to date")
        return
    if OUT.exists() and OUT.read_text() == body:
        print("build-cgj-site: unchanged")
        return
    OUT.write_text(body)
    print(f"build-cgj-site: wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
