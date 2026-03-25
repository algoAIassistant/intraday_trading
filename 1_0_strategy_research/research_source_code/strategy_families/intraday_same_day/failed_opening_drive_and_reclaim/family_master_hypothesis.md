# Family Hypothesis: failed_opening_drive_and_reclaim

---

## Core behavioral thesis

When a stock makes a clear directional drive early in the session and that drive fails — defined as price reversing back through a structurally significant intraday level — the subsequent behavior is not random. The failure creates an imbalance: trapped participants on the wrong side of the move, and a potential vacuum in the direction of the reclaim. This imbalance, when measurable, may produce a repeatable same-day directional edge.

The thesis is not that this pattern always works. It is that the failure-and-reclaim sequence conditions the distribution of intraday returns in a measurable way — and that some version of that conditioned behavior can be isolated, tested, and potentially formalized.

---

## Expected edge logic

- Stocks that fail an early drive and reclaim a key level tend to follow through in the reclaim direction more than chance would predict.
- The strength of the follow-through may be conditioned by: volume at the failure point, relative size of the initial drive, proximity to a structural level (VWAP, opening range), and broader market context.
- The edge, if it exists, is likely strongest within a bounded intraday time window — not at any arbitrary point in the session.

---

## What evidence would support the thesis

- Phase_r0 shows that same-day return distributions are non-uniform around opening drive sequences — some segment of stocks shows skewed intraday behavior.
- Phase_r1 shows that the failure-and-reclaim condition measurably shifts the return distribution relative to the unconditional baseline.
- Phase_r2 shows that the shift is stable across multiple years, is not concentrated in a single year or market regime, and holds across multiple stock buckets (cap tier, volume tier).
- Phase_r3 produces a formalized rule set with positive expectancy that does not depend on overfitted parameters.
- Phase_r4 shows that the edge survives realistic slippage assumptions and out-of-sample testing.

---

## What evidence would weaken or kill the thesis

- Phase_r0 shows no non-uniformity in same-day return distributions around opening drive sequences — the behavior is indistinguishable from random.
- Phase_r1 shows that the failure-and-reclaim condition adds no measurable lift over the unconditional baseline.
- Phase_r2 shows that any apparent edge is concentrated in a single year, a single bucket, or a single market regime — not structurally stable.
- Phase_r3 cannot produce a rule set with positive expectancy without data-mining parameters.
- Phase_r4 shows that the edge disappears under realistic slippage or in out-of-sample periods.

Any one of these outcomes at the appropriate phase is sufficient to close the branch as `closed_no_survivor`.
