// The Street Safety map's corner chart: Workspaces' shared PlotChart (plot-chart.ts and plot-spec.mjs, copied side by
// side from claude-live-feedback-plugin packages/core/src at 9fd846d53, 2026-11-19), mounted with mountFromSnapshot
// (component-snapshot.ts) as an Astro page would. src/safety-map/index.mjs bundles this file for the browser, mapping
// plot-chart.ts's esm.sh address for Plot to the site's own @observablehq/plot 0.6.17.
import mount from "./plot-chart.ts";
import { mountFromSnapshot } from "./component-snapshot.ts";

window.SafetyChart = {
  /** Draw `props` (a PlotChart spec plus title, subtitle and note) into `el`, replacing what it held. */
  draw(el, props) {
    if (el.__unmount) el.__unmount();
    el.__unmount = mountFromSnapshot(el, mount, props, { data: props.data }, { id: props.id || "safety-chart" });
  },
};
window.dispatchEvent(new Event("safetychart:ready"));
