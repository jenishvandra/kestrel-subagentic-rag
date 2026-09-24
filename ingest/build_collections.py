"""
Phase 2: Embed the clause-level chunks into three separate, persistent
Chroma collections (hr_policy, it_policy, finance_policy), one per
department. Uses Gemini's gemini-embedding-001 for all three so that
similarity scores are comparable.

Run: python -m ingest.build_collections
"""

from ingest.chunk import build_chunks
from common.gemini_setup import get_embedding_function, get_chroma_client

DEPARTMENT_TO_COLLECTION = {
    "hr": "hr_policy",
    "it": "it_policy",
    "finance": "finance_policy",
}

# Six sanity-check searches from the assignment's Phase 2 checkpoint table.
# Note: "meal allowance" expects "4.1" (the actual clause with the daily
# limits table) rather than "4" (the section heading) since our chunking
# splits at the X.Y clause level, not at top-level section headings.
TEST_SEARCHES = [
    ("hr_policy", "how many earned leave days per year", "3.1"),
    ("hr_policy", "notice period for a manager grade", "6.1"),
    ("it_policy", "VPN keeps disconnecting", "5.3"),
    ("it_policy", "lost laptop", "7.1"),
    ("finance_policy", "meal allowance per day", "4.1"),
    ("finance_policy", "repay relocation allowance after resigning", "6.6"),
]


def get_client():
    # Shared singleton client — see common.gemini_setup.get_chroma_client
    # docstring for why we don't open a fresh PersistentClient here.
    return get_chroma_client()


def build_collections(reset: bool = False) -> None:
    client = get_client()
    embedding_fn = get_embedding_function()
    chunks = build_chunks()

    chunks_by_dept: dict[str, list] = {}
    for c in chunks:
        chunks_by_dept.setdefault(c.department, []).append(c)

    for dept, collection_name in DEPARTMENT_TO_COLLECTION.items():
        if reset:
            try:
                client.delete_collection(collection_name)
            except Exception:
                pass

        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

        dept_chunks = chunks_by_dept.get(dept, [])

        # Skip re-embedding entirely if this collection already has the
        # expected number of chunks. Chunk IDs are stable and Phase 1
        # chunking is deterministic, so a matching count means this
        # department was already fully ingested in an earlier run — no
        # need to burn embedding-API quota re-embedding the same 31
        # chunks again. Use reset=True (or delete the chroma_db folder)
        # if you deliberately want to force a full re-embed.
        if not reset and collection.count() == len(dept_chunks) and len(dept_chunks) > 0:
            print(f"{collection_name}: already has {collection.count()} chunks, skipping re-embed.")
            continue

        ids = [c.id for c in dept_chunks]              # stable IDs -> upsert, no dupes
        documents = [c.text for c in dept_chunks]
        metadatas = [
            {
                "department": c.department,
                "doc_id": c.doc_id,
                "title": c.title,
                "version": c.version,
                "effective_date": c.effective_date,
                "section": c.section,
                "section_heading": c.section_heading,
                "page_number": c.page_number,
            }
            for c in dept_chunks
        ]

        # upsert (not add) so re-running ingestion replaces chunks
        # instead of duplicating them (Phase 2, step 3).
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        print(f"{collection_name}: upserted {len(ids)} chunks (total now {collection.count()})")


def run_test_searches() -> None:
    client = get_client()
    embedding_fn = get_embedding_function()
    print("\n=== Phase 2 checkpoint: test searches ===")
    all_passed = True
    for collection_name, query, expected_section in TEST_SEARCHES:
        collection = client.get_collection(collection_name, embedding_function=embedding_fn)
        # top-4 matches what the real subagents use (TOP_K=4 in subagents/builder.py),
        # so this checkpoint reflects what the running system will actually retrieve.
        results = collection.query(query_texts=[query], n_results=4)
        sections = [m["section"] for m in results["metadatas"][0]]
        passed = expected_section in sections
        all_passed &= passed
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {collection_name} | '{query}' -> top4 sections {sections} (expected {expected_section})")
    print(f"\nAll checks passed: {all_passed}")


if __name__ == "__main__":
    build_collections(reset=False)
    run_test_searches()
