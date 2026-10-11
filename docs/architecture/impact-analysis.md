# Impact analysis (Milestone 6)

Pure, deterministic code in `app/engines/impact`; the database layer in `app/services/impact.py` only loads inputs
and stores results. No LLM is involved.

## Inputs
The detected changes of a new revision (Milestone 4), the dependency graph (Milestone 5), the status of each
document and of the changed revision, and, for element-level links, the elements of each reachable document.

## Score
`score = 100 x dependency x change x propagation x status`, each factor between 0 and 1, then classified:
0 to 24 LOW, 25 to 49 MEDIUM, 50 to 74 HIGH, 75 to 100 CRITICAL. Every weight is in `ImpactConfig`, and a snapshot is
stored with each analysis. Every result stores all four factors with a sentence explaining each, plus the formula
with the numbers filled in, so the UI shows exactly why a score came out as it did.

| Factor | Meaning |
|---|---|
| dependency | The weakest relationship on the path (relationship type weight x confidence). A chain is as strong as its weakest link. |
| change | The strongest change, weighted by its severity, its type, and how relevant that kind of element is to the dependent's discipline (a door matters little to structure, a wall a lot), plus 0.03 per additional change, capped at 0.15. |
| propagation | 0.7 for every hop beyond the first (direct 1.0, two steps 0.7, three 0.49). |
| status | How consequential stale information is in the dependent document (issued 1.0, approved 0.95, in review 0.85, draft 0.7) times how official the changed revision is (issued/approved 1.0, in review 0.9, draft 0.8). |

Confidence is separate: the weakest relationship confidence x the confidence of the driving change x 0.9 per extra hop.

## Affected elements
For each reachable document with readable model data, four rules link its elements to the changed ones, strongest first:
counterpart (same class and tag), reference (the element lists the changed element in a `BasedOn` property, as the
quantity take-off does), proximity (plan outlines within 1000 mm after the change, from the body extent of the IFC
elements, or a rectangle from Length and Width), and same room. Large models (over 50 000 elements) skip this step
and say so. Elements with no body outline are treated as points.

## Open, reviewed, advisory
Events record what a revision could affect; whether each is still open is computed when read. An event is reviewed
when the first dependency on its path has been marked reviewed against the changed revision (or a later one). An
indirect impact follows its first hop. A path that starts with a two-way relationship cannot be reviewed and is
advisory. A newer revision of the changed document supersedes the older analysis, and earlier reviews do not carry
over. The analysis is recomputed when a comparison runs and whenever the dependency graph changes.

## Limitations
Weights are sensible defaults, not calibrated against real projects. Element proximity is plan-view only and ignores
height. Relationships between documents are those people registered; nothing is inferred.
