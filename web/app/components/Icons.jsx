// Small inline icons. Each state pairs an icon with words, so colour is never the only signal.
const PATHS = {
  check: <path d="M6 10.5 L9 13.2 L14.2 7.4" strokeLinecap="round" strokeLinejoin="round" />,
  cross: <path d="M7 7 L13 13 M13 7 L7 13" strokeLinecap="round" />,
  info: (
    <>
      <path d="M10 9 L10 14" strokeLinecap="round" />
      <circle cx="10" cy="6.2" r="0.6" />
    </>
  ),
  help: (
    <>
      <path
        d="M7.6 7.6 Q7.8 5.4 10 5.4 Q12.4 5.4 12.4 7.6 Q12.4 9.2 10.4 10 Q10 10.2 10 11.6"
        strokeLinecap="round"
      />
      <circle cx="10" cy="14.4" r="0.6" />
    </>
  ),
  pause: <path d="M8 6.5 L8 13.5 M12 6.5 L12 13.5" strokeLinecap="round" />,
  clock: <path d="M10 5.5 L10 10 L13 11.8" strokeLinecap="round" strokeLinejoin="round" />,
};

// A warning triangle is drawn on its own: the others sit inside a circle.
export default function Icon({ name }) {
  if (name === "warn") {
    return (
      <svg className="icon" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M10 2.8 L18 16.8 L2 16.8 Z" strokeLinejoin="round" />
        <path d="M10 8 L10 12" strokeLinecap="round" />
        <circle cx="10" cy="14.6" r="0.5" />
      </svg>
    );
  }
  return (
    <svg className="icon" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="10" cy="10" r="9" />
      {PATHS[name]}
    </svg>
  );
}
