"""
Phase 1b/1c: Split cleaned page text into one chunk per policy clause
(e.g. "4.4", "6.2"), attach full metadata, and further split any very
long clause with a character splitter while keeping the same metadata.
"""

import re
from dataclasses import dataclass, field
from ingest.load_and_clean import load_all_pages, Page

# A clause header looks like "4.4 " or "6.2  " at the start of a line,
# e.g. "4.4 Temporary accommodation: ...". Section-only headers like
# "4. Internal Transfer and Relocation" are also matched so we can pull
# the section heading text that goes with each clause.
CLAUSE_RE = re.compile(r"^(\d+\.\d+)\s+(.*)$", re.MULTILINE)
SECTION_HEADING_RE = re.compile(r"^(\d+)\.\s+([A-Z][^\n]*)$", re.MULTILINE)

MAX_CHUNK_CHARS = 1200  # further split any clause longer than this


@dataclass
class Chunk:
    id: str
    department: str
    doc_id: str
    title: str
    version: str
    effective_date: str
    section: str            # e.g. "4.4"
    section_heading: str    # e.g. "Internal Transfer and Relocation"
    page_number: int
    text: str


def _section_heading_map(full_text: str) -> dict[str, str]:
    """Map top-level section number ('4') -> heading text ('Internal Transfer...')."""
    return {m.group(1): m.group(2).strip() for m in SECTION_HEADING_RE.finditer(full_text)}


def _split_long_text(text: str, max_len: int) -> list[str]:
    """Character-splitter fallback for very long clauses, breaking on
    paragraph/sentence boundaries where possible."""
    if len(text) <= max_len:
        return [text]
    parts = []
    remaining = text
    while len(remaining) > max_len:
        # Prefer to break at the last newline or period before max_len.
        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len * 0.5:
            cut = remaining.rfind(". ", 0, max_len)
        if cut < max_len * 0.5:
            cut = max_len
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def build_chunks() -> list[Chunk]:
    pages = load_all_pages()

    # Group pages by document so we can work over the full document text
    # (clauses/tables can span a page break) while still tracking which
    # page each clause started on.
    by_doc: dict[str, list[Page]] = {}
    for p in pages:
        by_doc.setdefault(p.doc_id, []).append(p)

    chunks: list[Chunk] = []

    for doc_id, doc_pages in by_doc.items():
        doc_pages.sort(key=lambda p: p.page_number)
        meta = doc_pages[0]

        # Build full document text with page-boundary markers so we can
        # recover the correct page number for each clause match.
        marker = "\x00PAGE{}\x00"
        full_text = "".join(marker.format(p.page_number) + p.text + "\n" for p in doc_pages)

        headings = _section_heading_map(full_text.replace("\x00", ""))

        matches = list(CLAUSE_RE.finditer(full_text))
        for idx, m in enumerate(matches):
            section = m.group(1)
            start = m.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
            raw_clause = full_text[start:end]

            # Determine the page this clause started on by finding the
            # last page marker before its start position.
            page_num = doc_pages[0].page_number
            for pm in re.finditer(r"\x00PAGE(\d+)\x00", full_text[:start]):
                page_num = int(pm.group(1))

            # Strip any embedded page markers from the clause text itself.
            clause_text = re.sub(r"\x00PAGE\d+\x00", "", raw_clause).strip()

            top_section = section.split(".")[0]
            heading = headings.get(top_section, "")

            pieces = _split_long_text(clause_text, MAX_CHUNK_CHARS)
            for piece_idx, piece in enumerate(pieces):
                chunk_id = f"{doc_id}-{section}" if len(pieces) == 1 else f"{doc_id}-{section}-{piece_idx+1}"
                chunks.append(
                    Chunk(
                        id=chunk_id,
                        department=meta.department,
                        doc_id=doc_id,
                        title=meta.title,
                        version=meta.version,
                        effective_date=meta.effective_date,
                        section=section,
                        section_heading=heading,
                        page_number=page_num,
                        text=piece,
                    )
                )

    return chunks


if __name__ == "__main__":
    chunks = build_chunks()
    by_dept: dict[str, int] = {}
    for c in chunks:
        by_dept[c.department] = by_dept.get(c.department, 0) + 1
    print("Chunk counts per department:", by_dept)
    print(f"Total chunks: {len(chunks)}\n")

    # Checkpoint: Finance 6.4 must contain full clause text, version, date, page.
    fin_64 = [c for c in chunks if c.doc_id == "KSPL-FIN-POL-003" and c.section == "6.4"]
    print("=== Finance 6.4 check ===")
    for c in fin_64:
        print(f"id={c.id} version={c.version} effective={c.effective_date} page={c.page_number}")
        print(c.text)
        print()

    # Checkpoint: no chunk should contain header/footer artifacts.
    bad = [c for c in chunks if "Internal" in c.text and "Page" in c.text and "KSPL-" in c.text]
    print(f"Chunks with possible leftover masthead text: {len(bad)}")

    # Print a few sample chunks
    print("\n=== Sample chunks ===")
    for c in chunks[:3]:
        print(f"[{c.id}] page={c.page_number} heading='{c.section_heading}'")
        print(c.text[:200])
        print()
