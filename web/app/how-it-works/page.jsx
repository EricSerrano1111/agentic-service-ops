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

function Box({ x, y, w = 128, h = 44, lines, tone }) {
  return (
    <g className={tone ? `dg-box dg-${tone}` : "dg-box"}>
      <rect x={x} y={y} width={w} height={h} rx="10" />
      {lines.map((line, i) => (
        <text
          key={line}
          x={x + w / 2}
          y={y + h / 2 + (i - (lines.length - 1) / 2) * 17 + 5}
          textAnchor="middle"
        >
          {line}
        </text>
      ))}
    </g>
  );
}

function Diagram() {
  const cols = [64, 208, 352, 496];
  return (
    <svg
      className="diagram"
      viewBox="0 0 560 470"
      role="img"
      aria-label="Architecture diagram. The browser calls the gateway, which calls the orchestrator. The orchestrator calls three specialist agents, reporting, sentiment and forecast, each through its own MCP tool server to Cloud SQL, and the QA agent, which has its own SQL connection to Cloud SQL."
    >
      <defs>
        <marker id="dg-head" orient="auto" markerWidth="8" markerHeight="8" refX="6" refY="4">
          <path d="M0 0 L8 4 L0 8 Z" className="dg-head" />
        </marker>
      </defs>
      <g className="dg-line" markerEnd="url(#dg-head)">
        <path d="M280 44 L280 66" />
        <path d="M280 110 L280 132" />
        {cols.map((c) => (
          <path key={c} d={`M280 176 L280 206 L${c} 206 L${c} 230`} fill="none" />
        ))}
        {cols.map((c) => (
          <path key={`m${c}`} d={`M${c} 278 L${c} 310`} />
        ))}
        {cols.map((c) => (
          <path key={`s${c}`} d={`M${c} 358 L${c} 410`} />
        ))}
      </g>
      <Box x={216} y={0} lines={["Browser"]} />
      <Box x={216} y={68} lines={["Gateway"]} />
      <Box x={200} y={136} w={160} lines={["Orchestrator", "(router)"]} tone="accent" />
      <Box x={cols[0] - 64} y={232} lines={["Reporting", "agent"]} tone="agent" />
      <Box x={cols[1] - 64} y={232} lines={["Sentiment", "agent"]} tone="agent" />
      <Box x={cols[2] - 64} y={232} lines={["Forecast", "agent"]} tone="agent" />
      <Box x={cols[3] - 64} y={232} lines={["QA", "agent"]} tone="qa" />
      <Box x={cols[0] - 64} y={312} lines={["Incidents", "MCP server"]} />
      <Box x={cols[1] - 64} y={312} lines={["Feedback", "MCP server"]} />
      <Box x={cols[2] - 64} y={312} lines={["Volume", "MCP server"]} />
      <Box x={cols[3] - 64} y={312} lines={["Own SQL,", "read-only"]} tone="qa" />
      <Box x={0} y={412} w={560} lines={["Cloud SQL (PostgreSQL)"]} />
    </svg>
  );
}

export default function HowItWorks() {
  return (
    <main id="main" className="prose">
      <h1>How it works</h1>
      <p className="lede">
        A question passes through a router, one specialist agent with its own tools, and an
        independent QA check before an answer comes back.
      </p>

      <figure className="figure">
        <Diagram />
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
