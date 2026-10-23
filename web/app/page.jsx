"use client";

import { useEffect, useRef, useState } from "react";

const MAX_QUESTION = 500;

// Data dictionary section 6, "Answer display (UI)", rule 6 (TS-20-E): shown on every screen,
// before any question and on every answer; plain text, not dismissible, identical every time.
const SYNTHETIC_NOTICE =
  "Demonstration system: all data here is synthetic, generated for this project. " +
  "It describes no real company, customer, technician or operation.";

function Notice() {
  return (
    <p id="synthetic-notice" data-testid="synthetic-notice" className="hint">
      {SYNTHETIC_NOTICE}
    </p>
  );
}

// One screen (ADR-080). Everything shown comes from the gateway's view of the answer; the
// display rules are data dictionary section 6, "Answer display (UI)". Text only: nothing from
// a response is ever rendered as HTML.

async function postJson(path, body) {
  return fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export default function Page() {
  const [phase, setPhase] = useState("loading"); // loading | signed-out | ready
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const started = useRef(false);

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

  async function submit(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await postJson("/api/ask", { question: text });
      const body = await res.json().catch(() => ({}));
      if (res.status === 401) {
        setPhase("signed-out");
      } else if (res.ok) {
        setResult(body);
      } else {
        setError(body.detail || "The request could not be completed. Please try again.");
      }
    } catch {
      setError("The service could not be reached. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    try {
      await postJson("/auth/logout", {});
    } finally {
      setResult(null);
      setPhase("signed-out");
    }
  }

  if (phase === "loading") {
    return (
      <main>
        <Notice />
        <h1>Service Ops Intelligence</h1>
        <p className="hint" role="status">Loading</p>
      </main>
    );
  }

  if (phase === "signed-out") {
    return (
      <main>
        <Notice />
        <h1>Service Ops Intelligence</h1>
        <div className="panel" role="status">
          <p>An invite link is required. Open the link you were sent to sign in.</p>
        </div>
      </main>
    );
  }

  return (
    <main>
      <Notice />
      <div className="row">
        <h1>Service Ops Intelligence</h1>
        <button type="button" className="link" onClick={signOut}>Sign out</button>
      </div>

      <form onSubmit={submit}>
        <label htmlFor="question">Your question</label>
        <textarea
          id="question"
          name="question"
          value={question}
          maxLength={MAX_QUESTION}
          onChange={(e) => setQuestion(e.target.value)}
          aria-describedby="question-hint"
        />
        <div id="question-hint" className="hint">
          {question.length} of {MAX_QUESTION} characters. Answers can take up to two minutes.
        </div>
        <button type="submit" disabled={busy || !question.trim()}>
          {busy ? "Asking" : "Ask"}
        </button>
      </form>

      <div aria-live="polite">
        {error && <div className="error" role="alert">{error}</div>}

        {result && (
          <section className="panel" aria-label="Answer">
            <h2>Question</h2>
            <p>{result.question}</p>

            {result.escalate && (
              <>
                <h2>Follow-up</h2>
                <p className="flag">Sent for follow-up. {result.warning}</p>
              </>
            )}

            <h2>Answer</h2>
            <p>{result.answer}</p>

            {result.interpreted_as && (
              <>
                <h2>Interpreted as:</h2>
                <p className="interpreted">{result.interpreted_as}</p>
              </>
            )}

            {result.qa_text && (
              <>
                <h2>Verification</h2>
                <p>{result.qa_text}</p>
              </>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
