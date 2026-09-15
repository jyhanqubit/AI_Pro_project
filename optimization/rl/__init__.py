"""Research Mode — learned rebalancing control.

RL is research-only per ``CLAUDE_V2_APPEND_REVISED.md`` ("RL and QAOA are research-only and are
NOT V2 completion conditions"). This package trains a tabular policy over the *existing* V2-04
simulator (``optimization.mpc``) and scores it on the same V2-02 ledger as the mandatory policies,
so the learned policy is directly comparable to No-Action / Greedy / MILP / MPC / Oracle.

Nothing here may reach a product surface: outputs are labeled ``mode=research`` /
``claim_status=research`` and the ``ResultEnvelope`` validator blocks research values from
demo/replay/live views. No online learning or bandits (also prohibited) — training is a fully
offline, seeded simulation.
"""
