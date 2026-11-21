#!/usr/bin/env python3
"""Mirror every SFCTA Board and Vision Zero Committee agenda item since 2019 from SFGovTV's Granicus archive to data/sfcta-board/.

    tools/meetings/fetch-sfcta-board.py                   # since 2019-01-01; fetches only what is new or draft
    tools/meetings/fetch-sfcta-board.py --since 2015-01-01
    tools/meetings/fetch-sfcta-board.py --refetch         # ignore the byte cache

The San Francisco County Transportation Authority allocates Prop K and Prop L
sales-tax money to street projects, and its Board (the eleven Supervisors)
votes each allocation. An allocation names the project and the phase it pays
for, so for a Quick-Build or a streetscape it is often the first dated city
decision. sfcta.org answers every request with a Cloudflare challenge
(checked 2026-09-28), so this reads the agendas SFGovTV publishes on Granicus
instead: view 24 (Full Board) and view 172 (Vision Zero Committee, to 2020).
Committees that stopped meeting before 2019 (Plans and Programs, view 25;
Finance, view 23) are not read.

The agenda is the video index: every item's number and title, not the vote.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.fetch import Fetcher  # noqa: E402
from lib.mirror import Mirror, summary  # noqa: E402
from lib import granicus  # noqa: E402

VIEWS = {24: "Transportation Authority Full Board", 172: "Transportation Authority Vision Zero Committee"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2019-01-01")
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()
    mirror = Mirror("sfcta-board", "San Francisco County Transportation Authority Board",
                    granicus.listing_url(24))
    idx = granicus.mirror_views(mirror, Fetcher("sfcta-board", pause=0.5, refetch=args.refetch), VIEWS, args.since,
                                notes=["sfcta.org sits behind a Cloudflare challenge; agendas are read from SFGovTV's Granicus views 24 and 172.",
                                       "Items carry titles only. Granicus does not publish the vote."])
    print(summary(idx))


if __name__ == "__main__":
    main()
