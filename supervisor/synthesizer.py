"""
Phase 7: Combine subagent findings into one final cited answer, detect
and resolve conflicts between documents, and report gaps.
"""

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from subagents.schemas import SubagentResult
from common.gemini_setup import get_supervisor_llm, invoke_with_retry

SYNTHESIS_INSTRUCTIONS = """\
You are the supervisor for Kestrel Systems' employee help-desk assistant, writing the FINAL
answer from the findings your specialist subagents already returned.

RULES YOU MUST FOLLOW:
1. CITE EVERY RULE. Every fact, number, deadline or step in your answer must end with a
   citation in the form [DOC_ID, section X.Y]. Example: "...within 45 days of the last working
   day [KSPL-FIN-POL-003, section 8.1]."
2. USE ONLY THE FINDINGS PROVIDED. Do not add any number, name, deadline or rule that does not
   appear in the findings below. If the findings don't cover something, say so in a gap instead
   of guessing.
3. SHOW CALCULATIONS. If a subagent's finding already shows a calculation (e.g. a non-metro
   hotel limit), carry it through into your answer exactly as computed. Do not silently redo or
   alter the arithmetic.
4. DETECT CONFLICTS. If two findings (usually from different departments/documents) cover the
   SAME topic but give DIFFERENT values or rules, this is a conflict. Resolve it in this exact
   order:
     a) A clause that explicitly states it replaces/supersedes an earlier limit wins.
     b) Otherwise, the Finance policy prevails on financial benefits (per HR Handbook 1.3 /
        Finance 1.3, Finance governs money matters).
     c) Otherwise, the document with the NEWER effective_date wins.
     d) If still unclear, present BOTH values and tell the employee to confirm with HR.
   When you resolve a conflict, add a short "Conflict note" to your answer: name both documents,
   state both values, say which one applies and why.
5. REPORT GAPS. If any subagent reported covered=false or listed gaps, or if a needed department
   was skipped/failed, list what could not be answered. Where helpful, point the employee to HR
   Business Partner / hr-help@kestrel.example (HR Handbook 7.4) or the relevant service desk.
6. If NO subagent found anything relevant (all covered=false, no findings), clearly state the
   topic is not covered by Kestrel policy, and suggest the HR Business Partner as the contact.
   Do not invent a policy that doesn't exist.
7. Write in plain, friendly, direct language for an employee — not a legal document. Keep
   citations inline but keep prose readable.

Produce a SynthesisResult with: answer (the full final answer text with inline citations),
conflict_detected (true/false), conflict_note (empty string if none), gaps (list of strings).
"""


class SynthesisResult(BaseModel):
    answer: str = Field(..., description="The final answer text, with inline citations.")
    conflict_detected: bool = False
    conflict_note: str = ""
    gaps: list[str] = Field(default_factory=list)


def _format_findings(results: list[SubagentResult]) -> str:
    blocks = []
    for r in results:
        blocks.append(f"### Department: {r.department} | covered: {r.covered}")
        for f in r.findings:
            blocks.append(
                f"- RULE: {f.rule}\n"
                f"  SECTION: {f.section} | PAGE: {f.page} | DOC: {f.doc_id} "
                f"v{f.version} | EFFECTIVE: {f.effective_date}"
            )
        for g in r.gaps:
            blocks.append(f"- GAP: {g}")
        blocks.append("")
    return "\n".join(blocks) if blocks else "(no subagents ran / no findings)"


def synthesize(
    question: str,
    subagent_results: list[SubagentResult],
    failed_departments: list[str] | None = None,
) -> SynthesisResult:
    llm = get_supervisor_llm()
    structured_llm = llm.with_structured_output(SynthesisResult)

    findings_text = _format_findings(subagent_results)
    failed_text = ""
    if failed_departments:
        failed_text = (
            f"\nNOTE: these departments could not be checked (timeout/error): "
            f"{', '.join(failed_departments)}. Mention this as a gap.\n"
        )

    user_content = (
        f"Employee question: {question}\n\n"
        f"Findings from subagents:\n{findings_text}\n{failed_text}"
    )

    messages = [
        SystemMessage(content=SYNTHESIS_INSTRUCTIONS),
        HumanMessage(content=user_content),
    ]
    result: SynthesisResult = invoke_with_retry(structured_llm, messages)
    return result


def out_of_scope_reply() -> SynthesisResult:
    return SynthesisResult(
        answer=(
            "That doesn't look like something covered by Kestrel's HR, IT, or Travel/Expense "
            "policies. I can help with questions about leave, hybrid work, VPN and IT support, "
            "expense claims, travel, or relocation. Could you rephrase your question around one "
            "of those topics?"
        ),
        conflict_detected=False,
        conflict_note="",
        gaps=["Question is outside the scope of HR, IT and Finance policy documents."],
    )
