"""V2-06 GraphRAG Decision Copilot — typed tools + router + benchmark.

The Copilot answers operator questions by routing to a **typed tool** that returns a grounded,
provenance-carrying result read from a committed V2 artifact (or the event graph). A numeric answer
is emitted ONLY when a typed tool produced it; otherwise the Copilot refuses. This enforces the V2
rule "a numeric Copilot answer is rejected if there is no typed tool result behind it."
"""
