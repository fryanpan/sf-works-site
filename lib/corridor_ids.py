"""Stable ids for the school case study's plan corridors, kept in data/school-case/corridor-ids.json.

A corridor is a run of North Star blocks on one street that isn't all-ages
today (lib/school-travel-time.py's group_gaps), and the case study page
puts its id in a shareable address (?c=). Its id was "c" plus its lowest CNN,
which moves when a block of the run is built and the run splits. So the ids
live in a tracked registry that only grows:

  - a run whose blocks are exactly a registered id's keeps that id;
  - otherwise each registered id goes to the run holding most of its blocks
    (ties to the run with the lower lowest CNN), so when a run splits the
    larger half keeps the id and the other half gets a new one;
  - a run that collects several ids keeps the one it holds most blocks of,
    and each other becomes {"alias": <id>}, so an old address still opens it;
  - a run holding no registered block gets "c" plus its lowest CNN, or that
    with "-2", "-3" and so on if the id was ever used;
  - an id none of whose blocks is still a gap (all built, or dropped from the
    plan) stays, with listed: false.

Not data/project-ids.json (lib/project_ids.py): that registry holds
the slugs of project pages, matched by a department's own project id and its
page links. A corridor has neither, only a set of centerline blocks, and its
ids never become a page, so mixing the two would let one namespace take the
other's ids.

    from lib import corridor_ids
    ids, reg = corridor_ids.assign([["123000", "124000"], ...], names=["Mansell St", ...])
    corridor_ids.save(reg)
    corridor_ids.aliases(reg)   # {old id: the id it now resolves to}
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import json
import os

ROOT = paths.ROOT
PATH = os.path.join(ROOT, "data", "school-case", "corridor-ids.json")


def load(path=PATH):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _norm(run):
    return sorted({str(int(float(c))) for c in run}, key=int)


def assign(runs, names=None, path=PATH, reg=None):
    """The id of each run (a list of CNNs), in order, and the updated registry."""
    reg = load(path) if reg is None else reg
    runs = [_norm(r) for r in runs]
    names = names or [None] * len(runs)
    owner = {}
    for i, r in enumerate(runs):
        for c in r:
            owner[c] = i
    live = {k: e for k, e in reg.items() if "alias" not in e and "block" not in e}
    by_set = {tuple(e["cnns"]): k for k, e in live.items()}
    out = [by_set.get(tuple(r)) for r in runs]
    taken = {k for k in out if k}
    claims = collections.defaultdict(list)
    for k in sorted(live):
        if k in taken:
            continue
        cnt = collections.Counter(owner[c] for c in live[k]["cnns"] if c in owner)
        if not cnt:
            continue
        i = max(cnt, key=lambda j: (cnt[j], -int(runs[j][0])))
        claims[i].append((cnt[i], k))
    for i in sorted(claims):
        cl = sorted(claims[i], key=lambda t: (-t[0], t[1]))
        if out[i] is None:
            out[i] = cl[0][1]
            cl = cl[1:]
        for _n, k in cl:
            reg[k] = {"alias": out[i], "cnns": live[k]["cnns"]}
    used = set(reg)
    for i, r in enumerate(runs):
        if out[i] is not None:
            continue
        base = "c%s" % r[0]
        k, n = base, 1
        while k in used:
            n += 1
            k = "%s-%d" % (base, n)
        out[i] = k
        used.add(k)
    assert len(set(out)) == len(out), "corridor ids repeat"
    for i, r in enumerate(runs):
        e = {"cnns": r, "listed": True}
        if names[i]:
            e["street"] = names[i]
        reg[out[i]] = e
    mine = set(out)
    for k, e in reg.items():
        if "alias" not in e and "block" not in e and k not in mine:
            e["listed"] = False
    return out, reg


def register_blocks(reg, blocks):
    """Add each plan block's id, "b" plus its CNN, which never changes: {cnn: street}. Entries only grow."""
    for cnn, street in sorted(blocks.items()):
        k = "b%s" % int(float(cnn))
        if k not in reg:
            reg[k] = {"block": str(int(float(cnn))), "street": street}
    return reg


def aliases(reg):
    """{id: the id it resolves to} for every alias, chains followed."""
    out = {}
    for k, e in reg.items():
        if "alias" not in e:
            continue
        t, seen = e["alias"], {k}
        while t in reg and "alias" in reg[t] and t not in seen:
            seen.add(t)
            t = reg[t]["alias"]
        out[k] = t
    return out


def save(reg, path=PATH):
    from lib import stable
    stable.write_json(path, {k: reg[k] for k in sorted(reg)}, indent=1, ensure_ascii=False)


def _selftest():
    reg = {}
    ids, reg = assign([["10", "20", "30"], ["50"]], reg=reg)
    assert ids == ["c10", "c50"], ids
    # Block 20 is built and the run splits into halves of one block each: the tie goes to the lower CNN.
    ids, reg = assign([["10"], ["30"], ["50"]], reg=reg)
    assert ids == ["c10", "c30", "c50"], ids
    # A split with a larger half: c100's blocks 100, 110 | 130, 140, 150.
    reg = {}
    ids, reg = assign([["100", "110", "120", "130", "140", "150"]], reg=reg)
    ids, reg = assign([["100", "110"], ["130", "140", "150"]], reg=reg)
    assert ids == ["c100-2", "c100"], ids
    # Two runs merge: the one it holds more of keeps its id, the other aliases to it.
    reg = {}
    ids, reg = assign([["1", "2", "3"], ["7", "8"]], reg=reg)
    ids, reg = assign([["1", "2", "3", "5", "7", "8"]], reg=reg)
    assert ids == ["c1"] and reg["c7"]["alias"] == "c1" and aliases(reg) == {"c7": "c1"}, (ids, reg)
    # Idempotent.
    before = json.dumps(reg, sort_keys=True)
    ids2, reg = assign([["1", "2", "3", "5", "7", "8"]], reg=reg)
    assert ids2 == ids and json.dumps(reg, sort_keys=True) == before
    # Block ids sit beside corridor ids and never claim a run.
    reg = {}
    ids, reg = assign([["1", "2"]], reg=reg)
    register_blocks(reg, {"1": "A St"})
    ids, reg = assign([["1", "2"]], reg=reg)
    assert ids == ["c1"] and reg["b1"] == {"block": "1", "street": "A St"}, reg
    print("corridor_ids selftest ok")


if __name__ == "__main__":
    _selftest()
