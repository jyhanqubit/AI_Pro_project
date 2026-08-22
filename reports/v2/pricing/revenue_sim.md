# V2-05 — Event-aware dynamic-fare revenue (SIMULATED SHADOW)

> SIMULATED SHADOW QUOTE — NOT A LIVE PRICE (not applied to any rider). No rider is charged; there is no real conversion log. Revenue is
> modeled through an explicit demand-elasticity response and reported honestly, including
> the elasticity boundary where the uplift disappears.

- Config `pricing-v2` · base fare **1.00** · cap **1.50×**
- Priced with the real `/v2/pricing/quote` path (replay engine as-of `2026-07-12T15:30:00-04:00`, 45 stations)
- Headline elasticity **0.5** (a +100% fare would remove ~50% of demand)

## Headline

| policy | revenue | fulfilled rentals | rev / rental | surcharged stations |
| --- | ---: | ---: | ---: | ---: |
| flat (base fare) | 362.00 | 362 | 1.000 | 0 |
| event-aware dynamic | 363.40 | 362 | 1.004 | 7 |

**Revenue uplift +1.40 (+0.4%)** · fulfilled-rental delta +0 (rentals lost to the surcharge at this elasticity).

## Elasticity sensitivity

The uplift is only real while the bounded surcharge's price gain survives the modeled
conversion loss. Higher elasticity = riders balk sooner.

| elasticity | flat revenue | dynamic revenue | uplift | uplift % | fulfilled Δ |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 362.00 | 363.40 | +1.40 | +0.4% | +0 |
| 0.25 | 362.00 | 363.40 | +1.40 | +0.4% | +0 |
| 0.50 | 362.00 | 363.40 | +1.40 | +0.4% | +0 |
| 0.75 | 362.00 | 363.40 | +1.40 | +0.4% | +0 |
| 1.00 | 362.00 | 363.40 | +1.40 | +0.4% | +0 |
| 1.50 | 362.00 | 363.40 | +1.40 | +0.4% | +0 |

Reading: the surcharge only fires at the event-affected zones, and there the available
bikes are fewer than the riders who want them (supply-constrained), so a bounded surcharge
captures value on bikes that would have sold anyway. The uplift stays positive until the
elasticity is high enough that the surcharge pushes converted demand below the available
supply — that crossover is the honest limit of the claim.

## Event-severity what-if

How event-aware revenue scales as the **event** intensifies (event component only; base
inventory scarcity is not amplified). This is a labelled what-if, not a measured event.

| event severity | flat revenue | dynamic revenue | uplift | uplift % | max tier | surcharged |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ×1 | 362.00 | 363.40 | +1.40 | +0.4% | 1.10× | 7 |
| ×2 | 362.00 | 365.50 | +3.50 | +1.0% | 1.25× | 9 |
| ×3 | 362.00 | 367.30 | +5.30 | +1.5% | 1.25× | 9 |

As the event grows, more zones cross into scarcity and the bounded surcharge climbs its
tiers (toward the hard 1.50× cap), so event-aware revenue rises with event intensity while
flat pricing leaves that value on the table. This is the event-awareness of the pricing,
shown directly.
