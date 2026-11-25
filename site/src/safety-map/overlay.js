// The Street Safety map's overlays, shared by the dashboard and the story: the slim key with its one headline figure,
// and the corner chart (Workspaces' PlotChart, window.SafetyChart from src/plot-chart/entry.mjs). Each follows
// the map's state; none of them holds any state of its own.
//
//   SafetyOverlay.attach(ctl, { key, headline, chart, noWhere });
//
// Bryan, 2026-11-19: "overlay one simple chart on top of the map. Somewhere. Off in a corner", and "keep the legends
// and metrics and so on simpler".
(function (root) {
  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function n0(v) { return Math.round(v).toLocaleString("en-US"); }
  function n2(v) { v = Math.round(v); if (v < 100) return String(v); var p = Math.pow(10, Math.floor(Math.log10(v)) - 1); return (Math.round(v / p) * p).toLocaleString("en-US"); }

  // The one headline figure for the state, scoped to the area, time and day filters where they apply.
  // `noWhere` leaves the area out, for a page whose title above already names it (one place per fact).
  function headline(ctl, s, noWhere) {
    var D = ctl.data(); if (!D) return "";
    var where = s.filter.area && !noWhere ? (s.filter.area.hood ? " in " + esc(s.filter.area.hood) : s.filter.area.district ? " in District " + s.filter.area.district : " in this area") : "";
    if (s.view === "injuries") {
      // Just the two counts (Bryan, 2026-11-19: "Just say 'Showing <x> people injured, <y>
      // killed'. The date range already shows up elsewhere"): the map's title carries the years and the severity, the
      // drawer the other filters. Injured is everyone shown who wasn't killed, so the two add up to the people shown.
      var f = ctl.figures();
      var line = "Showing " + (s.filter.severity === "killed" ? "<b>" + n0(f.killed) + "</b> people killed" : "<b>" + n0(f.people - f.killed) + "</b> people injured, <b>" + n0(f.killed) + "</b> killed") +
        (ctl.olderLoading && ctl.olderLoading() ? '<span class="sm-na">Loading 2005 to 2020</span>' : "");
      // Each year's worst 10 miles (teal) is ranked on that year's severe and fatal injuries alone, so it gets its own line.
      var W = s.worst && D.worst ? D.worst.summary.filter(function (x) { return x.year === s.worst; })[0] : null;
      if (W) return "<b>" + n0(W.people) + "</b> of the " + n0(W.people_in_year) + " people severely hurt or killed in " + W.year + " were on its worst 10 miles, in teal" +
        (W.complete ? "" : " (" + W.year + " is not yet complete)") + '.<span class="sm-na">' + line.replace(/<\/?b>/g, "") + ".</span>";
      return line + unplacedNote(f);
    }
    return other(ctl, s, where) + na(s);
  }
  // The people the headline counts whom the map can't draw, said once under it and only when there are any: the
  // police record gives no place in San Francisco for them (map.js `np`), so they count and have no dot.
  function unplacedNote(f) {
    var n = f.unplaced || 0, k = f.unplacedKilled || 0;
    if (!n) return "";
    var who = k === n ? n0(n) + (n === 1 ? " death has" : " deaths have") : n0(n) + " of these people " + (n === 1 ? "has" : "have");
    return '<span class="sm-na sm-unplaced">' + who + " no location in the police record and " + (n === 1 ? "isn't" : "aren't") + " on the map</span>";
  }
  // What a view can't take from the day and time choice, said once under its headline. Traffic stress and through
  // traffic have weekday data only (Bryan, 2026-11-19: weekend choices say so on those layers).
  function na(s) {
    var S = window.SafetyMapState, t = s.filter.time.length, d = s.filter.days, wd = S.weekdays(d) || [],
      wkend = wd.indexOf(0) >= 0 || wd.indexOf(6) >= 0, oneDay = d.length && d[0] !== "weekday" && d[0] !== "weekend";
    if (!t && !d.length) return "";
    var why = "";
    if (s.view === "stress") why = (wkend ? "No weekend data: these" : "These") + " are traffic figures for the busiest weekday hour, so the day and time choice doesn't change this view.";
    if (s.view === "through" && wkend) why = "No weekend data: the travel model is one weekday, so this shows weekday traffic.";
    else if (s.view === "through" && oneDay) why = "The travel model is one average weekday, so single days show that weekday.";
    if (s.view === "through" && t > 1) why += (why ? " " : "") + "The model gives one time of day at a time, so with several picked this shows the whole day.";
    if (s.view === "bike") why = "The Bike Comfort Index has no hour or day, so the day and time choice doesn't change this view.";
    return why ? '<span class="sm-na">' + why + "</span>" : "";
  }
  function other(ctl, s, where) {
    var m = ctl.mixes();
    if (s.view === "stress") {
      var busy = m.stress.cls.slice(1).reduce(function (a, b) { return a + b; }, 0);
      return "<b>" + n0(busy) + "</b> of " + n0(m.stress.n) + " residential blocks" + where + " carry 1.5 cars a minute or more at the busiest hour";
    }
    if (s.view === "through") {
      var t = m.through;
      var tm = s.filter.time.length === 1 ? (window.SafetyMapState.TIMES.filter(function (x) { return x[0] === s.filter.time[0]; })[0] || [0, ""])[1].replace(/,.*/, "").toLowerCase() : "";
      return "On <b>" + n0(t.most) + "</b> of " + n0(t.n) + " blocks the model carries" + where + ", most car trips" + (tm ? " in the " + esc(tm) : "") + " are passing through" +
        (s.near !== window.SafetyMapState.DEFAULTS.near && ctl.nearPhrase ? ", with neither end within " + ctl.nearPhrase() : "");
    }
    if (s.view === "from") {
      var w = m.from, a = s.filter.area;
      if (!a) return "Pick a neighborhood or draw an area to see where the cars on its streets come from";
      if ((!w || !w.ready) && ctl.fromFailed && ctl.fromFailed()) return "Couldn't load where the traffic" + where + " comes from. Reload the page to try again";
      if (!w || !w.ready) return "Loading where the traffic" + where + " comes from…";
      var name = a.hood ? esc(a.hood) : a.district ? "District " + a.district : "this area";
      if (!w.hood) return "<b>" + n0(w.total) + "</b> car crossings a weekday " + (s.ends === "from" ? "into " + name : s.ends === "to" ? "out of " + name : "into or out of " + name) +
        '. <span class="sm-na">A cordon count over the ' + n0(w.links) + " links onto or off the streets inside the edge you drew: a car counts each time it crosses, so it can't show through cars alone.</span>";
      // The share leads (Bryan, 2026-11-20: "I want us to think about fractions"), with the
      // count it is a share of as the one other figure.
      // Both counts each car at both of its ends, so its share is of trip ends, the base the bars and bubbles use.
      // A phone gets one short line.
      // Passing through: the through cars as a share of every car on the area's streets.
      // The one other figure is the through cars themselves, the base the bars' and bubbles' shares are of.
      if (w.thru) return ctl.narrow && ctl.narrow() ? "<b>" + Math.round(100 * w.lead) + "%</b> pass through: " + n2(w.thr) + " cars a weekday" :
        "<b>" + Math.round(100 * w.lead) + "%</b> of the cars on " + name + "'s streets pass through it: " + n2(w.thr) + " a weekday";
      if (ctl.narrow && ctl.narrow()) return "<b>" + Math.round(100 * w.lead) + "%</b> of " + n2(w.users) + " cars " + (s.ends === "from" ? "start outside" : s.ends === "to" ? "end outside" : "trip ends are outside");
      if (s.ends === "both") return "<b>" + Math.round(100 * w.lead) + "%</b> of the trip ends of the " + n2(w.users) + " cars a weekday on " + name + "'s streets are outside it";
      return "<b>" + Math.round(100 * w.lead) + "%</b> of the " + n2(w.users) + " cars a weekday on " + name + "'s streets " + (s.ends === "from" ? "start outside it" : "end outside it");
    }
    if (s.view === "bike") {
      var all = m.bci.reduce(function (a, b) { return a + b; }, 0), A = ctl.data().bci.aaa;
      var pk = s.filter.bci || [];
      // With classes picked (the key or the chart), the blocks in them.
      if (pk.length) return "<b>" + n0(pk.reduce(function (a, k) { return a + m.bci[k]; }, 0)) + "</b> of " + n0(all) + " blocks" + where + " score " +
        pk.map(function (k) { return esc(ctl.data().bci.labels[k].replace(/ - /, " to ")); }).join(" or ") + " on SFMTA's Bike Comfort Index";
      return "<b>" + n0(m.bci.slice(0, A.below).reduce(function (a, b) { return a + b; }, 0)) + "</b> of " + n0(all) + " blocks" + where + " score " + A.score + " or under on SFMTA's Bike Comfort Index, below its all ages line";
    }
    // Crime loads the first time its view opens (map.js loadCrime).
    if (m.crime.loading) return "Loading SFPD reports since 2018";
    return "<b>" + n0(m.crime.n) + "</b> SFPD reports" + where + ", " + esc(ctl.crimeSpan());
  }

  // The corner chart. With `o.picker` the chart's title is a menu of the view's charts (Bryan, 2026-11-19: "let the
  // user choose which dimension to show"). A distribution chart gets one button per bar laid over the drawing, so a
  // bar can be hovered, focused, clicked or tapped: hover and keyboard focus highlight its people on the map, a click,
  // a tap or Enter filters to them, and the same again clears it. On a touch screen a tap only filters.
  function attach(ctl, o) {
    var lastChart = "", S = root.SafetyMapState, box = o.chart, head = null, pick = null, upBtn = null;
    if (box && o.picker) {
      head = document.createElement("div");
      head.className = "sm-chart-head";
      head.innerHTML = (o.chartLabel ? '<p class="sm-chart-label">' + esc(o.chartLabel) + "</p>" : "") +
        '<select class="sm-chart-pick" aria-label="' + esc(o.chartLabel || "Chart") + '"></select><button type="button" class="sm-chart-up" hidden></button>';
      box.insertBefore(head, box.firstChild);
      pick = head.querySelector("select"); upBtn = head.querySelector(".sm-chart-up");
      pick.addEventListener("change", function () { ctl.setState({ chart: { id: pick.value } }); });
      upBtn.addEventListener("click", function () { ctl.chartPick("up"); });
    }
    function picker(s, props) {
      if (!pick) return;
      var ids = S.CHARTS[s.view];
      var want = ids.map(function (id) { return id + "|" + ctl.chartTitles[id]; }).join(";");
      if (pick.dataset.ids !== want) {
        // The headline beside it already says what is counted, so the menu names only the split: "By cause".
        pick.innerHTML = ids.map(function (id) { return '<option value="' + id + '">' + esc(ctl.chartTitles[id].replace(/^(People hurt|SFPD reports) by/, "By")) + "</option>"; }).join("");
        pick.dataset.ids = want;
      }
      pick.value = props.id;
      pick.hidden = ids.length < 2;
      head.classList.toggle("one", ids.length < 2);
      upBtn.hidden = !props.up;
      upBtn.textContent = props.up ? "‹ " + props.up : "";
    }
    // The where-from view marks the bar of a hovered bubble or an open card.
    function markHl() {
      if (!box || !ctl.fromHl) return;
      var k = ctl.fromHl();
      Array.prototype.forEach.call(box.querySelectorAll(".sm-hit.look"), function (b) { b.classList.toggle("on", k != null && b.dataset.key === String(k)); });
    }
    ctl.onFromHl = markHl;
    // One button per bar, over the bar's row: the label, the bar and its figure.
    var leaveT = 0;
    function hits(slot, props) {
      var old = slot.parentNode.querySelector(".sm-chart-hits");
      var focused = old && old.contains(document.activeElement) ? document.activeElement.dataset.key : null;
      if (old) old.remove();
      var rows = props.data.rows;
      if (!rows.length || !rows.some(function (r) { return r.key !== undefined; })) return;
      // The first bar mark holds one rect per row; a stacked chart draws its parts as a second bar mark over it.
      var first = slot.querySelector('g[aria-label="bar"]'), rects = first ? first.querySelectorAll("rect") : [];
      if (rects.length !== rows.length) return;
      var layer = document.createElement("div"), base = slot.getBoundingClientRect();
      layer.className = "sm-chart-hits";
      layer.style.top = slot.offsetTop + "px"; layer.style.left = slot.offsetLeft + "px"; layer.style.width = slot.offsetWidth + "px"; layer.style.height = slot.offsetHeight + "px";
      // Each row's button runs from its name (the 14 px above its bar) to its bar's foot, and neighbours meet halfway
      // across the gap between them, so the pointer never crosses a strip that belongs to no bar (Bryan, 2026-11-19,
      // "hovering inbetween shouldn't introduce a big flicker").
      var ext = Array.prototype.map.call(rects, function (rc) { var rb = rc.getBoundingClientRect(); return [rb.top - base.top - 14, rb.bottom - base.top + 2]; });
      // The first and the last row take the same half gap on their open side, so every row's button is one row tall
      // (44 px on a tablet, where the rows are spaced for touch).
      var half = ext.length > 1 ? Math.max(0, (ext[1][0] - ext[0][1]) / 2) : 0;
      if (ext.length) { ext[0][0] -= half; ext[ext.length - 1][1] += half; }
      for (var k = 1; k < ext.length; k++) { var mid = (ext[k - 1][1] + ext[k][0]) / 2; ext[k - 1][1] = mid; ext[k][0] = mid; }
      rows.forEach(function (r, i) {
        var b = document.createElement("button");
        b.type = "button"; b.className = "sm-hit" + (r.on ? " on" : ""); b.dataset.key = r.key;
        b.style.top = ext[i][0] + "px"; b.style.height = (ext[i][1] - ext[i][0]) + "px";
        if (r.title && r.title !== r.label) b.title = r.title;
        b.setAttribute("aria-label", (r.title || r.label) + ": " + n0(r.value) + (r.pick ? (r.on ? ". Selected; press to clear the filter" : ". Press to show only these") : ""));
        if (r.pick) b.setAttribute("aria-pressed", r.on ? "true" : "false");
        // Leaving a bar clears the highlight only after 150 ms, and entering another bar cancels that, so moving from
        // one bar to the next never flashes the whole map in between.
        b.addEventListener("pointerenter", function (e) { if (e.pointerType === "mouse") { clearTimeout(leaveT); ctl.chartHover(r.key); } });
        b.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse") { clearTimeout(leaveT); leaveT = setTimeout(function () { ctl.chartHover(null); }, 150); } });
        b.addEventListener("focus", function () { if (b.matches(":focus-visible")) ctl.chartHover(r.key); });
        b.addEventListener("blur", function () { ctl.chartHover(null); });
        if (r.pick) b.addEventListener("click", function () { ctl.chartPick(r.key); });
        else { b.classList.add("look"); if (ctl.chartTap) b.addEventListener("click", function () { ctl.chartTap(r.key); }); }
        layer.appendChild(b);
      });
      slot.parentNode.appendChild(layer);
      layer._slot = slot;
      markHl();
      if (focused != null) { var again = layer.querySelector('[data-key="' + String(focused).replace(/"/g, '\\"') + '"]'); if (again) again.focus(); }
    }
    // A bar's figure "6,935 (71%)": the share after the count in smaller type, so the count reads first.
    function small(slot) {
      Array.prototype.forEach.call(slot.querySelectorAll("svg text"), function (t) {
        if (t.children.length) return;
        // The where-from chart leads with the share, "6.1% (11,400)", so there the count is the smaller part.
        var m = /^(.*\S) \((<?\d+%)\)$/.exec(t.textContent) || /^(<?[\d.]+%) \(([\d,]+)\)$/.exec(t.textContent);
        if (!m) return;
        var ns = "http://www.w3.org/2000/svg", a = document.createElementNS(ns, "tspan"), b = document.createElementNS(ns, "tspan");
        a.textContent = m[1]; b.textContent = " (" + m[2] + ")"; b.setAttribute("font-size", "0.85em"); b.setAttribute("fill-opacity", "0.8");
        t.textContent = ""; t.appendChild(a); t.appendChild(b);
      });
    }
    function chart(s) {
      if (!box) return;
      var props = ctl.chart();
      box.hidden = !props || !!s.crash;
      if (!props) return;
      if (pick) { picker(s, props); props = Object.assign({}, props, { title: pick.hidden ? props.title : "" }); }
      // A bar's name runs the box's width, then ends in an ellipsis (Plot's lineWidth is in ems of the 11 px text).
      var lab = props.marks && props.marks[1] && props.marks[1].options;
      if (lab && lab.lineWidth) { props = JSON.parse(JSON.stringify(props)); props.marks[1].options.lineWidth = Math.max(10, (box.clientWidth - 30) / 11); }
      // Margins wider than a narrow box (a phone) would leave the bars a negative width, which the browser refuses
      // ("<rect> attribute width: A negative value"): shrink both margins so the bars keep at least 40 px.
      var po = props.options || {}, room = box.querySelector(".sm-chart-slot").clientWidth - 40, ml = po.marginLeft || 0, mr = po.marginRight || 0;
      if (room > 0 && ml + mr > room) { var k = room / (ml + mr); props = JSON.parse(JSON.stringify(props)); props.options.marginLeft = Math.floor(ml * k); props.options.marginRight = Math.floor(mr * k); }
      var key = JSON.stringify(props);
      if (key === lastChart) return;
      lastChart = key;
      var slot = box.querySelector(".sm-chart-slot");
      if (root.SafetyChart) { root.SafetyChart.draw(slot, props); small(slot); hits(slot, props); }
      else root.addEventListener("safetychart:ready", function () { lastChart = ""; chart(ctl.getState()); }, { once: true });
    }
    function sync(s) {
      if (o.key) o.key.innerHTML = ctl.keyHTML();
      if (o.headline) o.headline.innerHTML = headline(ctl, s, !!(o.noWhere && o.noWhere(s)));
      chart(s);
      // With a home for it, the headline is the corner chart's title, and moves to its home while the chart is hidden.
      if (o.headline && o.headlineHome && box) {
        var to = box.hidden ? o.headlineHome : box;
        if (to.firstChild !== o.headline) to.insertBefore(o.headline, to.firstChild);
      }
      // The headline above the chart can change height after the bars' buttons were laid: set them over the bars again.
      var hl = box && box.querySelector(".sm-chart-hits");
      if (hl && hl._slot) { hl.style.top = hl._slot.offsetTop + "px"; hl.style.left = hl._slot.offsetLeft + "px"; }
    }
    ctl.on(function (s) { sync(s); });
    // A key entry that filters (a bike comfort class): a click shows only it, the same click again shows every class.
    if (o.key) o.key.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-bci]"); if (!b) return;
      var k = Number(b.dataset.bci), pk = ctl.getState().filter.bci;
      ctl.setState({ filter: { bci: pk.length === 1 && pk[0] === k ? [] : [k] } });
    });
    ctl.ready.then(function () { sync(ctl.getState()); });
    // The bar buttons sit over the drawing, so a resize that moves the drawing moves them.
    root.addEventListener("resize", function () { lastChart = ""; chart(ctl.getState()); });
    return { sync: sync };
  }

  root.SafetyOverlay = { attach: attach, headline: headline };
})(this);
