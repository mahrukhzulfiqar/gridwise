# Discovery plan: user interviews with EV owners

**Status:** planned; [desk research](desk-research.md) done first and refined the target segment · **Owner:** Mahrukh Zulfiqar · **Findings:** [discovery.md](discovery.md) (after the interviews)

## Why now
GridWise v0.1 was built on assumptions. Before adding features (all-in price, charger control), I want to learn whether the core problem is real for EV owners in Denmark, and what would make them act on a recommendation.

## What I want to learn
| # | Question | Assumption in the [brief](brief.md) it tests | What would change my mind |
|---|---|---|---|
| 1 | How do people decide when to charge today? | People plug in and charge at the evening peak | Most already charge overnight automatically |
| 2 | Is their electricity price variable by the hour? | Spot-price savings reach the user | Many are on fixed-price contracts, so hourly timing saves them nothing |
| 3 | What tools do they already use (charger app, car app, supplier app)? | There is a gap to fill | Their charger app already schedules by price and they trust it |
| 4 | Do they care more about cost or CO2? | A balanced default fits most people | One clearly dominates |
| 5 | What would make them trust and act on a recommendation? | Showing "vs charging now" builds trust | They want automation, not advice |

## Who to talk to
**5 people**, enough to see patterns in a first round.
- Lives in Denmark, owns or leases an EV, charges at home at least weekly
- Mix: at least 2 in DK2 (Zealand) and 1 in DK1; at least 1 who does **not** use smart charging today
- Not: people who work in energy trading (too expert to represent the user)

**Where:** colleagues and friends with EVs, EV owner groups on Facebook or LinkedIn, neighbours with a home charger.

## Interview guide (30 minutes, video or in person)
Ask about past behaviour, not opinions about the future. Don't pitch GridWise until the last part.

**1. Warm-up (3 min)**
- What car do you drive, and how long have you had an EV?
- Where do you usually charge?

**2. Current behaviour (10 min)**
- Tell me about the last time you charged at home. When did you plug in? When did it actually charge?
- How did you decide that? Has that changed since you got the car?
- Does the time of day affect what you pay for electricity? How do you know?
- What app or settings do you use for charging, if any? Show me, if you can.

**3. Motivation and pain (7 min)**
- Have you ever tried to charge at a cheaper or greener time? What happened?
- What's the most annoying part of charging at home?
- If charging cost you nothing extra to think about, what would you do differently?

**4. Concept test (8 min)** *Share screen: [live demo](https://gridwise-dk.streamlit.app)*
- Task: "You plug in at 17:00 and need the car at 07:00. Find out when to charge." (Don't help; note where they hesitate.)
- What do you understand from this result? What would you do now?
- What would you need to see to trust it?
- Would you rather get advice like this, or have it happen automatically?

**5. Wrap-up (2 min)**
- Is there anything I should have asked?
- Do you know someone else with an EV I could talk to?

## Notes template (one per interview)
```
Interview #   Date:          Area: DK1 / DK2   Car:        Charger/app:
Electricity contract: hourly / fixed / don't know
How they charge today (their words):
Biggest pain (quote):
Cost vs CO2:
Demo: where they hesitated / what they misunderstood:
Trust: what they'd need:
Advice or automation:
Surprises:
```

## From notes to decisions
1. After each interview: write the notes the same day, and pull out 3 to 5 key quotes.
2. After all five: group observations by question (1 to 5 above) and mark each assumption **confirmed**, **weakened** or **wrong**.
3. Update the [roadmap](roadmap.md) and [decision log](decision-log.md) with what changes, and write findings in `discovery.md`.

## Ethics
Ask for consent to take notes, don't record without permission, and don't publish names: use "Interview 1 to 5" and anonymised quotes.
