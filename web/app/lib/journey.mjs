// The answer journey's wording and geometry (data dictionary section 6, rule 10). Everything here
// is read from the journey object the gateway returns; nothing is computed except bar positions
// from `start_ms` and `duration_ms`, and the totals the page prints are the journey's own fields.

export const SERVICE_LABEL = {
  gateway: "Gateway",
  orchestrator: "Orchestrator",
  reporting: "Reporting agent",
  sentiment: "Sentiment agent",
  forecast: "Forecast agent",
  qa: "QA agent",
};

const STEP_LABEL = {
  route: "routes the question",
  parse: "reads the question",
  tool: "runs the query",
  figures_check: "checks the figures",
  interpretation_check: "interpretation check",
  forward: "forwards the question",
};

const STATUS_WORDS = {
  ok: "",
  failed: "failed",
  timeout: "timed out",
  skipped: "skipped",
  not_called: "not called",
};

const SPECIALISTS = ["reporting", "sentiment", "forecast"];
// The tool server a specialist's `tool` hop ran on.
const MCP_KEY = { reporting: "mcp_reporting", sentiment: "mcp_sentiment", forecast: "mcp_forecast" };

/** Does this gateway response carry a journey worth showing? */
export function hasJourney(result) {
  const j = result && result.journey;
  return Boolean(j && Array.isArray(j.hops) && j.hops.length > 0);
}

/** "0.05 s" under a second, "1.3 s" above. */
export function formatSeconds(ms) {
  const m = Math.max(0, Number(ms) || 0);
  return m < 1000 ? `${(m / 1000).toFixed(2)} s` : `${(m / 1000).toFixed(1)} s`;
}

/** The end of the last hop, in ms: the server time shown above the timeline. */
export function serverMs(hops) {
  return hops.reduce((end, h) => Math.max(end, h.start_ms + h.duration_ms), 0);
}

/** "Server time N.N s". */
export function serverTimeLabel(hops) {
  return `Server time ${(serverMs(hops) / 1000).toFixed(1)} s`;
}

/** "in your browser N.N s": the rule 7 timer, shown apart from the server time. */
export function browserTimeLabel(ms) {
  return `in your browser ${(Math.max(0, Number(ms) || 0) / 1000).toFixed(1)} s`;
}

/** Bar positions on a 0 to 1000 scale, from start and duration only. A bar is at least 6 wide
 *  so a very short hop stays visible, and never runs past the end. */
export function barLayout(hops) {
  const total = Math.max(serverMs(hops), 1);
  return hops.map((h) => {
    const x = Math.min(Math.round((h.start_ms / total) * 1000), 994);
    const w = Math.max(Math.round((h.duration_ms / total) * 1000), 6);
    return { x, w: Math.min(w, 1000 - x) };
  });
}

/** One timeline row's text: "3 · Reporting agent reads the question · 1.60 s". */
export function rowLabel(hop, number) {
  const words = [SERVICE_LABEL[hop.service], STEP_LABEL[hop.step]];
  if (hop.attempt > 1) words.push(`(attempt ${hop.attempt})`);
  const status = STATUS_WORDS[hop.status];
  const tail = status ? `${status} · ${formatSeconds(hop.duration_ms)}` : formatSeconds(hop.duration_ms);
  return `${number} · ${words.join(" ")} · ${tail}`;
}

/** Boxes that are lit with their owner and carry no number of their own. */
export const UNNUMBERED = ["db", "qa_sql"];

/**
 * Which diagram boxes were used, and in what order: { key: 1-based number }. Keys are the
 * service names, `mcp_<specialist>` for a specialist's tool server, `qa_sql` for QA's own
 * connection and `db` for Cloud SQL. The last two share their owner's number (they light with
 * it and are not numbered in the picture). A box absent from the result was not called.
 */
export function boxOrder(hops) {
  const order = {};
  let count = 0;
  const add = (key) => {
    if (key in order) return order[key];
    count += 1;
    order[key] = count;
    return count;
  };
  const sorted = [...hops].sort((a, b) => a.start_ms - b.start_ms);
  for (const h of sorted) {
    if ((h.status === "skipped" || h.status === "not_called") && h.service !== "orchestrator") {
      continue;
    }
    add(h.service);
    if (h.step === "tool" && MCP_KEY[h.service]) {
      const n = add(MCP_KEY[h.service]);
      if (!("db" in order)) order.db = n;
    }
    if (h.step === "figures_check" && h.service === "qa") {
      order.qa_sql = order.qa;
      if (!("db" in order)) order.db = order.qa;
    }
  }
  return order;
}

/** The number a hop's row carries: its box's number (a tool hop belongs to the tool server). */
export function hopNumber(order, hop) {
  const key = hop.step === "tool" && MCP_KEY[hop.service] ? MCP_KEY[hop.service] : hop.service;
  return order[key] ?? "";
}

/** The first specialist that ran, or null (a routing-only outcome). */
export function specialistOf(hops) {
  const hop = hops.find((h) => SPECIALISTS.includes(h.service) && h.status !== "skipped");
  return hop ? hop.service : null;
}

function figuresResult(qa) {
  const checks = qa ? qa.checks.filter((c) => c.class === "figures") : [];
  if (checks.length === 0) return "not run";
  return checks.every((c) => c.passed) ? "pass" : "fail";
}

const INTERPRETATION_WORDS = {
  faithful: "faithful",
  not_faithful: "not faithful",
  not_run: "not run",
  unavailable: "unavailable",
};

/** The chips under the timeline: [{ text, tone }], tone one of "plain", "ok", "bad". */
export function chips(journey) {
  const figures = figuresResult(journey.qa);
  const out = [
    { text: `Model calls: ${journey.model_calls}`, tone: "plain" },
    { text: `Estimated cost: $${journey.cost_usd.toFixed(4)} (list price)`, tone: "plain" },
    {
      text: `QA figures check: ${figures}`,
      tone: figures === "pass" ? "ok" : figures === "fail" ? "bad" : "plain",
    },
  ];
  const interp = journey.qa ? journey.qa.interpretation : "not_run";
  const mode = journey.qa ? journey.qa.mode : null;
  out.push({
    text: `Interpretation check: ${mode ? `${mode} · ` : ""}${INTERPRETATION_WORDS[interp] || "not run"}`,
    tone: "plain",
  });
  return out;
}

/** "Routed to the reporting agent · QA checked the figures", from journey fields only. */
export function routedLine(journey) {
  const specialist = specialistOf(journey.hops);
  const first = specialist
    ? `Routed to the ${SERVICE_LABEL[specialist].toLowerCase()}`
    : "Handled by the router; no specialist agent was called";
  const figures = figuresResult(journey.qa);
  const qa = {
    pass: "QA checked the figures",
    fail: "QA's figures check failed",
    "not run": "QA did not check figures",
  }[figures];
  return `${first} · ${qa}`;
}

/** The text alternative of the journey diagram: what was called, in order, and what was not. */
export function diagramDescription(order) {
  const names = [
    ["gateway", "Gateway"],
    ["orchestrator", "Orchestrator"],
    ["reporting", "Reporting agent"],
    ["sentiment", "Sentiment agent"],
    ["forecast", "Forecast agent"],
    ["qa", "QA agent"],
  ];
  const called = names
    .filter(([k]) => k in order)
    .sort((a, b) => order[a[0]] - order[b[0]])
    .map(([, n]) => n);
  const not = names.filter(([k]) => !(k in order)).map(([, n]) => n);
  const parts = [`Answer journey diagram. Called, in order: ${called.join(", ") || "none"}.`];
  if (not.length) parts.push(`Not called: ${not.join(", ")}.`);
  return parts.join(" ");
}

/** Does the person prefer no motion? Safe where `window` is absent. */
export function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** The replay's pace: all steps lit in about 1.5 s in total. */
export const REPLAY_TOTAL_MS = 1500;
export function replayInterval(steps) {
  return Math.max(Math.round(REPLAY_TOTAL_MS / Math.max(steps, 1)), 50);
}
