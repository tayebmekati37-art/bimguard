# ADR-004: Deterministic impact analysis instead of LLM reasoning

**Status:** accepted

**Context.** Engineers need to trust a "what changed and what could it affect" answer, and need to be able to
audit it. LLMs can be fluent but may state a dependency or a number that is not in the data.

**Decision.** Change detection, dependency traversal, impact scoring and release validation are plain, tested
code driven by stored data and visible configuration. Every result records the inputs and thresholds that produced
it. The AI layer (Milestone 9) receives only structured engine output and may only explain it; it cannot add or
remove findings, and the product works with AI disabled.

**Consequences.** Results are reproducible and testable, and wrong answers can be traced to a rule or a
threshold. The cost is that new kinds of checks need code or rule configuration rather than a prompt.
