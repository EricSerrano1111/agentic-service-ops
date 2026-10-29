// Run with `node --test`: the shape of web/data/results.json, which the /results/ page reads.
// The values are checked against their sources and the report by tests/unit/test_results_data.py.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const data = JSON.parse(readFileSync(new URL("../data/results.json", import.meta.url), "utf8"));

test("every figure carries its source, hash, locator and report section", () => {
  const entries = Object.entries(data.figures);
  assert.ok(entries.length > 0);
  for (const [id, f] of entries) {
    assert.ok(f.text, id);
    assert.match(f.source, /^[\w./-]+$/, id);
    assert.match(f.sha256, /^[0-9a-f]{64}$/, id);
    assert.ok(["file", "line"].includes(f.hashed), id);
    assert.ok(f.locator?.kind, id);
    assert.match(f.report_section, /^\d+(\.\d+)?$/, id);
  }
});

test("a figure drawn as a bar has a number, and a fraction has its denominator", () => {
  for (const id of [
    "sentiment_bert", "sentiment_tfidf", "forecast_holdout_volume_v2",
    "forecast_holdout_seasonal_naive", "fr03_route_v6", "fr03_route_v3",
  ]) {
    assert.equal(typeof data.figures[id].number, "number", id);
  }
  for (const id of ["fr03_route_v6", "fr03_route_v3"]) {
    assert.equal(typeof data.figures[id].of, "number", id);
  }
});
