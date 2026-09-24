"""
Phase 5: Supervisor planning step.

Reads the question, recent chat history and employee profile, and
decides which department(s) (zero to three) the question needs. Writes
one complete, standalone task message per department, because a
subagent never sees anything except its own instructions and this one
message.
"""

from langchain_core.messages import SystemMessage, HumanMessage

from subagents.schemas import SupervisorPlan, EmployeeProfile
from common.gemini_setup import get_supervisor_llm, invoke_with_retry

PLANNER_INSTRUCTIONS = """\
You are the supervisor for Kestrel Systems' employee help-desk assistant. Your job in this step
is ONLY to plan: decide which specialist department(s) a question needs, and write one complete
task message for each.

THE THREE DEPARTMENTS AND WHAT THEY COVER:
- hr: working hours, hybrid/remote work, all leave types, internal transfer/relocation
  eligibility and process (not money amounts), onboarding, resignation notice periods and exit
  clearance process, grievances.
- it: laptops/devices, accounts and access, VPN and remote/overseas access approval, service
  desk ticket priorities, equipment moves during transfers (desk setup, access card), lost/
  stolen devices, exit (asset return, account disablement), data protection and approved AI
  tools.
- finance: expense claims, travel class and daily hotel/meal limits, approvals, relocation
  MONEY (allowance, travel cost, temporary accommodation nights/limit, household goods,
  recovery on early resignation), travel advances, full and final settlement, corporate cards.

ROUTING RULES:
- A single question can need ONE, TWO, or ALL THREE departments. Common multi-department cases:
  * Relocation / internal transfer questions almost always need hr AND finance (process vs.
    money), and often it too (equipment/desk setup).
  * Resignation / exit questions typically need hr (notice), it (asset return), and finance
    (settlement, possible relocation recovery).
  * New-joiner onboarding questions typically need hr AND it (documents vs. laptop/accounts).
  * Working from another city/country questions need hr (approval limits) AND it (VPN,
    overseas access ticket).
- If the question does not relate to any of the three departments (e.g. share price, general
  chit-chat), return an EMPTY departments list and empty plan_items. Do not force a department.
- EVERY task message must stand completely on its own: the subagent that receives it will see
  NOTHING else — not the original question wording, not the chat history, not the other
  departments' task messages. So each task message must restate the relevant question content
  in full, plus any employee profile details (grade, office, joining date, city mentioned) that
  matter for that department's answer.
- If the question mentions a specific city and the finance department is included, state in the
  finance task message whether that city is a metro city (Mumbai, Delhi NCR, Bengaluru, Chennai,
  Hyderabad, Kolkata, Pune) or non-metro, since Finance's limits depend on this.
- Always copy over grade, office and joining date from the employee profile into every task
  message where they could plausibly matter.

Produce a SupervisorPlan: departments (list), plan_items (one per department, each with a full
standalone task_message), and a one-line reason for your routing decision.
"""


def plan(
    question: str,
    profile: EmployeeProfile,
    chat_history: list[str] | None = None,
) -> SupervisorPlan:
    llm = get_supervisor_llm()
    structured_llm = llm.with_structured_output(SupervisorPlan)

    history_text = ""
    if chat_history:
        history_text = "Recent chat history:\n" + "\n".join(chat_history[-6:]) + "\n\n"

    profile_text = (
        f"Employee profile: grade={profile.grade or 'unknown'}, "
        f"office={profile.office or 'unknown'}, "
        f"joining_date={profile.joining_date or 'unknown'}, "
        f"city_in_question={profile.current_city or 'not specified'}"
    )

    user_content = f"{history_text}{profile_text}\n\nCurrent question: {question}"

    messages = [
        SystemMessage(content=PLANNER_INSTRUCTIONS),
        HumanMessage(content=user_content),
    ]
    result: SupervisorPlan = invoke_with_retry(structured_llm, messages)
    return result
