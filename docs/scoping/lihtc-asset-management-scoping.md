# Scoping questions — a private AI assistant for real estate asset management

Hey — thanks for doing this. Short version of what I'm building: a tool that lets
an AI assistant (like Claude) answer questions about property/portfolio data
**without that data ever leaving your own computer**. It runs locally, crunches the
spreadsheets itself, and only ever shows the AI a summary — not the raw files.

I already have it working for a couple of other fields (biomechanics research,
earthquake data, fitness data). I want to build a version aimed at **real estate
asset management / LIHTC**, and you're the person I know who actually lives in that
world. Your answers below decide what the tool computes, what it's allowed to touch,
and what it remembers.

### Ground rules (please read)

- **Do NOT send me any real data.** No real rent rolls, tenant info, deal terms,
  nothing. Just *describe the shape* — "a rent roll has one row per unit, with these
  columns." I'll build a fake/synthetic sample dataset from your descriptions so none
  of your actual data is ever used.
- Answer in whatever's easy — bullets, half-sentences, a voice memo, screenshots of a
  *blank* template. Depth helps but don't polish it.
- If you're short on time, **Sections 2 and 3 are the most important** — do those
  first.
- Total time: ~30–45 min if you go deep, 15 if you skim.

---

## Section 1 — The data you actually work with

1. When you're managing a property, what files land on your desk each month/quarter?
   (e.g., rent roll, T-12 / trailing-12 operating statement, operating budget,
   lender/agency reporting, tenant income certifications, HFA compliance reports,
   CapEx schedules… list whatever's real for you.)
2. Where do they come out of — Yardi, RealPage, MRI, AppFolio, Excel templates, PDFs
   from a property manager? Which come as clean spreadsheets vs. PDFs you have to
   re-key by hand?
3. For the 2–3 files you touch most, what does **one row** represent, and what columns
   are on it? (e.g., *rent roll: one row per unit — unit #, floorplan, sq ft, lease
   start/end, market rent, actual rent, status, set-aside %, income at certification…*)
4. What uniquely identifies a single property in your world — a property name, a deal
   code, an agency/BIN number, something else?

## Section 2 — The questions worth answering instantly  ⭐ (most important)

Imagine an assistant that already read all the files and will answer in plain English,
so you never open the spreadsheet yourself.

5. **What are the 5–8 questions you'd ask it most often?** Seed examples (replace with
   your real ones):
   - "Which properties are running below underwritten NOI this quarter?"
   - "Which assets are at risk of missing their 40/60 set-aside?"
   - "What's portfolio occupancy, and which way is it trending?"
   - "Which units are due for income recertification in the next 90 days?"
   - "Show DSCR by property against the loan covenant."
   - "Where are operating expenses running over budget, and by how much?"
6. For each question above, what numbers/metrics does the answer involve?
7. Which of those numbers are **pure math** (same inputs always give the same answer —
   NOI, DSCR, debt yield, cap rate, occupancy %) vs. which need **your judgment/
   assumptions** (vacancy factor, exit cap, expense growth)? I need to know which is
   which.
8. What's the single most **tedious recurring analysis** you'd most want off your plate?

## Section 3 — What's confidential vs. shareable  ⭐ (most important)

This section literally defines what the tool is allowed to let the AI see. The whole
point is that sensitive stuff is stripped out *before* anything reaches the AI.

9. On a rent roll or tenant income certification, which fields are **personally
   identifying / sensitive and must never leave the building**? (e.g., tenant name,
   SSN, DOB, household member names, exact income, phone/email…)
10. Which fields are **safe to summarize or share**? (e.g., unit count, aggregate
    occupancy, AMI-band distribution, NOI, expense ratios…)
11. Are there fields that are **sensitive individually but fine in aggregate**? (Classic
    example: one tenant's exact income = sensitive; the *income-band distribution*
    across the property = fine.)
12. Do your compliance exports come with any kind of **data dictionary or flag** that
    already marks which fields are PII / identifiers? (Even informally — "everyone knows
    columns A–F are the private ones.")

## Section 4 — What you track over time

The tool can remember things across quarters so you're not starting from scratch each
time you pick a property back up. This part is a big deal for asset management
specifically.

13. For a property you manage, what do you keep **notes on across quarters**? (variance
    explanations, business-plan milestones, lease-up progress, covenant watch-items…)
14. When you come back to a property after a quarter (or a year), what do you wish you
    could **instantly recall** about it?
15. Do you keep a **watch list** of at-risk assets? What puts a property on it, and what
    takes it off?
16. Are there **past mistakes or lessons** you'd want the tool to flag so they don't get
    repeated? (e.g., "we over-assumed lease-up speed on this asset type.")

## Section 5 — Data-handling rules at your firm

This grounds the core pitch — that local-only handling is what makes AI usable on this
data at all. I want the *real* policy, not the ideal.

17. At a place like Aegon (or institutional RE generally), what are the rules about
    putting confidential property / tenant / LP data into **outside software or AI
    tools**? Allowed, restricted, or flat-out prohibited?
18. If you wanted to paste a rent roll into ChatGPT/Claude **today**, would compliance/IT
    actually permit it? What's the written rule — or the unwritten one?
19. Who **owns that decision** — compliance, IT, legal, the deal team?
20. Would "the data physically never leaves your own laptop/network" change that answer?

## Section 6 — Scale & vocabulary

21. A typical chunk of portfolio you'd analyze at once: roughly how many **properties**?
    How many **units** per property? How much **history** (months / quarters / years)?
22. Rough sizes: a rent roll is about how many rows? A T-12 has about how many line
    items? (Ballpark is fine — I'm gauging how big these get.)
23. **Glossary check** (so I don't embarrass us on terminology): in your own words,
    define — NOI, DSCR, debt yield, cap rate, set-aside (40/60 vs 20/50), AMI, income
    certification / recertification, T-12. Correct me anywhere I'm using a term loosely.

---

### What happens next

From your answers I'll design (a) the list of questions the tool can answer instantly,
(b) the rule for what gets stripped before the AI sees anything, (c) what it remembers
across quarters, and (d) a realistic **synthetic** sample dataset for testing — built
from your *descriptions*, never your real files. I'll send the design back to you to
sanity-check before any of it gets built.

Thanks — this is the part I genuinely can't do without someone who's actually done the
job.
