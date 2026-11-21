// About the data for the Grand Juries page: how the counts were made, how a
// report gets answered, and what we have not verified. The words are the
// research's own (data/cgj.json, tools/grand-juries/build-cgj-site.py).

import { page } from "../layout.mjs";
import { data, md, counted, newestTerm, FN_CSS, FN_SCRIPT, SOURCES } from "../grand-juries.mjs";

export const path = "/grand-juries/about";
export const file = "grand-juries/about/index.html";

const list = (sec) => `<ul>${sec.items.map((x) => `<li>${md(x, sec.notes)}</li>`).join("")}</ul>`;

export function render() {
  const L = data.lede;
  const body = `<style>${FN_CSS}</style>
<div class="gj-about">
<h1>About the Grand Juries Data</h1>
<p class="lede">How the counts on the <a href="/grand-juries">Grand Juries</a> page were made, and what they can't tell you.</p>
<h2>How we counted</h2>
<p>The headline counts the ${counted.n} recommendations from reports before ${newestTerm}. The ${counted.newestN} from ${newestTerm} reports are too new for a follow-up. R1.1 and the like are the jury's recommendation numbers.</p>
<p>${md(`A recommendation has evidence it was done when a published dashboard, a passed law or measure, an existing document or a later audit shows the action happened. Evidence means the step was taken, not that the problem went away. What the city says it did is in each report's Response, and later progress comes mainly from the Controller's December 2025 status reports.{{fn:1}}`, [L.notes[1]])}</p>
<h2>How reports get answered</h2>
${list(data.method["How reports get answered"])}
<h2>What we have not verified</h2>
${list({ ...data.method["What we have not verified"], items: data.method["What we have not verified"].items.map((x) => x.replace("The counts above follow the city's own labels.", "Each report's Response follows the city's own labels.")) })}
</div>
${FN_SCRIPT}`;
  return page({
    title: "About the Grand Juries Data",
    description: "How the Civil Grand Jury counts on SF Works were made, how the city answers a report, and what is not yet verified.",
    path,
    body,
    sources: SOURCES,
  });
}
