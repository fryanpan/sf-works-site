/* Compiled inner loops for lib/school-travel-time.py: the shortest walk, the
 * Lagrangian pass, the uncapped fastest time, and the exact label-setting search
 * for the fastest route under a length cap.
 *
 * Each function is a line-for-line port of the Python function of the same name
 * in school-travel-time.py, which stays as the reference (--pure). The results
 * are bit-identical to it, which rests on three things:
 *   - every sum is written in the same order as the Python expression, and the
 *     file is compiled with -ffp-contract=off, so no a*b+c is fused into one
 *     rounding (clang fuses by default on arm64);
 *   - each priority queue orders its entries by the same tuple Python's heapq
 *     compares, (cost, node) or (key, t, m, node), and a heap under a total
 *     order pops in the same sequence whatever its internal layout;
 *   - neighbours are visited in the same order (edge index, as Net builds adj).
 * Built by lib/rcsp.py with the system C compiler; no Python dependency.
 */
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* The f32 mode rounds each float operation to 32 bits, as numpy does; that
   needs float arithmetic without excess precision. */
_Static_assert(FLT_EVAL_METHOD == 0, "float arithmetic must not use excess precision");

/* ---- heaps ------------------------------------------------------------- */

typedef struct { double k; int32_t u; } E2;
typedef struct { double k, t, m; int32_t u; } E4;

static inline int lt2(const E2 *a, const E2 *b) {
    return a->k < b->k || (a->k == b->k && a->u < b->u);
}
static inline int lt4(const E4 *a, const E4 *b) {
    if (a->k != b->k) return a->k < b->k;
    if (a->t != b->t) return a->t < b->t;
    if (a->m != b->m) return a->m < b->m;
    return a->u < b->u;
}

typedef struct { E2 *a; int64_t n, cap; } H2;
typedef struct { E4 *a; int64_t n, cap; } H4;

static int h2_push(H2 *h, double k, int32_t u) {
    if (h->n == h->cap) {
        int64_t c = h->cap ? h->cap * 2 : 1024;
        E2 *na = (E2 *)realloc(h->a, c * sizeof(E2));
        if (!na) return -1;
        h->a = na; h->cap = c;
    }
    int64_t i = h->n++;
    E2 x = {k, u};
    while (i > 0) {
        int64_t p = (i - 1) >> 1;
        if (!lt2(&x, &h->a[p])) break;
        h->a[i] = h->a[p]; i = p;
    }
    h->a[i] = x;
    return 0;
}
static E2 h2_pop(H2 *h) {
    E2 top = h->a[0], x = h->a[--h->n];
    int64_t i = 0, n = h->n;
    for (;;) {
        int64_t c = 2 * i + 1;
        if (c >= n) break;
        if (c + 1 < n && lt2(&h->a[c + 1], &h->a[c])) c++;
        if (!lt2(&h->a[c], &x)) break;
        h->a[i] = h->a[c]; i = c;
    }
    if (n) h->a[i] = x;
    return top;
}
static int h4_push(H4 *h, double k, double t, double m, int32_t u) {
    if (h->n == h->cap) {
        int64_t c = h->cap ? h->cap * 2 : 1024;
        E4 *na = (E4 *)realloc(h->a, c * sizeof(E4));
        if (!na) return -1;
        h->a = na; h->cap = c;
    }
    int64_t i = h->n++;
    E4 x = {k, t, m, u};
    while (i > 0) {
        int64_t p = (i - 1) >> 1;
        if (!lt4(&x, &h->a[p])) break;
        h->a[i] = h->a[p]; i = p;
    }
    h->a[i] = x;
    return 0;
}
static E4 h4_pop(H4 *h) {
    E4 top = h->a[0], x = h->a[--h->n];
    int64_t i = 0, n = h->n;
    for (;;) {
        int64_t c = 2 * i + 1;
        if (c >= n) break;
        if (c + 1 < n && lt4(&h->a[c + 1], &h->a[c])) c++;
        if (!lt4(&h->a[c], &x)) break;
        h->a[i] = h->a[c]; i = c;
    }
    if (n) h->a[i] = x;
    return top;
}

/* Per-process scratch, kept between calls (each forked worker has its own). */
static H2 g_h2;
static H4 g_h4;

/* ---- walk_search / walk_array ------------------------------------------ */

/* dist: n doubles, filled with INFINITY by the caller. seeds as (node, d = c + along). */
int walk_search(int32_t n, const int64_t *indptr, const int32_t *nbr, const int32_t *eid, const double *L,
                int32_t ns, const int32_t *snode, const double *sd, double cutoff, double *dist) {
    H2 *h = &g_h2; h->n = 0;
    for (int32_t i = 0; i < ns; i++) {
        int32_t node = snode[i];
        if (sd[i] < dist[node]) { dist[node] = sd[i]; if (h2_push(h, sd[i], node)) return -1; }
    }
    while (h->n) {
        E2 x = h2_pop(h);
        double d = x.k; int32_t u = x.u;
        if (d > dist[u]) continue;
        for (int64_t j = indptr[u]; j < indptr[u + 1]; j++) {
            int32_t v = nbr[j];
            double nd = d + L[eid[j]];
            if (nd <= cutoff && nd < dist[v]) { dist[v] = nd; if (h2_push(h, nd, v)) return -1; }
        }
    }
    return 0;
}

/* ---- lagrange_search ----------------------------------------------------- */

/* cost filled INF, tm/ln 0, src -1 by the caller. seeds (node, c, along, edge, school).
 * target: NULL or an n-byte mask; ntarget its count (stop once all are settled). */
int lagrange_search(int32_t n, const int64_t *indptr, const int32_t *nbr, const int32_t *eid, const double *L,
                    const uint8_t *bike, double RW, double RB, double lw, double cutoff,
                    int32_t ns, const int32_t *snode, const double *sc, const double *salong, const int32_t *se,
                    const int32_t *ss, uint8_t *target, int64_t ntarget,
                    double *cost, double *tm, double *ln, int32_t *src) {
    for (int32_t i = 0; i < ns; i++) {
        int32_t node = snode[i];
        double c = sc[i], along = salong[i];
        double t = c * RW + along * (bike[se[i]] ? RB : RW);
        double m = c + along;
        double k = t + lw * m;
        if (k < cost[node]) { cost[node] = k; tm[node] = t; ln[node] = m; src[node] = ss[i]; }
    }
    H2 *h = &g_h2; h->n = 0;
    for (int32_t u = 0; u < n; u++)
        if (cost[u] < INFINITY) { if (h2_push(h, cost[u], u)) return -1; }
    int64_t left = ntarget;
    while (h->n) {
        E2 x = h2_pop(h);
        double k = x.k; int32_t u = x.u;
        if (k > cost[u]) continue;
        if (target) {
            if (target[u]) { target[u] = 0; left--; }
            if (!left) break;
        }
        double tu = tm[u], lu = ln[u]; int32_t su = src[u];
        for (int64_t j = indptr[u]; j < indptr[u + 1]; j++) {
            int32_t v = nbr[j], e = eid[j];
            double le = L[e];
            double te = le * (bike[e] ? RB : RW);
            double nk = k + te + lw * le;
            if (nk < cost[v] && nk <= cutoff) {
                cost[v] = nk; tm[v] = tu + te; ln[v] = lu + le; src[v] = su;
                if (h2_push(h, nk, v)) return -1;
            }
        }
    }
    return 0;
}

/* ---- time_array ---------------------------------------------------------- */

int time_search(int32_t n, const int64_t *indptr, const int32_t *nbr, const int32_t *eid, const double *L,
                const uint8_t *bike, double RW, double RB,
                int32_t ns, const int32_t *snode, const double *sc, const double *salong, const int32_t *se,
                double cutoff, double *dist) {
    H2 *h = &g_h2; h->n = 0;
    for (int32_t i = 0; i < ns; i++) {
        int32_t node = snode[i];
        double t = sc[i] * RW + salong[i] * (bike[se[i]] ? RB : RW);
        if (t < dist[node]) { dist[node] = t; if (h2_push(h, t, node)) return -1; }
    }
    while (h->n) {
        E2 x = h2_pop(h);
        double d = x.k; int32_t u = x.u;
        if (d > dist[u]) continue;
        for (int64_t j = indptr[u]; j < indptr[u + 1]; j++) {
            int32_t v = nbr[j], e = eid[j];
            double nd = d + L[e] * (bike[e] ? RB : RW);
            if (nd <= cutoff && nd < dist[v]) { dist[v] = nd; if (h2_push(h, nd, v)) return -1; }
        }
    }
    return 0;
}

/* ---- lazy searches --------------------------------------------------------- */

/* A shortest-walk or fastest-time search from one block's ends that settles
 * nodes only as far as queries need. A query for node u runs the search until
 * u is settled, or the queue is empty (u lies past the cutoff: INFINITY). A
 * Dijkstra distance does not depend on the order ties are settled in, so each
 * value is the one walk_search / time_search would return with the same
 * seeds and cutoff; the search just stops early. refine_block keeps two: slot 0
 * the walk (for the detour ellipse), slot 1 the time on one network (for A*). */
typedef struct {
    double *dist; uint8_t *done; int32_t *touched;
    int64_t ntouched; int32_t n;
    H2 h;
    const int64_t *indptr; const int32_t *nbr, *eid; const double *L;
    const uint8_t *bike; double RW, RB, cutoff;
} Lazy;
static Lazy g_lazy[2];

int lazy_init(int32_t slot, int32_t n, const int64_t *indptr, const int32_t *nbr, const int32_t *eid, const double *L,
              const uint8_t *bike, double RW, double RB,
              int32_t ns, const int32_t *snode, const double *sc, const double *salong, const int32_t *se,
              double cutoff) {
    Lazy *z = &g_lazy[slot];
    if (z->n < n) {
        free(z->dist); free(z->done); free(z->touched);
        z->dist = (double *)malloc((size_t)n * sizeof(double));
        z->done = (uint8_t *)malloc((size_t)n);
        z->touched = (int32_t *)malloc((size_t)n * sizeof(int32_t));
        if (!z->dist || !z->done || !z->touched) { z->n = 0; return -1; }
        for (int32_t i = 0; i < n; i++) { z->dist[i] = INFINITY; z->done[i] = 0; }
        z->n = n; z->ntouched = 0;
    }
    for (int64_t i = 0; i < z->ntouched; i++) { z->dist[z->touched[i]] = INFINITY; z->done[z->touched[i]] = 0; }
    z->ntouched = 0;
    z->h.n = 0;
    z->indptr = indptr; z->nbr = nbr; z->eid = eid; z->L = L;
    z->bike = bike; z->RW = RW; z->RB = RB; z->cutoff = cutoff;
    for (int32_t i = 0; i < ns; i++) {
        int32_t node = snode[i];
        /* The seeds exactly as walk_search (c + along) and time_search compute them. */
        double d = bike ? sc[i] * RW + salong[i] * (bike[se[i]] ? RB : RW) : sc[i] + salong[i];
        if (d < z->dist[node]) {
            if (z->dist[node] == INFINITY) z->touched[z->ntouched++] = node;
            z->dist[node] = d;
            if (h2_push(&z->h, d, node)) return -1;
        }
    }
    return 0;
}

/* The settled distance of u, or INFINITY past the cutoff; -1 (as NaN) never. */
static double lazy_get(Lazy *z, int32_t u, int *err) {
    while (!z->done[u]) {
        if (!z->h.n) return INFINITY;
        E2 x = h2_pop(&z->h);
        double d = x.k; int32_t w = x.u;
        if (d > z->dist[w] || z->done[w]) continue;
        z->done[w] = 1;
        for (int64_t j = z->indptr[w]; j < z->indptr[w + 1]; j++) {
            int32_t v = z->nbr[j], e = z->eid[j];
            double nd = d + (z->bike ? z->L[e] * (z->bike[e] ? z->RB : z->RW) : z->L[e]);
            if (nd <= z->cutoff && nd < z->dist[v]) {
                if (z->dist[v] == INFINITY) z->touched[z->ntouched++] = v;
                z->dist[v] = nd;
                if (h2_push(&z->h, nd, v)) { *err = 1; return INFINITY; }
            }
        }
    }
    return z->dist[u];
}

/* ---- exact_best ---------------------------------------------------------- */

/* Label store: per node a singly linked list of non-dominated (t, m) labels. */
static int32_t *g_head = NULL;      /* n, -1 = empty */
static int32_t *g_tfirst = NULL;    /* n: first of the block's ends at this node, -1 = none */
static int32_t g_head_n = 0;
static int32_t *g_touched = NULL;   /* nodes whose head was set this school */
static int64_t g_ntouched = 0, g_touched_cap = 0;
static double *g_lt = NULL, *g_lm = NULL;
static int32_t *g_lnext = NULL;
static int64_t g_nl = 0, g_lcap = 0;

static int ensure_nodes(int32_t n) {
    if (g_head_n >= n) return 0;
    free(g_head);
    free(g_tfirst);
    g_head = (int32_t *)malloc((size_t)n * sizeof(int32_t));
    g_tfirst = (int32_t *)malloc((size_t)n * sizeof(int32_t));
    if (!g_head || !g_tfirst) return -1;
    for (int32_t i = 0; i < n; i++) g_head[i] = g_tfirst[i] = -1;
    g_head_n = n;
    return 0;
}
static int label_new(double t, double m) {
    if (g_nl == g_lcap) {
        int64_t c = g_lcap ? g_lcap * 2 : 4096;
        double *a = (double *)realloc(g_lt, c * sizeof(double));
        if (!a) return -1;
        g_lt = a;
        a = (double *)realloc(g_lm, c * sizeof(double));
        if (!a) return -1;
        g_lm = a;
        int32_t *b = (int32_t *)realloc(g_lnext, c * sizeof(int32_t));
        if (!b) return -1;
        g_lnext = b;
        g_lcap = c;
    }
    if (g_nl >= INT32_MAX) return -1;  /* label ids are int32 */
    g_lt[g_nl] = t; g_lm[g_nl] = m; g_lnext[g_nl] = -1;
    return (int)(g_nl++);
}
static int touch(int32_t u) {
    if (g_ntouched == g_touched_cap) {
        int64_t c = g_touched_cap ? g_touched_cap * 2 : 4096;
        int32_t *a = (int32_t *)realloc(g_touched, c * sizeof(int32_t));
        if (!a) return -1;
        g_touched = a; g_touched_cap = c;
    }
    g_touched[g_ntouched++] = u;
    return 0;
}

/* Schools as CSR over their ends: soff[nsch+1]; per end (node, c, along, edge).
 * Ws[si]: shortest walk from this block to school si (INFINITY: none).
 * Block ends (bnode, bc, balong, be), nb of them, in the Python list's order.
 * wb: n floats; hb: n floats or NULL. Output: out[0] = t, out[1] = m, *osi = school; returns 1 if found,
 * 0 if not, -1 on allocation failure.
 *
 * f32 reproduces the Python caller that passes wb and hb as numpy float32 arrays
 * (gap_eval): there, under NumPy 2's promotion rules (NEP 50), a Python float plus a
 * float32 is a float32, and a float32 compared with a Python float casts the
 * Python float to float32. So the key, the ellipse test and the best-so-far
 * tests round to float32 exactly where the Python does. Without f32 (refine_block,
 * wb a list of Python floats, no hb) every value is a double.
 *
 * hd (used only without f32; may be NULL): a lower bound, in seconds, on the time
 * from each node to the block, which orders the search and prunes it (A*). It
 * never changes the answer, only how much is searched: a label is dropped only
 * when its time plus the bound cannot beat the best so far, and the caller
 * lowers the bound by a margin far above rounding error, so no float rounding
 * can make it exceed the true remaining time.
 *
 * lazy (without f32): bit 1 reads wb from lazy slot 0 (the walk, rounded to
 * float32 as walk_array stores it) instead of the wb array; bit 2 reads hd from
 * slot 1 (the time, less hd_margin, floored at 0) instead of the hd array.
 *
 * k > 0 asks instead for the k fastest schools (the k nearest destinations of a
 * type): each school's own fastest capped time is searched for with the k-th
 * best so far (or upper) as its bound, and kept in kt/ksi, sorted by time and
 * then school index. The return value is how many were found (at most k).
 * order (or NULL): the order to try schools in; nearest on foot first lets the
 * k-th best fall early and prune the rest. The order decides only between
 * destinations at exactly equal times (the first tried is kept); the caller
 * derives it from walks alone, so it is the same on every network. */
int exact_best(int32_t n, const int64_t *indptr, const int32_t *nbr, const int32_t *eid, const double *L,
               const uint8_t *bike, double RW, double RB, double DETOUR, double CAP_TOL,
               int32_t nsch, const int64_t *soff, const int32_t *snode, const double *sc, const double *salong,
               const int32_t *se, const double *Ws,
               int32_t nb, const int32_t *bnode, const double *bc, const double *balong, const int32_t *be,
               const float *wb, const float *hb, int32_t f32, const double *hd, int32_t lazy, double hd_margin,
               double upper, double *out, int32_t *osi, int32_t k, double *kt, int32_t *ksi, const int32_t *order) {
    if (ensure_nodes(n)) return -1;
    double best = upper;
    int found = 0, nfound = 0;
    double kth = upper;
    static double *tt = NULL, *mm = NULL;
    static int32_t *tnext = NULL;
    static int32_t ncap = 0;
    if (nb > ncap) {
        double *a = (double *)realloc(tt, (size_t)nb * sizeof(double));
        if (!a) return -1;
        tt = a;
        a = (double *)realloc(mm, (size_t)nb * sizeof(double));
        if (!a) return -1;
        mm = a;
        int32_t *b = (int32_t *)realloc(tnext, (size_t)nb * sizeof(int32_t));
        if (!b) return -1;
        tnext = b;
        ncap = nb;
    }
    for (int32_t i = 0; i < nb; i++) {
        tt[i] = bc[i] * RW + balong[i] * (bike[be[i]] ? RB : RW);
        mm[i] = bc[i] + balong[i];
    }
    /* Per node, the block's ends there, in list order (Python's target[node]). */
    for (int32_t i = nb - 1; i >= 0; i--) {
        tnext[i] = g_tfirst[bnode[i]];
        g_tfirst[bnode[i]] = i;
    }
    int rc = 0, err = 0;
    Lazy *zw = (lazy & 1) ? &g_lazy[0] : NULL, *zh = (lazy & 2) ? &g_lazy[1] : NULL;
#define WB(u) (zw ? (double)(float)lazy_get(zw, (u), &err) : (double)wb[u])
#define HD(u) (zh ? fmax(lazy_get(zh, (u), &err) - hd_margin, 0.0) : (hd ? hd[u] : 0.0))
    H4 *h = &g_h4;
    for (int32_t oi = 0; oi < nsch; oi++) {
        int32_t si = order ? order[oi] : oi;
        double W = Ws[si];
        double school_t = INFINITY;
        if (k > 0) best = kth;
        if (W == INFINITY || W * RB >= best) continue;
        double cap = DETOUR * W + CAP_TOL;
        h->n = 0;
        g_nl = 0;
        for (int64_t i = 0; i < g_ntouched; i++) g_head[g_touched[i]] = -1;
        g_ntouched = 0;
        for (int64_t i = soff[si]; i < soff[si + 1]; i++) {
            int32_t node = snode[i];
            double t0 = sc[i] * RW + salong[i] * (bike[se[i]] ? RB : RW);
            double k0 = f32 ? (double)((float)t0 + hb[node]) : t0 + HD(node);
            if (h4_push(h, k0, t0, sc[i] + salong[i], node)) { rc = -1; goto done; }
        }
        while (h->n) {
            E4 x = h4_pop(h);
            double t = x.t, m = x.m; int32_t u = x.u;
            if (f32 ? ((float)x.k >= (float)best) : (x.k >= best)) break;
            if (f32 ? ((float)m + wb[u] > (float)cap) : (m + WB(u) > cap)) continue;
            int dom = 0;
            for (int32_t l = g_head[u]; l >= 0; l = g_lnext[l])
                if (g_lt[l] <= t && g_lm[l] <= m) { dom = 1; break; }
            if (dom) continue;
            /* Drop the labels the new one beats on both, then add it. */
            /* Allocate first: label_new may move g_lnext, which pp points into. */
            int nl = label_new(t, m);
            if (nl < 0) { rc = -1; goto done; }
            int32_t *pp = &g_head[u];
            int was_empty = (*pp < 0);
            while (*pp >= 0) {
                int32_t l = *pp;
                if (t <= g_lt[l] && m <= g_lm[l]) *pp = g_lnext[l];
                else pp = &g_lnext[l];
            }
            *pp = nl;
            if (was_empty && touch(u)) { rc = -1; goto done; }
            for (int32_t i = g_tfirst[u]; i >= 0; i = tnext[i]) {
                if (m + mm[i] <= cap && t + tt[i] < best) {
                    best = t + tt[i]; found = 1; school_t = best;
                    out[0] = t + tt[i]; out[1] = m + mm[i]; *osi = si;
                }
            }
            for (int64_t j = indptr[u]; j < indptr[u + 1]; j++) {
                int32_t v = nbr[j], e = eid[j];
                double le = L[e];
                double nt = t + le * (bike[e] ? RB : RW), nm = m + le;
                int ok;
                double nk;
                if (f32) {
                    float k32 = (float)nt + hb[v];
                    nk = (double)k32;
                    ok = k32 < (float)best && (float)nm + wb[v] <= (float)cap;
                } else {
                    nk = nt + HD(v);
                    ok = nk < best && nm + WB(v) <= cap;
                }
                if (ok) {
                    if (h4_push(h, nk, nt, nm, v)) { rc = -1; goto done; }
                }
            }
        }
        if (k > 0 && school_t < INFINITY) {
            /* Insert (school_t, si) into the sorted top-k list. */
            int32_t j = nfound < k ? nfound++ : k - 1;
            while (j > 0 && (kt[j - 1] > school_t || (kt[j - 1] == school_t && ksi[j - 1] > si))) {
                kt[j] = kt[j - 1]; ksi[j] = ksi[j - 1]; j--;
            }
            kt[j] = school_t; ksi[j] = si;
            if (nfound == k) kth = kt[k - 1];
        }
    }
    rc = err ? -1 : (k > 0 ? nfound : found);
#undef WB
#undef HD
done:
    for (int32_t i = 0; i < nb; i++) g_tfirst[bnode[i]] = -1;
    return rc;
}
