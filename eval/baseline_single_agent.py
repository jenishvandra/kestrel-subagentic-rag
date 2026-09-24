"""
Phase 10: The "pilot" single-agent baseline described in the assignment,
Section 2 — one Chroma collection with all three documents' chunks mixed
together, searched once and answered by one Gemini call. Same chunking
and embedding model as the subagent design, so the only variable being
tested is the architecture (one shared collection vs. per-department
subagents).

Uses the same single-retrieval-then-one-LLM-call shape as
subagents/builder.py (see the design note there) so the comparison
between the two designs isn't confounded by one using more API calls
than the other, and so both fit within a free-tier daily quota.
"""

import time

from langchain_core.messages import SystemMessage, HumanMessage

from ingest.chunk import build_chunks
from common.gemini_setup import get_embedding_function, get_supervisor_llm, invoke_with_retry, get_chroma_client

BASELINE_COLLECTION = "baseline_all_policies"
TOP_K = 4


def build_baseline_collection(reset: bool = False):
    embedding_fn = get_embedding_function()
    client = get_chroma_client()  # shared singleton, see common.gemini_setup
    if reset:
        try:
            client.delete_collection(BASELINE_COLLECTION)
        except Exception:
            pass
    collection = client.get_or_create_collection(
        name=BASELINE_COLLECTION, embedding_function=embedding_fn, metadata={"hnsw:space": "cosine"}
    )

    chunks = build_chunks()  # all departments mixed into one collection

    # Skip re-embedding entirely if already fully ingested (see the same
    # optimization + rationale in ingest/build_collections.py). Without
    # this, every single `python -m eval.run_baseline_eval` invocation
    # would re-embed all 93 chunks before even starting the questions —
    # a large, easy-to-avoid waste of embedding-API quota.
    if not reset and collection.count() == len(chunks) and len(chunks) > 0:
        print(f"{BASELINE_COLLECTION}: already has {collection.count()} chunks, skipping re-embed.")
        return collection

    ids = [c.id for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [
        {
            "department": c.department,
            "doc_id": c.doc_id,
            "title": c.title,
            "version": c.version,
            "effective_date": c.effective_date,
            "section": c.section,
            "page_number": c.page_number,
        }
        for c in chunks
    ]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"{BASELINE_COLLECTION}: upserted {len(ids)} chunks (total now {collection.count()})")
    return collection


BASELINE_INSTRUCTIONS = """\
You are Kestrel Systems' employee help-desk assistant. Below are the top matching clauses from a
single search across ALL company policy documents (HR, IT, Finance) mixed together. Use ONLY
these clauses to answer the employee's question. Cite every rule as [DOC_ID, section X.Y]. If
nothing relevant is found, say the topic is not covered. If the question is unrelated to company
policy, say so politely.
"""


def _retrieve(collection, query_text: str, top_k: int = TOP_K) -> str:
    results = collection.query(query_texts=[query_text], n_results=top_k)
    if not results["documents"] or not results["documents"][0]:
        return "No relevant clauses found."
    blocks = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        blocks.append(
            f"[Section {meta['section']} | Page {meta['page_number']} | "
            f"{meta['doc_id']} v{meta['version']} | effective {meta['effective_date']}]\n{doc}"
        )
    return "\n\n---\n\n".join(blocks)


def _extract_text(content) -> str:
    """langchain_google_genai's AIMessage.content is usually a plain string,
    but for some Gemini responses it comes back as a list of content parts
    (e.g. [{'type': 'text', 'text': '...'}, ...]) instead. Normalize both
    shapes to a single string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        return "\n".join(p for p in parts if p)
    return str(content)


def get_baseline_agent():
    embedding_fn = get_embedding_function()
    client = get_chroma_client()  # shared singleton, see common.gemini_setup
    collection = client.get_collection(BASELINE_COLLECTION, embedding_function=embedding_fn)
    llm = get_supervisor_llm()  # same model as the subagent design's supervisor, for a fair comparison

    def run(question: str) -> tuple[str, float]:
        start = time.time()
        context = _retrieve(collection, question)
        messages = [
            SystemMessage(content=BASELINE_INSTRUCTIONS),
            HumanMessage(content=f"Question: {question}\n\nRetrieved clauses:\n\n{context}"),
        ]
        final = invoke_with_retry(llm, messages)
        elapsed = time.time() - start
        return _extract_text(final.content), elapsed

    return run


if __name__ == "__main__":
    build_baseline_collection(reset=False)
    agent = get_baseline_agent()
    answer, elapsed = agent("How many nights of temporary accommodation do I get when relocating?")
    print(answer)
    print(f"\n{elapsed:.2f}s")
