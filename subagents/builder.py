"""
Shared subagent builder (Phase 3, generalized in Phase 4).

Each subagent = (narrow instructions) + (a search over its own Chroma
collection only) + (fixed structured output: SubagentResult).

A subagent NEVER sees the chat history or other subagents' findings —
only its own instructions and the single task_message it is given. This
is what keeps each department's context clean (the whole point of the
subagent pattern over a single shared-collection RAG app).

DESIGN NOTE — single retrieval call instead of an agentic tool loop:
The assignment describes a subagent that may call its search tool
multiple times with different wording. We instead do ONE direct
retrieval (using the supervisor's task_message as the query) followed
by ONE structured-output LLM call. This is a deliberate trade-off for
free-tier API quotas: an agentic tool-calling loop can burn 3-4 LLM
calls per subagent (one per tool-call round plus the forced final
answer), and Gemini's free tier can be as low as ~20 requests/day on
some models. Collapsing each subagent to a single LLM call keeps a
16-question, 3-department evaluation feasible on a free API key. Since
the supervisor already writes a complete, detailed task message per
department (Phase 5), and each department's collection is small (~31
chunks), a single top-K retrieval reliably surfaces the relevant
clause(s) in practice. If you have a paid key / higher quota and want
the original multi-turn tool-calling behaviour, see the git history or
re-introduce a bind_tools() loop around llm_structured below.
"""

from langchain_core.messages import SystemMessage, HumanMessage

from subagents.schemas import SubagentResult
from common.gemini_setup import get_embedding_function, get_subagent_llm, invoke_with_retry, get_chroma_client

TOP_K = 4


def _get_collection(collection_name: str):
    client = get_chroma_client()  # shared singleton, see common.gemini_setup
    return client.get_collection(collection_name, embedding_function=get_embedding_function())


def retrieve_context(collection_name: str, query_text: str, top_k: int = TOP_K) -> str:
    """Direct (non-LLM) retrieval from one department's collection."""
    collection = _get_collection(collection_name)
    results = collection.query(query_texts=[query_text], n_results=top_k)
    if not results["documents"] or not results["documents"][0]:
        return "No relevant clauses found."

    blocks = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        blocks.append(
            f"[Section {meta['section']} | Page {meta['page_number']} | "
            f"{meta['doc_id']} v{meta['version']} | effective {meta['effective_date']}]\n"
            f"{doc}"
        )
    return "\n\n---\n\n".join(blocks)


def build_subagent(department: str, collection_name: str, instructions: str):
    """
    Returns a callable: run(task_message: str) -> SubagentResult

    Retrieves the top-K clauses for the task_message directly from this
    department's collection, then makes exactly ONE structured-output
    LLM call to extract findings in the fixed SubagentResult schema.
    """
    llm_structured = get_subagent_llm().with_structured_output(SubagentResult)

    def run(task_message: str) -> SubagentResult:
        context = retrieve_context(collection_name, task_message)

        messages = [
            SystemMessage(content=instructions),
            HumanMessage(
                content=(
                    f"Task: {task_message}\n\n"
                    f"Retrieved clauses from this department's policy collection:\n\n{context}\n\n"
                    "Using ONLY the clauses above, produce your final answer in the required "
                    "structured format. Every finding must have a section number, page, doc_id, "
                    "version and effective_date, copied exactly from the bracketed metadata above "
                    "each clause. If nothing above is relevant to the task, set covered=false and "
                    "explain in gaps rather than guessing."
                )
            ),
        ]
        result: SubagentResult = invoke_with_retry(llm_structured, messages)
        result.department = department  # enforce correct department tag
        return result

    return run
