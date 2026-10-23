"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "./components/Icons";
import { EXAMPLES } from "./lib/examples.mjs";
import { finishedLabel, workingLabel } from "./lib/timer.mjs";

const MAX_QUESTION = 500;
const REFUSAL_CODES = ["session_limit", "daily_limit"];
const QA_ICONS = { verified: "check", failed: "cross", unavailable: "warn", not_checked: "clock" };

// One screen (ADR-080). Everything shown comes from the gateway's view of the answer; the
// display rules are data dictionary section 6, "Answer display (UI)". Text only: nothing from
// a response is ever rendered as HTML, and nothing here computes a figure.

async function postJson(path, body) {
  return fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function Callout({ kind, icon, children }) {
  return (
    <div className={`callout callout-${kind}`}>
      <Icon name={icon} />
      <span>{children}</span>
    </div>
  );
}

function Answer({ result }) {
  if (result.outcome === "needs_clarification") {
    return (
      <>
        <div className="clarify-title">
          <Icon name="help" />
          <span>Clarification needed</span>
        </div>
        <p className="answer-text">{result.answer}</p>
      </>
    );
  }
  const plain = ["answered", "degraded"].includes(result.outcome);
  return (
    <>
      {result.headline && (
        <div className="headline" data-testid="headline">
          <span className="headline-figure">{result.headline.figure}</span>
          <span className="headline-caption">{result.headline.caption}</span>
        </div>
      )}
      {plain ? (
        <p className="answer-text">{result.answer}</p>
      ) : (
        <Callout kind="note" icon="info">{result.answer}</Callout>
      )}

      {result.interpreted_as && (
        <div className="interpreted">
          <span className="label">Interpreted as:</span>
          <span>{result.interpreted_as}</span>
        </div>
      )}

      {result.qa_text && (
        <div className={`callout callout-qa-${result.qa_status}`}>
          <Icon name={QA_ICONS[result.qa_status] || "info"} />
          <span>{result.qa_text}</span>
        </div>
      )}

      {result.escalate && (
        <Callout kind="warn" icon="warn">Sent for follow-up. {result.warning}</Callout>
      )}
    </>
  );
}

export default function Page() {
  const [phase, setPhase] = useState("loading"); // loading | signed-out | ready
  const [question, setQuestion] = useState("");
  // null before the first question; then { status: "working" | "done" | "failed", asked, ... }
  const [run, setRun] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(false);
  const inputRef = useRef(null);
  const sentAt = useRef(0);

  const busy = run?.status === "working";

  useEffect(() => {
    // Read an invite from the fragment, exchange it, then ask the gateway whether we are
    // signed in. Runs on load and when the fragment changes (a link opened in an open tab).
    async function enter() {
      const match = /(?:^|&)invite=([^&]+)/.exec(window.location.hash.replace(/^#/, ""));
      if (match) {
        // The token travels in the fragment, which is never sent to a server. Clear it from
        // the address bar and history as soon as it is read.
        const token = decodeURIComponent(match[1]);
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
        try {
          await postJson("/auth/exchange", { token });
        } catch {
          // the session check below decides what the page shows
        }
      }
      try {
        const res = await fetch("/api/session", { credentials: "same-origin" });
        setPhase(res.ok ? "ready" : "signed-out");
      } catch {
        setPhase("signed-out");
      }
    }

    if (!started.current) {
      started.current = true;
      enter();
    }
    window.addEventListener("hashchange", enter);
    return () => window.removeEventListener("hashchange", enter);
  }, []);

  // The timer (rule 7) counts the browser's own wait; it reads no response field.
  useEffect(() => {
    if (!busy) return undefined;
    const tick = setInterval(() => setElapsed(performance.now() - sentAt.current), 250);
    return () => clearInterval(tick);
  }, [busy]);

  async function submit(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    sentAt.current = performance.now();
    setElapsed(0);
    setRun({ status: "working", asked: text });
    let next;
    try {
      const res = await postJson("/api/ask", { question: text });
      const body = await res.json().catch(() => ({}));
      const ms = performance.now() - sentAt.current;
      if (res.status === 401) {
        setPhase("signed-out");
        setRun(null);
        return;
      }
      if (res.ok) {
        next = { status: "done", asked: text, result: body, ms };
      } else {
        next = {
          status: "failed",
          asked: text,
          ms,
          refusal: REFUSAL_CODES.includes(body.error),
          message: body.detail || "The request could not be completed. Please try again.",
        };
      }
    } catch {
      next = {
        status: "failed",
        asked: text,
        ms: performance.now() - sentAt.current,
        refusal: false,
        message: "The service could not be reached. Please try again.",
      };
    }
    setRun(next);
  }

  function fillExample(text) {
    setQuestion(text);
    inputRef.current?.focus();
  }

  async function signOut() {
    try {
      await postJson("/auth/logout", {});
    } finally {
      setRun(null);
      setPhase("signed-out");
    }
  }

  if (phase === "loading") {
    return (
      <main id="main">
        <h1>Service Ops Intelligence</h1>
        <p className="muted" role="status">Loading</p>
      </main>
    );
  }

  if (phase === "signed-out") {
    return (
      <main id="main">
        <h1>Service Ops Intelligence</h1>
        <div className="card card-pad" role="status">
          <p>An invite link is required. Open the link you were sent to sign in.</p>
        </div>
      </main>
    );
  }

  const timer =
    run && (run.status === "working" ? workingLabel(elapsed) : finishedLabel(run.ms, run.status === "done"));
  let cardClass = "card";
  if (run?.status === "failed") cardClass = run.refusal ? "card card-refusal" : "card card-error";
  if (run?.status === "done" && run.result.outcome === "degraded") cardClass = "card card-degraded";

  return (
    <main id="main">
      <section id="ask" className="stack">
        <h1>Ask about field-service operations</h1>
        <p className="lede">
          Incident reporting, customer sentiment and volume forecasts from one question. A router
          picks the specialist agent, and an independent QA agent checks the figures before you
          see them.
        </p>
        <form className="ask-form" onSubmit={submit}>
          <label htmlFor="question" className="sr-only">Your question</label>
          <input
            id="question"
            name="question"
            type="text"
            ref={inputRef}
            value={question}
            maxLength={MAX_QUESTION}
            autoComplete="off"
            onChange={(e) => setQuestion(e.target.value)}
            aria-describedby="question-hint"
          />
          <button type="submit" className="primary" disabled={busy || !question.trim()}>
            {busy ? "Asking" : "Ask"}
          </button>
          <div className="form-foot">
            <span id="question-hint" className="muted small">
              {question.length} of {MAX_QUESTION} characters. Answers can take up to two minutes.
            </span>
            <button type="button" className="link" onClick={signOut}>Sign out</button>
          </div>
        </form>
      </section>

      <section aria-labelledby="examples-heading" className="stack">
        <h2 id="examples-heading" className="eyebrow">Try a question</h2>
        <div className="examples">
          {EXAMPLES.map((group) => (
            <div key={group.area} className={group.edge ? "example-group example-edge" : "example-group"}>
              <span className="example-area">{group.area}</span>
              {group.items.map((item) => (
                <button
                  key={item.q}
                  type="button"
                  className="example"
                  onClick={() => fillExample(item.q)}
                >
                  {item.q}
                  {item.note && <span className="muted"> · {item.note}</span>}
                </button>
              ))}
            </div>
          ))}
        </div>
      </section>

      {run && (
        <section className={cardClass} aria-label="Answer">
          <div className="card-head">
            <span className="muted">
              You asked: <b>{run.asked}</b>
            </span>
            <span className="timer" data-testid="timer">{timer}</span>
          </div>
          <div className="card-body" aria-live="polite" aria-busy={busy}>
            {run.status === "working" && <div className="pending" aria-hidden="true" />}
            {run.status === "failed" && (
              <Callout kind={run.refusal ? "refusal" : "error"} icon={run.refusal ? "pause" : "cross"}>
                {run.message}
              </Callout>
            )}
            {run.status === "done" && <Answer result={run.result} />}
          </div>
        </section>
      )}
    </main>
  );
}
