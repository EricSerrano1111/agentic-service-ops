id: f01
category: ambiguous
question: Are our bigger accounts getting a worse deal from us lately?
expected: ambiguous
candidates: reporting, sentiment
reason: "Worse deal" could mean worse service outcomes (SLA compliance, incident rate, repeat visits for those accounts, a reporting question) or customers saying they're less happy (feedback sentiment trend, a sentiment question). It also doesn't say what "bigger" or "lately" means. The two readings return different kinds of answer.

id: f02
category: ambiguous
question: Is the repair side of the business in trouble?
expected: ambiguous
candidates: forecast, reporting, sentiment
reason: "Trouble" could mean demand about to fall (future weekly repair volume, forecast), execution problems (repair incident rate, first-time fix, SLA misses, reporting), or unhappy customers (repair feedback sentiment). No reading is favoured.

id: f03
category: ambiguous
question: Are we on track going into Q4?
expected: ambiguous
candidates: forecast, reporting
reason: "On track" could mean the volume we should expect (future weekly request volume, forecast) or whether current performance holds up (SLA compliance, incident rate to date, reporting). The question doesn't say which target it is measured against.

id: f04
category: ambiguous
question: Is quality slipping in the central region?
expected: ambiguous
candidates: reporting, sentiment
reason: "Quality" could be operational (incident rate, repeat-visit rate, first-time fix, SLA compliance, reporting) or perceived (share of negative feedback, sentiment). Both are plausible, and "central" is the only constraint.

id: f05
category: ambiguous
question: Where are we losing customer goodwill?
expected: ambiguous
candidates: sentiment, reporting
reason: "Goodwill" could mean where feedback is turning negative (sentiment by region or period) or where things go wrong operationally (incident counts by region, account, type or severity, reporting). The "where" could be region, account, service type or technician.

id: f06
category: underspecified
question: How's first-time fix looking for the Northeast?
expected: reporting
candidates: -
reason: Clearly the first-time fix rate. Region is given, period is missing.

id: f07
category: underspecified
question: Do our customers generally speak well of us?
expected: sentiment
candidates: -
reason: Clearly a question about customer feedback tone. Region and period are both missing.

id: f08
category: underspecified
question: What's the outlook for weekly request volume heading into year-end?
expected: forecast
candidates: -
reason: Clearly a future weekly volume question. Horizon is implied, but total versus service type is not stated.

id: f09
category: underspecified
question: Roughly how many repair requests should we expect each week?
expected: forecast
candidates: -
reason: "Should we expect" makes it a forecast of repair volume. The horizon (how many weeks ahead) is missing.

id: f10
category: underspecified
question: Is feedback from the West getting better or worse?
expected: sentiment
candidates: -
reason: A sentiment trend question with region given. The period to compare over is missing.

id: f11
category: clear
question: Forecast total weekly service request volume for the 13 weeks starting September 7, 2026.
expected: forecast
candidates: -
reason: Future weekly volume, total, with an explicit horizon. Nothing missing.

id: f12
category: clear
question: What share of customer feedback in the central region during Q2 2025 was negative?
expected: sentiment
candidates: -
reason: Negative-sentiment share with region and period stated.

id: f13
category: clear
question: What was our SLA compliance rate for requests dispatched in January 2026?
expected: reporting
candidates: -
reason: SLA compliance for a defined period, using the canonical dispatched_at date filter. Nothing missing.

id: f14
category: clear  (feeling words, not sentiment)
question: The dispatch team is dreading the quarter-end review. What was our incident rate per 100 completed requests in Q4 2025?
expected: reporting
candidates: -
reason: The feeling words ("dreading") describe staff, not customers, and carry no sentiment question. The ask is the incident rate with a defined period, which is reporting.

id: f15
category: clear  (feeling words, not sentiment)
question: How do our technicians feel about the new dispatch process?
expected: out_of_scope
candidates: -
reason: This asks about employee attitudes. The sentiment agent reads only customer feedback_text, and no table holds technician survey or opinion data. It is a deliberate trap for sentiment routing.
