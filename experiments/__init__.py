"""Agent experiments (interview evidence): MCP token accounting, SHAP explanations, retrain gate.

Everything here is additive. Nothing in ``experiments/`` changes a served model, a committed
metric or an existing endpoint; the modules read the same artifacts and fixtures the API serves
and write their own outputs under ``reports/agent_experiments/``.
"""
