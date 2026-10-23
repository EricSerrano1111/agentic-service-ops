import { UNNUMBERED, diagramDescription } from "../lib/journey.mjs";

// The services diagram, shared by "How it works" (static) and the answer journey (rule 10), where
// the services a request used are highlighted in the order they were used and the rest are dimmed
// and say "not called". Text only; no figure is computed here.

const STATIC_LABEL =
  "Architecture diagram. The browser calls the gateway, which calls the orchestrator. The orchestrator calls three specialist agents, reporting, sentiment and forecast, each through its own MCP tool server to Cloud SQL, and the QA agent, which has its own SQL connection to Cloud SQL.";

function Box({ x, y, w = 128, h = 44, lines, tone, state }) {
  const cls = ["dg-box", tone ? `dg-${tone}` : "", state ? `dg-${state}` : ""].filter(Boolean).join(" ");
  return (
    <g className={cls}>
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

/**
 * `order` is the journey's box order (lib/journey.mjs `boxOrder`) or undefined for the static
 * picture; `lit` is how many of the called boxes are lit so far (the replay), all by default.
 */
export default function ArchitectureDiagram({ order, lit = Infinity }) {
  const cols = [64, 208, 352, 496];
  const journey = order !== undefined;

  // One box's lines and state. Called: "2 · Name"; not called: "Name" and "not called".
  const node = (key, lines, offLines) => {
    if (!journey) return { lines };
    if (!(key in order)) return { lines: offLines ?? [lines[0], "not called"], state: "off" };
    const number = order[key];
    const first = UNNUMBERED.includes(key) ? lines[0] : `${number} · ${lines[0]}`;
    return { lines: [first, ...lines.slice(1)], state: number <= lit ? "on" : "pending" };
  };
  const plain = (lines) => (journey ? { lines: ["Browser"], state: "on" } : { lines });

  return (
    <svg
      className="diagram"
      viewBox="0 0 560 470"
      role="img"
      aria-label={journey ? diagramDescription(order) : STATIC_LABEL}
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
      <Box x={216} y={0} {...plain(["Browser"])} />
      <Box x={216} y={68} {...node("gateway", ["Gateway"])} />
      <Box x={200} y={136} w={160} tone="accent" {...node("orchestrator", ["Orchestrator", "(router)"], ["Orchestrator", "not called"])} />
      <Box x={cols[0] - 64} y={232} tone="agent" {...node("reporting", ["Reporting", "agent"])} />
      <Box x={cols[1] - 64} y={232} tone="agent" {...node("sentiment", ["Sentiment", "agent"])} />
      <Box x={cols[2] - 64} y={232} tone="agent" {...node("forecast", ["Forecast", "agent"])} />
      <Box x={cols[3] - 64} y={232} tone="qa" {...node("qa", ["QA", "agent"])} />
      <Box x={cols[0] - 64} y={312} {...node("mcp_reporting", ["Incidents", "MCP server"])} />
      <Box x={cols[1] - 64} y={312} {...node("mcp_sentiment", ["Feedback", "MCP server"])} />
      <Box x={cols[2] - 64} y={312} {...node("mcp_forecast", ["Volume", "MCP server"])} />
      <Box x={cols[3] - 64} y={312} tone="qa" {...node("qa_sql", ["Own SQL,", "read-only"])} />
      <Box x={0} y={412} w={560} {...node("db", ["Cloud SQL (PostgreSQL)"], ["Cloud SQL", "not called"])} />
    </svg>
  );
}
