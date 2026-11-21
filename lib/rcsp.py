"""Compiled graph searches for lib/school-travel-time.py (lib/rcsp.c), built with the system C compiler and loaded by ctypes.

The C file is compiled once per source version into lib/_build/ (gitignored)
with -O2 -ffp-contract=off, so no multiply-add is fused and every sum rounds
exactly as the Python reference does. `available()` is False when no compiler
is found; the script then falls back to its pure-Python searches.
"""

import ctypes
import hashlib
import os
import subprocess
import sys

import numpy

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "rcsp.c")
BUILD = os.path.join(HERE, "_build")
FLAGS = ["-O2", "-ffp-contract=off", "-fno-fast-math", "-fPIC", "-shared"]

_lib = None
_err = None

P = ctypes.c_void_p
I32, I64, F64 = ctypes.c_int32, ctypes.c_int64, ctypes.c_double
SIGS = {
    "walk_search": [I32, P, P, P, P, I32, P, P, F64, P],
    "lagrange_search": [I32, P, P, P, P, P, F64, F64, F64, F64, I32, P, P, P, P, P, P, I64, P, P, P, P],
    "time_search": [I32, P, P, P, P, P, F64, F64, I32, P, P, P, P, F64, P],
    "exact_best": [I32, P, P, P, P, P, F64, F64, F64, F64, I32, P, P, P, P, P, P,
                   I32, P, P, P, P, P, P, I32, P, I32, F64, F64, P, P, I32, P, P, P],
    # ... nb, ends, wb, hb, f32, hd, lazy, margin, upper, out, osi, k, kt, ksi, order
    "lazy_init": [I32, I32, P, P, P, P, P, F64, F64, I32, P, P, P, P, F64],
}


def _load():
    global _lib, _err
    if _lib is not None or _err is not None:
        return _lib
    src = open(SRC, "rb").read()
    tag = hashlib.sha1(src + " ".join(FLAGS).encode() + sys.platform.encode()).hexdigest()[:12]
    so = os.path.join(BUILD, "rcsp-%s.so" % tag)
    try:
        if not os.path.exists(so):
            os.makedirs(BUILD, exist_ok=True)
            tmp = so + ".%d.tmp" % os.getpid()
            cc = os.environ.get("CC", "cc")
            subprocess.run([cc] + FLAGS + ["-o", tmp, SRC, "-lm"], check=True, capture_output=True)
            os.replace(tmp, so)
        lib = ctypes.CDLL(so)
        for name, args in SIGS.items():
            f = getattr(lib, name)
            f.argtypes = args
            f.restype = ctypes.c_int
        _lib = lib
    except (OSError, subprocess.CalledProcessError) as e:
        _err = e
    return _lib


def available():
    return _load() is not None


def ptr(a):
    return None if a is None else a.ctypes.data


class Graph(object):
    """CSR copy of a walk graph's adjacency, neighbours kept in adj's order."""

    def __init__(self, adj, L):
        self.n = len(adj)
        deg = numpy.fromiter((len(x) for x in adj), dtype=numpy.int64, count=self.n)
        self.indptr = numpy.zeros(self.n + 1, dtype=numpy.int64)
        numpy.cumsum(deg, out=self.indptr[1:])
        self.nbr = numpy.fromiter((v for x in adj for v, _e in x), dtype=numpy.int32, count=int(self.indptr[-1]))
        self.eid = numpy.fromiter((e for x in adj for _v, e in x), dtype=numpy.int32, count=int(self.indptr[-1]))
        self.L = numpy.asarray(L, dtype=numpy.float64)
        self._g = (self.n, ptr(self.indptr), ptr(self.nbr), ptr(self.eid), ptr(self.L))

    def walk(self, seed_nodes, seed_d, cutoff):
        """Shortest walk from seeds (node, metres) to every node within cutoff; INF elsewhere."""
        dist = numpy.full(self.n, numpy.inf)
        sn = numpy.ascontiguousarray(seed_nodes, dtype=numpy.int32)
        sd = numpy.ascontiguousarray(seed_d, dtype=numpy.float64)
        _check(_lib.walk_search(*self._g, len(sn), ptr(sn), ptr(sd), float(cutoff), ptr(dist)))
        return dist

    def lagrange(self, bike, RW, RB, lw, cutoff, seeds, target=None):
        n = self.n
        cost = numpy.full(n, numpy.inf)
        tm = numpy.zeros(n)
        ln = numpy.zeros(n)
        src = numpy.full(n, -1, dtype=numpy.int32)
        nt = 0
        if target is not None:
            target = target.copy()
            nt = int(target.sum())
        _check(_lib.lagrange_search(*self._g, ptr(bike), RW, RB, lw, cutoff, len(seeds.node), ptr(seeds.node),
                                    ptr(seeds.c), ptr(seeds.along), ptr(seeds.e), ptr(seeds.s),
                                    ptr(target), nt, ptr(cost), ptr(tm), ptr(ln), ptr(src)))
        return cost, tm, ln, src

    def time(self, bike, RW, RB, ends, cutoff=numpy.inf):
        dist = numpy.full(self.n, numpy.inf)
        _check(_lib.time_search(*self._g, ptr(bike), RW, RB, len(ends.node), ptr(ends.node), ptr(ends.c),
                                ptr(ends.along), ptr(ends.e), float(cutoff), ptr(dist)))
        return dist

    def lazy(self, slot, bike, RW, RB, ends, cutoff):
        """Start lazy search `slot` (0: walk, bike None; 1: time on `bike`) from a point's ends."""
        # The C side keeps a pointer to bike until the slot is started again; hold the array here.
        self.__dict__.setdefault("_lazy_bike", {})[slot] = bike
        _check(_lib.lazy_init(slot, *self._g, ptr(bike), RW, RB, len(ends.node), ptr(ends.node), ptr(ends.c),
                              ptr(ends.along), ptr(ends.e), float(cutoff)))

    def exact(self, bike, RW, RB, DETOUR, CAP_TOL, schools, Ws, bends, wb, hb, f32, hd, upper, lazy=0, margin=0.0):
        out = numpy.zeros(2)
        osi = ctypes.c_int32(-1)
        r = _lib.exact_best(*self._g, ptr(bike), RW, RB, DETOUR, CAP_TOL, len(schools.off) - 1, ptr(schools.off),
                            ptr(schools.node), ptr(schools.c), ptr(schools.along), ptr(schools.e), ptr(Ws),
                            len(bends.node), ptr(bends.node), ptr(bends.c), ptr(bends.along), ptr(bends.e),
                            ptr(wb), ptr(hb), int(f32), ptr(hd), int(lazy), float(margin), float(upper), ptr(out),
                            ctypes.byref(osi), 0, None, None, None)
        _check(r)
        return (float(out[0]), osi.value, float(out[1])) if r == 1 else None

    def topk(self, bike, RW, RB, DETOUR, CAP_TOL, schools, Ws, bends, k, upper, margin, order=None):
        """The k fastest capped routes to distinct destinations, under upper: [(seconds, destination index)].

        Reads the block's walk and time bound from lazy slots 0 and 1."""
        out = numpy.zeros(2)
        osi = ctypes.c_int32(-1)
        kt = numpy.zeros(k)
        ksi = numpy.zeros(k, dtype=numpy.int32)
        r = _lib.exact_best(*self._g, ptr(bike), RW, RB, DETOUR, CAP_TOL, len(schools.off) - 1, ptr(schools.off),
                            ptr(schools.node), ptr(schools.c), ptr(schools.along), ptr(schools.e), ptr(Ws),
                            len(bends.node), ptr(bends.node), ptr(bends.c), ptr(bends.along), ptr(bends.e),
                            None, None, 0, None, 3, float(margin), float(upper), ptr(out), ctypes.byref(osi),
                            int(k), ptr(kt), ptr(ksi), ptr(order))
        _check(r)
        return list(zip(kt[:r].tolist(), ksi[:r].tolist()))


def _check(r):
    if r < 0:
        raise MemoryError("rcsp: allocation failed (%d)" % r)


class Ends(object):
    """A point's joins to the network, as arrays: node, connector m, along-edge m, edge (and school index)."""

    def __init__(self, ends, school=None):
        self.node = numpy.array([x[0] for x in ends], dtype=numpy.int32)
        self.c = numpy.array([x[1] for x in ends], dtype=numpy.float64)
        self.along = numpy.array([x[2] for x in ends], dtype=numpy.float64)
        self.e = numpy.array([x[3] for x in ends], dtype=numpy.int32)
        if school is not None:
            self.s = numpy.array(school, dtype=numpy.int32)


class Schools(object):
    """Several schools' ends, concatenated, with offsets (CSR)."""

    def __init__(self, ends_lists):
        flat = [x for ends in ends_lists for x in ends]
        e = Ends(flat)
        self.node, self.c, self.along, self.e = e.node, e.c, e.along, e.e
        self.off = numpy.zeros(len(ends_lists) + 1, dtype=numpy.int64)
        numpy.cumsum([len(x) for x in ends_lists], out=self.off[1:])
