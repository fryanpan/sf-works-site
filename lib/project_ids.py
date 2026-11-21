"""Every project page address the site has ever published, kept for good.

A project page lives at /transportation/bike/projects/<slug>/ (at /transportation/projects/<slug>/ until 2026-09-29, which still redirects). The slug started as
a hash of the source's project id (Bryan, 2026-09-24: "is the project name slug
stable? If not, please consider using a short random hash instead"), and a
hash alone is stable only while the id is. Ids do move: an SFMTA project first
read from its page (`sfmta-page:<path>`) gains a layer id (`sfmta:<n>`) once
SFMTA maps it, and a feed row can be merged into another. So the addresses are
kept in data/project-ids.json, which is tracked and only ever grows:

  - a known id keeps its slug;
  - a new id that shares a department page with a project that has left the
    list takes that project's slug, and the old id goes in `formerIds`;
  - anything else gets a fresh hash, never one used before;
  - a slug whose project has left the list stays, with `listed: false`, and
    `redirect` naming the listed project that took over its page when there
    is one, or the row it was merged into (a feed row folded into an SFMTA
    project, `feedId`, or a feed job entered twice, `alsoIds`). The site
    builds a page for it either way, so no address breaks;
  - an address from before the hash scheme (the name slugs of 2026-09-22 to
    09-24) is an alias, `{"alias": <slug>}`, and redirects there for good.

`pipeline/transportation-audit.py` (check S1) fails when a slug published at
HEAD is missing from the file, or points at a different project without the
old id in `formerIds`.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import hashlib
import json
import os
import re
import urllib.parse

ROOT = paths.ROOT
PATH = os.path.join(ROOT, "data", "project-ids.json")

# Links that are not a project's own page: the feed row is per id, and would
# tie a project to itself.
NOT_A_PAGE = ("data.sf.gov/resource/",)
# A "program" link (a department's programme page, or the Public Works paving
# map offered as the closest official source) is shared by many jobs, so it
# cannot say which one moved.
SHARED_KINDS = ("program",)


def load(path=PATH):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return {}


def same_page(url):
    """A page address as compared, not as stored: one page under two spellings is one page.

    sfpublicworks.org linked its pages as /index%2Ephp/<slug> until September
    2026 and as /index.php/<slug> since (checked 2026-09-28), so a registry
    entry written before the change would otherwise share no page with the
    project that holds it now, and lose its heir and its redirect.
    """
    p = urllib.parse.urlsplit(urllib.parse.unquote(url.strip()))
    host = re.sub(r"^www\.", "", p.netloc.lower())
    return "%s%s%s" % (host, p.path.rstrip("/"), "?" + p.query if p.query else "")


def pages(project):
    return sorted({l["url"] for l in project.get("links") or ()
                   if l.get("url") and l.get("kind") not in SHARED_KINDS
                   and not any(s in l["url"] for s in NOT_A_PAGE)})


def assign(projects, path=PATH):
    """Set p["slug"] on each project dict (needs id, name, links); return the registry."""
    reg = load(path)
    by_id = {}
    for slug, e in reg.items():
        if "alias" in e:
            continue
        by_id[e["id"]] = slug
        for old in e.get("formerIds", ()):
            by_id.setdefault(old, slug)
    current = {p["id"] for p in projects}
    claimed = set()

    def fresh(pid):
        digest = hashlib.sha1(pid.encode()).hexdigest()
        n = 6
        while digest[:n] in reg:
            n += 1
        return digest[:n]

    # Known ids first, so a new id can only take a slug nobody listed holds.
    new = []
    for p in sorted(projects, key=lambda p: p["id"]):
        slug = by_id.get(p["id"])
        if slug and slug not in claimed:
            p["slug"] = slug
            claimed.add(slug)
            if reg[slug]["id"] != p["id"]:
                reg[slug]["formerIds"] = sorted(set(reg[slug].get("formerIds", [])) | {reg[slug]["id"]})
                reg[slug]["id"] = p["id"]
        else:
            new.append(p)
    for p in new:
        mine = {same_page(u) for u in pages(p)}
        heir = None
        for slug, e in sorted(reg.items()):
            if slug in claimed or "alias" in e or e["id"] in current:
                continue
            if mine & {same_page(u) for u in e.get("pages", ())}:
                heir = slug
                break
        if heir:
            e = reg[heir]
            e["formerIds"] = sorted(set(e.get("formerIds", [])) | {e["id"]})
            e["id"] = p["id"]
            p["slug"] = heir
        else:
            p["slug"] = fresh(p["id"])
            reg[p["slug"]] = {"id": p["id"]}
        claimed.add(p["slug"])

    listed_pages = {}
    merged = {}
    for p in projects:
        # A feed row merged into an SFMTA project carries its id as feedId.
        if p.get("feedId"):
            merged["dotmaps:%s" % p["feedId"]] = p["slug"]
        # A feed job entered twice keeps one row; the other's ids are alsoIds.
        for other in p.get("alsoIds") or ():
            merged[other] = p["slug"]
        e = reg[p["slug"]]
        e.update({"name": p["name"], "pages": pages(p), "listed": True})
        e.pop("redirect", None)
        for u in e["pages"]:
            listed_pages.setdefault(same_page(u), p["slug"])
    for slug, e in reg.items():
        if slug in claimed or "alias" in e:
            continue
        e["listed"] = False
        heirs = sorted({listed_pages[same_page(u)] for u in e.get("pages", ()) if same_page(u) in listed_pages})
        if e["id"] in merged:
            heirs = [merged[e["id"]]]
        if heirs:
            e["redirect"] = heirs[0]
        else:
            e.pop("redirect", None)
    return reg


def save(reg, path=PATH):
    from lib import stable
    stable.write_json(path, {k: reg[k] for k in sorted(reg)}, indent=1, ensure_ascii=False)
