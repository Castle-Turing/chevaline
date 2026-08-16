# Evaluating the design process

This project spends real effort on process — a standards ledger with a
discovery obligation, an RFC workflow, structured reviewer questions, a
packet generator. That effort has to justify itself against the null
hypothesis that it is elaborate theatre producing little a cheap prompt
would not.

This document holds the criteria and the evidence. It is deliberately
willing to conclude that parts of the process should be deleted.

## Criteria

1. **RFC revision rate before acceptance.** If a meaningful fraction of
   RFCs are rejected or materially rewritten by evidence before landing in
   `SPEC.md`, the process prevented that many bad commitments. If they all
   land as written, it added ceremony to conclusions already reached. This
   is the single most decisive number and it is cheap to track.
2. **Lift over the null model.** What a plain "what is wrong with this?"
   prompt finds, versus what the structured process finds, on the same
   input. See the experiment below.
3. **Cost per surviving defect**, in tokens, counting only defects that
   held up under scrutiny.
4. **Reviewer disagreement variance.** If structured questions produce more
   divergence than generic prompts, the anti-sycophancy framing is doing
   something. If less, it is manufacturing consensus.
5. **Disposition distribution.** `docs/rfcs/README.md` predicts `deferred`
   should dominate sweeps. A sweep that adopts everything is
   rubber-stamping. That prediction is falsifiable.

## Defect taxonomy, organised by detector

The first version of this taxonomy sorted defects by *kind*. That was the
wrong axis. What matters operationally is **what is minimally required to
find it**, because each class has a different cheapest detector — and using
the wrong one is how effort gets wasted.

| Class | Definition | Cheapest detector |
|---|---|---|
| **A — document-internal** | Contradictions between sections, unsatisfiable requirements, undefined defaults, framework grafted where it does not fit | An unstructured model read of the whole document |
| **B — requires external knowledge** | Duplicated prior art, false factual claims, ignorance of deployment reality | Discovery search and claim verification |
| **C — requires execution** | Fail-open behaviour visible only on real data, guarantees no implementer can meet | A resolver, an adapter, a real profile |

Chevaline's known defects sort cleanly into these, and — importantly —
**no detector finds another class's defects.** Matching detector to class
is the whole game.

## Experiment 1 — null model versus the process (2026-08-16)

**Setup.** `SPEC.md` at commit `4e3f54e` (v0.2, before any RFC annotated
it — verified to contain zero references to RFCs or known defects) was
given to a fresh model with no context and one unstructured prompt: *"tell
me what's wrong with it."* Ground truth was the set of defects latent in
that version that this project later found by other means.

**Cost.** One prompt, one tool call, ~32k tokens.

**Result: eight defects, of which seven were new** — never found by the
RFC process, the reviews, the ledger, or the resolver. Overlap with our
prior findings was approximately one.

The seven new ones:

1. `compose` is grafted onto `[sessions]` without checking it still means
   anything: `layer` ("project gates still run; this one runs too") is
   incoherent for a mutually-exclusive enum, and §3.8 calls `defer` "the
   sensible default here" while §2.2 says `layer` is the default
   everywhere — leaving the actual fallback undefined.
2. `[harnesses]`, `[models]`, and `[[extensions]]` are omitted from the
   composition discussion entirely — no `compose` key, no rationale, no
   deferral. A project could plausibly require a harness or forbid a model
   family. **The originating design brief explicitly warned about this
   class**, and the spec silently dropped it anyway.
3. Authority's "stricter of the two axes, always" is a fourth composition
   mode smuggled in unnamed, contradicting §2.2's claim that authority is
   axis-2-only because axis 1 "has no standing to have an opinion."
4. §4.1's mandatory `tokens` enforcement is a hard MUST that a pure
   config-rendering adapter — the kind §4 describes — cannot satisfy, with
   no carve-out and no statement that such adapters are non-conformant.
5. **TOML does not guarantee table declaration order.** Environment
   resolution depends entirely on it. *Verified against the TOML
   specification, which maps documents to hash tables and guarantees no
   ordering.* Our own resolver works only because Python dicts happen to
   preserve insertion order — an implementation detail, not a guarantee.
6. §4's marker-comment requirement is impossible in JSON, and Claude
   Code's `settings.json` — this project's named first adapter target — is
   JSON.
7. "Halt before the next model call" overstates what provider-reported
   usage permits: usage is known only after a call completes, so the call
   that crosses the threshold always runs uncapped.

**What the null model did not find:** the Agent Skills duplication
(needs search), the false tier prior-art claim (needs verification), the
cross-harness aggregation hole (needs deployment reasoning), the
array-replacement fail-open (needs execution). Classes B and C.

### Interpretation

The overlap between the two approaches is near zero, and the split is
principled rather than random. **Every one of the null model's eight
findings is Class A.** Every one of the process's findings is Class B or C.
This is consistent with the published finding that model reviewers
emphasise internal consistency and technical detail over novelty and
framing — they are extremely good at exactly the thing we were not using
them for.

The uncomfortable conclusion: an elaborate process was built and pointed at
Class A, where it is the worst available tool, while Class A went otherwise
unexamined for a day.

### Actions taken

- **Adopt the null-model read as a standing gate.** Run an unstructured
  "what is wrong with this?" pass against the full spec at every version
  bump, before any structured review. Highest yield per token observed by a
  wide margin, and it costs less than writing one RFC.
- **Narrow the RFC process's claim.** It is not a finder of internal
  contradictions and should stop being justified as one. Its remaining
  claim — preventing premature normativity and organising external evidence
  — is narrower and still unproven. Criterion 1 will settle it.

### Limitations

n=1, one model, one prompt, one document. Not rigorous. The effect size
(seven new findings against roughly one overlap) is large enough not to be
noise, but a second run with a different model would strengthen it, and the
null model's own findings each need verification before being treated as
defects — claim 5 was verified here, claim 6 is self-evident, the rest are
argued from the document and look sound but are unchecked.

## Proposed Experiment 2 — defect injection

Inject a single known defect of each class into a clean spec and measure
detection rate by detector. Cleaner ground truth than backtesting against
famously-regretted standards decisions, which is contaminated: models know
how those turned out, so it would measure recall of history rather than
review quality.

The second baseline worth running is a **six-item checklist** derived from
the taxonomy above. If a checklist matches the full process at a fraction
of the cost, the honest conclusion is to keep the checklist and delete the
process.
