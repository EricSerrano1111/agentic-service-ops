"use client";

import { useEffect, useMemo, useState } from "react";
import ArchitectureDiagram from "./ArchitectureDiagram";
import {
  barLayout,
  boxOrder,
  browserTimeLabel,
  chips,
  hopNumber,
  prefersReducedMotion,
  replayInterval,
  rowLabel,
  serverTimeLabel,
} from "../lib/journey.mjs";

// The answer journey (data dictionary section 6, rule 10): how the request was handled. It is
// telemetry about a request that already happened; it changes nothing about the answer above it.
// Not a live region: only the answer is announced to assistive technology.

export default function JourneyPanel({ journey, browserMs, question }) {
  const order = useMemo(() => boxOrder(journey.hops), [journey]);
  const total = Math.max(0, ...Object.values(order));
  const [reduced, setReduced] = useState(false);
  const [lit, setLit] = useState(Infinity);
  const [replays, setReplays] = useState(0);

  useEffect(() => setReduced(prefersReducedMotion()), []);

  // The replay: light the called boxes in order, once, in about 1.5 s (unless motion is reduced).
  useEffect(() => {
    if (reduced || replays === 0) return undefined;
    let n = 0;
    setLit(0);
    const timer = setInterval(() => {
      n += 1;
      setLit(n);
      if (n >= total) clearInterval(timer);
    }, replayInterval(total));
    return () => clearInterval(timer);
  }, [replays, reduced, total]);

  // Opening the panel plays the replay once.
  useEffect(() => setReplays(1), []);

  const bars = barLayout(journey.hops);
  return (
    <section id="journey-panel" className="card journey" aria-labelledby="journey-heading">
      <div className="card-head">
        <h2 id="journey-heading">Answer journey</h2>
        {!reduced && (
          <button type="button" className="link" onClick={() => setReplays((n) => n + 1)}>
            Replay
          </button>
        )}
      </div>
      <div className="journey-body">
        <p className="muted">
          One question, traced through every hop. Question: <b>{question}</b>
        </p>
        <figure className="figure">
          <ArchitectureDiagram order={order} lit={lit} />
        </figure>

        <div className="timeline-head">
          <h3>Timeline</h3>
          <span className="muted small timeline-total">
            {serverTimeLabel(journey.hops)}
            {browserMs != null && ` · ${browserTimeLabel(browserMs)}`}
          </span>
        </div>
        <ol className="timeline" aria-label="Hops in order">
          {journey.hops.map((hop, i) => (
            <li
              key={`${hop.service}-${hop.step}-${hop.attempt}-${hop.start_ms}-${i}`}
              className="timeline-row"
            >
              <span className="timeline-label">{rowLabel(hop, hopNumber(order, hop))}</span>
              <svg
                className="timeline-bar"
                viewBox="0 0 1000 20"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <rect className="bar-track" x="0" y="0" width="1000" height="20" rx="4" />
                <rect
                  className={`bar bar-${hop.service === "qa" ? "qa" : "main"} bar-${hop.status}`}
                  x={bars[i].x}
                  y="0"
                  width={bars[i].w}
                  height="20"
                  rx="4"
                />
              </svg>
            </li>
          ))}
        </ol>
        <p className="muted small">
          Server time is measured by the services. &ldquo;In your browser&rdquo; also includes the
          network and any cold start.
        </p>

        <ul className="chips" aria-label="Summary">
          {chips(journey).map((chip) => (
            <li key={chip.text} className={`chip chip-${chip.tone}`}>
              {chip.text}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
