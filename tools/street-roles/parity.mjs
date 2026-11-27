// Checks the Street Roles Map's browser model (site/src/street-roles.mjs, model()) against the Python build
// (tools/street-roles/street-roles.py route): on the default roles, both must count the same commuters connected
// today and with the network, and rate every block's stress with the network the same. Exits 1 on any difference.
//
//     node tools/street-roles/parity.mjs
import fs from "node:fs";
import path from "node:path";
import { model, SUMMARY, STREETS_FILE, COMMUTES_FILE } from "../../site/src/street-roles.mjs";

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const S = JSON.parse(fs.readFileSync(path.join(ROOT, STREETS_FILE), "utf8"));
const C = JSON.parse(fs.readFileSync(path.join(ROOT, COMMUTES_FILE), "utf8"));
const M = model();
const B = S.blocks, roles = S.roles;
const today = (i) => (roles[B.role[i]] === "walk" ? null : B.today[i]);
const net = (i) => M.stress(roles[B.role[i]], B, i);

const fails = [];
const t0 = Date.now();
const [c0, tot0] = M.connected(S, C, today);
const t1 = Date.now();
const [c1, tot1] = M.connected(S, C, net);
const t2 = Date.now();
if (tot0 !== SUMMARY.commuters_in_window || tot1 !== SUMMARY.commuters_in_window) fails.push(`commuters counted: browser ${tot0}/${tot1}, build ${SUMMARY.commuters_in_window}`);
if (c0 !== SUMMARY.connected_today) fails.push(`connected today: browser ${c0}, build ${SUMMARY.connected_today}`);
if (c1 !== SUMMARY.connected_network) fails.push(`connected with the network: browser ${c1}, build ${SUMMARY.connected_network}`);
const miles = {};
for (let i = 0; i < B.cnn.length; i++) { const s = net(i); if (s !== null) miles[s] = (miles[s] || 0) + B.ft[i] / 5280; }
for (const [k, v] of Object.entries(SUMMARY.miles_by_stress.network)) {
  if (Math.abs((miles[k] || 0) - v) > 0.1) fails.push(`stress ${k} with the network: browser ${(miles[k] || 0).toFixed(1)} mi, build ${v}`);
}
if (fails.length) { console.error("street-roles parity failed:\n  " + fails.join("\n  ")); process.exit(1); }
console.log(`street-roles parity: today ${c0}, with the network ${c1} of ${tot0}, as the build counts. Browser time ${t1 - t0} ms and ${t2 - t1} ms.`);
