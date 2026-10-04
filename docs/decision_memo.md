# Decision memo — ai-analyst-workflow (2026-10-04)

**Decision:** ship the LLM-eval repo with a **dated generation receipt** and make validation — not generation — the product. One prompt → guardrailed execution → result-fingerprint comparison against a hand-written golden set, every failure catalogued, a sample audited by hand from raw rows.

**Why this shape.** The hiring claim behind this repo is "I can use AI tools *and* judge their output". A demo that only shows generation proves the first half. The deliverable therefore spends its complexity on the trust boundary: parse-based SELECT-only guardrails (sqlglot), read-only execution with a watchdog and row cap, one shared result serializer for golden and candidate comparison, and a mismatch taxonomy (`sql_error · guardrail_reject · timeout · wrong_row_count · value_mismatch`). Golden SQL is hand-written — the moment the model writes the reference, the eval measures self-consistency.

**Key calls made during the build:**

1. **Fingerprints over SQL diffs.** The result is what an analyst consumes; SQL text can be wrong in a thousand spellings and right in a thousand others. Row count + sha256 over canonically ordered rows (2 dp numbers) is order-sensitive on purpose and dialect-agnostic.
2. **Deliberate traps are half the eval.** 6 of 32 questions encode real data hazards (non-unique `block`, `flat_model`/`flat_type` near-miss, gapped-series windows, lease-text months, deliberate ambiguity). They measure the failure mode that slips past code review.
3. **A dated receipt, not fake reproducibility.** Free-tier generation is not byte-reproducible and is capped (20 requests/day/model), so the run's model ids + date live inside `outputs/summary.json`, re-runs write `outputs/reruns/<date>/`, and only the deterministic half is byte-gated. The as-of run spans three sibling free-tier model ids because of that quota wall; the alternative was no receipt at all. This is disclosed in the README, `docs/model_note.md` and the per-question `model` field of `candidates.jsonl`.
4. **Failures lead.** The README answers with 27/32 first try **and** the five failures first: all value-level, all plausible-looking, retries rescued none, 3 of 6 traps caught the model. The durable output is the failure taxonomy and its fixes, not the pass rate.

**What this changes next iteration:** spell contract details in the questions themselves (rounding order, label types — 2 of 5 failures were contract slips), put window-frame semantics in the prompt contract, and route ambiguous questions to a question-rewrite track instead of counting them against the model. A single-model re-run on `gemini-3.7-flash` is one command when its quota resets, if model purity ever matters more than the workflow receipt.

**What we are not claiming:** no benchmark, no model ranking, no fine-tuning, no causal or predictive story. Adjacent work (BIRD/Spider model research; generic eval harnesses such as `jmpei/nl2sql-agents`) is named in the README as adjacent, not as inferior prior art.
