#!/usr/bin/env python3
"""Mirror every Recreation and Park Commission agenda item since 2019 from SFGovTV's Granicus archive to data/rec-park-commission/.

    tools/meetings/fetch-rec-park-commission.py            # since 2019-01-01; fetches only what is new or draft
    tools/meetings/fetch-rec-park-commission.py --since 2015-01-01

The Commission governs the roads and paths inside parks, Golden Gate Park's
John F Kennedy Drive and the Great Highway among them, and awards the park
contracts that rebuild them. Its agendas are on Granicus view 91. The agenda
is the video index: item numbers and titles, not the vote.
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

VIEWS = {91: "Recreation and Park Commission"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2019-01-01")
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()
    mirror = Mirror("rec-park-commission", "Recreation and Park Commission", granicus.listing_url(91))
    idx = granicus.mirror_views(mirror, Fetcher("rec-park-commission", pause=0.5, refetch=args.refetch),
                                VIEWS, args.since,
                                notes=["Items carry titles only. Granicus does not publish the vote."])
    print(summary(idx))


if __name__ == "__main__":
    main()
