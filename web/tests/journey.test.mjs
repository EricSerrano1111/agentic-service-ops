// Run with `node --test`: the answer journey's wording and geometry (data dictionary section 6,
// rule 10). Every input is a journey object; nothing here reads the question or the answer.
import assert from "node:assert/strict";
import test from "node:test";

import {
  barLayout,
  boxOrder,
  browserTimeLabel,
  chips,
  diagramDescription,
  formatSeconds,
  hasJourney,
  hopNumber,
  replayInterval,
  routedLine,
  rowLabel,
  serverTimeLabel,
} from "../app/lib/journey.mjs";

const hop = (service, step, start_ms, duration_ms, status = "ok", attempt = 1) => ({
  service, step, attempt, start_ms, duration_ms, status,
});

const HOPS = [
  hop("gateway", "forward", 0, 5500),
  hop("orchestrator", "route", 0, 1300),
  hop("reporting", "parse", 1300, 1600),
  hop("reporting", "tool", 2900, 400),
  hop("qa", "figures_check", 3300, 600),
  hop("qa", "interpretation_check", 3900, 1500),
];
const JOURNEY = {
  hops: HOPS,
  qa: {
    verdict: "pass",
    checks: [{ code: "figures_match_database", class: "figures", passed: true }],
    interpretation: "faithful",
    mode: "advisory",
  },
  model_calls: 3,
  cost_usd: 0.0018,
};

test("the button is shown only when a journey with hops is present", () => {
  assert.equal(hasJourney({ journey: JOURNEY }), true);
  assert.equal(hasJourney({ journey: null }), false);
  assert.equal(hasJourney({}), false);
  assert.equal(hasJourney(null), false);
  assert.equal(hasJourney({ journey: { hops: [] } }), false);
  assert.equal(hasJourney({ journey: { hops: "x" } }), false);
});

test("bar positions come only from start_ms and duration_ms", () => {
  const bars = barLayout(HOPS);
  assert.deepEqual(bars[0], { x: 0, w: 1000 }); // the forward hop spans the whole request
  assert.deepEqual(bars[1], { x: 0, w: 236 }); // 1300 of 5500
  assert.equal(bars[4].x, Math.round((3300 / 5500) * 1000));
  // the same hops with different text give the same layout: it reads no other field
  assert.deepEqual(barLayout(HOPS.map((h) => ({ ...h, note: "ignored" }))), bars);
});

test("a very short hop keeps a visible bar and no bar passes the end", () => {
  const bars = barLayout([hop("gateway", "forward", 0, 1000), hop("qa", "figures_check", 999, 0.2)]);
  assert.ok(bars[1].w >= 1 && bars[1].x + bars[1].w <= 1000);
  assert.deepEqual(barLayout([]), []);
  assert.deepEqual(barLayout([hop("orchestrator", "route", 0, 0)])[0].x, 0);
});

test("server time and the browser time are printed apart", () => {
  assert.equal(serverTimeLabel(HOPS), "Server time 5.5 s");
  assert.equal(browserTimeLabel(5912), "in your browser 5.9 s");
  assert.equal(browserTimeLabel(-3), "in your browser 0.0 s");
});

test("durations: hundredths under a second, tenths above", () => {
  assert.equal(formatSeconds(50), "0.05 s");
  assert.equal(formatSeconds(1300), "1.3 s");
  assert.equal(formatSeconds(-1), "0.00 s");
});

test("a row names the service, the step, the attempt and a failure", () => {
  assert.equal(rowLabel(HOPS[2], 3), "3 · Reporting agent reads the question · 1.6 s");
  assert.equal(
    rowLabel(hop("qa", "figures_check", 1, 20, "timeout", 2), 5),
    "5 · QA agent checks the figures (attempt 2) · timed out · 0.02 s",
  );
  assert.match(rowLabel(hop("reporting", "parse", 0, 0, "skipped"), 2), /skipped/);
});

test("the chips read as the rule words", () => {
  assert.deepEqual(chips(JOURNEY).map((c) => c.text), [
    "Model calls: 3",
    "Estimated cost: $0.0018 (list price)",
    "QA figures check: pass",
    "Interpretation check: advisory · faithful",
  ]);
});

test("chip states for a failed, unrun and unavailable QA", () => {
  const failed = { ...JOURNEY, qa: { ...JOURNEY.qa, verdict: "fail", interpretation: "not_run",
    checks: [{ code: "x", class: "figures", passed: false }] } };
  assert.equal(chips(failed)[2].text, "QA figures check: fail");
  assert.equal(chips(failed)[3].text, "Interpretation check: advisory · not run");
  const none = { ...JOURNEY, qa: null };
  assert.equal(chips(none)[2].text, "QA figures check: not run");
  assert.equal(chips(none)[3].text, "Interpretation check: not run");
  const notFaithful = { ...JOURNEY, qa: { ...JOURNEY.qa, interpretation: "not_faithful" } };
  assert.equal(chips(notFaithful)[3].text, "Interpretation check: advisory · not faithful");
  assert.equal(chips({ ...JOURNEY, cost_usd: 0 })[1].text, "Estimated cost: $0.0000 (list price)");
});

test("the routed line is built only from the journey", () => {
  assert.equal(routedLine(JOURNEY), "Routed to the reporting agent · QA checked the figures");
  const routeOnly = { ...JOURNEY, hops: [hop("orchestrator", "route", 0, 900)], qa: null };
  assert.equal(
    routedLine(routeOnly),
    "Handled by the router; no specialist agent was called · QA did not check figures",
  );
  const sentiment = { ...JOURNEY, hops: [hop("orchestrator", "route", 0, 9), hop("sentiment", "parse", 9, 5)] };
  assert.match(routedLine(sentiment), /^Routed to the sentiment agent/);
  const skipped = { ...JOURNEY, hops: [hop("orchestrator", "route", 0, 9), hop("reporting", "parse", 9, 0, "skipped")] };
  assert.match(routedLine(skipped), /^Handled by the router/);
});

test("services used are numbered in hop order; the rest are absent (not called)", () => {
  const order = boxOrder(HOPS);
  assert.deepEqual(order, {
    gateway: 1, orchestrator: 2, reporting: 3, mcp_reporting: 4, db: 4, qa: 5, qa_sql: 5,
  });
  // a row carries its box's number: the tool hop is the tool server's, QA's two checks are QA's
  assert.deepEqual(HOPS.map((h) => hopNumber(order, h)), [1, 2, 3, 4, 5, 5]);
  assert.equal("sentiment" in order, false);
  assert.equal("forecast" in order, false);
  const text = diagramDescription(order);
  assert.match(text, /Called, in order: Gateway, Orchestrator, Reporting agent, QA agent\./);
  assert.match(text, /Not called: Sentiment agent, Forecast agent\./);
});

test("a skipped specialist hop counts as not called", () => {
  const order = boxOrder([hop("orchestrator", "route", 0, 5), hop("reporting", "parse", 5, 0, "skipped")]);
  assert.equal("reporting" in order, false);
});

test("the replay lights every step in about 1.5 s", () => {
  assert.equal(replayInterval(7) * 7 <= 1600 && replayInterval(7) * 7 >= 1400, true);
  assert.equal(replayInterval(0) > 0, true);
});
