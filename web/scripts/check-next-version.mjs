// Fails the build if the installed `next` is below the patched minimum (ADR-080: "the patch
// pin stays anyway"). Raise MIN_NEXT when a newer patched release is published; the minimum,
// its source and the date it was read are recorded in docs/sprint-log.md.
import { readFileSync } from "node:fs";

const MIN_NEXT = "16.4.1"; // GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr, GHSA-p3m5-59mp-jv5r patched release, read 2026-10-14

const parse = (v) => v.split("-")[0].split(".").map((n) => Number.parseInt(n, 10));
const isBelow = (have, need) => {
  for (let i = 0; i < 3; i += 1) {
    if (have[i] !== need[i]) return have[i] < need[i];
  }
  return false;
};

const installed = JSON.parse(readFileSync("node_modules/next/package.json", "utf8")).version;
const have = parse(installed);

if (have.length !== 3 || have.some(Number.isNaN) || isBelow(have, parse(MIN_NEXT))) {
  console.error(`next ${installed} is below the required minimum ${MIN_NEXT}`);
  process.exit(1);
}
console.log(`next ${installed} >= ${MIN_NEXT}`);
