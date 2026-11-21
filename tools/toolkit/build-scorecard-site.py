#!/usr/bin/env python3
"""Copy the options scorecard (data/options/scorecard.json) into the site as site/data/options/scorecard.json, sorted and validated.

    python3 tools/toolkit/build-scorecard-site.py           # write the site copy
    python3 tools/toolkit/build-scorecard-site.py --check   # exit 1 if the site copy is out of date, or the source holds a private key

The working scorecard's source paths, verbatim note quotes and research notes
(the PRIVATE keys below) are not published, in the source file or the site copy.
The site copy keeps every figure and its provenance tag. The toolkit-matrix
block (site/src/toolkit-blocks.mjs) reads the site copy at build time.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(paths.ROOT)
SRC = ROOT / "data/options/scorecard.json"
OUT = ROOT / "site/data/options/scorecard.json"
STUDIES = ROOT / "data/evidence/studies.json"


# Keys that hold private paths, verbatim note quotes or working notes for the next research pass.
PRIVATE = {"source", "topic_note", "quote", "via", "notes", "note", "scope", "count", "area_rule", "measured"}


def scrub(v):
    """Drop every key that names a private path; keep figures, tags and words."""
    if isinstance(v, dict):
        return {k: scrub(x) for k, x in v.items() if k not in PRIVATE}
    if isinstance(v, list):
        return [scrub(x) for x in v]
    if isinstance(v, str):
        # A note path inside a sentence ("per notes/x/y.md, climate plan paragraph") goes, the sentence stays.
        return re.sub(r"\s*\(?(?:per |via )?(?:notes|scratch)/[^\s,;)]+\)?", "", v)
    return v


def validate(d):
    """Stop the build on a row the page can't stand behind: a figure with no source or tag, a range out of order, a study with no grade."""
    graded = {r["id"] for r in json.loads(STUDIES.read_text())["studies"]}
    bad = []
    for o in d["options"]:
        v = o["vmt_reduction"]
        vmt = [v[k] for k in ("annual_miles_low", "annual_miles_central", "annual_miles_high") if v[k] is not None]
        if vmt != sorted(vmt):
            bad.append(f"{o['id']}: miles out of order")
        if vmt and not (v.get("tag") and v.get("grade")):
            bad.append(f"{o['id']}: miles with no tag or grade")
        for f in (v, o["mode_shift_pts"], o["injuries_avoided_per_year"]):
            bad += [f"{o['id']}: study {s} has no row in data/evidence/studies.json" for s in f.get("studies", []) if s not in graded]
        c = o["cost"]
        if c.get("no_setup_priced") and c.get("one_time"):
            bad.append(f"{o['id']}: no_setup_priced with a one-time cost")
        if c.get("tied_to_miles") and None in (v["annual_miles_low"], v["annual_miles_high"]):
            bad.append(f"{o['id']}: tied_to_miles needs both ends of the miles range")
        if o["status"]["state"] == "ignored" and o["status"].get("asked_by"):
            bad.append(f"{o['id']}: nobody's asking, yet it names an asker")
    if bad:
        sys.exit("build-scorecard-site: " + "; ".join(bad))


def private_keys(v, at="$"):
    """Every PRIVATE key left in the source file, by its path: the public source carries none."""
    if isinstance(v, dict):
        return [f"{at}.{k}" for k in v if k in PRIVATE] + [p for k, x in v.items() for p in private_keys(x, f"{at}.{k}")]
    if isinstance(v, list):
        return [p for i, x in enumerate(v) for p in private_keys(x, f"{at}[{i}]")]
    return []


def build():
    d = json.loads(SRC.read_text())
    left = private_keys(d)
    if left:
        sys.exit("build-scorecard-site: data/options/scorecard.json holds private keys: " + ", ".join(left[:10]))
    validate(d)
    out = {k: scrub(v) for k, v in d.items() if k != "options"}
    out["options"] = sorted((scrub(o) for o in d["options"]), key=lambda o: o["id"])
    text = json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if "notes/" in text:
        sys.exit("build-scorecard-site: a notes/ path survived the scrub")
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = build()
    if a.check:
        if not OUT.exists() or OUT.read_text() != text:
            sys.exit("build-scorecard-site: site/data/options/scorecard.json is out of date; run python3 tools/toolkit/build-scorecard-site.py")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUT.exists() or OUT.read_text() != text:
        OUT.write_text(text)


if __name__ == "__main__":
    main()
