// The street-arrangement carousel on the Street Safety dashboard (Bryan, 2026-11-20: "make a carousel with these
// diagrams in the pedestrian violations category"). The card's markup is written at build time by arrangements.mjs;
// this shows it only while the chart is split by cause with Pedestrian violation picked whole, and steps it: the two
// buttons, the arrow keys while the card has focus, and a sideways swipe. One slide shows at a time and all seven
// share one grid cell, so the card keeps the size of its longest slide and nothing moves on a step. No autoplay.
var SafetyArrangements = (function () {
  var CAUSE = "pedestrian-violation";
  // True when the state is the injuries view, its chart is the cause chart, and the cause filter is that one cause.
  function shows(s, S) {
    var c = s && s.filter && s.filter.cause || [];
    return !!s && s.view === "injuries" && !s.crash && S.chartFor(s) === "by-cause" && c.length === 1 && c[0] === CAUSE;
  }
  function attach(el) {
    var slides = Array.prototype.slice.call(el.querySelectorAll("[data-arr-slide]")), pos = el.querySelector("[data-arr-pos]"), i = 0;
    function show(n) {
      i = (n + slides.length) % slides.length;
      slides.forEach(function (sl, k) { sl.classList.toggle("on", k === i); });
      pos.textContent = (i + 1) + " of " + slides.length;
    }
    el.querySelector("[data-arr-prev]").addEventListener("click", function () { show(i - 1); });
    el.querySelector("[data-arr-next]").addEventListener("click", function () { show(i + 1); });
    el.addEventListener("keydown", function (e) {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "ArrowLeft") { show(i - 1); e.preventDefault(); }
      else if (e.key === "ArrowRight") { show(i + 1); e.preventDefault(); }
    });
    // A swipe: a touch that ends at least 40 px to the side of where it began and moved more across than down.
    var t0 = null;
    el.addEventListener("touchstart", function (e) { var t = e.changedTouches[0]; t0 = e.touches.length === 1 ? [t.clientX, t.clientY] : null; }, { passive: true });
    el.addEventListener("touchend", function (e) {
      if (!t0) return;
      var t = e.changedTouches[0], dx = t.clientX - t0[0], dy = t.clientY - t0[1]; t0 = null;
      if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy) * 1.5) show(dx < 0 ? i + 1 : i - 1);
    }, { passive: true });
    show(0);
    return { sync: function (s, S) { el.hidden = !shows(s, S); }, show: show, index: function () { return i; } };
  }
  return { shows: shows, attach: attach, CAUSE: CAUSE };
})();
