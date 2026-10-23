// A static page (ADR-117 item 3). Each answer is traced to a document in the repository's
// docs/ folder in the pull request that added it.

export const metadata = {
  title: "FAQ · Service Ops Intelligence",
  description: "Common questions about declined questions, clarifications, the data and the limits.",
};

const ENTRIES = [
  {
    q: "Why was my question declined?",
    a: "The system answers three kinds of question: incident reporting, customer sentiment and weekly request-volume forecasts. Anything outside them, such as revenue, is declined with no figures, and so is a breakdown a specialist does not support. A question that covers several areas is not answered at once: ask one area at a time.",
  },
  {
    q: "Why was I asked to choose?",
    a: "When a question could reasonably mean different things, such as “How’s the Southeast doing?”, the router does not guess. It lists what each reading would answer and asks you to rephrase. About two in three open-ended questions get this reply today; the rest are routed to the best fit.",
  },
  {
    q: "What does “Interpreted as” mean?",
    a: "It is how the specialist read your question: the area, the measure, the period and the region. Check it against what you meant, because a figure can be correct for a request you did not intend.",
  },
  {
    q: "What do “Figures checked…” and “Not verified” mean?",
    a: "“Figures checked for the request as interpreted” means the QA agent recomputed the figures for that reading and they match. It does not say your question was understood correctly. “Not verified” means the answer failed the check, or the checking service was unavailable; “Not checked” means the request ended before the check ran.",
  },
  {
    q: "What data is this?",
    a: "A synthetic field-service dispatch database generated for this project. It describes no real company, customer or technician, and the customer comments were written by a language model once and then frozen.",
  },
  {
    q: "Why are dates relative to 2026-08-30?",
    a: "The dataset ends on 2026-08-30, so “last month” means July 2026, not the calendar month today. A question with no dates is answered for the last full month before that, and the answer says the range was assumed.",
  },
  {
    q: "Why can an answer take a while?",
    a: "Most answers arrive in a few seconds: the warm median was about 4 seconds in the Sprint 5 evaluation. The first question after the system has been idle can take 30 to 60 seconds while services start (cold starts measured 29 to 61 seconds). The system never waits longer than 120 seconds: past that, it returns a degraded answer instead.",
  },
  {
    q: "Why are some forecasts withheld?",
    a: "A forecast is released only if, in a back-test, its average error stayed within 30% and was no worse than a seasonal-naive baseline. For service types and horizons that fail, the system refuses the forecast and says so instead of showing a number.",
  },
  {
    q: "Is there a question limit?",
    a: "Yes. Each invite link allows 30 questions an hour, and the whole demo answers 50 questions a day, resetting at midnight Pacific time. A question can be up to 500 characters.",
  },
  {
    q: "How was the sentiment model trained?",
    a: "A BERT classifier was fine-tuned on the synthetic customer comments, so its results may not reflect how real customers write. Its confidence is calibrated, and comments it is unsure about are flagged for review.",
  },
];

export default function Faq() {
  return (
    <main id="main" className="prose">
      <h1>Frequently asked questions</h1>
      <p className="lede">Short answers about what the system does and where it stops.</p>
      {ENTRIES.map(({ q, a }) => (
        <section key={q} className="faq-entry">
          <h2>{q}</h2>
          <p>{a}</p>
        </section>
      ))}
    </main>
  );
}
