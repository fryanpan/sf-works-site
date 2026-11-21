#!/usr/bin/env python3
"""Fail when a file of 1 MB or more is not stored in Git LFS (ADR 0002, "Big data files go in Git LFS").

    python3 pipeline/check-large-files.py            # check every tracked file, and untracked ones git doesn't ignore
    python3 pipeline/check-large-files.py --write    # add a line to .gitattributes for each big file it lacks

1 MB here is 1,048,576 bytes. A file is covered when `git check-attr filter` reports `lfs` for it, which reads
.gitattributes and needs no git-lfs install. Each big file is named on its own line in .gitattributes, so a new
big file fails until someone adds it there on purpose (--write does that). Exits 1 on any uncovered file.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 1 << 20
ATTRS = os.path.join(ROOT, ".gitattributes")
LINE = "%s filter=lfs diff=lfs merge=lfs -text\n"


def git(*args, stdin=None):
    return subprocess.run(["git", *args], cwd=ROOT, input=stdin, capture_output=True, text=True, check=True).stdout


def big_files():
    names = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    out = []
    for n in sorted(set(filter(None, names))):
        p = os.path.join(ROOT, n)
        if os.path.isfile(p) and not os.path.islink(p) and os.path.getsize(p) >= LIMIT:
            out.append(n)
    return out


def uncovered(files):
    if not files:
        return []
    res = git("check-attr", "-z", "--stdin", "filter", stdin="\0".join(files) + "\0").split("\0")
    triples = [res[i:i + 3] for i in range(0, len(res) - 2, 3)]
    return [path for path, _attr, value in triples if value != "lfs"]


def main():
    big = big_files()
    bad = uncovered(big)
    if "--write" in sys.argv and bad:
        with open(ATTRS, "a") as fh:
            for n in bad:
                fh.write(LINE % n.replace(" ", "[[:space:]]"))
        print("check-large-files: added %d file(s) to .gitattributes" % len(bad))
        bad = uncovered(big)
    if bad:
        print("check-large-files: %d file(s) of 1 MB or more are not in Git LFS:" % len(bad))
        for n in bad:
            print("  %s (%.1f MB)" % (n, os.path.getsize(os.path.join(ROOT, n)) / LIMIT))
        print("Add each to .gitattributes (python3 pipeline/check-large-files.py --write), or make it smaller.")
        sys.exit(1)
    print("check-large-files: %d file(s) of 1 MB or more, all in Git LFS" % len(big))


if __name__ == "__main__":
    main()
