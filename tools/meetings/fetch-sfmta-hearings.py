#!/usr/bin/env python3
"""Mirror every item of every SFMTA engineering public hearing since the archive begins (August 2019), with its decision, to data/sfmta-hearings/.

    tools/meetings/fetch-sfmta-hearings.py                # fetches only what is new or draft
    tools/meetings/fetch-sfmta-hearings.py --pages 12     # walk more archive pages

tools/meetings/sfmta-hearings.py keeps only items that name a bike word. This keeps
every item: an ESTABLISH TOW-AWAY NO STOPPING that is part of a transit
project names the project and not a bike word, and it is still that project's
dated decision. The parsing is sfmta-hearings.py's own, imported rather than
copied, so the two readers cannot drift.

Per hearing the results order (the "Streets Division Directive Order") is
read when it is posted, which gives each item's decision. Before it is posted
the agenda PDF is read instead and the meeting stays a draft, to be fetched
again. The archive at https://www.sfmta.com/past-meetings-and-events/2617
starts at 2019-08-16; the script cannot read further back than SFMTA lists.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lib.fetch import Fetcher, pdf_text  # noqa: E402
from lib.mirror import Mirror, settled, summary  # noqa: E402

hear = paths.load("sfmta-hearings.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2019-01-01")
    ap.add_argument("--pages", type=int, default=10, help="archive pages to walk, about 20 hearings a page")
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()
    today = dt.date.today()
    fetcher = Fetcher("sfmta-hearings", pause=1.0, refetch=args.refetch)
    # The archive listing and a hearing's own page change as documents are
    # posted, so they are always read fresh; a PDF, once posted, is cached.
    hear.get = lambda url, binary=False, tries=3: fetcher.get(url, binary=binary, cache="/media/" in url)

    mirror = Mirror("sfmta-hearings", "SFMTA engineering public hearings", hear.ARCHIVE)
    listed, got, kept = [], 0, 0
    by_date = {}
    for h in hear.hearings(args.pages):
        by_date.setdefault(h["date"], []).append(h)
    for date in sorted(by_date):
        if date < args.since:
            continue
        mid = "hearing"
        # SFMTA lists some hearings under two pages ("...-february-19-2021"
        # and "...-2021-0"), in an order that changes between reads, so the
        # index flipped between them run to run. Pages are tried in sorted
        # order, and a final meeting names the page it was read from.
        by_date[date].sort(key=lambda h: h["page"])
        row = {"date": date, "id": mid, "committee": "Engineering public hearing",
               "page": by_date[date][0]["page"]}
        listed.append(row)
        if mirror.is_final(date, mid):
            row["page"] = (mirror.read(date, mid).get("sources") or {}).get("page") or row["page"]
            row["outcome"] = "mirrored"
            kept += 1
            continue
        docs, errors = None, []
        for h in by_date[date]:
            try:
                docs = hear.documents(h["page"])
                row["page"] = h["page"]
                break
            except Exception as exc:
                errors.append("%s: %s" % (type(exc).__name__, exc))
        if docs is None:
            row.update(outcome="unreachable", reason="; ".join(errors))
            continue
        text, form = None, None
        if docs.get("results"):
            try:
                text = hear.pdf_text(docs["results"])
                form = "results"
            except Exception as exc:
                errors.append("results: %s" % exc)
        if not text and docs.get("agenda"):
            text = hear.pdf_text(docs["agenda"])
            form = "agenda"
        if not text:
            row.update(outcome="empty", reason="no readable results order or agenda")
            continue
        order = hear.ORDER_NO.search(text) if form == "results" else None
        items = [{"no": r["no"], "title": r["head"], "district": r["district"], "approver": r["approver"],
                  "decision": r["decision"], "comments": r["comments"], "text": r["text"][:900]}
                 for r in hear.items(text)]
        if not items:
            row.update(outcome="empty", reason="%s parsed to no items" % form)
            continue
        rec = {"committee": "Engineering public hearing", "date": date, "id": mid,
               "status": "final" if (form == "results" or settled(date, today=today)) else "draft",
               "sources": {"page": row["page"], "results": docs.get("results"), "agenda": docs.get("agenda")},
               "order": order.group(1) if order else None, "form": form,
               "fetched": today.isoformat(), "items": items}
        mirror.write(rec)
        row["outcome"] = "mirrored"
        got += 1
        print("  %s: %d items from the %s" % (date, len(items), form))
    idx = mirror.write_index(listed, args.since,
                             notes=["The archive starts at 2019-08-16. A hearing whose results order is not yet posted "
                                    "is mirrored from its agenda, without decisions, and fetched again next run."])
    print("  fetched %d, already final %d, %d requests" % (got, kept, fetcher.requests))
    print(summary(idx))


if __name__ == "__main__":
    main()
