// Data dictionary section 6, "Answer display (UI)", rule 6 (TS-20-E): shown on every screen,
// before any question and on every answer; plain text, not dismissible, identical every time.
const SYNTHETIC_NOTICE =
  "Demonstration system: all data here is synthetic, generated for this project, and describes " +
  "no real company, customer, technician or operation. The sentiment model was trained on " +
  "synthetically written customer feedback, so its results may not reflect how real customers write.";

export default function Notice() {
  return (
    <p id="synthetic-notice" data-testid="synthetic-notice" className="notice">
      {SYNTHETIC_NOTICE}
    </p>
  );
}
