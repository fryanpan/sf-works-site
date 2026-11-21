// Street Safety Map: the draft dashboard of every person severely injured or killed on San Francisco streets, with
// the High Injury Networks, traffic stress, bike stress and crime as views of the same map.
//
// Bryan, 2026-11-19: "can you turn this map into a separate draft dashboard page to go to
// sf-works.org. And build it so that the same map component in the draft dashboard can be embedded in an article".
// The map is src/safety-map/ (one state object, setState with transitions); the article block is
// src/safety-map/story.mjs. Published as a draft like the Muni dashboard: live, out of the sitemap and every list.
//
// The map fills the screen below the site header (Bryan, 2026-11-19: "have it take up the full page if possible, and
// overlay a simpler set of filters on top of it, that can be hidden away"). The filters are one card in the top-left
// corner that folds to its title: the view, the area, the day and the time of day, with the rest under "More".
// The key with one headline figure sits beside the panel at the bottom and the corner chart bottom-right; a crash card opens over the
// right side. On a phone the panel starts hidden. The whole state is in the address (#view=stress&hood=...), so a view
// can be linked.

import { page } from "../layout.mjs";
import { MAP_HEAD } from "../maplibre.mjs";
import { NAMED_VIEWS, viewTitle } from "../safety-map/views.mjs";
import { ARR_CSS, ARR_SCRIPT, arrangementsHTML } from "../safety-map/arrangements.mjs";
import { SCRIPT, CSS as MAP_CSS, KIT_HEAD, DATA_URL, CRASHES_URL, CHART_SCRIPT, inlineData, STATE, districtsData, causeTree, dataMeta, dataFiles, hoodNames, mapData, throughMeta, whereFromRegions } from "../safety-map/index.mjs";

export const path = "/transportation/street-safety";
export const file = "transportation/street-safety/index.html";
export const sitemap = false;
export const listing = { draft: true, title: "Street Safety Map", line: "Every person severely hurt or killed on SF streets, with the High Injury Network, traffic stress and crime.", parent: "section", order: 4, crumb: "Street Safety Map" };
export const ABOUT = `${path}/about`;
const TITLE = "Street Safety Map";
// Each view's sources, for the source line on a downloaded image.
const IMAGE_SOURCES = { injuries: "SFPD crash reports via DataSF (nwes-mmgh)", stress: "SFMTA traffic counts, Telraam, SFCTA SF-CHAMP",
  through: "MTC Travel Model 1.6 (2023) on SFCTA's SF-CHAMP network", bike: "SFMTA Bike Comfort Index (2023 draft)", crime: "SFPD incident reports via DataSF (wg3w-h783)",
  from: "MTC Travel Model 1.6 (2023) on SFCTA's SF-CHAMP network" };

const M = dataMeta();
// The date the lists show beside this page, the same one its "Data updated" line gives (src/page-dates.mjs).
export const dataUpdated = M.read;
const BCI = mapData().bci;
const F = M.figures;
const LT = mapData().light;
const OT = mapData().others;
const OT_ALL = Object.values(OT).reduce((a, b) => a + b, 0);
const CR = mapData().crime;
const TS = F.through.all;
const T = throughMeta();
const n0 = (v) => Math.round(v).toLocaleString("en-US");

const VIEWS = [["injuries", "Injuries"], ["stress", "Traffic stress"], ["through", "Through traffic"], ["bike", "Bike comfort"], ["crime", "Crime"], ["from", "Where traffic comes and goes"]];
// Every choice below comes from the map's own state module (src/safety-map/state.js), so the controls offer exactly
// what the map filters on: road users, years, times, and the one day grouping (STATE.DAYS).
const USER_LABEL = { "Car or truck": "In a car or truck", "Other": "Other or not stated" };
const opt = (v, l) => `<wa-option value="${String(v).replace(/ /g, "_")}">${l}</wa-option>`;
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
// The day and the time of day as two rows of toggles (Bryan, 2026-11-19: "two multiselect filters
// one for Weekday vs. Weekend. Or another button for custom, to pick which days of week. And another for time of day
// period. Should all fit in two rows"). Nothing pressed in a row is every day, or any time. Weekdays and Weekends take
// turns; "Custom" opens a row of the seven days. Short time names, with the hours on hover. Both rows sit in one
// "When" field (Bryan, 2026-11-19: "Combine day and time onto one control"): closed it says what's
// picked, open it is the two rows in a popover.
const TIME_SHORT = { am: "AM rush", midday: "Midday", pm: "PM rush", evening: "Evening", night: "Night" };
const tog = (attr, v, label, title) => `<wa-button size="small" appearance="outlined" ${attr}="${v}" aria-pressed="false"${title ? ` title="${esc(title)}"` : ""}>${label}</wa-button>`;
const whenControl = `<div class="ss-when" data-filter="days"><p class="ss-lab" id="ss-when-lab">When</p>
    <button type="button" class="ss-field-open" id="ss-when-btn" aria-describedby="ss-when-lab"><span data-when-label>Any time</span><wa-icon library="system" name="chevron-down" variant="solid"></wa-icon></button>
    <wa-popover for="ss-when-btn" placement="bottom-start" without-arrow class="ss-pop ss-when-pop"><div class="wa-stack wa-gap-s">
      <div class="wa-stack wa-gap-2xs"><p class="ss-lab" id="ss-day-lab">Day</p>
      <wa-button-group class="ss-toggles ss-days" label="Day">${tog("data-day", "weekday", "Weekdays")}${tog("data-day", "weekend", "Weekends")}${tog("data-day", "custom", "Custom")}</wa-button-group>
      <wa-button-group class="ss-toggles ss-week" label="Days of the week" hidden>${STATE.WEEK.map((d) => tog("data-wd", d[0], d[1])).join("")}</wa-button-group></div>
      <div class="wa-stack wa-gap-2xs" data-filter="time"><p class="ss-lab" id="ss-time-lab">Time of day</p>
      <wa-button-group class="ss-toggles ss-times" label="Time of day">${STATE.TIMES.map((t) => tog("data-time", t[0], TIME_SHORT[t[0]] || t[1].split(",")[0], t[1])).join("")}</wa-button-group></div>
    </div></wa-popover>
  </div>`;
// The cause filter, as the police report's cause and under it the Vehicle Code section (map.json causes).
const causeTreeHTML = `<wa-tree class="ss-cause" selection="multiple" aria-label="Cause in the police report">${causeTree().map((c) =>
  `<wa-tree-item data-key="${c.key}" data-label="${esc(c.label)}">${esc(c.label)}${c.subs.length > 1 ? c.subs.map((sb) =>
    `<wa-tree-item data-key="${c.key}/${esc(sb.key)}" data-label="${esc(sb.label)}">${esc(sb.label)}</wa-tree-item>`).join("") : ""}</wa-tree-item>`).join("")}</wa-tree>`;
// The two long lists, Area and Cause, open with a box that filters them as you type (Bryan, 2026-11-19, thread
// eoy1gx0chxho). Web Awesome 3.14 has no combobox, so it is a text input at the top of the dropdown: it matches anywhere
// in a name, ignoring case; up and down move through what's left, Enter picks, Escape closes.
const findBox = (id, list, label) => `<input type="search" class="ss-find" id="${id}" role="combobox" aria-controls="${list}" aria-expanded="true" aria-autocomplete="list" autocomplete="off" spellcheck="false" enterkeyhint="done" placeholder="${label}" aria-label="${label}">`;
const areaOpt = (v, l) => `<div role="option" class="ss-opt" id="ss-area-o-${String(v).replace(/[^A-Za-z0-9]/g, "_")}" data-value="${esc(String(v).replace(/ /g, "_"))}" data-label="${esc(l)}" aria-selected="false">${esc(l)}</div>`;
const areaControl = `<div class="ss-area-field"><p class="ss-lab" id="ss-area-lab">Area</p>
    <div class="ss-area-row"><button type="button" class="ss-field-open" id="ss-area-btn" aria-describedby="ss-area-lab" aria-haspopup="listbox"><span data-area-label>All of San Francisco</span><wa-icon library="system" name="chevron-down" variant="solid"></wa-icon></button><wa-button size="small" appearance="plain" data-clear-area aria-label="Clear the area" hidden>&#215;</wa-button></div>
    <wa-popover for="ss-area-btn" placement="bottom-start" without-arrow class="ss-pop ss-find-pop ss-area-pop">${findBox("ss-area-find", "ss-area-list", "Search neighborhoods or districts")}
      <div role="listbox" id="ss-area-list" class="ss-list" aria-labelledby="ss-area-lab">${areaOpt("all", "All of San Francisco")}${areaOpt("draw", "An area you draw on the map")}<hr class="ss-sep">
        <div role="group" class="ss-grp" aria-labelledby="ss-grp-hood"><p class="ss-grp-h" id="ss-grp-hood">Neighborhoods</p>${hoodNames().map((n) => areaOpt(n, n)).join("")}</div>
        <div role="group" class="ss-grp" aria-labelledby="ss-grp-dist"><p class="ss-grp-h" id="ss-grp-dist">Supervisor districts</p>${districtsData().map((d) => areaOpt(`district:${d.district}`, `District ${d.district}`)).join("")}</div></div>
      <p class="ss-none" hidden>No neighborhood or district matches.</p></wa-popover></div>`;

// The filter panel's layout (Bryan, 2026-11-19: "Are you using Web Awesome elements in here? Also
// the layout is atrocious."). One card down the left edge with its own scroll: a header (the filters in force and the
// chevron that folds them) that stays put, and every control the view takes under it, all with Web Awesome's own
// labels, so there is one label style. Spacing is the kit's --wa-space-* tokens and its wa-stack / wa-cluster layout
// classes (styles/utilities.css). On a laptop the key sits beside the panel, not under it, so the panel can run the
// map's full height. The map's title is its own card at the top of the map (Bryan, 2026-11-19:
// "Please move the title into the map itself and in the title explain what the map shows").
// Slot another change fills: #ss-slot-severity (under Show, injuries only).
const CSS = `<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@awesome.me/webawesome@3.14.0/dist-cdn/styles/utilities.css">
<style>
html:has(.ss) { overflow-x: clip; }
/* On a phone the trail drops its section step, as the site does for a four-step trail, so About the data beside Share
   leaves the breadcrumb on one line and the map its height. */
@media (max-width: 520px) { body:has(.ss) .crumbs sl-breadcrumb-item:nth-child(2):nth-last-child(n+2) { display: none; } }
.ss { position: relative; width: 100vw; margin-left: calc(50% - 50vw); height: calc(100dvh - 76px); min-height: 420px; border-top: 1px solid var(--rule); }
.ss { --ss-panel-w: 300px; }
.ss-panel { background: #fff; left: 10px; top: 10px; width: var(--ss-panel-w); max-height: calc(100% - 20px); display: flex; flex-direction: column; z-index: 5; font-size: var(--wa-font-size-s); }
.ss-panel .ss-top { flex: none; display: grid; grid-template-columns: minmax(0, 1fr); align-items: center; padding: var(--wa-space-xs) var(--wa-space-s) var(--wa-space-xs) var(--wa-space-m); }
/* The drawer's header is "Filters" with the chevron right beside it (Bryan, 2026-11-19: "The
   caret is oddly disassociated from the title"; 2026-11-20: "Keep the title as Filters"), and a click folds it. The
   filters in force are the subtitle on the map's title card (.ss-only). */
.ss-panel .ss-sum { grid-row: 1; justify-self: start; max-width: 100%; display: inline-flex; align-items: center; gap: var(--wa-space-2xs); font: inherit; font-weight: var(--wa-font-weight-semibold); color: var(--sm-ink); background: none; border: 0; padding: 2px 0; cursor: pointer; text-align: left; }
.ss-panel .ss-sum-text { min-width: 0; }
.ss-panel .ss-sum wa-icon { flex: none; transition: rotate var(--wa-transition-fast, 150ms); }
.ss-panel.collapsed .ss-sum wa-icon { rotate: -90deg; }
/* Reset filters (Bryan, 2026-11-19: "Add a prominent button to reset filters") sits in the
   header, so it is there with the panel folded too; it shows only while a filter differs from its default. */
.ss-panel .ss-top [data-reset-filters] { grid-row: 3; justify-self: start; margin-top: var(--wa-space-xs); }
/* The headline is the corner chart's title (Bryan, 2026-11-19: "Just show the legend here");
   while a crash card hides the chart it moves here, under the filters. */
.ss-panel .ss-top .ss-headhome { grid-row: 2; margin-top: var(--wa-space-2xs); }
.ss-panel .ss-top .ss-headhome:empty { display: none; }
.ss-panel .ss-top .ss-headhome .sm-head { margin: 0; font-size: var(--wa-font-size-xs); line-height: 1.35; }
.ss-panel .ss-top .ss-headhome .sm-head b { font-size: var(--wa-font-size-s); }
/* The map's title: what it shows and the years, with the data date under it. */
.ss .ss-maptitle { top: 10px; left: calc(var(--ss-panel-w) + 20px); max-width: calc(100% - var(--ss-panel-w) - 150px); padding: 6px 12px; }
.ss .ss-maptitle h1 { margin: 0; font-size: 1.05rem; line-height: 1.25; display: flex; flex-wrap: wrap; align-items: center; gap: 2px var(--wa-space-xs); }
.ss .ss-maptitle wa-badge { font-size: var(--wa-font-size-2xs); font-family: var(--wa-font-family-body); }
.ss .ss-maptitle .data-updated { margin: 2px 0 0; font-size: var(--wa-font-size-xs); color: var(--sm-muted); }
.ss .ss-maptitle .ss-only { margin: 2px 0 0; font-size: var(--wa-font-size-s); line-height: 1.3; color: var(--sm-ink); }
.ss-panel .ss-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: var(--wa-space-xs) var(--wa-space-m) var(--wa-space-m); }
.ss-panel.collapsed .ss-body { display: none; }
.ss-panel.collapsed { width: auto; max-width: var(--ss-panel-w); }
.ss-panel .ss-slot:empty { display: none; }
/* A group whose controls the view all hides takes no gap (the injuries' controls on the crime view). */
.ss-panel .ss-who:not(:has(> :not([hidden]))) { display: none; }
.ss-panel wa-select, .ss-panel wa-slider, .ss-panel wa-tree { width: 100%; }
/* One label style: the kit's own form label, used for the few groups that are not one control. */
.ss-panel .ss-lab { margin: 0 0 var(--wa-space-2xs); font-size: var(--wa-font-size-s); font-weight: var(--wa-form-control-label-font-weight); color: var(--wa-form-control-label-color); line-height: var(--wa-form-control-label-line-height); }
.ss-panel .ss-toggles { display: block; width: 100%; }
.ss-panel .ss-toggles::part(base) { display: flex; width: 100%; }
.ss-panel .ss-toggles wa-button { flex: 1 1 auto; min-width: 0; }
.ss-panel .ss-toggles wa-button::part(base) { padding-inline: var(--wa-space-2xs); font-size: var(--wa-font-size-xs); }
.ss-panel .ss-area-row { display: flex; align-items: center; gap: var(--wa-space-2xs); }
.ss-panel .ss-area-row .ss-field-open { flex: 1; min-width: 0; }
.ss-panel .ss-field-open > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* The filter box stays at the top of its dropdown while the list under it scrolls; --ss-pop-max keeps the dropdown above
   a phone's on-screen keyboard (set from the visual viewport while it is open). */
.ss-find-pop::part(body) { padding-top: 0; max-height: min(var(--ss-pop-max, 60vh), 440px); }
.ss-find { position: sticky; top: 0; z-index: 1; display: block; width: 100%; box-sizing: border-box; margin: 0 0 var(--wa-space-2xs); padding: 6px 8px; font: inherit; font-size: 16px; border: 1px solid var(--wa-form-control-border-color, #c2c7cf); border-radius: var(--wa-form-control-border-radius, 6px); background: #fff; box-shadow: 0 calc(-1 * var(--wa-space-s)) 0 #fff; }
.ss-find:focus { outline: 2px solid var(--wa-color-focus, #0071ec); outline-offset: -1px; }
@media (min-width: 760px) { .ss-find { font-size: var(--wa-font-size-s); } }
.ss-list .ss-opt { padding: 5px 8px; border-radius: 4px; font-size: var(--wa-font-size-s); line-height: 1.3; cursor: pointer; }
.ss-list .ss-opt:hover { background: var(--wa-color-neutral-fill-quiet, #f1f2f4); }
.ss-list .ss-opt[aria-selected="true"] { font-weight: var(--wa-font-weight-semibold); }
.ss-list .ss-opt.ss-active, .ss-cause-pop wa-tree-item.ss-active::part(item) { background: var(--wa-color-brand-fill-quiet, #e6f0fb); }
.ss-list .ss-grp-h { margin: 6px 0 2px; padding: 0 8px; font-size: var(--wa-font-size-xs); font-weight: var(--wa-font-weight-semibold); color: var(--sm-muted); text-transform: uppercase; letter-spacing: 0.04em; }
.ss-list .ss-sep { border: 0; border-top: 1px solid var(--wa-color-neutral-border-quiet, #e3e5e8); margin: 4px 0; }
.ss-none { margin: var(--wa-space-2xs) 0; font-size: var(--wa-font-size-s); color: var(--sm-muted); }
.ss-panel wa-details { border-top: 1px solid var(--wa-color-surface-border); margin: 0 calc(-1 * var(--wa-space-m)); }
.ss-panel wa-details::part(header) { padding: var(--wa-space-s) var(--wa-space-m); font-weight: var(--wa-font-weight-semibold); }
.ss-panel wa-details::part(content) { padding: 0 var(--wa-space-m) var(--wa-space-xs); }
.ss-panel wa-slider::part(references) { font-size: var(--wa-font-size-xs); color: var(--sm-muted); }
/* The layer is its own card above the drawer (Bryan, 2026-11-19: "Move the 'Show' into a
   separate 'Layer' control"), so it stays with the drawer folded. room() sets the drawer's top under it. */
.ss .ss-layer { left: 10px; top: 10px; width: var(--ss-panel-w); padding: var(--wa-space-xs) var(--wa-space-s) var(--wa-space-xs) var(--wa-space-m); background: #fff; font-size: var(--wa-font-size-s); }
.ss .ss-layer wa-select::part(form-control) { display: flex; align-items: center; gap: var(--wa-space-s); }
.ss .ss-layer wa-select::part(form-control-label) { margin: 0; font-weight: var(--wa-font-weight-semibold); }
.ss .ss-layer wa-select::part(form-control-input) { flex: 1; min-width: 0; }
.ss .ss-layer wa-select::part(display-input) { font-size: 0.74rem; letter-spacing: -0.01em; }
/* The layer's own setting under it: the through-traffic distance slider, the where-from toggle. */
.ss .ss-layer .ss-layer-opt { margin-top: var(--wa-space-xs); }
.ss .ss-layer .ss-layer-opt[hidden] { display: none; }
.ss .ss-layer .ss-near-ticks { display: flex; justify-content: space-between; font-size: var(--wa-font-size-2xs); color: var(--sm-muted); margin-top: 2px; }
.ss .ss-layer .ss-toggles { display: block; width: 100%; }
.ss .ss-layer .ss-toggles::part(base) { display: flex; width: 100%; }
.ss .ss-layer .ss-toggles wa-button { flex: 1 1 auto; min-width: 0; }
.ss .ss-layer .ss-toggles wa-button::part(base) { padding-inline: var(--wa-space-2xs); font-size: var(--wa-font-size-xs); }
.ss-panel .ss-field-open { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: var(--wa-space-2xs); font: inherit; font-size: var(--wa-font-size-s); color: var(--sm-ink); text-align: left; min-height: var(--wa-form-control-height-s, 32px); padding: 3px 8px 3px 10px; border: 1px solid var(--wa-form-control-border-color, #c2c7cf); border-radius: var(--wa-form-control-border-radius, 6px); background: #fff; cursor: pointer; }
.ss-pop::part(body) { width: min(320px, calc(100vw - 24px)); max-height: min(60vh, 440px); overflow-y: auto; overscroll-behavior: contain; padding: var(--wa-space-s); }
.ss-pop { --max-width: min(340px, calc(100vw - 24px)); }
/* The cause filter is a field (Bryan, 2026-11-19: "Make this a dropdown that shows little chips in
   multiselect form if I select things -- but opening up the dropdown lets me dig into the hierarchy"): one removable
   chip per picked cause, a whole group as one chip, and the tree in a popover that scrolls inside itself. */
.ss-panel .ss-cause-field { display: flex; flex-wrap: wrap; align-items: center; gap: var(--wa-space-2xs); min-height: var(--wa-form-control-height-s, 32px); padding: 3px 4px 3px 6px; border: 1px solid var(--wa-form-control-border-color, #c2c7cf); border-radius: var(--wa-form-control-border-radius, 6px); background: #fff; }
.ss-panel .ss-cause-tags { display: contents; }
.ss-panel .ss-cause-tags wa-tag { max-width: 100%; min-width: 0; box-sizing: border-box; }
/* A long subcause name ends in an ellipsis inside the field; the chip's tooltip holds the whole name. */
.ss-panel .ss-cause-tags wa-tag::part(content) { display: block; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ss-panel .ss-cause-open { margin-left: auto; display: inline-flex; align-items: center; gap: var(--wa-space-2xs); font: inherit; font-size: var(--wa-font-size-s); color: var(--sm-ink); background: none; border: 0; padding: 2px 4px; cursor: pointer; }
.ss-panel .ss-cause-open:has(span:not(:empty)) { margin-left: 0; flex: 1; justify-content: space-between; }
.ss-cause-pop wa-tree { width: 100%; --indent-size: var(--wa-space-s); }
.ss-cause-pop wa-tree-item::part(label) { font-size: var(--wa-font-size-s); line-height: 1.3; }
.ss-cause-pop wa-tree-item::part(item) { padding: 1px 0; }
.ss-panel wa-tree { --indent-size: var(--wa-space-s); margin-left: calc(-1 * var(--wa-space-xs)); }
.ss-panel wa-tree-item::part(label) { font-size: var(--wa-font-size-s); line-height: 1.3; }
.ss-panel wa-tree-item::part(item) { padding: 1px 0; }
.ss-panel [hidden] { display: none !important; }
.ss-sev { margin-top: 8px; }
/* The severity slider's four steps are dots a reader can see on either side of the handle, the fill runs from half a
   dot before the handle to Killed so the handle's own step is inside it, and each label sits centred under its dot
   (Bryan, 2026-11-19). The track is inset from both ends so the four dots stay evenly spaced and
   the end labels still centre on their dots, and "Other visible" takes two lines so "Complaint of pain" fits (thread
   174ci0tj1nnw). placeTicks() measures the dots, so the labels follow the real track. */
.ss-sev-in { --marker-width: 10px; --marker-height: 10px; --track-size: 6px; }
.ss-panel .ss-sev-in { display: block; width: calc(100% - 60px); margin-inline: 30px; }
.ss-panel .ss-sev-in::part(label) { margin-inline: -30px; }
.ss-sev-in::part(track) { background: #d5dade; }
.ss-sev-in::part(marker) { display: block; background: #fff; border: 2px solid #5b636e; box-sizing: border-box; z-index: 1; }
.ss-sev-in::part(indicator) { margin-inline-start: -9px; padding-inline: 9px 7px; }
.ss-sev-ticks { position: relative; height: 2.4em; font-size: 0.68rem; line-height: 1.15; color: var(--muted); margin-top: 6px; }
.ss-sev-ticks span { position: absolute; top: 0; width: max-content; max-width: 60px; text-align: center; transform: translateX(-50%); white-space: normal; }
.ss-sev-ticks span.at-start { transform: none; text-align: left; }
.ss-sev-ticks span.at-end { transform: translateX(-100%); text-align: right; }
.ss-panel .hinln { display: inline-block; width: 18px; height: 0; border-top: 3px solid; vertical-align: middle; margin-right: 4px; }
/* The key sits beside the open panel on a laptop, so neither runs under the other. */
@media (min-width: 1001px) { .ss:has(.ss-panel:not(.collapsed)) .sm-legend { left: calc(var(--ss-panel-w) + 20px); } }
/* A tablet in portrait: the key stays at the left and stops short of the chart card. */
@media (min-width: 761px) and (max-width: 1000px) { .ss .sm-legend { max-width: calc(100% - 330px); } }
/* A bubble's or a block's popup opens over the layer and filter cards, not under them. */
.ss .maplibregl-popup { z-index: 7; }
.ss .sm-legend:has([data-key]:empty) { display: none; }
/* A phone's card sheet: its close button stays at the top right as the card scrolls. */
.ss .sm-sheet .sm-x { position: sticky; top: 0; float: right; width: 44px; height: 44px; margin: -6px -8px 0 6px; border: 0; background: #fff; font-size: 24px; line-height: 1; color: var(--sm-ink); cursor: pointer; border-radius: 6px; }
.ss .ss-map { position: absolute; inset: 0; }
.ss .ss-map .sm-canvas { height: 100%; border-radius: 0; }
.ss .sm-sheet { position: absolute; left: 6px; right: 6px; bottom: 6px; z-index: 6; margin: 0; max-height: 50%; overflow-y: auto; background: #fff; box-shadow: 0 2px 12px rgba(0,0,0,.18); }
@media (max-width: 760px) {
  .ss { height: calc(100dvh - 64px); }
  .ss-panel { left: 6px; top: 6px; width: calc(100% - 12px); max-height: calc(100% - 12px); }
  .ss-panel.collapsed { width: auto; max-width: calc(100% - 130px); }
  /* The map's buttons stack in one column at the right, so the folded card's 130 px gap clears them. */
  .ss .glmap .maplibregl-ctrl-top-right { flex-direction: column; align-items: flex-end; }
  .ss-panel.collapsed .ss-top { padding: var(--wa-space-2xs) var(--wa-space-s); }
  /* The title spans the top left of the map, clear of the map's buttons; the drawer's top is set under it (room()). */
  .ss .ss-maptitle { left: 6px; top: 6px; right: 104px; max-width: none; padding: 3px 8px; }
  .ss .ss-maptitle h1 { font-size: 0.9rem; }
  .ss .ss-maptitle wa-badge { display: none; }
  .ss .ss-maptitle .data-updated { margin: 0; font-size: 0.68rem; }
  .ss .ss-maptitle .ss-only { margin: 0; font-size: 0.75rem; }
  .ss .ss-layer { left: 6px; width: auto; padding: 2px 8px; }
  .ss .ss-layer wa-select { width: 200px; }
  /* The key and the chart in smaller type, so the overlays a phone opens with leave three quarters of the map clear. */
  .ss .sm-legend .sm-key { font-size: 0.7rem; gap: 0 8px; line-height: 1.35; }
  .ss .sm-legend .sm-key img { width: 15px; height: 15px; }
  .ss .sm-chart { max-height: 20%; }
  /* The where-from layer's name is the longest: its card runs the map's width so the name isn't cut. */
  .ss[data-view="from"] .ss-layer { right: 6px; }
  .ss[data-view="from"] .ss-layer wa-select { width: 100%; }
  /* Where traffic comes from, with an area picked: the chart is a full-width card under the map, so its bars can be
     read and nothing but the title, the layer and the key lies over the map. */
  /* The map takes the top of the screen and the chart follows it at its own height, so the page scrolls to the
     chart's last row and nothing scrolls inside the card. */
  .ss[data-from-area] { height: auto; min-height: calc(100dvh - 64px); overflow: visible; }
  .ss[data-from-area] .ss-map { position: relative; inset: auto; height: 60dvh; }
  .ss[data-from-area] .sm-chart { position: static; width: auto; max-height: none; overflow: visible; border-radius: 0; border-width: 1px 0 0; box-shadow: none; }
  /* The key's one fact, what a circle's area is, is the chart's note there, so the key isn't laid over the map. */
  .ss[data-from-area] .sm-legend { display: none; }
  /* A bubble's card opens over the chart, under the map, so the bubble and the toggle stay in view. */
  .ss[data-from-area] .sm-sheet { top: calc(60dvh + 4px); bottom: auto; max-height: none; }
}
.share-pop .share-download { display: block; margin-top: 8px; font: inherit; font-size: 0.85rem; padding: 4px 10px; border: 1px solid var(--rule); border-radius: 6px; background: #fff; cursor: pointer; }
/* Touch screens (Bryan, 2026-11-20: "Make the tap targets bigger on the injuries slider (and in general, make all tap
   targets at least the recommended minimum on tablet)"). The minimum is 44 px each way (Apple's Human Interface
   Guidelines; WCAG 2.2 success criterion 2.5.5). A slider's handle is drawn 28 px and takes touches 44 px across; the
   severity slider takes them on a 44 px band around its track, and the Years sliders' tracks do too. */
@media (pointer: coarse) {
  .ss-panel wa-slider { --thumb-width: 28px; --thumb-height: 28px; }
  .ss-panel wa-slider::part(thumb)::after { content: ""; position: absolute; inset: -9px; border-radius: 50%; }
  .ss-panel wa-slider::part(track)::before { content: ""; position: absolute; left: -14px; right: -14px; top: calc(50% - 22px); height: 44px; }
  .ss-panel .ss-sev-in::part(slider) { padding-block: 19px; margin-block: -8px; }
  .ss-panel .ss-sev-in { --marker-width: 12px; --marker-height: 12px; }
  .ss-panel wa-slider[range]::part(slider) { padding-block: 14px 4px; margin-inline: 8px; }
  .ss-panel wa-slider[range]::part(references) { margin-top: 12px; }
}
/* On a tablet every other control is at least 44 px tall and wide too. A phone keeps its compact layout. */
@media (pointer: coarse) and (min-width: 700px) {
  .ss { --ss-tap: 44px; }
  .ss wa-select::part(combobox) { min-height: var(--ss-tap); }
  .ss wa-select::part(clear-button) { min-width: var(--ss-tap); min-height: var(--ss-tap); justify-content: center; }
  .ss wa-option { min-height: var(--ss-tap); }
  .ss-panel .ss-sum { min-height: var(--ss-tap); min-width: 100%; }
  .ss-panel .ss-field-open, .ss-panel .ss-cause-open { min-height: var(--ss-tap); }
  .ss-panel .ss-cause-open { min-width: var(--ss-tap); justify-content: flex-end; }
  .ss-panel .ss-cause-field { row-gap: 0; }
  .ss-find { min-height: 44px; height: 44px; }
  .ss-panel .ss-cause-field { padding-block: 0; }
  .ss wa-button::part(base), .ss-pop wa-button::part(base) { min-height: var(--ss-tap); min-width: var(--ss-tap); }
  .ss-panel .ss-toggles wa-button::part(base) { min-width: 0; }
  .ss-pop.ss-when-pop::part(body) { width: min(400px, calc(100vw - 24px)); }
  .ss-pop.ss-when-pop { --max-width: min(420px, calc(100vw - 24px)); }
  .ss-list .ss-opt { min-height: var(--ss-tap); display: flex; align-items: center; box-sizing: border-box; }
  .ss-cause-pop wa-tree-item::part(item) { min-height: var(--ss-tap); }
  .ss-cause-pop wa-tree-item::part(expand-button) { min-width: var(--ss-tap); min-height: var(--ss-tap); }
  .ss-panel .ss-cause-tags wa-tag { height: var(--ss-tap); min-height: var(--ss-tap); padding-inline-end: 0; }
  .ss-panel .ss-cause-tags wa-tag::part(remove-button) { min-width: var(--ss-tap); min-height: var(--ss-tap); display: inline-flex; align-items: center; justify-content: center; }
  .ss .glmap .maplibregl-ctrl-group button { width: var(--ss-tap); height: var(--ss-tap); }
  .ss .glmap .maplibregl-ctrl-attrib-button { width: var(--ss-tap); height: var(--ss-tap); background-position: center; }
  .ss .sm-chart-pick { min-height: var(--ss-tap); }
  .ss .sm-chart-up { min-height: var(--ss-tap); min-width: var(--ss-tap); }
  .ss .sm-key .sm-kbtn { min-height: var(--ss-tap); }
  .ss .maplibregl-popup-close-button { width: var(--ss-tap); height: var(--ss-tap); font-size: 22px; }
}
</style>`;

const Y0 = STATE.YEARS[0], Y1 = STATE.YEARS.at(-1), CY0 = STATE.CRIME_YEARS[0];
const panel = `<div class="sm-ov ss-panel" data-panel>
  <div class="ss-top"><button type="button" class="ss-sum" data-toggle aria-expanded="true" aria-label="Hide the filters"><span class="ss-sum-text">Filters</span><wa-icon library="system" name="chevron-down" variant="solid"></wa-icon></button><div class="ss-headhome" data-headline-home></div><wa-button size="small" variant="brand" appearance="accent" data-reset-filters hidden>Reset filters</wa-button></div>
  <div class="ss-body wa-stack wa-gap-s">
  <div class="ss-slot ss-sev" id="ss-slot-severity" data-filter="severity"><wa-slider class="ss-sev-in" size="small" label="Injuries shown, up to the most severe" min="0" max="3" step="1" value="2" indicator-offset="3" with-markers></wa-slider>
    <div class="ss-sev-ticks" aria-hidden="true">${STATE.SEVERITIES.slice().reverse().map((x) => `<span>${x[1].replace(" injury", "").replace("Other visible", "Other<br>visible")}</span>`).join("")}</div></div>
  ${areaControl}
  ${whenControl}
    <div class="ss-stay wa-stack wa-gap-s">
    <div class="ss-who wa-stack wa-gap-s">
      <wa-select data-filter="user" class="ss-user" multiple with-clear size="small" label="Travel mode of injured party" placeholder="All">${STATE.USERS.map((u) => opt(u, USER_LABEL[u] || u)).join("")}</wa-select>
      <wa-select data-filter="other" class="ss-other" multiple with-clear size="small" label="Other party involved" placeholder="Any">${STATE.OTHERS.map((o) => opt(o[0], o[1])).join("")}</wa-select>
      <wa-slider data-filter="years" class="ss-years" range size="small" label="Years" min="${Y0}" max="${Y1}" step="1" min-value="${STATE.INLINE_FROM}" max-value="${Y1}" with-markers with-tooltip><span slot="reference">${Y0}</span><span slot="reference">${Y1} (partial)</span></wa-slider>
      <div data-filter="cause"><p class="ss-lab" id="ss-cause-lab">Cause in the police report</p>
        <div class="ss-cause-field"><span class="ss-cause-tags" data-cause-tags></span><button type="button" class="ss-cause-open" id="ss-cause-btn" aria-describedby="ss-cause-lab"><span data-cause-open-label>All causes</span><wa-icon library="system" name="chevron-down" variant="solid"></wa-icon></button></div>
        <wa-popover for="ss-cause-btn" placement="bottom-start" without-arrow class="ss-pop ss-find-pop ss-cause-pop">${findBox("ss-cause-find", "ss-cause-tree", "Type a cause")}<p class="ss-none" hidden>No cause matches.</p>${causeTreeHTML.replace("<wa-tree ", '<wa-tree id="ss-cause-tree" ').replace('aria-label="Cause in the police report"', 'aria-labelledby="ss-cause-lab"')}</wa-popover></div>
    </div>
    <!-- The crime view's own filters, in the injuries view's controls (Bryan, 2026-11-19: "Was
         expecting a year selector, time of day selector, kind of crime selector in the filters"). -->
    <div class="ss-crime wa-stack wa-gap-s">
      <wa-select data-filter="crimeKinds" class="ss-kinds" multiple with-clear size="small" label="Kind of crime" placeholder="Every kind">${STATE.CRIME_KINDS.map((k) => opt(k[0], k[1])).join("")}</wa-select>
      <wa-slider data-filter="crimeYears" class="ss-cyears" range size="small" label="Years" min="${CY0}" max="${Y1}" step="1" min-value="${CY0}" max-value="${Y1}" with-markers with-tooltip><span slot="reference">${CY0}</span><span slot="reference">${Y1} so far</span></wa-slider>
    </div>
    <div class="ss-hins wa-stack wa-gap-s" data-filter="network">
      <!-- One network at a time (Bryan, 2026-11-19: "HIN choices should be single select"), and no
           10-mile group choices ("Drop the 'worst to best in 10 mile group' options in the dropdown").
           A link that opens the groups still draws them, and the menu shows their edition. -->
      <wa-select class="ss-hin" size="small" label="High Injury Network" value="2024">
        <wa-option value="none">None</wa-option>
        <wa-option value="2024"><i slot="start" class="hinln" style="border-color:#4a4f57"></i>2024, the current one</wa-option>
        <wa-option value="2022"><i slot="start" class="hinln" style="border-color:#9c5f3c"></i>2022</wa-option>
        <wa-option value="2017"><i slot="start" class="hinln" style="border-color:#c8a25e;border-top-style:dashed"></i>2017</wa-option>
      </wa-select></div>
    </div>
  </div>
</div>`;

// Each cause and subcause key's label, for the drawer's summary.
const CAUSE_LABELS = Object.fromEntries(causeTree().flatMap((c) => [[c.key, c.label], ...c.subs.map((sb) => [`${c.key}/${sb.key}`, `${c.label}: ${sb.label}`])]));
// Each subcause key's short name ("Outside a crosswalk"), for the subtitle.
const SUB_SHORT = Object.fromEntries(causeTree().flatMap((c) => c.subs.map((sb) => [`${c.key}/${sb.key}`, sb.short || sb.label])));

const scriptPage = (preset) => `<script>
(function () {
  var START_FOLDED = ${preset ? "true" : "false"};
  var S = SafetyMapState, root = document.querySelector("[data-ss]"), $ = function (q) { return root.querySelector(q); }, $$ = function (q) { return Array.prototype.slice.call(root.querySelectorAll(q)); };
  // The edges of the map the filter card, the key and the corner chart cover, so a fitted area lands in the open
  // part. On a phone the card folds after a pick, so only its folded bar and the key below count.
  function fitPadding(mode) {
    var r = root.getBoundingClientRect(), box = function (sel) { var e = root.querySelector(sel); return e && !e.hidden && e.offsetWidth ? e.getBoundingClientRect() : null; };
    var pan = box("[data-panel]"), leg = box(".sm-legend"), ch = box("[data-chart]"), ttl = box("[data-maptitle]"), m = 16;
    // The map itself can stop above the chart (a phone's where-from view), so the bottom edge is the map's own.
    var mp = root.querySelector(".ss-map").getBoundingClientRect();
    // The where-from view's frame of every bubble on a tablet: under the filter card, left of the chart, above the key.
    if (mode === "all" && r.width >= 760) return { top: Math.max(pan ? pan.bottom - r.top : 0, ttl ? ttl.bottom - r.top : 0) + m, bottom: (leg ? r.bottom - leg.top : 0) + m, left: m, right: (ch ? r.right - ch.left : 0) + m };
    var p = r.width < 760
      ? { top: (pan && folded() ? pan.bottom - r.top : 60) + m, bottom: Math.max(0, leg ? mp.bottom - leg.top : 0, ch ? mp.bottom - ch.top : 0) + m, left: m, right: m }
      : { top: (ttl ? ttl.bottom - r.top : m) + m, bottom: m * 2, left: (pan ? pan.right - r.left : 0) + m, right: (ch ? r.right - ch.left : 0) + m };
    // Padding wider than the map leaves nothing to fit into: fall back to a plain margin.
    return p.left + p.right > r.width - 120 || p.top + p.bottom > mp.height - 120 ? m * 2 : p;
  }
  var BCI_LABELS = ${JSON.stringify(BCI.labels.map((l) => l.replace(" - ", " to ")))}, CAUSES = ${JSON.stringify(CAUSE_LABELS)}, USER_LABEL = ${JSON.stringify(USER_LABEL)}, SUBS = ${JSON.stringify(SUB_SHORT)}, TREE = ${JSON.stringify(causeTree().map((c) => ({ key: c.key, label: c.label })))};
  function folded() { return $("[data-panel]").classList.contains("collapsed"); }
  var askedArea = false;
  var ctl = SafetyMap.create(root.querySelector(".ss-map"), { lib: maplibregl, basemap: sfMap, cards: CrashCards, state: SafetyMapState, routes: window.muniRoutes, districts: ${JSON.stringify(districtsData())},
    dataUrl: ${JSON.stringify(DATA_URL)}, crashesUrl: ${JSON.stringify(CRASHES_URL)}, hash: true,
    cardHost: $("[data-card]"), sheetHost: $("[data-sheet]"), onChange: sync, fitPadding: fitPadding,
    keyBox: function () { var e = root.querySelector(".sm-legend"); return e && !e.hidden && e.offsetWidth ? e.getBoundingClientRect() : null; } });
  var overlay = SafetyOverlay.attach(ctl, { key: $(".sm-legend [data-key]"), headline: $("[data-headline]"), headlineHome: $("[data-headline-home]"), chart: $("[data-chart]"), picker: true,
    noWhere: function (s) { return !!s.filter.area; } });
  var arr = SafetyArrangements.attach($("[data-arr]"));
  var syncing = false, u = function (v) { return String(v).replace(/ /g, "_"); }, un = function (v) { return String(v).replace(/_/g, " "); };
  var customDays = false;
  // The Years slider's tooltip prints a year as a year, not as a number with a thousands comma (Bryan, 2026-11-19,
  // "Nobody puts a comma in a year").
  $$(".ss-years, .ss-cyears").forEach(function (c) { c.valueFormatter = function (v) { return String(v); }; });
  // State to controls.
  function sync(s) {
    // The page draws one High Injury Network at a time (Bryan, 2026-11-19: "HIN choices should be
    // single select"); a link naming several, from before, keeps the newest (STATE.HINS runs newest first). The story
    // still sets two editions side by side, so the state allows it.
    if (s.hin.length > 1) { var one = [s.hin[0]]; Promise.resolve().then(function () { ctl.setState({ hin: one }); }); }
    syncing = true;
    var f = s.filter;
    // The street-arrangement carousel shows only with Pedestrian violation picked on the cause chart.
    if (arr) arr.sync(s, S);
    // On a phone the where-from view with an area puts its chart under the map (the CSS reads this attribute).
    root.toggleAttribute("data-from-area", s.view === "from" && !!f.area);
    root.setAttribute("data-view", s.view);
    // The view asks for an area, and on a phone the Area control is inside the folded filter card: unfold it once.
    if (s.view === "from" && !f.area && folded() && root.getBoundingClientRect().width < 760 && !askedArea) { askedArea = true; Promise.resolve().then(function () { showPanel(true); }); }
    // Once an area is picked the card folds again, so the map under it shows.
    if (askedArea && s.view === "from" && f.area && !folded() && root.getBoundingClientRect().width < 760) Promise.resolve().then(function () { showPanel(false); });
    if (s.view !== "from" || f.area) askedArea = false;
    $$(".ss-view").forEach(function (g) { g.value = s.view; });
    // The layer's own setting: the distance slider on Through traffic, the three-way toggle on Where traffic comes from.
    $$("[data-layer-opt]").forEach(function (d) { d.hidden = d.dataset.layerOpt !== s.view; });
    $$(".ss-near").forEach(function (c) { c.value = S.NEARS.map(function (n) { return n[0]; }).indexOf(s.near); });
    $$("[data-ends]").forEach(function (b) { var on = b.dataset.ends === s.ends; b.setAttribute("aria-pressed", on ? "true" : "false"); b.appearance = on ? "filled" : "outlined"; b.variant = on ? "brand" : "neutral"; });
    $$(".ss-hin").forEach(function (c) { c.value = ({ groups: "2024", groups22: "2022" })[s.hin[0]] || s.hin[0] || "none"; });
    $$(".ss-user").forEach(function (c) { c.value = f.user.map(u); });
    $$(".ss-other").forEach(function (c) { c.value = f.other.slice(); });
    $$(".ss-sev-in").forEach(function (c) { c.value = 3 - S.sevLevel(f.severity); });
    // The day and time toggles: a pressed button is filled.
    var wd = S.weekdays(f.days) || [], single = f.days.length && f.days[0] !== "weekday" && f.days[0] !== "weekend";
    if (single) customDays = true;
    var mark = function (b, on) { b.setAttribute("aria-pressed", on ? "true" : "false"); b.appearance = on ? "filled" : "outlined"; b.variant = on ? "brand" : "neutral"; };
    $$("[data-day]").forEach(function (b) { mark(b, b.dataset.day === "custom" ? customDays : !customDays && f.days[0] === b.dataset.day); });
    $(".ss-week").hidden = !customDays;
    // The When field's closed face: the day and the time picked, or "Any time".
    var dl = S.whenLabel({ days: f.days, time: [] }), tl = S.whenLabel({ days: [], time: f.time }), takesT = (S.FILTERS[s.view] || []).indexOf("time") >= 0;
    $("[data-when-label]").textContent = [dl, takesT ? tl : null].filter(Boolean).join(" \u00b7 ") || "Any time";
    $$("[data-wd]").forEach(function (b) { mark(b, customDays && f.days.length > 0 && wd.indexOf(S.WEEK.filter(function (d) { return d[0] === b.dataset.wd; })[0][2][0]) >= 0); });
    $$("[data-time]").forEach(function (b) { mark(b, f.time.indexOf(b.dataset.time) >= 0); });
    var y = f.years || [S.YEARS[0], S.YEARS[S.YEARS.length - 1]];
    $$(".ss-years").forEach(function (c) { c.minValue = y[0]; c.maxValue = y[1]; });
    var cy = f.crimeYears || [S.CRIME_YEARS[0], S.CRIME_YEARS[S.CRIME_YEARS.length - 1]];
    $$(".ss-cyears").forEach(function (c) { c.minValue = cy[0]; c.maxValue = cy[1]; });
    $$(".ss-kinds").forEach(function (c) { c.value = f.crimeKinds.slice(); });
    $$(".ss-cause wa-tree-item").forEach(function (it) {
      var k = it.dataset.key, whole = k.split("/")[0];
      it.selected = f.cause.indexOf(k) >= 0 || f.cause.indexOf(whole) >= 0;
      if (f.cause.some(function (e) { return e.split("/")[0] === k && e !== k; })) it.expanded = true;
    });
    causeTags(f.cause);
    var a = f.area;
    var av = !a ? "all" : a.hood ? u(a.hood) : a.district ? "district:" + a.district : "draw";
    $$("#ss-area-list .ss-opt").forEach(function (o) { o.setAttribute("aria-selected", o.dataset.value === av ? "true" : "false"); });
    $("[data-area-label]").textContent = !a ? "All of San Francisco" : a.hood || (a.district ? "District " + a.district : "An area you draw on the map");
    $("[data-clear-area]").hidden = !a;
    $("[data-reset-filters]").hidden = JSON.stringify(f) === JSON.stringify(S.DEFAULTS.filter);
    // Each control shows only on the views that take its filter (STATE.FILTERS).
    var takes = S.FILTERS[s.view] || [];
    $$("[data-filter]").forEach(function (d) { d.hidden = takes.indexOf(d.dataset.filter) < 0; });
    syncing = false;
    retitle(s);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: S.toHash(s) }));
  }
  // The cause field's chips: one per picked cause or subcause, as the state holds them (a group picked whole is its
  // own key, so it is one chip). The × on a chip drops that pick.
  function causeTags(picked) {
    var box = $("[data-cause-tags]");
    box.innerHTML = "";
    picked.forEach(function (k) {
      var t = document.createElement("wa-tag");
      t.size = "small"; t.withRemove = true; t.setAttribute("with-remove", ""); t.textContent = CAUSES[k] || k; t.title = CAUSES[k] || k;
      t.addEventListener("wa-remove", function () { ctl.setState({ filter: { cause: ctl.getState().filter.cause.filter(function (x) { return x !== k; }) } }); });
      box.appendChild(t);
    });
    $("[data-cause-open-label]").textContent = picked.length ? "" : "All causes";
    $("#ss-cause-btn").setAttribute("aria-label", picked.length ? "Change the causes" : "All causes: choose causes");
  }
  // The map's title says what it shows and over which years (Bryan, 2026-11-19: "e.g. 'Map of
  // Injuries and Deaths in San Francisco (2024-2026)'"). The severity names the injuries; every other filter is in the
  // drawer's header, one place per fact.
  var NOUN = { killed: "Deaths", severe: "Injuries and Deaths", visible: "Visible Injuries and Deaths", pain: "All Reported Injuries and Deaths" };
  var VIEW_TITLE = { stress: "Traffic Stress", through: "Through Traffic", bike: "Bike Comfort", crime: "Crime" };
  var VIEW_SPAN = { stress: "", through: " (2023 Model)", bike: " (2023)" };
  // The crime view's title follows its Years filter (Bryan, 2026-11-19).
  var span = function (y, all) { y = y || all; return " (" + (y[0] === y[1] ? y[0] : y[0] + "–" + y[1]) + ")"; };
  var ENDS_TITLE = { from: "Where Traffic Comes From", to: "Where Traffic Goes", both: "Where Traffic Comes From and Goes" };
  function mapTitle(s) {
    if (s.view === "from") { var ar = s.filter.area; return ENDS_TITLE[s.ends] + (ar ? (ar.hood ? " for " + ar.hood : ar.district ? " for District " + ar.district : " for a Drawn Area") : "") + " (2023 Model)"; }
    if (s.view === "crime") return "Map of Crime in San Francisco" + span(s.filter.crimeYears, [S.CRIME_YEARS[0], S.CRIME_YEARS[S.CRIME_YEARS.length - 1]]);
    if (s.view !== "injuries") return "Map of " + VIEW_TITLE[s.view] + " in San Francisco" + VIEW_SPAN[s.view];
    var y = s.filter.years || [S.YEARS[0], S.YEARS[S.YEARS.length - 1]];
    return "Map of " + (NOUN[s.filter.severity] || NOUN.severe) + " in San Francisco (" + (y[0] === y[1] ? y[0] : y[0] + "–" + y[1]) + ")";
  }
  // The filters in force that the title doesn't name, as the subtitle under it: "Only showing pedestrian violations"
  // (Bryan, 2026-11-20: "Keep the title as Filters. Subtitle on the title panel should say 'Only showing pedestrian
  // violations' above the Date updated blurb"). Empty with none set. Only the filters the view takes count.
  var WHO = { "Walking": "people walking", "Biking": "people biking", "Motorcycle or moped": "people on motorcycles or mopeds", "Scooter or board": "people on scooters or boards",
    "Car or truck": "people in cars or trucks", "Other": "other road users" };
  var WITH = { none: "no other vehicle", foot: "a person on foot", car: "a car or truck", moto: "a motorcycle or moped", bike: "a bike or scooter", parked: "a parked vehicle", multiple: "multiple vehicles", unknown: "an unknown vehicle" };
  var CAUSE_ONLY = { "pedestrian-violation": "pedestrian violations", "other": "crashes with another cause", "unknown-or-not-stated": "crashes with no cause stated" };
  function or(a, word) { return a.length < 3 ? a.join(" " + word + " ") : a.slice(0, -1).join(", ") + " " + word + " " + a[a.length - 1]; }
  function lower(t) { return /^[A-Z]{2,}/.test(t) ? t : t.charAt(0).toLowerCase() + t.slice(1); }
  function causeOnly(k) {
    var top = k.split("/")[0], node = TREE.filter(function (c) { return c.key === top; })[0], lab = node ? node.label : top;
    var whole = CAUSE_ONLY[top] || lower(lab) + " crashes";
    return k === top ? whole : whole + " (" + lower(SUBS[k] || k.slice(top.length + 1)) + ")";
  }
  function summary(s) {
    var f = s.filter, takes = S.FILTERS[s.view] || [], out = [], has = function (k) { return takes.indexOf(k) >= 0; };
    if (has("user") && f.user.length) out.push(or(f.user.map(function (x) { return WHO[x] || x; }), "and"));
    if (has("other") && f.other.length) out.push("crashes with " + or(f.other.map(function (x) { return WITH[x] || x; }), "or"));
    if (has("crimeKinds") && f.crimeKinds.length) { var kn = S.CRIME_KINDS.filter(function (k) { return f.crimeKinds.indexOf(k[0]) >= 0; }).map(function (k) { return lower(k[1]); }); out.push(kn.length <= 2 ? or(kn, "and") + " reports" : kn.length + " kinds of crime"); }
    if (has("cause") && f.cause.length) { var cn = f.cause.map(causeOnly); out.push(cn.length <= 2 ? or(cn, "and") : cn[0] + " and " + (cn.length - 1) + " more causes"); }
    var when = (has("days") || has("time")) && S.whenLabel({ days: has("days") ? f.days : [], time: has("time") ? f.time : [] });
    if (when) out.push(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\\b/.test(when) ? when : lower(when));
    if (has("network") && f.hin !== "all") out.push(f.hin === "on" ? "on the High Injury Network" : "off the High Injury Network");
    if (has("hinGroup") && f.hinGroup.length) out.push(f.hinGroup.length === 1 ? "High Injury Network miles, group " + f.hinGroup[0] : f.hinGroup.length + " High Injury Network groups");
    if (s.view === "injuries" && f.at !== "all") out.push(f.at === "intersection" ? "at intersections" : "midblock");
    if (has("bci") && f.bci.length) out.push("Bike Comfort Index " + f.bci.map(function (k) { return BCI_LABELS[k]; }).join(", "));
    // The where-from view's title names its area, and its map shows the whole bay, so the subtitle leaves it out.
    if (has("area") && f.area && s.view !== "from") out.push(f.area.hood ? "in " + f.area.hood : f.area.district ? "in District " + f.area.district : "in a drawn area");
    // With the area alone, or first, it reads "Only showing South of Market".
     if (out.length) out[0] = out[0].replace(/^in (?!a drawn)/, "");
    return out.length ? "Only showing " + out.join(", ") : "";
  }
  // The subtitle sits between the title and the page's "Data updated" line, which the layout puts right under the h1.
  var only = document.createElement("p");
  only.className = "ss-only"; only.setAttribute("data-only", ""); only.setAttribute("aria-live", "polite"); only.hidden = true;
  (function () { var box = root.querySelector("[data-maptitle]"), h1 = box.querySelector("h1"); box.insertBefore(only, h1.nextSibling); })();
  function retitle(s) {
    var t = mapTitle(s), sum = summary(s);
    $("[data-title]").textContent = t;
    only.textContent = sum; only.hidden = !sum;
    // The tab names the filters too, for a shared link or a bookmark.
    document.title = (S.title(s, TREE, 60) || t) + " — SF Works";
  }
  // Controls to state.
  // On a phone the panel folds away after each pick, so the map shows the result (tool-ux-guidelines rule 12).
  var phone = window.innerWidth < 760;
  function on(sel, ev, fn) { $$(sel).forEach(function (el) { el.addEventListener(ev, function () { if (syncing) return; fn(el); if (phone && !el.closest(".ss-stay")) showPanel(false); }); }); }
  on(".ss-view", "change", function (g) { ctl.setState({ view: g.value, crash: null, chart: null }, { duration: 300 }); });
  on(".ss-near", "change", function (c) { var n = S.NEARS[Math.round(Number(c.value))]; if (n) ctl.setState({ near: n[0] }); });
  $$(".ss-near").forEach(function (c) { c.valueFormatter = function (v) { var n = S.NEARS[Math.round(Number(v))]; return n ? n[2] : ""; }; });
  on(".ss-hin", "change", function (c) { ctl.setState({ hin: c.value === "none" ? [] : [c.value] }, { duration: 300 }); });
  on(".ss-user", "change", function (c) { ctl.setState({ filter: { user: (c.value || []).map(un) } }); });
  on(".ss-other", "change", function (c) { ctl.setState({ filter: { other: c.value || [] } }); });
  // The severity slider runs from the least severe at the left to killed at the right (Bryan, 2026-11-19, thread
  // kbu8rjlgd9me: "More natural to have most sever on the right"): the handle is the least severe injury shown, and the
  // filled track runs from it to Killed. A position is 3 minus the severity's level in STATE.SEVERITIES.
  on(".ss-sev-in", "change", function (c) { var x = S.SEVERITIES[3 - Math.round(Number(c.value))] || S.SEVERITIES[1]; ctl.setState({ filter: { severity: x[0] } }); });
  // Each tick label centred under its dot, measured from the slider's own markers; a label that would run past the
  // track's end aligns to that end instead.
  function placeTicks() {
    $$(".ss-sev").forEach(function (box) {
      var sl = box.querySelector("wa-slider"), ticks = box.querySelector(".ss-sev-ticks"), tr = sl && sl.shadowRoot && sl.shadowRoot.querySelector('[part~="track"]');
      if (!tr || !ticks.offsetWidth) return;
      var base = ticks.getBoundingClientRect(), T = tr.getBoundingClientRect(), n = ticks.children.length;
      Array.prototype.forEach.call(ticks.children, function (lab, i) {
        var c = T.left + T.width * i / (n - 1), r = { left: c - 5, right: c + 5 }, x = c - base.left;
        lab.style.left = x + "px"; lab.classList.remove("at-start", "at-end");
        var w = lab.offsetWidth;
        if (x - w / 2 < 0) { lab.style.left = Math.max(0, r.left - base.left) + "px"; lab.classList.add("at-start"); }
        else if (x + w / 2 > base.width) { lab.style.left = Math.min(base.width, r.right - base.left) + "px"; lab.classList.add("at-end"); }
      });
    });
  }
  customElements.whenDefined("wa-slider").then(function () { var sl = $(".ss-sev-in"); return sl && sl.updateComplete; }).then(placeTicks);
  if (window.ResizeObserver) $$(".ss-sev-ticks").forEach(function (t) { new ResizeObserver(placeTicks).observe(t); });
  $$(".ss-sev-in").forEach(function (c) { c.valueFormatter = function (v) { var x = S.SEVERITIES[3 - Math.round(Number(v))]; return !x ? "" : x[0] === "killed" ? "Killed" : x[1] + " or worse"; }; });
  // The toggles take several picks in a row, so the panel stays open on a phone after each.
  function press(sel, fn) { $$(sel).forEach(function (b) { b.addEventListener("click", function () { fn(b, ctl.getState().filter); }); }); }
  press("[data-day]", function (b, f) {
    var d = b.dataset.day;
    if (d === "custom") { customDays = !customDays; if (customDays) sync(ctl.getState()); else ctl.setState({ filter: { days: [] } }); return; }
    customDays = false;
    ctl.setState({ filter: { days: f.days.length === 1 && f.days[0] === d ? [] : [d] } });
  });
  press("[data-wd]", function (b, f) {
    var n = S.WEEK.filter(function (d) { return d[0] === b.dataset.wd; })[0][2][0], wd = S.weekdays(f.days) || [];
    wd = wd.indexOf(n) >= 0 ? wd.filter(function (x) { return x !== n; }) : wd.concat([n]);
    ctl.setState({ filter: { days: S.WEEK.filter(function (d) { return wd.indexOf(d[2][0]) >= 0; }).map(function (d) { return d[0]; }) } });
  });
  press("[data-ends]", function (b) { ctl.setState({ ends: b.dataset.ends }); });
  press("[data-time]", function (b, f) {
    var t = b.dataset.time;
    ctl.setState({ filter: { time: f.time.indexOf(t) >= 0 ? f.time.filter(function (x) { return x !== t; }) : f.time.concat([t]) } });
  });
  on(".ss-years", "change", function (c) { ctl.setState({ filter: { years: [Number(c.minValue), Number(c.maxValue)] } }); });
  on(".ss-cyears", "change", function (c) { ctl.setState({ filter: { crimeYears: [Number(c.minValue), Number(c.maxValue)] } }); });
  on(".ss-kinds", "change", function (c) { ctl.setState({ filter: { crimeKinds: c.value || [] } }); });
  // The cause tree: a cause ticked whole is the cause; a cause partly ticked is its ticked subcauses; every cause is none.
  on(".ss-cause", "wa-selection-change", function (t) {
    var out = [], tops = Array.prototype.filter.call(t.children, function (x) { return x.tagName === "WA-TREE-ITEM"; });
    tops.forEach(function (it) {
      if (it.selected) { out.push(it.dataset.key); return; }
      Array.prototype.forEach.call(it.children, function (c) { if (c.tagName === "WA-TREE-ITEM" && c.selected) out.push(c.dataset.key); });
    });
    ctl.setState({ filter: { cause: out.length === tops.length && tops.every(function (x) { return x.selected; }) ? [] : out } });
  });
  var hint = $("[data-hint]");
  function pickArea(v) {
    $(".ss-area-pop").open = false;
    if (phone) showPanel(false);
    // A new area moves the map to it, and All of San Francisco back to the city (camera null fits either).
    var c = { value: v };
    if (c.value === "all") { ctl.cancelDraw(); ctl.setState({ filter: { area: null }, camera: null }, { duration: 600 }); return; }
    var dm = /^district:(\\d+)$/.exec(c.value);
    if (dm) { ctl.cancelDraw(); ctl.setState({ filter: { area: { district: Number(dm[1]) } }, camera: null, crash: null }, { duration: 600 }); return; }
    if (c.value !== "draw") { ctl.cancelDraw(); ctl.setState({ filter: { area: { hood: un(c.value) } }, camera: null, crash: null }, { duration: 600 }); return; }
    if (ctl.getState().filter.area && ctl.getState().filter.area.polygon) return;
    hint.hidden = false;
    if (window.innerWidth < 760) showPanel(false);
    ctl.drawArea().then(function (ring) { hint.hidden = true; if (!ring) sync(ctl.getState()); }, function () { hint.hidden = true; hint.textContent = "The drawing tool didn't load."; hint.hidden = false; });
  }
  $("#ss-area-list").addEventListener("click", function (e) { var o = e.target.closest(".ss-opt"); if (o) pickArea(o.dataset.value); });
  // Type to filter (findBox): items() lists every candidate in order, show(q) hides what doesn't match and returns the
  // number left, pick(el) acts on the highlighted one. The highlight starts on the first item whose own name matches.
  function typeToFilter(pop, input, items, show, pick) {
    var act = null, none = pop.querySelector(".ss-none");
    function visible() { return items().filter(function (el) { return el.getClientRects().length > 0 && el.style.display !== "none"; }); }
    function mark(el) {
      if (act) act.classList.remove("ss-active");
      act = el || null;
      if (act) { act.classList.add("ss-active"); if (act.id) input.setAttribute("aria-activedescendant", act.id); act.scrollIntoView({ block: "nearest" }); }
      else input.removeAttribute("aria-activedescendant");
    }
    function run() {
      var q = input.value.trim().toLowerCase(), n = show(q), v = q ? visible() : [];
      none.hidden = n > 0;
      mark(v.filter(function (el) { return el.dataset.label.toLowerCase().indexOf(q) >= 0; })[0] || v[0]);
    }
    input.addEventListener("input", run);
    input.addEventListener("keydown", function (e) {
      var v = visible(), i = v.indexOf(act);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (v.length) mark(v[e.key === "ArrowDown" ? (i + 1) % v.length : i <= 0 ? v.length - 1 : i - 1]); }
      else if (e.key === "Enter") { e.preventDefault(); if (act || v.length === 1) pick(act || v[0]); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); pop.open = false; var b = document.getElementById(pop.getAttribute("for")); if (b) b.focus(); }
    });
    // Each opening starts with the whole list. A mouse or keyboard puts the cursor in the box; a touch screen waits for
    // a tap on it, so the keyboard doesn't cover the list before it's been seen.
    pop.addEventListener("wa-show", function () { input.value = ""; run(); fitPop(pop); });
    pop.addEventListener("wa-after-show", function () { if (!phone) input.focus(); });
    input.addEventListener("focus", function () { setTimeout(function () { fitPop(pop); }, 300); });
  }
  // The dropdown ends above the on-screen keyboard: the visual viewport shrinks when it opens.
  function fitPop(pop) {
    var vv = window.visualViewport, body = pop.shadowRoot && pop.shadowRoot.querySelector('[part~="body"]');
    if (!vv || !body || !pop.open) return;
    var top = body.getBoundingClientRect().top;
    pop.style.setProperty("--ss-pop-max", Math.max(140, vv.offsetTop + vv.height - top - 8) + "px");
  }
  if (window.visualViewport) window.visualViewport.addEventListener("resize", function () { $$(".ss-find-pop").forEach(fitPop); });
  typeToFilter($(".ss-area-pop"), $("#ss-area-find"), function () { return $$("#ss-area-list .ss-opt"); }, function (q) {
    var n = 0;
    $$("#ss-area-list .ss-opt").forEach(function (o) { var hit = !q || o.dataset.label.toLowerCase().indexOf(q) >= 0; o.style.display = hit ? "" : "none"; if (hit) n++; });
    $("#ss-area-list .ss-sep").style.display = q ? "none" : "";
    // A group's header shows while any of its places match.
    $$("#ss-area-list .ss-grp").forEach(function (g) { g.style.display = Array.prototype.some.call(g.querySelectorAll(".ss-opt"), function (o) { return o.style.display !== "none"; }) ? "" : "none"; });
    return n;
  }, function (o) { pickArea(o.dataset.value); });
  // The cause tree filters the same way: a cause shows when its name or a subcause's name matches, opened to show the
  // matching subcauses; a cause whose own name matches keeps all its subcauses. Enter ticks or unticks the highlighted
  // one, through the tree's own click, and the cursor stays in the box for the next.
  var tree = $("#ss-cause-tree"), treeOpen = {};
  typeToFilter($(".ss-cause-pop"), $("#ss-cause-find"), function () { return $$("#ss-cause-tree wa-tree-item"); }, function (q) {
    var n = 0, has = function (it) { return it.dataset.label.toLowerCase().indexOf(q) >= 0; };
    Array.prototype.forEach.call(tree.children, function (top) {
      if (top.tagName !== "WA-TREE-ITEM") return;
      var subs = Array.prototype.filter.call(top.children, function (c) { return c.tagName === "WA-TREE-ITEM"; });
      var self = !q || has(top), subHit = q ? subs.filter(has) : [];
      top.style.display = self || subHit.length ? "" : "none";
      subs.forEach(function (c) { c.style.display = self || subHit.indexOf(c) >= 0 ? "" : "none"; });
      if (!q) { if (top.dataset.key in treeOpen) { top.expanded = treeOpen[top.dataset.key]; delete treeOpen[top.dataset.key]; } }
      else if (subHit.length) { if (!(top.dataset.key in treeOpen)) treeOpen[top.dataset.key] = top.expanded; top.expanded = true; }
      if (self || subHit.length) n += 1 + (self ? 0 : subHit.length);
    });
    return n;
  }, function (it) {
    // Tick or untick in the state's terms: a cause whole, or its subcauses; every subcause ticked is the cause whole,
    // and every cause ticked is no filter, as the tree's own handler reads it.
    var k = it.dataset.key, p = k.split("/")[0], cur = ctl.getState().filter.cause.slice(), parent = it.parentElement.closest("wa-tree-item");
    var subsOf = function (top) { return Array.prototype.filter.call(top.children, function (c) { return c.tagName === "WA-TREE-ITEM"; }).map(function (c) { return c.dataset.key; }); };
    if (!parent) cur = cur.indexOf(k) >= 0 ? cur.filter(function (x) { return x.split("/")[0] !== k; }) : cur.filter(function (x) { return x.split("/")[0] !== k; }).concat([k]);
    else {
      var subs = subsOf(parent);
      if (cur.indexOf(p) >= 0) cur = cur.filter(function (x) { return x !== p; }).concat(subs.filter(function (x) { return x !== k; }));
      else if (cur.indexOf(k) >= 0) cur = cur.filter(function (x) { return x !== k; });
      else { cur.push(k); if (subs.every(function (x) { return cur.indexOf(x) >= 0; })) cur = cur.filter(function (x) { return x.split("/")[0] !== p; }).concat([p]); }
    }
    var tops = Array.prototype.filter.call(tree.children, function (x) { return x.tagName === "WA-TREE-ITEM"; });
    ctl.setState({ filter: { cause: tops.every(function (t) { return cur.indexOf(t.dataset.key) >= 0; }) ? [] : cur } });
    var f = $("#ss-cause-find"); setTimeout(function () { f.focus(); }, 0);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { ctl.cancelDraw(); hint.hidden = true; } });
  // A phone's card sheet closes on a tap outside it. The map handles its own taps (another bubble swaps the card),
  // and the layer card's toggle keeps the card open and turns it to the new direction.
  document.addEventListener("click", function (e) {
    var sh = $("[data-sheet]"); if (sh.hidden || !ctl.getState().card) return;
    if (e.target.closest && (e.target.closest("[data-sheet]") || e.target.closest(".ss-map") || e.target.closest("[data-layer]"))) return;
    ctl.setState({ card: null });
  });
  // Fold and unfold the filters; the summary of what's set and Reset filters stay on screen. A phone starts folded.
  var tog = $("[data-toggle]");
  function showPanel(v) { $("[data-panel]").classList.toggle("collapsed", !v); tog.setAttribute("aria-label", v ? "Hide the filters" : "Show the filters"); tog.setAttribute("aria-expanded", v ? "true" : "false");
    var st = ctl.getState(); retitle(st); if (ctl.data()) overlay.sync(st); room(); }
  tog.addEventListener("click", function () { showPanel($("[data-panel]").classList.contains("collapsed")); });
  // Every filter back to its default; the view (Show), the network editions and the camera stay.
  $("[data-reset-filters]").addEventListener("click", function () { ctl.cancelDraw(); hint.hidden = true; ctl.setState({ filter: JSON.parse(JSON.stringify(S.DEFAULTS.filter)), highlight: null, crash: null }, { duration: 300 }); });
  $("[data-clear-area]").addEventListener("click", function () { ctl.cancelDraw(); ctl.setState({ filter: { area: null }, camera: null }, { duration: 600 }); });
  if (phone || START_FOLDED) { showPanel(false); }
  // The map fills the screen from wherever the site header ends.
  function fit() { var t = root.getBoundingClientRect().top + window.scrollY; root.style.height = Math.max(420, window.innerHeight - t) + "px"; }
  fit(); window.addEventListener("resize", fit);
  // Where the key sits under the panel (a narrow window, or the folded panel), the panel stops above it and scrolls
  // inside, so a long list of filters never runs under it. Beside it, the panel runs full height. On a phone the map's
  // title spans the top, so the panel starts under it.
  var panel = $("[data-panel]"), legend = root.querySelector(".sm-legend"), mt = $("[data-maptitle]"), layer = $("[data-layer]");
  // The top-left stack: on a phone the map's title, then the layer, then the drawer; on a laptop the layer and drawer.
  function room() {
    if (!panel) return;
    var ph = window.innerWidth < 760, gap = ph ? 6 : 8, top = ph ? mt.offsetTop + mt.offsetHeight + gap : 10;
    layer.style.top = top + "px"; top += layer.offsetHeight + gap;
    panel.style.top = top + "px"; panel.style.maxHeight = (root.clientHeight - top - (ph ? 6 : 10)) + "px";
    if (ph) return;
    var p = panel.getBoundingClientRect(), l = legend.getBoundingClientRect();
    if (l.left < p.right && l.right > p.left) panel.style.maxHeight = Math.max(160, legend.offsetTop - panel.offsetTop - 8) + "px";
  }
  room(); window.addEventListener("resize", room);
  if (window.ResizeObserver) { var ro = new ResizeObserver(room); ro.observe(legend); ro.observe(mt); ro.observe(layer); }
  // "Download image" in the site's Share menu: the map as it stands, with the generated title, the headline figure and
  // the corner chart, and a source line, as one PNG (Bryan, 2026-11-19: "let people share and export the map -- then
  // they have a built-in title"). The basemap tiles are OpenFreeMap's, served with CORS, so the canvas can be read. The
  // map's drawing buffer is read inside a render event, the one moment it still holds the frame.
  var SOURCES = ${JSON.stringify(IMAGE_SOURCES)}, UPDATED = ${JSON.stringify(M.read)};
  var pop = document.getElementById("share-pop");
  if (pop) {
    var dl = document.createElement("button");
    dl.type = "button"; dl.className = "share-download"; dl.textContent = "Download image";
    pop.appendChild(dl);
    dl.addEventListener("click", function () { dl.disabled = true; snapshot().then(function () { dl.disabled = false; }, function (e) { dl.disabled = false; dl.textContent = "Image failed: " + (e && e.message || e); }); });
  }
  function snapshot() {
    var s = ctl.getState(), map = ctl.map(), D = ctl.data();
    var sum = summary(s), title = mapTitle(s) + (sum ? " · " + sum : "");
    var head = ($("[data-headline]").textContent || "").replace(/\\s+/g, " ").trim();
    // The line about people with no location is its own sentence in the saved image.
    var noPlace = $("[data-headline] .sm-unplaced");
    if (noPlace) head = head.replace(noPlace.textContent, ". " + noPlace.textContent);
    var src = "SF Works street safety map \u00b7 data: " + (SOURCES[s.view] || "") + " \u00b7 data updated " + new Date(UPDATED.slice(0, 10) + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
    var mapShot = new Promise(function (res) { map.once("render", function () { res(map.getCanvas().toDataURL("image/png")); }); map.triggerRepaint(); });
    var svg = root.querySelector("[data-chart]:not([hidden]) .sm-chart-slot svg");
    var chartShot = !svg ? Promise.resolve(null) : new Promise(function (res) {
      var c = svg.cloneNode(true), r = svg.getBoundingClientRect();
      c.setAttribute("xmlns", "http://www.w3.org/2000/svg"); c.setAttribute("width", r.width); c.setAttribute("height", r.height);
      var img = new Image(); img.onload = function () { res({ img: img, w: r.width, h: r.height }); }; img.onerror = function () { res(null); };
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(c));
    });
    return Promise.all([mapShot, chartShot]).then(function (got) {
      return new Promise(function (res) { var m = new Image(); m.onload = function () { res([m, got[1]]); }; m.src = got[0]; });
    }).then(function (got) {
      var m = got[0], ch = got[1], el = map.getCanvas(), k = m.width / el.clientWidth, W = m.width, band = Math.round(78 * k);
      var cv = document.createElement("canvas"); cv.width = W; cv.height = m.height + band;
      var g = cv.getContext("2d");
      g.fillStyle = "#fff"; g.fillRect(0, 0, cv.width, cv.height);
      g.fillStyle = "#15181c"; g.font = "600 " + Math.round(20 * k) + "px system-ui, sans-serif"; g.fillText(title, 12 * k, 28 * k);
      g.font = Math.round(13 * k) + "px system-ui, sans-serif"; g.fillText(head, 12 * k, 50 * k);
      g.fillStyle = "#59626f"; g.font = Math.round(11 * k) + "px system-ui, sans-serif"; g.fillText(src, 12 * k, 68 * k);
      g.drawImage(m, 0, band);
      if (ch) {
        var cw = ch.w * k, chh = ch.h * k, x = W - cw - 16 * k, y = cv.height - chh - 16 * k, cp = ctl.chart(), lab = (cp && cp.subtitle) || ctl.chartTitles[S.chartFor(s)] || "";
        g.fillStyle = "rgba(255,255,255,.94)"; g.fillRect(x - 8 * k, y - 26 * k, cw + 16 * k, chh + 34 * k);
        g.fillStyle = "#15181c"; g.font = "600 " + Math.round(12 * k) + "px system-ui, sans-serif"; g.fillText(lab, x, y - 10 * k);
        g.drawImage(ch.img, x, y, cw, chh);
      }
      var a = document.createElement("a");
      a.download = title.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase() + ".png";
      var url = cv.toDataURL("image/png");
      a.href = url; document.body.appendChild(a); a.click(); a.remove();
      return url;
    });
  }
  window.__snapshot = snapshot;   // for a check script
  // The map's own Reset button moves the camera only (to the chosen area, or all of SF); on this page it says so.
  ctl.ready.then(function () { var r = root.querySelector('button[aria-label="Show all of San Francisco"]'); if (r) { r.textContent = "Reset view"; r.setAttribute("aria-label", "Reset the view to the chosen area"); } });
  ctl.ready.then(function () { sync(ctl.getState()); window.__ready = 2; }, function () { window.__ready = 2; });
  window.__ctl = ctl;   // for scripts/street-safety-check.mjs
})();
</script>`;

// A named view (src/safety-map/views.mjs) opens at its state with the filters folded. Framed in a board doc it drops
// the site's masthead and footer and asks the frame for a map-sized height.
const EMBED_CSS = `<style>
.ss-embed .masthead, .ss-embed .freshness, .ss-embed .about-link { display: none; }
.ss-embed .wrap { padding-top: 0; padding-bottom: 0; }
.ss-embed .ss { border-top: 0; }
</style>`;
const presetScript = ([name, hash]) => `<script>
(function () {
  if (!location.hash && ${JSON.stringify(hash)}) history.replaceState(null, "", location.pathname + location.search + "#" + ${JSON.stringify(hash)});
  if (window.self === window.top) return;
  document.documentElement.classList.add("ss-embed");
  function size() { parent.postMessage({ type: "sfworks:height", block: ${JSON.stringify(name)}, height: window.innerWidth < 600 ? 560 : 620 }, "*"); }
  size(); window.addEventListener("resize", size);
})();
</script>`;

export function render(preset = null) {
  const vt = preset && viewTitle(preset[1], causeTree());
  const body = `${preset ? presetScript(preset) + EMBED_CSS : ""}${KIT_HEAD}
${MAP_CSS}
${CSS}
${ARR_CSS}
<div class="ss sm-stage" data-ss>
  <div class="ss-map"></div>
  <div class="sm-ov ss-maptitle" data-maptitle><h1><span data-title>Map of Injuries and Deaths in San Francisco (${STATE.INLINE_FROM}–${Y1})</span> <wa-badge variant="neutral" appearance="outlined">Draft</wa-badge></h1></div>
  <div class="sm-ov ss-layer" data-layer><wa-select class="ss-view" value="injuries" size="small" label="Layer">${VIEWS.map(([v, l]) => opt(v, l)).join("")}</wa-select>
    <div class="ss-layer-opt" data-layer-opt="through" hidden><wa-slider class="ss-near" size="small" label="Through: neither trip end within" min="0" max="${STATE.NEARS.length - 1}" step="1" value="${STATE.NEARS.findIndex((n) => n[0] === STATE.DEFAULTS.near)}" with-markers with-tooltip></wa-slider>
      <div class="ss-near-ticks" aria-hidden="true">${STATE.NEARS.map((n) => `<span>${n[1]}</span>`).join("")}</div></div>
    <div class="ss-layer-opt" data-layer-opt="from" hidden><wa-button-group class="ss-toggles ss-ends" label="Which trips">${STATE.ENDS.map((e) => tog("data-ends", e[0], e[1])).join("")}</wa-button-group></div></div>
  ${panel}
  <div class="sm-ov sm-hint" data-hint hidden>Click the map to add corners; click the first corner or double-click to finish. Esc cancels.</div>
  <div class="sm-ov sm-legend"><div class="sm-key" data-key></div></div>
  <div class="sm-ov sm-chart" data-chart hidden><p class="sm-head" data-headline aria-live="polite"></p><div class="sm-chart-slot"></div></div>
  ${arrangementsHTML()}
  <div class="sm-ov sm-cardslot" data-card></div>
  <div class="sm-sheet" data-sheet hidden></div>
</div>
${MAP_HEAD}
${inlineData()}
${SCRIPT}
${ARR_SCRIPT}
${CHART_SCRIPT}
${scriptPage(preset)}`;
  return page({
    title: vt || TITLE,
    description: "Every person severely injured or killed on San Francisco streets from 2022 to 2024, with the High Injury Network, traffic stress, bike comfort and crime as views of the same map.",
    path: preset ? `${path}/view/${preset[0]}` : path,
    body,
    dataUpdated,
    directory: false,
    topLink: { href: ABOUT, label: "About the data" },
  });
}

/** The About page, the map's data files and its named views, published beside the dashboard. */
export function pages() {
  return [{ path: ABOUT, file: `${ABOUT.slice(1)}/index.html`, html: aboutPage(), sitemap: false }, ...dataFiles(),
    ...NAMED_VIEWS.map((v) => ({ path: `${path}/view/${v[0]}`, file: `${path.slice(1)}/view/${v[0]}/index.html`, html: render(v), sitemap: false }))];
}

function aboutPage() {
  const body = `<h1>About the Street Safety Map</h1>
<p class="lede">What each view of the <a href="${path}">Street Safety Map</a> counts, where it comes from and how we placed it.</p>
<h2>Injuries</h2>
<p>Each icon is one person severely injured or killed in an SFPD crash report, ${n0(F.people)} people from 2022 to 2024, ${n0(F.killed)} of them killed (<a href="https://data.sfgov.org/d/nwes-mmgh">DataSF nwes-mmgh</a>, one row per person). Each sits at the report's own geocoded point, which SFPD puts on the street centerline, so a crash recorded at an intersection sits at the corner, not in the crosswalk. People hurt at the same point stack up. Deaths after 2024 come from the city's <a href="https://data.sfgov.org/d/dau3-4s8f">Vision Zero fatality log</a> and news reports we checked on date and place; they're drawn but left out of the counts, which cover the police reports only.</p>
<p>Zoomed out, the people show as a heat map, and its shades are scaled to what it shows: the darkest shade is the 99th percentile of density among the people the filters keep in the current view, recomputed as the filters or the view change, so a handful of people stays as visible as every injury since 2005. The crime map is scaled the same way. We follow deck.gl's heat map, which takes its colour range from the densest point in view, and use the 99th percentile rather than the maximum so that one hotspot can't wash out the rest.</p>
<p>A person is on the High Injury Network when a network line runs within 60 ft of their point, the same rule for the <a href="https://www.sfmta.com/blog/new-high-injury-network-map-helps-guide-us-safer-city">2024</a>, <a href="https://data.sfgov.org/d/8vtn-qytr">2022</a> and 2017 editions. On that rule ${n0(F.on_hin_2024)} of the ${n0(F.people)} are on the 2024 network and ${n0(F.off_hin_2024)} are off it. Zoomed out, a heat map shows where people were hurt, a death counting three times.</p>
<p>The injury slider follows the police report's own four levels, as DataSF labels them: Fatal Injury, Severe Injury, Other Visible Injury and Complaint of Pain. It shows the chosen level and every level more severe, and starts at severe injuries and deaths, the two levels the city's High Injury Network counts. The two lower levels add ${n0(LT.visible)} people with another visible injury and ${n0(LT.pain)} with a complaint of pain from 2005 to ${LT.newest.slice(0, 4)}, from the same dataset. We couldn't reproduce a city-published total for those two levels, so treat their counts as the police reports as published, not an official tally.</p>
<p>The years run from 2005, the dataset's first, to its newest report, ${LT.newest}, so ${LT.newest.slice(0, 4)} is not yet complete, and the map opens on 2021 to now. The person icons are the severe injuries and deaths of 2022 to 2024; every other year and level is a dot at the report's point, read from the same dataset the same way. Every icon and dot opens its crash's card, in every year and at every level. Years before 2021 load when the Years slider reaches back. A police-reported death the fatality log also lists is drawn once, as the log's entry, and counted once, from the police report. ${n0(F.no_place)} of the ${n0(OT_ALL)} people in the police reports have no location in San Francisco in the record. They count in the headline and in every chart and filter that doesn't need a place, and they aren't on the map.</p>
<p>The 10-mile groups rank the 2024 High Injury Network the way the Department of Public Health ranks streets in its <a href="https://archivesystemprodsa.blob.core.windows.net/website-archive/visionzerosf-org/wp-content/uploads/2023/03/2022_Vision_Zero_Network_Update_Methodology.pdf">2022 network methodology</a>: severe and fatal injuries per mile on overlapping quarter-mile stretches of a street, each block taking the rate of its worst stretch, with no extra weight for a death. Blocks are then taken worst first and cut every 10 miles of network, a block going to the group its first foot falls in. The map ranks on 2020 to 2024 by default, or on 2022 to 2024. Each year's worst 10 miles is the same ranking run on one year's injuries over every street, not only the network, and the chart says how much of it was also the year before's worst.</p>
<p>The groups chart counts each person on the network segment nearest them within 60 ft, the map's own rule for being on the network; where two segments are equally near, usually at a corner, the one with the lower city segment id takes them. A street shorter than a quarter mile is ranked as one quarter-mile section. A year's worst 10 miles measures street length once where a street is drawn as two roadways, so both roadways are drawn, and a block nobody was hurt on that year can make the list on its neighbours' injuries, since each block takes its worst section's rate.</p>
<p>The cause is the one primary collision factor the officer recorded for the crash, a California Vehicle Code section, grouped into ${causeTree().length} causes (red light, unsafe speed, a pedestrian violation and so on). Under each cause the filter lists the sections themselves, with sections fewer than 3 people share pooled as "Other". It's the police's reading of who broke which rule, not a finding of fault. "How they travelled" is the person's own party in the report: walking, biking, on a motorcycle or moped, on a scooter or board, or in a car or truck. "Other party involved" reads the crash's other rows in the <a href="https://data.sfgov.org/d/8gtc-pjc6">party records</a> the same way and puts each of the ${n0(OT_ALL)} people in the police reports since 2005 in one group: no other vehicle, nobody else in the crash (${n0(OT.none)}); a person on foot and no vehicle (${n0(OT.foot)}); one car or truck, any motor vehicle that isn't a motorcycle (${n0(OT.car)}); one motorcycle or moped (${n0(OT.moto)}); one bike or scooter, meaning a bicycle, e-bike, scooter, board or other non-motor vehicle (${n0(OT.bike)}); only parked vehicles (${n0(OT.parked)}); multiple vehicles, two or more other moving vehicles (${n0(OT.multiple)}); or one unknown vehicle, where the report doesn't state its type or it left the scene unidentified (${n0(OT.unknown)}). ${n0(mapData().othersUnknownTo2012)} of the unknown vehicles are from 2005 to 2012, the years the city takes from the state's crash records and not from SFPD's own systems (the <a href="https://data.sfgov.org/d/8gtc-pjc6">party records</a>' description). From April to December 2018 SFPD's records list almost no parked vehicles, so people who hit one in those months appear under no other vehicle.</p>
<p>The crash cards join each person's report to the crash and party records (<a href="https://data.sfgov.org/d/ubvf-ztfx">crashes</a>, <a href="https://data.sfgov.org/d/8gtc-pjc6">parties</a>) and draw the streets from the <a href="https://data.sfgov.org/d/3psu-pn9h">street centerlines</a>. DataSF publishes each report's coded fields and no officer's narrative, so a card's account is those fields in words: who each party was, what the report says they were doing, how badly each person was hurt, who it marks most at fault and the primary collision factor. A person with "no injury recorded" has no row in the victims table, which lists only the people hurt.</p>
<p>Each crash card's drawing shows the city's street centrelines around the crash, north up. The arrows are each party's direction of travel as the report records it. The record doesn't say whether a turning party's direction is before or after the turn, so a turn is drawn as a curve where only one reading fits the streets, dashed where both fit, and as a straight arrow with the turn named where neither does. Each vehicle is drawn on its street, on the right-hand side for its direction. The city's file pulls the two halves of a divided street together at each junction, so we draw each half straight through instead. A party whose recorded street or direction fits no street in the drawing is listed under it with an asterisk and an arrow for the recorded direction. The dashed ring is where the report places the crash; the record names no crosswalk and no point of impact. A party with someone hurt takes the map's colour for the worst injury in it, and the rest are grey.</p>
<p>A death in the <a href="https://data.sfgov.org/d/dau3-4s8f">Vision Zero fatality log</a> that the police have also reported is one person on the map, drawn where the log puts it, with the police report's cause, other party and place. ${n0(F.deaths_outside_police_reports)} deaths, from the log or the news, have no police report we can match yet. They're drawn on the map but left out of every count, chart and heat map, and they carry no cause, other party, neighborhood or place type, so those filters take them off the map.</p>
<h2>Traffic Stress</h2>
<p>Cars both ways in the busiest weekday hour on every surface street block. Measured blocks are <a href="https://www.sfmta.com/TrafficCounts">SFMTA counts</a> from 2014 to 2023, which SFMTA mostly takes where someone asked, so they lean toward problem streets, and residents' <a href="https://telraam.net/">Telraam</a> window counters, the median Tuesday to Thursday rush hour over each counter's April to September days, or over all its days where it has fewer than five in those months. ${M.countRule} The 2023 Slow Streets evaluation counted whole days, so on those blocks the busiest hour is worked out as ${Math.round(M.k * 100)}% of the day. Modelled blocks are <a href="https://api.sfcta.org/api/">SFCTA's SF-CHAMP</a>, an undated run of 2019 or earlier, scaled to the counts. Estimated blocks are residential only: a count carried along its street, or a share of the parallel main street's traffic, which is a rough guess for the area.</p>
<h2 id="through-traffic">Through Traffic</h2>
<p>Each block's colour is the share of its car trips passing through: trips with neither end within half a mile of the block, or within the quarter, three quarters or one mile the slider picks. A distance replaced the block's Analysis Neighborhood, which counted almost every trip on Third Street as local because Bayview is so big. The trips are every car trip, for any purpose, in the <a href="https://mtc.ca.gov/">Metropolitan Transportation Commission</a>'s regional travel model for 2023 (<a href="https://github.com/BayAreaMetro/modeling-website/wiki/IndividualTrip">Travel Model 1.6</a>), counted as cars: two people sharing a ride are one car. We sent each down its fastest route on <a href="https://api.sfcta.org/api/">SFCTA's SF-CHAMP</a> road network, at the travel times for its hour, so the time of day filter changes this view. SFCTA doesn't publish SF-CHAMP's own trip table, so we use MTC's, whose zones in SF are about five times bigger; a trip end is shared over SF-CHAMP's zones inside each one by their homes and jobs. Trucks, visitors' and airport trips aren't in it, so a block's volume is residents' car trips, about half of all traffic on SF-CHAMP's network; read the share, not the volume. Night is the model's 10 pm to midnight and 5 to 6 am. A trip end is the middle of its SF-CHAMP zone, a few blocks across in SF, and MTC's own zones are bigger still, so read a block's colour, not its exact percentage. Every trip takes its fastest route, which favours the freeways, so on a street beside one the share is a floor.</p>
<p>The fastest route alone puts a whole corridor's traffic on whichever street wins by a few seconds, so we route every trip ${T.runs} times, each time with every street's travel time nudged by a random amount up to ${Math.round((T.jitter[1] - 1) * 100)}% either way, and average the runs. A block is dashed, a rough figure, where two halves of the runs, each averaged, put it in different colours, or where its routed trips come to more than SF-CHAMP's own all-day traffic on it. Blocks with fewer than ${T.minCars} car trips a day, or ${T.minBin} in one time of day, aren't coloured. Market Street east of Van Ness and JFK Drive in Golden Gate Park are closed to cars in the routing, as they are today; the model's network predates both closures. Main streets are drawn wide and residential streets thin. The model's network covers ${n0(TS.main.with_figure)} of ${n0(TS.main.blocks_total)} main-street blocks but only ${n0(TS.res.with_figure)} of ${n0(TS.res.blocks_total)} residential ones, the busier residential streets it codes as collectors, so a grey residential block isn't one we know is quiet. The network is an undated run from 2019 or earlier.</p>
<h2 id="where-traffic-comes-from">Where Traffic Comes From</h2>
<p>Pick a neighborhood or a Supervisor district and the map draws one circle for each of SF's 41 neighborhoods and each of ${whereFromRegions().length} regions around the bay. A circle's area is the cars a weekday that start or end there and drive on the chosen area's streets, and it prints its share of all the cars on those streets. These are the through-traffic view's routed car trips, keeping every one whose fastest route uses at least one of the area's streets (freeways and their ramps aren't its streets), the method planners call a select-link analysis. A trip end is in the area when the middle of its SF-CHAMP zone is. It's a model's estimate for 2023, not a count.</p>
<p>Coming from puts every car where it starts and Going to where it ends. Both puts it at both ends, so there a share is a share of trip ends. The ring on the chosen area is its own cars: the ones that start in it, end in it, or both.</p>
<p>The regions are groups of the <a href="https://github.com/BayAreaMetro/travel-model-one/blob/master/utilities/geographies/superdistrict-county.csv">Metropolitan Transportation Commission's superdistricts</a>: ${whereFromRegions().map((r) => `${r.name} (${r.places.join(", ")})`).join("; ")}. A region's circle sits at the middle of its people, or at the edge of the map toward it when that's off screen.</p>
<p>The time of day chart is cars an hour coming in from outside the area and going out of it, by each trip's departure hour in the model, in the map's five times of day. Night is 10 pm to midnight and 5 to 6 am, the only night hours the model's trips have.</p>
<p>Tap a circle and its card says how people travel between that place and the chosen area: every person trip with one end in each, by car, transit, bike and on foot, from <a href="https://github.com/BayAreaMetro/modeling-website/wiki/TravelModes">the same MTC model's trip files</a> for 2023. Car includes taxis and ride-hail. That's trips by their two ends, so a car passing through the area isn't in it. It's the model's estimate. For trips within SF the model has 30% on foot and 18% on transit. The Bay Area Travel Study 2023, which asked adults only, found 41% and 12% (<a href="https://www.sfcta.org/sites/default/files/2025-12/SFCTA_CMP_Report_2025_FINAL_2025-12-16.pdf">SFCTA, Congestion Management Program 2025</a>, Figures 4-40 to 4-42). The model simulates one trip in two, so under 60 trips a weekday the card doesn't split them, and under 60 car trips it gives no times.</p>
<p>The card's minutes and miles are for the trips people now drive: what the typical (median) one of a weekday's car trips takes door to door by each way at the morning rush, 6 to 10 am, from <a href="https://github.com/BayAreaMetro/modeling-website/wiki/SimpleSkims">MTC's zone-to-zone travel time tables</a> for the same model run. Transit adds the walk to the stop, the wait, the ride, any transfer and the walk from the stop, and from a region the card also gives the trip's time with a drive to the first stop. Bike is the shortest path on streets that allow bikes, ridden at 12 mph, with no hills or bike lanes in it. The model has no bike route longer than 75 miles, and <a href="https://511.org/biking/access/bridges">the Bay Bridge has no bike path all the way across</a>, so from most of the East Bay the card says no bike route. Where over half of the trips have no bike route, or no stop within a walk, the card gives that share and no time. Every trip is timed at the morning rush, whatever hour it leaves, which matters most for trips over the Bay Bridge.</p>
<p>A drawn area can't be worked out ahead of time, so for one the page counts the cars on every street crossing its edge, and on every freeway ramp inside it, inward by where they start and outward by where they end. That cordon count counts a car each time it crosses and can't tell a car passing through from one arriving, so a drawn area has no ring, no time of day chart and no travel figures on a card.</p>
<h2>Bike Comfort</h2>
<p>Every street block coloured by <a href="${BCI.source}">SFMTA's Bike Comfort Index</a> (the 2023 draft layer SFMTA built with Toole Design for every street, read ${BCI.fetched_on}), in five classes from 4 to 146, where higher is more comfortable. The colours split at a score over ${BCI.aaa.score}, the line <a href="${BCI.aaa.source}">SFMTA's Biking and Rolling Plan</a> uses for its all ages and abilities network (a painted lane or a calmed bike route counts only "BCI > ${BCI.aaa.score}"); blocks at ${BCI.aaa.score} or under are amber to brown, blocks over it teal. The classes are the ones SFMTA's layer draws, except that a score of 81 moves up a class so none straddles the line. ${n0(M.bci.matched)} street blocks have a score; ${n0(M.bci.unscored)} active blocks have none and aren't drawn. A block takes the layer's combined score, the lower of its two directions. It's a bike measure; we don't have one for walking. The index hasn't been checked against how stressed riders actually feel, and its surveys asked adults only, so read it as SFMTA's own rating rather than a measure of who feels safe riding.</p>
<h2>Crime</h2>
<p>Every SFPD incident report of any kind from ${CR.from.slice(0, 4)}, the dataset's first year, to ${CR.to} (<a href="https://data.sfgov.org/d/wg3w-h783">DataSF wg3w-h783</a>), one count per incident, supplements left out, drawn as a heat map; the map opens on every year. Each year's count matches DataSF's own count of distinct incidents with a location. Kind of crime sorts SFPD's categories into five groups: violence and weapons (assault, robbery, homicide, sex offenses, weapons), theft, burglary and fraud (including car theft), vandalism and arson, drugs, and other (warrants, lost property, non-criminal and the rest); a report with categories in several groups goes in the first of them in that order. Reports are filed days to weeks after the incident, so the newest weeks undercount. The heat map leaves out Other unless you pick it. SFPD records a report at the nearest intersection, so tap a spot zoomed in for the count there. Muni stops are every stop in SFMTA's published transit schedule data (GTFS), and the numbered lines, in SFMTA's own colour for each line, are ${M.muni.drawn} of Muni's ${M.muni.frequent} frequent lines (the ${M.muni.dropped.join(" and ")} have no route shape in the data), drawn as on the <a href="/transportation/muni/lines">Muni dashboard</a>. The day and time choice counts each report by the weekday of its incident date and the hour of its incident time.</p>
<h2>Area, Time and Day</h2>
<p>The area filter is one of SF's 41 Analysis Neighborhoods, one of the 11 <a href="https://data.sfgov.org/d/cqbw-m5m3">Supervisor districts</a> as drawn in 2022, or a shape you draw, and it scopes every view, the headline and the chart. A person counts in the district whose outline holds their point, or, for the few just outside every outline, the nearest one, so the 11 add up to the city. A person counts in the neighborhood their crash report's point falls in, a street block in the one its midpoint falls in, and a crime report in the one its intersection falls in, all against the city's full neighborhood outlines, so each sits in exactly one; ${n0(M.figures.people)} people across the 41 add up to ${n0(M.figures.people)}. A drawn shape counts the same points. The day filter is weekdays, weekends or any days you pick, and the time filter any of five times of day: the morning rush, 6 to 9 am; midday, 9 am to 3 pm; the evening rush, 3 to 7 pm; evening, 7 to 10 pm; and night. It reads each crash report's own hour and date, and each crime report's. Night runs from 10 pm to 6 am and the day is the calendar date, so a Saturday 1 am crash counts as a weekend crash and a Friday 11 pm one as a weekday crash. Traffic stress figures are for the busiest weekday hour, so the choice doesn't change that view. The through-traffic model is one weekday: one time of day picked applies, several show the whole day, and a weekend or single day shows weekday traffic. Every chart counts what the map shows under the filters, so its bars add up to the headline; a click on a bar filters the map to it, and a second click clears it. Where people hurt in an area were travelling to and from isn't in the crash reports, so the map can't show it yet.</p>
<h2>Updates</h2>
<p>The data was last read on ${M.read}. The map is a draft and we rebuild it by hand for now; it isn't on the site's daily refresh yet.</p>`;
  return page({ title: "About the Street Safety Map", description: "How the Street Safety Map counts and places each person hurt, and where its traffic, bike comfort and crime views come from.", path: ABOUT, body, dataUpdated, directory: false });
}
