#!/usr/bin/env node
// Tests the Sentry snippet (site/src/layout.mjs, errorTracking()): nothing without a DSN, and with one, the
// pinned errors-only bundle and an init that sends no default PII and loads no replay.
//
//   node site/tests/error-tracking-test.mjs
import assert from "node:assert/strict";
import path from "node:path";

import { ROOT } from "../scripts/lib/repo.mjs";
const { errorTracking, SENTRY_BUNDLE } = await import(path.join(ROOT, "site", "src", "layout.mjs"));

assert.equal(errorTracking(""), "", "no DSN, no script");
assert.equal(errorTracking(undefined), "", "no DSN, no script");

const dsn = "https://abc123@o1.ingest.us.sentry.io/42";
const html = errorTracking(dsn);
assert.ok(html.includes(`src="${SENTRY_BUNDLE.src}"`), "loads the pinned bundle");
assert.ok(html.includes(`integrity="${SENTRY_BUNDLE.integrity}"`), "checks its hash");
assert.match(SENTRY_BUNDLE.src, /\/bundle\.min\.js$/, "the errors-only bundle: no replay, no tracing");
assert.ok(html.includes(JSON.stringify(dsn)), "inits with the DSN");
assert.ok(html.includes("sendDefaultPii: false"), "sends no default PII");
assert.doesNotMatch(html, /replay/i, "no session replay");
console.log("error-tracking: ok");
