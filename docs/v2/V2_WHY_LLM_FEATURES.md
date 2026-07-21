# Why LLM-derived features matter — and the conditions under which they do

A synthesis of the V2-03 investigation. Every claim here points to a committed artifact under
`reports/v2/llm_value/`. The purpose is to state precisely *where* an LLM adds value in this system,
*why*, and *where it does not* — so the portfolio claims match what the code actually measures.

## The one-sentence version

> An LLM adds value by turning messy real-world event signals into **typed, grounded, decision-usable
> structure**. That structure has **measured** value in grounding/routing/explanation, and
> **conditional** value in demand forecasting — it improves the forecast when (and only when) the
> event source it structures is dense, precisely timed, precisely located, and forward-looking.

## 1. What "an LLM feature" actually is here

The LLM never predicts demand, price, or profit numbers (V2 contract). Its job is upstream:

- **Extraction / structuring** — read free-text (news, announcements, permit descriptions) and emit a
  typed event record: type, time, location, severity, evidence spans, provenance.
- **Grounding / routing** — map a question to the typed tool / graph node that answers it, and refuse
  when nothing does.
- **Explanation** — narrate *why* a zone's forecast moved, citing the events behind it.

The numeric model then consumes those structured records. So an "LLM feature" is only ever as useful
as the *structure it recovers* and the *source it recovers it from*.

## 2. Where LLM features are MEASURED-valuable

### 2a. Grounding & routing (the decision Copilot) — V2-06

The clearest measured LLM win in the system. On the fixed 20-question benchmark, the real in-session
LLM router scores **routing/correctness/refusal = 1.0/1.0/1.0** vs a keyword baseline's
**0.75/0.83/0.63**, cutting **hallucinated answers 3 → 0**. On the GraphRAG side, retrieval-grounded
answering takes correctness from a no-retrieval floor to **40% → 100%** with hallucinations
**10/10 → 0**. Here the LLM does something a keyword system provably cannot: understand paraphrase and
intent, and *refuse* the out-of-scope question instead of returning a confident wrong number.
Artifacts: `reports/v2/copilot/{correctness,graphrag,ragas_generation}_benchmark.json`.

### 2b. Making the event layer possible at all

The forecast lift from events (below) requires events to *exist* as typed, time-stamped, located,
provenance-carrying records. That structuring — from any unstructured source — is the LLM's job. The
NYC permit feed happens to arrive pre-structured (so it needs no LLM), but any *unstructured*
forward-looking source (venue announcements, press releases, community notices) would depend on the
LLM to reach the same structure.

## 3. Where LLM features are CONDITIONALLY valuable (demand forecasting)

The event layer measurably improves the forecast — **when the event source meets four conditions.**

- **Measured, real data:** the structured event feed lifts WAPE **+2.69%** at nowcast (A1−A0, CI
  excludes 0) and nets **+$33k** in the ledger. (`incremental_value_borough.json`,
  `borough_event_lift.json`.)
- **Simulated ceiling:** with a disclosed, forward-looking, precise, dense synthetic event source, an
  LLM-structured signal + post-correction improves the forecast **+10.43%** on event cells
  (`claim_status: simulated`, `synthetic_ceiling.json`).

### The four conditions (why the source, not the model, decides)

Established by a density learning curve + a quality-degradation ablation
(`density_curve.json`, `quality_ablation.json`): the event source must be

1. **dense** — enough demand-relevant events (value is absent at news scale ≤100; news has ~19),
2. **precisely timed** — exact hour (day-level coarsening collapses the lift),
3. **precisely located** — exact borough/zone (citywide smearing collapses it),
4. **forward-looking** — known before the event (retrospective availability collapses it).

Degrade *any one* and the +2.69% vanishes. This is why the source matters more than feature cleverness.

## 4. Where LLM features do NOT help (and why) — the honest boundary

- **LLM-from-retrospective-news** adds no incremental demand accuracy on this data. Verified across
  seven approaches (raw / improved / permit-schema / importance-weight / signed / post-processing /
  horizon). Root cause: news satisfies **0–1 of 4** conditions (only 2/23 events forward-looking) and
  its effect is largely **redundant** with the autoregressive demand lags.
- **Imposing an LLM demand *prior*** (parade=+, film=−) hurt (−3.39%): the contract's "LLM does not
  compute demand" rule, confirmed empirically — the model should *learn* the response, not be told it.
- **Finer LLM structure than a count** (per-type buckets) hurt (−1.9%) as **representation dilution**,
  not lost information: the same signal in sparse columns is used less efficiently by a
  capacity-limited learner at this event density / spatial grain.

## 5. The division of labor that makes LLM features meaningful

| layer | who does it | evidence |
|---|---|---|
| Recover event **facts** from text (type/time/place/evidence) | **LLM** | powers §2b, §3 |
| Decide the event's **demand effect** | the numeric **model** (learned) | §4: imposed priors hurt |
| Ground a question to the right tool / refuse | **LLM** | §2a (measured 1.0 vs 0.75) |
| Explain *why* with provenance | **LLM** | §2a GraphRAG 40%→100% |

**LLM features are meaningful precisely when they stay on the "facts + grounding + explanation" side
of this line and feed a source that meets the four conditions.** They stop being meaningful when they
cross into guessing demand, or when the source is sparse/coarse/retrospective.

## 6. Realizing more of the value (what would extend it)

The synthetic ceiling (+10.43%) is the upper bound the LLM could reach on the demand side with the
right source. Reaching it for real needs an **unstructured *and* forward-looking** event source —
event calendars, venue/sports schedules, press releases — structured by the LLM into the A1 slot, at a
**fine spatial grain** (per-H3, where a specific event localizes). Both are recorded as untested
(`blocked_data`) here — the available NYC data is either pre-structured (permits, no LLM needed) or
retrospective (GDELT news), so this remains a documented opportunity, not a claim.
