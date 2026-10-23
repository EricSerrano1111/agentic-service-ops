// Run with `node --test` (no package needed): the browser-side helpers that carry the rules of
// data dictionary section 6, rules 7 and 9.
import assert from "node:assert/strict";
import test from "node:test";

import { EXAMPLES } from "../app/lib/examples.mjs";
import { finishedLabel, workingLabel } from "../app/lib/timer.mjs";

test("the wait shows whole seconds, rounded down", () => {
  assert.equal(workingLabel(0), "Working… 0 s");
  assert.equal(workingLabel(999), "Working… 0 s");
  assert.equal(workingLabel(1000), "Working… 1 s");
  assert.equal(workingLabel(59999), "Working… 59 s");
});

test("a finished wait shows one decimal, and says how it ended", () => {
  assert.equal(finishedLabel(5912, true), "Answered in 5.9 s");
  assert.equal(finishedLabel(120000, true), "Answered in 120.0 s");
  assert.equal(finishedLabel(3100, false), "Ended after 3.1 s");
});

test("a negative reading never shows a negative time", () => {
  assert.equal(workingLabel(-5), "Working… 0 s");
  assert.equal(finishedLabel(-5, false), "Ended after 0.0 s");
});

test("the example questions are exactly rule 9's, grouped as the mockup groups them", () => {
  const flat = EXAMPLES.map((g) => [g.area, g.items.map((i) => [i.q, i.note ?? null])]);
  assert.deepEqual(flat, [
    [
      "Incident reporting",
      [
        ["What was SLA compliance in the Northeast last month?", null],
        ["Which incident types were most common in July 2026?", null],
      ],
    ],
    [
      "Customer sentiment",
      [
        ["Is negative feedback trending up in the West?", null],
        ["Show examples of negative comments from last month", null],
      ],
    ],
    ["Volume forecast", [["What weekly request volume should we expect for the next 8 weeks?", null]]],
    [
      "See how it handles edge cases",
      [
        ["How's the Southeast doing?", "too open: it asks you to choose"],
        ["What will revenue be next quarter?", "out of scope: it declines"],
      ],
    ],
  ]);
});

test("every example fits the question box", () => {
  for (const g of EXAMPLES) for (const i of g.items) assert.ok(i.q.length <= 500);
});
