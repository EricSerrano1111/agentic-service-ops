# **Agentic Service Operations Intelligence Platform**

## **Project Proposal and Business Case**

**Document Information**

Author(s): Eric Serrano

Keywords: Agentic, AI, Multi-Agent, Field Service, Operations, Business Intelligence, Multi Context Protocol (MCP), Agent to Agent (A2A), Capstone

## **Document Revision History**

| **Version** | **Date**  | **Author**   | **Changes Made** |
| ----------- | --------- | ------------ | ---------------- |
| 1.0         | 9/16/2026 | Eric Serrano | Initial version  |
|             |           |              |                  |
|             |           |              |                  |
|             |           |              |                  |
|             |           |              |                  |
|             |           |              |                  |

## **Reviewer(s)**

| **Name**                | **Contact Information** |
| ----------------------- | ----------------------- |
| Professor William Sunna | Canvas                  |
|                         |                         |



## **Business Problem and/or Opportunity**

Meridian Field Services dispatches technicians to install, repair, maintain, and upgrade customer network and hardware infrastructure. This is a networking business built on responding quickly and consistently across a growing number of service requests. As request volume has grown, so has the amount of operational data generated: completed jobs, quality incidents, customer feedback, and demand patterns across regions and skill categories (networking, hardware, cabling, security systems, power systems).

Today, these are the kind of operational questions constantly asked:

- _Which incident types are driving the most repeat visits this quarter?_
- _Is customer sentiment trending down in a specific region?_
- _How much technician capacity will we need next month?_

Answering any of these questions requires either a data analyst pulling and interpreting the numbers manually, or an operations leader attempting to extract insights themselves. Both paths are slow relative to how often these questions actually come up, and neither are scalable. As the operation continues to see growth, service volume is increasing but the organization is not currently in a position to invest in analyst headcount. The result is that day-to-day operational decisions are frequently made on intuition or stale reporting rather than current data, and the analysts who could answer precisely have become a bottleneck rather than a resource.

This is also a strategic timing issue, not just an efficiency one. As Meridian expands its technician headcount and adds service categories, leadership has already signaled a preference for scaling analytical capability without scaling analyst headcount. Meridian is seeking tools that let operations staff get answers directly rather than routing every question through a specialist. Left unaddressed, that gap will only widen as more technicians and more service requests mean more data, and more data without more accessible reporting means the bottleneck gets worse.

The opportunity is a system that lets operations leaders ask questions about quality, customer sentiment, and demand in plain language to not only get answers immediately but without waiting on an analyst or learning new technical skills. The harder requirement, and the one that makes this more than a convenience feature, is that those answers need to be verified before they reach a decision-maker as a wrong number quietly informing a staffing or escalation decision is worse than no number at all. The system this project builds is designed around that requirement directly where every answer is quality checked before it's returned.

## **Project Outcomes**

This project gives Meridian's operations leaders a way to ask direct, natural-language questions about service quality, customer sentiment, future demand, and receive immediate, verified answers without waiting on an analyst or learning new technical skills.

Beyond speed, the system changes how much operations leaders can trust the answers they act on. Every response is checked before it reaches a decision-maker, so leaders can act on the numbers directly, rather than treating them as a starting point for a follow-up conversation with the analyst team.

**The outcomes Meridian should expect from this project:**

- **Faster decisions**: Quality, sentiment, and demand questions that once took hours or days to answer now get answered in minutes, with no analyst in the loop.
- **Reduced reliance on limited analyst capacity**: Routine reporting questions are handled directly by the system, freeing analysts for work the system can't do.
- **More confident day-to-day decisions**: Because outputs are verified before they reach a decision-maker, staffing, escalation, and resourcing choices are made on checked numbers instead of intuition or a stale report.
- **Analytical capacity that scales with growth**: The reporting capability Meridian gains here doesn't require proportional analyst headcount growth as service volume increases.

### **Success Criteria (including measurement metrics)**

The following criteria translate project outcomes into measurable terms:

- **Faster access to operational answers:** Success means an operations leader gets a verified answer to a natural-language question with no analyst involved. Measured as end-to-end response time from question to answer, tracked separately for quality, sentiment, and demand questions. This is the outcome leaders will feel most directly as it's the gap between the current wait and an answer available in the moment a decision needs to be made.
- **Reduced dependency on analyst availability:** Success means routine operational questions in quality trends, sentiment shifts, and demand outlooks are answered directly by the system but also that the system correctly recognizes when a question is ambiguous or outside what it can answer, rather than guessing. Measured as routing accuracy across a representative set of test questions, including deliberately ambiguous and out-of-scope cases, with failure cases documented rather than hidden in an aggregate score. For an operations leader, a system that quietly guesses wrong is worse than one that visibly declines, so how it fails matters as much as how often it succeeds.
- **Verified accuracy that can be acted on:** Success means answers reaching a decision-maker have been checked, and incorrect or low-confidence answers are caught before delivery, not after a bad decision is made from them. Measured as the verification stage's catch rate against deliberately introduced errors, plus how often it correctly escalates a case it can't verify instead of passing it through. This is the evidence that turns "we added a review step" into a number leadership can actually weigh before trusting the system with a staffing or escalation call.
- **Analytical capacity that scales without adding headcount:** Success means Meridian can answer a growing volume of analytical questions without adding analysts to keep pace. The proposed system measures compute cost per answered question, tracked as question volume increases and compared against the cost of hiring additional analysts to handle the same growth. This shows leadership exactly what they avoid spending by not scaling headcount.

### **Scope**

This project delivers the following capabilities and components:

- **Natural-language query interface:** Operations leaders ask a question in plain English about quality, customer sentiment, or expected demand and receive an answer directly, with no query language or dashboard training required. When a question is ambiguous or outside what the system can answer, it says so rather than guessing.
- **Three specialist analytical capabilities:** Incident/quality reporting, customer sentiment analysis on feedback text, and service volume forecasting.
- **Automated answer verification:** Every answer is checked before it reaches an operations leader, with a documented escalation path for cases the system can't verify with sufficient confidence, rather than delivering an unchecked result.
- **Enforced data-access boundaries:** Each system capability can only reach the data it needs. For example, the sentiment capability never sees internal investigation notes or billing information, and customer contact details are never exposed to any of the three capabilities.
- **A representative operational dataset:** Ahead of connecting to Meridian's live systems, this project is developed and validated against a dataset modeling realistic field service operations. Database testing table examples include: accounts, technicians, service requests, incidents, and customer feedback. This is an approach that proves a new capability before it touches production data.
- **A deployed, usable interface:** A web-based front end that can be accessed directly by a user, showing each answer alongside its verification status.

### **Out of Scope**

This project intentionally excludes the following, several of which are reasonable candidates for future releases once the core system is proven:

- **Direct integration with Meridian's live production systems:** This phase validates the approach against a representative operational dataset, not live customer or billing data. Connecting to Meridian's actual systems is a natural next step once the approach is proven, not part of this delivery.
- **Any ability to take action on Meridian's behalf:** The system answers questions. It does not dispatch technicians, modify records, or issue credits. It is a decision-support tool for operations, not an operational control system. Extending it to take action under human approval is a reasonable future release.
- **Skill- and capacity-based staffing recommendations:** This phase answers what is happening as in quality, sentiment, demand but not what to do about it. A logical next release once the underlying reporting is proven out.
- **External market research web-scraping agent:** An agent that gathers external market data is not included in this phase. A narrowly scoped version, such as pulling an external SLA benchmark to contextualize the demand forecast, is a reasonable candidate for a future release if a specific need for it emerges.
- **Multi-turn, back-and-forth conversation:** Each question is answered fully and independently. The system does not hold context across follow-up questions in the same session in this phase. Conversational follow-up is a natural interface improvement for a later release.
- **Languages other than English:** Both the questions asked and the customer feedback analyzed are assumed to be in English for this phase.

### **End State**

At the conclusion of this project, Meridian's operations leaders have a working system they can use directly. They type a question about service quality, customer sentiment, or expected demand into a simple web interface and receive a verified answer within moments, without any involvement from the analyst team.

Behind that interface, three specialist reporting capabilities are fully operational, each drawing only on the data it needs, and every answer passes through an independent verification step before it's delivered. When an answer can't be verified with confidence, or a question falls outside what the system is built to answer, it says so and flags the case for a person, rather than guessing.

The system is proven, not assumed to work. Before delivery, each analytical capability is tested against a known-correct set of answers, and the verification step's ability to catch a mistake is measured by deliberately introducing wrong answers and confirming they're caught. The routing behind the natural-language interface is scored against a documented set of test questions including intentionally ambiguous and out-of-scope cases so its accuracy, and where it falls short, are known quantities rather than a claim.

The system runs against a representative operational dataset rather than Meridian's live production systems, consistent with the pilot approach described in the **Scope** section. Connecting it to live data, extending it to recommend or take action, and adding capabilities such as external market or benchmark data are explicitly future work, not part of this delivery.

## **Assumptions**

This plan rests on the following assumptions. If any of these prove incorrect, the scope, timeline, or cost described in this document would need to be revisited.

- **Dataset realism:** The representative operational dataset used to build and validate this system reflects realistic field service business patterns (such as seasonal demand, incident rates, and a natural mix of customer sentiment) closely enough that results validated against it will hold up once the system is exposed to live operations data.
- **Stable underlying technology:** The AI models and communication protocols this system depends on remain available and behave consistently, at their current specification, for the length of this project. A significant change to a pricing, availability, or protocol behavior partway through could affect delivery cost or timeline.
- **Fixed team and timeline:** This phase is scoped for delivery by a single developer within a fixed delivery window. The scope described in this document assumes that pace. Any addition to scope would extend the timeline or require additional resourcing.
- **Operating cost stays within plan:** The compute cost of running the system at pilot scale remains within the budget allocated for this phase.
- **Leadership follow-through on adoption:** Operations leaders are willing to act on verified answers directly once the system is delivered, rather than continuing to route questions through the analyst team out of habit.

## **Known Risks**

- **Representative data may not fully capture live operating patterns:** This phase validates the system against a representative dataset rather than Meridian's live production data (see **Assumptions**). If real-world patterns diverge meaningfully from what's modeled, results seen in this phase may not transfer directly to live operations without further validation. 
    - **Mitigation:** the modeled data is checked against industry known field-service industry patterns before any analytical capability is built on top of it, and results from this phase are treated as pilot evidence, not a production guarantee.

- **Some customer feedback is inherently hard to classify with confidence:** Sentiment is not always clear-cut as sarcasm, mixed reviews, and ambiguous language can mislead any classification approach, human or automated. 
    - **Mitigation:** sentiment classifications are cross-checked against the customer's numeric satisfaction rating where one is available, and low-confidence cases are flagged for human review rather than presented as certain.

- **A single point of delivery:** This phase is built and delivered by one developer within a fixed timeline, without a second reviewer to catch blind spots along the way.
    - **Mitigation:** automated testing and structured evaluation checkpoints substitute for a second reviewer, and progress is checked against the plan at defined intervals throughout delivery rather than only at the end.

- **Dependence on external AI agent vendors:** The models and infrastructure this system relies on are provided by outside vendors, whose pricing, availability, or terms could change during this phase. 
    - **Mitigation:** the system is built so its AI agent provider can be swapped without reworking the system around it, and cost is monitored continuously against plan so a change is caught early rather than discovered at delivery.

- **Underlying technology is new and evolving quickly:** The standards this system uses for coordinating its reporting components are recent and still evolving industry-wide. A significant change mid-project could require rework. 
    - **Mitigation:** this phase is built against a fixed, currently stable version of each standard, with no plan to adopt updates mid-project unless a specific issue requires it.

## **Appendices**

Running behind each specialist's MCP tool - two are deterministic code with no model involved and two are custom built models.

The table below breaks this down agent by agent:

| **Agent**              | **What's Behind MCP Tool**                                                                                                          | **Model Needed?**       |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| Reporting              | SQL queries & standardized metric calculations.                                                                                     | No - deterministic code |
| Sentiment              | A classifier, customer trained on labeled customer feedback                                                                         | Yes - custom model      |
| Forecast               | A regression/time-series model, customer trained on historical volume data                                                          | Yes - custom model      |
| Quality Assurance (QA) | Verification logic, re-running queries, checking forecast accuracy against threshold, scoring sentiment against labeled holdout set | No - deterministic code |