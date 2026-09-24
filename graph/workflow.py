"""
Phase 6: LangGraph workflow that connects planning -> parallel subagents
-> synthesis, using the Send API for true fan-out (all chosen subagents
run concurrently, not one after another).
"""

import time
import operator
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.constants import Send

from subagents.schemas import SupervisorPlan, SubagentResult, EmployeeProfile
from subagents.hr_agent import get_hr_subagent
from subagents.it_agent import get_it_subagent
from subagents.finance_agent import get_finance_subagent
from supervisor.planner import plan as run_planner
from supervisor.synthesizer import synthesize, out_of_scope_reply, SynthesisResult

SUBAGENT_TIMEOUT_SECONDS = 30

SUBAGENT_FACTORIES = {
    "hr": get_hr_subagent,
    "it": get_it_subagent,
    "finance": get_finance_subagent,
}


class SubagentTiming(TypedDict):
    department: str
    seconds: float
    ok: bool


class GraphState(TypedDict):
    question: str
    profile: EmployeeProfile
    chat_history: list[str]

    plan: SupervisorPlan
    findings: Annotated[list[SubagentResult], operator.add]
    timings: Annotated[list[SubagentTiming], operator.add]
    failed_departments: Annotated[list[str], operator.add]

    final: SynthesisResult
    total_seconds: float
    total_tokens: int
    estimated_cost: float


class SubagentTaskState(TypedDict):
    department: str
    task_message: str


# ---------------------------------------------------------------- nodes --

def plan_node(state: GraphState) -> dict:
    result = run_planner(state["question"], state["profile"], state.get("chat_history"))
    return {"plan": result}


def route_to_subagents(state: GraphState):
    """Conditional edge: fan out one Send per department in the plan, or
    go straight to the out-of-scope path if the plan is empty."""
    plan: SupervisorPlan = state["plan"]
    if not plan.departments:
        return "out_of_scope"
    return [
        Send("run_subagent", {"department": item.department, "task_message": item.task_message})
        for item in plan.plan_items
    ]


def run_subagent_node(state: SubagentTaskState) -> dict:
    """Runs exactly one subagent. Invoked once per Send fan-out branch,
    so multiple instances of this node execute in parallel."""
    department = state["department"]
    task_message = state["task_message"]
    factory = SUBAGENT_FACTORIES[department]

    start = time.time()
    try:
        # NOTE: a real deployment would run this in a worker with a hard
        # timeout (e.g. via concurrent.futures with a future.result(timeout=...)).
        # Shown here for clarity; wrap in ThreadPoolExecutor if you need a
        # true wall-clock cutoff independent of the underlying HTTP client.
        subagent_fn = factory()
        result: SubagentResult = subagent_fn(task_message)
        elapsed = time.time() - start
        return {
            "findings": [result],
            "timings": [{"department": department, "seconds": elapsed, "ok": True}],
        }
    except Exception as exc:
        elapsed = time.time() - start
        return {
            "findings": [],
            "timings": [{"department": department, "seconds": elapsed, "ok": False}],
            "failed_departments": [department],
        }


def synthesis_node(state: GraphState) -> dict:
    result = synthesize(
        state["question"],
        state["findings"],
        failed_departments=state.get("failed_departments") or None,
    )
    return {"final": result}


def out_of_scope_node(state: GraphState) -> dict:
    return {"final": out_of_scope_reply()}


# ---------------------------------------------------------------- build --

def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("plan", plan_node)
    graph.add_node("run_subagent", run_subagent_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("out_of_scope", out_of_scope_node)

    graph.set_entry_point("plan")
    graph.add_conditional_edges(
        "plan",
        route_to_subagents,
        ["run_subagent", "out_of_scope"],
    )
    graph.add_edge("run_subagent", "synthesis")
    graph.add_edge("synthesis", END)
    graph.add_edge("out_of_scope", END)

    return graph.compile()


# NOTE: Gemini responses expose per-call token counts via
# `response.usage_metadata` (input_tokens/output_tokens/total_tokens), but
# there is no drop-in "sum every call automatically" callback like OpenAI's
# get_openai_callback. Token/cost totals are left at 0 here; if you need
# exact accounting, capture `.usage_metadata` from each LLM response inside
# subagents/builder.py and supervisor/*.py and accumulate it into the state.
def run_query(question: str, profile: EmployeeProfile, chat_history: list[str] | None = None) -> GraphState:
    app = build_graph()
    start = time.time()
    result = app.invoke(
        {
            "question": question,
            "profile": profile,
            "chat_history": chat_history or [],
            "findings": [],
            "timings": [],
            "failed_departments": [],
        }
    )
    result["total_tokens"] = 0
    result["estimated_cost"] = 0.0
    result["total_seconds"] = time.time() - start
    return result


if __name__ == "__main__":
    profile = EmployeeProfile(grade="G5", office="Pune", joining_date="2024-01-15")
    out = run_query(
        "I'm moving from Pune to the Mumbai office next month. What do I get and what must I do?",
        profile,
    )
    print("Departments chosen:", out["plan"].departments)
    print("Timings:", out["timings"])
    print("Failed:", out["failed_departments"])
    print("\n--- FINAL ANSWER ---\n")
    print(out["final"].answer)
    if out["final"].conflict_detected:
        print("\nCONFLICT:", out["final"].conflict_note)
    if out["final"].gaps:
        print("\nGAPS:", out["final"].gaps)
    print(f"\nTotal time: {out['total_seconds']:.2f}s")
