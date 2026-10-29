import ArchitectureDiagram from "../components/ArchitectureDiagram";

// A static page (ADR-117 item 2): no data, no timings. Every claim here is traced to a document
// in the repository's docs/ folder in the pull request that added it.

export const metadata = {
  title: "How it works · Service Ops Intelligence",
  description: "How one question travels through the router, a specialist agent, its tools and QA.",
};

const HOPS = [
  "Your browser sends the question to the gateway, which checks your invite.",
  "The gateway passes it to the orchestrator.",
  "The orchestrator's router picks one specialist: reporting, sentiment or forecast.",
  "The specialist reads the question into a structured request and calls its own MCP tool server.",
  "The tool server queries Cloud SQL with its own least-privilege database role.",
  "The QA agent recomputes the figures with its own read-only SQL.",
  "The orchestrator returns the checked answer through the gateway to your browser.",
];

export default function HowItWorks() {
  return (
    <main id="main" className="prose">
      <h1>How it works</h1>
      <p className="lede">
        A question passes through a router, one specialist agent with its own tools, and an
        independent QA check before an answer comes back.
      </p>

      <figure className="figure">
        <ArchitectureDiagram />
        <figcaption className="muted small">
          Arrows show the direction of each call. The QA agent is called by the orchestrator and
          reads the database itself.
        </figcaption>
      </figure>
      <ol className="hops" aria-label="The hops in the diagram">
        {HOPS.map((hop) => (
          <li key={hop}>{hop}</li>
        ))}
      </ol>

      <section>
        <h2>One question&rsquo;s path</h2>
        <p>
          The gateway checks your invite and forwards the question to the orchestrator. Its router
          decides whether the question is about incident reporting, customer sentiment or a volume
          forecast, and sends it to that specialist over A2A. The specialist reads the question into
          a structured request, fetches figures through its own MCP tool server and fills in an
          answer template. The QA agent checks the draft against the database before it returns.
        </p>
      </section>

      <section>
        <h2>What each agent does</h2>
        <ul className="plain-list">
          <li>
            <b>Router (in the orchestrator):</b> picks the specialist, asks you to rephrase an open
            question, asks for one question per area, or declines a question outside the three
            areas.
          </li>
          <li>
            <b>Reporting agent:</b> incident counts, SLA compliance, first-time fix rate and
            repeat-visit drivers.
          </li>
          <li>
            <b>Sentiment agent:</b> how customers feel, from the words in their feedback, with
            trends and example comments.
          </li>
          <li>
            <b>Forecast agent:</b> weekly request volume for the coming weeks, from a stored model.
          </li>
          <li>
            <b>QA agent:</b> recomputes the figures with its own SQL and checks the answer&rsquo;s
            range and filters.
          </li>
        </ul>
      </section>

      <section>
        <h2>What &ldquo;Interpreted as&rdquo; and the verification line mean</h2>
        <p>
          &ldquo;Interpreted as&rdquo; shows how the specialist read your question: the area, the
          measure, the period and the region. Read it against your question, because it is your
          check on a misreading. &ldquo;Figures checked for the request as interpreted&rdquo; means
          the figures are correct for that reading. It does not mean your question was understood
          correctly. A separate check of the reading against your question runs too, but it is
          advisory and does not stop an answer.
        </p>
      </section>

      <section>
        <h2>Security boundaries</h2>
        <p>
          Each agent&rsquo;s tool server connects to the database as its own least-privilege role,
          and the QA agent as its own read-only role. No agent can read customer contact data, so
          it never reaches a prompt. Services call each other with IAM-authenticated requests, and
          secrets live in Secret Manager, not in code or images.
        </p>
      </section>

      <section>
        <h2>How well it works</h2>
        <p>
          The headline figures of the evaluation, each traced to the file it was read from, are on
          the <a href="/results/">Evaluation results</a> page.
        </p>
      </section>

      <section>
        <h2>Limitations</h2>
        <ul className="plain-list">
          <li>
            The data and the sentiment model are synthetic. Nothing here describes a real company or
            customer.
          </li>
          <li>
            Ambiguous questions are only partly handled: about two in three open-ended questions
            get a clarification, and the rest are routed to the best fit.
          </li>
          <li>
            The interpretation check is advisory. A misreading can still be marked as having
            checked figures, which is why the &ldquo;Interpreted as&rdquo; line matters.
          </li>
          <li>The data runs to 2026-08-30, and relative dates such as &ldquo;last month&rdquo; count from then.</li>
        </ul>
      </section>
    </main>
  );
}
