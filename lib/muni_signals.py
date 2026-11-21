"""Which SFMTA traffic signals have transit signal priority, for the Muni lever model and the line optimizer.

SFMTA's signal layer (DataSF ybh5-27n2, data/muni-ewt/lever/signals.json) marks a signal equipped when its preempt_pr
field lists "TSP" among its comma-separated tokens ("TSP-Planned" is not equipped). The layer is May 2024 data
(data_as_of 2024-05-28, rowsUpdatedAt 2024-05-31) and hasn't changed since. SFMTA named the intersections it finished
after that in the TSP installation list it gave the Transportation Authority (SFCTA Resolution 25-22, adopted
2024-12-10, Attachment 5, PDF p. 21, "Intersections completed since June 2023 are shown in blue", maps dated October
2024); the three the layer doesn't flag are rows of kind "signal" in data/muni-ewt/optimizer/built_overrides.csv,
their cnn in the stop column, as the line optimizer's pre-send verifier read them [primary — read 2026-11-15 by the
pre-send verifier]. Work after October 2024 isn't published.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, os

ROOT = paths.ROOT
OVERRIDES = os.path.join(ROOT, "data", "muni-ewt", "optimizer", "built_overrides.csv")
LAYER_TSP = 486  # signals the layer flags TSP


def override_cnns():
    with open(OVERRIDES, encoding="utf-8") as f:
        return {str(int(float(r["stop"]))) for r in csv.DictReader(f) if r["kind"] == "signal"}


def has_tsp(rec, extra=None):
    """Whether one signals.json record has priority: the layer's TSP flag, or a named override."""
    extra = override_cnns() if extra is None else extra
    return any(t.strip() == "TSP" for t in (rec.get("preempt_pr") or "").split(",")) or \
        str(rec.get("cnn", "")).split(".")[0] in extra
