# Statistical Verification — Weekday vs Weekend Demand

Data: `JC-202606-citibike-tripdata.csv.zip` (June 2026, 109,510 valid trips). 31 days:
22 weekdays, 9 weekend days. Significance level α = 0.05. Two-sided tests.

> **Method note.** Daily demand is right-skewed and non-normal (Shapiro–Wilk p < 0.001 for
> both groups), so the **Mann–Whitney U** rank test is the primary test; Welch's t-test is
> reported alongside for reference. Effect size is Cohen's d. Caveats: only 9 weekend days,
> and consecutive days are autocorrelated, so daily observations are not fully independent —
> results are indicative, not a controlled experiment.

## Headline: the difference is in **timing and composition**, not total volume

| Test | Weekday | Weekend | Mann–Whitney p | Welch p | Cohen's d | Verdict |
|---|---|---|---|---|---|---|
| **1. Daily total departures** | 3,722 | 3,069 | **0.019** | 0.147 | 0.88 (large) | Weak/borderline |
| **2. Evening-rush (17h) departures** | 391.8 | 232.8 | **0.00057** | 1.0e-5 | 2.20 (very large) | **Strong** |
| **3. Member share of trips** | 75.6% | 65.0% | **0.00014** | 1.6e-5 | 2.72 (very large) | **Strong** |

### Interpretation

- **Total daily volume barely differs.** By the valid (non-parametric) test it is marginally
  significant (p = 0.019) and by Welch's t-test it is *not* significant (p = 0.147). Weekends
  are still busy — leisure demand roughly compensates for lost commuting. So "weekday vs
  weekend" as a **level** shift is a weak signal.
- **The evening rush is where they diverge sharply.** Weekday 17:00 departures average 68%
  higher than weekend, with a very large effect (d = 2.20, p ≈ 1e-5). The regime difference is
  about **when** people ride, not how much in total — which is exactly why hour-of-day and
  same-hour-last-week features matter more than a raw weekend flag.
- **Composition differs even more than timing.** Member share is 75.6% on weekdays vs 65.0% on
  weekends (d = 2.72, the largest effect measured). Members = commuters; casual riders = leisure.
  This **statistically justifies adding `member_casual`** as a feature (implemented, see below).

## Supporting tests

**4. Day-of-week effect (Kruskal–Wallis across 7 groups).** H = 15.45, p = 0.017 → daily demand
differs by day of week (reject equal-medians). Supports the day-of-week / weekly-lag features.

**5. `rideable_type` × period independence (chi-square).** electric/classic counts for
rush (07,08,17,18h) vs off-peak: χ² = 0.47, p = 0.495 → **not significant**. The electric/classic
mix does not differ between rush and off-peak once AM and PM are pooled (the earlier hourly dip
is specifically a morning effect). Takeaway: `rideable_type` is a weak signal for the commute
distinction and is **deprioritized** relative to `member_casual`.

## Conclusions for feature engineering

1. A plain weekday/weekend **level** flag is weak; keep it, but rely more on **hour-of-day**,
   **rush flags**, and **same-hour-last-week lag** (which encode the timing difference that *is*
   significant).
2. **`member_casual` is strongly justified** (d = 2.72) → added as leakage-safe lagged features.
3. Day-of-week matters (p = 0.017) → weekly lag and day-of-week features retained.
4. `rideable_type` is not justified for the rush distinction → not added now.
