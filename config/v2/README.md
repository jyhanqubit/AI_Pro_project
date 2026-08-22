# config/v2/ — V2 configuration

Versioned, typed configuration for the V2 phases. Values are populated by their owning phase;
economic figures carry `claim_status: assumption` (see `docs/v2/V2_PROFIT_REGRET_LEDGER.md`).

Planned files:

- `assumptions.yaml`   — versioned assumption set: margin, shortage externality, overflow
                         penalty, distance cost, elasticity (V2-02, V2-05).
- `holdout.yaml`       — rolling H3 holdout windows + seed (V2-01).
- `guardrails.yaml`    — pricing bounds and guardrail thresholds G1–G5 (V2-05).
- `policies.yaml`      — MPC horizon + policy search space (V2-04).

Search spaces and runtime settings belong here (typed config / YAML), never hidden in notebooks.
