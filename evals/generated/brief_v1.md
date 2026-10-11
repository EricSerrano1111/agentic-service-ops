# Question-writing brief v1

You are helping test a question-answering assistant used by the operations leaders of a
field-service company. You have not seen the assistant and you will not. Your job: write
realistic questions such a leader might type, and label each one with what a correct
assistant should do with it.

## The business

The company sends technicians to customer sites to do five kinds of work: installs,
repairs, maintenance, inspections and upgrades. Customers are business accounts, each with
one or more sites. Every site is in one of four regions: Northeast, Southeast, Central and
West.

Each job has a scheduled time, a promised service window (its SLA) that it either met or
missed, and an outcome. Some jobs need a follow-up visit to finish the work. Some jobs lead
to a quality incident, which has a type and a severity. After a job, the customer may leave
a written comment.

The records run from {DATA_START} to {DATA_END}. Treat today as {AS_OF_DATE}.

How periods are read, counting from today:
- "last month": the last full calendar month before today's month.
- "this month": from the first of today's month to today.
- "last quarter": the last full calendar quarter before today's quarter.
- "this quarter": from the first day of today's quarter to today.
- "the past N days" or "the past N weeks": the N days or weeks ending today.
- "year to date": from January 1 of today's year to today.
- A month or quarter with a year ("July 2026", "Q2 2026"): exactly that period.
- For the future: "next month" is the calendar month after today's; "the next N weeks" is
  the N weeks after today.

Some of the company's accounts: {ACCOUNT_NAMES}
Some of its technicians: {TECHNICIAN_NAMES}

## What the assistant covers: three areas

A question belongs to an area by what it asks to be measured.

1. **Operations reporting:** past performance figures. These are:
   - the number of quality incidents;
   - the incident rate (incidents per 100 completed jobs);
   - SLA compliance (the share of jobs that met their promised window);
   - the first-time fix rate (the share of completed jobs that needed no follow-up visit);
   - what is associated with follow-up visits.

   Figures cover a past period. They can be for all sites, or narrowed to one region, one
   account or one technician. They can be broken down by account, region, kind of work or
   technician. Incident counts can also be broken down by incident type or severity.
2. **Customer sentiment:** what customers' written comments say. That means how many
   comments were positive, neutral, negative or mixed, and their shares; whether negative
   comments are rising or falling month by month or quarter by quarter; and a few example
   comments. It covers a past period, for all sites or one region.
3. **Volume forecast:** how many service requests to expect per week in the future, up to
   26 weeks ahead, in total or for one kind of work.

Out of scope: billing, revenue, invoices, costs and prices; staffing, schedules and pay;
parts and inventory; customer contact details; anything about other companies; and general
knowledge.

## Which area a question belongs to (the label rules)

- Asks for a past performance figure → `reporting`.
- Asks what customers said or felt in their comments → `sentiment`.
- Asks about the future, whatever the measure → `forecast`, even when the forecast area
  will then explain it can only forecast request volume.
- Fits one area but asks for a detail that area doesn't offer (for example, comment
  sentiment broken down by technician) → that area. The area will explain what it can't do.
- Clearly fits one area, names what it wants measured, but leaves out a detail such as the
  period, the region or the breakdown → that area. This is *underspecified*, not ambiguous.
- Explicitly asks for things from two or more areas in one question → `multi_domain`, with
  those areas as `candidate_areas`.
- Could reasonably be read as asking for measures from two or more areas, so that the
  answers would be different kinds of thing, including a question that names no measure at
  all (for example "how are things going with Northwind?" or "how's the West doing?") →
  `ambiguous`, with the plausible areas as `candidate_areas`.
- Anything outside the three areas → `out_of_scope`.

## How to write

- Write the way busy managers type: short and informal, sometimes vague, with shorthand
  ("FTF", "SLA %", "Q3"). Add a typo now and then: no more than one question in ten.
- Vary the wording. Don't reuse a sentence pattern more than twice in a batch.
- Each question stands alone, with no follow-ups and no "as I asked before".
- Don't write questions about star ratings on their own.
- Don't mention the assistant, AI, databases or SQL.
- Use the account and technician names above. For a "not found" case, invent a name that
  isn't in the lists, and say so in the rationale.

## Output

Return only a JSON array. Each element:

```json
{
  "id": "string, unique within this batch, e.g. AMB-07",
  "category": "one of: clear_reporting, clear_sentiment, clear_forecast, underspecified, ambiguous, multi_domain, out_of_scope, near_miss, technician, filtered, unsupported_in_area",
  "question": "the question exactly as the manager would type it",
  "expected_route": "reporting | sentiment | forecast | multi_domain | ambiguous | out_of_scope",
  "candidate_areas": ["two or more of reporting, sentiment, forecast for ambiguous and multi_domain; otherwise empty"],
  "intent": null,
  "rationale": "one sentence: why this label, under the rules above"
}
```

`intent` is null for `ambiguous`, `multi_domain`, `out_of_scope` and `near_miss`. For every
other category, fill it in like this, using null where the question doesn't say:

```json
{
  "area": "reporting | sentiment | forecast",
  "measure": "reporting: incident_count | incident_rate | sla_compliance | first_time_fix_rate | followup_drivers; sentiment: sentiment_mix | sentiment_trend | example_comments; forecast: weekly_volume; any area: other (a measure that area doesn't offer)",
  "period_stated": true,
  "period_text": "the words in the question that give the period, or null",
  "period_start": "YYYY-MM-DD, worked out from today's date and the period rules above, or null if no period is stated",
  "period_end": "YYYY-MM-DD or null",
  "horizon_weeks": "forecast only: weeks ahead as an integer, or null",
  "region": "northeast | southeast | central | west | unsupported (the question names an area that isn't one of the four) | null",
  "account_name": "as written in the question, or null",
  "technician_name": "as written in the question, or null",
  "breakdown": "account | region | work_type | technician | incident_type | severity | month | quarter | null",
  "work_type": "install | repair | maintenance | inspection | upgrade | null",
  "sentiment_label": "positive | neutral | negative | mixed | null",
  "examples_requested": false
}
```

If the question states no period, leave the dates null. Don't guess what the assistant
would assume.

## Categories

You will be asked for one category per request, with a count. What each category is:

- `clear_reporting`, `clear_sentiment`, `clear_forecast`: plainly one area, nothing missing.
- `underspecified`: plainly one area and its measure, with a detail left out.
- `ambiguous`: as defined above. Make them realistic, not trick questions.
- `multi_domain`: explicitly asks for two or three areas at once.
- `out_of_scope`: plainly outside the three areas.
- `near_miss`: sounds operational and close to an area, but is out of scope (for example
  revenue by region, or technician overtime).
- `technician`: a reporting question about a named technician. About a third should use a
  name not in the list.
- `filtered`: a reporting or sentiment question narrowed to one region or one account.
  About one in five should name an area that isn't one of the four regions (for example
  "the Midwest"); label its region `unsupported`.
- `unsupported_in_area`: fits an area but asks for something it doesn't offer, labelled
  with that area.
