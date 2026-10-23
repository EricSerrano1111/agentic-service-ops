// The landing page's example questions (data dictionary section 6, rule 9). A click fills the
// input and never submits. `note` is the caption of an edge case, shown beside the question.
export const EXAMPLES = [
  {
    area: "Incident reporting",
    items: [
      { q: "What was SLA compliance in the Northeast last month?" },
      { q: "Which incident types were most common in July 2026?" },
    ],
  },
  {
    area: "Customer sentiment",
    items: [
      { q: "Is negative feedback trending up in the West?" },
      { q: "Show examples of negative comments from last month" },
    ],
  },
  {
    area: "Volume forecast",
    items: [{ q: "What weekly request volume should we expect for the next 8 weeks?" }],
  },
  {
    area: "See how it handles edge cases",
    edge: true,
    items: [
      { q: "How's the Southeast doing?", note: "too open: it asks you to choose" },
      { q: "What will revenue be next quarter?", note: "out of scope: it declines" },
    ],
  },
];
