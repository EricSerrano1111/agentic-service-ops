// One horizontal bar with its number written beside it, so length and colour are never the only
// signal. The width is the only thing computed from a figure: value over the scale's maximum.
// Drawn as SVG attributes, not a style attribute (the CSP forbids inline styles).

const BAR_WIDTH = 100;
const BAR_HEIGHT = 10;

export default function Bar({ label, text, value, max, source, base = false }) {
  const width = max > 0 ? (value / max) * BAR_WIDTH : 0;
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <svg
        className={base ? "bar bar-base" : "bar"}
        viewBox={`0 0 ${BAR_WIDTH} ${BAR_HEIGHT}`}
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        <rect className="bar-track" width={BAR_WIDTH} height={BAR_HEIGHT} />
        <rect className="bar-fill" width={width} height={BAR_HEIGHT} />
      </svg>
      <strong className="bar-num">{text}</strong>
      <code className="src">{source}</code>
    </div>
  );
}
