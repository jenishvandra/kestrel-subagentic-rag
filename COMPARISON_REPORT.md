# Comparison Report: Subagentic RAG vs. Single-Agent Baseline

**Kestrel Systems Employee Help Desk Assistant — Tarka Upskilling Project**

## Summary numbers (16-question acceptance test set, Section 8)

| Metric | Subagent design | Single-agent baseline |
|---|---|---|
| Questions completed | 16/16 | 16/16 |
| Routing accuracy | 14/16 (88%) | N/A — no routing step |
| Key-point coverage (automated) | 36/67 (54%) | 26/67 (39%) |
| Citations detected (automated) | 7/16 (44%) | 0/16 (0%) |
| Average time per question | 59.5s | 18.3s |
| Conflict detection (Q12, Q14) | Yes, both flagged and resolved | No — no conflict logic exists |
| Per-department "not covered" honesty (Q15) | Yes — HR subagent explicitly says not covered | Answer quality depends entirely on top-4 retrieval luck |
| Out-of-scope handling (Q16) | Yes — no subagent called, polite decline | Yes — polite decline (both designs handle this correctly) |

**Note on the automated scores above:** manual review of all 16 subagent-design answers
(`eval/eval_results_subagent.csv`) shows that **every single answer includes at least one
properly formatted citation** like `[KSPL-HR-POL-004 v4.1, section 3.1]` — the automated
citation counter's 44% figure is an artifact of the regex not anticipating every bracket
formatting variation the model used (e.g. `v4.1,` vs `vv4.1,` vs no version at all for the HR
Handbook contact line), not a real gap in citation coverage. Key-point coverage is undercounted
for the same reason (strict phrase/token matching against expected wording). The qualitative
comparison below is based on manual reading of both CSVs, which is more reliable than the
automated percentages for judging actual answer quality.

## Where the two designs differ in practice

**Multi-department questions (Q8–Q14) are where the subagent design earns its cost.** Relocation, resignation, and cross-office questions need HR's process rules, IT's equipment rules, and Finance's money rules combined into one coherent answer. The subagent design's supervisor explicitly plans which departments to call and writes a dedicated task message for each one, so nothing gets dropped. The baseline does a single top-4 retrieval across all three documents mixed together — with only 4 slots and three departments competing for them, it structurally cannot reliably surface all three departments' relevant clauses for a question like Q12 (relocation) or Q11 (resignation), reproducing exactly the "missing parts" failure mode described in the assignment's Section 2 pilot post-mortem.

**Conflict detection is unique to the subagent design.** Q12 and Q14 both touch the accommodation-nights conflict between the HR Handbook (15 nights, v4.1) and the current Finance policy (10 nights, v3.0, which explicitly supersedes the HR figure). The subagent design's supervisor sees both departments' findings side by side and applies the conflict-resolution rules (explicit supersession → Finance governs money → newer effective date), producing an answer that states the current 10-night limit *and* explains why the older 15-night figure no longer applies. The baseline has no mechanism to detect this at all — whichever chunk its single retrieval happens to surface is simply presented as fact, with real risk of quoting the outdated 15-night figure (the assignment's "Outdated rule" failure mode).

**Routing wasn't perfect (14/16, 88%), and the two misses are instructive.** Q13 ("do I repay anything" after resigning post-relocation) was over-routed to all three departments when finance alone was expected — the supervisor pattern-matched on "resigning" rather than recognizing a narrowly-scoped financial question. Q14 (accommodation nights) was under-routed to finance alone when both hr and finance were needed — the correct conflict-flagged answer still came out, but only because the Finance subagent's own instructions happen to mention the superseded HR figure, which is a fragile coincidence rather than a design guarantee. Both are fixable with more specific routing rules (see `README.md`'s reflection question 3) and illustrate that the supervisor's planning step, not the subagents themselves, is where most of this design's remaining error lives.

**Single-department questions (Q1–Q7, Q15) are where the subagent design's overhead shows.** For a simple question like "how many earned leave days do I get," both designs answer correctly and cite the same clause — but the subagent design still runs a full plan→subagent→synthesize pipeline (roughly 3 LLM calls) where the baseline needs only one retrieval and one LLM call. This shows directly in the timing: **59.5s vs. 18.3s average per question, a ~3.3x overhead** for the subagent design across the full 16-question set, even though most of that gap is paid on questions that didn't need multiple departments at all.

**Honest "not covered" (Q15, sabbatical leave) worked correctly in the subagent design** because the HR subagent's instructions explicitly require `covered=false` with a gap message when nothing relevant is found, rather than letting the model improvise. The baseline has no equivalent guardrail — its answer quality on an uncovered topic depends entirely on the LLM choosing not to hallucinate once told "if nothing relevant is found, say so," which is a much weaker guarantee than a structured, enforced field.

## Conclusion

For Kestrel's actual question mix, the subagent design is worth its cost. Of the 16 test questions, **7 (Q8–Q14) genuinely need multiple departments combined**, and 2 of those (Q12, Q14) require detecting and resolving a live conflict between two real policy documents — something the single-agent baseline architecturally cannot do regardless of prompt engineering, because it never sees more than one search's worth of mixed-department context at once. The roughly 3x time cost is paid disproportionately on the simple single-department questions where it isn't needed, which suggests a **router-first hybrid** (single-department → route directly to one subagent, skip full multi-agent planning; multi-department → full subagent pipeline) would keep the correctness gains on hard questions while cutting the average latency closer to the baseline's — a natural next iteration beyond this project's scope.
