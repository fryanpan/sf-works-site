// The contact-officials block: pick your supervisor (or the Mayor), edit a
// short prefilled note, and open it in
// your own email app. Bryan, 2026-10-06, on the post's placeholder "Insert a
// way to send this article to your supervisor or mayor": "Add this widget
// please", and earlier, "a re-usable UX component for emailing your elected
// representative".
//
// Nothing leaves the page. Bryan, 2026-10-07, dropped the "Use my location"
// lookup as unnecessary; the city's district finder link stays. The message
// goes out through a mailto:
// link the reader's own email app opens; there are no form posts, no
// third-party services and no analytics. The names and addresses are
// hand-kept in site/data/officials.json, with the page each was read from and
// the date.
//
// Reusable: contactOfficials({ url, subject, body }) takes the link and the
// message, so another post can carry the same block with its own words.

import fs from "node:fs";
import path from "node:path";
import { esc } from "./html.mjs";

const DATA = path.join(import.meta.dirname, "..", "data");
const read = (f) => JSON.parse(fs.readFileSync(path.join(DATA, f), "utf8"));
const officials = read("officials.json");

// Where the email goes.
//   "direct" each official's own published contact address: a supervisor's
//            office inbox from their page on sf.gov, the Mayor's "Contact the
//            Mayor" address.
//   "clerk"  the Board of Supervisors' institutional inbox, with the chosen
//            supervisor named in the subject line. (The Mayor's message still
//            goes to the Mayor's published address.)
// Bryan, 2026-10-06: their own addresses.
export const EMAIL_MODE = "direct";

// The post's live address, from its front matter: the sf-works.org dashboard,
// which keeps updating while the fryanpan.com copy stays as published.
const POST = path.join(import.meta.dirname, "..", "content", "posts", "sf-bike-network.md");
const front = (fs.readFileSync(POST, "utf8").split(/^---$/m)[1] || "");
export const POST_URL = (/^dashboard:\s*(\S+)\s*$/m.exec(front) || [])[1] || "https://sf-works.org/transportation/bike/";

export const BIKE_SUBJECT = "Hold SFMTA Accountable to the Law: Build Bikeways When We Repave";
// Under 120 words, in Bryan's voice. The figures are the post's own (its
// opening paragraphs), so the note says nothing the link doesn't back.
export const bikeBody = (url) => `I live in San Francisco, and I want a bike network that's safe enough for kids and seniors. The city adopted the Biking and Rolling Plan in March 2025. Since the plan passed, SFMTA has added under 5 of the 255 miles still to build. Even at the last ten years' pace, it won't be finished until after 2050.

City law already requires adding the planned bikeway when a street is repaved. The city repaved 7.9 miles of plan streets that needed a better bikeway and added a bikeway on only 0.7 of those miles.

Please hold SFMTA more accountable to the law.

Here's the data: ${url}

Thank you,
[Your name and neighborhood]`;

const greeting = (who) => (who ? `Dear ${who},` : "Hello,");

// Each official's portrait, for the picker (Bryan, 2026-10-06: "Add pictures
// to the dropdown"). All twelve are the city's official portraits as hosted
// on Wikimedia Commons, public domain under PD-CAGov; officials.json records
// each file page, the city page it came from and the date read. Cropped to
// 96 by 96 and shown at 48, so they stay sharp on a 2x screen at about 3 kB
// each. Each is its own file, served beside the embed pages and loaded only
// when the list opens (or, for the button, once someone is chosen).
export const PHOTO_DIR = "/photos/officials";
const everyone = () => [...officials.supervisors, officials.mayor];
export const officialPhotos = () => everyone().map((o) => ({
  path: `${PHOTO_DIR}/${o.photo.file}`, file: `${PHOTO_DIR.slice(1)}/${o.photo.file}`,
  bytes: fs.readFileSync(path.join(DATA, "photos", o.photo.file)),
}));

// The photo credits as one entry per photographer, each surname linking to
// its Commons file page; an embed page folds them into its "Photos:" line and
// a full page gathers them at its end (layout.mjs, gatherNotes).
function photoCredits() {
  const groups = new Map();
  for (const o of everyone()) {
    const key = `${o.photo.by}\u0000${o.photo.licence}\u0000${o.photo.licenceUrl}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(`<a href="${esc(o.photo.url)}">${esc(o.name.split(" ").slice(-1)[0])}</a>`);
  }
  const items = [...groups].map(([key, names]) => {
    const [by, licence, url] = key.split("\u0000");
    return `<li>${esc(by)} (${names.join(", ")}), Wikimedia Commons (<a href="${esc(url)}">${esc(licence)}</a>), cropped</li>`;
  });
  return `<ul class="credit" data-for="Officials' photos">${items.join("")}</ul>`;
}

const photo = (o) => `<img class="co-face" src="${PHOTO_DIR}/${o.photo.file}" alt="" width="48" height="48" loading="lazy" decoding="async">`;
// A neutral head-and-shoulders mark for the button before anyone is chosen.
const BLANK = `<svg class="co-face co-face-blank" viewBox="0 0 48 48" width="48" height="48" aria-hidden="true"><circle cx="24" cy="24" r="24" fill="var(--rule)"/><circle cx="24" cy="19" r="8" fill="var(--paper)"/><path d="M9 41c3-8 9-12 15-12s12 4 15 12" fill="var(--paper)"/></svg>`;

/** The picker: a native select as the no-script fallback, and the listbox with photos that the script swaps in. */
function picker() {
  const m = officials.mayor;
  const opts = [
    ...officials.supervisors.map((s) => ({ value: `d${s.district}`, o: s, sub: `District ${s.district}` })),
    { value: "mayor", o: m, sub: "Mayor" },
  ];
  return `<select id="co-to" class="co-native" data-co-to>
<option value="">Choose your supervisor or the Mayor</option>
${officials.supervisors.map((s) => `<option value="d${s.district}">District ${s.district}: ${esc(s.name)}</option>`).join("\n")}
<option value="mayor">Mayor ${esc(m.name)}</option>
</select>
<div class="co-lb" data-co-lb hidden>
<div class="co-combo" id="co-combo" role="combobox" tabindex="0" aria-haspopup="listbox" aria-expanded="false" aria-controls="co-list" aria-labelledby="co-to-label" data-co-combo>
<span class="co-combo-face" data-co-face>${BLANK}</span><span class="co-combo-text" data-co-text><span class="co-placeholder">Choose your supervisor or the Mayor</span></span><svg class="co-chev" viewBox="0 0 12 8" width="12" height="8" aria-hidden="true"><path d="M1 1.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>
</div>
<ul class="co-list" id="co-list" role="listbox" aria-labelledby="co-to-label" tabindex="-1" hidden data-co-list>
${opts.map(({ value, o, sub }) => `<li class="co-opt" id="co-opt-${value}" role="option" aria-selected="false" data-value="${value}">${photo(o)}<span class="co-opt-text"><span class="co-opt-name">${esc(o.name)}</span><span class="co-opt-sub">${sub}</span></span></li>`).join("\n")}
</ul>
</div>`;
}

/** The data the browser half reads, in the block's own JSON script. */
function blockData({ subject, body }) {
  return {
    mode: EMAIL_MODE,
    subject,
    body,
    clerk: officials.board.clerkEmail,
    mayor: { name: officials.mayor.name, email: officials.mayor.email },
    supervisors: officials.supervisors.map((s) => ({ district: s.district, name: s.name, email: s.email })),
  };
}

/** The block's markup, pre-rendered with the message as it reads before anyone touches a control. */
export function contactOfficials({ url = POST_URL, subject = BIKE_SUBJECT, body = bikeBody(url) } = {}) {
  const m = officials.mayor;
  const text = `${greeting("")}\n\n${body}`;
  const mailto = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text.replace(/\n/g, "\r\n"))}`;
  const sources = [
    `Names and addresses from the <a href="${officials.board.url}">Board of Supervisors</a> and <a href="${m.url}">Mayor's Office</a> pages on sf.gov, as of ${officials.asOf}`,
  ];
  return `<div class="co" data-co>
<h3 class="co-h">Send This to Your Supervisor or the Mayor</h3>
<div class="co-who">
<label class="co-label" id="co-to-label" for="co-to">Who to write to</label>
<div class="co-pick">
${picker()}
</div>
<p class="co-hint" data-co-status aria-live="polite">Look up your district on the <a href="${officials.board.findYourSupervisor}">city's district finder</a>.</p>
</div>
<p class="co-to-line" data-co-address hidden></p>
<label class="co-label" for="co-subject">Subject</label>
<input type="text" id="co-subject" class="co-field" data-co-subject value="${esc(subject)}">
<label class="co-label" for="co-body">Message</label>
<textarea id="co-body" class="co-field" data-co-body rows="18">${esc(text)}</textarea>
<div class="co-send">
<a class="co-btn co-btn-main" data-co-mail href="${esc(mailto)}">Open in my email</a>
<button type="button" class="co-btn co-btn-quiet" data-co-copy>Copy message</button>
<span class="co-done" data-co-done aria-live="polite"></span>
</div>
<p class="co-note">Nothing is sent from this page. Your email app opens with the message, and you send it.</p>
<script type="application/json" data-co-data>${JSON.stringify(blockData({ subject, body })).replace(/</g, "\\u003c")}</script>
</div>
<ul class="cite" data-for="Contact officials">${sources.map((s) => `<li>${s}</li>`).join("")}</ul>
${photoCredits()}`;
}

export const CONTACT_CSS = `<style>
.co { border: 1px solid var(--rule); border-radius: 6px; padding: 16px; background: var(--raised); max-width: 720px; }
.co-h { font-size: 1.15rem; margin: 0 0 12px; }
.co-label { display: block; font-weight: 600; font-size: 0.92rem; margin: 12px 0 4px; }
.co-who .co-label { margin-top: 0; }
.co-pick { display: flex; flex-wrap: wrap; gap: 8px; }
.co-lb { position: relative; flex: 1 1 260px; min-width: 0; }
.co-lb[hidden], .co-list[hidden] { display: none; }
.co-js .co-native { display: none; }
.co-combo { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 5px 12px 5px 6px; border: 1px solid var(--muted); border-radius: 4px; background: var(--paper); color: var(--ink); cursor: pointer; user-select: none; }
.co-combo-text { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; line-height: 1.25; }
.co-chev { flex: none; color: var(--muted); transition: transform 0.15s; }
.co-combo[aria-expanded="true"] .co-chev { transform: rotate(180deg); }
.co-face { display: block; flex: none; width: 36px; height: 36px; border-radius: 50%; object-fit: cover; background: var(--rule); }
.co-list { position: absolute; z-index: 20; left: 0; right: 0; top: calc(100% + 4px); margin: 0; padding: 4px; list-style: none; max-height: min(420px, 62vh); overflow-y: auto; overscroll-behavior: contain; background: var(--paper); border: 1px solid var(--muted); border-radius: 6px; box-shadow: 0 6px 20px rgba(21, 24, 28, 0.16); }
.co-opt { display: flex; align-items: center; gap: 12px; padding: 6px 10px 6px 6px; border-radius: 4px; cursor: pointer; line-height: 1.25; }
.co-opt .co-face { width: 48px; height: 48px; }
.co-opt-text { display: flex; flex-direction: column; min-width: 0; }
.co-opt-name { font-weight: 600; overflow-wrap: anywhere; }
.co-opt-sub { font-size: 0.86rem; color: var(--muted); }
.co-placeholder { color: var(--muted); }
.co-opt:hover { background: var(--raised); }
.co-opt.co-active { background: var(--seq-3-soft); box-shadow: inset 0 0 0 2px var(--seq-3); }
.co-opt[aria-selected="true"] .co-opt-name::after { content: " \\2713"; color: var(--seq-3); }
.co-pick select { flex: 1 1 260px; min-width: 0; font: inherit; font-size: 1rem; padding: 8px 10px; border: 1px solid var(--muted); border-radius: 4px; background: var(--paper); color: var(--ink); }
.co-field { display: block; width: 100%; font: inherit; font-size: 1rem; line-height: 1.5; padding: 8px 10px; border: 1px solid var(--muted); border-radius: 4px; background: var(--paper); color: var(--ink); }
textarea.co-field { resize: vertical; min-height: 12em; field-sizing: content; }
.co-hint, .co-note, .co-to-line { font-size: 0.88rem; line-height: 1.45; margin: 8px 0 0; color: var(--muted); }
.co-to-line { color: var(--ink); margin-top: 12px; overflow-wrap: anywhere; }
.co-hint.co-found { color: var(--ink); }
.co-btn { display: inline-flex; align-items: center; justify-content: center; font: inherit; font-weight: 600; font-size: 0.98rem; line-height: 1.2; padding: 9px 16px; border-radius: 4px; border: 1px solid var(--ink); cursor: pointer; text-decoration: none; }
.co-btn-main { background: var(--ink); color: #ffffff; }
.co-btn-main:hover { background: var(--grey-dark); }
.co-btn-quiet { background: var(--paper); color: var(--ink); }
.co-btn-quiet:hover { background: var(--rule); }
.co-link { font: inherit; color: var(--accent); background: none; border: 0; padding: 0; text-decoration: underline; cursor: pointer; }
.co-send { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 14px; }
.co-done { font-size: 0.9rem; color: var(--ok); }
.co select:focus-visible, .co .co-combo:focus-visible, .co .co-field:focus-visible, .co .co-btn:focus-visible, .co .co-link:focus-visible { outline: 3px solid var(--seq-3); outline-offset: 2px; }
@media (max-width: 480px) {
  .co { padding: 12px; }
  .co-pick .co-btn, .co-send .co-btn { flex: 1 1 100%; }
}
</style>`;

// The browser half. Runs inside the block (document answers from inside it
// only, see bike-blocks.mjs), so two copies on one page keep apart.
export const CONTACT_SCRIPT = `<script>
(function () {
  document.querySelectorAll("[data-co]").forEach(function (w) {
    var d = JSON.parse(w.querySelector("[data-co-data]").textContent);
    var to = w.querySelector("[data-co-to]"), subj = w.querySelector("[data-co-subject]"), body = w.querySelector("[data-co-body]");
    var mail = w.querySelector("[data-co-mail]"), status = w.querySelector("[data-co-status]"), done = w.querySelector("[data-co-done]");
    var address = w.querySelector("[data-co-address]");
    var statusHTML = status.innerHTML;
    function who() {
      var v = to.value;
      if (v === "mayor") return { greet: "Mayor " + d.mayor.name.split(" ").slice(-1)[0], email: d.mayor.email, label: "Mayor " + d.mayor.name, mayor: true };
      var n = Number(v.slice(1));
      var s = d.supervisors.filter(function (x) { return x.district === n; })[0];
      if (!s) return null;
      return { greet: "Supervisor " + s.name.split(" ").slice(-1)[0], email: d.mode === "clerk" ? d.clerk : s.email,
        label: "Supervisor " + s.name + " (District " + s.district + ")", district: s.district, name: s.name };
    }
    function subjectFor(o) {
      return d.mode === "clerk" && o && !o.mayor ? "For Supervisor " + o.name + " (District " + o.district + "): " + d.subject : d.subject;
    }
    // A field the reader has typed in keeps their words; only its greeting
    // (the message's first line) and a subject still as we wrote it follow the pick.
    var lastSubject = subj.value;
    function update() {
      var o = who();
      var lines = body.value.split("\\n");
      if (/^(Dear .*,|Hello,)\\s*$/.test(lines[0])) { lines[0] = o ? "Dear " + o.greet + "," : "Hello,"; body.value = lines.join("\\n"); }
      if (subj.value === lastSubject) subj.value = lastSubject = subjectFor(o);
      address.hidden = !o;
      if (o) address.textContent = "To: " + o.label + ", " + o.email + (d.mode === "clerk" && !o.mayor ? " (the Board of Supervisors' public inbox)" : "");
      href();
    }
    function href() {
      var o = who();
      var enc = function (s) { return encodeURIComponent(s.replace(/\\r?\\n/g, "\\r\\n")); };
      mail.href = "mailto:" + (o ? o.email : "") + "?subject=" + enc(subj.value) + "&body=" + enc(body.value);
    }
    function say(html, found) { status.innerHTML = html; status.classList.toggle("co-found", !!found); }

    // The picker with photos: a select-only combobox (WAI-ARIA APG pattern).
    // Focus stays on the combobox and aria-activedescendant names the option
    // the arrows are on; the hidden native select stays the one value
    // everything else reads, and is what a reader without scripts gets.
    var lb = w.querySelector("[data-co-lb]"), combo = w.querySelector("[data-co-combo]"), list = w.querySelector("[data-co-list]");
    var face = w.querySelector("[data-co-face]"), ctext = w.querySelector("[data-co-text]");
    var opts = [].slice.call(list.querySelectorAll("[role=option]"));
    var blankFace = face.innerHTML, blankText = ctext.innerHTML;
    var active = -1, typed = "", typedAt = 0;
    w.classList.add("co-js");
    lb.hidden = false;
    w.querySelector("#co-to-label").addEventListener("click", function (e) { e.preventDefault(); combo.focus(); });
    function isOpen() { return combo.getAttribute("aria-expanded") === "true"; }
    function indexOf(v) { for (var i = 0; i < opts.length; i++) if (opts[i].getAttribute("data-value") === v) return i; return -1; }
    function show() {
      var i = indexOf(to.value);
      opts.forEach(function (o, k) { o.setAttribute("aria-selected", k === i ? "true" : "false"); });
      if (i < 0) { face.innerHTML = blankFace; ctext.innerHTML = blankText; return; }
      var img = opts[i].querySelector("img").cloneNode(true);
      img.loading = "eager";
      face.innerHTML = ""; face.appendChild(img);
      ctext.innerHTML = opts[i].querySelector(".co-opt-text").innerHTML;
    }
    function setActive(i) {
      if (active >= 0) opts[active].classList.remove("co-active");
      active = Math.max(0, Math.min(opts.length - 1, i));
      opts[active].classList.add("co-active");
      combo.setAttribute("aria-activedescendant", opts[active].id);
      var top = opts[active].offsetTop, bottom = top + opts[active].offsetHeight;
      if (top < list.scrollTop) list.scrollTop = top - 4;
      else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 4;
    }
    function open(at) {
      if (!isOpen()) { list.hidden = false; combo.setAttribute("aria-expanded", "true"); }
      var i = indexOf(to.value);
      setActive(at === "first" ? 0 : at === "last" ? opts.length - 1 : typeof at === "number" ? at : i < 0 ? 0 : i);
    }
    function close() {
      if (!isOpen()) return;
      list.hidden = true;
      combo.setAttribute("aria-expanded", "false");
      combo.removeAttribute("aria-activedescendant");
      if (active >= 0) opts[active].classList.remove("co-active");
      active = -1;
    }
    function choose(i) {
      close();
      pick(opts[i].getAttribute("data-value"));
      say(statusHTML, false);
    }
    // One place sets who the message goes to: the select, the button, the note.
    function pick(v) { to.value = v; show(); update(); }
    function typeahead(ch) {
      var now = Date.now();
      typed = (now - typedAt > 700 ? "" : typed) + ch.toLowerCase();
      typedAt = now;
      // The same letter again steps to the next name that starts with it.
      var q = typed.split("").every(function (c) { return c === typed[0]; }) ? typed[0] : typed;
      var start = active < 0 ? 0 : active + (q.length === 1 ? 1 : 0);
      for (var k = 0; k < opts.length; k++) {
        var o = opts[(start + k) % opts.length];
        var name = o.querySelector(".co-opt-name").textContent.toLowerCase(), sub = o.querySelector(".co-opt-sub").textContent.toLowerCase();
        var words = (name + " " + sub).split(/\\s+/);
        if (name.indexOf(q) === 0 || sub.indexOf(q) === 0 || words.some(function (x) { return x.indexOf(q) === 0; })) return (start + k) % opts.length;
      }
      return -1;
    }
    combo.addEventListener("click", function () { if (isOpen()) close(); else open(); });
    combo.addEventListener("keydown", function (e) {
      var k = e.key;
      if (e.altKey && k === "ArrowUp" && isOpen()) { e.preventDefault(); choose(active); return; }
      if (!isOpen()) {
        if (k === "ArrowDown" || k === "ArrowUp" || k === "Enter" || k === " ") { e.preventDefault(); open(k === "ArrowUp" && !e.altKey && to.value === "" ? "last" : undefined); }
        else if (k === "Home" || k === "End") { e.preventDefault(); open(k === "Home" ? "first" : "last"); }
        else if (k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { var t = typeahead(k); if (t >= 0) { e.preventDefault(); open(t); } }
        return;
      }
      if (k === "ArrowDown") { e.preventDefault(); setActive(active + 1); }
      else if (k === "ArrowUp") { e.preventDefault(); setActive(active - 1); }
      else if (k === "Home") { e.preventDefault(); setActive(0); }
      else if (k === "End") { e.preventDefault(); setActive(opts.length - 1); }
      else if (k === "PageDown") { e.preventDefault(); setActive(active + 5); }
      else if (k === "PageUp") { e.preventDefault(); setActive(active - 5); }
      else if (k === "Enter" || k === " ") { e.preventDefault(); choose(active); }
      else if (k === "Escape") { e.preventDefault(); close(); }
      else if (k === "Tab") { choose(active); }
      else if (k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { var j = typeahead(k); if (j >= 0) { e.preventDefault(); setActive(j); } }
    });
    // The list never takes focus, so a press on it would blur the combobox first.
    list.addEventListener("mousedown", function (e) { e.preventDefault(); });
    list.addEventListener("click", function (e) {
      var o = e.target.closest && e.target.closest("[role=option]");
      if (o) { choose(opts.indexOf(o)); combo.focus(); }
    });
    list.addEventListener("mousemove", function (e) {
      var o = e.target.closest && e.target.closest("[role=option]");
      if (o && opts.indexOf(o) !== active) setActive(opts.indexOf(o));
    });
    combo.addEventListener("blur", close);
    document.addEventListener("pointerdown", function (e) { if (isOpen() && !lb.contains(e.target)) close(); });
    show();

    to.addEventListener("change", function () { show(); update(); if (to.value) say(statusHTML, false); });
    subj.addEventListener("input", href);
    body.addEventListener("input", href);
    mail.addEventListener("click", function (e) {
      if (who()) return;
      e.preventDefault();
      say("Choose who to write to first.", true);
      combo.focus();
    });
    w.querySelector("[data-co-copy]").addEventListener("click", function () {
      var text = (who() ? "To: " + who().email + "\\n" : "") + "Subject: " + subj.value + "\\n\\n" + body.value;
      function ok() { done.textContent = "Copied. Paste it into an email."; setTimeout(function () { done.textContent = ""; }, 4000); }
      function fallback() {
        body.focus(); body.select();
        try { if (window.document.execCommand("copy")) return ok(); } catch (e) {}
        done.textContent = "Select the message and copy it.";
      }
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, fallback);
      else fallback();
    });

    update();
  });
})();
</script>`;
