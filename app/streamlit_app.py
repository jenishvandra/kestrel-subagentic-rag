"""
Phase 8: Streamlit chat UI.

Run with:  streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path

# Allow running as `streamlit run app/streamlit_app.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from subagents.schemas import EmployeeProfile
from graph.workflow import run_query

st.set_page_config(page_title="Kestrel Help Desk Assistant", page_icon="🦅", layout="wide")

# ---------------------------------------------------------------- state --

if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role", "content", "trace"}

# ---------------------------------------------------------------- sidebar --

with st.sidebar:
    st.header("Employee profile")
    name = st.text_input("Name", value="Employee")
    grade = st.selectbox("Grade", ["G1", "G2", "G3", "G4", "G5", "G6", "G7"], index=3)
    office = st.selectbox("Office", ["Pune", "Mumbai", "Bengaluru"])
    joining_date = st.date_input("Joining date")
    current_city = st.text_input("City mentioned in your question (optional)", value="")

    st.divider()
    st.caption(
        "This assistant answers from Kestrel's HR, IT and Travel/Expense/Relocation "
        "policy documents only. It is not a substitute for HR/IT/Finance advice."
    )
    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()

profile = EmployeeProfile(
    name=name,
    grade=grade,
    office=office,
    joining_date=str(joining_date),
    current_city=current_city or None,
)

# ---------------------------------------------------------------- header --

st.title("🦅 Kestrel Employee Help Desk Assistant")
st.caption("Ask about HR, IT, or Travel/Expense/Relocation policy. Every answer is cited.")

# ---------------------------------------------------------------- trace renderer --

def render_trace(trace: dict):
    with st.expander("🔍 Behind this answer", expanded=False):
        st.markdown(f"**Departments chosen:** {', '.join(trace['departments']) or 'none'}")
        st.markdown(f"**Supervisor's reason:** {trace['reason']}")

        if trace.get("conflict_detected"):
            st.warning(f"⚠️ Conflict detected: {trace['conflict_note']}")

        if trace.get("task_messages"):
            st.markdown("**Task messages sent to subagents:**")
            for dept, msg in trace["task_messages"].items():
                st.markdown(f"- *{dept}*: {msg}")

        if trace.get("findings"):
            st.markdown("**Findings per subagent:**")
            for f in trace["findings"]:
                st.markdown(f"**{f['department']}** — covered: {f['covered']}")
                for item in f["findings"]:
                    st.markdown(
                        f"  - {item['rule']} "
                        f"`[{item['doc_id']}, §{item['section']}, p.{item['page']}, "
                        f"v{item['version']}, eff. {item['effective_date']}]`"
                    )
                for gap in f["gaps"]:
                    st.markdown(f"  - _gap: {gap}_")

        if trace.get("gaps"):
            st.markdown("**Overall gaps:**")
            for g in trace["gaps"]:
                st.markdown(f"- {g}")

        if trace.get("timings"):
            st.markdown("**Timing per subagent:**")
            for t in trace["timings"]:
                status = "✅" if t["ok"] else "❌ failed"
                st.markdown(f"- {t['department']}: {t['seconds']:.2f}s {status}")

        st.markdown(f"**Total time:** {trace['total_seconds']:.2f}s")
        st.markdown(f"**Total tokens:** {trace.get('total_tokens', 0)}")
        st.markdown(f"**Estimated cost:** ${trace.get('estimated_cost', 0):.4f} (rough estimate)")


# ---------------------------------------------------------------- chat history --

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("trace"):
            render_trace(msg["trace"])

# ---------------------------------------------------------------- input --

question = st.chat_input("Ask a question, e.g. 'My VPN keeps disconnecting, what should I do?'")

if question:
    st.session_state.messages.append({"role": "user", "content": question, "trace": None})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Checking policy documents..."):
            history_strs = [m["content"] for m in st.session_state.messages[-8:-1]]
            result = run_query(question, profile, chat_history=history_strs)

        final = result["final"]
        answer_text = final.answer
        if final.conflict_detected:
            answer_text = "🔶 **Conflict detected between documents** — see details below.\n\n" + answer_text

        st.markdown(answer_text)

        trace = {
            "departments": result["plan"].departments,
            "reason": result["plan"].reason,
            "task_messages": {
                item.department: item.task_message for item in result["plan"].plan_items
            },
            "findings": [
                {
                    "department": f.department,
                    "covered": f.covered,
                    "findings": [
                        {
                            "rule": item.rule,
                            "section": item.section,
                            "page": item.page,
                            "doc_id": item.doc_id,
                            "version": item.version,
                            "effective_date": item.effective_date,
                        }
                        for item in f.findings
                    ],
                    "gaps": f.gaps,
                }
                for f in result["findings"]
            ],
            "gaps": final.gaps,
            "conflict_detected": final.conflict_detected,
            "conflict_note": final.conflict_note,
            "timings": result["timings"],
            "total_seconds": result["total_seconds"],
            "estimated_cost": result.get("estimated_cost", 0),
            "total_tokens": result.get("total_tokens", 0),
        }
        render_trace(trace)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer_text, "trace": trace}
    )
